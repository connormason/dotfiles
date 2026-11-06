"""
docs-audit package: discover, classify, and check per-directory READMEs.
"""
from __future__ import annotations

from scripts.docs_audit.audit import run_audit
from scripts.docs_audit.checks import BrokenLink
from scripts.docs_audit.checks import LinkFinding
from scripts.docs_audit.checks import MissingFinding
from scripts.docs_audit.checks import PolicyFinding
from scripts.docs_audit.checks import PolicyMatch
from scripts.docs_audit.checks import StaleFinding
from scripts.docs_audit.checks import StructuralFinding
from scripts.docs_audit.classify import DirClass
from scripts.docs_audit.report import AuditReport

__all__ = [
    'AuditReport',
    'BrokenLink',
    'DirClass',
    'LinkFinding',
    'MissingFinding',
    'PolicyFinding',
    'PolicyMatch',
    'StaleFinding',
    'StructuralFinding',
    'run_audit',
]
