#!/usr/bin/env python3
"""
Collect a diagnostic snapshot of Python executables, virtualenvs, package managers, and system config.

Author:      Connor Mason
Source:      https://github.com/connormason/dotfiles/blob/main/scripts/env/python_diagnostic.py

This script collects comprehensive information about a user's Python environment to help diagnose installation and
configuration issues.

Output is colorized with ANSI escapes for terminal readability. Color honors the ``NO_COLOR`` environment variable
(https://no-color.org/) and the ``--no-color`` flag, and saved reports (``--save`` / ``--output``) are always written
without styling.

Usage::

    python3 python_diagnostic.py              # Print to stdout
    python3 python_diagnostic.py --no-color   # Print to stdout without ANSI escapes
    python3 python_diagnostic.py --save       # Save to file (plain text, no ANSI)
    python3 python_diagnostic.py --json       # Output as JSON

Options:
    --max-installed-packages NUM   Max number of installed python packages to list under "INSTALLED PACKAGES"
    --no-color                     Disable colored output (no ANSI escape sequences)
    -s, --save                     Save output to file instead of printing
    -j, --json                     Output as JSON format
    -o, --output FILEPATH          Output file path (default: python_diagnostic_<timestamp>.txt)
    -h, --help                     Show help message and exit

Environment:
    NO_COLOR              Disables ANSI styling when set (https://no-color.org/)
    CONDA_DEFAULT_ENV, CONDA_PREFIX, HATCH_ENV_ACTIVE, HATCH_UV, HOME, HOMEBREW_PREFIX, PATH, PIP_INDEX_URL, PWD,
    PYENV_ROOT, PYENV_VERSION, PYTHONHOME, PYTHONPATH, SHELL, TERM, UV_INDEX_URL, VIRTUAL_ENV, ZSH
                          Read verbatim (not modified) and reported in the "ENVIRONMENT VARIABLES" report section
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from collections.abc import Sequence
from datetime import datetime
from functools import partial
from operator import itemgetter
from pathlib import Path
from typing import Any
from typing import Literal
from typing import TypedDict
from typing import Union
from typing import cast

# ==================================================================================================
# Script configuration
# ==================================================================================================


#: Python executable names to look for in ``get_python_executables()``
PYTHON_EXECUTABLE_NAMES: list[str] = [
    'python',
    'python3',
    'python3.9',
    'python3.10',
    'python3.11',
    'python3.12',
    'python3.13',
    'python3.14',
]


# ==================================================================================================
# Types
# ==================================================================================================


PathLike   = Union[Path, str]
StyleColor = Union[int, tuple[int, int, int], str]


# ==================================================================================================
# Styling/formatting utils
# ==================================================================================================


#: Module-level color toggle. Disabled by ``--no-color`` (see :func:`main`); :func:`style` also honors ``NO_COLOR``.
COLOR_ENABLED = True


#: ANSI color escape code lookup
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


def set_color_enabled(enabled: bool) -> None:
    """
    Enable or disable ANSI styling globally for :func:`style`.

    :param enabled: True to emit ANSI escapes, False to return plain text
    """
    global COLOR_ENABLED
    COLOR_ENABLED = enabled


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
    italic: bool | None = None,
    reset: bool = True,
) -> str:
    """
    Style text with ANSI codes and return the new string.

    Returns plain text when color is disabled via :func:`set_color_enabled` (``--no-color``) or the ``NO_COLOR``
    environment variable (https://no-color.org/).

    :param text: the string to style with ansi codes
    :param fg: foreground color
    :param bg: background color
    :param bold: enable or disable bold mode
    :param dim: enable or disable dim mode
    :param underline: enable or disable underline
    :param italic: enable or disable italic
    :param reset: add a reset-all code at the end of the string
    :return: styled text
    """
    if (not COLOR_ENABLED) or (os.environ.get('NO_COLOR') is not None):
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
    if italic is not None:
        bits.append(f'\033[{3 if italic else 23}m')

    bits.append(text)
    if reset:
        bits.append(ANSI_RESET_ALL)
    return ''.join(bits)


def unstyle(text: str) -> str:
    """
    Removes ANSI styling information from a string.

    :param text: the text to remove style information from
    :return: string with ANSI styling characters removed
    """
    return re.sub(r'\033\[[;?0-9]*[a-zA-Z]', '', text)


def folduser(path: PathLike) -> str:
    """
    Replace the user's home directory prefix with ``~`` for display.

    :param path: file path to fold
    :return: path string with home directory replaced by ``~``
    """
    return str(path).replace(str(Path.home()), '~')


def pathstyle(path: PathLike, **opts: Any) -> str:
    """
    Style a file path in magenta with the home directory folded to ``~``.

    :param path: file path to style
    :return: ANSI-styled path string
    """
    return style(folduser(path), fg='magenta', **opts)


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


# ==================================================================================================
# Command execution
# ==================================================================================================


class ErrorDict(TypedDict):
    """
    Error information from a failed command.
    """
    error: str


class RunCommandResult(TypedDict, total=False):
    """
    Result of running a subprocess command.
    """
    stdout:     str
    stderr:     str
    returncode: int
    error:      bool
    message:    str


def run_command(cmd: list[str], **kwargs: Any) -> RunCommandResult:
    """
    Run a command and return output, error, and return code.

    :param cmd: command to run as list of arguments
    :return: dict with stdout, stderr, returncode, and error flag
    """
    try:
        result = subprocess.run(
            cmd,
            check=kwargs.pop('check', False),
            capture_output=kwargs.pop('capture_output', True),
            text=kwargs.pop('text', True),
            timeout=kwargs.pop('timeout', 5),
            **kwargs,
        )
    except FileNotFoundError:
        return dict(error=True, message='Command not found')
    except subprocess.TimeoutExpired:
        return dict(error=True, message='Command timed out')
    except Exception as e:
        return dict(error=True, message=str(e))
    else:
        return dict(
            stdout=result.stdout.strip(),
            stderr=result.stderr.strip(),
            returncode=result.returncode,
            error=False,
        )


# ==================================================================================================
# Python executable info
# ==================================================================================================


class PythonExecutable(TypedDict):
    """
    Information about a discovered Python executable.
    """
    path:       str
    real_path:  str
    version:    str
    is_symlink: bool


def get_python_executables() -> dict[str, PythonExecutable]:
    """
    Find all Python executables in PATH.

    :return: mapping from executable name -> path/version info (:class:`PythonExecutable`)
    """
    executables: dict[str, PythonExecutable] = {}
    for name in PYTHON_EXECUTABLE_NAMES:
        if path := shutil.which(name):
            version_info = run_command([name, '--version'])
            executables[name] = {
                'path':       path,
                'real_path':  str(Path(path).resolve()),
                'version':    version_info.get('stdout', version_info.get('stderr', 'Unknown')),
                'is_symlink': Path(path).is_symlink(),
            }

    return executables


# ==================================================================================================
# Package manager info
# ==================================================================================================


class VersionParts(TypedDict):
    """
    Parsed semantic version components.
    """
    major: int
    minor: int
    patch: int


# `pip` info types
# ------------------------------------------------------------------------------

class PipInfo(TypedDict):
    """
    Pip installation paths and version.
    """
    pip_path:  str | None
    pip3_path: str | None
    version:   str


# `uv` info types
# ------------------------------------------------------------------------------

class UvInstalledPython(TypedDict):
    """
    Details of a single Python installation managed by uv.
    """
    key:            str
    version:        str
    version_parts:  VersionParts
    path:           str
    symlink:        str | None
    url:            str | None
    os:             str
    variant:        str
    implementation: str
    arch:           str
    libc:           str


class UvInstalledPythons(TypedDict):
    """
    Collection of Python installations managed by uv.
    """
    installed: list[UvInstalledPython]


UvPythons = Union[UvInstalledPythons, ErrorDict]


class UvInfo(TypedDict):
    """
    Uv tool path, version, and managed Python installations.
    """
    path:    str
    version: str
    pythons: UvPythons


# `hatch` info types
# ------------------------------------------------------------------------------

class HatchEnvironment(TypedDict):
    """
    Configuration for a single Hatch virtual environment.
    """
    type:      Literal['virtual']
    python:    str
    installer: str


HatchEnvironments = Union[dict[str, HatchEnvironment], ErrorDict]


class HatchInfo(TypedDict):
    """
    Hatch tool path, version, and environment configuration.
    """
    path:         str
    version:      str
    environments: HatchEnvironments


class PackageManagerInfo(TypedDict, total=False):
    """
    Dict schema with info about a package manager (values in dict returned by :func:`get_package_manager_info`).
    """
    pip:   PipInfo
    uv:    UvInfo
    hatch: HatchInfo


def get_package_manager_info() -> PackageManagerInfo:
    """
    Get information about package managers (pip, uv, hatch).

    :return: mapping from package manager name -> path/version info (:class:`PackageManagerInfo`)
    """
    managers: PackageManagerInfo = PackageManagerInfo()

    # Check pip
    pip_path  = shutil.which('pip')
    pip3_path = shutil.which('pip3')
    if pip_path or pip3_path:
        pip_version = run_command([cast('str', pip3_path or pip_path), '--version'])
        managers['pip'] = PipInfo(
            pip_path=pip_path,
            pip3_path=pip3_path,
            version=pip_version.get('stdout', 'Unknown'),
        )

    # Check uv
    if uv_path := shutil.which('uv'):
        uv_version = run_command([uv_path, '--color', 'never', '--version'])
        uv_python  = run_command([
            uv_path,
            '--color',
            'never',
            'python',
            'list',
            '--only-installed',
            '--output-format',
            'json',
        ])

        pythons: UvPythons
        if uv_python.get('error'):
            pythons = ErrorDict(error=uv_python.get('message', 'Unknown error'))
        elif uv_python.get('returncode') != 0:
            pythons = ErrorDict(error=f"`uv python list` failed: {uv_python.get('stderr', 'Unknown error')}")
        else:
            try:
                pythons = UvInstalledPythons(installed=json.loads(uv_python['stdout']))
            except (json.JSONDecodeError, KeyError) as e:
                pythons = ErrorDict(error=f'Failed to parse `uv python list` output: {e}')

        managers['uv'] = UvInfo(
            path=uv_path,
            version=uv_version.get('stdout', 'Unknown'),
            pythons=pythons,
        )

    # Check hatch
    if hatch_path := shutil.which('hatch'):
        hatch_version = run_command([hatch_path, '--no-color', '--version'])
        hatch_envs    = run_command([hatch_path, '--no-color', 'env', 'show', '--json'])

        environments: HatchEnvironments
        if hatch_envs.get('error'):
            environments = ErrorDict(error=hatch_envs.get('message', 'Unknown error'))
        elif hatch_envs.get('returncode') != 0:
            environments = ErrorDict(error=f"`hatch env show` failed: {hatch_envs.get('stderr', 'Unknown error')}")
        else:
            try:
                environments = json.loads(hatch_envs['stdout'])
            except (json.JSONDecodeError, KeyError) as e:
                environments = ErrorDict(error=f'Failed to parse `hatch env show` output: {e}')

        managers['hatch'] = HatchInfo(
            path=hatch_path,
            version=hatch_version.get('stdout', 'Unknown'),
            environments=environments,
        )

    return managers


# ==================================================================================================
# Virtual environment info
# ==================================================================================================


class VirtualenvInfo(TypedDict):
    """
    Current virtual environment state and prefix paths.
    """
    in_virtualenv:   bool
    virtual_env:     str | None
    conda_env:       str | None
    sys_prefix:      str
    sys_base_prefix: str | None
    sys_real_prefix: str | None


def get_virtual_env_info() -> VirtualenvInfo:
    """
    Get information about current virtual environment.

    :return: dict with virtual environment details (:class:`VirtualenvInfo`)
    """
    return {
        'in_virtualenv':   hasattr(sys, 'real_prefix') or (
            hasattr(sys, 'base_prefix') and (sys.base_prefix != sys.prefix)
        ),
        'virtual_env':     os.environ.get('VIRTUAL_ENV'),
        'conda_env':       os.environ.get('CONDA_DEFAULT_ENV'),
        'sys_prefix':      sys.prefix,
        'sys_base_prefix': getattr(sys, 'base_prefix', None),
        'sys_real_prefix': getattr(sys, 'real_prefix', None),
    }


# ==================================================================================================
# Environment variables
# ==================================================================================================


def get_environment_variables() -> dict[str, str | None]:
    """
    Get relevant environment variables (non-sensitive).

    :return: dict of environment variables
    """
    return {
        'CONDA_DEFAULT_ENV': os.environ.get('CONDA_DEFAULT_ENV'),
        'CONDA_PREFIX':      os.environ.get('CONDA_PREFIX'),
        'HATCH_ENV_ACTIVE':  os.environ.get('HATCH_ENV_ACTIVE'),
        'HATCH_UV':          os.environ.get('HATCH_UV'),
        'HOME':              os.environ.get('HOME'),
        'HOMEBREW_PREFIX':   os.environ.get('HOMEBREW_PREFIX'),
        'PATH':              os.environ.get('PATH'),
        'PIP_INDEX_URL':     os.environ.get('PIP_INDEX_URL'),
        'PWD':               os.environ.get('PWD'),
        'PYENV_ROOT':        os.environ.get('PYENV_ROOT'),
        'PYENV_VERSION':     os.environ.get('PYENV_VERSION'),
        'PYTHONHOME':        os.environ.get('PYTHONHOME'),
        'PYTHONPATH':        os.environ.get('PYTHONPATH'),
        'SHELL':             os.environ.get('SHELL'),
        'TERM':              os.environ.get('TERM'),
        'UV_INDEX_URL':      os.environ.get('UV_INDEX_URL'),
        'VIRTUAL_ENV':       os.environ.get('VIRTUAL_ENV'),
        'ZSH':               os.environ.get('ZSH'),
    }


# ==================================================================================================
# Python path info
# ==================================================================================================


class PythonPaths(TypedDict):
    """
    Python interpreter paths and site-packages locations.
    """
    sys_executable: str
    sys_path:       list[str]
    site_packages:  list[str]
    user_base:      str | None
    user_site:      str | None


def get_python_paths() -> PythonPaths:
    """
    Get Python-specific paths and configuration.

    :return: dict with Python paths (:class;`PythonPaths`)
    """
    return {
        'sys_executable': sys.executable,
        'sys_path':       sys.path,
        'site_packages':  [p for p in sys.path if 'site-packages' in p],
        'user_base':      getattr(sys, 'user_base', None),
        'user_site':      getattr(sys, 'user_site', None),
    }


# ==================================================================================================
# System info
# ==================================================================================================


class SystemInfo(TypedDict):
    """
    Host system platform, architecture, and OS version details.
    """
    platform:              str
    machine:               str
    processor:             str
    python_version:        str
    python_implementation: str
    sw_vers:               str
    uname:                 str


def get_system_info() -> SystemInfo:
    """
    Get macOS system information.

    :return: dict with system details (:class:`SystemInfo`)
    """
    sw_vers = run_command(['sw_vers'])
    uname   = run_command(['uname', '-a'])
    return {
        'platform':              platform.platform(),
        'machine':               platform.machine(),
        'processor':             platform.processor(),
        'python_version':        sys.version,
        'python_implementation': platform.python_implementation(),
        'sw_vers':               sw_vers.get('stdout', ''),
        'uname':                 uname.get('stdout', ''),
    }


# ==================================================================================================
# Python installation
# ==================================================================================================


class PythonInstallation(TypedDict):
    """
    Existence and symlink info for a Python installation at a known path.
    """
    exists:      bool
    description: str
    is_symlink:  bool | None
    resolved:    str | None


def check_common_locations() -> dict[str, PythonInstallation]:
    """
    Check for Python installations in common locations.

    :return: mapping from paths -> python installation info/existence info (:class:`PythonInstallation`)
    """
    common_paths: dict[str, str] = {
        '/usr/bin/python3':                     'System Python',
        '/usr/local/bin/python3':               'Homebrew Python (Intel)',
        '/opt/homebrew/bin/python3':            'Homebrew Python (Apple Silicon)',
        str(Path.home() / '.pyenv'):            'pyenv installation',
        str(Path.home() / 'Library/Python'):    'User Python packages',
        '/Library/Frameworks/Python.framework': 'Python.org installation',
        str(Path.home() / '.local/bin'):        'User local binaries',
    }

    return {
        path: {
            'exists':      Path(path).exists(),
            'description': desc,
            'is_symlink':  Path(path).is_symlink()   if Path(path).exists() else None,
            'resolved':    str(Path(path).resolve()) if Path(path).exists() else None,
        }
        for path, desc in common_paths.items()
    }


# ==================================================================================================
# Installed Python packages
# ==================================================================================================


class InstalledPythonVersions(TypedDict):
    """
    Installed Python package versions and editable project locations.
    """
    versions:           dict[str, str]        # package name -> version
    editable_locations: dict[str, str]        # package name -> editable project location (path)


InstalledPythonPackages = Union[
    InstalledPythonVersions,
    ErrorDict,
]


def get_installed_packages() -> InstalledPythonPackages:
    """
    Get list of installed packages in current environment.

    :return: dict containing "versions" (mapping from package name -> version) and "editable_locations" (mapping from
             package name -> editable project location), or dict with single "error" entry if `pip` command fails
    """
    if uv_path := shutil.which('uv'):
        pip_list = run_command([uv_path, 'pip', 'list', '--format=json'])
    else:
        pip_list = run_command([sys.executable, '-m', 'pip', 'list', '--format=json'])

    if pip_list.get('error'):
        return ErrorDict(error=pip_list.get('message', 'Unknown error'))
    if pip_list.get('returncode') != 0:
        return ErrorDict(error=f"`pip list` failed: {pip_list.get('stderr', 'Unknown error')}")
    try:
        pip_list_packages = json.loads(pip_list['stdout'])
    except (json.JSONDecodeError, KeyError) as e:
        return ErrorDict(error=f'Failed to parse `pip list` output: {e}')
    else:
        packages: InstalledPythonVersions = InstalledPythonVersions(versions={}, editable_locations={})
        for pkg in pip_list_packages:
            packages['versions'][pkg['name']] = pkg['version']
            if editable_location := pkg.get('editable_project_location'):
                packages['editable_locations'][pkg['name']] = editable_location
        return packages


# ==================================================================================================
# Top-level diagnostics compilation/formatting
# ==================================================================================================


class Diagnostics(TypedDict):
    """
    Complete Python environment diagnostic report.
    """
    timestamp:             str
    system:                SystemInfo
    python_executables:    dict[str, PythonExecutable]
    virtual_env:           VirtualenvInfo
    package_managers:      PackageManagerInfo
    environment_variables: dict[str, str | None]
    python_paths:          PythonPaths
    common_locations:      dict[str, PythonInstallation]
    installed_packages:    InstalledPythonPackages


def collect_diagnostics() -> Diagnostics:
    """
    Collect all diagnostic information.

    :return: complete diagnostic data dict (:class:`Diagnostics`)
    """
    return {
        'timestamp':             datetime.now().isoformat(),
        'system':                get_system_info(),
        'python_executables':    get_python_executables(),
        'virtual_env':           get_virtual_env_info(),
        'package_managers':      get_package_manager_info(),
        'environment_variables': get_environment_variables(),
        'python_paths':          get_python_paths(),
        'common_locations':      check_common_locations(),
        'installed_packages':    get_installed_packages(),
    }


# Report styling helpers
# ----------------------

#: Width of the report banner and section separator rules
REPORT_WIDTH = 80

#: Label-column widths for the aligned ``label  value`` rows in each section
SYS_FIELD_WIDTH  = 22
VENV_FIELD_WIDTH = 23
EXEC_FIELD_WIDTH = 11
PKG_FIELD_WIDTH  = 10


def _banner(title: str) -> list[str]:
    """
    Build the three-line report banner (rule, title, rule) in cyan.

    :param title: banner title text
    :return: list of styled lines
    """
    rule = style('═' * REPORT_WIDTH, fg='bright_blue')
    return [rule, style(title, fg='bright_blue', bold=True), rule]


def _section(title: str) -> list[str]:
    """
    Build a section header: a blank spacer, the bold title, and a dimmed separator rule.

    :param title: section title text
    :return: list of styled lines
    """
    return ['', style(title, fg='bright_white', bold=True), style('─' * REPORT_WIDTH, dim=True)]


def _label(text: str) -> str:
    """
    Style a field label (dimmed white).

    :param text: label text
    :return: styled label
    """
    return style(text, fg='bright_white', dim=True)


def _field(label: str, value: str, *, indent: int = 0, width: int = 0) -> str:
    """
    Render an aligned ``label  value`` row with a dimmed label.

    :param label: label text (including any trailing colon)
    :param value: already-styled value text
    :param indent: number of leading spaces
    :param width: label column width to pad to (0 leaves the label unpadded)
    :return: formatted row
    """
    return f'{" " * indent}{_label(label.ljust(width))} {value}'


def _as_path(value: str | None) -> Path | None:
    """
    Coerce an optional path string to :class:`Path`, preserving ``None``.

    Lets :func:`typestyle` render the value as a folded magenta path (or magenta italic ``None`` when absent).

    :param value: path string or None
    :return: :class:`Path` wrapping the value, or None
    """
    return None if value is None else Path(value)


def format_diagnostic_output(data: Diagnostics, *, max_installed_packages: int | None = None) -> str:
    """
    Format diagnostic data for human-readable (ANSI-styled) output.

    Color is applied via :func:`style`, which honors ``NO_COLOR``. Callers writing the result to a file should strip
    styling first with :func:`unstyle`.

    :param data: diagnostic data dict
    :param max_installed_packages: maximum number of installed python packages to list in "INSTALLED PACKAGES" section
                                   before truncating list. If None, all installed packages will be outputted
    :return: formatted (ANSI-styled) string output
    """
    system = data['system']
    sysf   = partial(_field, width=SYS_FIELD_WIDTH)

    # Header + system info from `get_system_info`
    lines: list[str] = [
        *_banner('PYTHON ENVIRONMENT DIAGNOSTIC REPORT'),
        _field('Generated:', style(data['timestamp'],                         fg='bright_cyan')),
        *_section('SYSTEM INFORMATION'),
        sysf('Platform:',              style(system['platform'],              fg='bright_white')),
        sysf('Architecture:',          style(system['machine'],               fg='bright_white')),
        sysf('Python Version:',        style(system['python_version'],        fg='bright_cyan')),
        sysf('Python Implementation:', style(system['python_implementation'], fg='bright_cyan')),
        '',
        _label('macOS Version:'),
        system['sw_vers'],
        *_section('PYTHON EXECUTABLES IN PATH'),
    ]

    # Python executables from `get_python_executables`
    if data['python_executables']:
        execf = partial(_field, indent=2, width=EXEC_FIELD_WIDTH)
        for name, py_exc_info in data['python_executables'].items():
            lines.extend([
                f'\n{style(f"{name}:", fg="bright_magenta", bold=True)}',
                execf('Path:',       pathstyle(py_exc_info['path'])),
                execf('Real Path:',  pathstyle(py_exc_info['real_path'])),
                execf('Version:',    style(py_exc_info['version'], fg='bright_cyan')),
                execf('Is Symlink:', typestyle(py_exc_info['is_symlink'])),
            ])
    else:
        lines.append(style('  No Python executables found in PATH', fg='bright_yellow'))

    # Virtual environment status from `get_virtual_env_info`
    venv  = data['virtual_env']
    venvf = partial(_field, width=VENV_FIELD_WIDTH)
    lines.extend([
        *_section('VIRTUAL ENVIRONMENT STATUS'),
        venvf('In Virtual Environment:', typestyle(venv['in_virtualenv'])),
        venvf('VIRTUAL_ENV:',            typestyle(_as_path(venv['virtual_env']))),
        venvf('CONDA_DEFAULT_ENV:',      typestyle(venv['conda_env'])),
        venvf('sys.prefix:',             pathstyle(venv['sys_prefix'])),
        venvf('sys.base_prefix:',        typestyle(_as_path(venv['sys_base_prefix']))),
        *_section('PACKAGE MANAGERS'),
    ])

    # Package manager info from `get_package_manager_info`
    managers = data['package_managers']
    pkgf     = partial(_field, indent=2, width=PKG_FIELD_WIDTH)
    if 'pip' in managers:
        pip_info = managers['pip']
        lines.extend([
            f'\n{style("pip:", fg="bright_magenta", bold=True)}',
            pkgf('pip path:',  typestyle(_as_path(pip_info['pip_path']))),
            pkgf('pip3 path:', typestyle(_as_path(pip_info['pip3_path']))),
            pkgf('Version:',   style(pip_info['version'], fg='bright_cyan')),
        ])

    if 'uv' in managers:
        uv_info = managers['uv']
        lines.extend([
            f'\n{style("uv:", fg="bright_magenta", bold=True)}',
            pkgf('Path:',    pathstyle(uv_info['path'])),
            pkgf('Version:', style(uv_info['version'], fg='bright_cyan')),
            f'\n  {_label("Python installations:")}',
        ])

        try:
            installed_pythons = uv_info['pythons']['installed']     # type: ignore[typeddict-item]
        except KeyError:
            pass
        else:
            col1_width:           int = 0
            python_installations: list[tuple[str, str]] = []
            for py_inst in installed_pythons:
                if (key := py_inst.get('key')) and (path := py_inst.get('path')):
                    python_installations.append((
                        key,
                        f'{path} -> {py_inst["symlink"]}' if py_inst['symlink'] else path,
                    ))
                    col1_width = max(col1_width, len(key))

            for key, path in python_installations:
                lines.append(f'    {style(key.ljust(col1_width + 4), fg="bright_cyan")} {pathstyle(path)}')

    if 'hatch' in managers:
        hatch_info = managers['hatch']
        lines.extend([
            f'\n{style("hatch:", fg="bright_magenta", bold=True)}',
            pkgf('Path:',    pathstyle(hatch_info['path'])),
            pkgf('Version:', style(hatch_info['version'], fg='bright_cyan')),
        ])

    # Environment variables from `get_environment_variables`
    lines.extend(_section('ENVIRONMENT VARIABLES'))

    env_vars: dict[str, str] = {
        var: value
        for var, value in sorted(data['environment_variables'].items(), key=itemgetter(0))
        if value is not None
    }
    if env_vars:
        env_col_width = len(max(env_vars.keys(), key=len)) + 1
        for var, value in env_vars.items():
            if value and (var != 'PATH'):
                var_ljust = f'{var}:'.ljust(env_col_width)
                lines.append(f'{style(var_ljust, fg="yellow")} {folduser(value)}')

    if path_envvar := data['environment_variables'].get('PATH'):
        lines.append(f'\n{style("PATH:", fg="yellow")}')
        lines.extend(f'  {pathstyle(path)}' for path in path_envvar.split(os.pathsep))

    # Python paths from `get_python_paths`
    py_paths = data['python_paths']
    lines.extend([
        *_section('PYTHON PATHS'),
        _field('sys.executable:', pathstyle(py_paths['sys_executable'])),
        f'\n{_label("sys.path:")}',
        *[f'  {pathstyle(path)}' for path in py_paths['sys_path']],
    ])

    # Common installation locations from `check_common_locations`
    lines.extend(_section('COMMON INSTALLATION LOCATIONS'))
    for path, py_inst_info in data['common_locations'].items():
        icon = style('✓', fg='bright_green') if py_inst_info['exists'] else style('✗', fg='bright_red')
        lines.append(f"{icon} {style(py_inst_info['description'], fg='bright_white')}: {pathstyle(path)}")
        if py_inst_info['exists'] and py_inst_info['is_symlink'] and (resolved := py_inst_info['resolved']):
            lines.append(f"  {style('→', dim=True)} {pathstyle(resolved, dim=True)}")

    # Installed packages from `get_installed_packages`
    if max_installed_packages:
        pkg_title = f'INSTALLED PACKAGES (first {max_installed_packages})'
    else:
        pkg_title = 'INSTALLED PACKAGES'
    lines.extend(_section(pkg_title))

    packages = data['installed_packages']
    if isinstance(packages, dict) and ('error' not in packages):
        pkg_versions       = cast('dict[str, str]', packages.get('versions', {}))
        editable_locations = cast('dict[str, str]', packages.get('editable_locations', {}))

        shown: dict[str, str] = {
            name: vers
            for i, (name, vers) in enumerate(pkg_versions.items())
            if (max_installed_packages is None) or (i < max_installed_packages)
        }
        col1_width = max((len(f'{name}=={vers}') for name, vers in shown.items()), default=0)

        for name, vers in shown.items():
            spec = f'{style(name, fg="bright_white")}{style("==", dim=True)}{style(vers, fg="bright_cyan")}'
            if loc := editable_locations.get(name):
                gap  = ' ' * (col1_width - len(f'{name}=={vers}'))
                spec = f'{spec}{gap}        {pathstyle(loc)}'
            lines.append(f'  {spec}')

        if max_installed_packages and (len(pkg_versions) > max_installed_packages):
            remaining = len(pkg_versions) - max_installed_packages
            lines.append(style(f'  ... and {remaining} more packages', dim=True))

    else:
        error_msg = packages.get('error', 'Unknown error')
        lines.append(f"  {style('Error:', fg='bright_red', bold=True)} {style(error_msg, fg='bright_yellow')}")

    lines.extend([
        '',
        *_banner('END OF DIAGNOSTIC REPORT'),
    ])
    return '\n'.join(lines)


# ==================================================================================================
# Argument parsing and core script entry point
# ==================================================================================================


class Args(argparse.Namespace):
    """
    Annotated :class:`argparse.Namespace` for script command-line arguments.
    """
    max_installed_packages: int | None      # --max-installed-packages
    no_color:               bool            # --no-color
    save:                   bool            # -s/--save
    json:                   bool            # -j, --json
    output:                 Path | None     # -o/--output


def build_parser() -> argparse.ArgumentParser:
    """
    Build argument parser for script.

    :return: :class:`argparse.ArgumentParser`
    """
    parser = argparse.ArgumentParser(
        description=style('Collect Python environment diagnostic information', fg='bright_magenta'),
        formatter_class=partial(argparse.RawTextHelpFormatter, max_help_position=50),
        add_help=False,
    )

    def add_console_out_opts() -> None:
        """
        Add console output options group to the argument parser.
        """
        console_out_opts = parser.add_argument_group(style('Console output options', fg='bright_white'))
        console_out_opts.add_argument(
            '--max-installed-packages',
            metavar='NUM',
            type=int,
            help='Max number of installed python packages to list under "INSTALLED PACKAGES"',
        )
        console_out_opts.add_argument(
            '--no-color',
            action='store_true',
            help='Disable colored output (no ANSI escape sequences)',
        )
    add_console_out_opts()

    def add_file_out_opts() -> None:
        """
        Add file output options group to the argument parser.
        """
        file_out_opts = parser.add_argument_group(style('File output options', fg='bright_white'))
        file_out_opts.add_argument(
            '-s',
            '--save',
            action='store_true',
            help='Save output to file instead of printing',
        )
        file_out_opts.add_argument(
            '-j',
            '--json',
            action='store_true',
            help='Output as JSON format',
        )
        file_out_opts.add_argument(
            '-o',
            '--output',
            type=Path,
            metavar='FILEPATH',
            help='Output file path (default: python_diagnostic_<timestamp>.txt)',
        )
    add_file_out_opts()

    def add_other_opts() -> None:
        """
        Add miscellaneous options group to the argument parser.
        """
        other_opts = parser.add_argument_group(style('Other options', fg='bright_white'))
        other_opts.add_argument(
            '-h',
            '--help',
            action='help',
            default=argparse.SUPPRESS,
            help='Show help message and exit',
        )
    add_other_opts()

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """
    Main entry point.

    :param argv: argument list to parse, defaults to sys.argv[1:]
    :return: int script exit code
    """
    parser = build_parser()
    args   = parser.parse_args(argv, namespace=Args())

    if args.no_color:
        set_color_enabled(False)

    print(style('Collecting diagnostic information...', fg='bright_cyan'), file=sys.stderr)
    data = collect_diagnostics()

    extension: Literal['json', 'txt']
    if args.json:
        output    = json.dumps(data, indent=4)
        extension = 'json'
    else:
        output    = format_diagnostic_output(data, max_installed_packages=args.max_installed_packages)
        extension = 'txt'

    if args.save or args.output:
        if args.output:
            output_path = Path(args.output).expanduser().resolve()
        else:
            timestamp   = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_path = Path(f'python_diagnostic_{timestamp}.{extension}')

        # Saved reports are always plain text -- strip ANSI styling from the human-readable report
        output_path.write_text(unstyle(output) if extension == 'txt' else output)
        print(file=sys.stderr)
        print(
            f'{style("✓", fg="bright_green")} Diagnostic report saved to: {pathstyle(output_path)}',
            file=sys.stderr,
        )
        print(style(f'File size: {output_path.stat().st_size} bytes', dim=True), file=sys.stderr)
    else:
        print(output)

    return 0


if __name__ == '__main__':
    sys.exit(main())
