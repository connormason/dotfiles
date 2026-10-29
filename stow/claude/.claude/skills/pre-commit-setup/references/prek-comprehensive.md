# prek Comprehensive Reference

prek is a Rust-based, dependency-free reimplementation of pre-commit. It is a drop-in replacement: existing
`.pre-commit-config.yaml` files work without modification. Official docs: https://prek.j178.dev

<!-- mdformat-toc start --slug=github --maxlevel=3 --minlevel=2 -->

- [1. Full CLI Reference](#1-full-cli-reference)
  - [Global Options](#global-options)
  - [Hook Selector Syntax](#hook-selector-syntax)
  - [`prek install`](#prek-install)
  - [`prek prepare-hooks`](#prek-prepare-hooks)
  - [`prek uninstall`](#prek-uninstall)
  - [`prek run [selectors]`](#prek-run-selectors)
  - [`prek list`](#prek-list)
  - [`prek try-repo REPO`](#prek-try-repo-repo)
  - [`prek validate-config`](#prek-validate-config)
  - [`prek validate-manifest`](#prek-validate-manifest)
  - [`prek sample-config`](#prek-sample-config)
  - [`prek auto-update`](#prek-auto-update)
  - [`prek cache`](#prek-cache)
  - [`prek self update`](#prek-self-update)
  - [`prek util`](#prek-util)
- [2. Supported Languages](#2-supported-languages)
  - [Fully Supported](#fully-supported)
  - [Not Yet Supported](#not-yet-supported)
  - [Toolchain Auto-Download](#toolchain-auto-download)
- [3. Workspace Mode](#3-workspace-mode)
  - [Discovery](#discovery)
  - [Execution Order](#execution-order)
  - [`orphan: true`](#orphan-true)
  - [Selector Syntax in Workspace Context](#selector-syntax-in-workspace-context)
  - [Single Config Mode](#single-config-mode)
  - [Cache](#cache)
  - [Example: Monorepo with Orphan Sub-project](#example-monorepo-with-orphan-sub-project)
- [4. Hook Authoring](#4-hook-authoring)
  - [Manifest Format](#manifest-format)
  - [Required Keys](#required-keys)
  - [Optional Keys](#optional-keys)
  - [Stages](#stages)
  - [Argument Passing](#argument-passing)
  - [Versioning for `prek auto-update`](#versioning-for-prek-auto-update)
  - [Testing a Hook Locally](#testing-a-hook-locally)
  - [Validating the Manifest](#validating-the-manifest)
- [5. CI/CD Integration](#5-cicd-integration)
  - [Docker](#docker)
  - [GitHub Actions](#github-actions)
  - [Alternative Installation via `taiki-e/install-action`](#alternative-installation-via-taiki-einstall-action)
  - [Standalone curl Installer in CI](#standalone-curl-installer-in-ci)
- [6. Debugging](#6-debugging)
  - [Verbose Output](#verbose-output)
  - [Log Files](#log-files)
  - [Common Diagnostic Steps](#common-diagnostic-steps)
- [7. FAQ](#7-faq)
- [8. Compatibility with pre-commit](#8-compatibility-with-pre-commit)
  - [Full Compatibility](#full-compatibility)
  - [Legacy Command Aliases](#legacy-command-aliases)
  - [Not Implemented](#not-implemented)
  - [Portability Recommendations](#portability-recommendations)
- [9. Installation](#9-installation)
  - [Standalone Installers](#standalone-installers)
  - [Package Managers](#package-managers)
  - [Docker](#docker-1)
  - [From Source](#from-source)
  - [Self-Update](#self-update)
  - [Shell Completions](#shell-completions)

<!-- mdformat-toc end -->

---

## 1. Full CLI Reference<a name="1-full-cli-reference"></a>

### Global Options<a name="global-options"></a>

These options apply to every command.

| Flag                | Short | Description                                                    |
| ------------------- | ----- | -------------------------------------------------------------- |
| `--config <path>`   | `-c`  | Use an alternate configuration file                            |
| `--cd <dir>`        | `-C`  | Change working directory before running                        |
| `--color <mode>`    |       | Output coloring: `auto` (default), `always`, `never`           |
| `--verbose`         | `-v`  | Detailed output (stackable: `-vvv` for trace-level tracing)    |
| `--quiet`           | `-q`  | Suppress output (stackable for silent mode)                    |
| `--log-file <path>` |       | Write trace logs to a specific file                            |
| `--no-progress`     |       | Hide progress indicators                                       |
| `--refresh`         |       | Clear the workspace discovery cache before running             |
| `--skip <selector>` |       | Exclude specific hooks or projects (see selector syntax below) |
| `--version`         | `-V`  | Show prek version                                              |
| `--help`            | `-h`  | Display help for any command                                   |

### Hook Selector Syntax<a name="hook-selector-syntax"></a>

Selectors are used with `prek run [selectors]`, `--skip`, and `PREK_SKIP`.

| Pattern                | Meaning                                        |
| ---------------------- | ---------------------------------------------- |
| `hook-id`              | All hooks matching this ID across all projects |
| `project-path/`        | All hooks from the specified project directory |
| `project-path:hook-id` | A specific hook from a specific project        |

For hook IDs that themselves contain colons (e.g., `lint:ruff`), prefix with `:` — e.g., `prek run :lint:ruff`.

---

### `prek install`<a name="prek-install"></a>

Deploy git shims to `.git/hooks/`. Does not prepare environments by default.

```sh
prek install                        # Install git shims for pre-commit stage
prek install -f                     # Force overwrite existing shims
prek install --prepare-hooks        # Install shims and prepare all hook environments
prek install -t pre-push            # Install shim for a specific hook type
prek install -t pre-commit -t pre-push  # Install shims for multiple hook types
```

| Flag                       | Description                                            |
| -------------------------- | ------------------------------------------------------ |
| `-f`, `--overwrite`        | Overwrite existing hook shims                          |
| `--prepare-hooks`          | Also prepare environments for all configured hooks     |
| `-t`, `--hook-type <type>` | Install shim for a specific git hook type (repeatable) |
| `--allow-missing-config`   | Do not fail if no config file is found                 |
| `--git-dir <path>`         | Use an alternate `.git` directory                      |

---

### `prek prepare-hooks`<a name="prek-prepare-hooks"></a>

Set up isolated environments for all configured hooks without installing git shims. Useful in CI to warm the cache
before the first commit.

```sh
prek prepare-hooks
```

---

### `prek uninstall`<a name="prek-uninstall"></a>

Remove git hook shims installed by `prek install`.

```sh
prek uninstall
```

---

### `prek run [selectors]`<a name="prek-run-selectors"></a>

Execute hooks. Without arguments, runs against staged files.

```sh
prek run                                     # Run hooks on staged files
prek run ruff                                # Run only the 'ruff' hook
prek run frontend/                           # Run all hooks for the frontend project
prek run frontend:ruff                       # Run ruff in the frontend project only
prek run --all-files                         # Run on all tracked files
prek run --files src/foo.py src/bar.py       # Run on specific files
prek run --from-ref HEAD~1 --to-ref HEAD     # Run on files changed between two refs
prek run --last-commit                       # Run on files changed in the last commit
prek run --hook-stage pre-push              # Run hooks for a specific git hook stage
prek run --directory services/api/           # Run from a specific directory
prek run --skip ruff                         # Skip a hook by ID
prek run --skip frontend/                    # Skip an entire project
```

| Flag                     | Short | Description                                             |
| ------------------------ | ----- | ------------------------------------------------------- |
| `--all-files`            | `-a`  | Run on all tracked files instead of staged files        |
| `--files <file>...`      |       | Run on specific files (space-separated)                 |
| `--from-ref <ref>`       | `-s`  | Start ref for diff-based file selection                 |
| `--to-ref <ref>`         | `-o`  | End ref for diff-based file selection                   |
| `--last-commit`          |       | Run on files changed in the last commit                 |
| `--hook-stage <stage>`   |       | Execute hooks declared for this specific git hook stage |
| `--directory <dir>`      | `-d`  | Change to this directory before running                 |
| `--skip <selector>`      |       | Skip a hook or project (repeatable)                     |
| `--fail-fast`            |       | Stop on first hook failure                              |
| `--show-diff-on-failure` |       | Print a diff when any hook fails                        |
| `--dry-run`              |       | Show what would run without executing                   |

---

### `prek list`<a name="prek-list"></a>

Display all configured hooks and their metadata.

```sh
prek list
prek list --hook-stage pre-push
prek list --language python
prek list --output-format json
```

| Flag                    | Description                               |
| ----------------------- | ----------------------------------------- |
| `--hook-stage <stage>`  | Filter to hooks for a specific stage      |
| `--language <lang>`     | Filter to hooks using a specific language |
| `--output-format <fmt>` | Output format: `text` (default) or `json` |

---

### `prek try-repo REPO`<a name="prek-try-repo-repo"></a>

Fetch and test hooks from a repository without installing them into the current project. Useful when developing or
evaluating a hook repository.

```sh
prek try-repo https://github.com/astral-sh/ruff-pre-commit
prek try-repo https://github.com/astral-sh/ruff-pre-commit --rev v0.11.0
prek try-repo ../path/to/local/hook-repo my-hook-id --verbose
prek try-repo ../path/to/local/hook-repo --all-files
```

Accepts most `prek run` flags (`--all-files`, `--files`, `--from-ref`, `--to-ref`, etc.) plus `--rev`/`--ref` to pin a
specific revision.

---

### `prek validate-config`<a name="prek-validate-config"></a>

Validate a prek configuration file (`prek.toml` or `.pre-commit-config.yaml`).

```sh
prek validate-config
prek validate-config --config path/to/prek.toml
```

---

### `prek validate-manifest`<a name="prek-validate-manifest"></a>

Validate a `.pre-commit-hooks.yaml` hook manifest.

```sh
prek validate-manifest
prek validate-manifest .pre-commit-hooks.yaml
```

---

### `prek sample-config`<a name="prek-sample-config"></a>

Print a sample configuration to stdout. Useful as a starting point.

```sh
prek sample-config
prek sample-config > .pre-commit-config.yaml
```

---

### `prek auto-update`<a name="prek-auto-update"></a>

Update the `rev` field of each repo in the configuration to the latest version.

```sh
prek auto-update                          # Update all repos to latest semver tag
prek auto-update --bleeding-edge          # Update to the latest commit (not just tags)
prek auto-update --freeze                 # Pin to exact commit SHAs instead of tags
prek auto-update --repo https://github.com/astral-sh/ruff-pre-commit  # Update one repo
prek auto-update --dry-run                # Preview changes without writing
prek auto-update --cooldown-days 7        # Skip repos updated within the last N days
prek auto-update -j 4                     # Use 4 parallel jobs
```

| Flag                  | Short | Description                                                       |
| --------------------- | ----- | ----------------------------------------------------------------- |
| `--bleeding-edge`     |       | Use the latest commit on the default branch instead of latest tag |
| `--freeze`            |       | Write exact commit SHAs rather than version tags                  |
| `--repo <url>`        |       | Update only this specific repository (repeatable)                 |
| `--dry-run`           |       | Show what would change without modifying the config file          |
| `--cooldown-days <n>` |       | Do not update repos last updated within this many days            |
| `--jobs <n>`          | `-j`  | Number of parallel update jobs                                    |

---

### `prek cache`<a name="prek-cache"></a>

Manage the prek cache of downloaded environments and repositories.

```sh
prek cache dir       # Print the cache directory path
prek cache gc        # Remove environments no longer referenced by any config
prek cache gc --dry-run  # Preview what would be removed
prek cache clean     # Remove all cached data
prek cache size      # Print total disk usage of the cache
```

---

### `prek self update`<a name="prek-self-update"></a>

Update prek itself to the latest release. Works regardless of how prek was installed.

```sh
prek self update
```

---

### `prek util`<a name="prek-util"></a>

Utility subcommands for file inspection, template setup, and configuration conversion.

#### `prek util identify`

Tag a file with the type identifiers prek would use for hook filtering (`types`, `types_or`, `exclude_types`).

```sh
prek util identify src/main.py
prek util identify package.json
```

#### `prek util list-builtins`

List all available hook IDs from `repo = "builtin"`.

```sh
prek util list-builtins
```

#### `prek util init-template-dir`

Populate a git template directory with prek shims so that `git clone` and `git init` automatically install the hooks.

```sh
prek util init-template-dir ~/.git-template
git config --global init.templateDir ~/.git-template
```

#### `prek util yaml-to-toml`

Convert an existing `.pre-commit-config.yaml` to `prek.toml` format.

```sh
prek util yaml-to-toml                               # Reads .pre-commit-config.yaml, prints TOML
prek util yaml-to-toml --output prek.toml            # Write output to file
```

---

## 2. Supported Languages<a name="2-supported-languages"></a>

prek manages isolated environments per hook repository and per language version. For supported languages, prek
automatically downloads the required toolchain if a matching system installation is not found.

### Fully Supported<a name="fully-supported"></a>

| Language       | Environment Mechanism                                      | Notes                                                      |
| -------------- | ---------------------------------------------------------- | ---------------------------------------------------------- |
| `bun`          | `bun install` from `package.json`                          | Semver version selectors; prek-only (not in pre-commit)    |
| `docker`       | Bind-mounted container via Docker daemon                   | Auto-detects runtime; builds from `Dockerfile`             |
| `docker_image` | Pre-built Docker image                                     | No build step; pulls image directly                        |
| `fail`         | No environment; always fails with entry text               | Useful for blocking patterns                               |
| `golang`       | `go install ./...` in isolated `GOPATH`                    | Semver version selectors; toolchain auto-download          |
| `haskell`      | `cabal` build                                              |                                                            |
| `julia`        | Julia built-in package manager from `Project.toml`         |                                                            |
| `lua`          | `luarocks` installation                                    |                                                            |
| `node`         | `npm install .` from `package.json`                        | Semver and `lts` selectors; toolchain auto-download        |
| `python`       | `uv pip install` into isolated virtualenv                  | Semver selectors; PEP 723 inline script metadata; uv-based |
| `pygrep`       | No environment; runs regex against file contents           | Supports flags (e.g., case-insensitive)                    |
| `ruby`         | Gems from `*.gemspec`; executables declared in gemspec     | Semver selectors; `rv` toolchain auto-download             |
| `rust`         | `cargo install --bins --locked`                            | Semver selectors; toolchain auto-download                  |
| `swift`        | `Package.swift` built in release mode                      | Requires system Swift installation                         |
| `system`       | No environment; uses system PATH                           |                                                            |
| `script`       | No environment; runs repository script directly            |                                                            |
| `deno`         | `deno install --global` for each `additional_dependencies` | Supports npm: and JSR: specifiers; prek-only               |

### Not Yet Supported<a name="not-yet-supported"></a>

The following languages are tracked as open issues and not yet implemented:

- `conda` (issue #52)
- `coursier` (issue #53)
- `dart` (issue #51)
- `dotnet` (issue #48)
- `perl` (issue #1447)
- `r` (issue #42)

### Toolchain Auto-Download<a name="toolchain-auto-download"></a>

prek resolves toolchains in two steps: first it discovers system installations, then it downloads a matching toolchain
when the system version does not satisfy the requested version specifier. Languages with automatic toolchain download:
Python, Node, Bun, Deno, Go, Rust, Ruby.

Version specifiers in `language_version` accept semver ranges (`^1.2`, `>=1.5, <2.0`) and special selectors (`lts` for
Node). Set versions globally with `default_language_version` or per hook with `language_version`.

---

## 3. Workspace Mode<a name="3-workspace-mode"></a>

Workspace mode enables a monorepo to have multiple independent (or hierarchically related) prek configurations, one per
sub-project.

### Discovery<a name="discovery"></a>

On each run, prek traverses upward from the current directory until it finds a root config (`prek.toml` or
`.pre-commit-config.yaml`). It then recursively searches subdirectories for additional configs. Discovery respects git
boundaries — it will not cross into a nested git repository.

**Excluded from discovery:**

- Dot-prefixed directories (`.git/`, `.venv/`, etc.)
- Cookiecutter template directories
- Paths listed in `.gitignore`
- Paths listed in `.prekignore` (same syntax as `.gitignore`)

After changes to `.prekignore` or new configs are added, run with `--refresh` to rebuild the cache.

### Execution Order<a name="execution-order"></a>

Projects run **deepest-to-shallowest**. Each project can only see files within its own directory tree — hooks in
`frontend/` cannot process files in `backend/`.

By default, a file in a nested directory is processed by every project in the ancestor chain. Use `orphan` to prevent
this.

### `orphan: true`<a name="orphan-true"></a>

Setting `orphan: true` at the top level of a sub-project config marks that project as self-contained. Files in an orphan
project are not passed to parent project hooks — the orphan "consumes" them.

```toml
# services/api/prek.toml
orphan = true

[[repos]]
repo = "builtin"
hooks = [
  { id = "trailing-whitespace" },
  { id = "end-of-file-fixer" },
]
```

### Selector Syntax in Workspace Context<a name="selector-syntax-in-workspace-context"></a>

```sh
prek run ruff                    # Run ruff in all projects
prek run frontend/               # Run all hooks in the frontend project
prek run frontend:ruff           # Run ruff only in the frontend project
prek run --skip backend/         # Skip the entire backend project
PREK_SKIP=backend/,frontend:eslint prek run
```

For hook IDs containing colons, prefix with `:`: `prek run :lint:ruff`.

### Single Config Mode<a name="single-config-mode"></a>

Passing `--config path/to/config` disables workspace discovery entirely. Hooks run from the git root on all repository
files — this restores traditional pre-commit behavior.

```sh
prek run --config services/api/prek.toml --all-files
```

### Cache<a name="cache"></a>

Workspace discovery results are cached automatically. The cache is invalidated on most structural changes. For new
configs or `.prekignore` modifications, force a refresh:

```sh
prek run --refresh
```

### Example: Monorepo with Orphan Sub-project<a name="example-monorepo-with-orphan-sub-project"></a>

```toml
# prek.toml (repo root) — global hooks for all projects
[[repos]]
repo = "builtin"
hooks = [
  { id = "check-merge-conflict" },
  { id = "detect-private-key" },
  { id = "no-commit-to-branch", args = ["-b", "main"] },
]
```

```toml
# services/api/prek.toml — isolated; root hooks do not process these files
orphan = true

[[repos]]
repo = "https://github.com/astral-sh/ruff-pre-commit"
rev = "v0.11.0"
hooks = [
  { id = "ruff", args = ["--fix"] },
  { id = "ruff-format" },
]
```

---

## 4. Hook Authoring<a name="4-hook-authoring"></a>

prek hook repositories use the same manifest format as pre-commit and are fully interoperable.

### Manifest Format<a name="manifest-format"></a>

Create `.pre-commit-hooks.yaml` at the repository root. Each entry is a hook definition.

```yaml
  - id: my-linter
    name: My Linter
    description: Check code style.
    entry: my-linter
    language: python
    types: [python]
    args: []
    stages: [pre-commit, pre-push]
```

### Required Keys<a name="required-keys"></a>

| Key        | Description                                                             |
| ---------- | ----------------------------------------------------------------------- |
| `id`       | Stable identifier used in end-user configs (`hooks: [{id: my-linter}]`) |
| `name`     | Human-friendly label shown in output                                    |
| `entry`    | Command to execute                                                      |
| `language` | Execution environment (e.g., `python`, `node`, `system`)                |

### Optional Keys<a name="optional-keys"></a>

| Key                       | Description                                           |
| ------------------------- | ----------------------------------------------------- |
| `args`                    | Default argument list prepended before file paths     |
| `files`                   | Regex (or glob in prek) to include files              |
| `exclude`                 | Regex (or glob in prek) to exclude files              |
| `types` / `types_or`      | File type filtering (AND / OR logic)                  |
| `exclude_types`           | File types to exclude                                 |
| `stages`                  | Declare which git hook stages this hook supports      |
| `require_serial`          | Disable parallel execution of this hook               |
| `pass_filenames`          | Whether to append matched filenames (default: `true`) |
| `always_run`              | Run even when no files match                          |
| `description`             | Documentation string                                  |
| `language_version`        | Minimum or exact version of the language runtime      |
| `additional_dependencies` | Extra packages to install into the hook environment   |

### Stages<a name="stages"></a>

Declare the stages a hook supports via the `stages` key. Supported stage values: `pre-commit`, `pre-merge-commit`,
`prepare-commit-msg`, `commit-msg`, `post-commit`, `post-checkout`, `pre-push`, `post-rewrite`, `post-merge`, `manual`.

The `manual` stage is special: it **never runs automatically**. It must be invoked explicitly:

```sh
prek run --hook-stage manual my-hook-id
```

### Argument Passing<a name="argument-passing"></a>

User-supplied `args` are prepended before file paths:

```
my-hook --max-line-length=120 path/to/file1 path/to/file2
```

### Versioning for `prek auto-update`<a name="versioning-for-prek-auto-update"></a>

- Use semantic version tags (`v1.2.3` or `1.2.3`)
- Push tags to the remote (annotated or lightweight both work)
- Treat tags as immutable; never force-push a tag
- `--bleeding-edge` uses the default branch head; `--freeze` writes commit SHAs

### Testing a Hook Locally<a name="testing-a-hook-locally"></a>

```sh
prek try-repo ../path/to/hook-repo hook-id --verbose
prek try-repo ../path/to/hook-repo hook-id --all-files
# For commit-msg hooks:
prek try-repo ../path/to/hook-repo hook-id --commit-msg-filename .git/COMMIT_EDITMSG
```

### Validating the Manifest<a name="validating-the-manifest"></a>

```sh
prek validate-manifest .pre-commit-hooks.yaml
```

---

## 5. CI/CD Integration<a name="5-cicd-integration"></a>

### Docker<a name="docker"></a>

prek publishes a distroless container image. The image contains only the prek binary at `/prek`.

```dockerfile
# Copy prek binary into your own image
COPY --from=ghcr.io/j178/prek:v0.3.8 /prek /usr/local/bin/prek
```

**Verify image authenticity with GitHub Attestations:**

```sh
gh attestation verify --owner j178 oci://ghcr.io/j178/prek:latest
gh attestation verify --owner j178 oci://ghcr.io/j178/prek:v0.3.8
```

Use specific version tags (not `latest`) in production for reproducible verification.

### GitHub Actions<a name="github-actions"></a>

Use the official `j178/prek-action`:

```yaml
name: Pre-commit checks
on: [push, pull_request]

jobs:
  prek:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: j178/prek-action@v2
```

The action installs prek and runs `prek run --all-files` by default.

### Alternative Installation via `taiki-e/install-action`<a name="alternative-installation-via-taiki-einstall-action"></a>

```yaml
  - uses: taiki-e/install-action@v2
    with:
      tool: prek
```

### Standalone curl Installer in CI<a name="standalone-curl-installer-in-ci"></a>

```sh
curl --proto '=https' --tlsv1.2 -LsSf \
  https://github.com/j178/prek/releases/download/v0.3.8/prek-installer.sh | sh
prek run --all-files
```

---

## 6. Debugging<a name="6-debugging"></a>

### Verbose Output<a name="verbose-output"></a>

Increase verbosity with stacked `-v` flags:

```sh
prek run -v       # Basic verbose
prek run -vv      # More detail
prek run -vvv     # Trace-level output
```

### Log Files<a name="log-files"></a>

prek writes a log file on every run:

- **Default path**: `~/.cache/prek/prek.log`
- Override with: `prek run --log-file /path/to/custom.log`

The log captures timing, environment setup, hook invocations, and errors. Always include this file when reporting
issues.

### Common Diagnostic Steps<a name="common-diagnostic-steps"></a>

1. Run `prek run -vvv` to see exactly which files are matched and which commands are executed.
2. Check `~/.cache/prek/prek.log` for errors that did not appear in stdout.
3. Run `prek cache gc` to remove stale environments, then re-run.
4. Run with `--refresh` if workspace discovery appears stale.
5. Use `prek util identify <file>` to verify that a file is matched by the expected type filters.

---

## 7. FAQ<a name="7-faq"></a>

**How is "prek" pronounced?** Like "wreck" with a "p" — rhymes with "trek".

**Changes to `.prekignore` are not being picked up — why?** prek caches workspace discovery results for performance.
After modifying `.prekignore`, force a refresh:

```sh
prek run --refresh
```

**What does `prek install --prepare-hooks` do differently from `prek install`?** `prek install` only installs git shims
in `.git/hooks/`. `prek install --prepare-hooks` does that _and_ immediately downloads and prepares all hook
environments, so the first commit does not incur setup latency. This flag exists for compatibility with the original
pre-commit's `--install-hooks` flag.

**How do I use prek with private repositories?** Three approaches, in order of recommendation:

1. **Credential helpers (recommended)**: Configure GitHub CLI (`gh auth login`), Git Credential Manager, or macOS
   Keychain. prek inherits credentials from git automatically.

2. **SSH URLs**: Replace HTTPS URLs in the config with SSH equivalents. Requires SSH keys configured with an agent.

3. **Token-based URL rewriting (CI)**: Use git's `url.<base>.insteadOf` config or environment variables to rewrite HTTPS
   URLs to include access tokens at clone time.

**Can I run a specific hook without running all hooks?** Yes: `prek run <hook-id>`. Use the full selector syntax for
workspace precision:

```sh
prek run ruff                  # All ruff hooks across all projects
prek run frontend:ruff         # Only ruff in the frontend project
```

**How do I skip a hook for one commit?** Use the `PREK_SKIP` environment variable:

```sh
PREK_SKIP=ruff git commit -m "..."
PREK_SKIP=ruff,mypy git commit -m "..."
PREK_SKIP=frontend/ git commit -m "..."   # Skip entire project
```

**How do I see what hooks are configured?**

```sh
prek list
prek list --output-format json
```

---

## 8. Compatibility with pre-commit<a name="8-compatibility-with-pre-commit"></a>

### Full Compatibility<a name="full-compatibility"></a>

Existing `.pre-commit-config.yaml` and `.pre-commit-config.yml` files work without modification. Most `pre-commit`
commands have identical behavior in `prek`.

### Legacy Command Aliases<a name="legacy-command-aliases"></a>

The following deprecated forms are still accepted for backward compatibility:

| Legacy command                      | Preferred equivalent           |
| ----------------------------------- | ------------------------------ |
| `prek install-hooks`                | `prek prepare-hooks`           |
| `prek install --install-hooks`      | `prek install --prepare-hooks` |
| `prek autoupdate`                   | `prek auto-update`             |
| `prek gc`                           | `prek cache gc`                |
| `prek clean`                        | `prek cache clean`             |
| `prek init-templatedir`             | `prek util init-template-dir`  |
| `prek init-template-dir` (old path) | `prek util init-template-dir`  |

### Not Implemented<a name="not-implemented"></a>

Two pre-commit features are absent from prek:

- `pre-commit hazmat` — the escape-hatch command for low-level manipulation
- `pre-commit migrate-config` — YAML migration tool (use `prek util yaml-to-toml` instead for TOML conversion)

### Portability Recommendations<a name="portability-recommendations"></a>

To keep configurations usable with the original `pre-commit`, avoid these prek-only features:

| Feature                     | Why it breaks portability                              |
| --------------------------- | ------------------------------------------------------ |
| `prek.toml`                 | Only prek reads TOML configs; pre-commit requires YAML |
| `repo: builtin`             | pre-commit has no built-in Rust hooks                  |
| Glob mappings (`{ glob: }`) | pre-commit only accepts regex strings                  |
| Workspace mode              | pre-commit has no workspace/monorepo support           |
| `orphan: true`              | pre-commit does not recognize this key                 |
| `env:` per-hook             | pre-commit does not recognize this key                 |
| `priority:` per-hook        | pre-commit does not recognize this key                 |

---

## 9. Installation<a name="9-installation"></a>

### Standalone Installers<a name="standalone-installers"></a>

**macOS / Linux:**

```sh
curl --proto '=https' --tlsv1.2 -LsSf \
  https://github.com/j178/prek/releases/download/v0.3.8/prek-installer.sh | sh
```

**Windows (PowerShell):**

```powershell
powershell -ExecutionPolicy ByPass -c `
  "irm https://github.com/j178/prek/releases/download/v0.3.8/prek-installer.ps1 | iex"
```

### Package Managers<a name="package-managers"></a>

| Method             | Command                           |
| ------------------ | --------------------------------- |
| uv (recommended)   | `uv tool install prek`            |
| uvx (one-shot)     | `uvx prek`                        |
| pip                | `pip install prek`                |
| pipx               | `pipx install prek`               |
| Homebrew           | `brew install prek`               |
| mise (v2025.8.11+) | `mise use prek`                   |
| npm                | `npm install -g @j178/prek`       |
| pnpm               | `pnpm add -g @j178/prek`          |
| bun                | `bun install -g @j178/prek`       |
| Nix shell          | `nix-shell -p prek`               |
| Conda              | `conda install conda-forge::prek` |
| Scoop              | `scoop install main/prek`         |
| Winget             | `winget install --id j178.Prek`   |
| MacPorts           | `sudo port install prek`          |
| cargo-binstall     | `cargo binstall prek`             |

### Docker<a name="docker-1"></a>

```sh
docker pull ghcr.io/j178/prek
docker run --rm -v $(pwd):/repo ghcr.io/j178/prek run --all-files
```

### From Source<a name="from-source"></a>

Requires Rust 1.89 or later.

```sh
cargo install --locked prek
```

### Self-Update<a name="self-update"></a>

```sh
prek self update
```

### Shell Completions<a name="shell-completions"></a>

Enable tab completion by adding one of the following to your shell's startup file.

**Bash** (`~/.bashrc`):

```sh
eval "$(COMPLETE=bash prek)"
```

**Zsh** (`~/.zshrc`):

```sh
eval "$(COMPLETE=zsh prek)"
```

**Fish** (`~/.config/fish/config.fish`):

```fish
COMPLETE=fish prek | source
```

**PowerShell** (`$PROFILE`):

```powershell
$env:COMPLETE = "powershell"; prek | Out-String | Invoke-Expression; Remove-Item Env:\COMPLETE
```
