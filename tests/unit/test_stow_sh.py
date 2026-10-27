"""
Unit tests for stow.sh (layered stow driver)
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.skipif(shutil.which('stow') is None, reason='GNU Stow not installed')


@pytest.fixture
def world(tmp_path: Path, shell: str) -> dict[str, Path]:
    """
    Fixture repo (copy of the engine files), overlay, HOME, overlays registry, and the bash interpreter under test
    """
    repo = tmp_path / 'repo'
    (repo / 'bootstrap').mkdir(parents=True)
    (repo / 'scripts' / 'utility').mkdir(parents=True)
    shutil.copy2(REPO_ROOT / 'stow.sh', repo / 'stow.sh')
    shutil.copy2(REPO_ROOT / 'bootstrap' / 'lib.sh', repo / 'bootstrap' / 'lib.sh')
    shutil.copy2(REPO_ROOT / 'scripts' / 'utility' / 'summarize_stow.awk', repo / 'scripts' / 'utility')
    overlay = tmp_path / 'overlay'
    (overlay / 'stow').mkdir(parents=True)
    home = tmp_path / 'home'
    home.mkdir()
    return {'repo': repo, 'overlay': overlay, 'home': home, 'registry': tmp_path / 'overlays', 'shell': Path(shell)}


def _pkg(layer: Path, pkg: str, files: dict[str, str]) -> None:
    """
    Create a stow package with the given $HOME-relative files
    """
    for rel, content in files.items():
        path = layer / 'stow' / pkg / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')


def _stow(world: dict[str, Path], *args: str, register_overlay: bool = True) -> subprocess.CompletedProcess[str]:
    """
    Run the fixture repo's stow.sh (under the parametrized bash) with an isolated HOME
    """
    if register_overlay:
        world['registry'].write_text(f'{world["overlay"]}\n', encoding='utf-8')
    env = {
        **os.environ,
        'HOME': str(world['home']),
        'XDG_CONFIG_HOME': str(world['home'] / '.config'),
        'DOTFILES_OVERLAYS_FILE': str(world['registry']),
    }
    env.pop('DOTFILES_REPO', None)
    return subprocess.run(
        [str(world['shell']), str(world['repo'] / 'stow.sh'), *args],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


class TestDiscovery:
    """
    Tests for package discovery across layers
    """
    def test_list_shows_packages_with_layers(self, world: dict[str, Path]) -> None:
        """
        Test that --list prints base packages, then overlay packages, with their layer roots
        """
        _pkg(world['repo'], 'shell', {'.zshrc': 'x'})
        _pkg(world['overlay'], 'work-shell', {'.config/zsh/conf.d/31-work.zsh': 'x'})
        result = _stow(world, '--list')
        assert result.returncode == 0, result.stderr
        assert result.stdout.splitlines() == [
            f'shell\t{world["repo"].resolve()}',
            f'work-shell\t{world["overlay"].resolve()}',
        ]

    def test_duplicate_package_name_fails(self, world: dict[str, Path]) -> None:
        """
        Test that a package name defined in two layers is rejected
        """
        _pkg(world['repo'], 'shell', {'.zshrc': 'x'})
        _pkg(world['overlay'], 'shell', {'.zprofile': 'x'})
        result = _stow(world, '--list')
        assert result.returncode != 0
        assert "package 'shell' is defined in two layers" in result.stderr

    def test_unknown_package_fails(self, world: dict[str, Path]) -> None:
        """
        Test that requesting an unknown package is an error
        """
        _pkg(world['repo'], 'shell', {'.zshrc': 'x'})
        result = _stow(world, 'nope')
        assert result.returncode != 0
        assert 'unknown package: nope' in result.stderr

    def test_missing_overlay_fails(self, world: dict[str, Path]) -> None:
        """
        Test that a registered but missing overlay aborts before stowing
        """
        _pkg(world['repo'], 'shell', {'.zshrc': 'x'})
        world['registry'].write_text(f'{world["overlay"] / "gone"}\n', encoding='utf-8')
        result = _stow(world, register_overlay=False)
        assert result.returncode != 0
        assert not (world['home'] / '.zshrc').exists()


class TestOwnership:
    """
    Tests for single ownership of $HOME paths
    """
    def test_two_packages_same_path_fails_before_linking(self, world: dict[str, Path]) -> None:
        """
        Test that two packages providing one path abort the run and name both owners
        """
        _pkg(world['repo'], 'shell', {'.zshrc': 'a', '.zprofile': 'a'})
        _pkg(world['overlay'], 'work-shell', {'.zshrc': 'b'})
        result = _stow(world)
        assert result.returncode == 1
        assert '~/.zshrc' in result.stderr
        assert 'shell' in result.stderr
        assert 'work-shell' in result.stderr
        assert not (world['home'] / '.zprofile').exists()

    def test_readme_at_package_root_is_ignored(self, world: dict[str, Path]) -> None:
        """
        Test that package-root README files (ignored by stow) do not count as owned paths
        """
        _pkg(world['repo'], 'shell', {'README.md': 'docs', '.zshrc': 'x'})
        _pkg(world['overlay'], 'work-shell', {'README.md': 'docs'})
        assert _stow(world).returncode == 0


class TestLinking:
    """
    Tests for linking behavior
    """
    def test_layers_share_real_directories(self, world: dict[str, Path]) -> None:
        """
        Test that base and overlay files land in one real (unfolded) directory
        """
        _pkg(world['repo'], 'shell', {'.config/zsh/conf.d/00-lib.zsh': 'base'})
        _pkg(world['overlay'], 'work-shell', {'.config/zsh/conf.d/31-work.zsh': 'work'})
        result = _stow(world)
        assert result.returncode == 0, result.stderr
        conf_d = world['home'] / '.config' / 'zsh' / 'conf.d'
        assert conf_d.is_dir()
        assert not conf_d.is_symlink()
        assert (conf_d / '00-lib.zsh').is_symlink()
        assert (conf_d / '31-work.zsh').read_text(encoding='utf-8') == 'work'
        assert 'stow: applied' in result.stdout

    def test_single_package_directory_is_not_folded(self, world: dict[str, Path]) -> None:
        """
        Test that a directory owned by one package is still a real directory
        """
        _pkg(world['repo'], 'tmux', {'.config/tmux/tmux.conf': 'x'})
        assert _stow(world).returncode == 0
        assert not (world['home'] / '.config' / 'tmux').is_symlink()

    def test_restow_is_idempotent(self, world: dict[str, Path]) -> None:
        """
        Test that a second run reports no changes
        """
        _pkg(world['repo'], 'shell', {'.zshrc': 'x'})
        assert _stow(world).returncode == 0
        second = _stow(world)
        assert second.returncode == 0
        assert 'no changes' in second.stdout

    def test_dry_run_writes_nothing(self, world: dict[str, Path]) -> None:
        """
        Test that -n simulates without creating links
        """
        _pkg(world['repo'], 'shell', {'.zshrc': 'x'})
        result = _stow(world, '-n')
        assert result.returncode == 0
        assert not (world['home'] / '.zshrc').exists()
        assert 'simulated' in result.stdout

    def test_backup_conflicts_moves_existing_file(self, world: dict[str, Path]) -> None:
        """
        Test that --backup-conflicts moves a blocking regular file aside, then links
        """
        _pkg(world['repo'], 'shell', {'.zshrc': 'repo'})
        (world['home'] / '.zshrc').write_text('old', encoding='utf-8')
        result = _stow(world, '--backup-conflicts')
        assert result.returncode == 0, result.stderr
        assert (world['home'] / '.zshrc').is_symlink()
        backups = list((world['home'] / '.dotfiles-backup').glob('*/.zshrc'))
        assert len(backups) == 1
        assert backups[0].read_text(encoding='utf-8') == 'old'
