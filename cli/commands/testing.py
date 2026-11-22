"""
Test suite commands
"""
from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path
from typing import ClassVar

from cli.infra.command import Command
from cli.utils.shell import shell_command
from cli.utils.styling import printf
from cli.utils.uv import uv_command

__all__ = [
    'ANALYZE_DEFAULT_DURATIONS',
    'TestAnalyzeCommand',
    'TestCommand',
    'TestCovCommand',
    'TestFullCommand',
    'TestIntegrationCommand',
    'TestUnitCommand',
]

#: Default ``--durations`` count for ``--analyze`` and ``test-analyze``
ANALYZE_DEFAULT_DURATIONS: int = 20


def _combine_markers(*exprs: str | None) -> str | None:
    """
    AND together mark expressions, skipping empty ones.

    :param exprs: mark expressions to combine
    :return: the single expression as-is, several parenthesized and joined with ``and``, or None if there are none
    """
    parts = [expr for expr in exprs if expr]
    if len(parts) <= 1:
        return parts[0] if parts else None
    return ' and '.join(f'({part})' for part in parts)


def _uv_test(*cmd: str) -> list[str]:
    """
    Build the public-index ``uv run`` command line for the ``test`` dependency group

    :param cmd: command and arguments to run in the test environment
    :return: command line
    """
    return uv_command('run', '--group', 'test', *cmd)


# ==================================================================================================
# Testing commands
#
# Every command runs pytest through the public-index uv wrapper and shares the same options (PATHS replace the
# command's default target; marker, coverage, and timing options compose with the command's built-in settings).
# The generated Makefile cannot forward flags, so presets (test-cov, test-analyze) cover the common combinations.
#
# Commands
#   - test:             Run the unit tests that are not marked slow
#   - test-full:        Run the full test suite
#   - test-unit:        Run all unit tests, including slow ones
#   - test-integration: Run the integration tests
#   - test-cov:         Run the full test suite under coverage
#   - test-analyze:     Run the full test suite with coverage and timing analysis
# ==================================================================================================


class _PytestCommand(Command, register=False):
    """
    Base for commands that run a subset of the suite: subclasses set the default target, built-in marker, and presets
    """
    group: ClassVar[str] = 'Testing'

    default_paths:   ClassVar[tuple[str, ...]] = ('tests',)
    builtin_marker:  ClassVar[str | None]      = None
    always_coverage: ClassVar[bool]            = False
    always_analyze:  ClassVar[bool]            = False

    class Args(argparse.Namespace):
        paths:     list[str]        # positional arg(s) "PATHS"
        marker:    str | None       # --marker
        args:      str | None       # --args
        verbose:   int              # --verbose
        coverage:  bool             # --coverage
        durations: int | None       # --durations
        quick:     bool             # --quick
        analyze:   bool             # --analyze

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.set_defaults(quick=False, analyze=False)
        parser.add_argument(
            'paths',
            type=str,
            nargs='*',
            help=f'Test paths (default: {" ".join(self.default_paths)})',
        )

        def add_pytest_opts() -> None:
            pytest_opts = parser.add_argument_group(
                'Pytest options',
                description='Options passed directly to pytest',
            )
            pytest_opts.add_argument(
                '-m',
                '--marker',
                type=str,
                help=(
                    'Only run tests matching given mark expression (e.g., "integration"). '
                    "Combined with the command's own marker, if any"
                ),
            )
            pytest_opts.add_argument(
                '--args',
                type=str,
                help='Additional arguments to pass directly to pytest; use the = form (e.g., --args="-x -k foo")',
            )
        add_pytest_opts()

        def add_output_opts() -> None:
            output_opts = parser.add_argument_group(
                'Output options',
                description='Options for configuring output (logging) from tests',
            )
            output_opts.add_argument(
                '-v',
                '--verbose',
                action='count',
                default=0,
                help='pytest verbosity level (repeat for more)',
            )
        add_output_opts()

        def add_analysis_opts() -> None:
            analysis_opts = parser.add_argument_group(
                'Analysis options',
                description='Options for test coverage and timing analysis',
            )
            analysis_opts.add_argument(
                '-c',
                '--cov',
                '--coverage',
                dest='coverage',
                action='store_true',
                default=False,
                help='Run under coverage, then write the HTML report and print the terminal summary',
            )
            analysis_opts.add_argument(
                '-d',
                '--durations',
                type=int,
                metavar='N',
                default=None,
                help=f'Show the N slowest test durations (e.g., --durations {ANALYZE_DEFAULT_DURATIONS})',
            )
        add_analysis_opts()

        def add_shortcut_opts() -> None:
            shortcut_opts = parser.add_argument_group(
                'Shortcut options',
                description='Convenience shortcuts for common option combinations',
            )
            if self.builtin_marker is None:
                shortcut_opts.add_argument(
                    '-q',
                    '--quick',
                    action='store_true',
                    help='Exclude slow tests. Alias for: -m "not slow"',
                )
            if not self.always_analyze:
                shortcut_opts.add_argument(
                    '--analyze',
                    action='store_true',
                    help=(
                        f'Enable coverage and timing analysis. '
                        f'Alias for: --durations {ANALYZE_DEFAULT_DURATIONS} --coverage'
                    ),
                )
        add_shortcut_opts()

    def _analyze(self, args: Args) -> bool:
        return args.analyze or self.always_analyze

    def _coverage(self, args: Args) -> bool:
        return args.coverage or self.always_coverage or self._analyze(args)

    def _durations(self, args: Args) -> int | None:
        if args.durations is not None:
            return args.durations
        return ANALYZE_DEFAULT_DURATIONS if self._analyze(args) else None

    def _marker(self, args: Args) -> str | None:
        return _combine_markers(args.marker, self.builtin_marker, 'not slow' if args.quick else None)

    def build_commands(self, args: Args) -> list[list[str]]:
        """
        Build the argv of each step of the command, in execution order.

        :param args: parsed command line
        :return: list of ``uv`` command lines
        """
        pytest_cmd: list[str] = ['pytest']
        if marker := self._marker(args):
            pytest_cmd.extend(['-m', marker])
        if (durations := self._durations(args)) is not None:
            pytest_cmd.append(f'--durations={durations}')
        if args.verbose:
            pytest_cmd.append(f'-{"v" * args.verbose}')
        if args.args:
            pytest_cmd.extend(shlex.split(args.args))
        pytest_cmd.extend(args.paths or self.default_paths)

        if not self._coverage(args):
            return [_uv_test(*pytest_cmd)]

        return [
            _uv_test('coverage', 'run', '-m', *pytest_cmd),
            _uv_test('coverage', 'html'),
            _uv_test('coverage', 'report'),
        ]

    def _print_header(self, args: Args) -> None:
        printf('🖥  Running tests...', fg='bright_cyan')
        if self._coverage(args):
            printf('📊 coverage analysis enabled', fg='bright_green', indent=3)
        if self._durations(args) is not None:
            printf('🕗 timing analysis enabled', fg='bright_green', indent=3)
        if 'not slow' in (self._marker(args) or ''):
            printf('🚀 skipping slow tests', fg='bright_magenta', indent=3)

    def run(self, args: Args) -> None:
        self._print_header(args)

        if self._coverage(args):
            for stale in (Path.cwd() / '.coverage', *Path.cwd().glob('.coverage.*')):
                if stale.is_file():
                    stale.unlink()

        returncode = 0
        for cmd in self.build_commands(args):
            returncode = shell_command(cmd, check=False).returncode
            if returncode != 0:
                break

        sys.exit(returncode)


class TestCommand(_PytestCommand):
    """
    Run the unit tests that are not marked slow (fast feedback)
    """
    name: ClassVar[str] = 'test'

    default_paths:  ClassVar[tuple[str, ...]] = ('tests/unit',)
    builtin_marker: ClassVar[str | None]      = 'not slow'


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

    always_coverage: ClassVar[bool] = True


class TestAnalyzeCommand(_PytestCommand):
    """
    Run the full test suite with coverage and timing analysis
    """
    name: ClassVar[str] = 'test-analyze'

    always_analyze: ClassVar[bool] = True
