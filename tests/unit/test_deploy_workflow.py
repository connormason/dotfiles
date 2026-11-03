"""
Guardrail tests that keep the CI deploy workflow on the same code path as `run.py nas-deploy`
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW  = REPO_ROOT / '.github' / 'workflows' / 'deploy.yml'
SCRIPT    = 'scripts/nas/deploy-services.sh'


def _steps(job: str) -> list[dict[str, Any]]:  # Any: heterogeneous, yaml-loaded workflow structure
    """
    Return the steps of a job in the deploy workflow
    """
    data = yaml.safe_load(WORKFLOW.read_text(encoding='utf-8'))
    return data['jobs'][job]['steps']


class TestDeployWorkflow:
    """
    Tests for .github/workflows/deploy.yml
    """
    @pytest.mark.parametrize('job', ['deploy-push', 'deploy-manual'])
    def test_deploys_through_the_shared_script(self, job: str) -> None:
        """
        Test that each deploy job calls the shared script and holds no inline rsync
        """
        runs = [step['run'] for step in _steps(job) if 'run' in step]

        assert any(SCRIPT in run for run in runs)
        assert not any('rsync' in run for run in runs)

    @pytest.mark.parametrize('job', ['deploy-push', 'deploy-manual'])
    def test_inputs_reach_the_script_through_env(self, job: str) -> None:
        """
        Test that host, user, and service pass via env, never interpolated into the shell command
        """
        steps = [step for step in _steps(job) if SCRIPT in step.get('run', '')]

        assert len(steps) == 1
        step = steps[0]
        assert '${{' not in step['run']
        assert set(step['env']) == {'NAS_HOST', 'NAS_USER', 'SERVICE'}
        assert 'NAS_SSH_KEY="$HOME/.ssh/id_nas"' in step['run']
