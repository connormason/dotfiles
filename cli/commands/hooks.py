"""
Git hook commands (install, prepare, uninstall, run prek hooks)
"""
from __future__ import annotations

import argparse
import sys
from typing import ClassVar
from typing import cast

from cli.infra.command import Command
from cli.utils.python import check_python
from cli.utils.styling import printf
from cli.utils.uv import ensure_uv
from cli.utils.uv import uv_run
from cli.utils.venv import ensure_venv

__all__ = [
    'InstallHooksCommand',
    'PreCommand',
    'PrepareHooksCommand',
    'RunHooksCommand',
    'UninstallHooksCommand',
]


# ==================================================================================================
# Hooks commands
#
# Commands:
#   - install-hooks:   Install prek git hook shims
#   - prepare-hooks:   Prepare the environments of all prek hooks
#   - uninstall-hooks: Uninstall prek git hook shims
#   - run-hooks:       Run prek hooks on modified or specified project files
#   - pre:             Run prek pre-commit hooks on all files
# ==================================================================================================


class InstallHooksCommand(Command):
    """
    Install prek git hook shims
    """
    name:  ClassVar[str] = 'install-hooks'
    group: ClassVar[str] = 'Hooks'

    class Args(argparse.Namespace):
        overwrite:     bool                 # --overwrite
        hook_type:     list[str] | None     # --hook-type
        prepare_hooks: bool                 # --prepare-hooks
        verbose:       bool                 # --verbose

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            '-f',
            '--overwrite',
            action='store_true',
            help='Overwrite existing git shims',
        )
        parser.add_argument(
            '-t',
            '--hook-type',
            action='append',
            metavar='TYPE',
            help='Which git shim(s) to install (may be repeated)',
        )
        parser.add_argument(
            '--prepare-hooks',
            action='store_true',
            help='Also prepare environments for all hooks after installing',
        )
        parser.add_argument(
            '-v',
            '--verbose',
            action='store_true',
            help='Output verbose logging from prek',
        )

    def run(self, args: Args) -> None:
        check_python()
        ensure_uv()
        ensure_venv(groups=['lint'], inexact=True)

        cmd: list[str] = ['prek', 'install']
        if args.overwrite:
            cmd.append('--overwrite')
        if args.prepare_hooks:
            cmd.append('--prepare-hooks')
        for hook_type in (args.hook_type or []):
            cmd.extend(['--hook-type', hook_type])
        if args.verbose:
            cmd.append('--verbose')

        printf('🪝 Installing prek git hook shims...', fg='bright_cyan')
        result = uv_run(cmd, indent=3, check=False)
        sys.exit(result.returncode)


class PrepareHooksCommand(Command):
    """
    Prepare the environments of all prek hooks
    """
    name:  ClassVar[str] = 'prepare-hooks'
    group: ClassVar[str] = 'Hooks'

    class Args(argparse.Namespace):
        hooks:   list[str] | None       # positional arg(s) "HOOK|PROJECT"
        skip:    list[str] | None       # --skip
        verbose: bool                   # --verbose

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            'hooks',
            nargs='*',
            default=None,
            metavar='HOOK|PROJECT',
            help='Hooks or projects to prepare (default: all)',
        )
        parser.add_argument(
            '--skip',
            action='append',
            metavar='HOOK|PROJECT',
            help='Skip this hook or project (repeatable)',
        )
        parser.add_argument(
            '-v',
            '--verbose',
            action='store_true',
            help='Show verbose prek output',
        )

    def run(self, args: Args) -> None:
        check_python()
        ensure_uv()
        ensure_venv(groups=['lint'], inexact=True)

        cmd: list[str] = ['prek', 'prepare-hooks', *(args.hooks or [])]
        for skip in (args.skip or []):
            cmd.extend(['--skip', skip])
        if args.verbose:
            cmd.append('--verbose')

        printf('⏬ Preparing prek hook environments...', fg='bright_cyan')
        result = uv_run(cmd, indent=3, check=False)
        sys.exit(result.returncode)


class UninstallHooksCommand(Command):
    """
    Uninstall prek git hook shims
    """
    name:  ClassVar[str] = 'uninstall-hooks'
    group: ClassVar[str] = 'Hooks'

    class Args(argparse.Namespace):
        all:       bool                 # --all
        hook_type: list[str] | None     # --hook-type
        verbose:   bool                 # --verbose

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            '-a',
            '--all',
            action='store_true',
            dest='all',
            help='Uninstall all prek-managed Git shims',
        )
        parser.add_argument(
            '-t',
            '--hook-type',
            action='append',
            metavar='TYPE',
            help='Which Git shim(s) to uninstall (may be repeated)',
        )
        parser.add_argument(
            '-v',
            '--verbose',
            action='store_true',
            help='Output verbose logging from prek',
        )

    def run(self, args: Args) -> None:
        check_python()
        ensure_uv()
        ensure_venv(groups=['lint'], inexact=True)

        cmd: list[str] = ['prek', 'uninstall']
        if args.all:
            cmd.append('--all')
        for hook_type in (args.hook_type or []):
            cmd.extend(['--hook-type', hook_type])
        if args.verbose:
            cmd.append('--verbose')

        printf('🧹 Uninstalling prek git hook shims...', fg='bright_cyan')
        result = uv_run(cmd, indent=3, check=False)
        sys.exit(result.returncode)


class RunHooksCommand(Command):
    """
    Run prek hooks on modified or specified project files
    """
    name:  ClassVar[str] = 'run-hooks'
    group: ClassVar[str] = 'Hooks'

    class Args(argparse.Namespace):
        hooks:       list[str] | None   # positional arg(s) "HOOK|PROJECT"
        all_files:   bool               # --all-files
        files:       list[str] | None   # --files
        directory:   str | None         # --directory
        from_ref:    str | None         # --from-ref
        to_ref:      str | None         # --to-ref
        last_commit: bool               # --last-commit
        skip:        list[str] | None   # --skip
        stage:       str | None         # --stage
        show_diff:   bool               # --show-diff-on-failure
        fail_fast:   bool               # --fail-fast
        dry_run:     bool               # --dry-run
        verbose:     bool               # --verbose

    def add_arguments(self, parser: argparse.ArgumentParser, *, include_selection: bool = True) -> None:
        def add_positional_args() -> None:
            parser.add_argument(
                'hooks',
                nargs='*',
                default=None,
                metavar='HOOK|PROJECT',
                help='Hooks or projects to run (default: all)',
            )
        add_positional_args()

        def add_file_opts() -> None:
            file_opts = parser.add_argument_group('File selection')
            file_opts.add_argument(
                '-a',
                '--all-files',
                action='store_true',
                help='Run on all files in the repo',
            )
            file_opts.add_argument(
                '--files',
                nargs='*',
                metavar='FILE',
                help='Run on these files (put hook names before this option)',
            )
            file_opts.add_argument(
                '-d',
                '--directory',
                metavar='DIR',
                help='Run on all files in this directory',
            )
        if include_selection:
            add_file_opts()

        def add_ref_opts() -> None:
            ref_opts = parser.add_argument_group('Ref selection')
            ref_opts.add_argument(
                '-s',
                '--from-ref',
                metavar='REF',
                help='Original ref in a from_ref...to_ref diff expression',
            )
            ref_opts.add_argument(
                '-o',
                '--to-ref',
                metavar='REF',
                help='Destination ref in a from_ref...to_ref diff expression (default: HEAD)',
            )
            ref_opts.add_argument(
                '--last-commit',
                action='store_true',
                help='Run on the files of the last commit (--from-ref HEAD~1 --to-ref HEAD)',
            )
        if include_selection:
            add_ref_opts()

        def add_run_opts() -> None:
            run_opts = parser.add_argument_group('Run options')
            run_opts.add_argument(
                '--skip',
                action='append',
                metavar='HOOK|PROJECT',
                help='Skip this hook or project (repeatable)',
            )
            run_opts.add_argument(
                '--stage',
                metavar='STAGE',
                help='The git stage the hooks run for (e.g. pre-push, manual)',
            )
            run_opts.add_argument(
                '--show-diff-on-failure',
                action='store_true',
                dest='show_diff',
                help='Run `git diff` after a hook fails',
            )
            run_opts.add_argument(
                '--fail-fast',
                action='store_true',
                help='Stop after the first failing hook',
            )
            run_opts.add_argument(
                '--dry-run',
                action='store_true',
                help='List the hooks that would run without running them',
            )
            run_opts.add_argument(
                '-v',
                '--verbose',
                action='store_true',
                help='Show verbose prek output',
            )
        add_run_opts()

    @staticmethod
    def build_command(args: Args) -> list[str]:
        """
        Build the ``prek run`` command line

        Hook names go first: prek's ``--files`` is greedy, so a trailing hook name would be read as a filename.

        :param args: parsed arguments (the file and ref selection attributes are absent for commands that omit those
                     options)
        :return: command and arguments
        """
        cmd: list[str] = ['prek', 'run', *(args.hooks or [])]

        # File selection
        if getattr(args, 'all_files', False):
            cmd.append('--all-files')
        if files := getattr(args, 'files', None):
            cmd.extend(['--files', *files])
        if directory := getattr(args, 'directory', None):
            cmd.extend(['--directory', cast('str', directory)])

        # Ref selection
        if from_ref := getattr(args, 'from_ref', None):
            cmd.extend(['--from-ref', cast('str', from_ref)])
        if to_ref := getattr(args, 'to_ref', None):
            cmd.extend(['--to-ref', cast('str', to_ref)])
        if getattr(args, 'last_commit', False):
            cmd.append('--last-commit')

        # Ruyn options
        for skip in (args.skip or []):
            cmd.extend(['--skip', skip])
        if args.stage:
            cmd.extend(['--stage', args.stage])
        if args.show_diff:
            cmd.append('--show-diff-on-failure')
        if args.fail_fast:
            cmd.append('--fail-fast')
        if args.dry_run:
            cmd.append('--dry-run')
        if args.verbose:
            cmd.append('--verbose')
        return cmd

    def run(self, args: Args) -> None:
        check_python()
        ensure_uv()
        ensure_venv(groups=['lint'], inexact=True)

        cmd = self.build_command(args)

        if getattr(args, 'all_files', False):
            printf('🕝 Running prek hooks on all project files...',     fg='bright_cyan')
        elif files := getattr(args, 'files', None):
            files = cast('list[str]', files)
            printf(f'🕝 Running prek hooks on {len(files)} file(s)...', fg='bright_cyan')
        else:
            printf('🕝 Running prek hooks...',                          fg='bright_cyan')

        result = uv_run(cmd, check=False)
        sys.exit(result.returncode)


class PreCommand(RunHooksCommand):
    """
    Run prek (pre-commit) hooks on all project files
    """
    name: ClassVar[str] = 'pre'

    def add_arguments(self, parser: argparse.ArgumentParser, **_kwargs: object) -> None:
        super().add_arguments(parser, include_selection=False)

    def run(self, args: RunHooksCommand.Args) -> None:
        args.all_files = True
        super().run(args)
