# Jellyfin Service Design

**Date:** 2026-05-25
**Status:** Approved
**Goal:** Run Jellyfin alongside Plex on the NAS to evaluate it as a Plex replacement.

## Context

The NAS Docker stack (`services/`) hosts Plex via `linuxserver/plex` with media at
`/storage/media/{tv,movies,music}` and config at `/storage/media/config/plex`. Each service is
self-contained in `services/<name>/compose.yml`, deployed to `~/docker/<name>/` on the NAS by:

- **`deploy.sh`** — discovers any `~/docker/*/compose.yml` and runs `docker compose ... up -d`
- **`.github/workflows/deploy.yml`** — rsyncs changed `services/**` directories to the NAS on push to `main`

This spec adds Jellyfin as a peer service so the user can compare both servers against the same
media library before committing to a migration.

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Image | `linuxserver/jellyfin` | Matches the rest of the stack (plex, sonarr, radarr, prowlarr, transmission). Same PUID/PGID convention. |
| Hardware transcoding | Skipped | Out of scope for evaluation. Easy to add `/dev/dri` passthrough later if NAS hardware supports VAAPI/QSV. |
| Remote access | LAN-only HTTP on `:8096` | Defers Caddy/Tailscale wiring until after migration commitment. No `BaseURL` headaches during evaluation. |
| Media access | Same paths as Plex, read-write | Lets Jellyfin write trickplay/chapter assets next to media if those features are enabled later. Read-write matches Plex's mount mode. |
| Timezone env var | Omitted | `linuxserver/plex` does not set `TZ`; matching that for consistency. |

## Architecture

No changes to the Ansible role (`roles/docker/`), the shared `compose.base.yml`, the deploy script
(`deploy.sh`), or the GitHub Actions workflow are required. The service-discovery model handles new
services transparently — adding `services/jellyfin/compose.yml` is sufficient.

```
services/
├── compose.base.yml          # unchanged
├── plex/compose.yml          # unchanged
├── jellyfin/compose.yml      # NEW
└── ...
```

## Service Definition

`services/jellyfin/compose.yml`:

```yaml
---
services:
  jellyfin:
    image: linuxserver/jellyfin
    container_name: jellyfin
    restart: unless-stopped
    environment:
      - PUID=1000
      - PGID=1000
    ports:
      - "8096:8096"          # HTTP web UI
      - "7359:7359/udp"      # client auto-discovery on LAN
    volumes:
      - /storage/media/config/jellyfin:/config
      - /storage/media/tv:/tv
      - /storage/media/movies:/movies
      - /storage/media/music:/music
```

### Port allocation

| Port | Protocol | Purpose | Conflict check |
|---|---|---|---|
| 8096 | TCP | Jellyfin HTTP web UI | Free — no service in current stack uses 8096. |
| 7359 | UDP | LAN client auto-discovery | Free — no other service uses 7359. |

Intentionally omitted:

- **8920/tcp** (HTTPS web UI) — requires a self-signed cert; LAN HTTP is sufficient for evaluation.
- **1900/udp** (DLNA) — DLNA is off by default in Jellyfin and not needed for first-party clients.

### Volume layout

| Host path | Container path | Mode | Purpose |
|---|---|---|---|
| `/storage/media/config/jellyfin` | `/config` | rw | Jellyfin config + metadata DB (created on first run) |
| `/storage/media/tv` | `/tv` | rw | TV library (shared with Plex) |
| `/storage/media/movies` | `/movies` | rw | Movie library (shared with Plex) |
| `/storage/media/music` | `/music` | rw | Music library (shared with Plex) |

The mount points inside the container intentionally mirror Plex's layout so library paths in the
Jellyfin setup wizard can use familiar names.

## Documentation Updates

**`services/README.md`:**

- Add a row to the "Quick Reference" table:
  `| jellyfin | linuxserver/jellyfin | 8096/tcp, 7359/udp | Media streaming server (Plex alternative for evaluation) |`
- Add a `### jellyfin` section under "Services" briefly describing it and noting it shares libraries with Plex.

**`.claude/CLAUDE.md`:**

- Append `Jellyfin` to the Media services bullet in the "Docker Stack (NAS)" section.

## Deployment Flow

1. Create `services/jellyfin/compose.yml`.
2. Update `services/README.md` and `.claude/CLAUDE.md`.
3. Commit and push to `main`.
4. GitHub Actions detects the new service, rsyncs `services/jellyfin/` to `~/docker/jellyfin/` on the NAS, and invokes `deploy.sh jellyfin`.
5. `deploy.sh` runs `docker compose ... up -d jellyfin`, which pulls the image and starts the container.
6. User completes Jellyfin's first-run wizard at `http://<nas-host>:8096`, pointing libraries at `/tv`, `/movies`, `/music`.

No manual NAS-side commands required for the deploy itself — CI handles it. If desired, the user can also run `~/docker/deploy.sh jellyfin` directly on the NAS for a faster initial deploy.

## Verification

After deploy:

- `docker ps` on the NAS shows `jellyfin` container running.
- `curl -fsS http://<nas-host>:8096/health` returns `Healthy`.
- Jellyfin web UI loads at `http://<nas-host>:8096` and the setup wizard appears.
- `ls /storage/media/config/jellyfin` shows config files were written (proves PUID/PGID + volume mount work).

## Out of Scope

- **Hardware transcoding** — deferred. Trivial to add `devices: [/dev/dri:/dev/dri]` and `group_add: [render]` later.
- **Reverse proxy / Tailscale exposure** — deferred. Will be added to `services/caddy/` once migration is committed.
- **Plex → Jellyfin metadata migration** (watch state, ratings, playlists) — separate work, after evaluation.
- **HTTPS / DLNA** — see "Port allocation" above.

## Risks

- **Shared read-write media access**: Jellyfin and Plex both have rw access to the same media tree. Neither server modifies media files in default configurations, but if Jellyfin's "extract chapter images during library scan" or trickplay features are enabled, it will write `.bif` / image files alongside media. This is benign — Plex ignores those files — but worth knowing.
- **Library scan load**: First scan over the full `/storage/media` tree will be I/O heavy. Run it during off-hours if streaming concurrently is a concern.
