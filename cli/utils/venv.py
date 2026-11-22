"""
Virtual environment validation, creation, and entry helpers
"""
from __future__ import annotations

import dataclasses
import enum
import os
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from cli.infra.config import DOTFILES_DIR
from cli.infra.config import VENV_DIR
from cli.infra.config import VENVSHELL_SCRIPT_PATH
from cli.infra.config import ExitCode
from cli.utils.scripts import check_script_validity
from cli.utils.shell import shell_command
from cli.utils.styling import printf
from cli.utils.uv import find_uv_executable
from cli.utils.uv import uv_command
from cli.utils.uv import uv_sync

__all__ = [
    'VenvHealth',
    'VenvStatus',
    'count_venv_packages',
    'ensure_venv',
    'enter_venv',
    'get_external_active_venv',
    'is_venv_stale',
    'parse_pyvenv_version',
    'validate_venv',
]


# ==================================================================================================
# Virtual environment helpers
# ==================================================================================================


class VenvStatus(str, enum.Enum):
    """
    Possible states of project virtual environment.
    """
    HEALTHY        = 'healthy'
    MISSING        = 'missing'
    BROKEN_SYMLINK = 'broken_symlink'
    NOT_ACTIVATED  = 'not_activated'
    STALE_DEPS     = 'stale_deps'


@dataclasses.dataclass(frozen=True)
class VenvHealth:
    """
    Result of validating the project ``.venv`` directory.

    :param status: overall health status
    :param python_version: Python version from pyvenv.cfg (e.g. ``'3.13.2'``)
    :param package_count: number of installed packages in site-packages
    :param stale: True if uv.lock is newer than .venv
    :param message: human-readable status description
    """
    status:         VenvStatus
    python_version: str | None = None
    package_count:  int | None = None
    stale:          bool       = False
    message:        str        = ''


def parse_pyvenv_version(pyvenv_cfg: Path) -> str | None:
    """
    Extract ``version_info`` from a pyvenv.cfg file.

    :param pyvenv_cfg: path to the pyvenv.cfg file
    :return: version string (e.g. "3.13.2"), or None if not parseable
    """
    if not pyvenv_cfg.is_file():
        return None

    try:
        for line in pyvenv_cfg.read_text(encoding='utf-8').splitlines():
            if line.startswith('version_info'):
                return line.split('=', 1)[1].strip()
    except OSError:
        pass
    return None


def count_venv_packages(venv_dir: Path) -> int | None:
    """
    Count installed packages in the venv's site-packages directory.

    :param venv_dir: path to the .venv directory
    :return: number of ``.dist-info`` directories, or None if site-packages not found
    """
    if site_packages_dirs := list((venv_dir / 'lib').glob('python*/site-packages')):
        return len(list(site_packages_dirs[0].glob('*.dist-info')))
    return None


def get_external_active_venv() -> Path | None:
    """
    Return the path of an externally-activated virtual environment, or None.

    "External" means ``$VIRTUAL_ENV`` is set, points to an existing directory, and resolves to something other than
    the project's :data:`VENV_DIR`. Used by the status command so that users who manage their own venv (rather than
    the project's uv-managed ``.venv``) can still inspect its health.

    :return: resolved path of the active venv, or None if no external venv is active
    """
    if not (active := os.environ.get('VIRTUAL_ENV')):
        return None

    try:
        active_path = Path(active).resolve()
    except OSError:
        return None

    if not active_path.is_dir():
        return None

    try:
        if active_path == VENV_DIR.resolve(strict=False):
            return None
    except OSError:
        pass
    return active_path


# TODO: merge functionality into :func:`uv_sync`?
def is_venv_stale(
    venv_dir: Path,
    *,
    all_extras: bool = False,
    all_groups: bool = False,
    inexact: bool = True,
    timeout: float | None = 5,
) -> bool:
    """
    Check whether ``venv_dir`` is out of sync with ``uv.lock`` via ``uv sync --check``.

    For the project's own ``.venv`` this targets it implicitly; for any other venv (e.g. one the user
    manages themselves) the check is run with ``--active`` and ``VIRTUAL_ENV`` pointed at ``venv_dir`` so uv inspects
    that venv instead.

    :param venv_dir: path to the venv to inspect
    :param all_extras: include all optional (extra) dependencies when checking for stale env
    :param all_groups: include all dependency groups when checking for stale env
    :param inexact: pass ``--inexact`` so extraneous packages are tolerated; mirrors how ``make dev`` installs
                    (which always syncs with ``--inexact``) to avoid falsely reporting a correct venv as stale
    :param timeout: ``uv sync --check`` command timeout
    :return: True if ``uv`` reports the venv would be modified by a sync; False if in-sync or check cannot be run
    """
    if not venv_dir.exists():
        return False
    if find_uv_executable() is None:
        return False

    cmd: list[str] = ['sync', '--check']
    if all_extras:
        cmd.append('--all-extras')
    if all_groups:
        cmd.append('--all-groups')
    if inexact:
        cmd.append('--inexact')

    is_external: bool
    try:
        is_external = venv_dir.resolve() != VENV_DIR.resolve(strict=False)
    except OSError:
        is_external = False

    env: dict[str, str] | None = None
    if is_external:
        cmd.append('--active')
        env = {'VIRTUAL_ENV': str(venv_dir)}

    try:
        result = shell_command(
            uv_command(*cmd),
            cwd=DOTFILES_DIR,
            capture_output=True,
            timeout=timeout,
            check=False,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    else:
        return result.returncode != 0


def validate_venv(venv_dir: Path, *, check_stale: bool = True) -> VenvHealth:
    """
    Validate that ``.venv`` is usable, has the correct Python version, and is in sync with ``uv.lock``.

    :param venv_dir: path to the .venv directory
    :param check_stale: run the (relatively slow) ``uv sync --check`` staleness probe; pass False in quick mode to
                        skip it, in which case ``stale`` is left False and the venv is never reported as ``STALE_DEPS``
    :return: :class:`VenvHealth` describing the current state
    """
    if not venv_dir.exists():
        return VenvHealth(status=VenvStatus.MISSING, message='no .venv directory')

    python_exe = venv_dir / 'bin' / 'python'
    if not python_exe.exists():
        return VenvHealth(status=VenvStatus.BROKEN_SYMLINK, message='.venv/bin/python missing or broken symlink')

    pyvenv_cfg   = venv_dir / 'pyvenv.cfg'
    venv_version = parse_pyvenv_version(pyvenv_cfg)

    # Detect whether the venv is currently activated by comparing Python major.minor versions.
    # A mismatch means the script is running from a different interpreter (e.g. system Python)
    # — the venv itself is fine, just not activated in the current shell.
    activated = True
    if venv_version:
        current_mm = f'{sys.version_info.major}.{sys.version_info.minor}'
        venv_mm    = '.'.join(venv_version.split('.')[:2])
        if venv_mm != current_mm:
            activated = False

    stale     = is_venv_stale(venv_dir) if check_stale else False
    pkg_count = count_venv_packages(venv_dir)

    if stale:
        return VenvHealth(
            status=VenvStatus.STALE_DEPS,
            python_version=venv_version,
            package_count=pkg_count,
            stale=True,
            message='dependencies do not match uv.lock (run `make install`)',
        )

    if not activated:
        return VenvHealth(
            status=VenvStatus.NOT_ACTIVATED,
            python_version=venv_version,
            package_count=pkg_count,
            stale=False,
            message='not activated (run `make shell`)',
        )

    return VenvHealth(
        status=VenvStatus.HEALTHY,
        python_version=venv_version,
        package_count=pkg_count,
        stale=False,
        message='synced',
    )


def ensure_venv(
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
    indent: int = 0,
    env: dict[str, str] | None = None,
    **kwargs: Any,
) -> Path:
    """
    Ensure that ``.venv`` exists, is healthy, and is synced with project dependencies.

    Validates existing venvs for broken symlinks and Python version mismatches, auto-recreating if needed.

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
    :param indent: number of spaces to indent command output by if `capture_output=False`
    :param env: environment variables to forward to :func:`shell_command` calls
    :param kwargs: additional keyword args to forward to :func:`shell_command` calls
    :raises ShellCommandError: if command exits with nonzero code and ``check=True``
    :return: path to the ``.venv`` directory
    """
    if VENV_DIR.exists():
        health = validate_venv(VENV_DIR, check_stale=False)
        if health.status == VenvStatus.BROKEN_SYMLINK:
            printf('🔴 .venv has broken symlinks, recreating...', fg='bright_yellow', indent=indent)
            shutil.rmtree(VENV_DIR)

    if not VENV_DIR.exists():
        printf('💾 Creating virtual environment...', fg='bright_cyan', indent=indent)
        shell_command(uv_command('venv'), indent=indent)
        printf('')

    printf('📦 Syncing dependencies...', fg='bright_cyan', indent=indent)
    uv_sync(
        extra=extra,
        extras=extras,
        all_extras=all_extras,
        no_extra=no_extra,
        no_extras=no_extras,
        no_dev=no_dev,
        only_dev=only_dev,
        group=group,
        groups=groups,
        no_group=no_group,
        no_groups=no_groups,
        no_default_groups=no_default_groups,
        only_group=only_group,
        all_groups=all_groups,
        inexact=inexact,
        active=active,
        locked=locked,
        frozen=frozen,
        env=env,
        indent=indent + 3,
        **kwargs,
    )
    printf('')
    return VENV_DIR


def enter_venv(*, verbose: bool = False, indent: int = 0) -> None:
    """
    Enter the project ``.venv`` in an interactive subshell via ``venvshell.py``.

    :param verbose: output verbose logging from ``venvshell.py`` script
    :param indent: number of spaces to indent logging output by
    """
    if not VENV_DIR.exists():
        printf('🔴 No virtual environment found. Run `make install` first.\n', fg='bright_red', indent=indent)
        sys.exit(ExitCode.SETUP_ERROR)

    check_script_validity(VENVSHELL_SCRIPT_PATH, 'venvshell script', indent=indent)

    cmd: list[str] = [sys.executable, str(VENVSHELL_SCRIPT_PATH), '--path', str(VENV_DIR)]
    if verbose:
        cmd.append('--verbose')

    try:
        shell_command(cmd, check=False)
    except KeyboardInterrupt:
        printf('⏪ Exiting virtual environment...', fg='bright_white', indent=indent)
