# Playbooks

Ansible playbooks for automated system configuration. This directory contains two bootstrap workflows targeting
different environments: personal macOS machines and home NAS/server infrastructure.

## Table of Contents

- [Overview](#overview)
- [Playbook Workflows](#playbook-workflows)
  - [local_bootstrap.yml](#local_bootstrapyml)
  - [nas_bootstrap.yml](#nas_bootstrapyml)
- [Execution Methods](#execution-methods)
- [Bootstrap Scripts](#bootstrap-scripts)
- [Tag System](#tag-system)
- [Security Considerations](#security-considerations)
- [Troubleshooting](#troubleshooting)

## Overview

The playbook system provides two complete environment bootstraps:

| Playbook | Target | Bootstrap Script | Purpose |
|----------|--------|------------------|---------|
| `local_bootstrap.yml` | macOS (localhost) | `local_bootstrap.sh` | Personal Mac configuration with GUI apps, dev tools, and system settings |
| `nas_bootstrap.yml` | Debian server (nas host) | `nas_bootstrap.sh` | Home NAS with Docker media stack, file sharing, and network services |

Both playbooks:
- Require inventory from separate git submodule (`inventory/`)
- Use encrypted Ansible Vault for secrets
- Support selective execution via tags
- Set become password from vault for privilege escalation

## Playbook Workflows

### local_bootstrap.yml

Configures personal macOS machines with development environment, GUI applications, and system preferences.

**Host target:** `localhost` (defined in `inventory/inventory.yml`)

**Role execution order:**

1. **zsh** - Shell configuration and plugins
   - Tags: `zsh`, `configfile`
2. **macos** - Package manager setup (Homebrew, casks, Mac App Store)
   - Tags: `macos`
3. **macos_settings** - System preferences (Finder, Activity Monitor, etc.)
   - Tags: `macos`, `dock`
4. **macos_dock** - Dock configuration and layout
   - Tags: `macos`, `dock`
5. **git** - Git configuration and gh CLI
   - Tags: `git`, `configfile`
6. **hammerspoon** - Window management automation
   - Tags: `hammerspoon`, `configfile`
7. **iterm** - iTerm2 terminal configuration
   - Tags: `iterm`
8. **ssh** - SSH client configuration
   - Tags: `ssh`, `configfile`
9. **starship** - Shell prompt configuration
   - Tags: `starship`
10. **python** - Python tooling (pipx, uv, hatch)
    - Tags: `python`

**Variables required:**
- `admin_password` (from `inventory/group_vars/all/vault.yml` or `inventory/group_vars/localhost/vault.yml`)

**Common usage examples:**

```bash
# Full bootstrap (all roles)
ansible-playbook playbooks/local_bootstrap.yml -i inventory/inventory.yml --ask-become-pass -vv

# Only configure dotfiles (skip package installation)
ansible-playbook playbooks/local_bootstrap.yml -i inventory/inventory.yml --ask-become-pass -vv --tags configfile

# Only update macOS packages and settings
ansible-playbook playbooks/local_bootstrap.yml -i inventory/inventory.yml --ask-become-pass -vv --tags macos

# Only update git configuration
ansible-playbook playbooks/local_bootstrap.yml -i inventory/inventory.yml --ask-become-pass -vv --tags git

# Update shell configuration only
ansible-playbook playbooks/local_bootstrap.yml -i inventory/inventory.yml --ask-become-pass -vv --tags zsh
```

### nas_bootstrap.yml

Configures home NAS server running Debian with Docker media stack, ZFS storage, and network services.

**Host target:** `nas` (defined in `inventory/inventory.yml`)

**Role execution order:**

1. **APT update** - Updates package index (cached for 24 hours)
2. **debian** - Base system packages and configuration
   - Tags: `debian`, `configfile`
3. **zfs** - ZFS filesystem configuration
   - Tags: `zfs`, `configfile`
4. **samba** - File sharing via SMB/CIFS
   - Tags: `samba`, `configfile`
5. **docker** - Docker setup with complete media stack
   - Tags: `docker`, `configfile`, `homeassistant`
6. **glance** - Dashboard configuration
   - Tags: `glance`, `configfile`
7. **git** - Git configuration
   - Tags: `git`, `configfile`
8. **ssh** - SSH client configuration
   - Tags: `ssh`, `configfile`
9. **zsh** - Shell configuration
   - Tags: `zsh`, `configfile`

**Variables required:**
- `admin_password` (from `inventory/group_vars/all/vault.yml` or `inventory/host_vars/nas/vault.yml`)

**Common usage examples:**

```bash
# Full bootstrap (all roles)
ansible-playbook playbooks/nas_bootstrap.yml -i inventory/inventory.yml --ask-become-pass -vv

# Only update Docker stack
ansible-playbook playbooks/nas_bootstrap.yml -i inventory/inventory.yml --ask-become-pass -vv --tags docker

# Only update Samba configuration
ansible-playbook playbooks/nas_bootstrap.yml -i inventory/inventory.yml --ask-become-pass -vv --tags samba

# Only update dotfiles (skip services)
ansible-playbook playbooks/nas_bootstrap.yml -i inventory/inventory.yml --ask-become-pass -vv --tags configfile
```

## Execution Methods

### Method 1: Bootstrap Scripts (Recommended for Fresh Install)

Use the provided shell scripts for zero-to-configured system setup:

```bash
# macOS machine
chmod u+x local_bootstrap.sh
./local_bootstrap.sh

# NAS server
chmod u+x nas_bootstrap.sh
./nas_bootstrap.sh
```

**What the scripts do:**
1. Validate repository structure (checks for `run.py`, playbooks, etc.)
2. Install Homebrew with checksum verification (if not present)
3. Install Ansible via Homebrew (if not present)
4. Execute corresponding playbook with verbose output (`-vv`)
5. (macOS only) Kick off system software update

See [Bootstrap Scripts](#bootstrap-scripts) section for security details.

### Method 2: Direct Ansible Execution

When Ansible is already installed, run playbooks directly:

```bash
# Basic execution
ansible-playbook playbooks/local_bootstrap.yml \
  -i inventory/inventory.yml \
  --ask-become-pass \
  -vv

# With extra variables
ansible-playbook playbooks/local_bootstrap.yml \
  -i inventory/inventory.yml \
  --ask-become-pass \
  -e "some_var=value" \
  -vv

# Limit to specific hosts
ansible-playbook playbooks/nas_bootstrap.yml \
  -i inventory/inventory.yml \
  --limit nas \
  --ask-become-pass \
  -vv

# Check mode (dry run)
ansible-playbook playbooks/local_bootstrap.yml \
  -i inventory/inventory.yml \
  --check \
  -vv

# Verbose debug output
ansible-playbook playbooks/local_bootstrap.yml \
  -i inventory/inventory.yml \
  --ask-become-pass \
  -vvv
```

### Method 3: Selective Tag Execution

Target specific components without running full playbook:

```bash
# Update only shell configuration
ansible-playbook playbooks/local_bootstrap.yml \
  -i inventory/inventory.yml \
  --ask-become-pass \
  --tags zsh \
  -vv

# Update multiple components
ansible-playbook playbooks/local_bootstrap.yml \
  -i inventory/inventory.yml \
  --ask-become-pass \
  --tags git,ssh,configfile \
  -vv

# Skip specific tags
ansible-playbook playbooks/local_bootstrap.yml \
  -i inventory/inventory.yml \
  --ask-become-pass \
  --skip-tags macos \
  -vv
```

## Bootstrap Scripts

### Security Features

Both `local_bootstrap.sh` and `nas_bootstrap.sh` implement security best practices:

#### 1. Repository Validation

Before execution, scripts verify they're in the correct directory:

```bash
# Checks for required files/directories
if [[ ! -f "${DOTFILES_DIR}/run.py" ]] || \
   [[ ! -f "${DOTFILES_DIR}/local_bootstrap.sh" ]] || \
   [[ ! -d "${DOTFILES_DIR}/playbooks" ]]; then
    echo -e "${RED}ERROR: This doesn't appear to be the dotfiles directory!${NC}"
    exit 1
fi
```

**Why:** Prevents accidental execution in wrong directory, which could cause configuration corruption.

#### 2. Homebrew Checksum Verification

Downloads installer to temporary file and validates SHA-256 checksum before execution:

```bash
# Download to temp file
BREW_INSTALLER="/tmp/brew-install.sh"
curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh -o "$BREW_INSTALLER"

# Expected checksum (last updated: 2026-01-11)
EXPECTED_CHECKSUM="b2ffbf7e7f451c6db3b5d1976fc6a9c2faecf58ee5e1dbf6e498643c91f0d3bc"

# Verify before execution
ACTUAL_CHECKSUM=$(shasum -a 256 "$BREW_INSTALLER" | awk '{print $1}')
if [ "$ACTUAL_CHECKSUM" != "$EXPECTED_CHECKSUM" ]; then
    echo "WARNING: Homebrew installer checksum mismatch!"
    # ... detailed warning ...
    rm -f "$BREW_INSTALLER"
    exit 1
fi
```

**Why:** Protects against:
- Man-in-the-middle attacks
- DNS hijacking
- Compromised download sources

**When checksum changes:**
1. Verify new installer at https://github.com/Homebrew/install
2. Generate new checksum:
`curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh | shasum -a 256`
3. Update `EXPECTED_CHECKSUM` in both bootstrap scripts
4. Update "Last updated" comment

#### 3. Fail-Fast Behavior

```bash
set -e  # Exit immediately on any command failure
```

**Why:** Prevents cascading failures and ensures consistent state.

### Script Flow

**Both scripts follow this pattern:**

1. **Setup**
   - Define color codes for output
   - Enable fail-fast (`set -e`)
   - Determine script directory

2. **Validation**
   - Check for required files/directories
   - Exit with error if validation fails

3. **Dependency Installation**
   - Install Homebrew if missing (with checksum verification)
   - Add Homebrew to PATH
   - Install Ansible via Homebrew if missing

4. **Playbook Execution**
   - Run corresponding playbook with:
     - Inventory file: `inventory/inventory.yml`
     - Become password prompt: `--ask-become-pass`
     - Verbose output: `-vv`

5. **Post-Bootstrap** (macOS only)
   - Kick off macOS software update
   - Note: System may restart automatically

## Tag System

### Tag Categories

**Role-specific tags:**
Each role has its own tag matching the role name (e.g., `zsh`, `git`, `macos`).

**Functional tags:**
- `configfile` - All roles that create/link configuration files
- `macos` - All macOS-specific roles (app installation + settings)
- `dock` - Dock-related configuration (settings + layout)
- `debian` - Debian-specific roles
- `docker` - Docker and container services
- `homeassistant` - Home Assistant specific config
- `always` - Tasks that always run (e.g., setting become password)

### Tag Inheritance

Roles can have multiple tags for flexible targeting:

```yaml
- include_role:
    name: roles/zsh
    apply:
      tags: zsh
  tags:
    - zsh
    - configfile
```

This role runs when either `zsh` OR `configfile` tags are specified.

### Common Tag Patterns

```bash
# All configuration files only (no package installation)
--tags configfile

# All macOS roles (packages + settings + dock)
--tags macos

# Only Dock configuration (settings + layout)
--tags dock

# Multiple specific roles
--tags git,ssh,zsh

# Everything except macOS packages (useful when packages already installed)
--skip-tags macos
```

## Security Considerations

### Vault Password Management

**All secrets are encrypted using Ansible Vault:**

1. Create `vault_password.txt` in repository root (gitignored):
   ```bash
   echo "your-vault-password" > vault_password.txt
   chmod 600 vault_password.txt
   ```

2. Ansible automatically uses this file (configured in `ansible.cfg` or inventory)

3. Encrypted vault files in inventory:
   - `inventory/group_vars/all/vault.yml` - Shared secrets
   - `inventory/group_vars/localhost/vault.yml` - Mac-specific secrets
   - `inventory/host_vars/nas/vault.yml` - NAS-specific secrets

**Never commit:**
- `vault_password.txt`
- Decrypted vault contents
- Plain-text passwords or API keys

### Become Password Handling

Both playbooks set `ansible_become_pass` from vault at the start:

```yaml
- name: Set ansible_become_pass
  ansible.builtin.set_fact:
    ansible_become_pass: "{{ admin_password }}"
  no_log: true  # Prevents password from appearing in logs
  tags:
    - always
```

**Benefits:**
- Only one password prompt (via `--ask-become-pass`)
- Password available to all roles for privilege escalation
- Not logged to output (even with `-vvv`)

### SSH Key Requirements

For remote playbooks (like `nas_bootstrap.yml`):

1. Ensure SSH key access to target host:
   ```bash
   ssh-copy-id user@nas-hostname
   ```

2. Verify connection:
   ```bash
   ansible nas -i inventory/inventory.yml -m ping
   ```

3. If using custom SSH keys, configure in `inventory/inventory.yml`:
   ```yaml
   nas:
     ansible_host: 192.168.1.100
     ansible_user: admin
     ansible_ssh_private_key_file: ~/.ssh/nas_key
   ```

## Troubleshooting

### Inventory Not Found

**Symptom:**
```
ERROR! the playbook could not be found
```

**Solution:**
Update inventory submodule:
```bash
python3 run.py update-inventory
# Or manually:
git submodule update --init --recursive
```

### Vault Password Issues

**Symptom:**
```
ERROR! Attempting to decrypt but no vault secrets found
```

**Solution:**
1. Verify `vault_password.txt` exists in repository root
2. Ensure file contains correct password
3. Check file permissions: `chmod 600 vault_password.txt`
4. If using `--ask-vault-pass`, ensure you enter correct password

### Homebrew Checksum Mismatch

**Symptom:**
```
WARNING: Homebrew installer checksum mismatch!
```

**Solution:**
1. Verify if Homebrew installer was legitimately updated:
   - Check https://github.com/Homebrew/install for recent commits
2. Generate new checksum:
   ```bash
   curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh | shasum -a 256
   ```
3. Compare with checksum in bootstrap script
4. If legitimate update, update `EXPECTED_CHECKSUM` in bootstrap script
5. If suspicious, investigate before proceeding

### Role Failures

**Symptom:**
```
TASK [roles/some-role : Some task] *****************************************
fatal: [localhost]: FAILED! => {...}
```

**Solution:**
1. Check verbose output for specific error
2. Run specific role with extra verbosity:
   ```bash
   ansible-playbook playbooks/local_bootstrap.yml \
     -i inventory/inventory.yml \
     --ask-become-pass \
     --tags some-role \
     -vvv
   ```
3. Check role-specific README in `roles/some-role/README.md`
4. Verify required variables are set in inventory

### macOS Dock Configuration Not Applying

**Symptom:**
Dock settings changed by playbook revert after restart

**Solution:**
1. Kill Dock to force reload:
   ```bash
   killall Dock
   ```
2. Ensure `macos_dock` role ran successfully
3. Check for conflicting system profile settings (MDM/corporate managed machines)

### Docker Stack Issues (NAS)

**Symptom:**
Docker containers not starting or configuration not applied

**Solution:**
1. Check Docker service status:
   ```bash
   ssh nas "sudo systemctl status docker"
   ```
2. Verify compose file was deployed:
   ```bash
   ssh nas "cat /etc/docker/docker-compose.yml"
   ```
3. Check container logs:
   ```bash
   ssh nas "cd /etc/docker && sudo docker-compose logs [service-name]"
   ```
4. Restart Docker stack:
   ```bash
   ssh nas "cd /etc/docker && sudo docker-compose down && sudo docker-compose up -d"
   ```

### Permission Denied Errors

**Symptom:**
```
fatal: [localhost]: FAILED! => {"changed": false, "msg": "Permission denied"}
```

**Solution:**
1. Verify `--ask-become-pass` flag is used
2. Check become password is correct in vault
3. Ensure user has sudo privileges
4. Try with explicit become:
   ```bash
   ansible-playbook playbooks/local_bootstrap.yml \
     -i inventory/inventory.yml \
     --ask-become-pass \
     --become \
     -vv
   ```

## Best Practices

### Development Workflow

1. **Test with specific tags:**
   ```bash
   ansible-playbook playbooks/local_bootstrap.yml \
     -i inventory/inventory.yml \
     --ask-become-pass \
     --tags git \
     --check \
     -vv
   ```

2. **Use check mode for validation:**
   ```bash
   ansible-playbook playbooks/local_bootstrap.yml \
     -i inventory/inventory.yml \
     --check \
     -vv
   ```

3. **Run full bootstrap periodically:**
   - Weekly for active development machines
   - Monthly for stable production systems
   - After major OS updates

### Adding New Roles

1. Create role in `roles/` directory
2. Add to appropriate playbook:
   ```yaml
   - include_role:
       name: roles/new-role
       apply:
         tags: new-role
     tags:
       - new-role
       - configfile  # If it creates config files
   ```
3. Test with tag:
   ```bash
   ansible-playbook playbooks/local_bootstrap.yml \
     -i inventory/inventory.yml \
     --ask-become-pass \
     --tags new-role \
     -vv
   ```

### Version Control

1. Commit playbook changes separately from role changes
2. Use descriptive commit messages referencing affected roles
3. Tag major configuration updates:
   ```bash
   git tag -a v2.1.0 -m "Add Python development environment"
   ```

### Inventory Management

1. Keep inventory in separate private repository
2. Update via `python3 run.py update-inventory` before playbook runs
3. Never commit unencrypted secrets to any repository
4. Use separate vault files for different host groups

## Future Enhancements

Potential improvements:

- **Bootstrap command in run.py:** Wrapper to execute bootstrap scripts with proper validation
- **Role dependency visualization:** Generate graph of role dependencies
- **Pre-flight checks:** Validate system requirements before playbook execution
- **Rollback mechanism:** Create system snapshots before major changes
- **Diff mode improvements:** Better change tracking for configuration management
- **Modular playbook composition:** Include task files for more granular execution
