#!/usr/bin/env python3
"""
Pre-commit hook to validate JSON5 file syntax.
"""
# /// script
# requires-python = ">= 3.9"
# dependencies = [
#     "pyjson5",
# ]
# ///
from __future__ import annotations

import argparse
import functools
import re
import sys
import textwrap
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from typing import Union
from typing import cast

try:
    import pyjson5
except (ModuleNotFoundError, NameError, ImportError):
    print('`pyjson5` package not installed. Please install `pyjson5` before running hook')
    sys.exit(1)


# ==========================
# Constants/defaults/globals
# ==========================


VERBOSE: bool = False


# ===============
# Types/protocols
# ===============


PathLike   = Union[str, Path]
StyleColor = Union[int, tuple[int, int, int], str]


# ==================
# Formatting/logging
# ==================


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
    Replace the user's home directory with ``~`` in a path string.

    :param path: path
    :return: folded path string
    """
    return str(path).replace(str(Path.home()), '~')


ERROR   = style('ERROR',   fg='bright_red',    bold=True)
INFO    = style('INFO',    fg='bright_blue',   bold=True)
WARNING = style('WARNING', fg='bright_yellow', bold=True)


def printf(
    text: str = '',
    *,
    fg: StyleColor | None = None,
    bold: bool | None = None,
    dim: bool | None = None,
    indent: int = 0,
    verbose: bool = False,
) -> None:
    """
    Print styled text with optional indent and verbose gating.

    :param text: text to print
    :param fg: foreground color
    :param bold: bold mode
    :param dim: dim mode
    :param indent: number of spaces to indent output by
    :param verbose: only print when global ``VERBOSE`` is True. Output is dim and sent to stderr
    """
    if verbose and not VERBOSE:
        return
    if verbose:
        fg   = fg or 'bright_white'
        dim  = True if dim is None else dim
        file = sys.stderr
    else:
        file = None

    print(
        style(textwrap.indent(text, ' ' * indent), fg=fg, bold=bold, dim=dim),
        file=file,
    )


# ======================
# Command-line arguments
# ======================


class Args(argparse.Namespace):
    """
    :class:`argparse.Namespace` annotated with args supported by this script.
    """
    filenames: Sequence[str]
    verbose:   bool


def parse_args(argv: Sequence[str] | None = None) -> Args:
    """
    Build argument parser and parse command-line args.

    :param argv: command-line arguments (default: ``sys.argv[1:]``)
    :return: :class:`Args` (typed :class:`argparse.Namespace` subclass)
    """
    global VERBOSE

    parser = argparse.ArgumentParser(
        description='Validate that JSON5 files have valid syntax (parsable)',
        formatter_class=functools.partial(argparse.RawTextHelpFormatter, max_help_position=50),
        add_help=False,
    )

    def add_positional_args() -> None:
        """
        Register the positional arguments group on the parser.
        """
        positional_args = parser.add_argument_group('Positional arguments')
        positional_args.add_argument(
            'filenames',
            nargs='*',
            help='.json5 files to check',
        )
    add_positional_args()

    def add_output_opts() -> None:
        """
        Register the output options group on the parser.
        """
        output_opts = parser.add_argument_group('Output options')
        output_opts.add_argument(
            '-v',
            '--verbose',
            action='store_true',
            help='Output validation result for each analyzed file to console',
        )
    add_output_opts()

    def add_other_opts() -> None:
        """
        Register the miscellaneous options group on the parser.
        """
        other_opts = parser.add_argument_group('Other options')
        other_opts.add_argument(
            '-h',
            '--help',
            action='help',
            default=argparse.SUPPRESS,
            help='Show this help message and exit',
        )
    add_other_opts()

    args    = parser.parse_args(argv, namespace=Args())
    VERBOSE = args.verbose
    return args


# =================
# Core script logic
# =================


def main(argv: Sequence[str] | None = None) -> int:
    """
    Validate that JSON5 files have valid syntax (parsable).

    :param argv: command-line arguments (default: ``sys.argv[1:]``)
    :return: 0 on success, non-zero on failure
    """
    args = parse_args(argv)
    if not args.filenames:
        printf('No filenames to check', fg='yellow')
        return 0

    retval: int = 0
    for filename in args.filenames:
        path = Path(filename)
        try:
            raw = path.read_bytes()
        except Exception as open_exc:
            printf(f'{ERROR}   {style(filename,       fg="bright_white")}')
            printf(f'Unable load file: {open_exc!s}', fg='bright_red', indent=8)
            retval = 1
            continue

        try:
            text = raw.decode('utf-8')
        except UnicodeDecodeError as decode_exc:
            printf(f'{ERROR}   {style(filename,                fg="bright_white")}')
            printf(f'File is not valid UTF-8: {decode_exc!s}', fg='bright_red', indent=8)
            retval = 1
            continue

        try:
            pyjson5.loads(text)
        except pyjson5.Json5DecoderException as json5_exc:
            printf(f'{ERROR}   {style(filename,                            fg="bright_white")}')
            printf(f'{json5_exc.__class__.__name__}: {json5_exc.message}', fg='bright_red', indent=8)
            retval = 1
            continue
        except Exception as json5_exc:
            printf(f'{ERROR}   {style(filename,              fg="bright_white")}')
            printf(f'Unable to decode JSON5: {json5_exc!s}', fg='bright_red', indent=8)
            retval = 1
            continue

        else:
            if args.verbose:
                printf(f'{INFO}    {style(filename, fg="bright_white")}')
                printf(style('Valid JSON5',         fg='green'), indent=8)

    return retval


if __name__ == '__main__':
    sys.exit(main())
