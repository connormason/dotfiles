"""
Tests for the per-service ``.local`` hostnames: the shared ``local_services`` list, the Caddy ``http://`` sites that
route them, and the ``mdns`` role that announces them

Tasks, templates and scripts run for real (ansible-playbook against localhost, stub binaries on PATH); see
CLAUDE-LESSONS.md, "String-matching Ansible YAML is not verification: run the role".
"""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import time
from contextlib import contextmanager
from typing import TYPE_CHECKING
from typing import Any

import pytest
import yaml

from tests.unit.roles.test_alerting_roles import REPO_ROOT
from tests.unit.roles.test_alerting_roles import ROLES
from tests.unit.roles.test_alerting_roles import _render
from tests.unit.roles.test_alerting_roles import _run_tasks
from tests.unit.roles.test_alerting_roles import needs_ansible

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

PLAYBOOK       = REPO_ROOT / 'playbooks' / 'nas_bootstrap.yml'
LOCAL_SERVICES = REPO_ROOT / 'playbooks' / 'vars' / 'local_services.yml'

ServiceDict = dict[str, Any]  # Any: yaml-loaded mapping of name (str) and port (int)


# ==================================================================================================
# The shared list
# ==================================================================================================


def _default_services() -> list[ServiceDict]:
    """
    Load the default hostname list from playbooks/vars/local_services.yml
    """
    data = yaml.safe_load(LOCAL_SERVICES.read_text(encoding='utf-8'))
    return data['local_services_default']


def _container_ports(name: str) -> set[int]:
    """
    Return the container-side TCP ports that a service's compose file publishes
    """
    compose = yaml.safe_load((REPO_ROOT / 'services' / name / 'compose.yml').read_text(encoding='utf-8'))
    ports: set[int] = set()
    for service in compose['services'].values():
        for mapping in service.get('ports', []):
            target = str(mapping).rsplit(':', 1)[-1]
            if not target.endswith('/udp'):
                ports.add(int(target.removesuffix('/tcp')))
    return ports


def _resolved(tmp_path: Path, *extra: str) -> list[ServiceDict]:
    """
    Resolve the play's ``local_services`` expression through a real ansible-playbook run

    The expression is read from the playbook itself, so the test follows whatever the play defines.

    :param tmp_path: scratch directory
    :param extra: extra ansible-playbook arguments (for example an inventory override)
    :return: the list the play would hand to every role
    """
    play = yaml.safe_load(PLAYBOOK.read_text(encoding='utf-8'))[0]
    dest = tmp_path / 'resolved.json'
    tasks = [
        {'ansible.builtin.set_fact': {'local_services': play['vars']['local_services']}},
        {'ansible.builtin.copy': {'content': '{{ local_services | to_json }}', 'dest': str(dest)}},
    ]
    code, output = _run_tasks(tmp_path, 'tailscale', tasks, '-e', f'@{LOCAL_SERVICES}', *extra)
    assert code == 0, output
    return json.loads(dest.read_text(encoding='utf-8'))


class TestLocalServicesDefault:
    """
    Tests for playbooks/vars/local_services.yml
    """
    def test_list_is_not_empty(self) -> None:
        """
        Test that the default list names at least one service
        """
        assert _default_services()

    @pytest.mark.parametrize('service', _default_services(), ids=lambda service: service['name'])
    def test_entry_proxies_to_a_published_container_port(self, service: ServiceDict) -> None:
        """
        Test that each entry names an enabled compose service and a container port that service publishes
        """
        assert service['port'] in _container_ports(service['name'])

    def test_names_are_unique_dns_labels(self) -> None:
        """
        Test that names are unique lowercase DNS labels, so each is a valid <name>.local
        """
        names = [service['name'] for service in _default_services()]
        assert len(names) == len(set(names))
        assert all(re.fullmatch(r'[a-z0-9]([a-z0-9-]*[a-z0-9])?', name) for name in names)


class TestLocalServicesWiring:
    """
    Tests for how the NAS play defines local_services
    """
    def test_play_loads_the_default_file_and_defines_the_variable(self) -> None:
        """
        Test that the play loads the default list and derives local_services with an inventory override
        """
        play = yaml.safe_load(PLAYBOOK.read_text(encoding='utf-8'))[0]
        assert play['vars_files'] == ['vars/local_services.yml']
        assert play['vars']['local_services'] == '{{ local_services_override | default(local_services_default) }}'

    @needs_ansible
    def test_resolves_to_the_default_list(self, tmp_path: Path) -> None:
        """
        Test that without an override every role sees the default list
        """
        assert _resolved(tmp_path) == _default_services()

    @needs_ansible
    def test_inventory_override_replaces_the_list(self, tmp_path: Path) -> None:
        """
        Test that local_services_override replaces the whole default list
        """
        override = [{'name': 'kavita', 'port': 5000}]
        assert _resolved(tmp_path, '-e', json.dumps({'local_services_override': override})) == override


# ==================================================================================================
# Caddy
# ==================================================================================================

TAILSCALE_VARS = {
    'tailscale_hostname':     'nas',
    'tailscale_tailnet_name': 'tail1234.ts.net',
    'tailscale_services':     [
        {'name': 'sonarr', 'port': 8989, 'path': 'sonarr'},
        {'name': 'plex', 'port': 32400, 'dedicated_port': 32443},
    ],
}

SAMPLE_SERVICES = [{'name': 'jellyfin', 'port': 8096}, {'name': 'sonarr', 'port': 8989}]


def _caddyfile(tmp_path: Path, local_services: list[ServiceDict]) -> str:
    """
    Render the tailscale role's Caddyfile through the real template module
    """
    values = {**TAILSCALE_VARS, 'local_services': local_services}
    return _render(tmp_path, 'tailscale', 'Caddyfile.j2', '-e', json.dumps(values))


@needs_ansible
class TestCaddyfileLocalSites:
    """
    Real-render tests of roles/tailscale/templates/Caddyfile.j2
    """
    def test_each_entry_gets_a_plain_http_site(self, tmp_path: Path) -> None:
        """
        Test that every local_services entry becomes an http:// site proxying to its container
        """
        rendered = _caddyfile(tmp_path, SAMPLE_SERVICES)

        assert 'http://jellyfin.local {\n    reverse_proxy jellyfin:8096\n}' in rendered
        assert 'http://sonarr.local {\n    reverse_proxy sonarr:8989\n}' in rendered

    def test_tailscale_routes_are_unchanged(self, tmp_path: Path) -> None:
        """
        Test that the Tailscale HTTPS blocks still render alongside the local sites
        """
        rendered = _caddyfile(tmp_path, SAMPLE_SERVICES)

        assert 'https://nas.tail1234.ts.net {' in rendered
        assert 'handle /sonarr/* {' in rendered
        assert 'https://nas.tail1234.ts.net:32443 {' in rendered

    def test_local_sites_are_never_https(self, tmp_path: Path) -> None:
        """
        Test that each name appears once, as an http:// address only
        """
        rendered = _caddyfile(tmp_path, SAMPLE_SERVICES)

        assert 'https://jellyfin.local' not in rendered
        assert rendered.count('http://jellyfin.local') == 1

    def test_empty_list_renders_no_local_sites(self, tmp_path: Path) -> None:
        """
        Test that an empty list leaves the Caddyfile without any .local site
        """
        assert '.local' not in _caddyfile(tmp_path, [])

    def test_missing_list_fails_loudly(self, tmp_path: Path) -> None:
        """
        Test that rendering without local_services fails instead of silently dropping the sites
        """
        task = {
            'ansible.builtin.template': {
                'src':  str(ROLES / 'tailscale' / 'templates' / 'Caddyfile.j2'),
                'dest': str(tmp_path / 'rendered'),
            },
        }
        code, output = _run_tasks(tmp_path, 'tailscale', [task], '-e', json.dumps(TAILSCALE_VARS))

        assert code != 0
        assert 'local_services' in output


class TestCaddyCompose:
    """
    Tests for services/caddy/compose.yml
    """
    def test_publishes_port_80(self) -> None:
        """
        Test that the caddy container publishes host port 80 for the .local sites
        """
        compose = yaml.safe_load((REPO_ROOT / 'services' / 'caddy' / 'compose.yml').read_text(encoding='utf-8'))
        assert '80:80' in compose['services']['caddy']['ports']


# ==================================================================================================
# mdns role: tasks
# ==================================================================================================

MDNS_ROLE      = ROLES / 'mdns'
PUBLISH_SCRIPT = MDNS_ROLE / 'files' / 'nas-mdns-publish'

TaskDict = dict[str, Any]  # Any: heterogeneous, yaml-loaded task structure

FILE_TASKS  = ['Configure Avahi', 'Install the mDNS name publisher', 'Install the mDNS publisher unit']
CHECK_TASKS = ['Require at least one local_services entry', 'Require local_services names that are plain DNS labels']


def _runnable(task: TaskDict) -> TaskDict:
    """
    Adapt a role task to run outside the role as a non-root user

    Sources become absolute, and ``owner``/``group`` are dropped because chown to root fails for an unprivileged user.
    """
    adapted = {key: value for key, value in task.items() if key not in {'notify', 'become'}}
    for module in ('ansible.builtin.copy', 'ansible.builtin.template'):
        if module in adapted:
            args   = {key: value for key, value in adapted[module].items() if key not in {'owner', 'group'}}
            subdir = 'files' if module.endswith('copy') else 'templates'
            args['src'] = str(MDNS_ROLE / subdir / args['src'])
            adapted[module] = args
    return adapted


def _tasks_named(names: list[str]) -> list[TaskDict]:
    """
    Load the named tasks from the role's tasks/main.yml, runnable in a scratch play
    """
    tasks   = yaml.safe_load((MDNS_ROLE / 'tasks' / 'main.yml').read_text(encoding='utf-8'))
    by_name = {task['name']: task for task in tasks}
    return [_runnable(by_name[name]) for name in names]


def _vars(tmp_path: Path, **overrides: Any) -> list[str]:  # Any: JSON-serializable test values
    """
    Build the ``-e`` argument (JSON) that points the role at scratch paths and gives it complete settings
    """
    values = {
        'local_services':   SAMPLE_SERVICES,
        'mdns_interface':   'br0',
        'mdns_avahi_conf':  str(tmp_path / 'avahi-daemon.conf'),
        'mdns_script_path': str(tmp_path / 'nas-mdns-publish'),
        'mdns_unit_path':   str(tmp_path / 'nas-mdns-publish.service'),
        **overrides,
    }
    return ['-e', json.dumps(values)]


@needs_ansible
class TestMdnsFiles:
    """
    Real-run tests of the file-writing tasks in roles/mdns/tasks/main.yml
    """
    def test_writes_the_three_files_then_converges(self, tmp_path: Path) -> None:
        """
        Test that the first run writes the config, script and unit, and a second run changes nothing
        """
        code, output = _run_tasks(tmp_path, 'mdns', _tasks_named(FILE_TASKS), *_vars(tmp_path))
        assert code == 0, output
        assert 'changed=3' in output, output

        conf = (tmp_path / 'avahi-daemon.conf').read_text(encoding='utf-8')
        assert 'allow-interfaces=br0' in conf
        assert 'use-ipv4=yes' in conf
        assert 'use-ipv6=no' in conf

        script = tmp_path / 'nas-mdns-publish'
        unit   = (tmp_path / 'nas-mdns-publish.service').read_text(encoding='utf-8')
        assert os.access(script, os.X_OK)
        assert f'ExecStart={script} jellyfin sonarr\n' in unit
        assert 'Requires=avahi-daemon.service' in unit

        code, output = _run_tasks(tmp_path, 'mdns', _tasks_named(FILE_TASKS), *_vars(tmp_path))
        assert code == 0, output
        assert 'changed=0' in output, output


@needs_ansible
class TestMdnsChecks:
    """
    Real-run tests of the assertions that guard the unit's ExecStart line
    """
    @pytest.mark.parametrize('name', ['sonarr', 'my-app', 'a1', 'x'])
    def test_plain_dns_labels_pass(self, tmp_path: Path, name: str) -> None:
        """
        Test that lowercase letters, digits and inner hyphens are accepted
        """
        variables    = _vars(tmp_path, local_services=[{'name': name, 'port': 1}])
        code, output = _run_tasks(tmp_path, 'mdns', _tasks_named(CHECK_TASKS), *variables)
        assert code == 0, output

    @pytest.mark.parametrize('name', ['Sonarr', 'my_app', '-lead', 'trail-', 'a.b', '', 'sonarr\n'])
    def test_other_names_fail(self, tmp_path: Path, name: str) -> None:
        """
        Test that uppercase, underscores, edge hyphens, dots, empty names and a trailing newline are all refused
        """
        variables    = _vars(tmp_path, local_services=[{'name': name, 'port': 1}])
        code, output = _run_tasks(tmp_path, 'mdns', _tasks_named(CHECK_TASKS), *variables)
        assert code != 0
        assert 'DNS label' in output

    def test_empty_list_fails(self, tmp_path: Path) -> None:
        """
        Test that publishing nothing is an error rather than a unit that exits at once
        """
        code, output = _run_tasks(tmp_path, 'mdns', _tasks_named(CHECK_TASKS), *_vars(tmp_path, local_services=[]))
        assert code != 0
        assert 'at least one' in output


class TestMdnsHandlerFlush:
    """
    Structural test of the end of roles/mdns/tasks/main.yml
    """
    def test_final_task_flushes_handlers(self) -> None:
        """
        Test that handlers run inside the role, so a later role failing cannot leave Avahi or the publisher stale
        """
        tasks = yaml.safe_load((MDNS_ROLE / 'tasks' / 'main.yml').read_text(encoding='utf-8'))
        final = {key: value for key, value in tasks[-1].items() if key != 'name'}
        assert final == {'ansible.builtin.meta': 'flush_handlers'}


# ==================================================================================================
# mdns role: publisher script
# ==================================================================================================

# ip -4 route get 1.1.1.1 (prints a source address unless FAKE_NO_ROUTE is set)
FAKE_IP = """#!/usr/bin/env bash
if [[ -n "${FAKE_NO_ROUTE:-}" ]]; then
    echo 'RTNETLINK answers: Network is unreachable' >&2
    exit 2
fi
echo '1.1.1.1 via 192.168.1.1 dev br0 src 192.168.1.50 uid 1000'
echo '    cache'
"""

# avahi-publish -a -R NAME ADDRESS: log "pid args", then live until killed (one second when it is FAKE_SHORT_LIVED)
FAKE_AVAHI_PUBLISH = """#!/usr/bin/env bash
echo "$$ $*" >> "${FAKE_LOG}"
if [[ "$3" == "${FAKE_SHORT_LIVED:-}" ]]; then
    exec sleep 1
fi
exec sleep 60
"""


@pytest.fixture
def stub_bin(tmp_path: Path) -> Path:
    """
    Create a directory holding stub ip and avahi-publish binaries

    :return: the directory, to be put first on PATH
    """
    bindir = tmp_path / 'bin'
    bindir.mkdir()
    for name, body in (('ip', FAKE_IP), ('avahi-publish', FAKE_AVAHI_PUBLISH)):
        stub = bindir / name
        stub.write_text(body, encoding='utf-8')
        stub.chmod(0o755)
    return bindir


@contextmanager
def _publisher(tmp_path: Path, stub_bin: Path, *names: str, **extra: str) -> Iterator[subprocess.Popen[str]]:
    """
    Run the publisher script with the stubs on PATH, and make sure it is gone afterwards
    """
    env = {
        **os.environ,
        'PATH':     f'{stub_bin}:{os.environ["PATH"]}',
        'FAKE_LOG': str(tmp_path / 'publish.log'),
        **extra,
    }
    proc = subprocess.Popen(
        [str(PUBLISH_SCRIPT), *names],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        yield proc
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait()
        if proc.stderr is not None:
            proc.stderr.close()


def _wait_for_lines(log: Path, count: int) -> list[str]:
    """
    Wait up to ten seconds for the stub log to hold ``count`` lines, and return them
    """
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        lines = log.read_text(encoding='utf-8').splitlines() if log.exists() else []
        if len(lines) >= count:
            return lines
        time.sleep(0.05)
    raise AssertionError(f'expected {count} publisher starts in {log}')


def _gone(pid: int) -> bool:
    """
    Return whether a process has exited, allowing it up to three seconds to do so
    """
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.05)
    return False


def _stderr(proc: subprocess.Popen[str]) -> str:
    """
    Read what the finished process wrote to stderr
    """
    assert proc.stderr is not None
    return proc.stderr.read()


class TestPublishScript:
    """
    Real-run tests of roles/mdns/files/nas-mdns-publish with stub ip and avahi-publish binaries
    """
    def test_publishes_an_address_record_per_name(self, tmp_path: Path, stub_bin: Path) -> None:
        """
        Test that each name is published as <name>.local at the default-route address, and SIGTERM exits 0
        """
        with _publisher(tmp_path, stub_bin, 'jellyfin', 'sonarr') as proc:
            lines = _wait_for_lines(tmp_path / 'publish.log', 2)
            proc.send_signal(signal.SIGTERM)
            assert proc.wait(timeout=10) == 0

        published = sorted(line.split(' ', 1)[1] for line in lines)
        assert published == ['-a -R jellyfin.local 192.168.1.50', '-a -R sonarr.local 192.168.1.50']

    def test_sigterm_stops_every_publisher(self, tmp_path: Path, stub_bin: Path) -> None:
        """
        Test that stopping the script also stops the avahi-publish processes it started
        """
        with _publisher(tmp_path, stub_bin, 'jellyfin', 'sonarr') as proc:
            lines = _wait_for_lines(tmp_path / 'publish.log', 2)
            proc.send_signal(signal.SIGTERM)
            proc.wait(timeout=10)

        assert all(_gone(int(line.split(' ', 1)[0])) for line in lines)

    def test_exits_1_and_stops_the_rest_when_a_publisher_dies(self, tmp_path: Path, stub_bin: Path) -> None:
        """
        Test that one publisher exiting ends the script with status 1 and takes the survivors down with it
        """
        with _publisher(tmp_path, stub_bin, 'jellyfin', 'sonarr', FAKE_SHORT_LIVED='sonarr.local') as proc:
            lines = _wait_for_lines(tmp_path / 'publish.log', 2)
            assert proc.wait(timeout=15) == 1
            assert 'exited' in _stderr(proc)

        jellyfin_pid = next(int(line.split(' ', 1)[0]) for line in lines if 'jellyfin.local' in line)
        assert _gone(jellyfin_pid)

    def test_no_default_route_exits_1_without_publishing(self, tmp_path: Path, stub_bin: Path) -> None:
        """
        Test that a missing IPv4 default route is reported and nothing is published
        """
        with _publisher(tmp_path, stub_bin, 'jellyfin', FAKE_NO_ROUTE='1') as proc:
            assert proc.wait(timeout=10) == 1
            assert 'no IPv4 address' in _stderr(proc)

        assert not (tmp_path / 'publish.log').exists()

    def test_no_names_exits_2(self, tmp_path: Path, stub_bin: Path) -> None:
        """
        Test that running without names is a usage error
        """
        with _publisher(tmp_path, stub_bin) as proc:
            assert proc.wait(timeout=10) == 2
            assert 'no names' in _stderr(proc)
