[Project Root](../../README.md) > [Roles](../README.md) > **services**

# services

Puts the Compose services on the NAS and starts them: syncs the repository's `services/` tree to `~/docker`, renders the
per-service secret files, and runs `deploy.sh all`. Runs last in `playbooks/nas_bootstrap.yml`, after the
[`docker`](../docker/README.md) role has installed the engine and `deploy.sh`.

## Tasks

All of `tasks/main.yml`, in order.

| Task                                  | What it does                                                                                                                                                                                                         |
| ------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Install rsync                         | `apt` install on the NAS (`synchronize` runs rsync on both ends; a minimal Debian ships without it)                                                                                                                  |
| Sync compose files to the NAS         | `ansible.posix.synchronize` of `services/` to `~/docker/`, excluding `*.j2`, `.env`, `.backups/` and `.DS_Store`; no delete, directory times not copied                                                              |
| Find per-service secret templates     | `find` for `env.j2` (`depth: 2`) in the checkout's `services/`, on the machine running Ansible (`delegate_to: localhost`, `connection: local`); `check_mode: false`, so it also runs under `--check` (tag `secrets`) |
| Create per-service secret directories | Ensures `~/docker/<svc>/` exists for every template found, but only for a service that has a `compose.yml` (tag `secrets`)                                                                                           |
| Render per-service secret files       | Renders each such `env.j2` to `~/docker/<svc>/.env`, mode `0600`, no diff output; same `compose.yml` condition (tag `secrets`)                                                                                       |
| Deploy all services                   | Runs `~/docker/deploy.sh all` as the SSH user, async (3600 s, polled every 15 s); changed only when containers start, recreate, create, or pull; skipped under `--check`                                             |

## Variables

| Variable              | Default                          | Purpose                                                   |
| --------------------- | -------------------------------- | --------------------------------------------------------- |
| `services_target_dir` | `~/docker` (the SSH user's home) | Must match `docker_dir` in the `docker` role              |
| `services_source_dir` | `{{ playbook_dir }}/../services` | The checkout's `services/` on the machine running Ansible |

## Per-service secrets

A service that needs a secret ships `services/<svc>/env.j2` and sets `env_file: <svc>/.env` in its `compose.yml`
(relative to `~/docker`, because `deploy.sh` passes `--project-directory ~/docker`). The template's variables come from
the inventory.

The directory and render tasks run only for a service whose `compose.yml` exists in the checkout. A disabled service
(`compose.yml.disabled`) has no consumer for its secret, and its variable may be undefined, so it is skipped.
`services/pihole/env.j2` (variable `pihole_web_password`) is the only template today and PiHole is disabled, so nothing
is rendered and `pihole_web_password` is not needed; re-enabling PiHole makes it required. See
[Secrets](../../services/README.md#secrets) for the rest of the secret flow.

## Tags and running

```bash
python3 run.py nas-provision --tags services          # the whole role: sync, secrets, deploy
python3 run.py nas-provision --tags secrets           # rotate secrets only; then: run.py nas-deploy <svc>
```

The playbook include carries the tags `services` and `secrets`, and `apply` hands `services` to every task in the role.
A tag on `include_role` selects only the include itself, so `--tags secrets` reaches just the three tasks that carry it:
the discovery, directory, and render tasks. The sync and the deploy do not run.

Under `--check` the discovery task still runs and the deploy is skipped.

The sync pushes the working tree of the machine running Ansible, as `run.py nas-deploy` does; a later CI deploy of
`main` supersedes a branch deploy for any service it changes.

## Related

- [`services/README.md`](../../services/README.md): the Compose definitions, secrets, and deploy routes
- [`roles/docker/README.md`](../docker/README.md): the engine, `~/docker`, and `deploy.sh` this role depends on
