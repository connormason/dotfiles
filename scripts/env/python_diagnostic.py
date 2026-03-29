#!/usr/bin/env python3
"""
Python Environment Diagnostic Tool

This script collects comprehensive information about a user's Python environment to help diagnose installation and
configuration issues.

Usage::

    python3 python_diagnostic.py              # Print to stdout
    python3 python_diagnostic.py --save       # Save to file
    python3 python_diagnostic.py --json       # Output as JSON

"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime
from functools import partial
from operator import itemgetter
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from typing import Literal
from typing import TypedDict
from typing import Union
from typing import cast

if TYPE_CHECKING:
    from collections.abc import Sequence


# ====================
# Script configuration
# ====================

#: Python executable names to look for in ``get_python_executables()``
PYTHON_EXECUTABLE_NAMES: list[str] = [
    'python',
    'python3',
    'python3.9',
    'python3.10',
    'python3.11',
    'python3.12',
    'python3.13',
]


# =================
# Command execution
# =================


class ErrorDict(TypedDict):
    error: str


class RunCommandResult(TypedDict, total=False):
    stdout:     str
    stderr:     str
    returncode: int
    error:      bool
    message:    str


def run_command(cmd: list[str], **kwargs: Any) -> RunCommandResult:
    """
    Run a command and return output, error, and return code

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


# ======================
# Python executable info
# ======================


class PythonExecutable(TypedDict):
    path:       str
    real_path:  str
    version:    str
    is_symlink: bool


def get_python_executables() -> dict[str, PythonExecutable]:
    """
    Find all Python executables in PATH

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


# ====================
# Package manager info
# ====================


class VersionParts(TypedDict):
    major: int
    minor: int
    patch: int


""" `pip` info types """


class PipInfo(TypedDict):
    pip_path:  str | None
    pip3_path: str | None
    version:   str


""" `uv` info types """


class UvInstalledPython(TypedDict):
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
    installed: list[UvInstalledPython]


UvPythons = Union[UvInstalledPythons, ErrorDict]


class UvInfo(TypedDict):
    path:    str
    version: str
    pythons: UvPythons


""" `hatch` info types """


class HatchEnvironment(TypedDict):
    type:      Literal['virtual']
    python:    str
    installer: str


HatchEnvironments = Union[dict[str, HatchEnvironment], ErrorDict]


class HatchInfo(TypedDict):
    path:         str
    version:      str
    environments: HatchEnvironments


class PackageManagerInfo(TypedDict, total=False):
    """
    Dict schema with info about a package manager (values in dict returned by :func:`get_package_manager_info`)
    """
    pip:   PipInfo
    uv:    UvInfo
    hatch: HatchInfo


def get_package_manager_info() -> PackageManagerInfo:
    """
    Get information about package managers (pip, uv, hatch)

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


# ========================
# Virtual environment info
# ========================


class VirtualenvInfo(TypedDict):
    in_virtualenv:   bool
    virtual_env:     str | None
    conda_env:       str | None
    sys_prefix:      str
    sys_base_prefix: str | None
    sys_real_prefix: str | None


def get_virtual_env_info() -> VirtualenvInfo:
    """
    Get information about current virtual environment

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


# =====================
# Environment variables
# =====================


def get_environment_variables() -> dict[str, str | None]:
    """
    Get relevant environment variables (non-sensitive)

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


# ================
# Python path info
# ================


class PythonPaths(TypedDict):
    sys_executable: str
    sys_path:       list[str]
    site_packages:  list[str]
    user_base:      str | None
    user_site:      str | None


def get_python_paths() -> PythonPaths:
    """
    Get Python-specific paths and configuration

    :return: dict with Python paths (:class;`PythonPaths`)
    """
    return {
        'sys_executable': sys.executable,
        'sys_path':       sys.path,
        'site_packages':  [p for p in sys.path if 'site-packages' in p],
        'user_base':      getattr(sys, 'user_base', None),
        'user_site':      getattr(sys, 'user_site', None),
    }


# ===========
# System info
# ===========


class SystemInfo(TypedDict):
    platform:              str
    machine:               str
    processor:             str
    python_version:        str
    python_implementation: str
    sw_vers:               str
    uname:                 str


def get_system_info() -> SystemInfo:
    """
    Get macOS system information

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


# ===================
# Python installation
# ===================


class PythonInstallation(TypedDict):
    exists:      bool
    description: str
    is_symlink:  bool | None
    resolved:    str | None


def check_common_locations() -> dict[str, PythonInstallation]:
    """
    Check for Python installations in common locations

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


# =========================
# Installed Python packages
# =========================


class InstalledPythonVersions(TypedDict):
    versions:           dict[str, str]        # package name -> version
    editable_locations: dict[str, str]        # package name -> editable project location (path)


InstalledPythonPackages = Union[
    InstalledPythonVersions,
    ErrorDict,
]


def get_installed_packages() -> InstalledPythonPackages:
    """
    Get list of installed packages in current environment

    :return: dict containing "versions" (mapping from package name -> version) and "editable_locations" (mapping from
             package name -> editable project location), or dict with single "error" entry if `pip` command fails
    """
    if uv_path := shutil.which('uv'):
        pip_list = run_command([uv_path, 'pip', 'list', '--format=json'])
    else:
        pip_list = run_command([sys.executable, '-m', 'pip', 'list', '--format=json'])

    if pip_list.get('error'):
        return ErrorDict(error=pip_list.get('message', 'Unknown error'))
    elif pip_list.get('returncode') != 0:
        return ErrorDict(error=f"`pip list` failed: {pip_list.get('stderr', 'Unknown error')}")
    else:
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


# ============================================
# Top-level diagnostics compilation/formatting
# ============================================


class Diagnostics(TypedDict):
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
    Collect all diagnostic information

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


def format_diagnostic_output(data: Diagnostics, *, max_installed_packages: int | None = None) -> str:
    """
    Format diagnostic data for human-readable output

    :param data: diagnostic data dict
    :param max_installed_packages: maximum number of installed python packages to list in "INSTALLED PACKAGES" section before
                         truncating list. If None, all installed packages will be outputted
    :return: formatted string output
    """

    """ Header + system info from :func:`get_system_info` """

    lines: list[str] = [
        '=' * 80,
        'PYTHON ENVIRONMENT DIAGNOSTIC REPORT',
        '=' * 80,
        f"Generated: {data['timestamp']}",
        '',
        'SYSTEM INFORMATION',
        '-' * 80,
        f"Platform:               {data['system']['platform']}",
        f"Architecture:           {data['system']['machine']}",
        f"Python Version:         {data['system']['python_version']}",
        f"Python Implementation:  {data['system']['python_implementation']}",
        '',
        'macOS Version:',
        data['system']['sw_vers'],
        '',
        'PYTHON EXECUTABLES IN PATH',
        '-' * 80,
    ]

    """ Python executables from :func: `get_python_executables` """

    if data['python_executables']:
        for name, py_exc_info in data['python_executables'].items():
            lines.extend([
                f'\n{name}:',
                f"  Path:       {py_exc_info['path']}",
                f"  Real Path:  {py_exc_info['real_path']}",
                f"  Version:    {py_exc_info['version']}",
                f"  Is Symlink: {py_exc_info['is_symlink']}",
            ])
    else:
        lines.append('  No Python executables found in PATH')

    """ Virtual environment status from :func: `get_virtual_env_info` """

    lines.extend([
        '',
        'VIRTUAL ENVIRONMENT STATUS',
        '-' * 80,
        f"In Virtual Environment: {data['virtual_env']['in_virtualenv']}",
        f"VIRTUAL_ENV:            {data['virtual_env']['virtual_env']}",
        f"CONDA_DEFAULT_ENV:      {data['virtual_env']['conda_env']}",
        f"sys.prefix:             {data['virtual_env']['sys_prefix']}",
        f"sys.base_prefix:        {data['virtual_env']['sys_base_prefix']}",
        '',
        'PACKAGE MANAGERS',
        '-' * 80,
    ])

    """ Package manager info from :func:`get_package_manager_info` """

    if 'pip' in data['package_managers']:
        pip_info = data['package_managers']['pip']
        lines.extend([
            '\npip:',
            f"  pip path:  {pip_info['pip_path']}",
            f"  pip3 path: {pip_info['pip3_path']}",
            f"  Version:   {pip_info['version']}",
        ])

    if 'uv' in data['package_managers']:
        uv_info = data['package_managers']['uv']
        lines.extend([
            '\nuv:',
            f"  Path:      {uv_info['path']}",
            f"  Version:   {uv_info['version']}",
            '\n  Python installations:',
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
                        f'{path} -> {py_inst["symlink"]}' if py_inst['symlink'] else path
                    ))
                    col1_width = max(col1_width, len(key))

            for key, path in python_installations:
                lines.append(f'    {key.ljust(col1_width + 4)} {path}')

    if 'hatch' in data['package_managers']:
        hatch_info = data['package_managers']['hatch']
        lines.extend([
            '\nhatch:',
            f"  Path:      {hatch_info['path']}",
            f"  Version:   {hatch_info['version']}",
        ])

    """ Environment variables from :func:`get_environment_variables` """

    lines.extend([
        '',
        'ENVIRONMENT VARIABLES',
        '-' * 80,
    ])

    env_vars: dict[str, str] = {
        var: value
        for var, value in sorted(data['environment_variables'].items(), key=itemgetter(0))
        if value is not None
    }
    col1_width = len(max(env_vars.keys(), key=len)) + 1

    for var, value in env_vars.items():
        if value and (var != 'PATH'):
            var_ljust = f'{var}:'.ljust(col1_width)
            lines.append(f'{var_ljust} {value}')

    if path_envvar := data['environment_variables'].get('PATH'):
        lines.append('\nPATH:')
        for path in path_envvar.split(':'):
            lines.append(f'  {path}')

    """ Python paths from :func:`get_python_paths` """

    lines.extend([
        '',
        'PYTHON PATHS',
        '-' * 80,
        f"sys.executable: {data['python_paths']['sys_executable']}",
        '\nsys.path:',
    ])

    for path in data['python_paths']['sys_path']:
        lines.append(f'  {path}')

    """ Common installation locations from :func:`check_common_locations` """

    lines.extend([
        '',
        'COMMON INSTALLATION LOCATIONS',
        '-' * 80,
    ])

    for path, py_inst_info in data['common_locations'].items():
        status = '✓' if py_inst_info['exists'] else '✗'
        lines.append(f"{status} {py_inst_info['description']}: {path}")
        if py_inst_info['exists'] and py_inst_info['is_symlink']:
            lines.append(f"  → {py_inst_info['resolved']}")

    """ Installed packages from :func:`get_installed_packages` """

    lines.extend([
        '',
        f'INSTALLED PACKAGES (first {max_installed_packages})' if max_installed_packages else 'INSTALLED PACKAGES',
        '-' * 80,
    ])

    packages = data['installed_packages']
    if isinstance(packages, dict) and ('error' not in packages):
        pkg_versions       = cast('dict[str, str]', packages.get('versions', {}))
        editable_locations = cast('dict[str, str]', packages.get('editable_locations', {}))

        name_to_name_vers: dict[str, str] = {
            name: f'{name}=={vers}'
            for i, (name, vers) in enumerate(pkg_versions.items())
            if (max_installed_packages is None) or (i < max_installed_packages)
        }
        col1_width = len(max(name_to_name_vers.values(), key=len))

        for name, name_vers in name_to_name_vers.items():
            if loc := editable_locations.get(name):
                name_vers = f'{name_vers.ljust(col1_width)}        {loc}'
            lines.append(f'  {name_vers}')

        if max_installed_packages and (len(packages) > max_installed_packages):
            lines.append(f'  ... and {len(packages) - max_installed_packages} more packages')

    else:
        lines.append(f"  Error: {packages.get('error', 'Unknown error')}")

    lines.extend([
        '',
        '=' * 80,
        'END OF DIAGNOSTIC REPORT',
        '=' * 80,
    ])
    return '\n'.join(lines)


# ============================================
# Argument parsing and core script entry point
# ============================================


class Args(argparse.Namespace):
    """
    Annotated :class:`argparse.Namespace` for script command-line arguments
    """
    max_installed_packages: int | None      # --max-installed-packages
    save:                   bool            # -s/--save
    json:                   bool            # -j, --json
    output:                 Path | None     # -o/--output


def build_parser() -> argparse.ArgumentParser:
    """
    Build argument parser for script

    :return: :class:`argparse.ArgumentParser`
    """
    parser = argparse.ArgumentParser(
        description='Collect Python environment diagnostic information',
        formatter_class=partial(argparse.HelpFormatter, max_help_position=80),
        add_help=False,
    )

    console_out_opts = parser.add_argument_group('Console output options')
    console_out_opts.add_argument(
        '--max-installed-packages',
        metavar='NUM',
        type=int,
        help='Max number of installed python packages to list under "INSTALLED PACKAGES"',
    )

    file_out_opts = parser.add_argument_group('File output options')
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

    other_group = parser.add_argument_group('Other options')
    other_group.add_argument(
        '-h',
        '--help',
        action='help',
        default=argparse.SUPPRESS,
        help='Show help message and exit',
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """
    Main entry point

    :param argv: argument list to parse, defaults to sys.argv[1:]
    :return: int script exit code
    """
    parser = build_parser()
    args   = parser.parse_args(argv, namespace=Args())

    print('Collecting diagnostic information...', file=sys.stderr)
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

        output_path.write_text(output)
        print('')
        print(f'Diagnostic report saved to: {output_path}',     file=sys.stderr)
        print(f'File size: {output_path.stat().st_size} bytes', file=sys.stderr)
    else:
        print(output)

    return 0


if __name__ == '__main__':
    sys.exit(main())
