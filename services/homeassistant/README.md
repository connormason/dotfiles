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
| `dashboards/`                                     | YAML dashboards, see [Dashboards](#dashboards) |

Everything else stays on the VM and is covered by Home Assistant's own
[backups](../../vms/haos/README.md#fresh-install):

- `.storage/` (integrations, devices, entities, auth tokens), the recorder database, logs, `.cloud/`, `deps/`, `tts/`.
- `custom_components/`. HACS installs and updates its integrations there, so the directory holds vendored upstream code
  (HACS alone is about 50 MB) that a push would overwrite with a stale copy. HACS records what it installed in
  `.storage/`.
- `secrets.yaml`. Its real values never enter the repo, but `ha-push` still builds it: see [Secrets](#secrets).
  `.gitignore` blocks `secrets.yaml` here as a guard.

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

## Secrets<a name="secrets"></a>

[`config/secrets.yaml.j2`](config/secrets.yaml.j2) is the template of the VM's `/config/secrets.yaml`. `ha-push` renders
it with Ansible against the inventory's `nas` host, so a value comes from the same place as in the services' `env.j2`
files: `inventory/host_vars/nas/` (vault included), unlocked with `vault_password.txt`. The rendered text is never
printed, written locally, or committed. For example, `nas_docker_url` is built from `nas_lan_ip`.

- The template is the single source of truth. A key that exists only on the VM is deleted by the next push, so add every
  `!secret <key>` the config uses to the template.
- The confirmation prompt, `--dry-run`, and the summary list secrets by **key name** only (`+` new, `~` changed, `-`
  removed). A rewrite is skipped when the parsed content already matches, so comments and quoting on the VM do not cause
  churn.
- The file is uploaded before the config, because the config may already reference a new key. It is written `0600`, and
  the rollback described under [Workflow](#workflow) restores the previous `secrets.yaml` too (or deletes the file when
  the VM had none).
- A missing variable, inventory or vault password aborts the push before anything on the VM changes. Without a template,
  `ha-push` leaves the VM's `secrets.yaml` alone.

## Dashboards<a name="dashboards"></a>

Dashboards built in the UI live in the VM's `.storage/`, which is not tracked. A dashboard that should be in version
control is a **YAML-mode dashboard**: its file sits in [`config/dashboards/`](config/dashboards/) and
`configuration.yaml` registers it under `lovelace: dashboards:` (the key becomes the URL path and needs a hyphen).
`ha-push` uploads the files, and `--restart` is needed the first time, when the registration is added.

- A YAML dashboard is **read-only in the UI**. Edit the file and push; the browser only needs a refresh afterwards.
- Dashboards are not validated by `ha core check`. A mistake shows up as an error card in the browser, not as a failed
  push.
- [`dashboards/main.yaml`](config/dashboards/main.yaml) is the Main dashboard (lights by floor), migrated from the
  UI-built `.storage/lovelace.dashboard_main`. Its custom cards load from `.storage/lovelace_resources`, which HACS
  manages and which stays untracked. The built-in `map` dashboard and the auto-generated Overview have no stored cards,
  so they stay as they are.
- [`dashboards/nas_containers.yaml`](config/dashboards/nas_containers.yaml) is the NAS container overview: a table of
  every `sensor.nas_*_state` with the container's uptime, and a banner that appears while any container is stopped. It
  reads the [Monitor Docker](#monitor-docker) sensors.

## Monitor Docker<a name="monitor-docker"></a>

[`monitor_docker`](https://github.com/ualex73/monitor_docker) (a HACS integration, configured in YAML) reports the NAS
containers as sensors. The `monitor_docker:` block in `configuration.yaml` lists the containers Glance shows for the
stack. It reads the Docker API through the read-only [`docker-proxy`](../README.md#docker-proxy) service, because the VM
cannot reach the NAS's Docker socket.

1. Define `nas_lan_ip` (the NAS's LAN address) for the `nas` host in the inventory, in `host_vars/nas/vault.yml` or
   `vars.yml`. `ha-push` turns it into `nas_docker_url` (see [Secrets](#secrets)); nothing is edited on the VM.
2. Deploy the proxy: `python3 run.py nas-deploy docker-proxy`.
3. `python3 run.py ha-push --restart`. `monitor_docker:` is read at startup, so a restart is required.

Each container gets `state`, `status`, `health`, `uptime`, CPU and memory sensors; the host gets version and
running/total/stopped counts. A container added to the stack needs an entry in both `containers` and `rename`.
