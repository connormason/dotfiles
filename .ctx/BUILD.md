# Build / Test / Run

Full command reference for the dotfiles repository. Loaded on demand from [`CLAUDE.md`](../CLAUDE.md).

## Bootstrapping

```bash
# Bootstrap a Mac (stow engine + numbered stages; --dry-run previews, --list shows stages, --resume continues)
bootstrap/bootstrap.sh

# Bootstrap NAS server (Ansible; asks for the sudo password)
chmod u+x nas_bootstrap.sh && ./nas_bootstrap.sh
```

## Running Ansible Playbooks (NAS)

```bash
# Run specific tags only
ansible-playbook playbooks/nas_bootstrap.yml -i inventory/inventory.yml --ask-become-pass -vv --tags git,zsh

# Run with extra variables
ansible-playbook playbooks/nas_bootstrap.yml -i inventory/inventory.yml --ask-become-pass -e "some_var=value"

# Syntax check
ansible-playbook --syntax-check -i localhost, playbooks/nas_bootstrap.yml
```

## Python Script Commands (`run.py`)

```bash
# List available inventory hosts
python3 run.py list-hosts

# Update inventory from remote repository
python3 run.py update-inventory

# Clean build artifacts and caches
python3 run.py clean

# Run prek (pre-commit) hooks on all files
python3 run.py pre

# Generate Makefile from run.py commands
python3 run.py makefile
```

## Layered Dev Environment (`run.py` Dotfiles group)

Wrappers over `stow.sh`, `bootstrap/bootstrap.sh`, and `scripts/dotfiles/render.py`; see
[`docs/RUN_PY_REFERENCE.md`](../docs/RUN_PY_REFERENCE.md) for options. Prefer `scripts/hooks/uv-public.sh run python`
over bare `python3` when running them from this repo.

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

```bash
# Show available targets
make help

# All python3 run.py commands are available as make targets
make update-inventory
make clean
make pre
```

## Git Hooks (prek)

Hooks run via [prek](https://github.com/j178/prek) (a faster pre-commit reimplementation), configured in
`.pre-commit-config.yaml`. Hooks are ordered by `priority`: dependency syncing (0–6) → read-only checks (10) →
whitespace fixers (20s) → formatters (30) → linters (40).

- **Dependency sync**: `uv-lock`, `uv-sync`, `uv-export` (requirements.txt), `sync-with-uv`, `sync-pre-commit-deps`
- **Checks**: filesystem safety, large files, merge conflicts, private keys, `detect-secrets`, submodule ban,
  shebang/executable, TOML/XML/YAML/JSON syntax, `validate-pyproject`, Python AST/debug/test-naming
- **Formatters**: JSON (`.claude`), shell (`shfmt`), TOML (`taplo`), markdown (`mdformat`), Python (`ruff --fix-only`)
- **Linters**: `ruff check`, `mypy`, `interrogate`, `shellcheck`, `yamllint`, `codespell`

```bash
# All files
prek run --all-files

# Or via the run.py wrapper
python3 run.py pre

# Install / update the git hook shims
python3 run.py install-hooks
```

## Ansible Linting

`ansible-lint` (with `.ansible-lint.yaml`) is available but commented out in `.pre-commit-config.yaml`; enable when
ready. `shellcheck` is already enabled as a prek linter (priority 40).
