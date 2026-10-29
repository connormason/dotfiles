# pre-commit Quick Reference

Source: https://pre-commit.com

<!-- mdformat-toc start --slug=github --maxlevel=3 --minlevel=2 -->

- [1. Configuration Format](#1-configuration-format)
- [2. Repository Configuration](#2-repository-configuration)
- [3. Hook Configuration](#3-hook-configuration)
- [4. Common CLI Commands](#4-common-cli-commands)
  - [Install](#install)
  - [Run](#run)
  - [Autoupdate](#autoupdate)
  - [Maintenance](#maintenance)
  - [Uninstall](#uninstall)
  - [Utilities](#utilities)
- [5. Hook Stages](#5-hook-stages)
- [6. File Type Filtering](#6-file-type-filtering)
- [7. Common Hooks (`pre-commit/pre-commit-hooks`)](#7-common-hooks-pre-commitpre-commit-hooks)
- [8. Skipping Hooks](#8-skipping-hooks)
- [9. Local Hooks](#9-local-hooks)
- [10. Configuration Examples](#10-configuration-examples)
  - [Minimal setup](#minimal-setup)
  - [Python project (ruff + mypy + pre-commit-hooks)](#python-project-ruff--mypy--pre-commit-hooks)
  - [Multi-language project (Python + JS + Docker)](#multi-language-project-python--js--docker)
  - [Monorepo with path filtering](#monorepo-with-path-filtering)

<!-- mdformat-toc end -->

---

## 1. Configuration Format<a name="1-configuration-format"></a>

Top-level keys in `.pre-commit-config.yaml`:

| Key                          | Type    | Default        | Description                                                                  |
| ---------------------------- | ------- | -------------- | ---------------------------------------------------------------------------- |
| `repos`                      | list    | required       | Repository mappings containing hook definitions                              |
| `default_install_hook_types` | list    | `[pre-commit]` | Hook types installed when running `pre-commit install`                       |
| `default_language_version`   | mapping | `{}`           | Override language versions globally (e.g. `python: python3.11`)              |
| `default_stages`             | list    | all stages     | Default execution stages for hooks that don't specify their own              |
| `files`                      | string  | `''`           | Global file include pattern (Python regex); hooks run only on matching files |
| `exclude`                    | string  | `^$`           | Global file exclude pattern (Python regex); matched files are skipped        |
| `fail_fast`                  | boolean | `false`        | Stop running hooks after the first failure                                   |
| `minimum_pre_commit_version` | string  | `'0'`          | Minimum pre-commit version required to use this config                       |

---

## 2. Repository Configuration<a name="2-repository-configuration"></a>

Each entry under `repos` has these keys:

| Key     | Required                    | Description                                                                        |
| ------- | --------------------------- | ---------------------------------------------------------------------------------- |
| `repo`  | yes                         | Git URL of the hooks repository, `local` for local hooks, or `meta` for meta hooks |
| `rev`   | yes (except `local`/`meta`) | Immutable reference — use a tag or full SHA, never a branch name                   |
| `hooks` | yes                         | List of hook definitions (see section 3)                                           |

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0          # tag or SHA — never a branch
    hooks:
      - id: trailing-whitespace
```

`meta` repos provide built-in hooks: `identity`, `check-hooks-apply`, `check-useless-excludes`.

---

## 3. Hook Configuration<a name="3-hook-configuration"></a>

Keys available within each hook definition:

| Key                       | Type    | Default          | Description                                                                 |
| ------------------------- | ------- | ---------------- | --------------------------------------------------------------------------- |
| `id`                      | string  | required         | Hook identifier as defined in the repository's `.pre-commit-hooks.yaml`     |
| `alias`                   | string  | —                | Additional alias to invoke the hook by                                      |
| `name`                    | string  | hook default     | Override the display name shown during execution                            |
| `language_version`        | string  | hook default     | Override the language version for this hook (e.g. `python3.11`)             |
| `files`                   | string  | hook default     | File include pattern (Python regex); narrows or replaces the hook's default |
| `exclude`                 | string  | hook default     | File exclude pattern (Python regex)                                         |
| `types`                   | list    | hook default     | File type tags that ALL must match (AND logic)                              |
| `types_or`                | list    | hook default     | File type tags where ANY must match (OR logic)                              |
| `exclude_types`           | list    | `[]`             | File type tags; files matching any of these are excluded                    |
| `args`                    | list    | `[]`             | Additional arguments passed to the hook                                     |
| `stages`                  | list    | `default_stages` | Stages during which this hook runs                                          |
| `additional_dependencies` | list    | `[]`             | Extra packages to install alongside the hook's language environment         |
| `always_run`              | boolean | `false`          | Run even when no files match the filter                                     |
| `verbose`                 | boolean | `false`          | Always print hook output, even on success                                   |
| `log_file`                | string  | —                | Write hook output to this file path in addition to stdout                   |

---

## 4. Common CLI Commands<a name="4-common-cli-commands"></a>

### Install<a name="install"></a>

```bash
pre-commit install                   # install into .git/hooks/pre-commit
pre-commit install -f                # force overwrite existing hook script
pre-commit install --install-hooks   # also install hook environments immediately
pre-commit install -t pre-push       # install for a specific hook type
pre-commit install -t commit-msg -t pre-push  # install multiple types
```

### Run<a name="run"></a>

```bash
pre-commit run                        # run on staged files
pre-commit run --all-files            # run on all files in the repo
pre-commit run <hook-id>              # run a specific hook
pre-commit run --files a.py b.py      # run on specific files
pre-commit run --from-ref HEAD~3 --to-ref HEAD  # run on files changed between refs
pre-commit run --hook-stage pre-push  # run hooks for a specific stage
pre-commit run --show-diff-on-failure # print a diff when a hook modifies files
pre-commit run -v                     # verbose: show hook output even on success
```

### Autoupdate<a name="autoupdate"></a>

```bash
pre-commit autoupdate                 # update all repos to latest tag
pre-commit autoupdate --bleeding-edge # update to latest commit on default branch
pre-commit autoupdate --freeze        # pin to full SHA instead of tag
pre-commit autoupdate --repo https://github.com/psf/black  # update specific repo
pre-commit autoupdate -j 4            # update using 4 parallel jobs
```

### Maintenance<a name="maintenance"></a>

```bash
pre-commit clean          # remove cached hook environments (~/.cache/pre-commit)
pre-commit gc             # garbage collect unused cached environments
```

### Uninstall<a name="uninstall"></a>

```bash
pre-commit uninstall                  # remove pre-commit from .git/hooks/pre-commit
pre-commit uninstall -t pre-push      # remove from a specific hook type
```

### Utilities<a name="utilities"></a>

```bash
pre-commit validate-config            # validate .pre-commit-config.yaml syntax
pre-commit sample-config              # print a sample config to stdout
pre-commit try-repo https://github.com/psf/black  # try hooks from a repo without configuring
pre-commit try-repo /path/to/local/repo --ref HEAD  # try local repo at specific ref
```

---

## 5. Hook Stages<a name="5-hook-stages"></a>

Hooks can be configured to run at specific git lifecycle points:

| Stage                | Triggered by                                            |
| -------------------- | ------------------------------------------------------- |
| `pre-commit`         | `git commit` (default)                                  |
| `prepare-commit-msg` | `git commit` — before editor opens                      |
| `commit-msg`         | `git commit` — validates the commit message             |
| `post-commit`        | `git commit` — after commit is created                  |
| `pre-push`           | `git push`                                              |
| `pre-merge-commit`   | `git merge`                                             |
| `post-merge`         | `git merge` — after merge completes                     |
| `post-checkout`      | `git checkout` / `git switch`                           |
| `post-rewrite`       | `git rebase`, `git commit --amend`                      |
| `pre-rebase`         | `git rebase` — before rebase starts                     |
| `manual`             | Only when explicitly invoked with `--hook-stage manual` |

Hooks default to `pre-commit` unless `stages` is specified in the hook definition or `default_stages` is set globally.

---

## 6. File Type Filtering<a name="6-file-type-filtering"></a>

Three keys control which files a hook receives:

- `types` — ALL listed tags must match (AND logic). Use to require, e.g., both `python` and `executable`.
- `types_or` — ANY listed tag must match (OR logic). Use to accept multiple file types.
- `exclude_types` — Files matching ANY listed tag are excluded regardless of `types`/`types_or`.

Common type tags:

| Tag              | Matches                                           |
| ---------------- | ------------------------------------------------- |
| `file`           | Regular files (not symlinks or directories)       |
| `symlink`        | Symbolic links                                    |
| `directory`      | Directories                                       |
| `executable`     | Files with executable bit set                     |
| `text`           | Text files (detected by content)                  |
| `binary`         | Binary files                                      |
| `python`         | `.py`, `.pyi` files                               |
| `javascript`     | `.js`, `.jsx`, `.mjs` files                       |
| `typescript`     | `.ts`, `.tsx` files                               |
| `json`           | `.json` files                                     |
| `yaml`           | `.yaml`, `.yml` files                             |
| `toml`           | `.toml` files                                     |
| `markdown`       | `.md`, `.markdown` files                          |
| `bash`           | `.bash`, `.sh` (detected by shebang or extension) |
| `dockerfile`     | `Dockerfile` and `*.dockerfile`                   |
| `non_executable` | Files without executable bit                      |

Full tag list: https://pre-commit.com/hooks.html — run `pre-commit run --all-files identity -v` to see detected types
for your files.

---

## 7. Common Hooks (`pre-commit/pre-commit-hooks`)<a name="7-common-hooks-pre-commitpre-commit-hooks"></a>

Repo: `https://github.com/pre-commit/pre-commit-hooks`

| Hook ID                           | Description                                  | Notable Args                                     |
| --------------------------------- | -------------------------------------------- | ------------------------------------------------ |
| `trailing-whitespace`             | Remove trailing whitespace                   | `--markdown-linebreak-ext=md` to preserve `  \n` |
| `end-of-file-fixer`               | Ensure files end with a single newline       | —                                                |
| `check-yaml`                      | Validate YAML syntax                         | `--unsafe` to allow custom tags                  |
| `check-json`                      | Validate JSON syntax                         | —                                                |
| `check-toml`                      | Validate TOML syntax                         | —                                                |
| `check-added-large-files`         | Fail if large files are staged               | `--maxkb=500` (default: 500 KB)                  |
| `check-merge-conflict`            | Detect unresolved merge conflict markers     | —                                                |
| `detect-private-key`              | Fail if private keys are staged              | —                                                |
| `mixed-line-ending`               | Normalize line endings                       | `--fix=lf` or `--fix=crlf`                       |
| `no-commit-to-branch`             | Prevent direct commits to protected branches | `--branch main --branch master`                  |
| `check-executables-have-shebangs` | Fail if executable files lack shebangs       | —                                                |
| `check-symlinks`                  | Fail if symlinks point to nothing            | —                                                |

---

## 8. Skipping Hooks<a name="8-skipping-hooks"></a>

Skip specific hooks for a single commit using the `SKIP` environment variable:

```bash
SKIP=flake8 git commit -m "wip"
SKIP=flake8,mypy git commit -m "wip"   # comma-separated, no spaces
```

Skip all hooks (bypasses pre-commit entirely — prefer SKIP when possible):

```bash
git commit --no-verify -m "emergency fix"
```

The environment variable `PRE_COMMIT=1` is set by pre-commit during hook execution. Hook scripts can check for this to
detect that they are running inside pre-commit.

---

## 9. Local Hooks<a name="9-local-hooks"></a>

Use `repo: local` to define hooks that run scripts or tools already present on the system without installing from a
remote repository.

```yaml
repos:
  - repo: local
    hooks:
      # System tool — no environment installed, uses whatever is on PATH
      - id: check-migrations
        name: Check for missing migrations
        language: system
        entry: python manage.py migrate --check
        pass_filenames: false
        always_run: true

      # Python tool — pre-commit creates an isolated venv with the listed deps
      - id: mypy
        name: mypy type checking
        language: python
        entry: mypy
        types: [python]
        args: [--strict]
        additional_dependencies:
          - mypy==1.8.0
          - types-requests
```

Supported `language` values for local hooks: `conda`, `coursier`, `dart`, `docker`, `docker_image`, `dotnet`, `fail`,
`golang`, `haskell`, `lua`, `node`, `perl`, `python`, `r`, `ruby`, `rust`, `swift`, `pygrep`, `script`, `system`.

Use `language: fail` to create a hook that always fails with a message (useful for blocking certain patterns):

```yaml
  - id: no-print-statements
    name: No print statements
    language: fail
    entry: print() found — use logging instead
    types: [python]
    files: \.py$
```

---

## 10. Configuration Examples<a name="10-configuration-examples"></a>

### Minimal setup<a name="minimal-setup"></a>

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
```

### Python project (ruff + mypy + pre-commit-hooks)<a name="python-project-ruff--mypy--pre-commit-hooks"></a>

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-toml
      - id: check-merge-conflict
      - id: detect-private-key
      - id: no-commit-to-branch
        args: [--branch, main]

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.3.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.8.0
    hooks:
      - id: mypy
        additional_dependencies:
          - types-requests
          - types-PyYAML
```

### Multi-language project (Python + JS + Docker)<a name="multi-language-project-python--js--docker"></a>

```yaml
default_stages: [pre-commit]
fail_fast: false

repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-json
      - id: check-added-large-files
        args: [--maxkb=1024]
      - id: detect-private-key

  # Python
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.3.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  # JavaScript / TypeScript
  - repo: https://github.com/pre-commit/mirrors-eslint
    rev: v8.57.0
    hooks:
      - id: eslint
        files: \.[jt]sx?$
        types: [file]
        additional_dependencies:
          - eslint@8.57.0
          - '@typescript-eslint/eslint-plugin@7.0.0'

  # Dockerfile linting
  - repo: https://github.com/hadolint/hadolint
    rev: v2.12.0
    hooks:
      - id: hadolint-docker
        args: [--ignore, DL3008]
```

### Monorepo with path filtering<a name="monorepo-with-path-filtering"></a>

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.3.0
    hooks:
      - id: ruff
        files: ^(backend|scripts)/  # only run on these directories
        args: [--fix]

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.8.0
    hooks:
      - id: mypy
        files: ^backend/
        args: [--config-file=backend/mypy.ini]
        additional_dependencies:
          - types-requests

  - repo: local
    hooks:
      - id: pytest-fast
        name: pytest (fast suite)
        language: system
        entry: pytest -m "not slow" --tb=short
        pass_filenames: false
        stages: [pre-push]    # only runs on git push, not every commit
```
