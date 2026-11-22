# Per-Service `.local` Hostnames Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every NAS web UI reachable as `http://<name>.local` (for example `http://jellyfin.local`) with no port.

**Architecture:** A new `mdns` Ansible role installs Avahi and a systemd unit that publishes one `<name>.local` address
record per service, all pointing at the NAS's LAN IPv4 address. The existing Caddy container gains a plain-HTTP `:80`
site per name that proxies to `<name>:<port>` on `nas-network`. One list, `local_services`, feeds both halves.

**Tech Stack:** Ansible (roles, Jinja templates), Avahi (`avahi-daemon`, `avahi-publish`), systemd, Caddy 2, Docker
Compose, pytest (real `ansible-playbook` runs against localhost plus stub binaries on `PATH`).

**Spec:** `~/dotfiles-personal/docs/plans/2026-11/2026-11-21-local-mdns-hostnames-design.md`

**Paths:** Paths in task headings are rooted at the repository, `~/dotfiles-personal`. Implementation happens in the
worktree `~/dotfiles-personal/.claude/worktrees/local-mdns-hostnames`, which mirrors the repository, and every command
below runs from that worktree root (the session's working directory).

**Commits:** The commit steps run only after the user has authorized commits for this work.

## Global Constraints

- Transport is plain HTTP on port 80. No HTTPS, no local CA. The Tailscale HTTPS routes are unchanged.
- Hostnames are exactly the `local_services` entries: glance (8080), plex (32400), jellyfin (8096), sonarr (8989),
  radarr (7878), prowlarr (9696), transmission (9091). Ports are the container-side ports on `nas-network`.
- `homeassistant.local` is not published (HAOS announces it itself). ntfy, flaresolverr and autoplex get no name.
- `local_services` default lives in `playbooks/vars/local_services.yml` as `local_services_default`; the play defines
  `local_services: "{{ local_services_override | default(local_services_default) }}"`; inventory overrides with
  `local_services_override`.
- Avahi uses `use-ipv6=no` and `allow-interfaces=<default-route interface>`. The publisher resolves the IP when it
  starts, not at render time.
- The `mdns` role runs after `samba` and before `docker`, with the role-name tag `mdns` (apply tag plus include tag).
- Python: single quotes, `from __future__ import annotations`, one import per line, multi-line docstrings, `-> None` on
  every test. Never run `ruff format`; run `uv run ruff check --fix` on edited Python files. Add an import in the same
  edit as its first use (the edit-time ruff hook strips unused imports).
- Markdown: 120-column lines; format changed READMEs with `uv run mdformat <files>`. `.ctx/` and `docs/plans/` are
  hand-maintained and excluded from the formatter.
- Run Python only through `uv run`. Use `$TMPDIR`, never `/tmp`.

## File Structure

| File                                                                  | Responsibility                                                     |
| --------------------------------------------------------------------- | ------------------------------------------------------------------ |
| `playbooks/vars/local_services.yml` (create)                          | Default hostname list `local_services_default`                     |
| `playbooks/nas_bootstrap.yml` (modify)                                | Load the default list, define `local_services`, include `mdns`     |
| `roles/tailscale/templates/Caddyfile.j2` (modify)                     | One `http://<name>.local` site per entry                           |
| `services/caddy/compose.yml` (modify)                                 | Publish host port 80                                               |
| `roles/mdns/defaults/main.yml` (create)                               | `mdns_interface` and the three destination paths                   |
| `roles/mdns/tasks/main.yml` (create)                                  | Validate names, install Avahi, publisher script and unit, start    |
| `roles/mdns/handlers/main.yml` (create)                               | Restart Avahi and the publisher on change                          |
| `roles/mdns/files/nas-mdns-publish` (create)                          | Run one `avahi-publish` per name until stopped                     |
| `roles/mdns/templates/avahi-daemon.conf.j2` (create)                  | Avahi settings (IPv4 only, one interface)                          |
| `roles/mdns/templates/nas-mdns-publish.service.j2` (create)           | systemd unit that runs the script with the names                   |
| `roles/mdns/README.md` (create)                                       | Role documentation                                                 |
| `tests/unit/roles/test_local_hostnames.py` (create)                   | Tests for the list, Caddy sites, `mdns` role tasks and script      |
| `tests/unit/bootstrap/nas/test_nas_playbook.py` (modify)              | `EXPECTED_ORDER` gains `mdns`                                      |
| Docs: `roles/README.md`, `playbooks/README.md`, `README.md`, `.ctx/ARCHITECTURE.md`, `.ctx/BUILD.md`, `services/README.md`, `roles/tailscale/README.md` | Role rows, order, new section |

---

### Task 1: The shared `local_services` list

**Files:**
- Create: `~/dotfiles-personal/playbooks/vars/local_services.yml`
- Modify: `~/dotfiles-personal/playbooks/nas_bootstrap.yml:3-6`
- Create: `~/dotfiles-personal/tests/unit/roles/test_local_hostnames.py`

**Interfaces:**
- Produces: play variable `local_services`, a list of `{name: str, port: int}` dicts, defined for every role in the
  play. Later tasks read it as `local_services` in templates and tasks. Helpers in the test module: `_default_services()`,
  `_container_ports(name)`, `_resolved(tmp_path, *extra)`; constants `PLAYBOOK`, `LOCAL_SERVICES`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/roles/test_local_hostnames.py`:

```python
"""
Tests for the per-service ``.local`` hostnames: the shared ``local_services`` list, the Caddy ``http://`` sites that
route them, and the ``mdns`` role that announces them

Tasks, templates and scripts run for real (ansible-playbook against localhost, stub binaries on PATH); see
CLAUDE-LESSONS.md, "String-matching Ansible YAML is not verification: run the role".
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.unit.roles.test_alerting_roles import REPO_ROOT
from tests.unit.roles.test_alerting_roles import _run_tasks
from tests.unit.roles.test_alerting_roles import needs_ansible

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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/roles/test_local_hostnames.py -v`
Expected: collection error, `FileNotFoundError` for `playbooks/vars/local_services.yml` (the parametrize call reads it
at import time).

- [ ] **Step 3: Create the default list**

Create `playbooks/vars/local_services.yml`:

```yaml
---
# Default hostnames for the NAS's web UIs. Each name becomes <name>.local, published over mDNS by the mdns role and
# routed by a Caddy http:// site (rendered by the tailscale role) to <name>:<port> on nas-network. The inventory replaces
# the whole list by setting local_services_override.
local_services_default:
  - {name: glance, port: 8080}
  - {name: plex, port: 32400}
  - {name: jellyfin, port: 8096}
  - {name: sonarr, port: 8989}
  - {name: radarr, port: 7878}
  - {name: prowlarr, port: 9696}
  - {name: transmission, port: 9091}
```

- [ ] **Step 4: Wire the list into the play**

In `playbooks/nas_bootstrap.yml`, replace the play header (lines 2-6)

```yaml
- name: Home NAS bootstrap
  hosts: nas
  vars:
    # The NAS clone of this repository: the dotfiles role clones it, the haos role runs vms/haos/setup.sh from it
    dotfiles_repo_dir: "{{ ansible_facts['user_dir'] }}/dotfiles-personal"
```

with

```yaml
- name: Home NAS bootstrap
  hosts: nas
  vars_files:
    - vars/local_services.yml
  vars:
    # The NAS clone of this repository: the dotfiles role clones it, the haos role runs vms/haos/setup.sh from it
    dotfiles_repo_dir: "{{ ansible_facts['user_dir'] }}/dotfiles-personal"
    # Web-UI hostnames, read by the mdns role (mDNS names) and the tailscale role (Caddy http:// sites). The default list
    # is in vars/local_services.yml; an inventory sets local_services_override to replace it
    local_services: "{{ local_services_override | default(local_services_default) }}"
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/roles/test_local_hostnames.py tests/unit/bootstrap/nas/test_nas_playbook.py -v`
Expected: all PASS, including `TestPlaybookSyntax::test_syntax_check_passes`.

- [ ] **Step 6: Lint**

Run: `uv run ruff check --fix tests/unit/roles/test_local_hostnames.py` and
`uv run yamllint playbooks/nas_bootstrap.yml playbooks/vars/local_services.yml`
Expected: no findings.

- [ ] **Step 7: Commit**

```bash
git add docs/plans/2026-11/2026-11-21-local-mdns-hostnames-design.md docs/plans/2026-11/2026-11-21-local-mdns-hostnames-plan.md playbooks/vars/local_services.yml playbooks/nas_bootstrap.yml tests/unit/roles/test_local_hostnames.py
git commit -m "Add the local_services hostname list and wire it into the NAS play"
```

### Task 2: Caddy plain-HTTP sites

**Files:**
- Modify: `~/dotfiles-personal/roles/tailscale/templates/Caddyfile.j2:1,34`
- Modify: `~/dotfiles-personal/services/caddy/compose.yml:7-9`
- Modify: `~/dotfiles-personal/roles/tailscale/defaults/main.yml:15`
- Modify: `~/dotfiles-personal/tests/unit/roles/test_local_hostnames.py`

**Interfaces:**
- Consumes: `local_services` (list of `{name, port}`), from Task 1.
- Produces: for each entry, a Caddy site `http://<name>.local` that runs `reverse_proxy <name>:<port>`; the caddy
  container publishes host port 80. Test helpers: `_caddyfile(tmp_path, local_services)`, `TAILSCALE_VARS`.

- [ ] **Step 1: Write the failing tests**

In `tests/unit/roles/test_local_hostnames.py`, add these imports in the same edit as the tests below (alphabetical
within the existing `tests.unit.roles.test_alerting_roles` group):

```python
from tests.unit.roles.test_alerting_roles import ROLES
from tests.unit.roles.test_alerting_roles import _render
```

Append to the file:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/roles/test_local_hostnames.py -k "Caddy" -v`
Expected: 4 FAIL (`test_each_entry_gets_a_plain_http_site`, `test_local_sites_are_never_https`,
`test_missing_list_fails_loudly`, `test_publishes_port_80`) and 2 PASS (`test_tailscale_routes_are_unchanged`,
`test_empty_list_renders_no_local_sites`; they guard behavior that must not regress).

- [ ] **Step 3: Add the sites to the template**

In `roles/tailscale/templates/Caddyfile.j2`, change line 1 to

```
# Reverse proxy for NAS services: Tailscale HTTPS routes and plain-HTTP .local hostnames
```

and append after the final `{% endfor %}` (line 34), keeping one blank line between blocks:

```
{% for svc in local_services %}
# {{ svc.name | capitalize }} at http://{{ svc.name }}.local (name published over mDNS by the mdns role)
http://{{ svc.name }}.local {
    reverse_proxy {{ svc.name }}:{{ svc.port }}
}

{% endfor %}
```

An explicit `http://` address keeps Caddy from redirecting these sites to HTTPS, so no global option is needed.

- [ ] **Step 4: Publish port 80 and document the variable's origin**

In `services/caddy/compose.yml`, change the ports to

```yaml
    ports:
      - "80:80"
      - "443:443"
      - "32443:32443"
```

In `roles/tailscale/defaults/main.yml`, add below line 15 (`tailscale_services`):

```yaml
# local_services (the <name>.local sites) is a play variable, defined in playbooks/nas_bootstrap.yml
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/roles/test_local_hostnames.py tests/unit/test_docs_consistency.py -v`
Expected: all PASS.

- [ ] **Step 6: Lint**

Run: `uv run ruff check --fix tests/unit/roles/test_local_hostnames.py` and
`uv run yamllint services/caddy/compose.yml roles/tailscale/defaults/main.yml`
Expected: no findings.

- [ ] **Step 7: Commit**

```bash
git add roles/tailscale/templates/Caddyfile.j2 roles/tailscale/defaults/main.yml services/caddy/compose.yml tests/unit/roles/test_local_hostnames.py
git commit -m "Route the .local hostnames through Caddy on port 80"
```

### Task 3: The `mdns` role

**Files:**
- Create: `~/dotfiles-personal/roles/mdns/defaults/main.yml`
- Create: `~/dotfiles-personal/roles/mdns/tasks/main.yml`
- Create: `~/dotfiles-personal/roles/mdns/handlers/main.yml`
- Create: `~/dotfiles-personal/roles/mdns/files/nas-mdns-publish`
- Create: `~/dotfiles-personal/roles/mdns/templates/avahi-daemon.conf.j2`
- Create: `~/dotfiles-personal/roles/mdns/templates/nas-mdns-publish.service.j2`
- Create: `~/dotfiles-personal/roles/mdns/README.md`
- Modify: `~/dotfiles-personal/playbooks/nas_bootstrap.yml` (new include after `samba`)
- Modify: `~/dotfiles-personal/tests/unit/bootstrap/nas/test_nas_playbook.py:232`
- Modify: `~/dotfiles-personal/tests/unit/roles/test_local_hostnames.py`
- Modify (role rows): `roles/README.md`, `playbooks/README.md`, `README.md`, `.ctx/ARCHITECTURE.md`, `.ctx/BUILD.md`

**Interfaces:**
- Consumes: `local_services` (Task 1).
- Produces: `/usr/local/bin/nas-mdns-publish NAME...` (publishes `<NAME>.local` for each name, exit 1 when a publisher
  dies or no IPv4 default route exists, exit 2 with no names, exit 0 on SIGTERM/SIGINT); the unit
  `nas-mdns-publish.service`; role variables `mdns_interface`, `mdns_avahi_conf`, `mdns_script_path`,
  `mdns_unit_path`. Test helpers: `_runnable(task)`, `_tasks_named(names)`, `_vars(tmp_path, **overrides)`,
  `_publisher(tmp_path, stub_bin, *names, **extra)`, fixture `stub_bin`.

- [ ] **Step 1: Write the failing tests**

In `tests/unit/roles/test_local_hostnames.py`, extend the imports in the same edit as the tests below. The final
import block is:

```python
import json
import os
import re
import signal
import subprocess
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.unit.roles.test_alerting_roles import REPO_ROOT
from tests.unit.roles.test_alerting_roles import ROLES
from tests.unit.roles.test_alerting_roles import _render
from tests.unit.roles.test_alerting_roles import _run_tasks
from tests.unit.roles.test_alerting_roles import needs_ansible
```

Append to the file:

```python
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
```

Then append the script tests:

```python
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
```

- [ ] **Step 2: Put `mdns` into the expected playbook order**

In `tests/unit/bootstrap/nas/test_nas_playbook.py`, change `EXPECTED_ORDER` (line 232) to

```python
EXPECTED_ORDER = ['debian', 'zfs', 'backup', 'samba', 'mdns', 'docker', 'tailscale', 'dotfiles', 'haos', 'services']
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/roles/test_local_hostnames.py tests/unit/bootstrap/nas/test_nas_playbook.py -v`
Expected: every `TestMdnsFiles`, `TestMdnsChecks` and `TestPublishScript` test FAILS (missing role files:
`FileNotFoundError` or `No such file`), and `TestPlaybookOrder::test_role_order` FAILS (the include does not exist yet).
Task 1 and 2 tests still PASS.

- [ ] **Step 4: Create the role's defaults, handlers and tasks**

`roles/mdns/defaults/main.yml`:

```yaml
---
# Interface Avahi announces on: the default-route interface (br0 on the NAS, where the HAOS bridge takes over the NIC),
# so the names stay off Docker's bridges
mdns_interface: "{{ ansible_facts['default_ipv4']['interface'] }}"

# local_services (the hostnames to publish) is a play variable, defined in playbooks/nas_bootstrap.yml
mdns_avahi_conf: /etc/avahi/avahi-daemon.conf
mdns_script_path: /usr/local/bin/nas-mdns-publish
mdns_unit_path: /etc/systemd/system/nas-mdns-publish.service
```

`roles/mdns/handlers/main.yml`:

```yaml
---
- name: Restart Avahi
  become: true
  ansible.builtin.service:
    name: avahi-daemon
    state: restarted

- name: Restart the mDNS publisher
  become: true
  ansible.builtin.systemd:
    name: nas-mdns-publish.service
    state: restarted
```

`roles/mdns/tasks/main.yml`:

```yaml
---
- name: Require at least one local_services entry
  ansible.builtin.assert:
    that:
      - local_services | length > 0
    fail_msg: local_services is empty; there would be no hostnames to publish
    quiet: true

# The names reach the unit's ExecStart line, so they must be plain DNS labels. \Z, not $: $ also matches before a
# trailing newline, which would start a new line in the unit file.
- name: Require local_services names that are plain DNS labels
  ansible.builtin.assert:
    that:
      - mdns_service.name is match('^[a-z0-9]([a-z0-9-]*[a-z0-9])?\Z')
    fail_msg: "'{{ mdns_service.name }}' is not a lowercase DNS label, so it cannot be <name>.local"
    quiet: true
  loop: "{{ local_services }}"
  loop_control:
    loop_var: mdns_service
    label: "{{ mdns_service.name }}"

- name: Install Avahi
  become: true
  ansible.builtin.apt:
    pkg:
      - avahi-daemon
      - avahi-utils

- name: Configure Avahi
  become: true
  ansible.builtin.template:
    src: avahi-daemon.conf.j2
    dest: "{{ mdns_avahi_conf }}"
    owner: root
    group: root
    mode: "0644"
  notify: Restart Avahi

- name: Install the mDNS name publisher
  become: true
  ansible.builtin.copy:
    src: nas-mdns-publish
    dest: "{{ mdns_script_path }}"
    owner: root
    group: root
    mode: "0755"
  notify: Restart the mDNS publisher

- name: Install the mDNS publisher unit
  become: true
  ansible.builtin.template:
    src: nas-mdns-publish.service.j2
    dest: "{{ mdns_unit_path }}"
    owner: root
    group: root
    mode: "0644"
  notify: Restart the mDNS publisher

- name: Enable and start Avahi
  become: true
  ansible.builtin.service:
    name: avahi-daemon
    state: started
    enabled: true

# daemon_reload here picks up an edited unit before the restart handler runs at the end of the play
- name: Enable and start the mDNS publisher
  become: true
  ansible.builtin.systemd:
    name: nas-mdns-publish.service
    state: started
    enabled: true
    daemon_reload: true
```

- [ ] **Step 5: Create the templates and the script**

`roles/mdns/templates/avahi-daemon.conf.j2`:

```
# Generated by Ansible — do not edit manually
[server]
use-ipv4=yes
use-ipv6=no
allow-interfaces={{ mdns_interface }}
ratelimit-interval-usec=1000000
ratelimit-burst=1000

[wide-area]
enable-wide-area=yes

[publish]
publish-hinfo=no
publish-workstation=no

[reflector]

[rlimits]
rlimit-core=0
rlimit-data=4194304
rlimit-fsize=0
rlimit-nofile=768
rlimit-stack=4194304
rlimit-nproc=3
```

`roles/mdns/templates/nas-mdns-publish.service.j2`:

```
# Generated by Ansible — do not edit manually
[Unit]
Description=Publish .local hostnames for the NAS web UIs over mDNS
Documentation=man:avahi-publish(1)
Requires=avahi-daemon.service
After=avahi-daemon.service network-online.target
Wants=network-online.target

[Service]
ExecStart={{ mdns_script_path }} {{ local_services | map(attribute='name') | join(' ') }}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

`roles/mdns/files/nas-mdns-publish` (then `chmod 0755 roles/mdns/files/nas-mdns-publish`):

```bash
#!/usr/bin/env bash
# Publish <name>.local address records for the NAS's LAN IPv4 address, one avahi-publish per name, until stopped.
#
# Usage: nas-mdns-publish NAME...
#
# The address is the one the default route uses, read once when the script starts. If any publisher exits (for example
# because avahi-daemon restarted), the script stops the rest and exits 1, so systemd restarts the whole set with a fresh
# address lookup. SIGTERM and SIGINT stop every publisher and exit 0.
set -o errexit -o nounset -o pipefail

(( $# > 0 )) || { echo 'nas-mdns-publish: no names given' >&2; exit 2; }

ip_address="$(ip -4 route get 1.1.1.1 2>/dev/null | sed -n 's/.* src \([0-9.]*\).*/\1/p' || true)"
[[ -n "${ip_address}" ]] || { echo 'nas-mdns-publish: no IPv4 address on the default route' >&2; exit 1; }

pids=()
for name in "$@"; do
    avahi-publish -a -R "${name}.local" "${ip_address}" &
    pids+=("$!")
done

stop_publishers() {
    kill "${pids[@]}" 2>/dev/null || true
    wait "${pids[@]}" 2>/dev/null || true
}
trap 'stop_publishers; exit 0' TERM INT

while :; do
    for pid in "${pids[@]}"; do
        if ! kill -0 "${pid}" 2>/dev/null; then
            echo "nas-mdns-publish: publisher ${pid} exited; stopping the set so it restarts" >&2
            stop_publishers
            exit 1
        fi
    done
    sleep 1 &
    wait "$!"
done
```

The trap is installed after the publishers start, which keeps `"${pids[@]}"` non-empty (an empty array is an unbound
variable under `set -u` on older bash). `sleep 1 & wait "$!"` lets a signal interrupt the wait immediately.

- [ ] **Step 6: Include the role in the playbook**

In `playbooks/nas_bootstrap.yml`, insert after the Samba include (the block ending with `- configfile` at the end of
"Configure Samba file sharing") and before "Tasks for Docker":

```yaml
    # mDNS: Avahi plus a publisher for the <name>.local hostnames of the web UIs (Caddy's http:// sites route them)
    - name: Publish the .local hostnames
      ansible.builtin.include_role:
        name: roles/mdns
        apply:
          tags: mdns
      tags:
        - mdns
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/roles/test_local_hostnames.py tests/unit/bootstrap/nas/test_nas_playbook.py -v`
Expected: all PASS, including `TestPlaybookTags` for the `mdns` include and the syntax check. If
`test_exits_1_and_stops_the_rest_when_a_publisher_dies` is slow, that is the script's one-second poll, not a hang.

- [ ] **Step 8: Write the role README**

`roles/mdns/README.md` (a short file: no mdformat-toc block):

````markdown
[Project Root](../../README.md) > [Roles](../README.md) > **mdns**

# mdns

Announces a `<name>.local` hostname for each NAS web UI over mDNS, so `http://jellyfin.local` resolves on the home
network without a port. Runs between the `samba` and `docker` roles in
[`playbooks/nas_bootstrap.yml`](../../playbooks/nas_bootstrap.yml).

## How it fits

A client resolving `jellyfin.local` asks the network over mDNS and gets the NAS's LAN address from Avahi. It then
connects to port 80, where the `caddy` container's `http://jellyfin.local` site proxies to `jellyfin:8096`. This role is
the first half. The second half is rendered by the [`tailscale`](../tailscale/README.md) role's `Caddyfile.j2` from the
same `local_services` list, so a new name needs one edit.

## Tasks

All of `tasks/main.yml`, in order. Every step except the two assertions runs with `become`.

| Step | Task                                    | Effect                                                                                             |
| ---- | --------------------------------------- | -------------------------------------------------------------------------------------------------- |
| 1    | Require at least one `local_services` entry | Fails on an empty list                                                                          |
| 2    | Require names that are plain DNS labels | Fails on any name outside `[a-z0-9]` with inner hyphens (the names reach the unit's `ExecStart`)   |
| 3    | Install Avahi                           | `apt` install of `avahi-daemon` and `avahi-utils`                                                  |
| 4    | Configure Avahi                         | Renders `avahi-daemon.conf`: IPv4 only, announcing on `mdns_interface`; notifies the Avahi restart |
| 5    | Install the mDNS name publisher         | Copies `files/nas-mdns-publish` to `mdns_script_path` (mode `0755`)                                |
| 6    | Install the mDNS publisher unit         | Renders `nas-mdns-publish.service` with one name per `local_services` entry                        |
| 7    | Enable and start Avahi                  | Starts and enables `avahi-daemon`                                                                  |
| 8    | Enable and start the mDNS publisher     | Reloads systemd, then starts and enables `nas-mdns-publish.service`                                |

Handlers: `Restart Avahi` (after a config change) and `Restart the mDNS publisher` (after a script or unit change).

## Variables

| Variable          | Default                                                  | Purpose                                                       |
| ----------------- | -------------------------------------------------------- | ------------------------------------------------------------- |
| `local_services`  | play variable, from `playbooks/vars/local_services.yml`  | List of `{name, port}`; the role publishes each `name`        |
| `mdns_interface`  | the default-route interface (`br0` on the NAS)           | The only interface Avahi announces on                         |
| `mdns_avahi_conf` | `/etc/avahi/avahi-daemon.conf`                           | Destination of the rendered Avahi configuration               |
| `mdns_script_path` | `/usr/local/bin/nas-mdns-publish`                       | Destination of the publisher script                           |
| `mdns_unit_path`  | `/etc/systemd/system/nas-mdns-publish.service`           | Destination of the unit file                                  |

The default list is `playbooks/vars/local_services.yml`; set `local_services_override` in the inventory to replace it.

## The publisher

`nas-mdns-publish NAME...` runs one `avahi-publish -a -R <name>.local <address>` per name. The address is the one the
default route uses, read when the script starts, so a changed address needs
`sudo systemctl restart nas-mdns-publish`, not a re-provision. If any publisher exits (for example when `avahi-daemon`
restarts), the script stops the rest and exits 1, and systemd restarts the set.

## Checking it

```bash
systemctl status nas-mdns-publish
avahi-resolve -n jellyfin.local        # on the NAS: prints the NAS's address
dns-sd -G v4 jellyfin.local            # on a Mac on the same network
curl -sI http://jellyfin.local         # needs the caddy container from the tailscale role's Caddyfile
```
````

- [ ] **Step 9: Add the role to every doc that lists roles**

Edit each of these (the docs tests cover the first three; the last two have no test):

1. `roles/README.md`: add a row after `samba` in the Roles table:

   ```
   | [`mdns`](mdns/README.md)           | Avahi plus a systemd publisher announcing a `<name>.local` address record for each web UI (`local_services`) |
   ```

2. `playbooks/README.md`: in the numbered execution list, insert after step `05. **samba**` and renumber the rest:

   ```
   06. **mdns** - Avahi and a publisher for the `<name>.local` hostnames of the web UIs. Tags: `mdns`
   07. **docker** - Docker Engine and compose plugin, docker-group membership, the `~/docker` skeleton and shared `.env`,
       the autoplex image build, and `deploy.sh`; the stack itself is the `services` step. Tags: `docker`, `configfile`
   08. **tailscale** - Tailscale install and configuration, HTTPS certificates, and the Caddyfile Caddy reads. Tags:
       `tailscale`
   09. **dotfiles** - hands `$HOME` to the stow engine (clone, `profiles/nas` overlay, login shell, `bootstrap.sh`). Tags:
       `dotfiles`
   10. **haos** - Home Assistant OS VM via `vms/haos/setup.sh`. Tags: `haos`
   11. **services** - Compose sync, per-service secrets, deploy. Tags: `services`, `secrets`
   ```

   Also add `mdns` to the whole-role row of the Tags table (`debian`, `zfs`, `samba`, `mdns`, `docker`, ...).

3. `.ctx/ARCHITECTURE.md`: add after the `samba` bullet:

   ```
   - `mdns`: Avahi and a systemd publisher announcing `<name>.local` for each web UI in `local_services`
   ```

4. `.ctx/BUILD.md` line 27: change `system: debian,zfs,samba,docker,tailscale` to
   `system: debian,zfs,samba,mdns,docker,tailscale`.

5. `README.md` Project Structure tree: add after the `samba/` line, with the `#` aligned to its neighbors:

   ```
   │   ├── mdns/                               # Avahi hostnames (<name>.local) for the web UIs
   ```

Then format the changed READMEs (not `.ctx/`):

Run: `uv run mdformat roles/README.md roles/mdns/README.md playbooks/README.md README.md`
Expected: files reformatted in place (the Tasks and Variables tables get re-aligned).

- [ ] **Step 10: Run the tests, lint and commit**

Run: `uv run pytest tests/unit/roles tests/unit/bootstrap/nas tests/unit/test_docs_consistency.py -v`
Expected: all PASS.

Run: `uv run ruff check --fix tests/unit/roles/test_local_hostnames.py tests/unit/bootstrap/nas/test_nas_playbook.py`,
`uv run yamllint roles/mdns playbooks/nas_bootstrap.yml`, and
`scripts/hooks/ansible-lint.sh roles/mdns playbooks/nas_bootstrap.yml`
Expected: no findings. Also run `shellcheck roles/mdns/files/nas-mdns-publish` if shellcheck is installed; expected
clean.

```bash
git add roles/mdns playbooks/nas_bootstrap.yml playbooks/README.md roles/README.md README.md .ctx/ARCHITECTURE.md .ctx/BUILD.md tests/unit/roles/test_local_hostnames.py tests/unit/bootstrap/nas/test_nas_playbook.py
git commit -m "Add the mdns role to announce a .local hostname per web UI"
```

### Task 4: Documentation

**Files:**
- Modify: `~/dotfiles-personal/services/README.md` (Quick Reference caddy row, LAN access paragraph, new section, `caddy` section)
- Modify: `~/dotfiles-personal/roles/tailscale/README.md` (Features bullet, new section)
- Modify: `~/dotfiles-personal/.ctx/ARCHITECTURE.md` (Docker Stack, Network line)

**Interfaces:**
- Consumes: the behavior built in Tasks 1-3. Documents only what the code proves; what only the NAS can show goes in
  a "Clarifications needed" list, which Task 5's owner-run checks resolve.

- [ ] **Step 1: Update `services/README.md`**

1. Quick Reference, `caddy` row: set the ports cell to `80/tcp`, `443/tcp`, `32443/tcp` and the purpose to
   `Reverse proxy: Tailscale HTTPS and .local hostnames (see below)`.

2. LAN access paragraph (the one starting "LAN access is `http://<nas-host>:<port>`"): append the sentence
   `The web UIs also answer on http://<name>.local, without a port (see [Local hostnames](#local-hostnames)).`

3. Insert a new section between "Tailscale / HTTPS" and "Services", using the same heading-anchor style as its
   neighbors:

   ````markdown
   ## Local hostnames<a name="local-hostnames"></a>

   Each web UI in `local_services` answers on `http://<name>.local` over plain HTTP on the home network. The `mdns` role
   announces the name over mDNS (all names point at the NAS's LAN address), and `caddy` routes it by `Host` header to the
   container, through an `http://` site that the `tailscale` role renders into the Caddyfile. The list lives in
   [`playbooks/vars/local_services.yml`](../playbooks/vars/local_services.yml); an inventory replaces it by setting
   `local_services_override`.

   | URL                         | Container:port       |
   | --------------------------- | -------------------- |
   | `http://glance.local`       | `glance:8080`        |
   | `http://plex.local`         | `plex:32400`         |
   | `http://jellyfin.local`     | `jellyfin:8096`      |
   | `http://sonarr.local`       | `sonarr:8989`        |
   | `http://radarr.local`       | `radarr:7878`        |
   | `http://prowlarr.local`     | `prowlarr:9696`      |
   | `http://transmission.local` | `transmission:9091`  |

   `homeassistant.local` is announced by Home Assistant OS itself and is not part of this list. `ntfy` is loopback-only,
   and `flaresolverr` and `autoplex` have no web UI, so none of the three has a name.

   Clients need mDNS support: macOS, iOS and Windows 10 and later have it; Linux needs `nss-mdns`. Without it, use
   `http://<nas-host>:<port>`.

   The Caddyfile is a single-file bind mount, so a change that edits only the Caddyfile does not recreate the container;
   `docker restart caddy` makes it read the new file. A change to `compose.yml` (such as publishing port 80) is applied by
   `python3 run.py nas-deploy caddy`.

   **Clarifications needed** (only the NAS can answer these; see the checks in the
   [design doc](../docs/plans/2026-11/2026-11-21-local-mdns-hostnames-design.md)):

   - Whether `http://sonarr.local`, `radarr.local` and `prowlarr.local` redirect `/` to their `UrlBase` prefix, and
     `transmission.local` to `/transmission/web/`.
   - Whether Transmission's RPC host whitelist accepts the `transmission.local` hostname.
   ````

4. `caddy` service section: change "Publishes `443` and `32443`" to "Publishes `80`, `443` and `32443`" and add
   "Port 80 serves the plain-HTTP `.local` sites (see [Local hostnames](#local-hostnames))".

- [ ] **Step 2: Update `roles/tailscale/README.md`**

1. Features list: change the Caddyfile bullet to
   `- Renders the Caddyfile at /etc/caddy/Caddyfile (NAS only): the Tailscale HTTPS routes plus a plain-HTTP http://<name>.local site per local_services entry; ...` keeping the rest of the existing bullet text.

2. After the "Service Routing" section, add:

   ```markdown
   ## Local Hostnames<a name="local-hostnames"></a>

   The Caddyfile also gets one `http://<name>.local` site per entry of `local_services`, each proxying to
   `<name>:<port>` on `nas-network`. `local_services` is a play variable (defined in `playbooks/nas_bootstrap.yml` from
   `playbooks/vars/local_services.yml`), not a variable of this role; the template fails if it is undefined. The names
   themselves are announced by the [`mdns`](../mdns/README.md) role. See
   [`services/README.md`](../../services/README.md#local-hostnames) for the URL table.
   ```

3. Add `- [Local Hostnames](#local-hostnames)` to the table of contents after Service Routing (the mdformat run in
   Step 4 also regenerates it).

- [ ] **Step 3: Update `.ctx/ARCHITECTURE.md`**

In the Docker Stack list, change the Network line to

```
- **Network**: Caddy (reverse proxy: Tailscale HTTPS routes and plain-HTTP `.local` hostnames), PiHole (DNS/ad-blocking; disabled)
```

- [ ] **Step 4: Format and test**

Run: `uv run mdformat services/README.md roles/tailscale/README.md`
Expected: both reformatted in place (tables re-aligned, toc updated).

Run: `uv run pytest tests/unit/test_docs_consistency.py -v`
Expected: all PASS (the Quick Reference parser still finds every container row).

- [ ] **Step 5: Commit**

```bash
git add services/README.md roles/tailscale/README.md .ctx/ARCHITECTURE.md
git commit -m "Document the .local hostnames in the services and tailscale READMEs"
```

### Task 5: Full verification

**Files:** none modified unless a check fails.

- [ ] **Step 1: Run the whole unit suite**

Run: `uv run pytest tests/unit -q`
Expected: all PASS. If a test fails, read the failure and fix it in the task that owns the file; if it looks unrelated
to this work, confirm it also fails on `origin/main` before touching it.

- [ ] **Step 2: Run every repository hook**

Run: `prek run --all-files`
Expected: all hooks pass (yamllint, ansible-lint, mdformat, ruff check, shell checks). Fix any finding in the file it
names and re-run until clean.

- [ ] **Step 3: Render the Caddyfile once and read it**

Run (a throwaway render with sample values, written under `$TMPDIR`):

```bash
uv run ansible localhost -c local -m ansible.builtin.template \
  -a "src=roles/tailscale/templates/Caddyfile.j2 dest=$TMPDIR/Caddyfile.sample" \
  -e '{"tailscale_hostname":"nas","tailscale_tailnet_name":"tail1234.ts.net","tailscale_services":[],"local_services":[{"name":"jellyfin","port":8096}]}'
```

Open `$TMPDIR/Caddyfile.sample` with Read.
Expected: the `https://nas.tail1234.ts.net` block (with the hard-coded `/pihole` route) followed by a
`http://jellyfin.local { reverse_proxy jellyfin:8096 }` block, with a blank line between blocks.

- [ ] **Step 4: Review the branch**

Run: `git log --oneline origin/main..HEAD` and `git diff --stat origin/main..HEAD`
Expected: only the commits and files named in this plan, none from `gh-labels-sync`.

---

### Task 6: Rollout and on-NAS checks (owner-run)

These steps change the live NAS, so the owner runs them. The agent hands over the commands and records the answers.

- [ ] **Step 1: Before anything else, confirm port 80 is free (on the NAS)**

Run: `ss -ltn 'sport = :80'`
Expected: no listener (Pi-hole is disabled; its UI is on 8053).
This must come first: merging this branch redeploys the caddy container with port 80 published (CI runs
`deploy.sh caddy` on any push to `main` that changes `services/`), and a held port 80 would stop caddy and with it the
Tailscale HTTPS routes.

- [ ] **Step 2: Provision from the branch checkout, before merging (from the Mac)**

Run: `python3 run.py nas-provision --tags mdns,tailscale`
Do not run `--check` for the `mdns` role before its first run: it fails on a never-installed unit (see
[`playbooks/README.md`](../../../playbooks/README.md)). `python3 run.py nas-provision --check --diff --tags tailscale`
is fine as a preview of the Caddyfile change.
Expected: the `mdns` role installs Avahi and the publisher; the `tailscale` role writes the new Caddyfile; the running
caddy container still serves the old one and is unaffected.

- [ ] **Step 3: Merge the PR**

CI then runs `deploy.sh caddy`. Because `services/caddy/compose.yml` changed (port 80), the container is recreated and
reads the Caddyfile written in Step 2. If CI did not run (for example the workflow was skipped), run
`python3 run.py nas-deploy caddy` from the Mac.
Expected: the caddy container publishes `80`, `443` and `32443`.

- [ ] **Step 4: Check names and routes (on the NAS)**

```bash
systemctl status nas-mdns-publish
avahi-resolve -n jellyfin.local
curl -sI -H 'Host: jellyfin.local' http://127.0.0.1 | head -3
```

The plain `curl http://jellyfin.local` would need `libnss-mdns`, which the role does not install.
Repeat the last two lines for each name in `local_services`.
Expected: the publisher is `active (running)`, each name resolves to the NAS's LAN address, and each `curl` returns an
HTTP status line (a `302` redirect is fine).

- [ ] **Step 5: If a name resolves but its site does not answer on port 80 (on the NAS)**

Run: `docker restart caddy`, then repeat Step 4.
A running container keeps the old Caddyfile after Ansible replaces the file, because it is a single-file bind mount.
A Caddyfile-only change at any later time needs the same restart.

- [ ] **Step 6: Check from another device on the LAN**

On a Mac: `dns-sd -G v4 jellyfin.local`, then open each `http://<name>.local` in a browser.
Expected: every name loads its UI.

- [ ] **Step 7: Resolve the open questions and update the docs**

Record, for `sonarr`, `radarr`, `prowlarr` and `transmission`, where `http://<name>.local/` ends up, and whether
`http://transmission.local` loads or returns an error. Replace the two "Clarifications needed" bullets in
`services/README.md` with what was observed. If Transmission rejects the hostname, add the hostname to its RPC host
whitelist (the `HOST_WHITELIST` environment variable of the linuxserver image) in `services/transmission/compose.yml`,
and do not add a `Host` rewrite to Caddy (Plex and Jellyfin need the original `Host` for correct absolute URLs).
Re-run `uv run pytest tests/unit/test_docs_consistency.py` and commit the docs change.
