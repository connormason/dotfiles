"""
Subprocess execution with live output streaming and error handling
"""
from __future__ import annotations

import errno
import os
import pty
import select
import shlex
import subprocess
import time
from typing import TYPE_CHECKING
from typing import Any
from typing import Literal
from typing import cast
from typing import overload

from cli.infra.config import DOTFILES_DIR
from cli.utils.styling import printf
from cli.utils.styling import style
from cli.utils.styling import unstyle

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

__all__ = [
    'RUN_COMMAND_ENVVARS',
    'ShellCommandError',
    'capture_command',
    'detect_ssh_error',
    'first_output_line',
    'handle_command_error',
    'shell_command',
]


# ==================================================================================================
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
# ==================================================================================================


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

        returncode = -1
        timed_out  = False
        deadline   = None if timeout is None else time.monotonic() + timeout
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


def capture_command(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    """
    Run a command quietly and capture its output (patched in tests)

    :param cmd: command and arguments
    :return: completed process with text stdout/stderr
    """
    return subprocess.run(cmd, capture_output=True, text=True, check=False, cwd=DOTFILES_DIR, **kwargs)


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


def first_output_line(text: str, default: str) -> str:
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
