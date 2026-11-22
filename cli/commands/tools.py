"""
Tool installation commands (install-uv, install-hatch)
"""
from __future__ import annotations

import argparse
import sys
from typing import ClassVar

from cli.infra.command import Command
from cli.infra.config import INSTALLER_SCRIPTS
from cli.infra.config import InstallableTool
from cli.utils.scripts import check_script_validity
from cli.utils.shell import shell_command
from cli.utils.styling import HATCH
from cli.utils.styling import UV
from cli.utils.styling import style

__all__ = [
    'InstallHatchCommand',
    'InstallUvCommand',
]


# ==================================================================================================
# Tool installation commands
# ==================================================================================================


class _InstallToolCommand(Command, register=False):
    """
    Base for tool installer commands that wrap a ``scripts/install/*.py`` installer script.

    Subclasses set :cvar:`tool_name`, which keys the script in :data:`INSTALLER_SCRIPTS`.
    """
    group:     ClassVar[str] = 'Tool Installation'
    tool_name: ClassVar[InstallableTool]

    class Args(argparse.Namespace):
        force:       bool           # --force
        verbose:     bool           # --verbose
        retries:     int | None     # --retries
        retry_delay: int | None     # --retry-delay

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            '-f',
            '--force',
            action='store_true',
            help=f'Force reinstall even if {style(self.tool_name, fg="bright_magenta")} is already installed',
        )
        parser.add_argument(
            '-v',
            '--verbose',
            action='store_true',
            help='Enable verbose output for debugging',
        )
        parser.add_argument(
            '--retries',
            type=int,
            metavar='N',
            help='Maximum number of download retry attempts',
        )
        parser.add_argument(
            '--retry-delay',
            type=int,
            metavar='SECONDS',
            help='Initial delay in seconds between retries with exponential backoff',
        )

    def run(self, args: Args) -> None:
        script_path = INSTALLER_SCRIPTS[self.tool_name]
        check_script_validity(script_path, f'{self.tool_name} installer script')

        cmd: list[str] = [sys.executable, str(script_path)]
        if args.force:
            cmd.append('--force')
        if args.verbose:
            cmd.append('--verbose')
        if args.retries is not None:
            cmd.extend(['--retries', str(args.retries)])
        if args.retry_delay is not None:
            cmd.extend(['--retry-delay', str(args.retry_delay)])

        result = shell_command(cmd, check=False)
        sys.exit(result.returncode)


class InstallUvCommand(_InstallToolCommand):
    """
    Install `uv` Python package installer tool
    """
    name:        ClassVar[str]             = 'install-uv'
    description: ClassVar[str]             = f'Install {UV} Python package installer tool'
    tool_name:   ClassVar[InstallableTool] = 'uv'


class InstallHatchCommand(_InstallToolCommand):
    """
    Install `hatch` Python project management tool
    """
    name:        ClassVar[str]             = 'install-hatch'
    description: ClassVar[str]             = f'Install {HATCH} Python project management tool'
    tool_name:   ClassVar[InstallableTool] = 'hatch'
