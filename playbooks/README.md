[Project Root](../README.md) > **Playbooks**

# Playbooks

Ansible playbooks for the home NAS. [`nas_bootstrap.yml`](nas_bootstrap.yml) is the only playbook; macOS configuration
moved to the stow engine (see [`bootstrap/`](../bootstrap/README.md)). The retired `local_bootstrap.yml` macOS playbook
is preserved in [`archive/ansible-macos/`](../archive/ansible-macos/README.md).

## Overview

| Playbook            | Target                   | Bootstrap script   | Purpose                                                              |
| ------------------- | ------------------------ | ------------------ | -------------------------------------------------------------------- |
| `nas_bootstrap.yml` | Debian server (nas host) | `nas_bootstrap.sh` | Home NAS with Docker media stack, file sharing, and network services |

The playbook:

- Requires the inventory from the separate `dotfiles-inventory` repository (cloned into `inventory/` by
  `run.py update-inventory`)
- Uses Ansible Vault for secrets
- Supports selective execution via tags
- Sets `ansible_become_pass` from the vault (`admin_password`) for privilege escalation

## nas_bootstrap.yml

**Host target:** `nas` (defined in `inventory/inventory.yml`)

**Execution order:**

1. **APT update** - updates the package index (cached for 24 hours)
2. **debian** - base system packages and configuration. Tags: `debian`, `configfile`
3. **zfs** - ZFS filesystem configuration. Tags: `zfs`, `configfile`
4. **samba** - file sharing via SMB/CIFS. Tags: `samba`, `configfile`
5. **docker** - Docker setup with the media stack. Tags: `docker`, `configfile`, `homeassistant`
6. **git** - git configuration. Tags: `git`, `configfile`
7. **ssh** - SSH key generation. Tags: `ssh`, `configfile`
8. **tailscale** - Tailscale install, configuration, and HTTPS/Caddy. Tags: `tailscale`, `configfile`
9. **zsh** - shell configuration. Tags: `zsh`, `configfile`

**Variables required:** `admin_password` (from `inventory/group_vars/all/vault.yml` or
`inventory/host_vars/nas/vault.yml`).

## Running

### Bootstrap script

```bash
chmod u+x nas_bootstrap.sh
./nas_bootstrap.sh
```

The script validates the repository layout (`run.py`, `nas_bootstrap.sh`, `playbooks/`), installs Homebrew (installer
checksum-verified before execution) and Ansible if missing, then runs the playbook with `--ask-become-pass -vv`.

The Homebrew installer URL is pinned to an upstream commit. To update the pin, pick a commit SHA from the history of
`install.sh` at https://github.com/Homebrew/install, put it in the URL, regenerate the checksum of that exact URL
(`curl -fsSL https://raw.githubusercontent.com/Homebrew/install/<commit-sha>/install.sh | shasum -a 256`), and update
the URL, `EXPECTED_CHECKSUM` and its "Last updated" comment in `nas_bootstrap.sh` (and the matching values in
`bootstrap/50-brew.sh`).

### Direct execution

```bash
# Full playbook
ansible-playbook playbooks/nas_bootstrap.yml -i inventory/inventory.yml --ask-become-pass -vv

# Dry run
ansible-playbook playbooks/nas_bootstrap.yml -i inventory/inventory.yml --ask-become-pass --check -vv

# Syntax check
ansible-playbook --syntax-check -i localhost, playbooks/nas_bootstrap.yml
```

### Tags

Each role has a tag matching its name; `configfile` selects every role that writes configuration files.

```bash
ansible-playbook playbooks/nas_bootstrap.yml -i inventory/inventory.yml --ask-become-pass -vv --tags docker
ansible-playbook playbooks/nas_bootstrap.yml -i inventory/inventory.yml --ask-become-pass -vv --tags configfile
ansible-playbook playbooks/nas_bootstrap.yml -i inventory/inventory.yml --ask-become-pass -vv --tags git,ssh,zsh
```

| Tag             | Selects                                             |
| --------------- | --------------------------------------------------- |
| `configfile`    | Roles that create or link configuration files       |
| `docker`        | Docker and container services                       |
| `homeassistant` | Home Assistant configuration inside the docker role |
| `always`        | Tasks that always run (setting the become password) |

## Vault

All secrets are `ansible-vault`-encrypted in the `inventory/` clone. Create `vault_password.txt` in the repository root
(gitignored; referenced by `ansible.cfg`). Never commit it or decrypted vault contents.

## Troubleshooting

| Symptom                                            | Fix                                                                                  |
| -------------------------------------------------- | ------------------------------------------------------------------------------------ |
| Inventory not found                                | `python3 run.py update-inventory`                                                    |
| `Attempting to decrypt but no vault secrets found` | Ensure `vault_password.txt` exists in the repository root with the correct password  |
| Homebrew installer checksum mismatch               | Verify the installer upstream, then update `EXPECTED_CHECKSUM` in `nas_bootstrap.sh` |
| Role failure                                       | Re-run with `--tags <role> -vvv` and read `roles/<role>/README.md`                   |
| Permission denied                                  | Use `--ask-become-pass` and confirm `admin_password` in the vault                    |

Docker stack issues on the NAS are covered in [`roles/docker/README.md`](../roles/docker/README.md).
