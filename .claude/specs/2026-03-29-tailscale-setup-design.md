# Tailscale Setup Design

**Date:** 2026-03-29
**Status:** Approved
**Scope:** NAS (Debian) + Mac (macOS) Tailscale configuration via Ansible

## Goal

Set up Tailscale on the home NAS and Mac to enable secure remote access to NAS Docker services (Plex, Sonarr, Radarr,
Transmission, Prowlarr, PiHole, Glance) over HTTPS via Tailscale, with MagicDNS and Tailscale SSH. Make the setup
fully repeatable via Ansible.

## Decisions

- **Auth method:** Pre-generated reusable auth key stored in Ansible Vault
- **DNS:** MagicDNS enabled for human-readable addressing
- **SSH:** Tailscale SSH enabled on the NAS
- **HTTPS:** Tailscale cert provisioning + Caddy reverse proxy for NAS services
- **Architecture:** Fully self-contained Ansible role (no `artis3n.tailscale` Galaxy dependency)
- **Plex networking:** Move from `network_mode: host` to bridge with port mapping
- **Home Assistant:** Excluded from Tailscale/Caddy; stays on host networking
- **Routing strategy:** Path-based routing for services that support URL base configuration; dedicated Caddy port for
Plex (which does not support path prefixes)

## Role Structure

```
roles/tailscale/
├── README.md                              # Setup guide and documentation
├── defaults/main.yml                      # Default variables (overridable)
├── tasks/
│   ├── main.yml                           # Entry point - dispatches to platform tasks
│   ├── install_debian.yml                 # Apt repo setup + package install (NAS)
│   ├── install_macos.yml                  # Ensure Tailscale is present via brew cask
│   ├── configure.yml                      # tailscale set/login with flags (shared logic)
│   └── https_certs.yml                    # Tailscale HTTPS cert provisioning (NAS only)
├── handlers/main.yml                      # Restart tailscaled handler
└── templates/
    ├── Caddyfile.j2                       # Caddy reverse proxy config (NAS only)
    ├── tailscale-cert-renewal.service.j2  # Systemd service for cert renewal
    └── tailscale-cert-renewal.timer.j2    # Systemd timer for weekly cert renewal
```

## Task Flow

1. Validate `tailscale_auth_key` is not empty (fail with clear error pointing to vault setup)
2. `main.yml` detects OS via `ansible_os_family` and dispatches to the correct install task
3. Install task adds Tailscale (apt repo + package on Debian, brew cask check on macOS)
4. `configure.yml` runs `tailscale set` + `tailscale login` with platform-appropriate flags
5. `https_certs.yml` provisions TLS certs, deploys systemd renewal timer, and deploys Caddy (NAS only, gated by
`tailscale_https_enabled`)

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
3. **CLI path:** On macOS, the Tailscale CLI is at `/Applications/Tailscale.app/Contents/MacOS/Tailscale`. The
`configure.yml` task will use this full path when `ansible_os_family == "Darwin"`. The Tailscale GUI app must be
4. launched at least once to set up the system extension before the CLI works.

## Configuration

### Approach: `tailscale set` + `tailscale login`

Use `tailscale set` (idempotent flag configuration) combined with `tailscale login` (authentication), rather than the
older `tailscale up` which combines both:

- `tailscale set` applies configuration flags and is inherently idempotent
- `tailscale login --authkey=...` handles authentication

### Idempotency

Check `tailscale status --json | jq .BackendState` before authenticating:
- If `"Running"` — already authenticated, skip `tailscale login`
- If `"NeedsLogin"` or `"Stopped"` — run `tailscale login --authkey=...`

Always run `tailscale set` with the desired flags (it's idempotent).

### NAS Configuration

```
tailscale set --ssh --hostname=nas --accept-dns=true
tailscale login --authkey=<key>   # Only if not already authenticated
```

### Mac Configuration

```
/Applications/Tailscale.app/Contents/MacOS/Tailscale set --accept-dns=true
/Applications/Tailscale.app/Contents/MacOS/Tailscale login --authkey=<key>   # Only if not already authenticated
```

### Auth Key Notes

- Generate a **reusable** auth key in the Tailscale admin console
- Reusable auth keys have a maximum lifetime (typically 90 days) — they will need periodic regeneration
- After initial authentication, re-running the playbook skips `tailscale login` if `BackendState == "Running"`
- Store the key in Ansible Vault (`inventory/group_vars/all/vault.yml`)

## HTTPS: Tailscale Certs + Caddy Reverse Proxy

### Cert Provisioning

- `tailscale cert <hostname>.<tailnet>.ts.net` outputs cert + key files to `tailscale_cert_dir`
(default: `/etc/tailscale/certs`)
- Certs are valid ~90 days and auto-renew via Let's Encrypt
- The role deploys two systemd units for automatic renewal:

**`tailscale-cert-renewal.service`:** Runs `tailscale cert` to refresh certs, then reloads Caddy via
`docker exec caddy caddy reload --config /etc/caddy/Caddyfile`

**`tailscale-cert-renewal.timer`:** Fires weekly (e.g., `OnCalendar=weekly`) to trigger the service

Both units are templated and deployed by `https_certs.yml`. Added to the Files Changed table.

### Caddy Reverse Proxy

Caddy is added to the existing `roles/docker/files/docker-compose.yml` so it shares the default Docker Compose
network with all other services. This means Caddy can reach services by container name (e.g., `sonarr:8989`).

**Caddy Docker container:**

```yaml
caddy:
  image: caddy:2-alpine
  container_name: caddy
  restart: unless-stopped
  ports:
    - "443:443"       # Main HTTPS (path-based services)
    - "32443:32443"   # Plex HTTPS (dedicated port)
  volumes:
    - /etc/tailscale/certs:/certs:ro                # Tailscale TLS certs
    - /etc/caddy/Caddyfile:/etc/caddy/Caddyfile:ro  # Generated config
    - caddy_data:/data                              # Caddy state
```

The existing commented-out Caddy service (`danielmmetz/caddy-dnsimple`) will be replaced with this configuration.
The existing `caddy_data: {}` top-level volume declaration should be retained.

**Host port mappings:** Existing host port mappings for services (e.g., `9091:9091` for Transmission,
`8989:8989` for Sonarr) will be kept so that services remain accessible on the LAN without Tailscale. Caddy provides
Tailscale-only HTTPS access as an additional layer, not a replacement for LAN access.

**Note on internal ports:** Caddy connects to containers via Docker's internal DNS. The ports used are the
container-internal ports (e.g., PiHole's web UI is on port 80 inside the container, not the host-mapped 8053).
This is the correct behavior for container-to-container communication on the Docker Compose network.

### Service Routing

**Path-based routing (port 443)** for services that support URL base configuration:

| Service | Internal Port | URL Path | Caddy Directive | App Config Required |
|---|---|---|---|---|
| Sonarr | 8989 | `/sonarr` | `handle` (preserves prefix) | Set `UrlBase` to `/sonarr` in Settings > General |
| Radarr | 7878 | `/radarr` | `handle` (preserves prefix) | Set `UrlBase` to `/radarr` in Settings > General |
| Prowlarr | 9696 | `/prowlarr` | `handle` (preserves prefix) | Set `UrlBase` to `/prowlarr` in Settings > General |
| Transmission | 9091 | `/transmission` | `handle` (preserves prefix) | Set `rpc-url` to `/transmission/` in `settings.json` |
| Glance | 8080 | `/glance` | `handle_path` (strips prefix) | No app config needed; Glance receives requests at `/` |

**PiHole** is handled as a special case outside the loop: Caddy matches `/pihole/*`, strips the prefix, and rewrites
to `/admin/*` (PiHole's web UI lives at `/admin`).

**Caddy directive choice:**
- `handle /path/*` — matches the prefix but does NOT strip it. Used for services with `UrlBase` configured
(Sonarr, Radarr, Prowlarr, Transmission) because they expect the full path.
- `handle_path /path/*` — matches the prefix AND strips it. Used for services that don't have URL base support
(Glance) or where we want to rewrite the path (PiHole).

**Dedicated port routing** for services that do not support path prefixes:

| Service | Internal Port | Caddy Port | URL |
|---|---|---|---|
| Plex | 32400 | 32443 | `https://nas.<tailnet>.ts.net:32443` |

**Excluded services** (no web UI or excluded by design):
- **Flaresolverr:** Backend proxy, no user-facing web UI
- **Autoplex:** Background file mover, no web UI
- **Home Assistant:** Excluded per the Decisions section (stays on host networking, not behind Tailscale)

### Caddyfile Template

The `Caddyfile.j2` template is rendered by the tailscale role and placed at `/etc/caddy/Caddyfile` on the NAS. The
Caddy container (defined in the docker role's compose file) mounts this path.

Skeleton:

```
# Path-based services on :443
https://{{ tailscale_hostname }}.{{ tailscale_tailnet_name }} {
    tls /certs/{{ tailscale_hostname }}.{{ tailscale_tailnet_name }}.crt /certs/{{ tailscale_hostname }}.{{ tailscale_tailnet_name }}.key

{% for svc in tailscale_services if not svc.dedicated_port is defined and svc.name != 'pihole' %}
{% if svc.strip_prefix | default(false) %}
    handle_path /{{ svc.path }}/* {
        reverse_proxy {{ svc.name }}:{{ svc.port }}
    }
{% else %}
    handle /{{ svc.path }}/* {
        reverse_proxy {{ svc.name }}:{{ svc.port }}
    }
{% endif %}
{% endfor %}

    # PiHole special case: strip /pihole prefix and rewrite to /admin
    handle_path /pihole/* {
        rewrite * /admin{uri}
        reverse_proxy pihole:80
    }
}

# Plex on dedicated port
https://{{ tailscale_hostname }}.{{ tailscale_tailnet_name }}:{{ tailscale_plex_port }} {
    tls /certs/{{ tailscale_hostname }}.{{ tailscale_tailnet_name }}.crt /certs/{{ tailscale_hostname }}.{{ tailscale_tailnet_name }}.key
    reverse_proxy plex:32400
}
```

**Template syntax note:** All `{{ ... }}` in the skeleton above are Jinja2 variables rendered at deploy time by
Ansible. The output Caddyfile will contain the actual values (e.g., `https://nas.tail1234.ts.net`).

### Plex Network Mode Change

Move Plex from `network_mode: host` to bridge networking with explicit port mapping (`32400:32400`). This is safe
because:
- Remote access is handled by Tailscale + Caddy, not DLNA/GDM discovery
- Bridge networking is more secure (only explicitly mapped ports are exposed)
- Caddy can now reach Plex by container name (`plex:32400`) on the Docker network

**Plex `ADVERTISE_IP`:** When on bridge networking, Plex cannot discover its own external address. Add
`ADVERTISE_IP=https://nas.<tailnet>.ts.net:32443` to the Plex container's environment variables so remote clients
connect through the Tailscale/Caddy path.

### Operational Notes

**Firewall:** Caddy binds to host ports 443 and 32443. If the NAS has `ufw` or `iptables` rules, these ports may need
to be allowed. However, since Tailscale traffic arrives via the `tailscale0` interface (already handled by
`tailscaled`), firewall rules typically do not need modification. Verify during first deployment.

**Role ordering:** The tailscale role's `https_certs.yml` deploys the Caddyfile and the cert renewal service
references the Caddy container. The docker role must run first so the Caddy container exists. In `nas_bootstrap.yml`,
the tailscale role is already ordered after docker. If running `--tags tailscale` alone, the docker stack must already
be up.

## Variables

### defaults/main.yml

```yaml
# Authentication
tailscale_auth_key: ""                      # Override in vault — role fails if empty

# Node configuration
tailscale_hostname: "{{ inventory_hostname }}"
tailscale_ssh_enabled: true
tailscale_accept_dns: true

# HTTPS (NAS only)
tailscale_https_enabled: false
tailscale_tailnet_name: ""                  # e.g., "tail1234.ts.net"
tailscale_cert_dir: "/etc/tailscale/certs"
tailscale_caddy_config_dir: "/etc/caddy"
tailscale_services: []                      # List of {name, port, path} dicts
tailscale_plex_port: 32443                  # Dedicated Caddy port for Plex

# Platform
tailscale_version: ""                       # Empty = latest available
tailscale_macos_cli: "/Applications/Tailscale.app/Contents/MacOS/Tailscale"
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
  - { name: sonarr, port: 8989, path: sonarr }
  - { name: radarr, port: 7878, path: radarr }
  - { name: transmission, port: 9091, path: transmission }
  - { name: prowlarr, port: 9696, path: prowlarr }
  - { name: pihole, port: 80, path: pihole }       # Handled as special case in Caddyfile template
  - { name: glance, port: 8080, path: glance, strip_prefix: true }
  - { name: plex, port: 32400, dedicated_port: 32443 }
```

## Files Changed

| File | Action | Purpose |
|---|---|---|
| `roles/tailscale/defaults/main.yml` | Create | Default variables |
| `roles/tailscale/tasks/main.yml` | Rewrite | Entry point with auth key validation, OS dispatch |
| `roles/tailscale/tasks/install_debian.yml` | Create | Apt repo + package install |
| `roles/tailscale/tasks/install_macos.yml` | Create | Ensure brew cask present |
| `roles/tailscale/tasks/configure.yml` | Create | `tailscale set` + `tailscale login` with idempotency |
| `roles/tailscale/tasks/https_certs.yml` | Create | Cert provisioning, systemd timer, Caddyfile deployment |
| `roles/tailscale/handlers/main.yml` | Create | Restart tailscaled handler |
| `roles/tailscale/templates/Caddyfile.j2` | Create | Reverse proxy config |
| `roles/tailscale/templates/tailscale-cert-renewal.service.j2` | Create | Systemd service for cert renewal + Caddy reload |
| `roles/tailscale/templates/tailscale-cert-renewal.timer.j2` | Create | Systemd weekly timer |
| `roles/tailscale/README.md` | Rewrite | Full setup guide and documentation |
| `playbooks/nas_bootstrap.yml` | Edit | Uncomment tailscale role |
| `playbooks/local_bootstrap.yml` | Edit | Add tailscale role for Mac |
| `roles/docker/files/docker-compose.yml` | Edit | Move Plex to bridge, replace commented-out Caddy with new config |
| `roles/requirements.yml` | Edit | Remove `artis3n.tailscale` dependency |
| `inventory/group_vars/all/vault.yml` | Edit | Add tailscale_auth_key + tailnet_name |
| `inventory/host_vars/nas/vars.yml` | Edit | Add NAS-specific tailscale vars |

## Manual Steps (Not Automatable)

1. **Generate auth key:** In Tailscale admin console, create a reusable auth key (note: expires after ~90 days,
regenerate as needed)
2. **Store in vault:** `ansible-vault edit inventory/group_vars/all/vault.yml` and add the key
3. **Enable HTTPS certs:** In Tailscale admin console, ensure HTTPS certificates are enabled for your tailnet
4. **First playbook run:** Execute `nas_bootstrap.sh` to bootstrap everything
5. **Configure app URL bases:** After first run, set URL base paths in each service's web UI:
   - Sonarr: Settings > General > URL Base = `/sonarr`
   - Radarr: Settings > General > URL Base = `/radarr`
   - Prowlarr: Settings > General > URL Base = `/prowlarr`
   - Transmission: Edit `settings.json`, set `rpc-url` to `/transmission/`
6. **macOS first launch:** Open Tailscale GUI app at least once to set up the system extension before running the Mac
playbook
7. **Verify:** Access `https://nas.<tailnet>.ts.net/sonarr` and `https://nas.<tailnet>.ts.net:32443` (Plex) from a
device on your tailnet
