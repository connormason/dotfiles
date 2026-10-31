[Project Root](../README.md) > **Bootstrap**

# Bootstrap

Layered, resumable provisioning driver. [`bootstrap.sh`](bootstrap.sh) discovers numbered stage scripts in the repo root
and in every registered overlay, merges them by number, and runs them in order. [`lib.sh`](lib.sh) holds the shared
helpers (`log`, `warn`, `die`, `run`, `try`, `prime_sudo`, layer discovery) that stages source.

## Usage

```bash
bootstrap/bootstrap.sh [--dry-run] [--list] [--only STAGE] [--from STAGE] [--resume] [--verify] [--no-log]
```

| Flag           | Effect                                                                                                   |
| -------------- | -------------------------------------------------------------------------------------------------------- |
| `--dry-run`    | Export `BOOTSTRAP_DRY_RUN=1`: stages print mutating commands instead of running them                     |
| `--list`       | List stages in run order and exit; overlay stages are tagged with their layer root                       |
| `--only STAGE` | Run a single stage                                                                                       |
| `--from STAGE` | Run from `STAGE` to the end                                                                              |
| `--resume`     | Run from the stage after the last successfully completed one (cannot combine with `--only/--from`)       |
| `--verify`     | After every stage succeeds, run `scripts/hooks/uv-public.sh run python run.py doctor` from the repo root |
| `--no-log`     | Do not tee the run to a logfile                                                                          |
| `-h`, `--help` | Show usage (served before the overlay registry is read, so it works with a broken registry)              |

Run state lives in `${BOOTSTRAP_LOG_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/dotfiles-bootstrap}`: one timestamped
logfile per run and a `last-completed-stage` file that `--resume` reads. Dry runs write nothing and never prompt for
sudo. Outside dry-run, sudo is primed once by the driver and kept alive for the whole run.

## Overlay contract

An overlay is a directory listed in the overlays registry
(`${DOTFILES_OVERLAYS_FILE:-${XDG_CONFIG_HOME:-$HOME/.config}/dotfiles/overlays}`, one absolute or `~/`-prefixed path
per line, `#` comments and blank lines ignored). Layers are ordered: the repo root first, then overlays in file order. A
listed path that is missing or cannot be entered is fatal, as is a layer listed twice (compared by canonical path, so
the repo root cannot also be registered as an overlay). An overlay contributes through its own `bootstrap/` directory:

| Part                                                             | Behavior                                                                                                                        |
| ---------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| `NN-*.sh`                                                        | Stages, merged with the base's by name. A two-digit number may be used only once across all layers (fatal otherwise)            |
| `env.sh`                                                         | Sourced by `lib.sh` at the top level of every shell that sources it, base first, so overlays can set variables base stages read |
| `Brewfile`, `uv-tools.txt`, `vscode-extensions.txt`, `repos.txt` | Manifest fragments; stages enumerate every layer's copy with `manifest_files NAME`                                              |

Each stage runs as a separate `"$BASH" <path>` process (the same bash that runs the driver, so `/bin/bash bootstrap.sh`
exercises every stage under bash 3.2) with these exported:

| Variable            | Value                                                                                                                 |
| ------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `BOOTSTRAP_DRY_RUN` | `1` under `--dry-run`, otherwise `0`                                                                                  |
| `DOTFILES_REPO`     | Root of the base layer (this repository)                                                                              |
| `DOTFILES_LAYER`    | Root of the layer the stage itself comes from                                                                         |
| `DOTFILES_OS`       | `darwin` or `linux` from `uname -s`; set it to preview another OS's selection (stages, stow packages, render targets) |

Base stages source the helpers with `source "$HERE/lib.sh"`. An overlay stage lives outside this repository, so it must
source them through the exported base root: `source "$DOTFILES_REPO/bootstrap/lib.sh"`.

## OS support

The engine runs on macOS and on Debian-family Linux with Homebrew (Linuxbrew) in `/home/linuxbrew/.linuxbrew`. `lib.sh`
`dotfiles_os` reports `darwin` or `linux` (`DOTFILES_OS` overrides it). A stage that only makes sense on one OS calls
`require_os <os>...` right after sourcing `lib.sh`; elsewhere it logs the skip and exits 0. On Linux the engine never
runs `apt` or `sudo`: the driver does not prime sudo, and `00-preflight` fails (warns under `--dry-run`) when a system
command is missing. Stow packages opt into an OS with a `.dotfiles-os` marker (see
[`stow/README.md`](../stow/README.md)); Brewfile entries that exist only on macOS sit inside `if OS.mac?`.

## Stages

Base stages, in run order. Overlays interleave their own stages by number. Every mutation goes through `run`/`try`, so
`--dry-run` prints it instead; the exceptions are read-only previews noted below.

| Stage        | Purpose                                                                                                                                           | Layer |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------- | ----- |
| 00-preflight | macOS: Command Line Tools present. Linux: Debian family and the system commands `curl file git cc make ps zsh` (fatal; warning under `--dry-run`) | base  |
| 20-ssh-key   | `~/.ssh` (mode 700) and an ed25519 key; if `ssh -T git@github.com` fails, print the key to register                                               | base  |
| 50-brew      | Install Homebrew if absent (checksum-verified installer), then `brew bundle` each layer's `Brewfile`                                              | base  |
| 60-macos     | macOS preferences (`defaults write`, `chflags`), then restart Dock/Finder/SystemUIServer (macOS only)                                             | base  |
| 72-vscode    | Install missing VS Code extensions from the union of every layer's `vscode-extensions.txt` (macOS only)                                           | base  |
| 80-repos     | Clone each `name url` line of every layer's `repos.txt` into `$HOME/<name>` unless that path exists                                               | base  |
| 90-python    | Install missing uv tools from every layer's `uv-tools.txt` (a later layer's line replaces the earlier one)                                        | base  |
| 95-dotfiles  | `stow.sh --backup-conflicts` (dry run: `stow.sh -n` preview), oh-my-zsh, and its custom plugins                                                   | base  |
| 96-iterm2    | Point iTerm2 at the stowed prefs folder `~/.config/iterm2` (after 95-dotfiles creates it) (macOS only)                                            | base  |
| 97-render    | `render.py`: 0 ok, 1 drift refused (warn), 2 config/I/O error (fail); dry run: `render.py --check`, warn only                                     | base  |

## Manifests

| File                                             | Format                                                       | Read by     |
| ------------------------------------------------ | ------------------------------------------------------------ | ----------- |
| [`Brewfile`](Brewfile)                           | `brew bundle` syntax; macOS-only entries inside `if OS.mac?` | `50-brew`   |
| [`vscode-extensions.txt`](vscode-extensions.txt) | One `publisher.name` extension ID per line                   | `72-vscode` |
| [`repos.txt`](repos.txt)                         | `name url`, separated by spaces or tabs                      | `80-repos`  |
| [`uv-tools.txt`](uv-tools.txt)                   | Package name, optionally followed by `uv tool install` flags | `90-python` |

`#` starts a comment in the three text manifests. Each stage reads the base copy first, then every overlay's copy in
layer order.
