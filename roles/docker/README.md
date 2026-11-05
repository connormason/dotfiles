[Project Root](../../README.md) > [Roles](../README.md) > **docker**

# docker

Installs Docker Engine from Docker's apt repository on the NAS, prepares the `~/docker` stack directory, builds the
image the stack runs from a local build (`danielmmetz/autoplex`), and installs `deploy.sh`. It does not sync compose
files, render per-service secrets, or start containers: the [`services`](../services/README.md) role does that and runs
last in `playbooks/nas_bootstrap.yml`.

<!-- mdformat-toc start --slug=github --maxlevel=3 --minlevel=2 -->

- [Tasks](#tasks)
- [What it installs](#what-it-installs)
- [Variables](#variables)
- [Tags and running](#tags-and-running)
- [Autoplex image](#autoplex-image)
- [Contract with the services role](#contract-with-the-services-role)
- [Related](#related)

<!-- mdformat-toc end -->

## Tasks<a name="tasks"></a>

All of `tasks/main.yml`, in order. Steps marked root run with `become`; the others run as the SSH user.

| Step | Module                                 | Effect                                                                                                                                           |
| ---- | -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1    | `apt` (root)                           | Installs `ca-certificates`, `curl`, `gnupg`                                                                                                      |
| 2    | `get_url` (root)                       | Downloads Docker's signing key to `/usr/share/keyrings/docker.asc`                                                                               |
| 3    | `command`                              | `dpkg --print-architecture`; never reports changed and also runs under `--check`                                                                 |
| 4    | `apt_repository` (root)                | Adds the Docker apt source; the module refreshes the package index itself                                                                        |
| 5    | `apt` (root)                           | Installs `docker-ce`, `docker-ce-cli`, `containerd.io`, `docker-buildx-plugin`, `docker-compose-plugin`, and the legacy `docker-compose` package |
| 6    | `service` (root)                       | Starts `docker`                                                                                                                                  |
| 7    | `user` (root)                          | Appends the SSH user (`ansible_facts['user_id']`) to the `docker` group                                                                          |
| 8    | `file`                                 | Creates `~/docker` and `~/docker/.build` (0755, enforced on every run)                                                                           |
| 9    | `stat`, `file`                         | Creates `~/docker/pihole-data/etc-pihole` (0755) only when it is absent, along with the missing parent `~/docker/pihole-data` (default mode)     |
| 10   | `template`                             | Renders `~/docker/.env` from `templates/env.j2` (tag `configfile`)                                                                               |
| 11   | `git`                                  | Clones or updates autoplex (see [Autoplex image](#autoplex-image))                                                                               |
| 12   | `community.docker.docker_image` (root) | Builds `danielmmetz/autoplex:latest` from that clone                                                                                             |
| 13   | `copy`                                 | Installs `files/deploy.sh` as `~/docker/deploy.sh` (tag `configfile`)                                                                            |

Step 9 is guarded because PiHole re-owns that bind mount once it runs: enforcing a mode afterwards would report changed
(or fail) on every run. The directory is created even though PiHole's compose file is currently `compose.yml.disabled`.
The Docker apt source in step 4 is keyed to the host's `distribution` and `distribution_release` facts and the
architecture from step 3.

## What it installs<a name="what-it-installs"></a>

| Path or object                    | Mode                    | Source                                                                                                     |
| --------------------------------- | ----------------------- | ---------------------------------------------------------------------------------------------------------- |
| `/usr/share/keyrings/docker.asc`  | `0644`, root            | `https://download.docker.com/linux/<distribution>/gpg`                                                     |
| `docker` group membership         |                         | The SSH user, appended                                                                                     |
| `~/docker`, `~/docker/.build`     | `0755`, enforced        | `file` loop                                                                                                |
| `~/docker/pihole-data/etc-pihole` | `0755` at creation only | `file`, when `stat` finds it absent; also creates the missing parent `~/docker/pihole-data` (default mode) |
| `~/docker/.env`                   | `0600`                  | `templates/env.j2`                                                                                         |
| `~/docker/.build/autoplex`        | git clone               | `docker_autoplex_repo_url`                                                                                 |
| Image `danielmmetz/autoplex`      | tag `latest`            | Built from the clone                                                                                       |
| `~/docker/deploy.sh`              | `0755`                  | `files/deploy.sh`                                                                                          |

`~/docker/.env` holds only `ADVERTISE_IP=https://<host>.<tailnet>.ts.net:32443` (`<tailnet>` is the part of
`tailscale_tailnet_name` before `.ts.net`), which `services/plex/compose.yml` passes to Plex through a bare
`ADVERTISE_IP` entry in `environment`. Per-service secrets are the `services` role's job. The render sets `diff: false`
because a host that predates that split still holds a password line in the old file, which `--check --diff` would print
as removed.

## Variables<a name="variables"></a>

| Variable                      | Default                                       | Purpose                                                                                         |
| ----------------------------- | --------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| `docker_dir`                  | `~/docker` (the SSH user's home)              | Stack root; must match `services_target_dir` (see [Contract](#contract-with-the-services-role)) |
| `docker_autoplex_repo_dest`   | `{{ docker_dir }}/.build/autoplex`            | Clone path                                                                                      |
| `docker_autoplex_repo_url`    | `https://github.com/danielmmetz/autoplex.git` | Upstream repository                                                                             |
| `docker_autoplex_repo_branch` | `master`                                      | Branch to check out                                                                             |
| `tailscale_tailnet_name`      | none; set in the inventory                    | Required by `env.j2`, e.g. `tail1234.ts.net`                                                    |
| `tailscale_hostname`          | none; falls back to `inventory_hostname`      | Optional host label in `ADVERTISE_IP`                                                           |

Every default is prefixed `docker_` (pinned by `tests/unit/test_services_role.py`). The `tailscale_*` pair are inputs
from the inventory: the [`tailscale`](../tailscale/README.md) role declares defaults for both but runs after this role,
so those defaults are not loaded here. The port `32443` is written into `env.j2` and is the port published by
`services/caddy/compose.yml`. The `tailscale` role's `tailscale_plex_port` (default `32443`) is otherwise unused: the
Caddy listener comes from the `dedicated_port` entry of `tailscale_services` (`roles/tailscale/templates/Caddyfile.j2`),
so changing that variable changes nothing.

## Tags and running<a name="tags-and-running"></a>

```bash
python3 run.py nas-provision --tags docker          # the whole role
python3 run.py nas-provision --tags configfile      # the docker role's .env render and deploy.sh copy (plus samba's smb.conf)
```

The playbook include carries the tags `docker` and `configfile`, and `apply` hands `docker` to every task in the role. A
tag on `include_role` selects only the include itself, so `--tags configfile` reaches just the two tasks that carry it
(steps 10 and 13); the `samba` include shares the tag, so its one `configfile` task runs too. The `always`-tagged
playbook tasks (become password, apt index refresh) run either way.

`--tags configfile` assumes `~/docker` exists, because the directory tasks do not carry the tag. On a host without it,
the run fails (at the `.env` render, with `Destination directory ... does not exist`, once samba is installed); run
`--tags docker` first. `tests/unit/test_services_role.py::TestTagSelection` exercises the tag selection against a
pre-created directory.

## Autoplex image<a name="autoplex-image"></a>

The clone lives at `docker_autoplex_repo_dest` (`~/docker/.build/autoplex`), on `docker_autoplex_repo_branch`
(`master`). The `git` task sets `update: true`, so it fetches on every run and reports changed whenever upstream moves.

The image is built only when it is missing. The build task sets `source: build` and no `force_source`, and the module
default (`force_source: false`) skips an existing `danielmmetz/autoplex:latest`. A moved clone therefore does not
refresh the image; rebuilding requires removing the image first. `services/autoplex/compose.yml` only names the image,
so the build here is what supplies it; the playbook runs `docker` before `services`.

## Contract with the services role<a name="contract-with-the-services-role"></a>

- **Directory.** `docker_dir` must equal `services_target_dir`; `test_target_dir_matches_the_docker_role` pins it.
  `deploy.sh` hard-codes `${HOME}/docker`, so overriding `docker_dir` would move the files but not where the script
  looks.
- **Docker group.** Membership (step 7) lets the `services` role run `deploy.sh` through `become` as the same user. That
  starts a fresh login, so the new group applies on the very first run.
- **`deploy.sh [<svc> ...|all]`.** With no argument or `all`, it discovers `~/docker/*/compose.yml`. For each service it
  runs `docker compose --project-directory ~/docker -f compose.base.yml -f <svc>/compose.yml up -d <svc>`, with
  `COMPOSE_IGNORE_ORPHANS=true` because every service is a separate file in one project. A failed service does not stop
  the rest; the script exits 1 at the end. It also exits 1 at once if `~/docker/compose.base.yml` is missing, and this
  role does not install that file: it arrives with the `services` sync, so `deploy.sh` works only after that sync.
- **`.env`.** The sync excludes `.env` and never deletes, so it leaves the file rendered here alone.

Not done by this role: syncing compose files, rendering per-service secrets, and starting services (the `services`
role); the Caddy configuration and TLS certificates (the `tailscale` role); the Home Assistant OS VM, including its
`docker.service` drop-in ([`vms/haos`](../../vms/haos/README.md)); and `/etc/docker/daemon.json`, which no task writes.

## Related<a name="related"></a>

- [`services/README.md`](../../services/README.md): the Compose definitions, ports, secrets, and deploy routes
- [`roles/services/README.md`](../services/README.md): sync, per-service secrets, and the `deploy.sh all` run
- [`roles/tailscale/README.md`](../tailscale/README.md): Tailscale certificates and the Caddy configuration
- [`vms/haos/README.md`](../../vms/haos/README.md): the Home Assistant OS VM
