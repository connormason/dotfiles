"""
Unit tests for run.py script metadata and dependency handling
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

import pytest
import tomllib

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import run

ROOT = Path(__file__).resolve().parents[2]

# Reference regex from PEP 723
PEP723_RE = re.compile(r'(?m)^# /// (?P<type>[a-zA-Z0-9-]+)$\s(?P<content>(^#(| .*)$\s)+)^# ///$')


def _script_metadata() -> dict[str, Any]:
    """
    Parse the PEP 723 ``script`` block at the top of run.py
    """
    text   = (ROOT / 'run.py').read_text(encoding='utf-8')
    blocks = [m for m in PEP723_RE.finditer(text) if m.group('type') == 'script']
    assert len(blocks) == 1

    toml_text = ''.join(
        line[2:] if line.startswith('# ') else line[1:]
        for line in blocks[0].group('content').splitlines(keepends=True)
    )
    return tomllib.loads(toml_text)


class TestScriptMetadata:
    """
    Tests for run.py's PEP 723 inline script metadata
    """
    def test_declares_python_floor(self) -> None:
        """
        Test that the script metadata matches the Python floor run.py is written for
        """
        assert _script_metadata()['requires-python'] == '>=3.9'

    def test_dependencies_match_pyproject(self) -> None:
        """
        Test that the one third-party dependency is declared identically in pyproject.toml
        """
        pyproject = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))
        for dependency in _script_metadata()['dependencies']:
            assert dependency in pyproject['project']['dependencies']

    def test_declares_pyyaml(self) -> None:
        """
        Test that PyYAML (imported lazily by list-hosts) is declared
        """
        assert any(dep.lower().startswith('pyyaml') for dep in _script_metadata()['dependencies'])


class TestListHostsDependency:
    """
    Tests for list-hosts when PyYAML is unavailable
    """
    def test_missing_yaml_is_reported_as_setup_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that a missing yaml module is not reported as an unparsable inventory
        """
        inventory = tmp_path / 'inventory.yml'
        inventory.write_text('all: {}\n', encoding='utf-8')
        monkeypatch.setattr(run, 'INVENTORY_FILE', inventory)
        monkeypatch.setitem(sys.modules, 'yaml', None)      # makes `import yaml` raise ImportError

        with pytest.raises(SystemExit) as exc_info:
            run.get_commands()['list-hosts'](argparse.Namespace())

        out = run.unstyle(capsys.readouterr().out)
        assert exc_info.value.code == run.ExitCode.SETUP_ERROR
        assert 'PyYAML is required'  in out
        assert 'Failed to parse' not in out
