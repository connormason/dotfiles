"""
Tests for ``scripts/docs_audit/audit.py``
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from scripts.docs_audit.audit import run_audit
from tests.unit.scripts.docs_audit.git_helpers import git_commit_all
from tests.unit.scripts.docs_audit.git_helpers import git_init


@pytest.mark.skipif(not shutil.which('git'), reason='git not available')
class TestRunAudit:
    """
    Tests for :func:`scripts.docs_audit.audit.run_audit`
    """
    def test_reports_missing_code_readme(self, tmp_path: Path) -> None:
        """
        Verify run_audit reports a code package that lacks a README
        """
        git_init(tmp_path)
        (tmp_path / 'pkg').mkdir()
        (tmp_path / 'pkg' / 'mod.py').write_text('x\n', encoding='utf-8')
        git_commit_all(tmp_path, 'init')

        report = run_audit([Path('pkg')], repo_root=tmp_path)
        assert Path('pkg') in [m.path for m in report.missing]

    def test_reports_policy_and_links_for_existing_readme(self, tmp_path: Path) -> None:
        """
        Verify run_audit surfaces policy and link findings on an existing README
        """
        git_init(tmp_path)
        (tmp_path / 'pkg').mkdir()
        (tmp_path / 'pkg' / 'mod.py').write_text('x\n', encoding='utf-8')
        (tmp_path / 'pkg' / 'README.md').write_text(
            '[Project Root](../README.md) > **pkg**\n\n# pkg\n\nRun ruff format.\n[gone](missing.md)\n',
            encoding='utf-8',
        )
        git_commit_all(tmp_path, 'init')

        report = run_audit([Path('pkg')], repo_root=tmp_path)
        assert any(p.readme    == Path('pkg/README.md') for p    in report.policy)
        assert any(link.readme == Path('pkg/README.md') for link in report.links)

    def test_reports_missing_downlink_to_child_readme(self, tmp_path: Path) -> None:
        """
        Verify run_audit passes each README's child READMEs to the structural check
        """
        git_init(tmp_path)
        (tmp_path / 'pkg' / 'sub').mkdir(parents=True)
        (tmp_path / 'pkg' / 'mod.py').write_text('x\n', encoding='utf-8')
        (tmp_path / 'pkg' / 'sub' / 'mod.py').write_text('x\n', encoding='utf-8')
        (tmp_path / 'pkg' / 'README.md').write_text(
            '[Project Root](../README.md) > **pkg**\n\n# pkg\n\nNo child links.\n',
            encoding='utf-8',
        )
        (tmp_path / 'pkg' / 'sub' / 'README.md').write_text(
            '[Project Root](../../README.md) > [pkg](../README.md) > **sub**\n\n# sub\n',
            encoding='utf-8',
        )
        git_commit_all(tmp_path, 'init')

        report = run_audit([Path('pkg')], repo_root=tmp_path)
        assert [(s.readme, s.issues) for s in report.structural] == [
            (Path('pkg/README.md'), ['no down-link to sub/README.md']),
        ]

    def test_clean_package_has_no_findings(self, tmp_path: Path) -> None:
        """
        Verify run_audit returns an empty report for a conformant, fully-documented package
        """
        git_init(tmp_path)
        (tmp_path / 'README.md').write_text('# repo\n', encoding='utf-8')
        (tmp_path / 'pkg').mkdir()
        (tmp_path / 'pkg' / 'mod.py').write_text('x\n', encoding='utf-8')
        (tmp_path / 'pkg' / 'README.md').write_text(
            '[Project Root](../README.md) > **pkg**\n\n# pkg\n\nClean module documentation.\n',
            encoding='utf-8',
        )
        git_commit_all(tmp_path, 'init')

        report = run_audit([Path('pkg')], repo_root=tmp_path)
        assert report.has_findings is False

    def test_exempt_dir_readmes_skip_per_readme_checks(self, tmp_path: Path) -> None:
        """
        Verify a README under docs/plans (EXEMPT) is not held to the structural, link, or policy checks
        """
        git_init(tmp_path)
        plan_dir = tmp_path / 'docs' / 'plans' / '2026-01' / 'some-plan'
        plan_dir.mkdir(parents=True)
        (plan_dir / 'README.md').write_text(
            '# Plan\n\nRun ruff format.\n\n[gone](missing.md)\n',
            encoding='utf-8',
        )
        git_commit_all(tmp_path, 'init')

        report = run_audit([Path('docs')], repo_root=tmp_path)
        assert report.structural == []
        assert report.links      == []
        assert report.policy     == []

    def test_non_exempt_readme_is_still_checked(self, tmp_path: Path) -> None:
        """
        Verify the same defective README outside an exempt directory is reported in every per-README category
        """
        git_init(tmp_path)
        (tmp_path / 'pkg').mkdir()
        (tmp_path / 'pkg' / 'mod.py').write_text('x\n', encoding='utf-8')
        (tmp_path / 'pkg' / 'README.md').write_text(
            '# Plan\n\nRun ruff format.\n\n[gone](missing.md)\n',
            encoding='utf-8',
        )
        git_commit_all(tmp_path, 'init')

        report = run_audit([Path('pkg')], repo_root=tmp_path)
        readme = Path('pkg/README.md')
        assert [s.readme for s in report.structural] == [readme]
        assert [link.readme for link in report.links] == [readme]
        assert [p.readme for p in report.policy]      == [readme]

    def test_exempt_dir_is_never_reported_missing(self, tmp_path: Path) -> None:
        """
        Verify docs/plans subdirectories without a README are not reported as missing
        """
        git_init(tmp_path)
        plan_dir = tmp_path / 'docs' / 'plans' / '2026-01'
        plan_dir.mkdir(parents=True)
        (plan_dir / 'a-plan.md').write_text('# A plan\n', encoding='utf-8')
        git_commit_all(tmp_path, 'init')

        report = run_audit([Path('docs/plans')], repo_root=tmp_path)
        assert report.missing == []
