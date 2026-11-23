# medialink Implementation Plan

> **For agentic workers:** work the checkboxes in order and keep them current. Run Python through `uv run`; never run
> `ruff format`.

**Goal:** replace the `autoplex` container with the `medialink` hardlinking service and backfill the torrents it missed.

**Spec:** [`2026-11-22-medialink-design.md`](2026-11-22-medialink-design.md)

**Architecture:** a stdlib-only Python package under `services/medialink/` that reconciles Transmission's torrent list
against the library every 60 seconds, deployed through the existing `services/<name>/compose.yml` pipeline.

**Tech stack:** Python 3.12 in `python:3.12-slim`, Docker Compose, ntfy, pytest.

## Global Constraints

- The container runs as `1000:1000` and mounts `/storage/media` once, so hardlinks work.
- The `run` loop and `once` only add links. Only `dedupe --apply` replaces files.
- Nothing on the live NAS changes until the owner runs the rollout steps.

## File Structure

| Path                                                 | Role                                                      |
| ---------------------------------------------------- | --------------------------------------------------------- |
| `services/medialink/{compose.yml,Dockerfile,env.j2}` | Deployment                                                |
| `services/medialink/medialink/*.py`                  | The package                                               |
| `tests/unit/services/test_medialink.py`              | Unit and deploy-contract tests                            |
| `pyproject.toml`                                     | `src`, `pythonpath` and `mypy_path` for the package       |
| `roles/docker/`                                      | Autoplex clone and build removed                          |
| `services/README.md` and four others                 | Documentation                                             |

## Tasks

### Task 1: Package and tests

- [x] `config`, `transmission`, `classify`, `linker`, `state`, `notify`, `engine`, `dedupe`, `cli`
- [x] `archives`: RAR volume detection, staged extraction with `unrar`/`7z`, crash-safe publish, resume markers
- [x] `dedupe`: mirrored legacy copies to links, flat duplicates removed, `--quick` sampled comparison
- [x] Unit tests for each module and the deploy contract (the staging-cleanup test was checked by mutation)
- [x] `ruff check` and `mypy` clean
- [x] Dry run against the live Transmission: 2,260 links, 141 RAR sets, 488 reclaimable copies (about 640 GiB)
- [x] Image built; `unrar 7.12` extracted a real multi-volume release to the exact declared size (throwaway image removed)

### Task 2: Deployment files

- [x] `compose.yml` with one `/storage/media` mount, `build.context: medialink`, `pull_policy: build`
- [x] `Dockerfile`, `.dockerignore`, `env.j2` (ntfy token from the vault)

### Task 3: Remove autoplex from the repository

- [x] Delete `services/autoplex/`
- [x] Remove the clone and build tasks, the `.build` directory and the `docker_autoplex_*` defaults from `roles/docker/`
- [x] Update `tests/unit/services/test_services_role.py`
- [x] Update `services/README.md`, `roles/docker/README.md`, `README.md`, `roles/README.md`, `playbooks/README.md`,
      `.ctx/ARCHITECTURE.md`

### Task 4: Verify and merge

- [x] Full `uv run pytest`, `ruff check`, `mypy`, prek hooks
- [x] Open a PR; CI deploys `medialink` on the merge to `main` (#71; later #74 added the `medialink` console script and
      `run.py medialink` passthrough, #75 quieted steady-state logging)

### Task 5: Rollout (owner, on the NAS)

- [ ] `docker stop autoplex` before the first medialink deploy (two writers must never overlap)
- [ ] Review `once --dry-run` from a NAS checkout, before the container exists (the loop acts immediately)
- [ ] Deploy; wait for the first pass (linking, then RAR extraction) to finish
- [ ] Remove autoplex by hand (container, image, `~/docker/autoplex`, `~/docker/.build`)
- [ ] Confirm the backfill; re-run the name-and-size audit
- [ ] Review `dedupe --quick`, then `dedupe --apply` (flat duplicates grow from 14 to about 1,400 after the first pass)

### Task 6: Follow-up, Jellyfin-style reorganisation

Design: [`2026-11-22-medialink-reorg-design.md`](2026-11-22-medialink-reorg-design.md); implementation plan:
[`2026-11-22-medialink-reorg-plan.md`](2026-11-22-medialink-reorg-plan.md).

- [x] Decide the target naming (`Show/Season NN/`, `Movie (Year)/`) and a title parser or an external matcher (offline
      stdlib parser plus an overrides file)
- [ ] Move library links, not files, so the seed copies stay linked
- [ ] Dry-run report, then apply in batches with a rescan check in Jellyfin and Plex

### Task 7: Follow-up, optional done-script trigger

- [ ] Add a `MEDIALINK_DONE_SCRIPT` option that wires Transmission's `script-torrent-done` to a one-shot pass
- [ ] Keep the polling loop running as the safety net
