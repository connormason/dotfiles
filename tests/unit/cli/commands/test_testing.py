"""
Unit tests for the test-suite commands (test, test-full, test-unit, test-integration, test-cov, test-analyze)
"""
from __future__ import annotations

import argparse
import subprocess
from typing import TYPE_CHECKING
from typing import cast

import pytest

import cli.commands  # noqa: F401  (importing registers every command)
from cli.commands import testing as testing_commands
from cli.infra.command import REGISTERED_COMMANDS
from cli.infra.main import Args
from cli.infra.main import build_parser

if TYPE_CHECKING:
    from pathlib import Path

PYTEST_PREFIX   = ['run', '--group', 'test', 'pytest']
COVERAGE_PREFIX = ['run', '--group', 'test', 'coverage']
COVERAGE_STEPS  = [[*COVERAGE_PREFIX, 'html'], [*COVERAGE_PREFIX, 'report']]
TEST_COMMANDS   = ['test', 'test-full', 'test-unit', 'test-integration', 'test-cov', 'test-analyze']


# ==================================================================================================
# Helpers
# ==================================================================================================


def _parse(*argv: str) -> argparse.Namespace:
    """
    Parse a run.py command line into the typed root namespace
    """
    return build_parser().parse_args(list(argv), namespace=Args())


def _option_strings(command: str) -> set[str]:
    """
    Get every option string a command's subparser accepts
    """
    action = next(a for a in build_parser()._actions if isinstance(a, argparse._SubParsersAction))
    return {opt for a in action.choices[command]._actions for opt in a.option_strings}


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
    command = cast('testing_commands._PytestCommand', REGISTERED_COMMANDS[argv[0]])
    args    = cast('testing_commands._PytestCommand.Args', _parse(*argv))
    return [_uv_args(cmd) for cmd in command.build_commands(args)]


# ==================================================================================================
# Unit tests
# ==================================================================================================


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
        Test that each command runs pytest against its default target with its built-in marker
        """
        assert _build(*argv) == [expected]

    @pytest.mark.parametrize(
        ('argv', 'expected'),
        [
            (
                ['test', 'tests/unit/cli'],
                [*PYTEST_PREFIX, '-m', 'not slow', 'tests/unit/cli'],
            ),
            (
                ['test-full', 'tests/unit/cli', 'x'],
                [*PYTEST_PREFIX, 'tests/unit/cli', 'x'],
            ),
            (
                ['test-unit', 'tests/unit/stow'],
                [*PYTEST_PREFIX, 'tests/unit/stow'],
            ),
            (
                ['test-integration', 'tests/integration/test_home.py'],
                [*PYTEST_PREFIX, 'tests/integration/test_home.py'],
            ),
        ],
    )
    def test_paths_replace_default_target(self, argv: list[str], expected: list[str]) -> None:
        """
        Test that positional paths replace the default target but keep the command's built-in marker
        """
        assert _build(*argv) == [expected]

    @pytest.mark.parametrize('name', TEST_COMMANDS)
    def test_commands_belong_to_testing_group(self, name: str) -> None:
        """
        Test that every test command is registered under the Testing group
        """
        assert REGISTERED_COMMANDS[name].group == 'Testing'


class TestMarkerOptions:
    """
    Tests for --marker and --quick
    """
    def test_marker_applies_to_command_without_builtin_marker(self) -> None:
        """
        Test that --marker is passed to pytest as-is when the command has no marker of its own
        """
        assert _build('test-full', '-m', 'integration') == [[*PYTEST_PREFIX, '-m', 'integration', 'tests']]

    def test_marker_is_anded_with_builtin_marker(self) -> None:
        """
        Test that --marker narrows the command's own marker instead of replacing it
        """
        assert _build('test', '--marker', 'timing') == [
            [*PYTEST_PREFIX, '-m', '(timing) and (not slow)', 'tests/unit'],
        ]

    @pytest.mark.parametrize('name', ['test-full', 'test-unit', 'test-integration'])
    def test_quick_excludes_slow_tests(self, name: str) -> None:
        """
        Test that --quick is shorthand for -m "not slow" on commands that run slow tests by default
        """
        assert _build(name, '-q')[0][4:6] == ['-m', 'not slow']
        assert _build(name, '--quick')[0][4:6] == ['-m', 'not slow']

    def test_quick_is_anded_with_marker(self) -> None:
        """
        Test that --quick combines with an explicit --marker
        """
        assert _build('test-full', '-q', '-m', 'integration')[0][4:6] == ['-m', '(integration) and (not slow)']

    def test_quick_not_offered_where_slow_tests_already_excluded(self) -> None:
        """
        Test that the test command has no --quick option because it already excludes slow tests
        """
        assert '--quick' not in _option_strings('test')
        assert '--quick' in _option_strings('test-full')


class TestPassthroughOptions:
    """
    Tests for --verbose, --durations, and --args
    """
    @pytest.mark.parametrize(
        ('flags', 'expected'),
        [
            (['-v'],         ['-v']),
            (['-vv'],        ['-vv']),
            (['-v', '-v'],   ['-vv']),
            (['-d', '5'],    ['--durations=5']),
            (['--durations', '0'], ['--durations=0']),
        ],
    )
    def test_verbosity_and_durations(self, flags: list[str], expected: list[str]) -> None:
        """
        Test that --verbose counts into -v/-vv and --durations becomes --durations=N
        """
        assert _build('test-full', *flags) == [[*PYTEST_PREFIX, *expected, 'tests']]

    def test_args_are_split_like_a_shell_and_precede_paths(self) -> None:
        """
        Test that --args is split with shell quoting rules and placed before the test paths
        """
        assert _build('test-full', '--args', "-x -k 'foo and bar'", 'tests/unit') == [
            [*PYTEST_PREFIX, '-x', '-k', 'foo and bar', 'tests/unit'],
        ]

    def test_option_order_is_marker_durations_verbose_args(self) -> None:
        """
        Test that pytest flags are composed in a stable order
        """
        assert _build('test-full', '--args=-x', '-vv', '-d', '3', '-m', 'integration') == [
            [*PYTEST_PREFIX, '-m', 'integration', '--durations=3', '-vv', '-x', 'tests'],
        ]


class TestCoverageOptions:
    """
    Tests for --coverage, --analyze, and the coverage presets
    """
    def test_coverage_wraps_pytest_and_reports(self) -> None:
        """
        Test that --coverage runs pytest under coverage, then writes the HTML report and the terminal summary
        """
        assert _build('test-full', '--cov') == [
            [*COVERAGE_PREFIX, 'run', '-m', 'pytest', 'tests'],
            *COVERAGE_STEPS,
        ]

    def test_coverage_keeps_other_options_on_the_pytest_step(self) -> None:
        """
        Test that markers, flags, and paths all land on the coverage-wrapped pytest step
        """
        steps = _build('test', '-c', '-d', '5', '-v', 'tests/unit/cli')
        assert steps[0] == [
            *COVERAGE_PREFIX, 'run', '-m', 'pytest', '-m', 'not slow', '--durations=5', '-v', 'tests/unit/cli',
        ]
        assert steps[1:] == COVERAGE_STEPS

    def test_analyze_enables_coverage_and_default_durations(self) -> None:
        """
        Test that --analyze is shorthand for --coverage plus the default --durations
        """
        durations = f'--durations={testing_commands.ANALYZE_DEFAULT_DURATIONS}'
        assert _build('test-full', '--analyze') == [
            [*COVERAGE_PREFIX, 'run', '-m', 'pytest', durations, 'tests'],
            *COVERAGE_STEPS,
        ]

    def test_analyze_respects_explicit_durations(self) -> None:
        """
        Test that an explicit --durations overrides the default one implied by --analyze
        """
        assert _build('test-full', '--analyze', '-d', '3')[0][-2] == '--durations=3'

    def test_test_cov_is_full_suite_with_coverage(self) -> None:
        """
        Test that test-cov is the full suite under coverage
        """
        assert _build('test-cov') == _build('test-full', '--coverage')

    def test_test_analyze_is_full_suite_with_analysis(self) -> None:
        """
        Test that test-analyze is the full suite with coverage and timing analysis
        """
        assert _build('test-analyze') == _build('test-full', '--analyze')

    def test_test_cov_paths_narrow_the_coverage_run_only(self) -> None:
        """
        Test that paths given to test-cov narrow the pytest step and leave the report steps unchanged
        """
        steps = _build('test-cov', 'tests/unit')
        assert steps[0]  == [*COVERAGE_PREFIX, 'run', '-m', 'pytest', 'tests/unit']
        assert steps[1:] == COVERAGE_STEPS

    def test_test_analyze_does_not_offer_analyze_option(self) -> None:
        """
        Test that test-analyze omits the --analyze option it already implies
        """
        assert '--analyze' not in _option_strings('test-analyze')
        assert '--analyze' in _option_strings('test-cov')


class TestRun:
    """
    Tests for executing the commands and propagating the exit code
    """
    @pytest.fixture(autouse=True)
    def _isolated_cwd(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Run in an empty directory so coverage-data cleanup never touches the real checkout
        """
        monkeypatch.chdir(tmp_path)

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

    def test_coverage_run_clears_stale_coverage_data(
        self, shell: tuple[list[list[str]], list[int]], tmp_path: Path,
    ) -> None:
        """
        Test that a coverage run deletes leftover coverage data files so results never mix with an earlier run
        """
        stale = [tmp_path / '.coverage', tmp_path / '.coverage.host.1234']
        keep = tmp_path / 'coverage.txt'
        for path in (*stale, keep):
            path.write_text('x', encoding='utf-8')

        with pytest.raises(SystemExit):
            REGISTERED_COMMANDS['test-full'](_parse('test-full', '--cov'))

        assert not any(path.exists() for path in stale)
        assert keep.exists()

    def test_run_without_coverage_leaves_coverage_data_alone(
        self, shell: tuple[list[list[str]], list[int]], tmp_path: Path,
    ) -> None:
        """
        Test that a plain run does not touch existing coverage data
        """
        data = tmp_path / '.coverage'
        data.write_text('x', encoding='utf-8')

        with pytest.raises(SystemExit):
            REGISTERED_COMMANDS['test-full'](_parse('test-full'))

        assert data.exists()

    def test_banner_lists_active_modifiers(
        self, shell: tuple[list[list[str]], list[int]], capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that the output names the active coverage, timing, and slow-test-skipping modifiers
        """
        with pytest.raises(SystemExit):
            REGISTERED_COMMANDS['test-full'](_parse('test-full', '--analyze', '--quick'))

        out = capsys.readouterr().out
        assert 'coverage' in out
        assert 'timing' in out
        assert 'skipping slow tests' in out

    def test_banner_omits_modifiers_for_plain_run(
        self, shell: tuple[list[list[str]], list[int]], capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that a plain run with no slow-test filter prints no modifier lines
        """
        with pytest.raises(SystemExit):
            REGISTERED_COMMANDS['test-full'](_parse('test-full'))

        out = capsys.readouterr().out
        assert 'coverage' not in out
        assert 'timing' not in out
        assert 'skipping slow tests' not in out
