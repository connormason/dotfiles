"""
Unit tests for bootstrap/lib.sh
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
LIB       = REPO_ROOT / 'bootstrap' / 'lib.sh'


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    """
    Environment with an isolated HOME and overlays registry
    """
    home = tmp_path / 'home'
    home.mkdir()
    return {
        **os.environ,
        'HOME': str(home),
        'XDG_CONFIG_HOME': str(home / '.config'),
        'DOTFILES_OVERLAYS_FILE': str(tmp_path / 'overlays'),
        'BOOTSTRAP_DRY_RUN': '0',
    }


def _bash(script: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """
    Source lib.sh in a fresh bash and run script
    """
    return subprocess.run(
        ['bash', '-c', f'source "{LIB}"\n{script}'],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def _overlay(tmp_path: Path, name: str) -> Path:
    """
    Create an empty overlay directory
    """
    path = tmp_path / name
    (path / 'bootstrap').mkdir(parents=True)
    return path


class TestDotfilesLayers:
    """
    Tests for dotfiles_layers
    """
    def test_no_registry_prints_repo_only(self, env: dict[str, str]) -> None:
        """
        Test that without an overlays file only the repo root is a layer
        """
        result = _bash('dotfiles_layers', env)
        assert result.returncode == 0
        assert result.stdout.splitlines() == [str(REPO_ROOT)]

    def test_registry_order_comments_and_tilde(self, env: dict[str, str], tmp_path: Path) -> None:
        """
        Test that overlays follow the repo in file order, ignoring comments and blanks and expanding ~/
        """
        first  = _overlay(tmp_path, 'first')
        second = _overlay(Path(env['HOME']), 'second')
        Path(env['DOTFILES_OVERLAYS_FILE']).write_text(
            f'# overlays\n\n{first}   # trailing comment\n~/second\n',
            encoding='utf-8',
        )
        result = _bash('dotfiles_layers', env)
        assert result.returncode == 0
        assert result.stdout.splitlines() == [str(REPO_ROOT), str(first), str(second.resolve())]

    def test_missing_overlay_fails(self, env: dict[str, str], tmp_path: Path) -> None:
        """
        Test that a registered overlay that does not exist is an error
        """
        Path(env['DOTFILES_OVERLAYS_FILE']).write_text(f'{tmp_path / "nope"}\n', encoding='utf-8')
        result = _bash('true', env)
        assert result.returncode != 0
        assert 'overlay not found' in result.stderr


class TestManifestFiles:
    """
    Tests for manifest_files
    """
    def test_lists_existing_fragments_in_layer_order(self, env: dict[str, str], tmp_path: Path) -> None:
        """
        Test that manifest fragments are listed base first, skipping layers without the file
        """
        with_file    = _overlay(tmp_path, 'with')
        without_file = _overlay(tmp_path, 'without')
        (with_file / 'bootstrap' / 'repos.txt').write_text('x\n', encoding='utf-8')
        Path(env['DOTFILES_OVERLAYS_FILE']).write_text(f'{without_file}\n{with_file}\n', encoding='utf-8')
        result = _bash('manifest_files repos.txt', env)
        assert result.returncode == 0
        expected = [str(with_file / 'bootstrap' / 'repos.txt')]
        if (REPO_ROOT / 'bootstrap' / 'repos.txt').exists():
            expected.insert(0, str(REPO_ROOT / 'bootstrap' / 'repos.txt'))
        assert result.stdout.splitlines() == expected


class TestLayerEnv:
    """
    Tests for per-layer bootstrap/env.sh
    """
    def test_overlay_env_is_sourced(self, env: dict[str, str], tmp_path: Path) -> None:
        """
        Test that an overlay's bootstrap/env.sh is sourced when lib.sh loads
        """
        overlay = _overlay(tmp_path, 'ov')
        (overlay / 'bootstrap' / 'env.sh').write_text('export LAYER_ENV_PROBE=from-overlay\n', encoding='utf-8')
        Path(env['DOTFILES_OVERLAYS_FILE']).write_text(f'{overlay}\n', encoding='utf-8')
        result = _bash('printf "%s" "$LAYER_ENV_PROBE"', env)
        assert result.stdout == 'from-overlay'


class TestRun:
    """
    Tests for the dry-run aware run helper
    """
    def test_run_executes_when_not_dry(self, env: dict[str, str]) -> None:
        """
        Test that run executes its command normally
        """
        assert _bash('run echo hello', env).stdout.strip() == 'hello'

    def test_run_skips_when_dry(self, env: dict[str, str], tmp_path: Path) -> None:
        """
        Test that run only prints under BOOTSTRAP_DRY_RUN=1
        """
        marker = tmp_path / 'marker'
        result = _bash(f'run touch "{marker}"', {**env, 'BOOTSTRAP_DRY_RUN': '1'})
        assert result.returncode == 0
        assert not marker.exists()
        assert '[dry-run]' in result.stdout

    def test_have(self, env: dict[str, str]) -> None:
        """
        Test that have reports PATH presence
        """
        assert _bash('have bash', env).returncode == 0
        assert _bash('have definitely-not-a-command-xyz', env).returncode != 0
