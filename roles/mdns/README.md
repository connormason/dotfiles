[Project Root](../../README.md) > [Roles](../README.md) > **mdns**

# mdns

Announces a `<name>.local` hostname for each NAS web UI over mDNS, so `http://jellyfin.local` resolves on the home
network without a port. Runs between the `samba` and `docker` roles in
[`playbooks/nas_bootstrap.yml`](../../playbooks/nas_bootstrap.yml).

## How it fits

A client resolving `jellyfin.local` asks the network over mDNS and gets the NAS's LAN address from Avahi. It then
connects to port 80, where the `caddy` container's `http://jellyfin.local` site proxies to `jellyfin:8096`. This role is
the first half. The second half is rendered by the [`tailscale`](../tailscale/README.md) role's `Caddyfile.j2` from the
same `local_services` list, so a new name needs one edit.

## Tasks

All of `tasks/main.yml`, in order. Every step except the two assertions runs with `become`.

| Step | Task                                        | Effect                                                                                             |
| ---- | ------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| 1    | Require at least one `local_services` entry | Fails on an empty list                                                                             |
| 2    | Require names that are plain DNS labels     | Fails on any name outside `[a-z0-9]` with inner hyphens (the names reach the unit's `ExecStart`)   |
| 3    | Install Avahi                               | `apt` install of `avahi-daemon` and `avahi-utils`                                                  |
| 4    | Configure Avahi                             | Renders `avahi-daemon.conf`: IPv4 only, announcing on `mdns_interface`; notifies the Avahi restart |
| 5    | Install the mDNS name publisher             | Copies `files/nas-mdns-publish` to `mdns_script_path` (mode `0755`)                                |
| 6    | Install the mDNS publisher unit             | Renders `nas-mdns-publish.service` with one name per `local_services` entry                        |
| 7    | Enable and start Avahi                      | Starts and enables `avahi-daemon`                                                                  |
| 8    | Enable and start the mDNS publisher         | Reloads systemd, then starts and enables `nas-mdns-publish.service`                                |

Handlers: `Restart Avahi` (after a config change) and `Restart the mDNS publisher` (after a script or unit change).

## Variables

| Variable           | Default                                                 | Purpose                                                |
| ------------------ | ------------------------------------------------------- | ------------------------------------------------------ |
| `local_services`   | play variable, from `playbooks/vars/local_services.yml` | List of `{name, port}`; the role publishes each `name` |
| `mdns_interface`   | the default-route interface (`br0` on the NAS)          | The only interface Avahi announces on                  |
| `mdns_avahi_conf`  | `/etc/avahi/avahi-daemon.conf`                          | Destination of the rendered Avahi configuration        |
| `mdns_script_path` | `/usr/local/bin/nas-mdns-publish`                       | Destination of the publisher script                    |
| `mdns_unit_path`   | `/etc/systemd/system/nas-mdns-publish.service`          | Destination of the unit file                           |

The default list is `playbooks/vars/local_services.yml`; set `local_services_override` in the inventory to replace it.

## The publisher

`nas-mdns-publish NAME...` runs one `avahi-publish -a -R <name>.local <address>` per name. The address is the one the
default route uses, read when the script starts, so a changed address needs `sudo systemctl restart nas-mdns-publish`,
not a re-provision. If any publisher exits (for example when `avahi-daemon` restarts), the script stops the rest and
exits 1, and systemd restarts the set.

## Checking it

```bash
systemctl status nas-mdns-publish
avahi-resolve -n jellyfin.local        # on the NAS: prints the NAS's address
dns-sd -G v4 jellyfin.local            # on a Mac on the same network
curl -sI http://jellyfin.local         # needs the caddy container from the tailscale role's Caddyfile
```
