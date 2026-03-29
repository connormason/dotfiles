# tailscale

Sets up [Tailscale VPN](https://tailscale.com/) on Debian and macOS systems.

## Features

- Installs Tailscale from official apt repository (Debian) or verifies brew cask (macOS)
- Configures Tailscale with idempotent `tailscale set` + `tailscale login`
- Enables Tailscale SSH on Linux hosts
- Provisions HTTPS certificates via `tailscale cert` (NAS only)
- Deploys Caddy reverse proxy for Docker services (NAS only)
- Automatic weekly cert renewal via systemd timer

## Prerequisites

1. **Tailscale account** with a tailnet configured
2. **Reusable auth key** generated in [Tailscale admin console](https://login.tailscale.com/admin/settings/keys)
   - Note: Reusable auth keys expire after ~90 days and must be regenerated
3. **HTTPS certificates enabled** in Tailscale admin console (for HTTPS feature)
4. **macOS only:** Launch Tailscale.app at least once to set up the system extension

## Required Variables

Set these in your Ansible Vault (`inventory/group_vars/all/vault.yml`):

```yaml
tailscale_auth_key: "tskey-auth-..."
tailscale_tailnet_name: "your-tailnet.ts.net"
```

## Optional Variables

See `defaults/main.yml` for all available variables and their defaults.

Key overrides for NAS (`inventory/host_vars/nas/vars.yml`):

```yaml
tailscale_https_enabled: true
tailscale_services:
  - { name: sonarr,       port: 8989,    path: sonarr }
  - { name: radarr,       port: 7878,    path: radarr }
  - { name: transmission, port: 9091,    path: transmission }
  - { name: prowlarr,     port: 9696,    path: prowlarr }
  - { name: pihole,       port: 80,      path: pihole }
  - { name: glance,       port: 8080,    path: glance, strip_prefix: true }
  - { name: plex,         port: 32400,   dedicated_port: 32443 }
```

## Service Routing

Services are accessible via `https://nas.<tailnet>.ts.net/<path>`:

| Service | URL | Notes |
|---|---|---|
| Sonarr | `/sonarr` | Requires `UrlBase = /sonarr` in app settings |
| Radarr | `/radarr` | Requires `UrlBase = /radarr` in app settings |
| Prowlarr | `/prowlarr` | Requires `UrlBase = /prowlarr` in app settings |
| Transmission | `/transmission` | Requires `rpc-url = /transmission/` in settings.json |
| PiHole | `/pihole` | Automatically rewrites to `/admin` |
| Glance | `/glance` | No app config needed |
| Plex | `:32443` (dedicated port) | Access via `https://nas.<tailnet>.ts.net:32443` |

## Post-Deployment Steps

After first playbook run:

1. Set URL base paths in each service's web UI (see table above)
2. Set `ADVERTISE_IP=https://nas.<tailnet>.ts.net:32443` in the Docker `.env` file for Plex
3. Restart the Docker stack: `docker compose up -d`
4. Verify access from a device on your tailnet

## Running

```bash
# Full NAS bootstrap
./nas_bootstrap.sh

# Tailscale only
ansible-playbook playbooks/nas_bootstrap.yml -i inventory/inventory.yml --ask-become-pass -vv --tags tailscale

# Mac bootstrap
./local_bootstrap.sh

# Tailscale only (Mac)
ansible-playbook playbooks/local_bootstrap.yml -i inventory/inventory.yml --ask-become-pass -vv --tags tailscale
```

## Cert Renewal

Certs are automatically renewed weekly via a systemd timer. To check status:

```bash
# Timer status
systemctl status tailscale-cert-renewal.timer

# Last renewal run
journalctl -u tailscale-cert-renewal.service --no-pager -n 20

# Manual renewal
sudo systemctl start tailscale-cert-renewal.service
```
