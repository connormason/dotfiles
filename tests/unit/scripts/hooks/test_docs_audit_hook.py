"""
Tests for ``scripts/hooks/docs_audit_hook.py``
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType

HOOK_PATH = Path(__file__).parents[4] / 'scripts' / 'hooks' / 'docs_audit_hook.py'

assert HOOK_PATH.is_file(), (
    f'Script under test not found: {HOOK_PATH}\n'
    'Did the script move? Update HOOK_PATH in this test module.'
)


def _load_hook() -> ModuleType:
    """
    Load docs_audit_hook.py by file path (the hooks directory is not a package).

    :return: the loaded module
    """
    spec = importlib.util.spec_from_file_location('_hooks_docs_audit_hook', HOOK_PATH)
    assert spec        is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestDocsAuditHook:
    """
    Tests for the changed-README prek hook
    """
    def setup_method(self) -> None:
        """
        Load the docs_audit_hook module before each test
        """
        self.mod = _load_hook()

    def test_ignores_non_readme_filenames(self) -> None:
        """
        Verify non-README filenames are silently ignored and the hook exits 0
        """
        assert self.mod.main(['scripts/some_module.py', 'CHANGELOG.md']) == 0

    def test_passes_clean_readme(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Verify a structurally complete leaf README passes the hook
        """
        monkeypatch.chdir(tmp_path)

        # Create a parent README so the breadcrumb link resolves
        (tmp_path / 'README.md').write_text('# Project Root\n\nRoot index.\n', encoding='utf-8')

        pkg_dir = tmp_path / 'pkg'
        pkg_dir.mkdir()
        readme = pkg_dir / 'README.md'
        readme.write_text(
            '[Project Root](../README.md) > **pkg**\n\n# pkg\n\nClean content.\n',
            encoding='utf-8',
        )
        assert self.mod.main([str(readme)]) == 0

    def test_fails_readme_with_policy_violation(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Verify a README containing a forbidden pattern fails the hook
        """
        monkeypatch.chdir(tmp_path)
        (tmp_path / 'README.md').write_text('# Project Root\n\nRoot index.\n', encoding='utf-8')

        pkg_dir = tmp_path / 'pkg'
        pkg_dir.mkdir()
        readme = pkg_dir / 'README.md'
        readme.write_text(
            '[Project Root](../README.md) > **pkg**\n\n# pkg\n\nRun ruff format.\n',
            encoding='utf-8',
        )
        assert self.mod.main([str(readme)]) == 1

    def test_fails_readme_with_structural_and_link_issues(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """
        Verify a README missing its breadcrumb and containing a broken relative link fails the hook
        """
        monkeypatch.chdir(tmp_path)
        readme = tmp_path / 'README.md'
        readme.write_text('# pkg\n\nNo breadcrumb here.\n\n[gone](missing.md)\n', encoding='utf-8')
        assert self.mod.main([str(readme)]) == 1

    def test_failure_report_names_each_issue_kind(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """
        Verify the failure output lists the structural, link, and policy problems of a README
        """
        monkeypatch.setenv('NO_COLOR', '1')
        monkeypatch.chdir(tmp_path)

        pkg_dir = tmp_path / 'pkg'
        pkg_dir.mkdir()
        readme = pkg_dir / 'README.md'
        readme.write_text('# pkg\n\nRun ruff format.\n\n[gone](missing.md)\n', encoding='utf-8')

        assert self.mod.main([str(readme)]) == 1
        out = capsys.readouterr().out

        assert 'structural: missing breadcrumb' in out
        assert 'link: missing.md (path not found)' in out
        assert 'policy:' in out

    def test_missing_file_is_skipped(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Verify a README path that no longer exists (e.g. a deleted file) is skipped rather than raising
        """
        monkeypatch.chdir(tmp_path)
        assert self.mod.main([str(tmp_path / 'gone' / 'README.md')]) == 0

    def test_symlinked_child_does_not_require_downlink(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """
        Verify a symlinked child directory containing a README does not demand a down-link from its parent

        A symlink is recorded by ``git ls-files`` as a single entry rather than an expanded directory, so the CLI
        audit never treats its target as a child; the hook must match that behavior and skip symlinks.
        """
        monkeypatch.chdir(tmp_path)
        (tmp_path / 'README.md').write_text('# Project Root\n\nRoot index.\n', encoding='utf-8')

        pkg_dir = tmp_path / 'pkg'
        pkg_dir.mkdir()

        # A real sibling directory with a README, which the symlink will point at
        real_target = tmp_path / 'real_target'
        real_target.mkdir()
        (real_target / 'README.md').write_text('# real\n', encoding='utf-8')

        # The pkg README has no down-link to the symlinked child below
        readme = pkg_dir / 'README.md'
        readme.write_text(
            '[Project Root](../README.md) > **pkg**\n\n# pkg\n\nClean content.\n',
            encoding='utf-8',
        )
        (pkg_dir / 'aliased').symlink_to(real_target, target_is_directory=True)

        assert self.mod.main([str(readme)]) == 0

    def test_excluded_child_does_not_require_downlink(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """
        Verify a child directory matching an audit exclusion (e.g. a hidden tooling directory) demands no down-link
        """
        monkeypatch.chdir(tmp_path)
        (tmp_path / 'README.md').write_text('# Project Root\n\nRoot index.\n', encoding='utf-8')

        pkg_dir = tmp_path / 'pkg'
        (pkg_dir / '.github').mkdir(parents=True)
        (pkg_dir / '.github' / 'README.md').write_text('# hidden\n', encoding='utf-8')

        readme = pkg_dir / 'README.md'
        readme.write_text(
            '[Project Root](../README.md) > **pkg**\n\n# pkg\n\nClean content.\n',
            encoding='utf-8',
        )

        assert self.mod.main([str(readme)]) == 0

    def test_real_child_requires_downlink(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Verify an ordinary child directory with a README does demand a down-link from its parent
        """
        monkeypatch.chdir(tmp_path)
        (tmp_path / 'README.md').write_text('# Project Root\n\nRoot index.\n', encoding='utf-8')

        pkg_dir = tmp_path / 'pkg'
        (pkg_dir / 'sub').mkdir(parents=True)
        (pkg_dir / 'sub' / 'README.md').write_text('# sub\n', encoding='utf-8')

        readme = pkg_dir / 'README.md'
        readme.write_text(
            '[Project Root](../README.md) > **pkg**\n\n# pkg\n\nClean content.\n',
            encoding='utf-8',
        )

        assert self.mod.main([str(readme)]) == 1

    def test_repo_root_readme_needs_no_breadcrumb(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Verify the repo-root README is exempt from the breadcrumb requirement, independent of any git state
        """
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(self.mod, 'REPO_ROOT', tmp_path.resolve())

        readme = tmp_path / 'README.md'
        readme.write_text('# Project Root\n\nRoot index.\n', encoding='utf-8')

        assert self.mod.main([str(readme)]) == 0

    def test_repo_root_detection_ignores_git_env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Verify GIT_DIR (set by git while committing from a linked worktree) does not break root-README detection
        """
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(self.mod, 'REPO_ROOT', tmp_path.resolve())
        monkeypatch.setenv('GIT_DIR', str(tmp_path / 'not-a-git-dir'))

        readme = tmp_path / 'README.md'
        readme.write_text('# Project Root\n\nRoot index.\n', encoding='utf-8')

        assert self.mod.main([str(readme)]) == 0

    @pytest.mark.parametrize('name', ['inventory', 'archive'])
    def test_root_only_excluded_child_needs_no_downlink_from_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
    ) -> None:
        """
        Verify a repo-root-only excluded child (e.g. the gitignored inventory clone) is not demanded as a root down-link
        """
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(self.mod, 'REPO_ROOT', tmp_path.resolve())

        (tmp_path / name).mkdir()
        (tmp_path / name / 'README.md').write_text('# Separate repo\n', encoding='utf-8')

        readme = tmp_path / 'README.md'
        readme.write_text('# Project Root\n\nRoot index.\n', encoding='utf-8')

        assert self.mod.main([str(readme)]) == 0

    def test_root_only_excluded_name_still_required_when_nested(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """
        Verify a nested directory named like a root-only exclude still demands a down-link from its parent
        """
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(self.mod, 'REPO_ROOT', tmp_path.resolve())
        (tmp_path / 'README.md').write_text('# Project Root\n\nRoot index.\n', encoding='utf-8')

        pkg_dir = tmp_path / 'pkg'
        (pkg_dir / 'inventory').mkdir(parents=True)
        (pkg_dir / 'inventory' / 'README.md').write_text('# inventory\n', encoding='utf-8')

        readme = pkg_dir / 'README.md'
        readme.write_text(
            '[Project Root](../README.md) > **pkg**\n\n# pkg\n\nClean content.\n',
            encoding='utf-8',
        )

        assert self.mod.main([str(readme)]) == 1
