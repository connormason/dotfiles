[Project Root](../../README.md) > [Roles](../README.md) > **zfs**

# zfs

Installs ZFS on Debian: enables the `contrib` apt component when it is missing (installing `software-properties-common`
first, for `apt-add-repository`), then installs the kernel headers and image for the host architecture plus `dpkg-dev`,
`zfs-dkms`, and `zfsutils-linux`. It then manages the existing pool's properties, ZED alert routing, and snapshots. The
role never creates, imports, or destroys a pool or a dataset.

## Tasks

| Task               | Effect                                                                                                                                                       |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Pool properties    | Fails unless `zfs_pool_name` exists, then sets each `zfs_pool_properties` entry that differs (default `compression=lz4`, `atime=off`); skipped in check mode |
| ZED                | Edits `zed.rc` so notifications run through `nas-notify` (from the [`debian`](../debian/README.md) role) and healthy scrubs and resilvers are reported too   |
| Snapshots (sanoid) | Installs `sanoid`, renders `/etc/sanoid/sanoid.conf`, enables `sanoid.timer`, and alerts when `sanoid.service` or `sanoid-prune.service` fails               |

Compression applies to data written after the property is set; existing blocks stay uncompressed.

ZED goes through its email hook because the OpenZFS 2.1 packaged on Debian 12 has no ntfy notifier. With no `@SUBJECT@`
in `ZED_EMAIL_OPTS`, ZED writes a `Subject:` line and then the message body to stdin, which `nas-notify -z` parses. The
`zed.rc` path is `zfs_zed_rc_path`.

The pool is a single dataset today, so the snapshot policy is one interim template (`hourly 24`, `daily 7`, no monthly)
applied to the whole pool. Replace `zfs_sanoid_datasets` and `zfs_sanoid_templates` with per-dataset policies once
`config`, `backups`, and the media datasets exist.

## Variables

| Variable               | Default                                                   | Purpose                                          |
| ---------------------- | --------------------------------------------------------- | ------------------------------------------------ |
| `zfs_pool_name`        | `storage`                                                 | The existing pool this role manages              |
| `zfs_pool_properties`  | `compression: lz4`, `atime: "off"`                        | Properties set on the pool's root dataset        |
| `zfs_zed_rc_path`      | `/etc/zfs/zed.d/zed.rc`                                   | The ZED settings file                            |
| `zfs_zed_settings`     | `ZED_EMAIL_PROG`, `ZED_EMAIL_OPTS`, `ZED_NOTIFY_VERBOSE`… | `zed.rc` keys and their shell-quoted values      |
| `zfs_sanoid_templates` | one `interim` template                                    | Retention counts per template                    |
| `zfs_sanoid_datasets`  | the pool, using `interim`                                 | Datasets to snapshot and the template each uses  |
| `zfs_sanoid_units`     | `sanoid.service`, `sanoid-prune.service`                  | Units that alert through `nas-notify` on failure |
