#!/usr/bin/env python3
"""
Script to update pre-commit hook versions using ``prek auto-update``.

Usage::

    python scripts/codebase/update_prek.py [--dry-run] [--repo URL] [--config PATH]

"""
from __future__ import annotations

import argparse
import subprocess
import sys
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    'run_autoupdate',
]


def run_autoupdate(
    config_path: Path,
    *,
    repo_urls: list[str] | None = None,
    exclude_repos: list[str] | None = None,
    include_tags: list[str] | None = None,
    exclude_tags: list[str] | None = None,
    repo_include_tags: list[str] | None = None,
    repo_exclude_tags: list[str] | None = None,
    bleeding_edge: bool = False,
    freeze: bool = False,
    jobs: int | None = None,
    cooldown_days: int | None = None,
    refresh: bool = False,
    timeout: float | None = 120,
    **kwargs: Any,
) -> subprocess.CompletedProcess[str]:
    """
    Run ``prek auto-update`` and return the completed process.

    :param config_path: path to the pre-commit config file
    :param repo_urls: optional list of repo URLs to filter updates
    :param exclude_repos: optional list of repo URLs to exclude from updates
    :param include_tags: optional list of glob patterns for tags to consider
    :param exclude_tags: optional list of glob patterns for tags to ignore
    :param repo_include_tags: optional list of ``<repo>=<pattern>`` per-repo tag include filters
    :param repo_exclude_tags: optional list of ``<repo>=<pattern>`` per-repo tag exclude filters
    :param bleeding_edge: update to the bleeding edge of the default branch instead of latest tag
    :param freeze: store frozen hashes in ``rev`` instead of tag names
    :param jobs: number of threads prek should use (``0`` lets prek decide)
    :param cooldown_days: minimum release age (in days) for a version to be eligible
    :param refresh: refresh all cached prek data before running
    :param timeout: command timeout
    :return: completed process from the auto-update command
    """
    cmd: list[str] = ['prek', 'auto-update', '--config', str(config_path)]
    if refresh:
        cmd.append('--refresh')
    if bleeding_edge:
        cmd.append('--bleeding-edge')
    if freeze:
        cmd.append('--freeze')
    if jobs is not None:
        cmd.extend(['--jobs', str(jobs)])
    if cooldown_days is not None:
        cmd.extend(['--cooldown-days', str(cooldown_days)])
    for url in repo_urls or []:
        cmd.extend(['--repo', url])
    for url in exclude_repos or []:
        cmd.extend(['--exclude-repo', url])
    for pattern in include_tags or []:
        cmd.extend(['--include-tag', pattern])
    for pattern in exclude_tags or []:
        cmd.extend(['--exclude-tag', pattern])
    for spec in repo_include_tags or []:
        cmd.extend(['--repo-include-tag', spec])
    for spec in repo_exclude_tags or []:
        cmd.extend(['--repo-exclude-tag', spec])

    return subprocess.run(
        cmd,
        capture_output=kwargs.pop('capture_output', True),
        text=kwargs.pop('text', True),
        check=kwargs.pop('check', False),
        timeout=timeout,
        **kwargs,
    )


class Args(argparse.Namespace):
    """
    Annotated :class:`argparse.Namespace` for script command-line arguments.
    """
    config:            Path                 # --config
    repos:             list[str] | None     # --repo
    exclude_repos:     list[str] | None     # --exclude-repo
    include_tags:      list[str] | None     # --include-tag
    exclude_tags:      list[str] | None     # --exclude-tag
    repo_include_tags: list[str] | None     # --repo-include-tag
    repo_exclude_tags: list[str] | None     # --repo-exclude-tag
    bleeding_edge:     bool                 # --bleeding-edge
    freeze:            bool                 # --freeze
    cooldown_days:     int | None           # --cooldown-days
    jobs:              int | None           # --jobs
    refresh:           bool                 # --refresh
    timeout:           float                # --timeout
    dry_run:           bool                 # --dry-run


def build_parser() -> argparse.ArgumentParser:
    """
    Build argument parser for script.

    :return: :class:`argparse.ArgumentParser`
    """
    parser = argparse.ArgumentParser(
        description='Update pre-commit hook versions using prek auto-update',
        formatter_class=partial(argparse.HelpFormatter, max_help_position=50),
        add_help=False,
    )

    def add_target_opts() -> None:
        """
        Add config file and repo target options to the argument parser.
        """
        target_opts = parser.add_argument_group('Target options')
        target_opts.add_argument(
            '-c',
            '--config',
            type=Path,
            metavar='PATH',
            default='.pre-commit-config.yaml',
            help='Path to pre-commit config file (default: .pre-commit-config.yaml)',
        )
        target_opts.add_argument(
            '-r',
            '--repo',
            action='append',
            dest='repos',
            metavar='URL',
            help='Only update the given repo (can be repeated)',
        )
        target_opts.add_argument(
            '--exclude-repo',
            action='append',
            dest='exclude_repos',
            metavar='URL',
            help='Skip the given repo (can be repeated)',
        )
        target_opts.add_argument(
            '--include-tag',
            action='append',
            dest='include_tags',
            metavar='PATTERN',
            help='Only consider tags matching this glob pattern (can be repeated)',
        )
        target_opts.add_argument(
            '--exclude-tag',
            action='append',
            dest='exclude_tags',
            metavar='PATTERN',
            help='Ignore tags matching this glob pattern (can be repeated)',
        )
        target_opts.add_argument(
            '--repo-include-tag',
            action='append',
            dest='repo_include_tags',
            metavar='REPO=PATTERN',
            help='Per-repo tag include filter as <repo>=<pattern> (can be repeated)',
        )
        target_opts.add_argument(
            '--repo-exclude-tag',
            action='append',
            dest='repo_exclude_tags',
            metavar='REPO=PATTERN',
            help='Per-repo tag exclude filter as <repo>=<pattern> (can be repeated)',
        )
    add_target_opts()

    def add_update_opts() -> None:
        """
        Add update behavior options to the argument parser.
        """
        update_opts = parser.add_argument_group('Update options')
        update_opts.add_argument(
            '--bleeding-edge',
            action='store_true',
            help='Update to the bleeding edge of the default branch instead of latest tag',
        )
        update_opts.add_argument(
            '--freeze',
            action='store_true',
            help='Store frozen hashes in `rev` instead of tag names',
        )
        update_opts.add_argument(
            '--cooldown-days',
            type=int,
            metavar='DAYS',
            default=None,
            help='Minimum release age (in days) required for a version to be eligible',
        )
    add_update_opts()

    def add_execution_opts() -> None:
        """
        Add execution control options to the argument parser.
        """
        execution_opts = parser.add_argument_group('Execution options')
        execution_opts.add_argument(
            '-j',
            '--jobs',
            type=int,
            metavar='N',
            default=None,
            help='Number of threads prek should use (0 lets prek decide)',
        )
        execution_opts.add_argument(
            '--refresh',
            action='store_true',
            help='Refresh all cached prek data before running',
        )
        execution_opts.add_argument(
            '-t',
            '--timeout',
            metavar='SECONDS',
            type=float,
            default=120,
            help='`prek auto-update` command timeout (in seconds)',
        )
        execution_opts.add_argument(
            '--dry-run',
            action='store_true',
            help='Run auto-update, show what changed, but revert the file',
        )
    add_execution_opts()

    def add_other_opts() -> None:
        """
        Add help and miscellaneous options to the argument parser.
        """
        other_opts = parser.add_argument_group('Other options')
        other_opts.add_argument(
            '-h',
            '--help',
            action='help',
            default=argparse.SUPPRESS,
            help='Show help message and exit',
        )
    add_other_opts()

    return parser


# TODO: ensure prek is installed (or install it if not?)
def main(argv: Sequence[str] | None = None) -> int:
    """
    Main entry point for the script.

    :param argv: argument list to parse, defaults to sys.argv[1:]
    :return: int script exit code
    """
    parser = build_parser()
    args   = parser.parse_args(argv, namespace=Args())

    if args.timeout < 0:
        print('Error: --timeout cannot be negative', file=sys.stderr)
        return 1
    if (args.cooldown_days is not None) and (args.cooldown_days < 0):
        print('Error: --cooldown-days cannot be negative', file=sys.stderr)
        return 1
    if (args.jobs is not None) and (args.jobs < 0):
        print('Error: --jobs cannot be negative', file=sys.stderr)
        return 1

    config_path = Path(args.config)
    if not config_path.exists():
        print(f'Error: config file not found at {config_path}', file=sys.stderr)
        return 1

    try:

        # Read current config content
        original_content = config_path.read_text(encoding='utf-8')

        # Run prek auto-update
        print('Running prek auto-update...')
        result = run_autoupdate(
            config_path,
            repo_urls=args.repos,
            exclude_repos=args.exclude_repos,
            include_tags=args.include_tags,
            exclude_tags=args.exclude_tags,
            repo_include_tags=args.repo_include_tags,
            repo_exclude_tags=args.repo_exclude_tags,
            bleeding_edge=args.bleeding_edge,
            freeze=args.freeze,
            jobs=args.jobs,
            cooldown_days=args.cooldown_days,
            refresh=args.refresh,
            timeout=args.timeout,
        )

        # Show stdout from auto-update (contains "Updating <repo> ... <from> -> <to>" lines)
        if result.stdout:
            print(result.stdout.rstrip())
        if result.stderr:
            print(result.stderr.rstrip(), file=sys.stderr)

        if result.returncode != 0:
            print(f'Error: prek auto-update exited with code {result.returncode}', file=sys.stderr)
            return 1

        # Read the (possibly updated) config
        updated_content = config_path.read_text(encoding='utf-8')

        # Detect changes
        if has_changes := original_content != updated_content:
            print('Changes detected in pre-commit config')
        else:
            print('No changes detected - hooks are already up to date')

        if args.dry_run:

            # Restore original content if updated but --dry-run requested
            if has_changes:
                config_path.write_text(original_content, encoding='utf-8')
                print('Dry run - reverted config file to original content')

            return 0

        if has_changes:
            print(f'Successfully updated {config_path}')
        return 0

    except subprocess.TimeoutExpired:
        print('Error: prek auto-update timed out', file=sys.stderr)
        return 1

    except KeyboardInterrupt:
        print('Cancelled')
        return 1

    except Exception as e:
        print(f'Error: {e}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
