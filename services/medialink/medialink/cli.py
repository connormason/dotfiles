"""
Command-line entry point: ``run`` (service loop), ``once`` (single pass / dry run) and ``dedupe``
"""
from __future__ import annotations

import argparse
import functools
import logging
import sys
import time
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING

from medialink.archives import Extractor
from medialink.config import Config
from medialink.config import ConfigError
from medialink.dedupe import dedupe
from medialink.dedupe import flat_duplicates
from medialink.engine import reconcile
from medialink.layout import load_overrides
from medialink.notify import Notifier
from medialink.reorganize import CONFLICT
from medialink.reorganize import CROSS
from medialink.reorganize import PROBLEMS
from medialink.reorganize import UNPARSED
from medialink.reorganize import apply_plan
from medialink.reorganize import discover
from medialink.reorganize import make_plan
from medialink.reorganize import select
from medialink.reorganize import undo
from medialink.state import State
from medialink.transmission import TransmissionClient
from medialink.transmission import TransmissionError

if TYPE_CHECKING:
    from collections.abc import Callable
    from collections.abc import Sequence

    from medialink.engine import Report
    from medialink.transmission import Torrent

__all__ = [
    'EXIT_CONFIG',
    'EXIT_OK',
    'EXIT_PROBLEMS',
    'EXIT_RPC',
    'main',
    'run_loop',
]

logger = logging.getLogger(__name__)

EXIT_OK       = 0
EXIT_PROBLEMS = 1  # a pass finished but some torrents could not be placed
EXIT_RPC      = 2  # Transmission unreachable
EXIT_CONFIG   = 3  # unusable configuration

OUTAGE_KEY = 'rpc-outage'
GIB        = 1024 ** 3


class Args(argparse.Namespace):
    """
    Typed view of the parsed command line
    """
    command: str        # command
    verbose: bool       # --verbose
    dry_run: bool       # --dry-run         "once" command only
    apply:   bool       # --apply           "dedupe" and "reorganize" commands
    quick:   bool       # --quick           "dedupe" command only
    limit:   int | None # --limit           "reorganize" command only
    only:    str        # --only            "reorganize" command only
    undo:    str | None # --undo            "reorganize" command only


def _build_parser() -> argparse.ArgumentParser:
    """
    Build the argument parser

    :return: the configured parser
    """
    formatter = functools.partial(argparse.RawTextHelpFormatter, max_help_position=50)
    parser = argparse.ArgumentParser(
        prog='medialink',
        description='Hardlink finished Transmission torrents into the Jellyfin/Plex media directories.',
        formatter_class=formatter,
        add_help=False,
    )
    commands = parser.add_subparsers(dest='command', required=True, metavar='COMMAND')

    def add_common_opts(sub: argparse.ArgumentParser) -> None:
        """
        Add the output and help options every command shares

        :param sub: the subcommand parser
        """
        output_opts = sub.add_argument_group('Output options')
        output_opts.add_argument(
            '-v',
            '--verbose',
            action='store_true',
            help='Log every action, not only changes',
        )
        other_opts = sub.add_argument_group('Other options')
        other_opts.add_argument(
            '-h',
            '--help',
            action='help',
            default=argparse.SUPPRESS,
            help='Show this help message and exit',
        )

    run = commands.add_parser(
        'run',
        formatter_class=formatter,
        add_help=False,
        help='Reconcile every MEDIALINK_INTERVAL seconds until stopped',
    )
    add_common_opts(run)

    once = commands.add_parser(
        'once',
        formatter_class=formatter,
        add_help=False,
        help='Run a single reconcile pass and exit',
    )
    once_opts = once.add_argument_group('Reconcile options')
    once_opts.add_argument(
        '-n',
        '--dry-run',
        action='store_true',
        help='Report what would be linked; change nothing',
    )
    add_common_opts(once)

    dedupe_cmd = commands.add_parser(
        'dedupe',
        formatter_class=formatter,
        add_help=False,
        help='Replace identical legacy copies in the library with hardlinks',
    )
    dedupe_opts = dedupe_cmd.add_argument_group('Dedupe options')
    dedupe_opts.add_argument(
        '--apply',
        action='store_true',
        help='Replace/remove files (default is a dry run)',
    )
    dedupe_opts.add_argument(
        '--quick',
        action='store_true',
        help='Compare size plus sampled blocks instead of hashing whole files (much faster)',
    )
    add_common_opts(dedupe_cmd)

    reorganize_cmd = commands.add_parser(
        'reorganize',
        formatter_class=formatter,
        add_help=False,
        help='Move library links into Movie (Year)/ and Show/Season NN/ folders',
    )
    reorganize_opts = reorganize_cmd.add_argument_group('Reorganize options')
    reorganize_opts.add_argument(
        '--apply',
        action='store_true',
        help='Move the links (default is a dry run that only reports)',
    )
    reorganize_opts.add_argument(
        '--limit',
        type=int,
        metavar='N',
        help='Apply at most N torrents, in name order, to check a batch before continuing',
    )
    reorganize_opts.add_argument(
        '--only',
        default='',
        metavar='REGEX',
        help='Only entries whose torrent name or path matches this case-insensitive pattern',
    )
    reorganize_opts.add_argument(
        '--undo',
        metavar='JOURNAL',
        help='Restore the moves recorded in a journal (a dry run unless --apply is given)',
    )
    add_common_opts(reorganize_cmd)

    other_opts = parser.add_argument_group('Other options')
    other_opts.add_argument(
        '-h',
        '--help',
        action='help',
        default=argparse.SUPPRESS,
        help='Show this help message and exit',
    )
    return parser


def _print_report(report: Report, *, dry_run: bool) -> None:
    """
    Print a human-readable summary of a pass to stdout

    :param report: the pass report
    :param dry_run: whether nothing was changed
    """
    verb = 'would link' if dry_run else 'linked'
    print(
        f'{verb}: {report.counts["linked"]}   '
        f'already linked: {report.counts["exists"]}   '
        f'legacy copies: {report.counts["legacy-copy"]}   '
        f'in progress: {report.pending}'
    )
    for problem in report.problems:
        print(f'PROBLEM  {problem.title}: {problem.message}')


def run_loop(
    config: Config,
    client: TransmissionClient,
    notifier: Notifier,
    state: State,
    *,
    extractor: Extractor | None = None,
    sleep: Callable[[float], None] = time.sleep,
    max_cycles: int | None = None,
) -> int:
    """
    Reconcile on an interval

    Returns (rather than looping forever) once Transmission has been unreachable for ``config.max_failures``
    consecutive cycles, so the container exits non-zero and the restart policy and ``docker ps`` show it. The outage
    alert is deduplicated through ``state`` so restart loops do not repeat it.

    :param config: runtime configuration
    :param client: Transmission client
    :param notifier: ntfy publisher
    :param state: notified-problem store
    :param extractor: RAR extraction tool, or None when unavailable or disabled
    :param sleep: injectable sleep (tests)
    :param max_cycles: stop after this many cycles (tests); None runs until an outage
    :return: ``EXIT_RPC`` after a sustained outage, ``EXIT_OK`` when ``max_cycles`` is reached
    """
    failures      = 0
    cycles        = 0
    last_problems = 0
    while (max_cycles is None) or (cycles < max_cycles):
        cycles += 1
        try:
            torrents = client.get_torrents()
        except TransmissionError as e:
            failures += 1
            logger.error('cycle failed (%d/%d): %s', failures, config.max_failures, e)
            if failures >= config.max_failures:
                if OUTAGE_KEY not in state:
                    notifier.send(
                        'Transmission unreachable',
                        f'{failures} consecutive failures: {e}',
                        priority='urgent',
                        tags='rotating_light',
                    )
                    state.add(OUTAGE_KEY)
                    state.save()
                return EXIT_RPC
        else:
            if failures:
                logger.info('Transmission reachable again after %d failed cycle(s)', failures)

            failures = 0
            if OUTAGE_KEY in state:
                state.discard(OUTAGE_KEY)
                state.save()

            report  = reconcile(torrents, config, state=state, notifier=notifier, extractor=extractor)
            # INFO only when something changed (new links or extractions, or the number of problems moved); a steady
            # state, including a known stuck torrent, stays at DEBUG instead of logging every cycle
            changed = report.counts['linked'] or report.counts['extracted'] or len(report.problems) != last_problems
            last_problems = len(report.problems)
            logger.log(
                logging.INFO if changed else logging.DEBUG,
                'cycle ok: %d linked, %d already linked, %d problem(s), %d in progress',
                report.counts['linked'],
                report.counts['exists'],
                len(report.problems),
                report.pending,
            )

        sleep(config.interval)
    return EXIT_OK


def _shown(path: Path | None, config: Config) -> str:
    """
    Format a library path relative to the media root

    :param path: absolute path, or None
    :param config: runtime configuration
    :return: the relative path, or an empty string
    """
    if path is None:
        return ''
    try:
        return path.relative_to(config.media_root).as_posix()
    except ValueError:
        return str(path)


def _run_reorganize(args: Args, config: Config, torrents: list[Torrent], state: State) -> int:
    """
    Plan, and with ``--apply`` carry out, the move into the Jellyfin layout

    :param args: parsed command line
    :param config: runtime configuration
    :param torrents: torrents from Transmission
    :param state: store of finished extractions
    :return: ``EXIT_OK``, or ``EXIT_PROBLEMS`` when files are in conflict or could not be placed
    """
    try:
        overrides = load_overrides(config.overrides_path)
    except ConfigError as e:
        logger.error('configuration error: %s', e)
        return EXIT_CONFIG

    entries  = make_plan(discover(torrents, config, state), config, overrides)
    selected = select(entries, only=args.only, limit=args.limit)
    counts   = Counter(e.action for e in selected)

    for entry in selected:
        if (entry.action in PROBLEMS) or args.verbose or (entry.action == CROSS):
            detail = f'  ({entry.detail})' if entry.detail else ''
            print(f'{entry.action:14} {_shown(entry.current, config)} -> {_shown(entry.target, config)}{detail}')

    print(', '.join(f'{action}: {n}' for action, n in sorted(counts.items())) or 'nothing owned by medialink found')
    if not args.apply:
        print('dry run: nothing was moved (use --apply)')
        return EXIT_PROBLEMS if (counts[CONFLICT] or counts[UNPARSED]) else EXIT_OK

    result = apply_plan(selected, config)
    print(f'applied: {result.done}   journal: {config.journal_path}')
    for error in result.errors:
        print(f'ERROR    {error}')
    return EXIT_PROBLEMS if (result.errors or counts[CONFLICT] or counts[UNPARSED]) else EXIT_OK


def _run_undo(args: Args, config: Config) -> int:
    """
    Restore moves recorded in a journal

    :param args: parsed command line (``undo`` holds the journal path)
    :param config: runtime configuration
    :return: ``EXIT_OK``, or ``EXIT_PROBLEMS`` when some records could not be restored
    """
    result = undo(config, Path(args.undo or ''), apply=args.apply)
    for error in result.errors:
        print(f'SKIPPED  {error}')
    print(f'{"restored" if args.apply else "would restore"}: {result.done}')
    if not args.apply:
        print('dry run: nothing was moved (use --apply)')
    return EXIT_PROBLEMS if result.errors else EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    """
    Run the command line

    :param argv: arguments (defaults to ``sys.argv[1:]``)
    :return: process exit code
    """
    args = _build_parser().parse_args(argv, namespace=Args())
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s',
        stream=sys.stderr,
    )

    try:
        config = Config.from_env()
    except ConfigError as e:
        logger.error('configuration error: %s', e)
        return EXIT_CONFIG

    client   = TransmissionClient(config.rpc_url, config.rpc_user, config.rpc_password)
    notifier = Notifier(config.ntfy_url, config.ntfy_topic, config.ntfy_token)
    state    = State(config.state_path)

    extractor = Extractor.discover(config.extractor) if config.extract else None
    if config.extract and (extractor is None):
        logger.warning('no RAR extractor found (unrar / 7z); RAR-packed torrents will be reported as problems')

    if args.command == 'run':
        logger.info(
            'medialink starting: %s, every %ds, extractor: %s',
            config.media_root,
            config.interval,
            extractor.binary if extractor else 'none',
        )
        return run_loop(config, client, notifier, state, extractor=extractor)

    if (args.command == 'reorganize') and args.undo:
        return _run_undo(args, config)

    try:
        torrents = client.get_torrents()
    except TransmissionError as e:
        logger.error('%s', e)
        return EXIT_RPC

    if args.command == 'reorganize':
        return _run_reorganize(args, config, torrents, state)

    if args.command == 'once':
        report = reconcile(torrents, config, dry_run=args.dry_run, state=state, notifier=notifier, extractor=extractor)
        _print_report(report, dry_run=args.dry_run)
        return EXIT_OK if report.ok else EXIT_PROBLEMS

    # dedupe: inspect with a dry-run reconcile (creates nothing), then act on the legacy copies it found.
    # The flat scan runs second, so a foldered twin made by an earlier `once` is what justifies removing a flat file.
    # `state` is passed so finished extractions are recognised (a dry run never writes it); without it every RAR set
    # would be logged as "would extract" again.
    report    = reconcile(torrents, config, dry_run=True, state=state)
    outcomes  = dedupe(report.results, apply=args.apply, quick=args.quick)
    outcomes += flat_duplicates((config.movies_root, config.tv_root), apply=args.apply, quick=args.quick)
    for outcome in outcomes:
        if outcome.action in {'differs', 'error'} or args.verbose:
            print(f'{outcome.action:18} {outcome.dest} {outcome.detail}'.rstrip())

    freed   = {'replaced', 'would-replace', 'removed-flat', 'would-remove-flat'}
    reclaim = sum(o.size for o in outcomes if o.action in freed)
    verb    = 'reclaimed' if args.apply else 'reclaimable'

    print(f'{verb}: {reclaim / GIB:.1f} GiB across {sum(o.action in freed for o in outcomes)} file(s)')
    print(
        f'  mirrored copies -> links: {sum(o.action.endswith("replace") or o.action == "replaced" for o in outcomes)}'
        f'   flat duplicates: {sum(o.action.endswith("flat") for o in outcomes)}'
        f'   differing: {sum(o.action == "differs" for o in outcomes)}'
        f'   errors: {sum(o.action == "error" for o in outcomes)}'
    )

    return EXIT_OK
