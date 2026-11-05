"""
Guardrail tests that keep the CI deploy workflow on the same code path as `run.py nas-deploy`
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
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

    @pytest.mark.parametrize('job', ['detect-changes', 'deploy-push', 'deploy-manual'])
    def test_no_script_interpolates_an_expression(self, job: str) -> None:
        """
        Test that no run step interpolates a ${{ }} expression, so secrets and event data travel through env
        """
        for step in _steps(job):
            assert '${{' not in step.get('run', ''), step.get('name')

    @pytest.mark.parametrize('job', ['deploy-push', 'deploy-manual'])
    def test_ssh_key_step_takes_the_secrets_through_env(self, job: str) -> None:
        """
        Test that the key step reads the private key and host from env variables
        """
        steps = [step for step in _steps(job) if step.get('name') == 'Set up SSH key']
        assert len(steps) == 1

        step = steps[0]
        assert set(step['env']) == {'NAS_SSH_PRIVATE_KEY', 'NAS_HOST'}
        assert '"$NAS_SSH_PRIVATE_KEY"' in step['run']
        assert '"$NAS_HOST"'            in step['run']

    @pytest.mark.parametrize('job', ['deploy-push', 'deploy-manual'])
    def test_ssh_key_step_writes_a_private_key_file(self, job: str, tmp_path: Path) -> None:
        """
        Test that running the key step's script writes the key verbatim to a 0600 file in a 0700 directory
        """
        step = next(step for step in _steps(job) if step.get('name') == 'Set up SSH key')

        bin_dir = tmp_path / 'bin'
        bin_dir.mkdir()

        keyscan = bin_dir / 'ssh-keyscan'
        keyscan.write_text('#!/bin/sh\nexit 0\n', encoding='utf-8')
        keyscan.chmod(0o755)

        home = tmp_path / 'home'
        home.mkdir()

        key = '-----BEGIN KEY-----\nline-two\n-----END KEY-----'
        subprocess.run(
            ['/bin/bash', '-e', '-c', step['run']],
            check=True,
            capture_output=True,
            env={
                'PATH': f'{bin_dir}:{os.environ["PATH"]}',
                'HOME': str(home),
                'NAS_SSH_PRIVATE_KEY': key,
                'NAS_HOST': 'nas.example',
            },
        )

        private = home / '.ssh' / 'id_nas'
        assert private.read_text(encoding='utf-8') == key + '\n'
        assert private.stat().st_mode & 0o777 == 0o600
        assert (home / '.ssh').stat().st_mode & 0o777 == 0o700
