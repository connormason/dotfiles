# Dev-Env Engine Implementation Plan (Phase A, part 1 of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the layered dotfiles engine in this repo — overlay registry, stow driver, bootstrap driver, JSON
settings renderer, and `run.py` commands — plus the two leak-guard prerequisites, all testable without touching any
machine's `$HOME`.

**Architecture:** One shell library (`bootstrap/lib.sh`) owns layer resolution (`dotfiles_layers`), so `stow.sh`,
`bootstrap.sh`, and the Python renderer all agree on the layer list. `stow.sh` discovers packages per layer, enforces
single ownership of every `$HOME` path, and always stows with `--no-folding`. `bootstrap.sh` merges numbered stages from
all layers. `scripts/dotfiles/render.py` deep-merges per-layer JSON fragments into real settings files behind a drift
guard. `run.py` gains thin commands over these tools.

**Tech Stack:** bash 3.2-compatible shell (macOS `/bin/bash`), GNU Stow 2.4, Python 3.9+ stdlib, pytest, prek, GitHub
Actions.

**Spec:** `docs/plans/2026-10/2026-10-26-dev-env-base-overlay-design.md`
**Next plan:** `docs/plans/2026-10/2026-10-27-dev-env-port-plan.md` (packages, stages, profile, cleanup, Phase B)

## Global Constraints

- Branch: `dev-env-base` (worktree `.claude/worktrees/dev-env-base`, based on `main` after #17). Never commit to or
  push `main`.
- **Every uv invocation goes through `scripts/hooks/uv-public.sh`** (e.g. `scripts/hooks/uv-public.sh run --group
  test pytest …`). Never bare `uv`. Before each commit confirm `uv.lock` is unmodified.
- **Public repo.** No file may contain employer domains, email addresses, internal host labels, internal tool/product
  names, or tracker URLs — not even split across string concatenation. Describe employer content generically
  ("work overlay", "employer Homebrew prefix"). Tests build the corporate domain only as `'apple' + '.com'`.
- The work repo `~/dotfiles` is **read-only reference** for this plan: copy from it, never modify it.
- Shell: `#!/usr/bin/env bash` + `set -euo pipefail`; bash 3.2 compatible (no associative arrays, no `mapfile`, guard
  empty arrays as `${A[@]+"${A[@]}"}`, use `if …; then …; fi` instead of `cond && action` as a loop's last statement).
  shellcheck- and shfmt-clean (repo prek hooks enforce both).
- Python: `from __future__ import annotations` first; one import per line; single quotes; sphinx docstrings; no blank
  line between a class docstring and its first member; boxed `# ====` section headers. Never run `ruff format`.
- Tests: pytest, classes `TestX`, every method `-> None`, multi-line docstrings, capitalized, no trailing period. Tests
  that need GNU Stow are skipped when `stow` is not on `PATH`.
- Layer contract (from the spec), binding on every task:
  - Overlays registry: `${DOTFILES_OVERLAYS_FILE:-${XDG_CONFIG_HOME:-$HOME/.config}/dotfiles/overlays}`, one absolute
    (or `~/`-prefixed) path per line, `#` comments and blank lines ignored; a listed path that does not exist is an
    error.
  - Layer order: repo root first, then overlays in file order.
  - Layer parts: `stow/<pkg>/`, `bootstrap/NN-*.sh`, `bootstrap/{Brewfile,uv-tools.txt,vscode-extensions.txt,repos.txt}`,
    `bootstrap/env.sh`, `render/<id>.json`.

## File Map

| File                                                   | Action | Responsibility                                                  |
| ------------------------------------------------------ | ------ | --------------------------------------------------------------- |
| `scripts/hooks/check-leaks-push.sh`                    | Create | pre-push scan of pushed commits' identities and messages        |
| `.pre-commit-config.yaml`                              | Modify | `pre-push` hook entries + install type                          |
| `bootstrap/lib.sh`                                     | Create | Shared shell helpers incl. `dotfiles_layers`, `manifest_files`  |
| `stow.sh`                                              | Create | Layered stow driver with ownership check                        |
| `scripts/utility/summarize_stow.awk`                   | Create | Stow log summarizer (ported verbatim)                           |
| `bootstrap/bootstrap.sh`                               | Create | Layered stage driver                                            |
| `bootstrap/00-preflight.sh`                            | Create | First base stage (ported)                                       |
| `bootstrap/README.md`                                  | Create | Stage table + overlay contract                                  |
| `scripts/dotfiles/render.py`                           | Create | Fragment merge renderer with drift guard                        |
| `run.py`, `Makefile`, `docs/RUN_PY_REFERENCE.md`       | Modify | `bootstrap`, `stow`, `render`, `doctor`, `test` commands        |
| `tests/unit/test_*.py`                                 | Create | One test module per component                                   |
| `.github/workflows/lint.yml`                           | Modify | Engine tests on `macos-latest` with GNU Stow                    |

---

### Task 1: Leak-guard prerequisites (private patterns + pre-push check)

**Files:**

- Create: `scripts/hooks/check-leaks-push.sh`
- Modify: `.pre-commit-config.yaml` (`default_install_hook_types`; the `repo: local` block holding `check-leaks`)
- Modify: `scripts/hooks/README.md`
- Test: `tests/unit/test_check_leaks_push.py`
- Local only (never committed): `~/.config/dotfiles/leak-patterns.txt`

**Interfaces:**

- Consumes: `scripts/hooks/check-leaks.py` CLI (`FILENAMES…`, `--identities-from FILE|-`; exit 0 clean / 1 findings /
  2 config error).
- Produces: `check-leaks-push.sh` — no args; reads `PRE_COMMIT_FROM_REF` / `PRE_COMMIT_TO_REF`; exit codes as
  `check-leaks.py`.

- [ ] **Step 1: Private pattern file (controller + user, not a subagent)**

The controller drafts `~/.config/dotfiles/leak-patterns.txt` from the work repo: one case-insensitive regex per
internal tool name, internal product name, internal host label, internal repository name, and internal package/tap
prefix found in `~/dotfiles` (the private package map from the planning session lists them). Use word boundaries
(`\bname\b`) for short names to avoid false positives. The **user reviews the file** before it is used. It lives only on
the work Mac; Phase C moves it into the work overlay.

Verify: `scripts/hooks/check-leaks.py -v README.md` reports more than 2 patterns, and running it over the work repo's
employer-only packages (`git -C ~/dotfiles ls-files -z | …`, restricted to those package directories) reports findings
in every one of them. Then `prek run check-leaks --all-files` in this repo must still pass — if a private pattern
matches existing public content, tighten the pattern (do not edit the content to dodge it unless it really is a leak).

- [ ] **Step 2: Write the failing tests**

`tests/unit/test_check_leaks_push.py`:

```python
"""
Unit tests for scripts/hooks/check-leaks-push.sh
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT    = REPO_ROOT / 'scripts' / 'hooks' / 'check-leaks-push.sh'

# Built at runtime so this file never contains the literal identifier it exercises
CORP_DOMAIN = 'apple' + '.com'


def _git(repo: Path, *args: str, env: dict[str, str] | None = None) -> str:
    """
    Run git in a fixture repo and return stdout
    """
    result = subprocess.run(['git', '-C', str(repo), *args], capture_output=True, text=True, check=True, env=env)
    return result.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """
    Fixture git repo with one clean root commit; private patterns isolated away
    """
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'xdg'))
    monkeypatch.delenv('DOTFILES_LEAK_PATTERNS', raising=False)
    for role in ('AUTHOR', 'COMMITTER'):
        monkeypatch.setenv(f'GIT_{role}_NAME', 'Jane Doe')
        monkeypatch.setenv(f'GIT_{role}_EMAIL', 'jane@example.org')
    path = tmp_path / 'repo'
    path.mkdir()
    _git(path, 'init', '-q', '-b', 'main', '--template=')
    _git(path, 'commit', '-q', '--allow-empty', '-m', 'root')
    return path


def _commit(repo: Path, message: str, email: str = 'jane@example.org') -> str:
    """
    Create an empty commit and return its sha
    """
    env = {**os.environ, 'GIT_AUTHOR_EMAIL': email, 'GIT_COMMITTER_EMAIL': email}
    _git(repo, 'commit', '-q', '--allow-empty', '-m', message, env=env)
    return _git(repo, 'rev-parse', 'HEAD')


def _run(repo: Path, from_ref: str | None, to_ref: str) -> subprocess.CompletedProcess[str]:
    """
    Run the pre-push script inside the fixture repo
    """
    env = {**os.environ, 'PRE_COMMIT_TO_REF': to_ref}
    if from_ref is not None:
        env['PRE_COMMIT_FROM_REF'] = from_ref
    return subprocess.run([str(SCRIPT)], cwd=repo, capture_output=True, text=True, check=False, env=env)


class TestCheckLeaksPush:
    """
    Tests for check-leaks-push.sh
    """
    def test_clean_range_passes(self, repo: Path) -> None:
        """
        Test that clean messages and identities pass
        """
        base = _git(repo, 'rev-parse', 'HEAD')
        head = _commit(repo, 'feat: clean change')
        assert _run(repo, base, head).returncode == 0

    def test_leaky_message_fails(self, repo: Path) -> None:
        """
        Test that a corporate domain in a pushed commit message is rejected
        """
        base = _git(repo, 'rev-parse', 'HEAD')
        head = _commit(repo, f'fix: talk to pkgs.{CORP_DOMAIN}')
        result = _run(repo, base, head)
        assert result.returncode == 1
        assert CORP_DOMAIN not in result.stdout

    def test_leaky_author_fails(self, repo: Path) -> None:
        """
        Test that a corporate author email in the pushed range is rejected
        """
        base = _git(repo, 'rev-parse', 'HEAD')
        head = _commit(repo, 'chore: cherry-picked', email=f'jane@{CORP_DOMAIN}')
        assert _run(repo, base, head).returncode == 1

    def test_commits_before_range_are_ignored(self, repo: Path) -> None:
        """
        Test that history before the pushed range is not scanned
        """
        old  = _commit(repo, f'old: mentions {CORP_DOMAIN}')
        head = _commit(repo, 'feat: clean change')
        assert _run(repo, old, head).returncode == 0

    def test_unknown_from_ref_scans_tip_only(self, repo: Path) -> None:
        """
        Test that an unreachable from-ref without an upstream falls back to the tip commit only
        """
        _commit(repo, f'old: mentions {CORP_DOMAIN}')
        head = _commit(repo, 'feat: clean tip')
        assert _run(repo, '0' * 40, head).returncode == 0
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `scripts/hooks/uv-public.sh run --group test pytest tests/unit/test_check_leaks_push.py`
Expected: FAIL — `FileNotFoundError` / permission error for the missing script.

- [ ] **Step 4: Implement the script**

`scripts/hooks/check-leaks-push.sh`:

```bash
#!/usr/bin/env bash
# pre-push leak scan of the commits being pushed: author/committer identities and commit messages.
#
# cherry-pick, rebase, am, and `git commit --no-verify` bypass the pre-commit and commit-msg hooks, so this is the
# last local gate before content becomes public. File contents in the pushed range are scanned by the separate
# check-leaks pre-push hook entry. Range: PRE_COMMIT_FROM_REF..PRE_COMMIT_TO_REF when the from-ref exists locally;
# otherwise merge-base(to, origin/main)..to; otherwise the tip commit only.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
to="${PRE_COMMIT_TO_REF:-HEAD}"
from="${PRE_COMMIT_FROM_REF:-}"

range=()
if [ -n "$from" ] && git cat-file -e "$from^{commit}" 2>/dev/null; then
    range=("$from..$to")
elif base="$(git merge-base "$to" origin/main 2>/dev/null)"; then
    range=("$base..$to")
else
    range=(-1 "$to")
fi

msgs="$(mktemp "${TMPDIR:-/tmp}/check-leaks-msgs.XXXXXX")"
trap 'rm -f "$msgs"' EXIT
git log --format=%B "${range[@]}" >"$msgs"
git log --format='%an <%ae>%n%cn <%ce>' "${range[@]}" |
    "$here/check-leaks.py" --identities-from - "$msgs"
```

Run: `chmod +x scripts/hooks/check-leaks-push.sh`

- [ ] **Step 5: Wire the pre-push hooks**

In `.pre-commit-config.yaml`, add `pre-push` to `default_install_hook_types`, and append to the `repo: local` hooks list
that holds `check-leaks` / `check-leaks-msg`:

```yaml
      # pre-push: scan file contents changed in the pushed range (catches content committed with --no-verify)
      - id: check-leaks-push-files
        name: "[check]  internal identifiers in pushed files"
        stages: [pre-push]
        priority: 10
        entry: scripts/hooks/check-leaks.py
        language: python
        types: [text]

      # pre-push: scan identities + messages of the pushed commits (cherry-picks/rebases bypass commit hooks)
      - id: check-leaks-push-history
        name: "[check]  internal identifiers in pushed commits"
        stages: [pre-push]
        priority: 10
        entry: scripts/hooks/check-leaks-push.sh
        language: system
        pass_filenames: false
        always_run: true
```

Run: `prek install -f` (installs the new `pre-push` shim alongside the others).

- [ ] **Step 6: Verify end-to-end and document**

Run: `scripts/hooks/uv-public.sh run --group test pytest tests/unit/test_check_leaks_push.py` → PASS.
Run: `PRE_COMMIT_FROM_REF=origin/main PRE_COMMIT_TO_REF=HEAD scripts/hooks/check-leaks-push.sh; echo "exit=$?"` →
`exit=0`.
Confirm which env var names prek actually exports to pre-push hooks: temporarily add `env | grep -i ref >&2` at the top
of the script, run `prek run --hook-stage pre-push check-leaks-push-history --from-ref origin/main --to-ref HEAD`, then
remove the debug line. If prek uses different names, support both (fall back in the `from`/`to` assignments) and adjust
the tests.

Add a `check-leaks-push.sh` section to `scripts/hooks/README.md` (purpose, range rules, the two hook ids, exit codes) and
add both hook ids to the Scripts table. Run `prek run mdformat --files scripts/hooks/README.md`.

- [ ] **Step 7: Commit**

```bash
git add scripts/hooks/check-leaks-push.sh .pre-commit-config.yaml scripts/hooks/README.md tests/unit/test_check_leaks_push.py
git commit -m "feat(hooks): scan pushed commits and files for leaks at pre-push"
```

---

### Task 2: Shared shell library and layer registry (`bootstrap/lib.sh`)

**Files:**

- Create: `bootstrap/lib.sh` (ported from `~/dotfiles/bootstrap/lib.sh`, then modified)
- Test: `tests/unit/test_lib_sh.py`

**Interfaces:**

- Produces (sourced by `stow.sh`, `bootstrap.sh`, every stage, and `render.py` via `bash -c`):
  - `DOTFILES_REPO` — repo root (exported; honors a pre-set value)
  - `log MSG…`, `warn MSG…`, `die MSG…`, `have CMD`, `fmt_duration SECONDS`, `run CMD…` (dry-run aware via
    `BOOTSTRAP_DRY_RUN=1`), `try CMD…`, `prime_sudo`, `confirm PROMPT`, `ensure_brew_on_path` — same behavior as the
    work repo's versions
  - `dotfiles_overlays_file` — prints the registry path
  - `dotfiles_layers` — prints the repo root, then each overlay root (absolute, one per line); dies on a missing overlay
  - `manifest_files NAME` — prints `<layer>/bootstrap/NAME` for every layer that has it, in layer order
  - At source time: each layer's `bootstrap/env.sh` is sourced (layer order), then `ensure_brew_on_path` runs

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_lib_sh.py`:

```python
"""
Unit tests for bootstrap/lib.sh
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
LIB       = REPO_ROOT / 'bootstrap' / 'lib.sh'


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    """
    Environment with an isolated HOME and overlays registry
    """
    home = tmp_path / 'home'
    home.mkdir()
    return {
        **os.environ,
        'HOME': str(home),
        'XDG_CONFIG_HOME': str(home / '.config'),
        'DOTFILES_OVERLAYS_FILE': str(tmp_path / 'overlays'),
        'BOOTSTRAP_DRY_RUN': '0',
    }


def _bash(script: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """
    Source lib.sh in a fresh bash and run script
    """
    return subprocess.run(
        ['bash', '-c', f'source "{LIB}"\n{script}'],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def _overlay(tmp_path: Path, name: str) -> Path:
    """
    Create an empty overlay directory
    """
    path = tmp_path / name
    (path / 'bootstrap').mkdir(parents=True)
    return path


class TestDotfilesLayers:
    """
    Tests for dotfiles_layers
    """
    def test_no_registry_prints_repo_only(self, env: dict[str, str]) -> None:
        """
        Test that without an overlays file only the repo root is a layer
        """
        result = _bash('dotfiles_layers', env)
        assert result.returncode == 0
        assert result.stdout.splitlines() == [str(REPO_ROOT)]

    def test_registry_order_comments_and_tilde(self, env: dict[str, str], tmp_path: Path) -> None:
        """
        Test that overlays follow the repo in file order, ignoring comments and blanks and expanding ~/
        """
        first  = _overlay(tmp_path, 'first')
        second = _overlay(Path(env['HOME']), 'second')
        Path(env['DOTFILES_OVERLAYS_FILE']).write_text(
            f'# overlays\n\n{first}   # trailing comment\n~/second\n',
            encoding='utf-8',
        )
        result = _bash('dotfiles_layers', env)
        assert result.returncode == 0
        assert result.stdout.splitlines() == [str(REPO_ROOT), str(first), str(second.resolve())]

    def test_missing_overlay_fails(self, env: dict[str, str], tmp_path: Path) -> None:
        """
        Test that a registered overlay that does not exist is an error
        """
        Path(env['DOTFILES_OVERLAYS_FILE']).write_text(f'{tmp_path / "nope"}\n', encoding='utf-8')
        result = _bash('true', env)
        assert result.returncode != 0
        assert 'overlay not found' in result.stderr


class TestManifestFiles:
    """
    Tests for manifest_files
    """
    def test_lists_existing_fragments_in_layer_order(self, env: dict[str, str], tmp_path: Path) -> None:
        """
        Test that manifest fragments are listed base first, skipping layers without the file
        """
        with_file    = _overlay(tmp_path, 'with')
        without_file = _overlay(tmp_path, 'without')
        (with_file / 'bootstrap' / 'repos.txt').write_text('x\n', encoding='utf-8')
        Path(env['DOTFILES_OVERLAYS_FILE']).write_text(f'{without_file}\n{with_file}\n', encoding='utf-8')
        result = _bash('manifest_files repos.txt', env)
        assert result.returncode == 0
        expected = [str(with_file / 'bootstrap' / 'repos.txt')]
        if (REPO_ROOT / 'bootstrap' / 'repos.txt').exists():
            expected.insert(0, str(REPO_ROOT / 'bootstrap' / 'repos.txt'))
        assert result.stdout.splitlines() == expected


class TestLayerEnv:
    """
    Tests for per-layer bootstrap/env.sh
    """
    def test_overlay_env_is_sourced(self, env: dict[str, str], tmp_path: Path) -> None:
        """
        Test that an overlay's bootstrap/env.sh is sourced when lib.sh loads
        """
        overlay = _overlay(tmp_path, 'ov')
        (overlay / 'bootstrap' / 'env.sh').write_text('export LAYER_ENV_PROBE=from-overlay\n', encoding='utf-8')
        Path(env['DOTFILES_OVERLAYS_FILE']).write_text(f'{overlay}\n', encoding='utf-8')
        result = _bash('printf "%s" "$LAYER_ENV_PROBE"', env)
        assert result.stdout == 'from-overlay'


class TestRun:
    """
    Tests for the dry-run aware run helper
    """
    def test_run_executes_when_not_dry(self, env: dict[str, str]) -> None:
        """
        Test that run executes its command normally
        """
        assert _bash('run echo hello', env).stdout.strip() == 'hello'

    def test_run_skips_when_dry(self, env: dict[str, str], tmp_path: Path) -> None:
        """
        Test that run only prints under BOOTSTRAP_DRY_RUN=1
        """
        marker = tmp_path / 'marker'
        result = _bash(f'run touch "{marker}"', {**env, 'BOOTSTRAP_DRY_RUN': '1'})
        assert result.returncode == 0
        assert not marker.exists()
        assert '[dry-run]' in result.stdout

    def test_have(self, env: dict[str, str]) -> None:
        """
        Test that have reports PATH presence
        """
        assert _bash('have bash', env).returncode == 0
        assert _bash('have definitely-not-a-command-xyz', env).returncode != 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `scripts/hooks/uv-public.sh run --group test pytest tests/unit/test_lib_sh.py`
Expected: FAIL (lib.sh missing → bash `source` error, non-zero exits).

- [ ] **Step 3: Port lib.sh and add the layer functions**

Copy `~/dotfiles/bootstrap/lib.sh` to `bootstrap/lib.sh`. Then:

1. Directly after `set -euo pipefail` and the `BOOTSTRAP_DRY_RUN` default, add:

```bash
# Repo root (this file lives in <repo>/bootstrap/). Exported so overlay stages can source "$DOTFILES_REPO/bootstrap/lib.sh".
DOTFILES_REPO="${DOTFILES_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
export DOTFILES_REPO
```

2. Replace the existing `ensure_brew_on_path` function (whatever its body) with this version — it must not name any
   employer-specific prefix:

```bash
# Append the first Homebrew prefix that has bin/brew to PATH. Appended (not prepended) so an active virtualenv's python
# is not shadowed. A layer's bootstrap/env.sh may set DOTFILES_BREW_PREFIXES (space-separated) to add prefixes.
ensure_brew_on_path() {
    local prefix
    for prefix in ${DOTFILES_BREW_PREFIXES:-/opt/homebrew /usr/local}; do
        if [ -x "$prefix/bin/brew" ]; then
            case ":$PATH:" in
                *":$prefix/bin:"*) ;;
                *) PATH="$PATH:$prefix/bin:$prefix/sbin" ;;
            esac
            export PATH
            return 0
        fi
    done
    return 0
}
```

3. Append the layer functions:

```bash
# Path of the overlays registry (one overlay root per line; '#' comments and blank lines ignored).
dotfiles_overlays_file() {
    printf '%s\n' "${DOTFILES_OVERLAYS_FILE:-${XDG_CONFIG_HOME:-$HOME/.config}/dotfiles/overlays}"
}

# Print the repo root, then each registered overlay root (absolute), one per line. Dies on a missing overlay.
dotfiles_layers() {
    local registry line
    registry="$(dotfiles_overlays_file)"
    printf '%s\n' "$DOTFILES_REPO"
    if [ ! -f "$registry" ]; then
        return 0
    fi
    while IFS= read -r line || [ -n "$line" ]; do
        line="${line%%#*}"
        line="${line#"${line%%[![:space:]]*}"}"
        line="${line%"${line##*[![:space:]]}"}"
        if [ -z "$line" ]; then
            continue
        fi
        case "$line" in
            "~/"*) line="$HOME/${line#\~/}" ;;
        esac
        if [ ! -d "$line" ]; then
            die "overlay not found: $line (listed in $registry)"
        fi
        (cd "$line" && pwd -P)
    done <"$registry"
}

# Print <layer>/bootstrap/NAME for every layer that provides it, base first.
manifest_files() {
    local layers layer
    layers="$(dotfiles_layers)" || return 1
    while IFS= read -r layer; do
        if [ -f "$layer/bootstrap/$1" ]; then
            printf '%s\n' "$layer/bootstrap/$1"
        fi
    done <<EOF
$layers
EOF
}

# Source every layer's bootstrap/env.sh (base first) so overlays can set variables base stages read.
_dotfiles_source_layer_env() {
    local layers layer
    layers="$(dotfiles_layers)" || exit 1
    while IFS= read -r layer; do
        if [ -f "$layer/bootstrap/env.sh" ]; then
            # shellcheck source=/dev/null
            source "$layer/bootstrap/env.sh"
        fi
    done <<EOF
$layers
EOF
}
```

4. Replace the file's final top-level `ensure_brew_on_path` call with:

```bash
_dotfiles_source_layer_env
ensure_brew_on_path
```

The repo root itself is printed with `pwd` (from step 1); tests compare against `Path(__file__).resolve()` — if the
worktree path contains a symlink, change step 1 to `pwd -P` so both agree.

- [ ] **Step 4: Run tests to verify they pass**

Run: `scripts/hooks/uv-public.sh run --group test pytest tests/unit/test_lib_sh.py` → PASS.
Run: `prek run --files bootstrap/lib.sh` → shellcheck/shfmt/check-leaks pass (run the private-pattern guard: the port
must not carry employer content).

- [ ] **Step 5: Commit**

```bash
git add bootstrap/lib.sh tests/unit/test_lib_sh.py
git commit -m "feat(bootstrap): shared shell library with overlay layer registry"
```

---

### Task 3: Layered stow driver (`stow.sh`)

**Files:**

- Create: `stow.sh`
- Create: `scripts/utility/summarize_stow.awk` (copy verbatim from `~/dotfiles/scripts/utility/summarize_stow.awk`)
- Create: `tests/unit/test_stow_summary.py` (copy verbatim from `~/dotfiles/tests/unit/test_stow_summary.py`; fix the
  awk path constant if it differs)
- Test: `tests/unit/test_stow_sh.py`

**Interfaces:**

- Consumes: `bootstrap/lib.sh` (`dotfiles_layers`, `die`).
- Produces: `stow.sh [-n|--simulate] [-v|--verbose] [--summary|--no-summary] [--backup-conflicts] [--list] [PKG…]`
  - `--list`: prints `<pkg>\t<layer-root>` per package (layer order, then directory order), exit 0
  - exit 0 success / dry-run; 1 ownership conflict (identical path or file-vs-directory), duplicate package, unknown
    package, missing overlay, any unresolvable stow conflict, backup-able conflict without `--backup-conflicts`,
    failed post-backup re-verification, combined short flags, bad `STOW_VERBOSE`; stow's own code on an unexpected apply
    failure
  - all-or-nothing apply: every layer is simulated first (`stow -n`), conflicts are classified, and nothing is changed
    unless the whole plan is clean:
    - backup-able (moved to `~/.dotfiles-backup/<timestamp>/` by `--backup-conflicts`; never directories): a regular file
      (`cannot stow … over existing target <T> since neither a link nor a directory …`,
      `existing target is neither a link nor a directory: <T>`) or a foreign symlink
      (`existing target is not owned by stow: <T>`) at `$HOME/<T>`
    - unresolvable (abort, nothing moved or linked, also under `-n`): any other conflict, a real directory where a
      package provides a file, a stow fatal error with no parseable conflict
    - after a backup, every layer is re-verified; if still not clean, nothing is linked and the backup dir is reported
  - every stow call passes `--no-folding --ignore='\.DS_Store' --restow`; the ownership check mirrors stow's built-in
    ignores (`README.*`, `LICENSE.*`, exact `COPYING` at the package root only)
  - final line: `stow: applied <pkgs>` | `stow: simulated <pkgs> (dry-run, no changes written)` |
    `stow: simulated <pkgs> (dry-run; <N> conflicting file(s) would be backed up first, then linked)` (preceded by one
    `stow: would back up existing <T> -> <dir>/<T>` line per target; stow reports no link plan while conflicts exist, so no
    summary is printed in that case)
  - summary lines from the awk summarizer (`stow: no changes (already current)` when nothing changed)

- [ ] **Step 1: Copy the summarizer and its tests; run them**

Copy the two files named above. Run: `scripts/hooks/uv-public.sh run --group test pytest tests/unit/test_stow_summary.py`
→ PASS.

- [ ] **Step 2: Write the failing stow.sh tests**

`tests/unit/test_stow_sh.py`:

```python
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
_SCRUBBED_VARS = (
    'DOTFILES_REPO',
    'DOTFILES_BREW_PREFIXES',
    'DOTFILES_LEAK_PATTERNS',
    'DOTFILES_OVERLAYS_FILE',
    'STOW_VERBOSE',
)

pytestmark = pytest.mark.skipif(shutil.which('stow') is None, reason='GNU Stow not installed')


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
    overlay = tmp_path / 'overlay'
    (overlay / 'stow').mkdir(parents=True)
    home = tmp_path / 'home'
    home.mkdir()
    return {'repo': repo, 'overlay': overlay, 'home': home, 'registry': tmp_path / 'overlays', 'shell': Path(shell)}


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
    env = {
        **{key: value for key, value in os.environ.items() if key not in _SCRUBBED_VARS},
        'HOME': str(world['home']),
        'XDG_CONFIG_HOME': str(world['home'] / '.config'),
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
        _pkg(world['repo'], 'shell', {'.zshrc': 'x'})
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
        _pkg(world['repo'], 'shell', {'.zshrc': 'x'})
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
    def test_two_packages_same_path_fails_before_linking(self, world: dict[str, Path]) -> None:
        """
        Test that two packages providing one path abort the run and name both owners
        """
        _pkg(world['repo'], 'shell', {'.zshrc': 'a', '.zprofile': 'a'})
        _pkg(world['overlay'], 'work-shell', {'.zshrc': 'b'})
        result = _stow(world)
        assert result.returncode == 1
        assert '~/.zshrc <- shell,work-shell' in result.stderr
        assert not (world['home'] / '.zprofile').exists()

    def test_file_versus_directory_collision_fails(self, world: dict[str, Path]) -> None:
        """
        Test that one package providing a path as a file and another providing files beneath it is rejected
        """
        _pkg(world['repo'], 'a-pkg', {'.config/app': 'file', '.zshrc': 'x'})
        _pkg(world['overlay'], 'b-pkg', {'.config/app/settings': 'nested'})
        result = _stow(world)
        assert result.returncode == 1
        assert '~/.config/app <- a-pkg (file), b-pkg (directory)' in result.stderr
        assert not (world['home'] / '.zshrc').exists()

    def test_collision_check_covers_unselected_packages(self, world: dict[str, Path]) -> None:
        """
        Test that ownership is checked across all packages even when only one is requested
        """
        _pkg(world['repo'], 'shell', {'.zshrc': 'a'})
        _pkg(world['overlay'], 'work-shell', {'.zshrc': 'b'})
        result = _stow(world, 'shell')
        assert result.returncode == 1
        assert '~/.zshrc <- shell,work-shell' in result.stderr

    def test_readme_at_package_root_is_ignored(self, world: dict[str, Path]) -> None:
        """
        Test that package-root README files (ignored by stow) do not count as owned paths
        """
        _pkg(world['repo'], 'shell', {'README.md': 'docs', '.zshrc': 'x'})
        _pkg(world['overlay'], 'work-shell', {'README.md': 'docs'})
        assert _stow(world).returncode == 0

    def test_nested_readme_is_not_ignored(self, world: dict[str, Path]) -> None:
        """
        Test that stow's README ignore is root-only, so a nested README still counts as an owned path
        """
        _pkg(world['repo'], 'a-pkg', {'.config/app/README.md': 'a'})
        _pkg(world['overlay'], 'b-pkg', {'.config/app/README.md': 'b'})
        result = _stow(world)
        assert result.returncode == 1
        assert '~/.config/app/README.md <- a-pkg,b-pkg' in result.stderr

    def test_ds_store_is_ignored_everywhere(self, world: dict[str, Path]) -> None:
        """
        Test that .DS_Store files neither collide across packages nor get linked
        """
        _pkg(world['repo'], 'a-pkg', {'.DS_Store': 'a', '.config/app/.DS_Store': 'a', '.config/app/f': 'a'})
        _pkg(world['overlay'], 'b-pkg', {'.DS_Store': 'b', '.bashrc': 'b'})
        result = _stow(world)
        assert result.returncode == 0, result.stderr
        assert (world['home'] / '.config' / 'app' / 'f').is_symlink()
        assert not (world['home'] / '.DS_Store').exists()
        assert not (world['home'] / '.config' / 'app' / '.DS_Store').exists()

    def test_copying_txt_at_package_root_is_counted_but_copying_is_not(self, world: dict[str, Path]) -> None:
        """
        Test that only an exact COPYING at the package root is ignored, matching stow's built-in rules
        """
        _pkg(world['repo'], 'a-pkg', {'COPYING': 'a', 'COPYING.txt': 'a'})
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
        _pkg(world['repo'], 'shell', {'.config/zsh/conf.d/00-lib.zsh': 'base'})
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

    def test_passthrough_flag_does_not_imply_dry_run(self, world: dict[str, Path]) -> None:
        """
        Test that a flag forwarded to stow does not make the run a simulation
        """
        _pkg(world['repo'], 'shell', {'.zshrc': 'x'})
        result = _stow(world, '--ignore=nothing-matches-this')
        assert result.returncode == 0, result.stderr
        assert (world['home'] / '.zshrc').is_symlink()
        assert 'stow: applied shell' in result.stdout


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
        assert '.zshrc' in result.stderr
        assert '.foreign' in result.stderr
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
        assert 'stow: would back up existing .zshrc -> ' in result.stdout
        assert 'stow: would back up existing .foreign -> ' in result.stdout
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
        target = foreign.readlink()
        result = _stow(world, '--backup-conflicts')
        assert result.returncode == 0, result.stderr
        assert (world['home'] / '.zshrc').is_symlink()
        assert (world['home'] / '.foreign').is_symlink()
        assert (world['home'] / '.foreign').readlink() != target
        zshrc_backups = list((world['home'] / '.dotfiles-backup').glob('*/.zshrc'))
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
        _pkg(world['repo'], 'shell', {'.zshrc': 'repo'})
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
        _pkg(world['repo'], 'shell', {'.zshrc': 'repo', '.bashrc': 'repo'})
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
        shim = shim_dir / 'stow'
        # Once a backup directory exists, every simulated stow reports a fresh unresolvable conflict
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `scripts/hooks/uv-public.sh run --group test pytest tests/unit/test_stow_sh.py`
Expected: FAIL (`stow.sh` missing).

- [ ] **Step 4: Implement `stow.sh`**

```bash
#!/usr/bin/env bash
# Stow the base layer's packages, then every registered overlay's, into $HOME.
#
# Usage: stow.sh [-n|--simulate] [-v|--verbose] [--summary|--no-summary] [--backup-conflicts] [--list] [PACKAGE...]
#
#   Layers     <repo>/stow, then <overlay>/stow for each overlay in the registry (bootstrap/lib.sh: dotfiles_layers)
#   Packages   every directory in a layer's stow/; a package name may exist in only one layer
#   Ownership  no two packages may provide the same $HOME-relative path (or a file where another has a directory);
#              checked before anything is linked
#   Folding    always --no-folding: $HOME directories stay real, so several packages (and apps' runtime state) can
#              share them, and nothing an app writes lands inside a repository
#   Apply      all-or-nothing: every layer is simulated first. Unresolvable conflicts (a real directory where a package
#              provides a file, ...) abort with nothing changed. Blocking regular files and foreign symlinks abort too
#              unless --backup-conflicts moves them to ~/.dotfiles-backup/<timestamp>/ first; the layers are then
#              re-verified and only a clean result is linked. -n previews exactly this, writing nothing.
#
# Env: STOW_VERBOSE=N raises stow's verbosity and prints its raw log.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"

# Help must work even when the overlay registry is broken, so it is handled before lib.sh is sourced.
for arg in "$@"; do
    case "$arg" in
    -h | --help)
        sed -n '2,/^set -euo pipefail/p' "${BASH_SOURCE[0]}" | sed -e '$d' -e 's/^# \{0,1\}//'
        exit 0
        ;;
    esac
done

SUMMARIZER="$REPO_DIR/scripts/utility/summarize_stow.awk"
# Pin the base layer to this checkout: an inherited DOTFILES_REPO from another checkout must not redirect it.
DOTFILES_REPO="$REPO_DIR"
export DOTFILES_REPO
# shellcheck source=/dev/null  # lib.sh is sourced at runtime from the repo root; shellcheck runs without -x
source "$REPO_DIR/bootstrap/lib.sh"

DRY_RUN=0
PASSTHRU=()
SHOW_RAW=0
SHOW_SUMMARY=1
BACKUP_CONFLICTS=0
LIST_ONLY=0
LEVEL="${STOW_VERBOSE:-0}"
case "$LEVEL" in
*[!0-9]*) die "STOW_VERBOSE must be a non-negative integer (got '$LEVEL')" ;;
esac
if [ "$LEVEL" -gt 0 ]; then
    SHOW_RAW=1
fi
WANT=()
for arg in "$@"; do
    case "$arg" in
    -n | --no | --simulate) DRY_RUN=1 ;;
    -v | --verbose)
        SHOW_RAW=1
        [ "$LEVEL" -ge 1 ] || LEVEL=1
        ;;
    --summary) SHOW_SUMMARY=1 ;;
    --no-summary) SHOW_SUMMARY=0 ;;
    --backup-conflicts) BACKUP_CONFLICTS=1 ;;
    --list) LIST_ONLY=1 ;;
    -[!-]?*) die "combined short flags are not supported: $arg (pass each flag separately, e.g. -n -v)" ;;
    -*) PASSTHRU+=("$arg") ;;
    *) WANT+=("$arg") ;;
    esac
done

# ---------------------------------------------------------------------------------------------------------------------
# Discovery: parallel arrays (bash 3.2 has no associative arrays)
# ---------------------------------------------------------------------------------------------------------------------
PKG_NAMES=()
PKG_LAYERS=()

pkg_index() { # print the index of package $1, or return 1
    local i
    for i in ${PKG_NAMES[@]+"${!PKG_NAMES[@]}"}; do
        if [ "${PKG_NAMES[$i]}" = "$1" ]; then
            printf '%s\n' "$i"
            return 0
        fi
    done
    return 1
}

LAYERS_OUT="$(dotfiles_layers)" || exit 1
while IFS= read -r layer; do
    if [ ! -d "$layer/stow" ]; then
        continue
    fi
    for dir in "$layer"/stow/*/; do
        if [ ! -d "$dir" ]; then
            continue
        fi
        pkg="$(basename "$dir")"
        if idx="$(pkg_index "$pkg")"; then
            die "package '$pkg' is defined in two layers: ${PKG_LAYERS[$idx]} and $layer"
        fi
        PKG_NAMES+=("$pkg")
        PKG_LAYERS+=("$layer")
    done
done <<EOF
$LAYERS_OUT
EOF

if [ "$LIST_ONLY" = 1 ]; then
    for i in ${PKG_NAMES[@]+"${!PKG_NAMES[@]}"}; do
        printf '%s\t%s\n' "${PKG_NAMES[$i]}" "${PKG_LAYERS[$i]}"
    done
    exit 0
fi

if [ ${#PKG_NAMES[@]} -eq 0 ]; then
    echo "stow: no packages found"
    exit 0
fi

SEL=()
if [ ${#WANT[@]} -eq 0 ]; then
    SEL=("${!PKG_NAMES[@]}")
else
    for pkg in "${WANT[@]}"; do
        idx="$(pkg_index "$pkg")" || die "unknown package: $pkg"
        already=0
        for i in ${SEL[@]+"${SEL[@]}"}; do
            if [ "$i" = "$idx" ]; then
                already=1
            fi
        done
        if [ "$already" = 0 ]; then
            SEL+=("$idx")
        fi
    done
fi

SEL_NAMES=()
for i in "${SEL[@]}"; do
    SEL_NAMES+=("${PKG_NAMES[$i]}")
done

# ---------------------------------------------------------------------------------------------------------------------
# Ownership: every $HOME-relative path belongs to exactly one package (across all packages, not just selected ones), and
# no package provides a file at a path another package uses as a directory.
# The prune list and root-level ignores mirror stow's built-in ignore list (Stow.pm, __DATA__): file names such as
# README.md only count as ignored at the package root, and only an exact COPYING is ignored there.
# ---------------------------------------------------------------------------------------------------------------------
package_files() { # $1=index: $HOME-relative paths the package provides, honoring stow's default ignores
    (
        cd "${PKG_LAYERS[$1]}/stow/${PKG_NAMES[$1]}" &&
            find . \( -name .git -o -name .gitignore -o -name .gitmodules -o -name .DS_Store -o -name RCS -o -name CVS \
                -o -name .cvsignore -o -name .svn -o -name _darcs -o -name .hg -o -name '?*,v' -o -name '?*~' \
                -o -name '.#?*' -o -name '#*#' \) -prune -o \( -type f -o -type l \) -print |
            sed 's|^\./||' | grep -v -E '^(README.*|LICENSE.*|COPYING)$' || true
    )
}

OWNERS="$(
    for i in "${!PKG_NAMES[@]}"; do
        package_files "$i" | awk -v pkg="${PKG_NAMES[$i]}" '{ print $0 "\t" pkg }'
    done
)"
# Prints "<path><TAB><owners>" for each identical-path clash ("pkgA,pkgB") and each file-vs-directory clash
# ("pkgA (file), pkgB (directory)")
COLLISIONS="$(printf '%s\n' "$OWNERS" | awk -F'\t' '
    $1 == "" { next }
    {
        path = $1
        pkg = $2
        files[path] = (path in files) ? files[path] "," pkg : pkg
        nfile[path]++
        n = split(path, parts, "/")
        prefix = ""
        for (i = 1; i < n; i++) {
            prefix = (i == 1) ? parts[1] : prefix "/" parts[i]
            if (!((prefix SUBSEP pkg) in seen)) {
                seen[prefix SUBSEP pkg] = 1
                dirs[prefix] = (prefix in dirs) ? dirs[prefix] ", " pkg " (directory)" : pkg " (directory)"
            }
        }
    }
    END {
        for (p in files) {
            if (nfile[p] > 1) print p "\t" files[p]
            if (p in dirs) print p "\t" files[p] " (file), " dirs[p]
        }
    }' | LC_ALL=C sort)"
if [ -n "$COLLISIONS" ]; then
    echo "stow: these paths are provided by more than one package:" >&2
    while IFS=$'\t' read -r path owners; do
        printf '  ~/%s <- %s\n' "$path" "$owners" >&2
    done <<EOF
$COLLISIONS
EOF
    exit 1
fi

# ---------------------------------------------------------------------------------------------------------------------
# Layer runs: one stow invocation per layer that has selected packages
# ---------------------------------------------------------------------------------------------------------------------
EFF_LEVEL="$LEVEL"
if [ "$SHOW_SUMMARY" = 1 ] && [ "$EFF_LEVEL" -lt 1 ]; then
    EFF_LEVEL=1
fi
VERBOSE=()
if [ "$EFF_LEVEL" -gt 0 ]; then
    VERBOSE=(--verbose="$EFF_LEVEL")
fi

PKGS=()
load_pkgs() { # fill PKGS with the selected package names that live in layer $1
    local i
    PKGS=()
    for i in "${SEL[@]}"; do
        if [ "${PKG_LAYERS[$i]}" = "$1" ]; then
            PKGS+=("${PKG_NAMES[$i]}")
        fi
    done
}

LAYER_ROOTS=()
while IFS= read -r layer; do
    load_pkgs "$layer"
    if [ ${#PKGS[@]} -gt 0 ]; then
        LAYER_ROOTS+=("$layer")
    fi
done <<EOF
$LAYERS_OUT
EOF

run_layer() { # $1=layer, $2=simulate (1|0): sets LAYER_OUT and LAYER_RC
    local mode=()
    if [ "$2" = 1 ]; then
        mode=(-n)
    fi
    load_pkgs "$1"
    LAYER_RC=0
    LAYER_OUT="$(stow --dir "$1/stow" --target "$HOME" --no-folding --ignore='\.DS_Store' --restow \
        ${VERBOSE[@]+"${VERBOSE[@]}"} ${mode[@]+"${mode[@]}"} ${PASSTHRU[@]+"${PASSTHRU[@]}"} "${PKGS[@]}" 2>&1)" ||
        LAYER_RC=$?
}

# ---------------------------------------------------------------------------------------------------------------------
# Preflight: simulate every layer and classify what stow reports. Nothing is changed here.
#   BACKUP_TARGETS  $HOME-relative regular files / symlinks (e.g. links from an old checkout) that block a link
#   UNRESOLVED      everything else (a real directory in the way, stow errors): never auto-fixed
# Stow 2.4.1 wording (Stow.pm), reported as "  * <message>" after "WARNING! stowing <pkg> would cause conflicts:":
#   cannot stow <src> over existing target <T> since neither a link nor a directory and --adopt not specified
#   existing target is neither a link nor a directory: <T>
#   existing target is not owned by stow: <T>
# Fatal errors (e.g. "stow: ERROR: unstow_contents() called with non-directory path: ...") have no "  * " lines and a
# non-zero exit.
# ---------------------------------------------------------------------------------------------------------------------
PRE_LOGS=()
BACKUP_TARGETS=()
UNRESOLVED=()

conflict_target() { # print the $HOME-relative target named by a backup-able conflict message $1, else return 1
    local target
    target="$(printf '%s\n' "$1" | sed -n \
        -e 's/^cannot stow .* over existing target \(.*\) since neither a link nor a directory and --adopt not specified$/\1/p' \
        -e 's/^existing target is neither a link nor a directory: \(.*\)$/\1/p' \
        -e 's/^existing target is not owned by stow: \(.*\)$/\1/p')"
    if [ -z "$target" ]; then
        return 1
    fi
    printf '%s\n' "$target"
}

preflight() {
    local layer msgs msg target src
    PRE_LOGS=()
    BACKUP_TARGETS=()
    UNRESOLVED=()
    for layer in "${LAYER_ROOTS[@]}"; do
        run_layer "$layer" 1
        PRE_LOGS+=("$LAYER_OUT")
        msgs="$(printf '%s\n' "$LAYER_OUT" | sed -n 's/^  \* //p')"
        if [ -z "$msgs" ]; then
            if [ "$LAYER_RC" -ne 0 ]; then
                UNRESOLVED+=("stow failed (exit $LAYER_RC) for $layer:"$'\n'"$LAYER_OUT")
            fi
            continue
        fi
        while IFS= read -r msg; do
            if target="$(conflict_target "$msg")"; then
                src="$HOME/$target"
                if [ -L "$src" ] || { [ -e "$src" ] && [ ! -d "$src" ]; }; then
                    BACKUP_TARGETS+=("$target")
                    continue
                fi
            fi
            UNRESOLVED+=("$msg")
        done <<EOF
$msgs
EOF
    done
}

report_unresolved() {
    local item
    echo "stow: cannot link; these conflicts need manual attention (nothing was changed):" >&2
    for item in "${UNRESOLVED[@]}"; do
        printf '  %s\n' "$item" >&2
    done
}

summarize() { # $1=log, $2=dry (1|0)
    if [ "$SHOW_SUMMARY" = 1 ]; then
        printf '%s' "$1" | awk -v dry="$2" -f "$SUMMARIZER"
    fi
}

show_raw() { # $1=log
    if [ "$SHOW_RAW" = 1 ]; then
        printf '%s' "$1" | grep -v '^/' >&2 || true
    fi
}

preflight
if [ ${#UNRESOLVED[@]} -gt 0 ]; then
    report_unresolved
    exit 1
fi
if [ ${#BACKUP_TARGETS[@]} -gt 0 ] && [ "$BACKUP_CONFLICTS" = 0 ]; then
    echo "stow: these existing files block linking (nothing was changed):" >&2
    for target in "${BACKUP_TARGETS[@]}"; do
        printf '  ~/%s\n' "$target" >&2
    done
    echo "stow: re-run with --backup-conflicts to move them to ~/.dotfiles-backup/ first" >&2
    exit 1
fi

BACKUP_DIR="$HOME/.dotfiles-backup/$(date +%Y%m%d-%H%M%S)"

# ---------------------------------------------------------------------------------------------------------------------
# Dry run: report what would happen, then stop
# ---------------------------------------------------------------------------------------------------------------------
if [ "$DRY_RUN" = 1 ]; then
    for log in ${PRE_LOGS[@]+"${PRE_LOGS[@]}"}; do
        show_raw "$log"$'\n'
    done
    if [ ${#BACKUP_TARGETS[@]} -gt 0 ]; then
        # Stow reports no link plan while conflicts exist, so no summary is printed for this case
        for target in "${BACKUP_TARGETS[@]}"; do
            echo "stow: would back up existing $target -> $BACKUP_DIR/$target"
        done
        echo "stow: simulated ${SEL_NAMES[*]} (dry-run; ${#BACKUP_TARGETS[@]} conflicting file(s) would be backed up first, then linked)"
    else
        ALL_PRE=""
        for log in ${PRE_LOGS[@]+"${PRE_LOGS[@]}"}; do
            ALL_PRE+="$log"$'\n'
        done
        summarize "$ALL_PRE" 1
        echo "stow: simulated ${SEL_NAMES[*]} (dry-run, no changes written)"
    fi
    exit 0
fi

# ---------------------------------------------------------------------------------------------------------------------
# Backup, then re-verify every layer before linking anything
# ---------------------------------------------------------------------------------------------------------------------
if [ ${#BACKUP_TARGETS[@]} -gt 0 ]; then
    for target in "${BACKUP_TARGETS[@]}"; do
        mkdir -p "$BACKUP_DIR/$(dirname "$target")"
        mv "$HOME/$target" "$BACKUP_DIR/$target" || die "could not back up ~/$target (moved files so far are in $BACKUP_DIR)"
        echo "stow: backed up existing $target -> $BACKUP_DIR/$target"
    done
    preflight
    if [ ${#UNRESOLVED[@]} -gt 0 ] || [ ${#BACKUP_TARGETS[@]} -gt 0 ]; then
        for log in ${PRE_LOGS[@]+"${PRE_LOGS[@]}"}; do
            printf '%s\n' "$log" >&2
        done
        echo "stow: re-verification failed after backing up; nothing was linked" >&2
        echo "stow: the moved files are in $BACKUP_DIR (move them back to restore)" >&2
        exit 1
    fi
fi

# ---------------------------------------------------------------------------------------------------------------------
# Apply: stow every layer for real
# ---------------------------------------------------------------------------------------------------------------------
STOW_LOG=""
for layer in "${LAYER_ROOTS[@]}"; do
    run_layer "$layer" 0
    STOW_LOG+="$LAYER_OUT"$'\n'
    if [ "$LAYER_RC" -ne 0 ]; then
        printf '%s' "$STOW_LOG" >&2
        echo "stow: FAILED (exit $LAYER_RC) for $layer" >&2
        exit "$LAYER_RC"
    fi
done

show_raw "$STOW_LOG"
summarize "$STOW_LOG" 0
echo "stow: applied ${SEL_NAMES[*]}"
```

Run: `chmod +x stow.sh`

Notes for the implementer: `PASSTHRU` flags never set `DRY_RUN` (fixes a work-repo quirk where any pass-through flag
counted as a dry run). *Superseded by the final-review fixes: `stow.sh` now rejects every option outside its documented
set (`--adopt`, `-D`, `--dir`, `--target`, ... never reach stow), so `PASSTHRU` is gone.* The conflict regexes target GNU Stow 2.4.1's wording (`Stow.pm`); re-probe them if Stow is
upgraded. If shellcheck flags the `${!PKG_NAMES[@]}` expansions, keep the logic and add a targeted
`# shellcheck disable=` with a reason comment rather than restructuring. The tests run `stow.sh` under every bash from
`tests/conftest.py` (`/bin/bash` 3.2 and the PATH bash).

- [ ] **Step 5: Run tests to verify they pass**

Run: `scripts/hooks/uv-public.sh run --group test pytest tests/unit/test_stow_sh.py tests/unit/test_stow_summary.py` →
PASS.
Run: `/bin/bash stow.sh --list` (macOS bash 3.2) in this repo → exit 0 (no packages yet; prints nothing).
Run: `prek run --files stow.sh scripts/utility/summarize_stow.awk tests/unit/test_stow_sh.py tests/unit/test_stow_summary.py`
→ pass.

- [ ] **Step 6: Commit**

```bash
git add stow.sh scripts/utility/summarize_stow.awk tests/conftest.py tests/unit/test_lib_sh.py tests/unit/test_stow_sh.py tests/unit/test_stow_summary.py
git commit -m "feat(stow): layered stow driver with single-ownership check"
```

---

### Task 4: Layered bootstrap driver (`bootstrap/bootstrap.sh`)

**Files:**

- Create: `bootstrap/bootstrap.sh` (ported from `~/dotfiles/bootstrap/bootstrap.sh`, then modified)
- Create: `bootstrap/00-preflight.sh` (copy verbatim from `~/dotfiles/bootstrap/00-preflight.sh`)
- Create: `bootstrap/README.md`
- Test: `tests/unit/test_bootstrap_driver.py`

**Interfaces:**

- Consumes: `bootstrap/lib.sh` (`dotfiles_layers`, `log`, `warn`, `die`, `fmt_duration`, `prime_sudo`).
- Produces: `bootstrap.sh [--dry-run] [--list] [--only STAGE] [--from STAGE] [--resume] [--verify] [--no-log]`
  - Stages: every `<layer>/bootstrap/[0-9][0-9]-*.sh`, merged across layers, sorted by name; a two-digit number used
    twice anywhere is fatal (`die "stage number NN is used twice: <path> and <path>"`)
  - `--list`: one line per stage: the stage name, plus `  (<layer root>)` when the stage comes from an overlay
  - Each stage runs as `"$BASH" <path>` (the driver's own interpreter) with `BOOTSTRAP_DRY_RUN`, `DOTFILES_REPO` (base root) and `DOTFILES_LAYER` (the
    stage's own layer root) exported
  - `--verify`: after all stages succeed, runs `scripts/hooks/uv-public.sh run python run.py doctor` from the repo root
  - State/log dir unchanged: `${BOOTSTRAP_LOG_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/dotfiles-bootstrap}`

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_bootstrap_driver.py`:

```python
"""
Unit tests for bootstrap/bootstrap.sh (layered stage driver)
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DRIVER    = REPO_ROOT / 'bootstrap' / 'bootstrap.sh'


@pytest.fixture
def overlay(tmp_path: Path) -> Path:
    """
    An overlay with one passing and one failing stage
    """
    root = tmp_path / 'overlay'
    stages = root / 'bootstrap'
    stages.mkdir(parents=True)
    (stages / '98-selftest-ok.sh').write_text(
        '#!/usr/bin/env bash\nprintf "%s|%s" "$DOTFILES_REPO" "$DOTFILES_LAYER" > "$PROBE_FILE"\n',
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
        **os.environ,
        'HOME': str(tmp_path / 'home'),
        'DOTFILES_OVERLAYS_FILE': str(registry),
        'BOOTSTRAP_LOG_DIR': str(tmp_path / 'state'),
        'PROBE_FILE': str(tmp_path / 'probe'),
    }


def _drive(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    """
    Run the bootstrap driver
    """
    return subprocess.run(['bash', str(DRIVER), *args], capture_output=True, text=True, check=False, env=env)


class TestStageDiscovery:
    """
    Tests for cross-layer stage discovery
    """
    def test_list_merges_layers_in_order(self, env: dict[str, str], overlay: Path) -> None:
        """
        Test that --list shows base stages first by number, then overlay stages tagged with their layer
        """
        result = _drive(env, '--list')
        assert result.returncode == 0, result.stderr
        lines = result.stdout.splitlines()
        assert lines[0] == '00-preflight'
        assert lines[-2:] == [f'98-selftest-ok  ({overlay.resolve()})', f'99-selftest-fail  ({overlay.resolve()})']

    def test_duplicate_number_across_layers_fails(self, env: dict[str, str], overlay: Path) -> None:
        """
        Test that a stage number reused by an overlay is fatal
        """
        (overlay / 'bootstrap' / '00-overlay-dup.sh').write_text('#!/usr/bin/env bash\n', encoding='utf-8')
        result = _drive(env, '--list')
        assert result.returncode != 0
        assert 'stage number 00 is used twice' in result.stderr


class TestStageExecution:
    """
    Tests for running stages
    """
    def test_overlay_stage_gets_layer_env(self, env: dict[str, str], overlay: Path, tmp_path: Path) -> None:
        """
        Test that a stage sees DOTFILES_REPO (base) and DOTFILES_LAYER (its own layer)
        """
        result = _drive(env, '--dry-run', '--no-log', '--only', '98-selftest-ok')
        assert result.returncode == 0, result.stderr
        repo, layer = (tmp_path / 'probe').read_text(encoding='utf-8').split('|')
        assert Path(repo).resolve() == REPO_ROOT
        assert Path(layer).resolve() == overlay.resolve()

    def test_failing_stage_reports_and_hints_resume(self, env: dict[str, str]) -> None:
        """
        Test that a failing stage exits non-zero with a summary and a resume hint
        """
        result = _drive(env, '--dry-run', '--no-log', '--only', '99-selftest-fail')
        output = result.stdout + result.stderr
        assert result.returncode != 0
        assert '99-selftest-fail' in output
        assert '--from 99-selftest-fail' in output

    def test_unknown_only_fails(self, env: dict[str, str]) -> None:
        """
        Test that --only with an unknown stage is rejected
        """
        assert _drive(env, '--only', '42-nope').returncode != 0

    def test_resume_conflicts_with_only(self, env: dict[str, str]) -> None:
        """
        Test that --resume cannot be combined with --only
        """
        assert _drive(env, '--resume', '--only', '98-selftest-ok').returncode != 0

    def test_resume_from_recorded_stage(self, env: dict[str, str]) -> None:
        """
        Test that --resume starts after the recorded last-completed stage
        """
        state = Path(env['BOOTSTRAP_LOG_DIR'])
        state.mkdir(parents=True)
        (state / 'last-completed-stage').write_text('98-selftest-ok\n', encoding='utf-8')
        result = _drive(env, '--dry-run', '--no-log', '--resume')
        assert 'resuming from stage: 99-selftest-fail' in result.stdout + result.stderr

    def test_help_mentions_flags(self, env: dict[str, str]) -> None:
        """
        Test that --help documents the driver flags
        """
        result = _drive(env, '--help')
        for flag in ('--verify', '--no-log', '--resume', '--only', '--from'):
            assert flag in result.stdout + result.stderr
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `scripts/hooks/uv-public.sh run --group test pytest tests/unit/test_bootstrap_driver.py` → FAIL (driver missing).

- [ ] **Step 3: Port the driver and replace stage discovery/execution**

Copy `~/dotfiles/bootstrap/bootstrap.sh` → `bootstrap/bootstrap.sh` and `~/dotfiles/bootstrap/00-preflight.sh` →
`bootstrap/00-preflight.sh`. Then edit `bootstrap.sh`:

1. Replace the single-directory discovery block (`STAGES=()` … `done < <(cd "$HERE" && ls [0-9][0-9]-*.sh … | sort)`)
   with:

```bash
# Discover NN-*.sh stages in every layer (base first, then overlays). Two-digit numbers must be unique across all
# layers so the merged order is unambiguous.
STAGE_NAMES=()
STAGE_PATHS=()
LAYERS_OUT="$(dotfiles_layers)" || exit 1

list_stages() {
    local layer f
    while IFS= read -r layer; do
        for f in "$layer"/bootstrap/[0-9][0-9]-*.sh; do
            if [ -f "$f" ]; then
                printf '%s\t%s\n' "$(basename "$f" .sh)" "$f"
            fi
        done
    done <<EOF
$LAYERS_OUT
EOF
}

prev_num=""
while IFS=$'\t' read -r name path; do
    if [ -z "$name" ]; then
        continue
    fi
    num="${name%%-*}"
    if [ "$num" = "$prev_num" ]; then
        die "stage number $num is used twice: ${STAGE_PATHS[${#STAGE_PATHS[@]} - 1]} and $path"
    fi
    prev_num="$num"
    STAGE_NAMES+=("$name")
    STAGE_PATHS+=("$path")
done < <(list_stages | LC_ALL=C sort)
```

2. Rewrite `stage_exists` and `next_stage_after` to iterate `STAGE_NAMES` (they previously iterated `STAGES` and
   stripped `.sh`; names in `STAGE_NAMES` already have no suffix).

3. Replace the `--list` output with:

```bash
for i in ${STAGE_NAMES[@]+"${!STAGE_NAMES[@]}"}; do
    layer="${STAGE_PATHS[$i]%/bootstrap/*}"
    if [ "$layer" = "$REPO" ]; then
        printf '%s\n' "${STAGE_NAMES[$i]}"
    else
        printf '%s  (%s)\n' "${STAGE_NAMES[$i]}" "$layer"
    fi
done
```

(`REPO` must be the physical repo root — set it from `DOTFILES_REPO` after sourcing lib.sh: `REPO="$DOTFILES_REPO"`.)

4. In the stage loop, iterate indexes instead of files and execute by path:

```bash
for i in ${STAGE_NAMES[@]+"${!STAGE_NAMES[@]}"}; do
    name="${STAGE_NAMES[$i]}"
    path="${STAGE_PATHS[$i]}"
    # (keep the existing --only / --from filtering, logging, timing, and result bookkeeping unchanged)
    BOOTSTRAP_DRY_RUN="${BOOTSTRAP_DRY_RUN:-0}" DOTFILES_REPO="$REPO" DOTFILES_LAYER="${path%/bootstrap/*}" \
        bash "$path"
    rc=$?
    # ...
done
```

5. In the `--verify` block, replace the doctor invocation with
   `(cd "$REPO" && "$REPO/scripts/hooks/uv-public.sh" run python run.py doctor)` and the `have uv` guard message
   accordingly.

6. Remove anything in the copied file that names employer-specific stages, hosts, or tools (help text examples, comments).
   The private-pattern leak guard must pass on the file.

Write `bootstrap/README.md` (breadcrumb `[Project Root](../README.md) > **Bootstrap**`): purpose, the flags table, the
overlay contract (stages merged by number, `env.sh`, manifest fragments via `manifest_files`), and a stage table whose
first column is the stage id — one row `| 00-preflight | macOS + Command Line Tools present | base |` for now.

- [ ] **Step 4: Run tests to verify they pass**

Run: `scripts/hooks/uv-public.sh run --group test pytest tests/unit/test_bootstrap_driver.py tests/unit/test_lib_sh.py`
→ PASS.
Run: `/bin/bash bootstrap/bootstrap.sh --list` → `00-preflight`.
Run: `/bin/bash bootstrap/bootstrap.sh --dry-run --no-log` → runs `00-preflight` in dry-run, prints the summary, exit 0.
Run: `prek run --files bootstrap/*.sh bootstrap/README.md tests/unit/test_bootstrap_driver.py` → pass.

- [ ] **Step 5: Commit**

```bash
git add bootstrap/bootstrap.sh bootstrap/00-preflight.sh bootstrap/README.md tests/unit/test_bootstrap_driver.py
git commit -m "feat(bootstrap): layered stage driver merging stages across overlays"
```

---

### Task 5: Settings renderer (`scripts/dotfiles/render.py`)

**Files:**

- Create: `scripts/dotfiles/render.py`
- Create: `scripts/dotfiles/README.md`
- Test: `tests/unit/test_render.py`

**Interfaces:**

- Consumes: `bootstrap/lib.sh` `dotfiles_layers` (via `bash -c`).
- Produces (module `render`, loaded by tests from its path):
  - `TARGETS: dict[str, str]` — `{'claude': '~/.claude/settings.json', 'vscode': '~/Library/Application Support/Code/User/settings.json'}`
  - `UNMANAGED_KEY = '$unmanaged'`
  - `class RenderError(Exception)`
  - `merge(base: object, overlay: object) -> object`
  - `layers(repo: Path) -> list[Path]` — lib.sh output is routed to stderr; non-absolute lines are rejected
  - `prepare(target: str, roots: Sequence[Path]) -> Prepared | None` — find + compose one target's fragments
  - `atomic_write(path: Path, text: str, default_mode: int, *, preserve_mode: bool = True) -> None` — temp file +
    `Path.replace`; the replaced file's mode is preserved unless `preserve_mode=False` (state files are always 0600)
  - `compose(fragments: Sequence[Path]) -> tuple[dict[str, object], list[str]]` — merged managed settings + the
    unmanaged top-level keys
  - `dumps(data: object) -> str` — deterministic JSON text (sorted keys, 2-space indent, trailing newline)
  - `main(argv: Sequence[str] | None = None) -> int`
  - CLI: `render.py [TARGET…] [--diff | --check] [--force] [--repo PATH] [-v]`; exit 0 ok / in sync, 1 drift refused
    or out of sync, 2 configuration or I/O error (bad fragment, unknown target, missing overlay, unreadable/unwritable
    path, bash unavailable)
- Semantics (binding): objects deep-merge; arrays concatenate with order-preserving de-duplication (by canonical JSON);
  scalars — later layer wins; `null` in a later layer deletes the key; a fragment's top-level `"$unmanaged"` (list of
  top-level key names, merged across layers) marks keys owned by the app/installer: they are never written from
  fragments, are preserved from the live file on render, and are ignored by drift/check comparison. State: the last
  managed render is stored as `${XDG_STATE_HOME:-~/.local/state}/dotfiles/render/<id>.json`; drift = live managed
  content differs from both the stored last render and the new render. `--force` backs the live file up to
  `~/.dotfiles-backup/<YYYYmmdd-HHMMSS>/<path relative to HOME>` first. A symlink at the target is replaced by a real
  file (the symlink's target is never written; its former target is reported, and its target's mode is inherited).
  Writes (target and state) are atomic via a same-directory temp file + replace, preserving an existing file's mode.
  A missing/corrupt/empty/non-object state file is treated as absent with a warning. All requested targets are
  composed and validated before any is written (a bad fragment exits 2 with nothing written). `--force` backs up only
  when drift exists; backup dirs are 0700 and files 0600. A key set by a fragment but listed in `$unmanaged` is
  dropped with a warning. A live file that is not valid JSON / not a JSON object is refused with a matching message.

(The spec named a SHA-256 state file; storing the last managed render itself is a superset that makes the drift diff
exact.)

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_render.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `scripts/hooks/uv-public.sh run --group test pytest tests/unit/test_render.py` → FAIL (module missing).

- [ ] **Step 3: Implement the renderer**

`scripts/dotfiles/render.py`:

```python
#!/usr/bin/env python3
"""
Render JSON settings files from per-layer fragments (base repo first, then registered overlays).

Each layer may provide ``render/<target>.json``. Fragments deep-merge in layer order into a real file at the target's
path. A drift guard refuses to overwrite edits made in the app since the last render.
"""
# /// script
# requires-python = ">= 3.9"
# dependencies = []
# ///
from __future__ import annotations

import argparse
import contextlib
import difflib
import functools
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

# ==========================
# Constants/defaults/globals
# ==========================


VERBOSE:       bool = False
UNMANAGED_KEY: str  = '$unmanaged'
DEFAULT_REPO:  Path = Path(__file__).resolve().parents[2]

DEFAULT_FILE_MODE:  int = 0o644
DEFAULT_STATE_MODE: int = 0o600
BACKUP_FILE_MODE:   int = 0o600
BACKUP_DIR_MODE:    int = 0o700

ANSI_ESCAPE = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')

TARGETS: dict[str, str] = {
    'claude': '~/.claude/settings.json',
    'vscode': '~/Library/Application Support/Code/User/settings.json',
}


# ===============
# Types/protocols
# ===============


class RenderError(Exception):
    """
    Configuration error: bad fragment, bad layer registry, or unknown target.
    """


class Prepared(NamedTuple):
    """
    A target whose fragments have been found and composed successfully.
    """
    target:    str
    managed:   dict[str, object]
    unmanaged: list[str]


# ==================
# Formatting/logging
# ==================


def info(message: str) -> None:
    """
    Print an informational line to stdout.

    :param message: text to print
    """
    print(f'render: {message}')


def warn(message: str) -> None:
    """
    Print a warning line to stderr.

    :param message: text to print
    """
    print(f'render: WARNING: {message}', file=sys.stderr)


def error(message: str) -> None:
    """
    Print an error line to stderr.

    :param message: text to print
    """
    print(f'render: ERROR: {message}', file=sys.stderr)


# =================
# Core script logic
# =================


def canonical(value: object) -> str:
    """
    Canonical JSON text used for equality and de-duplication.

    :param value: JSON-compatible value
    :return: compact, key-sorted JSON text
    """
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def dumps(data: object) -> str:
    """
    Deterministic output format for rendered files and state.

    :param data: JSON-compatible value
    :return: key-sorted, 2-space-indented JSON text with a trailing newline
    """
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + '\n'


def _drop_nulls(value: object) -> object:
    """
    Remove null-valued keys recursively (a null in a later layer means "delete").

    :param value: JSON-compatible value
    :return: value without null-valued object keys
    """
    if isinstance(value, dict):
        return {k: _drop_nulls(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_drop_nulls(v) for v in value]
    return value


def merge(base: object, overlay: object) -> object:
    """
    Merge a later layer's value over an earlier one.

    Objects deep-merge, arrays concatenate with order-preserving de-duplication, scalars are replaced, and a null
    object value deletes the key.

    :param base: earlier layer's value
    :param overlay: later layer's value
    :return: merged value
    """
    if isinstance(base, dict) and isinstance(overlay, dict):
        merged = dict(base)
        for key, value in overlay.items():
            if value is None:
                merged.pop(key, None)
            elif key in merged:
                merged[key] = merge(merged[key], value)
            else:
                merged[key] = _drop_nulls(value)
        return merged
    if isinstance(base, list) and isinstance(overlay, list):
        combined = list(base)
        seen     = {canonical(item) for item in combined}
        for item in overlay:
            cleaned = _drop_nulls(item)
            key     = canonical(cleaned)
            if key not in seen:
                combined.append(cleaned)
                seen.add(key)
        return combined
    return _drop_nulls(overlay)


def layers(repo: Path) -> list[Path]:
    """
    Resolve layer roots via ``bootstrap/lib.sh`` so shell and Python agree on one registry.

    Anything lib.sh or a layer's ``env.sh`` prints while being sourced is routed to stderr so it cannot be mistaken for
    a layer root.

    :param repo: base repository root
    :raises RenderError: if bash cannot run, the registry names a missing overlay, lib.sh fails, or a non-absolute
        layer path is produced
    :return: layer roots, base first
    """
    try:
        result = subprocess.run(
            ['bash', '-c', 'source "$1/bootstrap/lib.sh" >&2 && dotfiles_layers', '_', str(repo)],
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, 'DOTFILES_REPO': str(repo)},
        )
    except OSError as exc:
        raise RenderError(f'cannot run bash to resolve layers: {exc!s}') from exc
    if result.returncode != 0:
        raise RenderError(ANSI_ESCAPE.sub('', result.stderr).strip() or 'dotfiles_layers failed')
    roots = []
    for line in result.stdout.splitlines():
        if not line:
            continue
        root = Path(line)
        if not root.is_absolute():
            raise RenderError(f'dotfiles_layers produced a non-absolute layer path: {ANSI_ESCAPE.sub("", line)!r}')
        roots.append(root)
    return roots


def compose(fragments: Sequence[Path]) -> tuple[dict[str, object], list[str]]:
    """
    Merge fragments in order and split out the unmanaged-key list.

    A key that a fragment sets but that is also listed as unmanaged is dropped from the managed settings (the app or
    installer owns it) with a warning.

    :param fragments: fragment files, base first
    :raises RenderError: on unreadable/invalid JSON, a non-object fragment, or a malformed ``$unmanaged``
    :return: (managed settings, unmanaged top-level key names)
    """
    merged:    object    = {}
    unmanaged: list[str] = []
    for fragment in fragments:
        try:
            data = json.loads(fragment.read_text(encoding='utf-8'))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RenderError(f'{fragment}: {exc!s}') from exc
        if not isinstance(data, dict):
            raise RenderError(f'{fragment}: top level must be an object')
        keys = data.pop(UNMANAGED_KEY, [])
        if not isinstance(keys, list) or not all(isinstance(k, str) for k in keys):
            raise RenderError(f'{fragment}: {UNMANAGED_KEY} must be a list of key names')
        unmanaged.extend(k for k in keys if k not in unmanaged)
        merged = merge(merged, data)
    if not isinstance(merged, dict):
        raise RenderError('merged settings must be an object')
    overlap = [k for k in unmanaged if k in merged]
    if overlap:
        warn(f'fragment value(s) ignored for key(s) listed in {UNMANAGED_KEY}: {", ".join(overlap)}')
    return {k: v for k, v in merged.items() if k not in unmanaged}, unmanaged


def prepare(target: str, roots: Sequence[Path]) -> Prepared | None:
    """
    Find and compose the fragments of one target.

    :param target: target id from :data:`TARGETS`
    :param roots: layer roots, base first
    :raises RenderError: on invalid fragments
    :return: the composed target, or ``None`` if no layer provides a fragment
    """
    fragments = [root / 'render' / f'{target}.json' for root in roots]
    fragments = [f for f in fragments if f.is_file()]
    if not fragments:
        if VERBOSE:
            info(f'{target}: no fragments in any layer; skipped')
        return None
    managed, unmanaged = compose(fragments)
    return Prepared(target, managed, unmanaged)


def state_path(target: str) -> Path:
    """
    Where the last managed render of a target is stored.

    :param target: target id
    :return: state file path
    """
    state_home = os.environ.get('XDG_STATE_HOME') or str(Path.home() / '.local' / 'state')
    return Path(state_home) / 'dotfiles' / 'render' / f'{target}.json'


def read_state(state: Path) -> dict[str, object] | None:
    """
    Load the last managed render, treating a missing or unusable state file as absent.

    :param state: state file path
    :return: the stored managed settings, or ``None`` if absent or unusable (a warning is printed for the latter)
    """
    if not state.is_file():
        return None
    try:
        data = json.loads(state.read_text(encoding='utf-8'))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        warn(f'ignoring unusable state file {state} ({exc!s}); treating it as absent')
        return None
    if not isinstance(data, dict):
        warn(f'ignoring unusable state file {state} (not a JSON object); treating it as absent')
        return None
    return data


def atomic_write(path: Path, text: str, default_mode: int, *, preserve_mode: bool = True) -> None:
    """
    Write text to path through a temp file in the same directory and ``os.replace``.

    With ``preserve_mode`` an existing file's mode is kept; for a symlink the mode of its target is used. A symlink
    itself is replaced, never written through.

    :param path: destination path
    :param text: file content
    :param default_mode: mode used when no existing file supplies one (or when ``preserve_mode`` is false)
    :param preserve_mode: copy the mode of the file being replaced; disable for files this script owns outright
    """
    mode = default_mode
    if preserve_mode:
        with contextlib.suppress(OSError):
            mode = stat.S_IMODE(path.stat().st_mode)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f'.{path.name}.', suffix='.tmp')
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        tmp.chmod(mode)
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def _diff(old: str, new: str, old_label: str, new_label: str) -> str:
    """
    Unified diff of two texts.

    :param old: original text
    :param new: new text
    :param old_label: label for the original
    :param new_label: label for the new text
    :return: diff text (empty when equal)
    """
    return ''.join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), old_label, new_label))


def _backup(dest: Path) -> Path:
    """
    Copy the live file's content to ~/.dotfiles-backup/<timestamp>/<path relative to HOME>.

    Directories are created 0700 and the backup file 0600.

    :param dest: live target path
    :return: backup path
    """
    home = Path.home()
    try:
        relative = dest.relative_to(home)
    except ValueError:
        relative = Path(dest.name)
    backup = home / '.dotfiles-backup' / time.strftime('%Y%m%d-%H%M%S') / relative
    current = home
    for part in backup.parent.relative_to(home).parts:
        current = current / part
        current.mkdir(mode=BACKUP_DIR_MODE, exist_ok=True)
    fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, BACKUP_FILE_MODE)
    with os.fdopen(fd, 'wb') as handle:
        handle.write(dest.read_bytes())
    backup.chmod(BACKUP_FILE_MODE)
    return backup


def render_target(prepared: Prepared, *, mode: str, force: bool) -> int:
    """
    Render, check, or diff one composed target.

    :param prepared: composed target
    :param mode: ``'render'``, ``'check'``, or ``'diff'``
    :param force: overwrite despite drift (after backing up)
    :raises OSError: on I/O failures reading or writing the target, its state, or backups
    :return: 0 ok / in sync, 1 drift refused / out of sync
    """
    target, managed, unmanaged = prepared
    new_text = dumps(managed)
    dest     = Path(TARGETS[target]).expanduser()
    state    = state_path(target)
    last     = read_state(state)

    live:         dict[str, object] | None = None
    live_problem: str | None               = None
    if dest.exists():
        try:
            parsed = json.loads(dest.read_text(encoding='utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError):
            live_problem = 'is not valid JSON'
        else:
            if isinstance(parsed, dict):
                live = parsed
            else:
                live_problem = 'is not a JSON object'
    live_managed = {k: v for k, v in live.items() if k not in unmanaged} if live is not None else None
    live_managed_text = dumps(live_managed) if live_managed is not None else None

    if mode == 'diff':
        print(_diff(live_managed_text or '', new_text, f'{dest} (live)', f'{dest} (rendered)'), end='')
        return 0
    if mode == 'check':
        if live_managed_text == new_text:
            return 0
        error(f'{target}: {dest} is not in sync with its fragments (run: run.py render)')
        return 1

    current = live_managed_text == new_text
    in_sync = False
    if last is not None and live_managed is not None:
        in_sync = canonical(last) == canonical(live_managed)
    drifted = dest.exists() and not current and not in_sync
    if drifted and not force:
        reason = live_problem or 'was edited since the last render'
        error(f'{target}: {dest} {reason}; move the change into a render fragment, or re-run with --force')
        if live_managed_text is not None:
            old_text = dumps(last) if last is not None else ''
            print(_diff(old_text, live_managed_text, 'last render', f'{dest} (live)'), end='', file=sys.stderr)
        return 1

    output = dict(managed)
    if live is not None:
        output.update({k: live[k] for k in unmanaged if k in live})
    output_text = dumps(output)

    if dest.exists() and force and drifted:
        info(f'{target}: backed up live file to {_backup(dest)}')
    if dest.is_symlink():
        info(f'{target}: replacing symlink {dest} -> {dest.readlink()} with a regular file')
    if dest.is_symlink() or not dest.exists() or dest.read_text(encoding='utf-8') != output_text:
        atomic_write(dest, output_text, DEFAULT_FILE_MODE)
        info(f'{target}: rendered {dest}')
    elif VERBOSE:
        info(f'{target}: already current')
    atomic_write(state, new_text, DEFAULT_STATE_MODE, preserve_mode=False)
    return 0


# ======================
# Command-line arguments
# ======================


class Args(argparse.Namespace):
    """
    :class:`argparse.Namespace` annotated with args supported by this script.
    """
    targets: Sequence[str]
    diff:    bool
    check:   bool
    force:   bool
    repo:    str
    verbose: bool


def parse_args(argv: Sequence[str] | None = None) -> Args:
    """
    Parse command-line arguments.

    :param argv: argument list (default: ``sys.argv[1:]``)
    :return: parsed arguments
    """
    global VERBOSE

    parser = argparse.ArgumentParser(
        description='Render JSON settings files from per-layer fragments',
        formatter_class=functools.partial(argparse.RawTextHelpFormatter, max_help_position=50),
    )
    parser.add_argument('targets', nargs='*', help=f'Targets to render (default: all of {", ".join(TARGETS)})')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--diff', action='store_true', help='Show live-vs-rendered differences; write nothing')
    mode.add_argument('--check', action='store_true', help='Exit 1 if a target is out of sync; write nothing')
    parser.add_argument('--force', action='store_true', help='Overwrite in-app edits (live file is backed up first)')
    parser.add_argument('--repo', default=str(DEFAULT_REPO), help='Base repository root (default: this repo)')
    parser.add_argument('-v', '--verbose', action='store_true', help='Report skipped and already-current targets')
    args    = parser.parse_args(argv, namespace=Args())
    VERBOSE = args.verbose
    return args


def main(argv: Sequence[str] | None = None) -> int:
    """
    Render, check, or diff settings targets.

    All requested targets are composed and validated before any is written, so a bad fragment never leaves a partial
    render behind.

    :param argv: command-line arguments (default: ``sys.argv[1:]``)
    :return: 0 ok, 1 drift refused / out of sync, 2 configuration or I/O error
    """
    args    = parse_args(argv)
    mode    = 'diff' if args.diff else 'check' if args.check else 'render'
    targets = list(args.targets) or list(TARGETS)
    unknown = [t for t in targets if t not in TARGETS]
    if unknown:
        error(f'unknown target(s): {", ".join(unknown)} (known: {", ".join(TARGETS)})')
        return 2

    try:
        roots    = layers(Path(args.repo))
        composed = [p for p in (prepare(target, roots) for target in targets) if p is not None]
    except RenderError as exc:
        error(str(exc))
        return 2

    retval = 0
    try:
        for prepared in composed:
            retval = max(retval, render_target(prepared, mode=mode, force=args.force))
    except OSError as exc:
        error(str(exc))
        return 2
    return retval


if __name__ == '__main__':
    sys.exit(main())
```

Run: `chmod +x scripts/dotfiles/render.py`

Write `scripts/dotfiles/README.md` (breadcrumb `[Project Root](../../README.md) > **Dotfiles Tools**`): what
`render.py` does, the targets table, merge semantics table, `$unmanaged`, drift guard, flags, exit codes, and one worked
example fragment pair (base + overlay → result).

- [ ] **Step 4: Run tests to verify they pass**

Run: `scripts/hooks/uv-public.sh run --group test pytest tests/unit/test_render.py` → PASS.
Run: `scripts/hooks/uv-public.sh run ruff check scripts/dotfiles tests/unit/test_render.py && scripts/hooks/uv-public.sh run mypy scripts/dotfiles/render.py`
→ clean.

- [ ] **Step 5: Commit**

```bash
git add scripts/dotfiles/render.py scripts/dotfiles/README.md tests/unit/test_render.py
git commit -m "feat(render): layered JSON settings renderer with drift guard"
```

---

### Task 6: `run.py` commands (`bootstrap`, `stow`, `render`, `doctor`, `test`)

**Files:**

- Modify: `run.py` (add a new command section after the Codebase commands; follow the existing `@command` pattern,
  e.g. `cmd_pre`)
- Modify: `Makefile` (regenerate via `run.py makefile`), `docs/RUN_PY_REFERENCE.md`, `.ctx/BUILD.md`
- Test: `tests/unit/test_run_doctor.py`

**Interfaces:**

- Consumes: `stow.sh` (`-n`, `--backup-conflicts`, `--list`), `bootstrap/bootstrap.sh` flags, `render.py`
  (`--check`), `bootstrap/lib.sh` `dotfiles_layers`.
- Produces (importable from `run` for tests):
  - `cmd_bootstrap(args)` — forwards `--dry-run --list --only --from --resume --verify --no-log`
  - `cmd_stow(args)` — forwards `-n/--simulate`, `--backup-conflicts`, `-v`, packages
  - `cmd_render(args)` — forwards targets, `--diff`, `--check`, `--force`, `-v`
  - `cmd_test(args)` — `scripts/hooks/uv-public.sh run --group test pytest [paths…]`
  - `DoctorCheck` dataclass `(name: str, ok: bool, detail: str, fix: list[str] | None)`
  - `doctor_checks() -> list[DoctorCheck]` and the individual check functions `check_layers()`, `check_links()`,
    `check_render()`, `check_git_version()`, `check_tools()`
  - `cmd_doctor(args)` — prints one status line per check; `--fix` runs each failing check's `fix` command, then
    re-checks; exits 1 if anything still fails
- Group name: `Dotfiles`.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_run_doctor.py`:

```python
"""
Unit tests for run.py doctor checks
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import run  # noqa: E402


def _completed(returncode: int, stdout: str = '') -> subprocess.CompletedProcess[str]:
    """
    Build a fake CompletedProcess
    """
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr='')


class TestDoctorChecks:
    """
    Tests for individual doctor checks
    """
    def test_links_ok_when_stow_reports_no_changes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that a no-op stow simulation means links are current
        """
        monkeypatch.setattr(run, '_capture', lambda cmd: _completed(0, 'stow: no changes (already current)\n'))
        assert run.check_links().ok

    def test_links_ok_with_no_packages(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that a repo with no packages yet is not reported as broken
        """
        monkeypatch.setattr(run, '_capture', lambda cmd: _completed(0, 'stow: no packages found\n'))
        assert run.check_links().ok

    def test_links_fail_when_stow_would_change(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that pending stow changes fail the check and offer a fix
        """
        monkeypatch.setattr(run, '_capture', lambda cmd: _completed(0, 'stow: 2 added, 0 updated, 0 removed\n'))
        check = run.check_links()
        assert not check.ok
        assert check.fix is not None

    def test_render_check_maps_exit_code(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that render --check exit 1 fails the check
        """
        monkeypatch.setattr(run, '_capture', lambda cmd: _completed(1))
        assert not run.check_render().ok

    @pytest.mark.parametrize(
        ('version_line', 'ok'),
        [
            ('git version 2.36.0', True),
            ('git version 2.47.1 (Vendor Git-154)', True),
            ('git version 2.35.9', False),
        ],
    )
    def test_git_version(self, monkeypatch: pytest.MonkeyPatch, version_line: str, ok: bool) -> None:
        """
        Test that git must support includeIf hasconfig (>= 2.36)
        """
        monkeypatch.setattr(run, '_capture', lambda cmd: _completed(0, version_line + '\n'))
        assert run.check_git_version().ok is ok

    def test_layers_fail_on_registry_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that a broken overlay registry fails the layers check
        """
        monkeypatch.setattr(run, '_capture', lambda cmd: _completed(1))
        assert not run.check_layers().ok

    def test_tools_reports_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that a missing required tool fails the tools check and is named
        """
        monkeypatch.setattr(run.shutil, 'which', lambda name: None if name == 'stow' else f'/usr/bin/{name}')
        check = run.check_tools()
        assert not check.ok
        assert 'stow' in check.detail
```

(The `version_line` cases avoid any vendor name; the second case mimics a vendor-suffixed `git --version` line.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `scripts/hooks/uv-public.sh run --group test pytest tests/unit/test_run_doctor.py` → FAIL (`AttributeError`).

- [ ] **Step 3: Implement the commands**

Add to `run.py` (imports: ensure `re`, `shutil`, `subprocess`, `dataclasses.dataclass` are imported, one per line, in
the existing import blocks; add path constants next to the existing ones):

```python
STOW_SCRIPT:      Path = DOTFILES_DIR / 'stow.sh'
BOOTSTRAP_SCRIPT: Path = DOTFILES_DIR / 'bootstrap' / 'bootstrap.sh'
RENDER_SCRIPT:    Path = DOTFILES_DIR / 'scripts' / 'dotfiles' / 'render.py'
UV_PUBLIC:        Path = DOTFILES_DIR / 'scripts' / 'hooks' / 'uv-public.sh'
REQUIRED_TOOLS:   tuple[str, ...] = ('brew', 'git', 'stow', 'uv', 'zsh')
MIN_GIT_VERSION:  tuple[int, int] = (2, 36)
```

```python
"""
Dotfiles commands

Thin wrappers over the layered engine (stow.sh, bootstrap/bootstrap.sh, scripts/dotfiles/render.py) plus a doctor
that checks the overlay registry, link state, render drift, git version, and required tools.
"""


@dataclass(frozen=True)
class DoctorCheck:
    """
    Result of one doctor check.

    :param name: short check name
    :param ok: whether the check passed
    :param detail: one-line explanation
    :param fix: command that repairs the problem, if one exists
    """
    name:   str
    ok:     bool
    detail: str
    fix:    list[str] | None = None


def _capture(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    """
    Run a command quietly and capture its output (patched in tests).

    :param cmd: command and arguments
    :return: completed process with text stdout/stderr
    """
    return subprocess.run(cmd, capture_output=True, text=True, check=False, cwd=DOTFILES_DIR)


def check_layers() -> DoctorCheck:
    """
    Check that every registered overlay exists.
    """
    result = _capture(['bash', '-c', 'source bootstrap/lib.sh && dotfiles_layers'])
    if result.returncode != 0:
        return DoctorCheck('layers', False, (result.stderr or 'overlay registry error').strip())
    count = len([line for line in result.stdout.splitlines() if line])
    return DoctorCheck('layers', True, f'{count} layer(s): base + {count - 1} overlay(s)')


def check_links() -> DoctorCheck:
    """
    Check that stowing would change nothing.
    """
    result = _capture(['bash', str(STOW_SCRIPT), '-n'])
    if result.returncode == 0 and ('no changes' in result.stdout or 'no packages found' in result.stdout):
        return DoctorCheck('links', True, 'all packages linked')
    detail = next((line for line in result.stdout.splitlines() if line.startswith('stow: ') and 'added' in line), '')
    return DoctorCheck('links', False, detail or 'stow reports pending changes', ['bash', str(STOW_SCRIPT), '--backup-conflicts'])


def check_render() -> DoctorCheck:
    """
    Check that rendered settings files match their fragments.
    """
    result = _capture([sys.executable, str(RENDER_SCRIPT), '--check'])
    if result.returncode == 0:
        return DoctorCheck('render', True, 'rendered settings in sync')
    return DoctorCheck('render', False, 'rendered settings out of sync (see: run.py render --diff)', [sys.executable, str(RENDER_SCRIPT)])


def check_git_version() -> DoctorCheck:
    """
    Check that git supports ``includeIf "hasconfig:remote.*.url:..."`` (git >= 2.36).
    """
    result = _capture(['git', '--version'])
    match  = re.search(r'(\d+)\.(\d+)', result.stdout)
    if match is None:
        return DoctorCheck('git', False, 'could not determine git version')
    version = (int(match.group(1)), int(match.group(2)))
    ok      = version >= MIN_GIT_VERSION
    want    = '.'.join(map(str, MIN_GIT_VERSION))
    return DoctorCheck('git', ok, f'git {version[0]}.{version[1]} (need >= {want} for per-remote identity)')


def check_tools() -> DoctorCheck:
    """
    Check that required command-line tools are on PATH.
    """
    missing = [tool for tool in REQUIRED_TOOLS if shutil.which(tool) is None]
    if missing:
        return DoctorCheck('tools', False, f'missing: {", ".join(missing)}')
    return DoctorCheck('tools', True, ', '.join(REQUIRED_TOOLS))


def doctor_checks() -> list[DoctorCheck]:
    """
    Run every doctor check (tools and layers first; the rest depend on them).
    """
    first = [check_tools(), check_layers()]
    if not all(c.ok for c in first):
        return first
    return [*first, check_git_version(), check_links(), check_render()]


def add_doctor_arguments(parser: argparse.ArgumentParser) -> None:
    """
    Register doctor options.
    """
    parser.add_argument('-f', '--fix', action='store_true', help='Run the fix for each failing check, then re-check')


@command(group='Dotfiles', add_arguments=add_doctor_arguments)
def cmd_doctor(args: argparse.Namespace) -> None:
    """
    Check overlay registry, links, rendered settings, git version, and tools
    """
    checks = doctor_checks()
    if args.fix:
        for check in checks:
            if not check.ok and check.fix:
                printf(f'🔧 {check.name}: {shlex.join(check.fix)}', fg='bright_cyan')
                shell_command(check.fix, indent=3, check=False)
        checks = doctor_checks()
    for check in checks:
        emoji = '🟢' if check.ok else '🔴'
        printf(f'{emoji} {style(check.name, fg="white", bold=True)}  {check.detail}', indent=3)
    if not all(check.ok for check in checks):
        sys.exit(1)
```

```python
def add_bootstrap_arguments(parser: argparse.ArgumentParser) -> None:
    """
    Register bootstrap driver options.
    """
    parser.add_argument('--dry-run', action='store_true', help='Simulate every stage')
    parser.add_argument('--list', action='store_true', help='List stages across layers')
    parser.add_argument('--only', metavar='STAGE', help='Run a single stage')
    parser.add_argument('--from', dest='from_stage', metavar='STAGE', help='Run from STAGE onward')
    parser.add_argument('--resume', action='store_true', help='Continue after the last completed stage')
    parser.add_argument('--verify', action='store_true', help='Run doctor after all stages succeed')
    parser.add_argument('--no-log', action='store_true', help='Do not tee output to the bootstrap log')


@command(group='Dotfiles', add_arguments=add_bootstrap_arguments)
def cmd_bootstrap(args: argparse.Namespace) -> None:
    """
    Run the layered bootstrap stages (bootstrap/bootstrap.sh)
    """
    cmd = ['bash', str(BOOTSTRAP_SCRIPT)]
    for flag, enabled in (('--dry-run', args.dry_run), ('--list', args.list), ('--resume', args.resume),
                          ('--verify', args.verify), ('--no-log', args.no_log)):
        if enabled:
            cmd.append(flag)
    if args.only:
        cmd.extend(['--only', args.only])
    if args.from_stage:
        cmd.extend(['--from', args.from_stage])
    sys.exit(shell_command(cmd, check=False).returncode)


def add_stow_arguments(parser: argparse.ArgumentParser) -> None:
    """
    Register stow options.
    """
    parser.add_argument('packages', nargs='*', help='Packages to stow (default: all, across layers)')
    parser.add_argument('-n', '--simulate', action='store_true', help='Preview without changing $HOME')
    parser.add_argument('--backup-conflicts', action='store_true', help='Move blocking files to ~/.dotfiles-backup')
    parser.add_argument('-v', '--verbose', action='store_true', help='Show the raw stow log')


@command(group='Dotfiles', add_arguments=add_stow_arguments)
def cmd_stow(args: argparse.Namespace) -> None:
    """
    Link stow packages from every layer into $HOME (stow.sh)
    """
    cmd = ['bash', str(STOW_SCRIPT)]
    if args.simulate:
        cmd.append('-n')
    if args.backup_conflicts:
        cmd.append('--backup-conflicts')
    if args.verbose:
        cmd.append('--verbose')
    sys.exit(shell_command([*cmd, *args.packages], check=False).returncode)


def add_render_arguments(parser: argparse.ArgumentParser) -> None:
    """
    Register render options.
    """
    parser.add_argument('targets', nargs='*', help='Targets (default: all)')
    parser.add_argument('--diff', action='store_true', help='Preview differences; write nothing')
    parser.add_argument('--check', action='store_true', help='Exit 1 if out of sync; write nothing')
    parser.add_argument('--force', action='store_true', help='Overwrite in-app edits after backing them up')
    parser.add_argument('-v', '--verbose', action='store_true', help='Report skipped/current targets')


@command(group='Dotfiles', add_arguments=add_render_arguments)
def cmd_render(args: argparse.Namespace) -> None:
    """
    Render settings files from per-layer fragments (scripts/dotfiles/render.py)
    """
    cmd = [sys.executable, str(RENDER_SCRIPT), *args.targets]
    for flag, enabled in (('--diff', args.diff), ('--check', args.check), ('--force', args.force), ('-v', args.verbose)):
        if enabled:
            cmd.append(flag)
    sys.exit(shell_command(cmd, check=False).returncode)


def add_test_arguments(parser: argparse.ArgumentParser) -> None:
    """
    Register test options.
    """
    parser.add_argument('paths', nargs='*', help='Test paths (default: tests/)')


@command(group='Dotfiles', add_arguments=add_test_arguments)
def cmd_test(args: argparse.Namespace) -> None:
    """
    Run the test suite via uv (public-index wrapper)
    """
    cmd = [str(UV_PUBLIC), 'run', '--group', 'test', 'pytest', *(args.paths or ['tests'])]
    sys.exit(shell_command(cmd, check=False).returncode)
```

Adapt mechanical details to `run.py`'s existing conventions (e.g. whether `@command` takes `add_arguments=` exactly
like this, whether `shlex` is imported) — read `cmd_pre` and the `@command` definition first. If the `--fix` printing
or styling helpers differ, use the existing ones.

- [ ] **Step 4: Run tests, regenerate the Makefile, update docs**

Run: `scripts/hooks/uv-public.sh run --group test pytest tests/unit/test_run_doctor.py` → PASS.
Run: `scripts/hooks/uv-public.sh run python run.py makefile && scripts/hooks/uv-public.sh run python run.py --help` →
new `Dotfiles` group lists `bootstrap`, `doctor`, `render`, `stow`, `test`.
Run: `scripts/hooks/uv-public.sh run python run.py doctor; echo "exit=$?"` → runs; on this machine it may report
failures (no packages yet / render fragments absent are fine: links pass with no packages, render passes with no
fragments). Record the output in the report.
Update `docs/RUN_PY_REFERENCE.md` (new "Dotfiles" command section) and `.ctx/BUILD.md` (command list).

- [ ] **Step 5: Commit**

```bash
git add run.py Makefile docs/RUN_PY_REFERENCE.md .ctx/BUILD.md tests/unit/test_run_doctor.py
git commit -m "feat(run): bootstrap, stow, render, doctor, and test commands"
```

---

### Task 7: Run engine tests on macOS in CI

**Files:**

- Modify: `.github/workflows/lint.yml` (the `pytest` job)

- [ ] **Step 1: Move the pytest job to macOS with GNU Stow**

Replace the `pytest` job with:

```yaml
  pytest:
    name: pytest (macOS)
    runs-on: macos-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
      - name: Install GNU Stow
        run: brew install stow
      - name: Install dependencies
        run: uv sync --group test
      - name: Pytest
        run: uv run pytest
```

(macOS is the engine's target platform and provides `/bin/bash` 3.2, which the shell code must support.)

- [ ] **Step 2: Verify locally and commit**

Run: `scripts/hooks/uv-public.sh run yamllint .github/workflows/` → clean.
Run: `scripts/hooks/uv-public.sh run --group test pytest` → all engine + leak-guard tests PASS.

```bash
git add .github/workflows/lint.yml
git commit -m "ci: run the test suite on macOS with GNU Stow"
```

---

## After this plan

Execution continues with `docs/plans/2026-10/2026-10-27-dev-env-port-plan.md`. The branch is not pushed until both plans
are complete (or the user asks for an intermediate PR).
