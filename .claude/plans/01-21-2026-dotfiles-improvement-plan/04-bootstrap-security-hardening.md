# Plan: Bootstrap Script Security Hardening

## Problem Statement

The bootstrap scripts (`local_bootstrap.sh`, `nas_bootstrap.sh`) have good security foundations (Homebrew checksum
verification) but lack some critical safety checks:

1. **No vault password validation** before running Ansible
2. **No inventory existence check** before running playbook
3. **Missing error message filename** references wrong file (line 56)
4. **No SSH key validation** for inventory repo access
5. **No idempotency check** (warns if already bootstrapped)

## Current State Analysis

### Good: Homebrew Checksum Verification
Lines 38-59 contain excellent security practice for verifying the Homebrew installer checksum before execution.

### Issue 1: Wrong Filename in Error Message
**Line 56** says:
```bash
echo -e "  2. Update EXPECTED_CHECKSUM in bootstrap.sh"
```
Should reference `local_bootstrap.sh` or `nas_bootstrap.sh`.

### Issue 2: No Vault Password Check
Ansible will fail cryptically if `vault_password.txt` is missing:
```
ERROR\! Attempting to decrypt but no vault secrets found
```

### Issue 3: No Inventory Check
If inventory is missing, Ansible fails with unhelpful error:
```
ERROR\! Unable to parse inventory/inventory.yml as an inventory source
```

### Issue 4: No Pre-flight Validation
No checks for:
- Disk space
- Required commands (curl, git)
- Network connectivity
- macOS version (for compatibility)

---

## Implementation Tasks

### Phase 1: Add Vault Password Validation

- [ ] **Task 1.1**: Add vault password check function
  - Check if vault_password.txt exists in DOTFILES_DIR
  - If missing, show clear error with instructions to create it
  - Ensure proper permissions (chmod 600)
  - Exit early with helpful message

### Phase 2: Add Inventory Validation

- [ ] **Task 2.1**: Add inventory check function
  - Check if inventory/inventory.yml exists
  - If missing, attempt to fetch via run.py update-inventory
  - If Python not available, provide manual clone instructions
  - Exit with clear error on failure

### Phase 3: Add Pre-flight Checks

- [ ] **Task 3.1**: Add command availability checks
  - Verify curl and git are available
  - Show list of missing commands if any
  - Exit early with actionable error

- [ ] **Task 3.2**: Add disk space check
  - Check for minimum 5GB free space
  - Warn and prompt if low
  - Allow override with confirmation

- [ ] **Task 3.3**: Add network connectivity check
  - Test connection to github.com
  - Exit with clear error if unreachable

### Phase 4: Add Idempotency Check

- [ ] **Task 4.1**: Add "already bootstrapped" detection
  - Create marker file after successful bootstrap
  - Check for marker on subsequent runs
  - Prompt user to confirm re-run
  - Show timestamp of previous run

### Phase 5: Fix Error Messages

- [ ] **Task 5.1**: Fix filename reference in checksum warning
  - Use BASH_SOURCE to get actual script name
  - Dynamic reference instead of hardcoded "bootstrap.sh"

---

## New Bootstrap Flow

```
1. check_required_commands()
2. check_disk_space()
3. check_network()
4. check_previous_bootstrap()
5. validate_dotfiles_directory()
6. validate_vault_password()
7. validate_inventory()
8. install_homebrew()  # With checksum verification
9. install_ansible()
10. run_ansible_playbook()
11. run_post_bootstrap()  # OS-specific
12. mark_bootstrap_complete()
```

---

## Validation Checklist

- [ ] Missing vault_password.txt shows helpful error
- [ ] Missing inventory triggers auto-fetch
- [ ] Network failure shows clear error
- [ ] Low disk space shows warning with prompt
- [ ] Re-running bootstrap prompts for confirmation
- [ ] Error messages reference correct filenames
- [ ] All checks can be bypassed with `--force` flag

## Files to Modify

| File | Action |
|------|--------|
| `local_bootstrap.sh` | Add validation functions |
| `nas_bootstrap.sh` | Add validation functions |
| `bootstrap.sh` | New unified script with all checks |

## Risk Assessment

- **Low Risk**: Adding checks only, no functional changes
- **User Experience**: More informative errors
- **Failure Mode**: Safe - script exits early on problems
- **Testing**: Test each validation path individually
