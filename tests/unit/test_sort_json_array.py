"""
Unit tests for scripts/hooks/sort-json-array.py and its .pre-commit-config.yaml wiring
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import yaml

if TYPE_CHECKING:
    from types import ModuleType

REPO_ROOT   = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / 'scripts' / 'hooks' / 'sort-json-array.py'
CONFIG_PATH = REPO_ROOT / '.pre-commit-config.yaml'
KEYBINDINGS = 'stow/vscode/Library/Application Support/Code/User/keybindings.json'


def _load_module() -> ModuleType:
    """
    Import the hyphenated hook script as module ``sort_json_array``
    """
    spec = importlib.util.spec_from_file_location('sort_json_array', SCRIPT_PATH)
    assert spec        is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules['sort_json_array'] = module
    spec.loader.exec_module(module)
    return module


sort_json_array = _load_module()


def _write_json(path: Path, data: object) -> str:
    """
    Write ``data`` in the exact serialization the hook emits and return the text
    """
    text = json.dumps(data, indent=4, sort_keys=True, separators=(',', ': ')) + '\n'
    path.write_text(text, encoding='utf-8')
    return text


def _wired_hook() -> dict:
    """
    Return the ``sort-json-array`` hook entry declared in ``.pre-commit-config.yaml``
    """
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding='utf-8'))
    hooks  = [hook for repo in config['repos'] for hook in repo['hooks'] if hook['id'] == 'sort-json-array']
    assert len(hooks) == 1
    return hooks[0]


class TestSortFile:
    """
    Tests for sort_json_array.sort_file
    """
    def test_unsorted_input_is_rewritten(self, tmp_path: Path) -> None:
        """
        Test that an unsorted array is sorted in place and reported with exit code 1
        """
        path = tmp_path / 'in.json'
        _write_json(path, [{'command': 'b'}, {'command': 'c'}, {'command': 'a'}])

        assert sort_json_array.sort_file(path, key='command', indent=4) == 1
        assert [entry['command'] for entry in json.loads(path.read_text(encoding='utf-8'))] == ['a', 'b', 'c']

    def test_sorted_input_is_untouched(self, tmp_path: Path) -> None:
        """
        Test that an already sorted array keeps its bytes and exits 0
        """
        path     = tmp_path / 'in.json'
        original = _write_json(path, [{'command': 'a'}, {'command': 'b'}])

        assert sort_json_array.sort_file(path, key='command', indent=4) == 0
        assert path.read_text(encoding='utf-8') == original

    def test_second_run_is_a_noop(self, tmp_path: Path) -> None:
        """
        Test that a rewritten file is stable: the next run exits 0 and changes nothing
        """
        path = tmp_path / 'in.json'
        _write_json(path, [{'command': 'z'}, {'command': 'a'}])

        assert sort_json_array.sort_file(path, key='command', indent=4) == 1
        rewritten = path.read_text(encoding='utf-8')
        assert sort_json_array.sort_file(path, key='command', indent=4) == 0
        assert path.read_text(encoding='utf-8') == rewritten

    def test_missing_key_sorts_first(self, tmp_path: Path) -> None:
        """
        Test that entries lacking the sort key come before entries that have it
        """
        path = tmp_path / 'in.json'
        _write_json(path, [{'command': 'a'}, {'other': 1}, {'command': '-a'}])

        assert sort_json_array.sort_file(path, key='command', indent=4) == 1
        assert json.loads(path.read_text(encoding='utf-8')) == [{'other': 1}, {'command': '-a'}, {'command': 'a'}]

    def test_equal_keys_keep_their_order(self, tmp_path: Path) -> None:
        """
        Test that the sort is stable for entries sharing the same key value
        """
        path = tmp_path / 'in.json'
        _write_json(path, [{'command': 'b', 'key': '2'}, {'command': 'a', 'key': 'x'}, {'command': 'b', 'key': '1'}])

        assert sort_json_array.sort_file(path, key='command', indent=4) == 1
        assert [entry['key'] for entry in json.loads(path.read_text(encoding='utf-8'))] == ['x', '2', '1']

    def test_custom_key(self, tmp_path: Path) -> None:
        """
        Test that --key selects the sort field
        """
        path = tmp_path / 'in.json'
        _write_json(path, [{'name': 'b'}, {'name': 'a'}])

        assert sort_json_array.sort_file(path, key='name', indent=4) == 1
        assert [entry['name'] for entry in json.loads(path.read_text(encoding='utf-8'))] == ['a', 'b']

    @pytest.mark.parametrize(
        'content',
        [
            '{"command": "a"}\n',
            '[1, 2, 3]\n',
            '[{"command": "a"}, "text"]\n',
            '[{"command": "a"},\n',
            '',
        ],
        ids=['object', 'array-of-numbers', 'mixed-array', 'invalid-json', 'empty'],
    )
    def test_invalid_input_fails_without_modifying_file(self, tmp_path: Path, content: str) -> None:
        """
        Test that non-array, non-object-entry, and malformed JSON return 1 and leave the file as it was
        """
        path = tmp_path / 'in.json'
        path.write_text(content, encoding='utf-8')

        assert sort_json_array.sort_file(path, key='command', indent=4) == 1
        assert path.read_text(encoding='utf-8') == content

    def test_missing_file_fails(self, tmp_path: Path) -> None:
        """
        Test that an unreadable path returns 1 instead of raising
        """
        assert sort_json_array.sort_file(tmp_path / 'absent.json', key='command', indent=4) == 1


class TestMain:
    """
    Tests for sort_json_array.main
    """
    def test_no_filenames_returns_zero(self) -> None:
        """
        Test that an empty file list is a successful no-op
        """
        assert sort_json_array.main([]) == 0

    def test_any_rewritten_file_makes_exit_nonzero(self, tmp_path: Path) -> None:
        """
        Test that one rewritten file among sorted ones yields exit code 1
        """
        sorted_path   = tmp_path / 'sorted.json'
        unsorted_path = tmp_path / 'unsorted.json'
        _write_json(sorted_path,   [{'command': 'a'}, {'command': 'b'}])
        _write_json(unsorted_path, [{'command': 'b'}, {'command': 'a'}])

        assert sort_json_array.main(['--key', 'command', str(sorted_path), str(unsorted_path)]) == 1

    def test_tracked_keybindings_already_sorted(self) -> None:
        """
        Test that the tracked VS Code keybindings.json is sorted, so the wired hook is a no-op on it
        """
        path     = REPO_ROOT / KEYBINDINGS
        original = path.read_bytes()

        assert sort_json_array.sort_file(path, key='command', indent=4) == 0
        assert path.read_bytes() == original


class TestPreCommitWiring:
    """
    Tests for the sort-json-array hook entry in .pre-commit-config.yaml
    """
    def test_hook_declares_expected_entry(self) -> None:
        """
        Test that the hook runs the script with the command key in the pre-commit stage
        """
        hook = _wired_hook()

        assert hook['entry']    == 'scripts/hooks/sort-json-array.py'
        assert hook['language'] == 'python'
        assert hook['args']     == ['--key', 'command']
        assert hook['stages']   == ['pre-commit']
        assert (REPO_ROOT / hook['entry']).is_file()

    def test_files_pattern_matches_tracked_keybindings(self) -> None:
        """
        Test that the files regex matches the tracked keybindings path
        """
        assert re.search(_wired_hook()['files'], KEYBINDINGS)

    @pytest.mark.parametrize(
        'path',
        [
            'stow/vscode/Library/Application Support/Code/User/settings.json',
            'stow/zed/.config/zed/settings.json',
            'settings.json',
            'keybindings.json',
            'other/stow/vscode/Library/Application Support/Code/User/keybindings.json',
            f'{KEYBINDINGS}.bak',
        ],
    )
    def test_files_pattern_rejects_other_paths(self, path: str) -> None:
        """
        Test that the files regex does not match unrelated JSON files or lookalike paths
        """
        assert not re.search(_wired_hook()['files'], path)
