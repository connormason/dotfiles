"""
Unit tests for the overlay profiles under profiles/
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT     = Path(__file__).resolve().parents[2]
LIB           = REPO_ROOT / 'bootstrap' / 'lib.sh'
PROFILE       = REPO_ROOT / 'profiles' / 'personal-mac'
BASE_BREWFILE = REPO_ROOT / 'bootstrap' / 'Brewfile'

# Inherited variables that would leak the developer's own configuration into the tests
_SCRUBBED_VARS = ('DOTFILES_REPO', 'DOTFILES_BREW_PREFIXES', 'DOTFILES_LEAK_PATTERNS', 'DOTFILES_OVERLAYS_FILE')

# `<kind> "<name>"` as written in a Brewfile (taps, formulae, casks, mas apps)
_ENTRY = re.compile(r'^(tap|brew|cask|mas)\s+"([^"]+)"')


def _entries(brewfile: Path) -> list[tuple[str, str]]:
    """
    Parse the (kind, name) pairs of every non-comment Brewfile line
    """
    entries: list[tuple[str, str]] = []
    for line in brewfile.read_text(encoding='utf-8').splitlines():
        if match := _ENTRY.match(line.strip()):
            entries.append((match.group(1), match.group(2)))
    return entries


class TestPersonalMacProfile:
    """
    Tests for profiles/personal-mac
    """
    def test_manifest_files_lists_base_then_profile(self, shell: str, tmp_path: Path) -> None:
        """
        Test that registering the profile makes manifest_files list the base Brewfile and then the profile Brewfile
        """
        home = tmp_path / 'home'
        home.mkdir()

        registry = tmp_path / 'overlays'
        registry.write_text(f'{PROFILE}\n', encoding='utf-8')

        env: dict[str, str] = {
            **{key: value for key, value in os.environ.items() if key not in _SCRUBBED_VARS},
            'HOME':                   str(home),
            'XDG_CONFIG_HOME':        str(home / '.config'),
            'DOTFILES_OVERLAYS_FILE': str(registry),
            'BOOTSTRAP_DRY_RUN':      '0',
        }
        result = subprocess.run(
            [shell, '-c', f'source "{LIB}"\nmanifest_files Brewfile'],
            capture_output=True,
            text=True,
            check=False,
            env=env,
            timeout=60,
        )

        assert result.returncode == 0, result.stderr
        assert result.stdout.splitlines() == [
            str(REPO_ROOT / 'bootstrap' / 'Brewfile'),
            str(PROFILE.resolve() / 'bootstrap' / 'Brewfile'),
        ]

    def test_brewfile_has_entries(self) -> None:
        """
        Test that the profile Brewfile declares at least one entry
        """
        assert _entries(PROFILE / 'bootstrap' / 'Brewfile')

    def test_brewfile_does_not_duplicate_base(self) -> None:
        """
        Test that no profile Brewfile entry repeats a base Brewfile entry
        """
        assert _entries(BASE_BREWFILE), 'base Brewfile parsed as empty; the comparison below would pass vacuously'

        duplicates = set(_entries(PROFILE / 'bootstrap' / 'Brewfile')) & set(_entries(BASE_BREWFILE))
        assert not duplicates, f'already in bootstrap/Brewfile: {sorted(duplicates)}'

    @pytest.mark.parametrize(
        'name',
        ['README.md', 'bootstrap/Brewfile'],
    )
    def test_profile_files_exist(self, name: str) -> None:
        """
        Test that the profile ships its README and Brewfile
        """
        assert (PROFILE / name).is_file()
