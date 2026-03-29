# Plan: Role Documentation and External Dependencies

## Problem Statement

1. **16 roles exist** but documentation quality varies
2. **External role dependencies** are used but not declared in `requirements.yml`
3. **Missing role README.md** files or outdated content
4. **No role metadata** (meta/main.yml) for dependencies and platforms

## Current State Analysis

### Role Documentation Audit

| Role | README.md | Defaults | Meta | Notes |
|------|-----------|----------|------|-------|
| debian | Yes | No | No | Linux-specific |
| docker | Yes | Yes | No | Complex, needs better docs |
| git | Yes | Yes | No | Good |
| glance | Yes | Yes | No | Good |
| hammerspoon | Yes | Yes | No | Good |
| iterm | Yes | Yes | No | Good |
| link_dotfile | Yes | Yes | No | Good (reusable) |
| macos | Yes | Yes | No | Good |
| macos_dock | Yes | Yes | No | Good |
| macos_settings | Yes | Yes | No | Good |
| python | Yes | Yes | No | Good |
| samba | Yes | Yes | No | Linux-specific |
| ssh | Yes | Yes | No | Good |
| starship | No | Yes | No | Missing README |
| tailscale | Yes | Yes | No | Good |
| zfs | Yes | Yes | No | Linux-specific |
| zsh | Yes | Yes | No | Uses external roles |

### External Dependencies Not in requirements.yml

From `roles/zsh/tasks/main.yml`:
```yaml
- name: Install oh-my-zsh
  include_role:
    name: gantsign.oh-my-zsh  # External role\!

- name: Install powerlevel10k
  include_role:
    name: diodonfrost.p10k    # External role\!
```

These external roles will fail to run unless manually installed.

---

## Implementation Tasks

### Phase 1: Create/Update requirements.yml

- [ ] **Task 1.1**: Create comprehensive requirements.yml
  ```yaml
  ---
  # roles/requirements.yml

  # External Ansible roles
  roles:
    # Oh-my-zsh installation
    - name: gantsign.oh-my-zsh
      version: 2.16.0

    # Powerlevel10k theme
    - name: diodonfrost.p10k
      version: 1.3.0

    # macOS command line tools (if using)
    - name: elliotweiser.osx-command-line-tools
      version: 3.3.0

    # Homebrew management (if using geerlingguy)
    - name: geerlingguy.mac.homebrew
      version: 4.2.0

  # Collections (if any)
  collections: []
  ```

- [ ] **Task 1.2**: Add requirements installation to bootstrap
  ```bash
  # Add before running playbook
  ansible-galaxy install -r roles/requirements.yml --force
  ```

- [ ] **Task 1.3**: Add to run.py as install-requirements command

### Phase 2: Add Role Metadata Files

- [ ] **Task 2.1**: Create meta/main.yml template
  ```yaml
  ---
  # roles/<role_name>/meta/main.yml

  galaxy_info:
    author: Connor Mason
    description: <Role description>
    license: MIT
    min_ansible_version: "2.14"

    platforms:
      - name: MacOSX
        versions: [all]
      # Or for Linux roles:
      - name: Debian
        versions: [all]

    galaxy_tags:
      - dotfiles
      - macos
      - development

  dependencies:
    # List role dependencies here
    # - role: other_role
  ```

- [ ] **Task 2.2**: Add meta/main.yml to roles that use external dependencies
  ```yaml
  # roles/zsh/meta/main.yml
  dependencies:
    - role: gantsign.oh-my-zsh
    - role: diodonfrost.p10k
  ```

### Phase 3: Create Missing README.md Files

- [ ] **Task 3.1**: Create README template
  ```markdown
  # <Role Name>

  Brief description of what this role does.

  ## Requirements

  - macOS 12+ (or Debian 11+)
  - Ansible 2.14+
  - Dependencies: list any external roles

  ## Role Variables

  | Variable | Default | Description |
  |----------|---------|-------------|
  | `var_name` | `default` | What it does |

  ## Example Playbook

  ```yaml
  - hosts: localhost
    roles:
      - role: <role_name>
        vars:
          var_name: value
  ```

  ## Tags

  - `<role_name>`: All tasks in this role

  ## Files Managed

  - `~/.config/app/config`: Configuration file
  ```

- [ ] **Task 3.2**: Create README.md for starship role (missing)

- [ ] **Task 3.3**: Update existing READMEs to match template

### Phase 4: Document Role Dependencies Visually

- [ ] **Task 4.1**: Create role dependency diagram
  ```
  local_bootstrap.yml
  ├── macos
  │   └── (homebrew packages, casks, MAS apps)
  ├── git
  │   └── link_dotfile
  ├── zsh
  │   ├── gantsign.oh-my-zsh (external)
  │   ├── diodonfrost.p10k (external)
  │   └── link_dotfile
  ├── python
  │   └── link_dotfile
  └── ...
  ```

- [ ] **Task 4.2**: Add dependency diagram to main README

### Phase 5: Add Role Tags Documentation

- [ ] **Task 5.1**: Document all available tags in README
  ```markdown
  ## Available Tags

  | Tag | Roles | Description |
  |-----|-------|-------------|
  | `brew` | macos | Homebrew packages and casks |
  | `git` | git | Git configuration |
  | `shell` | zsh | Zsh and oh-my-zsh setup |
  | `python` | python | Python tooling |
  | `configfile` | multiple | Tasks that create config files |
  ```

---

## README Template for Roles

```markdown
# <Role Name> Role

One-line description.

## Overview

Longer description of what this role configures.

## Requirements

### Platform Support

| Platform | Versions | Status |
|----------|----------|--------|
| macOS | 12+ | Supported |
| Debian | 11+ | Not supported |

### Dependencies

- `gantsign.oh-my-zsh` (if applicable)
- `link_dotfile` role (internal)

## Variables

### Required Variables

| Variable | Description |
|----------|-------------|
| `home_dir` | User home directory |

### Optional Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `role_option` | `true` | Enable feature |

## Example Usage

```yaml
- hosts: localhost
  roles:
    - role: role_name
      vars:
        role_option: false
```

## Files Created/Modified

| Path | Type | Description |
|------|------|-------------|
| `~/.config/app` | Directory | Config directory |
| `~/.config/app/config` | Symlink | Main config |

## Tags

- `role_name`: All tasks
- `configfile`: Only config file tasks

## Troubleshooting

### Common Issues

1. **Issue description**
   - Solution steps
```

---

## Validation Checklist

- [ ] `ansible-galaxy install -r roles/requirements.yml` succeeds
- [ ] All roles have README.md
- [ ] All roles have meta/main.yml
- [ ] External dependencies documented
- [ ] Tag documentation is accurate
- [ ] Bootstrap works with fresh role install

## Files to Create/Modify

| File | Action |
|------|--------|
| `roles/requirements.yml` | Create/update with all dependencies |
| `roles/*/meta/main.yml` | Create for all roles |
| `roles/starship/README.md` | Create (missing) |
| `roles/*/README.md` | Update to template |
| `README.md` | Add dependency diagram and tag list |

## Risk Assessment

- **Low Risk**: Documentation changes only
- **Impact**: Better maintainability
- **Testing**: Run full bootstrap after requirements.yml changes
- **Dependencies**: External roles must be pinned to stable versions
