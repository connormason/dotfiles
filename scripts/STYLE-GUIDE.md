[Project Root](../README.md) > [Scripts](README.md) > **Style Guide**

# Script Styling & Console Output Guide

Standard patterns for console output and argparse setup across [`run.py`](../run.py) and every script under `scripts/`.

For the concise rules version auto-loaded by Claude Code, see
[`.claude/rules/script-style.md`](../.claude/rules/script-style.md).

<!-- mdformat-toc start --slug=github --maxlevel=3 --minlevel=2 -->

- [Overview](#overview)
- [Canonical Implementation](#canonical-implementation)
  - [Helper Reference](#helper-reference)
  - [Copying the Helpers Into a Script](#copying-the-helpers-into-a-script)
- [Color Theme](#color-theme)
- [Status Indicator Emoji](#status-indicator-emoji)
- [Output Patterns](#output-patterns)
  - [Tool Status Lines](#tool-status-lines)
  - [Action Headers](#action-headers)
  - [Success, Warning, and Error Messages](#success-warning-and-error-messages)
  - [Debug / Verbose Output](#debug--verbose-output)
  - [Hook Script Output](#hook-script-output)
- [Indentation](#indentation)
- [Argparse Conventions](#argparse-conventions)
- [Script Skeleton](#script-skeleton)

<!-- mdformat-toc end -->

## Overview<a name="overview"></a>

Scripts here share one visual language so output stays scannable: colors are assigned by *meaning* (a file path is
always magenta, a command always bright magenta), status lines lead with an emoji, and indentation marks hierarchy.

Most scripts run standalone, before or outside the project venv (`install_uv.py`, `install_hatch.py`, `venvshell.py`,
the prek hooks), so there is no shared styling package to import. The helpers are therefore copied into each script, and
the copies stay consistent only if they track one reference. That reference is `run.py`.

## Canonical Implementation<a name="canonical-implementation"></a>

The `# Text styling` section of [`run.py`](../run.py) is the source of truth for helper names, signatures, and behavior.
When a script's copy disagrees with `run.py`, the script is wrong.

### Helper Reference<a name="helper-reference"></a>

| Helper                            | Purpose                                                                           | Needed by         |
| --------------------------------- | --------------------------------------------------------------------------------- | ----------------- |
| `style(text, *, fg, bg, bold, …)` | Wrap text in ANSI codes and return it (does not print). Honors `NO_COLOR`         | every script      |
| `unstyle(text)`                   | Strip ANSI escape sequences. Canonical name; do not use `remove_ansi()`           | tests, width math |
| `folduser(path)`                  | Replace the home directory with `~`. Call it before `style()` when showing a path | every script      |
| `printf(text, *, indent, …)`      | Styled `print()` with indentation and debug/verbose gating                        | every script      |
| `pathstyle(path)`                 | `style(folduser(path), fg='magenta')`                                             | on demand         |
| `optstyle(text)`                  | `style(text, fg='yellow')` for CLI option names                                   | on demand         |
| `typestyle(val)`                  | Style a Python value by type (`None`, `bool`, `Path`, numbers, `str`, sequences)  | on demand         |
| `dim_paren(text, *, fg)`          | Dim `(text)` for supplementary info                                               | on demand         |
| `arg_note(name, val, *, color)`   | Dim `[name: val]` annotation for argparse help (env var, default)                 | scripts with opts |
| `status_line(name, detail, …)`    | Emoji + padded tool name + colored detail + optional `@ path` (`run.py` only)     | `run.py`          |

`style()` and `printf()` accept the full attribute set (`fg`, `bg`, `bold`, `dim`, `underline`, `overline`, `italic`,
`blink`, `reverse`, `strikethrough`, `reset`). A copy in a small script may drop attributes it never uses (the hooks
keep `fg`, `bold`, `dim`) but must keep the names and semantics of those it retains.

### Copying the Helpers Into a Script<a name="copying-the-helpers-into-a-script"></a>

Lift the blocks from `run.py` verbatim rather than rewriting them, and keep these behaviors:

- `style()` returns the text unstyled when `NO_COLOR` is set to a non-empty value (<https://no-color.org>), and appends
  the reset code unless `reset=False`. Read it once into a module-level `NO_COLOR` constant.
- `style()` raises `TypeError` (chained `from None`) for an unknown color name.
- `printf()` applies indentation with `textwrap.indent(text, ' ' * indent)` so multi-line text indents on every line.
- `printf()` in debug/verbose mode is a no-op unless the flag is on; when on, it defaults to `fg='bright_white'`,
  `dim=True` and writes to **stderr**.
- Add `flush=True` to `printf()` only in a script that streams child-process output straight to the terminal, so lines
  stay ordered when stdout is a pipe. `run.py` does; the hooks and installers capture child output and do not need it.

The gating flag differs by script type: `run.py` uses `printf(..., debug=True)` gated on `RUN_DEBUG`; standalone scripts
use `printf(..., verbose=True)` gated on a module-level `VERBOSE` set from `--verbose`.

## Color Theme<a name="color-theme"></a>

| Semantic role                  | `fg=`            | Modifiers   | Example                                            |
| ------------------------------ | ---------------- | ----------- | -------------------------------------------------- |
| File paths                     | `magenta`        |             | `pathstyle(path)`                                  |
| Commands / executables         | `bright_magenta` |             | `style('ruff check', fg='bright_magenta')`         |
| CLI option names               | `yellow`         |             | `optstyle('--verbose')`                            |
| Tool names (status lines)      | `white`          | `bold=True` | `style('python', fg='white', bold=True)`           |
| Version numbers                | `bright_cyan`    |             | `style('3.12.3', fg='bright_cyan')`                |
| Location annotations           |                  | `dim=True`  | `style('@ ~/.local/bin/python', dim=True)`         |
| Section headers / labels       | `bright_white`   | `bold=True` | `style('Commands:', fg='bright_white', bold=True)` |
| Informational body text        | `bright_white`   |             | text that is not a specific category               |
| Error text                     | `bright_red`     |             | body of error messages                             |
| Error labels                   | `bright_red`     | `bold=True` | `ERROR`                                            |
| Warning text                   | `bright_yellow`  |             | body of warning messages                           |
| Success text                   | `bright_green`   |             | completion messages                                |
| Action headers                 | `bright_cyan`    |             | `🔎 Linting code...`                               |
| Debug / verbose output         | `bright_white`   | `dim=True`  | applied automatically by `printf(debug=True)`      |
| Supplementary / parentheticals |                  | `dim=True`  | file counts, notes: `dim_paren('3 files')`         |

## Status Indicator Emoji<a name="status-indicator-emoji"></a>

The emoji carries the meaning; the text color reinforces it.

**State emoji:**

| Emoji | Meaning                      | Text color                |
| ----- | ---------------------------- | ------------------------- |
| 🟢    | Available / active / healthy | `bright_green` or neutral |
| 🔴    | Missing / failed / fatal     | `bright_red`              |
| 🟡    | Warning / optional missing   | `bright_yellow`           |
| ❌    | Error (inline, mid-flow)     | `bright_red`              |
| ✅    | Success / done               | `bright_green`            |
| ⚠️    | Cancelled / precondition     | `yellow`                  |
| ❓    | Unknown / unrecognized       | `red` (bold)              |

**Action emoji** (an operation in progress) always pair with `fg='bright_cyan'`:

| Emoji   | Action                            |
| ------- | --------------------------------- |
| ⏬      | Downloading / preparing           |
| 💿      | Installing                        |
| 💾      | Creating (environment, artifact)  |
| 🔎      | Analyzing / linting               |
| 🧹      | Cleaning                          |
| 📦      | Building / syncing dependencies   |
| 🕝      | Running prek hooks                |
| 🔧      | Running a diagnostic or check     |
| 🔒      | Locking / encrypting              |
| 🔗      | Linking (restowing)               |
| 🔄      | Updating / forcing a re-run       |
| 🔍      | Verifying                         |
| ⏩ / ⏪ | Entering / exiting an environment |

Emoji that render narrow (`⚠️`) take two trailing spaces so the message text lines up with the single-space emoji. New
emoji should follow the same rule: pick one that reads at a glance, and record it here when a second script adopts it.

## Output Patterns<a name="output-patterns"></a>

### Tool Status Lines<a name="tool-status-lines"></a>

Report tool availability as `emoji  name  version  @ folded_path` with aligned columns. In `run.py`, use
`status_line()`, which left-justifies the name to 12 columns and picks ✅ / 🟡 / 🔴 from `ok`, `warn`, and `optional`:

```python
status_line('python', '3.12.3', path=Path('~/.local/bin/python'))  # ✅  python       3.12.3 @ ~/.local/bin/python
status_line('hatch', 'not found', ok=False, optional=True)         # 🟡  hatch        not found
```

Standalone scripts build the same line by hand, padding the version with `.ljust(8)`:

```python
printf(
    f'🟢 {style("python", fg="white", bold=True)}  '
    f'{style(version.ljust(8), fg="bright_cyan")} '
    f'{style(f"@ {folduser(exe)}", dim=True)}',
    indent=indent,
)
```

### Action Headers<a name="action-headers"></a>

Announce an operation in `bright_cyan` with its emoji. Sub-items go three columns in (the emoji plus its space):

```python
printf('🔎 Linting code...', fg='bright_cyan')
printf(f'Running {style("ruff check", fg="bright_magenta")}', indent=3)
```

### Success, Warning, and Error Messages<a name="success-warning-and-error-messages"></a>

```python
printf('✅ Cleanup complete', fg='bright_green')
printf(f'{cleaned} files removed', dim=True, fg='bright_white', indent=3)

printf(f'🟡 Environment "{name}" is active and must be exited first', fg='bright_yellow')

printf('🔴 uv is not installed', fg='bright_red')                                    # fatal: followed by sys.exit
printf(f'   To continue, run {style("make bootstrap", fg="bright_magenta")}', fg='bright_white')

printf('❌ Failed to write installer', fg='bright_red', indent=indent)              # inline error mid-flow
printf(str(e), fg='red', indent=indent + 3)
```

Errors that end the run go to stderr (`file=sys.stderr`) so stdout stays parseable.

### Debug / Verbose Output<a name="debug--verbose-output"></a>

```python
printf(f'Running command: {style(shlex.join(cmd), fg="bright_magenta")}', debug=True)    # run.py
printf(f'Installer URL: {url}', verbose=True)                                           # standalone scripts
```

Debug output goes to **stderr**, is dim, and is gated on a runtime flag. It never reaches stdout.

### Hook Script Output<a name="hook-script-output"></a>

Prek hook scripts print a bold level label followed by the filename, with detail lines indented eight spaces. Labels are
right-padded so filenames align:

```python
ERROR   = style('ERROR',   fg='bright_red',    bold=True)
INFO    = style('INFO',    fg='bright_blue',   bold=True)
WARNING = style('WARNING', fg='bright_yellow', bold=True)

printf(f'{ERROR}   {style(filename, fg="bright_white")}')
printf(error_detail, indent=8)

printf(f'{INFO}    {style(filename, fg="bright_white")}', verbose=True)
printf(style('Valid', fg='green'), indent=8, verbose=True)
```

`ERROR` takes three trailing spaces, `INFO` four, and `WARNING` one. `INFO` lines appear only in verbose mode. See
[`hooks/README.md`](hooks/README.md) for the hook inventory.

## Indentation<a name="indentation"></a>

| Level       | Spaces | Usage                                            |
| ----------- | ------ | ------------------------------------------------ |
| 0           | 0      | Top-level status and action headers              |
| 1           | 3      | Sub-items, detail messages, remediation hints    |
| 2           | 5      | Nested details, indented command output          |
| 3           | 7      | Deep diagnostic output                           |
| Hook detail | 8      | Detail lines under a hook `ERROR` / `INFO` label |

## Argparse Conventions<a name="argparse-conventions"></a>

- Use `RawTextHelpFormatter` with `max_help_position=50`. It preserves newlines and keeps ANSI-styled help intact.
- Pass `add_help=False` and re-add `-h/--help` in a final "Other options" group, so it always lists last.
- Define a typed `Args(argparse.Namespace)` subclass and parse with `parser.parse_args(argv, namespace=Args())`.
- Declare each option group in its own local function, then call it immediately.
- Annotate help text with `arg_note()` for env vars and defaults.

```python
parser = argparse.ArgumentParser(
    description='Script description',
    formatter_class=functools.partial(argparse.RawTextHelpFormatter, max_help_position=50),
    add_help=False,
)

def add_output_opts() -> None:
    output_opts = parser.add_argument_group('Output options')
    output_opts.add_argument(
        '-v', '--verbose',
        action='store_true',
        default=False,
        help=' '.join([
            'Enable verbose output',
            arg_note('env var', 'MYSCRIPT_VERBOSE'),
            arg_note('default', repr(False), color='bright_red'),
        ]),
    )
add_output_opts()

def add_other_opts() -> None:
    other_opts = parser.add_argument_group('Other options')
    other_opts.add_argument('-h', '--help', action='help', default=argparse.SUPPRESS,
                            help='Show this help message and exit')
add_other_opts()
```

`run.py` commands follow the same shape inside `Command.add_arguments()`; see
[`.ctx/CONVENTIONS.md`](../.ctx/CONVENTIONS.md).

## Script Skeleton<a name="script-skeleton"></a>

Section layout for a new standalone script. Paste the helper blocks from `run.py` into the "Formatting / logging"
section; do not retype them.

```python
#!/usr/bin/env python3
"""
Brief description of what this script does.
"""
from __future__ import annotations

import argparse
import functools
import re
import sys
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from typing import Union

if TYPE_CHECKING:
    from collections.abc import Sequence

# ====================================================================================================
# Types
# ====================================================================================================

PathLike   = Union[Path, str]
StyleColor = Union[int, tuple[int, int, int], str]

VERBOSE: bool = False

# ====================================================================================================
# Formatting / logging
# ====================================================================================================

# style(), unstyle(), folduser(), printf() (+ pathstyle(), arg_note() if used), copied from run.py

# ====================================================================================================
# Command-line arguments
# ====================================================================================================

class Args(argparse.Namespace):
    """
    :class:`argparse.Namespace` annotated with the args supported by this script.
    """
    verbose: bool


def parse_args(argv: Sequence[str] | None = None) -> Args:
    """
    Build the argument parser and parse command-line args.

    :param argv: command-line arguments (default: ``sys.argv[1:]``)
    :return: parsed :class:`Args`
    """
    global VERBOSE
    parser = argparse.ArgumentParser(...)  # see Argparse Conventions
    args = parser.parse_args(argv, namespace=Args())
    VERBOSE = args.verbose
    return args

# ====================================================================================================
# Core script
# ====================================================================================================

def main(argv: Sequence[str] | None = None) -> int:
    """
    Main entry point.

    :param argv: command-line arguments (default: ``sys.argv[1:]``)
    :return: 0 on success, non-zero on failure
    """
    args = parse_args(argv)
    return 0


if __name__ == '__main__':
    sys.exit(main())
```

Section headers are boxed comments 100 columns wide (see
[`.claude/rules/python-style.md`](../.claude/rules/python-style.md)). Scripts executed directly omit `__all__`.
