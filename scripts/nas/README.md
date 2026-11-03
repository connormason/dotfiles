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
- Files named `*.j2` and `.env`, `.backups/` directories and `.DS_Store` files are never copied, directory times are not
  copied (so re-syncing an unchanged tree is a no-op), and nothing is deleted on the NAS.
- `--dry-run` runs `rsync -n` and prints the `ssh` command instead of running it.
- Exits 2 on a bad argument or missing variable; otherwise with the status of the failing `rsync` or `ssh`.

From a laptop, prefer `python3 run.py nas-deploy <service>`, which resolves the host and user from the inventory.
