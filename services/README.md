[Project Root](../README.md) > **Services**

# Services

Docker Compose definitions for the home NAS stack. Each subdirectory holds the `compose.yml` of one service;
`compose.base.yml` provides the shared project name (`nas-stack`) and the `nas-network` bridge that ties them together.
Besides the compose files, some services need inputs that exist only on the NAS, among them the shared `~/docker/.env`
(Glance and Plex; see [Secrets](#secrets)), the locally built `medialink` image (see [`medialink`](#medialink)), Caddy's
`Caddyfile` and certificates (see [`caddy`](#caddy)), and, when re-enabled, PiHole's `pihole/.env` (see
[`pihole`](#pihole)).

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

A service is **disabled** by renaming its `compose.yml` to `compose.yml.disabled`. `deploy.sh all` on the NAS discovers
only directories containing a `compose.yml`; `deploy-services.sh <svc>` requires `services/<svc>/compose.yml`, CI push
detection drops directories without one, and the `services` role renders `env.j2` only for those. In contrast,
`deploy-services.sh all` and the `services` role's own sync still push the whole `services/` tree, disabled directories
included. `pihole` and `homeassistant` are currently disabled.

Disabling a service in the repository stops nothing on the NAS. The sync never deletes, so an already-synced
`~/docker/<svc>/compose.yml` stays, its container keeps running, and `~/docker/deploy.sh all` on the NAS still discovers
it. Remove the NAS copy by hand; for `homeassistant`, the steps are in the
[cutover section of the Home Assistant OS runbook](../vms/haos/README.md#migrating-from-the-home-assistant-container).

<!-- mdformat-toc start --slug=github --maxlevel=3 --minlevel=2 -->

- [Quick Reference](#quick-reference)
- [Tailscale / HTTPS](#tailscale--https)
- [Local hostnames](#local-hostnames)
- [Services](#services-1)
  - [`caddy`](#caddy)
  - [`glance`](#glance)
  - [`home-assistant`](#home-assistant)
  - [`pihole`](#pihole)
  - [`plex`](#plex)
  - [`jellyfin`](#jellyfin)
  - [`prowlarr`, `radarr`, `sonarr`, `transmission`](#prowlarr-radarr-sonarr-transmission)
  - [`flaresolverr`](#flaresolverr)
  - [`medialink`](#medialink)
  - [`ntfy`](#ntfy)
  - [`docker-proxy`](#docker-proxy)
  - [`filebrowser`](#filebrowser)
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

| Container        | Image                                 | Host Port(s)                                    | Purpose                                                         |
| ---------------- | ------------------------------------- | ----------------------------------------------- | --------------------------------------------------------------- |
| `caddy`          | `caddy:2-alpine`                      | `80/tcp`, `443/tcp`, `32443/tcp`                | Reverse proxy: Tailscale HTTPS and .local hostnames (see below) |
| `glance`         | `glanceapp/glance`                    | `8080/tcp`                                      | Dashboard / homepage                                            |
| `home-assistant` | `homeassistant/home-assistant`        | host networking (`8123/tcp`, not declared here) | Home automation hub (**disabled**)                              |
| `pihole`         | `pihole/pihole:latest`                | `53/tcp`, `53/udp`, `67/udp`, `8053/tcp` → 80   | DNS, ad-blocking, DHCP (**disabled**)                           |
| `plex`           | `linuxserver/plex`                    | `32400/tcp`                                     | Media streaming server                                          |
| `jellyfin`       | `linuxserver/jellyfin`                | `8096/tcp`, `7359/udp`                          | Media streaming server (Plex alternative)                       |
| `prowlarr`       | `linuxserver/prowlarr`                | `9696/tcp`                                      | Indexer aggregator for Sonarr/Radarr                            |
| `radarr`         | `linuxserver/radarr`                  | `7878/tcp`                                      | Movie library management                                        |
| `sonarr`         | `linuxserver/sonarr`                  | `8989/tcp`                                      | TV library management                                           |
| `transmission`   | `linuxserver/transmission`            | `9091/tcp`                                      | BitTorrent client (web UI)                                      |
| `flaresolverr`   | `ghcr.io/flaresolverr/flaresolverr`   | internal only (`8191/tcp`, not declared here)   | Cloudflare challenge solver for Prowlarr                        |
| `medialink`      | `nas-medialink:local` (built)         | none                                            | Hardlinks completed downloads into the media libraries          |
| `ntfy`           | `binwiederhier/ntfy:v2.11.0`          | `127.0.0.1:2586` → 80 (loopback only)           | Push-notification channel for host alerts                       |
| `docker-proxy`   | `tecnativa/docker-socket-proxy:0.3.0` | `2375/tcp`                                      | Read-only Docker API for Home Assistant's Monitor Docker        |
| `filebrowser`    | `ghcr.io/gtsteffaniak/filebrowser`    | `8085/tcp` → 80                                 | Read-only web file browser for `/storage`                       |

The compose files declare neither the Home Assistant port `8123` nor the Flaresolverr port `8191`; both are upstream
defaults that nothing in this repository verifies.

LAN access is `http://<nas-host>:<port>` (e.g. `http://nas.local:8989` for Sonarr). While PiHole is disabled, its admin
UI (`http://<nas-host>:8053/admin`) is not deployed by this repository. Home Assistant now runs as a VM with its own LAN
address (see [`vms/haos/`](../vms/haos/README.md)). The web UIs also answer on `http://<name>.local`, without a port
(see [Local hostnames](#local-hostnames)).

## Tailscale / HTTPS<a name="tailscale--https"></a>

`caddy` terminates TLS using certs issued by `tailscale cert` and proxies a subset of the services under a single
hostname. Configuration is templated by
[`roles/tailscale/templates/Caddyfile.j2`](../roles/tailscale/templates/Caddyfile.j2) from the `tailscale_services`
variable, set in the NAS host variables of the inventory. In the URLs below, `<tailnet>` is the label of
`tailscale_tailnet_name` before `.ts.net`.

| Service      | External URL                                | Notes                                                                                                     |
| ------------ | ------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| Sonarr       | `https://nas.<tailnet>.ts.net/sonarr`       | Requires `UrlBase = /sonarr` in app settings                                                              |
| Radarr       | `https://nas.<tailnet>.ts.net/radarr`       | Requires `UrlBase = /radarr` in app settings                                                              |
| Prowlarr     | `https://nas.<tailnet>.ts.net/prowlarr`     | Requires `UrlBase = /prowlarr` in app settings                                                            |
| Transmission | `https://nas.<tailnet>.ts.net/transmission` | Requires `rpc-url = /transmission/` in settings                                                           |
| PiHole       | `https://nas.<tailnet>.ts.net/pihole`       | Caddy rewrites `/pihole` → `/admin`; not deployed by this repository while PiHole is disabled (see below) |
| Glance       | `https://nas.<tailnet>.ts.net/glance`       | Prefix stripped before proxying                                                                           |
| Plex         | `https://nas.<tailnet>.ts.net:32443`        | Dedicated port; `ADVERTISE_IP` must match                                                                 |

The template skips the `pihole` entry of `tailscale_services` in its loop and emits a hard-coded `/pihole` route to
`pihole:80` instead. The route is therefore always in the Caddyfile, even while PiHole is disabled and nothing in this
repository deploys that container.

## Local hostnames<a name="local-hostnames"></a>

Each web UI in `local_services` answers on `http://<name>.local` over plain HTTP on the home network. The `mdns` role
announces the name over mDNS (all names point at the NAS's LAN address), and `caddy` routes it by `Host` header to the
container, through an `http://` site that the `tailscale` role renders into the Caddyfile. The list lives in
[`playbooks/vars/local_services.yml`](../playbooks/vars/local_services.yml); an inventory replaces it by setting
`local_services_override`.

| URL                         | Container:port      |
| --------------------------- | ------------------- |
| `http://glance.local`       | `glance:8080`       |
| `http://plex.local`         | `plex:32400`        |
| `http://jellyfin.local`     | `jellyfin:8096`     |
| `http://sonarr.local`       | `sonarr:8989`       |
| `http://radarr.local`       | `radarr:7878`       |
| `http://prowlarr.local`     | `prowlarr:9696`     |
| `http://transmission.local` | `transmission:9091` |
| `http://filebrowser.local`  | `filebrowser:80`    |

`homeassistant.local` is announced by Home Assistant OS itself and is not part of this list. `ntfy` is loopback-only,
and `flaresolverr` and `medialink` have no web UI, so none of the three has a name.

Clients need mDNS support: macOS, iOS and Windows 10 and later have it; Linux needs `nss-mdns`. Without it, use
`http://<nas-host>:<port>`.

The Caddyfile is a single-file bind mount, so a change that edits only the Caddyfile does not recreate the container;
`docker restart caddy` makes it read the new file. A change to `compose.yml` (such as publishing port 80) is applied by
`python3 run.py nas-deploy caddy`.

**Clarifications needed** (only the NAS can answer these; see the checks in the
[design doc](../docs/plans/2026-11/2026-11-21-local-mdns-hostnames-design.md)):

- Whether `http://sonarr.local`, `radarr.local` and `prowlarr.local` redirect `/` to their `UrlBase` prefix, and
  `transmission.local` to `/transmission/web/`.
- Whether Transmission's RPC host whitelist accepts the `transmission.local` hostname.

## Services<a name="services-1"></a>

### `caddy`<a name="caddy"></a>

Reverse proxy that serves the stack over HTTPS under the NAS's Tailscale hostname. Publishes `80`, `443` and `32443`
(port 80 serves the plain-HTTP `.local` sites, see [Local hostnames](#local-hostnames)), reads its `Caddyfile` from
`/etc/caddy/` and TLS material from `/etc/tailscale/certs/` on the host (both mounted read-only and populated by the
`tailscale` role), and keeps its own state in the `caddy_data` named volume.

### `glance`<a name="glance"></a>

Web dashboard. Mounts `glance/config` and `glance/assets` from `~/docker/glance/`, `/etc/localtime`, the Docker socket
(read-only), and `/storage/media` (read-only, at `/mnt/media`, so the Infrastructure page's `server-stats` widget can
report its free space). Its `env_file: .env` resolves against `--project-directory ~/docker`, so it loads the shared
`~/docker/.env` rendered by the `docker` role (which holds only `ADVERTISE_IP`), not a `glance/.env`. See
[Secrets](#secrets).

Pages live in `glance/config/` and are included from `glance.yml`: `home.yml` (feeds, plus a releases widget listing the
upstream projects the NAS runs) and `infrastructure.yml` (host stats, a `monitor` widget that probes each service by
container name on `nas-network`, and the container list). A change to a page file is picked up by the running container;
the added mount needs the container recreated (`python3 run.py nas-deploy glance`).

### `home-assistant`<a name="home-assistant"></a>

**Disabled** (`compose.yml.disabled`) in favor of Home Assistant OS running as a libvirt VM, which adds the Supervisor
(apps, managed backups, OS updates). See [`vms/haos/`](../vms/haos/README.md) for the VM and the cutover steps.

The disabled definition uses `network_mode: host` and mounts `homeassistant/config` and `homeassistant/shared`
(read-write) and `/etc/localtime` (read-only). Its service key is `homeassistant` and its container name is
`home-assistant`. `homeassistant/shared/` holds only a `.gitkeep` in the repository. `homeassistant/config/` holds the
VM's tracked YAML configuration rather than a container's; see [`homeassistant/README.md`](homeassistant/README.md).
Like every disabled directory, it is still pushed to the NAS by the whole-tree sync.

### `pihole`<a name="pihole"></a>

**Disabled** (`compose.yml.disabled`). When re-enabling, confirm nothing else holds `:53`: libvirt's NAT `default`
network runs a `dnsmasq` on `:53`, which blocks PiHole. [`vms/haos/setup.sh`](../vms/haos/setup.sh) stops that network
and disables its autostart; otherwise bind the DNS ports to the NAS's LAN address.

DNS server and DHCP-capable ad-blocker. Binds privileged DNS/DHCP ports on the host; the admin UI is remapped to host
port `8053` to avoid colliding with other web services. It mounts `~/docker/pihole-data/etc-pihole` at `/etc/pihole`.
`FTLCONF_webserver_api_password` comes from `pihole/.env`, rendered from [`pihole/env.j2`](pihole/env.j2) (variable
`pihole_web_password`) and loaded through `env_file`. To re-enable, rename the file back to `compose.yml`, run
`python3 run.py nas-provision --tags secrets` to render `pihole/.env`, then `python3 run.py nas-deploy pihole`.

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

- `sonarr` and `radarr` each mount all of `/storage/media` as **one** volume at `/data`, so the library (`/data/tv`,
  `/data/movies`) and `/data/downloads` share a mount. Imports are hardlinks (Transmission keeps seeding from
  `downloads/complete`), and a hardlink between separate bind mounts fails with `EXDEV` even on one filesystem.
- `transmission` mounts `downloads/` and `watch/`. It reports paths as `/downloads/...`, which the arrs translate to
  `/data/downloads/...` with a remote path mapping.
- `prowlarr` mounts nothing else; it sees neither the library nor the download trees.
- `sonarr`, `radarr` and `prowlarr` set `SONARR__SERVER__URLBASE=/sonarr` (likewise `RADARR__…`, `PROWLARR__…`) so the
  `UrlBase` the Tailscale routes need survives a wiped `/config`.

The apps' settings live in their databases, not in compose. After a first start or a wipe of `/config`, run
[`scripts/nas/arr_setup.py`](../scripts/nas/README.md#arr_setuppy) on the NAS: it reads each API key from `config.xml`
and sets the root folders, the Transmission client and path mapping, Jellyfin-style naming, the FlareSolverr proxy,
Sonarr and Radarr as Prowlarr applications, and the IPTorrents indexer. It is idempotent and has a `--dry-run`.

### `flaresolverr`<a name="flaresolverr"></a>

Sidecar that solves Cloudflare challenges for Prowlarr. Publishes no port and mounts nothing; other containers on the
`nas-network` bridge reach it by name as `http://flaresolverr:8191` (`8191` is not declared here; it is the upstream
default). Prowlarr uses it as an indexer proxy: `arr_setup.py` creates the proxy and a `flaresolverr` tag, and only
indexers carrying that tag (IPTorrents) are routed through it.

### `medialink`<a name="medialink"></a>

Hardlinks completed Transmission downloads into the library trees, so Plex and Jellyfin serve the files while
Transmission keeps seeding from `downloads/complete` with no second copy on disk, and unpacks RAR-packed releases. It
replaces the third-party `autoplex`, which ran in `--mode copy` (every file stored twice), ignored any torrent not saved
directly under `downloads/complete/tv` or `downloads/complete/movies`, and flattened video files into the library root.

The service is a Python package (standard library only) in [`medialink/medialink/`](medialink/medialink), built on the
NAS from [`medialink/Dockerfile`](medialink/Dockerfile), which also installs RARLAB's `unrar` from Debian `non-free`
(Debian's packaged `7zip` is built without RAR support). Its compose entry sets `build.context: medialink` (relative to
`~/docker`, the `--project-directory` that `deploy.sh` passes) and `pull_policy: build`, so each deploy rebuilds the
image from the synced sources and a code change takes effect. It runs as `1000:1000` and mounts `/storage/media` as
**one** volume: hardlinks between separate bind mounts fail with `EXDEV` even when both sit on one filesystem.

Every `MEDIALINK_INTERVAL` seconds (default 60) it asks Transmission for all torrents (RPC at
`http://transmission:9091/transmission/rpc`). For each torrent with nothing left to download it:

1. **Classifies** it as `movies` or `tv`: a Transmission label (`tv`, `movies`) wins, then the download directory (`tv`,
   `movies`, and the singular `movie`; trailing slashes are ignored), then the release name (`S01E02`, `S01-S06`,
   `Season 3` mean TV; a year means a movie). A torrent that cannot be classified is skipped and reported.
2. **Links** every fully downloaded file to `<library>/<name as Transmission lists it>` (the torrent's own directory
   layout, unchanged), creating parent directories. A file already linked is left alone; an independent file already at
   the destination (an old autoplex copy) is reported as a legacy copy and never overwritten.
3. **Extracts** RAR sets instead of linking them. The `.rar`/`.rNN` volumes are never linked; the first volume (`x.rar`,
   or `x.part01.rar`) is unpacked into a staging directory beside the release folder in the library and the files are
   then moved into place without replacing anything that already exists. A crash or failure therefore never leaves a
   half-written file, and the set is retried on the next pass. Completed sets are remembered in the state file so
   gigabytes of archive are not re-read every minute. Symlinks inside an archive are discarded. `MEDIALINK_EXTRACT=0`
   turns extraction off, and RAR-packed torrents are then reported as problems.

Because each pass re-checks every torrent, a torrent that finished during a restart or outage is linked on the next pass
rather than lost. File names come from torrent metadata, so names that are absolute or contain `..` are refused.

The library mirrors each release folder (`movies/<release>/…`, `tv/<release>/…`). Autoplex instead put most video files
directly at the library root, so right after the first pass a title can appear twice: once as an old flat file and once
inside its release folder. `dedupe` (below) removes the flat duplicates.

Problems (a file missing on disk, a failed link, a failed extraction, an unclassifiable or out-of-tree torrent) log an
error and publish one ntfy message each to the `nas-media` topic through `http://ntfy:80`, using the write-only
`ntfy_alerts_token` that `env.j2` renders into `~/docker/medialink/.env` (the `nas-*` access rule from [`ntfy`](#ntfy)
already covers the topic). The variable falls back to empty when the vault does not define it; ntfy denies
unauthenticated publishes, so until the token exists (create it as in [`ntfy`](#ntfy), add it to the vault, re-render
with `nas-provision --tags secrets`, redeploy) alerts are only logged. The `.env` must exist before the first deploy
(see [Secrets](#secrets)). After `MEDIALINK_MAX_RPC_FAILURES` (default 5) consecutive failed cycles it alerts once and
exits with status 2, so `docker ps` and the restart policy show an outage instead of a healthy-looking log.

Commands run inside the container (`python -m medialink <command>`):

| Command                                                            | Effect                                                                                                          |
| ------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------- |
| `run`                                                              | The service loop (container default)                                                                            |
| `once [-n]`                                                        | One pass; `-n/--dry-run` reports what would be linked and changes nothing                                       |
| `dedupe [--apply] [--quick]`                                       | Cleans up what autoplex left, after verifying each file byte for byte (details below); dry run by default       |
| `reorganize [--apply] [--limit N] [--only REGEX] [--undo JOURNAL]` | Moves library links into the Jellyfin/Plex layout (see [Library layout](#medialink-layout)); dry run by default |

`dedupe` handles two cases. A **mirrored legacy copy** (an independent file at the exact path medialink links to) is
replaced by a hardlink through a temporary name and an atomic rename. A **flat duplicate** (a video at the library root
whose name, size and content match a video inside a folder, as left by autoplex) is removed, and the foldered copy
stays; flat files with no foldered twin, including everything you reorganised by hand, are never touched. `--quick`
compares the size plus three 1 MiB samples instead of hashing whole files: far faster on multi-gigabyte video, but not a
proof of equality. Run `once` first, because a flat file is only removed when its foldered twin exists.

#### Library layout<a name="medialink-layout"></a>

`MEDIALINK_LAYOUT` chooses where new links go:

- `mirror` (the default): each torrent's own layout, `<library>/<release>/…`.
- `jellyfin`: `movies/Title (Year)/Title (Year).ext` and `tv/Show/Season NN/Show - SNNENN.ext`, which Jellyfin and Plex
  both read. Subtitles are linked as `<video name>.<lang>.srt`. RAR volumes and scene leftovers (`.nfo`, `.sfv`,
  artwork, sample clips) are not linked. A name the parser cannot read (no year for a movie, no `SxxExx` marker for an
  episode) falls back to the mirrored path and is picked up by `reorganize` once an override exists. Files extracted
  from a RAR set stay in their release folder until `reorganize` moves them.

`reorganize` applies the same layout to what is already in the library. It only touches **files medialink owns**: a
library file that is still a hardlink at the path medialink linked it to, or a recorded RAR extraction. Anything a
person placed, copied or renamed is left alone, and so is a file already in the directory the layout asks for. It moves
links, never data, so Transmission keeps seeding from `downloads/complete`.

- The dry run lists every `conflict` (the target is taken by a different file, such as a second release of the same
  episode or a copy you made yourself), every `unparsed` file and every `cross-library` move (a season filed under
  `movies/`); `-v` lists the moves too. Exit status 1 means conflicts or unparsed files exist.
- A second release of the same movie takes a quality suffix (`Title (Year) - 2160p.mkv`); a second release of the same
  episode is a conflict and nothing moves.
- With `--apply`, each move is a `link` followed by an `unlink`, so nothing is ever overwritten, and is appended to
  `<media root>/config/medialink/reorg-journal.jsonl`. Directories the run emptied are removed. `--undo JOURNAL` replays
  a journal backwards (also a dry run until `--apply`), skipping any path that is occupied again.
- `--only REGEX` limits a run to matching torrents or paths, and `--limit N` to the first N torrents in name order, to
  check a batch in Jellyfin and Plex before continuing.
- Scene leftovers are dropped from the library (their seed copies remain) when their torrent is being reorganised.

Titles come from the release names alone. Fix a wrong or unreadable one in
`<media root>/config/medialink/overrides.json` (`MEDIALINK_OVERRIDES_PATH`), a JSON list read on every pass; a malformed
file is reported rather than ignored:

```json
[
  {
    "pattern": "The\\.Girl\\.on\\.the\\.Train",
    "title": "The Girl on the Train",
    "year": 2016
  },
  {
    "pattern": "Criminal\\.Minds\\.Evolution",
    "title": "Criminal Minds: Evolution",
    "year": 2022,
    "category": "tv"
  }
]
```

`pattern` is a case-insensitive regular expression searched in the torrent name; `year` is required for a movie that
prints none and, for a show, makes the folder `Show (Year)` (otherwise the folder carries no year, and an existing
`Show (Year)` directory is reused); `category` moves a torrent between libraries.

Run `dedupe --apply` before reorganising: it finds flat duplicates through the mirrored layout. Set
`MEDIALINK_LAYOUT=jellyfin` **before** the first `reorganize --apply`, otherwise the loop re-links the scene leftovers
that were dropped.

```bash
python3 run.py medialink once --dry-run
python3 run.py medialink dedupe
python3 run.py medialink dedupe --apply
```

`run.py medialink` runs the command in the container over SSH, and is the same as running
`docker exec medialink python -m medialink …` on the NAS. The project also installs a `medialink` console script
(`uv run medialink …`, from `[project.scripts]` in the root `pyproject.toml`), which runs the package from this checkout
with the `MEDIALINK_*` variables of the calling shell instead of the container's; use it on a host that can reach
Transmission and the media tree, since neither exists on the Mac.

| Variable                                   | Default                                                                             | Meaning                                                          |
| ------------------------------------------ | ----------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| `MEDIALINK_MEDIA_ROOT`                     | `/storage/media`                                                                    | Root holding `downloads/`, `movies/`, `tv/`                      |
| `MEDIALINK_TRANSMISSION_URL`               | `http://transmission:9091/transmission/rpc`                                         | RPC endpoint                                                     |
| `MEDIALINK_TRANSMISSION_USER`, `_PASSWORD` | empty                                                                               | Basic-auth credentials, if RPC authentication is on              |
| `MEDIALINK_TRANSMISSION_DOWNLOADS`         | `/downloads`                                                                        | Download root as Transmission's container sees it                |
| `MEDIALINK_INTERVAL`                       | `60`                                                                                | Seconds between passes                                           |
| `MEDIALINK_MAX_RPC_FAILURES`               | `5`                                                                                 | Consecutive failed cycles before exiting                         |
| `MEDIALINK_NTFY_URL`, `_TOPIC`, `_TOKEN`   | URL unset in code (compose sets `http://ntfy:80`), `nas-media`, token from `env.j2` | Notifications; a blank URL disables them                         |
| `MEDIALINK_STATE_PATH`                     | `<media root>/config/medialink/state.json`                                          | Remembers announced problems and finished extractions            |
| `MEDIALINK_EXTRACT`                        | `1`                                                                                 | `0`/`false`/`no`/`off` disables RAR extraction                   |
| `MEDIALINK_EXTRACTOR`                      | auto (`7zz`, `7z`, `unrar` on `PATH`)                                               | Extraction tool to use first                                     |
| `MEDIALINK_LAYOUT`                         | `mirror`                                                                            | `mirror` or `jellyfin` (see [Library layout](#medialink-layout)) |
| `MEDIALINK_OVERRIDES_PATH`                 | `<media root>/config/medialink/overrides.json`                                      | Title corrections for the `jellyfin` layout and `reorganize`     |

The `run` loop and `once` only ever add links and extracted files; nothing is deleted or renamed unless `dedupe --apply`
or `reorganize --apply` is run. An optional Transmission `script-torrent-done` trigger for instant linking is a planned
follow-up ([plan](../docs/plans/2026-11/2026-11-22-medialink-plan.md)).

### `ntfy`<a name="ntfy"></a>

Self-hosted push-notification server and the alert channel for the host (SMART, ZFS, snapshot and upgrade alerts). The
image is pinned to a version tag rather than `latest`. The port is published on the loopback interface only
(`127.0.0.1:2586`): scripts on the NAS publish to it directly, and Caddy reaches it by name on `nas-network`. The cache
and the user database live in `/storage/media/config/ntfy`. `NTFY_AUTH_DEFAULT_ACCESS=deny-all` makes every topic
require a token, so after the first deploy create an admin user and a write-only token for host scripts:

```bash
docker exec -it ntfy ntfy user add --role=admin <admin-user>
docker exec -it ntfy ntfy user add alerts
docker exec ntfy ntfy access alerts 'nas-*' write-only
docker exec ntfy ntfy token add alerts
```

A publish from the host then looks like
`curl -H "Authorization: Bearer <token>" -d "message" http://127.0.0.1:2586/nas-alerts`. Subscribe from a phone through
the ntfy app once the server has a tailnet route (a `tailscale_services` entry in the inventory); no compose setting
here exposes it beyond the NAS.

### `docker-proxy`<a name="docker-proxy"></a>

Read-only view of the NAS's Docker API for the Monitor Docker integration in Home Assistant, which runs in the HAOS VM
and so cannot reach `/var/run/docker.sock`. The proxy allows only the `containers`, `images`, `info`, `events`,
`version` and `ping` endpoints and, with `POST=0`, no write at all. Port `2375` is published on every interface, so keep
it off the internet; the API still discloses container details, including environment variables, to anything on the LAN.
Home Assistant reaches it at `http://<nas-lan-ip>:2375`; `run.py ha-push` writes that URL into the VM's `secrets.yaml`
from the inventory's `nas_lan_ip` (see [`services/homeassistant/`](homeassistant/README.md#monitor-docker)).

### `filebrowser`<a name="filebrowser"></a>

[FileBrowser Quantum](https://filebrowserquantum.com/en/), a web file browser for the whole `/storage` pool, on
`http://filebrowser.local` (host port `8085`). The pool is mounted `:ro`, so the app cannot modify files whatever its
users are permitted to do; making it read-write means dropping `:ro` in `compose.yml`. The same pool is already exposed
on the LAN by the [`samba`](../roles/samba/README.md) role. Settings live in the tracked
[`filebrowser/config.yaml`](filebrowser/config.yaml) (a single `Storage` source, granted to every user), mounted
read-only. Users, shares and the thumbnail cache sit in the named volume `filebrowser_data`, which no backup job covers.

No password is rendered from the repository. On the first start the app logs a one-time random admin password and
requires a change at first login:

```bash
docker logs filebrowser 2>&1 | grep -i password
```

Like the Caddyfile, `config.yaml` is a single-file bind mount: after editing it, run `docker restart filebrowser`. The
`stable` tag floats, so the image only updates through the manual pull in [Refreshing images](#refreshing-images).

## Data flow<a name="data-flow"></a>

The compose files provide the shared `nas-network` bridge and the mounts below; the wiring between the apps is applied
by [`scripts/nas/arr_setup.py`](../scripts/nas/README.md#arr_setuppy) (see
[`prowlarr`, `radarr`, `sonarr`, `transmission`](#prowlarr-radarr-sonarr-transmission)). The flow:

1. **Search.** Sonarr (TV) and Radarr (movies) search through Prowlarr, which aggregates the indexers. Flaresolverr
   clears Cloudflare challenges for Prowlarr.
2. **Download.** Sonarr and Radarr hand the release to Transmission, whose `/downloads` is `/storage/media/downloads`
   (`/data/downloads` inside the arrs).
3. **Import.** Sonarr and Radarr hardlink the finished download from `downloads/complete` into `tv/` or `movies/`,
   renaming it to the Jellyfin layout. `medialink` does the same for torrents the arrs did not request, by mirroring the
   torrent's own layout; two importers act on one library, so once the arrs own it, stop `medialink` (see
   [`medialink`](#medialink)).
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
│   ├── prowlarr/
│   └── ntfy/
├── downloads/
│   └── complete/           # Transmission's download directory; medialink links from here
│       ├── tv/
│       └── movies/
├── watch/
├── tv/
├── movies/
└── music/
```

| Path (under `/storage/media`) | Mounted by                                                                                            |
| ----------------------------- | ----------------------------------------------------------------------------------------------------- |
| `config/<name>`               | the app of the same name (`plex`, `jellyfin`, `transmission`, `sonarr`, `radarr`, `prowlarr`, `ntfy`) |
| `downloads`                   | `transmission`, `sonarr` (as `/data`), `radarr` (as `/data`), `medialink`                             |
| `watch`                       | `transmission`                                                                                        |
| `tv`                          | `plex`, `jellyfin`, `sonarr` (as `/data/tv`), `medialink`                                             |
| `movies`                      | `plex`, `jellyfin`, `radarr` (as `/data/movies`), `medialink`                                         |
| `music`                       | `plex`, `jellyfin`                                                                                    |

All of these mounts are read-write (no compose file sets `:ro` on them), except `filebrowser`, which mounts the whole
`/storage` pool read-only. `flaresolverr` mounts nothing. The mounts of the other services (Glance, Caddy, PiHole, Home
Assistant) are listed in their sections above. Relative paths in the compose files resolve against
`--project-directory ~/docker`.

## Secrets<a name="secrets"></a>

Secrets and other per-host values are rendered on the NAS and never copied from a checkout: the sync excludes `*.j2`,
`.env`, `.backups/`, and `.DS_Store`, and CI renders nothing.

**Shared `~/docker/.env`.** The `docker` role renders it from
[`roles/docker/templates/env.j2`](../roles/docker/templates/env.j2) (mode `0600`). It holds only
`ADVERTISE_IP=https://<host>.<tailnet>.ts.net:32443` (`<tailnet>` is the label of `tailscale_tailnet_name` before
`.ts.net`), which is not a secret. Plex reads it through the bare `ADVERTISE_IP` entry in its `environment`; Glance
reads it through `env_file: .env`, although no file under `services/glance/` refers to `ADVERTISE_IP`.

**Per-service secrets.** A service that needs a secret ships `services/<svc>/env.j2` and sets `env_file: <svc>/.env` in
its `compose.yml`. The path is relative to `~/docker`, because `deploy.sh` passes `--project-directory ~/docker`. The
`services` role renders each `env.j2` to `~/docker/<svc>/.env` (mode `0600`) from inventory variables, but only for
services that have a `compose.yml`. A disabled service therefore needs no inventory variable and gets no fresh `.env`.
Two services have an `env.j2` today. `medialink` is enabled, so the `services` role renders its `.env` (see the first
deploy note below). `pihole` is disabled, so nothing renders `pihole/.env`; a `~/docker/pihole/.env` already on the NAS
stays in place, since the sync neither ships nor deletes `.env` files. Because rsync never deletes, a service disabled
after it was deployed keeps its NAS `compose.yml` (so `deploy.sh all` keeps deploying it), but its `.env` is no longer
re-rendered, since the role checks the `compose.yml` in the controller's checkout. Rotate such a service's secret only
after removing the NAS copy.

**First deploy of a service with an `env.j2`: render before CI deploys.** The CI deploy renders nothing, and `deploy.sh`
fails the service with `env file …/<svc>/.env not found` when the file is absent, so a push that adds such a service
fails its first `deploy-push` run. Render the file from a machine that can SSH to the NAS, then re-run the failed job
(or `python3 run.py nas-deploy <svc>`):

```bash
python3 run.py nas-provision --tags secrets
```

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
`deploy.sh` on the NAS. Within one `deploy.sh` run, a failed service does not stop the others; the script exits 1 at the
end. On the NAS itself:

```bash
# Deploy everything
~/docker/deploy.sh all

# Deploy specific services
~/docker/deploy.sh sonarr radarr
```

### CI deploys<a name="ci-deploys"></a>

[`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml) joins the tailnet as `tag:ci` and runs
`scripts/nas/deploy-services.sh` over SSH. A push to `main` touching `services/<name>/` deploys just that service. A
change to `compose.base.yml`, or a push whose `before` SHA is null (the workflow's fallback for a new ref), deploys
every service that has a `compose.yml`, one at a time. A manual `workflow_dispatch` run deploys the named service
(default `all`):

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

**Tailscale SSH must stay off on the NAS** (`tailscale_ssh_enabled: false` in the NAS host variables). As observed when
CI deploys were set up (see the update note in the
[2026-03 deploy-pipeline design](../docs/plans/2026-03/2026-03-29-nas-docker-deploy-pipeline-design.md)), Tailscale SSH
let a tagged device such as `tag:ci` reach only other tagged devices, and the NAS is user-owned; with it on, Tailscale
also intercepted SSH connections to the tailnet address and ignored the deploy key. That behavior is Tailscale's, not
something this repository enforces. With the variable `false`, the `tailscale` role leaves `--ssh` off its
`tailscale set` command ([`configure.yml`](../roles/tailscale/tasks/configure.yml)); it never passes `--ssh=false`.

## Operations<a name="operations"></a>

Unless a comment says otherwise, these commands run on the NAS as the deploy user, who is in the `docker` group (the
`docker` role adds it). Each container has a fixed `container_name`, so `docker ps`, `docker logs <container>`,
`docker stop`, and `docker start` need no compose files. A `docker compose` subcommand has to name the project directory
and both compose files:

```bash
docker compose --project-directory ~/docker -f ~/docker/compose.base.yml -f ~/docker/<svc>/compose.yml <command> <svc>
```

### Refreshing images<a name="refreshing-images"></a>

`deploy.sh` runs `up -d`, which pulls an image only when it is missing locally (only `medialink` sets `pull_policy`), so
a deploy never refreshes a registry image that is already present. To update a registry image, pull it, then redeploy so
`up -d` recreates the container from the new image:

```bash
docker compose --project-directory ~/docker -f ~/docker/compose.base.yml -f ~/docker/plex/compose.yml pull plex
~/docker/deploy.sh plex
```

A `python3 run.py nas-provision` run after a manual pull recreates the updated container through `deploy.sh all` and
reports it as changed (the `services` role matches `Recreated`, `Started`, `Created`, and `Pulled`).

The `medialink` image is the exception: its compose entry sets `pull_policy: build`, so every deploy rebuilds it from
the synced sources (cached layers make an unchanged rebuild quick) and recreates the container only when the image
changed. Redeploying it is the whole refresh:

```bash
python3 run.py nas-deploy medialink
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
