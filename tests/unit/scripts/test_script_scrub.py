"""
Unit tests asserting the copied install/env/codebase scripts carry no employer-internal markers
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT:    Path       = Path(__file__).resolve().parents[3]
LEAK_GUARD:   Path       = REPO_ROOT / 'scripts' / 'hooks' / 'check-leaks.py'
SCRIPT_DIRS:  list[Path] = [
    REPO_ROOT / 'scripts' / 'install',
    REPO_ROOT / 'scripts' / 'env',
    REPO_ROOT / 'scripts' / 'codebase',
]
SCRIPT_FILES: list[Path] = sorted(path for directory in SCRIPT_DIRS for path in directory.glob('*.py'))


@pytest.fixture(scope='module')
def leak_guard() -> object:
    """
    Load the hyphen-named leak guard hook as a module
    """
    spec = importlib.util.spec_from_file_location('check_leaks', LEAK_GUARD)
    assert spec        is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TestScriptScrub:
    """
    Tests that the scripts under scripts/install, scripts/env and scripts/codebase pass the public-repo leak guard
    """
    def test_scripts_are_discovered(self) -> None:
        """
        Test that the glob finds the copied scripts, so the parametrized checks cannot pass vacuously
        """
        assert {path.name for path in SCRIPT_FILES} >= {
            'install_uv.py', 'install_hatch.py', 'python_diagnostic.py', 'venvshell.py', 'update_gitignore.py',
        }

    @pytest.mark.parametrize('script', SCRIPT_FILES, ids=lambda path: path.name)
    def test_script_has_no_internal_markers(self, leak_guard: object, script: Path) -> None:
        """
        Test that the leak guard baseline (plus the private pattern file, when present) flags nothing in the script
        """
        patterns = leak_guard.load_patterns(leak_guard.default_patterns_file(), required=False)     # type: ignore[attr-defined]
        findings = leak_guard.scan_file(script, patterns)                                           # type: ignore[attr-defined]
        assert findings == []
