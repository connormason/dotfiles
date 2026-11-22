"""
Unit tests for the run.py ``config`` command and the TOOL_CONFIGS registry behind it
"""
from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest

import cli.commands  # noqa: F401  (importing registers every command)
from cli.commands import tool_config as tool_config_commands
from cli.infra.command import get_commands
from cli.infra.config import DOTFILES_DIR
from cli.infra.config import RENDER_DIR
from cli.infra.config import STOW_DIR
from cli.infra.config import TOOL_CONFIGS
from cli.infra.config import ExitCode
from cli.infra.main import Args
from cli.infra.main import build_parser
from cli.utils.styling import unstyle

if TYPE_CHECKING:
    import argparse
    from pathlib import Path

Call = tuple[list[str], dict[str, object]]


# ==================================================================================================
# Helpers
# ==================================================================================================


def _parse(*argv: str) -> argparse.Namespace:
    """
    Parse a run.py command line into the typed root namespace
    """
    return build_parser().parse_args(list(argv), namespace=Args())


# ==================================================================================================
# Unit tests
# ==================================================================================================


class TestToolConfigsRegistry:
    """
    Tests for the TOOL_CONFIGS tool-to-file registry
    """
    @pytest.mark.parametrize('tool', sorted(TOOL_CONFIGS))
    def test_every_path_exists(self, tool: str) -> None:
        """
        Test that each registered file exists, so the registry cannot drift from the repository
        """
        missing = [str(path) for path in TOOL_CONFIGS[tool] if not path.is_file()]
        assert not missing, f'{tool}: registered files do not exist: {missing}'

    @pytest.mark.parametrize('tool', sorted(TOOL_CONFIGS))
    def test_paths_are_unique_and_non_empty(self, tool: str) -> None:
        """
        Test that each tool lists at least one file and never lists the same file twice
        """
        paths = TOOL_CONFIGS[tool]
        assert paths
        assert len(paths) == len(set(paths))

    @pytest.mark.parametrize(
        ('tool', 'primary'),
        [
            ('tmux',            STOW_DIR   / 'tmux' / '.config' / 'tmux' / 'tmux.conf'),
            ('zsh',             STOW_DIR   / 'shell' / '.zshrc'),
            ('vscode-settings', RENDER_DIR / 'vscode.json'),
            ('claude-settings', RENDER_DIR / 'claude.json'),
        ],
    )
    def test_primary_file(self, tool: str, primary: Path) -> None:
        """
        Test that the first registered file is the one opened by default, and that rendered settings files
        point at their render fragment instead of the (overwritten) target
        """
        assert TOOL_CONFIGS[tool][0] == primary


class TestConfigCommand:
    """
    Tests for the config command
    """
    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Record editor launches instead of running them, and start from an editor-free environment
        """
        self.calls:      list[Call] = []
        self.returncode: int        = 0

        def fake_shell_command(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            self.calls.append((cmd, kwargs))
            return subprocess.CompletedProcess(cmd, self.returncode, stdout='', stderr='')

        monkeypatch.delenv('VISUAL', raising=False)
        monkeypatch.delenv('EDITOR', raising=False)
        monkeypatch.setattr(tool_config_commands, 'shell_command', fake_shell_command)

    def _run(self, *argv: str) -> int:
        """
        Run a command and return its exit code (0 when it returns normally)
        """
        try:
            get_commands()[argv[0]](_parse(*argv))
        except SystemExit as e:
            return int(e.code or 0)
        return 0

    def test_is_registered_in_utilities_group(self) -> None:
        """
        Test that the command is registered under the Utilities group
        """
        assert get_commands()['config'].group == 'Utilities'

    def test_opens_primary_file_only_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that a multi-file tool opens only its first file, and that the editor's exit code is propagated
        """
        monkeypatch.setenv('EDITOR', 'myeditor')
        self.returncode = 3

        assert self._run('config', 'yazi') == 3
        assert self.calls == [(['myeditor', str(TOOL_CONFIGS['yazi'][0])], {'check': False})]

    def test_all_opens_every_file(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that --all hands every registered file of the tool to the editor, in registry order
        """
        monkeypatch.setenv('EDITOR', 'myeditor')

        assert self._run('config', 'yazi', '--all') == 0
        assert self.calls == [(['myeditor', *map(str, TOOL_CONFIGS['yazi'])], {'check': False})]

    @pytest.mark.parametrize(
        ('visual', 'editor', 'expected'),
        [
            ('code --wait', 'nano',  ['code', '--wait']),
            (None,          'nano',  ['nano']),
            (None,          None,    ['vi']),
            ('',            'nano',  ['nano']),
        ],
    )
    def test_editor_resolution(
        self,
        monkeypatch: pytest.MonkeyPatch,
        visual: str | None,
        editor: str | None,
        expected: list[str],
    ) -> None:
        """
        Test that $VISUAL wins over $EDITOR, vi is the fallback, and a multi-word editor command is split
        """
        if visual is not None:
            monkeypatch.setenv('VISUAL', visual)
        if editor is not None:
            monkeypatch.setenv('EDITOR', editor)

        assert self._run('config', 'starship') == 0
        assert self.calls == [([*expected, str(TOOL_CONFIGS['starship'][0])], {'check': False})]

    def test_missing_editor_is_a_setup_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that an editor command that cannot be executed exits with SETUP_ERROR and names the editor
        """
        def missing_editor(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            raise FileNotFoundError(cmd[0])

        monkeypatch.setenv('EDITOR', 'no-such-editor')
        monkeypatch.setattr(tool_config_commands, 'shell_command', missing_editor)

        assert self._run('config', 'starship') == ExitCode.SETUP_ERROR
        assert 'no-such-editor' in unstyle(capsys.readouterr().out)

    def test_print_path_does_not_launch_an_editor(self, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that --print-path emits one bare path per line (primary only without --all) and runs nothing
        """
        assert self._run('config', 'tmux', '--print-path') == 0
        assert capsys.readouterr().out.splitlines() == [str(TOOL_CONFIGS['tmux'][0])]

        assert self._run('config', 'tmux', '--print-path', '--all') == 0
        assert capsys.readouterr().out.splitlines() == [str(path) for path in TOOL_CONFIGS['tmux']]
        assert self.calls == []

    def test_list_shows_every_tool_without_launching(self, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that --list names every registered tool with its primary file (repo-relative) and runs nothing
        """
        assert self._run('config', '--list') == 0

        lines = unstyle(capsys.readouterr().out).splitlines()
        assert len(lines) == len(TOOL_CONFIGS)
        for tool, paths in TOOL_CONFIGS.items():
            line = next(line for line in lines if line.split()[0] == tool)
            assert str(paths[0].relative_to(DOTFILES_DIR)) in line
        assert self.calls == []

    def test_list_marks_tools_with_more_files(self, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that a tool with several files advertises the extras, and a single-file tool does not
        """
        assert self._run('config', '--list') == 0

        lines = {line.split()[0]: line for line in unstyle(capsys.readouterr().out).splitlines()}
        assert f'+{len(TOOL_CONFIGS["yazi"]) - 1} more' in lines['yazi']
        assert 'more' not in lines['starship']

    def test_unknown_tool_suggests_close_matches(self, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that a misspelled tool exits 1, suggests the near match, and launches nothing
        """
        assert self._run('config', 'tmx') == ExitCode.COMMAND_FAILED

        out = unstyle(capsys.readouterr().out)
        assert "Unknown tool 'tmx'" in out
        assert 'tmux'               in out
        assert self.calls == []

    def test_unknown_tool_without_match_lists_valid_tools(self, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that an unrecognizable tool name falls back to listing every valid tool
        """
        assert self._run('config', 'zzzzzzzz') == ExitCode.COMMAND_FAILED

        out = unstyle(capsys.readouterr().out)
        assert all(tool in out for tool in TOOL_CONFIGS)

    def test_no_tool_exits_with_the_tool_list(self, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that omitting the tool is an error that shows what can be opened
        """
        assert self._run('config') == ExitCode.COMMAND_FAILED

        out = unstyle(capsys.readouterr().out)
        assert 'tmux' in out
        assert self.calls == []
