"""
Tests for the per-service ``.local`` hostnames: the shared ``local_services`` list, the Caddy ``http://`` sites that
route them, and the ``mdns`` role that announces them

Tasks, templates and scripts run for real (ansible-playbook against localhost, stub binaries on PATH); see
CLAUDE-LESSONS.md, "String-matching Ansible YAML is not verification: run the role".
"""
from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING
from typing import Any

import pytest
import yaml

from tests.unit.roles.test_alerting_roles import REPO_ROOT
from tests.unit.roles.test_alerting_roles import _run_tasks
from tests.unit.roles.test_alerting_roles import needs_ansible

if TYPE_CHECKING:
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
