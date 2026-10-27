# Migrating from pre-commit to prek

A practical, step-by-step guide for teams and individuals moving from [pre-commit](https://pre-commit.com) to
[prek](https://github.com/j178/prek).

<!-- mdformat-toc start --slug=github --maxlevel=3 --minlevel=2 -->

- [1. Pre-Migration Checklist](#1-pre-migration-checklist)
- [2. Compatibility Matrix](#2-compatibility-matrix)
- [3. Step-by-Step Migration](#3-step-by-step-migration)
  - [Step 1: Install prek](#step-1-install-prek)
  - [Step 2: Test your existing config](#step-2-test-your-existing-config)
  - [Step 3: Reinstall git shims](#step-3-reinstall-git-shims)
  - [Step 4: (Optional) Convert config to TOML](#step-4-optional-convert-config-to-toml)
  - [Step 5: (Optional) Replace remote hooks with built-ins](#step-5-optional-replace-remote-hooks-with-built-ins)
  - [Step 6: Update CI/CD pipelines](#step-6-update-cicd-pipelines)
  - [Step 7: Update team documentation](#step-7-update-team-documentation)
- [4. YAML-to-TOML Conversion Guide](#4-yaml-to-toml-conversion-guide)
  - [Manual conversion rules](#manual-conversion-rules)
  - [Full before/after example](#full-beforeafter-example)
- [5. Post-Migration: prek-Only Improvements](#5-post-migration-prek-only-improvements)
  - [Built-in hooks (`repo: builtin`)](#built-in-hooks-repo-builtin)
  - [`env` key — per-hook environment variables](#env-key-%E2%80%94-per-hook-environment-variables)
  - [`priority` — execution order control](#priority-%E2%80%94-execution-order-control)
  - [Glob patterns — readable file filters](#glob-patterns-%E2%80%94-readable-file-filters)
  - [Workspace mode — monorepo support](#workspace-mode-%E2%80%94-monorepo-support)
- [6. CI/CD Migration Patterns](#6-cicd-migration-patterns)
  - [GitHub Actions](#github-actions)
  - [Docker](#docker)
  - [Generic CI (GitLab CI, Buildkite, CircleCI, etc.)](#generic-ci-gitlab-ci-buildkite-circleci-etc)
  - [Cache key migration](#cache-key-migration)
- [7. Rollback Strategy](#7-rollback-strategy)
  - [During migration: keep both config files](#during-migration-keep-both-config-files)
  - [To revert to pre-commit](#to-revert-to-pre-commit)
  - [If you deleted `.pre-commit-config.yaml`](#if-you-deleted-pre-commit-configyaml)
  - [Team communication checklist](#team-communication-checklist)

<!-- mdformat-toc end -->

---

## 1. Pre-Migration Checklist<a name="1-pre-migration-checklist"></a>

Before beginning migration, verify the following:

- [ ] **prek is installed** — run `prek --version` and confirm output like `prek 0.3.8`
- [ ] **Unsupported languages** — prek does NOT support the following language values; if your config uses any, those
  hooks will need to be replaced or removed:
  - `conda`
  - `coursier`
  - `dart`
  - `dotnet`
  - `perl`
  - `r`
- [ ] **`pre-commit hazmat` usage** — the `hazmat` subcommand is not implemented in prek. Audit any scripts or Makefiles
  that invoke it.
- [ ] **CI/CD pipelines** — note every pipeline that calls `pre-commit` directly; these will need updated commands (see
  Section 6).
- [ ] **`pre-commit migrate-config`** — if any scripts or docs reference this command, replace with
  `prek util yaml-to-toml` (see Section 4).

---

## 2. Compatibility Matrix<a name="2-compatibility-matrix"></a>

| Feature                             | pre-commit                       | prek                       | Notes                                                 |
| ----------------------------------- | -------------------------------- | -------------------------- | ----------------------------------------------------- |
| `.pre-commit-config.yaml` support   | Yes                              | Yes                        | prek reads existing YAML configs without modification |
| `prek.toml` support                 | No                               | Yes                        | Native TOML config format; optional migration         |
| `repo: builtin`                     | No                               | Yes                        | Zero-network, Rust-native built-in hooks              |
| Glob patterns for `files`/`exclude` | No                               | Yes                        | `{ glob = "*.py" }` instead of regex                  |
| `env` per hook                      | No                               | Yes                        | Set environment variables scoped to a single hook     |
| `priority` ordering                 | No                               | Yes                        | Integer priority controls cross-repo execution order  |
| Workspace mode                      | No                               | Yes                        | Monorepo support with nested configs                  |
| `hazmat` helpers                    | Yes                              | No                         | No prek equivalent; migrate or remove                 |
| `conda` language                    | Yes                              | No                         | Not supported in prek                                 |
| `coursier` language                 | Yes                              | No                         | Not supported in prek                                 |
| `dart` language                     | Yes                              | No                         | Not supported in prek                                 |
| `dotnet` language                   | Yes                              | No                         | Not supported in prek                                 |
| `perl` language                     | Yes                              | No                         | Not supported in prek                                 |
| `r` language                        | Yes                              | No                         | Not supported in prek                                 |
| `autoupdate` command                | Yes (`pre-commit autoupdate`)    | Yes (`prek auto-update`)   | Renamed with hyphen                                   |
| `install-hooks` command             | Yes (`pre-commit install-hooks`) | Yes (`prek prepare-hooks`) | Renamed                                               |
| `gc` command                        | Yes (`pre-commit gc`)            | Yes (`prek cache gc`)      | Moved under `cache` subcommand                        |
| `clean` command                     | Yes (`pre-commit clean`)         | Yes (`prek cache clean`)   | Moved under `cache` subcommand                        |

---

## 3. Step-by-Step Migration<a name="3-step-by-step-migration"></a>

### Step 1: Install prek<a name="step-1-install-prek"></a>

Choose one method:

```bash
# Homebrew (macOS/Linux)
brew install j178/tap/prek

# uv (recommended for Python projects)
uv tool install prek

# pip
pip install prek

# Standalone installer (Linux/macOS)
curl -fsSL https://raw.githubusercontent.com/j178/prek/main/install.sh | sh
```

Verify: `prek --version`

### Step 2: Test your existing config<a name="step-2-test-your-existing-config"></a>

prek reads `.pre-commit-config.yaml` directly — no conversion needed for this step.

```bash
# Run all hooks against all files using your existing YAML config
prek run --all-files
```

Investigate any failures before proceeding. If hooks that worked under pre-commit now fail, check whether any use
unsupported languages (see Section 1).

### Step 3: Reinstall git shims<a name="step-3-reinstall-git-shims"></a>

Replace pre-commit's git hook shims with prek's:

```bash
# -f overwrites pre-commit's existing shims
prek install -f
```

From this point on, git operations trigger prek instead of pre-commit.

### Step 4: (Optional) Convert config to TOML<a name="step-4-optional-convert-config-to-toml"></a>

If you want to adopt the native `prek.toml` format:

```bash
# Automated conversion
prek util yaml-to-toml
```

This reads `.pre-commit-config.yaml` and writes `prek.toml`. Review the output before committing. See Section 4 for
manual conversion rules.

### Step 5: (Optional) Replace remote hooks with built-ins<a name="step-5-optional-replace-remote-hooks-with-built-ins"></a>

prek ships built-in hooks that replace many common `pre-commit-hooks` entries. This eliminates network fetches and
speeds up hook installation.

**Before (YAML, remote hooks):**

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-json
```

**After (TOML, built-in hooks):**

```toml
[[repos]]
repo = "builtin"
hooks = [
  { id = "trailing-whitespace" },
  { id = "end-of-file-fixer" },
  { id = "check-yaml" },
  { id = "check-json" },
]
```

Run `prek builtin --list` to see all available built-in hook IDs.

### Step 6: Update CI/CD pipelines<a name="step-6-update-cicd-pipelines"></a>

Replace all `pre-commit` invocations with `prek` equivalents. See Section 6 for detailed before/after examples.

Quick reference for renamed commands:

| Old command                  | New command              |
| ---------------------------- | ------------------------ |
| `pre-commit autoupdate`      | `prek auto-update`       |
| `pre-commit install-hooks`   | `prek prepare-hooks`     |
| `pre-commit gc`              | `prek cache gc`          |
| `pre-commit clean`           | `prek cache clean`       |
| `pre-commit run --all-files` | `prek run --all-files`   |
| `pre-commit migrate-config`  | `prek util yaml-to-toml` |

### Step 7: Update team documentation<a name="step-7-update-team-documentation"></a>

- Update your project's README, CONTRIBUTING, and onboarding guides to reference `prek`
- Replace any `pre-commit` install instructions
- Communicate the migration to the team with rollback instructions (see Section 7)

---

## 4. YAML-to-TOML Conversion Guide<a name="4-yaml-to-toml-conversion-guide"></a>

### Manual conversion rules<a name="manual-conversion-rules"></a>

**Top-level keys** map directly to TOML key-value pairs:

```yaml
# YAML
default_language_version:
  python: python3.11
fail_fast: true
```

```toml
# TOML
fail_fast = true

[default_language_version]
python = "python3.11"
```

**`repos` list** becomes an array of TOML tables using `[[repos]]`:

```yaml
# YAML
repos:
  - repo: https://github.com/psf/black
    rev: 24.4.2
    hooks:
      - id: black
```

```toml
# TOML
[[repos]]
repo = "https://github.com/psf/black"
rev = "24.4.2"
hooks = [{ id = "black" }]
```

**`hooks` list** can be written inline or expanded:

```toml
# Inline (compact)
hooks = [{ id = "black", args = ["--line-length", "120"] }]

# Expanded (readable for complex hooks)
[[repos.hooks]]
id = "black"
args = ["--line-length", "120"]
```

**String values** require quotes in TOML; YAML often leaves them unquoted:

```yaml
# YAML
rev: v4.6.0
```

```toml
# TOML
rev = "v4.6.0"
```

**Lists** use the same bracket syntax, but string elements need quotes:

```yaml
# YAML
types: [python, pyi]
```

```toml
# TOML
types = ["python", "pyi"]
```

**Booleans** are identical in both formats: `true` / `false`.

**Regex patterns** work unchanged in TOML. prek additionally supports glob syntax as an alternative:

```toml
# Regex (same as pre-commit)
files = "\\.py$"

# Glob (prek-only, more readable)
files = { glob = "*.py" }
```

### Full before/after example<a name="full-beforeafter-example"></a>

**Before — `.pre-commit-config.yaml`:**

```yaml
default_language_version:
  python: python3.11
fail_fast: false
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
        args: [--unsafe]
      - id: check-merge-conflict
  - repo: https://github.com/psf/black
    rev: 24.4.2
    hooks:
      - id: black
        args: [--line-length, '120']
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.4.4
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
```

**After — `prek.toml`:**

```toml
fail_fast = false

[default_language_version]
python = "python3.11"

[[repos]]
repo = "builtin"
hooks = [
  { id = "trailing-whitespace" },
  { id = "end-of-file-fixer" },
  { id = "check-yaml", args = ["--unsafe"] },
  { id = "check-merge-conflict" },
]

[[repos]]
repo = "https://github.com/psf/black"
rev = "24.4.2"
hooks = [{ id = "black", args = ["--line-length", "120"] }]

[[repos]]
repo = "https://github.com/astral-sh/ruff-pre-commit"
rev = "v0.4.4"
hooks = [
  { id = "ruff", args = ["--fix"] },
  { id = "ruff-format" },
]
```

---

## 5. Post-Migration: prek-Only Improvements<a name="5-post-migration-prek-only-improvements"></a>

Once migrated, take advantage of features unavailable in pre-commit.

### Built-in hooks (`repo: builtin`)<a name="built-in-hooks-repo-builtin"></a>

Replace remote hook repos with prek's bundled Rust-native hooks. Benefits: faster install, no network required, no
version pinning needed.

```toml
[[repos]]
repo = "builtin"
hooks = [
  { id = "trailing-whitespace" },
  { id = "end-of-file-fixer" },
  { id = "check-yaml" },
  { id = "check-json" },
  { id = "check-toml" },
  { id = "mixed-line-ending" },
]
```

Run `prek builtin --list` for the full catalog.

### `env` key — per-hook environment variables<a name="env-key-%E2%80%94-per-hook-environment-variables"></a>

Set environment variables scoped to a single hook without polluting the shell environment:

```toml
[[repos]]
repo = "https://github.com/astral-sh/ruff-pre-commit"
rev = "v0.4.4"

[[repos.hooks]]
id = "ruff"
env = { RUFF_CONFIG = "pyproject.toml", PYTHONPATH = "src" }
```

### `priority` — execution order control<a name="priority-%E2%80%94-execution-order-control"></a>

Lower integers run first. Useful for ensuring formatters run before linters:

```toml
[[repos]]
repo = "https://github.com/psf/black"
rev = "24.4.2"
hooks = [{ id = "black", priority = 10 }] # runs first

[[repos]]
repo = "https://github.com/astral-sh/ruff-pre-commit"
rev = "v0.4.4"
hooks = [{ id = "ruff", priority = 20, args = ["--fix"] }] # runs second
```

Default priority is `0`; negative values run before the default group.

### Glob patterns — readable file filters<a name="glob-patterns-%E2%80%94-readable-file-filters"></a>

Use shell-style globs instead of Python regex for `files` and `exclude`:

```toml
# Old (regex, pre-commit style — still works in prek)
files = "\\.py$"
exclude = "^tests/"

# New (glob, prek-only — more readable)
files = { glob = "*.py" }
exclude = { glob = "tests/**" }
```

### Workspace mode — monorepo support<a name="workspace-mode-%E2%80%94-monorepo-support"></a>

For repositories with nested prek configs, workspace mode discovers and aggregates them:

```bash
# Run hooks across all workspace members
prek run --all-files --workspace
```

Configure workspace roots in the top-level `prek.toml`:

```toml
[workspace]
members = ["services/*", "libs/*"]
```

---

## 6. CI/CD Migration Patterns<a name="6-cicd-migration-patterns"></a>

### GitHub Actions<a name="github-actions"></a>

**Before:**

```yaml
  - name: Run pre-commit
    uses: pre-commit/action@v3.0.1
    with:
      extra_args: --all-files
```

**After:**

```yaml
  - name: Run prek
    uses: j178/prek-action@v1
    with:
      args: --all-files
```

For cache configuration with prek-action:

```yaml
  - name: Cache prek environments
    uses: actions/cache@v4
    with:
      path: ~/.cache/prek
      key: prek-${{ runner.os }}-${{ hashFiles('prek.toml', 
        '.pre-commit-config.yaml') }}
```

### Docker<a name="docker"></a>

**Before:**

```dockerfile
RUN pip install pre-commit && pre-commit run --all-files
```

**After:**

```dockerfile
COPY --from=ghcr.io/j178/prek:v0.3.8 /prek /usr/local/bin/prek
RUN prek run --all-files
```

Or using the official prek image as a base stage:

```dockerfile
FROM ghcr.io/j178/prek:v0.3.8 AS prek-bin

FROM python:3.11-slim
COPY --from=prek-bin /prek /usr/local/bin/prek
RUN prek run --all-files
```

### Generic CI (GitLab CI, Buildkite, CircleCI, etc.)<a name="generic-ci-gitlab-ci-buildkite-circleci-etc"></a>

Replace `pre-commit run --all-files` with `prek run --all-files`. The exit code semantics are identical: `0` for pass,
non-zero for failure.

**GitLab CI example:**

```yaml
lint:
  stage: lint
  script:
    - pip install prek  # or use uv tool install prek
    - prek run --all-files
  cache:
    key: prek-$CI_COMMIT_REF_SLUG
    paths:
      - ~/.cache/prek
```

### Cache key migration<a name="cache-key-migration"></a>

prek uses a different cache directory than pre-commit. Update your cache keys:

|                      | pre-commit                                               | prek                                 |
| -------------------- | -------------------------------------------------------- | ------------------------------------ |
| Environment variable | `PRE_COMMIT_HOME`                                        | `PREK_HOME`                          |
| Default cache path   | `~/.cache/pre-commit`                                    | `~/.cache/prek`                      |
| CI cache key example | `pre-commit-${{ hashFiles('.pre-commit-config.yaml') }}` | `prek-${{ hashFiles('prek.toml') }}` |

---

## 7. Rollback Strategy<a name="7-rollback-strategy"></a>

### During migration: keep both config files<a name="during-migration-keep-both-config-files"></a>

While transitioning, keep `.pre-commit-config.yaml` alongside `prek.toml`. prek prefers `prek.toml` if both are present,
but the YAML file remains available for rollback.

```
your-repo/
├── .pre-commit-config.yaml   # keep during transition
├── prek.toml                 # new config
└── ...
```

### To revert to pre-commit<a name="to-revert-to-pre-commit"></a>

```bash
# Uninstall prek git shims
prek uninstall

# Reinstall pre-commit shims
pre-commit install

# Verify pre-commit is running
pre-commit run --all-files
```

### If you deleted `.pre-commit-config.yaml`<a name="if-you-deleted-pre-commit-configyaml"></a>

The `prek util yaml-to-toml` conversion is one-way — there is no `toml-to-yaml` command. However:

1. The original YAML file is preserved in git history. Recover it with:
   ```bash
   git show HEAD~N:.pre-commit-config.yaml > .pre-commit-config.yaml
   ```
2. Alternatively, reconstruct from `prek.toml` manually — the structure maps directly (see Section 4 in reverse).

### Team communication checklist<a name="team-communication-checklist"></a>

When rolling out migration to a team:

- [ ] Announce the migration date and rationale in your team channel
- [ ] Share a link to this guide and to the [prek documentation](https://github.com/j178/prek)
- [ ] Provide explicit rollback instructions (commands above)
- [ ] Set a transition window (e.g., 2 weeks) during which both configs are supported
- [ ] Pin the prek version in CI to avoid surprise upgrades
- [ ] After the transition window, remove `.pre-commit-config.yaml` from the repo in a dedicated commit so the rollback
  path through git history remains clear
