---
globs: '**/*.py'
---

# Script Styling & Console Output Rules

> Conventions for formatting console output in standalone CLI scripts that produce styled terminal output. Adopt the
> subset relevant to a given script; a project may point at its own reference implementation in a project-level rule.

<!-- mdformat-toc start --slug=github --maxlevel=3 --minlevel=2 -->

- [Core Infrastructure Functions](#core-infrastructure-functions)
- [Color Theme (Semantic Roles)](#color-theme-semantic-roles)
- [Status Indicators](#status-indicators)
- [Tool Status Line Format](#tool-status-line-format)
- [Debug / Verbose Output](#debug--verbose-output)
- [Indentation Conventions](#indentation-conventions)
- [Argparse Conventions](#argparse-conventions)
  - [Formatter class](#formatter-class)
  - [Typed namespace](#typed-namespace)
  - [Option groups](#option-groups)
  - [Manual help option](#manual-help-option)
- [Hook Script Output Format](#hook-script-output-format)

<!-- mdformat-toc end -->

## Core Infrastructure Functions<a name="core-infrastructure-functions"></a>

A script that produces styled output should define (or import) these primitives. Use these canonical names:

| Function     | Purpose                                                                   |
| ------------ | ------------------------------------------------------------------------- |
| `style()`    | Apply ANSI escape codes to text. Returns a styled string (does not print) |
| `printf()`   | Print styled text with indent/debug/verbose support                       |
| `folduser()` | Replace `$HOME` with `~` in path strings for display                      |
| `unstyle()`  | Strip all ANSI escape sequences from a string                             |

Use `unstyle()` (not `remove_ansi()`) as the canonical name for ANSI stripping.

## Color Theme (Semantic Roles)<a name="color-theme-semantic-roles"></a>

Apply these color assignments consistently — they are the visual language of the output.

| Semantic role                     | fg color         | Modifiers   |
| --------------------------------- | ---------------- | ----------- |
| **File paths**                    | `magenta`        | —           |
| **Commands / executables**        | `bright_magenta` | —           |
| **CLI option names**              | `yellow`         | —           |
| **Tool names (status lines)**     | `white`          | `bold=True` |
| **Version numbers**               | `bright_cyan`    | —           |
| **Location annotations**          | —                | `dim=True`  |
| **Section headers / labels**      | `bright_white`   | `bold=True` |
| **Informational body text**       | `bright_white`   | —           |
| **Error text**                    | `bright_red`     | —           |
| **Error label**                   | `bright_red`     | `bold=True` |
| **Warning text**                  | `bright_yellow`  | —           |
| **Success text**                  | `bright_green`   | —           |
| **Action headers**                | `bright_cyan`    | —           |
| **Debug / verbose text**          | `bright_white`   | `dim=True`  |
| **Supplementary / parenthetical** | —                | `dim=True`  |

## Status Indicators<a name="status-indicators"></a>

Status messages use an emoji prefix; the emoji carries the semantic weight and the text color reinforces it.

| Emoji   | Meaning                      | Text color                     |
| ------- | ---------------------------- | ------------------------------ |
| 🟢      | Available / active / healthy | `bright_green` or neutral      |
| 🔴      | Missing / failed / fatal     | `bright_red`                   |
| 🟡      | Warning / caution            | `bright_yellow`                |
| ❌      | Error (inline)               | `bright_red`                   |
| ✅      | Success / done               | `bright_green`                 |
| ⏬      | Downloading                  | `bright_cyan`                  |
| 💿      | Installing                   | `bright_cyan`                  |
| 💾      | Creating (env, artifact)     | `bright_cyan`                  |
| 🔎      | Analyzing / linting          | `bright_cyan`                  |
| 🧹      | Cleaning                     | `bright_cyan`                  |
| 📦      | Building                     | `bright_cyan`                  |
| 🖥       | Running tests                | `bright_cyan`                  |
| ⏩ / ⏪ | Entering / exiting context   | `bright_cyan` / `bright_white` |
| ⚠️      | Operation cancelled          | `yellow`                       |

**Action messages** (🔎, 🧹, 📦, etc.) always use `bright_cyan`.

## Tool Status Line Format<a name="tool-status-line-format"></a>

When reporting tool availability, use: `emoji  tool_name  version(padded)  @ folded_path`.

```python
printf(
    f'🟢 {style("python", fg="white", bold=True)}  '
    f'{style(version.ljust(8), fg="bright_cyan")} '
    f'{style(f"@ {folduser(exe)}", dim=True)}',
    indent=indent,
)
```

Pad version strings to 8 chars with `.ljust(8)` for alignment when listing multiple tools.

## Debug / Verbose Output<a name="debug--verbose-output"></a>

Route verbose/debug output to **stderr** so it never contaminates stdout. Two common patterns:

```python
# Flag-gated via printf:
printf("diagnostic message", debug=True)    # prints dim text to stderr when debug flag is on; else no-op

# Simpler standalone scripts:
def vprint(*args: Any, **kwargs: Any) -> None:
    if VERBOSE:
        print(*args, file=kwargs.pop('file', sys.stderr), **kwargs)
```

## Indentation Conventions<a name="indentation-conventions"></a>

- Top-level messages: `indent=0` (default)
- Sub-items / details: `indent=3`
- Nested details: `indent=5`
- Deep nesting: `indent=7`

## Argparse Conventions<a name="argparse-conventions"></a>

### Formatter class<a name="formatter-class"></a>

Use `RawTextHelpFormatter` with a widened `max_help_position`:

```python
parser = argparse.ArgumentParser(
    formatter_class=functools.partial(argparse.RawTextHelpFormatter, max_help_position=50),
    add_help=False,  # re-add manually in an "Other options" group
)
```

### Typed namespace<a name="typed-namespace"></a>

Define an `Args(argparse.Namespace)` subclass with annotated fields:

```python
class Args(argparse.Namespace):
    filenames: Sequence[str]
    verbose:   bool
```

### Option groups<a name="option-groups"></a>

Organize arguments into named groups, each defined in its own local function:

```python
def add_output_opts() -> None:
    output_opts = parser.add_argument_group('Output options')
    output_opts.add_argument('-v', '--verbose', action='store_true', help='Enable verbose output')
add_output_opts()
```

### Manual help option<a name="manual-help-option"></a>

Re-add `-h/--help` in an "Other options" group so it sorts last:

```python
def add_other_opts() -> None:
    other_opts = parser.add_argument_group('Other options')
    other_opts.add_argument('-h', '--help', action='help', default=argparse.SUPPRESS,
                            help='Show this help message and exit')
add_other_opts()
```

## Hook Script Output Format<a name="hook-script-output-format"></a>

Pre-commit hook scripts use aligned labels (right-padded so the filename column lines up); use 8 spaces for detail
lines:

```python
IDNT = ' ' * 8

print(f'{style("ERROR", fg="bright_red", bold=True)}   {style(filename, fg="bright_white")}')
print(f'{IDNT}{error_details}')

print(f'{style("INFO", fg="bright_blue", bold=True)}    {style(filename, fg="bright_white")}')
print(f'{IDNT}{style("Valid", fg="green")}')
```
