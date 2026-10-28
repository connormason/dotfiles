"""
Unit tests for the manifest handling of bootstrap/90-python.sh (run in dry-run against a stub uv)
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
STAGE     = REPO_ROOT / 'bootstrap' / '90-python.sh'


@pytest.fixture
def overlay(tmp_path: Path) -> Path:
    """
    An empty overlay whose bootstrap/uv-tools.txt each test writes
    """
    (tmp_path / 'overlay' / 'bootstrap').mkdir(parents=True)
    return tmp_path / 'overlay'


@pytest.fixture
def env(tmp_path: Path, overlay: Path) -> dict[str, str]:
    """
    Isolated environment: the overlay registered, stub uv (no tools installed) and hatch first on PATH, dry-run on
    """
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    for tool in ('uv', 'hatch'):
        stub = bin_dir / tool
        stub.write_text('#!/bin/sh\nexit 0\n', encoding='utf-8')
        stub.chmod(0o755)
    registry = tmp_path / 'overlays'
    registry.write_text(f'{overlay}\n', encoding='utf-8')
    scrubbed = ('DOTFILES_REPO', 'DOTFILES_LAYER', 'DOTFILES_BREW_PREFIXES', 'XDG_CONFIG_HOME')
    return {
        **{key: value for key, value in os.environ.items() if key not in scrubbed},
        'HOME': str(tmp_path / 'home'),
        'PATH': f'{bin_dir}:{os.environ["PATH"]}',
        'DOTFILES_OVERLAYS_FILE': str(registry),
        'BOOTSTRAP_DRY_RUN': '1',
    }


def _stage(shell: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """
    Run the 90-python stage under the bash interpreter being tested
    """
    return subprocess.run([shell, str(STAGE)], capture_output=True, text=True, check=False, env=env)


class TestUvToolsManifest:
    """
    Tests for merging uv-tools.txt across layers
    """
    def test_overlay_line_replaces_base_line_in_place(self, shell: str, env: dict[str, str], overlay: Path) -> None:
        """
        Test that an overlay line for a base tool replaces the base line at the base tool's position
        """
        (overlay / 'bootstrap' / 'uv-tools.txt').write_text('posting --with extra-pkg\nzz-overlay-only\n', 'utf-8')
        result = _stage(shell, env)
        assert result.returncode == 0, result.stderr
        installs = [line for line in result.stdout.splitlines() if 'uv tool install' in line]
        assert any(line.endswith('uv tool install posting --with extra-pkg') for line in installs)
        assert not any(line.endswith('uv tool install posting') for line in installs)
        assert installs[-1].endswith('uv tool install zz-overlay-only')

    def test_option_first_line_is_fatal(self, shell: str, env: dict[str, str], overlay: Path) -> None:
        """
        Test that a line starting with an option dies with the manifest path and line number
        """
        manifest = overlay / 'bootstrap' / 'uv-tools.txt'
        manifest.write_text('# comment\nok-tool\n  --with stray\n', encoding='utf-8')
        result = _stage(shell, env)
        assert result.returncode != 0
        assert f'{manifest.resolve()}:3: a line must start with the tool name' in result.stderr
