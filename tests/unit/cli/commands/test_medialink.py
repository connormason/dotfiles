"""
Unit tests for the run.py ``medialink`` passthrough command and the ``medialink`` console-script entry point
"""
from __future__ import annotations

import importlib
import subprocess
from typing import TYPE_CHECKING

import pytest
import tomllib

import cli.commands  # noqa: F401  (importing registers every command)
from cli.commands import medialink as medialink_commands
from cli.commands.medialink import MEDIALINK_CONTAINER
from cli.commands.medialink import build_medialink_command
from cli.infra.command import get_commands
from cli.infra.config import DOTFILES_DIR
from cli.infra.main import Args
from cli.infra.main import build_parser

if TYPE_CHECKING:
    import argparse

Call = tuple[list[str], dict[str, object]]


# ==================================================================================================
# Helpers
# ==================================================================================================


def _parse(*argv: str) -> argparse.Namespace:
    """
    Parse a run.py command line into the typed root namespace
    """
    return build_parser().parse_args(list(argv), namespace=Args())


# ==================================================================================================
# Unit tests
# ==================================================================================================


class TestBuildMedialinkCommand:
    """
    Tests for build_medialink_command
    """
    def test_runs_the_module_inside_the_container(self) -> None:
        """
        Test that the remote command is docker exec of python -m medialink with the arguments appended
        """
        assert build_medialink_command('tester', 'nas.example', ['once', '--dry-run'], tty=False) == [
            'ssh',
            '--',
            'tester@nas.example',
            f'docker exec {MEDIALINK_CONTAINER} python -m medialink once --dry-run',
        ]

    def test_tty_allocates_a_terminal_on_both_hops(self) -> None:
        """
        Test that tty=True adds -t to ssh and to docker exec, so Ctrl-C reaches the process in the container
        """
        cmd = build_medialink_command('tester', 'nas.example', ['dedupe'], tty=True)

        assert cmd[:2] == ['ssh', '-t']
        assert cmd[-1] == f'docker exec -t {MEDIALINK_CONTAINER} python -m medialink dedupe'

    def test_arguments_survive_the_remote_shell(self) -> None:
        """
        Test that arguments with spaces or shell metacharacters reach medialink as single, literal arguments
        """
        cmd = build_medialink_command('tester', 'nas.example', ['once', 'a b', '$(reboot)', ';ls'], tty=False)
        assert cmd[-1].endswith("python -m medialink once 'a b' '$(reboot)' ';ls'")

    def test_destination_cannot_be_read_as_an_option(self) -> None:
        """
        Test that -- precedes the destination, so a host or user starting with '-' is not parsed by ssh as an option
        """
        cmd = build_medialink_command('tester', '-oProxyCommand=x', [], tty=False)
        assert cmd.index('--') < cmd.index('tester@-oProxyCommand=x')


class TestMedialinkCommand:
    """
    Tests for the medialink command
    """
    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Fake the NAS lookup and record ssh launches instead of running them
        """
        self.calls:      list[Call] = []
        self.returncode: int        = 0

        def fake_shell_command(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            self.calls.append((cmd, kwargs))
            return subprocess.CompletedProcess(cmd, self.returncode, stdout='', stderr='')

        monkeypatch.setattr(medialink_commands, 'resolve_reachable_nas', lambda: ('nas.example', 'tester'))
        monkeypatch.setattr(medialink_commands, 'shell_command',         fake_shell_command)

    def _run(self, *argv: str) -> int:
        """
        Run a command and return its exit code (0 when it returns normally)
        """
        try:
            get_commands()[argv[0]](_parse(*argv))
        except SystemExit as e:
            return int(e.code or 0)
        return 0

    def test_is_registered_script_only_in_utilities_group(self) -> None:
        """
        Test that the command is a Utilities command left out of the Makefile, whose targets cannot take arguments
        """
        command = get_commands()['medialink']

        assert command.group       == 'Utilities'
        assert command.script_only is True

    def test_forwards_arguments_unchanged(self) -> None:
        """
        Test that everything after the command name, options included, is handed to medialink in order
        """
        assert self._run('medialink', 'dedupe', '--apply', '--quick', '-v') == 0

        [(cmd, kwargs)] = self.calls
        assert cmd[-1] == f'docker exec {MEDIALINK_CONTAINER} python -m medialink dedupe --apply --quick -v'
        assert kwargs  == {'check': False}

    def test_double_dash_lets_medialink_options_lead(self) -> None:
        """
        Test that a leading -- is consumed by run.py, so medialink can be given an option before its command
        """
        self._run('medialink', '--', '--verbose', 'once')
        assert self.calls[0][0][-1].endswith('python -m medialink --verbose once')

    def test_help_after_a_command_reaches_medialink(self) -> None:
        """
        Test that --help following a medialink command is forwarded, not answered by run.py
        """
        self._run('medialink', 'once', '--help')
        assert self.calls[0][0][-1].endswith('python -m medialink once --help')

    def test_targets_the_resolved_nas(self) -> None:
        """
        Test that ssh connects to user@host from the inventory lookup
        """
        self._run('medialink', 'once')
        assert 'tester@nas.example' in self.calls[0][0]

    @pytest.mark.parametrize('returncode', [0, 1, 2, 3, 255])
    def test_exit_status_is_the_remote_status(self, returncode: int) -> None:
        """
        Test that medialink's exit status (or ssh's 255) becomes the command's exit status
        """
        self.returncode = returncode
        assert self._run('medialink', 'once') == returncode


class TestMedialinkEntryPoint:
    """
    Tests for the medialink console script declared in pyproject.toml
    """
    def test_script_targets_the_service_main(self) -> None:
        """
        Test that [project.scripts] medialink resolves to the service's main()
        """
        with (DOTFILES_DIR / 'pyproject.toml').open('rb') as f:
            pyproject = tomllib.load(f)

        module_name, _, attr = pyproject['project']['scripts']['medialink'].partition(':')
        main = getattr(importlib.import_module(module_name), attr)

        assert callable(main)
        assert module_name == 'medialink.cli'

    def test_build_backend_serves_the_service_directory(self) -> None:
        """
        Test that the build backend packages the medialink package from services/medialink, where the sources live
        """
        with (DOTFILES_DIR / 'pyproject.toml').open('rb') as f:
            pyproject = tomllib.load(f)

        backend = pyproject['tool']['uv']['build-backend']
        assert (DOTFILES_DIR / backend['module-root'] / backend['module-name'] / '__init__.py').is_file()
