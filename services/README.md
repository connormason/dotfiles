[Project Root](../README.md) > **Services**

# Services

Docker Compose definitions for the home NAS stack. Each subdirectory holds the `compose.yml` of one service;
`compose.base.yml` provides the shared project name (`nas-stack`) and the `nas-network` bridge that ties them together.
A `compose.yml` is self-contained apart from two things: Glance and Plex also read the shared `~/docker/.env` (see
[Secrets](#secrets)), and the `autoplex` image is built locally (see [`autoplex`](#autoplex)).

These files reach the NAS at `~/docker/` by three routes (see [Deploying](#deploying)): CI on a push to `main`,
`run.py nas-deploy` from a laptop, and the [`services`](../roles/services/README.md) Ansible role. Each ends in
`~/docker/deploy.sh` (installed by the `docker` role from
[`roles/docker/files/deploy.sh`](../roles/docker/files/deploy.sh)), which deploys the services named on its command
line, or for `all` every subdirectory of `~/docker/` containing a `compose.yml`. For each service it runs:

```bash
docker compose --project-directory ~/docker -f compose.base.yml -f <service>/compose.yml up -d <service>
```

with `COMPOSE_IGNORE_ORPHANS=true`, because every service is a separate file in one project and would otherwise see the
others as orphans. `up -d` receives the directory name, so the directory name must equal the service key inside its
`compose.yml`. Given a single service, [`scripts/nas/deploy-services.sh`](../scripts/nas/deploy-services.sh) also
rejects a name outside `^[a-z0-9][a-z0-9_-]*$` and a service without a `services/<name>/compose.yml`.

A service is **disabled** by renaming its `compose.yml` to `compose.yml.disabled`: `deploy.sh`, `deploy-services.sh`,
and the CI workflow only pick up directories containing a `compose.yml`, and the `services` role renders `env.j2` only
for those. `pihole` and `homeassistant` are currently disabled.

Disabling a service in the repository stops nothing on the NAS. The sync never deletes, so an already-synced
`~/docker/<svc>/compose.yml` stays, its container keeps running, and `~/docker/deploy.sh all` on the NAS still discovers
it. Remove the NAS copy by hand; for `homeassistant`, the steps are in the
[cutover section of the Home Assistant OS runbook](../vms/haos/README.md#migrating-from-the-home-assistant-container).

<!-- mdformat-toc start --slug=github --maxlevel=3 --minlevel=2 -->

- [Quick Reference](#quick-reference)
- [Tailscale / HTTPS](#tailscale--https)
- [Services](#services-1)
  - [`caddy`](#caddy)
  - [`glance`](#glance)
  - [`home-assistant`](#home-assistant)
  - [`pihole`](#pihole)
  - [`plex`](#plex)
  - [`jellyfin`](#jellyfin)
  - [`prowlarr`, `radarr`, `sonarr`, `transmission`](#prowlarr-radarr-sonarr-transmission)
  - [`flaresolverr`](#flaresolverr)
  - [`autoplex`](#autoplex)
- [Data flow](#data-flow)
- [Storage layout](#storage-layout)
- [Secrets](#secrets)
- [Deploying](#deploying)
  - [CI deploys](#ci-deploys)
- [Operations](#operations)
  - [Refreshing images](#refreshing-images)
  - [Backups](#backups)

<!-- mdformat-toc end -->

## Quick Reference<a name="quick-reference"></a>

All host ports below are bound on the NAS itself. Services without a host port are reachable only from inside the
`nas-network` bridge.

| Container        | Image                               | Host Port(s)                                  | Purpose                                     |
| ---------------- | ----------------------------------- | --------------------------------------------- | ------------------------------------------- |
| `caddy`          | `caddy:2-alpine`                    | `443/tcp`, `32443/tcp`                        | Tailscale HTTPS reverse proxy (see below)   |
| `glance`         | `glanceapp/glance`                  | `8080/tcp`                                    | Dashboard / homepage                        |
| `home-assistant` | `homeassistant/home-assistant`      | host networking (image default `8123/tcp`)    | Home automation hub (**disabled**)          |
| `pihole`         | `pihole/pihole`                     | `53/tcp`, `53/udp`, `67/udp`, `8053/tcp` → 80 | DNS, ad-blocking, DHCP (**disabled**)       |
| `plex`           | `linuxserver/plex`                  | `32400/tcp`                                   | Media streaming server                      |
| `jellyfin`       | `linuxserver/jellyfin`              | `8096/tcp`, `7359/udp`                        | Media streaming server (Plex alternative)   |
| `prowlarr`       | `linuxserver/prowlarr`              | `9696/tcp`                                    | Indexer aggregator for Sonarr/Radarr        |
| `radarr`         | `linuxserver/radarr`                | `7878/tcp`                                    | Movie library management                    |
| `sonarr`         | `linuxserver/sonarr`                | `8989/tcp`                                    | TV library management                       |
| `transmission`   | `linuxserver/transmission`          | `9091/tcp`                                    | BitTorrent client (web UI)                  |
| `flaresolverr`   | `ghcr.io/flaresolverr/flaresolverr` | internal only (image default `8191/tcp`)      | Cloudflare challenge solver for Prowlarr    |
| `autoplex`       | `danielmmetz/autoplex` (built)      | none                                          | Copies completed downloads into Plex layout |

The compose files declare neither the Home Assistant port `8123` nor the Flaresolverr port `8191`; both are image
defaults.

LAN access is `http://<nas-host>:<port>` (e.g. `http://nas.local:8989` for Sonarr). While PiHole is disabled, its admin
UI (`http://<nas-host>:8053/admin`) is not deployed. Home Assistant now runs as a VM with its own LAN address (see
[`vms/haos/`](../vms/haos/README.md)).

## Tailscale / HTTPS<a name="tailscale--https"></a>

`caddy` terminates TLS using certs issued by `tailscale cert` and proxies a subset of the services under a single
hostname. Configuration is templated by
[`roles/tailscale/templates/Caddyfile.j2`](../roles/tailscale/templates/Caddyfile.j2) from the `tailscale_services`
variable in `inventory/host_vars/nas/vars.yml`.

| Service      | External URL                                | Notes                                                                                 |
| ------------ | ------------------------------------------- | ------------------------------------------------------------------------------------- |
| Sonarr       | `https://nas.<tailnet>.ts.net/sonarr`       | Requires `UrlBase = /sonarr` in app settings                                          |
| Radarr       | `https://nas.<tailnet>.ts.net/radarr`       | Requires `UrlBase = /radarr` in app settings                                          |
| Prowlarr     | `https://nas.<tailnet>.ts.net/prowlarr`     | Requires `UrlBase = /prowlarr` in app settings                                        |
| Transmission | `https://nas.<tailnet>.ts.net/transmission` | Requires `rpc-url = /transmission/` in settings                                       |
| PiHole       | `https://nas.<tailnet>.ts.net/pihole`       | Caddy rewrites `/pihole` → `/admin`; unavailable while PiHole is disabled (see below) |
| Glance       | `https://nas.<tailnet>.ts.net/glance`       | Prefix stripped before proxying                                                       |
| Plex         | `https://nas.<tailnet>.ts.net:32443`        | Dedicated port; `ADVERTISE_IP` must match                                             |

The template skips the `pihole` entry of `tailscale_services` in its loop and emits a hard-coded `/pihole` route to
`pihole:80` instead. The route is therefore always in the Caddyfile, even while PiHole is disabled and nothing in this
repository deploys that container.

## Services<a name="services-1"></a>

### `caddy`<a name="caddy"></a>

Reverse proxy that serves the stack over HTTPS under the NAS's Tailscale hostname. Publishes `443` and `32443`, reads
its `Caddyfile` from `/etc/caddy/` and TLS material from `/etc/tailscale/certs/` on the host (both populated by the
`tailscale` role), and keeps its own state in the `caddy_data` named volume.

### `glance`<a name="glance"></a>

Web dashboard. Mounts `glance/config` and `glance/assets` from `~/docker/glance/`, `/etc/localtime`, and the Docker
socket (read-only). Its `env_file: .env` resolves against `--project-directory ~/docker`, so it loads the shared
`~/docker/.env` rendered by the `docker` role (which holds only `ADVERTISE_IP`), not a `glance/.env`. See
[Secrets](#secrets).

### `home-assistant`<a name="home-assistant"></a>

**Disabled** (`compose.yml.disabled`) in favor of Home Assistant OS running as a libvirt VM, which adds the Supervisor
(apps, managed backups, OS updates). See [`vms/haos/`](../vms/haos/README.md) for the VM and the cutover steps.

The disabled definition uses `network_mode: host`; its service key is `homeassistant` and its container name is
`home-assistant`. `homeassistant/config/` and `homeassistant/shared/` hold only a `.gitkeep` in the repository.

### `pihole`<a name="pihole"></a>

**Disabled** (`compose.yml.disabled`). When re-enabling, confirm nothing else holds `:53`: libvirt's NAT `default`
network runs a `dnsmasq` on `:53`, which blocks PiHole. [`vms/haos/setup.sh`](../vms/haos/setup.sh) stops that network
and disables its autostart; otherwise bind the DNS ports to the NAS's LAN address.

DNS server and DHCP-capable ad-blocker. Binds privileged DNS/DHCP ports on the host; the admin UI is remapped to host
port `8053` to avoid colliding with other web services. `FTLCONF_webserver_api_password` comes from `pihole/.env`,
rendered from [`pihole/env.j2`](pihole/env.j2) (variable `pihole_web_password`) and loaded through `env_file`. To
re-enable, rename the file back to `compose.yml`, run `python3 run.py nas-provision --tags secrets` to render
`pihole/.env`, then `python3 run.py nas-deploy pihole`.

### `plex`<a name="plex"></a>

Media server. Uses the LinuxServer.io image with `PUID=1000/PGID=1000` and mounts `config/plex` plus the `tv`, `movies`,
and `music` libraries from `/storage/media` (see [Storage layout](#storage-layout)). `ADVERTISE_IP` is a bare variable
name in `plex/compose.yml`; its value comes from the shared `~/docker/.env`, where the `docker` role renders it as the
Tailscale HTTPS URL of the dedicated Caddy port (`https://nas.<tailnet>.ts.net:32443`). The port `32443` is written
literally in [`roles/docker/templates/env.j2`](../roles/docker/templates/env.j2) and in
[`caddy/compose.yml`](caddy/compose.yml); the Caddy listener itself comes from the `dedicated_port` of the Plex entry in
`tailscale_services`.

### `jellyfin`<a name="jellyfin"></a>

Media server running alongside Plex. Uses the LinuxServer.io image with `PUID=1000/PGID=1000` and mounts the same
`/storage/media/{tv,movies,music}` libraries as Plex. Publishes HTTP on `8096` and client auto-discovery on `7359/udp`.
Config persists at `/storage/media/config/jellyfin`.

### `prowlarr`, `radarr`, `sonarr`, `transmission`<a name="prowlarr-radarr-sonarr-transmission"></a>

The \*arr and download stack (LinuxServer.io images, `PUID=1000/PGID=1000`). Each mounts its own
`/storage/media/config/<name>` directory. Beyond that:

- `sonarr` mounts `tv/` and `downloads/`.
- `radarr` mounts `movies/` and `downloads/`.
- `transmission` mounts `downloads/` and `watch/`.
- `prowlarr` mounts nothing else; it sees neither the library nor the download trees.

### `flaresolverr`<a name="flaresolverr"></a>

Sidecar that solves Cloudflare challenges for Prowlarr. Publishes no port and mounts nothing; other containers on the
`nas-network` bridge reach it by name as `http://flaresolverr:8191` (`8191` is the image default).

### `autoplex`<a name="autoplex"></a>

Copies completed downloads into the library trees. The image `danielmmetz/autoplex:latest` is built on the NAS by the
`docker` role (a clone of the upstream repository in `~/docker/.build/autoplex`, branch `master`, tagged
`danielmmetz/autoplex:latest`; see [`roles/docker/README.md`](../roles/docker/README.md#autoplex-image)). Its compose
entry has no `build:` key and only names the image, so that build is what supplies it, and the playbook runs the
`docker` role before `services`.

It starts with `--mode copy` and `--host transmission`, and two `--src`/`--dest` pairs: `/downloads/complete/tv` to
`/tv` and `/downloads/complete/movies` to `/movies`. Those are the container paths of `/storage/media/downloads`,
`/storage/media/tv`, and `/storage/media/movies`.

## Data flow<a name="data-flow"></a>

The compose files do not wire the apps together: they provide the shared `nas-network` bridge and the mounts below, and
nothing in this repository configures Prowlarr's indexers or the download client of Sonarr and Radarr. The intended
flow:

1. **Search.** Sonarr (TV) and Radarr (movies) search through Prowlarr, which aggregates the indexers. Flaresolverr
   clears Cloudflare challenges for Prowlarr.
2. **Download.** Sonarr and Radarr hand the release to Transmission, whose `/downloads` is `/storage/media/downloads`.
3. **Copy.** Autoplex (`--mode copy`) copies what is in `downloads/complete/tv` and `downloads/complete/movies` into the
   `tv/` and `movies/` trees. `--host transmission` points it at the Transmission container.
4. **Serve.** Plex and Jellyfin mount `tv/`, `movies/`, and `music/`.

## Storage layout<a name="storage-layout"></a>

Every media bind mount comes from `/storage/media`. Nothing in this repository creates it or its subdirectories.

```text
/storage/media/
├── config/                 # one /config directory per app
│   ├── plex/
│   ├── jellyfin/
│   ├── transmission/
│   ├── sonarr/
│   ├── radarr/
│   └── prowlarr/
├── downloads/
│   └── complete/           # the Autoplex sources
│       ├── tv/
│       └── movies/
├── watch/
├── tv/
├── movies/
└── music/
```

| Path (under `/storage/media`) | Mounted by                                                                                    |
| ----------------------------- | --------------------------------------------------------------------------------------------- |
| `config/<name>`               | the app of the same name (`plex`, `jellyfin`, `transmission`, `sonarr`, `radarr`, `prowlarr`) |
| `downloads`                   | `transmission`, `sonarr`, `radarr`, `autoplex`                                                |
| `watch`                       | `transmission`                                                                                |
| `tv`                          | `plex`, `jellyfin`, `sonarr`, `autoplex`                                                      |
| `movies`                      | `plex`, `jellyfin`, `radarr`, `autoplex`                                                      |
| `music`                       | `plex`, `jellyfin`                                                                            |

All of these mounts are read-write (no compose file sets `:ro` on them). `flaresolverr` mounts nothing. The other bind
mounts are `~/docker/glance/{config,assets}`, `~/docker/pihole-data/etc-pihole` (PiHole),
`~/docker/homeassistant/{config,shared}` (Home Assistant), and, for Caddy, `/etc/tailscale/certs` and
`/etc/caddy/Caddyfile` (both read-only) and the `caddy_data` named volume. Relative paths in the compose files resolve
against `--project-directory ~/docker`.

## Secrets<a name="secrets"></a>

Secrets and other per-host values are rendered on the NAS and never copied from a checkout: the sync excludes `*.j2`,
`.env`, `.backups/`, and `.DS_Store`, and CI renders nothing.

**Shared `~/docker/.env`.** The `docker` role renders it from
[`roles/docker/templates/env.j2`](../roles/docker/templates/env.j2) (mode `0600`). It holds only
`ADVERTISE_IP=https://<host>.<tailnet>:32443`, which is not a secret. Plex reads it through the bare `ADVERTISE_IP`
entry in its `environment`; Glance reads it through `env_file: .env`, although no file under `services/glance/` refers
to `ADVERTISE_IP`.

**Per-service secrets.** A service that needs a secret ships `services/<svc>/env.j2` and sets `env_file: <svc>/.env` in
its `compose.yml`. The path is relative to `~/docker`, because `deploy.sh` passes `--project-directory ~/docker`. The
`services` role renders each `env.j2` to `~/docker/<svc>/.env` (mode `0600`) from vault variables, but only for services
that have a `compose.yml`. A disabled service therefore needs no vault variable and gets no fresh `.env`. `pihole` is
the only service with an `env.j2` today and is disabled, so nothing renders `pihole/.env`; a `~/docker/pihole/.env`
already on the NAS stays in place, since the sync neither ships nor deletes `.env` files.

To rotate a secret, change it in the vault, re-render, and redeploy the service:

```bash
python3 run.py nas-provision --tags secrets
python3 run.py nas-deploy <svc>
```

## Deploying<a name="deploying"></a>

`~/docker/deploy.sh` on the NAS is installed by the `docker` role and is idempotent. Everything that deploys a service
runs it:

| Route                                  | What it does                                                                                          |
| -------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| CI (`.github/workflows/deploy.yml`)    | On a push to `main` that touches `services/`, or a manual run; calls `scripts/nas/deploy-services.sh` |
| `python3 run.py nas-deploy <svc\|all>` | The same script, from a laptop; `--dry-run` previews the rsync and the remote command                 |
| `python3 run.py nas-provision`         | The `services` role syncs `services/`, renders secrets, and runs `deploy.sh all`                      |

`scripts/nas/deploy-services.sh` (see the [NAS scripts README](../scripts/nas/README.md)) rsyncs without deleting (`all`
syncs the whole `services/` tree; a single service syncs `compose.base.yml` and its own directory), then runs
`deploy.sh` on the NAS. A failed service does not stop the others; `deploy.sh` exits 1 at the end. On the NAS itself:

```bash
# Deploy everything
~/docker/deploy.sh all

# Deploy specific services
~/docker/deploy.sh sonarr radarr
```

### CI deploys<a name="ci-deploys"></a>

[`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml) joins the tailnet as `tag:ci` and runs
`scripts/nas/deploy-services.sh` over SSH. A push to `main` touching `services/<name>/` deploys just that service. A
change to `compose.base.yml`, or a push whose `before` SHA is null (force push, new branch), deploys every service that
has a `compose.yml`, one at a time. A manual `workflow_dispatch` run deploys the named service (default `all`):

```bash
gh workflow run deploy.yml -f service=glance
```

The workflow reads five repository secrets:

| Secret                                                       | Used for                                                       |
| ------------------------------------------------------------ | -------------------------------------------------------------- |
| `TAILSCALE_OAUTH_CLIENT_ID`, `TAILSCALE_OAUTH_CLIENT_SECRET` | Joining the tailnet as `tag:ci`                                |
| `NAS_TAILSCALE_HOST`                                         | The NAS's SSH host (`NAS_HOST`), also the `ssh-keyscan` target |
| `NAS_USER`                                                   | The SSH user on the NAS                                        |
| `NAS_SSH_PRIVATE_KEY`                                        | The deploy key, written to `~/.ssh/id_nas` on the runner       |

The runner authenticates to the NAS's regular `sshd` with that dedicated deploy key. Its public half belongs in the
`NAS_USER` account's `~/.ssh/authorized_keys` on the NAS, prefixed with the `restrict` option. To rotate it:

```bash
# On the NAS, as NAS_USER: create the key pair and authorize the public half with restrict
ssh-keygen -t ed25519 -N '' -C github-actions-deploy -f ~/.ssh/gha_deploy
echo "restrict $(cat ~/.ssh/gha_deploy.pub)" >> ~/.ssh/authorized_keys   # then drop the old github-actions-deploy line

# On a machine where gh is authenticated for the repository (the NAS, or another machine after copying ~/.ssh/gha_deploy
# there; delete every copy of the private key afterwards)
gh secret set NAS_SSH_PRIVATE_KEY --repo connormason/dotfiles < ~/.ssh/gha_deploy && rm ~/.ssh/gha_deploy
```

**Tailscale SSH must stay off on the NAS** (`tailscale_ssh_enabled: false` in the NAS host vars). When enabled it
intercepts every SSH connection to the tailnet address and ignores the key. Tailscale SSH also never lets a tagged
device such as `tag:ci` into a user-owned node, so the deploy fails with
`tailnet policy does not permit you to SSH to this node`.

## Operations<a name="operations"></a>

Unless a comment says otherwise, these commands run on the NAS as the deploy user, who is in the `docker` group (the
`docker` role adds it). Each container has a fixed `container_name`, so `docker ps`, `docker logs <container>`,
`docker stop`, and `docker start` need no compose files. A `docker compose` subcommand has to name the project directory
and both compose files:

```bash
docker compose --project-directory ~/docker -f ~/docker/compose.base.yml -f ~/docker/<svc>/compose.yml <command> <svc>
```

### Refreshing images<a name="refreshing-images"></a>

`deploy.sh` runs `up -d`, which pulls an image only when it is missing locally (no compose file sets `pull_policy`), so
a deploy never refreshes an image that is already present. To update a registry image, pull it, then redeploy so `up -d`
recreates the container from the new image:

```bash
docker compose --project-directory ~/docker -f ~/docker/compose.base.yml -f ~/docker/plex/compose.yml pull plex
~/docker/deploy.sh plex
```

A `python3 run.py nas-provision` run after a manual pull recreates the updated container through `deploy.sh all` and
reports it as changed (the `services` role matches `Recreated`, `Started`, `Created`, and `Pulled`).

The `autoplex` image is the exception. It is built on the NAS by the `docker` role, not by this stack, so `pull` is not
how it is refreshed, and re-running the role does not rebuild an image that already exists (see
[`roles/docker/README.md`](../roles/docker/README.md#autoplex-image)). To rebuild it, remove the container that uses the
image and the image itself, then re-run the role and redeploy:

```bash
docker rm -f autoplex
docker rmi danielmmetz/autoplex:latest

# From the laptop: the role refreshes the clone and builds the now-missing image, then the deploy recreates the container
python3 run.py nas-provision --tags docker
python3 run.py nas-deploy autoplex
```

### Backups<a name="backups"></a>

- **Back up `/storage/media/config/` before the media trees.** It holds the `/config` mount of Plex, Jellyfin,
  Transmission, Sonarr, Radarr, and Prowlarr. This repository stores none of those apps' settings (for example the URL
  base values in the [Tailscale table](#tailscale--https)); they live in these directories.

- **Stop `sonarr`, `radarr`, and `prowlarr` before archiving their config directories**, so the archive is not taken
  while the apps are writing, and start them again afterwards:

  ```bash
  docker stop sonarr radarr prowlarr
  tar -czf <backup-dir>/arr-config-$(date +%Y%m%d).tar.gz -C /storage/media config/sonarr config/radarr config/prowlarr
  docker start sonarr radarr prowlarr
  ```

- **The `storage` pool has no redundancy.** [`vms/haos/README.md`](../vms/haos/README.md#fresh-install) records that the
  pool stripes across two disks with no redundancy, so a single disk failure loses the NAS copy of what it holds. Keep
  an off-site copy of anything that matters.

- Home Assistant now runs as a VM with its own backup targets; see
  [`vms/haos/README.md`](../vms/haos/README.md#fresh-install).
