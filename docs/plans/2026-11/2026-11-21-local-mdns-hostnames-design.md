# Per-Service `.local` Hostnames — Design

## Problem

`homeassistant.local` works on the home network because HAOS announces its own name over mDNS. Every other NAS service
with a web UI is reachable only as `http://nas.local:<port>` (`services/README.md:88`), which means remembering a port
per service. The goal is `http://jellyfin.local`, `http://sonarr.local`, and so on, with no port and no per-device setup.

## Decision

Two pieces, both on the NAS:

1. **Avahi publishes one mDNS address record per service name**, each pointing at the NAS's LAN IPv4 address.
2. **Caddy gets a plain-HTTP `:80` site** that routes by `Host` header to the right container on `nas-network`.

A client resolving `jellyfin.local` gets the NAS's address by mDNS, connects to port 80, and Caddy forwards to
`jellyfin:8096`.

Approaches considered:

| Approach                                              | Verdict                                                                                                      |
| ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| **Avahi aliases on the host + host-routed Caddy**     | **Chosen:** no router changes, no new container, reuses the Caddy already deployed.                          |
| Local DNS server (Pi-hole, dnsmasq)                   | Rejected: needs router DHCP changes, and `.local` is reserved for mDNS so some clients skip unicast DNS.     |
| mDNS responder container (host network)               | Rejected: more moving parts than Avahi on the host, with nothing gained.                                     |
| HTTPS with Caddy's internal CA                        | Rejected by the user: every device must trust the root cert, and several clients (TVs, apps) reject it.      |

Transport is **plain HTTP**. Traffic stays on the home LAN; the existing Tailscale HTTPS routes remain the encrypted
option for remote access.

## Components

### `mdns` role (new)

Runs in `playbooks/nas_bootstrap.yml` after `samba` and before `docker`, tagged `mdns`.

- Installs `avahi-daemon` and renders `/etc/avahi/avahi-daemon.conf` with `use-ipv6=no` and `allow-interfaces` set to the
  default-route interface (`br0` on this host, since the HAOS bridge takes over the NIC), so names are not announced on
  Docker bridges.
- Installs a small script and a systemd unit that run one `avahi-publish -a -R <name>.local <ip>` per entry in
  `local_services`. The IP is resolved when the unit starts (not baked in at render time), so a DHCP-reserved address
  change needs only a unit restart, not a re-provision.
- Does not publish `homeassistant.local`: HAOS announces it itself.

### Caddy `:80` site

- `services/caddy/compose.yml` publishes `80:80`.
- `roles/tailscale/templates/Caddyfile.j2` gains one `http://<name>.local` site per `local_services` entry, each with
  `reverse_proxy <name>:<port>`. An explicit `http://` site address means Caddy does not redirect it to HTTPS, so no
  global option is needed.
- The existing `https://` blocks are untouched.

### `local_services`

One list of `{name, port}` dicts, the same shape as `tailscale_services`; the container name equals `name`.

| name         | port |
| ------------ | ---- |
| glance       | 8080 |
| plex         | 32400 |
| jellyfin     | 8096 |
| sonarr       | 8989 |
| radarr       | 7878 |
| prowlarr     | 9696 |
| transmission | 9091 |

Both the `mdns` role and the `tailscale` role's Caddyfile need the list, and either role may run alone under `--tags`.
So the default lives in `playbooks/vars/local_services.yml`, loaded by `vars_files`, and the playbook defines
`local_services: "{{ local_services_override | default(local_services_default) }}"`. Inventory overrides by setting
`local_services_override`. `dotfiles_repo_dir` already sets the precedent for play-level variables in the playbook.

## Out of scope

- **`homeassistant.local`:** untouched.
- **ntfy:** loopback-only (`127.0.0.1:2586`), stays that way.
- **flaresolverr, autoplex:** no web UI.
- **`nas.local:<port>`:** keeps working; nothing is removed.
- **Moving the Caddyfile out of the `tailscale` role:** a larger refactor than this feature needs.

## Constraints and known behavior

- **Tailscale coupling.** The Caddyfile is rendered only when `tailscale_https_enabled` is true
  (`roles/tailscale/tasks/main.yml:19`), so `.local` routing is available only while that role's HTTPS setup is on.
  Names would still be announced without it, but would reach nothing on port 80.
- **UrlBase redirects.** Sonarr, Radarr, Prowlarr and Transmission are configured with a URL prefix for the Tailscale
  path routes. Requests to `sonarr.local/` are expected to redirect to `sonarr.local/sonarr`, and Transmission to
  `/transmission/web/`. The names work; the address bar shows the prefix. To be confirmed during verification.
- **Transmission host check.** Transmission can reject hostnames missing from its RPC host whitelist. Caddy passes the
  original `Host` header through, which is what Plex and Jellyfin need for correct absolute URLs, so no rewrite is
  applied globally. If `transmission.local` returns an error, the fix is on the Transmission side
  (`HOST_WHITELIST`), not a Caddy `Host` rewrite.
- **Client support.** `.local` resolves through mDNS: macOS, iOS, and Windows 10+ do it natively; Linux needs
  `nss-mdns`. A client without mDNS can still use `nas.local:<port>` or the IP.
- **Port 80.** Pi-hole is disabled (its UI is on 8053), so nothing else in the repo uses host port 80. Verify with
  `ss -ltn 'sport = :80'` before deploying.
- **Existing `nas.local`.** `services/README.md:88` assumes it resolves, but no role in this repository installs Avahi.
  Whether something on the host already announces it is unverified; installing `avahi-daemon` is expected to be
  harmless either way.

## Testing

- Unit tests render the Caddyfile and the Avahi script/unit from a sample `local_services` and assert on the output,
  following the existing tests under `tests/unit/`.
- `tests/unit/bootstrap/nas/test_nas_playbook.py` is extended so the `mdns` role's tag passes `TestPlaybookTags`.
- `caddy validate` against the rendered file, run from the `caddy:2-alpine` image.
- On the NAS after rollout: `avahi-resolve -n jellyfin.local`, then `curl -sI http://jellyfin.local`, repeated per name;
  from a second device on the LAN, open each name in a browser.

## Rollout (owner-run)

`run.py nas-provision --tags mdns,tailscale`, then `run.py nas-deploy` to republish Caddy with port 80. Both touch the
live NAS and are run by the owner.

## Documentation

New `roles/mdns/README.md`; updates to `roles/README.md`, `roles/tailscale/README.md`, `services/README.md` (Caddy
ports, LAN access section), and `.ctx/ARCHITECTURE.md` (role list and Docker stack).
