# Plan: Inventory Submodule Conflict Resolution

## Problem Statement

The personal dotfiles repository has conflicting approaches to inventory management:

1. **`.gitmodules`** declares `inventory/` as a git submodule pointing to
`git@github.com:connormason/dotfiles-inventory.git`
2. **`run.py:764-794`** treats inventory as a standalone git directory, using `git clone` and `git pull` directly

This creates confusion and potential breakage when:
- Running `python3 run.py update-inventory` destroys the submodule relationship
- Submodule operations (`git submodule update`) conflict with standalone git operations
- New clones of the repo may have inconsistent inventory state

## Current State

### .gitmodules (line 1-3)
```ini
[submodule "inventory"]
    path = inventory
    url = git@github.com:connormason/dotfiles-inventory.git
```

### run.py update-inventory logic (lines 776-793)
```python
# Inventory directory exists and is a git repo: pull latest
if INVENTORY_DIR.exists() and (INVENTORY_DIR / '.git').exists():
    pull_inventory_repo()

# Inventory directory exists, but isn't a git repo: remove and clone
elif INVENTORY_DIR.exists():
    shutil.rmtree(INVENTORY_DIR)  # <-- Destroys submodule\!
    clone_inventory_repo()

# Inventory directory does not exist: clone
else:
    clone_inventory_repo()
```

## Decision Required

**Choose ONE approach:**

| Approach | Pros | Cons |
|----------|------|------|
| **A: Full Submodule** | Standard git pattern, easier initial clone, version pinning | Requires submodule commands, more complex |
| **B: Standalone Clone** | Simpler mental model, run.py handles everything | Non-standard, requires manual management |

## Recommended: Approach B (Standalone Clone)

For personal dotfiles, simplicity trumps git purity. The inventory is always pulled fresh anyway.

---

## Implementation Tasks

### Phase 1: Remove Submodule Configuration

- [x] **Task 1.1**: Remove `.gitmodules` file
- [x] **Task 1.2**: Remove submodule tracking from git
- [x] **Task 1.3**: Update `.gitignore` to exclude inventory directory

### Phase 2: Enhance run.py Inventory Management

- [x] **Task 2.1**: Add inventory status check command
- [x] **Task 2.2**: Add `--force` flag to `update-inventory`
- [x] **Task 2.3**: Improve error handling for SSH key issues

### Phase 3: Update Documentation

- [x] **Task 3.1**: Update README with inventory setup instructions
- [ ] **Task 3.2**: Update CLAUDE.md to reflect new approach
- [ ] **Task 3.3**: Add inline documentation to run.py

---

## Validation Checklist

- [ ] Fresh clone of repo works correctly
- [ ] `python3 run.py update-inventory` succeeds
- [ ] `python3 run.py list-hosts` shows inventory hosts
- [ ] Bootstrap scripts can access inventory
- [ ] No orphaned git tracking for inventory directory

## Files to Modify

| File | Action |
|------|--------|
| `.gitmodules` | Delete (Approach B) or keep (Approach A) |
| `.gitignore` | Add `/inventory/` entry |
| `run.py` | Update inventory management logic |
| `README.md` | Document inventory setup |
| `CLAUDE.md` | Update architecture description |

## Risk Assessment

- **Low Risk**: Configuration change, not functional
- **Reversible**: Easy to switch approaches
- **Testing**: Can test in branch before merging
