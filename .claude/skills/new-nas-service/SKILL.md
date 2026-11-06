---
name: new-nas-service
description: Scaffold and wire a new Docker Compose service for the home NAS stack (services/<name>/compose.yml, optional env.j2 secret template, services/README.md rows, docs-consistency tests). Use when adding, enabling, or disabling a NAS service.
disable-model-invocation: true
argument-hint: <service-name> [image]
---

# New NAS Service

Adds one service to the NAS Compose stack under `services/` and keeps every hand-maintained inventory that mentions it
in sync. The procedure mirrors "Adding a Compose Service (NAS)" in `.ctx/CONVENTIONS.md`; the guardrails are
`tests/unit/test_docs_consistency.py::TestServicesReadme` and `tests/unit/services/`.

`$ARGUMENTS` is the service name, optionally followed by the image. Ask for whatever is missing (image, published ports,
volumes, whether it needs a secret) before writing files.

## Hard rules

- **Never deploy.** `python3 run.py nas-deploy <name>` (without `--dry-run`) and a push to `main` both change the live
  NAS. Run only `--dry-run` and tell the user the real deploy command; they run it.
- **Never edit `inventory/`.** It is a separate, gitignored repo holding the vault-encrypted host variables (a
  `PreToolUse` hook blocks edits). Anything needed there (`tailscale_services` entry, secret variable) goes in the final
  report as a manual step.
- Run Python through `uv run` only; never run `ruff format`.

## Procedure

1. **Validate the name.** It must match `^[a-z0-9][a-z0-9_-]*$` (enforced by `scripts/nas/deploy-services.sh`) and no
   `services/<name>/` may exist yet. The directory name **must equal the service key** inside the compose file, because
   `deploy.sh` runs `docker compose ... up -d <name>`.

2. **Read two neighbours first** to match house style: `services/sonarr/compose.yml` (LinuxServer.io app with a media
   mount) and `services/caddy/compose.yml` (non-LinuxServer image with a named volume). Conventions seen there:

   - `---` document start, then a top-level `services:` mapping holding exactly one service.
   - `container_name` equals the service key; `restart: unless-stopped`.
   - LinuxServer.io images set `PUID=1000` and `PGID=1000`, and keep config at `/storage/media/config/<name>:/config`.
   - Ports are quoted `"host:container"` strings. Media trees mount from `/storage/media/{tv,movies,music,downloads}`.
   - Relative paths and `env_file` resolve against `--project-directory ~/docker` on the NAS, not the service folder.
   - Networking comes from `services/compose.base.yml` (`nas-stack` project, `nas-network` bridge); do not redeclare it.

3. **Create `services/<name>/compose.yml`.** Check the chosen host ports against the Quick Reference table in
   `services/README.md` so nothing collides.

4. **If the service needs a secret**, also create `services/<name>/env.j2` and add `env_file: <name>/.env` to the
   compose service. The `services` role renders it to `~/docker/<name>/.env` (mode `0600`) from inventory variables.
   Look at `services/pihole/env.j2` for the template shape, and follow `tests/unit/services/test_service_secrets.py`
   when adding a rendering test for the new template. Never write a real secret value into any tracked file.

5. **Document it in `services/README.md`**:

   - A row in the Quick Reference table. Columns: container name in backticks, image, host ports, purpose. The container
     name is `container_name` (falling back to the service key). Append `(**disabled**)` to the purpose only when the
     file is `compose.yml.disabled`.
   - A per-service section under "Services": an H3 whose title is the service name in backticks, followed by the
     `<a name="...">` anchor the neighbouring headings carry. Match its neighbours, and add its entry to the
     mdformat-toc block.
   - Rows in the Storage layout table when it mounts under `/storage/media`.
   - If it needs a Caddy route, note in the Tailscale / HTTPS table that the `tailscale_services` inventory entry is
     required.

6. **Disabling instead of adding.** Rename `compose.yml` to `compose.yml.disabled` and add `(**disabled**)` to the
   README row. Repository changes stop nothing on the NAS; the NAS copy must be removed by hand (see the "disabled"
   paragraphs in `services/README.md`).

7. **Verify** (all must pass before reporting done):

   ```bash
   uv run pytest tests/unit/test_docs_consistency.py tests/unit/services tests/unit/deploy -q
   uv run python run.py run-hooks --files services/<name>/compose.yml services/README.md
   uv run python run.py nas-deploy <name> --dry-run
   ```

   Confirm the dry run exits cleanly, but treat a failure caused only by the NAS being unreachable as informational.

8. **Report**: files created or changed, the manual inventory steps (`tailscale_services` entry for a Caddy route, vault
   variable for a secret), and the exact deploy command for the user to run. Mention that merging to `main` triggers
   `.github/workflows/deploy.yml` for that service directory.
