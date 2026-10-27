"""
Shared pytest fixtures
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

__all__ = ['SHELLS', 'shell']


def _discover_shells() -> list[str]:
    """
    Find the bash interpreters to exercise (the system bash plus the PATH bash), deduplicated by resolved path
    """
    shells: list[str] = []
    seen: set[Path] = set()
    for candidate in ('/bin/bash', shutil.which('bash')):
        if not candidate or not Path(candidate).exists():
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
