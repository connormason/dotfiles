from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

# Import from the script file directly
SCRIPT_PATH = Path(__file__).parents[4] / 'scripts' / 'env' / 'venvshell.py'

assert SCRIPT_PATH.is_file(), (
    f'Script under test not found: {SCRIPT_PATH}\n'
    'Did the script move? Update SCRIPT_PATH in this test module.'
)
sys.path.insert(0, str(SCRIPT_PATH.parent))

import venvshell
from venvshell import Args
from venvshell import Exit
from venvshell import _resolve_zsh_histfile
from venvshell import find_hatch_env
from venvshell import find_venv
from venvshell import launch_venv_shell
from venvshell import main
from venvshell import parse_args
from venvshell import resolve_bool_env_var
from venvshell import unstyle
from venvshell import validate_venv

if TYPE_CHECKING:
    from collections.abc import Iterator


# ==================================================================================================
# Fixtures
# ==================================================================================================


@pytest.fixture
def fake_venv(tmp_path: Path) -> Path:
    """
    Create a minimal fake venv directory structure.

    :return: path to the fake venv directory
    """
    venv_dir = tmp_path / '.venv'
    bin_dir  = venv_dir / 'bin'
    bin_dir.mkdir(parents=True)

    (bin_dir / 'activate').write_text('# fake activate')
    (bin_dir / 'activate.fish').write_text('# fake activate.fish')

    python_bin = bin_dir / 'python'
    python_bin.symlink_to(sys.executable)
    return venv_dir


@pytest.fixture
def project_with_venv(tmp_path: Path, fake_venv: Path) -> Path:
    """
    Create a project directory that contains a .venv.

    The ``fake_venv`` fixture already creates it under ``tmp_path/.venv``, so ``tmp_path`` acts as the project root

    :return: path to the project root
    """
    return tmp_path


@pytest.fixture(autouse=True)
def _reset_module_globals() -> Iterator[None]:
    """
    Reset venvshell module-level globals to defaults before and after each test.
    """
    venvshell.VENV_DIR_NAMES         = ['.venv', 'venv']
    venvshell.HATCH_ENABLED          = True
    venvshell.PATH_DEFAULT           = None
    venvshell.HATCH_ENV_DEFAULT      = None
    venvshell.DISCOVER_DEFAULT       = True
    venvshell.HATCH_DISCOVER_DEFAULT = True
    venvshell.VERBOSE                = False

    yield

    venvshell.VENV_DIR_NAMES         = ['.venv', 'venv']
    venvshell.HATCH_ENABLED          = True
    venvshell.PATH_DEFAULT           = None
    venvshell.HATCH_ENV_DEFAULT      = None
    venvshell.DISCOVER_DEFAULT       = True
    venvshell.HATCH_DISCOVER_DEFAULT = True
    venvshell.VERBOSE                = False


# ==================================================================================================
# Unit tests
# ==================================================================================================


class TestUnstyle:
    """
    Tests for :func:`unstyle`.
    """
    def test_removes_ansi_codes(self) -> None:
        """
        Should strip ANSI escape sequences from styled text.
        """
        styled = '\033[1m\033[31mHello\033[0m'
        assert unstyle(styled) == 'Hello'

    def test_passthrough_plain_text(self) -> None:
        """
        Should return plain text unchanged.
        """
        assert unstyle('hello world') == 'hello world'

    def test_empty_string(self) -> None:
        """
        Should handle empty string.
        """
        assert unstyle('') == ''

    def test_removes_multiple_ansi_sequences(self) -> None:
        """
        Should strip multiple ANSI codes across the string.
        """
        styled = '\033[32mgreen\033[0m and \033[34mblue\033[0m'
        assert unstyle(styled) == 'green and blue'


class TestExitException:
    """
    Tests for :class:`Exit` exception.
    """
    def test_exit_code_values(self) -> None:
        """
        Should have expected exit code values.
        """
        assert Exit.Code.SUCCESS             == 0
        assert Exit.Code.ENV_ALREADY_ACTIVE  == 0
        assert Exit.Code.EXISTING_ENV_ACTIVE == 1
        assert Exit.Code.INVALID_PARAM       == 64
        assert Exit.Code.ENV_INVALID         == 65
        assert Exit.Code.ENV_NOT_FOUND       == 69
        assert Exit.Code.ACTIVATION_FAILED   == 90

    def test_exit_with_message(self) -> None:
        """
        Should store code and message.
        """
        exc = Exit(Exit.Code.ENV_NOT_FOUND, 'not found')
        assert exc.code    == 69
        assert exc.message == 'not found'

    def test_exit_without_message(self) -> None:
        """
        Should allow None message.
        """
        exc = Exit(Exit.Code.SUCCESS)
        assert exc.code    == 0
        assert exc.message is None

    def test_exit_method_calls_sys_exit(self) -> None:
        """
        :meth:`Exit.exit` should call :func:`sys.exit` with the exit code.
        """
        exc = Exit(Exit.Code.ENV_NOT_FOUND, 'test error')
        with pytest.raises(SystemExit) as exc_info:
            exc.exit()
        assert exc_info.value.code == 69

    def test_exit_method_no_message_skips_printf(self) -> None:
        """
        :meth:`Exit.exit` should not print anything when message is None.
        """
        exc = Exit(Exit.Code.SUCCESS)
        with patch('venvshell.printf') as mock_printf, pytest.raises(SystemExit):
            exc.exit()
        mock_printf.assert_not_called()

    def test_exit_error_defaults_to_true_for_nonzero_code(self) -> None:
        """
        When error is not specified, should default to True for non-zero exit codes.
        """
        exc = Exit(Exit.Code.ENV_NOT_FOUND, 'test')
        with patch('venvshell.printf') as mock_printf, pytest.raises(SystemExit):
            exc.exit()
        mock_printf.assert_called_once()
        assert mock_printf.call_args[1]['error'] is True

    def test_exit_error_defaults_to_false_for_zero_code(self) -> None:
        """
        When error is not specified, should default to False for zero exit codes.
        """
        exc = Exit(Exit.Code.SUCCESS, 'test')
        with patch('venvshell.printf') as mock_printf, pytest.raises(SystemExit):
            exc.exit()
        mock_printf.assert_called_once()
        assert mock_printf.call_args[1]['error'] is False


class TestFindVenv:
    """
    Tests for :func:`find_venv`.
    """
    def test_finds_venv_in_start_directory(self, project_with_venv: Path) -> None:
        """
        Should find .venv in the starting directory.
        """
        result = find_venv(project_with_venv)
        assert result is not None
        assert result.name   == '.venv'
        assert result.parent == project_with_venv

    def test_finds_venv_in_parent_directory(self, project_with_venv: Path) -> None:
        """
        Should walk up and find .venv in a parent directory.
        """
        child = project_with_venv / 'src' / 'pkg'
        child.mkdir(parents=True)

        result = find_venv(child)
        assert result is not None
        assert result.name == '.venv'

    def test_finds_venv_named_venv(self, tmp_path: Path) -> None:
        """
        Should find a directory named ``venv`` (not just ``.venv``).
        """
        venv_dir = tmp_path / 'venv'
        bin_dir  = venv_dir / 'bin'
        bin_dir.mkdir(parents=True)
        (bin_dir / 'activate').write_text('# fake')

        result = find_venv(tmp_path)
        assert result is not None
        assert result.name == 'venv'

    def test_returns_none_when_no_venv(self, tmp_path: Path) -> None:
        """
        Should return None when no venv exists in the tree.
        """
        result = find_venv(tmp_path)
        assert result is None

    def test_ignores_directory_without_activate(self, tmp_path: Path) -> None:
        """
        A .venv directory without bin/activate should not be matched.
        """
        (tmp_path / '.venv' / 'bin').mkdir(parents=True)

        # No activate script
        result = find_venv(tmp_path)
        assert result is None

    def test_defaults_to_cwd(self, project_with_venv: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Should default to cwd when no start argument provided.
        """
        monkeypatch.chdir(project_with_venv)
        result = find_venv()

        assert result is not None
        assert result.name == '.venv'

    def test_custom_dir_names(self, tmp_path: Path) -> None:
        """
        Should respect custom dir_names parameter.
        """
        custom_dir = tmp_path / 'myenv'
        bin_dir    = custom_dir / 'bin'
        bin_dir.mkdir(parents=True)
        (bin_dir / 'activate').write_text('# fake')

        # Default names should not find it
        assert find_venv(tmp_path) is None

        # Custom names should find it
        result = find_venv(tmp_path, dir_names=['myenv'])
        assert result is not None
        assert result.name == 'myenv'


class TestFindHatchEnv:
    """
    Tests for :func:`find_hatch_env`.
    """
    def test_returns_path_on_success(self, fake_venv: Path) -> None:
        """
        Should return the venv path when hatch env find succeeds.
        """
        mock_result = MagicMock()
        mock_result.stdout = str(fake_venv) + '\n'

        with patch('venvshell.subprocess.run', return_value=mock_result) as mock_run:
            result = find_hatch_env('default')

        assert result == fake_venv
        mock_run.assert_called_once_with(
            ['hatch', 'env', 'find', 'default'],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )

    def test_none_env_name_omits_arg(self, fake_venv: Path) -> None:
        """
        Should omit env name argument when env_name is None.
        """
        mock_result = MagicMock()
        mock_result.stdout = str(fake_venv) + '\n'

        with patch('venvshell.subprocess.run', return_value=mock_result) as mock_run:
            result = find_hatch_env(None)

        assert result == fake_venv
        mock_run.assert_called_once_with(
            ['hatch', 'env', 'find'],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )

    def test_default_env_name_is_none(self, fake_venv: Path) -> None:
        """
        Should default to no env name argument when called without arguments.
        """
        mock_result = MagicMock()
        mock_result.stdout = str(fake_venv) + '\n'

        with patch('venvshell.subprocess.run', return_value=mock_result) as mock_run:
            find_hatch_env()

        mock_run.assert_called_once_with(
            ['hatch', 'env', 'find'],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )

    def test_returns_none_when_hatch_not_installed(self) -> None:
        """
        Should return None when hatch is not installed (FileNotFoundError).
        """
        with patch('venvshell.subprocess.run', side_effect=FileNotFoundError):
            result = find_hatch_env()
        assert result is None

    def test_returns_none_when_command_fails(self) -> None:
        """
        Should return None when hatch env find fails.
        """
        with patch('venvshell.subprocess.run', side_effect=subprocess.CalledProcessError(1, 'hatch')):
            result = find_hatch_env()
        assert result is None

    def test_returns_none_when_timeout(self) -> None:
        """
        Should return None when hatch env find times out.
        """
        with patch('venvshell.subprocess.run', side_effect=subprocess.TimeoutExpired('hatch', 10)):
            result = find_hatch_env()
        assert result is None

    def test_returns_none_when_path_not_a_directory(self, tmp_path: Path) -> None:
        """
        Should return None when hatch returns a path that is not a directory.
        """
        mock_result = MagicMock()
        mock_result.stdout = str(tmp_path / 'nonexistent') + '\n'

        with patch('venvshell.subprocess.run', return_value=mock_result):
            result = find_hatch_env()
        assert result is None

    def test_custom_env_name(self, fake_venv: Path) -> None:
        """
        Should pass custom env name to hatch command.
        """
        mock_result = MagicMock()
        mock_result.stdout = str(fake_venv) + '\n'

        with patch('venvshell.subprocess.run', return_value=mock_result) as mock_run:
            find_hatch_env('test')

        mock_run.assert_called_once_with(
            ['hatch', 'env', 'find', 'test'],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )


class TestValidateVenv:
    """
    Tests for :func:`validate_venv`.
    """
    def test_healthy_venv_returns_none(self, fake_venv: Path) -> None:
        """
        A well-formed venv should return None (no error).
        """
        assert validate_venv(fake_venv) is None

    def test_missing_python_binary(self, fake_venv: Path) -> None:
        """
        Should return error when python binary is missing.
        """
        (fake_venv / 'bin' / 'python').unlink()
        result = validate_venv(fake_venv)

        assert result is not None
        assert 'python binary not found' in result

    def test_broken_python_symlink(self, fake_venv: Path) -> None:
        """
        Should return error when python binary is a broken symlink.
        """
        python_bin = fake_venv / 'bin' / 'python'
        python_bin.unlink()
        python_bin.symlink_to('/nonexistent/python3')

        result = validate_venv(fake_venv)
        assert result is not None
        assert 'broken symlink' in result

    def test_missing_activate_script(self, fake_venv: Path) -> None:
        """
        Should return error when activate script is missing.
        """
        (fake_venv / 'bin' / 'activate').unlink()
        result = validate_venv(fake_venv)

        assert result is not None
        assert 'activate script not found' in result


class TestResolveBoolEnvVar:
    """
    Tests for :func:`resolve_bool_env_var`.
    """
    def test_returns_default_when_not_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Should return the default value when environment variable is not set.
        """
        monkeypatch.delenv('TEST_VAR', raising=False)
        assert resolve_bool_env_var('TEST_VAR', default=True)  is True
        assert resolve_bool_env_var('TEST_VAR', default=False) is False
        assert resolve_bool_env_var('TEST_VAR')                is None

    def test_true_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Should return True when env var is set to 'true'.
        """
        monkeypatch.setenv('TEST_VAR', 'true')
        assert resolve_bool_env_var('TEST_VAR') is True

    def test_false_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Should return False when env var is set to 'false'.
        """
        monkeypatch.setenv('TEST_VAR', 'false')
        assert resolve_bool_env_var('TEST_VAR') is False

    def test_case_insensitive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Should handle case-insensitive boolean values.
        """
        monkeypatch.setenv('TEST_VAR', 'TRUE')
        assert resolve_bool_env_var('TEST_VAR') is True

        monkeypatch.setenv('TEST_VAR', 'False')
        assert resolve_bool_env_var('TEST_VAR') is False

    def test_strips_whitespace(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Should strip whitespace from env var value.
        """
        monkeypatch.setenv('TEST_VAR', '  true  ')
        assert resolve_bool_env_var('TEST_VAR') is True

    def test_invalid_value_returns_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Should return default when env var has an invalid value.
        """
        monkeypatch.setenv('TEST_VAR', 'yes')
        assert resolve_bool_env_var('TEST_VAR', default=True) is True

    def test_invalid_value_prints_warning(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Should print warning to stderr for invalid env var value.
        """
        monkeypatch.setenv('TEST_VAR', 'yes')
        resolve_bool_env_var('TEST_VAR')

        captured = capsys.readouterr()
        assert 'TEST_VAR'                       in captured.err
        assert 'Ignoring invalid env var value' in unstyle(captured.err)


class TestParseArgs:
    """
    Tests for :func:`parse_args`.
    """
    def test_no_args(self) -> None:
        """
        Should parse with no arguments (all defaults).
        """
        args = parse_args([])
        assert args.path           is None
        assert args.hatch_env      is None
        assert args.discover       is True
        assert args.discover_hatch is True

    def test_positional_path(self, tmp_path: Path) -> None:
        """
        Should accept a positional path argument.
        """
        args = parse_args([str(tmp_path)])
        assert args.path == tmp_path.resolve()

    def test_path_flag(self, tmp_path: Path) -> None:
        """
        Should accept --path flag.
        """
        args = parse_args(['--path', str(tmp_path)])
        assert args.path is not None

    def test_hatch_flag(self) -> None:
        """
        --hatch with a value should use that env name.
        """
        args = parse_args(['--hatch', 'test'])
        assert args.hatch_env == 'test'

    def test_path_and_positional_mutual_exclusion(self, tmp_path: Path) -> None:
        """
        Passing both --path and a positional path should raise Exit.
        """
        with pytest.raises(Exit) as exc_info:
            parse_args(['--path', str(tmp_path), str(tmp_path)])
        assert exc_info.value.code == Exit.Code.INVALID_PARAM

    def test_hatch_and_path_mutual_exclusion(self, tmp_path: Path) -> None:
        """
        Passing both --hatch and --path should raise Exit.
        """
        with pytest.raises(Exit) as exc_info:
            parse_args(['--hatch', 'test', '--path', str(tmp_path)])
        assert exc_info.value.code == Exit.Code.INVALID_PARAM

    def test_hatch_and_positional_mutual_exclusion(self, tmp_path: Path) -> None:
        """
        Passing both --hatch and a positional path should raise Exit.
        """
        with pytest.raises(Exit) as exc_info:
            parse_args(['--hatch', 'env', str(tmp_path)])
        assert exc_info.value.code == Exit.Code.INVALID_PARAM

    def test_no_discover_flag(self) -> None:
        """
        --no-discover should set discover to False.
        """
        args = parse_args(['--no-discover'])
        assert args.discover is False

    def test_no_discover_hatch_flag(self) -> None:
        """
        --no-discover-hatch should set discover_hatch to False.
        """
        args = parse_args(['--no-discover-hatch'])
        assert args.discover_hatch is False

    def test_hatch_unavailable_when_disabled(self) -> None:
        """
        --hatch should be unrecognized when HATCH_ENABLED is False.
        """
        venvshell.HATCH_ENABLED = False
        with pytest.raises(SystemExit):
            parse_args(['--hatch', 'test'])

    def test_returns_args_instance(self) -> None:
        """
        Should return an :class:`Args` instance.
        """
        args = parse_args([])
        assert isinstance(args, Args)

    def test_path_envvar_default(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """
        Should use VENVSHELL_PATH env var as default for --path.
        """
        monkeypatch.setenv('VENVSHELL_PATH', str(tmp_path))
        args = parse_args([])
        assert args.path is not None

    def test_hatch_env_envvar_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Should use VENVSHELL_HATCH_ENV env var as default for --hatch.
        """
        monkeypatch.setenv('VENVSHELL_HATCH_ENV', 'my-env')
        args = parse_args([])
        assert args.hatch_env == 'my-env'

    def test_discover_envvar_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Should use VENVSHELL_DISCOVER env var as default for --discover.
        """
        monkeypatch.setenv('VENVSHELL_DISCOVER', 'false')
        args = parse_args([])
        assert args.discover is False

    def test_discover_hatch_envvar_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Should use VENVSHELL_DISCOVER_HATCH env var as default for --discover-hatch.
        """
        monkeypatch.setenv('VENVSHELL_DISCOVER_HATCH', 'false')
        args = parse_args([])
        assert args.discover_hatch is False

    def test_verbose_flag(self) -> None:
        """
        Should parse -v/--verbose flag.
        """
        args = parse_args(['-v'])
        assert args.verbose is True

        args = parse_args(['--verbose'])
        assert args.verbose is True

    def test_verbose_defaults_to_false(self) -> None:
        """
        Should default verbose to False when not specified.
        """
        args = parse_args([])
        assert args.verbose is False


class TestVerboseOutput:
    """
    Tests for verbose output behavior.
    """
    def test_verbose_output_suppressed_by_default(self, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Verbose printf calls should produce no output when VERBOSE is False.
        """
        venvshell.VERBOSE = False
        venvshell.printf('debug message', verbose=True)
        captured = capsys.readouterr()

        assert captured.out == ''
        assert captured.err == ''

    def test_verbose_output_to_stderr_when_enabled(self, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Verbose printf calls should print to stderr when VERBOSE is True.
        """
        venvshell.VERBOSE = True
        venvshell.printf('debug message', verbose=True)
        captured = capsys.readouterr()

        assert captured.out == ''
        assert 'debug message' in unstyle(captured.err)

    def test_main_sets_verbose_global(
        self,
        project_with_venv: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        main() should set global VERBOSE from args.verbose.
        """
        monkeypatch.chdir(project_with_venv)
        monkeypatch.setenv('SHELL',       '/bin/bash')
        monkeypatch.delenv('VIRTUAL_ENV', raising=False)
        mock_run = MagicMock()

        assert venvshell.VERBOSE is False
        with patch('venvshell.subprocess.run', mock_run):
            main(['-v'])
        assert venvshell.VERBOSE is True

    def test_raises_exit_for_invalid_venv(self, tmp_path: Path) -> None:
        """
        Should raise :class:`Exit` for a venv that fails validation.
        """
        bad_venv = tmp_path / 'bad_venv'
        bad_venv.mkdir()
        with pytest.raises(Exit) as exc_info:
            launch_venv_shell(bad_venv)
        assert exc_info.value.code == Exit.Code.ENV_INVALID

    def test_bash_creates_rcfile(self, fake_venv: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        For bash shell, should create a temp rcfile and pass --rcfile.
        """
        monkeypatch.setenv('SHELL', '/bin/bash')
        mock_run = MagicMock()

        with patch('venvshell.subprocess.run', mock_run):
            launch_venv_shell(fake_venv)

        call_args  = mock_run.call_args
        shell_args = call_args[0][0]

        assert shell_args[0] == '/bin/bash'
        assert shell_args[1] == '--rcfile'

        # The rcfile should be a real temp file path
        rcfile_path = Path(shell_args[2])
        assert 'venv_shell_' in str(rcfile_path.parent)

    def test_zsh_sets_zdotdir(self, fake_venv: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        For zsh shell, should set ZDOTDIR to temp directory in env.
        """
        monkeypatch.setenv('SHELL',   '/bin/zsh')
        monkeypatch.setenv('ZDOTDIR', str(tmp_path))
        mock_run = MagicMock()

        with (
            patch('venvshell.subprocess.run',        mock_run),
            patch('venvshell._resolve_zsh_histfile', return_value=tmp_path / '.zsh_history'),
        ):
            launch_venv_shell(fake_venv)

        call_env = mock_run.call_args[1]['env']
        assert 'venv_shell_' in call_env['ZDOTDIR']

    def test_zsh_symlinks_dotfiles(self, fake_venv: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        For zsh shell, should symlink .zshenv etc. from real ZDOTDIR.
        """
        monkeypatch.setenv('SHELL', '/bin/zsh')

        zdotdir = tmp_path / 'zdotdir'
        zdotdir.mkdir()

        (zdotdir / '.zshenv').write_text('# zshenv')
        (zdotdir / '.zprofile').write_text('# zprofile')

        monkeypatch.setenv('ZDOTDIR', str(zdotdir))
        mock_run = MagicMock()

        with (
            patch('venvshell.subprocess.run',        mock_run),
            patch('venvshell._resolve_zsh_histfile', return_value=zdotdir / '.zsh_history'),
        ):
            launch_venv_shell(fake_venv)

        tmpdir = Path(mock_run.call_args[1]['env']['ZDOTDIR'])
        assert     (tmpdir / '.zshenv').is_symlink()
        assert     (tmpdir / '.zprofile').is_symlink()
        assert     (tmpdir / '.zshrc').exists()
        assert not (tmpdir / '.zshrc').is_symlink()

    def test_fish_uses_init_command(self, fake_venv: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        For fish shell, should use -C flag with activate.fish.
        """
        monkeypatch.setenv('SHELL', '/usr/bin/fish')
        mock_run = MagicMock()

        with patch('venvshell.subprocess.run', mock_run):
            launch_venv_shell(fake_venv)

        shell_args = mock_run.call_args[0][0]
        assert shell_args[0]   == '/usr/bin/fish'
        assert shell_args[1]   == '-C'
        assert 'activate.fish' in shell_args[2]

    def test_unsupported_shell_warns(
        self,
        fake_venv: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        For unsupported shells, should print a warning and still launch.
        """
        monkeypatch.setenv('SHELL', '/bin/csh')
        mock_run = MagicMock()

        with patch('venvshell.subprocess.run', mock_run):
            launch_venv_shell(fake_venv)

        captured = capsys.readouterr()
        assert 'unsupported shell' in captured.err

    def test_env_vars_set_correctly(self, fake_venv: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Should set VIRTUAL_ENV, prepend bin to PATH, and remove PYTHONHOME.
        """
        monkeypatch.setenv('SHELL',      '/bin/bash')
        monkeypatch.setenv('PYTHONHOME', '/some/python')
        mock_run = MagicMock()

        with patch('venvshell.subprocess.run', mock_run):
            launch_venv_shell(fake_venv)

        call_env = mock_run.call_args[1]['env']
        resolved = fake_venv.resolve()

        assert call_env['VIRTUAL_ENV'] == str(resolved)
        assert call_env['PATH'].startswith(str(resolved / 'bin'))
        assert 'PYTHONHOME' not in call_env

    def test_returns_none(self, fake_venv: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Should return None (not an exit code).
        """
        monkeypatch.setenv('SHELL', '/bin/bash')
        mock_run = MagicMock()

        with patch('venvshell.subprocess.run', mock_run):
            result = launch_venv_shell(fake_venv)               # type: ignore[func-returns-value]
        assert result is None

    def test_handles_keyboard_interrupt(self, fake_venv: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Should gracefully handle KeyboardInterrupt during shell execution.
        """
        monkeypatch.setenv('SHELL', '/bin/bash')
        with patch('venvshell.subprocess.run', side_effect=KeyboardInterrupt):
            launch_venv_shell(fake_venv)       # Should not raise

    def test_handles_called_process_error(self, fake_venv: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Should gracefully handle CalledProcessError from check=True.
        """
        monkeypatch.setenv('SHELL', '/bin/bash')
        with patch('venvshell.subprocess.run', side_effect=subprocess.CalledProcessError(1, 'bash')):
            launch_venv_shell(fake_venv)       # Should not raise

    def test_custom_bash_dotfiles(self, fake_venv: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Should use custom bash_dotfiles when provided.
        """
        monkeypatch.setenv('SHELL', '/bin/bash')
        mock_run = MagicMock()

        with patch('venvshell.subprocess.run', mock_run):
            launch_venv_shell(fake_venv, bash_dotfiles=['.my_bashrc'])

        shell_args     = mock_run.call_args[0][0]
        rcfile_path    = Path(shell_args[2])
        rcfile_content = rcfile_path.read_text()
        assert '.my_bashrc' in rcfile_content


class TestMain:
    """
    Integration tests for :func:`main`.
    """
    def test_auto_discovers_venv(self, project_with_venv: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Should auto-discover .venv and launch shell.
        """
        monkeypatch.chdir(project_with_venv)
        monkeypatch.setenv('SHELL',       '/bin/bash')
        monkeypatch.delenv('VIRTUAL_ENV', raising=False)
        mock_run = MagicMock()

        with patch('venvshell.subprocess.run', mock_run):
            main([])

    def test_explicit_path_positional(self, fake_venv: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Should accept a positional path to a venv.
        """
        monkeypatch.setenv('SHELL',       '/bin/bash')
        monkeypatch.delenv('VIRTUAL_ENV', raising=False)
        mock_run = MagicMock()

        with patch('venvshell.subprocess.run', mock_run):
            main([str(fake_venv)])

    def test_explicit_path_flag(self, fake_venv: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Should accept --path flag with path to a venv.
        """
        monkeypatch.setenv('SHELL',       '/bin/bash')
        monkeypatch.delenv('VIRTUAL_ENV', raising=False)
        mock_run = MagicMock()

        with patch('venvshell.subprocess.run', mock_run):
            main(['--path', str(fake_venv)])

    def test_explicit_path_nonexistent_raises_exit(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Should raise Exit when explicit path does not exist.
        """
        monkeypatch.delenv('VIRTUAL_ENV', raising=False)
        with pytest.raises(Exit) as exc_info:
            main(['--path', str(tmp_path / 'nonexistent')])
        assert exc_info.value.code == Exit.Code.ENV_NOT_FOUND

    def test_explicit_path_is_file_raises_exit(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Should raise Exit when explicit path is a file, not a directory.
        """
        file_path = tmp_path / 'not_a_dir'
        file_path.write_text('not a venv')
        monkeypatch.delenv('VIRTUAL_ENV', raising=False)

        with pytest.raises(Exit) as exc_info:
            main(['--path', str(file_path)])
        assert exc_info.value.code == Exit.Code.ENV_INVALID

    def test_no_venv_found_raises_exit(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Should raise Exit when no venv is found anywhere.
        """
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv('VIRTUAL_ENV', raising=False)

        with (
            patch('venvshell.find_hatch_env', return_value=None),
            pytest.raises(Exit) as exc_info,
        ):
            main([])
        assert exc_info.value.code == Exit.Code.ENV_NOT_FOUND

    def test_hatch_fallback(self, tmp_path: Path, fake_venv: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Should fall back to hatch when no venv/.venv found.
        """
        empty_dir = tmp_path / 'empty_project'
        empty_dir.mkdir()
        monkeypatch.chdir(empty_dir)
        monkeypatch.setenv('SHELL',       '/bin/bash')
        monkeypatch.delenv('VIRTUAL_ENV', raising=False)

        mock_run = MagicMock()
        with (
            patch('venvshell.find_hatch_env', return_value=fake_venv),
            patch('venvshell.subprocess.run', mock_run),
        ):
            main([])

    def test_hatch_explicit(self, fake_venv: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Should use --hatch flag to find hatch environment.
        """
        monkeypatch.setenv('SHELL',       '/bin/bash')
        monkeypatch.delenv('VIRTUAL_ENV', raising=False)

        mock_run = MagicMock()
        with (
            patch('venvshell.find_hatch_env', return_value=fake_venv) as mock_find,
            patch('venvshell.subprocess.run', mock_run),
        ):
            main(['--hatch', 'test'])

        mock_find.assert_called_once_with('test')

    def test_hatch_explicit_not_found_raises_exit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Should raise Exit when --hatch env is not found.
        """
        monkeypatch.delenv('VIRTUAL_ENV', raising=False)
        with (
            patch('venvshell.find_hatch_env', return_value=None),
            pytest.raises(Exit) as exc_info,
        ):
            main(['--hatch', 'nonexistent'])
        assert exc_info.value.code == Exit.Code.ENV_NOT_FOUND

    def test_already_active_same_env(
        self,
        project_with_venv: Path,
        fake_venv: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Should raise Exit with code 0 when the target env is already active.
        """
        monkeypatch.chdir(project_with_venv)
        monkeypatch.setenv('SHELL',       '/bin/bash')
        monkeypatch.setenv('VIRTUAL_ENV', str(fake_venv.resolve()))

        with pytest.raises(Exit) as exc_info:
            main([])
        assert exc_info.value.code == Exit.Code.ENV_ALREADY_ACTIVE

    def test_already_active_different_env(
        self,
        project_with_venv: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Should raise Exit with code 1 when a different env is already active.
        """
        monkeypatch.chdir(project_with_venv)
        monkeypatch.setenv('SHELL',       '/bin/bash')
        monkeypatch.setenv('VIRTUAL_ENV', '/some/other/venv')

        with pytest.raises(Exit) as exc_info:
            main([])
        assert exc_info.value.code == Exit.Code.EXISTING_ENV_ACTIVE

    def test_no_discover_flag_skips_auto_discovery(
        self, project_with_venv: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        --no-discover should prevent auto-discovery even when a venv exists.
        """
        monkeypatch.chdir(project_with_venv)
        monkeypatch.delenv('VIRTUAL_ENV', raising=False)

        with pytest.raises(Exit) as exc_info:
            main(['--no-discover'])
        assert exc_info.value.code == Exit.Code.ENV_NOT_FOUND

    def test_no_discover_hatch_skips_hatch_fallback(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        --no-discover-hatch should prevent hatch fallback discovery.
        """
        empty_dir = tmp_path / 'empty_project'
        empty_dir.mkdir()
        monkeypatch.chdir(empty_dir)
        monkeypatch.delenv('VIRTUAL_ENV', raising=False)

        with patch('venvshell.find_hatch_env') as mock_hatch, pytest.raises(Exit):
            main(['--no-discover-hatch'])

        mock_hatch.assert_not_called()

    def test_discover_envvar_disables_discovery(
        self,
        project_with_venv: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        VENVSHELL_DISCOVER=false should prevent auto-discovery.
        """
        monkeypatch.chdir(project_with_venv)
        monkeypatch.delenv('VIRTUAL_ENV',        raising=False)
        monkeypatch.setenv('VENVSHELL_DISCOVER', 'false')

        with pytest.raises(Exit) as exc_info:
            main([])
        assert exc_info.value.code == Exit.Code.ENV_NOT_FOUND

    def test_discover_hatch_envvar_disables_hatch_fallback(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        VENVSHELL_DISCOVER_HATCH=false should prevent hatch fallback.
        """
        empty_dir = tmp_path / 'empty_project'
        empty_dir.mkdir()
        monkeypatch.chdir(empty_dir)
        monkeypatch.delenv('VIRTUAL_ENV',              raising=False)
        monkeypatch.setenv('VENVSHELL_DISCOVER_HATCH', 'false')

        with patch('venvshell.find_hatch_env') as mock_hatch, pytest.raises(Exit):
            main([])

        mock_hatch.assert_not_called()

    def test_hatch_env_envvar_default(
        self,
        fake_venv: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        VENVSHELL_HATCH_ENV env var should set the default --hatch env name.
        """
        monkeypatch.setenv('SHELL',               '/bin/bash')
        monkeypatch.setenv('VENVSHELL_HATCH_ENV', 'custom-env')
        monkeypatch.delenv('VIRTUAL_ENV',         raising=False)

        mock_run = MagicMock()
        with (
            patch('venvshell.find_hatch_env', return_value=fake_venv) as mock_find,
            patch('venvshell.subprocess.run', mock_run),
        ):
            main([])

        mock_find.assert_called_once_with('custom-env')

    def test_no_venv_message_omits_hatch_when_disabled(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Error message should not mention --hatch when HATCH_ENABLED is False.
        """
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv('VIRTUAL_ENV', raising=False)
        venvshell.HATCH_ENABLED = False

        with pytest.raises(Exit):
            main([])

        captured = capsys.readouterr()
        assert '--hatch' not in captured.err

    def test_no_venv_message_includes_hatch_when_enabled(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Error message should mention --hatch when hatch is enabled.
        """
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv('VIRTUAL_ENV', raising=False)

        with patch('venvshell.find_hatch_env', return_value=None), pytest.raises(Exit):
            main([])

        captured = capsys.readouterr()
        assert '--hatch' in captured.err


class TestResolveZshHistfile:
    """
    Tests for :func:`_resolve_zsh_histfile`.
    """
    def test_returns_histfile_from_clean_output(self) -> None:
        """
        Should extract HISTFILE path from clean zsh output without escape codes.
        """
        mock_result = MagicMock()
        mock_result.stdout = '/Users/testuser/.zsh_history\n'

        with patch('venvshell.subprocess.run', return_value=mock_result):
            result = _resolve_zsh_histfile('/bin/zsh', default=Path('/fallback/.zsh_history'))

        assert result == Path('/Users/testuser/.zsh_history')

    def test_strips_osc_escape_sequences(self) -> None:
        """
        Should strip OSC escape sequences (shell integration) from output.
        """
        mock_result = MagicMock()
        mock_result.stdout = (
            '\x1b]1337;RemoteHost=user@host\x07'
            '\x1b]1337;CurrentDir=/home/user\x07'
            '\x1b]1337;ShellIntegrationVersion=14;shell=zsh\x07'
            '/Users/testuser/.zsh_history\n'
        )

        with patch('venvshell.subprocess.run', return_value=mock_result):
            result = _resolve_zsh_histfile('/bin/zsh', default=Path('/fallback'))

        assert result == Path('/Users/testuser/.zsh_history')

    def test_strips_ansi_csi_sequences(self) -> None:
        """
        Should strip ANSI CSI escape sequences from output.
        """
        mock_result = MagicMock()
        mock_result.stdout = '\x1b[32m/Users/testuser/.zsh_history\x1b[0m\n'

        with patch('venvshell.subprocess.run', return_value=mock_result):
            result = _resolve_zsh_histfile('/bin/zsh', default=Path('/fallback'))

        assert result == Path('/Users/testuser/.zsh_history')

    def test_returns_default_on_timeout(self) -> None:
        """
        Should return default path when zsh subprocess times out.
        """
        default = Path('/home/user/.zsh_history')

        with patch('venvshell.subprocess.run', side_effect=subprocess.TimeoutExpired('zsh', 5)):
            result = _resolve_zsh_histfile('/bin/zsh', default=default)

        assert result == default

    def test_returns_default_on_file_not_found(self) -> None:
        """
        Should return default path when shell binary is not found.
        """
        default = Path('/home/user/.zsh_history')

        with patch('venvshell.subprocess.run', side_effect=FileNotFoundError):
            result = _resolve_zsh_histfile('/nonexistent/zsh', default=default)

        assert result == default

    def test_returns_default_on_os_error(self) -> None:
        """
        Should return default path on general OS errors.
        """
        default = Path('/home/user/.zsh_history')

        with patch('venvshell.subprocess.run', side_effect=OSError('permission denied')):
            result = _resolve_zsh_histfile('/bin/zsh', default=default)

        assert result == default

    def test_returns_default_on_empty_output(self) -> None:
        """
        Should return default path when subprocess produces empty output.
        """
        mock_result = MagicMock()
        mock_result.stdout = '\n'
        default = Path('/home/user/.zsh_history')

        with patch('venvshell.subprocess.run', return_value=mock_result):
            result = _resolve_zsh_histfile('/bin/zsh', default=default)

        assert result == default

    def test_returns_default_when_output_is_not_absolute_path(self) -> None:
        """
        Should return default when output doesn't start with /.
        """
        mock_result = MagicMock()
        mock_result.stdout = 'relative/path/.zsh_history\n'
        default = Path('/home/user/.zsh_history')

        with patch('venvshell.subprocess.run', return_value=mock_result):
            result = _resolve_zsh_histfile('/bin/zsh', default=default)

        assert result == default

    def test_custom_histfile_location(self) -> None:
        """
        Should handle non-standard HISTFILE locations.
        """
        mock_result = MagicMock()
        mock_result.stdout = '/Users/testuser/.local/share/zsh/history\n'

        with patch('venvshell.subprocess.run', return_value=mock_result):
            result = _resolve_zsh_histfile('/bin/zsh', default=Path('/fallback'))

        assert result == Path('/Users/testuser/.local/share/zsh/history')

    def test_passes_correct_command_to_subprocess(self) -> None:
        """
        Should invoke zsh with -ic flag and echo HISTFILE.
        """
        mock_result = MagicMock()
        mock_result.stdout = '/Users/testuser/.zsh_history\n'

        with patch('venvshell.subprocess.run', return_value=mock_result) as mock_run:
            _resolve_zsh_histfile('/bin/zsh', default=Path('/fallback'))

        mock_run.assert_called_once_with(
            ['/bin/zsh', '-ic', 'echo "$HISTFILE"'],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )

    def test_custom_timeout(self) -> None:
        """
        Should pass custom timeout to subprocess.
        """
        mock_result = MagicMock()
        mock_result.stdout = '/Users/testuser/.zsh_history\n'

        with patch('venvshell.subprocess.run', return_value=mock_result) as mock_run:
            _resolve_zsh_histfile('/bin/zsh', default=Path('/fallback'), timeout=10)

        assert mock_run.call_args[1]['timeout'] == 10


class TestLaunchVenvShellHistfilePreservation:
    """
    Tests for HISTFILE preservation in :func:`launch_venv_shell` zsh code path.
    """
    def test_zsh_zshrc_contains_histfile_override(
        self,
        fake_venv: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Custom .zshrc for zsh should contain a HISTFILE= line to preserve history.
        """
        monkeypatch.setenv('SHELL', '/bin/zsh')

        zdotdir = tmp_path / 'zdotdir'
        zdotdir.mkdir()
        (zdotdir / '.zshrc').write_text('# real zshrc')
        monkeypatch.setenv('ZDOTDIR', str(zdotdir))

        mock_run = MagicMock()
        resolved_histfile = Path('/Users/testuser/.zsh_history')

        with (
            patch('venvshell.subprocess.run',        mock_run),
            patch('venvshell._resolve_zsh_histfile', return_value=resolved_histfile),
        ):
            launch_venv_shell(fake_venv)

        tmpdir        = Path(mock_run.call_args[1]['env']['ZDOTDIR'])
        zshrc_content = (tmpdir / '.zshrc').read_text()
        assert f'HISTFILE={resolved_histfile}' in zshrc_content

    def test_zsh_histfile_override_is_last_line(
        self,
        fake_venv: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        HISTFILE override should come after sourcing user config and venv activate.
        """
        monkeypatch.setenv('SHELL', '/bin/zsh')

        zdotdir = tmp_path / 'zdotdir'
        zdotdir.mkdir()
        (zdotdir / '.zshrc').write_text('# real zshrc')
        monkeypatch.setenv('ZDOTDIR', str(zdotdir))

        mock_run = MagicMock()
        resolved_histfile = Path('/Users/testuser/.zsh_history')

        with (
            patch('venvshell.subprocess.run',        mock_run),
            patch('venvshell._resolve_zsh_histfile', return_value=resolved_histfile),
        ):
            launch_venv_shell(fake_venv)

        tmpdir      = Path(mock_run.call_args[1]['env']['ZDOTDIR'])
        zshrc_lines = (tmpdir / '.zshrc').read_text().strip().splitlines()

        # HISTFILE line should be the last line
        assert zshrc_lines[-1].startswith('HISTFILE=')
        assert str(resolved_histfile) in zshrc_lines[-1]

        # source .zshrc and source activate should come before
        source_lines: list[str] = [line for line in zshrc_lines if 'source' in line]
        assert len(source_lines) == 2  # user .zshrc + activate

    def test_zsh_calls_resolve_histfile_with_correct_args(
        self,
        fake_venv: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Should call _resolve_zsh_histfile with the shell path and real ZDOTDIR-based default.
        """
        monkeypatch.setenv('SHELL', '/bin/zsh')

        zdotdir = tmp_path / 'zdotdir'
        zdotdir.mkdir()
        (zdotdir / '.zshrc').write_text('# real zshrc')
        monkeypatch.setenv('ZDOTDIR', str(zdotdir))

        mock_run = MagicMock()

        with (
            patch('venvshell.subprocess.run',        mock_run),
            patch('venvshell._resolve_zsh_histfile', return_value=Path('/fallback')) as mock_resolve,
        ):
            launch_venv_shell(fake_venv)

        mock_resolve.assert_called_once_with(
            '/bin/zsh',
            default=zdotdir / '.zsh_history',
        )

    def test_bash_not_affected_by_histfile_fix(
        self,
        fake_venv: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Bash code path should not call _resolve_zsh_histfile.
        """
        monkeypatch.setenv('SHELL', '/bin/bash')
        mock_run = MagicMock()

        with (
            patch('venvshell.subprocess.run', mock_run),
            patch('venvshell._resolve_zsh_histfile') as mock_resolve,
        ):
            launch_venv_shell(fake_venv)

        mock_resolve.assert_not_called()
