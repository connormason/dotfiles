"""
Test suite command
"""
from __future__ import annotations

import argparse
import sys
from typing import ClassVar

from cli.infra.command import Command
from cli.utils.shell import shell_command
from cli.utils.uv import uv_command

__all__ = [
    'TestCommand',
]


# ==================================================================================================
# Testing commands
#
# Commands
#   - test: Run the test suite through the public-index uv wrapper
# ==================================================================================================


class TestCommand(Command):
    """
    Run the test suite via uv (public-index wrapper)
    """
    name:  ClassVar[str] = 'test'
    group: ClassVar[str] = 'Testing'

    class Args(argparse.Namespace):
        paths: list[str]        # positional arg(s) "PATHS"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            'paths',
            type=str,
            nargs='*',
            help='Test paths (default: tests/)',
        )

    def run(self, args: Args) -> None:
        result = shell_command(
            uv_command('run', '--group', 'test', 'pytest', *(args.paths or ['tests'])),
            check=False,
        )
        sys.exit(result.returncode)
