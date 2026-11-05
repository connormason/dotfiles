"""
Unit tests for run.py command registration, parser construction, and dispatch
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import types
from pathlib import Path
from typing import ClassVar

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import run


@pytest.fixture
def registry(monkeypatch: pytest.MonkeyPatch) -> dict[str, run.Command]:
    """
    Swap in an empty command registry so test-defined commands never leak into the real one
    """
    isolated: dict[str, run.Command] = {}
    monkeypatch.setattr(run, 'REGISTERED_COMMANDS', isolated)
    return isolated


def _make_command(cls_name: str, *, register: bool = True, **attrs: object) -> type[run.Command]:
    """
    Define (and, by default, register) a no-op Command subclass with the given class attributes
    """
    namespace: dict[str, object] = {'run': lambda self, args: None, **attrs}
    return types.new_class(
        cls_name,
        (run.Command,),
        {'register': register},
        lambda ns: ns.update(namespace),
    )


def _subparsers(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    """
    Get the subcommand parsers of the root parser
    """
    action = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    return dict(action.choices)


class TestCommandRegistration:
    """
    Tests for Command subclass auto-registration
    """
    def test_subclass_registers_instance_under_derived_name(self, registry: dict[str, run.Command]) -> None:
        """
        Test that defining a subclass registers an instance named after the class minus its Command suffix
        """
        cls = _make_command('SampleCommand', __doc__='Do a sample thing')
        assert list(registry) == ['sample']
        assert isinstance(registry['sample'], cls)
        assert registry['sample'].description == 'Do a sample thing'

    def test_derived_name_lowercases_and_dashes_underscores(self, registry: dict[str, run.Command]) -> None:
        """
        Test that underscores become dashes and CamelCase is lowercased (not kebab-cased)
        """
        _make_command('Multi_WordCommand')
        assert list(registry) == ['multi-word']

    def test_explicit_name_and_description_win(self, registry: dict[str, run.Command]) -> None:
        """
        Test that explicit name and description class attributes override the derived values
        """
        _make_command('WhateverCommand', name='custom-name', description='Explicit', __doc__='Docstring')
        assert registry['custom-name'].description == 'Explicit'

    def test_register_false_skips_registration(self, registry: dict[str, run.Command]) -> None:
        """
        Test that register=False keeps an intermediate base class out of the registry, but not its subclasses
        """
        base = _make_command('BaseCommand', register=False)
        assert registry == {}

        types.new_class('ChildCommand', (base,), {}, lambda ns: ns.update({'__doc__': 'Child'}))
        assert list(registry) == ['child']

    def test_script_only_and_makefile_only_conflict(self, registry: dict[str, run.Command]) -> None:
        """
        Test that a command cannot be both script-only and makefile-only
        """
        with pytest.raises(ValueError, match='script_only'):
            _make_command('BothCommand', script_only=True, makefile_only=True)
        assert registry == {}

    def test_call_dispatches_to_run(self, registry: dict[str, run.Command]) -> None:
        """
        Test that calling a command instance invokes its run method with the parsed args
        """
        seen: list[argparse.Namespace] = []
        _make_command('RecordCommand', run=lambda self, args: seen.append(args))

        args = argparse.Namespace(flag=True)
        registry['record'](args)
        assert seen == [args]

    def test_real_commands_registered(self) -> None:
        """
        Test that every run.py command is registered, in definition order
        """
        assert list(run.REGISTERED_COMMANDS) == [
            'list-hosts', 'inventory-status', 'update-inventory', 'vault-decrypt', 'vault-encrypt',
            'clean', 'run-hooks', 'pre', 'prepare-hooks', 'install-hooks', 'uninstall-hooks', 'makefile',
            'nas-deploy', 'nas-provision',
            'doctor', 'bootstrap', 'stow', 'render', 'track-claude', 'test',
        ]


class TestGetCommands:
    """
    Tests for get_commands filtering and grouping
    """
    @pytest.fixture(autouse=True)
    def _commands(self, registry: dict[str, run.Command]) -> None:
        """
        Register two grouped commands plus one ungrouped command
        """
        _make_command('AlphaCommand', group='G1')
        _make_command('BetaCommand',  group='G2')
        _make_command('GammaCommand')

    def test_by_name(self) -> None:
        """
        Test that commands are returned by name in registration order
        """
        assert list(run.get_commands()) == ['alpha', 'beta', 'gamma']

    def test_exclude(self) -> None:
        """
        Test that excluded names are dropped
        """
        assert list(run.get_commands(exclude=['beta'])) == ['alpha', 'gamma']

    def test_by_group_defaults_ungrouped_to_other_commands(self) -> None:
        """
        Test that grouping preserves insertion order and files ungrouped commands under Other commands
        """
        groups = run.get_commands(by_group=True)
        assert {group: list(cmds) for group, cmds in groups.items()} == {
            'G1':             ['alpha'],
            'G2':             ['beta'],
            'Other commands': ['gamma'],
        }

    def test_group_order(self) -> None:
        """
        Test that listed groups come first and unlisted groups follow in insertion order
        """
        groups = run.get_commands(by_group=True, group_order=['G2'])
        assert list(groups) == ['G2', 'G1', 'Other commands']


class TestBuildParser:
    """
    Tests for argument parser construction
    """
    def test_every_command_has_subparser(self) -> None:
        """
        Test that each registered command gets a subparser
        """
        assert set(_subparsers(run.build_parser())) == set(run.REGISTERED_COMMANDS)

    def test_help_option_in_other_options_group(self) -> None:
        """
        Test that subcommand -h/--help lives in a trailing Other options group
        """
        for name, subparser in _subparsers(run.build_parser()).items():
            last_group = subparser._action_groups[-1]
            assert last_group.title == 'Other options', name
            assert ['-h', '--help'] in [a.option_strings for a in last_group._group_actions], name

    def test_add_help_false_omits_help(self, registry: dict[str, run.Command]) -> None:
        """
        Test that add_help=False suppresses the subcommand help option
        """
        _make_command('QuietCommand', add_help=False)
        subparser = _subparsers(run.build_parser())['quiet']
        assert not any('-h' in a.option_strings for a in subparser._actions)

    def test_parses_into_typed_args(self) -> None:
        """
        Test that subcommand options land on the root Args namespace
        """
        args = run.build_parser().parse_args(['stow', '-n', 'zsh'], namespace=run.Args())
        assert args.command  == 'stow'
        assert args.simulate is True
        assert args.packages == ['zsh']

    @pytest.mark.parametrize(
        ('argv',                   'expected'),
        [
            (['-d',         'pre'], True),
            (['--debug',    'pre'], True),
            (['--no-debug', 'pre'], False),
            (['pre'],               False),
        ],
    )
    def test_debug_flag(self, monkeypatch: pytest.MonkeyPatch, argv: list[str], expected: bool) -> None:
        """
        Test the -d/--debug/--no-debug root option
        """
        monkeypatch.setattr(run, 'RUN_DEBUG', False)
        assert run.build_parser().parse_args(argv, namespace=run.Args()).debug is expected


class TestMain:
    """
    Tests for main() dispatch and exit codes
    """
    @pytest.fixture(autouse=True)
    def _no_debug(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Keep main() from leaking a debug-mode change into other tests
        """
        monkeypatch.setattr(run, 'RUN_DEBUG', False)

    def test_no_command_prints_help_and_fails(self, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that running without a command prints help and exits 1
        """
        with pytest.raises(SystemExit) as exc_info:
            run.main([])
        assert exc_info.value.code == run.ExitCode.COMMAND_FAILED
        assert "Runner script for Connor's dotfiles" in capsys.readouterr().out

    def test_dispatches_to_command(self, registry: dict[str, run.Command]) -> None:
        """
        Test that main() runs the selected command with the parsed args
        """
        seen: list[argparse.Namespace] = []
        _make_command('RecordCommand', run=lambda self, args: seen.append(args))
        run.main(['record'])
        assert [a.command for a in seen] == ['record']

    @pytest.mark.parametrize(
        ('env_debug', 'argv', 'expected'),
        [
            (False, ['probe'],               False),
            (False, ['-d',         'probe'], True),
            (True,  ['probe'],               True),
            (True,  ['--no-debug', 'probe'], False),
        ],
    )
    def test_debug_flag_sets_run_debug(
        self,
        registry: dict[str, run.Command],
        monkeypatch: pytest.MonkeyPatch,
        env_debug: bool,
        argv: list[str],
        expected: bool,
    ) -> None:
        """
        Test that the parsed --debug/--no-debug value (defaulting to the env var) is what commands see as RUN_DEBUG
        """
        monkeypatch.setattr(run, 'RUN_DEBUG', env_debug)

        seen: list[bool] = []
        _make_command('ProbeCommand', run=lambda self, args: seen.append(run.RUN_DEBUG))
        run.main(argv)
        assert seen == [expected]

    def test_keyboard_interrupt_exits_user_cancelled(self, registry: dict[str, run.Command]) -> None:
        """
        Test that Ctrl-C inside a command exits with USER_CANCELLED
        """
        def interrupt(self: run.Command, args: argparse.Namespace) -> None:
            raise KeyboardInterrupt

        _make_command('InterruptCommand', run=interrupt)
        with pytest.raises(SystemExit) as exc_info:
            run.main(['interrupt'])
        assert exc_info.value.code == run.ExitCode.USER_CANCELLED

    @pytest.mark.parametrize(
        ('argv', 'traceback_shown'),
        [
            (['explode'],       False),
            (['-d', 'explode'], True),
        ],
    )
    def test_unexpected_error_exits_command_failed(
        self,
        registry: dict[str, run.Command],
        capsys: pytest.CaptureFixture[str],
        argv: list[str],
        traceback_shown: bool,
    ) -> None:
        """
        Test that an unexpected exception exits 1, with a traceback only in debug mode
        """
        def explode(self: run.Command, args: argparse.Namespace) -> None:
            raise RuntimeError('boom')

        _make_command('ExplodeCommand', run=explode)
        with pytest.raises(SystemExit) as exc_info:
            run.main(argv)

        captured = capsys.readouterr()
        assert exc_info.value.code == run.ExitCode.COMMAND_FAILED
        assert 'Unexpected error: boom' in captured.out
        assert ('Traceback' in captured.err) is traceback_shown


class TestUpdateInventory:
    """
    Tests for the update-inventory command's pull/clone dispatch and retry behavior
    """
    PULL:   ClassVar[list[str]] = ['git', 'pull', 'origin', 'main']
    STATUS: ClassVar[list[str]] = ['git', 'status', '--porcelain']
    RESET:  ClassVar[list[str]] = ['git', 'reset', '--hard', 'HEAD']

    @pytest.fixture
    def calls(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[list[str]]:
        """
        Point the inventory at a temp dir, fake shell_command, and record every command it is asked to run
        """
        monkeypatch.setattr(run,      'INVENTORY_DIR',        tmp_path / 'inventory')
        monkeypatch.setattr(run,      'handle_command_error', lambda *args, **kwargs: None)
        monkeypatch.setattr(run.time, 'sleep',                lambda seconds: None)

        self.failing: set[str]        = set()
        self.dirty:   bool            = False
        recorded:     list[list[str]] = []

        def fake_shell_command(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            recorded.append(cmd)
            if cmd[1] in self.failing:
                raise subprocess.CalledProcessError(1, cmd)
            return subprocess.CompletedProcess(cmd, 0, stdout=' M hosts.yml\n' if self.dirty else '')

        monkeypatch.setattr(run, 'shell_command', fake_shell_command)
        return recorded

    @staticmethod
    def _run(force: bool = False) -> None:
        """
        Invoke update-inventory through the registry
        """
        run.get_commands()['update-inventory'](argparse.Namespace(force=force))

    def test_pulls_existing_repo(self, calls: list[list[str]]) -> None:
        """
        Test that an existing git checkout is pulled without touching local changes
        """
        (run.INVENTORY_DIR / '.git').mkdir(parents=True)
        self._run()
        assert calls == [self.PULL]

    def test_force_resets_dirty_checkout_before_pull(self, calls: list[list[str]]) -> None:
        """
        Test that --force discards uncommitted changes before pulling
        """
        (run.INVENTORY_DIR / '.git').mkdir(parents=True)
        self.dirty = True
        self._run(force=True)
        assert calls == [self.STATUS, self.RESET, self.PULL]

    def test_force_skips_reset_on_clean_checkout(self, calls: list[list[str]]) -> None:
        """
        Test that --force only resets when the status shows changes
        """
        (run.INVENTORY_DIR / '.git').mkdir(parents=True)
        self._run(force=True)
        assert calls == [self.STATUS, self.PULL]

    def test_clones_when_missing(self, calls: list[list[str]]) -> None:
        """
        Test that a missing inventory directory is cloned
        """
        self._run()
        assert calls == [['git', 'clone', '--no-progress', run.INVENTORY_REPO_URL, str(run.INVENTORY_DIR)]]

    def test_reclones_non_git_directory(self, calls: list[list[str]]) -> None:
        """
        Test that an inventory directory that is not a git repo is removed and re-cloned
        """
        run.INVENTORY_DIR.mkdir()
        (run.INVENTORY_DIR / 'stale.yml').write_text('x')
        self._run()

        assert not (run.INVENTORY_DIR / 'stale.yml').exists()
        assert [cmd[1] for cmd in calls] == ['clone']

    def test_exhausted_retries_exit_command_failed(self, calls: list[list[str]]) -> None:
        """
        Test that a pull failing on every attempt is retried three times (re-running the force reset) then exits 1
        """
        (run.INVENTORY_DIR / '.git').mkdir(parents=True)
        self.failing = {'pull'}
        with pytest.raises(SystemExit) as exc_info:
            self._run(force=True)

        assert exc_info.value.code == run.ExitCode.COMMAND_FAILED
        assert calls == [self.STATUS, self.PULL] * 3


class TestMakefileCommand:
    """
    Tests for the makefile command
    """
    def test_generated_makefile_matches_checked_in(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that regenerating the Makefile reproduces the checked-in file (drift guard)
        """
        generated = tmp_path / 'Makefile'
        monkeypatch.setattr(run, 'MAKEFILE', generated)
        run.get_commands()['makefile'](argparse.Namespace())
        assert generated.read_text() == (run.DOTFILES_DIR / 'Makefile').read_text()

    @pytest.mark.parametrize('no_color', [None, '1'])
    def test_generated_makefile_is_independent_of_no_color(self, tmp_path: Path, no_color: str | None) -> None:
        """
        Test that the generated Makefile matches the checked-in file whether or not NO_COLOR is set
        """
        generated = tmp_path / 'Makefile'
        env = {key: val for key, val in os.environ.items() if key != 'NO_COLOR'}
        if no_color is not None:
            env['NO_COLOR'] = no_color

        code = (
            'import argparse, sys; '
            f'sys.path.insert(0, {str(run.DOTFILES_DIR)!r}); '
            'import run; '
            'from pathlib import Path; '
            f'run.MAKEFILE = Path({str(generated)!r}); '
            "run.get_commands()['makefile'](argparse.Namespace())"
        )
        subprocess.run([sys.executable, '-c', code], env=env, capture_output=True, text=True, check=True)
        assert generated.read_text() == (run.DOTFILES_DIR / 'Makefile').read_text()
