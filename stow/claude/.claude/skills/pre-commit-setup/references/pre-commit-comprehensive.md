# pre-commit Comprehensive Reference

Deep reference for advanced pre-commit usage. For everyday commands, see `pre-commit-quick-reference.md`.

<!-- mdformat-toc start --slug=github --maxlevel=3 --minlevel=2 -->

- [1. Full CLI Reference](#1-full-cli-reference)
  - [Global Options](#global-options)
  - [Exit Codes](#exit-codes)
  - [`pre-commit autoupdate`](#pre-commit-autoupdate)
  - [`pre-commit clean`](#pre-commit-clean)
  - [`pre-commit gc`](#pre-commit-gc)
  - [`pre-commit init-templatedir DIRECTORY`](#pre-commit-init-templatedir-directory)
  - [`pre-commit install`](#pre-commit-install)
  - [`pre-commit install-hooks`](#pre-commit-install-hooks)
  - [`pre-commit migrate-config`](#pre-commit-migrate-config)
  - [`pre-commit run [hook-id]`](#pre-commit-run-hook-id)
  - [`pre-commit sample-config`](#pre-commit-sample-config)
  - [`pre-commit try-repo REPO`](#pre-commit-try-repo-repo)
  - [`pre-commit uninstall`](#pre-commit-uninstall)
  - [`pre-commit validate-config [filenames]`](#pre-commit-validate-config-filenames)
  - [`pre-commit validate-manifest [filenames]`](#pre-commit-validate-manifest-filenames)
- [2. Supported Languages](#2-supported-languages)
  - [Compiled / Installed Languages](#compiled--installed-languages)
  - [Special Languages](#special-languages)
  - [Language-Specific Notes](#language-specific-notes)
- [3. Hook Authoring](#3-hook-authoring)
  - [All Keys](#all-keys)
  - [Complete Example `.pre-commit-hooks.yaml`](#complete-example-pre-commit-hooksyaml)
  - [`additional_dependencies`](#additional_dependencies)
- [4. Language Version Overrides](#4-language-version-overrides)
  - [Per-Hook Override](#per-hook-override)
  - [Top-Level Default](#top-level-default)
  - [Version Format per Language](#version-format-per-language)
- [5. CI/CD Integration](#5-cicd-integration)
  - [Running pre-commit in CI](#running-pre-commit-in-ci)
  - [Caching Environments](#caching-environments)
  - [GitHub Actions](#github-actions)
  - [GitLab CI](#gitlab-ci)
  - [Azure Pipelines](#azure-pipelines)
  - [`SKIP` Environment Variable](#skip-environment-variable)
- [6. Hazmat Helpers (v4.5.0+)](#6-hazmat-helpers-v450)
  - [`pre-commit hazmat cd SUBDIR CMD --`](#pre-commit-hazmat-cd-subdir-cmd---)
  - [`pre-commit hazmat ignore-exit-code CMD --`](#pre-commit-hazmat-ignore-exit-code-cmd---)
  - [`pre-commit hazmat n1 CMD --`](#pre-commit-hazmat-n1-cmd---)
  - [Combining Helpers](#combining-helpers)
- [7. Meta Hooks](#7-meta-hooks)
  - [`check-hooks-apply`](#check-hooks-apply)
  - [`check-useless-excludes`](#check-useless-excludes)
  - [`identity`](#identity)
- [8. Advanced File Type Filtering](#8-advanced-file-type-filtering)
  - [Tag Categories](#tag-categories)
  - [AND vs OR Logic](#and-vs-or-logic)
  - [Common Patterns](#common-patterns)
  - [Inspecting Tags](#inspecting-tags)

<!-- mdformat-toc end -->

---

## 1. Full CLI Reference<a name="1-full-cli-reference"></a>

### Global Options<a name="global-options"></a>

All commands accept these flags:

| Flag                          | Description                                                        |
| ----------------------------- | ------------------------------------------------------------------ |
| `--color {auto,always,never}` | Control colored output                                             |
| `-c CONFIG`                   | Path to alternate config file (default: `.pre-commit-config.yaml`) |
| `-h`, `--help`                | Show help message                                                  |

### Exit Codes<a name="exit-codes"></a>

| Code  | Meaning                                                    |
| ----- | ---------------------------------------------------------- |
| `0`   | Success — all hooks passed                                 |
| `1`   | Detected error — at least one hook failed                  |
| `3`   | Unexpected error — pre-commit itself encountered a problem |
| `130` | Ctrl+C — interrupted by user                               |

---

### `pre-commit autoupdate`<a name="pre-commit-autoupdate"></a>

Update hook revisions to latest tags from their remote repositories.

```
pre-commit autoupdate [options]
```

| Flag               | Description                                                           |
| ------------------ | --------------------------------------------------------------------- |
| `--bleeding-edge`  | Use the latest commit on the default branch instead of the latest tag |
| `--freeze`         | Pin revisions to exact SHAs rather than tags (reproducible builds)    |
| `--repo REPO`      | Only update a specific repo by URL; can be specified multiple times   |
| `-j N`, `--jobs N` | Number of parallel update threads (default: 1)                        |

Examples:

```bash
# Update all hooks to latest tags
pre-commit autoupdate

# Pin all hooks to exact SHAs
pre-commit autoupdate --freeze

# Update only one repo
pre-commit autoupdate --repo https://github.com/psf/black

# Parallel update with 4 threads
pre-commit autoupdate -j 4
```

---

### `pre-commit clean`<a name="pre-commit-clean"></a>

Remove the pre-commit cache directory (`~/.cache/pre-commit` or `$PRE_COMMIT_HOME`). Useful when environments are
corrupted.

```
pre-commit clean
```

No additional flags. Equivalent to deleting the cache directory manually.

---

### `pre-commit gc`<a name="pre-commit-gc"></a>

Clean unused cached hook environments. Keeps only repos referenced in currently-installed configs.

```
pre-commit gc
```

Scans all registered configs and removes cached environments that no longer appear in any config. Runs automatically
after `pre-commit autoupdate`.

---

### `pre-commit init-templatedir DIRECTORY`<a name="pre-commit-init-templatedir-directory"></a>

Install pre-commit as a Git template directory so new `git clone` or `git init` operations automatically receive the
hook.

```
pre-commit init-templatedir DIRECTORY [options]
```

| Flag           | Description                                              |
| -------------- | -------------------------------------------------------- |
| `-t HOOK_TYPE` | Hook type to install (default: `pre-commit`); repeatable |

```bash
# Set up a template dir
pre-commit init-templatedir ~/.git-template

# Configure Git to use it globally
git config --global init.templateDir ~/.git-template

# Install multiple hook types
pre-commit init-templatedir ~/.git-template -t pre-commit -t commit-msg
```

---

### `pre-commit install`<a name="pre-commit-install"></a>

Install the pre-commit script into `.git/hooks/`.

```
pre-commit install [options]
```

| Flag                     | Description                                              |
| ------------------------ | -------------------------------------------------------- |
| `-f`, `--overwrite`      | Replace any existing hook at that path                   |
| `--install-hooks`        | Also pre-install all hook environments immediately       |
| `-t HOOK_TYPE`           | Hook type to install (default: `pre-commit`); repeatable |
| `--allow-missing-config` | Install even if no config file exists yet                |

Hook types: `pre-commit`, `pre-merge-commit`, `pre-push`, `prepare-commit-msg`, `commit-msg`, `post-checkout`,
`post-commit`, `post-merge`, `post-rewrite`

```bash
# Standard install
pre-commit install

# Install and immediately download all environments
pre-commit install --install-hooks

# Install for commit-msg stage too
pre-commit install -t pre-commit -t commit-msg

# Overwrite an existing hook
pre-commit install -f
```

---

### `pre-commit install-hooks`<a name="pre-commit-install-hooks"></a>

Pre-install all hook environments without running any hooks. Useful in CI image preparation.

```
pre-commit install-hooks
```

Reads the config and installs every listed hook's environment. Equivalent to `pre-commit install --install-hooks`
without touching `.git/hooks/`.

---

### `pre-commit migrate-config`<a name="pre-commit-migrate-config"></a>

Convert a legacy `.pre-commit-config.yaml` list format to the current map format.

```
pre-commit migrate-config
```

Legacy format used a bare list at the top level. Current format uses `repos:` as the top-level key. This command
rewrites the file in place.

---

### `pre-commit run [hook-id]`<a name="pre-commit-run-hook-id"></a>

Run hooks. With no arguments, runs all hooks on staged files.

```
pre-commit run [hook-id] [options]
```

| Flag                          | Description                                                  |
| ----------------------------- | ------------------------------------------------------------ |
| `-a`, `--all-files`           | Run on all files in the repository                           |
| `--files [FILES...]`          | Run on specific files (space-separated)                      |
| `--from-ref FROM --to-ref TO` | Run on files changed between two refs                        |
| `--hook-stage STAGE`          | Specify which stage to run (e.g. `commit`, `push`, `manual`) |
| `--show-diff-on-failure`      | Print a diff when a hook fails                               |
| `-v`, `--verbose`             | Always print hook output even on success                     |

```bash
# Run all hooks on staged files
pre-commit run

# Run a specific hook on all files
pre-commit run black --all-files

# Run on files changed in a PR
pre-commit run --from-ref origin/main --to-ref HEAD

# Run with diff output on failure
pre-commit run --all-files --show-diff-on-failure

# Run only hooks in the push stage
pre-commit run --hook-stage push
```

---

### `pre-commit sample-config`<a name="pre-commit-sample-config"></a>

Print a minimal `.pre-commit-config.yaml` to stdout.

```
pre-commit sample-config
```

Pipe to a file to bootstrap a config:

```bash
pre-commit sample-config > .pre-commit-config.yaml
```

---

### `pre-commit try-repo REPO`<a name="pre-commit-try-repo-repo"></a>

Try hooks from a local or remote repository without adding them to your config. Extremely useful when authoring new
hooks.

```
pre-commit try-repo REPO [options]
```

| Flag        | Description                                                     |
| ----------- | --------------------------------------------------------------- |
| `--ref REF` | Git ref to use (default: HEAD for local, latest tag for remote) |

Supports all `run` options (`--all-files`, `--files`, `--from-ref`/`--to-ref`, etc.)

```bash
# Try hooks from a local repo
pre-commit try-repo ../my-hooks --all-files

# Try a specific ref from a remote repo
pre-commit try-repo https://github.com/psf/black --ref 23.7.0 --all-files
```

---

### `pre-commit uninstall`<a name="pre-commit-uninstall"></a>

Remove pre-commit hooks from `.git/hooks/`.

```
pre-commit uninstall [options]
```

| Flag           | Description                                                |
| -------------- | ---------------------------------------------------------- |
| `-t HOOK_TYPE` | Hook type to uninstall (default: `pre-commit`); repeatable |

```bash
pre-commit uninstall
pre-commit uninstall -t commit-msg -t pre-push
```

---

### `pre-commit validate-config [filenames]`<a name="pre-commit-validate-config-filenames"></a>

Validate one or more config files against the pre-commit schema.

```
pre-commit validate-config [filenames...]
```

Defaults to `.pre-commit-config.yaml` if no filenames given.

---

### `pre-commit validate-manifest [filenames]`<a name="pre-commit-validate-manifest-filenames"></a>

Validate one or more `.pre-commit-hooks.yaml` hook manifests against the schema.

```
pre-commit validate-manifest [filenames...]
```

---

## 2. Supported Languages<a name="2-supported-languages"></a>

### Compiled / Installed Languages<a name="compiled--installed-languages"></a>

| Language | Key        | Requirement                                         |
| -------- | ---------- | --------------------------------------------------- |
| Conda    | `conda`    | Conda environment with `environment.yml`            |
| Coursier | `coursier` | JVM + Coursier; uses Maven coordinates in `entry`   |
| Dart     | `dart`     | Dart SDK; uses `pubspec.yaml`                       |
| .NET     | `dotnet`   | .NET SDK; uses `.csproj`                            |
| Go       | `golang`   | Go source files in repo root                        |
| Haskell  | `haskell`  | Stack; uses `stack.yaml` and `.cabal`               |
| Julia    | `julia`    | Julia with `Project.toml`                           |
| Lua      | `lua`      | LuaRocks; uses a rockspec file                      |
| Node     | `node`     | Node.js; uses `package.json` with `bin` field       |
| Perl     | `perl`     | CPAN; installs from `Makefile.PL` or `Build.PL`     |
| Python   | `python`   | pip-installable package (setup.py / pyproject.toml) |
| R        | `r`        | R with `renv.lock`                                  |
| Ruby     | `ruby`     | Bundler; requires `*.gemspec`                       |
| Rust     | `rust`     | Cargo; requires `Cargo.toml` with a binary target   |
| Swift    | `swift`    | Swift Package Manager; uses `Package.swift`         |

### Special Languages<a name="special-languages"></a>

| Language     | Key            | Purpose                                                                    |
| ------------ | -------------- | -------------------------------------------------------------------------- |
| Docker       | `docker`       | Builds an image from a `Dockerfile` in the repo; runs command in container |
| Docker image | `docker_image` | Uses a pre-existing image; `entry` is the image name                       |
| Fail         | `fail`         | Lightweight hook that always fails — used to block files by pattern        |
| pygrep       | `pygrep`       | Runs a Python regex against file contents; `entry` is the pattern          |
| Script       | `script`       | Runs an executable script from the repo root                               |
| System       | `system`       | Uses a system-installed executable (no environment management)             |

### Language-Specific Notes<a name="language-specific-notes"></a>

**Python**: The repo must be pip-installable. pre-commit creates a virtualenv and runs `pip install .`. Use
`additional_dependencies` to add packages not declared in the package's own dependencies.

**Node**: The repo must have a `package.json` with a `bin` entry pointing to the executable. pre-commit runs
`npm install`.

**Ruby**: Requires a `*.gemspec`. pre-commit runs `gem build` and `gem install`.

**Rust**: Requires `Cargo.toml` with at least one `[[bin]]` target. pre-commit runs `cargo install --path .`.

**Golang**: The repo must contain Go source files. pre-commit runs `go install ./...`.

**R**: Requires `renv.lock`. pre-commit uses `renv::restore()` to set up the environment.

**fail**: No installation step. Useful for blocking files by extension or pattern without needing any runtime:

```yaml
  - id: no-commit-to-branch
    name: Prevent commits to protected branches
    language: fail
    entry: Direct commits to main are not allowed
    files: ''
```

**pygrep**: The `entry` value is a Python regex. Fails if any matched file contains the pattern:

```yaml
  - id: no-print-statements
    name: No print statements
    entry: ^print\(
    language: pygrep
    types: [python]
```

---

## 3. Hook Authoring<a name="3-hook-authoring"></a>

Hooks are defined in `.pre-commit-hooks.yaml` at the root of a repository.

### All Keys<a name="all-keys"></a>

| Key                          | Required | Default                 | Description                                       |
| ---------------------------- | -------- | ----------------------- | ------------------------------------------------- |
| `id`                         | Yes      | —                       | Unique identifier within this repo                |
| `name`                       | Yes      | —                       | Human-readable display name                       |
| `entry`                      | Yes      | —                       | Executable or command to run                      |
| `language`                   | Yes      | —                       | Environment type (see Section 2)                  |
| `files`                      | No       | `''`                    | Regex; only run on matching filenames             |
| `exclude`                    | No       | `^$` (nothing excluded) | Regex; exclude matching filenames                 |
| `types`                      | No       | `[file]`                | File type tags (AND logic) — all must match       |
| `types_or`                   | No       | `[]`                    | File type tags (OR logic) — any must match        |
| `exclude_types`              | No       | `[]`                    | File type tags to exclude                         |
| `always_run`                 | No       | `false`                 | Run even when no files match                      |
| `fail_fast`                  | No       | `false`                 | Stop running hooks if this one fails              |
| `verbose`                    | No       | `false`                 | Always show output even on success                |
| `pass_filenames`             | No       | `true`                  | Pass matched filenames as arguments               |
| `require_serial`             | No       | `false`                 | Disable parallel file processing                  |
| `description`                | No       | `''`                    | Human-readable description (unused by pre-commit) |
| `language_version`           | No       | `default`               | Override runtime version                          |
| `minimum_pre_commit_version` | No       | `'0'`                   | Minimum pre-commit version required               |
| `args`                       | No       | `[]`                    | Additional arguments prepended to the command     |
| `stages`                     | No       | all stages              | Restrict to specific Git hook stages              |

### Complete Example `.pre-commit-hooks.yaml`<a name="complete-example-pre-commit-hooksyaml"></a>

```yaml
  - id: check-json
    name: Check JSON syntax
    description: Validates JSON files for syntax errors
    entry: python -m json.tool
    language: python
    types: [json]
    pass_filenames: true
    require_serial: false

  - id: no-secrets
    name: Detect secrets
    description: Blocks files containing AWS keys or tokens
    entry: detect-secrets-hook
    language: python
    additional_dependencies: [detect-secrets==1.4.0]
    args: [--baseline, .secrets.baseline]
    stages: [pre-commit, pre-push]

  - id: enforce-changelog
    name: Require CHANGELOG entry
    description: Fails if CHANGELOG.md was not modified
    entry: CHANGELOG.md must be updated
    language: fail
    files: ^CHANGELOG\.md$
    always_run: true
    pass_filenames: false

  - id: check-merge-conflict
    name: Check for merge conflict markers
    description: Detects unresolved merge conflict markers in source files
    entry: check-merge-conflict
    language: python
    types: [text]
    args: [--assume-in-merge]
```

### `additional_dependencies`<a name="additional_dependencies"></a>

Not a top-level key in the manifest, but available in the consumer's config to inject extra packages into the hook's
environment:

```yaml
repos:
  - repo: https://github.com/PyCQA/flake8
    rev: 6.0.0
    hooks:
      - id: flake8
        additional_dependencies:
          - flake8-bugbear
          - flake8-comprehensions
```

---

## 4. Language Version Overrides<a name="4-language-version-overrides"></a>

### Per-Hook Override<a name="per-hook-override"></a>

Use `language_version` on a specific hook to pin the runtime:

```yaml
repos:
  - repo: https://github.com/psf/black
    rev: 23.7.0
    hooks:
      - id: black
        language_version: python3.11
```

### Top-Level Default<a name="top-level-default"></a>

Use `default_language_version` to set defaults for all hooks of a given language:

```yaml
default_language_version:
  python: python3.11
  node: 18.17.0
  ruby: 3.2.0
  golang: 1.21.0
  rust: stable
```

### Version Format per Language<a name="version-format-per-language"></a>

| Language | Format                         | Example            |
| -------- | ------------------------------ | ------------------ |
| Python   | `pythonX.Y` or full path       | `python3.11`       |
| Node     | semver string                  | `"18.17.0"`        |
| Ruby     | semver string                  | `3.2.0`            |
| Go       | semver string (no leading `v`) | `"1.21.0"`         |
| Rust     | channel name or semver         | `stable`, `1.72.0` |
| R        | semver string                  | `4.3.1`            |

`system` and `script` language hooks ignore `language_version` entirely — they use whatever is on `$PATH`.

---

## 5. CI/CD Integration<a name="5-cicd-integration"></a>

### Running pre-commit in CI<a name="running-pre-commit-in-ci"></a>

**Full check** — run all hooks on every file:

```bash
pre-commit run --all-files
```

**Changed files only** — run on files changed relative to a base branch (faster for large repos):

```bash
pre-commit run --from-ref origin/HEAD --to-ref HEAD
```

### Caching Environments<a name="caching-environments"></a>

pre-commit caches hook environments to avoid reinstalling on every run. Configure the cache location via:

| Variable          | Purpose                                       |
| ----------------- | --------------------------------------------- |
| `PRE_COMMIT_HOME` | Override the default cache directory entirely |
| `XDG_CACHE_HOME`  | Relocate `$XDG_CACHE_HOME/pre-commit`         |

Default location: `~/.cache/pre-commit`

### GitHub Actions<a name="github-actions"></a>

```yaml
name: pre-commit

on:
  pull_request:
  push:
    branches: [main]

jobs:
  pre-commit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - uses: actions/cache@v4
        with:
          path: ~/.cache/pre-commit
          key: pre-commit-${{ hashFiles('.pre-commit-config.yaml') }}
      - name: Install pre-commit
        run: pip install pre-commit
      - name: Run pre-commit
        run: pre-commit run --from-ref origin/${{ github.base_ref }} --to-ref 
          HEAD
```

The official `pre-commit/action` action wraps this pattern:

```yaml
  - uses: pre-commit/action@v3.0.0
```

### GitLab CI<a name="gitlab-ci"></a>

```yaml
pre-commit:
  image: python:3.11
  stage: lint
  variables:
    PRE_COMMIT_HOME: ${CI_PROJECT_DIR}/.cache/pre-commit
  cache:
    paths:
      - .cache/pre-commit
  before_script:
    - pip install pre-commit
  script:
    - pre-commit run --from-ref $CI_MERGE_REQUEST_DIFF_BASE_SHA --to-ref HEAD
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
```

### Azure Pipelines<a name="azure-pipelines"></a>

```yaml
trigger:
  - main

pool:
  vmImage: ubuntu-latest

steps:
  - task: UsePythonVersion@0
    inputs:
      versionSpec: '3.11'
  - script: pip install pre-commit
    displayName: Install pre-commit
  - task: Cache@2
    inputs:
      key: pre-commit | "$(Agent.OS)" | .pre-commit-config.yaml
      restoreKeys: pre-commit | "$(Agent.OS)"
      path: $(PRE_COMMIT_HOME)
    displayName: Cache pre-commit environments
    env:
      PRE_COMMIT_HOME: $(Pipeline.Workspace)/.pre-commit
  - script: pre-commit run --all-files
    displayName: Run pre-commit
    env:
      PRE_COMMIT_HOME: $(Pipeline.Workspace)/.pre-commit
```

### `SKIP` Environment Variable<a name="skip-environment-variable"></a>

Skip specific hooks in CI without modifying config:

```bash
SKIP=flake8,mypy pre-commit run --all-files
```

---

## 6. Hazmat Helpers (v4.5.0+)<a name="6-hazmat-helpers-v450"></a>

Hazmat helpers are special `entry` prefixes that modify how pre-commit invokes hook commands. They are intended for
advanced use cases where standard hook behavior is insufficient.

The prefix syntax is: `pre-commit hazmat <helper> <CMD> --`

The `--` separator is required. Everything after `--` is the actual command and its arguments.

### `pre-commit hazmat cd SUBDIR CMD --`<a name="pre-commit-hazmat-cd-subdir-cmd---"></a>

Change into a subdirectory before running the command. Essential for monorepos where a tool must run from a specific
project directory.

```yaml
  - id: run-tests-in-subdir
    name: Run backend tests
    entry: pre-commit hazmat cd backend python -m pytest --
    language: python
    pass_filenames: false
    always_run: true
```

### `pre-commit hazmat ignore-exit-code CMD --`<a name="pre-commit-hazmat-ignore-exit-code-cmd---"></a>

Treat a non-zero exit code from the command as success. Converts hard failures into warnings — the hook output is still
shown but the commit is not blocked.

```yaml
  - id: advisory-lint
    name: Advisory linting (non-blocking)
    entry: pre-commit hazmat ignore-exit-code pylint --
    language: python
    types: [python]
```

### `pre-commit hazmat n1 CMD --`<a name="pre-commit-hazmat-n1-cmd---"></a>

Process files one at a time sequentially instead of passing all matched files to a single command invocation. Useful for
tools that cannot accept multiple file arguments or that produce ambiguous output when given many files.

```yaml
  - id: process-one-at-a-time
    name: Per-file processor
    entry: pre-commit hazmat n1 my-tool --
    language: system
    types: [python]
```

### Combining Helpers<a name="combining-helpers"></a>

Helpers can be nested. Nesting order matters — the outermost helper executes first:

```yaml
entry: pre-commit hazmat cd src pre-commit hazmat n1 my-tool --
```

---

## 7. Meta Hooks<a name="7-meta-hooks"></a>

`repo: meta` provides built-in hooks that validate the pre-commit configuration itself. These hooks have no external
dependencies and run against the local repo.

```yaml
repos:
  - repo: meta
    hooks:
      - id: check-hooks-apply
      - id: check-useless-excludes
      - id: identity
```

### `check-hooks-apply`<a name="check-hooks-apply"></a>

Ensures every hook in the config matches at least one file in the repository. Catches hooks with overly-restrictive
`files` patterns that would never run.

Fails if: a hook's `files` pattern matches zero tracked files (and `always_run` is not set).

### `check-useless-excludes`<a name="check-useless-excludes"></a>

Verifies that every `exclude` pattern in the config actually excludes at least one file. Catches stale exclude patterns
left over after file moves or deletions.

Fails if: an `exclude` pattern matches no tracked files.

### `identity`<a name="identity"></a>

Prints all filenames passed to it, then exits successfully. Primarily a debugging aid — useful for inspecting which
files a particular `files`/`types` combination would select without running a real tool.

```yaml
  - repo: meta
    hooks:
      - id: identity
        files: ^src/.*\.py$
        types: [python]
```

Running this shows exactly which Python files in `src/` would be passed to a hook with those filters.

---

## 8. Advanced File Type Filtering<a name="8-advanced-file-type-filtering"></a>

pre-commit uses the `identify` library to tag files. Tags drive `types`, `types_or`, and `exclude_types` matching.

### Tag Categories<a name="tag-categories"></a>

**Filesystem tags** — always present based on filesystem metadata:

| Tag              | Meaning                                   |
| ---------------- | ----------------------------------------- |
| `file`           | Regular file (not a symlink or directory) |
| `symlink`        | Symbolic link                             |
| `directory`      | Directory                                 |
| `executable`     | File with execute bit set                 |
| `text`           | File with text content (heuristic)        |
| `binary`         | File with binary content                  |
| `non-executable` | File without execute bit                  |

**Language tags** — inferred from file content and extension:

Common examples: `python`, `javascript`, `typescript`, `jsx`, `tsx`, `ruby`, `go`, `rust`, `java`, `c`, `c++`, `swift`,
`kotlin`, `scala`, `bash`, `sh`, `zsh`, `sql`, `html`, `css`, `markdown`, `rst`

**Extension/format tags** — based purely on extension:

Common examples: `yaml`, `json`, `toml`, `ini`, `xml`, `csv`, `dockerfile`, `makefile`, `jupyter`, `proto`

### AND vs OR Logic<a name="and-vs-or-logic"></a>

`types` uses AND logic — every tag in the list must match the file:

```yaml
# Matches only non-symlink, text Python files
types: [file, text, python]
```

`types_or` uses OR logic — any single tag in the list is sufficient:

```yaml
# Matches JavaScript OR JSX OR TSX files
types_or: [javascript, jsx, tsx]
```

`types` and `types_or` can be combined. The file must satisfy both:

```yaml
# Matches files that are (text AND executable) AND (python OR ruby)
types: [text, executable]
types_or: [python, ruby]
```

`exclude_types` always uses OR logic — exclude if any listed tag matches:

```yaml
# Exclude binary files and symlinks
exclude_types: [binary, symlink]
```

### Common Patterns<a name="common-patterns"></a>

Match TypeScript and JavaScript (including React variants):

```yaml
types_or: [javascript, jsx, typescript, tsx]
```

Match only regular Python source files (exclude notebooks):

```yaml
types: [file, python]
exclude: \.ipynb$
```

Match Docker-related files:

```yaml
types_or: [dockerfile]
files: (Dockerfile|\.dockerignore)
```

Match any config file format:

```yaml
types_or: [yaml, toml, json, ini]
```

### Inspecting Tags<a name="inspecting-tags"></a>

Use the `identify` CLI to see what tags a file receives:

```bash
pip install identify
identify-cli path/to/file.py
# outputs: file non-executable python text
```

Or use the `identity` meta hook (Section 7) to see which files match a given filter combination.
