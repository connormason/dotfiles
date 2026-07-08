---
name: ruff-autofix
description: Auto-fix ruff lint violations in recently edited Python files. Use after editing Python files to catch and fix lint issues immediately rather than waiting for commit-time pre-commit hooks.
user-invocable: false
---

# Ruff Auto-Fix

After editing any Python file (`.py`), run ruff to auto-fix lint violations in-place.

## When to Activate

Trigger automatically after any Edit or Write to a `.py` file in the current project that is not included in
`.gitignore` rules or excluded by ruff per-file ignores (`tool.ruff.lint.per-file-ignores` in pyproject.toml or
ruff.toml).

## Procedure

1. Run `uv run ruff check --fix --quiet <file_path>` on the edited file
2. If ruff reports remaining unfixable violations, review them and fix manually
3. Do NOT run `ruff format` — this codebase does not use ruff's formatter

## Rules

- Only operate on `.py` files
- Don't run on `.py` files that are not tracked by git (based on `.gitignore` rules)
- Don't run on `.py` files that are excluded in ruff per-file ignores (`tool.ruff.lint.per-file-ignores` in
  pyproject.toml or ruff.toml)
- Always use `uv run` to invoke ruff (never bare `ruff`)
- Use `--fix` to apply safe fixes automatically
- Use `--quiet` to suppress noise — only show actual errors
- If a fix changes the file in a way that breaks the edit's intent, revert the fix and address the lint issue manually
- Do not fix files outside the current change scope
