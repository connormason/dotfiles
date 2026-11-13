[Project Root](../../README.md) > [Roles](../README.md) > **backup**

# backup

Nightly off-site backup of `/storage/media/config` and `/storage/backups` to a Backblaze B2 bucket with
[restic](https://restic.net), read from a ZFS snapshot rather than from the live databases.

The role depends on the [`debian`](../debian/README.md) role (`nas-notify` and the `nas-notify-failure@.service`
template) and on the [`zfs`](../zfs/README.md) role (the tools and the pool). It runs right after `zfs`, and stays inert
(with a warning) until a bucket is configured, so it never blocks the roles after it.

## Tasks

| Task                          | Effect                                                                                                                     |
| ----------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| Warn                          | Prints a warning and does nothing else while `backup_b2_bucket` is empty                                                   |
| Assert                        | Fails unless the three vault variables are set and the B2 values and paths are safe to write                               |
| restic                        | Installs the `restic` package (0.14.0 on Debian 12)                                                                        |
| Secrets                       | `/etc/restic/` (0700), `password` and `restic.env` (0600, root; `diff: false`, `no_log`)                                   |
| Scripts                       | `/usr/local/bin/restic-backup` (the job) and `/usr/local/bin/restic-nas` (restic with the job's credentials, for you)      |
| `restic-backup.service`/timer | Oneshot with `OnFailure=nas-notify-failure@%n.service`; the timer runs nightly at 02:30 (15 min jitter, `Persistent=true`) |

## How a run works

1. `restic cat config` proves the repository is reachable before anything is snapshotted.
2. Each path is mapped to its dataset with `findmnt`; a path that is not on ZFS stops the run (it would otherwise be
   backed up live).
3. `zfs snapshot -r storage@restic-backup` is taken. A stale one left by a killed run is destroyed first.
4. restic reads the paths through `<mountpoint>/.zfs/snapshot/restic-backup/...`. ZFS automounts that directory on
   access even though `snapdir=hidden`, so no mount or clone is managed. `storage/backups` is a separate dataset, which
   is why the snapshot is recursive.
5. `restic forget --prune --keep-daily 14 --keep-weekly 8 --keep-monthly 12`.
6. The snapshot is destroyed on every exit path.

The job takes its own snapshot instead of reusing a sanoid one: the interim sanoid policy covers only `storage` itself
(`recursive = no`), so `storage/backups` has no sanoid snapshots, and a fixed name keeps restic's paths stable so each
run finds its parent snapshot instead of rescanning. The copy is crash-consistent; SQLite replays its journal when a
restored database is first opened. restic stores the paths as read, so files appear in the repository under
`/storage/.zfs/snapshot/restic-backup/media/config/...` and `/storage/backups/.zfs/snapshot/restic-backup/...`.

## Setup (once)

1. In Backblaze, create a **private** bucket and an application key restricted to that bucket.
2. Add to the inventory vault: `restic_b2_account_id` (the key ID), `restic_b2_account_key` (the key) and
   `restic_repository_password` (generate a long random one). Keep a copy of the password outside the NAS: without it
   the backup cannot be read.
3. Set `backup_b2_bucket` in the NAS host variables (`host_vars/nas/vars.yml`).
4. `python3 run.py nas-provision --tags backup`. Nothing is written until step 3 is done.
5. `sudo restic-nas init`, once. The job refuses to run against an uninitialised repository.
6. `sudo systemctl start restic-backup.service` and follow it with `journalctl -fu restic-backup`. The first upload
   moves about 22 GB.

Check afterwards with `systemctl list-timers restic-backup.timer` and `sudo restic-nas snapshots`.

## Restore test

Run this after the first backup and again every few months. It proves the repository password, the key and the data.

```bash
mkdir -p "$TMPDIR/restore-test"
sudo restic-nas find sonarr.db                      # shows the path stored in the repository
sudo restic-nas restore latest --target "$TMPDIR/restore-test" \
    --include '/storage/.zfs/snapshot/restic-backup/media/config/sonarr/sonarr.db'
sqlite3 "$TMPDIR/restore-test/storage/.zfs/snapshot/restic-backup/media/config/sonarr/sonarr.db" 'PRAGMA integrity_check;'
```

Expect `ok`. Delete `$TMPDIR/restore-test` afterwards. For a deeper check, `sudo restic-nas check --read-data-subset=5%`
downloads a random 5% of the data and verifies it.

To test the alert path once `nas-notify` has an ntfy token, run
`sudo systemctl start nas-notify-failure@restic-backup.service`. It sends the same "Unit failed: restic-backup.service"
style alert that `OnFailure=` raises, so it proves delivery, not the `OnFailure=` wiring; the wiring is covered by the
unit's tests.

## Variables

| Variable                                        | Default                                  | Purpose                                              |
| ----------------------------------------------- | ---------------------------------------- | ---------------------------------------------------- |
| `backup_b2_bucket`                              | `""`                                     | Bucket name; the role is inert until it is set       |
| `backup_b2_prefix`                              | `restic`                                 | Folder inside the bucket                             |
| `restic_b2_account_id` (vault)                  | none                                     | B2 key ID (via `backup_b2_account_id`)               |
| `restic_b2_account_key` (vault)                 | none                                     | B2 application key (via `backup_b2_account_key`)     |
| `restic_repository_password` (vault)            | none                                     | restic password (via `backup_repository_password`)   |
| `backup_paths`                                  | `/storage/media/config /storage/backups` | Paths to back up; each must be on ZFS, no whitespace |
| `backup_zfs_dataset`                            | `storage`                                | Dataset snapshotted recursively                      |
| `backup_keep_daily` / `weekly` / `monthly`      | `14` / `8` / `12`                        | Retention for `restic forget`                        |
| `backup_on_calendar`, `backup_randomized_delay` | `*-*-* 02:30:00`, `15min`                | Timer schedule                                       |
| `backup_config_dir`                             | `/etc/restic`                            | Holds `password` and `restic.env`                    |
