# Plan: Unified Bootstrap Script

## Problem Statement

`local_bootstrap.sh` and `nas_bootstrap.sh` are **95% identical** (82 vs 86 lines), differing only in:

1. **Validation check** (line 20-21): References own filename
2. **Playbook path** (line 79): `local_bootstrap.yml` vs `nas_bootstrap.yml`
3. **Post-bootstrap action** (lines 84-85): macOS runs `softwareupdate`, NAS does not

This duplication creates maintenance burden and inconsistency risk.

## Current State Analysis

### Identical Sections (95%)
- Color definitions (lines 3-7)
- Error handling setup (line 10)
- Script directory detection (lines 12-16)
- Directory validation (lines 18-26)
- Homebrew installation with checksum verification (lines 30-69)
- Ansible installation (lines 71-76)

### Different Sections (5%)
| Line | local_bootstrap.sh | nas_bootstrap.sh |
|------|-------------------|------------------|
| 20 | `local_bootstrap.sh` | `nas_bootstrap.sh` |
| 79 | `playbooks/local_bootstrap.yml` | `playbooks/nas_bootstrap.yml` |
| 84-85 | `softwareupdate --all --install --force` | (absent) |

## Proposed Solution

Create a **single `bootstrap.sh`** that:
1. Accepts playbook name as argument
2. Auto-detects OS for platform-specific post-actions
3. Validates arguments and provides clear usage

---

## Implementation Tasks

### Phase 1: Create Unified Bootstrap Script

- [ ] **Task 1.1**: Create new `bootstrap.sh` with argument parsing
  ```bash
  #\!/usr/bin/env bash
  set -e

  # Usage: ./bootstrap.sh <playbook>
  # Examples:
  #   ./bootstrap.sh local     # Runs playbooks/local_bootstrap.yml
  #   ./bootstrap.sh nas       # Runs playbooks/nas_bootstrap.yml

  PLAYBOOK="${1:-}"
  if [[ -z "$PLAYBOOK" ]]; then
      echo "Usage: $0 <playbook>"
      echo "Available playbooks:"
      ls -1 playbooks/*.yml | sed 's|playbooks/||;s|_bootstrap.yml||'
      exit 1
  fi
  ```

- [ ] **Task 1.2**: Add OS detection for platform-specific actions
  ```bash
  OS_TYPE="$(uname -s)"

  run_post_bootstrap() {
      if [[ "$OS_TYPE" == "Darwin" && "$PLAYBOOK" == "local" ]]; then
          echo -e "${GREEN}Kicking off software update...${NC}"
          softwareupdate --all --install --force
      fi
  }
  ```

- [ ] **Task 1.3**: Parameterize playbook path
  ```bash
  PLAYBOOK_PATH="playbooks/${PLAYBOOK}_bootstrap.yml"
  if [[ \! -f "$PLAYBOOK_PATH" ]]; then
      echo "Error: Playbook not found: $PLAYBOOK_PATH"
      exit 1
  fi
  ```

### Phase 2: Improve Bootstrap Robustness

- [ ] **Task 2.1**: Add vault password validation
  ```bash
  if [[ \! -f "${DOTFILES_DIR}/vault_password.txt" ]]; then
      echo -e "${RED}ERROR: vault_password.txt not found${NC}"
      echo "Create this file with your Ansible vault password"
      exit 1
  fi
  chmod 600 "${DOTFILES_DIR}/vault_password.txt"
  ```

- [ ] **Task 2.2**: Add inventory validation
  ```bash
  if [[ \! -f "inventory/inventory.yml" ]]; then
      echo "Inventory not found. Running update-inventory..."
      python3 run.py update-inventory
  fi
  ```

- [ ] **Task 2.3**: Add dry-run support
  ```bash
  DRY_RUN="${2:-}"
  if [[ "$DRY_RUN" == "--dry-run" ]]; then
      ANSIBLE_OPTS="--check"
  fi
  ```

### Phase 3: Migration

- [ ] **Task 3.1**: Create backward-compatible wrapper scripts
  ```bash
  # local_bootstrap.sh (new - just calls unified script)
  #\!/usr/bin/env bash
  exec "$(dirname "$0")/bootstrap.sh" local "$@"
  ```

- [ ] **Task 3.2**: Update documentation
- [ ] **Task 3.3**: Deprecate old scripts after testing period

### Phase 4: run.py Integration (from work dotfiles)

Port the bootstrap command from work dotfiles to personal:

- [ ] **Task 4.1**: Add `bootstrap` command to run.py
  ```python
  @command(group='Bootstrap')
  def cmd_bootstrap(args: argparse.Namespace) -> None:
      """Bootstrap a target host"""
      # Implementation from work dotfiles
  ```

- [ ] **Task 4.2**: Add bootstrap options (--only, --skip, --dry-run)
- [ ] **Task 4.3**: Add preflight checks command
- [ ] **Task 4.4**: Add validate command

---

## New Unified Script Structure

```bash
#\!/usr/bin/env bash
set -e

# ============================================================================
# Configuration
# ============================================================================
NC="\033[0m"
YELLOW="\033[0;33m"
GREEN="\033[0;32m"
RED="\033[0;31m"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOTFILES_DIR="${SCRIPT_DIR}"
OS_TYPE="$(uname -s)"

# ============================================================================
# Argument Parsing
# ============================================================================
usage() {
    echo "Usage: $0 <playbook> [options]"
    echo ""
    echo "Playbooks:"
    echo "  local    Bootstrap local macOS machine"
    echo "  nas      Bootstrap NAS server"
    echo ""
    echo "Options:"
    echo "  --dry-run    Show what would be done without making changes"
    exit 1
}

PLAYBOOK="${1:-}"
[[ -z "$PLAYBOOK" ]] && usage

# ============================================================================
# Validation
# ============================================================================
validate_environment() {
    # Check dotfiles directory
    # Check vault password
    # Check inventory
}

# ============================================================================
# Installation Functions
# ============================================================================
install_homebrew() { ... }
install_ansible() { ... }

# ============================================================================
# Post-Bootstrap Actions
# ============================================================================
run_post_bootstrap() {
    case "$OS_TYPE-$PLAYBOOK" in
        Darwin-local) softwareupdate --all --install --force ;;
    esac
}

# ============================================================================
# Main
# ============================================================================
main() {
    validate_environment
    install_homebrew
    install_ansible
    ansible-playbook "playbooks/${PLAYBOOK}_bootstrap.yml" ...
    run_post_bootstrap
}

main "$@"
```

---

## Validation Checklist

- [ ] `./bootstrap.sh local` works on macOS
- [ ] `./bootstrap.sh nas` works on Linux
- [ ] `./bootstrap.sh` (no args) shows usage
- [ ] `./bootstrap.sh invalid` shows error
- [ ] `./bootstrap.sh local --dry-run` works
- [ ] Old scripts still work (backward compat)

## Files to Modify/Create

| File | Action |
|------|--------|
| `bootstrap.sh` | Create (new unified script) |
| `local_bootstrap.sh` | Replace with wrapper (optional) |
| `nas_bootstrap.sh` | Replace with wrapper (optional) |
| `run.py` | Add bootstrap command (Phase 4) |
| `README.md` | Update bootstrap documentation |

## Risk Assessment

- **Medium Risk**: Changes to bootstrap process
- **Mitigation**: Keep old scripts as wrappers
- **Testing**: Test on both macOS and Linux before removing old scripts
