# NAS and Dotfiles Audit: Improvement Plan

Date: 2026-11-11. Source: a full audit of the repository and of the live NAS (read-only checks run on the NAS itself).
SMART data and the host firewall need sudo and were **not** checked in the audit; they were checked on 2026-11-12 (see
[Baseline results](#baseline-results-2026-11-12)).

## Summary

The repository is well engineered (deep tests, leak guard, CI deploys, honest docs). The weakness is on the NAS: the
engineering went into how the stack is deployed, not into whether the data survives or the host stays patched. This plan
spends the next effort on the services and the storage, not on more tooling.

## Audit findings (evidence)

| Area         | Finding                                                                                                     | Evidence                                                  |
| ------------ | ----------------------------------------------------------------------------------------------------------- | --------------------------------------------------------- |
| Storage      | Pool `storage` is a 2-disk stripe (`sda`, `sdc`, 8 TB each), 5.7 TB used, no redundancy                     | `zpool status`                                            |
| Storage      | No ZFS snapshots                                                                                            | `zfs list -t snapshot`                                    |
| Storage      | `compression=off`, `atime=on`; one dataset, `media/` is a plain directory                                   | `zfs get`                                                 |
| Monitoring   | No `smartmontools`, `sanoid`, `restic`, `borg`, `rclone`; no ZED alerting                                   | `command -v`                                              |
| Backups      | Arr/Plex/Jellyfin configs live only on the stripe; only Home Assistant has an off-site copy (Google Drive)  | `services/README.md`, `vms/haos/README.md`                |
| Patching     | `unattended-upgrades` not installed                                                                         | `dpkg -l`                                                 |
| Docker       | Every image `:latest`; `up -d` never pulls; 62 images, 20 GB reclaimable (79%); no `daemon.json` log limits | `docker images`, `docker system df`, `services/*/compose` |
| Docker       | No healthchecks in any compose file                                                                         | `docker inspect`                                          |
| Docker       | `docker` role installs deprecated v1 `docker-compose` next to the compose plugin                            | `roles/docker/tasks/main.yml`                             |
| Exposure     | All service UIs bind `0.0.0.0`; Glance mounts `docker.sock`; `PasswordAuthentication` unset (defaults yes)  | `ss`, `services/glance/compose.yml`, `sshd_config`        |
| Transmission | No VPN; peer port 51413 exposed but not published                                                           | `docker ps`, `transmission/compose.yml`                   |
| Media layout | Autoplex copy mode on separate bind mounts: every download is stored twice, hardlinks impossible            | `autoplex/compose.yml`                                    |
| Drift        | `run.py doctor` red on the NAS: venv, 5 unlinked yazi links, render, Brewfile                               | `uv run run.py doctor`                                    |
| Drift        | Disabled services keep running; the sync never deletes                                                      | `services/README.md`                                      |
| Cleanup      | Hardcoded `/pihole` Caddy route; `Caddyfile.j2.archived`; `~/nas-probe.sh`, `~/mnamer`, `~/autoplex`        | `roles/tailscale`, `roles/docker`, `~`                    |
| Dev env      | Tool duplication; `mise` installed but unwired; `profiles/nas` empty; `pull.rebase=false`                   | `bootstrap/Brewfile`, `uv-tools.txt`, `.gitconfig`        |
| Repo         | `run.py` is 5,115 lines in one file; no behavioral (converge-twice) Ansible test                            | `wc -l`, `tests/`                                         |

## Baseline results (2026-11-12)

Phase 1 item 1 was run on the NAS (`smartctl -a`, `lsblk`, `iptables -S`, `dmesg`). Outcomes, and where each is handled:

| Device                           | Result                                                                                                                                                                                                                              | Handled by                                              |
| -------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------- |
| `sda`, `sdc` (WD80EFZZ 8 TB)     | Healthy: 0 reallocated, pending or uncorrectable sectors, no errors logged, 35-36 °C. 28,353 h and 28,666 h powered on (about 3.2 years). **No self-test has ever run.** Both are the same model and age, in a stripe.              | smartd self-tests (PR 57); redundancy decision (1.9)    |
| `sdb`, `sdd` (Crucial MX500 1TB) | Healthy: 0 errors, lifetime remaining 100, about 350 GB and 690 GB written. `sdb` logged 58 unexpected power losses (`sdd`: 10); attribute 180 reads 000 on both, assumed to be an MX500 reporting quirk (threshold 0, unverified). | smartd; investigate the power losses                    |
| `sdd` partitions                 | A 16 MB partition and a 146.5 GB partition exist, with no filesystem type visible to a non-root `lsblk`. `sdb` has none. Contents are unknown.                                                                                      | Inspect before any reuse (see below)                    |
| `sde` (Seagate ST2000DM001)      | Faulty. The kernel sees 3.9 GB, ATA IDENTIFY reports 137 GB (exactly the 28-bit LBA limit), and every SMART read aborts. No partitions, not in the pool. Not hotplugged: its by-id link dates from boot.                           | Ignored by smartd (PR 57); remove the drive physically  |
| `nvme0n1` (Samsung 970 EVO Plus) | The root disk. **Not baselined**: the audit's command list omitted it. smartd now scans it.                                                                                                                                         | Run `sudo smartctl -a /dev/nvme0` once                  |
| Firewall                         | `INPUT`, `FORWARD` and `OUTPUT` all default to ACCEPT. The only rules are Docker's, libvirt's and Tailscale's, so every published port is reachable from the LAN.                                                                   | Phase 3.3 (loopback binds); decide on a host firewall   |
| USB `1-6` (dresden elektronik)   | `dmesg` shows this device re-enumerating roughly hourly, two lines about 4 s apart. Not investigated; could be passthrough to the Home Assistant OS VM or the stick resetting.                                                       | Investigate (see below)                                 |

Follow-ups that stay open:

- **Inspect `sdd` before reuse.** `sudo blkid /dev/sdd1 /dev/sdd2`, `sudo wipefs -n /dev/sdd`, then mount read-only to
  look. Do not format it until the contents are known.
- **Baseline the NVMe disk.** `sudo smartctl -a /dev/nvme0`.
- **Check `sde` for kernel-level errors.** The first `dmesg` filter matched `dresden` ("dre**sde**n"), so any real `sde`
  errors were missed. Use `sudo dmesg | grep -E '\bsde\b|\[sde\]|ata[0-9]+\.[0-9]+:'`. Whether the port or the drive
  is at fault decides if the SATA port is safe to reuse.
- **Investigate the hourly USB re-enumeration** with `lsusb -t`, `sudo journalctl -k | grep 1-6`, and the HAOS VM's USB
  hostdev settings in `vms/haos/`. If the Zigbee coordinator drops hourly, Home Assistant loses its mesh each time.
- **Long self-tests** take about 14 hours on the 8 TB disks and run together on the 1st at 04:00. Staggering exists in
  smartd but is marked experimental; revisit if Plex or Jellyfin suffer.

## Principles

- Everything lands through the repo (roles, compose files, tests), never as a one-off command on the NAS, unless the
  step is destructive or hardware-specific (marked **manual**).
- One phase per branch and PR, in a git worktree. CI deploys `services/` on merge, so service changes go one service at
  a time.
- Each phase ends with a verification step that proves the behavior, not just that the YAML parses (see
  `CLAUDE-LESSONS.md`: "run the role").
- Docs that enumerate things stay guarded by the existing consistency tests; update READMEs in the same change.

## Phase 1: Data safety

Goal: a disk failure or bad write is detected early and is recoverable for everything irreplaceable.

1. **Baseline (manual, needs sudo).** *Done 2026-11-12; see [Baseline results](#baseline-results-2026-11-12).* Still
   open: the contents of the `sdd` partitions, `smartctl` on `nvme0n1`, and a narrower `dmesg` check of `sde`. `sde` is
   faulty and should be removed, not reused. Note that `smartctl` is not installed until the `debian` role provisions
   `smartmontools`, so the baseline needs `sudo apt-get install smartmontools` first.
2. **`smartmontools` + `smartd`.** Add to `debian_apt_packages` (or a new `monitoring` role); `smartd.conf` with a short
   self-test weekly and a long self-test monthly; alert to the channel built in Phase 4.
3. **ZED alerting.** Template `/etc/zfs/zed.d/zed.rc` (notify on scrub finish, resilver, checksum errors, pool state);
   same alert channel.
4. **Dataset layout (manual migration, then codified).** Create `storage/media/{tv,movies,music,downloads,config}`
   as datasets. Migrating in place means a new dataset, `mv` of contents within the pool, and a changed mountpoint, so
   schedule it with the media services stopped. Set `compression=lz4`, `atime=off` on `storage` (inherited).
   Compression applies to new writes only.
5. **Codify in the `zfs` role.** Today it installs packages and manages no pools. Add tasks that assert the pool exists,
   create missing datasets idempotently, and set properties. Never create or destroy a pool from Ansible.
6. **Snapshots.** Install `sanoid`; policy: `config` hourly 24 / daily 30 / monthly 6, `backups` daily 30 / monthly 12,
   media datasets daily 7 only.
7. **Off-site backup.** `restic` to Backblaze B2 of `/storage/media/config` and `/storage/backups` (plus any personal
   data directories chosen at execution time), run from a systemd timer, with the repository password and B2 key in the
   inventory vault and rendered to a `0600` file. Prune policy keep-daily 14, weekly 8, monthly 12. Stop-before-copy for
   the Arr databases is replaced by snapshotting `config` and backing up the snapshot.
8. **`fast` pool on the two 1 TB SSDs (decision).** Mirror `sdb` + `sdd`; host `config`, Plex/Jellyfin metadata and
   incomplete downloads. Gets databases off the stripe and speeds up metadata. Needs a decision before execution (see
   open questions).
9. **Bulk-pool redundancy (decision).** A stripe cannot be converted in place. Options: second 8 TB disk with `syncoid`
   replication, or accept the risk for re-downloadable media.

**Verification:** `systemctl list-timers` shows the snapshot, restic and smartd jobs; `zfs list -t snapshot` is
non-empty; a restore test pulls one Sonarr database from B2 into `$TMPDIR` and opens it with `sqlite3`; a forced alert
(`zpool scrub` on a test, or `smartctl -t short` with the alert channel active) arrives.

## Phase 2: Host hygiene

1. **`unattended-upgrades`** (security origin only, no automatic reboot because of `zfs-dkms`), plus a
   `reboot-required` notification through the alert channel.
2. **SSH hardening.** `PasswordAuthentication no` and `PermitRootLogin no` in an `sshd_config.d` drop-in, validated with
   `sshd -t`; confirm key login works from a second session before closing the first.
3. **Docker daemon.** Template `/etc/docker/daemon.json` with `log-driver json-file`, `max-size 10m`, `max-file 3`.
   Restarting `docker` recreates nothing, but schedule it in a quiet window.
4. **Remove the apt `docker-compose` (v1) package**; keep the plugin.
5. **Prune.** Remove unused images (deconz, mosquitto, smartthings bridge, old autoplex, `caddy:latest`, `python`
   images); add a weekly `docker image prune -af --filter until=168h` timer.
6. **Strays.** Remove `~/nas-probe.sh`, `~/nas-probe.txt`, `~/mnamer`, `~/autoplex` after confirming nothing references
   them (the old systemd `autoplex.service` may).
7. **Re-stow and converge.** Run the stow engine on the NAS (clears the 5 yazi links), `uv sync`, `run.py render`,
   `brew bundle`; then add a weekly systemd timer on the NAS that runs `git pull --ff-only`, `stow.sh`, and
   `run.py doctor`, alerting on red.

**Verification:** `run.py doctor` all green on the NAS; `unattended-upgrade --dry-run` lists the security origin;
`ssh -o PubkeyAuthentication=no nas` is refused; `docker system df` shows reclaimed space; log files stay under the cap.

## Phase 3: Service layer

1. **Pin images.** Replace `:latest` with explicit version tags (linuxserver tags, `caddy:2.x-alpine`, a Glance and
   Flaresolverr version). Add `renovate.json` scoped to `services/` with a 3-day minimum release age, matching the
   existing `prek update --cooldown-days 3` stance. A merged Renovate PR triggers the existing CI deploy.
2. **Healthchecks and restart policy** per service (HTTP check where the app exposes one); consider `depends_on` with
   `condition: service_healthy` only where services genuinely depend on each other.
3. **Bind ports to `127.0.0.1`** for services reachable through Caddy and not needed directly on the LAN. Keep Plex,
   Jellyfin discovery ports and Home Assistant-related ports as they are. Do this per service and re-test the
   `tailscale_services` routes after each.
4. **`docker-socket-proxy` for Glance** (read-only `containers` endpoint only), removing the direct socket mount.
5. **Unified media layout.** Mount `/storage/media` as `/data` in Sonarr, Radarr, Transmission, Plex and Jellyfin; set
   the Arr root folders and Transmission's download dir under `/data`. Enable hardlinks in Sonarr and Radarr. Migration
   is a one-time per-app UI change; do it with a copy of `config/` snapshotted first (Phase 1).
6. **Retire Autoplex** once hardlink imports are proven: remove `services/autoplex`, the `docker` role's autoplex clone
   and build tasks, the README sections, and the docs-consistency expectations.
7. **`gluetun` for Transmission.** Run Transmission with `network_mode: service:gluetun`, publish the web UI port on the
   gluetun service, and use the provider's forwarded port. Provider credentials go in `services/gluetun/env.j2` and the
   vault. Requires a decision on provider (see open questions).
8. **Authentication audit** of the Arr apps, Transmission and Jellyfin; set required auth to "enabled for all" where it
   is not.
9. **Tidy the templates.** Drop the hardcoded `/pihole` Caddy route (render it only when the service has a
   `compose.yml`), delete `Caddyfile.j2.archived`, and decide PiHole's fate (re-enable with the port-53 fix or delete
   the definition and the `docker` role's PiHole directory task).
10. **Reconcile command.** `deploy.sh reconcile` lists containers and `~/docker/*/compose.yml` that the repo no longer
    defines; with `--prune` it stops and renames them. Closes the "disabling stops nothing" gap.

**Verification:** per service, `docker inspect` shows the pinned image and `healthy`; `ss -tln` shows the intended
bindings; a download imported by Sonarr has a link count of 2 (`stat -c %h`) and `df` shows no growth; the Transmission
container's public IP (`docker exec gluetun wget -qO- ifconfig.me`) is the VPN's, and the forwarded port tests open; the
Caddy routes still answer over the tailnet.

## Phase 4: Observability and new services

Each new service follows the existing pattern: `services/<name>/compose.yml`, `env.j2` if it holds a secret, a row in
`services/README.md`, and a `tailscale_services` entry in the inventory for HTTPS access.

1. **ntfy** (alert channel for Phases 1 and 2) and **Uptime Kuma** (HTTP and TCP checks for every service plus
   certificate expiry). Build ntfy first; Phases 1 and 2 reference it.
2. **Beszel** (or Netdata) for host and container metrics; alert on disk, memory and pool capacity.
3. **Glance as an operations page:** replace the sample content (London weather, sample feeds) with `docker-containers`,
   `server-stats` and `monitor` widgets, and local weather.
4. **Immich** for phone photo backup, with its library on a snapshotted dataset included in the restic job.
5. **Media extras:** Recyclarr (quality profiles as code, in Git), Bazarr (subtitles), Jellyseerr (requests).
6. **Optional:** Vaultwarden (tailnet-only), Dozzle (logs), Paperless-ngx, Syncthing. Add only on need.
7. **Remote access to Home Assistant:** advertise the LAN as a Tailscale subnet route from the NAS
   (`tailscale set --advertise-routes=<lan-cidr>`, approve in the admin console), and update the "Remote access" section
   of `vms/haos/README.md`.

**Verification:** a deliberate stop of one container produces an ntfy push within the Kuma interval; Beszel shows all
containers; Immich restores a test photo from the restic repository.

## Phase 5: Dotfiles and dev environment

1. **Trim the manifests.** Decide per group and record the choice in the commit:
   - Task runners: keep one of `just`, `go-task`, `hk`, `mk`, `fzf-make`.
   - Hook runner: keep `prek`, drop `pre-commit`.
   - Python linters and checkers: keep `ruff` + `mypy` (the repo's CI set); drop `pylint`, `flake8`, `pyright`, `ty`
     unless used elsewhere.
   - Packaging: drop `poetry`, `pew`, `pex`, `shiv`, `pyinstaller`, `zipapps` if unused.
   - Drop `hub` (keep `gh`); keep one of `gitui` / `lazygit`.
   - Move `postgresql` and other desktop-only formulae into the `if OS.mac?` block (or the `personal-mac` overlay) so the
     NAS stops installing them.
2. **`mise`:** wire activation and a global `config.toml` for runtime versions, or remove it and `direnv` overlap.
3. **`atuin`:** add the formula and a `stow/atuin` package with its `conf.d` snippet; register it in `stow/README.md`.
4. **Git defaults:** `pull.rebase true`, `push.autoSetupRemote true`, `rerere.enabled true`, `diff.algorithm histogram`.
5. **`profiles/nas` content:** `ctop` or `dive`, ZFS and Docker aliases, a NAS banner; update the profile README.
6. **`yazi`:** finish the placeholder config or remove the package.
7. **Behavioral Ansible test.** A CI job (Debian container) that converges the `debian`, `docker` (without starting the
   daemon), and `services` roles twice and fails unless the second run reports `changed=0`. Reuses the pattern in
   `tests/unit/test_services_role.py`.
8. **Split `run.py`.** If a bare-`python3` entry point must remain, keep a small shim and move command classes into a
   package under `scripts/`. Do this last; it is the largest and least urgent change.
9. **Housekeeping:** delete finished items from `docs/notes/todo.md` (`lazydocker`, "install brew on linux too?"), and
   fold the remaining ones into this plan or the task tracker.

**Verification:** `uv run pytest`, `prek run --all-files`, and the bootstrap dry run on both macOS and Linux CI jobs;
`run.py doctor` green on the NAS and the Mac.

## Sequence and sizing

| Phase | Depends on                      | Size   | Risk                                           |
| ----- | ------------------------------- | ------ | ---------------------------------------------- |
| 1     | none (alert channel from 4.1)   | Large  | Dataset migration needs downtime               |
| 2     | none                            | Small  | SSH change can lock out: test a second session |
| 3     | Phase 1 snapshots before 3.5    | Large  | Media-layout change touches every Arr app      |
| 4     | none; 4.1 early                 | Medium | Low                                            |
| 5     | none                            | Medium | Low; `run.py` split is the outlier             |

Recommended order: 4.1 (ntfy) → 1.1–1.3 → 1.6–1.7 → Phase 2 → 1.4–1.5 → Phase 3 → rest of Phase 4 → Phase 5.

## Open questions

1. VPN provider for `gluetun` (needs port forwarding support)?
2. Use the two 1 TB SSDs as a mirrored `fast` pool, or keep one as a backup target?
3. Backup scope beyond `config/` and `backups/`: which personal directories are irreplaceable?
4. Re-enable PiHole (network-wide DNS) or delete its definition?
5. Alert delivery: self-hosted ntfy only, or also email?
6. Which task runner and linter set to keep in Phase 5.1?
7. Is the bare-`python3` entry point for `run.py` still required, which decides whether the split is a package or a shim?
8. Should the faulty `sde` (ST2000DM001) be removed from the chassis now, and does the hourly USB re-enumeration of the
   dresden elektronik device matter to the Zigbee setup?
9. Add a host firewall (the policy is ACCEPT everywhere), or rely on loopback binds from Phase 3.3 and the tailnet?
