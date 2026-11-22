# medialink: replace autoplex with a Transmission-aware hardlinker

## Problem

Finished torrents must appear in `/storage/media/{movies,tv}` for Jellyfin and Plex while Transmission keeps seeding
from `/storage/media/downloads/complete`. The third-party `autoplex` container did this in `--mode copy`. An audit on
2026-11-22 (all 176 torrents in Transmission, matched to the library by file name and size) found it only half working:

| Finding                                    | Evidence                                                                                                                                  |
| ------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------- |
| Every file is stored twice                 | `downloads/complete` is 2.3 TB, the libraries about 3.2 TB, zero hardlinked files; all of it is one ZFS dataset, so links were possible   |
| Torrents outside two directories are ignored | 36 torrents sit in `complete/` itself, 4 in `complete/movie`, 1 at `complete/movies/`; the log repeats `no src-dest pair for processing` |
| Torrents inside the watched directories vanish | 11 never arrived (The Sopranos 0 of 66 files, Scary Movie, Ace Ventura, Hot Fuzz) and 7 arrived partly (Diners MegaPack 91 of 207)      |
| It flattens the library                    | 1,381 of 2,103 video files sit directly at `<library>/<file name>`, 328 are mirrored in a release folder, 161 were reorganised by hand, 233 are absent; subtitles, `.nfo` and images are not copied |
| It unpacks RAR archives                    | 19 scene torrents ship video only inside `.rar` sets (Chainsaw Man, Barbie, People We Meet on Vacation); their extracted `.mkv` files are in the library root |
| Failures are invisible                     | It logs `run successful` each minute regardless; RPC outages appear only as log text                                                      |
| Minor                                      | One stopped torrent reports "No data found"; image is `:latest`; Transmission RPC is unauthenticated on `0.0.0.0:9091`                    |

The cause of the in-directory drops is unproven. The leading hypothesis is torrents that complete while Transmission or
autoplex restarts, which an event-style tool never revisits. Sonarr (0 series) and Radarr (last used 2024-07) are
dormant, so nothing else imports finished downloads.

## Decision

Replace autoplex with `medialink`, a standard-library-only Python service in `services/medialink/`:

- **Hardlink**, not copy: one copy on disk, still seeded by Transmission.
- **Reconcile, not react.** Each cycle lists every torrent and links whatever is missing, so a torrent missed during an
  outage heals on the next pass, and the same code backfills the existing misses.
- **Mirror the torrent's own layout** in the library (`<library>/<release>/…`). This was chosen knowing autoplex did
  something different: it flattened video files into the library root. The consequence is that a title can appear twice
  (old flat file, new foldered copy) until `dedupe` removes the flat duplicates; the alternative of flattening was
  declined. Jellyfin-style renaming is a later task.
- **Extract RAR sets** with `unrar` instead of linking the volumes. Extraction writes new data (it cannot be a
  hardlink), goes through a staging directory so a crash never leaves a truncated file in the library, and is
  remembered in the state file so the archive is not re-read each cycle.
- **Classify** by Transmission label, then download directory (`tv`, `movies`, `movie`, trailing slashes tolerated),
  then release name. Unclassifiable torrents are reported, never guessed.
- **Report failures**: per-torrent log lines, one ntfy message per problem, and a non-zero exit after a sustained RPC
  outage.

## Components

- `config.py`, `transmission.py` (RPC client with the 409 session handshake), `classify.py`, `linker.py`,
  `archives.py` (RAR volume detection and extraction), `engine.py` (one reconcile pass), `state.py` (alert dedupe and
  finished extractions), `notify.py` (ntfy), `dedupe.py`, `cli.py`.
- `linker.py` refuses torrent file names that are absolute or contain `..`: names come from untrusted torrent metadata.
  `archives.py` discards symlinks found inside an archive and never replaces an existing library file.
- The image installs RARLAB's `unrar` from Debian `non-free`: Debian's packaged `7zip` is built without RAR support.
  `Extractor` also drives `7z`/`7zz` when one is present (used by the tests). Verified by extracting a real multi-volume
  release in the built image: the output matched the archive's declared size to the byte.
- `dedupe` is a separate, explicit command with two verified clean-ups, both dry runs by default. A **mirrored legacy
  copy** becomes a hardlink via a temporary link and an atomic rename. A **flat duplicate** (a video at the library
  root with an identical copy in a folder) is deleted; the foldered copy remains and flat files without a twin are
  never touched. Equality is size plus SHA-256, or with `--quick` size plus three sampled blocks.
- Compose mounts `/storage/media` as one volume. Separate bind mounts of one filesystem make `link()` fail with `EXDEV`.
  The build context is `medialink` because `deploy.sh` runs compose with `--project-directory ~/docker`, and
  `pull_policy: build` makes its plain `up -d` rebuild after a code change.
- The ntfy token is rendered into `~/docker/medialink/.env` from the existing `ntfy_alerts_token` vault variable.

## Out of scope

- Reorganising the libraries into Jellyfin naming (follow-up below).
- Transmission's `script-torrent-done` trigger (follow-up below).
- Transmission RPC authentication and bind address.
- Retiring the dormant Sonarr, Radarr, Prowlarr and Flaresolverr services.

## Testing

Unit tests in `tests/unit/services/test_medialink.py` cover the classifier, path safety, the linker (fresh, idempotent,
partial, legacy copy, missing, incomplete, `EXDEV`), the RPC client against a stub HTTP server, notification dedupe,
the outage exit, `dedupe` (both clean-ups and their refusals), RAR extraction (volume naming, command shapes, staging,
crash recovery, no overwrite, symlinks, a real `7z` run) and the deploy contract (single mount, build context, secret
template). The docs consistency test pins the README table to the compose files. A dry run against the live Transmission
predicted 2,260 links, 141 RAR sets to extract and 488 reclaimable legacy copies (about 640 GiB).

## Rollout (owner-run)

1. **Stop autoplex first** (`docker stop autoplex`). Two writers must never overlap: a copy onto a destination that is
   already a hardlink of its own source would be a write to the seed file itself.
2. Review a dry run **before** the container exists, because the loop links and extracts as soon as it starts. From a
   checkout on the NAS: `MEDIALINK_TRANSMISSION_URL=http://localhost:9091/transmission/rpc PYTHONPATH=services/medialink
   uv run python -m medialink once --dry-run`. It is read-only (no links, no extraction, no notifications, no state).
3. Deploy `medialink` (merge to `main`; CI deploys it). It links, then extracts RAR sets (this takes a while and writes
   tens of gigabytes).
4. Remove autoplex by hand (`docker rm -f autoplex`, `docker rmi danielmmetz/autoplex:latest`,
   `rm -rf ~/docker/autoplex ~/docker/.build`); CI deploys never delete.
5. Confirm the backfill: re-run the audit and expect no missing or partial torrents.
6. Clean up: `docker exec medialink python -m medialink dedupe --quick` for the report, then `dedupe --apply` (drop
   `--quick` for a full-hash proof; that reads every duplicate in full, several terabytes). Run it only after the first
   pass has finished, because a flat file is removed only when its foldered twin exists.

## Follow-ups

- **Jellyfin-style reorganisation** of `movies/` and `tv/` (`Show/Season NN/`, `Movie (Year)/`). It must keep the
  hardlinks to the download tree intact, so it should move links, not files.
- **Done-script trigger**, enabled by configuration: set Transmission's `script-torrent-done` to run a one-shot pass for
  instant linking. The polling loop stays as the safety net.
