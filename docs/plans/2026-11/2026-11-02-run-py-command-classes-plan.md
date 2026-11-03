# run.py class-based `Command` registration — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `run.py`'s `@command` decorator registry with the work dotfiles' class-based `Command` ABC at full
infrastructure parity.

**Architecture:** One atomic swap inside `run.py`: new infrastructure (`ExitCode`, `Command`, `get_commands`, default
help formatter), all 15 commands rewritten as `Command` subclasses, and `build_parser`/`main` ported from
`~/dotfiles/run.py`. Module-level helpers (doctor checks, vault/inventory helpers, `retry_on_failure`) stay put. Docs
follow in a second task; verification in a third.

**Tech Stack:** Python stdlib only (`abc`, `argparse`, `enum`), pytest, prek (ruff check, mypy, interrogate, mdformat).

**Design:** [`2026-11-02-run-py-command-classes-design.md`](2026-11-02-run-py-command-classes-design.md)

## Global Constraints

- Worktree: `.claude/worktrees/run-py-command-classes` (branch
  `worktree-run-py-command-classes`). Run every command from there.
- Run Python only via `uv run …`; never bare `python`/`python3`. Never run `ruff format`.
- `run.py` stays stdlib-only and must type-check under mypy `python_version = "3.9"` (`[override]` is already disabled
  for module `run` in `pyproject.toml`).
- isort `force-single-line`: one import per line. Single quotes. Sphinx docstrings, no blank line after class docstring.
- Command description text must stay byte-identical (the generated `Makefile` must not change).
- Exit-code values unchanged except: `main()` Ctrl-C → `3` (`USER_CANCELLED`), unknown command → `2` (`SETUP_ERROR`).
- Reference implementation: `~/dotfiles/run.py:283-466` (infra) and `:4530-4711` (parser/main).
- Baseline help output captured at `$TMPDIR/runpy-baseline/` (root + every subcommand).
- **Rebased onto `51a13a3` (PR #37) after drafting.** `run.py:NNN` references in Tasks 1-2 were taken at `5401a8a`;
  locate code by the named function instead. PR #37 added a `NAS` group (between Codebase and Dotfiles) with
  `nas-deploy` (`script_only=True`) and `nas-provision`, plus `tests/unit/test_run_nas.py` — see Step 7b and Step 2.

______________________________________________________________________

### Task 1: Registry swap in `run.py` (+ tests)

**Files:**

- Modify: `run.py` (imports `:56-85`; types `:159-178`; registration `:180-325`; all command sections `:894-1793`;
  parser/main `:1795-1911`)
- Modify: `tests/unit/test_run_doctor.py` (command invocations `:228-364`, registration test `:278-283`)
- Create: `tests/unit/test_run_commands.py`

**Interfaces (produced):**

- `run.ExitCode(int, enum.Enum)` — `SUCCESS=0`, `COMMAND_FAILED=1`, `SETUP_ERROR=2`, `USER_CANCELLED=3`
- `run.REGISTERED_COMMANDS: dict[str, Command]` (instances)
- `run.Command` — ClassVars `name`, `description`, `epilog`, `group`, `add_help`, `script_only`, `makefile_only`;
  `__init_subclass__(register: bool = True)`; `help_formatter_type` property; `add_arguments(parser)`; abstract
  `run(args)`; `__call__(args)`
- `run.get_commands(*, by_group=False, group_order=None, exclude=None)`
- `run.get_default_help_formatter_cls(*, indent_increment=2, max_help_position=50, width=None)`
- `run.Args(argparse.Namespace)` — `command: str | None`, `debug: bool`
- `run.build_parser() -> argparse.ArgumentParser`; `run.main(argv: Sequence[str] | None = None) -> None`
- Command classes: `ListHostsCommand`, `InventoryStatusCommand`, `UpdateInventoryCommand`, `VaultDecryptCommand`,
  `VaultEncryptCommand`, `CleanCommand`, `PreCommand`, `InstallHooksCommand`, `UninstallHooksCommand`,
  `MakefileCommand`, `DoctorCommand`, `BootstrapCommand`, `StowCommand`, `RenderCommand`, `TestCommand`

- [ ] **Step 1: Write the new failing tests** — create `tests/unit/test_run_commands.py`:

```python
"""
Unit tests for run.py command registration, parser construction, and dispatch
"""
from __future__ import annotations

import argparse
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import run


@pytest.fixture
def registry(monkeypatch: pytest.MonkeyPatch) -> dict[str, run.Command]:
    """
    Swap in an empty command registry so test-defined commands never leak into the real one
    """
    isolated: dict[str, run.Command] = {}
    monkeypatch.setattr(run, 'REGISTERED_COMMANDS', isolated)
    return isolated


def _make_command(cls_name: str, *, register: bool = True, **attrs: object) -> type[run.Command]:
    """
    Define (and, by default, register) a no-op Command subclass with the given class attributes
    """
    namespace: dict[str, object] = {'run': lambda self, args: None, **attrs}
    return types.new_class(
        cls_name,
        (run.Command,),
        {'register': register},
        lambda ns: ns.update(namespace),
    )


class TestCommandRegistration:
    """
    Tests for Command subclass auto-registration
    """
    def test_subclass_registers_instance_under_derived_name(self, registry: dict[str, run.Command]) -> None:
        """
        Test that defining a subclass registers an instance named after the class minus its Command suffix
        """
        cls = _make_command('SampleCommand', __doc__='Do a sample thing')
        assert list(registry) == ['sample']
        assert isinstance(registry['sample'], cls)
        assert registry['sample'].description == 'Do a sample thing'

    def test_derived_name_lowercases_and_dashes_underscores(self, registry: dict[str, run.Command]) -> None:
        """
        Test that underscores become dashes and CamelCase is lowercased (not kebab-cased)
        """
        _make_command('Multi_WordCommand')
        assert list(registry) == ['multi-word']

    def test_explicit_name_and_description_win(self, registry: dict[str, run.Command]) -> None:
        """
        Test that explicit name and description class attributes override the derived values
        """
        _make_command('WhateverCommand', name='custom-name', description='Explicit', __doc__='Docstring')
        assert registry['custom-name'].description == 'Explicit'

    def test_register_false_skips_registration(self, registry: dict[str, run.Command]) -> None:
        """
        Test that register=False keeps an intermediate base class out of the registry
        """
        base = _make_command('BaseCommand', register=False)
        assert registry == {}

        types.new_class('ChildCommand', (base,), {}, lambda ns: ns.update({'__doc__': 'Child'}))
        assert list(registry) == ['child']

    def test_script_only_and_makefile_only_conflict(self, registry: dict[str, run.Command]) -> None:
        """
        Test that a command cannot be both script-only and makefile-only
        """
        with pytest.raises(ValueError, match='script_only'):
            _make_command('BothCommand', script_only=True, makefile_only=True)
        assert registry == {}

    def test_call_dispatches_to_run(self, registry: dict[str, run.Command]) -> None:
        """
        Test that calling a command instance invokes its run method with the parsed args
        """
        seen: list[argparse.Namespace] = []
        _make_command('RecordCommand', run=lambda self, args: seen.append(args))

        args = argparse.Namespace(flag=True)
        registry['record'](args)
        assert seen == [args]

    def test_real_commands_registered(self) -> None:
        """
        Test that every run.py command is registered, in definition order
        """
        assert list(run.REGISTERED_COMMANDS) == [
            'list-hosts', 'inventory-status', 'update-inventory', 'vault-decrypt', 'vault-encrypt',
            'clean', 'pre', 'install-hooks', 'uninstall-hooks', 'makefile',
            'doctor', 'bootstrap', 'stow', 'render', 'test',
        ]


class TestGetCommands:
    """
    Tests for get_commands filtering and grouping
    """
    @pytest.fixture(autouse=True)
    def _commands(self, registry: dict[str, run.Command]) -> None:
        """
        Register three commands across two groups plus one ungrouped command
        """
        _make_command('AlphaCommand', group='G1')
        _make_command('BetaCommand',  group='G2')
        _make_command('GammaCommand')

    def test_by_name(self) -> None:
        """
        Test that commands are returned by name in registration order
        """
        assert list(run.get_commands()) == ['alpha', 'beta', 'gamma']

    def test_exclude(self) -> None:
        """
        Test that excluded names are dropped
        """
        assert list(run.get_commands(exclude=['beta'])) == ['alpha', 'gamma']

    def test_by_group_defaults_ungrouped_to_other_commands(self) -> None:
        """
        Test that grouping preserves insertion order and files ungrouped commands under Other commands
        """
        groups = run.get_commands(by_group=True)
        assert {g: list(c) for g, c in groups.items()} == {
            'G1':             ['alpha'],
            'G2':             ['beta'],
            'Other commands': ['gamma'],
        }

    def test_group_order(self) -> None:
        """
        Test that listed groups come first and unlisted groups follow in insertion order
        """
        groups = run.get_commands(by_group=True, group_order=['G2'])
        assert list(groups) == ['G2', 'G1', 'Other commands']


def _subparsers(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    """
    Get the subcommand parsers of the root parser
    """
    action = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    return dict(action.choices)


class TestBuildParser:
    """
    Tests for argument parser construction
    """
    def test_every_command_has_subparser(self) -> None:
        """
        Test that each registered command gets a subparser
        """
        assert set(_subparsers(run.build_parser())) == set(run.REGISTERED_COMMANDS)

    def test_help_option_in_other_options_group(self) -> None:
        """
        Test that subcommand -h/--help lives in a trailing Other options group
        """
        for name, subparser in _subparsers(run.build_parser()).items():
            last_group = subparser._action_groups[-1]
            assert last_group.title == 'Other options', name
            assert ['-h', '--help'] in [a.option_strings for a in last_group._group_actions], name

    def test_add_help_false_omits_help(self, registry: dict[str, run.Command]) -> None:
        """
        Test that add_help=False suppresses the subcommand help option
        """
        _make_command('QuietCommand', add_help=False)
        subparser = _subparsers(run.build_parser())['quiet']
        assert not any('-h' in a.option_strings for a in subparser._actions)

    def test_parses_into_typed_args(self) -> None:
        """
        Test that subcommand options land on the root Args namespace
        """
        args = run.build_parser().parse_args(['stow', '-n', 'zsh'], namespace=run.Args())
        assert args.command == 'stow'
        assert args.simulate is True
        assert args.packages == ['zsh']

    @pytest.mark.parametrize(
        ('argv',                    'expected'),
        [
            (['-d',          'pre'], True),
            (['--debug',     'pre'], True),
            (['--no-debug',  'pre'], False),
        ],
    )
    def test_debug_flag(self, monkeypatch: pytest.MonkeyPatch, argv: list[str], expected: bool) -> None:
        """
        Test the -d/--debug/--no-debug root option
        """
        monkeypatch.setattr(run, 'RUN_DEBUG', False)
        assert run.build_parser().parse_args(argv, namespace=run.Args()).debug is expected


class TestMain:
    """
    Tests for main() dispatch and exit codes
    """
    @pytest.fixture(autouse=True)
    def _no_debug(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Keep main() from leaking a debug-mode change into other tests
        """
        monkeypatch.setattr(run, 'RUN_DEBUG', False)

    def test_no_command_prints_help_and_fails(self, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that running without a command prints help and exits 1
        """
        with pytest.raises(SystemExit) as exc_info:
            run.main([])
        assert exc_info.value.code == run.ExitCode.COMMAND_FAILED
        assert "Runner script for Connor's dotfiles" in capsys.readouterr().out

    def test_dispatches_to_command(self, registry: dict[str, run.Command]) -> None:
        """
        Test that main() runs the selected command with the parsed args
        """
        seen: list[argparse.Namespace] = []
        _make_command('RecordCommand', run=lambda self, args: seen.append(args))
        run.main(['record'])
        assert [a.command for a in seen] == ['record']

    def test_keyboard_interrupt_exits_user_cancelled(self, registry: dict[str, run.Command]) -> None:
        """
        Test that Ctrl-C inside a command exits with USER_CANCELLED
        """
        def interrupt(self: run.Command, args: argparse.Namespace) -> None:
            raise KeyboardInterrupt

        _make_command('InterruptCommand', run=interrupt)
        with pytest.raises(SystemExit) as exc_info:
            run.main(['interrupt'])
        assert exc_info.value.code == run.ExitCode.USER_CANCELLED

    @pytest.mark.parametrize(
        ('argv',              'traceback_shown'),
        [
            (['explode'],       False),
            (['-d', 'explode'], True),
        ],
    )
    def test_unexpected_error_exits_command_failed(
        self,
        registry: dict[str, run.Command],
        capsys: pytest.CaptureFixture[str],
        argv: list[str],
        traceback_shown: bool,
    ) -> None:
        """
        Test that an unexpected exception exits 1, with a traceback only in debug mode
        """
        def explode(self: run.Command, args: argparse.Namespace) -> None:
            raise RuntimeError('boom')

        _make_command('ExplodeCommand', run=explode)
        with pytest.raises(SystemExit) as exc_info:
            run.main(argv)

        captured = capsys.readouterr()
        assert exc_info.value.code == run.ExitCode.COMMAND_FAILED
        assert 'Unexpected error: boom' in captured.out
        assert ('Traceback' in captured.err) is traceback_shown


class TestMakefileCommand:
    """
    Tests for the makefile command
    """
    def test_generated_makefile_matches_checked_in(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that regenerating the Makefile reproduces the checked-in file (drift guard)
        """
        generated = tmp_path / 'Makefile'
        monkeypatch.setattr(run, 'MAKEFILE_PATH', generated)
        run.get_commands()['makefile'](argparse.Namespace())
        assert generated.read_text() == (run.DOTFILES_DIR / 'Makefile').read_text()
```

- [ ] **Step 2: Update `tests/unit/test_run_doctor.py` invocations**

Replace each direct function call with a registry call:

| Old                                     | New                                                  |
| --------------------------------------- | ---------------------------------------------------- |
| `run.cmd_doctor(…)`                     | `run.get_commands()['doctor'](…)`                    |
| `run.cmd_stow(args)`                    | `run.get_commands()['stow'](args)`                   |
| `run.cmd_bootstrap(args)`               | `run.get_commands()['bootstrap'](args)`              |
| `run.cmd_render(args)`                  | `run.get_commands()['render'](args)`                 |
| `run.cmd_test(…)`                       | `run.get_commands()['test'](…)`                      |
| `run.get_command_groups()['Dotfiles']`  | `run.get_commands(by_group=True)['Dotfiles']`        |

Update the `TestDoctorCommand` docstring to "Tests for the doctor orchestration and command registration" (unchanged).

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_run_commands.py tests/unit/test_run_doctor.py -q`
Expected: FAIL — `AttributeError: module 'run' has no attribute 'Command'` / `'get_commands'`.

- [ ] **Step 4: Imports.** In `run.py` add (sorted, single-line): `import abc`, `import enum`, `import traceback`,
  `from typing import ClassVar`; in the `TYPE_CHECKING` block add `from collections.abc import Sequence`.

- [ ] **Step 5: Types + infrastructure.** Delete `CommandFunc`/`AddArgumentsFunc` (`:169-170`) and the whole registration
  section (`:180-325`: header comment, `CommandInfo`, `REGISTERED_COMMANDS`, `command()`, `get_command_functions()`,
  `get_command_groups()`). Insert after `SupportsWrite`:

```python
# ====================================================================================================
# Exit codes
# ====================================================================================================


class ExitCode(int, enum.Enum):
    """
    Script exit codes
    """
    SUCCESS        = 0
    COMMAND_FAILED = 1
    SETUP_ERROR    = 2
    USER_CANCELLED = 3


# ====================================================================================================
# Command registration
#
# Commands are classes deriving from the abstract Command base:
#   - Subclasses register on definition via __init_subclass__ (pass `register=False` for intermediate bases)
#   - The name defaults to the class name minus its "Command" suffix, lowercased; multi-word commands set `name`
#   - The description defaults to the class docstring and drives subparser, script, and Makefile help text
#   - add_arguments() adds command options; a nested Args(argparse.Namespace) types the parsed result
#   - group / script_only / makefile_only control help organization and Makefile generation
#
# Example::
#
#     class UpdateInventoryCommand(Command):
#         '''
#         Update inventory repo
#         '''
#         name:  ClassVar[str] = 'update-inventory'
#         group: ClassVar[str] = 'Inventory'
#
#         class Args(argparse.Namespace):
#             force: bool
#
#         def add_arguments(self, parser: argparse.ArgumentParser) -> None:
#             parser.add_argument('-f', '--force', action='store_true', help='Discard local changes first')
#
#         def run(self, args: Args) -> None:
#             ...
#
# ====================================================================================================


def get_default_help_formatter_cls(
    *,
    indent_increment: int = 2,
    max_help_position: int = 50,
    width: int | None = None,
) -> type[argparse.HelpFormatter]:
    """
    Get HelpFormatter class to use for main script parser and default for subcommand parsers,
    unless :attr:`Command.help_formatter_type` overridden to return a different formatter type.

    :param indent_increment: number of spaces representing a single indentation level in help text
    :param max_help_position: max width of first column (command/parameter names) in help text
    :param width: max width of help text. If None (default), fill entire width available in the terminal
    :return: :class:`argparse.HelpFormatter` type
    """
    return cast(
        'type[argparse.HelpFormatter]',
        partial(
            argparse.RawTextHelpFormatter,
            indent_increment=indent_increment,
            max_help_position=max_help_position,
            width=width,
        ),
    )


REGISTERED_COMMANDS: dict[str, Command] = {}


class Command(metaclass=abc.ABCMeta):
    """
    Abstract base class for script commands.

    Subclasses define a command by setting class attributes and implementing :meth:`run`.
    Commands are auto-registered upon class definition via :meth:`__init_subclass__`.

    Class attributes:

    :cvar name: command name (used as subcommand on CLI). Defaults to class name lowercased with
                trailing "Command" stripped and underscores replaced with dashes
    :cvar description: command description shown in help text. Defaults to class docstring
    :cvar epilog: epilog text appended after help text
    :cvar group: command group name for help organization
    :cvar add_help: add --help/-h help option to command subparser (help option is added after parameters added by
                    :meth:`add_arguments` to an "Other options" group)
    :cvar script_only: if True, don't include command in Makefile targets generated by ``makefile`` command
    :cvar makefile_only: if True, don't include command in help text of script when called directly
    """
    name:          ClassVar[str | None] = None
    description:   ClassVar[str | None] = None
    epilog:        ClassVar[str | None] = None
    group:         ClassVar[str | None] = None
    add_help:      ClassVar[bool]       = True
    script_only:   ClassVar[bool]       = False
    makefile_only: ClassVar[bool]       = False

    def __init_subclass__(cls, register: bool = True, **kwargs: Any) -> None:
        """
        Register the command subclass in the global command registry.

        Derives the command name from the class name (stripping a ``Command`` suffix and lowercasing), populates
        the description from the class docstring if not explicitly set, and assigns the default help formatter.

        :param register: if False, skip registration (useful for abstract intermediate base classes)
        :raises ValueError: if both ``script_only`` and ``makefile_only`` are set
        """
        super().__init_subclass__(**kwargs)
        if not register:
            return

        if cls.script_only and cls.makefile_only:
            raise ValueError(f'{cls.__name__}: only one of `script_only` and `makefile_only` may be True')

        if cls.name is None:
            cls.name = cls.__name__.removesuffix('Command').replace('_', '-').lower()
        if 'description' not in cls.__dict__:
            cls.description = inspect.getdoc(cls)

        REGISTERED_COMMANDS[cls.name] = cls()

    def __call__(self, args: argparse.Namespace) -> None:
        return self.run(args)

    @property
    def help_formatter_type(self) -> type[argparse.HelpFormatter]:
        """
        :class:`argparse.HelpFormatter` type to use for command subparser help text.
        """
        return get_default_help_formatter_cls()

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:  # noqa: B027  (intentional no-op default)
        """
        Add command-specific arguments to the subparser.

        Override in subclasses to define CLI arguments. Default implementation is a no-op.

        :param parser: the argparse subparser for this command
        """
        pass

    @abc.abstractmethod
    def run(self, args: argparse.Namespace) -> None:
        """
        Execute the command.

        :param args: parsed command-line arguments
        """
        raise NotImplementedError
```

Then copy `get_commands` with its three `@overload`s verbatim from `~/dotfiles/run.py:409-466`.

- [ ] **Step 6: Convert the Inventory commands.** Each `@command(group='Inventory')` function becomes a class whose
  docstring is the function's docstring and whose `run(self, args: argparse.Namespace) -> None` body is the old function
  body moved verbatim, with `sys.exit(1)` → `sys.exit(ExitCode.COMMAND_FAILED)` and `sys.exit(0)` →
  `sys.exit(ExitCode.SUCCESS)` (same treatment in `parse_extra_vars`, `require_vault_password`, `require_inventory`).
  Keep the `# TODO: cleanup formatting` comment above `InventoryStatusCommand`. Headers:

```python
class ListHostsCommand(Command):
    """
    List available bootstrap targets from inventory
    """
    name:  ClassVar[str] = 'list-hosts'
    group: ClassVar[str] = 'Inventory'

    def run(self, args: argparse.Namespace) -> None:
        ...  # body of cmd_list_hosts (run.py:916-962)


class InventoryStatusCommand(Command):   # body: cmd_inventory_status (run.py:971-1071)
    name:  ClassVar[str] = 'inventory-status'
    group: ClassVar[str] = 'Inventory'

class VaultDecryptCommand(Command):      # body: cmd_vault_decrypt (run.py:1210-1244)
    name:  ClassVar[str] = 'vault-decrypt'
    group: ClassVar[str] = 'Inventory'

class VaultEncryptCommand(Command):      # body: cmd_vault_encrypt (run.py:1252-1285)
    name:  ClassVar[str] = 'vault-encrypt'
    group: ClassVar[str] = 'Inventory'
```

`UpdateInventoryCommand` replaces `add_update_inventory_arguments` + `cmd_update_inventory`; the closures become
static methods (`@staticmethod` outermost: on Python 3.9 a `staticmethod` object is not callable, so it cannot be the
inner decorator), and the pull helper takes `force` explicitly:

```python
class UpdateInventoryCommand(Command):
    """
    Update inventory repo
    """
    name:  ClassVar[str] = 'update-inventory'
    group: ClassVar[str] = 'Inventory'

    class Args(argparse.Namespace):
        force: bool

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            '-f',
            '--force',
            action='store_true',
            help='Force update by discarding any uncommitted local changes',
        )

    @staticmethod
    @retry_on_failure(max_attempts=3, delay=2.0, backoff=2.0)
    def pull_inventory_repo(*, force: bool = False, **kwargs: Any) -> subprocess.CompletedProcess:
        """
        Pull the latest inventory changes, optionally discarding uncommitted local changes first

        :param force: reset uncommitted changes before pulling
        :param kwargs: extra keyword arguments for :func:`shell_command`
        :return: completed ``git pull`` process
        """

        # If --force flag provided, reset any uncommitted changes before pulling
        if force:
            ...  # unchanged reset block (run.py:1100-1114)

        ...  # unchanged pull try/except/else (run.py:1116-1129)

    @staticmethod
    @retry_on_failure(max_attempts=3, delay=5.0, backoff=2.0)
    def clone_inventory_repo(**kwargs: Any) -> subprocess.CompletedProcess:
        """
        Clone the inventory repo into the inventory directory

        :param kwargs: extra keyword arguments for :func:`shell_command`
        :return: completed ``git clone`` process
        """
        ...  # unchanged clone try/except/else (run.py:1133-1145)

    def run(self, args: Args) -> None:
        printf('🔄 Updating inventory...', fg='bright_white')
        try:

            # Case 1: Inventory directory exists and is a git repo - pull latest changes
            if INVENTORY_DIR.exists() and (INVENTORY_DIR / '.git').exists():
                self.pull_inventory_repo(force=args.force)

            # Case 2: Inventory directory exists but isn't a git repo - remove and re-clone
            elif INVENTORY_DIR.exists():
                shutil.rmtree(INVENTORY_DIR)
                self.clone_inventory_repo()

            # Case 3: Inventory directory does not exist - clone from remote
            else:
                self.clone_inventory_repo()

        except Exception:
            printf('❌ Failed to update inventory after multiple attempts', fg='red', bold=True)
            sys.exit(ExitCode.COMMAND_FAILED)
```

(The `...` markers above denote the exact unchanged line ranges to move; nothing in them changes.)

- [ ] **Step 7: Convert the Codebase commands.** `clean`, `pre`, `install-hooks`, `uninstall-hooks` follow the same
  pattern (bodies verbatim from `run.py:1307-1325`, `:1333-1338`, `:1346-1351`, `:1359-1364`):

```python
class CleanCommand(Command):
    """
    Remove all environments, build artifacts, and caches
    """
    name:  ClassVar[str] = 'clean'
    group: ClassVar[str] = 'Codebase'

class PreCommand(Command):
    """
    Run prek (pre-commit) hooks on all project files
    """
    name:  ClassVar[str] = 'pre'
    group: ClassVar[str] = 'Codebase'

class InstallHooksCommand(Command):
    """
    Install prek git hook shims (overwrites any existing shims)
    """
    name:  ClassVar[str] = 'install-hooks'
    group: ClassVar[str] = 'Codebase'

class UninstallHooksCommand(Command):
    """
    Uninstall prek git hook shims
    """
    name:  ClassVar[str] = 'uninstall-hooks'
    group: ClassVar[str] = 'Codebase'
```

`MakefileCommand` keeps the explicit styled description and iterates `get_commands(by_group=True)`:

```python
class MakefileCommand(Command):
    """
    Generate Makefile from project management script commands
    """
    name:        ClassVar[str] = 'makefile'
    group:       ClassVar[str] = 'Codebase'
    description: ClassVar[str] = ' '.join([
        'Generate Makefile from project management script commands',
        style(f'({Path(__file__).name})', dim=True),
    ])

    def run(self, args: argparse.Namespace) -> None:
        command_groups: dict[str, dict[str, Command]] = {}
        command_names:  list[str]                     = []

        for group_name, commands in get_commands(by_group=True).items():
            for cmd_name, cmd_info in commands.items():
                if not cmd_info.script_only:
                    command_groups.setdefault(group_name, {})[cmd_name] = cmd_info
                    command_names.append(cmd_name)

        ...  # rest unchanged (run.py:1387-1426)
```

Update the Codebase section comment: "`makefile`: Generate Makefile targets from registered `Command` classes".

- [ ] **Step 7b: Convert the NAS commands.** `resolve_nas_target`, `require_nas_reachable`, `resolve_reachable_nas`,
  `warn_on_dirty_services`, and `build_nas_provision_command` stay module-level (tests patch/call them there); their
  `sys.exit(1)` calls become `sys.exit(ExitCode.COMMAND_FAILED)`.

```python
class NasDeployCommand(Command):
    """
    Sync services/ to the NAS and run deploy.sh there (the same script CI uses)
    """
    name:        ClassVar[str]  = 'nas-deploy'
    group:       ClassVar[str]  = 'NAS'
    script_only: ClassVar[bool] = True

    class Args(argparse.Namespace):
        service: str
        dry_run: bool

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        ...  # parser.add_argument calls from add_nas_deploy_arguments, unchanged

    def run(self, args: Args) -> None:
        ...  # body of cmd_nas_deploy, unchanged


class NasProvisionCommand(Command):
    """
    Provision the NAS with the Ansible playbook: system config, the stow engine, then services
    """
    name:  ClassVar[str] = 'nas-provision'
    group: ClassVar[str] = 'NAS'

    class Args(argparse.Namespace):
        tags:       str | None
        limit:      str | None
        check:      bool
        diff:       bool
        extra_vars: list[str] | None
        verbose:    int

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        ...  # parser.add_argument calls from add_nas_provision_arguments, unchanged

    def run(self, args: Args) -> None:
        ...  # body of cmd_nas_provision, unchanged
```

In `tests/unit/test_run_nas.py` replace `run.cmd_nas_deploy(` → `run.get_commands()['nas-deploy'](` and
`run.cmd_nas_provision(` → `run.get_commands()['nas-provision'](`; rename the `info` locals in the two registration tests
to `cmd`. Add `'nas-deploy', 'nas-provision'` between `'makefile'` and `'doctor'` in `test_real_commands_registered`.

- [ ] **Step 8: Convert the Dotfiles commands.** Fold each `add_*_arguments` into `add_arguments`, add a nested `Args`:

```python
class DoctorCommand(Command):
    """
    Check overlay registry, links, rendered settings, git version, and tools
    """
    name:  ClassVar[str] = 'doctor'
    group: ClassVar[str] = 'Dotfiles'

    class Args(argparse.Namespace):
        fix: bool

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            '-f',
            '--fix',
            action='store_true',
            help=(
                'Run the fix for each failing check, then re-check\n'
                '(links: stow.sh --backup-conflicts, which moves blocking files\n'
                'into ~/.dotfiles-backup/<timestamp>/)'
            ),
        )

    def run(self, args: Args) -> None:
        ...  # body of cmd_doctor (run.py:1594-1608), sys.exit(1) → sys.exit(ExitCode.COMMAND_FAILED)


class BootstrapCommand(Command):
    """
    Run the layered bootstrap stages (bootstrap/bootstrap.sh)
    """
    name:  ClassVar[str] = 'bootstrap'
    group: ClassVar[str] = 'Dotfiles'

    class Args(argparse.Namespace):
        dry_run:    bool
        list:       bool
        only:       str | None
        from_stage: str | None
        resume:     bool
        verify:     bool
        no_log:     bool

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        ...  # parser.add_argument calls from add_bootstrap_arguments (run.py:1615-1650), unchanged

    def run(self, args: Args) -> None:
        ...  # body of cmd_bootstrap (run.py:1658-1676)


class StowCommand(Command):
    """
    Link stow packages from every layer into the home directory (stow.sh)
    """
    name:  ClassVar[str] = 'stow'
    group: ClassVar[str] = 'Dotfiles'

    class Args(argparse.Namespace):
        packages:         list[str]
        simulate:         bool
        backup_conflicts: bool
        verbose:          bool

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        ...  # from add_stow_arguments (run.py:1683-1704)

    def run(self, args: Args) -> None:
        ...  # body of cmd_stow (run.py:1712-1722)


class RenderCommand(Command):
    """
    Render settings files from per-layer fragments (scripts/dotfiles/render.py)
    """
    name:  ClassVar[str] = 'render'
    group: ClassVar[str] = 'Dotfiles'

    class Args(argparse.Namespace):
        targets: list[str]
        diff:    bool
        check:   bool
        force:   bool
        verbose: bool

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        ...  # from add_render_arguments (run.py:1729-1754)

    def run(self, args: Args) -> None:
        ...  # body of cmd_render (run.py:1762-1774)


class TestCommand(Command):
    """
    Run the test suite via uv (public-index wrapper)
    """
    __test__ = False  # not a pytest test class despite the Test* name

    name:  ClassVar[str] = 'test'
    group: ClassVar[str] = 'Dotfiles'

    class Args(argparse.Namespace):
        paths: list[str]

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('paths', nargs='*', help='Test paths (default: tests/)')

    def run(self, args: Args) -> None:
        ...  # body of cmd_test (run.py:1789-1792)
```

(`__test__ = False` only matters if pytest ever collects `run.py`; drop it if `ruff`/`mypy` object and collection is
confirmed not to touch `run.py`.)

- [ ] **Step 9: Parser + entry point.** Add `SCRIPT_HELP_COL_SPACING: int = 4` to "Other static configuration".
  Replace `run.py:1795-1907` (section comment through `main`) with:

```python
# ====================================================================================================
# Command-line argument parsing / entry point
#
# build_parser() creates the root parser (help text organized by command group, Debug Options and Other Options groups)
# and one subparser per registered Command, with each command's -h/--help in a trailing "Other options" group.
#
# main() parses args into the typed root Args namespace, enables debug mode if requested, dispatches to the selected
# command, and maps Ctrl-C / unexpected errors to ExitCode values.
# ====================================================================================================


class Args(argparse.Namespace):
    """
    Annotated :class:`argparse.Namespace` returned by parsing with :func:`build_parser`
    """
    command: str | None  # subcommand name
    debug:   bool        # -d/--debug


def build_parser_help_text(*, col_spacing: int = SCRIPT_HELP_COL_SPACING) -> str:
    """
    Build help text for argument parser with commands listed by group

    :param col_spacing: width of spacing between command name and command description columns in script help text
    :return: help text string
    """
    col1_width = len(max(get_commands(), key=len))

    help_text = style("Runner script for Connor's dotfiles", fg='bright_green') + '\n\n'
    help_text += style('Commands:', fg='bright_white', bold=True) + '\n\n'
    for group_name, commands in get_commands(by_group=True).items():
        help_text += f'  {style(group_name, fg="bright_white")}\n'
        for cmd_name, cmd_info in commands.items():
            if not cmd_info.makefile_only:
                description = cmd_info.description or f'Run {cmd_name} command'
                help_text += f'    {style(cmd_name.ljust(col1_width + col_spacing), fg="yellow")} '
                help_text += f'{description.splitlines()[0]}\n'
        help_text += '\n'
    return help_text
```

Then `build_parser()` copied from `~/dotfiles/run.py:4559-4664` with these edits: the debug option
gets `'-d'` before `'--debug'`; drop the `--uv-verbose` option entirely; rename the misnamed `debug_opts` local in
`add_other_opts` to `other_opts`. Then:

```python
def main(argv: Sequence[str] | None = None) -> None:
    """
    Main entry point

    :param argv: argument list to parse. Defaults to ``sys.argv[1:]``
    """
    global RUN_DEBUG

    # Build argument parser and parse command-line args
    parser = build_parser()
    args   = parser.parse_args(argv, namespace=Args())

    # Print help text if no command provided
    if not args.command:
        parser.print_help()
        sys.exit(ExitCode.COMMAND_FAILED)

    # Enable debug logging
    if args.debug:
        RUN_DEBUG = True

    # Run specified command
    commands = get_commands()
    if cmd := commands.get(args.command):
        try:
            cmd(args)
        except KeyboardInterrupt:
            printf('⚠️ Operation cancelled by user', fg='yellow')
            sys.exit(ExitCode.USER_CANCELLED)
        except Exception as e:
            printf(f'❌ Unexpected error: {e!s}', fg='red', bold=True)
            if RUN_DEBUG:
                traceback.print_exc(file=sys.stderr)
            sys.exit(ExitCode.COMMAND_FAILED)
    else:
        printf(f'❓ Unknown command: {args.command}', fg='red', bold=True)
        printf(f'   Available commands: {", ".join(commands.keys())}')
        sys.exit(ExitCode.SETUP_ERROR)
```

Update the module docstring "Architecture" paragraph: "The script uses a class-based command registration system: each
command subclasses the abstract `Command` base, which auto-registers it on definition and:" (bullets unchanged), and add
"**Dotfiles**: Wrap the layered engine (bootstrap, stow, render, doctor, test)" under "Command Categories".

- [ ] **Step 10: Run the tests**

Run: `uv run pytest tests/unit/test_run_commands.py tests/unit/test_run_doctor.py tests/unit/test_run_shell_command.py -q`
Expected: PASS.

- [ ] **Step 11: Lint**

Run: `uv run ruff check --fix run.py tests/unit/test_run_commands.py tests/unit/test_run_doctor.py` then
`prek run --files run.py tests/unit/test_run_commands.py tests/unit/test_run_doctor.py`
Expected: all hooks pass (ruff, mypy, interrogate, codespell).

- [ ] **Step 12: Commit** (only once the user has asked for commits)

```bash
git add run.py tests/unit/test_run_commands.py tests/unit/test_run_doctor.py
git commit -m "refactor(run.py): class-based Command registration (parity with work dotfiles)"
```

______________________________________________________________________

### Task 2: Documentation

**Files:**

- Modify: `docs/RUN_PY_REFERENCE.md` (`makefile` behavior `:159`, "Command Registration System" `:234-261`, "Type System"
  `:405-430`, "Extension Guide" `:535-590`, best practice 5 `:618`, "Argument Parser Construction" `:696-701`)
- Modify: `.ctx/ARCHITECTURE.md:100`, `.claude/rules/python-style.md:41-45`, `README.md:321`

**Interfaces:** Consumes the names from Task 1 only.

- [ ] **Step 1: `docs/RUN_PY_REFERENCE.md` — Command Registration System.** Replace `:236-261` with a
  `class ListHostsCommand(Command)` example (docstring, `name`, `group`, `run`), a ClassVar table (`name`, `description`,
  `epilog`, `group`, `add_help`, `script_only`, `makefile_only` with defaults and meanings from the `Command`
  docstring), the `register=False` note, the `help_formatter_type` override note, and:
  "**Registry:** `REGISTERED_COMMANDS` maps `name -> Command` instance; query it with
  `get_commands(by_group=..., group_order=..., exclude=...)`."
- [ ] **Step 2: Type System.** Drop `CommandFunc`/`AddArgumentsFunc` and the `CommandInfo` block; add `ExitCode` (four
  members) and the root `Args` namespace.
- [ ] **Step 3: Extension Guide.** Rewrite "Adding New Commands" as: (1) subclass `Command` with docstring/`name`/`group`
  and `run`; (2) options via nested `Args(argparse.Namespace)` + `add_arguments`; (3) regenerate the Makefile. Rewrite
  "Adding New Command Groups" with two `group = 'Deployment'` classes. Best practice 5 → "Use
  `sys.exit(ExitCode.COMMAND_FAILED)` on failure". `makefile` behavior bullet → "Reads every registered `Command`".
  "Argument Parser Construction" → root Debug/Other Options groups, `add_arguments`, `-h` in "Other options", formatter
  via `help_formatter_type`. Error Handling: `KeyboardInterrupt` exits `USER_CANCELLED` (3).
- [ ] **Step 4: Other docs.** `.ctx/ARCHITECTURE.md:100` → "Command registration via `Command` subclasses
  (auto-registered by `__init_subclass__`)". `.claude/rules/python-style.md` "run.py patterns" → "Commands are
  `Command` subclasses (abstract base in `run.py`) that auto-register on definition into a global registry driving both
  argparse and Makefile generation; options go in `add_arguments` with a nested typed `Args` namespace". `README.md:321`
  → "**Command registration** via auto-registering `Command` classes".
- [ ] **Step 5: Format + check.** Run: `prek run mdformat --files docs/RUN_PY_REFERENCE.md README.md .claude/rules/python-style.md`
  (`.ctx/` is excluded from mdformat). Then `uv run pytest tests/unit/test_docs_consistency.py -q`. Expected: PASS.
- [ ] **Step 6: Commit** (once authorized) — `docs: document class-based run.py commands`.

______________________________________________________________________

### Task 3: Verification

- [ ] **Step 1:** `uv run pytest -q` — expect ≥ 867 passed (baseline at `51a13a3`) plus the new tests, 0 failed.
- [ ] **Step 2:** `uv run python run.py makefile && git diff --exit-code Makefile` — expect no diff.
- [ ] **Step 3:** Help diff against baseline:

```bash
A="$TMPDIR/runpy-after"; mkdir -p "$A"
uv run python run.py --help > "$A/root.txt" 2>&1
for c in list-hosts inventory-status update-inventory vault-decrypt vault-encrypt clean pre install-hooks \
         uninstall-hooks makefile nas-deploy nas-provision doctor bootstrap stow render test; do
    uv run python run.py "$c" --help > "$A/$c.txt" 2>&1
done
diff -ru "$TMPDIR/runpy-baseline" "$A"
```

Expected differences only: root help gains the "Commands:" header, indented groups, and Debug/Other Options groups;
subcommand `-h` moves into "Other options"; `doctor --fix` help wraps on the manual breaks. No command missing, no
option missing or renamed.

- [ ] **Step 4:** Smoke: `uv run python run.py doctor` (exit code matches pre-change behavior on this machine);
  `uv run python run.py; echo $?` → `1`.
- [ ] **Step 5:** `prek run --all-files` — all hooks pass.
