"""
ANSI text styling and styled console output (``style``, ``printf``, ``status_line``)
"""
from __future__ import annotations

import re
import sys
import textwrap
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from typing import cast

from cli.infra import config
from cli.infra.config import NO_COLOR
from cli.utils.formatting import folduser

if TYPE_CHECKING:
    from cli.infra.types import PathLike
    from cli.infra.types import StyleColor
    from cli.infra.types import SupportsWrite

__all__ = [
    'ANSI_COLOR',
    'ANSI_RESET_ALL',
    'HATCH',
    'UV',
    'arg_note',
    'dim_paren',
    'optstyle',
    'pathstyle',
    'printf',
    'status_line',
    'style',
    'typestyle',
    'unstyle',
]


# ==================================================================================================
# Text styling
#
# ANSI styling functions for terminal output. The style() function is inspired by Click's style implementation but
# standalone (no external dependencies)
#
# Supports:
#   - Foreground/background colors (named, 256-color palette, RGB tuples)
#   - Text attributes (bold, dim, italic, underline, etc.)
#   - Auto-reset by default to prevent style leakage
#
# The printf() function wraps style() for common use cases and supports:
#   - Debug mode filtering (only prints if DOTFILES_RUN_DEBUG=true)
#   - Text indentation
#   - Automatic text-to-str conversion
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
    Style text with ANSI escape codes. Returns the text unstyled when ``NO_COLOR`` is set.

    By default, the styling is self-contained. This means that at the end of the string, a reset code is issued.
    This can be prevented by passing ``reset=False``

    Examples::

        print(style('Hello World!', fg='green'))
        print(style('ATTENTION!', blink=True))
        print(style('Some things', reverse=True, fg='cyan'))
        print(style('More colors', fg=(255, 12, 128), bg=117))

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
    :param reset: by default a reset-all code is added at the end of the string which means that styles do not carry
                  over. This can be disabled to compose styles
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
    Removes ANSI styling information from a string

    :param text: the text to remove style information from
    :return: string with ANSI styling characters removed
    """
    return re.sub(r'\033\[[;?0-9]*[a-zA-Z]', '', text)


def arg_note(name: str, val: str, *, dim: bool = True, color: StyleColor | None = 'yellow') -> str:
    """
    Format a bracketed annotation string for argparse help text

    Produces styled output like ``[env var: DOTFILES_RUN_DEBUG]`` or ``[default: False]``

    :param name: the annotation label (e.g. ``"env var"``, ``"default"``)
    :param val: the annotation value
    :param dim: whether to apply dim styling
    :param color: foreground color for the value portion
    :return: the styled annotation string
    """
    return ''.join([
        style(f'[{name}: ', dim=dim),
        style(val,          dim=dim, fg=color),
        style(']',          dim=dim),
    ])


def dim_paren(s: str, *, fg: StyleColor | None = None) -> str:
    """
    Wrap text in dimmed parentheses with optional foreground color for the inner text

    :param s: text to wrap in parentheses
    :param fg: optional foreground color for the inner text
    :return: ANSI-styled string in the form ``(text)``
    """
    return ''.join([
        style('(', dim=True),
        style(s,   dim=True, fg=fg),
        style(')', dim=True),
    ])


def pathstyle(path: PathLike, **opts: Any) -> str:
    """
    Style a file path in magenta with the home directory folded to ``~``

    :param path: the file path to style
    :return: the ANSI-styled path string
    """
    return style(folduser(path), fg='magenta', **opts)


def optstyle(text: Any, **opts: Any) -> str:
    """
    Style a CLI option name in yellow.

    :param text: the option name to style
    :return: the ANSI-styled option string
    """
    return style(text, fg='yellow', **opts)


def typestyle(val: Any, **opts: Any) -> str:
    """
    Style a Python value by its type using semantic colors (roughly matching default repr styling provided by rich).

    Color mapping:

        - ``None`` = magenta italic
        - ``bool`` = green (True) / red (False) italic
        - ``Path`` = magenta with folduser
        - ``int``/``float`` = bright cyan bold
        - ``str`` = green

    Other types fall through to ``str(val)`` unstyled

    :param val: the Python value to style
    :return: the ANSI-styled representation
    """
    if val is None:
        return style(str(val),      fg='magenta',                             italic=True, **opts)
    if isinstance(val, bool):
        return style(str(val),      fg=f'bright_{"green" if val else "red"}', italic=True, **opts)
    if isinstance(val, Path):
        return style(folduser(val), fg='magenta',                                          **opts)
    if isinstance(val, (int, float)):
        return style(repr(val),     fg='bright_cyan',                         bold=True,   **opts)
    if isinstance(val, str):
        return style(repr(val),     fg='green',                                            **opts)
    if isinstance(val, Sequence):
        return ''.join([
            style('[', fg='bright_white'),
            ', '.join(typestyle(item, **opts) for item in val),
            style(']', fg='bright_white'),
        ])
    return str(val)


def printf(
    text: str,
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
    indent: int = 0,
    debug: bool = False,
    file: SupportsWrite[str] | None = None,
) -> None:
    """
    Print styled text with optional indentation and debug gating

    Applies ANSI styling via :func:`style` and prints the result. When ``debug=True``, the message is only emitted
    if the global ``RUN_DEBUG`` flag is set, defaults to dim bright-white text, and routes output to stderr

    :param text: the content to print (converted to str if needed)
    :param fg: foreground color
    :param bg: background color
    :param bold: enable or disable bold
    :param dim: enable or disable dim
    :param underline: enable or disable underline
    :param overline: enable or disable overline
    :param italic: enable or disable italic
    :param blink: enable or disable blink
    :param reverse: enable or disable reverse video
    :param strikethrough: enable or disable strikethrough
    :param reset: if True, append an ANSI reset sequence after the text
    :param indent: number of leading spaces to prepend
    :param debug: if True, only print when ``RUN_DEBUG`` is enabled and route to stderr
    :param file: output stream (defaults to stdout, or stderr when debug is True)
    """
    if debug and not config.RUN_DEBUG:
        return
    if debug:
        fg   = fg  if fg  is not None else 'bright_white'
        dim  = dim if dim is not None else True
        file = sys.stderr

    print(
        style(
            textwrap.indent(text, ' ' * indent),
            fg=fg,
            bg=bg,
            bold=bold,
            dim=dim,
            underline=underline,
            overline=overline,
            italic=italic,
            blink=blink,
            reverse=reverse,
            strikethrough=strikethrough,
            reset=reset,
        ),
        file=file,
        # Flush so our lines stay ordered with child-process output when stdout is a pipe (e.g. `| tee`): Python
        # block-buffers a pipe, while subprocesses write to it directly
        flush=True,
    )


def status_line(
    name: str,
    detail: str,
    path: Path | None = None,
    *,
    ok: bool = True,
    warn: bool = False,
    optional: bool = False,
    note: str = '',
) -> None:
    """
    Print a single status line with emoji, tool name, and detail.

    :param name: tool or component name
    :param detail: status detail text (version, message, etc.)
    :param path: optional path to display after the detail
    :param ok: True if the check passed
    :param warn: True if the check is a non-fatal warning
    :param optional: True if the component is optional
    :param note: additional note (e.g. what the tool is needed for)
    """
    emoji       = '✅' if ok else ('🟡' if (warn or optional) else '🔴')
    name_styled = style(name.ljust(12), fg='white', bold=True)
    if ok:
        detail_styled = style(detail, fg='bright_cyan')
    elif warn:
        detail_styled = style(detail, fg='bright_yellow')
    else:
        detail_styled = style(detail, fg='bright_red')

    loc    = f' {style(f"@ {folduser(path)}", dim=True)}' if path else ''
    suffix = f'  {style(f"({note})", dim=True)}' if note else ''
    printf(f'{emoji}  {name_styled} {detail_styled}{loc}{suffix}')


UV    = style('uv',    fg='bright_magenta')
HATCH = style('hatch', fg='bright_magenta')
