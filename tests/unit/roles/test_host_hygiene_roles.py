"""
Behavioral tests for host hygiene: unattended upgrades and the reboot alert (debian role), and the Docker daemon
configuration, legacy compose removal and image prune timer (docker role)

Tasks run for real with ansible-playbook against localhost (``ansible_become=false``, scratch destinations); the reboot
check runs for real with stub ``nas-notify`` and ``dkms`` binaries; the apt origin list is read back through the real
``apt-config``; the daemon configuration is validated by the real ``dockerd --validate``. See CLAUDE-LESSONS.md,
"String-matching Ansible YAML is not verification: run the role".
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.unit.roles.test_alerting_roles import REPO_ROOT
from tests.unit.roles.test_alerting_roles import ROLES
from tests.unit.roles.test_alerting_roles import _render
from tests.unit.roles.test_alerting_roles import _run_tasks
from tests.unit.roles.test_alerting_roles import _tasks
from tests.unit.roles.test_alerting_roles import needs_ansible

TaskDict = dict[str, Any]  # Any: heterogeneous, yaml-loaded task structure

REBOOT_CHECK = ROLES / 'debian' / 'files' / 'nas-reboot-check'

needs_apt_config = pytest.mark.skipif(shutil.which('apt-config') is None, reason='apt-config not available')
needs_dockerd    = pytest.mark.skipif(shutil.which('dockerd')    is None, reason='dockerd not available')


# ==================================================================================================
# Helpers
# ==================================================================================================


def _runnable(role: str, task: TaskDict, out: Path) -> TaskDict:
    """
    Adapt a role task to run as a non-root user with every destination redirected into a scratch directory

    Sources become absolute (the play is not in the role), destinations keep only their basename under ``out``, and
    ``owner``/``group`` are dropped (chown to root fails unprivileged; a structural test pins them instead).
    """
    adapted = {key: value for key, value in task.items() if key not in {'notify', 'become'}}

    for module, subdir in (
        ('ansible.builtin.copy',     'files'),
        ('ansible.builtin.template', 'templates'),
        ('ansible.builtin.file',     None),
    ):
        if module in adapted:
            args = {key: value for key, value in adapted[module].items() if key not in {'owner', 'group'}}
            if 'src' in args:
                args['src'] = str(ROLES / role / str(subdir) / args['src'])
            for key in ('dest', 'path'):
                if key in args:
                    args[key] = str(out / Path(args[key]).name)
            adapted[module] = args

    return adapted


def _named(role: str, file: str, names: list[str], out: Path) -> list[TaskDict]:
    """
    Pick tasks by name, in the given order, ready to run in a scratch play
    """
    by_name = {task['name']: task for task in _tasks(role, file)}
    return [_runnable(role, by_name[name], out) for name in names]


def _json_vars(**values: Any) -> list[str]:
    """
    Build an ``-e`` argument from JSON, so lists and dicts survive
    """
    return ['-e', json.dumps(values)]


# ==================================================================================================
# Unattended upgrades (debian role)
# ==================================================================================================

UPGRADE_FILE_TASKS = [
    'Enable the daily package list refresh and unattended upgrade',
    'Restrict unattended upgrades to the security origin and disable automatic reboot',
    'Create the failure-alert drop-in directory for apt-daily-upgrade',
    'Alert when the unattended upgrade run fails',
    'Install the reboot check',
    'Install the reboot check service',
    'Install the reboot check timer',
]

# The origin list shipped in unattended-upgrades 2.9.1+nmu3 (Debian 12), in
# /usr/share/unattended-upgrades/50unattended-upgrades. Note label=Debian: the regular stable repository, not just
# security.
DEBIAN_DEFAULT_50 = """\
Unattended-Upgrade::Origins-Pattern {
        "origin=Debian,codename=${distro_codename},label=Debian";
        "origin=Debian,codename=${distro_codename},label=Debian-Security";
        "origin=Debian,codename=${distro_codename}-security,label=Debian-Security";
};
"""

SECURITY_ORIGIN = 'origin=Debian,codename=${distro_codename}-security,label=Debian-Security'


def _effective_apt_config(tmp_path: Path, *parts: tuple[str, str]) -> list[str]:
    """
    Load apt.conf.d-style files through the real apt-config and return its Unattended-Upgrade lines

    :param tmp_path: scratch directory
    :param parts: (file name, content) pairs, loaded in name order like /etc/apt/apt.conf.d
    :return: the ``apt-config dump`` lines for the Unattended-Upgrade namespace
    """
    parts_dir = tmp_path / 'apt.conf.d'
    parts_dir.mkdir()
    for name, content in parts:
        (parts_dir / name).write_text(content, encoding='utf-8')

    main = tmp_path / 'apt.conf'
    main.write_text(f'Dir::Etc::Main "/dev/null";\nDir::Etc::Parts "{parts_dir}";\n', encoding='utf-8')

    result = subprocess.run(
        ['apt-config', 'dump'],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, 'APT_CONFIG': str(main)},
    )
    return [line for line in result.stdout.splitlines() if line.startswith('Unattended-Upgrade::')]


@needs_ansible
class TestUnattendedUpgrades:
    """
    Tests for roles/debian/tasks/upgrades.yml
    """
    @needs_apt_config
    def test_dropin_leaves_only_the_security_origin_over_the_debian_default(self, tmp_path: Path) -> None:
        """
        Test that the real apt-config, given Debian's default list plus the rendered drop-in, ends with only security
        """
        dropin = _render(tmp_path, 'debian', '52nas-unattended-upgrades.j2')
        lines  = _effective_apt_config(tmp_path, ('50unattended-upgrades', DEBIAN_DEFAULT_50), ('52nas', dropin))

        origins = [line for line in lines if line.startswith('Unattended-Upgrade::Origins-Pattern::')]
        assert origins == [f'Unattended-Upgrade::Origins-Pattern:: "{SECURITY_ORIGIN}";']
        assert 'Unattended-Upgrade::Automatic-Reboot "false";' in lines

    @needs_apt_config
    def test_default_alone_would_also_take_the_stable_repository(self, tmp_path: Path) -> None:
        """
        Test that without the drop-in Debian's list includes label=Debian, which is why the drop-in must clear it
        """
        lines = _effective_apt_config(tmp_path, ('50unattended-upgrades', DEBIAN_DEFAULT_50))
        assert any('label=Debian"' in line for line in lines)

    def test_files_are_written_then_converge(self, tmp_path: Path) -> None:
        """
        Test that the upgrade files write on the first run and a second run changes nothing
        """
        out = tmp_path / 'out'
        out.mkdir()
        tasks = _named('debian', 'upgrades.yml', UPGRADE_FILE_TASKS, out)

        code, output = _run_tasks(tmp_path, 'debian', tasks)
        assert code == 0, output
        assert 'changed=7' in output, output

        assert (out / '20auto-upgrades').read_text(encoding='utf-8').splitlines() == [
            'APT::Periodic::Update-Package-Lists "1";',
            'APT::Periodic::Unattended-Upgrade "1";',
        ]
        assert os.access(out / 'nas-reboot-check', os.X_OK)

        code, output = _run_tasks(tmp_path, 'debian', tasks)
        assert code == 0, output
        assert 'changed=0' in output, output

    def test_drift_in_the_origin_list_is_repaired(self, tmp_path: Path) -> None:
        """
        Test that a hand-edited drop-in is put back by the next run
        """
        out = tmp_path / 'out'
        out.mkdir()

        tasks = _named('debian', 'upgrades.yml', UPGRADE_FILE_TASKS, out)
        _run_tasks(tmp_path, 'debian', tasks)
        (out / '52nas-unattended-upgrades').write_text('Unattended-Upgrade::Automatic-Reboot "true";\n')

        code, output = _run_tasks(tmp_path, 'debian', tasks)
        assert code == 0, output
        assert 'changed=1' in output, output
        assert 'Automatic-Reboot "false"' in (out / '52nas-unattended-upgrades').read_text(encoding='utf-8')

    def test_failure_dropin_and_timer_are_rendered(self, tmp_path: Path) -> None:
        """
        Test that apt-daily-upgrade alerts on failure and the reboot timer is daily and persistent
        """
        out = tmp_path / 'out'
        out.mkdir()

        _run_tasks(tmp_path, 'debian', _named('debian', 'upgrades.yml', UPGRADE_FILE_TASKS, out))
        assert 'OnFailure=nas-notify-failure@%n.service' in (out / 'onfailure.conf').read_text(encoding='utf-8')

        timer = (out / 'nas-reboot-check.timer').read_text(encoding='utf-8')
        assert 'OnCalendar=*-*-* 09:00:00' in timer
        assert 'Persistent=true'           in timer

        service = (ROLES / 'debian' / 'files' / 'nas-reboot-check.service').read_text(encoding='utf-8')
        assert 'OnFailure=nas-notify-failure@%n.service' in service

    def test_unattended_upgrades_is_installed_and_both_apt_timers_enabled(self) -> None:
        """
        Test that the package is in the apt list and the apt timers are asserted enabled
        """
        defaults = yaml.safe_load((ROLES / 'debian' / 'defaults' / 'main.yml').read_text(encoding='utf-8'))
        assert 'unattended-upgrades' in defaults['debian_apt_packages']

        task = next(t for t in _tasks('debian', 'upgrades.yml') if t['name'].startswith('Enable the apt timers'))
        assert task['loop'] == ['apt-daily.timer', 'apt-daily-upgrade.timer']
        assert task['ansible.builtin.systemd']['enabled'] is True

    def test_reboot_check_timer_is_enabled_after_the_units_are_loaded(self) -> None:
        """
        Test that handlers are flushed (daemon-reload) between installing the timer and enabling it
        """
        names = [task['name'] for task in _tasks('debian', 'upgrades.yml')]
        assert (
            names.index('Install the reboot check timer')
            < names.index('Reload systemd before enabling the reboot check timer')
            < names.index('Enable and start the reboot check timer')
        )


# ==================================================================================================
# The reboot check script
# ==================================================================================================

FAKE_NAS_NOTIFY = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$FAKE_STATE/notifications.log"
"""

FAKE_DKMS = """#!/usr/bin/env bash
cat "$FAKE_STATE/dkms-status"
"""


class RebootEnv:
    """
    A scratch /boot, state file and stub binaries for running nas-reboot-check
    """
    def __init__(self, tmp_path: Path) -> None:
        """
        Build the stubs and an empty /boot

        :param tmp_path: scratch directory
        """
        self.state = tmp_path / 'state'
        self.boot  = tmp_path / 'boot'

        bindir = tmp_path / 'stub-bin'
        for directory in (self.state, self.boot, bindir):
            directory.mkdir()

        notify = self.state / 'nas-notify'
        notify.write_text(FAKE_NAS_NOTIFY, encoding='utf-8')
        notify.chmod(0o755)

        dkms = bindir / 'dkms'
        dkms.write_text(FAKE_DKMS, encoding='utf-8')
        dkms.chmod(0o755)

        self.env = {
            'PATH':                 f'{bindir}:{os.environ["PATH"]}',
            'FAKE_STATE':           str(self.state),
            'BOOT_DIR':             str(self.boot),
            'STATE_FILE':           str(self.state / 'reboot-state'),
            'NAS_NOTIFY':           str(notify),
            'REBOOT_REQUIRED_FILE': str(tmp_path / 'reboot-required'),
            'REBOOT_REQUIRED_PKGS': str(tmp_path / 'reboot-required.pkgs'),
            'KERNEL_RELEASE':       '6.1.0-52-amd64',
        }
        self.set_kernels('6.1.0-52-amd64')
        self.set_dkms('6.1.0-52-amd64')

    def set_kernels(self, *releases: str) -> None:
        """
        Replace the installed kernels in the scratch /boot
        """
        for image in self.boot.glob('vmlinuz-*'):
            image.unlink()
        for release in releases:
            (self.boot / f'vmlinuz-{release}').touch()

    def set_dkms(self, *releases: str) -> None:
        """
        Set which kernels `dkms status` reports the zfs module as installed for
        """
        lines = [f'zfs/2.1.11, {release}, x86_64: installed' for release in releases]
        (self.state / 'dkms-status').write_text('\n'.join(lines) + '\n', encoding='utf-8')

    def run(self, **env: str) -> subprocess.CompletedProcess[str]:
        """
        Run the check, returning the finished process
        """
        return subprocess.run(
            [str(REBOOT_CHECK)],
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, **self.env, **env},
            timeout=60,
        )

    def notifications(self) -> list[str]:
        """
        Return the recorded nas-notify argument lines
        """
        log = self.state / 'notifications.log'
        return log.read_text(encoding='utf-8').splitlines() if log.exists() else []


@pytest.fixture
def reboot_env(tmp_path: Path) -> RebootEnv:
    """
    Provide a scratch /boot with one kernel (the running one) and stub nas-notify and dkms
    """
    return RebootEnv(tmp_path)


class TestRebootCheck:
    """
    Tests for roles/debian/files/nas-reboot-check
    """
    def test_nothing_pending_stays_silent(self, reboot_env: RebootEnv) -> None:
        """
        Test that the running kernel being the newest, with no flag, sends nothing
        """
        result = reboot_env.run()
        assert result.returncode == 0, result.stderr
        assert reboot_env.notifications() == []

    def test_newer_installed_kernel_alerts_once_with_zfs_confirmation(self, reboot_env: RebootEnv) -> None:
        """
        Test that an installed-but-not-running kernel alerts at high priority and a second run stays quiet
        """
        reboot_env.set_kernels('6.1.0-52-amd64', '6.1.0-54-amd64')
        reboot_env.set_dkms('6.1.0-52-amd64', '6.1.0-54-amd64')
        assert reboot_env.run().returncode == 0

        [line] = reboot_env.notifications()
        assert line.startswith('-p high -t Reboot required on ')
        assert 'kernel 6.1.0-54-amd64 is installed but 6.1.0-52-amd64 is running' in line
        assert 'DKMS has built the zfs module for it'                             in line

        reboot_env.run()
        assert len(reboot_env.notifications()) == 1

    def test_missing_zfs_module_is_urgent_and_says_not_to_reboot(self, reboot_env: RebootEnv) -> None:
        """
        Test that a newer kernel without a DKMS-built zfs module raises urgent priority and a do-not-reboot warning
        """
        reboot_env.set_kernels('6.1.0-52-amd64', '6.1.0-54-amd64')
        reboot_env.set_dkms('6.1.0-52-amd64')

        reboot_env.run()

        [line] = reboot_env.notifications()
        assert line.startswith('-p urgent ')
        assert 'DO NOT REBOOT YET' in line

    def test_failed_zfs_build_is_not_mistaken_for_a_good_one(self, reboot_env: RebootEnv) -> None:
        """
        Test that a dkms status of 'built' (not 'installed') for the new kernel does not count as ready
        """
        reboot_env.set_kernels('6.1.0-52-amd64', '6.1.0-54-amd64')
        (reboot_env.state / 'dkms-status').write_text('zfs/2.1.11, 6.1.0-54-amd64, x86_64: built\n', encoding='utf-8')

        reboot_env.run()
        assert 'DO NOT REBOOT YET' in reboot_env.notifications()[0]

    def test_missing_dkms_is_reported_not_assumed_fine(self, reboot_env: RebootEnv, tmp_path: Path) -> None:
        """
        Test that with no dkms on PATH the message says the module could not be checked
        """
        reboot_env.set_kernels('6.1.0-52-amd64', '6.1.0-54-amd64')
        (tmp_path / 'stub-bin' / 'dkms').unlink()

        reboot_env.run(PATH='/usr/bin:/bin')

        [line] = reboot_env.notifications()
        assert 'dkms is not installed' in line
        assert 'DKMS has built' not in line

    @pytest.mark.parametrize(
        ('installed', 'running', 'alerts'),
        [
            (['6.1.0-9-amd64', '6.1.0-54-amd64'], '6.1.0-54-amd64', False),   # version order, not string order
            (['6.1.0-9-amd64', '6.1.0-54-amd64'], '6.1.0-9-amd64',  True),
            (['6.1.0-52-amd64'],                  '6.1.0-54-amd64', False),   # running is newer than anything installed
        ],
    )
    def test_kernels_compare_by_version(
        self,
        reboot_env: RebootEnv,
        installed: list[str],
        running: str,
        alerts: bool,
    ) -> None:
        """
        Test that kernel releases compare numerically (9 is older than 54) and only a newer installed one alerts
        """
        reboot_env.set_kernels(*installed)
        reboot_env.set_dkms(*installed)

        reboot_env.run(KERNEL_RELEASE=running)
        assert bool(reboot_env.notifications()) is alerts

    def test_reboot_required_flag_alerts_and_names_the_packages(self, reboot_env: RebootEnv, tmp_path: Path) -> None:
        """
        Test that the flag file alone triggers an alert listing the packages it names
        """
        (tmp_path / 'reboot-required').touch()
        (tmp_path / 'reboot-required.pkgs').write_text('libc6\nlibssl3\nlibc6\n', encoding='utf-8')

        reboot_env.run()
        [line] = reboot_env.notifications()
        assert 'reboot-required flag is set (libc6 libssl3)' in line

    def test_a_changed_condition_alerts_again_immediately(self, reboot_env: RebootEnv, tmp_path: Path) -> None:
        """
        Test that a new reason (a flag appearing after a kernel alert) is not suppressed by the earlier alert
        """
        reboot_env.set_kernels('6.1.0-52-amd64', '6.1.0-54-amd64')
        reboot_env.run()
        (tmp_path / 'reboot-required').touch()

        reboot_env.run()
        assert len(reboot_env.notifications()) == 2

    def test_reminder_after_the_interval_while_still_pending(self, reboot_env: RebootEnv) -> None:
        """
        Test that an unchanged condition alerts again once the state file is older than the reminder interval
        """
        reboot_env.set_kernels('6.1.0-52-amd64', '6.1.0-54-amd64')
        reboot_env.run()

        state          = Path(reboot_env.env['STATE_FILE'])
        eight_days_ago = time.time() - 8 * 86400
        os.utime(state, (eight_days_ago, eight_days_ago))

        reboot_env.run()
        assert len(reboot_env.notifications()) == 2

    def test_clearing_the_condition_resets_the_state(self, reboot_env: RebootEnv) -> None:
        """
        Test that after a reboot (running kernel is the newest) the state file goes, so a later kernel alerts again
        """
        reboot_env.set_kernels('6.1.0-52-amd64', '6.1.0-54-amd64')
        reboot_env.run()
        reboot_env.run(KERNEL_RELEASE='6.1.0-54-amd64')
        assert not Path(reboot_env.env['STATE_FILE']).exists()

        reboot_env.run()
        assert len(reboot_env.notifications()) == 2


# ==================================================================================================
# Docker daemon, compose v1 removal and image prune (docker role)
# ==================================================================================================

DOCKER_FILE_TASKS = [
    'Configure the docker daemon',
    'Install the weekly image prune service',
    'Install the weekly image prune timer',
]


@needs_ansible
class TestDockerDaemonConfig:
    """
    Tests for the docker role's daemon.json
    """
    def test_default_caps_logs_at_three_ten_megabyte_files(self, tmp_path: Path) -> None:
        """
        Test that the rendered file is JSON selecting json-file with string-valued max-size 10m and max-file 3
        """
        config = json.loads(_render(tmp_path, 'docker', 'daemon.json.j2'))
        assert config == {'log-driver': 'json-file', 'log-opts': {'max-file': '3', 'max-size': '10m'}}

    @needs_dockerd
    def test_the_real_dockerd_accepts_the_rendered_default(self, tmp_path: Path) -> None:
        """
        Test that dockerd --validate says the default configuration is OK
        """
        rendered = tmp_path / 'daemon.json'
        rendered.write_text(_render(tmp_path, 'docker', 'daemon.json.j2'), encoding='utf-8')

        result = subprocess.run(
            ['dockerd', '--validate', '--config-file', str(rendered)],
            capture_output=True,
            text=True,
            check=False,
            cwd=tmp_path,
        )
        assert result.returncode == 0, result.stderr
        assert 'configuration OK' in result.stdout + result.stderr

    @needs_dockerd
    def test_task_validates_before_installing_and_converges(self, tmp_path: Path) -> None:
        """
        Test that a valid file is installed once and left alone on a second run
        """
        out = tmp_path / 'out'
        out.mkdir()
        tasks = [_runnable('docker', _find_docker_task('Configure the docker daemon'), out)]

        code, output = _run_tasks(tmp_path, 'docker', tasks)
        assert code == 0, output
        assert 'changed=1' in output, output
        assert json.loads((out / 'daemon.json').read_text(encoding='utf-8'))['log-driver'] == 'json-file'

        code, output = _run_tasks(tmp_path, 'docker', tasks)
        assert code == 0, output
        assert 'changed=0' in output, output

    @needs_dockerd
    def test_invalid_configuration_is_refused_and_nothing_is_written(self, tmp_path: Path) -> None:
        """
        Test that a numeric log-opts value (dockerd wants strings) fails the task before it can break the daemon
        """
        out = tmp_path / 'out'
        out.mkdir()

        tasks = [_runnable('docker', _find_docker_task('Configure the docker daemon'), out)]
        bad   = _json_vars(docker_daemon_config={'log-driver': 'json-file', 'log-opts': {'max-size': 10}})

        code, output = _run_tasks(tmp_path, 'docker', tasks, *bad)
        assert code != 0, output
        assert not (out / 'daemon.json').exists()

    @pytest.mark.parametrize(('restart_enabled', 'restarted'), [(False, False), (True, True)])
    def test_restart_handler_runs_only_when_enabled(
        self,
        tmp_path: Path,
        restart_enabled: bool,
        restarted: bool,
    ) -> None:
        """
        Test that a changed daemon.json restarts docker only with docker_restart_on_config_change set
        """
        out = tmp_path / 'out'
        out.mkdir()

        marker = tmp_path / 'restarted'
        change = {**_runnable('docker', _find_docker_task('Configure the docker daemon'), out)}
        change['notify'] = 'Restart docker'
        change['ansible.builtin.template'] = {
            key: value
            for key, value in change['ansible.builtin.template'].items()
            if key != 'validate'
        }

        real = next(h for h in _handlers('docker') if h['name'] == 'Restart docker')
        handler = {'name': real['name'], 'ansible.builtin.file': {'path': str(marker), 'state': 'touch'}}
        handler['when'] = real['when']

        code, output = _run_tasks(
            tmp_path,
            'docker',
            [change],
            *_json_vars(docker_restart_on_config_change=restart_enabled),
            handlers=[handler],
        )
        assert code == 0, output
        assert marker.exists() is restarted


def _find_docker_task(name: str) -> TaskDict:
    """
    Return the docker role task with the given name, searching inside its blocks
    """
    def walk(tasks: list[TaskDict]) -> list[TaskDict]:
        found: list[TaskDict] = []
        for task in tasks:
            found.append(task)
            found += walk(task.get('block', []))
        return found

    matches = [task for task in walk(_tasks('docker', 'main.yml')) if task.get('name') == name]
    assert len(matches) == 1, f'expected exactly one docker task named {name!r}'
    return matches[0]


def _handlers(role: str) -> list[TaskDict]:
    """
    Load a role's handlers
    """
    return yaml.safe_load((ROLES / role / 'handlers' / 'main.yml').read_text(encoding='utf-8'))


@needs_ansible
class TestImagePrune:
    """
    Tests for the docker role's weekly image prune units
    """
    def test_units_prune_unused_images_older_than_a_week_and_alert_on_failure(self, tmp_path: Path) -> None:
        """
        Test that the service runs docker image prune with the age filter, and the timer is weekly and persistent
        """
        out = tmp_path / 'out'
        out.mkdir()
        tasks = [_runnable('docker', _find_docker_task(name), out) for name in DOCKER_FILE_TASKS[1:]]

        code, output = _run_tasks(tmp_path, 'docker', tasks)
        assert code == 0, output

        service = (out / 'docker-image-prune.service').read_text(encoding='utf-8')
        timer   = (out / 'docker-image-prune.timer').read_text(encoding='utf-8')

        assert 'ExecStart=/usr/bin/docker image prune --all --force --filter until=168h' in service
        assert 'OnFailure=nas-notify-failure@%n.service'                                 in service

        assert 'OnCalendar=Sun *-*-* 05:30:00' in timer
        assert 'Persistent=true'               in timer

        code, output = _run_tasks(tmp_path, 'docker', tasks)
        assert 'changed=0' in output, output


class TestComposeV1Removal:
    """
    Tests that the legacy docker-compose v1 package is removed and nothing in the repository needs it
    """
    def test_v1_is_not_installed_and_is_explicitly_removed(self) -> None:
        """
        Test that the install list holds the compose plugin only, and a task removes the v1 package
        """
        install = _find_docker_task('Install Docker engine')['ansible.builtin.apt']['pkg']
        assert 'docker-compose-plugin' in install
        assert 'docker-compose'    not in install

        removal = _find_docker_task('Remove the legacy docker-compose v1 package')['ansible.builtin.apt']
        assert removal == {'name': 'docker-compose', 'state': 'absent'}

    def test_no_script_or_service_invokes_v1(self) -> None:
        """
        Test that the deploy scripts and compose services never run the hyphenated docker-compose command
        """
        candidates: list[Path] = [
            ROLES / 'docker' / 'files' / 'deploy.sh',
            REPO_ROOT / 'scripts' / 'nas' / 'deploy-services.sh',
            *(REPO_ROOT / 'services').rglob('*'),
            *(REPO_ROOT / '.github' / 'workflows').glob('*.yml'),
        ]
        callers = [
            str(path.relative_to(REPO_ROOT))
            for path in candidates
            if path.is_file() and re.search(r'(?<![\w.-])docker-compose(?![\w.-])', path.read_text(encoding='utf-8'))
        ]
        assert callers == []
