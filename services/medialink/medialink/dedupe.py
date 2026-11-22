"""
Clean up what autoplex left behind: independent copies in the library that medialink now serves as hardlinks

Two situations, both verified byte-for-byte before anything is touched and both dry runs unless applied:

* **Mirrored legacy copies**: a file autoplex copied to the exact path medialink links to is replaced by a hardlink.
* **Flat duplicates**: autoplex put most video files directly at the library root (``movies/<file>``,
  ``tv/<file>``). Once medialink has linked or extracted the same video inside its release folder, the flat file is a
  second, identical copy and Jellyfin lists the title twice. The flat file is removed; the foldered copy remains.
"""
from __future__ import annotations

import contextlib
import hashlib
import os
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from medialink.archives import TEMP_PREFIX
from medialink.linker import LEGACY_COPY

if TYPE_CHECKING:
    from collections.abc import Iterable

    from medialink.linker import LinkResult

__all__ = [
    'DedupeOutcome',
    'dedupe',
    'file_digest',
    'flat_duplicates',
]

CHUNK            = 1024 * 1024
VIDEO_EXTENSIONS = ('.mkv', '.mp4', '.avi', '.m4v', '.divx')


@dataclass(frozen=True)
class DedupeOutcome:
    """
    What happened (or would happen) to one file

    ``size`` is the space the action frees (0 when the file shares data with another name and nothing is reclaimed).
    """
    dest:   Path
    size:   int
    action: str  # 'replaced' | 'would-replace' | 'removed-flat' | 'would-remove-flat' | 'differs' | 'error'
    detail: str = ''


def file_digest(path: Path, *, quick: bool = False) -> str:
    """
    SHA-256 of a file, streamed

    In quick mode only the size and three 1 MiB samples (start, middle, end) are hashed: far cheaper on multi-gigabyte
    video, and enough to tell apart copies of different files with the same name and size, but not a proof of
    equality.

    :param path: file to hash
    :param quick: sample instead of reading the whole file
    :return: hex digest
    """
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        if quick:
            size = os.fstat(handle.fileno()).st_size
            digest.update(str(size).encode())
            for offset in (0, max(size // 2 - CHUNK // 2, 0), max(size - CHUNK, 0)):
                handle.seek(offset)
                digest.update(handle.read(CHUNK))
        else:
            for chunk in iter(lambda: handle.read(CHUNK), b''):
                digest.update(chunk)
    return digest.hexdigest()


def _replace_with_link(source: Path, dest: Path) -> None:
    """
    Atomically swap ``dest`` for a hardlink to ``source``

    The link is created under a temporary name next to ``dest`` and renamed over it, so ``dest`` never disappears.

    :param source: file in the download tree
    :param dest: independent copy to replace
    """
    tmp = dest.with_name(f'.{dest.name}.medialink-tmp')
    try:
        os.link(source, tmp)
        tmp.replace(dest)
    except OSError:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise


def dedupe(results: list[LinkResult], *, apply: bool = False, quick: bool = False) -> list[DedupeOutcome]:
    """
    Convert legacy copies at the mirrored path into hardlinks after proving they are identical

    Only files the linker classified as ``legacy-copy`` are considered. Size is compared first (cheap), then the
    SHA-256 of both files; a mismatch is reported and left untouched.

    :param results: link results from a reconcile pass
    :param apply: perform the replacement (default is a dry run)
    :param quick: compare sampled digests instead of whole files
    :return: one outcome per legacy copy examined
    """
    outcomes: list[DedupeOutcome] = []
    for result in results:
        if result.status != LEGACY_COPY or result.source is None or result.dest is None:
            continue
        source, dest = result.source, result.dest
        try:
            size = source.stat().st_size
            if size != dest.stat().st_size or file_digest(source, quick=quick) != file_digest(dest, quick=quick):
                outcomes.append(DedupeOutcome(dest, size, 'differs'))
                continue
            if apply:
                _replace_with_link(source, dest)
                outcomes.append(DedupeOutcome(dest, size, 'replaced'))
            else:
                outcomes.append(DedupeOutcome(dest, size, 'would-replace'))
        except OSError as e:
            outcomes.append(DedupeOutcome(dest, 0, 'error', str(e)))
    return outcomes


def _index_videos(root: Path) -> tuple[list[tuple[Path, int]], dict[tuple[str, int], list[Path]]]:
    """
    Split a library's video files into those at its root and those inside folders

    :param root: library root (``.../movies`` or ``.../tv``)
    :return: the flat files with their sizes, and the foldered files keyed by (name, size)
    """
    flat:   list[tuple[Path, int]]            = []
    nested: dict[tuple[str, int], list[Path]] = defaultdict(list)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(TEMP_PREFIX)]
        at_root = Path(dirpath) == root
        for filename in filenames:
            if filename.startswith('.') or not filename.lower().endswith(VIDEO_EXTENSIONS):
                continue
            path = Path(dirpath) / filename
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if at_root:
                flat.append((path, size))
            else:
                nested[(filename, size)].append(path)
    return flat, nested


def flat_duplicates(roots: Iterable[Path], *, apply: bool = False, quick: bool = False) -> list[DedupeOutcome]:
    """
    Find (and optionally remove) video files at a library root that already exist, identical, inside a folder

    A flat file is removed only if a foldered file with the same name and size has the same digest and is a different
    inode, so no content is ever lost: the foldered copy stays. Flat files with no foldered twin (including everything
    you reorganised by hand) are left alone.

    :param roots: library roots to scan
    :param apply: delete the flat duplicates (default is a dry run)
    :param quick: compare sampled digests instead of whole files
    :return: one outcome per flat duplicate found, or per file that could not be examined
    """
    outcomes: list[DedupeOutcome] = []
    digests:  dict[Path, str]     = {}

    def digest_of(path: Path) -> str:
        """
        Digest a path once (a foldered twin is often compared against several flat files)
        """
        if path not in digests:
            digests[path] = file_digest(path, quick=quick)
        return digests[path]

    for root in roots:
        flat, nested = _index_videos(root)
        for flat_path, size in flat:
            twins = nested.get((flat_path.name, size))
            if not twins:
                continue
            try:
                flat_stat = flat_path.stat()
                twin      = next(
                    (
                        t for t in twins
                        if not os.path.samestat(flat_stat, t.stat()) and digest_of(t) == digest_of(flat_path)
                    ),
                    None,
                )
                if twin is None:
                    continue
                reclaimed = size if flat_stat.st_nlink == 1 else 0
                if apply:
                    flat_path.unlink()
                    outcomes.append(DedupeOutcome(flat_path, reclaimed, 'removed-flat', str(twin.relative_to(root))))
                else:
                    outcomes.append(
                        DedupeOutcome(flat_path, reclaimed, 'would-remove-flat', str(twin.relative_to(root))),
                    )
            except OSError as e:
                outcomes.append(DedupeOutcome(flat_path, 0, 'error', str(e)))
    return outcomes
