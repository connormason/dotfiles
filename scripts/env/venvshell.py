#!/usr/bin/env python3
"""
Launch an interactive subshell with a python project's virtual environment activated
"""
from __future__ import annotations

import argparse
import atexit
import enum
import functools
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from typing import Literal
from typing import Protocol
from typing import TypeVar
from typing import Union
from typing import cast

if TYPE_CHECKING:
    from collections.abc import Iterable
    from collections.abc import Sequence


# ====================
# Script configuration
# ====================

#: Directory names to look for virtual environments within when auto-discovering environment
VENV_DIR_NAMES: list[str] = ['.venv', 'venv']

#: Enable usage with hatch environments. If False, all functionality relating to hatch will be disabled
HATCH_ENABLED: bool = True


# =======================================================================================
# Script configuration/argument defaults that can be overridden via environment variables
# =======================================================================================

#: Default path to look for virtual environment directory (--path option default)
#: This hard-codes the default path we look for the virtual environment to activate, overriding auto-discovery behavior
PATH_ENVVAR:            str         = 'VENVSHELL_PATH'
PATH_DEFAULT:           Path | None = None

#: Default hatch env name (--hatch option default)
HATCH_ENV_ENVVAR:       str        = 'VENVSHELL_HATCH_ENV'
HATCH_ENV_DEFAULT:      str | None = None

#: Enable/disable virtual environment auto-discovery
#: If disabled, environment must be specified explicitly via command-line options (--path or --hatch)
DISCOVER_ENVVAR:        str  = 'VENVSHELL_DISCOVER'
DISCOVER_DEFAULT:       bool = True

#: Enable/disable auto-discovery of `hatch` environments (as fallback if no env directory found in project)
#: Ignored if auto-discovery is disabled
HATCH_DISCOVER_ENVVAR:  str  = 'VENVSHELL_DISCOVER_HATCH'
HATCH_DISCOVER_DEFAULT: bool = True


# =====
# Types
# =====

SupportedShell = Literal['bash', 'zsh', 'fish']
PathLike       = Union[Path, str]
StyleColor     = Union[int, tuple[int, int, int], str]
T_contra       = TypeVar('T_contra', contravariant=True)


class SupportsWrite(Protocol[T_contra]):
    """
    Protocol for writable things (like :attr:`sys.stdout` and :attr:`sys.stderr`)
    """
    def write(self, s: T_contra, /) -> object: ...


class Exit(Exception):
    """
    Exception raised to indicate script should exit

    :param code: script exit code (passed to :func:`sys.exit`)
    :param message: message to output when exiting script
    """
    class Code(enum.IntEnum):
        SUCCESS             = 0
        ENV_ALREADY_ACTIVE  = 0
        EXISTING_ENV_ACTIVE = 1
        INVALID_PARAM       = 64      # EX_USAGE:       bad command-line usage
        ENV_INVALID         = 65      # EX_DATAERR:     bad input data
        ENV_NOT_FOUND       = 69      # EX_UNAVAILABLE: service unavailable
        ACTIVATION_FAILED   = 90

    def __init__(
        self,
        code: Code | int,
        message: str | None = None,
        *,
        error: bool | None = None,
        warning: bool | None = None,
        file: SupportsWrite[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code    = code
        self.message = message
        self.error   = error
        self.warning = warning
        self.file    = file

    def exit(self) -> None:
        if self.message:
            printf(
                self.message,
                error=self.error if self.error is not None else (self.code != 0),
                warning=self.warning if self.warning is not None else False,
                file=self.file or sys.stderr,
            )
        sys.exit(self.code)


# ==========================
# Logging/formatting helpers
# ==========================


def style(
    text: Any,
    *,
    fg: StyleColor | None = None,
    bg: StyleColor | None = None,
    bold: bool | None = None,
    dim: bool | None = None,
    underline: bool | None = None,
    italic: bool | None = None,
    reset: bool = True,
) -> str:
    """
    Style text with ANSI codes and return the new string

    :param text: the string to style with ansi codes
    :param fg: foreground color
    :param bg: background color
    :param bold: enable or disable bold mode
    :param dim: enable or disable dim mode
    :param underline: enable or disable underline
    :param italic: enable or disable italic
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
        if isinstance(_color, int):
            return f'{38 + offset};5;{_color:d}'
        elif isinstance(_color, (tuple, list)):
            r, g, b = _color
            return f'{38 + offset};2;{r:d};{g:d};{b:d}'
        else:
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
    if italic is not None:
        bits.append(f'\033[{3 if italic else 23}m')

    bits.append(text)
    if reset:
        bits.append(_ansi_reset_all)
    return ''.join(bits)


def unstyle(text: str) -> str:
    """
    Removes ANSI styling information from a string

    :param text: the text to remove style information from
    :return: string with ANSI styling characters removed
    """
    return re.sub(r'\033\[[;?0-9]*[a-zA-Z]', '', text)


def printf(
    text: str,
    *,
    fg: StyleColor | None = None,
    bold: bool | None = None,
    dim: bool | None = None,
    indent: int = 0,
    file: SupportsWrite[str] | None = None,
    error: bool = False,
    warning: bool = False,
) -> None:
    """
    Print styled text

    :param text: text to print
    :param fg: foreground color
    :param bold: bold mode
    :param dim: dim mode
    :param indent: number of spaces to indent output by
    :param file: output file (defaults to stdout)
    :param error: prefix text to indicate an error message, and log to stderr (instead of stdout)
    :param warning: prefix text to indicate a warning message, and log to stderr (instead of stdout)
    :raises ValueError: if `error=True` and `warning=True` at the same time
    """
    prefix: str | None = ''
    if error and warning:
        raise ValueError('printf() cannot accept `error=True` and `warning=True` at the same time')
    elif error:
        prefix = style(f'🔴 {style("Error",   fg="red",    bold=True)}: ')
    elif warning:
        prefix = style(f'🟡 {style("Warning", fg="yellow", bold=True)}: ')

    _file = file if file is not None else (sys.stderr if error or warning else None)
    if prefix:
        text_lines = text.splitlines()
        prefix_len = len(unstyle(prefix)) + 1
        for i, line in enumerate(text_lines):
            if i == 0:
                print(textwrap.indent(f'{prefix}{line}', ' ' * indent),                file=_file)
            else:
                print(textwrap.indent(line,              ' ' * (indent + prefix_len)), file=_file)
    else:
        print(
            textwrap.indent(style(text or '', fg=fg, bold=bold, dim=dim), ' ' * indent),
            file=_file,
        )


def folduser(path: PathLike) -> str:
    return str(path).replace(str(Path.home()), '~')


def pathstyle(path: PathLike, **opts: Any) -> str:
    return style(folduser(path), fg='magenta', **opts)


def optstyle(text: Any, **opts: Any) -> str:
    return style(text, fg='yellow', **opts)


def typestyle(val: Any, **opts: Any) -> str:
    if val is None:
        return style(str(val), fg='magenta', italic=True, **opts)
    elif isinstance(val, bool):
        return style(str(val), fg=f'bright_{"green" if val else "red"}', italic=True, **opts)
    elif isinstance(val, Path):
        return style(folduser(val), fg='magenta', **opts)
    elif isinstance(val, (int, float)):
        return style(repr(val), fg='bright_cyan', bold=True, **opts)
    elif isinstance(val, str):
        return style(repr(val), fg='green', **opts)
    else:
        return str(val)


def dim_paren(s: str, *, fg: StyleColor | None = None) -> str:
    return ''.join([
        style('(', dim=True),
        style(s,   dim=True, fg=fg),
        style(')', dim=True),
    ])


def annotated_opt_help(opt_help: str, *, default: Any | None = None, envvar: str | None = None) -> str:
    help_lines: list[str] = style(opt_help, fg='bright_white').splitlines()
    if default is not None:
        help_lines.append(f'  default: {typestyle(default)}')
    if envvar is not None:
        help_lines.append(f'  env var: {style(envvar, fg="cyan")}')
    return '\n'.join([*help_lines, '  '])


# =============================
# Virtual environment discovery
# =============================


def find_venv(start: PathLike | None = None, *, dir_names: Iterable[str] | None = None) -> Path | None:
    """
    Walk up from start looking for a `venv/` or `.venv/` directory

    :param start: search path to start searching for virtual env within. Defaults to current working directory
    :param dir_names: directory filenames to consider virtual env dir candidates. Defaults to :attr:`VENV_DIR_NAMES`
    :return: virtual environment directory, or None if no venv found
    """
    candidate_dir_names: set[str] = set(dir_names or VENV_DIR_NAMES)

    start_path = Path(start).expanduser() if start else Path.cwd()
    for directory in [start_path, *start_path.parents]:
        for name in candidate_dir_names:
            candidate = directory / name
            if (candidate / 'bin' / 'activate').exists():
                return candidate
    return None


def find_hatch_env(env_name: str | None = None, *, timeout: float = 10) -> Path | None:
    """
    Discover a hatch-managed virtual environment for the current project

    :param env_name: name of the hatch environment to find
    :param timeout: `hatch env find` command timeout
    :return: path to the hatch venv directory, or None if not found
    """
    try:
        result = subprocess.run(
            ['hatch', 'env', 'find', *([env_name] if env_name else [])],
            capture_output=True,
            text=True,
            check=True,
            timeout=timeout,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return None

    venv_path = Path(result.stdout.strip())
    if venv_path.is_dir() and (venv_path / 'bin' / 'activate').exists():
        return venv_path
    return None


def validate_venv(venv_path: Path) -> str | None:
    """
    Check that a virtual environment is functional

    :param venv_path: path to the virtual environment directory
    :return: error message if the venv is broken, None if healthy
    """
    python_bin = venv_path / 'bin' / 'python'
    if python_bin.is_symlink() and (not python_bin.resolve().exists()):
        return ' '.join([
            'venv python binary is a broken symlink:',
            style(folduser(python_bin),            fg='magenta'),
            style('->',                            fg='bright_white'),
            style(folduser(python_bin.readlink()), fg='magenta'),
        ])
    elif not python_bin.exists():
        return f'venv python binary not found: {pathstyle(python_bin)}'

    activate = venv_path / 'bin' / 'activate'
    if not activate.exists():
        return f'venv activate script not found: {pathstyle(activate)}'
    return None


# ====================================
# Virtual environment shell activation
# ====================================


#: Configuration files to source/symlink when activating virtual environment subshell, mapped by shell
DOTFILES: dict[SupportedShell, list[str]] = {
    'bash': ['.bashrc', '.bash_profile', '.profile'],
    'zsh':  ['.zshenv', '.zprofile', '.zlogin', '.zlogout'],
}


def launch_venv_shell(
    venv: PathLike,
    *,
    bash_dotfiles: Iterable[str] | None = None,
    zsh_dotfiles: Iterable[str] | None = None,
) -> None:
    """
    Spawn an interactive subshell with the venv activated

    :param venv: filepath to python virtual env directory
    :param bash_dotfiles: configuration files to source when activating virtual environment subshell via `bash`.
                          Default: "bash" entry in :attr:`DOTFILES`
    :param zsh_dotfiles: configuration files to source/symlink when activating virtual environment subshell via `zsh`.
                         Default: "zsh" entry in :attr:`DOTFILES`
    """
    venv_path = Path(venv).expanduser().resolve()
    home      = Path.home()
    activate  = venv_path / 'bin' / 'activate'

    dotfiles: dict[SupportedShell, list[str]] = {
        'bash': list(bash_dotfiles or DOTFILES['bash']),
        'zsh':  list(zsh_dotfiles  or DOTFILES['zsh']),
    }

    # Validate the venv before attempting to launch
    if error := validate_venv(venv_path):
        raise Exit(Exit.Code.ENV_INVALID, error)

    shell      = os.environ.get('SHELL', '/bin/bash')
    shell_name = Path(shell).name

    # Build shell-specific rc file in a temp directory
    # Using :func:`subprocess.run` (not :func:`os.execvpe`) so atexit cleanup of temp files actually runs
    tmpdir:     str | None = None
    shell_args: list[str]

    if shell_name == 'bash':
        tmpdir  = tempfile.mkdtemp(prefix='venv_shell_')
        rc_file = Path(tmpdir) / '.bashrc'
        rc_file.write_text('\n'.join([
            *[f'[ -f "{home / rc}" ] && source "{home / rc}"' for rc in dotfiles['bash']],
            f'source "{activate}"',
        ]))
        shell_args = [shell, '--rcfile', str(rc_file)]

    elif shell_name == 'zsh':
        tmpdir       = tempfile.mkdtemp(prefix='venv_shell_')
        real_zdotdir = Path(os.environ.get('ZDOTDIR', str(home)))

        # Symlink all zsh dotfiles except .zshrc from the real ZDOTDIR so they still run normally
        for dotfile in dotfiles['zsh']:
            real_file = real_zdotdir / dotfile
            if real_file.exists():
                (Path(tmpdir) / dotfile).symlink_to(real_file)

        # Custom .zshrc: source user's real config first, then activate venv
        zshrc = Path(tmpdir) / '.zshrc'
        zshrc.write_text('\n'.join([
            f'[ -f "{real_zdotdir}/.zshrc" ] && source "{real_zdotdir}/.zshrc"',
            f'source "{activate}"',
        ]))
        shell_args = [shell]

    elif shell_name == 'fish':
        activate_fish = venv_path / 'bin' / 'activate.fish'
        if not activate_fish.exists():
            printf(
                f'fish activate script not found {dim_paren(folduser(activate_fish), fg="magenta")}, '
                f'activating via env vars only',
                warning=True,
            )
            shell_args = [shell]
        else:
            # fish supports -C (--init-command) which runs after config.fish — no temp files needed
            shell_args = [shell, '-C', f'source "{activate_fish}"']

    # Fallback: just exec the shell; venv is activated via env vars below
    else:
        printf(f'unsupported shell {typestyle(shell_name)}, activating via env vars only', warning=True)
        shell_args = [shell]

    env = os.environ.copy()

    if tmpdir:
        atexit.register(shutil.rmtree, tmpdir, ignore_errors=True)
        if shell_name == 'zsh':
            env['ZDOTDIR'] = tmpdir

    # Set the env vars that `activate` would set
    # (useful for the fallback case and ensures consistency even if activate sourcing somehow fails)
    env['VIRTUAL_ENV'] = str(venv_path)
    env['PATH']        = f"{venv_path / 'bin'}:{env.get('PATH', '')}"
    env.pop('PYTHONHOME', None)

    exit_opts = [style('exit', fg='bright_magenta'), style('Ctrl-D', fg='bright_yellow')]
    printf(
        style('❯❯❯ ',                             fg='bright_green') +
        style('Activating virtual environment: ', fg='bright_white') +
        style(folduser(venv),                     fg='magenta') +
        '\n    ' +
        f'Type {" or ".join(exit_opts)} to exit the environment'
    )

    # Send it
    try:
        subprocess.run(shell_args, env=env, check=True)
    except (KeyboardInterrupt, subprocess.CalledProcessError):
        pass
    finally:
        printf(
            style('❮❮❮ ',                               fg='bright_red')   +
            style('Deactivating virtual environment: ', fg='bright_white', dim=True) +
            style(folduser(venv),                       fg='magenta', dim=True)
        )


# ===============================================================================
# Command-line argument parsing and environment variable configuration resolution
# ===============================================================================


def resolve_bool_env_var(env_var_name: str, default: bool | None = None) -> bool | None:
    if env_var_name in os.environ:
        str_val = os.environ[env_var_name].strip().lower()
        if str_val == 'true':
            return True
        elif str_val == 'false':
            return False
        else:
            printf(
                f'🟡 {style("Ignoring invalid env var value", fg="bright_yellow")}: '
                f'{style(env_var_name, fg="cyan")} {style("=", fg="bright_white")} {typestyle(str_val)} '
                f'{style("--", dim=True)} '
                f'Expected {typestyle("true")} or {typestyle("false")}\n',
                file=sys.stderr,
            )
    return default


class Args(argparse.Namespace):
    """
    Annotated :class:`argparse.Namespace` returned by :func:`parse_args`
    """
    path:           Path | None     # Positional arg "PATH" or --path
    hatch_env:      str | None      # --hatch
    discover:       bool            # --discover/--no-discover
    discover_hatch: bool            # --discover-hatch/--no-discover-hatch


def parse_args(argv: Sequence[str] | None = None) -> Args:
    """
    Parse command-line arguments

    :param argv: argument list to parse, defaults to sys.argv[1:]
    :return: parsed namespace (:class:`Args`)
    """
    parser = argparse.ArgumentParser(
        description='\n'.join([
            style('Launch an interactive subshell with a virtual environment activated', fg='bright_magenta'),
            '',
            f'Virtual environment may be specified explicitly via {optstyle("--path PATH")}, '
            f'or automatically discovered from the current project directory',
        ]),
        formatter_class=functools.partial(argparse.RawTextHelpFormatter, max_help_position=50),
        add_help=False,
    )

    def parser_group(title: str, description: str | None = None) -> argparse._ArgumentGroup:
        return parser.add_argument_group(
            title=style(title, fg='bright_blue'),
            description=style(description, fg='bright_white', dim=True) if description else None,
        )

    def add_positional_args() -> None:
        positional_args = parser_group('Positional arguments')
        positional_args.add_argument(
            'path',
            metavar='PATH',
            nargs='?',
            type=Path,
            default=None,
            help=f'Path to virtual environment directory (alternative to {optstyle("--path PATH")})',
        )

    def add_env_selection_opts() -> None:
        env_selection_opts = parser_group(
            'Environment selection options',
            'Specify the virtual environment to activate/enter',
        )

        path_default = os.environ.get(PATH_ENVVAR, PATH_DEFAULT)
        env_selection_opts.add_argument(
            '--path',
            metavar='PATH',
            dest='path_opt',
            type=Path,
            default=path_default,
            help=annotated_opt_help(
                'Path to virtual environment directory',
                default=path_default,
                envvar=PATH_ENVVAR,
            ),
        )

        if HATCH_ENABLED:
            hatch_default = os.environ.get(HATCH_ENV_ENVVAR, HATCH_ENV_DEFAULT)
            env_selection_opts.add_argument(
                '--hatch',
                metavar='ENV',
                dest='hatch_env',
                default=hatch_default,
                help=annotated_opt_help(
                    'Hatch environment name',
                    default=hatch_default,
                    envvar=HATCH_ENV_ENVVAR,
                ),
            )

    def add_env_discovery_opts() -> None:
        env_discovery_opts = parser_group(
            'Environment discovery options',
            'Configure automatic virtual environment discovery (if environment not specified explicitly)',
        )

        discover_default = resolve_bool_env_var(DISCOVER_ENVVAR, default=DISCOVER_DEFAULT)
        env_discovery_opts.add_argument(
            '--discover',
            action=argparse.BooleanOptionalAction,
            default=discover_default,
            help=annotated_opt_help(
                'Enable/disable auto-discovery of environments in current directory',
                default=discover_default,
                envvar=DISCOVER_ENVVAR,
            ),
        )

        if HATCH_ENABLED:
            discover_hatch_default = resolve_bool_env_var(HATCH_DISCOVER_ENVVAR, default=HATCH_DISCOVER_DEFAULT)
            env_discovery_opts.add_argument(
                '--discover-hatch',
                action=argparse.BooleanOptionalAction,
                default=discover_hatch_default,
                help=annotated_opt_help(
                    'Enable/disable auto-discovery of Hatch environments for current project',
                    default=discover_hatch_default,
                    envvar=HATCH_DISCOVER_ENVVAR,
                ),
            )

    def add_other_opts() -> None:
        other_opts = parser_group('Other options')
        other_opts.add_argument(
            '-h',
            '--help',
            action='help',
            default=argparse.SUPPRESS,
            help='Show this help message and exit',
        )

    # Add argument groups to parser
    add_positional_args()
    add_env_selection_opts()
    add_env_discovery_opts()
    add_other_opts()

    # Remove extra default value string from options w/ `action=BooleanOptionalAction` (automatically added somehow)
    for action_group in parser._action_groups:
        for action in action_group._group_actions:
            if action.help:
                action.help = action.help.split('(default: ', 1)[0]

    # Parse command-line args
    args = parser.parse_args(argv, namespace=Args())

    # Validate/resolve command-line arg values
    patharg  = optstyle('PATH')
    pathopt  = optstyle('--path')
    hatchopt = optstyle('--hatch')

    if args.path and args.path_opt:
        raise Exit(Exit.Code.INVALID_PARAM, f'cannot specify both positional {patharg} and {pathopt}')
    elif HATCH_ENABLED and args.path and args.hatch_env:
        raise Exit(Exit.Code.INVALID_PARAM, f'cannot specify both {hatchopt} and positional {patharg} argument')
    elif HATCH_ENABLED and args.path_opt and args.hatch_env:
        raise Exit(Exit.Code.INVALID_PARAM, f'cannot specify both {hatchopt} and {pathopt}')

    if args.path_opt:
        args.path = Path(args.path_opt)
    if args.path:
        args.path = Path(args.path).expanduser().resolve()
    return args


# =======================
# Core script entry point
# =======================


def main(argv: list[str] | None = None) -> None:
    """
    Main script entry point

    Virtual environment resolution order of precedence:

        1. Explicitly-provided env path             (--path or script positional arg)
        2. Explicitly-provided hatch env name       (--hatch, if `HATCH_ENABLED=True`)
        3. Automatically-discovered project dir     (from :attr:`VENV_DIR_NAMES`)
        4. Automatically-discovered hatch env name  (from :attr:`HATCH_ENV_DEFAULT`, if `HATCH_ENABLED=True`)

    :param argv: argument list to parse, defaults to sys.argv[1:]
    """

    # Load env var configuration + parse command-line arguments
    args = parse_args(argv)

    # Determine venv filepath to use
    venv: Path | None = None

    # [1] Explicitly-provided env path (--path or script positional arg)
    if args.path:
        if not args.path.exists():
            raise Exit(Exit.Code.ENV_NOT_FOUND, f'no virtual environment exists at {pathstyle(args.path)}')
        elif not args.path.is_dir():
            raise Exit(Exit.Code.ENV_INVALID,   f'virtual environment path is not a directory: {pathstyle(args.path)}')
        venv = args.path

    # [2] Explicitly-provided hatch env name (--hatch)
    elif HATCH_ENABLED and (args.hatch_env is not None):
        if hatch_venv := find_hatch_env(args.hatch_env):
            venv = hatch_venv
        else:
            raise Exit(Exit.Code.ENV_NOT_FOUND, f'could not find hatch environment {typestyle(args.hatch_env)}')

    # No explicit environment request, attempt to auto-discover
    if (venv is None) and args.discover:

        # [3] Automatically-discovered project dir ("venv/" or ".venv/", from :attr:`VENV_DIR_NAMES`)
        if discovered_venv := find_venv():
            venv = discovered_venv

        # [4] Automatically-discovered hatch env name (from :attr:`HATCH_ENV_DEFAULT`)
        if (venv is None) and HATCH_ENABLED and args.discover_hatch:
            if discovered_hatch_venv := find_hatch_env():
                venv = discovered_hatch_venv

    # No environment found
    if venv is None:
        cwd = Path.cwd()
        printf(f'No virtual environment found in {pathstyle(cwd)}', error=True)
        printf(' '.join([
            style('Use', dim=True, fg='bright_white'), optstyle('--path PATH', dim=True),
            *([style('or', dim=True, fg='bright_white'), optstyle('--hatch ENV', dim=True)] if HATCH_ENABLED else []),
            style('to specify an environment', dim=True, fg='bright_white'),
        ]), file=sys.stderr, indent=10)
        raise Exit(Exit.Code.ENV_NOT_FOUND)

    # Already an active virtual environment
    if 'VIRTUAL_ENV' in os.environ:
        active_venv = Path(os.environ['VIRTUAL_ENV'])

        # Active environment is the one we expected to enter
        if active_venv == venv:
            raise Exit(
                Exit.Code.ENV_ALREADY_ACTIVE,
                f'🟢 {style("Environment already active", fg="bright_green")}: '
                f'{style(folduser(active_venv), fg="bright_white")}',
            )

        # Active environment is some other environment (not the one we expected to enter)
        else:
            raise Exit(
                Exit.Code.EXISTING_ENV_ACTIVE,
                f'🟡 {style("Existing environment already active", fg="bright_yellow")}: '
                f'{style(folduser(active_venv), fg="bright_white")}',
                error=False,
            )

    # Activate virtual environment in subshell
    launch_venv_shell(venv)


if __name__ == '__main__':
    try:
        main()
    except Exit as e:
        e.exit()
