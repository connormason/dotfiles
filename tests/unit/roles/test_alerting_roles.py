"""
Behavioral tests for the alerting, ZED, pool-property and sanoid tasks of the debian and zfs roles

Tasks are run for real with ansible-playbook against localhost (``ansible_become=false``, stub zfs/zpool binaries,
temporary destinations); see CLAUDE-LESSONS.md, "String-matching Ansible YAML is not verification: run the role".
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
ROLES     = REPO_ROOT / 'roles'

ANSIBLE_PLAYBOOK = Path(sys.executable).parent / 'ansible-playbook'

needs_ansible = pytest.mark.skipif(not ANSIBLE_PLAYBOOK.exists(), reason='ansible-playbook not in this environment')

TaskDict = dict[str, Any]  # Any: heterogeneous, yaml-loaded task structure
ZfsState = tuple[Path, dict[str, str]]  # (stub state directory, environment putting the stubs on PATH)

# zpool list -H -o name POOL
FAKE_ZPOOL = '#!/usr/bin/env bash\n[[ -d "$FAKE_ZFS_STATE/pool-$5" ]] && echo "$5" || exit 1\n'

# zfs get -H -o value PROP POOL  /  zfs set PROP=VALUE POOL
FAKE_ZFS = """#!/usr/bin/env bash
case "$1" in
    get) cat "$FAKE_ZFS_STATE/$5" ;;
    set) printf '%s\\n' "${2#*=}" > "$FAKE_ZFS_STATE/${2%%=*}"; echo "$2" >> "$FAKE_ZFS_STATE/set.log" ;;
    *)   exit 2 ;;
esac
"""


def _tasks(role: str, file: str) -> list[TaskDict]:
    """
    Load the tasks of one of a role's task files
    """
    return yaml.safe_load((ROLES / role / 'tasks' / file).read_text(encoding='utf-8'))


def _run_tasks(
    tmp_path: Path,
    role: str,
    tasks: list[TaskDict],
    *extra: str,
    env: dict[str, str] | None = None,
) -> tuple[int, str]:
    """
    Run tasks as one localhost play with the role's defaults loaded

    :param tmp_path: scratch directory
    :param role: role whose ``defaults/main.yml`` supplies the variables
    :param tasks: task dicts to run
    :param extra: extra ansible-playbook arguments (for example ``-e name=value``)
    :param env: extra environment variables
    :return: tuple of (return code, combined output)
    """
    play = [{
        'hosts': 'all',
        'gather_facts': False,
        'connection': 'local',
        'vars_files': [str(ROLES / role / 'defaults' / 'main.yml')],
        'tasks': tasks,
    }]
    playbook = tmp_path / 'play.yml'
    playbook.write_text(yaml.safe_dump(play), encoding='utf-8')

    vault = tmp_path / 'vault-pass'  # ansible.cfg names a vault password file; nothing here is encrypted
    vault.write_text('unused\n', encoding='utf-8')

    result = subprocess.run(
        [str(ANSIBLE_PLAYBOOK), str(playbook), '-i', 'localhost,', '-e', 'ansible_become=false', *extra],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
        env={**os.environ, 'ANSIBLE_VAULT_PASSWORD_FILE': str(vault), 'ANSIBLE_NOCOLOR': '1', **(env or {})},
        timeout=300,
    )
    return result.returncode, result.stdout + result.stderr


def _task(role: str, file: str, name: str) -> TaskDict:
    """
    Return the task with the given name from a role's task file, minus its handler notification
    """
    matches = [task for task in _tasks(role, file) if task.get('name') == name]
    assert len(matches) == 1, f'expected exactly one task named {name!r} in {role}/{file}'
    return {key: value for key, value in matches[0].items() if key != 'notify'}


def _render(tmp_path: Path, role: str, template: str, *extra: str) -> str:
    """
    Render one of a role's templates through the real template module with the role's defaults

    :return: the rendered text
    """
    dest = tmp_path / 'rendered'
    task = {'ansible.builtin.template': {'src': str(ROLES / role / 'templates' / template), 'dest': str(dest)}}
    code, output = _run_tasks(tmp_path, role, [task], *extra)
    assert code == 0, output
    return dest.read_text(encoding='utf-8')


@pytest.fixture
def zfs_state(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    """
    Create a stub zfs/zpool pair backed by files, holding a pool named 'storage' with ZFS's defaults

    :return: tuple of (state directory, environment putting the stubs first on PATH)
    """
    state = tmp_path / 'zfs-state'
    bindir = tmp_path / 'zfs-bin'
    state.mkdir()
    bindir.mkdir()
    (state / 'pool-storage').mkdir()
    (state / 'compression').write_text('off\n', encoding='utf-8')
    (state / 'atime').write_text('on\n', encoding='utf-8')
    for name, body in (('zpool', FAKE_ZPOOL), ('zfs', FAKE_ZFS)):
        stub = bindir / name
        stub.write_text(body, encoding='utf-8')
        stub.chmod(0o755)
    return state, {'PATH': f'{bindir}:{os.environ["PATH"]}', 'FAKE_ZFS_STATE': str(state)}


def _import_pool_tasks() -> list[TaskDict]:
    """
    The play body that runs the zfs role's pool.yml, as the role imports it
    """
    return [{'ansible.builtin.import_tasks': str(ROLES / 'zfs' / 'tasks' / 'pool.yml')}]


@needs_ansible
class TestPoolProperties:
    """
    Real-run tests of roles/zfs/tasks/pool.yml
    """
    def test_sets_lz4_and_atime_off_then_converges(self, tmp_path: Path, zfs_state: ZfsState) -> None:
        """
        Test that the first run sets both properties and a second run changes nothing
        """
        state, env = zfs_state

        code, output = _run_tasks(tmp_path, 'zfs', _import_pool_tasks(), env=env)
        assert code == 0, output
        assert (state / 'compression').read_text(encoding='utf-8').strip() == 'lz4'
        assert (state / 'atime').read_text(encoding='utf-8').strip() == 'off'
        assert 'changed=1' in output, output

        code, output = _run_tasks(tmp_path, 'zfs', _import_pool_tasks(), env=env)
        assert code == 0, output
        assert 'changed=0' in output, output
        assert len((state / 'set.log').read_text(encoding='utf-8').splitlines()) == 2

    def test_only_drifted_properties_are_rewritten(self, tmp_path: Path, zfs_state: ZfsState) -> None:
        """
        Test that after drift in one property a run sets just that property
        """
        state, env = zfs_state
        _run_tasks(tmp_path, 'zfs', _import_pool_tasks(), env=env)
        (state / 'set.log').unlink()
        (state / 'compression').write_text('off\n', encoding='utf-8')

        code, output = _run_tasks(tmp_path, 'zfs', _import_pool_tasks(), env=env)

        assert code == 0, output
        assert (state / 'set.log').read_text(encoding='utf-8').splitlines() == ['compression=lz4']

    def test_missing_pool_fails_without_creating_anything(
        self, tmp_path: Path, zfs_state: ZfsState,
    ) -> None:
        """
        Test that an absent pool stops the run with an explanation and no zfs set
        """
        state, env = zfs_state

        code, output = _run_tasks(tmp_path, 'zfs', _import_pool_tasks(), '-e', 'zfs_pool_name=tank', env=env)

        assert code != 0
        assert 'never creates pools' in output
        assert not (state / 'set.log').exists()


@needs_ansible
class TestZedConfiguration:
    """
    Real-run tests of the zed.rc edits
    """
    ZED_RC = (
        'ZED_EMAIL_ADDR="root"\n'
        '#ZED_EMAIL_PROG="mail"\n'
        '#ZED_EMAIL_OPTS="-s \'@SUBJECT@\' @ADDRESS@"\n'
        'ZED_NOTIFY_INTERVAL_SECS=3600\n'
        '#ZED_NOTIFY_VERBOSE=0\n'
    )

    def test_points_zed_at_nas_notify_and_converges(self, tmp_path: Path) -> None:
        """
        Test that the settings are uncommented or appended in place, other lines survive, and a re-run is a no-op
        """
        rc = tmp_path / 'zed.rc'
        rc.write_text(self.ZED_RC, encoding='utf-8')
        task = _task('zfs', 'zed.yml', 'Configure ZED notifications')

        code, output = _run_tasks(tmp_path, 'zfs', [task], '-e', f'zfs_zed_rc_path={rc}')
        assert code == 0, output
        lines = rc.read_text(encoding='utf-8').splitlines()
        assert 'ZED_EMAIL_PROG="/usr/local/bin/nas-notify"' in lines
        assert 'ZED_EMAIL_OPTS="-z"' in lines
        assert 'ZED_NOTIFY_VERBOSE=1' in lines
        assert 'ZED_NOTIFY_INTERVAL_SECS=3600' in lines
        assert not any(line.startswith('#ZED_EMAIL_PROG') for line in lines)

        code, output = _run_tasks(tmp_path, 'zfs', [task], '-e', f'zfs_zed_rc_path={rc}')
        assert code == 0, output
        assert 'changed=0' in output, output

    def test_zed_options_leave_the_subject_placeholder_out(self) -> None:
        """
        Test that ZED_EMAIL_OPTS has no @SUBJECT@, which makes ZED write the Subject header that nas-notify -z parses
        """
        defaults = yaml.safe_load((ROLES / 'zfs' / 'defaults' / 'main.yml').read_text(encoding='utf-8'))

        assert '@SUBJECT@' not in defaults['zfs_zed_settings']['ZED_EMAIL_OPTS']


@needs_ansible
class TestTemplates:
    """
    Real-render tests of the smartd, sanoid and nas-notify templates
    """
    def test_smartd_conf_alerts_through_nas_notify_on_the_default_schedule(self, tmp_path: Path) -> None:
        """
        Test that the single DEVICESCAN line carries the schedule and the nas-notify exec hook
        """
        text = _render(tmp_path, 'debian', 'smartd.conf.j2')

        line = next(line for line in text.splitlines() if line.startswith('DEVICESCAN'))
        assert '-s (S/../../7/03|L/../01/./04)' in line
        assert '-M exec /usr/local/bin/nas-notify' in line

    @pytest.mark.parametrize(
        ('stamp', 'matches'),
        [
            ('S/11/15/7/03', True),    # Sunday 03:00: short test
            ('L/11/01/1/04', True),    # 1st of the month 04:00: long test
            ('S/11/16/1/03', False),   # Monday
            ('L/11/02/2/04', False),   # not the 1st
            ('S/11/15/7/04', False),   # wrong hour
        ],
    )
    def test_default_schedule_selects_the_intended_slots(self, stamp: str, matches: bool) -> None:
        """
        Test that the default smartd regexp matches the weekly short and monthly long slots only
        """
        defaults = yaml.safe_load((ROLES / 'debian' / 'defaults' / 'main.yml').read_text(encoding='utf-8'))

        assert bool(re.fullmatch(defaults['debian_smartd_schedule'], stamp)) is matches

    def test_nas_notify_settings_carry_the_vault_token(self, tmp_path: Path) -> None:
        """
        Test that ntfy_alerts_token reaches NTFY_TOKEN and defaults to empty when unset
        """
        assert "NTFY_TOKEN=''" in _render(tmp_path, 'debian', 'nas-notify.env.j2')
        rendered = _render(tmp_path, 'debian', 'nas-notify.env.j2', '-e', 'ntfy_alerts_token=s3cret')
        assert "NTFY_TOKEN='s3cret'" in rendered

    def test_sanoid_conf_defines_the_interim_policy(self, tmp_path: Path) -> None:
        """
        Test that the pool gets a dataset section using a template section with the retention counts
        """
        text = _render(tmp_path, 'zfs', 'sanoid.conf.j2')

        assert re.search(r'^\[storage\]\n\tuse_template = interim\n\trecursive = no$', text, re.MULTILINE)
        template = text.split('[template_interim]')[1]
        for setting in ('hourly = 24', 'daily = 7', 'monthly = 0', 'autosnap = yes', 'autoprune = yes'):
            assert setting in template


class TestRoleWiring:
    """
    Structural tests that pin wiring the real-run tests cannot reach (root-owned paths)
    """
    def test_secret_settings_file_is_private_and_not_logged(self) -> None:
        """
        Test that the token file is 0600 root with diff and no_log off, per the check-mode lesson
        """
        task = next(t for t in _tasks('debian', 'alerts.yml') if t['name'] == 'Render the nas-notify settings')

        assert task['ansible.builtin.template']['mode'] == '0600'
        assert task['ansible.builtin.template']['owner'] == 'root'
        assert task['diff'] is False
        assert task['no_log'] is True

    def test_smartmontools_is_installed(self) -> None:
        """
        Test that smartmontools is in the debian role's package list
        """
        defaults = yaml.safe_load((ROLES / 'debian' / 'defaults' / 'main.yml').read_text(encoding='utf-8'))

        assert 'smartmontools' in defaults['debian_apt_packages']

    def test_every_notified_handler_exists_in_its_own_role(self) -> None:
        """
        Test that each role notifies only handlers it defines (handlers are play-global, so --tags zfs must stand alone)
        """
        for role in ('debian', 'zfs'):
            handlers = {h['name'] for h in yaml.safe_load((ROLES / role / 'handlers' / 'main.yml').read_text('utf-8'))}
            for path in (ROLES / role / 'tasks').glob('*.yml'):
                for task in yaml.safe_load(path.read_text(encoding='utf-8')):
                    notified = task.get('notify', [])
                    notified = [notified] if isinstance(notified, str) else notified
                    assert set(notified) <= handlers, f'{path.name}: {notified} not in {role} handlers {handlers}'

    def test_sanoid_units_alert_on_failure(self) -> None:
        """
        Test that both sanoid units get an OnFailure drop-in pointing at the nas-notify failure template
        """
        defaults = yaml.safe_load((ROLES / 'zfs' / 'defaults' / 'main.yml').read_text(encoding='utf-8'))
        task = next(t for t in _tasks('zfs', 'sanoid.yml') if t['name'] == 'Alert when a sanoid unit fails')

        assert defaults['zfs_sanoid_units'] == ['sanoid.service', 'sanoid-prune.service']
        assert 'OnFailure=nas-notify-failure@%n.service' in task['ansible.builtin.copy']['content']
