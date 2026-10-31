"""
Unit tests for stow.sh (layered stow driver)
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Inherited variables that would leak the developer's own configuration into the tests
_SCRUBBED_VARS: tuple[str, ...] = (
    'DOTFILES_OS',
    'DOTFILES_REPO',
    'DOTFILES_BREW_PREFIXES',
    'DOTFILES_LEAK_PATTERNS',
    'DOTFILES_OVERLAYS_FILE',
    'STOW_VERBOSE',
)

pytestmark = pytest.mark.skipif(
    shutil.which('stow') is None,
    reason='GNU Stow not installed',
)


@pytest.fixture
def world(tmp_path: Path, shell: str) -> dict[str, Path]:
    """
    Fixture repo (copy of the engine files), overlay, HOME, overlays registry, and the bash interpreter under test
    """
    repo = tmp_path / 'repo'
    (repo / 'bootstrap').mkdir(parents=True)
    (repo / 'scripts' / 'utility').mkdir(parents=True)

    shutil.copy2(REPO_ROOT / 'stow.sh', repo / 'stow.sh')
    shutil.copy2(REPO_ROOT / 'bootstrap' / 'lib.sh', repo / 'bootstrap' / 'lib.sh')
    shutil.copy2(REPO_ROOT / 'scripts' / 'utility' / 'summarize_stow.awk', repo / 'scripts' / 'utility')

    (repo / 'scripts' / 'dotfiles').mkdir()
    shutil.copy2(REPO_ROOT / 'scripts' / 'dotfiles' / 'render.py', repo / 'scripts' / 'dotfiles')

    overlay = tmp_path / 'overlay'
    (overlay / 'stow').mkdir(parents=True)

    home = tmp_path / 'home'
    home.mkdir()

    return {
        'repo':     repo,
        'overlay':  overlay,
        'home':     home,
        'registry': tmp_path / 'overlays',
        'shell':    Path(shell),
    }


def _pkg(layer: Path, pkg: str, files: dict[str, str]) -> None:
    """
    Create a stow package with the given $HOME-relative files
    """
    for rel, content in files.items():
        path = layer / 'stow' / pkg / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')


def _stow(
    world: dict[str, Path],
    *args: str,
    register_overlay: bool = True,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """
    Run the fixture repo's stow.sh (under the parametrized bash) with an isolated HOME
    """
    if register_overlay:
        world['registry'].write_text(f'{world["overlay"]}\n', encoding='utf-8')

    env: dict[str, str] = {
        **{key: value for key, value in os.environ.items() if key not in _SCRUBBED_VARS},
        'HOME':                   str(world['home']),
        'XDG_CONFIG_HOME':        str(world['home'] / '.config'),
        'DOTFILES_OVERLAYS_FILE': str(world['registry']),
        **(extra_env or {}),
    }
    return subprocess.run(
        [str(world['shell']), str(world['repo'] / 'stow.sh'), *args],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def _foreign_symlink(world: dict[str, Path], name: str) -> Path:
    """
    Create $HOME/<name> as an absolute symlink to a directory outside every stow layer (an old checkout's link)
    """
    elsewhere = world['home'].parent / 'old-checkout'
    elsewhere.mkdir(exist_ok=True)

    link = world['home'] / name
    link.symlink_to(elsewhere)
    return link


def _tree(root: Path) -> list[str]:
    """
    Snapshot every path under root (symlinks not followed) as a sorted list of relative names
    """
    return sorted(str(path.relative_to(root)) for path in root.rglob('*'))


class TestDiscovery:
    """
    Tests for package discovery across layers
    """
    def test_list_shows_packages_with_layers(self, world: dict[str, Path]) -> None:
        """
        Test that --list prints base packages, then overlay packages, with their layer roots
        """
        _pkg(world['repo'],    'shell',      {'.zshrc': 'x'})
        _pkg(world['overlay'], 'work-shell', {'.config/zsh/conf.d/31-work.zsh': 'x'})

        result = _stow(world, '--list')
        assert result.returncode == 0, result.stderr
        assert result.stdout.splitlines() == [
            f'shell\t{world["repo"].resolve()}',
            f'work-shell\t{world["overlay"].resolve()}',
        ]

    def test_inherited_dotfiles_repo_does_not_redirect_base_layer(self, world: dict[str, Path], tmp_path: Path) -> None:
        """
        Test that an exported DOTFILES_REPO from another checkout cannot change which base layer is used
        """
        _pkg(world['repo'], 'shell', {'.zshrc': 'x'})

        decoy = tmp_path / 'decoy'
        _pkg(decoy, 'decoy-pkg', {'.decoyrc': 'x'})

        result = _stow(world, '--list', extra_env={'DOTFILES_REPO': str(decoy)})
        assert result.returncode == 0, result.stderr
        assert result.stdout.splitlines() == [
            f'shell\t{world["repo"].resolve()}',
        ]

    def test_duplicate_package_name_fails(self, world: dict[str, Path]) -> None:
        """
        Test that a package name defined in two layers is rejected
        """
        _pkg(world['repo'],    'shell', {'.zshrc': 'x'})
        _pkg(world['overlay'], 'shell', {'.zprofile': 'x'})

        result = _stow(world, '--list')
        assert result.returncode == 1
        assert "package 'shell' is defined in two layers" in result.stderr

    def test_unknown_package_fails(self, world: dict[str, Path]) -> None:
        """
        Test that requesting an unknown package is an error
        """
        _pkg(world['repo'], 'shell', {'.zshrc': 'x'})

        result = _stow(world, 'nope')
        assert result.returncode == 1
        assert 'unknown package: nope' in result.stderr
        assert not (world['home'] / '.zshrc').exists()

    def test_missing_overlay_fails(self, world: dict[str, Path]) -> None:
        """
        Test that a registered but missing overlay aborts before stowing
        """
        _pkg(world['repo'], 'shell', {'.zshrc': 'x'})
        world['registry'].write_text(f'{world["overlay"] / "gone"}\n', encoding='utf-8')

        result = _stow(world, register_overlay=False)
        assert result.returncode == 1
        assert not (world['home'] / '.zshrc').exists()

    def test_unreadable_overlay_fails_list(self, world: dict[str, Path], unreadable_overlay: Path) -> None:
        """
        Test that an overlay that exists but cannot be entered aborts --list instead of being skipped
        """
        _pkg(world['repo'], 'shell', {'.zshrc': 'x'})
        world['registry'].write_text(f'{unreadable_overlay}\n{world["overlay"]}\n', encoding='utf-8')

        result = _stow(world, '--list', register_overlay=False)
        assert result.returncode != 0
        assert f'cannot resolve overlay: {unreadable_overlay}' in result.stderr

    def test_repeated_package_names_are_stowed_once(self, world: dict[str, Path]) -> None:
        """
        Test that naming a package twice selects it once
        """
        _pkg(world['repo'], 'shell', {'.zshrc': 'x'})

        result = _stow(world, 'shell', 'shell')
        assert result.returncode == 0, result.stderr
        assert 'stow: applied shell\n' in result.stdout


class TestCli:
    """
    Tests for argument and environment handling
    """
    def test_help_works_with_broken_registry(self, world: dict[str, Path]) -> None:
        """
        Test that --help prints usage without needing a valid overlay registry
        """
        world['registry'].write_text(f'{world["overlay"] / "gone"}\n', encoding='utf-8')

        result = _stow(world, '--help', register_overlay=False)
        assert result.returncode == 0, result.stderr
        assert 'Usage: stow.sh' in result.stdout

    def test_combined_short_flags_are_rejected(self, world: dict[str, Path]) -> None:
        """
        Test that a short-flag cluster such as -nv is an error instead of being forwarded to stow
        """
        _pkg(world['repo'], 'shell', {'.zshrc': 'x'})

        result = _stow(world, '-nv')
        assert result.returncode == 1
        assert 'combined short flags' in result.stderr
        assert not (world['home'] / '.zshrc').exists()

    @pytest.mark.parametrize('flag', ['--adopt', '-D', '--target=x', '--dir=x', '--ignore=x', '--no'])
    def test_unknown_flags_are_rejected(self, world: dict[str, Path], flag: str) -> None:
        """
        Test that a flag outside the documented set is an error instead of being forwarded to stow
        """
        _pkg(world['repo'], 'shell', {'.zshrc': 'x'})
        (world['home'] / '.zshrc').write_text('home', encoding='utf-8')

        before = _tree(world['repo'])
        result = _stow(world, flag)

        assert result.returncode == 1
        assert f'unknown option: {flag}' in result.stderr
        assert 'applied'             not in result.stdout

        assert (world['home'] / '.zshrc').read_text(encoding='utf-8') == 'home'
        assert (world['repo'] / 'stow' / 'shell' / '.zshrc').read_text(encoding='utf-8') == 'x'
        assert _tree(world['repo']) == before

    @pytest.mark.parametrize('value', ['abc', '-1', '1.5'])
    def test_non_numeric_stow_verbose_is_rejected(self, world: dict[str, Path], value: str) -> None:
        """
        Test that STOW_VERBOSE must be a non-negative integer
        """
        _pkg(world['repo'], 'shell', {'.zshrc': 'x'})

        result = _stow(world, extra_env={'STOW_VERBOSE': value})
        assert result.returncode == 1
        assert 'STOW_VERBOSE' in result.stderr


class TestOwnership:
    """
    Tests for single ownership of $HOME paths
    """
    def test_package_providing_a_render_target_fails(self, world: dict[str, Path]) -> None:
        """
        Test that a package shipping a file render.py writes is rejected before anything is linked
        """
        _pkg(world['repo'],    'shell',  {'.zshrc': 'x'})
        _pkg(world['overlay'], 'claude', {'.claude/settings.json': '{}', '.claude/rules/a.md': 'x'})

        result = _stow(world)
        assert result.returncode == 1
        assert 'written by scripts/dotfiles/render.py' in result.stderr
        assert '~/.claude/settings.json <- claude'     in result.stderr
        assert not (world['home'] / '.zshrc').exists()

    def test_package_providing_a_render_target_parent_fails(self, world: dict[str, Path], tmp_path: Path) -> None:
        """
        Test that a package linking a path above a render target (which would carry the target into the repo) fails
        """
        elsewhere = tmp_path / 'elsewhere'
        elsewhere.mkdir()

        package = world['repo'] / 'stow' / 'claude-link'
        package.mkdir(parents=True)
        (package / '.claude').symlink_to(elsewhere)

        result = _stow(world)
        assert result.returncode == 1
        assert '~/.claude/settings.json <- claude-link' in result.stderr

    def test_other_files_beside_a_render_target_are_allowed(self, world: dict[str, Path]) -> None:
        """
        Test that a package may provide siblings of a render target, such as files under ~/.claude/
        """
        _pkg(world['repo'], 'claude', {'.claude/rules/a.md': 'x', '.claude/settings.local.json': '{}'})

        result = _stow(world)
        assert result.returncode == 0, result.stderr
        assert (world['home'] / '.claude' / 'rules' / 'a.md').is_symlink()

    def test_empty_render_target_list_fails(self, world: dict[str, Path]) -> None:
        """
        Test that a render.py which lists no targets aborts the run instead of silently skipping the ownership check
        """
        (world['repo'] / 'scripts' / 'dotfiles' / 'render.py').write_text('', encoding='utf-8')
        _pkg(world['repo'], 'shell', {'.zshrc': 'x'})

        result = _stow(world)
        assert result.returncode == 1
        assert 'render targets' in result.stderr
        assert 'empty'          in result.stderr
        assert not (world['home'] / '.zshrc').exists()

    def test_two_packages_same_path_fails_before_linking(self, world: dict[str, Path]) -> None:
        """
        Test that two packages providing one path abort the run and name both owners
        """
        _pkg(world['repo'],    'shell',      {'.zshrc': 'a', '.zprofile': 'a'})
        _pkg(world['overlay'], 'work-shell', {'.zshrc': 'b'})

        result = _stow(world)
        assert result.returncode == 1
        assert '~/.zshrc <- shell,work-shell' in result.stderr
        assert not (world['home'] / '.zprofile').exists()

    def test_file_versus_directory_collision_fails(self, world: dict[str, Path]) -> None:
        """
        Test that one package providing a path as a file and another providing files beneath it is rejected
        """
        _pkg(world['repo'],    'a-pkg', {'.config/app': 'file', '.zshrc': 'x'})
        _pkg(world['overlay'], 'b-pkg', {'.config/app/settings': 'nested'})

        result = _stow(world)
        assert result.returncode == 1
        assert '~/.config/app <- a-pkg (file), b-pkg (directory)' in result.stderr
        assert not (world['home'] / '.zshrc').exists()

    def test_collision_check_covers_unselected_packages(self, world: dict[str, Path]) -> None:
        """
        Test that ownership is checked across all packages even when only one is requested
        """
        _pkg(world['repo'],    'shell',      {'.zshrc': 'a'})
        _pkg(world['overlay'], 'work-shell', {'.zshrc': 'b'})

        result = _stow(world, 'shell')
        assert result.returncode == 1
        assert '~/.zshrc <- shell,work-shell' in result.stderr

    def test_readme_at_package_root_is_ignored(self, world: dict[str, Path]) -> None:
        """
        Test that package-root README files (ignored by stow) do not count as owned paths
        """
        _pkg(world['repo'],    'shell',      {'README.md': 'docs', '.zshrc': 'x'})
        _pkg(world['overlay'], 'work-shell', {'README.md': 'docs'})
        assert _stow(world).returncode == 0

    def test_nested_readme_is_not_ignored(self, world: dict[str, Path]) -> None:
        """
        Test that stow's README ignore is root-only, so a nested README still counts as an owned path
        """
        _pkg(world['repo'],    'a-pkg', {'.config/app/README.md': 'a'})
        _pkg(world['overlay'], 'b-pkg', {'.config/app/README.md': 'b'})

        result = _stow(world)
        assert result.returncode == 1
        assert '~/.config/app/README.md <- a-pkg,b-pkg' in result.stderr

    def test_ds_store_is_ignored_everywhere(self, world: dict[str, Path]) -> None:
        """
        Test that .DS_Store files neither collide across packages nor get linked
        """
        _pkg(world['repo'],    'a-pkg', {'.DS_Store': 'a', '.config/app/.DS_Store': 'a', '.config/app/f': 'a'})
        _pkg(world['overlay'], 'b-pkg', {'.DS_Store': 'b', '.bashrc': 'b'})

        result = _stow(world)
        assert result.returncode == 0, result.stderr
        assert (world['home'] / '.config' / 'app' / 'f').is_symlink()
        assert not (world['home'] / '.DS_Store').exists()
        assert not (world['home'] / '.config' / 'app' / '.DS_Store').exists()

    def test_backups_directories_are_ignored_everywhere(self, world: dict[str, Path]) -> None:
        """
        Test that .backups directories neither collide across packages nor get linked
        """
        _pkg(world['repo'],    'a-pkg', {'.claude/.backups/CLAUDE.md.1.bak': 'a', '.claude/CLAUDE.md':  'a'})
        _pkg(world['overlay'], 'b-pkg', {'.claude/.backups/CLAUDE.md.1.bak': 'b', '.claude/rules/r.md': 'b'})

        result = _stow(world)
        assert result.returncode == 0, result.stderr
        assert (world['home'] / '.claude' / 'CLAUDE.md').is_symlink()
        assert not (world['home'] / '.claude' / '.backups').exists()

    def test_copying_txt_at_package_root_is_counted_but_copying_is_not(self, world: dict[str, Path]) -> None:
        """
        Test that only an exact COPYING at the package root is ignored, matching stow's built-in rules
        """
        _pkg(world['repo'],    'a-pkg', {'COPYING': 'a', 'COPYING.txt': 'a'})
        _pkg(world['overlay'], 'b-pkg', {'COPYING': 'b'})

        result = _stow(world)
        assert result.returncode == 0, result.stderr
        assert (world['home'] / 'COPYING.txt').is_symlink()
        assert not (world['home'] / 'COPYING').exists()

        _pkg(world['overlay'], 'c-pkg', {'COPYING.txt': 'c'})
        clash = _stow(world)
        assert clash.returncode == 1
        assert '~/COPYING.txt <- a-pkg,c-pkg' in clash.stderr


class TestLinking:
    """
    Tests for linking behavior
    """
    def test_layers_share_real_directories(self, world: dict[str, Path]) -> None:
        """
        Test that base and overlay files land in one real (unfolded) directory
        """
        _pkg(world['repo'],    'shell',      {'.config/zsh/conf.d/00-lib.zsh':  'base'})
        _pkg(world['overlay'], 'work-shell', {'.config/zsh/conf.d/31-work.zsh': 'work'})

        result = _stow(world)
        assert result.returncode == 0, result.stderr

        conf_d = world['home'] / '.config' / 'zsh' / 'conf.d'
        assert conf_d.is_dir()
        assert not conf_d.is_symlink()
        assert (conf_d / '00-lib.zsh').is_symlink()
        assert (conf_d / '31-work.zsh').read_text(encoding='utf-8') == 'work'
        assert 'stow: applied' in result.stdout

    def test_single_package_directory_is_not_folded(self, world: dict[str, Path]) -> None:
        """
        Test that a directory owned by one package is still a real directory
        """
        _pkg(world['repo'], 'tmux', {'.config/tmux/tmux.conf': 'x'})
        assert _stow(world).returncode == 0
        assert not (world['home'] / '.config' / 'tmux').is_symlink()

    def test_restow_is_idempotent(self, world: dict[str, Path]) -> None:
        """
        Test that a second run reports no changes
        """
        _pkg(world['repo'], 'shell', {'.zshrc': 'x'})
        assert _stow(world).returncode == 0

        second = _stow(world)
        assert second.returncode == 0
        assert 'no changes' in second.stdout

    def test_dry_run_writes_nothing(self, world: dict[str, Path]) -> None:
        """
        Test that -n simulates without creating links
        """
        _pkg(world['repo'], 'shell', {'.zshrc': 'x'})

        result = _stow(world, '-n')
        assert result.returncode == 0
        assert not (world['home'] / '.zshrc').exists()
        assert 'stow: simulated shell (dry-run, no changes written)' in result.stdout


class TestConflicts:
    """
    Tests for all-or-nothing conflict handling
    """
    def test_backupable_conflicts_without_flag_abort_untouched(self, world: dict[str, Path]) -> None:
        """
        Test that file and foreign-symlink conflicts abort with a hint and change nothing
        """
        _pkg(world['repo'], 'shell', {'.zshrc': 'repo', '.foreign': 'repo', '.fresh': 'repo'})
        (world['home'] / '.zshrc').write_text('old', encoding='utf-8')
        _foreign_symlink(world, '.foreign')

        before = _tree(world['home'])
        result = _stow(world)
        assert result.returncode == 1

        assert '--backup-conflicts' in result.stderr
        assert '.zshrc'             in result.stderr
        assert '.foreign'           in result.stderr

        assert _tree(world['home']) == before
        assert (world['home'] / '.zshrc').read_text(encoding='utf-8') == 'old'
        assert not (world['home'] / '.fresh').exists()

    def test_dry_run_with_backup_lists_every_would_back_up(self, world: dict[str, Path]) -> None:
        """
        Test that -n --backup-conflicts previews each move, exits 0, and moves nothing
        """
        _pkg(world['repo'], 'shell', {'.zshrc': 'repo', '.foreign': 'repo'})
        (world['home'] / '.zshrc').write_text('old', encoding='utf-8')
        _foreign_symlink(world, '.foreign')

        before = _tree(world['home'])
        result = _stow(world, '-n', '--backup-conflicts')
        assert result.returncode == 0, result.stderr

        assert 'stow: would back up existing .zshrc -> '                     in result.stdout
        assert 'stow: would back up existing .foreign -> '                   in result.stdout
        assert '2 conflicting file(s) would be backed up first, then linked' in result.stdout

        assert _tree(world['home']) == before
        assert (world['home'] / '.zshrc').read_text(encoding='utf-8') == 'old'

    def test_backup_conflicts_moves_files_and_foreign_symlinks(self, world: dict[str, Path]) -> None:
        """
        Test that --backup-conflicts moves a blocking file and a foreign symlink aside, then links both
        """
        _pkg(world['repo'], 'shell', {'.zshrc': 'repo', '.foreign': 'repo'})
        (world['home'] / '.zshrc').write_text('old', encoding='utf-8')

        foreign = _foreign_symlink(world, '.foreign')
        target  = foreign.readlink()
        result  = _stow(world, '--backup-conflicts')
        assert result.returncode == 0, result.stderr

        assert (world['home'] / '.zshrc').is_symlink()
        assert (world['home'] / '.foreign').is_symlink()
        assert (world['home'] / '.foreign').readlink() != target

        zshrc_backups   = list((world['home'] / '.dotfiles-backup').glob('*/.zshrc'))
        foreign_backups = list((world['home'] / '.dotfiles-backup').glob('*/.foreign'))

        assert len(zshrc_backups) == 1
        assert zshrc_backups[0].read_text(encoding='utf-8') == 'old'
        assert len(foreign_backups) == 1
        assert foreign_backups[0].is_symlink()
        assert foreign_backups[0].readlink() == target
        assert 'stow: applied shell' in result.stdout

    def test_unresolvable_conflict_changes_nothing(self, world: dict[str, Path]) -> None:
        """
        Test that a real directory where a package provides a file aborts without moving backup-able siblings
        """
        _pkg(world['repo'], 'shell', {'.zshrc': 'repo', '.config/app': 'repo', '.fresh': 'repo'})
        (world['home'] / '.zshrc').write_text('old', encoding='utf-8')
        (world['home'] / '.config' / 'app').mkdir(parents=True)

        before = _tree(world['home'])
        result = _stow(world, '--backup-conflicts')
        assert result.returncode == 1

        assert '.config/app' in result.stderr
        assert _tree(world['home']) == before
        assert (world['home'] / '.zshrc').read_text(encoding='utf-8') == 'old'
        assert not (world['home'] / '.dotfiles-backup').exists()

    def test_unresolvable_conflict_aborts_dry_run_too(self, world: dict[str, Path]) -> None:
        """
        Test that an unresolvable conflict is a failure even when simulating
        """
        _pkg(world['repo'], 'shell', {'.config/app': 'repo'})
        (world['home'] / '.config' / 'app').mkdir(parents=True)
        result = _stow(world, '-n', '--backup-conflicts')
        assert result.returncode == 1

    def test_conflict_in_overlay_leaves_base_unlinked(self, world: dict[str, Path]) -> None:
        """
        Test that a conflict in a later layer prevents any earlier layer from being linked
        """
        _pkg(world['repo'],    'shell',      {'.zshrc': 'repo'})
        _pkg(world['overlay'], 'work-shell', {'.workrc': 'overlay'})
        (world['home'] / '.workrc').write_text('old', encoding='utf-8')

        result = _stow(world)
        assert result.returncode == 1
        assert not (world['home'] / '.zshrc').exists()
        assert (world['home'] / '.workrc').read_text(encoding='utf-8') == 'old'

    def test_unresolvable_conflict_in_overlay_leaves_base_unlinked(self, world: dict[str, Path]) -> None:
        """
        Test that an unresolvable overlay conflict blocks the base layer even with --backup-conflicts
        """
        _pkg(world['repo'],    'shell',      {'.zshrc': 'repo', '.bashrc': 'repo'})
        _pkg(world['overlay'], 'work-shell', {'.workrc': 'overlay'})

        (world['home'] / '.bashrc').write_text('old', encoding='utf-8')
        (world['home'] / '.workrc').mkdir()

        result = _stow(world, '--backup-conflicts')
        assert result.returncode == 1
        assert not (world['home'] / '.zshrc').exists()
        assert (world['home'] / '.bashrc').read_text(encoding='utf-8') == 'old'

    def test_failed_reverify_links_nothing_and_names_backup_dir(self, world: dict[str, Path], tmp_path: Path) -> None:
        """
        Test that a still-dirty re-verification after backup exits 1 without linking and reports the backup directory
        """
        _pkg(world['repo'], 'shell', {'.zshrc': 'repo', '.fresh': 'repo'})
        (world['home'] / '.zshrc').write_text('old', encoding='utf-8')

        real_stow = shutil.which('stow')
        assert real_stow is not None

        shim_dir = tmp_path / 'shim'
        shim_dir.mkdir()

        # Once a backup directory exists, every simulated stow reports a fresh unresolvable conflict
        shim = shim_dir / 'stow'
        shim.write_text(
            '#!/bin/sh\n'
            'if [ -d "$HOME/.dotfiles-backup" ]; then\n'
            '    echo "WARNING! stowing shell would cause conflicts:"\n'
            '    echo "  * simulated residual conflict: .zshrc"\n'
            '    echo "All operations aborted."\n'
            '    exit 1\n'
            'fi\n'
            f'exec "{real_stow}" "$@"\n',
            encoding='utf-8',
        )
        shim.chmod(shim.stat().st_mode | stat.S_IXUSR)

        result = _stow(world, '--backup-conflicts', extra_env={'PATH': f'{shim_dir}{os.pathsep}{os.environ["PATH"]}'})
        assert result.returncode == 1
        assert str(world['home'] / '.dotfiles-backup') in result.stderr
        assert not (world['home'] / '.fresh').exists()

        backups = list((world['home'] / '.dotfiles-backup').glob('*/.zshrc'))
        assert len(backups) == 1
        assert backups[0].read_text(encoding='utf-8') == 'old'


def _marker(layer: Path, pkg: str, text: str) -> None:
    """
    Write a package's .dotfiles-os marker verbatim
    """
    path = layer / 'stow' / pkg / '.dotfiles-os'
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as handle:
        handle.write(text)


class TestOsMarkers:
    """
    Tests for per-package .dotfiles-os markers
    """
    def test_excluded_package_is_not_linked(self, world: dict[str, Path]) -> None:
        """
        Test that a darwin-only package is skipped on linux while unmarked packages are linked
        """
        _pkg(world['repo'],    'shell', {'.zshrc': 'x'})
        _pkg(world['repo'],    'mac',   {'.macrc': 'x'})
        _marker(world['repo'], 'mac',   'darwin\n')

        result = _stow(world, extra_env={'DOTFILES_OS': 'linux'})
        assert result.returncode == 0, result.stderr
        assert (world['home'] / '.zshrc').is_symlink()
        assert not (world['home'] / '.macrc').exists()

    def test_included_package_is_linked_without_its_marker(self, world: dict[str, Path]) -> None:
        """
        Test that a darwin-only package is linked on darwin and the marker file itself is not
        """
        _pkg(world['repo'],    'mac', {'.macrc': 'x'})
        _marker(world['repo'], 'mac', 'darwin\n')

        result = _stow(world, extra_env={'DOTFILES_OS': 'darwin'})
        assert result.returncode == 0, result.stderr
        assert (world['home'] / '.macrc').is_symlink()
        assert not (world['home'] / '.dotfiles-os').exists()

    def test_list_omits_excluded_packages(self, world: dict[str, Path]) -> None:
        """
        Test that --list shows only the packages that apply to this OS
        """
        _pkg(world['repo'],    'shell', {'.zshrc': 'x'})
        _pkg(world['repo'],    'mac',   {'.macrc': 'x'})
        _marker(world['repo'], 'mac',   'darwin\n')

        result = _stow(world, '--list', extra_env={'DOTFILES_OS': 'linux'})
        assert result.returncode == 0, result.stderr
        assert result.stdout.splitlines() == [f'shell\t{world["repo"].resolve()}']

    def test_requesting_an_excluded_package_fails(self, world: dict[str, Path]) -> None:
        """
        Test that naming an excluded package explains why instead of calling it unknown
        """
        _pkg(world['repo'],    'mac', {'.macrc': 'x'})
        _marker(world['repo'], 'mac', 'darwin\n')

        result = _stow(world, 'mac', extra_env={'DOTFILES_OS': 'linux'})
        assert result.returncode != 0
        assert "package 'mac' does not apply to linux (see its .dotfiles-os)" in result.stderr

    @pytest.mark.parametrize(
        ('text', 'message'),
        [
            ('macos\n',          "unknown OS 'macos'"),
            ('# nothing here\n', 'lists no OS'),
        ],
    )
    def test_invalid_marker_fails(self, world: dict[str, Path], text: str, message: str) -> None:
        """
        Test that an unknown OS id or an empty marker is fatal before anything is linked
        """
        _pkg(world['repo'], 'shell', {'.zshrc': 'x'})
        _pkg(world['repo'], 'odd',   {'.oddrc': 'x'})
        _marker(world['repo'], 'odd', text)

        result = _stow(world, extra_env={'DOTFILES_OS': 'linux'})
        assert result.returncode != 0
        assert message in result.stderr
        assert not (world['home'] / '.zshrc').exists()

    def test_comments_whitespace_and_crlf_are_tolerated(self, world: dict[str, Path]) -> None:
        """
        Test that a marker with comments, padding, and CRLF line endings parses
        """
        _pkg(world['repo'],    'both', {'.bothrc': 'x'})
        _marker(world['repo'], 'both', '# both platforms\r\n  darwin  # mac\r\nlinux\r\n')

        result = _stow(world, extra_env={'DOTFILES_OS': 'linux'})
        assert result.returncode == 0, result.stderr
        assert (world['home'] / '.bothrc').is_symlink()

    def test_os_variants_may_provide_the_same_path(self, world: dict[str, Path]) -> None:
        """
        Test that a darwin package and a linux package may own the same path, and the matching one is linked
        """
        _pkg(world['repo'],    'tool-darwin', {'.config/tool/config': 'mac'})
        _pkg(world['repo'],    'tool-linux',  {'.config/tool/config': 'linux'})
        _marker(world['repo'], 'tool-darwin', 'darwin\n')
        _marker(world['repo'], 'tool-linux',  'linux\n')

        result = _stow(world, extra_env={'DOTFILES_OS': 'linux'})
        assert result.returncode == 0, result.stderr
        assert (world['home'] / '.config' / 'tool' / 'config').read_text(encoding='utf-8') == 'linux'

    def test_duplicate_name_fails_even_when_one_copy_is_excluded(self, world: dict[str, Path]) -> None:
        """
        Test that the one-layer-per-package-name rule also covers excluded packages
        """
        _pkg(world['repo'],    'mac', {'.macrc': 'x'})
        _pkg(world['overlay'], 'mac', {'.macrc2': 'x'})
        _marker(world['repo'], 'mac', 'darwin\n')

        result = _stow(world, extra_env={'DOTFILES_OS': 'linux'})
        assert result.returncode != 0
        assert "package 'mac' is defined in two layers" in result.stderr

    def test_moving_a_file_between_packages_relinks_it(self, world: dict[str, Path]) -> None:
        """
        Test that a file moved from one package to another is relinked on the next run (the stale link is cleaned up)
        """
        _pkg(world['repo'], 'old', {'.config/app/config': 'x', '.oldrc': 'x'})
        assert _stow(world).returncode == 0

        moved = world['repo'] / 'stow' / 'new' / '.config' / 'app' / 'config'
        moved.parent.mkdir(parents=True)

        (world['repo'] / 'stow' / 'old' / '.config' / 'app' / 'config').rename(moved)
        shutil.rmtree(world['repo'] / 'stow' / 'old' / '.config')

        result = _stow(world)
        assert result.returncode == 0, result.stderr

        link = world['home'] / '.config' / 'app' / 'config'
        assert link.is_symlink()
        assert link.resolve() == moved.resolve()
