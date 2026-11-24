[Project Root](../README.md) > **Profiles**

# Profiles

Per-machine overlays. A profile is a directory that follows the
[overlay contract](../bootstrap/README.md#overlay-contract) and takes effect only on machines where it is listed in the
overlays registry.

| Profile                                  | Purpose                                                              |
| ---------------------------------------- | -------------------------------------------------------------------- |
| [`personal-mac`](personal-mac/README.md) | Applications and the NAS music auto-mount for the personal MacBook   |
| [`nas`](nas/README.md)                   | Overlay for the home NAS (registered by the `dotfiles` Ansible role) |
