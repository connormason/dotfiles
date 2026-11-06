"""
Unit tests for the run.py docs-audit command
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import run

if TYPE_CHECKING:
    import argparse

Call = tuple[list[str], dict[str, object]]


def _parse(*argv: str) -> argparse.Namespace:
    """
    Parse a run.py command line into the typed root namespace
    """
    return run.build_parser().parse_args(list(argv), namespace=run.Args())


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


class TestDocsAudit:
    """
    Tests for the docs-audit command
    """
    @pytest.mark.parametrize(
        ('argv', 'expected_args'),
        [
            ([],                                   []),
            (['roles'],                            ['roles']),
            (['roles', 'playbooks'],               ['roles', 'playbooks']),
            (['--json'],                           ['--json']),
            (['--no-fail'],                        ['--no-fail']),
            (['roles', '--json', '--no-fail'],     ['roles', '--json', '--no-fail']),
        ],
    )
    def test_builds_engine_command(
        self,
        monkeypatch: pytest.MonkeyPatch,
        argv: list[str],
        expected_args: list[str],
    ) -> None:
        """
        Test that scopes and flags are forwarded to the docs_audit module, run from the repo root
        """
        calls = _record(monkeypatch)

        with pytest.raises(SystemExit):
            run.REGISTERED_COMMANDS['docs-audit'](_parse('docs-audit', *argv))

        assert len(calls) == 1
        cmd, kwargs = calls[0]
        assert cmd == [sys.executable, '-m', 'scripts.docs_audit', *expected_args]
        assert kwargs['cwd'] == run.DOTFILES_DIR
        assert kwargs['check'] is False

    @pytest.mark.parametrize('returncode', [0, 1, 2])
    def test_propagates_exit_code(self, monkeypatch: pytest.MonkeyPatch, returncode: int) -> None:
        """
        Test that the engine's exit code becomes the command's exit code
        """
        _record(monkeypatch, returncode=returncode)

        with pytest.raises(SystemExit) as exc_info:
            run.REGISTERED_COMMANDS['docs-audit'](_parse('docs-audit'))

        assert exc_info.value.code == returncode

    def test_prints_status_line_for_text_output(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that the text mode announces the audit before running it
        """
        _record(monkeypatch)

        with pytest.raises(SystemExit):
            run.REGISTERED_COMMANDS['docs-audit'](_parse('docs-audit'))

        assert 'Auditing README documentation' in capsys.readouterr().out

    def test_json_output_has_no_status_line(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that --json leaves stdout untouched so it stays a single JSON document
        """
        _record(monkeypatch)

        with pytest.raises(SystemExit):
            run.REGISTERED_COMMANDS['docs-audit'](_parse('docs-audit', '--json'))

        assert capsys.readouterr().out == ''

    def test_group_and_description(self) -> None:
        """
        Test that the command is grouped under Static Analysis with a docstring-derived description
        """
        command = run.REGISTERED_COMMANDS['docs-audit']

        assert command.group == 'Static Analysis'
        assert command.description is not None
        assert command.description.startswith('Audit per-directory README documentation')
