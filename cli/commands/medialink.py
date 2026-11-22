"""
Medialink passthrough command (medialink)
"""
from __future__ import annotations

import argparse
import shlex
import sys
from typing import ClassVar

from cli.infra.command import Command
from cli.utils.nas import resolve_reachable_nas
from cli.utils.shell import shell_command
from cli.utils.styling import printf
from cli.utils.styling import style

__all__ = [
    'MEDIALINK_CONTAINER',
    'MedialinkCommand',
    'build_medialink_command',
]


MEDIALINK_CONTAINER: str = 'medialink'


def build_medialink_command(user: str, host: str, medialink_args: list[str], *, tty: bool) -> list[str]:
    """
    Build the ``ssh`` command that runs ``python -m medialink`` inside the NAS container

    ssh joins its trailing arguments into one string for the remote shell, so the remote command is quoted with
    :func:`shlex.join` to deliver each medialink argument intact.

    :param user: SSH user on the NAS
    :param host: SSH host of the NAS
    :param medialink_args: arguments for ``python -m medialink`` (e.g. ``['once', '--dry-run']``)
    :param tty: allocate a pseudo-terminal, so Ctrl-C reaches the process inside the container
    :return: ssh argv
    """
    remote = shlex.join([
        'docker', 'exec',
        *(['-t'] if tty else []),
        MEDIALINK_CONTAINER, 'python', '-m', 'medialink',
        *medialink_args,
    ])
    return ['ssh', *(['-t'] if tty else []), '--', f'{user}@{host}', remote]


# ==================================================================================================
# Medialink command
#
#   - medialink: run a medialink command (run / once / dedupe) in the container on the NAS
#     - Everything after `medialink` is forwarded unchanged, so `medialink once --dry-run` is
#       `docker exec medialink python -m medialink once --dry-run` run over SSH
#     - The process exit status is medialink's own (0 ok, 1 problems, 2 Transmission unreachable, 3 bad config)
# ==================================================================================================


class MedialinkCommand(Command):
    """
    Run a medialink command in the NAS container (e.g. 'medialink once --dry-run', 'medialink dedupe --apply')
    """
    name:        ClassVar[str] = 'medialink'
    group:       ClassVar[str] = 'Utilities'
    script_only: ClassVar[bool] = True
    epilog:      ClassVar[str] = (
        f'Arguments after {style("medialink", fg="yellow")} go to medialink untouched; ask it for its own help with\n'
        f'{style("run.py medialink once --help", fg="bright_magenta")} (a bare --help is answered by run.py).\n'
        f'To give medialink an option before its command, put -- first: '
        f'{style("run.py medialink -- --verbose once", fg="bright_magenta")}'
    )

    class Args(argparse.Namespace):
        medialink_args: list[str]       # ARGS

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            'medialink_args',
            nargs=argparse.REMAINDER,
            metavar='ARGS',
            help='Command and options to run: run, once [-n], dedupe [--apply] [--quick]',
        )

    def run(self, args: Args) -> None:
        medialink_args = args.medialink_args
        if medialink_args[:1] == ['--']:
            medialink_args = medialink_args[1:]

        host, user = resolve_reachable_nas()
        cmd = build_medialink_command(user, host, medialink_args, tty=sys.stdin.isatty() and sys.stdout.isatty())
        printf(f'Running in the {style(MEDIALINK_CONTAINER, fg="bright_magenta")} container on {host}', dim=True)

        result = shell_command(cmd, check=False)
        sys.exit(result.returncode)
