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
per line, `#` comments and blank lines ignored). Layers are ordered: the repo root first, then overlays in file order.
An overlay contributes through its own `bootstrap/` directory:

| Part                                                             | Behavior                                                                                                                        |
| ---------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| `NN-*.sh`                                                        | Stages, merged with the base's by name. A two-digit number may be used only once across all layers (fatal otherwise)            |
| `env.sh`                                                         | Sourced by `lib.sh` at the top level of every shell that sources it, base first, so overlays can set variables base stages read |
| `Brewfile`, `uv-tools.txt`, `vscode-extensions.txt`, `repos.txt` | Manifest fragments; stages enumerate every layer's copy with `manifest_files NAME`                                              |

Each stage runs as a separate `bash <path>` process with these exported:

| Variable            | Value                                         |
| ------------------- | --------------------------------------------- |
| `BOOTSTRAP_DRY_RUN` | `1` under `--dry-run`, otherwise `0`          |
| `DOTFILES_REPO`     | Root of the base layer (this repository)      |
| `DOTFILES_LAYER`    | Root of the layer the stage itself comes from |

## Stages

| Stage        | Purpose                            | Layer |
| ------------ | ---------------------------------- | ----- |
| 00-preflight | macOS + Command Line Tools present | base  |
