"""
Throwaway-home integration tests: base layer + fixture overlay stowed and rendered into an empty HOME
"""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE   = REPO_ROOT / 'tests' / 'fixtures' / 'overlay'

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which('stow') is None, reason='GNU Stow not installed'),
    pytest.mark.skipif(shutil.which('zsh')  is None, reason='zsh not installed'),
    pytest.mark.skipif(shutil.which('git')  is None, reason='git not installed'),
]


@dataclass
class Home:
    """
    An isolated HOME with the base layer and fixture overlay applied
    """
    path: Path
    env:  dict[str, str]

    def run(self, *cmd: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        """
        Run a command inside this HOME
        """
        return subprocess.run(
            list(cmd),
            capture_output=True,
            text=True,
            check=False,
            env=self.env,
            cwd=cwd or self.path,
        )

    def zsh(self, command: str) -> subprocess.CompletedProcess[str]:
        """
        Run an interactive zsh command inside this HOME
        """
        return self.run('zsh', '-i', '-c', command)


STARTUP_BUDGET_MS = 300   # on a machine whose calibration run takes CALIBRATION_MS or less
CALIBRATION_MS    = 25
TIMING_SAMPLES    = 3
PTY_TIMEOUT       = 10    # seconds before a terminal run is killed and the test fails


@dataclass
class StartupBudget:
    """
    Startup-time budget for this session, scaled by how slowly this machine launches processes right now
    """
    calib_ms:  float
    budget_ms: float
    source:    str

    def check(self, timings: list[float], label: str) -> None:
        """
        Assert that the best of the timings fits the budget, reporting the calibration on failure

        :param timings: wall times in seconds
        :param label: what was timed, for the assertion message
        """
        best_ms = min(timings) * 1000
        samples = ', '.join(f'{t * 1000:.0f}' for t in timings)
        assert best_ms < self.budget_ms, (
            f'{label} took {best_ms:.0f} ms at best ({samples} ms); budget {self.budget_ms:.0f} ms '
            f'({self.source}; calib {self.calib_ms:.1f} ms for 10 process launches)'
        )


@pytest.fixture(scope='session')
def startup_budget() -> StartupBudget:
    """
    Calibrate the startup budget once per session

    The calibration is the best of five wall times of a bare zsh launching /usr/bin/true ten times, which tracks
    process-launch cost under the current load. The budget is 300 ms, scaled up by calib / 25 ms when the machine is
    slower than that. DOTFILES_STARTUP_BUDGET_MS overrides the computed budget.
    """
    zsh = shutil.which('zsh')
    assert zsh is not None

    best = float('inf')
    for _ in range(5):
        start = time.monotonic()
        subprocess.run([zsh, '-f', '-c', 'repeat 10 /usr/bin/true'], check=True)
        best = min(best, time.monotonic() - start)
    calib_ms = best * 1000

    if override := os.environ.get('DOTFILES_STARTUP_BUDGET_MS', ''):
        try:
            return StartupBudget(calib_ms, float(override), 'DOTFILES_STARTUP_BUDGET_MS override')
        except ValueError:
            pytest.fail(f'DOTFILES_STARTUP_BUDGET_MS must be a number of milliseconds, got {override!r}')

    scale = max(1.0, calib_ms / CALIBRATION_MS)
    return StartupBudget(calib_ms, STARTUP_BUDGET_MS * scale, f'calibrated x{scale:.2f}')


def run_zsh_with_tty(
    home: Home,
    command: str,
    extra_env: dict[str, str] | None = None,
) -> tuple[subprocess.CompletedProcess[bytes], float]:
    """
    Run an interactive zsh command on a pseudo-terminal and return the result with its wall time

    A real terminal is what makes the starship and fzf snippets initialize, which plain pipes never do. The run is
    killed (with its whole process group) after PTY_TIMEOUT seconds; the test is skipped when no pseudo-terminal can be
    allocated.

    :param home: isolated HOME to run in
    :param command: zsh command string
    :param extra_env: environment overrides layered over the HOME's environment (TERM defaults to xterm-256color)
    :raises subprocess.TimeoutExpired: if the shell does not exit within PTY_TIMEOUT seconds
    :return: completed process (stdout holds the terminal output, stderr is empty) and elapsed seconds
    """
    import pty  # POSIX-only: imported lazily so test collection works everywhere
    import select

    try:
        leader, follower = pty.openpty()
    except OSError as e:
        pytest.skip(f'no pseudo-terminal available: {e}')

    env  = {**home.env, 'TERM': 'xterm-256color', **(extra_env or {})}
    proc = None
    try:
        start = time.monotonic()
        proc  = subprocess.Popen(
            ['zsh', '-i', '-c', command],
            stdin=follower,
            stdout=follower,
            stderr=follower,
            env=env,
            cwd=home.path,
            start_new_session=True,
        )

        returncode = proc.wait(timeout=PTY_TIMEOUT)
        elapsed    = time.monotonic() - start
        output     = b''
        while select.select([leader], [], [], 0.1)[0]:
            output += os.read(leader, 65536)

    finally:
        if (proc is not None) and (proc.poll() is None):
            try:
                os.killpg(proc.pid, signal.SIGKILL)  # start_new_session made the shell its group's leader
            except ProcessLookupError:
                pass
            proc.wait()

        os.close(leader)
        os.close(follower)

    return subprocess.CompletedProcess(proc.args, returncode, output, b''), elapsed


@pytest.fixture(scope='module')
def home(tmp_path_factory: pytest.TempPathFactory) -> Home:
    """
    Stow and render everything into a fresh HOME once per module
    """
    path     = tmp_path_factory.mktemp('home')
    registry = path / '.config' / 'dotfiles' / 'overlays'
    registry.parent.mkdir(parents=True)
    registry.write_text(f'{FIXTURE}\n', encoding='utf-8')

    env: dict[str, str] = {
        'HOME':                 str(path),
        'PATH':                 os.environ['PATH'],
        'TERM':                 'dumb',
        'DOTFILES_NO_BANNER':   '1',        # the banner slows and pollutes terminal runs; banner tests opt back in
        'GIT_CONFIG_NOSYSTEM':  '1',        # keep the machine's system gitconfig out of git assertions
        'XDG_CONFIG_HOME':      str(path / '.config'),
        'XDG_STATE_HOME':       str(path / '.local' / 'state'),
        'XDG_DATA_HOME':        str(path / '.local' / 'share'),
        'DOTFILES_OS':          'darwin',   # this module tests macOS layout; test_os_layout.py covers Linux

        # the darwin layout has no shell-linux package, so mirror its ~/.zshenv: on a Linux host Debian's
        # /etc/zsh/zshrc would otherwise run its own unguarded compinit
        'skip_global_compinit': '1',
    }
    result = Home(path, env)

    stowed = result.run('bash', str(REPO_ROOT / 'stow.sh'))
    assert stowed.returncode == 0, stowed.stdout + stowed.stderr

    rendered = result.run('python3', str(REPO_ROOT / 'scripts' / 'dotfiles' / 'render.py'), '--force')
    assert rendered.returncode == 0, rendered.stdout + rendered.stderr
    return result


class TestEngine:
    """
    Tests that hold for any set of packages
    """
    def test_overlay_package_is_linked(self, home: Home) -> None:
        """
        Test that the fixture overlay's files are stowed beside the base's
        """
        assert (home.path / '.config' / 'zsh' / 'conf.d' / '31-fixture.zsh').is_symlink()

    def test_no_folded_directories(self, home: Home) -> None:
        """
        Test that no directory under HOME is a symlink into a repository
        """
        folded = [p for p in home.path.rglob('*') if p.is_symlink() and p.is_dir()]
        assert folded == []

    def test_rendered_claude_settings_include_overlay(self, home: Home) -> None:
        """
        Test that the rendered Claude settings contain the overlay fragment's values
        """
        settings = json.loads((home.path / '.claude' / 'settings.json').read_text(encoding='utf-8'))
        assert settings['env']['FIXTURE_OVERLAY'] == '1'

    def test_render_is_in_sync(self, home: Home) -> None:
        """
        Test that a second check finds nothing to do
        """
        result = home.run('python3', str(REPO_ROOT / 'scripts' / 'dotfiles' / 'render.py'), '--check')
        assert result.returncode == 0, result.stderr


class TestShell:
    """
    Tests for the shell package
    """
    def test_interactive_zsh_is_clean(self, home: Home) -> None:
        """
        Test that an interactive shell starts without stderr output, cold and warm
        """
        for _ in range(2):
            result = home.zsh('exit')
            assert result.returncode == 0
            assert result.stderr == ''

    @pytest.mark.timing
    def test_interactive_zsh_is_clean_and_fast(self, home: Home, startup_budget: StartupBudget) -> None:
        """
        Test that an interactive shell starts without stderr output within the startup budget (best of three warm runs)
        """
        home.zsh('exit')  # warm caches (compinit dump, generated completions) before timing

        timings: list[float] = []
        for _ in range(TIMING_SAMPLES):
            start  = time.monotonic()
            result = home.zsh('exit')
            timings.append(time.monotonic() - start)
            assert result.returncode == 0
            assert result.stderr     == ''

        startup_budget.check(timings, 'zsh -i')

    def test_overlay_snippet_is_sourced(self, home: Home) -> None:
        """
        Test that conf.d snippets from overlays load alongside the base's
        """
        assert home.zsh('print -r -- $DOTFILES_FIXTURE_OVERLAY').stdout.strip() == '1'

    def test_dotfiles_repo_resolves(self, home: Home) -> None:
        """
        Test that DOTFILES_REPO points at this repository
        """
        assert Path(home.zsh('print -r -- $DOTFILES_REPO').stdout.strip()) == REPO_ROOT

    def test_zshrc_local_is_sourced_last(self, home: Home) -> None:
        """
        Test that ~/.zshrc.local runs after conf.d
        """
        local = home.path / '.zshrc.local'
        local.write_text('export ZSHRC_LOCAL_PROBE=1\n', encoding='utf-8')
        try:
            assert home.zsh('print -r -- $ZSHRC_LOCAL_PROBE').stdout.strip() == '1'
        finally:
            local.unlink()

    def test_interactive_zsh_is_clean_without_tools(self, home: Home) -> None:
        """
        Test that an interactive shell, including its chpwd hooks, is clean when no optional tool is on PATH
        """
        zsh    = shutil.which('zsh')
        assert zsh is not None

        env    = {**home.env, 'PATH': '/usr/bin:/bin', 'DOTFILES_BREW_PROBE': '0'}  # else the probe finds a local brew
        result = subprocess.run(
            [zsh, '-i', '-c', 'cd / && cd ~'],
            capture_output=True,
            text=True,
            check=False,
            env=env,
            cwd=home.path,
        )
        assert result.returncode == 0
        assert result.stderr     == ''


def write_fake_tool(path: Path, log: Path, output: str, status: int = 0) -> Path:
    """
    Write an executable stand-in that appends its arguments to log, prints output, and exits with status

    :param path: where to create the tool (parent directories are created)
    :param log: invocation log, one line of arguments per run
    :param output: text printed on stdout
    :param status: exit status
    :return: the tool's path
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'#!/bin/sh\nprintf \'%s\\n\' "$*" >> {shlex.quote(str(log))}\n'
        f"cat <<'EOF'\n{output}\nEOF\nexit {status}\n",
        encoding='utf-8',
    )
    path.chmod(0o755)
    return path


def invocations(log: Path) -> list[str]:
    """
    Return the argument lines a fake tool recorded, oldest first
    """
    return log.read_text(encoding='utf-8').splitlines() if log.exists() else []


def make_older(path: Path, seconds: float) -> None:
    """
    Set a file's mtime (not following symlinks) to the given number of seconds ago
    """
    when = time.time() - seconds
    os.utime(path, (when, when), follow_symlinks=False)


class TestStartupCaches:
    """
    Tests for cached generator output (cached_eval in 00-lib) and the completion dump (20-completion)
    """
    @staticmethod
    def _env(home: Home, root: Path, **extra: str) -> dict[str, str]:
        """
        Environment with only root/bin and the system directories on PATH, and a private cache directory
        """
        return {
            **home.env,
            'PATH':                f'{root / "bin"}:/usr/bin:/bin',
            'DOTFILES_BREW_PROBE': '0',
            'XDG_CACHE_HOME':      str(root / 'cache'),
            **extra,
        }

    @staticmethod
    def _zsh(home: Home, env: dict[str, str], command: str) -> subprocess.CompletedProcess[str]:
        """
        Run an interactive zsh command with stdin closed (so a compinit prompt fails fast instead of waiting)
        """
        zsh = shutil.which('zsh')
        assert zsh is not None

        return subprocess.run(
            [zsh, '-i', '-c', command],
            capture_output=True,
            text=True,
            check=False,
            env=env,
            cwd=home.path,
            stdin=subprocess.DEVNULL,
        )

    # ==============================================================================
    # cached_eval
    # ==============================================================================

    PROBE = 'cached_eval fake faketool init zsh; print -r -- "status=$? probe=${CACHED_PROBE-unset}"'

    def test_second_start_reuses_the_cache(self, home: Home, tmp_path: Path) -> None:
        """
        Test that the generator runs once and later shells source its saved output
        """
        log = tmp_path / 'calls.log'
        write_fake_tool(tmp_path / 'bin' / 'faketool', log, 'typeset -g CACHED_PROBE=loaded')

        env = self._env(home, tmp_path)
        for _ in range(2):
            result = self._zsh(home, env, self.PROBE)
            assert result.stderr == ''
            assert result.stdout.strip() == 'status=0 probe=loaded'

        assert invocations(log) == ['init zsh']
        assert (tmp_path / 'cache' / 'zsh' / 'fake.zsh').is_file()
        assert list((tmp_path / 'cache' / 'zsh').glob('*.tmp')) == []

    def test_newer_binary_regenerates(self, home: Home, tmp_path: Path) -> None:
        """
        Test that touching the binary newer than the cache makes the next shell regenerate it
        """
        log  = tmp_path / 'calls.log'
        tool = write_fake_tool(tmp_path / 'bin' / 'faketool', log, 'typeset -g CACHED_PROBE=loaded')
        env  = self._env(home, tmp_path)

        self._zsh(home, env, self.PROBE)
        future = time.time() + 3600
        os.utime(tool, (future, future))

        result = self._zsh(home, env, self.PROBE)
        assert result.stdout.strip() == 'status=0 probe=loaded'
        assert invocations(log) == ['init zsh', 'init zsh']

    def test_newer_symlink_target_regenerates(self, home: Home, tmp_path: Path) -> None:
        """
        Test that the mtime of a symlinked binary's target counts, as for Homebrew's bin/ links into the Cellar
        """
        log    = tmp_path / 'calls.log'
        target = write_fake_tool(tmp_path / 'Cellar' / 'v1' / 'faketool', log, 'typeset -g CACHED_PROBE=loaded')
        link   = tmp_path / 'bin' / 'faketool'

        link.parent.mkdir()
        link.symlink_to(target)
        make_older(link, 7200)

        env = self._env(home, tmp_path)
        self._zsh(home, env, self.PROBE)
        future = time.time() + 3600
        os.utime(target, (future, future))

        self._zsh(home, env, self.PROBE)
        assert invocations(log) == ['init zsh', 'init zsh']

    def test_retargeted_symlink_regenerates_even_when_the_new_binary_is_older(
        self,
        home: Home,
        tmp_path: Path,
    ) -> None:
        """
        Test that an upgrade which relinks to a binary built before the cache was written still regenerates it
        """
        log  = tmp_path / 'calls.log'
        old  = write_fake_tool(tmp_path / 'Cellar' / 'v1' / 'faketool', log, 'typeset -g CACHED_PROBE=v1')
        new  = write_fake_tool(tmp_path / 'Cellar' / 'v2' / 'faketool', log, 'typeset -g CACHED_PROBE=v2')
        link = tmp_path / 'bin' / 'faketool'

        link.parent.mkdir()
        link.symlink_to(old)

        env = self._env(home, tmp_path)
        assert self._zsh(home, env, self.PROBE).stdout.strip() == 'status=0 probe=v1'

        make_older(new, 86400)  # bottles keep their build-time mtimes, older than a cache written since
        link.unlink()
        link.symlink_to(new)

        assert self._zsh(home, env, self.PROBE).stdout.strip() == 'status=0 probe=v2'
        assert invocations(log) == ['init zsh', 'init zsh']

    def test_changed_arguments_regenerate(self, home: Home, tmp_path: Path) -> None:
        """
        Test that the cache records the generator's arguments, so editing a snippet's command takes effect
        """
        log = tmp_path / 'calls.log'
        write_fake_tool(tmp_path / 'bin' / 'faketool', log, 'typeset -g CACHED_PROBE=loaded')

        env = self._env(home, tmp_path)
        self._zsh(home, env, self.PROBE)
        self._zsh(home, env, self.PROBE.replace('init zsh', 'init zsh --cmd j'))
        assert invocations(log) == ['init zsh', 'init zsh --cmd j']

    @pytest.mark.parametrize(
        ('output', 'status'),
        [
            ('typeset -g CACHED_PROBE=partial', 3),
            ('',                                0),
        ],
    )
    def test_failed_or_empty_generation_is_not_cached(
        self,
        home: Home,
        tmp_path: Path,
        output: str,
        status: int,
    ) -> None:
        """
        Test that a failing or silent generator leaves no cache, sources nothing, and is retried by the next shell
        """
        log = tmp_path / 'calls.log'
        write_fake_tool(tmp_path / 'bin' / 'faketool', log, output, status)

        env = self._env(home, tmp_path)
        for _ in range(2):
            result = self._zsh(home, env, self.PROBE)
            assert result.stderr == ''
            assert result.stdout.strip() == 'status=1 probe=unset'

        assert invocations(log) == ['init zsh', 'init zsh']
        assert list((tmp_path / 'cache' / 'zsh').glob('fake*')) == []

    def test_unwritable_cache_falls_back_to_direct_eval(self, home: Home, tmp_path: Path) -> None:
        """
        Test that the tool still initializes, silently, when the cache directory cannot be created
        """
        log     = tmp_path / 'calls.log'
        blocker = tmp_path / 'not-a-dir'
        blocker.write_text('', encoding='utf-8')

        write_fake_tool(tmp_path / 'bin' / 'faketool', log, 'typeset -g CACHED_PROBE=loaded')

        env    = self._env(home, tmp_path, XDG_CACHE_HOME=str(blocker))
        result = self._zsh(home, env, self.PROBE)
        assert result.stderr == ''
        assert result.stdout.strip() == 'status=0 probe=loaded'

    def test_absent_binary_is_a_silent_no_op(self, home: Home, tmp_path: Path) -> None:
        """
        Test that naming a tool that is not installed returns 1 without output or a cache file
        """
        result = self._zsh(home, self._env(home, tmp_path), self.PROBE)
        assert result.stderr == ''
        assert result.stdout.strip() == 'status=1 probe=unset'
        assert not (tmp_path / 'cache' / 'zsh' / 'fake.zsh').exists()

    @pytest.mark.parametrize(
        ('tool', 'args', 'terminal'),
        [
            ('pkl',      'shell-completion zsh',          False),
            ('wt',       'config shell init zsh',         False),
            ('uv',       'generate-shell-completion zsh', False),
            ('fzf',      '--zsh',                         True),
            ('starship', 'init zsh',                      True),
        ],
    )
    def test_snippet_caches_generated_output(
        self,
        home: Home,
        tmp_path: Path,
        tool: str,
        args: str,
        terminal: bool,
    ) -> None:
        """
        Test that each snippet's generator runs on the first start only, and again once its binary is newer
        """
        if terminal and os.name != 'posix':
            pytest.skip('pseudo-terminals are POSIX-only')

        log    = tmp_path / 'calls.log'
        binary = write_fake_tool(tmp_path / 'bin' / tool, log, f'typeset -g CACHED_PROBE_{tool}=1')
        env    = self._env(home, tmp_path)
        probe  = f'print -r -- "probe=${{CACHED_PROBE_{tool}-unset}}"'

        def start() -> str:
            if terminal:
                overrides = {key: env[key] for key in ('PATH', 'DOTFILES_BREW_PROBE', 'XDG_CACHE_HOME')}
                on_tty, _elapsed = run_zsh_with_tty(home, probe, overrides)
                return on_tty.stdout.decode().strip()

            piped = self._zsh(home, env, probe)
            assert piped.stderr == ''
            return piped.stdout.strip()

        counts: list[int] = []
        for step in range(3):
            if step == 2:
                future = time.time() + 3600
                os.utime(binary, (future, future))

            assert start() == 'probe=1'
            counts.append(len(invocations(log)))

        assert counts == [1, 1, 2]
        assert set(invocations(log)) == {args}

    # ==============================================================================
    # compinit
    # ==============================================================================

    @staticmethod
    def _fake_compaudit(root: Path) -> tuple[Path, Path]:
        """
        Put a compaudit that records each run in a function directory, returning (directory, log)
        """
        log    = root / 'audit.log'
        fndir  = root / 'functions'
        fndir.mkdir()
        (fndir / 'compaudit').write_text(f'print -r -- audit >> {shlex.quote(str(log))}\nreturn 0\n', encoding='utf-8')
        return fndir, log

    @staticmethod
    def _fpath_with(directory: Path) -> str:
        """
        Return zsh's default FPATH with directory prepended (an FPATH in the environment replaces the default)
        """
        zsh = shutil.which('zsh')
        assert zsh is not None

        default = subprocess.run([zsh, '-f', '-c', 'print -r -- $FPATH'], capture_output=True, text=True, check=True)
        return f'{directory}:{default.stdout.strip()}'

    def _dump(self, root: Path) -> Path:
        """
        Return the single completion dump under root's cache directory
        """
        dumps = sorted((root / 'cache' / 'zsh').glob('zcompdump-*'))
        assert len(dumps) == 1, dumps
        return dumps[0]

    def test_compinit_audits_only_without_a_dump(self, home: Home, tmp_path: Path) -> None:
        """
        Test that the first shell runs the full compinit (security audit), and the next loads the dump as-is
        """
        fndir, log = self._fake_compaudit(tmp_path)
        env        = self._env(home, tmp_path, FPATH=self._fpath_with(fndir))

        counts     = []
        for _ in range(2):
            result = self._zsh(home, env, 'exit')
            assert result.returncode == 0
            assert result.stderr     == ''
            counts.append(len(invocations(log)))

        assert counts == [1, 1]
        assert self._dump(tmp_path).stat().st_size > 0

    def test_day_old_dump_gets_one_full_check(self, home: Home, tmp_path: Path) -> None:
        """
        Test that a dump older than 24 hours triggers one full compinit, which resets its age
        """
        fndir, log = self._fake_compaudit(tmp_path)
        env        = self._env(home, tmp_path, FPATH=self._fpath_with(fndir))

        self._zsh(home, env, 'exit')
        make_older(self._dump(tmp_path), 25 * 3600)

        counts: list[int] = []
        for _ in range(2):
            result = self._zsh(home, env, 'exit')
            assert result.stderr == ''
            counts.append(len(invocations(log)))

        assert counts == [2, 2]

    def test_pkl_completion_does_not_rerun_compinit(self, home: Home, tmp_path: Path) -> None:
        """
        Test that the bare compinit inside pkl's generated script is skipped, and compinit stays usable afterwards
        """
        fndir, audits = self._fake_compaudit(tmp_path)
        write_fake_tool(
            tmp_path / 'bin' / 'pkl', tmp_path / 'pkl.log',
            'autoload -Uz compinit\ncompinit\ntypeset -g CACHED_PROBE_pkl=1',
        )
        env    = self._env(home, tmp_path, FPATH=self._fpath_with(fndir))
        probe  = 'print -r -- "probe=$CACHED_PROBE_pkl compinit=${+functions[compinit]}"'

        counts: list[int] = []
        for _ in range(2):
            result = self._zsh(home, env, probe)
            assert result.stderr == ''
            assert result.stdout.strip() == 'probe=1 compinit=1'
            counts.append(len(invocations(audits)))

        assert counts == [1, 1]

    @staticmethod
    def _fake_omz(home: Home) -> Path:
        """
        Install a minimal oh-my-zsh at the path 10-omz sources, mirroring the real script's compinit and compdef calls
        """
        omz = home.path / '.oh-my-zsh'
        omz.mkdir()
        (omz / 'oh-my-zsh.sh').write_text(
            'autoload -U compaudit compinit zrecompile\n'
            'ZSH_COMPDUMP="${ZSH_COMPDUMP:-$HOME/.zcompdump-fakehost-$ZSH_VERSION}"\n'
            'unset _comp_secure\n'
            'compinit -i -d "$ZSH_COMPDUMP"\n'
            'compdef _fakeomz fakeomz\n'
            "compdef _fakeomz 'semi;colon'\n",
            encoding='utf-8',
        )
        return omz

    def test_oh_my_zsh_does_not_run_its_own_compinit(self, home: Home, tmp_path: Path) -> None:
        """
        Test that oh-my-zsh's compinit is skipped, its compdef calls are replayed after the real compinit, and
        compinit and compdef are the real functions again afterwards
        """
        fndir, audits = self._fake_compaudit(tmp_path)
        env   = self._env(home, tmp_path, FPATH=self._fpath_with(fndir))
        probe = (
            'print -r -- "comps=${_comps[fakeomz]-none},${_comps[semi;colon]-none}"; '
            'print -r -- "queue=${+_omz_deferred_compdefs}"; '
            'print -r -- "compinit=${functions[compinit]}"; '
            'print -r -- "compdef=${functions[compdef]}"'
        )

        omz = self._fake_omz(home)
        try:
            counts: list[int] = []
            for _ in range(2):
                result = self._zsh(home, env, probe)
                assert result.returncode == 0
                assert result.stderr     == ''

                comps, queue, compinit, *compdef = result.stdout.splitlines()
                assert comps    == 'comps=_fakeomz,_fakeomz'
                assert queue    == 'queue=0'
                assert compinit == 'compinit=builtin autoload -XU'
                assert '_omz_deferred_compdefs' not in '\n'.join(compdef)
                counts.append(len(invocations(audits)))

            assert counts == [1, 1]
            assert list(home.path.glob('.zcompdump*')) == []
            assert self._dump(tmp_path).stat().st_size > 0

        finally:
            shutil.rmtree(omz)

    def test_insecure_function_directory_is_ignored_without_a_prompt(self, home: Home, tmp_path: Path) -> None:
        """
        Test that the full compinit skips a world-writable fpath directory silently instead of asking
        """
        insecure = tmp_path / 'insecure'
        insecure.mkdir()

        (insecure / '_insecurefake').write_text('#compdef insecurefake\n', encoding='utf-8')
        insecure.chmod(0o777)

        env    = self._env(home, tmp_path, FPATH=self._fpath_with(insecure))
        result = self._zsh(home, env, 'print -r -- "comp=${_comps[insecurefake]-none}"')
        assert result.returncode == 0
        assert result.stderr == ''
        assert result.stdout.strip() == 'comp=none'


class TestPythonNode:
    """
    Tests for the python and node packages
    """
    def test_workon_home_resolves_cleanly(self, home: Home) -> None:
        """
        Test that WORKON_HOME is exported under HOME without stderr output
        """
        result = home.zsh('print -r -- $WORKON_HOME')
        assert result.returncode == 0
        assert result.stderr == ''
        assert result.stdout.strip() == str(home.path / '.virtualenvs')

    def test_bun_install_is_exported(self, home: Home) -> None:
        """
        Test that the node package points BUN_INSTALL at ~/.bun
        """
        assert home.zsh('print -r -- $BUN_INSTALL').stdout.strip() == str(home.path / '.bun')

    @pytest.mark.parametrize(
        'relpath',
        [
            '.pip/pip.conf',
            '.npmrc',
            '.config/uv/uv.toml',
        ],
    )
    def test_registry_configs_are_not_shipped(self, home: Home, relpath: str) -> None:
        """
        Test that the base layer ships no package-index or registry configuration
        """
        assert not (home.path / relpath).exists()

    def test_ipython_startup_file_is_linked(self, home: Home) -> None:
        """
        Test that the IPython startup file is stowed as a symlink
        """
        assert (home.path / '.ipython' / 'profile_default' / 'startup' / '00-rich.py').is_symlink()

    def test_hatch_config_is_generic(self, home: Home) -> None:
        """
        Test that the stowed hatch config carries no publish index, email, or hardcoded home paths
        """
        config = home.path / 'Library' / 'Application Support' / 'hatch' / 'config.toml'
        assert config.is_symlink()

        text = config.read_text(encoding='utf-8')
        assert '[publish' not in text
        assert 'email'    not in text
        assert '/Users/'  not in text


class TestClaude:
    """
    Tests for the claude package and render fragment
    """
    @staticmethod
    def _settings(home: Home) -> dict[str, object]:
        """
        Load the rendered Claude settings
        """
        return json.loads((home.path / '.claude' / 'settings.json').read_text(encoding='utf-8'))

    @staticmethod
    def _hook_commands(settings: dict[str, object]) -> list[str]:
        """
        Every hook command in the rendered settings
        """
        hooks = settings.get('hooks', {})
        assert isinstance(hooks, dict)
        return [hook['command'] for groups in hooks.values() for group in groups for hook in group['hooks']]

    def test_settings_hooks_use_home_relative_paths(self, home: Home) -> None:
        """
        Test that no rendered hook command embeds an absolute home path
        """
        text = (home.path / '.claude' / 'settings.json').read_text(encoding='utf-8')
        assert '/Users/' not in text

    def test_hook_scripts_exist_for_every_hook(self, home: Home) -> None:
        """
        Test that every $HOME path in a rendered hook command, interpreter-prefixed or not, points at a stowed script
        """
        scripts: list[Path] = [
            Path(token.strip('"').replace('$HOME', str(home.path), 1))
            for command in self._hook_commands(self._settings(home))
            for token in command.split()
            if token.strip('"').startswith('$HOME/')
        ]
        assert scripts, 'no home-relative hook commands rendered'

        missing = [str(script) for script in scripts if not script.is_file()]
        assert missing == []

    def test_direct_hook_commands_are_executable(self, home: Home) -> None:
        """
        Test that hook commands run without an interpreter prefix point at executable files
        """
        direct: list[Path] = [
            Path(command.split()[0].strip('"').replace('$HOME', str(home.path), 1))
            for command in self._hook_commands(self._settings(home))
            if command.startswith('$HOME/')
        ]
        assert direct
        assert [str(script) for script in direct if not os.access(script, os.X_OK)] == []

    def test_model_router_default_config_stowed_beside_script(self, home: Home) -> None:
        """
        Test that the model-router default config is stowed beside the script, since a missing default silently
        disables routing (the hook fails open on a missing config)
        """
        assert (home.path / '.claude' / 'hooks' / 'model-router.default.json').is_file()

    def test_base_settings_carry_no_overlay_only_keys(self, home: Home) -> None:
        """
        Test that keys the work overlay owns are absent when only the base and fixture overlay are rendered
        """
        settings = self._settings(home)
        for key in ('apiKeyHelper', 'statusLine', 'enabledPlugins', 'extraKnownMarketplaces', 'mcpServers'):
            assert key not in settings, key

    def test_spinner_verbs_are_unique(self, home: Home) -> None:
        """
        Test that the rendered spinner verbs contain no duplicates
        """
        spinner = self._settings(home)['spinnerVerbs']
        assert isinstance(spinner, dict)

        verbs = spinner['verbs']
        assert verbs
        assert len(verbs) == len(set(verbs))

    def test_claude_alias_without_ca_override(self, home: Home) -> None:
        """
        Test that the shell snippet defines the claude alias and leaves the Node CA bundle to overlays
        """
        result = home.zsh('alias cl; print -r -- "ca=${NODE_EXTRA_CA_CERTS-unset}"')
        assert result.returncode == 0, result.stderr
        assert result.stderr == ''
        assert 'claude'   in result.stdout
        assert 'ca=unset' in result.stdout

    def test_cleanup_script_runs_dry(self, home: Home) -> None:
        """
        Test that the stowed cleanup script completes a dry run in an empty Claude directory
        """
        script = home.path / '.claude' / 'scripts' / 'dotclaude-cleanup.sh'
        assert script.is_symlink()

        result = home.run('bash', str(script), '--dry-run')
        assert result.returncode == 0, result.stderr
        assert 'DRY RUN complete' in result.stdout


class TestGit:
    """
    Tests for per-remote git identity
    """
    PERSONAL = 'connor@conmason.com'
    DEFAULT  = 'work@example.com'

    def _repo(self, home: Home, name: str, remote: str | None) -> Path:
        """
        Create a repo inside HOME, with an origin remote when one is given
        """
        repo = home.path / name

        commands: list[tuple[str, ...]] = [('git', 'init', '-q', '--template=', str(repo))]
        if remote is not None:
            commands.append(('git', '-C', str(repo), 'remote', 'add', 'origin', remote))

        for command in commands:
            result = home.run(*command)
            assert result.returncode == 0, result.stderr
        return repo

    @pytest.mark.parametrize(
        ('remote', 'expected'),
        [
            ('git@github.com:connormason/x.git',              PERSONAL),
            ('https://github.com/connormason/x.git',          PERSONAL),
            ('ssh://git@github.com/connormason/x.git',        PERSONAL),
            ('https://someuser@github.com/connormason/x.git', PERSONAL),
            (None,                                            DEFAULT),
            ('git@git.example.com:team/x.git',                DEFAULT),
            ('git@github.com:connormason2/x.git',             DEFAULT),
        ],
    )
    def test_identity_follows_remote(self, home: Home, remote: str | None, expected: str) -> None:
        """
        Test that personal GitHub remotes get the personal identity and everything else the overlay's default
        """
        name   = 'repo-' + ''.join(c if c.isalnum() else '-' for c in str(remote))
        repo   = self._repo(home, name, remote)
        result = home.run('git', 'config', 'user.email', cwd=repo)
        assert result.stdout.strip() == expected


class TestVSCode:
    """
    Tests for the vscode package and render fragment
    """
    USER_DIR = Path('Library') / 'Application Support' / 'Code' / 'User'

    def _settings(self, home: Home) -> dict[str, object]:
        """
        Load the rendered VS Code settings
        """
        return json.loads((home.path / self.USER_DIR / 'settings.json').read_text(encoding='utf-8'))

    def test_settings_are_rendered_not_linked(self, home: Home) -> None:
        """
        Test that settings.json is a regular rendered file rather than a symlink into a repository
        """
        settings = home.path / self.USER_DIR / 'settings.json'
        assert settings.is_file()
        assert not settings.is_symlink()

    def test_fixture_overlay_value_wins_over_base(self, home: Home) -> None:
        """
        Test that the fixture overlay's editor.fontSize replaces the base value
        """
        assert self._settings(home)['editor.fontSize'] == 13

    def test_base_keys_are_present(self, home: Home) -> None:
        """
        Test that generic base keys survive the merge
        """
        settings = self._settings(home)
        assert settings['editor.rulers']            == [120]
        assert settings['python.languageServer']    == 'Pylance'
        assert settings['telemetry.telemetryLevel'] == 'off'

    @pytest.mark.parametrize(
        'key',
        [
            'claudeCode.claudeProcessWrapper',
            'claudeCode.disableLoginPrompt',
            'MATLAB.showFeatureNotAvailableError',
            'terminal.integrated.commandsToSkipShell',
        ],
    )
    def test_overlay_only_keys_are_absent(self, home: Home, key: str) -> None:
        """
        Test that keys the work overlay owns are absent when only the base and fixture overlay are rendered
        """
        assert key not in self._settings(home)

    @pytest.mark.parametrize('name', ['keybindings.json', 'snippets/.gitkeep'])
    def test_stowed_files_are_linked(self, home: Home, name: str) -> None:
        """
        Test that keybindings and the snippets placeholder are symlinked into the user directory
        """
        assert (home.path / self.USER_DIR / name).is_symlink()


class TestTerminalEditor:
    """
    Tests for the terminal, editor, and window-manager packages
    """
    @pytest.mark.parametrize(
        'relpath',
        [
            '.config/iterm2/com.googlecode.iterm2.plist',
            '.config/tmux/tmux.conf',
            '.config/tmux/tmux.conf.local',
            '.config/starship.toml',
            '.config/zed/settings.json',
            '.config/zsh/conf.d/05-homebrew.zsh',
            '.config/zsh/conf.d/30-iterm2.zsh',
            '.config/zsh/conf.d/36-fzf.zsh',
            '.config/zsh/conf.d/38-zoxide.zsh',
            '.config/zsh/conf.d/46-tmux.zsh',
            '.config/zsh/conf.d/80-starship.zsh',
            '.hammerspoon/init.lua',
            '.hammerspoon/Spoons/WifiNotifier.spoon/init.lua',
            '.hammerspoon/Spoons/ReloadConfiguration.spoon/init.lua',
            '.hammerspoon/Spoons/SpoonInstall.spoon/init.lua',
        ],
    )
    def test_key_files_are_linked(self, home: Home, relpath: str) -> None:
        """
        Test that each package's key files are stowed as symlinks
        """
        assert (home.path / relpath).is_symlink()

    def test_iterm2_working_directories_are_blank(self, home: Home) -> None:
        """
        Test that the iTerm2 profiles carry no hardcoded home path
        """
        text = (home.path / '.config' / 'iterm2' / 'com.googlecode.iterm2.plist').read_text(encoding='utf-8')
        assert '/Users/'                                           not in text
        assert '<key>Working Directory</key>\n\t\t\t<string></string>' in text

    def test_hammerspoon_loads_optional_overlay_hotkeys(self, home: Home) -> None:
        """
        Test that init.lua merges overlay hotkeys after the base mapping and before it is used to bind keys
        """
        text    = (home.path / '.hammerspoon' / 'init.lua').read_text(encoding='utf-8')
        defined = text.index('letterToWindowFilterMapping = {')
        merged  = text.index('pcall(require, "overlay")')
        bound   = text.index('for letter, filter in pairs(letterToWindowFilterMapping)')
        assert defined < merged < bound

    def test_hammerspoon_base_keeps_only_generic_apps(self, home: Home) -> None:
        """
        Test that the base hotkey table has no entries for work-only apps
        """
        text = (home.path / '.hammerspoon' / 'init.lua').read_text(encoding='utf-8')
        assert re.search(r'^\s*b\s*=\s*hs\.window\.filter\.new\(', text, re.MULTILINE)

        for letter in ('3', '4', 'q', 'r', 'w'):
            entry = rf"""^\s*(\[\s*['"]{letter}['"]\s*\]|{letter})\s*="""
            assert re.search(entry, text, re.MULTILINE) is None, letter

    def test_zed_ships_settings_only(self, home: Home) -> None:
        """
        Test that Zed's runtime state (prompts database) is not part of the package
        """
        assert sorted(p.name for p in (home.path / '.config' / 'zed').iterdir()) == ['settings.json']

    @pytest.mark.timing
    def test_zsh_is_clean_and_fast_with_all_snippets(self, home: Home, startup_budget: StartupBudget) -> None:
        """
        Test that an interactive shell with every terminal snippet sourced is clean and fast (best of three runs)
        """
        home.zsh('exit')  # warm caches before timing

        timings: list[float] = []
        for _ in range(TIMING_SAMPLES):
            start  = time.monotonic()
            result = home.zsh('exit')
            timings.append(time.monotonic() - start)
            assert result.returncode == 0
            assert result.stderr == ''

        startup_budget.check(timings, 'zsh -i')

    @pytest.mark.skipif(os.name != 'posix', reason='pseudo-terminals are POSIX-only')
    def test_zsh_on_a_terminal_is_clean(self, home: Home) -> None:
        """
        Test that a shell on a pseudo-terminal, where starship and fzf initialize, prints nothing, cold and warm
        """
        for _ in range(2):
            result, _elapsed = run_zsh_with_tty(home, 'exit')
            assert result.returncode == 0
            assert result.stdout.strip() == b'', result.stdout

    @pytest.mark.timing
    @pytest.mark.skipif(os.name != 'posix', reason='pseudo-terminals are POSIX-only')
    def test_zsh_on_a_terminal_is_clean_and_fast(self, home: Home, startup_budget: StartupBudget) -> None:
        """
        Test that a shell on a pseudo-terminal, where starship, fzf, and zoxide initialize, is clean and fast
        """
        run_zsh_with_tty(home, 'exit')  # warm caches before timing

        timings: list[float] = []
        for _ in range(TIMING_SAMPLES):
            result, elapsed = run_zsh_with_tty(home, 'exit')
            timings.append(elapsed)
            assert result.returncode == 0
            assert result.stdout.strip() == b'', result.stdout

        startup_budget.check(timings, 'tty zsh -i')

    @pytest.mark.skipif(os.name != 'posix', reason='pseudo-terminals are POSIX-only')
    @pytest.mark.parametrize(
        ('tool', 'function'),
        [
            ('starship', 'prompt_starship_precmd'),
            ('zoxide',   '__zoxide_hook'),
            ('fzf',      'fzf-file-widget'),
        ],
    )
    def test_tool_integrations_initialize_on_a_terminal(self, home: Home, tool: str, function: str) -> None:
        """
        Test that each tool's shell integration is defined when the tool is installed and a terminal is attached
        """
        if shutil.which(tool) is None:
            pytest.skip(f'{tool} not installed')

        probe = f'print -r -- "defined=${{+functions[{function}]}}${{+widgets[{function}]}}"'
        result, _elapsed = run_zsh_with_tty(home, probe)
        assert result.returncode == 0
        assert b'defined=1' in result.stdout or b'defined=01' in result.stdout, result.stdout

    @staticmethod
    def _fake_prefix(root: Path) -> Path:
        """
        Create a fake Homebrew prefix whose bin/brew is executable
        """
        brew = root / 'fakebrew' / 'bin' / 'brew'
        brew.parent.mkdir(parents=True)
        brew.write_text('#!/bin/sh\nexit 0\n', encoding='utf-8')
        brew.chmod(0o755)
        return brew.parent.parent

    def _zsh(self, home: Home, command: str, **env: str) -> subprocess.CompletedProcess[str]:
        """
        Run an interactive zsh command with a minimal PATH plus the given environment overrides
        """
        zsh = shutil.which('zsh')
        assert zsh is not None
        return subprocess.run(
            [zsh, '-i', '-c', command],
            capture_output=True,
            text=True,
            check=False,
            cwd=home.path,
            env={**home.env, 'PATH': '/usr/bin:/bin', **env},
        )

    def test_homebrew_prefix_is_probed_when_brew_is_off_path(self, home: Home, tmp_path: Path) -> None:
        """
        Test that a prefix listed in DOTFILES_BREW_PREFIXES is found, exported, and prepended to PATH
        """
        prefix = self._fake_prefix(tmp_path)
        result = self._zsh(
            home,
            'print -r -- $HOMEBREW_PREFIX $HOMEBREW_CELLAR $HOMEBREW_REPOSITORY; print -r -- ${(j: :)path}; '
            'print -r -- ${(j: :)fpath}',
            DOTFILES_BREW_PREFIXES=str(prefix),
        )
        assert result.returncode == 0
        assert result.stderr == ''

        exported, paths, fpath = (line.split() for line in result.stdout.strip().split('\n'))
        assert exported == [str(prefix), f'{prefix}/Cellar', str(prefix)]
        assert f'{prefix}/sbin' in paths
        assert paths.index(f'{prefix}/bin') < paths.index('/usr/bin')  # prepended, not appended
        assert f'{prefix}/share/zsh/site-functions' in fpath

    def test_homebrew_prefix_follows_brew_on_path(self, home: Home, tmp_path: Path) -> None:
        """
        Test that a brew already on PATH decides the prefix, without resolving symlinks
        """
        prefix = self._fake_prefix(tmp_path)
        result = self._zsh(home, 'print -r -- $HOMEBREW_PREFIX', PATH=f'{prefix}/bin:/usr/bin:/bin')

        assert result.returncode == 0
        assert result.stderr == ''
        assert result.stdout.strip() == str(prefix)

    def test_homebrew_probe_can_be_disabled(self, home: Home, tmp_path: Path) -> None:
        """
        Test that DOTFILES_BREW_PROBE=0 leaves Homebrew unconfigured when brew is not on PATH
        """
        prefix = self._fake_prefix(tmp_path)
        result = self._zsh(
            home, 'print -r -- "prefix=${HOMEBREW_PREFIX-unset}"',
            DOTFILES_BREW_PREFIXES=str(prefix), DOTFILES_BREW_PROBE='0',
        )

        assert result.returncode == 0
        assert result.stderr == ''
        assert result.stdout.strip() == 'prefix=unset'

    def test_fzf_default_command_requires_fd(self, home: Home, tmp_path: Path) -> None:
        """
        Test that FZF_DEFAULT_COMMAND is only exported when fd is available
        """
        absent = self._zsh(home, 'print -r -- "${FZF_DEFAULT_COMMAND-unset}"', DOTFILES_BREW_PROBE='0')
        assert absent.returncode == 0
        assert absent.stderr == ''
        assert absent.stdout.strip() == 'unset'

        fd = tmp_path / 'bin' / 'fd'
        fd.parent.mkdir()
        fd.write_text('#!/bin/sh\nexit 0\n', encoding='utf-8')
        fd.chmod(0o755)
        present = self._zsh(
            home, 'print -r -- "${FZF_DEFAULT_COMMAND-unset}"',
            DOTFILES_BREW_PROBE='0', PATH=f'{fd.parent}:/usr/bin:/bin',
        )
        assert present.stdout.strip().startswith('fd ')

    def test_path_and_fpath_have_no_duplicates(self, home: Home) -> None:
        """
        Test that nested shells do not accumulate duplicate PATH or FPATH entries
        """
        result = home.zsh(
            "zsh -i -c 'print -r -- ${#path} ${#${(u)path}} ${#fpath} ${#${(u)fpath}}'"
        )
        assert result.returncode == 0

        path_len, path_unique, fpath_len, fpath_unique = result.stdout.split()
        assert path_len  == path_unique
        assert fpath_len == fpath_unique


class TestOsTools:
    """
    Tests for the os_tools package
    """
    @pytest.mark.parametrize(
        'relpath',
        [
            '.config/btop/btop.conf',
            '.config/eza/theme.yml',
            '.config/fastfetch/config.jsonc',
            '.config/htop/htoprc',
            '.config/ranger/commands.py',
            '.config/ranger/rc.conf',
            '.config/ranger/rifle.conf',
            '.config/ranger/scope.sh',
            '.config/sshm/config.json',
            '.config/zsh/conf.d/49-os_tools.zsh',
            '.config/zsh/conf.d/90-banner.zsh',
        ],
    )
    def test_key_files_are_linked(self, home: Home, relpath: str) -> None:
        """
        Test that each os_tools file is stowed as a symlink
        """
        assert (home.path / relpath).is_symlink()

    def test_ssh_host_aliases_are_not_shipped(self, home: Home) -> None:
        """
        Test that host aliases live in ssh config.d files, not in a shell snippet
        """
        assert not (home.path / '.config' / 'zsh' / 'conf.d' / '60-ssh-hosts.zsh').exists()

    def test_eza_config_dir_is_exported_and_holds_the_theme(self, home: Home, tmp_path: Path) -> None:
        """
        Test that EZA_CONFIG_DIR is an exported absolute directory containing theme.yml
        """
        eza = tmp_path / 'bin' / 'eza'
        eza.parent.mkdir()
        eza.write_text('#!/bin/sh\nexit 0\n', encoding='utf-8')
        eza.chmod(0o755)

        env    = {**home.env, 'PATH': f'{eza.parent}:{home.env["PATH"]}'}
        result = subprocess.run(
            ['zsh', '-i', '-c', 'print -r -- "${(t)EZA_CONFIG_DIR} $EZA_CONFIG_DIR"'],
            capture_output=True, text=True, check=False, env=env, cwd=home.path,
        )
        assert result.returncode == 0
        assert result.stderr == ''

        kind, _, value = result.stdout.strip().partition(' ')
        assert kind == 'scalar-export'
        assert Path(value) == home.path / '.config' / 'eza'
        assert (Path(value) / 'theme.yml').is_file()

    def test_base_nas_alias_matches_the_ssh_host(self, home: Home) -> None:
        """
        Test that the bare nas command runs ssh against the base Host entry
        """
        result = home.zsh('print -r -- "${aliases[nas]-unset}"')
        assert result.stdout.strip() == 'ssh nas'

    def test_ls_aliases_require_eza(self, home: Home) -> None:
        """
        Test that `ls` is only aliased to eza when eza is installed
        """
        env    = {**home.env, 'PATH': '/usr/bin:/bin', 'DOTFILES_BREW_PROBE': '0'}
        result = subprocess.run(
            ['zsh', '-i', '-c', 'print -r -- "${aliases[ls]-unset}"'],
            capture_output=True,
            text=True,
            check=False,
            env=env,
            cwd=home.path,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == 'unset'

    @staticmethod
    def _fake_fastfetch(root: Path) -> Path:
        """
        Create a fastfetch stand-in that prints a marker, returning its directory
        """
        tool = root / 'ffbin' / 'fastfetch'
        tool.parent.mkdir()
        tool.write_text('#!/bin/sh\necho FASTFETCH-BANNER\n', encoding='utf-8')
        tool.chmod(0o755)
        return tool.parent

    @pytest.mark.skipif(os.name != 'posix', reason='pseudo-terminals are POSIX-only')
    @pytest.mark.parametrize(
        ('extra_env', 'shown'),
        [
            ({'DOTFILES_NO_BANNER': ''},  True),
            ({'DOTFILES_NO_BANNER': '1'}, False),
        ],
    )
    def test_banner_on_a_terminal_honors_the_opt_out(
        self, home: Home, tmp_path: Path, extra_env: dict[str, str], shown: bool
    ) -> None:
        """
        Test that the banner appears on a terminal unless DOTFILES_NO_BANNER is set
        """
        path       = f'{self._fake_fastfetch(tmp_path)}:{home.env["PATH"]}'
        result, _  = run_zsh_with_tty(home, 'exit', {'PATH': path, **extra_env})
        assert result.returncode == 0
        assert (b'FASTFETCH-BANNER' in result.stdout) is shown

    def test_banner_skips_shells_without_a_terminal(self, home: Home, tmp_path: Path) -> None:
        """
        Test that a shell whose stdout is a pipe never runs fastfetch, even when the opt-out is unset
        """
        env    = {**home.env, 'PATH': f'{self._fake_fastfetch(tmp_path)}:{home.env["PATH"]}', 'DOTFILES_NO_BANNER': ''}
        result = subprocess.run(
            ['zsh', '-i', '-c', 'exit'],
            capture_output=True,
            text=True,
            check=False,
            env=env,
            cwd=home.path,
        )

        assert result.returncode == 0
        assert result.stdout     == ''
        assert result.stderr     == ''

    @pytest.mark.skipif(os.name != 'posix', reason='pseudo-terminals are POSIX-only')
    def test_banner_skips_nested_shells(self, home: Home, tmp_path: Path) -> None:
        """
        Test that the banner is limited to the outermost shell (SHLVL 1)
        """
        path      = f'{self._fake_fastfetch(tmp_path)}:{home.env["PATH"]}'
        result, _ = run_zsh_with_tty(home, 'exit', {'PATH': path, 'DOTFILES_NO_BANNER': '', 'SHLVL': '2'})

        assert result.returncode == 0
        assert b'FASTFETCH-BANNER' not in result.stdout


class TestSsh:
    """
    Tests for ssh config composition
    """
    def test_config_includes_config_d(self, home: Home) -> None:
        """
        Test that the base ssh config includes per-layer config.d files
        """
        config = (home.path / '.ssh' / 'config').read_text(encoding='utf-8')
        assert config.splitlines()[1] == 'Include ~/.ssh/config.d/*'

    def test_base_and_overlay_hosts_share_config_d(self, home: Home) -> None:
        """
        Test that base and overlay host files are stowed into one real config.d directory
        """
        config_d = home.path / '.ssh' / 'config.d'
        assert     config_d.is_dir()
        assert not config_d.is_symlink()
        assert (config_d / 'personal').is_symlink()
        assert (config_d / 'fixture').is_symlink()

    def test_ssh_dir_is_real(self, home: Home) -> None:
        """
        Test that ~/.ssh is a real directory, so keys and known_hosts never land in the repository
        """
        ssh_dir = home.path / '.ssh'
        assert     ssh_dir.is_dir()
        assert not ssh_dir.is_symlink()

    @pytest.mark.parametrize('relpath', ['config', 'config.d/personal', 'config.d/fixture'])
    def test_stowed_files_are_not_group_or_world_writable(self, home: Home, relpath: str) -> None:
        """
        Test that ssh's ownership and permission check passes on each symlink target
        """
        target = (home.path / '.ssh' / relpath).resolve()
        info   = target.stat()
        assert info.st_uid == os.getuid()
        assert stat.S_IMODE(info.st_mode) & 0o022 == 0

    def test_base_host_has_no_address_or_user(self, home: Home) -> None:
        """
        Test that the base NAS entry names a MagicDNS host only: no IP address and no login name
        """
        text = (home.path / '.ssh' / 'config.d' / 'personal').read_text(encoding='utf-8')
        assert text.splitlines()[:2] == ['Host nas', '    HostName nas']
        assert re.search(r'^\s*User\s', text, re.MULTILINE) is None
        assert re.search(r'\d+\.\d+\.\d+\.\d+', text)       is None

    def test_keychain_option_is_ignorable_where_unsupported(self, home: Home) -> None:
        """
        Test that UseKeychain, an Apple-only option, is declared ignorable before it is set
        """
        lines = (home.path / '.ssh' / 'config').read_text(encoding='utf-8').splitlines()
        assert lines.index('    IgnoreUnknown UseKeychain') < lines.index('    UseKeychain yes')

    @pytest.mark.skipif(shutil.which('ssh') is None, reason='ssh not installed')
    def test_composed_config_resolves_hosts_from_every_layer(self, home: Home, tmp_path: Path) -> None:
        """
        Test that ssh parses the composed config and resolves base and overlay hosts

        ssh expands `~` in `Include` from the passwd home directory, so the include is pointed at the throwaway home
        in a copy of the config; the real ~/.ssh is never read.
        """
        config = (home.path / '.ssh' / 'config').read_text(encoding='utf-8')
        copy   = tmp_path / 'ssh_config'

        copy.write_text(config.replace('~/.ssh/config.d', str(home.path / '.ssh' / 'config.d')), encoding='utf-8')
        for host, expected in (('nas', 'nas'), ('fixture-host', 'fixture.example.com')):
            result = home.run('ssh', '-G', '-F', str(copy), host)
            assert result.returncode == 0, result.stderr
            assert f'hostname {expected}' in result.stdout.splitlines()


class TestVendoredNotices:
    """
    Tests for third-party license notices
    """
    RANGER_DIR = Path('stow') / 'os_tools' / '.config' / 'ranger'

    def test_notice_lists_every_vendored_ranger_file(self) -> None:
        """
        Test that NOTICE names each ranger file shipped by the os_tools package
        """
        notice  = (REPO_ROOT / 'NOTICE').read_text(encoding='utf-8')
        shipped = sorted(p.name for p in (REPO_ROOT / self.RANGER_DIR).iterdir())

        assert shipped == ['commands.py', 'rc.conf', 'rifle.conf', 'scope.sh']
        for name in shipped:
            assert f'{self.RANGER_DIR.as_posix()}/{name}' in notice

    def test_gpl_text_is_included(self) -> None:
        """
        Test that the GPL-3.0 text referenced by NOTICE is in the repository
        """
        text = (REPO_ROOT / 'docs' / 'licenses' / 'ranger-GPL-3.0.txt').read_text(encoding='utf-8')
        assert 'GNU GENERAL PUBLIC LICENSE' in text
        assert 'Version 3, 29 June 2007'    in text

    def test_modified_ranger_file_is_marked(self) -> None:
        """
        Test that rc.conf, the only modified ranger file, says so in a header
        """
        text = (REPO_ROOT / self.RANGER_DIR / 'rc.conf').read_text(encoding='utf-8')
        assert 'MODIFIED from ranger 1.9.4' in '\n'.join(text.splitlines()[:5])

    def test_readme_license_section_has_the_carve_out(self) -> None:
        """
        Test that the README points third-party files at NOTICE
        """
        readme = (REPO_ROOT / 'README.md').read_text(encoding='utf-8')
        assert 'Third-party files are under their own licenses; see [NOTICE](NOTICE).' in readme


class TestPortability:
    """
    Tests for the OS-conditional shell settings (they follow the host's $OSTYPE, whatever layout is stowed)
    """
    MACOS = sys.platform == 'darwin'

    def test_visual_editor(self, home: Home) -> None:
        """
        Test that VISUAL is Sublime Text on macOS and micro elsewhere
        """
        result = home.zsh('print -r -- $VISUAL')
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == ('subl' if self.MACOS else 'micro')

    def test_open_alias_is_macos_only(self, home: Home) -> None:
        """
        Test that `o` opens Finder on macOS and is not defined elsewhere
        """
        result = home.zsh('print -r -- "${aliases[o]-unset}"')
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == ('open .' if self.MACOS else 'unset')

    @pytest.mark.skipif(os.name != 'posix', reason='pseudo-terminals are POSIX-only')
    def test_banner_logo_follows_the_os(self, home: Home, tmp_path: Path) -> None:
        """
        Test that fastfetch gets the macOS logo on macOS only
        """
        tool = tmp_path / 'ffargs' / 'fastfetch'
        tool.parent.mkdir()
        tool.write_text('#!/bin/sh\necho "FFARGS:$*"\n', encoding='utf-8')
        tool.chmod(0o755)

        env       = {'PATH': f'{tool.parent}:{home.env["PATH"]}', 'DOTFILES_NO_BANNER': ''}
        result, _ = run_zsh_with_tty(home, 'exit', env)
        assert result.returncode == 0
        assert b'FFARGS:' in result.stdout
        assert (b'--logo macOS2' in result.stdout) is self.MACOS
