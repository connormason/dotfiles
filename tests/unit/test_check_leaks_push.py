"""
Unit tests for scripts/hooks/check-leaks-push.sh
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT    = REPO_ROOT / 'scripts' / 'hooks' / 'check-leaks-push.sh'

# Built at runtime so this file never contains the literal identifier it exercises
CORP_DOMAIN = 'apple' + '.com'


def _git(repo: Path, *args: str, env: dict[str, str] | None = None) -> str:
    """
    Run git in a fixture repo and return stdout
    """
    result = subprocess.run(['git', '-C', str(repo), *args], capture_output=True, text=True, check=True, env=env)
    return result.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """
    Fixture git repo with one clean root commit; private patterns and global git config isolated away
    """
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'xdg'))
    monkeypatch.delenv('DOTFILES_LEAK_PATTERNS', raising=False)

    # A developer's diff.renames, core.quotePath, etc. must not change what the script sees
    monkeypatch.setenv('GIT_CONFIG_GLOBAL', os.devnull)
    monkeypatch.setenv('GIT_CONFIG_NOSYSTEM', '1')

    for role in ('AUTHOR', 'COMMITTER'):
        monkeypatch.setenv(f'GIT_{role}_NAME',  'Jane Doe')
        monkeypatch.setenv(f'GIT_{role}_EMAIL', 'jane@example.org')

    path = tmp_path / 'repo'
    path.mkdir()
    _git(path, 'init', '-q', '-b', 'main', '--template=')
    _git(path, 'commit', '-q', '--allow-empty', '-m', 'root')
    return path


def _commit(repo: Path, message: str, email: str = 'jane@example.org') -> str:
    """
    Create an empty commit and return its sha
    """
    env: dict[str, str] = {**os.environ, 'GIT_AUTHOR_EMAIL': email, 'GIT_COMMITTER_EMAIL': email}
    _git(repo, 'commit', '-q', '--allow-empty', '-m', message, env=env)
    return _git(repo, 'rev-parse', 'HEAD')


def _write_commit(repo: Path, name: str, content: str, message: str) -> str:
    """
    Write a file, commit it, and return the new sha
    """
    (repo / name).write_text(content, encoding='utf-8')
    _git(repo, 'add', name)
    _git(repo, 'commit', '-q', '-m', message)
    return _git(repo, 'rev-parse', 'HEAD')


def _run(repo: Path, from_ref: str | None, to_ref: str) -> subprocess.CompletedProcess[str]:
    """
    Run the pre-push script inside the fixture repo
    """
    env = {**os.environ, 'PRE_COMMIT_TO_REF': to_ref}
    if from_ref is not None:
        env['PRE_COMMIT_FROM_REF'] = from_ref
    return subprocess.run([str(SCRIPT)], cwd=repo, capture_output=True, text=True, check=False, env=env)


class TestCheckLeaksPush:
    """
    Tests for check-leaks-push.sh
    """
    def test_clean_range_passes(self, repo: Path) -> None:
        """
        Test that clean messages and identities pass
        """
        base = _git(repo, 'rev-parse', 'HEAD')
        head = _commit(repo, 'feat: clean change')
        assert _run(repo, base, head).returncode == 0

    def test_leaky_message_fails(self, repo: Path) -> None:
        """
        Test that a corporate domain in a pushed commit message is rejected
        """
        base   = _git(repo, 'rev-parse', 'HEAD')
        head   = _commit(repo, f'fix: talk to pkgs.{CORP_DOMAIN}')
        result = _run(repo, base, head)

        assert result.returncode == 1
        assert CORP_DOMAIN not in result.stdout

    def test_leaky_author_fails(self, repo: Path) -> None:
        """
        Test that a corporate author email in the pushed range is rejected
        """
        base = _git(repo, 'rev-parse', 'HEAD')
        head = _commit(repo, 'chore: cherry-picked', email=f'jane@{CORP_DOMAIN}')
        assert _run(repo, base, head).returncode == 1

    def test_commits_before_range_are_ignored(self, repo: Path) -> None:
        """
        Test that history before the pushed range is not scanned
        """
        old  = _commit(repo, f'old: mentions {CORP_DOMAIN}')
        head = _commit(repo, 'feat: clean change')
        assert _run(repo, old, head).returncode == 0

    def test_unknown_from_ref_scans_tip_only(self, repo: Path) -> None:
        """
        Test that an unreachable from-ref without an upstream falls back to the tip commit only
        """
        _commit(repo, f'old: mentions {CORP_DOMAIN}')
        head = _commit(repo, 'feat: clean tip')
        assert _run(repo, '0' * 40, head).returncode == 0

    def test_content_added_then_removed_in_range_fails(self, repo: Path) -> None:
        """
        Test that content added by one pushed commit and removed by a later one is caught although the tip is clean
        """
        base = _git(repo, 'rev-parse', 'HEAD')
        _write_commit(repo, 'notes.txt', f'mirror: pkgs.{CORP_DOMAIN}\n', 'docs: add notes')

        head   = _write_commit(repo, 'notes.txt', 'mirror: example.org\n', 'docs: scrub notes')
        result = _run(repo, base, head)

        assert result.returncode == 1
        assert CORP_DOMAIN                      not in result.stdout
        assert f'pre-push: scanning {base}..{head}' in result.stdout

        hint = (
            "pre-push: inspect with: git log -p -U0 --cc --no-textconv --format='commit %h' --no-color "
            f'{base}..{head}'
        )
        assert hint in result.stdout

        path_hint = (
            'pre-push: and (paths):  git -c core.quotePath=false log --name-only --diff-filter=ACR --cc --no-textconv '
            f"--format='commit %h' --no-color {base}..{head}"
        )
        assert path_hint in result.stdout
        assert re.search(r'patch line N <= \d+ is line N of the first command', result.stdout)

    def test_removing_content_that_predates_range_passes(self, repo: Path) -> None:
        """
        Test that a pushed commit which only deletes already-published content is not rejected for the deleted lines
        """
        base   = _write_commit(repo, 'notes.txt', f'mirror: pkgs.{CORP_DOMAIN}\nkeep: example.org\n', 'docs: old notes')
        head   = _write_commit(repo, 'notes.txt', 'keep: example.org\n', 'docs: scrub notes')
        result = _run(repo, base, head)

        assert result.returncode == 0, result.stdout
        assert f'pre-push: scanning {base}..{head}' in result.stdout
        assert 'inspect with'                   not in result.stdout

    def test_empty_file_with_leaky_path_fails(self, repo: Path) -> None:
        """
        Test that a leak present only in the path of a pushed empty file is caught
        """
        base   = _git(repo, 'rev-parse', 'HEAD')
        head   = _write_commit(repo, f'pkgs.{CORP_DOMAIN}.txt', '', 'docs: add placeholder')
        result = _run(repo, base, head)

        assert result.returncode == 1
        assert CORP_DOMAIN not in result.stdout

    def test_pure_rename_to_leaky_path_fails(self, repo: Path) -> None:
        """
        Test that a content-preserving rename to a leaky path is caught although the patch has no added lines
        """
        base = _write_commit(repo, 'notes.txt', 'keep: example.org\n', 'docs: add notes')
        _git(repo, 'mv', 'notes.txt', f'pkgs.{CORP_DOMAIN}.txt')
        _git(repo, 'commit', '-q', '-m', 'docs: rename notes')

        head   = _git(repo, 'rev-parse', 'HEAD')
        result = _run(repo, base, head)
        assert result.returncode == 1
        assert CORP_DOMAIN not in result.stdout

    def test_merge_resolution_adding_leak_fails(self, repo: Path) -> None:
        """
        Test that a leak introduced only by a merge's conflict resolution is caught
        """
        _write_commit(repo, 'notes.txt', 'mirror: example.org\n', 'docs: add notes')

        base = _git(repo, 'rev-parse', 'HEAD')
        _git(repo, 'checkout', '-q', '-b', 'side')
        _write_commit(repo, 'notes.txt', 'mirror: side.example.org\n', 'docs: side notes')
        _git(repo, 'checkout', '-q', 'main')
        _write_commit(repo, 'notes.txt', 'mirror: main.example.org\n', 'docs: main notes')

        merge = subprocess.run(['git', '-C', str(repo), 'merge', 'side'], capture_output=True, text=True, check=False)
        assert merge.returncode != 0

        (repo / 'notes.txt').write_text(f'mirror: pkgs.{CORP_DOMAIN}\n', encoding='utf-8')
        _git(repo, 'add', 'notes.txt')
        _git(repo, 'commit', '-q', '--no-edit')

        head   = _git(repo, 'rev-parse', 'HEAD')
        result = _run(repo, base, head)
        assert result.returncode == 1
        assert CORP_DOMAIN not in result.stdout

    def test_merge_introducing_leaky_path_fails(self, repo: Path) -> None:
        """
        Test that a leak living only in the path of a file renamed by a merge commit is caught
        """
        _write_commit(repo, 'notes.txt', 'mirror: example.org\n', 'docs: add notes')

        base = _git(repo, 'rev-parse', 'HEAD')
        _git(repo, 'checkout', '-q', '-b', 'side')
        _write_commit(repo, 'side.txt', 'side: example.org\n', 'docs: side notes')
        _git(repo, 'checkout', '-q', 'main')
        _write_commit(repo, 'main.txt', 'main: example.org\n', 'docs: main notes')

        # The combined diff shows no hunk for a content-preserving rename, so only the path listing can see it
        _git(repo, 'merge', '-q', '--no-commit', '--no-ff', 'side')
        _git(repo, 'mv', 'notes.txt', f'pkgs.{CORP_DOMAIN}.txt')
        _git(repo, 'commit', '-q', '--no-edit')

        head   = _git(repo, 'rev-parse', 'HEAD')
        result = _run(repo, base, head)
        assert result.returncode == 1
        assert CORP_DOMAIN not in result.stdout

    def test_nul_byte_in_patch_does_not_disable_scan(self, repo: Path) -> None:
        """
        Test that a NUL byte on an added line does not hide a leak elsewhere in the scanned patch
        """
        # `diff` forces a textual patch; otherwise git would treat the NUL-bearing file as binary and emit no lines
        info = repo / '.git' / 'info'
        info.mkdir(exist_ok=True)
        (info / 'attributes').write_text('*.dat diff\n', encoding='utf-8')

        base = _git(repo, 'rev-parse', 'HEAD')
        (repo / 'blob.dat').write_bytes(f'head\0tail\nmirror: pkgs.{CORP_DOMAIN}\n'.encode())
        _git(repo, 'add', 'blob.dat')
        _git(repo, 'commit', '-q', '-m', 'docs: add blob')

        head   = _git(repo, 'rev-parse', 'HEAD')
        result = _run(repo, base, head)
        assert result.returncode == 1, result.stdout
        assert CORP_DOMAIN not in result.stdout

    def test_non_ascii_leaky_path_fails(self, repo: Path, tmp_path: Path) -> None:
        """
        Test that a leak containing non-ASCII characters is caught in a path git would otherwise quote as octal escapes
        """
        pattern       = 'café-corp'
        patterns_file = tmp_path / 'xdg' / 'dotfiles' / 'leak-patterns.txt'
        patterns_file.parent.mkdir(parents=True)
        patterns_file.write_text(f'{pattern}\n', encoding='utf-8')

        base   = _git(repo, 'rev-parse', 'HEAD')
        head   = _write_commit(repo, f'{pattern}.txt', '', 'docs: add placeholder')
        result = _run(repo, base, head)

        assert result.returncode == 1, result.stdout
        assert pattern not in result.stdout

    def test_octopus_merge_adding_leak_fails(self, repo: Path) -> None:
        """
        Test that a leak added by an octopus merge commit (three parents, three prefix columns) is caught
        """
        _write_commit(repo, 'notes.txt', 'mirror: example.org\n', 'docs: add notes')

        base = _git(repo, 'rev-parse', 'HEAD')
        for branch in ('left', 'right'):
            _git(repo, 'checkout', '-q', '-b', branch, base)
            _write_commit(repo, f'{branch}.txt', f'{branch}: example.org\n', f'docs: {branch} notes')

        _git(repo, 'checkout', '-q', 'main')
        _write_commit(repo, 'main.txt', 'main: example.org\n', 'docs: main notes')

        _git(repo, 'merge', '-q', '--no-commit', '--no-ff', 'left', 'right')
        (repo / 'notes.txt').write_text(f'mirror: pkgs.{CORP_DOMAIN}\n', encoding='utf-8')
        _git(repo, 'add', 'notes.txt')
        _git(repo, 'commit', '-q', '--no-edit')

        head = _git(repo, 'rev-parse', 'HEAD')
        assert len(_git(repo, 'rev-list', '--parents', '-n', '1', head).split()) == 4

        result = _run(repo, base, head)
        assert result.returncode == 1
        assert CORP_DOMAIN not in result.stdout
