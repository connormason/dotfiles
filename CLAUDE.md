# CLAUDE.md

Personal dotfiles repository using **Ansible** for automated system configuration on macOS and Debian Linux. Manages
dotfiles, applications, system settings, and home infrastructure (a NAS with a media-server / home-automation stack).

For detailed reference, load on-demand:

- [`.ctx/ARCHITECTURE.md`](.ctx/ARCHITECTURE.md) — bootstrap flow, inventory, role system, `run.py`, Docker stack, macOS layers
- [`.ctx/BUILD.md`](.ctx/BUILD.md) — full command reference (playbooks / `run.py` / make / pre-commit / lint)
- [`.ctx/CONVENTIONS.md`](.ctx/CONVENTIONS.md) — code style pointers and the "adding a dotfile / role / macOS app" patterns
- [`.claude/rules/`](.claude/rules) — self-contained Python / script / README style rules for this repo
- [`CLAUDE-LESSONS.md`](CLAUDE-LESSONS.md) — captured mistakes and rules to prevent recurrence; append new lessons here

## Entry Points

1. **`local_bootstrap.sh`** → `playbooks/local_bootstrap.yml` — personal Mac configuration.
2. **`nas_bootstrap.sh`** → `playbooks/nas_bootstrap.yml` — home NAS / server configuration.
3. **`run.py`** — repository-management CLI (inventory pull, tool installers, codebase chores). `Makefile` wraps these
   (`make help`). Full command reference in [`docs/RUN_PY_REFERENCE.md`](docs/RUN_PY_REFERENCE.md).

Both bootstrap scripts validate the repo, install Homebrew (checksum-verified) and Ansible, then run their playbook. See
[`.ctx/ARCHITECTURE.md`](.ctx/ARCHITECTURE.md) for the flow and [`.ctx/BUILD.md`](.ctx/BUILD.md) for invocation
(tags / extra-vars).

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
