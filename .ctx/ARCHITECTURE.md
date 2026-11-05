# Architecture

Key components and provisioning flow for the dotfiles repository; the directory tree is in the "Project Structure"
section of the [README](../README.md). Loaded on demand from [`CLAUDE.md`](../CLAUDE.md).

## Two Provisioning Systems

- **macOS** — the stow engine and `bootstrap/` stage scripts. Entry point: `bootstrap/bootstrap.sh`.
- **NAS** — Ansible plus the stow engine. Entry point: `run.py nas-provision` (wrapped by `nas_bootstrap.sh`) →
  `playbooks/nas_bootstrap.yml`; services deploy with `run.py nas-deploy`.

The retired Ansible macOS setup survives as a frozen, unmaintained snapshot in `archive/ansible-macos/` (reference only;
skipped by the lint tooling).

`run.py nas-provision`:

1. Preflight: `inventory/` present, vault password file present, then `ansible_host` and `ansible_user` of the `nas`
   host resolved through `ansible-inventory` (templated values are refused; `resolve_nas_target`), and the host
   reachable over SSH
2. Installs the Ansible collections from `roles/requirements.yml`; a failed install only warns, and the playbook still
   runs with the collections already installed
3. Runs `playbooks/nas_bootstrap.yml` in the uv environment and exits with its status

`nas_bootstrap.sh` validates the repository layout and delegates to it.

## Stow Engine and Bootstrap Stages (macOS + Linux)

Layered: the repo root is the base layer; machine-specific overlays (see `profiles/`) are directories listed in the
overlays registry (`~/.config/dotfiles/overlays`, or `$DOTFILES_OVERLAYS_FILE`). Layers are ordered base first, then
overlays in file order. Full contract in [`bootstrap/README.md`](../bootstrap/README.md).

- **`bootstrap/bootstrap.sh`**: discovers numbered stage scripts (`NN-*.sh`) in every layer's `bootstrap/` directory,
  merges them by number, and runs each as a separate bash process. Flags: `--dry-run`, `--list`, `--only`, `--from`,
  `--resume`, `--verify`, `--no-log`. Shared helpers live in `bootstrap/lib.sh`.
- **Stages** (base): `00-preflight`, `20-ssh-key`, `50-brew`, `58-defaults-backup` (macOS only), `60-macos` (macOS
  only), `72-vscode` (macOS only), `80-repos`, `90-python`, `95-dotfiles`, `96-iterm2` (macOS only), `97-render`. The
  macOS-only stages call `require_os darwin`, which logs the skip and exits 0 elsewhere.
- **Manifests**: `bootstrap/Brewfile`, `vscode-extensions.txt`, `repos.txt`, `uv-tools.txt`; each stage reads the base
  copy then every overlay's copy.
- **`stow.sh`**: links every layer's `stow/<package>/` into `$HOME` with `--no-folding`. All-or-nothing: layers are
  simulated first and unresolvable conflicts abort with nothing changed; `--backup-conflicts` moves blocking files to
  `~/.dotfiles-backup/<timestamp>/`. Package inventory: [`stow/README.md`](../stow/README.md).
- **`scripts/dotfiles/render.py`**: renders JSON settings files that apps rewrite at runtime (`render/<target>.json`
  fragments merged across layers, with a drift guard).
- **`run.py doctor`**: verifies tools, the overlay registry, the git version (>= 2.36, for the per-remote `includeIf`
  identity), links, and rendered settings.
- **`profiles/`**: per-machine overlays; see [`profiles/README.md`](../profiles/README.md).
- **OS support**: `lib.sh` `dotfiles_os` (`darwin`/`linux`, `DOTFILES_OS` override) and `require_os` gate stages;
  `.dotfiles-os` markers scope stow packages; `render.py` `TARGET_OS` scopes render targets; the Brewfile's
  `if OS.mac?` block holds macOS-only entries. Linux means Debian-family with Linuxbrew; the engine never runs `apt` or
  `sudo` there (root-level setup is the NAS Ansible's job). Contract in [`bootstrap/README.md`](../bootstrap/README.md).

## Inventory Management

- **Primary inventory**: `inventory/` (standalone git clone, managed by `run.py`)
- **Repository**: Cloned from `git@github.com:connormason/dotfiles-inventory.git` (override with
  `DOTFILES_INVENTORY_REPO_URL`)
- **Contains**: Host definitions, encrypted vault files for secrets
- **Setup command**: `python3 run.py update-inventory` clones when `inventory/` is missing and runs
  `git pull origin main` when it is a git clone. A directory that is not a git repository is removed and re-cloned
  automatically.
- **Local changes**: `python3 run.py update-inventory --force` discards uncommitted changes in the clone
  (`git reset --hard HEAD`) before pulling
- **Recovery**: for a corrupted clone, remove `inventory/` and re-run `python3 run.py update-inventory`
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

Ansible roles, all run by `playbooks/nas_bootstrap.yml`, listed in playbook order (`tests/unit/test_docs_consistency.py`
fails when this list drifts from the playbook):

- `debian`: base Debian configuration, covering system packages (including the stow engine's prerequisites), the
  Linuxbrew prefix, and the systemd sleep targets
- `zfs`: adds the `contrib` apt component and installs the kernel packages, `zfs-dkms`, `zfsutils-linux`; manages no
  pools
- `samba`: Samba file sharing
- `docker`: Docker Engine and compose plugin, docker-group membership, the `~/docker` skeleton and shared `.env`, the
  autoplex image build, `deploy.sh`
- `tailscale`: Tailscale install and configuration, HTTPS certificates, and the Caddyfile Caddy reads
- `dotfiles`: `$HOME` via the stow engine: clone, `profiles/nas` overlay, login shell, `bootstrap.sh`
- `haos`: Home Assistant OS VM via `vms/haos/setup.sh` (never `bridge.sh`)
- `services`: syncs `services/` to `~/docker`, renders per-service secrets from `services/*/env.j2` (only for services
  with a `compose.yml`), runs `deploy.sh all`

## Python Management Script (`run.py`)

`run.py` provides a CLI interface to repository operations.

**Command categories** (the `group` class attribute of each `Command` subclass):

- **Inventory**: `list-hosts`, `inventory-status`, `update-inventory`, `vault-decrypt`, `vault-encrypt`
- **Codebase**: `clean`, `pre`, `install-hooks`, `uninstall-hooks`, `makefile`
- **NAS**: `nas-provision`, `nas-deploy`
- **Dotfiles** (layered dev environment): `bootstrap`, `stow`, `render`, `doctor`, `test`

**Key features**:

- Type-annotated with full typing support
- ANSI styling via a custom `style()` function
- Command registration via `Command` subclasses (auto-registered by `__init_subclass__`)
- Auto-generates the `Makefile` from registered commands; script-only commands (`nas-deploy`) get no target
- Retry logic with exponential backoff, applied only to the `update-inventory` git pull and clone (3 attempts each)

**Environment variables and flags**:

- `DOTFILES_RUN_DEBUG`: enables debug output only when set to `true` (case-insensitive)
- `-d/--debug`: global flag with the same effect; it goes before the command (`python3 run.py -d doctor`).
  `--no-debug` overrides `DOTFILES_RUN_DEBUG=true`
- `DOTFILES_INVENTORY_REPO_URL`: Override inventory repo URL

## Docker Stack (NAS)

Media server stack defined by `services/compose.base.yml` plus one `services/<name>/compose.yml` per service. The
`services` role, CI, and `run.py nas-deploy` sync them to `~/docker/` and run `deploy.sh`:

**Services**:

- **Media**: Plex, Jellyfin, Radarr (movies), Sonarr (TV), Transmission (torrents), Prowlarr (indexer), Flaresolverr
- **Network**: Caddy (reverse proxy), PiHole (DNS/ad-blocking; disabled)
- **Dashboard**: Glance
- **Support**: Autoplex (copies completed downloads into the Plex layout)
- **Home automation**: Home Assistant runs as a libvirt VM provisioned by `vms/haos/` scripts; its container
  definition is disabled

**Disabling a service**: rename its `compose.yml` to `compose.yml.disabled` (`pihole` and `homeassistant` today).
`deploy.sh`, `scripts/nas/deploy-services.sh`, and the CI workflow pick up only directories containing a `compose.yml`.
The repository change stops nothing on the NAS; see [`services/README.md`](../services/README.md).

**Storage paths**: `/storage/media/*` mounted into containers

## Key Configuration Files

- **`.pre-commit-config.yaml`**: Code quality hooks
- **`pyproject.toml`**: Project metadata, uv dependency groups (`dev`, `lint`, `test`), and tool settings (ruff, mypy,
  interrogate, codespell, mdformat, pytest, coverage)
- **`.yamllint.yaml`**: YAML linting rules
- **`.ansible-lint.yaml`**: Ansible best practices
- **`.ansible-lint-ignore`**: ansible-lint findings accepted on purpose, each with its reason
- **`ansible.cfg`**: Ansible defaults (`roles_path`, `vault_password_file`)
- **`vault_password.txt`**: Ansible Vault password (gitignored, create manually)
- **`roles/requirements.yml`**: External Ansible collection dependencies
- **`.github/workflows/{lint,deploy,leaks}.yml`**: CI: lint and tests, service deploys, leak scanning (see
  [`BUILD.md`](BUILD.md#ci))

## Bootstrap Script Security

- Homebrew installer pinned to an upstream commit URL and checksum-verified before execution (`bootstrap/50-brew.sh`)
- To update, put a commit SHA from the upstream history of `install.sh` in the URL, then take the SHA-256 of that exact
  URL: `curl -fsSL https://raw.githubusercontent.com/Homebrew/install/<commit-sha>/install.sh | shasum -a 256`
