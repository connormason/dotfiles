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
