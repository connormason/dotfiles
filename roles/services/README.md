[Project Root](../../README.md) > [Roles](../README.md) > **services**

# services

Puts the Compose services on the NAS and starts them. Runs last in `playbooks/nas_bootstrap.yml`.

| Task                                  | What it does                                                                                      |
| ------------------------------------- | ------------------------------------------------------------------------------------------------- |
| Sync compose files to the NAS         | `ansible.posix.synchronize` of `services/` to `~/docker/`, excluding `*.j2` and `.env`, no delete |
| Create per-service secret directories | Ensures `~/docker/<svc>/` exists for every `services/<svc>/env.j2` (tag `secrets`)                |
| Render per-service secret files       | Renders each `env.j2` to `~/docker/<svc>/.env`, mode `0600`, no diff output (tag `secrets`)       |
| Deploy all services                   | Runs `~/docker/deploy.sh all`; changed only when containers start, recreate, create, or pull      |

## Variables

| Variable              | Default                          | Purpose                                                   |
| --------------------- | -------------------------------- | --------------------------------------------------------- |
| `services_target_dir` | `~/docker` (the SSH user's home) | Must match `docker_dir` in the `docker` role              |
| `services_source_dir` | `{{ playbook_dir }}/../services` | The checkout's `services/` on the machine running Ansible |

## Usage

```bash
python3 run.py nas-provision --tags services          # sync, secrets, deploy
python3 run.py nas-provision --tags secrets           # rotate secrets only; then: run.py nas-deploy <svc>
```

A service that needs a secret ships `services/<svc>/env.j2` and sets `env_file: <svc>/.env` in its `compose.yml`
(relative to `~/docker`, because `deploy.sh` passes `--project-directory ~/docker`). Variables come from the vault.

The sync pushes the working tree of the machine running Ansible, as `run.py nas-deploy` does; a later CI deploy of
`main` supersedes a branch deploy for any service it changes.

Depends on the [`docker`](../docker/README.md) role (engine, `~/docker/`, `deploy.sh`).
