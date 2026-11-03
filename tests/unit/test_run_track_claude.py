"""
Unit tests for the run.py track-claude command
"""
from __future__ import annotations

import argparse
import shutil
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

    def test_skips_gitignored_backups_and_bytecode(self, claude: tuple[Path, Path]) -> None:
        """
        Test that .backups and __pycache__ directories and stray .pyc files are not reported next to real files
        """
        config, _ = claude
        real = _write(config / 'skills' / 'foo' / 'SKILL.md')

        _write(config / 'skills' / 'foo' / '.backups' / 'SKILL.md.1.bak')
        _write(config / 'skills' / 'foo' / '.backups' / 'nested' / 'deep.md.2.bak')
        _write(config / 'hooks' / '__pycache__' / 'y.cpython-312.pyc')
        _write(config / 'hooks' / 'z.pyc')

        assert run.find_untracked_claude_files() == [real]

    @pytest.mark.skipif(not shutil.which('git'), reason='Git not available')
    @pytest.mark.parametrize(
        'relpath',
        [
            'stow/claude/.claude/skills/x/.backups/y.md.1.bak',
            'stow/claude/.claude/hooks/__pycache__/z.cpython-312.pyc',
            'stow/claude/.claude/hooks/z.pyc',
        ],
    )
    def test_ignored_junk_is_gitignored(self, relpath: str) -> None:
        """
        Test that each kind of junk track-claude skips is also ignored by the repo's .gitignore
        """
        result = subprocess.run(['git', 'check-ignore', '-q', relpath], cwd=run.DOTFILES_DIR, check=False)
        assert result.returncode == 0

    @pytest.mark.skipif(not shutil.which('git'), reason='Git not available')
    @pytest.mark.parametrize('dirname', sorted(run.CLAUDE_IGNORE_DIRS))
    def test_every_ignored_directory_name_is_gitignored(self, dirname: str) -> None:
        """
        Test that a directory name in CLAUDE_IGNORE_DIRS is covered by .gitignore, so the two cannot drift apart
        """
        relpath = f'stow/claude/.claude/skills/x/{dirname}/y.md.1.bak'
        result = subprocess.run(['git', 'check-ignore', '-q', relpath], cwd=run.DOTFILES_DIR, check=False)
        assert result.returncode == 0


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

    @staticmethod
    def _fake_confirm(monkeypatch: pytest.MonkeyPatch, answer: bool = True) -> list[str]:
        """
        Patch confirm to record each prompt and answer it
        """
        prompts: list[str] = []

        def fake_confirm(prompt_text: str, **kwargs: object) -> bool:
            prompts.append(prompt_text)
            return answer

        monkeypatch.setattr(run, 'confirm', fake_confirm)
        return prompts

    @staticmethod
    def _stub_preflight(
        monkeypatch: pytest.MonkeyPatch,
        returncode: int = 0,
        stdout: str = '',
        stderr: str = '',
    ) -> list[list[str]]:
        """
        Patch _capture (the stow preflight) to record commands and return the given result
        """
        calls: list[list[str]] = []

        def fake_capture(cmd: list[str]) -> subprocess.CompletedProcess[str]:
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr=stderr)

        monkeypatch.setattr(run, '_capture', fake_capture)
        return calls

    @pytest.fixture(autouse=True)
    def preflight_calls(self, monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
        """
        Default the stow preflight to success so no test ever shells out to the real stow.sh
        """
        return self._stub_preflight(monkeypatch)

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

    def test_dangling_symlink_destination_is_a_conflict(
        self,
        claude: tuple[Path, Path],
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that a dangling symlink at the repo destination counts as occupied and is never replaced
        """
        config, stow = claude
        local = _write(config / 'agents' / 'new.md', 'local')

        dst = stow / 'agents' / 'new.md'
        dst.parent.mkdir(parents=True)
        dst.symlink_to(stow / 'agents' / 'missing.md')

        calls   = self._record_shell(monkeypatch)
        prompts = self._fake_confirm(monkeypatch)

        self._run()
        assert dst.is_symlink()
        assert dst.readlink() == stow / 'agents' / 'missing.md'
        assert local.read_text(encoding='utf-8') == 'local'
        assert 'CONFLICT' in run.unstyle(capsys.readouterr().out)
        assert prompts == []
        assert calls   == []

    def test_mixed_conflict_moves_the_rest_but_skips_the_doomed_restow(
        self,
        claude: tuple[Path, Path],
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        preflight_calls: list[list[str]],
    ) -> None:
        """
        Test that with a conflict present the movable file moves, stow is not run, and recovery steps are printed
        """
        config, stow = claude
        local = _write(config / 'agents' / 'dup.md', 'local')
        repo  = _write(stow / 'agents' / 'dup.md', 'repo')

        _write(config / 'skills' / 'foo' / 'SKILL.md', 'skill')
        calls   = self._record_shell(monkeypatch)
        prompts = self._fake_confirm(monkeypatch)

        self._run()
        assert not (config / 'skills' / 'foo' / 'SKILL.md').exists()
        assert (stow / 'skills' / 'foo' / 'SKILL.md').read_text(encoding='utf-8') == 'skill'
        assert local.read_text(encoding='utf-8') == 'local'
        assert repo.read_text(encoding='utf-8')  == 'repo'

        assert calls           == []
        assert preflight_calls == []
        assert len(prompts)    == 1
        assert 'restow' not in prompts[0]

        out = run.unstyle(capsys.readouterr().out)
        for expected in ('CONFLICT', 'stow claude', '--backup-conflicts', 'git add stow/claude/.claude'):
            assert expected in out
        assert 'absent from ~/.claude until the restow succeeds' in out

    def test_dry_run_with_conflicts_does_not_promise_a_restow(
        self,
        claude: tuple[Path, Path],
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that the dry-run summary omits the restow when a conflict would block it
        """
        config, stow = claude
        _write(config / 'agents' / 'dup.md', 'local')
        _write(stow / 'agents' / 'dup.md', 'repo')
        _write(config / 'agents' / 'new.md')
        self._record_shell(monkeypatch)

        self._run(dry_run=True)
        summary = next(line for line in run.unstyle(capsys.readouterr().out).splitlines() if 'Dry run' in line)
        assert 'would move 1 file(s)' in summary
        assert 'restow' not in summary

    def test_destination_that_appears_before_the_move_is_not_overwritten(
        self,
        claude: tuple[Path, Path],
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that a destination created after planning (while confirming) is skipped as a conflict, not replaced
        """
        config, stow = claude
        raced = _write(config / 'agents' / 'raced.md', 'local')
        clean = _write(config / 'agents' / 'clean.md', 'clean')
        calls = self._record_shell(monkeypatch)

        def confirm_then_race(prompt_text: str, **kwargs: object) -> bool:
            _write(stow / 'agents' / 'raced.md', 'appeared')
            return True

        monkeypatch.setattr(run, 'confirm', confirm_then_race)

        self._run()
        assert raced.read_text(encoding='utf-8') == 'local'
        assert (stow / 'agents' / 'raced.md').read_text(encoding='utf-8') == 'appeared'
        assert not clean.exists()
        assert (stow / 'agents' / 'clean.md').read_text(encoding='utf-8') == 'clean'
        assert calls == []

        out = run.unstyle(capsys.readouterr().out)
        assert 'CONFLICT'           in out
        assert '--backup-conflicts' in out

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
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that a failing restow exits 1, says the moved files are not linked back, and names the count and recovery
        """
        config, stow = claude
        _write(config / 'agents' / 'new.md')
        self._record_shell(monkeypatch, returncode=1)
        monkeypatch.setattr(run, 'confirm', lambda *args, **kwargs: True)

        with pytest.raises(SystemExit) as exc_info:
            self._run()
        assert exc_info.value.code == run.ExitCode.COMMAND_FAILED
        assert (stow / 'agents' / 'new.md').exists()

        out = run.unstyle(capsys.readouterr().out)
        assert '1 file(s) are now in the repo but NOT linked back into ~/.claude' in out
        assert 'all-or-nothing'                                                   in out
        assert 'python3 run.py stow claude'                                       in out

    def test_preflight_runs_stow_simulation_before_the_prompt(
        self,
        claude: tuple[Path, Path],
        monkeypatch: pytest.MonkeyPatch,
        preflight_calls: list[list[str]],
    ) -> None:
        """
        Test that a passing stow simulation of the claude package happens once, before confirming, and the run proceeds
        """
        config, stow = claude
        _write(config / 'skills' / 'foo' / 'SKILL.md', 'skill')
        calls = self._record_shell(monkeypatch)
        seen_at_prompt: list[int] = []

        def fake_confirm(prompt_text: str, **kwargs: object) -> bool:
            seen_at_prompt.append(len(preflight_calls))
            return True

        monkeypatch.setattr(run, 'confirm', fake_confirm)

        self._run()
        assert preflight_calls == [['bash', str(run.STOW_SCRIPT), '-n', 'claude']]
        assert seen_at_prompt == [1]
        assert (stow / 'skills' / 'foo' / 'SKILL.md').exists()
        assert calls == [['bash', str(run.STOW_SCRIPT), 'claude']]

    def test_failed_preflight_moves_nothing_and_exits_command_failed(
        self,
        claude: tuple[Path, Path],
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that a failing stow simulation aborts before prompting or moving, shows stow's first lines, and exits 1
        """
        config, stow = claude
        src = _write(config / 'agents' / 'new.md')

        stow_lines = [f'\033[31mstow: blocked path {n}\033[0m' for n in range(12)]
        self._stub_preflight(monkeypatch, returncode=1, stderr='\n'.join(stow_lines) + '\n')

        calls = self._record_shell(monkeypatch)
        monkeypatch.setattr(run, 'confirm', lambda *args, **kwargs: pytest.fail('must not prompt'))

        with pytest.raises(SystemExit) as exc_info:
            self._run()

        assert exc_info.value.code == run.ExitCode.COMMAND_FAILED
        assert src.exists()
        assert not (stow / 'agents' / 'new.md').exists()
        assert calls == []

        out = run.unstyle(capsys.readouterr().out)
        assert 'nothing was moved'        in out
        assert 'stow: blocked path 0'     in out
        assert 'stow: blocked path 7'     in out
        assert 'stow: blocked path 8' not in out

    def test_dry_run_warns_when_the_preflight_fails_but_does_not_exit(
        self,
        claude: tuple[Path, Path],
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that --dry-run reports a failing stow simulation as a warning, moves nothing, and still returns normally
        """
        config, stow = claude
        src = _write(config / 'agents' / 'new.md')
        self._stub_preflight(monkeypatch, returncode=1, stdout='stow: blocked path\n')
        calls = self._record_shell(monkeypatch)

        self._run(dry_run=True)
        assert src.exists()
        assert not (stow / 'agents' / 'new.md').exists()
        assert calls == []

        out = run.unstyle(capsys.readouterr().out)
        assert 'stow: blocked path' in out
        assert 'would fail'         in out
        assert 'Dry run'            in out

    @pytest.mark.parametrize('error_type', [OSError, KeyboardInterrupt])
    def test_interrupted_move_reports_the_files_already_moved(
        self,
        claude: tuple[Path, Path],
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        error_type: type[BaseException],
    ) -> None:
        """
        Test that a failure on the second move lists the first moved file with the recovery command, then propagates
        """
        config, stow = claude
        _write(config / 'agents' / 'a.md')
        _write(config / 'agents' / 'b.md')

        calls = self._record_shell(monkeypatch)
        monkeypatch.setattr(run, 'confirm', lambda *args, **kwargs: True)
        real_move = run.shutil.move

        attempts: list[str] = []

        def flaky_move(src: str, dst: str) -> str:
            attempts.append(src)
            if len(attempts) == 2:
                raise error_type('boom')
            return real_move(src, dst)

        monkeypatch.setattr(run.shutil, 'move', flaky_move)

        with pytest.raises(error_type):
            self._run()
        assert (stow / 'agents' / 'a.md').exists()
        assert (config / 'agents' / 'b.md').exists()
        assert calls == []

        report = run.unstyle(capsys.readouterr().out).split('already moved', 1)[1]
        assert 'agents/a.md'                in report
        assert 'agents/b.md'            not in report
        assert 'python3 run.py stow claude' in report
