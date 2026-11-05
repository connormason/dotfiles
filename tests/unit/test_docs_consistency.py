"""
Guardrail tests that keep hand-maintained documentation inventories in sync with the infrastructure they describe

These assert that the bootstrap stage table in ``bootstrap/README.md``, the package table in ``stow/README.md``, the
roles table in ``roles/README.md``, and the container table in ``services/README.md`` match the stage scripts, stow
package directories, role directories, and compose files on disk. They also assert that the role order in the playbook
docs (``roles/README.md``, ``playbooks/README.md``, ``.ctx/ARCHITECTURE.md``) follows ``playbooks/nas_bootstrap.yml``
and that ``docs/RUN_PY_REFERENCE.md`` documents every command ``run.py`` registers. They exist to catch the drift
documented in ``CLAUDE-LESSONS.md`` ("Hand-maintained inventories in docs drift: guard each with a test") the moment
an inventory changes.
"""
from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]

# A bootstrap stage id: a two-digit ordering prefix plus a lowercase-kebab name (e.g. ``00-preflight``, ``72-vscode``)
STAGE_ID = r'\d{2}-[a-z0-9][a-z0-9-]*'

# A stow package name as written in the first cell of a stow/README.md table row (e.g. ``| `os_tools` |``)
PACKAGE_ROW = re.compile(r'^\|\s*`([A-Za-z0-9_-]+)`\s*\|(.*)$', re.MULTILINE)

# A conf.d snippet name inside a table cell (e.g. ``40-git.zsh``)
SNIPPET = re.compile(r'`(\d{2}-[A-Za-z0-9_-]+\.zsh)`')


# ==============================================================================
# Parsing helpers
# ==============================================================================

def _stage_scripts_on_disk(repo: Path) -> set[str]:
    """
    Return the set of bootstrap stage ids backed by a ``NN-*.sh`` script

    :param repo: repository root
    :return: stage ids such as ``{"00-preflight", "72-vscode", ...}``
    """
    return {path.stem for path in (repo / 'bootstrap').glob('[0-9][0-9]-*.sh')}


def _stage_ids_in_readme(repo: Path) -> set[str]:
    """
    Return the stage ids listed in the ``bootstrap/README.md`` stage table

    Only the leading cell of each table row is considered, so prose mentions of a stage elsewhere in the file are
    ignored.

    :param repo: repository root
    :return: stage ids documented in the stage table
    """
    text = (repo / 'bootstrap' / 'README.md').read_text(encoding='utf-8')
    row_pattern = re.compile(rf'^\|\s*({STAGE_ID})\s*\|', re.MULTILINE)
    return set(row_pattern.findall(text))


def _stow_package_dirs(repo: Path) -> set[str]:
    """
    Return the names of the package directories under ``stow/``

    :param repo: repository root
    :return: one entry per top-level package directory (hidden directories excluded)
    """
    return {
        path.name
        for path in (repo / 'stow').iterdir()
        if path.is_dir() and not path.name.startswith('.')
    }


def _stow_readme_rows(repo: Path) -> dict[str, str]:
    """
    Return the rows of the ``stow/README.md`` package table, keyed by package name

    Only rows whose first cell is a backticked name are considered, so the header, the separator, and prose are ignored.

    :param repo: repository root
    :return: mapping of package name to the remainder of its table row (the cells after the package name)
    """
    text = (repo / 'stow' / 'README.md').read_text(encoding='utf-8')
    return dict(PACKAGE_ROW.findall(text))


def _conf_d_snippets_on_disk(repo: Path, package: str) -> set[str]:
    """
    Return the zsh conf.d snippet file names a stow package provides

    :param repo: repository root
    :param package: package directory name under ``stow/``
    :return: snippet file names such as ``{"40-git.zsh"}``; empty when the package has none
    """
    conf_d = repo / 'stow' / package / '.config' / 'zsh' / 'conf.d'
    return {path.name for path in conf_d.glob('*.zsh')} if conf_d.is_dir() else set()


def _out_of_sync_message(label_a: str, set_a: set[str], label_b: str, set_b: set[str]) -> str:
    """
    Build a diff-style assertion message naming what is missing from each side

    :param label_a: human label for the first set
    :param set_a: the first set
    :param label_b: human label for the second set
    :param set_b: the second set
    :return: a multi-line message listing the asymmetric differences
    """
    only_a = sorted(set_a - set_b)
    only_b = sorted(set_b - set_a)
    return (
        f'{label_a} and {label_b} are out of sync:\n'
        f'  only in {label_a}: {only_a or "none"}\n'
        f'  only in {label_b}: {only_b or "none"}'
    )


# ==============================================================================
# Bootstrap stage documentation
# ==============================================================================

class TestBootstrapStageDocs:
    """
    Guardrails tying the bootstrap stage table to the stage scripts
    """
    def test_readme_table_matches_stage_scripts(self) -> None:
        """
        The bootstrap/README.md stage table lists exactly the NN-*.sh scripts on disk
        """
        documented = _stage_ids_in_readme(REPO_ROOT)
        on_disk    = _stage_scripts_on_disk(REPO_ROOT)

        assert documented == on_disk, _out_of_sync_message(
            'bootstrap/README.md stage table',
            documented,
            'bootstrap/*.sh scripts',
            on_disk,
        )

    def test_stage_table_is_not_empty(self) -> None:
        """
        The stage-table parser finds rows (guards against a silently broken regex)
        """
        assert _stage_ids_in_readme(REPO_ROOT), 'parsed zero stages from bootstrap/README.md'


# ==============================================================================
# Stow package documentation
# ==============================================================================

class TestStowPackageDocs:
    """
    Guardrails tying the stow/README.md package table to the stow/ directories
    """
    def test_readme_table_matches_stow_dirs(self) -> None:
        """
        Every directory under stow/ appears in the stow/README.md table and vice versa
        """
        documented = set(_stow_readme_rows(REPO_ROOT))
        on_disk    = _stow_package_dirs(REPO_ROOT)

        assert documented == on_disk, _out_of_sync_message(
            'stow/README.md package table',
            documented,
            'stow/ directories',
            on_disk,
        )

    def test_package_table_is_not_empty(self) -> None:
        """
        The package-table parser finds rows (guards against a silently broken regex)
        """
        assert _stow_readme_rows(REPO_ROOT), 'parsed zero packages from stow/README.md'

    def test_conf_d_column_matches_snippets_on_disk(self) -> None:
        """
        Each package row lists exactly the conf.d snippets its directory provides
        """
        mismatches: list[str] = []
        for package, rest in _stow_readme_rows(REPO_ROOT).items():
            documented = set(SNIPPET.findall(rest))
            on_disk    = _conf_d_snippets_on_disk(REPO_ROOT, package)
            if documented != on_disk:
                mismatches.append(
                    f'{package}: documented {sorted(documented) or "none"}, on disk {sorted(on_disk) or "none"}',
                )

        assert not mismatches, 'stow/README.md conf.d column is out of sync:\n  ' + '\n  '.join(mismatches)


def _role_dirs(repo: Path) -> set[str]:
    """
    Return the names of the role directories under ``roles/``

    :param repo: repository root
    :return: one entry per role directory (hidden directories such as ansible-lint's ``.backups`` excluded)
    """
    return {path.name for path in (repo / 'roles').iterdir() if path.is_dir() and not path.name.startswith('.')}


def _roles_readme_rows(repo: Path) -> set[str]:
    """
    Return the role names linked in the first cell of the ``roles/README.md`` table

    :param repo: repository root
    :return: role names such as ``{"debian", "dotfiles", ...}``
    """
    text = (repo / 'roles' / 'README.md').read_text(encoding='utf-8')
    return set(re.findall(r'^\|\s*\[`([a-z0-9_-]+)`\]\(', text, re.MULTILINE))


class TestRolesReadme:
    """
    Tests that roles/README.md lists exactly the roles on disk
    """
    def test_readme_table_matches_role_dirs(self) -> None:
        """
        Test that every role directory has a table row and every row has a directory
        """
        assert _roles_readme_rows(REPO_ROOT) == _role_dirs(REPO_ROOT)


# A services/README.md Quick Reference row: the container name in the first cell (e.g. ``| `caddy` | ...``)
SERVICE_ROW = re.compile(r'^\|\s*`([a-z0-9_-]+)`\s*\|(.*)$', re.MULTILINE)


def _services_readme_rows(repo: Path) -> dict[str, str]:
    """
    Return the rows of the ``services/README.md`` Quick Reference table, keyed by container name

    :param repo: repository root
    :return: mapping of container name to the remainder of its table row
    """
    text  = (repo / 'services' / 'README.md').read_text(encoding='utf-8')
    quick = text.split('## Quick Reference', 1)[1].split('\n## ', 1)[0]
    return dict(SERVICE_ROW.findall(quick))


def _compose_containers(repo: Path) -> dict[str, bool]:
    """
    Return every container defined under ``services/`` and whether its compose file is enabled

    :param repo: repository root
    :return: mapping of container name (``container_name``, else the service key) to True for ``compose.yml`` and
             False for ``compose.yml.disabled``
    """
    found: dict[str, bool] = {}
    for path in sorted((repo / 'services').glob('*/compose.yml*')):
        if path.name not in ('compose.yml', 'compose.yml.disabled'):
            continue
        for key, service in yaml.safe_load(path.read_text(encoding='utf-8'))['services'].items():
            found[service.get('container_name', key)] = path.name == 'compose.yml'
    return found


class TestServicesReadme:
    """
    Guardrails tying the services/README.md container table to the compose files
    """
    def test_container_table_matches_compose_files(self) -> None:
        """
        The Quick Reference table lists exactly the containers the compose files define
        """
        documented = set(_services_readme_rows(REPO_ROOT))
        on_disk    = set(_compose_containers(REPO_ROOT))

        assert documented == on_disk, _out_of_sync_message(
            'services/README.md Quick Reference', documented, 'services/*/compose.yml*', on_disk,
        )

    def test_disabled_marker_matches_disabled_compose_files(self) -> None:
        """
        A row is marked (**disabled**) exactly when its compose file is compose.yml.disabled
        """
        rows    = _services_readme_rows(REPO_ROOT)
        enabled = _compose_containers(REPO_ROOT)

        mismatches: list[str] = []
        for name, rest in rows.items():
            marked_disabled = '(**disabled**)' in rest
            if name in enabled and marked_disabled == enabled[name]:
                mismatches.append(f'{name}: marked disabled={marked_disabled}, compose enabled={enabled[name]}')

        assert not mismatches, 'services/README.md disabled markers are out of sync:\n  ' + '\n  '.join(mismatches)

    def test_container_table_is_not_empty(self) -> None:
        """
        The container-table parser finds rows (guards against a silently broken regex)
        """
        assert _services_readme_rows(REPO_ROOT), 'parsed zero containers from services/README.md'


def _playbook_role_order(repo: Path) -> list[str]:
    """
    Return the roles ``playbooks/nas_bootstrap.yml`` includes, in play order

    :param repo: repository root
    :return: role names without the ``roles/`` prefix
    """
    key  = 'ansible.builtin.include_role'
    play = yaml.safe_load((repo / 'playbooks' / 'nas_bootstrap.yml').read_text(encoding='utf-8'))[0]
    return [task[key]['name'].removeprefix('roles/') for task in play['tasks'] if key in task]


def _playbooks_readme_role_order(repo: Path) -> list[str]:
    """
    Return the role names bolded in the numbered execution-order list of ``playbooks/README.md``

    :param repo: repository root
    :return: role names in document order (steps whose bold text is not a role directory, such as the apt refresh, are
             ignored)
    """
    text  = (repo / 'playbooks' / 'README.md').read_text(encoding='utf-8')
    names = re.findall(r'^\d+\. \*\*([a-z0-9_-]+)\*\*', text, re.MULTILINE)
    return [name for name in names if name in _role_dirs(repo)]


def _roles_readme_role_order(repo: Path) -> list[str]:
    """
    Return the role names linked in the first cell of the ``roles/README.md`` table, in table order
    """
    text = (repo / 'roles' / 'README.md').read_text(encoding='utf-8')
    return re.findall(r'^\|\s*\[`([a-z0-9_-]+)`\]\(', text, re.MULTILINE)


class TestRoleOrderDocs:
    """
    Guardrails tying the documented role order to the playbook
    """
    def test_playbooks_readme_follows_the_playbook(self) -> None:
        """
        The execution-order list in playbooks/README.md names the roles in the playbook's order
        """
        assert _playbooks_readme_role_order(REPO_ROOT) == _playbook_role_order(REPO_ROOT)

    def test_roles_readme_table_follows_the_playbook(self) -> None:
        """
        The roles/README.md table lists the roles in the playbook's order
        """
        assert _roles_readme_role_order(REPO_ROOT) == _playbook_role_order(REPO_ROOT)

    def test_order_parsers_are_not_empty(self) -> None:
        """
        The order parsers find roles (guards against silently broken regexes)
        """
        assert _playbook_role_order(REPO_ROOT)
        assert _playbooks_readme_role_order(REPO_ROOT)
        assert _roles_readme_role_order(REPO_ROOT)

    def test_architecture_role_list_follows_the_playbook(self) -> None:
        """
        The role bullets in .ctx/ARCHITECTURE.md name the roles in the playbook's order
        """
        text    = (REPO_ROOT / '.ctx' / 'ARCHITECTURE.md').read_text(encoding='utf-8')
        section = text.split('## Role System (NAS)', 1)[1].split('\n## ', 1)[0]
        roles   = re.findall(r'^- `([a-z0-9_-]+)`:', section, re.MULTILINE)

        assert roles == _playbook_role_order(REPO_ROOT)


def _registered_commands(repo: Path) -> set[str]:
    """
    Return the command names registered in ``run.py``

    :param repo: repository root
    :return: names in ``run.REGISTERED_COMMANDS``
    """
    sys.path.insert(0, str(repo))
    try:
        module = importlib.import_module('run')
    finally:
        sys.path.remove(str(repo))
    return set(module.REGISTERED_COMMANDS)


class TestRunPyReference:
    """
    Guardrails tying docs/RUN_PY_REFERENCE.md to the commands run.py registers
    """
    def test_every_registered_command_is_documented(self) -> None:
        """
        Every command registered in run.py appears backticked in the reference
        """
        text    = (REPO_ROOT / 'docs' / 'RUN_PY_REFERENCE.md').read_text(encoding='utf-8')
        missing = sorted(name for name in _registered_commands(REPO_ROOT) if f'`{name}`' not in text)

        assert not missing, f'docs/RUN_PY_REFERENCE.md does not document: {missing}'

    def test_registry_is_not_empty(self) -> None:
        """
        The registry lookup finds commands (guards against a broken import)
        """
        assert _registered_commands(REPO_ROOT)
