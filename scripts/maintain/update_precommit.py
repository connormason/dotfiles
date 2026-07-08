#!/usr/bin/env python3
"""
Script to update pre-commit hook versions using ``pre-commit autoupdate``.

Usage::

    python scripts/maintain/update_precommit.py [--dry-run] [--repo URL] [--config PATH]

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
    bleeding_edge: bool = False,
    freeze: bool = False,
    jobs: int | None = None,
    timeout: float | None = 120,
    **kwargs: Any,
) -> subprocess.CompletedProcess[str]:
    """
    Run ``pre-commit autoupdate`` and return the completed process.

    :param config_path: path to the pre-commit config file
    :param repo_urls: optional list of repo URLs to filter updates
    :param bleeding_edge: update to the bleeding edge of ``HEAD`` instead of the latest tagged version
    :param freeze: store frozen hashes in ``rev`` instead of tag names
    :param jobs: number of threads to use (defaults to ``pre-commit``'s built-in default of 1)
    :param timeout: command timeout
    :return: completed process from the autoupdate command
    """
    cmd: list[str] = ['pre-commit', 'autoupdate', '--config', str(config_path)]
    if bleeding_edge:
        cmd.append('--bleeding-edge')
    if freeze:
        cmd.append('--freeze')
    if jobs is not None:
        cmd.extend(['--jobs', str(jobs)])
    for url in repo_urls or []:
        cmd.extend(['--repo', url])

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
    config:        Path                 # --config
    repos:         list[str] | None     # --repo
    bleeding_edge: bool                 # --bleeding-edge
    freeze:        bool                 # --freeze
    jobs:          int | None           # --jobs
    timeout:       float                # --timeout
    dry_run:       bool                 # --dry-run


def build_parser() -> argparse.ArgumentParser:
    """
    Build argument parser for script.

    :return: :class:`argparse.ArgumentParser`
    """
    parser = argparse.ArgumentParser(
        description='Update pre-commit hook versions using pre-commit autoupdate',
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
    add_target_opts()

    def add_update_opts() -> None:
        """
        Add update behavior options to the argument parser.
        """
        update_opts = parser.add_argument_group('Update options')
        update_opts.add_argument(
            '--bleeding-edge',
            action='store_true',
            help='Update to the bleeding edge of `HEAD` instead of the latest tagged version',
        )
        update_opts.add_argument(
            '--freeze',
            action='store_true',
            help='Store frozen hashes in `rev` instead of tag names',
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
            help='Number of threads pre-commit should use (default: 1)',
        )
        execution_opts.add_argument(
            '-t',
            '--timeout',
            metavar='SECONDS',
            type=float,
            default=120,
            help='`pre-commit autoupdate` command timeout (in seconds)',
        )
        execution_opts.add_argument(
            '--dry-run',
            action='store_true',
            help='Run autoupdate, show what changed, but revert the file',
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


# TODO: ensure pre-commit is installed (or install it if not?)
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

        # Run pre-commit autoupdate
        print('Running pre-commit autoupdate...')
        result = run_autoupdate(
            config_path,
            repo_urls=args.repos,
            bleeding_edge=args.bleeding_edge,
            freeze=args.freeze,
            jobs=args.jobs,
            timeout=args.timeout,
        )

        # Show stdout from autoupdate (contains "Updating <repo> ... <from> -> <to>" lines)
        if result.stdout:
            print(result.stdout.rstrip())
        if result.stderr:
            print(result.stderr.rstrip(), file=sys.stderr)

        if result.returncode != 0:
            print(f'Error: pre-commit autoupdate exited with code {result.returncode}', file=sys.stderr)
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
        print('Error: pre-commit autoupdate timed out', file=sys.stderr)
        return 1

    except KeyboardInterrupt:
        print('Cancelled')
        return 1

    except Exception as e:
        print(f'Error: {e}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
