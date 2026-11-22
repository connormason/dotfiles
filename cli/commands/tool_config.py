"""
Tool config command (config)
"""
from __future__ import annotations

import argparse
import difflib
import os
import shlex
import sys
from typing import TYPE_CHECKING
from typing import ClassVar

from cli.infra.command import Command
from cli.infra.config import DOTFILES_DIR
from cli.infra.config import TOOL_CONFIGS
from cli.infra.config import ExitCode
from cli.utils.shell import shell_command
from cli.utils.styling import optstyle
from cli.utils.styling import pathstyle
from cli.utils.styling import printf
from cli.utils.styling import style

if TYPE_CHECKING:
    from pathlib import Path

__all__ = [
    'ConfigCommand',
]


DEFAULT_EDITOR: str = 'vi'


def _editor_command() -> list[str]:
    """
    Resolve the editor command: ``$VISUAL``, then ``$EDITOR``, then :data:`DEFAULT_EDITOR`.

    :return: editor executable and its arguments (``EDITOR='code --wait'`` yields two items)
    """
    return shlex.split(os.environ.get('VISUAL') or os.environ.get('EDITOR') or DEFAULT_EDITOR)


def _display_path(path: Path) -> str:
    """
    Style a registered file for display, relative to the repository root

    :param path: absolute path of a registered file
    :return: styled repo-relative path
    """
    return pathstyle(path.relative_to(DOTFILES_DIR))


def _print_tools(*, indent: int = 0) -> None:
    """
    Print every registered tool with its primary file, noting how many more files ``--all`` would open

    :param indent: number of spaces to indent each line by
    """
    width = max(map(len, TOOL_CONFIGS))
    for tool, paths in TOOL_CONFIGS.items():
        extra = f' {style(f"(+{len(paths) - 1} more)", dim=True)}' if len(paths) > 1 else ''
        printf(f'{style(tool.ljust(width), fg="white", bold=True)}  {_display_path(paths[0])}{extra}', indent=indent)


# ==================================================================================================
# Tool config command
#
#   - config: open a tool's config file (registered in TOOL_CONFIGS) in $VISUAL / $EDITOR
#     - Opens the tool's primary file; --all opens every registered file for the tool
#     - --print-path prints the path(s) instead, for use in scripts and command substitution
#     - --list shows every tool name with its primary file
# ==================================================================================================


class ConfigCommand(Command):
    """
    Open a tool's config file in $VISUAL / $EDITOR
    """
    name:  ClassVar[str] = 'config'
    group: ClassVar[str] = 'Utilities'

    class Args(argparse.Namespace):
        tool:       str | None      # TOOL
        all_files:  bool            # --all
        list_tools: bool            # --list
        print_path: bool            # --print-path

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            'tool',
            nargs='?',
            metavar='TOOL',
            help=f'Tool whose config to open (see {optstyle("--list")})',
        )

        def add_selection_opts() -> None:
            selection_opts = parser.add_argument_group('Selection options')
            selection_opts.add_argument(
                '-a',
                '--all',
                dest='all_files',
                action='store_true',
                help='Open every config file registered for the tool, not just the primary one',
            )
        add_selection_opts()

        def add_output_opts() -> None:
            output_opts = parser.add_argument_group('Output options')
            output_opts.add_argument(
                '-l',
                '--list',
                dest='list_tools',
                action='store_true',
                help='List the available tools with their primary config file',
            )
            output_opts.add_argument(
                '-p',
                '--print-path',
                dest='print_path',
                action='store_true',
                help='Print the config file path(s) instead of opening an editor',
            )
        add_output_opts()

    def run(self, args: Args) -> None:
        if args.list_tools:
            _print_tools()
            return

        if args.tool is None:
            printf('❌ No tool given. Available tools:', fg='bright_red')
            _print_tools(indent=3)
            sys.exit(ExitCode.COMMAND_FAILED)

        if args.tool not in TOOL_CONFIGS:
            printf(f"❌ Unknown tool '{args.tool}'", fg='bright_red')
            if matches := difflib.get_close_matches(args.tool, TOOL_CONFIGS, n=3):
                printf(f'Did you mean: {", ".join(style(m, fg="bright_cyan") for m in matches)}?', indent=3)
            else:
                printf('Available tools:', indent=3)
                _print_tools(indent=5)

            sys.exit(ExitCode.COMMAND_FAILED)

        paths = TOOL_CONFIGS[args.tool] if args.all_files else TOOL_CONFIGS[args.tool][:1]
        if args.print_path:
            for path in paths:
                print(path)
            return

        cmd: list[str] = [*_editor_command(), *map(str, paths)]
        try:
            result = shell_command(cmd, check=False)
        except FileNotFoundError:
            printf(
                f'❌ Editor not found: {style(cmd[0], fg="bright_magenta")} '
                f'(set $VISUAL or $EDITOR to an installed editor)',
                fg='bright_red',
            )
            sys.exit(ExitCode.SETUP_ERROR)
        else:
            sys.exit(result.returncode)
