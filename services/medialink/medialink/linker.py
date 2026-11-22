"""
Hardlink a torrent's files from the download tree into a library directory
"""
from __future__ import annotations

import errno
import os
from dataclasses import dataclass
from pathlib import Path
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from medialink.transmission import Torrent

__all__ = [
    'EXISTS',
    'EXTRACTED',
    'EXTRACT_FAILED',
    'FAILED',
    'INCOMPLETE',
    'LEGACY_COPY',
    'LINKED',
    'SKIPPED',
    'SOURCE_MISSING',
    'UNSAFE',
    'LinkResult',
    'link_torrent',
    'map_download_dir',
    'safe_join',
]

LINKED         = 'linked'          # hardlink created (or would be, in a dry run)
EXISTS         = 'exists'          # destination is already a hardlink of the source
LEGACY_COPY    = 'legacy-copy'     # destination exists as an independent file (e.g. autoplex's copy)
SOURCE_MISSING = 'source-missing'  # Transmission lists the file but it is not on disk
INCOMPLETE     = 'incomplete'      # file not fully downloaded (for example an unwanted file); skipped
UNSAFE         = 'unsafe'          # file name would escape its base directory
FAILED         = 'failed'          # os.link raised
SKIPPED        = 'skipped'         # deliberately not linked (archive volumes: their contents are extracted instead)
EXTRACTED      = 'extracted'       # archive unpacked into the library (or would be, in a dry run)
EXTRACT_FAILED = 'extract-failed'  # archive could not be unpacked


@dataclass(frozen=True)
class LinkResult:
    """
    Outcome of reconciling one file
    """
    torrent: str
    source:  Path | None
    dest:    Path | None
    status:  str
    detail:  str = ''


def map_download_dir(download_dir: str, transmission_root: str, local_root: Path) -> Path | None:
    """
    Translate a ``downloadDir`` from Transmission's container namespace to a local path

    :param download_dir: path as reported by Transmission (``/downloads/complete/tv``)
    :param transmission_root: root of the download tree inside Transmission's container (``/downloads``)
    :param local_root: where the same tree is mounted locally
    :return: the local directory, or None when ``download_dir`` lies outside ``transmission_root``
    """
    try:
        relative = PurePosixPath(download_dir).relative_to(PurePosixPath(transmission_root))
    except ValueError:
        return None
    return local_root.joinpath(*relative.parts)


def safe_join(base: Path, name: str) -> Path | None:
    """
    Join an untrusted relative name onto a base directory

    Torrent metadata is attacker-controlled, so absolute names and ``..`` components are rejected rather than
    normalised.

    :param base: directory the result must stay inside
    :param name: relative file name taken from a torrent
    :return: the joined path, or None if the name is absolute, empty, or contains ``..``
    """
    parts = PurePosixPath(name).parts
    if (not parts) or PurePosixPath(name).is_absolute() or ('..' in parts):
        return None
    return base.joinpath(*parts)


def _is_same_file(a: Path, b: Path) -> bool:
    """
    Whether two paths are the same inode (hardlinks of each other)

    :param a: first path
    :param b: second path
    :return: True when both exist and share a device and inode
    """
    try:
        return os.path.samestat(a.stat(), b.stat())
    except OSError:
        return False


def _link_one(torrent: str, source: Path, dest: Path, *, dry_run: bool) -> LinkResult:
    """
    Reconcile a single file

    :param torrent: torrent name (for reporting)
    :param source: file in the download tree
    :param dest: target path in the library
    :param dry_run: report what would happen without touching the filesystem
    :return: the result for this file
    """
    if not source.is_file():
        return LinkResult(torrent, source, dest, SOURCE_MISSING)
    if os.path.lexists(dest):
        status = EXISTS if _is_same_file(source, dest) else LEGACY_COPY
        return LinkResult(torrent, source, dest, status)
    if dry_run:
        return LinkResult(torrent, source, dest, LINKED, 'dry-run')

    try:
        dest.parent.mkdir(parents=True, exist_ok=True, mode=0o775)
        os.link(source, dest)
    except FileExistsError:
        # Lost a race with another writer; classify what is there now
        status = EXISTS if _is_same_file(source, dest) else LEGACY_COPY
        return LinkResult(torrent, source, dest, status)
    except OSError as e:
        hint = ''
        if e.errno == errno.EXDEV:
            hint = ' (source and destination are on different mounts; mount one common parent)'
        return LinkResult(torrent, source, dest, FAILED, f'{e.strerror or e}{hint}')

    return LinkResult(torrent, source, dest, LINKED)


def link_torrent(
    torrent: Torrent,
    source_dir: Path,
    dest_root: Path,
    *,
    dry_run: bool = False,
    skip: Callable[[str], bool] | None = None,
) -> list[LinkResult]:
    """
    Hardlink every complete file of a torrent into a library directory, mirroring the torrent's own layout

    A file's name in Transmission already includes the torrent's top-level directory for multi-file torrents, so the
    destination is simply ``dest_root / file.name``.

    :param torrent: the finished torrent
    :param source_dir: local directory the torrent was downloaded into
    :param dest_root: library root (``.../movies`` or ``.../tv``)
    :param dry_run: report only; create nothing
    :param skip: predicate on a file name; matching files are reported as ``skipped`` and never linked
    :return: one result per file in the torrent
    """
    results: list[LinkResult] = []

    for file in torrent.files:
        source = safe_join(source_dir, file.name)
        dest   = safe_join(dest_root, file.name)

        if (source is None) or (dest is None):
            results.append(LinkResult(torrent.name, None, None, UNSAFE, file.name))
        elif (skip is not None) and skip(file.name):
            results.append(LinkResult(torrent.name, source, dest, SKIPPED))
        elif not file.complete:
            results.append(LinkResult(torrent.name, source, dest, INCOMPLETE))
        else:
            results.append(_link_one(torrent.name, source, dest, dry_run=dry_run))

    return results
