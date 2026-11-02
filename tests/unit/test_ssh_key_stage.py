"""
Unit tests for bootstrap/20-ssh-key.sh (stub ssh and ssh-keygen; isolated HOME)
"""
from __future__ import annotations

import os
import pty
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
STAGE     = REPO_ROOT / 'bootstrap' / '20-ssh-key.sh'

_SCRUBBED_VARS: tuple[str, ...] = (
    'BOOTSTRAP_CHANGES_FILE',
    'BOOTSTRAP_DRY_RUN',
    'BOOTSTRAP_NONINTERACTIVE',
    'DOTFILES_BREW_PREFIXES',
    'DOTFILES_LAYER',
    'DOTFILES_OS',
    'DOTFILES_REPO',
    'XDG_CONFIG_HOME',
)

DENIED  = 'printf "git@github.com: Permission denied (publickey).\\n" >&2\nexit 255\n'
WORKING = 'printf "Hi tester! You have successfully authenticated.\\n" >&2\nexit 1\n'


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    """
    Isolated HOME, no overlays, a ledger, and stubs: ssh (auth denied) and ssh-keygen (writes a fake key pair)
    """
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    (bin_dir / 'ssh').write_text(f'#!/bin/sh\n{DENIED}', encoding='utf-8')
    (bin_dir / 'ssh-keygen').write_text(
        '#!/bin/sh\n'
        'while [ $# -gt 0 ]; do\n'
        '    if [ "$1" = "-f" ]; then key="$2"; fi\n'
        '    shift\n'
        'done\n'
        'echo private > "$key"\n'
        'echo "ssh-ed25519 AAAATEST tester@host" > "$key.pub"\n',
        encoding='utf-8',
    )
    for stub in bin_dir.iterdir():
        stub.chmod(0o755)

    home = tmp_path / 'home'
    home.mkdir()
    return {
        **{key: value for key, value in os.environ.items() if key not in _SCRUBBED_VARS},
        'HOME':                   str(home),
        'PATH':                   f'{bin_dir}:{os.environ["PATH"]}',
        'DOTFILES_OVERLAYS_FILE': str(tmp_path / 'no-overlays'),
        'BOOTSTRAP_DRY_RUN':      '0',
        'BOOTSTRAP_CHANGES_FILE': str(tmp_path / 'ledger'),
    }


def _stage(shell: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """
    Run the stage with stdin closed (an unattended run)
    """
    return subprocess.run(
        [shell, str(STAGE)],
        capture_output=True,
        text=True,
        check=False,
        env=env,
        stdin=subprocess.DEVNULL,
        timeout=60,
    )


def _ledger(env: dict[str, str]) -> list[str]:
    """
    Lines recorded in the change ledger (empty when none were)
    """
    path = Path(env['BOOTSTRAP_CHANGES_FILE'])
    return path.read_text(encoding='utf-8').splitlines() if path.exists() else []


class TestUnattendedSshKey:
    """
    Tests for 20-ssh-key without a human at the keyboard
    """
    @pytest.mark.parametrize('flag', ['1', None])
    def test_generates_key_warns_and_continues(self, shell: str, env: dict[str, str], flag: str | None) -> None:
        """
        Test that failed GitHub auth generates a key, prints it, warns, and exits 0 (flag set or stdin closed)
        """
        if flag is not None:
            env['BOOTSTRAP_NONINTERACTIVE'] = flag

        result = _stage(shell, env)
        assert result.returncode == 0, result.stderr

        key = Path(env['HOME']) / '.ssh' / 'id_ed25519'
        assert key.exists()
        assert 'ssh-ed25519 AAAATEST' in result.stdout
        assert 'non-interactive run: continuing without a GitHub-registered key' in result.stderr
        assert _ledger(env) == [f'generated SSH key {key}']

    def test_existing_key_is_kept_and_not_counted(self, shell: str, env: dict[str, str]) -> None:
        """
        Test that an existing key is neither regenerated nor recorded as a change
        """
        ssh_dir = Path(env['HOME']) / '.ssh'
        ssh_dir.mkdir()
        (ssh_dir / 'id_ed25519').write_text('mine\n', encoding='utf-8')
        (ssh_dir / 'id_ed25519.pub').write_text('ssh-ed25519 AAAAMINE me@host\n', encoding='utf-8')

        result = _stage(shell, env)
        assert result.returncode == 0, result.stderr
        assert (ssh_dir / 'id_ed25519').read_text(encoding='utf-8') == 'mine\n'
        assert _ledger(env) == []

    def test_working_auth_changes_nothing(self, shell: str, env: dict[str, str], tmp_path: Path) -> None:
        """
        Test that working GitHub auth exits early without generating or recording anything
        """
        (tmp_path / 'bin' / 'ssh').write_text(f'#!/bin/sh\n{WORKING}', encoding='utf-8')

        result = _stage(shell, env)
        assert result.returncode == 0, result.stderr
        assert 'already works' in result.stdout
        assert not (Path(env['HOME']) / '.ssh' / 'id_ed25519').exists()
        assert _ledger(env) == []


class TestInteractiveSshKey:
    """
    Tests for 20-ssh-key with a terminal on stdin
    """
    def test_declining_still_fails(self, shell: str, env: dict[str, str]) -> None:
        """
        Test that answering no at the terminal keeps the existing failure and re-run hint
        """
        primary, secondary = pty.openpty()
        try:
            os.write(primary, b'n\n')
            result = subprocess.run(
                [shell, str(STAGE)],
                stdin=secondary,
                capture_output=True,
                text=True,
                check=False,
                env=env,
                timeout=60,
            )
        finally:
            os.close(primary)
            os.close(secondary)

        assert result.returncode != 0
        assert 'register the SSH key, then re-run --from 20-ssh-key' in result.stderr
