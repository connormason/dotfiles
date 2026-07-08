[Project Root](../../README.md) > [Scripts](../README.md) > **Env Scripts**

---

# Env Scripts

Standalone Python utilities for inspecting, loading, and entering Python virtual environments. All three scripts are
zero-dependency where possible (standard library only) or declare their dependencies inline via PEP 723 script metadata,
making them safe to run without a pre-activated environment.

<!-- mdformat-toc start --slug=github --maxlevel=3 --minlevel=2 -->

- [Env Scripts](#env-scripts)
  - [Scripts](#scripts)
  - [`loadenv.py`](#loadenvpy)
    - [Synopsis](#synopsis)
    - [Options](#options)
    - [Behavior](#behavior)
    - [Exit Codes](#exit-codes)
    - [Usage Examples](#usage-examples)
  - [`python_diagnostic.py`](#python_diagnosticpy)
    - [Synopsis](#synopsis-1)
    - [Options](#options-1)
    - [Behavior](#behavior-1)
    - [Exit Codes](#exit-codes-1)
    - [Usage Examples](#usage-examples-1)
  - [`venvshell.py`](#venvshellpy)
    - [Synopsis](#synopsis-2)
    - [Options](#options-2)
      - [Environment selection](#environment-selection)
      - [Environment discovery (when no explicit path given)](#environment-discovery-when-no-explicit-path-given)
      - [Output](#output)
    - [Behavior](#behavior-2)
    - [Exit Codes](#exit-codes-2)
    - [Usage Examples](#usage-examples-2)

<!-- mdformat-toc end -->

## Scripts<a name="scripts"></a>

| Script                                         | What it does                                                     | Typical usage                                |
| ---------------------------------------------- | ---------------------------------------------------------------- | -------------------------------------------- |
| [`loadenv.py`](#loadenvpy)                     | Parse `.env` files; emit JSON, shell exports, or key-value pairs | `eval "$(python3 loadenv.py --export .env)"` |
| [`python_diagnostic.py`](#python_diagnosticpy) | Collect a full Python-environment diagnostic report              | `python3 python_diagnostic.py`               |
| [`venvshell.py`](#venvshellpy)                 | Spawn an interactive subshell with a virtualenv activated        | `python3 venvshell.py`                       |

---

## `loadenv.py`<a name="loadenvpy"></a>

### Synopsis<a name="synopsis"></a>

Standalone `.env` file parser. Parses a dotenv file and writes its contents to stdout in one of three formats. Parser
logic is vendored from `ezcli.dotenv` v1.6.13 and has no external dependencies.

```
python3 scripts/env/loadenv.py [OPTIONS] [FILE]
```

If `FILE` is omitted the script walks from the current working directory upward until it finds a `.env` file.

### Options<a name="options"></a>

| Flag               | Description                                                            | Default                       |
| ------------------ | ---------------------------------------------------------------------- | ----------------------------- |
| `FILE`             | Path to `.env` file                                                    | auto-discover from CWD upward |
| `-j`, `--json`     | Output as JSON object                                                  | yes (default mode)            |
| `-e`, `--export`   | Output as `export KEY="value"` statements                              | —                             |
| `-p`, `--pairs`    | Output as `KEY=value` pairs                                            | —                             |
| `--override`       | `.env` values override existing env vars during `${VAR}` interpolation | off                           |
| `--no-interpolate` | Disable `${VAR}` variable expansion                                    | interpolation on              |
| `-q`, `--quiet`    | Suppress warnings and errors to stderr                                 | off                           |
| `-v`, `--version`  | Print version and exit                                                 | —                             |
| `-h`, `--help`     | Show help and exit                                                     | —                             |

### Behavior<a name="behavior"></a>

1. Resolves the target file (explicit path or CWD-upward walk).
2. Parses each line into key-value `Binding` objects, handling single-quoted, double-quoted, and unquoted values, inline
   comments, `export` prefixes, and blank lines.
3. Optionally resolves `${NAME}` and `${NAME:-default}` variable references against already-seen dotenv values and
   `os.environ`.
4. Formats and writes the result to stdout.

### Exit Codes<a name="exit-codes"></a>

| Code | Meaning                                            |
| ---- | -------------------------------------------------- |
| `0`  | Success (no parse errors)                          |
| `1`  | File not found or could not be opened              |
| `2`  | Success, but one or more lines could not be parsed |

### Usage Examples<a name="usage-examples"></a>

```bash
# Source variables into the current shell
eval "$(python3 scripts/env/loadenv.py --export .env)"

# Inspect parsed values as JSON
python3 scripts/env/loadenv.py --json .env

# Emit raw KEY=value pairs (useful for piping into other tools)
python3 scripts/env/loadenv.py --pairs .env

# Disable variable interpolation
python3 scripts/env/loadenv.py --no-interpolate .env

# Suppress parse warnings while still failing on missing file
python3 scripts/env/loadenv.py -q .env || echo "file not found"
```

---

## `python_diagnostic.py`<a name="python_diagnosticpy"></a>

### Synopsis<a name="synopsis-1"></a>

Collects and formats a comprehensive Python-environment diagnostic report covering system info, all Python executables
on `PATH`, virtual-environment state, package managers (`pip`, `uv`, `hatch`), key environment variables, `sys.path`,
common installation locations, and installed packages.

```
python3 scripts/env/python_diagnostic.py [OPTIONS]
```

### Options<a name="options-1"></a>

| Flag                               | Description                                           | Default                             |
| ---------------------------------- | ----------------------------------------------------- | ----------------------------------- |
| `--max-installed-packages NUM`     | Truncate the installed-packages list to `NUM` entries | no limit                            |
| `-s`, `--save`                     | Save output to a timestamped file instead of printing | off                                 |
| `-j`, `--json`                     | Output raw JSON instead of formatted text             | off                                 |
| `-o FILEPATH`, `--output FILEPATH` | Explicit output file path (implies `--save`)          | `python_diagnostic_<timestamp>.txt` |
| `-h`, `--help`                     | Show help and exit                                    | —                                   |

### Behavior<a name="behavior-1"></a>

The script runs a collection phase followed by a formatting/output phase.

**Collection phase** — `collect_diagnostics()` gathers:

- `system` — `platform.platform()`, `sw_vers`, `uname -a`, Python version and implementation
- `python_executables` — resolves `python`, `python3`, `python3.9`–`python3.13` from `PATH` via `shutil.which`
- `virtual_env` — `VIRTUAL_ENV`, `CONDA_DEFAULT_ENV`, `sys.prefix` / `sys.base_prefix` / `sys.real_prefix`
- `package_managers` — pip path/version, `uv` path/version/managed-Python list (`uv python list --json`), hatch
  path/version/environments (`hatch env show --json`)
- `environment_variables` — a curated allowlist of non-sensitive vars (e.g. `PYTHONPATH`, `UV_INDEX_URL`, `PATH`)
- `python_paths` — `sys.executable`, `sys.path`, site-packages entries
- `common_locations` — existence/symlink check for system Python, Homebrew, pyenv, `~/.local/bin`, etc.
- `installed_packages` — `uv pip list --format=json` (falls back to `pip list`)

**Output phase** — either `format_diagnostic_output()` (human-readable text) or `json.dumps()` (structured JSON),
written to stdout or a file.

### Exit Codes<a name="exit-codes-1"></a>

| Code | Meaning                                                             |
| ---- | ------------------------------------------------------------------- |
| `0`  | Always (diagnostic failures are reported inline, not as exit codes) |

### Usage Examples<a name="usage-examples-1"></a>

```bash
# Print to stdout (default)
python3 scripts/env/python_diagnostic.py

# Limit installed package listing to avoid wall-of-text
python3 scripts/env/python_diagnostic.py --max-installed-packages 20

# Save full JSON report for sharing or diffing
python3 scripts/env/python_diagnostic.py --json --output /tmp/pydiag.json

# Auto-timestamped text file
python3 scripts/env/python_diagnostic.py --save
# => Saves to python_diagnostic_20240101_120000.txt
```

---

## `venvshell.py`<a name="venvshellpy"></a>

### Synopsis<a name="synopsis-2"></a>

Spawns an interactive subshell with a Python virtual environment activated. Supports `bash`, `zsh`, and `fish`. Handles
shell history preservation for zsh (works around `ZDOTDIR` override side effects), temp-dir cleanup via `atexit`, and
fish `activate.fish` sourcing. Also supports hatch-managed environments via `hatch env find`.

```
python3 scripts/env/venvshell.py [OPTIONS] [PATH]
```

### Options<a name="options-2"></a>

#### Environment selection

| Flag          | Description                                              | Env var override      | Default |
| ------------- | -------------------------------------------------------- | --------------------- | ------- |
| `PATH`        | Positional path to venv directory                        | `VENVSHELL_PATH`      | —       |
| `--path PATH` | Path to venv directory (named alternative to positional) | `VENVSHELL_PATH`      | —       |
| `--hatch ENV` | Hatch environment name                                   | `VENVSHELL_HATCH_ENV` | —       |

#### Environment discovery (when no explicit path given)

| Flag                                       | Description                                  | Env var override           | Default |
| ------------------------------------------ | -------------------------------------------- | -------------------------- | ------- |
| `--discover` / `--no-discover`             | Enable/disable auto-discovery                | `VENVSHELL_DISCOVER`       | `True`  |
| `--discover-hatch` / `--no-discover-hatch` | Include hatch environments in auto-discovery | `VENVSHELL_DISCOVER_HATCH` | `True`  |

#### Output

| Flag              | Description                                                                |
| ----------------- | -------------------------------------------------------------------------- |
| `-v`, `--verbose` | Print debug messages to stderr (discovery steps, shell args, env vars set) |
| `-h`, `--help`    | Show help and exit                                                         |

### Behavior<a name="behavior-2"></a>

**Resolution order** (first match wins):

1. Explicit `--path PATH` or positional `PATH` argument
2. Explicit `--hatch ENV` (runs `hatch env find ENV`)
3. Auto-discovered `.venv/` or `venv/` directory (walks up from CWD)
4. Auto-discovered default hatch environment (`hatch env find`)

**Shell activation** — launches via `subprocess.run` (not `os.execvpe`) so `atexit` cleanup of temp directories runs on
exit:

- **bash** — writes a temp `.bashrc` that sources the user's real dotfiles then `source activate`
- **zsh** — creates a temp `ZDOTDIR`, symlinks all non-`.zshrc` dotfiles from the real `ZDOTDIR`, generates a custom
  `.zshrc` that sources the real `.zshrc`, activates the venv, then hard-codes `HISTFILE` to the resolved real history
  file path (prevents history loss when `ZDOTDIR` is overridden)
- **fish** — passes `-C "source activate.fish"` to the shell process
- **other** — activates via env vars only (`VIRTUAL_ENV`, `PATH` prepend) with a warning

**Guard rails** — if `VIRTUAL_ENV` is already set, the script exits with a warning rather than nesting environments.

### Exit Codes<a name="exit-codes-2"></a>

| Code | Meaning                                                                    |
| ---- | -------------------------------------------------------------------------- |
| `0`  | Venv activated and subshell exited normally, or environment already active |
| `1`  | Existing (different) environment already active                            |
| `64` | Invalid arguments (`EX_USAGE`)                                             |
| `65` | Venv directory is broken/invalid (`EX_DATAERR`)                            |
| `69` | No virtual environment found (`EX_UNAVAILABLE`)                            |
| `90` | Shell activation failed                                                    |

### Usage Examples<a name="usage-examples-2"></a>

```bash
# Auto-discover venv in current project
python3 scripts/env/venvshell.py

# Explicitly specify a venv path
python3 scripts/env/venvshell.py .venv
python3 scripts/env/venvshell.py --path /path/to/project/.venv

# Use a hatch-managed environment
python3 scripts/env/venvshell.py --hatch default

# Disable hatch discovery fallback (only look for .venv/ or venv/ dirs)
python3 scripts/env/venvshell.py --no-discover-hatch

# Debug discovery steps
python3 scripts/env/venvshell.py --verbose

# Hard-code default venv path via environment variable (e.g. in shell profile)
export VENVSHELL_PATH=~/projects/myapp/.venv
python3 scripts/env/venvshell.py
```
