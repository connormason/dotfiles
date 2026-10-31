#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""
Claude Code statusline renderer

Claude Code pipes session JSON on stdin; this prints the statusline on stdout (one row, more when it wraps). Appearance
comes from the ``statusLineConfig`` block of ``~/.claude/settings.json`` (``$CLAUDE_CONFIG_DIR`` is honored). Missing
or invalid keys fall back to the defaults below, and unknown keys and component names are ignored, so one config block
can be shared with other statusline renderers:

    colorTheme      neon
    style           icon-pill (nerd-font caps around a colored icon cell) | none (icon + text)
    iconSet         nerd-font | text (no icons)
    separator       joins segments when pills are not drawn (default U+2502)
    components      ordered component names; see COMPONENTS
    directoryStyle  short (basename) | full (``~``-folded path)
    contextStyle    line (bar + percent) | percent
    modelStyle      full | short (first word of the display name)
    prUrlFormat     number (append ``#N`` to the git segment) | none
    truncation      wrap (overflow onto new rows) | truncate (drop trailing segments)

Set ``NO_COLOR`` to disable color. The width comes from ``COLUMNS``, which Claude Code sets for statusline commands.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import subprocess
import tempfile
import unicodedata
from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Any

# ==============================================================================
# Glyphs, themes, and icons
# ==============================================================================

RGB = tuple[int, int, int]

PILL_LEFT  = '\ue0b6'  # nerd-font left half-circle cap
PILL_RIGHT = '\ue0b4'  # nerd-font right half-circle cap
BAR_FULL   = '\u2501'  # heavy horizontal line: a filled context cell
BAR_EMPTY  = '\u2500'  # light horizontal line: an empty context cell
SEPARATOR  = '\u2502'  # light vertical line: the default segment separator
ARROW_UP   = '\u2191'
ARROW_DOWN = '\u2193'
DOT        = '\u00b7'
ELLIPSIS   = '\u2026'
PILL_GAP   = '  '


@dataclass(frozen=True)
class Palette:
    """
    Colors for one segment: the pill/icon accent, the text beside it, and the glyph drawn on the accent
    """
    accent:  RGB
    text:    RGB
    icon_fg: RGB = (0, 0, 0)


THEMES: dict[str, dict[str, Palette]] = {
    'neon': {
        'directory':   Palette(accent=(0, 255, 255),   text=(0, 255, 255)),
        'git':         Palette(accent=(57, 255, 20),   text=(57, 255, 20)),
        'active-tool': Palette(accent=(191, 0, 255),   text=(215, 95, 255)),
        'model':       Palette(accent=(255, 0, 255),   text=(255, 85, 255)),
        'effort':      Palette(accent=(42, 42, 74),    text=(144, 144, 208), icon_fg=(255, 255, 255)),
        'context':     Palette(accent=(0, 255, 255),   text=(0, 255, 255)),
        'duration':    Palette(accent=(255, 105, 180), text=(255, 105, 180)),
        'messages':    Palette(accent=(0, 191, 255),   text=(0, 191, 255)),
        'tools':       Palette(accent=(255, 140, 0),   text=(255, 140, 0)),
        'quota':       Palette(accent=(255, 255, 0),   text=(255, 255, 0)),
        'agent':       Palette(accent=(255, 215, 0),   text=(255, 215, 0)),
        'api-base':    Palette(accent=(26, 26, 26),    text=(57, 255, 20),   icon_fg=(0, 255, 255)),
        'warning':     Palette(accent=(255, 165, 0),   text=(255, 165, 0)),
        'critical':    Palette(accent=(255, 49, 49),   text=(255, 49, 49)),
    },
}
FALLBACK_PALETTE = Palette(accent=(255, 255, 255), text=(255, 255, 255))

ICON_SETS: dict[str, dict[str, str]] = {
    'nerd-font': {
        'directory':   '\uf07b',  # nf-fa-folder
        'git':         '\ue0a0',  # nf-pl-branch
        'active-tool': '\uf013',  # nf-fa-cog
        'model':       '\uf2db',  # nf-fa-microchip
        'effort':      '\uf0e7',  # nf-fa-bolt
        'context':     '\uf1c0',  # nf-fa-database
        'duration':    '\uf017',  # nf-fa-clock_o
        'messages':    '\uf075',  # nf-fa-comment
        'tools':       '\uf0ad',  # nf-fa-wrench
        'quota':       '\uf201',  # nf-fa-line_chart
        'agent':       '\U000f06a9',  # nf-md-robot (Nerd Fonts v3 code point)
        'api-base':    '\uf0ac',  # nf-fa-globe
    },
    'text': {},
}

# ==============================================================================
# ANSI helpers
# ==============================================================================

RESET   = '\x1b[0m'
ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')


def fg(rgb: RGB) -> str:
    """
    Build a 24-bit foreground color escape

    :param rgb: red, green, and blue components (0-255)
    :return: the escape sequence
    """
    return f'\x1b[38;2;{rgb[0]};{rgb[1]};{rgb[2]}m'


def bg(rgb: RGB) -> str:
    """
    Build a 24-bit background color escape

    :param rgb: red, green, and blue components (0-255)
    :return: the escape sequence
    """
    return f'\x1b[48;2;{rgb[0]};{rgb[1]};{rgb[2]}m'


def strip_ansi(text: str) -> str:
    """
    Remove SGR escape sequences

    :param text: possibly styled text
    :return: the text without escapes
    """
    return ANSI_RE.sub('', text)


def visible_width(text: str) -> int:
    """
    Measure how many terminal columns text occupies

    :param text: possibly styled text
    :return: the column count (wide characters count two, combining marks zero)
    """
    width = 0
    for char in strip_ansi(text):
        if unicodedata.combining(char):
            continue
        width += 2 if unicodedata.east_asian_width(char) in ('W', 'F') else 1
    return width

# ==============================================================================
# Configuration
# ==============================================================================

SETTINGS_KEY = 'statusLineConfig'

DEFAULT_COMPONENTS: tuple[str, ...] = (
    'directory',
    'git',
    'active-tool',
    'model',
    'effort',
    'context',
    'duration',
    'messages',
    'tools',
    'quota',
    'agent',
    'api-base',
)


@dataclass(frozen=True)
class Config:
    """
    Resolved ``statusLineConfig`` settings, with defaults for anything missing or invalid
    """
    color_theme:     str             = 'neon'
    style:           str             = 'icon-pill'
    icon_set:        str             = 'nerd-font'
    separator:       str             = SEPARATOR
    components:      tuple[str, ...] = DEFAULT_COMPONENTS
    directory_style: str             = 'short'
    context_style:   str             = 'line'
    model_style:     str             = 'full'
    pr_url_format:   str             = 'number'
    truncation:      str             = 'wrap'


# statusLineConfig key -> (Config field, allowed values, or None for any string)
CONFIG_KEYS: dict[str, tuple[str, frozenset[str] | None]] = {
    'colorTheme':     ('color_theme',     frozenset(THEMES)),
    'style':          ('style',           frozenset({'icon-pill', 'none'})),
    'iconSet':        ('icon_set',        frozenset(ICON_SETS)),
    'separator':      ('separator',       None),
    'directoryStyle': ('directory_style', frozenset({'short', 'full'})),
    'contextStyle':   ('context_style',   frozenset({'line', 'percent'})),
    'modelStyle':     ('model_style',     frozenset({'full', 'short'})),
    'prUrlFormat':    ('pr_url_format',   frozenset({'number', 'none'})),
    'truncation':     ('truncation',      frozenset({'wrap', 'truncate'})),
}


def settings_path() -> Path:
    """
    Locate the Claude Code user settings file, honoring ``CLAUDE_CONFIG_DIR``

    :return: path to ``settings.json`` (which may not exist)
    """
    return Path(os.environ.get('CLAUDE_CONFIG_DIR') or '~/.claude').expanduser() / 'settings.json'


def load_config(path: Path) -> Config:
    """
    Read ``statusLineConfig`` from a settings file

    A missing file, unreadable JSON, and invalid values all fall back to the :class:`Config` defaults, key by key, so a
    typo in one setting never blanks the statusline.

    :param path: settings file to read
    :return: the resolved configuration
    """
    try:
        raw = json.loads(path.read_text(encoding='utf-8')).get(SETTINGS_KEY)
    except (OSError, ValueError, AttributeError):
        return Config()
    if not isinstance(raw, dict):
        return Config()

    values: dict[str, Any] = {}
    for key, (attr, allowed) in CONFIG_KEYS.items():
        value = raw.get(key)
        if isinstance(value, str) and ((allowed is None) or (value in allowed)):
            values[attr] = value

    components = raw.get('components')
    if isinstance(components, list) and all(isinstance(name, str) for name in components):
        values['components'] = tuple(components)

    return Config(**values)

# ==============================================================================
# Formatting helpers
# ==============================================================================

BAR_WIDTH        = 10
WARNING_PERCENT  = 70
CRITICAL_PERCENT = 90


def format_duration(ms: float) -> str:
    """
    Format a duration compactly

    :param ms: duration in milliseconds
    :return: ``45s``, ``12m``, or ``1h 5m``
    """
    seconds = max(int(ms // 1000), 0)
    if seconds < 60:
        return f'{seconds}s'

    minutes = seconds // 60
    if minutes < 60:
        return f'{minutes}m'

    hours, minutes = divmod(minutes, 60)
    return f'{hours}h {minutes}m'


def context_bar(percent: float, width: int = BAR_WIDTH) -> str:
    """
    Draw a fixed-width usage bar

    :param percent: usage percentage (clamped to 0-100)
    :param width: number of cells
    :return: filled cells followed by empty cells
    """
    filled = min(max(round(percent / 100 * width), 0), width)
    return BAR_FULL * filled + BAR_EMPTY * (width - filled)


def severity(percent: float) -> str | None:
    """
    Classify a usage percentage

    :param percent: usage percentage
    :return: ``critical``, ``warning``, or None below the warning threshold
    """
    if percent >= CRITICAL_PERCENT:
        return 'critical'
    if percent >= WARNING_PERCENT:
        return 'warning'
    return None

# ==============================================================================
# Segment rendering and layout
# ==============================================================================

@dataclass(frozen=True)
class Segment:
    """
    One component's output: its text and an optional severity (``warning``/``critical``) that overrides its color
    """
    text:     str
    severity: str | None = None


def uses_pills(config: Config, color: bool) -> bool:
    """
    Decide whether segments are drawn as pills

    :param config: resolved configuration
    :param color: whether color output is enabled
    :return: True for the icon-pill style with color and a non-empty icon set
    """
    return color and (config.style == 'icon-pill') and bool(ICON_SETS.get(config.icon_set))


def render_segment(name: str, segment: Segment, config: Config, color: bool) -> str:
    """
    Style one segment

    :param name: component name (selects the icon and palette)
    :param segment: the component's output
    :param config: resolved configuration
    :param color: whether to emit color escapes
    :return: the styled segment
    """
    icon = ICON_SETS.get(config.icon_set, {}).get(name, '')
    if not color:
        return f'{icon} {segment.text}' if icon else segment.text

    palette = THEMES.get(config.color_theme, THEMES['neon']).get(segment.severity or name, FALLBACK_PALETTE)
    if uses_pills(config, color) and icon:
        return (
            f'{fg(palette.accent)}{PILL_LEFT}{bg(palette.accent)}{fg(palette.icon_fg)} {icon} {RESET}'
            f'{fg(palette.accent)}{PILL_RIGHT}{RESET} {fg(palette.text)}{segment.text}{RESET}'
        )

    prefix = f'{fg(palette.accent)}{icon}{RESET} ' if icon else ''
    return f'{prefix}{fg(palette.text)}{segment.text}{RESET}'


def joiner(config: Config, color: bool) -> str:
    """
    Choose the string placed between segments

    :param config: resolved configuration
    :param color: whether color output is enabled
    :return: a two-space gap between pills, else the separator padded with spaces
    """
    return PILL_GAP if uses_pills(config, color) else f' {config.separator} '


def layout(parts: list[str], gap: str, columns: int, truncation: str) -> list[str]:
    """
    Arrange styled segments into rows that fit the terminal width

    :param parts: styled segments, in order
    :param gap: string placed between segments
    :param columns: terminal width; 0 or less means unlimited
    :param truncation: ``wrap`` to overflow onto new rows, ``truncate`` to end the row with an ellipsis
    :return: one string per row
    """
    if not parts:
        return []
    if columns <= 0:
        return [gap.join(parts)]

    rows: list[list[str]] = [[]]
    for part in parts:
        if rows[-1] and (visible_width(gap.join([*rows[-1], part])) > columns):
            if truncation == 'truncate':
                rows[-1].append(ELLIPSIS)
                break
            rows.append([])
        rows[-1].append(part)

    return [gap.join(row) for row in rows]

# ==============================================================================
# Git
# ==============================================================================

GIT_TIMEOUT_S = 1.0


@dataclass(frozen=True)
class GitStatus:
    """
    Branch and working-tree state of a repository
    """
    branch: str
    dirty:  bool = False
    ahead:  int  = 0
    behind: int  = 0


def parse_porcelain_v2(output: str) -> GitStatus | None:
    """
    Parse ``git status --porcelain=v2 --branch`` output

    :param output: the command's stdout
    :return: the parsed status, or None when there is no branch header
    """
    head:   str | None = None
    oid:    str | None = None
    ahead:  int        = 0
    behind: int        = 0
    dirty:  bool       = False

    for line in output.splitlines():
        if line.startswith('# branch.head '):
            head = line[len('# branch.head '):]
        elif line.startswith('# branch.oid '):
            oid = line[len('# branch.oid '):]
        elif line.startswith('# branch.ab '):
            parts = line.split()
            with contextlib.suppress(IndexError, ValueError):
                ahead, behind = int(parts[2]), -int(parts[3])
        elif line and not line.startswith('#'):
            dirty = True

    if head is None:
        return None
    if head == '(detached)':
        head = oid[:7] if (oid and (oid != '(initial)')) else 'HEAD'
    return GitStatus(head, dirty, ahead, behind)


def git_status(cwd: str) -> GitStatus | None:
    """
    Query the repository containing ``cwd``

    ``GIT_OPTIONAL_LOCKS=0`` keeps this read-only probe from taking the index lock that a concurrent git command needs.
    Undecodable bytes in git's output (for example a non-UTF-8 file name) are replaced rather than raised.

    :param cwd: directory to inspect
    :return: the status, or None outside a repository or when git cannot run (missing, slow, or an unusable ``cwd``)
    """
    try:
        result = subprocess.run(
            ['git', '-C', cwd, 'status', '--porcelain=v2', '--branch', '--untracked-files=normal'],
            capture_output=True,
            text=True,
            errors='replace',
            timeout=GIT_TIMEOUT_S,
            check=False,
            env={**os.environ, 'GIT_OPTIONAL_LOCKS': '0'},
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return parse_porcelain_v2(result.stdout)

# ==============================================================================
# Transcript
# ==============================================================================

CACHE_DIR_NAME = 'claude-statusline'
MAX_PENDING    = 64

# User records whose string content starts with one of these are slash-command plumbing, not prompts
COMMAND_PREFIXES = ('<command-', '<local-command-')


@dataclass
class TranscriptStats:
    """
    Running counts parsed from a session transcript, resumable from a byte offset
    """
    path:      str            = ''
    offset:    int            = 0
    prompts:   int            = 0
    tool_uses: int            = 0
    pending:   dict[str, str] = field(default_factory=dict)

    @property
    def active_tool(self) -> str | None:
        """
        Name of the most recently started tool call that has no result yet
        """
        return next(reversed(self.pending.values()), None)


def _record_entry(stats: TranscriptStats, entry: Any) -> None:
    """
    Fold one transcript record into ``stats``

    :param stats: stats to update in place
    :param entry: one parsed JSONL record (any shape; unknown shapes are ignored)
    """
    if (not isinstance(entry, dict)) or entry.get('isSidechain') or entry.get('isMeta'):
        return

    message = entry.get('message')
    content = message.get('content') if isinstance(message, dict) else None
    blocks  = [block for block in content if isinstance(block, dict)] if isinstance(content, list) else []

    if entry.get('type') == 'assistant':
        for block in blocks:
            if block.get('type') == 'tool_use':
                stats.tool_uses += 1
                stats.pending[str(block.get('id', ''))] = str(block.get('name', '?'))
    elif entry.get('type') == 'user':
        if isinstance(content, str):
            if not content.startswith(COMMAND_PREFIXES):
                stats.prompts += 1
        else:
            results = [block for block in blocks if block.get('type') == 'tool_result']
            for block in results:
                stats.pending.pop(str(block.get('tool_use_id', '')), None)
            if (not results) and any(block.get('type') == 'text' for block in blocks):
                stats.prompts += 1

    while len(stats.pending) > MAX_PENDING:
        stats.pending.pop(next(iter(stats.pending)))


def update_stats(stats: TranscriptStats, path: Path) -> TranscriptStats:
    """
    Fold any transcript lines appended since ``stats.offset`` into ``stats``

    Only newline-terminated lines are consumed, so a line Claude Code is still writing is picked up on the next refresh.
    A transcript that shrank, or stats that belong to another transcript, are re-read from the start.

    :param stats: stats from the previous refresh (mutated and returned)
    :param path: the session transcript
    :return: the updated stats (a fresh object when re-reading from the start)
    """
    try:
        size = path.stat().st_size
    except OSError:
        return stats

    if (stats.path != str(path)) or (size < stats.offset):
        stats = TranscriptStats(path=str(path))
    if size == stats.offset:
        return stats

    try:
        with path.open('rb') as handle:
            handle.seek(stats.offset)
            chunk = handle.read(size - stats.offset)
    except OSError:
        return stats

    end = chunk.rfind(b'\n')
    if end < 0:
        return stats

    for line in chunk[:end].split(b'\n'):
        # Cheap pre-filter: every record that can change the counts mentions one of these
        if (b'user' not in line) and (b'tool_use' not in line):
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        _record_entry(stats, entry)

    stats.offset += end + 1
    return stats


def cache_path(session_id: str) -> Path:
    """
    Locate the per-session stats cache

    :param session_id: Claude Code session id (sanitized for use as a file name)
    :return: ``$TMPDIR/claude-statusline/<session>.json``
    """
    safe = re.sub(r'[^A-Za-z0-9_-]', '_', session_id) or 'unknown'
    return Path(os.environ.get('TMPDIR') or tempfile.gettempdir()) / CACHE_DIR_NAME / f'{safe}.json'


def _read_cache(cache: Path) -> TranscriptStats:
    """
    Load cached stats, or fresh stats when the cache is missing or invalid

    :param cache: cache file
    :return: the cached stats
    """
    try:
        raw = json.loads(cache.read_text(encoding='utf-8'))
        return TranscriptStats(
            path=str(raw['path']),
            offset=int(raw['offset']),
            prompts=int(raw['prompts']),
            tool_uses=int(raw['tool_uses']),
            pending={str(key): str(value) for key, value in raw['pending'].items()},
        )
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return TranscriptStats()


def _write_cache(cache: Path, stats: TranscriptStats) -> None:
    """
    Atomically save stats to the cache; failures are ignored (the next refresh re-reads)

    :param cache: cache file
    :param stats: stats to save
    """
    with contextlib.suppress(OSError):
        cache.parent.mkdir(parents=True, exist_ok=True)
        temporary = cache.with_suffix(f'.{os.getpid()}.tmp')
        temporary.write_text(json.dumps(asdict(stats)), encoding='utf-8')
        temporary.replace(cache)


def load_stats(session_id: str, transcript: str) -> TranscriptStats | None:
    """
    Return up-to-date transcript stats for a session, resuming from and refreshing its cache

    :param session_id: Claude Code session id
    :param transcript: transcript path from the session JSON
    :return: the stats, or None when there is no transcript
    """
    if not transcript:
        return None
    path = Path(transcript)
    if not path.is_file():
        return None

    cache  = cache_path(session_id)
    stats  = _read_cache(cache)
    before = (stats.path, stats.offset)
    stats  = update_stats(stats, path)
    if (stats.path, stats.offset) != before:
        _write_cache(cache, stats)
    return stats
