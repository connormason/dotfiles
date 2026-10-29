"""
Shared pytest fixtures
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

__all__ = [
    'SHELLS',
    'shell',
    'unreadable_overlay',
]


def _discover_shells() -> list[str]:
    """
    Find the bash interpreters to exercise (the system bash plus the PATH bash), deduplicated by resolved path
    """
    shells: list[str] = []

    seen: set[Path] = set()
    for candidate in ('/bin/bash', shutil.which('bash')):
        if (not candidate) or (not Path(candidate).exists()):
            continue

        resolved = Path(candidate).resolve()
        if resolved in seen:
            continue

        seen.add(resolved)
        shells.append(candidate)

    return shells


SHELLS = _discover_shells()


@pytest.fixture(params=SHELLS, ids=SHELLS)
def shell(request: pytest.FixtureRequest) -> str:
    """
    Bash interpreter under test (macOS /bin/bash is 3.2, so it guards the portability constraint)
    """
    return request.param


@pytest.fixture
def unreadable_overlay(tmp_path: Path) -> Iterator[Path]:
    """
    An existing overlay directory that cannot be entered (mode 000); its permissions are restored on teardown
    """
    if os.geteuid() == 0:
        pytest.skip('root ignores directory permissions')

    path = tmp_path / 'unreadable-overlay'
    (path / 'bootstrap').mkdir(parents=True)

    path.chmod(0)
    yield path
    path.chmod(0o755)
