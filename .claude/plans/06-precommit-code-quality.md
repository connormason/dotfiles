# Plan: Pre-commit and Code Quality Improvements

## Problem Statement

The pre-commit configuration is good but has gaps:

1. **No secrets detection** - Private keys checked, but not API keys, passwords
2. **Ansible-lint commented out** - Should be enabled
3. **Shellcheck commented out** - Shell scripts not validated
4. **No commit message linting** - No conventional commit enforcement
5. **Missing dependency updates** - Some hooks may be outdated

## Current State Analysis

### .pre-commit-config.yaml Audit

**Good (Enabled)**:
- Large file detection
- Merge conflict markers
- Private key detection
- Case conflict checking
- Symlink validation
- Python AST validation
- Debug statement detection
- JSON/YAML/TOML/XML validation
- Whitespace fixes
- yamllint (with custom config)
- ruff (Python linting)
- mypy (Python type checking)

**Missing/Disabled**:
- ansible-lint (lines 111-116, commented)
- shellcheck (lines 118-122, commented)
- Secrets scanning (detect-secrets, gitleaks, trufflehog)
- Commit message linting (commitizen, conventional)
- Documentation spelling (codespell)

---

## Implementation Tasks

### Phase 1: Enable Ansible Linting

- [ ] **Task 1.1**: Uncomment and configure ansible-lint
  ```yaml
  - repo: https://github.com/ansible/ansible-lint.git
    rev: v25.6.1
    hooks:
      - id: ansible-lint
        name: "[lint]  ansible"
        args: [--fix]
        files: \.(yml|yaml)$
        exclude: |
          (?x)(
              ^.pre-commit-config.yaml|
              ^.config/
          )
  ```

- [ ] **Task 1.2**: Update `.config/.ansible-lint.yaml` if needed
  ```yaml
  # Ensure rules are appropriate for dotfiles
  skip_list:
    - yaml[line-length]  # Long command lines are OK
    - name[missing]      # Not all tasks need names
  ```

### Phase 2: Enable Shell Script Linting

- [ ] **Task 2.1**: Uncomment and configure shellcheck
  ```yaml
  - repo: https://github.com/koalaman/shellcheck-precommit
    rev: v0.11.0
    hooks:
      - id: shellcheck
        name: "[lint]  shell"
        args: ["--severity=warning"]
  ```

- [ ] **Task 2.2**: Fix existing shellcheck warnings in:
  - `local_bootstrap.sh`
  - `nas_bootstrap.sh`
  - Any scripts in `scripts/`

### Phase 3: Add Secrets Detection

- [ ] **Task 3.1**: Add detect-secrets hook
  ```yaml
  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.5.0
    hooks:
      - id: detect-secrets
        name: "[security] detect secrets"
        args: ["--baseline", ".secrets.baseline"]
        exclude: |
          (?x)(
              ^inventory/.*vault\.yml$|
              ^\.secrets\.baseline$
          )
  ```

- [ ] **Task 3.2**: Generate initial secrets baseline
  ```bash
  detect-secrets scan > .secrets.baseline
  ```

- [ ] **Task 3.3**: Review and audit baseline for false positives

### Phase 4: Add Commit Message Linting (Optional)

- [ ] **Task 4.1**: Add commitizen for conventional commits
  ```yaml
  - repo: https://github.com/commitizen-tools/commitizen
    rev: v4.6.0
    hooks:
      - id: commitizen
        name: "[check] commit message"
        stages: [commit-msg]
  ```

- [ ] **Task 4.2**: Configure commitizen in pyproject.toml
  ```toml
  [tool.commitizen]
  name = "cz_conventional_commits"
  version = "0.1.0"
  tag_format = "v$version"
  ```

### Phase 5: Add Spelling Check (Optional)

- [ ] **Task 5.1**: Add codespell hook
  ```yaml
  - repo: https://github.com/codespell-project/codespell
    rev: v2.4.1
    hooks:
      - id: codespell
        name: "[check] spelling"
        args: [--skip, "*.json,*.lock"]
        exclude: |
          (?x)(
              ^archived_linux/
          )
  ```

### Phase 6: Update Hook Versions

- [ ] **Task 6.1**: Update all hooks to latest versions
  ```bash
  pre-commit autoupdate
  ```

- [ ] **Task 6.2**: Test all hooks pass after update
  ```bash
  pre-commit run --all-files
  ```

---

## Proposed Final Configuration

```yaml
---
repos:
  # Security checks
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v6.0.0
    hooks:
      - id: check-added-large-files
      - id: check-merge-conflict
      - id: detect-private-key

  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.5.0
    hooks:
      - id: detect-secrets
        args: ["--baseline", ".secrets.baseline"]

  # File integrity
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v6.0.0
    hooks:
      - id: check-case-conflict
      - id: check-symlinks
      - id: destroyed-symlinks
      - id: check-executables-have-shebangs

  # Data format validation
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v6.0.0
    hooks:
      - id: check-json
      - id: check-toml
      - id: check-xml
      - id: check-yaml

  # Python
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v6.0.0
    hooks:
      - id: check-ast
      - id: debug-statements

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.14.10
    hooks:
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.19.1
    hooks:
      - id: mypy
        args: [--ignore-missing-imports]

  # YAML/Ansible
  - repo: https://github.com/adrienverge/yamllint.git
    rev: v1.37.1
    hooks:
      - id: yamllint
        args: [-c, .config/.yamllint.yaml]

  - repo: https://github.com/ansible/ansible-lint.git
    rev: v25.6.1
    hooks:
      - id: ansible-lint
        args: [--fix]

  # Shell
  - repo: https://github.com/koalaman/shellcheck-precommit
    rev: v0.11.0
    hooks:
      - id: shellcheck
        args: ["--severity=warning"]

  # Fixers
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v6.0.0
    hooks:
      - id: fix-byte-order-marker
      - id: end-of-file-fixer
      - id: mixed-line-ending
      - id: trailing-whitespace
```

---

## Validation Checklist

- [ ] `pre-commit run --all-files` passes
- [ ] detect-secrets baseline generated
- [ ] ansible-lint runs without blocking errors
- [ ] shellcheck passes on all .sh files
- [ ] All hook versions are current

## Files to Modify

| File | Action |
|------|--------|
| `.pre-commit-config.yaml` | Enable hooks, add secrets detection |
| `.secrets.baseline` | Create (new file) |
| `.config/.ansible-lint.yaml` | Update rules if needed |
| `local_bootstrap.sh` | Fix shellcheck warnings |
| `nas_bootstrap.sh` | Fix shellcheck warnings |

## Risk Assessment

- **Low Risk**: Pre-commit hooks are development-time only
- **Impact**: May surface existing issues in codebase
- **Mitigation**: Fix issues incrementally, use baseline for secrets
- **Testing**: Run hooks on all files before committing config
