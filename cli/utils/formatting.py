"""
Plain-text formatting helpers (paths, durations, package names, whitespace)
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:

    from cli.infra.types import PathLike

__all__ = [
    'canonical_pkg_name',
    'cleanup_whitespace',
    'folduser',
    'format_elapsed',
]


# ==================================================================================================
# Formatting
# ==================================================================================================


def folduser(path: PathLike) -> str:
    """
    Does the opposite of :meth:`pathlib.Path.expanduser`, replacing the user's home directory with a "~"

    :param path: path
    :return: str folded path
    """
    home = str(Path.home())
    return str(path).replace(home, '~')


def format_elapsed(seconds: float) -> str:
    """
    Format elapsed time for display

    Shows seconds with one decimal for short durations, mm:ss for longer ones

    :param seconds: elapsed wall-clock time in seconds
    :return: human-readable duration string (e.g. "3.2s", "1:05")
    """
    if seconds < 60:
        return f'{seconds:.1f}s'
    minutes = int(seconds) // 60
    secs    = int(seconds) % 60
    return f'{minutes}:{secs:02d}'


def canonical_pkg_name(name: str) -> str:
    """
    Normalize a Python package name per PEP 503

    :param name: package name as it appears in pyproject.toml or a dist-info directory
    :return: canonical lowercase form with single hyphens between words
    """
    return re.sub(r'[-_.]+', '-', name).lower()


def cleanup_whitespace(text: str) -> str:
    r"""
    Strip trailing whitespace from each line and ensure the content ends with exactly one newline

    Mirrors the behavior of the ``trailing-whitespace`` and ``end-of-file-fixer`` pre-commit hooks, allowing
    programmatically generated text to be written to files without requiring a second pass from those hooks

    Examples
    --------
        >>> cleanup_whitespace('hello   \\nworld  \\n')
        'hello\\nworld\\n'
        >>> cleanup_whitespace('no trailing newline')
        'no trailing newline\\n'
        >>> cleanup_whitespace('extra\\n\\n\\n')
        'extra\\n'

    :param text: text content to clean up
    :return: cleaned text content
    """
    lines   = text.splitlines()
    cleaned = '\n'.join(line.rstrip() for line in lines)
    cleaned = cleaned.rstrip('\n')
    if cleaned:
        cleaned += '\n'
    return cleaned
