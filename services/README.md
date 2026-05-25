# Services

Docker Compose definitions for the home NAS stack. Each subdirectory contains a self-contained
`compose.yml` for a single service; `compose.base.yml` provides the shared project name and the
`nas-network` bridge that ties them together.

These files are deployed to the NAS at `~/docker/` by the `roles/docker` Ansible role and brought
up by `roles/docker/files/deploy.sh`, which discovers every subdirectory containing a `compose.yml`
and runs `docker compose -f compose.base.yml -f <service>/compose.yml up -d <service>`.

## Quick Reference

All host ports below are bound on the NAS itself. Services without a host port are reachable only
from inside the `nas-network` bridge (or, for Home Assistant, the host network namespace).

| Container        | Image                              | Host Port(s)                                  | Purpose                                       |
|------------------|------------------------------------|-----------------------------------------------|-----------------------------------------------|
| `caddy`          | `caddy:2-alpine`                   | `443/tcp`, `32443/tcp`                        | Tailscale HTTPS reverse proxy (see below)     |
| `glance`         | `glanceapp/glance`                 | `8080/tcp`                                    | Dashboard / homepage                          |
| `home-assistant` | `homeassistant/home-assistant`     | host networking (default `8123/tcp`)          | Home automation hub                           |
| `pihole`         | `pihole/pihole`                    | `53/tcp`, `53/udp`, `67/udp`, `8053/tcp` → 80 | DNS, ad-blocking, DHCP                        |
| `plex`           | `linuxserver/plex`                 | `32400/tcp`                                   | Media streaming server                        |
| `jellyfin`       | `linuxserver/jellyfin`             | `8096/tcp`, `7359/udp`                        | Media streaming server (Plex alternative)     |
| `prowlarr`       | `linuxserver/prowlarr`             | `9696/tcp`                                    | Indexer aggregator for Sonarr/Radarr          |
| `radarr`         | `linuxserver/radarr`               | `7878/tcp`                                    | Movie library management                      |
| `sonarr`         | `linuxserver/sonarr`               | `8989/tcp`                                    | TV library management                         |
| `transmission`   | `linuxserver/transmission`         | `9091/tcp`                                    | BitTorrent client (web UI)                    |
| `flaresolverr`   | `ghcr.io/flaresolverr/flaresolverr`| internal only (`8191/tcp` on the bridge)      | Cloudflare challenge solver for Prowlarr      |
| `autoplex`       | `danielmmetz/autoplex` (built)     | none                                          | Copies completed downloads into Plex layout   |

LAN access is `http://<nas-host>:<port>` (e.g. `http://nas.local:8989` for Sonarr). The PiHole
admin UI is `http://<nas-host>:8053/admin`. Home Assistant listens directly on the host network at
port `8123`.

## Tailscale / HTTPS

`caddy` terminates TLS using certs issued by `tailscale cert` and proxies a subset of the services
under a single hostname. Configuration is templated by `roles/tailscale/templates/Caddyfile.j2`
from the `tailscale_services` variable in `inventory/host_vars/nas/vars.yml`.

| Service       | External URL                                   | Notes                                              |
|---------------|------------------------------------------------|----------------------------------------------------|
| Sonarr        | `https://nas.<tailnet>.ts.net/sonarr`          | Requires `UrlBase = /sonarr` in app settings       |
| Radarr        | `https://nas.<tailnet>.ts.net/radarr`          | Requires `UrlBase = /radarr` in app settings       |
| Prowlarr      | `https://nas.<tailnet>.ts.net/prowlarr`        | Requires `UrlBase = /prowlarr` in app settings     |
| Transmission  | `https://nas.<tailnet>.ts.net/transmission`    | Requires `rpc-url = /transmission/` in settings    |
| PiHole        | `https://nas.<tailnet>.ts.net/pihole`          | Caddy rewrites `/pihole` → `/admin`                |
| Glance        | `https://nas.<tailnet>.ts.net/glance`          | Prefix stripped before proxying                    |
| Plex          | `https://nas.<tailnet>.ts.net:32443`           | Dedicated port; `ADVERTISE_IP` must match          |

## Services

### `caddy`
Reverse proxy fronting the stack on the Tailscale interface. Reads `Caddyfile` and TLS material
from `/etc/caddy/` and `/etc/tailscale/certs/` on the host, both populated by the `tailscale` role.

### `glance`
Web dashboard. Mounts `glance/config` and `glance/assets`, plus the Docker socket (read-only) so it
can display container status. Loads environment from a sibling `.env` file rendered by Ansible.

### `home-assistant`
Runs on the host network (`network_mode: host`) so it can discover devices via mDNS/SSDP and reach
the Lutron Caseta bridge directly. Secrets, certificates, and YAML config live under
`homeassistant/config/`, populated during the `docker` role's `homeassistant` task.

### `pihole`
DNS server and DHCP-capable ad-blocker. Binds privileged DNS/DHCP ports on the host; the admin UI
is remapped to host port `8053` to avoid colliding with other web services. `FTLCONF_webserver_api_password`
is sourced from the environment (the deploy `.env` file).

### `plex`
Media server. Uses the LinuxServer.io image with `PUID=1000/PGID=1000`. `ADVERTISE_IP` is set in the
deploy `.env` to the Tailscale HTTPS URL (`https://nas.<tailnet>.ts.net:32443`) so remote clients
get a working external address.

### `jellyfin`
Media server running alongside Plex for evaluation. Uses the LinuxServer.io image with
`PUID=1000/PGID=1000` and shares the same `/storage/media/{tv,movies,music}` libraries as Plex.
LAN-only HTTP on port `8096`; client auto-discovery on `7359/udp`. Config persists at
`/storage/media/config/jellyfin`.

### `prowlarr`, `radarr`, `sonarr`, `transmission`
Standard *arr / download stack. All share the `/storage/media` tree on the host so completed
downloads can be picked up by Radarr/Sonarr and reorganized by autoplex.

### `flaresolverr`
Headless-browser sidecar used by Prowlarr to solve Cloudflare challenges. Not exposed to the host;
other containers reach it as `http://flaresolverr:8191` over the `nas-network` bridge.

### `autoplex`
Built from source (`danielmmetz/autoplex`) by the `docker` Ansible role. Watches
`/storage/media/downloads/complete/{tv,movies}` and copies new files into the `tv/` and `movies/`
trees consumed by Plex and Sonarr/Radarr. Talks to `transmission` for completion status.

## Deploying

The Ansible bootstrap installs `~/docker/deploy.sh` on the NAS. It is idempotent and used by both
the initial provision and the GitHub Actions CI workflow on push to `main`.

```bash
# Deploy everything
~/docker/deploy.sh all

# Deploy specific services
~/docker/deploy.sh sonarr radarr
```
