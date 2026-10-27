"""
Throwaway-home integration tests: base layer + fixture overlay stowed and rendered into an empty HOME
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE   = REPO_ROOT / 'tests' / 'fixtures' / 'overlay'

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which('stow') is None, reason='GNU Stow not installed'),
]


@dataclass
class Home:
    """
    An isolated HOME with the base layer and fixture overlay applied
    """
    path: Path
    env:  dict[str, str]

    def run(self, *cmd: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        """
        Run a command inside this HOME
        """
        return subprocess.run(
            list(cmd), capture_output=True, text=True, check=False, env=self.env, cwd=cwd or self.path
        )

    def zsh(self, command: str) -> subprocess.CompletedProcess[str]:
        """
        Run an interactive zsh command inside this HOME
        """
        return self.run('zsh', '-i', '-c', command)


@pytest.fixture(scope='module')
def home(tmp_path_factory: pytest.TempPathFactory) -> Home:
    """
    Stow and render everything into a fresh HOME once per module
    """
    path     = tmp_path_factory.mktemp('home')
    registry = path / '.config' / 'dotfiles' / 'overlays'
    registry.parent.mkdir(parents=True)
    registry.write_text(f'{FIXTURE}\n', encoding='utf-8')
    env = {
        'HOME': str(path),
        'PATH': os.environ['PATH'],
        'TERM': 'dumb',
        'XDG_CONFIG_HOME': str(path / '.config'),
        'XDG_STATE_HOME': str(path / '.local' / 'state'),
        'XDG_DATA_HOME': str(path / '.local' / 'share'),
    }
    result = Home(path, env)
    stowed = result.run('bash', str(REPO_ROOT / 'stow.sh'))
    assert stowed.returncode == 0, stowed.stdout + stowed.stderr
    rendered = result.run('python3', str(REPO_ROOT / 'scripts' / 'dotfiles' / 'render.py'), '--force')
    assert rendered.returncode == 0, rendered.stdout + rendered.stderr
    return result


class TestEngine:
    """
    Tests that hold for any set of packages
    """
    def test_overlay_package_is_linked(self, home: Home) -> None:
        """
        Test that the fixture overlay's files are stowed beside the base's
        """
        assert (home.path / '.config' / 'zsh' / 'conf.d' / '31-fixture.zsh').is_symlink()

    def test_no_folded_directories(self, home: Home) -> None:
        """
        Test that no directory under HOME is a symlink into a repository
        """
        folded = [p for p in home.path.rglob('*') if p.is_symlink() and p.is_dir()]
        assert folded == []

    def test_rendered_claude_settings_include_overlay(self, home: Home) -> None:
        """
        Test that the rendered Claude settings contain the overlay fragment's values
        """
        settings = json.loads((home.path / '.claude' / 'settings.json').read_text(encoding='utf-8'))
        assert settings['env']['FIXTURE_OVERLAY'] == '1'

    def test_render_is_in_sync(self, home: Home) -> None:
        """
        Test that a second check finds nothing to do
        """
        result = home.run('python3', str(REPO_ROOT / 'scripts' / 'dotfiles' / 'render.py'), '--check')
        assert result.returncode == 0, result.stderr
