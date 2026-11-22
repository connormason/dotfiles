"""
Dotfiles commands (stow, render, track-claude)
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from typing import TYPE_CHECKING
from typing import ClassVar

from cli.infra.command import Command
from cli.infra.config import CLAUDE_STOW_DIR
from cli.infra.config import RENDER_SCRIPT
from cli.infra.config import STOW_SCRIPT
from cli.infra.config import ExitCode
from cli.utils.claude import CLAUDE_CONFIG_DIR
from cli.utils.claude import find_untracked_claude_files
from cli.utils.formatting import folduser
from cli.utils.prompts import confirm
from cli.utils.shell import capture_command
from cli.utils.shell import shell_command
from cli.utils.styling import printf
from cli.utils.styling import style
from cli.utils.styling import unstyle

if TYPE_CHECKING:
    from pathlib import Path

__all__ = [
    'TRACK_CLAUDE_PREFLIGHT_LINES',
    'RenderCommand',
    'StowCommand',
    'TrackClaudeCommand',
]


# Lines of a failed `stow.sh -n claude` shown by the track-claude preflight
TRACK_CLAUDE_PREFLIGHT_LINES: int = 8


# ==================================================================================================
# Dotfiles commands
#
# Thin wrappers over the layered engine (stow.sh, bootstrap/bootstrap.sh, scripts/dotfiles/render.py)
#   - stow:         Link stow packages from every layer into $HOME
#   - render:       Render settings files from per-layer fragments
#   - track-claude: Ingest local ~/.claude agents/commands/skills/hooks/rules into the ``claude`` stow package
# ==================================================================================================


class StowCommand(Command):
    """
    Link stow packages from every layer into the home directory (stow.sh)
    """
    name:  ClassVar[str] = 'stow'
    group: ClassVar[str] = 'Dotfiles'

    class Args(argparse.Namespace):
        packages:         list[str]     # positional arg(s) "PACKAGES"
        simulate:         bool          # --simulate
        backup_conflicts: bool          # --backup-conflicts
        verbose:          bool          # --verbose

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            'packages',
            nargs='*',
            help='Packages to stow (default: all, across layers)',
        )
        parser.add_argument(
            '-n',
            '--simulate',
            action='store_true',
            help='Preview without changing $HOME',
        )
        parser.add_argument(
            '--backup-conflicts',
            action='store_true',
            help='Move blocking files to ~/.dotfiles-backup',
        )
        parser.add_argument(
            '-v',
            '--verbose',
            action='store_true',
            help='Show the raw stow log',
        )

    def run(self, args: Args) -> None:
        cmd: list[str] = ['bash', str(STOW_SCRIPT)]
        if args.simulate:
            cmd.append('-n')
        if args.backup_conflicts:
            cmd.append('--backup-conflicts')
        if args.verbose:
            cmd.append('--verbose')

        result = shell_command([*cmd, *args.packages], check=False)
        sys.exit(result.returncode)


class RenderCommand(Command):
    """
    Render settings files from per-layer fragments (scripts/dotfiles/render.py)
    """
    name:  ClassVar[str] = 'render'
    group: ClassVar[str] = 'Dotfiles'

    class Args(argparse.Namespace):
        targets: list[str]      # positional arg(s) "TARGETS"
        diff:    bool           # --diff
        check:   bool           # --check
        force:   bool           # --force
        verbose: bool           # --verbose

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            'targets',
            nargs='*',
            help='Targets (default: all)',
        )
        parser.add_argument(
            '--diff',
            action='store_true',
            help='Preview differences; write nothing',
        )
        parser.add_argument(
            '--check',
            action='store_true',
            help='Exit 1 if out of sync; write nothing',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Overwrite in-app edits after backing them up',
        )
        parser.add_argument(
            '-v',
            '--verbose',
            action='store_true',
            help='Report skipped/current targets',
        )

    def run(self, args: Args) -> None:
        cmd: list[str] = [sys.executable, str(RENDER_SCRIPT), *args.targets]
        for flag, enabled in (
            ('--diff',  args.diff),
            ('--check', args.check),
            ('--force', args.force),
            ('-v',      args.verbose),
        ):
            if enabled:
                cmd.append(flag)

        result = shell_command(cmd, check=False)
        sys.exit(result.returncode)


class TrackClaudeCommand(Command):
    """
    Ingest new ~/.claude agents, commands, skills, hooks, and rules into the repo
    """
    name:  ClassVar[str] = 'track-claude'
    group: ClassVar[str] = 'Dotfiles'

    class Args(argparse.Namespace):
        dry_run: bool       # --dry-run

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            '-n',
            '--dry-run',
            action='store_true',
            help='Preview what would be ingested without moving anything',
        )

    @staticmethod
    def _preflight_restow() -> list[str] | None:
        """
        Simulate the restow that follows the moves, so a failure surfaces before any file is moved

        :return: ``None`` when stow would succeed, otherwise the first few lines of its output
        """
        result = capture_command(['bash', str(STOW_SCRIPT), '-n', 'claude'])
        if result.returncode == 0:
            return None

        lines = [line.strip() for line in unstyle(f'{result.stderr}\n{result.stdout}').splitlines() if line.strip()]
        return lines[:TRACK_CLAUDE_PREFLIGHT_LINES] or ['stow simulation failed']

    @staticmethod
    def _report_preflight_failure(stow_output: list[str], *, dry_run: bool) -> None:
        """
        Print why the restow would fail: a warning for a dry run, an error stating nothing was moved otherwise

        :param stow_output: leading lines of the failed stow simulation
        :param dry_run: whether the run only previews (the caller continues instead of exiting)
        """
        printf('')
        if dry_run:
            printf(
                '🟡 The claude restow would fail right now; a real run would stop before moving anything:',
                fg='yellow',
            )
        else:
            printf(
                '❌ The claude restow would fail, so nothing was moved (~/.claude is unchanged):',
                fg='red',
                bold=True,
            )

        for line in stow_output:
            printf(line, dim=True, indent=3)

        if not dry_run:
            printf(
                f'Fix what stow reported, then re-run {style("python3 run.py track-claude", fg="bright_magenta")}',
                indent=3,
            )

    @staticmethod
    def _report_partial_move(moved_rels: list[Path], total: int) -> None:
        """
        Print which files already left ``~/.claude`` when the move loop was cut short, and how to recover

        :param moved_rels: ``~/.claude``-relative paths already moved into the repo
        :param total: number of files the run planned to move
        """
        printf('')
        if not moved_rels:
            printf('❌ Move aborted before any file was moved', fg='red', bold=True)
            return

        printf(
            f'❌ Move aborted: {len(moved_rels)} of {total} file(s) already moved into the repo '
            f'and absent from ~/.claude:',
            fg='red',
            bold=True,
        )
        for rel in moved_rels:
            printf(f'└─ {rel}', indent=3)

        printf(
            f'Recover: run {style("python3 run.py stow claude", fg="bright_magenta")} to link them back, then review '
            f'and commit ({style("git add stow/claude/.claude && git commit", fg="bright_magenta")})',
            indent=3,
        )

    def run(self, args: Args) -> None:
        untracked = find_untracked_claude_files()
        if not untracked:
            printf('✅ Nothing to track: everything under ~/.claude is already in the repo', fg='bright_green')
            return

        printf(
            f'Found {len(untracked)} untracked file(s) under {folduser(CLAUDE_CONFIG_DIR)}:',
            bold=True,
            fg='bright_white',
        )

        # Plan moves: src (real file in ~/.claude) -> dst (mirrored path in the stow package). Any existing directory
        # entry at dst (even a dangling symlink, which exists() reports as absent) is a conflict: the repo has
        # something there and it is left untouched.
        moves:     list[tuple[Path, Path]] = []
        conflicts: list[Path]              = []
        for src in untracked:
            rel = src.relative_to(CLAUDE_CONFIG_DIR)
            dst = CLAUDE_STOW_DIR / rel
            if os.path.lexists(dst):
                conflicts.append(rel)
                printf(f'{style("CONFLICT", fg="red")}  {rel}', indent=2)
            else:
                moves.append((src, dst))
                printf(f'{style("→ repo", fg="green")}  {rel}', indent=2)

        if conflicts:
            printf('')
            printf(f'🟡 {len(conflicts)} file(s) already exist in the repo; skipped (resolve manually)', fg='yellow')
            if moves:
                printf('Restow will be skipped: the conflicting local files would block stow', fg='yellow', indent=3)

        if not moves:
            printf('')
            printf('Nothing to move.', fg='yellow')
            return

        # stow.sh aborts without changing anything if a regular file blocks a link, so any conflict rules out the restow
        scope = f'{len(moves)} file(s) into the repo' + ('' if conflicts else ' and restow')

        # A restow follows the moves unless a conflict rules it out. Prove it can succeed before touching any file:
        # files moved into the repo that then cannot be linked back would simply vanish from ~/.claude
        preflight_failure = None if conflicts else self._preflight_restow()
        if preflight_failure is not None:
            self._report_preflight_failure(preflight_failure, dry_run=args.dry_run)
            if not args.dry_run:
                sys.exit(ExitCode.COMMAND_FAILED)

        if args.dry_run:
            printf('')
            printf(f'Dry run: would move {scope}. No changes made.', fg='cyan')
            return

        printf('')
        if not confirm(f'Move {scope}?'):
            printf('⚠️  Cancelled', fg='yellow')
            return

        moved_rels: list[Path] = []
        try:
            for src, dst in moves:
                rel = src.relative_to(CLAUDE_CONFIG_DIR)

                # Re-check right before moving: shutil.move silently replaces an existing destination (rename
                # semantics), and the repo may have changed since planning
                if os.path.lexists(dst):
                    conflicts.append(rel)
                    printf(f'{style("CONFLICT", fg="red")}  {rel}', indent=2)
                    continue

                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))
                moved_rels.append(rel)
                printf(f'└─ {rel}', fg='green')
        except (OSError, KeyboardInterrupt):
            self._report_partial_move(moved_rels, len(moves))
            raise

        moved = len(moved_rels)
        if conflicts:
            printf('')
            printf(
                f'🟡 Moved {moved} file(s) into the repo; restow skipped: {len(conflicts)} conflicting local file(s) '
                f'would block stow',
                fg='yellow',
                bold=True,
            )
            if moved:
                printf(
                    f'The {moved} moved file(s) are absent from ~/.claude until the restow succeeds',
                    fg='yellow',
                    indent=3,
                )
            printf('Next steps:', fg='bright_white', bold=True)
            printf('1. Resolve the conflicts above (diff/merge, or delete the local copies)', indent=3)
            printf(
                f'2. Run {style("python3 run.py stow claude", fg="bright_magenta")} '
                f'(add {style("--backup-conflicts", fg="yellow")} to move the blocking local files to '
                f'~/.dotfiles-backup/<timestamp>/ instead)',
                indent=3,
            )
            printf(
                f'3. Review and commit: {style("git add stow/claude/.claude && git commit", fg="bright_magenta")}',
                indent=3,
            )
            return

        # The source paths are vacant now, so a plain restow links the moved files back in without conflicts
        printf('')
        printf('🔗 Restowing claude package...', fg='bright_cyan')
        try:
            shell_command(['bash', str(STOW_SCRIPT), 'claude'], indent=3)
        except subprocess.CalledProcessError:
            printf(
                f'❌ Restow failed: {moved} file(s) are now in the repo but NOT linked back into ~/.claude '
                f'(stow.sh is all-or-nothing, so none were linked)',
                fg='red',
                bold=True,
            )
            printf(
                f'Fix what stow reported above, then re-run {style("python3 run.py stow claude", fg="bright_magenta")}',
                indent=3,
            )
            sys.exit(ExitCode.COMMAND_FAILED)

        printf('')
        printf(f'✅ Ingested {moved} file(s). Review and commit them:', fg='bright_green', bold=True)
        printf(style('git add stow/claude/.claude && git commit', fg='bright_magenta'), indent=3)
