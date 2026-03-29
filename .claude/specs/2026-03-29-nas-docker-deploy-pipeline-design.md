# NAS Docker Deploy Pipeline Design

**Date:** 2026-03-29
**Status:** Approved

## Problem

Deploying Docker service config changes to a home NAS requires a manual workflow: edit locally, push to GitHub, SSH into the NAS, pull changes, restart containers. This is tedious for frequent config updates (Glance dashboards, Home Assistant automations, etc.) and error-prone.

## Goals

- **Edit, push, deploy**: pushing to `main` automatically deploys changed configs to the NAS
- **Per-service granularity**: only affected containers restart when their config changes
- **Low maintenance**: minimal moving parts, no new software on the NAS beyond what exists
- **Ansible for bootstrap only**: Ansible handles initial NAS setup and secrets, not day-to-day deploys

## Constraints

- NAS is reachable via Tailscale (not publicly exposed)
- Secrets come from Ansible Vault and are rendered during bootstrap (never stored in git)
- Home Assistant config will be consolidated from its separate repo into this one

## Design

### 1. Repository Structure

Restructure from a single `roles/docker/files/docker-compose.yml` to per-service directories:

```
services/
├── compose.base.yml              # Shared network definitions, extension fields
├── pihole/
│   ├── compose.yml               # PiHole service definition
│   └── etc-pihole/               # PiHole persistent config
├── plex/
│   └── compose.yml
├── transmission/
│   └── compose.yml
├── sonarr/
│   └── compose.yml
├── radarr/
│   └── compose.yml
├── prowlarr/
│   └── compose.yml
├── flaresolverr/
│   └── compose.yml
├── autoplex/
│   └── compose.yml
├── homeassistant/
│   ├── compose.yml
│   ├── configuration.yaml        # Consolidated from separate repo
│   ├── automations.yaml
│   ├── secrets.yaml.j2           # Template, rendered during bootstrap
│   └── ...                       # Other HA config files
└── glance/
    ├── compose.yml
    ├── config/
    │   ├── glance.yml
    │   └── home.yml
    └── assets/
        └── user.css
```

**Key decisions:**
- Each service directory contains its compose fragment and all config files it needs
- Home Assistant is consolidated from `connormason/homeassistant` into `services/homeassistant/`
- Config files live next to their service so GitHub Actions path triggers naturally identify what changed
- The existing `roles/glance/` role is removed (Glance config moves to `services/glance/`)

### 2. Deploy Script (`scripts/deploy.sh`)

A bash script placed on the NAS during Ansible bootstrap. Handles the actual deployment work:

1. Receives service names as arguments (e.g., `deploy.sh glance homeassistant`)
2. For each service:
   - The service directory has already been rsynced to `~/docker/<service>/` by CI
   - Runs `docker compose -f ~/docker/compose.base.yml -f ~/docker/<service>/compose.yml up -d <service>`
3. If called with no arguments or with `all`, deploys every service
4. Handles `compose.base.yml` which defines shared networks/extension fields

The script does not handle change detection - that is GitHub Actions' responsibility.

### 3. Compose File Strategy

Each `compose.yml` is fully self-contained, defining the service, its volumes, ports, and network references. The `compose.base.yml` at the services root defines shared resources (the default network all services communicate over).

On the NAS, compose files are merged at runtime:

```bash
docker compose -f ~/docker/compose.base.yml \
               -f ~/docker/glance/compose.yml \
               up -d glance
```

**Why per-service files:**
- Any service change targets exactly that service's file
- Each file is small and focused
- `docker compose` natively supports multiple `-f` flags
- Service dependencies declared via `depends_on` resolve across merged files

If `compose.base.yml` changes, a full redeploy of all services is triggered.

### 4. GitHub Actions Workflow (`.github/workflows/deploy.yml`)

Triggered on push to `main`. Two jobs:

**Job 1: `detect-changes`**
- Uses `git diff` between current and previous commit to identify changed files under `services/`
- Outputs a JSON list of affected service names (e.g., `["glance", "homeassistant"]`)
- If `services/compose.base.yml` changed, outputs all services
- If no services changed (e.g., only Ansible roles or docs edited), the deploy job is skipped

**Job 2: `deploy`**
- Runs as a matrix over the service list from job 1
- Steps:
  1. Checkout repo
  2. Set up Tailscale using `tailscale/github-action`
  3. Rsync the changed service directory to NAS via SSH over Tailscale
  4. SSH in and run `deploy.sh <service>`

**Manual trigger:** The workflow supports `workflow_dispatch` with an optional service name input (defaults to `all`). Useful for re-syncing after manual changes on the NAS.

### 5. GitHub Secrets

| Secret | Purpose |
|--------|---------|
| `TAILSCALE_OAUTH_CLIENT_ID` | Tailscale OAuth app client ID |
| `TAILSCALE_OAUTH_CLIENT_SECRET` | Tailscale OAuth app secret |
| `NAS_SSH_PRIVATE_KEY` | SSH private key for NAS access |
| `NAS_TAILSCALE_HOST` | NAS hostname/IP on the Tailnet |
| `NAS_USER` | SSH username on the NAS |

### 6. Ansible's Reduced Role

**Ansible still handles (bootstrap only):**
- Installing Docker engine and compose plugin
- Creating the `~/docker/` directory structure on the NAS
- Building custom images (autoplex, caddy-dnsimple) from git repos
- Rendering secret templates (`.env` from vault, `ha_secrets.yaml` from vault)
- Copying Lutron Caseta certificates from inventory
- Placing `deploy.sh` on the NAS
- Running an initial full deploy of all services

**Ansible stops handling:**
- Copying `docker-compose.yml` on every run
- Syncing Glance config files
- Being the mechanism for day-to-day config changes

**Changes to existing roles:**
- `roles/docker/tasks/main.yml`: trimmed to remove config copy tasks, replaced with initial full deploy
- `roles/docker/files/docker-compose.yml`: removed (replaced by per-service compose files in `services/`)
- `roles/glance/`: removed entirely (config moves to `services/glance/`)

### 7. Secrets Handling

Secrets remain in Ansible Vault, rendered once during bootstrap:
- `.env` file (PiHole password, DNSimple token) rendered to `~/docker/.env`
- `ha_secrets.yaml` rendered to `~/docker/homeassistant/secrets.yaml`

The CI pipeline never touches secrets - it only syncs config files and compose definitions. To rotate a secret, re-run the Ansible bootstrap with the relevant tag.

### 8. Failure Handling

- Failed deploys show as red in GitHub Actions with full logs
- No automatic rollback - the previous container keeps running if `docker compose up` fails (Docker's default behavior)
- Failed workflows can be re-run from the GitHub UI, or fixed with a new push

## Day-to-Day Workflow

```bash
# Edit a config file
vim services/glance/config/home.yml

# Push to main
git add -A && git commit -m "update glance dashboard" && git push

# GitHub Actions automatically:
#   1. Detects services/glance/* changed
#   2. Connects to NAS via Tailscale
#   3. Rsyncs glance/ directory to NAS
#   4. Runs deploy.sh glance (docker compose up -d glance)
#   Done. ~30-60 seconds.
```

## Migration Path

1. Create `services/` directory structure with per-service compose files
2. Consolidate Home Assistant config from separate repo
3. Move Glance config from `roles/glance/` to `services/glance/`
4. Write `scripts/deploy.sh`
5. Create `.github/workflows/deploy.yml`
6. Update `roles/docker/` Ansible role to handle bootstrap + initial deploy only
7. Remove `roles/glance/` and `roles/docker/files/docker-compose.yml`
8. Set up GitHub secrets (Tailscale OAuth, SSH key, NAS host)
9. Test end-to-end: push a config change, verify automatic deploy
