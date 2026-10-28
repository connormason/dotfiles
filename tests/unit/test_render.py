"""
Unit tests for scripts/dotfiles/render.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import stat
import subprocess
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
            ([1],                     [{'a': None, 'b': 1}], [1, {'b': 1}]),
            ([{'b': 1}],              [{'a': None, 'b': 1}], [{'b': 1}]),
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
        state = world['state'] / 'dotfiles' / 'render' / 'claude.json'
        assert state.read_text(encoding='utf-8') == render.dumps({'theme': 'dark'})

    def test_in_app_edit_is_refused(self, world: dict[str, Path], capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that a live edit since the last render blocks rendering and leaves the file untouched
        """
        _fragment(world['repo'], 'claude', {'theme': 'dark'})
        assert _run(world, 'claude') == 0
        _claude(world).write_text('{"theme": "edited"}\n', encoding='utf-8')
        _fragment(world['repo'], 'claude', {'theme': 'dark', 'verbose': True})
        capsys.readouterr()
        assert _run(world, 'claude') == 1
        assert json.loads(_claude(world).read_text(encoding='utf-8')) == {'theme': 'edited'}
        err = capsys.readouterr().err
        assert 'ERROR' in err
        assert '-  "theme": "dark"' in err
        assert '+  "theme": "edited"' in err

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
        state = world['state'] / 'dotfiles' / 'render' / 'claude.json'
        assert state.read_text(encoding='utf-8') == render.dumps({'theme': 'dark'})
        assert not (world['home'] / '.dotfiles-backup').exists()

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
        assert json.loads(_claude(world).read_text(encoding='utf-8')) == {'theme': 'dark', 'verbose': True}
        assert json.loads(other.read_text(encoding='utf-8')) == {'theme': 'dark'}
        backups = list((world['home'] / '.dotfiles-backup').glob('*/.claude/settings.json'))
        assert len(backups) == 1
        assert json.loads(backups[0].read_text(encoding='utf-8')) == {'theme': 'dark'}

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


class TestLayerResolution:
    """
    Tests for resolving layers through lib.sh robustly
    """
    def test_env_sh_output_is_not_a_layer(self, world: dict[str, Path]) -> None:
        """
        Test that text echoed by a layer env.sh never becomes a layer root
        """
        (world['overlay'] / 'bootstrap').mkdir()
        (world['overlay'] / 'bootstrap' / 'env.sh').write_text('echo NOT-A-LAYER\n', encoding='utf-8')
        resolved = [path.resolve() for path in render.layers(world['repo'])]
        assert resolved == [world['repo'].resolve(), world['overlay'].resolve()]

    def test_non_absolute_layer_line_is_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that a relative path in the layer list raises RenderError
        """
        fake = subprocess.CompletedProcess(args=[], returncode=0, stdout='relative/path\n', stderr='')
        monkeypatch.setattr(render.subprocess, 'run', lambda *_args, **_kwargs: fake)
        with pytest.raises(render.RenderError):
            render.layers(Path('/repo'))

    def test_error_text_is_stripped_of_ansi(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that escape sequences in lib.sh errors do not reach the terminal
        """
        fake = subprocess.CompletedProcess(args=[], returncode=1, stdout='', stderr='\x1b[31mboom\x1b[0m\n')
        monkeypatch.setattr(render.subprocess, 'run', lambda *_args, **_kwargs: fake)
        with pytest.raises(render.RenderError) as exc_info:
            render.layers(Path('/repo'))
        assert str(exc_info.value) == 'boom'

    def test_missing_bash_is_config_error(self, world: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that failing to launch bash exits 2 instead of raising
        """
        def _boom(*_args: object, **_kwargs: object) -> None:
            raise FileNotFoundError('bash')

        monkeypatch.setattr(render.subprocess, 'run', _boom)
        assert _run(world, 'claude') == 2


class TestAtomicWrites:
    """
    Tests for atomic, mode-preserving writes
    """
    def test_regular_file_mode_is_preserved(self, world: dict[str, Path]) -> None:
        """
        Test that re-rendering keeps a restrictive mode on an existing file
        """
        _fragment(world['repo'], 'claude', {'theme': 'dark'})
        assert _run(world, 'claude') == 0
        _claude(world).chmod(0o600)
        _fragment(world['repo'], 'claude', {'theme': 'light'})
        assert _run(world, 'claude') == 0
        assert stat.S_IMODE(_claude(world).stat().st_mode) == 0o600
        assert json.loads(_claude(world).read_text(encoding='utf-8')) == {'theme': 'light'}

    def test_symlink_target_mode_is_inherited(self, world: dict[str, Path], tmp_path: Path) -> None:
        """
        Test that replacing a symlink adopts the mode of the file it pointed to
        """
        other = tmp_path / 'elsewhere.json'
        other.write_text(render.dumps({'theme': 'dark'}), encoding='utf-8')
        other.chmod(0o600)
        _claude(world).parent.mkdir(parents=True)
        _claude(world).symlink_to(other)
        _fragment(world['repo'], 'claude', {'theme': 'dark'})
        assert _run(world, 'claude') == 0
        assert not _claude(world).is_symlink()
        assert stat.S_IMODE(_claude(world).stat().st_mode) == 0o600
        assert other.read_text(encoding='utf-8') == render.dumps({'theme': 'dark'})

    def test_no_temp_files_are_left_behind(self, world: dict[str, Path]) -> None:
        """
        Test that only the target remains in its directory after a render
        """
        _fragment(world['repo'], 'claude', {'theme': 'dark'})
        assert _run(world, 'claude') == 0
        assert [path.name for path in _claude(world).parent.iterdir()] == ['settings.json']


class TestResilientState:
    """
    Tests for corrupt or unreadable state files
    """
    @pytest.mark.parametrize('content', ['{corrupt', '', '[1, 2]'])
    def test_bad_state_adopts_identical_live_file(
        self, world: dict[str, Path], capsys: pytest.CaptureFixture[str], content: str,
    ) -> None:
        """
        Test that an unusable state file is ignored with a warning and the render proceeds
        """
        _fragment(world['repo'], 'claude', {'theme': 'dark'})
        state = world['state'] / 'dotfiles' / 'render' / 'claude.json'
        state.parent.mkdir(parents=True)
        state.write_text(content, encoding='utf-8')
        _claude(world).parent.mkdir(parents=True)
        _claude(world).write_text(render.dumps({'theme': 'dark'}), encoding='utf-8')
        assert _run(world, 'claude') == 0
        assert 'state' in capsys.readouterr().err
        assert state.read_text(encoding='utf-8') == render.dumps({'theme': 'dark'})

    @pytest.mark.parametrize('content', ['{corrupt', ''])
    def test_bad_state_with_differing_live_file_is_drift(self, world: dict[str, Path], content: str) -> None:
        """
        Test that an unusable state plus a differing live file is refused as drift, not a traceback
        """
        _fragment(world['repo'], 'claude', {'theme': 'dark'})
        state = world['state'] / 'dotfiles' / 'render' / 'claude.json'
        state.parent.mkdir(parents=True)
        state.write_text(content, encoding='utf-8')
        _claude(world).parent.mkdir(parents=True)
        _claude(world).write_text('{"theme": "edited"}\n', encoding='utf-8')
        assert _run(world, 'claude') == 1
        assert json.loads(_claude(world).read_text(encoding='utf-8')) == {'theme': 'edited'}


    @pytest.mark.skipif(os.geteuid() == 0, reason='root ignores file permissions')
    def test_unreadable_state_is_repaired(self, world: dict[str, Path], capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that an unreadable state file is rewritten 0600 so later renders are not refused as drift
        """
        _fragment(world['repo'], 'claude', {'theme': 'dark'})
        state = world['state'] / 'dotfiles' / 'render' / 'claude.json'
        state.parent.mkdir(parents=True)
        state.write_text(render.dumps({'theme': 'dark'}), encoding='utf-8')
        state.chmod(0o000)
        _claude(world).parent.mkdir(parents=True)
        _claude(world).write_text(render.dumps({'theme': 'dark'}), encoding='utf-8')
        assert _run(world, 'claude') == 0
        assert 'state' in capsys.readouterr().err
        assert stat.S_IMODE(state.stat().st_mode) == 0o600
        assert state.read_text(encoding='utf-8') == render.dumps({'theme': 'dark'})
        _fragment(world['repo'], 'claude', {'theme': 'light'})
        assert _run(world, 'claude') == 0
        assert json.loads(_claude(world).read_text(encoding='utf-8')) == {'theme': 'light'}


class TestIoErrors:
    """
    Tests that I/O problems exit 2 with an error line instead of a traceback
    """
    def test_destination_is_directory(self, world: dict[str, Path], capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that a directory at the target path exits 2
        """
        _fragment(world['repo'], 'claude', {'theme': 'dark'})
        _claude(world).mkdir(parents=True)
        assert _run(world, 'claude') == 2
        assert 'ERROR' in capsys.readouterr().err

    @pytest.mark.skipif(os.geteuid() == 0, reason='root ignores directory permissions')
    def test_read_only_destination_directory(self, world: dict[str, Path], capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that an unwritable destination directory exits 2
        """
        _fragment(world['repo'], 'claude', {'theme': 'dark'})
        _claude(world).parent.mkdir(parents=True)
        _claude(world).parent.chmod(0o500)
        try:
            assert _run(world, 'claude') == 2
        finally:
            _claude(world).parent.chmod(0o700)
        assert 'ERROR' in capsys.readouterr().err
        assert not _claude(world).exists()


class TestRiskPaths:
    """
    Tests for live-file edge cases, backups, warnings, and multi-target behavior
    """
    def test_invalid_live_json_is_refused(self, world: dict[str, Path], capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that an unparsable live file is refused and left untouched
        """
        _fragment(world['repo'], 'claude', {'theme': 'dark'})
        _claude(world).parent.mkdir(parents=True)
        _claude(world).write_text('{nope', encoding='utf-8')
        assert _run(world, 'claude') == 1
        assert _claude(world).read_text(encoding='utf-8') == '{nope'
        assert 'is not valid JSON' in capsys.readouterr().err

    def test_non_object_live_json_is_refused(self, world: dict[str, Path], capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that a live file holding a non-object is refused with an accurate message
        """
        _fragment(world['repo'], 'claude', {'theme': 'dark'})
        _claude(world).parent.mkdir(parents=True)
        _claude(world).write_text('[1, 2]', encoding='utf-8')
        assert _run(world, 'claude') == 1
        assert _claude(world).read_text(encoding='utf-8') == '[1, 2]'
        err = capsys.readouterr().err
        assert 'is not a JSON object' in err
        assert 'is not valid JSON' not in err

    def test_in_sync_symlink_is_replaced_without_force(self, world: dict[str, Path], tmp_path: Path) -> None:
        """
        Test that a symlink whose content equals the render becomes a real file without --force
        """
        other = tmp_path / 'elsewhere.json'
        other.write_text('{"theme": "dark"}', encoding='utf-8')
        _claude(world).parent.mkdir(parents=True)
        _claude(world).symlink_to(other)
        _fragment(world['repo'], 'claude', {'theme': 'dark'})
        assert _run(world, 'claude') == 0
        assert not _claude(world).is_symlink()
        assert json.loads(_claude(world).read_text(encoding='utf-8')) == {'theme': 'dark'}
        assert other.read_text(encoding='utf-8') == '{"theme": "dark"}'
        assert not (world['home'] / '.dotfiles-backup').exists()

    def test_dangling_symlink_is_replaced_and_reported(
        self, world: dict[str, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that a dangling symlink is replaced by a real file and its former target is reported
        """
        missing = tmp_path / 'missing.json'
        _claude(world).parent.mkdir(parents=True)
        _claude(world).symlink_to(missing)
        _fragment(world['repo'], 'claude', {'theme': 'dark'})
        assert _run(world, 'claude') == 0
        assert not _claude(world).is_symlink()
        assert json.loads(_claude(world).read_text(encoding='utf-8')) == {'theme': 'dark'}
        assert not missing.exists()
        assert str(missing) in capsys.readouterr().out

    def test_force_without_drift_makes_no_backup(self, world: dict[str, Path]) -> None:
        """
        Test that --force on an undrifted file does not create a backup
        """
        _fragment(world['repo'], 'claude', {'theme': 'dark'})
        assert _run(world, 'claude') == 0
        _fragment(world['repo'], 'claude', {'theme': 'light'})
        assert _run(world, 'claude', '--force') == 0
        assert json.loads(_claude(world).read_text(encoding='utf-8')) == {'theme': 'light'}
        assert not (world['home'] / '.dotfiles-backup').exists()

    def test_backups_are_private(self, world: dict[str, Path]) -> None:
        """
        Test that backup directories are 0700 and backup files are 0600
        """
        _fragment(world['repo'], 'claude', {'theme': 'dark'})
        _claude(world).parent.mkdir(parents=True)
        _claude(world).write_text('{"theme": "hand-made"}\n', encoding='utf-8')
        _claude(world).chmod(0o644)
        assert _run(world, 'claude', '--force') == 0
        root = world['home'] / '.dotfiles-backup'
        (backup,) = root.glob('*/.claude/settings.json')
        assert stat.S_IMODE(backup.stat().st_mode) == 0o600
        for directory in (root, backup.parent.parent, backup.parent):
            assert stat.S_IMODE(directory.stat().st_mode) == 0o700

    def test_check_ignores_changed_unmanaged_keys(self, world: dict[str, Path]) -> None:
        """
        Test that --check stays in sync when only an unmanaged key changes
        """
        _fragment(world['repo'], 'claude', {'theme': 'dark', '$unmanaged': ['installerHash']})
        assert _run(world, 'claude') == 0
        live = json.loads(_claude(world).read_text(encoding='utf-8'))
        live['installerHash'] = 'changed'
        _claude(world).write_text(json.dumps(live), encoding='utf-8')
        assert _run(world, 'claude', '--check') == 0

    def test_fragment_value_for_unmanaged_key_warns(
        self, world: dict[str, Path], capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that a key both set by a fragment and listed as unmanaged is dropped with a warning
        """
        _fragment(world['repo'], 'claude', {'theme': 'dark', 'owned': 'x', '$unmanaged': ['owned']})
        managed, _unmanaged = render.compose([world['repo'] / 'render' / 'claude.json'])
        assert managed == {'theme': 'dark'}
        err = capsys.readouterr().err
        assert 'owned' in err
        assert 'WARNING' in err

    def test_multi_target_exit_code_is_the_maximum(self, world: dict[str, Path]) -> None:
        """
        Test that a refused target yields exit 1 while other targets still render
        """
        _fragment(world['repo'], 'claude', {'theme': 'dark'})
        _fragment(world['repo'], 'vscode', {'editor.fontSize': 12})
        assert _run(world, 'claude') == 0
        _claude(world).write_text('{"theme": "edited"}\n', encoding='utf-8')
        assert _run(world, 'claude', 'vscode') == 1
        vscode = world['home'] / 'Library' / 'Application Support' / 'Code' / 'User' / 'settings.json'
        assert json.loads(vscode.read_text(encoding='utf-8')) == {'editor.fontSize': 12}
        assert json.loads(_claude(world).read_text(encoding='utf-8')) == {'theme': 'edited'}

    def test_bad_fragment_blocks_all_targets(self, world: dict[str, Path]) -> None:
        """
        Test that one malformed fragment exits 2 before any target is written
        """
        _fragment(world['repo'], 'claude', {'theme': 'dark'})
        (world['repo'] / 'render' / 'vscode.json').write_text('{nope', encoding='utf-8')
        assert _run(world) == 2
        assert not _claude(world).exists()
        assert not (world['state'] / 'dotfiles' / 'render').exists()


class TestListTargets:
    """
    Tests for --list-targets (the render-owned paths stow.sh refuses to link)
    """
    def test_prints_home_relative_paths(self, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that every target path is printed relative to HOME, one per line, in TARGETS order
        """
        assert render.main(['--list-targets']) == 0
        assert capsys.readouterr().out.splitlines() == [
            '.claude/settings.json',
            'Library/Application Support/Code/User/settings.json',
        ]

    def test_needs_no_layers(self, world: dict[str, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that listing works without resolving layers, so a broken registry cannot hide render ownership
        """
        (tmp_path / 'overlays').write_text(f'{tmp_path / "gone"}\n', encoding='utf-8')
        assert _run(world, '--list-targets') == 0
        assert '.claude/settings.json' in capsys.readouterr().out.splitlines()

    def test_script_entry_point(self) -> None:
        """
        Test that the script prints the list when executed directly, as stow.sh does
        """
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), '--list-targets'], capture_output=True, text=True, check=False,
        )
        assert result.returncode == 0, result.stderr
        assert len(result.stdout.splitlines()) == len(render.TARGETS)


class TestUnexpectedErrors:
    """
    Tests for crash handling in render.main
    """
    @pytest.mark.parametrize('mode', [(), ('--check',)])
    def test_crash_exits_2_with_error_line(
        self, world: dict[str, Path], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
        mode: tuple[str, ...],
    ) -> None:
        """
        Test that an unexpected exception is reported as an ERROR line and exit 2, never as drift (exit 1)
        """
        def _crash(*_args: object, **_kwargs: object) -> int:
            raise RuntimeError('kaboom')

        monkeypatch.setattr(render, 'prepare', _crash)
        assert _run(world, *mode) == 2
        err = capsys.readouterr().err
        assert 'render: ERROR: unexpected RuntimeError: kaboom' in err
        assert 'Traceback' not in err
