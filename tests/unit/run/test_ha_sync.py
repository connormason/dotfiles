"""
Unit tests for the run.py Home Assistant config sync (ha-pull, ha-push) and its tree and tar helpers

The end-to-end tests replace the ssh transport with a local ``sh -c`` and the VM's ``/config`` with a temp directory,
so the real tar pipelines, diffing, rollback, and command flow all run
"""
from __future__ import annotations

import argparse
import io
import os
import shutil
import stat
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import TYPE_CHECKING
from typing import NamedTuple

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import run

if TYPE_CHECKING:
    from collections.abc import Sequence

# ==================================================================================================
# Helpers
# ==================================================================================================


def _write(path: Path, text: str = 'x') -> Path:
    """
    Write a file, creating parent directories
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


def _tree(root: Path) -> dict[str, str]:
    """
    Snapshot every file under root as {relative path: text}
    """
    return {
        p.relative_to(root).as_posix(): p.read_text(encoding='utf-8')
        for p in sorted(root.rglob('*'))
        if p.is_file()
    }


def _pull(*, dry_run: bool = False, force: bool = False) -> None:
    """
    Run ha-pull
    """
    run.REGISTERED_COMMANDS['ha-pull'](argparse.Namespace(dry_run=dry_run, force=force))


def _push(*, dry_run: bool = False, restart: bool = False, yes: bool = True) -> None:
    """
    Run ha-push
    """
    run.REGISTERED_COMMANDS['ha-push'](argparse.Namespace(dry_run=dry_run, restart=restart, yes=yes))


# ==================================================================================================
# Fixtures
# ==================================================================================================


class FakeVM(NamedTuple):
    """
    Local stand-ins for the Home Assistant VM and the repo checkout
    """
    remote:   Path    # the VM's /config
    local:    Path    # homeassistant/config/ in the repo
    log:      Path    # one line per `ha ...` invocation
    sudo_log: Path    # one line per `sudo ...` invocation


def _write_shim(path: Path, body: str) -> None:
    """
    Write an executable sh script
    """
    path.write_text(f'#!/bin/sh\n{body}', encoding='utf-8')
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


@pytest.fixture
def vm(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> FakeVM:
    """
    Point run.py at a fake VM (local sh + temp /config + fake ha CLI) and a temp repo directory

    The VM's SSH login is an unprivileged user and its /config is root-owned: shims for ``tar -x`` and ``rm`` refuse to
    write unless they were launched through the fake ``sudo``, as on the real Advanced SSH & Terminal app. The ``ha``
    CLI likewise rejects calls that lack the Supervisor token, which only a login shell (``sh -lc``) provides. The
    ``tar`` shim sets COPYFILE_DISABLE so macOS bsdtar skips its ``._*`` xattr sidecars, matching the VM's busybox tar
    """
    remote   = tmp_path / 'vm' / 'config'
    local    = tmp_path / 'repo' / 'homeassistant' / 'config'
    log      = tmp_path / 'ha.log'
    sudo_log = tmp_path / 'sudo.log'
    bindir   = tmp_path / 'bin'
    real_tar = shutil.which('tar')
    real_rm  = shutil.which('rm')
    real_sh  = shutil.which('sh')

    remote.mkdir(parents=True)
    local.mkdir(parents=True)
    bindir.mkdir()

    _write_shim(
        bindir / 'ha',
        'if [ -z "$HA_FAKE_TOKEN" ]; then\n'
        '    echo "Error: unauthorized: missing or invalid API token" >&2; exit 1\n'
        'fi\n'
        'echo "$@" >> "$HA_FAKE_LOG"\n'
        'if [ "$1 $2" = "core check" ] && grep -q BROKEN "$HA_FAKE_CONFIG/configuration.yaml"; then\n'
        '    echo "Invalid config"; exit 1\n'
        'fi\n',
    )
    _write_shim(
        bindir / 'sh',
        'if [ "$1" = "-lc" ]; then\n'
        '    shift\n'
        f'    HA_FAKE_TOKEN=1 exec {real_sh} -c "$@"\n'
        'fi\n'
        f'exec {real_sh} "$@"\n',
    )
    _write_shim(
        bindir / 'sudo',
        'echo "$@" >> "$HA_FAKE_SUDO_LOG"\n'
        '[ "$1" = "-n" ] && shift\n'
        'HA_FAKE_ROOT=1 exec "$@"\n',
    )
    _write_shim(
        bindir / 'tar',
        'if [ "$1" = "-xf" ] && [ -z "$HA_FAKE_ROOT" ]; then\n'
        '    echo "tar: can\'t remove old file automations.yaml: Permission denied" >&2; exit 1\n'
        'fi\n'
        f'COPYFILE_DISABLE=1 exec {real_tar} "$@"\n',
    )
    _write_shim(
        bindir / 'rm',
        'if [ -z "$HA_FAKE_ROOT" ]; then\n'
        '    echo "rm: can\'t remove file: Permission denied" >&2; exit 1\n'
        'fi\n'
        f'exec {real_rm} "$@"\n',
    )

    monkeypatch.setenv('PATH',             f'{bindir}{os.pathsep}{os.environ["PATH"]}')
    monkeypatch.delenv('HA_FAKE_ROOT',     raising=False)
    monkeypatch.delenv('HA_FAKE_TOKEN',    raising=False)
    monkeypatch.setenv('HA_FAKE_LOG',      str(log))
    monkeypatch.setenv('HA_FAKE_SUDO_LOG', str(sudo_log))
    monkeypatch.setenv('HA_FAKE_CONFIG',   str(remote))

    monkeypatch.setattr(run, 'ha_ssh_command',              lambda remote_command: ['sh', '-c', remote_command])
    monkeypatch.setattr(run, 'HA_USER',                     'connormason')
    monkeypatch.setattr(run, 'HA_REMOTE_CONFIG_DIR',        str(remote))
    monkeypatch.setattr(run, 'HA_CONFIG_DIR',               local)
    monkeypatch.setattr(run, 'DOTFILES_DIR',                tmp_path / 'repo')
    monkeypatch.setattr(run, 'ha_config_has_local_changes', lambda: False)

    return FakeVM(remote=remote, local=local, log=log, sudo_log=sudo_log)


# ==================================================================================================
# Unit tests
# ==================================================================================================


class TestDiffTrees:
    """
    Tests for diff_trees
    """
    def test_reports_added_modified_and_removed_sorted(self, tmp_path: Path) -> None:
        """
        Test that files only in new are added, only in old removed, and differing ones modified
        """
        old = tmp_path / 'old'
        new = tmp_path / 'new'

        _write(old / 'configuration.yaml', 'same')
        _write(new / 'configuration.yaml', 'same')
        _write(old / 'automations.yaml',   'old')
        _write(new / 'automations.yaml',   'new')
        _write(old / 'scripts.yaml')
        _write(new / 'blueprints' / 'b.yaml')
        _write(new / 'blueprints' / 'a.yaml')

        diff = run.diff_trees(old, new)
        assert diff.added    == ['blueprints/a.yaml', 'blueprints/b.yaml']
        assert diff.modified == ['automations.yaml']
        assert diff.removed  == ['scripts.yaml']
        assert diff.changed

    def test_identical_trees_have_no_changes(self, tmp_path: Path) -> None:
        """
        Test that equal trees produce an empty diff
        """
        _write(tmp_path / 'a' / 'scenes.yaml', 'x')
        _write(tmp_path / 'b' / 'scenes.yaml', 'x')
        assert not run.diff_trees(tmp_path / 'a', tmp_path / 'b').changed

    def test_ignores_untracked_names_and_excluded_files(self, tmp_path: Path) -> None:
        """
        Test that files outside the allowlist, caches, and symlinks never appear in a diff
        """
        old = tmp_path / 'old'
        new = tmp_path / 'new'
        old.mkdir()

        _write(new / 'secrets.yaml')
        _write(new / '.storage' / 'auth')
        _write(new / 'custom_components' / 'hacs' / '__init__.py')
        _write(new / 'packages' / 'x' / '__pycache__' / 'x.pyc')
        _write(new / 'packages' / 'x' / '.DS_Store')
        _write(new / 'real.txt')
        (new / 'scripts.yaml').symlink_to(new / 'real.txt')

        assert not run.diff_trees(old, new).changed


class TestApplyTreeDiff:
    """
    Tests for apply_tree_diff
    """
    def test_copies_removes_and_prunes_empty_directories(self, tmp_path: Path) -> None:
        """
        Test that added and modified files are copied, removed ones deleted, and emptied directories pruned
        """
        src  = tmp_path / 'src'
        dest = tmp_path / 'dest'

        _write(src / 'configuration.yaml', 'new')
        _write(src / 'blueprints' / 'automation' / 'n.yaml', 'n')
        _write(dest / 'configuration.yaml', 'old')
        _write(dest / 'themes' / 'dark' / 'dark.yaml')

        run.apply_tree_diff(src, dest, run.diff_trees(dest, src))

        assert _tree(dest) == {'configuration.yaml': 'new', 'blueprints/automation/n.yaml': 'n'}
        assert not (dest / 'themes' / 'dark').exists()
        assert (dest / 'themes').is_dir()


class TestTarStream:
    """
    Tests for pack_ha_files and unpack_ha_stream
    """
    def test_round_trip_normalizes_ownership_and_modes(self, tmp_path: Path) -> None:
        """
        Test that packing records root ownership and 0644/0755 modes, and unpacking restores content with mode 0644
        """
        src = tmp_path / 'src'
        _write(src / 'configuration.yaml', 'cfg').chmod(0o600)

        script = _write(src / 'packages' / 'x' / 'run.sh', '#!/bin/sh')
        script.chmod(0o700)

        buffer = io.BytesIO()
        run.pack_ha_files(src, ['configuration.yaml', 'packages/x/run.sh'], buffer)

        buffer.seek(0)
        with tarfile.open(fileobj=buffer, mode='r:') as tar:
            members = {m.name: m for m in tar.getmembers()}

        assert members['configuration.yaml'].mode == 0o644
        assert members['packages/x/run.sh'].mode  == 0o755
        assert all((m.uid, m.gid, m.uname, m.gname) == (0, 0, 'root', 'root') for m in members.values())

        buffer.seek(0)
        dest = tmp_path / 'dest'
        run.unpack_ha_stream(buffer, dest)
        assert _tree(dest) == {'configuration.yaml': 'cfg', 'packages/x/run.sh': '#!/bin/sh'}
        assert stat.S_IMODE((dest / 'packages' / 'x' / 'run.sh').stat().st_mode) == 0o644

    @pytest.mark.parametrize('name', ['../escape.yaml', '/abs/escape.yaml', 'blueprints/../../escape.yaml'])
    def test_unpack_rejects_unsafe_paths(self, tmp_path: Path, name: str) -> None:
        """
        Test that a member path that is absolute or climbs out of the destination raises
        """
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode='w') as tar:
            info = tarfile.TarInfo(name)
            info.size = 1
            tar.addfile(info, io.BytesIO(b'x'))
        buffer.seek(0)

        with pytest.raises(run.HASyncError, match='unsafe path'):
            run.unpack_ha_stream(buffer, tmp_path / 'dest')
        assert not (tmp_path / 'escape.yaml').exists()

    def test_unpack_skips_links_and_directories(self, tmp_path: Path) -> None:
        """
        Test that only regular files are extracted from a stream that also holds a symlink and a directory
        """
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode='w') as tar:
            directory = tarfile.TarInfo('blueprints')
            directory.type = tarfile.DIRTYPE
            tar.addfile(directory)

            link = tarfile.TarInfo('scripts.yaml')
            link.type = tarfile.SYMTYPE
            link.linkname = '/etc/passwd'
            tar.addfile(link)

            real = tarfile.TarInfo('scenes.yaml')
            real.size = 2
            tar.addfile(real, io.BytesIO(b'ok'))

        buffer.seek(0)

        dest = tmp_path / 'dest'
        run.unpack_ha_stream(buffer, dest)
        assert _tree(dest) == {'scenes.yaml': 'ok'}
        assert not (dest / 'scripts.yaml').is_symlink()


class TestHaSshCommand:
    """
    Tests for ha_ssh_command
    """
    def test_targets_configured_host_with_key_auth_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that the command uses batch mode, the configured port and login, and wraps the snippet in sh -c
        """
        monkeypatch.setattr(run, 'HA_HOST', 'ha.example')
        monkeypatch.setattr(run, 'HA_USER', 'hass')
        monkeypatch.setattr(run, 'HA_PORT', '2222')

        cmd = run.ha_ssh_command("echo 'hi'")
        assert cmd[0] == 'ssh'
        assert 'BatchMode=yes' in cmd
        assert cmd[cmd.index('-p') + 1] == '2222'
        assert 'hass@ha.example' in cmd
        assert cmd[-1].startswith('sh -c ')
        assert 'echo' in cmd[-1]


class TestHaPrivileged:
    """
    Tests for ha_privileged
    """
    @pytest.mark.parametrize(
        ('user', 'expected'),
        [
            ('root',        'tar -xf -'),
            ('connormason', 'sudo -n tar -xf -'),
        ],
    )
    def test_escalates_only_for_non_root_logins(
        self,
        monkeypatch: pytest.MonkeyPatch,
        user: str,
        expected: str,
    ) -> None:
        """
        Test that the snippet is prefixed with non-interactive sudo unless the SSH login is already root
        """
        monkeypatch.setattr(run, 'HA_USER', user)
        assert run.ha_privileged('tar -xf -') == expected


class TestHaCli:
    """
    Tests for ha_cli
    """
    def test_runs_the_subcommand_in_a_login_shell(self) -> None:
        """
        Test that the ha CLI is wrapped in a login shell, which is what supplies its Supervisor token
        """
        assert run.ha_cli('core check') == "sh -lc 'ha core check'"


class TestHaConfigHasLocalChanges:
    """
    Tests for ha_config_has_local_changes
    """
    def test_detects_untracked_and_ignores_unlisted_files(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """
        Test that an untracked allowlisted file counts as a change while an unlisted file does not
        """
        repo   = tmp_path / 'repo'
        config = repo / 'homeassistant' / 'config'
        config.mkdir(parents=True)

        subprocess.run(['git', 'init', '-q'], cwd=repo, check=True)
        monkeypatch.setattr(run, 'DOTFILES_DIR',   repo)
        monkeypatch.setattr(run, 'HA_CONFIG_DIR',  config)

        _write(config / 'secrets.yaml.example')
        assert not run.ha_config_has_local_changes()

        _write(config / 'automations.yaml', '[]')
        assert run.ha_config_has_local_changes()


class TestHaPull:
    """
    Tests for the ha-pull command against a fake VM
    """
    def test_pulls_only_allowlisted_files(self, vm: FakeVM) -> None:
        """
        Test that tracked files and directories arrive while secrets, .storage, and the database stay behind
        """
        _write(vm.remote / 'configuration.yaml',                         'cfg')
        _write(vm.remote / 'automations.yaml',                           '[]')
        _write(vm.remote / 'blueprints' / 'automation' / 'm.yaml',       'bp')
        _write(vm.remote / 'packages' / 'x' / '__pycache__' / 'x.pyc',   'pyc')
        _write(vm.remote / 'custom_components' / 'hacs' / '__init__.py', 'hacs')
        _write(vm.remote / 'secrets.yaml',                               'token: hunter2')
        _write(vm.remote / '.storage' / 'auth',                          'secret')
        _write(vm.remote / 'home-assistant_v2.db',                       'db')

        _pull()
        assert _tree(vm.local) == {
            'configuration.yaml':           'cfg',
            'automations.yaml':             '[]',
            'blueprints/automation/m.yaml': 'bp',
        }

    def test_second_pull_reports_already_in_sync(self, vm: FakeVM, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that pulling an unchanged VM prints the in-sync message and writes nothing
        """
        _write(vm.remote / 'configuration.yaml', 'cfg')
        _pull()
        capsys.readouterr()

        _pull()
        assert 'already matches' in run.unstyle(capsys.readouterr().out)

    def test_dry_run_writes_nothing(self, vm: FakeVM, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that --dry-run lists the incoming files without touching the repo directory
        """
        _write(vm.remote / 'configuration.yaml', 'cfg')
        _pull(dry_run=True)

        assert _tree(vm.local) == {}
        assert '+ configuration.yaml' in run.unstyle(capsys.readouterr().out)

    def test_mirrors_modifications_and_deletions(self, vm: FakeVM) -> None:
        """
        Test that a changed file is overwritten and a file deleted on the VM is deleted locally
        """
        _write(vm.local  / 'configuration.yaml', 'stale')
        _write(vm.local  / 'scripts.yaml',       'gone on the VM')
        _write(vm.remote / 'configuration.yaml', 'fresh')

        _pull()
        assert _tree(vm.local) == {'configuration.yaml': 'fresh'}

    def test_refuses_to_overwrite_uncommitted_local_changes(
        self,
        vm: FakeVM,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Test that a dirty tracked tree aborts the pull unless --force is given
        """
        _write(vm.remote / 'configuration.yaml', 'remote')
        _write(vm.local  / 'configuration.yaml', 'local edit')
        monkeypatch.setattr(run, 'ha_config_has_local_changes', lambda: True)

        with pytest.raises(SystemExit) as exc_info:
            _pull()

        assert exc_info.value.code == run.ExitCode.COMMAND_FAILED
        assert _tree(vm.local) == {'configuration.yaml': 'local edit'}

        _pull(force=True)
        assert _tree(vm.local) == {'configuration.yaml': 'remote'}

    def test_unreachable_vm_exits_with_remedy(
        self,
        vm: FakeVM,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that a failing ssh probe exits non-zero and names the SSH app
        """
        monkeypatch.setattr(run, 'ha_ssh_command', lambda remote_command: ['sh', '-c', 'echo refused >&2; exit 255'])

        with pytest.raises(SystemExit) as exc_info:
            _pull()
        assert exc_info.value.code == run.ExitCode.COMMAND_FAILED

        output = run.unstyle(capsys.readouterr().out)
        assert 'Advanced SSH' in output
        assert 'refused'      in output

    def test_missing_remote_config_is_reported(self, vm: FakeVM, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that a VM holding none of the tracked entries fails the pull with the remote's exit status
        """
        with pytest.raises(SystemExit) as exc_info:
            _pull()

        assert exc_info.value.code == run.ExitCode.COMMAND_FAILED
        assert 'Downloading the Home Assistant config failed (exit 3)' in run.unstyle(capsys.readouterr().out)


class TestHaPush:
    """
    Tests for the ha-push command against a fake VM
    """
    def test_pushes_added_modified_and_removed_files(self, vm: FakeVM) -> None:
        """
        Test that the VM ends up matching the repo for tracked files, leaving untracked VM files alone
        """
        _write(vm.remote / 'configuration.yaml',                   'old')
        _write(vm.remote / 'scripts.yaml',                         'delete me')
        _write(vm.remote / 'secrets.yaml',                         'keep me')
        _write(vm.remote / '.storage' / 'auth',                    'keep me too')
        _write(vm.local  / 'configuration.yaml',                   'new')
        _write(vm.local  / 'automations.yaml',                     '- alias: a')
        _write(vm.local  / 'blueprints' / 'automation' / 'm.yaml', 'bp')

        _push()

        assert _tree(vm.remote) == {
            'configuration.yaml':            'new',
            'automations.yaml':              '- alias: a',
            'blueprints/automation/m.yaml':  'bp',
            'secrets.yaml':                  'keep me',
            '.storage/auth':                 'keep me too',
        }
        assert vm.log.read_text(encoding='utf-8').splitlines() == ['core check']

    def test_writes_to_root_owned_config_go_through_sudo(self, vm: FakeVM) -> None:
        """
        Test that the upload and the deletion are escalated, while the config check and the fetch are not
        """
        _write(vm.remote / 'configuration.yaml', 'old')
        _write(vm.remote / 'scripts.yaml',       'delete me')
        _write(vm.local  / 'configuration.yaml', 'new')

        _push()

        assert vm.sudo_log.read_text(encoding='utf-8').splitlines() == [
            '-n tar -xf -',
            '-n rm -f -- scripts.yaml',
        ]

    def test_root_login_writes_without_sudo(self, vm: FakeVM, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that a root SSH login never invokes sudo
        """
        monkeypatch.setattr(run, 'HA_USER', 'root')
        monkeypatch.setenv('HA_FAKE_ROOT', '1')
        _write(vm.remote / 'configuration.yaml', 'old')
        _write(vm.local  / 'configuration.yaml', 'new')

        _push()

        assert _tree(vm.remote) == {'configuration.yaml': 'new'}
        assert not vm.sudo_log.exists()

    def test_uploaded_files_get_mode_0644(self, vm: FakeVM) -> None:
        """
        Test that uploaded files get mode 0644 regardless of the repo file's mode
        """
        _write(vm.remote / 'configuration.yaml', 'old')
        _write(vm.local  / 'configuration.yaml', 'new').chmod(0o600)

        _push()

        assert stat.S_IMODE((vm.remote / 'configuration.yaml').stat().st_mode) == 0o644

    def test_dry_run_changes_nothing(self, vm: FakeVM, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that --dry-run prints the plan, leaves the VM untouched, and runs no ha command
        """
        _write(vm.remote / 'configuration.yaml', 'old')
        _write(vm.local  / 'configuration.yaml', 'new')

        _push(dry_run=True)

        assert _tree(vm.remote) == {'configuration.yaml': 'old'}
        assert '~ configuration.yaml' in run.unstyle(capsys.readouterr().out)
        assert not vm.log.exists()

    def test_in_sync_vm_is_a_no_op(self, vm: FakeVM, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that identical trees report in-sync and skip the config check
        """
        _write(vm.remote / 'configuration.yaml', 'same')
        _write(vm.local  / 'configuration.yaml', 'same')

        _push()

        assert 'already matches' in run.unstyle(capsys.readouterr().out)
        assert not vm.log.exists()

    def test_declined_confirmation_cancels(self, vm: FakeVM, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that answering no at the prompt exits with USER_CANCELLED and leaves the VM unchanged
        """
        _write(vm.remote / 'configuration.yaml', 'old')
        _write(vm.local  / 'configuration.yaml', 'new')
        monkeypatch.setattr(run, 'confirm', lambda *a, **k: False)

        with pytest.raises(SystemExit) as exc_info:
            _push(yes=False)

        assert exc_info.value.code == run.ExitCode.USER_CANCELLED
        assert _tree(vm.remote) == {'configuration.yaml': 'old'}

    def test_failed_check_rolls_back_every_change(self, vm: FakeVM, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that a rejected config restores modified, removed, and added files and exits non-zero
        """
        _write(vm.remote / 'configuration.yaml', 'good')
        _write(vm.remote / 'scripts.yaml',       'was here')
        _write(vm.local  / 'configuration.yaml', 'BROKEN')
        _write(vm.local  / 'scenes.yaml',        'added')
        before = _tree(vm.remote)

        with pytest.raises(SystemExit) as exc_info:
            _push()

        assert exc_info.value.code == run.ExitCode.COMMAND_FAILED
        assert _tree(vm.remote) == before

        output = run.unstyle(capsys.readouterr().out)
        assert 'rejected the config' in output
        assert 'Invalid config'      in output

    def test_failed_apply_rolls_back_the_partial_push(
        self,
        vm: FakeVM,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that a failure after the upload (here the deletion step) restores the VM instead of leaving it half-pushed
        """
        _write(vm.remote / 'configuration.yaml', 'old')
        _write(vm.remote / 'scripts.yaml',       'delete me')
        _write(vm.local  / 'configuration.yaml', 'new')
        before = _tree(vm.remote)

        real_delete = run.delete_ha_files
        calls: list[Sequence[str]] = []

        def flaky_delete(relpaths: Sequence[str]) -> None:
            calls.append(relpaths)
            if len(calls) == 1:
                raise run.HASyncError('Deleting from the Home Assistant config failed: connection lost')
            real_delete(relpaths)

        monkeypatch.setattr(run, 'delete_ha_files', flaky_delete)

        with pytest.raises(SystemExit) as exc_info:
            _push()

        assert exc_info.value.code == run.ExitCode.COMMAND_FAILED
        assert _tree(vm.remote) == before

        output = run.unstyle(capsys.readouterr().out)
        assert 'connection lost' in output
        assert 'restored'        in output
        assert not vm.log.exists()

    def test_failed_rollback_is_reported_as_a_possible_partial_push(
        self,
        vm: FakeVM,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that when the upload and the rollback both fail, the output warns the VM may hold a partial push
        """
        _write(vm.remote / 'configuration.yaml', 'old')
        _write(vm.local  / 'configuration.yaml', 'new')

        def failing_upload(root: Path, relpaths: Sequence[str]) -> None:
            raise run.HASyncError('Uploading to the Home Assistant config failed (exit 255): connection lost')

        monkeypatch.setattr(run, 'upload_ha_files', failing_upload)

        with pytest.raises(SystemExit) as exc_info:
            _push()

        assert exc_info.value.code == run.ExitCode.COMMAND_FAILED

        output = run.unstyle(capsys.readouterr().out)
        assert 'Rollback failed' in output
        assert 'partial push'    in output

    def test_restart_flag_restarts_core_after_a_passing_check(self, vm: FakeVM) -> None:
        """
        Test that --restart issues ha core restart after ha core check
        """
        _write(vm.remote / 'configuration.yaml', 'old')
        _write(vm.local  / 'configuration.yaml', 'new')

        _push(restart=True)

        assert vm.log.read_text(encoding='utf-8').splitlines() == ['core check', 'core restart']

    def test_empty_local_tree_points_at_ha_pull(self, vm: FakeVM, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that pushing with nothing tracked locally refuses, so an empty checkout cannot wipe the VM
        """
        _write(vm.remote / 'configuration.yaml', 'keep')

        with pytest.raises(SystemExit) as exc_info:
            _push()

        assert exc_info.value.code == run.ExitCode.COMMAND_FAILED
        assert 'ha-pull' in run.unstyle(capsys.readouterr().out)
        assert _tree(vm.remote) == {'configuration.yaml': 'keep'}
