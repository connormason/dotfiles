[Project Root](../../README.md) > [Roles](../README.md) > **debian**

# debian

Base Debian configuration for the NAS: system packages (including everything the stow engine needs before it can run),
the Linuxbrew prefix, and the systemd sleep targets.

## Tasks

| Task             | Effect                                                                                                                                         |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| Sleep targets    | Masks or unmasks `sleep`, `suspend`, `hibernate`, `hybrid-sleep`; reads each state first (idempotent)                                          |
| apt packages     | `debian_engine_packages` + `debian_apt_packages`                                                                                               |
| Linuxbrew prefix | `/home/linuxbrew` (root, 0755) and `debian_linuxbrew_prefix` owned by `ansible_user`, so the engine's `50-brew` installs Homebrew without sudo |

## Variables

| Variable                   | Default                                            | Purpose                                                        |
| -------------------------- | -------------------------------------------------- | -------------------------------------------------------------- |
| `systemd_allow_sleep` etc. | `true`                                             | Whether each sleep target may run; overridden in the inventory |
| `debian_engine_packages`   | `build-essential procps curl file git zsh python3` | Engine prerequisites checked by `bootstrap/00-preflight.sh`    |
| `debian_apt_packages`      | `fzf exfat-fuse`                                   | Other packages                                                 |
| `debian_linuxbrew_prefix`  | `/home/linuxbrew/.linuxbrew`                       | Homebrew's Linux prefix                                        |
