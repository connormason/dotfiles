"""
Hardcoded conventions for the deterministic docs audit.

These encode this repository's rules (directory exclusions, meta-directory names, the planning-artifacts exemption, and
forbidden command patterns in docs). They are intentionally hardcoded named constants rather than a config file (YAGNI).
"""
from __future__ import annotations

import re

__all__ = [
    'EXCLUDE_SEGMENTS',
    'EXCLUDE_SUFFIXES',
    'EXCLUDE_TOP_LEVEL',
    'FORBIDDEN_PATTERNS',
    'META_DIR_NAMES',
    'PLACEHOLDER_FILENAMES',
    'PLANS_EXEMPT_PARTS',
    'POLICY_ALLOW_END',
    'POLICY_ALLOW_INLINE',
    'POLICY_ALLOW_START',
]

# Path segments that disqualify a directory at ANY depth. These are caches, VCS/editor/tooling state, and the hidden
# directories that hold either tooling config (.ctx, .github, .claude) or stow payloads destined for $HOME (.config,
# .ssh, .hammerspoon, ...), none of which is documentable source.
EXCLUDE_SEGMENTS: frozenset[str] = frozenset({
    '.claude',
    '.config',
    '.ctx',
    '.git',
    '.git-template',
    '.github',
    '.hammerspoon',
    '.idea',
    '.ipython',
    '.mypy_cache',
    '.nox',
    '.pytest_cache',
    '.ruff_cache',
    '.ssh',
    '.venv',
    '.vscode',
    '__pycache__',
})

# Directory names excluded ONLY when they are the top-level (repo-root) directory. ``archive`` is the frozen pre-stow
# setup (not maintained, skipped by the lint tooling); ``inventory`` is a gitignored clone of a separate repo (it has
# its own README, but is not part of this one); build/dist/site are output dirs that matter only if ever tracked.
EXCLUDE_TOP_LEVEL: frozenset[str] = frozenset({
    'archive',
    'build',
    'dist',
    'inventory',
    'site',
})

# Path-segment suffixes that disqualify a directory (e.g. ``dotfiles.egg-info``)
EXCLUDE_SUFFIXES: tuple[str, ...] = (
    '.egg-info',
)

# Filenames that hold a directory in version control without contributing documentable content. A directory whose only
# entries are placeholders (e.g. ``services/homeassistant/config`` seeded with ``.gitkeep``) carries nothing worth a
# README and is treated as EXEMPT.
PLACEHOLDER_FILENAMES: frozenset[str] = frozenset({
    '.gitkeep',
    '.keep',
})

# Top-level directory names treated as "meta" (index/overview README). The repo root is also meta (handled separately).
META_DIR_NAMES: frozenset[str] = frozenset({
    'docs',
    'scripts',
    'tests',
})

# Leading path parts whose subtree is exempt from the missing-README requirement (planning artifacts, no index)
PLANS_EXEMPT_PARTS: tuple[str, ...] = (
    'docs',
    'plans',
)

# Forbidden command patterns in docs (compiled, word-bounded).
# Seed: the code formatter this repo bans (see ``.claude/rules/python-style.md``); only the linter is used.
FORBIDDEN_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r'\bruff format\b'),
)

# Opt-out markers that suppress forbidden-pattern matching, for docs that must legitimately reference an anti-pattern
# (e.g. documentation of the policy check itself). The inline marker suppresses the single line it appears on; the
# block markers suppress every line between them (use these to wrap a fenced code example, since an inline HTML comment
# inside a code fence would corrupt the example).
POLICY_ALLOW_INLINE: str = '<!-- docs-audit-allow -->'
POLICY_ALLOW_START:  str = '<!-- docs-audit-allow-start -->'
POLICY_ALLOW_END:    str = '<!-- docs-audit-allow-end -->'
