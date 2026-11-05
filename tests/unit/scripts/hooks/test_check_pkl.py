"""
Tests for the check-pkl.py pre-commit hook script.

Validates Pkl file syntax checking, argument parsing, pkl executable detection, per-file processing,
and --require-pkl / --verbose / --dump-yaml / --color / --timeout / --no-cache flags.
"""
from __future__ import annotations

import argparse
import importlib.util
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING
from typing import get_args
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

if TYPE_CHECKING:
    from types import ModuleType


HOOK_PATH = str(Path(__file__).parents[4] / 'scripts' / 'hooks' / 'check-pkl.py')

assert Path(HOOK_PATH).is_file(), (
    f'Script under test not found: {HOOK_PATH}\n'
    'Did the script move? Update HOOK_PATH in this test module.'
)


# ==================================================================================================
# Fixtures
# ==================================================================================================


def _load_module() -> ModuleType:
    """
    Load check-pkl.py via importlib.

    :return: the loaded module
    """
    spec = importlib.util.spec_from_file_location('check_pkl', HOOK_PATH)
    assert spec        is not None
    assert spec.loader is not None

    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def hook() -> ModuleType:
    """
    Return the loaded check-pkl module.
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


class TestColorOption:
    """
    Tests for the ColorOption type alias.
    """

    def test_color_option_is_literal(self, hook: ModuleType) -> None:
        """
        Test that ColorOption is a Literal type with expected values.
        """
        args = get_args(hook.ColorOption)
        assert 'never'  in args
        assert 'auto'   in args
        assert 'always' in args


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
        assert 'filenames'   in annotations
        assert 'require_pkl' in annotations
        assert 'executable'  in annotations
        assert 'verbose'     in annotations
        assert 'dump_yaml'   in annotations
        assert 'color'       in annotations
        assert 'timeout'     in annotations
        assert 'no_cache'    in annotations


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

    def test_dump_yaml_default_false(self, hook: ModuleType) -> None:
        """
        Test that --dump-yaml defaults to False.
        """
        args = hook.parse_args([])
        assert args.dump_yaml is False

    def test_dump_yaml_flag(self, hook: ModuleType) -> None:
        """
        Test that --dump-yaml flag is parsed correctly.
        """
        args = hook.parse_args(['--dump-yaml', 'file.pkl'])
        assert args.dump_yaml is True

    def test_color_default_always(self, hook: ModuleType) -> None:
        """
        Test that --color defaults to 'always'.
        """
        args = hook.parse_args([])
        assert args.color == 'always'

    def test_color_choices(self, hook: ModuleType) -> None:
        """
        Test that --color accepts all valid choices.
        """
        for choice in ('never', 'auto', 'always'):
            args = hook.parse_args(['--color', choice, 'file.pkl'])
            assert args.color == choice

    def test_timeout_default_none(self, hook: ModuleType) -> None:
        """
        Test that --timeout defaults to None.
        """
        args = hook.parse_args([])
        assert args.timeout is None

    def test_timeout_float_value(self, hook: ModuleType) -> None:
        """
        Test that --timeout accepts a float value.
        """
        args = hook.parse_args(['--timeout', '10.5', 'file.pkl'])
        assert args.timeout == 10.5

    def test_timeout_short_flag(self, hook: ModuleType) -> None:
        """
        Test that -t is a shorthand for --timeout.
        """
        args = hook.parse_args(['-t', '5', 'file.pkl'])
        assert args.timeout == 5.0

    def test_no_cache_default_false(self, hook: ModuleType) -> None:
        """
        Test that --no-cache defaults to False.
        """
        args = hook.parse_args([])
        assert args.no_cache is False

    def test_no_cache_flag(self, hook: ModuleType) -> None:
        """
        Test that --no-cache flag is parsed correctly.
        """
        args = hook.parse_args(['--no-cache', 'file.pkl'])
        assert args.no_cache is True

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

    def test_pkl_found_runs_subprocess_per_file(self, hook: ModuleType) -> None:
        """
        Test that main runs pkl eval once per file when pkl is found on PATH.
        """
        mock_result = MagicMock()
        mock_result.stdout = ''

        with (
            patch('shutil.which',   return_value='/usr/local/bin/pkl'),
            patch('subprocess.run', return_value=mock_result) as mock_run,
        ):
            result = hook.main(['a.pkl', 'b.pkl'])
        assert result == 0
        assert mock_run.call_count == 2

        first_call_args = mock_run.call_args_list[0][0][0]
        assert first_call_args[0] == 'pkl'
        assert 'eval'  in first_call_args
        assert 'a.pkl' in first_call_args

        second_call_args = mock_run.call_args_list[1][0][0]
        assert 'b.pkl' in second_call_args

    def test_pkl_eval_failure_returns_nonzero(
        self,
        hook: ModuleType,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that pkl eval failure (CalledProcessError) returns nonzero.
        """
        with (
            patch('shutil.which',   return_value='/usr/local/bin/pkl'),
            patch('subprocess.run', side_effect=subprocess.CalledProcessError(1, 'pkl', stderr='some error')),
        ):
            result = hook.main(['file.pkl'])
        assert result == 1

        captured = capsys.readouterr()
        assert 'ERROR' in captured.out

    def test_pkl_eval_failure_shows_stderr(
        self,
        hook: ModuleType,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that stderr from pkl eval failure is shown in output.
        """
        exc = subprocess.CalledProcessError(1, 'pkl', stderr='syntax error at line 5')
        with (
            patch('shutil.which',   return_value='/usr/local/bin/pkl'),
            patch('subprocess.run', side_effect=exc),
        ):
            hook.main(['file.pkl'])

        captured = capsys.readouterr()
        assert 'syntax error at line 5' in captured.out

    def test_pkl_eval_failure_strips_pkl_error_header(
        self,
        hook: ModuleType,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that the Pkl Error header line is stripped from stderr output.
        """
        stderr_with_header = '\u2013\u2013 Pkl Error \u2013\u2013\nActual error message'
        with (
            patch('shutil.which',   return_value='/usr/local/bin/pkl'),
            patch('subprocess.run', side_effect=subprocess.CalledProcessError(1, 'pkl', stderr=stderr_with_header)),
        ):
            hook.main(['file.pkl'])

        captured = capsys.readouterr()
        assert 'Actual error message' in captured.out

    def test_partial_failure_returns_nonzero(self, hook: ModuleType) -> None:
        """
        Test that if one file fails and another succeeds, main returns nonzero.
        """
        mock_result = MagicMock()
        mock_result.stdout = ''

        def run_side_effect(cmd: list[str], **_kwargs: object) -> MagicMock:
            if 'good.pkl' in cmd:
                return mock_result
            raise subprocess.CalledProcessError(1, 'pkl', stderr='error')

        with (
            patch('shutil.which',   return_value='/usr/local/bin/pkl'),
            patch('subprocess.run', side_effect=run_side_effect),
        ):
            result = hook.main(['good.pkl', 'bad.pkl'])
        assert result == 1

    def test_generic_exception_returns_nonzero(
        self,
        hook: ModuleType,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that a generic exception during subprocess execution returns nonzero.
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

    def test_verbose_shows_valid_files(
        self,
        hook: ModuleType,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that verbose mode outputs info for valid files.
        """
        mock_result = MagicMock()
        mock_result.stdout = ''

        with (
            patch('shutil.which',   return_value='/usr/local/bin/pkl'),
            patch('subprocess.run', return_value=mock_result),
        ):
            hook.main(['--verbose', 'file.pkl'])

        captured = capsys.readouterr()
        assert 'INFO'      in captured.out
        assert 'Valid Pkl' in captured.out

    def test_dump_yaml_shows_output(
        self,
        hook: ModuleType,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that --dump-yaml flag prints compiled YAML output.
        """
        mock_result = MagicMock()
        mock_result.stdout = 'key: value\n'

        with (
            patch('shutil.which',   return_value='/usr/local/bin/pkl'),
            patch('subprocess.run', return_value=mock_result),
        ):
            hook.main(['--dump-yaml', 'file.pkl'])

        captured = capsys.readouterr()
        assert 'Compiled YAML' in captured.out
        assert 'key: value'    in captured.out

    def test_color_option_passed_to_pkl(self, hook: ModuleType) -> None:
        """
        Test that --color value is passed through to the pkl command.
        """
        mock_result = MagicMock()
        mock_result.stdout = ''

        with (
            patch('shutil.which',   return_value='/usr/local/bin/pkl'),
            patch('subprocess.run', return_value=mock_result) as mock_run,
        ):
            hook.main(['--color', 'never', 'file.pkl'])

        call_args = mock_run.call_args[0][0]
        assert '--color' in call_args

        color_idx = call_args.index('--color')
        assert call_args[color_idx + 1] == 'never'

    def test_timeout_option_passed_to_pkl(self, hook: ModuleType) -> None:
        """
        Test that --timeout value is passed through to the pkl command.
        """
        mock_result = MagicMock()
        mock_result.stdout = ''

        with (
            patch('shutil.which',   return_value='/usr/local/bin/pkl'),
            patch('subprocess.run', return_value=mock_result) as mock_run,
        ):
            hook.main(['--timeout', '30', 'file.pkl'])

        call_args = mock_run.call_args[0][0]
        assert '--timeout' in call_args

        timeout_idx = call_args.index('--timeout')
        assert call_args[timeout_idx + 1] == '30.0'

    def test_no_cache_option_passed_to_pkl(self, hook: ModuleType) -> None:
        """
        Test that --no-cache flag is passed through to the pkl command.
        """
        mock_result = MagicMock()
        mock_result.stdout = ''

        with (
            patch('shutil.which',   return_value='/usr/local/bin/pkl'),
            patch('subprocess.run', return_value=mock_result) as mock_run,
        ):
            hook.main(['--no-cache', 'file.pkl'])

        call_args = mock_run.call_args[0][0]
        assert '--no-cache' in call_args

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
        mock_result.stdout = ''

        with (
            patch('shutil.which',   return_value='/custom/pkl'),
            patch('subprocess.run', return_value=mock_result) as mock_run,
        ):
            hook.main(['--executable', '/custom/pkl', 'file.pkl'])

        call_args = mock_run.call_args[0][0]
        assert call_args[0] == '/custom/pkl'

    def test_timeout_zero_passed_to_pkl(self, hook: ModuleType) -> None:
        """
        Test that --timeout 0 is correctly forwarded to pkl (not silently dropped).
        """
        mock_result = MagicMock()
        mock_result.stdout = ''

        with (
            patch('shutil.which',   return_value='/usr/local/bin/pkl'),
            patch('subprocess.run', return_value=mock_result) as mock_run,
        ):
            hook.main(['--timeout', '0', 'file.pkl'])

        call_args = mock_run.call_args[0][0]
        assert '--timeout' in call_args

    def test_no_filenames_output(self, hook: ModuleType, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that empty filenames prints a yellow message.
        """
        hook.main([])
        captured = capsys.readouterr()
        assert 'No filenames to check' in captured.out


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
