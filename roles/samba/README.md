[Project Root](../../README.md) > [Roles](../README.md) > **samba**

# samba

Installs Samba on the NAS, renders `/etc/samba/smb.conf` from a list of shares, starts `smbd` and `nmbd`, and adds the
Samba users. Runs between the `zfs` and `docker` roles in `playbooks/nas_bootstrap.yml`.

## Tasks

All of `tasks/main.yml`, in order, plus the one handler. Steps marked root run with `become`; the others run as the SSH
user.

| Step    | Task                                              | Effect                                                                                                                                                                                                                                                       |
| ------- | ------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1       | Install Samba (root)                              | `apt` install of `samba` and `smbclient`                                                                                                                                                                                                                     |
| 2       | Register Samba version (root)                     | Runs `smbd --version`, strips the `Version ` prefix, and registers the result as `samba_version`; never reports changed. Tag `always`, so it runs whenever the role's include runs, including under `--tags configfile` (the template needs `samba_version`) |
| 3       | Build Samba configuration file (root)             | Renders `templates/smb.conf.j2` to `samba_configuration` (`/etc/samba/smb.conf`, mode `0644`), validated with `testparm -s` before it replaces the file; notifies the restart handler. Tag `configfile`                                                      |
| 4       | Start Samba services                              | Starts and enables each service in `samba_services` (`smbd`, `nmbd`)                                                                                                                                                                                         |
| 5       | Create Samba users if they don't exist yet (root) | For each entry of `samba_users`, adds the user with `smbpasswd -s -a` unless `pdbedit` already knows the name; `no_log`; changed only when the output contains `Added user`; skipped when `samba_users` is empty or undefined. Tag `samba`                   |
| Handler | Restart Samba services (root)                     | Restarts every service in `samba_services`                                                                                                                                                                                                                   |

## Variables

Defaults from `defaults/main.yml`:

| Variable                                                                                    | Default                              | Purpose                                                                                                                                                                                     |
| ------------------------------------------------------------------------------------------- | ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `samba_workgroup`                                                                           | `WORKGROUP`                          | `workgroup`                                                                                                                                                                                 |
| `samba_server_string`                                                                       | `Fileserver %m`                      | `server string`                                                                                                                                                                             |
| `samba_apple_extensions`                                                                    | `true`                               | Adds `fruit:aapl = yes` to `[global]`                                                                                                                                                       |
| `samba_security`                                                                            | `user`                               | `security`                                                                                                                                                                                  |
| `samba_passdb_backend`                                                                      | `tdbsam`                             | `passdb backend`                                                                                                                                                                            |
| `samba_map_to_guest`                                                                        | `Never`                              | `map to guest`                                                                                                                                                                              |
| `samba_wins_support`, `samba_local_master`, `samba_domain_master`, `samba_preferred_master` | `'yes'` each                         | `wins support`, `local master`, `domain master`, `preferred master`; rendered `yes` when truthy and `no` otherwise, so use a boolean `false`: the string `'no'` is truthy and renders `yes` |
| `samba_shares_root`                                                                         | `/srv/shares`                        | Parent of a share's path when the share sets no `path` (`<root>/<name>`)                                                                                                                    |
| `samba_shares`                                                                              | one `media` share (see below)        | Shares to define; the `[share]` sections are omitted when the list is empty                                                                                                                 |
| `samba_users`                                                                               | `ansible_user` with `admin_password` | Users added to Samba's password database                                                                                                                                                    |

Two more variables are read when set but have no default: `samba_netbios_name` (falls back to the host's `hostname`
fact) and `samba_mdns_name` (falls back to `netbios`).

`vars/main.yml` fixes `samba_configuration_dir` (`/etc/samba`), `samba_configuration` (`<dir>/smb.conf`), and
`samba_services` (`smbd`, `nmbd`).

The default `samba_shares` is a single share: `media`, `path: /storage`, `group` and `write_list` set to `ansible_user`.

## Shares

Each entry of `samba_shares` becomes a `[<name>]` section. Besides `name`, the template reads:

| Key                                                             | Rendered as                                                                                                                                                                    |
| --------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `path`                                                          | `path`; default `<samba_shares_root>/<name>`                                                                                                                                   |
| `public`                                                        | `public`; default `no`                                                                                                                                                         |
| `create_mode`, `force_create_mode`                              | `create mode`, `force create mode`; default `0664`                                                                                                                             |
| `directory_mode`, `force_directory_mode`                        | `directory mode`, `force directory mode`; default `0775`                                                                                                                       |
| `comment`, `valid_users`, `write_list`, `guest_ok`              | `comment`, `valid users`, `write list`, `guest ok`; only when set                                                                                                              |
| `group`, `user`                                                 | `force group`, `force user`; only when set                                                                                                                                     |
| `browsable`, `browseable`, `writable`, `writeable`, `read_only` | The same-named option (`read only` for `read_only`) through `ternary('yes', 'no')`; only when the key is truthy, so `false` emits nothing <!-- codespell:ignore browseable --> |
| `include_file`                                                  | `include = <samba_configuration_dir>/<basename of the value>`; only when set                                                                                                   |
| `vfs_objects`                                                   | `vfs objects = <names>` plus one `<name>:<option> = <value>` line per entry of `options`                                                                                       |

The `[global]` section also sets `logging = syslog`, turns printing off (`load printers = no`,
`printcap name = /dev/null`, `disable spoolss = yes`), and adds `nt pipe support = no` when the installed Samba version
is from 3.5.0 up to, but not including, 4.6.4 (the CVE-2017-7494 fix).

## Tags and running

```bash
python3 run.py nas-provision --tags samba          # the whole role
python3 run.py nas-provision --tags configfile     # step 3 (and step 2, tagged always) plus the docker role's configfile tasks
```

The playbook include carries the tags `samba` and `configfile`, and `apply` hands `samba` to every task in the role. A
tag on `include_role` selects only the include itself, so `--tags configfile` reaches just the tasks that carry it (plus
the `always`-tagged step 2). See [`docker`](../docker/README.md#tags-and-running) for the other tasks selected by that
tag.

## Known gap

No task creates the directory behind a share's `path`; `tasks/main.yml` has a `# TODO: create Samba share directories`
comment where such a task would go.
