# run.py: class-based `Command` registration — design

**Date:** 2026-11-02 **Status:** approved

## Goal

Replace the `@command` decorator / `CommandInfo` registry in `run.py` with the class-based `Command` infrastructure used
by the work dotfiles (`~/dotfiles/run.py`), at full infrastructure parity, so both repos share one command idiom.

## Decisions

| Question           | Decision                                                                                                    |
| ------------------ | ----------------------------------------------------------------------------------------------------------- |
| Fidelity           | Full infra parity: `Command` ABC, `get_commands`, help formatter, `-h` in "Other options", `ExitCode`, typed `Args`, `main(argv)` |
| Name derivation    | Match work: `removesuffix('Command').replace('_', '-').lower()`; every command sets an explicit `name`     |
| Helper placement   | Doctor checks, vault/inventory helpers, `retry_on_failure` stay module-level (tests patch them there)       |
| Shared module      | Rejected: `run.py` must remain a standalone stdlib script runnable by bare `python3` on a fresh machine    |

## Architecture

### Infrastructure (replaces the "Command registration" section)

- `ExitCode(int, enum.Enum)`: `SUCCESS=0`, `COMMAND_FAILED=1`, `SETUP_ERROR=2`, `USER_CANCELLED=3`. Command failure
  exits use `ExitCode.COMMAND_FAILED` (value unchanged); `main()` uses `USER_CANCELLED` for Ctrl-C (was 1) and
  `SETUP_ERROR` for an unknown command.
- `get_default_help_formatter_cls()` — `partial(argparse.RawTextHelpFormatter, max_help_position=50, ...)`.
- `REGISTERED_COMMANDS: dict[str, Command]` and `Command(metaclass=abc.ABCMeta)` copied from work:
  - ClassVars `name`, `description`, `epilog`, `group`, `add_help`, `script_only`, `makefile_only`
  - `__init_subclass__(register=True)` derives `name` and `description` (class docstring), instantiates, registers
  - `help_formatter_type` property, no-op `add_arguments(parser)`, abstract `run(args)`, `__call__` → `run`
  - **Addition over work:** `__init_subclass__` raises `ValueError` when both `script_only` and `makefile_only` are set,
    preserving the invariant the decorator enforced.
- `get_commands(*, by_group=False, group_order=None, exclude=None)` with overloads, replacing `get_command_functions()`
  and `get_command_groups()`.
- Removed: `CommandInfo`, `command()`, `CommandFunc`, `AddArgumentsFunc`.

### Commands

All 17 commands become `<Name>Command(Command)` classes with explicit `name` and `group` ClassVars; the docstring is the
description (text unchanged so the generated `Makefile` is byte-identical). Commands with options gain a nested
`Args(argparse.Namespace)` and an `add_arguments` method absorbing the former `add_*_arguments` functions:

| Group     | Commands                                                                        |
| --------- | ------------------------------------------------------------------------------- |
| Inventory | `list-hosts`, `inventory-status`, `update-inventory`, `vault-decrypt`, `vault-encrypt` |
| Codebase  | `clean`, `pre`, `install-hooks`, `uninstall-hooks`, `makefile`                  |
| NAS       | `nas-deploy` (`script_only`), `nas-provision` — added by PR #37 after this design was drafted |
| Dotfiles  | `doctor`, `bootstrap`, `stow`, `render`, `test`                                 |

`UpdateInventoryCommand`'s nested closures become `@staticmethod` methods decorated with `@retry_on_failure` (order:
`@staticmethod` outermost — `staticmethod` objects are not callable on Python 3.9, the declared mypy target); the pull
helper takes `force` as a keyword argument instead of closing over `args`.

### Parser and entry point

- Root `Args(argparse.Namespace)`: `command: str | None`, `debug: bool`.
- `build_parser()` follows work: default formatter for root and subparsers; subparsers built with `add_help=False` and
  `-h/--help` appended to an "Other options" group when `cmd.add_help`; root "Debug Options" group with
  `-d/--debug` (`BooleanOptionalAction`, default `RUN_DEBUG`, env-var/default notes) and "Other Options" group with
  `-h/--help`. Work's `--uv-verbose` is omitted (no uv-driven commands here).
- `main(argv: Sequence[str] | None = None)` parses into the root `Args`, prints a traceback to stderr on unexpected
  errors when debug is enabled.
- `RawTextHelpFormatter` does not wrap, so the long `doctor --fix` help gets explicit line breaks.

## Testing

- `tests/unit/test_run_doctor.py` and `tests/unit/test_run_nas.py`: call commands through the registry
  (`run.get_commands()['doctor'](ns)`) and use `run.get_commands(by_group=True)`.
- New `tests/unit/test_run_commands.py`, against an isolated (monkeypatched) registry:
  - name/description derivation, explicit-name override, `register=False`, `script_only`+`makefile_only` error
  - `get_commands`: `exclude`, `by_group`, `group_order`, default group `Other commands`
  - `build_parser`: one subparser per command, `-h` in "Other options", `add_help=False` honored, typed `Args` parsing
  - `main(argv)`: no command → help + exit 1, dispatch, `KeyboardInterrupt` → 3, unexpected error → 1
  - drift guard: `makefile` output equals the checked-in `Makefile`

## Documentation

Update the `run.py` module docstring and section comments, `docs/RUN_PY_REFERENCE.md` (registration, data structures,
"adding a command" examples), `.ctx/ARCHITECTURE.md`, `.ctx/CONVENTIONS.md`, `.claude/rules/python-style.md`, and
`README.md`.

## Verification

- `uv run pytest` and `prek run --all-files` pass.
- `run.py makefile` leaves `Makefile` unchanged.
- `--help` for the root parser and every subcommand diffed against a pre-change baseline; only the intended cosmetic
  differences (option grouping, formatter) appear.
