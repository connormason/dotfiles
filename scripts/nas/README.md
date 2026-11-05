[Project Root](../../README.md) > **NAS scripts**

# NAS scripts

Scripts that act on the home NAS from a controlling machine.

| File                                       | Purpose                                                                             |
| ------------------------------------------ | ----------------------------------------------------------------------------------- |
| [`deploy-services.sh`](deploy-services.sh) | rsync `services/` to the NAS and run `~/docker/deploy.sh` (used by CI and `run.py`) |

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
(every such service when `compose.base.yml` changed, or when the push's `before` SHA is null, as for a new branch); a
manual run passes its `service` input, which defaults to `all`.
[`services/README.md`](../../services/README.md#ci-deploys) describes the workflow and its secrets.
