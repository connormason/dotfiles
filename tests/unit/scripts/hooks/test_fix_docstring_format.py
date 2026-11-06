"""
Tests for the fix_docstring_format.py pre-commit hook script.

Validates single-line to multi-line docstring conversion, AST-based docstring detection, argument parsing, and
edge case handling (empty docstrings, syntax errors, non-docstring strings, different quote styles).
"""
from __future__ import annotations

import argparse
import ast
import importlib.util
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from tests.conftest import unstyle

if TYPE_CHECKING:
    from types import ModuleType


HOOK_PATH = str(Path(__file__).parents[4] / 'scripts' / 'hooks' / 'fix_docstring_format.py')

assert Path(HOOK_PATH).is_file(), (
    f'Script under test not found: {HOOK_PATH}\n'
    'Did the script move? Update HOOK_PATH in this test module.'
)


# ==================================================================================================
# Fixtures
# ==================================================================================================


def _load_module() -> ModuleType:
    """
    Load fix-docstring-format.py via importlib (hyphenated filename prevents normal import).

    :return: the loaded module
    """
    spec = importlib.util.spec_from_file_location('fix_docstring_format', HOOK_PATH)
    assert spec        is not None
    assert spec.loader is not None

    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def hook() -> ModuleType:
    """
    Return the loaded fix-docstring-format module.
    """
    return _load_module()


# ==================================================================================================
# Unit tests
# ==================================================================================================


class TestExpandSingleLineDocstring:
    """
    Tests for expand_single_line_docstring().
    """
    def test_basic_double_quote(self, hook: ModuleType) -> None:
        """
        Test expansion of a basic double-quote single-line docstring.
        """
        result = hook.expand_single_line_docstring('    """Brief description."""')
        assert result == [
            '    """',
            '    Brief description.',
            '    """',
        ]

    def test_basic_single_quote(self, hook: ModuleType) -> None:
        """
        Test expansion of a single-quote triple-quoted docstring.
        """
        result = hook.expand_single_line_docstring("    '''Brief description.'''")
        assert result == [
            "    '''",
            '    Brief description.',
            "    '''",
        ]

    def test_no_indentation(self, hook: ModuleType) -> None:
        """
        Test expansion of a module-level docstring with no indentation.
        """
        result = hook.expand_single_line_docstring('"""Module docstring."""')
        assert result == [
            '"""',
            'Module docstring.',
            '"""',
        ]

    def test_deep_indentation(self, hook: ModuleType) -> None:
        """
        Test expansion preserves deep indentation levels.
        """
        result = hook.expand_single_line_docstring('            """Deeply nested."""')
        assert result == [
            '            """',
            '            Deeply nested.',
            '            """',
        ]

    def test_raw_docstring_prefix(self, hook: ModuleType) -> None:
        """
        Test expansion of r-prefixed docstring.
        """
        result = hook.expand_single_line_docstring('    r"""Raw docstring with \\n."""')
        assert result == [
            '    r"""',
            '    Raw docstring with \\n.',
            '    """',
        ]

    def test_unicode_prefix(self, hook: ModuleType) -> None:
        """
        Test expansion of u-prefixed docstring.
        """
        result = hook.expand_single_line_docstring('    u"""Unicode docstring."""')
        assert result == [
            '    u"""',
            '    Unicode docstring.',
            '    """',
        ]

    def test_empty_docstring_unchanged(self, hook: ModuleType) -> None:
        """
        Test that empty docstrings are left unchanged.
        """
        line = '    """"""'
        result = hook.expand_single_line_docstring(line)
        assert result == [line]

    def test_whitespace_only_docstring_unchanged(self, hook: ModuleType) -> None:
        """
        Test that whitespace-only docstrings are left unchanged.
        """
        line = '    """   """'
        result = hook.expand_single_line_docstring(line)
        assert result == [line]

    def test_not_triple_quoted_unchanged(self, hook: ModuleType) -> None:
        """
        Test that non-triple-quoted strings are left unchanged.
        """
        line = '    "regular string"'
        result = hook.expand_single_line_docstring(line)
        assert result == [line]

    def test_content_with_inner_quotes(self, hook: ModuleType) -> None:
        """
        Test expansion when content contains inner double quotes.
        """
        result = hook.expand_single_line_docstring('    """Return the "name" field."""')
        assert result == [
            '    """',
            '    Return the "name" field.',
            '    """',
        ]

    def test_content_whitespace_stripped(self, hook: ModuleType) -> None:
        """
        Test that leading/trailing whitespace in docstring content is stripped.
        """
        result = hook.expand_single_line_docstring('    """   Padded content.   """')
        assert result == [
            '    """',
            '    Padded content.',
            '    """',
        ]

    def test_tabs_indentation(self, hook: ModuleType) -> None:
        """
        Test expansion preserves tab indentation.
        """
        result = hook.expand_single_line_docstring('\t\t"""Tab indented."""')
        assert result == [
            '\t\t"""',
            '\t\tTab indented.',
            '\t\t"""',
        ]


class TestFindDocstringExprs:
    """
    Tests for find_docstring_exprs().
    """
    def test_module_docstring(self, hook: ModuleType) -> None:
        """
        Test detection of module-level docstring.
        """
        tree  = ast.parse('"""Module doc."""\nx = 1\n')
        exprs = hook.find_docstring_exprs(tree)

        assert len(exprs)      == 1
        assert exprs[0].lineno == 1

    def test_function_docstring(self, hook: ModuleType) -> None:
        """
        Test detection of function docstring.
        """
        source = textwrap.dedent('''\
            def func():
                """Function doc."""
                pass
        ''')
        tree  = ast.parse(source)
        exprs = hook.find_docstring_exprs(tree)

        assert len(exprs)      == 1
        assert exprs[0].lineno == 2

    def test_class_docstring(self, hook: ModuleType) -> None:
        """
        Test detection of class docstring.
        """
        source = textwrap.dedent('''\
            class MyClass:
                """Class doc."""
                pass
        ''')
        tree  = ast.parse(source)
        exprs = hook.find_docstring_exprs(tree)

        assert len(exprs)      == 1
        assert exprs[0].lineno == 2

    def test_async_function_docstring(self, hook: ModuleType) -> None:
        """
        Test detection of async function docstring.
        """
        source = textwrap.dedent('''\
            async def func():
                """Async doc."""
                pass
        ''')
        tree  = ast.parse(source)
        exprs = hook.find_docstring_exprs(tree)
        assert len(exprs) == 1

    def test_method_docstring(self, hook: ModuleType) -> None:
        """
        Test detection of method docstring inside a class.
        """
        source = textwrap.dedent('''\
            class MyClass:
                """Class doc."""
                def method(self):
                    """Method doc."""
                    pass
        ''')
        tree  = ast.parse(source)
        exprs = hook.find_docstring_exprs(tree)
        assert len(exprs) == 2

    def test_section_comment_not_detected(self, hook: ModuleType) -> None:
        """
        Test that freestanding string expressions (section comments) are NOT detected as docstrings.
        """
        source = textwrap.dedent('''\
            class MyClass:
                """Class doc."""

                """ Section header """

                def method(self):
                    pass
        ''')
        tree  = ast.parse(source)
        exprs = hook.find_docstring_exprs(tree)
        assert len(exprs) == 1

    def test_no_docstrings(self, hook: ModuleType) -> None:
        """
        Test that code with no docstrings returns empty list.
        """
        tree  = ast.parse('x = 1\ny = 2\n')
        exprs = hook.find_docstring_exprs(tree)
        assert len(exprs) == 0

    def test_multiline_docstring_detected(self, hook: ModuleType) -> None:
        """
        Test that multi-line docstrings are found (though they won't need fixing).
        """
        source = textwrap.dedent('''\
            def func():
                """
                Already multi-line.
                """
                pass
        ''')
        tree  = ast.parse(source)
        exprs = hook.find_docstring_exprs(tree)

        assert len(exprs) == 1
        assert exprs[0].lineno != exprs[0].end_lineno


class TestFixResult:
    """
    Tests for the FixResult dataclass.
    """
    def test_default_skipped_lines_empty(self, hook: ModuleType) -> None:
        """
        Test that skipped_lines defaults to an empty list.
        """
        result = hook.FixResult(modified=False)
        assert result.skipped_lines == []

    def test_modified_flag(self, hook: ModuleType) -> None:
        """
        Test that modified flag is stored correctly.
        """
        assert hook.FixResult(modified=True).modified  is True
        assert hook.FixResult(modified=False).modified is False

    def test_skipped_lines_stored(self, hook: ModuleType) -> None:
        """
        Test that skipped_lines are stored correctly.
        """
        result = hook.FixResult(modified=False, skipped_lines=[1, 5, 10])
        assert result.skipped_lines == [1, 5, 10]


class TestHasSuppressionComment:
    """
    Tests for has_suppression_comment().
    """
    def test_inline_double_quote(self, hook: ModuleType) -> None:
        """
        Test detection of inline suppression comment with double quotes.
        """
        lines = ['    """Brief."""  # nofmt: docstring\n']
        assert hook.has_suppression_comment(lines, 0) is True

    def test_inline_single_quote(self, hook: ModuleType) -> None:
        """
        Test detection of inline suppression comment with single quotes.
        """
        lines = ["    '''Brief.'''  # nofmt: docstring\n"]
        assert hook.has_suppression_comment(lines, 0) is True

    def test_line_above(self, hook: ModuleType) -> None:
        """
        Test detection of suppression comment on the line above.
        """
        lines = ['    # nofmt: docstring\n', '    """Brief."""\n']
        assert hook.has_suppression_comment(lines, 1) is True

    def test_line_above_with_extra_text(self, hook: ModuleType) -> None:
        """
        Test detection when line-above comment has additional text after the marker.
        """
        lines = ['    # nofmt: docstring -- keep this one compact\n', '    """Brief."""\n']
        assert hook.has_suppression_comment(lines, 1) is True

    def test_no_suppression_comment(self, hook: ModuleType) -> None:
        """
        Test that docstrings without suppression comments return False.
        """
        lines = ['    """Brief."""\n']
        assert hook.has_suppression_comment(lines, 0) is False

    def test_unrelated_comment_above(self, hook: ModuleType) -> None:
        """
        Test that unrelated comments above do not trigger suppression.
        """
        lines = ['    # some other comment\n', '    """Brief."""\n']
        assert hook.has_suppression_comment(lines, 1) is False

    def test_first_line_no_line_above(self, hook: ModuleType) -> None:
        """
        Test that first line of file has no line above to check.
        """
        lines = ['"""Module doc."""\n']
        assert hook.has_suppression_comment(lines, 0) is False

    def test_code_line_above_not_matched(self, hook: ModuleType) -> None:
        """
        Test that a non-comment line above containing the marker text is not matched.
        """
        lines = ['x = "nofmt: docstring"\n', '    """Brief."""\n']
        assert hook.has_suppression_comment(lines, 1) is False

    def test_inline_without_trailing_newline(self, hook: ModuleType) -> None:
        """
        Test detection works on lines without trailing newlines.
        """
        lines = ['    """Brief."""  # nofmt: docstring']
        assert hook.has_suppression_comment(lines, 0) is True


class TestFixFile:
    """
    Tests for fix_file().
    """
    def test_fixes_single_line_docstring(self, hook: ModuleType, tmp_path: Path) -> None:
        """
        Test that a single-line function docstring is expanded to multi-line.
        """
        source = textwrap.dedent('''\
            def func():
                """Brief description."""
                pass
        ''')
        f = tmp_path / 'test.py'
        f.write_text(source)

        result = hook.fix_file(f)

        assert result.modified is True
        fixed = f.read_text()
        assert fixed == textwrap.dedent('''\
            def func():
                """
                Brief description.
                """
                pass
        ''')

    def test_fixes_multiple_docstrings(self, hook: ModuleType, tmp_path: Path) -> None:
        """
        Test that multiple single-line docstrings are all fixed.
        """
        source = textwrap.dedent('''\
            """Module doc."""

            class MyClass:
                """Class doc."""

                def method(self):
                    """Method doc."""
                    pass
        ''')
        f = tmp_path / 'test.py'
        f.write_text(source)

        result = hook.fix_file(f)
        assert result.modified is True

        fixed = f.read_text()
        assert '"""Module doc."""' not in fixed
        assert '"""Class doc."""'  not in fixed
        assert '"""Method doc."""' not in fixed
        assert fixed.count('"""') == 6

    def test_leaves_multiline_docstrings_unchanged(self, hook: ModuleType, tmp_path: Path) -> None:
        """
        Test that already multi-line docstrings are not modified.
        """
        source = textwrap.dedent('''\
            def func():
                """
                Already multi-line.
                """
                pass
        ''')
        f = tmp_path / 'test.py'
        f.write_text(source)

        result = hook.fix_file(f)

        assert result.modified is False
        assert f.read_text()   == source

    def test_check_only_does_not_modify(self, hook: ModuleType, tmp_path: Path) -> None:
        """
        Test that check_only=True reports violations without modifying the file.
        """
        source = textwrap.dedent('''\
            def func():
                """Brief description."""
                pass
        ''')
        f = tmp_path / 'test.py'
        f.write_text(source)

        result = hook.fix_file(f, check_only=True)

        assert result.modified is True
        assert f.read_text()   == source

    def test_syntax_error_returns_false(self, hook: ModuleType, tmp_path: Path) -> None:
        """
        Test that files with syntax errors are skipped gracefully.
        """
        f = tmp_path / 'broken.py'
        f.write_text('def func(\n')

        result = hook.fix_file(f)
        assert result.modified is False

    def test_no_docstrings_returns_false(self, hook: ModuleType, tmp_path: Path) -> None:
        """
        Test that files with no docstrings return False.
        """
        f = tmp_path / 'nodoc.py'
        f.write_text('x = 1\ny = 2\n')

        result = hook.fix_file(f)
        assert result.modified is False

    def test_section_comments_not_modified(self, hook: ModuleType, tmp_path: Path) -> None:
        """
        Test that freestanding string expressions used as section comments are not touched.
        """
        source = textwrap.dedent('''\
            class MyClass:
                """
                Class doc.
                """

                """ Section header """

                x = 1
        ''')
        f = tmp_path / 'test.py'
        f.write_text(source)

        result = hook.fix_file(f)

        assert result.modified is False
        assert f.read_text()   == source

    def test_preserves_non_docstring_code(self, hook: ModuleType, tmp_path: Path) -> None:
        """
        Test that code around docstrings is preserved exactly.
        """
        source = textwrap.dedent('''\
            from __future__ import annotations

            import os


            def func(x: int, y: int) -> int:
                """Add two numbers."""
                return x + y


            class MyClass:
                """A class."""

                attr = 42
        ''')
        f = tmp_path / 'test.py'
        f.write_text(source)

        hook.fix_file(f)

        fixed = f.read_text()
        assert 'from __future__ import annotations' in fixed
        assert 'import os'                          in fixed
        assert 'return x + y'                       in fixed
        assert 'attr = 42'                          in fixed

    def test_single_quote_docstring(self, hook: ModuleType, tmp_path: Path) -> None:
        """
        Test that single-quote triple-quoted docstrings are expanded correctly.
        """
        source = "def func():\n    '''Brief.'''\n    pass\n"
        f = tmp_path / 'test.py'
        f.write_text(source)

        result = hook.fix_file(f)
        assert result.modified is True

        fixed = f.read_text()
        assert fixed == "def func():\n    '''\n    Brief.\n    '''\n    pass\n"

    def test_suppressed_inline_not_modified(self, hook: ModuleType, tmp_path: Path) -> None:
        """
        Test that a docstring with inline suppression comment is not expanded.
        """
        source = textwrap.dedent('''\
            def func():
                """Brief description."""  # nofmt: docstring
                pass
        ''')
        f = tmp_path / 'test.py'
        f.write_text(source)

        result = hook.fix_file(f)

        assert result.modified      is False
        assert result.skipped_lines == [2]
        assert f.read_text()        == source

    def test_suppressed_line_above_not_modified(self, hook: ModuleType, tmp_path: Path) -> None:
        """
        Test that a docstring with suppression comment on line above is not expanded.
        """
        source = textwrap.dedent('''\
            def func():
                # nofmt: docstring
                """Brief description."""
                pass
        ''')
        f = tmp_path / 'test.py'
        f.write_text(source)

        result = hook.fix_file(f)

        assert result.modified      is False
        assert result.skipped_lines == [3]
        assert f.read_text()        == source

    def test_mixed_suppressed_and_unsuppressed(self, hook: ModuleType, tmp_path: Path) -> None:
        """
        Test that suppressed docstrings are skipped while unsuppressed ones are expanded.
        """
        source = textwrap.dedent('''\
            def func():
                """Should be expanded."""
                pass

            def other():
                """Keep me."""  # nofmt: docstring
                pass
        ''')
        f = tmp_path / 'test.py'
        f.write_text(source)

        result = hook.fix_file(f)

        assert result.modified      is True
        assert result.skipped_lines == [6]

        fixed = f.read_text()
        assert '"""Should be expanded."""'      not in fixed
        assert '"""Keep me."""  # nofmt: docstring' in fixed

    def test_all_suppressed_returns_not_modified(self, hook: ModuleType, tmp_path: Path) -> None:
        """
        Test that when all docstrings are suppressed the file is not modified.
        """
        source = textwrap.dedent('''\
            def func():
                """One."""  # nofmt: docstring
                pass

            def other():
                # nofmt: docstring
                """Two."""
                pass
        ''')
        f = tmp_path / 'test.py'
        f.write_text(source)

        result = hook.fix_file(f)

        assert result.modified      is False
        assert result.skipped_lines == [2, 7]
        assert f.read_text()        == source


class TestMain:
    """
    Tests for the main() entry point.
    """
    def test_no_filenames_returns_zero(self, hook: ModuleType) -> None:
        """
        Test that main returns 0 when no filenames are provided.
        """
        assert hook.main([]) == 0

    def test_file_with_violations_returns_one(self, hook: ModuleType, tmp_path: Path) -> None:
        """
        Test that main returns 1 when files are modified.
        """
        f = tmp_path / 'test.py'
        f.write_text('def func():\n    """Brief."""\n    pass\n')

        result = hook.main([str(f)])
        assert result == 1

    def test_clean_file_returns_zero(self, hook: ModuleType, tmp_path: Path) -> None:
        """
        Test that main returns 0 when no files need modification.
        """
        f = tmp_path / 'test.py'
        f.write_text('def func():\n    """\n    Brief.\n    """\n    pass\n')

        result = hook.main([str(f)])
        assert result == 0

    def test_check_mode_does_not_modify(self, hook: ModuleType, tmp_path: Path) -> None:
        """
        Test that --check flag prevents file modification.
        """
        source = 'def func():\n    """Brief."""\n    pass\n'
        f = tmp_path / 'test.py'
        f.write_text(source)

        result = hook.main(['--check', str(f)])

        assert result        == 1
        assert f.read_text() == source

    def test_multiple_files(self, hook: ModuleType, tmp_path: Path) -> None:
        """
        Test processing multiple files where some need fixing.
        """
        clean = tmp_path / 'clean.py'
        clean.write_text('def func():\n    """\n    Brief.\n    """\n    pass\n')

        dirty = tmp_path / 'dirty.py'
        dirty.write_text('def func():\n    """Brief."""\n    pass\n')

        result = hook.main([str(clean), str(dirty)])
        assert result == 1

    def test_verbose_shows_unmodified(
        self,
        hook: ModuleType,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that verbose mode reports unmodified files.
        """
        f = tmp_path / 'clean.py'
        f.write_text('def func():\n    """\n    Brief.\n    """\n    pass\n')

        hook.main(['-v', str(f)])

        captured = capsys.readouterr()
        assert 'clean.py' in captured.out

    def test_modified_file_shown_in_output(
        self,
        hook: ModuleType,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that modified files are reported in output.
        """
        f = tmp_path / 'dirty.py'
        f.write_text('def func():\n    """Brief."""\n    pass\n')

        hook.main([str(f)])

        captured = capsys.readouterr()
        assert 'dirty.py' in captured.out

    def test_verbose_shows_skipped(
        self,
        hook: ModuleType,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that verbose mode reports skipped docstrings.
        """
        f = tmp_path / 'test.py'
        f.write_text('def func():\n    """Brief."""  # nofmt: docstring\n    pass\n')

        hook.main(['-v', str(f)])

        captured = capsys.readouterr()
        assert 'SKIPPED' in unstyle(captured.out)

    def test_non_verbose_hides_skipped(
        self,
        hook: ModuleType,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that non-verbose mode does not report skipped docstrings.
        """
        f = tmp_path / 'test.py'
        f.write_text('def func():\n    """Brief."""  # nofmt: docstring\n    pass\n')

        hook.main([str(f)])

        captured = capsys.readouterr()
        assert 'SKIPPED' not in unstyle(captured.out)

    def test_suppressed_file_returns_zero(self, hook: ModuleType, tmp_path: Path) -> None:
        """
        Test that a file with only suppressed docstrings returns exit code 0.
        """
        f = tmp_path / 'test.py'
        f.write_text('def func():\n    """Brief."""  # nofmt: docstring\n    pass\n')

        result = hook.main([str(f)])
        assert result == 0


class TestArgs:
    """
    Tests for the Args namespace class.
    """
    def test_args_is_namespace_subclass(self, hook: ModuleType) -> None:
        """
        Test that Args inherits from argparse.Namespace.
        """
        assert issubclass(hook.Args, argparse.Namespace)

    def test_args_has_expected_annotations(self, hook: ModuleType) -> None:
        """
        Test that Args declares filenames, check, and verbose annotations.
        """
        annotations = hook.Args.__annotations__
        assert 'filenames' in annotations
        assert 'check'     in annotations
        assert 'verbose'   in annotations


class TestParseArgs:
    """
    Tests for the parse_args() function.
    """
    def test_filenames_parsed(self, hook: ModuleType) -> None:
        """
        Test that positional filenames are parsed correctly.
        """
        args = hook.parse_args(['a.py', 'b.py'])
        assert args.filenames == ['a.py', 'b.py']

    def test_no_filenames(self, hook: ModuleType) -> None:
        """
        Test that empty argv produces empty filenames list.
        """
        args = hook.parse_args([])
        assert args.filenames == []

    def test_check_flag_default_false(self, hook: ModuleType) -> None:
        """
        Test that --check defaults to False.
        """
        args = hook.parse_args([])
        assert args.check is False

    def test_check_flag(self, hook: ModuleType) -> None:
        """
        Test that --check flag is parsed correctly.
        """
        args = hook.parse_args(['--check', 'file.py'])
        assert args.check is True

    def test_verbose_flag_default_false(self, hook: ModuleType) -> None:
        """
        Test that verbose defaults to False.
        """
        args = hook.parse_args([])
        assert args.verbose is False

    def test_verbose_flag_short(self, hook: ModuleType) -> None:
        """
        Test that -v enables verbose mode.
        """
        args = hook.parse_args(['-v', 'file.py'])
        assert args.verbose is True

    def test_returns_args_instance(self, hook: ModuleType) -> None:
        """
        Test that parse_args returns an instance of Args.
        """
        args = hook.parse_args([])
        assert isinstance(args, hook.Args)
