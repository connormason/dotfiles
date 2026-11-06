# CLAUDE.md

Personal dotfiles repository. macOS is configured by a layered **stow engine** plus numbered `bootstrap/` stage scripts;
the home NAS (Debian Linux, with a media-server / home-automation stack) is configured by **Ansible**, which also hands
the user's home directory to the same stow engine (the `dotfiles` role applies the `profiles/nas` overlay).

For detailed reference, load on-demand:

- [`.ctx/ARCHITECTURE.md`](.ctx/ARCHITECTURE.md) — macOS stow/bootstrap layers, NAS bootstrap flow, inventory, role
  system, `run.py`, Docker stack
- [`.ctx/BUILD.md`](.ctx/BUILD.md) — full command reference (bootstrap / playbooks / `run.py` / make / prek / lint)
- [`.ctx/CONVENTIONS.md`](.ctx/CONVENTIONS.md) — code style pointers and the "adding a dotfile / role / macOS app"
  patterns
- [`.claude/rules/`](.claude/rules) — self-contained Python / script / README style rules for this repo
- [`CLAUDE-LESSONS.md`](CLAUDE-LESSONS.md) — captured mistakes and rules to prevent recurrence; append new lessons here

## Entry Points

1. **`bootstrap/bootstrap.sh`** — personal Mac configuration (stow packages in `stow/`, overlays in `profiles/`). It
   also runs on the NAS, where the `dotfiles` role applies the `profiles/nas` overlay.
2. **`run.py nas-provision`** → `playbooks/nas_bootstrap.yml` — home NAS / server configuration; **`run.py nas-deploy`**
   deploys Compose services. CI does the same on pushes to `main` that touch `services/`: `.github/workflows/deploy.yml`
   calls `scripts/nas/deploy-services.sh`, the script behind `nas-deploy`.
3. **`run.py`** — repository-management CLI (inventory and vault helpers, codebase chores and prek hook management
   (`run-hooks`, `prepare-hooks`, `install-hooks`), NAS provisioning and deploy, wrappers for the stow engine, and
   `track-claude` for ingesting local Claude config). `Makefile` wraps these (`make help`). Full command reference in
   [`docs/RUN_PY_REFERENCE.md`](docs/RUN_PY_REFERENCE.md).

`run.py nas-provision` checks the inventory, vault password, and SSH reachability before running the NAS playbook in the
uv environment. The Home Assistant OS VM is provisioned by the playbook's `haos` role, which runs `vms/haos/setup.sh`;
only `bridge.sh` is hand-run ([`vms/haos/`](vms/haos/README.md) has the runbook). See
[`.ctx/ARCHITECTURE.md`](.ctx/ARCHITECTURE.md) for the flows and [`.ctx/BUILD.md`](.ctx/BUILD.md) for invocation (stage
flags / tags / extra-vars).

## Inventory

Stored in a separate git repo (`git@github.com:connormason/dotfiles-inventory.git`), cloned into `inventory/` by
`python3 run.py update-inventory` — **not** a submodule, and gitignored. Contains host definitions and vault-encrypted
secrets. See [`.ctx/ARCHITECTURE.md`](.ctx/ARCHITECTURE.md) "Inventory Management" for the layout.

## Vault Password

All Ansible secrets are `ansible-vault`-encrypted in the `inventory/` clone. The password lives in `vault_password.txt`
(gitignored, created manually; referenced by `ansible.cfg`'s `vault_password_file`). Never commit the vault password or
decrypted secrets.

## Archive

[`archive/ansible-macos/`](archive/ansible-macos/README.md) is the frozen pre-stow Ansible macOS setup, kept for
reference. It is not maintained and is skipped by the lint tooling; do not edit it or treat it as active configuration.
[`archive/homeassistant/`](archive/homeassistant/README.md) likewise holds the retired YAML Home Assistant config; the
live instance is configured through the HA UI.

## Plans & Docs

Design docs and implementation plans live under [`docs/plans/<YYYY-MM>/`](docs/plans/), named
`YYYY-MM-DD-<topic>-{design,plan}.md`. Other extended docs are indexed in [`docs/README.md`](docs/README.md).
