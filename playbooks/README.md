[Project Root](../README.md) > **Playbooks**

# Playbooks

Ansible playbooks for the home NAS. [`nas_bootstrap.yml`](nas_bootstrap.yml) is the only playbook; macOS configuration
moved to the stow engine (see [`bootstrap/`](../bootstrap/README.md)). The retired `local_bootstrap.yml` macOS playbook
is preserved in [`archive/ansible-macos/`](../archive/ansible-macos/README.md).

<!-- mdformat-toc start --slug=github --maxlevel=3 --minlevel=2 -->

- [Overview](#overview)
- [nas_bootstrap.yml](#nas_bootstrapyml)
- [Running](#running)
  - [`run.py nas-provision`](#runpy-nas-provision)
  - [Direct execution](#direct-execution)
  - [Tags](#tags)
- [Vault](#vault)
- [Troubleshooting](#troubleshooting)

<!-- mdformat-toc end -->

## Overview<a name="overview"></a>

| Playbook            | Target                   | Entry point                                          | Purpose                                                              |
| ------------------- | ------------------------ | ---------------------------------------------------- | -------------------------------------------------------------------- |
| `nas_bootstrap.yml` | Debian server (nas host) | `run.py nas-provision` (wrapper: `nas_bootstrap.sh`) | Home NAS with Docker media stack, file sharing, and network services |

The playbook:

- Requires the inventory from the separate `dotfiles-inventory` repository (cloned into `inventory/` by
  `run.py update-inventory`)
- Uses Ansible Vault for secrets
- Supports selective execution via tags
- Sets `ansible_become_pass` from the vault (`admin_password`) for privilege escalation

## nas_bootstrap.yml<a name="nas_bootstrapyml"></a>

**Host target:** `nas` (defined in `inventory/inventory.yml`)

**Execution order:**

0. **Set ansible_become_pass** - copies `admin_password` into `ansible_become_pass` so every later `become` task can use
   it (tagged `always`)
1. **APT update** - updates the package index (cached for 24 hours; tagged `always`, so tag-scoped runs refresh a stale
   cache too)
2. **debian** - system packages (including the stow engine's prerequisites), the Linuxbrew prefix, and the systemd sleep
   targets. Tags: `debian`
3. **zfs** - ZFS installation: the `contrib` apt component, kernel packages, `zfs-dkms`, and `zfsutils-linux`. Tags:
   `zfs`
4. **samba** - file sharing via SMB/CIFS. Tags: `samba`, `configfile`
5. **docker** - Docker Engine and compose plugin, docker-group membership, the `~/docker` skeleton and shared `.env`,
   the autoplex image build, and `deploy.sh`; the stack itself is the `services` step. Tags: `docker`, `configfile`
6. **tailscale** - Tailscale install and configuration, HTTPS certificates, and the Caddyfile Caddy reads. Tags:
   `tailscale`
7. **dotfiles** - hands `$HOME` to the stow engine (clone, `profiles/nas` overlay, login shell, `bootstrap.sh`). Tags:
   `dotfiles`
8. **haos** - Home Assistant OS VM via `vms/haos/setup.sh`. Tags: `haos`
9. **services** - Compose sync, per-service secrets, deploy. Tags: `services`, `secrets`

The tags listed are the ones on the role's include; [Tags](#tags) explains what each reaches.

**Variables required** (defined in the inventory clone; its layout is in
[`.ctx/ARCHITECTURE.md`](../.ctx/ARCHITECTURE.md)):

- `admin_password`: the become password the play sets first; it is also the default Samba password of `ansible_user`
- `tailscale_auth_key`: a reusable auth key; the `tailscale` role asserts it is non-empty before doing anything else
- `tailscale_tailnet_name`: the tailnet domain including `.ts.net` (for example `tail1234.ts.net`); read by the `docker`
  role's `.env` template (`ADVERTISE_IP`) and, when `tailscale_https_enabled` is true, by the `tailscale` role's HTTPS
  tasks
- `ansible_user` of the `nas` host: required by the roles (`debian`, `samba` defaults, and `dotfiles` read it with no
  default). `run.py` alone falls back to the local login
- `ansible_host` of the `nas` host: optional, since `run.py` falls back to the inventory name `nas`. When either
  connection variable is set it must be a literal, not a template: `run.py` refuses templated values in its SSH
  preflight
- `tailscale_ssh_enabled: false` in the NAS host variables, which CI deploys require (Tailscale SSH blocks the `tag:ci`
  deploy; see [`services/README.md`](../services/README.md#ci-deploys))
- Whatever an enabled service's `services/<svc>/env.j2` references. No enabled service has one today: PiHole's `env.j2`
  needs `pihole_web_password`, but PiHole is disabled (`compose.yml.disabled`), so its template is skipped, and
  re-enabling PiHole makes the variable required

**Play variable:** `dotfiles_repo_dir` (the NAS clone of this repository, `~/dotfiles-personal`) is defined on the play
and shared by the `dotfiles` and `haos` roles.

## Running<a name="running"></a>

### `run.py nas-provision`<a name="runpy-nas-provision"></a>

```bash
python3 run.py nas-provision                 # preflight, collections, then the playbook
python3 run.py nas-provision --check --diff  # preview (converged host)
python3 run.py nas-provision --tags services -v
```

The command checks that the inventory and `vault_password.txt` exist and that the `nas` host answers over SSH, installs
the collections from `roles/requirements.yml`, then runs `ansible-playbook playbooks/nas_bootstrap.yml` in the uv
environment. Options are documented in [`docs/RUN_PY_REFERENCE.md`](../docs/RUN_PY_REFERENCE.md#nas-provision). On a
fresh host the samba probe fails and the tailscale probe returns nothing, so the next task's `from_json` fails (see
[Tags](#tags)).

`nas_bootstrap.sh` validates the repository layout (`run.py`, `nas_bootstrap.sh`, `playbooks/`) and hands every argument
to `run.py nas-provision`. The Homebrew installer pin lives only in `bootstrap/50-brew.sh` (`BREW_INSTALLER_URL` and
`BREW_INSTALLER_SHA256`; see the [README](../README.md#homebrew-checksum-mismatch) for how to re-pin).

### Direct execution<a name="direct-execution"></a>

Run these from the repository root so `ansible.cfg` applies. Calling `ansible-playbook` directly skips what
`run.py nas-provision` adds: the preflight (inventory, vault password, SSH reachability) and the collection install. It
also needs the `ansible-playbook` of the project environment, so prefix it with `scripts/hooks/uv-public.sh run`.

```bash
# Full playbook
scripts/hooks/uv-public.sh run ansible-playbook playbooks/nas_bootstrap.yml -i inventory/inventory.yml -vv

# Dry run (converged host; see Tags for the fresh-host limit)
scripts/hooks/uv-public.sh run ansible-playbook playbooks/nas_bootstrap.yml -i inventory/inventory.yml --check -vv

# Syntax check
scripts/hooks/uv-public.sh run ansible-playbook --syntax-check -i localhost, playbooks/nas_bootstrap.yml
```

The syntax check only parses the playbook; it never executes a play. Ansible still loads the vault password file first.
The check exits 0 when `vault_password.txt` exists in the repository root or when `ANSIBLE_VAULT_PASSWORD_FILE` names
any existing file; otherwise it fails with `The vault password file ... was not found`.

### Tags<a name="tags"></a>

Each role's include carries the role's name as a tag. The `samba` and `docker` includes also carry `configfile`, and the
`services` include also carries `secrets`. A tag on an `include_role` task selects only the include itself. The tasks
inside the role run only if they carry a selected tag, and `apply` gives every one of them the role-name tag. A
role-name tag therefore runs the whole role, whereas `configfile` and `secrets` reach only the few tasks inside those
roles that carry them.

| Tag                                                                             | Runs                                                                                                                                                                                                                                                                               |
| ------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `debian`, `zfs`, `samba`, `docker`, `tailscale`, `dotfiles`, `haos`, `services` | The whole role                                                                                                                                                                                                                                                                     |
| `configfile`                                                                    | In `docker`: the `.env` render and the `deploy.sh` copy. In `samba`: the `smb.conf` task. Only those tasks run, plus the `always` ones and any handler they notify (a changed `smb.conf` still restarts Samba); the other roles, including `dotfiles` and `haos`, are not selected |
| `secrets`                                                                       | In `services`: the three secret tasks (find the `env.j2` templates, create the directories, render the files); not the sync or the deploy                                                                                                                                          |
| `always`                                                                        | Setting the become password and refreshing the apt index on every run, plus samba's `Register Samba version` whenever the `samba` include is selected (so with `configfile` or `samba`)                                                                                            |

```bash
python3 run.py nas-provision --tags docker          # the whole docker role
python3 run.py nas-provision --tags configfile      # docker .env and deploy.sh, samba smb.conf
python3 run.py nas-provision --tags dotfiles,haos   # the stow engine and the Home Assistant OS VM
python3 run.py nas-provision --tags secrets         # per-service secret files only
```

The two probes that need an installed tool, samba's `Register Samba version` (`smbd --version`) and the `tailscale`
role's `tailscale status --json`, are read-only and carry `check_mode: false`, like the other roles' probes, so they run
under `--check` too. On a fresh host, where `smbd` or `tailscale` is not installed yet, the samba probe fails
(`smbd --version` errors) and the tailscale probe returns nothing, so the next task's `from_json` fails; the real run
installs those tools first.

`--tags configfile` assumes `~/docker` exists, because the directory tasks do not carry the tag. On a host without it,
the run fails (at the `.env` render once samba is installed); run `--tags docker` first. See
[`roles/docker/README.md`](../roles/docker/README.md#tags-and-running).

## Vault<a name="vault"></a>

All secrets are `ansible-vault`-encrypted in the `inventory/` clone. Create `vault_password.txt` in the repository root
(gitignored; referenced by `ansible.cfg`). Never commit it or decrypted vault contents.

## Troubleshooting<a name="troubleshooting"></a>

| Symptom                                            | Fix                                                                                                                                              |
| -------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| Inventory not found                                | `python3 run.py update-inventory`                                                                                                                |
| `Attempting to decrypt but no vault secrets found` | Ensure `vault_password.txt` exists in the repository root with the correct password                                                              |
| Homebrew installer checksum mismatch               | Treat as a bad or tampered download and re-run; re-pin only to adopt a newer upstream commit ([README](../README.md#homebrew-checksum-mismatch)) |
| Role failure                                       | Re-run with `--tags <role> -vvv` and read `roles/<role>/README.md`                                                                               |
| Permission denied                                  | Confirm `admin_password` in the vault (the play sets `ansible_become_pass` from it)                                                              |

Problems with the container stack on the NAS are covered in [`services/README.md`](../services/README.md) and
[`roles/services/README.md`](../roles/services/README.md).
