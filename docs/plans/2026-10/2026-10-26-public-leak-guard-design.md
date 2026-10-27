# Public Repo Hygiene & Leak Guard Design

**Date:** 2026-10-26
**Status:** Approved
**Goal:** Remove employer-internal content from this public repo (fix-forward) and make recurrence mechanically hard
before any dev-environment config is ported in from the private work dotfiles.

## Context

This repo is public on GitHub. Upcoming work (the dev-env base/overlay project) moves a large volume of configuration
from a private, employer-hosted dotfiles repo into this one, from a machine whose environment is configured for
employer-internal infrastructure. An audit on 2026-10-26 found existing leakage:

- `uv.lock` on `main` resolves every package through an employer-internal PyPI mirror. Root cause (verified
  empirically 2026-10-26): the work Claude Code settings export `UV_INDEX_URL` / `UV_DEFAULT_INDEX`, and the work
  user-level `~/.config/uv/uv.toml` adds the mirror as an `extra-index-url`, which uv consults *before* any default
  index. A plain `uv run` inside this repo silently rewrites a clean lock back to the mirror.
- `scripts/env/`, `scripts/install/`, and `scripts/maintain/` contain code derived from an employer-internal library,
  including an internal bug-tracker reference.
- `roles/git/templates/pre-commit.j2` hardcodes a virtualenv path belonging to that internal library.
- `docs/plans/2026-01/2026-01-21-dotfiles-improvement-plan/05-repo-integration-strategy.md` names internal tools.
- Five stale remote branches exist; three have unrelated history containing ~318 commits authored with a work email.

Manual vigilance will not scale to a bulk port. The guard must be automatic, run locally and in CI, and must not itself
publish the list of internal names it protects.

## Decisions

| Decision                  | Choice                                                         | Rationale                                                                                                       |
| ------------------------- | -------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| History                   | Fix forward; no history rewrite of `main`                      | Exposure is hostnames/email, not secrets; a force-push rewrite is irreversible and disproportionate.            |
| Internal-library scripts  | Delete; replace with standard tools                            | Ownership is uncertain; every script duplicates a standard tool (brew, `uv tool`, direnv, `prek autoupdate`).   |
| Stale branches            | Tag locally under `archive/*` (never pushed), delete on origin | Preserves a local record; removes the work-email commits from the public remote.                                |
| Guard pattern source      | Public generic baseline + optional private pattern file        | The public repo never enumerates internal tool/host names; the private work overlay supplies them (Project 1b). |
| Guard implementation      | Python prek hook + CI job                                      | Matches existing `scripts/hooks/*` style; a pygrep hook cannot load an external pattern file.                   |
| uv index                  | Run all repo uv calls via a scrubbing wrapper                  | Verified: only *unset index env vars + `UV_NO_CONFIG=1`* yields a public lock; the existing pin loses to both.  |
| Guard self-matching       | Write baseline regexes so their source text cannot match       | No exclusion list to maintain; the hook file is scanned like any other file.                                    |

## Architecture

### 1. Cleanup (one-time)

- Delete `scripts/env/`, `scripts/install/`, `scripts/maintain/` (scripts + READMEs).
- Remove the `run.py` commands `install-uv` and `install-hatch`; regenerate the `Makefile` (`run.py makefile`).
  uv is installed by Homebrew in the bootstrap; hatch, where still needed, via `uv tool install hatch`.
- Replace `roles/git/templates/pre-commit.j2` with a generic git-template hook that delegates to `prek` when a repo
  has a `.pre-commit-config.yaml` (no hardcoded interpreter path).
- Strip internal tool names from plan `05-repo-integration-strategy.md` and mark it superseded by the dev-env
  base/overlay design.
- Update any README / `.ctx` / `docs/RUN_PY_REFERENCE.md` references to the deleted scripts and commands.
- Regenerate `uv.lock` against `pypi.org` with `UV_INDEX_URL`, `UV_DEFAULT_INDEX`, `UV_EXTRA_INDEX_URL` unset.
- Remote branches `2026_infra_revamp`, `caddy_minimal`, `hooks`, `plex_bringup`, `separate_inventory_repo`:
  `git tag archive/<name> origin/<name>` locally, then `git push origin --delete <name>`.

### 2. Leak guard — `scripts/hooks/check-leaks.py`

**Inputs:** file paths (prek passes staged files; CI passes the full tree via `--all-files`).

**Pattern sources (case-insensitive regexes, one per line, `#` comments allowed):**

1. Built-in public baseline, embedded in the script: the employer's corporate domain and any subdomain (covers email
   addresses, internal hosts, and package mirrors) and bug-tracker URL schemes. Public vendor hosts (`www.`, `apps.`,
   `developer.`, `support.` — present in every macOS plist DTD and App Store URL) are allowed. Patterns are anchored so
   standard macOS `com.<vendor>.*` preference domains and the `Radarr` service do not match, and are written (escaped
   dot, `/{2}` quantifier) so the script's own source text never matches them.
2. Optional private file: `$DOTFILES_LEAK_PATTERNS`, defaulting to `~/.config/dotfiles/leak-patterns.txt`. Absent →
   silently baseline-only. Present but unreadable/invalid regex → hard error (fail closed).

**Checks:**

- File content and file path against all patterns. Binary files (NUL byte in the first 8 KiB) are skipped. At most
  five findings are printed per file, followed by a count of the remainder.
- Commit identity (`--identity`, pre-commit stage only): `git var GIT_AUTHOR_IDENT` and `GIT_COMMITTER_IDENT` against
  all patterns, so a commit made with the wrong `user.email` fails before it exists.
- Identity list (`--identities-from FILE|-`, CI): one `Name <email>` per line, checked against all patterns.
- Allow escape hatch: a line containing `leak-guard: allow` is skipped (for genuine false positives only).

**Output:** follows the repo hook format (`scripts/hooks/README.md`): `ERROR <path>:<line>` with the matched span
masked except for the first/last character, so CI logs do not re-publish the leaked string. Exit 1 on any finding.

**Wiring:**

- `.pre-commit-config.yaml`: local hook `check-leaks --identity`, checks band, `pre-commit` stage, all text files.
- `.github/workflows/leaks.yml`: add a `leak-guard` job that scans `git ls-files` (the runner has no git identity, so
  CI calls the script directly rather than through prek) and pipes every author/committer identity in the pushed or PR
  range to `--identities-from -`.

### 3. uv index root-cause guard

- `pyproject.toml` already declares `[[tool.uv.index]]` `name = "default"`, `url = "https://pypi.org/simple"`,
  `default = true` — and the lock was polluted anyway, which is the proof that the pin alone is insufficient. No change.
- `scripts/hooks/uv-public.sh`: `unset UV_INDEX_URL UV_DEFAULT_INDEX UV_EXTRA_INDEX_URL UV_INDEX`,
  `export UV_NO_CONFIG=1`, `exec uv "$@"`. Both halves are required (verified). `UV_NO_CONFIG` skips only user/system
  `uv.toml` files; the project's `[tool.uv]` table (e.g. `default-groups`) is still honored (verified).
- `.pre-commit-config.yaml`: replace the upstream `astral-sh/uv-pre-commit` hooks with local `language: system` hooks
  of the same ids that call the wrapper. Because `uv-lock` fires whenever `uv.lock` is staged, a lock polluted by a
  plain `uv run` is rewritten back to `pypi.org` at commit time (self-healing), and the commit stops for re-staging.
- `.claude/settings.json` (project): `env` pins `UV_NO_CONFIG=1`, `UV_DEFAULT_INDEX` and `UV_INDEX_URL` to
  `https://pypi.org/simple`, overriding the work user-level values for Claude Code sessions opened in this repo. Its
  PostToolUse hooks (`uv run ruff …`, `uv run yamllint …`) switch to the wrapper, since each plain `uv run` re-locks.
- `run.py` does not invoke uv; no change needed there.
- The leak guard is the backstop: a re-polluted `uv.lock` that somehow bypasses the hook still fails the commit.

## Testing

`tests/unit/test_check_leaks.py`:

- Baseline hits (domain, subdomain, email, tracker URL) and non-hits (`com.<vendor>.dock`-style domains, public
  vendor hosts, `Radarr`, `radarr`, the script's own source file).
- Private pattern file: absent → baseline only; present → extra patterns applied; invalid regex → non-zero exit.
- `leak-guard: allow` suppresses a single line only.
- Identity check rejects a matching author email, accepts a personal one (via `GIT_AUTHOR_EMAIL` env override).
- Output masking never prints the full matched string.

Acceptance: before cleanup, `prek run check-leaks --all-files` flags exactly the items in **Context**; after cleanup it
passes. `uv.lock` contains only `pypi.org` / `files.pythonhosted.org` URLs. `prek run --all-files` and CI are green.

## Out of Scope

- Stale READMEs, Pkl hooks, Ansible-role modernization — superseded by the dev-env base/overlay project.
- Rewriting `main` history.
- Shipping the private pattern file (delivered by the work overlay in Project 1b).
