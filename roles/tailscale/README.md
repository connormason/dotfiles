[Project Root](../../README.md) > [Roles](../README.md) > **tailscale**

# tailscale

Sets up [Tailscale VPN](https://tailscale.com/) on Debian systems.

<!-- mdformat-toc start --slug=github --maxlevel=3 --minlevel=2 -->

- [Features](#features)
- [Prerequisites](#prerequisites)
- [Required Variables](#required-variables)
- [Optional Variables](#optional-variables)
- [Service Routing](#service-routing)
- [Post-Deployment Steps](#post-deployment-steps)
- [Running](#running)
- [Cert Renewal](#cert-renewal)

<!-- mdformat-toc end -->

## Features<a name="features"></a>

- Installs Tailscale from official apt repository
- Configures Tailscale with idempotent `tailscale set` + `tailscale login`
- Enables Tailscale SSH on Linux hosts (`tailscale_ssh_enabled`; the NAS sets it to `false` so the CI deploy can use
  regular SSH, see [`services/README.md`](../../services/README.md#ci-deploys))
- Provisions HTTPS certificates via `tailscale cert` (NAS only)
- Renders the Caddyfile at `/etc/caddy/Caddyfile` (NAS only); the Caddy container itself is defined by
  [`services/caddy/compose.yml`](../../services/caddy/compose.yml) and deployed by the
  [`services`](../services/README.md) role or `python3 run.py nas-deploy caddy`
- Automatic weekly cert renewal via systemd timer

## Prerequisites<a name="prerequisites"></a>

1. **Tailscale account** with a tailnet configured
2. **Reusable auth key** generated in [Tailscale admin console](https://login.tailscale.com/admin/settings/keys)
   - Note: Reusable auth keys expire after ~90 days and must be regenerated
3. **HTTPS certificates enabled** in Tailscale admin console (for HTTPS feature)

## Required Variables<a name="required-variables"></a>

Set these in your Ansible Vault (`inventory/group_vars/all/vault.yml`):

```yaml
tailscale_auth_key: tskey-auth-...
tailscale_tailnet_name: tail1234.ts.net
```

`tailscale_tailnet_name` holds the full domain, including `.ts.net`. URLs in this document write it as
`nas.<tailnet>.ts.net`, where `<tailnet>` is the label before `.ts.net` (`tail1234` here).

## Optional Variables<a name="optional-variables"></a>

See `defaults/main.yml` for all available variables and their defaults.

Example overrides for the NAS (the inventory is a separate repository, not part of this checkout):

```yaml
tailscale_https_enabled: true
tailscale_services:
  - {name: sonarr, port: 8989, path: sonarr}
  - {name: radarr, port: 7878, path: radarr}
  - {name: transmission, port: 9091, path: transmission}
  - {name: prowlarr, port: 9696, path: prowlarr}
  - {name: pihole, port: 80, path: pihole}   # skipped by the Caddyfile template (see Service Routing)
  - {name: glance, port: 8080, path: glance, strip_prefix: true}
  - {name: plex, port: 32400, dedicated_port: 32443}
```

## Service Routing<a name="service-routing"></a>

The role writes the Caddyfile to `/etc/caddy/Caddyfile` (`tailscale_caddy_config_dir`) and the certificates to
`/etc/tailscale/certs` (`tailscale_cert_dir`). The `caddy` container is defined by `services/caddy/compose.yml`, not by
this role; that file names both host paths literally and mounts them read-only.

Services are accessible via `https://nas.<tailnet>.ts.net/<path>`:

| Service      | URL                       | Notes                                                                                      |
| ------------ | ------------------------- | ------------------------------------------------------------------------------------------ |
| Sonarr       | `/sonarr`                 | Requires `UrlBase = /sonarr` in app settings                                               |
| Radarr       | `/radarr`                 | Requires `UrlBase = /radarr` in app settings                                               |
| Prowlarr     | `/prowlarr`               | Requires `UrlBase = /prowlarr` in app settings                                             |
| Transmission | `/transmission`           | Requires `rpc-url = /transmission/` in settings.json                                       |
| PiHole       | `/pihole`                 | Rewrites to `/admin`; not deployed by this repository while PiHole is disabled (see below) |
| Glance       | `/glance`                 | Caddy strips the prefix before proxying (`strip_prefix: true`)                             |
| Plex         | `:32443` (dedicated port) | Access via `https://nas.<tailnet>.ts.net:32443`                                            |

The Caddyfile template skips any `pihole` entry of `tailscale_services` in its loop and always emits its own `/pihole`
route (prefix stripped, rewritten to `/admin`, proxied to `pihole:80`). The `pihole` entry above therefore has no
effect, and the route has no container behind it while PiHole is disabled (`services/pihole/compose.yml.disabled`).

## Post-Deployment Steps<a name="post-deployment-steps"></a>

After first playbook run:

1. Set URL base paths in each service's web UI (see table above)
2. Check that the `caddy` container is running. A full `nas-provision` deploys it, because the `services` role runs
   after this one. After a run limited to `--tags tailscale` on a host that has no Caddy container yet, deploy it with
   `python3 run.py nas-deploy caddy` (it syncs first), or `~/docker/deploy.sh caddy` on the NAS once an earlier sync has
   put `~/docker/caddy/compose.yml` there
3. Verify access from a device on your tailnet

Plex's `ADVERTISE_IP` needs no manual step: the `docker` role renders `~/docker/.env` with
`ADVERTISE_IP=https://<host>.<tailnet>.ts.net:32443` from `tailscale_tailnet_name` (see
[`roles/docker/README.md`](../docker/README.md#what-it-installs)).

## Running<a name="running"></a>

```bash
# Full NAS bootstrap
./nas_bootstrap.sh

# Tailscale only
ansible-playbook playbooks/nas_bootstrap.yml -i inventory/inventory.yml -vv --tags tailscale
```

## Cert Renewal<a name="cert-renewal"></a>

The playbook issues the certificate once (the `tailscale cert` task is skipped while the `.crt` file exists). After
that, certs are renewed weekly by a systemd timer (`OnCalendar=weekly`, with up to an hour of random delay). The service
it starts runs `tailscale cert` for the same files, then reloads Caddy with
`docker exec caddy caddy reload --config /etc/caddy/Caddyfile`. To check status:

```bash
# Timer status
systemctl status tailscale-cert-renewal.timer

# Last renewal run
journalctl -u tailscale-cert-renewal.service --no-pager -n 20

# Manual renewal
sudo systemctl start tailscale-cert-renewal.service
```
