# Build / Test / Run

Full command reference for the dotfiles-personal repository. Loaded on demand from [`CLAUDE.md`](../CLAUDE.md).

## Running Ansible Playbooks

```bash
# Bootstrap local Mac (interactive, asks for sudo password)
chmod u+x local_bootstrap.sh && ./local_bootstrap.sh

# Bootstrap NAS server
chmod u+x nas_bootstrap.sh && ./nas_bootstrap.sh

# Run specific tags only
ansible-playbook playbooks/local_bootstrap.yml -i inventory/inventory.yml --ask-become-pass -vv --tags git,zsh

# Run with extra variables
ansible-playbook playbooks/local_bootstrap.yml -i inventory/inventory.yml --ask-become-pass -e "some_var=value"
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

# Install Python tooling
python3 run.py install-uv
python3 run.py install-hatch

# Generate Makefile from run.py commands
python3 run.py makefile
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
