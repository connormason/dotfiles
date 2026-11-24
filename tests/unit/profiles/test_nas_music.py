"""
Unit tests for the personal-mac NAS music auto-mount (the ``nas-music`` stow package and the 98-nas-music stage)

Both run against stubbed macOS tools (``mount``, ``nc``, ``security``, ``osascript``, ``launchctl``, ...) that append
their arguments to a call log, so these cover the control flow, not the tools' real behavior on macOS.
"""
from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
PROFILE   = REPO_ROOT / 'profiles' / 'personal-mac'
PACKAGE   = PROFILE / 'stow' / 'nas-music'
SCRIPT    = PACKAGE / '.local' / 'bin' / 'nas-music-mount'
PLIST     = PACKAGE / 'Library' / 'LaunchAgents' / 'com.connormason.nas-music-mount.plist'
STAGE     = PROFILE / 'bootstrap' / '98-nas-music.sh'

# Inherited variables that would leak the developer's own configuration into the tests
_SCRUBBED_VARS: tuple[str, ...] = (
    'BOOTSTRAP_DRY_RUN',
    'BOOTSTRAP_NONINTERACTIVE',
    'DOTFILES_REPO',
    'DOTFILES_LAYER',
    'DOTFILES_OS',
    'DOTFILES_OVERLAYS_FILE',
    'NAS_MUSIC_CONF',
    'NAS_MUSIC_HOST',
    'NAS_MUSIC_SHARE',
    'NAS_MUSIC_USER',
    'XDG_CONFIG_HOME',
)

MOUNTED_LINE = '//connor@nas._smb._tcp.local/media on /Volumes/media (smbfs, nodev, nosuid, mounted by connor)\n'


# ==================================================================================================
# Helpers
# ==================================================================================================


def _stub(bin_dir: Path, name: str, body: str = '') -> None:
    """
    Write an executable stub that logs ``<name> <args>`` to ``$CALLS`` and then runs ``body``

    :param bin_dir: directory placed first on ``PATH``
    :param name: command name to shadow
    :param body: extra shell run after the call is logged (``exit 1`` makes the stub fail)
    """
    path = bin_dir / name
    path.write_text(f'#!/bin/sh\necho "{name} $*" >> "$CALLS"\n{body}\n', encoding='utf-8')
    path.chmod(0o755)


def _calls(env: dict[str, str]) -> list[str]:
    """
    Return the logged stub invocations, in order
    """
    log = Path(env['CALLS'])
    return log.read_text(encoding='utf-8').splitlines() if log.exists() else []


def _mount(shell: str, env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    """
    Run nas-music-mount under the bash interpreter being tested
    """
    return subprocess.run([shell, str(SCRIPT), *args], capture_output=True, text=True, check=False, env=env)


def _stage(shell: str, env: dict[str, str], **extra: str) -> subprocess.CompletedProcess[str]:
    """
    Run the 98-nas-music stage as macOS, under the bash interpreter being tested
    """
    return subprocess.run(
        [shell, str(STAGE)],
        capture_output=True,
        text=True,
        check=False,
        env={
            **env,
            'DOTFILES_REPO': str(REPO_ROOT),
            'DOTFILES_OS':   'darwin',
            **extra,
        },
        stdin=subprocess.DEVNULL,
    )


def _link_package(home: Path) -> None:
    """
    Stand in for 95-dotfiles: put the script and plist where stow would link them
    """
    (home / '.local' / 'bin').mkdir(parents=True)
    (home / 'Library' / 'LaunchAgents').mkdir(parents=True)
    shutil.copy(SCRIPT, home / '.local' / 'bin' / SCRIPT.name)
    shutil.copy(PLIST,  home / 'Library' / 'LaunchAgents' / PLIST.name)


# ==================================================================================================
# Fixtures
# ==================================================================================================


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """
    A throwaway HOME
    """
    path = tmp_path / 'home'
    path.mkdir()
    return path


@pytest.fixture
def env(tmp_path: Path, home: Path) -> dict[str, str]:
    """
    Isolated environment: stubbed tools first on PATH (NAS reachable, Keychain entry present, nothing mounted)
    """
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()

    _stub(bin_dir, 'mount')
    _stub(bin_dir, 'nc')
    _stub(bin_dir, 'security')
    _stub(bin_dir, 'osascript')
    _stub(bin_dir, 'diskutil')
    _stub(bin_dir, 'launchctl')

    return {
        **{key: value for key, value in os.environ.items() if key not in _SCRUBBED_VARS},
        'HOME':                   str(home),
        'PATH':                   f'{bin_dir}:{os.environ["PATH"]}',
        'DOTFILES_OVERLAYS_FILE': str(tmp_path / 'no-overlays'),
        'CALLS':                  str(tmp_path / 'calls.log'),
    }


@pytest.fixture
def conf(home: Path) -> Path:
    """
    A mount.conf in the default location (``$HOME/.config/nas-music``)
    """
    path = home / '.config' / 'nas-music' / 'mount.conf'
    path.parent.mkdir(parents=True)
    path.write_text('NAS_MUSIC_HOST=nas.local\nNAS_MUSIC_SHARE=media\nNAS_MUSIC_USER=connor\n', encoding='utf-8')
    return path


# ==================================================================================================
# Unit tests
# ==================================================================================================


@pytest.mark.usefixtures('conf')
class TestNasMusicMount:
    """
    Tests for the nas-music-mount script
    """
    def test_mounts_when_reachable_and_unmounted(self, shell: str, env: dict[str, str]) -> None:
        """
        Test that an unmounted share on a reachable NAS with a Keychain entry is mounted with the share URL
        """
        result = _mount(shell, env)
        assert result.returncode == 0, result.stderr
        assert 'mounted /Volumes/media' in result.stdout

        osascript = [call for call in _calls(env) if call.startswith('osascript')]
        assert len(osascript) == 1
        assert osascript[0].endswith('smb://connor@nas.local/media')

    def test_noop_when_already_mounted(self, shell: str, env: dict[str, str], tmp_path: Path) -> None:
        """
        Test that an already mounted share is left alone, silently
        """
        _stub(tmp_path / 'bin', 'mount', f"printf '%s' '{MOUNTED_LINE}'")

        result = _mount(shell, env)

        assert result.returncode == 0
        assert result.stdout     == ''
        assert not any(call.startswith('osascript') for call in _calls(env))

    def test_silent_noop_when_nas_unreachable(self, shell: str, env: dict[str, str], tmp_path: Path) -> None:
        """
        Test that an unreachable NAS (away from home) exits cleanly without output or a mount attempt
        """
        _stub(tmp_path / 'bin', 'nc', 'exit 1')

        result = _mount(shell, env)

        assert result.returncode == 0
        assert result.stdout     == ''
        assert result.stderr     == ''
        assert not any(call.startswith('osascript') for call in _calls(env))

    def test_missing_keychain_entry_never_mounts(self, shell: str, env: dict[str, str], tmp_path: Path) -> None:
        """
        Test that a missing Keychain password fails with a hint instead of raising a credentials dialog
        """
        _stub(tmp_path / 'bin', 'security', 'exit 44')

        result = _mount(shell, env)

        assert result.returncode == 1
        assert 'no Keychain password for connor@nas.local' in result.stderr
        assert not any(call.startswith('osascript') for call in _calls(env))

    def test_failed_mount_reports_failure(self, shell: str, env: dict[str, str], tmp_path: Path) -> None:
        """
        Test that a failing osascript mount is logged and returns non-zero
        """
        _stub(tmp_path / 'bin', 'osascript', 'exit 1')

        result = _mount(shell, env)

        assert result.returncode == 1
        assert 'failed to mount smb://connor@nas.local/media' in result.stderr

    def test_missing_user_is_an_error(self, shell: str, env: dict[str, str], conf: Path) -> None:
        """
        Test that a config without NAS_MUSIC_USER fails with a pointer to the bootstrap stage
        """
        conf.write_text('NAS_MUSIC_HOST=nas.local\n', encoding='utf-8')

        result = _mount(shell, env)

        assert result.returncode == 1
        assert 'NAS_MUSIC_USER is not set' in result.stderr

    def test_status_reports_mounted_and_not(self, shell: str, env: dict[str, str], tmp_path: Path) -> None:
        """
        Test that --status exits 1 when unmounted and 0 when mounted
        """
        unmounted = _mount(shell, env, '--status')
        assert unmounted.returncode == 1
        assert unmounted.stdout.strip() == 'not mounted: /Volumes/media'

        _stub(tmp_path / 'bin', 'mount', f"printf '%s' '{MOUNTED_LINE}'")
        mounted = _mount(shell, env, '--status')
        assert mounted.returncode == 0
        assert mounted.stdout.strip() == 'mounted: /Volumes/media'

    def test_unmount_calls_diskutil_only_when_mounted(self, shell: str, env: dict[str, str], tmp_path: Path) -> None:
        """
        Test that --unmount does nothing for an unmounted share and runs diskutil for a mounted one
        """
        _mount(shell, env, '--unmount')
        assert not any(call.startswith('diskutil') for call in _calls(env))

        _stub(tmp_path / 'bin', 'mount', f"printf '%s' '{MOUNTED_LINE}'")
        _mount(shell, env, '--unmount')
        assert 'diskutil unmount /Volumes/media' in _calls(env)

    def test_unknown_flag_prints_usage(self, shell: str, env: dict[str, str]) -> None:
        """
        Test that an unknown flag exits 2 and prints the usage text
        """
        result = _mount(shell, env, '--bogus')

        assert result.returncode == 2
        assert 'Usage: nas-music-mount' in result.stderr


class TestStage:
    """
    Tests for bootstrap stage 98-nas-music
    """
    def test_skipped_on_linux(self, shell: str, env: dict[str, str]) -> None:
        """
        Test that the stage is a clean no-op outside macOS
        """
        result = _stage(shell, env, DOTFILES_OS='linux')

        assert result.returncode == 0, result.stderr
        assert 'skipped (darwin only; this is linux)' in result.stdout

    def test_dry_run_without_config_only_announces(self, shell: str, env: dict[str, str], home: Path) -> None:
        """
        Test that a dry run with no config and no user announces the prompt and writes nothing
        """
        result = _stage(shell, env, BOOTSTRAP_DRY_RUN='1')

        assert result.returncode == 0, result.stderr
        assert 'would prompt for the NAS host, share, and user' in result.stdout
        assert not (home / '.config').exists()
        assert _calls(env) == []

    def test_non_interactive_without_user_skips(self, shell: str, env: dict[str, str], home: Path) -> None:
        """
        Test that an unattended run with no NAS_MUSIC_USER warns and skips instead of blocking on a prompt
        """
        result = _stage(shell, env, BOOTSTRAP_DRY_RUN='0', BOOTSTRAP_NONINTERACTIVE='1')

        assert result.returncode == 0, result.stderr
        assert 'skipping the NAS music mount' in result.stderr
        assert not (home / '.config').exists()

    def test_dry_run_with_user_previews_without_writing(self, shell: str, env: dict[str, str], home: Path) -> None:
        """
        Test that a dry run with the user supplied previews the config write and mutates nothing
        """
        _link_package(home)

        result = _stage(shell, env, BOOTSTRAP_DRY_RUN='1', NAS_MUSIC_USER='connor')

        assert result.returncode == 0, result.stderr
        assert 'user=connor'         in result.stdout
        assert 'launchctl bootstrap' in result.stdout

        assert not (home / '.config' / 'nas-music').exists()
        assert _calls(env) == [call for call in _calls(env) if call.startswith('security')]

    def test_real_run_writes_config_and_loads_agent(self, shell: str, env: dict[str, str], home: Path) -> None:
        """
        Test that a real run writes mount.conf, then boots out, bootstraps, and kickstarts the LaunchAgent
        """
        _link_package(home)

        result = _stage(
            shell,
            env,
            BOOTSTRAP_DRY_RUN='0',
            BOOTSTRAP_NONINTERACTIVE='1',
            NAS_MUSIC_USER='connor',
            NAS_MUSIC_HOST='nas.example',
        )
        assert result.returncode == 0, result.stderr

        conf = (home / '.config' / 'nas-music' / 'mount.conf').read_text(encoding='utf-8')
        assert 'NAS_MUSIC_HOST=nas.example' in conf
        assert 'NAS_MUSIC_SHARE=media'      in conf
        assert 'NAS_MUSIC_USER=connor'      in conf

        launchctl = [call for call in _calls(env) if call.startswith('launchctl')]
        label     = 'com.connormason.nas-music-mount'
        assert [call.split()[1] for call in launchctl] == ['bootout', 'bootstrap', 'kickstart']
        assert launchctl[1].endswith(str(home / 'Library' / 'LaunchAgents' / f'{label}.plist'))

    def test_existing_keychain_entry_is_not_overwritten(self, shell: str, env: dict[str, str], home: Path) -> None:
        """
        Test that a stored Keychain password is kept: the stage only looks it up
        """
        _link_package(home)
        _stage(shell, env, BOOTSTRAP_DRY_RUN='0', BOOTSTRAP_NONINTERACTIVE='1', NAS_MUSIC_USER='connor')

        assert not any(call.startswith('security add-internet-password') for call in _calls(env))

    def test_unlinked_package_is_fatal(self, shell: str, env: dict[str, str]) -> None:
        """
        Test that a real run before 95-dotfiles has linked the package fails with the remedy
        """
        result = _stage(shell, env, BOOTSTRAP_DRY_RUN='0', BOOTSTRAP_NONINTERACTIVE='1', NAS_MUSIC_USER='connor')

        assert result.returncode != 0
        assert 'run bootstrap/bootstrap.sh --only 95-dotfiles first' in result.stderr


class TestPackage:
    """
    Tests for the nas-music stow package files
    """
    def test_marker_limits_package_to_macos(self) -> None:
        """
        Test that the package's .dotfiles-os lists darwin and nothing else
        """
        lines = [
            line.strip()
            for line in (PACKAGE / '.dotfiles-os').read_text(encoding='utf-8').splitlines()
            if line.strip() and not line.lstrip().startswith('#')
        ]
        assert lines == ['darwin']

    def test_plist_runs_the_script_under_its_own_label(self) -> None:
        """
        Test that the plist parses, is labelled like its file, and starts nas-music-mount at load and on an interval
        """
        data = plistlib.loads(PLIST.read_bytes())

        assert data['Label'] == PLIST.stem
        assert data['RunAtLoad'] is True
        assert data['StartInterval'] > 0
        assert '$HOME/.local/bin/nas-music-mount' in data['ProgramArguments'][-1]

    def test_script_and_stage_are_executable(self) -> None:
        """
        Test that the mount script and the stage carry the executable bit
        """
        assert os.access(SCRIPT, os.X_OK)
        assert os.access(STAGE,  os.X_OK)

    @pytest.mark.skipif(not shutil.which('shellcheck'), reason='shellcheck not available')
    def test_shellcheck_clean(self) -> None:
        """
        Test that the script and the stage pass shellcheck
        """
        result = subprocess.run(['shellcheck', str(SCRIPT), str(STAGE)], capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stdout
