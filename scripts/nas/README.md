[Project Root](../../README.md) > **NAS scripts**

# NAS scripts

Scripts that act on the home NAS: `deploy-services.sh` from a controlling machine, `arr_setup.py` on the NAS itself.

| File                                       | Purpose                                                                             |
| ------------------------------------------ | ----------------------------------------------------------------------------------- |
| [`arr_setup.py`](arr_setup.py)             | provision Sonarr, Radarr and Prowlarr through their APIs (run on the NAS)           |
| [`deploy-services.sh`](deploy-services.sh) | rsync `services/` to the NAS and run `~/docker/deploy.sh` (used by CI and `run.py`) |

## `arr_setup.py`<a name="arr_setuppy"></a>

```bash
IPTORRENTS_COOKIE='uid=...; pass=...' IPTORRENTS_USER_AGENT='<browser user agent>' \
    uv run scripts/nas/arr_setup.py [--dry-run] [--refresh-secrets] [--host HOST] [--config-root DIR]
```

Run it on the NAS after Sonarr, Radarr and Prowlarr have started once (so each has written its `config.xml`), and again
after any wipe of their `/config` directories. Every step reads the current state and writes only a difference, so a
second run reports everything `unchanged`. Each app's API key is read from `<config-root>/<app>/config.xml`
(`/storage/media/config` by default) and is never printed.

| App            | What it sets                                                                                                  |
| -------------- | ------------------------------------------------------------------------------------------------------------- |
| Sonarr, Radarr | root folder (`/data/tv`, `/data/movies`); Transmission client (`transmission:9091`, category `tv` / `movies`) |
| Sonarr, Radarr | remote path mapping `/downloads/` to `/data/downloads/`; hardlink imports, `.srt` extras, completed downloads |
| Sonarr, Radarr | Jellyfin-style naming: `Show (Year)/Season 01/…`, `Movie (Year)/Movie (Year).ext`                             |
| Prowlarr       | `flaresolverr` tag; FlareSolverr proxy (`http://flaresolverr:8191/`); Sonarr and Radarr as full-sync apps     |
| Prowlarr       | IPTorrents indexer with the cookie and user agent from the environment, tagged `flaresolverr`                 |

- **Cookie.** IPTorrents authenticates by cookie and ties it to the user agent that received it. Log in at
  iptorrents.com, copy the full cookie string and the browser's user agent, and pass them as `IPTORRENTS_COOKIE` and
  `IPTORRENTS_USER_AGENT`. They are only ever held in memory. Prowlarr tests an enabled indexer on save; when the test
  fails (an expired cookie), the script saves the indexer **disabled**, prints a warning, and a later run with a fresh
  cookie re-enables it. Without a cookie, a missing indexer is skipped with a warning.
- **Secrets.** The API masks stored secrets, so an existing provider's cookie and the arr API keys held in Prowlarr are
  rewritten only with `--refresh-secrets` (use it after wiping only some of the apps), or automatically for an indexer
  left disabled.
- **`UrlBase`** is not set here: each compose file sets it through `<APP>__SERVER__URLBASE`.
- Health checks are printed as information and counted as warnings; right after provisioning, "no indexers" checks lag
  behind Prowlarr's first sync. The exit status is 1 when a step failed or an app could not be reached, 2 for a
  malformed cookie.
- `--port-offset N` adds `N` to each app's published port, to provision a second stack for testing.

## `deploy-services.sh`

```bash
NAS_HOST=<host> NAS_USER=<user> [NAS_SSH_KEY=<path>] scripts/nas/deploy-services.sh [--dry-run] <service|all>
```

- `NAS_HOST` / `NAS_USER` are required. `NAS_SSH_KEY` selects a private key and auto-accepts the host key (CI); without
  it the caller's SSH configuration applies.
- `<service>` is `all` or one directory under `services/`. A name must match `^[a-z0-9][a-z0-9_-]*$` and
  `services/<service>/compose.yml` must exist, so a service whose compose file is `compose.yml.disabled` is rejected.
- `all` syncs the whole `services/` tree to `~/docker/`. A single service syncs `services/compose.base.yml` to
  `~/docker/compose.base.yml` and `services/<service>/` to `~/docker/<service>/`. Either way the script then runs
  `~/docker/deploy.sh <service|all>` on the NAS over `ssh`.
- Files named `*.j2` and `.env`, `.backups/` directories and `.DS_Store` files are never copied, directory times are not
  copied (so re-syncing an unchanged tree is a no-op), and nothing is deleted on the NAS.
- A `NAS_HOST` or `NAS_USER` that starts with `-` is refused, and `--` precedes the operands of `rsync` and `ssh`, so
  neither command can read the destination as an option. The `NAS_SSH_KEY` path is single-quoted inside the string
  passed to `rsync -e`, which `rsync` splits on whitespace, so a path with spaces stays one word; a path that itself
  contains a single quote is refused.
- `--dry-run` runs `rsync -n` and prints the `ssh` command instead of running it.
- Exits 2 on any refused input (a bad argument, a missing variable, an option-like host or user, an invalid or unknown
  service, a key path with a single quote); otherwise with the status of the failing `rsync` or `ssh`.

From a laptop, prefer `python3 run.py nas-deploy <service>`, which resolves the host and user from the inventory.

### CI

[`.github/workflows/deploy.yml`](../../.github/workflows/deploy.yml) calls the script as
`NAS_SSH_KEY="$HOME/.ssh/id_nas" scripts/nas/deploy-services.sh "$SERVICE"`, with `NAS_HOST` and `NAS_USER` taken from
repository secrets. A push to `main` that touches `services/` runs it once per changed service that has a `compose.yml`
(every such service when `compose.base.yml` changed, or when the push's `before` SHA is null, the workflow's fallback
for a new ref); a manual run passes its `service` input, which defaults to `all`.
[`services/README.md`](../../services/README.md#ci-deploys) describes the workflow and its secrets.
