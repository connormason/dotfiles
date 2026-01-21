# macos

Ansible role for managing macOS application and tool installation through a three-layer package management system:
Homebrew formulae (CLI tools), Homebrew casks (GUI applications), and Mac App Store apps.

## Overview

This role provides a declarative approach to managing macOS software installations. It handles:

- Installation of macOS command-line tools (Xcode CLI tools)
- Installation and management of Homebrew
- Installation of CLI tools via Homebrew formulae
- Installation of GUI applications via Homebrew casks
- Installation of Mac App Store applications via `mas` CLI

All package lists are centrally defined in `defaults/main.yml`, making it easy to version control your software
environment and quickly bootstrap new macOS systems.

## Package Management Layers

### Layer 1: Homebrew Formulae (`brew_packages`)

**Purpose**: Command-line tools and utilities

**When to use**:
- CLI tools and utilities (e.g., `git`, `jq`, `ripgrep`)
- Development tools without GUIs (e.g., `node`, `python`, `hatch`)
- System utilities (e.g., `direnv`, `autojump`)

**Example packages**:
```yaml
brew_packages:
  - bat                    # cat alternative with syntax highlighting
  - fzf                    # fuzzy finder
  - ripgrep                # fast grep alternative
  - lazygit                # terminal UI for git
```

**Special syntax**:
- Standard packages: `package-name`
- Tap packages: `username/tap-name/package-name` (e.g., `jesseduffield/lazydocker/lazydocker`)

### Layer 2: Homebrew Casks (`brew_cask_packages`)

**Purpose**: GUI applications distributed outside the Mac App Store

**When to use**:
- Desktop applications with graphical interfaces
- Developer tools (IDEs, editors)
- Third-party applications not available in the Mac App Store
- Applications requiring more frequent updates than App Store allows

**Example packages**:
```yaml
brew_cask_packages:
  - google-chrome          # Web browser
  - iterm2                 # Terminal emulator
  - pycharm-ce             # Python IDE
  - hammerspoon            # Window management automation
```

**Benefits**:
- No App Store sandboxing restrictions
- Often more up-to-date than App Store versions
- Can install beta/nightly builds
- No Apple ID required

### Layer 3: Mac App Store (`mas_apps`)

**Purpose**: Applications distributed through Apple's Mac App Store

**When to use**:
- Applications only available in the Mac App Store
- Applications requiring App Store entitlements
- Apple's own applications
- Apps where App Store version is preferred

**Example packages**:
```yaml
mas_apps:
  - name: Amphetamine      # Keep Mac awake utility
    id: 937984704
  - name: iStat Menus      # System monitoring
    id: 1319778037
```

**Requirements**:
- Must be signed into Mac App Store with Apple ID
- App ID can be found in the App Store URL (e.g., `https://apps.apple.com/app/id937984704`)

**Finding App IDs**:
```bash
# Search for an app
mas search "app name"

# List installed apps with IDs
mas list
```

## Package Lists

All package lists are defined in `roles/macos/defaults/main.yml`:

```yaml
---
brew_packages:
  - package1
  - package2

brew_cask_packages:
  - app1
  - app2

mas_apps:
  - name: App Name
    id: 123456789

mas_upgrade_all_apps: false
```

### Current Package Inventory

**CLI Tools** (29 packages):
- Version control: `git-delta`, `git-extras`, `git-lfs`, `gh`, `hub`, `lazygit`
- Development: `hatch`, `pipx`, `node`, `mermaid-cli`
- File utilities: `bat`, `ripgrep`, `tree`, `jq`
- Interactive TUIs: `fzf`, `fzf-make`, `lazydocker`, `lazyssh`, `btop`
- Editors: `micro`
- Shell utilities: `autojump`, `direnv`
- System tools: `shellcheck`, `nmap`, `mas`, `just`, `moor`

**GUI Applications** (8 packages):
- Browsers: `google-chrome`
- Development: `pycharm-ce`, `sublime-text`, `macdown`, `iterm2`
- Automation: `hammerspoon`
- Communication: `signal`
- Media: `spotify`

**Mac App Store** (3 apps):
- System monitoring: `iStat Menus`
- Utilities: `Amphetamine`
- VPN: `Tailscale`

## Adding Applications

### Adding Homebrew Formulae

1. Open `roles/macos/defaults/main.yml`
2. Add package name to `brew_packages` list (alphabetically recommended):

```yaml
brew_packages:
  - existing-package
  - new-package          # Add here
  - another-package
```

3. For packages from custom taps, use full path:

```yaml
brew_packages:
  - username/tap-name/package-name
```

4. Commit changes and run playbook:

```bash
ansible-playbook playbooks/local_bootstrap.yml -i inventory/inventory.yml --ask-become-pass --tags macos
```

### Adding Homebrew Casks

1. Search for the cask name:

```bash
brew search --cask "app name"
```

2. Add to `brew_cask_packages` in `roles/macos/defaults/main.yml`:

```yaml
brew_cask_packages:
  - existing-app
  - new-app              # Add here
```

3. Run playbook with `macos` tag

### Adding Mac App Store Apps

1. Find the app ID from the Mac App Store:
   - Visit app page in browser
   - Copy ID from URL: `https://apps.apple.com/app/id123456789`
   - Or use `mas search "app name"`

2. Add to `mas_apps` in `roles/macos/defaults/main.yml`:

```yaml
mas_apps:
  - name: Existing App
    id: 123456789
  - name: New App        # Add here
    id: 987654321
```

3. Ensure you're signed into Mac App Store

4. Run playbook with `macos` tag

## Removing Applications

### Removing from Package Lists

1. Remove package/app from appropriate list in `roles/macos/defaults/main.yml`
2. Run playbook to ensure system state matches desired state

**Important**: The role is **idempotent** but only adds packages. Removing from the list does not uninstall the
application. To fully remove:

```bash
# Uninstall Homebrew formula
brew uninstall package-name

# Uninstall Homebrew cask
brew uninstall --cask app-name

# Uninstall Mac App Store app
mas uninstall app-id
```

## Dependencies

### External Ansible Roles

Defined in `roles/requirements.yml`:

- **elliotweiser.osx-command-line-tools**: Installs Xcode command-line tools
- **geerlingguy.mac.homebrew**: Manages Homebrew installation and packages
- **geerlingguy.mac.mas**: Manages Mac App Store installations

### Installation

External roles are automatically installed during bootstrap, but can be manually installed:

```bash
ansible-galaxy install -r roles/requirements.yml
```

### System Requirements

- macOS (tested on recent versions)
- Admin/sudo access
- Internet connection for downloading packages
- Apple ID (for Mac App Store apps only)

## Configuration Variables

All variables defined in `roles/macos/defaults/main.yml`:

| Variable | Type | Description | Default |
|----------|------|-------------|---------|
| `brew_packages` | list[string] | Homebrew formulae to install | See defaults file |
| `brew_cask_packages` | list[string] | Homebrew casks to install | See defaults file |
| `mas_apps` | list[object] | Mac App Store apps to install | See defaults file |
| `mas_upgrade_all_apps` | boolean | Whether to upgrade all installed MAS apps | `false` |

### Variable Overrides

Variables can be overridden via:

1. **Inventory variables**: `inventory/group_vars/localhost/vars.yml`
2. **Command-line**: `--extra-vars` or `-e` flag
3. **Custom variables file**: `--extra-vars "@path/to/vars.yml"`

Example override:

```bash
ansible-playbook playbooks/local_bootstrap.yml \
  -i inventory/inventory.yml \
  --ask-become-pass \
  --tags macos \
  -e "mas_upgrade_all_apps=true"
```

## Tasks

The role executes three main tasks (from `roles/macos/tasks/main.yml`):

### 1. Install macOS Command-Line Tools

Delegates to `elliotweiser.osx-command-line-tools` role.

- Installs Xcode command-line tools if not present
- Required for Homebrew and many CLI tools
- Non-interactive installation

### 2. Install Homebrew and Packages

Delegates to `geerlingguy.mac.homebrew` role.

- Installs Homebrew if not present
- Installs all packages from `brew_packages` list
- Installs all applications from `brew_cask_packages` list
- Sets `homebrew_cask_accept_external_apps: true` to allow apps from outside App Store

**Note**: This task handles both formulae and casks in a single operation.

### 3. Install Mac App Store Apps

Delegates to `geerlingguy.mac.mas` role.

- Requires `mas` CLI (installed via `brew_packages`)
- Requires Apple ID sign-in to Mac App Store
- Installs all apps from `mas_apps` list
- Optionally upgrades all installed apps if `mas_upgrade_all_apps: true`

## Usage Examples

### Run Full macOS Setup

Install all packages from all three layers:

```bash
ansible-playbook playbooks/local_bootstrap.yml \
  -i inventory/inventory.yml \
  --ask-become-pass \
  --tags macos
```

### Bootstrap New Mac

Run complete bootstrap (includes this role):

```bash
chmod u+x local_bootstrap.sh && ./local_bootstrap.sh
```

### Install Only This Role

```bash
ansible-playbook playbooks/local_bootstrap.yml \
  -i inventory/inventory.yml \
  --ask-become-pass \
  --tags macos
```

### Dry Run (Check Mode)

Preview changes without applying:

```bash
ansible-playbook playbooks/local_bootstrap.yml \
  -i inventory/inventory.yml \
  --ask-become-pass \
  --tags macos \
  --check
```

### Verbose Output

Increase verbosity for debugging:

```bash
ansible-playbook playbooks/local_bootstrap.yml \
  -i inventory/inventory.yml \
  --ask-become-pass \
  --tags macos \
  -vv
```

### Run with Different Package Lists

Override defaults with custom variables:

```bash
ansible-playbook playbooks/local_bootstrap.yml \
  -i inventory/inventory.yml \
  --ask-become-pass \
  --tags macos \
  -e "@custom_packages.yml"
```

Example `custom_packages.yml`:
```yaml
---
brew_packages:
  - git
  - vim

brew_cask_packages:
  - visual-studio-code

mas_apps: []
```

## Troubleshooting

### Common Issues

#### Issue: "mas" not found when installing App Store apps

**Cause**: The `mas` CLI tool is installed via `brew_packages` but may not be in PATH yet during the same playbook run.

**Solution**: Run the playbook twice, or install `mas` manually first:
```bash
brew install mas
```

#### Issue: Mac App Store apps fail to install

**Cause**: Not signed into Mac App Store with Apple ID.

**Solution**:
1. Open Mac App Store
2. Sign in with your Apple ID
3. Re-run the playbook

#### Issue: Homebrew cask installation fails with "already installed"

**Cause**: Application was installed manually, conflicts with Homebrew-managed version.

**Solution**: Remove manual installation first:
```bash
brew uninstall --cask app-name --force
rm -rf /Applications/AppName.app
```
Then re-run playbook.

#### Issue: Command-line tools installation hangs

**Cause**: Interactive prompts waiting for user input.

**Solution**: Install manually first:
```bash
xcode-select --install
```

#### Issue: Homebrew permissions errors

**Cause**: Homebrew directories have incorrect ownership.

**Solution**: Fix Homebrew permissions:
```bash
sudo chown -R $(whoami) $(brew --prefix)/*
```

#### Issue: Package installation fails due to network timeout

**Cause**: Network issues or slow connection.

**Solution**: Retry the playbook, or install individual package manually:
```bash
brew install package-name
brew install --cask app-name
mas install app-id
```

### Debugging Tips

1. **Check Homebrew status**:
```bash
brew doctor
```

2. **List installed packages**:
```bash
brew list              # formulae
brew list --cask       # casks
mas list               # Mac App Store apps
```

3. **Check available updates**:
```bash
brew outdated
brew outdated --cask
mas outdated
```

4. **View Homebrew logs**:
```bash
brew install --verbose package-name
```

5. **Test playbook with increased verbosity**:
```bash
ansible-playbook playbooks/local_bootstrap.yml \
  -i inventory/inventory.yml \
  --ask-become-pass \
  --tags macos \
  -vvv
```

### Getting Help

- **Homebrew**: https://docs.brew.sh
- **mas CLI**: https://github.com/mas-cli/mas
- **Ansible**: https://docs.ansible.com

## Related Roles

- **roles/macos_settings**: Configure macOS system preferences
- **roles/macos_dock**: Configure Dock appearance and applications
- **roles/hammerspoon**: Configure window management automation
- **roles/iterm**: Configure iTerm2 terminal emulator
- **roles/python**: Configure Python tooling (pipx, uv, hatch)

## Maintenance

### Keeping Package Lists Updated

1. **Review installed packages**:
```bash
brew list | wc -l       # count formulae
brew list --cask | wc -l  # count casks
```

2. **Remove unused packages** from `defaults/main.yml`

3. **Update Homebrew itself**:
```bash
brew update
```

4. **Upgrade all packages** (outside Ansible):
```bash
brew upgrade
brew upgrade --cask
mas upgrade
```

### Version Pinning

Homebrew typically installs latest versions. To pin specific versions, modify package names:

```yaml
brew_packages:
  - python@3.11          # Pin to Python 3.11
  - node@18              # Pin to Node 18
```

## Contributing

When modifying this role:

1. Keep package lists alphabetically sorted for easy scanning
2. Add comments for non-obvious package choices
3. Test changes on a clean macOS system if possible
4. Update this README if adding new variables or functionality
5. Run pre-commit hooks before committing:
```bash
pre-commit run --all-files
```
