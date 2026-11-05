from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT   = Path(__file__).parents[4]
SCRIPT_PATH = REPO_ROOT / 'scripts' / 'env' / 'loadenv.py'

assert SCRIPT_PATH.is_file(), (
    f'Script under test not found: {SCRIPT_PATH}\n'
    'Did the script move? Update SCRIPT_PATH in this test module.'
)
sys.path.insert(0, str(SCRIPT_PATH.parent))

from loadenv import format_export
from loadenv import format_json
from loadenv import format_pairs


class TestFormatJson:
    """
    Tests for JSON output formatting.
    """
    def test_basic_dict(self) -> None:
        """
        JSON output matches expected structure.
        """
        values = {'KEY': 'value', 'OTHER': 'data'}
        result = format_json(values)
        assert json.loads(result) == {'KEY': 'value', 'OTHER': 'data'}

    def test_none_values_become_null(self) -> None:
        """
        Bare keys with None values become JSON null.
        """
        values = {'BARE': None, 'NORMAL': 'val'}
        result = format_json(values)
        parsed = json.loads(result)
        assert parsed['BARE']   is None
        assert parsed['NORMAL'] == 'val'

    def test_empty_dict(self) -> None:
        """
        Empty input produces empty JSON object.
        """
        assert json.loads(format_json({})) == {}


class TestFormatExport:
    """
    Tests for shell export output formatting.
    """
    def test_basic_export(self) -> None:
        """
        Basic values are double-quoted in export lines.
        """
        values = {'KEY': 'value'}
        result = format_export(values)
        assert result == 'export KEY="value"\n'

    def test_escapes_double_quotes(self) -> None:
        """
        Double quotes in values are escaped.
        """
        values = {'KEY': 'say "hello"'}
        result = format_export(values)
        assert result == 'export KEY="say \\"hello\\""\n'

    def test_escapes_backslashes(self) -> None:
        """
        Backslashes in values are escaped.
        """
        values = {'KEY': 'path\\to\\file'}
        result = format_export(values)
        assert result == 'export KEY="path\\\\to\\\\file"\n'

    def test_escapes_dollar_signs(self) -> None:
        """
        Dollar signs in values are escaped.
        """
        values = {'KEY': 'price is $5'}
        result = format_export(values)
        assert result == 'export KEY="price is \\$5"\n'

    def test_escapes_backticks(self) -> None:
        """
        Backticks in values are escaped.
        """
        values = {'KEY': 'run `cmd`'}
        result = format_export(values)
        assert result == 'export KEY="run \\`cmd\\`"\n'

    def test_skips_none_values(self) -> None:
        """
        Bare keys (None values) are skipped in export mode.
        """
        values = {'BARE': None, 'NORMAL': 'val'}
        result = format_export(values)
        assert 'BARE' not in result
        assert 'export NORMAL="val"' in result

    def test_preserves_literal_newlines(self) -> None:
        """
        Literal newlines in values are preserved inside double quotes.
        """
        values = {'KEY': 'line1\nline2'}
        result = format_export(values)
        assert result == 'export KEY="line1\nline2"\n'


class TestFormatPairs:
    """
    Tests for key=value pairs output formatting.
    """
    def test_basic_pairs(self) -> None:
        """
        Basic values are output as KEY=value.
        """
        values = {'KEY': 'value'}
        result = format_pairs(values)
        assert result == 'KEY=value\n'

    def test_none_values_no_equals(self) -> None:
        """
        Bare keys (None values) output as KEY with no equals sign.
        """
        values = {'BARE': None}
        result = format_pairs(values)
        assert result == 'BARE\n'

    def test_empty_string_has_equals(self) -> None:
        """
        Empty string values output as KEY= (with trailing equals).
        """
        values = {'EMPTY': ''}
        result = format_pairs(values)
        assert result == 'EMPTY=\n'


@pytest.mark.slow
class TestStandaloneCLI:
    """
    Tests for the argparse CLI entry point.
    """
    def test_json_output_default(self, fixtures_dir: Path) -> None:
        """
        Default output format is JSON with correct key-value pairs.
        """
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), str(fixtures_dir / 'basic.env')],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data['APP_NAME'] == 'myapp'
        assert data['APP_PORT'] == '8080'

    def test_export_output(self, fixtures_dir: Path) -> None:
        """
        --export produces shell export statements.
        """
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), '--export', str(fixtures_dir / 'basic.env')],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode         == 0
        assert 'export APP_NAME="myapp"' in result.stdout

    def test_pairs_output(self, fixtures_dir: Path) -> None:
        """
        --pairs produces KEY=value lines.
        """
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), '--pairs', str(fixtures_dir / 'basic.env')],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0
        assert 'APP_NAME=myapp'  in result.stdout

    def test_file_not_found_exit_code_1(self, tmp_path: Path) -> None:
        """
        Missing file returns exit code 1 with error on stderr.
        """
        missing = str(tmp_path / 'nonexistent.env')
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), missing],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 1
        assert 'file not found'  in result.stderr.lower()

    def test_quiet_suppresses_stderr(self, tmp_path: Path) -> None:
        """
        -q flag suppresses stderr but preserves exit code 1.
        """
        missing = str(tmp_path / 'nonexistent.env')
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), '-q', missing],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 1
        assert result.stderr     == ''

    def test_no_interpolate_flag(self, fixtures_dir: Path) -> None:
        """
        --no-interpolate preserves ${VAR} literals.
        """
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), '--no-interpolate', str(fixtures_dir / 'interpolation.env')],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert '${BASE_DIR}' in data['DATA_DIR']

    def test_override_flag(self, fixtures_dir: Path) -> None:
        """
        --override causes .env values to win over existing env vars.
        """
        env = os.environ.copy()
        env['BASE_DIR'] = '/from/env'

        # Without --override: env var wins
        result_no = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), str(fixtures_dir / 'interpolation.env')],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        data_no = json.loads(result_no.stdout)
        assert data_no['DATA_DIR'] == '/from/env/data'

        # With --override: .env value wins
        result_yes = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), '--override', str(fixtures_dir / 'interpolation.env')],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        data_yes = json.loads(result_yes.stdout)
        assert data_yes['DATA_DIR'] == '/opt/app/data'

    def test_auto_discovery_walks_up(self, tmp_path: Path) -> None:
        """
        Auto-discovery finds .env by walking up from CWD.
        """
        dotenv_file = tmp_path / '.env'
        dotenv_file.write_text('DISCOVERED=yes\n')
        deep_dir = tmp_path / 'sub' / 'deep'
        deep_dir.mkdir(parents=True)

        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH)],
            capture_output=True,
            text=True,
            cwd=str(deep_dir),
            check=False,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data['DISCOVERED'] == 'yes'

    def test_parse_error_exit_code_2(self, fixtures_dir: Path) -> None:
        """
        Parse errors return exit code 2 with partial results.
        """
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), str(fixtures_dir / 'parse_errors.env')],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 2
        data = json.loads(result.stdout)
        assert 'VALID_KEY'  in data
        assert 'ALSO_VALID' in data


class TestShellSafety:
    """
    Verify export output is safe against shell injection.
    """
    def test_injection_via_double_quotes(self) -> None:
        """
        Values with double quotes cannot break out of quoting.
        """
        values = {'KEY': '"; rm -rf / #'}
        result = format_export(values)
        assert result == 'export KEY="\\"; rm -rf / #"\n'

    def test_injection_via_command_substitution(self) -> None:
        """
        Values with $() cannot trigger command substitution.
        """
        values = {'KEY': '$(whoami)'}
        result = format_export(values)
        assert result == 'export KEY="\\$(whoami)"\n'

    def test_injection_via_backticks(self) -> None:
        """
        Values with backticks cannot trigger command substitution.
        """
        values = {'KEY': '`whoami`'}
        result = format_export(values)
        assert result == 'export KEY="\\`whoami\\`"\n'

    def test_combined_injection_attempt(self) -> None:
        """
        Combined injection techniques are all neutralized.
        """
        values = {'KEY': 'a"$(b)`c`\\d$e'}
        result = format_export(values)
        assert '\\"'  in result
        assert '\\$'  in result
        assert '\\`'  in result
        assert '\\\\' in result
