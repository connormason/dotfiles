# NAS Provisioning & Deployment Design

**Date:** 2026-10-31
**Status:** Approved (design); implementation plan pending for sub-project 1
**Goal:** Standardize the developer environment across the work Mac, personal Mac, and home NAS by running the same
stow engine everywhere, keep Ansible for root-level NAS system configuration, and give the work MacBook first-class
commands to provision the NAS and deploy its services.

## Context

The October overhaul (PRs #17–#24) moved macOS provisioning off Ansible onto a layered stow engine plus numbered
`bootstrap/` stages. The NAS still runs on the pre-overhaul model. Findings from a survey of the repo at `1e1c8dd`:

### NAS today

- **Provisioning is controller-push Ansible.** `nas_bootstrap.sh` runs on a Mac: it installs Homebrew there (hardcoded
  `/opt/homebrew`), installs Ansible via `brew`, and runs `playbooks/nas_bootstrap.yml` over SSH against `hosts: nas`.
  Nothing Homebrew-related runs on the NAS itself.
- **Eight roles:** `debian`, `zfs`, `samba`, `docker`, `git`, `ssh`, `tailscale`, `zsh`. `tailscale` is the
  best-written; `debian` and `zfs` contain `command` tasks without `changed_when` (perpetually `changed`).
- **The dev environment is forked.** `roles/zsh` copies its own `.zshrc`/`.p10k.zsh` (oh-my-zsh + powerlevel10k) and
  `roles/git` templates its own `.gitconfig`. Both have drifted from `stow/shell` and `stow/git`.
- **Services already bypass Ansible for day-to-day deploys.** `.github/workflows/deploy.yml` triggers on pushes to
  `main` touching `services/**`, joins the tailnet (`tag:ci`), rsyncs `compose.base.yml` + `services/<svc>/` to
  `~/docker/` (`--exclude='*.j2'`, no `--delete`), and runs `~/docker/deploy.sh <svc>`. CI never handles secrets.
- **Fresh-install gap.** The `docker` role copies `deploy.sh` and runs `deploy.sh all`, but nothing in the role places
  `compose.base.yml` or `services/` on the NAS, so a fresh NAS cannot succeed until CI has run once.
- **Secrets reach services through one global `~/docker/.env`** rendered from `roles/docker/templates/env.j2`
  (consumed by `glance` and `plex`). Documented Home Assistant `secrets.yaml` templating was never implemented and is now
  moot: PR #26 moved Home Assistant into a HAOS VM that manages its own secrets.
- **System configuration is split.** PR #26 added `vms/haos/bridge.sh` and `vms/haos/setup.sh`: hand-run, idempotent,
  `--dry-run`-capable bash run with `sudo` from a repo clone on the NAS (LAN bridge, libvirt/KVM VM, libvirt-guests,
  Docker forwarding drop-in).
- **Stale docs:** `.ctx/ARCHITECTURE.md` points at a nonexistent `roles/docker/files/docker-compose.yml`;
  `services/README.md` says the docker role deploys `services/` (CI does); `roles/docker/README.md` (~1,090 lines)
  describes a single-compose-file era. `scripts/deploy_configs.sh` is unreferenced.

### Stow engine portability

- **The core is portable.** `bootstrap/lib.sh`, `stow.sh`, and the stage driver deliberately target bash 3.2 and use
  no BSD/GNU-divergent tools (no `sed -i`, `stat -f`, `readlink -f`, `date -v`). The Oct 26 design already states the
  engine "should not preclude Linux later."
- **macOS coupling is confined:**
  - `00-preflight.sh` dies unless `uname -s` is `Darwin` (the only OS detection in the engine).
  - `50-brew.sh`, `60-macos.sh`, `96-iterm2.sh` are macOS-specific; `72-vscode.sh` self-skips without `code`.
  - `lib.sh` `ensure_brew_on_path` probes only `/opt/homebrew` and `/usr/local`.
  - `run.py doctor` requires `brew`; `render.py`'s `vscode` target hardcodes `~/Library/Application Support/...`.
- **No per-OS package selection.** `stow.sh` links every package in every layer; `hammerspoon`, `iterm2`, `vscode`, and
  `python` (whose only file is `Library/Application Support/hatch/config.toml`) would litter `~/Library` on Linux.
- **Shell config is mostly portable.** Plugin discovery already goes through `$HOMEBREW_PREFIX` and skips missing
  plugins. macOS-isms: `alias o="open ."`, `VISUAL=subl`, `fastfetch --logo macOS2`, `~/Desktop`/`~/Downloads`
  directory shortcuts.
- **Brewfile:** 59 formulae, 12 casks, 2 `mas` entries, 3 taps.
- **CI:** lint jobs run on `ubuntu-latest`; `pytest (macOS)` (pytest + `bootstrap.sh --dry-run` under a throwaway
  `HOME`) runs only on `macos-latest`.

### Owner inputs (2026-10-31)

| Question                              | Answer                                                              |
| ------------------------------------- | ------------------------------------------------------------------- |
| Can the work MacBook reach the NAS?   | Yes — direct access (tailnet + SSH) is permitted                    |
| Dev-environment parity on the NAS     | Full parity: same shell, CLI tools, toolchains, Claude Code, repos  |
| NAS CPU architecture                  | x86_64 (Linuxbrew Tier 1)                                           |

## Goals and non-goals

Goals:

1. One dev-environment definition (stow packages, Brewfile, stages) used by every machine, with OS differences
   expressed declaratively rather than by forking files.
2. A single, explicit ownership boundary between user-space and system-space on the NAS.
3. From the work MacBook: provision the NAS and deploy any service with one command each, without pushing to `main`.
4. A fresh NAS converges from one provisioning run, with no CI prerequisite.
5. Zero behaviour change on either Mac from the engine work.

Non-goals:

- Migrating the work repo onto the engine as an overlay (P1b; a separate track that inherits this work).
- Replacing CI deploys; the push-to-`main` path stays.
- Managing Home Assistant configuration (lives in the HAOS VM, configured through its UI and backups).
- Container orchestration beyond Compose; a secrets manager beyond `ansible-vault`.

## Decisions

| #  | Decision                                                                                     | Rationale / alternatives rejected                                                                                                                                                                                                  |
| -- | -------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| D1 | **Hybrid: stow engine owns `$HOME`, Ansible owns root, `deploy.sh` owns services**           | All-scripts would reimplement Ansible's validated templating, handlers, apt-repo/key management, and idempotence in bash. All-Ansible keeps the dev env forked from the Macs — the opposite of the goal. The macOS move off Ansible was justified by user-space fit; that rationale does not transfer to `/etc`. |
| D2 | **Boundary rule: needs root → Ansible; lives in `$HOME` → engine**                           | One rule resolves every edge case (login shell → Ansible; SSH key → engine; `/home/linuxbrew` creation → Ansible; Homebrew install → engine).                                                                                       |
| D3 | **Ansible stays controller-push from the Mac**                                               | Agentless push over the tailnet is exactly "deploy from the work MacBook." `ansible-core` is already in the uv environment for vault commands.                                                                                    |
| D4 | **Linuxbrew on the NAS, one shared Brewfile with `if OS.mac?` blocks**                       | Full parity requires matching tool versions; Debian stable lags (or lacks) starship, eza, delta, etc. x86_64 is Linuxbrew Tier 1. A separate Linux manifest (apt/mise) was rejected as a second source of truth.                     |
| D5 | **OS-specific stages self-guard via `require_os`**                                           | Keeps the driver and cross-layer stage-number uniqueness untouched; the condition is visible in the stage. Filename tags (`60-macos.darwin.sh`) rejected as a driver change with no real benefit.                                   |
| D6 | **Per-package `.dotfiles-os` marker file**                                                   | Co-located with the package, so it works identically in overlays. A central per-OS package list was rejected: it must be kept in sync across layers.                                                                             |
| D7 | **`vms/haos/setup.sh` stays the implementation; a thin `haos` role invokes it**              | One entry point for system config without rewriting tested scripts. `bridge.sh` is never run by Ansible — it blips the network and relies on a rollback timer, unsafe over an Ansible SSH session.                                 |
| D8 | **One deploy implementation shared by CI and `run.py`** (`scripts/nas/deploy-services.sh`)   | Prevents laptop and CI deploys from drifting apart.                                                                                                                                                                                |
| D9 | **Per-service `env.j2` → vault-rendered `~/docker/<svc>/.env` (0600)**                       | The existing `*.j2` rsync exclusion already anticipates this. Secrets never touch CI. A global `.env` is retained only for non-secret shared values (e.g. `ADVERTISE_IP`).                                                         |

## Architecture

### Ownership on the NAS

| Layer                                                   | Owner                     | Source of truth                                     |
| ------------------------------------------------------- | ------------------------- | --------------------------------------------------- |
| `$HOME`: dotfiles, CLI tools, toolchains, repos, SSH key | Stow engine               | base layer + `profiles/nas` overlay                 |
| System: apt, ZFS, Samba, Docker engine, Tailscale, systemd, libvirt VM | Ansible   | `roles/` (+ `vms/haos/setup.sh` via `haos` role)    |
| Compose services                                        | `deploy.sh` on the NAS    | `services/`, triggered by CI or `run.py nas-deploy` |

### Control flow

```
work MacBook ──run.py nas-provision──▶ ansible-playbook (uv env) ──SSH/tailnet──▶ NAS
                                         debian → zfs → samba → docker → tailscale → dotfiles → haos → services
                                                                                        │
                                                                     bootstrap.sh (as user, profiles/nas)

work MacBook ──run.py nas-deploy svc──▶ scripts/nas/deploy-services.sh ──rsync+ssh──▶ ~/docker/deploy.sh svc
GitHub push to main (services/**) ────▶ deploy.yml ──▶ scripts/nas/deploy-services.sh ──▶ (same)
```

### Sub-projects

Each sub-project receives its own implementation plan and PR, in this order. The current NAS setup keeps working
between them.

1. **Engine Linux support** — buildable and CI-testable without the NAS.
2. **NAS profile and Ansible handoff** — `profiles/nas`, `dotfiles` and `haos` roles, retire `roles/zsh` and
   `roles/git`.
3. **Deploy from the laptop** — `run.py nas-provision` / `nas-deploy`, shared deploy script, fresh-install fix,
   per-service secrets.
4. **Docs truth-up** — `.ctx/ARCHITECTURE.md`, `.ctx/BUILD.md`, `services/README.md`, `roles/README.md`,
   `roles/docker/README.md`, `playbooks/README.md`, `CLAUDE.md` entry points.

## Sub-project 1: Engine Linux support

### OS detection

`bootstrap/lib.sh` gains `dotfiles_os`, printing `darwin` or `linux` from `uname -s` (any other value is fatal). The
`DOTFILES_OS` environment variable overrides detection for tests.

### Stage gating

- New helper `require_os <os>...`: if the current OS is not listed, log `skipped (<os> only)` and `exit 0`.
- Guarded `darwin`: `60-macos.sh`, `96-iterm2.sh`, `72-vscode.sh`.
- `00-preflight.sh` gains a Linux branch: confirm Debian via `/etc/os-release` and check for the system prerequisites
  Ansible installs (Homebrew build prerequisites, `zsh`, `git`, `curl`). Missing prerequisites fail with a message naming
  the `debian` role as the fix — the engine never runs `apt`.
- `--list` continues to show every discovered stage; guarded stages report their skip at run time.

### Package gating

- A package may contain `.dotfiles-os`, one OS name per line. Absent marker = all OSes.
- `stow.sh` filters packages by marker before simulation and passes `--ignore '\.dotfiles-os'`, so the marker is never
  linked.
- Marked `darwin`: `hammerspoon`, `iterm2`, `vscode`.
- `python`: its only file is the macOS hatch config path. The plan first checks whether hatch honours a portable config
  location (environment variable or `~/.config/hatch`); if so, the package moves to that location for both OSes,
  otherwise it is marked `darwin` and a `linux`-marked sibling provides the XDG path.
- A package-ownership conflict check (`stow.sh`'s "no two packages own the same path") runs over the filtered set.

### Homebrew

- `bootstrap/Brewfile`: wrap the 12 casks, 2 `mas` entries, and any macOS-only formulae/taps in `if OS.mac?` blocks.
  Overlay Brewfiles follow the same convention.
- `ensure_brew_on_path` adds `/home/linuxbrew/.linuxbrew` to its probe list.
- `50-brew.sh` on Linux installs Homebrew **without sudo**, using the same pinned, checksum-verified installer. It
  requires `/home/linuxbrew` to exist and be owned by the user (created by the `debian` role) and fails with that
  instruction otherwise. `NONINTERACTIVE=1` is set.

### Shell and tooling

- `40-aliases.zsh`: the `open` alias and `VISUAL=subl` become OS-conditional (`$OSTYPE`); Linux uses a terminal editor.
- `50-directories.zsh`: `~/Desktop`/`~/Downloads` shortcuts become conditional on the directory existing.
- `90-banner.zsh`: fastfetch logo becomes OS-conditional.
- `run.py doctor`: required-tools list per OS (`brew` required on both once Linuxbrew is installed; macOS-only checks
  skipped on Linux).
- `render.py`: the `vscode` target is darwin-only; `claude` renders on both.

### Compatibility constraint

All engine shell code stays bash 3.2-compatible (Debian's bash 5 runs it unchanged). The existing test pinning
`/bin/bash` 3.x on darwin stays.

## Sub-project 2: NAS profile and Ansible handoff

### `profiles/nas`

An in-repo overlay carrying NAS-only content: a Brewfile for any NAS-specific formulae, `repos.txt` additions, and
NAS-specific stages if needed. Starts minimal; base-layer parity is the default.

### Playbook order

`debian` → `zfs` → `samba` → `docker` → `tailscale` → `dotfiles` → `haos` → services deploy (sub-project 3).

### `debian` role additions

- Install Homebrew build prerequisites and engine prerequisites (`build-essential`, `procps`, `curl`, `file`, `git`,
  `zsh`; exact list confirmed against Homebrew's Linux requirements in the plan).
- Create `/home/linuxbrew/.linuxbrew` owned by `ansible_user`.
- Add `changed_when` to the `systemctl` mask/unmask tasks.

### `dotfiles` role (new)

1. Clone or fast-forward `~/dotfiles-personal` (`ansible.builtin.git`, `update: true`). If the clone has local
   modifications, fail with a clear message rather than clobbering — the NAS clone is a usable working copy.
2. Write `~/.config/dotfiles/overlays` listing `~/dotfiles-personal/profiles/nas`.
3. Set the login shell to `zsh` (`ansible.builtin.user`, root).
4. Run `bootstrap/bootstrap.sh` as the user (`become_user: "{{ ansible_user }}"`). `changed_when` keys off a summary
   line the driver emits (added in this sub-project if absent). `--check` maps to `--dry-run`.
5. **First-run migration:** the initial run passes `--backup-conflicts` to the dotfiles stage, moving the Ansible-copied
   `.zshrc`, `.zprofile`, `.p10k.zsh`, and `.gitconfig` into `~/.dotfiles-backup/<timestamp>/`. The prompt changes from
   powerlevel10k to starship, matching the Macs.

### Retired roles

- `roles/zsh` and `roles/git`: deleted.
- `roles/ssh`: deleted; the existing `20-ssh-key` stage (already Linux-ready) generates the key in user-space.

### `haos` role (new)

- Asserts `br0` exists; if not, fails with instructions to run `sudo vms/haos/bridge.sh` from the console or `tmux`.
- Runs `vms/haos/setup.sh` from the NAS clone as root. `--check` maps to `--dry-run`; `changed_when` keys off a summary
  line the script emits (added if absent).
- Depends on the `dotfiles` role for the repo clone.

### Other role hygiene

- `zfs`: `changed_when` on the `apt-add-repository` and `dpkg --print-architecture` tasks.
- Playbook: drop the redundant `--ask-become-pass` (the vault supplies `ansible_become_pass`).

## Sub-project 3: Deploy from the laptop

### Inventory

`ansible_host` for `nas` switches from the LAN address to the NAS's Tailscale MagicDNS name, so provisioning and
deploys work off-LAN. Both new commands read the host from the inventory. (A read-only probe on 2026-10-31 found port 22
refusing connections on the LAN address; the plan confirms the actual SSH path before changing the inventory.)

### `run.py nas-provision [--tags TAGS] [--check] [--diff] [--limit]`

- Runs `ansible-galaxy collection install -r roles/requirements.yml` (idempotent), then `ansible-playbook
  playbooks/nas_bootstrap.yml -i inventory/inventory.yml` inside the uv environment.
- Preflight: inventory present, `vault_password.txt` present, NAS reachable (`ssh -o ConnectTimeout`); each failure
  prints a specific remedy (`run.py update-inventory`, create the vault file, "is Tailscale up?").
- `nas_bootstrap.sh` becomes a thin wrapper around this command; its Homebrew install, `brew install ansible`, and the
  duplicated installer pin (plus `test_nas_bootstrap.py`'s pin-equality test) are removed.
- `scripts/deploy_configs.sh` is deleted.

### `run.py nas-deploy <svc|all> [--dry-run]`

- Delegates to `scripts/nas/deploy-services.sh`, extracted from `deploy.yml`'s rsync + `deploy.sh` steps.
  `deploy.yml` calls the same script, so CI and laptop behaviour cannot diverge.
- rsync excludes `*.j2` and `.env`; no `--delete` (unchanged semantics).
- Deploys the working tree; warns when it has uncommitted changes.
- **Documented caveat:** a laptop deploy from a branch is superseded the next time CI deploys `main` for that service.

### Fresh-install fix

The `docker` role syncs `compose.base.yml` and `services/` to `~/docker/` with `ansible.posix.synchronize` (same
exclusions as the shared script) before running `deploy.sh all`. `ansible.posix` is added to `roles/requirements.yml`.
The `deploy.sh all` task gains `changed_when`.

### Per-service secrets

- A service needing secrets gets `services/<svc>/env.j2` and references `env_file: <svc>/.env` in its `compose.yml`.
- The `docker` role (tag `secrets`) discovers `services/*/env.j2` and renders each to `~/docker/<svc>/.env`, mode
  `0600`, from vault variables.
- Rotation workflow: `run.py nas-provision --tags secrets`, then `run.py nas-deploy <svc>`.
- Stale Home Assistant secrets / Lutron cert documentation is removed.

## Error handling

| Failure                                      | Behaviour                                                                                 |
| -------------------------------------------- | ----------------------------------------------------------------------------------------- |
| Unsupported OS / non-Debian Linux            | `00-preflight` fails before any change                                                    |
| Missing system prerequisites on the NAS      | `00-preflight` / `50-brew` fail naming the `debian` role                                  |
| Stow conflicts                               | Existing all-or-nothing simulation aborts; `--backup-conflicts` is opt-in (first NAS run) |
| Dirty NAS repo clone                         | `dotfiles` role fails without modifying the clone                                         |
| `br0` missing                                | `haos` role fails with the manual bridge instructions                                     |
| NAS unreachable from laptop                  | `nas-provision` / `nas-deploy` preflight fails fast with "is Tailscale up?"               |
| Missing inventory or vault password          | Preflight names the remedy                                                                |
| Service fails to start                       | `deploy.sh` exits non-zero (existing behaviour); surfaced by CI and `run.py`              |

## Testing and verification

Sub-project 1:

- New CI job **`pytest (Linux)`** on `ubuntu-latest`: `pytest` plus `bootstrap.sh --dry-run` under a throwaway `HOME`.
- Unit tests: `dotfiles_os` (including `DOTFILES_OS` override and unknown-OS failure), `require_os`, `.dotfiles-os`
  filtering in `stow.sh`, Brewfile evaluation on both OSes (`brew bundle list`; the plan verifies Homebrew availability
  on the Ubuntu runner).
- **macOS no-op proof:** golden comparison of `bootstrap.sh --list` and the `stow.sh` simulation output on darwin
  before and after the change; any difference fails the test.

Sub-projects 2–3:

- `ansible-lint` added to prek and CI.
- `run.py nas-provision --check --diff` precedes every real run.
- Idempotence: a second provisioning run reports `changed=0`; changes reviewed by the `ansible-idempotency-reviewer`
  agent.
- Unit tests for `nas-provision` / `nas-deploy` command construction and preflight (mocked `subprocess`).
- Dry-run test of `scripts/nas/deploy-services.sh`.
- Live acceptance on the NAS: first `dotfiles` run with backups verified, `run.py doctor` green on the NAS, one service
  deployed from the laptop and one via CI.

## Open questions (resolved during planning)

1. Hatch portable config location (decides the `python` package split).
2. The NAS's actual SSH endpoint (port 22 refused on the LAN address during the 2026-10-31 probe; Tailscale SSH or a
   non-default port are both possible).
3. Exact Homebrew-on-Linux prerequisite package list for the current Debian release.
4. Whether Homebrew is preinstalled on `ubuntu-latest` runners (affects the Brewfile-evaluation test setup).
5. Which formulae in the base Brewfile are macOS-only beyond casks and `mas` (audit during sub-project 1).
