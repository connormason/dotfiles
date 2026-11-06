"""
Command-line entry point for the deterministic docs audit.

Usage::

    uv run python -m scripts.docs_audit [SCOPE ...] [--json] [--no-fail]

Exits 0 when no findings exist (or with ``--no-fail``), 1 when findings exist, and 2 on usage/internal error.
"""
from __future__ import annotations

import argparse
import functools
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from scripts.docs_audit.audit import run_audit

if TYPE_CHECKING:
    from collections.abc import Sequence


class Args(argparse.Namespace):
    """
    Annotated :class:`argparse.Namespace` for the docs_audit CLI.
    """
    scopes:  list[str]   # positional SCOPE paths
    json:    bool        # --json
    no_fail: bool        # --no-fail


def parse_args(argv: Sequence[str] | None = None) -> Args:
    """
    Parse command-line arguments.

    :param argv: argument list to parse, defaults to ``sys.argv[1:]``
    :return: an annotated :class:`Args`
    """
    parser = argparse.ArgumentParser(
        prog='python -m scripts.docs_audit',
        description='Deterministic per-directory README audit',
        formatter_class=functools.partial(
            argparse.RawTextHelpFormatter,
            max_help_position=50,
        ),
        add_help=False,
    )
    parser.add_argument(
        'scopes',
        nargs='*',
        help='repo-relative scope paths (default: whole repo)',
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='emit structured JSON instead of styled text',
    )
    parser.add_argument(
        '--no-fail',
        action='store_true',
        help='always exit 0, even when findings exist',
    )
    parser.add_argument(
        '-h',
        '--help',
        action='help',
        default=argparse.SUPPRESS,
        help='Show this help message and exit',
    )
    return parser.parse_args(argv, namespace=Args())


def _repo_root() -> Path:
    """
    Resolve the repository root via ``git rev-parse --show-toplevel``.

    :raises SystemExit: with code 2 when not inside a git repository
    :return: absolute path to the repository root
    """
    result = subprocess.run(
        ['git', 'rev-parse', '--show-toplevel'],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print('docs-audit: not inside a git repository', file=sys.stderr)
        raise SystemExit(2)
    return Path(result.stdout.strip())


def main(argv: Sequence[str] | None = None) -> int:
    """
    Run the audit and return the process exit code.

    :param argv: argument list to parse, defaults to ``sys.argv[1:]``
    :return: 0 (clean or --no-fail), 1 (findings), or 2 (usage/internal error)
    """
    args      = parse_args(argv)
    repo_root = _repo_root()
    scopes    = [Path(s) for s in args.scopes] or [Path()]

    try:
        report = run_audit(scopes, repo_root=repo_root)
    except (subprocess.CalledProcessError, OSError) as e:
        print(f'docs-audit: failed to run git while auditing: {e}', file=sys.stderr)
        return 2

    print(report.to_json() if args.json else report.to_text())

    if args.no_fail:
        return 0
    return 1 if report.has_findings else 0


if __name__ == '__main__':
    sys.exit(main())
