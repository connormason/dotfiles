"""
Behavioral tests for the backup role: its tasks, its backup script, and its restic wrapper

The tasks run for real with ansible-playbook against localhost (``ansible_become=false``, temporary destinations); the
scripts run for real with stub ``zfs``, ``restic`` and ``findmnt`` binaries on PATH that record their calls. See
CLAUDE-LESSONS.md, "String-matching Ansible YAML is not verification: run the role".
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.unit.roles.test_alerting_roles import ROLES
from tests.unit.roles.test_alerting_roles import _run_tasks
from tests.unit.roles.test_alerting_roles import needs_ansible

BACKUP_ROLE = ROLES / 'backup'
SCRIPT      = BACKUP_ROLE / 'files' / 'restic-backup'
WRAPPER     = BACKUP_ROLE / 'files' / 'restic-nas'

TaskDict = dict[str, Any]  # Any: heterogeneous, yaml-loaded task structure

# Fake credentials: the tests assert that these never reach Ansible's output
SECRET_KEY  = 'K0054b2s3cretkeyvalue'          # pragma: allowlist secret
SECRET_PW   = 'correct-horse-battery-staple'   # pragma: allowlist secret
ROTATED_KEY = 'K00rotatedkeyvalue'             # pragma: allowlist secret
ROTATED_PW  = 'rotated-pw'                     # pragma: allowlist secret

# Tasks that write files and need no root, systemd or apt, in role order
FILE_TASKS = [
    'Create the restic configuration directory',
    'Store the restic repository password',
    'Render the restic environment file',
    'Install the backup script',
    'Install the restic wrapper',
    'Install the backup service',
    'Install the backup timer',
]


def _main_tasks() -> list[TaskDict]:
    """
    Load the role's task file
    """
    return yaml.safe_load((BACKUP_ROLE / 'tasks' / 'main.yml').read_text(encoding='utf-8'))


def _block_tasks() -> list[TaskDict]:
    """
    Load the tasks inside the role's ``when: backup_b2_bucket`` block
    """
    return next(task['block'] for task in _main_tasks() if 'block' in task)


def _runnable(task: TaskDict) -> TaskDict:
    """
    Adapt a role task to run outside the role as a non-root user

    Sources become absolute (the play is not in the role), and ``owner``/``group`` are dropped because chown to root
    fails for an unprivileged user. Ownership is pinned by a structural test instead.
    """
    adapted = {key: value for key, value in task.items() if key not in {'notify', 'become'}}
    for module in ('ansible.builtin.copy', 'ansible.builtin.template', 'ansible.builtin.file'):
        if module in adapted:
            args = {key: value for key, value in adapted[module].items() if key not in {'owner', 'group'}}
            if 'src' in args:
                subdir = 'files' if module.endswith('copy') else 'templates'
                args['src'] = str(BACKUP_ROLE / subdir / args['src'])
            adapted[module] = args
    return adapted


def _file_tasks() -> list[TaskDict]:
    """
    The file-writing tasks, runnable in a scratch play
    """
    by_name = {task['name']: task for task in _block_tasks()}
    return [_runnable(by_name[name]) for name in FILE_TASKS]


def _vars(tmp_path: Path, **overrides: Any) -> list[str]:
    """
    Build the ``-e`` argument (JSON, so quotes, newlines and lists survive) that points the role at scratch paths and
    gives it complete settings
    """
    (tmp_path / 'bin').mkdir(exist_ok=True)
    (tmp_path / 'units').mkdir(exist_ok=True)
    values = {
        'backup_b2_bucket':           'nas-test-bucket',
        'backup_b2_account_id':       '0012345keyid',
        'backup_b2_account_key':      SECRET_KEY,
        'backup_repository_password': SECRET_PW,
        'backup_config_dir':          str(tmp_path / 'etc-restic'),
        'backup_script_path':         str(tmp_path / 'bin' / 'restic-backup'),
        'backup_wrapper_path':        str(tmp_path / 'bin' / 'restic-nas'),
        'backup_unit_dir':            str(tmp_path / 'units'),
        **overrides,
    }
    return ['-e', json.dumps(values)]


def _mode(path: Path) -> int:
    """
    Return a file's permission bits
    """
    return stat.S_IMODE(path.stat().st_mode)


@needs_ansible
class TestBackupTasks:
    """
    Real-run tests of the file-writing tasks in roles/backup/tasks/main.yml
    """
    def test_writes_private_files_then_converges(self, tmp_path: Path) -> None:
        """
        Test that the first run writes everything with private secrets, and a second run changes nothing
        """
        code, output = _run_tasks(tmp_path, 'backup', _file_tasks(), *_vars(tmp_path))
        assert code == 0, output
        assert 'changed=7' in output, output

        config = tmp_path / 'etc-restic'
        assert _mode(config)               == 0o700
        assert _mode(config / 'password')  == 0o600
        assert _mode(config / 'restic.env') == 0o600
        assert (config / 'password').read_text(encoding='utf-8') == SECRET_PW
        assert os.access(tmp_path / 'bin' / 'restic-backup', os.X_OK)
        assert os.access(tmp_path / 'bin' / 'restic-nas', os.X_OK)

        code, output = _run_tasks(tmp_path, 'backup', _file_tasks(), *_vars(tmp_path))
        assert code == 0, output
        assert 'changed=0' in output, output

    def test_environment_file_names_the_repository_and_credentials(self, tmp_path: Path) -> None:
        """
        Test that restic.env carries the b2: repository URL, the password file path and both B2 values
        """
        _run_tasks(tmp_path, 'backup', _file_tasks(), *_vars(tmp_path))
        lines = (tmp_path / 'etc-restic' / 'restic.env').read_text(encoding='utf-8').splitlines()

        assert "RESTIC_REPOSITORY='b2:nas-test-bucket:restic'"                        in lines
        assert f"RESTIC_PASSWORD_FILE='{tmp_path / 'etc-restic' / 'password'}'"      in lines
        assert "B2_ACCOUNT_ID='0012345keyid'"                                        in lines
        assert f"B2_ACCOUNT_KEY='{SECRET_KEY}'"                                      in lines

    def test_drift_is_repaired(self, tmp_path: Path) -> None:
        """
        Test that a loosened mode and an edited script are put back by the next run
        """
        _run_tasks(tmp_path, 'backup', _file_tasks(), *_vars(tmp_path))
        env = tmp_path / 'etc-restic' / 'restic.env'
        env.chmod(0o644)
        (tmp_path / 'bin' / 'restic-backup').write_text('#!/bin/sh\nexit 0\n', encoding='utf-8')

        code, output = _run_tasks(tmp_path, 'backup', _file_tasks(), *_vars(tmp_path))

        assert code == 0, output
        assert 'changed=2' in output, output
        assert _mode(env) == 0o600
        assert (tmp_path / 'bin' / 'restic-backup').read_text(encoding='utf-8') == SCRIPT.read_text(encoding='utf-8')

    @pytest.mark.parametrize('extra', [[], ['--check']])
    def test_secrets_never_reach_the_output(self, tmp_path: Path, extra: list[str]) -> None:
        """
        Test that --diff, alone and with --check over files holding old secrets, prints no key or password
        """
        _run_tasks(tmp_path, 'backup', _file_tasks(), *_vars(tmp_path))
        rotated = _vars(tmp_path, backup_b2_account_key=ROTATED_KEY, backup_repository_password=ROTATED_PW)

        code, output = _run_tasks(tmp_path, 'backup', _file_tasks(), '--diff', *extra, *rotated)

        assert code == 0, output
        for secret in (SECRET_KEY, SECRET_PW, ROTATED_KEY, ROTATED_PW):
            assert secret not in output

    def test_unset_bucket_warns_and_writes_nothing(self, tmp_path: Path) -> None:
        """
        Test that the whole task file, run with no bucket, prints the warning and touches nothing
        """
        tasks = [{'ansible.builtin.import_tasks': str(BACKUP_ROLE / 'tasks' / 'main.yml')}]
        args  = _vars(tmp_path, backup_b2_bucket='')

        code, output = _run_tasks(tmp_path, 'backup', tasks, *args)

        assert code == 0, output
        assert 'backup_b2_bucket is not set' in output
        assert not (tmp_path / 'etc-restic').exists()
        assert not any((tmp_path / 'bin').iterdir())

    @pytest.mark.parametrize(
        'override',
        [
            {'backup_b2_account_id': ''},
            {'backup_b2_account_key': ''},
            {'backup_repository_password': ''},
            {'backup_b2_account_key': "bad'quote"},
            {'backup_b2_account_id': 'bad\nnewline'},
            {'backup_paths': ['/storage/with space']},
            {'backup_paths': []},
        ],
    )
    def test_incomplete_settings_fail_before_anything_is_written(
        self,
        tmp_path: Path,
        override: dict[str, Any],
    ) -> None:
        """
        Test that a set bucket with missing or unsafe settings fails with an explanation and writes nothing
        """
        tasks = [{'ansible.builtin.import_tasks': str(BACKUP_ROLE / 'tasks' / 'main.yml')}]
        args  = _vars(tmp_path, **override)

        code, output = _run_tasks(tmp_path, 'backup', tasks, *args)

        assert code != 0
        assert 'incomplete or unusable' in output, output
        assert not (tmp_path / 'etc-restic').exists()
        assert SECRET_KEY not in output
        assert SECRET_PW  not in output

    def test_units_carry_the_failure_alert_schedule_and_retention(self, tmp_path: Path) -> None:
        """
        Test that the rendered service alerts on failure, and the timer is persistent with the nightly schedule
        """
        _run_tasks(tmp_path, 'backup', _file_tasks(), *_vars(tmp_path))
        service = (tmp_path / 'units' / 'restic-backup.service').read_text(encoding='utf-8')
        timer   = (tmp_path / 'units' / 'restic-backup.timer').read_text(encoding='utf-8')

        assert 'OnFailure=nas-notify-failure@%n.service'                       in service
        assert f"EnvironmentFile={tmp_path / 'etc-restic' / 'restic.env'}"     in service
        assert 'Environment="BACKUP_PATHS=/storage/media/config /storage/backups"' in service
        assert 'Environment=BACKUP_ZFS_DATASET=storage'  in service  # pragma: allowlist secret
        for setting in ('BACKUP_KEEP_DAILY=14', 'BACKUP_KEEP_WEEKLY=8', 'BACKUP_KEEP_MONTHLY=12'):
            assert f'Environment={setting}' in service
        assert 'OnCalendar=*-*-* 02:30:00' in timer
        assert 'Persistent=true'           in timer
        assert 'WantedBy=timers.target'    in timer

    def test_units_pass_systemd_verify(self, tmp_path: Path) -> None:
        """
        Test that systemd-analyze accepts the rendered service and timer
        """
        if not (Path('/usr/bin/systemd-analyze').exists() or Path('/bin/systemd-analyze').exists()):
            pytest.skip('systemd-analyze not available')
        _run_tasks(tmp_path, 'backup', _file_tasks(), *_vars(tmp_path))
        units = tmp_path / 'units'

        result = subprocess.run(
            ['systemd-analyze', 'verify', str(units / 'restic-backup.service'), str(units / 'restic-backup.timer')],
            capture_output=True,
            text=True,
            check=False,
        )
        problems = [line for line in result.stderr.splitlines() if 'nas-notify-failure' not in line]
        assert result.returncode == 0 or not problems, result.stderr


class TestBackupRoleWiring:
    """
    Structural tests for what the real-run tests cannot reach (root-owned paths, handlers, systemd)
    """
    def test_secret_files_are_root_private_and_not_logged(self) -> None:
        """
        Test that the password and environment files are root 0600 with diff and no_log off
        """
        by_name = {task['name']: task for task in _block_tasks()}
        for name, module in (
            ('Store the restic repository password', 'ansible.builtin.copy'),
            ('Render the restic environment file',  'ansible.builtin.template'),
        ):
            task = by_name[name]
            assert task[module]['mode']  == '0600'
            assert task[module]['owner'] == 'root'
            assert task['diff']   is False
            assert task['no_log'] is True

    def test_configuration_directory_is_root_only(self) -> None:
        """
        Test that /etc/restic is 0700 root
        """
        task = next(t for t in _block_tasks() if t['name'] == 'Create the restic configuration directory')
        assert task['ansible.builtin.file']['mode']  == '0700'
        assert task['ansible.builtin.file']['owner'] == 'root'

    def test_notified_handlers_exist_in_this_role(self) -> None:
        """
        Test that every notified handler is defined by this role (handlers are play-global; --tags must stand alone)
        """
        handlers = {h['name'] for h in yaml.safe_load((BACKUP_ROLE / 'handlers' / 'main.yml').read_text('utf-8'))}
        notified: set[str] = set()
        for task in _block_tasks():
            value = task.get('notify', [])
            notified |= {value} if isinstance(value, str) else set(value)

        assert notified
        assert notified <= handlers

    def test_timer_is_enabled_after_the_units_are_loaded(self) -> None:
        """
        Test that handlers are flushed (daemon-reload) between installing the units and enabling the timer
        """
        names = [task['name'] for task in _block_tasks()]
        assert (
            names.index('Install the backup timer')
            < names.index('Reload systemd before enabling the timer')
            < names.index('Enable and start the backup timer')
        )


# ==================================================================================================
# The backup script and the restic wrapper
# ==================================================================================================

FAKE_ZFS = """#!/usr/bin/env bash
echo "zfs $*" >> "$FAKE_STATE/calls.log"
case "$1" in
    list)     [[ -e "$FAKE_STATE/snap-${*: -1}" ]] ;;
    snapshot) touch "$FAKE_STATE/snap-${*: -1}" ;;
    destroy)  rm -f "$FAKE_STATE/snap-${*: -1}" ;;
    *)        exit 2 ;;
esac
"""

# findmnt -n -o TARGET,FSTYPE -T PATH: the first line of $FAKE_STATE/mounts whose prefix matches wins
FAKE_FINDMNT = """#!/usr/bin/env bash
path="${*: -1}"
while read -r prefix mountpoint fstype; do
    if [[ "$path" == "$prefix" || "$path" == "$prefix"/* ]]; then
        echo "$mountpoint $fstype"
        exit 0
    fi
done < "$FAKE_STATE/mounts"
exit 1
"""

FAKE_RESTIC = """#!/usr/bin/env bash
echo "restic $*" >> "$FAKE_STATE/calls.log"
case "$1" in
    cat)    exit "${FAKE_RESTIC_CAT_RC:-0}" ;;
    backup) ls "$FAKE_STATE"/snap-* > "$FAKE_STATE/snapshots-during-backup" 2>/dev/null
            exit "${FAKE_RESTIC_BACKUP_RC:-0}" ;;
    forget) exit 0 ;;
    *)      exit 0 ;;
esac
"""


class ScriptEnv:
    """
    A scratch pool layout with stub binaries, and a runner for the backup script
    """
    def __init__(self, tmp_path: Path) -> None:
        """
        Build the stubs, the mount table, and snapshot directories for two datasets

        :param tmp_path: scratch directory
        """
        self.state = tmp_path / 'state'
        self.pool  = tmp_path / 'storage'
        bindir     = tmp_path / 'stub-bin'
        self.state.mkdir()
        bindir.mkdir()

        for name, body in (('zfs', FAKE_ZFS), ('findmnt', FAKE_FINDMNT), ('restic', FAKE_RESTIC)):
            stub = bindir / name
            stub.write_text(body, encoding='utf-8')
            stub.chmod(0o755)

        snapshot = '.zfs/snapshot/restic-backup'
        (self.pool / 'media' / 'config').mkdir(parents=True)
        (self.pool / 'backups').mkdir()
        (self.pool / snapshot / 'media' / 'config').mkdir(parents=True)
        (self.pool / 'backups' / snapshot).mkdir(parents=True)

        # storage/backups is its own dataset, so it is listed first (longest prefix)
        self.write_mounts(
            f'{self.pool}/backups {self.pool}/backups zfs',
            f'{self.pool} {self.pool} zfs',
        )
        self.env = {
            'PATH':                bindir.as_posix() + ':' + os.environ['PATH'],
            'FAKE_STATE':          str(self.state),
            'RESTIC_REPOSITORY':   'b2:bucket:restic',
            'BACKUP_ZFS_DATASET':  'storage',
            'BACKUP_PATHS':        f'{self.pool}/media/config {self.pool}/backups',
            'BACKUP_KEEP_DAILY':   '14',
            'BACKUP_KEEP_WEEKLY':  '8',
            'BACKUP_KEEP_MONTHLY': '12',
        }

    def write_mounts(self, *lines: str) -> None:
        """
        Replace the stub findmnt table
        """
        (self.state / 'mounts').write_text('\n'.join(lines) + '\n', encoding='utf-8')

    def run(self, **env: str) -> subprocess.CompletedProcess[str]:
        """
        Run the backup script with the stubs, returning the finished process
        """
        return subprocess.run(
            [str(SCRIPT)],
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, **self.env, **env},
            timeout=60,
        )

    def calls(self) -> list[str]:
        """
        Return the recorded zfs and restic invocations in order
        """
        log = self.state / 'calls.log'
        return log.read_text(encoding='utf-8').splitlines() if log.exists() else []

    def snapshot_exists(self) -> bool:
        """
        Whether the stub pool currently holds the backup snapshot
        """
        return (self.state / 'snap-storage@restic-backup').exists()


@pytest.fixture
def script_env(tmp_path: Path) -> ScriptEnv:
    """
    Provide a scratch pool layout with stub zfs, restic and findmnt binaries
    """
    return ScriptEnv(tmp_path)


class TestBackupScript:
    """
    Tests for roles/backup/files/restic-backup
    """
    def test_backs_up_snapshot_paths_never_live_paths(self, script_env: ScriptEnv) -> None:
        """
        Test that restic is given the .zfs/snapshot paths of each dataset, in the right order, and prunes afterwards
        """
        result = script_env.run()
        pool   = script_env.pool
        snap   = '.zfs/snapshot/restic-backup'

        assert result.returncode == 0, result.stderr
        assert script_env.calls() == [
            'restic cat config',
            'zfs list -H -t snapshot -o name storage@restic-backup',
            'zfs snapshot -r storage@restic-backup',
            f'restic backup --tag zfs-snapshot {pool}/{snap}/media/config {pool}/backups/{snap}',
            'restic forget --prune --keep-daily 14 --keep-weekly 8 --keep-monthly 12',
            'zfs list -H -t snapshot -o name storage@restic-backup',
            'zfs destroy -r storage@restic-backup',
        ]

    def test_snapshot_exists_during_the_backup_and_is_gone_after(self, script_env: ScriptEnv) -> None:
        """
        Test that the snapshot is present while restic reads and destroyed once the run ends
        """
        script_env.run()

        during = (script_env.state / 'snapshots-during-backup').read_text(encoding='utf-8')
        assert 'snap-storage@restic-backup' in during
        assert not script_env.snapshot_exists()

    def test_failed_backup_skips_prune_but_still_destroys_the_snapshot(self, script_env: ScriptEnv) -> None:
        """
        Test that a restic backup failure propagates, never prunes, and leaves no snapshot behind
        """
        result = script_env.run(FAKE_RESTIC_BACKUP_RC='3')

        assert result.returncode == 3
        assert not any(call.startswith('restic forget') for call in script_env.calls())
        assert not script_env.snapshot_exists()

    def test_stale_snapshot_from_an_interrupted_run_is_replaced(self, script_env: ScriptEnv) -> None:
        """
        Test that a leftover snapshot is destroyed before the new one is taken
        """
        (script_env.state / 'snap-storage@restic-backup').touch()

        result = script_env.run()
        calls  = script_env.calls()

        assert result.returncode == 0, result.stderr
        assert 'removing stale snapshot' in result.stdout
        destroy  = calls.index('zfs destroy -r storage@restic-backup')
        snapshot = calls.index('zfs snapshot -r storage@restic-backup')
        assert destroy < snapshot
        assert not script_env.snapshot_exists()

    def test_path_outside_zfs_is_refused_without_snapshot_or_backup(self, script_env: ScriptEnv) -> None:
        """
        Test that a path on another filesystem stops the run instead of being backed up live
        """
        script_env.write_mounts(
            f'{script_env.pool}/backups {script_env.pool}/backups zfs',
            f'{script_env.pool} / ext4',
        )

        result = script_env.run()

        assert result.returncode == 1
        assert 'not ZFS' in result.stderr
        assert not any(call.startswith(('zfs snapshot', 'restic backup')) for call in script_env.calls())

    def test_uninitialised_repository_stops_before_snapshotting(self, script_env: ScriptEnv) -> None:
        """
        Test that an unreachable or uninitialised repository fails with the init hint and takes no snapshot
        """
        result = script_env.run(FAKE_RESTIC_CAT_RC='1')

        assert result.returncode == 1
        assert 'restic-nas init' in result.stderr
        assert not any(call.startswith('zfs') for call in script_env.calls())

    def test_path_missing_from_the_snapshot_fails_and_cleans_up(self, script_env: ScriptEnv) -> None:
        """
        Test that a path absent from the snapshot (created after it, say) fails the run and destroys the snapshot
        """
        (script_env.pool / 'media' / 'newdir').mkdir()

        result = script_env.run(BACKUP_PATHS=f'{script_env.pool}/media/newdir')

        assert result.returncode == 1
        assert 'missing from the snapshot' in result.stderr
        assert not any(call.startswith('restic backup') for call in script_env.calls())
        assert not script_env.snapshot_exists()

    @pytest.mark.parametrize(
        'variable',
        [
            'RESTIC_REPOSITORY',
            'BACKUP_ZFS_DATASET',
            'BACKUP_PATHS',
            'BACKUP_KEEP_DAILY',
            'BACKUP_KEEP_WEEKLY',
            'BACKUP_KEEP_MONTHLY',
        ],
    )
    def test_missing_setting_is_reported_by_name(self, script_env: ScriptEnv, variable: str) -> None:
        """
        Test that each required setting aborts the run, naming the variable, before any command runs
        """
        env = {key: value for key, value in {**os.environ, **script_env.env}.items() if key != variable}

        result = subprocess.run([str(SCRIPT)], capture_output=True, text=True, check=False, env=env, timeout=60)

        assert result.returncode != 0
        assert f'{variable} is not set' in result.stderr
        assert script_env.calls() == []


class TestResticWrapper:
    """
    Tests for roles/backup/files/restic-nas
    """
    def test_loads_the_environment_file_and_forwards_arguments(self, tmp_path: Path) -> None:
        """
        Test that restic runs with the file's variables exported and the caller's arguments intact
        """
        bindir = tmp_path / 'bin'
        bindir.mkdir()
        stub = bindir / 'restic'
        stub.write_text('#!/usr/bin/env bash\nprintf "%s|%s|%s\\n" "$RESTIC_REPOSITORY" "$B2_ACCOUNT_KEY" "$*"\n')
        stub.chmod(0o755)
        envfile = tmp_path / 'restic.env'
        envfile.write_text("RESTIC_REPOSITORY='b2:bucket:restic'\nB2_ACCOUNT_KEY='k'\n", encoding='utf-8')

        result = subprocess.run(
            [str(WRAPPER), 'snapshots', '--json'],
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, 'PATH': f'{bindir}:{os.environ["PATH"]}', 'RESTIC_NAS_ENV': str(envfile)},
            timeout=30,
        )

        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == 'b2:bucket:restic|k|snapshots --json'
