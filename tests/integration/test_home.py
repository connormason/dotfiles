"""
Throwaway-home integration tests: base layer + fixture overlay stowed and rendered into an empty HOME
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE   = REPO_ROOT / 'tests' / 'fixtures' / 'overlay'

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which('stow') is None, reason='GNU Stow not installed'),
    pytest.mark.skipif(shutil.which('zsh') is None, reason='zsh not installed'),
    pytest.mark.skipif(shutil.which('git') is None, reason='git not installed'),
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
            list(cmd), capture_output=True, text=True, check=False, env=self.env, cwd=cwd or self.path
        )

    def zsh(self, command: str) -> subprocess.CompletedProcess[str]:
        """
        Run an interactive zsh command inside this HOME
        """
        return self.run('zsh', '-i', '-c', command)


@pytest.fixture(scope='module')
def home(tmp_path_factory: pytest.TempPathFactory) -> Home:
    """
    Stow and render everything into a fresh HOME once per module
    """
    path     = tmp_path_factory.mktemp('home')
    registry = path / '.config' / 'dotfiles' / 'overlays'
    registry.parent.mkdir(parents=True)
    registry.write_text(f'{FIXTURE}\n', encoding='utf-8')
    env = {
        'HOME': str(path),
        'PATH': os.environ['PATH'],
        'TERM': 'dumb',
        'GIT_CONFIG_NOSYSTEM': '1',  # keep the machine's system gitconfig out of git assertions
        'XDG_CONFIG_HOME': str(path / '.config'),
        'XDG_STATE_HOME': str(path / '.local' / 'state'),
        'XDG_DATA_HOME': str(path / '.local' / 'share'),
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
    def test_interactive_zsh_is_clean_and_fast(self, home: Home) -> None:
        """
        Test that an interactive shell starts without stderr output in under 300 ms
        """
        home.zsh('exit')  # warm caches (compinit dump) before timing
        start  = time.monotonic()
        result = home.zsh('exit')
        elapsed = time.monotonic() - start
        assert result.returncode == 0
        assert result.stderr == ''
        assert elapsed < 0.3, f'zsh -i took {elapsed:.3f}s'

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
        env    = {**home.env, 'PATH': '/usr/bin:/bin'}
        result = subprocess.run(
            [zsh, '-i', '-c', 'cd / && cd ~'], capture_output=True, text=True, check=False, env=env, cwd=home.path
        )
        assert result.returncode == 0
        assert result.stderr == ''


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
        assert 'email' not in text
        assert '/Users/' not in text


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
        scripts = [
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
        direct = [
            Path(command.split()[0].strip('"').replace('$HOME', str(home.path), 1))
            for command in self._hook_commands(self._settings(home))
            if command.startswith('$HOME/')
        ]
        assert direct
        assert [str(script) for script in direct if not os.access(script, os.X_OK)] == []

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
        assert 'claude' in result.stdout
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
            ('git@github.com:connormason/x.git',            PERSONAL),
            ('https://github.com/connormason/x.git',        PERSONAL),
            ('ssh://git@github.com/connormason/x.git',      PERSONAL),
            ('https://someuser@github.com/connormason/x.git', PERSONAL),
            (None,                                          DEFAULT),
            ('git@git.example.com:team/x.git',              DEFAULT),
            ('git@github.com:connormason2/x.git',           DEFAULT),
        ],
    )
    def test_identity_follows_remote(self, home: Home, remote: str | None, expected: str) -> None:
        """
        Test that personal GitHub remotes get the personal identity and everything else the overlay's default
        """
        name = 'repo-' + ''.join(c if c.isalnum() else '-' for c in str(remote))
        repo = self._repo(home, name, remote)
        result = home.run('git', 'config', 'user.email', cwd=repo)
        assert result.stdout.strip() == expected
