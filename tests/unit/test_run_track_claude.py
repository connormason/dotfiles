"""
Unit tests for the run.py track-claude command
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import run


@pytest.fixture
def claude(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Path, Path]:
    """
    Point run.py at a throwaway ~/.claude and stow package; returns (config_dir, stow_dir)
    """
    config = tmp_path / 'home' / '.claude'
    stow   = tmp_path / 'repo' / 'stow' / 'claude' / '.claude'
    config.mkdir(parents=True)
    stow.mkdir(parents=True)
    monkeypatch.setattr(run, 'CLAUDE_CONFIG_DIR', config)
    monkeypatch.setattr(run, 'CLAUDE_STOW_DIR',   stow)
    return config, stow


def _write(path: Path, text: str = 'x') -> Path:
    """
    Write a file, creating parent directories
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


class TestFindUntrackedClaudeFiles:
    """
    Tests for detecting local Claude files that are not yet in the repo
    """
    def test_finds_real_files_in_tracked_subdirs(self, claude: tuple[Path, Path]) -> None:
        """
        Test that regular files under a tracked subdirectory are reported, sorted
        """
        config, _ = claude
        b = _write(config / 'skills' / 'foo' / 'SKILL.md')
        a = _write(config / 'agents' / 'new.md')
        r = _write(config / 'rules' / 'mine.md')
        assert run.find_untracked_claude_files() == sorted([a, b, r])

    def test_ignores_symlinks_ds_store_and_untracked_subdirs(self, claude: tuple[Path, Path]) -> None:
        """
        Test that stowed symlinks, .DS_Store, and files outside the tracked subdirectories are not reported
        """
        config, stow = claude
        target = _write(stow / 'agents' / 'tracked.md')
        (config / 'agents').mkdir()
        (config / 'agents' / 'tracked.md').symlink_to(target)
        _write(config / 'agents' / '.DS_Store')
        _write(config / 'projects' / 'session.jsonl')
        _write(config / 'plugins' / 'cache.json')

        assert run.find_untracked_claude_files() == []

    def test_does_not_descend_into_symlinked_directories(self, claude: tuple[Path, Path]) -> None:
        """
        Test that repo files reached through a symlinked directory are not mistaken for local files
        """
        config, stow = claude
        _write(stow / 'skills' / 'linked' / 'SKILL.md')
        (config / 'skills').mkdir()
        (config / 'skills' / 'linked').symlink_to(stow / 'skills' / 'linked')

        assert run.find_untracked_claude_files() == []

    def test_skips_a_tracked_subdir_that_is_itself_a_symlink(self, claude: tuple[Path, Path]) -> None:
        """
        Test that a symlinked tracked subdirectory is skipped (ingesting would move repo files onto themselves)
        """
        config, stow = claude
        _write(stow / 'hooks' / 'guard.sh')
        (config / 'hooks').symlink_to(stow / 'hooks')

        assert run.find_untracked_claude_files() == []


class TestTrackClaudeCommand:
    """
    Tests for the track-claude command flow
    """
    @staticmethod
    def _run(dry_run: bool = False) -> None:
        """
        Invoke track-claude through the registry
        """
        run.get_commands()['track-claude'](argparse.Namespace(dry_run=dry_run))

    @staticmethod
    def _record_shell(monkeypatch: pytest.MonkeyPatch, returncode: int = 0) -> list[list[str]]:
        """
        Patch shell_command to record commands; a nonzero code raises like check=True would
        """
        calls: list[list[str]] = []

        def fake_shell_command(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append(cmd)
            if returncode:
                raise run.ShellCommandError(returncode, run.shlex.join(cmd))
            return subprocess.CompletedProcess(cmd, 0, stdout='', stderr='')

        monkeypatch.setattr(run, 'shell_command', fake_shell_command)
        return calls

    def test_registered_in_dotfiles_group(self) -> None:
        """
        Test that track-claude is a Dotfiles command
        """
        assert 'track-claude' in run.get_commands(by_group=True)['Dotfiles']

    def test_nothing_to_track(
        self,
        claude: tuple[Path, Path],
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that an empty result reports success without prompting or restowing
        """
        calls = self._record_shell(monkeypatch)
        monkeypatch.setattr(run, 'confirm', lambda *args, **kwargs: pytest.fail('must not prompt'))

        self._run()
        assert 'Nothing to track' in run.unstyle(capsys.readouterr().out)
        assert calls == []

    def test_dry_run_moves_nothing(self, claude: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that --dry-run neither prompts, moves files, nor restows
        """
        config, stow = claude
        src = _write(config / 'agents' / 'new.md')
        calls = self._record_shell(monkeypatch)
        monkeypatch.setattr(run, 'confirm', lambda *args, **kwargs: pytest.fail('must not prompt'))

        self._run(dry_run=True)
        assert src.exists()
        assert not (stow / 'agents' / 'new.md').exists()
        assert calls == []

    def test_declined_confirmation_leaves_files_in_place(
        self,
        claude: tuple[Path, Path],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Test that answering no cancels without moving or restowing
        """
        config, stow = claude
        src = _write(config / 'agents' / 'new.md')
        calls = self._record_shell(monkeypatch)
        monkeypatch.setattr(run, 'confirm', lambda *args, **kwargs: False)

        self._run()
        assert src.exists()
        assert not (stow / 'agents' / 'new.md').exists()
        assert calls == []

    def test_conflicting_destination_is_skipped(
        self,
        claude: tuple[Path, Path],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Test that a file whose repo counterpart already exists is left alone and never overwritten
        """
        config, stow = claude
        local = _write(config / 'agents' / 'dup.md', 'local')
        repo  = _write(stow / 'agents' / 'dup.md', 'repo')
        self._record_shell(monkeypatch)
        monkeypatch.setattr(run, 'confirm', lambda *args, **kwargs: pytest.fail('nothing movable, must not prompt'))

        self._run()
        assert local.read_text(encoding='utf-8') == 'local'
        assert repo.read_text(encoding='utf-8')  == 'repo'

    def test_confirmed_files_move_into_the_repo_and_claude_is_restowed(
        self,
        claude: tuple[Path, Path],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Test that confirmed files move (creating parent dirs) and the claude package is restowed with stow.sh
        """
        config, stow = claude
        _write(config / 'skills' / 'foo' / 'SKILL.md', 'skill')
        calls = self._record_shell(monkeypatch)
        monkeypatch.setattr(run, 'confirm', lambda *args, **kwargs: True)

        self._run()
        assert not (config / 'skills' / 'foo' / 'SKILL.md').exists()
        assert (stow / 'skills' / 'foo' / 'SKILL.md').read_text(encoding='utf-8') == 'skill'
        assert calls == [['bash', str(run.STOW_SCRIPT), 'claude']]

    def test_failed_restow_exits_command_failed(
        self,
        claude: tuple[Path, Path],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Test that a failing restow exits 1 after the files were already moved
        """
        config, stow = claude
        _write(config / 'agents' / 'new.md')
        self._record_shell(monkeypatch, returncode=1)
        monkeypatch.setattr(run, 'confirm', lambda *args, **kwargs: True)

        with pytest.raises(SystemExit) as exc_info:
            self._run()
        assert exc_info.value.code == run.ExitCode.COMMAND_FAILED
        assert (stow / 'agents' / 'new.md').exists()
