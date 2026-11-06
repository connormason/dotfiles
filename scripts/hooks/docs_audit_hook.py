#!/usr/bin/env python3
"""
Pre-commit hook: validate changed README.md files.

Runs the file-scoped subset of the docs audit — structural, link/anchor, and content-policy checks — over the changed
``README.md`` files prek passes in. It deliberately skips the missing-README and stale-candidate checks: a changed-files
hook cannot see a directory whose README does not exist, and a README always looks "stale" mid-commit (the source change
is committed before the README is updated). Non-zero exit blocks the commit.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure the repo root is importable when prek executes this file directly
# parents[0]=hooks, parents[1]=scripts, parents[2]=<repo root>
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.docs_audit.checks import link_issues
from scripts.docs_audit.checks import policy_issues
from scripts.docs_audit.checks import structural_issues
from scripts.docs_audit.conventions import EXCLUDE_SEGMENTS
from scripts.docs_audit.conventions import EXCLUDE_SUFFIXES
from scripts.docs_audit.conventions import EXCLUDE_TOP_LEVEL
from scripts.docs_audit.report import style

# Resolved from this file's location rather than `git rev-parse`: git exports GIT_DIR while committing from a linked
# worktree, which makes `--show-toplevel` report the current directory instead of the repo root.
REPO_ROOT = Path(__file__).resolve().parents[2]


def _children_with_readme(readme: Path) -> list[Path]:
    """
    Return immediate child directories of the README's directory that themselves contain a README.

    Symlinked directories are skipped: their real location is documented in place, and the audit's directory discovery
    (driven by ``git ls-files``) records a symlink as a single entry rather than expanding it, so following symlinks
    here would demand down-links the CLI audit never requires. Directories matching the audit's exclusions (caches,
    build artifacts, ``*.egg-info``, etc.) are likewise skipped, and so are the repo-root-only exclusions
    (``EXCLUDE_TOP_LEVEL``) when ``readme`` is the repo-root README. Those include untracked or gitignored directories
    such as the ``inventory/`` clone, which the ``git ls-files``-driven audit never sees.

    :param readme: absolute path to the README file
    :return: list of child directories containing a README
    """
    is_repo_root = readme.resolve().parent == REPO_ROOT

    children: list[Path] = []
    for child in sorted(readme.parent.iterdir()):
        if child.is_symlink() or (not child.is_dir()) or (not (child / 'README.md').is_file()):
            continue
        if (child.name in EXCLUDE_SEGMENTS) or any(child.name.endswith(suffix) for suffix in EXCLUDE_SUFFIXES):
            continue
        if is_repo_root and (child.name in EXCLUDE_TOP_LEVEL):
            continue
        children.append(child)
    return children


def main(argv: list[str] | None = None) -> int:
    """
    Validate each changed README passed by prek.

    :param argv: file paths (defaults to ``sys.argv[1:]``)
    :return: 1 when any README has a structural, link, or policy issue; 0 otherwise
    """
    parser = argparse.ArgumentParser(description='Validate changed README files')
    parser.add_argument('filenames', nargs='*', help='files supplied by pre-commit')
    args = parser.parse_args(argv)

    readmes = [Path(name) for name in args.filenames if Path(name).name == 'README.md']

    failed = False
    for readme in readmes:
        if not readme.is_file():
            continue

        issues = structural_issues(
            readme,
            children_with_readme=_children_with_readme(readme),
            is_repo_root=readme.resolve().parent == REPO_ROOT,
        )
        broken  = link_issues(readme)
        matches = policy_issues(readme)
        if not (issues or broken or matches):
            continue

        failed = True
        print(f'🔴 {style(readme.as_posix(), fg="magenta", bold=True)}')
        for issue in issues:
            print(f'   structural: {issue}')
        for link in broken:
            print(f'   link: {link.link} ({link.reason})')
        for match in matches:
            print(f'   policy: {match.pattern} @ line {match.line}')

    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
