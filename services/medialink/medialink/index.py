"""
Inode index of the library: find where a download's hardlink lives, wherever it has been moved to
"""
from __future__ import annotations

import os
from pathlib import Path
from stat import S_ISREG

__all__ = [
    'Index',
    'build_index',
    'inode_key',
]

# (st_dev, st_ino) -> a library path holding that inode
Index = dict[tuple[int, int], Path]


def inode_key(path: Path) -> tuple[int, int] | None:
    """
    Identify a file by device and inode

    :param path: file to identify (symlinks are followed, as for a download source)
    :return: ``(st_dev, st_ino)``, or None when the file cannot be read
    """
    try:
        stat = path.stat()
    except OSError:
        return None
    return (stat.st_dev, stat.st_ino)


def build_index(*roots: Path) -> Index:
    """
    Index every multiply-linked regular file under the given library roots

    A library file that is a hardlink of a download has at least two names, so files with a single link are skipped:
    they cannot be linked to anything in the download tree. That keeps the map small. Files that vanish mid-walk are
    ignored, as are symlinks.

    :param roots: library directories (``movies``, ``tv``); missing ones are skipped
    :return: map from ``(st_dev, st_ino)`` to one path holding that inode
    """
    index: Index = {}
    for root in roots:
        for dirpath, _, filenames in os.walk(root):
            for filename in filenames:
                path = Path(dirpath) / filename
                try:
                    stat = path.lstat()
                except OSError:
                    continue
                if (stat.st_nlink > 1) and S_ISREG(stat.st_mode):  # lstat: a symlink is never regular
                    index.setdefault((stat.st_dev, stat.st_ino), path)
    return index
