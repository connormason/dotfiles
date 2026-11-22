"""
Helpers for finding untracked Claude Code config files
"""
from __future__ import annotations

import os
from pathlib import Path

__all__ = [
    'CLAUDE_CONFIG_DIR',
    'CLAUDE_IGNORE_DIRS',
    'CLAUDE_IGNORE_NAMES',
    'CLAUDE_IGNORE_SUFFIXES',
    'CLAUDE_TRACKED_SUBDIRS',
    'find_untracked_claude_files',
]


# `track-claude` command configuration
# -------------------------------------------------------------------
# Hand-authored Claude Code config that `track-claude` ingests into the `claude` stow package. Machine-managed state
# (plugins/, projects/, caches) stays untracked; stowed files are symlinks, so a regular file here is local-only.
CLAUDE_CONFIG_DIR:      Path      = Path.home() / '.claude'
CLAUDE_TRACKED_SUBDIRS: list[str] = ['agents', 'commands', 'skills', 'hooks', 'rules']

# Never ingested: .DS_Store plus the gitignored junk that appears next to tracked files (the settings-backup hook's
# `.backups/` and Python bytecode). Directories are pruned from the walk by name, files skipped by name or suffix;
# .gitignore must cover the directory names and suffixes (a test checks).
CLAUDE_IGNORE_NAMES:    set[str]  = {'.DS_Store'}
CLAUDE_IGNORE_DIRS:     set[str]  = {'.backups', '__pycache__'}
CLAUDE_IGNORE_SUFFIXES: set[str]  = {'.pyc'}


# ==================================================================================================
# Claude Code config file utilities
# ==================================================================================================


def find_untracked_claude_files() -> list[Path]:
    """
    Find real (non-symlink) files under the tracked ``~/.claude`` subdirectories

    Stowed agents/commands/skills/hooks/rules are symlinks into the repo, so any regular file is something Claude Code
    or the user created locally that the ``claude`` stow package does not have yet. Symlinked directories are never
    descended into, and a tracked subdirectory that is itself a symlink is skipped, so repo files reached through a
    link are never mistaken for local ones. Gitignored junk (``.backups/`` and ``__pycache__/`` directories, ``.pyc``
    files, ``.DS_Store``) is skipped, since ingesting it would put ignored files in the repo working copy.

    :return: sorted absolute paths of untracked files
    """
    untracked: list[Path] = []
    for subdir in CLAUDE_TRACKED_SUBDIRS:
        base = CLAUDE_CONFIG_DIR / subdir
        if base.is_symlink() or not base.is_dir():
            continue

        for dirpath, dirnames, filenames in os.walk(base):
            # Prune in place so os.walk never descends into gitignored junk directories
            dirnames[:] = [dirname for dirname in dirnames if dirname not in CLAUDE_IGNORE_DIRS]

            for filename in filenames:
                if filename in CLAUDE_IGNORE_NAMES or Path(filename).suffix in CLAUDE_IGNORE_SUFFIXES:
                    continue

                path = Path(dirpath) / filename
                if not path.is_symlink():
                    untracked.append(path)

    return sorted(untracked)
