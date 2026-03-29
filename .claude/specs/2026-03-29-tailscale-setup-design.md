# Tailscale Setup Design

**Date:** 2026-03-29
**Status:** Approved
**Scope:** NAS (Debian) + Mac (macOS) Tailscale configuration via Ansible

## Goal

Set up Tailscale on the home NAS and Mac to enable secure remote access to NAS Docker services (Plex, Sonarr, Radarr, Transmission, Prowlarr, PiHole, Glance) over HTTPS via Tailscale, with MagicDNS and Tailscale SSH. Make the setup fully repeatable via Ansible.

## Decisions

- **Auth method:** Pre-generated reusable auth key stored in Ansible Vault
- **DNS:** MagicDNS enabled for human-readable addressing
- **SSH:** Tailscale SSH enabled on the NAS
- **HTTPS:** Tailscale cert provisioning + Caddy reverse proxy for NAS services
- **Architecture:** Fully self-contained Ansible role (no `artis3n.tailscale` Galaxy dependency)
- **Plex networking:** Move from `network_mode: host` to bridge with port mapping
- **Home Assistant:** Excluded from Tailscale/Caddy; stays on host networking

## Role Structure

```
roles/tailscale/
├── README.md                  # Setup guide and documentation
├── defaults/main.yml          # Default variables (overridable)
├── tasks/
│   ├── main.yml               # Entry point - dispatches to platform tasks
│   ├── install_debian.yml     # Apt repo setup + package install (NAS)
│   ├── install_macos.yml      # Ensure Tailscale is present via brew cask
│   ├── configure.yml          # tailscale up with flags (shared logic)
│   └── https_certs.yml        # Tailscale HTTPS cert provisioning (NAS only)
├── handlers/main.yml          # Restart tailscaled handler
└── templates/
    └── Caddyfile.j2           # Caddy reverse proxy config (NAS only)
```

## Task Flow

1. `main.yml` detects OS via `ansible_os_family` and dispatches to the correct install task
2. Install task adds Tailscale (apt repo + package on Debian, brew cask check on macOS)
3. `configure.yml` runs `tailscale up` with platform-appropriate flags
4. `https_certs.yml` provisions TLS certs and deploys Caddy (NAS only, gated by `tailscale_https_enabled`)

## Installation

### Debian (NAS)

1. Add Tailscale's GPG signing key from `https://pkgs.tailscale.com/stable/debian/`
2. Add Tailscale stable apt repository for the host's Debian version
3. Install `tailscale` package via apt (`state: present`, not `latest`)
4. Enable and start `tailscaled` systemd service
5. `tailscale_version` variable allows pinning a specific version (default: latest available)

### macOS (Mac)

1. Verify Tailscale brew cask is present (safety check; `macos` role already installs it)
2. No service management needed (macOS Tailscale runs as a GUI app/system extension)

## Configuration (`tailscale up`)

### Idempotency

Check `tailscale status --json` before running `tailscale up`. Skip if already connected with correct settings.

### NAS Flags

- `--authkey={{ tailscale_auth_key }}`
- `--ssh`
- `--hostname={{ tailscale_hostname }}` (defaults to `nas`)
- `--accept-dns=true`

### Mac Flags

- `--authkey={{ tailscale_auth_key }}`
- `--accept-dns=true`

## HTTPS: Tailscale Certs + Caddy Reverse Proxy

### Cert Provisioning

- `tailscale cert <hostname>.<tailnet>.ts.net` outputs cert + key files to `tailscale_cert_dir`
- Certs are valid ~90 days and auto-renew via Let's Encrypt
- A systemd timer runs `tailscale cert` weekly to keep certs fresh

### Caddy Reverse Proxy

A Caddy Docker container serves as the HTTPS reverse proxy for all NAS services. The Caddyfile is generated from a Jinja2 template based on the `tailscale_services` variable.

**Caddy container configuration:**
- Mounted volumes: cert directory (read-only) + Caddyfile
- Listens on port 443
- TLS configured with Tailscale-provisioned certs

**Service routing (path-based):**

| Service | Internal Port | URL Path |
|---|---|---|
| Sonarr | 8989 | `/sonarr` |
| Radarr | 7878 | `/radarr` |
| Transmission | 9091 | `/transmission` |
| Prowlarr | 9696 | `/prowlarr` |
| PiHole | 80 | `/pihole` |
| Plex | 32400 | `/plex` |
| Glance | 8080 | `/glance` |

All services accessed via `https://nas.<tailnet>.ts.net/<path>`.

### Plex Network Mode Change

Move Plex from `network_mode: host` to bridge networking with explicit port mapping (`32400:32400`). This is safe because:
- Remote access is handled by Tailscale + Caddy, not DLNA/GDM discovery
- Bridge networking is more secure (only explicitly mapped ports are exposed)

## Variables

### defaults/main.yml

```yaml
# Authentication
tailscale_auth_key: ""              # Override in vault

# Node configuration
tailscale_hostname: "{{ inventory_hostname }}"
tailscale_ssh_enabled: true
tailscale_accept_dns: true

# HTTPS (NAS only)
tailscale_https_enabled: false
tailscale_tailnet_name: ""          # e.g., "tail1234.ts.net"
tailscale_cert_dir: "/etc/tailscale/certs"
tailscale_services: []              # List of {name, port, path} dicts

# Platform
tailscale_version: ""               # Empty = latest available
```

### Vault (inventory/group_vars/all/vault.yml)

```yaml
tailscale_auth_key: "tskey-auth-..."
tailscale_tailnet_name: "your-tailnet.ts.net"
```

### NAS Host Vars (inventory/host_vars/nas/vars.yml)

```yaml
tailscale_https_enabled: true
tailscale_services:
  - { name: sonarr, port: 8989, path: /sonarr }
  - { name: radarr, port: 7878, path: /radarr }
  - { name: transmission, port: 9091, path: /transmission }
  - { name: prowlarr, port: 9696, path: /prowlarr }
  - { name: pihole, port: 80, path: /pihole }
  - { name: plex, port: 32400, path: /plex }
  - { name: glance, port: 8080, path: /glance }
```

## Files Changed

| File | Action | Purpose |
|---|---|---|
| `roles/tailscale/defaults/main.yml` | Create | Default variables |
| `roles/tailscale/tasks/main.yml` | Rewrite | Entry point dispatching to platform tasks |
| `roles/tailscale/tasks/install_debian.yml` | Create | Apt repo + package install |
| `roles/tailscale/tasks/install_macos.yml` | Create | Ensure brew cask present |
| `roles/tailscale/tasks/configure.yml` | Create | `tailscale up` with idempotency |
| `roles/tailscale/tasks/https_certs.yml` | Create | Cert provisioning + renewal timer |
| `roles/tailscale/handlers/main.yml` | Create | Restart tailscaled handler |
| `roles/tailscale/templates/Caddyfile.j2` | Create | Reverse proxy config |
| `roles/tailscale/README.md` | Rewrite | Full setup guide and documentation |
| `playbooks/nas_bootstrap.yml` | Edit | Uncomment tailscale role |
| `playbooks/local_bootstrap.yml` | Edit | Add tailscale role for Mac |
| `roles/docker/files/docker-compose.yml` | Edit | Move Plex to bridge, add Caddy service |
| `roles/requirements.yml` | Edit | Remove `artis3n.tailscale` dependency |
| `inventory/group_vars/all/vault.yml` | Edit | Add tailscale_auth_key + tailnet_name |
| `inventory/host_vars/nas/vars.yml` | Edit | Add NAS-specific tailscale vars |

## Manual Steps (Not Automatable)

1. **Generate auth key:** In Tailscale admin console, create a reusable auth key
2. **Store in vault:** `ansible-vault edit inventory/group_vars/all/vault.yml` and add the key
3. **Enable HTTPS certs:** In Tailscale admin console, ensure HTTPS certificates are enabled for your tailnet
4. **First playbook run:** Execute `nas_bootstrap.sh` to bootstrap everything
5. **Verify:** Access `https://nas.<tailnet>.ts.net/sonarr` from a device on your tailnet
