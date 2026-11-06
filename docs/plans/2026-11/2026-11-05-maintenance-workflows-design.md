# Scheduled maintenance workflows — design

Port the scheduled upkeep automation from the author's work repository to this repo, replacing its internal CI layer
with GitHub Actions. This repo is public and guarded by the `check-leaks` hook, so nothing committed here may name the
source repo, its CI system, or other internal identifiers; the port is a clean re-implementation of generic logic.

## Goal

Keep three kinds of tracked state fresh without manual effort, each delivered as a reviewable pull request against
`main`:

1. prek hook revisions in `.pre-commit-config.yaml` (with a release-age cooldown for supply-chain safety)
2. Python dependencies in `uv.lock`, plus the files derived from it (`requirements.txt`, hook dependency pins)
3. The toptal-generated block of `.gitignore` (custom patterns below the end marker preserved)

## Scope

**In:** a prek auto-update script, a gitignore refresh script, a consolidated dependency update, the shared PR-opening
layer, two scheduled workflows, unit tests, and docs.

**Out:** the older `pre-commit`-based updater (superseded; this repo uses prek), the public-API sync tooling
(specific to the work repo), and the ruff-reference generator (no `docs/references/` tree here; not requested).

## What changes from the work repo

| Work repo                                                   | This repo (GitHub Actions)                                    |
| ----------------------------------------------------------- | ------------------------------------------------------------- |
| Pipeline timer in the CI config                             | `on: schedule` + `workflow_dispatch`                          |
| Shared wrapper module (run steps, commit, push, open PR)    | Composite action `.github/actions/open-maintenance-pr`        |
| Internal GitHub client and CI secret store                  | `gh` CLI with a fine-grained PAT secret                       |
| `--branch` argument on every wrapper                        | Base branch fixed to `main` in the composite action           |
| Dependency wrapper delegating to the `lock-upgrade` target  | Workflow steps: `update_prek.py`, then `run.py lock-upgrade`  |
| Internal-certificate workaround in the gitignore fetcher    | Dropped (GitHub runners have a normal trust store)            |

## Components

### 1. `scripts/codebase/update_prek.py`

Wraps `prek auto-update` with the tag/repo filter surface, `--cooldown-days`, and `--dry-run` (run, report, revert).
Conformed to this repo's rules: single-line imports, sphinx docstrings, boxed section headers, and the styled-output
helpers copied verbatim from `run.py` (`scripts/` are standalone). Public symbol: `run_autoupdate`.

### 2. `scripts/codebase/update_gitignore.py`

Reads the template list from the toptal URL in the current `.gitignore`, fetches fresh content (`urllib`, falling back
to `curl`), and re-appends custom patterns found after the end marker. The third `git-ignore-io` fallback is dropped: no
runner or machine here has it. Public symbols: `extract_templates_from_gitignore`, `extract_custom_patterns`,
`fetch_gitignore_content`, `generate_updated_gitignore`.

### 3. Composite action `.github/actions/open-maintenance-pr/action.yml`

Inputs: `branch` (e.g. `maintenance/update-dependencies`), `paths` (files to inspect and stage), `title`, `body`,
`commit-message`, `token`. Behaviour, using an evergreen head branch:

1. If none of `paths` differ from `HEAD` (`git status --porcelain -- <paths>`), report "up to date" and exit 0.
2. Set the committer identity, stage `paths`, commit, and `git push --force origin HEAD:<branch>`. The branch is
   always exactly one commit ahead of `main`.
3. If an open PR for `<branch>` exists, `gh pr edit` it (title/body refreshed); otherwise `gh pr create --base main`.

Pushing and PR creation use the PAT, not `GITHUB_TOKEN`, so the PR triggers `lint.yml` and gitleaks.

### 4. Workflows

- `.github/workflows/update-dependencies.yml` — Tuesdays 09:00 UTC. Steps: checkout, `astral-sh/setup-uv`,
  `uv sync --group lint`, `uv run scripts/codebase/update_prek.py --cooldown-days 3`, `uv run run.py lock-upgrade`,
  then the composite action over `.pre-commit-config.yaml`, `uv.lock`, `requirements.txt`. Order matters:
  `lock-upgrade` regenerates `requirements.txt` and re-syncs hook dependency pins from the new lock, so it runs after
  the hook bump.
- `.github/workflows/update-gitignore.yml` — Mondays 09:00 UTC. Steps: checkout, setup-uv,
  `uv run scripts/codebase/update_gitignore.py --force`, composite action over `.gitignore`.

Both: `permissions: contents: read` (writes happen through the PAT), `workflow_dispatch` enabled for manual runs, and a
`concurrency` group per workflow so overlapping runs cannot race on the evergreen branch.

### 5. Tests

`tests/unit/scripts/codebase/` covering the pure logic: template and custom-pattern extraction, gitignore regeneration
(with and without custom patterns, missing marker), `run_autoupdate` command construction for each option, and argument
validation in `main`. Network and `prek` invocations are mocked.

### 6. Docs

New `scripts/codebase/README.md` (breadcrumb, script table, API quick reference), a row in `scripts/README.md`, and
workflow notes in `.ctx/BUILD.md` / `.ctx/ARCHITECTURE.md` where CI is already covered.

## Prerequisites outside the repo

- Create a fine-grained PAT scoped to this repository only (`contents: write`, `pull-requests: write`) and store it as
  the `MAINTENANCE_PR_TOKEN` Actions secret. Owner action; documented in the new README.
- Actions already has "create pull requests" enabled and default `write` workflow permissions (verified via the API).

## Risks and open points

- **Provenance.** The source scripts were written for an employer-hosted repo. The leak guard is deliberately strict
  here, so the port must be a scrubbed re-implementation (no internal names, emails, hosts, or header attributions),
  and the author should confirm they are free to publish it. This is the author's call, not something the tooling can
  decide.
- **PAT expiry.** Fine-grained PATs expire (max one year). A lapsed token fails the workflow loudly at the push step;
  the README notes the renewal.
- **`run.py lock-upgrade` on a Linux runner.** It calls `ensure_uv`/`check_python` and runs derived-file hooks through
  `prek`; expected to work (repo supports Linux) but unproven in CI until the first `workflow_dispatch` run.
- **Third-party actions** are limited to `actions/checkout` and `astral-sh/setup-uv`, already used by `lint.yml`.

## Verification

- Unit tests and `ruff check` pass; prek hooks (including `check-leaks`) pass on every new file.
- Both scripts run locally with `--dry-run` against this repo and leave the tree clean.
- Composite action logic exercised with a local fixture repo (changed / unchanged / existing-PR paths, `gh` stubbed).
- After merge: `workflow_dispatch` each workflow once and confirm the PR opens and runs `lint.yml`.
