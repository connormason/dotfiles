"""
Unit tests for bootstrap/lib.sh
"""
from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
LIB       = REPO_ROOT / 'bootstrap' / 'lib.sh'

# Inherited variables that would leak the developer's own configuration into the tests
_SCRUBBED_VARS = ('DOTFILES_REPO', 'DOTFILES_BREW_PREFIXES', 'DOTFILES_LEAK_PATTERNS', 'DOTFILES_OVERLAYS_FILE')

BashRunner = Callable[..., 'subprocess.CompletedProcess[str]']


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    """
    Environment with an isolated HOME and overlays registry
    """
    home = tmp_path / 'home'
    home.mkdir()
    base = {key: value for key, value in os.environ.items() if key not in _SCRUBBED_VARS}
    return {
        **base,
        'HOME': str(home),
        'XDG_CONFIG_HOME': str(home / '.config'),
        'DOTFILES_OVERLAYS_FILE': str(tmp_path / 'overlays'),
        'BOOTSTRAP_DRY_RUN': '0',
    }


@pytest.fixture
def bash(shell: str, env: dict[str, str]) -> BashRunner:
    """
    Runner that sources lib.sh in a fresh bash (the parametrized shell) and then executes a script
    """
    def _run(script: str, environ: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [shell, '-c', f'source "{LIB}"\n{script}'],
            capture_output=True,
            text=True,
            check=False,
            env=environ if environ is not None else env,
            timeout=60,
        )
    return _run


def _overlay(parent: Path, name: str) -> Path:
    """
    Create an empty overlay directory
    """
    path = parent / name
    (path / 'bootstrap').mkdir(parents=True)
    return path


def _register(env: dict[str, str], content: str) -> None:
    """
    Write the overlays registry verbatim (no newline translation)
    """
    with Path(env['DOTFILES_OVERLAYS_FILE']).open('w', encoding='utf-8', newline='') as handle:
        handle.write(content)


class TestDotfilesLayers:
    """
    Tests for dotfiles_layers
    """
    def test_no_registry_prints_repo_only(self, bash: BashRunner) -> None:
        """
        Test that without an overlays file only the repo root is a layer
        """
        result = bash('dotfiles_layers')
        assert result.returncode == 0
        assert result.stdout.splitlines() == [str(REPO_ROOT)]

    def test_registry_order_comments_and_tilde(self, bash: BashRunner, env: dict[str, str], tmp_path: Path) -> None:
        """
        Test that overlays follow the repo in file order, ignoring comments and blanks and expanding ~/
        """
        first  = _overlay(tmp_path, 'first')
        second = _overlay(Path(env['HOME']), 'second')
        _register(env, f'# overlays\n\n{first}   # trailing comment\n~/second\n')
        result = bash('dotfiles_layers')
        assert result.returncode == 0
        assert result.stdout.splitlines() == [str(REPO_ROOT), str(first.resolve()), str(second.resolve())]

    def test_crlf_registry_lines(self, bash: BashRunner, env: dict[str, str], tmp_path: Path) -> None:
        """
        Test that CRLF line endings do not leak a carriage return into the overlay path
        """
        overlay = _overlay(tmp_path, 'crlf')
        _register(env, f'# overlays\r\n{overlay}\r\n')
        result = bash('dotfiles_layers')
        assert result.returncode == 0
        assert result.stdout.splitlines() == [str(REPO_ROOT), str(overlay.resolve())]

    def test_path_with_spaces(self, bash: BashRunner, env: dict[str, str], tmp_path: Path) -> None:
        """
        Test that an overlay path containing spaces is kept intact
        """
        overlay = _overlay(tmp_path, 'with space')
        _register(env, f'{overlay}\n')
        result = bash('dotfiles_layers')
        assert result.returncode == 0
        assert result.stdout.splitlines() == [str(REPO_ROOT), str(overlay.resolve())]

    def test_no_trailing_newline(self, bash: BashRunner, env: dict[str, str], tmp_path: Path) -> None:
        """
        Test that a final registry line without a newline is still read
        """
        overlay = _overlay(tmp_path, 'last')
        _register(env, f'{overlay}')
        result = bash('dotfiles_layers')
        assert result.returncode == 0
        assert result.stdout.splitlines() == [str(REPO_ROOT), str(overlay.resolve())]

    def test_missing_overlay_fails(self, bash: BashRunner, env: dict[str, str], tmp_path: Path) -> None:
        """
        Test that a registered overlay that does not exist is an error
        """
        _register(env, f'{tmp_path / "nope"}\n')
        result = bash('true')
        assert result.returncode != 0
        assert 'overlay not found' in result.stderr

    def test_relative_entry_fails(self, bash: BashRunner, env: dict[str, str]) -> None:
        """
        Test that a relative registry entry is rejected with a clear message
        """
        _register(env, 'some/relative/overlay\n')
        result = bash('true')
        assert result.returncode != 0
        assert 'overlay path must be absolute or ~/-relative: some/relative/overlay' in result.stderr

    def test_repo_root_is_canonical_through_symlink(
        self, shell: str, env: dict[str, str], tmp_path: Path,
    ) -> None:
        """
        Test that DOTFILES_REPO is the physical path even when lib.sh is sourced through a symlink
        """
        link = tmp_path / 'repo-link'
        link.symlink_to(REPO_ROOT)
        result = subprocess.run(
            [shell, '-c', f'source "{link}/bootstrap/lib.sh"\ndotfiles_layers'],
            capture_output=True,
            text=True,
            check=False,
            env=env,
            timeout=60,
        )
        assert result.returncode == 0
        assert result.stdout.splitlines() == [str(REPO_ROOT)]

    def test_preset_dotfiles_repo_is_honored(self, bash: BashRunner, env: dict[str, str], tmp_path: Path) -> None:
        """
        Test that a pre-set DOTFILES_REPO is used as the base layer
        """
        base = _overlay(tmp_path, 'fake-base')
        result = bash('dotfiles_layers', {**env, 'DOTFILES_REPO': str(base)})
        assert result.returncode == 0
        assert result.stdout.splitlines() == [str(base)]


class TestManifestFiles:
    """
    Tests for manifest_files
    """
    def test_lists_existing_fragments_in_layer_order(
        self, bash: BashRunner, env: dict[str, str], tmp_path: Path,
    ) -> None:
        """
        Test that manifest fragments are listed base first, skipping layers without the file
        """
        with_file    = _overlay(tmp_path, 'with')
        without_file = _overlay(tmp_path, 'without')
        (with_file / 'bootstrap' / 'repos.txt').write_text('x\n', encoding='utf-8')
        _register(env, f'{without_file}\n{with_file}\n')
        result = bash('manifest_files repos.txt')
        assert result.returncode == 0
        expected = [str(with_file.resolve() / 'bootstrap' / 'repos.txt')]
        if (REPO_ROOT / 'bootstrap' / 'repos.txt').exists():
            expected.insert(0, str(REPO_ROOT / 'bootstrap' / 'repos.txt'))
        assert result.stdout.splitlines() == expected

    def test_fails_when_overlay_disappears(self, bash: BashRunner, env: dict[str, str], tmp_path: Path) -> None:
        """
        Test that manifest_files returns non-zero when a registered overlay is missing at call time
        """
        script = f'printf "%s\\n" "{tmp_path / "gone"}" > "$DOTFILES_OVERLAYS_FILE"\nmanifest_files repos.txt'
        result = bash(script)
        assert result.returncode != 0
        assert 'overlay not found' in result.stderr


class TestLayerEnv:
    """
    Tests for per-layer bootstrap/env.sh
    """
    def test_overlay_env_is_sourced(self, bash: BashRunner, env: dict[str, str], tmp_path: Path) -> None:
        """
        Test that an overlay's bootstrap/env.sh is sourced when lib.sh loads
        """
        overlay = _overlay(tmp_path, 'ov')
        (overlay / 'bootstrap' / 'env.sh').write_text('export LAYER_ENV_PROBE=from-overlay\n', encoding='utf-8')
        _register(env, f'{overlay}\n')
        result = bash('printf "%s" "$LAYER_ENV_PROBE"')
        assert result.stdout == 'from-overlay'

    def test_declare_and_typeset_stay_global(self, bash: BashRunner, env: dict[str, str], tmp_path: Path) -> None:
        """
        Test that declare/typeset in an overlay env.sh are not scoped to a helper function
        """
        overlay = _overlay(tmp_path, 'decl')
        (overlay / 'bootstrap' / 'env.sh').write_text(
            'declare -x DECL_PROBE=bar\ntypeset ARR_PROBE=(a b)\n',
            encoding='utf-8',
        )
        _register(env, f'{overlay}\n')
        result = bash('printf "%s|%s" "$DECL_PROBE" "${ARR_PROBE[*]}"')
        assert result.returncode == 0
        assert result.stdout == 'bar|a b'

    def test_layer_order_base_first_later_overlay_wins(
        self, bash: BashRunner, env: dict[str, str], tmp_path: Path,
    ) -> None:
        """
        Test that env.sh files run base first and that a later overlay overrides an earlier one
        """
        base   = _overlay(tmp_path, 'base')
        first  = _overlay(tmp_path, 'first')
        second = _overlay(tmp_path, 'second')
        for name, layer in (('base', base), ('first', first), ('second', second)):
            (layer / 'bootstrap' / 'env.sh').write_text(
                f'ORDER_PROBE="${{ORDER_PROBE:-}}{name} "\nWINNER_PROBE={name}\n',
                encoding='utf-8',
            )
        _register(env, f'{first}\n{second}\n')
        result = bash('printf "%s|%s" "$ORDER_PROBE" "$WINNER_PROBE"', {**env, 'DOTFILES_REPO': str(base)})
        assert result.returncode == 0
        assert result.stdout == 'base first second |second'

    def test_env_sourcing_lib_does_not_recurse(self, bash: BashRunner, env: dict[str, str], tmp_path: Path) -> None:
        """
        Test that an env.sh which sources lib.sh again is not re-run recursively
        """
        overlay = _overlay(tmp_path, 'reenter')
        counter = tmp_path / 'counter'
        (overlay / 'bootstrap' / 'env.sh').write_text(
            f'printf x >> "{counter}"\nsource "{LIB}"\n',
            encoding='utf-8',
        )
        _register(env, f'{overlay}\n')
        result = bash('true')
        assert result.returncode == 0
        assert counter.read_text(encoding='utf-8') == 'x'


class TestEnsureBrewOnPath:
    """
    Tests for ensure_brew_on_path
    """
    @staticmethod
    def _fake_brew(tmp_path: Path) -> Path:
        """
        Create an executable fake brew under a throwaway prefix
        """
        prefix = tmp_path / 'fakebrew'
        brew   = prefix / 'bin' / 'brew'
        brew.parent.mkdir(parents=True)
        brew.write_text('#!/bin/sh\n', encoding='utf-8')
        brew.chmod(0o755)
        return prefix

    def test_extra_prefix_is_appended_once(self, bash: BashRunner, env: dict[str, str], tmp_path: Path) -> None:
        """
        Test that a DOTFILES_BREW_PREFIXES entry with bin/brew is appended (not prepended) to PATH exactly once
        """
        prefix = self._fake_brew(tmp_path)
        result = bash('printf "%s" "$PATH"', {**env, 'DOTFILES_BREW_PREFIXES': str(prefix)})
        assert result.returncode == 0
        entries = result.stdout.split(':')
        assert entries.count(f'{prefix}/bin') == 1
        assert result.stdout.endswith(f':{prefix}/bin:{prefix}/sbin')
        assert entries[0] != f'{prefix}/bin'

    def test_prefix_already_on_path_is_not_duplicated(
        self, bash: BashRunner, env: dict[str, str], tmp_path: Path,
    ) -> None:
        """
        Test that a prefix whose bin is already on PATH is left alone
        """
        prefix  = self._fake_brew(tmp_path)
        environ = {**env, 'DOTFILES_BREW_PREFIXES': str(prefix), 'PATH': f'{prefix}/bin:{env["PATH"]}'}
        result  = bash('printf "%s" "$PATH"', environ)
        assert result.returncode == 0
        assert result.stdout.split(':').count(f'{prefix}/bin') == 1
        assert f'{prefix}/sbin' not in result.stdout

    def test_extra_prefixes_extend_defaults(self, bash: BashRunner, env: dict[str, str], tmp_path: Path) -> None:
        """
        Test that DOTFILES_BREW_PREFIXES adds to the default prefixes instead of replacing them
        """
        default = next((p for p in ('/opt/homebrew', '/usr/local') if (Path(p) / 'bin' / 'brew').exists()), None)
        if default is None:
            pytest.skip('no default Homebrew prefix on this machine')
        environ = {**env, 'DOTFILES_BREW_PREFIXES': str(tmp_path / 'no-such-prefix'), 'PATH': '/usr/bin:/bin'}
        result  = bash('printf "%s" "$PATH"', environ)
        assert result.returncode == 0
        assert f'{default}/bin' in result.stdout.split(':')

    def test_extra_prefix_wins_over_defaults(self, bash: BashRunner, env: dict[str, str], tmp_path: Path) -> None:
        """
        Test that an extra prefix is checked before the defaults and the first match wins
        """
        prefix  = self._fake_brew(tmp_path)
        environ = {**env, 'DOTFILES_BREW_PREFIXES': str(prefix), 'PATH': '/usr/bin:/bin'}
        result  = bash('printf "%s" "$PATH"', environ)
        assert result.returncode == 0
        assert result.stdout == f'/usr/bin:/bin:{prefix}/bin:{prefix}/sbin'


class TestRun:
    """
    Tests for the dry-run aware run helper
    """
    def test_run_executes_when_not_dry(self, bash: BashRunner) -> None:
        """
        Test that run executes its command normally
        """
        assert bash('run echo hello').stdout.strip() == 'hello'

    def test_run_skips_when_dry(self, bash: BashRunner, env: dict[str, str], tmp_path: Path) -> None:
        """
        Test that run only prints under BOOTSTRAP_DRY_RUN=1
        """
        marker = tmp_path / 'marker'
        result = bash(f'run touch "{marker}"', {**env, 'BOOTSTRAP_DRY_RUN': '1'})
        assert result.returncode == 0
        assert not marker.exists()
        assert '[dry-run]' in result.stdout

    def test_have(self, bash: BashRunner) -> None:
        """
        Test that have reports PATH presence
        """
        assert bash('have bash').returncode == 0
        assert bash('have definitely-not-a-command-xyz').returncode != 0
