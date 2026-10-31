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

import json
import os
import re
import unicodedata
from dataclasses import dataclass
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
