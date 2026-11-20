# GitHub Label Sync (`gh-labels`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a `gh-labels` command that applies a TOML-defined label set to any GitHub repository (and exports an
existing repository's labels to TOML), packaged as a stow package.

**Architecture:** One PEP 723 `uv run --script` file (`stow/ghtools/.local/bin/gh-labels`) holding small pure functions
(config parsing, diffing) and a thin `gh api` layer, plus a seed `labels.toml` beside it. Reconciliation is
create/update by default; deletion is opt-in (`--prune`). The `gh` layer is a single function (`run_gh`) so tests
replace it with a recording fake.

**Tech Stack:** Python >= 3.11 (stdlib only: `tomllib`, `argparse`, `subprocess`, `json`), `uv`, GitHub CLI (`gh`),
GNU Stow, pytest.

**Spec:** `docs/plans/2026-11/2026-11-19-gh-labels-sync-design.md`

## Target repository and session

All work happens in this repository, the personal base (**`~/dotfiles-personal`**), and not in an employer-specific
overlay repository. Reason: the tool is generic, so it belongs in the base (details in the spec). Cross-repo git is
refused from sessions in the other repository, so **start the executing session in `~/dotfiles-personal`**. Paths below
are relative to that repo unless absolute. Per the user's global rule for non-trivial work, begin in a worktree
(`EnterWorktree`, name `gh-labels-sync`), and never push to `main`; deliver via a pull request.

## Global Constraints

- Python is run only through `uv` (`uv run ...`); never bare `python`, `python3`, or `pip`. Never run `ruff format`.
- Script runtime floor: `requires-python = ">=3.11"` (for `tomllib`) in the PEP 723 block; no third-party dependencies.
- Style: line length 120; single quotes; `from __future__ import annotations` first; one import per line (isort
  `force-single-line`); `TYPE_CHECKING` block for type-only imports; boxed `# ====` section headers; sphinx-style
  docstrings whose summary lines end with a period; no blank line between a class docstring and its first member; no
  `__all__` in scripts; no bare `Any`; exception chaining (`raise ... from e` or `from None`).
- Console output follows `.claude/rules/script-style.md`: `style()` / `printf()` / `folduser()` names, semantic colors
  (paths `magenta`, errors `bright_red`, action headers `bright_cyan`, warnings `bright_yellow`, success
  `bright_green`), emoji status prefixes, argparse with `RawTextHelpFormatter` (`max_help_position=50`), a typed
  `Args(argparse.Namespace)`, option groups in local functions, and `-h/--help` re-added under "Other options".
- Tests: classes `TestX`; every method annotated `-> None`; multi-line docstrings with capitalised first word and no
  trailing period; tuple-form `@pytest.mark.parametrize`; no network and no live `gh` calls.
- GitHub limits: label name <= 50 characters, description <= 100 characters, color = six hex digits.
- The stow package must contain no `__pycache__` or other untracked files (`tests/unit/stow/test_stow_tree.py`).
- Package docs: a row in `stow/README.md`'s package table (enforced by `tests/unit/test_docs_consistency.py`); no
  per-package README (stow would link it into `$HOME`).
- Commit messages: short imperative sentence, no conventional-commit prefix (matches `git log` of the base).

## File Structure

| File                                          | Responsibility                                                              |
| --------------------------------------------- | --------------------------------------------------------------------------- |
| `stow/ghtools/.local/bin/gh-labels`           | The CLI: config model, `gh` layer, reconcile, argparse front end            |
| `stow/ghtools/.config/gh-labels/labels.toml`  | The user's label set (seeded from an existing repo, descriptions added)     |
| `tests/unit/ghtools/__init__.py`              | Package marker (empty)                                                      |
| `tests/unit/ghtools/test_gh_labels.py`        | All unit tests; loads the extension-less script via `SourceFileLoader`      |
| `stow/README.md`                              | New package-table row and a short "GitHub labels" usage section             |

---

### Task 1: Config model, validation, and TOML rendering

**Files:**

- Create: `stow/ghtools/.local/bin/gh-labels`
- Create: `tests/unit/ghtools/__init__.py` (empty)
- Create: `tests/unit/ghtools/test_gh_labels.py`

**Interfaces:**

- Consumes: nothing.
- Produces (all in `gh-labels`):
  - `class LabelsError(RuntimeError)`
  - `@dataclass(frozen=True) class Label: name: str; color: str; description: str = ''` (`color` is six lowercase hex
    digits, no `#`)
  - `normalize_color(raw: str) -> str` (raises `LabelsError`)
  - `parse_labels(data: Mapping[str, object]) -> list[Label]` (raises `LabelsError`)
  - `load_labels(path: Path) -> list[Label]` (raises `LabelsError`)
  - `render_toml(labels: Sequence[Label]) -> str`
  - `default_config_path() -> Path`

- [ ] **Step 1: Create the directories and the test package**

```bash
mkdir -p stow/ghtools/.local/bin stow/ghtools/.config/gh-labels tests/unit/ghtools
: > tests/unit/ghtools/__init__.py
```

- [ ] **Step 2: Write the failing tests**

Create `tests/unit/ghtools/test_gh_labels.py`:

```python
"""
Unit tests for stow/ghtools/.local/bin/gh-labels
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import sys
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType

REPO_ROOT   = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / 'stow' / 'ghtools' / '.local' / 'bin' / 'gh-labels'


def _load_module() -> ModuleType:
    """
    Import the extension-less ``gh-labels`` script as module ``gh_labels``.
    """
    loader = importlib.machinery.SourceFileLoader('gh_labels', str(SCRIPT_PATH))
    spec   = importlib.util.spec_from_loader('gh_labels', loader)
    assert spec is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules['gh_labels'] = module

    # The script lives in a stow package: keep exec_module from leaving a __pycache__ that stow would link into $HOME
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous

    return module


gh_labels = _load_module()
Label     = gh_labels.Label


@pytest.fixture(autouse=True)
def plain_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Disable ANSI styling so assertions can match plain text
    """
    monkeypatch.setattr(gh_labels, 'NO_COLOR', True, raising=False)


class TestNormalizeColor:
    """
    Tests for normalize_color
    """
    @pytest.mark.parametrize(
        ('raw', 'expected'),
        [
            ('d73a4a',  'd73a4a'),
            ('#D73A4A', 'd73a4a'),
            ('5AB1CD',  '5ab1cd'),
        ],
    )
    def test_valid_colors_are_normalised(self, raw: str, expected: str) -> None:
        """
        Test that a color loses its hash prefix and is lowercased
        """
        assert gh_labels.normalize_color(raw) == expected

    @pytest.mark.parametrize('raw', ['', 'xyz123', '12345', '#1234567', 'ggg000'])
    def test_invalid_colors_are_rejected(self, raw: str) -> None:
        """
        Test that anything other than six hex digits raises
        """
        with pytest.raises(gh_labels.LabelsError, match='invalid color'):
            gh_labels.normalize_color(raw)


class TestParseLabels:
    """
    Tests for parse_labels
    """
    def test_valid_config_is_parsed(self) -> None:
        """
        Test that names, colors, and optional descriptions become Label objects
        """
        data = {
            'label': [
                {'name': 'bug',     'color': '#D73A4A', 'description': "Something isn't working"},
                {'name': 'feature', 'color': '5ab1cd'},
            ],
        }

        assert gh_labels.parse_labels(data) == [
            Label('bug',     'd73a4a', "Something isn't working"),
            Label('feature', '5ab1cd', ''),
        ]

    def test_name_is_stripped(self) -> None:
        """
        Test that surrounding whitespace in a name is removed
        """
        assert gh_labels.parse_labels({'label': [{'name': '  bug ', 'color': 'ffffff'}]})[0].name == 'bug'

    @pytest.mark.parametrize(
        ('data', 'message'),
        [
            ({},                                                              'at least one'),
            ({'label': []},                                                   'at least one'),
            ({'label': ['bug']},                                              'expected a table'),
            ({'label': [{'name': 'a', 'color': 'ffffff', 'colour': 'x'}]},    'unknown key'),
            ({'label': [{'color': 'ffffff'}]},                                'name must be'),
            ({'label': [{'name': '  ', 'color': 'ffffff'}]},                  'name must be'),
            ({'label': [{'name': 'x' * 51, 'color': 'ffffff'}]},              'exceeds 50'),
            ({'label': [{'name': 'a'}]},                                      'color must be'),
            ({'label': [{'name': 'a', 'color': 'nothex'}]},                   'invalid color'),
            ({'label': [{'name': 'a', 'color': 'ffffff', 'description': 7}]}, 'description must be'),
            ({'label': [{'name': 'a', 'color': 'ffffff', 'description': 'x' * 101}]}, 'exceeds 100'),
            (
                {'label': [{'name': 'Bug', 'color': 'ffffff'}, {'name': 'bug', 'color': '000000'}]},
                'duplicate',
            ),
        ],
    )
    def test_invalid_configs_are_rejected(self, data: dict[str, object], message: str) -> None:
        """
        Test that each validation rule raises a LabelsError with a helpful message
        """
        with pytest.raises(gh_labels.LabelsError, match=message):
            gh_labels.parse_labels(data)

    def test_description_at_limit_is_accepted(self) -> None:
        """
        Test that a 100 character description and a 50 character name are within limits
        """
        label = gh_labels.parse_labels({'label': [{'name': 'n' * 50, 'color': 'ffffff', 'description': 'd' * 100}]})[0]

        assert (len(label.name), len(label.description)) == (50, 100)


class TestLoadLabels:
    """
    Tests for load_labels
    """
    def test_loads_a_toml_file(self, tmp_path: Path) -> None:
        """
        Test that a TOML file on disk is parsed into labels
        """
        path = tmp_path / 'labels.toml'
        path.write_text('[[label]]\nname = "bug"\ncolor = "d73a4a"\n', encoding='utf-8')

        assert gh_labels.load_labels(path) == [Label('bug', 'd73a4a', '')]

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        """
        Test that a missing config file raises a LabelsError naming the path
        """
        with pytest.raises(gh_labels.LabelsError, match='config not found'):
            gh_labels.load_labels(tmp_path / 'absent.toml')

    def test_malformed_toml_raises(self, tmp_path: Path) -> None:
        """
        Test that TOML syntax errors surface as a LabelsError
        """
        path = tmp_path / 'labels.toml'
        path.write_text('[[label]\nname = ', encoding='utf-8')

        with pytest.raises(gh_labels.LabelsError, match=r'labels\.toml'):
            gh_labels.load_labels(path)


class TestRenderToml:
    """
    Tests for render_toml
    """
    def test_round_trips_through_the_parser(self) -> None:
        """
        Test that rendered TOML parses back to the same labels, including quotes and non-ASCII text
        """
        labels = [
            Label('bug',        'd73a4a', ''),
            Label('say "hi"',   'ffffff', 'tab\tand ünïcode ✅'),
            Label('back\\slash', '000000', 'x'),
        ]

        assert gh_labels.parse_labels(tomllib.loads(gh_labels.render_toml(labels))) == labels

    def test_empty_description_is_omitted(self) -> None:
        """
        Test that labels without a description render no description key
        """
        assert 'description' not in gh_labels.render_toml([Label('bug', 'd73a4a')])


class TestDefaultConfigPath:
    """
    Tests for default_config_path
    """
    def test_honours_xdg_config_home(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """
        Test that XDG_CONFIG_HOME relocates the default config
        """
        monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path))

        assert gh_labels.default_config_path() == tmp_path / 'gh-labels' / 'labels.toml'

    def test_falls_back_to_dot_config(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """
        Test that without XDG_CONFIG_HOME the default is under ~/.config
        """
        monkeypatch.delenv('XDG_CONFIG_HOME', raising=False)
        monkeypatch.setattr(Path, 'home', lambda: tmp_path)

        assert gh_labels.default_config_path() == tmp_path / '.config' / 'gh-labels' / 'labels.toml'
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/ghtools -v`
Expected: collection ERROR with `FileNotFoundError` for `stow/ghtools/.local/bin/gh-labels`.

- [ ] **Step 4: Write the script (config layer)**

Create `stow/ghtools/.local/bin/gh-labels`:

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Apply a TOML-defined GitHub label set to a repository, or export a repository's labels to TOML.

Examples
--------
    gh-labels apply --dry-run                         # preview changes for the repo in the current directory
    gh-labels apply --repo OWNER/REPO                 # sync a specific repo
    gh-labels pull --repo OWNER/REPO                  # print that repo's labels as TOML

Requires the GitHub CLI (``gh``), authenticated for the repository's host.
"""
from __future__ import annotations

import json
import os
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping
    from collections.abc import Sequence

# ==================================================================================================
# Constants and errors
# ==================================================================================================

NAME_MAX_LENGTH        = 50
DESCRIPTION_MAX_LENGTH = 100
CONFIG_KEYS            = frozenset({'name', 'color', 'description'})
HEX_COLOR              = re.compile(r'[0-9a-f]{6}')


class LabelsError(RuntimeError):
    """
    Raised for any user-facing failure: a bad config, bad arguments, or a failed ``gh`` call.
    """

# ==================================================================================================
# Label model and config parsing
# ==================================================================================================


@dataclass(frozen=True)
class Label:
    """
    A GitHub label. ``color`` is six lowercase hex digits without a leading ``#``.
    """
    name:        str
    color:       str
    description: str = ''


def normalize_color(raw: str) -> str:
    """
    Normalise a label color to six lowercase hex digits.

    :param raw: color as written in the config, with or without a leading ``#``
    :raises LabelsError: if the value is not six hex digits
    :return: the color without ``#``, lowercased
    """
    color = raw.removeprefix('#').lower()
    if not HEX_COLOR.fullmatch(color):
        raise LabelsError(f'invalid color {raw!r}: expected six hex digits')
    return color


def parse_labels(data: Mapping[str, object]) -> list[Label]:
    """
    Validate decoded TOML and convert its ``[[label]]`` tables to labels.

    :param data: the decoded TOML document
    :raises LabelsError: if the document violates the schema or GitHub's limits
    :return: labels in file order
    """
    entries = data.get('label')
    if not isinstance(entries, list) or not entries:
        raise LabelsError('config must define at least one [[label]] table')

    labels: list[Label] = []
    seen:   set[str]    = set()
    for position, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise LabelsError(f'label #{position}: expected a table')
        unknown = set(entry) - CONFIG_KEYS
        if unknown:
            raise LabelsError(f'label #{position}: unknown key(s) {sorted(unknown)}')

        name = entry.get('name')
        if not isinstance(name, str) or not name.strip():
            raise LabelsError(f'label #{position}: name must be a non-empty string')
        name = name.strip()
        if len(name) > NAME_MAX_LENGTH:
            raise LabelsError(f'label {name!r}: name exceeds {NAME_MAX_LENGTH} characters')
        if name.casefold() in seen:
            raise LabelsError(f'label {name!r}: duplicate name (names are case-insensitive)')
        seen.add(name.casefold())

        color = entry.get('color')
        if not isinstance(color, str):
            raise LabelsError(f'label {name!r}: color must be a string')
        try:
            color = normalize_color(color)
        except LabelsError as e:
            raise LabelsError(f'label {name!r}: {e}') from e

        description = entry.get('description', '')
        if not isinstance(description, str):
            raise LabelsError(f'label {name!r}: description must be a string')
        if len(description) > DESCRIPTION_MAX_LENGTH:
            raise LabelsError(f'label {name!r}: description exceeds {DESCRIPTION_MAX_LENGTH} characters')

        labels.append(Label(name, color, description))

    return labels


def load_labels(path: Path) -> list[Label]:
    """
    Read and validate a label definition file.

    :param path: TOML file containing ``[[label]]`` tables
    :raises LabelsError: if the file is missing, malformed, or invalid
    :return: labels in file order
    """
    try:
        with path.open('rb') as handle:
            data = tomllib.load(handle)
    except FileNotFoundError:
        raise LabelsError(f'config not found: {path}') from None
    except tomllib.TOMLDecodeError as e:
        raise LabelsError(f'{path}: {e}') from e
    return parse_labels(data)


def _toml_string(value: str) -> str:
    """
    Quote a string as a TOML basic string (JSON string syntax is a subset of it).
    """
    return json.dumps(value, ensure_ascii=False)


def render_toml(labels: Sequence[Label]) -> str:
    """
    Render labels as a ``labels.toml`` document.

    :param labels: labels to render, in output order
    :return: TOML text ending in a newline
    """
    lines = ['# GitHub label definitions applied by `gh-labels apply`.', '']
    for label in labels:
        lines.append('[[label]]')
        lines.append(f'name        = {_toml_string(label.name)}')
        lines.append(f'color       = {_toml_string(label.color)}')
        if label.description:
            lines.append(f'description = {_toml_string(label.description)}')
        lines.append('')
    return '\n'.join(lines)


def default_config_path() -> Path:
    """
    Locate the default label definition file.

    :return: ``$XDG_CONFIG_HOME/gh-labels/labels.toml``, or ``~/.config/gh-labels/labels.toml`` when unset
    """
    base = os.environ.get('XDG_CONFIG_HOME')
    root = Path(base) if base else Path.home() / '.config'
    return root / 'gh-labels' / 'labels.toml'
```

- [ ] **Step 5: Make the script executable and run the tests**

```bash
chmod +x stow/ghtools/.local/bin/gh-labels
uv run pytest tests/unit/ghtools -v
```

Expected: all tests PASS.

- [ ] **Step 6: Lint**

```bash
uv run ruff check --fix stow/ghtools/.local/bin/gh-labels tests/unit/ghtools
uv run ruff check stow/ghtools/.local/bin/gh-labels tests/unit/ghtools
```

Expected: `All checks passed!`. (Ruff lints explicitly passed files regardless of extension; repo-wide runs skip the
extension-less script, so always pass it by path.) If `--fix` reordered imports, re-run the tests.

- [ ] **Step 7: Commit**

```bash
git add stow/ghtools/.local/bin/gh-labels tests/unit/ghtools
git commit -m "Add gh-labels config model with validation and TOML rendering"
```

---

### Task 2: `gh` layer and reconciliation

**Files:**

- Modify: `stow/ghtools/.local/bin/gh-labels` (add imports; append sections after `default_config_path`)
- Modify: `tests/unit/ghtools/test_gh_labels.py` (add imports; append classes)

**Interfaces:**

- Consumes: `Label`, `LabelsError`, `normalize_color` is not needed; `Label` equality is dataclass equality.
- Produces (all in `gh-labels`):
  - `NO_COLOR: bool`, `style(text: object = '', *, fg: str | None = None, bold: bool | None = None, dim: bool | None = None) -> str`
  - `printf(text: object = '', *, indent: int = 0, file: TextIO | None = None) -> None`
  - `@dataclass(frozen=True) class RepoRef: host: str | None; owner: str; name: str` with property
    `labels_endpoint -> str` and `__str__`
  - `parse_repo(spec: str) -> RepoRef`
  - `run_gh(*args: str) -> str`
  - `gh_api(repo: RepoRef, endpoint: str, *, method: str = 'GET', fields: Mapping[str, str] | None = None, paginate: bool = False) -> str`
  - `current_repo() -> RepoRef`, `resolve_repo(spec: str | None) -> RepoRef`
  - `labels_from_api(rows: Sequence[Mapping[str, object]]) -> list[Label]`
  - `fetch_labels(repo: RepoRef) -> list[Label]`
  - `@dataclass(frozen=True) class Plan: create: list[Label]; update: list[tuple[Label, Label]]; unchanged: list[Label]; extra: list[Label]`
    (`update` holds `(existing, desired)` pairs)
  - `build_plan(desired: Sequence[Label], existing: Sequence[Label]) -> Plan`
  - `label_fields(label: Label) -> dict[str, str]`
  - `apply_plan(repo: RepoRef, plan: Plan, *, prune: bool, dry_run: bool) -> None`
  - `summarize(plan: Plan, *, prune: bool, dry_run: bool) -> None`

- [ ] **Step 1: Write the failing tests**

Add these imports to the test file's import block (one per line, isort order): `import json` among the plain imports and
`from itertools import pairwise` among the `from` imports (before `from pathlib import Path`). Then append:

```python
class FakeGh:
    """
    Stand-in for ``run_gh`` that records calls and serves a canned label list in two pages
    """
    def __init__(self, existing: list[dict[str, object]] | None = None) -> None:
        self.existing = existing or []
        self.repo_url = 'https://ghe.example.com/me/proj'
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, *args: str) -> str:
        self.calls.append(args)
        if args[:2] == ('repo', 'view'):
            return json.dumps({'url': self.repo_url})
        if '--paginate' in args:
            return json.dumps([self.existing[:2], self.existing[2:]])
        return ''

    @property
    def mutations(self) -> list[tuple[str, str, dict[str, str]]]:
        """
        Every non-GET ``gh api`` call as ``(method, endpoint, fields)``.
        """
        found = []
        for args in self.calls:
            if args[0] != 'api':
                continue
            method = args[args.index('--method') + 1]
            if method == 'GET':
                continue
            fields = {
                pair.partition('=')[0]: pair.partition('=')[2]
                for flag, pair in pairwise(args)
                if flag == '--raw-field'
            }
            found.append((method, args[1], fields))
        return found


EXISTING = [
    {'name': 'bug',     'color': 'D73A4A', 'description': None},
    {'name': 'Docs',    'color': '0075ca', 'description': None},
    {'name': 'wontfix', 'color': 'ffffff', 'description': 'This will not be worked on'},
]
DESIRED = [
    Label('bug',     'd73a4a'),
    Label('docs',    '0075ca', 'Documentation'),
    Label('feature', '5ab1cd', 'New capability'),
]
REPO = gh_labels.RepoRef(None, 'me', 'proj')


@pytest.fixture
def fake_gh(monkeypatch: pytest.MonkeyPatch) -> FakeGh:
    """
    Replace ``run_gh`` with a recording fake holding the sample repository's labels
    """
    fake = FakeGh(EXISTING)
    monkeypatch.setattr(gh_labels, 'run_gh', fake)
    return fake


class TestRepoRef:
    """
    Tests for parse_repo and RepoRef
    """
    @pytest.mark.parametrize(
        ('spec', 'host', 'owner', 'name'),
        [
            ('me/proj',                         None,                'me',        'proj'),
            ('ghe.example.com/me/proj',         'ghe.example.com',   'me',        'proj'),
            ('me/my.repo-name_2',               None,                'me',        'my.repo-name_2'),
        ],
    )
    def test_valid_specs(self, spec: str, host: str | None, owner: str, name: str) -> None:
        """
        Test that OWNER/REPO and HOST/OWNER/REPO are both understood
        """
        assert gh_labels.parse_repo(spec) == gh_labels.RepoRef(host, owner, name)

    @pytest.mark.parametrize('spec', ['proj', 'a/b/c/d', '', 'me/', '/proj', 'me/pro j'])
    def test_invalid_specs(self, spec: str) -> None:
        """
        Test that malformed repository specs raise
        """
        with pytest.raises(gh_labels.LabelsError, match='invalid repo'):
            gh_labels.parse_repo(spec)

    def test_endpoint_and_str(self) -> None:
        """
        Test the labels endpoint and the display form, with and without a host
        """
        assert REPO.labels_endpoint == 'repos/me/proj/labels'
        assert str(REPO) == 'me/proj'
        assert str(gh_labels.RepoRef('h.example.com', 'me', 'proj')) == 'h.example.com/me/proj'


class TestRunGh:
    """
    Tests for run_gh
    """
    def test_returns_stdout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that stdout of a successful gh call is returned and the argv is passed as a list
        """
        seen: list[list[str]] = []

        def fake_run(cmd: list[str], **kwargs: object) -> object:
            seen.append(cmd)
            return type('Result', (), {'stdout': 'ok\n'})()

        monkeypatch.setattr(gh_labels.subprocess, 'run', fake_run)

        assert gh_labels.run_gh('api', 'x') == 'ok\n'
        assert seen == [['gh', 'api', 'x']]

    def test_missing_gh_is_reported(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that a missing gh binary raises a LabelsError that says so
        """
        def fake_run(*args: object, **kwargs: object) -> object:
            raise FileNotFoundError

        monkeypatch.setattr(gh_labels.subprocess, 'run', fake_run)

        with pytest.raises(gh_labels.LabelsError, match='not installed'):
            gh_labels.run_gh('api', 'x')

    def test_failure_includes_stderr(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that a failing gh call surfaces its stderr text
        """
        def fake_run(cmd: list[str], **kwargs: object) -> object:
            raise gh_labels.subprocess.CalledProcessError(1, cmd, stderr='HTTP 404: Not Found\n')

        monkeypatch.setattr(gh_labels.subprocess, 'run', fake_run)

        with pytest.raises(gh_labels.LabelsError, match='HTTP 404'):
            gh_labels.run_gh('api', 'x')


class TestGhApi:
    """
    Tests for gh_api, current_repo, resolve_repo, and fetch_labels
    """
    def test_argument_shape(self, fake_gh: FakeGh) -> None:
        """
        Test the argv built for a mutating call with a host and raw fields
        """
        repo = gh_labels.RepoRef('ghe.example.com', 'me', 'proj')
        gh_labels.gh_api(repo, 'repos/me/proj/labels', method='POST', fields={'name': 'a=b', 'color': 'ffffff'})

        assert fake_gh.calls == [(
            'api', 'repos/me/proj/labels', '--method', 'POST', '--hostname', 'ghe.example.com',
            '--raw-field', 'name=a=b', '--raw-field', 'color=ffffff',
        )]

    def test_paginate_uses_slurp(self, fake_gh: FakeGh) -> None:
        """
        Test that paginated reads ask gh to slurp pages into one JSON array
        """
        gh_labels.gh_api(REPO, 'repos/me/proj/labels', paginate=True)

        assert fake_gh.calls[0][-2:] == ('--paginate', '--slurp')

    def test_current_repo_reads_host_from_url(self, fake_gh: FakeGh) -> None:
        """
        Test that the repository of the working directory is found through gh repo view
        """
        assert gh_labels.current_repo() == gh_labels.RepoRef('ghe.example.com', 'me', 'proj')

    def test_current_repo_failure_suggests_repo_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that failing to detect a repository hints at --repo
        """
        def failing(*args: str) -> str:
            raise gh_labels.LabelsError('gh repo failed: not a git repository')

        monkeypatch.setattr(gh_labels, 'run_gh', failing)

        with pytest.raises(gh_labels.LabelsError, match='--repo'):
            gh_labels.current_repo()

    def test_resolve_repo_prefers_the_explicit_spec(self, fake_gh: FakeGh) -> None:
        """
        Test that an explicit spec is parsed without calling gh
        """
        assert gh_labels.resolve_repo('me/proj') == REPO
        assert fake_gh.calls == []

    def test_fetch_labels_flattens_pages_and_normalises(self, fake_gh: FakeGh) -> None:
        """
        Test that pages are flattened, colors lowercased, and null descriptions become empty strings
        """
        assert gh_labels.fetch_labels(REPO) == [
            Label('bug',     'd73a4a', ''),
            Label('Docs',    '0075ca', ''),
            Label('wontfix', 'ffffff', 'This will not be worked on'),
        ]


class TestBuildPlan:
    """
    Tests for build_plan
    """
    def test_classifies_every_label(self) -> None:
        """
        Test create, update (case-insensitive match), unchanged, and extra classification
        """
        existing = gh_labels.labels_from_api(EXISTING)
        plan     = gh_labels.build_plan(DESIRED, existing)

        assert plan.create    == [Label('feature', '5ab1cd', 'New capability')]
        assert plan.update    == [(Label('Docs', '0075ca', ''), Label('docs', '0075ca', 'Documentation'))]
        assert plan.unchanged == [Label('bug', 'd73a4a', '')]
        assert plan.extra     == [Label('wontfix', 'ffffff', 'This will not be worked on')]

    def test_identical_sets_need_no_changes(self) -> None:
        """
        Test that matching sets yield an empty create, update, and extra list
        """
        plan = gh_labels.build_plan(DESIRED, DESIRED)

        assert (plan.create, plan.update, plan.extra) == ([], [], [])
        assert plan.unchanged == DESIRED


class TestApplyPlan:
    """
    Tests for apply_plan and summarize
    """
    def _plan(self) -> object:
        return gh_labels.build_plan(DESIRED, gh_labels.labels_from_api(EXISTING))

    def test_creates_and_updates(self, fake_gh: FakeGh) -> None:
        """
        Test the POST and PATCH calls, including a URL-quoted label name
        """
        existing = [Label('work in progress', 'c5def5', '')]
        desired  = [Label('work in progress', '000000', 'WIP'), Label('new', 'ffffff', '')]

        gh_labels.apply_plan(REPO, gh_labels.build_plan(desired, existing), prune=False, dry_run=False)

        assert fake_gh.mutations == [
            ('POST',  'repos/me/proj/labels', {'name': 'new', 'color': 'ffffff', 'description': ''}),
            (
                'PATCH',
                'repos/me/proj/labels/work%20in%20progress',
                {'new_name': 'work in progress', 'color': '000000', 'description': 'WIP'},
            ),
        ]

    def test_extras_are_kept_without_prune(self, fake_gh: FakeGh, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that labels missing from the config are reported but not deleted by default
        """
        gh_labels.apply_plan(REPO, self._plan(), prune=False, dry_run=False)

        assert all(method != 'DELETE' for method, _, _ in fake_gh.mutations)
        assert 'wontfix' in capsys.readouterr().out

    def test_prune_deletes_extras(self, fake_gh: FakeGh) -> None:
        """
        Test that --prune deletes labels missing from the config
        """
        gh_labels.apply_plan(REPO, self._plan(), prune=True, dry_run=False)

        assert ('DELETE', 'repos/me/proj/labels/wontfix', {}) in fake_gh.mutations

    def test_dry_run_makes_no_mutations(self, fake_gh: FakeGh, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that a dry run reports every action yet issues no mutating call, even with prune
        """
        gh_labels.apply_plan(REPO, self._plan(), prune=True, dry_run=True)
        out = capsys.readouterr().out

        assert fake_gh.mutations == []
        assert all(word in out for word in ('create', 'update', 'delete'))

    def test_summary_counts(self, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that the summary line reports counts and flags kept extras
        """
        gh_labels.summarize(self._plan(), prune=False, dry_run=False)
        out = capsys.readouterr().out

        assert '1 created, 1 updated, 1 unchanged' in out
        assert '--prune' in out
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/ghtools -v`
Expected: collection ERROR with `AttributeError: module 'gh_labels' has no attribute 'RepoRef'`, so no tests run: the
module-level `REPO = gh_labels.RepoRef(...)` fails at import until Step 4 exists. (`raising=False` on the autouse
`NO_COLOR` fixture from Task 1 stays: Task 1's script has no `NO_COLOR` attribute yet.)

- [ ] **Step 3: Add imports to the script**

In `stow/ghtools/.local/bin/gh-labels`, make the stdlib import block read (one per line, alphabetical; `import`
statements first, then `from` statements) and extend the `TYPE_CHECKING` block:

```python
import json
import os
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import quote
from urllib.parse import urlparse

if TYPE_CHECKING:
    from collections.abc import Mapping
    from collections.abc import Sequence
    from typing import TextIO
```

- [ ] **Step 4: Append the styling, `gh` layer, and reconcile sections**

Append to the end of `gh-labels`:

```python

# ==================================================================================================
# Text styling
#
# Reduced copy of run.py's style()/printf(): same names and semantics, limited to the options used here.
# ==================================================================================================

NO_COLOR = bool(os.environ.get('NO_COLOR'))

ANSI_COLOR: dict[str, int] = {
    'bright_red':    91,
    'bright_green':  92,
    'bright_yellow': 93,
    'bright_cyan':   96,
    'bright_white':  97,
    'magenta':       35,
}
ANSI_RESET_ALL = '\033[0m'


def style(text: object = '', *, fg: str | None = None, bold: bool | None = None, dim: bool | None = None) -> str:
    """
    Style text with ANSI escape codes. Returns the text unstyled when ``NO_COLOR`` is set.

    :param text: the value to style
    :param fg: foreground color name from ``ANSI_COLOR``
    :param bold: enable or disable bold mode
    :param dim: enable or disable dim mode
    :return: styled text, ending with a reset code
    """
    if NO_COLOR:
        return str(text)

    bits: list[str] = []
    if fg is not None:
        bits.append(f'\033[{ANSI_COLOR[fg]}m')
    if bold is not None:
        bits.append(f'\033[{1 if bold else 22}m')
    if dim is not None:
        bits.append(f'\033[{2 if dim else 22}m')
    bits.append(str(text))
    bits.append(ANSI_RESET_ALL)
    return ''.join(bits)


def printf(text: object = '', *, indent: int = 0, file: TextIO | None = None) -> None:
    """
    Print text, optionally indented, to stdout or the given stream.

    :param text: the value to print
    :param indent: number of leading spaces
    :param file: destination stream; defaults to the current ``sys.stdout``
    """
    print(f'{" " * indent}{text}', file=file or sys.stdout)


# ==================================================================================================
# GitHub access (via the gh CLI)
# ==================================================================================================

REPO_SPEC = re.compile(r'(?:(?P<host>[^/\s]+)/)?(?P<owner>[\w.-]+)/(?P<name>[\w.-]+)')


@dataclass(frozen=True)
class RepoRef:
    """
    A GitHub repository. ``host`` is set only when stated explicitly or detected from a remote URL.
    """
    host:  str | None
    owner: str
    name:  str

    @property
    def labels_endpoint(self) -> str:
        """
        REST endpoint of the repository's label collection.

        :return: ``repos/OWNER/REPO/labels``
        """
        return f'repos/{self.owner}/{self.name}/labels'

    def __str__(self) -> str:
        return '/'.join(part for part in (self.host, self.owner, self.name) if part)


def parse_repo(spec: str) -> RepoRef:
    """
    Parse ``[HOST/]OWNER/REPO``.

    :param spec: repository spec as given on the command line
    :raises LabelsError: if the spec is malformed
    :return: the parsed reference
    """
    match = REPO_SPEC.fullmatch(spec)
    if match is None:
        raise LabelsError(f'invalid repo {spec!r}: expected [HOST/]OWNER/REPO')
    return RepoRef(match['host'], match['owner'], match['name'])


def run_gh(*args: str) -> str:
    """
    Run ``gh`` with the given arguments (no shell) and return its stdout.

    :param args: arguments after ``gh``
    :raises LabelsError: if ``gh`` is missing or exits non-zero
    :return: captured standard output
    """
    try:
        result = subprocess.run(['gh', *args], capture_output=True, text=True, check=True)
    except FileNotFoundError:
        raise LabelsError('the GitHub CLI (gh) is not installed or not on PATH') from None
    except subprocess.CalledProcessError as e:
        detail = (e.stderr or '').strip() or f'exit status {e.returncode}'
        raise LabelsError(f'gh {args[0]} failed: {detail}') from e
    return result.stdout


def gh_api(
    repo: RepoRef,
    endpoint: str,
    *,
    method: str = 'GET',
    fields: Mapping[str, str] | None = None,
    paginate: bool = False,
) -> str:
    """
    Call the GitHub REST API through ``gh api``.

    :param repo: repository whose host (if any) selects the API host
    :param endpoint: REST path, e.g. ``repos/OWNER/REPO/labels``
    :param method: HTTP method
    :param fields: string fields sent as raw request parameters
    :param paginate: follow pagination and slurp every page into one JSON array
    :return: response body
    """
    args = ['api', endpoint, '--method', method]
    if repo.host:
        args += ['--hostname', repo.host]
    if paginate:
        args += ['--paginate', '--slurp']
    for key, value in (fields or {}).items():
        args += ['--raw-field', f'{key}={value}']
    return run_gh(*args)


def current_repo() -> RepoRef:
    """
    Detect the repository of the current working directory via ``gh repo view``.

    :raises LabelsError: if the directory is not a GitHub repository
    :return: the repository, with the host taken from its URL
    """
    try:
        url = json.loads(run_gh('repo', 'view', '--json', 'url'))['url']
    except LabelsError as e:
        raise LabelsError(f'{e}; pass --repo to choose a repository') from e
    parsed = urlparse(url)
    owner, name = parsed.path.strip('/').split('/')[:2]
    return RepoRef(parsed.hostname, owner, name)


def resolve_repo(spec: str | None) -> RepoRef:
    """
    Resolve the target repository.

    :param spec: ``--repo`` value, or ``None`` to use the current directory's repository
    :return: the repository to operate on
    """
    return parse_repo(spec) if spec else current_repo()


def labels_from_api(rows: Sequence[Mapping[str, object]]) -> list[Label]:
    """
    Convert REST label objects to labels (lowercase color, ``None`` description as an empty string).

    :param rows: label objects as returned by the API
    :return: labels in API order
    """
    return [
        Label(str(row['name']), str(row['color']).lower(), str(row.get('description') or ''))
        for row in rows
    ]


def fetch_labels(repo: RepoRef) -> list[Label]:
    """
    Fetch every label of a repository.

    :param repo: repository to read
    :return: the repository's labels
    """
    pages = json.loads(gh_api(repo, f'{repo.labels_endpoint}?per_page=100', paginate=True))
    return labels_from_api([row for page in pages for row in page])


# ==================================================================================================
# Reconciliation
# ==================================================================================================


@dataclass(frozen=True)
class Plan:
    """
    The difference between the desired and existing label sets. ``update`` holds ``(existing, desired)`` pairs.
    """
    create:    list[Label]
    update:    list[tuple[Label, Label]]
    unchanged: list[Label]
    extra:     list[Label]


def build_plan(desired: Sequence[Label], existing: Sequence[Label]) -> Plan:
    """
    Diff the desired labels against a repository's labels, matching names case-insensitively.

    :param desired: labels from the config
    :param existing: labels currently on the repository
    :return: what to create, update, leave alone, and what exists beyond the config
    """
    current = {label.name.casefold(): label for label in existing}
    wanted  = {label.name.casefold() for label in desired}

    create:    list[Label]                = []
    update:    list[tuple[Label, Label]]  = []
    unchanged: list[Label]                = []
    for label in desired:
        found = current.get(label.name.casefold())
        if found is None:
            create.append(label)
        elif found == label:
            unchanged.append(label)
        else:
            update.append((found, label))

    extra = [label for label in existing if label.name.casefold() not in wanted]
    return Plan(create, update, unchanged, extra)


def label_fields(label: Label) -> dict[str, str]:
    """
    Build the request fields for creating a label.

    :param label: the label to send
    :return: ``name``, ``color``, and ``description`` as strings
    """
    return {'name': label.name, 'color': label.color, 'description': label.description}


def _describe(label: Label) -> str:
    """
    Format a label as a styled ``name #color`` fragment.
    """
    return f'{style(label.name, fg="bright_white", bold=True)} {style("#" + label.color, dim=True)}'


def apply_plan(repo: RepoRef, plan: Plan, *, prune: bool, dry_run: bool) -> None:
    """
    Report each action in a plan and, unless this is a dry run, perform it.

    :param repo: repository to modify
    :param plan: the computed difference
    :param prune: delete labels that are not in the config
    :param dry_run: print actions without calling the API
    """
    for label in plan.create:
        printf(f'💾 {style("create", fg="bright_cyan")}  {_describe(label)}')
        if not dry_run:
            gh_api(repo, repo.labels_endpoint, method='POST', fields=label_fields(label))

    for current, label in plan.update:
        printf(f'🔄 {style("update", fg="bright_cyan")}  {_describe(current)} -> {_describe(label)}')
        if not dry_run:
            fields = {'new_name': label.name, 'color': label.color, 'description': label.description}
            gh_api(repo, f'{repo.labels_endpoint}/{quote(current.name, safe="")}', method='PATCH', fields=fields)

    for label in plan.extra:
        if prune:
            printf(f'🧹 {style("delete", fg="bright_cyan")}  {_describe(label)}')
            if not dry_run:
                gh_api(repo, f'{repo.labels_endpoint}/{quote(label.name, safe="")}', method='DELETE')
        else:
            printf(f'🟡 {style("extra", fg="bright_yellow")}   {_describe(label)}')


def summarize(plan: Plan, *, prune: bool, dry_run: bool) -> None:
    """
    Print the closing summary of an apply run.

    :param plan: the computed difference
    :param prune: whether extras were (or would be) deleted
    :param dry_run: whether nothing was changed
    """
    counts = f'{len(plan.create)} created, {len(plan.update)} updated, {len(plan.unchanged)} unchanged'
    if dry_run:
        printf(f'🟡 {style("Dry run, nothing changed", fg="bright_yellow")}: {counts}')
    else:
        printf(f'✅ {style("Done", fg="bright_green")}: {counts}')
    if plan.extra:
        verb = 'deleted' if prune and not dry_run else 'would be deleted' if prune else 'kept (use --prune to delete)'
        printf(f'{len(plan.extra)} label(s) not in the config {verb}', indent=3)
```

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/unit/ghtools -v`
Expected: all tests PASS. If `test_summary_counts` fails on wording, fix the script, not the test: the summary must
contain `1 created, 1 updated, 1 unchanged` and `--prune`.

- [ ] **Step 6: Lint**

```bash
uv run ruff check --fix stow/ghtools/.local/bin/gh-labels tests/unit/ghtools
uv run ruff check stow/ghtools/.local/bin/gh-labels tests/unit/ghtools
uv run pytest tests/unit/ghtools -q
```

Expected: `All checks passed!` and all tests pass. The `_plan` helper in `TestApplyPlan` returns `object` only to keep
the annotation free of the dynamically loaded `Plan` type; if ruff or mypy objects, annotate it `-> gh_labels.Plan`.

- [ ] **Step 7: Commit**

```bash
git add stow/ghtools/.local/bin/gh-labels tests/unit/ghtools/test_gh_labels.py
git commit -m "Add gh-labels GitHub access layer and label reconciliation"
```

---

### Task 3: Command-line interface

**Files:**

- Modify: `stow/ghtools/.local/bin/gh-labels` (add imports; append CLI section)
- Modify: `tests/unit/ghtools/test_gh_labels.py` (add imports; append classes)

**Interfaces:**

- Consumes: everything from Tasks 1 and 2 (`load_labels`, `default_config_path`, `resolve_repo`, `fetch_labels`,
  `build_plan`, `apply_plan`, `summarize`, `render_toml`, `style`, `printf`, `LabelsError`).
- Produces:
  - `folduser(path: str | Path) -> str`
  - `class Args(argparse.Namespace)` with `command: str`, `repo: str | None`, `config: Path`, `dry_run: bool`,
    `prune: bool`, `output: Path | None`
  - `build_parser() -> argparse.ArgumentParser`
  - `cmd_apply(args: Args) -> int`, `cmd_pull(args: Args) -> int`
  - `main(argv: Sequence[str] | None = None) -> int` (exit codes: `0` success, `1` any `LabelsError`)

- [ ] **Step 1: Write the failing tests**

Add `import os` to the test file's imports (keep the block sorted), then append:

```python
@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    """
    Write the sample desired label set to a TOML file
    """
    path = tmp_path / 'labels.toml'
    path.write_text(gh_labels.render_toml(DESIRED), encoding='utf-8')
    return path


class TestFolduser:
    """
    Tests for folduser
    """
    def test_folds_home_prefix(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """
        Test that a path under the home directory is shown with a tilde
        """
        monkeypatch.setattr(Path, 'home', lambda: tmp_path)

        assert gh_labels.folduser(tmp_path / '.config' / 'x') == '~/.config/x'

    def test_leaves_other_paths_alone(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """
        Test that a path outside the home directory is returned unchanged
        """
        monkeypatch.setattr(Path, 'home', lambda: tmp_path / 'home')

        assert gh_labels.folduser('/etc/hosts') == '/etc/hosts'


class TestMainApply:
    """
    Tests for the apply subcommand
    """
    def test_creates_and_updates_but_keeps_extras(self, fake_gh: FakeGh, config_file: Path) -> None:
        """
        Test the full apply flow against the fake gh without --prune
        """
        code = gh_labels.main(['apply', '--repo', 'me/proj', '--config', str(config_file)])

        assert code == 0
        assert fake_gh.mutations == [
            (
                'POST',
                'repos/me/proj/labels',
                {'name': 'feature', 'color': '5ab1cd', 'description': 'New capability'},
            ),
            (
                'PATCH',
                'repos/me/proj/labels/Docs',
                {'new_name': 'docs', 'color': '0075ca', 'description': 'Documentation'},
            ),
        ]

    def test_prune_flag_deletes_extras(self, fake_gh: FakeGh, config_file: Path) -> None:
        """
        Test that --prune adds a DELETE for labels missing from the config
        """
        gh_labels.main(['apply', '--repo', 'me/proj', '--config', str(config_file), '--prune'])

        assert ('DELETE', 'repos/me/proj/labels/wontfix', {}) in fake_gh.mutations

    def test_dry_run_flag_changes_nothing(
        self, fake_gh: FakeGh, config_file: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that --dry-run reports actions and makes no mutating call
        """
        code = gh_labels.main(['apply', '-r', 'me/proj', '-c', str(config_file), '-n'])

        assert code == 0
        assert fake_gh.mutations == []
        assert 'create' in capsys.readouterr().out

    def test_second_run_is_idempotent(self, monkeypatch: pytest.MonkeyPatch, config_file: Path) -> None:
        """
        Test that applying to a repository that already matches performs no mutations
        """
        fake = FakeGh([{'name': label.name, 'color': label.color, 'description': label.description} for label in DESIRED])
        monkeypatch.setattr(gh_labels, 'run_gh', fake)

        assert gh_labels.main(['apply', '--repo', 'me/proj', '--config', str(config_file)]) == 0
        assert fake.mutations == []

    def test_repo_defaults_to_current_directory_and_its_host(self, fake_gh: FakeGh, config_file: Path) -> None:
        """
        Test that omitting --repo uses gh repo view and passes the detected host to gh api
        """
        gh_labels.main(['apply', '--config', str(config_file), '--dry-run'])

        api_calls = [call for call in fake_gh.calls if call[0] == 'api']
        assert api_calls
        for call in api_calls:
            at = call.index('--hostname')
            assert call[at:at + 2] == ('--hostname', 'ghe.example.com')

    def test_missing_config_fails_with_exit_code_one(
        self, fake_gh: FakeGh, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that an unreadable config returns 1, names the problem on stderr, and never calls gh
        """
        code = gh_labels.main(['apply', '--repo', 'me/proj', '--config', str(tmp_path / 'absent.toml')])

        assert code == 1
        assert 'config not found' in capsys.readouterr().err
        assert fake_gh.calls == []

    def test_gh_failure_returns_one(
        self, monkeypatch: pytest.MonkeyPatch, config_file: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that a failing gh call is reported on stderr with exit code 1
        """
        def failing(*args: str) -> str:
            raise gh_labels.LabelsError('gh api failed: HTTP 403')

        monkeypatch.setattr(gh_labels, 'run_gh', failing)

        assert gh_labels.main(['apply', '--repo', 'me/proj', '--config', str(config_file)]) == 1
        assert 'HTTP 403' in capsys.readouterr().err

    def test_config_defaults_to_xdg_location(
        self, fake_gh: FakeGh, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        """
        Test that --config defaults to the XDG config path
        """
        target = tmp_path / 'gh-labels' / 'labels.toml'
        target.parent.mkdir()
        target.write_text(gh_labels.render_toml(DESIRED), encoding='utf-8')
        monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path))

        assert gh_labels.main(['apply', '--repo', 'me/proj', '--dry-run']) == 0


class TestMainPull:
    """
    Tests for the pull subcommand
    """
    def test_prints_sorted_toml_that_round_trips(self, fake_gh: FakeGh, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that pull emits valid, case-insensitively sorted TOML matching the repository
        """
        assert gh_labels.main(['pull', '--repo', 'me/proj']) == 0

        labels = gh_labels.parse_labels(tomllib.loads(capsys.readouterr().out))
        assert [label.name for label in labels] == ['bug', 'Docs', 'wontfix']
        assert labels[0] == Label('bug', 'd73a4a', '')

    def test_output_flag_writes_a_file(
        self, fake_gh: FakeGh, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that --output writes the TOML to disk and keeps stdout to a status line
        """
        target = tmp_path / 'out.toml'

        assert gh_labels.main(['pull', '--repo', 'me/proj', '--output', str(target)]) == 0

        assert len(gh_labels.load_labels(target)) == len(EXISTING)
        assert '[[label]]' not in capsys.readouterr().out


USAGE_EXIT = 2  # argparse's exit status for a usage error


class TestParser:
    """
    Tests for build_parser
    """
    def test_subcommand_is_required(self, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that running without a subcommand exits with a usage error
        """
        with pytest.raises(SystemExit) as exc_info:
            gh_labels.main([])

        assert exc_info.value.code == USAGE_EXIT

    def test_help_lists_options(self, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that apply --help documents its options
        """
        with pytest.raises(SystemExit) as exc_info:
            gh_labels.main(['apply', '--help'])

        out = capsys.readouterr().out
        assert exc_info.value.code == 0
        assert all(option in out for option in ('--repo', '--config', '--dry-run', '--prune', '--help'))


class TestScriptFile:
    """
    Tests for the shipped script file itself
    """
    def test_is_executable_with_uv_shebang_and_pep723_block(self) -> None:
        """
        Test that the script is executable, uses a uv shebang, and declares its Python floor inline
        """
        text = SCRIPT_PATH.read_text(encoding='utf-8')

        assert os.access(SCRIPT_PATH, os.X_OK)
        assert text.startswith('#!/usr/bin/env -S uv run --script\n')
        assert '# requires-python = ">=3.11"' in text
        assert '# dependencies = []' in text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/ghtools -v`
Expected: the new tests FAIL with `AttributeError: ... has no attribute 'main'` or `'folduser'`; earlier tests pass.

- [ ] **Step 3: Add imports to the script**

Extend the script's import block so it reads (one per line):

```python
import argparse
import functools
import json
import os
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import quote
from urllib.parse import urlparse
```

- [ ] **Step 4: Append the CLI section**

Append to the end of `gh-labels`:

```python

# ==================================================================================================
# Command-line interface
# ==================================================================================================


def folduser(path: str | Path) -> str:
    """
    Replace the home directory prefix of a path with ``~`` for display.

    :param path: path to display
    :return: the folded path, or the path unchanged when it is outside the home directory
    """
    try:
        return f'~/{Path(path).relative_to(Path.home())}'
    except ValueError:
        return str(path)


class Args(argparse.Namespace):
    """
    Parsed command-line arguments.
    """
    command: str
    repo:    str | None
    config:  Path
    dry_run: bool
    prune:   bool
    output:  Path | None


def _path(value: str) -> Path:
    """
    Argparse type: a path with ``~`` expanded.
    """
    return Path(value).expanduser()


def build_parser() -> argparse.ArgumentParser:
    """
    Build the ``gh-labels`` argument parser.

    :return: parser with ``apply`` and ``pull`` subcommands
    """
    formatter = functools.partial(argparse.RawTextHelpFormatter, max_help_position=50)
    parser = argparse.ArgumentParser(
        prog='gh-labels',
        description="Sync GitHub labels from a TOML file, or export a repository's labels to one.",
        formatter_class=formatter,
        add_help=False,
    )
    subparsers = parser.add_subparsers(dest='command', metavar='COMMAND', required=True)

    def add_target_opts(sub: argparse.ArgumentParser) -> None:
        target_opts = sub.add_argument_group('Target options')
        target_opts.add_argument(
            '-r', '--repo', metavar='[HOST/]OWNER/REPO',
            help='Repository to operate on (default: the repository of the current directory).\n'
                 'HOST is only needed off github.com, e.g. ghe.example.com/OWNER/REPO',
        )

    def add_other_opts(sub: argparse.ArgumentParser) -> None:
        other_opts = sub.add_argument_group('Other options')
        other_opts.add_argument(
            '-h', '--help', action='help', default=argparse.SUPPRESS, help='Show this help message and exit',
        )

    apply_parser = subparsers.add_parser(
        'apply', help='Create and update labels to match the config file', formatter_class=formatter, add_help=False,
    )
    add_target_opts(apply_parser)
    apply_opts = apply_parser.add_argument_group('Apply options')
    apply_opts.add_argument(
        '-c', '--config', type=_path, default=default_config_path(), metavar='PATH',
        help=f'Label definition file (default: {folduser(default_config_path())})',
    )
    apply_opts.add_argument('-n', '--dry-run', action='store_true', help='Show the changes without making them')
    apply_opts.add_argument(
        '--prune', action='store_true', help='Also delete labels that are not in the config file',
    )
    add_other_opts(apply_parser)

    pull_parser = subparsers.add_parser(
        'pull', help="Print a repository's labels as TOML", formatter_class=formatter, add_help=False,
    )
    add_target_opts(pull_parser)
    pull_opts = pull_parser.add_argument_group('Pull options')
    pull_opts.add_argument('-o', '--output', type=_path, metavar='PATH', help='Write the TOML here instead of stdout')
    add_other_opts(pull_parser)

    add_other_opts(parser)
    return parser


def cmd_apply(args: Args) -> int:
    """
    Run the ``apply`` subcommand.

    :param args: parsed arguments
    :raises LabelsError: on a bad config or a failed ``gh`` call
    :return: process exit code
    """
    desired = load_labels(args.config)
    repo    = resolve_repo(args.repo)

    suffix = f' {style("(dry run)", dim=True)}' if args.dry_run else ''
    printf(
        f'🔎 {style("Applying", fg="bright_cyan")} {len(desired)} labels from '
        f'{style(folduser(args.config), fg="magenta")} to {style(str(repo), fg="bright_white", bold=True)}{suffix}',
    )

    plan = build_plan(desired, fetch_labels(repo))
    apply_plan(repo, plan, prune=args.prune, dry_run=args.dry_run)
    summarize(plan, prune=args.prune, dry_run=args.dry_run)
    return 0


def cmd_pull(args: Args) -> int:
    """
    Run the ``pull`` subcommand.

    :param args: parsed arguments
    :raises LabelsError: on a failed ``gh`` call
    :return: process exit code
    """
    repo   = resolve_repo(args.repo)
    labels = sorted(fetch_labels(repo), key=lambda label: label.name.casefold())
    text   = render_toml(labels)

    if args.output is None:
        sys.stdout.write(text)
    else:
        args.output.write_text(text, encoding='utf-8')
        printf(
            f'✅ {style("Wrote", fg="bright_green")} {len(labels)} labels to '
            f'{style(folduser(args.output), fg="magenta")}',
        )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """
    Entry point.

    :param argv: arguments after the program name; defaults to ``sys.argv[1:]``
    :return: process exit code (``0`` on success, ``1`` on any :class:`LabelsError`)
    """
    args = build_parser().parse_args(argv, namespace=Args())
    try:
        return cmd_apply(args) if args.command == 'apply' else cmd_pull(args)
    except LabelsError as e:
        printf(f'❌ {style("Error:", fg="bright_red", bold=True)} {style(e, fg="bright_red")}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
```

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/unit/ghtools -v`
Expected: all tests PASS.

- [ ] **Step 6: Smoke-test the real entry point (no network)**

```bash
stow/ghtools/.local/bin/gh-labels --help
stow/ghtools/.local/bin/gh-labels apply --help
stow/ghtools/.local/bin/gh-labels apply --config /nonexistent.toml --repo me/proj; echo "exit=$?"
```

Expected: usage text lists `apply` and `pull`; `apply --help` lists `--repo`, `--config`, `--dry-run`, `--prune`;
the last command prints `❌ Error: config not found: /nonexistent.toml` and `exit=1` (the config is loaded before any
`gh` call).

- [ ] **Step 7: Lint**

```bash
uv run ruff check --fix stow/ghtools/.local/bin/gh-labels tests/unit/ghtools
uv run ruff check stow/ghtools/.local/bin/gh-labels tests/unit/ghtools
uv run pytest tests/unit/ghtools -q
```

Expected: `All checks passed!`; all tests pass. If a line exceeds 120 characters, wrap it by hand; do not run
`ruff format`.

- [ ] **Step 8: Commit**

```bash
git add stow/ghtools/.local/bin/gh-labels tests/unit/ghtools/test_gh_labels.py
git commit -m "Add gh-labels apply and pull commands"
```

---

### Task 4: Seed label set and package documentation

**Files:**

- Create: `stow/ghtools/.config/gh-labels/labels.toml`
- Modify: `stow/README.md` (package table row; new "GitHub labels" section)
- Modify: any other doc that enumerates stow packages (found in Step 5)
- Modify: `tests/unit/ghtools/test_gh_labels.py` (seed-config test)

**Interfaces:**

- Consumes: `load_labels(path: Path) -> list[Label]` from Task 1.
- Produces: the shipped `labels.toml`, and a doc row `ghtools` that `tests/unit/test_docs_consistency.py` accepts.

- [ ] **Step 1: Write the failing seed test**

Append to the test file:

```python
class TestSeedConfig:
    """
    Tests for the labels.toml shipped in the stow package
    """
    SEED_PATH = REPO_ROOT / 'stow' / 'ghtools' / '.config' / 'gh-labels' / 'labels.toml'

    def test_seed_config_is_valid(self) -> None:
        """
        Test that the shipped label set parses, and that every label carries a description
        """
        labels = gh_labels.load_labels(self.SEED_PATH)

        assert labels
        assert all(label.description for label in labels)
```

Run: `uv run pytest tests/unit/ghtools/test_gh_labels.py::TestSeedConfig -v`
Expected: FAIL with `LabelsError: config not found`.

- [ ] **Step 2: Seed the file from the source repository**

The source repository (the one whose labels are the template) may live on a GitHub host other than `gh`'s default, so
name the host explicitly. This is a read-only call; substitute the real `HOST/OWNER/REPO`:

```bash
stow/ghtools/.local/bin/gh-labels pull --repo HOST/OWNER/REPO \
    --output stow/ghtools/.config/gh-labels/labels.toml
```

Expected: `✅ Wrote 12 labels to ...`. The file contains the 12 labels, sorted by name, with colors but no descriptions.

- [ ] **Step 3: Add descriptions**

Edit `stow/ghtools/.config/gh-labels/labels.toml` so the file reads exactly as follows. The descriptions are drafts for
the user to adjust; the colors are the ones fetched from the source repository in Step 2 (if Step 2 returned a different
color for any label, keep the fetched color):

```toml
# GitHub label definitions applied by `gh-labels apply`.

[[label]]
name        = "bug"
color       = "d73a4a"
description = "Something isn't working"

[[label]]
name        = "cleanup"
color       = "5319e7"
description = "Remove dead code or tidy up"

[[label]]
name        = "documentation"
color       = "0075ca"
description = "Improvements or additions to documentation"

[[label]]
name        = "enhancement"
color       = "a2eeef"
description = "Improvement to an existing feature"

[[label]]
name        = "feature"
color       = "5ab1cd"
description = "New user-facing capability"

[[label]]
name        = "infrastructure"
color       = "7e5f0e"
description = "CI, build, and tooling changes"

[[label]]
name        = "maintenance"
color       = "403ac4"
description = "Dependency bumps and routine upkeep"

[[label]]
name        = "refactoring"
color       = "fef2c0"
description = "Restructure code without changing behavior"

[[label]]
name        = "release"
color       = "b33b9b"
description = "Release preparation or version bump"

[[label]]
name        = "task"
color       = "76600d"
description = "Discrete unit of work"

[[label]]
name        = "unit tests"
color       = "82cd44"
description = "Adding or fixing unit tests"

[[label]]
name        = "work in progress"
color       = "c5def5"
description = "Not ready for review or merge"
```

- [ ] **Step 4: Verify the seed and a read-only dry run against the source repository**

```bash
uv run pytest tests/unit/ghtools -q
stow/ghtools/.local/bin/gh-labels apply --dry-run \
    --repo HOST/OWNER/REPO \
    --config stow/ghtools/.config/gh-labels/labels.toml
```

Expected: tests pass. The dry run prints `🔄 update` for each label that gains a description (all 12), no `create`, no
`delete`, no `extra`, and ends with `Dry run, nothing changed: 0 created, 12 updated, 0 unchanged`. A second `pull`
piped through `diff` against the file is not expected to be empty (descriptions differ until a real apply); that is
fine. **Do not run a real `apply` here**; Task 5 covers live runs.

- [ ] **Step 5: Find every doc that enumerates stow packages**

```bash
grep -rln 'yazi' --include='*.md' . | grep -v '^./docs/plans/' | grep -v '^./archive/'
```

For each hit, open it and add `ghtools` wherever the other packages are enumerated as a list or table (for example
`stow/README.md`, `.ctx/ARCHITECTURE.md`, `.ctx/CONVENTIONS.md`, `docs/README.md`). Skip files that only mention yazi
in passing prose. In `stow/README.md`, add this row to the package table in alphabetical position (between `git` and
`hammerspoon`):

```markdown
| `ghtools`      | `gh-labels` (GitHub label sync CLI) in `~/.local/bin` and its label set in `~/.config/gh-labels/labels.toml` | —               |
```

and add this section after "Git identity":

````markdown
## GitHub labels

The `ghtools` package ships `gh-labels`, which applies one TOML-defined label set to any GitHub repository. Edit
[`ghtools/.config/gh-labels/labels.toml`](ghtools/.config/gh-labels/labels.toml) (each `[[label]]` takes `name`,
`color`, and an optional `description`), then:

```bash
gh-labels apply --dry-run          # preview for the repo in the current directory
gh-labels apply                    # create missing labels, update changed ones, keep extras
gh-labels apply --prune            # also delete labels that are not in labels.toml
gh-labels apply -r HOST/OWNER/REPO   # a repo on a specific host
gh-labels pull -r OWNER/REPO       # print an existing repo's labels as TOML (to seed or refresh the file)
```

`--prune` is opt-in because deleting a label removes it from every issue and pull request that carries it. Requires `gh`
authenticated for the repository's host.
````

- [ ] **Step 6: Format and verify the docs**

```bash
uv run prek run mdformat --files stow/README.md
uv run pytest tests/unit/test_docs_consistency.py tests/unit/stow tests/unit/ghtools -q
```

Expected: mdformat may realign the table (re-run until it reports no changes); all tests pass, in particular
`test_readme_table_matches_stow_dirs` and `test_conf_d_column_matches_snippets_on_disk`. If the `prek` invocation
differs in this repo, use the form documented in `.ctx/BUILD.md` ("Git Hooks (prek)").

- [ ] **Step 7: Verify the stow package links cleanly (dry run)**

```bash
./stow.sh -n ghtools
```

Expected: the dry run lists links for `~/.config/gh-labels/labels.toml` and `~/.local/bin/gh-labels` with no conflicts
and nothing about `__pycache__`. If `stow.sh` rejects the package for a reason not covered here, read its error and
`stow/README.md` before changing anything.

- [ ] **Step 8: Full verification, then commit**

```bash
uv run ruff check stow/ghtools/.local/bin/gh-labels tests/unit/ghtools
uv run pytest tests/unit -q
git status --short
```

Expected: lint clean; the unit suite passes (tests that need a VM or the network are not in `tests/unit`);
`git status` shows only the intended files and no `__pycache__` under `stow/ghtools`.

```bash
git add stow/ghtools stow/README.md tests/unit/ghtools
git add -u -- .ctx docs/README.md 2>/dev/null || true
git commit -m "Ship the ghtools stow package with a seeded label set"
```

Before committing, run `git status --short` once more and confirm that only the files edited in Step 5 appear beside the
package; stage any other doc edited in Step 5 by name.

---

### Task 5: Live rollout (user-run runbook)

These steps change state outside the working tree (the stowed home directory and GitHub repositories), so the user runs
them, or explicitly approves each one. The executing agent stops after Task 4, pushes the branch only if asked, and
opens a pull request with the Task 4 verification output.

**Files:** none.

- [ ] **Step 1: Open the pull request**

From the worktree, after the user approves pushing: push the branch and open a PR against `main` titled
`Add gh-labels and the ghtools stow package`, with a summary (what the tool does, `--prune` is opt-in, the seed file's
descriptions are drafts) and the test plan from Task 4. Never push to `main` directly.

- [ ] **Step 2: Link the package into `$HOME`**

After the PR merges (or from the branch to try it early), from a plain terminal in `~/dotfiles-personal`:

```bash
./stow.sh -n ghtools     # preview
./stow.sh ghtools        # link
command -v gh-labels     # expect ~/.local/bin/gh-labels
gh-labels --help
```

Expected: `gh-labels` resolves through `~/.local/bin` (already on `PATH`). The first run downloads nothing: the script
declares no dependencies, so `uv` only needs a Python >= 3.11.

- [ ] **Step 3: Review the label descriptions**

Edit `~/.config/gh-labels/labels.toml` (a symlink into the repo) to taste, then preview against the source repository:

```bash
gh-labels apply --dry-run -r HOST/OWNER/REPO
```

- [ ] **Step 4: Apply to a new project**

In the new project's directory (or with `-r HOST/OWNER/REPO`):

```bash
gh-labels apply --dry-run     # inspect
gh-labels apply               # create the label set; GitHub's default labels are kept
gh-labels apply --prune       # optional: also remove GitHub's default labels that are not in labels.toml
```

Use `--prune` only on a fresh repo, or after checking that no issue depends on the labels it would delete. A second
`gh-labels apply` must report `0 created, 0 updated`.

---

## Self-Review

**Spec coverage:**

| Spec requirement                                                          | Task                                  |
| ------------------------------------------------------------------------- | ------------------------------------- |
| TOML schema (`name`, `color`, optional `description`) and validation      | Task 1                                |
| `#`-optional, normalised colors; 50/100 character limits; case-insensitive duplicates | Task 1                    |
| Fetch with `--paginate --slurp`; case-folded matching                     | Task 2 (`gh_api`, `fetch_labels`, `build_plan`) |
| Create / update / leave alone; extras reported; `--prune` opt-in; `--dry-run` | Task 2 (`apply_plan`), Task 3 (flags) |
| Idempotent second run                                                     | Task 3 (`test_second_run_is_idempotent`) |
| `pull` subcommand with `-o`                                               | Task 3                                |
| `--repo` default via `gh repo view`, host from URL, `HOST/OWNER/REPO`     | Task 2 (`current_repo`, `parse_repo`), Task 3 |
| `--config` default under XDG config home                                  | Task 1 (`default_config_path`), Task 3 |
| List-argv `gh` calls, URL-quoted names                                    | Task 2 (`run_gh`, `apply_plan`)       |
| Stow package `ghtools`, seed `labels.toml`, executable bit                | Tasks 3 and 4                         |
| Docs row and usage section; docs-consistency test                         | Task 4                                |
| Seeded from an existing repo with drafted descriptions                    | Task 4                                |
| Out of scope (aliases, multi-repo, org inheritance)                       | not implemented, by design            |

**Placeholder scan:** no `TBD`/`TODO`; every code step carries its code. The only judgement calls are the three drafted
areas flagged for the user: the label descriptions (Task 4 Step 3), the doc files that enumerate packages (Task 4
Step 5, found by a concrete `grep`), and long-line wrapping in tests (Task 3 Step 7).

**Type consistency:** `Label(name, color, description='')`, `LabelsError`, `RepoRef(host, owner, name)`,
`Plan(create, update, unchanged, extra)`, `gh_api(repo, endpoint, *, method, fields, paginate)`,
`apply_plan(repo, plan, *, prune, dry_run)`, `summarize(plan, *, prune, dry_run)`, `main(argv) -> int` are named and
shaped identically in every task that mentions them. `FakeGh.mutations` relies on `gh_api` placing the endpoint at
`args[1]` and emitting `--method <M>` and `--raw-field k=v` pairs, which Task 2 Step 4 implements.
