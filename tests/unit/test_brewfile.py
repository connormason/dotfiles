"""
Brewfile regression tests: what `brew bundle` resolves bootstrap/Brewfile to on each OS
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.golden import GOLDEN_DIR
from tests.golden import check_golden

REPO_ROOT = Path(__file__).resolve().parents[2]
BREWFILE  = REPO_ROOT / 'bootstrap' / 'Brewfile'
BREW      = shutil.which('brew')

pytestmark = pytest.mark.skipif(BREW is None, reason='Homebrew not installed')


def bundle_list(*flags: str) -> list[str]:
    """
    Run `brew bundle list` against the base Brewfile without auto-updating Homebrew

    :param flags: entry-type flags such as --all or --formula
    :return: sorted, non-empty output lines
    """
    assert BREW is not None
    result = subprocess.run(
        [BREW, 'bundle', 'list', *flags, '--file', str(BREWFILE)],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, 'HOMEBREW_NO_AUTO_UPDATE': '1', 'HOMEBREW_NO_ENV_HINTS': '1'},
    )
    assert result.returncode == 0, result.stderr
    return sorted(line for line in result.stdout.splitlines() if line)


@pytest.mark.skipif(sys.platform != 'darwin', reason='darwin resolution')
class TestDarwinBrewfile:
    """
    Tests pinning the darwin Brewfile resolution to the pre-Linux-support golden files
    """
    def test_all_entries_match_golden(self) -> None:
        """
        Test that every tap, formula, cask, and Mac App Store entry resolves exactly as before
        """
        check_golden('brewfile-darwin.txt', bundle_list('--all'))

    def test_formulae_match_golden(self) -> None:
        """
        Test that the formula list resolves exactly as before
        """
        check_golden('brewfile-darwin-formulae.txt', bundle_list('--formula'))


# Formulae that exist only on macOS; they live inside the Brewfile's `if OS.mac?` block
DARWIN_ONLY_FORMULAE = frozenset({'mas'})


@pytest.mark.skipif(sys.platform != 'linux', reason='linux resolution')
class TestLinuxBrewfile:
    """
    Tests for what Linuxbrew resolves the base Brewfile to
    """
    def test_no_casks_or_mac_app_store_entries(self) -> None:
        """
        Test that casks and Mac App Store entries are invisible on linux
        """
        assert bundle_list('--cask') == []
        assert bundle_list('--mas')  == []

    def test_formulae_are_the_darwin_formulae_minus_macos_only(self) -> None:
        """
        Test that linux gets every darwin formula except the macOS-only ones
        """
        darwin = (GOLDEN_DIR / 'brewfile-darwin-formulae.txt').read_text(encoding='utf-8').splitlines()
        assert bundle_list('--formula') == sorted(set(darwin) - DARWIN_ONLY_FORMULAE)

    def test_no_formula_requires_macos(self) -> None:
        """
        Test that no formula linux installs declares a macOS requirement (the Brewfile's taps must be tapped)
        """
        assert BREW is not None
        result = subprocess.run(
            [BREW, 'info', '--json=v2', '--formula', *bundle_list('--formula')],
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, 'HOMEBREW_NO_AUTO_UPDATE': '1'},
        )
        assert result.returncode == 0, result.stderr

        macos_only = [
            formula['full_name']
            for formula in json.loads(result.stdout)['formulae']
            if any(req['name'] == 'macos' for req in formula['requirements'])
        ]
        assert macos_only == []
