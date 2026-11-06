"""
The five deterministic audit checks plus their finding dataclasses.

Each check is a pure function: it takes paths (and, where needed, a repo root and the classified directory set) and
returns structured findings. None mutate global state, so each is independently testable.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from scripts.docs_audit.classify import DirClass
from scripts.docs_audit.conventions import FORBIDDEN_PATTERNS
from scripts.docs_audit.conventions import POLICY_ALLOW_END
from scripts.docs_audit.conventions import POLICY_ALLOW_INLINE
from scripts.docs_audit.conventions import POLICY_ALLOW_START

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    'BrokenLink',
    'LinkFinding',
    'MissingFinding',
    'PolicyFinding',
    'PolicyMatch',
    'StaleFinding',
    'StructuralFinding',
    'find_missing',
    'link_issues',
    'policy_issues',
    'stale_candidates',
    'structural_issues',
]

# ==============================================================================
# Finding dataclasses
# ==============================================================================


@dataclass(frozen=True)
class MissingFinding:
    """
    A directory that is required to have a README but has none.
    """
    path:      Path
    dir_class: DirClass


@dataclass(frozen=True)
class StaleFinding:
    """
    A README whose commit time predates the newest source file in its directory.
    """
    readme:             Path
    readme_mtime:       str
    newest_source:      str
    newest_source_file: Path


@dataclass(frozen=True)
class StructuralFinding:
    """
    A README with one or more structural issues (breadcrumb, title, down-links).
    """
    readme: Path
    issues: list[str]


@dataclass(frozen=True)
class BrokenLink:
    """
    A single broken relative link or unresolved anchor within a README.
    """
    link:   str
    reason: str


@dataclass(frozen=True)
class LinkFinding:
    """
    A README with one or more broken links.
    """
    readme: Path
    broken: list[BrokenLink]


@dataclass(frozen=True)
class PolicyMatch:
    """
    A single forbidden-pattern match within a README.
    """
    pattern: str
    line:    int
    text:    str


@dataclass(frozen=True)
class PolicyFinding:
    """
    A README containing one or more forbidden command patterns.
    """
    readme:  Path
    matches: list[PolicyMatch]


# ==============================================================================
# Content-policy check
# ==============================================================================


def policy_issues(readme: Path) -> list[PolicyMatch]:
    """
    Scan a README for forbidden command patterns (see :data:`conventions.FORBIDDEN_PATTERNS`).

    Lines may opt out of the scan: a line containing :data:`conventions.POLICY_ALLOW_INLINE` is skipped, and every line
    between :data:`conventions.POLICY_ALLOW_START` and :data:`conventions.POLICY_ALLOW_END` is skipped. This lets docs
    that must legitimately reference an anti-pattern (e.g. documentation of this check) exempt those lines.

    :param readme: path to the README file
    :return: one match per forbidden pattern occurrence, with line number and stripped line text
    """
    matches: list[PolicyMatch] = []

    in_allow_block = False
    text = readme.read_text(encoding='utf-8', errors='replace')
    for lineno, line in enumerate(text.splitlines(), start=1):
        if POLICY_ALLOW_START in line:
            in_allow_block = True
            continue
        if POLICY_ALLOW_END in line:
            in_allow_block = False
            continue
        if in_allow_block or (POLICY_ALLOW_INLINE in line):
            continue

        matches.extend(
            PolicyMatch(pattern=pattern.pattern, line=lineno, text=line.strip())
            for pattern in FORBIDDEN_PATTERNS
            if pattern.search(line)
        )

    return matches


# ==============================================================================
# Structural check
# ==============================================================================

LINK_RE:           re.Pattern[str] = re.compile(r'\[[^\]]*\]\(([^)]+)\)')
BREADCRUMB_PREFIX: str             = '[Project Root]'
SCHEME_RE:         re.Pattern[str] = re.compile(r'^[a-zA-Z][a-zA-Z0-9+.\-]*:')


def _links_to(links: set[str], base: Path, target: Path) -> bool:
    """
    Return whether any extracted link, resolved relative to ``base``, points at ``target``.

    :param links: the set of raw link targets extracted from a README
    :param base: the directory the README lives in
    :param target: the absolute path the link should resolve to
    :return: True when at least one link resolves to ``target``
    """
    for link in links:
        path_part = link.split('#', 1)[0]
        if not path_part:
            continue
        try:
            if (base / path_part).resolve() == target.resolve():
                return True
        except OSError:
            continue
    return False


def structural_issues(
    readme: Path,
    *,
    children_with_readme: Sequence[Path],
    is_repo_root: bool,
) -> list[str]:
    """
    Check a README for structural completeness.

    :param readme: absolute path to the README file
    :param children_with_readme: absolute paths of immediate child directories that themselves have a README
    :param is_repo_root: whether this README is the repo-root README (exempt from the breadcrumb requirement)
    :return: a list of human-readable issue strings (empty when the README is structurally complete)
    """
    issues: list[str] = []

    text  = readme.read_text(encoding='utf-8', errors='replace')
    lines = text.splitlines()

    first_non_empty = next((ln.strip() for ln in lines if ln.strip()), '')
    if (not is_repo_root) and (not first_non_empty.startswith(BREADCRUMB_PREFIX)):
        issues.append('missing breadcrumb')

    if not any(ln.lstrip().startswith('# ') for ln in lines):
        issues.append('missing H1 title')

    links = set(LINK_RE.findall(text))
    base  = readme.parent
    issues.extend(
        f'no down-link to {child.name}/README.md'
        for child in children_with_readme
        if not _links_to(links, base, child / 'README.md')
    )

    return issues


# ==============================================================================
# Link / anchor check
# ==============================================================================

HEADING_RE:    re.Pattern[str] = re.compile(r'^#{1,6}\s+(.*)$')
ANCHOR_TAG_RE: re.Pattern[str] = re.compile(r'<a name="([^"]+)">')

FENCE_RE:       re.Pattern[str] = re.compile(r'^[ \t]*(`{3,}|~{3,})')
INLINE_CODE_RE: re.Pattern[str] = re.compile(r'(?P<ticks>`+)(?:(?!(?P=ticks)).)*?(?P=ticks)', re.DOTALL)


def _strip_code_spans(text: str) -> str:
    """
    Blank out fenced code blocks and inline code spans so link extraction ignores links that are merely illustrative.

    A token like ``[#N](url)`` written inside a backtick span (to document a link's *format*) is not a navigable
    Markdown link, so it must not be reported as broken. Fenced blocks and inline spans are replaced with blank
    content while preserving line structure.

    :param text: the Markdown source
    :return: the text with fenced code blocks and inline code spans removed
    """
    out:        list[str] = []
    fence_char: str | None = None
    for line in text.splitlines():
        if fence_char is None:
            if (match := FENCE_RE.match(line)) is not None:
                fence_char = match.group(1)[0]
                out.append('')
            else:
                out.append(INLINE_CODE_RE.sub('', line))
        else:
            out.append('')
            if line.lstrip().startswith(fence_char * 3):
                fence_char = None
    return '\n'.join(out)


def _github_slug(heading_text: str) -> str:
    """
    Compute the GitHub-style anchor slug for a Markdown heading's text.

    Mirrors GitHub's heading-slug algorithm (which ``mdformat-toc --slug=github`` also targets): strip inline HTML,
    lowercase, drop punctuation except word characters / spaces / hyphens, then replace spaces with hyphens.

    :param heading_text: the heading text (the portion after the leading ``#`` markers)
    :return: the GitHub anchor slug
    """
    text = re.sub(r'<[^>]+>', '', heading_text)
    text = text.strip().lower()
    text = re.sub(r'[^\w\s-]', '', text)
    return text.strip().replace(' ', '-')


def _anchors_in(text: str) -> set[str]:
    """
    Collect every anchor name a fragment link may target within a Markdown file.

    Includes explicit ``<a name="...">`` anchors and the GitHub auto-slug of every heading, so the link check accepts
    both the repo's explicit-anchor convention and plain GitHub heading anchors.

    :param text: the target file's contents
    :return: the set of valid anchor names
    """
    anchors: set[str] = set(ANCHOR_TAG_RE.findall(text))
    for line in text.splitlines():
        if (match := HEADING_RE.match(line)) and (slug := _github_slug(match.group(1))):
            anchors.add(slug)
    return anchors


def link_issues(readme: Path) -> list[BrokenLink]:
    """
    Check a README's relative links and explicit anchors.

    Skips links with a URI scheme (``http(s)://``, ``mailto:``, etc.), and links that appear inside fenced code blocks
    or inline code spans (illustrative format examples, not navigable links). For ``path#frag`` links the path part is
    resolved
    relative to the README's directory (flagged if it does not exist); when a fragment is present, the target file
    must contain either an explicit ``<a name="frag">`` anchor (the repo's anchor convention, which ``mdformat-toc``
    emits) or a heading whose GitHub auto-slug equals ``frag``.

    :param readme: absolute path to the README file
    :return: a list of broken links (empty when all links resolve)
    """
    text = _strip_code_spans(readme.read_text(encoding='utf-8', errors='replace'))

    broken: list[BrokenLink] = []
    for raw in LINK_RE.findall(text):
        link = raw.strip()
        if SCHEME_RE.match(link):
            continue

        path_part, _, frag = link.partition('#')
        if path_part:
            target = readme.parent / path_part
            if not target.exists():
                broken.append(BrokenLink(link=link, reason='path not found'))
                continue
        else:
            target = readme

        if frag:
            target_text = target.read_text(encoding='utf-8', errors='replace') if target.is_file() else ''
            if frag not in _anchors_in(target_text):
                broken.append(BrokenLink(link=link, reason=f"anchor '{frag}' not found"))

    return broken


# ==============================================================================
# Missing-README check
# ==============================================================================


def _nearest_classified_ancestor(rel_dir: Path, classes: dict[Path, DirClass]) -> DirClass | None:
    """
    Walk up from ``rel_dir`` and return the class of its nearest ancestor present in ``classes``.

    :param rel_dir: the directory whose ancestors to inspect
    :param classes: mapping of repo-relative directory to its class
    :return: the nearest ancestor's class, or None when no ancestor is classified
    """
    parent = rel_dir.parent
    while True:
        if parent in classes:
            return classes[parent]
        if parent == parent.parent:
            return None
        parent = parent.parent


def _nearest_readme_ancestor(rel_dir: Path, classes: dict[Path, DirClass], repo_root: Path) -> DirClass | None:
    """
    Return the class of ``rel_dir``'s nearest ancestor that has a README, stopping before the repo root.

    The repo root is deliberately excluded: its README is a master index, not a per-subtree index, so it must not
    exempt every top-level package from the per-directory README requirement.

    :param rel_dir: the directory whose ancestors to inspect
    :param classes: mapping of repo-relative directory to its class
    :param repo_root: absolute path to the repository root
    :return: the class of the nearest README-bearing ancestor, or None when none exists below the repo root
    """
    parent = rel_dir.parent
    while (parent != Path()) and (parent != parent.parent):
        if (parent in classes) and (repo_root / parent / 'README.md').exists():
            return classes[parent]
        parent = parent.parent
    return None


def find_missing(
    classified: Sequence[tuple[Path, DirClass]],
    *,
    repo_root: Path,
) -> list[MissingFinding]:
    """
    Report directories that are required to have a README but have none.

    EXEMPT directories are never reported. A directory is considered already covered (and is not reported) when:

    - it is DATA and its nearest classified ancestor is also DATA (the top-of-tree rule -- only the tree top needs a
      README), or
    - it is DATA and any ancestor below the repo root has a README (covers resource trees rooted inside a documented
      Python package, e.g. ``src/pkg/data/``), or
    - it is non-DATA and its nearest README-bearing ancestor is a META or DATA directory (an index README that maps its
      whole subtree, e.g. ``tests/`` or ``examples/``). A CODE ancestor does not cover descendants, since code
      packages are documented per package.

    :param classified: pairs of (repo-relative directory, class)
    :param repo_root: absolute path to the repository root
    :return: one finding per directory that should have a README and does not
    """
    classes: dict[Path, DirClass] = dict(classified)

    findings: list[MissingFinding] = []
    for rel_dir, cls in classified:
        if cls is DirClass.EXEMPT:
            continue
        if (repo_root / rel_dir / 'README.md').exists():
            continue

        cover = _nearest_readme_ancestor(rel_dir, classes, repo_root)

        if cls is DirClass.DATA:
            if (_nearest_classified_ancestor(rel_dir, classes) is DirClass.DATA) or (cover is not None):
                continue
        elif cover in (DirClass.META, DirClass.DATA):
            continue

        findings.append(MissingFinding(path=rel_dir, dir_class=cls))

    return findings


# ==============================================================================
# Stale-candidate check (timestamp only)
# ==============================================================================


def _git_commit_time(repo_root: Path, rel_path: Path) -> tuple[int, str] | None:
    """
    Return the most recent commit time for ``rel_path`` as ``(epoch_seconds, iso8601)``.

    Epoch seconds (``%ct``) give a timezone-correct ordering key; the ISO-8601 string (``%cI``) is kept for display.

    :param repo_root: absolute path to the repository root
    :param rel_path: repo-relative path to inspect
    :return: a ``(epoch_seconds, iso8601)`` tuple, or None when the path has no commit history
    """
    result = subprocess.run(
        ['git', 'log', '-1', '--format=%ct %cI', '--', rel_path.as_posix()],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    out = result.stdout.strip()
    if not out:
        return None

    epoch_str, _, iso = out.partition(' ')
    return int(epoch_str), iso


def stale_candidates(classified: Sequence[tuple[Path, DirClass]], *, repo_root: Path) -> list[StaleFinding]:
    """
    Report READMEs whose commit time predates the newest source file in the same directory.

    This is a cheap timestamp heuristic only; content-drift confirmation is left to the LLM. EXEMPT directories and
    directories without a committed README are skipped.

    :param classified: pairs of (repo-relative directory, class)
    :param repo_root: absolute path to the repository root
    :return: one finding per README that is older than its newest sibling source file
    """
    findings: list[StaleFinding] = []

    for rel_dir, cls in classified:
        if cls is DirClass.EXEMPT:
            continue

        readme_rel = rel_dir / 'README.md'
        if not (repo_root / readme_rel).exists():
            continue

        readme_time = _git_commit_time(repo_root, readme_rel)
        if readme_time is None:
            continue

        readme_epoch, readme_iso = readme_time

        newest_epoch: int | None  = None
        newest_iso:   str | None  = None
        newest_file:  Path | None = None

        for child in sorted((repo_root / rel_dir).glob('*')):
            if child.is_dir() or (child.name == 'README.md'):
                continue

            child_rel  = child.relative_to(repo_root)
            child_time = _git_commit_time(repo_root, child_rel)
            if child_time is None:
                continue

            child_epoch, child_iso = child_time
            if (newest_epoch is None) or (child_epoch > newest_epoch):
                newest_epoch, newest_iso, newest_file = child_epoch, child_iso, child_rel

        if (
            (newest_epoch is not None)
            and (newest_file is not None)
            and (newest_iso is not None)
            and (newest_epoch > readme_epoch)
        ):
            findings.append(
                StaleFinding(
                    readme=readme_rel,
                    readme_mtime=readme_iso,
                    newest_source=newest_iso,
                    newest_source_file=newest_file,
                )
            )

    return findings
