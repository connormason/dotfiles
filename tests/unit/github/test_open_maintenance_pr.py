"""
Tests for the open-maintenance-pr action script, run against a throwaway origin/work repo pair with a stubbed gh
"""
from __future__ import annotations

import os
import stat
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).parents[3] / '.github' / 'actions' / 'open-maintenance-pr' / 'open-pr.sh'

BRANCH = 'maintenance/update-things'

RunScript = Callable[..., subprocess.CompletedProcess[str]]

GIT_ENV = {
    **os.environ,
    'GIT_CONFIG_GLOBAL':   os.devnull,
    'GIT_CONFIG_SYSTEM':   os.devnull,
    'GIT_AUTHOR_NAME':     'Test',
    'GIT_AUTHOR_EMAIL':    'test@example.com',
    'GIT_COMMITTER_NAME':  'Test',
    'GIT_COMMITTER_EMAIL': 'test@example.com',
}

FAKE_GH = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$FAKE_GH_LOG"
if [[ "$1 $2" == "pr list" && -n "${FAKE_GH_NUMBER:-}" ]]; then
  echo "$FAKE_GH_NUMBER"
fi
"""


def git(cwd: Path, *args: str) -> str:
    """
    Run git in ``cwd`` with the isolated environment and return stripped stdout
    """
    result = subprocess.run(['git', *args], cwd=cwd, env=GIT_ENV, check=True, capture_output=True, text=True)
    return result.stdout.strip()


@pytest.fixture
def origin(tmp_path: Path) -> Path:
    """
    A bare origin repository
    """
    path = tmp_path / 'origin.git'
    git(tmp_path, 'init', '--bare', '--initial-branch=main', str(path))
    return path


@pytest.fixture
def work(tmp_path: Path, origin: Path) -> Path:
    """
    A clone of the origin with one pushed commit on main containing tracked.txt and other.txt
    """
    path = tmp_path / 'work'
    git(tmp_path, 'clone', str(origin), str(path))
    (path / 'tracked.txt').write_text('base\n', encoding='utf-8')
    (path / 'other.txt').write_text('base\n', encoding='utf-8')
    git(path, 'add', '-A')
    git(path, 'commit', '-m', 'base')
    git(path, 'push', 'origin', 'main')
    return path


@pytest.fixture
def gh_log(tmp_path: Path) -> Path:
    """
    Path of the file the stub gh appends its argument lines to
    """
    return tmp_path / 'gh.log'


@pytest.fixture
def run_script(tmp_path: Path, work: Path, gh_log: Path) -> RunScript:
    """
    Return a callable that runs open-pr.sh in the work clone with the stub gh first on PATH
    """
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    fake_gh = bin_dir / 'gh'
    fake_gh.write_text(FAKE_GH, encoding='utf-8')
    fake_gh.chmod(fake_gh.stat().st_mode | stat.S_IEXEC)

    def _run(*, paths: str = 'tracked.txt', pr_number: str = '', **overrides: str) -> subprocess.CompletedProcess[str]:
        env = {
            **GIT_ENV,
            'PATH':           f'{bin_dir}{os.pathsep}{os.environ["PATH"]}',
            'FAKE_GH_LOG':    str(gh_log),
            'FAKE_GH_NUMBER': pr_number,
            'BRANCH':         BRANCH,
            'PATHS':          paths,
            'TITLE':          'Update things',
            'BODY':           'Body text',
            'COMMIT_MESSAGE': 'chore: update things',
            **overrides,
        }
        return subprocess.run(
            ['bash', str(SCRIPT_PATH)],
            cwd=work,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )

    return _run


def gh_calls(gh_log: Path) -> list[str]:
    """
    Argument lines recorded by the stub gh (empty if it was never called)
    """
    return gh_log.read_text(encoding='utf-8').splitlines() if gh_log.exists() else []


def remote_branches(origin: Path) -> list[str]:
    """
    Names of the maintenance branches present on the origin
    """
    return git(origin, 'for-each-ref', '--format=%(refname:short)', 'refs/heads/maintenance').splitlines()


class TestOpenMaintenancePr:
    """
    Tests for open-pr.sh
    """
    def test_no_changes_is_a_noop(self, run_script: RunScript, origin: Path, gh_log: Path) -> None:
        """
        Test that an unchanged tree pushes nothing and never calls gh
        """
        result = run_script()

        assert result.returncode == 0
        assert 'already up to date' in result.stdout
        assert remote_branches(origin) == []
        assert gh_calls(gh_log) == []

    def test_changes_outside_paths_are_ignored(self, run_script: RunScript, work: Path, origin: Path) -> None:
        """
        Test that a modified file not listed in PATHS does not trigger a commit
        """
        (work / 'other.txt').write_text('changed\n', encoding='utf-8')

        assert run_script(paths='tracked.txt').returncode == 0
        assert remote_branches(origin) == []

    def test_change_pushes_branch_and_creates_pr(
        self, run_script: RunScript, work: Path, origin: Path, gh_log: Path,
    ) -> None:
        """
        Test that a change is committed, force-pushed one commit ahead of main, and opened as a new PR
        """
        (work / 'tracked.txt').write_text('updated\n', encoding='utf-8')

        result = run_script()

        assert result.returncode == 0, result.stderr
        assert remote_branches(origin) == [BRANCH]
        assert git(origin, 'rev-list', '--count', f'main..{BRANCH}') == '1'
        assert git(origin, 'show', f'{BRANCH}:tracked.txt') == 'updated'
        assert git(origin, 'log', '-1', '--format=%s', BRANCH) == 'chore: update things'

        calls = gh_calls(gh_log)
        assert calls[0].startswith('pr list --head maintenance/update-things --base main')
        assert calls[1] == f'pr create --base main --head {BRANCH} --title Update things --body Body text'

    def test_existing_pr_is_edited(self, run_script: RunScript, work: Path, gh_log: Path) -> None:
        """
        Test that an open PR for the branch is refreshed rather than duplicated
        """
        (work / 'tracked.txt').write_text('updated\n', encoding='utf-8')

        assert run_script(pr_number='7').returncode == 0

        calls = gh_calls(gh_log)
        assert calls[1] == 'pr edit 7 --title Update things --body Body text'
        assert not any(call.startswith('pr create') for call in calls)

    def test_untracked_file_under_a_listed_directory_is_included(
        self, run_script: RunScript, work: Path, origin: Path,
    ) -> None:
        """
        Test that new files under a listed path are staged, not only modifications
        """
        (work / 'generated').mkdir()
        (work / 'generated' / 'new.txt').write_text('new\n', encoding='utf-8')

        assert run_script(paths='generated').returncode == 0
        assert git(origin, 'show', f'{BRANCH}:generated/new.txt') == 'new'

    def test_rerun_force_pushes_a_single_commit(self, run_script: RunScript, work: Path, origin: Path) -> None:
        """
        Test that a second run from main replaces the branch instead of stacking commits
        """
        (work / 'tracked.txt').write_text('first\n', encoding='utf-8')
        assert run_script().returncode == 0

        git(work, 'reset', '--hard', 'origin/main')
        (work / 'tracked.txt').write_text('second\n', encoding='utf-8')
        assert run_script().returncode == 0

        assert git(origin, 'rev-list', '--count', f'main..{BRANCH}') == '1'
        assert git(origin, 'show', f'{BRANCH}:tracked.txt') == 'second'

    @pytest.mark.parametrize('missing', ['BRANCH', 'PATHS', 'TITLE', 'BODY', 'COMMIT_MESSAGE'])
    def test_missing_required_variable_fails(self, run_script: RunScript, missing: str) -> None:
        """
        Test that each required variable is enforced with a message naming it
        """
        result = run_script(**{missing: ''})

        assert result.returncode != 0
        assert missing in result.stderr
