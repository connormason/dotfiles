"""
Unit tests for the Homebrew installer checksum gate of bootstrap/50-brew.sh (sandboxed: stub curl, stub installer)
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
STAGE     = REPO_ROOT / 'bootstrap' / '50-brew.sh'

# Stands in for the downloaded Homebrew installer: records that it ran and installs a stub brew into the sandbox prefix
INSTALLER_PAYLOAD = (
    '#!/bin/bash\n'
    'touch "$INSTALLER_MARKER"\n'
    'mkdir -p "$SANDBOX_PREFIX/bin"\n'
    'printf "#!/bin/sh\\nexit 1\\n" > "$SANDBOX_PREFIX/bin/brew"\n'
    'chmod 755 "$SANDBOX_PREFIX/bin/brew"\n'
)

# The pinned digest assignment in the stage; group 1 is the digest
PINNED_SHA = re.compile(r'^BREW_INSTALLER_SHA256="([0-9a-f]{64})"', re.MULTILINE)

# Replaces ensure_brew_on_path so the stage never discovers a real Homebrew in /opt/homebrew or /usr/local
ENV_OVERRIDE = (
    'ensure_brew_on_path() {\n'
    '    PATH="$PATH:$SANDBOX_PREFIX/bin"\n'
    '    export PATH\n'
    '}\n'
)


@dataclass
class Sandbox:
    """
    A hermetic run environment for the 50-brew stage plus the paths its stubs write to
    """
    env:          dict[str, str]
    stage:        Path
    marker:       Path
    sudo_marker:  Path
    curl_args:    Path
    tmpdir:       Path
    payload:      bytes


@pytest.fixture
def sandbox(tmp_path: Path) -> Sandbox:
    """
    Copy the real stage and lib.sh into a throwaway base layer; PATH holds only stub curl/sudo plus the system dirs, so
    neither the real Homebrew, the real HOME, nor the real network is reachable
    """
    stages = tmp_path / 'base' / 'bootstrap'
    stages.mkdir(parents=True)
    (stages / 'lib.sh').write_bytes((REPO_ROOT / 'bootstrap' / 'lib.sh').read_bytes())
    stage = stages / '50-brew.sh'
    stage.write_bytes(STAGE.read_bytes())

    overlay = tmp_path / 'overlay'
    (overlay / 'bootstrap').mkdir(parents=True)
    (overlay / 'bootstrap' / 'env.sh').write_text(ENV_OVERRIDE, encoding='utf-8')
    registry = tmp_path / 'overlays'
    registry.write_text(f'{overlay}\n', encoding='utf-8')

    payload = tmp_path / 'payload'
    payload.write_text(INSTALLER_PAYLOAD, encoding='utf-8')

    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    curl_args = tmp_path / 'curl-args'
    sudo_marker = tmp_path / 'sudo-called'
    (bin_dir / 'curl').write_text(
        '#!/bin/sh\n'
        f'printf "%s\\n" "$*" > "{curl_args}"\n'
        'while [ $# -gt 0 ]; do\n'
        '    if [ "$1" = "-o" ]; then out="$2"; fi\n'
        '    shift\n'
        'done\n'
        f'cat "{payload}" > "$out"\n',
        encoding='utf-8',
    )
    (bin_dir / 'sudo').write_text(f'#!/bin/sh\ntouch "{sudo_marker}"\nexit 1\n', encoding='utf-8')
    for stub in bin_dir.iterdir():
        stub.chmod(0o755)

    tmpdir = tmp_path / 'tmp'
    tmpdir.mkdir()
    marker = tmp_path / 'installer-ran'

    scrubbed: tuple[str, ...] = (
        'BOOTSTRAP_DRY_RUN',
        'DOTFILES_REPO',
        'DOTFILES_LAYER',
        'DOTFILES_BREW_PREFIXES',
        'XDG_CONFIG_HOME',
    )
    env = {
        **{key: value for key, value in os.environ.items() if key not in scrubbed},
        'HOME':                   str(tmp_path / 'home'),
        'PATH':                   f'{bin_dir}:/usr/bin:/bin',
        'TMPDIR':                 str(tmpdir),
        'DOTFILES_OVERLAYS_FILE': str(registry),
        'SANDBOX_PREFIX':         str(tmp_path / 'prefix'),
        'INSTALLER_MARKER':       str(marker),
    }
    return Sandbox(
        env=env,
        stage=stage,
        marker=marker,
        sudo_marker=sudo_marker,
        curl_args=curl_args,
        tmpdir=tmpdir,
        payload=payload.read_bytes(),
    )


def _run(shell: str, box: Sandbox) -> subprocess.CompletedProcess[str]:
    """
    Run the sandboxed 50-brew stage under the bash interpreter being tested, with stdin closed
    """
    return subprocess.run(
        [shell, str(box.stage)],
        capture_output=True,
        text=True,
        check=False,
        env=box.env,
        stdin=subprocess.DEVNULL,
    )


class TestBrewInstallerChecksum:
    """
    Tests for the checksum gate in front of the Homebrew installer
    """
    def test_matching_checksum_runs_installer(self, shell: str, sandbox: Sandbox) -> None:
        """
        Test that an installer whose SHA-256 equals the pin is executed and the temp file is cleaned up
        """
        # The pin cannot be satisfied by chosen bytes, so the copy pins the stub payload's real digest instead; shasum
        # and the comparison under test are untouched
        text = sandbox.stage.read_text(encoding='utf-8')
        assert PINNED_SHA.search(text)

        digest = hashlib.sha256(sandbox.payload).hexdigest()
        sandbox.stage.write_text(PINNED_SHA.sub(f'BREW_INSTALLER_SHA256="{digest}"', text), encoding='utf-8')

        result = _run(shell, sandbox)
        assert result.returncode == 0, result.stderr
        assert 'installer checksum verified' in result.stdout
        assert 'raw.githubusercontent.com/Homebrew/install/HEAD/install.sh' in sandbox.curl_args.read_text('utf-8')
        assert sandbox.marker.exists()
        assert not sandbox.sudo_marker.exists()
        assert list(sandbox.tmpdir.iterdir()) == []

    def test_mismatched_checksum_aborts_without_running_installer(self, shell: str, sandbox: Sandbox) -> None:
        """
        Test that a download whose SHA-256 differs from the pin exits non-zero, never executes it and removes it
        """
        pinned = PINNED_SHA.search(sandbox.stage.read_text(encoding='utf-8'))
        assert pinned
        assert hashlib.sha256(sandbox.payload).hexdigest() != pinned.group(1)

        result = _run(shell, sandbox)
        assert result.returncode != 0
        assert 'Homebrew installer checksum mismatch' in result.stderr
        assert f'expected: {pinned.group(1)}' in result.stderr
        assert f'actual:   {hashlib.sha256(sandbox.payload).hexdigest()}' in result.stderr
        assert 'installer checksum verified' not in result.stdout
        assert not sandbox.marker.exists()
        assert not sandbox.sudo_marker.exists()
        assert list(sandbox.tmpdir.iterdir()) == []
