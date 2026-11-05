"""
Unit tests for the change-ledger entries of the 80-repos, 90-python, 95-dotfiles, and 97-render stages
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]

_SCRUBBED_VARS: tuple[str, ...] = (
    'BOOTSTRAP_CHANGES_FILE',
    'BOOTSTRAP_DRY_RUN',
    'BOOTSTRAP_NONINTERACTIVE',
    'DOTFILES_BREW_PREFIXES',
    'DOTFILES_LAYER',
    'DOTFILES_OS',
    'DOTFILES_REPO',
    'XDG_CONFIG_HOME',
    'XDG_STATE_HOME',
)

# Keeps lib.sh from appending a real Homebrew prefix to PATH (which would expose a real stow, uv, or git)
NO_BREW = 'ensure_brew_on_path() { return 0; }\n'


@pytest.fixture
def overlay(tmp_path: Path) -> Path:
    """
    An overlay whose env.sh hides any real Homebrew; tests add manifest fragments to its bootstrap/
    """
    root = tmp_path / 'overlay'
    (root / 'bootstrap').mkdir(parents=True)
    (root / 'bootstrap' / 'env.sh').write_text(NO_BREW, encoding='utf-8')
    return root


@pytest.fixture
def env(tmp_path: Path, overlay: Path) -> dict[str, str]:
    """
    Isolated HOME, the overlay registered, a stub bin directory first on a minimal PATH, and a ledger
    """
    (tmp_path / 'bin').mkdir()
    (tmp_path / 'home').mkdir()
    registry = tmp_path / 'overlays'
    registry.write_text(f'{overlay}\n', encoding='utf-8')
    return {
        **{key: value for key, value in os.environ.items() if key not in _SCRUBBED_VARS},
        'HOME':                   str(tmp_path / 'home'),
        'PATH':                   f'{tmp_path / "bin"}:/usr/bin:/bin',
        'DOTFILES_OVERLAYS_FILE': str(registry),
        'BOOTSTRAP_DRY_RUN':      '0',
        'BOOTSTRAP_CHANGES_FILE': str(tmp_path / 'ledger'),
    }


def _stub(env: dict[str, str], name: str, body: str) -> None:
    """
    Write an executable stub into the env's bin directory
    """
    path = Path(env['PATH'].split(':', 1)[0]) / name
    path.write_text(f'#!/bin/sh\n{body}', encoding='utf-8')
    path.chmod(0o755)


def _stage(shell: str, name: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """
    Run a base stage in place under the bash interpreter being tested
    """
    return subprocess.run(
        [shell, str(REPO_ROOT / 'bootstrap' / f'{name}.sh')],
        capture_output=True,
        text=True,
        check=False,
        env=env,
        stdin=subprocess.DEVNULL,
        timeout=120,
    )


def _ledger(env: dict[str, str]) -> list[str]:
    """
    Lines recorded in the change ledger (empty when none were)
    """
    path = Path(env['BOOTSTRAP_CHANGES_FILE'])
    return path.read_text(encoding='utf-8').splitlines() if path.exists() else []


class TestReposChanges:
    """
    Tests for 80-repos change entries
    """
    def test_clone_is_recorded_once(self, shell: str, env: dict[str, str], overlay: Path) -> None:
        """
        Test that a clone is recorded and an existing clone is not
        """
        (overlay / 'bootstrap' / 'repos.txt').write_text('demo https://example.invalid/demo.git\n', encoding='utf-8')
        _stub(env, 'git', '[ "$1" = clone ] && mkdir -p "$3/.git"\nexit 0\n')

        first = _stage(shell, '80-repos', env)
        assert first.returncode == 0, first.stderr
        assert _ledger(env) == ['cloned demo']

        second = _stage(shell, '80-repos', env)
        assert second.returncode == 0, second.stderr
        assert _ledger(env) == ['cloned demo']


class TestPythonChanges:
    """
    Tests for 90-python change entries
    """
    @pytest.mark.parametrize(
        ('listed', 'expected'),
        [
            ('',               ['installed uv tool ruff']),
            ('ruff v0.9.0\\n', []),
        ],
    )
    def test_install_is_recorded_only_when_missing(
        self,
        shell: str,
        env: dict[str, str],
        overlay: Path,
        listed: str,
        expected: list[str],
    ) -> None:
        """
        Test that a missing tool's install is recorded and a present tool is not
        """
        (overlay / 'bootstrap' / 'uv-tools.txt').write_text('ruff\n', encoding='utf-8')
        _stub(env, 'uv', f'[ "$1 $2" = "tool list" ] && printf "{listed}"\nexit 0\n')
        _stub(env, 'hatch', 'exit 0\n')

        result = _stage(shell, '90-python', {**env, 'BOOTSTRAP_DRY_RUN': '1'})
        assert result.returncode == 0, result.stderr
        # The base uv-tools.txt is merged in too, and the stub lists none of its tools, so only ruff's entry is checked
        assert [line for line in _ledger(env) if line.endswith(' ruff')] == expected


class TestDotfilesChanges:
    """
    Tests for 95-dotfiles change entries (dry run, with stow hidden so only the oh-my-zsh steps are exercised)
    """
    def test_missing_omz_and_plugins_are_recorded(self, shell: str, env: dict[str, str]) -> None:
        """
        Test that a would-be oh-my-zsh install and plugin clones are recorded
        """
        result = _stage(shell, '95-dotfiles', {**env, 'BOOTSTRAP_DRY_RUN': '1'})
        assert result.returncode == 0, result.stderr
        assert {'installed oh-my-zsh', 'cloned omz plugin alias-tips', 'cloned omz plugin zsh-histdb'} <= set(
            _ledger(env),
        )

    def test_present_omz_and_plugins_are_not(self, shell: str, env: dict[str, str]) -> None:
        """
        Test that an installed oh-my-zsh with both plugins records nothing
        """
        omz = Path(env['HOME']) / '.oh-my-zsh'
        for plugin in ('alias-tips', 'zsh-histdb'):
            (omz / 'custom' / 'plugins' / plugin).mkdir(parents=True)
        (omz / 'oh-my-zsh.sh').write_text('# stub\n', encoding='utf-8')

        result = _stage(shell, '95-dotfiles', {**env, 'BOOTSTRAP_DRY_RUN': '1'})
        assert result.returncode == 0, result.stderr
        assert not [line for line in _ledger(env) if 'oh-my-zsh' in line or 'omz plugin' in line]


class TestRenderChanges:
    """
    Tests for 97-render change entries (real render.py into the isolated HOME)
    """
    def test_first_render_is_recorded_and_second_is_not(self, shell: str, env: dict[str, str]) -> None:
        """
        Test that writing settings is recorded and an in-sync render records nothing
        """
        first = _stage(shell, '97-render', env)
        assert first.returncode == 0, first.stderr
        assert _ledger(env) == ['render: wrote settings']

        second = _stage(shell, '97-render', env)
        assert second.returncode == 0, second.stderr
        assert _ledger(env) == ['render: wrote settings']

    def test_dry_run_records_drift(self, shell: str, env: dict[str, str]) -> None:
        """
        Test that a dry run against unrendered settings records the drift
        """
        result = _stage(shell, '97-render', {**env, 'BOOTSTRAP_DRY_RUN': '1'})
        assert result.returncode == 0, result.stderr
        assert _ledger(env) == ['render: settings out of sync']
