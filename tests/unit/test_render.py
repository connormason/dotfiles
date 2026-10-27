"""
Unit tests for scripts/dotfiles/render.py
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType

REPO_ROOT   = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / 'scripts' / 'dotfiles' / 'render.py'

# Inherited variables that would leak the developer's own configuration into the tests
_SCRUBBED_VARS = (
    'DOTFILES_REPO',
    'DOTFILES_BREW_PREFIXES',
    'DOTFILES_LEAK_PATTERNS',
    'DOTFILES_OVERLAYS_FILE',
)


def _load_module() -> ModuleType:
    """
    Import render.py as module ``render``
    """
    spec = importlib.util.spec_from_file_location('render', SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules['render'] = module
    spec.loader.exec_module(module)
    return module


render = _load_module()


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """
    Fixture repo with lib.sh, an overlay, an isolated HOME and state dir
    """
    for var in _SCRUBBED_VARS:
        monkeypatch.delenv(var, raising=False)
    repo = tmp_path / 'repo'
    (repo / 'bootstrap').mkdir(parents=True)
    (repo / 'render').mkdir()
    shutil.copy2(REPO_ROOT / 'bootstrap' / 'lib.sh', repo / 'bootstrap' / 'lib.sh')
    overlay = tmp_path / 'overlay'
    (overlay / 'render').mkdir(parents=True)
    home = tmp_path / 'home'
    home.mkdir()
    registry = tmp_path / 'overlays'
    registry.write_text(f'{overlay}\n', encoding='utf-8')
    monkeypatch.setenv('HOME', str(home))
    monkeypatch.setenv('XDG_CONFIG_HOME', str(home / '.config'))
    monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path / 'state'))
    monkeypatch.setenv('DOTFILES_OVERLAYS_FILE', str(registry))
    return {'repo': repo, 'overlay': overlay, 'home': home, 'state': tmp_path / 'state'}


def _fragment(layer: Path, target: str, data: object) -> None:
    """
    Write a render fragment for target into layer
    """
    (layer / 'render' / f'{target}.json').write_text(json.dumps(data), encoding='utf-8')


def _claude(world: dict[str, Path]) -> Path:
    """
    Path of the rendered claude settings in the fixture HOME
    """
    return world['home'] / '.claude' / 'settings.json'


def _run(world: dict[str, Path], *args: str) -> int:
    """
    Invoke render.main against the fixture repo
    """
    return render.main(['--repo', str(world['repo']), *args])


class TestMerge:
    """
    Tests for merge semantics
    """
    @pytest.mark.parametrize(
        ('base', 'overlay', 'expected'),
        [
            ({'a': 1, 'b': {'x': 1}}, {'b': {'y': 2}},   {'a': 1, 'b': {'x': 1, 'y': 2}}),
            ({'a': 1},                {'a': 2},          {'a': 2}),
            ({'a': 1, 'b': 2},        {'b': None},       {'a': 1}),
            ({'a': {'x': 1}},         {'a': {'x': None}}, {'a': {}}),
            ({},                      {'n': {'k': None, 'v': 1}}, {'n': {'v': 1}}),
            ([1, 2],                  [2, 3],            [1, 2, 3]),
            ([{'m': 'x'}],            [{'m': 'x'}, {'m': 'y'}], [{'m': 'x'}, {'m': 'y'}]),
            ({'a': [1]},              {'a': 'scalar'},   {'a': 'scalar'}),
        ],
    )
    def test_merge(self, base: object, overlay: object, expected: object) -> None:
        """
        Test deep merge, array de-duplication, scalar override, and null deletion
        """
        assert render.merge(base, overlay) == expected

    def test_dumps_is_deterministic(self) -> None:
        """
        Test that output is key-sorted, 2-space indented, and newline-terminated
        """
        assert render.dumps({'b': 1, 'a': [1]}) == '{\n  "a": [\n    1\n  ],\n  "b": 1\n}\n'


class TestCompose:
    """
    Tests for composing fragments across layers
    """
    def test_layer_order_and_unmanaged(self, world: dict[str, Path]) -> None:
        """
        Test that overlays merge after the base and $unmanaged lists merge and are removed
        """
        _fragment(world['repo'], 'claude', {'theme': 'dark', '$unmanaged': ['stateA']})
        _fragment(world['overlay'], 'claude', {'theme': 'light', 'env': {'X': '1'}, '$unmanaged': ['stateB']})
        fragments = [world['repo'] / 'render' / 'claude.json', world['overlay'] / 'render' / 'claude.json']
        managed, unmanaged = render.compose(fragments)
        assert managed == {'env': {'X': '1'}, 'theme': 'light'}
        assert unmanaged == ['stateA', 'stateB']

    def test_bad_unmanaged_type_is_config_error(self, world: dict[str, Path]) -> None:
        """
        Test that a non-list $unmanaged is rejected
        """
        _fragment(world['repo'], 'claude', {'$unmanaged': 'oops'})
        with pytest.raises(render.RenderError):
            render.compose([world['repo'] / 'render' / 'claude.json'])


class TestLayers:
    """
    Tests for layer resolution through lib.sh
    """
    def test_base_first_then_overlays(self, world: dict[str, Path]) -> None:
        """
        Test that the base repo precedes the registered overlay
        """
        resolved = [path.resolve() for path in render.layers(world['repo'])]
        assert resolved == [world['repo'].resolve(), world['overlay'].resolve()]


class TestRender:
    """
    Tests for rendering, drift guard, and modes
    """
    def test_first_render_writes_file_and_state(self, world: dict[str, Path]) -> None:
        """
        Test that a first render creates the target and records state
        """
        _fragment(world['repo'], 'claude', {'theme': 'dark'})
        assert _run(world, 'claude') == 0
        assert json.loads(_claude(world).read_text(encoding='utf-8')) == {'theme': 'dark'}
        assert (world['state'] / 'dotfiles' / 'render' / 'claude.json').is_file()

    def test_in_app_edit_is_refused(self, world: dict[str, Path]) -> None:
        """
        Test that a live edit since the last render blocks rendering and leaves the file untouched
        """
        _fragment(world['repo'], 'claude', {'theme': 'dark'})
        assert _run(world, 'claude') == 0
        _claude(world).write_text('{"theme": "edited"}\n', encoding='utf-8')
        _fragment(world['repo'], 'claude', {'theme': 'dark', 'verbose': True})
        assert _run(world, 'claude') == 1
        assert json.loads(_claude(world).read_text(encoding='utf-8')) == {'theme': 'edited'}

    def test_force_backs_up_and_overwrites(self, world: dict[str, Path]) -> None:
        """
        Test that --force saves the live file to ~/.dotfiles-backup and renders
        """
        _fragment(world['repo'], 'claude', {'theme': 'dark'})
        _claude(world).parent.mkdir(parents=True)
        _claude(world).write_text('{"theme": "hand-made"}\n', encoding='utf-8')
        assert _run(world, 'claude', '--force') == 0
        backups = list((world['home'] / '.dotfiles-backup').glob('*/.claude/settings.json'))
        assert len(backups) == 1
        assert 'hand-made' in backups[0].read_text(encoding='utf-8')
        assert json.loads(_claude(world).read_text(encoding='utf-8')) == {'theme': 'dark'}

    def test_unmanaged_keys_survive_and_do_not_drift(self, world: dict[str, Path]) -> None:
        """
        Test that installer-owned keys are preserved and ignored by the drift guard
        """
        _fragment(world['repo'], 'claude', {'theme': 'dark', '$unmanaged': ['installerHash']})
        assert _run(world, 'claude') == 0
        live = json.loads(_claude(world).read_text(encoding='utf-8'))
        live['installerHash'] = 'abc'
        _claude(world).write_text(json.dumps(live), encoding='utf-8')
        _fragment(world['repo'], 'claude', {'theme': 'light', '$unmanaged': ['installerHash']})
        assert _run(world, 'claude') == 0
        assert json.loads(_claude(world).read_text(encoding='utf-8')) == {'installerHash': 'abc', 'theme': 'light'}

    def test_existing_identical_file_is_adopted(self, world: dict[str, Path]) -> None:
        """
        Test that a pre-existing file equal to the render is adopted without --force
        """
        _fragment(world['repo'], 'claude', {'theme': 'dark'})
        _claude(world).parent.mkdir(parents=True)
        _claude(world).write_text('{"theme": "dark"}', encoding='utf-8')
        assert _run(world, 'claude') == 0

    def test_symlink_target_is_replaced_not_followed(self, world: dict[str, Path], tmp_path: Path) -> None:
        """
        Test that a symlinked settings file becomes a real file and its link target is untouched
        """
        other = tmp_path / 'elsewhere.json'
        other.write_text('{"theme": "dark"}', encoding='utf-8')
        _claude(world).parent.mkdir(parents=True)
        _claude(world).symlink_to(other)
        _fragment(world['repo'], 'claude', {'theme': 'dark', 'verbose': True})
        assert _run(world, 'claude', '--force') == 0
        assert not _claude(world).is_symlink()
        assert json.loads(other.read_text(encoding='utf-8')) == {'theme': 'dark'}

    def test_check_and_diff_do_not_write(self, world: dict[str, Path], capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that --check reports out-of-sync and --diff previews, neither writing
        """
        _fragment(world['repo'], 'claude', {'theme': 'dark'})
        assert _run(world, 'claude', '--check') == 1
        assert _run(world, 'claude', '--diff') == 0
        assert '"theme": "dark"' in capsys.readouterr().out
        assert not _claude(world).exists()
        assert _run(world, 'claude') == 0
        assert _run(world, 'claude', '--check') == 0

    def test_target_without_fragments_is_skipped(self, world: dict[str, Path]) -> None:
        """
        Test that a target no layer provides is skipped successfully
        """
        assert _run(world, 'vscode') == 0
        assert not (world['home'] / 'Library').exists()

    def test_invalid_fragment_is_config_error(self, world: dict[str, Path]) -> None:
        """
        Test that malformed fragment JSON exits 2
        """
        (world['repo'] / 'render' / 'claude.json').write_text('{nope', encoding='utf-8')
        assert _run(world, 'claude') == 2

    def test_unknown_target_is_config_error(self, world: dict[str, Path]) -> None:
        """
        Test that an unknown target id exits 2
        """
        assert _run(world, 'nope') == 2

    def test_missing_overlay_is_config_error(self, world: dict[str, Path], tmp_path: Path) -> None:
        """
        Test that a registered missing overlay exits 2
        """
        (tmp_path / 'overlays').write_text(f'{tmp_path / "gone"}\n', encoding='utf-8')
        _fragment(world['repo'], 'claude', {'theme': 'dark'})
        assert _run(world, 'claude') == 2
