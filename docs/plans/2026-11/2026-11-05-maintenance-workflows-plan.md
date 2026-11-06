# Scheduled Maintenance Workflows Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Scheduled GitHub Actions workflows that open reviewable PRs refreshing prek hook revisions, `uv.lock` plus derived files, and the generated `.gitignore` block.

**Architecture:** One ported standalone script (`update_gitignore.py`), one shell script behind a local composite action that commits to an evergreen `maintenance/<name>` branch and opens or refreshes a PR with `gh`, and two workflows that wire them to `prek update` and `run.py lock-upgrade`. Spec: `~/dotfiles-personal/docs/plans/2026-11/2026-11-05-maintenance-workflows-design.md`.

**Tech Stack:** Python 3.12 (ruff target py39), bash, GitHub Actions, `uv`, `prek` 0.5.10, `gh`, pytest.

## Global Constraints

- Work only in the worktree `~/dotfiles-personal/.claude/worktrees/maintenance-workflows` (branch `worktree-maintenance-workflows`). Never `cd` out of it; run git plainly from there.
- The repo is public and guarded by the `check-leaks` hook. No committed file, test, doc, or commit message may name the author's work repository, its CI system, employer-internal hosts, or email addresses. Never bypass hooks (`--no-verify`).
- Python is always run through `uv` (`uv run ...`). Never run `ruff format`; `ruff check --fix` is fine.
- Python style (`.claude/rules/python-style.md`): `from __future__ import annotations` first, one import per line, single quotes inline, sphinx docstrings that are multi-line, no blank line between a class docstring and its first member, boxed `# ====` section headers, line width 120, scripts executed directly omit `__all__`.
- Standalone scripts under `scripts/` carry copies of the styling helpers from `run.py` (`# Text styling` section); `run.py` wins on disagreement.
- Tests: classes `TestX`, every method `-> None`, multi-line docstrings (capitalized, no trailing period), parametrize with tuple names.
- Workflow actions are limited to `actions/checkout@v4` and `astral-sh/setup-uv@v6`; the PR token secret is `MAINTENANCE_PR_TOKEN`; PRs target `main` from `maintenance/<name>`.
- Commit after each task; `git status` must be clean afterward. Prek hooks run on commit and may rewrite files (section headers, docstrings): re-stage and recommit rather than skipping them.

## Deviation from the design doc

`prek update` (this prek version has no `auto-update` command) natively supports `--cooldown-days`, tag and repo filters, `--jobs`, `--refresh`, and `--dry-run`, which is everything the ported wrapper script provided. The wrapper is therefore dropped (YAGNI) and the workflow calls `uv run prek update --cooldown-days 3` directly. The `.gitignore` workflow also omits `--force`. Task 3 updates the design doc to match.

## File Structure

| Path                                                            | Responsibility                                                       |
| --------------------------------------------------------------- | -------------------------------------------------------------------- |
| `scripts/codebase/update_gitignore.py`                          | Refresh the generated `.gitignore` block, preserving custom lines    |
| `.github/actions/open-maintenance-pr/open-pr.sh`                | Commit, force-push evergreen branch, open or refresh PR              |
| `.github/actions/open-maintenance-pr/action.yml`                | Composite action wrapping `open-pr.sh` (inputs to env)               |
| `.github/workflows/update-dependencies.yml`                     | Tuesday job: `prek update`, `lock-upgrade`, PR                       |
| `.github/workflows/update-gitignore.yml`                        | Monday job: gitignore refresh, PR                                    |
| `tests/unit/scripts/codebase/test_update_gitignore.py`          | Unit tests for the gitignore script                                  |
| `tests/unit/github/test_open_maintenance_pr.py`                 | Fixture-repo tests for `open-pr.sh` with a stubbed `gh`              |
| `tests/unit/github/test_maintenance_workflows.py`               | Structural guards for the workflows and action                       |
| `scripts/codebase/README.md`, `scripts/README.md`, `README.md`, `.ctx/BUILD.md`, `.ctx/ARCHITECTURE.md` | Docs                       |

---

## Task 1: `update_gitignore.py`

**Files:**
- Create: `scripts/codebase/update_gitignore.py` (mode 755)
- Create: `tests/unit/scripts/codebase/__init__.py` (empty), `tests/unit/scripts/codebase/test_update_gitignore.py`
- Modify: `tests/unit/scripts/test_script_scrub.py` (`SCRIPT_DIRS`, discovery assertion)

**Interfaces:**
- Produces (module-level, loaded by path in tests): `extract_templates(gitignore_content: str) -> list[str]`, `extract_custom_patterns(gitignore_content: str) -> list[str]`, `fetch_gitignore_content(templates: list[str]) -> str`, `generate_updated_gitignore(fresh_content: str, custom_patterns: list[str]) -> str`, `main(argv: Sequence[str] | None = None) -> int`, module attributes `urlopen`, `subprocess`.
- Behavior contract: `extract_templates` raises `ValueError` without the toptal URL; `extract_custom_patterns` raises `ValueError` without the end marker (never silently drops custom lines); fetch raises `RuntimeError` when every method fails or the content lacks the end marker; `main` returns 0 on success or up-to-date, 1 on any error.

- [ ] **Step 1: Write the failing tests**

Create the empty package file `tests/unit/scripts/codebase/__init__.py`, then `tests/unit/scripts/codebase/test_update_gitignore.py` with the content below.

```python
"""
Tests for the update_gitignore.py script
"""
from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from tests.conftest import unstyle

if TYPE_CHECKING:
    from types import ModuleType

SCRIPT_PATH = Path(__file__).parents[4] / 'scripts' / 'codebase' / 'update_gitignore.py'

TEMPLATES = 'macos,python,pycharm+all'
API_URL   = 'https://www.toptal.com/developers/gitignore/api/'
GENERATED = (
    f'# Created by {API_URL}{TEMPLATES}\n'
    f'# Edit at https://www.toptal.com/developers/gitignore?templates={TEMPLATES}\n'
    '\n'
    '### macOS ###\n'
    '.DS_Store\n'
    '\n'
    f'# End of {API_URL}{TEMPLATES}\n'
)
CUSTOM = '\n# Custom\n.claude/worktrees/\n\n*.local\n'


class FakeResponse:
    """
    Minimal stand-in for the context manager returned by ``urlopen``
    """
    def __init__(self, body: str) -> None:
        self._body = body

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body.encode('utf-8')


@pytest.fixture
def script() -> ModuleType:
    """
    Load the script as a module (it lives outside any package)
    """
    spec = importlib.util.spec_from_file_location('update_gitignore', SCRIPT_PATH)
    assert spec        is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestExtractTemplates:
    """
    Tests for extract_templates
    """
    @pytest.mark.parametrize(
        ('content', 'expected'),
        [
            (GENERATED,                                   ['macos', 'python', 'pycharm+all']),
            (f'# Created by {API_URL}rust-analyzer,a.b\n', ['rust-analyzer', 'a.b']),
            (f'x\n# Created by {API_URL}git\ny\n',         ['git']),
        ],
    )
    def test_parses_template_list(self, script: ModuleType, content: str, expected: list[str]) -> None:
        """
        Test that the template list is read from the embedded gitignore.io URL
        """
        assert script.extract_templates(content) == expected

    def test_missing_url_raises(self, script: ModuleType) -> None:
        """
        Test that a file without the gitignore.io URL is rejected
        """
        with pytest.raises(ValueError, match='gitignore.io URL'):
            script.extract_templates('*.pyc\n')


class TestExtractCustomPatterns:
    """
    Tests for extract_custom_patterns
    """
    def test_returns_lines_after_end_marker(self, script: ModuleType) -> None:
        """
        Test that custom lines are kept verbatim, minus leading and trailing blank lines
        """
        assert script.extract_custom_patterns(GENERATED + CUSTOM) == ['# Custom', '.claude/worktrees/', '', '*.local']

    @pytest.mark.parametrize('tail', ['', '\n', '\n\n   \n'])
    def test_no_custom_lines(self, script: ModuleType, tail: str) -> None:
        """
        Test that blank-only content after the marker yields no custom patterns
        """
        assert script.extract_custom_patterns(GENERATED + tail) == []

    def test_missing_end_marker_raises(self, script: ModuleType) -> None:
        """
        Test that a missing end marker is an error rather than silently dropping custom patterns
        """
        with pytest.raises(ValueError, match='end marker'):
            script.extract_custom_patterns(f'# Created by {API_URL}git\n.DS_Store\n')


class TestGenerateUpdatedGitignore:
    """
    Tests for generate_updated_gitignore
    """
    def test_without_custom_patterns(self, script: ModuleType) -> None:
        """
        Test that fresh content is returned with exactly one trailing newline
        """
        assert script.generate_updated_gitignore(GENERATED + '\n\n', []) == GENERATED

    def test_round_trip_preserves_custom_patterns(self, script: ModuleType) -> None:
        """
        Test that extracting then regenerating reproduces the original file
        """
        original = GENERATED + CUSTOM.replace('\n\n*.local', '\n*.local')
        custom   = script.extract_custom_patterns(original)
        assert script.generate_updated_gitignore(GENERATED, custom) == original


class TestFetchGitignoreContent:
    """
    Tests for fetch_gitignore_content
    """
    def test_urllib_success(self, script: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that urllib content is returned and the request URL joins the templates
        """
        seen: list[str] = []

        def fake_urlopen(url: str, timeout: float) -> FakeResponse:
            seen.append(url)
            return FakeResponse(GENERATED)

        monkeypatch.setattr(script, 'urlopen', fake_urlopen)
        assert script.fetch_gitignore_content(['macos', 'python']) == GENERATED
        assert seen == [f'{API_URL}macos,python']

    def test_falls_back_to_curl(self, script: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that a urllib failure falls back to curl against the same URL
        """
        def failing_urlopen(url: str, timeout: float) -> FakeResponse:
            raise OSError('certificate verify failed')

        calls: list[list[str]] = []

        def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, stdout=GENERATED, stderr='')

        monkeypatch.setattr(script, 'urlopen', failing_urlopen)
        monkeypatch.setattr(script.subprocess, 'run', fake_run)

        assert script.fetch_gitignore_content(['git']) == GENERATED
        assert calls[0][0] == 'curl'
        assert calls[0][-1] == f'{API_URL}git'

    def test_all_methods_fail(self, script: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that a curl failure after a urllib failure raises RuntimeError with the exit code
        """
        def failing_urlopen(url: str, timeout: float) -> FakeResponse:
            raise OSError('offline')

        def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(cmd, 22, stdout='', stderr='HTTP 404')

        monkeypatch.setattr(script, 'urlopen', failing_urlopen)
        monkeypatch.setattr(script.subprocess, 'run', fake_run)

        with pytest.raises(RuntimeError, match='curl exit 22'):
            script.fetch_gitignore_content(['git'])

    def test_curl_missing(self, script: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that an absent curl binary is reported as a fetch failure
        """
        def failing_urlopen(url: str, timeout: float) -> FakeResponse:
            raise OSError('offline')

        def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            raise FileNotFoundError('curl')

        monkeypatch.setattr(script, 'urlopen', failing_urlopen)
        monkeypatch.setattr(script.subprocess, 'run', fake_run)

        with pytest.raises(RuntimeError, match='urllib and curl both failed'):
            script.fetch_gitignore_content(['git'])

    def test_content_without_end_marker_rejected(self, script: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that truncated or error-page content is refused instead of overwriting the file
        """
        monkeypatch.setattr(script, 'urlopen', lambda url, timeout: FakeResponse('<html>rate limited</html>'))
        with pytest.raises(RuntimeError, match='end marker'):
            script.fetch_gitignore_content(['git'])


class TestMain:
    """
    Tests for main
    """
    @pytest.fixture
    def gitignore(self, tmp_path: Path) -> Path:
        """
        A .gitignore with a stale generated block and custom patterns
        """
        path = tmp_path / '.gitignore'
        path.write_text(GENERATED.replace('.DS_Store', '.OLD') + CUSTOM, encoding='utf-8')
        return path

    def test_updates_file_and_keeps_custom_patterns(
        self,
        script: ModuleType,
        gitignore: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that a changed upstream block is written and custom patterns survive
        """
        monkeypatch.setattr(script, 'fetch_gitignore_content', lambda templates: GENERATED)

        assert script.main(['--gitignore-path', str(gitignore)]) == 0

        text = gitignore.read_text(encoding='utf-8')
        assert '.DS_Store' in text
        assert '.OLD' not in text
        assert text.endswith('# Custom\n.claude/worktrees/\n\n*.local\n')
        assert 'Updated' in unstyle(capsys.readouterr().out)

    def test_already_up_to_date(
        self,
        script: ModuleType,
        gitignore: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that identical content leaves the file untouched and says so
        """
        current = gitignore.read_text(encoding='utf-8')
        monkeypatch.setattr(script, 'fetch_gitignore_content', lambda templates: current.split('\n# Custom')[0] + '\n')

        assert script.main(['--gitignore-path', str(gitignore)]) == 0
        assert gitignore.read_text(encoding='utf-8') == current
        assert 'already up to date' in unstyle(capsys.readouterr().out)

    def test_dry_run_does_not_write(
        self,
        script: ModuleType,
        gitignore: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that --dry-run reports the change without modifying the file
        """
        before = gitignore.read_text(encoding='utf-8')
        monkeypatch.setattr(script, 'fetch_gitignore_content', lambda templates: GENERATED)

        assert script.main(['--gitignore-path', str(gitignore), '--dry-run']) == 0
        assert gitignore.read_text(encoding='utf-8') == before
        assert 'Dry run' in unstyle(capsys.readouterr().out)

    def test_force_rewrites_identical_content(
        self,
        script: ModuleType,
        gitignore: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that --force reports an update even when nothing changed
        """
        current = gitignore.read_text(encoding='utf-8')
        monkeypatch.setattr(script, 'fetch_gitignore_content', lambda templates: current.split('\n# Custom')[0] + '\n')

        assert script.main(['--gitignore-path', str(gitignore), '--force']) == 0
        assert 'Updated' in unstyle(capsys.readouterr().out)

    def test_missing_file(self, script: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that a nonexistent .gitignore exits 1 with a message on stderr
        """
        assert script.main(['--gitignore-path', str(tmp_path / 'nope')]) == 1
        assert 'not found' in unstyle(capsys.readouterr().err)

    def test_file_without_gitignore_url(
        self,
        script: ModuleType,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that a hand-written .gitignore is rejected rather than overwritten
        """
        path = tmp_path / '.gitignore'
        path.write_text('*.pyc\n', encoding='utf-8')

        assert script.main(['--gitignore-path', str(path)]) == 1
        assert path.read_text(encoding='utf-8') == '*.pyc\n'
        assert 'gitignore.io URL' in unstyle(capsys.readouterr().err)

    def test_fetch_failure_leaves_file_untouched(
        self,
        script: ModuleType,
        gitignore: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Test that a fetch error exits 1 and does not modify the file
        """
        def failing_fetch(templates: list[str]) -> str:
            raise RuntimeError('offline')

        before = gitignore.read_text(encoding='utf-8')
        monkeypatch.setattr(script, 'fetch_gitignore_content', failing_fetch)

        assert script.main(['--gitignore-path', str(gitignore)]) == 1
        assert gitignore.read_text(encoding='utf-8') == before
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/scripts/codebase -q -p no:sugar`
Expected: collection or fixture error because `scripts/codebase/update_gitignore.py` does not exist.

- [ ] **Step 3: Write the script**

Create `scripts/codebase/update_gitignore.py` with exactly this content:

```python
#!/usr/bin/env python3
"""
Refresh the generated block of ``.gitignore`` from gitignore.io while preserving custom patterns.

The template list is read from the toptal.com URL embedded in the file's header comment. Fresh content is fetched
(``urllib``, falling back to ``curl``) and any custom patterns found after the generated block's end marker are
re-appended. A missing marker or a fetch that does not return a complete block aborts without touching the file.

Usage::

    uv run --no-project scripts/codebase/update_gitignore.py [--gitignore-path PATH] [--dry-run] [--force]
"""
from __future__ import annotations

import argparse
import functools
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from typing import TextIO
from typing import Union
from typing import cast
from urllib.request import urlopen

if TYPE_CHECKING:
    from collections.abc import Sequence


PathLike   = Union[Path, str]
StyleColor = Union[int, tuple[int, int, int], str]


# ====================================================================================================
# Console output + styling helpers (copied from run.py; run.py wins on disagreement)
# ====================================================================================================


NO_COLOR: bool = bool(os.getenv('NO_COLOR'))        # https://no-color.org: any non-empty value disables color

ANSI_COLOR: dict[str, int] = {
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


def _interpret_color(_color: StyleColor, offset: int = 0) -> str:
    """
    Resolve a color name, integer, or RGB tuple to an ANSI SGR parameter string.

    :param _color: color as a named string, 256-color int, or ``(r, g, b)`` tuple
    :param offset: offset added to the base code (0 for foreground, 10 for background)
    :return: ANSI SGR parameter fragment (e.g. ``"32"`` or ``"38;2;255;0;0"``)
    """
    if isinstance(_color, int):
        return f'{38 + offset};5;{_color:d}'
    if isinstance(_color, (tuple, list)):
        r, g, b = _color
        return f'{38 + offset};2;{r:d};{g:d};{b:d}'
    _color = cast('str', _color)
    return str(ANSI_COLOR[_color] + offset)


def style(
    text: Any = '',
    *,
    fg: StyleColor | None = None,
    bg: StyleColor | None = None,
    bold: bool | None = None,
    dim: bool | None = None,
    reset: bool = True,
) -> str:
    """
    Style text with ANSI escape codes. Returns the text unstyled when ``NO_COLOR`` is set.

    :param text: the string to style with ansi codes
    :param fg: foreground color
    :param bg: background color
    :param bold: enable or disable bold mode
    :param dim: enable or disable dim mode
    :param reset: add a reset-all code at the end of the string
    :raises TypeError: if invalid fg/bg color requested
    :return: styled text
    """
    if NO_COLOR:
        return str(text)
    if not isinstance(text, str):
        text = str(text)

    bits: list[str] = []
    if fg is not None:
        try:
            bits.append(f'\033[{_interpret_color(fg)}m')
        except KeyError:
            raise TypeError(f'Unknown color {fg!r}') from None
    if bg is not None:
        try:
            bits.append(f'\033[{_interpret_color(bg, 10)}m')
        except KeyError:
            raise TypeError(f'Unknown color {bg!r}') from None
    if bold is not None:
        bits.append(f'\033[{1 if bold else 22}m')
    if dim is not None:
        bits.append(f'\033[{2 if dim else 22}m')

    bits.append(text)
    if reset:
        bits.append(ANSI_RESET_ALL)
    return ''.join(bits)


def folduser(path: PathLike) -> str:
    """
    Does the opposite of :meth:`pathlib.Path.expanduser`, replacing the user's home directory with a "~"

    :param path: path
    :return: str folded path
    """
    home = str(Path.home())
    return str(path).replace(home, '~')


def pathstyle(path: PathLike, **opts: Any) -> str:
    """
    Style a file path in magenta with the home directory folded to ``~``

    :param path: the file path to style
    :return: the ANSI-styled path string
    """
    return style(folduser(path), fg='magenta', **opts)


def printf(
    text: str = '',
    *,
    fg: StyleColor | None = None,
    bold: bool | None = None,
    dim: bool | None = None,
    indent: int = 0,
    file: TextIO | None = None,
) -> None:
    """
    Print styled text with optional indentation (flushed so lines stay ordered with child-process output)

    :param text: the content to print
    :param fg: foreground color
    :param bold: enable or disable bold
    :param dim: enable or disable dim
    :param indent: number of leading spaces to prepend
    :param file: output stream (defaults to stdout)
    """
    print(style(textwrap.indent(text, ' ' * indent), fg=fg, bold=bold, dim=dim), file=file, flush=True)


# ====================================================================================================
# Constants
# ====================================================================================================


GITIGNORE_API_URL: str = 'https://www.toptal.com/developers/gitignore/api/'
FETCH_TIMEOUT:     int = 30

TEMPLATES_RE  = re.compile(re.escape(GITIGNORE_API_URL) + r'([A-Za-z0-9+,._-]+)')
END_MARKER_RE = re.compile(re.escape(f'# End of {GITIGNORE_API_URL}'))


# ====================================================================================================
# Core logic
# ====================================================================================================


def extract_templates(gitignore_content: str) -> list[str]:
    """
    Read the template list from the gitignore.io URL in the current ``.gitignore`` header.

    :param gitignore_content: content of the current ``.gitignore``
    :raises ValueError: if the gitignore.io URL is absent
    :return: template names, in file order
    """
    if m := TEMPLATES_RE.search(gitignore_content):
        return m.group(1).split(',')
    raise ValueError('Could not find the gitignore.io URL in the current .gitignore')


def extract_custom_patterns(gitignore_content: str) -> list[str]:
    """
    Extract the lines added after the generated block's end marker.

    Leading and trailing blank lines are dropped; interior blank lines are kept.

    :param gitignore_content: content of the current ``.gitignore``
    :raises ValueError: if the end marker is absent (so custom patterns can never be dropped silently)
    :return: custom lines
    """
    lines   = gitignore_content.splitlines()
    end_idx = next((i for i, line in enumerate(lines) if END_MARKER_RE.match(line)), None)
    if end_idx is None:
        raise ValueError('Could not find the gitignore.io end marker; refusing to risk dropping custom patterns')

    custom   = lines[end_idx + 1:]
    nonblank = [i for i, line in enumerate(custom) if line.strip()]
    return custom[nonblank[0]:nonblank[-1] + 1] if nonblank else []


def _require_end_marker(content: str) -> str:
    """
    Reject fetched content that lacks the end marker (an error page or truncated response).

    :param content: fetched gitignore.io content
    :raises RuntimeError: if the end marker is absent
    :return: ``content`` unchanged
    """
    if not any(END_MARKER_RE.match(line) for line in content.splitlines()):
        raise RuntimeError('Fetched content has no gitignore.io end marker; refusing to use it')
    return content


def fetch_gitignore_content(templates: list[str]) -> str:
    """
    Fetch fresh ``.gitignore`` content for ``templates``, trying ``urllib`` then ``curl``.

    :param templates: template names
    :raises RuntimeError: if every method fails or the content is incomplete
    :return: gitignore.io content
    """
    url = f'{GITIGNORE_API_URL}{",".join(templates)}'

    try:
        with urlopen(url, timeout=FETCH_TIMEOUT) as response:       # noqa: S310
            content = response.read().decode('utf-8')
    except OSError as e:
        printf(f'🟡 urllib failed ({e}); trying curl...', fg='bright_yellow', indent=3)
    else:
        return _require_end_marker(content)

    try:
        result = subprocess.run(
            ['curl', '--silent', '--show-error', '--location', '--fail', '--max-time', str(FETCH_TIMEOUT), url],
            check=False,
            capture_output=True,
            text=True,
            timeout=FETCH_TIMEOUT + 5,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        raise RuntimeError(f'Could not fetch {url} (urllib and curl both failed): {e}') from e
    if result.returncode != 0:
        raise RuntimeError(f'Could not fetch {url} (curl exit {result.returncode}): {result.stderr.strip()}')
    return _require_end_marker(result.stdout)


def generate_updated_gitignore(fresh_content: str, custom_patterns: list[str]) -> str:
    """
    Combine fresh gitignore.io content with preserved custom patterns.

    :param fresh_content: fresh content from gitignore.io
    :param custom_patterns: custom lines to append after a blank line
    :return: new ``.gitignore`` content
    """
    result = fresh_content.rstrip('\n') + '\n'
    if custom_patterns:
        result += '\n' + ''.join(f'{line}\n' for line in custom_patterns)
    return result


# ====================================================================================================
# Command-line interface
# ====================================================================================================


class Args(argparse.Namespace):
    """
    :class:`argparse.Namespace` annotated with the args supported by this script
    """
    gitignore_path: Path        # --gitignore-path
    dry_run:        bool        # --dry-run
    force:          bool        # --force


def build_parser() -> argparse.ArgumentParser:
    """
    Build the argument parser.

    :return: the configured :class:`argparse.ArgumentParser`
    """
    parser = argparse.ArgumentParser(
        description='Refresh the generated block of .gitignore from gitignore.io, preserving custom patterns',
        formatter_class=functools.partial(argparse.RawTextHelpFormatter, max_help_position=50),
        add_help=False,
    )

    def add_file_opts() -> None:
        file_opts = parser.add_argument_group('File options')
        file_opts.add_argument(
            '--gitignore-path',
            type=Path,
            default=Path('.gitignore'),
            metavar='PATH',
            help='Path to the .gitignore file (default: .gitignore)',
        )
    add_file_opts()

    def add_execution_opts() -> None:
        execution_opts = parser.add_argument_group('Execution options')
        execution_opts.add_argument('--dry-run', action='store_true', help='Show the result without writing the file')
        execution_opts.add_argument('--force', action='store_true', help='Write the file even if nothing changed')
    add_execution_opts()

    def add_other_opts() -> None:
        other_opts = parser.add_argument_group('Other options')
        other_opts.add_argument('-h', '--help', action='help', default=argparse.SUPPRESS,
                                help='Show this help message and exit')
    add_other_opts()

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """
    Script entry point.

    :param argv: command-line arguments (default: ``sys.argv[1:]``)
    :return: 0 on success or when already up to date, 1 on any error
    """
    args = build_parser().parse_args(argv, namespace=Args())

    if not args.gitignore_path.is_file():
        printf(f'❌ {pathstyle(args.gitignore_path)} not found', fg='bright_red', file=sys.stderr)
        return 1

    try:
        current   = args.gitignore_path.read_text(encoding='utf-8')
        templates = extract_templates(current)
        custom    = extract_custom_patterns(current)

        printf('🔄 Refreshing .gitignore from gitignore.io', fg='bright_cyan')
        printf(f'Templates: {", ".join(templates)}', indent=3)
        printf(f'Preserving {len(custom)} custom line(s)', indent=3)

        updated = generate_updated_gitignore(fetch_gitignore_content(templates), custom)
        if (updated == current) and (not args.force):
            printf(f'✅ {pathstyle(args.gitignore_path)} is already up to date', fg='bright_green')
            return 0

        if args.dry_run:
            printf(f'🔍 Dry run: would update {pathstyle(args.gitignore_path)}', fg='bright_cyan')
            printf(updated, dim=True)
            return 0

        args.gitignore_path.write_text(updated, encoding='utf-8')
    except (ValueError, RuntimeError, OSError) as e:
        printf(f'❌ {e}', fg='bright_red', file=sys.stderr)
        return 1

    printf(f'✅ Updated {pathstyle(args.gitignore_path)}', fg='bright_green')
    return 0


if __name__ == '__main__':
    sys.exit(main())
```

- [ ] **Step 4: Make it executable and run the tests**

Run: `chmod +x scripts/codebase/update_gitignore.py && uv run pytest tests/unit/scripts/codebase -q -p no:sugar`
Expected: all pass. If `test_updates_file_and_keeps_custom_patterns` shows a wrong tail, re-check `generate_updated_gitignore` against `CUSTOM` in the test.

- [ ] **Step 5: Extend the leak-scrub test to cover the new directory**

In `tests/unit/scripts/test_script_scrub.py`, change `SCRIPT_DIRS` to
`[REPO_ROOT / 'scripts' / 'install', REPO_ROOT / 'scripts' / 'env', REPO_ROOT / 'scripts' / 'codebase']`, add `'update_gitignore.py'` to the set asserted in `test_scripts_are_discovered`, and update the class docstring and module docstring wording from "scripts/install and scripts/env" to include `scripts/codebase`.

Run: `uv run pytest tests/unit/scripts/test_script_scrub.py -q -p no:sugar`
Expected: PASS, with a `test_script_has_no_internal_markers[update_gitignore.py]` case.

- [ ] **Step 6: Lint, then smoke-test against the real file**

Run: `uv run ruff check --fix scripts/codebase tests/unit/scripts/codebase tests/unit/scripts/test_script_scrub.py && uv run mypy scripts/codebase/update_gitignore.py tests/unit/scripts/codebase`
Expected: no remaining findings (ruff may reorder imports; if INP001 fires for the new directory, mirror how `scripts/hooks` avoids it rather than adding an `__init__.py`).

Run: `uv run scripts/codebase/update_gitignore.py --dry-run`
Expected: exit 0 with either "already up to date" or a dry-run listing; `git status` shows `.gitignore` unmodified. If the real fetch fails offline, that is acceptable here; the unit tests are the gate.

- [ ] **Step 7: Commit**

```bash
git add scripts/codebase/update_gitignore.py tests/unit/scripts/codebase tests/unit/scripts/test_script_scrub.py
git commit -m "Add update_gitignore.py script to refresh the generated .gitignore block"
```
Expected: prek hooks pass. If they rewrite files (docstrings, section headers), `git add` the rewrites and commit again.

---

## Task 2: `open-maintenance-pr` composite action

**Files:**
- Create: `.github/actions/open-maintenance-pr/open-pr.sh` (mode 755), `.github/actions/open-maintenance-pr/action.yml`
- Create: `tests/unit/github/__init__.py` (empty), `tests/unit/github/test_open_maintenance_pr.py`

**Interfaces:**
- `open-pr.sh` reads environment variables `BRANCH`, `PATHS` (space-separated), `TITLE`, `BODY`, `COMMIT_MESSAGE` (all required), `BASE_BRANCH` (default `main`). It needs `git` with push access to `origin` and `gh` (with `GH_TOKEN`) on `PATH`. Exit 0 when nothing changed (no push, no `gh` call); otherwise commits, force-pushes `HEAD:refs/heads/$BRANCH`, then runs `gh pr list ... --jq '.[0].number // empty'` followed by `gh pr edit <n> --title T --body B` or `gh pr create --base B --head BR --title T --body B`.
- `action.yml` inputs: `branch`, `paths`, `title`, `body`, `commit-message`, `token` (required); `base-branch` (default `main`). Consumed by Task 3 workflows.

- [ ] **Step 1: Write the failing tests**

Create the empty `tests/unit/github/__init__.py`, then `tests/unit/github/test_open_maintenance_pr.py`:

```python
"""
Tests for the open-maintenance-pr action script, run against a throwaway origin/work repo pair with a stubbed gh
"""
from __future__ import annotations

import os
import stat
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).parents[3] / '.github' / 'actions' / 'open-maintenance-pr' / 'open-pr.sh'

BRANCH = 'maintenance/update-things'

RunScript = Callable[..., subprocess.CompletedProcess[str]]

GIT_ENV = {
    **os.environ,
    'GIT_CONFIG_GLOBAL':   os.devnull,
    'GIT_CONFIG_SYSTEM':   os.devnull,
    'GIT_AUTHOR_NAME':     'Test',
    'GIT_AUTHOR_EMAIL':    'test@example.com',
    'GIT_COMMITTER_NAME':  'Test',
    'GIT_COMMITTER_EMAIL': 'test@example.com',
}

FAKE_GH = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$FAKE_GH_LOG"
if [[ "$1 $2" == "pr list" && -n "${FAKE_GH_NUMBER:-}" ]]; then
  echo "$FAKE_GH_NUMBER"
fi
"""


def git(cwd: Path, *args: str) -> str:
    """
    Run git in ``cwd`` with the isolated environment and return stripped stdout
    """
    result = subprocess.run(['git', *args], cwd=cwd, env=GIT_ENV, check=True, capture_output=True, text=True)
    return result.stdout.strip()


@pytest.fixture
def origin(tmp_path: Path) -> Path:
    """
    A bare origin repository
    """
    path = tmp_path / 'origin.git'
    git(tmp_path, 'init', '--bare', '--initial-branch=main', str(path))
    return path


@pytest.fixture
def work(tmp_path: Path, origin: Path) -> Path:
    """
    A clone of the origin with one pushed commit on main containing tracked.txt and other.txt
    """
    path = tmp_path / 'work'
    git(tmp_path, 'clone', str(origin), str(path))
    (path / 'tracked.txt').write_text('base\n', encoding='utf-8')
    (path / 'other.txt').write_text('base\n', encoding='utf-8')
    git(path, 'add', '-A')
    git(path, 'commit', '-m', 'base')
    git(path, 'push', 'origin', 'main')
    return path


@pytest.fixture
def gh_log(tmp_path: Path) -> Path:
    """
    Path of the file the stub gh appends its argument lines to
    """
    return tmp_path / 'gh.log'


@pytest.fixture
def run_script(tmp_path: Path, work: Path, gh_log: Path) -> RunScript:
    """
    Return a callable that runs open-pr.sh in the work clone with the stub gh first on PATH
    """
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    fake_gh = bin_dir / 'gh'
    fake_gh.write_text(FAKE_GH, encoding='utf-8')
    fake_gh.chmod(fake_gh.stat().st_mode | stat.S_IEXEC)

    def _run(*, paths: str = 'tracked.txt', pr_number: str = '', **overrides: str) -> subprocess.CompletedProcess[str]:
        env = {
            **GIT_ENV,
            'PATH':           f'{bin_dir}{os.pathsep}{os.environ["PATH"]}',
            'FAKE_GH_LOG':    str(gh_log),
            'FAKE_GH_NUMBER': pr_number,
            'BRANCH':         BRANCH,
            'PATHS':          paths,
            'TITLE':          'Update things',
            'BODY':           'Body text',
            'COMMIT_MESSAGE': 'chore: update things',
            **overrides,
        }
        return subprocess.run(['bash', str(SCRIPT_PATH)], cwd=work, env=env, check=False, capture_output=True, text=True)

    return _run


def gh_calls(gh_log: Path) -> list[str]:
    """
    Argument lines recorded by the stub gh (empty if it was never called)
    """
    return gh_log.read_text(encoding='utf-8').splitlines() if gh_log.exists() else []


def remote_branches(origin: Path) -> list[str]:
    """
    Names of the maintenance branches present on the origin
    """
    return git(origin, 'for-each-ref', '--format=%(refname:short)', 'refs/heads/maintenance').splitlines()


class TestOpenMaintenancePr:
    """
    Tests for open-pr.sh
    """
    def test_no_changes_is_a_noop(self, run_script: RunScript, origin: Path, gh_log: Path) -> None:
        """
        Test that an unchanged tree pushes nothing and never calls gh
        """
        result = run_script()

        assert result.returncode == 0
        assert 'already up to date' in result.stdout
        assert remote_branches(origin) == []
        assert gh_calls(gh_log) == []

    def test_changes_outside_paths_are_ignored(self, run_script: RunScript, work: Path, origin: Path) -> None:
        """
        Test that a modified file not listed in PATHS does not trigger a commit
        """
        (work / 'other.txt').write_text('changed\n', encoding='utf-8')

        assert run_script(paths='tracked.txt').returncode == 0
        assert remote_branches(origin) == []

    def test_change_pushes_branch_and_creates_pr(
        self, run_script: RunScript, work: Path, origin: Path, gh_log: Path,
    ) -> None:
        """
        Test that a change is committed, force-pushed one commit ahead of main, and opened as a new PR
        """
        (work / 'tracked.txt').write_text('updated\n', encoding='utf-8')

        result = run_script()

        assert result.returncode == 0, result.stderr
        assert remote_branches(origin) == [BRANCH]
        assert git(origin, 'rev-list', '--count', f'main..{BRANCH}') == '1'
        assert git(origin, 'show', f'{BRANCH}:tracked.txt') == 'updated'
        assert git(origin, 'log', '-1', '--format=%s', BRANCH) == 'chore: update things'

        calls = gh_calls(gh_log)
        assert calls[0].startswith('pr list --head maintenance/update-things --base main')
        assert calls[1] == f'pr create --base main --head {BRANCH} --title Update things --body Body text'

    def test_existing_pr_is_edited(self, run_script: RunScript, work: Path, gh_log: Path) -> None:
        """
        Test that an open PR for the branch is refreshed rather than duplicated
        """
        (work / 'tracked.txt').write_text('updated\n', encoding='utf-8')

        assert run_script(pr_number='7').returncode == 0

        calls = gh_calls(gh_log)
        assert calls[1] == 'pr edit 7 --title Update things --body Body text'
        assert not any(call.startswith('pr create') for call in calls)

    def test_untracked_file_under_a_listed_directory_is_included(
        self, run_script: RunScript, work: Path, origin: Path,
    ) -> None:
        """
        Test that new files under a listed path are staged, not only modifications
        """
        (work / 'generated').mkdir()
        (work / 'generated' / 'new.txt').write_text('new\n', encoding='utf-8')

        assert run_script(paths='generated').returncode == 0
        assert git(origin, 'show', f'{BRANCH}:generated/new.txt') == 'new'

    def test_rerun_force_pushes_a_single_commit(self, run_script: RunScript, work: Path, origin: Path) -> None:
        """
        Test that a second run from main replaces the branch instead of stacking commits
        """
        (work / 'tracked.txt').write_text('first\n', encoding='utf-8')
        assert run_script().returncode == 0

        git(work, 'reset', '--hard', 'origin/main')
        (work / 'tracked.txt').write_text('second\n', encoding='utf-8')
        assert run_script().returncode == 0

        assert git(origin, 'rev-list', '--count', f'main..{BRANCH}') == '1'
        assert git(origin, 'show', f'{BRANCH}:tracked.txt') == 'second'

    @pytest.mark.parametrize('missing', ['BRANCH', 'PATHS', 'TITLE', 'BODY', 'COMMIT_MESSAGE'])
    def test_missing_required_variable_fails(self, run_script: RunScript, missing: str) -> None:
        """
        Test that each required variable is enforced with a message naming it
        """
        result = run_script(**{missing: ''})

        assert result.returncode != 0
        assert missing in result.stderr
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/github/test_open_maintenance_pr.py -q -p no:sugar`
Expected: failures (the script does not exist, `bash` exits 127).

- [ ] **Step 3: Write the script**

Create `.github/actions/open-maintenance-pr/open-pr.sh`:

```bash
#!/usr/bin/env bash
# Commit changes under PATHS to an evergreen branch and open (or refresh) a pull request for it.
#
# Environment: BRANCH PATHS TITLE BODY COMMIT_MESSAGE [BASE_BRANCH=main]
# Requires: git with push access to origin (the caller's checkout supplies the credentials) and gh with GH_TOKEN set.
#
# The job checks out BASE_BRANCH, so the new commit sits directly on top of it and the force-pushed branch is always
# exactly one commit ahead: an evergreen branch that carries only the latest automated change.
set -euo pipefail

: "${BRANCH:?BRANCH is required}"
: "${PATHS:?PATHS is required}"
: "${TITLE:?TITLE is required}"
: "${BODY:?BODY is required}"
: "${COMMIT_MESSAGE:?COMMIT_MESSAGE is required}"
BASE_BRANCH="${BASE_BRANCH:-main}"

read -r -a paths <<< "$PATHS"

if [[ -z "$(git status --porcelain -- "${paths[@]}")" ]]; then
  echo "No changes in ${PATHS}; already up to date"
  exit 0
fi

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git add -A -- "${paths[@]}"
git commit --quiet -m "$COMMIT_MESSAGE"
git push --force origin "HEAD:refs/heads/${BRANCH}"

number="$(gh pr list --head "$BRANCH" --base "$BASE_BRANCH" --state open --json number --jq '.[0].number // empty')"
if [[ -n "$number" ]]; then
  echo "Refreshing pull request #${number}"
  gh pr edit "$number" --title "$TITLE" --body "$BODY"
else
  echo "Opening pull request ${BRANCH} -> ${BASE_BRANCH}"
  gh pr create --base "$BASE_BRANCH" --head "$BRANCH" --title "$TITLE" --body "$BODY"
fi
```

Run: `chmod +x .github/actions/open-maintenance-pr/open-pr.sh`

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/github/test_open_maintenance_pr.py -q -p no:sugar`
Expected: all pass. Note `:?` messages name the variable (`BRANCH: BRANCH is required`), satisfying the parametrized check.

- [ ] **Step 5: Write the composite action**

Create `.github/actions/open-maintenance-pr/action.yml`. Inputs reach the script through `env:`, never interpolated into the shell text, so a PR title or body cannot inject commands.

```yaml
---
name: Open maintenance pull request
description: >-
  Commit changes under the given paths to an evergreen branch, force-push it, and open or refresh a pull request
  against the base branch. The calling job's checkout must use the same token (actions/checkout `token:`) so the push
  authenticates as that token's owner and the resulting pull request triggers workflows.

inputs:
  branch:
    description: Evergreen head branch, for example maintenance/update-dependencies
    required: true
  paths:
    description: Space-separated paths to inspect and stage
    required: true
  title:
    description: Pull request title
    required: true
  body:
    description: Pull request body (Markdown)
    required: true
  commit-message:
    description: Commit message
    required: true
  base-branch:
    description: Branch the pull request targets
    required: false
    default: main
  token:
    description: Token gh uses to open or edit the pull request
    required: true

runs:
  using: composite
  steps:
    - name: Commit, push, and open or refresh the pull request
      shell: bash
      env:
        GH_TOKEN: ${{ inputs.token }}
        BRANCH: ${{ inputs.branch }}
        PATHS: ${{ inputs.paths }}
        TITLE: ${{ inputs.title }}
        BODY: ${{ inputs.body }}
        COMMIT_MESSAGE: ${{ inputs.commit-message }}
        BASE_BRANCH: ${{ inputs.base-branch }}
      run: bash "${{ github.action_path }}/open-pr.sh"
```

Run: `uvx yamllint .github/actions`
Expected: no output.

- [ ] **Step 6: Lint and commit**

Run: `uv run ruff check --fix tests/unit/github && uv run mypy tests/unit/github && uv run prek run shellcheck shfmt --files .github/actions/open-maintenance-pr/open-pr.sh` (use the hook ids from `.pre-commit-config.yaml` if they differ; `uv run prek list` shows them).
Expected: clean. Fix any shellcheck or shfmt findings in the script, then rerun Step 4.

```bash
git add .github/actions tests/unit/github
git commit -m "Add open-maintenance-pr composite action with fixture-repo tests"
```

---

## Task 3: Workflows, structural guard tests, and design-doc sync

**Files:**
- Create: `.github/workflows/update-dependencies.yml`, `.github/workflows/update-gitignore.yml`
- Create: `tests/unit/github/test_maintenance_workflows.py`
- Modify: `docs/plans/2026-11/2026-11-05-maintenance-workflows-design.md`

**Interfaces:**
- Consumes: `./.github/actions/open-maintenance-pr` and its inputs (Task 2); `uv run --no-project scripts/codebase/update_gitignore.py` (Task 1); `uv run prek update --cooldown-days 3`; `uv run run.py lock-upgrade` (already in `run.py`; upgrades `uv.lock`, then regenerates `requirements.txt` and re-syncs hook dependency pins through prek).
- Both workflows define a single job named `update`, so the guard tests can address `jobs.update`.

- [ ] **Step 1: Write the failing guard tests**

Create `tests/unit/github/test_maintenance_workflows.py`:

```python
"""
Structural guards for the scheduled maintenance workflows and their composite action

The workflows cannot be executed locally, so these assert the properties whose violation fails silently in CI: a missing
PR token (PRs that never trigger checks), a job running off a non-main ref, references to scripts that moved, and
action inputs that drifted from the workflow call sites.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT     = Path(__file__).resolve().parents[3]
WORKFLOWS_DIR = REPO_ROOT / '.github' / 'workflows'
ACTION_DIR    = REPO_ROOT / '.github' / 'actions' / 'open-maintenance-pr'
WORKFLOWS     = ['update-dependencies.yml', 'update-gitignore.yml']
TOKEN_EXPR    = '${{ secrets.MAINTENANCE_PR_TOKEN }}'
ACTION_REF    = './.github/actions/open-maintenance-pr'
SCRIPT_RE     = re.compile(r'uv run (?:--no-project )?(\S+\.py)')


def load_workflow(name: str) -> dict[str, Any]:
    """
    Parse a workflow file (PyYAML reads the ``on`` key as boolean ``True``; normalize it back)
    """
    data = yaml.safe_load((WORKFLOWS_DIR / name).read_text(encoding='utf-8'))
    data['on'] = data.pop(True, data.get('on'))
    return data


def load_action() -> dict[str, Any]:
    """
    Parse the composite action definition
    """
    return yaml.safe_load((ACTION_DIR / 'action.yml').read_text(encoding='utf-8'))


@pytest.mark.parametrize('name', WORKFLOWS)
class TestMaintenanceWorkflows:
    """
    Tests for the scheduled maintenance workflows
    """
    def test_runs_on_a_weekly_schedule_and_manually(self, name: str) -> None:
        """
        Test that the workflow has exactly one cron entry and can be dispatched by hand
        """
        triggers = load_workflow(name)['on']

        assert 'workflow_dispatch' in triggers
        assert len(triggers['schedule']) == 1
        assert len(triggers['schedule'][0]['cron'].split()) == 5

    def test_token_is_read_only_by_default(self, name: str) -> None:
        """
        Test that GITHUB_TOKEN stays read-only because writes go through the PR token
        """
        assert load_workflow(name)['permissions'] == {'contents': 'read'}

    def test_runs_are_serialized(self, name: str) -> None:
        """
        Test that overlapping runs queue instead of racing on the evergreen branch
        """
        concurrency = load_workflow(name)['concurrency']

        assert concurrency['group'] == Path(name).stem
        assert concurrency['cancel-in-progress'] is False

    def test_job_only_runs_on_main(self, name: str) -> None:
        """
        Test that a manual dispatch from another branch cannot open a PR containing that branch's changes
        """
        assert load_workflow(name)['jobs']['update']['if'] == "github.ref == 'refs/heads/main'"

    def test_first_step_requires_the_pr_token(self, name: str) -> None:
        """
        Test that a missing secret fails loudly instead of silently falling back to the default token
        """
        first = load_workflow(name)['jobs']['update']['steps'][0]

        assert first['env'] == {'TOKEN': TOKEN_EXPR}
        assert 'MAINTENANCE_PR_TOKEN' in first['run']

    def test_checkout_uses_the_pr_token(self, name: str) -> None:
        """
        Test that the push authenticates as the PR token's owner so the PR triggers other workflows
        """
        steps    = load_workflow(name)['jobs']['update']['steps']
        checkout = next(step for step in steps if step.get('uses', '').startswith('actions/checkout@'))

        assert checkout['with']['token'] == TOKEN_EXPR

    def test_final_step_calls_the_action_with_valid_inputs(self, name: str) -> None:
        """
        Test that the last step uses the composite action, passing every required input and no unknown one
        """
        last   = load_workflow(name)['jobs']['update']['steps'][-1]
        inputs = load_action()['inputs']
        given  = set(last['with'])

        assert last['uses'] == ACTION_REF
        assert last['with']['token'] == TOKEN_EXPR
        assert {key for key, spec in inputs.items() if spec.get('required')} <= given
        assert given <= set(inputs)

    def test_referenced_scripts_exist(self, name: str) -> None:
        """
        Test that every ``uv run <script>.py`` target exists in the repository
        """
        runs    = [step['run'] for step in load_workflow(name)['jobs']['update']['steps'] if 'run' in step]
        scripts = [match for run in runs for match in SCRIPT_RE.findall(run)]

        assert scripts, 'expected at least one uv-run script'
        for script in scripts:
            assert (REPO_ROOT / script).is_file(), script


class TestCompositeAction:
    """
    Tests for the open-maintenance-pr composite action
    """
    def test_is_composite_and_calls_the_shipped_script(self) -> None:
        """
        Test that the action runs open-pr.sh and that the script is present and executable
        """
        action = load_action()
        script = ACTION_DIR / 'open-pr.sh'

        assert action['runs']['using'] == 'composite'
        assert 'open-pr.sh' in action['runs']['steps'][0]['run']
        assert script.is_file()
        assert script.stat().st_mode & 0o111

    def test_inputs_reach_the_script_via_env_not_shell_text(self) -> None:
        """
        Test that no input is interpolated into the shell command (script injection guard)
        """
        run = load_action()['runs']['steps'][0]['run']

        assert 'inputs.' not in run
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/github/test_maintenance_workflows.py -q -p no:sugar`
Expected: the workflow-parametrized tests fail with `FileNotFoundError`; the `TestCompositeAction` tests pass.

- [ ] **Step 3: Write `update-dependencies.yml`**

```yaml
---
name: Update dependencies
on:
  schedule:
    - cron: "0 9 * * 2"   # Tuesdays, 09:00 UTC
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: update-dependencies
  cancel-in-progress: false

jobs:

  update:
    name: prek hooks, uv.lock, requirements
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      # Without the PAT the checkout would fall back to GITHUB_TOKEN and the PR would never trigger lint/leak checks
      - name: Require MAINTENANCE_PR_TOKEN
        env:
          TOKEN: ${{ secrets.MAINTENANCE_PR_TOKEN }}
        run: test -n "$TOKEN" || { echo "::error::MAINTENANCE_PR_TOKEN secret is not set"; exit 1; }
      - uses: actions/checkout@v4
        with:
          token: ${{ secrets.MAINTENANCE_PR_TOKEN }}
      - uses: astral-sh/setup-uv@v6
      - name: Install dependencies
        run: uv sync --group lint
      # Skips releases younger than three days: a supply-chain guard against freshly published (or hijacked) versions
      - name: Update prek hook revisions
        run: uv run prek update --cooldown-days 3
      # Upgrades uv.lock, then regenerates requirements.txt and re-syncs hook dependency pins from the new lock
      - name: Upgrade uv.lock and regenerate derived files
        run: uv run run.py lock-upgrade
      - uses: ./.github/actions/open-maintenance-pr
        with:
          branch: maintenance/update-dependencies
          paths: .pre-commit-config.yaml uv.lock requirements.txt
          title: "chore: update dependencies (prek hooks, uv.lock, requirements)"
          commit-message: |
            chore: update dependencies (prek hooks, uv.lock, requirements)

            Automated by the scheduled "Update dependencies" workflow:
              - prek update --cooldown-days 3 (hook revisions)
              - uv lock --upgrade (Python package dependencies)
              - regenerated requirements.txt and synced hook dependency pins from uv.lock
          body: |
            ## Automated dependency update

            Opened by the scheduled `Update dependencies` workflow.

            - `prek update --cooldown-days 3`: hook revisions in `.pre-commit-config.yaml`
            - `uv lock --upgrade`: `uv.lock`
            - `run.py lock-upgrade` regenerated `requirements.txt` and synced hook dependency pins

            Review the diff and merge if it looks good. This PR tracks the evergreen `maintenance/update-dependencies`
            branch: if the workflow runs again before this is merged, the branch is force-updated and this PR is
            refreshed.
          token: ${{ secrets.MAINTENANCE_PR_TOKEN }}
```

- [ ] **Step 4: Write `update-gitignore.yml`**

```yaml
---
name: Update gitignore
on:
  schedule:
    - cron: "0 9 * * 1"   # Mondays, 09:00 UTC
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: update-gitignore
  cancel-in-progress: false

jobs:

  update:
    name: gitignore.io patterns
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      # Without the PAT the checkout would fall back to GITHUB_TOKEN and the PR would never trigger lint/leak checks
      - name: Require MAINTENANCE_PR_TOKEN
        env:
          TOKEN: ${{ secrets.MAINTENANCE_PR_TOKEN }}
        run: test -n "$TOKEN" || { echo "::error::MAINTENANCE_PR_TOKEN secret is not set"; exit 1; }
      - uses: actions/checkout@v4
        with:
          token: ${{ secrets.MAINTENANCE_PR_TOKEN }}
      - uses: astral-sh/setup-uv@v6
      - name: Refresh .gitignore from gitignore.io
        run: uv run --no-project scripts/codebase/update_gitignore.py
      - uses: ./.github/actions/open-maintenance-pr
        with:
          branch: maintenance/update-gitignore
          paths: .gitignore
          title: "chore: update .gitignore from gitignore.io"
          commit-message: |
            chore: update .gitignore from gitignore.io

            Automated by the scheduled "Update gitignore" workflow; custom patterns below the generated block are
            preserved.
          body: |
            ## Automated .gitignore update

            Opened by the scheduled `Update gitignore` workflow, which regenerates the gitignore.io block from the
            templates named in the file header and keeps the custom patterns below it.

            Review the diff and merge if it looks good. This PR tracks the evergreen `maintenance/update-gitignore`
            branch: if the workflow runs again before this is merged, the branch is force-updated and this PR is
            refreshed.
          token: ${{ secrets.MAINTENANCE_PR_TOKEN }}
```

- [ ] **Step 5: Run the guard tests and lint the YAML**

Run: `uv run pytest tests/unit/github -q -p no:sugar && uvx yamllint .github`
Expected: all pass, yamllint silent. If yamllint rejects the inline `# ...` comment spacing after the cron value, follow its message (one or two spaces before `#`).

- [ ] **Step 6: Sync the design doc with the deviations**

Read `docs/plans/2026-11/2026-11-05-maintenance-workflows-design.md`, then edit it so it matches what was built:
- Scope **In:** drop "a prek auto-update script,".
- Replace the whole `### 1. scripts/codebase/update_prek.py` section with `### 1. prek hook updates (no script)`: the workflow calls `prek update --cooldown-days 3` directly; prek 0.5.10 natively provides the tag and repo filters, `--jobs`, `--refresh`, and `--dry-run` that a wrapper would re-expose, so no wrapper is ported.
- In the gitignore script section: public symbols are `extract_templates`, `extract_custom_patterns`, `fetch_gitignore_content`, `generate_updated_gitignore`; add that a missing end marker raises instead of dropping custom patterns, fetched content without the end marker is refused, and `curl` runs with `--fail`.
- In the workflows section: dependencies step is `uv run prek update --cooldown-days 3`; the gitignore step is `uv run --no-project scripts/codebase/update_gitignore.py` with no `--force`; both jobs are guarded by `github.ref == 'refs/heads/main'` and begin with a step that fails when `MAINTENANCE_PR_TOKEN` is unset.
- In the tests section: replace the `run_autoupdate` / `main` mention with the fixture-repo tests for `open-pr.sh` (stubbed `gh`) and the structural workflow guard tests; "curl and urllib are mocked".

- [ ] **Step 7: Commit**

```bash
git add .github/workflows tests/unit/github docs/plans/2026-11/2026-11-05-maintenance-workflows-design.md
git commit -m "Add scheduled dependency and gitignore update workflows"
```

---

## Task 4: Documentation and full verification

**Files:**
- Create: `scripts/codebase/README.md`
- Modify: `scripts/README.md`, `README.md`, `.ctx/BUILD.md`, `.ctx/ARCHITECTURE.md`

- [ ] **Step 1: Create `scripts/codebase/README.md`**

Facts must match the implemented code; if Task 1 changed a flag or message, correct the text here.

```markdown
[Project Root](../../README.md) > [Scripts](../README.md) > **Codebase**

# Codebase Scripts

Scripts that keep generated, tracked files current. The scheduled
[`Update gitignore`](../../.github/workflows/update-gitignore.yml) workflow runs `update_gitignore.py`.

| Script                                           | Purpose                                                                           |
| ------------------------------------------------ | --------------------------------------------------------------------------------- |
| [`update_gitignore.py`](update_gitignore.py)     | Refresh the gitignore.io block of `.gitignore`, preserving custom patterns        |

## `update_gitignore.py`

Reads the template list from the toptal.com URL in the `.gitignore` header, fetches fresh content (`urllib`, falling
back to `curl`), and re-appends the custom lines found after the generated block's end marker.

```
uv run --no-project scripts/codebase/update_gitignore.py [--gitignore-path PATH] [--dry-run] [--force]
```

| Option             | Description                                                    |
| ------------------ | -------------------------------------------------------------- |
| `--gitignore-path` | File to refresh (default: `.gitignore`)                        |
| `--dry-run`        | Print the result without writing                               |
| `--force`          | Write (and report an update) even when nothing changed        |

Exit codes: `0` updated or already up to date, `1` on any error. The file is never modified on error: a missing
gitignore.io URL, a missing end marker (which would otherwise drop custom patterns), and fetched content without the end
marker (an error page or truncated response) are all refused.

| Symbol                         | Signature                                          | Description                                          |
| ------------------------------ | -------------------------------------------------- | ---------------------------------------------------- |
| `extract_templates`            | `(gitignore_content: str) -> list[str]`            | Template names from the embedded URL                 |
| `extract_custom_patterns`      | `(gitignore_content: str) -> list[str]`            | Lines after the end marker, outer blank lines dropped |
| `fetch_gitignore_content`      | `(templates: list[str]) -> str`                    | Fetch fresh content via `urllib`, then `curl`        |
| `generate_updated_gitignore`   | `(fresh_content: str, custom_patterns: list[str]) -> str` | Fresh block plus preserved custom lines       |

## Scheduled workflows

| Workflow                                                                      | Schedule (UTC) | Branch                            | Updates                                            |
| ----------------------------------------------------------------------------- | -------------- | --------------------------------- | -------------------------------------------------- |
| [`update-dependencies.yml`](../../.github/workflows/update-dependencies.yml) | Tuesdays 09:00 | `maintenance/update-dependencies` | prek hook revisions, `uv.lock`, `requirements.txt` |
| [`update-gitignore.yml`](../../.github/workflows/update-gitignore.yml)       | Mondays 09:00  | `maintenance/update-gitignore`    | `.gitignore`                                       |

Each run force-pushes one commit on top of `main` to its evergreen branch and opens, or refreshes, a pull request
against `main` through the
[`open-maintenance-pr`](../../.github/actions/open-maintenance-pr/action.yml) composite action. Both can also be started
by hand (`gh workflow run "Update gitignore"`) and only run from `main`.

### One-time setup

Pull requests opened with the default `GITHUB_TOKEN` do not trigger other workflows, so the maintenance PRs would get no
lint or leak checks. The workflows therefore push and open PRs with a personal access token:

1. Create a fine-grained token limited to this repository with **Contents: read and write** and **Pull requests: read
   and write**.
1. Store it as the Actions secret `MAINTENANCE_PR_TOKEN`.

Both workflows fail at their first step with an explicit error while the secret is unset. Fine-grained tokens expire (at
most one year); a lapsed token fails the run at the push step, so renew the secret then.

## Dependencies

`update_gitignore.py` is standard-library only (`curl` is an optional fallback). The workflows additionally use `uv`,
`prek`, and `gh`, all present on `ubuntu-latest` runners or installed from the `lint` dependency group.
```

(Keep the fenced blocks as real fences in the file; the outer fence above is only for this plan.)

- [ ] **Step 2: Update the index and overview docs**

- `scripts/README.md`: add the table row ``| [`codebase/`](codebase/) | `update_gitignore.py`: refreshes the generated `.gitignore` block |`` (alphabetically first), add `- [Codebase scripts](codebase/README.md)` to "Subdirectory READMEs", and add "codebase maintenance" to the intro sentence's list.
- `README.md`: add a ``| [`scripts/codebase/`](scripts/codebase/) | Scheduled `.gitignore` refresh script and the update workflows' setup | [scripts/codebase/README.md](scripts/codebase/README.md) |`` row after the `scripts/` row of the directory table (line ~150), and a ``│   ├── codebase/    # update_gitignore.py (scheduled .gitignore refresh)`` line first under `scripts/` in the tree (line ~412), matching the column alignment of its neighbours.
- `.ctx/BUILD.md` (CI section, line ~205): change "Three workflows" to "Five workflows" and append two bullets after `leaks.yml`:
  - **`update-dependencies.yml`** (`Update dependencies`, Tuesdays 09:00 UTC or manual, `main` only): `prek update --cooldown-days 3`, then `run.py lock-upgrade`; opens or refreshes a PR from `maintenance/update-dependencies` covering `.pre-commit-config.yaml`, `uv.lock`, and `requirements.txt`.
  - **`update-gitignore.yml`** (`Update gitignore`, Mondays 09:00 UTC or manual, `main` only): runs `scripts/codebase/update_gitignore.py` and opens or refreshes a PR from `maintenance/update-gitignore`. Both use the `MAINTENANCE_PR_TOKEN` secret through `.github/actions/open-maintenance-pr` (setup in [`scripts/codebase/README.md`](../scripts/codebase/README.md#one-time-setup)).
- `.ctx/ARCHITECTURE.md` (line ~176): change the bullet to ``**`.github/workflows/{lint,deploy,leaks,update-dependencies,update-gitignore}.yml`**: CI: lint and tests, service deploys, leak scanning, scheduled dependency and `.gitignore` update PRs (see [`BUILD.md`](BUILD.md#ci))``.

- [ ] **Step 3: Format and check the docs**

Run: `uv run prek run mdformat --files scripts/codebase/README.md scripts/README.md README.md`
Expected: the hook may rewrite table alignment and add nothing else; rerun until it reports Passed. Then `git add` the rewrites.

Run: `uv run run.py docs-audit`
Expected: no new findings for `scripts/codebase`. If the audit flags `.github/actions/open-maintenance-pr` for lacking a README, compare how it treats `.github/workflows` and follow that outcome (add nothing if workflows are exempt).

- [ ] **Step 4: Full verification**

Run each and expect success:

```bash
uv run pytest -q -p no:sugar
uv run ruff check .
uv run mypy .
uv run interrogate
uvx yamllint .
uv run prek run --from-ref main --to-ref HEAD
uv run scripts/codebase/update_gitignore.py --dry-run
```

Expected: tests green (the existing suite plus the new files), no lint, type, docstring-coverage, YAML, or leak findings, and the dry run exits 0 leaving `git status` clean. `uv run prek run --from-ref main --to-ref HEAD` also exercises `check-leaks` over everything this branch adds.

- [ ] **Step 5: Commit**

```bash
git add scripts/codebase/README.md scripts/README.md README.md .ctx/BUILD.md .ctx/ARCHITECTURE.md
git commit -m "Document scheduled maintenance workflows and the PR token setup"
```

- [ ] **Step 6: Report the owner actions**

Do not push or open a PR without being asked. Report: the branch name, the commits, that `MAINTENANCE_PR_TOKEN` must be created before the first run, and that the first verification is a manual `gh workflow run "Update gitignore"` (then `"Update dependencies"`) after merge, checking that each PR appears and runs `lint.yml`. Remaining unproven until then: `run.py lock-upgrade` on a Linux runner.
