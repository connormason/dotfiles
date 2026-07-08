#!/usr/bin/env python3
"""
Programmatically install Hatch using the official installer script.
"""
from __future__ import annotations

import argparse
import enum
import functools
import os
import platform
import re
import shutil
import ssl
import subprocess
import sys
import textwrap
import time
import urllib.error
import urllib.request
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from typing import Callable
from typing import Protocol
from typing import TypeVar
from typing import Union
from typing import cast

# ==================================================================================================
# Constants/defaults/globals
# ==================================================================================================


# Configuration
MIN_PYTHON:           tuple[int, int] = (3, 8)   # Minimum supported python version. Script exits with error if not met
DOWNLOAD_TIMEOUT:     float           = 30.0     # Installer download timeout in seconds (default for --timeout)
DOWNLOAD_RETRIES:     int             = 3        # Maximum number of download retry attempts (default for --retries)
DOWNLOAD_RETRY_DELAY: float           = 2        # Initial delay in seconds between retries (default for --retry-delay)

# Reference URLs
DOCS_URL:               str = 'https://hatch.pypa.io/'
INSTALLATION_GUIDE_URL: str = 'https://hatch.pypa.io/latest/install/'

# Global verbose flag
VERBOSE: bool = False


# ==================================================================================================
# Types/protocols
# ==================================================================================================


PathLike   = Union[Path, str]
StyleColor = Union[int, tuple[int, int, int], str]

T_contra   = TypeVar('T_contra', contravariant=True)


class SupportsWrite(Protocol[T_contra]):
    """
    Protocol for writable things (like :attr:`sys.stdout` and :attr:`sys.stderr`).
    """
    def write(self, s: T_contra, /) -> object:
        ...


class ExitCode(int, enum.Enum):
    """
    Script exit codes.
    """
    SUCCESS              = 0
    ALREADY_INSTALLED    = 0
    INVALID_PARAMETERS   = 1
    DOWNLOAD_FAILED      = 2
    INSTALL_FAILED       = 3
    VERIFICATION_FAILED  = 4
    UNSUPPORTED_PLATFORM = 5
    PYTHON_VERSION       = 6


class DownloadMethod(str, enum.Enum):
    """
    Installer download methods, ordered by the priority in which they may be attempted.

    ``curl`` is preferred over ``urllib`` by default because curl uses the platform's native trust store
    (e.g. SecureTransport on macOS)
    """
    CURL   = 'curl'
    URLLIB = 'urllib'

    def __str__(self) -> str:
        return self.value


# Default ordered list of download methods to attempt. curl is tried before urllib (see :class:`DownloadMethod`)
DEFAULT_DOWNLOAD_METHODS: tuple[DownloadMethod, ...] = (DownloadMethod.CURL, DownloadMethod.URLLIB)


# ==================================================================================================
# Formatting/logging
# ==================================================================================================


ANSI_COLORS: dict[str, int] = {
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

    :param _color: color as a name string, 256-color int, or (r, g, b) tuple
    :param offset: offset to add for background colors (10 for bg, 0 for fg)
    :return: ANSI SGR parameter string (e.g. ``'38;5;196'``)
    """
    if isinstance(_color, int):
        return f'{38 + offset};5;{_color:d}'
    if isinstance(_color, (tuple, list)):
        r, g, b = _color
        return f'{38 + offset};2;{r:d};{g:d};{b:d}'
    _color = cast('str', _color)
    return str(ANSI_COLORS[_color] + offset)


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
    Style text with ANSI escape codes.

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
        bits.append(ANSI_RESET_ALL)
    return ''.join(bits)


def unstyle(text: str) -> str:
    """
    Remove ANSI styling information from a string.

    :param text: the text to remove style information from
    :return: string with ANSI styling characters removed
    """
    return re.sub(r'\033\[[;?0-9]*[a-zA-Z]', '', text)


def folduser(path: PathLike) -> str:
    """
    Does the opposite of :meth:`pathlib.Path.expanduser`, replacing the user's home directory with a "~".

    :param path: path
    :return: str folded path
    """
    home = str(Path.home())
    return str(path).replace(home, '~')


def pathstyle(path: PathLike, **kwargs: Any) -> str:
    """
    Style a file path with magenta foreground and home directory condensed to ``~``.

    :param path: path to style
    :return: styled path string
    """
    return style(folduser(path), fg='magenta', **kwargs)


def optstyle(text: Any, **opts: Any) -> str:
    """
    Style a CLI option name in yellow.

    :param text: the option name to style
    :param opts: additional keyword arguments forwarded to :func:`style`
    :return: ANSI-styled string
    """
    return style(text, fg='yellow', **opts)


def typestyle(val: Any, **opts: Any) -> str:
    """
    Style a Python value by its type using semantic colors (roughly matching default repr styling provided by rich).

    Color mapping:

        - ``None`` = magenta italic
        - ``bool`` = green (True) / red (False) italic
        - ``Path`` = magenta with folduser
        - ``int``/``float`` = bright cyan bold
        - ``str`` = green

    Other types fall through to ``str(val)`` unstyled

    :param val: the Python value to style
    :return: the ANSI-styled representation
    """
    if val is None:
        return style(str(val), fg='magenta', italic=True, **opts)
    if isinstance(val, bool):
        return style(str(val), fg=f'bright_{"green" if val else "red"}', italic=True, **opts)
    if isinstance(val, Path):
        return style(folduser(val), fg='magenta', **opts)
    if isinstance(val, (int, float)):
        return style(repr(val), fg='bright_cyan', bold=True, **opts)
    if isinstance(val, str):
        return style(repr(val), fg='green', **opts)
    if isinstance(val, Sequence):
        return ''.join([
            style('[', fg='bright_white'),
            ', '.join(typestyle(item, **opts) for item in val),
            style(']', fg='bright_white'),
        ])
    return style(val, **opts)


def annotated_opt_help(
    opt_help: str,
    *extra_help_lines: str,
    choices: Sequence[Any] | None = None,
    default: Any | None = None,
    default_fg: StyleColor | None = None,
    envvar: str | None = None,
    extra_line: bool = True,
) -> str:
    """
    Build a styled argparse help string with optional default value and environment variable annotations.

    :param opt_help: core help text for the option (will be styled "bright_white")
    :param extra_help_lines: additional help text lines (joined by newlines) for the option. Outputted with no styling
                             after `opt_help` and before `default`/`envvar`
    :param choices: valid option value choices to display below the help text
    :param default: default value to display below the help text
    :param default_fg: explicit foreground color for the default value (overrides :func:`typestyle`)
    :param envvar: environment variable name that can override this option
    :param extra_line: if True (default), extra blank line included at the end of the option help text (visually spaces
                       sequential options apart from each other)
    :return: multi-line styled help string with annotations appended
    """
    help_lines: list[str] = style(opt_help, fg='bright_white').splitlines()
    for extra_help_line in extra_help_lines:
        help_lines.extend(extra_help_line.splitlines())
    if choices is not None:
        help_lines.append(f'  choices: {typestyle(choices)}')
    if default is not None:
        help_lines.append(f'  default: {typestyle(default) if default_fg is None else style(default, fg=default_fg)}')
    if envvar is not None:
        help_lines.append(f'  env var: {style(envvar, fg="cyan")}')
    if extra_line:
        help_lines.append('  ')
    return '\n'.join(help_lines)


def printf(
    text: str = '',
    *,
    fg: StyleColor | None = None,
    bold: bool | None = None,
    dim: bool | None = None,
    indent: int = 0,
    file: SupportsWrite[str] | None = None,
    verbose: bool = False,
) -> None:
    """
    Print styled text with optional indent and verbose gating.

    :param text: text to print
    :param fg: foreground color
    :param bold: bold mode
    :param dim: dim mode
    :param indent: number of spaces to indent output by
    :param file: output file (defaults to stdout, or stderr for verbose output)
    :param verbose: only print when global ``VERBOSE`` is True. Output is dim and sent to stderr
    """
    if verbose and not VERBOSE:
        return
    if verbose:
        fg   = fg or 'bright_white'
        dim  = True if dim is None else dim
        file = file or sys.stderr

    print(
        style(textwrap.indent(text, ' ' * indent), fg=fg, bold=bold, dim=dim),
        file=file,
    )


# ==================================================================================================
# Python checks
# ==================================================================================================


def check_python_version() -> bool:
    """
    Check minimum Python version requirement (:attr:`MIN_PYTHON` above).

    :return: True if minimum python version requirement met, False if not
    """
    if sys.version_info < MIN_PYTHON:
        printf(
            f'❌ Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ required, '
            f'but you have Python {sys.version_info.major}.{sys.version_info.minor}',
            fg='bright_red',
            file=sys.stderr,
        )
        return False
    vers_str = f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}'
    printf(f'✅ Python version {vers_str}', verbose=True)
    return True


# ==================================================================================================
# Shell detection & path mapping
# ==================================================================================================


class Shell(enum.Enum):
    """
    Known shells with their associated RC file paths and PATH export syntax.
    """
    BASH = 'bash'
    ZSH  = 'zsh'
    FISH = 'fish'
    TCSH = 'tcsh'
    CSH  = 'csh'

    @classmethod
    def detect(cls) -> Shell | None:
        """
        Detect the user's shell from the ``$SHELL`` environment variable.

        :return: detected :class:`Shell` member, or ``None`` if unrecognized or unset
        """
        if shell := os.environ.get('SHELL', ''):
            name = Path(shell).name
            try:
                return cls(name)
            except ValueError:
                return None
        return None

    @property
    def rc_file(self) -> Path:
        """
        Get the appropriate RC file path for this shell.

        On macOS, bash prefers ``~/.bash_profile`` over ``~/.bashrc`` when the file exists.

        :return: path to the shell's RC file
        """
        home = Path.home()
        rc_map: dict[Shell, Path] = {
            Shell.BASH: home / '.bashrc',
            Shell.ZSH:  home / '.zshrc',
            Shell.FISH: home / '.config' / 'fish' / 'config.fish',
            Shell.TCSH: home / '.tcshrc',
            Shell.CSH:  home / '.cshrc',
        }
        if (self is Shell.BASH) and (platform.system() == 'Darwin'):
            bash_profile = home / '.bash_profile'
            if bash_profile.exists():
                return bash_profile
        return rc_map[self]

    def path_export_command(self, directory: PathLike) -> str:
        """
        Get the command to add a directory to ``PATH`` for this shell.

        :param directory: directory to prepend to ``PATH``
        :return: shell-specific export command string
        """
        directory_path = Path(directory).expanduser().resolve()
        if self in (Shell.BASH, Shell.ZSH):
            return f'export PATH="{directory_path}:$PATH"'
        if self is Shell.FISH:
            return f'set -gx PATH "{directory_path}" $PATH'
        # TCSH, CSH
        return f'setenv PATH "{directory_path}:$PATH"'


# ==================================================================================================
# Local executable checks
# ==================================================================================================


# TODO: support brew install location as well
# TODO: allow installation from current environment as well (from `pip install`)
def get_common_install_locations() -> list[Path]:
    """
    Get common installation locations for Hatch on macOS.

    :return: list of filepaths (:class:`pathlib.Path`)
    """
    home = Path.home()
    locations: list[Path] = [
        home / '.local' / 'bin' / 'hatch',
        home / '.cargo' / 'bin' / 'hatch',
        Path('/usr/local/bin/hatch'),
        Path('/usr/local/hatch/bin/hatch'),
        Path('/usr/bin/hatch'),
        home / '.hatch' / 'bin' / 'hatch',
    ]

    # macOS pip ``--user`` installs land in ``~/Library/Python/<X.Y>/bin/hatch`` (one entry per framework Python).
    # Scanning catches hatch installed by ``install_via_pip`` even when the system python3 falls back to PEP 370
    # user-base, plus any pre-existing pip --user installs.
    library_python = home / 'Library' / 'Python'
    if library_python.is_dir():
        for child in sorted(library_python.iterdir()):
            hatch_path = child / 'bin' / 'hatch'
            if hatch_path not in locations:
                locations.append(hatch_path)

    # Locations registered dynamically by ``install_via_pip`` (e.g. system python3 scripts dir)
    for path in PIP_INSTALL_LOCATIONS:
        if path not in locations:
            locations.append(path)

    return locations


def find_executable(*, path_only: bool = False) -> tuple[str | None, str | None]:
    """
    Try to find the Hatch executable in common locations.

    :param path_only: if True, only look for executable in PATH. If False, look for executable in other common locations
                      where hatch might be installed
    :return: tuple (executable path, version)
    """

    # First check if it's in PATH
    try:
        result = subprocess.run(
            ['hatch', '--version'],
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    else:
        return 'hatch', result.stdout.strip()

    # Check common installation locations
    if not path_only:
        for location in get_common_install_locations():
            if location.exists() and location.is_file():
                try:
                    result = subprocess.run(
                        [str(location), '--version'],
                        check=True,
                        capture_output=True,
                        text=True,
                    )
                except (subprocess.CalledProcessError, PermissionError):
                    continue
                else:
                    return str(location), result.stdout.strip()

    return None, None


def is_installed(*, quiet: bool = False) -> bool:
    """
    Check if Hatch is already installed.

    :param quiet: suppress console output if True
    :return: True if `hatch` already installed, False if not
    """
    executable, version = find_executable()
    if executable:
        if not quiet:
            printf(f'✅ Already installed: {style(version, fg="bright_white")}', fg='bright_green')
            if executable != 'hatch':
                printf(f'Found at: {pathstyle(executable)}', indent=3)
                printf(
                    style('NOTE: ',                            fg='magenta', bold=True) +
                    style('consider adding this to your PATH', fg='bright_white'),
                    indent=3,
                )
        return True
    return False


# ==================================================================================================
# Installer retrieval/execution
# ==================================================================================================


def get_installer_url() -> str:
    """
    Get the Hatch installer URL for macOS.

    On macOS, Hatch is distributed as a ``.pkg`` installer.

    :raises OSError: if current platform is not macOS
    :return: installer URL
    """
    if platform.system().lower() != 'darwin':
        raise OSError(f'This installer only supports macOS (got: {platform.system()})')
    return 'https://github.com/pypa/hatch/releases/latest/download/hatch-universal.pkg'


def write_installer(dest: PathLike, content: bytes) -> bool:
    """
    Write downloaded installer bytes to disk, surfacing helpful troubleshooting tips on failure.

    :param dest: destination file path
    :param content: bytes to write
    :return: True if successful, False if not
    """
    try:
        with Path(dest).expanduser().open('wb') as f:
            f.write(content)
    except (PermissionError, OSError) as e:
        printf(f'❌ Failed to write installer to disk: {e!s}',       fg='bright_red',   file=sys.stderr)
        print(file=sys.stderr)
        printf('🔧 Troubleshooting:',                                fg='bright_white', file=sys.stderr)
        printf(f'1. Check write permissions for: {pathstyle(dest)}', indent=3,          file=sys.stderr)
        printf('2. Verify sufficient disk space is available',       indent=3,          file=sys.stderr)
        printf('3. Ensure the parent directory exists',              indent=3,          file=sys.stderr)
        return False
    else:
        printf(f'✅ Downloaded to {pathstyle(dest)}', fg='bright_green')
        return True


def download_with_urllib(
    url: str,
    dest: PathLike,
    *,
    timeout: float = DOWNLOAD_TIMEOUT,
    retries: int = DOWNLOAD_RETRIES,
    retry_delay: float = DOWNLOAD_RETRY_DELAY,
) -> bool:
    """
    Download a file using Python's :mod:`urllib`.

    Aborts early on SSL verification errors so the curl fallback can be tried sooner.
    SSL errors are not transient and additional retries will not recover.

    :param url: source URL
    :param dest: destination file path
    :param timeout: per-request timeout in seconds
    :param retries: maximum number of retry attempts
    :param retry_delay: initial delay in seconds between retries, before exponential backoff
    :return: True if successful, False if not
    """
    content: bytes | None = None
    for attempt in range(1, retries + 1):
        try:
            if attempt > 1:
                delay = retry_delay * (2 ** (attempt - 2))      # Exponential backoff
                printf(f'⏱️  Retrying in {delay} seconds... (attempt {attempt}/{retries})', fg='bright_yellow')
                time.sleep(delay)

            printf(f'⏬ Downloading installer from {url} (urllib)...', bold=True)
            printf(f'Attempt {attempt}/{retries}', indent=3, verbose=True)

            with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
                content = response.read()

        except urllib.error.URLError as e:
            printf(f'❌ urllib download failed: {e!s}', fg='bright_red', file=sys.stderr)
            if isinstance(e.reason, ssl.SSLError):
                printf('SSL verification failed; aborting urllib retries', indent=3, verbose=True, file=sys.stderr)
                return False
            if attempt == retries:
                return False

        except Exception as e:
            printf(f'❌ Unexpected error during urllib download: {e!s}', fg='bright_red', file=sys.stderr)
            if attempt == retries:
                return False

        # Download succeeded, break out of retry loop
        else:
            break

    if content is None:
        return False
    return write_installer(dest, content)


def download_with_curl(
    url: str,
    dest: PathLike,
    *,
    timeout: float = DOWNLOAD_TIMEOUT,
    retries: int = DOWNLOAD_RETRIES,
    retry_delay: float = DOWNLOAD_RETRY_DELAY,
) -> bool:
    """
    Download a file using the system ``curl`` executable.

    Useful as a fallback when :mod:`urllib` fails — particularly with SSL certificate verification errors — since curl
    uses the platform's native trust store (e.g. SecureTransport on macOS)

    :param url: source URL
    :param dest: destination file path
    :param timeout: per-request timeout in seconds
    :param retries: maximum number of retry attempts
    :param retry_delay: initial delay in seconds between retries, before exponential backoff
    :return: True if successful, False if not
    """
    curl = shutil.which('curl')
    if curl is None:
        printf('curl not available, skipping curl fallback', verbose=True, file=sys.stderr)
        return False

    dest_path = Path(dest).expanduser()
    cmd: list[str] = [
        curl,
        '--fail',
        '--silent',
        '--show-error',
        '--location',
        '--max-time', str(int(timeout)),
        '--output',   str(dest_path),
        url,
    ]

    for attempt in range(1, retries + 1):
        if attempt > 1:
            delay = retry_delay * (2 ** (attempt - 2))      # Exponential backoff
            printf(f'⏱️  Retrying in {delay} seconds... (attempt {attempt}/{retries})', fg='bright_yellow')
            time.sleep(delay)

        printf(f'⏬ Downloading installer from {url} (curl)...', bold=True)
        printf(f'Attempt {attempt}/{retries}', indent=3, verbose=True)
        printf(f'Running: {" ".join(cmd)}',    indent=3, verbose=True)
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            err = (e.stderr or '').strip() or str(e)
            printf(f'❌ curl download failed: {err}', fg='bright_red', file=sys.stderr)
            if attempt == retries:
                return False
        else:
            printf(f'✅ Downloaded to {pathstyle(dest_path)}', fg='bright_green')
            return True

    return False


# Dispatch table mapping each download method to its implementation.
# Both functions share the same signature ``(url, dest, *, timeout, retries, retry_delay) -> bool``
DOWNLOAD_FUNCS: dict[DownloadMethod, Callable[..., bool]] = {
    DownloadMethod.CURL:   download_with_curl,
    DownloadMethod.URLLIB: download_with_urllib,
}


def download_installer(
    url: str,
    dest: PathLike,
    *,
    methods: Sequence[DownloadMethod] = DEFAULT_DOWNLOAD_METHODS,
    timeout: float = DOWNLOAD_TIMEOUT,
    retries: int = DOWNLOAD_RETRIES,
    retry_delay: float = DOWNLOAD_RETRY_DELAY,
) -> bool:
    """
    Download the installer script, trying each configured download method in order until one succeeds.

    The default order (see :attr:`DEFAULT_DOWNLOAD_METHODS`) tries ``curl`` before :mod:`urllib`. curl handles
    environments where Python's bundled OpenSSL CA list cannot validate the TLS chain to ``url``

    :param url: installer URL
    :param dest: where to download installer to
    :param methods: ordered download methods to attempt; each is tried until one succeeds
    :param timeout: download timeout in seconds
    :param retries: maximum number of download retry attempts
    :param retry_delay: initial delay in seconds between retries, before exponential backoff
    :raises ValueError: if `url` does not start with "http:" or "https:"
    :return: True if successful, False if not
    """
    if not url.startswith(('http:', 'https:')):
        raise ValueError("URL must start with 'http:' or 'https:'")

    ordered_methods = list(methods) or list(DEFAULT_DOWNLOAD_METHODS)
    for index, method in enumerate(ordered_methods):
        download_func = DOWNLOAD_FUNCS[method]
        if download_func(url, dest, timeout=timeout, retries=retries, retry_delay=retry_delay):
            return True

        # Announce the fallback to the next method, if any remain
        if index < len(ordered_methods) - 1:
            next_method = ordered_methods[index + 1]
            printf(f'⚠️ {method} download failed; falling back to {next_method}', fg='bright_yellow')
            printf('')

    return False


def run_installer(installer_path: PathLike) -> bool:
    """
    Execute the Hatch ``.pkg`` installer via ``sudo installer``.

    :param installer_path: path to ``.pkg`` installer
    :return: True on success, False on failure
    """
    printf('💿 Running Hatch .pkg installer (requires sudo)...', bold=True)
    try:
        result = subprocess.run(
            ['sudo', 'installer', '-pkg', str(installer_path), '-target', '/'],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        printf(f'❌ Installation failed: {e!s}', fg='bright_red', file=sys.stderr)
        printf(e.stderr, indent=3, file=sys.stderr)
        return False
    else:
        printf(result.stdout, indent=3)
        return True


# ==================================================================================================
# `pip`-based installation (last-resort fallback)
# ==================================================================================================


# Locations registered dynamically by :func:`install_via_pip` so :func:`find_executable` can find hatch after a
# successful pip install on this run.
PIP_INSTALL_LOCATIONS: list[Path] = []


def resolve_system_python() -> str | None:
    """
    Locate a system ``python3`` executable suitable for the pip-install fallback.

    Prefers the macOS system interpreter at ``/usr/bin/python3``, then anything named ``python3`` on ``PATH``.

    :return: absolute path to a python3 executable, or ``None`` if none can be found
    """
    system_python = Path('/usr/bin/python3')
    if system_python.exists():
        return str(system_python)
    return shutil.which('python3')


def register_pip_install_location(python_exe: str) -> None:
    """
    Register the scripts directory of ``python_exe`` so :func:`find_executable` can find ``hatch``.

    Asks the interpreter for its ``sysconfig`` scripts path and appends ``<scripts>/hatch`` to the module-level
    :attr:`PIP_INSTALL_LOCATIONS` list.

    :param python_exe: path to a python interpreter that just ran ``pip install hatch``
    """
    try:
        result = subprocess.run(
            [python_exe, '-c', 'import sysconfig; print(sysconfig.get_path("scripts"))'],
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return
    else:
        candidate = Path(result.stdout.strip()) / 'hatch'
        if candidate not in PIP_INSTALL_LOCATIONS:
            PIP_INSTALL_LOCATIONS.append(candidate)
            printf(f'Registered pip install location: {pathstyle(candidate)}', indent=3, verbose=True)


def install_via_pip() -> bool:
    """
    Install Hatch via ``python3 -m pip install hatch`` using the system ``python3`` executable.

    Used as a last-resort fallback when neither :mod:`urllib` nor ``curl`` could fetch the official ``.pkg`` installer
    (or when the user cannot run ``sudo`` to execute the ``.pkg``). Installs into the system Python's site-packages so
    the resulting ``hatch`` executable lands in that interpreter's scripts directory.

    :return: True on success, False on failure
    """
    printf('')
    printf('💿 Falling back to pip install hatch (system python3)...', bold=True)

    python3 = resolve_system_python()
    if python3 is None:
        printf('❌ Could not find a python3 executable for pip fallback', fg='bright_red', file=sys.stderr)
        return False
    printf(f'Using python: {pathstyle(python3)}', indent=3, verbose=True)

    cmd: list[str] = [python3, '-m', 'pip', 'install', 'hatch']
    printf(f'Running: {" ".join(cmd)}', indent=3, verbose=True)

    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)

    except subprocess.CalledProcessError as e:
        printf(f'❌ pip install hatch failed (exit {e.returncode})', fg='bright_red', file=sys.stderr)
        if e.stdout:
            printf(e.stdout.rstrip(),                                       indent=3, file=sys.stderr)
        if e.stderr:
            printf(e.stderr.rstrip(),                                       indent=3, file=sys.stderr)
        return False

    except FileNotFoundError as e:
        printf(f'❌ pip install hatch failed: {e!s}', fg='bright_red', file=sys.stderr)
        return False

    else:
        if VERBOSE and result.stdout:
            printf(result.stdout.rstrip(), indent=3, verbose=True)
        printf('✅ Installed hatch via pip', fg='bright_green')
        register_pip_install_location(python3)
        return True


def verify_installation() -> bool:
    """
    Verify that Hatch was installed successfully. Provides detailed guidance if tool is installed but not in PATH.

    :return: True on success, False on failure
    """
    printf('')
    printf('🔍 Verifying installation...', bold=True)
    printf('Checking all known installation locations...', indent=3, verbose=True)

    # Use find_executable to check all locations
    executable, version = find_executable()
    if not executable:
        printf('❌ Hatch installation could not be verified\n',         fg='bright_red',   file=sys.stderr)
        printf('🔧 Troubleshooting:',                                   fg='bright_white', file=sys.stderr)
        printf('1. Close and reopen your terminal',                              indent=3, file=sys.stderr)
        printf(f'2. Try running the installer again with {optstyle("--force")}', indent=3, file=sys.stderr)
        printf('3. Check the official Hatch installation guide:',                indent=3, file=sys.stderr)
        printf(INSTALLATION_GUIDE_URL,                                 dim=True, indent=6, file=sys.stderr)
        return False

    # Tool found!
    printf('✅ Installed successfully', fg='bright_green')
    printf(version or '', indent=3)

    # Check if it's in PATH
    if executable == 'hatch':
        printf('✅ In your PATH and ready to use', fg='bright_green')
        printf(f'Executable: {executable}', indent=3, verbose=True)
        return True

    # Tool is installed but not in PATH
    printf(f'📍 Found at: {pathstyle(executable)}\n')
    printf('⚠️ Installed but not in your PATH', fg='bright_yellow')

    install_dir = Path(executable).parent
    shell       = Shell.detect()

    printf('')
    printf('💡 To make it available globally, add it to your PATH:\n', fg='bright_white')
    if shell:
        rc_file    = shell.rc_file
        export_cmd = shell.path_export_command(install_dir)
        printf(f'For {shell.value}, add this line to {pathstyle(rc_file)}:',      indent=3)
        printf(style(export_cmd, fg='bright_magenta'),                            indent=3)
        printf('')
        printf('Then run:',                                                       indent=3)
        printf(style(f'source {folduser(rc_file)}', fg='bright_magenta'),         indent=3)
    else:
        printf(f'Add {pathstyle(install_dir)} to your PATH environment variable', indent=3)
        printf("Consult your shell's documentation for instructions",             indent=3, dim=True)

    printf('')
    printf(f'Or use the full path: {pathstyle(executable)}', indent=3)

    # Still consider this a success since the tool is installed
    return True


# ==================================================================================================
# Command-line arguments
# ==================================================================================================


class Args(argparse.Namespace):
    """
    Annotated :class:`argparse.Namespace` returned by :func:`parse_args`.
    """
    force:            bool                  # -f/--force
    ensure:           bool                  # -e/--ensure
    verbose:          bool                  # -v/--verbose
    timeout:          float                 # -t/--timeout
    retries:          int                   # -r/--retries
    retry_delay:      float                 # --retry-delay
    download_methods: list[DownloadMethod]  # -m/--download-method


def parse_args(argv: Sequence[str] | None = None) -> Args:
    """
    Build parser and parse command-line arguments.

    :param argv: argument list of parse. Defaults to ``sys.argv[1:]``
    :return: annotated namespace of parsed args (:class:`Args`)
    """
    global VERBOSE

    PROG = style('%(prog)s', fg='bright_magenta')

    def dim(text: Any, **opts: Any) -> str:
        return style(text, dim=opts.pop('dim', True), **opts)

    # Build argument parser
    parser = argparse.ArgumentParser(
        description=style('Install Hatch build tool using official installer script', fg='bright_yellow'),
        formatter_class=functools.partial(
            argparse.RawTextHelpFormatter,
            max_help_position=80,
        ),
        epilog='\n'.join([
            style('Examples:', fg='bright_blue', bold=True),
            '',
            f'  {PROG}                                {dim("# Normal installation")}',
            f'  {PROG} --force                        {dim("# Force reinstall even if present")}',
            f'  {PROG} --verbose                      {dim("# Show detailed progress")}',
            f'  {PROG} --force -v                     {dim("# Force reinstall with verbose output")}',
            f'  {PROG} --retries 5                    {dim("# Increase download retry attempts to 5")}',
            f'  {PROG} --retry-delay 3                {dim("# Set initial retry delay to 3 seconds")}',
            f'  {PROG} --retries 5 --retry-delay 3    {dim("# Custom retry configuration")}',
            f'  {PROG} --download-method curl         {dim("# Only use curl to download the installer")}',
            f'  {PROG} --download-method urllib curl  {dim("# Try urllib first, then fall back to curl")}',
        ]),
        add_help=False,
    )

    def add_execution_opts() -> None:
        """
        Add execution option arguments (``--force``, ``--ensure``) to the parser.
        """
        execution_opts = parser.add_argument_group(style('Execution options', fg='bright_blue', bold=True))
        execution_opts.add_argument(
            '-f',
            '--force',
            action='store_true',
            help=annotated_opt_help('Force installation even if Hatch is already installed'),
        )
        execution_opts.add_argument(
            '-e',
            '--ensure',
            action='store_true',
            help=annotated_opt_help(
                'Install Hatch if it does not exist, otherwise quietly exit with no console output'
            ),
        )
    add_execution_opts()

    def add_download_opts() -> None:
        """
        Add download option arguments (``--timeout``, ``--retries``, ``--retry-delay``) to the parser.
        """
        download_opts = parser.add_argument_group(style('Download options', fg='bright_blue', bold=True))
        download_opts.add_argument(
            '-t',
            '--timeout',
            type=float,
            default=DOWNLOAD_TIMEOUT,
            metavar='SECONDS',
            help=annotated_opt_help(
                'Download timeout in seconds',
                default=DOWNLOAD_TIMEOUT,
            ),
        )
        download_opts.add_argument(
            '-r',
            '--retries',
            type=int,
            default=DOWNLOAD_RETRIES,
            metavar='NUM',
            help=annotated_opt_help(
                'Maximum number of download retry attempts',
                default=DOWNLOAD_RETRIES,
            ),
        )
        download_opts.add_argument(
            '-d',
            '--retry-delay',
            type=float,
            default=DOWNLOAD_RETRY_DELAY,
            metavar='SECONDS',
            help=annotated_opt_help(
                'Initial delay in seconds between retries, uses exponential backoff',
                default=DOWNLOAD_RETRY_DELAY,
            ),
        )
        download_opts.add_argument(
            '-m',
            '--download-method',
            dest='download_methods',
            nargs='+',
            type=DownloadMethod,
            choices=list(DownloadMethod),
            default=list(DEFAULT_DOWNLOAD_METHODS),
            metavar='METHOD',
            help=annotated_opt_help(
                'Ordered download methods to try, highest priority first',
                choices=[m.value for m in DownloadMethod],
                default=[m.value for m in DEFAULT_DOWNLOAD_METHODS],
            ),
        )
    add_download_opts()

    def add_other_opts() -> None:
        """
        Add miscellaneous option arguments (``--help``) to the parser.
        """
        other_opts = parser.add_argument_group(style('Other options', fg='bright_blue', bold=True))
        other_opts.add_argument(
            '-v',
            '--verbose',
            action='store_true',
            help='Enable verbose output for debugging',
        )
        other_opts.add_argument(
            '-h',
            '--help',
            action='help',
            default=argparse.SUPPRESS,
            help='Show this help message and exit',
        )
    add_other_opts()

    # Parse arguments
    args = parser.parse_args(argv, namespace=Args())

    # Set global config variables with parsed command-line option values
    VERBOSE = args.verbose

    # Validate retry parameters
    if args.timeout < 0:
        printf(f'❌ {optstyle("--timeout")} cannot be negative',     fg='bright_red', file=sys.stderr)
        sys.exit(ExitCode.INVALID_PARAMETERS)
    if args.retries < 1:
        printf(f'❌ {optstyle("--retries")} must be at least 1',     fg='bright_red', file=sys.stderr)
        sys.exit(ExitCode.INVALID_PARAMETERS)
    if args.retry_delay < 0:
        printf(f'❌ {optstyle("--retry-delay")} cannot be negative', fg='bright_red', file=sys.stderr)
        sys.exit(ExitCode.INVALID_PARAMETERS)

    # Enforce mutual exclusivity of --force and --ensure
    # Using ``add_mutually_exclusive_group()`` prevents us from adding a help text title to the execution options group
    if args.force and args.ensure:
        printf(
            f'❌ {optstyle("--force")} and {optstyle("--ensure")} are mutually exclusive',
            fg='bright_red',
            file=sys.stderr,
        )
        sys.exit(ExitCode.INVALID_PARAMETERS)

    return args


# ==================================================================================================
# Core script entry point
# ==================================================================================================


def main(argv: Sequence[str] | None = None) -> None:
    """
    Programmatically install Hatch using the official installer script.

    :param argv: argument list of parse. Defaults to ``sys.argv[1:]``
    """

    # Parse command-line arguments
    args = parse_args(argv)

    if args.verbose or not args.ensure:
        printf()
        printf('Hatch installation', fg='bright_cyan', bold=True)
        printf('─' * 77, dim=True)
        printf(
            f'Download configuration: methods={" → ".join(str(m) for m in args.download_methods)}, '
            f'{args.retries} attempts, {args.retry_delay}s initial delay\n',
            verbose=True,
        )

    # Check Python version
    if not check_python_version():
        sys.exit(ExitCode.PYTHON_VERSION)

    # Check if already installed (unless --force is specified)
    if not args.force:
        if is_installed(quiet=args.ensure and not args.verbose):
            if not args.ensure:
                printf('⏭️ Skipping installation')
                printf(
                    f'{style("Use", fg="bright_white")} {optstyle("--force")} '
                    f'{style("to reinstall", fg="bright_white")}',
                    indent=3,
                )
            sys.exit(ExitCode.ALREADY_INSTALLED)
    else:
        printf(f'🔄 {optstyle("--force")} specified, proceeding with installation...\n', fg='bright_cyan')

    # Get installer URL
    try:
        url = get_installer_url()
        printf(f'Installer URL: {url}', verbose=True)
    except OSError as e:
        printf(f'❌ {e!s}', fg='bright_red', file=sys.stderr)
        sys.exit(ExitCode.UNSUPPORTED_PLATFORM)

    # Download installer to temp location
    installer_path = Path.home() / '.hatch-universal.pkg'
    printf(f'Temporary installer path: {installer_path}', verbose=True)

    # Try the official .pkg installer first; fall back to ``pip install hatch`` if either the download or the installer
    # execution fails. Network/SSL errors typically affect the download step. Missing ``sudo`` or platform mismatches
    # typically affect the installer step.
    installed: bool = False
    if download_installer(
        url,
        installer_path,
        methods=args.download_methods,
        timeout=args.timeout,
        retries=args.retries,
        retry_delay=args.retry_delay,
    ):
        printf('')
        installed = run_installer(installer_path)
        installer_path.unlink(missing_ok=True)
        if not installed:
            printf('⚠️ .pkg installer failed; trying pip fallback', fg='bright_yellow')

    if not installed:
        installed = install_via_pip()

    if not installed:
        printf('',                                                                             file=sys.stderr)
        printf('🔧 Troubleshooting:',                                       fg='bright_white', file=sys.stderr)
        printf('1. Check your internet connection',                                  indent=3, file=sys.stderr)
        printf('2. Verify you can access https://github.com',                        indent=3, file=sys.stderr)
        printf('3. Check if a proxy is required in your network',                    indent=3, file=sys.stderr)
        printf('4. For SSL errors, try: export SSL_CERT_FILE=$(python3 -m certifi)', indent=3, file=sys.stderr)
        sys.exit(ExitCode.INSTALL_FAILED)

    # Verify installation
    if not verify_installation():
        sys.exit(ExitCode.VERIFICATION_FAILED)

    # We did it!
    source_shell_rc_msg: str = ''
    if shell := Shell.detect():
        source_shell_rc_msg = f' (or run: {style("source", fg="bright_magenta")} {pathstyle(shell.rc_file)})'

    printf('')
    printf('🎉 Installation complete!\n',                                          fg='bright_green', bold=True)
    if not args.ensure:
        printf('📋 Next steps:',                                                   fg='bright_cyan')
        printf(f'1. Close and reopen your terminal{source_shell_rc_msg}',          indent=3)
        printf(f'2. Verify with: {style("hatch --version", fg="bright_magenta")}', indent=3)
        printf(f'3. View documentation: {style(DOCS_URL, dim=True)}',              indent=3)
    sys.exit(ExitCode.SUCCESS)


if __name__ == '__main__':
    main()
