# Architecture

Directory layout, key components, and provisioning flow for the dotfiles repository. Loaded on demand from
[`CLAUDE.md`](../CLAUDE.md).

## Two Provisioning Systems

- **macOS** — the stow engine and `bootstrap/` stage scripts. Entry point: `bootstrap/bootstrap.sh`.
- **NAS** — Ansible. Entry point: `nas_bootstrap.sh` → `playbooks/nas_bootstrap.yml`.

The retired Ansible macOS setup survives as a frozen, unmaintained snapshot in `archive/ansible-macos/` (reference only;
skipped by the lint tooling).

`nas_bootstrap.sh`:

1. Validates repository structure
2. Installs Homebrew with checksum verification
3. Installs Ansible via Homebrew
4. Executes the NAS playbook

## Stow Engine and Bootstrap Stages (macOS + Linux)

Layered: the repo root is the base layer; machine-specific overlays (see `profiles/`) are directories listed in the
overlays registry (`~/.config/dotfiles/overlays`, or `$DOTFILES_OVERLAYS_FILE`). Layers are ordered base first, then
overlays in file order. Full contract in [`bootstrap/README.md`](../bootstrap/README.md).

- **`bootstrap/bootstrap.sh`**: discovers numbered stage scripts (`NN-*.sh`) in every layer's `bootstrap/` directory,
  merges them by number, and runs each as a separate bash process. Flags: `--dry-run`, `--list`, `--only`, `--from`,
  `--resume`, `--verify`, `--no-log`. Shared helpers live in `bootstrap/lib.sh`.
- **Stages** (base): `00-preflight`, `20-ssh-key`, `50-brew`, `60-macos`, `72-vscode`, `80-repos`, `90-python`,
  `95-dotfiles`, `96-iterm2`, `97-render`.
- **Manifests**: `bootstrap/Brewfile`, `vscode-extensions.txt`, `repos.txt`, `uv-tools.txt`; each stage reads the base
  copy then every overlay's copy.
- **`stow.sh`**: links every layer's `stow/<package>/` into `$HOME` with `--no-folding`. All-or-nothing: layers are
  simulated first and unresolvable conflicts abort with nothing changed; `--backup-conflicts` moves blocking files to
  `~/.dotfiles-backup/<timestamp>/`. Package inventory: [`stow/README.md`](../stow/README.md).
- **`scripts/dotfiles/render.py`**: renders JSON settings files that apps rewrite at runtime (`render/<target>.json`
  fragments merged across layers, with a drift guard).
- **`run.py doctor`**: verifies tools, overlay registry, links, and rendered settings.
- **`profiles/`**: per-machine overlays; see [`profiles/README.md`](../profiles/README.md).
- **OS support**: `lib.sh` `dotfiles_os` (`darwin`/`linux`, `DOTFILES_OS` override) and `require_os` gate stages;
  `.dotfiles-os` markers scope stow packages; `render.py` `TARGET_OS` scopes render targets; the Brewfile's
  `if OS.mac?` block holds macOS-only entries. Linux means Debian-family with Linuxbrew; the engine never runs `apt` or
  `sudo` there (root-level setup is the NAS Ansible's job). Contract in [`bootstrap/README.md`](../bootstrap/README.md).

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
├── inventory.yml             # Host definitions
├── group_vars/
│   └── all/vault.yml         # Shared secrets
└── host_vars/
    └── nas/
        ├── vars.yml          # NAS-specific variables
        └── vault.yml         # NAS-specific secrets
```

## Role System (NAS)

Ansible roles, all run by `playbooks/nas_bootstrap.yml`:

**Linux system roles**:

- `debian`: System packages and configuration
- `docker`: Docker setup with compose stack (Plex, Sonarr, Radarr, PiHole, etc.)
- `zfs`: ZFS filesystem configuration
- `samba`: File sharing setup

**User and network roles**:

- `git`: Git configuration
- `ssh`: SSH key generation
- `zsh`: Shell configuration
- `tailscale`: Tailscale VPN setup

## Python Management Script (`run.py`)

`run.py` provides a CLI interface to repository operations.

**Command categories**:

- **Inventory**: `list-hosts`, `update-inventory`
- **Codebase**: `clean`, `pre`, `makefile`
- **Layered dev environment**: `bootstrap`, `stow`, `render`, `doctor`, `test`

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
- **Automation**: Glance dashboard (Home Assistant OS runs as a libvirt VM, provisioned by `vms/haos/` scripts)
- **Support**: Autoplex (automated file organization)

**Storage paths**: `/storage/media/*` mounted into containers

## Key Configuration Files

- **`.pre-commit-config.yaml`**: Code quality hooks
- **`.yamllint.yaml`**: YAML linting rules
- **`.ansible-lint.yaml`**: Ansible best practices
- **`ansible.cfg`**: Ansible defaults (`roles_path`, `vault_password_file`)
- **`vault_password.txt`**: Ansible Vault password (gitignored, create manually)
- **`roles/requirements.yml`**: External Ansible collection dependencies

## Bootstrap Script Security

- Homebrew installer pinned to an upstream commit URL and checksum-verified before execution (`nas_bootstrap.sh`,
  `bootstrap/50-brew.sh`; a test keeps the two pins identical)
- To update, put a commit SHA from the upstream history of `install.sh` in the URL, then take the SHA-256 of that exact
  URL: `curl -fsSL https://raw.githubusercontent.com/Homebrew/install/<commit-sha>/install.sh | shasum -a 256`
