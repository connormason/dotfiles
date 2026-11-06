#!/usr/bin/env python3
'''
Pre-commit hook to format module-level section headers.

Converts module-level triple-quoted section headers to boxed comment headers and keeps the borders of boxed comment
headers at a consistent width.

Old format:

    \"""
    Section name
    \"""

New format:

    # ==============================================================================
    # Section name
    # ==============================================================================

Module docstrings (the first triple-quoted block at the top of a file, before any code) are preserved unchanged.
Indented triple-quoted strings (function/class docstrings, multi-line string literals) are not touched -- only lines
consisting of exactly ``\"""`` (no leading whitespace, nothing else) are considered.

Border normalization (enabled by default, disable with ``--no-normalize-borders``): an existing boxed header -- a
standalone border comment, one or more standalone comment lines, and a closing border comment, all at the same
indentation -- has both borders rewritten so the full line (indentation included) is ``--border-width`` characters wide.
A border is a ``#`` comment consisting solely of three or more ``--border-char`` characters. Only borders made of the
configured character are recognized, so other comment rules (e.g. ``# -----``) are never touched, and a lone border
that does not enclose a header (such as a ``=====`` underline beneath a title) is left alone. Comments inside string
literals are ignored.

Usage:

    # Recurse into the current directory
    uv run scripts/hooks/format_module_section_headers.py

    # Use 120-wide borders drawn with dashes
    uv run scripts/hooks/format_module_section_headers.py --border-char - --border-width 120 file.py

    # Only convert triple-quoted headers; leave existing borders as-is
    uv run scripts/hooks/format_module_section_headers.py --no-normalize-borders file.py

    # Process specific files (used by pre-commit)
    uv run scripts/hooks/format_module_section_headers.py path/to/file1.py path/to/file2.py

    # Pre-commit fixer mode (exit non-zero when any file was modified)
    uv run scripts/hooks/format_module_section_headers.py --exit-non-zero-on-fix file.py

'''
# /// script
# requires-python = ">= 3.9"
# dependencies = []
# ///
from __future__ import annotations

import argparse
import ast
import functools
import io
import sys
import tokenize
from pathlib import Path

# ==================================================================================================
# Constants
# ==================================================================================================


DEFAULT_BORDER_CHAR:  str = '='
DEFAULT_BORDER_WIDTH: int = 100

# Shortest run of border characters (after ``# ``) recognized as a border, so short rules like ``# --`` are ignored.
MIN_BORDER_RUN: int = 3

SKIP_DIRS: frozenset[str] = frozenset({
    '.git',
    '.venv',
    'venv',
    '.tox',
    'site-packages',
    '__pycache__',
})


# ==================================================================================================
# Formatting
# ==================================================================================================


def is_module_docstring_position(lines_before: list[str]) -> bool:
    """
    Check whether the lines preceding an opening triple-quote could legally precede a module docstring.

    A module docstring must be the first statement in a file, so only blanks and ``#`` comments (including shebangs and
    PEP 723 metadata) may appear before it.

    :param lines_before: lines of the file appearing before the opening triple-quote
    :return: True if the position is valid for a module docstring
    """
    for line in lines_before:
        stripped = line.strip()
        if stripped == '':
            continue
        if stripped.startswith('#'):
            continue
        return False
    return True


def make_border(
    indent: int = 0,
    char:   str = DEFAULT_BORDER_CHAR,
    width:  int = DEFAULT_BORDER_WIDTH,
) -> str:
    """
    Build a border comment line.

    :param indent: number of leading spaces
    :param char: character repeated to draw the border
    :param width: total line width in characters, indentation and the leading ``# `` included
    :return: the border line (at least one border character, even when ``width`` is too small to fit one)
    """
    return ' ' * indent + '# ' + char * max(width - indent - 2, 1)


def is_border(comment: str, char: str = DEFAULT_BORDER_CHAR) -> bool:
    """
    Check whether a comment is a border made of ``char``.

    :param comment: comment text, starting with ``#``
    :param char: border character
    :return: True if the comment is ``#`` followed by an optional space and at least :data:`MIN_BORDER_RUN` ``char``
             characters and nothing else
    """
    body = comment[1:]
    body = body.removeprefix(' ')
    return (len(body) >= MIN_BORDER_RUN) and (body == char * len(body))


def normalize_borders(text: str, char: str = DEFAULT_BORDER_CHAR, width: int = DEFAULT_BORDER_WIDTH) -> tuple[str, int]:
    """
    Resize the borders of every boxed comment header in ``text`` to ``width`` characters.

    A boxed header is a standalone border comment, one or more standalone non-border comment lines, and a closing border
    comment, all on consecutive lines at the same indentation. Comment detection uses :mod:`tokenize`, so border-like
    text inside string literals is never touched.

    :param text: valid Python source
    :param char: border character; borders made of other characters are not recognized
    :param width: target total line width, indentation included
    :return: tuple of the new source and the number of headers whose borders were changed
    """
    lines = text.split('\n')

    # Line index -> (column, comment text) for every comment that is alone on its line.
    comments: dict[int, tuple[int, str]] = {}
    for tok in tokenize.generate_tokens(io.StringIO(text).readline):
        if (tok.type == tokenize.COMMENT) and (tok.line[:tok.start[1]].strip() == ''):
            comments[tok.start[0] - 1] = (tok.start[1], tok.string.rstrip())

    idxs = sorted(comments)

    def continues(k: int, col: int) -> bool:
        return (k < len(idxs)) and (idxs[k] == idxs[k - 1] + 1) and (comments[idxs[k]][0] == col)

    n_changed = 0
    k = 0
    while k < len(idxs):
        col = comments[idxs[k]][0]
        if not is_border(comments[idxs[k]][1], char):
            k += 1
            continue

        m = k + 1
        while continues(m, col) and not is_border(comments[idxs[m]][1], char):
            m += 1

        if (m > k + 1) and continues(m, col):
            changed = False
            if width - col - 2 >= 1:
                for border_idx in (idxs[k], idxs[m]):
                    new_line = lines[border_idx][:col] + make_border(0, char, width - col)
                    if lines[border_idx] != new_line:
                        lines[border_idx] = new_line
                        changed = True
            n_changed += changed
            k = m + 1
        else:
            k += 1

    return '\n'.join(lines), n_changed


def format_file(
    path:         Path,
    border_char:  str  = DEFAULT_BORDER_CHAR,
    border_width: int  = DEFAULT_BORDER_WIDTH,
    normalize:    bool = True,
) -> int:
    """
    Format section headers in a single file in place.

    Uses :mod:`ast` to identify module-level string-expression statements (the canonical "section header" pattern),
    which avoids the pitfalls of naive line-based pairing -- a closing triple double-quote line belonging to a
    multi-line string literal inside a function or assignment is no longer mistaken for a standalone delimiter.
    Afterwards, unless disabled, the borders of every boxed comment header are resized with :func:`normalize_borders`.

    :param path: path to the Python file to convert
    :param border_char: character used to draw borders
    :param border_width: total border line width in characters (indentation included)
    :param normalize: whether to resize the borders of existing boxed comment headers
    :return: number of headers converted or resized (zero if no changes were made), or -1 if the file could not be
             parsed as valid Python
    """

    # Read without newline translation so CRLF files round-trip; work on LF text and restore the endings on write.
    with path.open(encoding='utf-8', newline='') as fh:
        raw = fh.read()

    eol   = '\r\n' if '\r\n' in raw else '\n'
    text  = raw.replace('\r\n', '\n')
    lines = text.split('\n')
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as e:
        print(f'ERROR: {path} could not be parsed as Python; skipping ({e})', file=sys.stderr)
        return -1

    string_exprs: list[ast.Expr] = [
        node for node in tree.body if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        )
    ]

    sections: list[tuple[int, int]] = []
    for j, node in enumerate(string_exprs):
        open_idx  = node.lineno - 1
        close_idx = (node.end_lineno or node.lineno) - 1

        # Only convert multi-line section headers whose open and close lines are exactly ``"""``.
        # This filters out single-line ``"""..."""`` strings as well as triple-single-quoted (``'''``) blocks.
        if open_idx == close_idx:
            continue
        if (lines[open_idx] != '"""') or (lines[close_idx] != '"""'):
            continue

        # Preserve the module docstring (only legal as the first statement when nothing but blanks/comments precede it).
        if (j == 0) and is_module_docstring_position(lines[:open_idx]):
            continue

        sections.append((open_idx, close_idx))

    border = make_border(0, border_char, border_width)
    for open_idx, close_idx in reversed(sections):
        content_lines = lines[open_idx + 1:close_idx]
        replacement   = [border]

        for content_line in content_lines:
            stripped = content_line.rstrip()
            if stripped == '':
                replacement.append('#')
            else:
                replacement.append('# ' + stripped)

        replacement.append(border)
        lines[open_idx:close_idx + 1] = replacement

    new_text  = '\n'.join(lines)
    n_resized = 0
    if normalize:
        try:
            new_text, n_resized = normalize_borders(new_text, border_char, border_width)
        except (tokenize.TokenError, SyntaxError) as e:
            print(f'ERROR: {path} could not be tokenized; skipping ({e})', file=sys.stderr)
            return -1

    if new_text != text:
        with path.open('w', encoding='utf-8', newline='') as fh:
            fh.write(new_text.replace('\n', eol))
    return len(sections) + n_resized


# ==================================================================================================
# Python file iteration
# ==================================================================================================


def iter_python_files(paths: list[Path]) -> list[Path]:
    """
    Expand ``paths`` (files and/or directories) into a flat list of .py files.

    Files passed directly are included as-is (regardless of suffix). Directories are recursed and any ``.py`` file
    under them is yielded, except those inside well-known generated/vendored directories (``.git``, ``.venv``, ``venv``,
    ``.tox``, ``site-packages``, ``__pycache__``).

    :param paths: list of file or directory paths
    :return: deduplicated list of file paths to process, sorted for deterministic output
    """
    seen:   set[Path]  = set()
    result: list[Path] = []

    for path in paths:
        if path.is_file():
            resolved = path.resolve()
            if resolved not in seen:
                seen.add(resolved)
                result.append(path)

        elif path.is_dir():
            for py_path in sorted(path.rglob('*.py')):
                if SKIP_DIRS.intersection(py_path.parts):
                    continue

                resolved = py_path.resolve()
                if resolved not in seen:
                    seen.add(resolved)
                    result.append(py_path)

        else:
            print(f'WARN: skipping non-existent path: {path}', file=sys.stderr)

    return result


# ==================================================================================================
# CLI
# ==================================================================================================


class Args(argparse.Namespace):
    """
    :class:`argparse.Namespace` annotated with args supported by this script.
    """
    paths:                list[Path]        # positional arg(s) "PATHS"
    exit_non_zero_on_fix: bool              # --exit-non-zero-on-fix
    normalize_borders:    bool              # --no-normalize-borders
    border_char:          str               # --border-char
    border_width:         int               # --border-width


def border_char_type(value: str) -> str:
    """
    Validate a ``--border-char`` value.

    :param value: raw command-line value
    :raises argparse.ArgumentTypeError: if the value is not exactly one non-whitespace character
    :return: the validated character
    """
    if (len(value) != 1) or value.isspace():
        raise argparse.ArgumentTypeError(f'must be a single non-whitespace character, got {value!r}')
    return value


def border_width_type(value: str) -> int:
    """
    Validate a ``--border-width`` value.

    :param value: raw command-line value
    :raises argparse.ArgumentTypeError: if the value is not an integer of at least 3 (room for ``# `` and one border
                                        character)
    :return: the validated width
    """
    try:
        width = int(value)
    except ValueError as e:
        raise argparse.ArgumentTypeError(f'must be an integer, got {value!r}') from e
    if width < 3:
        raise argparse.ArgumentTypeError(f'must be at least 3, got {width}')
    return width


def parse_args(argv: list[str] | None = None) -> Args:
    """
    Parse command-line arguments.

    :param argv: argument list (defaults to ``sys.argv[1:]``)
    :return: parsed namespace
    """
    parser = argparse.ArgumentParser(
        description=(
            'Convert module-level triple-quoted section headers to boxed comment headers and normalize the width of\n'
            'existing boxed comment header borders.'
        ),
        formatter_class=functools.partial(
            argparse.RawTextHelpFormatter,
            max_help_position=50,
        ),
        add_help=False,
    )

    def add_positional() -> None:
        parser.add_argument(
            'paths',
            nargs='*',
            type=Path,
            default=[Path()],
            help='Files or directories to process (default: current working directory)',
        )
    add_positional()

    def add_border_opts() -> None:
        border_opts = parser.add_argument_group('Border options')
        border_opts.add_argument(
            '--border-char',
            type=border_char_type,
            default=DEFAULT_BORDER_CHAR,
            metavar='CHAR',
            help=f'Character used to draw borders (default: {DEFAULT_BORDER_CHAR!r})',
        )
        border_opts.add_argument(
            '--border-width',
            type=border_width_type,
            default=DEFAULT_BORDER_WIDTH,
            metavar='N',
            help=(
                'Total border line width in characters, indentation and the leading "# " included '
                f'(default: {DEFAULT_BORDER_WIDTH})'
            ),
        )
        border_opts.add_argument(
            '--no-normalize-borders',
            dest='normalize_borders',
            action='store_false',
            help='Do not resize the borders of existing boxed headers (only convert triple-quoted headers)',
        )
    add_border_opts()

    def add_behavior_opts() -> None:
        behavior_opts = parser.add_argument_group('Behavior options')
        behavior_opts.add_argument(
            '--exit-non-zero-on-fix',
            action='store_true',
            help='Exit with code 1 if any file was modified (for pre-commit fixer hooks)',
        )
    add_behavior_opts()

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

    return parser.parse_args(argv, namespace=Args())


def main(argv: list[str] | None = None) -> int:
    """
    Entry point for the conversion script.

    :param argv: argument list (defaults to ``sys.argv[1:]``)
    :return: process exit code (0 normally, 1 when ``--exit-non-zero-on-fix`` and a file was modified, or when any file
             was skipped because it could not be parsed as Python)
    """
    args = parse_args(argv)

    n_files_with_replacements = 0
    n_errors                  = 0

    for py_path in iter_python_files(args.paths):
        replaced = format_file(py_path, args.border_char, args.border_width, args.normalize_borders)
        if replaced < 0:
            n_errors += 1
        elif replaced:
            n_files_with_replacements += 1
            print(f'{py_path}: fixed {replaced} header{"s" if replaced > 1 else ""}')

    if n_errors > 0:
        return 1
    return 1 if args.exit_non_zero_on_fix and (n_files_with_replacements > 0) else 0


if __name__ == '__main__':
    sys.exit(main())
