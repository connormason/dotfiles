"""
Structural tests for the NAS playbook and its roles (no NAS needed): syntax, wiring, and the summary-line contract
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

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
