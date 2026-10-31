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
