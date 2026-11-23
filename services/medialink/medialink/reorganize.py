"""
Move the library links medialink owns into the Jellyfin/Plex layout, with a journal so every move can be undone

Only links are moved, never data: a library file is a hardlink of the file Transmission seeds, so a ``link`` plus
``unlink`` inside one dataset leaves the seed copy untouched. A file counts as *owned* only while it still sits at the
path medialink linked it to (the torrent's own layout) or is a recorded RAR extraction; anything a person placed or
renamed is never touched, and a file that has already been moved is not a candidate a second time.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from medialink.classify import MOVIES
from medialink.classify import TV
from medialink.classify import classify
from medialink.layout import JUNK
from medialink.layout import OTHER
from medialink.layout import kind
from medialink.layout import place
from medialink.linker import map_download_dir
from medialink.linker import safe_join

if TYPE_CHECKING:
    from collections.abc import Iterable
    from collections.abc import Sequence
    from typing import TextIO

    from medialink.config import Config
    from medialink.layout import Override
    from medialink.state import State
    from medialink.transmission import Torrent

__all__ = [
    'CONFLICT',
    'CROSS',
    'DROP',
    'IN_PLACE',
    'KEEP',
    'MOVE',
    'PROBLEMS',
    'REDUNDANT',
    'UNPARSED',
    'ApplyResult',
    'Candidate',
    'Entry',
    'apply_plan',
    'discover',
    'make_plan',
    'select',
    'undo',
]

logger = logging.getLogger(__name__)

MOVE      = 'move'           # relink to the new path, drop the old one
CROSS     = 'cross-library'  # as MOVE, but into the other library (a season found in movies/)
IN_PLACE  = 'in-place'       # already in the directory the layout asks for
REDUNDANT = 'redundant'      # the target already holds this very file; only the old link goes
DROP      = 'drop-junk'      # scene leftover (.nfo, .sfv, artwork, samples) whose torrent is being reorganised
KEEP      = 'keep'           # not touched: other file types, or junk of a torrent nothing could be placed for
CONFLICT  = 'conflict'       # the target is taken by a different file
UNPARSED  = 'unparsed'       # no title could be read; needs an entry in the overrides file

ACTIONABLE = frozenset({MOVE, CROSS, REDUNDANT, DROP})
PROBLEMS   = frozenset({CONFLICT, UNPARSED})


@dataclass(frozen=True)
class Candidate:
    """
    A library file medialink owns

    ``name`` is the path below the library root, which for a mirrored link is the torrent-relative file name.
    ``source`` is the download-tree file it is a link of (None for an extracted file).
    """
    torrent:  str
    category: str
    name:     str
    current:  Path
    source:   Path | None


@dataclass(frozen=True)
class Entry:
    """
    What the plan does with one candidate
    """
    torrent: str
    current: Path
    target:  Path | None
    action:  str
    source:  Path | None = None
    detail:  str         = ''


@dataclass(frozen=True)
class ApplyResult:
    """
    What an apply (or undo) did
    """
    done:   int
    errors: tuple[str, ...] = ()


def _same(a: Path, b: Path) -> bool:
    """
    Whether two paths are the same inode

    :param a: first path
    :param b: second path
    :return: True when both exist and are hardlinks of each other
    """
    try:
        return os.path.samestat(a.stat(), b.stat())
    except OSError:
        return False


def _regular(path: Path) -> bool:
    """
    Whether a path is a regular file and not a symlink

    :param path: path to test
    :return: True for a real file
    """
    return path.is_file() and not path.is_symlink()


def discover(torrents: Iterable[Torrent], config: Config, state: State | None = None) -> list[Candidate]:
    """
    Find the library files medialink owns

    :param torrents: torrents from Transmission
    :param config: runtime configuration
    :param state: store of finished extractions, to find their outputs (omit to skip extracted files)
    :return: owned files, unsorted
    """
    found: list[Candidate] = []

    for torrent in torrents:
        if not torrent.finished:
            continue

        category   = classify(torrent.name, torrent.download_dir, torrent.labels)
        source_dir = map_download_dir(torrent.download_dir, config.transmission_downloads, config.downloads_root)
        if (category is None) or (source_dir is None):
            continue

        root = config.movies_root if category == MOVIES else config.tv_root
        for file in torrent.files:
            source  = safe_join(source_dir, file.name)
            current = safe_join(root, file.name)
            if (source is None) or (current is None) or (not file.complete):
                continue
            if _regular(current) and _same(source, current):
                found.append(Candidate(torrent.name, category, file.name, current, source))

        if state is None:
            continue

        for key, paths in state.outputs.items():
            if key.split(':', 2)[1:2] != [torrent.hash]:
                continue

            for relative in paths:
                current = config.media_root / relative
                try:
                    name = PurePosixPath(relative).relative_to(root.name).as_posix()
                except ValueError:
                    continue
                if _regular(current):
                    found.append(Candidate(torrent.name, category, name, current, None))

    return found


def _show_dirs(tv_root: Path) -> set[str]:
    """
    Names of the show directories that already exist

    :param tv_root: the ``tv`` library root
    :return: directory names; empty when the root cannot be listed
    """
    try:
        return {p.name for p in tv_root.iterdir() if p.is_dir()}
    except OSError:
        return set()


def make_plan(candidates: Sequence[Candidate], config: Config, overrides: Sequence[Override] = ()) -> list[Entry]:
    """
    Decide what to do with every owned file; touches nothing

    :param candidates: owned files from :func:`discover`
    :param config: runtime configuration
    :param overrides: hand-written title corrections
    :return: one entry per candidate, ordered by current path
    """
    ordered = sorted(candidates, key=lambda c: str(c.current))
    shows   = _show_dirs(config.tv_root)

    placements = {}
    for c in ordered:
        if kind(c.name) in {'video', 'subtitle'}:
            placement = place(c.category, c.torrent, c.name, overrides, shows)
            placements[c.current] = placement
            if placement and (placement.category == TV):
                shows.add(placement.directory.split('/', 1)[0])

    placed_torrents = {c.torrent for c in ordered if placements.get(c.current) is not None}

    entries: list[Entry] = []
    claimed: dict[Path, Path] = {}
    for c in ordered:
        file_kind = kind(c.name)
        if file_kind == OTHER:
            entries.append(Entry(c.torrent, c.current, None, KEEP, c.source, 'not a video, subtitle or scene file'))
            continue
        if file_kind == JUNK:
            action = DROP if c.torrent in placed_torrents else KEEP
            entries.append(Entry(c.torrent, c.current, None, action, c.source))
            continue

        placement = placements[c.current]
        if placement is None:
            entries.append(Entry(c.torrent, c.current, None, UNPARSED, c.source, 'no title and year or episode found'))
            continue

        first = config.media_root / placement.category / placement.path
        if (first == c.current) or (first.parent == c.current.parent):
            entries.append(Entry(c.torrent, c.current, first, IN_PLACE, c.source))
            continue

        entry = None
        for option in (placement, placement.with_version()):
            if option is None:
                continue

            target = config.media_root / option.category / option.path
            if (target in claimed) or os.path.lexists(target):
                if (target not in claimed) and _same(c.current, target):
                    entry = Entry(c.torrent, c.current, target, REDUNDANT, c.source)
                    break
                continue

            claimed[target] = c.current
            action = MOVE if option.category == c.category else CROSS
            entry  = Entry(c.torrent, c.current, target, action, c.source)
            break

        if entry is None:
            detail = f'{first} is taken by a different file'
            entry  = Entry(c.torrent, c.current, first, CONFLICT, c.source, detail)

        entries.append(entry)

    return entries


def select(entries: Sequence[Entry], *, only: str = '', limit: int | None = None) -> list[Entry]:
    """
    Narrow a plan to a batch

    :param entries: the full plan
    :param only: regular expression matched (case-insensitively) against the torrent name and the current path
    :param limit: apply at most this many torrents (in name order)
    :return: the selected entries, still in plan order
    """
    chosen = [e for e in entries if not only or re.search(only, f'{e.torrent}\n{e.current}', re.IGNORECASE)]
    if limit is not None:
        names  = sorted({e.torrent for e in chosen if e.action in ACTIONABLE})[:limit]
        chosen = [e for e in chosen if e.torrent in names]
    return chosen


def _record(journal: TextIO, **fields: str | None) -> None:
    """
    Append one journal line and force it to disk

    :param journal: open journal file
    :param fields: record fields
    """
    journal.write(json.dumps({'ts': int(time.time()), **fields}) + '\n')
    journal.flush()
    os.fsync(journal.fileno())


def _prune(directories: Iterable[Path], roots: Sequence[Path]) -> None:
    """
    Remove directories a run emptied, climbing until one is not empty; library roots are never removed

    :param directories: directories files were removed from
    :param roots: library roots that must stay
    """
    for directory in sorted(set(directories), key=lambda d: len(d.parts), reverse=True):
        while (directory not in roots) and any(directory.is_relative_to(r) for r in roots):
            try:
                directory.rmdir()
            except OSError:
                break
            directory = directory.parent


def apply_plan(entries: Sequence[Entry], config: Config) -> ApplyResult:
    """
    Carry out the actionable entries

    A move is a ``link`` (which refuses to overwrite) followed by an ``unlink``; the journal line is written between
    them, so a crash leaves at worst a second link that the next plan reports as redundant.

    :param entries: entries to apply, normally from :func:`select`
    :param config: runtime configuration (journal location, library roots)
    :return: how many entries were applied, and a message for each that failed
    """
    done = 0
    errors:  list[str] = []
    touched: set[Path] = set()

    config.journal_path.parent.mkdir(parents=True, exist_ok=True)
    with config.journal_path.open('a', encoding='utf-8') as journal:
        for entry in entries:
            if entry.action not in ACTIONABLE:
                continue

            try:
                if (entry.action in {MOVE, CROSS}) and (entry.target is not None):
                    entry.target.parent.mkdir(parents=True, exist_ok=True, mode=0o775)
                    os.link(entry.current, entry.target)
                    _record(journal, op='move', old=str(entry.current), new=str(entry.target))
                elif entry.action in {REDUNDANT, DROP}:
                    holder = entry.target if entry.action == REDUNDANT else entry.source
                    _record(journal, op='drop', old=str(entry.current), source=str(holder) if holder else None)
                else:
                    continue        # an actionable entry without what it needs (a move with no target): never unlink
                entry.current.unlink()
            except OSError as e:
                errors.append(f'{entry.current}: {e.strerror or e}')
                continue

            touched.add(entry.current.parent)
            done += 1

    _prune(touched, (config.movies_root, config.tv_root))
    return ApplyResult(done, tuple(errors))


def undo(config: Config, journal_path: Path, *, apply: bool) -> ApplyResult:
    """
    Replay a journal backwards

    A move is restored only if its new path still exists and the old one is free; a dropped file is re-linked from the
    path the journal recorded when that still exists. Anything else is reported and skipped.

    :param config: runtime configuration
    :param journal_path: ``reorg-journal.jsonl``
    :param apply: perform the restores (otherwise count what would be restored)
    :return: how many records were (or would be) restored, and a message for each skipped one
    """
    done   = 0
    errors: list[str] = []
    touched: set[Path] = set()

    try:
        lines = journal_path.read_text(encoding='utf-8').splitlines()
    except OSError as e:
        return ApplyResult(0, (f'cannot read {journal_path}: {e.strerror or e}',))

    for line in reversed(lines):
        try:
            record = json.loads(line)
            old    = Path(record['old'])
            new    = Path(record['new']) if record['op'] == 'move' else None
            source = Path(record['source']) if record.get('source') else None
        except (ValueError, KeyError, TypeError):
            errors.append(f'unreadable journal line: {line[:80]}')
            continue

        origin = new or source
        if (origin is None) or not origin.is_file():
            errors.append(f'{old}: nothing to restore it from')
        elif os.path.lexists(old):
            errors.append(f'{old}: already occupied')
        else:
            if apply:
                try:
                    old.parent.mkdir(parents=True, exist_ok=True, mode=0o775)
                    os.link(origin, old)
                    if new is not None:
                        new.unlink()
                        touched.add(new.parent)
                except OSError as e:
                    errors.append(f'{old}: {e.strerror or e}')
                    continue
            done += 1

    if apply:
        _prune(touched, (config.movies_root, config.tv_root))

    return ApplyResult(done, tuple(errors))
