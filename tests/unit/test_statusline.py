"""
Unit tests for stow/claude/.claude/statusline/statusline.py
"""
from __future__ import annotations

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

    def test_nul_in_cwd_returns_none(self) -> None:
        """
        Return None when the directory name cannot be passed to git
        """
        assert statusline.git_status('bad\x00dir') is None

    def test_undecodable_output_is_replaced(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """
        Replace undecodable bytes in git's output instead of raising
        """
        bin_dir  = tmp_path / 'bin'
        fake_git = bin_dir / 'git'
        bin_dir.mkdir()
        fake_git.write_text(
            "#!/bin/sh\nprintf '# branch.oid abc\\n# branch.head trunk\\n? file\\351.txt\\n'\n",
            encoding='utf-8',
        )
        fake_git.chmod(0o755)
        monkeypatch.setenv('PATH', str(bin_dir))
        assert statusline.git_status(str(tmp_path)) == statusline.GitStatus('trunk', dirty=True)


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

    def test_lone_surrogate_is_replaced(self, tmp_path: Path) -> None:
        """
        Exit 0 and replace a lone surrogate in the directory name instead of failing to encode it
        """
        result = self._run(tmp_path, '{"cwd": "/a/b\\ud800"}')
        assert result.returncode == 0
        assert result.stdout     == 'b?\n'

    def test_deeply_nested_stdin(self, tmp_path: Path) -> None:
        """
        Exit 0 and fall back to $PWD when the session JSON nests past the recursion limit
        """
        result = self._run(tmp_path, '[' * 200_000, PWD='/x/y')
        assert result.returncode == 0
        assert result.stdout     == 'y\n'
