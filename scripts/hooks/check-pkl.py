#!/usr/bin/env python3
"""
Pre-commit hook to validate Pkl configuration files via ``pkl eval``.

If ``pkl`` is not found on PATH, prints a warning and exits successfully (exit code 0) so that the hook does not
block commits in environments where ``pkl`` is not installed. Otherwise, runs ``pkl eval --format yaml`` on all
provided files to validate syntax and schema correctness.
"""
from __future__ import annotations

import argparse
import functools
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from typing import Literal
from typing import Union
from typing import cast
from typing import get_args

if TYPE_CHECKING:
    from collections.abc import Sequence


# ==========================
# Constants/defaults/globals
# ==========================


PKL_INSTALLATION_DOCS_URL: str = 'https://pkl-lang.org/main/current/pkl-cli/index.html#installation'

VERBOSE: bool = False


# ===============
# Types/protocols
# ===============


PathLike   = Union[str, Path]
StyleColor = Union[int, tuple[int, int, int], str]


# ==================
# Formatting/logging
# ==================


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
    _ansi_colors: dict[str, int] = {
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
    _ansi_reset_all = '\033[0m'

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
        return str(_ansi_colors[_color] + offset)

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
        bits.append(_ansi_reset_all)
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


ColorOption = Literal['never', 'auto', 'always']

DEFAULT_COLOR_OPTION: ColorOption = 'always'


class Args(argparse.Namespace):
    """
    :class:`argparse.Namespace` annotated with args supported by this script.
    """
    filenames:   Sequence[str]              # positional arg(s)
    require_pkl: bool                       # --require-pkl
    executable:  str                        # --executable
    verbose:     bool                       # --verbose
    dump_yaml:   bool                       # --dump-yaml
    color:       ColorOption | None         # --color
    timeout:     float | None               # --timeout
    no_cache:    bool                       # --no-cache


def parse_args(argv: Sequence[str] | None = None) -> Args:
    """
    Build argument parser and parse command-line args.

    :param argv: command-line arguments (default: ``sys.argv[1:]``)
    :return: :class:`Args` (typed :class:`argparse.Namespace` subclass)
    """
    global VERBOSE

    parser = argparse.ArgumentParser(
        description='Validate Pkl files by evaluating them with ``pkl eval``',
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
            help='.pkl files to check',
        )
    add_positional_args()

    def add_pkl_executable_opts() -> None:
        """
        Register the Pkl executable options group on the parser.
        """
        pkl_executable_opts = parser.add_argument_group('Pkl executable options')
        pkl_executable_opts.add_argument(
            '--require-pkl',
            action='store_true',
            default=False,
            help=(
                'Exit with error (nonzero status) if ``pkl`` executable is not found.\n'
                'By default, simple warning outputted and script exits with status code 0'
            ),
        )
        pkl_executable_opts.add_argument(
            '--executable',
            metavar='PATH',
            type=str,
            default='pkl',
            help='Filepath to ``pkl`` executable to use. Default: "pkl" (resolve from PATH)',
        )
    add_pkl_executable_opts()

    def add_output_opts() -> None:
        """
        Register the output options group on the parser.
        """
        output_opts = parser.add_argument_group('Output options')
        output_opts.add_argument(
            '-v',
            '--verbose',
            action='store_true',
            default=False,
            help='Output validation result for each analyzed file to console',
        )
        output_opts.add_argument(
            '--dump-yaml',
            action='store_true',
            default=False,
            help='Dump YAML generated from module evaluation to stdout',
        )
        output_opts.add_argument(
            '--color',
            choices=get_args(ColorOption),
            default=DEFAULT_COLOR_OPTION,
            help=(
                f'Whether to format messages in ANSI color\n'
                f'{style("Default:", fg="bright_white", dim=True)} {style(DEFAULT_COLOR_OPTION, fg="green", dim=True)}'
            ),
        )
    add_output_opts()

    def add_execution_opts() -> None:
        """
        Register the execution options group on the parser.
        """
        execution_opts = parser.add_argument_group('Execution options')
        execution_opts.add_argument(
            '-t',
            '--timeout',
            metavar='SECONDS',
            type=float,
            default=None,
            help='Duration (in seconds) after which evaluation of source module will be timed out',
        )
    add_execution_opts()

    def add_package_opts() -> None:
        """
        Register the package options group on the parser.
        """
        package_opts = parser.add_argument_group('Package options')
        package_opts.add_argument(
            '--no-cache',
            action='store_true',
            default=False,
            help='Disable caching of packages',
        )
    add_package_opts()

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

    args = parser.parse_args(argv, namespace=Args())
    VERBOSE = args.verbose
    return args


# =================
# Core script logic
# =================


def main(argv: Sequence[str] | None = None) -> int:
    """
    Validate Pkl files by evaluating them with ``pkl eval``.

    :param argv: command-line arguments (default: ``sys.argv[1:]``)
    :return: 0 on success, non-zero on failure
    """
    args = parse_args(argv)
    if not args.filenames:
        printf('No filenames to check', fg='yellow')
        return 0

    if not shutil.which(args.executable):
        if args.require_pkl:
            err = f'{args.executable} not found'
            printf(f'{ERROR} {style(err, fg="bright_red")}')
            printf(f'Install pkl: {PKL_INSTALLATION_DOCS_URL}', indent=8)
            return 1
        printf(
            f'{WARNING} '
            f'{style("Executable not found", fg="bright_white")}: '
            f'{style(args.executable,        fg="bright_magenta")}'
        )
        printf('Skipping Pkl syntax validation',           indent=8)
        printf(style(PKL_INSTALLATION_DOCS_URL, dim=True), indent=8)
        return 0

    base_cmd: list[str] = [args.executable, 'eval', '--format', 'yaml']
    if args.color is not None:
        base_cmd.extend(['--color', args.color])
    if args.timeout is not None:
        base_cmd.extend(['--timeout', str(args.timeout)])
    if args.no_cache:
        base_cmd.append('--no-cache')

    retval: int = 0
    for filename in args.filenames:
        try:
            result = subprocess.run([*base_cmd, filename], check=True, capture_output=True, text=True)

        except subprocess.CalledProcessError as cmd_exc:
            printf(f'{ERROR}   {style(filename, fg="bright_white")}')
            if cmd_exc.stderr:
                stderr_lines = cmd_exc.stderr.splitlines()
                if unstyle(stderr_lines[0].strip()) == '–– Pkl Error ––':  # noqa: RUF001 (pkl emits literal en-dashes)
                    stderr_lines = stderr_lines[1:]
                printf('\n'.join(stderr_lines), indent=8)
            else:
                printf(str(cmd_exc),            indent=8)
            retval = 1

        except Exception as e:
            printf(f'{ERROR}   {style(filename, fg="bright_white")}')
            printf(f'{e!s}', indent=8)
            retval = 1

        else:
            if args.verbose:
                printf(f'{INFO}    {style(filename, fg="bright_white")}')
                printf(style('Valid Pkl', fg='green'), indent=8)
            if args.dump_yaml:
                printf(style('Compiled YAML:', fg='bright_white', bold=True, dim=True), indent=8)
                printf(style(result.stdout, dim=True), indent=10)

    return retval


if __name__ == '__main__':
    sys.exit(main())
