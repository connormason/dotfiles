# NAS Sub-project 3: Deploy from the Laptop

**Date:** 2026-11-02
**Status:** Draft, pending owner review
**Parent design:** [`2026-10-31-nas-provisioning-design.md`](../2026-10/2026-10-31-nas-provisioning-design.md)
(decisions D1–D9 and the "Sub-project 3" section; this document refines them against the repository as of `5401a8a`)
**Goal:** Provision the NAS and deploy its services from the work MacBook with one command each, make a fresh NAS
converge from a single provisioning run, and give services a per-service secrets mechanism.

## Context

Sub-projects 1 (engine Linux support, PR #27) and 2 (NAS profile and Ansible handoff, PR #36) are merged. Provisioning
works but is hand-driven: the sub-project 2 rollout assembled a `PLAY=(…)` array of `ansible-playbook` flags in the
owner's terminal (`~/nas-sp2-rollout.md`). Service deploys exist only as the rsync + `deploy.sh` steps inlined three
times in `.github/workflows/deploy.yml`.

Findings from reading the repository at `5401a8a`:

- **`nas_bootstrap.sh`** still installs Homebrew (hardcoded `/opt/homebrew`, `shasum`) and `brew install ansible` on the
  controller, though `ansible-core` is already a uv dependency (`pyproject.toml`). It duplicates the Homebrew installer
  pin held in `bootstrap/50-brew.sh`; `tests/unit/test_nas_bootstrap.py` keeps the two equal.
- **`deploy.yml`** has three copies of the Tailscale + SSH-key setup and the rsync/ssh steps (matrix push job, manual
  job). `detect-changes` is sound and stays.
- **The `docker` role does not place `compose.base.yml` or `services/` on the NAS.** It copies `deploy.sh` and runs
  `deploy.sh all` unconditionally (no `changed_when`, so it reports `changed` on every run). A fresh NAS cannot succeed
  until CI has deployed once.
- **Fresh-install bug in the `docker` role:** the "Add Docker GPG signing key" `get_url` writes to
  `/usr/share/keyrings/` without `become`. It succeeds today only because the file already exists and is unchanged.
- **Secrets:** `roles/docker/templates/env.j2` renders one global `~/docker/.env` holding `pihole_web_password` and
  `ADVERTISE_IP`. PiHole's compose file is `compose.yml.disabled`; `ADVERTISE_IP` is not secret (consumed by Plex via
  interpolation); Glance reads the file through `env_file: .env`. The design's per-service mechanism therefore has no
  live secret consumer until PiHole returns.
- **Inventory** lives in a separate private repo (`dotfiles-inventory`), cloned to the gitignored `inventory/`. The
  `nas` host's `ansible_host` is `192.168.68.79`. Any inventory change is made there, not in this repository.
- **`run.py`** already provides `@command` registration, `shell_command()`, `parse_extra_vars()`, and
  `require_inventory()` / `require_vault_password()` helpers (`run.py:871`, `1179`, `1192`), and generates the Makefile
  from registered commands.
- **SSH path:** the sub-project 2 rollout ran Ansible over plain sshd at the LAN address, resolving the parent design's
  open question 2 for the LAN. Reachability through the tailnet name cannot be probed from the Claude sandbox (LAN
  sockets are blocked); the owner confirms it.

## Goals and non-goals

Goals:

1. `run.py nas-provision` and `run.py nas-deploy` replace the hand-assembled Ansible and rsync invocations.
2. CI and laptop deploys share one implementation (parent D8).
3. A fresh NAS converges from one provisioning run, with no CI prerequisite, and a converged NAS reports `changed=0`.
4. Services opt into per-service secrets rendered from the vault; the first consumer is PiHole's password (parent D9).
5. Clear up the backlog items deferred from sub-project 2 that belong to this layer.

Non-goals:

- Editing the inventory repo (MagicDNS host switch, removing stale Lutron certificate files in `group_vars/all`). These
  are owner actions, listed under [Owner actions](#owner-actions).
- The docs truth-up (sub-project 4). This PR touches only the docs its own changes make false.
- Replacing the CI deploy path or changing `detect-changes`.
- Re-enabling PiHole.

## Decisions

| #   | Decision                                                                                       | Rationale / alternatives rejected                                                                                                                                                                                      |
| --- | ---------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| E1  | **New `services` role (last in the playbook) owns sync, secrets, and `deploy.sh all`**         | Keeps `docker` to engine install and directories. Folding sync into `docker` mixes two lifecycles (engine vs. content) behind one tag; `services` gets a clean `--tags services` / `secrets` handle.                    |
| E2  | **Sync with `ansible.posix.synchronize` from the controller's working tree**                   | Same semantics as `nas-deploy` (the laptop's tree), so one mental model. Rejected: copying from the NAS clone of `main` (needs the `dotfiles` role earlier in the playbook and diverges from a branch test).             |
| E3  | **`scripts/nas/deploy-services.sh` parameterised by env (`NAS_HOST`, `NAS_USER`, `NAS_SSH_KEY`)** | CI passes a key and a host from secrets; the laptop passes inventory-resolved values and relies on `ssh-agent`/config. One script, two callers.                                                                         |
| E4  | **Host and user for `nas-deploy` come from the inventory** (`ansible-inventory --host nas`)    | The inventory stays the single source for the NAS address, so the MagicDNS switch is one edit. Rejected: a second host setting in `run.py` or an environment variable.                                                  |
| E5  | **`nas_bootstrap.sh` becomes a thin wrapper over `run.py nas-provision`**                      | Keeps the documented entry point without a second code path. The Homebrew/Ansible installs and the duplicated installer pin disappear. Rejected: deleting the script (documented entry point; fresh-clone muscle memory). |
| E6  | **`changed_when` for `deploy.sh all` keys on `compose up` verbs, not on `Running`**            | `Started`, `Recreated`, `Created`, `Pulled` mean real change; `Running` means converged. Gives a truthful `changed=0` on re-runs.                                                                                       |
| E7  | **Secrets render on the NAS from controller-side templates, mode `0600`, `no_log`**            | Vault values never reach CI or `~/docker/<svc>/` in a world-readable file.                                                                                                                                             |

## Architecture

### Control flow

```
work MacBook ─ run.py nas-provision ─▶ preflight ─▶ ansible-galaxy install ─▶ ansible-playbook (uv env) ─SSH▶ NAS
                                                       debian → zfs → samba → docker → tailscale → dotfiles → haos → services
                                                                                                                      │
                                                                 synchronize ─▶ render secrets ─▶ deploy.sh all ◀─────┘

work MacBook ─ run.py nas-deploy <svc|all> ─▶ resolve host/user from inventory ─▶ scripts/nas/deploy-services.sh
GitHub push (services/**) ─▶ deploy.yml ─▶ scripts/nas/deploy-services.sh ──────▶ rsync + ssh ~/docker/deploy.sh <svc>
```

### `run.py nas-provision`

`run.py nas-provision [--tags TAGS] [--check] [--diff] [--limit HOSTS] [-e KEY=VALUE …]`

1. **Preflight**, each failure printing its remedy:
   - inventory present → `run.py update-inventory`;
   - `vault_password.txt` present → create it (see `CLAUDE.md`);
   - the NAS's `ansible_host` resolved and answering `ssh -o ConnectTimeout=5 -o BatchMode=yes … true` → "is
     Tailscale up? does the inventory host resolve?".
2. `ansible-galaxy collection install -r roles/requirements.yml` (idempotent).
3. `ansible-playbook playbooks/nas_bootstrap.yml -i inventory/inventory.yml` with the vault password file, forwarding
   `--tags`, `--check`, `--diff`, `--limit`, and `-e` (reusing `parse_extra_vars`). `-e dotfiles_repo_version=<branch>`
   is the supported way to test the `dotfiles` role against a branch.
4. Runs Python through `scripts/hooks/uv-public.sh`, matching the rollout runbook and the repository's uv rule.

The exit status is Ansible's.

### `run.py nas-deploy`

`run.py nas-deploy <service|all> [--dry-run]`

- Resolves `ansible_host` and `ansible_user` for `nas` from the inventory (`ansible-inventory --host nas`, using the
  vault password file when variables are vaulted).
- Warns (does not block) when the working tree has uncommitted changes under `services/`.
- Exports `NAS_HOST` / `NAS_USER` and runs `scripts/nas/deploy-services.sh [--dry-run] <service|all>`.
- **Documented caveat:** a deploy from a branch is superseded the next time CI deploys `main` for that service.

### `scripts/nas/deploy-services.sh`

`deploy-services.sh [--dry-run] <service|all>`

- Requires `NAS_HOST` and `NAS_USER`; optional `NAS_SSH_KEY` adds `-i` and `StrictHostKeyChecking=accept-new` (CI
  behaviour; the laptop uses its normal SSH configuration).
- For one service: `rsync -az --exclude='*.j2' --exclude='.env'` of `services/compose.base.yml` and
  `services/<service>/` to `~/docker/`. For `all`: the same rsync of `services/`. No `--delete` (unchanged semantics).
- Then `ssh … "~/docker/deploy.sh <service>"`. Fails fast on a missing service directory.
- `--dry-run` adds `rsync -n` and prints, rather than runs, the `ssh` command.
- bash 3.2-compatible, `set -euo pipefail`, styled like the other repository scripts.

### CI

`deploy.yml` keeps `detect-changes` unchanged. In `deploy-push` and `deploy-manual`, the "Rsync …" and "Deploy" steps
collapse into one step that exports `NAS_HOST`, `NAS_USER`, and `NAS_SSH_KEY` from the existing secrets and calls the
script. The Tailscale and key setup steps are untouched. A new `tests/unit` check pins that the workflow calls the
script and no longer contains inline `rsync` (the parent design requires CI and laptop paths not to diverge).

### `services` role

Runs last in `playbooks/nas_bootstrap.yml` (tags `services`, `configfile`); the secrets step also carries `secrets`.

| Step    | Module                          | Detail                                                                                                  |
| ------- | ------------------------------- | ------------------------------------------------------------------------------------------------------- |
| sync    | `ansible.posix.synchronize`     | `compose.base.yml` and `services/` to `{{ docker_dir }}/`; excludes `*.j2`, `.env`; no delete           |
| secrets | `ansible.builtin.template` loop | `services/*/env.j2` found on the controller; dest `{{ docker_dir }}/<svc>/.env`, mode `0600`, `no_log` |
| deploy  | `ansible.builtin.command`       | `{{ docker_dir }}/deploy.sh all`; `changed_when` per E6; `HOME` pinned as the current task does         |

`ansible.posix` joins `community.docker` in `roles/requirements.yml` (the FQCN guard test already compares usage with
the requirements file). `--check` skips the deploy command and previews sync and render.

### Per-service secrets

- A service needing secrets ships `services/<svc>/env.j2` and references `env_file: .env` in its `compose.yml`.
- The `services` role's secrets step renders each template to `~/docker/<svc>/.env`. Rotation:
  `run.py nas-provision --tags secrets`, then `run.py nas-deploy <svc>`.
- **PiHole migration:** `services/pihole/env.j2` carries `FTLCONF_webserver_api_password={{ pihole_web_password }}`;
  `compose.yml.disabled` gains `env_file: .env` and loses its bare `FTLCONF_webserver_api_password` entry under
  `environment:` (Compose lets `environment:` override `env_file:`, and a bare name resolved from an unset interpolation
  variable would shadow the value). The password line is removed from `roles/docker/templates/env.j2`, which keeps only
  the non-secret `ADVERTISE_IP`.
- The parent design's cleanup of stale Home Assistant secrets / Lutron certificate documentation is part of the doc
  edits in this PR where such text exists in files this PR already touches; the certificate files themselves live in the
  inventory repo.

### `docker` role changes

- `get_url` for the Docker GPG key gains `become: true` (fresh-install bug above).
- `dpkg --print-architecture` task gains `changed_when: false`.
- `service:` becomes `ansible.builtin.service:`.
- The "Run initial full deploy" task moves to the `services` role; `docker` keeps copying `deploy.sh`.
- Whether the legacy `docker-compose` apt package is still needed beside `docker-compose-plugin` is confirmed on the NAS
  during the live run (`deploy.sh` uses `docker compose`); it is removed only if nothing references `docker-compose`.

### `nas_bootstrap.sh`

Keeps the repository-layout validation, then `exec uv run run.py nas-provision "$@"`. No Homebrew or Ansible install, no
`/opt/homebrew`, no `shasum`. `tests/unit/test_nas_bootstrap.py` drops the installer and pin-equality tests (the pin
then exists only in `bootstrap/50-brew.sh`) and keeps the collection guard.

### Housekeeping from the sub-project 2 backlog

- `vms/haos/setup.sh`: `usbutils` added to `PACKAGES` (ConBee passthrough calls `lsusb`).
- `.ctx/ARCHITECTURE.md`: stage list gains `58-defaults-backup`.
- `scripts/deploy_configs.sh`: deleted (unreferenced).

## Error handling

| Failure                                    | Behaviour                                                                                         |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------- |
| Inventory or vault password missing        | `nas-provision` / `nas-deploy` preflight fails before any network call, naming the remedy         |
| NAS unreachable (SSH probe fails)          | Preflight fails fast with "is Tailscale up? does `<host>` resolve?"                               |
| Unknown service name                       | `deploy-services.sh` exits non-zero before rsync                                                  |
| Dirty working tree under `services/`       | `nas-deploy` warns and continues                                                                  |
| Service fails to start                     | `deploy.sh` exits non-zero (existing); `nas-deploy` and CI surface it; Ansible task fails         |
| Secret template references missing vault var | Template task fails the play (Ansible undefined-variable error); `no_log` hides values            |
| `--check`                                  | Sync and secrets previewed; `deploy.sh` skipped                                                   |

## Testing and verification

Unit tests (mocked `subprocess`; no network), following existing `tests/unit` style:

- `nas-provision`: argument-to-command construction (tags, check, diff, limit, extra vars); each preflight failure and
  its message; exit status passthrough.
- `nas-deploy`: host/user resolution; dirty-tree warning; `--dry-run` never invokes `ssh`; unknown service handling.
- `deploy-services.sh`: executed with stub `rsync` / `ssh` first on `PATH`, asserting arguments, excludes, `--dry-run`,
  and the missing-service failure.
- Playbook/role structure (extending `test_nas_playbook.py`): `services` is last; the `secrets` tag reaches only the
  render step; `ansible.posix` is declared; `docker` no longer runs `deploy.sh`; the Docker key task has `become`.
- Workflow: `deploy.yml` invokes the script and holds no inline `rsync`.
- `nas_bootstrap.sh`: delegates to `run.py nas-provision`; contains no Homebrew installer.
- `ansible-lint` (prek and CI) stays green.

Live acceptance (run by the owner; the Claude sandbox cannot open LAN sockets):

1. `run.py nas-provision --check --diff` shows no unexpected change.
2. A real run, then a second run reporting `changed=0` for the whole play.
3. `~/docker/pihole/.env` exists with mode `0600`; `~/docker/.env` holds only `ADVERTISE_IP`.
4. `run.py nas-deploy glance` from the laptop succeeds; one CI deploy of a service succeeds after merge.
5. The `docker-compose` package decision is made from `which docker-compose` use on the NAS.

## Owner actions

Not part of the PR:

- Change `ansible_host` for `nas` in the inventory repo to the MagicDNS name once `ssh <name>` works from the laptop,
  and push that repo.
- Remove the stale Lutron certificate files from the inventory repo's `group_vars/all` (unused since the HAOS move).
- Run the live acceptance steps above.

## Open questions

1. Whether plain sshd is reachable through the tailnet name from the work MacBook (owner-verified; affects only the
   inventory edit above, not the code).
2. Whether the `docker-compose` apt package has remaining consumers on the NAS (resolved during live acceptance).
