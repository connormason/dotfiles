# Connor's Dotfiles

Personal dotfiles repository. A layered stow engine plus `bootstrap/` stage scripts configure macOS; Ansible configures
the home NAS (Debian Linux) and its Docker media-server / home-automation stack.

<!-- mdformat-toc start --slug=github --maxlevel=3 --minlevel=2 -->

- [Quick Start](#quick-start)
  - [Personal Mac Bootstrapping](#personal-mac-bootstrapping)
  - [NAS Bootstrapping](#nas-bootstrapping)
- [Architecture Overview](#architecture-overview)
  - [macOS: stow engine and bootstrap stages](#macos-stow-engine-and-bootstrap-stages)
  - [NAS/Server Configuration (`nas_bootstrap.yml`)](#nasserver-configuration-nas_bootstrapyml)
  - [Core Components](#core-components)
- [Documentation](#documentation)
  - [Configuration Files](#configuration-files)
- [Common Operations](#common-operations)
  - [Inventory Management](#inventory-management)
  - [Repository Management](#repository-management)
  - [Layered Dev Environment (macOS)](#layered-dev-environment-macos)
  - [Ansible Playbook Execution (NAS)](#ansible-playbook-execution-nas)
  - [Using Make Targets](#using-make-targets)
- [Project Structure](#project-structure)
- [Key Features](#key-features)
  - [Layered Dev Environment (macOS)](#layered-dev-environment-macos-1)
  - [Security Features](#security-features)
  - [Docker Media Stack (NAS)](#docker-media-stack-nas)
  - [Python CLI (`run.py`)](#python-cli-runpy)
- [Development Workflow](#development-workflow)
  - [Adding a Dotfile or Tool (macOS)](#adding-a-dotfile-or-tool-macos)
  - [Adding Applications (macOS)](#adding-applications-macos)
  - [Adding Services (NAS)](#adding-services-nas)
  - [Creating New Roles](#creating-new-roles)
  - [Testing Changes](#testing-changes)
- [Environment Variables](#environment-variables)
- [Troubleshooting](#troubleshooting)
  - [Inventory Issues](#inventory-issues)
  - [Vault Password Issues](#vault-password-issues)
  - [Homebrew Checksum Mismatch](#homebrew-checksum-mismatch)
  - [Role Failures](#role-failures)
- [Pre-commit Hooks](#pre-commit-hooks)
- [Related Projects](#related-projects)
- [License](#license)
- [Author](#author)

<!-- mdformat-toc end -->

## Quick Start<a name="quick-start"></a>

### Personal Mac Bootstrapping<a name="personal-mac-bootstrapping"></a>

1. Download password manager from the Mac App Store
2. Login to github.com from browser
3. Setup SSH keys with Github
   - Generate SSH key in terminal: `ssh-keygen -t ed25519 -C "your_email@example.com"`
   - Start SSH agent: `eval "$(ssh-agent -s)"`
   - Add SSH key to ssh-agent: `ssh-add --apple-use-keychain ~/.ssh/id_ed25519`
   - Copy SSH key to clipboard: `pbcopy < ~/.ssh/id_ed25519.pub`
   - Add SSH key to github.com account
4. Clone dotfiles repo: `git clone git@github.com:connormason/dotfiles-personal.git`
5. Run the bootstrap driver (preview first with `--dry-run`, list the stages with `--list`)
   - `cd dotfiles-personal`
   - `bootstrap/bootstrap.sh`

The driver runs the numbered stages in [`bootstrap/`](bootstrap/README.md) (preflight, SSH key, Homebrew, macOS
preferences, VS Code extensions, repos, Python tools, stow, iTerm2, rendered settings) and is resumable with `--resume`.
Machine-specific additions come from [`profiles/`](profiles/README.md) overlays registered on that machine.

### NAS Bootstrapping<a name="nas-bootstrapping"></a>

1. Pull inventory repository: `python3 run.py update-inventory`
2. Create file `vault_password.txt` in the repo root and paste in the Ansible Vault password from password manager
3. Run bootstrapping script
   - `chmod u+x nas_bootstrap.sh`
   - `./nas_bootstrap.sh`
4. Point router DNS at NAS for PiHole

## Architecture Overview<a name="architecture-overview"></a>

Two independent mechanisms, one per environment:

### macOS: stow engine and bootstrap stages<a name="macos-stow-engine-and-bootstrap-stages"></a>

- **[`stow/`](stow/README.md)** holds stow packages (one directory per tool); `stow.sh` links them into `$HOME` with
  `--no-folding`, aborting before any change if a conflict is unresolvable.
- **[`bootstrap/`](bootstrap/README.md)** is a layered, resumable driver that runs numbered stage scripts and installs
  the Brewfile, VS Code extensions, repos, and uv tools.
- **[`render/`](render/)** holds per-layer JSON fragments that `scripts/dotfiles/render.py` merges into settings files
  that apps rewrite at runtime (see [`scripts/dotfiles/`](scripts/dotfiles/README.md)).
- **[`profiles/`](profiles/README.md)** holds per-machine overlays that follow the same layout and are registered in
  `~/.config/dotfiles/overlays`.

### NAS/Server Configuration (`nas_bootstrap.yml`)<a name="nasserver-configuration-nas_bootstrapyml"></a>

Configures the home NAS server with:

- **Storage**: ZFS filesystem management
- **File sharing**: Samba (SMB/CIFS)
- **Media stack**: Plex, Sonarr, Radarr, Transmission, Prowlarr (via Docker)
- **Network services**: PiHole DNS/ad-blocking, Tailscale
- **Home automation**: Home Assistant, Glance dashboard
- **Base system**: Debian packages, git, ssh, zsh

### Core Components<a name="core-components"></a>

| Directory / file           | Purpose                                                 | Documentation                                            |
| -------------------------- | ------------------------------------------------------- | -------------------------------------------------------- |
| [`bootstrap/`](bootstrap/) | Layered stage driver and install manifests (macOS)      | [bootstrap/README.md](bootstrap/README.md)               |
| [`stow/`](stow/)           | Stow packages linked into `$HOME` (macOS)               | [stow/README.md](stow/README.md)                         |
| [`profiles/`](profiles/)   | Per-machine overlays                                    | [profiles/README.md](profiles/README.md)                 |
| [`render/`](render/)       | Settings fragments merged by `render.py`                | [scripts/dotfiles/README.md](scripts/dotfiles/README.md) |
| [`scripts/`](scripts/)     | Render tool, prek hooks, utilities                      | [scripts/hooks/README.md](scripts/hooks/README.md)       |
| [`playbooks/`](playbooks/) | NAS Ansible playbook and execution guide                | [playbooks/README.md](playbooks/README.md)               |
| [`roles/`](roles/)         | Ansible roles for the NAS                               | [roles/README.md](roles/README.md)                       |
| [`services/`](services/)   | Docker Compose definitions for the NAS stack            | [services/README.md](services/README.md)                 |
| [`docs/`](docs/)           | Extended documentation, notes, and plans                | [docs/README.md](docs/README.md)                         |
| [`run.py`](run.py)         | Python CLI for repository management                    | [docs/RUN_PY_REFERENCE.md](docs/RUN_PY_REFERENCE.md)     |
| `inventory/`               | Host definitions and encrypted vault files (gitignored) | Managed via `run.py update-inventory`                    |

## Documentation<a name="documentation"></a>

- **[Python CLI Reference](docs/RUN_PY_REFERENCE.md)** - complete `run.py` command reference (inventory management,
  codebase maintenance, the layered dev-environment commands)
- **[Bootstrap](bootstrap/README.md)** - stage list, overlay contract, manifests
- **[Stow packages](stow/README.md)** - what each package configures
- **[Profiles](profiles/README.md)** - per-machine overlays
- **[Playbook Workflows](playbooks/README.md)** - NAS playbook execution, tags, troubleshooting
- **[Ansible Roles](roles/README.md)** - NAS role set and how to add one
- **[Docker Role](roles/docker/README.md)** - NAS media stack architecture, storage layout, service management

### Configuration Files<a name="configuration-files"></a>

- **`.pre-commit-config.yaml`** - Code quality hooks (Python, YAML, JSON validation)
- **`.yamllint.yaml`** - YAML linting rules
- **`.ansible-lint.yaml`** - Ansible best practices
- **`vault_password.txt`** - Ansible Vault password (gitignored, create manually)
- **`roles/requirements.yml`** - External Ansible collection dependencies

## Common Operations<a name="common-operations"></a>

### Inventory Management<a name="inventory-management"></a>

The inventory repository is a separate private git repository containing host definitions and Ansible Vault encrypted
secrets. It is managed as a standalone clone in the `inventory/` directory.

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

**Important notes:**

- The `inventory/` directory is gitignored in the main repository
- `run.py update-inventory` clones from `git@github.com:connormason/dotfiles-inventory.git`
- SSH authentication to GitHub is required for inventory operations
- Vault password must be in `vault_password.txt` for playbook execution

### Repository Management<a name="repository-management"></a>

```bash
# List available hosts
python3 run.py list-hosts

# Update inventory from remote
python3 run.py update-inventory

# Clean build artifacts
python3 run.py clean

# Run prek hooks
python3 run.py pre

# Generate Makefile from run.py commands
python3 run.py makefile
```

### Layered Dev Environment (macOS)<a name="layered-dev-environment-macos"></a>

```bash
# Run the bootstrap stages (--list, --dry-run, --resume, --verify are available)
bootstrap/bootstrap.sh

# Link stow packages into $HOME (-n previews without writing)
./stow.sh -n

# Verify tools, overlay registry, links, and rendered settings
python3 run.py doctor
```

See [docs/RUN_PY_REFERENCE.md](docs/RUN_PY_REFERENCE.md) for the corresponding `run.py` wrappers.

### Ansible Playbook Execution (NAS)<a name="ansible-playbook-execution-nas"></a>

```bash
# Full NAS bootstrap
ansible-playbook playbooks/nas_bootstrap.yml -i inventory/inventory.yml --ask-become-pass -vv

# Update specific role
ansible-playbook playbooks/nas_bootstrap.yml -i inventory/inventory.yml --ask-become-pass --tags git -vv

# Update only Docker stack
ansible-playbook playbooks/nas_bootstrap.yml -i inventory/inventory.yml --ask-become-pass --tags docker -vv
```

### Using Make Targets<a name="using-make-targets"></a>

```bash
# Generate Makefile
python3 run.py makefile

# Use make for any run.py command
make help
make update-inventory
make clean
make pre
```

## Project Structure<a name="project-structure"></a>

```
dotfiles-personal/
├── run.py                                  # Python CLI for repository management
├── stow.sh                                 # Links stow packages into $HOME
├── nas_bootstrap.sh                        # NAS bootstrap script
├── Makefile                                # Auto-generated from run.py commands
│
├── bootstrap/                              # macOS stage driver, stages, and install manifests
├── stow/                                   # Stow packages (one directory per tool)
├── render/                                 # Settings fragments merged by render.py
├── profiles/                               # Per-machine overlays
│
├── playbooks/                              # Ansible playbooks
│   └── nas_bootstrap.yml                   # NAS configuration playbook
│
├── roles/                                  # Ansible roles (NAS)
│   ├── debian/                             # Debian system packages
│   ├── docker/                             # Docker media stack
│   ├── zfs/                                # ZFS filesystem
│   ├── samba/                              # File sharing
│   ├── git/                                # Git configuration
│   ├── ssh/                                # SSH key generation
│   ├── tailscale/                          # Tailscale VPN
│   ├── zsh/                                # Shell configuration
│   └── requirements.yml                    # External collection dependencies
│
├── services/                               # Docker Compose definitions for the NAS stack
│
├── inventory/                              # Standalone git repository (private)
│   ├── inventory.yml                       # Host definitions
│   ├── group_vars/                         # Group variables and vault files
│   └── host_vars/                          # Host-specific variables and vault files
│
├── scripts/                                # Utility scripts
│   ├── dotfiles/                           # render.py
│   ├── hooks/                              # Custom prek hook scripts
│   └── utility/                            # Helper scripts
│
├── tests/                                  # Unit and integration tests
│
├── docs/                                   # Documentation
│   ├── RUN_PY_REFERENCE.md                 # Python CLI reference
│   ├── notes/                              # Informal working notes
│   └── plans/                              # Design docs & implementation plans (YYYY-MM/)
│
├── .ctx/                                   # On-demand Claude reference docs (architecture, build, conventions)
├── .ansible-lint.yaml                      # Ansible linting rules
├── .yamllint.yaml                          # YAML linting rules
├── .pre-commit-config.yaml                 # prek / pre-commit hook configuration
├── CLAUDE.md                               # Claude Code project instructions
└── CLAUDE-LESSONS.md                       # Captured rules to prevent recurring mistakes
```

## Key Features<a name="key-features"></a>

### Layered Dev Environment (macOS)<a name="layered-dev-environment-macos-1"></a>

- **Stow packages** linked with `--no-folding`, all-or-nothing, with conflict backup to `~/.dotfiles-backup/`
- **Resumable stage driver** with `--dry-run`, `--only`, `--from`, `--resume`, and `--verify`
- **Overlays** add stages, stow packages, render fragments, and manifest entries without touching the base layer

### Security Features<a name="security-features"></a>

- **Ansible Vault encryption** for all NAS secrets (passwords, API keys, tokens)
- **Homebrew installer checksum verification** in the bootstrap scripts
- **SSH key-based authentication** for remote host management
- **Gitignored sensitive files** (vault_password.txt, decrypted secrets)

### Docker Media Stack (NAS)<a name="docker-media-stack-nas"></a>

Comprehensive media server and home automation:

- **Media services**: Plex, Sonarr, Radarr, Transmission, Prowlarr, Flaresolverr
- **Network services**: PiHole (DNS/ad-blocking)
- **Automation**: Home Assistant, Glance dashboard
- **Support**: Autoplex (automated file organization)

### Python CLI (`run.py`)<a name="python-cli-runpy"></a>

Feature-rich command-line interface:

- **Command registration** via decorator pattern
- **ANSI styling** for rich terminal output
- **Retry logic** with exponential backoff for network operations
- **Shell command execution** with live output via PTY
- **Auto-generated Makefile** from registered commands

## Development Workflow<a name="development-workflow"></a>

### Adding a Dotfile or Tool (macOS)<a name="adding-a-dotfile-or-tool-macos"></a>

Add or extend a package under `stow/<package>/` using the `$HOME`-relative path of each file, then run `./stow.sh -n` to
preview the links. Add the package to the table in [stow/README.md](stow/README.md); a test fails if the table and the
directories disagree.

### Adding Applications (macOS)<a name="adding-applications-macos"></a>

Edit the manifests in [`bootstrap/`](bootstrap/README.md#manifests): CLI tools and apps in `Brewfile`, extensions in
`vscode-extensions.txt`, uv tools in `uv-tools.txt`. Machine-specific apps belong in a profile overlay.

### Adding Services (NAS)<a name="adding-services-nas"></a>

Add a `services/<name>/compose.yml` (see [services/README.md](services/README.md)) and see
[roles/docker/README.md](roles/docker/README.md) for the deployment flow.

### Creating New Roles<a name="creating-new-roles"></a>

See [roles/README.md](roles/README.md#adding-a-role).

### Testing Changes<a name="testing-changes"></a>

```bash
# Run the test suite through the public-index uv wrapper
python3 run.py test

# Run prek hooks
python3 run.py pre

# Syntax-check the NAS playbook
ansible-playbook --syntax-check -i localhost, playbooks/nas_bootstrap.yml
```

## Environment Variables<a name="environment-variables"></a>

| Variable                      | Purpose                       | Default                                             |
| ----------------------------- | ----------------------------- | --------------------------------------------------- |
| `DOTFILES_RUN_DEBUG`          | Enable debug output in run.py | `false`                                             |
| `DOTFILES_INVENTORY_REPO_URL` | Inventory repository URL      | `git@github.com:connormason/dotfiles-inventory.git` |

## Troubleshooting<a name="troubleshooting"></a>

### Inventory Issues<a name="inventory-issues"></a>

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

### Vault Password Issues<a name="vault-password-issues"></a>

1. Verify `vault_password.txt` exists in repository root
2. Ensure file contains correct password
3. Check file permissions: `chmod 600 vault_password.txt`

### Homebrew Checksum Mismatch<a name="homebrew-checksum-mismatch"></a>

1. Verify if Homebrew installer was legitimately updated at https://github.com/Homebrew/install
2. Generate new checksum:
   `curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh | shasum -a 256`
3. Update the checksum constant in the script that failed: `EXPECTED_CHECKSUM` in `nas_bootstrap.sh`, or
   `BREW_INSTALLER_SHA256` in `bootstrap/50-brew.sh`

### Role Failures<a name="role-failures"></a>

1. Check verbose output for specific error
2. Run specific role with extra verbosity: `-vvv`
3. Check role-specific README for troubleshooting
4. Verify required variables are set in inventory

See [playbooks/README.md](playbooks/README.md#troubleshooting) for comprehensive troubleshooting guide.

## Pre-commit Hooks<a name="pre-commit-hooks"></a>

Configured checks include:

- **File integrity**: Large files, merge conflicts, private keys, symlinks
- **Python**: AST validation, debug statements, ruff linting, mypy type checking, interrogate docstring coverage
- **Data formats**: JSON, YAML, TOML, XML validation
- **YAML**: yamllint with custom config
- **Fixers**: Whitespace, line endings, UTF-8 BOM

Run hooks:

```bash
# All files
prek run --all-files

# Or via script
python3 run.py pre
```

## Related Projects<a name="related-projects"></a>

- **GNU Stow**: https://www.gnu.org/software/stow/
- **Ansible**: https://docs.ansible.com/
- **Homebrew**: https://brew.sh/
- **Claude Code**: https://claude.com/claude-code
- **Home Assistant**: https://www.home-assistant.io/
- **Docker**: https://www.docker.com/

## License<a name="license"></a>

Personal configuration - not licensed for reuse.

Third-party files are under their own licenses; see [NOTICE](NOTICE).

## Author<a name="author"></a>

Connor Mason
