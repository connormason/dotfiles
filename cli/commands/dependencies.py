"""
Dependency lock commands (lock, lock-check, lock-upgrade, lock-sync)
"""
from __future__ import annotations

import argparse
import sys
from typing import ClassVar

from cli.infra import config
from cli.infra.command import Command
from cli.infra.config import ExitCode
from cli.utils.python import check_python
from cli.utils.styling import printf
from cli.utils.styling import style
from cli.utils.uv import ensure_uv
from cli.utils.uv import uv_lock
from cli.utils.uv import uv_run
from cli.utils.venv import ensure_venv

__all__ = [
    'LockCheckCommand',
    'LockCommand',
    'LockSyncCommand',
    'LockUpgradeCommand',
    'regenerate_derived_files',
]


# ==================================================================================================
# Dependencies commands
#
# Commands:
#   - lock:         Update uv.lock from pyproject.toml
#   - lock-check:   Check that uv.lock is up to date
#   - lock-upgrade: Upgrade locked dependency versions
#   - lock-sync:    Re-sync dependencies, exported requirements, and hook versions from uv.lock
# ==================================================================================================


def regenerate_derived_files(*, indent: int = 0) -> None:
    """
    Regenerate files derived from ``uv.lock`` (exported requirements + pinned hook versions).

    Runs the ``uv-export`` / ``sync-with-uv`` / ``sync-pre-commit-deps`` prek hooks against all files. These are fixer
    hooks that exit nonzero when they rewrite a file, so the run uses ``check=False``.
    """
    printf('📦 Regenerating files derived from uv.lock...', fg='bright_cyan', indent=indent)
    uv_run(
        ['prek', 'run', '--all-files', '--no-progress', *config.DERIVED_FILE_HOOK_IDS],
        indent=indent + 3,
        check=False,
    )


class LockCommand(Command):
    """
    Update uv.lock from pyproject.toml
    """
    name:  ClassVar[str] = 'lock'
    group: ClassVar[str] = 'Dependencies'

    class Args(argparse.Namespace):
        refresh: bool       # --refresh

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            '--refresh',
            action='store_true',
            help='Refresh cached package metadata',
        )

    def run(self, args: Args) -> None:
        check_python(quiet=True)
        ensure_uv(quiet=True)

        printf('🔒 Updating uv.lock...', fg='bright_cyan')
        result = uv_lock(refresh=args.refresh, check=False, indent=3)
        if result.returncode == 0:
            printf('')
            regenerate_derived_files()
        sys.exit(result.returncode)


class LockCheckCommand(Command):
    """
    Check that uv.lock is up to date with pyproject.toml
    """
    name:  ClassVar[str] = 'lock-check'
    group: ClassVar[str] = 'Dependencies'

    def run(self, args: argparse.Namespace) -> None:
        check_python(quiet=True)
        ensure_uv(quiet=True)

        printf('🔎 Checking uv.lock...', fg='bright_cyan')
        result = uv_lock(check_only=True, check=False, indent=3)
        if result.returncode != 0:
            printf('🔴 uv.lock is out of date', fg='bright_red')
            printf(f'Update it with: {style("make lock", fg="bright_magenta")}', fg='bright_white', indent=3)
            sys.exit(ExitCode.COMMAND_FAILED)
        printf('✅ uv.lock is up to date', fg='bright_green')


class LockUpgradeCommand(Command):
    """
    Upgrade locked dependency versions in uv.lock
    """
    name:  ClassVar[str] = 'lock-upgrade'
    group: ClassVar[str] = 'Dependencies'

    class Args(argparse.Namespace):
        packages: list[str] | None      # --package

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            '-P',
            '--package',
            dest='packages',
            action='append',
            metavar='PACKAGE',
            help='Upgrade only this package (may be repeated; default: upgrade all packages)',
        )

    def run(self, args: Args) -> None:
        check_python(quiet=True)
        ensure_uv(quiet=True)

        printf('⏬ Upgrading uv.lock...', fg='bright_cyan')
        result = uv_lock(upgrade=not args.packages, upgrade_packages=args.packages, check=False, indent=3)
        if result.returncode == 0:
            printf('')
            regenerate_derived_files()
        sys.exit(result.returncode)


class LockSyncCommand(Command):
    """
    Re-sync dependencies, exported requirements, and hook versions from the committed uv.lock
    """
    name:  ClassVar[str] = 'lock-sync'
    group: ClassVar[str] = 'Dependencies'

    def run(self, args: argparse.Namespace) -> None:
        check_python(quiet=True)
        ensure_uv(quiet=True)
        ensure_venv(groups=['lint'], inexact=True, frozen=True)
        regenerate_derived_files()
