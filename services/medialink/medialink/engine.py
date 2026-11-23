"""
One reconcile pass: classify each finished torrent and make sure its files are linked into the library
"""
from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass
from dataclasses import field
from typing import TYPE_CHECKING

from medialink.archives import extract_torrent
from medialink.archives import has_archives
from medialink.archives import is_archive_part
from medialink.classify import MOVIES
from medialink.classify import TV
from medialink.classify import classify
from medialink.config import JELLYFIN
from medialink.config import ConfigError
from medialink.index import build_index
from medialink.layout import JUNK
from medialink.layout import kind
from medialink.layout import load_overrides
from medialink.layout import place
from medialink.linker import EXTRACT_FAILED
from medialink.linker import EXTRACTED
from medialink.linker import FAILED
from medialink.linker import LINKED
from medialink.linker import SOURCE_MISSING
from medialink.linker import UNSAFE
from medialink.linker import link_torrent
from medialink.linker import map_download_dir

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from medialink.archives import Extractor
    from medialink.config import Config
    from medialink.index import Index
    from medialink.layout import Override
    from medialink.linker import LinkResult
    from medialink.notify import Notifier
    from medialink.state import State
    from medialink.transmission import Torrent

__all__ = [
    'LayoutContext',
    'Problem',
    'Report',
    'reconcile',
]

logger = logging.getLogger(__name__)

# Statuses that need a human: the file should have been linked and was not.
PROBLEM_STATUSES = frozenset({FAILED, SOURCE_MISSING, UNSAFE, EXTRACT_FAILED})

# Key prefixes this module owns in the notified-problem state (the CLI owns 'rpc-outage')
PROBLEM_PREFIXES = ('unclassified:', 'outside:', 'link:', 'overrides')


@dataclass(frozen=True)
class Problem:
    """
    Something the operator should look at; ``key`` dedupes notifications across cycles
    """
    key:     str
    title:   str
    message: str


@dataclass
class Report:
    """
    Aggregate outcome of a reconcile pass
    """
    counts:   Counter[str]     = field(default_factory=Counter)
    results:  list[LinkResult] = field(default_factory=list)
    problems: list[Problem]    = field(default_factory=list)
    pending:  int              = 0

    @property
    def ok(self) -> bool:
        """
        Whether the pass finished without problems
        """
        return not self.problems


@dataclass
class LayoutContext:
    """
    What the Jellyfin layout needs for one pass: the overrides, and the show directories (grown as shows are placed)
    """
    overrides: list[Override]
    shows:     set[str]


def _skip_archives_and_junk(name: str) -> bool:
    """
    Whether the Jellyfin layout leaves a torrent file out: RAR volumes (extracted instead) and scene leftovers

    :param name: torrent-relative file name
    :return: True to skip
    """
    return is_archive_part(name) or kind(name) == JUNK


def _placer(category: str, torrent: Torrent, config: Config, layout: LayoutContext) -> Callable[[str], Path | None]:
    """
    Build the function that maps one torrent file to its path in the Jellyfin layout

    :param category: library the torrent was classified into
    :param torrent: the torrent
    :param config: runtime configuration
    :param layout: overrides and known show directories
    :return: a function returning the destination, or None when the file cannot be placed (it is mirrored instead)
    """
    def place_file(name: str) -> Path | None:
        """
        Destination of one file

        :param name: torrent-relative file name
        :return: absolute destination, or None
        """
        placement = place(category, torrent.name, name, layout.overrides, layout.shows)
        if placement is None:
            return None
        if placement.category == TV:
            layout.shows.add(placement.directory.split('/', 1)[0])
        return (config.tv_root if placement.category == TV else config.movies_root) / placement.path

    return place_file


def _layout_context(config: Config, report: Report) -> LayoutContext | None:
    """
    Prepare the Jellyfin layout for a pass

    A damaged overrides file is reported as a problem and treated as empty, so the pass still links everything.

    :param config: runtime configuration
    :param report: report that receives the overrides problem, if any
    :return: the context, or None when the layout is ``mirror``
    """
    if config.layout != JELLYFIN:
        return None

    try:
        overrides = load_overrides(config.overrides_path)
    except ConfigError as e:
        report.problems.append(Problem(key='overrides', title='Overrides file unusable', message=str(e)))
        overrides = []

    try:
        shows = {p.name for p in config.tv_root.iterdir() if p.is_dir()}
    except OSError:
        shows = set()
    return LayoutContext(overrides, shows)


def _summarise(results: list[LinkResult], limit: int = 5) -> str:
    """
    Describe the failing files of one torrent

    :param results: all results for the torrent
    :param limit: how many failing files to list before eliding
    :return: a short multi-line description
    """
    bad   = [r for r in results if r.status in PROBLEM_STATUSES]
    lines = [f'{r.status}: {r.dest or r.detail} {r.detail if r.dest else ""}'.rstrip() for r in bad[:limit]]
    if len(bad) > limit:
        lines.append(f'… and {len(bad) - limit} more')
    return '\n'.join(lines)


def _handle_torrent(
    torrent: Torrent,
    config: Config,
    report: Report,
    *,
    dry_run: bool,
    state: State | None,
    extractor: Extractor | None,
    index: Index | None = None,
    layout: LayoutContext | None = None,
) -> None:
    """
    Reconcile one finished torrent, recording results and problems on the report

    :param torrent: finished torrent
    :param config: runtime configuration
    :param report: report to update
    :param dry_run: do not touch the filesystem
    :param state: store of completed extractions
    :param extractor: RAR extraction tool, or None when unavailable or disabled
    :param index: library inode index, so files moved within the library are recognised
    :param layout: Jellyfin-layout context, or None to mirror each torrent's own layout
    """
    category = classify(torrent.name, torrent.download_dir, torrent.labels)
    if category is None:
        report.problems.append(
            Problem(
                key=f'unclassified:{torrent.hash}',
                title='Torrent not placed',
                message=(
                    f'Cannot tell movie from TV: {torrent.name}\nSaved in {torrent.download_dir}. '
                    'Add a "movies" or "tv" label in Transmission.'
                ),
            )
        )
        return

    source_dir = map_download_dir(torrent.download_dir, config.transmission_downloads, config.downloads_root)
    if source_dir is None:
        report.problems.append(
            Problem(
                key=f'outside:{torrent.hash}',
                title='Torrent outside download tree',
                message=f'{torrent.name} is in {torrent.download_dir}, not under {config.transmission_downloads}',
            )
        )
        return

    dest_root = config.movies_root if category == MOVIES else config.tv_root
    skip      = is_archive_part
    placer    = None
    if layout is not None:
        placer = _placer(category, torrent, config, layout)
        skip   = _skip_archives_and_junk
    results   = link_torrent(
        torrent, source_dir, dest_root, dry_run=dry_run, skip=skip, index=index, placer=placer,
    )
    if has_archives(torrent):
        results += extract_torrent(torrent, source_dir, dest_root, extractor, state, dry_run=dry_run)
    report.results.extend(results)
    report.counts.update(r.status for r in results)

    for result in results:
        if result.status == LINKED:
            logger.info('%s %s -> %s', 'would link' if dry_run else 'linked', result.source, result.dest)
        elif result.status == EXTRACTED:
            logger.info(
                '%s %s -> %s (%s)', 'would extract' if dry_run else 'extracted',
                result.source,
                result.dest,
                result.detail,
            )
        elif result.status in PROBLEM_STATUSES:
            # A problem already announced on an earlier pass would otherwise repeat every cycle for as long as it
            # lasts; keep its detail at DEBUG then. Manual dry runs stay fully verbose.
            known = (not dry_run) and state is not None and f'link:{torrent.hash}' in state
            logger.log(
                logging.DEBUG if known else logging.ERROR,
                '%s: %s (%s)',
                result.status,
                result.dest or result.source,
                result.detail,
            )

    if any(r.status in PROBLEM_STATUSES for r in results):
        report.problems.append(
            Problem(
                key=f'link:{torrent.hash}',
                title='Torrent linking failed',
                message=f'{torrent.name} ({category})\n{_summarise(results)}',
            )
        )


def reconcile(
    torrents: list[Torrent],
    config: Config,
    *,
    dry_run: bool = False,
    state: State | None = None,
    notifier: Notifier | None = None,
    extractor: Extractor | None = None,
) -> Report:
    """
    Link every finished torrent's files into the library and alert on anything that could not be placed

    Idempotent: files already linked are left alone, so the pass heals whatever an earlier run (or an outage)
    missed. RAR sets are unpacked instead of linked. Problems notify once per key; a key is forgotten again when its
    torrent stops being a problem.

    :param torrents: torrents from Transmission
    :param config: runtime configuration
    :param dry_run: report only; no links created, no extraction, no notifications, no state written
    :param state: notified-problem store, also remembering completed extractions (omit to skip both)
    :param notifier: ntfy publisher (omit to skip notifications)
    :param extractor: RAR extraction tool (omit and any RAR-packed torrent is reported as a problem)
    :return: the aggregate report
    """
    report = Report()
    index  = build_index(config.movies_root, config.tv_root)
    layout = _layout_context(config, report)
    for torrent in torrents:
        if not torrent.finished:
            report.pending += 1
            continue
        _handle_torrent(
            torrent, config, report, dry_run=dry_run, state=state, extractor=extractor, index=index, layout=layout,
        )

    if dry_run or (state is None):
        return report

    current = {problem.key for problem in report.problems}
    for problem in report.problems:
        if problem.key not in state:
            if notifier is not None:
                notifier.send(problem.title, problem.message, priority='high', tags='warning')
            state.add(problem.key)

    state.prune(PROBLEM_PREFIXES, keep=current)
    state.save()
    return report
