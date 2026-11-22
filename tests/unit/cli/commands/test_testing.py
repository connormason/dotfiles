"""
Unit tests for the test-suite commands (test, test-full, test-unit, test-integration, test-cov)
"""
from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING
from typing import cast

import pytest

import cli.commands  # noqa: F401  (registers every command)
from cli.commands import testing as testing_commands
from cli.infra.command import REGISTERED_COMMANDS
from cli.infra.main import Args
from cli.infra.main import build_parser

if TYPE_CHECKING:
    import argparse

PYTEST_PREFIX = ['run', '--group', 'test', 'pytest']
COVERAGE_PREFIX = ['run', '--group', 'test', 'coverage']


def _parse(*argv: str) -> argparse.Namespace:
    """
    Parse a run.py command line into the typed root namespace
    """
    return build_parser().parse_args(list(argv), namespace=Args())


def _uv_args(cmd: list[str]) -> list[str]:
    """
    Strip the uv wrapper (and any ``env PATH=...`` prefix) from a command, leaving the arguments after ``uv``
    """
    start = next(i for i, part in enumerate(cmd) if part == 'run')
    return cmd[start:]


def _build(*argv: str) -> list[list[str]]:
    """
    Build the uv argument lists (wrapper stripped) a test command would run for the given command line
    """
    args = _parse(*argv)
    command = cast('testing_commands._PytestCommand', REGISTERED_COMMANDS[argv[0]])
    return [_uv_args(cmd) for cmd in command.build_commands(args.paths)]


class TestPytestCommands:
    """
    Tests for the pytest-backed commands
    """
    @pytest.mark.parametrize(
        ('argv', 'expected'),
        [
            (['test'],             [*PYTEST_PREFIX, '-m', 'not slow', 'tests/unit']),
            (['test-full'],        [*PYTEST_PREFIX, 'tests']),
            (['test-unit'],        [*PYTEST_PREFIX, 'tests/unit']),
            (['test-integration'], [*PYTEST_PREFIX, 'tests/integration']),
        ],
    )
    def test_default_invocation(self, argv: list[str], expected: list[str]) -> None:
        """
        Test that each command runs pytest against its default target with its marker options
        """
        assert _build(*argv) == [expected]

    @pytest.mark.parametrize(
        ('argv', 'expected'),
        [
            (['test', 'tests/unit/cli'],             [*PYTEST_PREFIX, '-m', 'not slow', 'tests/unit/cli']),
            (['test-full', 'tests/unit/cli', 'x'],   [*PYTEST_PREFIX, 'tests/unit/cli', 'x']),
            (['test-unit', 'tests/unit/stow'],       [*PYTEST_PREFIX, 'tests/unit/stow']),
            (['test-integration', 'tests/integration/test_home.py'],
                                                     [*PYTEST_PREFIX, 'tests/integration/test_home.py']),
        ],
    )
    def test_paths_replace_default_target(self, argv: list[str], expected: list[str]) -> None:
        """
        Test that positional paths replace the default target but keep the command's marker options
        """
        assert _build(*argv) == [expected]

    def test_cov_runs_coverage_html_then_report(self) -> None:
        """
        Test that test-cov runs the suite under coverage, then writes the HTML report and the terminal summary
        """
        assert _build('test-cov') == [
            [*COVERAGE_PREFIX, 'run', '-m', 'pytest', 'tests'],
            [*COVERAGE_PREFIX, 'html'],
            [*COVERAGE_PREFIX, 'report'],
        ]

    def test_cov_paths_narrow_the_coverage_run_only(self) -> None:
        """
        Test that paths given to test-cov narrow the pytest step and leave the report steps unchanged
        """
        steps = _build('test-cov', 'tests/unit')
        assert steps[0] == [*COVERAGE_PREFIX, 'run', '-m', 'pytest', 'tests/unit']
        assert steps[1:] == [[*COVERAGE_PREFIX, 'html'], [*COVERAGE_PREFIX, 'report']]

    @pytest.mark.parametrize('name', ['test', 'test-full', 'test-unit', 'test-integration', 'test-cov'])
    def test_commands_belong_to_testing_group(self, name: str) -> None:
        """
        Test that every test command is registered under the Testing group
        """
        assert REGISTERED_COMMANDS[name].group == 'Testing'


class TestRun:
    """
    Tests for executing the commands and propagating the exit code
    """
    @pytest.fixture
    def shell(self, monkeypatch: pytest.MonkeyPatch) -> tuple[list[list[str]], list[int]]:
        """
        Patch shell_command to record each call's uv arguments; exit codes queued in the second item are consumed in
        order (default 0)
        """
        calls: list[list[str]] = []
        codes: list[int] = []

        def fake_shell_command(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append(_uv_args(cmd))
            return subprocess.CompletedProcess(cmd, codes.pop(0) if codes else 0, stdout='', stderr='')

        monkeypatch.setattr(testing_commands, 'shell_command', fake_shell_command)
        return calls, codes

    def test_exits_zero_when_every_step_passes(self, shell: tuple[list[list[str]], list[int]]) -> None:
        """
        Test that a passing run executes every step and exits with code zero
        """
        calls, _codes = shell
        with pytest.raises(SystemExit) as exc_info:
            REGISTERED_COMMANDS['test-cov'](_parse('test-cov'))
        assert exc_info.value.code == 0
        assert [step[3:5] for step in calls] == [['coverage', 'run'], ['coverage', 'html'], ['coverage', 'report']]

    def test_failing_step_exits_with_its_code_and_skips_the_rest(
        self, shell: tuple[list[list[str]], list[int]],
    ) -> None:
        """
        Test that a nonzero exit stops the sequence and is propagated as the process exit code
        """
        calls, codes = shell
        codes.append(3)
        with pytest.raises(SystemExit) as exc_info:
            REGISTERED_COMMANDS['test-cov'](_parse('test-cov'))
        assert exc_info.value.code == 3
        assert len(calls) == 1

    def test_pytest_failure_exit_code_propagates(self, shell: tuple[list[list[str]], list[int]]) -> None:
        """
        Test that the default test command exits with pytest's return code
        """
        calls, codes = shell
        codes.append(1)
        with pytest.raises(SystemExit) as exc_info:
            REGISTERED_COMMANDS['test'](_parse('test'))
        assert exc_info.value.code == 1
        assert calls == [[*PYTEST_PREFIX, '-m', 'not slow', 'tests/unit']]
