"""
Orchestrate the deterministic docs audit: discover, classify, run every check, and assemble an AuditReport.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from scripts.docs_audit.checks import LinkFinding
from scripts.docs_audit.checks import PolicyFinding
from scripts.docs_audit.checks import StructuralFinding
from scripts.docs_audit.checks import find_missing
from scripts.docs_audit.checks import link_issues
from scripts.docs_audit.checks import policy_issues
from scripts.docs_audit.checks import stale_candidates
from scripts.docs_audit.checks import structural_issues
from scripts.docs_audit.classify import DirClass
from scripts.docs_audit.classify import classify
from scripts.docs_audit.discover import discover
from scripts.docs_audit.report import AuditReport

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    'run_audit',
]


def run_audit(scopes: Sequence[Path], *, repo_root: Path) -> AuditReport:
    """
    Run the full deterministic audit over the given scopes.

    :param scopes: repo-relative scope paths to audit (use ``[Path('.')]`` for the whole repo)
    :param repo_root: absolute path to the repository root
    :return: an :class:`AuditReport` aggregating every finding category
    """
    dirs       = discover(scopes, repo_root=repo_root)
    classified = [(rel_dir, classify(rel_dir, repo_root=repo_root)) for rel_dir in dirs]

    have_readme: set[Path] = {
        rel_dir for rel_dir, _ in classified
        if (repo_root / rel_dir / 'README.md').exists()
    }

    structural: list[StructuralFinding] = []
    links:      list[LinkFinding]       = []
    policy:     list[PolicyFinding]     = []

    for rel_dir, cls in classified:
        # EXEMPT directories (e.g. docs/plans) are index-free by convention, so any README in them is not held to the
        # navigation contract
        if cls is DirClass.EXEMPT:
            continue

        readme_abs = repo_root / rel_dir / 'README.md'
        if not readme_abs.exists():
            continue

        children: list[Path] = [
            repo_root / child
            for child in have_readme
            if (child.parent == rel_dir) and (child != rel_dir)
        ]

        if issues := structural_issues(
            readme_abs,
            children_with_readme=children,
            is_repo_root=(rel_dir == Path()),
        ):
            structural.append(StructuralFinding(readme=rel_dir / 'README.md', issues=issues))

        if broken := link_issues(readme_abs):
            links.append(LinkFinding(readme=rel_dir / 'README.md', broken=broken))

        if matches := policy_issues(readme_abs):
            policy.append(PolicyFinding(readme=rel_dir / 'README.md', matches=matches))

    return AuditReport(
        scope=[scope.as_posix() for scope in scopes],
        missing=find_missing(classified, repo_root=repo_root),
        stale_candidates=stale_candidates(classified, repo_root=repo_root),
        structural=structural,
        links=links,
        policy=policy,
    )
