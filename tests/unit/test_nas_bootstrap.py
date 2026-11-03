"""
Static guardrail tests for the NAS bootstrap entry point and its Ansible collection requirements
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# A fully-qualified collection module reference at the start of a task key (e.g. ``community.docker.docker_image:``);
# ``ansible.builtin`` ships with ansible-core and never needs installing
FQCN_MODULE = re.compile(r'^\s*(?:-\s+)?([a-z0-9_]+)\.([a-z0-9_]+)\.[a-z0-9_]+:', re.MULTILINE)

# A collection entry in requirements.yml (e.g. ``  - name: community.docker``)
REQUIREMENT = re.compile(r'^\s*-\s+name:\s*([a-z0-9_]+\.[a-z0-9_]+)\s*$', re.MULTILINE)

# The Homebrew installer download URL in bootstrap/50-brew.sh (group 1 is the URL)
BREW_URL = re.compile(r'^BREW_INSTALLER_URL="([^"]+)"$', re.MULTILINE)

# A commit-pinned upstream installer URL: the ref segment is a full 40-hex commit SHA, never a moving ref such as HEAD
COMMIT_PINNED_URL = re.compile(r'^https://raw\.githubusercontent\.com/Homebrew/install/[0-9a-f]{40}/install\.sh$')


class TestNasBootstrapScript:
    """
    Tests for nas_bootstrap.sh
    """
    SCRIPT = REPO_ROOT / 'nas_bootstrap.sh'

    def test_delegates_to_nas_provision_through_uv(self) -> None:
        """
        Test that the script hands every argument to run.py nas-provision through the public-index uv wrapper
        """
        text = self.SCRIPT.read_text(encoding='utf-8')
        assert re.search(
            r'^exec "\$\{SCRIPT_DIR\}/scripts/hooks/uv-public\.sh" run python "\$\{SCRIPT_DIR\}/run\.py" '
            r'nas-provision "\$@"$',
            text,
            re.MULTILINE,
        )

    def test_installs_nothing_on_the_controller(self) -> None:
        """
        Test that the Homebrew and Ansible installs, and their platform-specific paths, are gone
        """
        text = self.SCRIPT.read_text(encoding='utf-8').lower()
        for needle in ('brew', '/opt/', 'shasum', 'curl', 'ansible-playbook'):
            assert needle not in text, needle

    def test_still_validates_the_repository_layout(self) -> None:
        """
        Test that the script refuses to run outside the dotfiles directory
        """
        text = self.SCRIPT.read_text(encoding='utf-8')
        assert '"${SCRIPT_DIR}/run.py"' in text
        assert '"${SCRIPT_DIR}/playbooks"' in text

    def test_stops_with_a_clear_message_when_uv_is_missing(self, tmp_path: Path) -> None:
        """
        Test that a PATH without uv ends the script with exit 1 and a message naming uv, before any exec
        """
        bin_dir = tmp_path / 'bin'
        bin_dir.mkdir()
        (bin_dir / 'dirname').symlink_to(shutil.which('dirname') or '/usr/bin/dirname')

        result = subprocess.run(
            ['/bin/bash', str(self.SCRIPT)],
            capture_output=True,
            text=True,
            check=False,
            env={'PATH': str(bin_dir)},
        )

        assert result.returncode == 1
        assert 'uv is required' in result.stderr

    def test_uv_check_precedes_the_exec(self) -> None:
        """
        Test that the uv guard sits before the exec line, so a missing uv never reaches the wrapper
        """
        text = self.SCRIPT.read_text(encoding='utf-8')
        assert text.index('command -v uv') < text.index('exec "${SCRIPT_DIR}')


class TestBrewInstallerPin:
    """
    Tests for the Homebrew installer URL pinned in bootstrap/50-brew.sh
    """
    def test_installer_url_is_commit_pinned(self) -> None:
        """
        Test that the macOS brew stage downloads the installer from a 40-hex commit, never a moving ref
        """
        brew = BREW_URL.search((REPO_ROOT / 'bootstrap' / '50-brew.sh').read_text(encoding='utf-8'))

        assert brew, 'BREW_INSTALLER_URL not found in bootstrap/50-brew.sh'
        assert COMMIT_PINNED_URL.match(brew.group(1)), brew.group(1)
        assert '/HEAD/' not in brew.group(1)


class TestRolesRequirements:
    """
    Tests for roles/requirements.yml
    """
    def test_requirements_match_collections_used_by_roles_and_playbooks(self) -> None:
        """
        Test that requirements.yml lists exactly the external collections the roles and playbooks use
        """
        used: set[str] = set()
        for base in ('roles', 'playbooks'):
            for path in (REPO_ROOT / base).rglob('*.yml'):
                if path.name == 'requirements.yml':
                    continue
                for namespace, collection in FQCN_MODULE.findall(path.read_text(encoding='utf-8')):
                    if (namespace, collection) != ('ansible', 'builtin'):
                        used.add(f'{namespace}.{collection}')

        text = (REPO_ROOT / 'roles' / 'requirements.yml').read_text(encoding='utf-8')
        listed = set(REQUIREMENT.findall(text))

        assert used, 'expected at least one external collection to be in use'
        assert listed == used
