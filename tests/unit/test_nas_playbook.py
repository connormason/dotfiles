"""
Structural tests for the NAS playbook and its roles (no NAS needed): syntax, wiring, and the summary-line contract
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PLAYBOOK  = REPO_ROOT / 'playbooks' / 'nas_bootstrap.yml'
ROLES     = REPO_ROOT / 'roles'
LIB       = REPO_ROOT / 'bootstrap' / 'lib.sh'

ANSIBLE_PLAYBOOK = Path(sys.executable).parent / 'ansible-playbook'


def _role_defaults(role: str) -> dict[str, object]:
    """
    Load a role's defaults/main.yml
    """
    data = yaml.safe_load((ROLES / role / 'defaults' / 'main.yml').read_text(encoding='utf-8'))
    assert isinstance(data, dict)
    return data


def _role_task(role: str, name: str) -> dict[str, Any]:  # Any: heterogeneous, yaml-loaded task structure
    """
    Load the task with the given name from a role's tasks/main.yml
    """
    tasks = yaml.safe_load((ROLES / role / 'tasks' / 'main.yml').read_text(encoding='utf-8'))
    matches = [task for task in tasks if task.get('name') == name]
    assert len(matches) == 1, f'expected exactly one task named {name!r}'
    return matches[0]

class TestPlaybookSyntax:
    """
    Tests for the playbook as Ansible parses it
    """
    @pytest.mark.skipif(not ANSIBLE_PLAYBOOK.exists(), reason='ansible-playbook not in this environment')
    def test_syntax_check_passes(self, tmp_path: Path) -> None:
        """
        Test that ansible-playbook --syntax-check accepts the playbook (with a throwaway vault password file)
        """
        vault = tmp_path / 'vault-pass'
        vault.write_text('unused\n', encoding='utf-8')

        result = subprocess.run(
            [str(ANSIBLE_PLAYBOOK), '--syntax-check', '-i', 'localhost,', str(PLAYBOOK)],
            capture_output=True,
            text=True,
            check=False,
            cwd=REPO_ROOT,
            env={**os.environ, 'ANSIBLE_VAULT_PASSWORD_FILE': str(vault)},
            timeout=300,
        )
        assert result.returncode == 0, result.stdout + result.stderr


class TestDotfilesRole:
    """
    Tests for the dotfiles role's wiring
    """
    def test_overlay_is_the_nas_profile(self) -> None:
        """
        Test that the role registers profiles/nas and that the profile exists in the repo
        """
        assert _role_defaults('dotfiles')['dotfiles_overlays'] == ['{{ dotfiles_repo_dir }}/profiles/nas']
        assert (REPO_ROOT / 'profiles' / 'nas' / 'README.md').is_file()

    def test_nas_profile_is_a_valid_layer(self, tmp_path: Path) -> None:
        """
        Test that the engine accepts profiles/nas as an overlay
        """
        registry = tmp_path / 'overlays'
        registry.write_text(f'{REPO_ROOT / "profiles" / "nas"}\n', encoding='utf-8')

        result = subprocess.run(
            ['bash', '-c', f'source "{LIB}"; dotfiles_layers'],
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, 'DOTFILES_OVERLAYS_FILE': str(registry), 'HOME': str(tmp_path)},
            timeout=60,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.splitlines()[-1] == str((REPO_ROOT / 'profiles' / 'nas').resolve())

    def test_summary_line_contract(self) -> None:
        """
        Test that the role matches the exact line the driver prints
        """
        driver = (REPO_ROOT / 'bootstrap' / 'bootstrap.sh').read_text(encoding='utf-8')
        tasks  = (ROLES / 'dotfiles' / 'tasks' / 'main.yml').read_text(encoding='utf-8')
        assert "printf 'bootstrap: changes=%d\\n'" in driver
        assert "'bootstrap: changes=0'" in tasks
        assert "'^bootstrap: changes=[0-9]+$'" in tasks

    def test_play_defines_the_repo_dir(self) -> None:
        """
        Test that the play defines dotfiles_repo_dir for every role that needs it
        """
        play = yaml.safe_load(PLAYBOOK.read_text(encoding='utf-8'))[0]
        assert play['vars']['dotfiles_repo_dir'] == "{{ ansible_facts['user_dir'] }}/dotfiles-personal"

    def test_safety_assert_covers_every_probe(self) -> None:
        """
        Test that the refuse-to-update assert checks the status, remote-branch and local-branch ancestry probes
        """
        refuse = _role_task('dotfiles', 'Refuse to update a clone with local work')
        conditions = '\n'.join(refuse['ansible.builtin.assert']['that'])
        assert 'dotfiles_clone_status.stdout | length == 0' in conditions
        assert 'dotfiles_clone_remote.rc == 0' in conditions
        assert 'dotfiles_clone_remote.stdout | length > 0' in conditions
        assert 'dotfiles_clone_pushed.rc' in conditions

        pushed = _role_task('dotfiles', 'Check that the local version branch is pushed')
        argv = pushed['ansible.builtin.command']['argv']
        assert argv[-3:] == [
            '--is-ancestor',
            'refs/heads/{{ dotfiles_repo_version }}',
            'refs/remotes/origin/{{ dotfiles_repo_version }}',
        ]
        assert pushed['check_mode'] is False
        assert pushed['changed_when'] is False
        assert pushed['failed_when'] is False

    def test_login_shell_is_verified_before_it_is_set(self) -> None:
        """
        Test that the login shell is checked for existence, executability and /etc/shells ahead of the user task
        """
        tasks = yaml.safe_load((ROLES / 'dotfiles' / 'tasks' / 'main.yml').read_text(encoding='utf-8'))
        names = [task['name'] for task in tasks]
        assert names.index('Require a usable login shell') < names.index('Set the login shell')

        require = _role_task('dotfiles', 'Require a usable login shell')
        conditions = '\n'.join(require['ansible.builtin.assert']['that'])
        assert 'dotfiles_shell.stat.exists' in conditions
        assert 'dotfiles_shell.stat.executable' in conditions
        assert 'dotfiles_shell_listed.rc == 0' in conditions

    def test_engine_dry_run_only_under_check_or_preview(self) -> None:
        """
        Test that the engine argv adds --dry-run solely under check mode or the preview variable
        """
        engine = _role_task('dotfiles', 'Run the bootstrap engine')
        argv = engine['ansible.builtin.command']['argv']
        assert argv.count('--dry-run') == 1
        assert 'if (ansible_check_mode or dotfiles_bootstrap_preview | bool) else []' in argv
        assert engine['environment']['DOTFILES_OVERLAYS_FILE'] == '{{ dotfiles_overlays_file }}'
        assert engine['environment']['BOOTSTRAP_NONINTERACTIVE'] == '1'
        assert (engine['async'], engine['poll']) == (7200, 30)


class TestHaosRole:
    """
    Tests for the haos role's wiring
    """
    def test_runs_the_repo_script(self) -> None:
        """
        Test that the role runs vms/haos/setup.sh from the clone and that the script exists
        """
        assert _role_defaults('haos')['haos_setup_script'] == '{{ dotfiles_repo_dir }}/vms/haos/setup.sh'
        assert (REPO_ROOT / 'vms' / 'haos' / 'setup.sh').is_file()

    def test_never_runs_bridge_sh(self) -> None:
        """
        Test that no role task executes bridge.sh (it blips the network and would cut the Ansible session)
        """
        tasks = yaml.safe_load((ROLES / 'haos' / 'tasks' / 'main.yml').read_text(encoding='utf-8'))
        for task in tasks:
            for module in ('ansible.builtin.command', 'ansible.builtin.shell', 'ansible.builtin.script'):
                assert 'bridge.sh' not in str(task.get(module, ''))

    def test_summary_line_contract(self) -> None:
        """
        Test that the role matches the exact line setup.sh prints
        """
        setup = (REPO_ROOT / 'vms' / 'haos' / 'setup.sh').read_text(encoding='utf-8')
        tasks = (ROLES / 'haos' / 'tasks' / 'main.yml').read_text(encoding='utf-8')
        assert "printf 'haos: changes=%d\\n'" in setup
        assert "'haos: changes=0'" in tasks
        assert "'^haos: changes=[0-9]+$'" in tasks

    def test_setup_runs_async_and_dry_run_only_under_check(self) -> None:
        """
        Test that the setup task survives a dropped session and adds --dry-run solely under check mode
        """
        setup = _role_task('haos', 'Provision the Home Assistant OS VM')
        argv = setup['ansible.builtin.command']['argv']
        assert argv.count('--dry-run') == 1
        assert 'if ansible_check_mode else []' in argv
        assert setup['environment']['BRIDGE'] == '{{ haos_bridge }}'
        assert setup['become'] is True
        assert setup['check_mode'] is False
        assert (setup['async'], setup['poll']) == (3600, 15)

    def test_hardened_against_missing_results(self) -> None:
        """
        Test that the clone path is asserted first and the summary conditions tolerate an async timeout result
        """
        tasks = yaml.safe_load((ROLES / 'haos' / 'tasks' / 'main.yml').read_text(encoding='utf-8'))
        assert tasks[0]['name'] == 'Require the clone path'
        assert 'dotfiles_repo_dir is defined' in tasks[0]['ansible.builtin.assert']['that']

        setup = _role_task('haos', 'Provision the Home Assistant OS VM')
        assert 'rc | default(1)' in setup['failed_when']
        assert setup['failed_when'].count('stdout_lines | default([])') == 1
        assert 'stdout_lines | default([])' in setup['changed_when']
