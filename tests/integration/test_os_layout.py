"""
OS layout regression tests: which $HOME paths the base layer links on each OS
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.golden import check_golden

REPO_ROOT = Path(__file__).resolve().parents[2]

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which('stow') is None, reason='GNU Stow not installed'),
]


def linked_paths(tmp_path: Path, os_name: str) -> list[str]:
    """
    Stow the base layer (no overlays) into an empty HOME as os_name and list the symlinks it created

    :param tmp_path: scratch directory for the HOME
    :param os_name: value for DOTFILES_OS
    :return: sorted HOME-relative symlink paths
    """
    home = tmp_path / f'home-{os_name}'
    home.mkdir()

    env: dict[str, str] = {
        'HOME':                   str(home),
        'PATH':                   os.environ['PATH'],
        'XDG_CONFIG_HOME':        str(home / '.config'),
        'DOTFILES_OVERLAYS_FILE': str(tmp_path / 'no-overlays'),
        'DOTFILES_OS':            os_name,
    }
    result = subprocess.run(
        ['bash', str(REPO_ROOT / 'stow.sh'), '--no-summary'],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return sorted(str(path.relative_to(home)) for path in home.rglob('*') if path.is_symlink())


class TestDarwinLayout:
    """
    Tests pinning the darwin link set to the pre-Linux-support golden file
    """
    @pytest.mark.skipif(sys.platform != 'darwin', reason='the golden file is regenerated on macOS only')
    def test_darwin_links_match_golden(self, tmp_path: Path) -> None:
        """
        Test that the base layer links exactly the golden set of paths on darwin
        """
        check_golden('darwin-links.txt', linked_paths(tmp_path, 'darwin'))

    def test_darwin_links_match_golden_on_any_host(self, tmp_path: Path) -> None:
        """
        Test that DOTFILES_OS=darwin reproduces the golden set even on a Linux host
        """
        if os.environ.get('DOTFILES_UPDATE_GOLDEN') == '1':
            pytest.skip('golden files are being rewritten')
        check_golden('darwin-links.txt', linked_paths(tmp_path, 'darwin'))


# Paths the base layer links on darwin only (prefix match against the darwin golden file)
DARWIN_ONLY: tuple[str, ...] = (
    '.hammerspoon/',
    '.config/iterm2/',
    '.config/zsh/conf.d/30-iterm2.zsh',
    'Library/',
)

# Paths the base layer links on linux only
LINUX_ONLY: tuple[str, ...] = (
    '.config/hatch/config.toml',
    '.zshenv',
)


class TestLinuxLayout:
    """
    Tests deriving the linux link set from the darwin golden file
    """
    def test_linux_links_are_darwin_minus_macos_packages(self, tmp_path: Path) -> None:
        """
        Test that linux links the darwin set minus macOS-only paths, plus linux-only paths
        """
        if os.environ.get('DOTFILES_UPDATE_GOLDEN') == '1':
            pytest.skip('golden files are being rewritten')

        darwin   = (REPO_ROOT / 'tests' / 'fixtures' / 'os_layout' / 'darwin-links.txt').read_text('utf-8').splitlines()
        expected = sorted([path for path in darwin if not path.startswith(DARWIN_ONLY)] + list(LINUX_ONLY))
        assert linked_paths(tmp_path, 'linux') == expected

    def test_linux_hatch_config_matches_the_darwin_file(self, tmp_path: Path) -> None:
        """
        Test that the linux hatch config resolves to the same content as the macOS one, and nothing lands in ~/Library
        """
        linked_paths(tmp_path, 'linux')
        home = tmp_path / 'home-linux'

        config = home / '.config' / 'hatch' / 'config.toml'
        darwin = REPO_ROOT / 'stow' / 'hatch-darwin' / 'Library' / 'Application Support' / 'hatch' / 'config.toml'
        assert config.is_symlink()
        assert config.read_text(encoding='utf-8') == darwin.read_text(encoding='utf-8')
        assert not (home / 'Library').exists()

    @pytest.mark.skipif(shutil.which('zsh') is None, reason='zsh not installed')
    def test_zshenv_skips_the_debian_global_compinit(self, tmp_path: Path) -> None:
        """
        Test that the linux layout links a ~/.zshenv that sets skip_global_compinit for every zsh
        """
        linked_paths(tmp_path, 'linux')
        home = tmp_path / 'home-linux'

        env: dict[str, str] = {'HOME': str(home), 'PATH': os.environ['PATH']}
        result = subprocess.run(
            ['zsh', '-c', 'print -r -- ${skip_global_compinit-unset}'],
            capture_output=True, text=True, check=False, env=env,
        )
        assert (home / '.zshenv').is_symlink()
        assert result.stdout.strip() == '1', result.stderr

    @pytest.mark.skipif(shutil.which('zsh') is None, reason='zsh not installed')
    def test_interactive_zsh_is_clean_with_the_linux_layout(self, tmp_path: Path) -> None:
        """
        Test that an interactive zsh over the linux layout starts without any error output
        """
        linked_paths(tmp_path, 'linux')
        home = tmp_path / 'home-linux'

        env: dict[str, str] = {
            'HOME':               str(home),
            'PATH':               os.environ['PATH'],
            'TERM':               'dumb',
            'DOTFILES_NO_BANNER': '1',
            'XDG_CONFIG_HOME':    str(home / '.config'),
            'XDG_STATE_HOME':     str(home / '.local' / 'state'),
            'XDG_DATA_HOME':      str(home / '.local' / 'share'),
        }
        result = subprocess.run(['zsh', '-i', '-c', 'true'], capture_output=True, text=True, check=False, env=env)
        assert result.returncode == 0
        assert result.stderr == ''
