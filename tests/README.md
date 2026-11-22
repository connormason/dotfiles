[Project Root](../README.md) > **Tests**

# Tests

The pytest suite. `python3 run.py test [PATH...]` (or `make test`) runs the unit tests not marked `slow`, and
`test-full` runs everything; both go through the public-index `uv` wrapper (the other subsets are in
[`docs/RUN_PY_REFERENCE.md`](../docs/RUN_PY_REFERENCE.md#testing)). CI runs `uv run pytest` on macOS and Linux (see
[`.ctx/BUILD.md`](../.ctx/BUILD.md#ci)).

| Path                           | Contents                                                                                               |
| ------------------------------ | ------------------------------------------------------------------------------------------------------ |
| [`conftest.py`](conftest.py)   | Shared fixtures: `SHELLS`, `shell`, `unreadable_overlay`                                               |
| [`golden.py`](golden.py)       | `check_golden()`: compare lines to a golden file; set `DOTFILES_UPDATE_GOLDEN=1` to rewrite the golden |
| [`unit/`](unit/)               | Unit tests, one subdirectory per area of the repo (below)                                              |
| [`integration/`](integration/) | `pytest.mark.integration` tests: throwaway-`HOME` stow and render runs, and the per-OS link layout     |
| [`fixtures/`](fixtures/)       | Input data: `model_router/` payloads, `os_layout/` golden files, `overlay/` fixture overlay            |

## Unit tests<a name="unit-tests"></a>

| Directory                            | Covers                                                                              |
| ------------------------------------ | ----------------------------------------------------------------------------------- |
| [`unit/bootstrap/`](unit/bootstrap/) | `bootstrap/` stage scripts and driver, including the NAS bootstrap and playbook     |
| [`unit/claude/`](unit/claude/)       | Stowed Claude tooling: the model router hook and the statusline                     |
| [`unit/deploy/`](unit/deploy/)       | `scripts/nas/deploy-services.sh` and the deploy workflow                            |
| [`unit/profiles/`](unit/profiles/)   | `profiles/` overlays                                                                |
| [`unit/cli/`](unit/cli/)             | `cli/` (behind `run.py`): infra, utils (uv, doctor, HA sync, styling), and commands |
| [`unit/scripts/`](unit/scripts/)     | `scripts/`: render, env, install, hook scripts, and the docs audit                  |
| [`unit/services/`](unit/services/)   | Per-service secrets and the `services` Ansible role                                 |
| [`unit/stow/`](unit/stow/)           | `stow.sh`, the stow summary, and the stow package tree                              |
| [`unit/vms/`](unit/vms/)             | `vms/haos` setup                                                                    |

Two modules sit directly in `unit/` as repository guardrails: `test_docs_consistency.py` keeps hand-maintained
documentation inventories in sync with the files they describe, and `test_repo_hygiene.py` checks that path-keyed config
(the `detect-secrets` baseline and ruff per-file ignores) names only existing files.
