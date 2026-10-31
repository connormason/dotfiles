# NAS Sub-project 2: Profile and Ansible Handoff — Design Addendum

**Date:** 2026-10-31
**Status:** Approved
**Parent design:** [2026-10-31-nas-provisioning-design.md](2026-10-31-nas-provisioning-design.md) ("Sub-project 2",
D1/D2/D7, "Error handling"). This addendum records the decisions settled before planning and the NAS facts that shaped
them; everything not mentioned here follows the parent design.

## NAS state (read-only probe, 2026-10-31)

| Fact                                                                                     | Consequence                                                                     |
| ---------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| Debian 12 (bookworm), x86_64, zsh 5.9; login shell already `/bin/zsh`                    | The `user` shell task converges immediately                                     |
| `/etc/zsh/zshrc` runs `compinit` unless `skip_global_compinit` is set                     | Already handled by `stow/shell-linux/.zshenv` (sub-project 1); no `~/.zshenv` yet |
| `~/.zshrc`, `~/.zprofile`, `~/.p10k.zsh`, `~/.gitconfig` are regular files (old roles)   | `95-dotfiles` always passes `--backup-conflicts`; no first-run flag is needed    |
| `~/.oh-my-zsh` exists (cloned by `roles/zsh`); `custom/plugins` holds only `example`    | `95-dotfiles` keeps it and adds `alias-tips` / `zsh-histdb`                      |
| Repo cloned at `~/dotfiles` (clean, `main`, SSH origin); no `~/dotfiles-personal`        | Decision 4                                                                      |
| GitHub SSH auth works with the 2023 `id_ed25519`                                         | `20-ssh-key` exits early today; decision 1 matters for a fresh or rebuilt NAS   |
| `/home/linuxbrew` (root, 0755) and `.linuxbrew` (user) exist; Linuxbrew installed Jan 2026 | `debian` role directory tasks converge; `50-brew` adopts the install           |
| `build-essential procps curl file git zsh python3` all installed                         | `debian` prerequisite task converges                                            |
| Docker from apt: `/usr/bin/docker` 29.7.2, Compose v5.4.0                                | Decision 2                                                                      |
| sudo requires a password                                                                 | `become` keeps using the vault-supplied `ansible_become_pass`                   |
| `br0` up with **192.168.68.79/22**; HAOS VM `haos` running; Docker drop-in present        | `haos` role's bridge check passes; inventory's `ansible_host: 192.168.68.74` is stale |
| User not in the `libvirt` group                                                          | The first `haos` run reports one change (`usermod -aG libvirt`)                  |
| sshd listening on :22; Tailscale up (`nas`, 100.123.182.80)                              | Ansible reaches the NAS over the LAN from the owner's terminal                  |

The Claude Code session on the work Mac cannot open LAN sockets (`connect: Operation not permitted`, a local policy on
that process, not the NAS), so every live NAS step runs from the owner's terminal and its output is handed back as a
file.

## Decisions

| #  | Question                                              | Decision                                                                                                                                                                                                                                                                                                  |
| -- | ----------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| S1 | `20-ssh-key` confirm under an unattended run          | **Warn and continue.** `BOOTSTRAP_NONINTERACTIVE=1` (set by the role) or a non-TTY stdin makes `confirm` warn and answer "no" without reading. `20-ssh-key` then generates the key if missing, prints the public key and the `gh ssh-key add` hint as warnings, and exits 0, so a fresh NAS converges in one run. |
| S2 | Linuxbrew formulae that conflict or do not fit Linux  | **`docker`, `docker-compose`, `mermaid-cli` move into `if OS.mac?`.** apt's Docker CLI and Compose plugin stay authoritative on the NAS (Linuxbrew is prepended to `PATH` and would shadow them). `mermaid-cli`'s Puppeteer/Chromium renderer needs desktop libraries a headless server lacks. `node` and `postgresql` stay shared (client binaries; nothing starts a brew service). Darwin's installed set is unchanged. |
| S3 | Change detection for the `dotfiles` and `haos` roles  | **Change ledger plus a summary line.** `lib.sh` gains `note_change MSG`, appending to `$BOOTSTRAP_CHANGES_FILE` (exported by the driver). Stages call it only on real mutations. The driver ends its summary with `bootstrap: changes=N`; under `--dry-run`, N counts would-be changes. `vms/haos/setup.sh` counts in `run()` / `write_if_changed` and prints `haos: changes=N`. Roles use `changed_when` on `changes=0`. Under `--check` the roles run the script's `--dry-run` with `check_mode: false` (the task is read-only) and report would-change honestly. |
| S4 | NAS clone location                                    | **A new `~/dotfiles-personal`** (`dotfiles_repo_dir`), matching the Macs. The old `~/dotfiles` clone is left untouched and deleted by hand after acceptance.                                                                                                                                               |

## Design deltas against the parent design

### Engine (bash 3.2, TDD)

- `lib.sh`: `note_change`, and a non-interactive `confirm` that never calls `read` without a TTY.
- Driver: creates and exports the per-run ledger and appends `bootstrap: changes=N` to the run summary.
- Change points: `20-ssh-key` (key generated); `50-brew` (Homebrew installed, legacy starship removed, `brew bundle`
  run because a `brew bundle check` pre-check was unsatisfied; a satisfied pre-check skips `brew bundle`); `80-repos`
  (clone); `90-python` (uv tool installed); `stow.sh` (anything linked or backed up); `95-dotfiles` (oh-my-zsh or a
  plugin installed); `97-render` (files written, or drift reported under `--check`).
- macOS no-op proof: the existing darwin goldens (`--list`, stow layout) stay byte-identical; the only new Mac output is
  the summary line.

### `profiles/nas`

A README only. `dotfiles_layers` requires the overlay directory to exist; NAS-only manifests are added when needed.

### `dotfiles` role

1. Safety check when `dotfiles_repo_dir` exists: fail without touching it if it has uncommitted changes, is not on
   `main`, or has commits not on `origin/main` (the git module's update would otherwise reset local work).
2. Clone or fast-forward from `https://github.com/connormason/dotfiles.git` (works on a fresh NAS without a key), then
   set `remote.origin.pushurl` to the SSH URL.
3. Write `~/.config/dotfiles/overlays` listing `<dotfiles_repo_dir>/profiles/nas` (the role owns the file).
4. Set the login shell to zsh (root).
5. Run `bootstrap.sh` as the connecting user (no `become`) with `BOOTSTRAP_NONINTERACTIVE=1`; `changed_when` on
   `bootstrap: changes=0`. Under `--check`: `--dry-run` with `check_mode: false`, skipped (with a message) when the clone
   does not exist yet.

### `haos` role

- Fails with the `sudo vms/haos/bridge.sh` instructions when `br0` has no IPv4 address, and when `setup.sh` is absent
  from the clone.
- Runs `setup.sh` as root (`--dry-run` under `--check`); `changed_when` on `haos: changes=0`.
- `setup.sh`: counter in `run()` / `write_if_changed` and on the direct `iptables -I` path; `systemctl enable --now`
  guarded by `is-enabled` / `is-active`; summary line printed before the dry-run early exit.

### Other Ansible changes

- Playbook order `debian → zfs → samba → docker → tailscale → dotfiles → haos`; `git`, `ssh`, `zsh` includes and roles
  deleted; `community.crypto` dropped from `roles/requirements.yml` if unused; `--ask-become-pass` dropped from
  `nas_bootstrap.sh`.
- `debian`: prerequisite packages, `/home/linuxbrew` (root, 0755) and `/home/linuxbrew/.linuxbrew` (user); mask/unmask
  tasks read `systemctl is-enabled` and act only on a mismatch, without the nested `sudo`.
- `zfs`: `apt-add-repository contrib` only when `contrib` is absent; cache refresh only after adding it;
  `dpkg --print-architecture` gets `changed_when: false`.
- ansible-lint enabled in prek and CI. It currently aborts on `.yamllint.yaml` (`comments-indentation` must be false),
  so that is reconciled first. Findings in touched roles are fixed; untouched roles get trivial fixes or justified
  `skip_list` entries.

### Docs (minimal; full truth-up is sub-project 4)

New role and `profiles/nas` READMEs; `roles/README.md` table; `playbooks/README.md` order; `vms/haos/README.md`
re-bootstrap section; `bootstrap/README.md` (`note_change`, `BOOTSTRAP_NONINTERACTIVE`).

## Verification

Automated: pytest for the ledger, non-interactive `confirm`, per-stage change points (stubbed tools), the driver summary
line, and `setup.sh --dry-run` under a stubbed `PATH`; Brewfile goldens; `ansible-playbook --syntax-check`;
ansible-lint; `ansible-idempotency-reviewer` on every role change.

Live, from the owner's terminal, with output saved for review:

0. Correct `ansible_host` for `nas` to `192.168.68.79` in the inventory repo (a stale fact; the MagicDNS switch remains
   sub-project 3).
1. `--check --diff`.
2. Real run (the first `brew bundle` on the NAS is slow).
3. Second run: must report `changed=0`.
4. Acceptance: Ansible-era dotfiles present under `~/.dotfiles-backup/<timestamp>/`, starship prompt, `run.py doctor`
   green, `command -v docker` is `/usr/bin/docker`; then the owner deletes `~/dotfiles`.

## Out of scope

`run.py nas-provision` / `nas-deploy`, the inventory host change to MagicDNS, the `docker` role's fresh-install sync,
and per-service secrets (sub-project 3); the documentation truth-up (sub-project 4).
