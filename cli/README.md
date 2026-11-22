[Project Root](../README.md) > **cli**

# cli

Implementation of [`run.py`](../run.py), the repository-management CLI. `run.py` holds the PEP 723 header and the
`main()` call; everything else lives here.

## Layout

| Directory                         | Contents                                                                                         |
| --------------------------------- | ------------------------------------------------------------------------------------------------ |
| [`infra/`](infra/README.md)       | Configuration and paths, shared types, the `Command` base and registry, the argparse entry point |
| [`utils/`](utils/README.md)       | Styling, subprocess execution, and tool / environment / host helpers                             |
| [`commands/`](commands/README.md) | One module per command group; importing the package registers every command                      |

Dependencies point one way: `utils` imports `infra.config` and `infra.types`; `infra.main` imports `utils`; `commands`
imports from all three. A command module never imports another command module.

## How a command is wired

1. A subclass of `cli.infra.command.Command` registers itself in `REGISTERED_COMMANDS` when the class body executes.
2. [`commands/__init__.py`](commands/__init__.py) imports the command modules in a fixed order. That order is the
   registration order, so it decides the order of the groups in `run.py --help` and of the targets in the generated
   `Makefile`.
3. [`infra/main.py`](infra/main.py) builds one argparse subparser per registered command and dispatches to the selected
   one.

## Adding a command

Add the `Command` subclass to the module for its group (or a new module, imported in `commands/__init__.py` at the
position its group should appear in help text), use helpers from `cli.utils`, then run `uv run python run.py makefile`
so the `Makefile` picks up the target. Style rules: [`.claude/rules/python-style.md`](../.claude/rules/python-style.md).

## Runtime flags

`RUN_DEBUG` is the one value `main()` rewrites after import (`--debug` / `--no-debug`). Read it as `config.RUN_DEBUG`
(`from cli.infra import config`); `from cli.infra.config import RUN_DEBUG` would copy the value at import time and miss
the rewrite.

## Tests

[`tests/unit/cli/`](../tests/unit/cli) mirrors this layout (`infra/`, `utils/`, `commands/`). Tests patch a helper in
the module that uses it, for example `monkeypatch.setattr('cli.commands.deploy.shell_command', fake)`, because each
module binds the helpers it imports by name.
