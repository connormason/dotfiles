"""
Unit tests for the run.py uv command builders and virtual environment helpers
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import run

Call = tuple[list[str], dict[str, object]]


def _completed(cmd: list[str], returncode: int = 0) -> subprocess.CompletedProcess[str]:
    """
    Build a fake CompletedProcess
    """
    return subprocess.CompletedProcess(cmd, returncode, stdout='', stderr='')


@pytest.fixture
def uv_on_path(monkeypatch: pytest.MonkeyPatch) -> Path:
    """
    Pretend uv is installed at /fake/bin/uv and resolvable through PATH
    """
    uv = Path('/fake/bin/uv')
    monkeypatch.setattr(run,        'find_uv_executable', lambda: uv)
    monkeypatch.setattr(run.shutil, 'which',              lambda name: str(uv))
    return uv


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[Call]:
    """
    Patch shell_command to record each call and succeed
    """
    recorded: list[Call] = []

    def fake_shell_command(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        recorded.append((cmd, kwargs))
        return _completed(cmd)

    monkeypatch.setattr(run, 'shell_command', fake_shell_command)
    return recorded


class TestUvCommand:
    """
    Tests for uv_command
    """
    def test_public_uses_the_wrapper_script(self, uv_on_path: Path) -> None:
        """
        Test that project-scoped calls run through uv-public.sh
        """
        assert run.uv_command('sync', '--check') == [str(run.UV_PUBLIC_SCRIPT), 'sync', '--check']

    def test_not_public_uses_the_uv_executable(self, uv_on_path: Path) -> None:
        """
        Test that tool-level calls bypass the wrapper
        """
        assert run.uv_command('--version', public=False) == [str(uv_on_path), '--version']

    def test_not_public_falls_back_to_bare_uv(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that a missing uv resolves to the bare name so the failure surfaces from the shell
        """
        monkeypatch.setattr(run, 'find_uv_executable', lambda: None)
        assert run.uv_command('--version', public=False) == ['uv', '--version']

    def test_public_wraps_with_path_when_uv_is_off_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that a uv found outside PATH has its directory prepended so the wrapper's `exec uv` resolves
        """
        monkeypatch.setattr(run,        'find_uv_executable', lambda: Path('/opt/uv-home/uv'))
        monkeypatch.setattr(run.shutil, 'which',              lambda name: None)
        monkeypatch.setenv('PATH', '/usr/bin')

        cmd = run.uv_command('lock')
        assert cmd == ['env', f'PATH=/opt/uv-home{run.os.pathsep}/usr/bin', str(run.UV_PUBLIC_SCRIPT), 'lock']


class TestUvRun:
    """
    Tests for uv_run
    """
    def test_builds_command(self, uv_on_path: Path, calls: list[Call]) -> None:
        """
        Test that the options precede the `--` separator and the command follows it
        """
        run.uv_run(['prek', 'install'], active=True, python='3.12', indent=3, check=False)
        assert calls == [(
            [str(run.UV_PUBLIC_SCRIPT), 'run', '--active', '--python', '3.12', '--', 'prek', 'install'],
            {'indent': 3, 'check': False},
        )]


class TestUvSync:
    """
    Tests for uv_sync
    """
    def test_defaults(self, uv_on_path: Path, calls: list[Call]) -> None:
        """
        Test that a bare sync forwards check/indent/env defaults
        """
        run.uv_sync()
        assert calls == [([str(run.UV_PUBLIC_SCRIPT), 'sync'], {'check': True, 'indent': 0, 'env': None})]

    def test_forwards_flags(self, uv_on_path: Path, calls: list[Call]) -> None:
        """
        Test that group, extra, and mode flags map to the matching uv sync options in order
        """
        run.uv_sync(groups=['lint', 'test'], extras=['x'], no_dev=True, inexact=True, active=True, locked=True)
        assert calls[0][0] == [
            str(run.UV_PUBLIC_SCRIPT), 'sync',
            '--extra', 'x',
            '--no-dev',
            '--group', 'lint',
            '--group', 'test',
            '--inexact',
            '--active',
            '--locked',
        ]


class TestUvLock:
    """
    Tests for uv_lock
    """
    @pytest.mark.parametrize(
        ('kwargs', 'expected'),
        [
            ({},                               ['lock']),
            ({'check_only': True},             ['lock', '--check']),
            ({'refresh': True},                ['lock', '--refresh']),
            ({'upgrade': True},                ['lock', '--upgrade']),
            ({'upgrade_packages': ['a', 'b']}, ['lock', '--upgrade-package', 'a', '--upgrade-package', 'b']),
        ],
    )
    def test_builds_command(
        self,
        uv_on_path: Path,
        calls: list[Call],
        kwargs: dict[str, object],
        expected: list[str],
    ) -> None:
        """
        Test that each option maps to the matching uv lock flag and the call runs from the repo root
        """
        run.uv_lock(**kwargs)  # type: ignore[arg-type]
        assert calls == [([str(run.UV_PUBLIC_SCRIPT), *expected], {'indent': 0, 'cwd': run.DOTFILES_DIR})]

    def test_forwards_shell_command_kwargs(self, uv_on_path: Path, calls: list[Call]) -> None:
        """
        Test that check=False reaches shell_command, so a stale lock returns a status instead of raising
        """
        run.uv_lock(check_only=True, check=False, indent=3)
        assert calls[0][1] == {'indent': 3, 'cwd': run.DOTFILES_DIR, 'check': False}


class TestIsVenvStale:
    """
    Tests for is_venv_stale
    """
    @pytest.fixture(autouse=True)
    def _project_venv(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, uv_on_path: Path) -> None:
        """
        Point VENV_DIR at an existing temporary venv directory
        """
        self.venv = tmp_path / '.venv'
        self.venv.mkdir()
        monkeypatch.setattr(run, 'VENV_DIR', self.venv)

    def test_missing_venv_is_not_stale(self, tmp_path: Path) -> None:
        """
        Test that a nonexistent venv is reported as not stale rather than probed
        """
        assert run.is_venv_stale(tmp_path / 'nope') is False

    def test_no_uv_is_not_stale(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that the probe is skipped when uv cannot be found
        """
        monkeypatch.setattr(run, 'find_uv_executable', lambda: None)
        assert run.is_venv_stale(self.venv) is False

    @pytest.mark.parametrize(('returncode', 'expected'), [(0, False), (1, True)])
    def test_project_venv_uses_the_exit_status(
        self,
        monkeypatch: pytest.MonkeyPatch,
        calls: list[Call],
        returncode: int,
        expected: bool,
    ) -> None:
        """
        Test that a nonzero `uv sync --check` means stale, targeting the project venv implicitly (no --active)
        """
        def fake_shell_command(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append((cmd, kwargs))
            return _completed(cmd, returncode)

        monkeypatch.setattr(run, 'shell_command', fake_shell_command)
        assert run.is_venv_stale(self.venv, all_groups=True) is expected

        cmd, kwargs = calls[0]
        assert cmd == [str(run.UV_PUBLIC_SCRIPT), 'sync', '--check', '--all-groups', '--inexact']
        assert kwargs['env'] is None

    def test_external_venv_is_probed_with_active(self, tmp_path: Path, calls: list[Call]) -> None:
        """
        Test that another venv is checked with --active and VIRTUAL_ENV pointing at it
        """
        other = tmp_path / 'other'
        other.mkdir()

        run.is_venv_stale(other)
        cmd, kwargs = calls[0]
        assert cmd[-1] == '--active'
        assert kwargs['env'] == {'VIRTUAL_ENV': str(other)}

    def test_timeout_is_not_stale(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that a timed-out probe is treated as unknown, not stale
        """
        def timeout(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            raise subprocess.TimeoutExpired(cmd, 5)

        monkeypatch.setattr(run, 'shell_command', timeout)
        assert run.is_venv_stale(self.venv) is False


class TestVenvInspection:
    """
    Tests for the pyvenv.cfg and site-packages helpers
    """
    @pytest.mark.parametrize(
        ('content', 'expected'),
        [
            ('home = /x\nversion_info = 3.13.2\n', '3.13.2'),
            ('home = /x\n',                        None),
        ],
    )
    def test_parse_pyvenv_version(self, tmp_path: Path, content: str, expected: str | None) -> None:
        """
        Test that version_info is extracted from pyvenv.cfg when present
        """
        cfg = tmp_path / 'pyvenv.cfg'
        cfg.write_text(content, encoding='utf-8')
        assert run.parse_pyvenv_version(cfg) == expected

    def test_parse_pyvenv_version_missing_file(self, tmp_path: Path) -> None:
        """
        Test that a missing pyvenv.cfg yields None
        """
        assert run.parse_pyvenv_version(tmp_path / 'pyvenv.cfg') is None

    def test_count_venv_packages(self, tmp_path: Path) -> None:
        """
        Test that .dist-info directories in site-packages are counted
        """
        site = tmp_path / 'lib' / 'python3.12' / 'site-packages'
        for name in ('a-1.0.dist-info', 'b-2.0.dist-info'):
            (site / name).mkdir(parents=True)
        (site / 'a').mkdir()

        assert run.count_venv_packages(tmp_path) == 2

    def test_count_venv_packages_without_site_packages(self, tmp_path: Path) -> None:
        """
        Test that a venv without site-packages yields None
        """
        assert run.count_venv_packages(tmp_path) is None


class TestGetExternalActiveVenv:
    """
    Tests for get_external_active_venv
    """
    def test_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that no VIRTUAL_ENV means no external venv
        """
        monkeypatch.delenv('VIRTUAL_ENV', raising=False)
        assert run.get_external_active_venv() is None

    def test_project_venv_is_not_external(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that the project's own .venv is never reported as external
        """
        monkeypatch.setattr(run, 'VENV_DIR', tmp_path)
        monkeypatch.setenv('VIRTUAL_ENV', str(tmp_path))
        assert run.get_external_active_venv() is None

    def test_other_directory_is_external(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that an existing foreign venv is returned resolved
        """
        other = tmp_path / 'other'
        other.mkdir()
        monkeypatch.setattr(run, 'VENV_DIR', tmp_path / '.venv')
        monkeypatch.setenv('VIRTUAL_ENV', str(other))
        assert run.get_external_active_venv() == other.resolve()

    def test_nonexistent_directory_is_ignored(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that a VIRTUAL_ENV pointing at a vanished directory is ignored
        """
        monkeypatch.setenv('VIRTUAL_ENV', str(tmp_path / 'gone'))
        assert run.get_external_active_venv() is None


class TestValidateVenv:
    """
    Tests for validate_venv
    """
    @staticmethod
    def _make_venv(root: Path, version: str) -> Path:
        """
        Create a minimal venv layout reporting ``version``
        """
        (root / 'bin').mkdir(parents=True)
        (root / 'bin' / 'python').write_text('', encoding='utf-8')
        (root / 'pyvenv.cfg').write_text(f'version_info = {version}\n', encoding='utf-8')
        return root

    def test_missing(self, tmp_path: Path) -> None:
        """
        Test that an absent directory is MISSING
        """
        assert run.validate_venv(tmp_path / 'nope').status == run.VenvStatus.MISSING

    def test_broken_symlink(self, tmp_path: Path) -> None:
        """
        Test that a venv without bin/python is BROKEN_SYMLINK
        """
        assert run.validate_venv(tmp_path).status == run.VenvStatus.BROKEN_SYMLINK

    def test_healthy(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that a matching interpreter version in sync with the lock is HEALTHY
        """
        monkeypatch.setattr(run, 'is_venv_stale', lambda *args, **kwargs: False)
        version = f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}'

        health = run.validate_venv(self._make_venv(tmp_path / 'v', version))
        assert health.status         == run.VenvStatus.HEALTHY
        assert health.python_version == version

    def test_not_activated(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that a venv built for another python minor version is NOT_ACTIVATED
        """
        monkeypatch.setattr(run, 'is_venv_stale', lambda *args, **kwargs: False)
        assert run.validate_venv(self._make_venv(tmp_path / 'v', '2.7.1')).status == run.VenvStatus.NOT_ACTIVATED

    def test_stale(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that an out-of-sync venv is STALE_DEPS, taking precedence over not-activated
        """
        monkeypatch.setattr(run, 'is_venv_stale', lambda *args, **kwargs: True)

        health = run.validate_venv(self._make_venv(tmp_path / 'v', '2.7.1'))
        assert health.status == run.VenvStatus.STALE_DEPS
        assert health.stale

    def test_check_stale_false_skips_the_probe(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that quick mode never runs the staleness probe
        """
        def explode(*args: object, **kwargs: object) -> bool:
            raise AssertionError('probe should not run')

        monkeypatch.setattr(run, 'is_venv_stale', explode)
        version = f'{sys.version_info.major}.{sys.version_info.minor}.0'
        assert run.validate_venv(self._make_venv(tmp_path / 'v', version), check_stale=False).stale is False
