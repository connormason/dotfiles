"""
Unit tests guarding that every file in the stowed trees is actually tracked by git

A stock ``.gitignore`` rule (for example IPython's ``profile_default/``) can silently exclude a package file; the
integration harness stows from the working tree, so such a file passes tests yet never reaches a clone.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TREES     = ('stow', 'render', 'profiles', 'tests/fixtures')
NOISE     = ('.DS_Store', '__pycache__', '.pyc')

pytestmark = pytest.mark.skipif(shutil.which('git') is None, reason='git not installed')


def list_others(*flags: str) -> list[str]:
    """
    List untracked (optionally ignored-only) paths below the guarded trees, minus platform noise.

    :param flags: extra ``git ls-files`` flags (``--ignored`` restricts the listing to ignored paths).
    :return: the offending repository-relative paths.
    """
    result = subprocess.run(
        ['git', 'ls-files', '--others', *flags, '--exclude-standard', '--', *TREES],
        capture_output=True, text=True, check=True, cwd=REPO_ROOT,
    )
    return [line for line in result.stdout.splitlines() if not any(noise in line for noise in NOISE)]


class TestStowTree:
    """
    Tests for the tracked-ness of package files
    """
    def test_no_untracked_files(self) -> None:
        """
        Test that no file under the guarded trees is untracked
        """
        assert list_others() == []

    def test_no_ignored_files(self) -> None:
        """
        Test that no file under the guarded trees is excluded by a gitignore rule
        """
        assert list_others('--ignored') == []
