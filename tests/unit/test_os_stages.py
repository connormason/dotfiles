"""
Unit tests for OS gating in the bootstrap stages (require_os and the Linux preflight)
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
STAGES    = REPO_ROOT / 'bootstrap'

# Inherited variables that would leak the developer's own configuration into the tests
_SCRUBBED_VARS: tuple[str, ...] = (
    'BOOTSTRAP_DRY_RUN',
    'DOTFILES_REPO',
    'DOTFILES_LAYER',
    'DOTFILES_BREW_PREFIXES',
    'DOTFILES_OS',
    'DOTFILES_OS_RELEASE',
    'XDG_CONFIG_HOME',
)

DEBIAN_RELEASE = 'PRETTY_NAME="Debian GNU/Linux 13 (trixie)"\nID=debian\n'
UBUNTU_RELEASE = 'PRETTY_NAME="Ubuntu 24.04 LTS"\nID=ubuntu\nID_LIKE=debian\n'
FEDORA_RELEASE = 'PRETTY_NAME="Fedora Linux 41"\nID=fedora\n'

LINUX_PREREQS: tuple[str, ...] = ('curl', 'file', 'git', 'cc', 'make', 'ps', 'zsh')


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    """
    Isolated environment: no overlays, a throwaway HOME, dry-run on
    """
    return {
        **{key: value for key, value in os.environ.items() if key not in _SCRUBBED_VARS},
        'HOME':                   str(tmp_path / 'home'),
        'DOTFILES_OVERLAYS_FILE': str(tmp_path / 'no-overlays'),
        'BOOTSTRAP_DRY_RUN':      '1',
    }


@pytest.fixture
def linux_bin(tmp_path: Path) -> Path:
    """
    A hermetic PATH for the Linux preflight: the two utilities the stage itself needs plus a stub per prerequisite
    """
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    for tool in ('dirname', 'uname'):
        real = shutil.which(tool)
        assert real is not None
        (bin_dir / tool).symlink_to(real)

    for tool in LINUX_PREREQS:
        stub = bin_dir / tool
        stub.write_text('#!/bin/sh\nexit 0\n', encoding='utf-8')
        stub.chmod(0o755)
    return bin_dir


def _stage(shell: str, name: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """
    Run a real stage script under the bash interpreter being tested, with stdin closed
    """
    return subprocess.run(
        [shell, str(STAGES / name)],
        capture_output=True,
        text=True,
        check=False,
        env=env,
        stdin=subprocess.DEVNULL,
    )


def _preflight(
    shell: str,
    env: dict[str, str],
    tmp_path: Path,
    bin_dir: Path,
    release: str,
    *,
    dry_run: bool = True,
) -> subprocess.CompletedProcess[str]:
    """
    Run 00-preflight as linux against a fixture os-release and the hermetic PATH
    """
    path = tmp_path / 'os-release'
    path.write_text(release, encoding='utf-8')
    return _stage(
        shell,
        '00-preflight.sh',
        {
            **env,
            'DOTFILES_OS':         'linux',
            'DOTFILES_OS_RELEASE': str(path),
            'PATH':                str(bin_dir),
            'BOOTSTRAP_DRY_RUN':   '1' if dry_run else '0',
        },
    )


class TestDarwinOnlyStages:
    """
    Tests for stages gated with require_os darwin
    """
    @pytest.mark.parametrize('stage', ['60-macos.sh', '72-vscode.sh', '96-iterm2.sh'])
    def test_skips_on_linux_without_running_anything(self, shell: str, env: dict[str, str], stage: str) -> None:
        """
        Test that the stage exits 0 on linux before any mutating command
        """
        result = _stage(shell, stage, {**env, 'DOTFILES_OS': 'linux'})
        assert result.returncode == 0, result.stderr
        assert 'skipped (darwin only; this is linux)' in result.stdout
        assert '[dry-run]' not in result.stdout

    @pytest.mark.skipif(sys.platform != 'darwin', reason='runs macOS commands outside run()')
    @pytest.mark.parametrize('stage', ['60-macos.sh', '96-iterm2.sh'])
    def test_runs_on_darwin(self, shell: str, env: dict[str, str], stage: str) -> None:
        """
        Test that the stage still previews its commands on darwin
        """
        result = _stage(shell, stage, {**env, 'DOTFILES_OS': 'darwin'})
        assert result.returncode == 0, result.stderr
        assert '[dry-run]' in result.stdout


class TestLinuxPreflight:
    """
    Tests for the Linux branch of 00-preflight
    """
    @pytest.mark.parametrize(
        ('release', 'pretty'),
        [
            (DEBIAN_RELEASE, 'Debian GNU/Linux 13 (trixie)'),
            (UBUNTU_RELEASE, 'Ubuntu 24.04 LTS'),
        ],
    )
    def test_debian_family_passes(
        self,
        shell: str,
        env: dict[str, str],
        tmp_path: Path,
        linux_bin: Path,
        release: str,
        pretty: str,
    ) -> None:
        """
        Test that Debian and a Debian derivative pass and are named in the log
        """
        result = _preflight(shell, env, tmp_path, linux_bin, release, dry_run=False)
        assert result.returncode == 0, result.stderr
        assert pretty in result.stdout
        assert 'preflight OK' in result.stdout

    def test_other_distribution_fails(self, shell: str, env: dict[str, str], tmp_path: Path, linux_bin: Path) -> None:
        """
        Test that a non-Debian distribution is refused
        """
        result = _preflight(shell, env, tmp_path, linux_bin, FEDORA_RELEASE)
        assert result.returncode != 0
        assert "unsupported Linux distribution 'fedora'" in result.stderr

    def test_missing_prerequisite_fails_a_real_run(
        self,
        shell: str,
        env: dict[str, str],
        tmp_path: Path,
        linux_bin: Path,
    ) -> None:
        """
        Test that a missing system command is fatal and points at the debian Ansible role
        """
        # cc, because lib.sh appends a Homebrew prefix to PATH and the Brewfile installs zsh, git, and curl there
        (linux_bin / 'cc').unlink()
        result = _preflight(shell, env, tmp_path, linux_bin, DEBIAN_RELEASE, dry_run=False)
        assert result.returncode != 0
        assert 'missing system commands: cc' in result.stderr
        assert "'debian' Ansible role"       in result.stderr

    def test_missing_prerequisite_only_warns_in_dry_run(
        self,
        shell: str,
        env: dict[str, str],
        tmp_path: Path,
        linux_bin: Path,
    ) -> None:
        """
        Test that a dry run reports the missing command without failing the preview
        """
        (linux_bin / 'cc').unlink()
        result = _preflight(shell, env, tmp_path, linux_bin, DEBIAN_RELEASE)
        assert result.returncode == 0, result.stderr
        assert 'missing system commands: cc' in result.stderr

    def test_unreadable_os_release_fails(
        self,
        shell: str,
        env: dict[str, str],
        tmp_path: Path,
        linux_bin: Path,
    ) -> None:
        """
        Test that a missing os-release file is fatal with the path in the message
        """
        result = _stage(
            shell,
            '00-preflight.sh',
            {**env, 'DOTFILES_OS': 'linux', 'DOTFILES_OS_RELEASE': str(tmp_path / 'absent'), 'PATH': str(linux_bin)},
        )
        assert result.returncode != 0
        assert f'cannot read {tmp_path / "absent"}' in result.stderr
