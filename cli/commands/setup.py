"""
Setup & Environment commands (install, dev, shell, status, doctor, clean)
"""
from __future__ import annotations

import argparse
import os
import shlex
import shutil
import sys
from typing import TYPE_CHECKING
from typing import Any
from typing import ClassVar
from typing import cast

from cli.infra import config
from cli.infra.command import Command
from cli.infra.config import ExitCode
from cli.utils.doctor_checks import check_hooks
from cli.utils.doctor_checks import doctor_checks
from cli.utils.prompts import confirm
from cli.utils.python import check_python
from cli.utils.shell import shell_command
from cli.utils.styling import pathstyle
from cli.utils.styling import printf
from cli.utils.styling import status_line
from cli.utils.styling import style
from cli.utils.uv import check_uv
from cli.utils.uv import ensure_uv
from cli.utils.uv import uv_run
from cli.utils.uv import uv_sync
from cli.utils.venv import VenvStatus
from cli.utils.venv import ensure_venv
from cli.utils.venv import enter_venv
from cli.utils.venv import get_external_active_venv
from cli.utils.venv import validate_venv

if TYPE_CHECKING:
    from pathlib import Path

__all__ = [
    'CLEAN_PATTERN_GROUPS',
    'CleanCommand',
    'DevCommand',
    'DoctorCommand',
    'InstallCommand',
    'ShellCommand',
    'StatusCommand',
]


# `clean` command configuration
# -------------------------------------------------------------------
# Patterns for files/directories to remove during `run.py clean`
CLEAN_PATTERN_GROUPS: dict[str, list[str]] = {
    'package build artifacts': [
        'build',
        'dist',
        '*.egg-info',
    ],
    'package cache files': [
        '__pycache__',
        '**/__pycache__',
        '**/*.pyc',
    ],
    'tool cache files': [
        '.mypy_cache',
        '.pytest_cache',
        '.ruff_cache',
        '.tox',
        '.nox',
        '.coverage',
    ],
    'virtual environments': [
        'venv',
        '.venv',
    ],
}


# ==================================================================================================
# Setup & Environment commands
#
# Commands:
#   - install: Install dependencies into active/default environment
#   - dev:     Create .venv, install dependencies + hooks, and enter env in a subshell
#   - shell:   Enter .venv in a subshell
#   - status:  Show environment health status
#   - doctor:  Verify the environment (``--fix`` confirms each repair, then re-checks; ``--yes`` skips the prompts)
#   - clean:   Remove environments, build artifacts, caches, and temporary files
# ==================================================================================================


class InstallCommand(Command):
    """
    Install dependencies into active environment (or .venv if no active environment)
    """
    name:  ClassVar[str] = 'install'
    group: ClassVar[str] = 'Setup & Environment'

    class Args(argparse.Namespace):
        dev:   bool     # --dev
        hooks: bool     # --hooks/--no-hooks
        shell: bool     # --shell/--no-shell

    def add_arguments(
        self,
        parser: argparse.ArgumentParser,
        *,
        dev: bool = True,
        hooks: bool | None = True,
        shell: bool | None = True,
    ) -> None:
        if dev:
            parser.add_argument(
                '-d',
                '--dev',
                action='store_true',
                help='Install development dependencies',
            )

        if (hooks is not None) and hooks:
            parser.add_argument(
                '--hooks',
                action='store_true',
                help='Install pre-commit (prek) git hooks',
            )
        elif hooks is not None:
            parser.add_argument(
                '--no-hooks',
                dest='hooks',
                action='store_false',
                help='Skip pre-commit (prek) hook installation',
            )

        if (shell is not None) and shell:
            parser.add_argument(
                '--shell',
                '--env',
                dest='shell',
                action='store_true',
                help='Enter the environment in subshell after installation (if not already active)',
            )
        elif shell is not None:
            parser.add_argument(
                '--no-shell',
                '--no-env',
                dest='shell',
                action='store_false',
                help='Skip entering the environment in subshell after installation',
            )

    def run(self, args: Args) -> None:
        check_python()
        ensure_uv()

        if active_venv := os.environ.get('VIRTUAL_ENV'):
            printf(f'📦 Installing dependencies into active environment: {pathstyle(active_venv)}', fg='bright_cyan')
            uv_sync(
                active=True,
                inexact=True,
                no_dev=not getattr(args, 'dev', False),
                indent=3,
            )
            printf('')
        else:
            ensure_venv(
                inexact=True,
                no_dev=not getattr(args, 'dev', False),
            )

        if args.hooks:
            printf('💿 Installing pre-commit hooks...', fg='bright_cyan')
            uv_run(['prek', 'install', '-f'], active=active_venv is not None, indent=3)
            printf('')

        if args.shell:
            enter_venv()
            return

        printf(f'✅ Environment ready: {pathstyle(config.VENV_DIR)}', fg='bright_green')
        if not active_venv:
            printf(f'Enter environment with: {style("make shell", fg="bright_magenta")}', fg='bright_white', indent=3)


class DevCommand(InstallCommand):
    """
    Create .venv, install dependencies + hooks, and enter environment in a subshell
    """
    name:  ClassVar[str] = 'dev'
    group: ClassVar[str] = 'Setup & Environment'

    def add_arguments(self, parser: argparse.ArgumentParser, **kwargs: Any) -> None:
        super().add_arguments(parser, dev=False, hooks=False, shell=False, **kwargs)

    def run(self, args: InstallCommand.Args) -> None:
        check_python()
        ensure_uv()

        if active_venv := os.environ.get('VIRTUAL_ENV'):
            printf(f'📦 Installing dependencies into active environment: {pathstyle(active_venv)}', fg='bright_cyan')
            uv_sync(active=True, inexact=True, indent=3)
            printf('')
        else:
            ensure_venv(inexact=True)

        if args.hooks:
            printf('💿 Installing pre-commit hooks...', fg='bright_cyan')
            uv_run(['prek', 'install'], active=active_venv is not None, indent=3)
            printf('')

        if args.shell:
            enter_venv()
            return

        printf(f'✅ Environment ready: {pathstyle(config.VENV_DIR)}', fg='bright_green')
        if not active_venv:
            printf(f'Enter environment with: {style("make shell", fg="bright_magenta")}', fg='bright_white', indent=3)


class ShellCommand(Command):
    """
    Enter .venv in a subshell
    """
    name:  ClassVar[str] = 'shell'
    group: ClassVar[str] = 'Setup & Environment'

    def run(self, args: argparse.Namespace) -> None:
        check_python(quiet=True)
        ensure_uv(quiet=True)
        enter_venv()


class StatusCommand(Command):
    """
    Show environment health status
    """
    name:  ClassVar[str] = 'status'
    group: ClassVar[str] = 'Setup & Environment'

    OPTIONAL_TOOLS: ClassVar[list[tuple[str, str]]] = []

    def run(self, args: argparse.Namespace) -> None:
        printf(f'\n{style("dotfiles", fg="bright_blue")} environment status', fg='bright_white', bold=True)
        printf(style('─' * 80, dim=True))
        all_ok = True

        # Python
        python_info = check_python(quiet=True)
        status_line('python', python_info['version'], python_info['executable'], ok=True)

        # uv
        if uv_info := check_uv():
            status_line('uv', uv_info['version'], uv_info['executable'], ok=True)
        else:
            status_line('uv', 'not installed', ok=False)
            all_ok = False

        # Git hooks
        hooks = check_hooks()
        status_line('hooks', hooks.detail, ok=hooks.ok)
        all_ok &= hooks.ok

        # Optional tools
        for tool_name, note in self.OPTIONAL_TOOLS:
            if shutil.which(tool_name):
                status_line(tool_name, 'available',     ok=True,  optional=True)
            else:
                status_line(tool_name, 'not installed', ok=False, optional=True, note=note)

        # .venv (or external active venv if user manages their own)
        external_venv = get_external_active_venv()
        target_venv   = external_venv or config.VENV_DIR
        venv_label    = 'active venv' if external_venv else '.venv'
        venv_path     = external_venv or None

        health = validate_venv(target_venv)
        if health.status == VenvStatus.HEALTHY:
            venv_desc = f'Python {health.python_version or "?"}'
            if health.package_count is not None:
                venv_desc += f', {health.package_count} packages'
            if not health.stale:
                venv_desc += ', synced'
            status_line(venv_label, venv_desc, venv_path, ok=True)

        elif health.status == VenvStatus.MISSING:
            if external_venv:
                # `VIRTUAL_ENV` pointed at a path that disappeared between resolve() and validate()
                status_line(venv_label, 'active venv vanished',           venv_path, ok=False)
            else:
                status_line(venv_label, 'not created (run `make install`)',          ok=False)
            all_ok = False

        elif health.status == VenvStatus.NOT_ACTIVATED:
            # An external venv is, by definition, the activated one — only the project's `.venv` can land here when
            # the shell is running outside it
            venv_desc = f'Python {health.python_version or "?"}'
            if health.package_count is not None:
                venv_desc += f', {health.package_count} packages'
            venv_desc += ', not activated (run `make shell`)'
            status_line(venv_label, venv_desc, venv_path,      ok=False, warn=True)

        elif health.status == VenvStatus.STALE_DEPS:
            status_line(venv_label, health.message, venv_path, ok=False, warn=True)

        else:
            status_line(venv_label, health.message, venv_path, ok=False)
            all_ok = False

        # Summary
        printf(style('─' * 80, dim=True))
        if all_ok:
            printf('Environment ready.', fg='bright_green')
        else:
            printf(
                f'Environment has issues. To fix, run {style("make install", fg="bright_magenta")}',
                fg='bright_yellow',
            )


# TODO: cleanup formatting
class DoctorCommand(Command):
    """
    Check tools, python/uv/venv, overlays, git version and hooks, links, rendered settings, and Brewfiles
    """
    name:  ClassVar[str] = 'doctor'
    group: ClassVar[str] = 'Setup & Environment'

    class Args(argparse.Namespace):
        fix: bool       # --fix
        yes: bool       # --yes

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            '-f',
            '--fix',
            action='store_true',
            help=(
                'Ask before fixing each failing check, then re-check. The fixes are:\n'
                '  hooks:    prek install\n'
                '  links:    stow.sh --backup-conflicts (moves blocking files into\n'
                '            ~/.dotfiles-backup/<timestamp>/)\n'
                '  render:   render.py (without --force)\n'
                '  brewfile: brew bundle --no-upgrade --file for each unsatisfied Brewfile'
            ),
        )
        parser.add_argument(
            '-y',
            '--yes',
            action='store_true',
            help='Apply fixes without prompting for confirmation (implies --fix)',
        )

    def run(self, args: Args) -> None:
        checks = doctor_checks()

        if args.fix or args.yes:
            for check in checks:
                if check.ok or not check.fix:
                    continue

                command  = shlex.join(check.fix)
                question = f'Run {style(command, fg="bright_magenta")} to fix {style(check.name, bold=True)}?'
                if not args.yes and not confirm(question, indent=3):
                    printf(f'Skipped {check.name}', dim=True, indent=3)
                    continue

                printf(f'🔧 {check.name}: {command}', fg='bright_cyan')
                shell_command(check.fix, indent=3, check=False, cwd=config.DOTFILES_DIR)

            checks = doctor_checks()

        for check in checks:
            emoji = '🟢' if check.ok else '🔴'
            printf(f'{emoji} {style(check.name, fg="white", bold=True)}  {check.detail}', indent=3)

        if not all(check.ok for check in checks):
            sys.exit(ExitCode.COMMAND_FAILED)


class CleanCommand(Command):
    """
    Remove all environments, build artifacts, caches, and temporary files
    """
    name:  ClassVar[str] = 'clean'
    group: ClassVar[str] = 'Setup & Environment'

    class Args(argparse.Namespace):
        envs: bool      # --no-envs

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            '--no-envs',
            '--no-env',
            dest='envs',
            action='store_false',
            help='Skip removal of project virtual environment',
        )

    def run(self, args: Args) -> None:
        printf('🧹 Cleaning project workspace...', fg='bright_cyan')

        cleaned = 0
        for group, patterns in CLEAN_PATTERN_GROUPS.items():
            if (group == 'virtual environments') and not args.envs:
                continue
            printf(f'Cleaning {style(group, fg="bright_white")}...', indent=3)

            for pattern in patterns:
                for path in config.DOTFILES_DIR.glob(pattern):
                    path     = cast('Path', path)
                    rel_path = path.relative_to(config.DOTFILES_DIR)

                    if path.is_dir():
                        dir_files = list(path.glob('**/*'))
                        printf(
                            style(f'Removing {rel_path}', dim=True, fg='bright_yellow') +
                            style(f' ({len(dir_files)} files)', dim=True),
                            debug=True,
                            indent=5,
                        )
                        for p in dir_files:
                            printf(str(p.relative_to(config.DOTFILES_DIR)), debug=True, indent=7)
                        shutil.rmtree(path)
                        cleaned += len(dir_files)

                    elif path.is_file():
                        printf(f'Removing {rel_path}', debug=True, fg='bright_white', indent=5)
                        path.unlink()
                        cleaned += 1

        printf('✅ Cleanup complete',                                  fg='bright_green')
        printf(f'{cleaned} file{"s" if cleaned != 1 else ""} removed', fg='bright_white', dim=True, indent=3)
