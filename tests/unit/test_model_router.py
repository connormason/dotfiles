"""
Unit tests for stow/claude/.claude/hooks/model-router.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
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
            ('rules',           [{'class': ['hard'], 'any': ['x']}]),
            ('rules',           [{'class': {}, 'any': ['x']}]),
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
        event = _event(MECHANICAL, env, tool_response={'resolvedModel': 'claude-haiku-5-5'})
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
