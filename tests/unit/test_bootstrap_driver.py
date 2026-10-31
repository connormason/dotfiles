"""
Unit tests for bootstrap/bootstrap.sh (layered stage driver)
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Inherited variables that would leak the developer's own configuration into the tests
_SCRUBBED_VARS: tuple[str, ...] = (
    'BOOTSTRAP_DRY_RUN',
    'DOTFILES_REPO',
    'DOTFILES_LAYER',
    'DOTFILES_BREW_PREFIXES',
    'DOTFILES_OS',
    'DOTFILES_OVERLAYS_FILE',
    'XDG_STATE_HOME',
)


@pytest.fixture
def base(tmp_path: Path) -> Path:
    """
    A minimal base layer: the real driver and lib.sh plus one trivial stage, so no real provisioning stage ever runs
    """
    stages = tmp_path / 'base' / 'bootstrap'
    stages.mkdir(parents=True)
    for name in ('bootstrap.sh', 'lib.sh'):
        shutil.copy2(REPO_ROOT / 'bootstrap' / name, stages / name)

    (stages / '00-preflight.sh').write_text('#!/usr/bin/env bash\ntrue\n', encoding='utf-8')
    return stages.parent.resolve()


@pytest.fixture
def overlay(tmp_path: Path) -> Path:
    """
    An overlay with one passing and one failing stage
    """
    root = tmp_path / 'overlay'
    stages = root / 'bootstrap'
    stages.mkdir(parents=True)

    (stages / '98-selftest-ok.sh').write_text(
        '#!/usr/bin/env bash\n'
        'printf "%s|%s|%s" "$DOTFILES_REPO" "$DOTFILES_LAYER" "$BOOTSTRAP_DRY_RUN" > "$PROBE_FILE"\n',
        encoding='utf-8',
    )
    (stages / '99-selftest-fail.sh').write_text('#!/usr/bin/env bash\nexit 1\n', encoding='utf-8')
    return root


@pytest.fixture
def env(tmp_path: Path, overlay: Path) -> dict[str, str]:
    """
    Isolated environment with the overlay registered
    """
    registry = tmp_path / 'overlays'
    registry.write_text(f'{overlay}\n', encoding='utf-8')
    return {
        **{key: value for key, value in os.environ.items() if key not in _SCRUBBED_VARS},
        'HOME':                   str(tmp_path / 'home'),
        'DOTFILES_OVERLAYS_FILE': str(registry),
        'BOOTSTRAP_LOG_DIR':      str(tmp_path / 'state'),
        'PROBE_FILE':             str(tmp_path / 'probe'),
    }


def _drive(base: Path, shell: str, env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    """
    Run the fake base's copy of the bootstrap driver under the bash interpreter being tested
    """
    driver = base / 'bootstrap' / 'bootstrap.sh'
    return subprocess.run([shell, str(driver), *args], capture_output=True, text=True, check=False, env=env)


class TestStageDiscovery:
    """
    Tests for cross-layer stage discovery
    """
    def test_list_merges_layers_in_order(self, base: Path, shell: str, env: dict[str, str], overlay: Path) -> None:
        """
        Test that --list shows base stages first by number, then overlay stages tagged with their layer
        """
        result = _drive(base, shell, env, '--list')
        assert result.returncode == 0, result.stderr

        lines = result.stdout.splitlines()
        assert lines[0]   == '00-preflight'
        assert lines[-2:] == [f'98-selftest-ok  ({overlay.resolve()})', f'99-selftest-fail  ({overlay.resolve()})']

    def test_list_interleaves_overlay_stages_by_number(
        self,
        base: Path,
        shell: str,
        env: dict[str, str],
        overlay: Path,
    ) -> None:
        """
        Test that an overlay stage numbered between base stages sorts between them rather than after them
        """
        (overlay / 'bootstrap' / '05-overlay-early.sh').write_text('#!/usr/bin/env bash\n', encoding='utf-8')
        result = _drive(base, shell, env, '--list')
        assert result.returncode == 0, result.stderr
        assert result.stdout.splitlines()[:2] == ['00-preflight', f'05-overlay-early  ({overlay.resolve()})']

    def test_list_without_overlays_shows_base_only(
        self,
        base: Path,
        shell: str,
        env: dict[str, str],
        tmp_path: Path,
    ) -> None:
        """
        Test that with an empty registry --list shows plain stage names with no layer suffix
        """
        Path(env['DOTFILES_OVERLAYS_FILE']).write_text('', encoding='utf-8')
        result = _drive(base, shell, env, '--list')
        assert result.returncode == 0, result.stderr
        assert '00-preflight' in result.stdout.splitlines()
        assert '('        not in result.stdout

    def test_duplicate_number_across_layers_fails(
        self,
        base: Path,
        shell: str,
        env: dict[str, str],
        overlay: Path,
    ) -> None:
        """
        Test that a stage number reused by an overlay is fatal
        """
        (overlay / 'bootstrap' / '00-overlay-dup.sh').write_text('#!/usr/bin/env bash\n', encoding='utf-8')
        result = _drive(base, shell, env, '--list')

        assert result.returncode != 0
        assert 'stage number 00 is used twice'                            in result.stderr
        assert str(base / 'bootstrap' / '00-preflight.sh')                in result.stderr
        assert str(overlay.resolve() / 'bootstrap' / '00-overlay-dup.sh') in result.stderr

    def test_duplicate_number_within_overlay_fails(
        self,
        base: Path,
        shell: str,
        env: dict[str, str],
        overlay: Path,
    ) -> None:
        """
        Test that two stages sharing a number inside one overlay are fatal
        """
        (overlay / 'bootstrap' / '98-selftest-twin.sh').write_text('#!/usr/bin/env bash\n', encoding='utf-8')
        result = _drive(base, shell, env, '--list')
        assert result.returncode != 0
        assert 'stage number 98 is used twice' in result.stderr

    def test_missing_overlay_is_fatal(self, base: Path, shell: str, env: dict[str, str], tmp_path: Path) -> None:
        """
        Test that a registered overlay that does not exist aborts discovery
        """
        Path(env['DOTFILES_OVERLAYS_FILE']).write_text(f'{tmp_path / "gone"}\n', encoding='utf-8')
        result = _drive(base, shell, env, '--list')
        assert result.returncode != 0
        assert 'overlay not found' in result.stderr

    def test_unreadable_overlay_is_fatal(
        self,
        base: Path,
        shell: str,
        env: dict[str, str],
        overlay: Path,
        unreadable_overlay: Path,
    ) -> None:
        """
        Test that an overlay that exists but cannot be entered aborts discovery instead of being skipped
        """
        Path(env['DOTFILES_OVERLAYS_FILE']).write_text(f'{unreadable_overlay}\n{overlay}\n', encoding='utf-8')
        result = _drive(base, shell, env, '--list')
        assert result.returncode != 0
        assert f'cannot resolve overlay: {unreadable_overlay}' in result.stderr


class TestStageExecution:
    """
    Tests for running stages
    """
    def test_overlay_stage_gets_layer_env(
        self,
        base: Path,
        shell: str,
        env: dict[str, str],
        overlay: Path,
        tmp_path: Path,
    ) -> None:
        """
        Test that a stage sees DOTFILES_REPO (base), DOTFILES_LAYER (its own layer), and the dry-run flag
        """
        result = _drive(base, shell, env, '--dry-run', '--no-log', '--only', '98-selftest-ok')
        assert result.returncode == 0, result.stderr

        repo, layer, dry_run = (tmp_path / 'probe').read_text(encoding='utf-8').split('|')
        assert Path(repo).resolve()  == base
        assert Path(layer).resolve() == overlay.resolve()
        assert dry_run == '1'

    def test_stage_runs_under_driver_interpreter(
        self,
        base: Path,
        shell: str,
        env: dict[str, str],
        overlay: Path,
        tmp_path: Path,
    ) -> None:
        """
        Test that stages run under the bash that runs the driver, not whichever bash is first on PATH
        """
        probe = tmp_path / 'bash-version'
        (overlay / 'bootstrap' / '97-selftest-bash.sh').write_text(
            f'printf "%s" "${{BASH_VERSINFO[0]}}" > "{probe}"\n',
            encoding='utf-8',
        )

        expected = subprocess.run(
            [shell, '-c', 'printf "%s" "${BASH_VERSINFO[0]}"'],
            capture_output=True,
            text=True,
            check=True,
        ).stdout

        result = _drive(base, shell, env, '--dry-run', '--no-log', '--only', '97-selftest-bash')
        assert result.returncode == 0, result.stderr
        assert probe.read_text(encoding='utf-8') == expected
        if (shell == '/bin/bash') and (sys.platform == 'darwin'):
            assert expected == '3'

    def test_inherited_dotfiles_repo_does_not_redirect_base_layer(
        self,
        base: Path,
        shell: str,
        env: dict[str, str],
        tmp_path: Path,
    ) -> None:
        """
        Test that an exported DOTFILES_REPO from another checkout cannot change which base layer is used
        """
        elsewhere = tmp_path / 'other-checkout'
        (elsewhere / 'bootstrap').mkdir(parents=True)
        (elsewhere / 'bootstrap' / '77-impostor.sh').write_text('#!/usr/bin/env bash\n', encoding='utf-8')

        result = _drive(base, shell, {**env, 'DOTFILES_REPO': str(elsewhere)}, '--list')
        assert result.returncode == 0, result.stderr
        assert '77-impostor' not in result.stdout
        assert result.stdout.splitlines()[0] == '00-preflight'

    def test_stages_run_in_number_order(
        self,
        base: Path,
        shell: str,
        env: dict[str, str],
        overlay: Path,
        tmp_path: Path,
    ) -> None:
        """
        Test that --from runs the named stage and everything after it, in order
        """
        (overlay / 'bootstrap' / '97-selftest-first.sh').write_text('#!/usr/bin/env bash\ntrue\n', encoding='utf-8')
        result = _drive(base, shell, env, '--dry-run', '--no-log', '--from', '97-selftest-first')
        output = result.stdout

        assert result.returncode != 0
        assert '00-preflight' not in output
        assert output.index('=== stage: 97-selftest-first') < output.index('=== stage: 98-selftest-ok')
        assert output.index('=== stage: 98-selftest-ok')    < output.index('=== stage: 99-selftest-fail')

    def test_failing_stage_reports_and_hints_resume(self, base: Path, shell: str, env: dict[str, str]) -> None:
        """
        Test that a failing stage exits non-zero with a summary and a resume hint
        """
        result = _drive(base, shell, env, '--dry-run', '--no-log', '--only', '99-selftest-fail')
        output = result.stdout + result.stderr

        assert result.returncode != 0
        assert '99-selftest-fail'        in output
        assert '--from 99-selftest-fail' in output

    def test_failure_stops_later_stages(self, base: Path, shell: str, env: dict[str, str], overlay: Path) -> None:
        """
        Test that stages after a failing one are not run and the stage's exit status is propagated
        """
        early_fail = overlay / 'bootstrap' / '96-selftest-early-fail.sh'
        early_fail.write_text('#!/usr/bin/env bash\nexit 3\n', encoding='utf-8')

        result = _drive(base, shell, env, '--dry-run', '--no-log', '--from', '96-selftest-early-fail')
        assert result.returncode == 3
        assert 'failed at stage: 96-selftest-early-fail' in result.stderr
        assert '=== stage: 98-selftest-ok'           not in result.stdout
        assert not Path(env['PROBE_FILE']).exists()

    def test_unknown_only_fails(self, base: Path, shell: str, env: dict[str, str]) -> None:
        """
        Test that --only with an unknown stage is rejected
        """
        result = _drive(base, shell, env, '--only', '42-nope')
        assert result.returncode != 0
        assert 'unknown stage: 42-nope' in result.stderr

    def test_unknown_from_fails(self, base: Path, shell: str, env: dict[str, str]) -> None:
        """
        Test that --from with an unknown stage is rejected
        """
        result = _drive(base, shell, env, '--from', '42-nope')
        assert result.returncode != 0
        assert 'unknown stage: 42-nope' in result.stderr

    @pytest.mark.parametrize('flag', ['--only', '--from'])
    def test_empty_stage_value_fails(self, base: Path, shell: str, env: dict[str, str], flag: str) -> None:
        """
        Test that an empty --only/--from value is rejected instead of silently selecting every stage
        """
        result = _drive(base, shell, env, '--dry-run', '--no-log', flag, '')
        assert result.returncode != 0
        assert f'{flag} requires a non-empty stage name' in result.stderr
        assert '=== stage:' not in result.stdout

    @pytest.mark.parametrize('flag', ['--only', '--from'])
    def test_missing_stage_value_fails(self, base: Path, shell: str, env: dict[str, str], flag: str) -> None:
        """
        Test that a trailing --only/--from with no value reports the option instead of exiting silently
        """
        result = _drive(base, shell, env, '--dry-run', '--no-log', flag)
        assert result.returncode != 0
        assert f'{flag} requires a non-empty stage name' in result.stderr
        assert '=== stage:' not in result.stdout

    def test_unknown_argument_fails(self, base: Path, shell: str, env: dict[str, str]) -> None:
        """
        Test that an unrecognised flag is rejected
        """
        result = _drive(base, shell, env, '--bogus')
        assert result.returncode != 0
        assert 'unknown argument: --bogus' in result.stderr

    def test_resume_conflicts_with_only(self, base: Path, shell: str, env: dict[str, str]) -> None:
        """
        Test that --resume cannot be combined with --only
        """
        assert _drive(base, shell, env, '--resume', '--only', '98-selftest-ok').returncode != 0

    def test_resume_from_recorded_stage(self, base: Path, shell: str, env: dict[str, str]) -> None:
        """
        Test that --resume starts after the recorded last-completed stage
        """
        state = Path(env['BOOTSTRAP_LOG_DIR'])
        state.mkdir(parents=True)
        (state / 'last-completed-stage').write_text('98-selftest-ok\n', encoding='utf-8')

        result = _drive(base, shell, env, '--dry-run', '--no-log', '--resume')
        assert 'resuming from stage: 99-selftest-fail' in result.stdout + result.stderr

    def test_resume_after_final_stage_has_nothing_to_do(self, base: Path, shell: str, env: dict[str, str]) -> None:
        """
        Test that --resume after the last stage reports completion and clears the recorded state
        """
        state = Path(env['BOOTSTRAP_LOG_DIR'])
        state.mkdir(parents=True)
        (state / 'last-completed-stage').write_text('99-selftest-fail\n', encoding='utf-8')

        result = _drive(base, shell, env, '--dry-run', '--no-log', '--resume')
        assert result.returncode == 0, result.stderr
        assert 'nothing to resume' in result.stdout
        assert not (state / 'last-completed-stage').exists()

    def test_resume_with_stale_state_runs_from_first_stage(self, base: Path, shell: str, env: dict[str, str]) -> None:
        """
        Test that a recorded stage that no longer exists falls back to running from the first stage
        """
        state = Path(env['BOOTSTRAP_LOG_DIR'])
        state.mkdir(parents=True)
        (state / 'last-completed-stage').write_text('42-gone\n', encoding='utf-8')

        result = _drive(base, shell, env, '--dry-run', '--no-log', '--resume')
        assert "recorded stage '42-gone' no longer exists" in result.stderr


class TestDryRun:
    """
    Tests for dry-run safety
    """
    def test_dry_run_never_primes_sudo(self, base: Path, shell: str, env: dict[str, str], tmp_path: Path) -> None:
        """
        Test that --dry-run reaches the stages without invoking sudo
        """
        bin_dir = tmp_path / 'bin'
        bin_dir.mkdir()

        sentinel = tmp_path / 'sudo-called'
        stub = bin_dir / 'sudo'
        stub.write_text(f'#!/bin/sh\ntouch "{sentinel}"\nexit 1\n', encoding='utf-8')
        stub.chmod(0o755)

        stubbed = {**env, 'PATH': f'{bin_dir}:{env["PATH"]}', 'DOTFILES_OS': 'darwin'}
        result  = _drive(base, shell, stubbed, '--dry-run', '--no-log', '--only', '98-selftest-ok')

        assert result.returncode == 0, result.stderr
        assert 'would prime sudo' in result.stdout
        assert not sentinel.exists()

    def test_linux_never_primes_sudo(self, base: Path, shell: str, env: dict[str, str], tmp_path: Path) -> None:
        """
        Test that a real run on linux never invokes sudo (no Linux stage needs root; Ansible owns root)
        """
        bin_dir = tmp_path / 'bin'
        bin_dir.mkdir()

        sentinel = tmp_path / 'sudo-called'
        stub = bin_dir / 'sudo'
        stub.write_text(f'#!/bin/sh\ntouch "{sentinel}"\nexit 1\n', encoding='utf-8')
        stub.chmod(0o755)

        stubbed = {**env, 'PATH': f'{bin_dir}:{env["PATH"]}', 'DOTFILES_OS': 'linux'}
        result  = _drive(base, shell, stubbed, '--no-log', '--only', '98-selftest-ok')

        assert result.returncode == 0, result.stderr
        assert not sentinel.exists()

    def test_darwin_still_primes_sudo(self, base: Path, shell: str, env: dict[str, str], tmp_path: Path) -> None:
        """
        Test that a real run on darwin primes sudo exactly as before
        """
        bin_dir = tmp_path / 'bin'
        bin_dir.mkdir()

        # `sudo -v` succeeds and records the call; `sudo -n true` fails so the keep-alive loop exits at once
        sentinel = tmp_path / 'sudo-called'
        stub = bin_dir / 'sudo'
        stub.write_text(f'#!/bin/sh\n[ "$1" = "-v" ] || exit 1\ntouch "{sentinel}"\n', encoding='utf-8')
        stub.chmod(0o755)

        stubbed = {**env, 'PATH': f'{bin_dir}:{env["PATH"]}', 'DOTFILES_OS': 'darwin'}
        result  = _drive(base, shell, stubbed, '--no-log', '--only', '98-selftest-ok')

        assert result.returncode == 0, result.stderr
        assert sentinel.exists()

    def test_dry_run_writes_no_state(self, base: Path, shell: str, env: dict[str, str]) -> None:
        """
        Test that --dry-run leaves the state and log directory untouched
        """
        result = _drive(base, shell, env, '--dry-run', '--only', '98-selftest-ok')
        assert result.returncode == 0, result.stderr
        assert 'would tee this run to a logfile' in result.stdout
        assert not Path(env['BOOTSTRAP_LOG_DIR']).exists()

    def test_verify_is_skipped_under_dry_run(self, base: Path, shell: str, env: dict[str, str]) -> None:
        """
        Test that --verify prints the public uv wrapper doctor command but does not run it under --dry-run
        """
        result = _drive(base, shell, env, '--dry-run', '--no-log', '--only', '98-selftest-ok', '--verify')
        assert result.returncode == 0, result.stderr
        assert 'scripts/hooks/uv-public.sh run python run.py doctor' in result.stdout
        assert 'verify (dry-run)' in result.stdout


class TestHelp:
    """
    Tests for the help text
    """
    def test_help_mentions_flags(self, base: Path, shell: str, env: dict[str, str]) -> None:
        """
        Test that --help documents the driver flags
        """
        result = _drive(base, shell, env, '--help')
        assert result.returncode == 0, result.stderr
        for flag in ('--dry-run', '--list', '--verify', '--no-log', '--resume', '--only', '--from'):
            assert flag in result.stdout + result.stderr

    def test_help_works_with_broken_registry(self, base: Path, shell: str, env: dict[str, str], tmp_path: Path) -> None:
        """
        Test that --help is served before the overlay registry is read, so a bad registry cannot hide it
        """
        Path(env['DOTFILES_OVERLAYS_FILE']).write_text(f'{tmp_path / "gone"}\n', encoding='utf-8')
        result = _drive(base, shell, env, '-h')
        assert result.returncode == 0, result.stderr
        assert '--resume' in result.stdout
