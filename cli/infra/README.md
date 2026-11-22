[Project Root](../../README.md) > [cli](../README.md) > **infra**

# cli/infra

The command framework: configuration, shared types, the `Command` base class with its registry, and the argparse entry
point.

| Module                     | Contents                                                                                                                                          |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`config.py`](config.py)   | Constants, `DOTFILES_`-prefixed environment variables and their values, project paths, `ExitCode`, `VERSION_RE`, and the mutable `RUN_DEBUG` flag |
| [`types.py`](types.py)     | `PathLike`, `StyleColor`, `CommandFunc`, `AddArgumentsFunc`, `SupportsWrite`, `ToolInfo`, `SSHTarget`, and the TypeVars `F`, `T_contra`, `ModT`   |
| [`command.py`](command.py) | `Command` (abstract base that registers subclasses), `REGISTERED_COMMANDS`, `get_commands`, `get_default_help_formatter_cls`                      |
| [`main.py`](main.py)       | `Args`, `build_parser_help_text`, `build_parser`, and `main`                                                                                      |

`DOTFILES_DIR` in `config.py` is derived from the file's own location (`Path(__file__).parents[2]`), so it is the
repository root regardless of the working directory; `SCRIPT_PATH` is `DOTFILES_DIR / 'run.py'`.

## Dependencies

- `config.py`, `types.py`, and `command.py` import only the standard library.
- `main.py` imports `config`, `command`, and `cli.utils` (`shell`, `styling`).
- Reverse: every module in [`cli/utils/`](../utils/README.md) imports `config` and/or `types`; every module in
  [`cli/commands/`](../commands/README.md) imports `command` and `config`.
