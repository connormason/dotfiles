# Engine Linux Support Implementation Plan (NAS sub-project 1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the stow engine (driver, stages, `stow.sh`, `render.py`, Brewfile, shell config) run on Debian-family
Linux with Linuxbrew, while proving that nothing changes on macOS.

**Architecture:** `bootstrap/lib.sh` gains `dotfiles_os` (`darwin`/`linux`, `DOTFILES_OS` override) and `require_os`.
Stages self-gate with `require_os`; stow packages opt into OSes with a `.dotfiles-os` marker; `render.py` scopes the
`vscode` target to darwin; the Brewfile wraps macOS-only entries in `if OS.mac?`. Golden files captured from the
unmodified tree prove the darwin result is unchanged after every task.

**Tech Stack:** bash (3.2-compatible), GNU Stow 2.4.1, Homebrew / Linuxbrew `brew bundle`, Python 3.9+ (`render.py`,
pytest), GitHub Actions.

**Spec:** [`2026-10-31-nas-provisioning-design.md`](2026-10-31-nas-provisioning-design.md), "Sub-project 1".

Paths below are relative to the repository root: `~/dotfiles-personal`, or the active worktree under
`~/dotfiles-personal/.claude/worktrees/`.

## Global Constraints

- Public repo: nothing employer-specific (names, hosts, tools, people's handles) in any file or commit message. The
  private leak patterns live at `~/.config/dotfiles/leak-patterns.txt` and are enforced by the leak guard in prek.
- Every `uv` call goes through `scripts/hooks/uv-public.sh`. Never run `ruff format`. No bare `python`/`python3`/`pip`.
  Use `$TMPDIR`, never `/tmp`, for scratch files.
- Never run stow, render, bootstrap (outside `--dry-run` in a throwaway HOME) or `doctor --fix` against the real HOME.
- **Zero behaviour change on macOS.** The darwin golden files from Task 1 must keep passing, unmodified, through
  Task 10. A task that needs to edit a darwin golden file is wrong; stop and re-plan.
- All engine shell code stays bash 3.2-compatible (no associative arrays, no `declare -g`, no `${var,,}`, no
  `mapfile`); the existing `shell` fixture runs every bash test under `/bin/bash` 3.2 on macOS.
- The engine never runs `apt` and never uses `sudo` on Linux. Root-level prerequisites are the NAS `debian` Ansible
  role's job (sub-project 2).
- OS ids are exactly `darwin` and `linux` everywhere (`DOTFILES_OS`, `.dotfiles-os`, `require_os`, `render.py`).
- Do not bypass hooks (`--no-verify`). Before each commit: `prek run --files <changed files>` and the full suite
  `scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider` pass. Baseline at plan time: 584 passed (~32 s).
- `tests/unit/test_stow_tree.py` fails on untracked files under `stow/`, `render/`, `profiles/`, `tests/fixtures/`:
  `git add` new files there **before** running the full suite.
- Python style: single quotes, sphinx docstrings, `from __future__ import annotations`, one import per line (isort
  `force-single-line`), aligned dict/assignment columns as in neighbouring code, no blank line between a class
  docstring and its first member. Tests: multi-line docstrings (capitalized, no trailing period), `-> None` on every
  test method, classes named `TestXxx`.
- `docs/plans/` and `.ctx/` are hand-maintained (120-column wrap). Other Markdown is formatted by the `mdformat` prek
  hook; let the hook do it.
- Every test module that runs engine code adds `'DOTFILES_OS'` to its scrubbed-variable list, so a developer's own
  environment cannot leak in. Tests that depend on an OS set `DOTFILES_OS` explicitly.
- Commits are conventional (`feat(engine): …`, `test(engine): …`, `ci: …`, `docs: …`), one logical change per
  commit. Do not push until Task 10, and push only with the owner's approval.

## File Map

| File | Change |
| --- | --- |
| `tests/golden.py` | **Create.** `check_golden()` helper shared by the golden tests |
| `tests/fixtures/os_layout/darwin-links.txt` | **Create (generated).** `$HOME` symlinks the base layer creates on darwin |
| `tests/fixtures/os_layout/brewfile-darwin.txt` | **Create (generated).** Sorted `brew bundle list --all` on darwin |
| `tests/fixtures/os_layout/brewfile-darwin-formulae.txt` | **Create (generated).** Sorted `brew bundle list --formula` on darwin |
| `tests/integration/test_os_layout.py` | **Create.** Per-OS link-set tests (golden for darwin, derived for linux) |
| `tests/unit/test_brewfile.py` | **Create.** Brewfile resolution tests per OS |
| `bootstrap/lib.sh` | `dotfiles_os`, `require_os`, `sha256_of`; Linuxbrew default prefix |
| `stow/homebrew/.config/zsh/conf.d/05-homebrew.zsh` | Linuxbrew default prefix (mirrors `lib.sh`) |
| `stow.sh` | `.dotfiles-os` package markers |
| `stow/{hammerspoon,iterm2,vscode}/.dotfiles-os` | **Create.** `darwin` |
| `stow/hatch-darwin/`, `stow/hatch-linux/` | **Create.** hatch config moved out of `stow/python/` |
| `scripts/dotfiles/render.py` | `TARGET_OS`, `current_os()`, OS-filtered default targets |
| `bootstrap/bootstrap.sh` | Prime sudo on darwin only |
| `bootstrap/00-preflight.sh` | Linux branch (Debian family + system prerequisites) |
| `bootstrap/60-macos.sh`, `72-vscode.sh`, `96-iterm2.sh` | `require_os darwin` |
| `bootstrap/50-brew.sh` | `sha256_of`, Linuxbrew prefix precondition, `NONINTERACTIVE`, darwin-only starship cleanup |
| `bootstrap/Brewfile` | `if OS.mac?` block for `mas`, casks, fonts, Mac App Store |
| `stow/shell/.config/zsh/conf.d/40-aliases.zsh` | OS-conditional `VISUAL`/`st` and `o` alias |
| `stow/os_tools/.config/zsh/conf.d/90-banner.zsh` | OS-conditional fastfetch logo |
| `.github/workflows/lint.yml` | **New job** `pytest (Linux)` |
| `bootstrap/README.md`, `stow/README.md`, `.ctx/ARCHITECTURE.md` | Document OS support |
| Tests: `test_lib_sh.py`, `test_stow_sh.py`, `test_render.py`, `test_bootstrap_driver.py`, `test_brew_stage.py`, `test_profiles.py`, `tests/integration/test_home.py`; new `tests/unit/test_os_stages.py` | See tasks |

## Deliberate deviations from the spec

- **`run.py doctor` is unchanged.** Its link check runs `stow.sh -n`, so the marker filter flows through, and its
  required tools (`brew`, `git`, `stow`, `uv`, `zsh`) are identical on Linux once Linuxbrew is installed.
- **`50-directories.zsh` is unchanged.** Its aliases (`desk="~/Desktop"`, …) only fail if invoked on a machine without
  the directory; wrapping a keep-sorted block in conditionals buys nothing.
- **`python` is not marked darwin-only.** It also ships `42-python.zsh` and the IPython startup file. Only the hatch
  config moves (Task 4). It stays at its exact macOS path in `hatch-darwin` (so the darwin link set is unchanged); the
  Linux path is an in-repo relative symlink to that file, so the content exists once.
- **The driver primes sudo only on darwin** (not in the spec): no Linux stage needs root, and a sudo prompt would block
  an unattended Ansible run.
- **CI installs GNU Stow from Linuxbrew, not apt.** `stow.sh` classifies conflicts by Stow 2.4.1's message wording;
  Ubuntu/Debian 12 apt ship 2.3.1. The NAS also gets Stow from the shared Brewfile.

## Handoff notes for sub-project 2 (not implemented here)

- `20-ssh-key` ends with an interactive `confirm` when GitHub auth fails; an unattended Ansible run needs either a
  working key first or a non-interactive mode.
- The `debian` role must install `build-essential procps curl file git zsh` and create `/home/linuxbrew/.linuxbrew`
  owned by the user, matching `00-preflight` (Task 6) and `50-brew` (Task 7).

---

### Task 1: Darwin baseline goldens

Capture what the **unmodified** tree produces on macOS, so every later task can prove it changed nothing there. Run this
task on a Mac, before any other change.

**Files:**
- Create: `tests/golden.py`
- Create: `tests/integration/test_os_layout.py`
- Create: `tests/unit/test_brewfile.py`
- Create (generated): `tests/fixtures/os_layout/darwin-links.txt`, `brewfile-darwin.txt`, `brewfile-darwin-formulae.txt`

**Interfaces:**
- Produces: `tests.golden.check_golden(name: str, actual: list[str]) -> None`;
  `tests.integration.test_os_layout.linked_paths(tmp_path: Path, os_name: str) -> list[str]`;
  `tests.unit.test_brewfile.bundle_list(*flags: str) -> list[str]` and the module constant `GOLDEN_DIR`.

- [ ] **Step 1: Write `tests/golden.py`**

```python
"""
Golden-file helper for regression tests
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

__all__ = [
    'GOLDEN_DIR',
    'check_golden',
]

REPO_ROOT  = Path(__file__).resolve().parents[1]
GOLDEN_DIR = REPO_ROOT / 'tests' / 'fixtures' / 'os_layout'


def check_golden(name: str, actual: list[str]) -> None:
    """
    Compare lines with a golden file, or rewrite the golden file when DOTFILES_UPDATE_GOLDEN=1

    :param name: file name under tests/fixtures/os_layout
    :param actual: lines produced by the code under test
    """
    path = GOLDEN_DIR / name
    if os.environ.get('DOTFILES_UPDATE_GOLDEN') == '1':
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(''.join(f'{line}\n' for line in actual), encoding='utf-8')
        pytest.skip(f'rewrote {path.relative_to(REPO_ROOT)}')

    assert actual == path.read_text(encoding='utf-8').splitlines()
```

- [ ] **Step 2: Write `tests/integration/test_os_layout.py`**

```python
"""
OS layout regression tests: which $HOME paths the base layer links on each OS
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.golden import check_golden

REPO_ROOT = Path(__file__).resolve().parents[2]

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which('stow') is None, reason='GNU Stow not installed'),
]


def linked_paths(tmp_path: Path, os_name: str) -> list[str]:
    """
    Stow the base layer (no overlays) into an empty HOME as os_name and list the symlinks it created

    :param tmp_path: scratch directory for the HOME
    :param os_name: value for DOTFILES_OS
    :return: sorted HOME-relative symlink paths
    """
    home = tmp_path / f'home-{os_name}'
    home.mkdir()

    env: dict[str, str] = {
        'HOME':                   str(home),
        'PATH':                   os.environ['PATH'],
        'XDG_CONFIG_HOME':        str(home / '.config'),
        'DOTFILES_OVERLAYS_FILE': str(tmp_path / 'no-overlays'),
        'DOTFILES_OS':            os_name,
    }
    result = subprocess.run(
        ['bash', str(REPO_ROOT / 'stow.sh'), '--no-summary'],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return sorted(str(path.relative_to(home)) for path in home.rglob('*') if path.is_symlink())


class TestDarwinLayout:
    """
    Tests pinning the darwin link set to the pre-Linux-support golden file
    """
    @pytest.mark.skipif(sys.platform != 'darwin', reason='the golden file is regenerated on macOS only')
    def test_darwin_links_match_golden(self, tmp_path: Path) -> None:
        """
        Test that the base layer links exactly the golden set of paths on darwin
        """
        check_golden('darwin-links.txt', linked_paths(tmp_path, 'darwin'))

    def test_darwin_links_match_golden_on_any_host(self, tmp_path: Path) -> None:
        """
        Test that DOTFILES_OS=darwin reproduces the golden set even on a Linux host
        """
        if os.environ.get('DOTFILES_UPDATE_GOLDEN') == '1':
            pytest.skip('golden files are being rewritten')
        check_golden('darwin-links.txt', linked_paths(tmp_path, 'darwin'))
```

(The two darwin tests differ only in host gating: the first is the one allowed to rewrite the golden file; the second
asserts on every host, including the Linux CI runner.)

- [ ] **Step 3: Write `tests/unit/test_brewfile.py`**

```python
"""
Brewfile regression tests: what `brew bundle` resolves bootstrap/Brewfile to on each OS
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.golden import check_golden

REPO_ROOT = Path(__file__).resolve().parents[2]
BREWFILE  = REPO_ROOT / 'bootstrap' / 'Brewfile'
BREW      = shutil.which('brew')

pytestmark = pytest.mark.skipif(BREW is None, reason='Homebrew not installed')


def bundle_list(*flags: str) -> list[str]:
    """
    Run `brew bundle list` against the base Brewfile without auto-updating Homebrew

    :param flags: entry-type flags such as --all or --formula
    :return: sorted, non-empty output lines
    """
    assert BREW is not None
    result = subprocess.run(
        [BREW, 'bundle', 'list', *flags, '--file', str(BREWFILE)],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, 'HOMEBREW_NO_AUTO_UPDATE': '1', 'HOMEBREW_NO_ENV_HINTS': '1'},
    )
    assert result.returncode == 0, result.stderr
    return sorted(line for line in result.stdout.splitlines() if line)


@pytest.mark.skipif(sys.platform != 'darwin', reason='darwin resolution')
class TestDarwinBrewfile:
    """
    Tests pinning the darwin Brewfile resolution to the pre-Linux-support golden files
    """
    def test_all_entries_match_golden(self) -> None:
        """
        Test that every tap, formula, cask, and Mac App Store entry resolves exactly as before
        """
        check_golden('brewfile-darwin.txt', bundle_list('--all'))

    def test_formulae_match_golden(self) -> None:
        """
        Test that the formula list resolves exactly as before
        """
        check_golden('brewfile-darwin-formulae.txt', bundle_list('--formula'))
```

- [ ] **Step 4: Generate the golden files from the unmodified tree**

Run: `DOTFILES_UPDATE_GOLDEN=1 scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider tests/integration/test_os_layout.py tests/unit/test_brewfile.py`

Expected: 3 skipped ("rewrote tests/fixtures/os_layout/…"), 1 skipped ("golden files are being rewritten").

- [ ] **Step 5: Sanity-check the generated files**

Run: `wc -l tests/fixtures/os_layout/*.txt && grep -c '^Library/Application Support/hatch/config.toml$' tests/fixtures/os_layout/darwin-links.txt`

Expected: `brewfile-darwin.txt` 76 lines (3 taps + 59 formulae + 12 casks + 2 mas), `brewfile-darwin-formulae.txt` 59
lines, `darwin-links.txt` non-empty and containing the hatch path once (`1`). Read `darwin-links.txt` and confirm it
contains `.hammerspoon/init.lua`, `.config/iterm2/com.googlecode.iterm2.plist`,
`Library/Application Support/Code/User/keybindings.json`, and no `.dotfiles-os` entry.

- [ ] **Step 6: Run the tests normally**

Run: `git add tests/golden.py tests/integration/test_os_layout.py tests/unit/test_brewfile.py tests/fixtures/os_layout && scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider`

Expected: all pass (584 + 4 new).

- [ ] **Step 7: Commit**

```bash
git add tests/golden.py tests/integration/test_os_layout.py tests/unit/test_brewfile.py tests/fixtures/os_layout
git commit -m "test(engine): pin the darwin link set and Brewfile resolution as golden files"
```

---

### Task 2: `lib.sh` OS primitives and the Linuxbrew prefix

**Files:**
- Modify: `bootstrap/lib.sh` (add three functions after `have()`; edit `ensure_brew_on_path`)
- Modify: `stow/homebrew/.config/zsh/conf.d/05-homebrew.zsh:5-13`
- Test: `tests/unit/test_lib_sh.py`

**Interfaces:**
- Produces (bash, sourced from `lib.sh`):
  - `dotfiles_os` → prints `darwin` or `linux`; honours `DOTFILES_OS`; dies (exit 1) on an invalid override or an
    unsupported `uname -s`.
  - `require_os OS...` → returns 0 if the current OS is listed; otherwise logs `skipped (<OS...> only; this is <os>)`
    and **exits the calling script with status 0**.
  - `sha256_of FILE` → prints the hex SHA-256 of FILE (`shasum -a 256` if present, else `sha256sum`).
  - `ensure_brew_on_path` default probe list becomes `/opt/homebrew /usr/local /home/linuxbrew/.linuxbrew`.

- [ ] **Step 1: Write the failing tests** — in `tests/unit/test_lib_sh.py`, add `import hashlib`, `import platform`,
  `import shutil` (one per line, sorted), add `'DOTFILES_OS'` to `_SCRUBBED_VARS`, and append:

```python
class TestDotfilesOs:
    """
    Tests for dotfiles_os
    """
    @pytest.mark.parametrize('value', ['darwin', 'linux'])
    def test_override_is_honored(self, bash: BashRunner, env: dict[str, str], value: str) -> None:
        """
        Test that DOTFILES_OS overrides detection
        """
        result = bash('dotfiles_os', {**env, 'DOTFILES_OS': value})
        assert result.returncode == 0, result.stderr
        assert result.stdout == f'{value}\n'

    def test_invalid_override_fails(self, bash: BashRunner, env: dict[str, str]) -> None:
        """
        Test that an unknown DOTFILES_OS value is fatal and named in the error
        """
        result = bash('dotfiles_os', {**env, 'DOTFILES_OS': 'macos'})
        assert result.returncode != 0
        assert "DOTFILES_OS must be darwin or linux (got 'macos')" in result.stderr

    def test_detects_the_host(self, bash: BashRunner) -> None:
        """
        Test that detection without an override maps uname -s to the engine's OS id
        """
        expected = {'Darwin': 'darwin', 'Linux': 'linux'}[platform.system()]
        assert bash('dotfiles_os').stdout == f'{expected}\n'


class TestRequireOs:
    """
    Tests for require_os
    """
    def test_listed_os_continues(self, bash: BashRunner, env: dict[str, str]) -> None:
        """
        Test that a listed OS returns and the script carries on
        """
        result = bash('require_os darwin linux; echo after', {**env, 'DOTFILES_OS': 'linux'})
        assert result.returncode == 0, result.stderr
        assert result.stdout.splitlines()[-1] == 'after'

    def test_unlisted_os_exits_cleanly(self, bash: BashRunner, env: dict[str, str]) -> None:
        """
        Test that an unlisted OS logs the skip and exits 0 before the rest of the script
        """
        result = bash('require_os darwin; echo after', {**env, 'DOTFILES_OS': 'linux'})
        assert result.returncode == 0, result.stderr
        assert 'skipped (darwin only; this is linux)' in result.stdout
        assert 'after' not in result.stdout


class TestSha256Of:
    """
    Tests for sha256_of
    """
    def test_digest_matches(self, bash: BashRunner, tmp_path: Path) -> None:
        """
        Test that the digest is correct with the host's tools (shasum on macOS)
        """
        payload = tmp_path / 'payload'
        payload.write_bytes(b'hello\n')

        result = bash(f'sha256_of "{payload}"')
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == hashlib.sha256(b'hello\n').hexdigest()

    def test_falls_back_to_sha256sum(self, bash: BashRunner, tmp_path: Path) -> None:
        """
        Test that the digest is correct when shasum is absent (Debian without perl) and only sha256sum remains
        """
        if shutil.which('sha256sum') is None:
            pytest.skip('sha256sum not installed')

        payload = tmp_path / 'payload'
        payload.write_bytes(b'hello\n')

        # Hide shasum from `have` rather than from PATH: lib.sh appends a Homebrew prefix, and Homebrew's perl ships one
        script = f'have() {{ [ "$1" != shasum ] && command -v "$1" >/dev/null 2>&1; }}\nsha256_of "{payload}"'
        result = bash(script)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == hashlib.sha256(b'hello\n').hexdigest()
```

(`shasum` on macOS is a version-selecting wrapper, so it is exercised with the normal PATH only.)

Also, in `TestEnsureBrewOnPath.test_extra_prefixes_extend_defaults`, change the default tuple to
`('/opt/homebrew', '/usr/local', '/home/linuxbrew/.linuxbrew')`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider tests/unit/test_lib_sh.py -k "DotfilesOs or RequireOs or Sha256Of"`
Expected: FAIL — `dotfiles_os: command not found` (and the same for `require_os`, `sha256_of`).

- [ ] **Step 3: Implement in `bootstrap/lib.sh`** — insert after the `have()` definition:

```bash
# dotfiles_os -> print the engine's OS id: "darwin" or "linux". DOTFILES_OS overrides detection (tests, previews of
# another OS's layout). Dies on an invalid override or an unsupported kernel. Callers capture it with
# os="$(dotfiles_os)" so a failure aborts under `set -e`.
dotfiles_os() {
    local os="${DOTFILES_OS:-}"
    if [ -z "$os" ]; then
        case "$(uname -s)" in
        Darwin) os=darwin ;;
        Linux) os=linux ;;
        *) die "unsupported OS: $(uname -s) (the engine supports macOS and Linux)" ;;
        esac
    fi
    case "$os" in
    darwin | linux) printf '%s\n' "$os" ;;
    *) die "DOTFILES_OS must be darwin or linux (got '$os')" ;;
    esac
}

# require_os OS... -> return if the current OS is one of OS...; otherwise log the skip and exit the calling stage with
# status 0, so an OS-specific stage is a clean no-op elsewhere. Call it right after sourcing this file.
require_os() {
    local current want
    current="$(dotfiles_os)" || exit 1
    for want in "$@"; do
        if [ "$want" = "$current" ]; then
            return 0
        fi
    done
    log "skipped ($* only; this is $current)"
    exit 0
}

# sha256_of FILE -> print FILE's SHA-256 hex digest. macOS ships shasum; on Linux it comes with perl, so fall back to
# coreutils' sha256sum when shasum is absent.
sha256_of() {
    if have shasum; then
        shasum -a 256 "$1" | awk '{print $1}'
    else
        sha256sum "$1" | awk '{print $1}'
    fi
}
```

Then in `ensure_brew_on_path`, change the loop and its comment:

```bash
# Append the first Homebrew prefix that has bin/brew to PATH. Appended (not prepended) so an active virtualenv's python
# is not shadowed. A layer's bootstrap/env.sh may set DOTFILES_BREW_PREFIXES (space-separated) to add prefixes; these
# are checked before the defaults (/opt/homebrew, /usr/local, /home/linuxbrew/.linuxbrew) and the first prefix with
# bin/brew wins. Keep the defaults in sync with stow/homebrew/.config/zsh/conf.d/05-homebrew.zsh.
ensure_brew_on_path() {
    local prefix
    for prefix in ${DOTFILES_BREW_PREFIXES:-} /opt/homebrew /usr/local /home/linuxbrew/.linuxbrew; do
```

- [ ] **Step 4: Mirror the prefix in `05-homebrew.zsh`** — change the comment's "then /opt/homebrew and /usr/local" to
  "then /opt/homebrew, /usr/local, and /home/linuxbrew/.linuxbrew (keep in sync with bootstrap/lib.sh)" and the loop to:

```zsh
    for _prefix in ${=DOTFILES_BREW_PREFIXES:-} /opt/homebrew /usr/local /home/linuxbrew/.linuxbrew; do
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider tests/unit/test_lib_sh.py`
Expected: PASS (on a Mac without coreutils, the `sha256sum` case skips).

- [ ] **Step 6: Full suite, hooks, commit**

```bash
scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider
prek run --files bootstrap/lib.sh stow/homebrew/.config/zsh/conf.d/05-homebrew.zsh tests/unit/test_lib_sh.py
git add bootstrap/lib.sh stow/homebrew/.config/zsh/conf.d/05-homebrew.zsh tests/unit/test_lib_sh.py
git commit -m "feat(engine): add dotfiles_os, require_os, and sha256_of; probe the Linuxbrew prefix"
```

---

### Task 3: `.dotfiles-os` package markers in `stow.sh`

**Files:**
- Modify: `stow.sh` (header comment, discovery loop, `package_files`, `run_layer`, package selection)
- Create: `stow/hammerspoon/.dotfiles-os`, `stow/iterm2/.dotfiles-os`, `stow/vscode/.dotfiles-os`
- Modify: `stow/README.md`, `tests/integration/test_home.py` (pin the `home` fixture to darwin)
- Test: `tests/unit/test_stow_sh.py`, `tests/integration/test_os_layout.py`

**Interfaces:**
- Consumes: `dotfiles_os` (Task 2).
- Produces: marker contract — a package directory may contain `.dotfiles-os` listing OS ids (`darwin`, `linux`), one
  per line, `#` comments and blank lines ignored, whitespace/CR stripped. No marker = every OS. An unknown id or a marker
  with no ids is fatal. Excluded packages are invisible to `--list`, linking, and the ownership check; requesting one by
  name fails with `package '<name>' does not apply to <os> (see its .dotfiles-os)`. The package-name uniqueness rule
  still spans every package, excluded or not. The marker file itself is never linked and never counts as an owned path.

- [ ] **Step 1: Write the failing unit tests** — in `tests/unit/test_stow_sh.py` add `'DOTFILES_OS'` to
  `_SCRUBBED_VARS` and append:

```python
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
        _pkg(world['repo'], 'shell', {'.zshrc': 'x'})
        _pkg(world['repo'], 'mac',   {'.macrc': 'x'})
        _marker(world['repo'], 'mac', 'darwin\n')

        result = _stow(world, extra_env={'DOTFILES_OS': 'linux'})
        assert result.returncode == 0, result.stderr
        assert (world['home'] / '.zshrc').is_symlink()
        assert not (world['home'] / '.macrc').exists()

    def test_included_package_is_linked_without_its_marker(self, world: dict[str, Path]) -> None:
        """
        Test that a darwin-only package is linked on darwin and the marker file itself is not
        """
        _pkg(world['repo'], 'mac', {'.macrc': 'x'})
        _marker(world['repo'], 'mac', 'darwin\n')

        result = _stow(world, extra_env={'DOTFILES_OS': 'darwin'})
        assert result.returncode == 0, result.stderr
        assert (world['home'] / '.macrc').is_symlink()
        assert not (world['home'] / '.dotfiles-os').exists()

    def test_list_omits_excluded_packages(self, world: dict[str, Path]) -> None:
        """
        Test that --list shows only the packages that apply to this OS
        """
        _pkg(world['repo'], 'shell', {'.zshrc': 'x'})
        _pkg(world['repo'], 'mac',   {'.macrc': 'x'})
        _marker(world['repo'], 'mac', 'darwin\n')

        result = _stow(world, '--list', extra_env={'DOTFILES_OS': 'linux'})
        assert result.returncode == 0, result.stderr
        assert result.stdout.splitlines() == [f'shell\t{world["repo"].resolve()}']

    def test_requesting_an_excluded_package_fails(self, world: dict[str, Path]) -> None:
        """
        Test that naming an excluded package explains why instead of calling it unknown
        """
        _pkg(world['repo'], 'mac', {'.macrc': 'x'})
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
        _pkg(world['repo'], 'both', {'.bothrc': 'x'})
        _marker(world['repo'], 'both', '# both platforms\r\n  darwin  # mac\r\nlinux\r\n')

        result = _stow(world, extra_env={'DOTFILES_OS': 'linux'})
        assert result.returncode == 0, result.stderr
        assert (world['home'] / '.bothrc').is_symlink()

    def test_os_variants_may_provide_the_same_path(self, world: dict[str, Path]) -> None:
        """
        Test that a darwin package and a linux package may own the same path, and the matching one is linked
        """
        _pkg(world['repo'], 'tool-darwin', {'.config/tool/config': 'mac'})
        _pkg(world['repo'], 'tool-linux',  {'.config/tool/config': 'linux'})
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider tests/unit/test_stow_sh.py -k OsMarkers`
Expected: FAIL — excluded packages are still linked; `--list` shows `mac`; error messages absent. (The final test,
`test_moving_a_file_between_packages_relinks_it`, may already pass: it pins Stow 2.4.1 behaviour verified at plan
time.)

- [ ] **Step 3: Implement in `stow.sh`**

(a) Header comment: after the `#   Packages …` line insert

```bash
#   OS         a package's optional .dotfiles-os file lists the OS ids it applies to (darwin, linux; one per line, '#'
#              comments); packages without one apply everywhere. Other packages are invisible on this OS
```

(b) Immediately before the `# Discovery` section banner, insert:

```bash
CURRENT_OS="$(dotfiles_os)" || exit 1

# package_os_ok DIR -> succeed if the package at DIR applies to CURRENT_OS (see "OS" in the header). Dies on an unknown
# OS id or a marker that lists none.
package_os_ok() {
    local marker="$1/.dotfiles-os" line any=0 found=0
    if [ ! -f "$marker" ]; then
        return 0
    fi
    while IFS= read -r line || [ -n "$line" ]; do
        line="${line%%#*}"
        line="${line//[[:space:]]/}"
        if [ -z "$line" ]; then
            continue
        fi
        case "$line" in
        darwin | linux) ;;
        *) die "unknown OS '$line' in $marker (expected darwin or linux)" ;;
        esac
        any=1
        if [ "$line" = "$CURRENT_OS" ]; then
            found=1
        fi
    done <"$marker"
    if [ "$any" = 0 ]; then
        die "$marker lists no OS (expected darwin and/or linux)"
    fi
    [ "$found" = 1 ]
}
```

(c) Replace the discovery loop body. Before the loop add `SEEN_NAMES=()`, `SEEN_LAYERS=()`, `SKIPPED_NAMES=()` (with a
comment: every package in every layer, for the one-layer-per-name rule; packages whose marker excludes this OS). Replace

```bash
        pkg="$(basename "$dir")"
        if idx="$(pkg_index "$pkg")"; then
            die "package '$pkg' is defined in two layers: ${PKG_LAYERS[$idx]} and $layer"
        fi
        PKG_NAMES+=("$pkg")
        PKG_LAYERS+=("$layer")
```

with

```bash
        pkg="$(basename "$dir")"
        for i in ${SEEN_NAMES[@]+"${!SEEN_NAMES[@]}"}; do
            if [ "${SEEN_NAMES[$i]}" = "$pkg" ]; then
                die "package '$pkg' is defined in two layers: ${SEEN_LAYERS[$i]} and $layer"
            fi
        done
        SEEN_NAMES+=("$pkg")
        SEEN_LAYERS+=("$layer")
        if package_os_ok "${dir%/}"; then
            PKG_NAMES+=("$pkg")
            PKG_LAYERS+=("$layer")
        else
            SKIPPED_NAMES+=("$pkg")
        fi
```

(d) Package selection: replace `idx="$(pkg_index "$pkg")" || die "unknown package: $pkg"` with

```bash
        if ! idx="$(pkg_index "$pkg")"; then
            for skipped in ${SKIPPED_NAMES[@]+"${SKIPPED_NAMES[@]}"}; do
                if [ "$skipped" = "$pkg" ]; then
                    die "package '$pkg' does not apply to $CURRENT_OS (see its .dotfiles-os)"
                fi
            done
            die "unknown package: $pkg"
        fi
```

(e) `package_files`: add `-o -name .dotfiles-os` to the `find` prune expression (after `-o -name .backups`). Update
the comment above the Ownership section: ".DS_Store, .backups/ … and .dotfiles-os markers are pruned everywhere,
matching the --ignore flags passed to stow below."

(f) `run_layer`: add `--ignore='\.dotfiles-os'` after `--ignore='\.backups'`.

- [ ] **Step 4: Add the markers** — create each of `stow/hammerspoon/.dotfiles-os`, `stow/iterm2/.dotfiles-os`,
  `stow/vscode/.dotfiles-os` with exactly:

```text
# macOS-only package (see stow/README.md "OS-specific packages")
darwin
```

- [ ] **Step 5: Pin the integration `home` fixture to darwin** — in `tests/integration/test_home.py`, add
  `'DOTFILES_OS': 'darwin',` to the `env` dict of the `home` fixture, with the comment
  `# the module asserts the macOS layout (hammerspoon, iterm2, vscode); test_os_layout.py covers Linux`. Align the
  value column with its neighbours.

- [ ] **Step 6: Add the Linux layout test** — in `tests/integration/test_os_layout.py` add, below `TestDarwinLayout`:

```python
# Paths the base layer links on darwin only (prefix match against the darwin golden file)
DARWIN_ONLY: tuple[str, ...] = (
    '.hammerspoon/',
    '.config/iterm2/',
    '.config/zsh/conf.d/30-iterm2.zsh',
    'Library/Application Support/Code/',
)

# Paths the base layer links on linux only
LINUX_ONLY: tuple[str, ...] = ()


class TestLinuxLayout:
    """
    Tests deriving the linux link set from the darwin golden file
    """
    def test_linux_links_are_darwin_minus_macos_packages(self, tmp_path: Path) -> None:
        """
        Test that linux links the darwin set minus macOS-only paths, plus linux-only paths
        """
        if os.environ.get('DOTFILES_UPDATE_GOLDEN') == '1':
            pytest.skip('golden files are being rewritten')

        darwin   = (REPO_ROOT / 'tests' / 'fixtures' / 'os_layout' / 'darwin-links.txt').read_text('utf-8').splitlines()
        expected = sorted([path for path in darwin if not path.startswith(DARWIN_ONLY)] + list(LINUX_ONLY))
        assert linked_paths(tmp_path, 'linux') == expected
```

- [ ] **Step 7: Document in `stow/README.md`** — append " (macOS only)" to the "What it configures" cell of the
  `hammerspoon`, `iterm2`, and `vscode` rows, and add a short section after the package table:

```markdown
## OS-specific packages

A package that applies only to some operating systems carries a `.dotfiles-os` file at its root listing the OS ids it
applies to (`darwin`, `linux`), one per line; `#` starts a comment. `stow.sh` skips packages whose marker excludes the
current OS (`bootstrap/lib.sh` `dotfiles_os`, overridable with `DOTFILES_OS`): they are not linked, not listed by
`--list`, and not part of the ownership check, so a `<tool>-darwin` and a `<tool>-linux` package may provide the same
path. Package names stay unique across every layer regardless of markers. Packages without a marker apply everywhere.
```

- [ ] **Step 8: Run the tests**

Run: `git add stow && scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider`
Expected: all pass, including both darwin golden tests (the markers changed nothing on darwin) and
`test_linux_links_are_darwin_minus_macos_packages`.

- [ ] **Step 9: Hooks and commit**

```bash
prek run --files stow.sh stow/README.md stow/hammerspoon/.dotfiles-os stow/iterm2/.dotfiles-os stow/vscode/.dotfiles-os tests/unit/test_stow_sh.py tests/integration/test_home.py tests/integration/test_os_layout.py
git add stow.sh stow/README.md stow/hammerspoon/.dotfiles-os stow/iterm2/.dotfiles-os stow/vscode/.dotfiles-os tests/unit/test_stow_sh.py tests/integration/test_home.py tests/integration/test_os_layout.py
git commit -m "feat(engine): scope stow packages to an OS with .dotfiles-os markers"
```

---

### Task 4: Split the hatch config into `hatch-darwin` / `hatch-linux`

**Files:**
- Move: `stow/python/Library/Application Support/hatch/config.toml` → `stow/hatch-darwin/Library/Application Support/hatch/config.toml`
- Create: `stow/hatch-darwin/.dotfiles-os`, `stow/hatch-linux/.dotfiles-os`, `stow/hatch-linux/.config/hatch/config.toml` (relative symlink)
- Modify: `stow/README.md`, `tests/integration/test_os_layout.py`

**Interfaces:**
- Consumes: the marker contract (Task 3).
- Produces: on darwin the link set is unchanged (`Library/Application Support/hatch/config.toml`); on linux
  `.config/hatch/config.toml` (hatch's Linux default location) resolves to the same file content.

- [ ] **Step 1: Write the failing test** — in `tests/integration/test_os_layout.py`, change the constants and add a test:

```python
DARWIN_ONLY: tuple[str, ...] = (
    '.hammerspoon/',
    '.config/iterm2/',
    '.config/zsh/conf.d/30-iterm2.zsh',
    'Library/',
)

LINUX_ONLY: tuple[str, ...] = (
    '.config/hatch/config.toml',
)
```

and, in `TestLinuxLayout`:

```python
    def test_linux_hatch_config_matches_the_darwin_file(self, tmp_path: Path) -> None:
        """
        Test that the linux hatch config resolves to the same content as the macOS one, and nothing lands in ~/Library
        """
        linked_paths(tmp_path, 'linux')
        home = tmp_path / 'home-linux'

        config = home / '.config' / 'hatch' / 'config.toml'
        darwin = REPO_ROOT / 'stow' / 'hatch-darwin' / 'Library' / 'Application Support' / 'hatch' / 'config.toml'
        assert config.is_symlink()
        assert config.read_text(encoding='utf-8') == darwin.read_text(encoding='utf-8')
        assert not (home / 'Library').exists()
```

- [ ] **Step 2: Run to verify failure**

Run: `scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider tests/integration/test_os_layout.py`
Expected: FAIL — linux still links `Library/Application Support/hatch/config.toml`; `.config/hatch/config.toml` missing.

- [ ] **Step 3: Move the file and create the packages**

```bash
mkdir -p "stow/hatch-darwin/Library/Application Support/hatch" stow/hatch-linux/.config/hatch
git mv "stow/python/Library/Application Support/hatch/config.toml" "stow/hatch-darwin/Library/Application Support/hatch/config.toml"
ln -s "../../../hatch-darwin/Library/Application Support/hatch/config.toml" stow/hatch-linux/.config/hatch/config.toml
printf '%s\n' '# macOS-only package (see stow/README.md "OS-specific packages")' darwin > stow/hatch-darwin/.dotfiles-os
printf '%s\n' '# Linux-only package (see stow/README.md "OS-specific packages")' linux > stow/hatch-linux/.dotfiles-os
```

Verify: `ls -la stow/python` shows no `Library` directory (git removes empty parents); `cat stow/hatch-linux/.config/hatch/config.toml`
prints the hatch config (the symlink resolves inside the repo).

- [ ] **Step 4: Update `stow/README.md`** — `python` row: "IPython startup script and Python shell aliases" (drop
  "hatch config"). Add two rows in sorted position (after `git`, before `hammerspoon`):

```markdown
| `hatch-darwin` | hatch global config at its macOS path (macOS only)                                    | — |
| `hatch-linux`  | hatch global config at its Linux path, a symlink to the `hatch-darwin` file (Linux only) | — |
```

(The `mdformat` hook realigns the table.)

- [ ] **Step 5: Run the tests**

Run: `git add stow && scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider`
Expected: all pass. In particular `test_darwin_links_match_golden*` (darwin path unchanged), the existing
`test_hatch_config_is_generic` in `test_home.py` (darwin fixture), `test_docs_consistency.py` (README table matches the
new directories), and both linux layout tests.

- [ ] **Step 6: Hooks and commit**

```bash
prek run --files stow/README.md stow/hatch-darwin/.dotfiles-os stow/hatch-linux/.dotfiles-os tests/integration/test_os_layout.py
git add -A stow/python stow/hatch-darwin stow/hatch-linux stow/README.md tests/integration/test_os_layout.py
git commit -m "feat(engine): move the hatch config into hatch-darwin and hatch-linux packages"
```

---

### Task 5: OS-scoped render targets

**Files:**
- Modify: `scripts/dotfiles/render.py` (constants block after `TARGETS`; new `current_os`/`applies`; `_main`)
- Test: `tests/unit/test_render.py`

**Interfaces:**
- Produces: `render.TARGET_OS: dict[str, frozenset[str]]` (`{'vscode': frozenset({'darwin'})}`);
  `render.current_os() -> str` (raises `RenderError`); `render.applies(target: str, os_name: str) -> bool`.
  Behaviour: with no positional targets, render/check/diff only the targets that apply to the current OS; an explicitly
  named target that does not apply exits 2 with `target(s) not available on <os>: <names>`; `--list-targets` keeps
  listing **every** target on every OS (stow ownership stays strict and OS-independent).

- [ ] **Step 1: Write the failing tests** — in `tests/unit/test_render.py`, add `'DOTFILES_OS'` to `_SCRUBBED_VARS`; in
  the `world` fixture add `monkeypatch.setenv('DOTFILES_OS', 'darwin')` after the scrub loop (keeps existing tests
  host-independent); append:

```python
class TestOsTargets:
    """
    Tests for OS-scoped render targets
    """
    @staticmethod
    def _vscode(world: dict[str, Path]) -> Path:
        """
        Path of the rendered VS Code settings in the fixture HOME
        """
        return world['home'] / 'Library' / 'Application Support' / 'Code' / 'User' / 'settings.json'

    def test_vscode_is_skipped_on_linux(self, world: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that a default render on linux writes claude settings but not the macOS-only vscode target
        """
        monkeypatch.setenv('DOTFILES_OS', 'linux')
        _fragment(world['repo'], 'claude', {'a': 1})
        _fragment(world['repo'], 'vscode', {'b': 2})

        assert _run(world) == 0
        assert _claude(world).exists()
        assert not (world['home'] / 'Library').exists()

    def test_vscode_renders_on_darwin(self, world: dict[str, Path]) -> None:
        """
        Test that the vscode target still renders on darwin
        """
        _fragment(world['repo'], 'vscode', {'b': 2})
        assert _run(world) == 0
        assert json.loads(self._vscode(world).read_text(encoding='utf-8')) == {'b': 2}

    def test_explicit_foreign_target_is_config_error(
        self,
        world: dict[str, Path],
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that naming a target that does not apply to this OS exits 2 with an explanation
        """
        monkeypatch.setenv('DOTFILES_OS', 'linux')
        assert _run(world, 'vscode') == 2
        assert 'target(s) not available on linux: vscode' in capsys.readouterr().err

    def test_list_targets_ignores_the_os(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that --list-targets prints every target on linux, so stow ownership does not depend on the OS
        """
        monkeypatch.setenv('DOTFILES_OS', 'linux')
        assert render.main(['--list-targets']) == 0
        assert capsys.readouterr().out.splitlines() == [
            '.claude/settings.json',
            'Library/Application Support/Code/User/settings.json',
        ]

    def test_invalid_os_override_is_config_error(
        self,
        world: dict[str, Path],
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that an invalid DOTFILES_OS exits 2 naming the allowed values
        """
        monkeypatch.setenv('DOTFILES_OS', 'plan9')
        assert _run(world) == 2
        assert 'DOTFILES_OS must be darwin or linux' in capsys.readouterr().err
```

- [ ] **Step 2: Run to verify failure**

Run: `scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider tests/unit/test_render.py -k OsTargets`
Expected: FAIL — vscode renders on linux; foreign target accepted; invalid override ignored.

- [ ] **Step 3: Implement in `render.py`** — after the `TARGETS` dict:

```python
# Operating systems each target exists on (absent: every OS). VS Code keeps user settings under ~/Library only on macOS.
TARGET_OS: dict[str, frozenset[str]] = {
    'vscode': frozenset({'darwin'}),
}
```

Add, in the "Core script logic" section before `layers()`:

```python
def current_os() -> str:
    """
    Get the engine's OS id, honoring DOTFILES_OS like bootstrap/lib.sh's dotfiles_os.

    :raises RenderError: if the platform is unsupported or DOTFILES_OS is invalid
    :return: ``darwin`` or ``linux``
    """
    value = os.environ.get('DOTFILES_OS') or {'darwin': 'darwin', 'linux': 'linux'}.get(sys.platform, '')
    if value not in ('darwin', 'linux'):
        raise RenderError(f'unsupported OS {value or sys.platform!r}: DOTFILES_OS must be darwin or linux')
    return value


def applies(target: str, os_name: str) -> bool:
    """
    Check whether a target exists on an operating system.

    :param target: target id from :data:`TARGETS`
    :param os_name: ``darwin`` or ``linux``
    :return: True if the target is rendered on that OS
    """
    return os_name in TARGET_OS.get(target, frozenset({os_name}))
```

In `_main`, after the `--list-targets` block (which must stay before any OS filtering) and before the `try:` that calls
`layers()`, insert:

```python
    try:
        os_name = current_os()
    except RenderError as exc:
        error(str(exc))
        return 2

    if args.targets:
        foreign = [t for t in targets if not applies(t, os_name)]
        if foreign:
            error(f'target(s) not available on {os_name}: {", ".join(foreign)}')
            return 2
    else:
        targets = [t for t in targets if applies(t, os_name)]
```

- [ ] **Step 4: Run the render tests**

Run: `scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider tests/unit/test_render.py`
Expected: PASS (all existing tests unchanged thanks to the darwin pin in `world`).

- [ ] **Step 5: Full suite, hooks, commit**

```bash
scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider
prek run --files scripts/dotfiles/render.py tests/unit/test_render.py
git add scripts/dotfiles/render.py tests/unit/test_render.py
git commit -m "feat(engine): render the vscode target on macOS only"
```

---

### Task 6: Stage gating, the Linux preflight, and darwin-only sudo

**Files:**
- Modify: `bootstrap/bootstrap.sh` (compute the OS after sourcing `lib.sh`; gate `prime_sudo`)
- Modify: `bootstrap/00-preflight.sh` (rewrite)
- Modify: `bootstrap/60-macos.sh`, `bootstrap/72-vscode.sh`, `bootstrap/96-iterm2.sh` (`require_os darwin`)
- Modify: `bootstrap/README.md`
- Create: `tests/unit/test_os_stages.py`
- Test: `tests/unit/test_bootstrap_driver.py`

**Interfaces:**
- Consumes: `dotfiles_os`, `require_os`, `have`, `warn`, `die` (Task 2 / existing `lib.sh`).
- Produces: `00-preflight` honours `DOTFILES_OS_RELEASE` (test hook; default `/etc/os-release`). On Linux it accepts
  `ID=debian` or `debian` in `ID_LIKE`, and requires the commands `curl file git cc make ps zsh` (fatal on a real run,
  warning under dry-run).

- [ ] **Step 1: Write the failing stage tests** — create `tests/unit/test_os_stages.py`:

```python
"""
Unit tests for OS gating in the bootstrap stages (require_os and the Linux preflight)
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
STAGES    = REPO_ROOT / 'bootstrap'

# Inherited variables that would leak the developer's own configuration into the tests
_SCRUBBED_VARS: tuple[str, ...] = (
    'BOOTSTRAP_DRY_RUN',
    'DOTFILES_REPO',
    'DOTFILES_LAYER',
    'DOTFILES_BREW_PREFIXES',
    'DOTFILES_OS',
    'DOTFILES_OS_RELEASE',
    'XDG_CONFIG_HOME',
)

DEBIAN_RELEASE = 'PRETTY_NAME="Debian GNU/Linux 13 (trixie)"\nID=debian\n'
UBUNTU_RELEASE = 'PRETTY_NAME="Ubuntu 24.04 LTS"\nID=ubuntu\nID_LIKE=debian\n'
FEDORA_RELEASE = 'PRETTY_NAME="Fedora Linux 41"\nID=fedora\n'

LINUX_PREREQS: tuple[str, ...] = ('curl', 'file', 'git', 'cc', 'make', 'ps', 'zsh')


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    """
    Isolated environment: no overlays, a throwaway HOME, dry-run on
    """
    return {
        **{key: value for key, value in os.environ.items() if key not in _SCRUBBED_VARS},
        'HOME':                   str(tmp_path / 'home'),
        'DOTFILES_OVERLAYS_FILE': str(tmp_path / 'no-overlays'),
        'BOOTSTRAP_DRY_RUN':      '1',
    }


@pytest.fixture
def linux_bin(tmp_path: Path) -> Path:
    """
    A hermetic PATH for the Linux preflight: the two utilities the stage itself needs plus a stub per prerequisite
    """
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    for tool in ('dirname', 'uname'):
        real = shutil.which(tool)
        assert real is not None
        (bin_dir / tool).symlink_to(real)

    for tool in LINUX_PREREQS:
        stub = bin_dir / tool
        stub.write_text('#!/bin/sh\nexit 0\n', encoding='utf-8')
        stub.chmod(0o755)
    return bin_dir


def _stage(shell: str, name: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """
    Run a real stage script under the bash interpreter being tested, with stdin closed
    """
    return subprocess.run(
        [shell, str(STAGES / name)],
        capture_output=True,
        text=True,
        check=False,
        env=env,
        stdin=subprocess.DEVNULL,
    )


def _preflight(
    shell: str,
    env: dict[str, str],
    tmp_path: Path,
    bin_dir: Path,
    release: str,
    *,
    dry_run: bool = True,
) -> subprocess.CompletedProcess[str]:
    """
    Run 00-preflight as linux against a fixture os-release and the hermetic PATH
    """
    path = tmp_path / 'os-release'
    path.write_text(release, encoding='utf-8')
    return _stage(
        shell,
        '00-preflight.sh',
        {
            **env,
            'DOTFILES_OS':         'linux',
            'DOTFILES_OS_RELEASE': str(path),
            'PATH':                str(bin_dir),
            'BOOTSTRAP_DRY_RUN':   '1' if dry_run else '0',
        },
    )


class TestDarwinOnlyStages:
    """
    Tests for stages gated with require_os darwin
    """
    @pytest.mark.parametrize('stage', ['60-macos.sh', '72-vscode.sh', '96-iterm2.sh'])
    def test_skips_on_linux_without_running_anything(self, shell: str, env: dict[str, str], stage: str) -> None:
        """
        Test that the stage exits 0 on linux before any mutating command
        """
        result = _stage(shell, stage, {**env, 'DOTFILES_OS': 'linux'})
        assert result.returncode == 0, result.stderr
        assert 'skipped (darwin only; this is linux)' in result.stdout
        assert '[dry-run]' not in result.stdout

    @pytest.mark.skipif(sys.platform != 'darwin', reason='runs macOS commands outside run()')
    @pytest.mark.parametrize('stage', ['60-macos.sh', '96-iterm2.sh'])
    def test_runs_on_darwin(self, shell: str, env: dict[str, str], stage: str) -> None:
        """
        Test that the stage still previews its commands on darwin
        """
        result = _stage(shell, stage, {**env, 'DOTFILES_OS': 'darwin'})
        assert result.returncode == 0, result.stderr
        assert '[dry-run]' in result.stdout


class TestLinuxPreflight:
    """
    Tests for the Linux branch of 00-preflight
    """
    @pytest.mark.parametrize(
        ('release', 'pretty'),
        [
            (DEBIAN_RELEASE, 'Debian GNU/Linux 13 (trixie)'),
            (UBUNTU_RELEASE, 'Ubuntu 24.04 LTS'),
        ],
    )
    def test_debian_family_passes(
        self,
        shell: str,
        env: dict[str, str],
        tmp_path: Path,
        linux_bin: Path,
        release: str,
        pretty: str,
    ) -> None:
        """
        Test that Debian and a Debian derivative pass and are named in the log
        """
        result = _preflight(shell, env, tmp_path, linux_bin, release, dry_run=False)
        assert result.returncode == 0, result.stderr
        assert pretty in result.stdout
        assert 'preflight OK' in result.stdout

    def test_other_distribution_fails(self, shell: str, env: dict[str, str], tmp_path: Path, linux_bin: Path) -> None:
        """
        Test that a non-Debian distribution is refused
        """
        result = _preflight(shell, env, tmp_path, linux_bin, FEDORA_RELEASE)
        assert result.returncode != 0
        assert "unsupported Linux distribution 'fedora'" in result.stderr

    def test_missing_prerequisite_fails_a_real_run(
        self,
        shell: str,
        env: dict[str, str],
        tmp_path: Path,
        linux_bin: Path,
    ) -> None:
        """
        Test that a missing system command is fatal and points at the debian Ansible role
        """
        # cc, because lib.sh appends a Homebrew prefix to PATH and the Brewfile installs zsh, git, and curl there
        (linux_bin / 'cc').unlink()
        result = _preflight(shell, env, tmp_path, linux_bin, DEBIAN_RELEASE, dry_run=False)
        assert result.returncode != 0
        assert 'missing system commands: cc' in result.stderr
        assert "'debian' Ansible role"       in result.stderr

    def test_missing_prerequisite_only_warns_in_dry_run(
        self,
        shell: str,
        env: dict[str, str],
        tmp_path: Path,
        linux_bin: Path,
    ) -> None:
        """
        Test that a dry run reports the missing command without failing the preview
        """
        (linux_bin / 'cc').unlink()
        result = _preflight(shell, env, tmp_path, linux_bin, DEBIAN_RELEASE)
        assert result.returncode == 0, result.stderr
        assert 'missing system commands: cc' in result.stderr

    def test_unreadable_os_release_fails(self, shell: str, env: dict[str, str], tmp_path: Path, linux_bin: Path) -> None:
        """
        Test that a missing os-release file is fatal with the path in the message
        """
        result = _stage(
            shell,
            '00-preflight.sh',
            {**env, 'DOTFILES_OS': 'linux', 'DOTFILES_OS_RELEASE': str(tmp_path / 'absent'), 'PATH': str(linux_bin)},
        )
        assert result.returncode != 0
        assert f'cannot read {tmp_path / "absent"}' in result.stderr
```

- [ ] **Step 2: Write the failing driver tests** — in `tests/unit/test_bootstrap_driver.py` add `'DOTFILES_OS'` to
  `_SCRUBBED_VARS`. In `TestDryRun.test_dry_run_never_primes_sudo` change the env line to
  `stubbed = {**env, 'PATH': f'{bin_dir}:{env["PATH"]}', 'DOTFILES_OS': 'darwin'}`. Append to `TestDryRun`:

```python
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
```

- [ ] **Step 3: Run to verify failure**

Run: `scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider tests/unit/test_os_stages.py tests/unit/test_bootstrap_driver.py`
Expected: FAIL — stages run on linux; preflight dies with "targets macOS only"; `test_linux_never_primes_sudo` sees
the sentinel.

- [ ] **Step 4: Gate the macOS stages** — in each of `60-macos.sh`, `72-vscode.sh`, `96-iterm2.sh`, add on the line
  after `source "$HERE/lib.sh"`:

```bash
require_os darwin
```

- [ ] **Step 5: Rewrite `bootstrap/00-preflight.sh`**

```bash
#!/usr/bin/env bash
# 00-preflight: verify the platform. macOS: ensure the Xcode Command Line Tools. Linux: require a Debian-family
# distribution and the system commands the engine cannot install itself (it never runs apt or sudo on Linux; the NAS
# `debian` Ansible role provides them).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh disable=SC1091
source "$HERE/lib.sh"

# /etc/os-release identifies the Linux distribution; DOTFILES_OS_RELEASE points elsewhere (tests)
OS_RELEASE="${DOTFILES_OS_RELEASE:-/etc/os-release}"

# Commands the Linux engine needs from the system: Homebrew's build prerequisites (build-essential, procps, curl, file,
# git) plus zsh for the stowed shell
LINUX_PREREQS=(curl file git cc make ps zsh)

preflight_darwin() {
    log "macOS $(sw_vers -productVersion) on $(uname -m)"

    # Xcode Command Line Tools
    if xcode-select -p >/dev/null 2>&1; then
        log "Xcode CLT already installed at $(xcode-select -p)"
    else
        log "installing Xcode Command Line Tools (a GUI dialog may appear)"
        run xcode-select --install || true
        warn "complete the CLT install dialog, then re-run: bootstrap.sh --from 00-preflight"
    fi
}

preflight_linux() {
    local id id_like pretty cmd missing="" msg
    [ -r "$OS_RELEASE" ] || die "cannot read $OS_RELEASE to identify the Linux distribution"
    # shellcheck source=/dev/null
    id="$(. "$OS_RELEASE" && printf '%s' "${ID:-}")"
    # shellcheck source=/dev/null
    id_like="$(. "$OS_RELEASE" && printf '%s' "${ID_LIKE:-}")"
    # shellcheck source=/dev/null
    pretty="$(. "$OS_RELEASE" && printf '%s' "${PRETTY_NAME:-Linux}")"
    case " $id $id_like " in
    *" debian "*) ;;
    *) die "unsupported Linux distribution '$id' (the engine supports Debian and its derivatives)" ;;
    esac
    log "$pretty on $(uname -m)"

    for cmd in "${LINUX_PREREQS[@]}"; do
        if ! have "$cmd"; then
            missing="$missing $cmd"
        fi
    done
    if [ -n "$missing" ]; then
        msg="missing system commands:$missing (install them with the NAS 'debian' Ansible role, or: sudo apt-get"
        msg="$msg install build-essential procps curl file git zsh)"
        if [ "${BOOTSTRAP_DRY_RUN}" = "1" ]; then
            warn "$msg"
        else
            die "$msg"
        fi
    fi
}

OS="$(dotfiles_os)"
case "$OS" in
darwin) preflight_darwin ;;
linux) preflight_linux ;;
esac

# On macOS, sudo is primed once by the driver (bootstrap.sh) and kept alive for the whole run.
log "preflight OK"
```

- [ ] **Step 6: Gate sudo in `bootstrap/bootstrap.sh`** — right after `REPO="$DOTFILES_REPO"` add
  `DRIVER_OS="$(dotfiles_os)" || exit 1`. Replace the `prime_sudo` call and its comment with:

```bash
# Prime sudo once, here in the driver, and keep it alive for the whole run. The keep-alive loop
# is tied to this process, so it outlives the individual stage subshells (which all share this
# tty's cached credential). No-op under dry-run. macOS only: no Linux stage needs root (root-level
# setup belongs to Ansible), and a password prompt would block an unattended run.
if [ "$DRIVER_OS" = "darwin" ]; then
    prime_sudo
fi
```

- [ ] **Step 7: Run the tests**

Run: `scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider tests/unit/test_os_stages.py tests/unit/test_bootstrap_driver.py`
Expected: PASS.

- [ ] **Step 8: Document in `bootstrap/README.md`**
  - Stage table: `00-preflight` → "macOS: Command Line Tools present. Linux: Debian family and the system commands
    `curl file git cc make ps zsh` (fatal; warning under `--dry-run`)". Append " (macOS only)" to the `60-macos`,
    `72-vscode`, and `96-iterm2` purposes.
  - Stage environment table: add a `DOTFILES_OS` row — "`darwin` or `linux` from `uname -s`; set it to preview
    another OS's selection (stages, stow packages, render targets)".
  - New section "## OS support" before "## Stages":

```markdown
## OS support

The engine runs on macOS and on Debian-family Linux with Homebrew (Linuxbrew) in `/home/linuxbrew/.linuxbrew`.
`lib.sh` `dotfiles_os` reports `darwin` or `linux` (`DOTFILES_OS` overrides it). A stage that only makes sense on one
OS calls `require_os <os>...` right after sourcing `lib.sh`; elsewhere it logs the skip and exits 0. On Linux the engine
never runs `apt` or `sudo`: the driver does not prime sudo, and `00-preflight` fails (warns under `--dry-run`) when a
system command is missing. Stow packages opt into an OS with a `.dotfiles-os` marker (see
[`stow/README.md`](../stow/README.md)); Brewfile entries that exist only on macOS sit inside `if OS.mac?`.
```

- [ ] **Step 9: Full suite, hooks, commit**

```bash
scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider
prek run --files bootstrap/bootstrap.sh bootstrap/00-preflight.sh bootstrap/60-macos.sh bootstrap/72-vscode.sh bootstrap/96-iterm2.sh bootstrap/README.md tests/unit/test_os_stages.py tests/unit/test_bootstrap_driver.py
git add bootstrap/bootstrap.sh bootstrap/00-preflight.sh bootstrap/60-macos.sh bootstrap/72-vscode.sh bootstrap/96-iterm2.sh bootstrap/README.md tests/unit/test_os_stages.py tests/unit/test_bootstrap_driver.py
git commit -m "feat(engine): gate macOS stages, add a Linux preflight, and prime sudo on macOS only"
```

---

### Task 7: Linuxbrew install path in `50-brew`

**Files:**
- Modify: `bootstrap/50-brew.sh`
- Test: `tests/unit/test_brew_stage.py`

**Interfaces:**
- Consumes: `dotfiles_os`, `sha256_of` (Task 2).
- Produces: on Linux, `install_homebrew` requires `$LINUXBREW_PREFIX` (default `/home/linuxbrew/.linuxbrew`; test hook
  `DOTFILES_LINUXBREW_PREFIX`) to be an existing writable directory (fatal on a real run, warning in dry-run), and runs
  the installer as `env NONINTERACTIVE=1 /bin/bash <installer>`. macOS invocation is byte-for-byte unchanged. The
  legacy `/usr/local/bin/starship` cleanup runs on darwin only.

- [ ] **Step 1: Write the failing tests** — in `tests/unit/test_brew_stage.py`:
  - Change `INSTALLER_PAYLOAD`'s first command from `'touch "$INSTALLER_MARKER"\n'` to
    `'printf "%s" "${NONINTERACTIVE-unset}" > "$INSTALLER_MARKER"\n'` and its comment to "records that it ran (and
    whether NONINTERACTIVE was set) and installs a stub brew into the sandbox prefix".
  - Add `'DOTFILES_OS'` and `'DOTFILES_LINUXBREW_PREFIX'` to the sandbox's `scrubbed` tuple, and add
    `'DOTFILES_OS': 'darwin',` to the sandbox `env` dict (existing tests stay macOS-path tests on any host).
  - In `test_matching_checksum_runs_installer`, after `assert sandbox.marker.exists()` add
    `assert sandbox.marker.read_text(encoding='utf-8') == 'unset'  # macOS runs the installer interactively, as before`.
  - Append:

```python
def _pin_payload(box: Sandbox) -> None:
    """
    Pin the sandbox stage to the stub payload's real digest (the real pin cannot be satisfied by chosen bytes)
    """
    text   = box.stage.read_text(encoding='utf-8')
    digest = hashlib.sha256(box.payload).hexdigest()
    box.stage.write_text(PINNED_SHA.sub(f'BREW_INSTALLER_SHA256="{digest}"', text), encoding='utf-8')


class TestLinuxbrewInstall:
    """
    Tests for the Linux (Linuxbrew) install path
    """
    def test_installs_noninteractively_into_a_writable_prefix(
        self,
        shell: str,
        sandbox: Sandbox,
        tmp_path: Path,
    ) -> None:
        """
        Test that linux runs the verified installer with NONINTERACTIVE=1 and without sudo
        """
        prefix = tmp_path / 'linuxbrew'
        prefix.mkdir()
        _pin_payload(sandbox)
        sandbox.env.update({'DOTFILES_OS': 'linux', 'DOTFILES_LINUXBREW_PREFIX': str(prefix)})

        result = _run(shell, sandbox)
        assert result.returncode == 0, result.stderr
        assert 'installer checksum verified' in result.stdout
        assert sandbox.marker.read_text(encoding='utf-8') == '1'
        assert not sandbox.sudo_marker.exists()

    def test_missing_prefix_fails_before_downloading(self, shell: str, sandbox: Sandbox, tmp_path: Path) -> None:
        """
        Test that linux refuses to install when the prefix does not exist, before any download
        """
        sandbox.env.update({'DOTFILES_OS': 'linux', 'DOTFILES_LINUXBREW_PREFIX': str(tmp_path / 'absent')})

        result = _run(shell, sandbox)
        assert result.returncode != 0
        assert 'must exist and be writable' in result.stderr
        assert not sandbox.curl_args.exists()
        assert not sandbox.marker.exists()

    def test_missing_prefix_only_warns_in_dry_run(self, shell: str, sandbox: Sandbox, tmp_path: Path) -> None:
        """
        Test that a dry run reports the missing prefix and still previews the install
        """
        sandbox.env.update(
            {'DOTFILES_OS': 'linux', 'DOTFILES_LINUXBREW_PREFIX': str(tmp_path / 'absent'), 'BOOTSTRAP_DRY_RUN': '1'},
        )

        result = _run(shell, sandbox)
        assert result.returncode == 0, result.stderr
        assert 'must exist and be writable' in result.stderr
        assert "env NONINTERACTIVE=1 /bin/bash <temp file>" in result.stdout
```

- [ ] **Step 2: Run to verify failure**

Run: `scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider tests/unit/test_brew_stage.py`
Expected: FAIL — marker reads `unset` on linux; missing prefix is not checked.

- [ ] **Step 3: Implement in `bootstrap/50-brew.sh`**

(a) After `source "$HERE/lib.sh"` add:

```bash
OS="$(dotfiles_os)"

# Homebrew's Linux prefix. The engine never uses sudo on Linux, so the prefix must already exist and be writable by the
# user (the NAS `debian` Ansible role creates it); the installer then needs no root. DOTFILES_LINUXBREW_PREFIX moves
# this check for tests only: the installer itself always targets the default prefix.
LINUXBREW_PREFIX="${DOTFILES_LINUXBREW_PREFIX:-/home/linuxbrew/.linuxbrew}"
```

(b) Replace `install_homebrew` with:

```bash
# install_homebrew -> download the official installer, verify its checksum, then run it.
install_homebrew() {
    local actual msg installer_env=()
    if [ "$OS" = "linux" ]; then
        if [ ! -d "$LINUXBREW_PREFIX" ] || [ ! -w "$LINUXBREW_PREFIX" ]; then
            msg="$LINUXBREW_PREFIX must exist and be writable by $(id -un) so Homebrew installs without sudo"
            msg="$msg (the NAS 'debian' Ansible role creates it)"
            if [ "${BOOTSTRAP_DRY_RUN}" = "1" ]; then
                warn "$msg"
            else
                die "$msg"
            fi
        fi
        # The installer's confirmation prompt would block an unattended run (Ansible)
        installer_env=(env NONINTERACTIVE=1)
    fi

    if [ "${BOOTSTRAP_DRY_RUN}" = "1" ]; then
        run curl -fsSL "$BREW_INSTALLER_URL" -o '<temp file>'
        log "would verify the installer's SHA-256 is $BREW_INSTALLER_SHA256"
        run ${installer_env[@]+"${installer_env[@]}"} /bin/bash '<temp file>'
        return 0
    fi

    BREW_INSTALLER="$(mktemp "${TMPDIR:-/tmp}/brew-install.XXXXXX")"
    trap cleanup_installer EXIT
    run curl -fsSL "$BREW_INSTALLER_URL" -o "$BREW_INSTALLER"

    actual="$(sha256_of "$BREW_INSTALLER")"
    if [ "$actual" != "$BREW_INSTALLER_SHA256" ]; then
        warn "Homebrew installer checksum mismatch"
        warn "  expected: $BREW_INSTALLER_SHA256"
        warn "  actual:   $actual"
        warn "the URL is pinned to an upstream commit: treat this as a bad or tampered download, not a Homebrew update"
        warn "retry first; re-pin $0 and nas_bootstrap.sh together only to adopt a newer upstream commit (README.md)"
        die "Homebrew installer checksum mismatch; retry with: bootstrap.sh --from 50-brew"
    fi
    log "installer checksum verified"

    run ${installer_env[@]+"${installer_env[@]}"} /bin/bash "$BREW_INSTALLER"
}
```

(c) Starship block: change its condition's start to `if [ "$OS" = "darwin" ] && have brew && brew list starship …` and
prefix its comment with "macOS only: ".

- [ ] **Step 4: Run the tests**

Run: `scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider tests/unit/test_brew_stage.py tests/unit/test_nas_bootstrap.py`
Expected: PASS (`test_nas_bootstrap.py`'s pin-equality test still sees identical pins).

- [ ] **Step 5: Full suite, hooks, commit**

```bash
scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider
prek run --files bootstrap/50-brew.sh tests/unit/test_brew_stage.py
git add bootstrap/50-brew.sh tests/unit/test_brew_stage.py
git commit -m "feat(engine): install Linuxbrew without sudo in the 50-brew stage"
```

---

### Task 8: macOS-only Brewfile entries

**Files:**
- Modify: `bootstrap/Brewfile`, `bootstrap/README.md` (Manifests table)
- Modify: `tests/unit/test_profiles.py:22` (`_ENTRY` regex)
- Test: `tests/unit/test_brewfile.py`

**Interfaces:**
- Consumes: `bundle_list`, `check_golden` (Task 1).
- Produces: on Linux, `brew bundle` sees the 3 taps and 58 formulae (all but `mas`), no casks, no Mac App Store
  entries. On darwin the resolved set equals the Task 1 golden files.

- [ ] **Step 1: Write the failing tests** — append to `tests/unit/test_brewfile.py` (add `import json`):

```python
# Formulae that exist only on macOS; they live inside the Brewfile's `if OS.mac?` block
DARWIN_ONLY_FORMULAE = frozenset({'mas'})


@pytest.mark.skipif(sys.platform != 'linux', reason='linux resolution')
class TestLinuxBrewfile:
    """
    Tests for what Linuxbrew resolves the base Brewfile to
    """
    def test_no_casks_or_mac_app_store_entries(self) -> None:
        """
        Test that casks and Mac App Store entries are invisible on linux
        """
        assert bundle_list('--cask') == []
        assert bundle_list('--mas')  == []

    def test_formulae_are_the_darwin_formulae_minus_macos_only(self) -> None:
        """
        Test that linux gets every darwin formula except the macOS-only ones
        """
        darwin = (GOLDEN_DIR / 'brewfile-darwin-formulae.txt').read_text(encoding='utf-8').splitlines()
        assert bundle_list('--formula') == sorted(set(darwin) - DARWIN_ONLY_FORMULAE)

    def test_no_formula_requires_macos(self) -> None:
        """
        Test that no formula linux installs declares a macOS requirement (the Brewfile's taps must be tapped)
        """
        assert BREW is not None
        result = subprocess.run(
            [BREW, 'info', '--json=v2', '--formula', *bundle_list('--formula')],
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, 'HOMEBREW_NO_AUTO_UPDATE': '1'},
        )
        assert result.returncode == 0, result.stderr

        macos_only = [
            formula['full_name']
            for formula in json.loads(result.stdout)['formulae']
            if any(req['name'] == 'macos' for req in formula['requirements'])
        ]
        assert macos_only == []
```

and change the import line to `from tests.golden import GOLDEN_DIR` + `from tests.golden import check_golden` (one per
line). On a Mac these skip; they run in the Linux CI job (Task 10). On darwin, `TestDarwinBrewfile` is the guard.

Also edit `tests/unit/test_profiles.py:22`: `_ENTRY = re.compile(r'^\s*(tap|brew|cask|mas)\s+"([^"]+)"')` — entries
inside an `if OS.mac?` block are indented, and the profile duplicate check must still see them.

- [ ] **Step 2: Verify the darwin guard catches a mistake (sanity)** — temporarily delete the `cask "zed"` line, run
  `scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider tests/unit/test_brewfile.py`, expect FAIL in
  `TestDarwinBrewfile`, then restore the line (`git checkout bootstrap/Brewfile`).

- [ ] **Step 3: Edit `bootstrap/Brewfile`**
  - Remove `brew "mas"` from the Formulae keep-sorted block.
  - Replace everything from the `# Casks` comment to the end of the file with the block below. Copy the cask, font,
    and `mas` lines verbatim from the current file, indented by two spaces; keep the existing keep-sorted markers
    around the casks.

```ruby
# macOS-only entries: the `mas` CLI, casks, fonts, and Mac App Store apps. Homebrew on Linux skips this block, so the
# NAS (Linuxbrew) installs the same formulae as the Macs and nothing else.
if OS.mac?
  brew "mas"

  # Casks
  # keep-sorted start
  cask "claude-devtools"
  cask "google-chrome"
  cask "hammerspoon"
  cask "iterm2"
  cask "pycharm"
  cask "signal"
  cask "slack"
  cask "sublime-text"
  cask "todoist-app"
  cask "visual-studio-code"
  cask "zed"
  # keep-sorted end

  # Fonts (Nerd Fonts live in the main homebrew/cask repo; the homebrew/cask-fonts tap is deprecated)
  cask "font-fira-code-nerd-font"

  # Mac App Store (requires `mas` and an authenticated App Store session)
  mas "Amphetamine", id: 937984704
  mas "Apple Remote Desktop", id: 409907375
end
```

  - Add to the header comment: "Wrap anything that does not exist on Linux in the `if OS.mac?` block at the end."

- [ ] **Step 4: Update `bootstrap/README.md`** — Manifests table, `Brewfile` row format cell: "`brew bundle` syntax;
  macOS-only entries inside `if OS.mac?`". (Overlay Brewfiles registered only on Macs, such as
  `profiles/personal-mac`, need no guard.)

- [ ] **Step 5: Run the tests**

Run: `scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider tests/unit/test_brewfile.py tests/unit/test_profiles.py`
Expected: PASS on macOS — `TestDarwinBrewfile` proves the sorted darwin resolution is unchanged (the `mas` formula only
moved); the Linux class skips.

- [ ] **Step 6: Full suite, hooks, commit**

```bash
scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider
prek run --files bootstrap/Brewfile bootstrap/README.md tests/unit/test_brewfile.py tests/unit/test_profiles.py
git add bootstrap/Brewfile bootstrap/README.md tests/unit/test_brewfile.py tests/unit/test_profiles.py
git commit -m "feat(engine): keep casks, fonts, and Mac App Store entries out of Linuxbrew"
```

---

### Task 9: Shell portability

**Files:**
- Modify: `stow/shell/.config/zsh/conf.d/40-aliases.zsh`, `stow/os_tools/.config/zsh/conf.d/90-banner.zsh`
- Test: `tests/integration/test_home.py`, `tests/integration/test_os_layout.py`

**Interfaces:**
- Produces: `VISUAL` is `subl` on macOS and `micro` (from the shared Brewfile) elsewhere, where `st` is also aliased to
  `micro` so the `zshconfig`/`zshrc`/`bashconfig` aliases work; `o` (`open .`) exists on macOS only (Debian's `open` is
  `openvt`); fastfetch passes `--logo macOS2` on macOS only. All branches key off zsh's `$OSTYPE` at runtime.

- [ ] **Step 1: Write the failing tests** — in `tests/integration/test_home.py` add `import sys` if absent and a new
  class at the end of the file:

```python
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
```

In `tests/integration/test_os_layout.py`, add to `TestLinuxLayout` (gated on zsh being installed):

```python
    @pytest.mark.skipif(shutil.which('zsh') is None, reason='zsh not installed')
    def test_interactive_zsh_is_clean_with_the_linux_layout(self, tmp_path: Path) -> None:
        """
        Test that an interactive zsh over the linux layout starts without any error output
        """
        linked_paths(tmp_path, 'linux')
        home = tmp_path / 'home-linux'

        env: dict[str, str] = {
            'HOME':               str(home),
            'PATH':               os.environ['PATH'],
            'TERM':               'dumb',
            'DOTFILES_NO_BANNER': '1',
            'XDG_CONFIG_HOME':    str(home / '.config'),
            'XDG_STATE_HOME':     str(home / '.local' / 'state'),
            'XDG_DATA_HOME':      str(home / '.local' / 'share'),
        }
        result = subprocess.run(['zsh', '-i', '-c', 'true'], capture_output=True, text=True, check=False, env=env)
        assert result.returncode == 0
        assert result.stderr == ''
```

- [ ] **Step 2: Run to verify failure (macOS host)**

Run: `scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider tests/integration/test_home.py -k Portability tests/integration/test_os_layout.py`
Expected on macOS: `TestPortability` already PASSES (current values are the macOS values) — it becomes a real check on
the Linux runner. The Linux-layout zsh test PASSES or exposes a startup error to fix in this task. This task is
verified as a whole by the Linux CI job in Task 10.

- [ ] **Step 3: Edit `40-aliases.zsh`** — replace

```zsh
# Set default pager/editor
export PAGER=moor
export VISUAL=subl
```

with

```zsh
# Set default pager/editor: Sublime Text on macOS; elsewhere (the headless NAS) micro from the shared Brewfile, which
# also stands in for Sublime's `st` so the config aliases below work
export PAGER=moor
if [[ $OSTYPE == darwin* ]]; then
    export VISUAL=subl
else
    export VISUAL=micro
    alias st=micro
fi
```

and replace the line `alias o="open ."` with

```zsh
# macOS only: Linux's `open` is openvt
if [[ $OSTYPE == darwin* ]]; then
    alias o="open ."
fi
```

- [ ] **Step 4: Edit `90-banner.zsh`** — replace `    fastfetch -c archey --logo macOS2` with

```zsh
    if [[ $OSTYPE == darwin* ]]; then
        fastfetch -c archey --logo macOS2
    else
        fastfetch -c archey
    fi
```

- [ ] **Step 5: Run the tests**

Run: `scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider`
Expected: all pass (the darwin goldens are unaffected; snippet content changes do not alter link paths).

- [ ] **Step 6: Hooks and commit**

```bash
prek run --files stow/shell/.config/zsh/conf.d/40-aliases.zsh stow/os_tools/.config/zsh/conf.d/90-banner.zsh tests/integration/test_home.py tests/integration/test_os_layout.py
git add stow/shell/.config/zsh/conf.d/40-aliases.zsh stow/os_tools/.config/zsh/conf.d/90-banner.zsh tests/integration/test_home.py tests/integration/test_os_layout.py
git commit -m "feat(shell): make the editor, open alias, and banner logo OS-aware"
```

---

### Task 10: Linux CI job, architecture docs, and CI verification

**Files:**
- Modify: `.github/workflows/lint.yml` (new job after `pytest`)
- Modify: `.ctx/ARCHITECTURE.md` ("macOS: Stow Engine and Bootstrap Stages" section)

- [ ] **Step 1: Add the job** — in `.github/workflows/lint.yml`, after the `pytest (macOS)` job:

```yaml
  pytest-linux:
    name: pytest (Linux)
    runs-on: ubuntu-latest
    env:
      HOMEBREW_NO_AUTO_UPDATE: "1"
      HOMEBREW_NO_ENV_HINTS: "1"
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
      # The runner image ships Linuxbrew in the same prefix the NAS uses; fail loudly if that ever changes
      - name: Put Linuxbrew on PATH
        run: |
          test -x /home/linuxbrew/.linuxbrew/bin/brew || { echo "::error::no Linuxbrew on this runner image"; exit 1; }
          echo /home/linuxbrew/.linuxbrew/bin >> "$GITHUB_PATH"
      # stow.sh parses Stow 2.4.x conflict messages; apt ships 2.3.x, and the NAS gets Stow from the Brewfile too
      - name: Install GNU Stow (Linuxbrew) and zsh (apt)
        run: |
          brew install stow
          sudo apt-get update && sudo apt-get install -y zsh
      - name: Tap the Brewfile's taps
        run: brew bundle list --tap --file bootstrap/Brewfile | xargs -n1 brew tap
      - name: Install dependencies
        run: uv sync --group test
      - name: Pytest
        run: uv run pytest
      - name: Bootstrap dry run (throwaway HOME)
        run: mkdir -p "$RUNNER_TEMP/home" && HOME="$RUNNER_TEMP/home" bash bootstrap/bootstrap.sh --dry-run --no-log
```

- [ ] **Step 2: Update `.ctx/ARCHITECTURE.md`** — rename the heading to "## Stow Engine and Bootstrap Stages (macOS +
  Linux)" and add a bullet after the `profiles/` bullet:

```markdown
- **OS support**: `lib.sh` `dotfiles_os` (`darwin`/`linux`, `DOTFILES_OS` override) and `require_os` gate stages;
  `.dotfiles-os` markers scope stow packages; `render.py` `TARGET_OS` scopes render targets; the Brewfile's
  `if OS.mac?` block holds macOS-only entries. Linux means Debian-family with Linuxbrew; the engine never runs `apt` or
  `sudo` there (root-level setup is the NAS Ansible's job). Contract in [`bootstrap/README.md`](../bootstrap/README.md).
```

  Leave the "Two Provisioning Systems" section alone (sub-project 4 rewrites it once the NAS uses the engine).

- [ ] **Step 3: Validate the workflow locally**

Run: `prek run --files .github/workflows/lint.yml .ctx/ARCHITECTURE.md` (yamllint) and
`scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider`
Expected: both pass.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/lint.yml .ctx/ARCHITECTURE.md
git commit -m "ci: run pytest and a bootstrap dry run on Linux"
```

- [ ] **Step 5: Ask the owner to approve pushing the branch**, then push and open a draft PR (base `main`). Watch the
  `pytest (Linux)` job: `gh pr checks --watch`.

- [ ] **Step 6: Triage Linux CI failures** — for each failing test, read the log (`gh run view --log-failed`) and
  classify:
  - **Portability bug in engine code** (e.g. a BSD-only flag, a macOS path): fix the code, add or extend a unit test
    that reproduces it under `DOTFILES_OS=linux` or on Linux, commit as `fix(engine): …`.
  - **Test that encodes a macOS-only fact** (e.g. a test of the macOS layout that does not use the darwin-pinned
    `home` fixture): pin it with `DOTFILES_OS=darwin` or gate it with
    `@pytest.mark.skipif(sys.platform != 'darwin', reason='<the macOS fact>')`, naming the fact in `reason`.
  - **Missing tool on the runner**: install it in the job if the NAS will have it (from the Brewfile, via
    `brew install`); otherwise gate the test on `shutil.which(...)`, as the existing tests do.

  Never edit a darwin golden file to make CI pass. Push the fixes; repeat until both `pytest (macOS)` and
  `pytest (Linux)` are green.

- [ ] **Step 7: Report the follow-up to the owner** — adding `pytest (Linux)` to the "Default branch - required CI
  checks" ruleset is a repository-settings change; propose it, do not make it unasked.

---

## Self-review (completed at plan time)

- **Spec coverage:** OS detection → Task 2; stage gating and `00-preflight` Linux branch → Task 6; package gating and
  marked packages → Task 3; `python`/hatch → Task 4; Brewfile `if OS.mac?` → Task 8; `ensure_brew_on_path` Linuxbrew
  prefix → Task 2; `50-brew` without sudo and `NONINTERACTIVE` → Task 7; shell tweaks → Task 9; `render.py` vscode
  darwin-only → Task 5; `pytest (Linux)` CI job and dry run → Task 10; macOS no-op proof → Task 1 goldens, re-run in
  every task; bash 3.2 → global constraint plus the existing `shell` fixture. `doctor` and `50-directories.zsh` are
  intentionally unchanged (see "Deliberate deviations").
- **Open questions from the spec, resolved:** (1) hatch: the config stays at its macOS path, and Linux gets hatch's
  default `~/.config/hatch` via an in-repo symlink (Task 4). (3) Linux prerequisites: `build-essential procps curl
  file git zsh` (Task 6). (4) Linuxbrew on `ubuntu-latest`: the CI job asserts `/home/linuxbrew/.linuxbrew/bin/brew`
  and fails loudly otherwise (Task 10). (5) macOS-only formulae: `mas` is known. `test_no_formula_requires_macos`
  audits the rest on Linux CI and keeps auditing future additions (Task 8). (2) The NAS SSH endpoint belongs to
  sub-project 3.
- **Verified at plan time:** `brew bundle list --all/--formula/--cask/--mas/--tap` work (76/59/12/2/3 entries). Stow
  2.4.1 relinks a file moved between packages on `--restow` (exit 0). The suite baseline is 584 passed.
- **Name consistency:** `dotfiles_os`, `require_os`, `sha256_of`, `DOTFILES_OS`, `DOTFILES_OS_RELEASE`,
  `DOTFILES_LINUXBREW_PREFIX`, `.dotfiles-os`, `TARGET_OS`, `current_os`, `applies`, `check_golden`, `GOLDEN_DIR`,
  `linked_paths`, `bundle_list`, `DARWIN_ONLY`, `LINUX_ONLY`, and `DARWIN_ONLY_FORMULAE` are used identically across
  tasks.
