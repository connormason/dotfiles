"""
Unit tests for run.py doctor checks
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import run


def _completed(returncode: int, stdout: str = '', stderr: str = '') -> subprocess.CompletedProcess[str]:
    """
    Build a fake CompletedProcess
    """
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


class TestDoctorChecks:
    """
    Tests for individual doctor checks
    """
    def test_links_ok_when_stow_reports_no_changes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that a no-op stow simulation means links are current
        """
        stdout = 'stow: no changes (already current)\nstow: simulated foo (dry-run, no changes written)\n'
        monkeypatch.setattr(run, '_capture', lambda cmd: _completed(0, stdout))
        assert run.check_links().ok

    def test_links_ok_with_no_packages(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that a repo with no packages yet is not reported as broken
        """
        monkeypatch.setattr(run, '_capture', lambda cmd: _completed(0, 'stow: no packages found\n'))
        assert run.check_links().ok

    def test_links_fail_when_stow_would_change(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that pending stow changes fail the check and offer a fix
        """
        stdout = (
            'stow: dry-run preview of changes:\n'
            '  + ~/.foorc (would link)\n'
            'stow: 2 added, 0 updated, 0 removed\n'
            'stow: simulated foo (dry-run, no changes written)\n'
        )
        monkeypatch.setattr(run, '_capture', lambda cmd: _completed(0, stdout))

        check = run.check_links()
        assert not check.ok
        assert check.fix is not None
        assert '2 added' in check.detail

    def test_links_fail_when_conflicts_block_stow(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that a blocked stow (exit 1) fails the check, surfaces stderr, and offers the backup fix
        """
        stderr = 'stow: these existing files block linking (nothing was changed):\n  ~/.foorc\n'
        monkeypatch.setattr(run, '_capture', lambda cmd: _completed(1, '', stderr))

        check = run.check_links()
        assert not check.ok
        assert 'block linking' in check.detail
        assert check.fix is not None
        assert '--backup-conflicts' in check.fix

    def test_render_check_maps_exit_code(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that render --check exit 1 fails the check and offers a fix
        """
        monkeypatch.setattr(run, '_capture', lambda cmd: _completed(1))

        check = run.check_render()
        assert not check.ok
        assert check.fix is not None

    def test_render_check_ok_on_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that render --check exit 0 passes the check
        """
        monkeypatch.setattr(run, '_capture', lambda cmd: _completed(0))
        assert run.check_render().ok

    def test_render_check_config_error_has_no_fix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that render exit 2 (config or I/O error) fails without offering a blind re-render
        """
        monkeypatch.setattr(run, '_capture', lambda cmd: _completed(2, '', 'render: bad fragment\n'))

        check = run.check_render()
        assert not check.ok
        assert check.fix is None
        assert 'bad fragment' in check.detail

    @pytest.mark.parametrize(
        ('version_line', 'ok'),
        [
            ('git version 2.36.0',                  True),
            ('git version 2.47.1 (Vendor Git-154)', True),
            ('git version 2.35.9',                  False),
        ],
    )
    def test_git_version(self, monkeypatch: pytest.MonkeyPatch, version_line: str, ok: bool) -> None:
        """
        Test that git must support includeIf hasconfig (>= 2.36)
        """
        monkeypatch.setattr(run, '_capture', lambda cmd: _completed(0, version_line + '\n'))
        assert run.check_git_version().ok is ok

    def test_layers_fail_on_registry_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that a broken overlay registry fails the layers check
        """
        monkeypatch.setattr(run, '_capture', lambda cmd: _completed(1))
        assert not run.check_layers().ok

    def test_layers_count_overlays(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that the layers check reports the base layer plus each overlay
        """
        monkeypatch.setattr(run, '_capture', lambda cmd: _completed(0, '/repo\n/overlay\n'))

        check = run.check_layers()
        assert check.ok
        assert '2 layer(s)' in check.detail

    def test_layers_count_ignores_env_sh_output(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """
        Test that text an overlay env.sh prints while lib.sh loads is not counted as a layer
        """
        overlay = tmp_path / 'overlay'
        (overlay / 'bootstrap').mkdir(parents=True)
        (overlay / 'bootstrap' / 'env.sh').write_text('echo NOT-A-LAYER\n', encoding='utf-8')

        registry = tmp_path / 'overlays'
        registry.write_text(f'{overlay}\n', encoding='utf-8')

        monkeypatch.setenv('HOME',                   str(tmp_path / 'home'))
        monkeypatch.setenv('DOTFILES_OVERLAYS_FILE', str(registry))
        monkeypatch.delenv('DOTFILES_BREW_PREFIXES', raising=False)

        check = run.check_layers()
        assert check.ok, check.detail
        assert check.detail == '2 layer(s): base + 1 overlay(s)'

    def test_tools_reports_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that a missing required tool fails the tools check and is named
        """
        monkeypatch.setattr(run.shutil, 'which', lambda name: None if name == 'stow' else f'/usr/bin/{name}')

        check = run.check_tools()
        assert not check.ok
        assert 'stow' in check.detail


class TestDoctorReadOnly:
    """
    Tests that the doctor's own probes can never mutate the home directory
    """
    @staticmethod
    def _record(monkeypatch: pytest.MonkeyPatch, stdout: str = '') -> list[list[str]]:
        """
        Stub _capture to record every probe command line
        """
        seen: list[list[str]] = []

        def fake_capture(cmd: list[str]) -> subprocess.CompletedProcess[str]:
            seen.append(cmd)
            return _completed(0, stdout)

        monkeypatch.setattr(run, '_capture', fake_capture)
        return seen

    def test_links_probe_simulates_stow(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that the links check runs this repo's stow.sh in simulate mode only
        """
        seen = self._record(monkeypatch, 'stow: no changes (already current)\n')
        run.check_links()
        assert seen == [['bash', str(run.STOW_SCRIPT), '-n']]

    def test_render_probe_is_check_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that the render check passes --check and nothing that writes
        """
        seen = self._record(monkeypatch)
        run.check_render()
        assert seen == [[sys.executable, str(run.RENDER_SCRIPT), '--check']]

    def test_layers_probe_pins_repo(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that the layers check pins DOTFILES_REPO to this repository checkout
        """
        seen = self._record(monkeypatch, f'{run.DOTFILES_DIR}\n')
        run.check_layers()

        assert len(seen) == 1
        assert seen[0][:2] == ['bash', '-c']
        assert 'export DOTFILES_REPO="$1"' in seen[0][2]
        assert seen[0][-1] == str(run.DOTFILES_DIR)

    def test_git_probe_only_reads_version(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that the git check only asks for the version
        """
        seen = self._record(monkeypatch, 'git version 2.47.1\n')
        run.check_git_version()
        assert seen == [['git', '--version']]

    def test_fix_commands_are_not_run_without_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that doctor without --fix never invokes a fix command
        """
        monkeypatch.setattr(run, 'doctor_checks', lambda: [run.DoctorCheck('links', False, 'x', ['echo', 'fix'])])

        def fail_shell_command(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            raise AssertionError(f'unexpected command: {cmd}')

        monkeypatch.setattr(run, 'shell_command', fail_shell_command)
        with pytest.raises(SystemExit):
            run.cmd_doctor(run.argparse.Namespace(fix=False))


class TestDoctorCommand:
    """
    Tests for the doctor orchestration and command registration
    """
    def test_checks_stop_early_when_prerequisites_fail(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that dependent checks are skipped when tools or layers fail
        """
        monkeypatch.setattr(run, 'check_tools',  lambda: run.DoctorCheck('tools',  False, 'missing: stow'))
        monkeypatch.setattr(run, 'check_layers', lambda: run.DoctorCheck('layers', True,  '1 layer(s)'))
        assert [c.name for c in run.doctor_checks()] == ['tools', 'layers']

    def test_doctor_exits_nonzero_on_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that doctor exits 1 when any check fails
        """
        monkeypatch.setattr(run, 'doctor_checks', lambda: [run.DoctorCheck('links', False, 'pending')])
        with pytest.raises(SystemExit) as exc_info:
            run.cmd_doctor(run.argparse.Namespace(fix=False))
        assert exc_info.value.code == 1

    def test_doctor_passes_quietly_when_all_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that doctor returns normally when every check passes
        """
        monkeypatch.setattr(run, 'doctor_checks', lambda: [run.DoctorCheck('links', True, 'ok')])
        run.cmd_doctor(run.argparse.Namespace(fix=False))

    def test_fix_runs_fix_then_rechecks(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that --fix runs each failing check's fix command and re-runs the checks
        """
        results = iter([
            [run.DoctorCheck('links', False, 'pending',             ['echo', 'fix'])],
            [run.DoctorCheck('links', True,  'all packages linked')],
        ])
        ran: list[list[str]] = []

        def fake_shell_command(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            ran.append(cmd)
            return _completed(0)

        monkeypatch.setattr(run, 'doctor_checks', lambda: next(results))
        monkeypatch.setattr(run, 'shell_command', fake_shell_command)
        run.cmd_doctor(run.argparse.Namespace(fix=True))
        assert ran == [['echo', 'fix']]

    def test_dotfiles_commands_registered(self) -> None:
        """
        Test that every Dotfiles command is registered under the Dotfiles group
        """
        group = run.get_command_groups()['Dotfiles']
        assert set(group) == {'bootstrap', 'stow', 'render', 'doctor', 'test'}


class TestForwarding:
    """
    Tests for the commands that forward their flags to the underlying scripts
    """
    @staticmethod
    def _capture_cmd(monkeypatch: pytest.MonkeyPatch, returncode: int = 0) -> list[list[str]]:
        """
        Patch shell_command to record the forwarded command line
        """
        seen: list[list[str]] = []

        def fake_shell_command(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            seen.append(cmd)
            return _completed(returncode)

        monkeypatch.setattr(run, 'shell_command', fake_shell_command)
        return seen

    def test_stow_forwards_flags_and_packages(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that stow forwards -n, --backup-conflicts, -v, and package names
        """
        seen = self._capture_cmd(monkeypatch)
        args = run.argparse.Namespace(simulate=True, backup_conflicts=True, verbose=True, packages=['zsh', 'git'])
        with pytest.raises(SystemExit) as exc_info:
            run.cmd_stow(args)

        assert exc_info.value.code == 0
        assert seen[0][2:] == ['-n', '--backup-conflicts', '--verbose', 'zsh', 'git']
        assert seen[0][1] == str(run.STOW_SCRIPT)

    def test_stow_propagates_exit_code(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that stow exits with the script's return code
        """
        self._capture_cmd(monkeypatch, returncode=1)
        args = run.argparse.Namespace(simulate=False, backup_conflicts=False, verbose=False, packages=[])
        with pytest.raises(SystemExit) as exc_info:
            run.cmd_stow(args)
        assert exc_info.value.code == 1

    def test_bootstrap_forwards_flags(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that bootstrap forwards its flags and stage selectors
        """
        seen = self._capture_cmd(monkeypatch)
        args = run.argparse.Namespace(
            dry_run=True,
            list=False,
            resume=True,
            verify=True,
            no_log=True,
            only='00-preflight',
            from_stage='20-x',
        )
        with pytest.raises(SystemExit):
            run.cmd_bootstrap(args)

        assert seen[0][2:] == [
            '--dry-run', '--resume', '--verify', '--no-log', '--only', '00-preflight', '--from', '20-x',
        ]

    def test_render_forwards_targets_and_flags(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that render forwards targets, --diff, --check, --force, and -v
        """
        seen = self._capture_cmd(monkeypatch)
        args = run.argparse.Namespace(targets=['claude'], diff=True, check=True, force=True, verbose=True)
        with pytest.raises(SystemExit):
            run.cmd_render(args)
        assert seen[0][2:] == ['claude', '--diff', '--check', '--force', '-v']

    def test_test_defaults_to_tests_dir(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that the test command runs pytest on tests/ through the public uv wrapper
        """
        seen = self._capture_cmd(monkeypatch)
        with pytest.raises(SystemExit):
            run.cmd_test(run.argparse.Namespace(paths=[]))
        assert seen[0] == [str(run.UV_PUBLIC), 'run', '--group', 'test', 'pytest', 'tests']
