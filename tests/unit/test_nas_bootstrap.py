"""
Static guardrail tests for the NAS bootstrap entry point and its Ansible collection requirements
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# A fully-qualified collection module reference at the start of a task key (e.g. ``community.docker.docker_image:``);
# ``ansible.builtin`` ships with ansible-core and never needs installing
FQCN_MODULE = re.compile(r'^\s*(?:-\s+)?([a-z0-9_]+)\.([a-z0-9_]+)\.[a-z0-9_]+:', re.MULTILINE)

# A collection entry in requirements.yml (e.g. ``  - name: community.docker``)
REQUIREMENT = re.compile(r'^\s*-\s+name:\s*([a-z0-9_]+\.[a-z0-9_]+)\s*$', re.MULTILINE)

# The pinned Homebrew installer SHA-256 in nas_bootstrap.sh and in bootstrap/50-brew.sh (group 1 is the digest)
NAS_PIN  = re.compile(r'^\s*EXPECTED_CHECKSUM="([0-9a-f]{64})"', re.MULTILINE)
BREW_PIN = re.compile(r'^BREW_INSTALLER_SHA256="([0-9a-f]{64})"', re.MULTILINE)


class TestNasBootstrapScript:
    """
    Tests for nas_bootstrap.sh
    """
    SCRIPT = REPO_ROOT / 'nas_bootstrap.sh'

    def test_installer_is_not_a_predictable_tmp_path(self) -> None:
        """
        Test that the Homebrew installer is not written to a fixed /tmp path
        """
        text = self.SCRIPT.read_text(encoding='utf-8')
        assert '/tmp/brew-install.sh' not in text

    def test_installer_uses_mktemp_with_exit_trap(self) -> None:
        """
        Test that the installer is created with mktemp and removed by an EXIT trap
        """
        text = self.SCRIPT.read_text(encoding='utf-8')
        assert re.search(r'BREW_INSTALLER="\$\(mktemp ',                 text)
        assert re.search(r"^\s*trap 'rm -f \"\$BREW_INSTALLER\"' EXIT$", text, re.MULTILINE)

    def test_checksum_hint_names_this_script(self) -> None:
        """
        Test that the mismatch hint points at the file that defines EXPECTED_CHECKSUM
        """
        text = self.SCRIPT.read_text(encoding='utf-8')
        assert 'EXPECTED_CHECKSUM='                           in text
        assert 'Update EXPECTED_CHECKSUM in nas_bootstrap.sh' in text

    def test_installer_checksum_matches_macos_brew_stage(self) -> None:
        """
        Test that nas_bootstrap.sh and bootstrap/50-brew.sh pin the same Homebrew installer SHA-256
        """
        nas  = NAS_PIN.search(self.SCRIPT.read_text(encoding='utf-8'))
        brew = BREW_PIN.search((REPO_ROOT / 'bootstrap' / '50-brew.sh').read_text(encoding='utf-8'))

        assert nas,  'EXPECTED_CHECKSUM pin not found in nas_bootstrap.sh'
        assert brew, 'BREW_INSTALLER_SHA256 pin not found in bootstrap/50-brew.sh'
        assert nas.group(1) == brew.group(1)


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
