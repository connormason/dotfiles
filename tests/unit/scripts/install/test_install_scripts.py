"""
Unit tests for scripts/install/install_uv.py and scripts/install/install_hatch.py.

Both installer scripts share an identical interface and structure; their testable seams -- argument parsing, styling
helpers, shell detection, executable lookup, installer download/execution, the pip fallback, verification, and the
top-level ``main`` flow -- are exercised against both modules via the parametrized ``installer`` fixture. Tool-specific
behavior (the installer command, the urllib User-Agent header, installer URLs) is asserted where it diverges.

Network and subprocess boundaries are mocked; ``time.sleep`` is patched so retry paths run instantly.
"""
from __future__ import annotations

import importlib.util
import ssl
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from typing import NamedTuple

import pytest
from typing_extensions import Self

if TYPE_CHECKING:
    from types import ModuleType

# ==================================================================================================
# Filepaths and module loading
# ==================================================================================================


INSTALL_DIR: Path = Path(__file__).parents[4] / 'scripts' / 'install'

INSTALLER_SCRIPTS: dict[str, Path] = {
    'uv':    INSTALL_DIR / 'install_uv.py',
    'hatch': INSTALL_DIR / 'install_hatch.py',
}

for _tool, _path in INSTALLER_SCRIPTS.items():
    assert _path.is_file(), (
        f'Installer script under test not found: {_path}\n'
        'Did the script move? Update INSTALLER_SCRIPTS in this test module.'
    )


def _load_installer(tool: str) -> ModuleType:
    """
    Load an installer script as an importable module by filepath.

    The scripts are not part of a package, so :mod:`importlib` is used to load them directly. A fresh module object is
    returned on every call, which isolates module-level mutable state (``VERBOSE``, ``PIP_INSTALL_LOCATIONS``) between
    tests.

    :param tool: tool key (``'uv'`` or ``'hatch'``) selecting which installer script to load
    :return: the loaded module object
    """
    path = INSTALLER_SCRIPTS[tool]
    spec = importlib.util.spec_from_file_location(f'install_{tool}', path)
    assert spec         is not None
    assert spec.loader  is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ==================================================================================================
# Fixtures and helpers
# ==================================================================================================


@pytest.fixture(params=sorted(INSTALLER_SCRIPTS))
def installer(request: pytest.FixtureRequest) -> tuple[str, ModuleType]:
    """
    Provide each installer module paired with its bare-command tool name.

    :param request: pytest request supplying the parametrized tool key
    :return: tuple of (tool name, loaded installer module)
    """
    tool = request.param
    return tool, _load_installer(tool)


def _completed(
    *,
    args: Any = None,
    returncode: int = 0,
    stdout: str = '',
    stderr: str = '',
) -> subprocess.CompletedProcess[str]:
    """
    Build a :class:`subprocess.CompletedProcess` for stubbing ``subprocess.run``.

    :param args: command args recorded on the result (defaults to a placeholder list)
    :param returncode: process return code
    :param stdout: captured standard output
    :param stderr: captured standard error
    :return: a populated completed-process instance
    """
    return subprocess.CompletedProcess(args=args or ['cmd'], returncode=returncode, stdout=stdout, stderr=stderr)


class _FakeResponse:
    """
    Minimal stand-in for the context manager returned by :func:`urllib.request.urlopen`.
    """
    def __init__(self, data: bytes) -> None:
        self._data = data

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def read(self) -> bytes:
        """
        Return the canned response body.

        :return: response bytes
        """
        return self._data


# ==================================================================================================
# Color / styling helpers
# ==================================================================================================


class TestInterpretColor:
    """
    Tests for the _interpret_color helper.
    """
    def test_named_color_resolves_to_code(self, installer: tuple[str, ModuleType]) -> None:
        """
        Verify a named foreground color resolves to its ANSI code as a string.
        """
        _tool, mod = installer
        assert mod._interpret_color('red') == '31'

    def test_named_color_with_background_offset(self, installer: tuple[str, ModuleType]) -> None:
        """
        Verify the background offset of 10 is applied to a named color.
        """
        _tool, mod = installer
        assert mod._interpret_color('red', 10) == '41'

    def test_integer_color_uses_256_color_sequence(self, installer: tuple[str, ModuleType]) -> None:
        """
        Verify an integer color produces a 256-color SGR parameter string.
        """
        _tool, mod = installer
        assert mod._interpret_color(196) == '38;5;196'

    def test_rgb_tuple_uses_truecolor_sequence(self, installer: tuple[str, ModuleType]) -> None:
        """
        Verify an (r, g, b) tuple produces a 24-bit truecolor SGR parameter string.
        """
        _tool, mod = installer
        assert mod._interpret_color((10, 20, 30)) == '38;2;10;20;30'


class TestStyle:
    """
    Tests for the style helper.
    """
    def test_plain_text_is_wrapped_with_reset(self, installer: tuple[str, ModuleType]) -> None:
        """
        Verify styled text ends with the reset-all sequence by default.
        """
        _tool, mod = installer
        result = mod.style('hello', fg='red')
        assert 'hello' in result
        assert result.endswith(mod.ANSI_RESET_ALL)

    def test_reset_can_be_disabled(self, installer: tuple[str, ModuleType]) -> None:
        """
        Verify reset=False omits the trailing reset-all sequence.
        """
        _tool, mod = installer
        result = mod.style('hello', fg='red', reset=False)
        assert not result.endswith(mod.ANSI_RESET_ALL)

    def test_non_string_input_is_coerced(self, installer: tuple[str, ModuleType]) -> None:
        """
        Verify a non-string value is coerced to its string form before styling.
        """
        _tool, mod = installer
        assert '123' in mod.style(123, fg='green')

    def test_unknown_color_raises_type_error(self, installer: tuple[str, ModuleType]) -> None:
        """
        Verify an unknown color name raises TypeError.
        """
        _tool, mod = installer
        with pytest.raises(TypeError):
            mod.style('hello', fg='not_a_color')

    def test_bold_disabled_emits_normal_intensity(self, installer: tuple[str, ModuleType]) -> None:
        """
        Verify bold=False emits the normal-intensity (22) code rather than bold (1).
        """
        _tool, mod = installer
        assert '\033[22m' in mod.style('x', bold=False)


class TestFoldUser:
    """
    Tests for the folduser helper.
    """
    def test_home_is_replaced_with_tilde(self, installer: tuple[str, ModuleType]) -> None:
        """
        Verify the user's home directory prefix is folded to ``~``.
        """
        _tool, mod = installer
        sample = Path.home() / 'projects' / 'thing'
        assert mod.folduser(sample) == '~/projects/thing'

    def test_path_outside_home_is_unchanged(self, installer: tuple[str, ModuleType]) -> None:
        """
        Verify a path outside the home directory is returned verbatim.
        """
        _tool, mod = installer
        assert mod.folduser('/usr/local/bin/tool') == '/usr/local/bin/tool'


class TestTypeStyle:
    """
    Tests for the typestyle helper.
    """
    @pytest.mark.parametrize('value', [None, True, False, 7, 3.5, 'text', Path('/tmp/x')])
    def test_returns_string_containing_value(self, installer: tuple[str, ModuleType], value: Any) -> None:
        """
        Verify typestyle renders each supported type to a string containing its representation.
        """
        _tool, mod = installer
        result = mod.typestyle(value)
        assert isinstance(result, str)
        assert result != ''

    def test_sequence_is_rendered_with_brackets(self, installer: tuple[str, ModuleType]) -> None:
        """
        Verify a sequence is rendered with bracket delimiters around its styled items.
        """
        _tool, mod = installer
        result = mod.typestyle(['a', 'b'])
        assert '[' in result
        assert ']' in result


class TestAnnotatedOptHelp:
    """
    Tests for the annotated_opt_help helper.
    """
    def test_choices_and_default_are_appended(self, installer: tuple[str, ModuleType]) -> None:
        """
        Verify choices, default, and env var annotations are appended to the help text.
        """
        _tool, mod = installer
        result = mod.annotated_opt_help(
            'Core help text',
            choices=['a', 'b'],
            default='a',
            envvar='SOME_VAR',
        )
        assert 'Core help text' in result
        assert 'choices:'       in result
        assert 'default:'       in result
        assert 'env var:'       in result
        assert 'SOME_VAR'       in result

    def test_extra_help_lines_are_included(self, installer: tuple[str, ModuleType]) -> None:
        """
        Verify additional help lines are included between the core help text and annotations.
        """
        _tool, mod = installer
        result = mod.annotated_opt_help('Core', 'Extra detail line')
        assert 'Extra detail line' in result


class TestPrintf:
    """
    Tests for the printf helper.
    """
    def test_verbose_suppressed_when_global_off(
        self,
        installer: tuple[str, ModuleType],
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Verify verbose output is suppressed when the module-level VERBOSE flag is False.
        """
        _tool, mod = installer
        monkeypatch.setattr(mod, 'VERBOSE', False)
        mod.printf('hidden', verbose=True)

        captured = capsys.readouterr()
        assert 'hidden' not in captured.out
        assert 'hidden' not in captured.err

    def test_verbose_emitted_to_stderr_when_global_on(
        self,
        installer: tuple[str, ModuleType],
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Verify verbose output is routed to stderr when VERBOSE is True.
        """
        _tool, mod = installer
        monkeypatch.setattr(mod, 'VERBOSE', True)
        mod.printf('shown', verbose=True)

        captured = capsys.readouterr()
        assert 'shown'     in captured.err
        assert 'shown' not in captured.out

    def test_non_verbose_goes_to_stdout(
        self,
        installer: tuple[str, ModuleType],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Verify ordinary output is written to stdout.
        """
        _tool, mod = installer
        mod.printf('normal')
        assert 'normal' in capsys.readouterr().out


# ==================================================================================================
# Enums
# ==================================================================================================


class TestExitCodes:
    """
    Tests for the ExitCode enum shared by both installer scripts.
    """
    def test_not_found_exit_code_is_7(self, installer: tuple[str, ModuleType]) -> None:
        """
        Verify the NOT_FOUND exit code resolves to 7.
        """
        _tool, mod = installer
        assert int(mod.ExitCode.NOT_FOUND) == 7

    def test_success_and_already_installed_are_zero(self, installer: tuple[str, ModuleType]) -> None:
        """
        Verify both SUCCESS and ALREADY_INSTALLED resolve to exit code 0.
        """
        _tool, mod = installer
        assert int(mod.ExitCode.SUCCESS)           == 0
        assert int(mod.ExitCode.ALREADY_INSTALLED) == 0


class TestDownloadMethod:
    """
    Tests for the DownloadMethod enum.
    """
    def test_str_returns_bare_value(self, installer: tuple[str, ModuleType]) -> None:
        """
        Verify ``str(DownloadMethod)`` returns the bare value without the enum prefix.
        """
        _tool, mod = installer
        assert str(mod.DownloadMethod.CURL)   == 'curl'
        assert str(mod.DownloadMethod.URLLIB) == 'urllib'

    def test_default_methods_try_curl_first(self, installer: tuple[str, ModuleType]) -> None:
        """
        Verify the default download method order tries curl before urllib.
        """
        _tool, mod = installer
        assert mod.DEFAULT_DOWNLOAD_METHODS == (mod.DownloadMethod.CURL, mod.DownloadMethod.URLLIB)


# ==================================================================================================
# Argument parsing
# ==================================================================================================


class TestParseArgs:
    """
    Tests for parse_args.
    """
    def test_defaults(self, installer: tuple[str, ModuleType]) -> None:
        """
        Verify the default flag and download-option values.
        """
        _tool, mod = installer
        args = mod.parse_args([])

        assert args.force      is False
        assert args.ensure     is False
        assert args.verbose    is False
        assert args.print_path is False

        assert args.timeout          == mod.DOWNLOAD_TIMEOUT
        assert args.retries          == mod.DOWNLOAD_RETRIES
        assert args.retry_delay      == mod.DOWNLOAD_RETRY_DELAY
        assert args.download_methods == list(mod.DEFAULT_DOWNLOAD_METHODS)

    @pytest.mark.parametrize('flag', ['-f', '--force'])
    def test_force_flag(self, installer: tuple[str, ModuleType], flag: str) -> None:
        """
        Verify the force flag enables forced reinstall.
        """
        _tool, mod = installer
        assert mod.parse_args([flag]).force is True

    @pytest.mark.parametrize('flag', ['-e', '--ensure'])
    def test_ensure_flag(self, installer: tuple[str, ModuleType], flag: str) -> None:
        """
        Verify the ensure flag enables presence-check mode.
        """
        _tool, mod = installer
        assert mod.parse_args([flag]).ensure is True

    @pytest.mark.parametrize('flag', ['-v', '--verbose'])
    def test_verbose_flag_sets_global(self, installer: tuple[str, ModuleType], flag: str) -> None:
        """
        Verify the verbose flag sets both the namespace attribute and the module-level VERBOSE global.
        """
        _tool, mod = installer
        args = mod.parse_args([flag])
        assert args.verbose is True
        assert mod.VERBOSE  is True

    def test_download_option_values_are_parsed(self, installer: tuple[str, ModuleType]) -> None:
        """
        Verify numeric download options are parsed to their typed values.
        """
        _tool, mod = installer
        args = mod.parse_args(['--timeout', '12.5', '--retries', '5', '--retry-delay', '3'])

        assert args.timeout     == 12.5
        assert args.retries     == 5
        assert args.retry_delay == 3.0

    def test_download_method_order_is_preserved(self, installer: tuple[str, ModuleType]) -> None:
        """
        Verify multiple --download-method values are parsed into an ordered list of enum members.
        """
        _tool, mod = installer
        args = mod.parse_args(['--download-method', 'urllib', 'curl'])
        assert args.download_methods == [mod.DownloadMethod.URLLIB, mod.DownloadMethod.CURL]

    def test_help_exits_zero(self, installer: tuple[str, ModuleType]) -> None:
        """
        Verify --help exits with code 0.
        """
        _tool, mod = installer
        with pytest.raises(SystemExit) as exc_info:
            mod.parse_args(['--help'])
        assert exc_info.value.code == 0

    @pytest.mark.parametrize(
        'argv',
        [
            ['--timeout',     '-1'],
            ['--retries',     '0'],
            ['--retry-delay', '-1'],
        ],
    )
    def test_invalid_download_parameters_exit(self, installer: tuple[str, ModuleType], argv: list[str]) -> None:
        """
        Verify out-of-range download parameters exit with INVALID_PARAMETERS.
        """
        _tool, mod = installer
        with pytest.raises(SystemExit) as exc_info:
            mod.parse_args(argv)
        assert exc_info.value.code == mod.ExitCode.INVALID_PARAMETERS

    def test_force_and_ensure_are_mutually_exclusive(self, installer: tuple[str, ModuleType]) -> None:
        """
        Verify combining --force and --ensure exits with INVALID_PARAMETERS.
        """
        _tool, mod = installer
        with pytest.raises(SystemExit) as exc_info:
            mod.parse_args(['--force', '--ensure'])
        assert exc_info.value.code == mod.ExitCode.INVALID_PARAMETERS


class TestPrintPathArgument:
    """
    Tests for the --print-path command-line option.
    """
    def test_print_path_defaults_to_false(self, installer: tuple[str, ModuleType]) -> None:
        """
        Verify --print-path is absent by default.
        """
        _tool, mod = installer
        args = mod.parse_args([])
        assert args.print_path is False

    @pytest.mark.parametrize('flag', ['-p', '--print-path'])
    def test_print_path_flag_sets_attribute(self, installer: tuple[str, ModuleType], flag: str) -> None:
        """
        Verify both the short and long --print-path flags enable the attribute.
        """
        _tool, mod = installer
        args = mod.parse_args([flag])
        assert args.print_path is True


# ==================================================================================================
# Python version check
# ==================================================================================================


class TestCheckPythonVersion:
    """
    Tests for check_python_version.
    """
    def test_current_python_meets_minimum(self, installer: tuple[str, ModuleType]) -> None:
        """
        Verify the running interpreter satisfies the bootstrap minimum.
        """
        _tool, mod = installer
        assert mod.check_python_version() is True

    def test_below_minimum_returns_false(
        self,
        installer: tuple[str, ModuleType],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Verify an interpreter below MIN_PYTHON reports a failed version check.
        """
        _tool, mod = installer

        class _VersionInfo(NamedTuple):
            major: int
            minor: int
            micro: int

        monkeypatch.setattr(mod.sys, 'version_info', _VersionInfo(3, 0, 0))
        assert mod.check_python_version() is False


# ==================================================================================================
# Shell detection & path mapping
# ==================================================================================================


class TestShellDetect:
    """
    Tests for Shell.detect.
    """
    @pytest.mark.parametrize(
        ('shell_env', 'expected_name'),
        [
            ('/bin/bash',          'bash'),
            ('/usr/local/bin/zsh', 'zsh'),
            ('/usr/bin/fish',      'fish'),
            ('/bin/tcsh',          'tcsh'),
            ('/bin/csh',           'csh'),
        ],
    )
    def test_known_shells(
        self,
        installer: tuple[str, ModuleType],
        monkeypatch: pytest.MonkeyPatch,
        shell_env: str,
        expected_name: str,
    ) -> None:
        """
        Verify Shell.detect maps a known $SHELL value to the right Shell member.
        """
        _tool, mod = installer
        monkeypatch.setenv('SHELL', shell_env)

        result = mod.Shell.detect()
        assert result is not None
        assert result.value == expected_name

    def test_unrecognized_shell_returns_none(
        self,
        installer: tuple[str, ModuleType],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Verify an unrecognized $SHELL value yields None.
        """
        _tool, mod = installer
        monkeypatch.setenv('SHELL', '/usr/bin/nu')
        assert mod.Shell.detect() is None

    def test_unset_shell_returns_none(
        self,
        installer: tuple[str, ModuleType],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Verify a missing $SHELL value yields None.
        """
        _tool, mod = installer
        monkeypatch.delenv('SHELL', raising=False)
        assert mod.Shell.detect() is None


class TestShellRcFile:
    """
    Tests for the Shell.rc_file property.
    """
    @pytest.mark.parametrize(
        ('member_name', 'expected_suffix'),
        [
            ('ZSH',  '.zshrc'),
            ('FISH', 'config.fish'),
            ('TCSH', '.tcshrc'),
            ('CSH',  '.cshrc'),
        ],
    )
    def test_rc_file_maps_to_expected_path(
        self,
        installer: tuple[str, ModuleType],
        member_name: str,
        expected_suffix: str,
    ) -> None:
        """
        Verify each shell maps to its conventional RC file.
        """
        _tool, mod = installer
        rc_file = mod.Shell[member_name].rc_file
        assert rc_file.name == expected_suffix or str(rc_file).endswith(expected_suffix)

    def test_bash_prefers_bash_profile_on_darwin(
        self,
        installer: tuple[str, ModuleType],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Verify bash resolves to ~/.bash_profile on macOS when that file exists.
        """
        _tool, mod = installer
        monkeypatch.setattr(mod.platform, 'system', lambda: 'Darwin')
        monkeypatch.setattr(mod.Path,     'exists', lambda self: True)
        assert mod.Shell.BASH.rc_file.name == '.bash_profile'

    def test_bash_uses_bashrc_when_profile_absent(
        self,
        installer: tuple[str, ModuleType],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Verify bash falls back to ~/.bashrc when ~/.bash_profile does not exist.
        """
        _tool, mod = installer
        monkeypatch.setattr(mod.platform, 'system', lambda: 'Darwin')
        monkeypatch.setattr(mod.Path,     'exists', lambda self: False)
        assert mod.Shell.BASH.rc_file.name == '.bashrc'


class TestShellPathExportCommand:
    """
    Tests for the Shell.path_export_command method.
    """
    @pytest.mark.parametrize(
        ('member_name', 'expected_prefix'),
        [
            ('BASH', 'export PATH='),
            ('ZSH',  'export PATH='),
            ('FISH', 'set -gx PATH'),
            ('TCSH', 'setenv PATH'),
            ('CSH',  'setenv PATH'),
        ],
    )
    def test_export_syntax_matches_shell(
        self,
        installer: tuple[str, ModuleType],
        member_name: str,
        expected_prefix: str,
    ) -> None:
        """
        Verify each shell emits its own PATH export syntax.
        """
        _tool, mod = installer
        command = mod.Shell[member_name].path_export_command('/opt/tool/bin')
        assert command.startswith(expected_prefix)
        assert '/opt/tool/bin' in command


# ==================================================================================================
# Executable discovery
# ==================================================================================================


class TestInstallLocations:
    """
    Tests for get_common_install_locations.
    """
    def test_homebrew_location_present(self, installer: tuple[str, ModuleType]) -> None:
        """
        Verify the Apple-silicon Homebrew prefix is among the common install locations.
        """
        tool, mod = installer
        locations = mod.get_common_install_locations()
        assert Path(f'/opt/homebrew/bin/{tool}') in locations

    def test_registered_pip_locations_are_appended(self, installer: tuple[str, ModuleType]) -> None:
        """
        Verify locations registered by the pip fallback are appended to the common locations.
        """
        tool, mod = installer
        registered = Path(f'/some/scripts/dir/{tool}')
        mod.PIP_INSTALL_LOCATIONS.append(registered)
        assert registered in mod.get_common_install_locations()


class TestFindExecutable:
    """
    Tests for find_executable.
    """
    def test_returns_path_when_tool_on_path(
        self,
        installer: tuple[str, ModuleType],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Verify find_executable returns the bare command and version when the tool is on PATH.
        """
        tool, mod = installer
        monkeypatch.setattr(
            mod.subprocess,
            'run',
            lambda *a, **k: _completed(stdout=f'{tool} 1.2.3\n'),
        )

        executable, version = mod.find_executable()
        assert executable == tool
        assert version is not None
        assert '1.2.3' in version

    def test_returns_none_when_not_found(
        self,
        installer: tuple[str, ModuleType],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Verify find_executable returns (None, None) when the tool is missing everywhere.
        """
        _tool, mod = installer

        def _raise(*_a: object, **_k: object) -> None:
            raise FileNotFoundError

        monkeypatch.setattr(mod.subprocess, 'run',                          _raise)
        monkeypatch.setattr(mod,            'get_common_install_locations', list)

        executable, version = mod.find_executable()
        assert executable is None
        assert version    is None

    def test_falls_back_to_common_location(
        self,
        installer: tuple[str, ModuleType],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """
        Verify find_executable returns a concrete location when the tool is absent from PATH but present on disk.
        """
        tool, mod = installer
        fake_exe = tmp_path / tool
        fake_exe.write_text('#!/bin/sh\n')

        calls: list[list[str]] = []

        def _run(cmd: list[str], **_k: object) -> subprocess.CompletedProcess[str]:
            calls.append(cmd)
            if cmd[0] == tool:
                raise FileNotFoundError
            return _completed(stdout=f'{tool} 9.9.9\n')

        monkeypatch.setattr(mod.subprocess, 'run',                          _run)
        monkeypatch.setattr(mod,            'get_common_install_locations', lambda: [fake_exe])

        executable, version = mod.find_executable()
        assert executable == str(fake_exe)
        assert version is not None
        assert '9.9.9' in version


class TestFindExecutablePathOnly:
    """
    Tests for the path_only argument of find_executable.
    """
    def test_path_only_skips_common_locations(
        self,
        installer: tuple[str, ModuleType],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Verify path_only=True does not scan broad install locations when the tool is absent from PATH.
        """
        tool, mod = installer

        def _raise(*_args: object, **_kwargs: object) -> None:
            raise FileNotFoundError(tool)

        scanned = False

        def _track_locations() -> list[Path]:
            nonlocal scanned
            scanned = True
            return []

        monkeypatch.setattr(mod.subprocess, 'run',                          _raise)
        monkeypatch.setattr(mod,            'get_common_install_locations', _track_locations)

        executable, version = mod.find_executable(path_only=True)
        assert executable is None
        assert version    is None
        assert scanned    is False

    def test_non_path_only_scans_common_locations(
        self,
        installer: tuple[str, ModuleType],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Verify path_only=False falls back to scanning broad install locations.
        """
        tool, mod = installer

        def _raise(*_args: object, **_kwargs: object) -> None:
            raise FileNotFoundError(tool)

        scanned = False

        def _track_locations() -> list[Path]:
            nonlocal scanned
            scanned = True
            return []

        monkeypatch.setattr(mod.subprocess, 'run',                          _raise)
        monkeypatch.setattr(mod,            'get_common_install_locations', _track_locations)

        mod.find_executable(path_only=False)
        assert scanned is True


class TestIsInstalled:
    """
    Tests for is_installed.
    """
    def test_returns_true_when_tool_works(
        self,
        installer: tuple[str, ModuleType],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Verify is_installed returns True when find_executable yields a path.
        """
        tool, mod = installer
        monkeypatch.setattr(mod, 'find_executable', lambda **_k: (tool, '1.0.0'))
        assert mod.is_installed(quiet=True) is True

    def test_returns_false_when_not_found(
        self,
        installer: tuple[str, ModuleType],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Verify is_installed returns False when the tool is not found.
        """
        _tool, mod = installer
        monkeypatch.setattr(mod, 'find_executable', lambda **_k: (None, None))
        assert mod.is_installed(quiet=True) is False

    def test_reports_off_path_location(
        self,
        installer: tuple[str, ModuleType],
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Verify a non-quiet check prints the discovered off-PATH location and a PATH hint.
        """
        tool, mod = installer
        monkeypatch.setattr(mod, 'find_executable', lambda **_k: (f'/opt/homebrew/bin/{tool}', '1.0.0'))
        assert mod.is_installed(quiet=False) is True

        out = capsys.readouterr().out
        assert 'Found at:' in out
        assert 'PATH'      in out


class TestIsInstalledPathOnly:
    """
    Tests that is_installed forwards path_only to find_executable.
    """
    @pytest.mark.parametrize('path_only', [True, False])
    def test_path_only_is_forwarded(
        self,
        installer: tuple[str, ModuleType],
        monkeypatch: pytest.MonkeyPatch,
        path_only: bool,
    ) -> None:
        """
        Verify is_installed passes its path_only argument through to find_executable.
        """
        _tool, mod = installer
        received: dict[str, bool] = {}

        def _fake_find(*, path_only: bool = False) -> tuple[None, None]:
            received['path_only'] = path_only
            return None, None

        monkeypatch.setattr(mod, 'find_executable', _fake_find)

        assert mod.is_installed(quiet=True, path_only=path_only) is False
        assert received['path_only'] is path_only


class TestPrintExecutablePath:
    """
    Tests for print_executable_path query mode.
    """
    def test_exits_not_found_when_absent(
        self,
        installer: tuple[str, ModuleType],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Verify a missing executable exits with the NOT_FOUND code.
        """
        _tool, mod = installer
        monkeypatch.setattr(mod, 'find_executable', lambda *a, **k: (None, None))

        with pytest.raises(SystemExit) as exc_info:
            mod.print_executable_path()
        assert exc_info.value.code == mod.ExitCode.NOT_FOUND

    def test_prints_concrete_path_and_exits_success(
        self,
        installer: tuple[str, ModuleType],
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Verify a concrete location is printed verbatim to stdout with a SUCCESS exit.
        """
        tool, mod = installer
        concrete  = f'/opt/homebrew/bin/{tool}'
        monkeypatch.setattr(mod, 'find_executable', lambda *a, **k: (concrete, '1.0.0'))

        with pytest.raises(SystemExit) as exc_info:
            mod.print_executable_path()

        assert exc_info.value.code == mod.ExitCode.SUCCESS
        assert capsys.readouterr().out.strip() == concrete

    def test_bare_command_is_expanded_via_which(
        self,
        installer: tuple[str, ModuleType],
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Verify a PATH-resolved bare command is expanded to an absolute path before printing.
        """
        tool, mod = installer
        resolved  = f'/usr/local/bin/{tool}'
        monkeypatch.setattr(mod,        'find_executable', lambda *a, **k: (tool, '1.0.0'))
        monkeypatch.setattr(mod.shutil, 'which',           lambda _name: resolved)

        with pytest.raises(SystemExit) as exc_info:
            mod.print_executable_path()
        assert exc_info.value.code == mod.ExitCode.SUCCESS
        assert capsys.readouterr().out.strip() == resolved

    def test_unresolvable_bare_command_exits_not_found(
        self,
        installer: tuple[str, ModuleType],
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Verify a bare command that shutil.which cannot resolve exits NOT_FOUND instead of printing the bare name.
        """
        tool, mod = installer
        monkeypatch.setattr(mod,        'find_executable', lambda *a, **k: (tool, '1.0.0'))
        monkeypatch.setattr(mod.shutil, 'which',           lambda _name: None)

        with pytest.raises(SystemExit) as exc_info:
            mod.print_executable_path()
        assert exc_info.value.code == mod.ExitCode.NOT_FOUND

        # Nothing degraded should leak to stdout; the bare command name must not be emitted as if it were a path.
        assert capsys.readouterr().out.strip() == ''


# ==================================================================================================
# Installer URL & download
# ==================================================================================================


class TestGetInstallerUrl:
    """
    Tests for get_installer_url.
    """
    def test_returns_https_url_on_darwin(
        self,
        installer: tuple[str, ModuleType],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Verify an HTTPS installer URL is returned on macOS.
        """
        _tool, mod = installer
        monkeypatch.setattr(mod.platform, 'system', lambda: 'Darwin')
        url = mod.get_installer_url()
        assert url.startswith('https://')

    def test_raises_on_non_darwin(
        self,
        installer: tuple[str, ModuleType],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Verify a non-macOS platform raises OSError.
        """
        _tool, mod = installer
        monkeypatch.setattr(mod.platform, 'system', lambda: 'Linux')
        with pytest.raises(OSError, match='macOS'):
            mod.get_installer_url()


class TestWriteInstaller:
    """
    Tests for write_installer.
    """
    def test_writes_bytes_to_disk(self, installer: tuple[str, ModuleType], tmp_path: Path) -> None:
        """
        Verify installer bytes are written to the destination and success is reported.
        """
        _tool, mod = installer
        dest = tmp_path / 'installer.sh'
        assert mod.write_installer(dest, b'payload') is True
        assert dest.read_bytes() == b'payload'

    def test_reports_failure_on_oserror(
        self,
        installer: tuple[str, ModuleType],
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Verify a write failure returns False and prints troubleshooting guidance.
        """
        _tool, mod = installer

        # A directory path cannot be opened for writing as a file
        assert mod.write_installer(tmp_path, b'payload') is False
        assert 'Troubleshooting' in capsys.readouterr().err


class TestDownloadWithUrllib:
    """
    Tests for download_with_urllib.
    """
    def test_successful_download_writes_file(
        self,
        installer: tuple[str, ModuleType],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """
        Verify a successful urllib download writes the response body to disk.
        """
        _tool, mod = installer
        dest = tmp_path / 'installer'
        monkeypatch.setattr(mod.urllib.request, 'urlopen', lambda *a, **k: _FakeResponse(b'script-body'))

        assert mod.download_with_urllib('https://example.test/x', dest) is True
        assert dest.read_bytes() == b'script-body'

    def test_ssl_error_aborts_immediately(
        self,
        installer: tuple[str, ModuleType],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """
        Verify an SSL verification error aborts without consuming the remaining retries.
        """
        _tool, mod = installer
        calls = 0

        def _raise_ssl(*_a: object, **_k: object) -> None:
            nonlocal calls
            calls += 1
            raise mod.urllib.error.URLError(reason=ssl.SSLError('bad cert'))

        monkeypatch.setattr(mod.urllib.request, 'urlopen', _raise_ssl)
        monkeypatch.setattr(mod.time,           'sleep',   lambda _s: None)

        assert mod.download_with_urllib('https://example.test/x', tmp_path / 'd', retries=3) is False
        assert calls == 1

    def test_transient_error_exhausts_retries(
        self,
        installer: tuple[str, ModuleType],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """
        Verify a non-SSL URLError is retried up to the configured limit before failing.
        """
        _tool, mod = installer
        calls = 0

        def _raise_transient(*_a: object, **_k: object) -> None:
            nonlocal calls
            calls += 1
            raise mod.urllib.error.URLError(reason=OSError('connection reset'))

        monkeypatch.setattr(mod.urllib.request, 'urlopen', _raise_transient)
        monkeypatch.setattr(mod.time,           'sleep',   lambda _s: None)

        assert mod.download_with_urllib('https://example.test/x', tmp_path / 'd', retries=3) is False
        assert calls == 3


class TestDownloadWithCurl:
    """
    Tests for download_with_curl.
    """
    def test_returns_false_when_curl_missing(
        self,
        installer: tuple[str, ModuleType],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """
        Verify the curl path short-circuits to False when curl is not on PATH.
        """
        _tool, mod = installer
        monkeypatch.setattr(mod.shutil, 'which', lambda _name: None)
        assert mod.download_with_curl('https://example.test/x', tmp_path / 'd') is False

    def test_successful_download_returns_true(
        self,
        installer: tuple[str, ModuleType],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """
        Verify a successful curl invocation returns True.
        """
        _tool, mod = installer
        monkeypatch.setattr(mod.shutil,     'which', lambda _name: '/usr/bin/curl')
        monkeypatch.setattr(mod.subprocess, 'run',   lambda *a, **k: _completed())
        assert mod.download_with_curl('https://example.test/x', tmp_path / 'd') is True

    def test_failure_exhausts_retries(
        self,
        installer: tuple[str, ModuleType],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """
        Verify a repeatedly failing curl invocation is retried up to the limit before failing.
        """
        _tool, mod = installer
        calls = 0

        def _fail(*_a: object, **_k: object) -> None:
            nonlocal calls
            calls += 1
            raise subprocess.CalledProcessError(returncode=1, cmd=['curl'], stderr='boom')

        monkeypatch.setattr(mod.shutil,     'which', lambda _name: '/usr/bin/curl')
        monkeypatch.setattr(mod.subprocess, 'run',   _fail)
        monkeypatch.setattr(mod.time,       'sleep', lambda _s: None)

        assert mod.download_with_curl('https://example.test/x', tmp_path / 'd', retries=2) is False
        assert calls == 2


class TestDownloadInstaller:
    """
    Tests for download_installer (method dispatch and fallback).
    """
    def test_rejects_non_http_url(self, installer: tuple[str, ModuleType], tmp_path: Path) -> None:
        """
        Verify a non-HTTP(S) URL raises ValueError.
        """
        _tool, mod = installer
        with pytest.raises(ValueError, match='http'):
            mod.download_installer('ftp://example.test/x', tmp_path / 'd')

    def test_falls_back_to_next_method(
        self,
        installer: tuple[str, ModuleType],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """
        Verify a failed first method falls back to the next configured method.
        """
        _tool, mod = installer
        attempts: list[str] = []

        def _curl(*_a: object, **_k: object) -> bool:
            attempts.append('curl')
            return False

        def _urllib(*_a: object, **_k: object) -> bool:
            attempts.append('urllib')
            return True

        monkeypatch.setitem(mod.DOWNLOAD_FUNCS, mod.DownloadMethod.CURL,   _curl)
        monkeypatch.setitem(mod.DOWNLOAD_FUNCS, mod.DownloadMethod.URLLIB, _urllib)

        assert mod.download_installer('https://example.test/x', tmp_path / 'd') is True
        assert attempts == ['curl', 'urllib']

    def test_empty_methods_uses_defaults(
        self,
        installer: tuple[str, ModuleType],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """
        Verify an empty methods list falls back to the default method order.
        """
        _tool, mod = installer
        used: list[str] = []

        def _curl(*_a: object, **_k: object) -> bool:
            used.append('curl')
            return True

        def _urllib(*_a: object, **_k: object) -> bool:
            used.append('urllib')
            return True

        monkeypatch.setitem(mod.DOWNLOAD_FUNCS, mod.DownloadMethod.CURL,   _curl)
        monkeypatch.setitem(mod.DOWNLOAD_FUNCS, mod.DownloadMethod.URLLIB, _urllib)

        assert mod.download_installer('https://example.test/x', tmp_path / 'd', methods=[]) is True
        assert used == ['curl']

    def test_returns_false_when_all_methods_fail(
        self,
        installer: tuple[str, ModuleType],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """
        Verify download_installer returns False once every method has failed.
        """
        _tool, mod = installer
        monkeypatch.setitem(mod.DOWNLOAD_FUNCS, mod.DownloadMethod.CURL,   lambda *a, **k: False)
        monkeypatch.setitem(mod.DOWNLOAD_FUNCS, mod.DownloadMethod.URLLIB, lambda *a, **k: False)
        assert mod.download_installer('https://example.test/x', tmp_path / 'd') is False


class TestRunInstaller:
    """
    Tests for run_installer.
    """
    def test_success_returns_true(
        self,
        installer: tuple[str, ModuleType],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Verify a successful installer invocation returns True.
        """
        _tool, mod = installer
        monkeypatch.setattr(mod.subprocess, 'run', lambda *a, **k: _completed(stdout='ok'))
        assert mod.run_installer('/tmp/installer') is True

    def test_failure_returns_false(
        self,
        installer: tuple[str, ModuleType],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Verify a failing installer invocation returns False.
        """
        _tool, mod = installer

        def _fail(*_a: object, **_k: object) -> None:
            raise subprocess.CalledProcessError(returncode=1, cmd=['installer'], stderr='nope')

        monkeypatch.setattr(mod.subprocess, 'run', _fail)
        assert mod.run_installer('/tmp/installer') is False

    def test_command_matches_tool(
        self,
        installer: tuple[str, ModuleType],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Verify the installer command differs per tool: uv runs ``sh`` while hatch runs a sudo ``.pkg`` install.
        """
        tool, mod = installer
        captured: dict[str, list[str]] = {}

        def _capture(cmd: list[str], **_k: object) -> subprocess.CompletedProcess[str]:
            captured['cmd'] = cmd
            return _completed(stdout='ok')

        monkeypatch.setattr(mod.subprocess, 'run', _capture)
        mod.run_installer('/tmp/installer')

        if tool == 'uv':
            assert captured['cmd'][0] == 'sh'
        else:
            assert captured['cmd'][:2] == ['sudo', 'installer']


# ==================================================================================================
# pip fallback
# ==================================================================================================


class TestResolveSystemPython:
    """
    Tests for resolve_system_python.
    """
    def test_prefers_usr_bin_python3(
        self,
        installer: tuple[str, ModuleType],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Verify the macOS system interpreter at /usr/bin/python3 is preferred when present.
        """
        _tool, mod = installer
        monkeypatch.setattr(mod.Path, 'exists', lambda self: True)
        assert mod.resolve_system_python() == '/usr/bin/python3'

    def test_falls_back_to_path_lookup(
        self,
        installer: tuple[str, ModuleType],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Verify a PATH lookup is used when /usr/bin/python3 is absent.
        """
        _tool, mod = installer
        monkeypatch.setattr(mod.Path,   'exists', lambda self: False)
        monkeypatch.setattr(mod.shutil, 'which',  lambda _name: '/opt/python/bin/python3')
        assert mod.resolve_system_python() == '/opt/python/bin/python3'

    def test_returns_none_when_no_python(
        self,
        installer: tuple[str, ModuleType],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Verify None is returned when no python3 interpreter can be located.
        """
        _tool, mod = installer
        monkeypatch.setattr(mod.Path,   'exists', lambda self: False)
        monkeypatch.setattr(mod.shutil, 'which',  lambda _name: None)
        assert mod.resolve_system_python() is None


class TestRegisterPipInstallLocation:
    """
    Tests for register_pip_install_location.
    """
    def test_registers_scripts_dir_entry(
        self,
        installer: tuple[str, ModuleType],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Verify the interpreter's scripts directory is registered for later discovery.
        """
        tool, mod = installer
        monkeypatch.setattr(mod.subprocess, 'run', lambda *a, **k: _completed(stdout='/scripts/dir\n'))
        mod.register_pip_install_location('/usr/bin/python3')
        assert Path(f'/scripts/dir/{tool}') in mod.PIP_INSTALL_LOCATIONS

    def test_subprocess_failure_registers_nothing(
        self,
        installer: tuple[str, ModuleType],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Verify a failed sysconfig query leaves the registered-locations list untouched.
        """
        _tool, mod = installer

        def _fail(*_a: object, **_k: object) -> None:
            raise subprocess.CalledProcessError(returncode=1, cmd=['python'])

        monkeypatch.setattr(mod.subprocess, 'run', _fail)
        mod.register_pip_install_location('/usr/bin/python3')
        assert mod.PIP_INSTALL_LOCATIONS == []


class TestInstallViaPip:
    """
    Tests for install_via_pip.
    """
    def test_success_returns_true(
        self,
        installer: tuple[str, ModuleType],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Verify a successful pip install returns True and registers the install location.
        """
        _tool, mod = installer
        monkeypatch.setattr(mod,            'resolve_system_python',         lambda: '/usr/bin/python3')
        monkeypatch.setattr(mod.subprocess, 'run',                           lambda *a, **k: _completed(stdout='done'))
        monkeypatch.setattr(mod,            'register_pip_install_location', lambda _p: None)
        assert mod.install_via_pip() is True

    def test_returns_false_without_python(
        self,
        installer: tuple[str, ModuleType],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Verify the fallback returns False when no python3 interpreter is available.
        """
        _tool, mod = installer
        monkeypatch.setattr(mod, 'resolve_system_python', lambda: None)
        assert mod.install_via_pip() is False

    def test_returns_false_on_pip_failure(
        self,
        installer: tuple[str, ModuleType],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Verify a failing pip invocation returns False.
        """
        _tool, mod = installer
        monkeypatch.setattr(mod, 'resolve_system_python', lambda: '/usr/bin/python3')

        def _fail(*_a: object, **_k: object) -> None:
            raise subprocess.CalledProcessError(returncode=1, cmd=['pip'], output='', stderr='boom')

        monkeypatch.setattr(mod.subprocess, 'run', _fail)
        assert mod.install_via_pip() is False


# ==================================================================================================
# Verification
# ==================================================================================================


class TestVerifyInstallation:
    """
    Tests for verify_installation.
    """
    def test_returns_false_when_absent(
        self,
        installer: tuple[str, ModuleType],
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Verify verification fails and prints troubleshooting guidance when the tool cannot be found.
        """
        _tool, mod = installer
        monkeypatch.setattr(mod, 'find_executable', lambda *a, **k: (None, None))
        assert mod.verify_installation() is False
        assert 'Troubleshooting' in capsys.readouterr().err

    def test_returns_true_when_on_path(
        self,
        installer: tuple[str, ModuleType],
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Verify verification succeeds and reports PATH readiness when the bare command resolves.
        """
        tool, mod = installer
        monkeypatch.setattr(mod, 'find_executable', lambda *a, **k: (tool, '1.0.0'))
        assert mod.verify_installation() is True
        assert 'ready to use' in capsys.readouterr().out

    def test_returns_true_when_off_path(
        self,
        installer: tuple[str, ModuleType],
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Verify an off-PATH install still verifies successfully and emits PATH-setup guidance.
        """
        tool, mod = installer
        monkeypatch.setattr(mod, 'find_executable', lambda *a, **k: (f'/opt/homebrew/bin/{tool}', '1.0.0'))
        monkeypatch.setattr(mod.Shell, 'detect', classmethod(lambda cls: cls.ZSH))
        assert mod.verify_installation() is True

        out = capsys.readouterr().out
        assert 'not in your PATH' in out
        assert 'export PATH='     in out


# ==================================================================================================
# Top-level main flow
# ==================================================================================================


class TestMain:
    """
    Tests for the top-level main entry point.
    """
    def test_print_path_short_circuits(
        self,
        installer: tuple[str, ModuleType],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Verify --print-path delegates to print_executable_path without running the install flow.
        """
        _tool, mod = installer
        called = {'print_path': False, 'download': False}

        def _print_path() -> None:
            called['print_path'] = True
            raise SystemExit(mod.ExitCode.SUCCESS)

        monkeypatch.setattr(mod, 'print_executable_path', _print_path)
        monkeypatch.setattr(mod, 'download_installer',    lambda *a, **k: called.__setitem__('download', True))

        with pytest.raises(SystemExit):
            mod.main(['--print-path'])
        assert called['print_path'] is True
        assert called['download']   is False

    def test_already_installed_skips_install(
        self,
        installer: tuple[str, ModuleType],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Verify a normal run exits ALREADY_INSTALLED and never downloads when the tool is present.
        """
        _tool, mod = installer
        downloaded = False

        def _track_download(*_a: object, **_k: object) -> bool:
            nonlocal downloaded
            downloaded = True
            return True

        monkeypatch.setattr(mod, 'check_python_version', lambda: True)
        monkeypatch.setattr(mod, 'is_installed',         lambda **_k: True)
        monkeypatch.setattr(mod, 'download_installer',   _track_download)

        with pytest.raises(SystemExit) as exc_info:
            mod.main([])
        assert exc_info.value.code == mod.ExitCode.ALREADY_INSTALLED
        assert downloaded is False

    def test_unsupported_platform_exits(
        self,
        installer: tuple[str, ModuleType],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Verify a non-macOS platform exits UNSUPPORTED_PLATFORM after the install-needed checks pass.
        """
        _tool, mod = installer
        monkeypatch.setattr(mod, 'check_python_version', lambda: True)
        monkeypatch.setattr(mod, 'is_installed',         lambda **_k: False)
        monkeypatch.setattr(mod, 'get_installer_url',    lambda: (_ for _ in ()).throw(OSError('nope')))

        with pytest.raises(SystemExit) as exc_info:
            mod.main([])
        assert exc_info.value.code == mod.ExitCode.UNSUPPORTED_PLATFORM

    def test_python_version_failure_exits(
        self,
        installer: tuple[str, ModuleType],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Verify a failed Python version check exits with PYTHON_VERSION.
        """
        _tool, mod = installer
        monkeypatch.setattr(mod, 'check_python_version', lambda: False)
        with pytest.raises(SystemExit) as exc_info:
            mod.main([])
        assert exc_info.value.code == mod.ExitCode.PYTHON_VERSION

    def test_successful_install_via_pip_fallback(
        self,
        installer: tuple[str, ModuleType],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Verify a download failure that recovers via the pip fallback exits SUCCESS.
        """
        _tool, mod = installer
        monkeypatch.setattr(mod, 'check_python_version', lambda:         True)
        monkeypatch.setattr(mod, 'is_installed',         lambda **_k:    False)
        monkeypatch.setattr(mod, 'get_installer_url',    lambda:         'https://example.test/install')
        monkeypatch.setattr(mod, 'download_installer',   lambda *a, **k: False)
        monkeypatch.setattr(mod, 'install_via_pip',      lambda:         True)
        monkeypatch.setattr(mod, 'verify_installation',  lambda:         True)

        with pytest.raises(SystemExit) as exc_info:
            mod.main([])
        assert exc_info.value.code == mod.ExitCode.SUCCESS

    def test_install_failure_exits(
        self,
        installer: tuple[str, ModuleType],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Verify a total install failure (download and pip both fail) exits INSTALL_FAILED.
        """
        _tool, mod = installer
        monkeypatch.setattr(mod, 'check_python_version', lambda:         True)
        monkeypatch.setattr(mod, 'is_installed',         lambda **_k:    False)
        monkeypatch.setattr(mod, 'get_installer_url',    lambda:         'https://example.test/install')
        monkeypatch.setattr(mod, 'download_installer',   lambda *a, **k: False)
        monkeypatch.setattr(mod, 'install_via_pip',      lambda:         False)

        with pytest.raises(SystemExit) as exc_info:
            mod.main([])
        assert exc_info.value.code == mod.ExitCode.INSTALL_FAILED

    def test_verification_failure_exits(
        self,
        installer: tuple[str, ModuleType],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Verify a successful install with failed verification exits VERIFICATION_FAILED.
        """
        _tool, mod = installer
        monkeypatch.setattr(mod, 'check_python_version', lambda:         True)
        monkeypatch.setattr(mod, 'is_installed',         lambda **_k:    False)
        monkeypatch.setattr(mod, 'get_installer_url',    lambda:         'https://example.test/install')
        monkeypatch.setattr(mod, 'download_installer',   lambda *a, **k: False)
        monkeypatch.setattr(mod, 'install_via_pip',      lambda:         True)
        monkeypatch.setattr(mod, 'verify_installation',  lambda:         False)

        with pytest.raises(SystemExit) as exc_info:
            mod.main([])
        assert exc_info.value.code == mod.ExitCode.VERIFICATION_FAILED

    def test_download_then_run_installer_success(
        self,
        installer: tuple[str, ModuleType],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """
        Verify the primary path -- successful download then installer execution -- exits SUCCESS.
        """
        _tool, mod = installer
        monkeypatch.setattr(mod, 'check_python_version', lambda:         True)
        monkeypatch.setattr(mod, 'is_installed',         lambda **_k:    False)
        monkeypatch.setattr(mod, 'get_installer_url',    lambda:         'https://example.test/install')
        monkeypatch.setattr(mod, 'download_installer',   lambda *a, **k: True)
        monkeypatch.setattr(mod, 'run_installer',        lambda _p:      True)
        monkeypatch.setattr(mod, 'verify_installation',  lambda:         True)

        # Keep the installer-path unlink within a temp directory rather than the real home directory
        monkeypatch.setattr(mod.Path, 'home', lambda: tmp_path)

        with pytest.raises(SystemExit) as exc_info:
            mod.main([])
        assert exc_info.value.code == mod.ExitCode.SUCCESS

    def test_ensure_checks_path_strictly_and_quietly(
        self,
        installer: tuple[str, ModuleType],
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Verify --ensure checks installation PATH-strictly and quietly, staying silent on a no-op run.
        """
        _tool, mod = installer
        received: dict[str, Any] = {}

        def _is_installed(*, quiet: bool = False, path_only: bool = False) -> bool:
            received['quiet']     = quiet
            received['path_only'] = path_only
            return True

        monkeypatch.setattr(mod, 'check_python_version', lambda: True)
        monkeypatch.setattr(mod, 'is_installed',         _is_installed)

        with pytest.raises(SystemExit) as exc_info:
            mod.main(['--ensure'])

        assert exc_info.value.code == mod.ExitCode.ALREADY_INSTALLED
        assert received == {'quiet': True, 'path_only': True}

        # A no-op --ensure run prints no banner
        assert 'installation' not in capsys.readouterr().out
