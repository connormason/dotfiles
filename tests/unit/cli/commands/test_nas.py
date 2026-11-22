"""
Unit tests for the run.py NAS commands (nas-deploy, nas-provision) with shell_command faked out
"""
from __future__ import annotations

import argparse
import getpass
import json
import subprocess
import sys
from typing import TYPE_CHECKING
from typing import Any
from typing import ClassVar

import pytest

import cli.commands  # noqa: F401  (importing registers every command)
from cli.commands import deploy as deploy_commands
from cli.infra.command import REGISTERED_COMMANDS
from cli.infra.command import get_commands
from cli.infra.config import ANSIBLE_REQUIREMENTS
from cli.infra.config import DOTFILES_DIR
from cli.infra.config import INVENTORY_FILE
from cli.infra.config import NAS_BOOTSTRAP_PLAYBOOK
from cli.infra.config import NAS_DEPLOY_SCRIPT
from cli.infra.config import UV_PUBLIC_SCRIPT
from cli.infra.config import VAULT_PASSWORD
from cli.infra.config import ExitCode
from cli.infra.types import SSHTarget
from cli.utils import ansible as ansible_utils
from cli.utils import nas as nas_utils
from cli.utils.ansible import build_nas_provision_command
from cli.utils.ansible import resolve_ssh_target_from_inventory_host
from cli.utils.nas import list_services
from cli.utils.nas import require_nas_reachable
from cli.utils.nas import resolve_reachable_nas
from cli.utils.prompts import select_option
from cli.utils.styling import printf
from cli.utils.styling import unstyle

if TYPE_CHECKING:
    from pathlib import Path

# ==================================================================================================
# Helpers
# ==================================================================================================


def _done(returncode: int = 0, stdout: str = '', stderr: str = '') -> subprocess.CompletedProcess[str]:
    """
    Build a fake CompletedProcess
    """
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def _output(capsys: pytest.CaptureFixture[str]) -> str:
    """
    Return captured stdout with ANSI styling removed
    """
    return unstyle(capsys.readouterr().out)


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


# ==================================================================================================
# Fixtures
# ==================================================================================================


class FakeShell:
    """
    Stand-in for shell_command: records every call and answers from canned results keyed by a command element
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
    Replace shell_command with a recording fake in every module on the NAS command paths
    """
    fake = FakeShell()
    monkeypatch.setattr(ansible_utils,   'shell_command', fake)
    monkeypatch.setattr(nas_utils,       'shell_command', fake)
    monkeypatch.setattr(deploy_commands, 'shell_command', fake)
    return fake


# ==================================================================================================
# Unit tests
# ==================================================================================================


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
        printf('hello', file=recorder)

        assert recorder.events[-1] == 'flush'
        assert 'write' in recorder.events


class TestResolveNasTarget:
    """
    Tests for resolve_ssh_target_from_inventory_host
    """
    def test_reads_host_and_user_from_the_inventory(self, fake_shell: FakeShell) -> None:
        """
        Test that ansible_host and ansible_user come from ansible-inventory --host nas
        """
        fake_shell.results['ansible-inventory'] = _done(
            stdout=json.dumps({'ansible_host': 'nas.example.ts.net', 'ansible_user': 'tester'}),
        )
        assert resolve_ssh_target_from_inventory_host('nas') == ('nas.example.ts.net', 'tester')

        cmd, kwargs = fake_shell.find('ansible-inventory')
        assert cmd[cmd.index('--host') + 1] == 'nas'
        assert kwargs['capture_output'] is True
        assert kwargs['cwd']            == DOTFILES_DIR

    def test_falls_back_to_the_host_name_and_local_user(
        self,
        fake_shell: FakeShell,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Test that missing variables fall back to the inventory name and the local login, as ssh would
        """
        fake_shell.results['ansible-inventory'] = _done(stdout='{}')
        monkeypatch.setattr(getpass, 'getuser', lambda: 'local')
        assert resolve_ssh_target_from_inventory_host('nas') == ('nas', 'local')

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
            resolve_ssh_target_from_inventory_host('nas')

        assert exc_info.value.code == 1
        assert 'bad vault password' in _output(capsys)

    def test_unparseable_output_exits(self, fake_shell: FakeShell, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that non-JSON ansible-inventory output exits 1
        """
        fake_shell.results['ansible-inventory'] = _done(stdout='not json')

        with pytest.raises(SystemExit) as exc_info:
            resolve_ssh_target_from_inventory_host('nas')

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
            resolve_ssh_target_from_inventory_host('nas')

        assert exc_info.value.code == 1
        assert 'Unexpected ansible-inventory output for host "nas"' in _output(capsys)

    def test_templated_values_are_rejected(self, fake_shell: FakeShell, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that a Jinja-templated ansible_host is refused with a hint to use a literal value
        """
        fake_shell.results['ansible-inventory'] = _done(stdout=json.dumps({'ansible_host': '{{ nas_ip }}'}))

        with pytest.raises(SystemExit) as exc_info:
            resolve_ssh_target_from_inventory_host('nas')

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
        require_nas_reachable('nas.example', 'tester')

        cmd, kwargs = fake_shell.find('ssh')
        assert cmd == ['ssh', '-o', 'ConnectTimeout=5', '-o', 'BatchMode=yes', 'tester@nas.example', 'true']
        assert kwargs['capture_output'] is True

    def test_failure_names_the_likely_causes(self, fake_shell: FakeShell, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that an unreachable NAS exits 1 and mentions Tailscale and ssh's own error
        """
        fake_shell.results['ssh'] = _done(255, stderr='Connection timed out')

        with pytest.raises(SystemExit) as exc_info:
            require_nas_reachable('nas.example', 'tester')

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

        def resolve(host: str) -> SSHTarget:
            order.append('resolve')
            return SSHTarget('h', 'u')

        monkeypatch.setattr(nas_utils, 'require_inventory',                      check_inventory)
        monkeypatch.setattr(nas_utils, 'require_vault_password',                 check_vault)
        monkeypatch.setattr(nas_utils, 'resolve_ssh_target_from_inventory_host', resolve)

        assert resolve_reachable_nas() == ('h', 'u')
        assert order == ['inventory', 'vault', 'resolve']
        assert fake_shell.find('ssh')[0][-2] == 'u@h'


class TestListServices:
    """
    Tests for list_services
    """
    def test_lists_directories_that_hold_a_compose_file(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Test that only service directories with a compose.yml are listed, sorted by name
        """
        for name in ('plex', 'glance'):
            (tmp_path / name).mkdir()
            (tmp_path / name / 'compose.yml').write_text('services: {}\n')

        (tmp_path / 'empty').mkdir()
        (tmp_path / 'compose.base.yml').write_text('services: {}\n')
        monkeypatch.setattr(nas_utils, 'SERVICES_DIR', tmp_path)

        assert list_services() == ['glance', 'plex']

    def test_matches_the_services_in_the_repo(self) -> None:
        """
        Test that the real services/ tree yields services and never the shared base file
        """
        services = list_services()
        assert 'glance'               in services
        assert 'compose.base.yml' not in services
        assert services == sorted(services)


class TestSelectOption:
    """
    Tests for select_option
    """
    @staticmethod
    def _answer(monkeypatch: pytest.MonkeyPatch, *answers: str) -> None:
        """
        Feed the given answers to input(), raising EOFError once they run out
        """
        remaining = iter(answers)

        def fake_input(_prompt: str = '') -> str:
            try:
                return next(remaining)
            except StopIteration:
                raise EOFError from None

        monkeypatch.setattr('builtins.input', fake_input)

    @pytest.mark.parametrize(
        ('answer', 'expected'),
        [
            ('1',     'all'),
            ('3',     'caddy'),
            (' 2 ',   'autoplex'),
            ('caddy', 'caddy'),
            ('all',   'all'),
        ],
    )
    def test_accepts_a_number_or_a_name(
        self,
        monkeypatch: pytest.MonkeyPatch,
        answer: str,
        expected: str,
    ) -> None:
        """
        Test that an entry selects the option by its 1-based number or by its exact name
        """
        self._answer(monkeypatch, answer)
        assert select_option('Pick one:', ['all', 'autoplex', 'caddy']) == expected

    @pytest.mark.parametrize('bad_answer', ['0', '4', '-1', 'plex', 'CADDY'])
    def test_reprompts_on_an_unrecognized_entry(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        bad_answer: str,
    ) -> None:
        """
        Test that an out-of-range number or unknown name is reported and the prompt repeats
        """
        self._answer(monkeypatch, bad_answer, '2')

        assert select_option('Pick one:', ['all', 'autoplex', 'caddy']) == 'autoplex'
        assert f'Not a valid choice: {bad_answer}' in _output(capsys)

    def test_lists_every_option_with_its_number(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that the heading and the numbered options are printed before the prompt
        """
        self._answer(monkeypatch, '1')
        select_option('Pick one:', ['all', 'caddy'])

        lines = [line.strip() for line in _output(capsys).splitlines()]
        assert lines[:3] == ['Pick one:', '1) all', '2) caddy']

    def test_empty_entry_cancels(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that pressing Enter without typing selects nothing
        """
        self._answer(monkeypatch, '')
        assert select_option('Pick one:', ['all']) is None

    def test_closed_stdin_cancels(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that EOF selects nothing instead of raising
        """
        self._answer(monkeypatch)
        assert select_option('Pick one:', ['all']) is None


class TestNasDeploy:
    """
    Tests for the nas-deploy command
    """
    @pytest.fixture(autouse=True)
    def _target(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Skip inventory resolution and the SSH probe
        """
        monkeypatch.setattr(deploy_commands, 'resolve_reachable_nas', lambda: ('h', 'u'))

    def test_registered_in_the_deploy_group_and_makefile(self) -> None:
        """
        Test that nas-deploy is grouped under Bootstrap & Deploy and gets a Makefile target (its service is optional)
        """
        cmd = REGISTERED_COMMANDS['nas-deploy']
        assert cmd.group       == 'Bootstrap & Deploy'
        assert cmd.script_only is False

    def test_service_argument_is_optional(self) -> None:
        """
        Test that the parser accepts nas-deploy with and without a service
        """
        parser = argparse.ArgumentParser()
        get_commands()['nas-deploy'].add_arguments(parser)

        assert parser.parse_args([]).service            is None
        assert parser.parse_args(['glance']).service    == 'glance'
        assert parser.parse_args(['--dry-run']).dry_run is True

    def test_prompts_for_a_service_when_none_is_given(
        self,
        fake_shell: FakeShell,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Test that the chosen service is deployed, with 'all' offered first and every service listed after it
        """
        offered: list[list[str]] = []

        def choose(_prompt: str, options: list[str]) -> str:
            offered.append(options)
            return options[-1]

        monkeypatch.setattr(sys.stdin,       'isatty',        lambda: True)
        monkeypatch.setattr(deploy_commands, 'list_services', lambda: ['caddy', 'glance'])
        monkeypatch.setattr(deploy_commands, 'select_option', choose)

        with pytest.raises(SystemExit) as exc_info:
            get_commands()['nas-deploy'](argparse.Namespace(service=None, dry_run=False))

        assert exc_info.value.code == 0
        assert offered             == [['all', 'caddy', 'glance']]
        assert fake_shell.find('bash')[0] == ['bash', str(NAS_DEPLOY_SCRIPT), 'glance']

    def test_a_given_service_skips_the_prompt(self, fake_shell: FakeShell, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that naming a service never prompts, even on a terminal
        """
        def unexpected(*_args: object, **_kwargs: object) -> str:
            raise AssertionError('the prompt must not run when a service is given')

        monkeypatch.setattr(sys.stdin,       'isatty',        lambda: True)
        monkeypatch.setattr(deploy_commands, 'select_option', unexpected)

        with pytest.raises(SystemExit):
            get_commands()['nas-deploy'](argparse.Namespace(service='glance', dry_run=False))

        assert fake_shell.find('bash')[0][-1] == 'glance'

    def test_cancelling_the_prompt_deploys_nothing(
        self,
        fake_shell: FakeShell,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that an empty answer exits as user-cancelled before the NAS is probed or anything runs
        """
        monkeypatch.setattr(sys.stdin,       'isatty',        lambda: True)
        monkeypatch.setattr(deploy_commands, 'select_option', lambda *_args, **_kwargs: None)

        with pytest.raises(SystemExit) as exc_info:
            get_commands()['nas-deploy'](argparse.Namespace(service=None, dry_run=False))

        assert exc_info.value.code == ExitCode.USER_CANCELLED
        assert 'Cancelled' in _output(capsys)
        assert fake_shell.calls == []

    def test_no_service_without_a_terminal_fails_instead_of_hanging(
        self,
        fake_shell: FakeShell,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that a missing service with no terminal to prompt on exits 1 with a remedy
        """
        monkeypatch.setattr(sys.stdin, 'isatty', lambda: False)

        with pytest.raises(SystemExit) as exc_info:
            get_commands()['nas-deploy'](argparse.Namespace(service=None, dry_run=False))

        assert exc_info.value.code == ExitCode.COMMAND_FAILED
        assert "pass a service or 'all'" in _output(capsys)
        assert fake_shell.calls == []

    def test_runs_the_shared_script_with_the_resolved_target(self, fake_shell: FakeShell) -> None:
        """
        Test that the script runs with NAS_HOST and NAS_USER from the inventory and its status is the exit code
        """
        fake_shell.results['bash'] = _done(3)

        with pytest.raises(SystemExit) as exc_info:
            get_commands()['nas-deploy'](argparse.Namespace(service='glance', dry_run=False))

        cmd, kwargs = fake_shell.find('bash')
        assert exc_info.value.code == 3
        assert cmd == ['bash', str(NAS_DEPLOY_SCRIPT), 'glance']
        assert kwargs['env']   == {'NAS_HOST': 'h', 'NAS_USER': 'u'}
        assert kwargs['check'] is False

    def test_dry_run_flag_precedes_the_service(self, fake_shell: FakeShell) -> None:
        """
        Test that --dry-run is forwarded ahead of the service name
        """
        with pytest.raises(SystemExit):
            get_commands()['nas-deploy'](argparse.Namespace(service='all', dry_run=True))

        assert fake_shell.find('bash')[0] == ['bash', str(NAS_DEPLOY_SCRIPT), '--dry-run', 'all']

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
            get_commands()['nas-deploy'](argparse.Namespace(service='glance', dry_run=False))

        assert exc_info.value.code == 0
        assert 'uncommitted' in _output(capsys)
        fake_shell.find('bash')

    def test_clean_tree_prints_no_warning(self, fake_shell: FakeShell, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that a clean services/ tree produces no warning
        """
        with pytest.raises(SystemExit):
            get_commands()['nas-deploy'](argparse.Namespace(service='glance', dry_run=False))
        assert 'uncommitted' not in _output(capsys)


class TestBuildNasProvisionCommand:
    """
    Tests for build_nas_provision_command
    """
    BASE: ClassVar[list[str]] = [
        str(UV_PUBLIC_SCRIPT), 'run', 'ansible-playbook', str(NAS_BOOTSTRAP_PLAYBOOK),
        '-i', str(INVENTORY_FILE),
        '--vault-password-file', str(VAULT_PASSWORD),
    ]

    def test_defaults_run_the_whole_playbook(self) -> None:
        """
        Test that no options yield only the playbook, inventory, and vault password file
        """
        assert build_nas_provision_command(_provision_args()) == self.BASE

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

        assert build_nas_provision_command(args) == [
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
            build_nas_provision_command(_provision_args(extra_vars=['oops']))


class TestNasProvision:
    """
    Tests for the nas-provision command
    """
    @pytest.fixture(autouse=True)
    def _target(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Skip inventory resolution and the SSH probe
        """
        monkeypatch.setattr(deploy_commands, 'resolve_reachable_nas', lambda: ('h', 'u'))

    def test_registered_in_the_nas_group_and_makefile(self) -> None:
        """
        Test that nas-provision is a NAS command that also gets a Makefile target
        """
        cmd = REGISTERED_COMMANDS['nas-provision']
        assert cmd.group       == 'Bootstrap & Deploy'
        assert cmd.script_only is False

    def test_installs_collections_then_runs_the_playbook_from_the_repo_root(self, fake_shell: FakeShell) -> None:
        """
        Test that galaxy runs before the playbook, both from the repo root, and the playbook status is the exit code
        """
        fake_shell.results['ansible-playbook'] = _done(4)

        with pytest.raises(SystemExit) as exc_info:
            get_commands()['nas-provision'](_provision_args(tags='services'))

        assert exc_info.value.code == 4
        assert [call[0][2] for call in fake_shell.calls] == ['ansible-galaxy', 'ansible-playbook']

        galaxy, galaxy_kwargs = fake_shell.find('ansible-galaxy')
        assert galaxy[-2:] == ['-r', str(ANSIBLE_REQUIREMENTS)]

        _playbook, playbook_kwargs = fake_shell.find('ansible-playbook')
        assert galaxy_kwargs['cwd'] == playbook_kwargs['cwd'] == DOTFILES_DIR

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
            get_commands()['nas-provision'](_provision_args())

        assert exc_info.value.code == 0
        assert 'Collection install failed' in _output(capsys)
        fake_shell.find('ansible-playbook')

    def test_unreachable_nas_stops_before_ansible(self, fake_shell: FakeShell, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that a failed preflight exits without installing collections or running the playbook
        """
        def unreachable() -> tuple[str, str]:
            raise SystemExit(1)

        monkeypatch.setattr(deploy_commands, 'resolve_reachable_nas', unreachable)

        with pytest.raises(SystemExit) as exc_info:
            get_commands()['nas-provision'](_provision_args())

        assert exc_info.value.code == 1
        assert fake_shell.calls == []

    def test_bad_extra_var_exits_before_the_preflight(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that command construction (and its validation) happens before any network probe
        """
        probed: list[bool] = []

        def probe() -> tuple[str, str]:
            probed.append(True)
            return SSHTarget('h', 'u')

        monkeypatch.setattr(deploy_commands, 'resolve_reachable_nas', probe)

        with pytest.raises(SystemExit):
            get_commands()['nas-provision'](_provision_args(extra_vars=['oops']))

        assert probed == []
