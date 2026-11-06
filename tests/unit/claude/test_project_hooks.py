"""
Unit tests for the project Claude Code hooks under .claude/hooks/ and their wiring in .claude/settings.json
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT    = Path(__file__).resolve().parents[3]
HOOKS_DIR    = REPO_ROOT / '.claude' / 'hooks'
SETTINGS     = REPO_ROOT / '.claude' / 'settings.json'
GUARD_SCRIPT = HOOKS_DIR / 'block-protected-files.sh'
LINT_SCRIPT  = HOOKS_DIR / 'lint-on-edit.sh'

needs_jq  = pytest.mark.skipif(not shutil.which('jq'), reason='jq not available')
needs_git = pytest.mark.skipif(not shutil.which('git'), reason='git not available')


def _run_hook(
    script: Path, file_path: str | None, env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """
    Run a hook script the way Claude Code does: tool data as JSON on stdin, no per-argument environment variables
    """
    tool_input = {} if file_path is None else {'file_path': file_path}
    payload    = json.dumps({'hook_event_name': 'PostToolUse', 'tool_name': 'Write', 'tool_input': tool_input})
    return subprocess.run(
        [str(script)], input=payload, capture_output=True, text=True, check=False, env={**os.environ, **(env or {})},
    )


class TestSettingsWiring:
    """
    Tests that settings.json hooks point at real scripts and read stdin, not phantom environment variables
    """
    def test_hook_commands_reference_existing_executable_scripts(self) -> None:
        """
        Every hook command names a script under .claude/hooks/ that exists and is executable
        """
        hooks    = json.loads(SETTINGS.read_text(encoding='utf-8'))['hooks']
        commands = [hook['command'] for groups in hooks.values() for group in groups for hook in group['hooks']]
        assert commands, 'parsed zero hook commands from .claude/settings.json'

        for command in commands:
            match = re.search(r'\.claude/hooks/[\w.-]+\.sh', command)
            assert match, f'hook command does not call a script under .claude/hooks/: {command}'
            script = REPO_ROOT / match.group(0)
            assert script.is_file(), f'missing hook script: {script}'
            assert os.access(script, os.X_OK), f'hook script is not executable: {script}'

    def test_settings_do_not_use_nonexistent_tool_arg_variables(self) -> None:
        """
        Claude Code exports no CLAUDE_TOOL_ARG_* variables, so a hook reading one sees an empty string
        """
        assert 'CLAUDE_TOOL_ARG' not in SETTINGS.read_text(encoding='utf-8')
        for script in HOOKS_DIR.glob('*.sh'):
            assert 'CLAUDE_TOOL_ARG' not in script.read_text(encoding='utf-8'), script.name


@needs_jq
class TestBlockProtectedFiles:
    """
    Tests for the PreToolUse guard protecting the vault password and the inventory clone
    """
    @pytest.mark.parametrize(
        'file_path',
        [
            '/repo/vault_password.txt',
            '/repo/vault_password',
            '/repo/inventory/group_vars/all/vault.yml',
            '/repo/.claude/worktrees/x/inventory/hosts.yml',
        ],
    )
    def test_protected_paths_are_blocked(self, file_path: str) -> None:
        """
        Editing a vault password or inventory path exits 2 with a BLOCKED message on stderr
        """
        result = _run_hook(GUARD_SCRIPT, file_path)
        assert result.returncode == 2
        assert 'BLOCKED' in result.stderr

    @pytest.mark.parametrize(
        'file_path',
        [
            '/repo/run.py',
            '/repo/roles/docker/tasks/main.yml',
            '/repo/docs/inventory_notes.md',
            '/repo/scripts/vault_password_helper/readme.md',
        ],
    )
    def test_other_paths_are_allowed(self, file_path: str) -> None:
        """
        Ordinary files, including near-miss names, pass the guard silently
        """
        result = _run_hook(GUARD_SCRIPT, file_path)
        assert result.returncode == 0
        assert result.stderr == ''

    def test_payload_without_file_path_is_allowed(self) -> None:
        """
        A tool call that carries no file_path is not the guard's business
        """
        assert _run_hook(GUARD_SCRIPT, None).returncode == 0


@needs_jq
@needs_git
class TestLintOnEdit:
    """
    Tests for the PostToolUse lint hook, run against a throwaway git repo with a stub uv-public.sh
    """
    @pytest.fixture
    def fake_repo(self, tmp_path: Path) -> Path:
        """
        Create a git repo whose scripts/hooks/uv-public.sh logs its arguments to uv.log and fails when STUB_EXIT is set
        """
        subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
        stub = tmp_path / 'scripts' / 'hooks' / 'uv-public.sh'
        stub.parent.mkdir(parents=True)
        stub.write_text(
            '#!/usr/bin/env bash\n'
            'echo "$@" >> "$(dirname "$0")/../../uv.log"\n'
            'echo "stub output"\n'
            'exit "${STUB_EXIT:-0}"\n',
            encoding='utf-8',
        )
        stub.chmod(0o755)
        return tmp_path

    def test_python_file_runs_ruff_fix_only(self, fake_repo: Path) -> None:
        """
        An edited .py file is passed to `ruff check --fix-only`, never to the formatter
        """
        target = fake_repo / 'mod.py'
        target.write_text('x = 1\n', encoding='utf-8')

        result = _run_hook(LINT_SCRIPT, str(target))

        assert result.returncode == 0
        logged = (fake_repo / 'uv.log').read_text(encoding='utf-8')
        assert f'run ruff check --fix-only --quiet {target}' in logged
        assert 'format' not in logged

    @pytest.mark.parametrize('name', ['play.yml', 'play.yaml'])
    def test_yaml_failure_is_reported_to_claude(self, fake_repo: Path, name: str) -> None:
        """
        A yamllint failure exits 2 with the linter output on stderr, which is how PostToolUse reaches Claude
        """
        target = fake_repo / name
        target.write_text('a: 1\n', encoding='utf-8')

        result = _run_hook(LINT_SCRIPT, str(target), env={'STUB_EXIT': '1'})

        assert result.returncode == 2
        assert 'stub output' in result.stderr
        assert str(target) in result.stderr

    def test_clean_yaml_is_silent(self, fake_repo: Path) -> None:
        """
        A YAML file that lints clean produces no output and exits 0
        """
        target = fake_repo / 'play.yml'
        target.write_text('a: 1\n', encoding='utf-8')

        result = _run_hook(LINT_SCRIPT, str(target))

        assert (result.returncode, result.stdout, result.stderr) == (0, '', '')

    def test_other_extensions_are_ignored(self, fake_repo: Path) -> None:
        """
        Files that are neither Python nor YAML never reach uv
        """
        target = fake_repo / 'notes.md'
        target.write_text('# hi\n', encoding='utf-8')

        assert _run_hook(LINT_SCRIPT, str(target)).returncode == 0
        assert not (fake_repo / 'uv.log').exists()

    def test_repo_without_uv_wrapper_is_ignored(self, tmp_path: Path) -> None:
        """
        A Python file in a repo that lacks scripts/hooks/uv-public.sh is left alone
        """
        subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
        target = tmp_path / 'mod.py'
        target.write_text('x = 1\n', encoding='utf-8')

        result = _run_hook(LINT_SCRIPT, str(target))

        assert (result.returncode, result.stderr) == (0, '')

    def test_missing_file_is_ignored(self, fake_repo: Path) -> None:
        """
        A path that does not exist (for example a deleted file) exits 0 without invoking uv
        """
        assert _run_hook(LINT_SCRIPT, str(fake_repo / 'gone.py')).returncode == 0
        assert not (fake_repo / 'uv.log').exists()
