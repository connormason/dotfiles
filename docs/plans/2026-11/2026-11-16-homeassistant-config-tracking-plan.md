# Home Assistant Config Tracking Implementation Plan

**Goal:** Track the hand-editable YAML of the HAOS VM's Home Assistant (`/config` inside the VM) in this repository, with
explicit `ha-pull` and `ha-push` commands in `run.py`.

**Background:** The files under `~/docker/homeassistant/config` on the NAS are stale leftovers of the retired container
(`automations.yaml` is `[]`, `secrets.yaml` holds a placeholder). The live config exists only inside the VM and is
configured through the UI. `services/homeassistant/` is a disabled Compose definition with `.gitkeep` files.

## Decisions

- **Transport:** SSH to the *Advanced SSH & Terminal* app in HAOS (key auth). No rsync dependency: the config travels as
  a tar stream built and read with Python's `tarfile`, which normalizes ownership and modes and rejects unsafe members.
- **Location:** `homeassistant/config/` at the repo root (`services/` is for Compose deployments; HA no longer runs
  there).
- **Allowlist (tracked):** `configuration.yaml`, `automations.yaml`, `scripts.yaml`, `scenes.yaml`, `blueprints/`,
  `themes/`, `custom_components/`, `packages/`.
- **Never tracked:** `secrets.yaml` (real values), `.storage/`, the recorder database, logs, `.cloud/`, `deps/`, `tts/`.
  `.storage/` stays covered by HA's own backups. `secrets.yaml.example` documents the keys.
- **Safety model:** both commands diff before acting. `ha-push` snapshots the remote first, uploads, runs
  `ha core check`, and restores the snapshot when the check fails. A restart happens only with `--restart`.
- **Connection settings:** `DOTFILES_HA_HOST` (default `homeassistant.local`), `DOTFILES_HA_USER` (`root`),
  `DOTFILES_HA_PORT` (`22`). Off-LAN machines reach the VM through `ProxyJump` via the NAS in `~/.ssh/config`.

## Tasks

- [x] 1. Add `run.py` constants, tree helpers (`diff_trees`, tar read/write), and the `ha-pull` / `ha-push` commands.
- [x] 2. Add `tests/unit/run/test_ha_sync.py`, including an end-to-end test against a local directory standing in for the
      VM's `/config` (fake `ssh` transport, fake `ha` binary).
- [x] 3. Add `homeassistant/README.md`, `homeassistant/config/secrets.yaml.example`, and a `.gitignore` guard for
      `secrets.yaml`.
- [x] 4. Update docs: `docs/RUN_PY_REFERENCE.md`, `.ctx/BUILD.md`, `.ctx/ARCHITECTURE.md`, root `README.md`,
      `vms/haos/README.md`, `services/README.md`.
- [x] 5. Run ruff, the unit suite, and the prek hooks.

## Manual step (owner)

Install the *Advanced SSH & Terminal* app in HAOS, add the public key of the machine running `run.py`, and start it.
Then run `python3 run.py ha-pull` to seed `homeassistant/config/` from the live instance and commit the result.
