#!/usr/bin/env python3
"""
run.py - CLI interface for Connor's personal dotfiles repository

This script provides a command-line interface for managing the dotfiles repository,
including inventory management, tool installation, and codebase maintenance tasks.

Architecture
-----------
The script uses a decorator-based command registration system (@command) that:
- Automatically builds argparse subparsers from registered functions
- Organizes commands by group for help text
- Supports generating Makefile targets from registered commands
- Allows commands to be script-only or makefile-only

Command Categories
-----------------
- **Inventory**: Manage the standalone inventory git repository
- **Tool Installation**: Install Python tooling (uv, hatch) with retry logic
- **Codebase**: Clean build artifacts, run pre-commit hooks, generate Makefile

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
- .claude/CLAUDE.md: Architecture and development guidance
"""
from __future__ import annotations

import argparse
import inspect
import os
import pty
import re
import shlex
import shutil
import subprocess
import sys
import textwrap
import time
from dataclasses import dataclass
from functools import partial
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from typing import Callable
from typing import Literal
from typing import TypeVar
from typing import Union
from typing import cast
from typing import overload

if TYPE_CHECKING:
    from collections.abc import Iterable


# TODO: some commands have dependency on `yaml`. Maybe we should add `uv` metadata to top of script?


"""
Constants/configuration
"""


# Filepaths - All absolute paths relative to script location
SCRIPT_PATH:    Path = Path(__file__)
DOTFILES_DIR:   Path = SCRIPT_PATH.parent
MAKEFILE_PATH:  Path = DOTFILES_DIR / 'Makefile'
INVENTORY_DIR:  Path = DOTFILES_DIR / 'inventory'  # Standalone git clone (not submodule)
INVENTORY_FILE: Path = INVENTORY_DIR / 'inventory.yml'
PLAYBOOKS_DIR:  Path = DOTFILES_DIR / 'playbooks'
SCRIPTS_DIR:    Path = DOTFILES_DIR / 'scripts'

# Environment variables - All prefixed with DOTFILES_ namespace
ENVVAR_PREFIX:             str = 'DOTFILES'
RUN_DEBUG_ENVVAR:          str = f'{ENVVAR_PREFIX}_RUN_DEBUG'
INVENTORY_REPO_URL_ENVVAR: str = f'{ENVVAR_PREFIX}_INVENTORY_REPO_URL'

RUN_DEBUG:          bool = os.getenv(RUN_DEBUG_ENVVAR, 'false').lower() == 'true'
INVENTORY_REPO_URL: str  = os.getenv(
    INVENTORY_REPO_URL_ENVVAR,
    'git@github.com:connormason/dotfiles-inventory.git',
)

# Other static configuration
# Patterns for files/directories to remove during cleanup
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
}


"""
Basic types
"""


F = TypeVar('F', bound=Callable[..., Any])

PathLike         = Union[str, Path]
StyleColor       = Union[int, tuple[int, int, int], str]
CommandFunc      = Callable[[argparse.Namespace],      None]
AddArgumentsFunc = Callable[[argparse.ArgumentParser], None]


"""
Command registration

The @command decorator provides a declarative way to register command functions:
- Extracts command name from function name (strips 'cmd_' or 'command_' prefix)
- Automatically builds argparse subparsers with help text from docstrings
- Supports optional argument addition via add_arguments callback
- Allows grouping commands for organized help text
- Enables filtering commands for script-only or Makefile-only visibility

Example:
    @command(group='Inventory', add_arguments=add_custom_args)
    def cmd_update_inventory(args: argparse.Namespace) -> None:
        '''Update inventory from remote repository'''
        # Implementation here
"""


@dataclass
class CommandInfo:
    name:            str
    func:            CommandFunc
    add_arguments:   AddArgumentsFunc | None      = None
    description:     str | None                   = None
    epilog:          str | None                   = None
    formatter_class: type[argparse.HelpFormatter] = argparse.RawDescriptionHelpFormatter
    group:           str | None                   = None
    script_only:     bool                         = False
    makefile_only:   bool                         = False


REGISTERED_COMMANDS: dict[str, CommandInfo] = {}


@overload
def command(func_or_name: CommandFunc) -> CommandFunc: ...

@overload
def command(
    *,
    name: str | None = None,
    add_arguments: AddArgumentsFunc | None = None,
    description: str | None = None,
    epilog: str | None = None,
    formatter_class: type[argparse.HelpFormatter] = argparse.RawDescriptionHelpFormatter,
    group: str | None = None,
    script_only: bool = False,
    makefile_only: bool = False,
) -> Callable[[CommandFunc], CommandFunc]: ...

def command(
    func_or_name: CommandFunc | str | None = None,
    *,
    name: str | None = None,
    add_arguments: AddArgumentsFunc | None = None,
    description: str | None = None,
    epilog: str | None = None,
    formatter_class: type[argparse.HelpFormatter] = argparse.RawDescriptionHelpFormatter,
    group: str | None = None,
    script_only: bool = False,
    makefile_only: bool = False,
) -> Callable[[CommandFunc], CommandFunc] | CommandFunc:
    """
    Decorator to register a function as a command

    :param func_or_name: function to decorate (when used without parens) or command name
    :param name: command name
    :param add_arguments: optional function to add command-specific arguments to the subparser
    :param description: command description (defaults to docstring of wrapped function)
    :param epilog: command parser epilog
    :param formatter_class: :class:`argparse.HelpFormatter` for command subparser
    :param group: command group name for help organization
    :param script_only: if True, don't include command in Makefile targets generated by `makefile` command
    :param makefile_only: if True, don't include command in help text of script when called directly
    :return: decorated function or decorator function
    """
    if script_only and makefile_only:
        raise ValueError('Only one of `script_only` and `makefile_only` may be True')

    def decorator(func: CommandFunc) -> CommandFunc:
        if name is not None:
            cmd_name = name
        elif isinstance(func_or_name, str):
            cmd_name = func_or_name
        else:
            cmd_name = func.__name__.removeprefix('cmd_').removeprefix('command_').replace('_', '-')

        REGISTERED_COMMANDS[cmd_name] = CommandInfo(
            name=cmd_name,
            func=func,
            add_arguments=add_arguments,
            description=description or inspect.getdoc(func),
            epilog=epilog,
            formatter_class=formatter_class,
            group=group,
            script_only=script_only,
            makefile_only=makefile_only,
        )
        return func

    if callable(func_or_name):
        return decorator(func_or_name)
    return decorator


def get_command_functions() -> dict[str, CommandFunc]:
    """
    Get all registered command functions

    :return: mapping from command name -> command func
    """
    return {name: cmd_info.func for name, cmd_info in REGISTERED_COMMANDS.items()}


def get_command_groups(exclude: Iterable[str] | None = None) -> dict[str, dict[str, CommandInfo]]:
    """
    Get command info by associated group

    :param exclude: command names to exclude
    :return: mapping from group name -> command name -> :class:`CommandInfo`
    """
    exclude_cmds: set[str] = set(exclude) if exclude is not None else set()

    command_groups: dict[str, dict[str, CommandInfo]] = {}
    for cmd_name, cmd_info in REGISTERED_COMMANDS.items():
        if cmd_name not in exclude_cmds:
            group_name = cmd_info.group or 'Other commands'
            command_groups.setdefault(group_name, {})[cmd_name] = cmd_info

    return command_groups


"""
Formatting

ANSI styling functions for terminal output. The style() function is inspired by Click's
style implementation but standalone (no external dependencies). Supports:
- Foreground/background colors (named, 256-color palette, RGB tuples)
- Text attributes (bold, dim, italic, underline, etc.)
- Auto-reset by default to prevent style leakage

The printf() function wraps style() for common use cases and supports:
- Debug mode filtering (only prints if RUN_DEBUG=true)
- Text indentation
- Automatic text-to-str conversion
"""


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
    Styles a text with ANSI styles and returns the new string. By default, the styling is self-contained. This means
    that at the end of the string, a reset code is issued. This can be prevented by passing ``reset=False``

    Examples::

        print(style('Hello World!', fg='green'))
        print(style('ATTENTION!', blink=True))
        print(style('Some things', reverse=True, fg='cyan'))
        print(style('More colors', fg=(255, 12, 128), bg=117))

    :param text: the string to style with ansi codes
    :param fg: if provided this will become the foreground color
    :param bg: if provided this will become the background color
    :param bold: if provided this will enable or disable bold mode
    :param dim: if provided this will enable or disable dim mode. This is badly supported
    :param underline: if provided this will enable or disable underline
    :param overline: if provided this will enable or disable overline
    :param italic: if provided this will enable or disable italic
    :param blink: if provided this will enable or disable blinking
    :param reverse: if provided this will enable or disable inverse rendering (foreground becomes background and the
                    other way round)
    :param strikethrough: if provided this will enable or disable striking through text
    :param reset: by default a reset-all code is added at the end of the string which means that styles do not carry
                  over. This can be disabled to compose styles
    :raises TypeError: if invalid fg/bg color requested
    :return: styled text
    """
    _ansi_colors: dict[str, int] = {
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
    _ansi_reset_all = '\033[0m'

    def _interpret_color(_color: StyleColor, offset: int = 0) -> str:
        if isinstance(_color, int):
            return f'{38 + offset};5;{_color:d}'
        elif isinstance(_color, (tuple, list)):
            r, g, b = _color
            return f'{38 + offset};2;{r:d};{g:d};{b:d}'
        else:
            _color = cast('str', _color)
            return str(_ansi_colors[_color] + offset)

    if not isinstance(text, str):
        text = str(text)

    bits: list[str] = []
    if fg:
        try:
            bits.append(f'\033[{_interpret_color(fg)}m')
        except KeyError:
            raise TypeError(f'Unknown color {fg!r}') from None

    if bg:
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
        bits.append(_ansi_reset_all)
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
) -> None:
    if debug and not RUN_DEBUG:
        return
    elif debug:
        fg = fg if fg is not None else 'bright_white'
        dim = dim if dim is not None else True

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
        )
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


"""
Command utils

Subprocess execution with enhanced error handling and output formatting.

The shell_command() function provides two execution modes:
1. capture_output=True: Captures stdout/stderr for programmatic use
2. capture_output=False with indent: Streams output live via pty with indentation

Key features:
- Automatic environment variable injection (RUN_COMMAND_ENVVARS)
- SSH error detection with helpful troubleshooting suggestions
- Timeout support with graceful degradation
- Custom ShellCommandError with formatted output
"""


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


def detect_ssh_error(e: subprocess.CalledProcessError) -> tuple[bool, str | None]:
    """
    Detect SSH-related errors from git command output

    :param e: subprocess exception
    :return: tuple of (is_ssh_error, specific_error_type)
    """
    stderr_text = ''
    if e.stderr:
        stderr_text = e.stderr if isinstance(e.stderr, str) else e.stderr.decode()

    stdout_text = ''
    if e.stdout:
        stdout_text = e.stdout if isinstance(e.stdout, str) else e.stdout.decode()

    combined = f'{stderr_text}\n{stdout_text}'.lower()

    # Check for various SSH error patterns
    ssh_patterns = {
        'permission_denied': 'permission denied (publickey)',
        'host_key_verification': 'host key verification failed',
        'no_identities': 'no such identity',
        'key_load_failed': 'load key',
        'connection_refused': 'connection refused',
        'connection_timeout': 'connection timed out',
        'unknown_host': 'could not resolve hostname',
    }

    for error_type, pattern in ssh_patterns.items():
        if pattern in combined:
            return True, error_type

    # Generic SSH detection
    if any(indicator in combined for indicator in ['ssh:', '@github.com', 'publickey', 'git@']):
        return True, 'generic'

    return False, None


def handle_command_error(e: subprocess.CalledProcessError, context: str, suggestion: str | None = None) -> None:
    """
    Format and display subprocess errors with context.

    :param e: subprocess exception
    :param context: description of what operation failed
    :param suggestion: optional helpful suggestion for fixing the issue
    """
    printf(f'❌ {context}',                      fg='red', bold=True)
    printf(f'  └─ Exit code: {e.returncode}',    fg='red', indent=1)
    printf(f'  └─ Command: {shlex.join(e.cmd)}', fg='red', indent=1)

    if e.stderr:
        stderr_text = e.stderr if isinstance(e.stderr, str) else e.stderr.decode()
        printf('  └─ Error output:', fg='red', indent=1)
        for line in stderr_text.strip().split('\n')[:10]:
            printf(f'     {line}',   fg='red', indent=1)

    # Check for SSH-specific errors and provide tailored suggestions
    is_ssh_error, ssh_error_type = detect_ssh_error(e)
    if is_ssh_error and ssh_error_type:
        printf('  └─ 🔑 SSH Authentication Issue Detected', fg='yellow', bold=True, indent=1)

        if ssh_error_type == 'permission_denied':
            printf('  └─ 💡 Your SSH key is not authorized for this repository', fg='yellow', indent=1)
            printf('     Try these steps:', fg='yellow', indent=1)
            printf('     1. Check if SSH key exists: ls -la ~/.ssh/', fg='yellow', indent=1)
            printf('     2. Generate new key if needed: ssh-keygen -t ed25519 -C "your_email@example.com"', fg='yellow', indent=1)
            printf('     3. Add key to ssh-agent: ssh-add ~/.ssh/id_ed25519', fg='yellow', indent=1)
            printf('     4. Add public key to GitHub: https://github.com/settings/keys', fg='yellow', indent=1)
            printf('     5. Test connection: ssh -T git@github.com', fg='yellow', indent=1)

        elif ssh_error_type == 'host_key_verification':
            printf('  └─ 💡 GitHub host key not recognized', fg='yellow', indent=1)
            printf('     Run: ssh-keyscan github.com >> ~/.ssh/known_hosts', fg='yellow', indent=1)

        elif ssh_error_type in ('no_identities', 'key_load_failed'):
            printf('  └─ 💡 SSH key could not be loaded', fg='yellow', indent=1)
            printf('     Run: ssh-add ~/.ssh/id_ed25519 (or your key path)', fg='yellow', indent=1)

        elif ssh_error_type == 'connection_refused':
            printf('  └─ 💡 SSH connection refused', fg='yellow', indent=1)
            printf('     Check network connectivity and firewall settings', fg='yellow', indent=1)

        elif ssh_error_type == 'connection_timeout':
            printf('  └─ 💡 SSH connection timed out', fg='yellow', indent=1)
            printf('     Check network connectivity and try again', fg='yellow', indent=1)

        elif ssh_error_type == 'unknown_host':
            printf('  └─ 💡 Could not resolve hostname', fg='yellow', indent=1)
            printf('     Check your internet connection and DNS settings', fg='yellow', indent=1)

        else:  # generic SSH error
            printf('  └─ 💡 Try testing SSH connection: ssh -T git@github.com', fg='yellow', indent=1)

    elif suggestion:
        printf(f'  └─ 💡 {suggestion}', fg='yellow', indent=1)


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
    env: dict[str, str] | None = ...,
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
    env: dict[str, str] | None = ...,
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
    env: dict[str, str] | None = ...,
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
    env: dict[str, str] | None = None,
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
            raise ShellCommandError(e.returncode, shlex.join(cmd), output=e.output, stderr=e.stderr)
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
        try:
            while True:
                output = os.read(master_fd, 1024).decode()
                if not output:
                    break

                buffer += output
                all_output += output
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    print(f'{indent_str}{line}')

            if buffer:
                print(f'{indent_str}{buffer}', end='')
        except Exception:
            raise
        finally:
            os.close(master_fd)
            try:
                returncode = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                printf(f'❌ Command timed out after {timeout}s', fg='red', bold=True, indent=indent or 0)
                printf(f'  └─ Command: {shlex.join(cmd)}',        fg='red',           indent=(indent or 0) + 1)
                if check:
                    raise
                return subprocess.CompletedProcess(cmd, -1, stdout=all_output)

        if check and (returncode != 0):
            raise ShellCommandError(returncode, shlex.join(cmd), stderr=all_output)
        else:
            return subprocess.CompletedProcess(cmd, returncode, stdout=all_output)


"""
Other utility functions

Includes:
- retry_on_failure: Decorator for exponential backoff retry logic
- parse_extra_vars: Parse ansible-playbook -e key=value arguments
"""


def retry_on_failure(
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
                            f'  └─ Attempt {attempt}/{max_attempts} failed, '
                            f'retrying in {wait_time:.1f}s...',
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
                sys.exit(1)

            key, value = var_str.split('=', 1)
            extra_vars[key.strip()] = value.strip()

    return extra_vars


"""
Bootstrap commands
"""


# TODO: implement bootstrap command(s)


"""
Inventory commands

Commands for managing the standalone inventory git repository.

The inventory is NOT a git submodule - it's a separate repository cloned into
the inventory/ directory by run.py. This approach simplifies the mental model
for personal dotfiles usage.

Key commands:
- list-hosts: Parse inventory.yml and display available bootstrap targets
- inventory-status: Show git status and metadata for inventory directory
- update-inventory: Clone (if missing) or pull (if exists) inventory repo
  - Supports --force flag to reset uncommitted changes before pulling
  - Includes retry logic with exponential backoff for network resilience
  - Provides SSH error detection and troubleshooting guidance
"""


@command(group='Inventory')
def cmd_list_hosts(args: argparse.Namespace) -> None:
    """
    List available bootstrap targets from inventory
    """
    printf('Available Bootstrap Targets', bold=True, fg='bright_white')
    printf('=' * 60,                      bold=True)

    # Check that inventory file exists
    if not INVENTORY_FILE.exists():
        printf('')
        printf('❌ Inventory file not found', fg='red', bold=True)
        printf(f'   Expected: {folduser(INVENTORY_FILE)}',                                 indent=3)
        printf(f'   Run: {style("python3 run.py update-inventory", fg="bright_magenta")}', indent=3)
        sys.exit(1)

    # Parse inventory file
    try:
        import yaml
        with INVENTORY_FILE.open() as f:
            inventory = yaml.safe_load(f)
    except Exception as e:
        printf('')
        printf('❌ Failed to parse inventory file', fg='red', bold=True)
        printf(f'   Error: {e}', indent=3)
        sys.exit(1)

    # Display all groups and hosts
    if (not inventory) or ('all' not in inventory):
        printf('')
        printf('⚠️  No hosts found in inventory', fg='yellow')
        sys.exit(0)

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


@command(group='Inventory')
def cmd_inventory_status(args: argparse.Namespace) -> None:
    """
    Display current status of inventory directory
    """
    printf('Inventory Status', bold=True, fg='bright_white')
    printf('=' * 60, bold=True)
    printf('')

    # Check if inventory directory exists
    if not INVENTORY_DIR.exists():
        printf('Status:   ', fg='bright_white', bold=True, reset=False)
        printf('Not found', fg='red', bold=True)
        printf(f'Path:     {folduser(INVENTORY_DIR)}', dim=True)
        printf('')
        printf(f'💡 Run {style("python3 run.py update-inventory", fg="bright_magenta")} to clone the inventory', fg='yellow')
        return

    printf('Status:   ', fg='bright_white', bold=True, reset=False)
    printf('Found', fg='green', bold=True)
    printf(f'Path:     {folduser(INVENTORY_DIR)}', dim=True)
    printf('')

    # Check if it's a git repository
    git_dir = INVENTORY_DIR / '.git'
    if not git_dir.exists():
        printf('Type:     ', fg='bright_white', bold=True, reset=False)
        printf('Not a git repository', fg='yellow', bold=True)
        printf('')
        printf('⚠️  Inventory exists but is not a git repository', fg='yellow')
        printf(f'   Run {style("python3 run.py update-inventory", fg="bright_magenta")} to fix', indent=3)
        return

    printf('Type:     ', fg='bright_white', bold=True, reset=False)
    printf('Git repository', fg='green', bold=True)
    printf('')

    # Get git remote information
    try:
        result = shell_command(
            ['git', 'remote', 'get-url', 'origin'],
            cwd=INVENTORY_DIR,
            capture_output=True,
        )
        remote_url = result.stdout.strip()
        printf('Remote:   ', fg='bright_white', bold=True, reset=False)
        printf(remote_url, fg='cyan')
    except subprocess.CalledProcessError:
        printf('Remote:   ', fg='bright_white', bold=True, reset=False)
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
        printf(branch, fg='cyan')
    except subprocess.CalledProcessError:
        printf('Branch:   ', fg='bright_white', bold=True, reset=False)
        printf('Unknown', fg='yellow')

    # Get last commit info
    try:
        result = shell_command(
            ['git', 'log', '-1', '--format=%h - %s (%cr)'],
            cwd=INVENTORY_DIR,
            capture_output=True,
        )
        last_commit = result.stdout.strip()
        printf('Commit:   ', fg='bright_white', bold=True, reset=False)
        printf(last_commit, dim=True)
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
        printf(' Found', fg='green', bold=True)
        printf(f'   {folduser(INVENTORY_FILE)}', dim=True, indent=3)
    else:
        printf('Inventory file:', fg='bright_white', bold=True, reset=False)
        printf(' Not found', fg='red', bold=True)
        printf(f'   Expected: {folduser(INVENTORY_FILE)}', dim=True, indent=3)


def add_update_inventory_arguments(parser: argparse.ArgumentParser) -> None:
    """
    Add arguments for update-inventory command

    :param parser: argument parser
    """
    parser.add_argument(
        '-f',
        '--force',
        action='store_true',
        help='Force update by discarding any uncommitted local changes',
    )


@command(group='Inventory', add_arguments=add_update_inventory_arguments)
def cmd_update_inventory(args: argparse.Namespace) -> None:
    """
    Update inventory repo
    """
    printf('🔄 Updating inventory...', fg='bright_white')

    @retry_on_failure(max_attempts=3, delay=2.0, backoff=2.0)
    def pull_inventory_repo(**kwargs: Any) -> subprocess.CompletedProcess:
        # If --force flag provided, reset any uncommitted changes before pulling
        if args.force:
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
                pass  # Continue with pull anyway

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

    @retry_on_failure(max_attempts=3, delay=5.0, backoff=2.0)
    def clone_inventory_repo(**kwargs: Any) -> subprocess.CompletedProcess:
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

    try:

        # Case 1: Inventory directory exists and is a git repo - pull latest changes
        if INVENTORY_DIR.exists() and (INVENTORY_DIR / '.git').exists():
            pull_inventory_repo()

        # Case 2: Inventory directory exists but isn't a git repo - remove and re-clone
        elif INVENTORY_DIR.exists():
            shutil.rmtree(INVENTORY_DIR)
            clone_inventory_repo()

        # Case 3: Inventory directory does not exist - clone from remote
        else:
            clone_inventory_repo()

    except Exception:
        printf('❌ Failed to update inventory after multiple attempts', fg='red', bold=True)
        sys.exit(1)


"""
Tool installation commands

Commands for installing Python tooling with enhanced reliability.

Both uv and hatch installation commands delegate to dedicated installer scripts
in scripts/installers/ that handle:
- Download and installation logic
- Checksum verification
- Retry logic for network resilience
- Force reinstall support
- Verbose output for debugging

The commands here simply build the appropriate CLI args and invoke the scripts.
"""


def installer_script_args(tool_name: str) -> Callable[[argparse.ArgumentParser], None]:
    def args_install_tool(parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            '-f',
            '--force',
            action='store_true',
            help=f'Force reinstall even if {style(tool_name, fg="bright_magenta")} is already installed',
        )
        parser.add_argument(
            '-v',
            '--verbose',
            action='store_true',
            help='Enable verbose output for debugging',
        )
        parser.add_argument(
            '--retries',
            type=int,
            metavar='N',
            help='Maximum number of download retry attempts',
        )
        parser.add_argument(
            '--retry-delay',
            type=int,
            metavar='SECONDS',
            help='Initial delay in seconds between retries with exponential backoff',
        )

    return args_install_tool


@command(
    group='Tool Installation',
    add_arguments=installer_script_args('uv'),
    description=f'Install {style("uv", fg="bright_magenta")} Python project manager',
)
def cmd_install_uv(args: argparse.Namespace) -> None:
    """
    Install `uv` Python package manager
    """
    cmd: list[str] = [str(SCRIPTS_DIR / 'installers' / 'install_uv.py')]
    if args.force:
        cmd.append('--force')
    if args.verbose:
        cmd.append('--verbose')
    if args.retries is not None:
        cmd.extend(['--retries', str(args.retries)])
    if args.retry_delay is not None:
        cmd.extend(['--retry-delay', str(args.retry_delay)])

    try:
        shell_command(cmd)
    except subprocess.CalledProcessError:
        sys.exit(1)


@command(
    group='Tool Installation',
    add_arguments=installer_script_args('hatch'),
    description=f'Install {style("hatch", fg="bright_magenta")} Python project manager',
)
def cmd_install_hatch(args: argparse.Namespace) -> None:
    """
    Install `hatch` Python project manager
    """
    cmd: list[str] = [str(SCRIPTS_DIR / 'installers' / 'install_hatch.py')]
    if args.force:
        cmd.append('--force')
    if args.verbose:
        cmd.append('--verbose')
    if args.retries is not None:
        cmd.extend(['--retries', str(args.retries)])
    if args.retry_delay is not None:
        cmd.extend(['--retry-delay', str(args.retry_delay)])

    try:
        shell_command(cmd)
    except subprocess.CalledProcessError:
        sys.exit(1)


"""
Codebase commands

General repository maintenance commands:
- clean: Remove build artifacts, caches, and temporary files
- pre: Run pre-commit hooks on all files
- makefile: Generate Makefile targets from @command-registered functions
  - Parses all registered commands and creates equivalent Make targets
  - Organizes targets by command group
  - Preserves command descriptions in Make comments
  - Auto-generates help target with formatted command listing
"""


@command(group='Codebase')
def cmd_clean(args: argparse.Namespace) -> None:
    """
    Remove all environments, build artifacts, and caches
    """
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


@command(group='Codebase')
def cmd_pre(args: argparse.Namespace) -> None:
    """
    Run pre-commit hooks on all project files
    """
    printf('🕝 Running pre-commit hooks on all project files...', fg='bright_cyan')
    shell_command(
        ['pre-commit', 'run', '--all-files'],
        indent=3,
        check=False,
    )


@command(
    group='Codebase',
    description=' '.join([
        'Generate Makefile from project management script commands',
        style(f'({Path(__file__).name})', dim=True),
    ]),
)
def cmd_makefile(args: argparse.Namespace) -> None:
    """
    Generate Makefile from project management script commands
    """
    command_groups: dict[str, dict[str, CommandInfo]] = {}
    command_names:  list[str]                         = []
    for group_name, commands in get_command_groups().items():
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
            description = cmd_info.description.splitlines()[0] if cmd_info.description else f'Run {cmd_name} command'
            lines.append(f'\t@echo "  $(YELLOW){cmd_name:<{col1_width}}$(NC) {description}"')
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


"""
Core runner entry point logic

The main() function handles:
1. Building the argument parser from registered commands
2. Parsing command-line arguments
3. Enabling debug mode if requested
4. Dispatching to the appropriate command function
5. Handling keyboard interrupts and unexpected errors gracefully

The build_parser() function:
- Creates main parser with custom help text organized by command group
- Registers subparsers for each @command-decorated function
- Integrates command-specific argument handlers via add_arguments callbacks
"""


def build_parser_help_text(col1_width: int = 30) -> str:
    """
    Build help text for argument parser with commands listed by group

    :param col1_width: width of col1 of help text
    :return: help text string
    """
    help_text = style("Runner script for Connor's dotfiles", fg='bright_green') + '\n\n'
    for group_name, commands in get_command_groups().items():
        help_text += f'{style(group_name, fg="bright_white")}:\n'
        for cmd_name, cmd_info in commands.items():
            if not cmd_info.makefile_only:
                description = cmd_info.description or f'Run {cmd_name} command'
                help_text += f'  {style(cmd_name, fg="yellow").ljust(col1_width)} {description.splitlines()[0]}\n'
        help_text += '\n'
    return help_text


def build_parser() -> argparse.ArgumentParser:
    """
    Build argument parser

    :return: :class:`argparse.ArgumentParser`
    """
    parser = argparse.ArgumentParser(
        description=build_parser_help_text(),
        formatter_class=partial(argparse.RawDescriptionHelpFormatter, max_help_position=80),
        add_help=False,
    )
    parser.add_argument(
        '-d',
        '--debug',
        action='store_true',
        help=f'Enable script debug logging {arg_note("env var", RUN_DEBUG_ENVVAR)}',
    )
    parser.add_argument(
        '-h',
        '--help',
        action='help',
        default=argparse.SUPPRESS,
        help='Show this help message and exit',
    )

    subparsers = parser.add_subparsers(
        dest='command',
        metavar='COMMAND',
        help=argparse.SUPPRESS,
    )
    for cmd in REGISTERED_COMMANDS.values():
        subparser = subparsers.add_parser(
            cmd.name,
            description=cmd.description or f'Run {cmd.name} command',
            help=cmd.description or f'Run {cmd.name} command',
            epilog=cmd.epilog,
            formatter_class=cmd.formatter_class,
        )
        if cmd.add_arguments:
            cmd.add_arguments(subparser)

    return parser


def main() -> None:
    """
    Main entry point
    """
    global RUN_DEBUG

    # Build argument parser and parse command-line args
    parser = build_parser()
    args   = parser.parse_args()

    # Print help text if no command provided
    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Enable debug logging
    if args.debug:
        RUN_DEBUG = True

    # Run specified command
    commands = get_command_functions()
    if cmd := commands.get(args.command):
        try:
            cmd(args)
        except KeyboardInterrupt:
            printf('⚠️ Operation cancelled by user', fg='yellow')
            sys.exit(1)
        except Exception as e:
            printf(f'❌ Unexpected error: {e!s}', fg='red', bold=True)
            sys.exit(1)
    else:
        printf(f'❓ Unknown command: {args.command}', fg='red', bold=True)
        printf(f'   Available commands: {", ".join(commands.keys())}')
        sys.exit(1)


if __name__ == '__main__':
    main()
