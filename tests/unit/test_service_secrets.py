"""
Tests for per-service secret templates: their rendering and the compose env_file contract
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import jinja2
import pytest
import yaml

REPO_ROOT    = Path(__file__).resolve().parents[2]
SERVICES_DIR = REPO_ROOT / 'services'
DOCKER_ENV   = REPO_ROOT / 'roles' / 'docker' / 'templates' / 'env.j2'

SECRET_TEMPLATES = sorted(SERVICES_DIR.glob('*/env.j2'))


def _compose_services(service_dir: Path) -> dict[str, dict[str, Any]]:  # Any: yaml-loaded compose structure
    """
    Load the services mapping from a service's compose file (enabled or .disabled)
    """
    candidates = [service_dir / 'compose.yml', service_dir / 'compose.yml.disabled']
    compose = next(path for path in candidates if path.exists())
    return yaml.safe_load(compose.read_text(encoding='utf-8'))['services']


def _env_files(service: dict[str, Any]) -> list[str]:  # Any: yaml-loaded compose structure
    """
    Normalise a compose service's env_file (absent, string, or list) to a list
    """
    value = service.get('env_file', [])
    return [value] if isinstance(value, str) else list(value)


class TestPiholeSecret:
    """
    Tests for the PiHole password template
    """
    def test_renders_the_password_variable(self) -> None:
        """
        Test that env.j2 turns the vault variable into the FTL setting
        """
        template = jinja2.Template((SERVICES_DIR / 'pihole' / 'env.j2').read_text(encoding='utf-8'))

        # Plain Jinja drops one trailing newline; Ansible's template module keeps it
        rendered = template.render(pihole_web_password='s3cret')
        assert rendered.rstrip('\n') == 'FTLCONF_webserver_api_password=s3cret'

    def test_global_env_keeps_only_non_secret_values(self) -> None:
        """
        Test that the shared ~/docker/.env no longer carries the PiHole password
        """
        text = DOCKER_ENV.read_text(encoding='utf-8')

        assert 'ADVERTISE_IP=' in text
        assert 'pihole' not in text.lower()
        assert 'password' not in text.lower()

    def test_global_env_renders_without_the_tailscale_roles_defaults(self) -> None:
        """
        Test that ADVERTISE_IP renders when only the inventory's tailnet name is set

        The docker role runs before the tailscale role, so tailscale_hostname (a default of that role) is undefined here
        """
        template = jinja2.Template(DOCKER_ENV.read_text(encoding='utf-8'), undefined=jinja2.StrictUndefined)

        rendered = template.render(inventory_hostname='nas', tailscale_tailnet_name='tail1234.ts.net')

        assert rendered.strip() == 'ADVERTISE_IP=https://nas.tail1234.ts.net:32443'

    def test_global_env_prefers_an_explicit_tailscale_hostname(self) -> None:
        """
        Test that an inventory-set tailscale_hostname still wins over the inventory name
        """
        template = jinja2.Template(DOCKER_ENV.read_text(encoding='utf-8'), undefined=jinja2.StrictUndefined)

        rendered = template.render(
            inventory_hostname='nas', tailscale_hostname='media', tailscale_tailnet_name='tail1234.ts.net',
        )

        assert rendered.strip() == 'ADVERTISE_IP=https://media.tail1234.ts.net:32443'

    def test_compose_reads_the_service_env_file_without_a_shadowing_entry(self) -> None:
        """
        Test that PiHole loads pihole/.env and has no bare environment entry that could shadow it
        """
        service = _compose_services(SERVICES_DIR / 'pihole')['pihole']

        assert _env_files(service) == ['pihole/.env']
        assert 'FTLCONF_webserver_api_password' not in service['environment']


class TestEnvFileContract:
    """
    Tests that every secret template is consumed by its own service
    """
    @pytest.mark.parametrize('template', SECRET_TEMPLATES, ids=lambda path: path.parent.name)
    def test_service_reads_its_rendered_env_file(self, template: Path) -> None:
        """
        Test that services/<svc>/env.j2 has a matching env_file entry (<svc>/.env, relative to ~/docker)
        """
        service_dir = template.parent
        services    = _compose_services(service_dir).values()

        assert any(f'{service_dir.name}/.env' in _env_files(service) for service in services)
