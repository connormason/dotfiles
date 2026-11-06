"""
Discover the set of in-scope directories for the docs audit.

Directories are derived from tracked files (``git ls-files``), so untracked build artifacts never appear. Any directory
whose path contains an excluded segment or suffix is dropped.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from scripts.docs_audit.conventions import EXCLUDE_SEGMENTS
from scripts.docs_audit.conventions import EXCLUDE_SUFFIXES
from scripts.docs_audit.conventions import EXCLUDE_TOP_LEVEL

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    'discover',
    'is_excluded',
]


def is_excluded(rel_dir: Path) -> bool:
    """
    Return whether a repo-relative directory falls under an excluded segment, top-level name, or suffix.

    :param rel_dir: directory path relative to the repo root
    :return: True when the directory should be excluded from the audit
    """
    parts = rel_dir.parts
    if parts and (parts[0] in EXCLUDE_TOP_LEVEL):
        return True

    for part in parts:
        if part in EXCLUDE_SEGMENTS:
            return True
        if any(part.endswith(suffix) for suffix in EXCLUDE_SUFFIXES):
            return True
    return False


def discover(scopes: Sequence[Path], *, repo_root: Path) -> list[Path]:
    """
    Enumerate the in-scope directories containing tracked files.

    :param scopes: repo-relative scope paths to audit (use ``[Path('.')]`` for the whole repo)
    :param repo_root: absolute path to the repository root
    :return: sorted, de-duplicated list of repo-relative directories (the repo root is ``Path('.')``)
    """
    dirs: set[Path] = set()

    for scope in scopes:
        result = subprocess.run(
            ['git', 'ls-files', '-z', '--', scope.as_posix()],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
        for rel in result.stdout.split('\0'):
            if rel:
                dirs.add(Path(rel).parent)

    return sorted(
        [d for d in dirs if not is_excluded(d)],
        key=lambda p: p.as_posix(),
    )
