# CLAUDE.md

Personal dotfiles repository. macOS is configured by a layered **stow engine** plus numbered `bootstrap/` stage scripts;
the home NAS (Debian Linux, with a media-server / home-automation stack) is configured by **Ansible**.

For detailed reference, load on-demand:

- [`.ctx/ARCHITECTURE.md`](.ctx/ARCHITECTURE.md) — macOS stow/bootstrap layers, NAS bootstrap flow, inventory, role
  system, `run.py`, Docker stack
- [`.ctx/BUILD.md`](.ctx/BUILD.md) — full command reference (bootstrap / playbooks / `run.py` / make / prek / lint)
- [`.ctx/CONVENTIONS.md`](.ctx/CONVENTIONS.md) — code style pointers and the "adding a dotfile / role / macOS app"
  patterns
- [`.claude/rules/`](.claude/rules) — self-contained Python / script / README style rules for this repo
- [`CLAUDE-LESSONS.md`](CLAUDE-LESSONS.md) — captured mistakes and rules to prevent recurrence; append new lessons here

## Entry Points

1. **`bootstrap/bootstrap.sh`** — personal Mac configuration (stow packages in `stow/`, overlays in `profiles/`).
2. **`nas_bootstrap.sh`** → `playbooks/nas_bootstrap.yml` — home NAS / server configuration.
3. **`run.py`** — repository-management CLI (inventory pull, codebase chores, wrappers for the macOS engine). `Makefile`
   wraps these (`make help`). Full command reference in [`docs/RUN_PY_REFERENCE.md`](docs/RUN_PY_REFERENCE.md).

`nas_bootstrap.sh` validates the repo, installs Homebrew (checksum-verified) and Ansible, then runs the NAS playbook.
See [`.ctx/ARCHITECTURE.md`](.ctx/ARCHITECTURE.md) for the flows and [`.ctx/BUILD.md`](.ctx/BUILD.md) for invocation
(stage flags / tags / extra-vars).

## Inventory

Stored in a separate git repo (`git@github.com:connormason/dotfiles-inventory.git`), cloned into `inventory/` by
`python3 run.py update-inventory` — **not** a submodule, and gitignored. Contains host definitions and vault-encrypted
secrets. See [`.ctx/ARCHITECTURE.md`](.ctx/ARCHITECTURE.md) "Inventory Management" for the layout.

## Vault Password

All secrets are `ansible-vault`-encrypted in the `inventory/` clone. The password lives in `vault_password.txt`
(gitignored, created manually; referenced by `ansible.cfg`'s `vault_password_file`). Never commit the vault password or
decrypted secrets.

## Plans & Docs

Design docs and implementation plans live under [`docs/plans/<YYYY-MM>/`](docs/plans/), named
`YYYY-MM-DD-<topic>-{design,plan}.md`. Other extended docs are indexed in [`docs/README.md`](docs/README.md).
