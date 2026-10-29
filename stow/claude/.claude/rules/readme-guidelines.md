---
globs: '**/README.md'
---

# README Guidelines

> How to write and maintain per-directory `README.md` files. These principles are tool-agnostic; a project may layer its
> own naming/section conventions on top in a project-level rule.

<!-- mdformat-toc start --slug=github --maxlevel=3 --minlevel=2 -->

- [Core Principles](#core-principles)
  - [Factual accuracy — never guess](#factual-accuracy-%E2%80%94-never-guess)
  - [Signal over noise — omit filler](#signal-over-noise-%E2%80%94-omit-filler)
  - [Diagrams only when they clarify](#diagrams-only-when-they-clarify)
  - [Relative links only](#relative-links-only)
- [Navigation Contract](#navigation-contract)
- [Directory Classification](#directory-classification)
- [Structure & Maintenance](#structure--maintenance)
- [Formatting](#formatting)

<!-- mdformat-toc end -->

## Core Principles<a name="core-principles"></a>

### Factual accuracy — never guess<a name="factual-accuracy-%E2%80%94-never-guess"></a>

Document **only what the source proves**: type annotations, `__all__`, docstrings, signatures, call sites. Never invent
behavior, intent, or data formats. Anything the code cannot answer goes into a **Clarifications needed** list as an
explicit question for the maintainer — never a plausible-sounding guess.

### Signal over noise — omit filler<a name="signal-over-noise-%E2%80%94-omit-filler"></a>

Every line must help a reader understand *what the module does* or *how it is structured*. Cut boilerplate that adds no
value: "this `__init__.py` is intentionally empty", "consumers import directly from `<module>`", noting that an empty
file is empty, or restating what a filename already conveys. If a line does not earn its place, delete it.

### Diagrams only when they clarify<a name="diagrams-only-when-they-clarify"></a>

Include a Mermaid (or any) diagram **only** when it genuinely illuminates architecture — a non-trivial class hierarchy,
a multi-step data/control flow, or component relationships that are hard to convey in prose. Never add a diagram by
default. A single box, a two-node flow, or a diagram that merely restates the file list adds nothing — omit it.

### Relative links only<a name="relative-links-only"></a>

Use repo-relative links throughout. Never hard-code absolute home-directory paths (`/Users/...`, `~/...`).

## Navigation Contract<a name="navigation-contract"></a>

Every README participates in a navigable tree:

- **Up-breadcrumb** at the very top (depth-appropriate relative paths; the repo-root README has none):
  ```
  [Project Root](../../README.md) > [Parent](../README.md) > **This Module**
  ```
- **Down-links:** a section listing each immediate child directory that has a README, linked.
- The **root README** carries the master directory table linking the whole tree.

## Directory Classification<a name="directory-classification"></a>

Pick a README template based on what the directory contains:

- **Code dir** — contains source files beyond an empty `__init__.py`. → **Full treatment:** public-API quick-reference
  table, `<details>` blocks for method-level detail, dependencies + reverse-dependencies, breadcrumb + child links, and
  a diagram only if it clarifies a non-trivial architecture.
- **Data / asset dir** — only non-code data/assets. → **Short README:** what the data is, its format, who
  produces/consumes it, and navigation links. No fabricated API. Require a README only at the *top* of a data tree; deep
  leaf data dirs need not each have one.
- **Meta dir** — `docs/`, `scripts/`, test dirs, the repo root. → **Index / overview:** a table or list appropriate to
  the contents (e.g. a table of test modules, a docs index).

## Structure & Maintenance<a name="structure--maintenance"></a>

A typical full-treatment README:

1. Up-breadcrumb
2. `# Title` + a one-line description of the module's purpose
3. mdformat-toc anchor block (only when the file is large enough — see project markdown convention)
4. Overview / key features with **working** code examples (examples must match current signatures)
5. Public-API quick-reference table; `<details>` blocks for dense method-level detail
6. Dependencies (required / optional / internal) and reverse-dependencies
7. Down-links to child READMEs

When a directory's source changes, refresh its README in the same change: a public symbol added/removed/renamed, a
changed signature, an added/removed file, or an example that no longer runs all make the README stale.

## Formatting<a name="formatting"></a>

Format every created/changed README with `mdformat` (e.g. `uv run mdformat <files>`). **Never** use `ruff format` on
markdown. Keep line width at 120 (except code blocks, tables, URLs, and mermaid diagrams).
