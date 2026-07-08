# Plan: Repository Integration Strategy (Personal + Work Dotfiles)

## Problem Statement

You maintain two separate dotfiles repositories:
- **Personal** (`~/dotfiles-personal`): Supports macOS + NAS Linux, broader scope
- **Work** (`~/dotfiles`): macOS only, Apple-specific tools, more mature run.py

Goals:
1. Use personal dotfiles as the **base** for all machines
2. Work dotfiles **extend/override** personal configuration
3. Keep repos **separate** but **composable**
4. Minimize duplication while maximizing flexibility

## Current State Comparison

### Personal Dotfiles (dotfiles-personal)
- **Targets**: macOS (local), Debian Linux (NAS)
- **Bootstrap**: Separate scripts per target
- **run.py**: ~1,090 lines, basic commands
- **Roles**: 16 roles (some Linux-specific)
- **Inventory**: Git submodule (conflicted)

### Work Dotfiles (dotfiles)
- **Targets**: macOS only (local + remote)
- **Bootstrap**: Single flexible script + robust run.py
- **run.py**: ~2,578 lines, comprehensive commands
- **Features not in personal**:
  - `bootstrap` command with --only/--skip/--dry-run
  - `preflight` command for pre-bootstrap checks
  - `validate` command for post-bootstrap verification
  - `report` and `backup` commands
  - Remote bootstrap support (rsync + SSH)
  - Custom Ansible modules
  - Apple-specific roles (fika, secrets, AppleConnect)

---

## Integration Approaches

### Approach A: Layered Playbook Import (Recommended)

Work dotfiles imports personal playbook, then adds work-specific config.

```yaml
# ~/dotfiles/playbooks/bootstrap.yml
---
# Phase 1: Import personal dotfiles base configuration
- name: Import personal dotfiles playbook
  import_playbook: ~/dotfiles-personal/playbooks/local_bootstrap.yml
  when: use_personal_base | default(true)

# Phase 2: Work-specific extensions
- name: Work-specific configuration
  hosts: "{{ bootstrap_target_host | default('localhost') }}"
  vars:
    # Extend personal package lists
    brew_packages_work:
      - corporate-tool
      - xcode
    brew_cask_packages_work:
      - slack-enterprise
      - zoom-enterprise
  roles:
    - role: fika
      tags: [fika]
    - role: secrets
      tags: [secrets]
    - role: apple_connect
      tags: [apple_connect]
```

**Pros**:
- Clean separation of concerns
- Personal repo stays portable
- Standard Ansible pattern
- Easy to disable personal base

**Cons**:
- Requires personal dotfiles cloned at fixed path
- Variable merging requires care

### Approach B: Git Submodule

Personal dotfiles as submodule in work repo.

```
dotfiles/
├── personal/              # Submodule: dotfiles-personal
├── playbooks/
│   └── bootstrap.yml      # Imports personal/playbooks/*
└── roles/
    └── work_specific/
```

**Pros**:
- Single repo to clone for work
- Version pinning possible

**Cons**:
- Submodule complexity
- Updates require submodule sync
- Personal changes need separate commits

### Approach C: Ansible Collection

Convert personal dotfiles to Ansible collection, install via Galaxy.

```yaml
# requirements.yml
collections:
  - name: connormason.personal_dotfiles
    source: git@github.com:connormason/dotfiles-personal.git
    type: git
```

**Pros**:
- Most "official" Ansible approach
- Proper namespace isolation
- Versioning via tags

**Cons**:
- Significant refactoring required
- Collection structure is rigid
- Overkill for personal use

---

## Recommended Implementation: Approach A

### Phase 1: Prepare Personal Dotfiles for Reuse

- [ ] **Task 1.1**: Make playbook paths portable
  ```yaml
  # playbooks/local_bootstrap.yml - Add vars at top
  vars:
    dotfiles_dir: "{{ playbook_dir | dirname }}"
    personal_dotfiles_dir: "{{ dotfiles_dir }}"
  ```

- [ ] **Task 1.2**: Extract variable files for extension
  ```yaml
  # roles/macos/defaults/main.yml
  # Add "_base" suffix to lists that should be extensible
  brew_packages_base:
    - git
    - gh
    - jq

  brew_packages: "{{ brew_packages_base + brew_packages_extra | default([]) }}"
  ```

- [ ] **Task 1.3**: Add conditional role execution
  ```yaml
  # Skip roles when used as base layer
  - role: macos
    when: not skip_personal_macos | default(false)
  ```

### Phase 2: Configure Work Dotfiles to Import Personal

- [ ] **Task 2.1**: Add personal dotfiles path configuration
  ```python
  # run.py additions
  PERSONAL_DOTFILES_DIR = Path.home() / "dotfiles-personal"

  @command(group="Setup")
  def cmd_setup_personal_base(args):
      """Clone personal dotfiles if not present"""
      if not PERSONAL_DOTFILES_DIR.exists():
          shell_command([
              "git", "clone",
              "git@github.com:connormason/dotfiles-personal.git",
              str(PERSONAL_DOTFILES_DIR)
          ])
  ```

- [ ] **Task 2.2**: Create work bootstrap playbook with import
  ```yaml
  # playbooks/bootstrap.yml
  ---
  - name: Personal dotfiles base
    import_playbook: ~/dotfiles-personal/playbooks/local_bootstrap.yml
    vars:
      # Override/extend personal vars
      brew_packages_extra:
        - work-specific-tool

  - name: Work-specific setup
    hosts: localhost
    roles:
      - secrets
      - fika
  ```

- [ ] **Task 2.3**: Add `--no-personal` flag to skip base import
  ```python
  parser.add_argument("--no-personal", action="store_true",
                      help="Skip personal dotfiles base layer")
  ```

### Phase 3: Port Features from Work to Personal

Port valuable features from work dotfiles back to personal:

- [ ] **Task 3.1**: Port `preflight` command
- [ ] **Task 3.2**: Port `validate` command
- [ ] **Task 3.3**: Port `report` command
- [ ] **Task 3.4**: Port bootstrap options (--only, --skip, --dry-run)
- [ ] **Task 3.5**: Port remote bootstrap support (optional)

### Phase 4: Consolidate Common Code

- [ ] **Task 4.1**: Extract shared run.py utilities to importable module
- [ ] **Task 4.2**: Create shared Ansible vars file for common settings
- [ ] **Task 4.3**: Document the layering pattern

---

## Variable Merging Strategy

```yaml
# Personal dotfiles define base lists
brew_packages_base:
  - git
  - gh
  - jq

# Work dotfiles extend
brew_packages_work:
  - corporate-tool
  - xcode

# Merged in playbook
brew_packages: "{{ brew_packages_base + brew_packages_work }}"
```

---

## Directory Structure After Integration

```
~/dotfiles-personal/           # Personal repo (base layer)
├── playbooks/
│   ├── local_bootstrap.yml    # macOS bootstrap
│   └── nas_bootstrap.yml      # NAS bootstrap
├── roles/
│   ├── macos/                 # Homebrew, casks, MAS apps
│   ├── git/                   # Git configuration
│   ├── zsh/                   # Shell setup
│   └── ...
├── inventory/                 # Personal inventory
└── run.py                     # Management script

~/dotfiles/                    # Work repo (extension layer)
├── playbooks/
│   └── bootstrap.yml          # Imports personal + adds work
├── roles/
│   ├── secrets/               # Work credentials
│   ├── fika/                  # Apple tools
│   └── apple_connect/         # AppleConnect setup
├── library/                   # Custom Ansible modules
├── inventory/                 # Work inventory
└── run.py                     # Extended management script
```

---

## Bootstrap Flow After Integration

```
./bootstrap.sh (work repo)
    |
    v
[1] Validate personal dotfiles exist
    |-- Clone if missing
    v
[2] Run personal bootstrap (import_playbook)
    |-- Install Homebrew
    |-- Install base packages
    |-- Configure shell, git, etc.
    v
[3] Run work-specific roles
    |-- Deploy secrets
    |-- Setup Apple tools
    |-- Configure Apple-specific settings
    v
[4] Run validation checks
```

---

## Validation Checklist

- [ ] Personal dotfiles work standalone
- [ ] Work dotfiles work with personal base
- [ ] Work dotfiles work without personal (--no-personal)
- [ ] Variable merging produces correct package lists
- [ ] No duplicate role execution
- [ ] Both inventories accessible
- [ ] Bootstrap completes successfully

## Files to Modify

### Personal Dotfiles
| File | Action |
|------|--------|
| `playbooks/*.yml` | Add portable vars, conditional execution |
| `roles/*/defaults/main.yml` | Split lists into base + extra |
| `run.py` | Port features from work |

### Work Dotfiles
| File | Action |
|------|--------|
| `playbooks/bootstrap.yml` | Add import_playbook directive |
| `run.py` | Add setup-personal-base command |
| `README.md` | Document layering pattern |

## Risk Assessment

- **Medium Risk**: Changes to both repos required
- **Mitigation**: Test layering on fresh VM first
- **Rollback**: Both repos remain independently functional
- **Testing**: Create integration test that bootstraps both layers
