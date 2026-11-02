# Services

Docker Compose definitions for the home NAS stack. Each subdirectory contains a self-contained `compose.yml` for a
single service; `compose.base.yml` provides the shared project name and the `nas-network` bridge that ties them
together.

These files are deployed to the NAS at `~/docker/` by the `roles/docker` Ansible role and brought up by
`roles/docker/files/deploy.sh`, which discovers every subdirectory containing a `compose.yml` and runs
`docker compose -f compose.base.yml -f <service>/compose.yml up -d <service>`.

A service is **disabled** by renaming its `compose.yml` to `compose.yml.disabled`: both `deploy.sh` and the CI deploy
workflow only pick up directories containing a `compose.yml`. `pihole` and `homeassistant` are currently disabled.

## Quick Reference

All host ports below are bound on the NAS itself. Services without a host port are reachable only from inside the
`nas-network` bridge.

| Container        | Image                               | Host Port(s)                                  | Purpose                                     |
| ---------------- | ----------------------------------- | --------------------------------------------- | ------------------------------------------- |
| `caddy`          | `caddy:2-alpine`                    | `443/tcp`, `32443/tcp`                        | Tailscale HTTPS reverse proxy (see below)   |
| `glance`         | `glanceapp/glance`                  | `8080/tcp`                                    | Dashboard / homepage                        |
| `home-assistant` | `homeassistant/home-assistant`      | host networking (default `8123/tcp`)          | Home automation hub (**disabled**)          |
| `pihole`         | `pihole/pihole`                     | `53/tcp`, `53/udp`, `67/udp`, `8053/tcp` → 80 | DNS, ad-blocking, DHCP (**disabled**)       |
| `plex`           | `linuxserver/plex`                  | `32400/tcp`                                   | Media streaming server                      |
| `jellyfin`       | `linuxserver/jellyfin`              | `8096/tcp`, `7359/udp`                        | Media streaming server (Plex alternative)   |
| `prowlarr`       | `linuxserver/prowlarr`              | `9696/tcp`                                    | Indexer aggregator for Sonarr/Radarr        |
| `radarr`         | `linuxserver/radarr`                | `7878/tcp`                                    | Movie library management                    |
| `sonarr`         | `linuxserver/sonarr`                | `8989/tcp`                                    | TV library management                       |
| `transmission`   | `linuxserver/transmission`          | `9091/tcp`                                    | BitTorrent client (web UI)                  |
| `flaresolverr`   | `ghcr.io/flaresolverr/flaresolverr` | internal only (`8191/tcp` on the bridge)      | Cloudflare challenge solver for Prowlarr    |
| `autoplex`       | `danielmmetz/autoplex` (built)      | none                                          | Copies completed downloads into Plex layout |

LAN access is `http://<nas-host>:<port>` (e.g. `http://nas.local:8989` for Sonarr). The PiHole admin UI is
`http://<nas-host>:8053/admin`. Home Assistant now runs as a VM with its own LAN address (see below).

## Tailscale / HTTPS

`caddy` terminates TLS using certs issued by `tailscale cert` and proxies a subset of the services under a single
hostname. Configuration is templated by `roles/tailscale/templates/Caddyfile.j2` from the `tailscale_services` variable
in `inventory/host_vars/nas/vars.yml`.

| Service      | External URL                                | Notes                                           |
| ------------ | ------------------------------------------- | ----------------------------------------------- |
| Sonarr       | `https://nas.<tailnet>.ts.net/sonarr`       | Requires `UrlBase = /sonarr` in app settings    |
| Radarr       | `https://nas.<tailnet>.ts.net/radarr`       | Requires `UrlBase = /radarr` in app settings    |
| Prowlarr     | `https://nas.<tailnet>.ts.net/prowlarr`     | Requires `UrlBase = /prowlarr` in app settings  |
| Transmission | `https://nas.<tailnet>.ts.net/transmission` | Requires `rpc-url = /transmission/` in settings |
| PiHole       | `https://nas.<tailnet>.ts.net/pihole`       | Caddy rewrites `/pihole` → `/admin`             |
| Glance       | `https://nas.<tailnet>.ts.net/glance`       | Prefix stripped before proxying                 |
| Plex         | `https://nas.<tailnet>.ts.net:32443`        | Dedicated port; `ADVERTISE_IP` must match       |

## Services

### `caddy`

Reverse proxy fronting the stack on the Tailscale interface. Reads `Caddyfile` and TLS material from `/etc/caddy/` and
`/etc/tailscale/certs/` on the host, both populated by the `tailscale` role.

### `glance`

Web dashboard. Mounts `glance/config` and `glance/assets`, plus the Docker socket (read-only) so it can display
container status. Loads environment from a sibling `.env` file rendered by Ansible.

### `home-assistant`

**Disabled** (`compose.yml.disabled`) in favor of Home Assistant OS running as a libvirt VM, which adds the Supervisor
(apps, managed backups, OS updates). See [`vms/haos/`](../vms/haos/README.md) for the VM and the cutover steps.

The container ran on the host network (`network_mode: host`) for mDNS/SSDP discovery; `homeassistant/config/` was
populated by Home Assistant itself on first boot.

### `pihole`

**Disabled** (`compose.yml.disabled`). When re-enabling, confirm nothing else holds `:53`: libvirt's `default` network
runs `dnsmasq` on `192.168.122.1:53`, which blocks Docker from binding `0.0.0.0:53`. [`vms/haos/setup.sh`](../vms/haos/)
disables that network; otherwise bind the DNS ports to the NAS's LAN address.

DNS server and DHCP-capable ad-blocker. Binds privileged DNS/DHCP ports on the host; the admin UI is remapped to host
port `8053` to avoid colliding with other web services. `FTLCONF_webserver_api_password` is sourced from the environment
(the deploy `.env` file).

### `plex`

Media server. Uses the LinuxServer.io image with `PUID=1000/PGID=1000`. `ADVERTISE_IP` is set in the deploy `.env` to
the Tailscale HTTPS URL (`https://nas.<tailnet>.ts.net:32443`) so remote clients get a working external address.

### `jellyfin`

Media server running alongside Plex for evaluation. Uses the LinuxServer.io image with `PUID=1000/PGID=1000` and shares
the same `/storage/media/{tv,movies,music}` libraries as Plex. LAN-only HTTP on port `8096`; client auto-discovery on
`7359/udp`. Config persists at `/storage/media/config/jellyfin`.

### `prowlarr`, `radarr`, `sonarr`, `transmission`

Standard \*arr / download stack. All share the `/storage/media` tree on the host so completed downloads can be picked up
by Radarr/Sonarr and reorganized by autoplex.

### `flaresolverr`

Headless-browser sidecar used by Prowlarr to solve Cloudflare challenges. Not exposed to the host; other containers
reach it as `http://flaresolverr:8191` over the `nas-network` bridge.

### `autoplex`

Built from source (`danielmmetz/autoplex`) by the `docker` Ansible role. Watches
`/storage/media/downloads/complete/{tv,movies}` and copies new files into the `tv/` and `movies/` trees consumed by Plex
and Sonarr/Radarr. Talks to `transmission` for completion status.

## Deploying

The Ansible bootstrap installs `~/docker/deploy.sh` on the NAS. It is idempotent and used by both the initial provision
and the GitHub Actions CI workflow on push to `main`.

```bash
# Deploy everything
~/docker/deploy.sh all

# Deploy specific services
~/docker/deploy.sh sonarr radarr
```

### CI deploys

`.github/workflows/deploy.yml` joins the tailnet as `tag:ci`, rsyncs the changed service directories to `~/docker/`, and
runs `deploy.sh` for them over SSH. A push to `main` touching `services/<name>/` deploys just that service; a manual
`workflow_dispatch` run syncs all of `services/` and deploys the named service (default `all`):

```bash
gh workflow run deploy.yml -f service=glance
```

The runner authenticates to the NAS's regular `sshd` with a dedicated deploy key: the `NAS_SSH_PRIVATE_KEY` repository
secret, whose public half sits in `~/.ssh/authorized_keys` with the `restrict` option. To rotate it:

```bash
ssh-keygen -t ed25519 -N '' -C github-actions-deploy -f ~/.ssh/gha_deploy
echo "restrict $(cat ~/.ssh/gha_deploy.pub)" >> ~/.ssh/authorized_keys   # then drop the old github-actions-deploy line
gh secret set NAS_SSH_PRIVATE_KEY --repo connormason/dotfiles < ~/.ssh/gha_deploy && rm ~/.ssh/gha_deploy
```

**Tailscale SSH must stay off on the NAS** (`tailscale_ssh_enabled: false` in the NAS host vars). When enabled it
intercepts every SSH connection to the tailnet address and ignores the key. Tailscale SSH also never lets a tagged
device such as `tag:ci` into a user-owned node, so the deploy fails with
`tailnet policy does not permit you to SSH to this node`.
