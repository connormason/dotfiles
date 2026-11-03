#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "PyYaml >= 6.0",
# ]
# ///
"""
run.py - CLI interface for Connor's personal dotfiles repository

This script provides a command-line interface for managing the dotfiles repository, including inventory management
and codebase maintenance tasks.

Architecture
-----------
The script uses a class-based command registration system: each command subclasses the abstract ``Command`` base,
which registers it on class definition and:
- Automatically builds argparse subparsers from registered commands
- Organizes commands by group for help text
- Supports generating Makefile targets from registered commands
- Allows commands to be script-only or makefile-only

Command Categories
-----------------
- **Inventory**: Manage the standalone inventory git repository
- **Codebase**: Clean build artifacts, run and prepare prek hooks, generate Makefile
- **NAS**: Provision the home NAS and deploy its Compose services
- **Dotfiles**: Wrap the layered engine (doctor, bootstrap, stow, render, test) and ingest local Claude config
  (track-claude)

Key Features
-----------
- ANSI styling with full color/formatting support (style/printf functions)
- Subprocess execution with live output streaming via pty (shell_command)
- Retry logic with exponential backoff for network operations
- SSH error detection and helpful troubleshooting guidance
- Environment variable configuration for debug mode and repo URLs

Environment Variables
--------------------
- DOTFILES_RUN_DEBUG: Enable debug output (true/false)
- DOTFILES_INVENTORY_REPO_URL: Override inventory repository URL
- NO_COLOR: Disable ANSI styling when set to any non-empty value

Usage Examples
-------------
    # List inventory hosts
    python3 run.py list-hosts

    # Update inventory from remote
    python3 run.py update-inventory

    # Clean build artifacts
    python3 run.py clean

    # Generate Makefile
    python3 run.py makefile

See Also
-------
- README.md: User-facing documentation
- CLAUDE.md: Architecture and development guidance

"""
from __future__ import annotations

import abc
import argparse
import dataclasses
import enum
import errno
import getpass
import inspect
import json
import os
import pty
import re
import select
import shlex
import shutil
import subprocess
import sys
import textwrap
import time
import traceback
from functools import partial
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from typing import Callable
from typing import ClassVar
from typing import Literal
from typing import Protocol
from typing import TypeVar
from typing import Union
from typing import cast
from typing import overload

if TYPE_CHECKING:
    from collections.abc import Iterable
    from collections.abc import Mapping
    from collections.abc import Sequence


# ====================================================================================================
# Constants/configuration
# ====================================================================================================


# Filepaths - All absolute paths relative to script location
SCRIPT_PATH:    Path = Path(__file__)
DOTFILES_DIR:   Path = SCRIPT_PATH.parent
MAKEFILE_PATH:  Path = DOTFILES_DIR  / 'Makefile'
INVENTORY_DIR:  Path = DOTFILES_DIR  / 'inventory'
INVENTORY_FILE: Path = INVENTORY_DIR / 'inventory.yml'
VAULT_PASSWORD: Path = DOTFILES_DIR  / 'vault_password.txt'
PLAYBOOKS_DIR:  Path = DOTFILES_DIR  / 'playbooks'

# Layered dev-env engine (stow.sh, bootstrap driver, settings renderer)
STOW_SCRIPT:      Path = DOTFILES_DIR / 'stow.sh'
BOOTSTRAP_SCRIPT: Path = DOTFILES_DIR / 'bootstrap' / 'bootstrap.sh'
RENDER_SCRIPT:    Path = DOTFILES_DIR / 'scripts' / 'dotfiles' / 'render.py'
UV_PUBLIC:        Path = DOTFILES_DIR / 'scripts' / 'hooks' / 'uv-public.sh'
STOW_DIR:         Path = DOTFILES_DIR / 'stow'
CLAUDE_STOW_DIR:  Path = STOW_DIR / 'claude' / '.claude'

# NAS provisioning (Ansible playbook, collections) and service deploys (script shared with CI)
NAS_PLAYBOOK:       Path = PLAYBOOKS_DIR / 'nas_bootstrap.yml'
NAS_REQUIREMENTS:   Path = DOTFILES_DIR  / 'roles' / 'requirements.yml'
NAS_DEPLOY_SCRIPT:  Path = DOTFILES_DIR  / 'scripts' / 'nas' / 'deploy-services.sh'
NAS_INVENTORY_HOST: str  = 'nas'

# Doctor requirements
REQUIRED_TOOLS:  tuple[str, ...] = ('brew', 'git', 'stow', 'uv', 'zsh')
MIN_GIT_VERSION: tuple[int, int] = (2, 36)  # includeIf "hasconfig:remote.*.url:" support

# Hand-authored Claude Code config that `track-claude` ingests into the `claude` stow package. Machine-managed state
# (plugins/, projects/, caches) stays untracked; stowed files are symlinks, so a regular file here is local-only.
CLAUDE_CONFIG_DIR:      Path      = Path.home() / '.claude'
CLAUDE_TRACKED_SUBDIRS: list[str] = ['agents', 'commands', 'skills', 'hooks', 'rules']
CLAUDE_IGNORE_NAMES:    set[str]  = {'.DS_Store'}

# Git hook types `prek install` must have shimmed (mirrors `default_install_hook_types` in .pre-commit-config.yaml;
# a test keeps the two in sync) and the marker prek writes into every shim it generates
GIT_HOOK_TYPES: tuple[str, ...] = (
    'pre-commit',
    'commit-msg',
    'post-checkout',
    'post-merge',
    'post-rewrite',
    'pre-push',
)
PREK_SHIM_MARKER: str = 'generated by prek'

# Glob patterns for finding vault files within inventory
VAULT_FILE_PATTERNS: list[str] = [
    'group_vars/*/vault.yml',
    'host_vars/*/vault.yml',
]

# Environment variables - All prefixed with DOTFILES_ namespace
ENVVAR_PREFIX:             str = 'DOTFILES'
RUN_DEBUG_ENVVAR:          str = f'{ENVVAR_PREFIX}_RUN_DEBUG'
INVENTORY_REPO_URL_ENVVAR: str = f'{ENVVAR_PREFIX}_INVENTORY_REPO_URL'

RUN_DEBUG:          bool = os.getenv(RUN_DEBUG_ENVVAR, 'false').lower() == 'true'
NO_COLOR:           bool = bool(os.getenv('NO_COLOR'))      # https://no-color.org: any non-empty value disables color
INVENTORY_REPO_URL: str  = os.getenv(
    INVENTORY_REPO_URL_ENVVAR,
    'git@github.com:connormason/dotfiles-inventory.git',
)

# Other static configuration
# Spacing between the command name and description columns in the script help text
SCRIPT_HELP_COL_SPACING: int = 4

# Patterns for files/directories to remove during `run.py clean`
CLEAN_PATTERN_GROUPS: dict[str, list[str]] = {
    'package build artifacts': [
        'build',
        'dist',
        '*.egg-info',
    ],
    'package cache files': [
        '**/__pycache__',
        '**/*.pyc',
    ],
    'tool cache files': [
        '.mypy_cache',
        '.pytest_cache',
        '.ruff_cache',
        '.tox',
        '.nox',
        '.coverage',
    ],
    'virtual environments': [
        'venv',
        '.venv',
    ],
}


# ====================================================================================================
# Basic types
# ====================================================================================================


F        = TypeVar('F',        bound=Callable[..., Any])
T_contra = TypeVar('T_contra', contravariant=True)

PathLike   = Union[str, Path]
StyleColor = Union[int, tuple[int, int, int], str]


class SupportsWrite(Protocol[T_contra]):
    """
    Protocol for types that support being written to and flushed (what ``print(..., flush=True)`` requires)
    """
    def write(self, s: T_contra, /) -> object: ...

    def flush(self) -> object: ...


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

        Derives the command name from the class name (stripping a ``Command`` suffix and lowercasing) and populates
        the description from the class docstring if not explicitly set.

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


@overload
def get_commands(*, exclude: Iterable[str] | None = None) -> dict[str, Command]: ...

@overload
def get_commands(
    *,
    by_group: Literal[True],
    group_order: Sequence[str] | None = ...,
    exclude: Iterable[str] | None = ...,
) -> dict[str, dict[str, Command]]: ...

@overload
def get_commands(
    *,
    by_group: Literal[False] = ...,
    exclude: Iterable[str] | None = ...,
) -> dict[str, Command]: ...

def get_commands(
    *,
    by_group: bool = False,
    group_order: Sequence[str] | None = None,
    exclude: Iterable[str] | None = None,
) -> dict[str, Command] | dict[str, dict[str, Command]]:
    """
    Get all registered commands.

    :param by_group: if True, get commands by group - then name. If False, get commands by name
    :param group_order: explicit ordering of group names when ``by_group=True``. Groups not in this list appear at the
                        end in insertion order. If None, groups are returned in insertion order
    :param exclude: command names to exclude
    :return: mapping from command name -> :class:`Command`,
             or mapping from group name -> command name -> :class:`Command` (if `by_group=True`)
    """
    exclude_cmds: set[str] = set(exclude) if exclude is not None else set()

    commands: dict[str, Command] = {
        cmd_name: cmd_info
        for cmd_name, cmd_info in REGISTERED_COMMANDS.items()
        if cmd_name not in exclude_cmds
    }
    if by_group:
        command_groups: dict[str, dict[str, Command]] = {}
        for cmd_name, cmd_info in get_commands(exclude=exclude).items():
            group_name = cmd_info.group or 'Other commands'
            command_groups.setdefault(group_name, {})[cmd_name] = cmd_info

        # Sort groups by explicit ordering; unlisted groups go at the end in insertion order
        if group_order:
            ordered: dict[str, dict[str, Command]] = {}
            for group_name in group_order:
                if group_name in command_groups:
                    ordered[group_name] = command_groups.pop(group_name)
            ordered.update(command_groups)
            return ordered

        return command_groups
    return commands


# ====================================================================================================
# Formatting
#
# ANSI styling functions for terminal output. The style() function is inspired by Click's style implementation but
# standalone (no external dependencies)
#
# Supports:
#   - Foreground/background colors (named, 256-color palette, RGB tuples)
#   - Text attributes (bold, dim, italic, underline, etc.)
#   - Auto-reset by default to prevent style leakage
#
# The printf() function wraps style() for common use cases and supports:
#   - Debug mode filtering (only prints if RUN_DEBUG=true)
#   - Text indentation
#   - Automatic text-to-str conversion
# ====================================================================================================


ANSI_COLOR: dict[str, int] = {
    'black':   30, 'bright_black':   90,
    'red':     31, 'bright_red':     91,
    'green':   32, 'bright_green':   92,
    'yellow':  33, 'bright_yellow':  93,
    'blue':    34, 'bright_blue':    94,
    'magenta': 35, 'bright_magenta': 95,
    'cyan':    36, 'bright_cyan':    96,
    'white':   37, 'bright_white':   97,
    'reset':   39,
}
ANSI_RESET_ALL = '\033[0m'


def _interpret_color(_color: StyleColor, offset: int = 0) -> str:
    """
    Resolve a color name, integer, or RGB tuple to an ANSI SGR parameter string.

    :param _color: color as a named string, 256-color int, or ``(r, g, b)`` tuple
    :param offset: offset added to the base code (0 for foreground, 10 for background)
    :return: ANSI SGR parameter fragment (e.g. ``"32"`` or ``"38;2;255;0;0"``)
    """
    if isinstance(_color, int):
        return f'{38 + offset};5;{_color:d}'
    if isinstance(_color, (tuple, list)):
        r, g, b = _color
        return f'{38 + offset};2;{r:d};{g:d};{b:d}'
    _color = cast('str', _color)
    return str(ANSI_COLOR[_color] + offset)


def style(
    text: Any,
    *,
    fg: StyleColor | None = None,
    bg: StyleColor | None = None,
    bold: bool | None = None,
    dim: bool | None = None,
    underline: bool | None = None,
    overline: bool | None = None,
    italic: bool | None = None,
    blink: bool | None = None,
    reverse: bool | None = None,
    strikethrough: bool | None = None,
    reset: bool = True,
) -> str:
    """
    Style text with ANSI escape codes. Returns the text unstyled when ``NO_COLOR`` is set.

    :param text: the string to style with ansi codes
    :param fg: foreground color
    :param bg: background color
    :param bold: enable or disable bold mode
    :param dim: enable or disable dim mode
    :param underline: enable or disable underline
    :param overline: enable or disable overline
    :param italic: enable or disable italic
    :param blink: enable or disable blinking
    :param reverse: enable or disable inverse rendering
    :param strikethrough: enable or disable striking through text
    :param reset: add a reset-all code at the end of the string
    :return: styled text
    """
    if NO_COLOR:
        return str(text)
    if not isinstance(text, str):
        text = str(text)

    bits: list[str] = []
    if fg is not None:
        try:
            bits.append(f'\033[{_interpret_color(fg)}m')
        except KeyError:
            raise TypeError(f'Unknown color {fg!r}') from None
    if bg is not None:
        try:
            bits.append(f'\033[{_interpret_color(bg, 10)}m')
        except KeyError:
            raise TypeError(f'Unknown color {bg!r}') from None
    if bold is not None:
        bits.append(f'\033[{1 if bold else 22}m')
    if dim is not None:
        bits.append(f'\033[{2 if dim else 22}m')
    if underline is not None:
        bits.append(f'\033[{4 if underline else 24}m')
    if overline is not None:
        bits.append(f'\033[{53 if overline else 55}m')
    if italic is not None:
        bits.append(f'\033[{3 if italic else 23}m')
    if blink is not None:
        bits.append(f'\033[{5 if blink else 25}m')
    if reverse is not None:
        bits.append(f'\033[{7 if reverse else 27}m')
    if strikethrough is not None:
        bits.append(f'\033[{9 if strikethrough else 29}m')

    bits.append(text)
    if reset:
        bits.append(ANSI_RESET_ALL)
    return ''.join(bits)


def unstyle(text: str) -> str:
    """
    Removes ANSI styling information from a string

    :param text: the text to remove style information from
    :return: string with ANSI styling characters removed
    """
    return re.sub(r'\033\[[;?0-9]*[a-zA-Z]', '', text)


def printf(
    text: str,
    *,
    fg: StyleColor | None = None,
    bg: StyleColor | None = None,
    bold: bool | None = None,
    dim: bool | None = None,
    underline: bool | None = None,
    overline: bool | None = None,
    italic: bool | None = None,
    blink: bool | None = None,
    reverse: bool | None = None,
    strikethrough: bool | None = None,
    reset: bool = True,
    indent: int = 0,
    debug: bool = False,
    file: SupportsWrite[str] | None = None,
) -> None:
    if debug and not RUN_DEBUG:
        return
    if debug:
        fg   = fg if fg   is not None else 'bright_white'
        dim  = dim if dim is not None else True
        file = sys.stderr

    print(
        style(
            textwrap.indent(text, ' ' * indent),
            fg=fg,
            bg=bg,
            bold=bold,
            dim=dim,
            underline=underline,
            overline=overline,
            italic=italic,
            blink=blink,
            reverse=reverse,
            strikethrough=strikethrough,
            reset=reset,
        ),
        file=file,
        # Flush so our lines stay ordered with child-process output when stdout is a pipe (e.g. `| tee`): Python
        # block-buffers a pipe, while subprocesses write to it directly
        flush=True,
    )


def folduser(path: PathLike) -> str:
    """
    Does the opposite of :meth:`pathlib.Path.expanduser`, replacing the user's home directory with a "~"

    :param path: path
    :return: str folded path
    """
    home = str(Path.home())
    return str(path).replace(home, '~')


def arg_note(name: str, val: str, *, dim: bool = True, color: StyleColor | None = 'yellow') -> str:
    return ''.join([
        style(f'[{name}: ', dim=dim),
        style(val,          dim=dim, fg=color),
        style(']',          dim=dim)
    ])


def confirm(prompt_text: str, *, default: bool = True, indent: int = 0) -> bool:
    """
    Prompt the user for Y/n confirmation

    :param prompt_text: the question to display
    :param default: the answer used when the user presses Enter without typing
    :param indent: number of spaces to indent the prompt by
    :return: True if the user confirmed; False if they declined or stdin is closed (EOF). Ctrl-C is not caught, so it
             cancels the whole run through :func:`main`
    """
    suffix = '[Y/n]' if default else '[y/N]'
    try:
        answer = input(f'{" " * indent}{prompt_text} {suffix}: ').strip().lower()
    except EOFError:
        printf('')
        return False

    if not answer:
        return default
    return answer in ('y', 'yes')


# ====================================================================================================
# Command utils
#
# Subprocess execution with enhanced error handling and output formatting
#
# The shell_command() function provides two execution modes:
#   1. capture_output=True: Captures stdout/stderr for programmatic use
#   2. capture_output=False with indent: Streams output live via pty with indentation
#
# Key features:
#   - Automatic environment variable injection (RUN_COMMAND_ENVVARS)
#   - SSH error detection with helpful troubleshooting suggestions
#   - Timeout support with graceful degradation
#   - Custom ShellCommandError with formatted output
# ====================================================================================================


RUN_COMMAND_ENVVARS: dict[str, str] = {}


class ShellCommandError(subprocess.CalledProcessError):
    """
    Exception raised by :func:`shell_command` when called subprocess exits with an error.
    Extends :class:`subprocess.CalledProcessError` with custom string formatting
    """
    def __str__(self) -> str:
        s = super().__str__()
        if self.stdout or self.stderr:
            s += '\n'
        if self.stdout:
            s += f'\n{self.stdout}'
        if self.stderr:
            s += f'\n{self.stderr}'
        return s


@overload
def shell_command(
    cmd: list[str],
    *,
    text: Literal[False],
    encoding: None = ...,
    check: bool = ...,
    capture_output: bool = ...,
    indent: int | None = ...,
    cwd: Path | str | None = ...,
    env: Mapping[str, str] | None = ...,
    timeout: float | None = ...,
    **kwargs: Any,
) -> subprocess.CompletedProcess[bytes]: ...

@overload
def shell_command(
    cmd: list[str],
    *,
    text: Literal[True],
    encoding: str | None = ...,
    check: bool = ...,
    capture_output: bool = ...,
    indent: int | None = ...,
    cwd: Path | str | None = ...,
    env: Mapping[str, str] | None = ...,
    timeout: float | None = ...,
    **kwargs: Any,
) -> subprocess.CompletedProcess[str]: ...

@overload
def shell_command(
    cmd: list[str],
    *,
    text: bool = ...,
    encoding: str | None = ...,
    check: bool = ...,
    capture_output: bool = ...,
    indent: int | None = ...,
    cwd: Path | str | None = ...,
    env: Mapping[str, str] | None = ...,
    timeout: float | None = ...,
    **kwargs: Any,
) -> subprocess.CompletedProcess[str]: ...

def shell_command(
    cmd: list[str],
    *,
    text: bool = True,
    encoding: str | None = None,
    check: bool = True,
    capture_output: bool = False,
    indent: int | None = None,
    cwd: Path | str | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float | None = None,
    **kwargs: Any,
) -> subprocess.CompletedProcess[str] | subprocess.CompletedProcess[bytes]:
    """
    Run command in subprocess

    :param cmd: list of cmd args
    :param text: if True (default), file objects are opened in text mode (stdout/stderr type: str).
                 If False, file objects opened in binary mode (stdout/stderr type: bytes)
    :param encoding: text encoding to use when `text=True`
    :param check: if True, raise exception if command exits with nonzero code
    :param capture_output: if True, capture stdout/stderr from subprocess
    :param indent: number of spaces to indent command output by if `capture_output=False`, or None
    :param cwd: current working directory when command is run
    :param env: environment variables when command is run
    :param timeout: timeout in seconds for command execution, or None for no timeout
    :raises ShellCommandError: if command exits with nonzero code and ``check=True``
    :raises subprocess.TimeoutExpired: if command times out and ``check=True``
    :return: :class:`subprocess.CompletedProcess`
    """
    indent_str = ' ' * (indent or 0)
    printf(f'{indent_str}Running command: {style(shlex.join(cmd), fg="bright_magenta")}', debug=True)
    cmd_env: dict[str, str] = {
        **os.environ,
        **RUN_COMMAND_ENVVARS,
        **(env or {}),
    }

    # Capture command output
    if capture_output or (indent is None):
        try:
            return subprocess.run(
                cmd,
                check=check,
                capture_output=capture_output,
                text=text,
                cwd=cwd,
                env=cmd_env or None,
                encoding=encoding,
                timeout=timeout,
                **kwargs,
            )
        except subprocess.CalledProcessError as e:
            raise ShellCommandError(e.returncode, shlex.join(cmd), output=e.output, stderr=e.stderr) from e
        except subprocess.TimeoutExpired as e:
            printf(f'❌ Command timed out after {timeout}s', fg='red', bold=True, indent=indent or 0)
            printf(f'  └─ Command: {shlex.join(cmd)}',       fg='red',            indent=(indent or 0) + 1)
            if check:
                raise
            return subprocess.CompletedProcess(cmd, -1, stdout=e.stdout, stderr=e.stderr)

    # Print command real-time output
    else:
        master_fd, slave_fd = pty.openpty()
        process = subprocess.Popen(
            cmd,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            cwd=cwd,
            env=cmd_env or None,
            universal_newlines=True,
            **kwargs,
        )
        os.close(slave_fd)

        buffer:     str = ''
        all_output: str = ''
        timed_out = False
        deadline = None if timeout is None else time.monotonic() + timeout
        try:
            while True:
                # Poll with the remaining budget: a bare blocking read would never notice a hung, silent child
                remaining = None if deadline is None else max(deadline - time.monotonic(), 0)
                if not select.select([master_fd], [], [], remaining)[0]:
                    timed_out = True
                    break

                try:
                    output = os.read(master_fd, 1024).decode()
                except OSError as e:
                    # Linux raises EIO (macOS returns b'') once the child closes its end of the pty
                    if e.errno == errno.EIO:
                        break
                    raise
                if not output:
                    break

                buffer     += output
                all_output += output
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    print(f'{indent_str}{line}')

            if buffer:
                print(f'{indent_str}{buffer}', end='')
        finally:
            os.close(master_fd)
            if not timed_out:
                try:
                    returncode = process.wait(timeout=None if deadline is None else max(deadline - time.monotonic(), 0))
                except subprocess.TimeoutExpired:
                    timed_out = True
            if timed_out:
                process.kill()
                process.wait()

        if timed_out:
            printf(f'❌ Command timed out after {timeout}s',  fg='red', bold=True, indent=indent or 0)
            printf(f'  └─ Command: {shlex.join(cmd)}',        fg='red',            indent=(indent or 0) + 1)
            if check:
                raise subprocess.TimeoutExpired(cmd, cast('float', timeout), output=all_output)
            return subprocess.CompletedProcess(cmd, -1, stdout=all_output)

        if check and (returncode != 0):
            raise ShellCommandError(returncode, shlex.join(cmd), stderr=all_output)
        return subprocess.CompletedProcess(cmd, returncode, stdout=all_output)


def detect_ssh_error(e: subprocess.CalledProcessError) -> tuple[bool, str | None]:
    """
    Detect SSH-related errors from git command output

    :param e: subprocess exception
    :return: tuple of (is_ssh_error, specific_error_type)
    """
    stderr_text: str = e.stderr if isinstance(e.stderr, str) else e.stderr.decode()
    stdout_text: str = e.stdout if isinstance(e.stdout, str) else e.stdout.decode()
    combined = f'{stderr_text}\n{stdout_text}'.lower()

    # Check for various SSH error patterns
    ssh_patterns: dict[str, str] = {
        'permission_denied':     'permission denied (publickey)',
        'host_key_verification': 'host key verification failed',
        'no_identities':         'no such identity',
        'key_load_failed':       'load key',
        'connection_refused':    'connection refused',
        'connection_timeout':    'connection timed out',
        'unknown_host':          'could not resolve hostname',
    }

    for error_type, pattern in ssh_patterns.items():
        if pattern in combined:
            return True, error_type

    # Generic SSH detection
    if any(indicator in combined for indicator in ('ssh:', '@github.com', 'publickey', 'git@')):
        return True, 'generic'

    return False, None


def handle_command_error(e: subprocess.CalledProcessError, context: str, *, suggestion: str | None = None) -> None:
    """
    Format and display subprocess errors with context

    :param e: subprocess exception
    :param context: description of what operation failed
    :param suggestion: optional helpful suggestion for fixing the issue
    """
    printf(f'❌ {context}',                        fg='red', bold=True)
    printf(f'    └─ Exit code: {e.returncode}',    fg='red')
    printf(f'    └─ Command: {shlex.join(e.cmd)}', fg='red')

    if e.stderr:
        stderr_text = e.stderr if isinstance(e.stderr, str) else e.stderr.decode()
        printf('   └─ Error output:', fg='red')
        for line in stderr_text.strip().split('\n')[:10]:
            printf(f'      {line}',   fg='red')

    # Check for SSH-specific errors and provide tailored suggestions
    is_ssh_error, ssh_error_type = detect_ssh_error(e)
    if is_ssh_error and ssh_error_type:
        printf('   └─ 🔑 SSH Authentication Issue Detected', fg='yellow', bold=True)

        if ssh_error_type == 'permission_denied':
            printf('   └─ 💡 Your SSH key is not authorized for this repository',                       fg='yellow')
            printf('      Try these steps:',                                                            fg='yellow')
            printf('      1. Check if SSH key exists: ls -la ~/.ssh/',                                  fg='yellow')
            printf('      2. Generate new key if needed: ssh-keygen -t ed25519 -C "email@example.com"', fg='yellow')
            printf('      3. Add key to ssh-agent: ssh-add ~/.ssh/id_ed25519',                          fg='yellow')
            printf('      4. Add public key to GitHub: https://github.com/settings/keys',               fg='yellow')
            printf('      5. Test connection: ssh -T git@github.com',                                   fg='yellow')

        elif ssh_error_type == 'host_key_verification':
            printf('   └─ 💡 GitHub host key not recognized',                    fg='yellow')
            printf('      Run: ssh-keyscan github.com >> ~/.ssh/known_hosts',    fg='yellow')

        elif ssh_error_type in ('no_identities', 'key_load_failed'):
            printf('   └─ 💡 SSH key could not be loaded',                       fg='yellow')
            printf('      Run: ssh-add ~/.ssh/id_ed25519 (or your key path)',    fg='yellow')

        elif ssh_error_type == 'connection_refused':
            printf('   └─ 💡 SSH connection refused',                            fg='yellow')
            printf('      Check network connectivity and firewall settings',     fg='yellow')

        elif ssh_error_type == 'connection_timeout':
            printf('   └─ 💡 SSH connection timed out',                          fg='yellow')
            printf('      Check network connectivity and try again',             fg='yellow')

        elif ssh_error_type == 'unknown_host':
            printf('   └─ 💡 Could not resolve hostname',                        fg='yellow')
            printf('      Check your internet connection and DNS settings',      fg='yellow')

        else:  # generic SSH error
            printf('   └─ 💡 Try testing SSH connection: ssh -T git@github.com', fg='yellow')

    elif suggestion:
        printf(f'   └─ 💡 {suggestion}',                                         fg='yellow')


# ====================================================================================================
# Other utility functions
#
# Includes:
#   - retry_on_failure: Decorator for exponential backoff retry logic
#   - parse_extra_vars: Parse ansible-playbook -e key=value arguments
# ====================================================================================================


def retry_on_failure(
    *,
    max_attempts: int = 3,
    delay: float = 2.0,
    backoff: float = 2.0,
) -> Callable[[F], F]:
    """
    Decorator to retry failed operations with exponential backoff

    :param max_attempts: maximum number of retry attempts
    :param delay: initial delay in seconds between retries
    :param backoff: exponential backoff multiplier
    :return: decorator function
    """
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception: Exception | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_attempts:
                        wait_time = delay * (backoff ** (attempt - 1))
                        printf(
                            f'  └─ Attempt {attempt}/{max_attempts} failed, retrying in {wait_time:.1f}s...',
                            fg='yellow',
                        )
                        time.sleep(wait_time)
                    else:
                        printf(f'  └─ All {max_attempts} attempts failed', fg='red')

            if last_exception:
                raise last_exception
            return None

        return wrapper          # type: ignore[return-value]
    return decorator


def parse_extra_vars(extra_vars_list: list[str] | None) -> dict[str, str]:
    """
    Parse ``ansible-playbook`` extra variables (-e, --extra-vars) from command line format (key=val)

    :param extra_vars_list: value from argparse
    :return: mapping from key -> value
    """
    extra_vars: dict[str, str] = {}
    if extra_vars_list:
        for var_str in extra_vars_list:
            if '=' not in var_str:
                printf(
                    f'❌ {style("Error", fg="red", bold=True)}: Invalid extra var format "{var_str}". '
                    f'Use key=value format'
                )
                sys.exit(ExitCode.COMMAND_FAILED)

            key, value = var_str.split('=', 1)
            extra_vars[key.strip()] = value.strip()

    return extra_vars


# ====================================================================================================
# Inventory commands
#
# Commands for managing the standalone inventory git repository
#
# The inventory is a separate repository cloned into the inventory/ directory by run.py.
#
# Key commands:
#   - list-hosts:       Parse inventory.yml and display available bootstrap targets
#   - inventory-status: Show git status and metadata for inventory directory
#   - update-inventory: Clone (if missing) or pull (if exists) inventory repo
#     - Supports --force flag to reset uncommitted changes before pulling
#     - Includes retry logic with exponential backoff for network resilience
#     - Provides SSH error detection and troubleshooting guidance
# ====================================================================================================


def find_vault_files() -> list[Path]:
    """
    Find all vault.yml files in the inventory directory

    :return: sorted list of vault file paths
    """
    vault_files: list[Path] = []
    for pattern in VAULT_FILE_PATTERNS:
        vault_files.extend(INVENTORY_DIR.glob(pattern))
    return sorted(vault_files)


def require_vault_password() -> None:
    """
    Validate that the vault password file exists and exit with an error if not

    :raises SystemExit: if vault password file is missing
    """
    if not VAULT_PASSWORD.is_file():
        printf('❌ Vault password file not found', fg='red', bold=True)
        printf(f'   Expected: {folduser(VAULT_PASSWORD)}', indent=3)
        printf(f'   Create it with: {style("echo YOUR_PASSWORD > vault_password.txt", fg="bright_magenta")}', indent=3)
        sys.exit(ExitCode.COMMAND_FAILED)


def require_inventory() -> None:
    """
    Validate that the inventory directory exists and exit with an error if not

    :raises SystemExit: if inventory directory is missing
    """
    if not INVENTORY_DIR.exists():
        printf('❌ Inventory directory not found', fg='red', bold=True)
        printf(f'   Expected: {folduser(INVENTORY_DIR)}', indent=3)
        printf(f'   Run: {style("python3 run.py update-inventory", fg="bright_magenta")}', indent=3)
        sys.exit(ExitCode.COMMAND_FAILED)


class ListHostsCommand(Command):
    """
    List available bootstrap targets from inventory
    """
    name:  ClassVar[str] = 'list-hosts'
    group: ClassVar[str] = 'Inventory'

    def run(self, args: argparse.Namespace) -> None:
        printf('Available Bootstrap Targets', bold=True, fg='bright_white')
        printf('=' * 60,                      bold=True)

        # Check that inventory file exists
        if not INVENTORY_FILE.exists():
            printf('')
            printf('❌ Inventory file not found', fg='red', bold=True)
            printf(f'   Expected: {folduser(INVENTORY_FILE)}',                                 indent=3)
            printf(f'   Run: {style("python3 run.py update-inventory", fg="bright_magenta")}', indent=3)
            sys.exit(ExitCode.COMMAND_FAILED)

        # PyYAML is the one third-party dependency: report a missing module separately from an unparsable inventory
        try:
            import yaml
        except ImportError:
            hint = style('scripts/hooks/uv-public.sh run python run.py list-hosts', fg='bright_magenta')
            printf('')
            printf('❌ PyYAML is required to read the inventory', fg='red', bold=True)
            printf(f'Run it through uv: {hint}', indent=3)
            sys.exit(ExitCode.SETUP_ERROR)

        # Parse inventory file
        try:
            with INVENTORY_FILE.open() as f:
                inventory = yaml.safe_load(f)
        except Exception as e:
            printf('')
            printf('❌ Failed to parse inventory file', fg='red', bold=True)
            printf(f'   Error: {e}', indent=3)
            sys.exit(ExitCode.COMMAND_FAILED)

        # Display all groups and hosts
        if (not inventory) or ('all' not in inventory):
            printf('')
            printf('⚠️  No hosts found in inventory', fg='yellow')
            sys.exit(ExitCode.SUCCESS)

        all_hosts: set[str] = set()
        if 'children' in inventory.get('all', {}):
            printf('')
            for group_name, group_data in inventory['all']['children'].items():
                printf(f'{group_name}:', fg='cyan', bold=True)
                if 'hosts' in group_data:
                    for host_name, host_data in group_data['hosts'].items():
                        all_hosts.add(host_name)
                        ansible_host = host_data.get('ansible_host', host_name) if host_data else host_name
                        printf(f'  └─ {style(host_name, fg="green")}')
                        if ansible_host != host_name:
                            printf(f'     (connects to: {style(ansible_host, dim=True)})', indent=3)
                else:
                    printf('  └─ (no hosts)', dim=True)
                printf('')

        # Show total
        printf('=' * 60,                         bold=True)
        printf(f'Total hosts: {len(all_hosts)}', bold=True)


# TODO: cleanup formatting
class InventoryStatusCommand(Command):
    """
    Display current status of inventory directory
    """
    name:  ClassVar[str] = 'inventory-status'
    group: ClassVar[str] = 'Inventory'

    def run(self, args: argparse.Namespace) -> None:
        printf('Inventory Status', bold=True, fg='bright_white')
        printf('=' * 60, bold=True)
        printf('')

        # Check if inventory directory exists
        if not INVENTORY_DIR.exists():
            printf('Status:   ', fg='bright_white', bold=True, reset=False)
            printf('Not found',  fg='red',          bold=True)
            printf(f'Path:     {style(folduser(INVENTORY_DIR), fg="magenta", dim=True)}', dim=True)
            printf('')
            printf(
                f'💡 Run {style("python3 run.py update-inventory", fg="bright_magenta")} to clone the inventory',
                fg='yellow',
            )
            return

        printf('Status:   ', fg='bright_white', bold=True, reset=False)
        printf('Found',      fg='green',        bold=True)
        printf(f'Path:     {style(folduser(INVENTORY_DIR), fg="magenta", dim=True)}', dim=True)
        printf('')

        # Check if it's a git repository
        git_dir = INVENTORY_DIR / '.git'
        if not git_dir.exists():
            printf('Type:     ', fg='bright_white', bold=True, reset=False)
            printf('Not a git repository', fg='yellow', bold=True)
            printf('')
            printf('⚠️  Inventory exists but is not a git repository', fg='yellow')
            printf(f'   Run {style("python3 run.py update-inventory",  fg="bright_magenta")} to fix', indent=3)
            return

        printf('Type:     ',     fg='bright_white', bold=True, reset=False)
        printf('Git repository', fg='green',        bold=True)
        printf('')

        # Get git remote information
        try:
            result = shell_command(
                ['git', 'remote', 'get-url', 'origin'],
                cwd=INVENTORY_DIR,
                capture_output=True,
            )
            remote_url = result.stdout.strip()
            printf('Remote:   ',           fg='bright_white', bold=True, reset=False)
            printf(remote_url,             fg='cyan')
        except subprocess.CalledProcessError:
            printf('Remote:   ',           fg='bright_white', bold=True, reset=False)
            printf('No remote configured', fg='yellow')

        # Get current branch
        try:
            result = shell_command(
                ['git', 'branch', '--show-current'],
                cwd=INVENTORY_DIR,
                capture_output=True,
            )
            branch = result.stdout.strip()
            printf('Branch:   ', fg='bright_white', bold=True, reset=False)
            printf(branch,       fg='cyan')
        except subprocess.CalledProcessError:
            printf('Branch:   ', fg='bright_white', bold=True, reset=False)
            printf('Unknown',    fg='yellow')

        # Get last commit info
        try:
            result = shell_command(
                ['git', 'log', '-1', '--format=%h - %s (%cr)'],
                cwd=INVENTORY_DIR,
                capture_output=True,
            )
            last_commit = result.stdout.strip()
            printf('Commit:   ', fg='bright_white', bold=True, reset=False)
            printf(last_commit,  dim=True)
        except subprocess.CalledProcessError:
            pass

        # Check for uncommitted changes
        try:
            result = shell_command(
                ['git', 'status', '--porcelain'],
                cwd=INVENTORY_DIR,
                capture_output=True,
            )
            if result.stdout.strip():
                printf('')
                printf('⚠️  Uncommitted changes detected', fg='yellow', bold=True)
                for line in result.stdout.strip().split('\n')[:5]:
                    printf(f'   {line}', indent=3, fg='yellow')
        except subprocess.CalledProcessError:
            pass

        # Check if inventory.yml file exists
        printf('')
        if INVENTORY_FILE.exists():
            printf('Inventory file:', fg='bright_white', bold=True, reset=False)
            printf(' Found',          fg='green',        bold=True)
            printf(f'   {style(folduser(INVENTORY_FILE), fg="magenta", dim=True)}', indent=3)
        else:
            printf('Inventory file:', fg='bright_white', bold=True, reset=False)
            printf(' Not found',      fg='red',          bold=True)
            printf(f'   Expected: {style(folduser(INVENTORY_FILE), fg="magenta", dim=True)}', indent=3)


class UpdateInventoryCommand(Command):
    """
    Update inventory repo
    """
    name:  ClassVar[str] = 'update-inventory'
    group: ClassVar[str] = 'Inventory'

    class Args(argparse.Namespace):
        force: bool     # --force

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
            try:
                result = shell_command(
                    ['git', 'status', '--porcelain'],
                    cwd=INVENTORY_DIR,
                    capture_output=True,
                )
                if result.stdout.strip():
                    printf('⚠️  Uncommitted changes detected, resetting...', fg='yellow', indent=3)
                    shell_command(
                        ['git', 'reset', '--hard', 'HEAD'],
                        cwd=INVENTORY_DIR,
                        indent=3,
                    )
            except subprocess.CalledProcessError:
                pass    # Continue with pull anyway

        try:
            cp = shell_command(
                ['git', 'pull', 'origin', 'main'],
                cwd=INVENTORY_DIR,
                indent=3,
                timeout=30,
                **kwargs,
            )
        except subprocess.CalledProcessError as e:
            handle_command_error(e, 'Error pulling inventory repo')
            raise
        else:
            printf('✅ Inventory updated', fg='bright_green')
            return cp

    @staticmethod
    @retry_on_failure(max_attempts=3, delay=5.0, backoff=2.0)
    def clone_inventory_repo(**kwargs: Any) -> subprocess.CompletedProcess:
        """
        Clone the inventory repo into the inventory directory

        :param kwargs: extra keyword arguments for :func:`shell_command`
        :return: completed ``git clone`` process
        """
        try:
            cp = shell_command(
                ['git', 'clone', '--no-progress', INVENTORY_REPO_URL, str(INVENTORY_DIR)],
                indent=3,
                timeout=60,
                **kwargs,
            )
        except subprocess.CalledProcessError as e:
            handle_command_error(e, 'Error cloning inventory repo')
            raise
        else:
            printf('✅ Inventory cloned', fg='bright_green')
            return cp

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


class VaultDecryptCommand(Command):
    """
    Decrypt all inventory vault files for editing
    """
    name:  ClassVar[str] = 'vault-decrypt'
    group: ClassVar[str] = 'Inventory'

    def run(self, args: argparse.Namespace) -> None:
        require_vault_password()
        require_inventory()

        vault_files = find_vault_files()
        if not vault_files:
            printf('⚠️  No vault files found in inventory', fg='yellow')
            return

        printf('🔓 Decrypting vault files...', fg='bright_white')
        failed = 0
        for vault_file in vault_files:
            relative = vault_file.relative_to(INVENTORY_DIR)
            try:
                shell_command(
                    ['ansible-vault', 'decrypt', str(vault_file)],
                    capture_output=True,
                )
                printf(f'  └─ {style(str(relative), fg="green")} decrypted', indent=1)

            # ansible-vault returns error if file is already decrypted
            except subprocess.CalledProcessError as e:
                stderr = e.stderr if isinstance(e.stderr, str) else (e.stderr.decode() if e.stderr else '')
                if ('is not vault encrypted' in stderr) or ('input is not vault encrypted' in stderr):
                    printf(f'  └─ {style(str(relative), fg="yellow")} already decrypted, skipping', indent=1)
                else:
                    printf(f'  └─ {style(str(relative), fg="red")} failed to decrypt', indent=1)
                    if stderr.strip():
                        printf(f'     {stderr.strip()}', indent=1, fg='red')
                    failed += 1

        if failed:
            printf(f'❌ {failed} file{"s" if failed != 1 else ""} failed to decrypt', fg='red', bold=True)
            sys.exit(ExitCode.COMMAND_FAILED)
        else:
            printf('✅ All vault files decrypted', fg='bright_green')


class VaultEncryptCommand(Command):
    """
    Re-encrypt all inventory vault files after editing
    """
    name:  ClassVar[str] = 'vault-encrypt'
    group: ClassVar[str] = 'Inventory'

    def run(self, args: argparse.Namespace) -> None:
        require_vault_password()
        require_inventory()

        vault_files = find_vault_files()
        if not vault_files:
            printf('⚠️  No vault files found in inventory', fg='yellow')
            return

        printf('🔒 Encrypting vault files...', fg='bright_white')
        failed = 0
        for vault_file in vault_files:
            relative = vault_file.relative_to(INVENTORY_DIR)
            try:
                shell_command(
                    ['ansible-vault', 'encrypt', str(vault_file)],
                    capture_output=True,
                )
                printf(f'  └─ {style(str(relative), fg="green")} encrypted', indent=1)

            except subprocess.CalledProcessError as e:
                stderr = e.stderr if isinstance(e.stderr, str) else (e.stderr.decode() if e.stderr else '')
                if 'input is already encrypted' in stderr:
                    printf(f'  └─ {style(str(relative), fg="yellow")} already encrypted, skipping', indent=1)
                else:
                    printf(f'  └─ {style(str(relative), fg="red")} failed to encrypt', indent=1)
                    if stderr.strip():
                        printf(f'     {stderr.strip()}', indent=1, fg='red')
                    failed += 1

        if failed:
            printf(f'❌ {failed} file{"s" if failed != 1 else ""} failed to encrypt', fg='red', bold=True)
            sys.exit(ExitCode.COMMAND_FAILED)
        else:
            printf('✅ All vault files encrypted', fg='bright_green')


# ====================================================================================================
# Codebase commands
#
# General repository maintenance commands:
# - clean:    Remove build artifacts, caches, and temporary files
# - pre:      Run prek hooks on all files
# - makefile: Generate Makefile targets from registered Command classes
#   - Parses all registered commands and creates equivalent Make targets
#   - Organizes targets by command group
#   - Preserves command descriptions in Make comments
#   - Auto-generates help target with formatted command listing
# ====================================================================================================


class CleanCommand(Command):
    """
    Remove all environments, build artifacts, and caches
    """
    name:  ClassVar[str] = 'clean'
    group: ClassVar[str] = 'Codebase'

    def run(self, args: argparse.Namespace) -> None:
        printf('🧹 Cleaning project workspace...', fg='bright_cyan')

        cleaned = 0
        for group, patterns in CLEAN_PATTERN_GROUPS.items():
            printf(f'Cleaning {group}...', indent=3)
            for pattern in patterns:
                for path in DOTFILES_DIR.glob(pattern):
                    path = cast('Path', path)
                    if path.is_dir():
                        printf(f'Removing {path}', debug=True, indent=5)
                        shutil.rmtree(path)
                        cleaned += 1
                    elif path.is_file():
                        printf(f'Removing {path}', debug=True, indent=5)
                        path.unlink()
                        cleaned += 1

        printf(f'{cleaned} file{"s" if cleaned != 1 else ""} removed', debug=True, indent=3)
        printf('✅ Cleanup complete\n', fg='bright_green')


class RunHooksCommand(Command):
    """
    Run prek hooks on modified or specified project files
    """
    name:  ClassVar[str] = 'run-hooks'
    group: ClassVar[str] = 'Codebase'

    class Args(argparse.Namespace):
        # `pre` parses none of the file/ref selection options below (PreCommand.run sets all_files itself)
        hooks:       list[str] | None   # positional arg(s) "HOOK|PROJECT"
        skip:        list[str] | None   # --skip
        all_files:   bool               # --all-files
        files:       list[str] | None   # --files
        directory:   str | None         # --directory
        from_ref:    str | None         # --from-ref
        to_ref:      str | None         # --to-ref
        last_commit: bool               # --last-commit
        stage:       str | None         # --stage
        show_diff:   bool               # --show-diff-on-failure
        fail_fast:   bool               # --fail-fast
        dry_run:     bool               # --dry-run
        verbose:     bool               # --verbose

    def add_arguments(self, parser: argparse.ArgumentParser, *, include_selection: bool = True) -> None:
        parser.add_argument(
            'hooks',
            nargs='*',
            default=None,
            metavar='HOOK|PROJECT',
            help='Hooks or projects to run (default: all)',
        )

        if include_selection:
            file_opts = parser.add_argument_group('File selection')
            file_opts.add_argument(
                '-a',
                '--all-files',
                action='store_true',
                help='Run on all files in the repo',
            )
            file_opts.add_argument(
                '--files',
                nargs='*',
                metavar='FILE',
                help='Run on these files (put hook names before this option)',
            )
            file_opts.add_argument(
                '-d',
                '--directory',
                metavar='DIR',
                help='Run on all files in this directory',
            )

            ref_opts = parser.add_argument_group('Ref selection')
            ref_opts.add_argument(
                '-s',
                '--from-ref',
                metavar='REF',
                help='Original ref in a from_ref...to_ref diff expression',
            )
            ref_opts.add_argument(
                '-o',
                '--to-ref',
                metavar='REF',
                help='Destination ref in a from_ref...to_ref diff expression (default: HEAD)',
            )
            ref_opts.add_argument(
                '--last-commit',
                action='store_true',
                help='Run on the files of the last commit (--from-ref HEAD~1 --to-ref HEAD)',
            )

        run_opts = parser.add_argument_group('Run options')
        run_opts.add_argument(
            '--skip',
            action='append',
            metavar='HOOK|PROJECT',
            help='Skip this hook or project (repeatable)',
        )
        run_opts.add_argument(
            '--stage',
            metavar='STAGE',
            help='The git stage the hooks run for (e.g. pre-push, manual)',
        )
        run_opts.add_argument(
            '--show-diff-on-failure',
            action='store_true',
            dest='show_diff',
            help='Run `git diff` after a hook fails',
        )
        run_opts.add_argument(
            '--fail-fast',
            action='store_true',
            help='Stop after the first failing hook',
        )
        run_opts.add_argument(
            '--dry-run',
            action='store_true',
            help='List the hooks that would run without running them',
        )
        run_opts.add_argument(
            '-v',
            '--verbose',
            action='store_true',
            help='Show verbose prek output',
        )

    @staticmethod
    def build_command(args: Args) -> list[str]:
        """
        Build the ``prek run`` command line

        Hook names go first: prek's ``--files`` is greedy, so a trailing hook name would be read as a filename.

        :param args: parsed arguments (the file and ref selection attributes are absent for commands that omit those
                     options)
        :return: command and arguments
        """
        cmd: list[str] = ['prek', 'run', *(args.hooks or [])]

        if getattr(args, 'all_files', False):
            cmd.append('--all-files')
        if files := getattr(args, 'files', None):
            cmd.extend(['--files', *files])
        if directory := getattr(args, 'directory', None):
            cmd.extend(['--directory', directory])

        if from_ref := getattr(args, 'from_ref', None):
            cmd.extend(['--from-ref', from_ref])
        if to_ref := getattr(args, 'to_ref', None):
            cmd.extend(['--to-ref', to_ref])
        if getattr(args, 'last_commit', False):
            cmd.append('--last-commit')

        for skip in (args.skip or []):
            cmd.extend(['--skip', skip])
        if args.stage:
            cmd.extend(['--stage', args.stage])
        if args.show_diff:
            cmd.append('--show-diff-on-failure')
        if args.fail_fast:
            cmd.append('--fail-fast')
        if args.dry_run:
            cmd.append('--dry-run')
        if args.verbose:
            cmd.append('--verbose')

        return cmd

    def run(self, args: Args) -> None:
        if getattr(args, 'all_files', False):
            printf('🕝 Running prek hooks on all project files...', fg='bright_cyan')
        elif files := getattr(args, 'files', None):
            printf(f'🕝 Running prek hooks on {len(files)} file(s)...', fg='bright_cyan')
        else:
            printf('🕝 Running prek hooks...', fg='bright_cyan')

        sys.exit(shell_command(self.build_command(args), check=False).returncode)


class PreCommand(RunHooksCommand):
    """
    Run prek (pre-commit) hooks on all project files
    """
    name: ClassVar[str] = 'pre'

    def add_arguments(self, parser: argparse.ArgumentParser, **_kwargs: object) -> None:
        super().add_arguments(parser, include_selection=False)

    def run(self, args: RunHooksCommand.Args) -> None:
        args.all_files = True
        super().run(args)


class PrepareHooksCommand(Command):
    """
    Prepare the environments of all prek hooks
    """
    name:  ClassVar[str] = 'prepare-hooks'
    group: ClassVar[str] = 'Codebase'

    class Args(argparse.Namespace):
        hooks:   list[str] | None       # positional arg(s) "HOOK|PROJECT"
        skip:    list[str] | None       # --skip
        verbose: bool                   # --verbose

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            'hooks',
            nargs='*',
            default=None,
            metavar='HOOK|PROJECT',
            help='Hooks or projects to prepare (default: all)',
        )
        parser.add_argument(
            '--skip',
            action='append',
            metavar='HOOK|PROJECT',
            help='Skip this hook or project (repeatable)',
        )
        parser.add_argument(
            '-v',
            '--verbose',
            action='store_true',
            help='Show verbose prek output',
        )

    def run(self, args: Args) -> None:
        cmd: list[str] = ['prek', 'prepare-hooks', *(args.hooks or [])]
        for skip in (args.skip or []):
            cmd.extend(['--skip', skip])
        if args.verbose:
            cmd.append('--verbose')

        printf('⏬ Preparing prek hook environments...', fg='bright_cyan')
        sys.exit(shell_command(cmd, indent=3, check=False).returncode)


class InstallHooksCommand(Command):
    """
    Install prek git hook shims (overwrites any existing shims)
    """
    name:  ClassVar[str] = 'install-hooks'
    group: ClassVar[str] = 'Codebase'

    def run(self, args: argparse.Namespace) -> None:
        printf('🪝 Installing prek git hook shims...', fg='bright_cyan')
        shell_command(
            ['prek', 'install', '-f'],
            indent=3,
            check=False,
        )


class UninstallHooksCommand(Command):
    """
    Uninstall prek git hook shims
    """
    name:  ClassVar[str] = 'uninstall-hooks'
    group: ClassVar[str] = 'Codebase'

    def run(self, args: argparse.Namespace) -> None:
        printf('🪝 Uninstalling prek git hook shims...', fg='bright_cyan')
        shell_command(
            ['prek', 'uninstall'],
            indent=3,
            check=False,
        )


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

        lines: list[str] = [
            '#',
            "# Makefile for Connor's dotfiles",
            '#',
            f'# Auto-generated via `{Path(__file__).name} makefile`',
            '#',
            f'.PHONY: help {" ".join(command_names)}',
            '',
            'BRIGHT_GREEN := \\033[0;92m',
            'BRIGHT_WHITE := \\033[0;97m',
            'YELLOW := \\033[0;33m',
            'NC := \\033[0m',
            '',
            'help: ## Show this help message',
            '\t@echo "$(BRIGHT_GREEN)Runner script for Connor\'s dotfiles$(NC)"',
            '\t@echo ""',
        ]

        # Add grouped help display
        col1_width = len(max(command_names, key=len))
        for group_name, commands in command_groups.items():
            lines.append(f'\t@echo "$(BRIGHT_WHITE){group_name}:$(NC)"')
            for cmd_name, cmd_info in commands.items():
                desc = cmd_info.description.splitlines()[0] if cmd_info.description else f'Run {cmd_name} command'
                lines.append(f'\t@echo "  $(YELLOW){cmd_name:<{col1_width}}$(NC) {desc}"')
            lines.append('\t@echo ""')
        lines.append('')

        # Add targets grouped by section
        for group_name, commands in command_groups.items():
            lines.append(f'# {group_name}')
            for cmd_name, cmd_info in commands.items():
                target = f'{cmd_name}:'
                if cmd_info.description:
                    target += f' ## {cmd_info.description.splitlines()[0]}'
                lines.extend([target, f'\t@python3 {SCRIPT_PATH.relative_to(DOTFILES_DIR)} {cmd_name}', ''])

        with MAKEFILE_PATH.open('w') as f:
            f.write('\n'.join(lines))
        printf('✅ Makefile updated', fg='bright_green')


# ====================================================================================================
# NAS commands
#
# Provision the home NAS and deploy its Compose services from this machine, over SSH (tailnet or LAN):
#   - nas-provision: Run the Ansible playbook (playbooks/nas_bootstrap.yml) against the inventory's ``nas`` host
#   - nas-deploy:    Sync services/ to the NAS and run deploy.sh there (scripts/nas/deploy-services.sh, as CI does)
# ====================================================================================================


def resolve_nas_target(host: str = NAS_INVENTORY_HOST) -> tuple[str, str]:
    """
    Resolve the SSH host and user of an inventory host through ``ansible-inventory``

    :param host: inventory host name
    :return: tuple of (``ansible_host``, ``ansible_user``); missing values fall back to the inventory name and the
             local login, as ssh would
    """
    result = shell_command(
        [
            str(UV_PUBLIC), 'run', 'ansible-inventory',
            '-i', str(INVENTORY_FILE),
            '--vault-password-file', str(VAULT_PASSWORD),
            '--host', host,
        ],
        capture_output=True,
        check=False,
        cwd=DOTFILES_DIR,
    )
    if result.returncode != 0:
        printf(f'❌ Could not read host "{host}" from the inventory', fg='red', bold=True)
        printf(result.stderr.strip(), indent=3)
        sys.exit(ExitCode.COMMAND_FAILED)

    try:
        variables = json.loads(result.stdout)
    except json.JSONDecodeError:
        variables = None
    if not isinstance(variables, dict):
        printf(f'❌ Unexpected ansible-inventory output for host "{host}"', fg='red', bold=True)
        sys.exit(ExitCode.COMMAND_FAILED)

    ssh_host = str(variables.get('ansible_host') or host)
    ssh_user = str(variables.get('ansible_user') or getpass.getuser())
    if '{{' in (ssh_host + ssh_user):
        printf(f'❌ ansible_host/ansible_user for "{host}" are templated: {ssh_user}@{ssh_host}', fg='red', bold=True)
        printf('The NAS commands need literal values in the inventory', indent=3)
        sys.exit(ExitCode.COMMAND_FAILED)

    return ssh_host, ssh_user


def require_nas_reachable(host: str, user: str) -> None:
    """
    Exit with a remedy unless the NAS answers a non-interactive SSH probe

    :param host: SSH host
    :param user: SSH user
    :raises SystemExit: if the probe fails
    """
    result = shell_command(
        ['ssh', '-o', 'ConnectTimeout=5', '-o', 'BatchMode=yes', f'{user}@{host}', 'true'],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        printf(f'❌ Cannot reach the NAS at {user}@{host} over SSH', fg='red', bold=True)
        printf('Is Tailscale up? Does the host resolve? Is your SSH key loaded (ssh-add)?',                 indent=3)
        printf(f'The host comes from ansible_host of "{NAS_INVENTORY_HOST}" in {folduser(INVENTORY_FILE)}', indent=3)
        printf(f'ssh said: {result.stderr.strip()}', indent=3, dim=True)
        sys.exit(ExitCode.COMMAND_FAILED)


def resolve_reachable_nas() -> tuple[str, str]:
    """
    Check the inventory and vault password, resolve the NAS target, and probe it over SSH

    :return: tuple of (SSH host, SSH user)
    """
    require_inventory()
    require_vault_password()

    host, user = resolve_nas_target()
    require_nas_reachable(host, user)
    return host, user


def warn_on_dirty_services() -> None:
    """
    Warn when services/ has uncommitted changes, since a deploy ships the working tree
    """
    result = shell_command(
        ['git', 'status', '--porcelain', '--', 'services'],
        capture_output=True,
        check=False,
        cwd=DOTFILES_DIR,
    )
    if (result.returncode == 0) and result.stdout.strip():
        printf('🟡 services/ has uncommitted changes; deploying the working tree', fg='bright_yellow')
        printf('CI redeploys main whenever it changes a service, which supersedes a branch deploy', indent=3, dim=True)


def build_nas_provision_command(args: argparse.Namespace) -> list[str]:
    """
    Build the ``ansible-playbook`` command line for nas-provision

    :param args: parsed nas-provision arguments
    :return: command and arguments
    """
    cmd: list[str] = [
        str(UV_PUBLIC), 'run', 'ansible-playbook', str(NAS_PLAYBOOK),
        '-i', str(INVENTORY_FILE),
        '--vault-password-file', str(VAULT_PASSWORD),
    ]
    if args.tags:
        cmd.extend(['--tags', args.tags])
    if args.limit:
        cmd.extend(['--limit', args.limit])
    if args.check:
        cmd.append('--check')
    if args.diff:
        cmd.append('--diff')
    for key, value in parse_extra_vars(args.extra_vars).items():
        cmd.extend(['-e', f'{key}={value}'])
    if args.verbose:
        cmd.append('-' + 'v' * args.verbose)
    return cmd


class NasDeployCommand(Command):
    """
    Sync services/ to the NAS and run deploy.sh there (the same script CI uses)
    """
    name:        ClassVar[str]  = 'nas-deploy'
    group:       ClassVar[str]  = 'NAS'
    script_only: ClassVar[bool] = True

    class Args(argparse.Namespace):
        service: str        # positional arg "SERVICE"
        dry_run: bool       # --dry-run

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            'service',
            help="Directory under services/ to deploy, or 'all'",
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview the rsync and print the remote command without running it',
        )

    def run(self, args: Args) -> None:
        host, user = resolve_reachable_nas()
        warn_on_dirty_services()

        cmd: list[str] = ['bash', str(NAS_DEPLOY_SCRIPT)]
        if args.dry_run:
            cmd.append('--dry-run')
        cmd.append(args.service)

        sys.exit(
            shell_command(cmd, env={'NAS_HOST': host, 'NAS_USER': user}, check=False).returncode
        )


class NasProvisionCommand(Command):
    """
    Provision the NAS with the Ansible playbook: system config, the stow engine, then services
    """
    name:  ClassVar[str] = 'nas-provision'
    group: ClassVar[str] = 'NAS'

    class Args(argparse.Namespace):
        tags:       str | None          # --tags
        limit:      str | None          # --limit
        check:      bool                # --check
        diff:       bool                # --diff
        extra_vars: list[str] | None    # --extra-vars
        verbose:    int                 # --verbose

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            '--tags',
            metavar='TAGS',
            help=(
                'Only run tasks with these comma-separated tags\n'
                '(e.g. debian,dotfiles,haos,services,secrets)'
            ),
        )
        parser.add_argument(
            '--limit',
            metavar='HOSTS',
            help='Limit the run to these inventory hosts',
        )
        parser.add_argument(
            '--check',
            action='store_true',
            help='Predict changes without making them',
        )
        parser.add_argument(
            '--diff',
            action='store_true',
            help='Show file and template differences',
        )
        parser.add_argument(
            '-e',
            '--extra-vars',
            action='append',
            metavar='KEY=VALUE',
            help=(
                'Extra playbook variable (repeatable),\n'
                'e.g. -e dotfiles_repo_version=my-branch'
            ),
        )
        parser.add_argument(
            '-v',
            '--verbose',
            action='count',
            default=0,
            help='Increase Ansible verbosity (-v, -vv, ...)',
        )

    def run(self, args: Args) -> None:
        playbook_cmd = build_nas_provision_command(args)
        resolve_reachable_nas()

        printf('📦 Installing Ansible collections', fg='bright_cyan')
        galaxy = shell_command(
            [str(UV_PUBLIC), 'run', 'ansible-galaxy', 'collection', 'install', '-r', str(NAS_REQUIREMENTS)],
            check=False,
            cwd=DOTFILES_DIR,
        )
        if galaxy.returncode != 0:
            printf(
                '🟡 Collection install failed; continuing with the collections already installed',
                fg='bright_yellow',
            )

        sys.exit(
            shell_command(playbook_cmd, check=False, cwd=DOTFILES_DIR).returncode
        )


# ====================================================================================================
# Dotfiles commands
#
# Thin wrappers over the layered engine (stow.sh, bootstrap/bootstrap.sh, scripts/dotfiles/render.py)
# plus a doctor that checks tools, overlays, git version and hook shims, links, render drift, and Brewfile drift:
#   - bootstrap:    Run the layered bootstrap stages
#   - stow:         Link stow packages from every layer into $HOME
#   - render:       Render settings files from per-layer fragments
#   - track-claude: Ingest local ~/.claude agents/commands/skills/hooks/rules into the ``claude`` stow package
#   - doctor:       Verify the environment (``--fix`` confirms each repair, then re-checks; ``--yes`` skips the prompts)
#   - test:         Run the test suite through the public-index uv wrapper
# ====================================================================================================


@dataclasses.dataclass(frozen=True)
class DoctorCheck:
    """
    Result of one doctor check

    :param name: short check name
    :param ok: whether the check passed
    :param detail: one-line explanation
    :param fix: command that repairs the problem, if one exists
    """
    name:   str
    ok:     bool
    detail: str
    fix:    list[str] | None = None


def _capture(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    """
    Run a command quietly and capture its output (patched in tests)

    :param cmd: command and arguments
    :return: completed process with text stdout/stderr
    """
    return subprocess.run(cmd, capture_output=True, text=True, check=False, cwd=DOTFILES_DIR)


def _first_line(text: str, default: str) -> str:
    """
    Get the first non-empty line of command output with ANSI styling removed

    :param text: command output
    :param default: value returned when the output has no text
    :return: first non-empty line, or ``default``
    """
    for line in unstyle(text).splitlines():
        if line.strip():
            return line.strip()
    return default


def _probe_layers() -> subprocess.CompletedProcess[str]:
    """
    Ask bootstrap/lib.sh for the layer directories (base first), one per stdout line
    """

    # DOTFILES_REPO is pinned to this checkout so an inherited value from another one cannot redirect the base layer.
    # Anything lib.sh or a layer env.sh prints while loading goes to stderr so it cannot be counted as a layer.
    script = 'export DOTFILES_REPO="$1"; source "$1/bootstrap/lib.sh" >&2 && dotfiles_layers'
    return _capture(['bash', '-c', script, 'doctor', str(DOTFILES_DIR)])


def check_layers() -> DoctorCheck:
    """
    Check that every registered overlay exists
    """
    result = _probe_layers()
    if result.returncode != 0:
        return DoctorCheck('layers', False, _first_line(result.stderr, 'overlay registry error'))

    count = len([line for line in result.stdout.splitlines() if line])
    return DoctorCheck('layers', True, f'{count} layer(s): base + {count - 1} overlay(s)')


def check_hooks() -> DoctorCheck:
    """
    Check that prek's git hook shims are installed for every type in :data:`GIT_HOOK_TYPES`

    The ``pre-push`` shim runs the public-repo leak guard, so a checkout without it pushes unscanned.
    """
    result = _capture(['git', 'rev-parse', '--git-path', 'hooks'])
    if result.returncode != 0:
        return DoctorCheck('hooks', False, _first_line(result.stderr, 'not a git checkout'))

    # Relative to the repo root in a plain checkout; the absolute common-dir path inside a linked worktree
    hooks_dir = DOTFILES_DIR / result.stdout.strip()

    missing: list[str] = []
    for hook_type in GIT_HOOK_TYPES:
        try:
            installed = PREK_SHIM_MARKER in (hooks_dir / hook_type).read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError):
            installed = False
        if not installed:
            missing.append(hook_type)

    if not missing:
        return DoctorCheck('hooks', True, f'{len(GIT_HOOK_TYPES)} prek hook shims installed')

    detail = f'missing prek shims: {", ".join(missing)}'
    if shutil.which('prek') is None:
        return DoctorCheck('hooks', False, f'{detail} (prek not on PATH)')
    return DoctorCheck('hooks', False, detail, ['prek', 'install'])


def check_brewfiles() -> DoctorCheck:
    """
    Check that every layer's Brewfile is satisfied (``brew bundle check``)

    Homebrew has no lockfile, so ``brew bundle check`` is the reproducibility signal; bootstrap stage 50-brew runs the
    same probe while applying the Brewfiles.
    """
    if shutil.which('brew') is None:
        return DoctorCheck('brewfile', False, 'brew not found')

    layers = _probe_layers()
    if layers.returncode != 0:
        return DoctorCheck('brewfile', False, 'cannot enumerate layers (see the layers check)')

    brewfiles = [
        brewfile
        for line in layers.stdout.splitlines()
        if line and (brewfile := Path(line) / 'bootstrap' / 'Brewfile').is_file()
    ]
    if not brewfiles:
        return DoctorCheck('brewfile', True, 'no Brewfiles declared')

    drifted = [
        brewfile
        for brewfile in brewfiles
        if _capture(
            ['env', 'HOMEBREW_NO_AUTO_UPDATE=1', 'brew', 'bundle', 'check', '--file', str(brewfile)],
        ).returncode != 0
    ]
    if not drifted:
        return DoctorCheck('brewfile', True, f'{len(brewfiles)} Brewfile(s) satisfied')

    install = 'for brewfile in "$@"; do brew bundle --file "$brewfile" || exit 1; done'
    return DoctorCheck(
        'brewfile',
        False,
        f'unsatisfied: {", ".join(folduser(brewfile) for brewfile in drifted)}',
        ['bash', '-c', install, 'doctor', *(str(brewfile) for brewfile in drifted)],
    )


def check_links() -> DoctorCheck:
    """
    Check that stowing would change nothing
    """
    result = _capture(['bash', str(STOW_SCRIPT), '-n'])
    if (
        (result.returncode == 0) and
        (('stow: no changes' in result.stdout) or ('stow: no packages found' in result.stdout))
    ):
        return DoctorCheck('links', True, 'all packages linked')

    fix: list[str] = ['bash', str(STOW_SCRIPT), '--backup-conflicts']
    if result.returncode != 0:
        return DoctorCheck('links', False, _first_line(result.stderr or result.stdout, 'stow simulation failed'), fix)

    summary = next((line for line in result.stdout.splitlines() if re.match(r'stow: \d+ added', line)), '')
    return DoctorCheck('links', False, summary or 'stow reports pending changes', fix)


def check_render() -> DoctorCheck:
    """
    Check that rendered settings files match their fragments
    """
    result = _capture([sys.executable, str(RENDER_SCRIPT), '--check'])
    if result.returncode == 0:
        return DoctorCheck('render', True, 'rendered settings in sync')

    if result.returncode == 1:
        return DoctorCheck(
            'render',
            False,
            'rendered settings out of sync (see: run.py render --diff)',
            [sys.executable, str(RENDER_SCRIPT)],
        )

    # Exit 2 (or anything else): bad fragment/registry or I/O error, which re-rendering cannot repair
    return DoctorCheck('render', False, _first_line(result.stderr, f'render failed (exit {result.returncode})'))


def check_git_version() -> DoctorCheck:
    """
    Check that git supports ``includeIf "hasconfig:remote.*.url:..."`` (git >= 2.36)
    """
    result = _capture(['git', '--version'])
    match  = re.search(r'(\d+)\.(\d+)', result.stdout)
    if match is None:
        return DoctorCheck('git', False, 'could not determine git version')

    version = (int(match.group(1)), int(match.group(2)))
    want    = '.'.join(map(str, MIN_GIT_VERSION))
    return DoctorCheck(
        'git',
        version >= MIN_GIT_VERSION,
        f'git {version[0]}.{version[1]} (need >= {want} for per-remote identity)',
    )


def check_tools() -> DoctorCheck:
    """
    Check that required command-line tools are on PATH
    """
    if missing := [tool for tool in REQUIRED_TOOLS if shutil.which(tool) is None]:
        return DoctorCheck('tools', False, f'missing: {", ".join(missing)}')
    return DoctorCheck('tools', True, ', '.join(REQUIRED_TOOLS))


def doctor_checks() -> list[DoctorCheck]:
    """
    Run every doctor check (tools and layers first; the rest depend on them, and the slow Brewfile probe runs last)
    """
    first = [check_tools(), check_layers()]
    if not all(c.ok for c in first):
        return first
    return [*first, check_git_version(), check_hooks(), check_links(), check_render(), check_brewfiles()]


class DoctorCommand(Command):
    """
    Check tools, overlays, git version and hooks, links, rendered settings, and Brewfiles
    """
    name:  ClassVar[str] = 'doctor'
    group: ClassVar[str] = 'Dotfiles'

    class Args(argparse.Namespace):
        fix: bool       # --fix
        yes: bool       # --yes

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            '-f',
            '--fix',
            action='store_true',
            help=(
                'Ask before fixing each failing check, then re-check. The fixes are:\n'
                '  hooks:    prek install\n'
                '  links:    stow.sh --backup-conflicts (moves blocking files into\n'
                '            ~/.dotfiles-backup/<timestamp>/)\n'
                '  render:   render.py (without --force)\n'
                '  brewfile: brew bundle --file for each unsatisfied Brewfile'
            ),
        )
        parser.add_argument(
            '-y',
            '--yes',
            action='store_true',
            help='Apply fixes without prompting for confirmation (implies --fix)',
        )

    def run(self, args: Args) -> None:
        checks = doctor_checks()

        if args.fix or args.yes:
            for check in checks:
                if check.ok or not check.fix:
                    continue

                command  = shlex.join(check.fix)
                question = f'Run {style(command, fg="bright_magenta")} to fix {style(check.name, bold=True)}?'
                if not args.yes and not confirm(question, indent=3):
                    printf(f'Skipped {check.name}', dim=True, indent=3)
                    continue

                printf(f'🔧 {check.name}: {command}', fg='bright_cyan')
                shell_command(check.fix, indent=3, check=False)
            checks = doctor_checks()

        for check in checks:
            emoji = '🟢' if check.ok else '🔴'
            printf(f'{emoji} {style(check.name, fg="white", bold=True)}  {check.detail}', indent=3)

        if not all(check.ok for check in checks):
            sys.exit(ExitCode.COMMAND_FAILED)


class BootstrapCommand(Command):
    """
    Run the layered bootstrap stages (bootstrap/bootstrap.sh)
    """
    name:  ClassVar[str] = 'bootstrap'
    group: ClassVar[str] = 'Dotfiles'

    class Args(argparse.Namespace):
        dry_run:    bool            # --dry-run
        list:       bool            # --list
        only:       str | None      # --only
        from_stage: str | None      # --from
        resume:     bool            # --resume
        verify:     bool            # --verify
        no_log:     bool            # --no-log

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simulate every stage',
        )
        parser.add_argument(
            '--list',
            action='store_true',
            help='List stages across layers',
        )
        parser.add_argument(
            '--only',
            metavar='STAGE',
            help='Run a single stage',
        )
        parser.add_argument(
            '--from',
            dest='from_stage',
            metavar='STAGE',
            help='Run from STAGE onward',
        )
        parser.add_argument(
            '--resume',
            action='store_true',
            help='Continue after the last completed stage',
        )
        parser.add_argument(
            '--verify',
            action='store_true',
            help='Run doctor after all stages succeed',
        )
        parser.add_argument(
            '--no-log',
            action='store_true',
            help='Do not tee output to the bootstrap log',
        )

    def run(self, args: Args) -> None:
        cmd: list[str] = ['bash', str(BOOTSTRAP_SCRIPT)]
        for flag, enabled in (
            ('--dry-run', args.dry_run),
            ('--list',    args.list),
            ('--resume',  args.resume),
            ('--verify',  args.verify),
            ('--no-log',  args.no_log),
        ):
            if enabled:
                cmd.append(flag)

        if args.only:
            cmd.extend(['--only', args.only])
        if args.from_stage:
            cmd.extend(['--from', args.from_stage])

        sys.exit(
            shell_command(cmd, check=False).returncode
        )


class StowCommand(Command):
    """
    Link stow packages from every layer into the home directory (stow.sh)
    """
    name:  ClassVar[str] = 'stow'
    group: ClassVar[str] = 'Dotfiles'

    class Args(argparse.Namespace):
        packages:         list[str]     # positional arg(s) "PACKAGES"
        simulate:         bool          # --simulate
        backup_conflicts: bool          # --backup-conflicts
        verbose:          bool          # --verbose

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            'packages',
            nargs='*',
            help='Packages to stow (default: all, across layers)',
        )
        parser.add_argument(
            '-n',
            '--simulate',
            action='store_true',
            help='Preview without changing $HOME',
        )
        parser.add_argument(
            '--backup-conflicts',
            action='store_true',
            help='Move blocking files to ~/.dotfiles-backup',
        )
        parser.add_argument(
            '-v',
            '--verbose',
            action='store_true',
            help='Show the raw stow log',
        )

    def run(self, args: Args) -> None:
        cmd: list[str] = ['bash', str(STOW_SCRIPT)]
        if args.simulate:
            cmd.append('-n')
        if args.backup_conflicts:
            cmd.append('--backup-conflicts')
        if args.verbose:
            cmd.append('--verbose')

        sys.exit(
            shell_command([*cmd, *args.packages], check=False).returncode,
        )


class RenderCommand(Command):
    """
    Render settings files from per-layer fragments (scripts/dotfiles/render.py)
    """
    name:  ClassVar[str] = 'render'
    group: ClassVar[str] = 'Dotfiles'

    class Args(argparse.Namespace):
        targets: list[str]      # positional arg(s) "TARGETS"
        diff:    bool           # --diff
        check:   bool           # --check
        force:   bool           # --force
        verbose: bool           # --verbose

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            'targets',
            nargs='*',
            help='Targets (default: all)',
        )
        parser.add_argument(
            '--diff',
            action='store_true',
            help='Preview differences; write nothing',
        )
        parser.add_argument(
            '--check',
            action='store_true',
            help='Exit 1 if out of sync; write nothing',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Overwrite in-app edits after backing them up',
        )
        parser.add_argument(
            '-v',
            '--verbose',
            action='store_true',
            help='Report skipped/current targets',
        )

    def run(self, args: Args) -> None:
        cmd: list[str] = [sys.executable, str(RENDER_SCRIPT), *args.targets]
        for flag, enabled in (
            ('--diff',  args.diff),
            ('--check', args.check),
            ('--force', args.force),
            ('-v',      args.verbose),
        ):
            if enabled:
                cmd.append(flag)

        sys.exit(
            shell_command(cmd, check=False).returncode,
        )


def find_untracked_claude_files() -> list[Path]:
    """
    Find real (non-symlink) files under the tracked ``~/.claude`` subdirectories

    Stowed agents/commands/skills/hooks/rules are symlinks into the repo, so any regular file is something Claude Code
    or the user created locally that the ``claude`` stow package does not have yet. Symlinked directories are never
    descended into, and a tracked subdirectory that is itself a symlink is skipped, so repo files reached through a
    link are never mistaken for local ones.

    :return: sorted absolute paths of untracked files
    """
    untracked: list[Path] = []
    for subdir in CLAUDE_TRACKED_SUBDIRS:
        base = CLAUDE_CONFIG_DIR / subdir
        if base.is_symlink() or not base.is_dir():
            continue

        for dirpath, _dirnames, filenames in os.walk(base):
            for filename in filenames:
                if filename in CLAUDE_IGNORE_NAMES:
                    continue

                path = Path(dirpath) / filename
                if not path.is_symlink():
                    untracked.append(path)

    return sorted(untracked)


class TrackClaudeCommand(Command):
    """
    Ingest new ~/.claude agents, commands, skills, hooks, and rules into the repo
    """
    name:  ClassVar[str] = 'track-claude'
    group: ClassVar[str] = 'Dotfiles'

    class Args(argparse.Namespace):
        dry_run: bool       # --dry-run

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            '-n',
            '--dry-run',
            action='store_true',
            help='Preview what would be ingested without moving anything',
        )

    def run(self, args: Args) -> None:
        untracked = find_untracked_claude_files()
        if not untracked:
            printf('✅ Nothing to track: everything under ~/.claude is already in the repo', fg='bright_green')
            return

        printf(
            f'Found {len(untracked)} untracked file(s) under {folduser(CLAUDE_CONFIG_DIR)}:',
            bold=True,
            fg='bright_white',
        )

        # Plan moves: src (real file in ~/.claude) -> dst (mirrored path in the stow package). Any existing directory
        # entry at dst (even a dangling symlink, which exists() reports as absent) is a conflict: the repo has
        # something there and it is left untouched.
        moves:     list[tuple[Path, Path]] = []
        conflicts: list[Path]              = []
        for src in untracked:
            rel = src.relative_to(CLAUDE_CONFIG_DIR)
            dst = CLAUDE_STOW_DIR / rel
            if os.path.lexists(dst):
                conflicts.append(rel)
                printf(f'{style("CONFLICT", fg="red")}  {rel}', indent=2)
            else:
                moves.append((src, dst))
                printf(f'{style("→ repo", fg="green")}  {rel}', indent=2)

        if conflicts:
            printf('')
            printf(f'🟡 {len(conflicts)} file(s) already exist in the repo; skipped (resolve manually)', fg='yellow')
            if moves:
                printf('Restow will be skipped: the conflicting local files would block stow', fg='yellow', indent=3)

        if not moves:
            printf('')
            printf('Nothing to move.', fg='yellow')
            return

        # stow.sh aborts without changing anything if a regular file blocks a link, so any conflict rules out the restow
        scope = f'{len(moves)} file(s) into the repo' + ('' if conflicts else ' and restow')
        if args.dry_run:
            printf('')
            printf(f'Dry run: would move {scope}. No changes made.', fg='cyan')
            return

        printf('')
        if not confirm(f'Move {scope}?'):
            printf('⚠️  Cancelled', fg='yellow')
            return

        moved = 0
        for src, dst in moves:
            rel = src.relative_to(CLAUDE_CONFIG_DIR)

            # Re-check right before moving: shutil.move silently replaces an existing destination (rename semantics),
            # and the repo may have changed since planning
            if os.path.lexists(dst):
                conflicts.append(rel)
                printf(f'{style("CONFLICT", fg="red")}  {rel}', indent=2)
                continue

            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            moved += 1
            printf(f'└─ {rel}', fg='green')

        if conflicts:
            printf('')
            printf(
                f'🟡 Moved {moved} file(s) into the repo; restow skipped: {len(conflicts)} conflicting local file(s) '
                f'would block stow',
                fg='yellow',
                bold=True,
            )
            printf('Next steps:', fg='bright_white', bold=True)
            printf('1. Resolve the conflicts above (diff/merge, or delete the local copies)', indent=3)
            printf(
                f'2. Run {style("python3 run.py stow claude", fg="bright_magenta")} '
                f'(add {style("--backup-conflicts", fg="yellow")} to move the blocking local files to '
                f'~/.dotfiles-backup/<timestamp>/ instead)',
                indent=3,
            )
            printf(
                f'3. Review and commit: {style("git add stow/claude/.claude && git commit", fg="bright_magenta")}',
                indent=3,
            )
            return

        # The source paths are vacant now, so a plain restow links the moved files back in without conflicts
        printf('')
        printf('🔗 Restowing claude package...', fg='bright_cyan')
        try:
            shell_command(['bash', str(STOW_SCRIPT), 'claude'], indent=3)
        except subprocess.CalledProcessError:
            printf('❌ Restow failed: files moved into the repo, but symlinks may be incomplete', fg='red', bold=True)
            printf(f'Re-run: {style("python3 run.py stow claude", fg="bright_magenta")}', indent=3)
            sys.exit(ExitCode.COMMAND_FAILED)

        printf('')
        printf(f'✅ Ingested {moved} file(s). Review and commit them:', fg='bright_green', bold=True)
        printf(style('git add stow/claude/.claude && git commit', fg='bright_magenta'), indent=3)


class TestCommand(Command):
    """
    Run the test suite via uv (public-index wrapper)
    """
    name:  ClassVar[str] = 'test'
    group: ClassVar[str] = 'Dotfiles'

    class Args(argparse.Namespace):
        paths: list[str]        # positional arg(s) "PATHS"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            'paths',
            nargs='*',
            help='Test paths (default: tests/)',
        )

    def run(self, args: Args) -> None:
        sys.exit(
            shell_command(
                [str(UV_PUBLIC), 'run', '--group', 'test', 'pytest', *(args.paths or ['tests'])],
                check=False,
            ).returncode,
        )


# ====================================================================================================
# Command-line argument parsing / entry point
#
# build_parser() creates the root parser (help text organized by command group, plus Debug Options and Other Options
# groups) and one subparser per registered Command, each with its -h/--help in a trailing "Other options" group.
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


def build_parser() -> argparse.ArgumentParser:
    """
    Build argument parser

    :return: :class:`argparse.ArgumentParser`
    """

    # Build root parser
    parser = argparse.ArgumentParser(
        description=build_parser_help_text(),
        formatter_class=get_default_help_formatter_cls(),
        add_help=False,
    )

    def add_subcommand_parsers() -> None:
        """
        Register all command subparsers from the ``REGISTERED_COMMANDS`` registry
        """
        subparsers = parser.add_subparsers(
            dest='command',
            metavar='COMMAND',
            help=argparse.SUPPRESS,
        )
        for cmd_name, cmd in REGISTERED_COMMANDS.items():
            subparser = subparsers.add_parser(
                cmd_name,
                description=cmd.description or f'Run {cmd_name} command',
                help=cmd.description        or f'Run {cmd_name} command',
                epilog=cmd.epilog,
                formatter_class=cmd.help_formatter_type,
                add_help=False,
            )
            cmd.add_arguments(subparser)
            if cmd.add_help:
                cmd_other_opts = subparser.add_argument_group('Other options')
                cmd_other_opts.add_argument(
                    '-h',
                    '--help',
                    action='help',
                    default=argparse.SUPPRESS,
                    help='Show this help message and exit',
                )
    add_subcommand_parsers()

    def add_debug_opts() -> None:
        """
        Add the debug argument group to the root parser
        """
        debug_opts = parser.add_argument_group(
            title=style('Debug Options', fg='bright_white', bold=True),
        )
        debug_opts.add_argument(
            '-d',
            '--debug',
            action=argparse.BooleanOptionalAction,
            dest='debug',
            default=RUN_DEBUG,
            help=' '.join([
                'Enable script debug logging          ',
                arg_note('env var', RUN_DEBUG_ENVVAR) + '   ',
                arg_note(
                    'default',
                    repr(RUN_DEBUG),
                    color='bright_green' if RUN_DEBUG else 'bright_red',
                ),
            ]),
        )

        # Remove extra default value string from options w/ `action=BooleanOptionalAction` (automatically added somehow)
        for option in debug_opts._group_actions:
            if option.help:
                option.help = option.help.split('(default: ', 1)[0]
    add_debug_opts()

    def add_other_opts() -> None:
        """
        Add the help option and other miscellaneous options group to the root parser
        """
        other_opts = parser.add_argument_group(
            title=style('Other Options', fg='bright_white', bold=True),
        )
        other_opts.add_argument(
            '-h',
            '--help',
            action='help',
            default=argparse.SUPPRESS,
            help='Show this help message and exit',
        )
    add_other_opts()

    return parser


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

    # Apply -d/--debug/--no-debug (defaults to the DOTFILES_RUN_DEBUG value, so this can also turn debug off)
    RUN_DEBUG = args.debug

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


if __name__ == '__main__':
    main()
