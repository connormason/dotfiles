# Dev-Env Port Implementation Plan (Phase A part 2 + Phase B)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the work repo's generic dev-environment stack into this repo's layered engine, add base bootstrap stages
and the `personal-mac` profile, retire the Ansible macOS side, and validate on the personal MacBook (Phase B).

**Architecture:** Each work-repo package becomes a base stow package here, with every employer-specific item moved to a
local, never-committed **overlay staging directory** that later seeds the work overlay (Phase C, work repo). A
throwaway-home integration test (macOS CI) proves the base plus a fixture overlay produce a clean shell, correct git
identity, ssh includes, and valid rendered settings.

**Tech Stack:** GNU Stow, zsh, bash 3.2, Python 3.9+ stdlib, pytest, GitHub Actions (macOS).

**Spec:** `docs/plans/2026-10/2026-10-26-dev-env-base-overlay-design.md`
**Prerequisite plan (must be complete):** `docs/plans/2026-10/2026-10-27-dev-env-engine-plan.md`

## Global Constraints

All Global Constraints of the engine plan apply unchanged (branch `dev-env-base`; every uv call via
`scripts/hooks/uv-public.sh`; public-repo naming rules; `~/dotfiles` is read-only reference; bash 3.2; Python style;
test conventions). In addition:

- **Private leak patterns must be installed** (`~/.config/dotfiles/leak-patterns.txt`, engine plan Task 1) before any
  task here starts. Every ported file passes `scripts/hooks/check-leaks.py` with those patterns.
- **Overlay staging directory:** `.superpowers/overlay-staging/` at the worktree root (git-excluded via
  `.git/info/exclude`; never committed; worktree-isolated agents cannot write outside the worktree).
  Layout mirrors a future overlay: `stow/<overlay-pkg>/<$HOME-relative path>`, `render/<id>.json`,
  `bootstrap/<file>`. Every move into staging is appended as one line to `.superpowers/overlay-staging/STAGING.md`:
  `<source file:lines> -> <staging path> — <generic one-line reason>`. Staging is the Phase C input.
- **Every zsh snippet must be safe when its tool is absent** (guard with `have`-style checks / `source_if_exists`), so
  `zsh -i -c exit` in an empty `$HOME` prints nothing to stderr.
- No hardcoded home paths (`/Users/<name>`), and no `~/dotfiles` / `~/dotfiles-personal` paths: use `$HOME`, or
  `$DOTFILES_REPO` (exported by the shell package, see Task 2).

### Port protocol (referenced by every package task)

1. Copy only tracked files: `git -C ~/dotfiles ls-files -z stow/<pkg> | (cd ~/dotfiles && xargs -0 tar cf -) | tar xf - -C .`
   (run from this repo's root; the paths land under `stow/<pkg>/`).
2. Remove the files and lines the task lists under **Employer content** — move each into staging at the stated
   overlay path and log it in `STAGING.md`.
3. Run `scripts/hooks/check-leaks.py stow/<pkg>/` (all files) with private patterns active. Every finding is either
   moved to staging (employer content the task did not anticipate — log it and mention it in your report) or is a
   genuine false positive that you report (do not add `leak-guard: allow` markers without listing them in the report).
4. Replace hardcoded paths per the Global Constraints.
5. Add the package's assertions to `tests/integration/test_home.py` (Task 1), run it, commit.

## File Map

| Path                                              | Action  | Responsibility                                               |
| ------------------------------------------------- | ------- | ------------------------------------------------------------ |
| `tests/integration/test_home.py`                  | Create  | Throwaway-home integration test                              |
| `tests/fixtures/overlay/`                         | Create  | Generic fixture overlay exercising every composition point   |
| `stow/{shell,git,python,node,claude,vscode,…}/`   | Create  | Base packages                                                |
| `stow/ssh/`                                       | Create  | `~/.ssh/config` with `Include ~/.ssh/config.d/*`             |
| `render/{claude,vscode}.json`                     | Create  | Base render fragments                                        |
| `bootstrap/NN-*.sh`, manifests                    | Create  | Base stages + Brewfile / uv-tools / vscode-extensions / repos |
| `profiles/personal-mac/`                          | Create  | Personal-only overlay                                        |
| `stow/README.md`, `bootstrap/README.md`           | Create/Modify | Package and stage tables                               |
| `tests/unit/test_docs_consistency.py`             | Create  | Tables match the tree                                        |
| Ansible macOS roles, `local_bootstrap.sh`, …      | Delete  | Superseded                                                   |

---

### Task 1: Throwaway-home integration harness and fixture overlay

**Files:**

- Create: `tests/integration/__init__.py` (empty), `tests/integration/test_home.py`
- Create: `tests/fixtures/overlay/stow/fixture-overlay/.config/zsh/conf.d/31-fixture.zsh`
- Create: `tests/fixtures/overlay/stow/fixture-overlay/.gitconfig.overlay`
- Create: `tests/fixtures/overlay/stow/fixture-overlay/.ssh/config.d/fixture`
- Create: `tests/fixtures/overlay/render/claude.json`, `tests/fixtures/overlay/render/vscode.json`
- Modify: `pyproject.toml` (`markers`: add `"integration: Throwaway-home integration tests"`)

**Interfaces:**

- Produces: pytest fixture `home(tmp_path) -> Home` where `Home` is a dataclass with `path: Path`, `env: dict[str, str]`
  (HOME, XDG dirs, `DOTFILES_OVERLAYS_FILE` registering `tests/fixtures/overlay`), and methods
  `run(*cmd) -> CompletedProcess[str]` and `zsh(command) -> CompletedProcess[str]` (`zsh -i -c command` in that
  HOME). The fixture runs `stow.sh` and `render.py --force` once; later tasks add test methods only.

- [ ] **Step 1: Fixture overlay (generic content only)**

```zsh
# tests/fixtures/overlay/stow/fixture-overlay/.config/zsh/conf.d/31-fixture.zsh
export DOTFILES_FIXTURE_OVERLAY=1
```

```ini
# tests/fixtures/overlay/stow/fixture-overlay/.gitconfig.overlay
[user]
    email = work@example.com
```

```
# tests/fixtures/overlay/stow/fixture-overlay/.ssh/config.d/fixture
Host fixture-host
    HostName fixture.example.com
```

`tests/fixtures/overlay/render/claude.json`: `{"env": {"FIXTURE_OVERLAY": "1"}, "$unmanaged": ["fixtureInstallerKey"]}`
`tests/fixtures/overlay/render/vscode.json`: `{"editor.fontSize": 13}`

- [ ] **Step 2: Harness**

`tests/integration/test_home.py`:

```python
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
        return subprocess.run(list(cmd), capture_output=True, text=True, check=False, env=self.env, cwd=cwd or self.path)

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
```

Tests for packages (zsh startup, git identity, ssh) are added by the package tasks.

- [ ] **Step 3: Run and commit**

Run: `scripts/hooks/uv-public.sh run --group test pytest tests/integration/test_home.py` → PASS (no base packages yet:
only the overlay's files are linked; `render.py --force` renders the overlay fragment alone).

```bash
git add tests/integration tests/fixtures pyproject.toml
git commit -m "test: throwaway-home integration harness with fixture overlay"
```

---

### Task 2: `shell` package

**Files:** `stow/shell/**` (ported), `tests/integration/test_home.py` (add `TestShell`)

**Employer content (move to staging):**

- The whole device-profile shell file at the package root → `stow/work-shell/<same name>`.
- In the misc-tools snippet: the alias block for internal CLIs and the alias pointing at an internal blob-storage host →
  `stow/work-shell/.config/zsh/conf.d/35-work-tools.zsh` (keep generic tools — `lazyssh`, `pkl`, `autojump` — in base).
- In the oh-my-zsh snippet: a comment naming an employer-only package's snippet → reword the comment generically
  (no staging needed).

**Changes beyond the port protocol:**

1. `.zshrc`: after the `conf.d` loop, add the machine-local hook:

```zsh
# Machine-local, untracked additions (sourced last)
[[ -r "$HOME/.zshrc.local" ]] && source "$HOME/.zshrc.local"
```

2. `00-lib.zsh`: append the repo locator (this file is a symlink into `<repo>/stow/shell/.config/zsh/conf.d/`):

```zsh
# Repo root: resolve this snippet's symlink, then climb conf.d/zsh/.config/shell/stow/<repo>
export DOTFILES_REPO="${DOTFILES_REPO:-${${(%):-%x}:A:h:h:h:h:h:h}}"
```

3. `50-directories.zsh`: the `dotfiles` alias becomes `alias dotfiles='cd "$DOTFILES_REPO"'`.
4. Every snippet must be clean in an empty HOME (no oh-my-zsh, no plugins): guard `source` calls with
   `source_if_exists` or `[[ -r … ]]`, and tool initializations with `(( $+commands[tool] ))`.

**Test additions** (`TestShell` in `test_home.py`):

```python
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
```

If the 300 ms budget fails on CI only (cold runners), report the measured times rather than loosening the bound
silently; the bound is a spec requirement.

- [ ] **Step 1:** Port per protocol; apply changes 1–4.
- [ ] **Step 2:** Add `TestShell`; run `scripts/hooks/uv-public.sh run --group test pytest tests/integration/test_home.py` → PASS.
- [ ] **Step 3:** `prek run --files $(git ls-files -o -m --exclude-standard stow/shell tests)` → pass.
- [ ] **Step 4:** Commit `feat(stow): shell package (zsh conf.d loader, helpers, aliases)`.

---

### Task 3: `git` package with per-remote identity

**Files:** `stow/git/**`, `tests/integration/test_home.py` (add `TestGit`)

**Employer content (move to staging):**

- `.gitconfig`: the alias that calls an internal CLI → staging `stow/work-git/.gitconfig.overlay` (alongside the work
  default identity, which Phase C fills in from the work inventory).
- `.config/gh/hosts.yml` → do not port at all (gh writes it; it holds the internal GitHub host). Not staged.
- `.git-template/hooks/pre-commit` → do not port; replace (below).

**Changes beyond the port protocol:**

1. `.gitconfig`: delete `commit.template` (points at a file that does not exist); replace the `[include]` of
   `~/.gitconfig.local` with this block at the **end** of the file:

```ini
[user]
    name = Connor Mason
    email = connor@conmason.com
[include]
    ; work overlay (or machine-local overrides): default identity, extra aliases
    path = ~/.gitconfig.overlay
[includeIf "hasconfig:remote.*.url:git@github.com:connormason/**"]
    ; personal remotes always use the personal identity, even on a machine whose default is the work identity
    path = ~/.config/git/identity-personal
[includeIf "hasconfig:remote.*.url:https://github.com/connormason/**"]
    path = ~/.config/git/identity-personal
```

(The personal name and email are already public in this repo's history.)

2. New `stow/git/.config/git/identity-personal`:

```ini
[user]
    name = Connor Mason
    email = connor@conmason.com
```

3. `.git-template/hooks/pre-commit`: use the generic prek delegate (same content as `roles/git/templates/pre-commit.j2`,
   which has no Jinja syntax), mode 755.

**Test additions:**

```python
class TestGit:
    """
    Tests for per-remote git identity
    """
    def _repo(self, home: Home, name: str, remote: str) -> Path:
        """
        Create a repo with an origin remote inside HOME
        """
        repo = home.path / name
        home.run('git', 'init', '-q', '--template=', str(repo))
        home.run('git', '-C', str(repo), 'remote', 'add', 'origin', remote)
        return repo

    def test_personal_remote_uses_personal_identity(self, home: Home) -> None:
        """
        Test that a personal GitHub remote overrides the overlay's default identity
        """
        repo = self._repo(home, 'personal', 'git@github.com:connormason/example.git')
        assert home.run('git', 'config', 'user.email', cwd=repo).stdout.strip() == 'connor@conmason.com'

    def test_other_remote_uses_overlay_default(self, home: Home) -> None:
        """
        Test that any other remote gets the overlay's default identity
        """
        repo = self._repo(home, 'other', 'git@git.example.com:team/example.git')
        assert home.run('git', 'config', 'user.email', cwd=repo).stdout.strip() == 'work@example.com'
```

- [ ] **Step 1:** Port per protocol; apply changes 1–3.
- [ ] **Step 2:** Add `TestGit`; run the integration tests → PASS.
- [ ] **Step 3:** Commit `feat(stow): git package with per-remote identity`.

---

### Task 4: `python` and `node` packages

**Files:** `stow/python/**`, `stow/node/**`

**Employer content (move to staging):**

- `.pip/pip.conf` (internal indexes) → staging `stow/work-python/.pip/pip.conf` (whole file; base ships none).
- `.config/uv/uv.toml` (internal extra index) → staging `stow/work-python/.config/uv/uv.toml` (whole file; base ships
  none).
- hatch `config.toml`: the publish-repository URL and the work email → staging
  `stow/work-python/.config/zsh/conf.d/43-work-python.zsh` as `export HATCH_INDEX_REPO=…` (and drop the email line —
  hatch falls back to git config). Also delete the data/cache directory lines (they restate macOS defaults and hardcode
  the home path).
- The IPython startup file for internal device tooling → staging `stow/work-python/.ipython/profile_default/startup/`.
- `42-python.zsh`: the `venvshell`/`v` aliases (they call a script that lives only in the work repo) → staging
  `43-work-python.zsh`.
- `.npmrc` (internal registry + corporate CA bundle) → staging `stow/work-node/.config/zsh/conf.d/45-work-node.zsh` as
  `NPM_CONFIG_REGISTRY` / `NPM_CONFIG_CAFILE` exports (base ships no `.npmrc`).

**Test additions:** in `TestShell`, assert `home.zsh('print -r -- $WORKON_HOME').returncode == 0` still has empty stderr
(covered by the existing clean-startup test once these snippets exist — re-run it).

- [ ] **Step 1:** Port both packages per protocol.
- [ ] **Step 2:** Integration tests → PASS (startup still clean and < 300 ms).
- [ ] **Step 3:** Commit `feat(stow): python and node packages`.

---

### Task 5: `claude` package and base render fragment

**Files:** `stow/claude/.claude/**`, `stow/claude/.config/zsh/conf.d/32-claude.zsh`, `render/claude.json`

**Port these (generic) directories/files** per protocol: `agents/` (generic agents only), `hooks/` (generic hooks only),
`rules/`, `skills/` (generic skills only), `commands/` (generic only), `scripts/`, `CLAUDE.md`,
`claude-devtools-config.json`, `plugins/config.json`. Do **not** port `settings.json` (it becomes a render fragment) or
any `.backups/` / `__pycache__/`.

**Employer content (move to staging, path `stow/work-claude/.claude/…` unless stated):**

- Agents, hooks, skills, and commands that exist only for employer tooling (the explorer report's EMPLOYER column;
  re-derive with the private leak guard). The permission-reviewer hook family is employer-specific (internal model
  endpoint and auth).
- The entire employer-specific config directory under `.claude/` and the statusline bundle directory (copied from an
  internal repository — provenance excludes it from the public base).
- In the ansible agent: two lines describing the employer environment and an internal Ansible collection → reword
  generically.
- In two generic skills' docs: example hostnames/badges that name internal systems → replace with neutral examples
  (`github.example.com`, a generic badge). No staging.
- `CLAUDE.md`: the branch-workflow section for internal tooling and the internal tracker mention in the commit
  guidance → staging `stow/work-claude/.claude/rules/work-workflow.md` (as a rule file).
- `32-claude.zsh`: the corporate CA export → staging `stow/work-claude/.config/zsh/conf.d/33-work-claude.zsh`.
- `scripts/dotclaude-cleanup.sh` / its command doc: the employer-specific cleanup sections → staging as an overlay
  script, keeping the generic core in base.
- One third-party skill whose license is not stated in its files: port it only if a permissive license file is present
  in the skill directory; otherwise stage it (`stow/work-claude/.claude/skills/<name>`) and list it in the report.

**Base render fragment `render/claude.json`:** build it from the work `settings.json`, keeping **only** these keys and
entries (everything else → staging `render/claude.json`, verbatim):

- Top-level: `attribution`, `autoMemoryEnabled`, `effortLevel`, `model`, `modelSettings`, `preferredNotifChannel`,
  `sandbox`, `skipWebFetchPreflight`, `skipWorkflowUsageWarning`, `theme`, `verbose`, `worktree`, `statusLineConfig`,
  `spinnerVerbs`.
- `autoMode`: `allow`, `hard_deny`, `soft_deny` in full; from `environment`, only the generic lines.
- `env`: only the generic keys (telemetry/timeouts/columns/tool-search/autoupdate-plugins group).
- `hooks`: only the generic hooks, with every command path rewritten from an absolute home path to
  `$HOME/.claude/hooks/<file>`.
- `permissions`: `defaultMode`, all `deny` entries, and only the generic `allow` entries.
- Omit `enabledPlugins` and `extraKnownMarketplaces` from the base for now (Phase B decides the public plugin set).
- `spinnerVerbs`: drop the one entry that names the employer; **the user reviews the remaining list** before commit
  (some entries are profane). Ask the controller to obtain the user's decision; do not decide yourself.

**Test additions:**

```python
class TestClaude:
    """
    Tests for the claude package and render fragment
    """
    def test_settings_hooks_use_home_relative_paths(self, home: Home) -> None:
        """
        Test that no rendered hook command embeds an absolute home path
        """
        text = (home.path / '.claude' / 'settings.json').read_text(encoding='utf-8')
        assert '/Users/' not in text

    def test_hook_scripts_exist_for_every_hook(self, home: Home) -> None:
        """
        Test that every rendered hook command points at a stowed script
        """
        settings = json.loads((home.path / '.claude' / 'settings.json').read_text(encoding='utf-8'))
        for groups in settings.get('hooks', {}).values():
            for group in groups:
                for hook in group['hooks']:
                    script = hook['command'].split()[0].replace('$HOME', str(home.path)).strip('"')
                    if script.startswith(str(home.path)):
                        assert Path(script).exists(), script
```

- [ ] **Step 1:** Port per protocol; build `render/claude.json`; stage the rest.
- [ ] **Step 2:** Get the user's `spinnerVerbs` decision via the controller; apply it.
- [ ] **Step 3:** Integration tests → PASS. `render.py --diff claude` against the real `~/.claude/settings.json` must
  not be run with `--force` on this machine — use only the throwaway home.
- [ ] **Step 4:** Commit `feat(stow): claude package and base settings fragment`.

---

### Task 6: `vscode` package and base render fragment

**Files:** `stow/vscode/Library/Application Support/Code/User/{keybindings.json,snippets/.gitkeep}`, `render/vscode.json`,
`bootstrap/vscode-extensions.txt`

**Employer content (move to staging):**

- `settings.json` keys that point at an employer wrapper for the Claude extension (two keys) → staging
  `render/vscode.json`.
- Settings for a commercial numerical-computing product used only at work (two keys) and its extension in the
  extensions manifest → staging `render/vscode.json` and staging `bootstrap/vscode-extensions.txt`.

**Changes:** `settings.json` is not stowed; its remaining keys become `render/vscode.json` (base). The extensions
manifest is copied to `bootstrap/vscode-extensions.txt` minus the staged line.

- [ ] **Step 1:** Port; build the fragment; stage the rest.
- [ ] **Step 2:** Integration: add `assert 'editor.fontSize' in json.loads(...vscode settings...)` (fixture overlay
  value) and that base keys are present.
- [ ] **Step 3:** Commit `feat(stow): vscode package and base settings fragment`.

---

### Task 7: Terminal and editor packages (`iterm2`, `tmux`, `starship`, `zed`, `fzf`, `zoxide`, `homebrew`, `hammerspoon`)

**Files:** `stow/{iterm2,tmux,starship,zed,fzf,zoxide,homebrew,hammerspoon}/**`

**Package notes:**

- `iterm2`: blank the two `Working Directory` values that hardcode the home path (both profiles use "Custom Directory =
  No", so the value is unused).
- `zed`: port `settings.json` only (the prompts database is app runtime state).
- `homebrew`: replace the comment URL pointing at an internal Homebrew mirror with `https://brew.sh`.
- `hammerspoon`: in `init.lua`, move the hotkey entries for employer-internal apps and corporate collaboration apps
  (the explorer report lists five letters) → staging `stow/work-hammerspoon/.hammerspoon/overlay.lua`, written as a
  module returning a table `{ [letter] = <same value as in init.lua> }`. In base `init.lua`, immediately after the
  `letterToWindowFilterMapping` table is defined and before it is used, add:

```lua
-- Optional overlay hotkeys: ~/.hammerspoon/overlay.lua returns { [letter] = mapping }
local hasOverlay, overlayMappings = pcall(require, "overlay")
if hasOverlay and type(overlayMappings) == "table" then
    for letter, mapping in pairs(overlayMappings) do
        letterToWindowFilterMapping[letter] = mapping
    end
end
```

- `tmux`, `starship`, `fzf`, `zoxide`: straight ports.

- [ ] **Step 1:** Port each per protocol.
- [ ] **Step 2:** Integration tests → PASS (startup still clean and < 300 ms with all snippets present).
- [ ] **Step 3:** Commit `feat(stow): terminal, editor, and window-manager packages`.

---

### Task 8: `os_tools` and `ssh` packages

**Files:** `stow/os_tools/**`, `stow/ssh/.ssh/config`, `stow/ssh/.ssh/config.d/personal`

**Employer content:** the ssh-host alias snippet's lab-host aliases (internal hostnames) → staging
`stow/work-ssh/.ssh/config.d/work` converted to `Host` blocks. The snippet's personal NAS alias becomes a `Host` block in
base `config.d/personal` using the Tailscale MagicDNS name (no LAN IP, no username in the public repo). Delete the
alias snippet from base once both are converted. Also fix the os_tools snippet's `EZA_CONFIG_DIR` (quoted `~`, not
exported) to `export EZA_CONFIG_DIR="$HOME/.config/eza"`.

`stow/ssh/.ssh/config`:

```
# Per-layer host definitions (base: config.d/personal; overlays add their own files)
Include ~/.ssh/config.d/*

Host *
    AddKeysToAgent yes
    UseKeychain yes
    IdentityFile ~/.ssh/id_ed25519
```

`stow/ssh/.ssh/config.d/personal`:

```
Host nas
    HostName nas
```

**Test additions:**

```python
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
        assert config_d.is_dir()
        assert not config_d.is_symlink()
        assert (config_d / 'personal').is_symlink()
        assert (config_d / 'fixture').is_symlink()
```

(ssh expands `~` in `Include` from the account's home directory, not `$HOME`, so resolution through `ssh -G` cannot be
isolated in a throwaway home; Phase B step B4 verifies it on the real machine.)

- [ ] **Step 1:** Port and convert; write the ssh package.
- [ ] **Step 2:** Integration tests → PASS.
- [ ] **Step 3:** Commit `feat(stow): os_tools and ssh packages`.

---

### Task 9: Base bootstrap stages and manifests

**Files:** `bootstrap/{20-ssh-key,50-brew,60-macos,72-vscode,80-repos,90-python,95-dotfiles,96-iterm2,97-render}.sh`,
`bootstrap/{Brewfile,uv-tools.txt,repos.txt}`, `bootstrap/README.md`

Every stage starts with the work-repo header pattern (`set -euo pipefail`, `HERE=…`, `REPO=…`,
`source "$HERE/lib.sh"`), uses `run`/`try` for every mutation, and reads manifests with `manifest_files <name>`.

| Stage           | Source in work repo   | Change                                                                                                                                                                                                                     |
| --------------- | --------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `20-ssh-key`    | `20-ssh-key.sh`       | Generic: create `~/.ssh/id_ed25519` if missing; test `ssh -T git@github.com`; if not authenticated print the public key and `gh ssh-key add ~/.ssh/id_ed25519.pub`.                                                         |
| `50-brew`       | `50-brew.sh`          | If `brew` is absent, install Homebrew with the checksum-verified installer logic from this repo's `local_bootstrap.sh` (move it here). No tap trust step. Then for each `manifest_files Brewfile`: `run brew bundle --file "$f"`; drift → warning. |
| `60-macos`      | `60-macos.sh`         | Straight port (generic preferences).                                                                                                                                                                                       |
| `72-vscode`     | `72-vscode.sh`        | Read the union of `manifest_files vscode-extensions.txt`.                                                                                                                                                                  |
| `80-repos`      | `80-repos.sh`         | Read `manifest_files repos.txt`; split each non-comment line on whitespace into `name url` (fixes the work repo's tab-only parsing bug); clone into `$HOME/name` if absent.                                                 |
| `90-python`     | `90-python.sh`        | uv comes from the Brewfile (no installer fallback); install tools from the union of `manifest_files uv-tools.txt` with the same line syntax.                                                                              |
| `95-dotfiles`   | `95-dotfiles.sh`      | `run "$REPO/stow.sh" --backup-conflicts`; keep the oh-my-zsh unattended install and plugin clones; delete the `.gitconfig.local` rendering (identity is static now).                                                     |
| `96-iterm2`     | `70-iterm2.sh`        | Renumbered to run after `95-dotfiles` (fixes the work repo's ordering bug: the prefs folder must exist first).                                                                                                             |
| `97-render`     | new                   | `try python3 "$REPO/scripts/dotfiles/render.py"`; on drift, warn with the `run.py render --diff` hint (bootstrap continues).                                                                                               |

Manifests:

- `bootstrap/Brewfile` ← work Brewfile minus employer taps/formulae/casks (six lines) and a remote-desktop app used only
  for work (→ staging `bootstrap/Brewfile`). Ensure `stow`, `uv`, `gh`, `git`, `zsh` and `fzf-tab` (sourced by the
  completion snippet but missing from the work Brewfile) are present.
- `bootstrap/uv-tools.txt` ← work list minus employer tools and one tool's employer-only `--with` flag (→ staging).
- `bootstrap/repos.txt` ← header comment only (`# name  url`); personal repos are added as needed.

Delete `local_bootstrap.sh` in Task 11, after `50-brew` has absorbed its Homebrew installer.

Verification:

- Run: `/bin/bash bootstrap/bootstrap.sh --list` → base stages in order.
- Run: `HOME=$(mktemp -d) /bin/bash bootstrap/bootstrap.sh --dry-run --no-log` → every stage completes in dry-run.
- Add a CI step to the `pytest (macOS)` job after `Pytest`:
  `HOME="$RUNNER_TEMP/home" bash bootstrap/bootstrap.sh --dry-run --no-log` (with `mkdir -p "$RUNNER_TEMP/home"`).
- Update `bootstrap/README.md` stage table (one row per stage, id in the first column).

- [ ] **Step 1:** Port/write stages and manifests.
- [ ] **Step 2:** Dry-run locally and in a throwaway HOME; shellcheck/shfmt via prek.
- [ ] **Step 3:** Commit `feat(bootstrap): base stages and manifests`.

---

### Task 10: `profiles/personal-mac` overlay

**Files:** `profiles/personal-mac/bootstrap/Brewfile`, `profiles/personal-mac/README.md`

`Brewfile` (personal-only apps from the old `roles/macos` lists, minus anything already in the base Brewfile):

```ruby
# Personal-Mac-only applications (registered as an overlay only on the personal MacBook)
cask "claude-code"
cask "macdown"
cask "pycharm-ce"
cask "signal"
cask "spotify"
cask "sublime-text"
mas "Amphetamine", id: 937984704
mas "iStat Menus", id: 1319778037
mas "Tailscale", id: 1475387142
```

Verify each id/cask name against the old `roles/macos/defaults/main.yml` (copy ids from there, not from this plan) and
drop any entry already in `bootstrap/Brewfile`. README: what the profile is, how to register it
(`echo "$PWD/profiles/personal-mac" >> ~/.config/dotfiles/overlays`).

- [ ] **Step 1:** Write the profile; `bash -c 'source bootstrap/lib.sh; DOTFILES_OVERLAYS_FILE=<tmp registry> manifest_files Brewfile'`
  lists base then profile.
- [ ] **Step 2:** Commit `feat(profiles): personal-mac overlay`.

---

### Task 11: Retire the Ansible macOS side and update docs

**Files:**

- Delete: `roles/{iterm,python,starship,hammerspoon,macos,macos_settings,macos_dock,link_dotfile}/`,
  `playbooks/local_bootstrap.yml`, `local_bootstrap.sh`, and `library/*.py` modules used only by deleted roles (verify
  with `git grep` before deleting).
- Modify: roles shared with the NAS playbook (`git`, `ssh`, `zsh`, `tailscale`): remove macOS-only tasks/branches;
  `roles/requirements.yml`: drop collections/roles only the deleted roles used.
- Modify: `README.md`, `roles/README.md`, `playbooks/README.md`, `.ctx/ARCHITECTURE.md`, `.ctx/CONVENTIONS.md`,
  `.ctx/BUILD.md`, `CLAUDE.md` (entry points: macOS = `bootstrap/bootstrap.sh`; NAS unchanged).
- Create: `stow/README.md` (package table: package, what it configures, conf.d snippets), and
  `tests/unit/test_docs_consistency.py` (port the work repo's stage-table test; replace its hardcoded-array test with
  "every directory under `stow/` appears in `stow/README.md`'s table and vice versa").

- [ ] **Step 1:** `git grep -n -E 'local_bootstrap|link_dotfile|macos_settings|macos_dock|osx_pmset|configure_network_interfaces'`
  before and after; after must only show `docs/plans/`.
- [ ] **Step 2:** `ansible-playbook --syntax-check -i localhost, playbooks/nas_bootstrap.yml` still passes.
- [ ] **Step 3:** Full suite + `prek run --all-files` → pass.
- [ ] **Step 4:** Commit `refactor: retire Ansible macOS configuration in favor of the stow engine`.

---

### Task 12: Publish Phase A

- [ ] **Step 1:** Controller confirms with the user, then pushes `dev-env-base` and opens a PR (CI must be green:
  lint, leak guard, `pytest (macOS)` incl. integration + bootstrap dry-run). Per the user's preference, remove the
  local worktree after the PR is opened (keep the branch).
- [ ] **Step 2:** Back up `.superpowers/overlay-staging/` (it is the only copy of the Phase C input) — e.g.
  copy it into the work repo's working tree **outside git tracking**, or into a private location the user chooses.

---

## Phase B — Personal MacBook (runbook, executed by the user with assistance)

These steps run on the personal MacBook after the Phase A PR merges. They are a checklist, not subagent tasks.

- [ ] **B1. Prepare:** macOS updated; `xcode-select --install`; `git clone git@github.com:connormason/dotfiles.git
  ~/dotfiles-personal`; register the profile:
  `mkdir -p ~/.config/dotfiles && echo "$HOME/dotfiles-personal/profiles/personal-mac" > ~/.config/dotfiles/overlays`.
- [ ] **B2. Inventory and clear the old setup:** list Ansible-era links and files:
  `find ~ -maxdepth 4 -type l -lname '*dotfiles*' 2>/dev/null` and the old `~/.zshrc` / `~/.p10k.zsh` / `~/.gitconfig`.
  Copy them to `~/.dotfiles-backup/pre-base/`, then remove the links.
- [ ] **B3. Bootstrap:** `~/dotfiles-personal/bootstrap/bootstrap.sh --dry-run`, review, then
  `~/dotfiles-personal/bootstrap/bootstrap.sh --verify`. Resolve every doctor failure.
- [ ] **B4. Verify:** new terminal (clean, fast); `git config user.email` inside `~/dotfiles-personal` is the personal
  identity; `ssh -G nas | grep -i '^hostname'` resolves through `~/.ssh/config.d/personal`; Claude Code starts and logs
  in; VS Code opens with base settings.
- [ ] **B5. Resolve the spec's clarifications by experiment:**
  1. Install the desired public plugin marketplaces/plugins in Claude Code, then `run.py render --diff claude` and move
     the resulting `enabledPlugins` / `extraKnownMarketplaces` into `render/claude.json`; note how duplicates across
     marketplaces behave.
  2. Use VS Code normally for a few days; run `run.py render --check vscode` daily and record whether VS Code rewrites
     `settings.json` on its own (drift guard noise).
  3. In a terminal (not inside Claude Code), probe `--settings` layering: in an empty directory create
     `.claude/settings.json` = `{"env": {"LAYER_PROJ": "project"}, "hooks": {"SessionStart": [{"hooks": [{"type":
     "command", "command": "echo project-hook >> out.txt"}]}]}}` and `overlay.json` = `{"env": {"LAYER_OVERLAY":
     "overlay", "LAYER_PROJ": "overlay"}, "hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "echo
     overlay-hook >> out.txt; env | grep ^LAYER_ >> out.txt"}]}]}}`; run `claude -p "Reply OK" --settings overlay.json`;
     inspect `out.txt` (do both hooks run? which `LAYER_PROJ` wins?) and record the results.
- [ ] **B6. Record findings** in `docs/plans/2026-11/<date>-phase-b-findings.md`, update the spec's Clarifications
  section, and open a small PR with the `render/claude.json` plugin set and any fixes.

After Phase B, Phases C and D are planned in the work repository using the staging directory as input.
