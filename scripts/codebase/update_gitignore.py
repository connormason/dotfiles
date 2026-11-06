#!/usr/bin/env python3
"""
Refresh the generated block of ``.gitignore`` from gitignore.io while preserving custom patterns.

The template list is read from the toptal.com URL embedded in the file's header comment. Fresh content is fetched
(``urllib``, falling back to ``curl``) and any custom patterns found after the generated block's end marker are
re-appended. A missing marker or a fetch that does not return a complete block aborts without touching the file.

Usage::

    uv run --no-project scripts/codebase/update_gitignore.py [--gitignore-path PATH] [--dry-run] [--force]
"""
from __future__ import annotations

import argparse
import functools
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from typing import TextIO
from typing import Union
from typing import cast
from urllib.request import urlopen

if TYPE_CHECKING:
    from collections.abc import Sequence


PathLike   = Union[Path, str]
StyleColor = Union[int, tuple[int, int, int], str]


# ==================================================================================================
# Console output + styling helpers (copied from run.py; run.py wins on disagreement)
# ==================================================================================================


NO_COLOR: bool = bool(os.getenv('NO_COLOR'))        # https://no-color.org: any non-empty value disables color

ANSI_COLOR: dict[str, int] = {
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

    :param _color: color as a named string, 256-color int, or ``(r, g, b)`` tuple
    :param offset: offset added to the base code (0 for foreground, 10 for background)
    :return: ANSI SGR parameter fragment (e.g. ``"32"`` or ``"38;2;255;0;0"``)
    """
    if isinstance(_color, int):
        return f'{38 + offset};5;{_color:d}'
    if isinstance(_color, (tuple, list)):
        r, g, b = _color
        return f'{38 + offset};2;{r:d};{g:d};{b:d}'
    _color = cast('str', _color)
    return str(ANSI_COLOR[_color] + offset)


def style(
    text: Any = '',
    *,
    fg: StyleColor | None = None,
    bg: StyleColor | None = None,
    bold: bool | None = None,
    dim: bool | None = None,
    reset: bool = True,
) -> str:
    """
    Style text with ANSI escape codes. Returns the text unstyled when ``NO_COLOR`` is set.

    :param text: the string to style with ansi codes
    :param fg: foreground color
    :param bg: background color
    :param bold: enable or disable bold mode
    :param dim: enable or disable dim mode
    :param reset: add a reset-all code at the end of the string
    :raises TypeError: if invalid fg/bg color requested
    :return: styled text
    """
    if NO_COLOR:
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

    bits.append(text)
    if reset:
        bits.append(ANSI_RESET_ALL)
    return ''.join(bits)


def folduser(path: PathLike) -> str:
    """
    Does the opposite of :meth:`pathlib.Path.expanduser`, replacing the user's home directory with a "~"

    :param path: path
    :return: str folded path
    """
    home = str(Path.home())
    return str(path).replace(home, '~')


def pathstyle(path: PathLike, **opts: Any) -> str:
    """
    Style a file path in magenta with the home directory folded to ``~``

    :param path: the file path to style
    :return: the ANSI-styled path string
    """
    return style(folduser(path), fg='magenta', **opts)


def printf(
    text: str = '',
    *,
    fg: StyleColor | None = None,
    bold: bool | None = None,
    dim: bool | None = None,
    indent: int = 0,
    file: TextIO | None = None,
) -> None:
    """
    Print styled text with optional indentation (flushed so lines stay ordered with child-process output)

    :param text: the content to print
    :param fg: foreground color
    :param bold: enable or disable bold
    :param dim: enable or disable dim
    :param indent: number of leading spaces to prepend
    :param file: output stream (defaults to stdout)
    """
    print(
        style(
            textwrap.indent(text, ' ' * indent),
            fg=fg,
            bold=bold,
            dim=dim,
        ),
        file=file,
        flush=True,
    )


# ==================================================================================================
# Constants
# ==================================================================================================


GITIGNORE_API_URL: str = 'https://www.toptal.com/developers/gitignore/api/'
FETCH_TIMEOUT:     int = 30

TEMPLATES_RE  = re.compile(re.escape(GITIGNORE_API_URL) + r'([A-Za-z0-9+,._-]+)')
END_MARKER_RE = re.compile(re.escape(f'# End of {GITIGNORE_API_URL}'))


# ==================================================================================================
# Core logic
# ==================================================================================================


def extract_templates(gitignore_content: str) -> list[str]:
    """
    Read the template list from the gitignore.io URL in the current ``.gitignore`` header.

    :param gitignore_content: content of the current ``.gitignore``
    :raises ValueError: if the gitignore.io URL is absent
    :return: template names, in file order
    """
    if m := TEMPLATES_RE.search(gitignore_content):
        return m.group(1).split(',')
    raise ValueError('Could not find the gitignore.io URL in the current .gitignore')


def extract_custom_patterns(gitignore_content: str) -> list[str]:
    """
    Extract the lines added after the generated block's end marker.

    Leading and trailing blank lines are dropped; interior blank lines are kept.

    :param gitignore_content: content of the current ``.gitignore``
    :raises ValueError: if the end marker is absent (so custom patterns can never be dropped silently)
    :return: custom lines
    """
    lines   = gitignore_content.splitlines()
    end_idx = next((i for i, line in enumerate(lines) if END_MARKER_RE.match(line)), None)
    if end_idx is None:
        raise ValueError('Could not find the gitignore.io end marker; refusing to risk dropping custom patterns')

    custom   = lines[end_idx + 1:]
    nonblank = [i for i, line in enumerate(custom) if line.strip()]
    return custom[nonblank[0]:nonblank[-1] + 1] if nonblank else []


def _require_end_marker(content: str) -> str:
    """
    Reject fetched content that lacks the end marker (an error page or truncated response).

    :param content: fetched gitignore.io content
    :raises RuntimeError: if the end marker is absent
    :return: ``content`` unchanged
    """
    if not any(END_MARKER_RE.match(line) for line in content.splitlines()):
        raise RuntimeError('Fetched content has no gitignore.io end marker; refusing to use it')
    return content


def fetch_gitignore_content(templates: list[str]) -> str:
    """
    Fetch fresh ``.gitignore`` content for ``templates``, trying ``urllib`` then ``curl``.

    :param templates: template names
    :raises RuntimeError: if every method fails or the content is incomplete
    :return: gitignore.io content
    """
    url = f'{GITIGNORE_API_URL}{",".join(templates)}'
    try:
        with urlopen(url, timeout=FETCH_TIMEOUT) as response:       # noqa: S310
            content = response.read().decode('utf-8')
    except OSError as e:
        printf(f'🟡 urllib failed ({e}); trying curl...', fg='bright_yellow', indent=3)
    else:
        return _require_end_marker(content)

    try:
        result = subprocess.run(
            ['curl', '--silent', '--show-error', '--location', '--fail', '--max-time', str(FETCH_TIMEOUT), url],
            check=False,
            capture_output=True,
            text=True,
            timeout=FETCH_TIMEOUT + 5,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        raise RuntimeError(f'Could not fetch {url} (urllib and curl both failed): {e}') from e
    if result.returncode != 0:
        raise RuntimeError(f'Could not fetch {url} (curl exit {result.returncode}): {result.stderr.strip()}')
    return _require_end_marker(result.stdout)


def generate_updated_gitignore(fresh_content: str, custom_patterns: list[str]) -> str:
    """
    Combine fresh gitignore.io content with preserved custom patterns.

    :param fresh_content: fresh content from gitignore.io
    :param custom_patterns: custom lines to append after a blank line
    :return: new ``.gitignore`` content
    """
    result = fresh_content.rstrip('\n') + '\n'
    if custom_patterns:
        result += '\n' + ''.join(f'{line}\n' for line in custom_patterns)
    return result


# ==================================================================================================
# Command-line interface
# ==================================================================================================


class Args(argparse.Namespace):
    """
    :class:`argparse.Namespace` annotated with the args supported by this script
    """
    gitignore_path: Path        # --gitignore-path
    dry_run:        bool        # --dry-run
    force:          bool        # --force


def build_parser() -> argparse.ArgumentParser:
    """
    Build the argument parser.

    :return: the configured :class:`argparse.ArgumentParser`
    """
    parser = argparse.ArgumentParser(
        description='Refresh the generated block of .gitignore from gitignore.io, preserving custom patterns',
        formatter_class=functools.partial(
            argparse.RawTextHelpFormatter,
            max_help_position=50,
        ),
        add_help=False,
    )

    def add_file_opts() -> None:
        file_opts = parser.add_argument_group('File options')
        file_opts.add_argument(
            '--gitignore-path',
            type=Path,
            default=Path('.gitignore'),
            metavar='PATH',
            help='Path to the .gitignore file (default: .gitignore)',
        )
    add_file_opts()

    def add_execution_opts() -> None:
        execution_opts = parser.add_argument_group('Execution options')
        execution_opts.add_argument(
            '--dry-run',
            action='store_true',
            help='Show the result without writing the file',
        )
        execution_opts.add_argument(
            '--force',
            action='store_true',
            help='Write the file even if nothing changed',
        )
    add_execution_opts()

    def add_other_opts() -> None:
        other_opts = parser.add_argument_group('Other options')
        other_opts.add_argument(
            '-h',
            '--help',
            action='help',
            default=argparse.SUPPRESS,
            help='Show this help message and exit',
        )
    add_other_opts()

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """
    Script entry point.

    :param argv: command-line arguments (default: ``sys.argv[1:]``)
    :return: 0 on success or when already up to date, 1 on any error
    """
    args = build_parser().parse_args(argv, namespace=Args())

    if not args.gitignore_path.is_file():
        printf(f'❌ {pathstyle(args.gitignore_path)} not found', fg='bright_red', file=sys.stderr)
        return 1

    try:
        current   = args.gitignore_path.read_text(encoding='utf-8')
        templates = extract_templates(current)
        custom    = extract_custom_patterns(current)

        printf('🔄 Refreshing .gitignore from gitignore.io', fg='bright_cyan')
        printf(f'Templates: {", ".join(templates)}',       indent=3)
        printf(f'Preserving {len(custom)} custom line(s)', indent=3)

        updated = generate_updated_gitignore(fetch_gitignore_content(templates), custom)
        if (updated == current) and (not args.force):
            printf(f'✅ {pathstyle(args.gitignore_path)} is already up to date', fg='bright_green')
            return 0

        if args.dry_run:
            printf(f'🔍 Dry run: would update {pathstyle(args.gitignore_path)}', fg='bright_cyan')
            printf(updated, dim=True)
            return 0

        args.gitignore_path.write_text(updated, encoding='utf-8')

    except (ValueError, RuntimeError, OSError) as e:
        printf(f'❌ {e}', fg='bright_red', file=sys.stderr)
        return 1

    printf(f'✅ Updated {pathstyle(args.gitignore_path)}', fg='bright_green')
    return 0


if __name__ == '__main__':
    sys.exit(main())
