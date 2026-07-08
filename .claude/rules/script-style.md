---
globs: '**/*.py'
---

# Script Styling & Console Output

Self-contained conventions for styled terminal output in CLI scripts (does not depend on any global `~/.claude/rules/`).

## Reference implementation

[`run.py`](../../run.py) is the canonical in-repo implementation of the styling contract — match its patterns when
adding styled output to `run.py` or scripts under [`scripts/`](../../scripts) (`env/`, `install/`). It provides:

| Function     | Purpose                                                                   |
| ------------ | ------------------------------------------------------------------------- |
| `style()`    | Apply ANSI escape codes to text; returns a styled string (does not print) |
| `printf()`   | Print styled text with indent / debug / verbose support                   |
| `folduser()` | Replace `$HOME` with `~` in path strings for display                      |
| `unstyle()`  | Strip all ANSI escape sequences from a string                             |

It also uses a `RawTextHelpFormatter`-based argparse setup with a typed `Args(argparse.Namespace)` subclass; follow that
shape for new CLI options.

## Conventions

- Route verbose/debug output to **stderr** so it never contaminates stdout.
- Use emoji-prefixed status lines (🟢 available, 🔴 failed, 🟡 warning, ✅ success) with a reinforcing text color; action
  messages (🔎 analyzing, 🧹 cleaning, 📦 building) use a cyan-ish accent. Keep it consistent with `run.py`.
- Custom **Ansible modules** live in [`library/`](../../library) (e.g. `configure_network_interfaces.py`,
  `osx_pmset.py`); they follow the same Python style rules but are executed by Ansible, not via `uv`.
