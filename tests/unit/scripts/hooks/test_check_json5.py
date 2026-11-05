"""
Tests for the check-json5.py pre-commit hook script.

Validates JSON5 file syntax checking, argument parsing, and verbose/error output formatting.
"""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType


HOOK_PATH = str(Path(__file__).parents[4] / 'scripts' / 'hooks' / 'check-json5.py')

assert Path(HOOK_PATH).is_file(), (
    f'Script under test not found: {HOOK_PATH}\n'
    'Did the script move? Update HOOK_PATH in this test module.'
)


# ==================================================================================================
# Fixtures
# ==================================================================================================


def _load_module() -> ModuleType:
    """
    Load check-json5.py via importlib (hyphenated filename prevents normal import).

    :raises Skipped: if pyjson5 is not installed
    :return: the loaded module
    """
    pytest.importorskip('pyjson5', reason='pyjson5 is required for check-json5 tests')

    spec = importlib.util.spec_from_file_location('check_json5', HOOK_PATH)
    assert spec        is not None
    assert spec.loader is not None

    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def hook() -> ModuleType:
    """
    Return the loaded check-json5 module.
    """
    return _load_module()


# ==================================================================================================
# Unit tests
# ==================================================================================================


class TestPrintf:
    """
    Tests for the printf() helper function.
    """
    def test_basic_output(self, hook: ModuleType, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that printf prints text to stdout.
        """
        hook.printf('hello world')
        captured = capsys.readouterr()
        assert 'hello world' in captured.out

    def test_indent(self, hook: ModuleType, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that printf indents output by the specified number of spaces.
        """
        hook.printf('indented', indent=4)
        captured = capsys.readouterr()
        assert captured.out.startswith('    ')


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
        Test that Args declares filenames and verbose annotations.
        """
        annotations = hook.Args.__annotations__
        assert 'filenames' in annotations
        assert 'verbose'   in annotations


class TestParseArgs:
    """
    Tests for the parse_args() function.
    """
    def test_filenames_parsed(self, hook: ModuleType) -> None:
        """
        Test that positional filenames are parsed correctly.
        """
        args = hook.parse_args(['a.json5', 'b.json5'])
        assert args.filenames == ['a.json5', 'b.json5']

    def test_no_filenames(self, hook: ModuleType) -> None:
        """
        Test that empty argv produces empty filenames list.
        """
        args = hook.parse_args([])
        assert args.filenames == []

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
        args = hook.parse_args(['-v', 'file.json5'])
        assert args.verbose is True

    def test_verbose_flag_long(self, hook: ModuleType) -> None:
        """
        Test that --verbose enables verbose mode.
        """
        args = hook.parse_args(['--verbose', 'file.json5'])
        assert args.verbose is True

    def test_returns_args_instance(self, hook: ModuleType) -> None:
        """
        Test that parse_args returns an instance of Args.
        """
        args = hook.parse_args([])
        assert isinstance(args, hook.Args)


class TestMain:
    """
    Tests for the main() entry point.
    """
    def test_no_filenames_returns_zero(self, hook: ModuleType) -> None:
        """
        Test that main returns 0 when no filenames are provided.
        """
        assert hook.main([]) == 0

    def test_valid_json5_file(self, hook: ModuleType, tmp_path: Path) -> None:
        """
        Test that a valid JSON5 file produces return code 0.
        """
        valid_file = tmp_path / 'valid.json5'
        valid_file.write_text('{ key: "value", number: 42 }')
        assert hook.main([str(valid_file)]) == 0

    def test_invalid_json5_file(self, hook: ModuleType, tmp_path: Path) -> None:
        """
        Test that an invalid JSON5 file produces return code 1.
        """
        invalid_file = tmp_path / 'invalid.json5'
        invalid_file.write_text('{{{invalid json5')
        assert hook.main([str(invalid_file)]) == 1

    def test_nonexistent_file(self, hook: ModuleType) -> None:
        """
        Test that a nonexistent file produces return code 1.
        """
        assert hook.main(['/nonexistent/path/file.json5']) == 1

    def test_mixed_valid_and_invalid(self, hook: ModuleType, tmp_path: Path) -> None:
        """
        Test that a mix of valid and invalid files returns 1.
        """
        valid = tmp_path / 'good.json5'
        valid.write_text('{ key: "value" }')

        invalid = tmp_path / 'bad.json5'
        invalid.write_text('{{{')

        assert hook.main([str(valid), str(invalid)]) == 1

    def test_verbose_shows_valid_files(
        self,
        hook: ModuleType,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that verbose mode outputs info for valid files.
        """
        valid_file = tmp_path / 'valid.json5'
        valid_file.write_text('{ key: "value" }')

        hook.main(['-v', str(valid_file)])
        captured = capsys.readouterr()
        assert 'Valid JSON5' in captured.out

    def test_error_output_shows_filename(
        self,
        hook: ModuleType,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that error output includes the failing filename.
        """
        invalid_file = tmp_path / 'broken.json5'
        invalid_file.write_text('{{{')

        hook.main([str(invalid_file)])
        captured = capsys.readouterr()
        assert 'broken.json5' in captured.out

    def test_multiple_valid_files(self, hook: ModuleType, tmp_path: Path) -> None:
        """
        Test that multiple valid files all pass.
        """
        files: list[str] = []
        for i in range(3):
            f = tmp_path / f'file{i}.json5'
            f.write_text(f'{{ key{i}: "value{i}" }}')
            files.append(str(f))
        assert hook.main(files) == 0

    def test_valid_json5_with_comments(self, hook: ModuleType, tmp_path: Path) -> None:
        """
        Test that JSON5 with single-line and block comments returns 0.
        """
        content = '{\n  // single-line comment\n  "name": "test",\n  /* block comment */\n  "value": 1,\n}\n'
        f = tmp_path / 'commented.json5'
        f.write_text(content)
        assert hook.main([str(f)]) == 0

    def test_valid_json5_with_trailing_commas(self, hook: ModuleType, tmp_path: Path) -> None:
        """
        Test that trailing commas (a JSON5 feature) are accepted.
        """
        f = tmp_path / 'trailing.json5'
        f.write_text('{ "items": [1, 2, 3,], "nested": { "a": true, }, }')
        assert hook.main([str(f)]) == 0

    def test_valid_json5_single_quoted_strings(self, hook: ModuleType, tmp_path: Path) -> None:
        """
        Test that single-quoted strings (a JSON5 feature) are accepted.
        """
        f = tmp_path / 'single_quotes.json5'
        f.write_text("{ 'key': 'value' }")
        assert hook.main([str(f)]) == 0

    def test_invalid_json5_unclosed_brace(self, hook: ModuleType, tmp_path: Path) -> None:
        """
        Test that an unclosed brace produces return code 1.
        """
        f = tmp_path / 'unclosed.json5'
        f.write_text('{ "key": "value"')
        assert hook.main([str(f)]) == 1

    def test_invalid_json5_empty_file(self, hook: ModuleType, tmp_path: Path) -> None:
        """
        Test that an empty file produces return code 1.
        """
        f = tmp_path / 'empty.json5'
        f.write_text('')
        assert hook.main([str(f)]) == 1
