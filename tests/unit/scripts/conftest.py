from __future__ import annotations

from pathlib import Path

import pytest

__all__ = [
    'fixtures_dir',
]


@pytest.fixture
def fixtures_dir() -> Path:
    """
    Return path to the test fixtures directory.
    """
    return Path(__file__).parent / 'fixtures'
