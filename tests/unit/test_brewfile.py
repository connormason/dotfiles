"""
Brewfile regression tests: what `brew bundle` resolves bootstrap/Brewfile to on each OS
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

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
