# Pre-Commit Hook Catalog

A tool-agnostic reference catalog of common pre-commit hooks organized by language and purpose. Each entry includes the
repo URL, a recommended revision, configuration in both YAML and TOML formats, and usage notes.

> **Note for prek users:** Many hooks in the Universal section are available as built-in hooks via `repo: builtin`,
> which are faster and require no network access. See the prek quick reference.

---

## 1. Universal Hooks

**Repo:** `https://github.com/pre-commit/pre-commit-hooks` **Rev:** `v5.0.0`

These hooks apply to virtually every project regardless of language.

### Full repo stanza (YAML)

```yaml
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-added-large-files
      - id: check-merge-conflict
      - id: detect-private-key
      - id: no-commit-to-branch
        args: [--branch, main, --branch, master]
      - id: mixed-line-ending
      - id: check-case-conflict
      - id: check-symlinks
```

### Full repo stanza (TOML)

```toml
[[repos]]
repo = "https://github.com/pre-commit/pre-commit-hooks"
rev = "v5.0.0"

[[repos.hooks]]
id = "trailing-whitespace"

[[repos.hooks]]
id = "end-of-file-fixer"

[[repos.hooks]]
id = "check-added-large-files"

[[repos.hooks]]
id = "check-merge-conflict"

[[repos.hooks]]
id = "detect-private-key"

[[repos.hooks]]
id = "no-commit-to-branch"
args = ["--branch", "main", "--branch", "master"]

[[repos.hooks]]
id = "mixed-line-ending"

[[repos.hooks]]
id = "check-case-conflict"

[[repos.hooks]]
id = "check-symlinks"
```

---

#### trailing-whitespace

- **Repo:** `https://github.com/pre-commit/pre-commit-hooks`
- **Rev:** `v5.0.0`
- **Config (YAML):**
  ```yaml
    - id: trailing-whitespace
  ```
- **Config (TOML):**
  ```toml
  { id = "trailing-whitespace" }
  ```
- **Notes:** Trims trailing whitespace from all files. Pass `--markdown-linebreak-ext=md` to preserve Markdown two-space
  line breaks.

---

#### end-of-file-fixer

- **Repo:** `https://github.com/pre-commit/pre-commit-hooks`
- **Rev:** `v5.0.0`
- **Config (YAML):**
  ```yaml
    - id: end-of-file-fixer
  ```
- **Config (TOML):**
  ```toml
  { id = "end-of-file-fixer" }
  ```
- **Notes:** Ensures files end with a single newline. Fixes silently on commit.

---

#### check-added-large-files

- **Repo:** `https://github.com/pre-commit/pre-commit-hooks`
- **Rev:** `v5.0.0`
- **Config (YAML):**
  ```yaml
    - id: check-added-large-files
      args: [--maxkb=500]
  ```
- **Config (TOML):**
  ```toml
  { id = "check-added-large-files", args = ["--maxkb=500"] }
  ```
- **Notes:** Default limit is 500 KB. Adjust `--maxkb` to suit your project. Does not affect files already tracked by
  git.

---

#### check-merge-conflict

- **Repo:** `https://github.com/pre-commit/pre-commit-hooks`
- **Rev:** `v5.0.0`
- **Config (YAML):**
  ```yaml
    - id: check-merge-conflict
  ```
- **Config (TOML):**
  ```toml
  { id = "check-merge-conflict" }
  ```
- **Notes:** Blocks commits that contain unresolved merge conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`).

---

#### detect-private-key

- **Repo:** `https://github.com/pre-commit/pre-commit-hooks`
- **Rev:** `v5.0.0`
- **Config (YAML):**
  ```yaml
    - id: detect-private-key
  ```
- **Config (TOML):**
  ```toml
  { id = "detect-private-key" }
  ```
- **Notes:** Scans for common private key headers (RSA, DSA, EC, OpenSSH). For broader secret detection, pair with
  gitleaks or trufflehog (see Security section).

---

#### no-commit-to-branch

- **Repo:** `https://github.com/pre-commit/pre-commit-hooks`
- **Rev:** `v5.0.0`
- **Config (YAML):**
  ```yaml
    - id: no-commit-to-branch
      args: [--branch, main, --branch, master]
  ```
- **Config (TOML):**
  ```toml
  { id = "no-commit-to-branch", args = ["--branch", "main", "--branch", "master"] }
  ```
- **Notes:** Prevents direct commits to protected branches. Add any additional branches you want to protect via
  `--branch` args. Supports glob patterns with `--pattern`.

---

#### mixed-line-ending

- **Repo:** `https://github.com/pre-commit/pre-commit-hooks`
- **Rev:** `v5.0.0`
- **Config (YAML):**
  ```yaml
    - id: mixed-line-ending
      args: [--fix=lf]
  ```
- **Config (TOML):**
  ```toml
  { id = "mixed-line-ending", args = ["--fix=lf"] }
  ```
- **Notes:** Detects and optionally fixes mixed line endings. Use `--fix=lf` for Unix, `--fix=crlf` for Windows. Default
  (`--fix=auto`) uses the most common ending in the file.

---

#### check-case-conflict

- **Repo:** `https://github.com/pre-commit/pre-commit-hooks`
- **Rev:** `v5.0.0`
- **Config (YAML):**
  ```yaml
    - id: check-case-conflict
  ```
- **Config (TOML):**
  ```toml
  { id = "check-case-conflict" }
  ```
- **Notes:** Prevents adding files whose names differ only in case, which causes issues on case-insensitive filesystems
  (macOS HFS+, Windows NTFS).

---

#### check-symlinks

- **Repo:** `https://github.com/pre-commit/pre-commit-hooks`
- **Rev:** `v5.0.0`
- **Config (YAML):**
  ```yaml
    - id: check-symlinks
  ```
- **Config (TOML):**
  ```toml
  { id = "check-symlinks" }
  ```
- **Notes:** Checks for symlinks that do not point to anything. Catches accidentally broken links before they are
  committed.

---

## 2. Python

### ruff (lint)

#### ruff-check

- **Repo:** `https://github.com/astral-sh/ruff-pre-commit`
- **Rev:** `v0.9.10`
- **Config (YAML):**
  ```yaml
    - repo: https://github.com/astral-sh/ruff-pre-commit
      rev: v0.9.10
      hooks:
        - id: ruff
          args: [--fix]
  ```
- **Config (TOML):**
  ```toml
  [[repos]]
  repo = "https://github.com/astral-sh/ruff-pre-commit"
  rev = "v0.9.10"

  [[repos.hooks]]
  id = "ruff"
  args = ["--fix"]
  ```
- **Notes:** Ruff replaces flake8, isort, pyupgrade, autoflake, and many other Python linters in a single fast tool. The
  `--fix` flag auto-applies safe fixes. Strongly preferred over running those individual tools separately. Configure
  rules in `pyproject.toml` under `[tool.ruff.lint]`.

---

#### ruff-format

- **Repo:** `https://github.com/astral-sh/ruff-pre-commit`
- **Rev:** `v0.9.10`
- **Config (YAML):**
  ```yaml
    - repo: https://github.com/astral-sh/ruff-pre-commit
      rev: v0.9.10
      hooks:
        - id: ruff-format
  ```
- **Config (TOML):**
  ```toml
  [[repos]]
  repo = "https://github.com/astral-sh/ruff-pre-commit"
  rev = "v0.9.10"

  [[repos.hooks]]
  id = "ruff-format"
  ```
- **Notes:** Ruff's formatter is Black-compatible and significantly faster. Replaces black in most cases. Run
  ruff-format before ruff (lint) in your hook list so the linter sees formatted code. Configure under
  `[tool.ruff.format]` in `pyproject.toml`.

---

#### mypy

- **Repo:** `https://github.com/pre-commit/mirrors-mypy`
- **Rev:** `v1.15.0`
- **Config (YAML):**
  ```yaml
    - repo: https://github.com/pre-commit/mirrors-mypy
      rev: v1.15.0
      hooks:
        - id: mypy
          additional_dependencies: [types-requests, types-PyYAML]
  ```
- **Config (TOML):**
  ```toml
  [[repos]]
  repo = "https://github.com/pre-commit/mirrors-mypy"
  rev = "v1.15.0"

  [[repos.hooks]]
  id = "mypy"
  additional_dependencies = ["types-requests", "types-PyYAML"]
  ```
- **Notes:** Static type checker for Python. Add any `types-*` stubs your project needs in `additional_dependencies`.
  Mypy runs in an isolated environment, so project dependencies are not available unless listed here. Configure in
  `pyproject.toml` under `[tool.mypy]`. Consider a local hook if your project has complex dependency requirements.

---

#### bandit

- **Repo:** `https://github.com/PyCQA/bandit`
- **Rev:** `1.8.3`
- **Config (YAML):**
  ```yaml
    - repo: https://github.com/PyCQA/bandit
      rev: 1.8.3
      hooks:
        - id: bandit
          args: [-c, pyproject.toml]
  ```
- **Config (TOML):**
  ```toml
  [[repos]]
  repo = "https://github.com/PyCQA/bandit"
  rev = "1.8.3"

  [[repos.hooks]]
  id = "bandit"
  args = ["-c", "pyproject.toml"]
  ```
- **Notes:** Security linter for Python. Flags common security issues (hardcoded passwords, use of `eval`, insecure
  random, etc.). Configure exclusions in `pyproject.toml` under `[tool.bandit]`. Use `-ll` to report only medium and
  high severity issues in busy codebases.

---

## 3. JavaScript / TypeScript

#### eslint

- **Repo:** `https://github.com/pre-commit/mirrors-eslint`
- **Rev:** `v9.22.0`
- **Config (YAML):**
  ```yaml
    - repo: https://github.com/pre-commit/mirrors-eslint
      rev: v9.22.0
      hooks:
        - id: eslint
          files: \.(js|jsx|ts|tsx)$
          types: [file]
          additional_dependencies:
            - eslint@9.22.0
            - '@typescript-eslint/parser@8.26.0'
            - '@typescript-eslint/eslint-plugin@8.26.0'
  ```
- **Config (TOML):**
  ```toml
  [[repos]]
  repo = "https://github.com/pre-commit/mirrors-eslint"
  rev = "v9.22.0"

  [[repos.hooks]]
  id = "eslint"
  files = "\\.(js|jsx|ts|tsx)$"
  types = ["file"]
  additional_dependencies = [
    "eslint@9.22.0",
    "@typescript-eslint/parser@8.26.0",
    "@typescript-eslint/eslint-plugin@8.26.0",
  ]
  ```
- **Notes:** The mirrors-eslint hook requires you to list all ESLint plugins in `additional_dependencies` since the hook
  runs in isolation. Pin all versions to keep builds reproducible. Alternatively, use a local hook pointing to
  `./node_modules/.bin/eslint` to reuse your existing `node_modules`.

---

#### prettier

- **Repo:** `https://github.com/pre-commit/mirrors-prettier`
- **Rev:** `v4.0.0-alpha.8`
- **Config (YAML):**
  ```yaml
    - repo: https://github.com/pre-commit/mirrors-prettier
      rev: v4.0.0-alpha.8
      hooks:
        - id: prettier
          types_or: [javascript, jsx, ts, tsx, css, json, yaml, markdown]
  ```
- **Config (TOML):**
  ```toml
  [[repos]]
  repo = "https://github.com/pre-commit/mirrors-prettier"
  rev = "v4.0.0-alpha.8"

  [[repos.hooks]]
  id = "prettier"
  types_or = ["javascript", "jsx", "ts", "tsx", "css", "json", "yaml", "markdown"]
  ```
- **Notes:** Opinionated formatter covering JS/TS, CSS, JSON, YAML, and Markdown. Configure in `.prettierrc` or
  `package.json`. The mirrors-prettier repo may lag behind Prettier releases; run `pre-commit autoupdate` to get the
  latest rev. For YAML-only formatting, Prettier is a good alternative to check-yaml.

---

#### tsc (local hook)

- **Repo:** `local`
- **Rev:** N/A (local)
- **Config (YAML):**
  ```yaml
    - repo: local
      hooks:
        - id: tsc
          name: TypeScript type check
          entry: npx tsc --noEmit
          language: node
          pass_filenames: false
          types: [ts]
  ```
- **Config (TOML):**
  ```toml
  [[repos]]
  repo = "local"

  [[repos.hooks]]
  id = "tsc"
  name = "TypeScript type check"
  entry = "npx tsc --noEmit"
  language = "node"
  pass_filenames = false
  types = ["ts"]
  ```
- **Notes:** Runs the TypeScript compiler in type-check mode without emitting files. Use `pass_filenames = false` since
  tsc reads `tsconfig.json` itself. Requires Node.js in PATH. Slower than ESLint but catches type errors that linting
  misses.

---

## 4. Go

#### golangci-lint

- **Repo:** `https://github.com/golangci/golangci-lint`
- **Rev:** `v2.1.2`
- **Config (YAML):**
  ```yaml
    - repo: https://github.com/golangci/golangci-lint
      rev: v2.1.2
      hooks:
        - id: golangci-lint
  ```
- **Config (TOML):**
  ```toml
  [[repos]]
  repo = "https://github.com/golangci/golangci-lint"
  rev = "v2.1.2"

  [[repos.hooks]]
  id = "golangci-lint"
  ```
- **Notes:** Meta-linter that runs many Go linters in parallel. Replaces running golint, staticcheck, errcheck, and
  others individually. Configure enabled linters in `.golangci.yml` or `.golangci.toml`. Pinning the rev is important —
  golangci-lint has frequent breaking changes between major versions. Run `pre-commit autoupdate` periodically.

---

#### gofmt (local hook)

- **Repo:** `local`
- **Rev:** N/A (local)
- **Config (YAML):**
  ```yaml
    - repo: local
      hooks:
        - id: gofmt
          name: gofmt
          entry: gofmt -l -w
          language: golang
          types: [go]
  ```
- **Config (TOML):**
  ```toml
  [[repos]]
  repo = "local"

  [[repos.hooks]]
  id = "gofmt"
  name = "gofmt"
  entry = "gofmt -l -w"
  language = "golang"
  types = ["go"]
  ```
- **Notes:** Standard Go formatter. The `-w` flag writes changes in place; `-l` lists changed files. Consider
  `goimports` instead if you want import management as well. Requires Go in PATH.

---

#### go vet (local hook)

- **Repo:** `local`
- **Rev:** N/A (local)
- **Config (YAML):**
  ```yaml
    - repo: local
      hooks:
        - id: go-vet
          name: go vet
          entry: go vet ./...
          language: golang
          pass_filenames: false
          types: [go]
  ```
- **Config (TOML):**
  ```toml
  [[repos]]
  repo = "local"

  [[repos.hooks]]
  id = "go-vet"
  name = "go vet"
  entry = "go vet ./..."
  language = "golang"
  pass_filenames = false
  types = ["go"]
  ```
- **Notes:** Built-in Go static analyzer. Catches suspicious constructs the compiler accepts (e.g., unreachable code,
  incorrect format strings). Fast and zero-configuration. Use `pass_filenames = false` since `./...` handles the file
  selection.

---

## 5. Rust

#### clippy (local hook)

- **Repo:** `local`
- **Rev:** N/A (local)
- **Config (YAML):**
  ```yaml
    - repo: local
      hooks:
        - id: clippy
          name: cargo clippy
          entry: cargo clippy --all-targets --all-features -- -D warnings
          language: rust
          pass_filenames: false
          types: [rust]
  ```
- **Config (TOML):**
  ```toml
  [[repos]]
  repo = "local"

  [[repos.hooks]]
  id = "clippy"
  name = "cargo clippy"
  entry = "cargo clippy --all-targets --all-features -- -D warnings"
  language = "rust"
  pass_filenames = false
  types = ["rust"]
  ```
- **Notes:** Rust's official linter with hundreds of checks. The `-D warnings` flag treats all warnings as errors —
  remove it if you want a softer enforcement. `--all-targets` includes tests and examples. Can be slow on large
  projects; consider adding `stages: [manual]` and running in CI instead.

---

#### rustfmt (local hook)

- **Repo:** `local`
- **Rev:** N/A (local)
- **Config (YAML):**
  ```yaml
    - repo: local
      hooks:
        - id: rustfmt
          name: cargo fmt
          entry: cargo fmt --all -- --check
          language: rust
          pass_filenames: false
          types: [rust]
  ```
- **Config (TOML):**
  ```toml
  [[repos]]
  repo = "local"

  [[repos.hooks]]
  id = "rustfmt"
  name = "cargo fmt"
  entry = "cargo fmt --all -- --check"
  language = "rust"
  pass_filenames = false
  types = ["rust"]
  ```
- **Notes:** Official Rust formatter. The `--check` flag fails without modifying files (good for CI). Remove `--check`
  to auto-fix on commit. Configure style in `rustfmt.toml` or `.rustfmt.toml`.

---

#### cargo check (local hook)

- **Repo:** `local`
- **Rev:** N/A (local)
- **Config (YAML):**
  ```yaml
    - repo: local
      hooks:
        - id: cargo-check
          name: cargo check
          entry: cargo check --all-targets
          language: rust
          pass_filenames: false
          types: [rust]
  ```
- **Config (TOML):**
  ```toml
  [[repos]]
  repo = "local"

  [[repos.hooks]]
  id = "cargo-check"
  name = "cargo check"
  entry = "cargo check --all-targets"
  language = "rust"
  pass_filenames = false
  types = ["rust"]
  ```
- **Notes:** Compiles without producing binaries — faster than `cargo build`. Catches type errors and borrow checker
  violations. Run this before clippy in your hook list to surface compile errors first.

---

## 6. YAML / JSON / TOML / XML

All four file-format hooks come from `pre-commit-hooks`:

**Repo:** `https://github.com/pre-commit/pre-commit-hooks` **Rev:** `v5.0.0`

#### check-yaml

- **Config (YAML):**
  ```yaml
    - id: check-yaml
      args: [--allow-multiple-documents]
  ```
- **Config (TOML):**
  ```toml
  { id = "check-yaml", args = ["--allow-multiple-documents"] }
  ```
- **Notes:** Validates YAML syntax. Pass `--allow-multiple-documents` for files using `---` separators (common in
  Kubernetes manifests). Use `--unsafe` for files with custom YAML tags.

---

#### check-json

- **Config (YAML):**
  ```yaml
    - id: check-json
  ```
- **Config (TOML):**
  ```toml
  { id = "check-json" }
  ```
- **Notes:** Validates JSON syntax. Does not check schema — pair with a schema validator if needed.

---

#### check-toml

- **Config (YAML):**
  ```yaml
    - id: check-toml
  ```
- **Config (TOML):**
  ```toml
  { id = "check-toml" }
  ```
- **Notes:** Validates TOML syntax. Useful for catching errors in `pyproject.toml`, `Cargo.toml`, and similar config
  files.

---

#### check-xml

- **Config (YAML):**
  ```yaml
    - id: check-xml
  ```
- **Config (TOML):**
  ```toml
  { id = "check-xml" }
  ```
- **Notes:** Validates XML syntax. Does not validate against a schema (DTD/XSD).

---

#### prettier (JSON/YAML/Markdown formatting)

- **Repo:** `https://github.com/pre-commit/mirrors-prettier`
- **Rev:** `v4.0.0-alpha.8`
- **Config (YAML):**
  ```yaml
    - repo: https://github.com/pre-commit/mirrors-prettier
      rev: v4.0.0-alpha.8
      hooks:
        - id: prettier
          types_or: [json, yaml, markdown]
  ```
- **Config (TOML):**
  ```toml
  [[repos]]
  repo = "https://github.com/pre-commit/mirrors-prettier"
  rev = "v4.0.0-alpha.8"

  [[repos.hooks]]
  id = "prettier"
  types_or = ["json", "yaml", "markdown"]
  ```
- **Notes:** Prettier formats JSON, YAML, and Markdown consistently. A good complement to `check-yaml`/`check-json`
  which only validate syntax. If you are already using Prettier for JS/TS, reuse the same stanza — just add additional
  types.

---

## 7. Docker

#### hadolint

- **Repo:** `https://github.com/hadolint/hadolint`
- **Rev:** `v2.13.1-beta`
- **Config (YAML):**
  ```yaml
    - repo: https://github.com/hadolint/hadolint
      rev: v2.13.1-beta
      hooks:
        - id: hadolint-docker
  ```
- **Config (TOML):**
  ```toml
  [[repos]]
  repo = "https://github.com/hadolint/hadolint"
  rev = "v2.13.1-beta"

  [[repos.hooks]]
  id = "hadolint-docker"
  ```
- **Notes:** Lints Dockerfiles against best practices (pinned base images, avoiding `latest`, `RUN` layer optimization,
  etc.). Two hook IDs are available: `hadolint-docker` (runs via Docker, requires Docker daemon) and `hadolint` (uses a
  pre-built binary). Prefer `hadolint` if you want to avoid the Docker dependency. Configure ignored rules in
  `.hadolint.yaml`.

---

## 8. Shell

#### shellcheck

- **Repo:** `https://github.com/shellcheck-py/shellcheck-py`
- **Rev:** `v0.10.0.1`
- **Config (YAML):**
  ```yaml
    - repo: https://github.com/shellcheck-py/shellcheck-py
      rev: v0.10.0.1
      hooks:
        - id: shellcheck
  ```
- **Config (TOML):**
  ```toml
  [[repos]]
  repo = "https://github.com/shellcheck-py/shellcheck-py"
  rev = "v0.10.0.1"

  [[repos.hooks]]
  id = "shellcheck"
  ```
- **Notes:** Static analysis for bash/sh scripts. Catches common bugs (unquoted variables, incorrect comparison
  operators, command substitution issues). The shellcheck-py wrapper installs the native `shellcheck` binary via pip for
  cross-platform convenience. Configure exclusions with `args: [--exclude=SC2034,SC2086]` or via `.shellcheckrc`.

---

#### shfmt

- **Repo:** `https://github.com/scop/pre-commit-shfmt`
- **Rev:** `v3.11.0-1`
- **Config (YAML):**
  ```yaml
    - repo: https://github.com/scop/pre-commit-shfmt
      rev: v3.11.0-1
      hooks:
        - id: shfmt
          args: [-i, '2', -ci]
  ```
- **Config (TOML):**
  ```toml
  [[repos]]
  repo = "https://github.com/scop/pre-commit-shfmt"
  rev = "v3.11.0-1"

  [[repos.hooks]]
  id = "shfmt"
  args = ["-i", "2", "-ci"]
  ```
- **Notes:** Formats shell scripts using the `shfmt` tool. `-i 2` sets 2-space indentation; `-ci` indents switch cases.
  Use `-w` to write in place (default is check mode in pre-commit context). Combine with shellcheck for full shell
  script hygiene.

---

## 9. Security

#### detect-private-key

See [Universal Hooks > detect-private-key](#detect-private-key) above.

---

#### gitleaks

- **Repo:** `https://github.com/gitleaks/gitleaks`
- **Rev:** `v8.24.2`
- **Config (YAML):**
  ```yaml
    - repo: https://github.com/gitleaks/gitleaks
      rev: v8.24.2
      hooks:
        - id: gitleaks
  ```
- **Config (TOML):**
  ```toml
  [[repos]]
  repo = "https://github.com/gitleaks/gitleaks"
  rev = "v8.24.2"

  [[repos.hooks]]
  id = "gitleaks"
  ```
- **Notes:** Detects hardcoded secrets (API keys, tokens, passwords) using regex rules. More comprehensive than
  `detect-private-key`. Configure custom rules and allowlists in `.gitleaks.toml`. The `gitleaks` hook scans staged
  files; a separate `gitleaks-ci` hook scans full commit history. False positives are common — use `# gitleaks:allow`
  inline comments to suppress known-safe values.

---

#### trufflehog

- **Repo:** `https://github.com/trufflesecurity/trufflehog`
- **Rev:** `v3.88.1`
- **Config (YAML):**
  ```yaml
    - repo: https://github.com/trufflesecurity/trufflehog
      rev: v3.88.1
      hooks:
        - id: trufflehog
          entry: trufflehog git file://. --since-commit HEAD --only-verified 
            --fail
          language: golang
          pass_filenames: false
  ```
- **Config (TOML):**
  ```toml
  [[repos]]
  repo = "https://github.com/trufflesecurity/trufflehog"
  rev = "v3.88.1"

  [[repos.hooks]]
  id = "trufflehog"
  entry = "trufflehog git file://. --since-commit HEAD --only-verified --fail"
  language = "golang"
  pass_filenames = false
  ```
- **Notes:** Scans for credentials and verifies them against external APIs (GitHub tokens, AWS keys, etc.) to reduce
  false positives. The `--only-verified` flag only reports secrets that actually authenticate successfully. Slower than
  gitleaks due to live verification — consider running at `push` stage rather than `commit`. Use either gitleaks or
  trufflehog, not both.

---

## 10. Commit Messages

These hooks run at the `commit-msg` stage, not the default `pre-commit` stage.

#### commitizen

- **Repo:** `https://github.com/commitizen-tools/commitizen`
- **Rev:** `v4.5.0`
- **Config (YAML):**
  ```yaml
    - repo: https://github.com/commitizen-tools/commitizen
      rev: v4.5.0
      hooks:
        - id: commitizen
          stages: [commit-msg]
  ```
- **Config (TOML):**
  ```toml
  [[repos]]
  repo = "https://github.com/commitizen-tools/commitizen"
  rev = "v4.5.0"

  [[repos.hooks]]
  id = "commitizen"
  stages = ["commit-msg"]
  ```
- **Notes:** Enforces conventional commit format (`feat:`, `fix:`, `chore:`, etc.) and can automate changelog generation
  and version bumping. Configure commit types and scopes in `pyproject.toml` under `[tool.commitizen]`. More opinionated
  and feature-rich than conventional-pre-commit — prefer this if you want automated releases.

---

#### conventional-pre-commit

- **Repo:** `https://github.com/compilerla/conventional-pre-commit`
- **Rev:** `v3.6.0`
- **Config (YAML):**
  ```yaml
    - repo: https://github.com/compilerla/conventional-pre-commit
      rev: v3.6.0
      hooks:
        - id: conventional-pre-commit
          stages: [commit-msg]
          args: [feat, fix, docs, style, refactor, perf, test, build, ci, chore, 
                revert]
  ```
- **Config (TOML):**
  ```toml
  [[repos]]
  repo = "https://github.com/compilerla/conventional-pre-commit"
  rev = "v3.6.0"

  [[repos.hooks]]
  id = "conventional-pre-commit"
  stages = ["commit-msg"]
  args = [
    "feat",
    "fix",
    "docs",
    "style",
    "refactor",
    "perf",
    "test",
    "build",
    "ci",
    "chore",
    "revert",
  ]
  ```
- **Notes:** Lightweight validator for conventional commit format. Unlike commitizen, it only validates — no changelog
  or versioning features. The `args` list defines the allowed commit types. Prefer this over commitizen if you only want
  enforcement without the extra tooling.

---

## Quick Reference: Keeping Revs Up to Date

Run the following command to update all hook revisions to their latest tags:

```bash
# For .pre-commit-config.yaml
pre-commit autoupdate

# For prek (pre-commit-config.toml)
prek auto-update
```

Pin revisions to a specific tag or commit SHA for reproducible builds. Avoid using `HEAD` or branch names as revisions —
they change without notice and break cached environments.
