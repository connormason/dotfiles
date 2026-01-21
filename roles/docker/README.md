# Docker Role

Comprehensive Ansible role for managing a Docker-based home media server and automation stack on Debian/Ubuntu NAS
systems.

## Table of Contents

- [Overview](#overview)
- [Service Stack](#service-stack)
- [Architecture](#architecture)
- [Storage Layout](#storage-layout)
- [Network Configuration](#network-configuration)
- [Service Configuration](#service-configuration)
- [Custom Images](#custom-images)
- [Role Tasks](#role-tasks)
- [Usage](#usage)
- [Troubleshooting](#troubleshooting)
- [Adding New Services](#adding-new-services)
- [Maintenance](#maintenance)

## Overview

This role deploys and configures a complete home media server stack using Docker Compose. It handles:

- Docker Engine installation and configuration
- Custom Docker image builds from git repositories
- Service orchestration via Docker Compose
- Automated media file management
- Network services (DNS/ad-blocking)
- Home automation integration
- Dashboard services

The stack is designed to provide a fully automated media server experience with minimal manual intervention.

## Service Stack

### Media Services

#### Plex (Port 32400)
**Purpose**: Media streaming server
- **Image**: `linuxserver/plex`
- **Network Mode**: `host` (temporary workaround for Docker/Plex networking issues)
- **Storage**: Mounts `/storage/media/tv`, `/storage/media/movies`, `/storage/media/music`
- **Dependencies**: Receives media from Autoplex
- **Configuration**: `/storage/media/config/plex`

#### Autoplex (No exposed ports)
**Purpose**: Automated file organization for Plex
- **Image**: `danielmmetz/autoplex:latest` (custom build)
- **Functionality**: Monitors Transmission download directory and copies completed files to appropriate media folders
- **Mode**: Copy mode (preserves original files)
- **Workflow**:
  - Monitors `/downloads/complete/tv` -> copies to `/tv`
  - Monitors `/downloads/complete/movies` -> copies to `/movies`
- **Dependencies**: Requires Transmission

### Media Lookup/Download Services

#### Transmission (Port 9091)
**Purpose**: BitTorrent client
- **Image**: `linuxserver/transmission`
- **Web UI**: Port 9091
- **Storage**:
  - Downloads: `/storage/media/downloads`
  - Watch folder: `/storage/media/watch`
  - Config: `/storage/media/config/transmission`
- **Dependencies**: Used by Sonarr and Radarr for downloads

#### Prowlarr (Port 9696)
**Purpose**: Torrent indexer aggregator
- **Image**: `linuxserver/prowlarr`
- **Functionality**: Centralized management of torrent indexers for Sonarr and Radarr
- **Configuration**: `/storage/media/config/prowlarr`
- **Dependencies**: Integrates with Flaresolverr for Cloudflare bypass

#### Flaresolverr (No exposed ports)
**Purpose**: Cloudflare protection bypass
- **Image**: `ghcr.io/flaresolverr/flaresolverr`
- **Functionality**: Proxy service to bypass Cloudflare CAPTCHA challenges
- **Dependencies**: Used by Prowlarr

#### Sonarr (Port 8989)
**Purpose**: TV show management and automation
- **Image**: `linuxserver/sonarr`
- **Functionality**:
  - Monitors TV show releases
  - Searches for episodes via Prowlarr
  - Sends downloads to Transmission
  - Manages TV library organization
- **Storage**:
  - TV library: `/storage/media/tv`
  - Downloads: `/storage/media/downloads`
  - Config: `/storage/media/config/sonarr`
- **Dependencies**: Prowlarr (indexers), Transmission (downloads)

#### Radarr (Port 7878)
**Purpose**: Movie management and automation
- **Image**: `linuxserver/radarr`
- **Functionality**:
  - Monitors movie releases
  - Searches for movies via Prowlarr
  - Sends downloads to Transmission
  - Manages movie library organization
- **Storage**:
  - Movie library: `/storage/media/movies`
  - Downloads: `/storage/media/downloads`
  - Config: `/storage/media/config/radarr`
- **Dependencies**: Prowlarr (indexers), Transmission (downloads)

### Network Services

#### PiHole (Ports 53/tcp, 53/udp, 67/udp, 8053/tcp)
**Purpose**: Network-wide ad blocking and DNS server
- **Image**: `pihole/pihole:latest`
- **Ports**:
  - 53/tcp, 53/udp: DNS service
  - 67/udp: DHCP server (optional)
  - 8053/tcp: Web UI (remapped from 80 to avoid conflicts)
- **Configuration**: `./etc-pihole` (relative to docker-compose.yml)
- **Environment**:
  - Timezone: America/Los_Angeles
  - DNS listening mode: ALL
  - Web password: From vault (via `.env` file)

### Home Automation & Dashboards

#### Home Assistant (Port 8123)
**Purpose**: Home automation platform
- **Image**: `homeassistant/home-assistant`
- **Network Mode**: `host` (required for service discovery)
- **Configuration**: `./homeassistant` (git repository)
- **Secrets**: Generated from template `ha_secrets.yaml.j2`
- **Special Features**:
  - Lutron Caseta integration (certificates copied from inventory)
  - Shared volume for inter-service communication
- **Storage**:
  - Config: `./homeassistant` (git-managed)
  - Shared: `./shared`

#### Glance (Port 8080)
**Purpose**: Personal dashboard
- **Image**: `glanceapp/glance`
- **Configuration**: `./glance/config`, `./glance/assets`
- **Features**:
  - Docker container monitoring (via Docker socket)
  - Time synchronization
- **Dependencies**: Requires `.env` file for configuration

### Disabled Services

#### Caddy (Commented out)
**Purpose**: Reverse proxy with automatic HTTPS
- **Image**: `danielmmetz/caddy-dnsimple` (custom build)
- **Functionality**: Would provide `*.conmason.com` subdomains for services
- **Configuration**: `Caddyfile` (generated from template)
- **Note**: Currently disabled in docker-compose.yml

#### PyAutoplex (Commented out)
**Purpose**: Alternative Python-based file organizer
- **Image**: `connormason/pyautoplex:latest` (custom build)
- **Note**: Replaced by Autoplex (Go implementation)

## Architecture

### Service Dependency Graph

```
                           ┌─────────────┐
                           │   PiHole    │
                           │   (DNS)     │
                           └─────────────┘

┌─────────────┐            ┌─────────────┐            ┌─────────────┐
│  Prowlarr   │◄───────────│ Flaresolverr│            │   Glance    │
│  (Indexer)  │            │  (Proxy)    │            │ (Dashboard) │
└──────┬──────┘            └─────────────┘            └─────────────┘
       │
       │ Provides indexers
       ├─────────┬─────────┐
       ▼         ▼         ▼
┌─────────┐ ┌─────────┐   │
│ Sonarr  │ │ Radarr  │   │
│  (TV)   │ │ (Movies)│   │
└────┬────┘ └────┬────┘   │
     │           │         │
     │    Sends download requests
     └─────┬─────┴─────────┘
           ▼
    ┌──────────────┐
    │Transmission  │
    │  (Torrent)   │
    └──────┬───────┘
           │
           │ Downloads complete
           ▼
    ┌──────────────┐
    │  Autoplex    │
    │ (Organizer)  │
    └──────┬───────┘
           │
           │ Copies files
           ▼
    ┌──────────────┐
    │    Plex      │
    │  (Streamer)  │
    └──────────────┘

    ┌──────────────┐
    │    Home      │
    │  Assistant   │
    └──────────────┘
```

### Data Flow

1. **Content Discovery**:
   - User adds TV show to Sonarr or movie to Radarr
   - Sonarr/Radarr searches Prowlarr for available torrents
   - Prowlarr queries configured indexers (using Flaresolverr if needed)

2. **Download**:
   - Sonarr/Radarr sends torrent to Transmission
   - Transmission downloads to `/storage/media/downloads`

3. **Organization**:
   - Autoplex monitors download completion
   - Copies completed files to appropriate directories:
     - TV shows → `/storage/media/tv`
     - Movies → `/storage/media/movies`

4. **Consumption**:
   - Plex scans media directories and makes content available
   - Users stream via Plex clients

## Storage Layout

### Directory Structure

```
/storage/media/
├── config/                  # Service configurations
│   ├── plex/                # Plex database and config
│   ├── transmission/        # Transmission settings
│   ├── sonarr/              # Sonarr database and config
│   ├── radarr/              # Radarr database and config
│   └── prowlarr/            # Prowlarr indexer config
├── downloads/               # Transmission download directory
│   ├── complete/            # Completed downloads
│   │   ├── tv/              # Completed TV downloads
│   │   └── movies/          # Completed movie downloads
│   └── incomplete/          # In-progress downloads
├── watch/                   # Transmission watch folder
├── tv/                      # Organized TV library
├── movies/                  # Organized movie library
└── music/                   # Music library

~/docker/                    # Docker Compose project directory
├── docker-compose.yml       # Service definitions
├── .env                     # Environment variables (secrets)
├── etc-pihole/              # PiHole persistent data
├── homeassistant/           # Home Assistant config (git repo)
│   ├── configuration.yaml
│   ├── secrets.yaml         # Generated from template
│   ├── caseta.crt           # Lutron certificates
│   ├── caseta.key
│   └── caseta-bridge.crt
├── glance/
│   ├── config/              # Glance dashboard config
│   └── assets/              # Glance assets
├── shared/                  # Shared volume for services
├── autoplex/                # Autoplex git repository
├── pyautoplex/              # PyAutoplex git repository (unused)
├── caddy-dnsimple/          # Caddy custom image source
└── Caddyfile                # Caddy configuration (for future use)
```

### Volume Mounts

**Media Services:**
- Plex: Read-only access to `/storage/media/tv`, `/storage/media/movies`, `/storage/media/music`
- Autoplex: Read from `/storage/media/downloads`, write to `/storage/media/tv` and `/storage/media/movies`

**Download Services:**
- Transmission: Read/write to `/storage/media/downloads` and `/storage/media/watch`
- Sonarr: Read-only `/storage/media/tv`, read/write `/storage/media/downloads`
- Radarr: Read-only `/storage/media/movies`, read/write `/storage/media/downloads`

**Configuration Persistence:**
- All services: Config directories under `/storage/media/config/*`

## Network Configuration

### Port Mapping

| Service | Port | Protocol | Purpose |
|---------|------|----------|---------|
| PiHole | 53 | TCP/UDP | DNS queries |
| PiHole | 67 | UDP | DHCP server (optional) |
| PiHole | 8053 | TCP | Web UI |
| Plex | 32400 | TCP | Media streaming (host network) |
| Transmission | 9091 | TCP | Web UI |
| Prowlarr | 9696 | TCP | Web UI |
| Sonarr | 8989 | TCP | Web UI |
| Radarr | 7878 | TCP | Web UI |
| Home Assistant | 8123 | TCP | Web UI (host network) |
| Glance | 8080 | TCP | Dashboard |

### Network Modes

**Host Mode:**
- **Plex**: Uses host networking to avoid Docker networking complexities with media streaming
- **Home Assistant**: Uses host networking for service discovery (mDNS, UPnP)

**Bridge Mode (default):**
- All other services use Docker's default bridge network
- Services communicate via container names (e.g., `sonarr:8989`)

### Reverse Proxy (Disabled)

The Caddy reverse proxy configuration (currently commented out) would provide:
- HTTPS endpoints: `tv.conmason.com`, `movies.conmason.com`, `transmission.conmason.com`, `prowlarr.conmason.com`,
`plex.conmason.com`
- Automatic HTTPS via DNS-01 challenge with DNSimple
- TLS certificate management

To enable:
1. Uncomment Caddy service in `roles/docker/files/docker-compose.yml`
2. Uncomment Caddy setup in `roles/docker/tasks/main.yml`
3. Ensure `dnsimple_oauth_token` is set in inventory vault

## Service Configuration

### Environment Variables

**Common Variables (LinuxServer.io images):**
- `PUID=1000`: User ID for file permissions
- `PGID=1000`: Group ID for file permissions
- `VERSION=docker`: Use Docker-managed version updates
- `TZ='America/Los_Angeles'`: Timezone setting

**Secrets (from `.env` file):**
- `DNSIMPLE_OAUTH_TOKEN`: DNSimple API token for Caddy ACME DNS-01
- `FTLCONF_webserver_api_password`: PiHole admin password

**Service-Specific:**
- PiHole: `FTLCONF_dns_listeningMode=ALL` (listen on all interfaces)
- Autoplex: Command-line arguments for source/destination paths

### Configuration Files

**Generated from Templates:**
- `.env`: Contains secrets from Ansible Vault
- `Caddyfile`: Reverse proxy configuration with dynamic IP address
- `homeassistant/secrets.yaml`: Home Assistant secrets

**Static Files:**
- `docker-compose.yml`: Copied from `roles/docker/files/`

**Git Repositories:**
- Home Assistant config: Cloned from `git@github.com:connormason/homeassistant.git`
- Autoplex: Cloned from `https://github.com/danielmmetz/autoplex.git`
- PyAutoplex: Cloned from `git@github.com:connormason/pyautoplex.git`
- Caddy DNSimple: Cloned from `https://github.com/danielmmetz/caddy-dnsimple`

### Lutron Caseta Integration

Home Assistant requires Lutron Caseta certificates for smart home integration:
- Certificates stored in `inventory/group_vars/all/`
- Copied to `~/docker/homeassistant/` during role execution
- Files: `caseta.crt`, `caseta.key`, `caseta-bridge.crt`

## Custom Images

### Autoplex

**Source**: `https://github.com/danielmmetz/autoplex.git`
- **Language**: Go
- **Purpose**: File organization service
- **Build Process**:
  1. Clone repository to `~/docker/autoplex`
  2. Build Docker image from source
  3. Tag as `danielmmetz/autoplex:latest`
- **Used By**: Autoplex service in compose file

### PyAutoplex (Unused)

**Source**: `git@github.com:connormason/pyautoplex.git`
- **Language**: Python
- **Purpose**: Alternative file organization service
- **Build Process**: Same as Autoplex
- **Status**: Built but not active in docker-compose.yml

### Caddy DNSimple (Disabled)

**Source**: `https://github.com/danielmmetz/caddy-dnsimple`
- **Purpose**: Caddy reverse proxy with DNSimple DNS integration
- **Build Process**: Same as Autoplex
- **Status**: Built but Caddy service commented out

## Role Tasks

The role performs the following operations in order:

### 1. Docker Installation

```yaml
- Setup Docker repository (GPG key, apt repository)
- Install Docker Engine (docker-ce, docker-ce-cli, containerd.io)
- Install Docker Compose (both plugin and standalone)
- Start Docker daemon
```

### 2. Network Configuration

```yaml
- Detect host IP address (used in Caddyfile template)
```

### 3. Custom Image Builds

```yaml
- Clone Caddy DNSimple repository
- Build caddy-dnsimple Docker image
- Generate Caddyfile from template
- Generate .env file from template

- Clone Autoplex repository
- Build autoplex Docker image

- Clone PyAutoplex repository
- Build pyautoplex Docker image
```

### 4. Home Assistant Setup

```yaml
- Clone Home Assistant config repository
- Generate secrets.yaml from template
- Copy Lutron Caseta certificates from inventory
```

### 5. Docker Compose Deployment

```yaml
- Copy docker-compose.yml to ~/docker/
- Create backup of existing docker-compose.yml if present
```

**Note**: The role does NOT automatically start services (`docker-compose up`). This must be done manually.

## Usage

### Initial Deployment

Run the NAS bootstrap playbook:

```bash
# From repository root
./nas_bootstrap.sh

# Or manually
ansible-playbook playbooks/nas_bootstrap.yml -i inventory/inventory.yml --ask-become-pass
```

This will:
1. Install Docker
2. Build custom images
3. Deploy docker-compose.yml
4. Set up all configuration files

### Starting Services

```bash
# SSH to NAS
ssh nas

# Navigate to Docker directory
cd ~/docker

# Start all services
docker-compose up -d

# Or start specific services
docker-compose up -d plex sonarr radarr transmission
```

### Stopping Services

```bash
# Stop all services
docker-compose down

# Stop specific service
docker-compose stop plex

# Stop and remove containers, networks, volumes
docker-compose down -v
```

### Viewing Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f plex

# Last 100 lines
docker-compose logs --tail=100 sonarr
```

### Updating Services

```bash
# Pull latest images
docker-compose pull

# Recreate containers with new images
docker-compose up -d

# Update specific service
docker-compose pull plex
docker-compose up -d plex
```

### Rebuilding Custom Images

```bash
# Re-run Ansible role with specific tags
ansible-playbook playbooks/nas_bootstrap.yml -i inventory/inventory.yml --tags docker

# Or manually rebuild
cd ~/docker/autoplex
docker build -t danielmmetz/autoplex:latest .
docker-compose up -d autoplex
```

### Updating Configurations

```bash
# Update docker-compose.yml
ansible-playbook playbooks/nas_bootstrap.yml -i inventory/inventory.yml --tags docker,configfile

# Update Home Assistant config
ansible-playbook playbooks/nas_bootstrap.yml -i inventory/inventory.yml --tags homeassistant,configfile

# Or pull changes directly
cd ~/docker/homeassistant
git pull
docker-compose restart homeassistant
```

## Troubleshooting

### Service Won't Start

```bash
# Check service status
docker-compose ps

# View service logs
docker-compose logs <service_name>

# Check Docker daemon
sudo systemctl status docker

# Restart Docker daemon
sudo systemctl restart docker
```

### Permission Issues

```bash
# Check ownership of media directories
ls -la /storage/media/

# Fix ownership (should match PUID/PGID in compose)
sudo chown -R 1000:1000 /storage/media/

# Check directory permissions
sudo chmod -R 755 /storage/media/
```

### Network Issues

```bash
# Check if containers can communicate
docker exec sonarr ping transmission

# Inspect network
docker network inspect docker_default

# Check port conflicts
sudo netstat -tulpn | grep <port>

# Restart network
docker-compose down
docker network prune
docker-compose up -d
```

### PiHole DNS Not Working

```bash
# Check PiHole is listening
docker exec pihole netstat -tulpn | grep 53

# Check DNS resolution
docker exec pihole nslookup google.com

# Check firewall
sudo ufw status
sudo ufw allow 53/tcp
sudo ufw allow 53/udp

# View PiHole logs
docker-compose logs pihole
```

### Plex Not Accessible

```bash
# Plex uses host networking, check if port is bound
sudo netstat -tulpn | grep 32400

# Check Plex logs
docker-compose logs plex

# Try accessing locally
curl http://localhost:32400/web
```

### Home Assistant Issues

```bash
# Check Home Assistant logs
docker-compose logs homeassistant

# Validate configuration
docker exec home-assistant hass --script check_config

# Check Lutron certificates
ls -la ~/docker/homeassistant/caseta*
```

### Autoplex Not Moving Files

```bash
# Check Autoplex logs
docker-compose logs autoplex

# Verify source directories exist
ls -la /storage/media/downloads/complete/tv
ls -la /storage/media/downloads/complete/movies

# Check destination permissions
ls -la /storage/media/tv
ls -la /storage/media/movies

# Test manually
docker exec autoplex ls /downloads/complete/tv
```

### Storage Full

```bash
# Check disk usage
df -h /storage/media

# Find large files
du -sh /storage/media/*

# Clean old downloads
rm -rf /storage/media/downloads/complete/*

# Clean Docker volumes
docker system prune -a --volumes
```

### Image Build Failures

```bash
# Check repository clone
ls -la ~/docker/autoplex
ls -la ~/docker/caddy-dnsimple

# Re-clone repository
rm -rf ~/docker/autoplex
git clone https://github.com/danielmmetz/autoplex.git ~/docker/autoplex

# Manual build with verbose output
cd ~/docker/autoplex
docker build --no-cache -t danielmmetz/autoplex:latest .
```

## Adding New Services

### Step 1: Add Service to docker-compose.yml

Edit `roles/docker/files/docker-compose.yml`:

```yaml
  newservice:
    image: linuxserver/newservice
    container_name: newservice
    restart: unless-stopped
    environment:
      - PUID=1000
      - PGID=1000
      - TZ='America/Los_Angeles'
    volumes:
      - /storage/media/config/newservice:/config
    ports:
      - "8080:8080"
```

### Step 2: Add Storage Directories (if needed)

```bash
# Create config directory on NAS
ssh nas
sudo mkdir -p /storage/media/config/newservice
sudo chown 1000:1000 /storage/media/config/newservice
```

### Step 3: Add to Caddy Configuration (optional)

Edit `roles/docker/templates/Caddyfile.j2`:

```
newservice.conmason.com {
    tls {
        dns lego_deprecated dnsimple
    }

    reverse_proxy newservice:8080
}
```

### Step 4: Deploy Changes

```bash
# Update docker-compose.yml
ansible-playbook playbooks/nas_bootstrap.yml -i inventory/inventory.yml --tags docker,configfile

# Start new service
ssh nas
cd ~/docker
docker-compose up -d newservice
```

### Step 5: Add to Documentation

Update this README with:
- Service description in [Service Stack](#service-stack)
- Port mapping in [Network Configuration](#network-configuration)
- Dependencies in [Architecture](#architecture)

### Custom Image Services

If the service requires a custom image:

1. **Add repository variables** to `roles/docker/defaults/main.yml`:
   ```yaml
   newservice_repo_dest: "{{ docker_dir }}/newservice"
   newservice_repo_url: https://github.com/user/newservice.git
   newservice_repo_branch: main
   ```

2. **Add build task** to `roles/docker/tasks/main.yml`:
   ```yaml
   - name: Setup newservice
     block:
       - name: Clone newservice repo
         ansible.builtin.git:
           repo: "{{ newservice_repo_url }}"
           dest: "{{ newservice_repo_dest }}"
           version: "{{ newservice_repo_branch }}"
           clone: true
           update: true
           accept_hostkey: true

       - name: Build newservice image
         community.docker.docker_image:
           build:
             path: "{{ newservice_repo_dest }}"
           name: user/newservice
           tag: latest
           source: build
         become: true
   ```

3. **Use custom image** in docker-compose.yml:
   ```yaml
   newservice:
     image: user/newservice:latest
     # ...
   ```

## Maintenance

### Regular Tasks

**Weekly:**
- Check Docker container status: `docker-compose ps`
- Review service logs for errors: `docker-compose logs --tail=100`
- Monitor disk usage: `df -h /storage/media`

**Monthly:**
- Update service images: `docker-compose pull && docker-compose up -d`
- Clean old downloads: `rm -rf /storage/media/downloads/complete/*`
- Review PiHole statistics for blocked domains

**Quarterly:**
- Review and update service configurations
- Check for security updates: `apt update && apt list --upgradable`
- Backup Home Assistant configuration
- Review Sonarr/Radarr quality profiles

### Backup Strategy

**Configuration Backups:**
```bash
# Home Assistant (already in git)
cd ~/docker/homeassistant
git status
git add -A
git commit -m "Backup configuration"
git push

# Backup service configs
tar -czf ~/backups/docker-config-$(date +%Y%m%d).tar.gz /storage/media/config/

# Backup Docker directory
tar -czf ~/backups/docker-dir-$(date +%Y%m%d).tar.gz ~/docker/
```

**Media Library Backups:**
- Media files are large; consider separate backup strategy
- Metadata can be regenerated by Plex/Sonarr/Radarr
- Prioritize backing up `/storage/media/config/` over media files

**Database Backups:**
```bash
# Sonarr/Radarr databases are in config directories
# Stop services before backup
docker-compose stop sonarr radarr prowlarr

# Backup
tar -czf ~/backups/media-dbs-$(date +%Y%m%d).tar.gz \
  /storage/media/config/sonarr \
  /storage/media/config/radarr \
  /storage/media/config/prowlarr

# Restart services
docker-compose start sonarr radarr prowlarr
```

### Monitoring

**Service Health:**
```bash
# All container status
docker-compose ps

# Resource usage
docker stats

# Container uptime
docker-compose ps --format "table {{.Name}}\t{{.Status}}"
```

**Disk Usage:**
```bash
# Media storage
du -sh /storage/media/*

# Docker disk usage
docker system df

# Find large files
find /storage/media -type f -size +5G
```

**Network Monitoring:**
```bash
# Port listeners
sudo netstat -tulpn | grep -E "53|32400|9091|8989|7878"

# DNS queries (PiHole)
docker exec pihole pihole -c -e
```

**Log Rotation:**

Docker logs can grow large. Configure log rotation in `/etc/docker/daemon.json`:

```json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
```

Then restart Docker: `sudo systemctl restart docker`

### Security Updates

**Update Docker Engine:**
```bash
sudo apt update
sudo apt upgrade docker-ce docker-ce-cli containerd.io
sudo systemctl restart docker
```

**Update Container Images:**
```bash
cd ~/docker
docker-compose pull
docker-compose up -d
```

**Audit Open Ports:**
```bash
# Check exposed ports
sudo ufw status
sudo netstat -tulpn

# Restrict access if needed
sudo ufw allow from 192.168.1.0/24 to any port 8989  # Sonarr from local network only
```

**Review Credentials:**
- Rotate PiHole admin password in inventory vault
- Update DNSimple OAuth token if compromised
- Review Home Assistant user accounts

### Performance Optimization

**Docker Storage:**
```bash
# Clean unused images, containers, networks
docker system prune -a

# Clean unused volumes (CAUTION: may delete service data)
docker volume prune
```

**Plex Transcoding:**
- Consider hardware transcoding if available
- Monitor transcoding directory size
- Optimize library for direct play

**Transmission:**
- Limit active downloads
- Set bandwidth limits during peak hours
- Clean completed downloads regularly

### Ansible Redeployment

To redeploy the entire stack:

```bash
# Full redeployment
ansible-playbook playbooks/nas_bootstrap.yml -i inventory/inventory.yml --tags docker

# Update only configurations
ansible-playbook playbooks/nas_bootstrap.yml -i inventory/inventory.yml --tags docker,configfile

# Rebuild custom images
ansible-playbook playbooks/nas_bootstrap.yml -i inventory/inventory.yml --tags docker
```

This will:
- Update docker-compose.yml
- Rebuild custom images (Autoplex, Caddy)
- Regenerate configuration files (.env, Caddyfile)
- Update Home Assistant configuration

Note: Does not automatically restart services. Use `docker-compose up -d` after redeployment.

## Role Variables

### Default Variables

Defined in `roles/docker/defaults/main.yml`:

| Variable | Default | Description |
|----------|---------|-------------|
| `docker_dir` | `{{ ansible_facts['user_dir'] }}/docker` | Docker Compose project directory |
| `autoplex_repo_url` | `https://github.com/danielmmetz/autoplex.git` | Autoplex source repository |
| `autoplex_repo_branch` | `master` | Autoplex git branch |
| `pyautoplex_repo_url` | `git@github.com:connormason/pyautoplex.git` | PyAutoplex source repository |
| `pyautoplex_repo_branch` | `main` | PyAutoplex git branch |
| `caddy_dnsimple_repo_url` | `https://github.com/danielmmetz/caddy-dnsimple` | Caddy DNSimple source |
| `caddy_dnsimple_repo_branch` | `master` | Caddy DNSimple git branch |
| `homeassistant_repo_url` | `git@github.com:connormason/homeassistant.git` | Home Assistant config repo |
| `homeassistant_repo_branch` | `nas_bringup` | Home Assistant git branch |

### Required Variables from Inventory

Must be defined in inventory vault files:

| Variable | Source | Used By |
|----------|--------|---------|
| `dnsimple_oauth_token` | Vault | Caddy ACME DNS-01 |
| `pihole_web_password` | Vault | PiHole web UI |

Home Assistant secrets (defined in `templates/ha_secrets.yaml.j2`) - refer to Home Assistant repository for details.

## Related Documentation

- **Bootstrap Script**: `nas_bootstrap.sh` - Automated NAS setup
- **Playbook**: `playbooks/nas_bootstrap.yml` - Ansible playbook calling this role
- **Inventory**: `inventory/host_vars/nas/` - NAS-specific variables and secrets
- **Main CLAUDE.md**: Repository overview and common patterns
- **Docker Compose**: Official documentation at https://docs.docker.com/compose/
- **LinuxServer.io**: Images used by most services - https://www.linuxserver.io/

## License

Part of personal dotfiles repository. See repository root for license information.
