"""
Tests for ``scripts/docs_audit/__main__.py``
"""
from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING

from scripts.docs_audit.__main__ import main
from tests.unit.scripts.docs_audit.git_helpers import git_commit_all
from tests.unit.scripts.docs_audit.git_helpers import git_init

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _make_undocumented_package(root: Path) -> None:
    """
    Commit a repo containing one Python package that has no README
    """
    git_init(root)
    (root / 'pkg').mkdir()
    (root / 'pkg' / 'mod.py').write_text('x\n', encoding='utf-8')
    git_commit_all(root, 'init')


class TestMain:
    """
    Tests for :func:`scripts.docs_audit.__main__.main`
    """
    def test_clean_scope_exits_zero(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Verify a genuinely conformant scope exits 0 (without --no-fail) and emits the JSON envelope
        """
        git_init(tmp_path)
        (tmp_path / 'README.md').write_text('# repo\n', encoding='utf-8')
        (tmp_path / 'docs').mkdir()
        (tmp_path / 'docs' / 'README.md').write_text(
            '[Project Root](../README.md) > **docs**\n\n# Docs\n\nProject documentation index.\n',
            encoding='utf-8',
        )
        git_commit_all(tmp_path, 'init')
        monkeypatch.chdir(tmp_path)

        code = main(['docs', '--json'])
        out  = capsys.readouterr().out

        assert code == 0
        assert '"summary"' in out

    def test_findings_exit_one(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Verify a scope with a missing README exits 1 without --no-fail
        """
        _make_undocumented_package(tmp_path)
        monkeypatch.chdir(tmp_path)

        code = main(['pkg'])
        capsys.readouterr()
        assert code == 1

    def test_no_fail_suppresses_exit_one(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Verify --no-fail returns 0 even when findings exist
        """
        _make_undocumented_package(tmp_path)
        monkeypatch.chdir(tmp_path)

        code = main(['pkg', '--no-fail'])
        capsys.readouterr()
        assert code == 0

    def test_json_flag_emits_valid_json(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Verify --json emits parseable JSON with expected top-level keys
        """
        _make_undocumented_package(tmp_path)
        monkeypatch.chdir(tmp_path)

        main(['pkg', '--json', '--no-fail'])
        data = json.loads(capsys.readouterr().out)

        assert set(data) == {'scope', 'missing', 'stale_candidates', 'structural', 'links', 'policy', 'summary'}
        assert data['missing'] == [{'path': 'pkg', 'class': 'code'}]

    def test_text_output_is_default(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Verify the default output is the human-readable report rather than JSON
        """
        _make_undocumented_package(tmp_path)
        monkeypatch.setenv('NO_COLOR', '1')
        monkeypatch.chdir(tmp_path)

        main(['pkg', '--no-fail'])
        out = capsys.readouterr().out

        assert out.startswith('docs-audit — pkg')
        assert 'Missing (1)' in out

    def test_not_a_git_repository_exits_two(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Verify running outside a git repository is reported on stderr and exits 2
        """
        # Stop git from discovering a repository in any parent of the scratch directory
        monkeypatch.setenv('GIT_CEILING_DIRECTORIES', str(tmp_path.parent))
        monkeypatch.chdir(tmp_path)

        try:
            main(['--no-fail'])
        except SystemExit as exc:
            assert exc.code == 2
        else:
            raise AssertionError('expected SystemExit(2)')
        assert 'not inside a git repository' in capsys.readouterr().err

    def test_git_failure_during_audit_exits_two(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Verify a git failure during the audit is reported and exits 2 (not 1)
        """
        _make_undocumented_package(tmp_path)
        monkeypatch.chdir(tmp_path)

        def _boom(*_args: object, **_kwargs: object) -> None:
            raise subprocess.CalledProcessError(returncode=128, cmd=['git', 'ls-files'])

        monkeypatch.setattr('scripts.docs_audit.audit.discover', _boom)

        code = main(['pkg'])
        err  = capsys.readouterr().err
        assert code == 2
        assert 'docs-audit' in err
