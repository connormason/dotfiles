[Project Root](../../README.md) > [Roles](../README.md) > **dotfiles**

# dotfiles

Hands the NAS user's `$HOME` to the stow engine, the same one the Macs use: clones this repository, registers the
[`profiles/nas`](../../profiles/nas/README.md) overlay, sets the login shell, and runs
[`bootstrap/bootstrap.sh`](../../bootstrap/README.md) as the user. Root-level prerequisites (Homebrew build packages,
the Linuxbrew prefix) come from the [`debian`](../debian/README.md) role, which must run first.

## Tasks

| Step             | Effect                                                                                                                 |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------- |
| Safety check     | Fails, touching nothing, if the clone has uncommitted changes to tracked files or a `HEAD` that is on no remote branch |
| Clone / update   | `ansible.builtin.git` from `dotfiles_repo_url` at `dotfiles_repo_version`; `remote.origin.pushurl` set to the SSH URL  |
| Overlay registry | Writes `~/.config/dotfiles/overlays` from `dotfiles_overlays` (the role owns the file)                                 |
| Login shell      | `dotfiles_login_shell` for `ansible_user` (root)                                                                       |
| Engine           | `bootstrap.sh` with `BOOTSTRAP_NONINTERACTIVE=1`; changed unless its last line is `bootstrap: changes=0`               |

The engine's `95-dotfiles` stage moves pre-existing dotfiles that block a link into `~/.dotfiles-backup/<timestamp>/`.
With `BOOTSTRAP_NONINTERACTIVE=1`, `20-ssh-key` generates a key if needed and prints it for registration instead of
waiting for confirmation.

## Check mode and preview

Under `--check`, the engine runs with `--dry-run` (read-only) and the task reports whether a real run would change
anything; it is skipped when the clone does not exist yet. `-e dotfiles_bootstrap_preview=true` runs `--dry-run` in a
real play: the clone, registry, and login shell are applied, `$HOME` is only previewed.

## Variables

| Variable                     | Default                                       | Purpose                                         |
| ---------------------------- | --------------------------------------------- | ----------------------------------------------- |
| `dotfiles_repo_dir`          | play variable: `~/dotfiles-personal`          | Clone path (shared with the `haos` role)        |
| `dotfiles_repo_url`          | `https://github.com/connormason/dotfiles.git` | Fetch URL                                       |
| `dotfiles_repo_push_url`     | `git@github.com:connormason/dotfiles.git`     | Push URL                                        |
| `dotfiles_repo_version`      | `main`                                        | Branch to check out                             |
| `dotfiles_overlays`          | `[<dotfiles_repo_dir>/profiles/nas]`          | Overlays registry content                       |
| `dotfiles_login_shell`       | `/bin/zsh`                                    | Login shell                                     |
| `dotfiles_bootstrap_preview` | `false`                                       | Preview the engine (`--dry-run`) in a real play |
