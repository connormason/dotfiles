"""
Helpers for locating and running ``uv``
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from cli.infra.config import CI
from cli.infra.config import DOTFILES_DIR
from cli.infra.config import UV_COMMON_EXECUTABLE_PATHS
from cli.infra.config import UV_PUBLIC_SCRIPT
from cli.infra.config import VERSION_RE
from cli.infra.config import ExitCode
from cli.infra.types import PathLike
from cli.infra.types import ToolInfo
from cli.utils.formatting import folduser
from cli.utils.prompts import confirm
from cli.utils.scripts import run_installer
from cli.utils.shell import ShellCommandError
from cli.utils.shell import shell_command
from cli.utils.styling import printf
from cli.utils.styling import style

__all__ = [
    'check_uv',
    'ensure_uv',
    'find_uv_executable',
    'uv_command',
    'uv_lock',
    'uv_pip_list',
    'uv_run',
    'uv_sync',
    'uv_tree',
]


# ==================================================================================================
# `uv` helpers
# ==================================================================================================


def find_uv_executable() -> Path | None:
    """
    Find uv executable, checking both PATH and common install locations.

    :return: path to ``uv`` executable, or None if not found
    """
    uv_path: str | None = shutil.which('uv')
    if uv_path:
        return Path(uv_path)
    for path in UV_COMMON_EXECUTABLE_PATHS:
        if path.exists() and path.is_file():
            return path
    return None


def uv_command(*args: str, public: bool = True) -> list[str]:
    """
    Build the argv for a ``uv`` invocation.

    With ``public=True`` (the default, and the repo policy for every project-scoped call) the command runs through
    :data:`UV_PUBLIC_SCRIPT`, which neutralizes internal package index configuration so ``uv.lock`` only ever references
    public PyPI. The script ``exec``s a bare ``uv``, so when ``uv`` was found outside ``PATH`` (e.g. right after
    ``install-uv``, before the shell restarts) the command is wrapped in ``env PATH=...`` to keep it resolvable.

    :param args: arguments to pass to ``uv``
    :param public: route through the public-index wrapper script. Pass False for tool-level calls
                   (``uv --version``, ``uv tool ...``) that have no index involvement
    :return: command and arguments
    """
    uv_exe = find_uv_executable()
    if not public:
        return [str(uv_exe or 'uv'), *args]

    cmd: list[str] = [str(UV_PUBLIC_SCRIPT), *args]
    if (uv_exe is not None) and (shutil.which('uv') is None):
        cmd = ['env', f'PATH={uv_exe.parent}{os.pathsep}{os.environ.get("PATH", "")}', *cmd]
    return cmd


def check_uv(*, timeout: float | None = 5) -> ToolInfo | None:
    """
    Get ``uv`` executable path and version if installed.

    :param timeout: ``uv --version`` command timeout in seconds
    :return: :class:`ToolInfo` with executable path and installed version, None if ``uv`` not installed
    """
    if uv_executable_path := find_uv_executable():
        try:
            cp = shell_command(uv_command('--version', public=False), capture_output=True, timeout=timeout)
        except (FileNotFoundError, ShellCommandError):
            return None
        else:
            if m := VERSION_RE.search(f'{cp.stdout}\n{cp.stderr}'):
                return ToolInfo(executable=uv_executable_path, version=m.group('version'))
    return None


def ensure_uv(*, install_if_missing: bool | None = None, quiet: bool = False, indent: int = 0) -> ToolInfo:
    """
    Ensure that uv is installed and accessible, offering auto-installation if missing.

    In CI mode, auto-installs without prompting. In interactive mode, asks for user confirmation.

    :param install_if_missing: if True, uv will be installed automatically if it isn't currently installed.
                               If False, script will exit with error if uv is not installed.
                               If None (default), user will be prompted asking if they would like to install uv (unless
                               script is running in CI, in which case we proceed with installation without prompt)
    :param quiet: if True, suppress console output unless uv is not installed
    :param indent: number of spaces to indent logging output by
    :return: :class:`ToolInfo` with executable path and installed version
    """
    if uv_info := check_uv():
        if not quiet:
            uv_loc = style(f'@ {folduser(uv_info["executable"])}', dim=True)
            printf(
                f'⚪ {style("uv", fg="white", bold=True)}      '
                f'{style(uv_info["version"].ljust(8), fg="bright_cyan")} {uv_loc}',
                indent=indent,
            )
        return uv_info

    printf('🔴 uv is not installed', fg='bright_red')

    perform_install: bool
    if install_if_missing is not None:
        perform_install = install_if_missing
    elif CI:
        printf('💿 Auto-installing uv (CI mode)...', fg='bright_cyan', indent=3)
        perform_install = True
    else:
        perform_install = confirm('Would you like to install it now?', default=True, indent=3)

    if not perform_install:
        printf('')
        printf('To install uv:',                        fg='bright_white',   indent=3)
        printf('python3 scripts/install/install_uv.py', fg='bright_magenta', indent=5)
        printf('')
        sys.exit(ExitCode.SETUP_ERROR)

    if not run_installer('uv', indent=3):
        sys.exit(ExitCode.SETUP_ERROR)

    if uv_info := check_uv():
        printf(
            f'✅ uv {style(uv_info["version"], fg="bright_cyan")} installed successfully\n',
            fg='bright_green',
            indent=3,
        )
        return uv_info

    printf('❌ uv installation succeeded but tool not found in PATH',  fg='bright_red')
    printf('Try restarting your terminal and re-running this command', fg='bright_white', indent=3)
    sys.exit(ExitCode.SETUP_ERROR)


def uv_run(
    command: list[str],
    *,
    active: bool = False,
    python: str | float | None = None,
    indent: int | None = None,
    **kwargs: Any,
) -> subprocess.CompletedProcess[str]:
    """
    Run a command via ``uv run`` against the project's ``.venv``.

    :param command: command args to execute
    :param active: prefer the active virtual environment over the project's virtual environment
    :param python: the Python interpreter to use for the run environment
    :param indent: number of spaces to indent command output by, or None
    :param kwargs: additional keyword args to forward to :func:`shell_command`
    :return: :class:`subprocess.CompletedProcess`
    """
    cmd: list[str] = ['run']
    if active:
        cmd.append('--active')
    if python:
        cmd.extend(['--python', str(python)])
    return shell_command(uv_command(*cmd, '--', *command), indent=indent, **kwargs)


def uv_sync(
    *,
    extra: str | None = None,
    extras: Sequence[str] | None = None,
    all_extras: bool = False,
    no_extra: str | None = None,
    no_extras: Sequence[str] | None = None,
    no_dev: bool = False,
    only_dev: bool = False,
    group: str | None = None,
    groups: Sequence[str] | None = None,
    no_group: str | None = None,
    no_groups: Sequence[str] | None = None,
    no_default_groups: bool = False,
    only_group: str | None = None,
    all_groups: bool = False,
    inexact: bool = False,
    active: bool = False,
    locked: bool = False,
    frozen: bool = False,
    dry_run: bool = False,
    indent: int = 0,
    check: bool = True,
    env: dict[str, str] | None = None,
    **kwargs: Any,
) -> subprocess.CompletedProcess[str]:
    """
    Sync project dependencies via ``uv sync``.

    :param extra: include optional dependencies from the specified extra name
    :param extras: include optional dependencies from the specified extra name(s)
    :param all_extras: include all optional dependencies
    :param no_extra: exclude the specified optional dependencies, if `all_extras=True` is supplied
    :param no_extras: exclude the specified optional dependencies, if `all_extras=True` is supplied
    :param no_dev: disable development dependency group
    :param only_dev: only include the development dependency group
    :param group: include dependencies from the specified dependency group
    :param groups: include dependencies from the specified dependency group(s)
    :param no_group: disable the specified dependency group
    :param no_groups: disable the specified dependency groups
    :param no_default_groups: ignore the default dependency groups
    :param only_group: only include dependencies from the specified dependency group
    :param all_groups: include dependencies from all dependency groups
    :param inexact: do not remove extraneous packages present in the environment
    :param active: sync dependencies to the active virtual environment
    :param locked: assert that the `uv.lock` will remain unchanged
    :param frozen: sync without updating the `uv.lock`
    :param dry_run: perform a dry run, without writing the lockfile or modifying the project environment
    :param indent: number of spaces to indent command output by if `capture_output=False`
    :param check: if True, raise exception if command exits with nonzero code
    :param env: environment variables when command is run
    :param kwargs: additional keyword args to forward to :func:`shell_command`
    :raises ShellCommandError: if command exits with nonzero code and ``check=True``
    :return: :class:`subprocess.CompletedProcess`
    """
    cmd: list[str] = ['sync']
    if extra:
        cmd.extend(['--extra', extra])
    for e in (extras or []):
        cmd.extend(['--extra', e])
    if all_extras:
        cmd.append('--all-extras')
    if no_extra:
        cmd.extend(['--no-extra', no_extra])
    for ne in (no_extras or []):
        cmd.extend(['--no-extra', ne])
    if no_dev:
        cmd.append('--no-dev')
    if only_dev:
        cmd.append('--only-dev')
    if group:
        cmd.extend(['--group', group])
    for g in (groups or []):
        cmd.extend(['--group', g])
    if no_group:
        cmd.extend(['--no-group', no_group])
    for ng in (no_groups or []):
        cmd.extend(['--no-group', ng])
    if no_default_groups:
        cmd.append('--no-default-groups')
    if only_group:
        cmd.extend(['--only-group', only_group])
    if all_groups:
        cmd.append('--all-groups')
    if inexact:
        cmd.append('--inexact')
    if active:
        cmd.append('--active')
    if locked:
        cmd.append('--locked')
    if frozen:
        cmd.append('--frozen')
    if dry_run:
        cmd.append('--dry-run')

    return shell_command(uv_command(*cmd), check=check, indent=indent, env=env, **kwargs)


def uv_lock(
    *,
    check_only: bool = False,
    refresh: bool = False,
    upgrade: bool = False,
    upgrade_packages: Sequence[str] | None = None,
    indent: int = 0,
    **kwargs: Any,
) -> subprocess.CompletedProcess[str]:
    """
    Update the project lockfile via ``uv lock``.

    :param check_only: verify ``uv.lock`` is up to date without writing it (``--check``)
    :param refresh: refresh cached package metadata (``--refresh``)
    :param upgrade: allow upgrades of every package (``--upgrade``)
    :param upgrade_packages: allow upgrades of only these packages (``--upgrade-package`` for each)
    :param indent: number of spaces to indent command output by
    :param kwargs: additional keyword args to forward to :func:`shell_command` (e.g. ``check=False`` to receive a
                   nonzero exit status instead of an exception)
    :raises ShellCommandError: if command exits with nonzero code (unless ``check=False`` is forwarded)
    :return: :class:`subprocess.CompletedProcess`
    """
    cmd: list[str] = ['lock']
    if check_only:
        cmd.append('--check')
    if refresh:
        cmd.append('--refresh')
    if upgrade:
        cmd.append('--upgrade')
    for package in (upgrade_packages or []):
        cmd.extend(['--upgrade-package', package])
    return shell_command(uv_command(*cmd), indent=indent, cwd=DOTFILES_DIR, **kwargs)


def uv_pip_list(
    venv_dir: PathLike | None = None,
    *,
    system: bool = False,
    timeout: float | None = 5,
) -> list[dict[str, Any]]:
    """
    List installed packages in ``venv_dir`` via ``uv pip list --format json --python ...``.

    :param venv_dir: path to the venv to inspect, or None to list packages installed in currently-active python
                     environment (or system python if no active environment and no project environment found in current
                     working directory)
    :param system: if True, list packages in the system python environment (overrides `venv_dir` if provided)
    :param timeout: command timeout in seconds
    :return: list of package dicts (each has ``name`` and ``version``); empty on any failure
    """
    python_exe: Path | None = None
    if (venv_dir is not None) and (not system):
        env_dir = Path(venv_dir).expanduser()
        if not env_dir.exists():
            return []

        python_exe = env_dir / 'bin' / 'python'
        if not python_exe.exists():
            return []

    uv_exe = find_uv_executable()
    if uv_exe is None:
        return []

    cmd: list[str] = [str(uv_exe), 'pip', 'list', '--format', 'json']
    if system:
        cmd.append('--system')
    elif python_exe is not None:
        cmd.extend(['--python', str(python_exe)])

    try:
        result = shell_command(cmd, capture_output=True, timeout=timeout, check=False)
    except (OSError, ShellCommandError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []

    try:
        data = json.loads(result.stdout or '[]')
    except (TypeError, ValueError):
        return []
    else:
        return data if isinstance(data, list) else []


def uv_tree(
    *,
    all_groups: bool = True,
    depth: int = 1,
    cwd: Path | None = None,
    timeout: float | None = 5,
) -> str | None:
    """
    Run ``uv tree`` and return its stdout, or None on failure.

    :param all_groups: pass ``--all-groups`` to include every dependency group
    :param depth: passed as ``--depth N``
    :param cwd: working directory for the call (defaults to caller's cwd)
    :param timeout: command timeout in seconds
    :return: raw stdout text on success; None if uv is missing or the call fails
    """
    uv_exe = find_uv_executable()
    if uv_exe is None:
        return None

    cmd: list[str] = [str(uv_exe), 'tree', '--depth', str(depth)]
    if all_groups:
        cmd.append('--all-groups')

    try:
        result = shell_command(
            cmd,
            cwd=cwd,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, ShellCommandError, subprocess.TimeoutExpired):
        return None
    else:
        if result.returncode != 0:
            return None
        return result.stdout
