# Jellyfin Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Jellyfin Docker service to the NAS stack alongside Plex, deployed automatically by the existing `services/**` GitHub Actions workflow.

**Architecture:** Drop a new `services/jellyfin/compose.yml` into the repo. The existing service-discovery model (`deploy.sh` on the NAS, `.github/workflows/deploy.yml` on push to `main`) handles deployment without any changes to the Ansible role, base compose file, or deploy script. Update two docs (`services/README.md`, `.claude/CLAUDE.md`) to reflect the new service.

**Tech Stack:** `linuxserver/jellyfin` Docker image, Docker Compose, GitHub Actions (rsync-based deploy), pre-commit (`yamllint`).

**Spec:** `docs/superpowers/specs/2026-05-25-jellyfin-service-design.md`

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `services/jellyfin/compose.yml` | Create | Jellyfin service definition (image, ports, volumes). |
| `services/README.md` | Modify | Add Jellyfin to Quick Reference table and Services section. |
| `.claude/CLAUDE.md` | Modify | Add Jellyfin to the Media services bullet in the Docker Stack section. |

No tests in the traditional sense — validation is `yamllint` (via pre-commit) for the compose file and post-deploy `curl` checks for the running service.

---

## Task 1: Create the Jellyfin compose file

**Files:**
- Create: `/Users/connormason/dotfiles-personal/services/jellyfin/compose.yml`

- [ ] **Step 1: Verify port 8096 and 7359/udp are not used by any other service**

Run: `grep -rn "8096\|7359" /Users/connormason/dotfiles-personal/services/`
Expected: no matches.

- [ ] **Step 2: Create the compose file**

Write to `/Users/connormason/dotfiles-personal/services/jellyfin/compose.yml`:

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
      - "8096:8096"
      - "7359:7359/udp"
    volumes:
      - /storage/media/config/jellyfin:/config
      - /storage/media/tv:/tv
      - /storage/media/movies:/movies
      - /storage/media/music:/music
```

- [ ] **Step 3: Validate YAML syntax with yamllint**

Run: `pre-commit run yamllint --files /Users/connormason/dotfiles-personal/services/jellyfin/compose.yml`
Expected: `Passed`.

- [ ] **Step 4: Validate compose file with docker compose config**

Run from repo root:
```bash
docker compose -f services/compose.base.yml -f services/jellyfin/compose.yml config >/dev/null && echo OK
```
Expected: `OK` (and no errors). If `docker` is not available locally, skip — CI will catch issues.

- [ ] **Step 5: Stage but do not commit yet** (commit happens after all docs are updated)

Run: `git add services/jellyfin/compose.yml && git status -s`
Expected: `A  services/jellyfin/compose.yml` shown in status.

---

## Task 2: Update services/README.md

**Files:**
- Modify: `/Users/connormason/dotfiles-personal/services/README.md`

- [ ] **Step 1: Add the Jellyfin row to the Quick Reference table**

In `services/README.md`, find the existing `plex` row in the table:

```markdown
| `plex`           | `linuxserver/plex`                 | `32400/tcp`                                   | Media streaming server                        |
```

Insert this row immediately below the `plex` row (preserve the column-alignment whitespace style of the existing rows — pad the `Container`, `Image`, and `Host Port(s)` columns with trailing spaces so the pipes line up):

```markdown
| `jellyfin`       | `linuxserver/jellyfin`             | `8096/tcp`, `7359/udp`                        | Media streaming server (Plex alternative)     |
```

- [ ] **Step 2: Add the `### jellyfin` Services section**

In `services/README.md`, find the `### plex` section. Insert this section immediately after the existing `### plex` paragraph (before the next `###` heading):

```markdown
### `jellyfin`
Media server running alongside Plex for evaluation. Uses the LinuxServer.io image with
`PUID=1000/PGID=1000` and shares the same `/storage/media/{tv,movies,music}` libraries as Plex.
LAN-only HTTP on port `8096`; client auto-discovery on `7359/udp`. Config persists at
`/storage/media/config/jellyfin`.
```

- [ ] **Step 3: Verify Markdown renders cleanly**

Run: `pre-commit run --files /Users/connormason/dotfiles-personal/services/README.md`
Expected: all hooks pass.

- [ ] **Step 4: Stage**

Run: `git add services/README.md && git status -s`
Expected: `services/README.md` listed as modified.

---

## Task 3: Update .claude/CLAUDE.md

**Files:**
- Modify: `/Users/connormason/dotfiles-personal/.claude/CLAUDE.md` (line 221)

- [ ] **Step 1: Replace the Media services bullet**

Find this exact line (line 221):

```
- **Media**: Plex, Radarr (movies), Sonarr (TV), Transmission (torrents), Prowlarr (indexer), Flaresolverr
```

Replace with:

```
- **Media**: Plex, Jellyfin, Radarr (movies), Sonarr (TV), Transmission (torrents), Prowlarr (indexer), Flaresolverr
```

- [ ] **Step 2: Verify the change**

Run: `grep -n "Jellyfin" /Users/connormason/dotfiles-personal/.claude/CLAUDE.md`
Expected: at least one matching line at line 221.

- [ ] **Step 3: Stage**

Run: `git add .claude/CLAUDE.md && git status -s`
Expected: `.claude/CLAUDE.md` listed as modified.

---

## Task 4: Pre-commit, commit, and push

**Files:** None new. All previously staged.

- [ ] **Step 1: Run pre-commit on staged files**

Run: `pre-commit run` (this runs against staged files only).
Expected: all hooks pass. If any auto-fixes are applied (whitespace, EOF newline), re-stage with `git add` and re-run.

- [ ] **Step 2: Verify final staged set**

Run: `git diff --cached --stat`
Expected: three files — `services/jellyfin/compose.yml` (new), `services/README.md`, `.claude/CLAUDE.md`.

- [ ] **Step 3: Commit**

Run:
```bash
git commit -m "$(cat <<'EOF'
add jellyfin docker service

Run Jellyfin alongside Plex for evaluation as a Plex replacement.
Shares /storage/media/{tv,movies,music} libraries with Plex; LAN-only
HTTP on :8096 with client auto-discovery on 7359/udp. No HW transcoding
or reverse proxy yet — both deferred per the design spec.
EOF
)"
```
Expected: commit succeeds; `git log -1 --oneline` shows the new commit.

- [ ] **Step 4: Push to main**

Run: `git push origin main`
Expected: push succeeds. GitHub Actions `deploy.yml` workflow triggers automatically on push to main.

---

## Task 5: Verify CI deploy and service health

**Files:** None.

- [ ] **Step 1: Watch the deploy workflow**

Run: `gh run watch` (or `gh run list --workflow=deploy.yml --limit=1` and then `gh run view <id> --log`).
Expected: The `detect-changes` job lists `["jellyfin"]` (and possibly other services if README changes triggered them — but the workflow filters `services/**` paths, so a `services/README.md` change *will* trigger it; that's fine, `deploy.sh` is idempotent for unchanged services). The `deploy` matrix job for `jellyfin` succeeds.

If the workflow doesn't pick up `services/README.md`-only changes (the workflow only matches `services/**` and that path qualifies), the jellyfin job still runs because `services/jellyfin/compose.yml` is new.

- [ ] **Step 2: Confirm container is running on the NAS**

SSH to NAS (or via Tailscale): `ssh nas 'docker ps --filter name=jellyfin --format "{{.Names}}\t{{.Status}}"'`
Expected: `jellyfin    Up <duration>`.

If the container isn't running, check:
```bash
ssh nas 'docker logs jellyfin --tail 50'
```
Most likely failure modes:
- Volume mount permission errors → check `/storage/media/config/jellyfin` is owned by UID/GID 1000 (or doesn't exist yet, in which case Docker creates it root-owned and Jellyfin will fail). Fix: `ssh nas 'sudo mkdir -p /storage/media/config/jellyfin && sudo chown 1000:1000 /storage/media/config/jellyfin'`.
- Port conflict on 8096 → revisit Task 1 Step 1.

- [ ] **Step 3: Hit the health endpoint**

From a machine on the LAN (or the NAS itself):
```bash
curl -fsS http://nas.local:8096/health
```
Expected: `Healthy`.

- [ ] **Step 4: Load the web UI**

Open `http://nas.local:8096` in a browser.
Expected: Jellyfin first-run setup wizard loads. Do NOT complete the wizard as part of this plan — that's a manual config step the user takes when ready.

- [ ] **Step 5: Confirm config volume was written**

Run: `ssh nas 'ls /storage/media/config/jellyfin'`
Expected: directory exists with files like `config/`, `data/`, `log/`, etc. created by the container on startup. This proves PUID/PGID + the volume mount work.

- [ ] **Step 6: Sanity-check Plex still works**

Run: `ssh nas 'docker ps --filter name=plex --format "{{.Names}}\t{{.Status}}"'`
Expected: Plex still `Up`. Then load `http://nas.local:32400/web` in a browser to confirm Plex UI still serves.

---

## Done criteria

- `services/jellyfin/compose.yml` exists, lints cleanly, and is committed.
- `services/README.md` and `.claude/CLAUDE.md` reference Jellyfin.
- GitHub Actions deploy succeeded for the `jellyfin` matrix entry.
- `jellyfin` container is `Up` on the NAS.
- `http://nas.local:8096/health` returns `Healthy`.
- Plex remains running and serving on `:32400`.

---

## Rollback

If anything goes sideways and you need to back out:

```bash
# Locally:
git revert HEAD && git push origin main

# Or, if not yet pushed:
git reset --hard HEAD~1

# On the NAS to stop Jellyfin without waiting for revert deploy:
ssh nas 'docker stop jellyfin && docker rm jellyfin'
```

The Jellyfin config under `/storage/media/config/jellyfin` is left in place — delete manually with `sudo rm -rf` if a clean slate is desired.
