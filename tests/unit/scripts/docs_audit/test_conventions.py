"""
Tests for ``scripts/docs_audit/conventions.py``
"""
from __future__ import annotations

import pytest

from scripts.docs_audit.conventions import EXCLUDE_SEGMENTS
from scripts.docs_audit.conventions import EXCLUDE_SUFFIXES
from scripts.docs_audit.conventions import EXCLUDE_TOP_LEVEL
from scripts.docs_audit.conventions import FORBIDDEN_PATTERNS
from scripts.docs_audit.conventions import META_DIR_NAMES
from scripts.docs_audit.conventions import PLACEHOLDER_FILENAMES
from scripts.docs_audit.conventions import PLANS_EXEMPT_PARTS
from scripts.docs_audit.conventions import POLICY_ALLOW_END
from scripts.docs_audit.conventions import POLICY_ALLOW_INLINE
from scripts.docs_audit.conventions import POLICY_ALLOW_START


class TestConventions:
    """
    Tests for the docs-audit convention constants
    """
    def test_meta_dirs(self) -> None:
        """
        Verify the meta-directory set is docs, scripts, and tests only
        """
        assert META_DIR_NAMES == frozenset({'docs', 'scripts', 'tests'})

    @pytest.mark.parametrize(
        'segment',
        ['.git', '.github', '.ctx', '.claude', '.config', '.ssh', '.hammerspoon', '.vscode', '.nox', '__pycache__'],
    )
    def test_hidden_and_cache_dirs_are_excluded_at_any_depth(self, segment: str) -> None:
        """
        Verify tooling, cache, and stow-payload hidden directories are excluded from discovery
        """
        assert segment in EXCLUDE_SEGMENTS

    def test_archive_is_a_top_level_only_exclude(self) -> None:
        """
        Verify the frozen archive is excluded at the repo root only, so a nested directory named archive stays auditable
        """
        assert 'archive'     in EXCLUDE_TOP_LEVEL
        assert 'archive' not in EXCLUDE_SEGMENTS

    def test_build_artifacts_are_top_level_only_excludes(self) -> None:
        """
        Verify build/dist/site are top-level-only excludes, not any-depth segments

        A nested source package named ``build`` must remain auditable, so ``build`` must NOT be in the any-depth
        segment set.
        """
        assert 'build'     in EXCLUDE_TOP_LEVEL
        assert 'dist'      in EXCLUDE_TOP_LEVEL
        assert 'site'      in EXCLUDE_TOP_LEVEL
        assert 'build' not in EXCLUDE_SEGMENTS
        assert 'dist'  not in EXCLUDE_SEGMENTS

    def test_gitkeep_is_a_placeholder_filename(self) -> None:
        """
        Verify .gitkeep is recognized as a content-free placeholder
        """
        assert '.gitkeep' in PLACEHOLDER_FILENAMES

    def test_egg_info_is_an_excluded_suffix(self) -> None:
        """
        Verify .egg-info directories are excluded via suffix matching
        """
        assert '.egg-info' in EXCLUDE_SUFFIXES

    def test_plans_exempt_parts(self) -> None:
        """
        Verify the planning-artifacts path exemption tuple is correct
        """
        assert PLANS_EXEMPT_PARTS == ('docs', 'plans')

    def test_forbidden_patterns_flag_the_formatter(self) -> None:
        """
        Verify the banned code formatter invocation is matched
        """
        assert any(p.search('run ruff format now') for p in FORBIDDEN_PATTERNS)
        assert any(p.search('uv run ruff format .') for p in FORBIDDEN_PATTERNS)

    @pytest.mark.parametrize(
        'text',
        [
            'uv run ruff check --fix',
            'ruff formatting is off',
            'uv run pytest',
            'hatch build',
        ],
    )
    def test_forbidden_patterns_do_not_flag_allowed_commands(self, text: str) -> None:
        """
        Verify the linter and unrelated commands are not matched by the forbidden patterns
        """
        assert not any(p.search(text) for p in FORBIDDEN_PATTERNS)

    def test_policy_allow_inline_marker(self) -> None:
        """
        Verify the inline opt-out marker string is correct
        """
        assert POLICY_ALLOW_INLINE == '<!-- docs-audit-allow -->'

    def test_policy_allow_block_markers(self) -> None:
        """
        Verify the block opt-out start/end markers are correct
        """
        assert POLICY_ALLOW_START == '<!-- docs-audit-allow-start -->'
        assert POLICY_ALLOW_END   == '<!-- docs-audit-allow-end -->'
