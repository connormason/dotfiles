"""
Tests for ``scripts/docs_audit/classify.py``
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.docs_audit.classify import DirClass
from scripts.docs_audit.classify import classify


class TestClassify:
    """
    Tests for :func:`scripts.docs_audit.classify.classify`
    """
    def test_repo_root_is_meta(self, tmp_path: Path) -> None:
        """
        Verify the repo root classifies as META
        """
        assert classify(Path(), repo_root=tmp_path) is DirClass.META

    @pytest.mark.parametrize('name', ['docs', 'scripts', 'tests'])
    def test_top_level_meta_dir_is_meta(self, name: str) -> None:
        """
        Verify each top-level meta directory classifies as META
        """
        assert classify(Path(name), repo_root=Path()) is DirClass.META

    def test_nested_meta_named_dir_is_not_meta(self, tmp_path: Path) -> None:
        """
        Verify a meta-named directory below the top level is classified by its contents, not by name
        """
        nested = tmp_path / 'roles' / 'docs'
        nested.mkdir(parents=True)
        (nested / 'notes.txt').write_text('x\n', encoding='utf-8')
        assert classify(Path('roles/docs'), repo_root=tmp_path) is DirClass.DATA

    def test_plans_subtree_is_exempt(self, tmp_path: Path) -> None:
        """
        Verify docs/plans and its subdirectories classify as EXEMPT
        """
        assert classify(Path('docs/plans'),         repo_root=tmp_path) is DirClass.EXEMPT
        assert classify(Path('docs/plans/2026-06'), repo_root=tmp_path) is DirClass.EXEMPT

    def test_code_dir_is_code(self, tmp_path: Path) -> None:
        """
        Verify a directory containing a .py file classifies as CODE
        """
        pkg = tmp_path / 'scripts' / 'env'
        pkg.mkdir(parents=True)
        (pkg / '__init__.py').write_text('', encoding='utf-8')
        assert classify(Path('scripts/env'), repo_root=tmp_path) is DirClass.CODE

    def test_data_only_dir_is_data(self, tmp_path: Path) -> None:
        """
        Verify a directory with only non-Python files classifies as DATA
        """
        data_dir = tmp_path / 'services' / 'caddy'
        data_dir.mkdir(parents=True)
        (data_dir / 'compose.yml').write_text('services: {}\n', encoding='utf-8')
        assert classify(Path('services/caddy'), repo_root=tmp_path) is DirClass.DATA

    def test_placeholder_only_dir_is_exempt(self, tmp_path: Path) -> None:
        """
        Verify a directory whose only entry is a .gitkeep placeholder classifies as EXEMPT
        """
        config_dir = tmp_path / 'config'
        config_dir.mkdir()
        (config_dir / '.gitkeep').write_text('', encoding='utf-8')
        assert classify(Path('config'), repo_root=tmp_path) is DirClass.EXEMPT

    def test_unreadable_dir_is_exempt(self, tmp_path: Path) -> None:
        """
        Verify a directory that cannot be iterated (OSError) classifies as EXEMPT
        """
        # The directory is never created, so iterdir() raises FileNotFoundError (an OSError subclass)
        assert classify(Path('gone'), repo_root=tmp_path) is DirClass.EXEMPT
