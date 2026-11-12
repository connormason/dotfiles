[Project Root](../../README.md) > [Roles](../README.md) > **debian**

# debian

Base Debian configuration for the NAS: system packages (including everything the stow engine needs before it can run),
the Linuxbrew prefix, the systemd sleep targets, and alerting (SMART monitoring plus the `nas-notify` publisher that the
[`zfs`](../zfs/README.md) role's ZED and sanoid hooks also use).

## Tasks

| Task             | Effect                                                                                                                                                                                                               |
| ---------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Sleep targets    | Masks or unmasks `sleep`, `suspend`, `hibernate`, `hybrid-sleep`; reads each state first (idempotent)                                                                                                                |
| apt packages     | `debian_engine_packages` + `debian_apt_packages`                                                                                                                                                                     |
| Linuxbrew prefix | The parent of `debian_linuxbrew_prefix` (`/home/linuxbrew` by default; root, 0755) and `debian_linuxbrew_prefix` owned by `ansible_user`, so the engine's `50-brew` installs Homebrew without sudo                   |
| Alerting         | `/usr/local/bin/nas-notify`, the `nas-notify-failure@.service` template, and `/etc/nas-notify.env` (0600, holds the ntfy token), then `/etc/smartd.conf` and the `smartmontools` service (see [Alerting](#alerting)) |

## Alerting<a name="alerting"></a>

[`nas-notify`](files/nas-notify) logs every alert to the journal (tag `nas-notify`) and publishes it to the local
[ntfy](../../services/README.md) server when `/etc/nas-notify.env` holds a token. Without a token it logs only and exits
0, so a host provisioned before ntfy has a token still converges. It serves three callers:

- direct calls (`nas-notify -p high -t Title message`), used by the failure template;
- smartd (`-M exec`), detected by `SMARTD_MESSAGE` in the environment;
- ZED (`nas-notify -z`), which reads ZED's `Subject:` line and body from stdin.

`smartd.conf` is a single `DEVICESCAN` line: health, error-log and self-test-log monitoring, a short self-test Sundays
at 03:00 and a long one on the 1st at 04:00 (`debian_smartd_schedule`). `nas-notify-failure@.service` turns any unit's
`OnFailure=nas-notify-failure@%n.service` into an alert; the [`zfs`](../zfs/README.md) role attaches it to sanoid.

To start delivering to ntfy, create the token as described in the [ntfy section](../../services/README.md), store it in
the inventory vault as `ntfy_alerts_token`, and run `python3 run.py nas-provision --tags debian`. After any change,
`nas-notify -t Test "hello"` on the NAS sends a test alert.

## Variables

| Variable                   | Default                                            | Purpose                                                        |
| -------------------------- | -------------------------------------------------- | -------------------------------------------------------------- |
| `systemd_allow_sleep` etc. | `true`                                             | Whether each sleep target may run; overridden in the inventory |
| `debian_engine_packages`   | `build-essential procps curl file git zsh python3` | Engine prerequisites checked by `bootstrap/00-preflight.sh`    |
| `debian_apt_packages`      | `fzf exfat-fuse smartmontools`                     | Other packages                                                 |
| `debian_linuxbrew_prefix`  | `/home/linuxbrew/.linuxbrew`                       | Homebrew's Linux prefix                                        |
| `debian_ntfy_url`          | `http://127.0.0.1:2586`                            | Where `nas-notify` publishes                                   |
| `debian_ntfy_topic`        | `nas-alerts`                                       | ntfy topic for alerts                                          |
| `debian_ntfy_token`        | `{{ ntfy_alerts_token \| default('') }}`           | Publisher token; `ntfy_alerts_token` is a vault variable       |
| `debian_smartd_schedule`   | `(S/../../7/03\|L/../01/./04)`                     | smartd self-test schedule regexp                               |
