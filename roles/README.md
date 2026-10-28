[Project Root](../README.md) > **Roles**

# Ansible Roles

Ansible roles for the home NAS (Debian Linux), run by [`playbooks/nas_bootstrap.yml`](../playbooks/nas_bootstrap.yml).
macOS configuration is no longer handled by Ansible; it lives in the stow engine (see [`stow/`](../stow/README.md),
[`bootstrap/`](../bootstrap/README.md), and [`profiles/`](../profiles/README.md)).

## Roles

Roles are included in the order the playbook runs them; each is selectable with the Ansible tag of the same name.

| Role                               | Purpose                                                                                |
| ---------------------------------- | -------------------------------------------------------------------------------------- |
| [`debian`](debian/README.md)       | Setup tasks for Debian Linux                                                           |
| [`zfs`](zfs/README.md)             | Dependencies for the ZFS filesystem                                                    |
| [`samba`](samba/README.md)         | Samba file sharing                                                                     |
| [`docker`](docker/README.md)       | Docker-based media server and home-automation stack                                    |
| [`git`](git/README.md)             | Global git config (rendered from a template), git template hooks, global ignore file   |
| [`ssh`](ssh/README.md)             | SSH key pair generation                                                                |
| [`tailscale`](tailscale/README.md) | Tailscale install and configuration, plus HTTPS certificates and Caddy for the NAS     |
| [`zsh`](zsh/README.md)             | oh-my-zsh, Powerlevel10k, default shell, and `.zshrc` / `.zprofile` / `.p10k.zsh` copy |

## External dependencies

[`requirements.yml`](requirements.yml) lists the collections to install with `ansible-galaxy`:

```bash
ansible-galaxy install -r roles/requirements.yml
```

## Running roles

```bash
# Whole NAS playbook
./nas_bootstrap.sh

# A single role (or several) by tag
ansible-playbook playbooks/nas_bootstrap.yml -i inventory/inventory.yml --ask-become-pass -vv --tags git
ansible-playbook playbooks/nas_bootstrap.yml -i inventory/inventory.yml --ask-become-pass -vv --tags zsh,git,ssh

# Every role tagged configfile
ansible-playbook playbooks/nas_bootstrap.yml -i inventory/inventory.yml --ask-become-pass -vv --tags configfile
```

## Adding a role

1. Create `roles/<name>/` with the standard layout (`tasks/main.yml`, plus `defaults/`, `files/`, `templates/`,
   `handlers/` as needed) and a `README.md`.

2. Include it in `playbooks/nas_bootstrap.yml` with `include_role` and matching `tags`:

   ```yaml
     - include_role:
         name: roles/<name>
         apply:
           tags: <name>
       tags:
         - <name>
         - configfile
   ```

3. Add any new collection to `requirements.yml`.

4. Add a row to the table above.

Use fully-qualified module names, a `defaults/` variable for file modes, and `become` only on tasks that need it.

## Variables

Role variables come from role `defaults/` and from the vault-encrypted inventory clone in `inventory/` (`group_vars/`
and `host_vars/`). Common ones: `dotfiles_home` (repository root on the target), `ansible_user`, and `admin_password`.

## Validation

`prek run --all-files` runs yamllint over role files; `ansible-lint` (configured in
[`.ansible-lint.yaml`](../.ansible-lint.yaml)) is available but not enabled as a hook.

## Related documentation

- [`playbooks/`](../playbooks/README.md) - the NAS playbook and its bootstrap script
- [`.ctx/ARCHITECTURE.md`](../.ctx/ARCHITECTURE.md) - inventory layout (a separate repository cloned by
  `run.py update-inventory`)
