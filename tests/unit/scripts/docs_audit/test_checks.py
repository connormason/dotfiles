"""
Tests for ``scripts/docs_audit/checks.py``
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from scripts.docs_audit.checks import find_missing
from scripts.docs_audit.checks import link_issues
from scripts.docs_audit.checks import policy_issues
from scripts.docs_audit.checks import stale_candidates
from scripts.docs_audit.checks import structural_issues
from scripts.docs_audit.classify import DirClass
from tests.unit.scripts.docs_audit.git_helpers import git_commit_all
from tests.unit.scripts.docs_audit.git_helpers import git_init


class TestStructuralIssues:
    """
    Tests for :func:`scripts.docs_audit.checks.structural_issues`
    """
    def test_flags_missing_breadcrumb_and_downlink(self, tmp_path: Path) -> None:
        """
        Verify a non-root README without a breadcrumb or a child down-link is flagged
        """
        readme = tmp_path / 'README.md'
        readme.write_text('# Title\n\nNo breadcrumb here.\n', encoding='utf-8')
        child = tmp_path / 'sub'
        child.mkdir()
        (child / 'README.md').write_text('# Sub\n', encoding='utf-8')

        issues = structural_issues(readme, children_with_readme=[child], is_repo_root=False)
        assert 'missing breadcrumb'   in issues
        assert any('down-link to sub' in issue for issue in issues)

    def test_repo_root_readme_is_exempt_from_breadcrumb(self, tmp_path: Path) -> None:
        """
        Verify the repo-root README is not flagged for a missing breadcrumb
        """
        readme = tmp_path / 'README.md'
        readme.write_text('# Project\n\nRoot index.\n', encoding='utf-8')
        issues = structural_issues(readme, children_with_readme=[], is_repo_root=True)
        assert 'missing breadcrumb' not in issues

    def test_flags_missing_h1_title(self, tmp_path: Path) -> None:
        """
        Verify a README with no H1 heading is flagged for a missing title
        """
        readme = tmp_path / 'README.md'
        readme.write_text('[Project Root](../README.md) > **pkg**\n\nNo heading at all.\n', encoding='utf-8')
        issues = structural_issues(readme, children_with_readme=[], is_repo_root=False)
        assert 'missing H1 title' in issues

    def test_valid_readme_has_no_issues(self, tmp_path: Path) -> None:
        """
        Verify a properly-formed non-root README with breadcrumb, title, and down-link is clean
        """
        child = tmp_path / 'sub'
        child.mkdir()
        (child / 'README.md').write_text('# Sub\n', encoding='utf-8')

        readme = tmp_path / 'README.md'
        readme.write_text(
            '[Project Root](../README.md) > **pkg**\n\n# Title\n\nSee [sub](sub/README.md).\n',
            encoding='utf-8',
        )
        issues = structural_issues(readme, children_with_readme=[child], is_repo_root=False)
        assert issues == []

    def test_downlink_via_relative_path_is_accepted(self, tmp_path: Path) -> None:
        """
        Verify that a down-link using a relative path to a child README is accepted
        """
        child = tmp_path / 'child'
        child.mkdir()
        (child / 'README.md').write_text('# Child\n', encoding='utf-8')

        readme = tmp_path / 'README.md'
        readme.write_text(
            '[Project Root](../README.md) > **here**\n\n# Here\n\n[child module](child/README.md)\n',
            encoding='utf-8',
        )
        issues = structural_issues(readme, children_with_readme=[child], is_repo_root=False)
        assert not any('down-link' in i for i in issues)


class TestPolicyIssues:
    """
    Tests for :func:`scripts.docs_audit.checks.policy_issues`
    """
    def test_flags_forbidden_pattern(self, tmp_path: Path) -> None:
        """
        Verify a forbidden command pattern is reported with its line number
        """
        readme = tmp_path / 'README.md'
        readme.write_text('# Title\n\nRun ruff format to tidy up.\n', encoding='utf-8')
        matches = policy_issues(readme)
        assert [m.line for m in matches] == [3]
        assert matches[0].text == 'Run ruff format to tidy up.'

    def test_inline_allow_marker_suppresses(self, tmp_path: Path) -> None:
        """
        Verify the inline opt-out marker suppresses a forbidden-pattern match
        """
        readme = tmp_path / 'README.md'
        readme.write_text('# Title\n\nruff format <!-- docs-audit-allow -->\n', encoding='utf-8')
        assert policy_issues(readme) == []

    def test_block_allow_markers_suppress(self, tmp_path: Path) -> None:
        """
        Verify forbidden patterns between block allow markers are suppressed
        """
        readme = tmp_path / 'README.md'
        readme.write_text(
            '# Title\n\n'
            '<!-- docs-audit-allow-start -->\n'
            'ruff format\n'
            '<!-- docs-audit-allow-end -->\n',
            encoding='utf-8',
        )
        assert policy_issues(readme) == []

    def test_matches_after_a_block_are_reported_again(self, tmp_path: Path) -> None:
        """
        Verify scanning resumes after the end marker of an opt-out block
        """
        readme = tmp_path / 'README.md'
        readme.write_text(
            '# Title\n\n'
            '<!-- docs-audit-allow-start -->\n'
            'ruff format\n'
            '<!-- docs-audit-allow-end -->\n'
            'ruff format\n',
            encoding='utf-8',
        )
        assert [m.line for m in policy_issues(readme)] == [6]

    def test_clean_readme_has_no_matches(self, tmp_path: Path) -> None:
        """
        Verify a README with no forbidden patterns returns an empty list
        """
        readme = tmp_path / 'README.md'
        readme.write_text('# Title\n\nUse `uv run ruff check --fix` and `make test`.\n', encoding='utf-8')
        assert policy_issues(readme) == []

    def test_multiple_forbidden_occurrences_all_reported(self, tmp_path: Path) -> None:
        """
        Verify multiple forbidden-pattern occurrences are all reported
        """
        readme = tmp_path / 'README.md'
        readme.write_text('# Title\n\nruff format\nuv run ruff format .\n', encoding='utf-8')
        assert [m.line for m in policy_issues(readme)] == [3, 4]


class TestLinkIssues:
    """
    Tests for :func:`scripts.docs_audit.checks.link_issues`
    """
    def test_flags_broken_relative_link(self, tmp_path: Path) -> None:
        """
        Verify a relative link to a nonexistent path is reported
        """
        readme = tmp_path / 'README.md'
        readme.write_text('# Title\n\n[gone](missing.md)\n', encoding='utf-8')
        broken = link_issues(readme)
        assert any(b.link == 'missing.md' for b in broken)

    def test_external_links_are_ignored(self, tmp_path: Path) -> None:
        """
        Verify http and mailto links are not treated as broken relative links
        """
        readme = tmp_path / 'README.md'
        readme.write_text('# Title\n\n[site](https://example.com) [me](mailto:a@b.c)\n', encoding='utf-8')
        assert link_issues(readme) == []

    def test_other_uri_schemes_are_ignored(self, tmp_path: Path) -> None:
        """
        Verify any scheme-prefixed link (not just http and mailto) is skipped rather than resolved as a path
        """
        readme = tmp_path / 'README.md'
        readme.write_text('# Title\n\n[ssh](ssh://host/repo) [phone](tel:+15555550100)\n', encoding='utf-8')
        assert link_issues(readme) == []

    def test_flags_missing_anchor(self, tmp_path: Path) -> None:
        """
        Verify a link to an existing file with a nonexistent anchor is reported
        """
        readme = tmp_path / 'README.md'
        (tmp_path / 'other.md').write_text('# Other\n', encoding='utf-8')
        readme.write_text('# Title\n\n[x](other.md#does-not-exist)\n', encoding='utf-8')
        broken = link_issues(readme)
        assert any(b.link == 'other.md#does-not-exist' for b in broken)

    def test_valid_anchor_is_accepted(self, tmp_path: Path) -> None:
        """
        Verify a link to a file with a matching explicit anchor tag is not flagged
        """
        readme = tmp_path / 'README.md'
        (tmp_path / 'other.md').write_text(
            '# Other\n\n<a name="section-one"></a>\n\n## Section One\n',
            encoding='utf-8',
        )
        readme.write_text('# Title\n\n[sec](other.md#section-one)\n', encoding='utf-8')
        broken = link_issues(readme)
        assert not any(b.link == 'other.md#section-one' for b in broken)

    def test_heading_slug_anchor_is_accepted(self, tmp_path: Path) -> None:
        """
        Verify a link whose fragment matches a heading's GitHub auto-slug is not flagged
        """
        readme = tmp_path / 'README.md'
        (tmp_path / 'other.md').write_text('# Other\n\n## Section One\n', encoding='utf-8')
        readme.write_text('# Title\n\n[sec](other.md#section-one)\n', encoding='utf-8')
        assert link_issues(readme) == []

    def test_fragment_only_link_resolved_against_self(self, tmp_path: Path) -> None:
        """
        Verify a fragment-only link is resolved against the README itself
        """
        readme = tmp_path / 'README.md'
        readme.write_text('# Title\n\n<a name="intro"></a>\n\n[back](#intro)\n', encoding='utf-8')
        assert link_issues(readme) == []

    def test_inline_code_span_link_is_ignored(self, tmp_path: Path) -> None:
        """
        Verify a link-shaped token inside an inline code span is not reported as broken
        """
        readme = tmp_path / 'README.md'
        readme.write_text(
            '# Title\n\nThe comment footer renders as `Title [#N](url)` text.\n',
            encoding='utf-8',
        )
        assert link_issues(readme) == []

    def test_fenced_code_block_link_is_ignored(self, tmp_path: Path) -> None:
        """
        Verify link-shaped tokens inside a fenced code block are not reported as broken
        """
        readme = tmp_path / 'README.md'
        readme.write_text(
            '# Title\n\n```\nexample: [label](missing/path.md)\n```\n',
            encoding='utf-8',
        )
        assert link_issues(readme) == []

    def test_real_link_outside_code_span_still_flagged(self, tmp_path: Path) -> None:
        """
        Verify a genuinely broken link outside any code span is still reported even when a code span is present
        """
        readme = tmp_path / 'README.md'
        readme.write_text(
            '# Title\n\nFormat is `[#N](url)`.\n\nBut [this](missing/path.md) is real.\n',
            encoding='utf-8',
        )
        broken = link_issues(readme)
        assert [b.link for b in broken] == ['missing/path.md']


@pytest.mark.skipif(not shutil.which('git'), reason='Git not available')
class TestStaleCandidates:
    """
    Tests for :func:`scripts.docs_audit.checks.stale_candidates` using scratch git repos
    """
    def test_stale_readme_is_reported(self, tmp_path: Path) -> None:
        """
        Verify a README that predates a newer source file in the same directory is reported
        """
        git_init(tmp_path)

        pkg = tmp_path / 'pkg'
        pkg.mkdir()
        (pkg / 'README.md').write_text('# Pkg\n', encoding='utf-8')
        git_commit_all(tmp_path, 'add README', date='2026-01-01T00:00:00+00:00')

        (pkg / 'module.py').write_text('# new module\n', encoding='utf-8')
        git_commit_all(tmp_path, 'add module', date='2026-02-01T00:00:00+00:00')

        classified = [(Path('pkg'), DirClass.CODE)]
        findings   = stale_candidates(classified, repo_root=tmp_path)
        assert len(findings) == 1
        assert findings[0].readme             == Path('pkg') / 'README.md'
        assert findings[0].newest_source_file == Path('pkg') / 'module.py'

    def test_up_to_date_readme_is_not_reported(self, tmp_path: Path) -> None:
        """
        Verify a README committed after all source files in its directory is not reported
        """
        git_init(tmp_path)

        pkg = tmp_path / 'pkg'
        pkg.mkdir()
        (pkg / 'module.py').write_text('# module\n', encoding='utf-8')
        git_commit_all(tmp_path, 'add module', date='2026-01-01T00:00:00+00:00')

        (pkg / 'README.md').write_text('# Pkg\n', encoding='utf-8')
        git_commit_all(tmp_path, 'add README after module', date='2026-02-01T00:00:00+00:00')

        classified = [(Path('pkg'), DirClass.CODE)]
        assert stale_candidates(classified, repo_root=tmp_path) == []

    def test_exempt_dirs_are_skipped(self, tmp_path: Path) -> None:
        """
        Verify EXEMPT directories are never reported as stale
        """
        git_init(tmp_path)

        pkg = tmp_path / 'pkg'
        pkg.mkdir()
        (pkg / 'README.md').write_text('# Pkg\n', encoding='utf-8')
        git_commit_all(tmp_path, 'add README', date='2026-01-01T00:00:00+00:00')

        (pkg / 'module.py').write_text('# new\n', encoding='utf-8')
        git_commit_all(tmp_path, 'add module', date='2026-02-01T00:00:00+00:00')

        classified = [(Path('pkg'), DirClass.EXEMPT)]
        assert stale_candidates(classified, repo_root=tmp_path) == []

    def test_uncommitted_readme_is_skipped(self, tmp_path: Path) -> None:
        """
        Verify a README with no commit history is not reported (nothing to compare against)
        """
        git_init(tmp_path)

        pkg = tmp_path / 'pkg'
        pkg.mkdir()
        (pkg / 'module.py').write_text('# module\n', encoding='utf-8')
        git_commit_all(tmp_path, 'add module')
        (pkg / 'README.md').write_text('# Pkg\n', encoding='utf-8')

        classified = [(Path('pkg'), DirClass.CODE)]
        assert stale_candidates(classified, repo_root=tmp_path) == []


class TestFindMissing:
    """
    Tests for :func:`scripts.docs_audit.checks.find_missing`
    """
    def test_code_dir_without_readme_is_reported(self, tmp_path: Path) -> None:
        """
        Verify a CODE directory without a README is returned as a MissingFinding
        """
        (tmp_path / 'pkg').mkdir()
        classified = [(Path('pkg'), DirClass.CODE)]
        findings   = find_missing(classified, repo_root=tmp_path)

        assert len(findings) == 1
        assert findings[0].path == Path('pkg')
        assert findings[0].dir_class is DirClass.CODE

    def test_exempt_dir_is_never_reported(self, tmp_path: Path) -> None:
        """
        Verify an EXEMPT directory is never included in missing findings
        """
        (tmp_path / 'plans').mkdir()
        classified = [(Path('plans'), DirClass.EXEMPT)]
        findings   = find_missing(classified, repo_root=tmp_path)
        assert findings == []

    def test_code_dir_with_readme_is_not_reported(self, tmp_path: Path) -> None:
        """
        Verify a CODE directory that already has a README is not reported
        """
        pkg = tmp_path / 'pkg'
        pkg.mkdir()
        (pkg / 'README.md').write_text('# Pkg\n', encoding='utf-8')

        classified = [(Path('pkg'), DirClass.CODE)]
        findings   = find_missing(classified, repo_root=tmp_path)
        assert findings == []

    def test_data_dir_covered_by_meta_ancestor_readme_is_not_reported(self, tmp_path: Path) -> None:
        """
        Verify a DATA directory whose META ancestor has a README is not reported
        """
        tests_dir = tmp_path / 'tests'
        tests_dir.mkdir()
        (tests_dir / 'README.md').write_text('# Tests\n', encoding='utf-8')
        data_dir = tests_dir / 'fixtures'
        data_dir.mkdir()

        classified = [
            (Path('tests'),              DirClass.META),
            (Path('tests') / 'fixtures', DirClass.DATA),
        ]
        findings = find_missing(classified, repo_root=tmp_path)
        assert not any(f.path == Path('tests') / 'fixtures' for f in findings)

    def test_nested_data_under_data_ancestor_not_reported(self, tmp_path: Path) -> None:
        """
        Verify a nested DATA directory under a DATA ancestor is not reported (top-of-tree rule)
        """
        parent = tmp_path / 'assets'
        parent.mkdir()
        child = parent / 'icons'
        child.mkdir()

        classified = [
            (Path('assets'),           DirClass.DATA),
            (Path('assets') / 'icons', DirClass.DATA),
        ]
        findings = find_missing(classified, repo_root=tmp_path)

        # Neither has a README; the nested one should be covered by its DATA ancestor
        assert not any(f.path == Path('assets') / 'icons' for f in findings)

    def test_code_dir_covered_by_meta_ancestor_readme_is_not_reported(self, tmp_path: Path) -> None:
        """
        Verify a non-DATA (CODE) directory whose nearest README-bearing ancestor is META is not reported
        """
        tests_dir = tmp_path / 'tests'
        tests_dir.mkdir()
        (tests_dir / 'README.md').write_text('# Tests\n', encoding='utf-8')
        unit_dir = tests_dir / 'unit'
        unit_dir.mkdir()
        (unit_dir / 'test_thing.py').write_text('', encoding='utf-8')

        classified = [
            (Path('tests'),          DirClass.META),
            (Path('tests') / 'unit', DirClass.CODE),
        ]
        findings = find_missing(classified, repo_root=tmp_path)
        assert not any(f.path == Path('tests') / 'unit' for f in findings)

    def test_code_dirs_under_meta_dir_without_readme_are_reported(self, tmp_path: Path) -> None:
        """
        Verify a CODE directory is reported (along with its META parent) when no ancestor has a README
        """
        (tmp_path / 'tests' / 'unit').mkdir(parents=True)

        classified = [
            (Path('tests'),          DirClass.META),
            (Path('tests') / 'unit', DirClass.CODE),
        ]
        findings = find_missing(classified, repo_root=tmp_path)
        assert {f.path for f in findings} == {Path('tests'), Path('tests') / 'unit'}

    def test_code_dir_with_code_ancestor_readme_is_still_reported(self, tmp_path: Path) -> None:
        """
        Verify a CODE directory is reported even when a CODE ancestor has a README (code is documented per package)
        """
        pkg_dir = tmp_path / 'pkg'
        pkg_dir.mkdir()
        (pkg_dir / 'README.md').write_text('# pkg\n', encoding='utf-8')
        (pkg_dir / '__init__.py').write_text('', encoding='utf-8')
        sub_dir = pkg_dir / 'sub'
        sub_dir.mkdir()
        (sub_dir / '__init__.py').write_text('', encoding='utf-8')

        classified = [
            (Path('pkg'),         DirClass.CODE),
            (Path('pkg') / 'sub', DirClass.CODE),
        ]
        findings = find_missing(classified, repo_root=tmp_path)
        assert any(f.path == Path('pkg') / 'sub' for f in findings)

    def test_repo_root_readme_does_not_cover_top_level_dirs(self, tmp_path: Path) -> None:
        """
        Verify the repo-root README is an index only and does not exempt top-level directories
        """
        (tmp_path / 'README.md').write_text('# Repo\n', encoding='utf-8')
        (tmp_path / 'pkg').mkdir()

        classified = [
            (Path(),       DirClass.META),
            (Path('pkg'),  DirClass.CODE),
        ]
        findings = find_missing(classified, repo_root=tmp_path)
        assert [f.path for f in findings] == [Path('pkg')]
