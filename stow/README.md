[Project Root](../README.md) > **Stow Packages**

# Stow Packages

Dotfiles linked into `$HOME` with [GNU Stow](https://www.gnu.org/software/stow/) by [`stow.sh`](../stow.sh). Each
subdirectory is one package whose internal layout mirrors `$HOME`; overlays under [`profiles/`](../profiles/README.md)
contribute further packages from their own `stow/` directories.

Packages for tools with shell integration carry their own `.config/zsh/conf.d/NN-<tool>.zsh` snippet alongside their
config. Stow merges all such snippets into a single `~/.config/zsh/conf.d/`, and `stow/shell/.zshrc` sources them in
sorted order.

## Packages

Every directory under `stow/` has one row, and every row names a directory; `tests/unit/test_docs_consistency.py`
enforces both directions, and also that the conf.d column matches the `.config/zsh/conf.d/*.zsh` files on disk.

| Package        | What it configures                                                                                                             | conf.d snippets                                                                                                             |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------- |
| `claude`       | `~/.claude`: `CLAUDE.md`, rules, hooks, scripts, agents, commands, skills, and plugin config                                   | `32-claude.zsh`                                                                                                             |
| `fzf`          | fzf shell integration (snippet only)                                                                                           | `36-fzf.zsh`                                                                                                                |
| `git`          | `~/.gitconfig`, global ignore, personal identity, `gh` config, worktrunk config, git-template pre-commit hook                  | `40-git.zsh`                                                                                                                |
| `hammerspoon`  | `~/.hammerspoon/init.lua` and the ReloadConfiguration, SpoonInstall, and WifiNotifier Spoons (macOS only)                      | —                                                                                                                           |
| `hatch-darwin` | hatch global config at its macOS path (macOS only)                                                                             | —                                                                                                                           |
| `hatch-linux`  | hatch global config at its Linux path, a symlink to the `hatch-darwin` file (Linux only)                                       | —                                                                                                                           |
| `homebrew`     | Homebrew environment in zsh (snippet only)                                                                                     | `05-homebrew.zsh`                                                                                                           |
| `iterm2`       | iTerm2 preferences plist in `~/.config/iterm2` (macOS only)                                                                    | `30-iterm2.zsh`                                                                                                             |
| `node`         | bun install location and `PATH` entry (snippet only)                                                                           | `44-node.zsh`                                                                                                               |
| `os_tools`     | btop, eza, fastfetch, htop, ranger, and sshm configuration                                                                     | `49-os_tools.zsh`, `90-banner.zsh`                                                                                          |
| `python`       | IPython startup script and Python shell aliases                                                                                | `42-python.zsh`                                                                                                             |
| `shell`        | bash, zsh, and fish startup files; the core zsh fragments (lib, path, oh-my-zsh, completion, misc tools, aliases, directories) | `00-lib.zsh`, `00-path.zsh`, `10-omz.zsh`, `20-completion.zsh`, `35-tools-misc.zsh`, `40-aliases.zsh`, `50-directories.zsh` |
| `shell-linux`  | zsh environment for Linux (skips the distro's global compinit) (Linux only)                                                    | —                                                                                                                           |
| `ssh`          | `~/.ssh/config` and `~/.ssh/config.d/personal`                                                                                 | `60-ssh-aliases.zsh`                                                                                                        |
| `starship`     | `~/.config/starship.toml`                                                                                                      | `80-starship.zsh`                                                                                                           |
| `tmux`         | `~/.config/tmux/tmux.conf` and `tmux.conf.local`                                                                               | `46-tmux.zsh`                                                                                                               |
| `vscode`       | VS Code `keybindings.json` and the snippets directory (macOS only)                                                             | —                                                                                                                           |
| `zed`          | `~/.config/zed/settings.json`                                                                                                  | —                                                                                                                           |
| `zoxide`       | zoxide shell integration (snippet only)                                                                                        | `38-zoxide.zsh`                                                                                                             |

Settings files that apps rewrite at runtime (`~/.claude/settings.json`, VS Code `settings.json`) are not stowed; they
are rendered from [`render/`](../render/) fragments by [`scripts/dotfiles/render.py`](../scripts/dotfiles/README.md),
and `stow.sh` refuses any package that provides a render target.

## OS-specific packages

A package that applies only to some operating systems carries a `.dotfiles-os` file at its root listing the OS ids it
applies to (`darwin`, `linux`), one per line; `#` starts a comment. `stow.sh` skips packages whose marker excludes the
current OS (`bootstrap/lib.sh` `dotfiles_os`, overridable with `DOTFILES_OS`): they are not linked, not listed by
`--list`, and not part of the ownership check, so a `<tool>-darwin` and a `<tool>-linux` package may provide the same
path. Package names stay unique across every layer regardless of markers. Packages without a marker apply everywhere.

## Git identity

[`git/.gitconfig`](git/.gitconfig) sets the personal identity as the default, then includes `~/.gitconfig.overlay`
(which a work overlay may use to replace that default). Four `includeIf "hasconfig:remote.*.url:..."` blocks follow
last, so they win: when any remote URL of a repository matches one of the globs below, the repository uses the personal
identity from `~/.config/git/identity-personal`.

- `git@github.com:connormason/**`
- `https://github.com/connormason/**`
- `ssh://git@github.com/connormason/**`
- `https://*@github.com/connormason/**`

This reduces the chance of a work-identity commit in a personal repository; it does not guarantee it. The match is a
case-sensitive glob against the remote URLs configured at the moment git reads its configuration, so the repository
falls back to the overlay's default identity when:

- it has no remote yet (commits made before `git remote add` keep the default; later commits switch);
- the owner or host differs in letter case (`ConnorMason`, `GitHub.com`);
- the remote uses an SSH host alias (`git@github.com-personal:...`) or an explicit port (`ssh://git@github.com:22/...`);
- the host is any other spelling (`www.github.com`, `ssh.github.com`), or the URL is rewritten from an alias by
  `url.<base>.insteadOf` (the URL is matched as written, not as rewritten).

To be certain, add the remote before the first commit or set `user.name` and `user.email` in the repository (a local
setting overrides all of the above; without it, `user.name` still comes from the overlay's default if it sets one, else
from the personal default in [`git/.gitconfig`](git/.gitconfig)). In this repository, the
[leak guard](../scripts/hooks/README.md#check-leakspy)'s `--identity` check additionally rejects a commit whose identity
matches its patterns.

## Apply

```bash
./stow.sh                # link every package from every layer
./stow.sh shell git      # only the named packages
./stow.sh -n             # preview without writing
./stow.sh --list         # list packages
```

`stow.sh` always uses `--no-folding` so `$HOME` directories stay real (several packages, and apps' runtime state, share
them), and it is all-or-nothing: unresolvable conflicts abort before anything is linked. `--backup-conflicts` moves
blocking files to `~/.dotfiles-backup/<timestamp>/` first. Run `./stow.sh --help` for the full contract.

## Add a new config

1. Place the file at its `$HOME`-relative path inside the appropriate package, e.g. `stow/shell/.config/foo/bar.conf`
   maps to `~/.config/foo/bar.conf`. Create a new top-level package directory if it is a new tool.
2. Add or update the package's row in the table above.
3. Run `./stow.sh -n <package>` to preview, then `./stow.sh <package>`.

## Clarifications needed

- The `node` package contains only a bun snippet (`44-node.zsh`). Should the package be named for bun, or is Node
  tooling expected to land here?
