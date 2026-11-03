"""
Unit tests for scripts/nas/deploy-services.sh (stubbed rsync and ssh: no NAS or network needed)
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT    = Path(__file__).resolve().parents[2]
SCRIPT       = REPO_ROOT / 'scripts' / 'nas' / 'deploy-services.sh'
SERVICES_DIR = REPO_ROOT / 'services'
BASH         = '/bin/bash'  # macOS ships bash 3.2 here, the oldest interpreter the script must run under

pytestmark = pytest.mark.skipif(not Path(BASH).exists(), reason='/bin/bash not available')

# Each stub appends "<name> <args>" to $STUB_LOG, which the tests read back
STUB = '#!/bin/sh\nprintf "%s %s\\n" "$(basename "$0")" "$*" >> "$STUB_LOG"\n'


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    """
    Stubbed rsync and ssh first on PATH, plus the required NAS variables
    """
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    for name in ('rsync', 'ssh'):
        stub = bin_dir / name
        stub.write_text(STUB, encoding='utf-8')
        stub.chmod(0o755)

    return {
        **{key: value for key, value in os.environ.items() if not key.startswith('NAS_')},
        'PATH':     f'{bin_dir}:{os.environ["PATH"]}',
        'STUB_LOG': str(tmp_path / 'calls.log'),
        'NAS_HOST': 'nas.example',
        'NAS_USER': 'tester',
    }


def _run(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    """
    Run the script under /bin/bash with the given arguments
    """
    return subprocess.run([BASH, str(SCRIPT), *args], capture_output=True, text=True, check=False, env=env)


def _calls(env: dict[str, str]) -> list[str]:
    """
    Return the stub invocations recorded so far
    """
    log = Path(env['STUB_LOG'])
    return log.read_text(encoding='utf-8').splitlines() if log.exists() else []


class TestDeployOneService:
    """
    Tests for deploying a single service
    """
    def test_syncs_base_compose_and_service_then_deploys(self, env: dict[str, str]) -> None:
        """
        Test that one service rsyncs compose.base.yml and its directory, then runs deploy.sh over ssh
        """
        result = _run(env, 'glance')

        assert result.returncode == 0, result.stderr
        calls = _calls(env)
        assert len(calls) == 3
        assert calls[0].endswith(f'{SERVICES_DIR}/compose.base.yml tester@nas.example:~/docker/compose.base.yml')
        assert calls[1].endswith(f'{SERVICES_DIR}/glance/ tester@nas.example:~/docker/glance/')
        assert calls[2] == 'ssh tester@nas.example ~/docker/deploy.sh glance'

    def test_rsync_skips_templates_and_env_files(self, env: dict[str, str]) -> None:
        """
        Test that rsync never ships *.j2 templates or .env files, and never deletes
        """
        _run(env, 'glance')

        calls = _calls(env)
        assert len(calls) == 3
        for call in calls[:2]:
            assert '--exclude=*.j2' in call
            assert '--exclude=.env'  in call
            assert '--delete'    not in call

    @pytest.mark.parametrize('service', ['glance', 'all'])
    def test_rsync_is_idempotent_and_skips_laptop_junk(self, env: dict[str, str], service: str) -> None:
        """
        Test that rsync ignores directory mtimes, backups, and .DS_Store files
        """
        _run(env, service)

        rsync_calls = [call for call in _calls(env) if call.startswith('rsync ')]
        assert rsync_calls
        for call in rsync_calls:
            for flag in ('--omit-dir-times', '--exclude=.backups/', '--exclude=.DS_Store'):
                assert flag in call

    def test_key_adds_identity_and_host_key_policy(self, env: dict[str, str]) -> None:
        """
        Test that NAS_SSH_KEY reaches both the rsync transport and the ssh call
        """
        env['NAS_SSH_KEY'] = '/keys/id_nas'
        _run(env, 'glance')

        option = '-i /keys/id_nas -o StrictHostKeyChecking=accept-new'
        calls  = _calls(env)
        assert f'-e ssh {option}' in calls[0]
        assert calls[2] == f'ssh {option} tester@nas.example ~/docker/deploy.sh glance'


class TestDeployAll:
    """
    Tests for deploying every service
    """
    def test_syncs_whole_tree_then_deploys_all(self, env: dict[str, str]) -> None:
        """
        Test that 'all' rsyncs the whole services/ directory and runs deploy.sh all
        """
        result = _run(env, 'all')

        assert result.returncode == 0, result.stderr
        calls = _calls(env)
        assert len(calls) == 2
        assert calls[0].endswith(f'{SERVICES_DIR}/ tester@nas.example:~/docker/')
        assert calls[1] == 'ssh tester@nas.example ~/docker/deploy.sh all'


class TestDryRun:
    """
    Tests for --dry-run
    """
    def test_previews_rsync_and_never_runs_ssh(self, env: dict[str, str]) -> None:
        """
        Test that --dry-run adds rsync -n, skips ssh, and prints the command it would have run
        """
        result = _run(env, '--dry-run', 'glance')

        assert result.returncode == 0, result.stderr
        calls = _calls(env)
        assert len(calls) == 2
        assert all(call.startswith('rsync ') and ' -n ' in call for call in calls)
        assert 'dry-run: would run: ssh tester@nas.example ~/docker/deploy.sh glance' in result.stdout


class TestValidation:
    """
    Tests for argument and environment validation
    """
    @pytest.mark.parametrize(
        ('args', 'message'),
        [
            (('nonexistent',),   'no services/nonexistent/compose.yml'),
            (('homeassistant',), 'no services/homeassistant/compose.yml'),
            (('../etc',),        'invalid service name'),
            (('Glance',),        'invalid service name'),
            ((),                 'usage'),
            (('glance', 'plex'), 'usage'),
        ],
    )
    def test_rejects_bad_arguments_before_any_network_call(
        self, env: dict[str, str], args: tuple[str, ...], message: str,
    ) -> None:
        """
        Test that unknown, disabled, malformed, or missing service arguments exit 2 without calling rsync or ssh
        """
        result = _run(env, *args)

        assert result.returncode == 2
        assert message in result.stderr
        assert _calls(env) == []

    @pytest.mark.parametrize('missing', ['NAS_HOST', 'NAS_USER'])
    def test_requires_host_and_user(self, env: dict[str, str], missing: str) -> None:
        """
        Test that a missing NAS_HOST or NAS_USER exits 2 and names the variable
        """
        del env[missing]
        result = _run(env, 'glance')

        assert result.returncode == 2
        assert missing in result.stderr
        assert _calls(env) == []
