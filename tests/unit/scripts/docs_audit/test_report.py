"""
Tests for ``scripts/docs_audit/report.py``
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from scripts.docs_audit.checks import BrokenLink
from scripts.docs_audit.checks import LinkFinding
from scripts.docs_audit.checks import MissingFinding
from scripts.docs_audit.checks import PolicyFinding
from scripts.docs_audit.checks import PolicyMatch
from scripts.docs_audit.checks import StaleFinding
from scripts.docs_audit.checks import StructuralFinding
from scripts.docs_audit.classify import DirClass
from scripts.docs_audit.report import AuditReport
from scripts.docs_audit.report import style
from scripts.docs_audit.report import unstyle

if TYPE_CHECKING:
    import pytest


def _empty_report() -> AuditReport:
    """
    Build an AuditReport with no findings
    """
    return AuditReport(
        scope=['.'],
        missing=[],
        stale_candidates=[],
        structural=[],
        links=[],
        policy=[],
    )


class TestAuditReport:
    """
    Tests for :class:`scripts.docs_audit.report.AuditReport`
    """
    def test_empty_report_has_no_findings(self) -> None:
        """
        Verify an empty report reports no findings and a zeroed summary
        """
        report = _empty_report()

        assert report.has_findings is False
        assert report.summary == {
            'missing': 0, 'stale_candidates': 0, 'structural': 0, 'links': 0, 'policy': 0,
        }

    def test_json_envelope_has_summary(self) -> None:
        """
        Verify the JSON envelope round-trips and includes the summary map and scope
        """
        envelope = json.loads(_empty_report().to_json())

        assert envelope['summary']['missing'] == 0
        assert envelope['scope']              == ['.']
        assert 'coverage' not in envelope

    def test_to_text_runs_without_color(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Verify to_text renders a plain string containing the scope header when NO_COLOR is set
        """
        monkeypatch.setenv('NO_COLOR', '1')
        text = _empty_report().to_text()
        assert 'docs-audit' in text
        assert '\033[' not in text

    def test_non_empty_report_has_findings(self) -> None:
        """
        Verify has_findings is True and summary counts the finding when a category is non-empty
        """
        report = _empty_report()
        report.missing = [MissingFinding(path=Path('src/foo'), dir_class=DirClass.CODE)]

        assert report.has_findings       is True
        assert report.summary['missing'] == 1

    def test_to_text_renders_a_finding(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Verify to_text renders the path of a missing finding when NO_COLOR is set
        """
        monkeypatch.setenv('NO_COLOR', '1')
        report = _empty_report()
        report.missing = [MissingFinding(path=Path('src/foo'), dir_class=DirClass.CODE)]

        assert 'src/foo' in report.to_text()

    @staticmethod
    def _fully_populated_report() -> AuditReport:
        """
        Build an AuditReport with one finding in every category
        """
        return AuditReport(
            scope=['.'],
            missing=[
                MissingFinding(
                    path=Path('pkg/data'),
                    dir_class=DirClass.DATA,
                ),
            ],
            stale_candidates=[
                StaleFinding(
                    readme=Path('pkg/README.md'),
                    readme_mtime='2026-06-01T00:00:00+00:00',
                    newest_source='2026-06-20T00:00:00+00:00',
                    newest_source_file=Path('pkg/core.py'),
                ),
            ],
            structural=[
                StructuralFinding(
                    readme=Path('pkg/README.md'),
                    issues=['missing breadcrumb', 'no H1'],
                ),
            ],
            links=[
                LinkFinding(
                    readme=Path('pkg/README.md'),
                    broken=[
                        BrokenLink(
                            link='../gone.md',
                            reason='path not found',
                        ),
                    ],
                ),
            ],
            policy=[
                PolicyFinding(
                    readme=Path('pkg/README.md'),
                    matches=[
                        PolicyMatch(
                            pattern='ruff format',
                            line=7,
                            text='run ruff format',
                        ),
                    ],
                ),
            ],
        )

    def test_to_dict_serializes_every_category(self) -> None:
        """
        Verify to_dict renders each finding category with its documented field names
        """
        envelope = self._fully_populated_report().to_dict()

        assert envelope['missing'] == [
            {'path': 'pkg/data', 'class': 'data'},
        ]

        assert envelope['stale_candidates'] == [{
            'path':               'pkg/README.md',
            'readme_mtime':       '2026-06-01T00:00:00+00:00',
            'newest_source':      '2026-06-20T00:00:00+00:00',
            'newest_source_file': 'pkg/core.py',
        }]

        assert envelope['structural'] == [{
            'path':   'pkg/README.md',
            'issues': ['missing breadcrumb', 'no H1'],
        }]

        assert envelope['links'] == [{
            'path':   'pkg/README.md',
            'broken': [{'link': '../gone.md', 'reason': 'path not found'}],
        }]

        assert envelope['policy'] == [{
            'path':    'pkg/README.md',
            'matches': [{'pattern': 'ruff format', 'line': 7, 'text': 'run ruff format'}],
        }]

        assert envelope['summary'] == {
            'missing': 1, 'stale_candidates': 1, 'structural': 1, 'links': 1, 'policy': 1,
        }

    def test_to_text_renders_every_category(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Verify to_text renders a detail line for each finding category when NO_COLOR is set
        """
        monkeypatch.setenv('NO_COLOR', '1')
        text = self._fully_populated_report().to_text()

        assert 'pkg/data — data'             in text
        assert 'newer source: pkg/core.py'   in text
        assert 'missing breadcrumb; no H1'   in text
        assert '../gone.md (path not found)' in text
        assert 'ruff format@7'               in text

    def test_to_text_emits_ansi_without_no_color(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Verify to_text emits ANSI escape sequences when NO_COLOR is absent
        """
        monkeypatch.delenv('NO_COLOR', raising=False)
        text = self._fully_populated_report().to_text()
        assert '\033[' in text


class TestStyleHelpers:
    """
    Tests for :func:`scripts.docs_audit.report.style` and :func:`scripts.docs_audit.report.unstyle`
    """
    def test_style_round_trips_through_unstyle(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Verify unstyle strips every sequence that style adds
        """
        monkeypatch.delenv('NO_COLOR', raising=False)
        styled = style('docs-audit', fg='cyan', bold=True, dim=True)

        assert styled != 'docs-audit'
        assert unstyle(styled) == 'docs-audit'

    def test_style_is_a_no_op_with_no_color(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Verify style returns the text unchanged when NO_COLOR is set
        """
        monkeypatch.setenv('NO_COLOR', '1')
        assert style('plain', fg='red', bold=True) == 'plain'

    def test_style_without_attributes_leaves_text_alone(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Verify style with no color or modifier does not append a stray reset sequence
        """
        monkeypatch.delenv('NO_COLOR', raising=False)
        assert style('plain') == 'plain'
