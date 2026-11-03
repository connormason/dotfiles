# NAS Sub-project 4 (PR A): Docs Truth-up and Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every NAS-related document true of the code after sub-projects 1-3, close the low-risk code follow-ups
deferred from PR #37, and add tests that catch the same drift next time.

**Architecture:** Code changes land first (tags, secrets discovery, a stat-guarded directory, script and workflow
hardening, stale-entry cleanup, a `uv` guard, one coverage test), each test-first and exercised by a real run where one
is possible. Docs follow, truth sources first (role and stack READMEs, then playbook/roles/`.ctx`, then the root README
and the rest); each doc task that fixes an enumerated inventory ships a drift guard in `test_docs_consistency.py`. A
verification phase ends with fresh read-only audit agents re-checking every changed claim.

**Tech Stack:** Ansible (ansible-core 2.21 in the uv environment), bash 3.2-compatible scripts, pytest, PyYAML, GitHub
Actions YAML, Markdown (mdformat via prek).

**Spec:** [`2026-11-02-nas-docs-truth-up-design.md`](2026-11-02-nas-docs-truth-up-design.md)

## Global Constraints

Every task's requirements include this section.

- **Worktree:** all work happens in `/Users/connormason/dotfiles-personal/.claude/worktrees/nas-docs-truth-up` on branch
  `worktree-nas-docs-truth-up`. Use absolute paths under it. Run git from that directory with no `-C`. Never set `HOME`
  in a Bash command (the worktree guard refuses it); keep Bash commands plain (no nested `bash -c`; put multi-line
  probes in a script file under `$TMPDIR` and run it).
- **No push, no PR, no `--no-verify`.** Local commits only. If a pre-commit hook modifies files, re-stage them and
  commit again.
- **Python and tooling:** run everything through `scripts/hooks/uv-public.sh run ...` (never bare `python`, `python3`,
  `pip`). **Never run `ruff format`** (`ruff check --fix` is fine). Baseline before this plan: `998 passed, 3 skipped`
  (`scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider`, about 65 s).
- **Do not edit `run.py`.** Another change (PR #38, class-based commands) is in flight; tests may `import run`. If PR
  #38
  merges first, rebase before the doc tasks that touch `docs/RUN_PY_REFERENCE.md` or `.ctx/CONVENTIONS.md`.
- **Python style** (`.claude/rules/python-style.md`): `from __future__ import annotations` first; one import per line;
  single-quoted strings; sphinx docstrings; test classes and methods carry multi-line docstrings (opening `"""` on the
  `def`/`class` line, description on the next line, capitalized, no trailing period, closing `"""` on its own line);
  every test method returns `-> None`; no blank line between a class docstring and its first member; no mutable default
  arguments; `# Any:` comment wherever `Any` is used.
- **Shell style:** scripts stay bash 3.2-compatible (`/bin/bash` on macOS), `set -euo pipefail`, 4-space indent, pass
  `shellcheck`/`shfmt` (the hooks run at commit).
- **Ansible style:** FQCN modules; role-prefixed variable names (`docker_`, `services_`); `diff: false` (and `no_log`
  where values print) on any task whose target holds secrets; `changed_when` on `command`/`shell` tasks.
- **Markdown:** relative links only (no `/Users/...`, no `~/...` in link targets); 120-column wrap; code blocks, tables,
  URLs exempt. `.ctx/` and `docs/plans/` are excluded from `mdformat`, so hand-wrap them; every other changed Markdown
  file is formatted by the `mdformat` hook at commit. Files of 100+ lines with 3+ `##` sections carry the
  `<!-- mdformat-toc start --slug=github --maxlevel=3 --minlevel=2 -->` / `<!-- mdformat-toc end -->` pair immediately
  after the H1 description (the hook fills it). Every README starts with an up-breadcrumb, e.g.
  `[Project Root](../../README.md) > [Roles](../README.md) > **docker**`.
- **Docs describe only what the code proves.** Every claim in a doc task's "Facts" list came from an audit and may be
  wrong: re-read the cited source before writing it. Anything the code cannot answer is omitted (the owner is asked
  separately).
- **Run.py form:** docs keep `python3 run.py <cmd>`; one "Running run.py" note (Task 14, mirrored in `.ctx/BUILD.md`)
  explains that bare `python3` suffices for the stdlib-only commands and `list-hosts` (PyYAML) needs
  `scripts/hooks/uv-public.sh run python run.py list-hosts`.
- **Facts about the NAS:** Debian 12 (bookworm), x86_64, user home `~`, stack under `~/docker`. PiHole and Home
  Assistant composes are `compose.yml.disabled`.
- **Commit messages:** `type(scope): subject`, no employer-internal names.

## File Structure

| Path                                                                                   | Change                                                                                      | Task  |
| -------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- | ----- |
| `playbooks/nas_bootstrap.yml`                                                          | Drop inert `configfile` / `homeassistant` tags                                              | 1     |
| `tests/unit/test_services_role.py`                                                     | Derive the harness play from the production include; tag, secrets, and PiHole-dir tests     | 1-3   |
| `tests/unit/test_nas_playbook.py`                                                      | Guard: every include tag reaches a task                                                     | 1     |
| `roles/services/tasks/main.yml`                                                        | Render secrets only for services with a `compose.yml`                                       | 2     |
| `roles/docker/tasks/main.yml`                                                          | Stat-guarded PiHole config directory                                                        | 3     |
| `scripts/nas/deploy-services.sh`, `tests/unit/test_deploy_services.py`                 | `--`, option-like value refusal, quoted key for `rsync -e`                                  | 4     |
| `.github/workflows/deploy.yml`, `tests/unit/test_deploy_workflow.py`                   | Secrets through `env:`                                                                      | 5     |
| `.secrets.baseline`, `pyproject.toml`, `tests/unit/test_repo_hygiene.py` (new)         | Drop stale entries; guard against new ones                                                  | 6     |
| `nas_bootstrap.sh`, `tests/unit/test_nas_bootstrap.py`                                 | `uv` guard                                                                                  | 7     |
| `tests/unit/test_run_nas.py`                                                           | Non-object `ansible-inventory` output test                                                  | 8     |
| `roles/docker/README.md`                                                               | Rewrite (about 120 lines)                                                                   | 9     |
| `services/README.md`, `tests/unit/test_docs_consistency.py`                            | Corrections; data flow, storage, operations; guard 1                                        | 10    |
| `roles/services/README.md`, `roles/tailscale/README.md`, `roles/samba/README.md`       | Gaps, stale steps, stub                                                                     | 11    |
| `playbooks/README.md`, `roles/README.md`, `tests/unit/test_docs_consistency.py`        | Tag truth, variables, add-a-role steps; guard 2                                             | 12    |
| `.ctx/ARCHITECTURE.md`, `.ctx/BUILD.md`, `.ctx/CONVENTIONS.md`, `tests/unit/test_docs_consistency.py` | Targeted fixes; guard 2 extension                                           | 13    |
| `README.md`                                                                            | 21 corrections, prerequisites, "Running run.py" note                                        | 14    |
| `CLAUDE.md`, `.claude/rules/readme-guidelines.md`, `vms/README.md`, `docs/RUN_PY_REFERENCE.md`, `scripts/nas/README.md`, `roles/docker/files/deploy.sh` (comment), `tests/unit/test_docs_consistency.py` | Remaining corrections; guard 3 | 15 |
| `CLAUDE-LESSONS.md`                                                                    | Four lessons                                                                                | 16    |
| `~/nas-sp4-rollout.md` (outside the repo)                                              | Owner-run NAS acceptance runbook                                                            | 17    |

---

## Task 1: Drop inert `configfile` and `homeassistant` tags

A tag on `include_role` selects only the include task itself; tasks inside the role see only the `apply:` tags plus
their own. Only three tasks carry `configfile` (docker `.env` render, docker `deploy.sh` copy, samba `smb.conf`), so six
includes carry a tag that selects nothing, and the docker include carries a `homeassistant` tag nothing uses.

**Files:**
- Modify: `tests/unit/test_services_role.py` (harness, new `TestTagSelection`, retag test)
- Modify: `tests/unit/test_nas_playbook.py` (new `TestPlaybookTags`)
- Modify: `playbooks/nas_bootstrap.yml`

**Interfaces:**
- Produces (in `test_services_role.py`, used by Tasks 2 and 3):
  - `needs_ansible` – `pytest.mark.skipif` marker for classes that run `ansible-playbook`
  - `_include_play(role: str) -> str` – YAML text of a one-task localhost play built from the production include of
    `roles/<role>` (same `tags` and `apply`, role name rewritten to the bare `role`)
  - `_run_play(tmp_path: Path, play: str, *args: str) -> tuple[int, str]` – runs it, returns
    `(returncode, stdout+stderr)`; skips the test when `ansible.posix` is missing
  - `_render_secrets(tmp_path: Path, source: Path, *extra_vars: str) -> tuple[int, str, Path]` – runs the services
    include with `--tags secrets --diff`, returns `(returncode, output, target_dir)`
  - `SERVICES_DIR` – `REPO_ROOT / 'services'`

- [ ] **Step 1: Replace the harness at the bottom of `tests/unit/test_services_role.py`**

Delete everything from the line `ANSIBLE_PLAYBOOK = Path(sys.executable).parent / 'ansible-playbook'` to the end of the
file (the `SECRETS_PLAYBOOK` constant and the `TestSecretsRender` class) and append:

```python
ANSIBLE_PLAYBOOK = Path(sys.executable).parent / 'ansible-playbook'
SERVICES_DIR     = REPO_ROOT / 'services'

needs_ansible = pytest.mark.skipif(not ANSIBLE_PLAYBOOK.exists(), reason='ansible-playbook not in this environment')


def _include_play(role: str) -> str:
    """
    Build a one-task localhost play from the production include of a role

    The include keeps its production tags and apply block; only the role name is made bare so Ansible finds it through
    ansible.cfg's roles_path when run from the repository root. Using the production include (not a copy) means a tag
    change in the playbook is exercised by these tests.

    :param role: role directory name, e.g. ``services``
    :return: playbook YAML text
    """
    key     = 'ansible.builtin.include_role'
    play    = yaml.safe_load(PLAYBOOK.read_text(encoding='utf-8'))[0]
    include = next(task for task in play['tasks'] if task.get(key, {}).get('name') == f'roles/{role}')
    include = {**include, key: {**include[key], 'name': role}}
    return yaml.safe_dump([{'hosts': 'all', 'gather_facts': False, 'connection': 'local', 'tasks': [include]}])


def _run_play(tmp_path: Path, play: str, *args: str) -> tuple[int, str]:
    """
    Run a one-play playbook against localhost with a throwaway vault password file

    Skips the calling test when the ansible.posix collection is not installed.

    :param tmp_path: scratch directory for the playbook and vault file
    :param play: playbook YAML text
    :param args: extra ansible-playbook arguments
    :return: tuple of (return code, combined stdout and stderr)
    """
    playbook = tmp_path / 'play.yml'
    playbook.write_text(play, encoding='utf-8')

    vault = tmp_path / 'vault-pass'
    vault.write_text('unused\n', encoding='utf-8')

    result = subprocess.run(
        [str(ANSIBLE_PLAYBOOK), str(playbook), '-i', 'localhost,', *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
        env={**os.environ, 'ANSIBLE_VAULT_PASSWORD_FILE': str(vault), 'ANSIBLE_NOCOLOR': '1'},
        timeout=300,
    )
    output = result.stdout + result.stderr
    if "couldn't resolve module/action 'ansible.posix" in output:
        pytest.skip('ansible.posix is not installed: ansible-galaxy collection install -r roles/requirements.yml')
    return result.returncode, output


def _render_secrets(tmp_path: Path, source: Path, *extra_vars: str) -> tuple[int, str, Path]:
    """
    Run the production services include with only the secrets tag selected

    :param tmp_path: scratch directory; the rendered tree lands in ``tmp_path / 'docker'``
    :param source: directory standing in for the repository's services/ tree
    :param extra_vars: ``name=value`` extra variables (vault values)
    :return: tuple of (return code, combined output, target directory)
    """
    target = tmp_path / 'docker'
    args   = [
        '--tags', 'secrets', '--diff',
        '-e', f'services_source_dir={source}',
        '-e', f'services_target_dir={target}',
    ]
    for var in extra_vars:
        args += ['-e', var]
    code, output = _run_play(tmp_path, _include_play('services'), *args)
    return code, output, target


@needs_ansible
class TestTagSelection:
    """
    Real-run tests of what '--tags configfile' selects (a tag on include_role selects only the include itself)
    """
    def test_configfile_selects_nothing_in_the_services_play(self, tmp_path: Path) -> None:
        """
        Test that --tags configfile runs no task of the services role and does not even select its include
        """
        target = tmp_path / 'docker'
        code, output = _run_play(
            tmp_path, _include_play('services'), '--tags', 'configfile',
            '-e', f'services_source_dir={SERVICES_DIR}', '-e', f'services_target_dir={target}',
        )

        assert code == 0, output
        for task in ('Install rsync', 'Sync compose files', 'Render per-service secret files', 'Deploy all services'):
            assert task not in output, output
        assert not target.exists()
        assert 'Deploy the container services' not in output, output

    def test_configfile_renders_only_the_env_file_and_deploy_script_in_the_docker_role(self, tmp_path: Path) -> None:
        """
        Test that --tags configfile reaches exactly the two docker tasks that carry the tag
        """
        docker_dir = tmp_path / 'docker'
        docker_dir.mkdir()
        code, output = _run_play(
            tmp_path, _include_play('docker'), '--tags', 'configfile',
            '-e', f'docker_dir={docker_dir}', '-e', 'tailscale_tailnet_name=example.ts.net',
        )

        assert code == 0, output
        assert sorted(path.name for path in docker_dir.iterdir()) == ['.env', 'deploy.sh']
        for task in ('Create docker directory structure', 'Install Docker engine', 'Build autoplex docker image'):
            assert task not in output, output


@needs_ansible
class TestSecretsRender:
    """
    End-to-end test of the secrets tasks: discovery, directory creation, and rendering, against a temp directory
    """
    def test_renders_every_env_template_privately_and_silently(self, tmp_path: Path) -> None:
        """
        Test that --tags secrets renders services/pihole/env.j2 to a 0600 .env without echoing the value

        Guards the first-live-run failure where discovery found no templates and nothing was rendered
        """
        code, output, target = _render_secrets(tmp_path, SERVICES_DIR, 'pihole_web_password=hunter2-test-value')

        assert code == 0, output
        env_file = target / 'pihole' / '.env'
        assert env_file.read_text(encoding='utf-8').strip() == 'FTLCONF_webserver_api_password=hunter2-test-value'
        assert env_file.stat().st_mode & 0o777 == 0o600
        assert 'hunter2-test-value' not in output
        assert 'Sync compose files' not in output
```

- [ ] **Step 2: Run the existing secrets test to confirm the new harness is faithful**

Run: `scripts/hooks/uv-public.sh run pytest tests/unit/test_services_role.py -q -p no:cacheprovider`
Expected: everything passes, including the two new `TestTagSelection` tests **except**
`test_configfile_selects_nothing_in_the_services_play`, which FAILS on its last assertion
(`'Deploy the container services' not in output`). That failure output is the proof of the premise: read it and confirm
it shows `TASK [Deploy the container services]` (the include was selected) and none of the inner task names. If an inner
task name appears, STOP and report: the tag model in this plan is wrong.

- [ ] **Step 3: Add the playbook-wide guard to `tests/unit/test_nas_playbook.py`**

Append after the `TestPlaybookOrder` class:

```python
def _collect_tags(node: object) -> set[str]:
    """
    Collect every value of a ``tags`` key anywhere inside a yaml-loaded task structure

    :param node: yaml-loaded structure (nested dicts and lists)
    :return: all tag names found, whether written as a string or a list
    """
    found: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if key == 'tags':
                found.update([value] if isinstance(value, str) else value)
            else:
                found |= _collect_tags(value)
    elif isinstance(node, list):
        for item in node:
            found |= _collect_tags(item)
    return found


def _role_tags(role: str) -> set[str]:
    """
    Return every tag carried by a task anywhere in a role's tasks/*.yml (block members and included files included)
    """
    tags: set[str] = set()
    for path in sorted((ROLES / role / 'tasks').glob('*.yml')):
        tags |= _collect_tags(yaml.safe_load(path.read_text(encoding='utf-8')))
    return tags


def _includes() -> list[dict[str, Any]]:  # Any: heterogeneous, yaml-loaded task structure
    """
    Return the include_role tasks of the NAS play, in order
    """
    play = yaml.safe_load(PLAYBOOK.read_text(encoding='utf-8'))[0]
    return [task for task in play['tasks'] if 'ansible.builtin.include_role' in task]


class TestPlaybookTags:
    """
    Tests for the tags on the playbook's role includes
    """
    @pytest.mark.parametrize(
        'include',
        _includes(),
        ids=lambda include: include['ansible.builtin.include_role']['name'],
    )
    def test_every_include_tag_reaches_a_task_in_the_role(self, include: dict[str, Any]) -> None:  # Any: yaml task
        """
        Test that each tag on an include is the apply tag or is carried by a task inside the role

        A tag on include_role selects only the include itself, so a tag that no inner task carries selects nothing
        """
        spec       = include['ansible.builtin.include_role']
        name       = spec['name']
        apply_tags = spec['apply']['tags']
        reachable  = {apply_tags} if isinstance(apply_tags, str) else set(apply_tags)
        reachable |= _role_tags(name.removeprefix('roles/'))

        dead = sorted(set(include['tags']) - reachable)
        assert not dead, f'tags {dead} on the {name} include reach no task'
```

- [ ] **Step 4: Update the services include test in `tests/unit/test_services_role.py`**

Replace `test_include_is_reachable_by_services_secrets_and_configfile_tags` with:

```python
    def test_include_is_reachable_by_the_services_and_secrets_tags(self, include: TaskDict) -> None:
        """
        Test that the include carries exactly the services and secrets tags (configfile selected nothing inside it)
        """
        assert include['tags'] == ['services', 'secrets']
```

- [ ] **Step 5: Run to verify the new tests fail for the stated reasons**

Run:
`scripts/hooks/uv-public.sh run pytest tests/unit/test_nas_playbook.py tests/unit/test_services_role.py -q -p no:cacheprovider`
Expected FAIL: `TestPlaybookTags` for `roles/debian`, `roles/zfs`, `roles/docker`, `roles/tailscale`, `roles/dotfiles`,
`roles/haos`, `roles/services` (message `tags [...] on the ... include reach no task`; `roles/samba` passes);
`test_include_is_reachable_by_the_services_and_secrets_tags`; `test_configfile_selects_nothing_in_the_services_play`.

- [ ] **Step 6: Write the new playbook**

Replace `playbooks/nas_bootstrap.yml` with exactly:

```yaml
---
- name: Home NAS bootstrap
  hosts: nas
  vars:
    # The NAS clone of this repository: the dotfiles role clones it, the haos role runs vms/haos/setup.sh from it
    dotfiles_repo_dir: "{{ ansible_facts['user_dir'] }}/dotfiles-personal"
  tasks:

    # Set become password so it can be used in any role
    - name: Set ansible_become_pass
      ansible.builtin.set_fact:
        ansible_become_pass: "{{ admin_password }}"
      no_log: true
      tags:
        - always

    # Update the apt package index (tagged always so tag-scoped runs still refresh a stale cache; the cache window keeps
    # it `ok` on re-runs)
    - name: Update apt package index
      become: true
      ansible.builtin.apt:
        update_cache: true
        cache_valid_time: 86400   # One day
      tags:
        - always

    # A tag on include_role selects only the include itself; the role's tasks see just the apply tag plus their own
    # tags. So every tag below must be the role name (via apply) or be carried by a task inside the role (guarded by
    # tests/unit/test_nas_playbook.py::TestPlaybookTags). configfile appears only where a task carries it.

    # Tasks for Debian Linux
    - name: Configure Debian
      ansible.builtin.include_role:
        name: roles/debian
        apply:
          tags: debian
      tags:
        - debian

    # Tasks for ZFS filesystem
    - name: Install ZFS
      ansible.builtin.include_role:
        name: roles/zfs
        apply:
          tags: zfs
      tags:
        - zfs

    # Tasks for Samba file sharing
    - name: Configure Samba file sharing
      ansible.builtin.include_role:
        name: roles/samba
        apply:
          tags: samba
      tags:
        - samba
        - configfile

    # Tasks for Docker
    - name: Configure Docker and the container stack
      ansible.builtin.include_role:
        name: roles/docker
        apply:
          tags: docker
      tags:
        - docker
        - configfile

    # Tasks for Tailscale configuration
    - name: Configure Tailscale
      ansible.builtin.include_role:
        name: roles/tailscale
        apply:
          tags: tailscale
      tags:
        - tailscale

    # $HOME: clone the repo, register profiles/nas, login shell, run the stow engine as the user
    - name: Hand the home directory to the stow engine
      ansible.builtin.include_role:
        name: roles/dotfiles
        apply:
          tags: dotfiles
      tags:
        - dotfiles

    # Home Assistant OS VM: preconditions, then vms/haos/setup.sh from the clone (never bridge.sh)
    - name: Provision the Home Assistant OS VM
      ansible.builtin.include_role:
        name: roles/haos
        apply:
          tags: haos
      tags:
        - haos

    # Compose services: sync services/ to ~/docker, render per-service secrets, deploy everything
    - name: Deploy the container services
      ansible.builtin.include_role:
        name: roles/services
        apply:
          tags: services
      tags:
        - services
        - secrets
```

- [ ] **Step 7: Run the tests, the syntax check, and ansible-lint**

Run:
`scripts/hooks/uv-public.sh run pytest tests/unit/test_nas_playbook.py tests/unit/test_services_role.py -q -p no:cacheprovider`
Expected: all pass.

Run: `prek run ansible-lint --all-files`
Expected: Passed.

- [ ] **Step 8: Commit**

```bash
git add playbooks/nas_bootstrap.yml tests/unit/test_nas_playbook.py tests/unit/test_services_role.py
git commit -m "fix(ansible): drop inert configfile and homeassistant tags from the NAS play"
```

Include in the commit body one line recording the Step 2 evidence (the include ran; no inner task did).

---

## Task 2: Render secrets only for services that have a `compose.yml`

`roles/services` renders `env.j2` for every `services/*/env.j2`, including PiHole's although its compose file is
`compose.yml.disabled`. `deploy.sh` ignores services without a `compose.yml`, so the secret has no consumer, and an
undefined vault variable for a disabled service fails the whole play.

**Files:**
- Modify: `tests/unit/test_services_role.py`
- Modify: `roles/services/tasks/main.yml:24-68`

**Interfaces:**
- Consumes: `_render_secrets`, `needs_ansible`, `SERVICES_DIR`, `_task`, `TaskDict` (Task 1 and the existing module)

- [ ] **Step 1: Write the failing tests**

In `TestSecretsRender` (Task 1), replace the single existing test with these four (keep the class decorator and
docstring), and add the module-level helper `_write` above the class:

```python
def _write(path: Path, text: str) -> None:
    """
    Write a file, creating its parent directories
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
```

```python
    def test_renders_an_enabled_service_privately_and_silently(self, tmp_path: Path) -> None:
        """
        Test that --tags secrets renders PiHole's real env.j2 for a service with a compose.yml, 0600, without echoing it

        Guards the first-live-run failure where discovery found no templates and nothing was rendered
        """
        source = tmp_path / 'services'
        _write(source / 'on' / 'compose.yml', 'services: {}\n')
        _write(source / 'on' / 'env.j2', (SERVICES_DIR / 'pihole' / 'env.j2').read_text(encoding='utf-8'))

        code, output, target = _render_secrets(tmp_path, source, 'pihole_web_password=hunter2-test-value')

        assert code == 0, output
        env_file = target / 'on' / '.env'
        assert env_file.read_text(encoding='utf-8').strip() == 'FTLCONF_webserver_api_password=hunter2-test-value'
        assert env_file.stat().st_mode & 0o777 == 0o600
        assert 'hunter2-test-value' not in output
        assert 'Sync compose files' not in output

    def test_skips_a_service_without_a_compose_file(self, tmp_path: Path) -> None:
        """
        Test that a disabled service's template is neither rendered nor required to have its variable defined
        """
        source = tmp_path / 'services'
        _write(source / 'off' / 'compose.yml.disabled', 'services: {}\n')
        _write(source / 'off' / 'env.j2', 'TOKEN={{ off_token }}\n')  # off_token is deliberately undefined

        code, output, target = _render_secrets(tmp_path, source)

        assert code == 0, output
        assert not (target / 'off').exists()

    def test_real_tree_renders_exactly_the_enabled_services(self, tmp_path: Path) -> None:
        """
        Test that the repository's own services/ tree renders a .env for each service with both env.j2 and compose.yml

        The expectation is computed, not hard-coded, so re-enabling PiHole later does not break this test
        """
        enabled = {
            path.parent.name for path in SERVICES_DIR.glob('*/env.j2') if (path.parent / 'compose.yml').is_file()
        }

        code, output, target = _render_secrets(tmp_path, SERVICES_DIR, 'pihole_web_password=hunter2-test-value')

        assert code == 0, output
        assert {path.parent.name for path in target.glob('*/.env')} == enabled

    def test_rendering_nothing_is_not_an_error(self, tmp_path: Path) -> None:
        """
        Test that a tree whose only template belongs to a disabled service renders nothing and still succeeds
        """
        source = tmp_path / 'services'
        _write(source / 'off' / 'compose.yml.disabled', 'services: {}\n')
        _write(source / 'off' / 'env.j2', 'TOKEN=x\n')

        code, output, target = _render_secrets(tmp_path, source)

        assert code == 0, output
        assert not list(target.glob('*/.env'))
```

Also add to `TestServicesRole`:

```python
    def test_secret_tasks_skip_services_without_a_compose_file(self) -> None:
        """
        Test that the directory and render tasks are guarded by the presence of the service's compose.yml
        """
        for name in ('Create per-service secret directories', 'Render per-service secret files'):
            assert "'/compose.yml') is file" in _task('services', name)['when'], name
```

- [ ] **Step 2: Run to verify the failures**

Run:
`scripts/hooks/uv-public.sh run pytest tests/unit/test_services_role.py -q -p no:cacheprovider -k "Secrets or secret_tasks"`
Expected FAIL: `test_skips_a_service_without_a_compose_file` (play fails with an undefined `off_token` variable),
`test_real_tree_renders_exactly_the_enabled_services` (`pihole` is rendered but not enabled),
`test_rendering_nothing_is_not_an_error`, `test_secret_tasks_skip_services_without_a_compose_file` (KeyError `when`).
`test_renders_an_enabled_service_privately_and_silently` passes already.

- [ ] **Step 3: Implement**

In `roles/services/tasks/main.yml`, replace the comment above "Find per-service secret templates" and the two loop
tasks. New text for lines 24-68:

```yaml
# A service opts in with services/<svc>/env.j2 and `env_file: <svc>/.env` in its compose.yml (deploy.sh passes
# --project-directory ~/docker, so the path is relative to that directory). Only services that have a compose.yml are
# rendered: a disabled service (compose.yml.disabled) has no consumer for its secret, and its vault variable may be
# undefined. Discovery uses find, not lookup('fileglob'): fileglob only globs the last path component, so
# services/*/env.j2 silently matches nothing.
# connection: local because the inventory's localhost entry points at 127.0.0.1 over ssh.
- name: Find per-service secret templates
  ansible.builtin.find:
    paths: "{{ services_source_dir }}"
    patterns: env.j2
    recurse: true
    depth: 2
    file_type: file
  delegate_to: localhost
  connection: local
  become: false
  run_once: true
  check_mode: false
  register: services_secret_found
  tags:
    - secrets

- name: Create per-service secret directories
  ansible.builtin.file:
    path: "{{ services_target_dir }}/{{ services_secret_template | dirname | basename }}"
    state: directory
    mode: "0755"
  loop: "{{ services_secret_found.files | map(attribute='path') | sort | list }}"
  loop_control:
    loop_var: services_secret_template
    label: "{{ services_secret_template | dirname | basename }}"
  when: ((services_secret_template | dirname) ~ '/compose.yml') is file
  tags:
    - secrets

# diff is off so rendered values never reach the console or a saved log
- name: Render per-service secret files
  ansible.builtin.template:
    src: "{{ services_secret_template }}"
    dest: "{{ services_target_dir }}/{{ services_secret_template | dirname | basename }}/.env"
    mode: "0600"
  diff: false
  loop: "{{ services_secret_found.files | map(attribute='path') | sort | list }}"
  loop_control:
    loop_var: services_secret_template
    label: "{{ services_secret_template | dirname | basename }}"
  when: ((services_secret_template | dirname) ~ '/compose.yml') is file
  tags:
    - secrets
```

(Lines 1-23 and 70-84 of the file are unchanged.)

- [ ] **Step 4: Run the tests and lint**

Run:
`scripts/hooks/uv-public.sh run pytest tests/unit/test_services_role.py tests/unit/test_service_secrets.py -q -p no:cacheprovider`
Expected: all pass.

Run: `prek run ansible-lint --all-files`
Expected: Passed.

- [ ] **Step 5: Commit**

```bash
git add roles/services/tasks/main.yml tests/unit/test_services_role.py
git commit -m "fix(services): render secrets only for services with a compose file"
```

---

## Task 3: Create the PiHole config directory once, without enforcing its mode

`roles/docker` enforces `mode: "0755"` on `~/docker/pihole-data/etc-pihole` every run. Once PiHole is re-enabled its
container re-owns the bind mount, so the task would report `changed` each run or fail with a permission error.

**Files:**
- Modify: `tests/unit/test_services_role.py` (`TestDockerRole`)
- Modify: `roles/docker/tasks/main.yml:71-81`

**Interfaces:**
- Consumes: `_run_play`, `needs_ansible`, `_task`, `yaml` (Task 1 and the existing module)
- Produces: `_task_play(role: str, *names: str) -> str` (module-level helper in `test_services_role.py`)

- [ ] **Step 1: Write the failing tests**

Add the helper below `_include_play`:

```python
def _task_play(role: str, *names: str) -> str:
    """
    Build a one-play localhost playbook from the named tasks of a role, exactly as the role defines them

    :param role: role directory name
    :param names: task names, in the order they should run
    :return: playbook YAML text
    """
    tasks = [_task(role, name) for name in names]
    return yaml.safe_dump([{'hosts': 'all', 'gather_facts': False, 'connection': 'local', 'tasks': tasks}])
```

Add to `TestDockerRole`:

```python
    def test_directory_loop_leaves_the_pihole_path_to_the_guarded_task(self) -> None:
        """
        Test that the enforced-mode directory loop no longer includes the PiHole config directory
        """
        loop = _task('docker', 'Create docker directory structure')['loop']
        assert not any('pihole' in entry for entry in loop), loop

    @needs_ansible
    def test_pihole_config_dir_is_created_once_and_never_re_enforced(self, tmp_path: Path) -> None:
        """
        Test that a container re-chmodding the bind mount does not make later runs report changed or reset the mode
        """
        play = _task_play(
            'docker', 'Check for the PiHole config directory', 'Create the PiHole config directory',
        )
        docker_dir = tmp_path / 'docker'
        pihole     = docker_dir / 'pihole-data' / 'etc-pihole'

        code, output = _run_play(tmp_path, play, '-e', f'docker_dir={docker_dir}')
        assert code == 0, output
        assert pihole.is_dir()
        assert 'changed=1' in output, output

        pihole.chmod(0o775)  # what a running container may do to its bind mount
        code, output = _run_play(tmp_path, play, '-e', f'docker_dir={docker_dir}')
        assert code == 0, output
        assert 'changed=0' in output, output
        assert pihole.stat().st_mode & 0o777 == 0o775
```

- [ ] **Step 2: Run to verify the failures**

Run: `scripts/hooks/uv-public.sh run pytest tests/unit/test_services_role.py -q -p no:cacheprovider -k "pihole"`
Expected FAIL: the loop test (`pihole` is in the loop) and the real-run test
(`expected exactly one task named 'Check for the PiHole config directory'`).

- [ ] **Step 3: Implement**

In `roles/docker/tasks/main.yml`, replace the "Create docker directory structure" task (lines 71-81) with:

```yaml
    - name: Create docker directory structure
      ansible.builtin.file:
        path: "{{ docker_dir_path }}"
        state: directory
        mode: "0755"
      loop:
        - "{{ docker_dir }}"
        - "{{ docker_dir }}/.build"
      loop_control:
        loop_var: docker_dir_path

    # PiHole re-owns this bind mount once it runs, so create the directory once and never enforce its mode or owner
    # afterwards (an enforced mode would report changed, or fail, on every run)
    - name: Check for the PiHole config directory
      ansible.builtin.stat:
        path: "{{ docker_dir }}/pihole-data/etc-pihole"
      register: docker_pihole_config_dir

    - name: Create the PiHole config directory
      ansible.builtin.file:
        path: "{{ docker_dir }}/pihole-data/etc-pihole"
        state: directory
        mode: "0755"
      when: not docker_pihole_config_dir.stat.exists
```

- [ ] **Step 4: Run the tests and lint**

Run: `scripts/hooks/uv-public.sh run pytest tests/unit/test_services_role.py -q -p no:cacheprovider`
Expected: all pass.

Run: `prek run ansible-lint --all-files`
Expected: Passed.

- [ ] **Step 5: Commit**

```bash
git add roles/docker/tasks/main.yml tests/unit/test_services_role.py
git commit -m "fix(docker): create the PiHole config directory once, without enforcing its mode"
```

---

## Task 4: Harden `deploy-services.sh`

Add `--` before the ssh target and the rsync operands, refuse a `NAS_USER`/`NAS_HOST` that starts with `-`, and keep a
`NAS_SSH_KEY` path containing spaces intact through `rsync -e` (rsync re-splits the `-e` string on whitespace and
honours single quotes, not backslashes).

**Files:**
- Modify: `scripts/nas/deploy-services.sh:32-70`
- Replace: `tests/unit/test_deploy_services.py`

**Interfaces:**
- Produces: the script's observable argv contract:
  `ssh [-i KEY -o StrictHostKeyChecking=accept-new] -- USER@HOST '~/docker/deploy.sh SERVICE'`;
  `rsync <flags> -e '<rsh>' -- SRC DEST`; exit code 2 for refused input.

- [ ] **Step 1: Write the failing tests**

Replace `tests/unit/test_deploy_services.py` with:

```python
"""
Unit tests for scripts/nas/deploy-services.sh (stubbed rsync and ssh: no NAS or network needed)
"""
from __future__ import annotations

import os
import re
import shlex
import shutil
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

# Like STUB, but wraps every argument in brackets so argument boundaries survive (a path with spaces stays one word)
ARGV_STUB = (
    '#!/bin/sh\n'
    'line="$(basename "$0")"\n'
    'for arg in "$@"; do line="$line [$arg]"; done\n'
    'printf "%s\\n" "$line" >> "$STUB_LOG"\n'
)


def _stub_env(tmp_path: Path, stub: str) -> dict[str, str]:
    """
    Environment with stubbed rsync and ssh first on PATH, plus the required NAS variables
    """
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    for name in ('rsync', 'ssh'):
        path = bin_dir / name
        path.write_text(stub, encoding='utf-8')
        path.chmod(0o755)

    return {
        **{key: value for key, value in os.environ.items() if not key.startswith('NAS_')},
        'PATH':     f'{bin_dir}:{os.environ["PATH"]}',
        'STUB_LOG': str(tmp_path / 'calls.log'),
        'NAS_HOST': 'nas.example',
        'NAS_USER': 'tester',
    }


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    """
    Stubbed rsync and ssh that log their arguments space-joined
    """
    return _stub_env(tmp_path, STUB)


@pytest.fixture
def argv_env(tmp_path: Path) -> dict[str, str]:
    """
    Stubbed rsync and ssh that log each argument in brackets
    """
    return _stub_env(tmp_path, ARGV_STUB)


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


def _words(call: str) -> list[str]:
    """
    Split a bracketed stub log line into its arguments (the stub name is dropped)
    """
    return re.findall(r'\[([^\]]*)\]', call)


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
        assert calls[2] == 'ssh -- tester@nas.example ~/docker/deploy.sh glance'

    def test_operands_follow_a_double_dash(self, env: dict[str, str]) -> None:
        """
        Test that rsync receives its source and destination after --, so they can never be read as options
        """
        _run(env, 'glance')

        rsync_calls = [call for call in _calls(env) if call.startswith('rsync ')]
        assert len(rsync_calls) == 2
        for call in rsync_calls:
            assert ' -- ' in call

    def test_rsync_skips_templates_and_env_files(self, env: dict[str, str]) -> None:
        """
        Test that rsync never ships *.j2 templates or .env files, and never deletes
        """
        _run(env, 'glance')

        calls = _calls(env)
        assert len(calls) == 3
        for call in calls[:2]:
            assert '--exclude=*.j2' in call
            assert '--exclude=.env'  in call
            assert '--delete'    not in call

    @pytest.mark.parametrize('service', ['glance', 'all'])
    def test_rsync_is_idempotent_and_skips_laptop_junk(self, env: dict[str, str], service: str) -> None:
        """
        Test that rsync ignores directory mtimes, backups, and .DS_Store files
        """
        _run(env, service)

        rsync_calls = [call for call in _calls(env) if call.startswith('rsync ')]
        assert rsync_calls
        for call in rsync_calls:
            for flag in ('--omit-dir-times', '--exclude=.backups/', '--exclude=.DS_Store'):
                assert flag in call

    def test_key_adds_identity_and_host_key_policy(self, env: dict[str, str]) -> None:
        """
        Test that NAS_SSH_KEY reaches both the rsync transport and the ssh call
        """
        env['NAS_SSH_KEY'] = '/keys/id_nas'
        _run(env, 'glance')

        option = '-i /keys/id_nas -o StrictHostKeyChecking=accept-new'
        calls  = _calls(env)
        assert "-e ssh -i '/keys/id_nas' -o StrictHostKeyChecking=accept-new" in calls[0]
        assert calls[2] == f'ssh {option} -- tester@nas.example ~/docker/deploy.sh glance'


class TestKeyHandling:
    """
    Tests for NAS_SSH_KEY paths and for values that could be read as options
    """
    def test_key_path_with_spaces_stays_one_word(self, argv_env: dict[str, str], tmp_path: Path) -> None:
        """
        Test that a key path containing a space is one ssh argument and one word in rsync's -e string
        """
        key = tmp_path / 'my keys' / 'id_nas'
        argv_env['NAS_SSH_KEY'] = str(key)

        result = _run(argv_env, 'glance')

        assert result.returncode == 0, result.stderr
        calls = _calls(argv_env)
        assert len(calls) == 3
        assert _words(calls[2]) == [
            '-i', str(key), '-o', 'StrictHostKeyChecking=accept-new', '--', 'tester@nas.example',
            '~/docker/deploy.sh glance',
        ]
        rsync_words = _words(calls[0])
        rsh         = rsync_words[rsync_words.index('-e') + 1]
        assert shlex.split(rsh) == ['ssh', '-i', str(key), '-o', 'StrictHostKeyChecking=accept-new']
        assert rsync_words[-3] == '--'

    def test_key_path_with_a_single_quote_is_refused(self, env: dict[str, str]) -> None:
        """
        Test that a key path rsync's -e quoting cannot carry exits 2 before any network call
        """
        env['NAS_SSH_KEY'] = "/keys/o'brien"

        result = _run(env, 'glance')

        assert result.returncode == 2
        assert 'single quote' in result.stderr
        assert _calls(env) == []

    @pytest.mark.parametrize('name', ['NAS_USER', 'NAS_HOST'])
    def test_option_like_user_or_host_is_refused(self, env: dict[str, str], name: str) -> None:
        """
        Test that a value starting with - exits 2 before any network call
        """
        env[name] = '-oProxyCommand=evil'

        result = _run(env, 'glance')

        assert result.returncode == 2
        assert 'must not start with' in result.stderr
        assert _calls(env) == []

    @pytest.mark.skipif(shutil.which('rsync') is None, reason='rsync not installed')
    def test_real_rsync_hands_a_key_path_with_spaces_to_ssh_as_one_word(self, tmp_path: Path) -> None:
        """
        Test that rsync's own -e parsing keeps the quoted key path whole (skipped on openrsync, which may differ)
        """
        version = subprocess.run(['rsync', '--version'], capture_output=True, text=True, check=False).stdout
        if 'openrsync' in version.lower():
            pytest.skip('openrsync may split -e differently; GNU rsync is what CI uses')

        bin_dir = tmp_path / 'bin'
        bin_dir.mkdir()
        ssh = bin_dir / 'ssh'
        ssh.write_text(ARGV_STUB + 'exit 255\n', encoding='utf-8')
        ssh.chmod(0o755)

        key = tmp_path / 'my keys' / 'id_nas'
        env = {
            **os.environ,
            'PATH':        f'{bin_dir}:{os.environ["PATH"]}',
            'STUB_LOG':    str(tmp_path / 'calls.log'),
            'NAS_HOST':    'nas.example',
            'NAS_USER':    'tester',
            'NAS_SSH_KEY': str(key),
        }

        _run(env, 'glance')  # real rsync fails against the stub ssh; only the arguments it passed matter

        first = _calls(env)[0]
        assert _words(first)[:4] == ['-i', str(key), '-o', 'StrictHostKeyChecking=accept-new']


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
        assert calls[1] == 'ssh -- tester@nas.example ~/docker/deploy.sh all'


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
        assert 'dry-run: would run: ssh -- tester@nas.example ~/docker/deploy.sh glance' in result.stdout

    def test_dry_run_escapes_a_key_path_with_spaces(self, env: dict[str, str]) -> None:
        """
        Test that the printed ssh command escapes a key path containing a space, so it can be pasted into a shell
        """
        env['NAS_SSH_KEY'] = '/keys/my keys/id'

        result = _run(env, '--dry-run', 'glance')

        assert result.returncode == 0, result.stderr
        assert (
            r'dry-run: would run: ssh -i /keys/my\ keys/id -o StrictHostKeyChecking=accept-new '
            '-- tester@nas.example ~/docker/deploy.sh glance'
        ) in result.stdout


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

- [ ] **Step 2: Run to verify the failures**

Run: `scripts/hooks/uv-public.sh run pytest tests/unit/test_deploy_services.py -q -p no:cacheprovider`
Expected FAIL: every test asserting `--` (`ssh -- ...`), the key tests (`-e ssh -i '...'`), the three refusal tests
(`returncode == 0`, not 2), the `%q` dry-run test. The real-rsync test is skipped on this Mac (openrsync). The unchanged
tests (validation, excludes, idempotent flags) still pass.

- [ ] **Step 3: Implement**

In `scripts/nas/deploy-services.sh`, replace everything from the line `[[ -n "${NAS_HOST:-}" ]] || die ...` through the
end of the file with:

```bash
[[ -n "${NAS_HOST:-}" ]] || die "NAS_HOST is not set"
[[ -n "${NAS_USER:-}" ]] || die "NAS_USER is not set"

# A leading '-' would let ssh or rsync read the destination as an option
[[ "$NAS_HOST" != -* ]] || die "NAS_HOST must not start with '-'"
[[ "$NAS_USER" != -* ]] || die "NAS_USER must not start with '-'"

# A service is a directory under services/; refuse anything that could escape it or reach the remote shell
if [[ "$service" != "all" ]]; then
    [[ "$service" =~ ^[a-z0-9][a-z0-9_-]*$ ]] || die "invalid service name: ${service}"
    [[ -f "${services_dir}/${service}/compose.yml" ]] || die "no services/${service}/compose.yml"
fi

target="${NAS_USER}@${NAS_HOST}"
ssh_cmd=(ssh)
rsh="ssh"
if [[ -n "${NAS_SSH_KEY:-}" ]]; then
    # rsync splits its -e string on whitespace but honours single quotes (not backslashes), so the key path is quoted
    # there and refused when it contains a quote itself
    [[ "$NAS_SSH_KEY" != *\'* ]] || die "NAS_SSH_KEY must not contain a single quote"
    ssh_cmd+=(-i "$NAS_SSH_KEY" -o StrictHostKeyChecking=accept-new)
    rsh="ssh -i '${NAS_SSH_KEY}' -o StrictHostKeyChecking=accept-new"
fi

rsync_flags=(-avz --omit-dir-times --exclude='*.j2' --exclude='.env' --exclude='.backups/' --exclude='.DS_Store')
if [[ $dry_run -eq 1 ]]; then
    rsync_flags+=(-n)
fi

push() {
    rsync "${rsync_flags[@]}" -e "$rsh" -- "$1" "$2"
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
    echo "dry-run: would run: $(printf '%q ' "${ssh_cmd[@]}")-- ${target} ${remote}"
else
    "${ssh_cmd[@]}" -- "$target" "$remote"
fi
```

(The header comment block and lines 14-30 stay unchanged. Task 1's `test_role_and_script_share_the_same_rsync_filters`
still finds the `rsync_flags=(` line.)

- [ ] **Step 4: Run the tests**

Run:
`scripts/hooks/uv-public.sh run pytest tests/unit/test_deploy_services.py tests/unit/test_services_role.py -q -p no:cacheprovider`
Expected: all pass (the real-rsync test shows as skipped on this Mac).

Also run the bash-3.2 syntax check: `/bin/bash -n scripts/nas/deploy-services.sh` (no output = valid).

- [ ] **Step 5: Commit**

```bash
git add scripts/nas/deploy-services.sh tests/unit/test_deploy_services.py
git commit -m "fix(nas): harden deploy-services.sh against option injection and key paths with spaces"
```

---

## Task 5: Pass deploy secrets through `env:`

`deploy.yml` interpolates `${{ secrets.NAS_SSH_PRIVATE_KEY }}` and `${{ secrets.NAS_TAILSCALE_HOST }}` into shell text
in both deploy jobs. Move them to `env:` so the shell never parses secret content.

**Files:**
- Modify: `.github/workflows/deploy.yml` (steps `Detect changed services`, and `Set up SSH key` in `deploy-push` and
  `deploy-manual`)
- Modify: `tests/unit/test_deploy_workflow.py`

- [ ] **Step 1: Write the failing tests**

Add imports at the top of `tests/unit/test_deploy_workflow.py`: `import os` and `import subprocess` (one per line,
alphabetical, before `from pathlib import Path`). Append to `TestDeployWorkflow`:

```python
    @pytest.mark.parametrize('job', ['detect-changes', 'deploy-push', 'deploy-manual'])
    def test_no_script_interpolates_an_expression(self, job: str) -> None:
        """
        Test that no run step interpolates a ${{ }} expression, so secrets and event data travel through env
        """
        for step in _steps(job):
            assert '${{' not in step.get('run', ''), step.get('name')

    @pytest.mark.parametrize('job', ['deploy-push', 'deploy-manual'])
    def test_ssh_key_step_takes_the_secrets_through_env(self, job: str) -> None:
        """
        Test that the key step reads the private key and host from env variables
        """
        steps = [step for step in _steps(job) if step.get('name') == 'Set up SSH key']

        assert len(steps) == 1
        step = steps[0]
        assert set(step['env']) == {'NAS_SSH_PRIVATE_KEY', 'NAS_HOST'}
        assert '"$NAS_SSH_PRIVATE_KEY"' in step['run']
        assert '"$NAS_HOST"' in step['run']

    @pytest.mark.parametrize('job', ['deploy-push', 'deploy-manual'])
    def test_ssh_key_step_writes_a_private_key_file(self, job: str, tmp_path: Path) -> None:
        """
        Test that running the key step's script writes the key verbatim to a 0600 file in a 0700 directory
        """
        step = next(step for step in _steps(job) if step.get('name') == 'Set up SSH key')

        bin_dir = tmp_path / 'bin'
        bin_dir.mkdir()
        keyscan = bin_dir / 'ssh-keyscan'
        keyscan.write_text('#!/bin/sh\nexit 0\n', encoding='utf-8')
        keyscan.chmod(0o755)
        home = tmp_path / 'home'
        home.mkdir()
        key = '-----BEGIN KEY-----\nline-two\n-----END KEY-----'

        subprocess.run(
            ['/bin/bash', '-e', '-c', step['run']],
            check=True,
            capture_output=True,
            env={
                'PATH': f'{bin_dir}:{os.environ["PATH"]}',
                'HOME': str(home),
                'NAS_SSH_PRIVATE_KEY': key,
                'NAS_HOST': 'nas.example',
            },
        )

        private = home / '.ssh' / 'id_nas'
        assert private.read_text(encoding='utf-8') == key + '\n'
        assert private.stat().st_mode & 0o777 == 0o600
        assert (home / '.ssh').stat().st_mode & 0o777 == 0o700
```

- [ ] **Step 2: Run to verify the failures**

Run: `scripts/hooks/uv-public.sh run pytest tests/unit/test_deploy_workflow.py -q -p no:cacheprovider`
Expected FAIL: `test_no_script_interpolates_an_expression[detect-changes]`, `[deploy-push]`, `[deploy-manual]`;
`test_ssh_key_step_takes_the_secrets_through_env` (KeyError `env`); `test_ssh_key_step_writes_a_private_key_file`.

- [ ] **Step 3: Implement**

In `.github/workflows/deploy.yml`:

(a) Replace the `Detect changed services` step header and its first lines, and the two `${{ github.sha }}` uses:

```yaml
      - name: Detect changed services
        id: detect
        env:
          BEFORE: ${{ github.event.before }}
          SHA: ${{ github.sha }}
        run: |
          # Fallback for force pushes or new branches (null SHA)
          if [[ "$BEFORE" == "0000000000000000000000000000000000000000" ]]; then
```

i.e. delete the line `BEFORE="${{ github.event.before }}"` (and the blank line after it). Then change
`git diff --name-only "$BEFORE".."${{ github.sha }}" | grep -q ...` to
`git diff --name-only "$BEFORE".."$SHA" | grep -q ...` and
`CHANGED_SERVICES=$(git diff --name-only "$BEFORE".."${{ github.sha }}" \` to
`CHANGED_SERVICES=$(git diff --name-only "$BEFORE".."$SHA" \`.

(b) In **both** `deploy-push` and `deploy-manual`, replace the `Set up SSH key` step with:

```yaml
      - name: Set up SSH key
        env:
          NAS_SSH_PRIVATE_KEY: ${{ secrets.NAS_SSH_PRIVATE_KEY }}
          NAS_HOST: ${{ secrets.NAS_TAILSCALE_HOST }}
        run: |
          umask 077
          mkdir -p ~/.ssh
          printf '%s\n' "$NAS_SSH_PRIVATE_KEY" > ~/.ssh/id_nas
          ssh-keyscan -H "$NAS_HOST" >> ~/.ssh/known_hosts 2>/dev/null || true
```

- [ ] **Step 4: Run the tests and the YAML lint**

Run: `scripts/hooks/uv-public.sh run pytest tests/unit/test_deploy_workflow.py -q -p no:cacheprovider`
Expected: all pass.

Run: `prek run yamllint --files .github/workflows/deploy.yml`
Expected: Passed. (If the hook id differs, run `prek run --files .github/workflows/deploy.yml`.)

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/deploy.yml tests/unit/test_deploy_workflow.py
git commit -m "fix(ci): pass deploy secrets through env instead of shell interpolation"
```

---

## Task 6: Remove stale entries for the deleted `get_lutron_cert.py`

`.secrets.baseline` still lists
`services/homeassistant/config/{scripts/get_lutron_cert.py,secrets_template.yaml,www/hass.html}`, none of which exists
any more, and `pyproject.toml` carries a ruff per-file ignore for `get_lutron_cert.py`. A new test stops path-keyed
configuration from naming files that are gone.

**Files:**
- Create: `tests/unit/test_repo_hygiene.py`
- Modify: `.secrets.baseline` (delete three keys)
- Modify: `pyproject.toml:308`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_repo_hygiene.py`:

```python
"""
Guardrail tests that keep path-keyed configuration from naming files that no longer exist
"""
from __future__ import annotations

import json
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


class TestPathKeyedConfig:
    """
    Tests for configuration files whose keys are repository paths
    """
    def test_secrets_baseline_names_only_existing_files(self) -> None:
        """
        Test that every file listed in .secrets.baseline still exists
        """
        results = json.loads((REPO_ROOT / '.secrets.baseline').read_text(encoding='utf-8'))['results']

        missing = sorted(name for name in results if not (REPO_ROOT / name).exists())

        assert not missing, f'.secrets.baseline lists files that no longer exist: {missing}'

    def test_ruff_per_file_ignores_match_existing_paths(self) -> None:
        """
        Test that every ruff per-file-ignores pattern in pyproject.toml matches at least one path
        """
        config   = tomllib.loads((REPO_ROOT / 'pyproject.toml').read_text(encoding='utf-8'))
        patterns = config['tool']['ruff']['lint']['per-file-ignores']

        unmatched = sorted(pattern for pattern in patterns if not any(REPO_ROOT.glob(pattern)))

        assert not unmatched, f'pyproject.toml per-file-ignores match nothing: {unmatched}'
```

- [ ] **Step 2: Run to verify the failures**

Run: `scripts/hooks/uv-public.sh run pytest tests/unit/test_repo_hygiene.py -q -p no:cacheprovider`
Expected FAIL: the baseline test lists the three `services/homeassistant/config/...` files; the ruff test lists
`services/homeassistant/config/scripts/get_lutron_cert.py`. If either test names an additional file, inspect it: delete
the entry only if the file is truly gone from the repository (`ls`), otherwise stop and report.

- [ ] **Step 3: Delete the stale entries**

In `.secrets.baseline`, read lines 190-250, then remove the three object keys
`"services/homeassistant/config/scripts/get_lutron_cert.py"`, `"services/homeassistant/config/secrets_template.yaml"`,
and `"services/homeassistant/config/www/hass.html"` together with their arrays (currently lines 196-243, from
`    "services/homeassistant/config/scripts/get_lutron_cert.py": [` through the `    ],` that closes the `hass.html`
array). The key before them (`render/claude.json`, whose array ends `    ],` on line 195) must be followed directly by
`    "stow/claude/.claude/hooks/secret-scanner.sh": [`. Do **not** rescan with `detect-secrets` (it would add `archive/`
noise). Leave `generated_at` alone.

In `pyproject.toml`, delete the line `"services/homeassistant/config/scripts/get_lutron_cert.py" = ["S"]` from
`[tool.ruff.lint.per-file-ignores]`.

- [ ] **Step 4: Verify**

Run: `scripts/hooks/uv-public.sh run python -I -m json.tool .secrets.baseline > /dev/null` (no output = valid JSON).
Run: `scripts/hooks/uv-public.sh run pytest tests/unit/test_repo_hygiene.py -q -p no:cacheprovider`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add .secrets.baseline pyproject.toml tests/unit/test_repo_hygiene.py
git commit -m "chore: drop baseline and lint entries for the deleted get_lutron_cert.py"
```

If the `taplo` hook re-aligns `pyproject.toml` (the per-file-ignores columns shrink once the longest key is gone), the
commit fails once; re-stage `pyproject.toml` and commit again.

---

## Task 7: Fail early with a clear message when `uv` is missing

Without `uv`, `nas_bootstrap.sh` dies with bash's `exec: ...: not found`, and `run.py` reports a misleading "Could not
read host nas from the inventory".

**Files:**
- Modify: `nas_bootstrap.sh:15-17`
- Modify: `tests/unit/test_nas_bootstrap.py`

Constraint from the existing test `test_installs_nothing_on_the_controller`: the script text (lowercased) must not
contain `brew`, `/opt/`, `shasum`, `curl`, or `ansible-playbook`.

- [ ] **Step 1: Write the failing tests**

Add `import shutil` and `import subprocess` to the imports of `tests/unit/test_nas_bootstrap.py` (alphabetical, one per
line). Append to `TestNasBootstrapScript`:

```python
    def test_stops_with_a_clear_message_when_uv_is_missing(self, tmp_path: Path) -> None:
        """
        Test that a PATH without uv ends the script with exit 1 and a message naming uv, before any exec
        """
        bin_dir = tmp_path / 'bin'
        bin_dir.mkdir()
        (bin_dir / 'dirname').symlink_to(shutil.which('dirname') or '/usr/bin/dirname')

        result = subprocess.run(
            ['/bin/bash', str(self.SCRIPT)],
            capture_output=True,
            text=True,
            check=False,
            env={'PATH': str(bin_dir)},
        )

        assert result.returncode == 1
        assert 'uv is required' in result.stderr

    def test_uv_check_precedes_the_exec(self) -> None:
        """
        Test that the uv guard sits before the exec line, so a missing uv never reaches the wrapper
        """
        text = self.SCRIPT.read_text(encoding='utf-8')
        assert text.index('command -v uv') < text.index('exec "${SCRIPT_DIR}')
```

- [ ] **Step 2: Run to verify the failures**

Run: `scripts/hooks/uv-public.sh run pytest tests/unit/test_nas_bootstrap.py -q -p no:cacheprovider`
Expected FAIL: both new tests (`.returncode` is 127, not 1 — bash's `exec: ... not found` — and `command -v uv` is
absent, `ValueError: substring not found`).

- [ ] **Step 3: Implement**

In `nas_bootstrap.sh`, insert between the layout check's closing `fi` and the `exec` line:

```bash
if ! command -v uv >/dev/null 2>&1; then
    echo "ERROR: uv is required to run the Ansible tooling but was not found on PATH." >&2
    echo "Install it (https://docs.astral.sh/uv/getting-started/installation/) and re-run." >&2
    exit 1
fi

```

(keep a blank line before `exec`). The `exec "${SCRIPT_DIR}/scripts/hooks/uv-public.sh" run python ... "$@"` line stays
byte-for-byte unchanged.

- [ ] **Step 4: Run the tests**

Run: `scripts/hooks/uv-public.sh run pytest tests/unit/test_nas_bootstrap.py -q -p no:cacheprovider`
Expected: all pass (including `test_delegates_to_nas_provision_through_uv` and
`test_installs_nothing_on_the_controller`).

- [ ] **Step 5: Commit**

```bash
git add nas_bootstrap.sh tests/unit/test_nas_bootstrap.py
git commit -m "feat(nas): fail early with a clear message when uv is missing"
```

(The README prerequisite line lands in Task 14.)

---

## Task 8: Cover non-object `ansible-inventory` output in `resolve_nas_target`

`resolve_nas_target` exits 1 when `ansible-inventory --host` prints something that is not a JSON object. Only
unparsable text is tested today; valid JSON that is not an object (`[]`, `null`, a string, a number) is not. This is a
coverage test for existing behavior; there is no code change and `run.py` is not edited.

**Files:**
- Modify: `tests/unit/test_run_nas.py` (`TestResolveNasTarget`, after `test_unparseable_output_exits`)

- [ ] **Step 1: Add the test**

```python
    @pytest.mark.parametrize('stdout', ['[]', 'null', '"nas"', '42'])
    def test_valid_json_that_is_not_an_object_exits(
        self,
        fake_shell: FakeShell,
        capsys: pytest.CaptureFixture[str],
        stdout: str,
    ) -> None:
        """
        Test that valid JSON other than an object exits 1 as unexpected output instead of crashing on a missing .get
        """
        fake_shell.results['ansible-inventory'] = _done(stdout=stdout)

        with pytest.raises(SystemExit) as exc_info:
            run.resolve_nas_target()

        assert exc_info.value.code == 1
        assert 'Unexpected ansible-inventory output for host "nas"' in _output(capsys)
```

- [ ] **Step 2: Run it (it passes immediately), then prove it pins the branch**

Run: `scripts/hooks/uv-public.sh run pytest tests/unit/test_run_nas.py -q -p no:cacheprovider -k valid_json_that_is_not`
Expected: 4 passed.

Mutation check (temporary; `run.py` must end unchanged): in `run.py`, change `if not isinstance(variables, dict):` to
`if False:`, re-run the command above, and confirm all four FAIL (an `AttributeError` or `TypeError` instead of
`SystemExit`). Then restore with `git checkout run.py` and confirm `git diff --stat run.py` prints nothing.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_run_nas.py
git commit -m "test(run): cover valid-JSON-but-not-an-object output in resolve_nas_target"
```

---

## Task 9: Rewrite `roles/docker/README.md`

The 1,087-line README describes a single-compose-file design (`docker-compose.yml`, PiHole/Home
Assistant/Caddy/PyAutoplex builds, DNSimple, Lutron certificates). The role now installs Docker Engine, prepares
`~/docker`, builds one image, and installs `deploy.sh`. Write a role README of roughly 110-130 lines that matches
`roles/dotfiles/README.md` in style.

**Files:**
- Replace: `roles/docker/README.md`

**Sources to read first:** `roles/docker/tasks/main.yml`, `roles/docker/defaults/main.yml`,
`roles/docker/files/deploy.sh`, `roles/docker/templates/env.j2`, `roles/services/README.md`,
`roles/services/tasks/main.yml`, `tests/unit/test_services_role.py::test_target_dir_matches_the_docker_role`,
`roles/tailscale/defaults/main.yml`. Use `roles/dotfiles/README.md` as the style model.

- [ ] **Step 1: Re-read the sources and verify these facts** (each came from an audit; correct any that no longer hold)

  - Tasks, in order (`tasks/main.yml`): (1) `apt` install `ca-certificates`, `curl`, `gnupg`; (2) `get_url` the Docker
    GPG key to `/usr/share/keyrings/docker.asc` (0644, root); (3) `dpkg --print-architecture` (read-only, runs in check
    mode); (4) `apt_repository` adds the Docker apt source (and refreshes the index); (5) `apt` installs `docker-ce`,
    `docker-ce-cli`, `containerd.io`, `docker-buildx-plugin`, `docker-compose-plugin`, and the legacy `docker-compose`
    package; (6) `service` starts `docker`; (7) `user` adds the SSH user to the `docker` group; (8) `file` creates
    `~/docker` and `~/docker/.build` (0755) enforced, then `~/docker/pihole-data/etc-pihole` only when absent (Task 3);
    (9) `template` renders `~/docker/.env` (0600, `diff: false`, tag `configfile`) from `env.j2`; (10) `git` clones
    autoplex to `docker_autoplex_repo_dest`; (11) `community.docker.docker_image` builds `danielmmetz/autoplex:latest`
    from the clone (root); (12) `copy` installs `files/deploy.sh` to `~/docker/deploy.sh` (0755, tag `configfile`).
  - Variables (`defaults/main.yml`): `docker_dir` (`{{ ansible_facts['user_dir'] }}/docker`),
    `docker_autoplex_repo_dest` (`{{ docker_dir }}/.build/autoplex`), `docker_autoplex_repo_url`
    (`https://github.com/danielmmetz/autoplex.git`), `docker_autoplex_repo_branch` (`master`). A test requires every
    default to start with `docker_`.
  - Inventory inputs of `env.j2`: `tailscale_tailnet_name` (required) and `tailscale_hostname` (optional, falls back to
    `inventory_hostname`); the port `32443` is hard-coded in `env.j2` and in `services/caddy/compose.yml`. The rendered
    file holds only `ADVERTISE_IP` (the `tailscale` role runs after `docker`, so its defaults are not loaded here).
  - Tags: playbook include tags are `docker` and `configfile`; `apply` hands `docker` to every task; only tasks 9 and 12
    also carry `configfile`. On a fresh host `--tags configfile` fails at the `.env` render because `~/docker` does not
    exist yet (run `--tags docker` first). Both claims were verified for real during planning: with a pre-created
    `docker_dir`, `--tags configfile` ran exactly "Render docker .env file" and "Copy deploy script" and left `.env` and
    `deploy.sh`; with a missing `docker_dir` the `.env` task failed with "Destination directory ... does not exist".
  - Contract with `services`: `docker_dir` must equal `services_target_dir` (pinned by
    `test_target_dir_matches_the_docker_role`); the docker-group membership lets the `services` role run `deploy.sh`
    through `become` as the same user; `deploy.sh <svc|all>` discovers `~/docker/*/compose.yml` and runs
    `docker compose --project-directory ~/docker -f compose.base.yml -f <svc>/compose.yml up -d <svc>` with
    `COMPOSE_IGNORE_ORPHANS=true`.
  - Not done by this role: syncing compose files, rendering per-service secrets, starting services (the `services`
    role), Caddy configuration (the `tailscale` role), Home Assistant (the `haos` role), `/etc/docker/daemon.json`.
  - The autoplex compose entry has no `build:`; the image only exists after this role has run.

- [ ] **Step 2: Write the README**

Outline (headings in this order): breadcrumb line; `# docker` with a one-paragraph purpose; the mdformat-toc block;
`## Tasks` (ordered table: step, module, effect); `## What it installs` (table: path or object, mode, source);
`## Variables` (table with the four `docker_*` defaults and the two inventory inputs); `## Tags and running`
(`python3 run.py nas-provision --tags docker`; which tasks `configfile` reaches; fresh-host caveat); `## Autoplex image`
(clone path, branch, tag, rebuild behavior: `git update` on every run so it can report changed when upstream moves);
`## Contract with the services role` (the three coupling points above plus reverse dependencies); `## Related` (links to
[`services/README.md`](../../services/README.md), [`roles/services/README.md`](../services/README.md),
[`roles/tailscale/README.md`](../tailscale/README.md), [`vms/haos/README.md`](../../vms/haos/README.md)). No "License"
footer, no troubleshooting for removed components, no diagrams.

- [ ] **Step 3: Verify**

  - `wc -l roles/docker/README.md` is between 90 and 140.
  - Every relative link resolves (see Task 17 Step 3 for the link checker; run it on this file now).
  - The content of the old README that is still true and belongs to the stack (data flow, storage layout, backups,
    image-update caveat) is **not** lost: Task 10 moves it into `services/README.md`. Before overwriting, copy the old
    file to `$TMPDIR/docker-readme-old.md` for Task 10 to read.

- [ ] **Step 4: Commit**

```bash
git add roles/docker/README.md
git commit -m "docs(docker): rewrite the role README for what the role does today"
```

---

## Task 10: Correct `services/README.md`, add stack operations, add drift guard 1

**Files:**
- Modify: `services/README.md`
- Modify: `tests/unit/test_docs_consistency.py`

**Sources:** `services/compose.base.yml`, every `services/*/compose.yml{,.disabled}` and `env.j2`,
`roles/docker/tasks/main.yml`, `roles/docker/files/deploy.sh`, `roles/docker/templates/env.j2`,
`roles/tailscale/templates/Caddyfile.j2`, `scripts/nas/deploy-services.sh`, `.github/workflows/deploy.yml`,
`vms/haos/README.md`, and the old docker README saved by Task 9 at `$TMPDIR/docker-readme-old.md`.

- [ ] **Step 1: Write guard 1 first**

Add `import yaml` (third-party group) to `tests/unit/test_docs_consistency.py`, then append:

```python
# A services/README.md Quick Reference row: the container name in the first cell (e.g. ``| `caddy` | ...``)
SERVICE_ROW = re.compile(r'^\|\s*`([a-z0-9_-]+)`\s*\|(.*)$', re.MULTILINE)


def _services_readme_rows(repo: Path) -> dict[str, str]:
    """
    Return the rows of the ``services/README.md`` Quick Reference table, keyed by container name

    :param repo: repository root
    :return: mapping of container name to the remainder of its table row
    """
    text  = (repo / 'services' / 'README.md').read_text(encoding='utf-8')
    quick = text.split('## Quick Reference', 1)[1].split('\n## ', 1)[0]
    return dict(SERVICE_ROW.findall(quick))


def _compose_containers(repo: Path) -> dict[str, bool]:
    """
    Return every container defined under ``services/`` and whether its compose file is enabled

    :param repo: repository root
    :return: mapping of container name (``container_name``, else the service key) to True for ``compose.yml`` and
             False for ``compose.yml.disabled``
    """
    found: dict[str, bool] = {}
    for path in sorted((repo / 'services').glob('*/compose.yml*')):
        if path.name not in ('compose.yml', 'compose.yml.disabled'):
            continue
        for key, service in yaml.safe_load(path.read_text(encoding='utf-8'))['services'].items():
            found[service.get('container_name', key)] = path.name == 'compose.yml'
    return found


class TestServicesReadme:
    """
    Guardrails tying the services/README.md container table to the compose files
    """
    def test_container_table_matches_compose_files(self) -> None:
        """
        The Quick Reference table lists exactly the containers the compose files define
        """
        documented = set(_services_readme_rows(REPO_ROOT))
        on_disk    = set(_compose_containers(REPO_ROOT))

        assert documented == on_disk, _out_of_sync_message(
            'services/README.md Quick Reference', documented, 'services/*/compose.yml*', on_disk,
        )

    def test_disabled_marker_matches_disabled_compose_files(self) -> None:
        """
        A row is marked (**disabled**) exactly when its compose file is compose.yml.disabled
        """
        rows    = _services_readme_rows(REPO_ROOT)
        enabled = _compose_containers(REPO_ROOT)

        mismatches: list[str] = []
        for name, rest in rows.items():
            marked_disabled = '(**disabled**)' in rest
            if name in enabled and marked_disabled == enabled[name]:
                mismatches.append(f'{name}: marked disabled={marked_disabled}, compose enabled={enabled[name]}')

        assert not mismatches, 'services/README.md disabled markers are out of sync:\n  ' + '\n  '.join(mismatches)

    def test_container_table_is_not_empty(self) -> None:
        """
        The container-table parser finds rows (guards against a silently broken regex)
        """
        assert _services_readme_rows(REPO_ROOT), 'parsed zero containers from services/README.md'
```

- [ ] **Step 2: Run the guard; prove it can fail**

Run: `scripts/hooks/uv-public.sh run pytest tests/unit/test_docs_consistency.py -q -p no:cacheprovider -k Services`
Expected: 3 passed (the table is already accurate). Mutation check: temporarily rename the `plex` row in
`services/README.md` to `plexx`, confirm `test_container_table_matches_compose_files` fails naming `plex`/`plexx`, then
revert that edit.

- [ ] **Step 3: Correct the README** (verify each against the cited source before writing)

  1. Add the up-breadcrumb `[Project Root](../README.md) > **Services**` and the mdformat-toc block (the file will
     exceed 100 lines with 3+ sections).
  2. Intro (lines 3-4 "self-contained"): Glance and Plex also read the shared `~/docker/.env`; say so.
  3. Intro/`Deploying` command line: `deploy.sh` runs
     `docker compose --project-directory ~/docker -f compose.base.yml -f <service>/compose.yml up -d <service>` with
     `COMPOSE_IGNORE_ORPHANS=true`; the directory name must equal the compose service key and match
     `^[a-z0-9][a-z0-9_-]*$` (`scripts/nas/deploy-services.sh` rejects other names and any without a `compose.yml`).
  4. Disabling a service: add that rsync never deletes, so an already-synced `~/docker/<svc>/compose.yml` and its
     running container survive; the NAS copy must be removed by hand (cross-link `vms/haos/README.md`'s cutover steps
     for `homeassistant`; read them first).
  5. `glance` section: `env_file: .env` resolves against `--project-directory ~/docker`, i.e. the shared `~/docker/.env`
     rendered by the `docker` role (it holds only `ADVERTISE_IP`); it does not read `glance/.env`.
  6. `plex` section: `ADVERTISE_IP` is a bare variable name in `plex/compose.yml`; its value comes from the shared
     `~/docker/.env` (`https://<host>.<tailnet>:32443`); port 32443 is hard-coded in `roles/docker/templates/env.j2` and
     `services/caddy/compose.yml`.
  7. PiHole: in the Tailscale table (line ~51) and the admin-URL sentence (lines ~36-37) mark the `/pihole` route and
     `:8053/admin` as unavailable while PiHole is disabled (`roles/tailscale/templates/Caddyfile.j2` still emits the
     `/pihole` block unconditionally).
  8. `prowlarr`/`radarr`/`sonarr`/`transmission` paragraph (line ~98): "All share `/storage/media`" is wrong for
     `prowlarr` (config directory only) and `flaresolverr` (nothing); fix from the compose volumes.
  9. `autoplex`: built by the `docker` role (clone to `~/docker/.build/autoplex`, branch `master`, tagged
     `danielmmetz/autoplex:latest`); its compose entry has no `build:`, so the `docker` role must have run first.
  10. Secrets: with Task 2, `env.j2` renders only for services that have a `compose.yml`, so a disabled service needs no
      vault variable and keeps no fresh `.env`; an existing `~/docker/pihole/.env` is left in place; CI never renders
      secrets (`*.j2` is not rsynced).
  11. CI: list the repository secrets the workflow reads (`TAILSCALE_OAUTH_CLIENT_ID`, `TAILSCALE_OAUTH_CLIENT_SECRET`,
      `NAS_TAILSCALE_HOST`, `NAS_USER`, `NAS_SSH_PRIVATE_KEY`; confirm against `deploy.yml`). Rewrite the sentence
      "whose public half sits in `~/.ssh/authorized_keys` with the `restrict` option" as an instruction in the rotation
      recipe (add the new key with `restrict`) and say which machine runs each line of the recipe.
  12. Port notes: mark `8123` (Home Assistant) and `8191` (Flaresolverr) as image defaults, since the compose files do
      not declare them.
  13. Link text: the `scripts/nas/deploy-services.sh` link points at `scripts/nas/README.md`; label it accordingly. The
      `[vms/haos/setup.sh](../vms/haos/)` link should target `../vms/haos/setup.sh`.
  14. Add `## Data flow`: Sonarr/Radarr search through Prowlarr (Flaresolverr clears Cloudflare challenges) and hand
      downloads to Transmission; Autoplex (`--mode copy`) copies `/storage/media/downloads/complete/{tv,movies}` into
      the `tv/` and `movies/` trees; Plex and Jellyfin read those. Verify each mount in the compose files; read the old
      README's "Data Flow" section for the original wording.
  15. Add `## Storage layout`: the `/storage/media` tree as the compose volumes actually use it
      (`config/{plex,jellyfin, transmission,sonarr,radarr,prowlarr}`, `downloads/complete/{tv,movies}`, `watch`, `tv`,
      `movies`, `music`). Do **not** list `incomplete/` (no compose file mounts it).
  16. Add `## Operations`: back up `/storage/media/config/` before media (metadata is regenerable), stop
      `sonarr`/`radarr`/`prowlarr` before archiving their databases; `deploy.sh` never pulls, so refresh a `:latest`
      image with `docker compose ... pull <svc>` first (the `services` role counts `Pulled` as a change); the `storage`
      pool is striped without redundancy (`vms/haos/README.md`, read the exact wording first). Do **not** carry over the
      old README's log-rotation advice (the NAS configuration is unverified).

- [ ] **Step 4: Verify and commit**

Run: `scripts/hooks/uv-public.sh run pytest tests/unit/test_docs_consistency.py -q -p no:cacheprovider`
Expected: pass. Run the link checker (Task 17 Step 3) on `services/README.md`.

```bash
git add services/README.md tests/unit/test_docs_consistency.py
git commit -m "docs(services): correct the stack README, add data flow, storage, and operations, guard the table"
```

---

## Task 11: Role READMEs for `services`, `tailscale`, `samba`

**Files:**
- Modify: `roles/services/README.md`, `roles/tailscale/README.md`, `roles/samba/README.md`

**Sources:** each role's `tasks/`, `defaults/`, `templates/`, `handlers/`; `playbooks/nas_bootstrap.yml`;
`roles/docker/templates/env.j2`; `services/caddy/compose.yml`.

- [ ] **Step 1: `roles/services/README.md`** (re-verify against `roles/services/tasks/main.yml` after Task 2)

Add the discovery task ("Find per-service secret templates": controller-side `find`, `depth: 2`, always runs even in
check mode, tag `secrets`) to the task table; state that directories and `.env` files are created only for services that
have a `compose.yml`; "Deploy all services" runs async (3600 s, polled every 15 s) and is skipped under `--check`; the
include carries tags `services` and `secrets` (apply tag `services`; `secrets` reaches exactly the discovery, directory,
and render tasks). Remove any statement that `pihole_web_password` is always required.

- [ ] **Step 2: `roles/tailscale/README.md`** (add the breadcrumb
  `[Project Root](../../README.md) > [Roles](../README.md) > **tailscale**`)

  - Line ~12 "Deploys Caddy reverse proxy": the role renders `/etc/caddy/Caddyfile` and issues certificates; the Caddy
    container is defined by `services/caddy/compose.yml` and deployed by the `services` role / `nas-deploy`.
  - Lines ~68-69: remove the manual "set `ADVERTISE_IP` in the Docker `.env`" step (the `docker` role renders it into
    `~/docker/.env` from `tailscale_tailnet_name`) and the `docker compose up -d` step (use
    `python3 run.py nas-deploy caddy` or `~/docker/deploy.sh caddy`).
  - Lines ~44 and ~59: note that the `pihole` route in `tailscale_services` is inert while PiHole is disabled.
  - Add: the weekly renewal unit reloads Caddy with `docker exec caddy caddy reload` (confirm in
    `templates/tailscale-cert-renewal.service.j2`).

- [ ] **Step 3: `roles/samba/README.md`** (grow the three-line stub; add the breadcrumb)

Document, from `tasks/main.yml`, `defaults/main.yml`, and `templates/smb.conf.j2` (read them): install `samba` and
`smbclient`; "Register Samba version" (tag `always`); render `smb.conf` to `samba_configuration` with a `testparm -s`
validate and a restart handler (tag `configfile`); start and enable the services in `samba_services`; create users from
`samba_users` (`no_log`, tag `samba`); the shares defined in the template; the variables table; and the known gap that
share directories are not created by the role (there is a `TODO` in `tasks/main.yml`).

- [ ] **Step 4: Verify and commit**

Run the link checker on the three files; run
`scripts/hooks/uv-public.sh run pytest tests/unit/test_docs_consistency.py -q -p no:cacheprovider`.

```bash
git add roles/services/README.md roles/tailscale/README.md roles/samba/README.md
git commit -m "docs(roles): fill the services and samba READMEs and fix stale tailscale steps"
```

---

## Task 12: `playbooks/README.md` and `roles/README.md`, with drift guard 2

**Files:**
- Modify: `playbooks/README.md`, `roles/README.md`, `tests/unit/test_docs_consistency.py`

- [ ] **Step 1: Write guard 2 first**

Append to `tests/unit/test_docs_consistency.py`:

```python
def _playbook_role_order(repo: Path) -> list[str]:
    """
    Return the roles ``playbooks/nas_bootstrap.yml`` includes, in play order

    :param repo: repository root
    :return: role names without the ``roles/`` prefix
    """
    key  = 'ansible.builtin.include_role'
    play = yaml.safe_load((repo / 'playbooks' / 'nas_bootstrap.yml').read_text(encoding='utf-8'))[0]
    return [task[key]['name'].removeprefix('roles/') for task in play['tasks'] if key in task]


def _playbooks_readme_role_order(repo: Path) -> list[str]:
    """
    Return the role names bolded in the numbered execution-order list of ``playbooks/README.md``

    :param repo: repository root
    :return: role names in document order (steps whose bold text is not a role directory, such as the apt refresh, are
             ignored)
    """
    text  = (repo / 'playbooks' / 'README.md').read_text(encoding='utf-8')
    names = re.findall(r'^\d+\. \*\*([a-z0-9_-]+)\*\*', text, re.MULTILINE)
    return [name for name in names if name in _role_dirs(repo)]


def _roles_readme_role_order(repo: Path) -> list[str]:
    """
    Return the role names linked in the first cell of the ``roles/README.md`` table, in table order
    """
    text = (repo / 'roles' / 'README.md').read_text(encoding='utf-8')
    return re.findall(r'^\|\s*\[`([a-z0-9_-]+)`\]\(', text, re.MULTILINE)


class TestRoleOrderDocs:
    """
    Guardrails tying the documented role order to the playbook
    """
    def test_playbooks_readme_follows_the_playbook(self) -> None:
        """
        The execution-order list in playbooks/README.md names the roles in the playbook's order
        """
        assert _playbooks_readme_role_order(REPO_ROOT) == _playbook_role_order(REPO_ROOT)

    def test_roles_readme_table_follows_the_playbook(self) -> None:
        """
        The roles/README.md table lists the roles in the playbook's order
        """
        assert _roles_readme_role_order(REPO_ROOT) == _playbook_role_order(REPO_ROOT)

    def test_order_parsers_are_not_empty(self) -> None:
        """
        The order parsers find roles (guards against silently broken regexes)
        """
        assert _playbook_role_order(REPO_ROOT)
        assert _playbooks_readme_role_order(REPO_ROOT)
        assert _roles_readme_role_order(REPO_ROOT)
```

Run: `scripts/hooks/uv-public.sh run pytest tests/unit/test_docs_consistency.py -q -p no:cacheprovider -k RoleOrder`
Expected: pass (order is already right). Mutation check: swap two rows in `roles/README.md`, confirm the failure,
revert.

- [ ] **Step 2: `playbooks/README.md`** (verify against `playbooks/nas_bootstrap.yml` as rewritten in Task 1,
  `roles/*/tasks`, `roles/tailscale/tasks/main.yml:2-8`)

  - Execution order: add the first step "Set `ansible_become_pass` (tag `always`)" as an unnumbered or `0.` line that
    the guard's regex ignores (bold text must not be a role name); the role steps keep their numbers and bold role
    names.
  - Per-role tag lists: `debian` → `debian`; `zfs` → `zfs`; `samba` → `samba`, `configfile`; `docker` → `docker`,
    `configfile` (no `homeassistant`); `tailscale` → `tailscale`; `dotfiles` → `dotfiles`; `haos` → `haos`; `services` →
    `services`, `secrets`.
  - docker wording: Docker Engine and compose plugin, docker-group membership, the `~/docker` skeleton and shared
    `.env`, the autoplex image build, and `deploy.sh`; the stack itself is the `services` step.
  - "Variables required": `admin_password`; `tailscale_auth_key` (hard assert in the `tailscale` role);
    `tailscale_tailnet_name` (HTTPS and the docker `.env`); plus whatever an enabled service's `env.j2` references (none
    today; PiHole's `pihole_web_password` returns when it is re-enabled).
  - Tags section: rewrite. Explain that a tag on an `include_role` selects only the include and the role-name tag (via
    `apply`) reaches the role's tasks; `configfile` therefore reaches only the docker `.env` render, the docker
    `deploy.sh` copy, and the samba `smb.conf` (plus `always` tasks), and on a fresh host fails at the `.env` render
    until `--tags docker` has created `~/docker`; use `--tags dotfiles` / `haos` for those roles. Remove the
    `homeassistant` row and the claim that `--tags configfile` runs the stow engine or `setup.sh`. Fix the `docker` row
    to "Docker Engine and image build" and the `configfile` row to "Tasks tagged `configfile` (docker `.env` and
    `deploy.sh`, samba `smb.conf`)".
  - Direct execution: say it skips the SSH preflight and collection install and needs `ansible-playbook` from the
    project environment (prefix with `scripts/hooks/uv-public.sh run`). Fix the syntax-check example. Verified during
    planning: `scripts/hooks/uv-public.sh run ansible-playbook --syntax-check -i localhost, playbooks/nas_bootstrap.yml`
    exits 0 when `vault_password.txt` exists (the normal state of a working clone) or when `ANSIBLE_VAULT_PASSWORD_FILE`
    names any existing file, and errors "vault password file ... was not found" otherwise. Document that requirement
    (the `-i localhost,` inventory matches no `nas` host, so the check only parses).
  - Last line (Troubleshooting): point stack problems at [`services/README.md`](../services/README.md) and
    [`roles/services/README.md`](../roles/services/README.md), not the docker README.

- [ ] **Step 3: `roles/README.md`**

  - Table rows: `debian` → the wording in `roles/debian/README.md` (read lines 1-8); `docker` → "Docker Engine,
    `~/docker` skeleton, autoplex image, `deploy.sh`"; `tailscale` → "Tailscale install and configuration, HTTPS
    certificates, and the Caddyfile Caddy reads". Keep the row order = playbook order (guard 2).
  - External dependencies: `ansible-galaxy collection install -r roles/requirements.yml` (the file lists collections
    only; `run.py nas-provision` runs it through `scripts/hooks/uv-public.sh`).
  - Running roles: remove the "Every role tagged configfile" example; prefer `python3 run.py nas-provision --tags ...`.
  - Adding a role: the include snippet drops `configfile` (note: add a tag to the include only if a task inside the role
    carries it, because a tag on an include selects only the include); add the two enforced steps: update
    `EXPECTED_ORDER` in `tests/unit/test_nas_playbook.py` and add the row to the table above (enforced by
    `tests/unit/test_docs_consistency.py`); delete the clause "a `defaults/` variable for file modes" (no role does
    that).

- [ ] **Step 4: Verify and commit**

Run: `scripts/hooks/uv-public.sh run pytest tests/unit/test_docs_consistency.py -q -p no:cacheprovider`; run the link
checker on both files.

```bash
git add playbooks/README.md roles/README.md tests/unit/test_docs_consistency.py
git commit -m "docs(ansible): describe tag selection truthfully, list required variables, guard role order"
```

---

## Task 13: `.ctx/` fixes and guard 2 extension

`.ctx/` is excluded from mdformat: hand-wrap at 120 columns.

**Files:**
- Modify: `.ctx/ARCHITECTURE.md`, `.ctx/BUILD.md`, `.ctx/CONVENTIONS.md`, `tests/unit/test_docs_consistency.py`

- [ ] **Step 1: Extend guard 2 to ARCHITECTURE (test first)**

Append to `TestRoleOrderDocs` in `tests/unit/test_docs_consistency.py`:

```python
    def test_architecture_role_list_follows_the_playbook(self) -> None:
        """
        The role bullets in .ctx/ARCHITECTURE.md name the roles in the playbook's order
        """
        text    = (REPO_ROOT / '.ctx' / 'ARCHITECTURE.md').read_text(encoding='utf-8')
        section = text.split('## Role System (NAS)', 1)[1].split('\n## ', 1)[0]
        roles   = re.findall(r'^- `([a-z0-9_-]+)`:', section, re.MULTILINE)

        assert roles == _playbook_role_order(REPO_ROOT)
```

Run it; expected pass already. Mutation check as before (swap two bullets, confirm failure, revert).

- [ ] **Step 2: `.ctx/ARCHITECTURE.md`** (verify each against the code)

  - Intro: drop "Directory layout" or link `README.md` (the project tree lives there).
  - `nas-provision` flow: add that a failed collection install only warns (the playbook still runs) and that preflight
    resolves `ansible_host`/`ansible_user` through `ansible-inventory` and refuses templated values (`run.py`
    `resolve_nas_target`).
  - Stage list: mark `58-defaults-backup`, `60-macos`, `72-vscode`, `96-iterm2` "(macOS only)" (each calls
    `require_os darwin`).
  - `doctor`: add the git-version check (`>= 2.36`; confirm the constant in `run.py`).
  - Inventory: `update-inventory --force` discards uncommitted local changes in the clone (`git reset --hard HEAD`)
    before pulling; a non-git `inventory/` is re-cloned automatically. Fix the "Recovery" line accordingly (remove
    `inventory/` and re-run for a corrupted clone).
  - Role System: use `roles/debian/README.md`'s wording for `debian`; `docker` → "Docker Engine and compose plugin,
    docker-group membership, the `~/docker` skeleton and shared `.env`, the autoplex image build, `deploy.sh`";
    `tailscale` → "...HTTPS certificates and the Caddyfile Caddy reads". Keep bullet order = playbook order.
  - `run.py` categories: Inventory also has `inventory-status`, `vault-decrypt`, `vault-encrypt`; Codebase also has
    `install-hooks`, `uninstall-hooks` (confirm each `@command(group=...)`). Retry logic applies to the
    `update-inventory` git pull/clone only. `DOTFILES_RUN_DEBUG` enables debug only when `true` (case-insensitive); a
    global `-d/--debug` also exists.
  - Docker Stack: mark PiHole "(disabled)"; state the `compose.yml.disabled` convention (`pihole`, `homeassistant`).
  - Key Configuration Files: add `.ansible-lint-ignore`, `pyproject.toml`, `.github/workflows/{lint,deploy,leaks}.yml`.

- [ ] **Step 3: `.ctx/BUILD.md`**

  - Add the "Running run.py" note at the top of "Python Script Commands" (bare `python3` is fine for stdlib-only
    commands; `list-hosts` needs PyYAML, so use `scripts/hooks/uv-public.sh run python run.py list-hosts`; the NAS
    commands already shell out through uv).
  - Syntax-check example (line ~34): replace with the working form verified in Task 12 (vault password file env var and
    the uv wrapper).
  - Make section: `nas-deploy` is script-only (no target) and make targets take no arguments, so options such as
    `--tags` need `python3 run.py`; fix "All python3 run.py commands are available as make targets".
  - Command list: add `inventory-status`, `vault-decrypt`, `vault-encrypt`, `uninstall-hooks`, and the global
    `-d/--debug`.
  - Git hooks: priority bands "formatters (30-35)"; Checks add `check-vcs-permalinks`, `check-json5`, `check-pkl`, and
    the leak guard (`check-leaks`, `check-leaks-msg` at commit-msg, `check-leaks-push-files` and
    `check-leaks-push-history` at pre-push); Formatters add `keep-sorted`, `format-pkl`, `sort-json-array`; `codespell`
    is a fixer; note that `default_install_hook_types` installs six hook types. Confirm each hook id and priority in
    `.pre-commit-config.yaml`.
  - Add a short "CI" section: the jobs in `.github/workflows/lint.yml` (confirm names), `deploy.yml`, `leaks.yml`.

- [ ] **Step 4: `.ctx/CONVENTIONS.md`** (read it first; keep it short)

Add: adding a role also needs a role `README.md`, a row in `roles/README.md`, and an `EXPECTED_ORDER` update (link to
[`roles/README.md#adding-a-role`](../roles/README.md#adding-a-role)); macOS-only Brewfile entries go inside `if OS.mac?`
because the NAS applies the base Brewfile too; a macOS-only or Linux-only stow package needs a `.dotfiles-os` marker
(see `stow/README.md`); a short "Adding a Compose service" pattern: `services/<name>/compose.yml` (service key equals
the directory name), optional `env.j2` + `env_file: <name>/.env`, deploy with `python3 run.py nas-deploy <name>`.

- [ ] **Step 5: Verify and commit**

Run: `scripts/hooks/uv-public.sh run pytest tests/unit/test_docs_consistency.py -q -p no:cacheprovider`; link-check the
three files; confirm no line in `.ctx/*.md` exceeds 120 columns outside code blocks and tables.

```bash
git add .ctx tests/unit/test_docs_consistency.py
git commit -m "docs(ctx): correct architecture and build references, add conventions, guard the role list"
```

---

## Task 14: Root `README.md`

**Files:**
- Modify: `README.md`

Read the whole file first (about 470 lines). The audit found these discrepancies; verify each, then fix:

  1. Lines ~3-4, 79: "Two independent mechanisms": reword to one stow engine plus two entry points. The NAS `$HOME` is
     handed to the engine by the `dotfiles` role (`profiles/nas` overlay); add the Linux/NAS note to the engine section
     (`bootstrap/README.md` has the contract).
  2. Line ~75: delete the "Point router DNS at NAS for PiHole" step (PiHole is disabled).
  3. Lines ~71-76: add prerequisites to NAS Bootstrapping: `uv` on the controlling machine (the Brewfile installs it on
     a Mac), SSH reachability, a literal `ansible_host`/`ansible_user` in the inventory, and `br0` present on the NAS
     (the `haos` role fails the play without it; `vms/haos/README.md` documents the hand-run `bridge.sh`).
  4. Lines ~98, 316: media stack also includes Jellyfin, Caddy, Glance; lines ~99, 317 replace "PiHole DNS/ad-blocking"
     with Tailscale + Caddy HTTPS and note PiHole is disabled.
  5. Line ~101 "Base system: Debian packages, git, ssh, zsh": the `git`/`ssh`/`zsh` roles are gone; say "Debian packages
     and the Linuxbrew prefix (`debian` role); `$HOME` via the stow engine (`dotfiles` role)". Add `dotfiles` and
     `services` to the component list.
  6. Lines ~105-118 Core Components: add rows for `vms/` and `scripts/nas`; the `scripts/` row also links
     `scripts/nas/README.md`.
  7. Lines ~122-129 Documentation list: add `services/README.md`, `roles/{services,dotfiles,haos}/README.md`,
     `vms/haos/README.md`, `scripts/nas/README.md`; the RUN_PY bullet mentions NAS provision/deploy; the Docker role
     bullet reads "Docker Engine, `~/docker` skeleton, autoplex image, `deploy.sh`".
  8. Lines ~163-164, 385-390: `update-inventory --force` discards uncommitted local changes then pulls (it does not
     re-clone); for a corrupted clone remove `inventory/` and re-run.
  9. Line ~399: retarget `docs/RUN_PY_REFERENCE.md#inventory-management` to `#inventory-update-failures`.
  10. Lines ~176-191: add the missing commands (`inventory-status`, `vault-decrypt`, `vault-encrypt`, `install-hooks`,
      `uninstall-hooks`) or point to `docs/RUN_PY_REFERENCE.md`; add the "Running run.py" note (bare `python3` for
      stdlib-only commands, `scripts/hooks/uv-public.sh run python run.py list-hosts` where PyYAML is needed).
  11. Lines ~217-218: "Update only Docker stack: `nas-provision --tags docker`" → `--tags services` (or
      `nas-deploy all`); `--tags docker` now means Docker Engine and the image build.
  12. Line ~224: the direct `ansible-playbook` invocation skips the preflight and collection install; say so.
  13. Line ~232: make wraps argument-less runs of most commands; `nas-deploy` has no target.
  14. Lines ~259-264 project tree: delete `roles/git`, `roles/ssh`, `roles/zsh`; list the eight real roles. Lines
      ~241-295: add `vms/` (`haos/{README.md,bridge.sh,setup.sh}`), `.github/workflows/`, `scripts/nas/`,
      `archive/homeassistant/`, `docs/MODEL_ROUTER.md`, `docs/licenses/`, `ansible.cfg`, `pyproject.toml`, `uv.lock`.
      Verify with `ls`.
  15. Line ~308: "Homebrew installer checksum verification in the macOS bootstrap" → in the bootstrap engine (macOS and
      the NAS).
  16. Lines ~65-66: the stage prose omits `58-defaults-backup` (preference backup).
  17. Lines ~133-137 and ~435-441: add `ansible.cfg`, `pyproject.toml`, `.ansible-lint-ignore`, `.gitleaks.toml`,
      `.secrets.baseline` to the configuration list and the missing hooks (shellcheck, shfmt, mdformat, taplo,
      ansible-lint, detect-secrets, the leak guard, codespell) to the pre-commit summary.
  18. Add a `uv` prerequisite line under NAS Bootstrapping: "Prerequisite: [`uv`](https://docs.astral.sh/uv/) on the
      controlling machine. `run.py` runs Ansible through `scripts/hooks/uv-public.sh`, and the macOS Brewfile installs
      it." (Task 7's script guard points users here.)

- [ ] **Step 1: Edit.** Keep the up-to-date sections untouched (Quick Start for the Mac, Homebrew Checksum Mismatch,
  Layered Dev Environment, Adding a Dotfile/Application/Service, Testing, Environment Variables).
- [ ] **Step 2: Verify.** Link-check `README.md`; confirm the `#homebrew-checksum-mismatch` anchor still resolves (it is
  referenced from `playbooks/README.md` and `bootstrap/50-brew.sh`); run
  `scripts/hooks/uv-public.sh run pytest tests/unit/test_docs_consistency.py -q -p no:cacheprovider`.
- [ ] **Step 3: Commit.**

```bash
git add README.md
git commit -m "docs(readme): describe the NAS as the stow engine plus Ansible, fix commands, tree, and links"
```

---

## Task 15: Remaining doc corrections and the `run.py` reference guard (guard 3)

**Files:**
- Modify: `CLAUDE.md`, `.claude/rules/readme-guidelines.md`, `vms/README.md`, `docs/RUN_PY_REFERENCE.md`,
  `scripts/nas/README.md`, `roles/docker/files/deploy.sh` (comment only), `tests/unit/test_docs_consistency.py`

- [ ] **Step 1: Write guard 3 first**

Add `import importlib` and `import sys` (stdlib group, alphabetical) to `tests/unit/test_docs_consistency.py`, then
append:

```python
def _registered_commands(repo: Path) -> set[str]:
    """
    Return the command names registered in ``run.py``

    :param repo: repository root
    :return: names in ``run.REGISTERED_COMMANDS``
    """
    sys.path.insert(0, str(repo))
    try:
        module = importlib.import_module('run')
    finally:
        sys.path.remove(str(repo))
    return set(module.REGISTERED_COMMANDS)


class TestRunPyReference:
    """
    Guardrails tying docs/RUN_PY_REFERENCE.md to the commands run.py registers
    """
    def test_every_registered_command_is_documented(self) -> None:
        """
        Every command registered in run.py appears backticked in the reference
        """
        text    = (REPO_ROOT / 'docs' / 'RUN_PY_REFERENCE.md').read_text(encoding='utf-8')
        missing = sorted(name for name in _registered_commands(REPO_ROOT) if f'`{name}`' not in text)

        assert not missing, f'docs/RUN_PY_REFERENCE.md does not document: {missing}'

    def test_registry_is_not_empty(self) -> None:
        """
        The registry lookup finds commands (guards against a broken import)
        """
        assert _registered_commands(REPO_ROOT)
```

Run it. Expected FAIL listing at least `inventory-status`, `vault-decrypt`, `vault-encrypt`, `install-hooks`,
`uninstall-hooks`. Record the exact list; Step 4 must resolve all of it.

- [ ] **Step 2: `CLAUDE.md`**

  - Lines ~25-26: the HAOS VM is provisioned by the `haos` role, which runs `vms/haos/setup.sh`; only `bridge.sh` is
    hand-run (`vms/haos/README.md` has the runbook).
  - Lines ~3-4, 18: note that `bootstrap/bootstrap.sh` also runs on the NAS (the `dotfiles` role applies the
    `profiles/nas` overlay).
  - Entry points: add one sentence on CI deploys (`.github/workflows/deploy.yml` calls `scripts/nas/deploy-services.sh`
    on pushes touching `services/`).
  - Everything else in `CLAUDE.md` was verified accurate; leave it.
  - Also in `.claude/rules/readme-guidelines.md`: the repo-specifics bullet says `mdformat` runs at priority 30; the
    hook's real priority is 35 (confirm at `.pre-commit-config.yaml`, the `mdformat` hook). Fix both files.

- [ ] **Step 3: `vms/README.md`, `scripts/nas/README.md`, `deploy.sh`**

  - `vms/README.md` (lines ~7-8): `setup.sh` is run by the `haos` role (it is part of the Ansible bootstrap); only
    `bridge.sh` is hand-run. Read `roles/haos/README.md` and `vms/haos/README.md` first.
  - `scripts/nas/README.md`: add the service-name rule (`^[a-z0-9][a-z0-9_-]*$` plus a required
    `services/<svc>/compose.yml`), the sync scope (`all` syncs the whole tree; one service syncs `compose.base.yml` plus
    its directory), the `--` / leading-dash / key-quoting behavior from Task 4, and CI usage.
  - `roles/docker/files/deploy.sh` line 5: the header comment names only GitHub Actions; it is also run by
    `scripts/nas/deploy-services.sh` (laptop and CI) and by the `services` role. Edit the comment only, not the code.

- [ ] **Step 4: `docs/RUN_PY_REFERENCE.md`** (resolve the full list Step 1 recorded; verify against `run.py`)

  - Add sections for `inventory-status`, `vault-decrypt`, `vault-encrypt` (Inventory), `install-hooks`,
    `uninstall-hooks` (Codebase), modeled on the neighboring commands (read each command's docstring and arguments in
    `run.py` first).
  - `update-inventory`: document `-f/--force` (discards uncommitted local changes via `git reset --hard HEAD`, then
    pulls).
  - `clean`: add the `virtual environments: venv, .venv` pattern group and its output line.
  - `nas-deploy`: single-service syncs `compose.base.yml` plus `services/<svc>/`; `all` syncs the whole tree; a service
    without `services/<svc>/compose.yml` is rejected.
  - Constants table: say it is an excerpt, or add `VAULT_PASSWORD`, `STOW_SCRIPT`, `BOOTSTRAP_SCRIPT`, `RENDER_SCRIPT`,
    `UV_PUBLIC`, `NAS_PLAYBOOK`, `NAS_REQUIREMENTS`, `NAS_DEPLOY_SCRIPT`, `NAS_INVENTORY_HOST`.
  - Hook list (line ~141): add `ansible-lint` and the leak guard.
  - Delete the "Future Enhancements" section (every item exists: `bootstrap`, `nas-provision --tags`, `vault-*`, the SSH
    preflight).
  - Leave the `list-hosts` sample output and the `prek cache clean` / `prek prepare-hooks` troubleshooting lines alone
    unless you can verify them; report them as unverified instead of changing them.

- [ ] **Step 5: Verify and commit**

Run: `scripts/hooks/uv-public.sh run pytest tests/unit/test_docs_consistency.py -q -p no:cacheprovider`
Expected: pass. Link-check every changed file. `git diff --stat main -- run.py` prints nothing.

```bash
git add CLAUDE.md .claude/rules/readme-guidelines.md vms/README.md docs/RUN_PY_REFERENCE.md scripts/nas/README.md roles/docker/files/deploy.sh tests/unit/test_docs_consistency.py
git commit -m "docs: correct CLAUDE.md, the VM and script READMEs, and the run.py reference; guard its command list"
```

---

## Task 16: Record the lessons

**Files:**
- Modify: `CLAUDE-LESSONS.md` (append after the last lesson, same `### title` + Context/Mistake/Rule shape)

- [ ] **Step 1: Append four lessons**

```markdown
### Hand-maintained inventories in docs drift: guard each with a test

- **Context**: READMEs and `.ctx/` files list stages, packages, roles, containers, and `run.py` commands.
  `tests/unit/test_docs_consistency.py` already cites this lesson in its docstring, but it was never written down.
- **Mistake**: After NAS sub-projects 1-3 the root README still listed retired roles, five registered commands were
  missing from the reference, and `--tags docker` was documented as the way to update the stack.
- **Rule**: When a doc enumerates something the code defines, add a parse-the-table test beside it (and a "parsed zero
  rows" companion). Add the guard in the same change that adds the inventory.

### String-matching Ansible YAML is not verification: run the role

- **Context**: NAS sub-project 3 added per-service secret rendering. Unit tests that read the role's YAML passed.
- **Mistake**: Two real bugs shipped past them: `lookup('fileglob', '.../*/env.j2')` matched nothing (so no secret was
  rendered) and a template used a variable another role defines.
- **Rule**: Exercise role tasks against localhost with `ansible-playbook` and assert on the result
  (`tests/unit/test_services_role.py`). Structural tests only pin wiring, never behavior.

### `--check --diff` of a template prints the old file

- **Context**: A secrets template whose target already holds secrets, run with `--check --diff`.
- **Mistake**: Check mode diffs the current file against the new one, so it prints the existing secret values.
- **Rule**: Set `diff: false` on any task whose target holds secrets, and `no_log` where values could print.

### A tag on `include_role` selects only the include

- **Context**: Every role include in the NAS play carried `configfile`, and `playbooks/README.md` said
  `--tags configfile` ran the whole stow engine.
- **Mistake**: Tasks inside an included role see only its `apply:` tags plus their own, so a tag nothing inside the role
  carries selects the include and nothing else. Only three tasks carried `configfile`.
- **Rule**: Every tag on an include must be the apply tag or be carried by a task in the role
  (`tests/unit/test_nas_playbook.py::TestPlaybookTags`). Prove tag semantics with a real run before documenting them.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE-LESSONS.md
git commit -m "docs(lessons): record doc-drift guards, run-the-role, check-mode diffs, and include tags"
```

---

## Task 17: Full verification and the owner's rollout runbook

**Files:**
- Create: `~/nas-sp4-rollout.md` (outside the repo; not committed)
- Create (scratch): `$TMPDIR/check_links.py`

- [ ] **Step 1: Full test suite**

Run: `scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider`
Expected: no failures; skips limited to the three Linux Brewfile tests and the real-rsync test. Record the final count
(baseline was `998 passed, 3 skipped`).

- [ ] **Step 2: Lint everything**

Run: `prek run --all-files` — expected all Passed (if a hook rewrites a file, review the diff, re-stage, and re-run).
Run: `scripts/hooks/uv-public.sh run ruff check` — expected `All checks passed`. Never `ruff format`.

- [ ] **Step 3: Link and anchor check over every changed Markdown file**

Write `$TMPDIR/check_links.py`:

```python
"""Check relative Markdown links and #anchors in the given files (stdlib only)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

LINK    = re.compile(r'(?<!\!)\[[^\]]*\]\(([^)\s]+)\)')
HEADING = re.compile(r'^#{1,6}\s+(.*?)\s*$', re.MULTILINE)


def slug(heading: str) -> str:
    """Approximate GitHub's heading slug."""
    text = re.sub(r'`', '', heading).lower()
    return re.sub(r'[^\w\- ]', '', text).replace(' ', '-')


def anchors(path: Path) -> set[str]:
    """Return the heading slugs of a Markdown file."""
    return {slug(h) for h in HEADING.findall(path.read_text(encoding='utf-8'))}


bad = 0
for name in sys.argv[1:]:
    path = Path(name).resolve()
    for target in LINK.findall(path.read_text(encoding='utf-8')):
        if re.match(r'^(https?:|mailto:)', target):
            continue
        file_part, _, anchor = target.partition('#')
        dest = (path.parent / file_part).resolve() if file_part else path
        if not dest.exists():
            print(f'{name}: missing target {target}')
            bad += 1
        elif anchor and dest.suffix == '.md' and anchor not in anchors(dest):
            print(f'{name}: missing anchor {target}')
            bad += 1
sys.exit(1 if bad else 0)
```

Run from the worktree root:
`scripts/hooks/uv-public.sh run python -I $TMPDIR/check_links.py $(git diff --name-only main...HEAD -- '*.md' ':!docs/plans')`
Expected: no output, exit 0. Treat an anchor miss as real only after reading the target's heading (the slug is an
approximation; headings with punctuation may need a manual check).

- [ ] **Step 4: Write `~/nas-sp4-rollout.md`** (owner runs every step in one terminal on the work Mac; saves output
  under `$TMPDIR`; tells Claude each filename)

Contents (the file text is everything between the four-backtick fences):

````markdown
# NAS sub-project 4: live acceptance

Run every command in ONE terminal on the work Mac. After each stage, save the output under `$TMPDIR` and tell Claude the
filename; wait for the review before the next stage. Nothing printed should contain a password; if it does, stop.

## Stage 0: baseline on main (the validation still owed from sub-project 3)

```bash
cd ~/dotfiles-personal RUN=(scripts/hooks/uv-public.sh run python run.py) "${RUN[@]}" nas-provision 2>&1 | tee
"$TMPDIR/nas4-0-run1.txt" "${RUN[@]}" nas-provision 2>&1 | tee "$TMPDIR/nas4-0-run2.txt"
```

Expect: run 1 may show `changed` (first run on main moves the NAS clone to main and runs the HAOS `setup.sh` for
usbutils; sync may report changed because CI re-stamps mtimes); run 2 must end `changed=0`. If run 2 is not `changed=0`,
run a third time and send all three files. **Send:** `nas4-0-run1.txt`, `nas4-0-run2.txt`.

## Setup for the branch (once)

```bash
cd ~/dotfiles-personal/.claude/worktrees/nas-docs-truth-up ln -s ~/dotfiles-personal/inventory inventory ln -s
~/dotfiles-personal/vault_password.txt vault_password.txt echo inventory >> "$(git rev-parse --git-path info/exclude)"
RUN=(scripts/hooks/uv-public.sh run python run.py)
```

## Stage 1: check mode from the branch

```bash
"${RUN[@]}" nas-provision --check --diff 2>&1 | tee "$TMPDIR/nas4-1-check.txt"
```

Expect: no failures. The changed code paths are the tag cleanup, the secrets discovery filter, and the PiHole directory.
`~/docker/pihole/.env` is not re-rendered any more (the file stays). **Send:** `nas4-1-check.txt`.

## Stage 2: real run, then re-runs

```bash
"${RUN[@]}" nas-provision 2>&1 | tee "$TMPDIR/nas4-2-run.txt" "${RUN[@]}" nas-provision 2>&1 | tee
"$TMPDIR/nas4-2-rerun.txt" "${RUN[@]}" nas-provision 2>&1 | tee "$TMPDIR/nas4-2-rerun2.txt"
```

Expect: the re-runs end `changed=0`, including "Create the PiHole config directory" (skipped, directory exists) and
"Deploy all services". **Send:** all three files.

## Stage 3: tag selection on the real host

```bash
"${RUN[@]}" nas-provision --tags configfile 2>&1 | tee "$TMPDIR/nas4-3-configfile.txt"
```

Expect: only the docker `.env` render, the docker `deploy.sh` copy, and the samba `smb.conf` tasks run (all `ok`), no
`dotfiles`/`haos`/`services` tasks. **Send:** `nas4-3-configfile.txt`.

## Stage 4: laptop deploy path (covers the hardened script)

```bash
"${RUN[@]}" nas-deploy glance --dry-run 2>&1 | tee "$TMPDIR/nas4-4-dry.txt" "${RUN[@]}" nas-deploy glance 2>&1 | tee
"$TMPDIR/nas4-4-deploy.txt"
```

Expect: the dry run prints `dry-run: would run: ssh -- <user>@<host> ~/docker/deploy.sh glance`; the real deploy ends
with glance `Running`. **Send:** both files.

## Stage 5: after the PR merges (CI path)

```bash
gh workflow run "Deploy NAS Services" -f service=glance gh run watch
```

Expect: green. This is the first run of the workflow's `env:`-based SSH key step. If it fails, send `gh run view --log`
output saved under `$TMPDIR` (or the failing step's text).

## Questions only you can answer (documented as absent until then)

1. Does the NAS configure Docker log rotation (`/etc/docker/daemon.json`)?
2. Is there an `incomplete/` directory under `/storage/media/downloads`?
3. Does the deploy key's line in `~/.ssh/authorized_keys` carry the `restrict` option?
````

- [ ] **Step 5: Commit nothing; report.** Write the final test count and the lint result into the progress notes for
  Task 18.

---

## Task 18: Independent audit and whole-branch review (controller-run)

- [ ] **Step 1: Fresh audit agents.** Dispatch four read-only `file-explorer` agents in parallel, each told to work only
  in the worktree and to report every claim in its files that the code contradicts (format:
  `file:line | doc says | code says (file:line) | severity | fix`), with no knowledge of this plan's fix lists:
  1. root `README.md`, `CLAUDE.md`, `docs/README.md`, `docs/RUN_PY_REFERENCE.md`, `.ctx/CONVENTIONS.md`,
     `scripts/nas/README.md`, `vms/README.md`;
  2. `.ctx/ARCHITECTURE.md`, `.ctx/BUILD.md`, `playbooks/README.md`, `roles/README.md`;
  3. `services/README.md`, `roles/docker/README.md`, `roles/services/README.md`, `roles/tailscale/README.md`,
     `roles/samba/README.md`;
  4. the code changes (`git diff main...HEAD -- . ':!*.md'`) for bugs, missed edge cases, and tests that would pass
     against the old code.
  **Exit criterion:** zero discrepancies of severity `wrong` or `misleading`; fix, re-run the affected agent, repeat.
- [ ] **Step 2: Idempotency review.** Dispatch `ansible-idempotency-reviewer` on the diff of `playbooks/`,
  `roles/docker`, `roles/services`. Resolve every finding or record why it is out of scope.
- [ ] **Step 3: Whole-branch review.** Run `/code-review` (or the `anthropic-pr-review-toolkit:code-reviewer` agent) on
  `git diff main...HEAD`, fix findings, and re-run the full suite and `prek run --all-files`.
- [ ] **Step 4: Report to the owner** with: commit list, final test count, the open questions above, the rollout runbook
  path, and the reminder that nothing is pushed. Ask before pushing or opening the PR (the worktree is removed after the
  PR, per the owner's standing rule; branch kept).
