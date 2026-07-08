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

# Run pre-commit hooks on all files
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

## Pre-commit Hooks

Configured in `.pre-commit-config.yaml`:

- **File integrity**: Large files, merge conflicts, private keys, symlinks
- **Python**: AST validation, debug statements, ruff linting, mypy type checking, interrogate docstring coverage
- **Data formats**: JSON, YAML, TOML, XML validation
- **YAML**: yamllint with custom config (`.yamllint.yaml`)
- **Fixers**: Whitespace, line endings, UTF-8 BOM

```bash
# All files
pre-commit run --all-files

# Or via the run.py wrapper
python3 run.py pre
```

## Ansible Linting

Commented out in the pre-commit config but available:

- `ansible-lint` with `.ansible-lint.yaml` configuration
- `shellcheck` for shell script validation
