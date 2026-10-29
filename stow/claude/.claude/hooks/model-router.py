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
from dataclasses import dataclass
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
RULE_FLAGS = re.IGNORECASE | re.DOTALL


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
    name = rule.get('class')
    if not isinstance(name, str) or name not in classes:
        raise ConfigError(f'{where}.class: {rule.get("class")!r} is not a defined class')
    patterns = rule.get('any')
    if not isinstance(patterns, list) or not patterns or not all(isinstance(p, str) for p in patterns):
        raise ConfigError(f'{where}.any: must be a non-empty list of strings')
    for pattern in patterns:
        try:
            re.compile(pattern, RULE_FLAGS)
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
            if any(re.search(pattern, text, RULE_FLAGS) for pattern in rule['any']):
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
        model = tool_response.get('resolvedModel')
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

        cfg = load_config(Path(payload.get('cwd') or Path.cwd()))
        if cfg['mode'] == 'off':
            return None

        if mode == 'pre':
            output, record = handle_pre(payload, cfg)
        else:
            output, record = None, handle_post(payload)
        if cfg.get('log', True):
            write_log(record)
        return output
    except Exception as e:
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
