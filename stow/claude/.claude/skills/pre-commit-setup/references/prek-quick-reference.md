# prek Quick Reference

prek is a Rust-based reimplementation of pre-commit with native speed, built-in hooks, and additional features like glob
patterns, per-hook environment variables, and execution priority ordering.

Official docs: https://prek.j178.dev

<!-- mdformat-toc start --slug=github --maxlevel=3 --minlevel=2 -->

- [1. Configuration Format](#1-configuration-format)
  - [Recognized Filenames (precedence order)](#recognized-filenames-precedence-order)
  - [Top-Level Keys](#top-level-keys)
- [2. Repository Configuration](#2-repository-configuration)
  - [Four Repo Types](#four-repo-types)
  - [Inline Format](#inline-format)
  - [Array-of-Tables Format](#array-of-tables-format)
  - [meta Hooks](#meta-hooks)
- [3. Hook Configuration](#3-hook-configuration)
  - [Hook-Level Keys](#hook-level-keys)
  - [Glob Pattern Syntax (prek-only)](#glob-pattern-syntax-prek-only)
- [4. Common CLI Commands](#4-common-cli-commands)
  - [Install / Uninstall](#install--uninstall)
  - [Running](#running)
  - [Updates](#updates)
  - [Validation](#validation)
  - [Cache Management](#cache-management)
  - [Utilities](#utilities)
- [5. Built-in Hooks](#5-built-in-hooks)
  - [Usage Example](#usage-example)
- [6. Key Differences from pre-commit](#6-key-differences-from-pre-commit)
- [7. Environment Variables](#7-environment-variables)
- [8. Configuration Examples](#8-configuration-examples)
  - [Minimal: Remote Hooks Only](#minimal-remote-hooks-only)
  - [Zero-Network: Built-in Hooks Only](#zero-network-built-in-hooks-only)
  - [Python Project: ruff + Built-ins](#python-project-ruff--built-ins)
  - [Monorepo / Workspace Example](#monorepo--workspace-example)

<!-- mdformat-toc end -->

---

## 1. Configuration Format<a name="1-configuration-format"></a>

### Recognized Filenames (precedence order)<a name="recognized-filenames-precedence-order"></a>

| Priority | Filename                  | Format |
| -------- | ------------------------- | ------ |
| 1        | `prek.toml`               | TOML   |
| 2        | `.pre-commit-config.yaml` | YAML   |
| 3        | `.pre-commit-config.yml`  | YAML   |

Config discovery traverses upward from the current directory to the git repository boundary.

### Top-Level Keys<a name="top-level-keys"></a>

| Key                          | Type          | Default        | Notes                                       |
| ---------------------------- | ------------- | -------------- | ------------------------------------------- |
| `repos`                      | list          | — (required)   |                                             |
| `files`                      | regex or glob | none           | Global include filter                       |
| `exclude`                    | regex or glob | none           | Global exclude filter                       |
| `fail_fast`                  | boolean       | `false`        |                                             |
| `default_language_version`   | map           | none           |                                             |
| `default_stages`             | list          | all stages     |                                             |
| `default_install_hook_types` | list          | `[pre-commit]` |                                             |
| `minimum_prek_version`       | string        | unset          | **prek-only**                               |
| `orphan`                     | boolean       | `false`        | Isolate from parent configs — **prek-only** |

---

## 2. Repository Configuration<a name="2-repository-configuration"></a>

### Four Repo Types<a name="four-repo-types"></a>

| Type      | Description                                    | Notes         |
| --------- | ---------------------------------------------- | ------------- |
| URL       | Remote git repo with `rev` and `hooks`         |               |
| `local`   | Inline hook definitions, no network            |               |
| `meta`    | Built-in validation hooks (pre-commit project) |               |
| `builtin` | prek's fast Rust-native offline hooks          | **prek-only** |

### Inline Format<a name="inline-format"></a>

```toml
[[repos]]
repo = "https://github.com/pre-commit/pre-commit-hooks"
rev = "v6.0.0"
hooks = [
  { id = "trailing-whitespace" },
  { id = "end-of-file-fixer", args = ["--fix"] },
]
```

### Array-of-Tables Format<a name="array-of-tables-format"></a>

```toml
[[repos]]
repo = "local"

[[repos.hooks]]
id = "ruff"
name = "ruff"
language = "system"
entry = "python3 -m ruff check"
files = "\\.py$"
```

### meta Hooks<a name="meta-hooks"></a>

```toml
[[repos]]
repo = "meta"
hooks = [
  { id = "check-hooks-apply" },
  { id = "check-useless-excludes" },
  { id = "identity" },
]
```

---

## 3. Hook Configuration<a name="3-hook-configuration"></a>

### Hook-Level Keys<a name="hook-level-keys"></a>

| Key                       | Type          | Default | Notes                                             |
| ------------------------- | ------------- | ------- | ------------------------------------------------- |
| `id`                      | string        | —       | Required                                          |
| `name`                    | string        |         |                                                   |
| `entry`                   | string        |         |                                                   |
| `language`                | string        |         |                                                   |
| `alias`                   | string        |         | Alternative ID for `--hook`                       |
| `args`                    | list[string]  | `[]`    |                                                   |
| `files`                   | regex or glob |         | Glob via `{ glob: "..." }` — **prek-only syntax** |
| `exclude`                 | regex or glob |         | Glob via `{ glob: "..." }` — **prek-only syntax** |
| `types`                   | list          |         | AND logic — all types must match                  |
| `types_or`                | list          |         | OR logic — any type must match                    |
| `exclude_types`           | list          |         |                                                   |
| `always_run`              | boolean       | `false` |                                                   |
| `pass_filenames`          | boolean       | `true`  |                                                   |
| `stages`                  | list          |         |                                                   |
| `require_serial`          | boolean       | `false` |                                                   |
| `fail_fast`               | boolean       | `false` |                                                   |
| `verbose`                 | boolean       | `false` |                                                   |
| `log_file`                | string        |         |                                                   |
| `description`             | string        |         |                                                   |
| `language_version`        | string        |         | Supports semver specifiers in prek                |
| `additional_dependencies` | list[string]  | `[]`    |                                                   |
| `env`                     | map           |         | Per-hook environment variables — **prek-only**    |
| `priority`                | integer       |         | Execution order; lower runs first — **prek-only** |
| `minimum_prek_version`    | string        |         | **prek-only**                                     |

### Glob Pattern Syntax (prek-only)<a name="glob-pattern-syntax-prek-only"></a>

Use `{ glob: "..." }` in place of a regex string for `files` or `exclude`:

```toml
[[repos.hooks]]
id = "my-hook"
files = { glob = "src/**/*.py" }
exclude = { glob = "tests/**" }
```

---

## 4. Common CLI Commands<a name="4-common-cli-commands"></a>

### Install / Uninstall<a name="install--uninstall"></a>

```sh
prek install                     # Install git hooks
prek install -f                  # Force reinstall, overwrite existing hooks
prek install --prepare-hooks     # Install and prepare hook environments
prek install -t pre-push         # Install for a specific hook type
prek uninstall                   # Remove installed git hooks
```

### Running<a name="running"></a>

```sh
prek run                         # Run hooks on staged files
prek run <hook-id>               # Run a specific hook
prek run --all-files             # Run on all tracked files
prek run --files a.py b.py       # Run on specific files
prek run --from-ref HEAD~1 --to-ref HEAD   # Run on files changed between refs
prek run --hook-stage pre-push   # Run hooks for a specific stage
prek run --last-commit           # Run on files changed in last commit
prek run --directory path/       # Run from a specific directory
prek run --skip hook-id          # Skip a specific hook (also: PREK_SKIP env var)
prek list                        # List all configured hooks
```

### Updates<a name="updates"></a>

```sh
prek auto-update                 # Update all repos to latest rev
prek auto-update --bleeding-edge # Update to latest commit (not just tags)
prek auto-update --freeze        # Pin to exact commit hash
prek auto-update --repo URL      # Update only a specific repo
prek auto-update --dry-run       # Preview updates without applying
prek auto-update --cooldown-days 7  # Skip repos updated within N days
```

### Validation<a name="validation"></a>

```sh
prek validate-config             # Validate configuration file
prek validate-manifest           # Validate .pre-commit-hooks.yaml manifest
prek sample-config               # Print a sample configuration
prek try-repo URL                # Try hooks from a remote repo without installing
prek try-repo URL --rev v1.0.0   # Try a specific revision
```

### Cache Management<a name="cache-management"></a>

```sh
prek cache dir                   # Print cache directory path
prek cache gc                    # Garbage-collect unused environments
prek cache clean                 # Remove all cached environments
prek cache size                  # Print total cache disk usage
```

### Utilities<a name="utilities"></a>

```sh
prek self update                 # Update prek itself to latest version
prek util yaml-to-toml           # Convert .pre-commit-config.yaml to prek.toml
prek util list-builtins          # List all available builtin hook IDs
prek util identify <file>        # Show file type tags for a path
prek util init-template-dir      # Initialize a git template directory
```

---

## 5. Built-in Hooks<a name="5-built-in-hooks"></a>

Use `repo = "builtin"` to access these Rust-native hooks with no network dependency.

| Hook ID                                | Description                                   | Notable Args                                                                 |
| -------------------------------------- | --------------------------------------------- | ---------------------------------------------------------------------------- |
| `trailing-whitespace`                  | Remove trailing whitespace                    | `--markdown-linebreak-ext`, `--chars`                                        |
| `check-added-large-files`              | Prevent committing large files                | `--maxkb` (default: 500), `--enforce-all`                                    |
| `check-case-conflict`                  | Check for case-insensitive filename conflicts |                                                                              |
| `check-illegal-windows-names`          | Prevent filenames illegal on Windows          |                                                                              |
| `end-of-file-fixer`                    | Ensure files end with a newline               |                                                                              |
| `file-contents-sorter`                 | Sort lines in files                           | `--ignore-case`, `--unique`                                                  |
| `fix-byte-order-marker`                | Remove UTF-8 BOM                              |                                                                              |
| `check-json`                           | Validate JSON files                           |                                                                              |
| `check-json5`                          | Validate JSON5 files                          |                                                                              |
| `pretty-format-json`                   | Format and optionally sort JSON               | `--autofix`, `--indent`, `--no-ensure-ascii`, `--no-sort-keys`, `--top-keys` |
| `check-toml`                           | Validate TOML files                           |                                                                              |
| `check-vcs-permalinks`                 | Warn on non-permalink VCS links               | `--additional-github-domain`                                                 |
| `check-yaml`                           | Validate YAML files                           | `-m`/`--allow-multiple-documents`                                            |
| `check-xml`                            | Validate XML files                            |                                                                              |
| `mixed-line-ending`                    | Check or fix mixed line endings               | `--fix=auto\|no\|lf\|crlf\|cr`                                               |
| `check-symlinks`                       | Check for broken symlinks                     |                                                                              |
| `destroyed-symlinks`                   | Detect symlinks converted to regular files    |                                                                              |
| `check-merge-conflict`                 | Detect unresolved merge conflict markers      | `--assume-in-merge`                                                          |
| `detect-private-key`                   | Scan for private key material                 |                                                                              |
| `no-commit-to-branch`                  | Block commits to protected branches           | `-b`/`--branch`, `-p`/`--pattern`                                            |
| `check-executables-have-shebangs`      | Ensure executable scripts have shebangs       |                                                                              |
| `check-shebang-scripts-are-executable` | Ensure scripts with shebangs are executable   |                                                                              |

### Usage Example<a name="usage-example"></a>

```toml
[[repos]]
repo = "builtin"
hooks = [
  { id = "trailing-whitespace" },
  { id = "end-of-file-fixer" },
  { id = "check-yaml" },
  { id = "check-added-large-files", args = ["--maxkb=1024"] },
]
```

---

## 6. Key Differences from pre-commit<a name="6-key-differences-from-pre-commit"></a>

- **Glob patterns**: `files`/`exclude` accept `{ glob: "..." }` objects in addition to regex strings.
- **Per-hook environment**: `env` key sets environment variables scoped to a single hook, not globally.
- **Execution priority**: `priority` integer controls ordering within a stage; lower values run first; hooks at the same
  priority run in parallel.
- **Built-in Rust hooks**: `repo = "builtin"` runs 22 hooks natively with no network or interpreter required.
- **Workspace / monorepo mode**: prek supports workspace configuration for multi-project repositories.
- **Semver `language_version`**: Accepts semver specifiers; prek downloads the matching toolchain automatically.
- **Python environments via `uv`**: Uses `uv` instead of `virtualenv` for faster Python virtual environment creation.
- **Parallel execution**: Hooks at the same priority level run concurrently; controlled by `PREK_MAX_CONCURRENCY`.
- **`prek list`**: Lists all configured hooks with their IDs, names, and stages. No equivalent in pre-commit.
- **`prek util yaml-to-toml`**: Converts an existing `.pre-commit-config.yaml` to `prek.toml` format.
- **`prek cache` subcommands**: Fine-grained cache inspection and management (`dir`, `gc`, `clean`, `size`).
- **`prek self update`**: Self-updating binary; no external package manager needed.
- **`orphan` key**: Prevents config from inheriting settings from parent-directory configs.
- **`minimum_prek_version`**: Enforces a minimum prek version at the config and hook level.

---

## 7. Environment Variables<a name="7-environment-variables"></a>

| Variable               | Description                                | Values                    |
| ---------------------- | ------------------------------------------ | ------------------------- |
| `PREK_HOME`            | Override the prek data/cache directory     | Absolute path             |
| `PREK_COLOR`           | Control colored output                     | `auto`, `always`, `never` |
| `PREK_SKIP`            | Comma-separated hook IDs to skip           | `hook-id,other-id`        |
| `PREK_MAX_CONCURRENCY` | Maximum number of parallel hook executions | Integer                   |
| `PREK_NO_CONCURRENCY`  | Disable all parallel execution             | `1`, `true`               |

---

## 8. Configuration Examples<a name="8-configuration-examples"></a>

### Minimal: Remote Hooks Only<a name="minimal-remote-hooks-only"></a>

```toml
# prek.toml
[[repos]]
repo = "https://github.com/pre-commit/pre-commit-hooks"
rev = "v6.0.0"
hooks = [
  { id = "trailing-whitespace" },
  { id = "end-of-file-fixer" },
  { id = "check-merge-conflict" },
]
```

### Zero-Network: Built-in Hooks Only<a name="zero-network-built-in-hooks-only"></a>

No internet access required after `prek install`.

```toml
# prek.toml
[[repos]]
repo = "builtin"
hooks = [
  { id = "trailing-whitespace" },
  { id = "end-of-file-fixer" },
  { id = "check-yaml" },
  { id = "check-toml" },
  { id = "check-json" },
  { id = "check-added-large-files", args = ["--maxkb=512"] },
  { id = "check-merge-conflict" },
  { id = "detect-private-key" },
  { id = "no-commit-to-branch", args = ["-b", "main", "-b", "master"] },
]
```

### Python Project: ruff + Built-ins<a name="python-project-ruff--built-ins"></a>

```toml
# prek.toml
fail_fast = false

[[repos]]
repo = "builtin"
hooks = [
  { id = "trailing-whitespace" },
  { id = "end-of-file-fixer" },
  { id = "check-toml" },
  { id = "check-yaml" },
  { id = "detect-private-key" },
]

[[repos]]
repo = "https://github.com/astral-sh/ruff-pre-commit"
rev = "v0.11.0"
hooks = [
  { id = "ruff", args = ["--fix"] },
  { id = "ruff-format" },
]
```

### Monorepo / Workspace Example<a name="monorepo--workspace-example"></a>

```toml
# prek.toml — root workspace config
default_stages = ["pre-commit"]

[[repos]]
repo = "builtin"
hooks = [
  { id = "check-merge-conflict" },
  { id = "detect-private-key" },
  { id = "no-commit-to-branch", args = ["-b", "main"] },
]

# services/api/prek.toml — package-specific config (orphan prevents root inheritance)
# orphan = true
#
# [[repos]]
# repo = "local"
#
# [[repos.hooks]]
# id = "api-lint"
# name = "API linter"
# language = "system"
# entry = "make lint"
# files = { glob = "services/api/**/*.py" }
# priority = 10
# env = { PYTHONPATH = "services/api" }
```
