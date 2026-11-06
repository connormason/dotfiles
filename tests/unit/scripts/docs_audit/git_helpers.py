"""
Scratch-repo helpers for the docs_audit tests

Every git call runs with global/system config disabled and a fixed identity, so the developer's own git configuration
(signing, hook paths, templates) cannot leak into the scratch repos.
"""
from __future__ import annotations

import os
import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

__all__ = [
    'git_commit_all',
    'git_init',
]

ISOLATED_GIT_ENV: dict[str, str] = {
    'GIT_CONFIG_GLOBAL':   os.devnull,
    'GIT_CONFIG_NOSYSTEM': '1',
    'GIT_AUTHOR_NAME':     'Test',
    'GIT_AUTHOR_EMAIL':    'test@example.com',
    'GIT_COMMITTER_NAME':  'Test',
    'GIT_COMMITTER_EMAIL': 'test@example.com',
}


def git_init(root: Path) -> None:
    """
    Initialize an empty git repository at ``root``.

    :param root: directory to initialize
    """
    subprocess.run(
        ['git', 'init', '-q', '-b', 'main'],
        cwd=root,
        check=True,
        capture_output=True,
        env={**os.environ, **ISOLATED_GIT_ENV},
    )


def git_commit_all(root: Path, message: str = 'commit', *, date: str | None = None) -> None:
    """
    Stage and commit everything under ``root``.

    :param root: repository root
    :param message: commit message
    :param date: ISO-8601 author/committer date, to give commits a deterministic order without sleeping
    """
    env = {**os.environ, **ISOLATED_GIT_ENV}
    if date is not None:
        env['GIT_AUTHOR_DATE']    = date
        env['GIT_COMMITTER_DATE'] = date

    subprocess.run(['git', 'add', '-A'],                   cwd=root, check=True, capture_output=True, env=env)
    subprocess.run(['git', 'commit', '-q', '-m', message], cwd=root, check=True, capture_output=True, env=env)
