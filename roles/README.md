[Project Root](../README.md) > **Roles**

# Ansible Roles

Ansible roles for the home NAS (Debian Linux), run by [`playbooks/nas_bootstrap.yml`](../playbooks/nas_bootstrap.yml).
macOS configuration is no longer handled by Ansible; it lives in the stow engine (see [`stow/`](../stow/README.md),
[`bootstrap/`](../bootstrap/README.md), and [`profiles/`](../profiles/README.md)). The retired macOS roles are preserved
as a frozen snapshot in [`archive/ansible-macos/`](../archive/ansible-macos/README.md).

## Roles

Roles are included in the order the playbook runs them; each is selectable with the Ansible tag of the same name.

| Role                               | Purpose                                                                                                                                                                      |
| ---------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`debian`](debian/README.md)       | Base Debian configuration: system packages (including the stow engine's prerequisites), the Linuxbrew prefix, the systemd sleep targets, and alerting (smartd, `nas-notify`) |
| [`zfs`](zfs/README.md)             | ZFS installation (`contrib` component, kernel packages, `zfs-dkms`, `zfsutils-linux`) plus pool properties, ZED alert routing, and sanoid snapshots                          |
| [`samba`](samba/README.md)         | Samba file sharing                                                                                                                                                           |
| [`docker`](docker/README.md)       | Docker Engine, `~/docker` skeleton, autoplex image, `deploy.sh`                                                                                                              |
| [`tailscale`](tailscale/README.md) | Tailscale install and configuration, HTTPS certificates, and the Caddyfile Caddy reads                                                                                       |
| [`dotfiles`](dotfiles/README.md)   | `$HOME` via the stow engine: clone, `profiles/nas` overlay, login shell, `bootstrap.sh`                                                                                      |
| [`haos`](haos/README.md)           | Home Assistant OS VM via `vms/haos/setup.sh` (never `bridge.sh`)                                                                                                             |
| [`services`](services/README.md)   | Syncs `services/` to the NAS, renders per-service secrets, deploys the stack                                                                                                 |

## External dependencies

[`requirements.yml`](requirements.yml) lists collections only. Install them with `ansible-galaxy`:

```bash
scripts/hooks/uv-public.sh run ansible-galaxy collection install -r roles/requirements.yml
```

`run.py nas-provision` runs the same command through `scripts/hooks/uv-public.sh` before every playbook run.

## Running roles

```bash
# Whole NAS playbook (preflight, collections, then ansible-playbook)
python3 run.py nas-provision

# A single role (or several) by tag
python3 run.py nas-provision --tags dotfiles
python3 run.py nas-provision --tags dotfiles,haos
```

A role-name tag runs the whole role. The `configfile` and `secrets` tags run only the tasks that carry them; see
[Tags](../playbooks/README.md#tags) for what each tag selects.

## Adding a role

1. Create `roles/<name>/` with the standard layout (`tasks/main.yml`, plus `defaults/`, `files/`, `templates/`,
   `handlers/` as needed) and a `README.md`.

2. Include it in `playbooks/nas_bootstrap.yml` with `include_role`, the role-name tag in `apply`, and the same tag on
   the include:

   ```yaml
     - name: <what the role does>
       ansible.builtin.include_role:
         name: roles/<name>
         apply:
           tags: <name>
       tags:
         - <name>
   ```

   A tag on an `include_role` selects only the include itself; the `apply` tag is what reaches the role's tasks. Add
   another tag (such as `configfile`) to the include only if a task inside the role carries that tag.
   `tests/unit/test_nas_playbook.py::TestPlaybookTags` fails on an include tag that reaches no task.

3. Add any new collection to `requirements.yml`.

4. Update `EXPECTED_ORDER` in `tests/unit/test_nas_playbook.py`.

5. Add a row to the table above, a step to the execution-order list in [`playbooks/README.md`](../playbooks/README.md),
   and a bullet to the "Role System (NAS)" list in [`.ctx/ARCHITECTURE.md`](../.ctx/ARCHITECTURE.md), all in playbook
   order. `tests/unit/test_docs_consistency.py` checks all three against the playbook. Two more places list the roles
   without a test: the `roles/` entries in the Project Structure tree of the root [`README.md`](../README.md), and the
   role-tag comment under "Running Ansible Playbooks (NAS)" in [`.ctx/BUILD.md`](../.ctx/BUILD.md). Update them too.

Use fully-qualified module names and `become` only on tasks that need it.

## Variables

Role variables come from each role's `defaults/` (overridable) and `vars/` (fixed values, such as
`roles/samba/vars/main.yml`), and from the inventory clone in `inventory/` (`group_vars/` and `host_vars/`, which hold
plain files such as `host_vars/nas/vars.yml` as well as vault-encrypted ones). Common ones: `dotfiles_repo_dir` (the NAS
clone, a play variable), `ansible_user`, and `admin_password`.

## Validation

`prek run --all-files` runs yamllint over role files and ansible-lint over `playbooks/` and `roles/` through
[`scripts/hooks/ansible-lint.sh`](../scripts/hooks/ansible-lint.sh) (check only; accepted findings are listed with
reasons in [`.ansible-lint-ignore`](../.ansible-lint-ignore)). CI runs the same wrapper.

## Related documentation

- [`playbooks/`](../playbooks/README.md) - the NAS playbook and its bootstrap script
- [`.ctx/ARCHITECTURE.md`](../.ctx/ARCHITECTURE.md) - inventory layout (a separate repository cloned by
  `run.py update-inventory`)
