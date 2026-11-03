"""
Unit tests for the run.py NAS commands (nas-deploy, nas-provision) with shell_command faked out
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from typing import ClassVar

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import run


def _done(returncode: int = 0, stdout: str = '', stderr: str = '') -> subprocess.CompletedProcess[str]:
    """
    Build a fake CompletedProcess
    """
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


class FakeShell:
    """
    Stand-in for run.shell_command: records every call and answers from canned results keyed by a command element
    """
    def __init__(self) -> None:
        self.results: dict[str, subprocess.CompletedProcess[str]] = {}
        self.calls:   list[tuple[list[str], dict[str, Any]]]      = []  # Any: mirrors shell_command's **kwargs

    def __call__(self, cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:  # Any: see above
        self.calls.append((cmd, kwargs))
        for token, result in self.results.items():
            if token in cmd:
                return result
        return _done()

    def find(self, token: str) -> tuple[list[str], dict[str, Any]]:  # Any: see above
        """
        Return the single recorded call whose command contains token
        """
        matches = [call for call in self.calls if token in call[0]]
        assert len(matches) == 1, f'expected exactly one {token!r} call, got {len(matches)}'
        return matches[0]


@pytest.fixture
def fake_shell(monkeypatch: pytest.MonkeyPatch) -> FakeShell:
    """
    Replace run.shell_command with a recording fake
    """
    fake = FakeShell()
    monkeypatch.setattr(run, 'shell_command', fake)
    return fake


def _output(capsys: pytest.CaptureFixture[str]) -> str:
    """
    Return captured stdout with ANSI styling removed
    """
    return run.unstyle(capsys.readouterr().out)


class TestPrintfFlush:
    """
    Tests for printf's flushing
    """
    def test_flushes_so_output_stays_ordered_with_child_processes(self) -> None:
        """
        Test that printf flushes after writing

        Python block-buffers a pipe (`| tee`) while subprocesses write to it directly, so an unflushed status line
        lands after the output of commands that ran later
        """
        class Recorder:
            def __init__(self) -> None:
                self.events: list[str] = []

            def write(self, text: str, /) -> int:
                self.events.append('write')
                return len(text)

            def flush(self) -> None:
                self.events.append('flush')

        recorder = Recorder()
        run.printf('hello', file=recorder)

        assert recorder.events[-1] == 'flush'
        assert 'write' in recorder.events


class TestResolveNasTarget:
    """
    Tests for resolve_nas_target
    """
    def test_reads_host_and_user_from_the_inventory(self, fake_shell: FakeShell) -> None:
        """
        Test that ansible_host and ansible_user come from ansible-inventory --host nas
        """
        fake_shell.results['ansible-inventory'] = _done(
            stdout=json.dumps({'ansible_host': 'nas.example.ts.net', 'ansible_user': 'tester'}),
        )

        assert run.resolve_nas_target() == ('nas.example.ts.net', 'tester')

        cmd, kwargs = fake_shell.find('ansible-inventory')
        assert cmd[cmd.index('--host') + 1] == 'nas'
        assert kwargs['capture_output'] is True
        assert kwargs['cwd']            == run.DOTFILES_DIR

    def test_falls_back_to_the_host_name_and_local_user(
        self,
        fake_shell: FakeShell,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Test that missing variables fall back to the inventory name and the local login, as ssh would
        """
        fake_shell.results['ansible-inventory'] = _done(stdout='{}')
        monkeypatch.setattr(run.getpass, 'getuser', lambda: 'local')
        assert run.resolve_nas_target() == ('nas', 'local')

    def test_inventory_failure_exits_with_the_error(
        self,
        fake_shell: FakeShell,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that an ansible-inventory failure exits 1 and shows its stderr
        """
        fake_shell.results['ansible-inventory'] = _done(1, stderr='bad vault password')

        with pytest.raises(SystemExit) as exc_info:
            run.resolve_nas_target()

        assert exc_info.value.code == 1
        assert 'bad vault password' in _output(capsys)

    def test_unparseable_output_exits(self, fake_shell: FakeShell, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that non-JSON ansible-inventory output exits 1
        """
        fake_shell.results['ansible-inventory'] = _done(stdout='not json')

        with pytest.raises(SystemExit) as exc_info:
            run.resolve_nas_target()

        assert exc_info.value.code == 1
        assert 'Unexpected' in _output(capsys)

    @pytest.mark.parametrize('stdout', ['[]', 'null', '"nas"', '42'])
    def test_valid_json_that_is_not_an_object_exits(
        self,
        fake_shell: FakeShell,
        capsys: pytest.CaptureFixture[str],
        stdout: str,
    ) -> None:
        """
        Test that valid JSON other than an object exits 1 as unexpected output instead of crashing on a missing .get
        """
        fake_shell.results['ansible-inventory'] = _done(stdout=stdout)

        with pytest.raises(SystemExit) as exc_info:
            run.resolve_nas_target()

        assert exc_info.value.code == 1
        assert 'Unexpected ansible-inventory output for host "nas"' in _output(capsys)

    def test_templated_values_are_rejected(self, fake_shell: FakeShell, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that a Jinja-templated ansible_host is refused with a hint to use a literal value
        """
        fake_shell.results['ansible-inventory'] = _done(stdout=json.dumps({'ansible_host': '{{ nas_ip }}'}))

        with pytest.raises(SystemExit) as exc_info:
            run.resolve_nas_target()

        assert exc_info.value.code == 1
        assert 'literal' in _output(capsys)


class TestRequireNasReachable:
    """
    Tests for require_nas_reachable
    """
    def test_probes_over_ssh_with_a_short_timeout(self, fake_shell: FakeShell) -> None:
        """
        Test that a successful probe returns quietly after one non-interactive ssh call
        """
        run.require_nas_reachable('nas.example', 'tester')

        cmd, kwargs = fake_shell.find('ssh')
        assert cmd == ['ssh', '-o', 'ConnectTimeout=5', '-o', 'BatchMode=yes', 'tester@nas.example', 'true']
        assert kwargs['capture_output'] is True

    def test_failure_names_the_likely_causes(self, fake_shell: FakeShell, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that an unreachable NAS exits 1 and mentions Tailscale and ssh's own error
        """
        fake_shell.results['ssh'] = _done(255, stderr='Connection timed out')

        with pytest.raises(SystemExit) as exc_info:
            run.require_nas_reachable('nas.example', 'tester')

        out = _output(capsys)
        assert exc_info.value.code == 1
        assert 'Tailscale'            in out
        assert 'Connection timed out' in out


class TestResolveReachableNas:
    """
    Tests for resolve_reachable_nas
    """
    def test_checks_files_resolves_then_probes(self, fake_shell: FakeShell, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that the inventory and vault checks run before resolution, and the probe uses the resolved target
        """
        order: list[str] = []

        def check_inventory() -> None:
            order.append('inventory')

        def check_vault() -> None:
            order.append('vault')

        def resolve() -> tuple[str, str]:
            order.append('resolve')
            return 'h', 'u'

        monkeypatch.setattr(run, 'require_inventory',      check_inventory)
        monkeypatch.setattr(run, 'require_vault_password', check_vault)
        monkeypatch.setattr(run, 'resolve_nas_target',     resolve)

        assert run.resolve_reachable_nas() == ('h', 'u')
        assert order == ['inventory', 'vault', 'resolve']
        assert fake_shell.find('ssh')[0][-2] == 'u@h'


class TestNasDeploy:
    """
    Tests for the nas-deploy command
    """
    @pytest.fixture(autouse=True)
    def _target(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Skip inventory resolution and the SSH probe
        """
        monkeypatch.setattr(run, 'resolve_reachable_nas', lambda: ('h', 'u'))

    def test_registered_as_a_script_only_nas_command(self) -> None:
        """
        Test that nas-deploy is grouped under NAS and kept out of the Makefile (its argument is required)
        """
        info = run.REGISTERED_COMMANDS['nas-deploy']
        assert info.group       == 'NAS'
        assert info.script_only is True

    def test_runs_the_shared_script_with_the_resolved_target(self, fake_shell: FakeShell) -> None:
        """
        Test that the script runs with NAS_HOST and NAS_USER from the inventory and its status is the exit code
        """
        fake_shell.results['bash'] = _done(3)

        with pytest.raises(SystemExit) as exc_info:
            run.cmd_nas_deploy(argparse.Namespace(service='glance', dry_run=False))

        cmd, kwargs = fake_shell.find('bash')
        assert exc_info.value.code == 3
        assert cmd == ['bash', str(run.NAS_DEPLOY_SCRIPT), 'glance']
        assert kwargs['env']   == {'NAS_HOST': 'h', 'NAS_USER': 'u'}
        assert kwargs['check'] is False

    def test_dry_run_flag_precedes_the_service(self, fake_shell: FakeShell) -> None:
        """
        Test that --dry-run is forwarded ahead of the service name
        """
        with pytest.raises(SystemExit):
            run.cmd_nas_deploy(argparse.Namespace(service='all', dry_run=True))

        assert fake_shell.find('bash')[0] == ['bash', str(run.NAS_DEPLOY_SCRIPT), '--dry-run', 'all']

    def test_warns_about_a_dirty_services_tree_and_still_deploys(
        self,
        fake_shell: FakeShell,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that uncommitted changes under services/ warn but do not block the deploy
        """
        fake_shell.results['git'] = _done(stdout=' M services/glance/compose.yml\n')

        with pytest.raises(SystemExit) as exc_info:
            run.cmd_nas_deploy(argparse.Namespace(service='glance', dry_run=False))

        assert exc_info.value.code == 0
        assert 'uncommitted' in _output(capsys)
        fake_shell.find('bash')

    def test_clean_tree_prints_no_warning(self, fake_shell: FakeShell, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that a clean services/ tree produces no warning
        """
        with pytest.raises(SystemExit):
            run.cmd_nas_deploy(argparse.Namespace(service='glance', dry_run=False))
        assert 'uncommitted' not in _output(capsys)


def _provision_args(**overrides: Any) -> argparse.Namespace:  # Any: free-form Namespace field overrides
    """
    Build the Namespace nas-provision receives, with every option at its default unless overridden
    """
    fields: dict[str, Any] = {  # Any: heterogeneous Namespace fields
        'tags':       None,
        'limit':      None,
        'check':      False,
        'diff':       False,
        'extra_vars': None,
        'verbose':    0,
    }
    fields.update(overrides)
    return argparse.Namespace(**fields)


class TestBuildNasProvisionCommand:
    """
    Tests for build_nas_provision_command
    """
    BASE: ClassVar[list[str]] = [
        str(run.UV_PUBLIC), 'run', 'ansible-playbook', str(run.NAS_PLAYBOOK),
        '-i', str(run.INVENTORY_FILE),
        '--vault-password-file', str(run.VAULT_PASSWORD),
    ]

    def test_defaults_run_the_whole_playbook(self) -> None:
        """
        Test that no options yield only the playbook, inventory, and vault password file
        """
        assert run.build_nas_provision_command(_provision_args()) == self.BASE

    def test_every_option_is_forwarded(self) -> None:
        """
        Test that tags, limit, check, diff, extra vars, and verbosity map to ansible-playbook flags
        """
        args = _provision_args(
            tags='dotfiles,haos',
            limit='nas',
            check=True,
            diff=True,
            extra_vars=['a=1', 'b=two'],
            verbose=2,
        )

        assert run.build_nas_provision_command(args) == [
            *self.BASE,
            '--tags', 'dotfiles,haos',
            '--limit', 'nas',
            '--check',
            '--diff',
            '-e', 'a=1',
            '-e', 'b=two',
            '-vv',
        ]

    def test_malformed_extra_var_exits(self) -> None:
        """
        Test that an extra var without '=' is rejected before anything runs
        """
        with pytest.raises(SystemExit):
            run.build_nas_provision_command(_provision_args(extra_vars=['oops']))


class TestNasProvision:
    """
    Tests for the nas-provision command
    """
    @pytest.fixture(autouse=True)
    def _target(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Skip inventory resolution and the SSH probe
        """
        monkeypatch.setattr(run, 'resolve_reachable_nas', lambda: ('h', 'u'))

    def test_registered_in_the_nas_group_and_makefile(self) -> None:
        """
        Test that nas-provision is a NAS command that also gets a Makefile target
        """
        info = run.REGISTERED_COMMANDS['nas-provision']
        assert info.group       == 'NAS'
        assert info.script_only is False

    def test_installs_collections_then_runs_the_playbook_from_the_repo_root(self, fake_shell: FakeShell) -> None:
        """
        Test that galaxy runs before the playbook, both from the repo root, and the playbook status is the exit code
        """
        fake_shell.results['ansible-playbook'] = _done(4)

        with pytest.raises(SystemExit) as exc_info:
            run.cmd_nas_provision(_provision_args(tags='services'))

        assert exc_info.value.code == 4
        assert [call[0][2] for call in fake_shell.calls] == ['ansible-galaxy', 'ansible-playbook']

        galaxy, galaxy_kwargs = fake_shell.find('ansible-galaxy')
        assert galaxy[-2:] == ['-r', str(run.NAS_REQUIREMENTS)]

        _playbook, playbook_kwargs = fake_shell.find('ansible-playbook')
        assert galaxy_kwargs['cwd'] == playbook_kwargs['cwd'] == run.DOTFILES_DIR

    def test_collection_install_failure_warns_and_continues(
        self,
        fake_shell: FakeShell,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that an offline collection install does not block a run with collections already installed
        """
        fake_shell.results['ansible-galaxy'] = _done(1)

        with pytest.raises(SystemExit) as exc_info:
            run.cmd_nas_provision(_provision_args())

        assert exc_info.value.code == 0
        assert 'Collection install failed' in _output(capsys)
        fake_shell.find('ansible-playbook')

    def test_unreachable_nas_stops_before_ansible(self, fake_shell: FakeShell, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that a failed preflight exits without installing collections or running the playbook
        """
        def unreachable() -> tuple[str, str]:
            raise SystemExit(1)

        monkeypatch.setattr(run, 'resolve_reachable_nas', unreachable)

        with pytest.raises(SystemExit) as exc_info:
            run.cmd_nas_provision(_provision_args())

        assert exc_info.value.code == 1
        assert fake_shell.calls == []

    def test_bad_extra_var_exits_before_the_preflight(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that command construction (and its validation) happens before any network probe
        """
        probed: list[bool] = []

        def probe() -> tuple[str, str]:
            probed.append(True)
            return 'h', 'u'

        monkeypatch.setattr(run, 'resolve_reachable_nas', probe)

        with pytest.raises(SystemExit):
            run.cmd_nas_provision(_provision_args(extra_vars=['oops']))

        assert probed == []
