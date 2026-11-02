[Project Root](../../README.md) > [Roles](../README.md) > **dotfiles**

# dotfiles

Hands the NAS user's `$HOME` to the stow engine, the same one the Macs use: clones this repository, registers the
[`profiles/nas`](../../profiles/nas/README.md) overlay, sets the login shell, and runs
[`bootstrap/bootstrap.sh`](../../bootstrap/README.md) as the user. Root-level prerequisites (Homebrew build packages,
the Linuxbrew prefix) come from the [`debian`](../debian/README.md) role, which must run first.

## Tasks

| Step             | Effect                                                                                                                                                                                                                            |
| ---------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Safety check     | Fails, touching nothing, if the clone has uncommitted changes to tracked files, a `HEAD` that is on no remote branch, or a local `dotfiles_repo_version` branch with commits `origin/<version>` lacks                             |
| Clone / update   | `ansible.builtin.git` from `dotfiles_repo_url` at `dotfiles_repo_version` (fails if that ref lacks `bootstrap/bootstrap.sh`); `remote.origin.pushurl` set to the SSH URL                                                          |
| Overlay registry | Writes `dotfiles_overlays_file` (`~/.config/dotfiles/overlays`) from `dotfiles_overlays` (the role owns the file); the engine is pointed at it with `DOTFILES_OVERLAYS_FILE`                                                      |
| Login shell      | `dotfiles_login_shell` for `ansible_user` (via become); fails first unless the shell exists, is executable, and is listed in `/etc/shells`                                                                                        |
| Engine           | `bootstrap.sh` with `BOOTSTRAP_NONINTERACTIVE=1`, run async (up to 2 hours, polled every 30 s) so a dropped SSH session cannot kill a long first run; changed unless its `bootstrap: changes=N` line (exactly one) is `changes=0` |

The engine's `95-dotfiles` stage moves pre-existing dotfiles that block a link into `~/.dotfiles-backup/<timestamp>/`.
With `BOOTSTRAP_NONINTERACTIVE=1`, `20-ssh-key` generates a key if needed and prints it for registration instead of
waiting for confirmation.

## Check mode and preview

Under `--check`, the engine runs with `--dry-run` (read-only) and the task reports whether a real run would change
anything; the preview is skipped when the clone does not exist yet (a real run fails if the clone lacks the engine).
`-e dotfiles_bootstrap_preview=true` runs `--dry-run` in a real play: the clone, registry, and login shell are applied,
`$HOME` is only previewed.

## Variables

| Variable                     | Default                                       | Purpose                                            |
| ---------------------------- | --------------------------------------------- | -------------------------------------------------- |
| `dotfiles_repo_dir`          | play variable: `~/dotfiles-personal`          | Clone path (shared with the `haos` role)           |
| `dotfiles_repo_url`          | `https://github.com/connormason/dotfiles.git` | Fetch URL                                          |
| `dotfiles_repo_push_url`     | `git@github.com:connormason/dotfiles.git`     | Push URL                                           |
| `dotfiles_repo_version`      | `main`                                        | Branch to check out                                |
| `dotfiles_overlays`          | `[<dotfiles_repo_dir>/profiles/nas]`          | Overlays registry content                          |
| `dotfiles_overlays_file`     | `~/.config/dotfiles/overlays`                 | Registry path the role writes and the engine reads |
| `dotfiles_login_shell`       | `/bin/zsh`                                    | Login shell                                        |
| `dotfiles_bootstrap_preview` | `false`                                       | Preview the engine (`--dry-run`) in a real play    |
