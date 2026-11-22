"""
Helpers for validating, importing, and running the repository's bundled scripts
"""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Literal
from typing import get_args
from typing import overload

from cli.infra import config
from cli.infra.config import INSTALLER_SCRIPTS
from cli.infra.config import ExitCode
from cli.infra.config import InstallableTool
from cli.utils.formatting import folduser
from cli.utils.shell import ShellCommandError
from cli.utils.shell import shell_command
from cli.utils.styling import pathstyle
from cli.utils.styling import printf
from cli.utils.styling import style

if TYPE_CHECKING:
    from types import ModuleType

    from cli.infra.types import ModT
    from cli.infra.types import PathLike

__all__ = [
    'check_script_validity',
    'import_script_module',
    'run_installer',
]


# ==================================================================================================
# External script utilities
# ==================================================================================================


def check_script_validity(script_path: PathLike, name: str | None = None, *, indent: int = 0) -> None:
    """
    Checks that the provided filepath points to a valid and executable script

    :param script_path: expected script filepath
    :param name: optional script "name", used as prefix for outputted error messages to indicate what the script is.
                 If not provided, defaults to filename of script
    :param indent: number of spaces to indent logging output by
    """
    path = Path(script_path).expanduser()
    name = name.strip().capitalize() if name else path.name

    valid: bool = False
    if not path.exists():
        printf(f'🔴 {name} not found',             fg='bright_red', indent=indent)
    elif not path.is_file():
        printf(f'🔴 {name} is not a regular file', fg='bright_red', indent=indent)
    elif not os.access(path, os.X_OK):
        printf(f'🔴 {name} is not executable',     fg='bright_red', indent=indent)
    else:
        valid = True

    if not valid:
        printf('')
        printf(f'Expected script path: {pathstyle(path)}', fg='white', indent=indent + 3)
        printf('')
        sys.exit(ExitCode.SETUP_ERROR)


@overload
def import_script_module(
    script_path: PathLike,
    *,
    protocol: type[ModT],
    exit_if_missing: Literal[True] = ...,
) -> ModT: ...

@overload
def import_script_module(
    script_path: PathLike,
    *,
    protocol: type[ModT],
    exit_if_missing: Literal[False],
) -> ModT | None: ...

@overload
def import_script_module(
    script_path: PathLike,
    *,
    protocol: None = ...,
    exit_if_missing: Literal[True] = ...,
) -> ModuleType: ...

@overload
def import_script_module(
    script_path: PathLike,
    *,
    protocol: None = ...,
    exit_if_missing: Literal[False],
) -> ModuleType | None: ...

def import_script_module(
    script_path: PathLike,
    *,
    protocol: type[ModT] | None = None,
    exit_if_missing: bool = True,
) -> ModT | ModuleType | None:
    """
    Dynamically import a script as a module given a filepath

    :param script_path: filepath to the ".py" script source file (absolute or relative to current working dir)
    :param protocol: optional :class:`typing.Protocol` to use as type annotation hint for the return type, enabling
                     full IDE auto-completion and mypy coverage on the returned module type

                     Example protocol::

                        class MathModule(Protocol):
                            def add(self, a: int, b: int) -> int: ...
                            def mul(self, a: int, b: int) -> int: ...


                        mod = load_module_from_file('math_utils.py', MathModule)
                        mod.add(1, 2)           # fully type-checked

    :param exit_if_missing: if True, exit if script is missing or there is an error loading it. If False, return None
    :raises TypeError: if ``path`` is not a str or Path, or ``protocol`` is not a class
    :return: loaded script module
    """
    import importlib.util

    if not isinstance(script_path, (str, Path)):
        raise TypeError(f'`path` must be a str or Path, got {type(script_path).__name__!r}')
    if (protocol is not None) and (not isinstance(protocol, type)):
        raise TypeError(f'`protocol` must be a class, got {type(protocol).__name__!r}')

    path = Path(script_path).expanduser().resolve()
    try:
        spec = importlib.util.spec_from_file_location(path.stem, path)
        if (spec is None) or (spec.loader is None):
            if exit_if_missing:
                printf(f'🔴 Script module not found: {folduser(path)}\n', fg='bright_red')
                sys.exit(ExitCode.SETUP_ERROR)
            return None

        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)

    except Exception as e:
        if exit_if_missing:
            printf(f'🔴 Error attempting to load script: {pathstyle(path)}\n', fg='bright_red')
            if not config.RUN_DEBUG:
                printf(str(e), fg='bright_red', indent=3)
            printf(traceback.format_exc(), indent=3, debug=True, fg='bright_red')
            sys.exit(ExitCode.SETUP_ERROR)
        return None

    else:
        return module


def run_installer(tool_name: InstallableTool, *, indent: int = 0) -> bool:
    """
    Run an installer script from ``scripts/install/`` and return True on success.

    Uses ``--ensure`` mode which suppresses the installer's banner and installs only if the tool is missing.
    Output is streamed in real-time with indentation via :func:`shell_command`.

    :param tool_name: name of tool to run installer script for ("uv")
    :param indent: number of spaces to indent output by
    :raises ValueError: if `tool_name` is not a tool we have an installer script for
    :return: True if installation succeeded, False otherwise
    """
    try:
        script_path = INSTALLER_SCRIPTS[tool_name]
    except KeyError as e:
        raise ValueError(
            f'No installer script available for tool {tool_name!r}. '
            f'Available tool installers: {", ".join(get_args(InstallableTool))}'
        ) from e

    check_script_validity(script_path, f'{tool_name} installer script', indent=indent)

    printf(f'💿 Installing {style(tool_name, fg="white", bold=True)}...', fg='bright_cyan', indent=indent)
    try:
        shell_command([sys.executable, str(script_path), '--ensure'], indent=indent + 2)
    except ShellCommandError as e:
        printf(
            f'❌ {style(tool_name, fg="white", bold=True)} installation failed (exit code {e.returncode})',
            fg='bright_red',
            indent=indent,
        )
        if e.stderr:
            printf(str(e.stderr).strip(), indent=indent + 3, debug=True)
        return False
    return True
