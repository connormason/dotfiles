---
globs: '**/*.py'
---

# Python Style

Self-contained Python style for this repository (does not depend on any global `~/.claude/rules/`). Python here is
`run.py`, custom Ansible modules under `library/`, and helper scripts under `scripts/`.

## Tooling (non-negotiable)

- Always run Python via **`uv`** (`uv run …`) — never bare `python`, `python3`, `pip`, or `hatch`.
- `ruff check --fix` is encouraged. **Never** run `ruff format` — this repo does not use the formatter.
- Config lives in `pyproject.toml`: ruff `line-length = 120`, `target-version = "py39"` (`keep-runtime-typing = true`),
  space indent (width 4). `interrogate` enforces **70%** docstring coverage (`fail-under = 70`).

## Imports

- `from __future__ import annotations` is a **required first import** (isort `required-imports`).
- isort uses **`force-single-line = true`** — one import per line; never `from x import a, b`.
- Ordering: standard library → third-party → local → `if TYPE_CHECKING:` block.
- `TC` (flake8-type-checking) is on: move type-only imports into `if TYPE_CHECKING:` blocks. `pydantic.BaseModel`
  subclasses are runtime-evaluated (exempt).

## Types & naming

- Python 3.9 syntax: `list[str]`, `dict[str, Any]`, `str | None` (via `from __future__ import annotations`).
- Files/modules snake_case; classes PascalCase; functions/methods snake_case; constants UPPER_SNAKE_CASE.
- No bare `Any` without justification (`ANN401` is otherwise ignored repo-wide, so use it sparingly and deliberately).
- No mutable default arguments. Exception chaining required: `raise NewError(...) from e` (or `from None`).
- Public **modules** define `__all__` after imports; scripts executed directly (e.g. `run.py`) do not.

## Quotes & docstrings

- **Single quotes** for inline strings (`flake8-quotes` inline-quotes = single).
- Docstring convention is **sphinx** (`interrogate style = "sphinx"`): colon-terminated section headers (`Examples:`,
  `See Also:`) and Sphinx field tags (`:param:`, `:raises:`, `:return:`). There is **no** enforced summary-line period
  and **no** dashed section underlines (that is the numpy convention, which this repo does not use).
- No blank line between a class docstring and its first member.

## `run.py` patterns

Commands register via the `@command` decorator into a global registry that drives both argparse and Makefile generation;
subprocess calls go through the typed `shell_command()` wrapper. Match these when adding commands. See
[`.ctx/CONVENTIONS.md`](../../.ctx/CONVENTIONS.md).
