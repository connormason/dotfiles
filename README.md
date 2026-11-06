# Connor's Dotfiles

Personal dotfiles repository. A layered stow engine plus `bootstrap/` stage scripts configure `$HOME` on macOS and on
the home NAS (Debian Linux). On the NAS, Ansible adds the system-level setup, hands `$HOME` to that engine, provisions
the Home Assistant OS VM, and deploys the Docker media stack.

<!-- mdformat-toc start --slug=github --maxlevel=3 --minlevel=2 -->

- [Quick Start](#quick-start)
  - [Personal Mac Bootstrapping](#personal-mac-bootstrapping)
  - [NAS Bootstrapping](#nas-bootstrapping)
- [Architecture Overview](#architecture-overview)
  - [Stow engine and bootstrap stages (macOS and Linux)](#stow-engine-and-bootstrap-stages-macos-and-linux)
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
4. Clone dotfiles repo: `git clone git@github.com:connormason/dotfiles.git`
5. Run the bootstrap driver (preview first with `--dry-run`, list the stages with `--list`)
   - `cd dotfiles`
   - `bootstrap/bootstrap.sh`

The driver runs the numbered stages in [`bootstrap/`](bootstrap/README.md) (preflight, SSH key, Homebrew, preference
backup, macOS preferences, VS Code extensions, repos, Python tools, stow, iTerm2, rendered settings) and is resumable
with `--resume`. Machine-specific additions come from [`profiles/`](profiles/README.md) overlays registered on that
machine.

### NAS Bootstrapping<a name="nas-bootstrapping"></a>

Prerequisite: [`uv`](https://docs.astral.sh/uv/) on the controlling machine. `run.py` runs Ansible through
`scripts/hooks/uv-public.sh`, and [`bootstrap/Brewfile`](bootstrap/Brewfile) installs it on a Mac. `./nas_bootstrap.sh`
stops with an install pointer when `uv` is missing.

The preflight and the roles also expect:

- **SSH reachability**: the `nas` host answers a non-interactive SSH probe as its `ansible_user`, so load the key into
  the agent first (`ssh-add`)
- **Literal connection values**: `ansible_host` and `ansible_user` of the `nas` host are literal in the inventory
  (templated values are refused)
- **The `br0` LAN bridge** on the NAS, created by hand. While `br0` has no IPv4 address the `haos` role fails the play,
  so the run never reaches `services`. `vms/haos/bridge.sh` creates it but lives in the NAS clone the `dotfiles` role
  makes, so a wiped NAS needs two passes: run `nas-provision` (it stops at `haos`), run
  `sudo ~/dotfiles-personal/vms/haos/bridge.sh` on the NAS from the console or `tmux`, then run `nas-provision` again in
  full (`--tags haos` alone would not deploy `services`). The [runbook](vms/haos/README.md#re-bootstrapping-a-wiped-nas)
  has the details

The inventory variables the playbook reads are listed in [`playbooks/README.md`](playbooks/README.md#nas_bootstrapyml).

1. Pull inventory repository: `python3 run.py update-inventory`
2. Create file `vault_password.txt` in the repo root and paste in the Ansible Vault password from password manager
3. Run the provisioning command (`./nas_bootstrap.sh` is a thin wrapper around it)
   - `python3 run.py nas-provision`

The system roles run first, then the `dotfiles` role hands the NAS user's `$HOME` to the stow engine, the `haos` role
provisions the Home Assistant OS VM, and the `services` role deploys the Compose stack; order and tags are in
[`playbooks/README.md`](playbooks/README.md). Manual follow-ups after the first run: router address reservation,
onboarding, and backups for the VM ([`vms/haos/README.md`](vms/haos/README.md#fresh-install)), and the URL base path in
each service's web UI ([`roles/tailscale/README.md`](roles/tailscale/README.md#post-deployment-steps)).

## Architecture Overview<a name="architecture-overview"></a>

One layered stow engine configures `$HOME`, with two entry points:

- **A Mac**: `bootstrap/bootstrap.sh` runs the engine's numbered stages directly.
- **The home NAS**: `run.py nas-provision` (wrapped by `nas_bootstrap.sh`) runs the Ansible playbook. It does the
  root-level setup, then hands the NAS user's `$HOME` to the same engine through the `dotfiles` role and the
  [`profiles/nas`](profiles/nas/README.md) overlay.

### Stow engine and bootstrap stages (macOS and Linux)<a name="stow-engine-and-bootstrap-stages-macos-and-linux"></a>

- **[`stow/`](stow/README.md)** holds stow packages (one directory per tool); `stow.sh` links them into `$HOME` with
  `--no-folding`, aborting before any change if a conflict is unresolvable.
- **[`bootstrap/`](bootstrap/README.md)** is a layered, resumable driver that runs numbered stage scripts and installs
  the Brewfile, VS Code extensions, repos, and uv tools.
- **[`render/`](render/)** holds per-layer JSON fragments that `scripts/dotfiles/render.py` merges into settings files
  that apps rewrite at runtime (see [`scripts/dotfiles/`](scripts/dotfiles/README.md)).
- **[`profiles/`](profiles/README.md)** holds per-machine overlays that follow the same layout and are registered in
  `~/.config/dotfiles/overlays`.
- **Linux (the NAS)**: the engine also runs on Debian-family Linux with Homebrew in `/home/linuxbrew/.linuxbrew`. It
  never runs `apt` or `sudo` there: macOS-only stages and stow packages skip themselves, and the root-level
  prerequisites come from the `debian` Ansible role. The contract is in
  [`bootstrap/README.md`](bootstrap/README.md#os-support).

### NAS/Server Configuration (`nas_bootstrap.yml`)<a name="nasserver-configuration-nas_bootstrapyml"></a>

Configures the home NAS server with:

- **Base system**: Debian packages and the Linuxbrew prefix (`debian` role); `$HOME` via the stow engine (`dotfiles`
  role)
- **Storage**: ZFS installation (`zfs` role); pools and datasets are not managed
- **File sharing**: Samba (SMB/CIFS)
- **Media stack**: Plex, Jellyfin, Sonarr, Radarr, Transmission, Prowlarr (via Docker Compose)
- **Network services**: Tailscale with HTTPS served through Caddy; PiHole is disabled
- **Home automation**: Home Assistant OS (libvirt VM, see [`vms/haos/`](vms/haos/README.md))
- **Dashboard**: Glance
- **Stack deployment**: the `docker` role installs Docker Engine and `deploy.sh`; the `services` role syncs
  [`services/`](services/README.md), renders per-service secrets, and deploys the stack

### Core Components<a name="core-components"></a>

| Directory / file                         | Purpose                                                                         | Documentation                                            |
| ---------------------------------------- | ------------------------------------------------------------------------------- | -------------------------------------------------------- |
| [`bootstrap/`](bootstrap/)               | Layered stage driver and install manifests (macOS and the NAS)                  | [bootstrap/README.md](bootstrap/README.md)               |
| [`stow/`](stow/)                         | Stow packages linked into `$HOME`                                               | [stow/README.md](stow/README.md)                         |
| [`profiles/`](profiles/)                 | Per-machine overlays                                                            | [profiles/README.md](profiles/README.md)                 |
| [`render/`](render/)                     | Settings fragments merged by `render.py`                                        | [render/README.md](render/README.md)                     |
| [`scripts/`](scripts/)                   | Render tool, prek hooks, tool installers, Python env scripts, NAS deploy script | [scripts/README.md](scripts/README.md)                   |
| [`scripts/codebase/`](scripts/codebase/) | Scheduled `.gitignore` refresh script and the update workflows' setup           | [scripts/codebase/README.md](scripts/codebase/README.md) |
| [`scripts/nas/`](scripts/nas/)           | Syncs `services/` to the NAS and runs `deploy.sh` (CI and `run.py nas-deploy`)  | [scripts/nas/README.md](scripts/nas/README.md)           |
| [`playbooks/`](playbooks/)               | NAS Ansible playbook and execution guide                                        | [playbooks/README.md](playbooks/README.md)               |
| [`roles/`](roles/)                       | Ansible roles for the NAS                                                       | [roles/README.md](roles/README.md)                       |
| [`services/`](services/)                 | Docker Compose definitions for the NAS stack                                    | [services/README.md](services/README.md)                 |
| [`vms/`](vms/)                           | Virtual machines on the NAS (Home Assistant OS)                                 | [vms/README.md](vms/README.md)                           |
| [`tests/`](tests/)                       | pytest suite: unit and integration tests, fixtures                              | [tests/README.md](tests/README.md)                       |
| [`archive/`](archive/)                   | Frozen reference material (retired Ansible macOS setup and YAML Home Assistant) | [archive/README.md](archive/README.md)                   |
| [`docs/`](docs/)                         | Extended documentation, notes, and plans                                        | [docs/README.md](docs/README.md)                         |
| [`run.py`](run.py)                       | Python CLI for repository management                                            | [docs/RUN_PY_REFERENCE.md](docs/RUN_PY_REFERENCE.md)     |
| `inventory/`                             | Host definitions and encrypted vault files (gitignored)                         | Managed via `run.py update-inventory`                    |

## Documentation<a name="documentation"></a>

- **[Python CLI Reference](docs/RUN_PY_REFERENCE.md)** - complete `run.py` command reference (environment and lock
  commands, hooks, inventory management, NAS provisioning and service deploys, tool installers, the layered
  dev-environment commands)
- **[Bootstrap](bootstrap/README.md)** - stage list, overlay contract, manifests
- **[Stow packages](stow/README.md)** - what each package configures
- **[Profiles](profiles/README.md)** - per-machine overlays
- **[Playbook Workflows](playbooks/README.md)** - NAS playbook execution, tags, troubleshooting
- **[Ansible Roles](roles/README.md)** - NAS role set and how to add one
- **[Docker Role](roles/docker/README.md)** - Docker Engine, `~/docker` skeleton, autoplex image, `deploy.sh`
- **[Services Role](roles/services/README.md)** - sync of `services/` to the NAS, per-service secrets, deploy
- **[dotfiles Role](roles/dotfiles/README.md)** - `$HOME` on the NAS via the stow engine
- **[haos Role](roles/haos/README.md)** - Home Assistant OS VM provisioning from the playbook
- **[Services](services/README.md)** - the NAS Compose stack: ports, storage layout, secrets, deploy routes, operations
- **[Home Assistant OS VM](vms/haos/README.md)** - runbook for the VM: bridge, install, backups, day-to-day operations
- **[NAS scripts](scripts/nas/README.md)** - `deploy-services.sh`, the script CI and `run.py nas-deploy` use to deploy

### Configuration Files<a name="configuration-files"></a>

- **`.pre-commit-config.yaml`** - prek hooks: checks, formatters, and linters (see
  [Pre-commit Hooks](#pre-commit-hooks))
- **`.yamllint.yaml`** - YAML linting rules
- **`.ansible-lint.yaml`** - Ansible best practices
- **`.ansible-lint-ignore`** - ansible-lint findings accepted on purpose, each with its reason
- **`.gitleaks.toml`** - gitleaks configuration: the default ruleset plus a repo allowlist (read by the `gitleaks` CI
  job)
- **`.secrets.baseline`** - `detect-secrets` baseline of audited findings
- **`ansible.cfg`** - Ansible defaults (`roles_path`, `vault_password_file`)
- **`pyproject.toml`** - project metadata, uv dependency groups, and tool settings (ruff, mypy, interrogate, codespell,
  mdformat, pytest)
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

# Discard uncommitted changes to tracked files in the clone (git reset --hard HEAD), then pull
python3 run.py update-inventory --force
```

**Important notes:**

- The `inventory/` directory is gitignored in the main repository
- `run.py update-inventory` clones from `git@github.com:connormason/dotfiles-inventory.git`
- SSH authentication to GitHub is required for inventory operations
- Vault password must be in `vault_password.txt` for playbook execution

### Repository Management<a name="repository-management"></a>

**Running run.py.** Bare `python3 run.py <command>` is enough for the stdlib-only commands. `inventory-hosts` needs
PyYAML, so run it as `scripts/hooks/uv-public.sh run python run.py inventory-hosts`. The NAS commands (`nas-provision`,
`nas-deploy`), the environment commands (`install`, `dev`, `lock*`), and the hooks commands (`pre`, `run-hooks`, …)
install and use uv themselves. The vault commands call `ansible-vault`, which must be on `PATH`. The global `-d/--debug`
flag turns on debug output and goes before the command: `python3 run.py -d update-inventory`. `--no-debug` turns it off
even when `DOTFILES_RUN_DEBUG=true`. `--uv-verbose` (or `DOTFILES_UV_VERBOSE=true`) turns on uv's debug logging.

```bash
# Create .venv and install dependencies (--dev adds the dev groups, --hooks the prek shims)
python3 run.py install --dev --hooks

# Environment health: python, uv, hooks, .venv (`doctor` runs the full set of checks)
python3 run.py status

# Update uv.lock / fail when it is stale / upgrade locked versions
python3 run.py lock
python3 run.py lock-check
python3 run.py lock-upgrade -P ruff

# Re-sync files derived from uv.lock (requirements.txt, pinned hook versions)
python3 run.py lock-sync

# List available hosts (needs PyYAML: see the note above)
scripts/hooks/uv-public.sh run python run.py inventory-hosts

# Show the inventory clone's git state
python3 run.py inventory-status

# Update inventory from remote
python3 run.py update-inventory

# Decrypt / re-encrypt the inventory vault files in place for editing (need vault_password.txt)
python3 run.py vault-decrypt
python3 run.py vault-encrypt

# Clean environments, build artifacts, and caches
python3 run.py clean

# Run prek hooks
python3 run.py pre

# Run hooks on specific hooks, files, or refs (hook names go before --files)
python3 run.py run-hooks mdformat --last-commit

# Prepare the hook environments ahead of the first commit
python3 run.py prepare-hooks

# Install / remove the prek git hook shims
python3 run.py install-hooks
python3 run.py uninstall-hooks

# Install uv / hatch with the bundled installers, or collect a Python environment diagnostic
python3 run.py install-uv
python3 run.py install-hatch
python3 run.py diagnose

# Generate Makefile from run.py commands
python3 run.py makefile
```

See [docs/RUN_PY_REFERENCE.md](docs/RUN_PY_REFERENCE.md) for every command and option.

### Layered Dev Environment (macOS)<a name="layered-dev-environment-macos"></a>

```bash
# Run the bootstrap stages (--list, --dry-run, --resume, --verify are available)
bootstrap/bootstrap.sh

# Link stow packages into $HOME (-n previews without writing)
./stow.sh -n

# Verify tools, python/uv/venv, overlays, git hooks, links, rendered settings, and Brewfiles
python3 run.py doctor

# Move local ~/.claude agents/commands/skills/hooks/rules into stow/claude and restow (--dry-run previews)
python3 run.py track-claude
```

See [docs/RUN_PY_REFERENCE.md](docs/RUN_PY_REFERENCE.md) for the corresponding `run.py` wrappers.

### Ansible Playbook Execution (NAS)<a name="ansible-playbook-execution-nas"></a>

```bash
# Full NAS provisioning (preflight, collections, playbook)
python3 run.py nas-provision

# Update specific role (a role-name tag runs the whole role)
python3 run.py nas-provision --tags dotfiles

# Sync services/, render per-service secrets, and redeploy the Compose stack only
python3 run.py nas-provision --tags services

# Docker Engine, the ~/docker skeleton, the autoplex image, and deploy.sh (does not deploy the stack)
python3 run.py nas-provision --tags docker

# Deploy one Compose service (or `all`) without running the playbook
python3 run.py nas-deploy glance
```

What each tag selects, including `configfile` and `secrets`, is listed in
[playbooks/README.md](playbooks/README.md#tags). `nas-deploy` syncs `services/` and runs `deploy.sh` but renders no
secrets; `--tags services` also renders them.

`--tags configfile` reaches only the `docker` role's `.env` render and `deploy.sh` copy and the `samba` role's
`smb.conf` task, plus the `always` tasks; it does not run the `dotfiles` role (the stow engine) or any other role.

Running `ansible-playbook` directly skips what `nas-provision` adds: the preflight (inventory, vault password, SSH
reachability) and the collection install. From the repository root, so `ansible.cfg` applies:

```bash
scripts/hooks/uv-public.sh run ansible-playbook playbooks/nas_bootstrap.yml -i inventory/inventory.yml -vv
```

See [Direct execution](playbooks/README.md#direct-execution) for the dry run and the syntax check.

### Using Make Targets<a name="using-make-targets"></a>

`python3 run.py makefile` writes the `Makefile`: one target per registered command except `nas-deploy`, which is
script-only. Each target runs `python3 run.py <command>` with no arguments, so anything that takes an option or an
argument (`nas-provision --tags ...`, `nas-deploy <service>`, `bootstrap --list`, `stow -n`) goes through
`python3 run.py` directly.

```bash
# Generate Makefile
python3 run.py makefile

# Run an argument-less command through make
make help
make update-inventory
make clean
make pre
```

## Project Structure<a name="project-structure"></a>

```
dotfiles/
├── run.py                                  # Python CLI for repository management
├── stow.sh                                 # Links stow packages into $HOME
├── nas_bootstrap.sh                        # Wrapper for `run.py nas-provision`
├── Makefile                                # Auto-generated from run.py commands
├── ansible.cfg                             # Ansible defaults (roles_path, vault_password_file)
├── pyproject.toml                          # Project metadata, uv dependency groups, and tool settings
├── uv.lock                                 # Locked dependencies
│
├── bootstrap/                              # Stage driver, stages, and install manifests (macOS and Linux)
├── stow/                                   # Stow packages (one directory per tool)
├── render/                                 # Settings fragments merged by render.py
├── profiles/                               # Per-machine overlays
│
├── playbooks/                              # Ansible playbooks
│   └── nas_bootstrap.yml                   # NAS configuration playbook
│
├── roles/                                  # Ansible roles (NAS), in playbook order
│   ├── debian/                             # Debian system packages and the Linuxbrew prefix
│   ├── zfs/                                # ZFS installation
│   ├── samba/                              # File sharing
│   ├── docker/                             # Docker Engine, ~/docker skeleton, autoplex image, deploy.sh
│   ├── tailscale/                          # Tailscale VPN, HTTPS certificates, Caddyfile
│   ├── dotfiles/                           # $HOME via the stow engine
│   ├── haos/                               # Home Assistant OS VM (runs vms/haos/setup.sh)
│   ├── services/                           # Compose sync, per-service secrets, deploy
│   └── requirements.yml                    # External collection dependencies
│
├── services/                               # Docker Compose definitions for the NAS stack
│
├── vms/                                    # Virtual machines on the NAS (libvirt/KVM)
│   └── haos/                               # Home Assistant OS: README.md, bridge.sh, setup.sh
│
├── archive/                                # Frozen reference material (not maintained)
│   ├── ansible-macos/                      # Retired Ansible macOS setup (snapshot of 1ef973a)
│   └── homeassistant/                      # Retired YAML Home Assistant config
│
├── inventory/                              # Standalone git repository (private)
│   ├── inventory.yml                       # Host definitions
│   ├── group_vars/                         # Group variables and vault files
│   └── host_vars/                          # Host-specific variables and vault files
│
├── scripts/                                # Utility scripts
│   ├── codebase/                           # update_gitignore.py (scheduled .gitignore refresh)
│   ├── docs_audit/                         # Deterministic per-directory README audit (`run.py docs-audit`)
│   ├── dotfiles/                           # render.py
│   ├── hooks/                              # Custom prek hook scripts
│   ├── nas/                                # deploy-services.sh (CI and `run.py nas-deploy`)
│   └── utility/                            # Helper scripts
│
├── tests/                                  # Unit and integration tests
│
├── docs/                                   # Documentation
│   ├── RUN_PY_REFERENCE.md                 # Python CLI reference
│   ├── MODEL_ROUTER.md                     # Subagent model-router hook
│   ├── licenses/                           # License texts for vendored third-party files (see NOTICE)
│   ├── notes/                              # Informal working notes
│   └── plans/                              # Design docs & implementation plans (YYYY-MM/)
│
├── .github/workflows/                      # CI: lint and tests, service deploys, leak scanning
├── .ctx/                                   # On-demand Claude reference docs (architecture, build, conventions)
├── .ansible-lint.yaml                      # Ansible linting rules
├── .ansible-lint-ignore                    # ansible-lint findings accepted on purpose
├── .gitleaks.toml                          # gitleaks configuration (default ruleset plus allowlist)
├── .secrets.baseline                       # detect-secrets baseline
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
- **Homebrew installer checksum verification** in the bootstrap engine, on macOS and the NAS (`bootstrap/50-brew.sh`)
- **SSH key-based authentication** for remote host management
- **Gitignored sensitive files** (vault_password.txt, decrypted secrets)

### Docker Media Stack (NAS)<a name="docker-media-stack-nas"></a>

Media server stack, defined in [`services/`](services/README.md):

- **Media services**: Plex, Jellyfin, Sonarr, Radarr, Transmission, Prowlarr, Flaresolverr
- **Network services**: Caddy reverse proxy serving a subset of the services over Tailscale HTTPS (the PiHole definition
  is disabled)
- **Dashboard**: Glance
- **Home automation** (outside `services/`): Home Assistant runs as a VM (see [`vms/haos/`](vms/haos/README.md))
- **Support**: Autoplex (copies completed downloads into the library trees)

### Python CLI (`run.py`)<a name="python-cli-runpy"></a>

Feature-rich command-line interface:

- **Command registration** via auto-registering `Command` classes
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

Add a `services/<name>/compose.yml` (see [services/README.md](services/README.md)), then deploy it with
`python3 run.py nas-deploy <name>`; pushes to `main` that touch the service deploy it from CI. A service that needs a
secret also ships `services/<name>/env.j2` (see [services/README.md](services/README.md#secrets)).

### Creating New Roles<a name="creating-new-roles"></a>

See [roles/README.md](roles/README.md#adding-a-role).

### Testing Changes<a name="testing-changes"></a>

```bash
# Run the test suite through the public-index uv wrapper
python3 run.py test

# Run prek hooks (python3 run.py run-hooks --last-commit for just the files of the last commit)
python3 run.py pre

# Syntax-check the NAS playbook (parses only; needs vault_password.txt, or ANSIBLE_VAULT_PASSWORD_FILE naming any
# existing file)
scripts/hooks/uv-public.sh run ansible-playbook --syntax-check -i localhost, playbooks/nas_bootstrap.yml
```

The dry run and the other direct invocations are in [playbooks/README.md](playbooks/README.md#direct-execution).

## Environment Variables<a name="environment-variables"></a>

| Variable                      | Purpose                                                     | Default                                             |
| ----------------------------- | ----------------------------------------------------------- | --------------------------------------------------- |
| `DOTFILES_RUN_DEBUG`          | Enable debug output in run.py                               | `false`                                             |
| `DOTFILES_INVENTORY_REPO_URL` | Inventory repository URL                                    | `git@github.com:connormason/dotfiles-inventory.git` |
| `NO_COLOR`                    | Disable ANSI styling in run.py output (any non-empty value) | unset                                               |
| `DOTFILES_UV_VERBOSE`         | Parsed by run.py into `UV_VERBOSE`; no command reads it yet | `false`                                             |

## Troubleshooting<a name="troubleshooting"></a>

### Inventory Issues<a name="inventory-issues"></a>

**Inventory directory not found:**

```bash
# Clone inventory repository
python3 run.py update-inventory
```

**Uncommitted local changes in the inventory clone:**

```bash
# Discard uncommitted changes to tracked files in the clone (git reset --hard HEAD), then pull
python3 run.py update-inventory --force
```

**Corrupted inventory clone:**

```bash
# From the repository root: remove the clone (this loses uncommitted edits such as decrypted vault files), then re-clone
rm -rf inventory
python3 run.py update-inventory
```

`update-inventory` already removes and re-clones an `inventory/` directory that is not a git repository.

**SSH authentication errors:**

1. Verify SSH key is added to GitHub account
2. Test SSH connection: `ssh -T git@github.com`
3. Check SSH agent has key loaded: `ssh-add -l`
4. Add key to agent: `ssh-add ~/.ssh/id_ed25519`

See [run.py documentation](docs/RUN_PY_REFERENCE.md#inventory-update-failures) for detailed troubleshooting.

### Vault Password Issues<a name="vault-password-issues"></a>

1. Verify `vault_password.txt` exists in repository root
2. Ensure file contains correct password
3. Check file permissions: `chmod 600 vault_password.txt`

### Homebrew Checksum Mismatch<a name="homebrew-checksum-mismatch"></a>

The installer is pinned to an upstream commit (URL) and verified against a SHA-256 before it runs, so a mismatch means
the download differs from the pinned content. Content at a commit-pinned URL does not change when Homebrew updates
`install.sh`, so a mismatch points to a bad or tampered download, not to an outdated pin.

Treat it as a bad download first: re-run (`bootstrap/bootstrap.sh --resume` on macOS, `python3 run.py nas-provision` for
the NAS). If the mismatch persists, do not run the installer by other means; find out why the download differs.

Re-pin only when deliberately moving to a newer upstream commit. The single pin lives in `bootstrap/50-brew.sh`:

1. Pick a commit SHA from the upstream history of `install.sh` at
   https://github.com/Homebrew/install/commits/HEAD/install.sh and put it in `BREW_INSTALLER_URL`
2. Generate the new checksum of that exact URL:
   `curl -fsSL https://raw.githubusercontent.com/Homebrew/install/<commit-sha>/install.sh | shasum -a 256`
3. Update `BREW_INSTALLER_SHA256` and the "Last updated" comment above it

### Role Failures<a name="role-failures"></a>

1. Check verbose output for specific error
2. Run the specific role with extra verbosity: `python3 run.py nas-provision --tags <role> -vvv`
3. Check role-specific README for troubleshooting
4. Verify required variables are set in inventory

See [playbooks/README.md](playbooks/README.md#troubleshooting) for comprehensive troubleshooting guide.

## Pre-commit Hooks<a name="pre-commit-hooks"></a>

Configured checks include:

- **File integrity**: Large files, merge conflicts, private keys, symlinks
- **Secrets and leaks**: `detect-secrets` against `.secrets.baseline`; the leak guard, which blocks internal identifiers
  in content, commit messages, and the git identity (see [scripts/hooks/README.md](scripts/hooks/README.md))
- **Python**: AST validation, debug statements, ruff linting, mypy type checking, interrogate docstring coverage
- **Data formats**: JSON, YAML, TOML, XML validation
- **YAML**: yamllint with custom config
- **Shell**: shellcheck linting
- **Ansible**: ansible-lint over `playbooks/` and `roles/` (check only; accepted findings are in `.ansible-lint-ignore`)
- **Formatters**: shfmt (shell), taplo (TOML), mdformat (Markdown; `.ctx/` and `docs/plans/` are excluded), ruff
  `--fix-only` (Python)
- **Fixers**: Whitespace, line endings, UTF-8 BOM, codespell (rewrites misspellings in place), and two Python fixers:
  `fix-docstring-format` (single-line docstrings become multi-line) and `format-module-section-headers` (module-level
  triple-quoted section headers become boxed `# ====` comments); see [scripts/hooks/README.md](scripts/hooks/README.md)

Run hooks:

```bash
# All files
prek run --all-files

# Or via script
python3 run.py pre

# Install / remove the git hook shims
python3 run.py install-hooks
python3 run.py uninstall-hooks
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
