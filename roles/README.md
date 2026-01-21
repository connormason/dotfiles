# Ansible Roles

This directory contains Ansible roles for automated configuration of macOS and Debian Linux systems. Roles are
organized by platform and provide modular, reusable configuration components for the dotfiles repository.

## Overview

The role system provides:
- **Platform-specific roles** for macOS and Linux system configuration
- **Shared roles** for cross-platform tools and configurations
- **Utility roles** for common operations like dotfile linking
- **External role dependencies** managed via `requirements.yml`

Roles are executed by playbooks in `playbooks/` and can be selectively applied using Ansible tags.

## Role Categories

### macOS Roles

Platform-specific roles for macOS configuration:

| Role | Description | Key Features |
|------|-------------|--------------|
| **macos** | Core macOS package management | Homebrew formulae (30+ CLI tools), cask apps (GUI applications), Mac App Store apps via `mas` CLI |
| **macos_settings** | System preferences configuration | Finder, Dock, Activity Monitor, Messages, power management, I/O devices via `defaults write` |
| **macos_dock** | Dock icon configuration | Manages Dock items and layout |
| **hammerspoon** | Window management automation | Configures Hammerspoon app for macOS window management |
| **iterm** | Terminal configuration | iTerm2 application setup and preferences |
| **python** | Python tooling for macOS | Global pip packages, pipx packages |

### Linux Roles

Platform-specific roles for Debian Linux systems:

| Role | Description | Key Features |
|------|-------------|--------------|
| **debian** | Base Debian system setup | System packages and configuration |
| **docker** | Docker containerization platform | Docker engine, Caddy reverse proxy, Autoplex/PyAutoplex image builds, Home Assistant, 195-line docker-compose stack |
| **zfs** | ZFS filesystem support | ZFS dependencies and configuration |
| **samba** | File sharing | Samba server configuration for network file sharing |
| **glance** | Dashboard application | [Glance](https://github.com/glanceapp/glance) dashboard setup |

### Shared Roles

Cross-platform roles that work on both macOS and Linux:

| Role | Description | Key Features |
|------|-------------|--------------|
| **git** | Git version control | Git configuration, gh CLI tool |
| **ssh** | SSH client/server | Key generation for remote hosts, ssh-agent loading for macOS, GitHub key authorization |
| **zsh** | Shell configuration | oh-my-zsh installation, Powerlevel10k theme, `.zshrc`/`.zprofile` setup, default shell configuration |
| **starship** | Shell prompt | Starship prompt installation and configuration (alternative to Powerlevel10k) |
| **link_dotfile** | Dotfile linking utility | Reusable role for safely creating symlinks with validation and backup |
| **tailscale** | VPN networking | [Tailscale VPN](https://tailscale.com/) setup using [artis3n.tailscale](https://github.com/artis3n/ansible-role-tailscale) role |

## Role Dependencies

### External Dependencies

External roles and collections are managed in `roles/requirements.yml`:

**External Roles:**
- `elliotweiser.osx-command-line-tools` - macOS command-line tools installation
- `artis3n.tailscale` - Tailscale VPN setup

**Ansible Collections:**
- `ansible.posix` - POSIX-specific modules
- `community.general` - Community-maintained general modules (includes `pipx` module)
- `geerlingguy.mac` - macOS-specific modules (Homebrew, Mac App Store)

Install external dependencies:
```bash
ansible-galaxy install -r roles/requirements.yml
```

### Internal Role Dependencies

Some roles depend on other roles in this repository:

**macos role:**
- Uses `elliotweiser.osx-command-line-tools` for Xcode CLI tools
- Uses `geerlingguy.mac.homebrew` for package management
- Uses `geerlingguy.mac.mas` for App Store apps

**python role:**
- Requires `macos` role to install `pipx` via Homebrew (macOS)
- Uses pipx executable from Homebrew prefix

**zsh role:**
- On macOS: Uses `elliotweiser.osx-command-line-tools` and `geerlingguy.mac.homebrew`
- Installs oh-my-zsh and Powerlevel10k theme
- Different behavior for localhost (symlinks) vs. remote hosts (copies files)

**starship role:**
- Uses `link_dotfile` role to symlink configuration
- Alternative to Powerlevel10k prompt in zsh

**docker role:**
- Linux only
- Sets up complete Docker infrastructure including custom image builds
- Clones and builds multiple custom images (Caddy, Autoplex, PyAutoplex)
- Configures Home Assistant with secrets and Lutron Caseta certificates
- Deploys docker-compose stack with media server services

## Usage Patterns

### Running Roles in Playbooks

Roles are included in playbooks using `include_role`:

```yaml
- name: Personal Mac bootstrap
  hosts: localhost
  tasks:
    - include_role:
        name: roles/git
        apply:
          tags: git
      tags:
        - git
        - configfile
```

### Running Specific Roles

Execute only specific roles using tags:

```bash
# Run only git configuration
ansible-playbook playbooks/local_bootstrap.yml -i inventory/inventory.yml --ask-become-pass --tags git

# Run multiple related roles
ansible-playbook playbooks/local_bootstrap.yml -i inventory/inventory.yml --ask-become-pass --tags zsh,git,ssh

# Run all dotfile configuration roles
ansible-playbook playbooks/local_bootstrap.yml -i inventory/inventory.yml --ask-become-pass --tags configfile
```

### Running Roles Standalone

Roles can be tested independently:

```bash
# Create a test playbook
cat > test_role.yml <<EOF
---
- hosts: localhost
  tasks:
    - include_role:
        name: roles/link_dotfile
      vars:
        link_dotfile_src: "{{ playbook_dir }}/test_source"
        link_dotfile_dst: "{{ ansible_facts['user_dir'] }}/test_dest"
EOF

# Run it
ansible-playbook test_role.yml
```

### Common Playbook Patterns

**Local Mac Bootstrap** (`playbooks/local_bootstrap.yml`):
```bash
chmod u+x local_bootstrap.sh && ./local_bootstrap.sh
```
Runs: zsh, macos, macos_settings, macos_dock, git, hammerspoon, iterm, ssh, starship, python

**NAS Server Bootstrap** (`playbooks/nas_bootstrap.yml`):
```bash
chmod u+x nas_bootstrap.sh && ./nas_bootstrap.sh
```
Runs: debian, zfs, samba, docker, glance, git, ssh, zsh

## The link_dotfile Pattern

The `link_dotfile` role provides a reusable pattern for safely linking dotfiles from the repository to their target
locations. This is the **preferred method** for managing dotfile symlinks across all roles.

### Why Use link_dotfile?

- **Validation**: Ensures source files exist before linking
- **Safety**: Backs up existing files with timestamps before replacing
- **Idempotency**: Only creates/updates links when necessary
- **Consistency**: Standardized error handling and debug output
- **Best Practice**: Centralizes linking logic instead of duplicating `ansible.builtin.file` tasks

### Basic Usage

```yaml
- name: Link git config
  ansible.builtin.include_role:
    name: roles/link_dotfile
  vars:
    link_dotfile_src: "{{ dotfiles_home }}/roles/git/files/gitconfig"
    link_dotfile_dst: "{{ user_home }}/.gitconfig"
```

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `link_dotfile_src` | Absolute path to source file in dotfiles repo | `{{ dotfiles_home }}/roles/git/files/gitconfig` |
| `link_dotfile_dst` | Absolute path to destination (target location) | `{{ user_home }}/.gitconfig` |

### Optional Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `dotfile_dir_mode` | Permissions for created parent directories | `omit` (uses default) |

### Advanced Example: Linking Multiple Files

```yaml
- name: Link shell dotfiles
  ansible.builtin.include_role:
    name: roles/link_dotfile
  vars:
    link_dotfile_src: "{{ dotfiles_home }}/roles/shell/files/{{ item }}"
    link_dotfile_dst: "{{ user_home }}/.{{ item }}"
  loop:
    - zshrc
    - zprofile
    - zshenv
```

### Real-World Example: Starship Configuration

From `roles/starship/tasks/main.yaml`:

```yaml
- name: Configure Starship
  tags:
    - configfile
    - preferences
  block:
    - name: Link starship.toml config
      ansible.builtin.include_role:
        name: roles/link_dotfile
      vars:
        link_dotfile_src: "{{ dotfiles_home }}/roles/starship/files/starship.toml"
        link_dotfile_dst: "{{ user_home }}/.config/starship.toml"
```

### Behavior

**Linking Decision Tree:**
```
1. Check destination file status
   ├─ Does not exist
   │  └─ Create parent directory → Create symlink
   │
   ├─ Exists as regular file (not symlink)
   │  └─ Backup file → Create symlink
   │
   ├─ Exists as symlink pointing to correct source
   │  └─ Skip (already correct) ✓
   │
   └─ Exists as symlink pointing to wrong source
      └─ Remove symlink → Create new symlink
```

**Backup Example:**
When a non-symlink file exists at the destination, it's backed up with a timestamp:
```
.zshrc.backup_20250219143022
```

### Complete Documentation

For comprehensive documentation including error handling, testing, and best practices, see:
**[roles/link_dotfile/README.md](link_dotfile/README.md)** (214 lines)

## Creating New Roles

### Role Directory Structure

Standard Ansible role structure:

```
roles/
└── my_new_role/
    ├── README.md              # Role documentation
    ├── defaults/
    │   └── main.yml           # Default variables
    ├── vars/
    │   └── main.yml           # Role-specific variables
    ├── tasks/
    │   └── main.yml           # Main task definitions
    ├── files/                 # Static files to copy/link
    │   └── config_file
    ├── templates/             # Jinja2 templates
    │   └── config.j2
    └── handlers/
        └── main.yml           # Handlers (optional)
```

### Step-by-Step: Creating a New Role

#### 1. Create Role Directory Structure

```bash
# Create basic structure
mkdir -p roles/my_new_role/{tasks,defaults,files}

# Create main task file
cat > roles/my_new_role/tasks/main.yml <<EOF
---
- name: My new role tasks
  block:
    - name: Example task
      ansible.builtin.debug:
        msg: "Hello from my_new_role"
EOF

# Create defaults file (optional)
cat > roles/my_new_role/defaults/main.yml <<EOF
---
my_role_setting: "default_value"
EOF

# Create README
cat > roles/my_new_role/README.md <<EOF
# my_new_role

Brief description of what this role does.

## Features
- Feature 1
- Feature 2
EOF
```

#### 2. Add Role to Playbook

Edit `playbooks/local_bootstrap.yml` or `playbooks/nas_bootstrap.yml`:

```yaml
- include_role:
    name: roles/my_new_role
    apply:
      tags: my_new_role
  tags:
    - my_new_role
    - configfile  # Add to existing tag groups if appropriate
```

#### 3. Test the Role

```bash
# Run with verbose output
ansible-playbook playbooks/local_bootstrap.yml \
  -i inventory/inventory.yml \
  --ask-become-pass \
  --tags my_new_role \
  -vv

# Check mode (dry run)
ansible-playbook playbooks/local_bootstrap.yml \
  -i inventory/inventory.yml \
  --ask-become-pass \
  --tags my_new_role \
  --check
```

### Example: Role for Linking Dotfiles

```yaml
# roles/my_app/tasks/main.yml
---
- name: Link my app configuration
  ansible.builtin.include_role:
    name: roles/link_dotfile
  vars:
    link_dotfile_src: "{{ dotfiles_home }}/roles/my_app/files/config.yaml"
    link_dotfile_dst: "{{ user_home }}/.config/myapp/config.yaml"
```

### Example: Platform-Specific Role

```yaml
# roles/my_tool/tasks/main.yml
---
- name: Install on macOS
  when: ansible_distribution == 'MacOSX'
  block:
    - name: Install with Homebrew
      community.general.homebrew:
        name: my-tool
        state: present

- name: Install on Debian
  when: ansible_distribution == 'Debian'
  block:
    - name: Install with apt
      become: true
      ansible.builtin.apt:
        name: my-tool
        state: present
```

### Example: Role with External Dependencies

```yaml
# roles/my_tool/tasks/main.yml
---
- name: Install command-line tools (macOS)
  when: ansible_distribution == 'MacOSX'
  include_role:
    name: elliotweiser.osx-command-line-tools

- name: Install the tool
  # ... installation tasks
```

### Best Practices

1. **Use link_dotfile for symlinks**: Don't duplicate linking logic with `ansible.builtin.file`
2. **Document in README.md**: Explain what the role does and any special requirements
3. **Use defaults/main.yml**: Define configurable variables with sensible defaults
4. **Tag appropriately**: Add meaningful tags for selective execution
5. **Platform awareness**: Use `when: ansible_distribution == 'MacOSX'` for platform-specific tasks
6. **Idempotency**: Ensure tasks can be run multiple times safely
7. **External dependencies**: Add to `requirements.yml` if using external roles/collections
8. **Group related tasks**: Use `block:` to organize related tasks with shared properties

## Common Variables

Variables commonly used across roles, defined in inventory (`inventory/inventory.yml` and `inventory/group_vars/`):

### Path Variables

```yaml
dotfiles_home: "/path/to/dotfiles-personal"  # Repository root
user_home: "{{ ansible_facts['user_dir'] }}"  # User home directory
homebrew_prefix: "/opt/homebrew"              # Homebrew installation path (macOS)
```

### User Variables

```yaml
ansible_user: "username"           # Current user for SSH/sudo operations
admin_password: "{{ vault_pass }}"  # Admin password from Ansible Vault
```

### Service-Specific Variables

```yaml
# Docker role
docker_dir: "/path/to/docker"
caddy_dnsimple_repo_url: "git@github.com:..."
autoplex_repo_url: "git@github.com:..."
homeassistant_repo_url: "git@github.com:..."

# Starship role
starship_version: "v1.17.1"
starship_install_directory: "/usr/local/bin"
starship_owner: "root"
starship_group: "root"

# Python role
global_python_packages:
  - package1
  - package2
pipx_packages:
  - package3
  - package4
```

### Accessing Variables

In role tasks:
```yaml
- name: Link dotfile
  ansible.builtin.file:
    src: "{{ dotfiles_home }}/roles/git/files/gitconfig"
    dest: "{{ user_home }}/.gitconfig"
    state: link
```

In role defaults:
```yaml
# roles/my_role/defaults/main.yml
---
my_config_dir: "{{ user_home }}/.config/my_app"
my_data_dir: "{{ user_home }}/.local/share/my_app"
```

## Package Management Roles

### macOS Package Management

The `macos` role manages three layers of macOS package installation:

**1. Homebrew Formulae** (CLI tools):
```yaml
# roles/macos/defaults/main.yml
brew_packages:
  - autojump      # Directory jumping
  - bat           # Better cat
  - btop          # System monitor
  - fzf           # Fuzzy finder
  - gh            # GitHub CLI
  - git-delta     # Git diff viewer
  - jq            # JSON processor
  - lazygit       # Git TUI
  - ripgrep       # Fast grep
  # ... 30+ packages total
```

**2. Homebrew Casks** (GUI applications):
```yaml
brew_cask_packages:
  - google-chrome
  - hammerspoon
  - iterm2
  - pycharm-ce
  - signal
  - spotify
  - sublime-text
```

**3. Mac App Store Apps** (via `mas` CLI):
```yaml
mas_apps:
  - name: Amphetamine
    id: 937984704
  - name: iStat Menus
    id: 1319778037
  - name: Tailscale
    id: 1475387142
```

### Python Package Management

The `python` role manages Python packages through multiple installation methods:

**Global pip packages**:
```yaml
global_python_packages:
  - package1
  - package2
```
Installed via: `/usr/bin/pip3 install`

**Isolated pipx packages**:
```yaml
pipx_packages:
  - package3
  - package4
```
Installed via: `pipx install` (requires pipx from Homebrew)

### Debian Package Management

The `debian` role manages system packages via apt:
```yaml
- name: Install system packages
  become: true
  ansible.builtin.apt:
    pkg:
      - package1
      - package2
```

## Docker Stack Configuration

The `docker` role provides comprehensive Docker infrastructure for the home NAS server. It's one of the most complex
roles in the repository.

### Docker Services Deployed

The 195-line `docker-compose.yml` deploys:

**Media Server Stack:**
- **Plex**: Media server
- **Sonarr**: TV show automation
- **Radarr**: Movie automation
- **Transmission**: BitTorrent client
- **Prowlarr**: Indexer manager
- **Flaresolverr**: CloudFlare bypass
- **Autoplex/PyAutoplex**: Automated file organization

**Infrastructure:**
- **PiHole**: DNS server and ad blocker
- **Caddy**: Reverse proxy with automatic HTTPS
- **Home Assistant**: Home automation platform
- **Glance**: Dashboard

### Docker Role Features

**1. Docker Engine Installation:**
- Adds Docker official repository
- Installs Docker CE, CLI, Containerd
- Installs docker-compose plugin

**2. Custom Image Builds:**
- Clones and builds custom Caddy image with DNSimple support
- Builds Autoplex from private repository
- Builds PyAutoplex from private repository

**3. Home Assistant Setup:**
- Clones Home Assistant configuration repository
- Generates `secrets.yaml` from Ansible Vault variables
- Copies Lutron Caseta certificates/keys for smart home integration

**4. Service Configuration:**
- Generates Caddyfile from Jinja2 template with host IP
- Creates `.env` file with DNSimple OAuth token
- Deploys complete docker-compose stack

### Docker Role Variables

Required variables in inventory:
```yaml
docker_dir: "/path/to/docker/configs"
caddy_dnsimple_repo_url: "git@github.com:user/caddy-dnsimple.git"
caddy_dnsimple_repo_dest: "/path/to/caddy-dnsimple"
caddy_dnsimple_repo_branch: "main"
autoplex_repo_url: "git@github.com:user/autoplex.git"
autoplex_repo_dest: "/path/to/autoplex"
autoplex_repo_branch: "main"
pyautoplex_repo_url: "git@github.com:user/pyautoplex.git"
pyautoplex_repo_dest: "/path/to/pyautoplex"
pyautoplex_repo_branch: "main"
homeassistant_repo_url: "git@github.com:user/homeassistant-config.git"
homeassistant_repo_dest: "/path/to/homeassistant"
homeassistant_repo_branch: "main"
```

## Role Testing and Validation

### Pre-commit Validation

Roles are validated via pre-commit hooks (`.pre-commit-config.yaml`):

```bash
# Run all checks
pre-commit run --all-files

# Or via Python script
python3 run.py pre
```

**Active checks:**
- YAML validation (yamllint)
- File integrity checks
- Whitespace/line ending fixers

**Available but commented:**
- ansible-lint (full Ansible best practices)
- shellcheck (shell script validation)

### ansible-lint Configuration

When enabled, ansible-lint uses `.config/.ansible-lint.yaml`:
```yaml
# Skip certain rule categories
skip_list:
  - yaml[line-length]
  - name[casing]
```

### yamllint Configuration

YAML linting uses `.config/.yamllint.yaml`:
```yaml
# Custom rules for role files
rules:
  line-length:
    max: 120
  indentation:
    spaces: 2
```

### Manual Testing

**Dry run (check mode):**
```bash
ansible-playbook playbooks/local_bootstrap.yml \
  -i inventory/inventory.yml \
  --ask-become-pass \
  --check \
  --diff
```

**Verbose output:**
```bash
ansible-playbook playbooks/local_bootstrap.yml \
  -i inventory/inventory.yml \
  --ask-become-pass \
  -vv
```

**Test specific role:**
```bash
ansible-playbook playbooks/local_bootstrap.yml \
  -i inventory/inventory.yml \
  --ask-become-pass \
  --tags my_role \
  --check \
  -vv
```

## Role Maintenance

### Updating External Dependencies

```bash
# Update roles and collections
ansible-galaxy install -r roles/requirements.yml --force

# Update only roles
ansible-galaxy role install -r roles/requirements.yml --force

# Update only collections
ansible-galaxy collection install -r roles/requirements.yml --force
```

### Adding External Dependencies

Edit `roles/requirements.yml`:

```yaml
---
roles:
  - name: username.rolename
    version: "1.0.0"  # Optional: pin to specific version

collections:
  - name: namespace.collection
    version: ">=2.0.0"  # Optional: version constraint
```

Then install:
```bash
ansible-galaxy install -r roles/requirements.yml
```

### Role Versioning

Roles in this repository follow semantic versioning through git:
- Use git tags for version tracking
- Document breaking changes in role README.md
- Test role changes before merging to main branch

## Troubleshooting

### Role Not Found

**Error:**
```
ERROR! the role 'roles/my_role' was not found
```

**Solutions:**
1. Check role name spelling in playbook
2. Verify role directory exists: `ls -la roles/my_role`
3. Ensure `tasks/main.yml` exists in role directory

### External Role Not Found

**Error:**
```
ERROR! the role 'external.role' was not found
```

**Solutions:**
1. Install dependencies: `ansible-galaxy install -r roles/requirements.yml`
2. Check `roles/requirements.yml` contains the role
3. Verify installation: `ansible-galaxy role list`

### Variable Undefined

**Error:**
```
fatal: [localhost]: FAILED! => {"msg": "The task includes an option with an undefined variable"}
```

**Solutions:**
1. Check variable is defined in `defaults/main.yml` or `vars/main.yml`
2. Verify variable exists in inventory: `inventory/group_vars/` or `inventory/host_vars/`
3. Pass variable via command line: `-e "var_name=value"`

### Permission Denied

**Error:**
```
fatal: [localhost]: FAILED! => {"msg": "Permission denied"}
```

**Solutions:**
1. Add `become: true` to task requiring sudo
2. Use `--ask-become-pass` when running playbook
3. Verify sudo password is correct in vault

### Vault Decryption Failed

**Error:**
```
ERROR! Attempting to decrypt but no vault secrets found
```

**Solutions:**
1. Create `vault_password.txt` in repository root
2. Verify password is correct
3. Check vault file is properly encrypted: `ansible-vault view inventory/group_vars/all/vault.yml`

## Related Documentation

- **[roles/link_dotfile/README.md](link_dotfile/README.md)** - Comprehensive dotfile linking guide (214 lines)
- **[scripts/installers/README.md](../scripts/installers/README.md)** - Bulletproof installer scripts reference (275 lines)
- **[playbooks/](../playbooks/)** - Playbook documentation and usage examples
- **[inventory/](../inventory/)** - Inventory structure and variable definitions

## References

- **Ansible Documentation**: https://docs.ansible.com/
- **Ansible Galaxy**: https://galaxy.ansible.com/
- **geerlingguy.mac Collection**: https://github.com/geerlingguy/ansible-collection-mac
- **Homebrew**: https://brew.sh/
- **oh-my-zsh**: https://ohmyz.sh/
- **Starship Prompt**: https://starship.rs/
- **Docker Compose**: https://docs.docker.com/compose/
