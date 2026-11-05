# Build / Test / Run

Full command reference for the dotfiles repository. Loaded on demand from [`CLAUDE.md`](../CLAUDE.md).

## Bootstrapping

```bash
# Bootstrap a Mac (stow engine + numbered stages; --dry-run previews, --list shows stages, --resume continues)
bootstrap/bootstrap.sh

# Provision the NAS (Ansible; the become password comes from the vault). nas_bootstrap.sh is a thin wrapper.
python3 run.py nas-provision --check --diff
python3 run.py nas-provision

# Deploy Compose services to the NAS (the script CI uses); --dry-run previews
python3 run.py nas-deploy glance --dry-run
python3 run.py nas-deploy glance
```

## Running Ansible Playbooks (NAS)

```bash
# Run specific tags only (system: debian,zfs,samba,docker,tailscale; $HOME: dotfiles; VM: haos; stack: services)
python3 run.py nas-provision --tags dotfiles,haos

# Extra variables, e.g. test the dotfiles role against a branch
python3 run.py nas-provision --tags dotfiles -e dotfiles_repo_version=my-branch

# Rotate per-service secrets, then restart the service
python3 run.py nas-provision --tags secrets
python3 run.py nas-deploy <svc>

# Syntax check: only parses, but Ansible still loads the vault password file, so vault_password.txt must exist or
# ANSIBLE_VAULT_PASSWORD_FILE must name any existing file
scripts/hooks/uv-public.sh run ansible-playbook --syntax-check -i localhost, playbooks/nas_bootstrap.yml
```

A role-name tag runs the whole role, whereas `configfile` and `secrets` reach only the few tasks that carry them. What
each tag selects is listed in [`playbooks/README.md`](../playbooks/README.md#tags).

## Python Script Commands (`run.py`)

**Running run.py.** Bare `python3 run.py <command>` is enough for the stdlib-only commands. `list-hosts` needs PyYAML,
so run it as `scripts/hooks/uv-public.sh run python run.py list-hosts`. The NAS commands (`nas-provision`,
`nas-deploy`) shell out through uv themselves. The global `-d/--debug` flag turns on debug output (so does
`DOTFILES_RUN_DEBUG=true`, which `--no-debug` overrides); it goes before the command:
`python3 run.py -d update-inventory`.

```bash
# List available inventory hosts (needs PyYAML: see the note above)
scripts/hooks/uv-public.sh run python run.py list-hosts

# Show the inventory clone's git state
python3 run.py inventory-status

# Update inventory from remote repository (--force first discards uncommitted changes in the clone)
python3 run.py update-inventory

# Decrypt / re-encrypt the inventory vault files in place (need vault_password.txt and ansible-vault on PATH)
python3 run.py vault-decrypt
python3 run.py vault-encrypt

# Clean build artifacts and caches
python3 run.py clean

# Run prek (pre-commit) hooks on all files
python3 run.py pre

# Install / remove the prek git hook shims
python3 run.py install-hooks
python3 run.py uninstall-hooks

# Generate Makefile from run.py commands
python3 run.py makefile
```

## Layered Dev Environment (`run.py` Dotfiles group)

Wrappers over `stow.sh`, `bootstrap/bootstrap.sh`, and `scripts/dotfiles/render.py`; see
[`docs/RUN_PY_REFERENCE.md`](../docs/RUN_PY_REFERENCE.md) for options. They are stdlib-only, so bare
`python3 run.py <command>` works (see the note above).

```bash
# Stages across all layers / simulate every stage / run them
python3 run.py bootstrap --list
python3 run.py bootstrap --dry-run
python3 run.py bootstrap --verify

# Link stow packages from every layer (-n previews, --backup-conflicts moves blockers aside)
python3 run.py stow -n
python3 run.py stow --backup-conflicts

# Render settings from per-layer fragments (--diff previews, --check exits 1 on drift)
python3 run.py render --check

# Verify tools, overlay registry, git version, links, and rendered settings (--fix repairs, then re-checks)
python3 run.py doctor
python3 run.py doctor --fix

# Run the test suite through the public-index uv wrapper
python3 run.py test
```

## Using Make (auto-generated)

`python3 run.py makefile` writes the `Makefile`: one target per registered command except the script-only `nas-deploy`,
each running `python3 run.py <command>` with no arguments. Anything that takes an option or an argument
(`nas-provision --tags ...`, `nas-deploy <svc>`, `bootstrap --list`, `stow -n`) goes through `python3 run.py`.

```bash
# Show available targets
make help

# Targets mirror the argument-less commands
make update-inventory
make clean
make pre
```

## Git Hooks (prek)

Hooks run via [prek](https://github.com/j178/prek) (a faster pre-commit reimplementation), configured in
`.pre-commit-config.yaml`. `default_install_hook_types` installs six hook types: `pre-commit`, `commit-msg`,
`post-checkout`, `post-merge`, `post-rewrite`, and `pre-push`. Hooks are ordered by `priority`: dependency syncing
(0–6) → read-only checks (10) → whitespace fixers (20–23) → formatters (30–35) → linters (40).

- **Dependency sync**: `uv-lock`, `uv-sync` (the only hook on the post-checkout / post-merge / post-rewrite stages),
  `uv-export` (requirements.txt), `sync-with-uv`, `sync-pre-commit-deps`
- **Checks**: filesystem safety, large files, merge conflicts, `check-vcs-permalinks` (VCS links must be permalinks),
  private keys, `detect-secrets`, submodule ban, shebang/executable, TOML/XML/YAML/JSON syntax, `check-json5`,
  `check-pkl`, `validate-pyproject`, Python AST/debug/test-naming
- **Leak guard** (blocks employer-internal identifiers): `check-leaks` (pre-commit, also checks the commit identity),
  `check-leaks-msg` (commit-msg), `check-leaks-push-files` and `check-leaks-push-history` (pre-push)
- **Formatters**: `keep-sorted` (priority 30); at 35, JSON (`.claude` settings via `pretty-format-json`), VS Code
  keybindings (`sort-json-array`), shell (`shfmt`), TOML (`taplo-format`), Pkl (`format-pkl`), markdown (`mdformat`;
  `.ctx/` and `docs/plans/` are excluded), Python (`ruff --fix-only`)
- **Linters** (40): `ruff check`, `mypy`, `interrogate`, `shellcheck`, `yamllint`, `ansible-lint`
- **Fixer at priority 40**: `codespell` runs with `--write-changes`, so it rewrites misspellings instead of reporting
  them

```bash
# All files
prek run --all-files

# Or via the run.py wrapper
python3 run.py pre

# Install / update, or remove, the git hook shims
python3 run.py install-hooks
python3 run.py uninstall-hooks
```

## Ansible Linting

`ansible-lint` runs as a prek hook (`prek run ansible-lint --all-files`) and as a CI job, both through
`scripts/hooks/ansible-lint.sh` (check only, offline; collections must be installed first with
`ansible-galaxy collection install -r roles/requirements.yml`). `shellcheck` is also a prek linter (priority 40).

## CI

Three workflows in `.github/workflows/`:

- **`lint.yml`** (`Lint`, on pull requests to `main`): jobs `ruff`, `mypy`, `interrogate`, `yamllint`, `ansible-lint`,
  `codespell`, `pytest (macOS)`, and `pytest (Linux)`. Both pytest jobs install the Ansible collections, run
  `uv run pytest`, then a `bootstrap/bootstrap.sh --dry-run` against a throwaway `HOME`.
- **`deploy.yml`** (`Deploy NAS Services`, on pushes to `main` that touch `services/**`, or a manual run with a
  `service` input that defaults to `all`): `detect-changes` (push only) lists the changed service directories that have
  a `compose.yml`; a change to `services/compose.base.yml` or a null `before` SHA selects every service that has one.
  `deploy-push` deploys them one at a time, and `deploy-manual` deploys the named service. Both join the tailnet as
  `tag:ci` and call `scripts/nas/deploy-services.sh`. See [`services/README.md`](../services/README.md#ci-deploys).
- **`leaks.yml`** (`gitleaks`, on pull requests, pushes, and manual runs): jobs `gitleaks` and `leak guard`. The latter
  runs `scripts/hooks/check-leaks.py` over the tracked files, the new commit messages, and the identity of every
  reachable commit.
