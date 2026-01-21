# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

Personal dotfiles repository using Ansible for automated system configuration on macOS and Debian Linux systems.
Manages dotfiles, applications, system settings, and home infrastructure (NAS with media server stack).

## Architecture

### Dual Bootstrap System

Two separate bootstrap workflows targeting different environments:

- **`local_bootstrap.sh`** → `playbooks/local_bootstrap.yml`: Personal Mac configuration
- **`nas_bootstrap.sh`** → `playbooks/nas_bootstrap.yml`: Home NAS/server configuration

Both scripts:
1. Validate repository structure
2. Install Homebrew with checksum verification/
3. Install Ansible via Homebrew
4. Execute corresponding Ansible playbook

### Inventory Management

- **Primary inventory**: `inventory/` (separate git submodule)
- **Contains**: Host definitions, encrypted vault files for secrets
- **Update command**: `python3 run.py update-inventory` (pulls from `git@github.com:connormason/dotfiles-inventory.git`)
- **Vault password**: Stored in `vault_password.txt` (gitignored, must be created manually)

Inventory structure:
```
inventory/
├── inventory.yml              # Host definitions
├── group_vars/
│   ├── all/vault.yml         # Shared secrets
│   └── localhost/
│       ├── vars.yml          # Mac-specific variables
│       └── vault.yml         # Mac-specific secrets
└── host_vars/
    └── nas/
        ├── vars.yml          # NAS-specific variables
        └── vault.yml         # NAS-specific secrets
```

### Role System

Ansible roles organized by target system:

**macOS roles**:
- `macos`: Homebrew packages, cask apps, Mac App Store apps
- `macos_settings`: System preferences (Finder, Dock, Activity Monitor, etc.)
- `macos_dock`: Dock configuration
- `hammerspoon`: Window management automation
- `iterm`: iTerm2 configuration
- `python`: Python tooling (pipx, uv, hatch)
- `starship`: Shell prompt configuration

**Linux roles**:
- `debian`: System packages and configuration
- `docker`: Docker setup with compose stack (Plex, Sonarr, Radarr, PiHole, Home Assistant, etc.)
- `zfs`: ZFS filesystem configuration
- `samba`: File sharing setup

**Shared roles**:
- `git`: Git configuration and gh CLI
- `ssh`: SSH client configuration
- `zsh`: Shell configuration
- `link_dotfile`: Reusable role for symlinking dotfiles

### link_dotfile Role Pattern

Reusable role for safely creating dotfile symlinks:
- Validates source exists
- Creates parent directories
- Backs up existing non-symlink files (with timestamp)
- Only updates if symlink missing or pointing to wrong target

Usage in playbooks:
```yaml
- include_role:
    name: roles/link_dotfile
  vars:
    link_dotfile_src: "{{ dotfiles_dir }}/path/to/source"
    link_dotfile_dst: "{{ home_dir }}/.config/destination"
```

### Python Management Script

`run.py` provides CLI interface to repository operations:

**Command categories**:
- **Inventory**: `list-hosts`, `update-inventory`
- **Tool Installation**: `install-uv`, `install-hatch`
- **Codebase**: `clean`, `pre`, `makefile`

**Key features**:
- Type-annotated with full typing support
- ANSI styling via custom `style()` function
- Command registration via `@command` decorator
- Auto-generates Makefile from registered commands
- Retry logic with exponential backoff for network operations

**Environment variables**:
- `DOTFILES_RUN_DEBUG`: Enable debug output
- `DOTFILES_INVENTORY_REPO_URL`: Override inventory repo URL

## Development Commands

### Running Ansible Playbooks

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

### Python Script Commands

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

### Using Make (auto-generated)

```bash
# Show available targets
make help

# All python3 run.py commands available as make targets
make update-inventory
make clean
make pre
```

## Testing and Validation

### Pre-commit Hooks

Configured in `.pre-commit-config.yaml`:

- **File integrity**: Large files, merge conflicts, private keys, symlinks
- **Python**: AST validation, debug statements, ruff linting, mypy type checking, interrogate docstring coverage
- **Data formats**: JSON, YAML, TOML, XML validation
- **YAML**: yamllint with custom config (`.config/.yamllint.yaml`)
- **Fixers**: Whitespace, line endings, UTF-8 BOM

Run hooks:
```bash
# All files
pre-commit run --all-files

# Or via script
python3 run.py pre
```

### Ansible Linting

Commented out in pre-commit config but available:
- `ansible-lint` with `.config/.ansible-lint.yaml` configuration
- `shellcheck` for shell script validation

## Key Configuration Files

- **`.pre-commit-config.yaml`**: Code quality hooks
- **`.config/.yamllint.yaml`**: YAML linting rules
- **`.config/.ansible-lint.yaml`**: Ansible best practices
- **`vault_password.txt`**: Ansible Vault password (gitignored, create manually)
- **`roles/requirements.yml`**: External Ansible role dependencies

## Security Considerations

### Vault Management

- All secrets stored in Ansible Vault encrypted files
- Vault password required in `vault_password.txt` for playbook execution
- Never commit vault password or decrypted secrets

### Bootstrap Script Security

- Homebrew installer checksum verified before execution (local_bootstrap.sh:41)
- Checksum expected value: `b2ffbf7e7f451c6db3b5d1976fc6a9c2faecf58ee5e1dbf6e498643c91f0d3bc`
- Update checksum when Homebrew installer changes:
`curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh | shasum -a 256`

## Docker Stack (NAS)

Media server and home automation stack in `roles/docker/files/docker-compose.yml`:

**Services**:
- **Media**: Plex, Radarr (movies), Sonarr (TV), Transmission (torrents), Prowlarr (indexer), Flaresolverr
- **Network**: PiHole (DNS/ad-blocking)
- **Automation**: Home Assistant, Glance dashboard
- **Support**: Autoplex (automated file organization)

**Storage paths**: `/storage/media/*` mounted into containers

## macOS-Specific

### Package Management Layers

1. **Homebrew formulae** (`brew_packages` in `roles/macos/defaults/main.yml`): CLI tools
2. **Homebrew casks** (`brew_cask_packages`): GUI applications
3. **Mac App Store** (`mas_apps`): App Store apps via `mas` CLI

### System Settings

The `macos_settings` role configures system preferences via `defaults write` commands:
- Finder behavior and appearance
- Dock size/position/behavior
- Activity Monitor preferences
- Messages app settings
- Power management
- I/O devices (keyboard, trackpad)

Applied via separate task files in `roles/macos_settings/tasks/`.

## Common Patterns

### Adding a New Dotfile

1. Place source file in appropriate `roles/*/files/` directory
2. Use `link_dotfile` role in playbook:
```yaml
- include_role:
    name: roles/link_dotfile
  vars:
    link_dotfile_src: "{{ dotfiles_dir }}/roles/myapp/files/config"
    link_dotfile_dst: "{{ home_dir }}/.config/myapp/config"
```

### Adding a New Ansible Role

1. Create role directory: `roles/new-role/`
2. Add `tasks/main.yml` with role logic
3. Add `defaults/main.yml` for default variables (optional)
4. Include role in appropriate playbook (`local_bootstrap.yml` or `nas_bootstrap.yml`)
5. Add role tags for selective execution

### Adding macOS Applications

Edit `roles/macos/defaults/main.yml`:
- CLI tools → `brew_packages`
- GUI apps → `brew_cask_packages`
- App Store apps → `mas_apps` (requires app ID from App Store)
