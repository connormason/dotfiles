"""
Tests for the format_module_section_headers.py pre-commit hook script.

Validates that module-level triple-quoted section headers are converted to boxed comment headers, that module
docstrings are preserved, that recursion respects skip directories, and that exit codes match the
``--exit-non-zero-on-fix`` contract used by pre-commit fixer hooks.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType


HOOK_PATH = str(Path(__file__).parents[4] / 'scripts' / 'hooks' / 'format_module_section_headers.py')

assert Path(HOOK_PATH).is_file(), (
    f'Script under test not found: {HOOK_PATH}\n'
    'Did the script move? Update HOOK_PATH in this test module.'
)


# ==================================================================================================
# Fixtures
# ==================================================================================================


def _load_module() -> ModuleType:
    """
    Load format_module_section_headers.py via importlib.

    :return: the loaded module
    """
    spec = importlib.util.spec_from_file_location('format_module_section_headers', HOOK_PATH)
    assert spec        is not None
    assert spec.loader is not None

    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def hook() -> ModuleType:
    """
    Return the loaded format_module_section_headers module.
    """
    return _load_module()


# ==================================================================================================
# Unit tests
# ==================================================================================================


class TestIsModuleDocstringPosition:
    """
    Tests for the is_module_docstring_position() helper.
    """
    def test_empty_lines_before(self, hook: ModuleType) -> None:
        """
        Test that an empty list of preceding lines is a valid module docstring position.
        """
        assert hook.is_module_docstring_position([]) is True

    def test_only_blanks_before(self, hook: ModuleType) -> None:
        """
        Test that only blank lines preceding allow a module docstring.
        """
        assert hook.is_module_docstring_position(['', '   ', '\t']) is True

    def test_comments_allowed_before(self, hook: ModuleType) -> None:
        """
        Test that shebang and comment lines preceding allow a module docstring.
        """
        lines = ['#!/usr/bin/env python3', '# coding: utf-8', '# /// script', '# ///', '']
        assert hook.is_module_docstring_position(lines) is True

    def test_code_before_disqualifies(self, hook: ModuleType) -> None:
        """
        Test that an import or other code line preceding rules out module docstring position.
        """
        assert hook.is_module_docstring_position(['import os', '']) is False

    def test_assignment_before_disqualifies(self, hook: ModuleType) -> None:
        """
        Test that any non-comment, non-blank line rules out module docstring position.
        """
        assert hook.is_module_docstring_position(['x = 1']) is False


class TestFormatFile:
    """
    Tests for the format_file() in-place conversion function.
    """
    def test_preserves_module_docstring(self, hook: ModuleType, tmp_path: Path) -> None:
        """
        Test that the leading module docstring is left untouched even if it is a standalone triple-quote pair.
        """
        src = '"""\nModule docstring\n"""\n\nx = 1\n'
        f = tmp_path / 'sample.py'
        f.write_text(src)

        replaced = hook.format_file(f)
        assert replaced      == 0
        assert f.read_text() == src

    def test_converts_section_header(self, hook: ModuleType, tmp_path: Path) -> None:
        """
        Test that a non-leading triple-quoted block is replaced with a boxed comment header.
        """
        src = '"""\nModule docstring\n"""\n\n\n"""\nSection name\n"""\n\n\nx = 1\n'
        f = tmp_path / 'sample.py'
        f.write_text(src)

        replaced = hook.format_file(f)
        assert replaced == 1

        result = f.read_text()
        assert hook.make_border()           in result
        assert '# Section name'             in result
        assert '"""\nSection name\n"""' not in result

    def test_converts_multiple_sections(self, hook: ModuleType, tmp_path: Path) -> None:
        """
        Test that all non-leading triple-quoted blocks are converted in a single pass.
        """
        src = (
            '"""\nModule\n"""\n\n\n'
            '"""\nFirst\n"""\n\n\n'
            'a = 1\n\n\n'
            '"""\nSecond\n"""\n\n\n'
            'b = 2\n'
        )
        f = tmp_path / 'sample.py'
        f.write_text(src)

        replaced = hook.format_file(f)
        assert replaced == 2

        result = f.read_text()
        assert '# First'  in result
        assert '# Second' in result
        assert result.count(hook.make_border()) == 4

    def test_preserves_blank_lines_inside_block(self, hook: ModuleType, tmp_path: Path) -> None:
        """
        Test that blank lines inside a section header become bare ``#`` lines (not ``# ``).
        """
        src = '"""\nModule\n"""\n\n\n"""\nFirst line\n\nThird line\n"""\n\n\nx = 1\n'
        f = tmp_path / 'sample.py'
        f.write_text(src)

        replaced = hook.format_file(f)
        assert replaced == 1

        result = f.read_text()
        assert '\n#\n'         in result
        assert '# First line'  in result
        assert '# Third line'  in result

    def test_leaves_indented_triple_quotes_alone(self, hook: ModuleType, tmp_path: Path) -> None:
        """
        Test that function/class docstrings (indented triple-quotes) are not converted.
        """
        src = '"""\nModule\n"""\n\n\ndef f() -> None:\n    """\n    Function docstring\n    """\n    pass\n'
        f = tmp_path / 'sample.py'
        f.write_text(src)

        replaced = hook.format_file(f)
        assert replaced      == 0
        assert f.read_text() == src

    def test_module_level_string_constants_are_not_mangled(self, hook: ModuleType, tmp_path: Path) -> None:
        """
        Test that module-level triple-quoted string constants (assignments) are left untouched.
        """
        src = (
            '"""\nModule docstring\n"""\n'
            'from __future__ import annotations\n\n'
            'A = """\nfirst constant\n"""\n\n'
            'B = """\nsecond constant\n"""\n'
        )
        f = tmp_path / 'sample.py'
        f.write_text(src)

        replaced = hook.format_file(f)
        assert replaced      == 0
        assert f.read_text() == src

    def test_mixed_header_and_constant_preserves_constant(self, hook: ModuleType, tmp_path: Path) -> None:
        """
        Test that only a genuine section header is converted while an adjacent string constant is left intact.
        """
        src = (
            '"""\nModule\n"""\n\n'
            '"""\nReal Section\n"""\n\n'
            'KEPT = """\nkept constant\n"""\n'
        )
        f = tmp_path / 'sample.py'
        f.write_text(src)

        replaced = hook.format_file(f)
        assert replaced == 1

        result = f.read_text()
        assert '# Real Section' in result
        assert 'KEPT = """'     in result
        assert 'kept constant'  in result

    def test_no_triple_quotes_returns_zero(self, hook: ModuleType, tmp_path: Path) -> None:
        """
        Test that a file with no standalone triple-quote lines is not modified.
        """
        src = 'import os\n\nx = 1\n'
        f = tmp_path / 'sample.py'
        f.write_text(src)

        replaced = hook.format_file(f)
        assert replaced      == 0
        assert f.read_text() == src

    def test_odd_triple_quote_count_skipped(
        self,
        hook: ModuleType,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that a file with an odd number of standalone triple-quote lines is left untouched and returns -1.
        """
        src = '"""\nModule\n"""\n\n\n"""\n'
        f = tmp_path / 'sample.py'
        f.write_text(src)

        replaced = hook.format_file(f)
        assert replaced      == -1
        assert f.read_text() == src

        captured = capsys.readouterr()
        assert 'could not be parsed as Python' in captured.err
        assert 'ERROR'                         in captured.err

    def test_does_not_rewrite_when_no_change(self, hook: ModuleType, tmp_path: Path) -> None:
        """
        Test that the file mtime is preserved when no replacements are made.
        """
        src = 'import os\n'
        f = tmp_path / 'sample.py'
        f.write_text(src)

        original_mtime = f.stat().st_mtime_ns
        replaced       = hook.format_file(f)

        assert replaced             == 0
        assert f.stat().st_mtime_ns == original_mtime


class TestMakeBorder:
    """
    Tests for the make_border() and is_border() helpers.
    """
    def test_default_is_100_wide_equals(self, hook: ModuleType) -> None:
        """
        Test that the default border is 100 characters of ``=`` after the leading comment marker.
        """
        border = hook.make_border()
        assert border == '# ' + '=' * 98
        assert len(border) == 100

    def test_indent_counts_toward_width(self, hook: ModuleType) -> None:
        """
        Test that indentation is included in the total width.
        """
        border = hook.make_border(4, '-', 40)
        assert border == '    # ' + '-' * 34
        assert len(border) == 40

    def test_tiny_width_still_has_one_char(self, hook: ModuleType) -> None:
        """
        Test that a width too small for a border still yields a one-character border.
        """
        assert hook.make_border(10, '=', 5) == ' ' * 10 + '# ='

    @pytest.mark.parametrize(
        ('comment', 'char', 'expected'),
        [
            ('# ======',   '=',  True),
            ('#======',    '=',  True),
            ('# ===',      '=',  True),
            ('# ==',       '=',  False),
            ('# == foo ==', '=', False),
            ('# Title',    '=',  False),
            ('# ------',   '=',  False),
            ('# ------',   '-',  True),
            ('# =-=-=-',   '=',  False),
        ],
    )
    def test_is_border(self, hook: ModuleType, comment: str, char: str, expected: bool) -> None:
        """
        Test border recognition across minimum length, mixed content, and configured character.
        """
        assert hook.is_border(comment, char) is expected


class TestNormalizeBorders:
    """
    Tests for the normalize_borders() function.
    """
    def test_widens_short_borders(self, hook: ModuleType) -> None:
        """
        Test that short borders are widened and counted once per header.
        """
        src = '# =====\n# Title\n# =====\n\nx = 1\n'
        result, n = hook.normalize_borders(src)
        border = hook.make_border()
        assert result == f'{border}\n# Title\n{border}\n\nx = 1\n'
        assert n      == 1

    def test_narrows_long_borders(self, hook: ModuleType) -> None:
        """
        Test that over-wide borders are narrowed to the configured width.
        """
        src = '# ' + '=' * 150 + '\n# Title\n# ' + '=' * 150 + '\n'
        result, n = hook.normalize_borders(src, '=', 50)
        assert result == '# ' + '=' * 48 + '\n# Title\n# ' + '=' * 48 + '\n'
        assert n      == 1

    def test_correct_borders_unchanged(self, hook: ModuleType) -> None:
        """
        Test that correctly sized headers are not counted as changed.
        """
        border = hook.make_border()
        src    = f'{border}\n# Title\n{border}\n'
        assert hook.normalize_borders(src) == (src, 0)

    def test_mismatched_pair_fixed(self, hook: ModuleType) -> None:
        """
        Test that a header with one correct and one incorrect border is fixed.
        """
        border = hook.make_border()
        src    = f'{border}\n# Title\n# ====\n'
        assert hook.normalize_borders(src) == (f'{border}\n# Title\n{border}\n', 1)

    def test_indented_header_width_includes_indent(self, hook: ModuleType) -> None:
        """
        Test that indented headers keep their indentation and total ``width`` characters.
        """
        src = 'class A:\n    # ====\n    # Title\n    # ====\n    x = 1\n'
        result, n = hook.normalize_borders(src, '=', 30)
        border = '    # ' + '=' * 24
        assert result == f'class A:\n{border}\n    # Title\n{border}\n    x = 1\n'
        assert n      == 1

    def test_multi_line_header(self, hook: ModuleType) -> None:
        """
        Test that headers with several text and bare ``#`` lines are recognized.
        """
        src = '# ====\n# One\n#\n# Two\n# ====\n'
        result, n = hook.normalize_borders(src, '=', 20)
        border = '# ' + '=' * 18
        assert result == f'{border}\n# One\n#\n# Two\n{border}\n'
        assert n      == 1

    def test_adjacent_headers(self, hook: ModuleType) -> None:
        """
        Test that back-to-back headers are paired independently.
        """
        src = '# ===\n# A\n# ===\n# ===\n# B\n# ===\n'
        result, n = hook.normalize_borders(src, '=', 10)
        border = '# ' + '=' * 8
        assert result == f'{border}\n# A\n{border}\n{border}\n# B\n{border}\n'
        assert n      == 2

    def test_lone_underline_untouched(self, hook: ModuleType) -> None:
        """
        Test that a border not enclosing a header (title underline) is left alone.
        """
        src = '# Title\n# =====\n\nx = 1\n'
        assert hook.normalize_borders(src) == (src, 0)

    def test_unclosed_border_untouched(self, hook: ModuleType) -> None:
        """
        Test that an opening border without a closing border is left alone.
        """
        src = '# =====\n# Title\n\nx = 1\n'
        assert hook.normalize_borders(src) == (src, 0)

    def test_blank_line_breaks_header(self, hook: ModuleType) -> None:
        """
        Test that borders separated by a blank line are not treated as one header.
        """
        src = '# =====\n# Title\n\n# =====\n'
        assert hook.normalize_borders(src) == (src, 0)

    def test_inline_comment_not_a_border(self, hook: ModuleType) -> None:
        """
        Test that trailing comments are not mistaken for standalone borders.
        """
        src = 'x = 1  # ====\n# Title\ny = 2  # ====\n'
        assert hook.normalize_borders(src) == (src, 0)

    def test_string_literal_contents_untouched(self, hook: ModuleType) -> None:
        """
        Test that border-like lines inside multi-line strings are never rewritten.
        """
        src = 'S = """\n# ====\n# Title\n# ====\n"""\n'
        assert hook.normalize_borders(src) == (src, 0)

    def test_other_border_char_untouched(self, hook: ModuleType) -> None:
        """
        Test that borders drawn with a different character than configured are not recognized.
        """
        src = '# ----\n# Title\n# ----\n'
        assert hook.normalize_borders(src, '=', 30) == (src, 0)

    def test_custom_char_recognized(self, hook: ModuleType) -> None:
        """
        Test that borders of the configured character are recognized and resized.
        """
        src = '# ----\n# Title\n# ----\n'
        result, n = hook.normalize_borders(src, '-', 12)
        assert result == '# ' + '-' * 10 + '\n# Title\n# ' + '-' * 10 + '\n'
        assert n      == 1

    def test_width_too_small_for_indent_skipped(self, hook: ModuleType) -> None:
        """
        Test that headers are left alone when the indent leaves no room for a border character.
        """
        src = '        # ====\n        # Title\n        # ====\n'
        assert hook.normalize_borders(src, '=', 10) == (src, 0)


class TestFormatFileBorders:
    """
    Tests for border handling in format_file().
    """
    def test_normalizes_by_default(self, hook: ModuleType, tmp_path: Path) -> None:
        """
        Test that existing short borders are widened by default.
        """
        f = tmp_path / 'sample.py'
        f.write_text('"""\nModule\n"""\n\n# ====\n# Title\n# ====\n\nx = 1\n')

        assert hook.format_file(f) == 1
        border = hook.make_border()
        assert f.read_text() == f'"""\nModule\n"""\n\n{border}\n# Title\n{border}\n\nx = 1\n'

    def test_disabled_leaves_borders_alone(self, hook: ModuleType, tmp_path: Path) -> None:
        """
        Test that normalization can be disabled.
        """
        src = '"""\nModule\n"""\n\n# ====\n# Title\n# ====\n\nx = 1\n'
        f   = tmp_path / 'sample.py'
        f.write_text(src)

        assert hook.format_file(f, normalize=False) == 0
        assert f.read_text()                        == src

    def test_disabled_still_converts_triple_quotes(self, hook: ModuleType, tmp_path: Path) -> None:
        """
        Test that disabling normalization does not disable triple-quote conversion.
        """
        f = tmp_path / 'sample.py'
        f.write_text('"""\nModule\n"""\n\n\n"""\nSection\n"""\n\nx = 1\n')

        assert hook.format_file(f, normalize=False) == 1
        assert hook.make_border() in f.read_text()

    def test_converted_header_uses_custom_char_and_width(self, hook: ModuleType, tmp_path: Path) -> None:
        """
        Test that converted triple-quoted headers use the configured character and width.
        """
        f = tmp_path / 'sample.py'
        f.write_text('"""\nModule\n"""\n\n\n"""\nSection\n"""\n\nx = 1\n')

        assert hook.format_file(f, '-', 20) == 1
        border = '# ' + '-' * 18
        assert f.read_text() == f'"""\nModule\n"""\n\n\n{border}\n# Section\n{border}\n\nx = 1\n'

    def test_converted_header_counted_once(self, hook: ModuleType, tmp_path: Path) -> None:
        """
        Test that a header converted from triple quotes is not also counted as a resized border.
        """
        f = tmp_path / 'sample.py'
        f.write_text('"""\nModule\n"""\n\n\n"""\nSection\n"""\n\nx = 1\n')
        assert hook.format_file(f) == 1

    def test_idempotent(self, hook: ModuleType, tmp_path: Path) -> None:
        """
        Test that a second run over a formatted file changes nothing.
        """
        f = tmp_path / 'sample.py'
        f.write_text('"""\nModule\n"""\n\n# ====\n# A\n# ====\n\n"""\nB\n"""\nx = 1\n')

        assert hook.format_file(f) == 2
        first = f.read_text()
        assert hook.format_file(f) == 0
        assert f.read_text()       == first


class TestIterPythonFiles:
    """
    Tests for the iter_python_files() path-expansion helper.
    """
    def test_expands_directory(self, hook: ModuleType, tmp_path: Path) -> None:
        """
        Test that directories are recursed and only ``.py`` files are returned.
        """
        (tmp_path / 'a.py').write_text('')
        (tmp_path / 'b.txt').write_text('')
        sub = tmp_path / 'sub'
        sub.mkdir()
        (sub / 'c.py').write_text('')

        result = hook.iter_python_files([tmp_path])
        names  = sorted(p.name for p in result)
        assert names == ['a.py', 'c.py']

    def test_files_passed_directly_returned_as_is(self, hook: ModuleType, tmp_path: Path) -> None:
        """
        Test that files passed directly are included regardless of suffix.
        """
        f = tmp_path / 'something.txt'
        f.write_text('')
        result = hook.iter_python_files([f])
        assert result == [f]

    def test_skip_dirs_excluded(self, hook: ModuleType, tmp_path: Path) -> None:
        """
        Test that .git, .venv, __pycache__, etc. are excluded during directory recursion.
        """
        for skip in hook.SKIP_DIRS:
            sub = tmp_path / skip
            sub.mkdir()
            (sub / 'ignored.py').write_text('')

        (tmp_path / 'kept.py').write_text('')

        result = hook.iter_python_files([tmp_path])
        names  = [p.name for p in result]
        assert names == ['kept.py']

    def test_deduplication(self, hook: ModuleType, tmp_path: Path) -> None:
        """
        Test that duplicate paths (file + dir containing it) are returned once.
        """
        f = tmp_path / 'a.py'
        f.write_text('')
        result = hook.iter_python_files([f, tmp_path])
        assert len(result) == 1

    def test_nonexistent_path_warns(
        self,
        hook: ModuleType,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that a nonexistent path is skipped with a warning to stderr.
        """
        bogus  = tmp_path / 'does-not-exist'
        result = hook.iter_python_files([bogus])
        assert result == []

        captured = capsys.readouterr()
        assert 'non-existent' in captured.err


class TestParseArgs:
    """
    Tests for the parse_args() function.
    """
    def test_default_path_is_cwd(self, hook: ModuleType) -> None:
        """
        Test that no positional arguments yields a default of the current working directory.
        """
        args = hook.parse_args([])
        assert args.paths == [Path()]

    def test_explicit_paths(self, hook: ModuleType) -> None:
        """
        Test that explicit positional paths are converted to Path objects.
        """
        args = hook.parse_args(['a.py', 'b/c.py'])
        assert args.paths == [Path('a.py'), Path('b/c.py')]

    def test_exit_non_zero_on_fix_default_false(self, hook: ModuleType) -> None:
        """
        Test that --exit-non-zero-on-fix defaults to False.
        """
        args = hook.parse_args([])
        assert args.exit_non_zero_on_fix is False

    def test_exit_non_zero_on_fix_flag(self, hook: ModuleType) -> None:
        """
        Test that the --exit-non-zero-on-fix flag enables fixer-mode exit codes.
        """
        args = hook.parse_args(['--exit-non-zero-on-fix'])
        assert args.exit_non_zero_on_fix is True

    def test_border_defaults(self, hook: ModuleType) -> None:
        """
        Test that borders default to 100 columns of ``=`` with normalization enabled.
        """
        args = hook.parse_args([])
        assert args.border_char       == '='
        assert args.border_width      == 100
        assert args.normalize_borders is True

    def test_border_options(self, hook: ModuleType) -> None:
        """
        Test that border character, width, and normalization can be overridden.
        """
        args = hook.parse_args(['--border-char', '-', '--border-width', '120', '--no-normalize-borders'])
        assert args.border_char       == '-'
        assert args.border_width      == 120
        assert args.normalize_borders is False

    @pytest.mark.parametrize(
        'bad_args',
        [
            ['--border-char',  ''],
            ['--border-char',  '=='],
            ['--border-char',  ' '],
            ['--border-width', 'abc'],
            ['--border-width', '2'],
            ['--border-width', '-5'],
        ],
    )
    def test_invalid_border_options_rejected(self, hook: ModuleType, bad_args: list[str]) -> None:
        """
        Test that invalid border characters and widths exit with an argparse error.
        """
        with pytest.raises(SystemExit) as exc_info:
            hook.parse_args(bad_args)
        assert exc_info.value.code == 2


class TestMain:
    """
    Tests for the main() entry point.
    """
    def test_returns_zero_when_no_changes(self, hook: ModuleType, tmp_path: Path) -> None:
        """
        Test that main returns 0 when nothing was modified.
        """
        f = tmp_path / 'a.py'
        f.write_text('import os\n')
        assert hook.main([str(f)]) == 0

    def test_returns_zero_on_changes_without_flag(self, hook: ModuleType, tmp_path: Path) -> None:
        """
        Test that main returns 0 when files are modified but the fixer-flag is absent.
        """
        f = tmp_path / 'a.py'
        f.write_text('"""\nModule\n"""\n\n\n"""\nSection\n"""\n\n\nx = 1\n')
        assert hook.main([str(f)]) == 0
        assert '# Section' in f.read_text()

    def test_returns_one_on_changes_with_flag(self, hook: ModuleType, tmp_path: Path) -> None:
        """
        Test that main returns 1 when files are modified and --exit-non-zero-on-fix is set.
        """
        f = tmp_path / 'a.py'
        f.write_text('"""\nModule\n"""\n\n\n"""\nSection\n"""\n\n\nx = 1\n')
        assert hook.main(['--exit-non-zero-on-fix', str(f)]) == 1

    def test_returns_zero_on_no_changes_with_flag(self, hook: ModuleType, tmp_path: Path) -> None:
        """
        Test that the fixer-flag does not change the return code when nothing was modified.
        """
        f = tmp_path / 'a.py'
        f.write_text('import os\n')
        assert hook.main(['--exit-non-zero-on-fix', str(f)]) == 0

    def test_prints_singular_for_single_replacement(
        self,
        hook: ModuleType,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that a single replacement uses 'header' (no plural).
        """
        f = tmp_path / 'a.py'
        f.write_text('"""\nModule\n"""\n\n\n"""\nSection\n"""\n\n\nx = 1\n')
        hook.main([str(f)])

        out = capsys.readouterr().out
        assert 'fixed 1 header\n'    in out
        assert 'fixed 1 headers' not in out

    def test_prints_plural_for_multiple_replacements(
        self,
        hook: ModuleType,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that two or more replacements use the plural 'headers'.
        """
        f = tmp_path / 'a.py'
        f.write_text(
            '"""\nModule\n"""\n\n\n'
            '"""\nFirst\n"""\n\n\n'
            'a = 1\n\n\n'
            '"""\nSecond\n"""\n\n\n'
            'b = 2\n'
        )
        hook.main([str(f)])

        out = capsys.readouterr().out
        assert 'fixed 2 headers' in out

    def test_returns_one_on_malformed_file(self, hook: ModuleType, tmp_path: Path) -> None:
        """
        Test that main returns 1 when any file is skipped due to a malformed triple-quote structure.
        """
        f = tmp_path / 'a.py'
        f.write_text('"""\nModule\n"""\n\n\n"""\n')
        assert hook.main([str(f)]) == 1

    def test_malformed_file_fails_even_without_fixer_flag(self, hook: ModuleType, tmp_path: Path) -> None:
        """
        Test that a malformed file fails the hook regardless of whether --exit-non-zero-on-fix is set.
        """
        f = tmp_path / 'a.py'
        f.write_text('"""\nModule\n"""\n\n\n"""\n')
        assert hook.main(['--exit-non-zero-on-fix', str(f)]) == 1
        assert hook.main([str(f)])                           == 1


class TestMainBorders:
    """
    Tests for border options wired through main().
    """
    def test_resize_reported_and_fixer_flag_fails(
        self,
        hook: ModuleType,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that resizing a border is reported as a fix and trips --exit-non-zero-on-fix.
        """
        f = tmp_path / 'a.py'
        f.write_text('# ====\n# Title\n# ====\nx = 1\n')

        assert hook.main(['--exit-non-zero-on-fix', str(f)]) == 1
        assert 'fixed 1 header\n' in capsys.readouterr().out
        assert f.read_text().splitlines()[0] == hook.make_border()

    def test_no_normalize_borders_flag_leaves_file_alone(self, hook: ModuleType, tmp_path: Path) -> None:
        """
        Test that --no-normalize-borders leaves existing borders alone and exits cleanly.
        """
        src = '# ====\n# Title\n# ====\nx = 1\n'
        f   = tmp_path / 'a.py'
        f.write_text(src)

        assert hook.main(['--exit-non-zero-on-fix', '--no-normalize-borders', str(f)]) == 0
        assert f.read_text() == src

    def test_custom_char_and_width(self, hook: ModuleType, tmp_path: Path) -> None:
        """
        Test that --border-char and --border-width apply to converted headers.
        """
        f = tmp_path / 'a.py'
        f.write_text('"""\nModule\n"""\n\n\n"""\nSection\n"""\nx = 1\n')

        assert hook.main(['--border-char', '~', '--border-width', '30', str(f)]) == 0
        assert ('# ' + '~' * 28) in f.read_text()
