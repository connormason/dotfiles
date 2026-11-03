"""
Unit tests for the run.py prek hook commands (run-hooks, pre, prepare-hooks)
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import cast

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import run

Call = tuple[list[str], dict[str, object]]


def _parse(*argv: str) -> argparse.Namespace:
    """
    Parse a run.py command line into the typed root namespace
    """
    return run.build_parser().parse_args(list(argv), namespace=run.Args())


def _build(*argv: str) -> list[str]:
    """
    Build the ``prek run`` command line for a run-hooks style invocation
    """
    return run.RunHooksCommand.build_command(cast('run.RunHooksCommand.Args', _parse(*argv)))


def _option_strings(command: str) -> set[str]:
    """
    Get every option string a command's subparser accepts
    """
    action = next(a for a in run.build_parser()._actions if isinstance(a, argparse._SubParsersAction))
    return {opt for a in action.choices[command]._actions for opt in a.option_strings}


def _record(monkeypatch: pytest.MonkeyPatch, returncode: int = 0) -> list[Call]:
    """
    Patch shell_command to record each call (command and keyword args) and exit with ``returncode``
    """
    calls: list[Call] = []

    def fake_shell_command(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, returncode, stdout='', stderr='')

    monkeypatch.setattr(run, 'shell_command', fake_shell_command)
    return calls


class TestRunHooks:
    """
    Tests for the run-hooks command
    """
    @pytest.mark.parametrize(
        ('argv', 'expected'),
        [
            (['run-hooks'],                        ['prek', 'run']),
            (['run-hooks', 'mdformat', 'ruff'],    ['prek', 'run', 'mdformat', 'ruff']),
            (['run-hooks', '-a'],                  ['prek', 'run', '--all-files']),
            (['run-hooks', '-d', 'docs'],          ['prek', 'run', '--directory', 'docs']),
            (['run-hooks', '--last-commit'],       ['prek', 'run', '--last-commit']),
            (['run-hooks', '--stage', 'pre-push'], ['prek', 'run', '--stage', 'pre-push']),
            (
                ['run-hooks', '-s', 'main', '-o', 'HEAD'],
                ['prek', 'run', '--from-ref', 'main', '--to-ref', 'HEAD'],
            ),
            (
                ['run-hooks', '--skip', 'mypy', '--skip', 'ruff'],
                ['prek', 'run', '--skip', 'mypy', '--skip', 'ruff'],
            ),
            (
                ['run-hooks', '--show-diff-on-failure', '--fail-fast', '--dry-run', '-v'],
                ['prek', 'run', '--show-diff-on-failure', '--fail-fast', '--dry-run', '--verbose'],
            ),
        ],
    )
    def test_builds_prek_command(self, argv: list[str], expected: list[str]) -> None:
        """
        Test that each option maps to the matching prek run flag
        """
        assert _build(*argv) == expected

    def test_hooks_precede_the_greedy_files_option(self) -> None:
        """
        Test that hook names are placed before --files, which would otherwise swallow them as filenames
        """
        cmd = _build('run-hooks', 'mdformat', '--files', 'a.md', 'b.md')
        assert cmd == ['prek', 'run', 'mdformat', '--files', 'a.md', 'b.md']

    def test_streams_output_and_propagates_exit_code(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that prek runs with inherited stdio and its exit code becomes the command's
        """
        calls = _record(monkeypatch, returncode=3)
        with pytest.raises(SystemExit) as exc_info:
            run.get_commands()['run-hooks'](_parse('run-hooks', '-a'))

        assert exc_info.value.code == 3
        assert calls == [(['prek', 'run', '--all-files'], {'check': False})]

    def test_description(self) -> None:
        """
        Test the help description shown in the script help and Makefile
        """
        assert run.get_commands()['run-hooks'].description == 'Run prek hooks on modified or specified project files'


class TestPre:
    """
    Tests for the pre command (run-hooks pinned to all files)
    """
    def test_forces_all_files_and_forwards_filters(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that pre always passes --all-files while still honoring hook filters and skips
        """
        calls = _record(monkeypatch)
        with pytest.raises(SystemExit) as exc_info:
            run.get_commands()['pre'](_parse('pre', 'mdformat', '--skip', 'mypy'))

        assert exc_info.value.code == 0
        assert calls[0][0] == ['prek', 'run', 'mdformat', '--all-files', '--skip', 'mypy']

    def test_propagates_exit_code(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that a failing prek run exits with prek's return code
        """
        calls = _record(monkeypatch, returncode=3)
        with pytest.raises(SystemExit) as exc_info:
            run.get_commands()['pre'](_parse('pre'))

        assert exc_info.value.code == 3
        assert calls == [(['prek', 'run', '--all-files'], {'check': False})]

    def test_file_selection_options_are_not_offered(self) -> None:
        """
        Test that pre offers none of the file or ref selection options, which conflict with its forced --all-files
        """
        selection_options = {'--all-files', '--files', '--directory', '--from-ref', '--to-ref', '--last-commit'}

        assert selection_options <= _option_strings('run-hooks')
        assert not selection_options & _option_strings('pre')

    def test_description_is_unchanged(self) -> None:
        """
        Test that the pre description (and therefore its Makefile line) is unchanged
        """
        assert run.get_commands()['pre'].description == 'Run prek (pre-commit) hooks on all project files'


class TestPrepareHooks:
    """
    Tests for the prepare-hooks command
    """
    def test_builds_prek_command(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that hook filters, --skip, and --verbose are forwarded to prek prepare-hooks
        """
        calls = _record(monkeypatch)
        with pytest.raises(SystemExit) as exc_info:
            run.get_commands()['prepare-hooks'](_parse('prepare-hooks', 'ruff', '--skip', 'mypy', '-v'))

        assert exc_info.value.code == 0
        expected = ['prek', 'prepare-hooks', 'ruff', '--skip', 'mypy', '--verbose']
        assert calls == [(expected, {'indent': 3, 'check': False})]

    def test_propagates_exit_code(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that a failing prepare exits with prek's return code
        """
        _record(monkeypatch, returncode=2)
        with pytest.raises(SystemExit) as exc_info:
            run.get_commands()['prepare-hooks'](_parse('prepare-hooks'))
        assert exc_info.value.code == 2
