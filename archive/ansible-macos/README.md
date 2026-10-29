[Project Root](../../README.md) > [Archive](../README.md) > **Ansible macOS**

# Ansible macOS (archived)

Frozen snapshot of the Ansible-based macOS configuration that this repository used before it moved to the stow engine
and `bootstrap/` stage scripts. Kept as reference material for a possible future Ansible bootstrap of another Mac.

## Status

- **Frozen and unmaintained.** Nothing here is linted, tested, or run by CI; pre-commit hooks, ruff, mypy, interrogate,
  yamllint, and codespell are configured to skip `archive/`. In CI, the gitleaks scan and the repo leak guard (a
  `git ls-files` scan) still cover it; the local prek hooks skip `archive/`.
- **Snapshot of commit `1ef973a`**, the last commit before the retirement on branch `dev-env-base` (PR #18). Commit SHAs
  may not survive a squash merge, so the files in this directory are the record, not the SHA.
- **The active macOS setup is the stow engine:** see [`bootstrap/README.md`](../../bootstrap/README.md) for the stage
  driver and [`stow/README.md`](../../stow/README.md) for the packages. Design and rationale of the retirement:
  [`docs/plans/2026-10/2026-10-27-dev-env-port-plan.md`](../../docs/plans/2026-10/2026-10-27-dev-env-port-plan.md)
  (Task 11).
- The NAS keeps using Ansible. Its roles and playbook live at [`roles/`](../../roles/README.md) and
  [`playbooks/`](../../playbooks/README.md) in the repository root and are not part of this archive. The `git`, `ssh`,
  `zsh`, and `tailscale` roles below are the **pre-retirement** copies, which still carry the macOS branches that were
  later stripped from the active NAS roles.

## What it contains

The layout mirrors the repository root as it was at `1ef973a`. Every file is byte-identical to that commit except the
one listed under [Sanitization](#sanitization); this README is the only file added.

| Path                                                             | Purpose (from the file itself)                                                                           |
| ---------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| [`ansible.cfg`](ansible.cfg)                                     | Ansible defaults: relative `library`, `module_utils`, `roles_path`; `vault_password_file=vault_password.txt` |
| [`local_bootstrap.sh`](local_bootstrap.sh)                       | Installs Homebrew (checksum-verified) and Ansible, runs the playbook, then `softwareupdate`              |
| [`playbooks/local_bootstrap.yml`](playbooks/local_bootstrap.yml) | "Personal Mac bootstrap" play on `hosts: localhost`; includes the roles below, each behind its own tag  |
| [`library/osx_pmset.py`](library/osx_pmset.py)                   | Module managing `pmset` power settings; used by `macos_settings/tasks/power.yml`                         |
| [`library/configure_network_interfaces.py`](library/configure_network_interfaces.py) | Module wrapping `networksetup` (see its [`.md`](library/configure_network_interfaces.md)); referenced by no archived role or playbook |
| [`roles/requirements.yml`](roles/requirements.yml)               | External role and collections (see [Known staleness](#known-staleness))                                  |
| [`roles/README.md`](roles/README.md)                             | The roles guide as it stood before retirement (covers the NAS roles too)                                 |

Roles, in the order `local_bootstrap.yml` runs them (tags in parentheses):

| Role                                        | What it does                                                                                                          | Where the concern lives now                                                                                                                                       |
| ------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`zsh`](roles/zsh) (`zsh`, `configfile`)    | Installs oh-my-zsh and powerlevel10k, sets the login shell, links (localhost) or copies (remote) zshrc/zprofile/p10k  | [`stow/shell`](../../stow/README.md) and the `95-dotfiles` stage (oh-my-zsh)                                                                                      |
| [`macos`](roles/macos) (`macos`)            | Command Line Tools, Homebrew formulae and casks, Mac App Store apps via `mas`                                         | `50-brew` with [`bootstrap/Brewfile`](../../bootstrap/Brewfile) and the [`personal-mac`](../../profiles/personal-mac/README.md) overlay Brewfile                  |
| [`macos_settings`](roles/macos_settings) (`macos`, `dock`) | `defaults write` style preferences: Activity Monitor, App Store, Dock, Finder, I/O, Messages, power, misc | `60-macos` stage (preferences and Dock/Finder restart); per-setting coverage was not compared. The `osx_pmset` call in `power.yml` has no counterpart in `bootstrap/` |
| [`macos_dock`](roles/macos_dock) (`macos`, `dock`) | Installs `dockutil` and rebuilds the Dock tiles from a list in `defaults/main.yml`                             | No counterpart found: `dockutil` appears nowhere in `bootstrap/` or `stow/`                                                                                       |
| [`git`](roles/git) (`git`, `configfile`)    | git template dir with a pre-commit hook, `~/.gitconfig` from a template, global ignore, `gh` config                   | [`stow/git`](../../stow/README.md)                                                                                                                                |
| [`hammerspoon`](roles/hammerspoon) (`hammerspoon`, `configfile`) | Symlinks `init.lua` into `~/.hammerspoon`                                                        | [`stow/hammerspoon`](../../stow/README.md)                                                                                                                        |
| [`iterm`](roles/iterm) (`iterm`)            | Points iTerm2 at a preferences folder inside the checkout; disables the quit prompt                                   | [`stow/iterm2`](../../stow/README.md) and the `96-iterm2` stage                                                                                                   |
| [`ssh`](roles/ssh) (`ssh`, `configfile`)    | Remote hosts: generates an ed25519 key. localhost: writes an `AddKeysToAgent` stanza if `~/.ssh/config` is absent     | [`stow/ssh`](../../stow/README.md) and the `20-ssh-key` stage                                                                                                     |
| [`starship`](roles/starship) (`starship`)   | Downloads a pinned Starship release archive; links `starship.toml`                                                    | [`stow/starship`](../../stow/README.md)                                                                                                                           |
| [`python`](roles/python) (`python`)         | pip packages (`/usr/bin/pip3`) and pipx packages (Homebrew `pipx`)                                                    | `90-python` stage with [`bootstrap/uv-tools.txt`](../../bootstrap/uv-tools.txt) and [`stow/python`](../../stow/README.md)                                          |
| [`tailscale`](roles/tailscale) (`tailscale`) | Debian apt install or macOS brew cask, `tailscale set`/`login` with an auth key; optional HTTPS certs and Caddy (NAS) | The app only: the `personal-mac` overlay Brewfile installs it with `mas`. Auth-key login and the NAS HTTPS pieces have no counterpart in the stow engine          |
| [`link_dotfile`](roles/link_dotfile) (not in the playbook) | Utility role included by `git`, `starship`: asserts `link_dotfile_src`/`link_dotfile_dst`, backs up a non-symlink destination, creates the symlink | [`stow.sh`](../../stow/README.md#apply)                                                                                  |

## How the tree was designed to run

Derived from `ansible.cfg`, `local_bootstrap.sh`, and `playbooks/local_bootstrap.yml`; none of it was re-run for this
archive.

1. **Working directory.** `ansible.cfg` uses relative paths (`./library`, `./module_utils`, `./roles`,
   `vault_password.txt`), so Ansible must start in the directory that holds it, here `archive/ansible-macos/`.
   `module_utils` does not exist in the snapshot.
1. **Inventory.** The script passes `-i inventory/inventory.yml`. The inventory is not in this repository: it is the
   private `dotfiles-inventory` repository cloned to `inventory/` at the repository root (see
   [`CLAUDE.md`](../../CLAUDE.md) "Inventory"), and `vault_password.txt` is a gitignored file created by hand.
1. **`local_bootstrap.sh`**, in order:
   1. Exits unless `run.py`, `local_bootstrap.sh`, and `playbooks/` exist next to the script.
   1. If `brew` is missing, downloads the Homebrew installer to `/tmp`, compares its SHA-256 to a pinned value (last
      updated 2026-01-11 per the script comment), and runs it.
   1. Prepends `/opt/homebrew/bin` to `PATH` and runs `brew install ansible` if `ansible-playbook` is missing.
   1. Runs `ansible-playbook playbooks/local_bootstrap.yml -i inventory/inventory.yml --ask-become-pass -vv`.
   1. Runs `softwareupdate --all --install --force`.
1. **The play.** `hosts: localhost`; the first task (tag `always`) sets `ansible_become_pass` from `admin_password`
   (`no_log`), then each role is included with `include_role` and tagged as listed above.
1. **Variables expected from the inventory or vault.** Read from the code:

   | Variable                      | Used by                                                  | Evidence                                                         |
   | ----------------------------- | -------------------------------------------------------- | ---------------------------------------------------------------- |
   | `admin_password`              | `playbooks/local_bootstrap.yml`                          | First task                                                       |
   | `dotfiles_home`               | `git`, `hammerspoon`, `iterm`, `starship`, `zsh` tasks   | Paths of the form `{{ dotfiles_home }}/roles/<role>/files/...`   |
   | `ansible_user`                | `zsh`                                                    | `become_user` and the `user` module                              |
   | `tailscale_auth_key`          | `tailscale`                                              | Defaults to `""`; `main.yml` asserts it is non-empty             |

   `roles/README.md` ("Common Variables") says these are defined in `inventory/inventory.yml` and
   `inventory/group_vars/`; `roles/tailscale/README.md` names `inventory/group_vars/all/vault.yml` for the auth key.
   The inventory contents themselves are not available here.

## Notes for reviving as a remote-Mac bootstrap

Observations from reading the code, not tested guidance.

- The play targets `hosts: localhost` and sets no `connection:`; whether that is a local or an SSH connection is decided
  by the (unavailable) inventory.
- Only `zsh` and `ssh` branch on `inventory_hostname == 'localhost'` (copy files vs. symlink; key generation vs. agent
  stanza). `git`, `hammerspoon`, `iterm`, `starship`, and `link_dotfile` assume the dotfiles checkout exists on the
  managed host: they symlink from, template from, or point iTerm at `{{ dotfiles_home }}/roles/...`, and `link_dotfile`
  fails if its source path is missing on the target. In this archive the files sit under `archive/ansible-macos/roles/`,
  so `dotfiles_home` would have to resolve to `archive/ansible-macos/`.
- `local_bootstrap.sh` requires `run.py` beside it. `run.py` is not in this archive, so the script exits at its
  validation step as shipped.
- Privilege: the play relies on `--ask-become-pass` (interactive) plus `admin_password`. `become: true` appears in
  `macos_settings` (`power.yml`, `other.yml`, `finder.yml`) and `zsh` (permissions, login shell, and the non-macOS
  package install); `tailscale` escalates only on its Debian and NAS paths.
- Homebrew prefix: the script hardcodes `/opt/homebrew/bin`; the `python` role derives its prefix from
  `ansible_facts['machine']` (`/opt/homebrew` on `arm64`, otherwise `/usr/local`).
- `macos_dock` pauses 7 seconds twice and restarts the Dock via `launchctl kickstart gui/<uid>/com.apple.Dock.agent`. It
  notifies a `Clear homebrew cache` handler that is not defined in the role.
- The `starship` role downloads a `...-unknown-linux-musl.tar.gz` archive and sets group `wheel`; the URL is a Linux
  build.
- The `ssh` remote branch uses `community.crypto.openssh_keypair`, which is not listed in `roles/requirements.yml`.
- The `git` role's `gh` task links from `roles/tools/files/gh/`, a path that does not exist in the snapshot (the files
  are in `roles/git/files/gh/`).
- `macos_settings`, `macos_dock`, and `python` declare the `macos` role as a dependency in `meta/main.yml`. Whether
  Ansible re-runs the `macos` tasks for each dependent was not tested.

## Known staleness

- Every role that links a dotfile does so from `roles/*/files` (or `templates`) shipped in this snapshot, via
  `link_dotfile` or direct symlinks. Those dotfiles have since been reworked in [`stow/`](../../stow/README.md) and
  were not kept in sync here.
- Pinned values date from the snapshot: Starship `1.24.2`, the Homebrew installer checksum, and the cask and App Store
  lists in `roles/macos/defaults/main.yml`.
- External requirements, verbatim from `roles/requirements.yml`: role `elliotweiser.osx-command-line-tools`;
  collections `ansible.posix`, `community.general`, and `geerlingguy.mac`.
- Not carried over from the repository root: `.ansible-lint.yaml`, `.yamllint.yaml`, and `playbooks/README.md`
  (it documented the NAS playbook as well).

## Sanitization

Public repository: exactly one file was edited relative to `1ef973a`, and nothing else was changed.

- `library/configure_network_interfaces.py`, line 167 (the `author` entry of the module documentation): a GitHub
  username was replaced with the placeholder `<github-username>`.

`library/configure_network_interfaces.md` was checked and needed no change. Byte-identity of the remaining files can be
verified with `git show 1ef973a:<path>` for any path relative to this directory.

## Clarifications needed

- What `inventory/inventory.yml` and `inventory/group_vars/` defined for `dotfiles_home`, `ansible_user`, and
  `admin_password`, and whether `localhost` was a local or an SSH connection. The inventory is private and absent.
- Whether the preferences in `macos_settings` were all ported to `bootstrap/60-macos.sh`; only the existence of the
  mechanism is confirmed here.
- Why `roles/git/tasks/main.yml` points at `roles/tools/files/gh/`; whether the task ever ran successfully from this
  layout is not provable from the files.
