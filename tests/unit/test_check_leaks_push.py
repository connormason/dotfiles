"""
Unit tests for scripts/hooks/check-leaks-push.sh
"""
from __future__ import annotations

import os
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
    Fixture git repo with one clean root commit; private patterns isolated away
    """
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'xdg'))
    monkeypatch.delenv('DOTFILES_LEAK_PATTERNS', raising=False)
    for role in ('AUTHOR', 'COMMITTER'):
        monkeypatch.setenv(f'GIT_{role}_NAME', 'Jane Doe')
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
    env = {**os.environ, 'GIT_AUTHOR_EMAIL': email, 'GIT_COMMITTER_EMAIL': email}
    _git(repo, 'commit', '-q', '--allow-empty', '-m', message, env=env)
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
        base = _git(repo, 'rev-parse', 'HEAD')
        head = _commit(repo, f'fix: talk to pkgs.{CORP_DOMAIN}')
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
