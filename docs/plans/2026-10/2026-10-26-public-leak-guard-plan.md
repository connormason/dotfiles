# Public Repo Hygiene & Leak Guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove employer-internal content from this public repo and add an automatic guard (local + CI) that blocks it
from returning.

**Architecture:** A uv wrapper (`scripts/hooks/uv-public.sh`) neutralizes the work environment's internal package index
for every uv call made by this repo's tooling. A self-contained PEP 723 hook (`scripts/hooks/check-leaks.py`) scans
file content, paths, and git identities against a public baseline plus an optional private pattern file. A one-time
cleanup deletes the internally-derived scripts and their references.

**Tech Stack:** Python 3.9+ stdlib, prek, uv, GitHub Actions, bash.

**Spec:** `docs/plans/2026-10/2026-10-26-public-leak-guard-design.md`

## Global Constraints

- Branch: `leak-guard` (already created; the spec is committed there). Never commit to or push `main`.
- **Every uv invocation in this repo goes through `scripts/hooks/uv-public.sh`** (created in Task 1), e.g.
  `scripts/hooks/uv-public.sh run --group test pytest …`. A plain `uv run`/`uv sync` from the work environment
  rewrites `uv.lock` to the internal mirror.
- If `git diff uv.lock` ever shows non-`pypi.org`/`files.pythonhosted.org` URLs, run `scripts/hooks/uv-public.sh lock`
  before staging. (This session's Claude hooks still run plain `uv run ruff` after edits until a new session starts.)
- Never run `ruff format`. `ruff check --fix` is fine.
- No file added or edited in this plan may contain the literal corporate domain, its email addresses, internal tool
  names, or bug-tracker URLs. Tests build such strings at runtime (`'apple' + '.com'`).
- Python style: `from __future__ import annotations` first; one import per line; single quotes; sphinx docstrings;
  no blank line between a class docstring and its first member; boxed `# ====` section headers.
- Tests: classes `TestX`, every test method `-> None`, multi-line docstrings, capitalized, no trailing period.
- Pre-commit hooks must pass on every commit (`prek` runs automatically on `git commit`).

## File Map

| File                                                                                | Action  | Responsibility                                 |
| ----------------------------------------------------------------------------------- | ------- | ---------------------------------------------- |
| `scripts/hooks/uv-public.sh`                                                        | Create  | uv wrapper that strips internal-index config   |
| `.pre-commit-config.yaml`                                                           | Modify  | Local uv hooks via wrapper; `check-leaks` hook |
| `.claude/settings.json`                                                             | Modify  | Public uv env for Claude; hooks via wrapper    |
| `uv.lock`, `requirements.txt`                                                       | Regen   | Public-PyPI-only lock                          |
| `scripts/hooks/check-leaks.py`                                                      | Create  | Leak guard hook                                |
| `tests/unit/__init__.py`, `tests/unit/test_check_leaks.py`                          | Create  | Guard unit tests                               |
| `.github/workflows/leaks.yml`                                                       | Modify  | `leak-guard` CI job                            |
| `.github/workflows/lint.yml`                                                        | Modify  | `pytest` CI job                                |
| `scripts/hooks/README.md`                                                           | Modify  | Document both new scripts                      |
| `scripts/env/`, `scripts/install/`, `scripts/maintain/`                             | Delete  | Internally-derived scripts                     |
| `run.py`, `Makefile`                                                                | Modify  | Drop `install-uv` / `install-hatch`            |
| `roles/git/templates/pre-commit.j2`                                                 | Rewrite | Generic prek-delegating git-template hook      |
| `docs/plans/2026-01/2026-01-21-dotfiles-improvement-plan/05-repo-integration-strategy.md` | Rewrite | Superseded stub                          |
| `README.md`, `roles/README.md`, `docs/RUN_PY_REFERENCE.md`, `.ctx/*`, misc          | Modify  | Remove references to deleted scripts/commands  |

---

### Task 1: Public-only uv wrapper, hooks, and lock regeneration

**Files:**

- Create: `scripts/hooks/uv-public.sh`
- Modify: `.pre-commit-config.yaml:25-53` (the `astral-sh/uv-pre-commit` repo block)
- Modify: `.claude/settings.json` (add `env`; rewrite two PostToolUse commands)
- Regenerate: `uv.lock`, `requirements.txt`

**Interfaces:**

- Produces: `scripts/hooks/uv-public.sh <uv args…>` — drop-in replacement for `uv`, used by every later task.

- [ ] **Step 1: Capture the failing condition**

Run: `grep -c 'registry = "https://pypi.org/simple"' uv.lock; grep -vc 'pypi.org\|pythonhosted.org' <(grep -o 'https://[^"]*' uv.lock | sort -u)`
Expected: first number `0` (no public registry entries); second number non-zero (internal URLs present).

- [ ] **Step 2: Create the wrapper**

`scripts/hooks/uv-public.sh`:

```bash
#!/usr/bin/env bash
# Run uv against public PyPI only.
#
# Work machines inject an internal package index two ways: UV_* index environment variables, and an extra-index-url
# in the user-level ~/.config/uv/uv.toml (which uv consults before any project default index). Both must be
# neutralized; either alone still produces a uv.lock that references the internal index. UV_NO_CONFIG skips only
# user/system uv.toml files -- this project's [tool.uv] table in pyproject.toml is still honored.
set -euo pipefail

unset UV_INDEX_URL UV_DEFAULT_INDEX UV_EXTRA_INDEX_URL UV_INDEX
export UV_NO_CONFIG=1

exec uv "$@"
```

Run: `chmod +x scripts/hooks/uv-public.sh`

- [ ] **Step 3: Replace the upstream uv hooks with local wrapper hooks**

In `.pre-commit-config.yaml`, replace the entire `- repo: https://github.com/astral-sh/uv-pre-commit` block (its
`rev:` line and the three hooks `uv-lock`, `uv-sync`, `uv-export`) with:

```yaml
  - repo: local
    hooks:

      # Ensure uv.lock is up-to-date. Runs through uv-public.sh, so a lock polluted by a plain `uv run` from a work
      # environment is rewritten back to public PyPI whenever uv.lock is staged
      # pyproject.toml -> uv.lock
      - id: uv-lock
        name: "[sync]   dependencies (pyproject.toml -> uv.lock)"
        stages: [pre-commit, manual]
        priority: 0
        entry: scripts/hooks/uv-public.sh lock
        language: system
        files: ^(uv\.lock|pyproject\.toml|uv\.toml)$
        pass_filenames: false

      # Sync .venv/ with uv.lock on checkout/pull/rebase
      # uv.lock -> .venv/
      - id: uv-sync
        name: "[sync]   dependencies (uv.lock -> .venv)"
        stages: [post-checkout, post-merge, post-rewrite]
        priority: 5
        entry: scripts/hooks/uv-public.sh sync --no-active --locked
        language: system
        always_run: true
        pass_filenames: false

      # Export locked package requirements to requirements.txt
      # uv.lock -> requirements.txt
      - id: uv-export
        name: "[sync]   dependencies (uv.lock -> requirements.txt)"
        stages: [pre-commit, manual]
        priority: 5
        entry: scripts/hooks/uv-public.sh export
        language: system
        files: ^uv\.lock$
        pass_filenames: false
        args:
          - "--format=requirements.txt"
          - "--output-file=requirements.txt"
          - "--frozen"
          - "--no-hashes"
          - "--no-header"
```

Leave the `sync-with-uv` and `sync-pre-commit-deps` blocks untouched.

- [ ] **Step 4: Pin public uv settings for Claude Code sessions in this repo**

In `.claude/settings.json`, add a top-level `env` object (keep keys sorted; the `pretty-format-json` hook enforces
2-space indent):

```json
  "env": {
    "UV_DEFAULT_INDEX": "https://pypi.org/simple",
    "UV_INDEX_URL": "https://pypi.org/simple",
    "UV_NO_CONFIG": "1"
  },
```

In the same file, change the two PostToolUse commands so they use the wrapper:

- `uv run ruff check --fix-only` → `"$CLAUDE_PROJECT_DIR"/scripts/hooks/uv-public.sh run ruff check --fix-only`
- `uv run yamllint` → `"$CLAUDE_PROJECT_DIR"/scripts/hooks/uv-public.sh run yamllint`

(Inside the JSON string the inner quotes are escaped: `\"$CLAUDE_PROJECT_DIR\"/scripts/hooks/uv-public.sh`.)

- [ ] **Step 5: Regenerate the lock and requirements**

Run: `scripts/hooks/uv-public.sh lock && scripts/hooks/uv-public.sh export --format=requirements.txt --output-file=requirements.txt --frozen --no-hashes --no-header && scripts/hooks/uv-public.sh sync --locked`
Expected: all three succeed.

- [ ] **Step 6: Verify the lock is public-only**

Run: `grep -o 'https://[^"/]*' uv.lock | sort -u`
Expected: exactly `https://files.pythonhosted.org` and `https://pypi.org`.

Run: `git diff --stat uv.lock requirements.txt` — record which package versions moved (if any) in the commit body.

- [ ] **Step 7: Verify the self-healing hook**

Run: `cp uv.lock "$TMPDIR/uv.lock.public" && uv lock -q; grep -o 'https://[^"/]*' uv.lock | sort -u`
Expected (inside a work-environment session): an internal host appears — a plain `uv lock` re-polluted the lock. If
only the two public hosts appear, the environment is already clean; skip to Step 8.
Run: `git add uv.lock && prek run uv-lock; grep -o 'https://[^"/]*' uv.lock | sort -u`
Expected: hook reports `Failed - files were modified`, and the URL list is again exactly the two public hosts.
Run: `cmp uv.lock "$TMPDIR/uv.lock.public" && echo identical`
Expected: `identical`.

- [ ] **Step 8: Run all hooks**

Run: `prek run --all-files`
Expected: all hooks pass (or are skipped). Fix anything flagged before committing.

- [ ] **Step 9: Commit**

```bash
git add scripts/hooks/uv-public.sh .pre-commit-config.yaml .claude/settings.json uv.lock requirements.txt
git commit -m "fix(uv): resolve dependencies from public PyPI only

Route every repo uv call through scripts/hooks/uv-public.sh, which unsets
the UV_* index variables and sets UV_NO_CONFIG=1; either measure alone still
produced a lock pointing at an internal mirror. The uv-lock hook now heals a
polluted lock at commit time."
```

---

### Task 2: Leak guard hook (`check-leaks.py`) with unit tests

**Files:**

- Create: `scripts/hooks/check-leaks.py`
- Create: `tests/unit/__init__.py` (empty)
- Create: `tests/unit/test_check_leaks.py`

**Interfaces:**

- Consumes: `scripts/hooks/uv-public.sh` (Task 1) for running tests.
- Produces (module `check_leaks`, loaded from the hyphenated file by tests):
  - `BASELINE_PATTERNS: tuple[str, ...]`, `ALLOW_MARKER: str = 'leak-guard: allow'`,
    `PATTERNS_ENV_VAR: str = 'DOTFILES_LEAK_PATTERNS'`, `MAX_FINDINGS_PER_FILE: int = 5`,
    `IDENTITY_SOURCE: str = '<identity>'`
  - `class LeakGuardError(Exception)`
  - `@dataclass(frozen=True) class Finding: source: str; line: int; match: str`
  - `default_patterns_file() -> Path`
  - `load_patterns(patterns_file: Path | None, *, required: bool) -> list[re.Pattern[str]]`
  - `mask(text: str) -> str`
  - `scan_text(text: str, patterns: Sequence[re.Pattern[str]]) -> list[tuple[int, str]]`
  - `scan_file(path: Path, patterns: Sequence[re.Pattern[str]]) -> list[Finding]` (raises `OSError` if unreadable)
  - `git_identities() -> list[str]` (raises `LeakGuardError`)
  - `scan_identities(identities: Iterable[str], patterns: Sequence[re.Pattern[str]]) -> list[Finding]`
  - `main(argv: Sequence[str] | None = None) -> int` — `0` clean, `1` findings or unreadable file, `2` configuration
    error
  - CLI: `check-leaks.py [FILENAMES…] [--identity] [--identities-from FILE|-] [--patterns-file PATH] [-v]`

- [ ] **Step 1: Write the failing tests**

`tests/unit/__init__.py`: empty file.

`tests/unit/test_check_leaks.py`:

```python
"""
Unit tests for scripts/hooks/check-leaks.py
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType

SCRIPT_PATH = Path(__file__).resolve().parents[2] / 'scripts' / 'hooks' / 'check-leaks.py'

# Built at runtime so this file never contains the literal identifiers it exercises
CORP_DOMAIN = 'apple' + '.com'
TRACKER_URL = 'rdar' + ':' + '//' + '123456'


def _load_module() -> ModuleType:
    """
    Import the hyphenated hook script as module ``check_leaks``
    """
    spec = importlib.util.spec_from_file_location('check_leaks', SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules['check_leaks'] = module
    spec.loader.exec_module(module)
    return module


check_leaks = _load_module()


@pytest.fixture(autouse=True)
def isolate_private_patterns(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """
    Keep a developer's real private pattern file out of every test
    """
    monkeypatch.delenv('DOTFILES_LEAK_PATTERNS', raising=False)
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'xdg-config'))


@pytest.fixture
def baseline() -> list:
    """
    Compiled baseline patterns only
    """
    return check_leaks.load_patterns(None, required=False)


class TestBaselinePatterns:
    """
    Tests for the built-in public baseline
    """
    @pytest.mark.parametrize(
        'text',
        [
            f'url = "https://pypi.{CORP_DOMAIN}/simple"',
            f'Author: Jane Doe <jane@{CORP_DOMAIN}>',
            f'host github.pie.{CORP_DOMAIN}',
            f'bare {CORP_DOMAIN.upper()} mention',
            f'see {TRACKER_URL}',
            'see ' + 'Radar' + ':' + '//' + '42',
        ],
    )
    def test_internal_identifiers_match(self, baseline: list, text: str) -> None:
        """
        Test that corporate domains, emails, subdomains, and tracker URLs are flagged
        """
        assert check_leaks.scan_text(text, baseline)

    @pytest.mark.parametrize(
        'text',
        [
            'defaults write com.apple.dock autohide -bool true',
            f'<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.{CORP_DOMAIN}/DTDs/PropertyList-1.0.dtd">',
            f'App ID from https://apps.{CORP_DOMAIN}/app/id937984704',
            f'https://developer.{CORP_DOMAIN}/documentation',
            f'https://support.{CORP_DOMAIN}/en-us/102345',
            'image: lscr.io/linuxserver/radarr:latest',
            'Radarr manages movies',
            'apple' + '.community',
        ],
    )
    def test_public_text_does_not_match(self, baseline: list, text: str) -> None:
        """
        Test that public vendor hosts, macOS preference domains, and Radarr are not flagged
        """
        assert check_leaks.scan_text(text, baseline) == []

    @pytest.mark.parametrize('path', [SCRIPT_PATH, Path(__file__)])
    def test_own_source_is_clean(self, baseline: list, path: Path) -> None:
        """
        Test that the hook script and this test file never match their own patterns
        """
        assert check_leaks.scan_file(path, baseline) == []


class TestPrivatePatterns:
    """
    Tests for loading the optional private pattern file
    """
    def test_absent_default_file_uses_baseline_only(self) -> None:
        """
        Test that a missing default pattern file silently falls back to the baseline
        """
        patterns = check_leaks.load_patterns(check_leaks.default_patterns_file(), required=False)
        assert len(patterns) == len(check_leaks.BASELINE_PATTERNS)

    def test_default_file_location_honors_xdg(self, tmp_path: Path) -> None:
        """
        Test that the default pattern file lives under XDG_CONFIG_HOME
        """
        assert check_leaks.default_patterns_file() == tmp_path / 'xdg-config' / 'dotfiles' / 'leak-patterns.txt'

    def test_present_file_adds_patterns(self, tmp_path: Path) -> None:
        """
        Test that private patterns are applied and comments/blank lines are ignored
        """
        patterns_file = tmp_path / 'leak-patterns.txt'
        patterns_file.write_text('# internal tools\n\nsecret-tool\n', encoding='utf-8')
        patterns = check_leaks.load_patterns(patterns_file, required=True)
        assert len(patterns) == len(check_leaks.BASELINE_PATTERNS) + 1
        assert check_leaks.scan_text('runs Secret-Tool nightly', patterns) == [(1, 'Secret-Tool')]

    def test_required_missing_file_raises(self, tmp_path: Path) -> None:
        """
        Test that an explicitly requested but missing pattern file fails closed
        """
        with pytest.raises(check_leaks.LeakGuardError):
            check_leaks.load_patterns(tmp_path / 'missing.txt', required=True)

    def test_invalid_regex_raises(self, tmp_path: Path) -> None:
        """
        Test that an invalid private regex fails closed
        """
        patterns_file = tmp_path / 'leak-patterns.txt'
        patterns_file.write_text('unclosed(group\n', encoding='utf-8')
        with pytest.raises(check_leaks.LeakGuardError):
            check_leaks.load_patterns(patterns_file, required=True)

    def test_env_var_invalid_file_exits_2(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """
        Test that main() returns a configuration error for a bad file named by the env var
        """
        monkeypatch.setenv('DOTFILES_LEAK_PATTERNS', str(tmp_path / 'missing.txt'))
        assert check_leaks.main([]) == 2


class TestAllowMarker:
    """
    Tests for the inline allow escape hatch
    """
    def test_marker_suppresses_only_its_line(self, baseline: list) -> None:
        """
        Test that the allow marker skips its own line but not the next one
        """
        text = f'{CORP_DOMAIN}  # {check_leaks.ALLOW_MARKER}\n{CORP_DOMAIN}\n'
        assert check_leaks.scan_text(text, baseline) == [(2, CORP_DOMAIN)]


class TestScanFile:
    """
    Tests for scan_file
    """
    def test_path_is_scanned(self, tmp_path: Path) -> None:
        """
        Test that a matching file path is reported with line 0
        """
        patterns_file = tmp_path / 'leak-patterns.txt'
        patterns_file.write_text('secret-tool\n', encoding='utf-8')
        patterns = check_leaks.load_patterns(patterns_file, required=True)
        target = tmp_path / 'secret-tool.txt'
        target.write_text('clean\n', encoding='utf-8')
        findings = check_leaks.scan_file(target, patterns)
        assert [(f.line, f.match) for f in findings] == [(0, 'secret-tool')]

    def test_content_line_numbers(self, baseline: list, tmp_path: Path) -> None:
        """
        Test that content findings carry 1-based line numbers
        """
        target = tmp_path / 'notes.md'
        target.write_text(f'clean\nmail jane@{CORP_DOMAIN}\n', encoding='utf-8')
        findings = check_leaks.scan_file(target, baseline)
        assert [(f.line, f.match) for f in findings] == [(2, CORP_DOMAIN)]

    def test_binary_file_is_skipped(self, baseline: list, tmp_path: Path) -> None:
        """
        Test that files with a NUL byte in the sniff window are not content-scanned
        """
        target = tmp_path / 'blob.bin'
        target.write_bytes(b'\0' + CORP_DOMAIN.encode())
        assert check_leaks.scan_file(target, baseline) == []


class TestIdentity:
    """
    Tests for git identity checks
    """
    @pytest.fixture
    def identity(self, monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
        """
        Pin a personal author and committer identity for git var
        """
        for role in ('AUTHOR', 'COMMITTER'):
            monkeypatch.setenv(f'GIT_{role}_NAME', 'Jane Doe')
            monkeypatch.setenv(f'GIT_{role}_EMAIL', 'jane@example.org')
        return monkeypatch

    def test_personal_identity_passes(self, identity: pytest.MonkeyPatch) -> None:
        """
        Test that a personal author/committer identity is accepted
        """
        assert check_leaks.main(['--identity']) == 0

    def test_corporate_author_email_fails(self, identity: pytest.MonkeyPatch) -> None:
        """
        Test that a corporate author email is rejected before the commit exists
        """
        identity.setenv('GIT_AUTHOR_EMAIL', f'jane@{CORP_DOMAIN}')
        assert check_leaks.main(['--identity']) == 1

    def test_identities_from_file(self, tmp_path: Path) -> None:
        """
        Test that identities read from a file are checked line by line
        """
        identities = tmp_path / 'identities.txt'
        identities.write_text(f'Jane Doe <jane@example.org>\nJane Doe <jane@{CORP_DOMAIN}>\n', encoding='utf-8')
        assert check_leaks.main(['--identities-from', str(identities)]) == 1


class TestOutput:
    """
    Tests for reporting and masking
    """
    @pytest.mark.parametrize(
        ('text', 'expected'),
        [
            ('abcdef', 'a****f'),
            ('ab',     '**'),
            ('a',      '*'),
        ],
    )
    def test_mask(self, text: str, expected: str) -> None:
        """
        Test that masking keeps only the first and last characters
        """
        assert check_leaks.mask(text) == expected

    def test_report_never_prints_match(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that output masks matched text and caps findings per file
        """
        target = tmp_path / 'many.txt'
        target.write_text(''.join(f'jane{i}@{CORP_DOMAIN}\n' for i in range(7)), encoding='utf-8')
        assert check_leaks.main([str(target)]) == 1
        out = capsys.readouterr().out
        assert CORP_DOMAIN not in out
        assert 'and 2 more' in out

    def test_clean_file_exits_0(self, tmp_path: Path) -> None:
        """
        Test that a clean file passes
        """
        target = tmp_path / 'clean.txt'
        target.write_text('nothing to see here\n', encoding='utf-8')
        assert check_leaks.main([str(target)]) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `scripts/hooks/uv-public.sh run --group test pytest tests/unit/test_check_leaks.py`
Expected: collection error — `FileNotFoundError` / spec loader failure for `scripts/hooks/check-leaks.py`.

- [ ] **Step 3: Implement the hook**

`scripts/hooks/check-leaks.py`:

```python
#!/usr/bin/env python3
"""
Pre-commit hook that blocks employer-internal identifiers from entering this public repository.

File contents, file paths, and git identities are matched against a built-in public baseline plus an optional private
pattern file that lives outside the repository (supplied by the private work dotfiles overlay).
"""
# /// script
# requires-python = ">= 3.9"
# dependencies = []
# ///
from __future__ import annotations

import argparse
import functools
import os
import re
import subprocess
import sys
import textwrap
from collections.abc import Iterable
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from typing import Union

# ==========================
# Constants/defaults/globals
# ==========================


VERBOSE:               bool = False
ALLOW_MARKER:          str  = 'leak-guard: allow'
PATTERNS_ENV_VAR:      str  = 'DOTFILES_LEAK_PATTERNS'
IDENTITY_SOURCE:       str  = '<identity>'
MAX_FINDINGS_PER_FILE: int  = 5
BINARY_SNIFF_BYTES:    int  = 8192

# Public vendor hosts that legitimately appear in public files (plist DTDs, App Store and developer links)
PUBLIC_VENDOR_HOSTS: tuple[str, ...] = ('apps', 'developer', 'support', 'www')
_PUBLIC_HOSTS_ALT:   str             = '|'.join(PUBLIC_VENDOR_HOSTS)

# Written so their own source text can never match them (escaped dot before the TLD, `/{2}` in place of a literal
# double slash), which lets this file be scanned like any other without an exclusion
BASELINE_PATTERNS: tuple[str, ...] = (
    # Corporate domain, any subdomain, and email addresses at it -- except the public vendor hosts above
    rf'(?<![\w.-])(?!(?:{_PUBLIC_HOSTS_ALT})\.)(?:[\w-]+\.)*apple\.com\b',
    # Internal bug-tracker URL schemes
    r'\b(?:rdar|radar):/{2}',
)

# `git var GIT_*_IDENT` prints "Name <email> <timestamp> <tz>"; keep everything through the closing ">"
IDENT_RE: re.Pattern[str] = re.compile(r'^(?P<ident>.*?>)')


# ===============
# Types/protocols
# ===============


PathLike = Union[str, Path]


class LeakGuardError(Exception):
    """
    Raised for configuration or environment failures (bad pattern file, unavailable git identity).
    """


@dataclass(frozen=True)
class Finding:
    """
    A single pattern match.

    :param source: file path, or :data:`IDENTITY_SOURCE` for git identity matches
    :param line: 1-based line number, or 0 when the match is in a path or identity
    :param match: matched text (never printed unmasked)
    """
    source: str
    line:   int
    match:  str


# ==================
# Formatting/logging
# ==================


ANSI_COLOR: dict[str, int] = {
    'red':    31, 'bright_red':    91,
    'green':  32, 'bright_green':  92,
    'yellow': 33, 'bright_yellow': 93,
    'blue':   34, 'bright_blue':   94,
    'white':  37, 'bright_white':  97,
}
ANSI_RESET_ALL = '\033[0m'


def style(text: Any = '', *, fg: str | None = None, bold: bool | None = None, dim: bool | None = None) -> str:
    """
    Style text with ANSI escape codes.

    :param text: the value to style (converted with ``str()``)
    :param fg: foreground color name from :data:`ANSI_COLOR`
    :param bold: enable or disable bold mode
    :param dim: enable or disable dim mode
    :return: styled text
    """
    bits: list[str] = []
    if fg:
        bits.append(f'\033[{ANSI_COLOR[fg]}m')
    if bold is not None:
        bits.append(f'\033[{1 if bold else 22}m')
    if dim is not None:
        bits.append(f'\033[{2 if dim else 22}m')
    bits.append(str(text))
    bits.append(ANSI_RESET_ALL)
    return ''.join(bits)


def folduser(path: PathLike) -> str:
    """
    Replace the user's home directory with ``~`` in a path string.

    :param path: path
    :return: folded path string
    """
    return str(path).replace(str(Path.home()), '~')


ERROR = style('ERROR', fg='bright_red',  bold=True)
INFO  = style('INFO',  fg='bright_blue', bold=True)


def printf(
    text: str = '',
    *,
    fg: str | None = None,
    bold: bool | None = None,
    dim: bool | None = None,
    indent: int = 0,
    verbose: bool = False,
) -> None:
    """
    Print styled text with optional indent and verbose gating.

    :param text: text to print
    :param fg: foreground color
    :param bold: bold mode
    :param dim: dim mode
    :param indent: number of spaces to indent output by
    :param verbose: only print when global ``VERBOSE`` is True. Output is dim and sent to stderr
    """
    if verbose and not VERBOSE:
        return
    if verbose:
        fg   = fg or 'bright_white'
        dim  = True if dim is None else dim
        file = sys.stderr
    else:
        file = None

    print(
        style(textwrap.indent(text, ' ' * indent), fg=fg, bold=bold, dim=dim),
        file=file,
    )


# ======================
# Command-line arguments
# ======================


class Args(argparse.Namespace):
    """
    :class:`argparse.Namespace` annotated with args supported by this script.
    """
    filenames:       Sequence[str]  # positional arg(s)
    identity:        bool
    identities_from: str | None
    patterns_file:   str | None
    verbose:         bool


def parse_args(argv: Sequence[str] | None = None) -> Args:
    """
    Parse command-line arguments.

    :param argv: argument list (default: ``sys.argv[1:]``)
    :return: :class:`Args` (typed :class:`argparse.Namespace` subclass)
    """
    global VERBOSE

    parser = argparse.ArgumentParser(
        description='Block employer-internal identifiers from entering this public repository',
        formatter_class=functools.partial(argparse.RawTextHelpFormatter, max_help_position=50),
        add_help=False,
    )

    def add_positional_args() -> None:
        """
        Register the positional arguments group on the parser.
        """
        positional_args = parser.add_argument_group('Positional arguments')
        positional_args.add_argument('filenames', nargs='*', help='Files whose paths and contents are scanned')
    add_positional_args()

    def add_identity_opts() -> None:
        """
        Register the identity options group on the parser.
        """
        identity_opts = parser.add_argument_group('Identity options')
        identity_opts.add_argument(
            '--identity',
            action='store_true',
            help='Also check the git author/committer identity of the commit being made',
        )
        identity_opts.add_argument(
            '--identities-from',
            metavar='FILE',
            help="Check one 'Name <email>' identity per line from FILE ('-' for stdin)",
        )
    add_identity_opts()

    def add_pattern_opts() -> None:
        """
        Register the pattern options group on the parser.
        """
        pattern_opts = parser.add_argument_group('Pattern options')
        pattern_opts.add_argument(
            '--patterns-file',
            metavar='PATH',
            help=(
                f'Private pattern file; must exist when given (default: ${PATTERNS_ENV_VAR}, else\n'
                f'{folduser(default_patterns_file())} if present)'
            ),
        )
    add_pattern_opts()

    def add_output_opts() -> None:
        """
        Register the output options group on the parser.
        """
        output_opts = parser.add_argument_group('Output options')
        output_opts.add_argument('-v', '--verbose', action='store_true', help='Report clean results too')
    add_output_opts()

    def add_other_opts() -> None:
        """
        Register the miscellaneous options group on the parser.
        """
        other_opts = parser.add_argument_group('Other options')
        other_opts.add_argument(
            '-h',
            '--help',
            action='help',
            default=argparse.SUPPRESS,
            help='Show this help message and exit',
        )
    add_other_opts()

    args    = parser.parse_args(argv, namespace=Args())
    VERBOSE = args.verbose
    return args


# =================
# Core script logic
# =================


def default_patterns_file() -> Path:
    """
    Location of the private pattern file when neither ``--patterns-file`` nor the env var is given.

    :return: ``$XDG_CONFIG_HOME/dotfiles/leak-patterns.txt`` (``~/.config`` when ``XDG_CONFIG_HOME`` is unset)
    """
    config_home = os.environ.get('XDG_CONFIG_HOME') or str(Path.home() / '.config')
    return Path(config_home) / 'dotfiles' / 'leak-patterns.txt'


def mask(text: str) -> str:
    """
    Mask matched text so reports never re-publish it.

    :param text: matched text
    :return: ``text`` with every character except the first and last replaced by ``*``
    """
    if len(text) <= 2:
        return '*' * len(text)
    return f'{text[0]}{"*" * (len(text) - 2)}{text[-1]}'


def load_patterns(patterns_file: Path | None, *, required: bool) -> list[re.Pattern[str]]:
    """
    Compile the baseline patterns plus any private patterns.

    :param patterns_file: private pattern file (one regex per line; blank lines and ``#`` comments are ignored)
    :param required: raise when ``patterns_file`` does not exist instead of falling back to the baseline
    :raises LeakGuardError: if a required file is missing, the file is unreadable, or a pattern is invalid
    :return: compiled, case-insensitive patterns
    """
    sources: list[str] = list(BASELINE_PATTERNS)
    if patterns_file is not None:
        if patterns_file.is_file():
            try:
                lines = patterns_file.read_text(encoding='utf-8').splitlines()
            except OSError as exc:
                raise LeakGuardError(f'Unable to read {folduser(patterns_file)}: {exc!s}') from exc
            sources.extend(line.strip() for line in lines if line.strip() and not line.lstrip().startswith('#'))
        elif required:
            raise LeakGuardError(f'Pattern file not found: {folduser(patterns_file)}')

    compiled: list[re.Pattern[str]] = []
    for source in sources:
        try:
            compiled.append(re.compile(source, re.IGNORECASE))
        except re.error as exc:
            raise LeakGuardError(f'Invalid pattern {mask(source)!r}: {exc!s}') from exc
    return compiled


def scan_text(text: str, patterns: Sequence[re.Pattern[str]]) -> list[tuple[int, str]]:
    """
    Find pattern matches in text, line by line.

    :param text: text to scan
    :param patterns: compiled patterns
    :return: ``(line_number, matched_text)`` pairs; lines containing :data:`ALLOW_MARKER` are skipped
    """
    hits: list[tuple[int, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if ALLOW_MARKER in line:
            continue
        for pattern in patterns:
            hits.extend((lineno, match.group(0)) for match in pattern.finditer(line))
    return hits


def scan_file(path: Path, patterns: Sequence[re.Pattern[str]]) -> list[Finding]:
    """
    Scan a file's path and (unless binary) its contents.

    :param path: file to scan
    :param patterns: compiled patterns
    :raises OSError: if the file cannot be read
    :return: findings, path matches first (line 0)
    """
    findings = [Finding(str(path), 0, match.group(0)) for pattern in patterns for match in pattern.finditer(str(path))]

    data = path.read_bytes()
    if b'\0' in data[:BINARY_SNIFF_BYTES]:
        return findings

    text = data.decode('utf-8', errors='replace')
    findings.extend(Finding(str(path), lineno, match) for lineno, match in scan_text(text, patterns))
    return findings


def git_identities() -> list[str]:
    """
    Resolve the author and committer identity git will record for the next commit.

    :raises LeakGuardError: if git cannot determine an identity
    :return: ``Name <email>`` strings for the author and committer
    """
    identities: list[str] = []
    for var in ('GIT_AUTHOR_IDENT', 'GIT_COMMITTER_IDENT'):
        result = subprocess.run(['git', 'var', var], capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise LeakGuardError(f'git var {var} failed: {result.stderr.strip()}')
        ident = result.stdout.strip()
        match = IDENT_RE.match(ident)
        identities.append(match.group('ident') if match else ident)
    return identities


def scan_identities(identities: Iterable[str], patterns: Sequence[re.Pattern[str]]) -> list[Finding]:
    """
    Scan git identities.

    :param identities: ``Name <email>`` strings (blank entries are ignored)
    :param patterns: compiled patterns
    :return: findings with source :data:`IDENTITY_SOURCE`
    """
    return [
        Finding(IDENTITY_SOURCE, 0, match.group(0))
        for identity in identities
        if identity.strip()
        for pattern in patterns
        for match in pattern.finditer(identity)
    ]


def report(findings: Sequence[Finding]) -> None:
    """
    Print findings grouped by source, masked, capped at :data:`MAX_FINDINGS_PER_FILE` per source.

    :param findings: findings to print
    """
    by_source: dict[str, list[Finding]] = {}
    for finding in findings:
        by_source.setdefault(finding.source, []).append(finding)

    for source, items in by_source.items():
        printf(f'{ERROR}   {style(source, fg="bright_white")}')
        for item in items[:MAX_FINDINGS_PER_FILE]:
            if item.line:
                label = f'line {item.line}'
            else:
                label = 'identity' if source == IDENTITY_SOURCE else 'path'
            printf(f'{label}: internal identifier {mask(item.match)}', fg='bright_red', indent=8)
        if len(items) > MAX_FINDINGS_PER_FILE:
            printf(f'... and {len(items) - MAX_FINDINGS_PER_FILE} more', dim=True, indent=8)


def main(argv: Sequence[str] | None = None) -> int:
    """
    Scan files and identities for employer-internal identifiers.

    :param argv: command-line arguments (default: ``sys.argv[1:]``)
    :return: 0 if clean, 1 on findings or unreadable files, 2 on configuration errors
    """
    args = parse_args(argv)

    explicit = args.patterns_file or os.environ.get(PATTERNS_ENV_VAR)
    try:
        patterns = load_patterns(
            Path(explicit).expanduser() if explicit else default_patterns_file(),
            required=bool(explicit),
        )
    except LeakGuardError as exc:
        printf(f'{ERROR}   {exc!s}')
        return 2

    retval:   int           = 0
    findings: list[Finding] = []
    for filename in args.filenames:
        try:
            findings.extend(scan_file(Path(filename), patterns))
        except OSError as exc:
            printf(f'{ERROR}   {style(filename, fg="bright_white")}')
            printf(f'Unable to read file: {exc!s}', fg='bright_red', indent=8)
            retval = 1

    identities: list[str] = []
    if args.identity:
        try:
            identities.extend(git_identities())
        except LeakGuardError as exc:
            printf(f'{ERROR}   {exc!s}')
            return 2
    if args.identities_from:
        if args.identities_from == '-':
            identities.extend(sys.stdin.read().splitlines())
        else:
            identities.extend(Path(args.identities_from).read_text(encoding='utf-8').splitlines())
    findings.extend(scan_identities(identities, patterns))

    if findings:
        report(findings)
        return 1

    printf(f'{INFO}    No internal identifiers found ({len(patterns)} patterns)', verbose=True)
    return retval


if __name__ == '__main__':
    sys.exit(main())
```

Run: `chmod +x scripts/hooks/check-leaks.py`

- [ ] **Step 4: Run tests to verify they pass**

Run: `scripts/hooks/uv-public.sh run --group test pytest tests/unit/test_check_leaks.py`
Expected: all tests PASS.

- [ ] **Step 5: Lint**

Run: `scripts/hooks/uv-public.sh run ruff check --fix scripts/hooks/check-leaks.py tests/unit && scripts/hooks/uv-public.sh run mypy scripts/hooks/check-leaks.py`
Expected: no errors. If ruff flags `S603`/`S607` on the `git var` call, add `# noqa: S603, S607` with a trailing
reason comment (fixed argv, no shell) rather than restructuring.

- [ ] **Step 6: Commit**

```bash
git add scripts/hooks/check-leaks.py tests/unit/__init__.py tests/unit/test_check_leaks.py
git commit -m "feat(hooks): add check-leaks guard against internal identifiers"
```

---

### Task 3: Wire the guard into prek and CI; document both scripts

**Files:**

- Modify: `.pre-commit-config.yaml` (the `repo: local` block containing `check-json5` / `check-pkl`, ~line 236)
- Modify: `.github/workflows/leaks.yml`
- Modify: `.github/workflows/lint.yml`
- Modify: `scripts/hooks/README.md`

**Interfaces:**

- Consumes: `check-leaks.py` CLI (Task 2); `uv-public.sh` (Task 1).

- [ ] **Step 1: Add the prek hook**

Append to the `repo: local` hooks list that holds `check-json5` and `check-pkl`:

```yaml
      # Block employer-internal identifiers in staged content/paths and in the commit identity (public baseline +
      # optional private patterns from ~/.config/dotfiles/leak-patterns.txt). CI scans the full tree separately
      - id: check-leaks
        name: "[check]  internal identifiers (leak guard)"
        stages: [pre-commit]
        priority: 10
        entry: scripts/hooks/check-leaks.py --identity
        language: python
        types: [text]
        always_run: true
```

- [ ] **Step 2: Record the pre-cleanup baseline**

Run: `prek run check-leaks --all-files`
Expected: FAIL, findings only in `scripts/env/venvshell.py` and `scripts/install/install_uv.py` (tracker URLs). No
findings in `uv.lock` (fixed in Task 1), plists, or `roles/macos/README.md`. If any other file is flagged, stop and
report it — it is either a new leak to add to Task 4 or a false positive to fix in the baseline (with a test).

- [ ] **Step 3: Add the CI job**

Append to `jobs:` in `.github/workflows/leaks.yml`:

```yaml
  leak-guard:
    name: leak guard
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: astral-sh/setup-uv@v6
      # The runner has no git identity, so the script is called directly instead of through prek's --identity hook
      - name: Scan tracked files
        run: git ls-files -z | xargs -0 uv run --no-project scripts/hooks/check-leaks.py
      - name: Scan commit identities
        env:
          EVENT_NAME:  ${{ github.event_name }}
          PR_BASE:     ${{ github.event.pull_request.base.sha }}
          PR_HEAD:     ${{ github.event.pull_request.head.sha }}
          PUSH_BEFORE: ${{ github.event.before }}
        run: |
          if [ "$EVENT_NAME" = "pull_request" ]; then
            range="$PR_BASE..$PR_HEAD"
          elif [ -n "$PUSH_BEFORE" ] && [ "$PUSH_BEFORE" != "0000000000000000000000000000000000000000" ]; then
            range="$PUSH_BEFORE..$GITHUB_SHA"
          else
            range="-1 $GITHUB_SHA"
          fi
          # shellcheck disable=SC2086  # $range intentionally splits into "-1 <sha>"
          git log --format='%an <%ae>%n%cn <%ce>' $range \
            | uv run --no-project scripts/hooks/check-leaks.py --identities-from -
```

Append to `jobs:` in `.github/workflows/lint.yml`:

```yaml
  pytest:
    name: pytest
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
      - name: Install dependencies
        run: uv sync --group test
      - name: Pytest
        run: uv run pytest
```

Run: `scripts/hooks/uv-public.sh run yamllint .github/workflows/`
Expected: no errors.

- [ ] **Step 4: Document both scripts in `scripts/hooks/README.md`**

- Intro paragraph: "All four scripts" → "The Python scripts"; mention that `uv-public.sh` is a shell wrapper, not a
  filename-consuming hook.
- Add rows to the **Scripts** table:

  ```markdown
  | [`check-leaks.py`](#check-leakspy)         | Block employer-internal identifiers (content, paths, git identity) | `check-leaks`     | 10 (check phase)  |
  | [`uv-public.sh`](#uv-publicsh)             | Run uv against public PyPI only (wraps `uv-lock`/`uv-sync`/`uv-export`) | `uv-*`      | 0–5 (sync phase)  |
  ```

- Add `check-leaks` to the priority-10 row of the **Priority scheme** table, and change the 0–6 row's note to
  "`uv-lock`, `uv-sync`, `uv-export` (via `uv-public.sh`), `sync-with-uv`, `sync-pre-commit-deps`".
- Add a `## \`check-leaks.py\`` section (Synopsis / Options / Behavior / Exit Codes / Pre-Commit Integration, same
  shape as the others) covering: the two pattern sources and their precedence (`--patterns-file` >
  `$DOTFILES_LEAK_PATTERNS` > `$XDG_CONFIG_HOME/dotfiles/leak-patterns.txt`, the last optional); fail-closed rules;
  public vendor hosts allowed; the self-non-matching regex convention; `leak-guard: allow`; masking and the
  5-per-file cap; `--identity` vs `--identities-from`; exit codes 0/1/2; the CI job. Do not write any literal
  corporate domain or tracker URL in the README — describe them.
- Add a `## \`uv-public.sh\`` section: why both `unset` and `UV_NO_CONFIG=1` are needed (verified 2026-10-26), that
  project `[tool.uv]` settings still apply, the self-healing `uv-lock` behavior, and "always use it instead of bare
  `uv` in this repo".
- Delete the trailing `> **See also**: [scripts/env/]…` line (that directory is removed in Task 4).

Run: `prek run mdformat --files scripts/hooks/README.md` (the hook populates the TOC).

- [ ] **Step 5: Run hooks**

Run: `prek run --files .pre-commit-config.yaml .github/workflows/leaks.yml .github/workflows/lint.yml scripts/hooks/README.md`
Expected: PASS (`check-leaks` runs on these files only and they are clean).

- [ ] **Step 6: Commit**

```bash
git add .pre-commit-config.yaml .github/workflows/leaks.yml .github/workflows/lint.yml scripts/hooks/README.md
git commit -m "ci(hooks): run check-leaks in prek and CI; add pytest job"
```

---

### Task 4: One-time cleanup of internally-derived content

**Files:**

- Delete: `scripts/env/` , `scripts/install/`, `scripts/maintain/` (all files incl. READMEs and `__pycache__`)
- Modify: `run.py` (lines ~19, ~1271-1360), `Makefile` (regenerated)
- Rewrite: `roles/git/templates/pre-commit.j2`
- Rewrite: `docs/plans/2026-01/2026-01-21-dotfiles-improvement-plan/05-repo-integration-strategy.md`
- Modify: `docs/plans/2026-01/2026-01-21-dotfiles-improvement-plan/README.md:13`
- Modify: `.gitignore:391`, `pyproject.toml:304`, `scripts/utility/generate_completions.py` (examples)
- Modify docs: `README.md`, `roles/README.md:852`, `docs/RUN_PY_REFERENCE.md`, `.ctx/ARCHITECTURE.md:96`,
  `.ctx/BUILD.md:37-38`, `.claude/rules/readme-guidelines.md:24`

**Interfaces:**

- Consumes: `check-leaks` hook (Task 3) as the acceptance check.

- [ ] **Step 1: Delete the scripts**

```bash
git rm -r scripts/env scripts/install scripts/maintain
rm -rf scripts/maintain/__pycache__
```

- [ ] **Step 2: Remove the installer commands from `run.py`**

- Delete the whole "Tool installation commands" section: the module-level docstring block beginning
  `"""\nTool installation commands`, `installer_script_args()`, `cmd_install_uv()`, and `cmd_install_hatch()` (from the
  docstring through the end of `cmd_install_hatch`, immediately before the `"""\nCodebase commands` block).
- In the module docstring near line 19, delete the bullet `- **Tool Installation**: Install Python tooling (uv, hatch)
  with retry logic`.
- If `SCRIPTS_DIR` (line ~103) is now unused, delete it; if `Callable` or other imports become unused, ruff will flag
  them — remove them.

Run: `scripts/hooks/uv-public.sh run python run.py makefile && scripts/hooks/uv-public.sh run ruff check run.py && scripts/hooks/uv-public.sh run python run.py --help`
Expected: Makefile regenerated without `install-uv`/`install-hatch`; ruff clean; help lists no "Tool Installation"
group. Confirm with `grep -c 'install-uv\|install-hatch' Makefile` → `0`.

- [ ] **Step 3: Replace the git-template pre-commit hook**

Overwrite `roles/git/templates/pre-commit.j2` with a generic hook (no interpreter path; Jinja-safe, no `{{`):

```bash
#!/usr/bin/env bash
# Git template pre-commit hook (installed into new clones via init.templateDir).
# Delegates to prek when the repository has a pre-commit config; otherwise does nothing.
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
if [[ -f "$repo_root/.pre-commit-config.yaml" ]] && command -v prek >/dev/null 2>&1; then
    exec prek run
fi
exit 0
```

(`prek run` with no arguments runs the `pre-commit` stage against staged files. Repos that ran `prek install` get
their own shim, which replaces this template hook entirely.)

Check the role still renders: `grep -n 'pre-commit.j2' roles/git/tasks/*.yml` — the task's `dest`/`mode` stay as-is.

- [ ] **Step 4: Replace plan 05 with a superseded stub**

Overwrite `docs/plans/2026-01/2026-01-21-dotfiles-improvement-plan/05-repo-integration-strategy.md` with:

```markdown
# Plan: Repository Integration Strategy (Personal + Work Dotfiles)

**Status:** Superseded (2026-10-26)

This Ansible-era plan for layering a private work dotfiles repository on top of this one is superseded by the
dev-env base/overlay design in [`docs/plans/2026-10/`](../../2026-10/), which reflects both repositories' current
(stow-based) architecture.
```

In the same directory's `README.md` line 13, append ` (superseded)` to the "Repo Integration Strategy" title cell.

- [ ] **Step 5: Remove remaining references**

- `.gitignore`: delete the line `!scripts/env/`.
- `pyproject.toml`: delete the per-file-ignore line `"scripts/env/venvshell.py" = ["RUF001"]` (inside the
  keep-sorted block).
- `scripts/utility/generate_completions.py`: replace every `scripts/maintain/update_prek.py` example path with
  `scripts/hooks/sort-json-array.py` and the `update_prek` example names with `sort_json_array`.
- `README.md`: delete the "Tool installation (install-uv, install-hatch)" bullet (~line 76); delete the
  "[Installer Scripts](scripts/install/README.md)" bullet and its sub-bullets (~line 127); in the tree diagram
  (~lines 280-283) replace the `scripts/install/` subtree with `│   └── hooks/   # Custom prek hook scripts`.
- `roles/README.md:852`: delete the bullet linking `scripts/install/README.md`.
- `docs/RUN_PY_REFERENCE.md`: delete the "### Tool Installation" section (`install-uv`, `install-hatch`), the
  `install-uv` lines in the Makefile example (~229-240), the retry example (~498), the troubleshooting entry for
  `install-uv`/`install-hatch` (~694-706), and the `SCRIPTS_DIR` constant line (~398) if removed from `run.py`.
- `.ctx/ARCHITECTURE.md:96`: delete the `**Tool Installation**` bullet. `.ctx/BUILD.md:37-38`: delete both lines.
- `.claude/rules/readme-guidelines.md:24`: replace `scripts/install/` with `scripts/hooks/`.

Run: `git grep -n -E 'scripts/(env|install|installers|maintain)|install-uv|install-hatch|install_uv|install_hatch|loadenv|venvshell|python_diagnostic|update_prek|update_gitignore' -- ':!docs/plans/'`
Expected: no output.

- [ ] **Step 6: Acceptance — full-tree guard and hooks**

Run: `prek run check-leaks --all-files`
Expected: PASS.
Run: `prek run --all-files`
Expected: PASS.
Run: `scripts/hooks/uv-public.sh run --group test pytest`
Expected: PASS.
Run: `grep -o 'https://[^"/]*' uv.lock | sort -u`
Expected: exactly `https://files.pythonhosted.org` and `https://pypi.org`.

- [ ] **Step 7: Commit**

```bash
git add -A scripts run.py Makefile roles/git/templates/pre-commit.j2 docs .gitignore pyproject.toml README.md roles/README.md .ctx .claude/rules/readme-guidelines.md
git status --short   # confirm nothing unintended (no uv.lock churn, no inventory/ or vault files)
git commit -m "chore: remove internally-derived scripts and stale references

Drop scripts/env, scripts/install, and scripts/maintain plus the run.py
install-uv/install-hatch commands (which already pointed at a nonexistent
directory). Replace the git-template pre-commit hook with a generic prek
delegate and stub out the superseded repo-integration plan."
```

---

### Task 5: Publish (requires explicit user confirmation at each step)

**Files:** none (remote operations).

- [ ] **Step 1: Ask the user before pushing.** On approval: `git push -u origin leak-guard`, then open a PR to `main`
  (via `gh pr create` if `gh auth status -h github.com` succeeds; otherwise give the user the compare URL).
- [ ] **Step 2: Confirm CI is green on the PR** — `gitleaks`, `leak guard`, `ruff`, `mypy`, `interrogate`, `yamllint`,
  `codespell`, `pytest`. Note: lint CI previously could not resolve the internal mirror from GitHub runners, so these
  jobs may be going green for the first time; investigate any failure rather than assuming it is pre-existing.
- [ ] **Step 3: Archive and delete stale remote branches** (user approved deletion in brainstorming; re-confirm
  immediately before running):

```bash
for b in 2026_infra_revamp caddy_minimal hooks plex_bringup separate_inventory_repo; do
    git tag "archive/$b" "origin/$b"
done
git tag -l 'archive/*'                          # verify all five tags exist locally (never push these)
git push origin --delete 2026_infra_revamp caddy_minimal hooks plex_bringup separate_inventory_repo
git fetch --prune && git branch -r              # expect only origin/HEAD, origin/main, origin/leak-guard
```

- [ ] **Step 4: Post-merge check in a fresh Claude Code session in this repo:** `env | grep '^UV_'` should show the
  three public values from `.claude/settings.json`. If the work user-level values still win, record it in
  `CLAUDE-LESSONS.md` — the wrapper and the self-healing hook remain the effective guards.
