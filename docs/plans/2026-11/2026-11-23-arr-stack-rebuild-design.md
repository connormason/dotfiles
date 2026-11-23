# Rebuild Prowlarr, Sonarr and Radarr from scratch

Status: **approved 2026-11-23**. Implementation: `scripts/nas/arr_setup.py` and the compose changes under `services/`.

## Problem

Prowlarr's IPTorrents indexer failed with `IPTorrents authentication with cookies failed`, its update check raised
exceptions, and Sonarr logged `BaseUrl must not be empty` validation errors. The compose files only provided mounts and
the shared network: the indexer, download-client, root-folder and application settings lived solely in the apps'
SQLite databases, so there was nothing to restore from and no record of what "right" looked like.

## Decisions

| Decision                                  | Choice                                                                                       |
| ----------------------------------------- | -------------------------------------------------------------------------------------------- |
| Reset scope                               | Wipe all three `/config` directories, re-add the library through the arrs' Library Import    |
| Who imports finished downloads            | Sonarr and Radarr (hardlink and rename to the Jellyfin layout); `medialink` is stopped later |
| How the apps are configured               | A repo-tracked, idempotent script (`scripts/nas/arr_setup.py`), not UI clicks                |
| FlareSolverr                              | Existing sidecar, wired as a Prowlarr indexer proxy through a `flaresolverr` tag             |
| `UrlBase`                                 | `<APP>__SERVER__URLBASE` environment variables in compose                                    |

## Findings that shaped the design

Everything below was checked against throwaway containers (`linuxserver/{sonarr,radarr,prowlarr}` with temporary
configs on a private network, Sonarr 4.0.20, Radarr 6.4.4, Prowlarr 2.7.0), never the live stack.

- **Hardlinks need one mount.** The arrs mounted `/tv` or `/movies` and `/downloads` as separate bind mounts, and a
  hardlink across bind mounts fails with `EXDEV`. Both arrs now mount `/storage/media` once, at `/data`.
- **Transmission paths need a mapping.** Transmission reports `/downloads/complete/...`; inside an arr the same files
  are `/data/downloads/complete/...`. The script creates the remote path mapping, and the apps' own
  `RemotePathMappingCheck` confirmed the translation.
- **`UrlBase` can come from the environment.** `SONARR__SERVER__URLBASE=/sonarr` (and the Radarr and Prowlarr
  equivalents) showed up as `urlBase` in each app's host config, so a wiped config comes back correct. The Tailscale
  routes depend on it. The setting is not written to `config.xml`.
- **Field names come from the schema.** The script builds each provider from the app's own `/schema` template and sets
  fields by name, so unrelated defaults stay intact and an unknown name is a clear error.
- **Saving a failing indexer.** Prowlarr tests an indexer when saving it and rejects a failure with HTTP 400.
  `?forceSave=true` skips only warnings, not errors, so it does not help with an expired cookie. Prowlarr tests only
  enabled indexers, so the script saves the indexer disabled, warns, and enables it on the next run that has a working
  cookie.
- **Secrets are masked by the API**, so an existing provider's cookie and the API keys held in Prowlarr cannot be
  compared. They are written on create, and afterwards only with `--refresh-secrets`.

## Not changed

- `medialink` stays in the repository, enabled. Its compose file is pinned by its own tests and docs, and stopping it
  is an operational decision to take after Library Import has been checked (see below).
- Authentication settings of the apps. A fresh install defaults to `AuthenticationMethod=None`; choose the method in
  each app's UI (Settings, General) to match what the old `config.xml` held.
- The Prowlarr "update check" error in the old logs was a network failure to the update server, not configuration.

## Cutover (owner-run)

1. Deploy the compose changes: merge to `main` (CI deploys changed services) or
   `python3 run.py nas-deploy sonarr radarr prowlarr flaresolverr`.
2. Stop the three apps. Note `AuthenticationMethod` from each old `config.xml`. Back up the config directories, for
   example `tar -C /storage/media/config -czf /storage/media/config-backups/arr-$(date +%F).tar.gz sonarr radarr prowlarr`
   (stopped, so the SQLite files are consistent).
3. Empty the three directories and start the apps. They write fresh databases and new API keys.
4. In a browser, log in to iptorrents.com and copy the cookie string and the browser's user agent. Then, on the NAS:
   `IPTORRENTS_COOKIE='...' IPTORRENTS_USER_AGENT='...' uv run scripts/nas/arr_setup.py --dry-run`, followed by the same
   command without `--dry-run`.
5. In Sonarr and Radarr, run **Library Import** on `/data/tv` and `/data/movies`.
6. Once imports look right, stop `medialink` (`docker stop medialink`) so two importers never act on one library.

## Verification

- `uv run pytest tests/unit/scripts/nas` covers the diffing, secret handling, indexer fallback and HTTP client.
- The script ran against the throwaway stack: a dry run wrote nothing, a real run created every resource and the apps'
  own connection tests passed for Transmission, FlareSolverr, and the Sonarr and Radarr applications, and a second run
  reported every Sonarr, Radarr and Prowlarr resource except the unauthenticated indexer as `unchanged`.
- Not verifiable without credentials: the IPTorrents login itself. Prowlarr's "Test" on the indexer, and one grabbed
  release hardlinked into the library (`stat -c %h` shows 2 or more), are the live acceptance checks.
