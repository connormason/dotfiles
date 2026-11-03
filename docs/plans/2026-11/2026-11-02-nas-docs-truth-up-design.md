# NAS Sub-project 4: Docs Truth-up and Hardening (PR A)

**Date:** 2026-11-02
**Status:** Approved (design); implementation plan pending
**Parent design:** [`2026-10-31-nas-provisioning-design.md`](../2026-10/2026-10-31-nas-provisioning-design.md)
(sub-project 4); follows [`2026-11-02-nas-laptop-deploy-design.md`](2026-11-02-nas-laptop-deploy-design.md)
**Goal:** Make every NAS-related document describe the repository as it is after sub-projects 1-3, close the small code
follow-ups deferred from PR #37, and add guardrails so the same drift is caught by tests next time.

## Context

Sub-projects 1-3 (PRs #27, #36, #37) moved the NAS from a single-compose Ansible stack to: the stow engine owning
`$HOME` (`dotfiles` role), a HAOS VM (`haos` role), per-service Compose definitions under `services/`, and one deploy
script (`scripts/nas/deploy-services.sh`) shared by CI and `run.py nas-deploy`. PR #37 corrected the docs its own
changes made false, so the docs are now a mixture: some files are accurate, a few are badly stale, and several carry a
handful of wrong claims.

Four read-only audits compared the docs with the code on 2026-11-02 (root README / `CLAUDE.md` / docs index; `.ctx/`,
`playbooks/`, `roles/`; `services/` and the `docker` role; the code follow-ups). Findings that shape this design:

- **Smaller than the known-stale list:** `.ctx/ARCHITECTURE.md`, `playbooks/README.md`, and `roles/README.md` are mostly
  correct after PR #37 and need targeted fixes, not rewrites. `docs/README.md` and `scripts/nas/README.md` are accurate.
- **Larger than the known-stale list:**
  - The root `README.md` has 21 discrepancies: retired roles (`git`, `ssh`, `zsh`) in the project tree, `--tags docker`
    advice for the stack, `update-inventory --force` described as a re-clone, PiHole shown as running, and the NAS framed
    as independent of the stow engine.
  - `CLAUDE.md` and `vms/README.md` both say the HAOS VM is outside Ansible; the `haos` role runs `vms/haos/setup.sh`
    (only `bridge.sh` is hand-run).
  - `docs/RUN_PY_REFERENCE.md` omits five registered commands and keeps a "Future Enhancements" section whose items all
    exist now.
  - `roles/tailscale/README.md` has stale steps; `roles/samba/README.md` is a three-line stub; `.ctx/BUILD.md` and
    `.ctx/CONVENTIONS.md` have gaps (leak-guard hooks, the `if OS.mac?` / `.dotfiles-os` rules, how to add a role or a
    Compose service).
- **`configfile` is broader than "inert on `services`".** The tag sits on every `include_role`, but `apply:` hands only
  the role-name tag to inner tasks, so a tag on the include selects the include and nothing inside it. Only three tasks
  carry `configfile` (docker `.env` render, docker `deploy.sh` copy, samba `smb.conf`). `playbooks/README.md` claims
  `--tags configfile` runs the whole stow engine and `setup.sh`, which would be false. The `homeassistant` tag on the
  `docker` include selects nothing at all.
- **Premise corrections:** `nas_bootstrap.sh` execs `scripts/hooks/uv-public.sh run python run.py`, not `uv run`; the
  NAS is Debian 12 (bookworm), not 13 (a test fixture says 13); the non-dict branch of `resolve_nas_target` is partly
  covered (an unparseable-output test exists), so the gap is valid-JSON-but-not-an-object only.

## Goals and non-goals

Goals:

1. Every claim in the in-scope docs is true of the code at merge time (verified by fresh audit agents, not by the
   author).
2. The code follow-ups in [Workstream 1](#workstream-1-code-follow-ups) land, each with a test that fails before the
   change.
3. Drift between docs and infrastructure inventories (services, role order, `run.py` commands) is caught by
   `test_docs_consistency.py`.
4. Lessons from sub-project 3 and this work are recorded in `CLAUDE-LESSONS.md`.

Non-goals:

- The `apt_repository` to `deb822_repository` migration (PR B; see [Deferred](#deferred)).
- Removing the legacy apt `docker-compose` package (only if the owner asks).
- Editing `run.py` (including its stale module docstring): a locked sibling worktree (`run-py-command-classes`) may be
  refactoring it.
- Re-enabling PiHole, or changing the dead `/pihole` route in `roles/tailscale/templates/Caddyfile.j2`.
- Editing the private inventory repo.

## Decisions

| #  | Decision                                                                                             | Rationale / alternatives rejected                                                                                                                                                                                                  |
| -- | ---------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| F1 | **Two PRs: this one (docs + low-risk hardening), then `deb822_repository` separately**               | The apt migration changes apt state on the box serving Plex and needs an owner-run Debian verification; it must not hold the docs hostage. Rejected: one PR (a NAS-side surprise blocks everything); three PRs (the docs describe tag semantics the hardening changes, so the first two must land in order anyway). |
| F2 | **Code before docs inside the branch**                                                               | The docs describe final tag semantics, role behavior, and script behavior; writing them first guarantees a second pass.                                                                                                              |
| F3 | **Drop `configfile` from the six includes with no `configfile` task; drop the dead `homeassistant` tag** | Behavior-neutral cleanup that makes the documented meaning of `--tags configfile` true (docker `.env`, docker `deploy.sh`, samba `smb.conf`). The alternative (tag the services sync/secret tasks) changes a documented command and needs `rsync` install tagged too. |
| F4 | **Docs keep `python3 run.py`; one "Running run.py" note** (README Quick Start, mirrored in `.ctx/BUILD.md`) | `run.py` is stdlib-only except `list-hosts` (PyYAML) and the NAS commands shell out through uv themselves. Rewriting ~60 examples to the uv wrapper adds noise for one real exception.                                            |
| F5 | **Operational knowledge from the old docker README moves into `services/README.md`**                 | Data flow, `/storage/media` layout, backup order, and the "compose never pulls `:latest`" caveat describe the stack, not the engine role. A separate runbook doc was considered; one home for stack facts is simpler.            |
| F6 | **`roles/services` skips `env.j2` for services without a `compose.yml`**                             | A disabled service's secret has no consumer, and an undefined vault var for it fails the whole play. Requiring the var instead was rejected (it ties provisioning to a service nobody runs).                                      |
| F7 | **Three drift guards, no more**                                                                      | Services table vs compose files, playbook role order vs docs, `run.py` commands vs `RUN_PY_REFERENCE.md`. Each is a cheap parse of data already structured; broader prose-checking tests would be brittle.                         |
| F8 | **Unverifiable claims are dropped from docs and reported to the owner as questions**                 | Per `readme-guidelines.md`, the code cannot answer them (e.g. whether the NAS has Docker log rotation configured, the `incomplete/` download directory, image-default ports 8123 and 8191).                                      |

## Workstream 1: code follow-ups

Each item is test-first (the new test is run against the old code and must fail for the stated reason) and verified by a
real run where one is possible. Lesson from sub-project 3: tests that string-match Ansible YAML did not catch two real
bugs, so role changes are exercised through the existing localhost `ansible-playbook` harness
(`tests/unit/test_services_role.py::TestSecretsRender`).

| #  | Change                                                                                                                                                                                                                                                                                                                                                                        | Files                                                                                       |
| -- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| W1 | **`configfile`:** prove the tag semantics with a real run first; drop `configfile` from the debian, zfs, tailscale, dotfiles, haos, and services includes and `homeassistant` from docker; add a guard test that every include tag is the `apply` tag or is carried by an inner task; pin the new tag sets                                                                      | `playbooks/nas_bootstrap.yml`, `tests/unit/test_services_role.py`, `tests/unit/test_nas_playbook.py` |
| W2 | **`deploy-services.sh`:** `--` before the ssh target and rsync operands; reject `NAS_USER` / `NAS_HOST` starting with `-`; build the `rsync -e` string with a single-quoted key and reject a key path containing `'`; print the dry-run ssh command with `%q`; add a stub that logs argument boundaries, and a real-rsync variant that skips when rsync is absent             | `scripts/nas/deploy-services.sh`, `tests/unit/test_deploy_services.py`                      |
| W3 | **`deploy.yml`:** pass `NAS_SSH_PRIVATE_KEY` and `NAS_TAILSCALE_HOST` through `env:` in `deploy-push` and `deploy-manual`; `umask 077` replaces `chmod`; `detect-changes` passes `github.event.before` / `github.sha` through `env:` too; test that no `run:` step contains `${{`                                                                                              | `.github/workflows/deploy.yml`, `tests/unit/test_deploy_workflow.py`                        |
| W4 | **Stale entries for the deleted `get_lutron_cert.py`:** remove the three `services/homeassistant/config/...` keys from `.secrets.baseline` and `pyproject.toml:308`; run `taplo format` (column alignment); validate the JSON                                                                                                                                                  | `.secrets.baseline`, `pyproject.toml`                                                       |
| W5 | **`uv` prerequisite:** guard in `nas_bootstrap.sh` (wording must avoid the strings `test_nas_bootstrap.py` forbids), README prerequisite line                                                                                                                                                                                                                                  | `nas_bootstrap.sh`, `tests/unit/test_nas_bootstrap.py`, `README.md`                         |
| W6 | **`roles/services`:** discovery filtered to services with a `compose.yml` (same `when` on the directory and render tasks, so the `secrets` tag still reaches exactly three tasks); rewrite the end-to-end test over a synthetic tree whose disabled service has an undefined variable, and keep a real-tree check whose expectation is computed, not hard-coded to PiHole     | `roles/services/tasks/main.yml`, `tests/unit/test_services_role.py`                         |
| W7 | **`resolve_nas_target`:** parametrized test for valid JSON that is not an object (`[]`, `null`, `"nas"`, `42`)                                                                                                                                                                                                                                                                | `tests/unit/test_run_nas.py`                                                                |
| W8 | **`roles/docker`:** `stat` then create `pihole-data/etc-pihole` only when absent; the other two directories keep enforced mode. Real-run test: `chmod 0775` the directory, run again, `changed=0` and mode preserved                                                                                                                                                           | `roles/docker/tasks/main.yml`, `tests/unit/test_services_role.py`                           |

## Workstream 2: docs

The audit lists become the per-file task specifications in the implementation plan. Truth sources are written first so
later files can link to them.

| File                                   | Treatment                                                                                                                                                                                                                       |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `roles/docker/README.md`               | Rewrite to roughly 110-130 lines: breadcrumb, one-line purpose, mdformat-toc block, ordered task table, installed paths and modes, the four `docker_*` variables plus inventory inputs, tags, the autoplex image, the contract with `services` |
| `services/README.md`                   | Correct the Glance/Plex shared `~/docker/.env` account, the dead `/pihole` route, the "all share `/storage/media`" overstatement, the disabling caveat (rsync never deletes), the `deploy.sh` command line, CI secrets; add data flow, storage layout, and operations (backups, image updates) |
| `roles/services`, `tailscale`, `samba` READMEs | Fill the gaps listed by the audit; samba grows from a stub; tailscale loses its stale manual steps; breadcrumbs added                                                                                               |
| `playbooks/README.md`, `roles/README.md` | Truthful tag section (`configfile`, no `homeassistant`), step 0 (become password), required vault variables, docker wording, `collection install`, the two enforced add-a-role steps (`EXPECTED_ORDER`, table row), syntax-check example |
| `.ctx/ARCHITECTURE.md`, `BUILD.md`, `CONVENTIONS.md` | Targeted fixes: `--force`, docker role wording, disabled PiHole, missing commands, retry-logic claim, OS-only stages, hook priorities and the leak-guard hooks, a short CI section, make-target limits, add-a-service / `if OS.mac?` / `.dotfiles-os` conventions |
| `README.md` (root), `CLAUDE.md`        | Root: "one engine, two entry points" framing, prerequisites (uv, SSH, `br0`), no PiHole step, component and documentation lists, project tree, corrected commands and wording, the "Running run.py" note. `CLAUDE.md`: haos role, `bootstrap.sh` also runs on the NAS, CI deploy, mdformat priority 35 |
| `vms/README.md`, `docs/RUN_PY_REFERENCE.md`, `scripts/nas/README.md`, `roles/docker/files/deploy.sh` (comment) | `vms`: `setup.sh` is run by the `haos` role. Reference: five missing commands, `update-inventory --force`, the `clean` venv group, the `nas-deploy` single-service clause, delete "Future Enhancements". Script README: validation and scope notes. `deploy.sh`: header names all three callers |

`.ctx/` and `docs/plans/` are excluded from `mdformat`, so those files are hand-wrapped at 120 columns; every other
changed Markdown file is formatted by `prek run mdformat`. Relative links only, no absolute home-directory paths.

## Workstream 3: guardrails and lessons

New tests in `tests/unit/test_docs_consistency.py` (same parse-the-table style as the existing guards):

1. The `services/README.md` Quick Reference lists exactly the `container_name` values in `services/*/compose.yml` and
   `compose.yml.disabled`, and a row is marked disabled iff its file is `.disabled`.
2. The role order in `playbooks/README.md` and `.ctx/ARCHITECTURE.md` matches the `include_role` order in
   `playbooks/nas_bootstrap.yml`.
3. Every command registered in `run.py` is documented in `docs/RUN_PY_REFERENCE.md` (included only if the registry is
   importable without side effects; otherwise a static parse of the `@command` decorators).

`CLAUDE-LESSONS.md` gains: enumerated infra inventories in docs drift (already cited by `test_docs_consistency.py`, never
written); string-matching Ansible YAML is not verification; `--check --diff` of a template prints the old file, so use
`diff: false` where the target holds secrets; a tag on `include_role` selects only the include (recorded after the real
run confirms it).

## Verification and rollout

In the branch:

1. Baseline `pytest` before any change; every new test is run against the old code first.
2. Full `pytest`, `scripts/hooks/ansible-lint.sh`, `prek run --all-files`, `ruff check` (never the formatter).
3. A relative-link and anchor check over every changed Markdown file.
4. Fresh read-only audit agents re-verify every changed doc claim against the code; zero open discrepancies is the exit
   criterion. The `ansible-idempotency-reviewer` agent reviews the role changes (W1, W6, W8).
5. A whole-branch code review before the PR.

On the NAS (owner runs; output saved under `$TMPDIR`; runbook `~/nas-sp4-rollout.md`):

1. **Baseline first** (still pending from sub-project 3): full `run.py nas-provision` on `main`, run twice; the second
   run must report `changed=0`.
2. Then from this branch: `nas-provision --check --diff`, a real run, and a second run at `changed=0`. Expected
   differences: none on a converged host; `~/docker/pihole/.env` stays in place (the skip stops re-rendering, it does
   not delete); `--tags configfile` now touches only the docker `.env`, the `deploy.sh` copy, and `smb.conf`.
3. `run.py nas-deploy glance --dry-run`, then a CI deploy, to cover W2 and W3.

## Risks

| Risk                                                                                  | Mitigation                                                                                                            |
| ------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `run-py-command-classes` (locked sibling worktree) edits `run.py` or its reference doc | No `run.py` edits here; `RUN_PY_REFERENCE.md` edits stay section-scoped so a rebase is mechanical                      |
| `.secrets.baseline` rescan adds noisy `archive/` entries                              | Hand-delete the three stale keys; do not rescan                                                                       |
| Docs rewritten from audit output carry the audit's errors                             | Fresh verification agents re-check every claim against the code; the author does not self-certify                    |
| A drift guard becomes brittle                                                         | Parse only structured data (tables, includes, decorators); each guard has a "parsed zero rows" companion test         |

## Deferred

- **PR B, `apt_repository` to `deb822_repository`.** Uses: `roles/docker/tasks/main.yml:30-38` and
  `roles/tailscale/tasks/install_debian.yml:15-22` (the archive copy is frozen; `roles/zfs` calls `apt-add-repository`
  through `command`, a separate cleanup). Carry forward: keep `signed_by` pointing at the existing keyring files so the
  `get_url` tasks stay; add `python3-debian` before the first `deb822_repository` task (the module imports
  `debian.deb822`); `deb822_repository` does not refresh the index, so the Docker install task needs `update_cache`
  without `cache_valid_time`; a leftover one-line `.list` beside the new `.sources` makes apt warn about duplicate
  sources, so add idempotent cleanup first (Tailscale's file name is known, `tailscale.list`; Docker's was auto-derived,
  so find it by content); the NAS is Debian 12, and behavior must be verified on a bookworm container or the NAS itself.
- **Legacy apt `docker-compose` removal:** a `state: absent` task, only if the owner confirms no consumer (the oh-my-zsh
  `docker-compose` plugin enabled by the shell package is the one reference found).
- Noticed, not fixed here: `roles/docker/templates/Caddyfile.j2.archived` is unreferenced; `tailscale_plex_port` is
  defined and never used; dead mypy / ruff / check-yaml excludes for `services/homeassistant/`; the `run.py` module
  docstring lists only two command categories.

## Open questions for the owner

Facts the code cannot answer; documented as absent from the docs rather than guessed:

1. Does the NAS configure Docker log rotation (`/etc/docker/daemon.json`)? The old README advised it; no role applies it.
2. Is there an `incomplete/` directory under `/storage/media/downloads`? The old README listed it; no compose file
   mounts it.
3. Is the `restrict` option present on the deploy key line in `~/.ssh/authorized_keys` (documented in
   `services/README.md`, not provable from the repository)?
