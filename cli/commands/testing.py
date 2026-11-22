"""
Test suite commands
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
    'TestCovCommand',
    'TestFullCommand',
    'TestIntegrationCommand',
    'TestUnitCommand',
]


# ==================================================================================================
# Testing commands
#
# Every command runs pytest through the public-index uv wrapper and accepts optional PATHS that replace its default
# target (any command's markers and options still apply).
#
# Commands
#   - test:             Run the unit tests that are not marked slow
#   - test-full:        Run the full test suite
#   - test-unit:        Run all unit tests, including slow ones
#   - test-integration: Run the integration tests
#   - test-cov:         Run the full test suite under coverage and report the result
# ==================================================================================================


class _PytestCommand(Command, register=False):
    """
    Base for commands that run a subset of the suite: subclasses set the default target and pytest options
    """
    group: ClassVar[str] = 'Testing'

    default_paths: ClassVar[tuple[str, ...]] = ('tests',)
    pytest_args:   ClassVar[tuple[str, ...]] = ()

    class Args(argparse.Namespace):
        paths: list[str]        # positional arg(s) "PATHS"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            'paths',
            type=str,
            nargs='*',
            help=f'Test paths (default: {" ".join(self.default_paths)})',
        )

    def build_commands(self, paths: list[str]) -> list[list[str]]:
        """
        Build the argv of each step of the command, in execution order.

        :param paths: test paths from the command line; empty to use :attr:`default_paths`
        :return: list of ``uv`` command lines
        """
        return [uv_command('run', '--group', 'test', 'pytest', *self.pytest_args, *(paths or self.default_paths))]

    def run(self, args: Args) -> None:
        returncode = 0
        for cmd in self.build_commands(args.paths):
            returncode = shell_command(cmd, check=False).returncode
            if returncode != 0:
                break
        sys.exit(returncode)


class TestCommand(_PytestCommand):
    """
    Run the unit tests that are not marked slow (fast feedback)
    """
    name: ClassVar[str] = 'test'

    default_paths: ClassVar[tuple[str, ...]] = ('tests/unit',)
    pytest_args:   ClassVar[tuple[str, ...]] = ('-m', 'not slow')


class TestFullCommand(_PytestCommand):
    """
    Run the full test suite (unit + integration), as CI does
    """
    name: ClassVar[str] = 'test-full'


class TestUnitCommand(_PytestCommand):
    """
    Run all unit tests, including slow ones
    """
    name: ClassVar[str] = 'test-unit'

    default_paths: ClassVar[tuple[str, ...]] = ('tests/unit',)


class TestIntegrationCommand(_PytestCommand):
    """
    Run the integration tests
    """
    name: ClassVar[str] = 'test-integration'

    default_paths: ClassVar[tuple[str, ...]] = ('tests/integration',)


class TestCovCommand(_PytestCommand):
    """
    Run the full test suite under coverage and report the result
    """
    name: ClassVar[str] = 'test-cov'

    def build_commands(self, paths: list[str]) -> list[list[str]]:
        """
        Build the coverage run, HTML report, and terminal report steps.

        :param paths: test paths from the command line; empty to use :attr:`default_paths`
        :return: list of ``uv`` command lines
        """
        return [
            uv_command('run', '--group', 'test', 'coverage', 'run', '-m', 'pytest', *(paths or self.default_paths)),
            uv_command('run', '--group', 'test', 'coverage', 'html'),
            uv_command('run', '--group', 'test', 'coverage', 'report'),
        ]
