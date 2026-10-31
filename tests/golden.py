"""
Golden-file helper for regression tests
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

__all__ = [
    'GOLDEN_DIR',
    'check_golden',
]

REPO_ROOT  = Path(__file__).resolve().parents[1]
GOLDEN_DIR = REPO_ROOT / 'tests' / 'fixtures' / 'os_layout'


def check_golden(name: str, actual: list[str]) -> None:
    """
    Compare lines with a golden file, or rewrite the golden file when DOTFILES_UPDATE_GOLDEN=1

    :param name: file name under tests/fixtures/os_layout
    :param actual: lines produced by the code under test
    """
    path = GOLDEN_DIR / name
    if os.environ.get('DOTFILES_UPDATE_GOLDEN') == '1':
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(''.join(f'{line}\n' for line in actual), encoding='utf-8')
        pytest.skip(f'rewrote {path.relative_to(REPO_ROOT)}')

    assert actual == path.read_text(encoding='utf-8').splitlines()
