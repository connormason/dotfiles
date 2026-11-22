"""
Static analysis commands (docs-audit)
"""
from __future__ import annotations

import argparse
import sys
from typing import ClassVar

from cli.infra.command import Command
from cli.infra.config import DOTFILES_DIR
from cli.utils.shell import shell_command
from cli.utils.styling import printf

__all__ = [
    'DocsAuditCommand',
]


# ==================================================================================================
# Static analysis commands
#
# Commands
#   - docs-audit: Audit per-directory README documentation (scripts/docs_audit)
# ==================================================================================================


class DocsAuditCommand(Command):
    """
    Audit per-directory README documentation (missing, stale, structural, links, policy)
    """
    name:  ClassVar[str] = 'docs-audit'
    group: ClassVar[str] = 'Static Analysis'

    class Args(argparse.Namespace):
        scopes:  list[str]      # positional arg(s) "SCOPE"
        json:    bool           # --json
        no_fail: bool           # --no-fail

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            'scopes',
            type=str,
            nargs='*',
            metavar='SCOPE',
            help='Repo-relative paths to audit (default: whole repo)',
        )
        parser.add_argument(
            '--json',
            action='store_true',
            help='Emit structured JSON instead of styled text',
        )
        parser.add_argument(
            '--no-fail',
            action='store_true',
            help='Always exit 0, even when findings exist',
        )

    def run(self, args: Args) -> None:
        cmd: list[str] = [sys.executable, '-m', 'scripts.docs_audit', *args.scopes]
        if args.json:
            cmd.append('--json')
        if args.no_fail:
            cmd.append('--no-fail')

        # Keep stdout machine-readable under --json
        if not args.json:
            printf('🔎 Auditing README documentation...', fg='bright_cyan')
        result = shell_command(cmd, check=False, cwd=DOTFILES_DIR)
        sys.exit(result.returncode)
