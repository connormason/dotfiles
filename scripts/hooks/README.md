[Project Root](../../README.md) > [Scripts](../README.md) > **Hook Scripts**

---

# Hook Scripts

Custom pre-commit hook scripts for checks and transforms not covered by standard hooks. All four scripts follow the same
interface contract as `pre-commit`: they accept a list of filenames as positional arguments and exit `0` on success or
non-zero on failure. They are wired into [`.pre-commit-config.yaml`](../../.pre-commit-config.yaml) as `local` repo
hooks and run via `prek` / `make pre`. Each is a self-contained PEP 723 script, so `uv run` resolves any dependencies in
isolation.

<!-- mdformat-toc start --slug=github --maxlevel=3 --minlevel=2 -->

- [Scripts](#scripts)
- [Pre-Commit Wiring](#pre-commit-wiring)
- [`check-json5.py`](#check-json5py)
  - [Synopsis](#synopsis)
  - [Options](#options)
  - [Behavior](#behavior)
  - [Exit Codes](#exit-codes)
  - [Pre-Commit Integration](#pre-commit-integration)
- [`check-pkl.py`](#check-pklpy)
  - [Synopsis](#synopsis-1)
  - [Options](#options-1)
  - [Behavior](#behavior-1)
  - [Exit Codes](#exit-codes-1)
  - [Pre-Commit Integration](#pre-commit-integration-1)
- [`format-pkl.py`](#format-pklpy)
  - [Synopsis](#synopsis-2)
  - [Options](#options-2)
  - [Behavior](#behavior-2)
  - [Exit Codes](#exit-codes-2)
  - [Pre-Commit Integration](#pre-commit-integration-2)
- [`sort-json-array.py`](#sort-json-arraypy)
  - [Synopsis](#synopsis-3)
  - [Options](#options-3)
  - [Behavior](#behavior-3)
  - [Exit Codes](#exit-codes-3)
  - [Pre-Commit Integration](#pre-commit-integration-3)

<!-- mdformat-toc end -->

## Scripts<a name="scripts"></a>

| Script                                     | What it does                                           | Hook id           | Priority          |
| ------------------------------------------ | ------------------------------------------------------ | ----------------- | ----------------- |
| [`check-json5.py`](#check-json5py)         | Validate JSON5 file syntax via `pyjson5`               | `check-json5`     | 10 (check phase)  |
| [`check-pkl.py`](#check-pklpy)             | Validate Pkl files by running `pkl eval --format yaml` | `check-pkl`       | 10 (check phase)  |
| [`format-pkl.py`](#format-pklpy)           | Auto-format Pkl files via `pkl format`                 | `format-pkl`      | 35 (format phase) |
| [`sort-json-array.py`](#sort-json-arraypy) | Sort a top-level JSON array of objects by a key        | `sort-json-array` | 30 (sort phase)   |

> [!NOTE]
> this repository does not currently contain any `.json5`, `.pkl`, or `keybindings.json` files, so all four hooks are
> staged for future use. Each is scoped so it matches nothing today and fires automatically the moment a matching file
> lands.

## Pre-Commit Wiring<a name="pre-commit-wiring"></a>

All four hooks are declared as `repo: local` entries in [`.pre-commit-config.yaml`](../../.pre-commit-config.yaml),
slotted into the repository's priority scheme. The relevant stanzas are:

```yaml
  - repo: local
    hooks:
      - id: check-json5
        name: '[check]  json5 syntax'
        priority: 10
        entry: scripts/hooks/check-json5.py
        language: python
        files: .*\.json5$

      - id: check-pkl
        name: '[check]  pkl syntax'
        priority: 10
        entry: scripts/hooks/check-pkl.py
        language: python
        files: .*\.pkl$
        types: [file]

  - repo: local
    hooks:
      - id: sort-json-array
        name: '[format] sorting (keybindings.json)'
        priority: 30
        stages: [pre-commit]
        entry: scripts/hooks/sort-json-array.py
        language: python
        files: .*keybindings\.json$
        args: [--key, command]

  - repo: local
    hooks:
      - id: format-pkl
        name: '[format] pkl (pkl format)'
        priority: 35
        stages: [pre-commit]    # skipped in CI
        entry: scripts/hooks/format-pkl.py
        language: python
        files: .*\.pkl$
        types: [file]
```

**Priority scheme** used across the whole config:

| Priority band | Phase             | Notes                                                                     |
| ------------- | ----------------- | ------------------------------------------------------------------------- |
| 0–6           | Dependency sync   | `uv-lock`, `uv-sync`, `uv-export`, `sync-with-uv`, `sync-pre-commit-deps` |
| 10            | Read-only checks  | Run in parallel; `check-json5`, `check-pkl` live here                     |
| 20–23         | Whitespace fixers | `fix-byte-order-marker`, `end-of-file-fixer`, `trailing-whitespace`, etc. |
| 30–35         | Formatters        | `keep-sorted`, `sort-json-array` (30); `shfmt`, `format-pkl`, etc. (35)   |
| 40            | Linters           | `ruff`, `mypy`, `yamllint`, `shellcheck`, `codespell`                     |

The `format-pkl` hook carries `stages: [pre-commit]` so it is skipped when the config is run in CI (`manual` stage).
`check-pkl` and `check-json5` run in all stages. `sort-json-array` runs at priority 30 (before the priority-35
`pretty-format-json` formatter) so a reordered array is normalized once and surfaces in the diff to re-stage rather than
landing silently.

Both Pkl hooks are tolerant of environments where `pkl` is not installed: by default they print a warning and exit `0`.
Pass `--require-pkl` to make the missing binary a hard failure.

---

## `check-json5.py`<a name="check-json5py"></a>

### Synopsis<a name="synopsis"></a>

Validates that every supplied `.json5` file parses successfully via `pyjson5`. Declared as a PEP 723 inline-script with
`pyjson5` as a dependency so `uv run` can execute it in isolation.

```
python3 scripts/hooks/check-json5.py [OPTIONS] [FILENAMES...]
```

### Options<a name="options"></a>

| Flag              | Description                                       | Default |
| ----------------- | ------------------------------------------------- | ------- |
| `FILENAMES`       | One or more `.json5` files to validate            | —       |
| `-v`, `--verbose` | Print a per-file `INFO` line for every valid file | off     |
| `-h`, `--help`    | Show help and exit                                | —       |

### Behavior<a name="behavior"></a>

For each filename:

1. Opens the file and calls `pyjson5.load()`.
2. On `Json5DecoderException` — prints `ERROR <filename>` followed by the exception class and message (indented),
   records failure.
3. On any other exception — prints `ERROR <filename>` followed by `Unable to decode JSON5: <exc>`.
4. On success with `--verbose` — prints `INFO <filename>` followed by `Valid JSON5`.

All output is ANSI-colored. The script exits non-zero if any file fails.

### Exit Codes<a name="exit-codes"></a>

| Code | Meaning                                |
| ---- | -------------------------------------- |
| `0`  | All files valid (or no files supplied) |
| `1`  | One or more files failed to parse      |

### Pre-Commit Integration<a name="pre-commit-integration"></a>

```yaml
  - id: check-json5
    entry: scripts/hooks/check-json5.py
    language: python
    files: .*\.json5$
```

pre-commit passes all staged `.json5` files as positional arguments. The `language: python` runtime means pre-commit
manages the `pyjson5` dependency automatically using the inline PEP 723 metadata.

---

## `check-pkl.py`<a name="check-pklpy"></a>

### Synopsis<a name="synopsis-1"></a>

Validates Pkl configuration files by running `pkl eval --format yaml` against each file. If `pkl` is not found on `PATH`
the script warns and exits `0` (non-blocking) unless `--require-pkl` is set.

```
python3 scripts/hooks/check-pkl.py [OPTIONS] [FILENAMES...]
```

### Options<a name="options-1"></a>

#### Positional

| Argument    | Description                          |
| ----------- | ------------------------------------ |
| `FILENAMES` | One or more `.pkl` files to validate |

#### Pkl executable options

| Flag                | Description                                                        | Default                      |
| ------------------- | ------------------------------------------------------------------ | ---------------------------- |
| `--require-pkl`     | Exit non-zero if `pkl` binary not found (default: warn and exit 0) | off                          |
| `--executable PATH` | Path to `pkl` binary                                               | `pkl` (resolved from `PATH`) |

#### Output options

| Flag                          | Description                                             | Default  |
| ----------------------------- | ------------------------------------------------------- | -------- |
| `-v`, `--verbose`             | Print per-file `INFO` line for valid files              | off      |
| `--dump-yaml`                 | Print the YAML output generated by `pkl eval` to stdout | off      |
| `--color never\|auto\|always` | ANSI color control (forwarded to `pkl eval --color`)    | `always` |

#### Execution options

| Flag                              | Description                                                     | Default |
| --------------------------------- | --------------------------------------------------------------- | ------- |
| `-t SECONDS`, `--timeout SECONDS` | Per-file evaluation timeout (forwarded to `pkl eval --timeout`) | none    |

#### Package options

| Flag         | Description                                                   | Default |
| ------------ | ------------------------------------------------------------- | ------- |
| `--no-cache` | Disable Pkl package cache (passes `--no-cache` to `pkl eval`) | off     |

#### Other

| Flag           | Description        |
| -------------- | ------------------ |
| `-h`, `--help` | Show help and exit |

### Behavior<a name="behavior-1"></a>

1. Checks `shutil.which(args.executable)`. If not found: warn and return `0`, or error and return `1` if `--require-pkl`
   is set.
2. Builds the base command: `pkl eval --format yaml [--color ...] [--timeout ...] [--no-cache]`.
3. For each file, runs the command via `subprocess.run(check=True, capture_output=True)`.
4. On `CalledProcessError` — prints `ERROR <filename>` with the stderr content (strips the redundant `–– Pkl Error ––`
   header that `pkl` emits).
5. On success with `--verbose` — prints `INFO <filename>` followed by `Valid Pkl`.
6. With `--dump-yaml` — prints the evaluated YAML output below the per-file status line.

### Exit Codes<a name="exit-codes-1"></a>

| Code | Meaning                                                                                 |
| ---- | --------------------------------------------------------------------------------------- |
| `0`  | All files valid, or `pkl` not installed (without `--require-pkl`), or no files supplied |
| `1`  | One or more files failed validation, or `pkl` not found with `--require-pkl`            |

### Pre-Commit Integration<a name="pre-commit-integration-1"></a>

```yaml
  - id: check-pkl
    entry: scripts/hooks/check-pkl.py
    language: python
    files: .*\.pkl$
    types: [file]
```

---

## `format-pkl.py`<a name="format-pklpy"></a>

### Synopsis<a name="synopsis-2"></a>

Auto-formats Pkl files in-place using `pkl format`. Detects files that need formatting (exit code `11` from
`pkl format --diff-name-only`) and rewrites them with `--write`. Reports `MODIFIED` or `UNMODIFIED` per file. If `pkl`
is not on `PATH`, warns and exits `0` unless `--require-pkl` is set.

```
python3 scripts/hooks/format-pkl.py [OPTIONS] [FILENAMES...]
```

### Options<a name="options-2"></a>

#### Positional

| Argument    | Description                        |
| ----------- | ---------------------------------- |
| `FILENAMES` | One or more `.pkl` files to format |

#### Pkl executable options

| Flag                | Description                             | Default                      |
| ------------------- | --------------------------------------- | ---------------------------- |
| `--require-pkl`     | Exit non-zero if `pkl` binary not found | off                          |
| `--executable PATH` | Path to `pkl` binary                    | `pkl` (resolved from `PATH`) |

#### Grammar options

| Flag                     | Description                                                      | Default |
| ------------------------ | ---------------------------------------------------------------- | ------- |
| `--grammar-version 1\|2` | Pkl grammar compatibility version (`1` = 0.25–0.29, `2` = 0.30+) | `2`     |

#### Output options

| Flag              | Description                                              | Default |
| ----------------- | -------------------------------------------------------- | ------- |
| `-v`, `--verbose` | Print `UNMODIFIED` line for files that needed no changes | off     |
| `-h`, `--help`    | Show help and exit                                       | —       |

### Behavior<a name="behavior-2"></a>

1. Checks `shutil.which(args.executable)`. If not found: warn and return `0`, or error and return `1` if
   `--require-pkl`.
2. Builds the base command: `pkl format --diff-name-only [--grammar-version N]`.
3. For each file:
   - Runs `pkl format --diff-name-only <file>`. Exit `0` means already formatted; exit `11` means the file needs
     reformatting.
   - On exit `11` — re-runs with `--write` to reformat in-place, prints `MODIFIED <filename>`.
   - On any other non-zero exit — prints `ERROR <filename>` with stderr (suppressing the generic
     `An error occurred during formatting.` line), and records the exit code.
4. With `--verbose`, prints `UNMODIFIED <filename>` for files that required no changes.

The exit code of the hook is the maximum non-zero return code seen across all files, or `0` if all succeeded.

### Exit Codes<a name="exit-codes-2"></a>

| Code     | Meaning                                                                                               |
| -------- | ----------------------------------------------------------------------------------------------------- |
| `0`      | All files formatted or already correct, or `pkl` not installed (without `--require-pkl`), or no files |
| `1`      | `pkl` not found with `--require-pkl`, or an unexpected exception occurred                             |
| `N` (>0) | Maximum `pkl format` exit code across all failing files                                               |

### Pre-Commit Integration<a name="pre-commit-integration-2"></a>

```yaml
  - id: format-pkl
    entry: scripts/hooks/format-pkl.py
    language: python
    files: .*\.pkl$
    types: [file]
    stages: [pre-commit]  # not run in CI
```

The `stages: [pre-commit]` restriction means this hook only runs during interactive `git commit` (and `make pre`). CI
pipelines run `check-pkl` (read-only) instead of attempting in-place formatting.

---

## `sort-json-array.py`<a name="sort-json-arraypy"></a>

### Synopsis<a name="synopsis-3"></a>

Sorts a top-level JSON array of objects in-place by the value of a chosen object key. Pure-stdlib PEP 723 script (no
dependencies). The file is rewritten only when the sorted result differs from the original.

```
python3 scripts/hooks/sort-json-array.py [OPTIONS] [FILENAMES...]
```

### Options<a name="options-3"></a>

| Flag              | Description                                           | Default   |
| ----------------- | ----------------------------------------------------- | --------- |
| `FILENAMES`       | One or more JSON files (top-level array of objects)   | —         |
| `-k`, `--key`     | Object key whose value each array entry is sorted by  | `command` |
| `--indent`        | Number of spaces to indent the rewritten JSON by      | `4`       |
| `-v`, `--verbose` | Print a per-file `INFO` line for already-sorted files | off       |
| `-h`, `--help`    | Show help and exit                                    | —         |

### Behavior<a name="behavior-3"></a>

For each filename:

1. Reads and parses the file as JSON.
2. On a decode error, or if the top level is not an array of objects — prints `ERROR <filename>` with the reason,
   records failure.
3. Stably sorts the array by `entry.get(key, '')` (entries missing the key sort first; equal keys keep their original
   relative order).
4. Re-serializes and, if the result differs, rewrites the file in-place and prints `INFO <filename>` /
   `Sorted array by '<key>'`.
5. If already sorted — with `--verbose`, prints `INFO <filename>` / `Already sorted by '<key>'`.

### Exit Codes<a name="exit-codes-3"></a>

| Code | Meaning                                                                           |
| ---- | --------------------------------------------------------------------------------- |
| `0`  | Every file already sorted (or no files supplied)                                  |
| `1`  | One or more files were rewritten, failed to parse, or are not an array of objects |

### Pre-Commit Integration<a name="pre-commit-integration-3"></a>

```yaml
  - id: sort-json-array
    entry: scripts/hooks/sort-json-array.py
    language: python
    args: [--key, command]
    files: .*keybindings\.json$
```

Scoped to any `keybindings.json`, this keeps such a file's array ordered by each entry's `command` value. It runs at
priority 30 (before the priority-35 `pretty-format-json` formatter), so a reordered file is normalized once and surfaces
in the diff to re-stage rather than landing silently. The default `--key command` also makes the hook usable as-is for
other keybindings-style JSON.

---

> **See also**: [`scripts/env/`](../env/README.md) for the Python environment utilities used during development.
