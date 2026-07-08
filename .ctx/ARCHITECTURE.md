# Architecture

Directory layout, key components, and provisioning flow for the dotfiles-personal repository. Loaded on demand from
[`CLAUDE.md`](../CLAUDE.md).

## Dual Bootstrap System

Two separate bootstrap workflows targeting different environments:

- **`local_bootstrap.sh`** → `playbooks/local_bootstrap.yml`: Personal Mac configuration
- **`nas_bootstrap.sh`** → `playbooks/nas_bootstrap.yml`: Home NAS/server configuration

Both scripts:

1. Validate repository structure
2. Install Homebrew with checksum verification
3. Install Ansible via Homebrew
4. Execute corresponding Ansible playbook

## Inventory Management

- **Primary inventory**: `inventory/` (standalone git clone, managed by `run.py`)
- **Repository**: Cloned from `git@github.com:connormason/dotfiles-inventory.git`
- **Contains**: Host definitions, encrypted vault files for secrets
- **Setup command**: `python3 run.py update-inventory` (clones if missing, pulls if exists)
- **Recovery**: `python3 run.py update-inventory --force` (removes and re-clones if corrupted)
- **Vault password**: Stored in `vault_password.txt` (gitignored, must be created manually)

**Note**: The inventory is NOT a git submodule. It is a separate git repository cloned into the `inventory/` directory
by `run.py`. This simplifies the mental model for personal dotfiles while maintaining version control. The directory is
excluded from the main repository via `.gitignore`.

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

## Role System

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
- `tailscale`: Tailscale VPN setup
- `link_dotfile`: Reusable role for symlinking dotfiles

## link_dotfile Role Pattern

Reusable role for safely creating dotfile symlinks:

- Validates source exists
- Creates parent directories
- Backs up existing non-symlink files (with timestamp)
- Only updates if symlink missing or pointing to wrong target

Usage details and the include-role snippet live in [`CONVENTIONS.md`](CONVENTIONS.md) "Adding a New Dotfile".

## Python Management Script (`run.py`)

`run.py` provides a CLI interface to repository operations.

**Command categories**:

- **Inventory**: `list-hosts`, `update-inventory`
- **Tool Installation**: `install-uv`, `install-hatch`
- **Codebase**: `clean`, `pre`, `makefile`

**Key features**:

- Type-annotated with full typing support
- ANSI styling via a custom `style()` function
- Command registration via the `@command` decorator
- Auto-generates the `Makefile` from registered commands
- Retry logic with exponential backoff for network operations

**Environment variables**:

- `DOTFILES_RUN_DEBUG`: Enable debug output
- `DOTFILES_INVENTORY_REPO_URL`: Override inventory repo URL

## Docker Stack (NAS)

Media server and home automation stack in `roles/docker/files/docker-compose.yml`, with per-service definitions under
`services/`:

**Services**:

- **Media**: Plex, Jellyfin, Radarr (movies), Sonarr (TV), Transmission (torrents), Prowlarr (indexer), Flaresolverr
- **Network**: PiHole (DNS/ad-blocking), Caddy (reverse proxy)
- **Automation**: Home Assistant, Glance dashboard
- **Support**: Autoplex (automated file organization)

**Storage paths**: `/storage/media/*` mounted into containers

## macOS Package Management Layers

1. **Homebrew formulae** (`brew_packages` in `roles/macos/defaults/main.yml`): CLI tools
2. **Homebrew casks** (`brew_cask_packages`): GUI applications
3. **Mac App Store** (`mas_apps`): App Store apps via the `mas` CLI

## macOS System Settings

The `macos_settings` role configures system preferences via `defaults write` commands, applied via separate task files
in `roles/macos_settings/tasks/`:

- Finder behavior and appearance
- Dock size/position/behavior
- Activity Monitor preferences
- Messages app settings
- Power management
- I/O devices (keyboard, trackpad)

## Key Configuration Files

- **`.pre-commit-config.yaml`**: Code quality hooks
- **`.yamllint.yaml`**: YAML linting rules
- **`.ansible-lint.yaml`**: Ansible best practices
- **`ansible.cfg`**: Ansible defaults (`roles_path`, `library`, `vault_password_file`)
- **`vault_password.txt`**: Ansible Vault password (gitignored, create manually)
- **`roles/requirements.yml`**: External Ansible role dependencies

## Bootstrap Script Security

- Homebrew installer checksum verified before execution (`local_bootstrap.sh`)
- Expected checksum: `b2ffbf7e7f451c6db3b5d1976fc6a9c2faecf58ee5e1dbf6e498643c91f0d3bc`
- Update the checksum when the Homebrew installer changes:
  `curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh | shasum -a 256`
