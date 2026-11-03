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
            run.get_commands()['doctor'](run.argparse.Namespace(fix=False, yes=False))


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
            run.get_commands()['doctor'](run.argparse.Namespace(fix=False, yes=False))
        assert exc_info.value.code == 1

    def test_doctor_passes_quietly_when_all_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that doctor returns normally when every check passes
        """
        monkeypatch.setattr(run, 'doctor_checks', lambda: [run.DoctorCheck('links', True, 'ok')])
        run.get_commands()['doctor'](run.argparse.Namespace(fix=False, yes=False))

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
        run.get_commands()['doctor'](run.argparse.Namespace(fix=True, yes=True))
        assert ran == [['echo', 'fix']]

    def test_fix_asks_before_each_fix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that --fix names the fix command in a confirmation prompt before running it
        """
        results = iter([
            [run.DoctorCheck('links', False, 'pending',             ['echo', 'fix'])],
            [run.DoctorCheck('links', True,  'all packages linked')],
        ])
        asked: list[str] = []
        ran:   list[list[str]] = []

        def fake_confirm(prompt: str, **kwargs: object) -> bool:
            asked.append(run.unstyle(prompt))
            return True

        def fake_shell_command(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            ran.append(cmd)
            return _completed(0)

        monkeypatch.setattr(run, 'doctor_checks', lambda: next(results))
        monkeypatch.setattr(run, 'confirm', fake_confirm)
        monkeypatch.setattr(run, 'shell_command', fake_shell_command)

        run.get_commands()['doctor'](run.argparse.Namespace(fix=True, yes=False))
        assert len(asked) == 1
        assert 'echo fix' in asked[0]
        assert 'links' in asked[0]
        assert ran == [['echo', 'fix']]

    def test_declined_fix_is_skipped_and_doctor_still_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that a declined fix does not run, the checks are re-run, and the command exits 1
        """
        pending = [run.DoctorCheck('links', False, 'pending', ['echo', 'fix'])]
        ran: list[list[str]] = []

        def fake_shell_command(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            ran.append(cmd)
            return _completed(0)

        monkeypatch.setattr(run, 'doctor_checks', lambda: pending)
        monkeypatch.setattr(run, 'confirm', lambda prompt, **kwargs: False)
        monkeypatch.setattr(run, 'shell_command', fake_shell_command)

        with pytest.raises(SystemExit) as exc_info:
            run.get_commands()['doctor'](run.argparse.Namespace(fix=True, yes=False))
        assert exc_info.value.code == 1
        assert ran == []

    def test_yes_implies_fix_without_prompting(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that --yes applies fixes without --fix and never asks
        """
        results = iter([
            [run.DoctorCheck('links', False, 'pending',             ['echo', 'fix'])],
            [run.DoctorCheck('links', True,  'all packages linked')],
        ])
        ran: list[list[str]] = []

        def refuse_prompt(prompt: str, **kwargs: object) -> bool:
            raise AssertionError('--yes must not prompt')

        def fake_shell_command(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            ran.append(cmd)
            return _completed(0)

        monkeypatch.setattr(run, 'doctor_checks', lambda: next(results))
        monkeypatch.setattr(run, 'confirm', refuse_prompt)
        monkeypatch.setattr(run, 'shell_command', fake_shell_command)

        run.get_commands()['doctor'](run.argparse.Namespace(fix=False, yes=True))
        assert ran == [['echo', 'fix']]

    def test_dotfiles_commands_registered(self) -> None:
        """
        Test that every Dotfiles command is registered under the Dotfiles group
        """
        group = run.get_commands(by_group=True)['Dotfiles']
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
            run.get_commands()['stow'](args)

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
            run.get_commands()['stow'](args)
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
            run.get_commands()['bootstrap'](args)

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
            run.get_commands()['render'](args)
        assert seen[0][2:] == ['claude', '--diff', '--check', '--force', '-v']

    def test_test_defaults_to_tests_dir(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that the test command runs pytest on tests/ through the public uv wrapper
        """
        seen = self._capture_cmd(monkeypatch)
        with pytest.raises(SystemExit):
            run.get_commands()['test'](run.argparse.Namespace(paths=[]))
        assert seen[0] == [str(run.UV_PUBLIC), 'run', '--group', 'test', 'pytest', 'tests']


SHIM = '#!/bin/sh\n# File generated by prek: https://github.com/j178/prek\nexec prek hook-impl "$@"\n'


def _write_shims(hooks_dir: Path, hook_types: tuple[str, ...], content: str = SHIM) -> None:
    """
    Create hook shim files for the given hook types
    """
    hooks_dir.mkdir(parents=True, exist_ok=True)
    for hook_type in hook_types:
        (hooks_dir / hook_type).write_text(content, encoding='utf-8')


class TestCheckHooks:
    """
    Tests for the git hooks doctor check
    """
    @pytest.fixture(autouse=True)
    def _prek_on_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Pretend prek is installed unless a test says otherwise
        """
        monkeypatch.setattr(run.shutil, 'which', lambda name: f'/usr/bin/{name}')

    def test_ok_when_every_shim_is_installed(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """
        Test that the check passes when all hook types have a prek shim
        """
        hooks = tmp_path / 'hooks'
        _write_shims(hooks, run.GIT_HOOK_TYPES)
        monkeypatch.setattr(run, '_capture', lambda cmd: _completed(0, f'{hooks}\n'))

        check = run.check_hooks()
        assert check.ok
        assert check.detail == '6 prek hook shims installed'

    def test_missing_shim_fails_and_offers_prek_install(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """
        Test that a missing pre-push shim (the leak guard) fails the check and is named in the detail
        """
        hooks = tmp_path / 'hooks'
        _write_shims(hooks, tuple(t for t in run.GIT_HOOK_TYPES if t != 'pre-push'))
        monkeypatch.setattr(run, '_capture', lambda cmd: _completed(0, f'{hooks}\n'))

        check = run.check_hooks()
        assert not check.ok
        assert 'pre-push' in check.detail
        assert check.fix == ['prek', 'install']

    def test_foreign_shim_counts_as_missing(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """
        Test that a hook file not generated by prek does not satisfy the check
        """
        hooks = tmp_path / 'hooks'
        _write_shims(hooks, run.GIT_HOOK_TYPES, content='#!/bin/sh\necho custom hook\n')
        monkeypatch.setattr(run, '_capture', lambda cmd: _completed(0, f'{hooks}\n'))
        assert not run.check_hooks().ok

    def test_relative_hooks_path_is_resolved_against_the_repo(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """
        Test that the relative path git prints in a plain checkout is resolved against the repo root
        """
        _write_shims(tmp_path / '.git' / 'hooks', run.GIT_HOOK_TYPES)
        monkeypatch.setattr(run, 'DOTFILES_DIR', tmp_path)
        monkeypatch.setattr(run, '_capture', lambda cmd: _completed(0, '.git/hooks\n'))
        assert run.check_hooks().ok

    def test_absolute_hooks_path_from_a_linked_worktree(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """
        Test that the absolute common-dir path git prints inside a linked worktree is used as is
        """
        common = tmp_path / 'main-checkout' / '.git' / 'hooks'
        _write_shims(common, run.GIT_HOOK_TYPES)
        monkeypatch.setattr(run, 'DOTFILES_DIR', tmp_path / 'worktree')
        monkeypatch.setattr(run, '_capture', lambda cmd: _completed(0, f'{common}\n'))
        assert run.check_hooks().ok

    def test_fails_outside_a_git_checkout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that a failing git probe fails the check with git's message
        """
        monkeypatch.setattr(run, '_capture', lambda cmd: _completed(128, '', 'fatal: not a git repository\n'))

        check = run.check_hooks()
        assert not check.ok
        assert 'not a git repository' in check.detail

    def test_no_fix_when_prek_is_missing(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """
        Test that the check offers no fix (and says why) when prek is not on PATH
        """
        monkeypatch.setattr(run.shutil, 'which', lambda name: None)
        monkeypatch.setattr(run, '_capture', lambda cmd: _completed(0, f'{tmp_path / "hooks"}\n'))

        check = run.check_hooks()
        assert not check.ok
        assert check.fix is None
        assert 'prek not on PATH' in check.detail

    def test_probe_only_resolves_the_hooks_path(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """
        Test that the check runs a single read-only git probe
        """
        seen: list[list[str]] = []

        def fake_capture(cmd: list[str]) -> subprocess.CompletedProcess[str]:
            seen.append(cmd)
            return _completed(0, f'{tmp_path}\n')

        monkeypatch.setattr(run, '_capture', fake_capture)
        run.check_hooks()
        assert seen == [['git', 'rev-parse', '--git-path', 'hooks']]

    def test_hook_types_match_the_prek_config(self) -> None:
        """
        Test that GIT_HOOK_TYPES mirrors default_install_hook_types in .pre-commit-config.yaml
        """
        import yaml

        config = yaml.safe_load((run.DOTFILES_DIR / '.pre-commit-config.yaml').read_text(encoding='utf-8'))
        assert list(run.GIT_HOOK_TYPES) == config['default_install_hook_types']


class TestCheckBrewfiles:
    """
    Tests for the Brewfile drift doctor check
    """
    @staticmethod
    def _layers(tmp_path: Path, *, with_brewfile: tuple[bool, ...]) -> list[Path]:
        """
        Create one layer directory per flag, with a bootstrap/Brewfile where the flag is true
        """
        layers: list[Path] = []
        for index, has_brewfile in enumerate(with_brewfile):
            layer = tmp_path / f'layer{index}'
            (layer / 'bootstrap').mkdir(parents=True)
            if has_brewfile:
                (layer / 'bootstrap' / 'Brewfile').write_text('brew "jq"\n', encoding='utf-8')
            layers.append(layer)
        return layers

    @staticmethod
    def _capture_with(
        monkeypatch: pytest.MonkeyPatch,
        layers: list[Path],
        *,
        unsatisfied: set[Path] | None = None,
        layers_rc: int = 0,
    ) -> list[list[str]]:
        """
        Stub _capture: the layer probe lists ``layers``; ``brew bundle check`` fails for the ``unsatisfied`` Brewfiles
        """
        seen: list[list[str]] = []
        stdout = ''.join(f'{layer}\n' for layer in layers)

        def fake_capture(cmd: list[str]) -> subprocess.CompletedProcess[str]:
            seen.append(cmd)
            if cmd[:2] == ['bash', '-c']:
                return _completed(layers_rc, stdout)
            return _completed(1 if Path(cmd[-1]) in (unsatisfied or set()) else 0)

        monkeypatch.setattr(run, '_capture', fake_capture)
        monkeypatch.setattr(run.shutil, 'which', lambda name: f'/usr/bin/{name}')
        return seen

    def test_ok_when_every_brewfile_is_satisfied(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """
        Test that the check passes and counts only layers that declare a Brewfile
        """
        layers = self._layers(tmp_path, with_brewfile=(True, False, True))
        self._capture_with(monkeypatch, layers)

        check = run.check_brewfiles()
        assert check.ok
        assert check.detail == '2 Brewfile(s) satisfied'

    def test_ok_when_no_layer_declares_a_brewfile(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """
        Test that a repo without Brewfiles is not reported as drifted
        """
        self._capture_with(monkeypatch, self._layers(tmp_path, with_brewfile=(False,)))
        assert run.check_brewfiles().ok

    def test_drift_fails_names_the_brewfile_and_offers_a_bundle_fix(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """
        Test that only the unsatisfied Brewfile is named and fixed
        """
        layers  = self._layers(tmp_path, with_brewfile=(True, True))
        drifted = layers[1] / 'bootstrap' / 'Brewfile'
        self._capture_with(monkeypatch, layers, unsatisfied={drifted})

        check = run.check_brewfiles()
        assert not check.ok
        assert str(drifted) in check.detail
        assert str(layers[0] / 'bootstrap' / 'Brewfile') not in check.detail
        assert check.fix is not None
        assert check.fix[:2] == ['bash', '-c']
        assert 'brew bundle --file' in check.fix[2]
        assert check.fix[-1] == str(drifted)

    def test_probe_is_read_only(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """
        Test that the check only runs "brew bundle check" with auto-update disabled
        """
        layers = self._layers(tmp_path, with_brewfile=(True,))
        seen   = self._capture_with(monkeypatch, layers)

        run.check_brewfiles()
        brewfile = layers[0] / 'bootstrap' / 'Brewfile'
        assert seen[1:] == [['env', 'HOMEBREW_NO_AUTO_UPDATE=1', 'brew', 'bundle', 'check', '--file', str(brewfile)]]

    def test_fails_when_layers_cannot_be_enumerated(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """
        Test that a broken overlay registry fails the check without probing brew
        """
        seen = self._capture_with(monkeypatch, [], layers_rc=1)

        assert not run.check_brewfiles().ok
        assert len(seen) == 1

    def test_fails_when_brew_is_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that a missing brew is reported rather than raising FileNotFoundError
        """
        monkeypatch.setattr(run.shutil, 'which', lambda name: None)
        assert not run.check_brewfiles().ok


class TestDoctorCheckOrder:
    """
    Tests for the order and gating of the full doctor check list
    """
    def test_full_run_includes_hooks_and_brewfile_checks(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that the slow Brewfile check runs last and the hooks check follows the git version check
        """
        for func, name in {
            'check_tools':       'tools',
            'check_layers':      'layers',
            'check_git_version': 'git',
            'check_hooks':       'hooks',
            'check_links':       'links',
            'check_render':      'render',
            'check_brewfiles':   'brewfile',
        }.items():
            monkeypatch.setattr(run, func, lambda name=name: run.DoctorCheck(name, True, 'ok'))

        names = [c.name for c in run.doctor_checks()]
        assert names == ['tools', 'layers', 'git', 'hooks', 'links', 'render', 'brewfile']
