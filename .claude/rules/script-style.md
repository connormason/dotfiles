---
globs: '**/*.py'
---

# Script Styling & Console Output

Concise rules for styled terminal output in CLI scripts (does not depend on any global `~/.claude/rules/`). The full
guide, with the color and emoji tables, output patterns, argparse setup, and a script skeleton, is
[`scripts/STYLE-GUIDE.md`](../../scripts/STYLE-GUIDE.md); read it before adding styled output.

## Reference implementation

The `# Text styling` section of [`run.py`](../../run.py) is the canonical implementation. Scripts under
[`scripts/`](../../scripts) are standalone, so they carry copies of the helpers; copy from `run.py` verbatim rather than
rewriting, and when a copy disagrees with `run.py`, `run.py` wins.

| Function     | Purpose                                                                   |
| ------------ | ------------------------------------------------------------------------- |
| `style()`    | Apply ANSI escape codes to text; returns a styled string (does not print) |
| `printf()`   | Print styled text with indent / debug / verbose support                   |
| `folduser()` | Replace `$HOME` with `~` in path strings for display                      |
| `unstyle()`  | Strip all ANSI escape sequences (not `remove_ansi()`)                     |

## Conventions

- Colors are semantic: paths `magenta`, commands `bright_magenta`, CLI options `yellow`, versions `bright_cyan`, errors
  `bright_red`, warnings `bright_yellow`, success `bright_green`, action headers `bright_cyan`.
- Route verbose/debug output to **stderr**, dim, gated on a runtime flag (`debug=True` in `run.py`, `verbose=True` in
  standalone scripts); it must never contaminate stdout.
- Use emoji-prefixed status lines (🟢 available, 🔴 failed, 🟡 warning, ❌ inline error, ✅ success) with a reinforcing text
  color; action messages (🔎 analyzing, 🧹 cleaning, 📦 building) are `bright_cyan`.
- Indent sub-items 3 spaces, nested details 5, deep details 7; hook detail lines 8.
- `style()` honors `NO_COLOR`; call `folduser()` before styling a path.
- Argparse: `RawTextHelpFormatter` with `max_help_position=50`, `add_help=False` with `-h/--help` re-added in a final
  "Other options" group, a typed `Args(argparse.Namespace)`, one local function per option group.
- Shell scripts under [`bootstrap/`](../../bootstrap) and [`stow.sh`](../../stow.sh) have their own helpers
  (`bootstrap/lib.sh`); Python helpers live in [`scripts/`](../../scripts) and follow the same Python style rules.
