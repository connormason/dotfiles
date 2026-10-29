"""
Guardrail tests that keep hand-maintained documentation inventories in sync with the infrastructure they describe

These assert that the bootstrap stage table in ``bootstrap/README.md`` and the package table in ``stow/README.md`` match
the stage scripts and stow package directories on disk. They exist to catch the drift documented in
``CLAUDE-LESSONS.md`` ("Enumerated infra inventories in docs drift") the moment a stage or package is added or removed.
"""
from __future__ import annotations

import re
from pathlib import Path

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
