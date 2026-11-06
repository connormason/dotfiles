"""
Tests for ``scripts/docs_audit/discover.py``
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from scripts.docs_audit.discover import discover
from scripts.docs_audit.discover import is_excluded
from tests.unit.scripts.docs_audit.git_helpers import git_commit_all
from tests.unit.scripts.docs_audit.git_helpers import git_init


class TestIsExcluded:
    """
    Tests for :func:`scripts.docs_audit.discover.is_excluded`
    """
    @pytest.mark.parametrize(
        ('path', 'expected'),
        [
            (Path('scripts/__pycache__'),        True),
            (Path('dotfiles.egg-info/PKG-INFO'), True),
            (Path('stow/git/.config/gh'),        True),   # hidden stow payload directory
            (Path('.github/workflows'),          True),
            (Path('.ctx'),                       True),
            (Path('archive'),                    True),   # frozen archive, top-level only
            (Path('archive/ansible-macos'),      True),
            (Path('build'),                      True),   # top-level artifact dir
            (Path('dist'),                       True),   # top-level artifact dir
            (Path('roles/docker'),               False),
            (Path('scripts/hooks'),              False),
            (Path('scripts/install/build'),      False),  # nested source pkg named "build" is NOT excluded
            (Path('docs/archive'),               False),  # nested dir named "archive" is NOT excluded
        ],
    )
    def test_is_excluded(self, path: Path, expected: bool) -> None:
        """
        Verify excluded segments/suffixes and top-level artifact dirs are detected, while a nested source package that
        merely shares a name with a top-level exclusion is kept
        """
        assert is_excluded(path) == expected


@pytest.mark.skipif(not shutil.which('git'), reason='git not available')
class TestDiscover:
    """
    Tests for :func:`scripts.docs_audit.discover.discover`
    """
    def test_discovers_tracked_dirs_only(self, tmp_path: Path) -> None:
        """
        Verify discovery returns directories of tracked files and skips excluded ones
        """
        git_init(tmp_path)

        (tmp_path / 'pkg').mkdir()
        (tmp_path / 'pkg' / 'mod.py').write_text('x\n', encoding='utf-8')
        (tmp_path / '__pycache__').mkdir()
        (tmp_path / '__pycache__' / 'mod.pyc').write_text('x\n', encoding='utf-8')
        (tmp_path / '.github' / 'workflows').mkdir(parents=True)
        (tmp_path / '.github' / 'workflows' / 'ci.yml').write_text('x\n', encoding='utf-8')
        (tmp_path / 'archive' / 'old').mkdir(parents=True)
        (tmp_path / 'archive' / 'old' / 'legacy.py').write_text('x\n', encoding='utf-8')
        git_commit_all(tmp_path, 'init')

        dirs = discover([Path()], repo_root=tmp_path)
        assert Path('pkg')                   in dirs
        assert Path('__pycache__')       not in dirs
        assert Path('.github/workflows') not in dirs
        assert Path('archive/old')       not in dirs

    def test_scope_limits_discovery(self, tmp_path: Path) -> None:
        """
        Verify only directories under the requested scope are returned
        """
        git_init(tmp_path)

        for name in ('alpha', 'beta'):
            (tmp_path / name).mkdir()
            (tmp_path / name / 'mod.py').write_text('x\n', encoding='utf-8')
        git_commit_all(tmp_path, 'init')

        dirs = discover([Path('alpha')], repo_root=tmp_path)
        assert dirs == [Path('alpha')]
