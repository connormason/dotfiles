"""
Guardrail tests that keep path-keyed configuration from naming files that no longer exist
"""
from __future__ import annotations

import json
from pathlib import Path

import tomllib

REPO_ROOT = Path(__file__).resolve().parents[2]


class TestPathKeyedConfig:
    """
    Tests for configuration files whose keys are repository paths
    """
    def test_secrets_baseline_names_only_existing_files(self) -> None:
        """
        Test that every file listed in .secrets.baseline still exists
        """
        results = json.loads((REPO_ROOT / '.secrets.baseline').read_text(encoding='utf-8'))['results']
        missing = sorted(name for name in results if not (REPO_ROOT / name).exists())
        assert not missing, f'.secrets.baseline lists files that no longer exist: {missing}'

    def test_ruff_per_file_ignores_match_existing_paths(self) -> None:
        """
        Test that every ruff per-file-ignores pattern in pyproject.toml matches at least one path
        """
        config    = tomllib.loads((REPO_ROOT / 'pyproject.toml').read_text(encoding='utf-8'))
        patterns  = config['tool']['ruff']['lint']['per-file-ignores']
        unmatched = sorted(pattern for pattern in patterns if not any(REPO_ROOT.glob(pattern)))

        assert not unmatched, f'pyproject.toml per-file-ignores match nothing: {unmatched}'
