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

1. **APT update** - updates the package index (cached for 24 hours; tagged `always`, so tag-scoped runs refresh a stale
   cache too)
2. **debian** - base system packages and configuration. Tags: `debian`, `configfile`
3. **zfs** - ZFS filesystem configuration. Tags: `zfs`, `configfile`
4. **samba** - file sharing via SMB/CIFS. Tags: `samba`, `configfile`
5. **docker** - Docker setup with the media stack. Tags: `docker`, `configfile`, `homeassistant`
6. **tailscale** - Tailscale install, configuration, and HTTPS/Caddy. Tags: `tailscale`, `configfile`
7. **dotfiles** - hands `$HOME` to the stow engine (clone, `profiles/nas` overlay, login shell, `bootstrap.sh`). Tags:
   `dotfiles`, `configfile`
8. **haos** - Home Assistant OS VM via `vms/haos/setup.sh`. Tags: `haos`, `configfile`

**Variables required:** `admin_password` (from `inventory/group_vars/all/vault.yml` or
`inventory/host_vars/nas/vault.yml`).

**Play variable:** `dotfiles_repo_dir` (the NAS clone of this repository, `~/dotfiles-personal`) is defined on the play
and shared by the `dotfiles` and `haos` roles.

## Running

### Bootstrap script

```bash
chmod u+x nas_bootstrap.sh
./nas_bootstrap.sh
```

The script validates the repository layout (`run.py`, `nas_bootstrap.sh`, `playbooks/`), installs Homebrew (installer
checksum-verified before execution) and Ansible if missing, then runs the playbook with `-vv`.

The Homebrew installer URL is pinned to an upstream commit. To update the pin, pick a commit SHA from the history of
`install.sh` at https://github.com/Homebrew/install, put it in the URL, regenerate the checksum of that exact URL
(`curl -fsSL https://raw.githubusercontent.com/Homebrew/install/<commit-sha>/install.sh | shasum -a 256`), and update
the URL, `EXPECTED_CHECKSUM` and its "Last updated" comment in `nas_bootstrap.sh` (and the matching values in
`bootstrap/50-brew.sh`).

### Direct execution

```bash
# Full playbook
ansible-playbook playbooks/nas_bootstrap.yml -i inventory/inventory.yml -vv

# Dry run
ansible-playbook playbooks/nas_bootstrap.yml -i inventory/inventory.yml --check -vv

# Syntax check
ansible-playbook --syntax-check -i localhost, playbooks/nas_bootstrap.yml
```

### Tags

Each role has a tag matching its name; `configfile` selects every role that writes configuration files. Note that
`--tags configfile` therefore also runs the full stow engine (including `brew bundle`) via the `dotfiles` role and root
`setup.sh` via the `haos` role.

```bash
ansible-playbook playbooks/nas_bootstrap.yml -i inventory/inventory.yml -vv --tags docker
ansible-playbook playbooks/nas_bootstrap.yml -i inventory/inventory.yml -vv --tags configfile
ansible-playbook playbooks/nas_bootstrap.yml -i inventory/inventory.yml -vv --tags dotfiles,haos
```

| Tag             | Selects                                                                       |
| --------------- | ----------------------------------------------------------------------------- |
| `configfile`    | Roles that create or link configuration files                                 |
| `docker`        | Docker and container services                                                 |
| `homeassistant` | Home Assistant configuration inside the docker role                           |
| `always`        | Tasks that always run (setting the become password, refreshing the apt index) |

## Vault

All secrets are `ansible-vault`-encrypted in the `inventory/` clone. Create `vault_password.txt` in the repository root
(gitignored; referenced by `ansible.cfg`). Never commit it or decrypted vault contents.

## Troubleshooting

| Symptom                                            | Fix                                                                                                                                              |
| -------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| Inventory not found                                | `python3 run.py update-inventory`                                                                                                                |
| `Attempting to decrypt but no vault secrets found` | Ensure `vault_password.txt` exists in the repository root with the correct password                                                              |
| Homebrew installer checksum mismatch               | Treat as a bad or tampered download and re-run; re-pin only to adopt a newer upstream commit ([README](../README.md#homebrew-checksum-mismatch)) |
| Role failure                                       | Re-run with `--tags <role> -vvv` and read `roles/<role>/README.md`                                                                               |
| Permission denied                                  | Confirm `admin_password` in the vault (the play sets `ansible_become_pass` from it)                                                              |

Docker stack issues on the NAS are covered in [`roles/docker/README.md`](../roles/docker/README.md).
