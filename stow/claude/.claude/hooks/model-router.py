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
import re
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
    name = rule.get('class')
    if not isinstance(name, str) or name not in classes:
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
