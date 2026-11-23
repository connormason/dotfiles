"""
Unpack RAR-packed releases (common for scene torrents) into a library directory

Archive volumes are never linked into the library; their contents are extracted instead, next to where the volumes
sit in the torrent, so the library mirrors the release folder just like linked files do.
"""
from __future__ import annotations

import contextlib
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from medialink.linker import EXISTS
from medialink.linker import EXTRACT_FAILED
from medialink.linker import EXTRACTED
from medialink.linker import INCOMPLETE
from medialink.linker import SOURCE_MISSING
from medialink.linker import UNSAFE
from medialink.linker import LinkResult
from medialink.linker import safe_join

if TYPE_CHECKING:
    from collections.abc import Callable

    from medialink.state import State
    from medialink.transmission import Torrent

__all__ = [
    'ExtractError',
    'Extractor',
    'extract_torrent',
    'has_archives',
    'is_archive_part',
    'is_first_volume',
]

logger = logging.getLogger(__name__)

# A multi-volume set is `name.rar` + `name.r00`, `name.r01`, ... or `name.part01.rar`, `name.part02.rar`, ...
_ARCHIVE_PART = re.compile(r'\.(rar|r\d{2,3})$',   re.IGNORECASE)
_PART_VOLUME  = re.compile(r'\.part0*(\d+)\.rar$', re.IGNORECASE)

TEMP_PREFIX     = '.medialink-extract-'
DEFAULT_TIMEOUT = 6 * 3600
CANDIDATES      = ('7zz', '7z', 'unrar')


class ExtractError(RuntimeError):
    """
    Raised when an archive cannot be unpacked
    """
    pass


def is_archive_part(name: str) -> bool:
    """
    Whether a file name is any volume of a RAR set

    :param name: torrent-relative file name
    :return: True for ``.rar`` and ``.rNN`` names
    """
    return bool(_ARCHIVE_PART.search(name))


def is_first_volume(name: str) -> bool:
    """
    Whether a file name is the volume to hand to the extractor

    ``x.rar`` starts an old-style set and ``x.part01.rar`` (any zero padding) starts a new-style one; ``x.part02.rar``
    and ``x.r00`` are continuations.

    :param name: torrent-relative file name
    :return: True when extraction should start from this file
    """
    if not name.lower().endswith('.rar'):
        return False

    match = _PART_VOLUME.search(name)
    return (match is None) or (int(match.group(1)) == 1)


def has_archives(torrent: Torrent) -> bool:
    """
    Whether any file of the torrent is a RAR volume

    :param torrent: the torrent to inspect
    :return: True if at least one RAR volume is present
    """
    return any(is_archive_part(f.name) for f in torrent.files)


def _tail(text: str, limit: int = 300) -> str:
    """
    Last part of a command's output, for error messages

    :param text: command output
    :param limit: maximum characters kept
    :return: the trimmed tail
    """
    text = text.strip()
    return text[-limit:] if len(text) > limit else text


class Extractor:
    """
    Runs ``7z``/``7zz`` or RARLAB ``unrar`` to unpack a RAR set

    Debian's packaged ``7zip`` is built without RAR support, which is why the container installs ``unrar`` instead;
    ``7z`` with the RAR module (as on many desktops) works as well.
    """
    def __init__(
        self,
        binary: str,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        """
        Create an extractor

        :param binary: path of the extraction tool
        :param runner: ``subprocess.run`` stand-in (tests)
        :param timeout: seconds allowed per archive
        """
        self.binary  = binary
        self.runner  = runner
        self.timeout = timeout

    @classmethod
    def discover(cls, preferred: str = '') -> Extractor | None:
        """
        Find an extraction tool on ``PATH``

        :param preferred: tool name or path to try first (``MEDIALINK_EXTRACTOR``)
        :return: an extractor, or None when none of the candidates is installed
        """
        for candidate in (preferred, *CANDIDATES):
            if found := shutil.which(candidate) if candidate else None:
                return cls(found)
        return None

    def command(self, archive: Path, out_dir: Path) -> list[str]:
        """
        Build the extraction command line

        :param archive: first volume of the set
        :param out_dir: directory to unpack into
        :return: argv for the configured tool
        """
        if Path(self.binary).name.lower().startswith('7z'):
            return [self.binary, 'x', '-y', '-bd', '-bso0', '-bsp0', f'-o{out_dir}', str(archive)]
        return [self.binary, 'x', '-y', '-idq', '-o+', str(archive), f'{out_dir}{os.sep}']

    def extract(self, archive: Path, out_dir: Path) -> None:
        """
        Unpack a RAR set

        :param archive: first volume of the set
        :param out_dir: directory to unpack into (created if needed)
        :raises ExtractError: if the tool is missing, times out, or exits non-zero
        """
        out_dir.mkdir(parents=True, exist_ok=True)
        try:
            proc = self.runner(
                self.command(archive, out_dir),
                capture_output=True,
                text=True,
                check=False,
                timeout=self.timeout,
            )
        except (OSError, subprocess.TimeoutExpired) as e:
            raise ExtractError(f'{Path(self.binary).name} failed to run: {e}') from e

        if proc.returncode != 0:
            raise ExtractError(
                f'{Path(self.binary).name} exited {proc.returncode}: {_tail(proc.stderr or proc.stdout or "")}',
            )


def _publish(staging: Path, dest_dir: Path) -> list[Path]:
    """
    Move freshly extracted files from the staging directory into the library

    Existing files are never replaced, and symlinks from the archive are discarded. Moving within one filesystem is an
    atomic rename, so a reader never sees a half-written file.

    :param staging: directory the archive was unpacked into
    :param dest_dir: final library directory
    :return: the library paths of the files moved into place
    """
    moved: list[Path] = []

    for dirpath, _, filenames in os.walk(staging):
        for filename in filenames:
            source = Path(dirpath) / filename
            if source.is_symlink():
                continue

            target = dest_dir / source.relative_to(staging)
            if os.path.lexists(target):
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            source.replace(target)
            moved.append(target)

    return moved


def _extract_one(
    torrent: Torrent,
    volume_name: str,
    source_dir: Path,
    dest_root: Path,
    *,
    extractor: Extractor | None,
    state: State | None,
    dry_run: bool,
) -> LinkResult:
    """
    Handle one RAR set of a torrent

    :param torrent: the torrent
    :param volume_name: torrent-relative name of the set's first volume
    :param source_dir: local download directory
    :param dest_root: library root
    :param extractor: extraction tool, or None when none is available
    :param state: store of completed extractions (omit to re-check every pass)
    :param dry_run: report only
    :return: the result for this set
    """
    parent   = PurePosixPath(volume_name).parent
    archive  = safe_join(source_dir, volume_name)
    dest_dir = dest_root if parent == PurePosixPath('.') else safe_join(dest_root, parent.as_posix())
    if (archive is None) or (dest_dir is None):
        return LinkResult(torrent.name, None, None, UNSAFE, volume_name)

    siblings = [f for f in torrent.files if is_archive_part(f.name) and PurePosixPath(f.name).parent == parent]
    if not all(f.complete for f in siblings):
        return LinkResult(torrent.name, archive, dest_dir, INCOMPLETE, 'archive volumes still missing')
    if not archive.is_file():
        return LinkResult(torrent.name, archive, dest_dir, SOURCE_MISSING)

    key = f'extracted:{torrent.hash}:{volume_name}'
    if (state is not None) and (key in state):
        return LinkResult(torrent.name, archive, dest_dir, EXISTS, 'extracted earlier')
    if dry_run:
        return LinkResult(torrent.name, archive, dest_dir, EXTRACTED, 'dry-run')
    if extractor is None:
        return LinkResult(
            torrent.name,
            archive,
            dest_dir,
            EXTRACT_FAILED,
            'no RAR-capable extractor found (install unrar or 7-Zip with RAR support)'
        )

    staging = dest_dir / f'{TEMP_PREFIX}{torrent.hash[:8]}'
    try:
        shutil.rmtree(staging, ignore_errors=True)  # leftovers from a crashed run may be truncated
        extractor.extract(archive, staging)
        moved = _publish(staging, dest_dir)
    except (ExtractError, OSError) as e:
        logger.error('extracting %s failed: %s', archive, e)
        return LinkResult(torrent.name, archive, dest_dir, EXTRACT_FAILED, str(e))
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        with contextlib.suppress(OSError):
            dest_dir.rmdir()  # drop a directory we created for nothing

    if state is not None:
        state.add(key)
        state.record_outputs(key, [p.relative_to(dest_root.parent).as_posix() for p in moved])
    return LinkResult(torrent.name, archive, dest_dir, EXTRACTED, f'{len(moved)} file(s)')


def extract_torrent(
    torrent: Torrent,
    source_dir: Path,
    dest_root: Path,
    extractor: Extractor | None,
    state: State | None = None,
    *,
    dry_run: bool = False,
) -> list[LinkResult]:
    """
    Unpack every RAR set in a torrent into the library, beside where its volumes sit in the release folder

    Completed sets are remembered in ``state`` so the next pass does not read gigabytes of archive again. A failed or
    interrupted extraction leaves nothing half-written in the library and is retried on the next pass.

    :param torrent: the finished torrent
    :param source_dir: local directory the torrent was downloaded into
    :param dest_root: library root
    :param extractor: extraction tool, or None when none is available
    :param state: store of completed extractions
    :param dry_run: report only; extract nothing
    :return: one result per RAR set
    """
    return [
        _extract_one(torrent, f.name, source_dir, dest_root, extractor=extractor, state=state, dry_run=dry_run)
        for f in torrent.files
        if is_first_volume(f.name)
    ]
