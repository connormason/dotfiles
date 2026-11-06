"""
Classify an in-scope directory to select its README expectations.
"""
from __future__ import annotations

import enum
from pathlib import Path
from typing import Literal

from scripts.docs_audit.conventions import META_DIR_NAMES
from scripts.docs_audit.conventions import PLACEHOLDER_FILENAMES
from scripts.docs_audit.conventions import PLANS_EXEMPT_PARTS

__all__ = [
    'DirClass',
    'DirClassName',
    'classify',
]


# ==================================================================================================
# Directory classification enum
# ==================================================================================================


class DirClass(str, enum.Enum):
    """
    Documentation class of a directory, determining its README requirements.
    """
    CODE   = 'code'
    DATA   = 'data'
    META   = 'meta'
    EXEMPT = 'exempt'


DirClassName = Literal['code', 'data', 'meta', 'exempt']


# ==================================================================================================
# Classification logic
# ==================================================================================================


def classify(rel_dir: Path, *, repo_root: Path) -> DirClass:
    """
    Classify a repo-relative directory.

    :param rel_dir: directory path relative to the repo root (the repo root is ``Path('.')``)
    :param repo_root: absolute path to the repository root
    :return: the directory's :class:`DirClass`
    """
    parts = rel_dir.parts

    # Planning artifacts (docs/plans/**) are index-free by convention
    if parts[:len(PLANS_EXEMPT_PARTS)] == PLANS_EXEMPT_PARTS:
        return DirClass.EXEMPT

    # The repo root and top-level docs/scripts/tests get index/overview READMEs
    if rel_dir == Path():
        return DirClass.META
    if (len(parts) == 1) and (parts[0] in META_DIR_NAMES):
        return DirClass.META

    # A directory whose only entries are placeholders (e.g. an empty Sphinx _static seeded with .gitkeep) holds nothing
    # documentable, so it is exempt from the README requirement.
    abs_dir = repo_root / rel_dir
    try:
        documentable = [entry for entry in abs_dir.iterdir() if entry.name not in PLACEHOLDER_FILENAMES]
    except OSError:
        documentable = []
    if not documentable:
        return DirClass.EXEMPT

    # Code if it holds any .py file (an __init__.py-only package counts as code)
    return DirClass.CODE if any(entry.suffix == '.py' for entry in documentable) else DirClass.DATA
