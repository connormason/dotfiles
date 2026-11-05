# NAS Sub-project 3: Deploy from the Laptop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provision the NAS and deploy its Compose services from the work MacBook with `run.py nas-provision` and
`run.py nas-deploy`, make a fresh NAS converge from one provisioning run, and add per-service secrets.

**Architecture:** One shell script (`scripts/nas/deploy-services.sh`) syncs `services/` to the NAS and runs
`~/docker/deploy.sh`; CI and `run.py nas-deploy` both call it. A new `services` Ansible role (last in the playbook)
syncs the same files, renders `services/*/env.j2` into `~/docker/<svc>/.env` (0600), and runs `deploy.sh all`.
`run.py nas-provision` wraps preflight checks plus `ansible-playbook` in the uv environment; `nas_bootstrap.sh` shrinks
to a wrapper over it.

**Tech Stack:** bash 3.2-compatible shell, Python 3.9 (`run.py`, pytest), Ansible (`ansible-core` plus `ansible.posix`
and `community.docker`), GitHub Actions, `prek` hooks.

**Spec:** [`2026-11-02-nas-laptop-deploy-design.md`](2026-11-02-nas-laptop-deploy-design.md). Parent design:
[`../2026-10/2026-10-31-nas-provisioning-design.md`](../2026-10/2026-10-31-nas-provisioning-design.md).

## Global Constraints

- Run all Python and pytest through `scripts/hooks/uv-public.sh run …`. Never bare `python`, `python3`, `pip`.
- Never run `ruff format`. `ruff check --fix` is fine.
- Python: `from __future__ import annotations` first; one import per line (isort `force-single-line`); single quotes;
  Python 3.9 syntax; sphinx-style docstrings; no blank line between a class docstring and its first member; no bare `Any`
  without a comment; exception chaining (`raise X from e`).
- Tests: multi-line docstrings (capitalised first word, no trailing period), `-> None` on every test method,
  `@pytest.mark.parametrize` tuple format, file names `test_*.py` under `tests/unit/`.
- Shell: bash 3.2-compatible (no `mapfile`, no associative arrays, no `${var,,}`); `shfmt` (4-space indent) and
  `shellcheck` clean. Executable bit set on new scripts.
- Ansible: fully-qualified module names; `changed_when` on every `command`/`shell`; `mode:` on every
  `file`/`template`/`copy`/`get_url`; loop variables prefixed with the role name; role variables prefixed with the role
  name.
- Line width 120 (code, docstrings, Markdown prose). Markdown under `docs/plans/` and `.ctx/` is hand-maintained; other
  Markdown is formatted by the `mdformat` prek hook.
- Never commit secrets, the vault password, or decrypted vault content. Never print vault values.
- Never push to `main`. Never run `ansible-playbook` against the real NAS from this session: the Claude sandbox cannot
  open LAN sockets, and live runs are the owner's (Task 11).
- Work happens in the worktree `/Users/connormason/dotfiles-personal/.claude/worktrees/nas-laptop-deploy` on branch
  `worktree-nas-laptop-deploy`. Use absolute paths. Git commands run from the current directory (no `git -C`).
- The inventory is a separate private repo; this plan changes nothing in it.
- Commit messages follow `type(scope): summary` (the `commit-formatter` convention already used in `git log`).

## File Structure

| Path                                          | Action | Responsibility                                                            |
| --------------------------------------------- | ------ | ------------------------------------------------------------------------- |
| `scripts/nas/deploy-services.sh`              | Create | rsync `services/` to the NAS and run `deploy.sh` (CI and laptop share it) |
| `scripts/nas/README.md`                       | Create | Directory README (usage, env vars)                                        |
| `.github/workflows/deploy.yml`                | Modify | Call the script instead of inline rsync/ssh                               |
| `run.py`                                      | Modify | `nas-provision`, `nas-deploy`, host resolution, preflight                 |
| `nas_bootstrap.sh`                            | Modify | Thin wrapper over `run.py nas-provision`                                  |
| `scripts/deploy_configs.sh`                   | Delete | Unreferenced                                                              |
| `roles/services/{tasks,defaults}/main.yml`    | Create | Sync, per-service secrets, deploy                                         |
| `roles/services/README.md`                    | Create | Role README                                                               |
| `roles/requirements.yml`                      | Modify | Add `ansible.posix`                                                       |
| `playbooks/nas_bootstrap.yml`                 | Modify | Include the `services` role last                                          |
| `roles/docker/tasks/main.yml`, `defaults/…`   | Modify | Fresh-install fixes, lint cleanup, drop `deploy.sh all`                   |
| `roles/docker/templates/env.j2`               | Modify | Keep only non-secret `ADVERTISE_IP`                                       |
| `services/pihole/env.j2`                      | Create | First per-service secret                                                  |
| `services/pihole/compose.yml.disabled`        | Modify | Read the per-service env file                                             |
| `.ansible-lint-ignore`                        | Modify | Drop the docker-role entries                                              |
| `vms/haos/setup.sh`                           | Modify | Add `usbutils` to `PACKAGES`                                              |
| `tests/unit/test_deploy_services.py`          | Create | Script behaviour with stubbed `rsync`/`ssh`                               |
| `tests/unit/test_deploy_workflow.py`          | Create | Workflow uses the shared script                                           |
| `tests/unit/test_run_nas.py`                  | Create | `nas-provision` / `nas-deploy` command construction and preflight         |
| `tests/unit/test_nas_bootstrap.py`            | Modify | Wrapper contract; drop installer-pin tests                                |
| `tests/unit/test_services_role.py`            | Create | `services` and `docker` role structure, playbook wiring                   |
| `tests/unit/test_service_secrets.py`          | Create | `env.j2` rendering and the compose `env_file` contract                    |
| `tests/unit/test_haos_setup.py`               | Modify | `usbutils` is a required package                                          |
| `Makefile`, `CLAUDE.md`, `.ctx/*.md`, `docs/…` | Modify | Docs made false by this change (Task 10)                                  |

---

### Task 1: Shared deploy script

**Files:**
- Create: `scripts/nas/deploy-services.sh`
- Test: `tests/unit/test_deploy_services.py`

**Interfaces:**
- Produces: `scripts/nas/deploy-services.sh [--dry-run] <service|all>`, configured by env `NAS_HOST` (required),
  `NAS_USER` (required), `NAS_SSH_KEY` (optional). Exit code 2 for usage/validation errors; otherwise the exit code of the
  failing `rsync`/`ssh`. Tasks 2 and 3 call it.

- [ ] **Step 1: Write the failing test**

Create `/Users/connormason/dotfiles-personal/.claude/worktrees/nas-laptop-deploy/tests/unit/test_deploy_services.py`:

```python
"""
Unit tests for scripts/nas/deploy-services.sh (stubbed rsync and ssh: no NAS or network needed)
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT    = Path(__file__).resolve().parents[2]
SCRIPT       = REPO_ROOT / 'scripts' / 'nas' / 'deploy-services.sh'
SERVICES_DIR = REPO_ROOT / 'services'
BASH         = '/bin/bash'  # macOS ships bash 3.2 here, the oldest interpreter the script must run under

pytestmark = pytest.mark.skipif(not Path(BASH).exists(), reason='/bin/bash not available')

# Each stub appends "<name> <args>" to $STUB_LOG, which the tests read back
STUB = '#!/bin/sh\nprintf "%s %s\\n" "$(basename "$0")" "$*" >> "$STUB_LOG"\n'


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    """
    Stubbed rsync and ssh first on PATH, plus the required NAS variables
    """
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    for name in ('rsync', 'ssh'):
        stub = bin_dir / name
        stub.write_text(STUB, encoding='utf-8')
        stub.chmod(0o755)

    return {
        **{key: value for key, value in os.environ.items() if not key.startswith('NAS_')},
        'PATH':     f'{bin_dir}:{os.environ["PATH"]}',
        'STUB_LOG': str(tmp_path / 'calls.log'),
        'NAS_HOST': 'nas.example',
        'NAS_USER': 'tester',
    }


def _run(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    """
    Run the script under /bin/bash with the given arguments
    """
    return subprocess.run([BASH, str(SCRIPT), *args], capture_output=True, text=True, check=False, env=env)


def _calls(env: dict[str, str]) -> list[str]:
    """
    Return the stub invocations recorded so far
    """
    log = Path(env['STUB_LOG'])
    return log.read_text(encoding='utf-8').splitlines() if log.exists() else []


class TestDeployOneService:
    """
    Tests for deploying a single service
    """
    def test_syncs_base_compose_and_service_then_deploys(self, env: dict[str, str]) -> None:
        """
        Test that one service rsyncs compose.base.yml and its directory, then runs deploy.sh over ssh
        """
        result = _run(env, 'glance')

        assert result.returncode == 0, result.stderr
        calls = _calls(env)
        assert len(calls) == 3
        assert calls[0].endswith(f'{SERVICES_DIR}/compose.base.yml tester@nas.example:~/docker/compose.base.yml')
        assert calls[1].endswith(f'{SERVICES_DIR}/glance/ tester@nas.example:~/docker/glance/')
        assert calls[2] == 'ssh tester@nas.example ~/docker/deploy.sh glance'

    def test_rsync_skips_templates_and_env_files(self, env: dict[str, str]) -> None:
        """
        Test that rsync never ships *.j2 templates or .env files, and never deletes
        """
        _run(env, 'glance')

        for call in _calls(env)[:2]:
            assert '--exclude=*.j2' in call
            assert '--exclude=.env'  in call
            assert '--delete'    not in call

    def test_key_adds_identity_and_host_key_policy(self, env: dict[str, str]) -> None:
        """
        Test that NAS_SSH_KEY reaches both the rsync transport and the ssh call
        """
        env['NAS_SSH_KEY'] = '/keys/id_nas'
        _run(env, 'glance')

        option = '-i /keys/id_nas -o StrictHostKeyChecking=accept-new'
        calls  = _calls(env)
        assert f'-e ssh {option}' in calls[0]
        assert calls[2] == f'ssh {option} tester@nas.example ~/docker/deploy.sh glance'


class TestDeployAll:
    """
    Tests for deploying every service
    """
    def test_syncs_whole_tree_then_deploys_all(self, env: dict[str, str]) -> None:
        """
        Test that 'all' rsyncs the whole services/ directory and runs deploy.sh all
        """
        result = _run(env, 'all')

        assert result.returncode == 0, result.stderr
        calls = _calls(env)
        assert len(calls) == 2
        assert calls[0].endswith(f'{SERVICES_DIR}/ tester@nas.example:~/docker/')
        assert calls[1] == 'ssh tester@nas.example ~/docker/deploy.sh all'


class TestDryRun:
    """
    Tests for --dry-run
    """
    def test_previews_rsync_and_never_runs_ssh(self, env: dict[str, str]) -> None:
        """
        Test that --dry-run adds rsync -n, skips ssh, and prints the command it would have run
        """
        result = _run(env, '--dry-run', 'glance')

        assert result.returncode == 0, result.stderr
        calls = _calls(env)
        assert len(calls) == 2
        assert all(call.startswith('rsync ') and ' -n ' in call for call in calls)
        assert 'dry-run: would run: ssh tester@nas.example ~/docker/deploy.sh glance' in result.stdout


class TestValidation:
    """
    Tests for argument and environment validation
    """
    @pytest.mark.parametrize(
        ('args', 'message'),
        [
            (('nonexistent',),   'no services/nonexistent/compose.yml'),
            (('homeassistant',), 'no services/homeassistant/compose.yml'),
            (('../etc',),        'invalid service name'),
            (('Glance',),        'invalid service name'),
            ((),                 'usage'),
            (('glance', 'plex'), 'usage'),
        ],
    )
    def test_rejects_bad_arguments_before_any_network_call(
        self, env: dict[str, str], args: tuple[str, ...], message: str,
    ) -> None:
        """
        Test that unknown, disabled, malformed, or missing service arguments exit 2 without calling rsync or ssh
        """
        result = _run(env, *args)

        assert result.returncode == 2
        assert message in result.stderr
        assert _calls(env) == []

    @pytest.mark.parametrize('missing', ['NAS_HOST', 'NAS_USER'])
    def test_requires_host_and_user(self, env: dict[str, str], missing: str) -> None:
        """
        Test that a missing NAS_HOST or NAS_USER exits 2 and names the variable
        """
        del env[missing]
        result = _run(env, 'glance')

        assert result.returncode == 2
        assert missing in result.stderr
        assert _calls(env) == []
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `scripts/hooks/uv-public.sh run pytest tests/unit/test_deploy_services.py -v`
Expected: FAIL — every test errors because `scripts/nas/deploy-services.sh` does not exist (non-zero exit / missing
file assertions).

- [ ] **Step 3: Write the script**

Create `/Users/connormason/dotfiles-personal/.claude/worktrees/nas-laptop-deploy/scripts/nas/deploy-services.sh`, then
`chmod +x` it:

```bash
#!/usr/bin/env bash
# Sync services/ to the NAS and run ~/docker/deploy.sh there. Shared by `run.py nas-deploy` and
# .github/workflows/deploy.yml so the laptop and CI cannot drift apart.
#
# Usage: NAS_HOST=<host> NAS_USER=<user> [NAS_SSH_KEY=<path>] deploy-services.sh [--dry-run] <service|all>
#
#   NAS_HOST     SSH host of the NAS (required)
#   NAS_USER     SSH user on the NAS (required)
#   NAS_SSH_KEY  private key to use, with host-key auto-accept (CI); unset to use the caller's SSH configuration
#
# rsync never deletes, and never ships *.j2 templates or .env files: secrets are rendered on the NAS by the `services`
# Ansible role, not copied from a checkout.
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
services_dir="${repo}/services"

die() {
    echo "deploy-services: $*" >&2
    exit 2
}

dry_run=0
if [[ "${1:-}" == "--dry-run" ]]; then
    dry_run=1
    shift
fi
[[ $# -eq 1 ]] || die "usage: deploy-services.sh [--dry-run] <service|all>"
service="$1"

[[ -n "${NAS_HOST:-}" ]] || die "NAS_HOST is not set"
[[ -n "${NAS_USER:-}" ]] || die "NAS_USER is not set"

# A service is a directory under services/; refuse anything that could escape it or reach the remote shell
if [[ "$service" != "all" ]]; then
    [[ "$service" =~ ^[a-z0-9][a-z0-9_-]*$ ]] || die "invalid service name: ${service}"
    [[ -f "${services_dir}/${service}/compose.yml" ]] || die "no services/${service}/compose.yml"
fi

target="${NAS_USER}@${NAS_HOST}"
ssh_cmd=(ssh)
if [[ -n "${NAS_SSH_KEY:-}" ]]; then
    ssh_cmd+=(-i "$NAS_SSH_KEY" -o StrictHostKeyChecking=accept-new)
fi

rsync_flags=(-avz --exclude='*.j2' --exclude='.env')
if [[ $dry_run -eq 1 ]]; then
    rsync_flags+=(-n)
fi

push() {
    rsync "${rsync_flags[@]}" -e "${ssh_cmd[*]}" "$1" "$2"
}

if [[ "$service" == "all" ]]; then
    push "${services_dir}/" "${target}:~/docker/"
else
    push "${services_dir}/compose.base.yml" "${target}:~/docker/compose.base.yml"
    push "${services_dir}/${service}/" "${target}:~/docker/${service}/"
fi

# The tilde is deliberately unexpanded here: the remote shell expands it
# shellcheck disable=SC2088
remote="~/docker/deploy.sh ${service}"
if [[ $dry_run -eq 1 ]]; then
    echo "dry-run: would run: ${ssh_cmd[*]} ${target} ${remote}"
else
    "${ssh_cmd[@]}" "$target" "$remote"
fi
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `scripts/hooks/uv-public.sh run pytest tests/unit/test_deploy_services.py -v`
Expected: PASS (all tests).

- [ ] **Step 5: Add the directory README**

Create `/Users/connormason/dotfiles-personal/.claude/worktrees/nas-laptop-deploy/scripts/nas/README.md`:

```markdown
[Project Root](../../README.md) > [Scripts](../README.md) > **NAS**

# NAS scripts

Scripts that act on the home NAS from a controlling machine.

| File                                       | Purpose                                                                              |
| ------------------------------------------ | ------------------------------------------------------------------------------------ |
| [`deploy-services.sh`](deploy-services.sh) | rsync `services/` to the NAS and run `~/docker/deploy.sh` (used by CI and `run.py`) |

## `deploy-services.sh`

```bash
NAS_HOST=<host> NAS_USER=<user> [NAS_SSH_KEY=<path>] scripts/nas/deploy-services.sh [--dry-run] <service|all>
```

- `NAS_HOST` / `NAS_USER` are required. `NAS_SSH_KEY` selects a private key and auto-accepts the host key (CI); without it
  the caller's SSH configuration applies.
- Files named `*.j2` and `.env` are never copied, and nothing is deleted on the NAS.
- `--dry-run` runs `rsync -n` and prints the `ssh` command instead of running it.
- Exits 2 on a bad argument or missing variable; otherwise with the status of the failing `rsync` or `ssh`.

From a laptop, prefer `python3 run.py nas-deploy <service>`, which resolves the host and user from the inventory.
```

Check `ls scripts/README.md` first: if it does not exist, drop the middle breadcrumb link so the breadcrumb reads
`[Project Root](../../README.md) > **NAS scripts**` (the README guidelines require breadcrumbs to point at real files).

- [ ] **Step 6: Lint and commit**

Run: `prek run --files scripts/nas/deploy-services.sh scripts/nas/README.md tests/unit/test_deploy_services.py`
Expected: all hooks pass (shellcheck, shfmt, ruff, mypy, leak guard). Fix anything they report, then:

```bash
git add scripts/nas tests/unit/test_deploy_services.py
git commit -m "feat(nas): shared service-deploy script"
```

---

### Task 2: CI uses the shared script

**Files:**
- Modify: `.github/workflows/deploy.yml:97-115` (deploy-push steps) and `:137-148` (deploy-manual steps)
- Test: `tests/unit/test_deploy_workflow.py`

**Interfaces:**
- Consumes: `scripts/nas/deploy-services.sh` and its env contract (Task 1).

- [ ] **Step 1: Write the failing test**

Create `/Users/connormason/dotfiles-personal/.claude/worktrees/nas-laptop-deploy/tests/unit/test_deploy_workflow.py`:

```python
"""
Guardrail tests that keep the CI deploy workflow on the same code path as `run.py nas-deploy`
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW  = REPO_ROOT / '.github' / 'workflows' / 'deploy.yml'
SCRIPT    = 'scripts/nas/deploy-services.sh'


def _steps(job: str) -> list[dict[str, Any]]:  # Any: heterogeneous, yaml-loaded workflow structure
    """
    Return the steps of a job in the deploy workflow
    """
    data = yaml.safe_load(WORKFLOW.read_text(encoding='utf-8'))
    return data['jobs'][job]['steps']


class TestDeployWorkflow:
    """
    Tests for .github/workflows/deploy.yml
    """
    @pytest.mark.parametrize('job', ['deploy-push', 'deploy-manual'])
    def test_deploys_through_the_shared_script(self, job: str) -> None:
        """
        Test that each deploy job calls the shared script and holds no inline rsync
        """
        runs = [step['run'] for step in _steps(job) if 'run' in step]

        assert any(SCRIPT in run for run in runs)
        assert not any('rsync' in run for run in runs)

    @pytest.mark.parametrize('job', ['deploy-push', 'deploy-manual'])
    def test_inputs_reach_the_script_through_env(self, job: str) -> None:
        """
        Test that host, user, and service pass via env, never interpolated into the shell command
        """
        steps = [step for step in _steps(job) if SCRIPT in step.get('run', '')]

        assert len(steps) == 1
        step = steps[0]
        assert '${{' not in step['run']
        assert set(step['env']) == {'NAS_HOST', 'NAS_USER', 'SERVICE'}
        assert 'NAS_SSH_KEY="$HOME/.ssh/id_nas"' in step['run']
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `scripts/hooks/uv-public.sh run pytest tests/unit/test_deploy_workflow.py -v`
Expected: FAIL — the jobs still contain inline `rsync` and no step calls the script.

- [ ] **Step 3: Replace the deploy steps**

In `.github/workflows/deploy.yml`, replace the three steps `Rsync compose.base.yml`, `Rsync service directory`, and
`Deploy service` (job `deploy-push`, from `- name: Rsync compose.base.yml` through the end of the job) with:

```yaml
      - name: Deploy service
        env:
          NAS_HOST: ${{ secrets.NAS_TAILSCALE_HOST }}
          NAS_USER: ${{ secrets.NAS_USER }}
          SERVICE: ${{ matrix.service }}
        run: NAS_SSH_KEY="$HOME/.ssh/id_nas" scripts/nas/deploy-services.sh "$SERVICE"
```

and replace the two steps `Rsync all services` and `Deploy` (job `deploy-manual`, through the end of the file) with:

```yaml
      - name: Deploy
        env:
          NAS_HOST: ${{ secrets.NAS_TAILSCALE_HOST }}
          NAS_USER: ${{ secrets.NAS_USER }}
          SERVICE: ${{ github.event.inputs.service || 'all' }}
        run: NAS_SSH_KEY="$HOME/.ssh/id_nas" scripts/nas/deploy-services.sh "$SERVICE"
```

Leave `detect-changes`, the `Set up Tailscale` steps, and the `Set up SSH key` steps untouched.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `scripts/hooks/uv-public.sh run pytest tests/unit/test_deploy_workflow.py tests/unit/test_deploy_services.py -v`
Expected: PASS.

- [ ] **Step 5: Lint and commit**

Run: `prek run --files .github/workflows/deploy.yml tests/unit/test_deploy_workflow.py`
Expected: pass (yamllint, ruff, mypy, leak guard).

```bash
git add .github/workflows/deploy.yml tests/unit/test_deploy_workflow.py
git commit -m "ci(nas): deploy through the shared service-deploy script"
```

---

### Task 3: `run.py nas-deploy`

**Files:**
- Modify: `run.py` (imports at lines 56-69; constants after line 109; new section before the "Dotfiles commands"
  section header)
- Test: `tests/unit/test_run_nas.py`

**Interfaces:**
- Consumes: `scripts/nas/deploy-services.sh` (Task 1); existing `shell_command`, `printf`, `folduser`,
  `require_inventory`, `require_vault_password`, `UV_PUBLIC`, `INVENTORY_FILE`, `VAULT_PASSWORD`, `DOTFILES_DIR`.
- Produces (used by Task 4):
  - `NAS_PLAYBOOK`, `NAS_REQUIREMENTS`, `NAS_DEPLOY_SCRIPT: Path`; `NAS_INVENTORY_HOST: str = 'nas'`
  - `resolve_nas_target(host: str = NAS_INVENTORY_HOST) -> tuple[str, str]` — `(ansible_host, ansible_user)`
  - `require_nas_reachable(host: str, user: str) -> None` — exits 1 with a remedy when SSH fails
  - `resolve_reachable_nas() -> tuple[str, str]` — inventory + vault checks, resolution, reachability probe
  - `warn_on_dirty_services() -> None`

- [ ] **Step 1: Write the failing tests**

Create `/Users/connormason/dotfiles-personal/.claude/worktrees/nas-laptop-deploy/tests/unit/test_run_nas.py`:

```python
"""
Unit tests for the run.py NAS commands (nas-deploy, nas-provision) with shell_command faked out
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import run


def _done(returncode: int = 0, stdout: str = '', stderr: str = '') -> subprocess.CompletedProcess[str]:
    """
    Build a fake CompletedProcess
    """
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


class FakeShell:
    """
    Stand-in for run.shell_command: records every call and answers from canned results keyed by a command element
    """
    def __init__(self) -> None:
        self.results: dict[str, subprocess.CompletedProcess[str]] = {}
        self.calls:   list[tuple[list[str], dict[str, Any]]]      = []  # Any: mirrors shell_command's **kwargs

    def __call__(self, cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:  # Any: see above
        self.calls.append((cmd, kwargs))
        for token, result in self.results.items():
            if token in cmd:
                return result
        return _done()

    def find(self, token: str) -> tuple[list[str], dict[str, Any]]:  # Any: see above
        """
        Return the single recorded call whose command contains token
        """
        matches = [call for call in self.calls if token in call[0]]
        assert len(matches) == 1, f'expected exactly one {token!r} call, got {len(matches)}'
        return matches[0]


@pytest.fixture
def fake_shell(monkeypatch: pytest.MonkeyPatch) -> FakeShell:
    """
    Replace run.shell_command with a recording fake
    """
    fake = FakeShell()
    monkeypatch.setattr(run, 'shell_command', fake)
    return fake


def _output(capsys: pytest.CaptureFixture[str]) -> str:
    """
    Return captured stdout with ANSI styling removed
    """
    return run.unstyle(capsys.readouterr().out)


class TestResolveNasTarget:
    """
    Tests for resolve_nas_target
    """
    def test_reads_host_and_user_from_the_inventory(self, fake_shell: FakeShell) -> None:
        """
        Test that ansible_host and ansible_user come from ansible-inventory --host nas
        """
        fake_shell.results['ansible-inventory'] = _done(
            stdout=json.dumps({'ansible_host': 'nas.example.ts.net', 'ansible_user': 'tester'}),
        )

        assert run.resolve_nas_target() == ('nas.example.ts.net', 'tester')
        cmd, kwargs = fake_shell.find('ansible-inventory')
        assert cmd[cmd.index('--host') + 1] == 'nas'
        assert kwargs['capture_output'] is True
        assert kwargs['cwd'] == run.DOTFILES_DIR

    def test_falls_back_to_the_host_name_and_local_user(
        self, fake_shell: FakeShell, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Test that missing variables fall back to the inventory name and the local login, as ssh would
        """
        fake_shell.results['ansible-inventory'] = _done(stdout='{}')
        monkeypatch.setattr(run.getpass, 'getuser', lambda: 'local')

        assert run.resolve_nas_target() == ('nas', 'local')

    def test_inventory_failure_exits_with_the_error(
        self, fake_shell: FakeShell, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that an ansible-inventory failure exits 1 and shows its stderr
        """
        fake_shell.results['ansible-inventory'] = _done(1, stderr='bad vault password')

        with pytest.raises(SystemExit) as exc_info:
            run.resolve_nas_target()

        assert exc_info.value.code == 1
        assert 'bad vault password' in _output(capsys)

    def test_unparseable_output_exits(self, fake_shell: FakeShell, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that non-JSON ansible-inventory output exits 1
        """
        fake_shell.results['ansible-inventory'] = _done(stdout='not json')

        with pytest.raises(SystemExit) as exc_info:
            run.resolve_nas_target()

        assert exc_info.value.code == 1
        assert 'Unexpected' in _output(capsys)

    def test_templated_values_are_rejected(self, fake_shell: FakeShell, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that a Jinja-templated ansible_host is refused with a hint to use a literal value
        """
        fake_shell.results['ansible-inventory'] = _done(stdout=json.dumps({'ansible_host': '{{ nas_ip }}'}))

        with pytest.raises(SystemExit) as exc_info:
            run.resolve_nas_target()

        assert exc_info.value.code == 1
        assert 'literal' in _output(capsys)


class TestRequireNasReachable:
    """
    Tests for require_nas_reachable
    """
    def test_probes_over_ssh_with_a_short_timeout(self, fake_shell: FakeShell) -> None:
        """
        Test that a successful probe returns quietly after one non-interactive ssh call
        """
        run.require_nas_reachable('nas.example', 'tester')

        cmd, kwargs = fake_shell.find('ssh')
        assert cmd == ['ssh', '-o', 'ConnectTimeout=5', '-o', 'BatchMode=yes', 'tester@nas.example', 'true']
        assert kwargs['capture_output'] is True

    def test_failure_names_the_likely_causes(self, fake_shell: FakeShell, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that an unreachable NAS exits 1 and mentions Tailscale and ssh's own error
        """
        fake_shell.results['ssh'] = _done(255, stderr='Connection timed out')

        with pytest.raises(SystemExit) as exc_info:
            run.require_nas_reachable('nas.example', 'tester')

        out = _output(capsys)
        assert exc_info.value.code == 1
        assert 'Tailscale' in out
        assert 'Connection timed out' in out


class TestResolveReachableNas:
    """
    Tests for resolve_reachable_nas
    """
    def test_checks_files_resolves_then_probes(self, fake_shell: FakeShell, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that the inventory and vault checks run before resolution, and the probe uses the resolved target
        """
        order: list[str] = []
        monkeypatch.setattr(run, 'require_inventory',      lambda: order.append('inventory'))
        monkeypatch.setattr(run, 'require_vault_password', lambda: order.append('vault'))
        monkeypatch.setattr(run, 'resolve_nas_target',     lambda: (order.append('resolve'), ('h', 'u'))[1])

        assert run.resolve_reachable_nas() == ('h', 'u')
        assert order == ['inventory', 'vault', 'resolve']
        assert fake_shell.find('ssh')[0][-2] == 'u@h'


class TestNasDeploy:
    """
    Tests for the nas-deploy command
    """
    @pytest.fixture(autouse=True)
    def _target(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Skip inventory resolution and the SSH probe
        """
        monkeypatch.setattr(run, 'resolve_reachable_nas', lambda: ('h', 'u'))

    def test_registered_as_a_script_only_nas_command(self) -> None:
        """
        Test that nas-deploy is grouped under NAS and kept out of the Makefile (its argument is required)
        """
        info = run.REGISTERED_COMMANDS['nas-deploy']
        assert info.group == 'NAS'
        assert info.script_only is True

    def test_runs_the_shared_script_with_the_resolved_target(self, fake_shell: FakeShell) -> None:
        """
        Test that the script runs with NAS_HOST and NAS_USER from the inventory and its status is the exit code
        """
        fake_shell.results['bash'] = _done(3)

        with pytest.raises(SystemExit) as exc_info:
            run.cmd_nas_deploy(argparse.Namespace(service='glance', dry_run=False))

        cmd, kwargs = fake_shell.find('bash')
        assert exc_info.value.code == 3
        assert cmd == ['bash', str(run.NAS_DEPLOY_SCRIPT), 'glance']
        assert kwargs['env'] == {'NAS_HOST': 'h', 'NAS_USER': 'u'}
        assert kwargs['check'] is False

    def test_dry_run_flag_precedes_the_service(self, fake_shell: FakeShell) -> None:
        """
        Test that --dry-run is forwarded ahead of the service name
        """
        with pytest.raises(SystemExit):
            run.cmd_nas_deploy(argparse.Namespace(service='all', dry_run=True))

        assert fake_shell.find('bash')[0] == ['bash', str(run.NAS_DEPLOY_SCRIPT), '--dry-run', 'all']

    def test_warns_about_a_dirty_services_tree_and_still_deploys(
        self, fake_shell: FakeShell, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that uncommitted changes under services/ warn but do not block the deploy
        """
        fake_shell.results['git'] = _done(stdout=' M services/glance/compose.yml\n')

        with pytest.raises(SystemExit) as exc_info:
            run.cmd_nas_deploy(argparse.Namespace(service='glance', dry_run=False))

        assert exc_info.value.code == 0
        assert 'uncommitted' in _output(capsys)
        fake_shell.find('bash')

    def test_clean_tree_prints_no_warning(self, fake_shell: FakeShell, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that a clean services/ tree produces no warning
        """
        with pytest.raises(SystemExit):
            run.cmd_nas_deploy(argparse.Namespace(service='glance', dry_run=False))

        assert 'uncommitted' not in _output(capsys)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `scripts/hooks/uv-public.sh run pytest tests/unit/test_run_nas.py -v`
Expected: FAIL — `AttributeError: module 'run' has no attribute 'resolve_nas_target'` (and the other new names).

- [ ] **Step 3: Add imports and constants to `run.py`**

In the import block (`run.py:56-69`) add `import getpass` between `import errno` and `import inspect`, and `import json`
between `import inspect` and `import os`.

After the `UV_PUBLIC` constant (`run.py:109`) add:

```python

# NAS provisioning (Ansible playbook, collections) and service deploys (script shared with CI)
NAS_PLAYBOOK:       Path = PLAYBOOKS_DIR / 'nas_bootstrap.yml'
NAS_REQUIREMENTS:   Path = DOTFILES_DIR  / 'roles' / 'requirements.yml'
NAS_DEPLOY_SCRIPT:  Path = DOTFILES_DIR  / 'scripts' / 'nas' / 'deploy-services.sh'
NAS_INVENTORY_HOST: str  = 'nas'
```

- [ ] **Step 4: Add the shared NAS helpers and `nas-deploy`**

Insert this block immediately before the section header comment that starts `# Dotfiles commands` (the
`# ======…` rule line above it belongs to that header, so insert above the rule):

```python
# ====================================================================================================
# NAS commands
#
# Provision the home NAS and deploy its Compose services from this machine, over SSH (tailnet or LAN):
#   - nas-provision: Run the Ansible playbook (playbooks/nas_bootstrap.yml) against the inventory's ``nas`` host
#   - nas-deploy:    Sync services/ to the NAS and run deploy.sh there (scripts/nas/deploy-services.sh, as CI does)
# ====================================================================================================


def resolve_nas_target(host: str = NAS_INVENTORY_HOST) -> tuple[str, str]:
    """
    Resolve the SSH host and user of an inventory host through ``ansible-inventory``

    :param host: inventory host name
    :return: tuple of (``ansible_host``, ``ansible_user``); missing values fall back to the inventory name and the
             local login, as ssh would
    """
    result = shell_command(
        [
            str(UV_PUBLIC), 'run', 'ansible-inventory',
            '-i', str(INVENTORY_FILE),
            '--vault-password-file', str(VAULT_PASSWORD),
            '--host', host,
        ],
        capture_output=True,
        check=False,
        cwd=DOTFILES_DIR,
    )
    if result.returncode != 0:
        printf(f'❌ Could not read host "{host}" from the inventory', fg='red', bold=True)
        printf(result.stderr.strip(), indent=3)
        sys.exit(1)

    try:
        variables = json.loads(result.stdout)
    except json.JSONDecodeError:
        variables = None
    if not isinstance(variables, dict):
        printf(f'❌ Unexpected ansible-inventory output for host "{host}"', fg='red', bold=True)
        sys.exit(1)

    ssh_host = str(variables.get('ansible_host') or host)
    ssh_user = str(variables.get('ansible_user') or getpass.getuser())
    if '{{' in (ssh_host + ssh_user):
        printf(f'❌ ansible_host/ansible_user for "{host}" are templated: {ssh_user}@{ssh_host}', fg='red', bold=True)
        printf('The NAS commands need literal values in the inventory', indent=3)
        sys.exit(1)

    return ssh_host, ssh_user


def require_nas_reachable(host: str, user: str) -> None:
    """
    Exit with a remedy unless the NAS answers a non-interactive SSH probe

    :param host: SSH host
    :param user: SSH user
    :raises SystemExit: if the probe fails
    """
    result = shell_command(
        ['ssh', '-o', 'ConnectTimeout=5', '-o', 'BatchMode=yes', f'{user}@{host}', 'true'],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        printf(f'❌ Cannot reach the NAS at {user}@{host} over SSH', fg='red', bold=True)
        printf('Is Tailscale up? Does the host resolve? Is your SSH key loaded (ssh-add)?', indent=3)
        printf(f'The host comes from ansible_host of "{NAS_INVENTORY_HOST}" in {folduser(INVENTORY_FILE)}', indent=3)
        printf(f'ssh said: {result.stderr.strip()}', indent=3, dim=True)
        sys.exit(1)


def resolve_reachable_nas() -> tuple[str, str]:
    """
    Check the inventory and vault password, resolve the NAS target, and probe it over SSH

    :return: tuple of (SSH host, SSH user)
    """
    require_inventory()
    require_vault_password()
    host, user = resolve_nas_target()
    require_nas_reachable(host, user)
    return host, user


def warn_on_dirty_services() -> None:
    """
    Warn when services/ has uncommitted changes, since a deploy ships the working tree
    """
    result = shell_command(
        ['git', 'status', '--porcelain', '--', 'services'],
        capture_output=True,
        check=False,
        cwd=DOTFILES_DIR,
    )
    if result.returncode == 0 and result.stdout.strip():
        printf('🟡 services/ has uncommitted changes; deploying the working tree', fg='bright_yellow')
        printf('CI redeploys main whenever it changes a service, which supersedes a branch deploy', indent=3, dim=True)


def add_nas_deploy_arguments(parser: argparse.ArgumentParser) -> None:
    """
    Register nas-deploy options
    """
    parser.add_argument(
        'service',
        help="Directory under services/ to deploy, or 'all'",
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview the rsync and print the remote command without running it',
    )


@command(group='NAS', add_arguments=add_nas_deploy_arguments, script_only=True)
def cmd_nas_deploy(args: argparse.Namespace) -> None:
    """
    Sync services/ to the NAS and run deploy.sh there (the same script CI uses)
    """
    host, user = resolve_reachable_nas()
    warn_on_dirty_services()

    cmd: list[str] = ['bash', str(NAS_DEPLOY_SCRIPT)]
    if args.dry_run:
        cmd.append('--dry-run')
    cmd.append(args.service)

    sys.exit(
        shell_command(cmd, env={'NAS_HOST': host, 'NAS_USER': user}, check=False).returncode
    )


```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `scripts/hooks/uv-public.sh run pytest tests/unit/test_run_nas.py -v`
Expected: PASS for `TestResolveNasTarget`, `TestRequireNasReachable`, `TestResolveReachableNas`, `TestNasDeploy`.

- [ ] **Step 6: Lint and commit**

Run: `scripts/hooks/uv-public.sh run ruff check run.py tests/unit/test_run_nas.py` and
`scripts/hooks/uv-public.sh run mypy run.py` (or `prek run --files run.py tests/unit/test_run_nas.py`).
Expected: clean.

```bash
git add run.py tests/unit/test_run_nas.py
git commit -m "feat(nas): run.py nas-deploy"
```

---

### Task 4: `run.py nas-provision`

**Files:**
- Modify: `run.py` (extend the NAS commands section from Task 3)
- Test: `tests/unit/test_run_nas.py` (append)

**Interfaces:**
- Consumes: Task 3's `resolve_reachable_nas`, `NAS_PLAYBOOK`, `NAS_REQUIREMENTS`; existing `parse_extra_vars`, `UV_PUBLIC`,
  `INVENTORY_FILE`, `VAULT_PASSWORD`, `DOTFILES_DIR`.
- Produces: `build_nas_provision_command(args: argparse.Namespace) -> list[str]`; command `nas-provision` with
  Namespace fields `tags: str | None`, `limit: str | None`, `check: bool`, `diff: bool`,
  `extra_vars: list[str] | None`, `verbose: int`.

- [ ] **Step 1: Append the failing tests**

Append to `tests/unit/test_run_nas.py`:

```python
def _provision_args(**overrides: Any) -> argparse.Namespace:  # Any: free-form Namespace field overrides
    """
    Build the Namespace nas-provision receives, with every option at its default unless overridden
    """
    fields: dict[str, Any] = {  # Any: heterogeneous Namespace fields
        'tags': None, 'limit': None, 'check': False, 'diff': False, 'extra_vars': None, 'verbose': 0,
    }
    fields.update(overrides)
    return argparse.Namespace(**fields)


class TestBuildNasProvisionCommand:
    """
    Tests for build_nas_provision_command
    """
    BASE = [
        str(run.UV_PUBLIC), 'run', 'ansible-playbook', str(run.NAS_PLAYBOOK),
        '-i', str(run.INVENTORY_FILE),
        '--vault-password-file', str(run.VAULT_PASSWORD_PATH),
    ]

    def test_defaults_run_the_whole_playbook(self) -> None:
        """
        Test that no options yield only the playbook, inventory, and vault password file
        """
        assert run.build_nas_provision_command(_provision_args()) == self.BASE

    def test_every_option_is_forwarded(self) -> None:
        """
        Test that tags, limit, check, diff, extra vars, and verbosity map to ansible-playbook flags
        """
        args = _provision_args(
            tags='dotfiles,haos', limit='nas', check=True, diff=True, extra_vars=['a=1', 'b=two'], verbose=2,
        )

        assert run.build_nas_provision_command(args) == [
            *self.BASE,
            '--tags', 'dotfiles,haos',
            '--limit', 'nas',
            '--check',
            '--diff',
            '-e', 'a=1',
            '-e', 'b=two',
            '-vv',
        ]

    def test_malformed_extra_var_exits(self) -> None:
        """
        Test that an extra var without '=' is rejected before anything runs
        """
        with pytest.raises(SystemExit):
            run.build_nas_provision_command(_provision_args(extra_vars=['oops']))


class TestNasProvision:
    """
    Tests for the nas-provision command
    """

    @pytest.fixture(autouse=True)
    def _target(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Skip inventory resolution and the SSH probe
        """
        monkeypatch.setattr(run, 'resolve_reachable_nas', lambda: ('h', 'u'))

    def test_registered_in_the_nas_group_and_makefile(self) -> None:
        """
        Test that nas-provision is a NAS command that also gets a Makefile target
        """
        info = run.REGISTERED_COMMANDS['nas-provision']
        assert info.group == 'NAS'
        assert info.script_only is False

    def test_installs_collections_then_runs_the_playbook_from_the_repo_root(self, fake_shell: FakeShell) -> None:
        """
        Test that galaxy runs before the playbook, both from the repo root, and the playbook status is the exit code
        """
        fake_shell.results['ansible-playbook'] = _done(4)

        with pytest.raises(SystemExit) as exc_info:
            run.cmd_nas_provision(_provision_args(tags='services'))

        assert exc_info.value.code == 4
        assert [call[0][2] for call in fake_shell.calls] == ['ansible-galaxy', 'ansible-playbook']
        galaxy, galaxy_kwargs = fake_shell.find('ansible-galaxy')
        assert galaxy[-2:] == ['-r', str(run.NAS_REQUIREMENTS)]
        _playbook, playbook_kwargs = fake_shell.find('ansible-playbook')
        assert galaxy_kwargs['cwd'] == playbook_kwargs['cwd'] == run.DOTFILES_DIR

    def test_collection_install_failure_warns_and_continues(
            self, fake_shell: FakeShell, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that an offline collection install does not block a run with collections already installed
        """
        fake_shell.results['ansible-galaxy'] = _done(1)

        with pytest.raises(SystemExit) as exc_info:
            run.cmd_nas_provision(_provision_args())

        assert exc_info.value.code == 0
        assert 'Collection install failed' in _output(capsys)
        fake_shell.find('ansible-playbook')

    def test_unreachable_nas_stops_before_ansible(self, fake_shell: FakeShell, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that a failed preflight exits without installing collections or running the playbook
        """

        def unreachable() -> tuple[str, str]:
            raise SystemExit(1)

        monkeypatch.setattr(run, 'resolve_reachable_nas', unreachable)

        with pytest.raises(SystemExit) as exc_info:
            run.cmd_nas_provision(_provision_args())

        assert exc_info.value.code == 1
        assert fake_shell.calls == []

    def test_bad_extra_var_exits_before_the_preflight(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that command construction (and its validation) happens before any network probe
        """
        probed: list[bool] = []
        monkeypatch.setattr(run, 'resolve_reachable_nas', lambda: (probed.append(True), ('h', 'u'))[1])

        with pytest.raises(SystemExit):
            run.cmd_nas_provision(_provision_args(extra_vars=['oops']))

        assert probed == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `scripts/hooks/uv-public.sh run pytest tests/unit/test_run_nas.py -v -k "Provision"`
Expected: FAIL — `AttributeError: module 'run' has no attribute 'build_nas_provision_command'`.

- [ ] **Step 3: Implement `nas-provision`**

Append to the NAS commands section in `run.py`, directly after `cmd_nas_deploy` (before the Dotfiles section header):

```python
def add_nas_provision_arguments(parser: argparse.ArgumentParser) -> None:
    """
    Register nas-provision options
    """
    parser.add_argument(
        '--tags',
        metavar='TAGS',
        help='Only run tasks with these comma-separated tags (e.g. debian,dotfiles,haos,services,secrets)',
    )
    parser.add_argument(
        '--limit',
        metavar='HOSTS',
        help='Limit the run to these inventory hosts',
    )
    parser.add_argument(
        '--check',
        action='store_true',
        help='Predict changes without making them',
    )
    parser.add_argument(
        '--diff',
        action='store_true',
        help='Show file and template differences',
    )
    parser.add_argument(
        '-e',
        '--extra-vars',
        action='append',
        metavar='KEY=VALUE',
        help='Extra playbook variable (repeatable), e.g. -e dotfiles_repo_version=my-branch',
    )
    parser.add_argument(
        '-v',
        '--verbose',
        action='count',
        default=0,
        help='Increase Ansible verbosity (-v, -vv, ...)',
    )


def build_nas_provision_command(args: argparse.Namespace) -> list[str]:
    """
    Build the ``ansible-playbook`` command line for nas-provision

    :param args: parsed nas-provision arguments
    :return: command and arguments
    """
    cmd: list[str] = [
        str(UV_PUBLIC), 'run', 'ansible-playbook', str(NAS_PLAYBOOK),
        '-i', str(INVENTORY_FILE),
        '--vault-password-file', str(VAULT_PASSWORD),
    ]
    if args.tags:
        cmd.extend(['--tags', args.tags])
    if args.limit:
        cmd.extend(['--limit', args.limit])
    if args.check:
        cmd.append('--check')
    if args.diff:
        cmd.append('--diff')
    for key, value in parse_extra_vars(args.extra_vars).items():
        cmd.extend(['-e', f'{key}={value}'])
    if args.verbose:
        cmd.append('-' + 'v' * args.verbose)
    return cmd


@command(group='NAS', add_arguments=add_nas_provision_arguments)
def cmd_nas_provision(args: argparse.Namespace) -> None:
    """
    Provision the NAS with the Ansible playbook: system config, the stow engine, then services
    """
    playbook_cmd = build_nas_provision_command(args)
    resolve_reachable_nas()

    printf('📦 Installing Ansible collections', fg='bright_cyan')
    galaxy = shell_command(
        [str(UV_PUBLIC), 'run', 'ansible-galaxy', 'collection', 'install', '-r', str(NAS_REQUIREMENTS)],
        check=False,
        cwd=DOTFILES_DIR,
    )
    if galaxy.returncode != 0:
        printf('🟡 Collection install failed; continuing with the collections already installed', fg='bright_yellow')

    sys.exit(
        shell_command(playbook_cmd, check=False, cwd=DOTFILES_DIR).returncode
    )


```

- [ ] **Step 4: Run all NAS tests**

Run: `scripts/hooks/uv-public.sh run pytest tests/unit/test_run_nas.py -v`
Expected: PASS (every test in the file).

- [ ] **Step 5: Smoke-check the CLI wiring (no network)**

Run: `scripts/hooks/uv-public.sh run python run.py nas-provision --help` and
`scripts/hooks/uv-public.sh run python run.py nas-deploy --help`
Expected: both print usage with the options above; `run.py --help` lists a `NAS:` group with both commands.

- [ ] **Step 6: Lint and commit**

Run: `prek run --files run.py tests/unit/test_run_nas.py`
Expected: pass.

```bash
git add run.py tests/unit/test_run_nas.py
git commit -m "feat(nas): run.py nas-provision"
```

---

### Task 5: `nas_bootstrap.sh` wrapper and retired scripts

**Files:**
- Modify: `nas_bootstrap.sh` (replace entire contents)
- Delete: `scripts/deploy_configs.sh`
- Modify: `tests/unit/test_nas_bootstrap.py`

**Interfaces:**
- Consumes: `run.py nas-provision` (Task 4).

- [ ] **Step 1: Rewrite the tests (they fail against the old script)**

In `tests/unit/test_nas_bootstrap.py`:

1. Update the module docstring first line to: `Static guardrail tests for the NAS bootstrap entry point and its Ansible collection requirements` (unchanged) — keep it.
2. Run `grep -rn "NAS_PIN\|NAS_URL\|BREW_PIN\|BREW_URL\|COMMIT_PINNED_URL" tests/` to see what else uses the pin regexes.
3. Delete the regex constants `NAS_PIN` and `NAS_URL` (and their comments). Keep `BREW_URL` and `COMMIT_PINNED_URL`; delete
   `BREW_PIN` only if the grep shows nothing else uses it.
4. Replace the whole `class TestNasBootstrapScript` with:

```python
class TestNasBootstrapScript:
    """
    Tests for nas_bootstrap.sh
    """
    SCRIPT = REPO_ROOT / 'nas_bootstrap.sh'

    def test_delegates_to_nas_provision_through_uv(self) -> None:
        """
        Test that the script hands every argument to run.py nas-provision through the public-index uv wrapper
        """
        text = self.SCRIPT.read_text(encoding='utf-8')
        assert re.search(
            r'^exec "\$\{SCRIPT_DIR\}/scripts/hooks/uv-public\.sh" run python "\$\{SCRIPT_DIR\}/run\.py" '
            r'nas-provision "\$@"$',
            text,
            re.MULTILINE,
        )

    def test_installs_nothing_on_the_controller(self) -> None:
        """
        Test that the Homebrew and Ansible installs, and their platform-specific paths, are gone
        """
        text = self.SCRIPT.read_text(encoding='utf-8').lower()
        for needle in ('brew', '/opt/', 'shasum', 'curl', 'ansible-playbook'):
            assert needle not in text, needle

    def test_still_validates_the_repository_layout(self) -> None:
        """
        Test that the script refuses to run outside the dotfiles directory
        """
        text = self.SCRIPT.read_text(encoding='utf-8')
        assert '"${SCRIPT_DIR}/run.py"' in text
        assert '"${SCRIPT_DIR}/playbooks"' in text


class TestBrewInstallerPin:
    """
    Tests for the Homebrew installer URL pinned in bootstrap/50-brew.sh
    """
    def test_installer_url_is_commit_pinned(self) -> None:
        """
        Test that the macOS brew stage downloads the installer from a 40-hex commit, never a moving ref
        """
        brew = BREW_URL.search((REPO_ROOT / 'bootstrap' / '50-brew.sh').read_text(encoding='utf-8'))

        assert brew, 'BREW_INSTALLER_URL not found in bootstrap/50-brew.sh'
        assert COMMIT_PINNED_URL.match(brew.group(1)), brew.group(1)
        assert '/HEAD/' not in brew.group(1)
```

   Leave `class TestRolesRequirements` untouched.

- [ ] **Step 2: Run the tests to verify the new ones fail**

Run: `scripts/hooks/uv-public.sh run pytest tests/unit/test_nas_bootstrap.py -v`
Expected: `test_delegates_to_nas_provision_through_uv` and `test_installs_nothing_on_the_controller` FAIL against the old
script; the rest pass.

- [ ] **Step 3: Replace the script**

Overwrite `/Users/connormason/dotfiles-personal/.claude/worktrees/nas-laptop-deploy/nas_bootstrap.sh` (keep it
executable):

```bash
#!/usr/bin/env bash
# Provision the home NAS from this machine: a thin wrapper over `run.py nas-provision`, which holds the preflight
# checks and the playbook run. Options pass straight through (see `run.py nas-provision --help`).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Validate we're in the right place by checking for required files/directories
if [[ ! -f "${SCRIPT_DIR}/run.py" ]] ||
    [[ ! -f "${SCRIPT_DIR}/nas_bootstrap.sh" ]] ||
    [[ ! -d "${SCRIPT_DIR}/playbooks" ]]; then
    echo "ERROR: This doesn't appear to be the dotfiles directory!" >&2
    echo "Expected to find run.py, nas_bootstrap.sh, and playbooks/ in ${SCRIPT_DIR}" >&2
    exit 1
fi

exec "${SCRIPT_DIR}/scripts/hooks/uv-public.sh" run python "${SCRIPT_DIR}/run.py" nas-provision "$@"
```

- [ ] **Step 4: Delete the unreferenced script**

Run: `grep -rn "deploy_configs" . --include='*.md' --include='*.yml' --include='*.sh' --include='*.py' --include='*.toml'`
Expected: hits only under `docs/plans/` and `archive/` (history; leave them). Then:

```bash
git rm scripts/deploy_configs.sh
```

- [ ] **Step 5: Run the tests**

Run: `scripts/hooks/uv-public.sh run pytest tests/unit/test_nas_bootstrap.py tests/unit/test_brew_stage.py -v`
Expected: PASS.

- [ ] **Step 6: Lint and commit**

Run: `prek run --files nas_bootstrap.sh tests/unit/test_nas_bootstrap.py`
Expected: pass.

```bash
git add nas_bootstrap.sh tests/unit/test_nas_bootstrap.py
git commit -m "refactor(nas): nas_bootstrap.sh delegates to run.py nas-provision"
```

---

### Task 6: The `services` role and playbook wiring

**Files:**
- Create: `roles/services/defaults/main.yml`, `roles/services/tasks/main.yml`, `roles/services/README.md`
- Modify: `roles/requirements.yml`, `playbooks/nas_bootstrap.yml`
- Test: `tests/unit/test_services_role.py`

**Interfaces:**
- Consumes: `~/docker/deploy.sh` and `~/docker/` created by the `docker` role; `services/` in the controller checkout.
- Produces: role `roles/services` with variables `services_target_dir`, `services_source_dir`; task names
  `Sync compose files to the NAS`, `Create per-service secret directories`, `Render per-service secret files`,
  `Deploy all services`. Task 7 and Task 8 tests rely on these names.

- [ ] **Step 1: Write the failing tests**

Create `/Users/connormason/dotfiles-personal/.claude/worktrees/nas-laptop-deploy/tests/unit/test_services_role.py`:

```python
"""
Structural tests for the services role and its place in the NAS playbook (no NAS needed)
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PLAYBOOK  = REPO_ROOT / 'playbooks' / 'nas_bootstrap.yml'
ROLES     = REPO_ROOT / 'roles'

TaskDict = dict[str, Any]  # Any: heterogeneous, yaml-loaded task structure


def _flatten(tasks: list[TaskDict]) -> list[TaskDict]:
    """
    Flatten block/rescue nesting into one task list (blocks included)
    """
    flat: list[TaskDict] = []
    for task in tasks:
        flat.append(task)
        for key in ('block', 'rescue', 'always'):
            flat.extend(_flatten(task.get(key, [])))
    return flat


def _tasks(role: str) -> list[TaskDict]:
    """
    Load every task in a role's tasks/main.yml
    """
    return _flatten(yaml.safe_load((ROLES / role / 'tasks' / 'main.yml').read_text(encoding='utf-8')))


def _task(role: str, name: str) -> TaskDict:
    """
    Load the task with the given name from a role
    """
    matches = [task for task in _tasks(role) if task.get('name') == name]
    assert len(matches) == 1, f'expected exactly one task named {name!r} in role {role}'
    return matches[0]


def _defaults(role: str) -> dict[str, Any]:  # Any: heterogeneous, yaml-loaded variables
    """
    Load a role's defaults/main.yml
    """
    data = yaml.safe_load((ROLES / role / 'defaults' / 'main.yml').read_text(encoding='utf-8'))
    assert isinstance(data, dict)
    return data


class TestPlaybookWiring:
    """
    Tests for how the playbook includes the services role
    """
    @pytest.fixture
    def include(self) -> TaskDict:
        """
        The last task of the NAS play
        """
        return yaml.safe_load(PLAYBOOK.read_text(encoding='utf-8'))[0]['tasks'][-1]

    def test_services_role_runs_last(self, include: TaskDict) -> None:
        """
        Test that the services role is the final include, after haos
        """
        assert include['ansible.builtin.include_role']['name'] == 'roles/services'

    def test_include_is_reachable_by_services_secrets_and_configfile_tags(self, include: TaskDict) -> None:
        """
        Test that the include carries the services, secrets, and configfile tags
        """
        assert include['tags'] == ['services', 'secrets', 'configfile']

    def test_only_the_services_tag_is_applied_inside_the_role(self, include: TaskDict) -> None:
        """
        Test that apply tags the role's tasks 'services' only, so '--tags secrets' selects just the secret tasks
        """
        assert include['ansible.builtin.include_role']['apply']['tags'] == 'services'


class TestServicesRole:
    """
    Tests for roles/services
    """
    def test_sync_pushes_the_tree_without_templates_env_files_or_deletes(self) -> None:
        """
        Test that the sync uses ansible.posix.synchronize with the same exclusions as deploy-services.sh
        """
        args = _task('services', 'Sync compose files to the NAS')['ansible.posix.synchronize']

        assert '--exclude=*.j2' in args['rsync_opts']
        assert '--exclude=.env'  in args['rsync_opts']
        assert not args.get('delete')
        assert args['dest'].startswith('{{ services_target_dir }}')

    def test_only_the_secret_tasks_carry_the_secrets_tag(self) -> None:
        """
        Test that the secrets tag reaches exactly the directory and render tasks
        """
        tagged = {task['name'] for task in _tasks('services') if 'secrets' in task.get('tags', [])}

        assert tagged == {'Create per-service secret directories', 'Render per-service secret files'}

    def test_secrets_render_to_private_env_files_from_the_controller_checkout(self) -> None:
        """
        Test that each services/*/env.j2 renders to a 0600 file, without echoing a diff
        """
        task = _task('services', 'Render per-service secret files')

        assert task['ansible.builtin.template']['mode'] == '0600'
        assert task['ansible.builtin.template']['dest'].endswith('/.env')
        assert task['diff'] is False
        assert '/*/env.j2' in task['loop']

    def test_deploy_reports_changes_only_when_containers_change(self) -> None:
        """
        Test that deploy.sh all is skipped in check mode and counts compose changes, not 'Running'
        """
        task = _task('services', 'Deploy all services')

        assert task['when'] == 'not ansible_check_mode'
        for verb in ('Started', 'Recreated', 'Created', 'Pulled'):
            assert verb in task['changed_when']
        assert 'Running' not in task['changed_when']

    def test_deploy_runs_with_a_fresh_group_list(self) -> None:
        """
        Test that deploy.sh runs through become as the same user, so a docker group added this run applies
        """
        task = _task('services', 'Deploy all services')

        assert task['become'] is True
        assert task['become_user'] == "{{ ansible_facts['user_id'] }}"

    def test_target_dir_matches_the_docker_role(self) -> None:
        """
        Test that both roles agree where ~/docker lives
        """
        assert _defaults('services')['services_target_dir'] == _defaults('docker')['docker_dir']
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `scripts/hooks/uv-public.sh run pytest tests/unit/test_services_role.py -v`
Expected: FAIL — `FileNotFoundError` for `roles/services/...` and the playbook assertions.

- [ ] **Step 3: Create the role**

`roles/services/defaults/main.yml`:

```yaml
---
# Where the compose files land on the NAS; must match docker_dir in the docker role (a test pins the two together)
services_target_dir: "{{ ansible_facts['user_dir'] }}/docker"

# The repository's services/ directory on the machine running Ansible
services_source_dir: "{{ playbook_dir }}/../services"
```

`roles/services/tasks/main.yml`:

```yaml
---
# Pushes the controller's services/ tree, so a run from a branch deploys that branch (same as `run.py nas-deploy`).
# *.j2 templates and .env files never travel: secrets are rendered below, on the NAS side of the connection.
- name: Sync compose files to the NAS
  ansible.posix.synchronize:
    src: "{{ services_source_dir }}/"
    dest: "{{ services_target_dir }}/"
    rsync_opts:
      - "--exclude=*.j2"
      - "--exclude=.env"

# A service opts in with services/<svc>/env.j2 and `env_file: <svc>/.env` in its compose.yml (deploy.sh passes
# --project-directory ~/docker, so the path is relative to that directory)
- name: Create per-service secret directories
  ansible.builtin.file:
    path: "{{ services_target_dir }}/{{ services_secret_template | dirname | basename }}"
    state: directory
    mode: "0755"
  loop: "{{ lookup('ansible.builtin.fileglob', services_source_dir ~ '/*/env.j2', wantlist=True) | sort }}"
  loop_control:
    loop_var: services_secret_template
    label: "{{ services_secret_template | dirname | basename }}"
  tags:
    - secrets

# diff is off so rendered values never reach the console or a saved log
- name: Render per-service secret files
  ansible.builtin.template:
    src: "{{ services_secret_template }}"
    dest: "{{ services_target_dir }}/{{ services_secret_template | dirname | basename }}/.env"
    mode: "0600"
  diff: false
  loop: "{{ lookup('ansible.builtin.fileglob', services_source_dir ~ '/*/env.j2', wantlist=True) | sort }}"
  loop_control:
    loop_var: services_secret_template
    label: "{{ services_secret_template | dirname | basename }}"
  tags:
    - secrets

# compose prints its progress on stderr, and reports "Running" for containers it leaves alone. become as the same user
# starts a fresh login, so the docker group added by the docker role applies on the very first run. A fresh host pulls
# images, so this runs async: a dropped SSH session would otherwise kill the deploy mid-pull.
- name: Deploy all services
  become: true
  become_user: "{{ ansible_facts['user_id'] }}"
  ansible.builtin.command:
    cmd: "{{ services_target_dir }}/deploy.sh all"
  environment:
    HOME: "{{ ansible_facts['user_dir'] }}"
  async: 3600
  poll: 15
  register: services_deploy
  changed_when: (services_deploy.stdout ~ services_deploy.stderr) is search('(Started|Recreated|Created|Pulled)')
  when: not ansible_check_mode
```

Keep exactly those four verbs in `changed_when`: `Running` (an untouched container) must not match.

- [ ] **Step 4: Wire the role into the playbook and requirements**

Append to the `tasks:` list in `playbooks/nas_bootstrap.yml` (after the `haos` include; match the file's 4-space task
indent and existing comment style):

```yaml

    # Compose services: sync services/ to ~/docker, render per-service secrets, deploy everything
    - name: Deploy the container services
      ansible.builtin.include_role:
        name: roles/services
        apply:
          tags: services
      tags:
        - services
        - secrets
        - configfile
```

Replace `roles/requirements.yml` with:

```yaml
---
collections:
  - name: ansible.posix
  - name: community.docker
```

- [ ] **Step 5: Run the tests**

Run: `scripts/hooks/uv-public.sh run pytest tests/unit/test_services_role.py tests/unit/test_nas_playbook.py tests/unit/test_nas_bootstrap.py -v`
Expected: PASS, including the existing requirements-vs-usage test (it now sees `ansible.posix.synchronize`) and the
playbook syntax check (skipped if `ansible-playbook` is absent from the environment).

- [ ] **Step 6: Write the role README**

Create `roles/services/README.md` (breadcrumb target `../README.md` is `roles/README.md`):

```markdown
[Project Root](../../README.md) > [Roles](../README.md) > **services**

# services

Puts the Compose services on the NAS and starts them. Runs last in `playbooks/nas_bootstrap.yml`.

| Task                                  | What it does                                                                                    |
| ------------------------------------- | ----------------------------------------------------------------------------------------------- |
| Sync compose files to the NAS         | `ansible.posix.synchronize` of `services/` to `~/docker/`, excluding `*.j2` and `.env`, no delete |
| Create per-service secret directories | Ensures `~/docker/<svc>/` exists for every `services/<svc>/env.j2` (tag `secrets`)              |
| Render per-service secret files       | Renders each `env.j2` to `~/docker/<svc>/.env`, mode `0600`, no diff output (tag `secrets`)      |
| Deploy all services                   | Runs `~/docker/deploy.sh all`; changed only when containers start, recreate, create, or pull     |

## Variables

| Variable              | Default                                         | Purpose                                              |
| --------------------- | ----------------------------------------------- | ---------------------------------------------------- |
| `services_target_dir` | `~/docker` (the SSH user's home)                | Must match `docker_dir` in the `docker` role         |
| `services_source_dir` | `{{ playbook_dir }}/../services`                | The checkout's `services/` on the machine running Ansible |

## Usage

```bash
python3 run.py nas-provision --tags services          # sync, secrets, deploy
python3 run.py nas-provision --tags secrets           # rotate secrets only; then: run.py nas-deploy <svc>
```

A service that needs a secret ships `services/<svc>/env.j2` and sets `env_file: <svc>/.env` in its `compose.yml`
(relative to `~/docker`, because `deploy.sh` passes `--project-directory ~/docker`). Variables come from the vault.

The sync pushes the working tree of the machine running Ansible, as `run.py nas-deploy` does; a later CI deploy of
`main` supersedes a branch deploy for any service it changes.

Depends on the [`docker`](../docker/README.md) role (engine, `~/docker/`, `deploy.sh`).
```

- [ ] **Step 7: Lint and commit**

Run: `prek run --files roles/services/defaults/main.yml roles/services/tasks/main.yml roles/services/README.md roles/requirements.yml playbooks/nas_bootstrap.yml tests/unit/test_services_role.py`
Expected: yamllint, ruff, mypy pass. The `ansible-lint` hook may need network (`uv tool run`, collections via
`roles/requirements.yml`); if the sandbox blocks it, record that in the commit notes and leave it to the owner's terminal
and CI — do not skip fixing findings it does report.

```bash
git add roles/services roles/requirements.yml playbooks/nas_bootstrap.yml tests/unit/test_services_role.py
git commit -m "feat(nas): services role syncs, renders secrets, and deploys"
```

---

### Task 7: PiHole password moves to a per-service secret

**Files:**
- Create: `services/pihole/env.j2`
- Modify: `services/pihole/compose.yml.disabled`, `roles/docker/templates/env.j2`
- Test: `tests/unit/test_service_secrets.py`

**Interfaces:**
- Consumes: the `env_file: <svc>/.env` convention (Task 6).

- [ ] **Step 1: Write the failing tests**

Create `/Users/connormason/dotfiles-personal/.claude/worktrees/nas-laptop-deploy/tests/unit/test_service_secrets.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `scripts/hooks/uv-public.sh run pytest tests/unit/test_service_secrets.py -v`
Expected: FAIL — `FileNotFoundError: services/pihole/env.j2`, and the global-env test fails on `pihole`.

- [ ] **Step 3: Make the changes**

Create `services/pihole/env.j2` (single line plus trailing newline):

```
FTLCONF_webserver_api_password={{ pihole_web_password }}
```

Edit `services/pihole/compose.yml.disabled`: add `env_file: pihole/.env` directly after `restart: unless-stopped` and
delete the line `      - FTLCONF_webserver_api_password` from `environment:`. The service block becomes:

```yaml
---
services:
  pihole:
    container_name: pihole
    image: pihole/pihole:latest
    restart: unless-stopped
    env_file: pihole/.env
    ports:
      - "53:53/tcp"
      - "53:53/udp"
      - "67:67/udp"
      - "8053:80/tcp"
    environment:
      - TZ=America/Los_Angeles
      - FTLCONF_dns_listeningMode=ALL
    volumes:
      - ./pihole-data/etc-pihole:/etc/pihole
    cap_add:
      - NET_ADMIN
      - SYS_NICE
```

Replace `roles/docker/templates/env.j2` with the single line:

```
ADVERTISE_IP=https://{{ tailscale_hostname }}.{{ tailscale_tailnet_name }}:32443
```

- [ ] **Step 4: Run the tests**

Run: `scripts/hooks/uv-public.sh run pytest tests/unit/test_service_secrets.py tests/unit/test_services_role.py -v`
Expected: PASS. `jinja2` ships with `ansible-core`; if the import fails, run
`scripts/hooks/uv-public.sh run python -c "import jinja2"` to confirm and add nothing else.

- [ ] **Step 5: Lint and commit**

Run: `prek run --files services/pihole/env.j2 services/pihole/compose.yml.disabled roles/docker/templates/env.j2 tests/unit/test_service_secrets.py`
Expected: pass (the `secrets` and leak-guard hooks must stay green: the template holds a Jinja variable, no value).

```bash
git add services/pihole roles/docker/templates/env.j2 tests/unit/test_service_secrets.py
git commit -m "feat(nas): PiHole password as a per-service secret"
```

---

### Task 8: `docker` role fresh-install fixes and lint cleanup

**Files:**
- Modify: `roles/docker/tasks/main.yml` (rewrite), `roles/docker/defaults/main.yml`, `.ansible-lint-ignore`
- Test: `tests/unit/test_services_role.py` (append `TestDockerRole`)

**Interfaces:**
- Consumes: nothing from earlier tasks except the `services` role now owning `deploy.sh all` (Task 6).
- Produces: `docker` role without a deploy step; variables `docker_dir`, `docker_autoplex_repo_dest`,
  `docker_autoplex_repo_url`, `docker_autoplex_repo_branch`.

- [ ] **Step 1: Append the failing tests**

Append to `tests/unit/test_services_role.py`:

```python
class TestDockerRole:
    """
    Tests for the docker role after the fresh-install and lint fixes
    """
    def test_does_not_deploy_services(self) -> None:
        """
        Test that deploying services belongs to the services role, so the docker role no longer runs deploy.sh all
        """
        text = (ROLES / 'docker' / 'tasks' / 'main.yml').read_text(encoding='utf-8')

        assert 'deploy.sh all' not in text
        assert any(task.get('name') == 'Copy deploy script' for task in _tasks('docker'))

    def test_gpg_key_is_fetched_as_root_with_an_explicit_mode(self) -> None:
        """
        Test that the Docker apt key download can write /usr/share/keyrings on a fresh host
        """
        task = _task('docker', 'Add Docker GPG signing key')

        assert task['become'] is True
        assert task['ansible.builtin.get_url']['mode'] == '0644'

    def test_architecture_probe_is_read_only(self) -> None:
        """
        Test that the dpkg architecture lookup never reports changed and also runs in check mode
        """
        task = _task('docker', 'Print debian architecture')

        assert 'ansible.builtin.command' in task
        assert task['changed_when'] is False
        assert task['check_mode'] is False

    def test_ssh_user_joins_the_docker_group(self) -> None:
        """
        Test that the SSH user can run docker without sudo after a fresh install
        """
        args = _task('docker', 'Allow the SSH user to run docker without sudo')['ansible.builtin.user']

        assert args['name']   == "{{ ansible_facts['user_id'] }}"
        assert args['groups'] == 'docker'
        assert args['append'] is True

    def test_autoplex_variables_carry_the_role_prefix(self) -> None:
        """
        Test that every default in the docker role starts with docker_
        """
        assert all(name.startswith('docker_') for name in _defaults('docker'))

    def test_no_docker_lint_exceptions_remain(self) -> None:
        """
        Test that .ansible-lint-ignore holds no entry for the docker role
        """
        ignore = (REPO_ROOT / '.ansible-lint-ignore').read_text(encoding='utf-8')

        assert 'roles/docker/' not in ignore
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `scripts/hooks/uv-public.sh run pytest tests/unit/test_services_role.py -v -k Docker`
Expected: FAIL (the role still runs `deploy.sh all`, the key task has no `become`, etc.).

- [ ] **Step 3: Check for other users of the variables being renamed**

Run: `grep -rn "deb_architecture\|autoplex_repo" roles playbooks services`
Expected: only the docker role's own files (the `zfs` role must not read `deb_architecture`; if it does, keep a
`set_fact` for it in the docker role and note why in a comment). `inventory/host_vars` is outside the repo; none of its
visible variable names collide.

- [ ] **Step 4: Rewrite the role**

`roles/docker/defaults/main.yml`:

```yaml
---
docker_dir: "{{ ansible_facts['user_dir'] }}/docker"

docker_autoplex_repo_dest: "{{ docker_dir }}/.build/autoplex"
docker_autoplex_repo_url: https://github.com/danielmmetz/autoplex.git
docker_autoplex_repo_branch: master
```

`roles/docker/tasks/main.yml` (full replacement):

```yaml
---
# ============================================================
# Docker installation
# ============================================================
- name: Install docker
  block:
    - name: Setup Docker repository
      block:
        - name: Install dependencies
          become: true
          ansible.builtin.apt:
            pkg:
              - ca-certificates
              - curl
              - gnupg

        - name: Add Docker GPG signing key
          become: true
          ansible.builtin.get_url:
            url: "https://download.docker.com/linux/{{ ansible_facts['distribution'] | lower }}/gpg"
            dest: /usr/share/keyrings/docker.asc
            mode: "0644"

        - name: Print debian architecture
          ansible.builtin.command: dpkg --print-architecture
          register: docker_dpkg_architecture
          changed_when: false
          check_mode: false

        # apt_repository refreshes the package index itself when it adds the repository
        - name: Add Docker repository
          become: true
          ansible.builtin.apt_repository:
            repo: >-
              deb [arch={{ docker_dpkg_architecture.stdout }} signed-by=/usr/share/keyrings/docker.asc]
              https://download.docker.com/linux/{{ ansible_facts['distribution'] | lower }}
              {{ ansible_facts['distribution_release'] }} stable
            state: present

    - name: Install Docker engine
      become: true
      ansible.builtin.apt:
        pkg:
          - docker-ce
          - docker-ce-cli
          - containerd.io
          - docker-buildx-plugin
          - docker-compose-plugin
          - docker-compose

    - name: Ensure docker daemon is running
      become: true
      ansible.builtin.service:
        name: docker
        state: started

    # deploy.sh runs as this user; the group applies to new sessions, which is why the services role deploys through
    # become as the same user
    - name: Allow the SSH user to run docker without sudo
      become: true
      ansible.builtin.user:
        name: "{{ ansible_facts['user_id'] }}"
        groups: docker
        append: true

# ============================================================
# Directory and environment setup
# ============================================================
- name: Setup docker environment
  block:
    - name: Create docker directory structure
      ansible.builtin.file:
        path: "{{ docker_dir_path }}"
        state: directory
        mode: "0755"
      loop:
        - "{{ docker_dir }}"
        - "{{ docker_dir }}/.build"
        - "{{ docker_dir }}/pihole-data/etc-pihole"
      loop_control:
        loop_var: docker_dir_path

    # Shared, non-secret values only; per-service secrets are rendered by the services role
    - name: Render docker .env file
      ansible.builtin.template:
        src: env.j2
        dest: "{{ docker_dir }}/.env"
        mode: "0600"
      tags:
        - configfile

# ============================================================
# Custom docker image builds
# ============================================================
- name: Setup autoplex
  block:
    - name: Clone autoplex repo
      ansible.builtin.git:
        repo: "{{ docker_autoplex_repo_url }}"
        dest: "{{ docker_autoplex_repo_dest }}"
        version: "{{ docker_autoplex_repo_branch }}"
        clone: true
        update: true
        accept_hostkey: true

    - name: Build autoplex docker image
      community.docker.docker_image:
        build:
          path: "{{ docker_autoplex_repo_dest }}"
        name: danielmmetz/autoplex
        tag: latest
        source: build
      become: true

# ============================================================
# Deploy script (the services role runs it)
# ============================================================
- name: Copy deploy script
  ansible.builtin.copy:
    src: deploy.sh
    dest: "{{ docker_dir }}/deploy.sh"
    mode: "0755"
  tags:
    - configfile
```

The legacy `docker-compose` apt package stays on purpose: removing it is deferred until the owner confirms on the NAS
that nothing calls `docker-compose` (live acceptance, Task 11).

`.ansible-lint-ignore`: delete the seven lines beginning `roles/docker/`, leaving:

```
# ansible-lint findings accepted on purpose: `<path> <rule>`, then the reason.
roles/samba/handlers/main.yml loop-var-prefix[missing]  # samba role: untouched here; fix with a NAS-verified change
roles/samba/tasks/main.yml loop-var-prefix[missing]  # samba role: untouched here; fix with a NAS-verified change
roles/debian/defaults/main.yml var-naming[no-role-prefix]  # systemd_allow_* are set in inventory host_vars
```

- [ ] **Step 5: Run the tests**

Run: `scripts/hooks/uv-public.sh run pytest tests/unit/test_services_role.py tests/unit/test_nas_playbook.py tests/unit/test_nas_bootstrap.py -v`
Expected: PASS.

- [ ] **Step 6: Run ansible-lint**

Run: `scripts/hooks/ansible-lint.sh` (needs the collections: run
`scripts/hooks/uv-public.sh run ansible-galaxy collection install -r roles/requirements.yml` first).
Expected: no findings for `roles/docker` or `roles/services`. If a rule still fires, fix the task (do not re-add an
ignore entry). If the sandbox cannot reach the network for the tool or collections, say so in the commit body and defer
this check to Task 11's owner run.

- [ ] **Step 7: Commit**

```bash
git add roles/docker .ansible-lint-ignore tests/unit/test_services_role.py
git commit -m "fix(nas): docker role fresh-install fixes and lint cleanup"
```

---

### Task 9: `usbutils` and the architecture stage list

**Files:**
- Modify: `vms/haos/setup.sh:54`, `.ctx/ARCHITECTURE.md` (stage list)
- Test: `tests/unit/test_haos_setup.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_haos_setup.py`:

```python
class TestHaosPackages:
    """
    Tests for the package list setup.sh installs
    """
    def test_usbutils_is_installed_for_lsusb(self) -> None:
        """
        Test that PACKAGES includes usbutils, which provides the lsusb the USB passthrough step calls
        """
        text = SETUP.read_text(encoding='utf-8')
        packages = re.search(r'^PACKAGES=\((.*?)\)$', text, re.MULTILINE)

        assert packages, 'PACKAGES array not found in setup.sh'
        assert 'usbutils' in packages.group(1).split()
```

Ensure the file imports `re` (add `import re` in alphabetical position among the stdlib imports if absent).

- [ ] **Step 2: Run the test to verify it fails**

Run: `scripts/hooks/uv-public.sh run pytest tests/unit/test_haos_setup.py -v -k Packages`
Expected: FAIL — `usbutils` not in the list.

- [ ] **Step 3: Add the package**

In `vms/haos/setup.sh` line 54 change

```bash
PACKAGES=(qemu-system-x86 qemu-utils libvirt-daemon-system libvirt-clients virtinst ovmf xz-utils curl)
```

to

```bash
PACKAGES=(qemu-system-x86 qemu-utils libvirt-daemon-system libvirt-clients virtinst ovmf xz-utils curl usbutils)
```

- [ ] **Step 4: Fix the stage list in `.ctx/ARCHITECTURE.md`**

Run `ls bootstrap/[0-9][0-9]-*.sh` to confirm the stage names, then in the "Stages (base)" bullet insert
`58-defaults-backup` (or the exact name listed) between `50-brew` and `60-macos`.

- [ ] **Step 5: Run the haos tests**

Run: `scripts/hooks/uv-public.sh run pytest tests/unit/test_haos_setup.py -v`
Expected: PASS (the converged-host tests are unaffected: the `dpkg-query` stub reports every package installed).

- [ ] **Step 6: Lint and commit**

Run: `prek run --files vms/haos/setup.sh tests/unit/test_haos_setup.py`
Expected: pass.

```bash
git add vms/haos/setup.sh tests/unit/test_haos_setup.py .ctx/ARCHITECTURE.md
git commit -m "fix(haos): install usbutils for USB passthrough"
```

---

### Task 10: Documentation and Makefile

**Files:**
- Modify: `CLAUDE.md`, `.ctx/BUILD.md`, `.ctx/ARCHITECTURE.md`, `docs/RUN_PY_REFERENCE.md`, `services/README.md`,
  `roles/README.md`, `playbooks/README.md`, `roles/docker/README.md`, `docs/README.md` (only if it indexes scripts),
  `Makefile` (regenerated)
- Test: `tests/unit/test_docs_consistency.py` (existing)

Documents made false by this PR are fixed here; the wider truth-up stays in sub-project 4.

- [ ] **Step 1: Regenerate the Makefile**

Run: `scripts/hooks/uv-public.sh run python run.py makefile`
Expected: `✅ Makefile updated`; `git diff Makefile` shows a `NAS:` help group and a `nas-provision` target, and **no**
`nas-deploy` target (it is `script_only`).

- [ ] **Step 2: `CLAUDE.md`**

Replace the Entry Points item

```
2. **`nas_bootstrap.sh`** → `playbooks/nas_bootstrap.yml` — home NAS / server configuration.
```

with

```
2. **`run.py nas-provision`** (wrapped by `nas_bootstrap.sh`) → `playbooks/nas_bootstrap.yml` — home NAS / server
   configuration; **`run.py nas-deploy`** deploys Compose services.
```

and replace the sentence

```
`nas_bootstrap.sh` validates the repo, installs Homebrew (checksum-verified) and Ansible, then runs the NAS playbook.
```

with

```
`nas_bootstrap.sh` validates the repo, then hands off to `run.py nas-provision`, which checks the inventory, vault
password, and SSH reachability before running the NAS playbook in the uv environment.
```

(Re-wrap the paragraph to 120 columns if the replacement leaves a short line.)

- [ ] **Step 3: `.ctx/BUILD.md`**

Replace

```
# Bootstrap NAS server (Ansible; the become password comes from the vault)
chmod u+x nas_bootstrap.sh && ./nas_bootstrap.sh
```

with

```
# Provision the NAS (Ansible; the become password comes from the vault). nas_bootstrap.sh is a thin wrapper.
python3 run.py nas-provision --check --diff
python3 run.py nas-provision

# Deploy Compose services to the NAS (the script CI uses); --dry-run previews
python3 run.py nas-deploy glance --dry-run
python3 run.py nas-deploy glance
```

In the "Running Ansible Playbooks (NAS)" block, replace the first two example commands with

```bash
# Run specific tags only (system: debian,zfs,samba,docker,tailscale; $HOME: dotfiles; VM: haos; stack: services)
python3 run.py nas-provision --tags dotfiles,haos

# Extra variables, e.g. test the dotfiles role against a branch
python3 run.py nas-provision --tags dotfiles -e dotfiles_repo_version=my-branch

# Rotate per-service secrets, then restart the service
python3 run.py nas-provision --tags secrets
python3 run.py nas-deploy pihole
```

keeping the syntax-check example unchanged.

- [ ] **Step 4: `.ctx/ARCHITECTURE.md`**

Make these replacements (the file is hand-maintained):

1. In "Two Provisioning Systems", the NAS bullet becomes
   ``- **NAS** — Ansible plus the stow engine. Entry point: `run.py nas-provision` (wrapped by `nas_bootstrap.sh`) →
   `playbooks/nas_bootstrap.yml`; services deploy with `run.py nas-deploy`.``
2. Replace the `nas_bootstrap.sh`: numbered list with

   ```
   `run.py nas-provision`:

   1. Preflight: inventory present, vault password file present, `nas` reachable over SSH
   2. Installs the Ansible collections from `roles/requirements.yml`
   3. Runs `playbooks/nas_bootstrap.yml` in the uv environment

   `nas_bootstrap.sh` validates the repository layout and delegates to it.
   ```
3. "Python Management Script" categories gain ``- **NAS**: `nas-provision`, `nas-deploy` ``.
4. "Role System (NAS)": add `` - `services`: syncs `services/` to `~/docker`, renders per-service secrets from
   `services/*/env.j2`, runs `deploy.sh all` `` after the `haos` entry.
5. "Docker Stack (NAS)": replace ``in `roles/docker/files/docker-compose.yml`, with per-service definitions under
   `services/`:`` with ``defined by `services/compose.base.yml` plus one `services/<name>/compose.yml` per service. The
   `services` role, CI, and `run.py nas-deploy` sync them to `~/docker/` and run `deploy.sh`:``.
6. "Bootstrap Script Security": change ``(`nas_bootstrap.sh`, `bootstrap/50-brew.sh`; a test keeps the two pins
   identical)`` to ``(`bootstrap/50-brew.sh`)``.

- [ ] **Step 5: `docs/RUN_PY_REFERENCE.md`**

Read lines 191-231 (the `### Dotfiles` section) and add a sibling `### NAS` section directly after it, in the same
format, documenting:

- `nas-provision [--tags TAGS] [--check] [--diff] [--limit HOSTS] [-e KEY=VALUE]… [-v…]` — preflight (inventory, vault
  password file, SSH probe with a 5 s timeout), `ansible-galaxy collection install`, then `ansible-playbook
  playbooks/nas_bootstrap.yml` via `scripts/hooks/uv-public.sh`; exit status is Ansible's; a failed collection install
  warns and continues.
- `nas-deploy <service|all> [--dry-run]` — resolves `ansible_host` / `ansible_user` for `nas` with `ansible-inventory`
  (literal values required; the user falls back to the local login), warns on uncommitted changes under `services/`,
  runs `scripts/nas/deploy-services.sh`; not generated as a Makefile target.

Also add `NAS` to the "Command Categories" overview if that section enumerates groups.

- [ ] **Step 6: Service, role, and playbook docs**

- `services/README.md`: read it, then (a) correct any statement that the `docker` role deploys `services/` — deploys come
  from CI, `run.py nas-deploy`, and the `services` role; (b) add a "Secrets" section: a service ships
  `services/<svc>/env.j2` and sets `env_file: <svc>/.env` (relative to `~/docker`); the `services` role renders it to
  `~/docker/<svc>/.env` (mode 0600) from vault variables; rotate with `run.py nas-provision --tags secrets` then
  `run.py nas-deploy <svc>`; files named `*.j2` and `.env` are never rsynced; remove any remaining Home Assistant
  `secrets.yaml` / Lutron certificate text.
- `roles/README.md`: add a row ``| [`services`](services/README.md) | Syncs `services/` to the NAS, renders per-service
  secrets, deploys the stack |`` in playbook order after `haos`, aligned with the existing table.
- `playbooks/README.md`: add `9. **services** - Compose sync, per-service secrets, deploy. Tags: `services`, `secrets`,
  `configfile`` after the `haos` item, and list `secrets` and `services` in the tags table.
- `roles/docker/README.md`: insert directly under the H1 description a note: `> **Note:** deploying services and
  rendering per-service secrets moved to the [`services`](../services/README.md) role; this document is rewritten in the
  docs truth-up (NAS sub-project 4).`

- [ ] **Step 7: Format and run the doc-consistency tests**

Run: `prek run mdformat --files CLAUDE.md services/README.md roles/README.md playbooks/README.md roles/docker/README.md roles/services/README.md scripts/nas/README.md docs/RUN_PY_REFERENCE.md`
Run: `scripts/hooks/uv-public.sh run pytest tests/unit/test_docs_consistency.py -v`
Expected: both pass. (`.ctx/` and `docs/plans/` are excluded from mdformat; keep their lines ≤ 120 columns by hand.)

- [ ] **Step 8: Commit**

```bash
git add CLAUDE.md .ctx docs/RUN_PY_REFERENCE.md services/README.md roles/README.md playbooks/README.md roles/docker/README.md Makefile
git commit -m "docs(nas): nas-provision, nas-deploy, and the services role"
```

---

### Task 11: Verification and the live-acceptance runbook

**Files:**
- Create: `~/nas-sp3-rollout.md` (outside the repo, like `~/nas-sp2-rollout.md`)
- Modify: `docs/plans/2026-11/2026-11-02-nas-laptop-deploy-design.md` (status line only)

- [ ] **Step 1: Full test suite and lint**

Run: `scripts/hooks/uv-public.sh run pytest tests -q`
Expected: all pass (the macOS-only integration tests run on this Mac).
Run: `prek run --all-files`
Expected: all hooks pass. Note any hook skipped for lack of network (ansible-lint) for the PR description.

- [ ] **Step 2: Syntax check the playbook**

Run: `scripts/hooks/uv-public.sh run ansible-playbook --syntax-check -i localhost, playbooks/nas_bootstrap.yml` with
`ANSIBLE_VAULT_PASSWORD_FILE` pointing at a throwaway file (the structural test already does this; run it by hand only if
that test was skipped).
Expected: `playbook: playbooks/nas_bootstrap.yml`.

- [ ] **Step 3: Offline smoke test of both commands' wiring**

Run: `scripts/hooks/uv-public.sh run python run.py --help | grep -A3 NAS`
Expected: the NAS group with both commands. Run `bash nas_bootstrap.sh --help`.
Expected: `run.py nas-provision --help` output (the wrapper forwards arguments).

- [ ] **Step 4: Write the owner's runbook**

Create `/Users/connormason/nas-sp3-rollout.md`:

````markdown
# NAS sub-project 3: live acceptance

Run every Mac command in **one** terminal on the work Mac. After each stage, save the output under `$TMPDIR` and tell
Claude it landed; wait for the review before the next stage.

## Setup (once)

```bash
cd ~/dotfiles-personal/.claude/worktrees/nas-laptop-deploy
ln -s ~/dotfiles-personal/inventory inventory
ln -s ~/dotfiles-personal/vault_password.txt vault_password.txt
echo inventory >> "$(git rev-parse --git-path info/exclude)"   # keep the symlink out of git status
RUN=(scripts/hooks/uv-public.sh run python run.py)
```

## Stage 0: dry preflight (changes nothing)

```bash
"${RUN[@]}" nas-deploy glance --dry-run 2>&1 | tee "$TMPDIR/nas3-0-dry.txt"
```

Expect: rsync file lists marked as a dry run, then `dry-run: would run: ssh <user>@<host> ~/docker/deploy.sh glance`.
**Send:** `nas3-0-dry.txt`

## Stage 1: check mode for the changed roles

```bash
"${RUN[@]}" nas-provision --tags docker,services --check --diff 2>&1 | tee "$TMPDIR/nas3-1-check.txt"
```

Expect: no failures. **Send:** `nas3-1-check.txt`

## Stage 2: real run, then a converged re-run

```bash
"${RUN[@]}" nas-provision --tags docker,services 2>&1 | tee "$TMPDIR/nas3-2-run.txt"
"${RUN[@]}" nas-provision --tags docker,services 2>&1 | tee "$TMPDIR/nas3-2-rerun.txt"
```

Expect: the first run changes the sync, `pihole/.env`, the global `.env` (password removed), and possibly the docker
group; the second run reports `changed=0`. **Send:** both files.

## Stage 3: verify on the NAS

```bash
ssh <user>@<host> 'stat -c "%a %n" ~/docker/pihole/.env ~/docker/.env; grep -c FTLCONF ~/docker/.env; \
  id -nG | tr " " "\n" | grep -x docker; which docker-compose; grep -rn "docker-compose" ~ 2>/dev/null | head -5'
```

Expect: `600 …/pihole/.env`, `600 …/.env`, `0` matches for FTLCONF in the global file, `docker` in the groups. Report the
`docker-compose` lines so the legacy-package question can be settled.
**Send:** the output (it prints no secret values).

## Stage 4: deploy one service from the laptop

```bash
"${RUN[@]}" nas-deploy glance 2>&1 | tee "$TMPDIR/nas3-4-deploy.txt"
```

Expect: exit 0 and `Done: glance`. **Send:** `nas3-4-deploy.txt`

## After the PR merges

1. Full convergence on `main`: `python3 run.py nas-provision --check --diff`, then `python3 run.py nas-provision` twice;
   the second run reports `changed=0` for the whole play (this includes the `usbutils` change in the `haos` role).
2. CI: push a trivial change under one `services/<svc>/` and confirm the `Deploy NAS Services` run succeeds.
3. Inventory repo (private): set `ansible_host` for `nas` to the MagicDNS name once `ssh <name>` works from this Mac;
   delete the unused Lutron certificate files under `group_vars/all`.
4. Remove the symlinks: `rm inventory vault_password.txt` in the worktree (or delete the worktree).
````

- [ ] **Step 5: Mark the design as implemented-pending-acceptance and commit**

In `docs/plans/2026-11/2026-11-02-nas-laptop-deploy-design.md` change the status line to
`**Status:** Implemented on branch worktree-nas-laptop-deploy; live acceptance pending (owner)`.

```bash
git add docs/plans/2026-11
git commit -m "docs: sub-project 3 status"
```

- [ ] **Step 6: Hand off**

Report to the owner: branch name, test and lint results, any hook that could not run in the sandbox, and the runbook
path. Do not push or open the PR without the owner's go-ahead.

---

## Self-review (spec coverage)

| Spec requirement                                                       | Task        |
| ---------------------------------------------------------------------- | ----------- |
| `scripts/nas/deploy-services.sh`, env contract, `--dry-run`, excludes  | 1           |
| `deploy.yml` calls the shared script; no inline rsync                  | 2           |
| `run.py nas-deploy` (inventory host/user, dirty warning, script-only)  | 3           |
| `run.py nas-provision` (preflight, galaxy, flags, `-e`)                | 3 (helpers), 4 |
| `nas_bootstrap.sh` wrapper; pin tests removed; `deploy_configs.sh` out | 5           |
| `services` role: sync, secrets, deploy; `ansible.posix`; wiring        | 6           |
| Per-service secrets; PiHole migration; global `.env` non-secret only   | 6, 7        |
| `docker` role: key `become`, `changed_when`, FQCN, no deploy, lint      | 8           |
| Fresh install: docker group + fresh-group deploy                       | 6, 8        |
| `usbutils`; `58-defaults-backup` in ARCHITECTURE                       | 9           |
| Docs made false by this PR; Makefile                                   | 10          |
| Live acceptance, MagicDNS and Lutron owner actions                     | 11          |
| Preflight remedies (inventory, vault, unreachable)                     | 3           |

Two deviations from the design are intentional and called out in the tasks: `env_file` is `<svc>/.env` (not `.env`)
because of `--project-directory`, and the `docker` role gains a docker-group task plus a `become`-as-self deploy so the
first run on a fresh NAS can succeed. The legacy `docker-compose` package removal remains an owner-confirmed follow-up.
