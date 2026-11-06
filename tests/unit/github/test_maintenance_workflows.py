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
