"""
Tests for the format-pkl.py pre-commit hook script.

Validates Pkl file formatting, argument parsing, pkl executable detection, per-file processing with
--diff-name-only / --write flow, and --require-pkl / --verbose / --grammar-version flags.
"""
from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from typing import get_args
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

# Import functions and classes from run.py
sys.path.insert(0, str(Path(__file__).parents[4]))

from run import unstyle

if TYPE_CHECKING:
    from types import ModuleType


HOOK_PATH = str(Path(__file__).parents[4] / 'scripts' / 'hooks' / 'format-pkl.py')

assert Path(HOOK_PATH).is_file(), (
    f'Script under test not found: {HOOK_PATH}\n'
    'Did the script move? Update HOOK_PATH in this test module.'
)


# ==================================================================================================
# Fixtures
# ==================================================================================================


def _load_module() -> ModuleType:
    """
    Load format-pkl.py via importlib.

    :return: the loaded module
    """
    spec = importlib.util.spec_from_file_location('format_pkl', HOOK_PATH)
    assert spec        is not None
    assert spec.loader is not None

    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def hook() -> ModuleType:
    """
    Return the loaded format-pkl module.
    """
    return _load_module()


# ==================================================================================================
# Unit tests
# ==================================================================================================


class TestGrammarVersion:
    """
    Tests for the GrammarVersion type alias.
    """

    def test_grammar_version_is_literal(self, hook: ModuleType) -> None:
        """
        Test that GrammarVersion is a Literal type with expected values.
        """
        args = get_args(hook.GrammarVersion)
        assert 1 in args
        assert 2 in args

    def test_default_grammar_version(self, hook: ModuleType) -> None:
        """
        Test that DEFAULT_GRAMMAR_VERSION is 2.
        """
        assert hook.DEFAULT_GRAMMAR_VERSION == 2


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
        Test that Args declares all expected annotations.
        """
        annotations = hook.Args.__annotations__
        assert 'filenames'       in annotations
        assert 'require_pkl'     in annotations
        assert 'executable'      in annotations
        assert 'grammar_version' in annotations
        assert 'verbose'         in annotations


class TestParseArgs:
    """
    Tests for the parse_args() function.
    """

    def test_filenames_parsed(self, hook: ModuleType) -> None:
        """
        Test that positional filenames are parsed correctly.
        """
        args = hook.parse_args(['a.pkl', 'b.pkl'])
        assert args.filenames == ['a.pkl', 'b.pkl']

    def test_no_filenames(self, hook: ModuleType) -> None:
        """
        Test that empty argv produces empty filenames list.
        """
        args = hook.parse_args([])
        assert args.filenames == []

    def test_require_pkl_default_false(self, hook: ModuleType) -> None:
        """
        Test that --require-pkl defaults to False.
        """
        args = hook.parse_args([])
        assert args.require_pkl is False

    def test_require_pkl_flag(self, hook: ModuleType) -> None:
        """
        Test that --require-pkl flag is parsed correctly.
        """
        args = hook.parse_args(['--require-pkl', 'file.pkl'])
        assert args.require_pkl is True

    def test_executable_default(self, hook: ModuleType) -> None:
        """
        Test that --executable defaults to 'pkl'.
        """
        args = hook.parse_args([])
        assert args.executable == 'pkl'

    def test_executable_custom(self, hook: ModuleType) -> None:
        """
        Test that --executable accepts a custom path.
        """
        args = hook.parse_args(['--executable', '/usr/local/bin/pkl', 'file.pkl'])
        assert args.executable == '/usr/local/bin/pkl'

    def test_grammar_version_default(self, hook: ModuleType) -> None:
        """
        Test that --grammar-version defaults to 2.
        """
        args = hook.parse_args([])
        assert args.grammar_version == 2

    def test_grammar_version_choices(self, hook: ModuleType) -> None:
        """
        Test that --grammar-version accepts valid choices.
        """
        for version in (1, 2):
            args = hook.parse_args(['--grammar-version', str(version), 'file.pkl'])
            assert args.grammar_version == version

    def test_verbose_default_false(self, hook: ModuleType) -> None:
        """
        Test that --verbose defaults to False.
        """
        args = hook.parse_args([])
        assert args.verbose is False

    def test_verbose_flag_short(self, hook: ModuleType) -> None:
        """
        Test that -v enables verbose mode.
        """
        args = hook.parse_args(['-v', 'file.pkl'])
        assert args.verbose is True

    def test_verbose_flag_long(self, hook: ModuleType) -> None:
        """
        Test that --verbose enables verbose mode.
        """
        args = hook.parse_args(['--verbose', 'file.pkl'])
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

    def test_no_filenames_returns_zero(self, hook: ModuleType, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that main returns 0 when no filenames are provided.
        """
        assert hook.main([]) == 0

        captured = capsys.readouterr()
        assert 'No filenames to format' in captured.out

    def test_pkl_not_found_default_returns_zero(
        self,
        hook: ModuleType,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that missing pkl executable returns 0 by default (warning only).
        """
        with patch('shutil.which', return_value=None):
            result = hook.main(['file.pkl'])
        assert result == 0

        captured = capsys.readouterr()
        assert 'WARNING'              in captured.out
        assert 'Executable not found' in captured.out

    def test_pkl_not_found_require_pkl_returns_one(
        self,
        hook: ModuleType,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that missing pkl executable with --require-pkl returns 1.
        """
        with patch('shutil.which', return_value=None):
            result = hook.main(['--require-pkl', 'file.pkl'])
        assert result == 1

        captured = capsys.readouterr()
        assert 'ERROR'     in captured.out
        assert 'not found' in captured.out

    def test_pkl_not_found_warning_shows_install_url(
        self,
        hook: ModuleType,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that the pkl installation URL is shown when pkl is not found.
        """
        with patch('shutil.which', return_value=None):
            hook.main(['file.pkl'])

        captured = capsys.readouterr()
        assert 'pkl-lang.org' in captured.out

    def test_already_formatted_file_returns_zero(self, hook: ModuleType) -> None:
        """
        Test that a file already correctly formatted returns 0 (no subprocess error).
        """
        mock_result = MagicMock()
        mock_result.returncode = 0

        with (
            patch('shutil.which',   return_value='/usr/local/bin/pkl'),
            patch('subprocess.run', return_value=mock_result),
        ):
            result = hook.main(['file.pkl'])
        assert result == 0

    def test_unformatted_file_triggers_write(self, hook: ModuleType, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that a file needing formatting (exit code 11) triggers pkl format --write.
        """
        diff_exc = subprocess.CalledProcessError(11, 'pkl')
        write_result = MagicMock()
        write_result.returncode = 0

        call_count = 0

        def run_side_effect(cmd: list[str], **_kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise diff_exc
            return write_result

        with (
            patch('shutil.which',   return_value='/usr/local/bin/pkl'),
            patch('subprocess.run', side_effect=run_side_effect) as mock_run,
        ):
            result = hook.main(['file.pkl'])

        # The file was reformatted, so the hook should succeed
        # (exit code 0) and print MODIFIED
        assert result              == 0
        assert mock_run.call_count == 2

        # First call: --diff-name-only (check)
        first_cmd = mock_run.call_args_list[0][0][0]
        assert '--diff-name-only' in first_cmd
        assert '--write'      not in first_cmd

        # Second call: --diff-name-only --write (apply)
        second_cmd = mock_run.call_args_list[1][0][0]
        assert '--write' in second_cmd

        captured = capsys.readouterr()
        assert 'MODIFIED' in captured.out

    def test_verbose_shows_unmodified_files(
        self,
        hook: ModuleType,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that verbose mode outputs UNMODIFIED for already-formatted files.
        """
        mock_result = MagicMock()
        mock_result.returncode = 0

        with (
            patch('shutil.which',   return_value='/usr/local/bin/pkl'),
            patch('subprocess.run', return_value=mock_result),
        ):
            hook.main(['--verbose', 'file.pkl'])

        captured = capsys.readouterr()
        assert 'UNMODIFIED' in captured.out

    def test_pkl_eval_failure_returns_nonzero(
        self,
        hook: ModuleType,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that a non-11 CalledProcessError returns the error's exit code.
        """
        with (
            patch('shutil.which',   return_value='/usr/local/bin/pkl'),
            patch('subprocess.run', side_effect=subprocess.CalledProcessError(2, 'pkl', stderr='parse error')),
        ):
            result = hook.main(['file.pkl'])
        assert result == 2

        captured = capsys.readouterr()
        assert 'ERROR' in captured.out

    def test_pkl_failure_shows_stderr(
        self,
        hook: ModuleType,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that stderr from pkl failure is shown in output.
        """
        exc = subprocess.CalledProcessError(2, 'pkl', stderr='syntax error at line 5')
        with (
            patch('shutil.which',   return_value='/usr/local/bin/pkl'),
            patch('subprocess.run', side_effect=exc),
        ):
            hook.main(['file.pkl'])

        captured = capsys.readouterr()
        assert 'syntax error at line 5' in captured.out

    def test_pkl_failure_strips_generic_error_header(
        self,
        hook: ModuleType,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that the generic 'An error occurred during formatting.' line is stripped from stderr.
        """
        stderr = 'An error occurred during formatting.\nActual error detail'
        with (
            patch('shutil.which',   return_value='/usr/local/bin/pkl'),
            patch('subprocess.run', side_effect=subprocess.CalledProcessError(2, 'pkl', stderr=stderr)),
        ):
            hook.main(['file.pkl'])

        captured = capsys.readouterr()
        assert 'An error occurred during formatting.' not in captured.out
        assert 'Actual error detail' in captured.out

    def test_partial_failure_returns_max_retval(self, hook: ModuleType) -> None:
        """
        Test that if one file fails and another succeeds, main returns the highest error code.
        """
        mock_result = MagicMock()
        mock_result.returncode = 0

        def run_side_effect(cmd: list[str], **_kwargs: object) -> MagicMock:
            if 'good.pkl' in cmd:
                return mock_result
            raise subprocess.CalledProcessError(3, 'pkl', stderr='error')

        with (
            patch('shutil.which',   return_value='/usr/local/bin/pkl'),
            patch('subprocess.run', side_effect=run_side_effect),
        ):
            result = hook.main(['good.pkl', 'bad.pkl'])
        assert result == 3

    def test_generic_exception_returns_one(
        self,
        hook: ModuleType,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that a generic exception during subprocess execution returns 1.
        """
        with (
            patch('shutil.which',   return_value='/usr/local/bin/pkl'),
            patch('subprocess.run', side_effect=OSError('permission denied')),
        ):
            result = hook.main(['file.pkl'])
        assert result == 1

        captured = capsys.readouterr()
        assert 'ERROR'             in captured.out
        assert 'permission denied' in captured.out

    def test_custom_executable_used_in_which_check(self, hook: ModuleType) -> None:
        """
        Test that --executable value is passed to shutil.which.
        """
        with patch('shutil.which', return_value=None) as mock_which:
            hook.main(['--executable', '/custom/pkl', 'file.pkl'])
        mock_which.assert_called_once_with('/custom/pkl')

    def test_custom_executable_used_in_subprocess(self, hook: ModuleType) -> None:
        """
        Test that --executable value is used as the command in subprocess.run.
        """
        mock_result = MagicMock()
        mock_result.returncode = 0

        with (
            patch('shutil.which',   return_value='/custom/pkl'),
            patch('subprocess.run', return_value=mock_result) as mock_run,
        ):
            hook.main(['--executable', '/custom/pkl', 'file.pkl'])

        call_args = mock_run.call_args[0][0]
        assert call_args[0] == '/custom/pkl'

    def test_grammar_version_passed_to_pkl(self, hook: ModuleType) -> None:
        """
        Test that --grammar-version value is passed through to the pkl command.
        """
        mock_result = MagicMock()
        mock_result.returncode = 0

        with (
            patch('shutil.which',   return_value='/usr/local/bin/pkl'),
            patch('subprocess.run', return_value=mock_result) as mock_run,
        ):
            hook.main(['--grammar-version', '1', 'file.pkl'])

        call_args = mock_run.call_args[0][0]
        assert '--grammar-version' in call_args

        gv_idx = call_args.index('--grammar-version')
        assert call_args[gv_idx + 1] == '1'

    def test_multiple_files_processed(self, hook: ModuleType) -> None:
        """
        Test that main processes all provided files.
        """
        mock_result = MagicMock()
        mock_result.returncode = 0

        with (
            patch('shutil.which',   return_value='/usr/local/bin/pkl'),
            patch('subprocess.run', return_value=mock_result) as mock_run,
        ):
            result = hook.main(['a.pkl', 'b.pkl', 'c.pkl'])

        assert result == 0
        assert mock_run.call_count == 3

    def test_write_failure_after_diff_returns_error(
        self,
        hook: ModuleType,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that a failure during the --write step still returns an error.
        """
        call_count = 0

        def run_side_effect(cmd: list[str], **_kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise subprocess.CalledProcessError(11, 'pkl')

            # Write step also fails
            raise subprocess.CalledProcessError(1, 'pkl', stderr='write failed')

        with (
            patch('shutil.which',   return_value='/usr/local/bin/pkl'),
            patch('subprocess.run', side_effect=run_side_effect),
        ):
            result = hook.main(['file.pkl'])

        assert result >= 1

        captured = capsys.readouterr()
        assert 'ERROR' in captured.out


class TestLabelConstants:
    """
    Tests for pre-rendered ANSI label constants.
    """

    def test_error_label_contains_error(self, hook: ModuleType) -> None:
        """
        Test that ERROR label contains the word ERROR.
        """
        assert 'ERROR' in unstyle(hook.ERROR)

    def test_warning_label_contains_warning(self, hook: ModuleType) -> None:
        """
        Test that WARNING label contains the word WARNING.
        """
        assert 'WARNING' in unstyle(hook.WARNING)

    def test_modified_label_contains_modified(self, hook: ModuleType) -> None:
        """
        Test that MODIFIED label contains the word MODIFIED.
        """
        assert 'MODIFIED' in unstyle(hook.MODIFIED)

    def test_unmodified_label_contains_unmodified(self, hook: ModuleType) -> None:
        """
        Test that UNMODIFIED label contains the word UNMODIFIED.
        """
        assert 'UNMODIFIED' in unstyle(hook.UNMODIFIED)


class TestPklInstallationDocsUrl:
    """
    Tests for the PKL_INSTALLATION_DOCS_URL constant.
    """

    def test_url_is_string(self, hook: ModuleType) -> None:
        """
        Test that PKL_INSTALLATION_DOCS_URL is a string.
        """
        assert isinstance(hook.PKL_INSTALLATION_DOCS_URL, str)

    def test_url_points_to_pkl_docs(self, hook: ModuleType) -> None:
        """
        Test that the URL points to pkl-lang.org.
        """
        assert 'pkl-lang.org' in hook.PKL_INSTALLATION_DOCS_URL
