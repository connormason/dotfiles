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

ANSIBLE_PLAYBOOK = Path(sys.executable).parent / 'ansible-playbook'
SERVICES_DIR     = REPO_ROOT / 'services'

needs_ansible = pytest.mark.skipif(not ANSIBLE_PLAYBOOK.exists(), reason='ansible-playbook not in this environment')

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


def _tasks(role: str, file: str = 'main.yml') -> list[TaskDict]:
    """
    Load every task in one of a role's task files (tasks/main.yml unless another file is named)
    """
    return _flatten(yaml.safe_load((ROLES / role / 'tasks' / file).read_text(encoding='utf-8')))


def _task(role: str, name: str, file: str = 'main.yml') -> TaskDict:
    """
    Load the task with the given name from a role's task file
    """
    matches = [task for task in _tasks(role, file) if task.get('name') == name]
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

    def test_include_is_reachable_by_the_services_and_secrets_tags(self, include: TaskDict) -> None:
        """
        Test that the include carries exactly the services and secrets tags (configfile selected nothing inside it)
        """
        assert include['tags'] == ['services', 'secrets']

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

    def test_secret_tasks_skip_services_without_a_compose_file(self) -> None:
        """
        Test that the directory and render tasks are guarded by the presence of the service's compose.yml
        """
        for name in ('Create per-service secret directories', 'Render per-service secret files'):
            assert "'/compose.yml') is file" in _task('services', name)['when'], name

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

    def test_directory_loop_leaves_the_pihole_path_to_the_guarded_task(self) -> None:
        """
        Test that the enforced-mode directory loop no longer includes the PiHole config directory
        """
        loop = _task('docker', 'Create docker directory structure')['loop']
        assert not any('pihole' in entry for entry in loop), loop

    @needs_ansible
    def test_pihole_config_dir_is_created_once_and_never_re_enforced(self, tmp_path: Path) -> None:
        """
        Test that a container re-chmodding the bind mount does not make later runs report changed or reset the mode
        """
        play = _task_play(
            'docker', 'Check for the PiHole config directory', 'Create the PiHole config directory',
        )
        docker_dir = tmp_path / 'docker'
        pihole     = docker_dir / 'pihole-data' / 'etc-pihole'

        code, output = _run_play(tmp_path, play, '-e', f'docker_dir={docker_dir}')
        assert code == 0, output
        assert pihole.is_dir()
        assert pihole.stat().st_mode & 0o777 == 0o755
        assert 'changed=1' in output, output

        pihole.chmod(0o775)  # what a running container may do to its bind mount
        code, output = _run_play(tmp_path, play, '-e', f'docker_dir={docker_dir}')
        assert code == 0, output
        assert 'changed=0' in output, output
        assert pihole.stat().st_mode & 0o777 == 0o775


def _include_play(role: str) -> str:
    """
    Build a one-task localhost play from the production include of a role

    The include keeps its production tags and apply block; only the role name is made bare so Ansible finds it through
    ansible.cfg's roles_path when run from the repository root. Using the production include (not a copy) means a tag
    change in the playbook is exercised by these tests.

    :param role: role directory name, e.g. ``services``
    :return: playbook YAML text
    """
    key     = 'ansible.builtin.include_role'
    play    = yaml.safe_load(PLAYBOOK.read_text(encoding='utf-8'))[0]
    include = next(task for task in play['tasks'] if task.get(key, {}).get('name') == f'roles/{role}')
    include = {**include, key: {**include[key], 'name': role}}
    return yaml.safe_dump([{'hosts': 'all', 'gather_facts': False, 'connection': 'local', 'tasks': [include]}])


def _play_text(tasks: list[TaskDict]) -> str:
    """
    Wrap tasks in a one-play localhost playbook

    :param tasks: task dicts, in the order they should run
    :return: playbook YAML text
    """
    return yaml.safe_dump([{'hosts': 'all', 'gather_facts': False, 'connection': 'local', 'tasks': tasks}])


def _task_play(role: str, *names: str) -> str:
    """
    Build a one-play localhost playbook from the named tasks of a role, exactly as the role defines them

    :param role: role directory name
    :param names: task names, in the order they should run
    :return: playbook YAML text
    """
    return _play_text([_task(role, name) for name in names])


def _run_play(tmp_path: Path, play: str, *args: str, env: dict[str, str] | None = None) -> tuple[int, str]:
    """
    Run a one-play playbook against localhost with a throwaway vault password file

    Skips the calling test when the ansible.posix collection is not installed.

    :param tmp_path: scratch directory for the playbook and vault file
    :param play: playbook YAML text
    :param args: extra ansible-playbook arguments
    :param env: extra environment variables, merged over the inherited environment
    :return: tuple of (return code, combined stdout and stderr)
    """
    playbook = tmp_path / 'play.yml'
    playbook.write_text(play, encoding='utf-8')

    vault = tmp_path / 'vault-pass'
    vault.write_text('unused\n', encoding='utf-8')

    result = subprocess.run(
        [str(ANSIBLE_PLAYBOOK), str(playbook), '-i', 'localhost,', *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
        env={**os.environ, 'ANSIBLE_VAULT_PASSWORD_FILE': str(vault), 'ANSIBLE_NOCOLOR': '1', **(env or {})},
        timeout=300,
    )
    output = result.stdout + result.stderr
    if "couldn't resolve module/action 'ansible.posix" in output:
        pytest.skip('ansible.posix is not installed: ansible-galaxy collection install -r roles/requirements.yml')
    return result.returncode, output


def _render_secrets(tmp_path: Path, source: Path, *extra_vars: str) -> tuple[int, str, Path]:
    """
    Run the production services include with only the secrets tag selected

    :param tmp_path: scratch directory; the rendered tree lands in ``tmp_path / 'docker'``
    :param source: directory standing in for the repository's services/ tree
    :param extra_vars: ``name=value`` extra variables (vault values)
    :return: tuple of (return code, combined output, target directory)
    """
    target = tmp_path / 'docker'
    args   = [
        '--tags', 'secrets', '--diff',
        '-e', f'services_source_dir={source}',
        '-e', f'services_target_dir={target}',
    ]
    for var in extra_vars:
        args += ['-e', var]
    code, output = _run_play(tmp_path, _include_play('services'), *args)
    return code, output, target


@needs_ansible
class TestTagSelection:
    """
    Real-run tests of what '--tags configfile' selects (a tag on include_role selects only the include itself)
    """
    def test_configfile_selects_nothing_in_the_services_play(self, tmp_path: Path) -> None:
        """
        Test that --tags configfile runs no task of the services role and does not even select its include
        """
        target = tmp_path / 'docker'
        code, output = _run_play(
            tmp_path, _include_play('services'), '--tags', 'configfile',
            '-e', f'services_source_dir={SERVICES_DIR}', '-e', f'services_target_dir={target}',
        )

        assert code == 0, output
        for task in ('Install rsync', 'Sync compose files', 'Render per-service secret files', 'Deploy all services'):
            assert task not in output, output
        assert not target.exists()
        assert 'Deploy the container services' not in output, output

    def test_configfile_renders_only_the_env_file_and_deploy_script_in_the_docker_role(self, tmp_path: Path) -> None:
        """
        Test that --tags configfile reaches exactly the two docker tasks that carry the tag
        """
        docker_dir = tmp_path / 'docker'
        docker_dir.mkdir()
        code, output = _run_play(
            tmp_path, _include_play('docker'), '--tags', 'configfile',
            '-e', f'docker_dir={docker_dir}', '-e', 'tailscale_tailnet_name=example.ts.net',
        )

        assert code == 0, output
        assert sorted(path.name for path in docker_dir.iterdir()) == ['.env', 'deploy.sh']
        for task in ('Create docker directory structure', 'Install Docker engine', 'Build autoplex docker image'):
            assert task not in output, output


def _write(path: Path, text: str) -> None:
    """
    Write a file, creating its parent directories
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


@needs_ansible
class TestSecretsRender:
    """
    End-to-end test of the secrets tasks: discovery, directory creation, and rendering, against a temp directory
    """
    def test_renders_an_enabled_service_privately_and_silently(self, tmp_path: Path) -> None:
        """
        Test that --tags secrets renders PiHole's real env.j2 for a service with a compose.yml, 0600, without echoing it

        Guards the first-live-run failure where discovery found no templates and nothing was rendered
        """
        source = tmp_path / 'services'
        _write(source / 'on' / 'compose.yml', 'services: {}\n')
        _write(source / 'on' / 'env.j2', (SERVICES_DIR / 'pihole' / 'env.j2').read_text(encoding='utf-8'))

        code, output, target = _render_secrets(tmp_path, source, 'pihole_web_password=hunter2-test-value')

        assert code == 0, output
        env_file = target / 'on' / '.env'
        assert env_file.read_text(encoding='utf-8').strip() == 'FTLCONF_webserver_api_password=hunter2-test-value'
        assert env_file.stat().st_mode & 0o777 == 0o600
        assert 'hunter2-test-value' not in output
        assert 'Sync compose files' not in output

    def test_skips_a_service_without_a_compose_file(self, tmp_path: Path) -> None:
        """
        Test that a disabled service's template is neither rendered nor required to have its variable defined
        """
        source = tmp_path / 'services'
        _write(source / 'off' / 'compose.yml.disabled', 'services: {}\n')
        _write(source / 'off' / 'env.j2', 'TOKEN={{ off_token }}\n')  # off_token is deliberately undefined

        code, output, target = _render_secrets(tmp_path, source)

        assert code == 0, output
        assert not (target / 'off').exists()

    def test_real_tree_renders_exactly_the_enabled_services(self, tmp_path: Path) -> None:
        """
        Test that the repository's own services/ tree renders a .env for each service with both env.j2 and compose.yml

        The expectation is computed, not hard-coded, so re-enabling PiHole later does not break this test
        """
        enabled = {
            path.parent.name for path in SERVICES_DIR.glob('*/env.j2') if (path.parent / 'compose.yml').is_file()
        }

        code, output, target = _render_secrets(tmp_path, SERVICES_DIR, 'pihole_web_password=hunter2-test-value')

        assert code == 0, output
        assert {path.parent.name for path in target.glob('*/.env')} == enabled

    def test_rendering_nothing_is_not_an_error(self, tmp_path: Path) -> None:
        """
        Test that a tree whose only template belongs to a disabled service renders nothing and still succeeds
        """
        source = tmp_path / 'services'
        _write(source / 'off' / 'compose.yml.disabled', 'services: {}\n')
        _write(source / 'off' / 'env.j2', 'TOKEN=x\n')

        code, output, target = _render_secrets(tmp_path, source)

        assert code == 0, output
        assert not list(target.glob('*/.env'))


def _stub_tool(tmp_path: Path, name: str, output: str) -> dict[str, str]:
    """
    Put a fake executable that prints fixed text, whatever its arguments, first on PATH

    :param tmp_path: scratch directory that receives the ``bin`` directory
    :param name: executable name, e.g. ``smbd``
    :param output: text the stub prints
    :return: environment overrides for ``_run_play``
    """
    stub = tmp_path / 'bin' / name
    _write(stub, f"#!/bin/sh\ncat <<'EOF'\n{output}\nEOF\n")
    stub.chmod(0o755)
    return {'PATH': f'{stub.parent}{os.pathsep}{os.environ["PATH"]}'}


def _without_become(task: TaskDict) -> TaskDict:
    """
    Copy a production task minus ``become``, which a test without sudo cannot honour; nothing else changes
    """
    return {key: value for key, value in task.items() if key != 'become'}


@needs_ansible
class TestReadOnlyProbesRunUnderCheck:
    """
    Real-run tests that read-only probes execute under --check, so the tasks consuming them have a value to work with
    """
    def test_samba_version_probe_feeds_the_template_version_test(self, tmp_path: Path) -> None:
        """
        Test that --check still registers the Samba version that smb.conf.j2 compares

        A skipped probe leaves stdout empty and the template raises "Input version value cannot be empty"
        """
        play = _play_text([
            _without_become(_task('samba', 'Register Samba version')),
            {
                'name': 'Compare the version the way smb.conf.j2 does',
                'ansible.builtin.assert': {
                    'that': [
                        "samba_version.stdout == '4.17.12-Debian'",
                        "samba_version.stdout is version('3.5.0', '>=')",
                    ],
                },
            },
        ])

        code, output = _run_play(
            tmp_path, play, '--check', env=_stub_tool(tmp_path, 'smbd', 'Version 4.17.12-Debian'),
        )

        assert code == 0, output

    def test_tailscale_status_probe_feeds_the_backend_state_parse(self, tmp_path: Path) -> None:
        """
        Test that --check still registers the tailscale status that the following task parses as JSON

        A skipped probe leaves stdout empty and from_json raises "Expecting value"
        """
        play = _play_text([
            _without_become(_task('tailscale', 'Check Tailscale backend state', 'configure.yml')),
            _task('tailscale', 'Parse Tailscale backend state', 'configure.yml'),
            {
                'name': 'Require the parsed state',
                'ansible.builtin.assert': {'that': ["_tailscale_backend_state == 'Running'"]},
            },
        ])

        code, output = _run_play(
            tmp_path, play, '--check', env=_stub_tool(tmp_path, 'tailscale', '{"BackendState": "Running"}'),
        )

        assert code == 0, output
