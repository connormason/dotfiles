[Project Root](../../README.md) > [Services](../README.md) > **Home Assistant**

# Home Assistant

Version-controlled copy of the hand-editable YAML configuration of the Home Assistant instance running in the
[HAOS VM](../../vms/haos/README.md). The VM's own `/config` stays the live copy; `run.py ha-pull` and `run.py ha-push`
move the tracked files between the two over SSH. The `compose.yml.disabled` and `shared/` beside `config/` belong to the
retired container definition, described in [`services/README.md`](../README.md#home-assistant).

## What is tracked

`services/homeassistant/config/` mirrors these entries of the VM's `/config` (the `HA_SYNC_PATHS` allowlist in
[`run.py`](../../run.py)):

| Entry                                             | Purpose                                        |
| ------------------------------------------------- | ---------------------------------------------- |
| `configuration.yaml`                              | Top-level configuration and `!include`s        |
| `automations.yaml`, `scripts.yaml`, `scenes.yaml` | Files the UI editors read and rewrite          |
| `blueprints/`, `themes/`, `packages/`             | Directories of the same names, when they exist |

Everything else stays on the VM and is covered by Home Assistant's own
[backups](../../vms/haos/README.md#fresh-install):

- `.storage/` (integrations, devices, entities, auth tokens), the recorder database, logs, `.cloud/`, `deps/`, `tts/`.
- `custom_components/`. HACS installs and updates its integrations there, so the directory holds vendored upstream code
  (HACS alone is about 50 MB) that a push would overwrite with a stale copy. HACS records what it installed in
  `.storage/`.
- `secrets.yaml`. Its real values never enter the repo. [`config/secrets.yaml.example`](config/secrets.yaml.example)
  lists the keys, and `.gitignore` blocks `secrets.yaml` here as a guard.

Files that exist only locally under a tracked directory are uploaded by `ha-push`, and files deleted on one side are
deleted on the other, so the allowlisted part of the two trees always ends up identical.

## One-time setup

1. In Home Assistant, install the **Advanced SSH & Terminal** app (*Settings → Apps*), put the public key of the machine
   that runs `run.py` in its `authorized_keys` option, and start it. Password logins are not used: both commands run
   `ssh` with `BatchMode=yes`.

2. Check the connection: `ssh connormason@homeassistant.local true`. The defaults can be overridden per machine with
   `DOTFILES_HA_HOST`, `DOTFILES_HA_USER` and `DOTFILES_HA_PORT`. A machine outside the LAN (the Mac away from home)
   reaches the VM through the NAS with a `ProxyJump` entry for the VM's host in `~/.ssh/config`.

   Unless `DOTFILES_HA_USER` is `root`, the login needs passwordless `sudo` on the VM: `/config` and its files are
   root-owned, so `ha-push` writes and deletes through `sudo -n`.

3. Seed the repo from the live instance and commit the result:

   ```bash
   python3 run.py ha-pull
   git diff services/homeassistant/ && git add services/homeassistant/config
   ```

## Workflow

```bash
python3 run.py ha-pull              # VM -> repo (refuses when tracked files have uncommitted edits; --force overrides)
$EDITOR services/homeassistant/config/automations.yaml
python3 run.py ha-push --dry-run    # show the diff the VM would get
python3 run.py ha-push              # confirm, upload, `ha core check`, roll back if the upload or the check fails
python3 run.py ha-push --restart    # same, then restart Core (configuration.yaml changes need it)
```

- Both commands diff against the VM first. `ha-pull` prints what the VM has that the repo lacks; `ha-push` prints
  exactly what it will change on the VM.
- `ha-push` fetches a snapshot of the VM's tracked files before it writes. When the upload fails partway or
  `ha core check` rejects the result, it uploads the snapshot back, so a bad push leaves the VM as it was. If the
  rollback itself fails, the output says the VM may hold a partial push.
- The `ha` CLI authenticates with a Supervisor token that the VM's login shell exports, so `ha-push` runs it through
  `sh -lc`; a bare `ssh host 'ha ...'` fails with `unauthorized: missing or invalid API token`.
- Pull before editing. The UI automation editor rewrites `automations.yaml` wholesale, so an edit made in the UI and
  another made in the repo cannot be merged. `ha-push` overwrites whatever the VM has with the repo's version.
- `ha-push` refuses to run when the repo holds no tracked files, so an empty checkout cannot wipe the VM.
