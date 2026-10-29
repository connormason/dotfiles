# Subagent Model Router Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a configurable Claude Code hook pair that routes `Agent`/`Task` subagent spawns to the cheapest adequate
model, in `advise` mode first, with a decision log.

**Architecture:** One stdlib-only script, `model-router.py`, invoked as `pre` (PreToolUse: decide, then advise or
rewrite `model`) or `post` (PostToolUse: log). A pure `decide()` function takes plain dicts, so it is unit-tested without
stdin mocking. Config is layered JSON (shipped default → user → project). Wiring lives in `render/claude.json`.

**Tech Stack:** Python 3 stdlib (hook runtime), pytest (tests), the repo's `uv-public.sh` wrapper, `prek`/`mdformat`.

Design: [`2026-10-29-model-router-design.md`](2026-10-29-model-router-design.md).

## Global Constraints

- The hook runs under bare `python3` of unpinned version: stdlib only, JSON config, no syntax newer than Python 3.9
  (Task 1 confirms the real version).
- Fail open: any error → exit 0, tool call unchanged, error appended to the decision log. The hook never denies or
  blocks a call.
- Never log prompt text; log only the matched rule id and the prompt length.
- A rewrite sets `model` to a bare alias only (`haiku`, `sonnet`, `opus`, `fable`), never a full model ID.
- Ships with `"mode": "advise"`. `enforce` is switched on by the user after reviewing the log.
- Settings wiring goes in `render/claude.json` only, never the live `~/.claude/settings.json` (render drift guard).
- Repo Python style: single quotes, one import per line (isort `force-single-line`), `from __future__ import annotations`
  first, Sphinx docstrings, no `__all__` in executed scripts, no blank line after a class docstring.
- **Never run `ruff format`.** Lint with `scripts/hooks/uv-public.sh run ruff check --fix <files>`. Run Python only via
  `scripts/hooks/uv-public.sh run …`, never bare `python`/`python3`.
- This repo is public: nothing employer-specific in any file.
- Tests: multi-line docstrings, `-> None` on every test method, parametrize with tuple format.
- Paths: `$WT` is the worktree root, `~/dotfiles-personal/.claude/worktrees/model-router`. Commands assume the shell's
  working directory is `$WT` (the worktree tool sets this).

## File Structure

| File                                                       | Responsibility                                                            |
| ---------------------------------------------------------- | ------------------------------------------------------------------------- |
| `$WT/stow/claude/.claude/hooks/model-router.py`            | Config, `decide()`, hook I/O, log writer, CLI entry (created in Tasks 2–4) |
| `$WT/stow/claude/.claude/hooks/model-router.default.json`  | Shipped default config                                                    |
| `$WT/tests/unit/test_model_router.py`                      | Unit + CLI tests                                                          |
| `$WT/tests/fixtures/model_router/post_agent_payload.json`  | Real `PostToolUse` payload captured by the spike                          |
| `$WT/render/claude.json`                                   | Hook wiring and the `CLAUDE_CODE_SUBAGENT_MODEL` baseline                 |
| `$WT/docs/MODEL_ROUTER.md`, `$WT/docs/README.md`           | User-facing docs and index row                                            |

---

### Task 0: Isolated workspace and planning docs

**Files:**
- Create: worktree `$WT` on branch `model-router`
- Create (moved in): `$WT/docs/plans/2026-10/2026-10-29-model-router-design.md`, `…-plan.md`

- [ ] **Step 1: Create the worktree**

Load the tool schema with `ToolSearch` query `select:EnterWorktree,ExitWorktree`, then call `EnterWorktree` with name
`model-router`. Confirm:

Run: `git branch --show-current && pwd`
Expected: `model-router` and a path ending in `.claude/worktrees/model-router`

- [ ] **Step 2: Bring the two untracked planning docs onto the branch**

They exist only in the main checkout (untracked), so the worktree does not have them.

```bash
mkdir -p docs/plans/2026-10
cp ~/dotfiles-personal/docs/plans/2026-10/2026-10-29-model-router-design.md docs/plans/2026-10/
cp ~/dotfiles-personal/docs/plans/2026-10/2026-10-29-model-router-plan.md docs/plans/2026-10/
diff -q ~/dotfiles-personal/docs/plans/2026-10/2026-10-29-model-router-design.md docs/plans/2026-10/2026-10-29-model-router-design.md
diff -q ~/dotfiles-personal/docs/plans/2026-10/2026-10-29-model-router-plan.md docs/plans/2026-10/2026-10-29-model-router-plan.md
```
Expected: `diff` prints nothing (identical).

- [ ] **Step 3: Remove the untracked originals from the main checkout**

Only after Step 2's `diff` is silent. They would otherwise block the later merge ("untracked file would be
overwritten").

```bash
rm ~/dotfiles-personal/docs/plans/2026-10/2026-10-29-model-router-design.md
rm ~/dotfiles-personal/docs/plans/2026-10/2026-10-29-model-router-plan.md
```

- [ ] **Step 4: Commit**

```bash
git add docs/plans/2026-10/2026-10-29-model-router-design.md docs/plans/2026-10/2026-10-29-model-router-plan.md
git commit -m "docs: model-router design and implementation plan"
```

---

### Task 1: Feasibility spike (manual; gates everything else)

Verifies the three open questions from the design before any real code exists. Nothing in the repo is touched except
the design doc's findings.

**Files:**
- Create (outside repo): `$TMPDIR/router-spike/spike.py`, `$TMPDIR/router-spike/settings.json`
- Create: `$WT/tests/fixtures/model_router/post_agent_payload.json`
- Modify: `$WT/docs/plans/2026-10/2026-10-29-model-router-design.md` (Open questions section)

**Interfaces:**
- Produces: the recorded `PostToolUse` payload fixture (consumed by Task 4), the confirmed Python version, and a
  go/no-go on `updatedInput` for `Agent`.

- [ ] **Step 1: Write the throwaway spike hook and its settings file**

```bash
SPIKE_DIR="$TMPDIR/router-spike"
mkdir -p "$SPIKE_DIR"

cat > "$SPIKE_DIR/spike.py" <<'PY'
#!/usr/bin/env python3
"""Throwaway spike: record hook payloads and force model=haiku on Agent/Task spawns."""
from __future__ import annotations

import json
import sys

stage, log_path = sys.argv[1], sys.argv[2]
payload = json.load(sys.stdin)
with open(log_path, 'a', encoding='utf-8') as handle:
    handle.write(json.dumps({'stage': stage, 'python': sys.version, 'payload': payload}) + '\n')

if stage == 'pre' and payload.get('tool_name') in ('Agent', 'Task'):
    updated = dict(payload['tool_input'])
    updated['model'] = 'haiku'
    print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'updatedInput': updated}}))
PY

cat > "$SPIKE_DIR/settings.json" <<EOF
{
  "hooks": {
    "PreToolUse": [
      {"matcher": "Agent|Task", "hooks": [{"type": "command", "command": "python3 $SPIKE_DIR/spike.py pre $SPIKE_DIR/log.jsonl"}]}
    ],
    "PostToolUse": [
      {"matcher": "Agent|Task", "hooks": [{"type": "command", "command": "python3 $SPIKE_DIR/spike.py post $SPIKE_DIR/log.jsonl"}]}
    ]
  }
}
EOF
rm -f "$SPIKE_DIR/log.jsonl"
```

- [ ] **Step 2: Run a one-shot session that spawns a subagent and asks it to state its model**

If the sandbox denies the `claude` binary, ask the user to run the command with the `!` prefix.

```bash
claude -p "Use the Agent tool exactly once with subagent_type general-purpose and this prompt: 'Reply with only your exact model ID as stated in your system prompt.' After it returns, reply with the subagent's answer verbatim." --settings "$SPIKE_DIR/settings.json" --output-format text
```
Expected: a reply containing a **Haiku** model ID. An Opus ID means the rewrite was ignored (or the settings were not
merged; Step 3 tells them apart).

- [ ] **Step 3: Read the spike log with the Read tool (`$TMPDIR/router-spike/log.jsonl`) and record three findings**

1. **Rewrite works?** A `pre` record exists *and* the reply named Haiku → yes. A `pre` record exists but the reply
   named Opus → `updatedInput` is ignored for this tool. No `pre` record → the `--settings` hooks were not merged
   (fix the invocation and rerun; this is not a design failure).
2. **`PostToolUse` shape:** in the `post` record, note the `tool_name` (`Agent` vs `Task`), and where, if anywhere, the
   model that actually ran appears (look in `tool_response` and `tool_input`).
3. **Python version:** read the `python` field. If older than 3.9, stop and tell the user.

- [ ] **Step 4: Decide, then record**

- If rewrite works as-is: continue.
- If rewrite is ignored without `"permissionDecision": "allow"`, edit `spike.py` to add that field to the
  `hookSpecificOutput`, rerun Steps 2–3, and if it then works, **stop and ask the user**: emitting `allow` skips the
  permission prompt for `Agent` calls, which is a security-relevant side effect.
- If rewrite never works: **stop**. Report to the user that the design degrades to advise-only and needs revision.

Replace the design doc's "Open questions" section with a "Spike results (2026-10-29)" section stating the three
findings above (rewrite verdict, Post payload shape and the `tool_name` observed, Python version).

- [ ] **Step 5: Save the recorded `PostToolUse` payload as a test fixture**

Create `$WT/tests/fixtures/model_router/post_agent_payload.json` from the `payload` of the `post` record. Replace
`session_id`, `transcript_path`, `cwd`, `tool_use_id`, and any prompt or response text with fixed dummy strings
(`"session-1"`, `"/tmp/transcript.jsonl"`, `"/tmp/project"`, `"toolu_1"`, `"redacted"`). Add one extra top-level key,
`"_expected_resolved_model"`, set to the model string found in Step 3 finding 2, or `null` if the payload carries none.

- [ ] **Step 6: Commit**

```bash
git add tests/fixtures/model_router/post_agent_payload.json docs/plans/2026-10/2026-10-29-model-router-design.md
git commit -m "docs: record model-router spike results and Post payload fixture"
```

---

### Task 2: Config loading, layering, and validation

**Files:**
- Create: `$WT/stow/claude/.claude/hooks/model-router.default.json`
- Create: `$WT/stow/claude/.claude/hooks/model-router.py` (config section only)
- Create: `$WT/tests/unit/test_model_router.py`

**Interfaces:**
- Produces (all in `model-router.py`):
  - `class ConfigError(ValueError)`
  - `VALID_MODELS: tuple[str, ...]`, `VALID_MODES: tuple[str, ...]`, `DEFAULT_CONFIG: Path`
  - `read_layer(path: Path, *, required: bool) -> dict`
  - `merge_layers(base: dict, override: dict) -> dict`
  - `validate_config(cfg: dict) -> None` (raises `ConfigError`)
  - `load_config(cwd: Path, home: Path | None = None, default_path: Path = DEFAULT_CONFIG) -> dict`

- [ ] **Step 1: Write the failing tests**

Create `$WT/tests/unit/test_model_router.py`:

```python
"""
Unit tests for stow/claude/.claude/hooks/model-router.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from typing import NamedTuple

import pytest

if TYPE_CHECKING:
    from types import ModuleType

HOOKS_DIR = Path(__file__).resolve().parents[2] / 'stow' / 'claude' / '.claude' / 'hooks'
SCRIPT_PATH = HOOKS_DIR / 'model-router.py'


def _load_module() -> ModuleType:
    """
    Import the hyphenated hook script as module ``model_router``
    """
    spec = importlib.util.spec_from_file_location('model_router', SCRIPT_PATH)
    assert spec        is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules['model_router'] = module
    spec.loader.exec_module(module)
    return module


model_router = _load_module()


class Env(NamedTuple):
    """
    Isolated HOME, state directory, and project directory for one test
    """
    home:    Path
    state:   Path
    project: Path


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Env:
    """
    Point HOME and XDG_STATE_HOME at throwaway directories so no real config or log is touched
    """
    home = tmp_path / 'home'
    project = tmp_path / 'proj'
    home.mkdir()
    project.mkdir()
    monkeypatch.setenv('HOME', str(home))
    monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path / 'state'))
    return Env(home, tmp_path / 'state', project)


def _write_layer(root: Path, data: object) -> None:
    """
    Write ``root/.claude/model-router.json``
    """
    path = root / '.claude' / 'model-router.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding='utf-8')


def _default_cfg() -> dict:
    """
    The shipped default config, unmerged
    """
    return model_router.read_layer(model_router.DEFAULT_CONFIG, required=True)


class TestLoadConfig:
    """
    Tests for layered config loading
    """
    def test_default_only(self, env: Env) -> None:
        """
        Test that the shipped default loads, validates, and starts in advise mode
        """
        cfg = model_router.load_config(env.project)
        assert cfg['mode'] == 'advise'
        assert set(cfg['classes']) == {'mechanical', 'standard', 'hard'}

    def test_user_layer_overrides_scalar(self, env: Env) -> None:
        """
        Test that the user layer overrides a default scalar
        """
        _write_layer(env.home, {'mode': 'enforce'})
        assert model_router.load_config(env.project)['mode'] == 'enforce'

    def test_project_layer_wins_over_user(self, env: Env) -> None:
        """
        Test that the project layer beats the user layer
        """
        _write_layer(env.home, {'mode': 'enforce'})
        _write_layer(env.project, {'mode': 'off'})
        assert model_router.load_config(env.project)['mode'] == 'off'

    def test_rules_concatenate_with_project_first(self, env: Env) -> None:
        """
        Test that project rules are evaluated before user rules, which precede the defaults
        """
        _write_layer(env.home, {'rules': [{'id': 'user', 'class': 'hard', 'any': ['zzz']}]})
        _write_layer(env.project, {'rules': [{'id': 'proj', 'class': 'hard', 'any': ['yyy']}]})
        ids = [rule['id'] for rule in model_router.load_config(env.project)['rules']]
        assert ids[:2] == ['proj', 'user']
        assert 'hard-keywords' in ids

    def test_classes_deep_merge(self, env: Env) -> None:
        """
        Test that overriding one class keeps the others
        """
        _write_layer(env.home, {'classes': {'standard': 'opus'}})
        classes = model_router.load_config(env.project)['classes']
        assert classes['standard'] == 'opus'
        assert classes['mechanical'] == 'haiku'

    def test_same_layer_not_applied_twice(self, env: Env) -> None:
        """
        Test that running from HOME does not apply the user layer as both user and project
        """
        _write_layer(env.home, {'rules': [{'id': 'user', 'class': 'hard', 'any': ['zzz']}]})
        ids = [rule['id'] for rule in model_router.load_config(env.home)['rules']]
        assert ids.count('user') == 1

    def test_invalid_json_layer_raises(self, env: Env) -> None:
        """
        Test that an unparsable layer raises ConfigError rather than being skipped
        """
        path = env.home / '.claude' / 'model-router.json'
        path.parent.mkdir(parents=True)
        path.write_text('{nope', encoding='utf-8')
        with pytest.raises(model_router.ConfigError):
            model_router.load_config(env.project)

    def test_non_object_root_raises(self, env: Env) -> None:
        """
        Test that a JSON array at the root raises ConfigError
        """
        _write_layer(env.home, ['not', 'an', 'object'])
        with pytest.raises(model_router.ConfigError):
            model_router.load_config(env.project)


class TestValidateConfig:
    """
    Tests for config validation
    """
    @pytest.mark.parametrize(
        ('key', 'value'),
        [
            ('mode',            'loud'),
            ('classes',         {'x': 'gpt'}),
            ('classes',         {}),
            ('floor',           'mega'),
            ('agent_overrides', {'Plan': 'gpt'}),
            ('agent_overrides', ['Plan']),
            ('classify_types',  'general-purpose'),
            ('opt_out_prefix',  5),
            ('rules',           'x'),
            ('rules',           [{'class': 'nope', 'any': ['x']}]),
            ('rules',           [{'class': 'hard', 'any': ['(']}]),
            ('rules',           [{'class': 'hard', 'any': 'x'}]),
            ('rules',           [{'class': 'hard', 'any': []}]),
            ('rules',           ['not-an-object']),
        ],
    )
    def test_invalid_values_rejected(self, key: str, value: object) -> None:
        """
        Test that each malformed setting raises ConfigError
        """
        cfg = {**_default_cfg(), key: value}
        with pytest.raises(model_router.ConfigError):
            model_router.validate_config(cfg)

    def test_default_config_is_valid(self) -> None:
        """
        Test that the shipped default passes validation
        """
        model_router.validate_config(_default_cfg())
```

Imports note: `ruff check --fix` will merge/sort the two `typing` imports per the repo's `force-single-line` rule; keep
them as shown.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `scripts/hooks/uv-public.sh run --group test pytest tests/unit/test_model_router.py -v`
Expected: collection error / `FileNotFoundError` (the script does not exist yet).

- [ ] **Step 3: Write the default config**

Create `$WT/stow/claude/.claude/hooks/model-router.default.json`. `hard` rules come first so a prompt carrying both
signals is never routed down:

```json
{
  "mode": "advise",
  "opt_out_prefix": "~",
  "classes": {
    "mechanical": "haiku",
    "standard": "sonnet",
    "hard": "opus"
  },
  "agent_overrides": {
    "Plan": "opus"
  },
  "classify_types": ["general-purpose", "Explore"],
  "rules": [
    {
      "id": "hard-keywords",
      "class": "hard",
      "any": [
        "\\barchitect",
        "\\bdesign\\b.*\\btrade-?offs?\\b",
        "\\broot cause\\b",
        "\\bsecurity (review|audit)\\b",
        "\\brace condition\\b"
      ]
    },
    {
      "id": "mechanical-keywords",
      "class": "mechanical",
      "any": [
        "\\brename\\b",
        "\\bgrep\\b",
        "\\blist all\\b",
        "\\bfind (all|every)\\b",
        "\\bwhere (is|are)\\b"
      ]
    }
  ],
  "floor": "haiku",
  "log": true
}
```

- [ ] **Step 4: Write the config section of the script**

Create `$WT/stow/claude/.claude/hooks/model-router.py`:

```python
#!/usr/bin/env python3
"""
PreToolUse / PostToolUse hook: route subagent spawns to the cheapest adequate model.

Invoked as ``model-router.py pre`` (advise on, or rewrite the ``model`` of, ``Agent``/``Task`` calls) or
``model-router.py post`` (log the outcome). Hooks cannot change the main session's model, so only subagent spawns are
routed. The hook fails open: any error leaves the call unchanged and is appended to the decision log.

See docs/MODEL_ROUTER.md for configuration and rollout.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from datetime import timezone
from pathlib import Path

# ==============================================================================
# Constants
# ==============================================================================

VALID_MODELS = ('haiku', 'sonnet', 'opus', 'fable')
VALID_MODES = ('off', 'advise', 'enforce')
TIER_ORDER = {'haiku': 0, 'sonnet': 1, 'opus': 2}
ROUTED_TOOLS = ('Agent', 'Task')
DEFAULT_CONFIG = Path(__file__).with_name('model-router.default.json')
CONFIG_NAME = 'model-router.json'
LOG_MAX_BYTES = 1_000_000


# ==============================================================================
# Config
# ==============================================================================

class ConfigError(ValueError):
    """
    Raised when a config layer is unreadable or fails validation.
    """


def read_layer(path: Path, *, required: bool) -> dict:
    """
    Read one JSON config layer.

    :param path: file to read.
    :param required: when true a missing file is an error; otherwise it yields an empty layer.
    :raises ConfigError: if the file is missing (when required), unparsable, or not a JSON object.
    :return: the parsed layer.
    """
    if not path.is_file():
        if required:
            raise ConfigError(f'missing config: {path}')
        return {}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as e:
        raise ConfigError(f'unreadable config {path}: {e!s}') from e
    if not isinstance(data, dict):
        raise ConfigError(f'config root must be an object: {path}')
    return data


def merge_layers(base: dict, override: dict) -> dict:
    """
    Merge ``override`` onto ``base``: objects deep-merge, ``rules`` concatenate with override first, all else replaces.

    :param base: lower-precedence layer.
    :param override: higher-precedence layer.
    :return: a new merged dict.
    """
    merged = dict(base)
    for key, value in override.items():
        if key == 'rules' and isinstance(value, list) and isinstance(base.get(key), list):
            merged[key] = value + base[key]
        elif isinstance(value, dict) and isinstance(base.get(key), dict):
            merged[key] = merge_layers(base[key], value)
        else:
            merged[key] = value
    return merged


def _check_model(value: object, where: str) -> None:
    """
    Require ``value`` to be one of the supported model aliases.
    """
    if value not in VALID_MODELS:
        raise ConfigError(f'{where}: {value!r} is not one of {", ".join(VALID_MODELS)}')


def _validate_rule(rule: object, index: int, classes: dict) -> None:
    """
    Validate one classification rule.
    """
    where = f'rules[{index}]'
    if not isinstance(rule, dict):
        raise ConfigError(f'{where}: must be an object')
    if rule.get('class') not in classes:
        raise ConfigError(f'{where}.class: {rule.get("class")!r} is not a defined class')
    patterns = rule.get('any')
    if not isinstance(patterns, list) or not patterns or not all(isinstance(p, str) for p in patterns):
        raise ConfigError(f'{where}.any: must be a non-empty list of strings')
    for pattern in patterns:
        try:
            re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            raise ConfigError(f'{where}.any: invalid regex {pattern!r}: {e!s}') from e


def validate_config(cfg: dict) -> None:
    """
    Validate a fully merged config.

    :param cfg: merged config.
    :raises ConfigError: on the first malformed setting.
    """
    if cfg.get('mode') not in VALID_MODES:
        raise ConfigError(f'mode: {cfg.get("mode")!r} is not one of {", ".join(VALID_MODES)}')

    classes = cfg.get('classes')
    if not isinstance(classes, dict) or not classes:
        raise ConfigError('classes: must be a non-empty object')
    for name, model in classes.items():
        _check_model(model, f'classes.{name}')

    overrides = cfg.get('agent_overrides', {})
    if not isinstance(overrides, dict):
        raise ConfigError('agent_overrides: must be an object')
    for name, model in overrides.items():
        _check_model(model, f'agent_overrides.{name}')

    if cfg.get('floor') is not None:
        _check_model(cfg['floor'], 'floor')

    if not isinstance(cfg.get('opt_out_prefix', ''), str):
        raise ConfigError('opt_out_prefix: must be a string')

    types = cfg.get('classify_types', [])
    if not isinstance(types, list) or not all(isinstance(t, str) for t in types):
        raise ConfigError('classify_types: must be a list of strings')

    rules = cfg.get('rules', [])
    if not isinstance(rules, list):
        raise ConfigError('rules: must be a list')
    for index, rule in enumerate(rules):
        _validate_rule(rule, index, classes)


def load_config(cwd: Path, home: Path | None = None, default_path: Path = DEFAULT_CONFIG) -> dict:
    """
    Load and validate the layered config: shipped default, then ``~/.claude``, then ``<cwd>/.claude``.

    A layer reachable through both the home and project paths (cwd == home) is applied once.

    :param cwd: the session's working directory (source of the project layer).
    :param home: home directory; defaults to the current user's.
    :param default_path: the shipped default config.
    :raises ConfigError: if any layer is unreadable or the merged result is invalid.
    :return: the merged, validated config.
    """
    home = home or Path.home()
    cfg = read_layer(default_path, required=True)
    seen: list[Path] = []
    for root in (home, cwd):
        path = (root / '.claude' / CONFIG_NAME).resolve()
        if path in seen:
            continue
        seen.append(path)
        cfg = merge_layers(cfg, read_layer(path, required=False))
    validate_config(cfg)
    return cfg
```

Imports `os`, `sys`, `datetime`, `timezone` are used by later tasks; ruff will flag them as unused until then. Add them
in the task that first uses them if `ruff check` complains (Task 4 uses all four).

- [ ] **Step 5: Run the tests to verify they pass**

Run: `scripts/hooks/uv-public.sh run --group test pytest tests/unit/test_model_router.py -v`
Expected: all `TestLoadConfig` and `TestValidateConfig` tests PASS.

- [ ] **Step 6: Lint, then commit**

Run: `scripts/hooks/uv-public.sh run ruff check --fix stow/claude/.claude/hooks/model-router.py tests/unit/test_model_router.py`
Expected: clean. If it reports `F401` for `os`, `sys`, `datetime`, `timezone`, remove those four imports now and re-add
them in Task 4.

```bash
git add stow/claude/.claude/hooks/model-router.py stow/claude/.claude/hooks/model-router.default.json tests/unit/test_model_router.py
git commit -m "feat(claude): model-router config loading, layering, and validation"
```

---

### Task 3: The decision function

**Files:**
- Modify: `$WT/stow/claude/.claude/hooks/model-router.py` (append a decision section)
- Modify: `$WT/tests/unit/test_model_router.py` (append `TestDecide`)

**Interfaces:**
- Consumes: `load_config` / `_default_cfg()` from Task 2.
- Produces:
  - `@dataclass class Decision` with fields `action: str` (`'passthrough' | 'advise' | 'rewrite'`), `reason: str`,
    `model: str | None = None`, `cls: str | None = None`, `rule: str | None = None`
  - `apply_floor(model: str, floor: str | None) -> str`
  - `decide(tool_input: dict, cfg: dict) -> Decision`
  - `reason` values: `mode-off`, `opt-out`, `unmatched`, `agent-override`, `rule`, `preset-agree`, `preset-disagree`.
    For `preset-*`, `model` holds what the router *would* have chosen.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_model_router.py`:

```python
GP = 'general-purpose'


def _cfg(**overrides: object) -> dict:
    """
    The default config with top-level settings replaced
    """
    return {**_default_cfg(), **overrides}


class TestDecide:
    """
    Tests for the pure decision function
    """
    @pytest.mark.parametrize(
        ('tool_input', 'overrides', 'action', 'model', 'reason'),
        [
            # classified by rule
            ({'subagent_type': GP, 'prompt': 'rename the helper foo across the repo'},
             {'mode': 'enforce'},                  'rewrite',     'haiku',  'rule'),
            ({'subagent_type': GP, 'prompt': 'weigh the design trade-offs of two caches'},
             {'mode': 'enforce'},                  'rewrite',     'opus',   'rule'),
            ({'subagent_type': GP, 'prompt': 'rename helpers, then explain the design tradeoffs'},
             {'mode': 'enforce'},                  'rewrite',     'opus',   'rule'),
            ({'subagent_type': 'Explore', 'prompt': 'list all usages of foo'},
             {'mode': 'enforce'},                  'rewrite',     'haiku',  'rule'),
            ({'prompt': 'list all usages of foo'},
             {'mode': 'enforce'},                  'rewrite',     'haiku',  'rule'),
            ({'subagent_type': GP, 'description': 'grep for TODOs', 'prompt': 'do it'},
             {'mode': 'enforce'},                  'rewrite',     'haiku',  'rule'),
            # per-agent override
            ({'subagent_type': 'Plan', 'prompt': 'draft a plan'},
             {'mode': 'enforce'},                  'rewrite',     'opus',   'agent-override'),
            # advise mode never rewrites
            ({'subagent_type': GP, 'prompt': 'rename x'},
             {},                                   'advise',      'haiku',  'rule'),
            # floor lifts the chosen tier
            ({'subagent_type': GP, 'prompt': 'rename x'},
             {'mode': 'enforce', 'floor': 'sonnet'}, 'rewrite',   'sonnet', 'rule'),
            # pass-through cases
            ({'subagent_type': GP, 'prompt': 'summarize this module'},
             {'mode': 'enforce'},                  'passthrough', None,     'unmatched'),
            ({'subagent_type': 'file-searcher', 'prompt': 'rename x'},
             {'mode': 'enforce'},                  'passthrough', None,     'unmatched'),
            ({'subagent_type': GP, 'prompt': '~rename x'},
             {'mode': 'enforce'},                  'passthrough', None,     'opt-out'),
            ({'subagent_type': GP, 'prompt': 'rename x'},
             {'mode': 'off'},                      'passthrough', None,     'mode-off'),
            # caller already chose a model: never overridden, disagreement is still reported
            ({'subagent_type': GP, 'prompt': 'rename x', 'model': 'sonnet'},
             {'mode': 'enforce'},                  'passthrough', 'haiku',  'preset-disagree'),
            ({'subagent_type': GP, 'prompt': 'rename x', 'model': 'haiku'},
             {'mode': 'enforce'},                  'passthrough', 'haiku',  'preset-agree'),
        ],
    )
    def test_decision_table(
        self,
        tool_input: dict,
        overrides: dict,
        action: str,
        model: str | None,
        reason: str,
    ) -> None:
        """
        Test the decision flow across classification, overrides, opt-out, mode, floor, and preset models
        """
        decision = model_router.decide(tool_input, _cfg(**overrides))
        assert (decision.action, decision.model, decision.reason) == (action, model, reason)

    def test_rule_decision_carries_class_and_rule_id(self) -> None:
        """
        Test that a rule match reports its class and rule id
        """
        decision = model_router.decide({'subagent_type': GP, 'prompt': 'rename x'}, _cfg())
        assert decision.cls  == 'mechanical'
        assert decision.rule == 'mechanical-keywords'

    def test_rule_without_id_gets_positional_id(self) -> None:
        """
        Test that an id-less rule is reported as rule-<index>
        """
        cfg = _cfg(rules=[{'class': 'hard', 'any': ['zzz']}])
        decision = model_router.decide({'subagent_type': GP, 'prompt': 'zzz'}, cfg)
        assert decision.rule == 'rule-0'

    def test_apply_floor_ignores_unranked_models(self) -> None:
        """
        Test that a model outside the tier order is left untouched by the floor
        """
        assert model_router.apply_floor('fable', 'sonnet') == 'fable'
        assert model_router.apply_floor('haiku', None) == 'haiku'
        assert model_router.apply_floor('haiku', 'opus') == 'opus'
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `scripts/hooks/uv-public.sh run --group test pytest tests/unit/test_model_router.py::TestDecide -v`
Expected: FAIL — `AttributeError: module 'model_router' has no attribute 'decide'`.

- [ ] **Step 3: Implement the decision section**

Add `from dataclasses import dataclass` to the imports (alphabetical, before `datetime` is fine; ruff will order), then
append to `model-router.py`:

```python
# ==============================================================================
# Decision
# ==============================================================================

@dataclass
class Decision:
    """
    Outcome of routing one spawn. For ``preset-*`` reasons, ``model`` is what the router would have chosen.
    """
    action: str
    reason: str
    model:  str | None = None
    cls:    str | None = None
    rule:   str | None = None


def apply_floor(model: str, floor: str | None) -> str:
    """
    Lift ``model`` to ``floor`` when it ranks lower; models outside ``TIER_ORDER`` are returned unchanged.

    :param model: the chosen model alias.
    :param floor: minimum tier, or ``None`` for no floor.
    :return: the model after applying the floor.
    """
    if floor in TIER_ORDER and model in TIER_ORDER and TIER_ORDER[model] < TIER_ORDER[floor]:
        return floor
    return model


def decide(tool_input: dict, cfg: dict) -> Decision:
    """
    Decide how to route one ``Agent``/``Task`` call. First match wins; every early exit leaves the call untouched.

    :param tool_input: the tool call's input (``subagent_type``, ``description``, ``prompt``, optional ``model``).
    :param cfg: validated, merged config.
    :return: the routing decision.
    """
    if cfg.get('mode') == 'off':
        return Decision('passthrough', 'mode-off')

    description = str(tool_input.get('description') or '')
    prompt = str(tool_input.get('prompt') or '')
    prefix = cfg.get('opt_out_prefix') or ''
    if prefix and (prompt.lstrip().startswith(prefix) or description.lstrip().startswith(prefix)):
        return Decision('passthrough', 'opt-out')

    subagent_type = str(tool_input.get('subagent_type') or 'general-purpose')
    chosen: str | None = None
    cls: str | None = None
    rule_id: str | None = None
    reason = 'unmatched'

    overrides = cfg.get('agent_overrides') or {}
    if subagent_type in overrides:
        chosen, reason = overrides[subagent_type], 'agent-override'
    elif subagent_type in (cfg.get('classify_types') or []):
        text = f'{description}\n{prompt}'
        for index, rule in enumerate(cfg.get('rules') or []):
            if any(re.search(pattern, text, re.IGNORECASE) for pattern in rule['any']):
                cls = rule['class']
                chosen = cfg['classes'][cls]
                rule_id = rule.get('id') or f'rule-{index}'
                reason = 'rule'
                break

    if chosen is None:
        return Decision('passthrough', 'unmatched')

    chosen = apply_floor(chosen, cfg.get('floor'))
    preset = tool_input.get('model')
    if preset:
        verdict = 'preset-agree' if preset == chosen else 'preset-disagree'
        return Decision('passthrough', verdict, chosen, cls, rule_id)

    action = 'advise' if cfg.get('mode') == 'advise' else 'rewrite'
    return Decision(action, reason, chosen, cls, rule_id)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `scripts/hooks/uv-public.sh run --group test pytest tests/unit/test_model_router.py -v`
Expected: all PASS (Task 2 tests included).

- [ ] **Step 5: Lint, then commit**

Run: `scripts/hooks/uv-public.sh run ruff check --fix stow/claude/.claude/hooks/model-router.py tests/unit/test_model_router.py`
Expected: clean.

```bash
git add stow/claude/.claude/hooks/model-router.py tests/unit/test_model_router.py
git commit -m "feat(claude): model-router decision function"
```

---

### Task 4: Hook I/O, decision log, and CLI

**Files:**
- Modify: `$WT/stow/claude/.claude/hooks/model-router.py` (append output, log, run, main)
- Modify: `$WT/tests/unit/test_model_router.py` (append tests; add imports `os`, `subprocess`)

**Interfaces:**
- Consumes: `Decision`, `decide`, `load_config`, `ConfigError`, `ROUTED_TOOLS`, `LOG_MAX_BYTES` (Tasks 2–3).
- Produces:
  - `build_pre_output(tool_input: dict, decision: Decision) -> dict | None`
  - `handle_pre(payload: dict, cfg: dict) -> tuple[dict | None, dict]` (hook output, log record)
  - `extract_resolved_model(tool_response: object) -> str | None`
  - `handle_post(payload: dict) -> dict` (log record)
  - `now_iso() -> str`, `state_dir() -> Path`, `write_log(record: dict) -> None`
  - `run(mode: str, raw: str) -> dict | None` — never raises
  - `main() -> None`
- Log file: `<state_dir()>/decisions.jsonl`, rotated to `decisions.jsonl.1` above `LOG_MAX_BYTES`.

- [ ] **Step 1: Write the failing tests**

Add `import os` and `import subprocess` to the test file's imports, then append:

```python
FIXTURE_DIR = Path(__file__).resolve().parents[1] / 'fixtures' / 'model_router'


def _event(tool_input: dict, env: Env, tool_name: str = 'Agent', **extra: object) -> str:
    """
    Serialize a hook event payload
    """
    payload = {
        'session_id': 'session-1',
        'tool_use_id': 'toolu_1',
        'cwd': str(env.project),
        'tool_name': tool_name,
        'tool_input': tool_input,
        **extra,
    }
    return json.dumps(payload)


def _log_path(env: Env) -> Path:
    """
    Location of the decision log inside the isolated state directory
    """
    return env.state / 'dotfiles' / 'model-router' / 'decisions.jsonl'


def _records(env: Env) -> list[dict]:
    """
    Parsed decision-log records
    """
    path = _log_path(env)
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]


MECHANICAL = {'subagent_type': GP, 'description': 'tidy', 'prompt': 'rename the helper foo across the repo'}


class TestBuildPreOutput:
    """
    Tests for PreToolUse hook output
    """
    def test_rewrite_sets_model_and_preserves_input(self) -> None:
        """
        Test that a rewrite returns updatedInput with only model added, and never a permission decision
        """
        decision = model_router.decide(MECHANICAL, _cfg(mode='enforce'))
        output = model_router.build_pre_output(MECHANICAL, decision)
        specific = output['hookSpecificOutput']
        assert specific['hookEventName'] == 'PreToolUse'
        assert specific['updatedInput'] == {**MECHANICAL, 'model': 'haiku'}
        assert 'permissionDecision' not in specific

    def test_advise_adds_context_only(self) -> None:
        """
        Test that advise mode emits context naming the model and rule, with no input rewrite
        """
        decision = model_router.decide(MECHANICAL, _cfg(mode='advise'))
        specific = model_router.build_pre_output(MECHANICAL, decision)['hookSpecificOutput']
        assert 'updatedInput' not in specific
        assert "model='haiku'" in specific['additionalContext']
        assert 'mechanical-keywords' in specific['additionalContext']

    def test_passthrough_emits_nothing(self) -> None:
        """
        Test that a pass-through decision produces no output
        """
        decision = model_router.decide({'subagent_type': GP, 'prompt': 'summarize'}, _cfg())
        assert model_router.build_pre_output({'prompt': 'summarize'}, decision) is None


class TestRun:
    """
    Tests for the fail-open entry point and the decision log
    """
    def test_enforce_rewrites_and_logs_without_prompt_text(self, env: Env) -> None:
        """
        Test that enforce mode rewrites the model and logs a record that omits the prompt
        """
        _write_layer(env.home, {'mode': 'enforce'})
        output = model_router.run('pre', _event(MECHANICAL, env))
        assert output['hookSpecificOutput']['updatedInput']['model'] == 'haiku'

        [record] = _records(env)
        assert record['action'] == 'rewrite'
        assert record['decided_model'] == 'haiku'
        assert record['rule'] == 'mechanical-keywords'
        assert record['tool_use_id'] == 'toolu_1'
        assert record['prompt_len'] == len(MECHANICAL['prompt'])
        assert 'rename' not in _log_path(env).read_text(encoding='utf-8')

    def test_default_advise_does_not_rewrite(self, env: Env) -> None:
        """
        Test that the shipped default only advises
        """
        output = model_router.run('pre', _event(MECHANICAL, env))
        assert 'updatedInput' not in output['hookSpecificOutput']
        assert _records(env)[0]['action'] == 'advise'

    def test_unrouted_tool_ignored(self, env: Env) -> None:
        """
        Test that other tools are ignored and leave no log
        """
        assert model_router.run('pre', _event({'command': 'ls'}, env, tool_name='Bash')) is None
        assert _records(env) == []

    def test_malformed_stdin_fails_open_and_logs_error(self, env: Env) -> None:
        """
        Test that unparsable stdin yields no output and an error record
        """
        assert model_router.run('pre', '{nope') is None
        assert _records(env)[0]['event'] == 'error'

    def test_invalid_config_fails_open_and_logs_error(self, env: Env) -> None:
        """
        Test that an invalid config layer leaves the call untouched and logs the error
        """
        _write_layer(env.home, {'mode': 'loud'})
        assert model_router.run('pre', _event(MECHANICAL, env)) is None
        assert 'mode' in _records(env)[0]['error']

    def test_off_mode_is_inert(self, env: Env) -> None:
        """
        Test that off mode produces no output and no log
        """
        _write_layer(env.home, {'mode': 'off'})
        assert model_router.run('pre', _event(MECHANICAL, env)) is None
        assert _records(env) == []

    def test_log_can_be_disabled(self, env: Env) -> None:
        """
        Test that log=false suppresses the decision log but not the routing
        """
        _write_layer(env.home, {'mode': 'enforce', 'log': False})
        assert model_router.run('pre', _event(MECHANICAL, env)) is not None
        assert _records(env) == []

    def test_post_logs_event_with_resolved_model(self, env: Env) -> None:
        """
        Test that PostToolUse writes a post record and produces no hook output
        """
        event = _event(MECHANICAL, env, tool_response={'model': 'claude-haiku-5-5'})
        assert model_router.run('post', event) is None

        [record] = _records(env)
        assert record['event'] == 'post'
        assert record['tool_use_id'] == 'toolu_1'
        assert record['resolved_model'] == 'claude-haiku-5-5'

    def test_log_rotates_above_size_cap(self, env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that the log rotates once it exceeds the size cap
        """
        monkeypatch.setattr(model_router, 'LOG_MAX_BYTES', 10)
        model_router.run('pre', _event(MECHANICAL, env))
        model_router.run('pre', _event(MECHANICAL, env))

        rotated = _log_path(env).with_name('decisions.jsonl.1')
        assert rotated.is_file()
        assert len(_records(env)) == 1


class TestRecordedPostPayload:
    """
    Tests against the real PostToolUse payload captured by the feasibility spike
    """
    def test_resolved_model_matches_recorded_payload(self) -> None:
        """
        Test that handle_post extracts the resolved model from the captured payload
        """
        payload = json.loads((FIXTURE_DIR / 'post_agent_payload.json').read_text(encoding='utf-8'))
        expected = payload.pop('_expected_resolved_model')
        assert model_router.handle_post(payload)['resolved_model'] == expected


class TestCli:
    """
    Tests for the script's command-line contract
    """
    @staticmethod
    def _invoke(env: Env, args: list[str], stdin: str) -> subprocess.CompletedProcess[str]:
        """
        Run the script with an isolated HOME and state directory
        """
        child_env = {**os.environ, 'HOME': str(env.home), 'XDG_STATE_HOME': str(env.state)}
        return subprocess.run(
            [sys.executable, str(SCRIPT_PATH), *args],
            input=stdin, capture_output=True, text=True, env=child_env, check=False,
        )

    def test_pre_prints_hook_json(self, env: Env) -> None:
        """
        Test that pre prints the rewrite JSON on stdout and exits 0
        """
        _write_layer(env.home, {'mode': 'enforce'})
        result = self._invoke(env, ['pre'], _event(MECHANICAL, env))
        assert result.returncode == 0
        assert json.loads(result.stdout)['hookSpecificOutput']['updatedInput']['model'] == 'haiku'

    @pytest.mark.parametrize(
        ('args', 'stdin'),
        [
            ([],        '{}'),
            (['bogus'], '{}'),
            (['pre'],   '{nope'),
            (['post'],  ''),
        ],
    )
    def test_bad_invocations_exit_zero_silently(self, env: Env, args: list[str], stdin: str) -> None:
        """
        Test that unknown modes and malformed input never fail the hook
        """
        result = self._invoke(env, args, stdin)
        assert result.returncode == 0
        assert result.stdout == ''
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `scripts/hooks/uv-public.sh run --group test pytest tests/unit/test_model_router.py -v`
Expected: the new classes FAIL (`AttributeError` for `build_pre_output`, `run`, `handle_post`); Tasks 2–3 still PASS.

- [ ] **Step 3: Implement output, log, entry points**

Append to `model-router.py` (ensure the imports `os`, `sys`, `datetime`, `timezone` from Task 2 are present):

```python
# ==============================================================================
# Hook output and records
# ==============================================================================

def now_iso() -> str:
    """
    Current UTC time, ISO-8601, second resolution.
    """
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def build_pre_output(tool_input: dict, decision: Decision) -> dict | None:
    """
    Build the PreToolUse hook output for a decision.

    A rewrite returns ``updatedInput`` (the original input plus ``model``) and deliberately no ``permissionDecision``,
    so the user's normal permission flow still applies. Advise mode returns context only.

    :param tool_input: the original tool input.
    :param decision: the routing decision.
    :return: hook output, or ``None`` to leave the call untouched.
    """
    if decision.action == 'rewrite':
        updated = dict(tool_input)
        updated['model'] = decision.model
        return {
            'hookSpecificOutput': {
                'hookEventName':     'PreToolUse',
                'updatedInput':      updated,
                'additionalContext': f'model-router: routed to {decision.model} ({decision.cls or decision.reason}).',
            }
        }
    if decision.action == 'advise':
        return {
            'hookSpecificOutput': {
                'hookEventName':     'PreToolUse',
                'additionalContext': (
                    f"model-router (advise): this spawn matches {decision.rule or decision.reason} "
                    f"(class {decision.cls or 'n/a'}); consider passing model='{decision.model}'."
                ),
            }
        }
    return None


def handle_pre(payload: dict, cfg: dict) -> tuple[dict | None, dict]:
    """
    Decide on a PreToolUse payload.

    :param payload: the hook's stdin JSON.
    :param cfg: validated config.
    :return: ``(hook_output, log_record)``; the record never contains prompt text.
    """
    tool_input = payload.get('tool_input') or {}
    decision = decide(tool_input, cfg)
    record = {
        'event':           'pre',
        'ts':              now_iso(),
        'session_id':      payload.get('session_id'),
        'tool_use_id':     payload.get('tool_use_id'),
        'subagent_type':   tool_input.get('subagent_type'),
        'requested_model': tool_input.get('model'),
        'decided_model':   decision.model,
        'class':           decision.cls,
        'rule':            decision.rule,
        'mode':            cfg.get('mode'),
        'action':          decision.action,
        'reason':          decision.reason,
        'prompt_len':      len(str(tool_input.get('prompt') or '')),
    }
    return build_pre_output(tool_input, decision), record


def extract_resolved_model(tool_response: object) -> str | None:
    """
    Read the model a subagent actually ran on from a PostToolUse ``tool_response``.

    :param tool_response: the payload's ``tool_response`` value.
    :return: the model string, or ``None`` when the payload does not carry one.
    """
    if isinstance(tool_response, dict):
        model = tool_response.get('model')
        if isinstance(model, str):
            return model
    return None


def handle_post(payload: dict) -> dict:
    """
    Build the log record for a PostToolUse payload.

    :param payload: the hook's stdin JSON.
    :return: the log record.
    """
    tool_input = payload.get('tool_input') or {}
    return {
        'event':          'post',
        'ts':             now_iso(),
        'session_id':     payload.get('session_id'),
        'tool_use_id':    payload.get('tool_use_id'),
        'subagent_type':  tool_input.get('subagent_type'),
        'resolved_model': extract_resolved_model(payload.get('tool_response')),
    }


# ==============================================================================
# Decision log
# ==============================================================================

def state_dir() -> Path:
    """
    Directory holding the decision log: ``${XDG_STATE_HOME:-~/.local/state}/dotfiles/model-router``.
    """
    base = os.environ.get('XDG_STATE_HOME') or str(Path.home() / '.local' / 'state')
    return Path(base) / 'dotfiles' / 'model-router'


def write_log(record: dict) -> None:
    """
    Append one JSON record to the decision log, rotating once it exceeds ``LOG_MAX_BYTES``.

    I/O errors are swallowed on purpose: a logging failure must never fail a hook that fails open.

    :param record: the record to append.
    """
    try:
        directory = state_dir()
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / 'decisions.jsonl'
        if path.is_file() and path.stat().st_size > LOG_MAX_BYTES:
            path.replace(directory / 'decisions.jsonl.1')
        with path.open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(record, sort_keys=True) + '\n')
    except OSError:
        pass


# ==============================================================================
# Entry points
# ==============================================================================

def run(mode: str, raw: str) -> dict | None:
    """
    Process one hook event. Never raises: any failure is logged and the call is left untouched.

    :param mode: ``'pre'`` or ``'post'``.
    :param raw: the hook's raw stdin text.
    :return: hook output to print as JSON, or ``None`` for no output.
    """
    try:
        payload = json.loads(raw or '{}')
        if not isinstance(payload, dict) or payload.get('tool_name') not in ROUTED_TOOLS:
            return None

        cfg = load_config(Path(payload.get('cwd') or os.getcwd()))
        if cfg['mode'] == 'off':
            return None

        if mode == 'pre':
            output, record = handle_pre(payload, cfg)
        else:
            output, record = None, handle_post(payload)
        if cfg.get('log', True):
            write_log(record)
        return output
    except Exception as e:  # noqa: BLE001 - a router must never block a spawn
        write_log({'event': 'error', 'ts': now_iso(), 'mode': mode, 'error': f'{type(e).__name__}: {e!s}'})
        return None


def main() -> None:
    """
    CLI entry: ``model-router.py pre|post`` with the hook payload on stdin. Unknown modes exit 0 silently.
    """
    mode = sys.argv[1] if len(sys.argv) > 1 else ''
    if mode not in ('pre', 'post'):
        sys.exit(0)

    output = run(mode, sys.stdin.read())
    if output is not None:
        print(json.dumps(output))


if __name__ == '__main__':
    main()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `scripts/hooks/uv-public.sh run --group test pytest tests/unit/test_model_router.py -v`
Expected: all PASS except possibly `TestRecordedPostPayload`; see Step 5.

- [ ] **Step 5: Reconcile `extract_resolved_model` with the recorded payload**

`TestRecordedPostPayload` is the arbiter of the real `PostToolUse` shape captured in Task 1.

- If it passes, nothing to do.
- If it fails because the model sits somewhere other than `tool_response['model']`, edit `extract_resolved_model` to
  read that location (for example a nested key), keep the function's `str | None` contract, and rerun until it passes.
  Also adjust the inline payload in `test_post_logs_event_with_resolved_model` to the same shape.
- If the fixture's `_expected_resolved_model` is `null`, the payload carries no model: the test passes as-is, and
  `resolved_model` will always be `null` in the log. Note that limitation in `docs/MODEL_ROUTER.md` (Task 5).

- [ ] **Step 6: Lint, make the script executable, commit**

Run: `scripts/hooks/uv-public.sh run ruff check --fix stow/claude/.claude/hooks/model-router.py tests/unit/test_model_router.py`
Expected: clean. If `RUF100` reports the `# noqa: BLE001` as unused, delete that comment.

```bash
chmod +x stow/claude/.claude/hooks/model-router.py
git add stow/claude/.claude/hooks/model-router.py tests/unit/test_model_router.py
git commit -m "feat(claude): model-router hook entry points and decision log"
```

---

### Task 5: Wiring, docs, and end-to-end verification

**Files:**
- Modify: `$WT/render/claude.json` (`env`, `hooks.PreToolUse`, `hooks.PostToolUse`)
- Create: `$WT/docs/MODEL_ROUTER.md`
- Modify: `$WT/docs/README.md` (Reference table row)

`stow/README.md` needs no change: the `claude` package row already lists hooks, and
`tests/unit/test_docs_consistency.py` only checks package-level rows.

- [ ] **Step 1: Wire the hooks in `render/claude.json`**

Append one entry to the `PostToolUse` array and one to the `PreToolUse` array, after the existing entries:

```json
{
  "matcher": "Agent|Task",
  "hooks": [
    {
      "type": "command",
      "command": "python3 $HOME/.claude/hooks/model-router.py post"
    }
  ]
}
```

```json
{
  "matcher": "Agent|Task",
  "hooks": [
    {
      "type": "command",
      "command": "python3 $HOME/.claude/hooks/model-router.py pre"
    }
  ]
}
```

(First snippet goes in `PostToolUse`, second in `PreToolUse`.)

- [ ] **Step 2: Defer the baseline env var**

The `CLAUDE_CODE_SUBAGENT_MODEL` baseline is added in Step 7 as its own commit, so the user can drop it independently.
It changes the model of every subagent that has neither a frontmatter `model` nor a per-call `model` (for example plugin
reviewers and architects that inherit today). Nothing to do in this step.

- [ ] **Step 3: Run the render and integration tests**

Run: `scripts/hooks/uv-public.sh run --group test pytest tests/unit/test_render.py tests/integration/test_home.py::TestClaude -v`
Expected: PASS. `test_hook_scripts_exist_for_every_hook` now covers `model-router.py`; `test_settings_hooks_use_home_relative_paths`
confirms no absolute home path leaked in.

- [ ] **Step 4: Write the user docs**

Create `$WT/docs/MODEL_ROUTER.md`:

````markdown
[Project Root](../README.md) > [Docs](README.md) > **Model Router**

# Model Router

A Claude Code hook pair that routes subagent spawns (`Agent`/`Task` tool calls) to the cheapest adequate model. Hooks
cannot change the main session's model, so only subagents are routed. Rationale and rejected alternatives:
[design](plans/2026-10/2026-10-29-model-router-design.md).

Source: [`stow/claude/.claude/hooks/model-router.py`](../stow/claude/.claude/hooks/model-router.py), defaults in
[`model-router.default.json`](../stow/claude/.claude/hooks/model-router.default.json), wired through
[`render/claude.json`](../render/claude.json).

## Behavior

For each `Agent`/`Task` call the `pre` hook applies the first matching step:

1. `mode` is `off`, or the prompt or description starts with `opt_out_prefix` (default `~`): do nothing.
2. `subagent_type` is in `agent_overrides`: use that model.
3. `subagent_type` is in `classify_types` (default `general-purpose`, `Explore`): the first rule whose regex matches
   the description plus prompt picks a class, and `classes` maps it to a model.
4. Otherwise do nothing.

A call that already sets `model` is never changed; a disagreement is only logged. `floor` lifts a chosen model to a
minimum tier. In `advise` mode the hook adds context suggesting the model; in `enforce` mode it rewrites `model`. The
hook never denies a call and fails open on any error.

The `post` hook logs the outcome. A `CLAUDE_CODE_SUBAGENT_MODEL=sonnet` baseline in `render/claude.json` separately
moves unpinned subagents to Sonnet.

## Configuration

Layered JSON, later wins: the shipped default, `~/.claude/model-router.json`, `.claude/model-router.json` in the
project. Objects deep-merge, `rules` concatenate with the later layer first, everything else replaces. An invalid layer
disables routing and writes an error record to the log.

| Key               | Meaning                                                                               |
| ----------------- | ------------------------------------------------------------------------------------- |
| `mode`            | `off`, `advise` (default), or `enforce`                                               |
| `opt_out_prefix`  | Prompt or description prefix that skips routing                                       |
| `classes`         | Class name to model alias (`haiku`, `sonnet`, `opus`, `fable`)                        |
| `agent_overrides` | `subagent_type` to model alias; checked before rules                                  |
| `classify_types`  | Agent types whose prompts are matched against `rules`                                 |
| `rules`           | Ordered `{id?, class, any: [regex]}`; case-insensitive; first match wins              |
| `floor`           | Minimum tier (`haiku` < `sonnet` < `opus`); `null` disables                           |
| `log`             | Write the decision log                                                                |

## Decision log

`${XDG_STATE_HOME:-~/.local/state}/dotfiles/model-router/decisions.jsonl`, rotated once to `decisions.jsonl.1` above
about 1 MB. One JSON object per line; `pre` and `post` records share a `tool_use_id`. Prompt text is never logged, only
`prompt_len` and the matched `rule`.

```bash
# Where would enforce have changed the model?
jq -c 'select(.event == "pre" and .action != "passthrough")' ~/.local/state/dotfiles/model-router/decisions.jsonl
# Calls where the caller's model disagreed with the router
jq -c 'select(.reason == "preset-disagree")' ~/.local/state/dotfiles/model-router/decisions.jsonl
```

## Rollout

The hook ships in `advise`. After about a week of logs, review the `advise` and `preset-disagree` records; when the
suggestions look right, set `{"mode": "enforce"}` in `~/.claude/model-router.json`.
````

If Task 4 Step 5 found that `PostToolUse` carries no model, add a sentence under "Decision log": "`resolved_model` is
always `null`: the `PostToolUse` payload for `Agent` does not report the model that ran."

- [ ] **Step 5: Index the doc**

In `$WT/docs/README.md`, add a row to the Reference table:

```markdown
| [MODEL_ROUTER.md](MODEL_ROUTER.md)         | Subagent model-router hook: behavior, config, decision log, rollout. |
```

- [ ] **Step 6: Format and validate**

Run: `prek run --files render/claude.json docs/MODEL_ROUTER.md docs/README.md stow/claude/.claude/hooks/model-router.default.json`
Expected: PASS (mdformat realigns the tables; the JSON formatter may reflow arrays; rerun until clean).

Then commit:

```bash
git add render/claude.json docs/MODEL_ROUTER.md docs/README.md stow/claude/.claude/hooks/model-router.default.json
git commit -m "feat(claude): wire model-router hooks and document them"
```

- [ ] **Step 7: Add the Sonnet baseline as a separate commit**

In the `env` object of `render/claude.json`, insert between `CLAUDE_CODE_ENABLE_TELEMETRY` and `COLUMNS` (keys are
alphabetical):

```json
"CLAUDE_CODE_SUBAGENT_MODEL": "sonnet",
```

Run: `scripts/hooks/uv-public.sh run --group test pytest tests/unit/test_render.py tests/integration/test_home.py::TestClaude -q`
Expected: PASS.

```bash
git add render/claude.json
git commit -m "feat(claude): default unpinned subagents to Sonnet"
```

- [ ] **Step 8: End-to-end verification against the real hook, without touching `~/.claude`**

Do **not** run `stow.sh` or `render` from the worktree: that would repoint the live `~/.claude` symlinks into a
directory that disappears when the worktree is removed. Test the worktree script directly with `--settings`.

```bash
E2E="$TMPDIR/router-e2e"; mkdir -p "$E2E/proj/.claude" "$E2E/state"; rm -f "$E2E/state/dotfiles/model-router/decisions.jsonl"
cat > "$E2E/settings.json" <<EOF
{
  "hooks": {
    "PreToolUse":  [{"matcher": "Agent|Task", "hooks": [{"type": "command", "command": "XDG_STATE_HOME=$E2E/state python3 $PWD/stow/claude/.claude/hooks/model-router.py pre"}]}],
    "PostToolUse": [{"matcher": "Agent|Task", "hooks": [{"type": "command", "command": "XDG_STATE_HOME=$E2E/state python3 $PWD/stow/claude/.claude/hooks/model-router.py post"}]}]
  }
}
EOF
```

(a) Advise mode (project config absent, so the shipped `advise` default applies). Run from the scratch project so the
payload `cwd` points at it:

```bash
cd "$E2E/proj" && claude -p "Use the Agent tool exactly once with subagent_type general-purpose and this prompt: 'rename is the keyword here; reply with only your exact model ID from your system prompt.' Then repeat the answer verbatim." --settings "$E2E/settings.json" --output-format text
```
Expected: the subagent reports the **main** model (no rewrite). `decisions.jsonl` has a `pre` record with
`"action": "advise"` and a matching `post` record (same `tool_use_id`).

(b) Enforce mode:

```bash
echo '{"mode": "enforce"}' > "$E2E/proj/.claude/model-router.json"
cd "$E2E/proj" && claude -p "Use the Agent tool exactly once with subagent_type general-purpose and this prompt: 'rename is the keyword here; reply with only your exact model ID from your system prompt.' Then repeat the answer verbatim." --settings "$E2E/settings.json" --output-format text
```
Expected: the subagent reports a **Haiku** model ID; a new `pre` record shows `"action": "rewrite"`,
`"decided_model": "haiku"`.

(c) Pinned agent is left alone: run (b) again with `subagent_type file-searcher`. Expected: reports a Haiku ID
from the agent's own frontmatter; the `pre` record has `"reason": "unmatched"` and `"action": "passthrough"`.

Read `$E2E/state/dotfiles/model-router/decisions.jsonl` with the Read tool to check each record. If (b) does not produce
Haiku, return to Task 1's findings: something differs between the spike hook and this one.

- [ ] **Step 9: Full verification, then stop**

Run: `scripts/hooks/uv-public.sh run --group test pytest tests/unit tests/integration/test_home.py::TestClaude -q`
Expected: all PASS.

Run: `prek run --all-files`
Expected: PASS (including the leak guard; the new files must contain nothing employer-specific).

Dispatch `anthropic-pr-review-toolkit:code-reviewer` on `git diff main...HEAD` and fix any real findings.

Report to the user: spike results, test and E2E output, the separate Sonnet-baseline commit, and that nothing has been
pushed. Open a PR or merge only if the user asks.
