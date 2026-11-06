"""
Guardrail tests for the Homebrew installer pin and the NAS Ansible collection requirements

The checks are static: they read the brew stage script and the role and playbook files.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]

# A fully-qualified collection module reference at the start of a task key (e.g. ``community.docker.docker_image:``);
# ``ansible.builtin`` ships with ansible-core and never needs installing
FQCN_MODULE = re.compile(r'^\s*(?:-\s+)?([a-z0-9_]+)\.([a-z0-9_]+)\.[a-z0-9_]+:', re.MULTILINE)

# A collection entry in requirements.yml (e.g. ``  - name: community.docker``)
REQUIREMENT = re.compile(r'^\s*-\s+name:\s*([a-z0-9_]+\.[a-z0-9_]+)\s*$', re.MULTILINE)

# The Homebrew installer download URL in bootstrap/50-brew.sh (group 1 is the URL)
BREW_URL = re.compile(r'^BREW_INSTALLER_URL="([^"]+)"$', re.MULTILINE)

# A commit-pinned upstream installer URL: the ref segment is a full 40-hex commit SHA, never a moving ref such as HEAD
COMMIT_PINNED_URL = re.compile(r'^https://raw\.githubusercontent\.com/Homebrew/install/[0-9a-f]{40}/install\.sh$')


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
