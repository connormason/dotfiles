---
globs: '**/README.md'
---

# README Guidelines

Self-contained conventions for per-directory `README.md` files (does not depend on any global `~/.claude/rules/`).

## Core principles

- **Factual accuracy — never guess.** Document only what the source proves (signatures, `__all__`, docstrings, task
  names, call sites). Anything the code can't answer becomes an explicit "Clarifications needed" question, never a
  plausible-sounding guess.
- **Signal over noise.** Every line must help a reader understand what a module does or how it is structured. Cut filler
  ("this file is intentionally empty", restating a filename).
- **Diagrams only when they clarify** a non-trivial architecture or flow — never by default.
- **Relative links only.** Never hard-code absolute home-directory paths.

## Navigation contract

- Up-breadcrumb at the very top (repo root has none):
  `[Project Root](../README.md) > [Parent](../README.md) > **This Module**`
- Down-links: a section listing each immediate child directory that has a README.
- Every source/module directory carries its own `README.md` — `roles/`, `services/`, `playbooks/`, `scripts/install/`,
  and `docs/` already follow this.

## Repo specifics

- **Markdown is auto-formatted by `mdformat` via the `prek` hook** (`.pre-commit-config.yaml`, priority 30) at the
  **120-char** line width. `.ctx/` and `docs/plans/` are excluded, so those stay hand-maintained. Run
  `prek run mdformat --all-files` (or let the commit hook do it) rather than formatting by hand.
- Files with 100+ lines and 3+ h2 sections should carry the mdformat-toc anchor block (`<!-- mdformat-toc start ... -->`
  / `<!-- mdformat-toc end -->`) immediately after the H1 description; the hook populates it. Shorter files omit it.
- Never run `ruff format` on markdown.
