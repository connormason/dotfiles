#!/usr/bin/env python3
"""
Pre-commit hook to enforce multi-line docstring format for Python files.

Converts single-line docstrings to multi-line format::

    # Before
    def func():
        \"\"\"Brief description.\"\"\"

    # After
    def func():
        \"\"\"
        Brief description.
        \"\"\"

Individual docstrings can be excluded from conversion with a ``# nofmt: docstring`` comment, either inline or on the
line immediately above::

    def func():
        \"\"\"Keep me single-line.\"\"\"  # nofmt: docstring

    def other():
        # nofmt: docstring
        \"\"\"Also kept single-line.\"\"\"

Uses the ``ast`` module to reliably identify docstrings (first expression statement in a module, class, or
function/method body), avoiding false positives on regular string literals or section-comment strings.
"""
from __future__ import annotations

import argparse
import ast
import functools
import io
import sys
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from typing import Union
from typing import cast

if TYPE_CHECKING:
    from collections.abc import Sequence


StyleColor = Union[int, tuple[int, int, int], str]


# ==================================================================================================
# Console output + styling helpers
# ==================================================================================================


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


def printf(
    text: str = '',
    *,
    fg: StyleColor | None = None,
    bold: bool | None = None,
    dim: bool | None = None,
    indent: int = 0,
) -> None:
    """
    Print styled text with optional indent and styling.

    :param text: text to print
    :param fg: foreground color
    :param bold: bold mode
    :param dim: dim mode
    :param indent: number of spaces to indent output by
    """
    print(
        style(
            textwrap.indent(text, ' ' * indent),
            fg=fg,
            bold=bold,
            dim=dim,
        ),
    )


# ==================================================================================================
# Constants/defaults/globals
# ==================================================================================================


SUPPRESSION_MARKER = 'nofmt: docstring'


ERROR      = style('ERROR',      fg='bright_red',    bold=True)
MODIFIED   = style('MODIFIED',   fg='bright_yellow')
UNMODIFIED = style('UNMODIFIED', fg='bright_blue')
SKIPPED    = style('SKIPPED',    fg='bright_blue',   dim=True)


# ==================================================================================================
# Detection
# ==================================================================================================


def find_docstring_exprs(tree: ast.Module) -> list[ast.Expr]:
    """
    Find all ``ast.Expr`` nodes that represent docstrings in the AST.

    A docstring is the first statement in a module, class, or function body when that statement is a bare string
    expression. This correctly excludes section-comment strings and regular string literals.

    :param tree: parsed AST module
    :return: list of ``ast.Expr`` nodes representing docstrings
    """
    results: list[ast.Expr] = []

    def _check_first_stmt(body: list[ast.stmt]) -> None:
        """
        Check if the first statement in a body is a docstring and, if so, append it to results.

        :param body: list of AST statements from a module, class, or function body
        """
        if not body:
            return

        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            results.append(first)

    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            _check_first_stmt(node.body)
    return results


def has_suppression_comment(lines: list[str], docstring_line_idx: int) -> bool:
    """
    Check whether a docstring has a ``# nofmt: docstring`` suppression comment.

    Checks two locations:

        1. **Inline**     — after the closing triple quotes on the docstring line itself
        2. **Line above** — a standalone comment line immediately above the docstring

    :param lines: source lines of the file (may include trailing newlines)
    :param docstring_line_idx: 0-based index of the docstring line
    :return: True if a suppression comment was found
    """
    docstring_line = lines[docstring_line_idx].rstrip('\r\n')
    for quote in ('"""', "'''"):
        last_quote_pos = docstring_line.rfind(quote)
        if last_quote_pos != -1:
            after_quotes = docstring_line[last_quote_pos + len(quote):]
            if SUPPRESSION_MARKER in after_quotes:
                return True
            break

    if docstring_line_idx > 0:
        above_line = lines[docstring_line_idx - 1].strip()
        if above_line.startswith('#') and SUPPRESSION_MARKER in above_line:
            return True
    return False


# ==================================================================================================
# Fixing
# ==================================================================================================


class FixResult:
    """
    Result of fixing a single Python file.

    :param modified: whether the file was modified (or would be in check mode)
    :param skipped_lines: 1-based line numbers of docstrings skipped due to suppression comments
    """
    __slots__ = ('modified', 'skipped_lines')

    def __init__(self, modified: bool, *, skipped_lines: list[int] | None = None) -> None:
        self.modified      = modified
        self.skipped_lines = skipped_lines if skipped_lines is not None else []


def expand_single_line_docstring(line: str) -> list[str]:
    """
    Expand a single-line docstring into multi-line format.

    Takes a source line like ``    \"\"\"Brief description.\"\"\"`` and returns three lines::

        '    \"\"\"'
        '    Brief description.'
        '    \"\"\"'

    Returns the original line (as a single-element list) if the line cannot be parsed as a single-line triple-quoted
    string, or if the docstring content is empty.

    :param line: source line containing a single-line docstring (without trailing newline)
    :return: list of replacement lines (without trailing newlines)
    """
    indent_len = len(line) - len(line.lstrip())
    indent_str = line[:indent_len]
    stripped  = line.strip()

    prefix = ''
    quote  = ''
    for candidate_prefix in ('r', 'R', 'u', 'U', ''):
        for candidate_quote in ('"""', "'''"):
            full = candidate_prefix + candidate_quote
            if stripped.startswith(full) and stripped.endswith(candidate_quote):
                prefix = candidate_prefix
                quote = candidate_quote
                break
        if quote:
            break

    if not quote:
        return [line]

    opener        = prefix + quote
    content_start = len(opener)
    content_end   = len(stripped) - len(quote)

    if content_end <= content_start:
        return [line]

    content = stripped[content_start:content_end].strip()
    if not content:
        return [line]

    return [
        f'{indent_str}{opener}',
        f'{indent_str}{content}',
        f'{indent_str}{quote}',
    ]


def fix_file(filepath: Path, *, check_only: bool = False) -> FixResult:
    """
    Fix single-line docstrings in a Python file by expanding them to multi-line format.

    Docstrings marked with a ``# nofmt: docstring`` comment (inline or on the line above) are skipped.

    The file is read and written without newline translation, so CRLF files keep their line endings.

    :param filepath: path to the Python file
    :param check_only: if ``True``, report violations without modifying the file
    :raises SyntaxError: if the file cannot be parsed as Python
    :return: :class:`FixResult` with modification status and any skipped line numbers
    """
    with filepath.open(encoding='utf-8', newline='') as fh:
        source = fh.read()
    tree = ast.parse(source, filename=str(filepath))

    docstring_exprs:   list[ast.Expr] = find_docstring_exprs(tree)
    single_line_exprs: list[ast.Expr] = [expr for expr in docstring_exprs if expr.lineno == expr.end_lineno]

    if not single_line_exprs:
        return FixResult(modified=False)

    # Unlike str.splitlines(), this splits only on \n, \r\n and \r, matching how ast numbers lines
    lines = io.StringIO(source, newline='').readlines()
    single_line_exprs.sort(key=lambda e: e.lineno, reverse=True)

    modified = False
    skipped_lines: list[int] = []
    for expr in single_line_exprs:
        idx = expr.lineno - 1

        if has_suppression_comment(lines, idx):
            skipped_lines.append(expr.lineno)
            continue

        original_line = lines[idx]

        if original_line.endswith('\r\n'):
            line_ending = '\r\n'
        elif original_line.endswith('\n'):
            line_ending = '\n'
        elif original_line.endswith('\r'):
            line_ending = '\r'
        else:
            line_ending = '\n'

        line_content = original_line.rstrip('\r\n')
        new_lines    = expand_single_line_docstring(line_content)
        if (len(new_lines) == 1) and (new_lines[0] == line_content):
            continue

        lines[idx:idx + 1] = [expanded + line_ending for expanded in new_lines]
        modified = True

    if modified and not check_only:
        with filepath.open('w', encoding='utf-8', newline='') as fh:
            fh.write(''.join(lines))

    skipped_lines.sort()
    return FixResult(modified=modified, skipped_lines=skipped_lines)


# ==================================================================================================
# Command-line arguments
# ==================================================================================================


class Args(argparse.Namespace):
    """
    :class:`argparse.Namespace` annotated with args supported by this script.
    """
    filenames: Sequence[str]        # positional arg(s) "FILENAMES"
    check:     bool                 # --check
    verbose:   bool                 # --verbose


def parse_args(argv: Sequence[str] | None = None) -> Args:
    """
    Build argument parser and parse command-line args.

    :param argv: command-line arguments (default: ``sys.argv[1:]``)
    :return: :class:`Args` (typed :class:`argparse.Namespace` subclass)
    """
    parser = argparse.ArgumentParser(
        description='Enforce multi-line docstring format in Python files',
        formatter_class=functools.partial(
            argparse.RawTextHelpFormatter,
            max_help_position=50,
        ),
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
            help='Python files to check/fix',
        )
    add_positional_args()

    def add_mode_opts() -> None:
        """
        Register the mode options group on the parser.
        """
        mode_opts = parser.add_argument_group('Mode options')
        mode_opts.add_argument(
            '--check',
            action='store_true',
            default=False,
            help='Report violations without modifying files (exit non-zero if any found)',
        )
    add_mode_opts()

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
            help='Output result for each processed file to console',
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

    return parser.parse_args(argv, namespace=Args())


# ==================================================================================================
# Core script entry point
# ==================================================================================================


def main(argv: Sequence[str] | None = None) -> int:
    """
    Enforce multi-line docstring format in Python files.

    :param argv: command-line arguments (default: ``sys.argv[1:]``)
    :return: 0 on success, 1 if any files were modified or violations found
    """
    args = parse_args(argv)
    if not args.filenames:
        printf('No filenames to check', fg='yellow')
        return 0

    retval: int = 0
    for filename in args.filenames:
        filepath = Path(filename)
        try:
            result = fix_file(filepath, check_only=args.check)
        except Exception as exc:
            printf(f'{ERROR}      {style(filename, fg="bright_white")}')
            printf(f'{exc!s}', fg='bright_red', indent=12)
            retval = 1
            continue

        if result.modified:
            print(f'{MODIFIED}    {style(filename, fg="bright_white")}')
            retval = 1
        elif args.verbose:
            printf(f'{UNMODIFIED}  {style(filename)}')

        if args.verbose and result.skipped_lines:
            for lineno in result.skipped_lines:
                printf(
                    f'{SKIPPED}     {style(f"{filename}:{lineno}", fg="bright_white")}'
                    f'  {style("(# nofmt: docstring)", dim=True)}',
                )

    return retval


if __name__ == '__main__':
    sys.exit(main())
