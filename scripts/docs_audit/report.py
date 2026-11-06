"""
Aggregate audit findings into an :class:`AuditReport` and render it as styled text or JSON.

Console styling follows ``.claude/rules/script-style.md`` (semantic color theme, status emojis). The styling helpers
are defined here so the prek hook wrapper can reuse them without duplicating ANSI handling.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING
from typing import Any
from typing import TypedDict

if TYPE_CHECKING:
    from scripts.docs_audit.checks import LinkFinding
    from scripts.docs_audit.checks import MissingFinding
    from scripts.docs_audit.checks import PolicyFinding
    from scripts.docs_audit.checks import StaleFinding
    from scripts.docs_audit.checks import StructuralFinding

__all__ = [
    'AuditReport',
    'AuditReportDict',
    'AuditReportSummaryDict',
    'style',
    'unstyle',
]


# ==================================================================================================
# Styling
# ==================================================================================================


ANSI_COLORS: dict[str, int] = {
    'black':   30, 'bright_black':   90,
    'red':     31, 'bright_red':     91,
    'green':   32, 'bright_green':   92,
    'yellow':  33, 'bright_yellow':  93,
    'blue':    34, 'bright_blue':    94,
    'magenta': 35, 'bright_magenta': 95,
    'cyan':    36, 'bright_cyan':    96,
    'white':   37, 'bright_white':   97,
    'reset':   39,
}
ANSI_RESET_ALL = '\033[0m'


def style(text: Any, *, fg: str | None = None, bold: bool | None = None, dim: bool | None = None) -> str:
    """
    Style text with ANSI codes.

    :param text: the value to render
    :param fg: optional foreground color name
    :param bold: enable bold when True
    :param dim: enable dim when True
    :return: the styled string
    """
    text = str(text)
    if os.environ.get('NO_COLOR'):
        return text

    bits: list[str] = []
    if fg is not None:
        bits.append(f'\033[{ANSI_COLORS[fg]}m')
    if bold:
        bits.append('\033[1m')
    if dim:
        bits.append('\033[2m')

    bits.append(text)
    if bits[:-1]:
        bits.append(ANSI_RESET_ALL)
    return ''.join(bits)


def unstyle(text: str) -> str:
    """
    Strip ANSI styling sequences from a string.

    :param text: styled text
    :return: text with ANSI sequences removed
    """
    return re.sub(r'\033\[[;?0-9]*[a-zA-Z]', '', text)


# ==================================================================================================
# Report
# ==================================================================================================


class AuditReportSummaryDict(TypedDict):
    """
    Per-category finding counts. Dict schema for return value of :meth:`AuditReport.summary`.
    """
    missing:          int
    stale_candidates: int
    structural:       int
    links:            int
    policy:           int


class AuditReportDict(TypedDict):
    """
    JSON-serializable dict representation of :class:`AuditReport` (returned by :meth:`AuditReport.to_dict`)
    """
    scope:            list[str]
    missing:          list[MissingFinding.MissingFindingDict]
    stale_candidates: list[StaleFinding.StaleFindingDict]
    structural:       list[StructuralFinding.StructuralFindingDict]
    links:            list[LinkFinding.LinkFindingDict]
    policy:           list[PolicyFinding.PolicyFindingDict]
    summary:          AuditReportSummaryDict


@dataclass
class AuditReport:
    """
    Aggregated deterministic docs-audit findings.
    """
    scope:            list[str]
    missing:          list[MissingFinding]
    stale_candidates: list[StaleFinding]
    structural:       list[StructuralFinding]
    links:            list[LinkFinding]
    policy:           list[PolicyFinding]

    @property
    def has_findings(self) -> bool:
        """
        Whether any finding category is non-empty.

        :return: True when the report contains at least one finding
        """
        return bool(
            self.missing
            or self.stale_candidates
            or self.structural
            or self.links
            or self.policy
        )

    @property
    def summary(self) -> AuditReportSummaryDict:
        """
        Per-category finding counts.

        :return: mapping of category name to count
        """
        return {
            'missing':          len(self.missing),
            'stale_candidates': len(self.stale_candidates),
            'structural':       len(self.structural),
            'links':            len(self.links),
            'policy':           len(self.policy),
        }

    def to_dict(self) -> AuditReportDict:
        """
        Get audit report data as a dictionary.

        :return: JSON-encodable dict
        """
        return {
            'scope':            self.scope,
            'missing':          [m.to_dict() for m in self.missing],
            'stale_candidates': [s.to_dict() for s in self.stale_candidates],
            'structural':       [s.to_dict() for s in self.structural],
            'links':            [l.to_dict() for l in self.links],
            'policy':           [p.to_dict() for p in self.policy],
            'summary':          self.summary,
        }

    def to_json(self, *, indent: int | None = 2, **kwargs: Any) -> str:
        """
        Render the report as the documented JSON envelope.

        :param indent: JSON indent width (passed through to :func:`json.dumps`, default: 2)
        :return: a JSON string
        """
        return json.dumps(self.to_dict(), indent=indent, **kwargs)

    def to_text(self) -> str:
        """
        Render the report as a styled human-readable string.

        :return: the report text (ANSI-styled unless NO_COLOR is set)
        """
        out: list[str] = [
            style(f"docs-audit — {', '.join(self.scope)}", fg='cyan', bold=True),
        ]

        def header(emoji: str, name: str, count: int) -> str:
            color = 'bright_green' if count == 0 else 'bright_yellow'
            return f'{emoji} {style(f"{name} ({count})", fg=color, bold=True)}'

        out.append(header('🔴', 'Missing', len(self.missing)))
        out.extend(f'   {style(m.path.as_posix(), fg="magenta")} — {m.dir_class.value}' for m in self.missing)

        out.append(header('🟡', 'Stale candidates', len(self.stale_candidates)))
        for s in self.stale_candidates:
            newest = s.newest_source_file.as_posix()
            out.append(f'   {style(s.readme.as_posix(), fg="magenta")} — newer source: {newest}')

        out.append(header('🟡', 'Structural', len(self.structural)))
        out.extend(f'   {style(st.readme.as_posix(), fg="magenta")} — {"; ".join(st.issues)}' for st in self.structural)

        out.append(header('🔴', 'Links', len(self.links)))
        for link_finding in self.links:
            detail = '; '.join(f'{b.link} ({b.reason})' for b in link_finding.broken)
            out.append(f'   {style(link_finding.readme.as_posix(), fg="magenta")} — {detail}')

        out.append(header('🔴', 'Policy', len(self.policy)))
        for p in self.policy:
            detail = '; '.join(f'{m.pattern}@{m.line}' for m in p.matches)
            out.append(f'   {style(p.readme.as_posix(), fg="magenta")} — {detail}')

        return '\n'.join(out)
