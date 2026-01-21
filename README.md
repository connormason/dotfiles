# Connor's Dotfiles

Personal dotfiles repository using Ansible for automated system configuration on macOS and Debian Linux systems.
Manages dotfiles, applications, system settings, and home infrastructure (NAS with media server stack).

## Quick Start

### Personal Mac Bootstrapping

1. Download password manager from the Mac App Store
2. Login to github.com from browser
3. Setup SSH keys with Github
   - Generate SSH key in terminal: `ssh-keygen -t ed25519 -C "your_email@example.com"`
   - Start SSH agent: `eval "$(ssh-agent -s)"`
   - Add SSH key to ssh-agent: `ssh-add --apple-use-keychain ~/.ssh/id_ed25519`
   - Copy SSH key to clipboard: `pbcopy < ~/.ssh/id_ed25519.pub`
   - Add SSH key to github.com account
4. Clone dotfiles repo: `git clone git@github.com:connormason/dotfiles-personal.git`
5. Pull inventory repository: `cd dotfiles-personal && python3 run.py update-inventory`
6. Create `vault_password.txt` file in dotfiles repo and paste in Ansible Vault password from password manager
7. Run bootstrapping script
   - `chmod u+x local_bootstrap.sh`
   - `./local_bootstrap.sh`

### NAS Bootstrapping

1. Pull inventory repository: `python3 run.py update-inventory`
2. Create file `vault_password.txt` in the repo root and paste in the Ansible Vault password from password manager
3. Run bootstrapping script
   - `chmod u+x nas_bootstrap.sh`
   - `./nas_bootstrap.sh`
4. Point router DNS at NAS for PiHole

## Architecture Overview

This repository implements a dual-bootstrap system targeting two distinct environments:

### macOS Configuration (`local_bootstrap.yml`)

Configures personal Mac with:
- **Development tools**: Git, Python tooling (uv, hatch, pipx), SSH, zsh with plugins
- **GUI applications**: Homebrew casks and Mac App Store apps
- **System settings**: Finder, Dock, Activity Monitor, power management
- **Window management**: Hammerspoon automation
- **Terminal**: iTerm2 and Starship prompt

### NAS/Server Configuration (`nas_bootstrap.yml`)

Configures home NAS server with:
- **Storage**: ZFS filesystem management
- **File sharing**: Samba (SMB/CIFS)
- **Media stack**: Plex, Sonarr, Radarr, Transmission, Prowlarr (via Docker)
- **Network services**: PiHole DNS/ad-blocking
- **Home automation**: Home Assistant, Glance dashboard
- **Base system**: Debian packages, git, ssh, zsh

### Core Components

| Component | Purpose | Documentation |
|-----------|---------|---------------|
| **run.py** | Python CLI for repository management | [📖 docs/RUN_PY_REFERENCE.md](docs/RUN_PY_REFERENCE.md) |
| **playbooks/** | Ansible playbooks and execution workflows | [📖 playbooks/README.md](playbooks/README.md) |
| **roles/** | Ansible roles for system configuration | [📖 roles/README.md](roles/README.md) |
| **inventory/** | Host definitions and encrypted vault files | Managed via `run.py update-inventory` |
| **cc-statusline/** | Custom Claude Code statusline | [📖 cc-statusline/README.md](cc-statusline/README.md) |

## Documentation

### User Guides

- **[Python CLI Reference](docs/RUN_PY_REFERENCE.md)** - Complete `run.py` command reference
  - Inventory management (list-hosts, update-inventory)
  - Tool installation (install-uv, install-hatch)
  - Codebase maintenance (clean, pre, makefile)
  - Architecture details and extension guide

- **[Playbook Workflows](playbooks/README.md)** - Ansible playbook execution guide
  - Bootstrap scripts with security features
  - Tag system for selective execution
  - Troubleshooting common issues
  - Best practices for development workflow

- **[Ansible Roles](roles/README.md)** - Role system overview
  - 17 roles organized by platform (macOS, Linux, Shared)
  - Role dependencies and usage patterns
  - Creating new roles
  - Common variables and testing

### Component Documentation

#### System Configuration

- **[macOS Role](roles/macos/README.md)** - Package management layers
  - Homebrew formulae (CLI tools)
  - Homebrew casks (GUI applications)
  - Mac App Store apps
  - Adding/removing applications

- **[Docker Role](roles/docker/README.md)** - NAS media stack
  - 10+ service architecture (Plex, Sonarr, Radarr, etc.)
  - Storage layout and network configuration
  - Service management and troubleshooting
  - Adding new services

- **[link_dotfile Role](roles/link_dotfile/README.md)** - Reusable dotfile linking pattern
  - Safe symlink creation with backups
  - Usage in other roles
  - Best practices

#### Developer Tools

- **[cc-statusline](cc-statusline/README.md)** - Custom Claude Code statusline
  - 15 modular components
  - 4 themes and 4 layouts
  - Customization guide
  - Development guide

- **[Installer Scripts](scripts/installers/README.md)** - Python tool installers
  - uv and hatch installation
  - Retry logic and security features
  - Extension guide

### Configuration Files

- **`.pre-commit-config.yaml`** - Code quality hooks (Python, YAML, JSON validation)
- **`.config/.yamllint.yaml`** - YAML linting rules
- **`.config/.ansible-lint.yaml`** - Ansible best practices
- **`vault_password.txt`** - Ansible Vault password (gitignored, create manually)
- **`roles/requirements.yml`** - External Ansible role dependencies

## Common Operations

### Inventory Management

The inventory repository is a separate private git repository containing host definitions and Ansible Vault encrypted secrets. It is managed as a standalone clone in the `inventory/` directory.

**Initial setup:**

```bash
# Clone inventory repository
python3 run.py update-inventory

# Create vault password file
echo "your_vault_password" > vault_password.txt
chmod 600 vault_password.txt
```

**Update inventory:**

```bash
# Pull latest inventory changes
python3 run.py update-inventory

# Force re-clone if corrupted
python3 run.py update-inventory --force
```

**Inventory structure:**

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

**Important notes:**

- The `inventory/` directory is gitignored in the main repository
- `run.py update-inventory` clones from `git@github.com:connormason/dotfiles-inventory.git`
- SSH authentication to GitHub is required for inventory operations
- Vault password must be in `vault_password.txt` for playbook execution

### Repository Management

```bash
# List available hosts
python3 run.py list-hosts

# Update inventory from remote
python3 run.py update-inventory

# Clean build artifacts
python3 run.py clean

# Run pre-commit hooks
python3 run.py pre

# Generate Makefile from run.py commands
python3 run.py makefile
```

### Ansible Playbook Execution

```bash
# Full macOS bootstrap
ansible-playbook playbooks/local_bootstrap.yml -i inventory/inventory.yml --ask-become-pass -vv

# Update specific role
ansible-playbook playbooks/local_bootstrap.yml -i inventory/inventory.yml --ask-become-pass --tags git -vv

# Update only dotfiles (skip package installation)
ansible-playbook playbooks/local_bootstrap.yml -i inventory/inventory.yml --ask-become-pass --tags configfile -vv

# Full NAS bootstrap
ansible-playbook playbooks/nas_bootstrap.yml -i inventory/inventory.yml --ask-become-pass -vv

# Update only Docker stack
ansible-playbook playbooks/nas_bootstrap.yml -i inventory/inventory.yml --ask-become-pass --tags docker -vv
```

### Using Make Targets

```bash
# Generate Makefile
python3 run.py makefile

# Use make for any run.py command
make help
make update-inventory
make clean
make pre
```

## Project Structure

```
dotfiles-personal/
├── run.py                          # Python CLI for repository management
├── local_bootstrap.sh              # macOS bootstrap script
├── nas_bootstrap.sh                # NAS bootstrap script
├── Makefile                        # Auto-generated from run.py commands
│
├── playbooks/                      # Ansible playbooks
│   ├── local_bootstrap.yml         # macOS configuration playbook
│   └── nas_bootstrap.yml           # NAS configuration playbook
│
├── roles/                          # Ansible roles
│   ├── macos/                      # macOS package management
│   ├── macos_settings/             # macOS system preferences
│   ├── macos_dock/                 # Dock configuration
│   ├── debian/                     # Debian system packages
│   ├── docker/                     # Docker media stack
│   ├── zfs/                        # ZFS filesystem
│   ├── samba/                      # File sharing
│   ├── git/                        # Git configuration
│   ├── ssh/                        # SSH configuration
│   ├── zsh/                        # Shell configuration
│   ├── starship/                   # Shell prompt
│   ├── hammerspoon/                # Window management
│   ├── iterm/                      # iTerm2 configuration
│   ├── python/                     # Python tooling
│   ├── glance/                     # Dashboard
│   ├── link_dotfile/               # Reusable dotfile linking
│   └── requirements.yml            # External role dependencies
│
├── inventory/                      # Standalone git repository (private)
│   ├── inventory.yml               # Host definitions
│   ├── group_vars/                 # Group variables and vault files
│   └── host_vars/                  # Host-specific variables and vault files
│
├── scripts/                        # Utility scripts
│   └── installers/                 # Tool installation scripts
│       ├── install_uv.py           # uv Python package manager installer
│       └── install_hatch.py        # hatch Python project manager installer
│
├── library/                        # Custom Ansible modules
│   └── configure_network_interfaces.py
│
├── cc-statusline/                  # Custom Claude Code statusline
│   ├── statusline.sh               # Main orchestration script
│   ├── components/                 # 15 modular component scripts
│   ├── themes/                     # 4 theme files
│   └── layouts/                    # 4 layout configurations
│
├── docs/                           # Documentation
│   └── RUN_PY_REFERENCE.md         # Python CLI reference
│
├── .config/                        # Tool configuration files
│   ├── .yamllint.yaml              # YAML linting rules
│   └── .ansible-lint.yaml          # Ansible linting rules
│
└── .pre-commit-config.yaml         # Pre-commit hooks configuration
```

## Key Features

### Dual Bootstrap System

Two separate bootstrap workflows targeting different environments:
- **`local_bootstrap.sh`** → `playbooks/local_bootstrap.yml`: Personal Mac configuration
- **`nas_bootstrap.sh`** → `playbooks/nas_bootstrap.yml`: Home NAS/server configuration

Both scripts:
1. Validate repository structure
2. Install Homebrew with checksum verification
3. Install Ansible via Homebrew
4. Execute corresponding Ansible playbook

### Security Features

- **Ansible Vault encryption** for all secrets (passwords, API keys, tokens)
- **Homebrew installer checksum verification** in bootstrap scripts
- **SSH key-based authentication** for remote host management
- **Gitignored sensitive files** (vault_password.txt, decrypted secrets)

### Package Management Layers (macOS)

1. **Homebrew formulae**: CLI tools (git, ripgrep, fzf, etc.)
2. **Homebrew casks**: GUI applications (iTerm2, Visual Studio Code, etc.)
3. **Mac App Store**: App Store apps via `mas` CLI (Xcode, etc.)

### Docker Media Stack (NAS)

Comprehensive media server and home automation:
- **Media services**: Plex, Sonarr, Radarr, Transmission, Prowlarr, Flaresolverr
- **Network services**: PiHole (DNS/ad-blocking)
- **Automation**: Home Assistant, Glance dashboard
- **Support**: Autoplex (automated file organization)

### Modular Role System

- **17 Ansible roles** organized by platform
- **Reusable patterns** (link_dotfile for safe symlink creation)
- **Tag-based execution** for selective role runs
- **External role dependencies** via requirements.yml

### Python CLI (`run.py`)

Feature-rich command-line interface:
- **Command registration** via decorator pattern
- **ANSI styling** for rich terminal output
- **Retry logic** with exponential backoff for network operations
- **Shell command execution** with live output via PTY
- **Auto-generated Makefile** from registered commands

### Custom Claude Code Statusline

Modular statusline system with:
- **15 components** (git, model, tokens, cost, etc.)
- **4 themes** (default, emoji, minimal, neon)
- **4 layouts** (minimal, default, full, connor)
- **Dynamic component loading** based on layout configuration

## Development Workflow

### Adding Applications (macOS)

Edit `roles/macos/defaults/main.yml`:
- CLI tools → `brew_packages`
- GUI apps → `brew_cask_packages`
- App Store apps → `mas_apps` (requires app ID)

See [roles/macos/README.md](roles/macos/README.md) for details.

### Adding Services (NAS)

Edit `roles/docker/files/docker-compose.yml` to add new containers.

See [roles/docker/README.md](roles/docker/README.md) for details.

### Creating New Roles

1. Create role directory: `roles/new-role/`
2. Add `tasks/main.yml` with role logic
3. Add `defaults/main.yml` for default variables (optional)
4. Include role in appropriate playbook
5. Add role tags for selective execution

See [roles/README.md](roles/README.md) for details.

### Testing Changes

```bash
# Run pre-commit hooks
python3 run.py pre

# Test specific role with check mode
ansible-playbook playbooks/local_bootstrap.yml \
  -i inventory/inventory.yml \
  --tags new-role \
  --check \
  -vv

# Run full playbook in check mode
ansible-playbook playbooks/local_bootstrap.yml \
  -i inventory/inventory.yml \
  --check \
  -vv
```

## Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `DOTFILES_RUN_DEBUG` | Enable debug output in run.py | `false` |
| `DOTFILES_INVENTORY_REPO_URL` | Inventory repository URL | `git@github.com:connormason/dotfiles-inventory.git` |

## Troubleshooting

### Inventory Issues

**Inventory directory not found:**
```bash
# Clone inventory repository
python3 run.py update-inventory
```

**Inventory out of sync or corrupted:**
```bash
# Force re-clone from remote
python3 run.py update-inventory --force
```

**SSH authentication errors:**
1. Verify SSH key is added to GitHub account
2. Test SSH connection: `ssh -T git@github.com`
3. Check SSH agent has key loaded: `ssh-add -l`
4. Add key to agent: `ssh-add ~/.ssh/id_ed25519`

See [run.py documentation](docs/RUN_PY_REFERENCE.md#inventory-management) for detailed troubleshooting.

### Vault Password Issues

1. Verify `vault_password.txt` exists in repository root
2. Ensure file contains correct password
3. Check file permissions: `chmod 600 vault_password.txt`

### Homebrew Checksum Mismatch

1. Verify if Homebrew installer was legitimately updated at https://github.com/Homebrew/install
2. Generate new checksum:
`curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh | shasum -a 256`
3. Update `EXPECTED_CHECKSUM` in bootstrap scripts

### Role Failures

1. Check verbose output for specific error
2. Run specific role with extra verbosity: `-vvv`
3. Check role-specific README for troubleshooting
4. Verify required variables are set in inventory

See [playbooks/README.md](playbooks/README.md#troubleshooting) for comprehensive troubleshooting guide.

## Pre-commit Hooks

Configured checks include:
- **File integrity**: Large files, merge conflicts, private keys, symlinks
- **Python**: AST validation, debug statements, ruff linting, mypy type checking, interrogate docstring coverage
- **Data formats**: JSON, YAML, TOML, XML validation
- **YAML**: yamllint with custom config
- **Fixers**: Whitespace, line endings, UTF-8 BOM

Run hooks:
```bash
# All files
pre-commit run --all-files

# Or via script
python3 run.py pre
```

## Related Projects

- **Ansible**: https://docs.ansible.com/
- **Homebrew**: https://brew.sh/
- **Claude Code**: https://claude.com/claude-code
- **Home Assistant**: https://www.home-assistant.io/
- **Docker**: https://www.docker.com/

## License

Personal configuration - not licensed for reuse.

## Author

Connor Mason
