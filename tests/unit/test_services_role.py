"""
Structural tests for the services role and its place in the NAS playbook (no NAS needed)
"""
from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PLAYBOOK  = REPO_ROOT / 'playbooks' / 'nas_bootstrap.yml'
ROLES     = REPO_ROOT / 'roles'

TaskDict = dict[str, Any]  # Any: heterogeneous, yaml-loaded task structure


def _flatten(tasks: list[TaskDict]) -> list[TaskDict]:
    """
    Flatten block/rescue nesting into one task list (blocks included)
    """
    flat: list[TaskDict] = []
    for task in tasks:
        flat.append(task)
        for key in ('block', 'rescue', 'always'):
            flat.extend(_flatten(task.get(key, [])))
    return flat


def _tasks(role: str) -> list[TaskDict]:
    """
    Load every task in a role's tasks/main.yml
    """
    return _flatten(yaml.safe_load((ROLES / role / 'tasks' / 'main.yml').read_text(encoding='utf-8')))


def _task(role: str, name: str) -> TaskDict:
    """
    Load the task with the given name from a role
    """
    matches = [task for task in _tasks(role) if task.get('name') == name]
    assert len(matches) == 1, f'expected exactly one task named {name!r} in role {role}'
    return matches[0]


def _defaults(role: str) -> dict[str, Any]:  # Any: heterogeneous, yaml-loaded variables
    """
    Load a role's defaults/main.yml
    """
    data = yaml.safe_load((ROLES / role / 'defaults' / 'main.yml').read_text(encoding='utf-8'))
    assert isinstance(data, dict)
    return data


class TestPlaybookWiring:
    """
    Tests for how the playbook includes the services role
    """
    @pytest.fixture
    def include(self) -> TaskDict:
        """
        The last task of the NAS play
        """
        return yaml.safe_load(PLAYBOOK.read_text(encoding='utf-8'))[0]['tasks'][-1]

    def test_services_role_runs_last(self, include: TaskDict) -> None:
        """
        Test that the services role is the final include, after haos
        """
        assert include['ansible.builtin.include_role']['name'] == 'roles/services'

    def test_include_is_reachable_by_services_secrets_and_configfile_tags(self, include: TaskDict) -> None:
        """
        Test that the include carries the services, secrets, and configfile tags
        """
        assert include['tags'] == ['services', 'secrets', 'configfile']

    def test_only_the_services_tag_is_applied_inside_the_role(self, include: TaskDict) -> None:
        """
        Test that apply tags the role's tasks 'services' only, so '--tags secrets' selects just the secret tasks
        """
        assert include['ansible.builtin.include_role']['apply']['tags'] == 'services'


class TestServicesRole:
    """
    Tests for roles/services
    """
    def test_sync_pushes_the_tree_without_templates_env_files_or_deletes(self) -> None:
        """
        Test that the sync uses ansible.posix.synchronize with the same exclusions as deploy-services.sh
        """
        args = _task('services', 'Sync compose files to the NAS')['ansible.posix.synchronize']

        assert '--exclude=*.j2'  in args['rsync_opts']
        assert '--exclude=.env'  in args['rsync_opts']
        assert not args.get('delete')
        assert args['dest'].startswith('{{ services_target_dir }}')

    def test_sync_is_idempotent_and_skips_laptop_junk(self) -> None:
        """
        Test that the sync ignores directory mtimes, backups, and .DS_Store files
        """
        opts = _task('services', 'Sync compose files to the NAS')['ansible.posix.synchronize']['rsync_opts']
        for opt in ('--omit-dir-times', '--exclude=.backups/', '--exclude=.DS_Store'):
            assert opt in opts

    def test_role_and_script_share_the_same_rsync_filters(self) -> None:
        """
        Test that the role's rsync_opts and deploy-services.sh's rsync_flags carry identical exclude/omit tokens
        """
        script = (REPO_ROOT / 'scripts' / 'nas' / 'deploy-services.sh').read_text(encoding='utf-8')
        line   = next(line for line in script.splitlines() if line.startswith('rsync_flags=('))

        script_tokens = {
            token for token in shlex.split(line.removeprefix('rsync_flags=(').removesuffix(')'))
            if token.startswith('--exclude=') or token == '--omit-dir-times'
        }

        opts        = _task('services', 'Sync compose files to the NAS')['ansible.posix.synchronize']['rsync_opts']
        role_tokens = {opt for opt in opts if opt.startswith('--exclude=') or opt == '--omit-dir-times'}

        assert script_tokens
        assert script_tokens == role_tokens

    def test_rsync_is_installed_first_on_the_nas(self) -> None:
        """
        Test that the role's first task installs rsync as root, because synchronize runs rsync on both ends
        """
        first = yaml.safe_load((ROLES / 'services' / 'tasks' / 'main.yml').read_text(encoding='utf-8'))[0]

        assert first['name']   == 'Install rsync'
        assert first['become'] is True
        assert first['ansible.builtin.apt']['name']  == 'rsync'
        assert first['ansible.builtin.apt']['state'] == 'present'
        assert 'secrets' not in first.get('tags', [])

    def test_only_the_secret_tasks_carry_the_secrets_tag(self) -> None:
        """
        Test that the secrets tag reaches exactly the discovery, directory, and render tasks
        """
        tagged = {task['name'] for task in _tasks('services') if 'secrets' in task.get('tags', [])}
        assert tagged == {
            'Find per-service secret templates',
            'Create per-service secret directories',
            'Render per-service secret files',
        }

    def test_secrets_render_to_private_env_files_from_the_discovered_templates(self) -> None:
        """
        Test that each discovered env.j2 renders to a 0600 file, without echoing a diff
        """
        task = _task('services', 'Render per-service secret files')

        assert task['ansible.builtin.template']['mode'] == '0600'
        assert task['ansible.builtin.template']['dest'].endswith('/.env')
        assert task['diff'] is False
        assert 'services_secret_found' in task['loop']

    def test_discovery_does_not_rely_on_a_wildcard_directory_glob(self) -> None:
        """
        Test that templates are found with the find module, since lookup('fileglob') cannot glob a directory part

        A fileglob over services/*/env.j2 matched nothing on the first live check, so no secret was ever rendered
        """
        text = (ROLES / 'services' / 'tasks' / 'main.yml').read_text(encoding='utf-8')
        task = _task('services', 'Find per-service secret templates')

        assert "lookup('ansible.builtin.fileglob'" not in text
        assert task['ansible.builtin.find']['patterns'] == 'env.j2'
        assert task['delegate_to'] == 'localhost'
        assert task['connection']  == 'local'
        assert task['check_mode']  is False

    def test_deploy_reports_changes_only_when_containers_change(self) -> None:
        """
        Test that deploy.sh all is skipped in check mode and counts compose changes, not 'Running'
        """
        task = _task('services', 'Deploy all services')
        assert task['when'] == 'not ansible_check_mode'

        for verb in ('Started', 'Recreated', 'Created', 'Pulled'):
            assert verb in task['changed_when']
        assert 'Running' not in task['changed_when']

    def test_deploy_runs_with_a_fresh_group_list(self) -> None:
        """
        Test that deploy.sh runs through become as the same user, so a docker group added this run applies
        """
        task = _task('services', 'Deploy all services')
        assert task['become']      is True
        assert task['become_user'] == "{{ ansible_facts['user_id'] }}"

    def test_target_dir_matches_the_docker_role(self) -> None:
        """
        Test that both roles agree where ~/docker lives
        """
        assert _defaults('services')['services_target_dir'] == _defaults('docker')['docker_dir']


class TestDockerRole:
    """
    Tests for the docker role after the fresh-install and lint fixes
    """
    def test_does_not_deploy_services(self) -> None:
        """
        Test that deploying services belongs to the services role, so the docker role no longer runs deploy.sh all
        """
        text = (ROLES / 'docker' / 'tasks' / 'main.yml').read_text(encoding='utf-8')

        assert 'deploy.sh all' not in text
        assert any(task.get('name') == 'Copy deploy script' for task in _tasks('docker'))

    def test_gpg_key_is_fetched_as_root_with_an_explicit_mode(self) -> None:
        """
        Test that the Docker apt key download can write /usr/share/keyrings on a fresh host
        """
        task = _task('docker', 'Add Docker GPG signing key')

        assert task['become'] is True
        assert task['ansible.builtin.get_url']['mode'] == '0644'

    def test_architecture_probe_is_read_only(self) -> None:
        """
        Test that the dpkg architecture lookup never reports changed and also runs in check mode
        """
        task = _task('docker', 'Print debian architecture')

        assert 'ansible.builtin.command' in task
        assert task['changed_when'] is False
        assert task['check_mode']   is False

    def test_ssh_user_joins_the_docker_group(self) -> None:
        """
        Test that the SSH user can run docker without sudo after a fresh install
        """
        args = _task('docker', 'Allow the SSH user to run docker without sudo')['ansible.builtin.user']

        assert args['name']   == "{{ ansible_facts['user_id'] }}"
        assert args['groups'] == 'docker'
        assert args['append'] is True

    def test_env_render_never_prints_a_diff(self) -> None:
        """
        Test that the docker .env render suppresses diffs, so a --check --diff run cannot echo a secret
        """
        task = _task('docker', 'Render docker .env file')
        assert task['diff'] is False
        assert task['ansible.builtin.template']['mode'] == '0600'

    def test_autoplex_variables_carry_the_role_prefix(self) -> None:
        """
        Test that every default in the docker role starts with docker_
        """
        assert all(name.startswith('docker_') for name in _defaults('docker'))

    def test_no_docker_lint_exceptions_remain(self) -> None:
        """
        Test that .ansible-lint-ignore holds no entry for the docker role
        """
        ignore = (REPO_ROOT / '.ansible-lint-ignore').read_text(encoding='utf-8')
        assert 'roles/docker/' not in ignore


ANSIBLE_PLAYBOOK = Path(sys.executable).parent / 'ansible-playbook'

# The production include, run against localhost with only the secrets tag selected
SECRETS_PLAYBOOK = """\
- hosts: all
  gather_facts: false
  connection: local
  tasks:
    - name: Deploy the container services
      ansible.builtin.include_role:
        name: services
        apply:
          tags: services
      tags: [services, secrets, configfile]
"""


@pytest.mark.skipif(not ANSIBLE_PLAYBOOK.exists(), reason='ansible-playbook not in this environment')
class TestSecretsRender:
    """
    End-to-end test of the secrets tasks: discovery, directory creation, and rendering, against a temp directory
    """
    def test_renders_every_env_template_privately_and_silently(self, tmp_path: Path) -> None:
        """
        Test that --tags secrets renders services/pihole/env.j2 to a 0600 .env without echoing the value

        Guards the first-live-run failure where discovery found no templates and nothing was rendered
        """
        playbook = tmp_path / 'secrets.yml'
        playbook.write_text(SECRETS_PLAYBOOK, encoding='utf-8')

        vault = tmp_path / 'vault-pass'
        vault.write_text('unused\n', encoding='utf-8')

        target = tmp_path / 'docker'
        result = subprocess.run(
            [
                str(ANSIBLE_PLAYBOOK), str(playbook), '-i', 'localhost,', '--tags', 'secrets', '--diff',
                '-e', f'services_source_dir={REPO_ROOT / "services"}',
                '-e', f'services_target_dir={target}',
                '-e', 'pihole_web_password=hunter2-test-value',
            ],
            capture_output=True,
            text=True,
            check=False,
            cwd=REPO_ROOT,
            env={**os.environ, 'ANSIBLE_VAULT_PASSWORD_FILE': str(vault), 'ANSIBLE_NOCOLOR': '1'},
            timeout=300,
        )

        output = result.stdout + result.stderr
        assert result.returncode == 0, output

        env_file = target / 'pihole' / '.env'
        assert env_file.read_text(encoding='utf-8').strip() == 'FTLCONF_webserver_api_password=hunter2-test-value'
        assert env_file.stat().st_mode & 0o777 == 0o600
        assert 'hunter2-test-value' not in output
        assert 'Sync compose files' not in output
