[Project Root](../../README.md) > [Roles](../README.md) > **debian**

# debian

Base Debian configuration for the NAS: system packages (including everything the stow engine needs before it can run),
the Linuxbrew prefix, the systemd sleep targets, alerting (SMART monitoring plus the `nas-notify` publisher that the
[`zfs`](../zfs/README.md) role's ZED and sanoid hooks also use), and automatic security upgrades with a reboot alert.

## Tasks

| Task             | Effect                                                                                                                                                                                                               |
| ---------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Sleep targets    | Masks or unmasks `sleep`, `suspend`, `hibernate`, `hybrid-sleep`; reads each state first (idempotent)                                                                                                                |
| apt packages     | `debian_engine_packages` + `debian_apt_packages`                                                                                                                                                                     |
| Linuxbrew prefix | The parent of `debian_linuxbrew_prefix` (`/home/linuxbrew` by default; root, 0755) and `debian_linuxbrew_prefix` owned by `ansible_user`, so the engine's `50-brew` installs Homebrew without sudo                   |
| Upgrades         | `unattended-upgrades` limited to the security origin with no automatic reboot, plus the `nas-reboot-check` timer (see [Unattended upgrades and reboots](#unattended-upgrades))                                       |
| Alerting         | `/usr/local/bin/nas-notify`, the `nas-notify-failure@.service` template, and `/etc/nas-notify.env` (0600, holds the ntfy token), then `/etc/smartd.conf` and the `smartmontools` service (see [Alerting](#alerting)) |

## Unattended upgrades and reboots<a name="unattended-upgrades"></a>

The `unattended-upgrades` package installs security updates daily without rebooting. Three files carry the policy:

- `/etc/apt/apt.conf.d/20auto-upgrades` turns on the daily package-list refresh and the unattended run (the apt
  package's `apt-daily.timer` and `apt-daily-upgrade.timer` drive them, and the role asserts both are enabled).
- `/etc/apt/apt.conf.d/52nas-unattended-upgrades` sorts after the package's own `50unattended-upgrades` and replaces its
  origin list. Debian's default list also contains `label=Debian`, the regular stable repository (point-release
  updates), so the drop-in uses `#clear` and keeps only `codename=${distro_codename}-security`. Docker's and Tailscale's
  repositories never match, which keeps `docker-ce` from upgrading unattended (that would restart `dockerd` and stop
  every container). It also sets `Automatic-Reboot "false"`: with `zfs-dkms`, a reboot should follow a check that DKMS
  built the module for the new kernel.
- `apt-daily-upgrade.service` gets an `OnFailure=` drop-in, so a failed run raises an alert through `nas-notify`.

The logs are in `/var/log/unattended-upgrades/`. `sudo unattended-upgrade --dry-run --debug` shows the origins it allows
and what it would install.

**Reboot alert.** `nas-reboot-check` runs daily at 09:00 (`nas-reboot-check.timer`) and alerts when
`/run/reboot-required` exists or a kernel newer than the running one is installed in `/boot`. The second signal matters:
`/run/reboot-required` is written by `update-notifier-common`, which this host does not install. When a newer kernel is
the reason, the alert says whether `dkms status` shows the zfs module as `installed` for it; if not, the alert is
`urgent` and says not to reboot, because a kernel without `zfs.ko` boots with the pool unimported. The same condition is
announced once and repeated weekly while it persists; the state file lives in `/run`, so it resets at boot.

## Alerting<a name="alerting"></a>

[`nas-notify`](files/nas-notify) logs every alert to the journal (tag `nas-notify`) and publishes it to the local
[ntfy](../../services/README.md) server when `/etc/nas-notify.env` holds a token. Without a token it logs only and exits
0, so a host provisioned before ntfy has a token still converges. It serves three callers:

- direct calls (`nas-notify -p high -t Title message`), used by the failure template;
- smartd (`-M exec`), detected by `SMARTD_MESSAGE` in the environment;
- ZED (`nas-notify -z`), which reads ZED's `Subject:` line and body from stdin.

`smartd.conf` is one `DEVICESCAN` line (preceded by a `-d ignore` line per entry of `debian_smartd_ignored_devices`):
health, error-log and self-test-log monitoring, a short self-test Sundays at 03:00 and a long one on the 1st at 04:00
(`debian_smartd_schedule`). The long test takes about 14 hours on the 8 TB disks. The line deliberately omits `-o on`
(ATA-only; the WD drives do not support automatic offline testing) and `-S on`, because the root disk is NVMe and the
scan covers it. The ignore list holds the faulty Seagate ST2000DM001 (3.9 GB to the kernel, 137 GB to ATA IDENTIFY,
every SMART read aborts; no partitions), which would otherwise alert daily. `nas-notify-failure@.service` turns any
unit's `OnFailure=nas-notify-failure@%n.service` into an alert; the [`zfs`](../zfs/README.md) role attaches it to
sanoid.

To start delivering to ntfy, create the token as described in the [ntfy section](../../services/README.md), store it in
the inventory vault as `ntfy_alerts_token`, and run `python3 run.py nas-provision --tags debian`. After any change,
`nas-notify -t Test "hello"` on the NAS sends a test alert.

## Variables

| Variable                            | Default                                                                    | Purpose                                                        |
| ----------------------------------- | -------------------------------------------------------------------------- | -------------------------------------------------------------- |
| `systemd_allow_sleep` etc.          | `true`                                                                     | Whether each sleep target may run; overridden in the inventory |
| `debian_engine_packages`            | `build-essential procps curl file git zsh python3`                         | Engine prerequisites checked by `bootstrap/00-preflight.sh`    |
| `debian_apt_packages`               | `fzf exfat-fuse smartmontools unattended-upgrades`                         | Other packages                                                 |
| `debian_linuxbrew_prefix`           | `/home/linuxbrew/.linuxbrew`                                               | Homebrew's Linux prefix                                        |
| `debian_ntfy_url`                   | `http://127.0.0.1:2586`                                                    | Where `nas-notify` publishes                                   |
| `debian_ntfy_topic`                 | `nas-alerts`                                                               | ntfy topic for alerts                                          |
| `debian_ntfy_token`                 | `{{ ntfy_alerts_token \| default('') }}`                                   | Publisher token; `ntfy_alerts_token` is a vault variable       |
| `debian_smartd_schedule`            | `(S/../../7/03\|L/../01/./04)`                                             | smartd self-test schedule regexp                               |
| `debian_smartd_ignored_devices`     | the ST2000DM001's `/dev/disk/by-id` path                                   | Devices smartd skips; remove the entry when the drive is gone  |
| `debian_unattended_origin_patterns` | `origin=Debian,codename=${distro_codename}-security,label=Debian-Security` | Origins upgraded automatically (replaces Debian's list)        |
| `debian_reboot_check_on_calendar`   | `*-*-* 09:00:00`                                                           | When `nas-reboot-check` looks for a pending reboot             |
