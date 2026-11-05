"""
Unit tests for the run.py environment commands (install, dev, status, clean, lock*, install-uv/hatch, diagnose)
and the python/uv/venv doctor checks
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import run

Call = tuple[list[str], dict[str, object]]


def _parse(*argv: str) -> argparse.Namespace:
    """
    Parse a run.py command line into the typed root namespace
    """
    return run.build_parser().parse_args(list(argv), namespace=run.Args())


def _completed(cmd: list[str], returncode: int = 0) -> subprocess.CompletedProcess[str]:
    """
    Build a fake CompletedProcess
    """
    return subprocess.CompletedProcess(cmd, returncode, stdout='', stderr='')


# ==============================================================================
# python / uv / venv doctor checks
# ==============================================================================


class TestEnvironmentDoctorChecks:
    """
    Tests for check_python_tool, check_uv_tool, and check_venv
    """
    def test_python_ok_without_minimum(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that python passes when no minimum version is configured
        """
        monkeypatch.setattr(run, 'MIN_PYTHON', None)
        check = run.check_python_tool()
        assert check.ok
        assert check.name == 'python'

    def test_python_fails_below_minimum(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that an unmet MIN_PYTHON fails the check without exiting
        """
        monkeypatch.setattr(run, 'MIN_PYTHON', (99, 0))
        check = run.check_python_tool()
        assert not check.ok
        assert '99.0' in check.detail

    def test_uv_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that an installed uv reports its version
        """
        monkeypatch.setattr(run, 'check_uv', lambda: run.ToolInfo(executable=Path('/x/uv'), version='0.9.1'))
        check = run.check_uv_tool()
        assert check.ok
        assert '0.9.1' in check.detail

    def test_uv_missing_offers_the_installer(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that a missing uv fails with the bundled installer script as the fix
        """
        monkeypatch.setattr(run, 'check_uv', lambda: None)
        check = run.check_uv_tool()
        assert not check.ok
        assert check.fix == [sys.executable, str(run.INSTALLER_SCRIPTS['uv']), '--ensure']

    @pytest.mark.parametrize(
        ('status', 'ok', 'has_fix'),
        [
            (run.VenvStatus.HEALTHY,        True,  False),
            (run.VenvStatus.NOT_ACTIVATED,  True,  False),
            (run.VenvStatus.STALE_DEPS,     False, True),
            (run.VenvStatus.MISSING,        False, True),
            (run.VenvStatus.BROKEN_SYMLINK, False, True),
        ],
    )
    def test_venv_status_mapping(
        self,
        monkeypatch: pytest.MonkeyPatch,
        status: run.VenvStatus,
        ok: bool,
        has_fix: bool,
    ) -> None:
        """
        Test that healthy and merely-inactive venvs pass while the rest fail with `run.py install` as the fix
        """
        monkeypatch.setattr(run, 'get_external_active_venv', lambda: None)
        monkeypatch.setattr(run, 'validate_venv', lambda venv_dir: run.VenvHealth(status=status, message='msg'))

        check = run.check_venv()
        assert check.ok is ok
        assert (check.fix == [sys.executable, str(run.SCRIPT_PATH), 'install']) if has_fix else (check.fix is None)

    def test_external_venv_has_no_fix(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that a stale user-managed venv is reported without offering to repair it
        """
        monkeypatch.setattr(run, 'get_external_active_venv', lambda: tmp_path)
        monkeypatch.setattr(
            run,
            'validate_venv',
            lambda venv_dir: run.VenvHealth(status=run.VenvStatus.STALE_DEPS, message='stale'),
        )
        assert run.check_venv().fix is None

    def test_included_in_full_run(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that doctor_checks includes the python, uv, and venv checks
        """
        for func in (
            'check_tools', 'check_layers', 'check_python_tool', 'check_uv_tool', 'check_git_version',
            'check_hooks', 'check_venv', 'check_links', 'check_render', 'check_brewfiles',
        ):
            monkeypatch.setattr(run, func, lambda func=func: run.DoctorCheck(func, True, 'ok'))

        names = [c.name for c in run.doctor_checks()]
        assert {'check_python_tool', 'check_uv_tool', 'check_venv'} <= set(names)


# ==============================================================================
# lock, lock-check, lock-upgrade
# ==============================================================================


class TestLockCommands:
    """
    Tests for the lock, lock-check, and lock-upgrade commands
    """
    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Skip tool checks and record uv_lock calls
        """
        self.calls: list[dict[str, object]] = []
        self.returncode = 0

        def fake_uv_lock(**kwargs: object) -> subprocess.CompletedProcess[str]:
            self.calls.append(kwargs)
            return _completed(['uv', 'lock'], self.returncode)

        monkeypatch.setattr(run, 'check_python', lambda **_kwargs: None)
        monkeypatch.setattr(run, 'ensure_uv',    lambda **_kwargs: None)
        monkeypatch.setattr(run, 'uv_lock',      fake_uv_lock)

    def _run(self, *argv: str) -> int:
        """
        Run a command and return its exit code (0 when it returns normally)
        """
        try:
            run.get_commands()[argv[0]](_parse(*argv))
        except SystemExit as e:
            return int(e.code or 0)
        return 0

    @pytest.mark.parametrize(('argv', 'refresh'), [(['lock'], False), (['lock', '--refresh'], True)])
    def test_lock(self, argv: list[str], refresh: bool) -> None:
        """
        Test that lock forwards --refresh and exits successfully
        """
        assert self._run(*argv) == 0
        assert self.calls == [{'refresh': refresh, 'check': False, 'indent': 3}]

    def test_lock_propagates_failure(self) -> None:
        """
        Test that lock exits with uv's return code
        """
        self.returncode = 2
        assert self._run('lock') == 2

    def test_lock_check_passes(self, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that an up-to-date lock reports success and returns normally
        """
        assert self._run('lock-check') == 0
        assert self.calls == [{'check_only': True, 'check': False, 'indent': 3}]
        assert 'up to date' in run.unstyle(capsys.readouterr().out)

    def test_lock_check_stale_exits_1_with_hint(self, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that a stale lock exits 1 and points at `make lock`
        """
        self.returncode = 1
        assert self._run('lock-check') == run.ExitCode.COMMAND_FAILED

        out = run.unstyle(capsys.readouterr().out)
        assert 'out of date' in out
        assert 'make lock'   in out

    def test_lock_upgrade_all(self, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that without -P every package is upgraded, and the hook reminder is printed on success
        """
        assert self._run('lock-upgrade') == 0
        assert self.calls == [{'upgrade': True, 'upgrade_packages': None, 'check': False, 'indent': 3}]

        out = run.unstyle(capsys.readouterr().out)
        assert 'Regenerating files derived from uv.lock' in out

    def test_lock_upgrade_packages(self) -> None:
        """
        Test that repeated -P options upgrade only those packages
        """
        assert self._run('lock-upgrade', '-P', 'ruff', '-P', 'pytest') == 0
        assert self.calls == [{'upgrade': False, 'upgrade_packages': ['ruff', 'pytest'], 'check': False, 'indent': 3}]

    def test_lock_upgrade_failure_skips_the_reminder(self, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that a failed upgrade exits with uv's code and prints no reminder
        """
        self.returncode = 1
        assert self._run('lock-upgrade') == 1
        assert 'uv-export' not in run.unstyle(capsys.readouterr().out)


# ==============================================================================
# install, dev
# ==============================================================================


class TestInstallAndDev:
    """
    Tests for the install and dev commands
    """
    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Record the environment helpers instead of running them
        """
        self.venv_calls: list[dict[str, object]] = []
        self.sync_calls: list[dict[str, object]] = []
        self.uv_runs:    list[Call]              = []
        self.entered:    int                     = 0

        def fake_uv_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            self.uv_runs.append((cmd, kwargs))
            return _completed(cmd)

        def enter(**_kwargs: object) -> None:
            self.entered += 1

        monkeypatch.delenv('VIRTUAL_ENV', raising=False)
        monkeypatch.setattr(run, 'check_python', lambda **_kwargs: None)
        monkeypatch.setattr(run, 'ensure_uv',    lambda **_kwargs: None)
        monkeypatch.setattr(run, 'ensure_venv',  lambda **kwargs: self.venv_calls.append(kwargs))
        monkeypatch.setattr(run, 'uv_sync',      lambda **kwargs: self.sync_calls.append(kwargs))
        monkeypatch.setattr(run, 'uv_run',       fake_uv_run)
        monkeypatch.setattr(run, 'enter_venv',   enter)

    @pytest.mark.parametrize('command', ['install', 'dev'])
    def test_all_option_is_not_offered(self, command: str) -> None:
        """
        Test that --all is gone: the project defines no extras
        """
        with pytest.raises(SystemExit) as exc_info:
            _parse(command, '--all')
        assert exc_info.value.code == 2

    def test_install_default(self) -> None:
        """
        Test that a plain install syncs without dev dependencies, hooks, or a subshell
        """
        run.get_commands()['install'](_parse('install'))

        assert self.venv_calls == [{'inexact': True, 'no_dev': True}]
        assert self.uv_runs    == []
        assert self.entered    == 0

    def test_install_dev_hooks_shell(self) -> None:
        """
        Test that --dev, --hooks, and --shell include dev dependencies, force-install hooks, and enter the venv
        """
        run.get_commands()['install'](_parse('install', '--dev', '--hooks', '--shell'))

        assert self.venv_calls == [{'inexact': True, 'no_dev': False}]
        assert self.uv_runs    == [(['prek', 'install', '-f'], {'active': False, 'indent': 3})]
        assert self.entered    == 1

    def test_install_into_active_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that an active virtualenv is synced in place instead of creating .venv
        """
        monkeypatch.setenv('VIRTUAL_ENV', '/somewhere/venv')
        run.get_commands()['install'](_parse('install'))

        assert self.venv_calls == []
        assert self.sync_calls == [{'active': True, 'inexact': True, 'no_dev': True, 'indent': 3}]

    def test_dev_defaults_install_hooks_and_enter_shell(self) -> None:
        """
        Test that dev installs hooks and enters the subshell by default
        """
        run.get_commands()['dev'](_parse('dev'))

        assert self.venv_calls == [{'inexact': True}]
        assert self.uv_runs    == [(['prek', 'install'], {'active': False, 'indent': 3})]
        assert self.entered    == 1

    def test_dev_opt_outs(self) -> None:
        """
        Test that --no-hooks and --no-shell skip hook installation and the subshell
        """
        run.get_commands()['dev'](_parse('dev', '--no-hooks', '--no-shell'))

        assert self.uv_runs == []
        assert self.entered == 0


# ==============================================================================
# install-uv, install-hatch
# ==============================================================================


class TestToolInstallers:
    """
    Tests for the install-uv and install-hatch commands
    """
    @pytest.mark.parametrize('tool', ['uv', 'hatch'])
    def test_builds_command(self, monkeypatch: pytest.MonkeyPatch, tool: str) -> None:
        """
        Test that the installer script runs under the current interpreter with every option forwarded
        """
        calls: list[Call] = []

        def fake_shell_command(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append((cmd, kwargs))
            return _completed(cmd)

        monkeypatch.setattr(run, 'check_script_validity', lambda *args, **kwargs: None)
        monkeypatch.setattr(run, 'shell_command',         fake_shell_command)

        argv = [f'install-{tool}', '-f', '-v', '--retries', '3', '--retry-delay', '5']
        with pytest.raises(SystemExit) as exc_info:
            run.get_commands()[f'install-{tool}'](_parse(*argv))

        assert exc_info.value.code == 0
        expected = [
            sys.executable, str(run.INSTALLER_SCRIPTS[tool]),  # type: ignore[index]
            '--force', '--verbose', '--retries', '3', '--retry-delay', '5',
        ]
        assert calls == [(expected, {'check': False})]

    def test_propagates_exit_code(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that a failing installer exits with its return code
        """
        monkeypatch.setattr(run, 'check_script_validity', lambda *args, **kwargs: None)
        monkeypatch.setattr(run, 'shell_command',         lambda cmd, **kwargs: _completed(cmd, 4))

        with pytest.raises(SystemExit) as exc_info:
            run.get_commands()['install-uv'](_parse('install-uv'))
        assert exc_info.value.code == 4

    def test_missing_script_is_a_setup_error(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """
        Test that a missing installer script exits with SETUP_ERROR before anything runs
        """
        monkeypatch.setitem(run.INSTALLER_SCRIPTS, 'uv', tmp_path / 'missing.py')
        with pytest.raises(SystemExit) as exc_info:
            run.get_commands()['install-uv'](_parse('install-uv'))
        assert exc_info.value.code == run.ExitCode.SETUP_ERROR


# ==============================================================================
# diagnose
# ==============================================================================


class TestDiagnose:
    """
    Tests for the diagnose command
    """
    @pytest.mark.parametrize(
        ('argv', 'extra'),
        [
            ([],                                 []),
            (['--max-installed-packages', '10'], ['--max-installed-packages', '10']),
            (['-s', '-j'],                       ['--save', '--json']),
            (['-o', 'out.txt'],                  ['--output', 'out.txt']),
        ],
    )
    def test_builds_command(self, monkeypatch: pytest.MonkeyPatch, argv: list[str], extra: list[str]) -> None:
        """
        Test that only the supplied options reach the diagnostic script
        """
        calls: list[Call] = []

        def fake_shell_command(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append((cmd, kwargs))
            return _completed(cmd)

        monkeypatch.setattr(run, 'check_script_validity', lambda *args, **kwargs: None)
        monkeypatch.setattr(run, 'shell_command',         fake_shell_command)

        run.get_commands()['diagnose'](_parse('diagnose', *argv))
        assert calls == [([sys.executable, str(run.DIAGNOSTIC_SCRIPT_PATH), *extra], {'indent': 3})]


# ==============================================================================
# status
# ==============================================================================


class TestStatus:
    """
    Tests for the status command
    """
    @pytest.mark.parametrize(('hooks_ok', 'marker'), [(True, 'hooks-detail-ok'), (False, 'hooks-detail-bad')])
    def test_hooks_row_comes_from_check_hooks(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        hooks_ok: bool,
        marker: str,
    ) -> None:
        """
        Test that the hooks row shows the doctor hooks check's detail and a failure marks the environment unhealthy
        """
        python = run.ToolInfo(executable=Path('/p'), version='3.12.0')
        monkeypatch.setattr(run, 'check_python',  lambda **_kwargs: python)
        monkeypatch.setattr(run, 'check_uv',      lambda: run.ToolInfo(executable=Path('/x/uv'), version='0.9.1'))
        monkeypatch.setattr(run, 'check_hooks',   lambda: run.DoctorCheck('hooks', hooks_ok, marker))
        monkeypatch.setattr(run, 'validate_venv', lambda *args, **kwargs: run.VenvHealth(status=run.VenvStatus.HEALTHY))
        monkeypatch.setattr(run, 'get_external_active_venv', lambda: None)

        run.get_commands()['status'](argparse.Namespace())

        out = run.unstyle(capsys.readouterr().out)
        assert marker in out
        assert ('Environment ready.' in out) is hooks_ok


# ==============================================================================
# clean
# ==============================================================================


class TestClean:
    """
    Tests for the clean command
    """
    @pytest.fixture(autouse=True)
    def _workspace(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Build a workspace with a venv, a build directory, and a cache directory
        """
        for name in ('.venv', 'build', '.pytest_cache'):
            (tmp_path / name).mkdir()
            (tmp_path / name / 'file').write_text('x', encoding='utf-8')
        self.root = tmp_path
        monkeypatch.setattr(run, 'DOTFILES_DIR', tmp_path)

    def test_removes_everything_by_default(self) -> None:
        """
        Test that the virtual environment is removed along with artifacts and caches
        """
        run.get_commands()['clean'](_parse('clean'))
        assert not any((self.root / name).exists() for name in ('.venv', 'build', '.pytest_cache'))

    def test_no_envs_keeps_the_venv(self) -> None:
        """
        Test that --no-envs preserves .venv but still removes artifacts and caches
        """
        run.get_commands()['clean'](_parse('clean', '--no-envs'))

        assert     (self.root / '.venv' / 'file').exists()
        assert not (self.root / 'build').exists()
        assert not (self.root / '.pytest_cache').exists()
