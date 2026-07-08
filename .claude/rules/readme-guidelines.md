---
globs: '**/README.md'
---

# README Guidelines

Self-contained conventions for per-directory `README.md` files (does not depend on any global `~/.claude/rules/`).

## Core principles

- **Factual accuracy — never guess.** Document only what the source proves (signatures, `__all__`, docstrings, task
  names, call sites). Anything the code can't answer becomes an explicit "Clarifications needed" question, never a
  plausible-sounding guess.
- **Signal over noise.** Every line must help a reader understand what a module does or how it is structured. Cut
  filler ("this file is intentionally empty", restating a filename).
- **Diagrams only when they clarify** a non-trivial architecture or flow — never by default.
- **Relative links only.** Never hard-code absolute home-directory paths.

## Navigation contract

- Up-breadcrumb at the very top (repo root has none):
  `[Project Root](../README.md) > [Parent](../README.md) > **This Module**`
- Down-links: a section listing each immediate child directory that has a README.
- Every source/module directory carries its own `README.md` — `roles/`, `services/`, `playbooks/`, `scripts/install/`,
  and `docs/` already follow this.

## Repo specifics

- **This repo has no `mdformat`/`prek` hook** — READMEs are hand-maintained. Do not run `mdformat`, and do not add an
  mdformat-toc anchor block. Keep tables and wrapping tidy by hand at the **120-char** line width.
- Never run `ruff format` on markdown.
