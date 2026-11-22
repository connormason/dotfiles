"""
Python interpreter checks
"""
from __future__ import annotations

import sys
from pathlib import Path

from cli.infra.config import MIN_PYTHON
from cli.infra.config import ExitCode
from cli.infra.types import ToolInfo
from cli.utils.formatting import folduser
from cli.utils.styling import printf
from cli.utils.styling import style

__all__ = [
    'check_python',
]


# ==================================================================================================
# Python helpers
# ==================================================================================================


def check_python(*, quiet: bool = False, indent: int = 0) -> ToolInfo:
    """
    Get current python executable path and version.

    Also ensures minimum python version requirement is met (if :attr:`MIN_PYTHON` is set at the top of this script).

    :param quiet: if True, suppress console output unless python version is not supported
    :param indent: number of spaces to indent logging output by
    :return: :class:`ToolInfo` with python executable path and installed version
    """
    v        = sys.version_info
    v_str    = f'{v.major}.{v.minor}.{v.micro}'
    exe      = Path(sys.executable)
    exe_str  = style(f'@ {folduser(exe)}', dim=True)
    info_str = f'{style("python", fg="white", bold=True)}  {style(v_str.ljust(8), fg="bright_cyan")} {exe_str}'

    if (MIN_PYTHON is not None) and (v < MIN_PYTHON):
        printf(f'🔴 {info_str}', indent=indent)
        printf(f'   Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ required', fg='bright_red', indent=indent)
        sys.exit(ExitCode.SETUP_ERROR)

    if not quiet:
        printf(f'⚪ {info_str}', indent=indent)
    return ToolInfo(executable=exe, version=v_str)
