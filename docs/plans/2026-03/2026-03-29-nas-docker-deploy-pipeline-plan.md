# NAS Docker Deploy Pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the manual SSH-pull-restart Docker deployment workflow with automated per-service CI deploys via GitHub Actions + Tailscale SSH.

**Architecture:** Per-service compose files in `services/`, a bash deploy script on the NAS, and a GitHub Actions workflow that detects changed services, rsyncs them to the NAS over Tailscale, and restarts only affected containers. Ansible is retained for bootstrap/secrets only.

**Tech Stack:** Docker Compose, GitHub Actions, Tailscale, rsync, bash, Ansible (bootstrap only)

**Spec:** `.claude/specs/2026-03-29-nas-docker-deploy-pipeline-design.md`

---

## File Map

### New files to create

| File | Responsibility |
|------|---------------|
| `services/compose.base.yml` | Shared network, project name `nas-stack` |
| `services/caddy/compose.yml` | Caddy reverse proxy (Tailscale HTTPS) |
| `services/pihole/compose.yml` | PiHole DNS/ad-blocker |
| `services/plex/compose.yml` | Plex media server |
| `services/autoplex/compose.yml` | Automated file organizer |
| `services/transmission/compose.yml` | Torrent client |
| `services/flaresolverr/compose.yml` | Cloudflare bypass proxy |
| `services/prowlarr/compose.yml` | Indexer aggregator |
| `services/radarr/compose.yml` | Movie management |
| `services/sonarr/compose.yml` | TV show management |
| `services/homeassistant/compose.yml` | Home automation |
| `services/homeassistant/config/` | HA config (consolidated from separate repo) |
| `services/homeassistant/shared/.gitkeep` | Shared volume placeholder |
| `services/glance/compose.yml` | Dashboard |
| `services/glance/config/glance.yml` | Glance main config (moved from roles/glance/) |
| `services/glance/config/home.yml` | Glance home page config (moved from roles/glance/) |
| `services/glance/assets/user.css` | Glance custom CSS (moved from roles/glance/) |
| `scripts/deploy.sh` | NAS deploy script (rsync target, docker compose up) |
| `.github/workflows/deploy.yml` | CI pipeline: change detection + deploy |

### Files to modify

| File | Change |
|------|--------|
| `roles/docker/tasks/main.yml` | Remove caddy-dnsimple/pyautoplex builds, extract .env task, remove config copy, add deploy.sh placement + initial deploy |
| `roles/docker/defaults/main.yml` | Remove caddy-dnsimple/pyautoplex vars, update autoplex dest |
| `roles/docker/templates/env.j2` | Remove DNSIMPLE_OAUTH_TOKEN, add ADVERTISE_IP |
| `.pre-commit-config.yaml` | Add yamllint exclude for HA config |

### Files to delete

| File | Reason |
|------|--------|
| `roles/docker/files/docker-compose.yml` | Replaced by per-service compose files |
| `roles/docker/templates/Caddyfile.j2` | Replaced by `roles/tailscale/templates/Caddyfile.j2` |
| `roles/docker/templates/ha_secrets.yaml.j2` | Moved to `services/homeassistant/config/secrets.yaml.j2` |
| `roles/glance/` (entire directory) | Config moved to `services/glance/` |

---

## Task 1: Create compose.base.yml and per-service compose files

**Files:**
- Create: `services/compose.base.yml`
- Create: `services/caddy/compose.yml`
- Create: `services/pihole/compose.yml`
- Create: `services/plex/compose.yml`
- Create: `services/autoplex/compose.yml`
- Create: `services/transmission/compose.yml`
- Create: `services/flaresolverr/compose.yml`
- Create: `services/prowlarr/compose.yml`
- Create: `services/radarr/compose.yml`
- Create: `services/sonarr/compose.yml`
- Create: `services/homeassistant/compose.yml`
- Create: `services/glance/compose.yml`

- [ ] **Step 1: Create `services/compose.base.yml`**

```yaml
---
name: nas-stack

networks:
  default:
    name: nas-network
```

- [ ] **Step 2: Create `services/caddy/compose.yml`**

```yaml
---
services:
  caddy:
    image: caddy:2-alpine
    container_name: caddy
    restart: unless-stopped
    ports:
      - "443:443"
      - "32443:32443"
    volumes:
      - /etc/tailscale/certs:/certs:ro
      - /etc/caddy/Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data

volumes:
  caddy_data: {}
```

- [ ] **Step 3: Create `services/pihole/compose.yml`**

```yaml
---
services:
  pihole:
    container_name: pihole
    image: pihole/pihole:latest
    restart: unless-stopped
    ports:
      - "53:53/tcp"
      - "53:53/udp"
      - "67:67/udp"
      - "8053:80/tcp"
    environment:
      - TZ=America/Los_Angeles
      - FTLCONF_dns_listeningMode=ALL
      - FTLCONF_webserver_api_password
    volumes:
      - ./pihole-data/etc-pihole:/etc/pihole
    cap_add:
      - NET_ADMIN
      - SYS_NICE
```

Note: Volume path `./pihole-data/etc-pihole` resolves via `--project-directory ~/docker` to `~/docker/pihole-data/etc-pihole`, keeping runtime data outside the rsynced `~/docker/pihole/` service directory.

- [ ] **Step 4: Create `services/plex/compose.yml`**

```yaml
---
services:
  plex:
    image: linuxserver/plex
    container_name: plex
    restart: unless-stopped
    environment:
      - PUID=1000
      - PGID=1000
      - VERSION=docker
      - ADVERTISE_IP
    ports:
      - "32400:32400"
    volumes:
      - /storage/media/config/plex:/config
      - /storage/media/tv:/tv
      - /storage/media/movies:/movies
      - /storage/media/music:/music
```

- [ ] **Step 5: Create `services/autoplex/compose.yml`**

```yaml
---
services:
  autoplex:
    image: danielmmetz/autoplex:latest
    container_name: autoplex
    restart: unless-stopped
    volumes:
      - /storage/media/downloads:/downloads
      - /storage/media/tv:/tv
      - /storage/media/movies:/movies
    command:
      - "--mode"
      - "copy"
      - "--host"
      - "transmission"
      - "--src"
      - "/downloads/complete/tv"
      - "--dest"
      - "/tv"
      - "--src"
      - "/downloads/complete/movies"
      - "--dest"
      - "/movies"
```

- [ ] **Step 6: Create `services/transmission/compose.yml`**

```yaml
---
services:
  transmission:
    image: linuxserver/transmission
    container_name: transmission
    restart: unless-stopped
    environment:
      - PUID=1000
      - PGID=1000
    volumes:
      - /storage/media/config/transmission:/config
      - /storage/media/downloads:/downloads
      - /storage/media/watch:/watch
    ports:
      - "9091:9091"
```

- [ ] **Step 7: Create `services/flaresolverr/compose.yml`**

```yaml
---
services:
  flaresolverr:
    image: ghcr.io/flaresolverr/flaresolverr
    container_name: flaresolverr
    restart: unless-stopped
    environment:
      - PUID=1000
      - PGID=1000
```

- [ ] **Step 8: Create `services/prowlarr/compose.yml`**

```yaml
---
services:
  prowlarr:
    image: linuxserver/prowlarr
    container_name: prowlarr
    restart: unless-stopped
    environment:
      - PUID=1000
      - PGID=1000
    volumes:
      - /storage/media/config/prowlarr:/config
    ports:
      - "9696:9696"
```

- [ ] **Step 9: Create `services/radarr/compose.yml`**

```yaml
---
services:
  radarr:
    image: linuxserver/radarr
    container_name: radarr
    restart: unless-stopped
    environment:
      - PUID=1000
      - PGID=1000
    volumes:
      - /storage/media/config/radarr:/config
      - /storage/media/movies:/movies
      - /storage/media/downloads:/downloads
    ports:
      - "7878:7878"
```

- [ ] **Step 10: Create `services/sonarr/compose.yml`**

```yaml
---
services:
  sonarr:
    image: linuxserver/sonarr
    container_name: sonarr
    restart: unless-stopped
    environment:
      - PUID=1000
      - PGID=1000
    volumes:
      - /storage/media/config/sonarr:/config
      - /storage/media/tv:/tv
      - /storage/media/downloads:/downloads
    ports:
      - "8989:8989"
```

- [ ] **Step 11: Create `services/homeassistant/compose.yml`**

```yaml
---
services:
  homeassistant:
    container_name: home-assistant
    image: homeassistant/home-assistant
    network_mode: host
    restart: always
    environment:
      - TZ=America/Los_Angeles
    volumes:
      - ./homeassistant/config:/config
      - /etc/localtime:/etc/localtime:ro
      - ./homeassistant/shared:/shared
```

Note: `network_mode: host` means this service does not join the shared network defined in `compose.base.yml`.

- [ ] **Step 12: Create `services/glance/compose.yml`**

```yaml
---
services:
  glance:
    container_name: glance
    image: glanceapp/glance
    restart: unless-stopped
    env_file: .env
    volumes:
      - ./glance/config:/app/config
      - ./glance/assets:/app/assets
      - /etc/localtime:/etc/localtime:ro
      - /var/run/docker.sock:/var/run/docker.sock:ro
    ports:
      - "8080:8080"
```

- [ ] **Step 13: Validate all compose files parse correctly**

Run: `for f in services/*/compose.yml services/compose.base.yml; do echo "--- $f ---"; docker compose -f "$f" config --quiet && echo "OK" || echo "FAIL"; done`

Expected: All files print "OK" (note: some may warn about undefined env vars like `FTLCONF_webserver_api_password` — that's expected since `.env` isn't present locally).

- [ ] **Step 14: Commit**

```bash
git add services/
git commit -m "feat: create per-service compose files

Split monolithic docker-compose.yml into individual service
compose files under services/. Each service gets its own
directory with a standalone compose.yml fragment."
```

---

## Task 2: Move Glance config to services/

**Files:**
- Create: `services/glance/config/glance.yml` (move from `roles/glance/files/config/glance.yml`)
- Create: `services/glance/config/home.yml` (move from `roles/glance/files/config/home.yml`)
- Create: `services/glance/assets/user.css` (move from `roles/glance/files/assets/user.css`)

- [ ] **Step 1: Move Glance config and assets**

```bash
mkdir -p services/glance/config services/glance/assets
cp roles/glance/files/config/glance.yml services/glance/config/glance.yml
cp roles/glance/files/config/home.yml services/glance/config/home.yml
cp roles/glance/files/assets/user.css services/glance/assets/user.css
```

- [ ] **Step 2: Verify files match originals**

```bash
diff roles/glance/files/config/glance.yml services/glance/config/glance.yml
diff roles/glance/files/config/home.yml services/glance/config/home.yml
diff roles/glance/files/assets/user.css services/glance/assets/user.css
```

Expected: No diff output (files identical).

- [ ] **Step 3: Commit**

```bash
git add services/glance/config/ services/glance/assets/
git commit -m "feat: move Glance config to services/glance/

Glance config files moved from roles/glance/files/ to
services/glance/ for CI-based deployment."
```

---

## Task 3: Consolidate Home Assistant config

**Files:**
- Create: `services/homeassistant/config/` (contents from `connormason/homeassistant` repo)
- Create: `services/homeassistant/config/secrets.yaml.j2` (move from `roles/docker/templates/ha_secrets.yaml.j2`)
- Create: `services/homeassistant/shared/.gitkeep`

- [ ] **Step 1: Clone the HA repo and copy contents**

```bash
git clone git@github.com:connormason/homeassistant.git /tmp/ha-config-import
mkdir -p services/homeassistant/config
cp -R /tmp/ha-config-import/* services/homeassistant/config/
cp /tmp/ha-config-import/.* services/homeassistant/config/ 2>/dev/null || true
rm -rf services/homeassistant/config/.git
rm -rf /tmp/ha-config-import
```

- [ ] **Step 2: Move the secrets template (from Ansible role to services)**

```bash
mv roles/docker/templates/ha_secrets.yaml.j2 services/homeassistant/config/secrets.yaml.j2
```

Note: This file is excluded from rsync via `--exclude='*.j2'`. Ansible renders it during bootstrap. The original is removed from `roles/docker/templates/` to avoid two copies drifting apart.

- [ ] **Step 3: Create shared directory placeholder**

```bash
mkdir -p services/homeassistant/shared
touch services/homeassistant/shared/.gitkeep
```

- [ ] **Step 4: Verify HA config directory has expected files**

```bash
ls services/homeassistant/config/
```

Expected: Should contain at minimum `configuration.yaml`, `secrets.yaml.j2`, and other HA config files from the repo.

- [ ] **Step 5: Commit**

```bash
git add services/homeassistant/
git commit -m "feat: consolidate Home Assistant config into services/

Import HA config from connormason/homeassistant repo into
services/homeassistant/config/. secrets.yaml.j2 template
moved from roles/docker/templates/."
```

---

## Task 4: Write the deploy script

**Files:**
- Create: `scripts/deploy.sh`

- [ ] **Step 1: Create `scripts/deploy.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

# NAS Docker service deploy script
# Placed on NAS by Ansible bootstrap. Called by GitHub Actions CI.
#
# Usage:
#   deploy.sh <service> [<service> ...]   Deploy specific services
#   deploy.sh all                          Deploy all services
#   deploy.sh                              Deploy all services (default)

DOCKER_DIR="${HOME}/docker"
BASE_COMPOSE="${DOCKER_DIR}/compose.base.yml"

# Discover all services: subdirectories of ~/docker/ containing a compose.yml
discover_services() {
    local services=()
    for dir in "${DOCKER_DIR}"/*/; do
        if [[ -f "${dir}compose.yml" ]]; then
            services+=("$(basename "$dir")")
        fi
    done
    echo "${services[@]}"
}

# Deploy a single service
deploy_service() {
    local service="$1"
    local service_compose="${DOCKER_DIR}/${service}/compose.yml"

    if [[ ! -f "$service_compose" ]]; then
        echo "ERROR: No compose.yml found for service '${service}' at ${service_compose}" >&2
        return 1
    fi

    echo "Deploying ${service}..."
    docker compose \
        --project-directory "${DOCKER_DIR}" \
        -f "${BASE_COMPOSE}" \
        -f "${service_compose}" \
        up -d "${service}"
    echo "Done: ${service}"
}

# Main
main() {
    if [[ ! -f "$BASE_COMPOSE" ]]; then
        echo "ERROR: Base compose file not found at ${BASE_COMPOSE}" >&2
        exit 1
    fi

    local services=("$@")

    # Default to "all" if no arguments
    if [[ ${#services[@]} -eq 0 ]] || [[ "${services[0]}" == "all" ]]; then
        read -ra services <<< "$(discover_services)"
        echo "Deploying all services: ${services[*]}"
    fi

    local failed=0
    for service in "${services[@]}"; do
        if ! deploy_service "$service"; then
            echo "FAILED: ${service}" >&2
            failed=1
        fi
    done

    if [[ $failed -ne 0 ]]; then
        echo "Some services failed to deploy" >&2
        exit 1
    fi

    echo "All deployments complete"
}

main "$@"
```

- [ ] **Step 2: Make executable**

```bash
chmod +x scripts/deploy.sh
```

- [ ] **Step 3: Validate with shellcheck (if available)**

```bash
shellcheck scripts/deploy.sh || echo "shellcheck not installed, skipping"
```

Expected: No errors. Warnings about `read -ra` on older bash are acceptable.

- [ ] **Step 4: Commit**

```bash
git add scripts/deploy.sh
git commit -m "feat: add NAS deploy script

Bash script that deploys Docker services by running
docker compose up -d with per-service compose files.
Supports deploying specific services or all at once."
```

---

## Task 5: Create GitHub Actions workflow

**Files:**
- Create: `.github/workflows/deploy.yml`

- [ ] **Step 1: Create `.github/workflows/deploy.yml`**

```yaml
---
name: Deploy NAS Services

on:
  push:
    branches: [main]
    paths:
      - "services/**"
  workflow_dispatch:
    inputs:
      service:
        description: "Service to deploy (or 'all')"
        required: false
        default: "all"

jobs:
  detect-changes:
    if: github.event_name == 'push'
    runs-on: ubuntu-latest
    outputs:
      services: ${{ steps.detect.outputs.services }}
      has_changes: ${{ steps.detect.outputs.has_changes }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Detect changed services
        id: detect
        run: |
          BEFORE="${{ github.event.before }}"

          # Fallback for force pushes or new branches (null SHA)
          if [[ "$BEFORE" == "0000000000000000000000000000000000000000" ]]; then
            echo "Null SHA detected (force push or new branch) — deploying all services"
            SERVICES=$(ls -d services/*/compose.yml 2>/dev/null | xargs -I{} dirname {} | xargs -I{} basename {} | jq -R . | jq -s .)
            echo "services=${SERVICES}" >> "$GITHUB_OUTPUT"
            echo "has_changes=true" >> "$GITHUB_OUTPUT"
            exit 0
          fi

          # Check if compose.base.yml changed — if so, deploy everything
          if git diff --name-only "$BEFORE".."${{ github.sha }}" | grep -q "^services/compose.base.yml$"; then
            echo "compose.base.yml changed — deploying all services"
            SERVICES=$(ls -d services/*/compose.yml 2>/dev/null | xargs -I{} dirname {} | xargs -I{} basename {} | jq -R . | jq -s .)
            echo "services=${SERVICES}" >> "$GITHUB_OUTPUT"
            echo "has_changes=true" >> "$GITHUB_OUTPUT"
            exit 0
          fi

          # Detect which service directories changed
          CHANGED_SERVICES=$(git diff --name-only "$BEFORE".."${{ github.sha }}" \
            | grep "^services/" \
            | grep -v "^services/compose.base.yml$" \
            | cut -d'/' -f2 \
            | sort -u \
            | jq -R . | jq -s .)

          if [[ "$CHANGED_SERVICES" == "[]" ]]; then
            echo "No service changes detected"
            echo "services=[]" >> "$GITHUB_OUTPUT"
            echo "has_changes=false" >> "$GITHUB_OUTPUT"
          else
            echo "Changed services: ${CHANGED_SERVICES}"
            echo "services=${CHANGED_SERVICES}" >> "$GITHUB_OUTPUT"
            echo "has_changes=true" >> "$GITHUB_OUTPUT"
          fi

  deploy-push:
    if: github.event_name == 'push' && needs.detect-changes.outputs.has_changes == 'true'
    needs: detect-changes
    runs-on: ubuntu-latest
    strategy:
      max-parallel: 1
      matrix:
        service: ${{ fromJson(needs.detect-changes.outputs.services) }}
    steps:
      - uses: actions/checkout@v4

      - name: Set up Tailscale
        uses: tailscale/github-action@v3
        with:
          oauth-client-id: ${{ secrets.TAILSCALE_OAUTH_CLIENT_ID }}
          oauth-secret: ${{ secrets.TAILSCALE_OAUTH_CLIENT_SECRET }}
          tags: tag:ci

      - name: Set up SSH key
        run: |
          mkdir -p ~/.ssh
          echo "${{ secrets.NAS_SSH_PRIVATE_KEY }}" > ~/.ssh/id_nas
          chmod 600 ~/.ssh/id_nas
          ssh-keyscan -H ${{ secrets.NAS_TAILSCALE_HOST }} >> ~/.ssh/known_hosts 2>/dev/null || true

      - name: Rsync compose.base.yml
        run: |
          rsync -avz --exclude='*.j2' \
            services/compose.base.yml \
            ${{ secrets.NAS_USER }}@${{ secrets.NAS_TAILSCALE_HOST }}:~/docker/compose.base.yml \
            -e "ssh -i ~/.ssh/id_nas -o StrictHostKeyChecking=accept-new"

      - name: Rsync service directory
        run: |
          rsync -avz --exclude='*.j2' \
            services/${{ matrix.service }}/ \
            ${{ secrets.NAS_USER }}@${{ secrets.NAS_TAILSCALE_HOST }}:~/docker/${{ matrix.service }}/ \
            -e "ssh -i ~/.ssh/id_nas -o StrictHostKeyChecking=accept-new"

      - name: Deploy service
        run: |
          ssh -i ~/.ssh/id_nas -o StrictHostKeyChecking=accept-new \
            ${{ secrets.NAS_USER }}@${{ secrets.NAS_TAILSCALE_HOST }} \
            "~/docker/deploy.sh ${{ matrix.service }}"

  deploy-manual:
    if: github.event_name == 'workflow_dispatch'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Tailscale
        uses: tailscale/github-action@v3
        with:
          oauth-client-id: ${{ secrets.TAILSCALE_OAUTH_CLIENT_ID }}
          oauth-secret: ${{ secrets.TAILSCALE_OAUTH_CLIENT_SECRET }}
          tags: tag:ci

      - name: Set up SSH key
        run: |
          mkdir -p ~/.ssh
          echo "${{ secrets.NAS_SSH_PRIVATE_KEY }}" > ~/.ssh/id_nas
          chmod 600 ~/.ssh/id_nas
          ssh-keyscan -H ${{ secrets.NAS_TAILSCALE_HOST }} >> ~/.ssh/known_hosts 2>/dev/null || true

      - name: Rsync all services
        run: |
          rsync -avz --exclude='*.j2' \
            services/ \
            ${{ secrets.NAS_USER }}@${{ secrets.NAS_TAILSCALE_HOST }}:~/docker/ \
            -e "ssh -i ~/.ssh/id_nas -o StrictHostKeyChecking=accept-new"

      - name: Deploy
        run: |
          ssh -i ~/.ssh/id_nas -o StrictHostKeyChecking=accept-new \
            ${{ secrets.NAS_USER }}@${{ secrets.NAS_TAILSCALE_HOST }} \
            "~/docker/deploy.sh ${{ github.event.inputs.service }}"
```

- [ ] **Step 2: Validate YAML syntax**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/deploy.yml'))" && echo "Valid YAML"
```

Expected: "Valid YAML"

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/deploy.yml
git commit -m "feat: add GitHub Actions deploy workflow

CI pipeline that detects changed services on push to main,
connects to NAS via Tailscale, rsyncs changed files, and
runs deploy.sh. Supports manual dispatch for full redeploys."
```

---

## Task 6: Update Ansible docker role

**Files:**
- Modify: `roles/docker/tasks/main.yml`
- Modify: `roles/docker/defaults/main.yml`
- Modify: `roles/docker/templates/env.j2`

- [ ] **Step 1: Update `roles/docker/defaults/main.yml`**

Replace the entire file with:

```yaml
docker_dir: "{{ ansible_facts['user_dir'] }}/docker"

autoplex_repo_dest: "{{ docker_dir }}/.build/autoplex"
autoplex_repo_url: https://github.com/danielmmetz/autoplex.git
autoplex_repo_branch: master

homeassistant_config_dir: "{{ docker_dir }}/homeassistant/config"
```

This removes caddy-dnsimple and pyautoplex variables, moves autoplex build to `.build/`, and removes the separate homeassistant repo variables (HA config now comes from this repo via CI rsync).

- [ ] **Step 2: Update `roles/docker/templates/env.j2`**

Replace the entire file with:

```
FTLCONF_webserver_api_password={{ pihole_web_password }}
ADVERTISE_IP=https://{{ tailscale_hostname }}.{{ tailscale_tailnet_name }}:32443
```

This removes `DNSIMPLE_OAUTH_TOKEN` and adds `ADVERTISE_IP` for Plex's Tailscale URL.

- [ ] **Step 3: Rewrite `roles/docker/tasks/main.yml`**

Replace the entire file with:

```yaml
---
# ============================================================
# Docker installation (unchanged)
# ============================================================
- name: Setup Docker
  block:
    - name: Setup Docker repository
      block:
        - name: Install dependencies
          become: true
          ansible.builtin.apt:
            pkg:
              - ca-certificates
              - curl
              - gnupg

        - name: Add Docker GPG signing key
          ansible.builtin.get_url:
            url: "https://download.docker.com/linux/{{ ansible_facts['distribution'] | lower }}/gpg"
            dest: /usr/share/keyrings/docker.asc

        - name: Get debian architecture
          block:
            - name: Print debian architecture
              ansible.builtin.shell: "dpkg --print-architecture"
              register: dpkg_print_architecture

            - name: Set debian architecture fact
              ansible.builtin.set_fact:
                deb_architecture: "{{ dpkg_print_architecture.stdout }}"

        - name: Add Docker repository
          become: true
          ansible.builtin.apt_repository:
            repo: "deb [arch={{ deb_architecture }} signed-by=/usr/share/keyrings/docker.asc] https://download.docker.com/linux/{{ ansible_facts['distribution'] | lower }} {{ ansible_facts['distribution_release'] }} stable"
            state: present
          register: docker_repo_add

        - name: Update apt package index
          become: true
          ansible.builtin.apt:
            update_cache: true
          when: docker_repo_add.changed

    - name: Install Docker engine
      become: true
      ansible.builtin.apt:
        pkg:
          - docker-ce
          - docker-ce-cli
          - containerd.io
          - docker-buildx-plugin
          - docker-compose-plugin
          - docker-compose

    - name: Ensure docker daemon is running
      service:
        name: docker
        state: started
      become: true

# ============================================================
# Directory setup
# ============================================================
- name: Create docker directory structure
  ansible.builtin.file:
    path: "{{ item }}"
    state: directory
  loop:
    - "{{ docker_dir }}"
    - "{{ docker_dir }}/.build"
    - "{{ docker_dir }}/pihole-data/etc-pihole"

# ============================================================
# Secrets and environment (extracted from old caddy block)
# ============================================================
- name: Render .env file
  ansible.builtin.template:
    src: env.j2
    dest: "{{ docker_dir }}/.env"
  tags:
    - configfile

# ============================================================
# Custom image builds
# ============================================================
- name: Setup autoplex
  block:
    - name: Clone autoplex repo
      ansible.builtin.git:
        repo: "{{ autoplex_repo_url }}"
        dest: "{{ autoplex_repo_dest }}"
        version: "{{ autoplex_repo_branch }}"
        clone: true
        update: true
        accept_hostkey: true

    - name: Build autoplex image
      community.docker.docker_image:
        build:
          path: "{{ autoplex_repo_dest }}"
        name: danielmmetz/autoplex
        tag: latest
        source: build
      become: true

# ============================================================
# Home Assistant secrets and certificates
# ============================================================
- name: Setup homeassistant secrets
  tags:
    - homeassistant
  block:
    - name: Ensure homeassistant config directory exists
      ansible.builtin.file:
        path: "{{ homeassistant_config_dir }}"
        state: directory

    - name: Render homeassistant secrets file
      ansible.builtin.template:
        src: "{{ playbook_dir }}/../services/homeassistant/config/secrets.yaml.j2"
        dest: "{{ homeassistant_config_dir }}/secrets.yaml"
      tags:
        - configfile

    - name: Copy Lutron Caseta certifications/keys
      block:
        - name: Get path to group "all" inventory dir
          ansible.builtin.set_fact:
            ansible_group_all_inventory_dir: "{{ inventory_dir }}/group_vars/all"
          tags:
            - always

        - name: Copy caseta.crt
          ansible.builtin.copy:
            src: "{{ ansible_group_all_inventory_dir }}/caseta.crt"
            dest: "{{ homeassistant_config_dir }}"

        - name: Copy caseta.key
          ansible.builtin.copy:
            src: "{{ ansible_group_all_inventory_dir }}/caseta.key"
            dest: "{{ homeassistant_config_dir }}"

        - name: Copy caseta-bridge.crt
          ansible.builtin.copy:
            src: "{{ ansible_group_all_inventory_dir }}/caseta-bridge.crt"
            dest: "{{ homeassistant_config_dir }}"

# ============================================================
# Deploy script and initial deploy
# ============================================================
- name: Copy deploy script
  ansible.builtin.copy:
    src: "{{ playbook_dir }}/../scripts/deploy.sh"
    dest: "{{ docker_dir }}/deploy.sh"
    mode: "0755"
  tags:
    - configfile

- name: Run initial full deploy
  ansible.builtin.command:
    cmd: "{{ docker_dir }}/deploy.sh all"
  environment:
    HOME: "{{ ansible_facts['user_dir'] }}"
```

- [ ] **Step 4: Commit**

```bash
git add roles/docker/tasks/main.yml roles/docker/defaults/main.yml roles/docker/templates/env.j2
git commit -m "refactor: update docker role for bootstrap-only workflow

Remove caddy-dnsimple/pyautoplex builds. Extract .env rendering
from caddy block. Move autoplex build to .build/ dir. Update
env template (remove DNSIMPLE_OAUTH_TOKEN, add ADVERTISE_IP).
Add deploy.sh placement. HA secrets render to new config path."
```

---

## Task 7: Update pre-commit config and clean up old files

**Files:**
- Modify: `.pre-commit-config.yaml`
- Delete: `roles/docker/files/docker-compose.yml`
- Delete: `roles/docker/templates/Caddyfile.j2`
- Delete: `roles/glance/` (entire directory)

- [ ] **Step 1: Add yamllint exclude for HA config**

In `.pre-commit-config.yaml`, update the yamllint exclude pattern (line 88-93) to also exclude HA config:

Current:
```yaml
        exclude: |
          (?x)(
              ^.pre-commit-config.yaml|
              ^.config/.ansible-lint.yaml|
              archived_linux/
          )
```

New:
```yaml
        exclude: |
          (?x)(
              ^.pre-commit-config.yaml|
              ^.config/.ansible-lint.yaml|
              archived_linux/|
              ^services/homeassistant/config/
          )
```

- [ ] **Step 2: Also add check-yaml exclude for HA config**

HA YAML uses `!include` and `!secret` tags that cause `check-yaml` to fail. Update the check-yaml hook (line 44-45) to exclude HA config:

Current:
```yaml
      - id: check-yaml
        name: "[check] yaml"
```

New:
```yaml
      - id: check-yaml
        name: "[check] yaml"
        exclude: ^services/homeassistant/config/
```

- [ ] **Step 3: Delete old monolithic docker-compose.yml**

```bash
git rm roles/docker/files/docker-compose.yml
```

- [ ] **Step 4: Delete old Caddyfile template from docker role**

```bash
git rm roles/docker/templates/Caddyfile.j2
```

This template is superseded by `roles/tailscale/templates/Caddyfile.j2`.

- [ ] **Step 5: Delete the glance role**

```bash
git rm -r roles/glance/
```

Glance config now lives in `services/glance/` and deploys via CI.

- [ ] **Step 6: Run pre-commit to verify config is valid**

```bash
pre-commit run --all-files
```

Expected: All hooks pass. HA config YAML files (if present) should be excluded from yamllint and check-yaml.

- [ ] **Step 7: Commit**

```bash
git add .pre-commit-config.yaml
git commit -m "refactor: cleanup old files and update pre-commit config

Remove monolithic docker-compose.yml (replaced by per-service
compose files). Remove old Caddyfile.j2 (replaced by tailscale
role template). Remove roles/glance/ (moved to services/).
Add yamllint and check-yaml excludes for HA config."
```

---

## Task 8: Update nas_bootstrap.yml playbook

**Files:**
- Modify: `playbooks/nas_bootstrap.yml`

- [ ] **Step 1: Remove the glance role include from `playbooks/nas_bootstrap.yml`**

Remove lines 58-65 (the glance role include block):

```yaml
    # Tasks for Glance
    - include_role:
        name: roles/glance
        apply:
          tags: glance
      tags:
        - glance
        - configfile
```

- [ ] **Step 2: Commit**

```bash
git add playbooks/nas_bootstrap.yml
git commit -m "refactor: remove glance role from NAS bootstrap

Glance config now deploys via CI pipeline from services/glance/."
```

---

## Task 9: Validate and document

- [ ] **Step 1: Verify the full file structure is correct**

```bash
echo "=== Services ==="
find services/ -type f | sort
echo ""
echo "=== Deploy script ==="
ls -la scripts/deploy.sh
echo ""
echo "=== GitHub Actions ==="
ls -la .github/workflows/deploy.yml
echo ""
echo "=== Deleted files (should not exist) ==="
ls roles/docker/files/docker-compose.yml 2>&1 || true
ls roles/docker/templates/Caddyfile.j2 2>&1 || true
ls roles/glance/ 2>&1 || true
```

- [ ] **Step 2: Run pre-commit on entire repo**

```bash
pre-commit run --all-files
```

Expected: All hooks pass.

- [ ] **Step 3: Verify git status is clean**

```bash
git status
```

Expected: Clean working tree, all changes committed.

---

## Post-Implementation: Manual Steps (not automated)

These steps require access to GitHub settings and the NAS:

1. **Audit existing NAS `.env` file** — SSH into the NAS and check `~/docker/.env` for any variables not in the `env.j2` template (e.g., Glance API keys). Add any missing variables to `roles/docker/templates/env.j2` before running Ansible bootstrap, or they will be overwritten.

2. **Migrate Home Assistant shared volume** — the `shared/` volume path changed from `~/docker/shared` to `~/docker/homeassistant/shared`. On the NAS:
   ```bash
   # If ~/docker/shared/ has data, move it to the new location
   mv ~/docker/shared/* ~/docker/homeassistant/shared/ 2>/dev/null || true
   ```

3. **Set up GitHub secrets** in the repository settings:
   - `TAILSCALE_OAUTH_CLIENT_ID` — create an OAuth client in Tailscale admin console with `tag:ci` tag
   - `TAILSCALE_OAUTH_CLIENT_SECRET` — the OAuth client secret
   - `NAS_SSH_PRIVATE_KEY` — SSH private key that can authenticate to the NAS via Tailscale SSH
   - `NAS_TAILSCALE_HOST` — the NAS hostname on the tailnet (e.g., `nas`)
   - `NAS_USER` — SSH username on the NAS

4. **Initial NAS bootstrap** — run the Ansible playbook once to set up the new directory structure, render secrets, place the deploy script, and run the initial full deploy:
   ```bash
   ansible-playbook playbooks/nas_bootstrap.yml -i inventory/inventory.yml --ask-become-pass --tags docker
   ```

5. **End-to-end test** — make a small config change (e.g., edit `services/glance/config/home.yml`), push to main, verify the GitHub Actions workflow runs successfully and the Glance container restarts with the new config.
