"""
Unit tests for the preference snapshot stage (58-defaults-backup) and its restore script
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = REPO_ROOT / 'bootstrap'
DOMAINS   = BOOTSTRAP / 'defaults-domains.txt'

# Stub `defaults`: `read` fails for domains listed in $FAKE_ABSENT, `export` writes a file naming the domain, and every
# call is appended to $FAKE_LOG so tests can assert exactly what ran.
FAKE_DEFAULTS = """#!/bin/sh
echo "defaults $*" >> "$FAKE_LOG"
case "$1" in
read)
    case " $FAKE_ABSENT " in *" $2 "*) exit 1 ;; esac
    exit 0
    ;;
export) echo "plist-of-$2" > "$3" ;;
esac
exit 0
"""
FAKE_SUDO    = '#!/bin/sh\necho "sudo $*" >> "$FAKE_LOG"\nexec "$@"\n'
FAKE_KILLALL = '#!/bin/sh\necho "killall $*" >> "$FAKE_LOG"\n'

_SCRUBBED_VARS: tuple[str, ...] = ('BOOTSTRAP_DRY_RUN', 'DOTFILES_REPO', 'DOTFILES_OS', 'DEFAULTS_BACKUP_DIR')


def _manifest_domains() -> set[str]:
    """
    Return the domains listed in defaults-domains.txt, comments and blanks removed
    """
    lines = (line.split('#', 1)[0].strip() for line in DOMAINS.read_text(encoding='utf-8').splitlines())
    return {line for line in lines if line}


def _written_domains(stage: str) -> set[str]:
    """
    Return the domains a stage targets with `defaults write`, normalising `-g` to NSGlobalDomain
    """
    text = (BOOTSTRAP / stage).read_text(encoding='utf-8')

    # `defaults write [-g] DOMAIN`, optionally behind `run`/`try`/`sudo`; a trailing backslash continues the command
    found = re.findall(r'^\s*(?:(?:run|try|sudo)\s+)*defaults\s+write\s+(\S+)', text, flags=re.MULTILINE)
    return {'NSGlobalDomain' if domain == '-g' else domain for domain in found}


@pytest.fixture
def sandbox(tmp_path: Path) -> dict[str, object]:
    """
    A throwaway HOME, a stub-command directory ahead of PATH, and the call log the stubs append to
    """
    stubs = tmp_path / 'stubs'
    stubs.mkdir()
    for name, body in (('defaults', FAKE_DEFAULTS), ('sudo', FAKE_SUDO), ('killall', FAKE_KILLALL)):
        stub = stubs / name
        stub.write_text(body, encoding='utf-8')
        stub.chmod(0o755)

    log = tmp_path / 'calls.log'
    log.write_text('', encoding='utf-8')

    env = {
        **{key: value for key, value in os.environ.items() if key not in _SCRUBBED_VARS},
        'HOME':                 str(tmp_path / 'home'),
        'PATH':                 f'{stubs}{os.pathsep}{os.environ["PATH"]}',
        'DOTFILES_OS':          'darwin',
        'DEFAULTS_BACKUP_DIR':  str(tmp_path / 'backups'),
        'FAKE_LOG':             str(log),
        'FAKE_ABSENT':          '',
    }
    return {'env': env, 'log': log, 'backups': tmp_path / 'backups'}


def _run(shell: str, script: str, env: object, *args: str) -> subprocess.CompletedProcess[str]:
    """
    Run a bootstrap script under the bash interpreter being tested, with stdin closed
    """
    assert isinstance(env, dict)
    return subprocess.run(
        [shell, str(BOOTSTRAP / script), *args],
        capture_output=True,
        text=True,
        check=False,
        env=env,
        stdin=subprocess.DEVNULL,
    )


def _plain(text: str) -> str:
    """
    Strip ANSI escape sequences, which run() wraps around its [dry-run] marker
    """
    return re.sub(r'\x1b\[[0-9;]*m', '', text)


def _calls(sandbox: dict[str, object]) -> list[str]:
    """
    Return the stub-command calls recorded so far
    """
    log = sandbox['log']
    assert isinstance(log, Path)
    return log.read_text(encoding='utf-8').splitlines()


def _snapshots(sandbox: dict[str, object]) -> list[Path]:
    """
    Return the snapshot directories written under the sandbox backup root, oldest first
    """
    backups = sandbox['backups']
    assert isinstance(backups, Path)
    return sorted(backups.glob('defaults-*'))


class TestDomainManifest:
    """
    Tests for defaults-domains.txt
    """
    @pytest.mark.parametrize('stage', ['60-macos.sh', '96-iterm2.sh'])
    def test_covers_every_domain_the_stage_writes(self, stage: str) -> None:
        """
        Test that each domain a stage writes is snapshotted, so a new `defaults write` cannot escape the backup
        """
        written = _written_domains(stage)
        assert written, f'no defaults write found in {stage}; the extraction pattern is stale'
        assert written <= _manifest_domains(), sorted(written - _manifest_domains())

    def test_has_no_unused_domains(self) -> None:
        """
        Test that every listed domain is written by some stage
        """
        written = _written_domains('60-macos.sh') | _written_domains('96-iterm2.sh')
        assert _manifest_domains() <= written, sorted(_manifest_domains() - written)


class TestDefaultsBackupStage:
    """
    Tests for 58-defaults-backup
    """
    def test_skips_on_linux(self, shell: str, sandbox: dict[str, object]) -> None:
        """
        Test that the stage exits 0 on linux without touching defaults
        """
        env = {**sandbox['env'], 'DOTFILES_OS': 'linux'}  # type: ignore[dict-item]
        result = _run(shell, '58-defaults-backup.sh', env)
        assert result.returncode == 0, result.stderr
        assert 'skipped (darwin only; this is linux)' in result.stdout
        assert _calls(sandbox) == []

    def test_exports_present_domains_and_records_absent_ones(self, shell: str, sandbox: dict[str, object]) -> None:
        """
        Test that present domains are exported and absent ones are only recorded in the manifest
        """
        env = {**sandbox['env'], 'FAKE_ABSENT': 'com.apple.mail'}  # type: ignore[dict-item]
        result = _run(shell, '58-defaults-backup.sh', env)
        assert result.returncode == 0, result.stderr

        (snapshot,) = _snapshots(sandbox)
        manifest = (snapshot / 'MANIFEST.tsv').read_text().splitlines()
        rows = {domain: (file, state) for domain, file, state in (line.split('\t') for line in manifest)}
        loginwindow = '/Library/Preferences/com.apple.loginwindow'
        assert set(rows) == _manifest_domains()
        assert rows['com.apple.mail'] == ('com.apple.mail.plist', 'absent')
        assert rows['com.apple.dock'] == ('com.apple.dock.plist', 'present')
        assert rows[loginwindow][0]   == 'Library_Preferences_com.apple.loginwindow.plist'

        assert (snapshot / 'com.apple.dock.plist').read_text() == 'plist-of-com.apple.dock\n'
        assert not (snapshot / 'com.apple.mail.plist').exists()

    def test_dry_run_writes_no_manifest(self, shell: str, sandbox: dict[str, object]) -> None:
        """
        Test that --dry-run previews the exports without recording or exporting anything
        """
        env = {**sandbox['env'], 'BOOTSTRAP_DRY_RUN': '1'}  # type: ignore[dict-item]
        result = _run(shell, '58-defaults-backup.sh', env)
        assert result.returncode == 0, result.stderr
        assert '[dry-run] defaults export com.apple.dock' in _plain(result.stdout)
        assert not any(call.startswith('defaults export') for call in _calls(sandbox))
        assert _snapshots(sandbox) == []


class TestDefaultsRestore:
    """
    Tests for defaults-restore.sh
    """
    def _backup(self, shell: str, sandbox: dict[str, object], absent: str = '') -> None:
        """
        Take a snapshot through the real stage, then clear the call log
        """
        env = {**sandbox['env'], 'FAKE_ABSENT': absent}  # type: ignore[dict-item]
        assert _run(shell, '58-defaults-backup.sh', env).returncode == 0
        log = sandbox['log']
        assert isinstance(log, Path)
        log.write_text('', encoding='utf-8')

    def test_imports_present_deletes_absent_and_uses_sudo_for_file_domains(
        self, shell: str, sandbox: dict[str, object]
    ) -> None:
        """
        Test the three restore actions: import, delete for absent domains, and sudo for /Library domains
        """
        self._backup(shell, sandbox, absent='com.apple.mail')

        result = _run(shell, 'defaults-restore.sh', sandbox['env'])
        assert result.returncode == 0, result.stderr

        calls = _calls(sandbox)
        (snapshot,) = _snapshots(sandbox)
        assert f'defaults import com.apple.dock {snapshot}/com.apple.dock.plist' in calls
        assert 'defaults delete com.apple.mail'                                  in calls
        assert any(c.startswith('sudo defaults import /Library/Preferences/com.apple.loginwindow ') for c in calls)
        assert {'killall Dock', 'killall Finder', 'killall SystemUIServer'} <= set(calls)

    def test_defaults_to_the_oldest_snapshot(self, shell: str, sandbox: dict[str, object]) -> None:
        """
        Test that the pristine, oldest snapshot is restored unless one is named
        """
        backups = sandbox['backups']
        assert isinstance(backups, Path)
        for name in ('defaults-20260101-000000', 'defaults-20260202-000000'):
            (backups / name).mkdir(parents=True)
            (backups / name / 'MANIFEST.tsv').write_text('com.apple.dock\tcom.apple.dock.plist\tpresent\n')

        result = _run(shell, 'defaults-restore.sh', sandbox['env'])
        assert result.returncode == 0, result.stderr
        oldest = backups / 'defaults-20260101-000000'
        assert f'defaults import com.apple.dock {oldest}/com.apple.dock.plist' in _calls(sandbox)

    def test_dies_without_snapshots(self, shell: str, sandbox: dict[str, object]) -> None:
        """
        Test that restore fails loudly instead of doing nothing when no snapshot exists
        """
        result = _run(shell, 'defaults-restore.sh', sandbox['env'])
        assert result.returncode != 0
        assert 'no snapshots' in result.stderr

    def test_dry_run_changes_nothing(self, shell: str, sandbox: dict[str, object]) -> None:
        """
        Test that --dry-run prints the restore commands without running them
        """
        self._backup(shell, sandbox)

        result = _run(shell, 'defaults-restore.sh', sandbox['env'], '--dry-run')
        assert result.returncode == 0, result.stderr
        assert '[dry-run] defaults import com.apple.dock' in _plain(result.stdout)
        assert _calls(sandbox) == []
