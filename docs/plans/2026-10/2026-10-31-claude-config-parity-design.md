# Claude Code Config Parity Design

**Date:** 2026-10-31
**Status:** Approved
**Goal:** Bring the parts of the work-machine Claude Code setup that are generic into this repo — a personal
statusline, the claude-devtools config, and the portable settings, skills and plugins — and document everything that is
deliberately left behind.

## Context

The work machine's Claude Code config lives in a private dotfiles repo and is stowed into `~/.claude`. This repo
already stows a subset (`stow/claude/`) and renders `settings.json` from layered fragments (`render/claude.json`, then
profile overlays such as `profiles/personal-mac/render/claude.json`).

An audit on 2026-10-31 found:

- The statusline the user likes is an **employer-internal, unlicensed npm package** configured through a
  `statusLineConfig` block in `settings.json`. The modular bash renderer stowed next to it is only a fallback with a
  different, plainer look. The package cannot be copied into this public repo.
- `claude-devtools` is already installed by the base Brewfile; only its app-written config file is missing.
- Most other deltas are employer-specific (internal marketplaces and plugins, MCP servers, proxy/env settings, a
  permission-review hook built on an internal AI gateway, internal skills). A smaller set is generic.

Because this repo is public and guarded by `scripts/hooks/check-leaks.py`, nothing employer-derived may be copied; every
ported item is either already generic or is rewritten.

## Decisions

| Decision               | Choice                                                         | Rationale                                                                            |
| ---------------------- | -------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| Statusline source      | Clean-room rewrite from the user's config and observed output  | The internal package is unlicensed; the package source is not read.                  |
| Statusline language    | Stdlib-only Python, run with `uv run --script`                 | Matches repo tooling; rendering logic is unit-testable; ~40-80 ms startup is fine.   |
| Statusline scope       | `neon` theme; `icon-pill` and `none` styles; nerd-font + text  | Covers the look in use; no speculative themes or styles (YAGNI).                     |
| Config schema          | Reuse the existing `statusLineConfig` key names                | The same settings read identically on both machines.                                 |
| Other deltas           | Port the generic ones now, report the rest                     | User choice. Each ported item is audited for employer-specific content first.        |
| Permission-review hook | Not ported                                                     | Entirely dependent on an internal gateway and auth; a rewrite is a separate decision. |

## Architecture

### 1. Statusline

- **Files:** `stow/claude/.claude/statusline/statusline.py` (renderer), referenced by `statusLine.command` in
  `render/claude.json` (base layer, so every machine gets it). Tests live in `tests/`.
- **Contract:** Claude Code pipes session JSON on stdin; the renderer prints one line on stdout. Any exception prints a
  minimal `dir │ model` line and exits 0, so the UI is never broken by the statusline.
- **Output shape:** each segment is a rounded nerd-font cap around a colored icon cell, followed by plain text in the
  same color; segments are joined by a configurable separator (`│`). The context segment renders a short bar plus a
  percentage. `none` style drops the pill and keeps icon + text. A `text` icon set provides a non-nerd-font fallback.
- **Components:** `directory`, `git` (branch, dirty, ahead/behind), `model`, `effort`, `context`, `duration`,
  `messages`, `tools`, `todos`, `active-tool`, and `quota` (cost/limits, shown only when the session JSON carries them).
  `agent` and `api-base` are dropped: they only exist for an employer-internal local proxy. A base-URL segment appears
  only when `ANTHROPIC_BASE_URL` is set.
- **Config (`statusLineConfig`):** `colorTheme`, `style`, `iconSet`, `separator`, `components`, `directoryStyle`,
  `contextStyle`, `modelStyle`, `truncation`. Unknown keys are ignored; missing keys fall back to defaults.
- **Transcript-derived segments** (`messages`, `tools`, `todos`, `active-tool`) read the transcript path from the
  session JSON, tail-limit the read, and omit the segment on any parse problem.

### 2. claude-devtools

Add `stow/claude/.claude/claude-devtools-config.json` (no employer-specific content; app-written, so the stowed
symlink lets the app update the tracked file). The cask is already in the base Brewfile.

### 3. Generic deltas

| Area            | Port                                                                                                          |
| --------------- | ------------------------------------------------------------------------------------------------------------- |
| Skills          | `gh-pr-comments` (GitHub Enterprise example genericized), `claude-session-logs`, `shell-scripting`            |
| Settings        | `spinnerVerbs` (employer reference and duplicate removed), `worktree.baseRef`, `modelSettings`, `theme`, `verbose` |
| Permissions     | Generic allow/deny entries only (toolchain commands, `Edit`/`Glob`/`Write`, superpowers skills, secret-file reads) |
| Plugins         | Public equivalents of the daily drivers, names verified against the official marketplace before enabling       |
| Reconciliation  | `file-searcher`, `ansible-devops-engineer` wording and the `CLAUDE.md` worktree line                            |

### 4. Not ported (documented in the delta report)

Employer marketplaces and plugins, internal MCP servers and their permission entries, proxy and registry env vars, the
managed-install config tree and its skill, the permission-review hook, VM/test-framework agents and skills, and the
bug-tracker branch-workflow section of the global `CLAUDE.md`.

## Constraints

- All Python via `uv`; `ruff format` is never run; `ruff check --fix` is.
- Repo `uv` invocations go through the scrubbing wrapper described in the leak-guard design, because the work
  environment exports internal index URLs.
- Every ported file is scanned for employer-specific content before commit; the leak-guard hook must pass.
- Rendered settings must remain drift-free (`render/claude.json` is the single source for `statusLine*`).

## Testing

- `pytest` unit tests: per-component rendering, theme and style output (ANSI stripped for assertions), config fallback,
  malformed or empty stdin, missing transcript, non-git directory, and the exception fallback line.
- Render pipeline: the existing render tests plus a case asserting `statusLine` appears in the rendered `settings.json`.
- Manual: run the renderer against recorded sample session JSON and compare against the work statusline's observed look.

## Delivery

Worktree `claude-config-parity`, four commits (statusline, devtools, settings and permissions, skills and plugins),
prek hooks green, then a PR from the branch.
