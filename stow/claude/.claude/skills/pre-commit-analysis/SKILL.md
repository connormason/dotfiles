---
name: pre-commit-analysis
description: Analyze, audit, and improve pre-commit hook configurations. Also diagnose pre-commit hook failures. Use when users ask to review their hooks, improve their pre-commit setup, or when a pre-commit hook fails during development. Triggers on phrases like "pre-commit hook failed", "hook error", "commit blocked by hook", "analyze my hooks", "improve pre-commit config", "audit hooks", "hook is failing".
---

# Pre-Commit Hook Analysis

You are an expert at analyzing pre-commit hook configurations and diagnosing hook failures.

<!-- mdformat-toc start --slug=github --maxlevel=3 --minlevel=2 -->

- [When This Skill Activates](#when-this-skill-activates)
- [Analysis Workflow](#analysis-workflow)
  - [1. Detect Tool and Read Config](#1-detect-tool-and-read-config)
  - [2. Scan Project Tech Stack](#2-scan-project-tech-stack)
  - [3. Compare Against Hook Catalog](#3-compare-against-hook-catalog)
  - [4. Generate Recommendations](#4-generate-recommendations)
- [Hook Failure Diagnosis](#hook-failure-diagnosis)
  - [1. Identify the Failure](#1-identify-the-failure)
  - [2. Classify the Failure](#2-classify-the-failure)
  - [3. Recommend a Fix](#3-recommend-a-fix)
- [Key Principles](#key-principles)

<!-- mdformat-toc end -->

## When This Skill Activates<a name="when-this-skill-activates"></a>

**Analysis mode:**

- User asks to analyze, audit, review, or improve their pre-commit hooks
- User asks what hooks they should add
- User wants to know if their hooks are up to date

**Failure mode:**

- A pre-commit hook failed during a commit
- User reports a hook error or that their commit was blocked by a hook
- Hook environment or installation issues

## Analysis Workflow<a name="analysis-workflow"></a>

### 1. Detect Tool and Read Config<a name="1-detect-tool-and-read-config"></a>

Check for `.pre-commit-config.yaml`, `.pre-commit-config.yml`, or `prek.toml`. Read the config file to understand
current hook setup.

### 2. Scan Project Tech Stack<a name="2-scan-project-tech-stack"></a>

Use Glob to detect:

**Languages:**

- `**/*.py` → Python
- `**/*.js`, `**/*.ts`, `**/*.jsx`, `**/*.tsx` → JavaScript/TypeScript
- `**/*.go` → Go
- `**/*.rs` → Rust
- `**/*.rb` → Ruby
- `**/*.java` → Java
- `**/*.swift` → Swift
- `**/*.sh`, `**/*.bash` → Shell

**Build/Config Files:**

- `pyproject.toml`, `setup.py`, `setup.cfg` → Python project
- `package.json` → Node.js project
- `Cargo.toml` → Rust project
- `go.mod` → Go project
- `Makefile`, `CMakeLists.txt` → C/C++ project
- `Dockerfile`, `docker-compose.yml` → Docker usage

**Existing Linters/Formatters:**

- `ruff.toml`, `pyproject.toml` [tool.ruff] → Ruff configured
- `.eslintrc*`, `eslint.config.*` → ESLint configured
- `.prettierrc*` → Prettier configured
- `rustfmt.toml` → Rustfmt configured
- `.golangci.yml` → golangci-lint configured

### 3. Compare Against Hook Catalog<a name="3-compare-against-hook-catalog"></a>

Read `references/hook-catalog.md` and compare detected languages/tools against configured hooks. Identify:

- **Missing coverage**: Language detected but no corresponding linter/formatter hook
- **Universal gaps**: Missing trailing-whitespace, end-of-file-fixer, check-added-large-files
- **Security gaps**: No secret detection hook (detect-private-key, gitleaks)
- **Redundant hooks**: e.g., both flake8 and ruff (ruff replaces flake8)
- **Outdated revs**: Known outdated versions (suggest running `autoupdate`/`auto-update`)
- **Misconfigured patterns**: File patterns that don't match the project structure

### 4. Generate Recommendations<a name="4-generate-recommendations"></a>

Present findings as a prioritized list:

1. **Critical**: Missing security hooks, broken config
2. **Recommended**: Missing language-specific hooks, outdated revs
3. **Optional**: Nice-to-have improvements (type filters, ordering)

For each recommendation, provide the exact config snippet to add.

## Hook Failure Diagnosis<a name="hook-failure-diagnosis"></a>

### 1. Identify the Failure<a name="1-identify-the-failure"></a>

Parse the error output to determine:

- Which hook failed (hook ID and name)
- What the error message says
- Whether files were modified by the hook

### 2. Classify the Failure<a name="2-classify-the-failure"></a>

| Type                     | Meaning                                                      | Fix                                                                         |
| ------------------------ | ------------------------------------------------------------ | --------------------------------------------------------------------------- |
| Linting/formatting error | Hook found issues in your code                               | Fix the code, not the hook — the hook is working correctly                  |
| Auto-fix applied         | Hook modified files (e.g., trailing-whitespace, black)       | Stage the changes and commit again                                          |
| Configuration error      | Wrong language version, missing dependency, bad file pattern | Fix the hook config                                                         |
| Environment error        | Corrupted cache, missing toolchain, network error            | Run `pre-commit clean` / `prek cache clean` and reinstall                   |
| Timeout                  | Hook took too long                                           | Check if the hook is running on too many files; add `types`/`files` filters |

### 3. Recommend a Fix<a name="3-recommend-a-fix"></a>

- **Always fix the root cause.** Never recommend `--no-verify` or `SKIP=` as the primary solution.
- If the user explicitly asks how to skip a hook temporarily, explain `SKIP=hook-id git commit` (pre-commit) or
  `PREK_SKIP=hook-id git commit` (prek) — but frame it as a temporary escape hatch, not a fix.
- For environment issues, the fix is usually: clean cache → reinstall → retry.
- For config issues, read the appropriate quick reference to understand the correct syntax.

## Key Principles<a name="key-principles"></a>

- **Diagnose before recommending**: Understand the failure before suggesting changes
- **Fix code, not hooks**: If a linter hook fails, the code needs fixing
- **Never bypass as default**: `--no-verify` and `SKIP=` are escape hatches, not solutions
- **Be specific**: Provide exact config snippets, not vague guidance
