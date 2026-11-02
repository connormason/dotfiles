# Claude Code Config Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the personal Mac the work machine's Claude Code statusline look (via a clean-room Python renderer), the
claude-devtools config, the three generic skills, and the public plugins, and record every remaining work/personal
delta.

**Architecture:** A single stdlib-only Python script, `stow/claude/.claude/statusline/statusline.py`, is stowed to
`~/.claude/statusline/` and run by `uv run --quiet --script`. It renders the session JSON Claude Code pipes on stdin,
styled by the `statusLineConfig` block already present in `render/claude.json`. Settings changes go through the
existing render layers (base `render/claude.json`, overlay `profiles/personal-mac/render/claude.json`); files go
through the `claude` stow package.

**Tech Stack:** Python 3.9+ stdlib (`json`, `subprocess`, `unicodedata`, `dataclasses`), pytest, uv, GNU stow, the
repo's prek hooks.

**Design doc:** [`2026-10-31-claude-config-parity-design.md`](2026-10-31-claude-config-parity-design.md)

## Global Constraints

- Run all Python through `uv`; repo `uv` calls go through `scripts/hooks/uv-public.sh` (for example
  `scripts/hooks/uv-public.sh run pytest ...`), because the work environment injects an internal package index.
- Never run `ruff format`. `ruff check --fix` is allowed. Match the hand-aligned style of the surrounding code.
- Python style: `from __future__ import annotations` first; one import per line (`force-single-line`); single quotes;
  sphinx docstrings in multi-line format; no blank line after a class docstring; ruff target py39, line length 120.
- The statusline script is stdlib-only and must run on Python 3.9 (no `match`, no runtime `X | Y` unions).
- Scripts executed directly do not define `__all__`.
- Tests: `TestXxx` classes, `-> None` on every test, multi-line docstrings (capitalized, no trailing period),
  `@pytest.mark.parametrize` with tuple names.
- This repo is public. No employer hostnames, internal package names, colleague names, or internal tool names in any
  committed file. `scripts/hooks/check-leaks.py` must pass on every commit.
- Write temporary files under the repo's gitignored `.tmp/` or `$TMPDIR`, never `/tmp`.
- The worktree harness rejects shell commands that override `HOME` or compute git arguments at runtime; keep commands
  plain.
- Every commit must pass the prek hooks. If a formatter hook rewrites files, `git add` them again and re-commit.
- Commit messages: conventional commits (`feat(claude): ...`), no attribution trailer.

## Spec Deviations (decided during planning)

1. **`todos` component dropped.** No transcript on the work machine has ever recorded a `TodoWrite`/`TaskCreate`
   call, so the segment would always be empty. The component list in `render/claude.json` loses `todos`; unknown names
   are ignored, so the work config still renders.
2. **`agent` and `api-base` kept.** `agent` shows the documented `agent.name` field; `api-base` shows
   `ANTHROPIC_BASE_URL` only when it is set.
3. **Settings deltas are mostly done already.** `render/claude.json` already carries the generic permissions,
   `spinnerVerbs` (without the employer line), `statusLineConfig`, `theme`, `verbose`, and `worktree.baseRef`. Only
   `statusLine` and the plugins remain. The work `modelSettings` entry for Sonnet (`high`) equals the global
   `effortLevel` and is skipped as redundant.
4. **No shared-file reconciliation needed.** The personal copies of `file-searcher`, `ansible-devops-engineer`,
   `CLAUDE.md`, and the hook scripts are already the generalized versions; the work copies differ only by
   employer-specific wording.
5. **Skills copied, not rewritten.** The user confirmed ownership of all three. `claude-session-logs` switches its
   invocations from `python3` to `uv run --script`, because the base permissions deny `Bash(python3:*)`.
6. **Quota segment** shows the claude.ai rate-limit windows (`5h`, `7d`) when present, else the session cost.
   `rate_limits.spend_limit` is not rendered.
7. **Pills join with two spaces.** Matching the observed output, `separator` applies only when pills are not drawn
   (`none` style, the `text` icon set, or `NO_COLOR`).
8. **Transcript reading is incremental** (a per-session byte-offset cache under `$TMPDIR`) rather than a tail-limited
   read: totals stay exact and each refresh parses only appended lines.
9. **Commits:** one per task rather than the four in the design.

## Statusline Input Reference

Documented session-JSON fields (code.claude.com/docs/en/statusline) the renderer reads. Every field may be absent or
null; components then return nothing rather than fail.

| Field                                                   | Used by                             |
| ------------------------------------------------------- | ----------------------------------- |
| `workspace.current_dir`, `cwd`                          | `directory`, `git`                  |
| `model.display_name`, `model.id`                        | `model`                             |
| `effort.level`                                          | `effort`                            |
| `context_window.used_percentage`                        | `context`                           |
| `cost.total_duration_ms`                                | `duration`                          |
| `cost.total_cost_usd`                                   | `quota` (fallback)                  |
| `rate_limits.five_hour/seven_day.used_percentage`       | `quota`                             |
| `agent.name`                                            | `agent`                             |
| `pr.number`                                             | `git` (`prUrlFormat`)               |
| `session_id`, `transcript_path`                         | `messages`, `tools`, `active-tool`  |

The transcript format is officially internal and unstable, so the parser tolerates unknown shapes. It treats records
as `{"type": "user"|"assistant", "isMeta"?: bool, "isSidechain"?: bool, "message": {"content": str | [block, ...]}}`,
with blocks `{"type": "tool_use", "id", "name"}` (assistant) and `{"type": "tool_result", "tool_use_id"}` (user).
Records are compact JSONL (verified against real transcripts on the work machine).

## File Map

| File                                                          | Change | Responsibility                                                     |
| ------------------------------------------------------------- | ------ | ------------------------------------------------------------------ |
| `stow/claude/.claude/statusline/statusline.py`                | Create | The renderer (config, themes, layout, git, transcript, components) |
| `tests/unit/test_statusline.py`                               | Create | Unit, end-to-end, and rendered-settings guardrail tests            |
| `render/claude.json`                                          | Modify | Add `statusLine`; drop `todos` from `statusLineConfig.components`  |
| `profiles/personal-mac/render/claude.json`                    | Modify | Enable the public plugins                                          |
| `profiles/personal-mac/README.md`                             | Modify | Mention the plugins in the `render/claude.json` row                |
| `stow/README.md`                                              | Modify | Mention the statusline and devtools config in the `claude` row     |
| `stow/claude/.claude/claude-devtools-config.json`             | Create | claude-devtools app config (copied from work)                      |
| `stow/claude/.claude/skills/claude-session-logs/`             | Create | Skill copied from work, switched to `uv run --script`              |
| `stow/claude/.claude/skills/gh-pr-comments/`                  | Create | Skill copied from work, GitHub Enterprise example genericized      |
| `stow/claude/.claude/skills/shell-scripting/`                 | Create | Skill copied from work unchanged                                   |
| `docs/plans/2026-10/2026-10-31-claude-config-parity-delta.md` | Create | Full work/personal delta report with dispositions                  |

---

### Task 1: Statusline rendering primitives

Config loading, themes, icons, ANSI helpers, formatting helpers, segment rendering, and row layout: everything pure.

**Files:**

- Create: `stow/claude/.claude/statusline/statusline.py`
- Create: `tests/unit/test_statusline.py`

**Interfaces:**

- Produces (module-level names later tasks and tests rely on): `RGB`, `PILL_LEFT`, `PILL_RIGHT`, `BAR_FULL`,
  `BAR_EMPTY`, `SEPARATOR`, `ARROW_UP`, `ARROW_DOWN`, `DOT`, `ELLIPSIS`, `PILL_GAP`, `Palette(accent, text, icon_fg)`,
  `THEMES: dict[str, dict[str, Palette]]`, `FALLBACK_PALETTE`, `ICON_SETS: dict[str, dict[str, str]]`, `RESET`,
  `fg(rgb) -> str`, `bg(rgb) -> str`, `strip_ansi(text) -> str`, `visible_width(text) -> int`, `DEFAULT_COMPONENTS`,
  `Config` (frozen dataclass: `color_theme`, `style`, `icon_set`, `separator`, `components`, `directory_style`,
  `context_style`, `model_style`, `pr_url_format`, `truncation`), `settings_path() -> Path`,
  `load_config(path: Path) -> Config`, `format_duration(ms: float) -> str`,
  `context_bar(percent: float, width: int = 10) -> str`, `severity(percent: float) -> str | None`,
  `Segment(text, severity=None)`, `uses_pills(config, color) -> bool`,
  `render_segment(name, segment, config, color) -> str`, `joiner(config, color) -> str`,
  `layout(parts, gap, columns, truncation) -> list[str]`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_statusline.py`:

```python
"""
Unit tests for stow/claude/.claude/statusline/statusline.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType

REPO_ROOT   = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / 'stow' / 'claude' / '.claude' / 'statusline' / 'statusline.py'


def _load_module(name: str, path: Path) -> ModuleType:
    """
    Import a standalone script as module ``name`` without leaving a __pycache__ beside it
    """
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec        is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module

    # The script lives in a stow package: keep exec_module from leaving a __pycache__ that stow would link into $HOME
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous

    return module


statusline = _load_module('statusline', SCRIPT_PATH)


def _settings(tmp_path: Path, config: object) -> Path:
    """
    Write a settings.json whose ``statusLineConfig`` is ``config``
    """
    path = tmp_path / 'settings.json'
    path.write_text(json.dumps({'statusLineConfig': config}), encoding='utf-8')
    return path


# ==============================================================================
# Config
# ==============================================================================

class TestLoadConfig:
    """
    Tests for load_config and settings_path
    """
    def test_missing_file_gives_defaults(self, tmp_path: Path) -> None:
        """
        Fall back to every default when the settings file does not exist
        """
        assert statusline.load_config(tmp_path / 'absent.json') == statusline.Config()

    @pytest.mark.parametrize(
        'content',
        [
            'not json',
            '[1, 2]',
            '{"statusLineConfig": "neon"}',
            '{}',
        ],
    )
    def test_unusable_content_gives_defaults(self, tmp_path: Path, content: str) -> None:
        """
        Fall back to every default when the file or its statusLineConfig block is unusable
        """
        path = tmp_path / 'settings.json'
        path.write_text(content, encoding='utf-8')
        assert statusline.load_config(path) == statusline.Config()

    def test_reads_valid_values(self, tmp_path: Path) -> None:
        """
        Map every supported camelCase key onto its Config field
        """
        path = _settings(tmp_path, {
            'colorTheme':     'neon',
            'style':          'none',
            'iconSet':        'text',
            'separator':      '|',
            'components':     ['model', 'git'],
            'directoryStyle': 'full',
            'contextStyle':   'percent',
            'modelStyle':     'short',
            'prUrlFormat':    'none',
            'truncation':     'truncate',
        })
        assert statusline.load_config(path) == statusline.Config(
            color_theme='neon',
            style='none',
            icon_set='text',
            separator='|',
            components=('model', 'git'),
            directory_style='full',
            context_style='percent',
            model_style='short',
            pr_url_format='none',
            truncation='truncate',
        )

    def test_invalid_values_fall_back_per_key(self, tmp_path: Path) -> None:
        """
        Replace only the invalid keys with defaults and keep the valid ones
        """
        path = _settings(tmp_path, {
            'colorTheme': 'dracula',
            'style':      'capsule',
            'components': 'model',
            'separator':  7,
            'modelStyle': 'short',
            'lines':      1,
        })
        config = statusline.load_config(path)
        assert config.color_theme == 'neon'
        assert config.style       == 'icon-pill'
        assert config.components  == statusline.DEFAULT_COMPONENTS
        assert config.separator   == statusline.SEPARATOR
        assert config.model_style == 'short'

    def test_non_string_components_fall_back(self, tmp_path: Path) -> None:
        """
        Reject a component list that contains non-strings
        """
        path = _settings(tmp_path, {'components': ['model', 3]})
        assert statusline.load_config(path).components == statusline.DEFAULT_COMPONENTS

    def test_settings_path_honors_claude_config_dir(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """
        Resolve settings.json inside CLAUDE_CONFIG_DIR when it is set
        """
        monkeypatch.setenv('CLAUDE_CONFIG_DIR', str(tmp_path))
        assert statusline.settings_path() == tmp_path / 'settings.json'

    def test_settings_path_defaults_to_home(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """
        Resolve ~/.claude/settings.json when CLAUDE_CONFIG_DIR is unset
        """
        monkeypatch.delenv('CLAUDE_CONFIG_DIR', raising=False)
        monkeypatch.setenv('HOME', str(tmp_path))
        assert statusline.settings_path() == tmp_path / '.claude' / 'settings.json'


# ==============================================================================
# Formatting helpers
# ==============================================================================

class TestFormatDuration:
    """
    Tests for format_duration
    """
    @pytest.mark.parametrize(
        ('ms', 'expected'),
        [
            (0,         '0s'),
            (45_000,    '45s'),
            (59_999,    '59s'),
            (754_000,   '12m'),
            (3_600_000, '1h 0m'),
            (3_900_000, '1h 5m'),
            (-5,        '0s'),
        ],
    )
    def test_formats(self, ms: float, expected: str) -> None:
        """
        Render seconds, then minutes, then hours plus minutes
        """
        assert statusline.format_duration(ms) == expected


class TestContextBar:
    """
    Tests for context_bar
    """
    @pytest.mark.parametrize(
        ('percent', 'filled'),
        [
            (0,   0),
            (42,  4),
            (100, 10),
            (150, 10),
            (-3,  0),
        ],
    )
    def test_fill(self, percent: float, filled: int) -> None:
        """
        Fill a proportional number of the ten cells, clamped to the bar
        """
        expected = statusline.BAR_FULL * filled + statusline.BAR_EMPTY * (10 - filled)
        assert statusline.context_bar(percent) == expected


class TestSeverity:
    """
    Tests for severity
    """
    @pytest.mark.parametrize(
        ('percent', 'expected'),
        [
            (0,    None),
            (69.9, None),
            (70,   'warning'),
            (89,   'warning'),
            (90,   'critical'),
            (100,  'critical'),
        ],
    )
    def test_thresholds(self, percent: float, expected: str | None) -> None:
        """
        Escalate to warning at 70 percent and critical at 90 percent
        """
        assert statusline.severity(percent) == expected


class TestVisibleWidth:
    """
    Tests for visible_width and strip_ansi
    """
    def test_ignores_ansi(self) -> None:
        """
        Exclude escape sequences from the width
        """
        assert statusline.visible_width(f'{statusline.fg((1, 2, 3))}abc{statusline.RESET}') == 3

    def test_wide_characters_count_double(self) -> None:
        """
        Count East Asian wide characters as two columns
        """
        assert statusline.visible_width('日本') == 4

    def test_combining_marks_count_zero(self) -> None:
        """
        Count combining marks as zero columns
        """
        assert statusline.visible_width('e\u0301') == 1


# ==============================================================================
# Segment rendering and layout
# ==============================================================================

class TestRenderSegment:
    """
    Tests for render_segment
    """
    def test_plain_without_color(self) -> None:
        """
        Emit icon and text with no escapes when color is off
        """
        icon = statusline.ICON_SETS['nerd-font']['model']
        out  = statusline.render_segment('model', statusline.Segment('Opus'), statusline.Config(), color=False)
        assert out == f'{icon} Opus'

    def test_text_icon_set_has_no_icon(self) -> None:
        """
        Emit only the text with the text icon set
        """
        config = statusline.Config(icon_set='text')
        assert statusline.render_segment('model', statusline.Segment('Opus'), config, color=False) == 'Opus'

    def test_icon_pill_structure(self) -> None:
        """
        Draw caps around a colored icon cell, then the text in the segment's text color
        """
        palette = statusline.THEMES['neon']['model']
        icon    = statusline.ICON_SETS['nerd-font']['model']
        out     = statusline.render_segment('model', statusline.Segment('Opus'), statusline.Config(), color=True)
        assert out == (
            f'{statusline.fg(palette.accent)}{statusline.PILL_LEFT}{statusline.bg(palette.accent)}'
            f'{statusline.fg(palette.icon_fg)} {icon} {statusline.RESET}'
            f'{statusline.fg(palette.accent)}{statusline.PILL_RIGHT}{statusline.RESET} '
            f'{statusline.fg(palette.text)}Opus{statusline.RESET}'
        )
        assert statusline.strip_ansi(out) == f'{statusline.PILL_LEFT} {icon} {statusline.PILL_RIGHT} Opus'

    def test_severity_overrides_palette(self) -> None:
        """
        Color a segment with the severity palette instead of its own
        """
        segment = statusline.Segment('95%', 'critical')
        out     = statusline.render_segment('context', segment, statusline.Config(), color=True)
        assert statusline.fg(statusline.THEMES['neon']['critical'].text)    in out
        assert statusline.fg(statusline.THEMES['neon']['context'].text) not in out

    def test_none_style_has_no_caps(self) -> None:
        """
        Draw a colored icon and text without pill caps in the none style
        """
        icon = statusline.ICON_SETS['nerd-font']['model']
        out  = statusline.render_segment('model', statusline.Segment('Opus'), statusline.Config(style='none'), True)
        assert statusline.PILL_LEFT not in out
        assert statusline.strip_ansi(out) == f'{icon} Opus'

    def test_unknown_component_uses_fallback_palette(self) -> None:
        """
        Color a component missing from the theme with the fallback palette
        """
        out = statusline.render_segment('mystery', statusline.Segment('x'), statusline.Config(style='none'), True)
        assert statusline.strip_ansi(out) == 'x'
        assert statusline.fg(statusline.FALLBACK_PALETTE.text) in out


class TestJoiner:
    """
    Tests for joiner
    """
    @pytest.mark.parametrize(
        ('style', 'icon_set', 'color', 'pills'),
        [
            ('icon-pill', 'nerd-font', True,  True),
            ('icon-pill', 'nerd-font', False, False),
            ('icon-pill', 'text',      True,  False),
            ('none',      'nerd-font', True,  False),
        ],
    )
    def test_gap_or_separator(self, style: str, icon_set: str, color: bool, pills: bool) -> None:
        """
        Join pills with a two-space gap and everything else with the separator
        """
        config   = statusline.Config(style=style, icon_set=icon_set)
        expected = statusline.PILL_GAP if pills else f' {statusline.SEPARATOR} '
        assert statusline.joiner(config, color) == expected


class TestLayout:
    """
    Tests for layout
    """
    def test_empty(self) -> None:
        """
        Produce no rows for no segments
        """
        assert statusline.layout([], ' | ', 80, 'wrap') == []

    def test_unbounded_columns_single_row(self) -> None:
        """
        Keep every segment on one row when the width is unknown
        """
        assert statusline.layout(['a', 'b'], ' | ', 0, 'wrap') == ['a | b']

    def test_wraps_at_segment_boundaries(self) -> None:
        """
        Start a new row when the next segment would overflow
        """
        assert statusline.layout(['aaaa', 'bbbb', 'cccc'], ' | ', 11, 'wrap') == ['aaaa | bbbb', 'cccc']

    def test_truncate_drops_trailing_segments(self) -> None:
        """
        Replace overflowing segments with an ellipsis
        """
        expected = [f'aaaa | bbbb | {statusline.ELLIPSIS}']
        assert statusline.layout(['aaaa', 'bbbb', 'cccc'], ' | ', 11, 'truncate') == expected

    def test_oversized_segment_gets_own_row(self) -> None:
        """
        Place a segment wider than the terminal on a row of its own
        """
        assert statusline.layout(['a' * 20, 'b'], ' | ', 5, 'wrap') == ['a' * 20, 'b']

    def test_measures_visible_width(self) -> None:
        """
        Ignore escape sequences when deciding whether a row fits
        """
        color = statusline.fg((255, 0, 0))
        parts = [f'{color}aaaa{statusline.RESET}', f'{color}bbbb{statusline.RESET}']
        assert len(statusline.layout(parts, ' | ', 11, 'wrap')) == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `scripts/hooks/uv-public.sh run pytest tests/unit/test_statusline.py -q`
Expected: a collection error, because the script does not exist yet.

- [ ] **Step 3: Write the implementation**

Create `stow/claude/.claude/statusline/statusline.py`:

```python
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
```

Make it executable: `chmod +x stow/claude/.claude/statusline/statusline.py`

- [ ] **Step 4: Run the tests to verify they pass**

Run: `scripts/hooks/uv-public.sh run pytest tests/unit/test_statusline.py -q`
Expected: all tests pass.

- [ ] **Step 5: Lint**

Run: `scripts/hooks/uv-public.sh run ruff check --fix stow/claude/.claude/statusline/statusline.py tests/unit/test_statusline.py`
then `scripts/hooks/uv-public.sh run mypy stow/claude/.claude/statusline/statusline.py tests/unit/test_statusline.py`
Expected: no errors. If ruff reports `EXE003` (shebang without `python`) on the `uv run` shebang, change the first line
to `#!/usr/bin/env python3` (the settings command invokes uv explicitly) and re-run.

- [ ] **Step 6: Commit**

```bash
git add stow/claude/.claude/statusline/statusline.py tests/unit/test_statusline.py
git commit -m "feat(claude): add statusline rendering primitives"
```

---

### Task 2: Statusline data sources (git and transcript)

**Files:**

- Modify: `stow/claude/.claude/statusline/statusline.py` (import block; append two sections)
- Modify: `tests/unit/test_statusline.py` (import block; append two sections)

**Interfaces:**

- Consumes: the Task 1 module.
- Produces: `GitStatus(branch, dirty=False, ahead=0, behind=0)`, `parse_porcelain_v2(output: str) -> GitStatus | None`,
  `git_status(cwd: str) -> GitStatus | None`, `MAX_PENDING`, `TranscriptStats(path='', offset=0, prompts=0,
  tool_uses=0, pending={})` with property `active_tool -> str | None`,
  `update_stats(stats: TranscriptStats, path: Path) -> TranscriptStats`, `cache_path(session_id: str) -> Path`,
  `load_stats(session_id: str, transcript: str) -> TranscriptStats | None`.

- [ ] **Step 1: Write the failing tests**

In `tests/unit/test_statusline.py`, replace the import block (between `from __future__ import annotations` and
`if TYPE_CHECKING:`) with:

```python
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
```

Append:

```python
# ==============================================================================
# Git
# ==============================================================================

class TestParsePorcelainV2:
    """
    Tests for parse_porcelain_v2
    """
    def test_clean_branch(self) -> None:
        """
        Report the branch of a clean, in-sync checkout
        """
        output = '# branch.oid abc1234def\n# branch.head main\n# branch.upstream origin/main\n# branch.ab +0 -0\n'
        assert statusline.parse_porcelain_v2(output) == statusline.GitStatus('main')

    def test_dirty_with_ahead_behind(self) -> None:
        """
        Report dirtiness and ahead/behind counts
        """
        output = (
            '# branch.oid abc\n# branch.head feat\n# branch.ab +2 -1\n'
            '1 .M N... 100644 100644 100644 aaa bbb file.py\n'
            '? new.txt\n'
        )
        assert statusline.parse_porcelain_v2(output) == statusline.GitStatus('feat', dirty=True, ahead=2, behind=1)

    def test_detached_uses_short_oid(self) -> None:
        """
        Name a detached HEAD by its abbreviated commit id
        """
        output = '# branch.oid 0123456789abcdef\n# branch.head (detached)\n'
        assert statusline.parse_porcelain_v2(output) == statusline.GitStatus('0123456')

    def test_detached_without_commits(self) -> None:
        """
        Name a detached HEAD with no commits HEAD
        """
        output = '# branch.oid (initial)\n# branch.head (detached)\n'
        assert statusline.parse_porcelain_v2(output) == statusline.GitStatus('HEAD')

    def test_malformed_ahead_behind_is_ignored(self) -> None:
        """
        Ignore an unparsable ahead/behind header
        """
        output = '# branch.head main\n# branch.ab garbage\n'
        assert statusline.parse_porcelain_v2(output) == statusline.GitStatus('main')

    def test_no_branch_header(self) -> None:
        """
        Return None when the output has no branch header
        """
        assert statusline.parse_porcelain_v2('') is None


class TestGitStatus:
    """
    Tests for git_status
    """
    @pytest.mark.skipif(not shutil.which('git'), reason='Git not available')
    def test_real_repository(self, tmp_path: Path) -> None:
        """
        Read the branch and dirtiness of a real repository
        """
        subprocess.run(['git', 'init', '-q', '-b', 'trunk', str(tmp_path)], check=True)
        (tmp_path / 'file.txt').write_text('x', encoding='utf-8')
        assert statusline.git_status(str(tmp_path)) == statusline.GitStatus('trunk', dirty=True)

    @pytest.mark.skipif(not shutil.which('git'), reason='Git not available')
    def test_non_repository(self, tmp_path: Path) -> None:
        """
        Return None outside a repository
        """
        assert statusline.git_status(str(tmp_path)) is None

    def test_missing_git_binary(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """
        Return None when git cannot be executed
        """
        monkeypatch.setenv('PATH', str(tmp_path))
        assert statusline.git_status(str(tmp_path)) is None


# ==============================================================================
# Transcript
# ==============================================================================

def _prompt(text: str, **extra: object) -> dict[str, object]:
    """
    A user prompt record
    """
    return {'type': 'user', 'message': {'role': 'user', 'content': text}, **extra}


def _tool_use(tool_id: str, name: str, **extra: object) -> dict[str, object]:
    """
    An assistant record that starts one tool call
    """
    content = [{'type': 'text', 'text': 'ok'}, {'type': 'tool_use', 'id': tool_id, 'name': name, 'input': {}}]
    return {'type': 'assistant', 'message': {'role': 'assistant', 'content': content}, **extra}


def _tool_result(tool_id: str) -> dict[str, object]:
    """
    A user record carrying one tool result
    """
    content = [{'type': 'tool_result', 'tool_use_id': tool_id, 'content': 'done'}]
    return {'type': 'user', 'message': {'role': 'user', 'content': content}}


def _append(path: Path, *entries: object, partial: str = '') -> None:
    """
    Append compact JSONL records (and an optional unterminated fragment) to a transcript
    """
    with path.open('a', encoding='utf-8') as handle:
        for entry in entries:
            handle.write(json.dumps(entry, separators=(',', ':')) + '\n')
        handle.write(partial)


class TestUpdateStats:
    """
    Tests for update_stats and TranscriptStats
    """
    def test_counts_prompts_and_tool_uses(self, tmp_path: Path) -> None:
        """
        Count prompts and tool calls, and track the unresolved call as active
        """
        path = tmp_path / 't.jsonl'
        _append(path, _prompt('hi'), _tool_use('t1', 'Bash'), _tool_result('t1'), _tool_use('t2', 'Read'))

        stats = statusline.update_stats(statusline.TranscriptStats(), path)
        assert (stats.prompts, stats.tool_uses) == (1, 2)
        assert stats.pending     == {'t2': 'Read'}
        assert stats.active_tool == 'Read'
        assert stats.offset      == path.stat().st_size

    def test_no_active_tool_when_all_resolved(self, tmp_path: Path) -> None:
        """
        Report no active tool once every call has a result
        """
        path = tmp_path / 't.jsonl'
        _append(path, _tool_use('t1', 'Bash'), _tool_result('t1'))
        assert statusline.update_stats(statusline.TranscriptStats(), path).active_tool is None

    def test_text_block_prompts_count_and_command_plumbing_does_not(self, tmp_path: Path) -> None:
        """
        Count text-block prompts but not slash-command plumbing records
        """
        path = tmp_path / 't.jsonl'
        _append(
            path,
            _prompt('<command-name>/model</command-name>'),
            _prompt('<local-command-stdout>done</local-command-stdout>'),
            {'type': 'user', 'message': {'content': [{'type': 'text', 'text': 'hi'}]}},
        )
        assert statusline.update_stats(statusline.TranscriptStats(), path).prompts == 1

    def test_meta_and_sidechain_records_are_ignored(self, tmp_path: Path) -> None:
        """
        Skip meta records and subagent sidechain records
        """
        path = tmp_path / 't.jsonl'
        _append(path, _prompt('x', isMeta=True), _tool_use('t9', 'Bash', isSidechain=True))

        stats = statusline.update_stats(statusline.TranscriptStats(), path)
        assert (stats.prompts, stats.tool_uses) == (0, 0)

    def test_malformed_and_foreign_lines_are_ignored(self, tmp_path: Path) -> None:
        """
        Skip unparsable lines, non-object lines, and records without a message
        """
        path = tmp_path / 't.jsonl'
        path.write_text('not json user\n[1]\n{"type":"attachment"}\n{"type":"user"}\n', encoding='utf-8')

        stats = statusline.update_stats(statusline.TranscriptStats(), path)
        assert (stats.prompts, stats.tool_uses) == (0, 0)
        assert stats.offset == path.stat().st_size

    def test_resumes_without_double_counting(self, tmp_path: Path) -> None:
        """
        Fold in only the lines appended since the last update
        """
        path = tmp_path / 't.jsonl'
        _append(path, _prompt('a'))
        stats = statusline.update_stats(statusline.TranscriptStats(), path)

        _append(path, _tool_use('t1', 'Bash'))
        stats = statusline.update_stats(stats, path)
        assert (stats.prompts, stats.tool_uses) == (1, 1)
        assert stats.offset == path.stat().st_size

    def test_unterminated_line_waits_for_newline(self, tmp_path: Path) -> None:
        """
        Leave a partially written line for the next update
        """
        path = tmp_path / 't.jsonl'
        _append(path, _prompt('a'), partial='{"type":"user","mess')
        stats = statusline.update_stats(statusline.TranscriptStats(), path)
        assert stats.prompts == 1
        assert stats.offset  == path.stat().st_size - len('{"type":"user","mess')

        _append(path, partial='age":{"content":"b"}}\n')
        assert statusline.update_stats(stats, path).prompts == 2

    def test_shrunk_file_is_reread(self, tmp_path: Path) -> None:
        """
        Start over when the transcript is smaller than the saved offset
        """
        path = tmp_path / 't.jsonl'
        _append(path, _prompt('a'), _prompt('b'))
        stats = statusline.update_stats(statusline.TranscriptStats(), path)

        path.write_text(json.dumps(_prompt('c')) + '\n', encoding='utf-8')
        assert statusline.update_stats(stats, path).prompts == 1

    def test_other_path_is_read_from_start(self, tmp_path: Path) -> None:
        """
        Start over when the stats belong to a different transcript
        """
        first, second = tmp_path / 'a.jsonl', tmp_path / 'b.jsonl'
        _append(first, _prompt('a'), _prompt('b'))
        _append(second, _prompt('c'))

        stats = statusline.update_stats(statusline.TranscriptStats(), first)
        assert statusline.update_stats(stats, second).prompts == 1

    def test_missing_file_leaves_stats_unchanged(self, tmp_path: Path) -> None:
        """
        Return the stats untouched when the transcript does not exist
        """
        stats = statusline.TranscriptStats()
        assert statusline.update_stats(stats, tmp_path / 'absent.jsonl') == statusline.TranscriptStats()

    def test_pending_calls_are_capped(self, tmp_path: Path) -> None:
        """
        Evict the oldest unresolved calls beyond MAX_PENDING
        """
        path  = tmp_path / 't.jsonl'
        total = statusline.MAX_PENDING + 5
        _append(path, *(_tool_use(f't{index}', f'Tool{index}') for index in range(total)))

        stats = statusline.update_stats(statusline.TranscriptStats(), path)
        assert len(stats.pending) == statusline.MAX_PENDING
        assert 't0' not in stats.pending
        assert stats.active_tool  == f'Tool{total - 1}'


class TestLoadStats:
    """
    Tests for load_stats and cache_path
    """
    @pytest.fixture(autouse=True)
    def _isolated_tmpdir(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """
        Point TMPDIR at a throwaway directory so no real cache is touched
        """
        monkeypatch.setenv('TMPDIR', str(tmp_path / 'tmp'))

    def test_no_transcript(self, tmp_path: Path) -> None:
        """
        Return None for an empty or missing transcript path
        """
        assert statusline.load_stats('s', '') is None
        assert statusline.load_stats('s', str(tmp_path / 'absent.jsonl')) is None

    def test_resumes_from_cache(self, tmp_path: Path) -> None:
        """
        Resume from the cached offset and counts instead of re-reading the transcript
        """
        path = tmp_path / 't.jsonl'
        _append(path, _prompt('a'))
        assert statusline.load_stats('sess-1', str(path)).prompts == 1

        cache = statusline.cache_path('sess-1')
        saved = json.loads(cache.read_text(encoding='utf-8'))
        saved['prompts'] = 10
        cache.write_text(json.dumps(saved), encoding='utf-8')

        _append(path, _prompt('b'))
        assert statusline.load_stats('sess-1', str(path)).prompts == 11

    def test_corrupt_cache_is_ignored(self, tmp_path: Path) -> None:
        """
        Re-read the transcript when the cache is unreadable
        """
        path = tmp_path / 't.jsonl'
        _append(path, _prompt('a'), _prompt('b'))

        cache = statusline.cache_path('sess-2')
        cache.parent.mkdir(parents=True)
        cache.write_text('garbage', encoding='utf-8')
        assert statusline.load_stats('sess-2', str(path)).prompts == 2

    def test_cache_path_is_sanitized(self, tmp_path: Path) -> None:
        """
        Keep session ids from escaping the cache directory
        """
        path = statusline.cache_path('../../etc')
        assert path.parent == tmp_path / 'tmp' / 'claude-statusline'
        assert path.name   == '______etc.json'
        assert statusline.cache_path('').name == 'unknown.json'
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `scripts/hooks/uv-public.sh run pytest tests/unit/test_statusline.py -q`
Expected: the new tests fail with `AttributeError: module 'statusline' has no attribute 'parse_porcelain_v2'` (and
similar); the Task 1 tests still pass.

- [ ] **Step 3: Write the implementation**

In `statusline.py`, replace the import block with:

```python
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
```

Append to the end of the file:

```python
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

    :param cwd: directory to inspect
    :return: the status, or None outside a repository or when git is unavailable or slow
    """
    try:
        result = subprocess.run(
            ['git', '-C', cwd, 'status', '--porcelain=v2', '--branch', '--untracked-files=normal'],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_S,
            check=False,
            env={**os.environ, 'GIT_OPTIONAL_LOCKS': '0'},
        )
    except (OSError, subprocess.SubprocessError):
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `scripts/hooks/uv-public.sh run pytest tests/unit/test_statusline.py -q`
Expected: all tests pass.

- [ ] **Step 5: Lint**

Run: `scripts/hooks/uv-public.sh run ruff check --fix stow/claude/.claude/statusline/statusline.py tests/unit/test_statusline.py`
then `scripts/hooks/uv-public.sh run mypy stow/claude/.claude/statusline/statusline.py tests/unit/test_statusline.py`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add stow/claude/.claude/statusline/statusline.py tests/unit/test_statusline.py
git commit -m "feat(claude): read git and transcript state for the statusline"
```

---

### Task 3: Statusline components, render, and entry point

**Files:**

- Modify: `stow/claude/.claude/statusline/statusline.py` (import block; append three sections)
- Modify: `tests/unit/test_statusline.py` (import block; append three sections)

**Interfaces:**

- Consumes: everything Tasks 1 and 2 produce.
- Produces: `Context(data, config, env, git_fn, stats_fn)` with `cwd`, `git`, `stats`; `dig(data, *keys)`;
  `COMPONENTS: dict[str, Callable[[Context], Segment | None]]`; `render(data, config, *, columns=0, color=True,
  env=None, git_fn=git_status, stats_fn=load_stats) -> str`; `read_session(stream: BinaryIO) -> dict`;
  `terminal_columns(env) -> int`; `fallback_line(data) -> str`; `main() -> int`.

- [ ] **Step 1: Write the failing tests**

In `tests/unit/test_statusline.py`, replace the import block with:

```python
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any

import pytest
```

Append:

```python
# ==============================================================================
# Components
# ==============================================================================

SAMPLE: dict[str, Any] = {
    'session_id':      'sess-0001',
    'transcript_path': '',
    'cwd':             '/work/proj',
    'model':           {'id': 'claude-sonnet-5-5', 'display_name': 'Sonnet 5.5'},
    'workspace':       {'current_dir': '/work/proj', 'project_dir': '/work/proj'},
    'cost':            {'total_cost_usd': 1.23, 'total_duration_ms': 754_000},
    'context_window':  {'used_percentage': 42, 'context_window_size': 200_000},
    'effort':          {'level': 'high'},
}


def _ctx(
    data:   dict[str, Any] | None = None,
    *,
    config: Any                   = None,
    env:    dict[str, str] | None = None,
    git:    Any                   = None,
    stats:  Any                   = None,
) -> Any:
    """
    Build a Context with stubbed git and transcript sources and an empty environment by default
    """
    return statusline.Context(
        data or {},
        config or statusline.Config(),
        env or {},
        lambda _cwd: git,
        lambda _session, _transcript: stats,
    )


def _component(name: str, data: dict[str, Any] | None = None, **kwargs: Any) -> Any:
    """
    Run one registered component against a stubbed Context
    """
    return statusline.COMPONENTS[name](_ctx(data, **kwargs))


def _stats(prompts: int = 0, tool_uses: int = 0, pending: dict[str, str] | None = None) -> Any:
    """
    Build TranscriptStats with the given counts
    """
    return statusline.TranscriptStats(prompts=prompts, tool_uses=tool_uses, pending=pending or {})


class TestComponents:
    """
    Tests for the registered components
    """
    def test_registry_matches_defaults(self) -> None:
        """
        Register exactly the default component names
        """
        assert set(statusline.COMPONENTS) == set(statusline.DEFAULT_COMPONENTS)

    def test_directory_short(self) -> None:
        """
        Show the basename of the working directory
        """
        assert _component('directory', SAMPLE) == statusline.Segment('proj')

    def test_directory_falls_back_to_cwd(self) -> None:
        """
        Use the top-level cwd when workspace is absent
        """
        assert _component('directory', {'cwd': '/a/b'}) == statusline.Segment('b')

    @pytest.mark.parametrize(
        ('path', 'expected'),
        [
            ('/Users/me/code/proj', '~/code/proj'),
            ('/Users/me',           '~'),
            ('/Users/meow/x',       '/Users/meow/x'),
            ('/opt/x',              '/opt/x'),
        ],
    )
    def test_directory_full_folds_home(self, path: str, expected: str) -> None:
        """
        Replace HOME with ~ only for HOME itself and its descendants
        """
        config  = statusline.Config(directory_style='full')
        segment = _component('directory', {'cwd': path}, config=config, env={'HOME': '/Users/me'})
        assert segment == statusline.Segment(expected)

    def test_git_clean(self) -> None:
        """
        Show the bare branch for a clean checkout
        """
        assert _component('git', SAMPLE, git=statusline.GitStatus('main')) == statusline.Segment('main')

    def test_git_dirty_ahead_behind_with_pr(self) -> None:
        """
        Mark dirtiness, ahead/behind counts, and the PR number
        """
        status   = statusline.GitStatus('feat', dirty=True, ahead=2, behind=1)
        expected = f'feat* {statusline.ARROW_UP}2 {statusline.ARROW_DOWN}1 #12'
        assert _component('git', {**SAMPLE, 'pr': {'number': 12}}, git=status) == statusline.Segment(expected)

    def test_git_pr_number_can_be_disabled(self) -> None:
        """
        Omit the PR number when prUrlFormat is none
        """
        config  = statusline.Config(pr_url_format='none')
        segment = _component('git', {'pr': {'number': 12}}, config=config, git=statusline.GitStatus('main'))
        assert segment == statusline.Segment('main')

    def test_git_outside_repository(self) -> None:
        """
        Render nothing outside a repository
        """
        assert _component('git', SAMPLE, git=None) is None

    def test_active_tool(self) -> None:
        """
        Show the unresolved tool call, and nothing when there is none
        """
        assert _component('active-tool', stats=_stats(pending={'t1': 'Bash'})) == statusline.Segment('Bash')
        assert _component('active-tool', stats=_stats()) is None
        assert _component('active-tool', stats=None)     is None

    @pytest.mark.parametrize(
        ('model', 'style', 'expected'),
        [
            ({'display_name': 'Sonnet 5.5', 'id': 'x'}, 'full',  'Sonnet 5.5'),
            ({'display_name': 'Sonnet 5.5', 'id': 'x'}, 'short', 'Sonnet'),
            ({'id': 'claude-x'},                        'full',  'claude-x'),
        ],
    )
    def test_model(self, model: dict[str, str], style: str, expected: str) -> None:
        """
        Show the display name (or id), optionally shortened to its first word
        """
        segment = _component('model', {'model': model}, config=statusline.Config(model_style=style))
        assert segment == statusline.Segment(expected)

    def test_model_absent(self) -> None:
        """
        Render nothing without model data
        """
        assert _component('model', {}) is None

    def test_effort(self) -> None:
        """
        Show the effort level when present
        """
        assert _component('effort', SAMPLE) == statusline.Segment('high')
        assert _component('effort', {})     is None

    @pytest.mark.parametrize(
        ('percent', 'expected_severity'),
        [
            (42, None),
            (75, 'warning'),
            (95, 'critical'),
        ],
    )
    def test_context_line(self, percent: int, expected_severity: str | None) -> None:
        """
        Show a usage bar and percentage, escalating severity with usage
        """
        segment  = _component('context', {'context_window': {'used_percentage': percent}})
        expected = f'{statusline.context_bar(percent)} {percent}%'
        assert segment == statusline.Segment(expected, expected_severity)

    def test_context_percent_style(self) -> None:
        """
        Show only the percentage in the percent style
        """
        config = statusline.Config(context_style='percent')
        assert _component('context', SAMPLE, config=config) == statusline.Segment('42%')

    @pytest.mark.parametrize('value', [None, True, 'high'])
    def test_context_unusable(self, value: object) -> None:
        """
        Render nothing for a null, boolean, or non-numeric percentage
        """
        assert _component('context', {'context_window': {'used_percentage': value}}) is None

    def test_duration(self) -> None:
        """
        Show the formatted session duration
        """
        assert _component('duration', SAMPLE) == statusline.Segment('12m')
        assert _component('duration', {})     is None

    def test_messages_and_tools(self) -> None:
        """
        Show the prompt and tool-call counts from the transcript
        """
        stats = _stats(prompts=3, tool_uses=7)
        assert _component('messages', stats=stats) == statusline.Segment('3')
        assert _component('tools',    stats=stats) == statusline.Segment('7')
        assert _component('messages', stats=None)  is None
        assert _component('tools',    stats=None)  is None

    def test_quota_rate_limits(self) -> None:
        """
        Show both rate-limit windows with the worst one's severity
        """
        data     = {'rate_limits': {'five_hour': {'used_percentage': 92.4}, 'seven_day': {'used_percentage': 41.2}}}
        expected = statusline.Segment(f'5h 92% {statusline.DOT} 7d 41%', 'critical')
        assert _component('quota', data) == expected

    def test_quota_single_window(self) -> None:
        """
        Show only the windows that are present
        """
        data = {'rate_limits': {'seven_day': {'used_percentage': 41.2}}}
        assert _component('quota', data) == statusline.Segment('7d 41%')

    def test_quota_falls_back_to_cost(self) -> None:
        """
        Show the session cost without rate limits, and nothing when it is zero
        """
        assert _component('quota', {'cost': {'total_cost_usd': 1.234}}) == statusline.Segment('$1.23')
        assert _component('quota', {'cost': {'total_cost_usd': 0}})     is None

    def test_agent(self) -> None:
        """
        Show the agent name when the session runs as an agent
        """
        assert _component('agent', {'agent': {'name': 'reviewer'}}) == statusline.Segment('reviewer')
        assert _component('agent', {})                               is None

    def test_api_base(self) -> None:
        """
        Show ANTHROPIC_BASE_URL only when it is set
        """
        env = {'ANTHROPIC_BASE_URL': 'http://localhost:8080'}
        assert _component('api-base', env=env) == statusline.Segment('http://localhost:8080')
        assert _component('api-base')          is None


# ==============================================================================
# Render
# ==============================================================================

def _render(data: dict[str, Any], config: Any, **kwargs: Any) -> str:
    """
    Render with stubbed sources and an empty environment unless overridden
    """
    kwargs.setdefault('env', {})
    kwargs.setdefault('git_fn', lambda _cwd: None)
    kwargs.setdefault('stats_fn', lambda _session, _transcript: None)
    return statusline.render(data, config, **kwargs)


class TestRender:
    """
    Tests for render
    """
    def test_plain_row(self) -> None:
        """
        Join plain segments with the separator
        """
        config = statusline.Config(icon_set='text', components=('directory', 'model', 'effort'))
        sep    = statusline.SEPARATOR
        assert _render(SAMPLE, config, color=False) == f'proj {sep} Sonnet 5.5 {sep} high'

    def test_unknown_and_empty_components_are_skipped(self) -> None:
        """
        Skip unknown names and components with nothing to show
        """
        config = statusline.Config(icon_set='text', components=('mystery', 'directory', 'agent'))
        assert _render(SAMPLE, config, color=False) == 'proj'

    def test_faulty_component_is_isolated(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Keep rendering the other segments when one component raises
        """
        def boom(_ctx: Any) -> None:
            raise RuntimeError('boom')

        monkeypatch.setitem(statusline.COMPONENTS, 'model', boom)
        config = statusline.Config(icon_set='text', components=('directory', 'model'))
        assert _render(SAMPLE, config, color=False) == 'proj'

    def test_wraps_to_columns(self) -> None:
        """
        Wrap onto a new row when the terminal is too narrow
        """
        config = statusline.Config(icon_set='text', components=('directory', 'model'))
        assert _render(SAMPLE, config, color=False, columns=6) == 'proj\nSonnet 5.5'

    def test_colored_pills(self) -> None:
        """
        Draw each segment as a pill and join pills with a two-space gap
        """
        icons       = statusline.ICON_SETS['nerd-font']
        left, right = statusline.PILL_LEFT, statusline.PILL_RIGHT
        out         = _render(SAMPLE, statusline.Config(components=('directory', 'model')), color=True)
        assert statusline.strip_ansi(out) == (
            f'{left} {icons["directory"]} {right} proj{statusline.PILL_GAP}{left} {icons["model"]} {right} Sonnet 5.5'
        )

    def test_git_is_queried_only_when_needed(self) -> None:
        """
        Skip the git subprocess when no component needs it
        """
        calls: list[str] = []

        def git_fn(cwd: str) -> None:
            calls.append(cwd)

        _render(SAMPLE, statusline.Config(components=('directory', 'model')), git_fn=git_fn)
        assert calls == []


# ==============================================================================
# Entry point
# ==============================================================================

class TestEntryPoint:
    """
    Tests for main and its helpers
    """
    @pytest.mark.parametrize(
        ('env', 'expected'),
        [
            ({'COLUMNS': '120'},  120),
            ({},                  0),
            ({'COLUMNS': 'wide'}, 0),
        ],
    )
    def test_terminal_columns(self, env: dict[str, str], expected: int) -> None:
        """
        Read COLUMNS, treating missing or invalid values as unlimited
        """
        assert statusline.terminal_columns(env) == expected

    @pytest.mark.parametrize(
        ('raw', 'expected'),
        [
            (b'{"a": 1}', {'a': 1}),
            (b'[1]',      {}),
            (b'\xff',     {}),
            (b'',         {}),
        ],
    )
    def test_read_session(self, raw: bytes, expected: dict[str, Any]) -> None:
        """
        Parse a JSON object and treat anything else as empty
        """
        assert statusline.read_session(io.BytesIO(raw)) == expected

    def test_fallback_line(self) -> None:
        """
        Show the directory and model in the fallback line
        """
        assert statusline.fallback_line(SAMPLE) == f'proj {statusline.SEPARATOR} Sonnet 5.5'

    def test_main_falls_back_when_render_fails(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys:      pytest.CaptureFixture[str],
    ) -> None:
        """
        Print the fallback line and exit 0 when rendering raises
        """
        def boom(*_args: Any, **_kwargs: Any) -> str:
            raise RuntimeError('boom')

        monkeypatch.setattr(sys, 'stdin', io.TextIOWrapper(io.BytesIO(json.dumps(SAMPLE).encode())))
        monkeypatch.setattr(statusline, 'render', boom)
        assert statusline.main() == 0
        assert capsys.readouterr().out == f'proj {statusline.SEPARATOR} Sonnet 5.5\n'

    def _run(self, tmp_path: Path, stdin: str, **env: str) -> subprocess.CompletedProcess[str]:
        """
        Run the script as Claude Code would, with an isolated settings directory and TMPDIR
        """
        config = {'iconSet': 'text', 'components': ['directory', 'model', 'context', 'effort']}
        (tmp_path / 'settings.json').write_text(json.dumps({'statusLineConfig': config}), encoding='utf-8')
        return subprocess.run(
            [sys.executable, str(SCRIPT_PATH)],
            input=stdin,
            capture_output=True,
            text=True,
            check=False,
            env={
                **os.environ,
                'CLAUDE_CONFIG_DIR': str(tmp_path),
                'TMPDIR':            str(tmp_path),
                'NO_COLOR':          '1',
                'COLUMNS':           '200',
                **env,
            },
        )

    def test_end_to_end(self, tmp_path: Path) -> None:
        """
        Render the configured components from stdin JSON
        """
        result = self._run(tmp_path, json.dumps(SAMPLE))
        sep    = statusline.SEPARATOR
        assert result.returncode == 0
        assert result.stdout     == f'proj {sep} Sonnet 5.5 {sep} {statusline.context_bar(42)} 42% {sep} high\n'

    def test_garbage_stdin(self, tmp_path: Path) -> None:
        """
        Exit 0 and fall back to $PWD for the directory on unparsable input
        """
        result = self._run(tmp_path, 'not json', PWD='/x/y')
        assert result.returncode == 0
        assert result.stdout     == 'y\n'
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `scripts/hooks/uv-public.sh run pytest tests/unit/test_statusline.py -q`
Expected: the new tests fail with `AttributeError` (no `Context`, `COMPONENTS`, `render`, ...); earlier tests pass.

- [ ] **Step 3: Write the implementation**

In `statusline.py`, replace the import block with:

```python
import contextlib
import functools
import json
import os
import re
import subprocess
import sys
import tempfile
import unicodedata
from collections.abc import Callable
from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from typing import BinaryIO
from typing import Optional

if TYPE_CHECKING:
    from collections.abc import Mapping
```

Append to the end of the file:

```python
# ==============================================================================
# Components
# ==============================================================================

def dig(data: Any, *keys: str) -> Any:
    """
    Walk nested dicts without raising

    :param data: parsed JSON (any shape)
    :param keys: keys to follow in order
    :return: the value found, or None when any step is missing or not a dict
    """
    for key in keys:
        if not isinstance(data, dict):
            return None
        data = data.get(key)
    return data


def _is_number(value: object) -> bool:
    """
    Check for an int or float that is not a bool

    :param value: value to check
    :return: True for real numbers
    """
    return isinstance(value, (int, float)) and not isinstance(value, bool)


@dataclass
class Context:
    """
    Everything a component may read: the session JSON, the config, the environment, and lazily computed git and
    transcript state (each computed at most once, and only when a component asks)
    """
    data:     dict[str, Any]
    config:   Config
    env:      Mapping[str, str]
    git_fn:   Callable[[str], GitStatus | None]
    stats_fn: Callable[[str, str], TranscriptStats | None]

    @property
    def cwd(self) -> str:
        """
        Working directory of the session, falling back to ``$PWD``
        """
        current = dig(self.data, 'workspace', 'current_dir') or self.data.get('cwd') or self.env.get('PWD') or '.'
        return str(current)

    @functools.cached_property
    def git(self) -> GitStatus | None:
        """
        Git status of the working directory
        """
        return self.git_fn(self.cwd)

    @functools.cached_property
    def stats(self) -> TranscriptStats | None:
        """
        Transcript stats of the session
        """
        return self.stats_fn(str(self.data.get('session_id') or ''), str(self.data.get('transcript_path') or ''))


ComponentFn = Callable[[Context], Optional[Segment]]

COMPONENTS: dict[str, ComponentFn] = {}


def component(name: str) -> Callable[[ComponentFn], ComponentFn]:
    """
    Register the decorated function as the renderer of component ``name``

    :param name: component name used in ``statusLineConfig.components``
    :return: the registering decorator
    """
    def register(fn: ComponentFn) -> ComponentFn:
        COMPONENTS[name] = fn
        return fn

    return register


@component('directory')
def _directory(ctx: Context) -> Segment | None:
    """
    Working directory: basename (``short``) or ``~``-folded path (``full``)
    """
    path = ctx.cwd
    if ctx.config.directory_style == 'short':
        return Segment(Path(path).name or path)

    home = ctx.env.get('HOME', '')
    if home and ((path == home) or path.startswith(home + os.sep)):
        path = '~' + path[len(home):]
    return Segment(path)


@component('git')
def _git(ctx: Context) -> Segment | None:
    """
    Branch, ``*`` when dirty, ahead/behind arrows, and the open PR number
    """
    status = ctx.git
    if status is None:
        return None

    text = status.branch + ('*' if status.dirty else '')
    if status.ahead:
        text += f' {ARROW_UP}{status.ahead}'
    if status.behind:
        text += f' {ARROW_DOWN}{status.behind}'

    number = dig(ctx.data, 'pr', 'number')
    if (ctx.config.pr_url_format == 'number') and _is_number(number):
        text += f' #{number}'
    return Segment(text)


@component('active-tool')
def _active_tool(ctx: Context) -> Segment | None:
    """
    Name of the tool call in progress
    """
    stats = ctx.stats
    return Segment(stats.active_tool) if (stats and stats.active_tool) else None


@component('model')
def _model(ctx: Context) -> Segment | None:
    """
    Model display name (``full``) or its first word (``short``)
    """
    name = dig(ctx.data, 'model', 'display_name') or dig(ctx.data, 'model', 'id')
    if (not isinstance(name, str)) or (not name):
        return None
    return Segment(name.split()[0] if ctx.config.model_style == 'short' else name)


@component('effort')
def _effort(ctx: Context) -> Segment | None:
    """
    Reasoning effort level
    """
    level = dig(ctx.data, 'effort', 'level')
    return Segment(level) if (isinstance(level, str) and level) else None


@component('context')
def _context(ctx: Context) -> Segment | None:
    """
    Context-window usage: a bar plus percentage (``line``) or the percentage alone
    """
    percent = dig(ctx.data, 'context_window', 'used_percentage')
    if not _is_number(percent):
        return None

    label = f'{round(percent)}%'
    text  = f'{context_bar(percent)} {label}' if ctx.config.context_style == 'line' else label
    return Segment(text, severity(percent))


@component('duration')
def _duration(ctx: Context) -> Segment | None:
    """
    Session wall-clock duration
    """
    ms = dig(ctx.data, 'cost', 'total_duration_ms')
    return Segment(format_duration(ms)) if _is_number(ms) else None


@component('messages')
def _messages(ctx: Context) -> Segment | None:
    """
    Number of user prompts in the session
    """
    stats = ctx.stats
    return Segment(str(stats.prompts)) if stats else None


@component('tools')
def _tools(ctx: Context) -> Segment | None:
    """
    Number of tool calls in the session
    """
    stats = ctx.stats
    return Segment(str(stats.tool_uses)) if stats else None


@component('quota')
def _quota(ctx: Context) -> Segment | None:
    """
    Rate-limit window usage when reported, otherwise the session cost
    """
    windows  = (('5h', 'five_hour'), ('7d', 'seven_day'))
    readings = [(label, dig(ctx.data, 'rate_limits', key, 'used_percentage')) for label, key in windows]
    present  = [(label, percent) for label, percent in readings if _is_number(percent)]
    if present:
        text = f' {DOT} '.join(f'{label} {round(percent)}%' for label, percent in present)
        return Segment(text, severity(max(percent for _, percent in present)))

    cost = dig(ctx.data, 'cost', 'total_cost_usd')
    if _is_number(cost) and (cost > 0):
        return Segment(f'${cost:.2f}')
    return None


@component('agent')
def _agent(ctx: Context) -> Segment | None:
    """
    Agent name when the session runs as an agent
    """
    name = dig(ctx.data, 'agent', 'name')
    return Segment(name) if (isinstance(name, str) and name) else None


@component('api-base')
def _api_base(ctx: Context) -> Segment | None:
    """
    Custom API endpoint (``ANTHROPIC_BASE_URL``), only when one is set
    """
    url = ctx.env.get('ANTHROPIC_BASE_URL', '')
    return Segment(url) if url else None

# ==============================================================================
# Render
# ==============================================================================

def render(
    data:     dict[str, Any],
    config:   Config,
    *,
    columns:  int                                          = 0,
    color:    bool                                         = True,
    env:      Mapping[str, str] | None                     = None,
    git_fn:   Callable[[str], GitStatus | None]            = git_status,
    stats_fn: Callable[[str, str], TranscriptStats | None] = load_stats,
) -> str:
    """
    Render the statusline for one session snapshot

    A component that raises is skipped, so one bad field never blanks the whole line.

    :param data: session JSON from stdin
    :param config: resolved configuration
    :param columns: terminal width (0 for unlimited)
    :param color: whether to emit color escapes
    :param env: environment to read (default: ``os.environ``)
    :param git_fn: git status provider
    :param stats_fn: transcript stats provider
    :return: the statusline rows joined by newlines
    """
    ctx = Context(data, config, os.environ if env is None else env, git_fn, stats_fn)

    parts: list[str] = []
    for name in config.components:
        renderer = COMPONENTS.get(name)
        if renderer is None:
            continue
        try:
            segment = renderer(ctx)
        except Exception:  # noqa: S112 - a faulty component is dropped, not fatal
            continue
        if (segment is not None) and segment.text:
            parts.append(render_segment(name, segment, config, color))

    return '\n'.join(layout(parts, joiner(config, color), columns, config.truncation))

# ==============================================================================
# Entry point
# ==============================================================================

def read_session(stream: BinaryIO) -> dict[str, Any]:
    """
    Parse the session JSON

    :param stream: binary stdin
    :return: the session object, or an empty dict for anything unparsable
    """
    try:
        data = json.loads(stream.read())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def terminal_columns(env: Mapping[str, str]) -> int:
    """
    Read the terminal width Claude Code provides

    :param env: environment to read
    :return: ``COLUMNS`` as an int, or 0 (unlimited) when missing or invalid
    """
    try:
        return int(env.get('COLUMNS', ''))
    except ValueError:
        return 0


def fallback_line(data: dict[str, Any]) -> str:
    """
    Build the minimal line printed when rendering fails

    :param data: session JSON (possibly empty)
    :return: ``<directory> <separator> <model>``
    """
    cwd   = dig(data, 'workspace', 'current_dir') or data.get('cwd') or os.environ.get('PWD') or '.'
    model = dig(data, 'model', 'display_name') or 'Claude'
    return f'{Path(str(cwd)).name} {SEPARATOR} {model}'


def main() -> int:
    """
    Read the session JSON from stdin and print the statusline

    Always exits 0: Claude Code blanks the statusline on a non-zero exit, so any failure prints the fallback line.

    :return: the exit code
    """
    data = read_session(sys.stdin.buffer)
    try:
        output = render(
            data,
            load_config(settings_path()),
            columns=terminal_columns(os.environ),
            color=not os.environ.get('NO_COLOR'),
        )
    except Exception:
        output = fallback_line(data)

    # Write UTF-8 bytes directly so a non-UTF-8 locale cannot turn a glyph into an encoding error
    sys.stdout.buffer.write(f'{output}\n'.encode())
    sys.stdout.buffer.flush()
    return 0


if __name__ == '__main__':
    sys.exit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `scripts/hooks/uv-public.sh run pytest tests/unit/test_statusline.py -q`
Expected: all tests pass.

- [ ] **Step 5: Lint**

Run: `scripts/hooks/uv-public.sh run ruff check --fix stow/claude/.claude/statusline/statusline.py tests/unit/test_statusline.py`
then `scripts/hooks/uv-public.sh run mypy stow/claude/.claude/statusline/statusline.py tests/unit/test_statusline.py`
Expected: no errors.

- [ ] **Step 6: Check the real output and its speed**

Write `.tmp/statusline-sample.json` with the Write tool:

```json
{
  "session_id": "manual-check",
  "transcript_path": "",
  "cwd": "/Users/connormason/dotfiles-personal",
  "model": {"id": "claude-sonnet-5-5", "display_name": "Sonnet 5.5"},
  "workspace": {"current_dir": "/Users/connormason/dotfiles-personal", "project_dir": "/Users/connormason/dotfiles-personal"},
  "cost": {"total_cost_usd": 1.23, "total_duration_ms": 754000},
  "context_window": {"used_percentage": 42, "context_window_size": 200000},
  "effort": {"level": "high"},
  "rate_limits": {"five_hour": {"used_percentage": 23.5}, "seven_day": {"used_percentage": 41.2}}
}
```

Run: `uv run --quiet --script stow/claude/.claude/statusline/statusline.py < .tmp/statusline-sample.json`
Expected: one row of neon pills (directory `dotfiles-personal`, git branch, model, effort, the context bar with `42%`,
`12m`, and quota `5h 24% · 7d 41%`). This reads the real `~/.claude/settings.json`, whose `statusLineConfig` matches
the repo's. Show the output to the user and compare it against the work statusline.

Run `/usr/bin/time -p uv run --quiet --script stow/claude/.claude/statusline/statusline.py < .tmp/statusline-sample.json`
three times. Expected: `real` under 0.15 s once warm.

- [ ] **Step 7: Commit**

```bash
git add stow/claude/.claude/statusline/statusline.py tests/unit/test_statusline.py
git commit -m "feat(claude): render statusline components from session JSON"
```

---

### Task 4: Wire the statusline into rendered settings

**Files:**

- Modify: `render/claude.json:229-235`
- Modify: `tests/unit/test_statusline.py` (append one section)
- Modify: `stow/README.md:20`

**Interfaces:**

- Consumes: `statusline.COMPONENTS`, `SCRIPT_PATH`, `_load_module`; and from `scripts/dotfiles/render.py`,
  `compose(fragments: Sequence[Path]) -> tuple[dict[str, object], list[str]]`.

- [ ] **Step 1: Write the failing guardrail tests**

Append to `tests/unit/test_statusline.py`:

```python
# ==============================================================================
# Rendered settings
# ==============================================================================

render_module = _load_module('render', REPO_ROOT / 'scripts' / 'dotfiles' / 'render.py')


class TestRenderedSettings:
    """
    Guardrails tying the rendered Claude Code settings (base plus personal-mac overlay) to the statusline script
    """
    @pytest.fixture(scope='class')
    def settings(self) -> dict[str, Any]:
        """
        Compose the real repository's base and personal-mac claude fragments
        """
        managed, _unmanaged = render_module.compose([
            REPO_ROOT / 'render' / 'claude.json',
            REPO_ROOT / 'profiles' / 'personal-mac' / 'render' / 'claude.json',
        ])
        return managed

    def test_status_line_runs_the_stowed_script(self, settings: dict[str, Any]) -> None:
        """
        Point statusLine at the stowed script through uv
        """
        status_line = settings['statusLine']
        assert status_line['type']    == 'command'
        assert status_line['command'] == 'uv run --quiet --script "$HOME/.claude/statusline/statusline.py"'
        assert SCRIPT_PATH.is_file()
        assert os.access(SCRIPT_PATH, os.X_OK)

    def test_configured_components_exist(self, settings: dict[str, Any]) -> None:
        """
        List only components the renderer implements
        """
        components = settings['statusLineConfig']['components']
        assert set(components) <= set(statusline.COMPONENTS)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `scripts/hooks/uv-public.sh run pytest tests/unit/test_statusline.py -q -k TestRenderedSettings`
Expected: `test_status_line_runs_the_stowed_script` fails with `KeyError: 'statusLine'`;
`test_configured_components_exist` fails because `todos` is not a component.

- [ ] **Step 3: Update `render/claude.json`**

Use the Edit tool. Replace:

```json
  "statusLineConfig": {
    "colorTheme": "neon",
    "components": [
      "directory",
      "git",
      "active-tool",
      "todos",
      "model",
```

with:

```json
  "statusLine": {
    "command": "uv run --quiet --script \"$HOME/.claude/statusline/statusline.py\"",
    "padding": 0,
    "type": "command"
  },
  "statusLineConfig": {
    "colorTheme": "neon",
    "components": [
      "directory",
      "git",
      "active-tool",
      "model",
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `scripts/hooks/uv-public.sh run pytest tests/unit/test_statusline.py tests/unit/test_render.py -q`
Expected: all pass.

- [ ] **Step 5: Update the stow README row**

In `stow/README.md`, the `claude` row's middle cell currently ends `skills, and plugin config`. Change that ending to
`skills, plugin config, and the statusline renderer`. The mdformat hook re-pads the table on commit.

- [ ] **Step 6: Commit**

```bash
git add render/claude.json tests/unit/test_statusline.py stow/README.md
git commit -m "feat(claude): render statusLine to run the stowed statusline"
```

If the mdformat hook rewrites `stow/README.md`, `git add stow/README.md` and commit again.

---

### Task 5: claude-devtools config

**Files:**

- Create: `stow/claude/.claude/claude-devtools-config.json`
- Modify: `stow/README.md:20`

- [ ] **Step 1: Copy the config**

Run: `cp /Users/connormason/dotfiles/stow/claude/.claude/claude-devtools-config.json stow/claude/.claude/claude-devtools-config.json`

- [ ] **Step 2: Validate and leak-scan**

Run: `jq -e 'has("general") and has("notifications")' stow/claude/.claude/claude-devtools-config.json`
Expected: `true`.

Run: `scripts/hooks/uv-public.sh run scripts/hooks/check-leaks.py stow/claude/.claude/claude-devtools-config.json`
Expected: exit 0, no findings. Also read the file and confirm that `notifications.ignoredRepositories` and
`ssh.profiles` are empty and `ssh.lastConnection` is null (no hostnames or repository paths).

- [ ] **Step 3: Update the stow README row**

In `stow/README.md`, change the `claude` row's ending (as left by Task 4) from
`plugin config, and the statusline renderer` to `plugin config, the statusline renderer, and the claude-devtools
config`.

- [ ] **Step 4: Commit**

```bash
git add stow/claude/.claude/claude-devtools-config.json stow/README.md
git commit -m "feat(claude): stow the claude-devtools config"
```

The app rewrites this file in place through the stow symlink, so later app edits appear as diffs in this repo (as they
already do at work). On the personal Mac, `95-dotfiles` (`--backup-conflicts`) moves any pre-existing real file to
`~/.dotfiles-backup/<timestamp>/` before linking. Note both in the PR description.

---

### Task 6: Port the three skills

**Files:**

- Create: `stow/claude/.claude/skills/claude-session-logs/` (`SKILL.md`, `README.md`, `scripts/extract.py`)
- Create: `stow/claude/.claude/skills/gh-pr-comments/` (`SKILL.md`, `README.md`, `scripts/gh_comments.sh`)
- Create: `stow/claude/.claude/skills/shell-scripting/SKILL.md`

- [ ] **Step 1: Copy the skills**

Run: `cp -R /Users/connormason/dotfiles/stow/claude/.claude/skills/claude-session-logs /Users/connormason/dotfiles/stow/claude/.claude/skills/gh-pr-comments /Users/connormason/dotfiles/stow/claude/.claude/skills/shell-scripting stow/claude/.claude/skills/`

Run: `git status --short stow/claude/.claude/skills`
Expected: exactly the seven files listed above (no `__pycache__`, no `.backups`).

- [ ] **Step 2: Make claude-session-logs run through uv**

In `stow/claude/.claude/skills/claude-session-logs/SKILL.md` (Edit tool):

- Line 7: replace `allowed-tools: Bash(python3 */scripts/extract.py *)` with
  `allowed-tools: Bash(uv run --script */scripts/extract.py *)`.
- Replace every `python3 {baseDir}/scripts/extract.py` with `uv run --script {baseDir}/scripts/extract.py`
  (`replace_all`; there are 30 occurrences).
- Line 58: the example full path contains a colleague's username. Replace the path inside the backticks with
  `/Users/username/.claude/projects/-Users-username-Developer-myapp/abc123.jsonl`.

In `stow/claude/.claude/skills/claude-session-logs/README.md`, line 24: replace
`- Python 3.6 or later (included with macOS)` with
`- [uv](https://docs.astral.sh/uv/), which runs the stdlib-only script with any installed Python 3.9+`.

Verify: `grep -rn 'python3 ' stow/claude/.claude/skills/claude-session-logs` prints nothing. (The script's
`#!/usr/bin/env python3` shebang has no trailing space and does not match.) Then read SKILL.md line 58 and confirm no
real username remains.

- [ ] **Step 3: Genericize gh-pr-comments**

In `stow/claude/.claude/skills/gh-pr-comments/README.md`, replace the internal GitHub Enterprise hostname on lines 40,
43, and 102 with `github.example.com` (`replace_all`).

In `stow/claude/.claude/skills/gh-pr-comments/scripts/gh_comments.sh`, change the shebang `#!/bin/bash` to
`#!/usr/bin/env bash`, matching the other scripts in this repo.

- [ ] **Step 4: Leak-scan and lint**

Run: `scripts/hooks/uv-public.sh run scripts/hooks/check-leaks.py stow/claude/.claude/skills/claude-session-logs/SKILL.md stow/claude/.claude/skills/claude-session-logs/README.md stow/claude/.claude/skills/claude-session-logs/scripts/extract.py stow/claude/.claude/skills/gh-pr-comments/SKILL.md stow/claude/.claude/skills/gh-pr-comments/README.md stow/claude/.claude/skills/gh-pr-comments/scripts/gh_comments.sh stow/claude/.claude/skills/shell-scripting/SKILL.md`
Expected: exit 0, no findings.

Run: `scripts/hooks/uv-public.sh run ruff check stow/claude/.claude/skills`
then `scripts/hooks/uv-public.sh run mypy stow/claude/.claude/skills/claude-session-logs/scripts/extract.py`
then `scripts/hooks/uv-public.sh run shellcheck stow/claude/.claude/skills/gh-pr-comments/scripts/gh_comments.sh`
Expected: all clean (a planning-time probe of the unmodified copies passed all three).

- [ ] **Step 5: Smoke-test the copied scripts**

Run: `uv run --script stow/claude/.claude/skills/claude-session-logs/scripts/extract.py projects`
Expected: a list of Claude Code project directories, exit 0.

Run: `bash -n stow/claude/.claude/skills/gh-pr-comments/scripts/gh_comments.sh`
Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
git add stow/claude/.claude/skills/claude-session-logs stow/claude/.claude/skills/gh-pr-comments stow/claude/.claude/skills/shell-scripting
git commit -m "feat(claude): add session-log, PR-comment, and shell-scripting skills"
```

If the shfmt or mdformat hooks rewrite files, `git add` the same paths and commit again.

---

### Task 7: Enable the public plugins

**Files:**

- Modify: `profiles/personal-mac/render/claude.json:4-6`
- Modify: `profiles/personal-mac/README.md` (the `render/claude.json` table row)
- Modify: `tests/unit/test_statusline.py` (one test in `TestRenderedSettings`)

All plugin names were verified during planning against the official marketplace manifest
(`anthropics/claude-plugins-official`, `.claude-plugin/marketplace.json`).

- [ ] **Step 1: Write the failing test**

Add to `TestRenderedSettings` in `tests/unit/test_statusline.py`:

```python
    def test_public_plugins_are_enabled(self, settings: dict[str, Any]) -> None:
        """
        Enable the official-marketplace plugins carried over from the work setup
        """
        expected = {
            f'{name}@claude-plugins-official'
            for name in (
                'claude-md-management',
                'code-simplifier',
                'commit-commands',
                'feature-dev',
                'frontend-design',
                'pr-review-toolkit',
                'pyright-lsp',
                'skill-creator',
                'superpowers',
            )
        }
        enabled = {name for name, on in settings['enabledPlugins'].items() if on}
        assert expected <= enabled
```

Run: `scripts/hooks/uv-public.sh run pytest tests/unit/test_statusline.py -q -k test_public_plugins_are_enabled`
Expected: FAIL (only `pyright-lsp` is enabled).

- [ ] **Step 2: Enable the plugins**

In `profiles/personal-mac/render/claude.json` (Edit tool), replace:

```json
  "enabledPlugins": {
    "pyright-lsp@claude-plugins-official": true
  },
```

with:

```json
  "enabledPlugins": {
    "claude-md-management@claude-plugins-official": true,
    "code-simplifier@claude-plugins-official": true,
    "commit-commands@claude-plugins-official": true,
    "feature-dev@claude-plugins-official": true,
    "frontend-design@claude-plugins-official": true,
    "pr-review-toolkit@claude-plugins-official": true,
    "pyright-lsp@claude-plugins-official": true,
    "skill-creator@claude-plugins-official": true,
    "superpowers@claude-plugins-official": true
  },
```

- [ ] **Step 3: Run the tests to verify they pass**

Run: `scripts/hooks/uv-public.sh run pytest tests/unit/test_statusline.py tests/unit/test_profiles.py -q`
Expected: all pass.

- [ ] **Step 4: Update the profile README**

In `profiles/personal-mac/README.md`, the `render/claude.json` row's purpose cell currently reads
``Claude Code settings merged after the base fragment: pins `model`, adds the iTerm2 `cc-status` hooks, ...``. Change
``pins `model`, adds`` to ``pins `model`, enables the official-marketplace plugins, adds``; leave the rest of the cell
unchanged.

- [ ] **Step 5: Commit**

```bash
git add profiles/personal-mac/render/claude.json profiles/personal-mac/README.md tests/unit/test_statusline.py
git commit -m "feat(personal-mac): enable the public Claude Code plugins"
```

Enabling a plugin in settings does not install it. After merge, on the personal Mac, run
`claude plugin install <name>@claude-plugins-official` for each new plugin (or accept the install prompt), then
`python3 run.py render --check claude`. Put this in the PR description.

---

### Task 8: Delta report, full verification, and PR

**Files:**

- Create: `docs/plans/2026-10/2026-10-31-claude-config-parity-delta.md`

- [ ] **Step 1: Write the delta report**

Create `docs/plans/2026-10/2026-10-31-claude-config-parity-delta.md` with the Write tool:

```markdown
# Claude Code Config Parity: Work vs. Personal Delta Report

**Date:** 2026-10-31
**Scope:** user-level Claude Code configuration only (`~/.claude` files and rendered `settings.json`).
**Companion docs:** [design](2026-10-31-claude-config-parity-design.md), [plan](2026-10-31-claude-config-parity-plan.md)

Employer-internal items are described generically; this repo is public.

## Ported in this change

| Item                        | Notes                                                                              |
| --------------------------- | ---------------------------------------------------------------------------------- |
| Statusline                  | Clean-room Python renderer reading the shared `statusLineConfig`; `todos` dropped  |
| claude-devtools config      | Stowed; the cask was already in the base Brewfile                                  |
| `claude-session-logs` skill | Invokes its script through `uv run --script` (base permissions deny `python3`)     |
| `gh-pr-comments` skill      | GitHub Enterprise example genericized; `env bash` shebang                          |
| `shell-scripting` skill     | Copied unchanged                                                                   |
| Public plugins              | Eight official-marketplace plugins added beside the existing `pyright-lsp`         |

## Already at parity (no change needed)

Generic permission allow/deny lists, `spinnerVerbs`, `statusLineConfig`, `attribution`, `autoMemoryEnabled`,
`effortLevel`, `theme`, `verbose`, `worktree.baseRef`, `skipWorkflowUsageWarning`, the shared hook set (personal uses
`$HOME` paths), rules, commands, the other skills, and the agents. The personal copies of `file-searcher`,
`ansible-devops-engineer`, `CLAUDE.md`, `dotclaude-cleanup`, and the hook scripts are the generalized versions; the
work copies differ only by employer wording, `#!/bin/bash` shebangs, and employer-specific cleanup sections.

## Deliberately not ported (employer-specific)

| Item                                                          | Reason                                                            |
| ------------------------------------------------------------- | ----------------------------------------------------------------- |
| API key helper, available-models list and its hash            | Tied to the employer's model gateway                              |
| Company announcements                                         | Employer content                                                  |
| Internal marketplaces, strict-marketplace list, their plugins | Internal sources, unreachable off the corporate network           |
| MCP servers and their permission entries                      | Internal services                                                 |
| Gateway, registry, and index env vars; shell-prefix wrapper   | Internal infrastructure                                           |
| Disabled CLI commands, autoupdater, and sandbox toggles       | Managed-install policy                                            |
| Message-display and tool-call-monitor hooks                   | Part of the managed install                                       |
| Permission-review hook                                        | Built entirely on the internal AI gateway and its auth            |
| Managed-install config tree and its skill                     | Managed-install internals                                         |
| VM-management skill and test-framework agent                  | Internal tools                                                    |
| Bug-tracker branch-workflow section of the global CLAUDE.md   | Internal tool                                                     |
| Extra CA bundle export in `32-claude.zsh`                     | Corporate TLS                                                     |
| Internal entries in `autoMode` and one spinner verb           | Employer references                                               |
| Internal npm statusline package and its bash fallback         | Unlicensed internal package (replaced by the clean-room renderer) |

## Skipped as redundant

- `modelSettings` effort `high` for Sonnet: equal to the global `effortLevel`.

## Personal-only (candidates to bring to work)

- `model-router` hooks and `CLAUDE_CODE_SUBAGENT_MODEL=sonnet`.
- The `dotclaude-cleanup.d/` drop-in extension mechanism and `#!/usr/bin/env bash` shebangs.
- The clean-room statusline (it runs anywhere `uv` is installed).
- iTerm2 `cc-status` hooks (personal-mac overlay).

## Follow-ups

- After merge, on the personal Mac: run `95-dotfiles` and `97-render`, install the new plugins, and confirm that
  `python3 run.py render --check claude` exits 0 and the statusline renders.
- Decide separately whether to rebuild a permission-review hook against a personal API key.
```

- [ ] **Step 2: Run the full test suite**

Run: `scripts/hooks/uv-public.sh run pytest -q`
Expected: all tests pass (including `test_docs_consistency.py` and `test_render.py`).

- [ ] **Step 3: Run every hook over the repo**

Run: `scripts/hooks/uv-public.sh run prek run --all-files`
Expected: all hooks pass or skip. If a formatter changes files, review the diff, commit it with
`git commit -am "style: apply formatter fixes"`, and re-run until clean.

- [ ] **Step 4: Confirm the lockfile is untouched**

Run: `git diff --exit-code main -- uv.lock requirements.txt`
Expected: exit 0.

- [ ] **Step 5: Commit the report**

```bash
git add docs/plans/2026-10/2026-10-31-claude-config-parity-delta.md
git commit -m "docs(plans): record the work vs. personal Claude Code delta"
```

- [ ] **Step 6: Open the PR (confirm with the user first)**

Ask the user before pushing. Then write `.tmp/pr-body.md` covering:

- what changed, linking the delta report;
- the post-merge steps on the personal Mac (Task 5's backup note, Task 7's plugin installs, `95-dotfiles` and
  `97-render`);
- the test evidence (pytest count, prek clean).

Then run:

```bash
git push -u origin worktree-claude-config-parity
gh pr create --base main --title "feat(claude): statusline, devtools config, skills, and plugins from the work setup" --body-file .tmp/pr-body.md
```

After the PR opens, remove the local worktree but keep the branch.

## Self-Review Notes

- **Spec coverage:** statusline (Tasks 1–4), devtools (Task 5), skills (Task 6), plugins (Task 7). Settings and
  shared-file reconciliation need no work (Deviations 3–4, recorded in the delta report). The not-ported list and the
  delta report are Task 8. Testing covers unit, end-to-end, rendered-settings guardrails, and a manual sample render.
  Delivery is Task 8.
- **Type consistency:** every component returns the Task 1 `Segment(text, severity)`. Task 2's
  `GitStatus`/`git_status` and `TranscriptStats`/`load_stats` match the Task 3 `Context` field types and `render`
  defaults. Task 1's `_load_module(name, path)` is reused for `render_module` in Task 4.
- **Placeholder scan:** none. Every code step carries complete code; every command has an expected result.
