"""
Argument parser construction and the ``main`` entry point
"""
from __future__ import annotations

import argparse
import sys
import traceback
from collections.abc import Sequence

from cli.infra import config
from cli.infra.command import REGISTERED_COMMANDS
from cli.infra.command import get_commands
from cli.infra.command import get_default_help_formatter_cls
from cli.infra.config import RUN_DEBUG_ENVVAR
from cli.infra.config import SCRIPT_HELP_COL_SPACING
from cli.infra.config import UV_VERBOSE
from cli.infra.config import UV_VERBOSE_ENVVAR
from cli.infra.config import ExitCode
from cli.utils.shell import RUN_COMMAND_ENVVARS
from cli.utils.styling import arg_note
from cli.utils.styling import printf
from cli.utils.styling import style

__all__ = [
    'Args',
    'build_parser',
    'build_parser_help_text',
    'main',
]


# ==================================================================================================
# Command-line argument parsing / entry point
#
# build_parser() creates the root parser (help text organized by command group, plus Debug Options and Other Options
# groups) and one subparser per registered Command, each with its -h/--help in a trailing "Other options" group.
#
# main() parses args into the typed root Args namespace, enables debug mode if requested, dispatches to the selected
# command, and maps Ctrl-C / unexpected errors to ExitCode values.
# ==================================================================================================


class Args(argparse.Namespace):
    """
    Annotated :class:`argparse.Namespace` returned by parsing with :func:`build_parser`
    """
    command:    str | None  # subcommand name
    debug:      bool        # --debug
    uv_verbose: bool        # --uv-verbose


def build_parser_help_text(*, col_spacing: int = SCRIPT_HELP_COL_SPACING) -> str:
    """
    Build help text for argument parser with commands listed by group

    :param col_spacing: width of spacing between command name and command description columns in script help text
    :return: help text string
    """
    col1_width = len(max(get_commands(), key=len))

    help_text = style("Runner script for Connor's dotfiles", fg='bright_green') + '\n\n'
    help_text += style('Commands:', fg='bright_white', bold=True) + '\n\n'
    for group_name, commands in get_commands(by_group=True).items():
        help_text += f'  {style(group_name, fg="bright_white")}\n'
        for cmd_name, cmd_info in commands.items():
            if not cmd_info.makefile_only:
                description = cmd_info.description or f'Run {cmd_name} command'
                help_text += f'    {style(cmd_name.ljust(col1_width + col_spacing), fg="yellow")} '
                help_text += f'{description.splitlines()[0]}\n'
        help_text += '\n'
    return help_text


def build_parser() -> argparse.ArgumentParser:
    """
    Build argument parser

    :return: :class:`argparse.ArgumentParser`
    """
    parser = argparse.ArgumentParser(
        description=build_parser_help_text(),
        formatter_class=get_default_help_formatter_cls(),
        add_help=False,
    )

    def add_subcommand_parsers() -> None:
        """
        Register all command subparsers from the ``REGISTERED_COMMANDS`` registry
        """
        subparsers = parser.add_subparsers(
            dest='command',
            metavar='COMMAND',
            help=argparse.SUPPRESS,
        )
        for cmd_name, cmd in REGISTERED_COMMANDS.items():
            subparser = subparsers.add_parser(
                cmd_name,
                description=cmd.description or f'Run {cmd_name} command',
                help=cmd.description        or f'Run {cmd_name} command',
                epilog=cmd.epilog,
                formatter_class=cmd.help_formatter_type,
                add_help=False,
            )
            cmd.add_arguments(subparser)
            if cmd.add_help:
                cmd_other_opts = subparser.add_argument_group('Other options')
                cmd_other_opts.add_argument(
                    '-h',
                    '--help',
                    action='help',
                    default=argparse.SUPPRESS,
                    help='Show this help message and exit',
                )
    add_subcommand_parsers()

    def add_debug_opts() -> None:
        """
        Add the debug argument group to the root parser
        """
        debug_opts = parser.add_argument_group(
            title=style('Debug Options', fg='bright_white', bold=True),
        )
        debug_opts.add_argument(
            '-d',
            '--debug',
            action=argparse.BooleanOptionalAction,
            dest='debug',
            default=config.RUN_DEBUG,
            help=' '.join([
                'Enable script debug logging          ',
                arg_note('env var', RUN_DEBUG_ENVVAR) + '   ',
                arg_note(
                    'default',
                    repr(config.RUN_DEBUG),
                    color='bright_green' if config.RUN_DEBUG else 'bright_red',
                ),
            ]),
        )
        debug_opts.add_argument(
            '--uv-verbose',
            action=argparse.BooleanOptionalAction,
            dest='uv_verbose',
            default=UV_VERBOSE,
            help=' '.join([
                'Enable verbose logging from uv       ',
                arg_note('env var', UV_VERBOSE_ENVVAR) + '  ',
                arg_note(
                    'default',
                    repr(UV_VERBOSE),
                    color='bright_green' if UV_VERBOSE else 'bright_red',
                ),
            ]),
        )

        # Remove extra default value string from options w/ `action=BooleanOptionalAction` (automatically added somehow)
        for option in debug_opts._group_actions:
            if option.help:
                option.help = option.help.split('(default: ', 1)[0]
    add_debug_opts()

    def add_other_opts() -> None:
        """
        Add the help option and other miscellaneous options group to the root parser
        """
        other_opts = parser.add_argument_group(
            title=style('Other Options', fg='bright_white', bold=True),
        )
        other_opts.add_argument(
            '-h',
            '--help',
            action='help',
            default=argparse.SUPPRESS,
            help='Show this help message and exit',
        )
    add_other_opts()

    return parser


def main(argv: Sequence[str] | None = None) -> None:
    """
    Main entry point

    :param argv: argument list to parse. Defaults to ``sys.argv[1:]``
    """
    # Build argument parser and parse command-line args
    parser: argparse.ArgumentParser = build_parser()
    args:   Args                    = parser.parse_args(argv, namespace=Args())

    # Print help text if no command provided
    if not args.command:
        parser.print_help()
        sys.exit(ExitCode.COMMAND_FAILED)

    # Enable debug logging
    if args.uv_verbose:
        RUN_COMMAND_ENVVARS['RUST_LOG'] = 'uv=debug'
    config.RUN_DEBUG = args.debug

    # Run specified command
    commands = get_commands()
    if cmd := commands.get(args.command):
        try:
            cmd(args)
        except KeyboardInterrupt:
            printf('⚠️ Operation cancelled by user', fg='yellow')
            sys.exit(ExitCode.USER_CANCELLED)
        except Exception as e:
            printf(f'❌ Unexpected error: {e!s}', fg='red', bold=True)
            if config.RUN_DEBUG:
                traceback.print_exc(file=sys.stderr)
            sys.exit(ExitCode.COMMAND_FAILED)

    else:
        printf(f'❓ Unknown command: {args.command}', fg='red', bold=True)
        printf(f'   Available commands: {", ".join(commands.keys())}')
        sys.exit(ExitCode.SETUP_ERROR)
