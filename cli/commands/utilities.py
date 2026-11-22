"""
Utility commands (makefile, diagnose)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import ClassVar

from cli.infra import config
from cli.infra.command import Command
from cli.infra.command import get_commands
from cli.utils.scripts import check_script_validity
from cli.utils.shell import shell_command
from cli.utils.styling import printf
from cli.utils.styling import style
from cli.utils.styling import unstyle

__all__ = [
    'DiagnoseCommand',
    'MakefileCommand',
]


# ==================================================================================================
# Utilities commands
#
# General repository maintenance commands:
#   - diagnose: Generate diagnostic report for python environment debug
#   - makefile: Generate Makefile targets from registered Command classes
#     - Parses all registered commands and creates equivalent Make targets
#     - Organizes targets by command group
#     - Preserves command descriptions in Make comments
#     - Auto-generates help target with formatted command listing
# ==================================================================================================


class MakefileCommand(Command):
    """
    Generate Makefile from project management script commands
    """
    name:        ClassVar[str] = 'makefile'
    group:       ClassVar[str] = 'Utilities'
    description: ClassVar[str] = ' '.join([
        'Generate Makefile from project management script commands',
        style(f'({config.SCRIPT_PATH.name})', dim=True),
    ])

    class Args(argparse.Namespace):
        col_spacing: int        # --col-spacing

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            '-c',
            '--col-spacing',
            '--spacing',
            dest='col_spacing',
            metavar='COLS',
            type=int,
            default=config.MAKEFILE_HELP_COL_SPACING,
            help=(
                f'Width of spacing between command name and command description columns '
                f'in generated Makefile help target\n'
                f'(default: {config.MAKEFILE_HELP_COL_SPACING})'
            ),
        )

    def run(self, args: Args) -> None:
        command_groups: dict[str, dict[str, Command]] = {}
        command_names:  list[str]                     = []

        for group_name, commands in get_commands(by_group=True).items():
            for cmd_name, cmd_info in commands.items():
                if not cmd_info.script_only:
                    command_groups.setdefault(group_name, {})[cmd_name] = cmd_info
                    command_names.append(cmd_name)

        lines: list[str] = [
            '#',
            "# Makefile for Connor's dotfiles",
            '#',
            f'# Auto-generated via `{config.SCRIPT_PATH.name} makefile`',
            '#',
            f'.PHONY: help {" ".join(command_names)}',
            '',
            'BRIGHT_GREEN := \\033[0;92m',
            'BRIGHT_WHITE := \\033[0;97m',
            'YELLOW := \\033[0;33m',
            'NC := \\033[0m',
            '',
            'help: ## Show this help message',
            '\t@echo "$(BRIGHT_GREEN)Runner script for Connor\'s dotfiles$(NC)"',
            '\t@echo ""',
        ]

        # Add grouped help display
        col1_width = len(max(command_names, key=len))
        for group_name, commands in command_groups.items():
            lines.append(f'\t@echo "$(BRIGHT_WHITE){group_name}:$(NC)"')
            for cmd_name, cmd_info in commands.items():
                desc = (
                    unstyle(cmd_info.description).splitlines()[0] if cmd_info.description else f'Run {cmd_name} command'
                )
                lines.append(f'\t@echo "  $(YELLOW){cmd_name:<{col1_width + args.col_spacing}}$(NC) {desc}"')
            lines.append('\t@echo ""')
        lines.append('')

        # Add targets grouped by section
        for group_name, commands in command_groups.items():
            lines.append(f'# {group_name}')
            for cmd_name, cmd_info in commands.items():
                target = f'{cmd_name}:'
                if cmd_info.description:
                    target += f' ## {unstyle(cmd_info.description).splitlines()[0]}'
                lines.extend([
                    target,
                    f'\t@python3 {config.SCRIPT_PATH.relative_to(config.DOTFILES_DIR)} {cmd_name}',
                    '',
                ])

        with config.MAKEFILE.open('w') as f:
            f.write('\n'.join(lines))
        printf('✅ Makefile updated', fg='bright_green')


class DiagnoseCommand(Command):
    """
    Gather and output local Python environment information to help triage installation/configuration issues
    """
    name:  ClassVar[str] = 'diagnose'
    group: ClassVar[str] = 'Utilities'

    class Args(argparse.Namespace):
        max_installed_packages: int | None      # --max-installed-packages
        save:                   bool            # --save
        json:                   bool            # --json
        output:                 Path | None     # --output

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        def add_console_out_opts() -> None:
            console_out_opts = parser.add_argument_group('Console output options')
            console_out_opts.add_argument(
                '--max-installed-packages',
                metavar='NUM',
                type=int,
                help='Max number of installed python packages to list under "INSTALLED PACKAGES"',
            )
        add_console_out_opts()

        def add_file_out_opts() -> None:
            file_out_opts = parser.add_argument_group('File output options')
            file_out_opts.add_argument(
                '-s',
                '--save',
                action='store_true',
                help='Save output to file instead of printing',
            )
            file_out_opts.add_argument(
                '-j',
                '--json',
                action='store_true',
                help='Output as JSON format',
            )
            file_out_opts.add_argument(
                '-o',
                '--output',
                type=Path,
                metavar='FILEPATH',
                help='Output file path (default: python_diagnostic_<timestamp>.txt)',
            )
        add_file_out_opts()

    def run(self, args: Args) -> None:
        check_script_validity(config.DIAGNOSTIC_SCRIPT_PATH, 'python diagnostic script')

        printf('🔧 Running python diagnostic script...', fg='bright_cyan')
        shell_command([
            sys.executable,
            str(config.DIAGNOSTIC_SCRIPT_PATH),
            *(['--max-installed-packages', str(args.max_installed_packages)] if args.max_installed_packages else []),
            *(['--save']                                                     if args.save                   else []),
            *(['--json']                                                     if args.json                   else []),
            *(['--output', str(args.output)]                                 if args.output                 else []),
        ], indent=3)
