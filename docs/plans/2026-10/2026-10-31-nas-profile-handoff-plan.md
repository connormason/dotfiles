# NAS Profile and Ansible Handoff Implementation Plan (NAS sub-project 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hand the NAS's `$HOME` to the stow engine (new `dotfiles` role + `profiles/nas`), wrap the HAOS VM script in a
`haos` role, retire the forked `zsh`/`git`/`ssh` roles, and make every changed role idempotent and lint-clean.

**Architecture:** The engine gains a per-run change ledger (`note_change` in `bootstrap/lib.sh`, a final
`bootstrap: changes=N` line from the driver) and a non-interactive mode, so Ansible can run `bootstrap.sh` unattended
and key `changed_when` off one line. `vms/haos/setup.sh` gets the same treatment (`haos: changes=N`). The new roles are
thin: they clone, register the overlay, set the shell, and run the scripts; the scripts remain the implementation.

**Tech Stack:** bash (3.2-compatible engine; bash 5 for `vms/haos/setup.sh`), GNU Stow 2.4.1, Homebrew/Linuxbrew,
Ansible (`ansible-core` from the uv environment), ansible-lint 25.6.1, pytest, GitHub Actions.

**Spec:** [`2026-10-31-nas-provisioning-design.md`](2026-10-31-nas-provisioning-design.md) ("Sub-project 2") plus the
approved addendum [`2026-10-31-nas-profile-handoff-design.md`](2026-10-31-nas-profile-handoff-design.md), which wins
where they differ.

Paths below are relative to the repository root: the worktree
`~/dotfiles-personal/.claude/worktrees/nas-profile-handoff` (branch `worktree-nas-profile-handoff`).

## Global Constraints

- Public repo: nothing employer-specific (names, hosts, tools, people's handles) in any file or commit message. The
  leak guard runs in prek; private patterns live at `~/.config/dotfiles/leak-patterns.txt`.
- Every `uv` call goes through `scripts/hooks/uv-public.sh`. Never run `ruff format`. No bare `python`/`python3`/`pip`.
  Use `$TMPDIR`, never `/tmp`, for scratch files.
- Never run stow, render, bootstrap (outside `--dry-run` in a throwaway HOME) or `doctor --fix` against the real HOME.
  Never run `ansible-playbook` against the NAS: this session cannot reach the LAN, and every live step is the owner's
  (see "Live verification").
- **Zero behaviour change on macOS.** `tests/fixtures/os_layout/*` must stay byte-identical (`git diff main --
  tests/fixtures/os_layout` empty at every commit). `brew bundle` keeps running on every pass. The only new Mac output
  is the run summary's change list and its final `bootstrap: changes=N` line.
- All engine shell code (`bootstrap/`, `stow.sh`) stays bash 3.2-compatible: no associative arrays, `declare -g`,
  `${var,,}`, `mapfile`. The `shell` fixture runs every bash test under `/bin/bash` 3.2 on macOS.
- The engine never runs `apt` and never uses `sudo` on Linux.
- The machine-readable lines are exactly `bootstrap: changes=<N>` and `haos: changes=<N>` (`printf '…%d\n'`, no colour,
  no leading spaces). The roles match `^bootstrap: changes=[0-9]+$` / `^haos: changes=[0-9]+$`.
- Ansible: FQCN modules; `become: true` only on tasks that need root; every `command`/`shell` task has `changed_when`;
  read-only probes have `changed_when: false` and `check_mode: false`; role variables use the role-name prefix
  (`dotfiles_`, `haos_`, `debian_`, `zfs_`) except the inventory-facing `systemd_allow_*`; loop variables match
  `^(__|<role>_)`; modes are quoted strings (`"0755"`). Never run `ansible-lint --fix`.
- Do not bypass hooks (`--no-verify`). Before each commit: `prek run --files <changed files>` and the full suite
  `scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider` pass. Baseline at plan time: **675 passed, 3 skipped**.
- `tests/unit/test_stow_tree.py` fails on untracked files under `stow/`, `render/`, `profiles/`, `tests/fixtures/`:
  `git add` new files there **before** running the full suite.
- Python style: single quotes, sphinx docstrings, `from __future__ import annotations` first, one import per line,
  aligned dict/assignment columns as in neighbouring code, no blank line between a class docstring and its first member.
  Tests: multi-line docstrings (capitalized, no trailing period), `-> None` on every test method, classes `TestXxx`.
- Every test module that runs engine code scrubs `DOTFILES_OS`, `BOOTSTRAP_CHANGES_FILE` and `BOOTSTRAP_NONINTERACTIVE`
  from the inherited environment.
- `docs/plans/` and `.ctx/` are hand-maintained (120-column wrap). Other Markdown is formatted by the `mdformat` prek
  hook; let it.
- Conventional commits (`feat(engine): …`, `feat(ansible): …`, `test: …`, `ci: …`, `docs: …`), one logical change per
  commit. Push only with the owner's approval (Task 16).
- Role tasks (10–14) end with a dispatch of the `ansible-idempotency-reviewer` agent on that task's diff; its
  Critical/Important findings are fixed before the task is marked done.

## File Map

| File | Change |
| --- | --- |
| `bootstrap/lib.sh` | `note_change`, `is_interactive`; non-interactive `confirm` |
| `bootstrap/bootstrap.sh` | Per-run change ledger; summary change list and `bootstrap: changes=N` |
| `bootstrap/20-ssh-key.sh` | Records key generation; non-interactive runs warn and continue |
| `bootstrap/50-brew.sh` | Records Homebrew install, `brew bundle` changes (before/after snapshot), starship removal |
| `bootstrap/80-repos.sh`, `90-python.sh`, `95-dotfiles.sh`, `97-render.sh` | Record their mutations |
| `stow.sh` | Records net link changes and backups; verbose log always captured |
| `bootstrap/Brewfile` | `docker`, `docker-compose`, `mermaid-cli` move into `if OS.mac?` |
| `bootstrap/README.md` | Ledger, summary line, `BOOTSTRAP_NONINTERACTIVE`, stage table |
| `vms/haos/setup.sh` | Change counter, `systemctl` guard, summary line, conditional address wait, test-only path overrides |
| `vms/haos/README.md` | Summary line; the `haos` role in the install and re-bootstrap flows |
| `profiles/nas/README.md`, `profiles/README.md` | **Create** the NAS overlay; index row |
| `roles/dotfiles/` | **Create.** `defaults/main.yml`, `tasks/main.yml`, `README.md` |
| `roles/haos/` | **Create.** `defaults/main.yml`, `tasks/main.yml`, `README.md` |
| `roles/debian/` | Engine prerequisites, Linuxbrew prefix, idempotent sleep-target masking, README |
| `roles/zfs/` | Idempotent `contrib` component and architecture probe, README |
| `roles/git/`, `roles/ssh/`, `roles/zsh/` | **Delete** |
| `roles/requirements.yml` | Drop `community.crypto` |
| `playbooks/nas_bootstrap.yml` | `dotfiles_repo_dir` play var; order debian → zfs → samba → docker → tailscale → dotfiles → haos |
| `nas_bootstrap.sh` | Drop `--ask-become-pass` |
| `scripts/hooks/ansible-lint.sh` | **Create.** Check-only ansible-lint wrapper (throwaway vault password, pinned version) |
| `.yamllint.yaml`, `.ansible-lint.yaml`, `.ansible-lint-ignore` (**create**) | ansible-lint compatibility, no auto-fix, accepted findings |
| `.pre-commit-config.yaml`, `.github/workflows/lint.yml` | ansible-lint hook and CI job |
| `roles/README.md`, `playbooks/README.md`, `README.md`, `.ctx/BUILD.md`, `roles/docker/README.md`, `roles/tailscale/README.md` | Role table, order, drop `--ask-become-pass` |
| Tests: `test_lib_sh.py`, `test_bootstrap_driver.py`, `test_brew_stage.py`, `test_stow_sh.py`, `test_brewfile.py`, `test_docs_consistency.py`; **new** `test_ssh_key_stage.py`, `test_stage_changes.py`, `test_haos_setup.py`, `test_nas_playbook.py` | See tasks |

## Deliberate deviations from the parent design

- **No first-run `--backup-conflicts` flag.** `95-dotfiles` already passes it to `stow.sh` on every run.
- **`profiles/nas` contains only a README.** The engine needs the directory to exist; content arrives when needed.
- **The safety check allows a clean, pushed branch** and switches it to `dotfiles_repo_version` (addendum, `dotfiles`
  role step 1).
- **`haos` and `dotfiles` share `dotfiles_repo_dir` through a play variable** in `playbooks/nas_bootstrap.yml`, so
  `--tags haos` alone still resolves it.

---

### Task 1: `note_change`, `is_interactive`, non-interactive `confirm`

**Files:**
- Modify: `bootstrap/lib.sh` (after `try()`; replace `confirm()`)
- Modify: `bootstrap/README.md` (Usage, overlay-contract variable table)
- Test: `tests/unit/test_lib_sh.py`

**Interfaces:**
- Produces: `note_change MSG...` (appends `"$*"` plus newline to `$BOOTSTRAP_CHANGES_FILE` when that is non-empty;
  otherwise a no-op; always returns 0). `is_interactive` (status 0 iff `BOOTSTRAP_NONINTERACTIVE` is not `1` **and**
  stdin is a terminal). `confirm PROMPT` (non-interactive: warns `non-interactive run: answering no to: PROMPT` on
  stderr, returns 1 without reading stdin; interactive: unchanged).

- [ ] **Step 1: Scrub the new variables in the test environment**

In `tests/unit/test_lib_sh.py`, extend `_SCRUBBED_VARS`:

```python
_SCRUBBED_VARS = (
    'BOOTSTRAP_CHANGES_FILE',
    'BOOTSTRAP_NONINTERACTIVE',
    'DOTFILES_REPO',
    'DOTFILES_BREW_PREFIXES',
    'DOTFILES_LEAK_PATTERNS',
    'DOTFILES_OS',
    'DOTFILES_OVERLAYS_FILE',
)
```

and add `import pty` to the imports (keep them sorted, one per line).

- [ ] **Step 2: Write the failing tests**

Append to `tests/unit/test_lib_sh.py`:

```python
class TestNoteChange:
    """
    Tests for note_change
    """
    def test_appends_one_line_per_call(self, bash: BashRunner, env: dict[str, str], tmp_path: Path) -> None:
        """
        Test that each call appends its message to the ledger as one line
        """
        ledger = tmp_path / 'ledger'
        result = bash('note_change "made a thing"; note_change second', {**env, 'BOOTSTRAP_CHANGES_FILE': str(ledger)})

        assert result.returncode == 0, result.stderr
        assert ledger.read_text(encoding='utf-8').splitlines() == ['made a thing', 'second']

    def test_without_a_ledger_is_a_no_op(self, bash: BashRunner) -> None:
        """
        Test that without BOOTSTRAP_CHANGES_FILE the call writes nothing and succeeds
        """
        result = bash('note_change anything && echo ok')

        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == 'ok'


# Sources lib.sh, asks once, then reads the next stdin line to prove whether confirm consumed it
CONFIRM_SCRIPT = (
    'if confirm "Proceed?"; then echo yes; else echo no; fi\n'
    'IFS= read -r rest || rest=""\n'
    'echo "left:$rest"\n'
)


class TestConfirm:
    """
    Tests for confirm and is_interactive
    """
    def test_noninteractive_flag_answers_no_without_reading(self, shell: str, env: dict[str, str]) -> None:
        """
        Test that BOOTSTRAP_NONINTERACTIVE=1 makes confirm warn and answer no, leaving stdin unread
        """
        result = subprocess.run(
            [shell, '-c', f'source "{LIB}"\n{CONFIRM_SCRIPT}'],
            input='y\n',
            capture_output=True,
            text=True,
            check=False,
            env={**env, 'BOOTSTRAP_NONINTERACTIVE': '1'},
            timeout=60,
        )

        assert result.returncode == 0, result.stderr
        assert result.stdout.splitlines() == ['no', 'left:y']
        assert 'non-interactive run: answering no to: Proceed?' in result.stderr

    def test_non_terminal_stdin_answers_no(self, shell: str, env: dict[str, str]) -> None:
        """
        Test that a pipe on stdin counts as non-interactive even without BOOTSTRAP_NONINTERACTIVE
        """
        result = subprocess.run(
            [shell, '-c', f'source "{LIB}"\n{CONFIRM_SCRIPT}'],
            input='y\n',
            capture_output=True,
            text=True,
            check=False,
            env=env,
            timeout=60,
        )

        assert result.returncode == 0, result.stderr
        assert result.stdout.splitlines() == ['no', 'left:y']

    @pytest.mark.parametrize(
        ('answer', 'expected'),
        [
            ('y', 'yes'),
            ('n', 'no'),
        ],
    )
    def test_terminal_reads_the_reply(self, shell: str, env: dict[str, str], answer: str, expected: str) -> None:
        """
        Test that with a terminal on stdin confirm still reads and honours the reply
        """
        primary, secondary = pty.openpty()
        try:
            os.write(primary, f'{answer}\n'.encode())
            result = subprocess.run(
                [shell, '-c', f'source "{LIB}"\nif confirm "Proceed?"; then echo yes; else echo no; fi'],
                stdin=secondary,
                capture_output=True,
                text=True,
                check=False,
                env=env,
                timeout=60,
            )
        finally:
            os.close(primary)
            os.close(secondary)

        assert result.returncode == 0, result.stderr
        assert result.stdout.splitlines() == [expected]

    def test_is_interactive_honours_the_flag(self, bash: BashRunner, env: dict[str, str]) -> None:
        """
        Test that is_interactive fails when BOOTSTRAP_NONINTERACTIVE=1
        """
        result = bash('if is_interactive; then echo yes; else echo no; fi', {**env, 'BOOTSTRAP_NONINTERACTIVE': '1'})

        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == 'no'
```

- [ ] **Step 3: Run them and watch them fail**

Run: `scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider tests/unit/test_lib_sh.py -k "NoteChange or Confirm"`
Expected: FAIL (`note_change: command not found`; `confirm` reads `y` from the pipe and prints `yes`).

- [ ] **Step 4: Implement**

In `bootstrap/lib.sh`, insert after `try()`:

```bash
# note_change WHAT... -> record one mutation in the driver's per-run change ledger (under --dry-run: one mutation a real
# run would make). The run summary lists and counts them on its final `bootstrap: changes=N` line. A no-op outside a
# driver run (BOOTSTRAP_CHANGES_FILE unset), so stages and stow.sh can call it unconditionally.
note_change() {
    if [ -n "${BOOTSTRAP_CHANGES_FILE:-}" ]; then
        printf '%s\n' "$*" >>"$BOOTSTRAP_CHANGES_FILE"
    fi
    return 0
}
```

Replace the existing `confirm()` with:

```bash
# is_interactive -> success when a human can answer prompts: BOOTSTRAP_NONINTERACTIVE is not 1 (the NAS `dotfiles`
# Ansible role sets it) and stdin is a terminal
is_interactive() {
    [ "${BOOTSTRAP_NONINTERACTIVE:-0}" != "1" ] && [ -t 0 ]
}

# confirm PROMPT -> interactive yes/no, default no. Non-interactive runs answer no without reading stdin, so an
# unattended run can never block on (or silently consume) a prompt.
confirm() {
    local reply
    if ! is_interactive; then
        warn "non-interactive run: answering no to: $1"
        return 1
    fi
    read -r -p "$1 [y/N] " reply
    [[ "$reply" =~ ^[Yy]$ ]]
}
```

- [ ] **Step 5: Run the tests**

Run: `scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider tests/unit/test_lib_sh.py`
Expected: PASS (both shells).

- [ ] **Step 6: Document**

In `bootstrap/README.md`, after the paragraph that starts "Run state lives in", add:

```markdown
Prompts (`lib.sh` `confirm`) need a human: when `BOOTSTRAP_NONINTERACTIVE=1` is set or stdin is not a terminal, every
prompt is answered "no" with a warning instead of blocking. The NAS `dotfiles` Ansible role sets the variable.
```

- [ ] **Step 7: Full suite, hooks, commit**

```bash
scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider
prek run --files bootstrap/lib.sh bootstrap/README.md tests/unit/test_lib_sh.py
git add bootstrap/lib.sh bootstrap/README.md tests/unit/test_lib_sh.py
git commit -m "feat(engine): change ledger helper and non-interactive confirm"
```

---

### Task 2: Driver change ledger and summary line

**Files:**
- Modify: `bootstrap/bootstrap.sh` (ledger creation before `print_summary`; `print_summary`; `cleanup`)
- Modify: `bootstrap/README.md` (Usage paragraph, overlay-contract variable table, stage-table intro)
- Test: `tests/unit/test_bootstrap_driver.py`

**Interfaces:**
- Consumes: `note_change` (Task 1).
- Produces: the driver exports `BOOTSTRAP_CHANGES_FILE` (a fresh `mktemp` file per run, removed on exit; an inherited
  value is ignored). The run summary prints, when non-empty, `  changes:` (`  would change:` under `--dry-run`) followed
  by each ledger line indented four spaces, and its **last stdout line** is `bootstrap: changes=<N>` — also after a
  failed stage.

- [ ] **Step 1: Scrub and write the failing tests**

Add `'BOOTSTRAP_CHANGES_FILE'` and `'BOOTSTRAP_NONINTERACTIVE'` to `_SCRUBBED_VARS` in
`tests/unit/test_bootstrap_driver.py`, then append:

```python
# An overlay stage that records two changes and saves the ledger path it saw
CHANGE_STAGE = (
    '#!/usr/bin/env bash\n'
    'source "$DOTFILES_REPO/bootstrap/lib.sh"\n'
    'printf "%s" "$BOOTSTRAP_CHANGES_FILE" > "$PROBE_FILE"\n'
    'note_change "made a thing"\n'
    'note_change "made another"\n'
)


class TestChangeLedger:
    """
    Tests for the per-run change ledger and the machine-readable summary line
    """
    def test_summary_lists_and_counts_changes(self, base: Path, shell: str, env: dict[str, str], overlay: Path) -> None:
        """
        Test that recorded changes are listed in the summary and counted on its last line
        """
        (overlay / 'bootstrap' / '97-selftest-change.sh').write_text(CHANGE_STAGE, encoding='utf-8')

        result = _drive(base, shell, env, '--no-log', '--only', '97-selftest-change')
        assert result.returncode == 0, result.stderr

        lines = result.stdout.splitlines()
        assert lines[-1] == 'bootstrap: changes=2'
        assert lines.index('  changes:') < lines.index('    made a thing') < lines.index('    made another')

    def test_no_changes_reports_zero(self, base: Path, shell: str, env: dict[str, str]) -> None:
        """
        Test that a run that records nothing ends with changes=0 and lists no changes
        """
        result = _drive(base, shell, env, '--no-log', '--only', '98-selftest-ok')
        assert result.returncode == 0, result.stderr

        lines = result.stdout.splitlines()
        assert lines[-1] == 'bootstrap: changes=0'
        assert '  changes:' not in lines

    def test_dry_run_counts_would_be_changes(self, base: Path, shell: str, env: dict[str, str], overlay: Path) -> None:
        """
        Test that under --dry-run the list is labelled as would-be changes and still counted
        """
        (overlay / 'bootstrap' / '97-selftest-change.sh').write_text(CHANGE_STAGE, encoding='utf-8')

        result = _drive(base, shell, env, '--dry-run', '--no-log', '--only', '97-selftest-change')
        assert result.returncode == 0, result.stderr

        lines = result.stdout.splitlines()
        assert '  would change:' in lines
        assert lines[-1] == 'bootstrap: changes=2'

    def test_failed_stage_still_ends_with_the_line(self, base: Path, shell: str, env: dict[str, str]) -> None:
        """
        Test that the summary line is printed when a stage fails
        """
        result = _drive(base, shell, env, '--no-log', '--from', '99-selftest-fail')

        assert result.returncode != 0
        assert result.stdout.splitlines()[-1] == 'bootstrap: changes=0'

    def test_ledger_is_fresh_and_removed(
        self,
        base: Path,
        shell: str,
        env: dict[str, str],
        overlay: Path,
        tmp_path: Path,
    ) -> None:
        """
        Test that an inherited ledger path is ignored and the run's own ledger is deleted on exit
        """
        (overlay / 'bootstrap' / '97-selftest-change.sh').write_text(CHANGE_STAGE, encoding='utf-8')
        inherited = tmp_path / 'inherited-ledger'

        result = _drive(
            base,
            shell,
            {**env, 'BOOTSTRAP_CHANGES_FILE': str(inherited)},
            '--no-log',
            '--only',
            '97-selftest-change',
        )
        assert result.returncode == 0, result.stderr

        seen = Path(Path(env['PROBE_FILE']).read_text(encoding='utf-8'))
        assert seen != inherited
        assert not inherited.exists()
        assert not seen.exists()
```

- [ ] **Step 2: Run them and watch them fail**

Run: `scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider tests/unit/test_bootstrap_driver.py -k ChangeLedger`
Expected: FAIL (no `bootstrap: changes=` line).

- [ ] **Step 3: Implement**

In `bootstrap/bootstrap.sh`, immediately before the comment `# Per-stage timing + end-of-run summary state`, insert:

```bash
# Per-run change ledger: stages record each mutation (under --dry-run, each one a real run would make) with lib.sh
# note_change; the summary lists them and ends with a machine-readable `bootstrap: changes=N` line that unattended
# callers (the NAS `dotfiles` Ansible role) key their changed status off. Always a fresh file: an inherited path from
# an enclosing run must not be appended to. Lives in TMPDIR and is deleted on exit, so dry runs still leave no state.
BOOTSTRAP_CHANGES_FILE="$(mktemp "${TMPDIR:-/tmp}/bootstrap-changes.XXXXXX")" || die "cannot create the change ledger"
export BOOTSTRAP_CHANGES_FILE
```

In `print_summary`, change `local i emoji` to `local i emoji line changes=0`, and replace the block from
`printf '  total: %s\n' …` through the `LOGFILE` block with:

```bash
    if [ -s "$BOOTSTRAP_CHANGES_FILE" ]; then
        changes="$(wc -l <"$BOOTSTRAP_CHANGES_FILE" | tr -d ' ')"
        if [ "${BOOTSTRAP_DRY_RUN:-0}" = "1" ]; then
            printf '  would change:\n'
        else
            printf '  changes:\n'
        fi
        while IFS= read -r line; do
            printf '    %s\n' "$line"
        done <"$BOOTSTRAP_CHANGES_FILE"
    fi
    printf '  total: %s\n' "$(fmt_duration "$((SECONDS - RUN_START))")"
    if [ -n "$LOGFILE" ]; then
        printf '  log:   %s\n' "$LOGFILE"
    fi
    if [ -n "$FAILED_STAGE" ]; then
        warn "failed at stage: $FAILED_STAGE — resume with: bootstrap.sh --resume (or: --from $FAILED_STAGE)"
    fi
    printf 'bootstrap: changes=%d\n' "$changes"
```

(Keep the trailing `return 0` and its comment.) In `cleanup()`, after `print_summary`, add
`rm -f "$BOOTSTRAP_CHANGES_FILE"`.

- [ ] **Step 4: Run the driver tests**

Run: `scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider tests/unit/test_bootstrap_driver.py`
Expected: PASS. If an older test asserted the summary's last line, update it to look before `bootstrap: changes=`.

- [ ] **Step 5: Document**

In `bootstrap/README.md`:
- Extend the "Run state lives in" paragraph: "Every run ends with a summary whose last line is `bootstrap: changes=N`:
  the number of mutations the stages recorded (under `--dry-run`, the number a real run would make), listed above it.
  Dry runs create only a temporary change ledger, deleted on exit."
- Add a row to the stage-environment table: `| BOOTSTRAP_CHANGES_FILE | Per-run change ledger; stages append to it through lib.sh note_change, never directly |`.
- In the "Stages" intro, after "Every mutation goes through `run`/`try`, so `--dry-run` prints it instead;", add
  "each one that actually changes something (or would) is also recorded with `note_change`. The macOS-only stages
  (`60-macos`, `72-vscode`, `96-iterm2`) do not record; the count is a signal for unattended NAS runs."

- [ ] **Step 6: Full suite, hooks, commit**

```bash
scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider
prek run --files bootstrap/bootstrap.sh bootstrap/README.md tests/unit/test_bootstrap_driver.py
git add bootstrap/bootstrap.sh bootstrap/README.md tests/unit/test_bootstrap_driver.py
git commit -m "feat(engine): per-run change ledger and bootstrap: changes=N summary line"
```

---

### Task 3: `20-ssh-key` in unattended runs

**Files:**
- Modify: `bootstrap/20-ssh-key.sh`
- Modify: `bootstrap/README.md` (stage table row `20-ssh-key`)
- Create: `tests/unit/test_ssh_key_stage.py`

**Interfaces:**
- Consumes: `note_change`, `is_interactive`, `confirm` (Task 1).
- Produces: records `generated SSH key <path>`; when auth fails in a non-interactive real run it prints the public key,
  warns `non-interactive run: continuing without a GitHub-registered key …`, and exits 0.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_ssh_key_stage.py`:

```python
"""
Unit tests for bootstrap/20-ssh-key.sh (stub ssh and ssh-keygen; isolated HOME)
"""
from __future__ import annotations

import os
import pty
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
STAGE     = REPO_ROOT / 'bootstrap' / '20-ssh-key.sh'

_SCRUBBED_VARS: tuple[str, ...] = (
    'BOOTSTRAP_CHANGES_FILE',
    'BOOTSTRAP_DRY_RUN',
    'BOOTSTRAP_NONINTERACTIVE',
    'DOTFILES_BREW_PREFIXES',
    'DOTFILES_LAYER',
    'DOTFILES_OS',
    'DOTFILES_REPO',
    'XDG_CONFIG_HOME',
)

DENIED  = 'printf "git@github.com: Permission denied (publickey).\\n" >&2\nexit 255\n'
WORKING = 'printf "Hi tester! You have successfully authenticated.\\n" >&2\nexit 1\n'


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    """
    Isolated HOME, no overlays, a ledger, and stubs: ssh (auth denied) and ssh-keygen (writes a fake key pair)
    """
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    (bin_dir / 'ssh').write_text(f'#!/bin/sh\n{DENIED}', encoding='utf-8')
    (bin_dir / 'ssh-keygen').write_text(
        '#!/bin/sh\n'
        'while [ $# -gt 0 ]; do\n'
        '    if [ "$1" = "-f" ]; then key="$2"; fi\n'
        '    shift\n'
        'done\n'
        'echo private > "$key"\n'
        'echo "ssh-ed25519 AAAATEST tester@host" > "$key.pub"\n',
        encoding='utf-8',
    )
    for stub in bin_dir.iterdir():
        stub.chmod(0o755)

    home = tmp_path / 'home'
    home.mkdir()
    return {
        **{key: value for key, value in os.environ.items() if key not in _SCRUBBED_VARS},
        'HOME':                   str(home),
        'PATH':                   f'{bin_dir}:{os.environ["PATH"]}',
        'DOTFILES_OVERLAYS_FILE': str(tmp_path / 'no-overlays'),
        'BOOTSTRAP_DRY_RUN':      '0',
        'BOOTSTRAP_CHANGES_FILE': str(tmp_path / 'ledger'),
    }


def _stage(shell: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """
    Run the stage with stdin closed (an unattended run)
    """
    return subprocess.run(
        [shell, str(STAGE)],
        capture_output=True,
        text=True,
        check=False,
        env=env,
        stdin=subprocess.DEVNULL,
        timeout=60,
    )


def _ledger(env: dict[str, str]) -> list[str]:
    """
    Lines recorded in the change ledger (empty when none were)
    """
    path = Path(env['BOOTSTRAP_CHANGES_FILE'])
    return path.read_text(encoding='utf-8').splitlines() if path.exists() else []


class TestUnattendedSshKey:
    """
    Tests for 20-ssh-key without a human at the keyboard
    """
    @pytest.mark.parametrize('flag', ['1', None])
    def test_generates_key_warns_and_continues(self, shell: str, env: dict[str, str], flag: str | None) -> None:
        """
        Test that failed GitHub auth generates a key, prints it, warns, and exits 0 (flag set or stdin closed)
        """
        if flag is not None:
            env['BOOTSTRAP_NONINTERACTIVE'] = flag

        result = _stage(shell, env)
        assert result.returncode == 0, result.stderr

        key = Path(env['HOME']) / '.ssh' / 'id_ed25519'
        assert key.exists()
        assert 'ssh-ed25519 AAAATEST' in result.stdout
        assert 'non-interactive run: continuing without a GitHub-registered key' in result.stderr
        assert _ledger(env) == [f'generated SSH key {key}']

    def test_existing_key_is_kept_and_not_counted(self, shell: str, env: dict[str, str]) -> None:
        """
        Test that an existing key is neither regenerated nor recorded as a change
        """
        ssh_dir = Path(env['HOME']) / '.ssh'
        ssh_dir.mkdir()
        (ssh_dir / 'id_ed25519').write_text('mine\n', encoding='utf-8')
        (ssh_dir / 'id_ed25519.pub').write_text('ssh-ed25519 AAAAMINE me@host\n', encoding='utf-8')

        result = _stage(shell, env)
        assert result.returncode == 0, result.stderr
        assert (ssh_dir / 'id_ed25519').read_text(encoding='utf-8') == 'mine\n'
        assert _ledger(env) == []

    def test_working_auth_changes_nothing(self, shell: str, env: dict[str, str], tmp_path: Path) -> None:
        """
        Test that working GitHub auth exits early without generating or recording anything
        """
        (tmp_path / 'bin' / 'ssh').write_text(f'#!/bin/sh\n{WORKING}', encoding='utf-8')

        result = _stage(shell, env)
        assert result.returncode == 0, result.stderr
        assert 'already works' in result.stdout
        assert not (Path(env['HOME']) / '.ssh' / 'id_ed25519').exists()
        assert _ledger(env) == []


class TestInteractiveSshKey:
    """
    Tests for 20-ssh-key with a terminal on stdin
    """
    def test_declining_still_fails(self, shell: str, env: dict[str, str]) -> None:
        """
        Test that answering no at the terminal keeps the existing failure and re-run hint
        """
        primary, secondary = pty.openpty()
        try:
            os.write(primary, b'n\n')
            result = subprocess.run(
                [shell, str(STAGE)],
                stdin=secondary,
                capture_output=True,
                text=True,
                check=False,
                env=env,
                timeout=60,
            )
        finally:
            os.close(primary)
            os.close(secondary)

        assert result.returncode != 0
        assert 'register the SSH key, then re-run --from 20-ssh-key' in result.stderr
```

- [ ] **Step 2: Run them and watch them fail**

Run: `scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider tests/unit/test_ssh_key_stage.py`
Expected: FAIL (unattended runs die at `confirm`; nothing recorded).

- [ ] **Step 3: Implement**

In `bootstrap/20-ssh-key.sh`, after `run ssh-keygen …` add `note_change "generated SSH key $KEY"`. Replace the final
block

```bash
if [ "${BOOTSTRAP_DRY_RUN}" != "1" ]; then
    confirm "Has the key been registered and verified?" || die "register the SSH key, then re-run --from 20-ssh-key"
fi
```

with

```bash
if [ "${BOOTSTRAP_DRY_RUN}" != "1" ]; then
    if is_interactive; then
        confirm "Has the key been registered and verified?" || die "register the SSH key, then re-run --from 20-ssh-key"
    else
        # An unattended run (the NAS `dotfiles` Ansible role) cannot wait for a human: the key printed above is the
        # follow-up, and the rest of the run does not need GitHub SSH access
        warn "non-interactive run: continuing without a GitHub-registered key (register it, then verify with: ssh -T $GITHUB)"
    fi
fi
```

- [ ] **Step 4: Run the tests**

Run: `scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider tests/unit/test_ssh_key_stage.py`
Expected: PASS.

- [ ] **Step 5: Document**

`bootstrap/README.md` stage table, row `20-ssh-key`, Purpose becomes: "`~/.ssh` (mode 700) and an ed25519 key; if
`ssh -T git@github.com` fails, print the key to register and ask for confirmation (non-interactive runs warn and
continue)".

- [ ] **Step 6: Full suite, hooks, commit**

```bash
scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider
prek run --files bootstrap/20-ssh-key.sh bootstrap/README.md tests/unit/test_ssh_key_stage.py
git add bootstrap/20-ssh-key.sh bootstrap/README.md tests/unit/test_ssh_key_stage.py
git commit -m "feat(engine): 20-ssh-key warns and continues in unattended runs"
```

---

### Task 4: Change points in `80-repos`, `90-python`, `95-dotfiles`, `97-render`

**Files:**
- Modify: `bootstrap/80-repos.sh`, `bootstrap/90-python.sh`, `bootstrap/95-dotfiles.sh`, `bootstrap/97-render.sh`
- Create: `tests/unit/test_stage_changes.py`

**Interfaces:**
- Consumes: `note_change` (Task 1).
- Produces ledger lines: `cloned <name>`; `installed uv tool <name>`; `installed oh-my-zsh`; `cloned omz plugin <name>`;
  `render: wrote settings` (real run, when `render.py` printed a `: rendered ` line);
  `render: settings out of sync` (dry run, `render.py --check` exit 1).

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_stage_changes.py`:

```python
"""
Unit tests for the change-ledger entries of the 80-repos, 90-python, 95-dotfiles, and 97-render stages
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

_SCRUBBED_VARS: tuple[str, ...] = (
    'BOOTSTRAP_CHANGES_FILE',
    'BOOTSTRAP_DRY_RUN',
    'BOOTSTRAP_NONINTERACTIVE',
    'DOTFILES_BREW_PREFIXES',
    'DOTFILES_LAYER',
    'DOTFILES_OS',
    'DOTFILES_REPO',
    'XDG_CONFIG_HOME',
    'XDG_STATE_HOME',
)

# Keeps lib.sh from appending a real Homebrew prefix to PATH (which would expose a real stow, uv, or git)
NO_BREW = 'ensure_brew_on_path() { return 0; }\n'


@pytest.fixture
def overlay(tmp_path: Path) -> Path:
    """
    An overlay whose env.sh hides any real Homebrew; tests add manifest fragments to its bootstrap/
    """
    root = tmp_path / 'overlay'
    (root / 'bootstrap').mkdir(parents=True)
    (root / 'bootstrap' / 'env.sh').write_text(NO_BREW, encoding='utf-8')
    return root


@pytest.fixture
def env(tmp_path: Path, overlay: Path) -> dict[str, str]:
    """
    Isolated HOME, the overlay registered, a stub bin directory first on a minimal PATH, and a ledger
    """
    (tmp_path / 'bin').mkdir()
    (tmp_path / 'home').mkdir()
    registry = tmp_path / 'overlays'
    registry.write_text(f'{overlay}\n', encoding='utf-8')
    return {
        **{key: value for key, value in os.environ.items() if key not in _SCRUBBED_VARS},
        'HOME':                   str(tmp_path / 'home'),
        'PATH':                   f'{tmp_path / "bin"}:/usr/bin:/bin',
        'DOTFILES_OVERLAYS_FILE': str(registry),
        'BOOTSTRAP_DRY_RUN':      '0',
        'BOOTSTRAP_CHANGES_FILE': str(tmp_path / 'ledger'),
    }


def _stub(env: dict[str, str], name: str, body: str) -> None:
    """
    Write an executable stub into the env's bin directory
    """
    path = Path(env['PATH'].split(':', 1)[0]) / name
    path.write_text(f'#!/bin/sh\n{body}', encoding='utf-8')
    path.chmod(0o755)


def _stage(shell: str, name: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """
    Run a base stage in place under the bash interpreter being tested
    """
    return subprocess.run(
        [shell, str(REPO_ROOT / 'bootstrap' / f'{name}.sh')],
        capture_output=True,
        text=True,
        check=False,
        env=env,
        stdin=subprocess.DEVNULL,
        timeout=120,
    )


def _ledger(env: dict[str, str]) -> list[str]:
    """
    Lines recorded in the change ledger (empty when none were)
    """
    path = Path(env['BOOTSTRAP_CHANGES_FILE'])
    return path.read_text(encoding='utf-8').splitlines() if path.exists() else []


class TestReposChanges:
    """
    Tests for 80-repos change entries
    """
    def test_clone_is_recorded_once(self, shell: str, env: dict[str, str], overlay: Path) -> None:
        """
        Test that a clone is recorded and an existing clone is not
        """
        (overlay / 'bootstrap' / 'repos.txt').write_text('demo https://example.invalid/demo.git\n', encoding='utf-8')
        _stub(env, 'git', '[ "$1" = clone ] && mkdir -p "$3/.git"\nexit 0\n')

        first = _stage(shell, '80-repos', env)
        assert first.returncode == 0, first.stderr
        assert _ledger(env) == ['cloned demo']

        second = _stage(shell, '80-repos', env)
        assert second.returncode == 0, second.stderr
        assert _ledger(env) == ['cloned demo']


class TestPythonChanges:
    """
    Tests for 90-python change entries
    """
    @pytest.mark.parametrize(
        ('listed', 'expected'),
        [
            ('',               ['installed uv tool ruff']),
            ('ruff v0.9.0\\n', []),
        ],
    )
    def test_install_is_recorded_only_when_missing(
        self,
        shell: str,
        env: dict[str, str],
        overlay: Path,
        listed: str,
        expected: list[str],
    ) -> None:
        """
        Test that a missing tool's install is recorded and a present tool is not
        """
        (overlay / 'bootstrap' / 'uv-tools.txt').write_text('ruff\n', encoding='utf-8')
        _stub(env, 'uv', f'[ "$1 $2" = "tool list" ] && printf "{listed}"\nexit 0\n')
        _stub(env, 'hatch', 'exit 0\n')

        result = _stage(shell, '90-python', {**env, 'BOOTSTRAP_DRY_RUN': '1'})
        assert result.returncode == 0, result.stderr
        assert _ledger(env) == expected


class TestDotfilesChanges:
    """
    Tests for 95-dotfiles change entries (dry run, with stow hidden so only the oh-my-zsh steps are exercised)
    """
    def test_missing_omz_and_plugins_are_recorded(self, shell: str, env: dict[str, str]) -> None:
        """
        Test that a would-be oh-my-zsh install and plugin clones are recorded
        """
        result = _stage(shell, '95-dotfiles', {**env, 'BOOTSTRAP_DRY_RUN': '1'})
        assert result.returncode == 0, result.stderr
        assert {'installed oh-my-zsh', 'cloned omz plugin alias-tips', 'cloned omz plugin zsh-histdb'} <= set(
            _ledger(env),
        )

    def test_present_omz_and_plugins_are_not(self, shell: str, env: dict[str, str]) -> None:
        """
        Test that an installed oh-my-zsh with both plugins records nothing
        """
        omz = Path(env['HOME']) / '.oh-my-zsh'
        for plugin in ('alias-tips', 'zsh-histdb'):
            (omz / 'custom' / 'plugins' / plugin).mkdir(parents=True)
        (omz / 'oh-my-zsh.sh').write_text('# stub\n', encoding='utf-8')

        result = _stage(shell, '95-dotfiles', {**env, 'BOOTSTRAP_DRY_RUN': '1'})
        assert result.returncode == 0, result.stderr
        assert not [line for line in _ledger(env) if 'oh-my-zsh' in line or 'omz plugin' in line]


class TestRenderChanges:
    """
    Tests for 97-render change entries (real render.py into the isolated HOME)
    """
    def test_first_render_is_recorded_and_second_is_not(self, shell: str, env: dict[str, str]) -> None:
        """
        Test that writing settings is recorded and an in-sync render records nothing
        """
        first = _stage(shell, '97-render', env)
        assert first.returncode == 0, first.stderr
        assert _ledger(env) == ['render: wrote settings']

        second = _stage(shell, '97-render', env)
        assert second.returncode == 0, second.stderr
        assert _ledger(env) == ['render: wrote settings']

    def test_dry_run_records_drift(self, shell: str, env: dict[str, str]) -> None:
        """
        Test that a dry run against unrendered settings records the drift
        """
        result = _stage(shell, '97-render', {**env, 'BOOTSTRAP_DRY_RUN': '1'})
        assert result.returncode == 0, result.stderr
        assert _ledger(env) == ['render: settings out of sync']
```

Note for the implementer: `/usr/bin/python3` must exist for the render tests (macOS Command Line Tools, every Linux
runner). If `uv tool list` output in `90-python`'s parser differs from `ruff v0.9.0`, match the stage's
`awk '{print $1}'` contract (first field = tool name).

- [ ] **Step 2: Run them and watch them fail**

Run: `scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider tests/unit/test_stage_changes.py`
Expected: FAIL (empty ledgers).

- [ ] **Step 3: Implement**

`bootstrap/80-repos.sh` — after `run git clone "$url" "$dest"`: `note_change "cloned $name"`.

`bootstrap/90-python.sh` — after `run uv tool install ${TOOL_ARGS[$i]}`: `note_change "installed uv tool $tool"`.

`bootstrap/95-dotfiles.sh` — at the end of the `else` branch that installs oh-my-zsh (after the inner `if/else/fi`):
`note_change "installed oh-my-zsh"`; after `run git clone --depth 1 "$url" "$dest"`:
`note_change "cloned omz plugin $name"`.

`bootstrap/97-render.sh` — in the dry-run `case`, change the `1)` arm to:

```bash
    1)
        warn "rendered settings out of sync; a real run renders them (preview with: run.py render --diff)"
        note_change "render: settings out of sync"
        ;;
```

and replace the real-run call

```bash
rc=0
run python3 "$RENDER" || rc=$?
```

with

```bash
# render.py prints "<target>: rendered <path>" for every file it actually writes; that is the change signal
rc=0
out="$(run python3 "$RENDER")" || rc=$?
if [ -n "$out" ]; then
    printf '%s\n' "$out"
fi
case "$out" in
*': rendered '*) note_change "render: wrote settings" ;;
esac
```

- [ ] **Step 4: Run the tests**

Run: `scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider tests/unit/test_stage_changes.py tests/unit/test_bootstrap_stages.py`
Expected: PASS.

- [ ] **Step 5: Full suite, hooks, commit**

```bash
scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider
prek run --files bootstrap/80-repos.sh bootstrap/90-python.sh bootstrap/95-dotfiles.sh bootstrap/97-render.sh tests/unit/test_stage_changes.py
git add bootstrap/80-repos.sh bootstrap/90-python.sh bootstrap/95-dotfiles.sh bootstrap/97-render.sh tests/unit/test_stage_changes.py
git commit -m "feat(engine): record repo, uv tool, oh-my-zsh and render changes in the ledger"
```

---

### Task 5: `50-brew` change detection

**Files:**
- Modify: `bootstrap/50-brew.sh`
- Test: `tests/unit/test_brew_stage.py`

**Interfaces:**
- Consumes: `note_change` (Task 1).
- Produces ledger lines: `installed Homebrew`; `brew bundle changed installed packages (<brewfile>)` (real run: the
  `brew_state` snapshot differs after `brew bundle`); `brew bundle would install or upgrade entries from <brewfile>`
  (dry run: `brew` absent, or `HOMEBREW_NO_AUTO_UPDATE=1 brew bundle check` fails); `removed legacy starship
  <path>`. `brew bundle` itself still runs on every real pass.

- [ ] **Step 1: Write the failing tests**

In `tests/unit/test_brew_stage.py`, add `'BOOTSTRAP_CHANGES_FILE'` and `'BOOTSTRAP_NONINTERACTIVE'` to the sandbox's
`scrubbed` tuple and `'BOOTSTRAP_CHANGES_FILE': str(tmp_path / 'ledger'),` to its `env`. Add an assertion at the end
of `test_matching_checksum_runs_installer`:

```python
        assert Path(sandbox.env['BOOTSTRAP_CHANGES_FILE']).read_text(encoding='utf-8').splitlines() == [
            'installed Homebrew',
        ]
```

Append:

```python
# A brew that is already installed: `bundle check` passes iff $BREW_STATE/satisfied exists; `bundle --file` appends a
# formula to the installed list iff $BREW_STATE/bundle-installs exists; `list`/`tap` print the state. `list <formula>`
# fails, so the darwin-only legacy-starship check never depends on the host's /usr/local/bin/starship.
BREW_STUB = (
    '#!/bin/sh\n'
    'case "$1 $2" in\n'
    '"bundle check") [ -f "$BREW_STATE/satisfied" ]; exit $? ;;\n'
    '"bundle --file") [ -f "$BREW_STATE/bundle-installs" ] && echo "newpkg 1.0" >> "$BREW_STATE/formulae"; exit 0 ;;\n'
    '"list --formula") cat "$BREW_STATE/formulae" 2>/dev/null; exit 0 ;;\n'
    '"list --cask") exit 0 ;;\n'
    '"list "*) exit 1 ;;\n'
    'esac\n'
    'exit 0\n'
)


def _installed_brew(box: Sandbox, tmp_path: Path) -> Path:
    """
    Put the stub brew into the sandbox prefix and give the overlay a Brewfile; return the stub's state directory
    """
    state = tmp_path / 'brew-state'
    state.mkdir()
    (state / 'formulae').write_text('stow 2.4.1\n', encoding='utf-8')

    prefix_bin = Path(box.env['SANDBOX_PREFIX']) / 'bin'
    prefix_bin.mkdir(parents=True)
    (prefix_bin / 'brew').write_text(BREW_STUB, encoding='utf-8')
    (prefix_bin / 'brew').chmod(0o755)

    registry = Path(box.env['DOTFILES_OVERLAYS_FILE'])
    overlay  = Path(registry.read_text(encoding='utf-8').strip())
    (overlay / 'bootstrap' / 'Brewfile').write_text('brew "stow"\n', encoding='utf-8')

    box.env['BREW_STATE'] = str(state)
    return state


def _ledger(box: Sandbox) -> list[str]:
    """
    Lines recorded in the sandbox's change ledger (empty when none were)
    """
    path = Path(box.env['BOOTSTRAP_CHANGES_FILE'])
    return path.read_text(encoding='utf-8').splitlines() if path.exists() else []


class TestBundleChanges:
    """
    Tests for recording what `brew bundle` changed
    """
    def test_bundle_that_installs_is_recorded(self, shell: str, sandbox: Sandbox, tmp_path: Path) -> None:
        """
        Test that a bundle run that changes the installed set is recorded
        """
        state = _installed_brew(sandbox, tmp_path)
        (state / 'bundle-installs').touch()
        (state / 'satisfied').touch()

        result = _run(shell, sandbox)
        assert result.returncode == 0, result.stderr
        assert len(_ledger(sandbox)) == 1
        assert _ledger(sandbox)[0].startswith('brew bundle changed installed packages (')

    def test_no_op_bundle_is_not_recorded(self, shell: str, sandbox: Sandbox, tmp_path: Path) -> None:
        """
        Test that a bundle run that changes nothing is not recorded (and still ran)
        """
        state = _installed_brew(sandbox, tmp_path)
        (state / 'satisfied').touch()

        result = _run(shell, sandbox)
        assert result.returncode == 0, result.stderr
        assert _ledger(sandbox) == []

    @pytest.mark.parametrize(
        ('satisfied', 'recorded'),
        [
            (True,  False),
            (False, True),
        ],
    )
    def test_dry_run_predicts_from_bundle_check(
        self,
        shell: str,
        sandbox: Sandbox,
        tmp_path: Path,
        satisfied: bool,
        recorded: bool,
    ) -> None:
        """
        Test that a dry run records a would-be change exactly when `brew bundle check` fails
        """
        state = _installed_brew(sandbox, tmp_path)
        if satisfied:
            (state / 'satisfied').touch()
        sandbox.env['BOOTSTRAP_DRY_RUN'] = '1'

        result = _run(shell, sandbox)
        assert result.returncode == 0, result.stderr
        assert bool(_ledger(sandbox)) is recorded
        assert '[dry-run] brew bundle --file' in result.stdout
```

- [ ] **Step 2: Run them and watch them fail**

Run: `scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider tests/unit/test_brew_stage.py`
Expected: the new tests and the extended checksum test FAIL.

- [ ] **Step 3: Implement**

In `bootstrap/50-brew.sh`, after `cleanup_installer()` add:

```bash
# brew_state -> the installed formulae and casks with their versions, plus the taps: compared before and after
# `brew bundle` to tell whether it installed, upgraded, or tapped anything. Casks do not exist on Linux.
brew_state() {
    brew list --formula --versions 2>/dev/null || true
    brew list --cask --versions 2>/dev/null || true
    brew tap 2>/dev/null || true
}
```

After `install_homebrew` in the "installing Homebrew" branch, add `note_change "installed Homebrew"` (before
`ensure_brew_on_path`). Replace the body of the Brewfile loop (from `log "applying $brewfile"` to the closing `fi` of the
check) with:

```bash
    log "applying $brewfile"
    if [ "${BOOTSTRAP_DRY_RUN}" = "1" ]; then
        run brew bundle --file "$brewfile"
        # Predict instead of observe: a failing check (missing or outdated entries) means a real run changes something.
        # On a fresh machine brew is not installed yet, so everything is a change.
        if have brew && HOMEBREW_NO_AUTO_UPDATE=1 brew bundle check --file "$brewfile" >/dev/null 2>&1; then
            log "Brewfile satisfied: $brewfile"
        else
            note_change "brew bundle would install or upgrade entries from $brewfile"
        fi
        continue
    fi
    before="$(brew_state)"
    run brew bundle --file "$brewfile"
    if [ "$(brew_state)" != "$before" ]; then
        note_change "brew bundle changed installed packages ($brewfile)"
    fi
    if brew bundle check --file "$brewfile"; then
        log "Brewfile satisfied: $brewfile"
    else
        warn "Brewfile drift: $brewfile has dependencies missing or out of date (see 'brew bundle check' above)"
    fi
```

In the starship block, add `note_change "removed legacy starship $LEGACY_STARSHIP"` after each of the two
`run sudo rm -f "$LEGACY_STARSHIP"` lines.

- [ ] **Step 4: Run the tests**

Run: `scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider tests/unit/test_brew_stage.py`
Expected: PASS.

- [ ] **Step 5: macOS dry-run sanity check (throwaway HOME)**

```bash
mkdir -p "$TMPDIR/sp2-home" && HOME="$TMPDIR/sp2-home" bash bootstrap/bootstrap.sh --dry-run --no-log --only 50-brew
```

Expected: exit 0, the base Brewfile reported as satisfied or as a would-be change, and a final
`bootstrap: changes=<N>` line. Nothing under the real HOME changes (dry run). Delete `$TMPDIR/sp2-home` afterwards.

- [ ] **Step 6: Full suite, hooks, commit**

```bash
scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider
prek run --files bootstrap/50-brew.sh tests/unit/test_brew_stage.py
git add bootstrap/50-brew.sh tests/unit/test_brew_stage.py
git commit -m "feat(engine): record Homebrew installs and brew bundle changes in the ledger"
```

---

### Task 6: `stow.sh` change detection

**Files:**
- Modify: `stow.sh` (`EFF_LEVEL`, `summarize()`, backup loops)
- Modify: `stow.sh` header comment (one line)
- Test: `tests/unit/test_stow_sh.py`

**Interfaces:**
- Consumes: `note_change` (Task 1; `stow.sh` already sources `lib.sh`).
- Produces ledger lines: the summarizer's last line when it is not `stow: no changes (already current)` (e.g.
  `stow: 1 added, 0 updated, 0 removed`) — also with `--no-summary` and under `-n`; `stow: backed up ~/<target>` /
  `stow: would back up ~/<target>` per conflicting file.

- [ ] **Step 1: Write the failing tests**

Add `'BOOTSTRAP_CHANGES_FILE'` to `_SCRUBBED_VARS` in `tests/unit/test_stow_sh.py` and append:

```python
class TestChangeLedger:
    """
    Tests for stow.sh's entries in the bootstrap change ledger
    """
    @staticmethod
    def _ledger(path: Path) -> list[str]:
        """
        Lines recorded in the ledger (empty when none were)
        """
        return path.read_text(encoding='utf-8').splitlines() if path.exists() else []

    def test_first_apply_is_recorded_and_restow_is_not(self, world: dict[str, Path], tmp_path: Path) -> None:
        """
        Test that new links are recorded and an idempotent restow records nothing
        """
        _pkg(world['repo'], 'demo', {'.democonf': 'x\n'})
        ledger = tmp_path / 'ledger'

        first = _stow(world, extra_env={'BOOTSTRAP_CHANGES_FILE': str(ledger)})
        assert first.returncode == 0, first.stderr
        assert self._ledger(ledger) == ['stow: 1 added, 0 updated, 0 removed']

        ledger.unlink()
        second = _stow(world, extra_env={'BOOTSTRAP_CHANGES_FILE': str(ledger)})
        assert second.returncode == 0, second.stderr
        assert self._ledger(ledger) == []

    def test_no_summary_still_records(self, world: dict[str, Path], tmp_path: Path) -> None:
        """
        Test that --no-summary hides the summary but the change is still recorded
        """
        _pkg(world['repo'], 'demo', {'.democonf': 'x\n'})
        ledger = tmp_path / 'ledger'

        result = _stow(world, '--no-summary', extra_env={'BOOTSTRAP_CHANGES_FILE': str(ledger)})
        assert result.returncode == 0, result.stderr
        assert 'added' not in result.stdout
        assert self._ledger(ledger) == ['stow: 1 added, 0 updated, 0 removed']

    def test_dry_run_records_would_be_links(self, world: dict[str, Path], tmp_path: Path) -> None:
        """
        Test that -n records the would-be change and links nothing
        """
        _pkg(world['repo'], 'demo', {'.democonf': 'x\n'})
        ledger = tmp_path / 'ledger'

        result = _stow(world, '-n', extra_env={'BOOTSTRAP_CHANGES_FILE': str(ledger)})
        assert result.returncode == 0, result.stderr
        assert self._ledger(ledger) == ['stow: 1 added, 0 updated, 0 removed']
        assert not (world['home'] / '.democonf').exists()

    def test_backups_are_recorded(self, world: dict[str, Path], tmp_path: Path) -> None:
        """
        Test that each backed-up file is recorded, followed by the links
        """
        _pkg(world['repo'], 'demo', {'.democonf': 'x\n'})
        (world['home'] / '.democonf').write_text('old\n', encoding='utf-8')
        ledger = tmp_path / 'ledger'

        result = _stow(world, '--backup-conflicts', extra_env={'BOOTSTRAP_CHANGES_FILE': str(ledger)})
        assert result.returncode == 0, result.stderr
        assert self._ledger(ledger) == ['stow: backed up ~/.democonf', 'stow: 1 added, 0 updated, 0 removed']
```

- [ ] **Step 2: Run them and watch them fail**

Run: `scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider tests/unit/test_stow_sh.py -k ChangeLedger`
Expected: FAIL (empty ledgers).

- [ ] **Step 3: Implement**

Replace

```bash
EFF_LEVEL="$LEVEL"
if [ "$SHOW_SUMMARY" = 1 ] && [ "$EFF_LEVEL" -lt 1 ]; then
    EFF_LEVEL=1
fi
```

with

```bash
# The summary and the bootstrap change ledger both read stow's verbose log, so it is always captured at level 1 or more
# (the captured log is only shown with -v / STOW_VERBOSE)
EFF_LEVEL="$LEVEL"
if [ "$EFF_LEVEL" -lt 1 ]; then
    EFF_LEVEL=1
fi
```

Replace `summarize()` with:

```bash
summarize() { # $1=log, $2=dry (1|0): print the net change (unless --no-summary) and record it in the change ledger
    local out
    out="$(printf '%s' "$1" | awk -v dry="$2" -f "$SUMMARIZER")"
    if [ "$SHOW_SUMMARY" = 1 ]; then
        printf '%s\n' "$out"
    fi
    case "$out" in
    'stow: no changes'*) ;;
    *) note_change "$(printf '%s\n' "$out" | tail -n 1)" ;;
    esac
}
```

In the dry-run backup loop, after `echo "stow: would back up existing $target -> $BACKUP_DIR/$target"` add
`note_change "stow: would back up ~/$target"`. In the real backup loop, after
`echo "stow: backed up existing $target -> $BACKUP_DIR/$target"` add `note_change "stow: backed up ~/$target"`.

In the header comment block, after the `# Env: STOW_VERBOSE=N …` line, add:
`# Changes are also recorded in the bootstrap change ledger (lib.sh note_change) when run under bootstrap.sh.`

- [ ] **Step 4: Run the tests**

Run: `scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider tests/unit/test_stow_sh.py tests/unit/test_stow_summary.py tests/integration/test_os_layout.py`
Expected: PASS; `git diff main -- tests/fixtures/os_layout` empty.

- [ ] **Step 5: Full suite, hooks, commit**

```bash
scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider
prek run --files stow.sh tests/unit/test_stow_sh.py
git add stow.sh tests/unit/test_stow_sh.py
git commit -m "feat(engine): record stow links and backups in the change ledger"
```

---

### Task 7: Brewfile — `docker`, `docker-compose`, `mermaid-cli` macOS-only

**Files:**
- Modify: `bootstrap/Brewfile`
- Modify: `tests/unit/test_brewfile.py` (`DARWIN_ONLY_FORMULAE`)
- Modify: `bootstrap/README.md` ("OS support" last sentence)

**Interfaces:** none (data change). The darwin goldens must not change: `bundle_list` sorts its output.

- [ ] **Step 1: Update the expectation first**

In `tests/unit/test_brewfile.py`:

```python
# Formulae that exist only on macOS, or that must not shadow the NAS's apt packages / need a desktop; they live inside
# the Brewfile's `if OS.mac?` block
DARWIN_ONLY_FORMULAE = frozenset({'docker', 'docker-compose', 'mas', 'mermaid-cli'})
```

(The Linux class only runs on Linux; on macOS this step cannot fail. The pytest (Linux) CI job is its gate.)

- [ ] **Step 2: Move the entries**

Delete `brew "docker"`, `brew "docker-compose"` and `brew "mermaid-cli"` from the main keep-sorted block. Replace the
comment and first line of the macOS block with:

```ruby
# macOS-only entries: the `mas` CLI, formulae that do not belong on the NAS, casks, fonts, and Mac App Store apps.
# Homebrew on Linux skips this block, so the NAS (Linuxbrew) installs every formula above it and nothing else.
if OS.mac?
  brew "mas"

  # The NAS uses apt's Docker CLI and Compose plugin (Linuxbrew is first on PATH and would shadow them); mermaid-cli's
  # Puppeteer/Chromium renderer needs desktop libraries a headless server lacks
  # keep-sorted start
  brew "docker"
  brew "docker-compose"
  brew "mermaid-cli"
  # keep-sorted end
```

- [ ] **Step 3: Prove darwin is unchanged**

Run: `scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider tests/unit/test_brewfile.py`
Expected: PASS on macOS (the darwin goldens match); `git diff main -- tests/fixtures/os_layout` empty.

- [ ] **Step 4: Document**

`bootstrap/README.md` "OS support", last sentence becomes: "Brewfile entries that exist only on macOS, or that must not
shadow the NAS's system packages, sit inside `if OS.mac?`."

- [ ] **Step 5: Full suite, hooks, commit**

```bash
scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider
prek run --files bootstrap/Brewfile bootstrap/README.md tests/unit/test_brewfile.py
git add bootstrap/Brewfile bootstrap/README.md tests/unit/test_brewfile.py
git commit -m "feat(brew): keep docker, docker-compose and mermaid-cli off Linux"
```

---

### Task 8: `setup.sh` change counter, guards, and summary line

**Files:**
- Modify: `vms/haos/setup.sh`
- Modify: `vms/haos/README.md` ("Fresh install" intro paragraph)
- Create: `tests/unit/test_haos_setup.py`

**Interfaces:**
- Produces: `setup.sh` prints `haos: changes=<N>` (plain, its own line) after step 6 in both modes; N counts every
  `run` call and every `write_if_changed` that writes (or would), plus the direct `iptables -I` path. Test-only env
  overrides: `HAOS_KVM_DEVICE` (default `/dev/kvm`), `HAOS_ETC_DIR` (default `/etc`), `HAOS_IMAGES_DIR` (default
  `/var/lib/libvirt/images`).

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_haos_setup.py`:

```python
"""
Unit tests for vms/haos/setup.sh --dry-run: change counting and the `haos: changes=N` line (stubbed host tools)
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SETUP     = REPO_ROOT / 'vms' / 'haos' / 'setup.sh'
BASH      = shutil.which('bash')

pytestmark = pytest.mark.skipif(BASH is None, reason='bash not installed')

# The two files setup.sh manages under /etc, exactly as it writes them (write_if_changed compares the content)
LIBVIRT_GUESTS = (
    '# Managed by dotfiles vms/haos/setup.sh\n'
    'ON_BOOT=ignore\n'
    'ON_SHUTDOWN=shutdown\n'
    'SHUTDOWN_TIMEOUT=300\n'
)
DOCKER_DROP_IN = (
    '# Managed by dotfiles vms/haos/setup.sh\n'
    '[Service]\n'
    "ExecStartPost=-/bin/sh -c 'iptables -w -C DOCKER-USER -i br0 -o br0 -j ACCEPT 2>/dev/null || "
    "iptables -w -I DOCKER-USER -i br0 -o br0 -j ACCEPT'\n"
)

# Stubs read flag files in $HAOS_TEST_STATE: each flag's presence makes the matching host fact true
STUBS: dict[str, str] = {
    'ip':          '[ -f "$HAOS_TEST_STATE/bridge" ] && echo "5: br0    inet 192.168.68.79/22 brd 192.168.71.255"\nexit 0\n',
    'dpkg-query':  '[ -f "$HAOS_TEST_STATE/pkgs" ] && printf "install ok installed"\nexit 0\n',
    'id':          'if [ -f "$HAOS_TEST_STATE/group" ]; then echo "tester sudo libvirt"; else echo "tester sudo"; fi\n',
    'df':          'printf "Avail\\n100G\\n"\n',
    'systemctl': (
        'case "$1" in\n'
        'is-enabled) [ -f "$HAOS_TEST_STATE/enabled-$3" ]; exit $? ;;\n'
        'is-active) [ -f "$HAOS_TEST_STATE/active-$3" ]; exit $? ;;\n'
        'list-unit-files) [ -f "$HAOS_TEST_STATE/docker" ]; exit $? ;;\n'
        'esac\n'
        'exit 0\n'
    ),
    'virsh': (
        'while [ "$1" = -r ] || [ "$1" = -c ]; do\n'
        '    if [ "$1" = -c ]; then shift; fi\n'
        '    shift\n'
        'done\n'
        'case "$1" in\n'
        'net-info) [ -f "$HAOS_TEST_STATE/net-default" ] || exit 1; printf "Active:         yes\\nAutostart:      yes\\n" ;;\n'
        'dominfo)\n'
        '    [ -f "$HAOS_TEST_STATE/vm" ] || exit 1\n'
        '    if [ -f "$HAOS_TEST_STATE/vm-autostart" ]; then echo "Autostart:      enable"; else echo "Autostart:      disable"; fi ;;\n'
        'domblklist) printf "Type   Device   Target   Source\\nfile   disk     sda      %s\\n" "$HAOS_IMAGES_DIR/haos.qcow2" ;;\n'
        'domstate) if [ -f "$HAOS_TEST_STATE/vm-running" ]; then echo running; else echo "shut off"; fi ;;\n'
        'esac\n'
        'exit 0\n'
    ),
}

# A host where setup.sh has already converged
CONVERGED = (
    'bridge',
    'pkgs',
    'group',
    'docker',
    'enabled-libvirtd.service',
    'enabled-libvirt-guests.service',
    'active-libvirt-guests.service',
    'vm',
    'vm-autostart',
    'vm-running',
)


@pytest.fixture
def host(tmp_path: Path) -> dict[str, str]:
    """
    Stubbed host tools first on PATH, relocated /etc, images dir and KVM device; returns the environment
    """
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    for name, body in STUBS.items():
        (bin_dir / name).write_text(f'#!/bin/sh\n{body}', encoding='utf-8')
        (bin_dir / name).chmod(0o755)

    for sub in ('state', 'etc', 'images'):
        (tmp_path / sub).mkdir()
    kvm = tmp_path / 'kvm'
    kvm.touch()

    return {
        **{key: value for key, value in os.environ.items() if not key.startswith(('HAOS_', 'BRIDGE'))},
        'PATH':            f'{bin_dir}:{os.environ["PATH"]}',
        'SUDO_USER':       'tester',
        'HAOS_TEST_STATE': str(tmp_path / 'state'),
        'HAOS_ETC_DIR':    str(tmp_path / 'etc'),
        'HAOS_IMAGES_DIR': str(tmp_path / 'images'),
        'HAOS_KVM_DEVICE': str(kvm),
    }


def _converge(host: dict[str, str], *, skip: tuple[str, ...] = ()) -> None:
    """
    Make the stubbed host converged, except for the flags in skip
    """
    state = Path(host['HAOS_TEST_STATE'])
    for flag in CONVERGED:
        if flag not in skip:
            (state / flag).touch()

    etc = Path(host['HAOS_ETC_DIR'])
    (etc / 'default').mkdir()
    (etc / 'default' / 'libvirt-guests').write_text(LIBVIRT_GUESTS, encoding='utf-8')
    drop_in = etc / 'systemd' / 'system' / 'docker.service.d'
    drop_in.mkdir(parents=True)
    (drop_in / '10-bridge-forward.conf').write_text(DOCKER_DROP_IN, encoding='utf-8')
    (Path(host['HAOS_IMAGES_DIR']) / 'haos.qcow2').touch()


def _dry_run(host: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """
    Run setup.sh --dry-run against the stubbed host
    """
    assert BASH is not None
    return subprocess.run([BASH, str(SETUP), '--dry-run'], capture_output=True, text=True, check=False, env=host)


class TestHaosChangeCount:
    """
    Tests for setup.sh's change counting
    """
    def test_converged_host_reports_zero(self, host: dict[str, str]) -> None:
        """
        Test that a converged host reports changes=0
        """
        _converge(host)

        result = _dry_run(host)
        assert result.returncode == 0, result.stderr
        assert 'haos: changes=0' in result.stdout.splitlines()

    @pytest.mark.parametrize(
        'missing',
        [
            'group',
            'active-libvirt-guests.service',
            'enabled-libvirtd.service',
            'vm-running',
            'vm-autostart',
        ],
    )
    def test_single_drift_reports_one(self, host: dict[str, str], missing: str) -> None:
        """
        Test that one unconverged fact is counted as exactly one change
        """
        _converge(host, skip=(missing,))

        result = _dry_run(host)
        assert result.returncode == 0, result.stderr
        assert 'haos: changes=1' in result.stdout.splitlines()

    def test_fresh_host_counts_without_writing(self, host: dict[str, str]) -> None:
        """
        Test that a fresh host reports changes and the dry run writes nothing
        """
        (Path(host['HAOS_TEST_STATE']) / 'bridge').touch()
        (Path(host['HAOS_TEST_STATE']) / 'docker').touch()

        result = _dry_run(host)
        assert result.returncode == 0, result.stderr

        counts = [line for line in result.stdout.splitlines() if line.startswith('haos: changes=')]
        assert len(counts) == 1
        assert int(counts[0].split('=', 1)[1]) > 0
        assert not any(Path(host['HAOS_ETC_DIR']).iterdir())

    def test_missing_bridge_fails_with_instructions(self, host: dict[str, str]) -> None:
        """
        Test that a missing bridge fails before any change, naming bridge.sh
        """
        result = _dry_run(host)
        assert result.returncode != 0
        assert 'run vms/haos/bridge.sh first' in result.stderr
```

- [ ] **Step 2: Run them and watch them fail**

Run: `scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider tests/unit/test_haos_setup.py`
Expected: FAIL (no summary line; `/dev/kvm` missing on macOS).

- [ ] **Step 3: Implement**

In `vms/haos/setup.sh`:

1. Header: after the `BRIDGE` override line, add:

   ```bash
   #
   # Test-only overrides (relocate the host paths this script checks; never set them on the NAS):
   #   HAOS_KVM_DEVICE, HAOS_ETC_DIR, HAOS_IMAGES_DIR
   #
   # Every run ends step 6 with a plain `haos: changes=N` line (under --dry-run: the changes a real run would make); the
   # NAS `haos` Ansible role keys its changed status off it.
   ```

2. Replace `IMAGES_DIR='/var/lib/libvirt/images'` with `IMAGES_DIR="${HAOS_IMAGES_DIR:-/var/lib/libvirt/images}"` and
   add below `LIBVIRT_URI`:

   ```bash
   ETC_DIR="${HAOS_ETC_DIR:-/etc}"
   KVM_DEVICE="${HAOS_KVM_DEVICE:-/dev/kvm}"
   ```

3. After `DRY_RUN=0` add:

   ```bash
   CHANGES=0     # mutations made (or, under --dry-run, that would be made); printed as `haos: changes=N`
   VM_STARTED=0  # 1 when this run defined or started the VM, so the address wait below is worth doing
   ```

4. In `run()`, add `CHANGES=$((CHANGES + 1))` as its first line. In `write_if_changed`, add
   `CHANGES=$((CHANGES + 1))` right after the `&& return 1` line.

5. Replace `[[ -e /dev/kvm ]] || die '/dev/kvm missing: …'` with
   `[[ -e "$KVM_DEVICE" ]] || die "${KVM_DEVICE} missing: enable SVM/VT-x in firmware and load kvm_amd/kvm_intel"`.

6. Replace `run systemctl enable --now libvirtd.service libvirt-guests.service` with:

   ```bash
   # Enabled is enough for libvirtd (socket activation starts it on demand); libvirt-guests must also be active, or its
   # shutdown hook will not run
   if systemctl is-enabled --quiet libvirtd.service && systemctl is-enabled --quiet libvirt-guests.service &&
       systemctl is-active --quiet libvirt-guests.service; then
       ok 'libvirtd and libvirt-guests enabled'
   else
       run systemctl enable --now libvirtd.service libvirt-guests.service
   fi
   ```

7. Replace the two `/etc/...` paths in the `write_if_changed` calls (and in the log lines that name them) with
   `"${ETC_DIR}/default/libvirt-guests"` and `"${ETC_DIR}/systemd/system/docker.service.d/10-bridge-forward.conf"`.

8. Replace `iptables -w -C $rule 2>/dev/null || iptables -w -I $rule` with:

   ```bash
           if ! iptables -w -C $rule 2>/dev/null; then
               iptables -w -I $rule
               CHANGES=$((CHANGES + 1))
           fi
   ```

   (keep the existing `# shellcheck disable=SC2086` directly above it).

9. In step 6, after `run virsh -c "$LIBVIRT_URI" start "$HAOS_NAME"` add `VM_STARTED=1`, and after the `virt-install`
   command add `VM_STARTED=1`.

9a. Replace `\s` with `[[:space:]]` in the three `grep -E`/`grep -qE` patterns (`^Active:\s+yes`,
    `^Autostart:\s+yes`, `^Autostart:\s+enable`): same meaning, and portable to the BSD grep the macOS test job uses.

10. Replace `[[ "$DRY_RUN" == 0 ]] || exit 0` with:

    ```bash
    printf 'haos: changes=%d\n' "$CHANGES"
    [[ "$DRY_RUN" == 0 ]] || exit 0
    ```

11. In the address report, make the wait conditional:

    ```bash
    # Wait (up to ~3 minutes) only when this run defined or started the VM; a running VM answers on the first attempt
    attempts=1
    if [[ "$VM_STARTED" == 1 ]]; then
        attempts=60
        log 'Waiting for the VM to report an address (first boot takes a minute or two)...'
    fi
    vm_ip=''
    for _ in $(seq 1 "$attempts"); do
    ```

    (replacing the old unconditional `log 'Waiting …'`, `vm_ip=''` and `for _ in $(seq 1 60); do`), and guard the final
    `log 'First boot downloads …'` with `if [[ "$VM_STARTED" == 1 ]]; then … fi`.

- [ ] **Step 4: Run the tests**

Run: `scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider tests/unit/test_haos_setup.py`
Expected: PASS. Also `bash -n vms/haos/setup.sh` and the prek `shellcheck` hook pass.

- [ ] **Step 5: Document**

`vms/haos/README.md`, "Fresh install" intro paragraph becomes: "Both scripts are idempotent and accept `--dry-run`,
which prints every mutating command without running it (and works without sudo). `setup.sh` ends with
`haos: changes=N`, the number of changes it made (or, under `--dry-run`, would make)."

- [ ] **Step 6: Full suite, hooks, commit**

```bash
scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider
prek run --files vms/haos/setup.sh vms/haos/README.md tests/unit/test_haos_setup.py
git add vms/haos/setup.sh vms/haos/README.md tests/unit/test_haos_setup.py
git commit -m "feat(haos): count changes in setup.sh and report haos: changes=N"
```

---

### Task 9: ansible-lint wrapper and configuration (not yet a gate)

**Files:**
- Create: `scripts/hooks/ansible-lint.sh` (mode 755)
- Create: `.ansible-lint-ignore`
- Modify: `.yamllint.yaml`, `.ansible-lint.yaml`

**Interfaces:**
- Produces: `scripts/hooks/ansible-lint.sh [ARGS...]` — runs ansible-lint 25.6.1 (via `uv-public.sh tool run`) on
  `playbooks/ roles/` from the repo root, offline, check-only, with a throwaway vault password file; exit status is
  ansible-lint's. Tasks 10–14 lint with it; Task 15 makes it a prek hook and a CI job.

- [ ] **Step 1: Write the wrapper**

```bash
#!/usr/bin/env bash
# Lint the NAS playbook and roles with ansible-lint (check only: never --fix). Used by the prek hook and the CI job.
#
# ansible.cfg points vault_password_file at vault_password.txt, which exists only on a provisioning machine; without it
# ansible-lint's syntax check aborts. A throwaway password file stands in, since linting decrypts nothing. --offline
# keeps ansible-lint from installing collections itself: install them first with
#   scripts/hooks/uv-public.sh run ansible-galaxy collection install -r roles/requirements.yml
set -euo pipefail

ANSIBLE_LINT_VERSION="25.6.1"

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
cd "$repo"

vault_pass="$(mktemp "${TMPDIR:-/tmp}/ansible-lint-vault.XXXXXX")"
trap 'rm -f "$vault_pass"' EXIT
printf 'unused\n' >"$vault_pass"

ANSIBLE_VAULT_PASSWORD_FILE="$vault_pass" "$repo/scripts/hooks/uv-public.sh" tool run \
    --from "ansible-lint==${ANSIBLE_LINT_VERSION}" ansible-lint --offline playbooks/ roles/ "$@"
```

`chmod 755 scripts/hooks/ansible-lint.sh`.

- [ ] **Step 2: Reconcile the configs**

`.yamllint.yaml`: replace the `comments-indentation:` block (level warning + ignore list) with

```yaml
  # ansible-lint refuses to run unless this rule is off
  comments-indentation: false
```

`.ansible-lint.yaml`: replace

```yaml
write_list:
  - all
```

with

```yaml
write_list:
  - none
```

and update the comment above it to say the repo never auto-fixes (`--fix` is not used; review findings by hand).

- [ ] **Step 3: Accept the findings that this sub-project deliberately leaves**

Create `.ansible-lint-ignore`:

```text
# ansible-lint findings accepted on purpose: `<path> <rule>`, then the reason.
roles/docker/defaults/main.yml var-naming[no-role-prefix]  # docker role: reworked by NAS sub-project 3
roles/docker/tasks/main.yml risky-file-permissions  # docker role: reworked by NAS sub-project 3
roles/docker/tasks/main.yml no-changed-when  # docker role: reworked by NAS sub-project 3
roles/docker/tasks/main.yml no-handler  # docker role: reworked by NAS sub-project 3
roles/docker/tasks/main.yml loop-var-prefix[missing]  # docker role: reworked by NAS sub-project 3
roles/samba/handlers/main.yml loop-var-prefix[missing]  # samba role: untouched here; fix with a NAS-verified change
roles/samba/tasks/main.yml loop-var-prefix[missing]  # samba role: untouched here; fix with a NAS-verified change
roles/debian/defaults/main.yml var-naming[no-role-prefix]  # systemd_allow_* are set in inventory host_vars
```

- [ ] **Step 4: Run it and check it changed nothing**

```bash
scripts/hooks/uv-public.sh run ansible-galaxy collection install -r roles/requirements.yml
scripts/hooks/ansible-lint.sh; echo "rc=$?"
git status --short
```

Expected: ansible-lint runs (no "incompatible custom yamllint configuration" error, no `internal-error` from the syntax
check), and **`git status` shows only this task's four files** — no rewritten roles. The remaining findings are exactly
those in `roles/debian/tasks`, `roles/zfs`, `roles/ssh`, `roles/zsh` (fixed or deleted by Tasks 10, 11 and 14). If any
role file was modified, ansible-lint is still auto-fixing: `git checkout -- roles playbooks`, add `--fix=none` to the
wrapper's command, and repeat. If the full-line comment in `.ansible-lint-ignore` is rejected, delete that line (the
trailing reasons stay). `prek run yamllint --all-files` must still pass with the relaxed rule.

- [ ] **Step 5: Commit**

```bash
prek run --files scripts/hooks/ansible-lint.sh .yamllint.yaml .ansible-lint.yaml .ansible-lint-ignore
git add scripts/hooks/ansible-lint.sh .yamllint.yaml .ansible-lint.yaml .ansible-lint-ignore
git commit -m "build(ansible): check-only ansible-lint wrapper and compatible lint config"
```

---

### Task 10: `debian` role — engine prerequisites, Linuxbrew prefix, idempotent sleep targets

**Files:**
- Modify: `roles/debian/defaults/main.yml`, `roles/debian/tasks/main.yml`, `roles/debian/README.md`

**Interfaces:**
- Produces: variables `systemd_allow_{sleep,suspend,hibernate,hybrid_sleep}` (unchanged names),
  `debian_sleep_targets`, `debian_engine_packages`, `debian_apt_packages` (renamed from `apt_packages`),
  `debian_linuxbrew_prefix`. `/home/linuxbrew` (root:root 0755) and `/home/linuxbrew/.linuxbrew`
  (`ansible_user`:`ansible_user` 0755) exist after the role.

- [ ] **Step 1: Confirm nothing else uses `apt_packages`**

Run: `git grep -n "apt_packages" -- roles playbooks` → only `roles/debian`. (The inventory's NAS vars set only
`docker_dir` and `systemd_allow_*`.)

- [ ] **Step 2: Write `roles/debian/defaults/main.yml`**

```yaml
---

# Sleep/hibernate configuration. The inventory overrides these, so they keep their unprefixed names.
systemd_allow_sleep: true
systemd_allow_suspend: true
systemd_allow_hibernate: true
systemd_allow_hybrid_sleep: true

# Each systemd sleep target and whether it may run (masked when not)
debian_sleep_targets:
  - {unit: sleep.target, allow: "{{ systemd_allow_sleep }}"}
  - {unit: suspend.target, allow: "{{ systemd_allow_suspend }}"}
  - {unit: hibernate.target, allow: "{{ systemd_allow_hibernate }}"}
  - {unit: hybrid-sleep.target, allow: "{{ systemd_allow_hybrid_sleep }}"}

# What the stow engine needs before it can run: Homebrew's Linux build requirements plus zsh, git and python3.
# bootstrap/00-preflight.sh checks for these and names this role as the fix.
debian_engine_packages:
  - build-essential
  - procps
  - curl
  - file
  - git
  - zsh
  - python3

# Other system packages
debian_apt_packages:
  - fzf
  - exfat-fuse

# Homebrew's Linux prefix: created here (that needs root) and owned by the user, so the engine installs Homebrew there
# without sudo
debian_linuxbrew_prefix: /home/linuxbrew/.linuxbrew
```

- [ ] **Step 3: Write `roles/debian/tasks/main.yml`**

```yaml
---
# Sleep targets are masked with systemctl because the systemd module's `masked` did not take effect on them. Reading
# each state first keeps a converged host at changed=0.
- name: Read sleep target states
  ansible.builtin.command:
    argv: [systemctl, is-enabled, "{{ debian_sleep_target.unit }}"]
  loop: "{{ debian_sleep_targets }}"
  loop_control:
    loop_var: debian_sleep_target
    label: "{{ debian_sleep_target.unit }}"
  register: debian_sleep_target_states
  changed_when: false
  failed_when: false
  check_mode: false

# `is-enabled` prints "masked" for a masked unit; act only where that disagrees with the unit's allow flag
- name: Mask or unmask sleep targets
  become: true
  ansible.builtin.command:
    argv:
      - systemctl
      - "{{ 'unmask' if debian_target_state.debian_sleep_target.allow | bool else 'mask' }}"
      - "{{ debian_target_state.debian_sleep_target.unit }}"
  loop: "{{ debian_sleep_target_states.results }}"
  loop_control:
    loop_var: debian_target_state
    label: "{{ debian_target_state.debian_sleep_target.unit }}"
  when: (debian_target_state.stdout == 'masked') == (debian_target_state.debian_sleep_target.allow | bool)
  changed_when: true

- name: Install apt packages
  become: true
  ansible.builtin.apt:
    name: "{{ debian_engine_packages + debian_apt_packages }}"

- name: Create the Homebrew parent directory
  become: true
  ansible.builtin.file:
    path: "{{ debian_linuxbrew_prefix | dirname }}"
    state: directory
    owner: root
    group: root
    mode: "0755"

- name: Create the Homebrew prefix, owned by the user
  become: true
  ansible.builtin.file:
    path: "{{ debian_linuxbrew_prefix }}"
    state: directory
    owner: "{{ ansible_user }}"
    group: "{{ ansible_user }}"
    mode: "0755"
```

- [ ] **Step 4: Lint and syntax-check**

```bash
scripts/hooks/ansible-lint.sh
printf 'unused\n' > "$TMPDIR/vault-dummy"
ANSIBLE_VAULT_PASSWORD_FILE="$TMPDIR/vault-dummy" scripts/hooks/uv-public.sh run ansible-playbook --syntax-check -i localhost, playbooks/nas_bootstrap.yml
```

Expected: no findings left under `roles/debian/`; syntax check prints `playbook: playbooks/nas_bootstrap.yml`.

- [ ] **Step 5: README**

Rewrite `roles/debian/README.md`:

```markdown
[Project Root](../../README.md) > [Roles](../README.md) > **debian**

# debian

Base Debian configuration for the NAS: system packages (including everything the stow engine needs before it can run),
the Linuxbrew prefix, and the systemd sleep targets.

## Tasks

| Task                     | Effect                                                                                              |
| ------------------------ | --------------------------------------------------------------------------------------------------- |
| Sleep targets            | Masks or unmasks `sleep`, `suspend`, `hibernate`, `hybrid-sleep`; reads each state first (idempotent) |
| apt packages             | `debian_engine_packages` + `debian_apt_packages`                                                    |
| Linuxbrew prefix         | `/home/linuxbrew` (root, 0755) and `debian_linuxbrew_prefix` owned by `ansible_user`, so the engine's `50-brew` installs Homebrew without sudo |

## Variables

| Variable                     | Default                       | Purpose                                                                 |
| ---------------------------- | ----------------------------- | ----------------------------------------------------------------------- |
| `systemd_allow_sleep` etc.   | `true`                        | Whether each sleep target may run; overridden in the inventory          |
| `debian_engine_packages`     | `build-essential procps curl file git zsh python3` | Engine prerequisites checked by `bootstrap/00-preflight.sh` |
| `debian_apt_packages`        | `fzf exfat-fuse`              | Other packages                                                          |
| `debian_linuxbrew_prefix`    | `/home/linuxbrew/.linuxbrew`  | Homebrew's Linux prefix                                                 |
```

- [ ] **Step 6: Idempotency review**

Dispatch the `ansible-idempotency-reviewer` agent on `git diff -- roles/debian` (prompt: "Review this change to
roles/debian for idempotency, check-mode behaviour, and repo conventions; the host is Debian 12 with sudo via the
vault-supplied become password"). Fix Critical/Important findings and re-run Step 4.

- [ ] **Step 7: Commit**

```bash
prek run --files roles/debian/defaults/main.yml roles/debian/tasks/main.yml roles/debian/README.md
git add roles/debian
git commit -m "feat(ansible): debian role installs engine prerequisites and the Linuxbrew prefix idempotently"
```

---

### Task 11: `zfs` role — idempotent `contrib` and architecture probe

**Files:**
- Modify: `roles/zfs/tasks/main.yml`, `roles/zfs/README.md`

**Interfaces:**
- Produces: registers `zfs_contrib_check`, `zfs_contrib_added`, `zfs_dpkg_architecture` (the old global
  `dpkg_print_architecture` / `deb_architecture` names are no longer set here; the docker role sets its own).

- [ ] **Step 1: Write `roles/zfs/tasks/main.yml`**

```yaml
---
- name: Install zfs
  block:
    # Matches one-line sources ("deb … main contrib") and deb822 sources ("Components: main contrib")
    - name: Check for the contrib component in the apt sources
      ansible.builtin.command:
        argv:
          - grep
          - -rqsE
          - '^(deb(-src)?[[:space:]].*|Components:.*)[[:space:]]contrib([[:space:]]|$)'
          - /etc/apt/sources.list
          - /etc/apt/sources.list.d
      register: zfs_contrib_check
      changed_when: false
      failed_when: false
      check_mode: false

    - name: Add the Debian contrib apt component
      become: true
      ansible.builtin.command:
        argv: [apt-add-repository, contrib, -y]
      register: zfs_contrib_added
      changed_when: true
      when: zfs_contrib_check.rc != 0

    - name: Update apt package index
      become: true
      ansible.builtin.apt:
        update_cache: true
      when: zfs_contrib_added is changed

    - name: Read the Debian architecture
      ansible.builtin.command:
        argv: [dpkg, --print-architecture]
      register: zfs_dpkg_architecture
      changed_when: false
      check_mode: false

    - name: Install zfs dependencies
      become: true
      ansible.builtin.apt:
        pkg:
          - "linux-headers-{{ zfs_dpkg_architecture.stdout }}"
          - "linux-image-{{ zfs_dpkg_architecture.stdout }}"
          - dpkg-dev
          - zfs-dkms
          - zfsutils-linux
```

- [ ] **Step 2: Lint and syntax-check** (same commands as Task 10 Step 4). Expected: no findings under `roles/zfs/`.

- [ ] **Step 3: README**

Rewrite `roles/zfs/README.md`:

```markdown
[Project Root](../../README.md) > [Roles](../README.md) > **zfs**

# zfs

Installs ZFS on Debian: enables the `contrib` apt component when it is missing, then installs the kernel headers and
image for the host architecture plus `zfs-dkms` and `zfsutils-linux`. Pool import and datasets are not managed here.
```

- [ ] **Step 4: Idempotency review** — dispatch `ansible-idempotency-reviewer` on `git diff -- roles/zfs`; fix
  Critical/Important findings.

- [ ] **Step 5: Commit**

```bash
prek run --files roles/zfs/tasks/main.yml roles/zfs/README.md
git add roles/zfs
git commit -m "fix(ansible): zfs role adds contrib only when missing and probes the architecture read-only"
```

---

### Task 12: `profiles/nas` and the `dotfiles` role

**Files:**
- Create: `profiles/nas/README.md`; modify `profiles/README.md`
- Create: `roles/dotfiles/defaults/main.yml`, `roles/dotfiles/tasks/main.yml`, `roles/dotfiles/README.md`
- Modify: `playbooks/nas_bootstrap.yml` (play `vars:`; include `dotfiles` as the last role for now)
- Create: `tests/unit/test_nas_playbook.py`

**Interfaces:**
- Consumes: the driver's `bootstrap: changes=N` line (Task 2); `BOOTSTRAP_NONINTERACTIVE` (Task 1).
- Produces: play variable `dotfiles_repo_dir: "{{ ansible_facts['user_dir'] }}/dotfiles-personal"`; role variables
  `dotfiles_repo_url`, `dotfiles_repo_push_url`, `dotfiles_repo_version` (default `main`), `dotfiles_overlays`,
  `dotfiles_login_shell` (default `/bin/zsh`), `dotfiles_bootstrap_preview` (default `false`).

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_nas_playbook.py`:

```python
"""
Structural tests for the NAS playbook and its roles (no NAS needed): syntax, wiring, and the summary-line contract
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PLAYBOOK  = REPO_ROOT / 'playbooks' / 'nas_bootstrap.yml'
ROLES     = REPO_ROOT / 'roles'
LIB       = REPO_ROOT / 'bootstrap' / 'lib.sh'

ANSIBLE_PLAYBOOK = Path(sys.executable).parent / 'ansible-playbook'


def _role_defaults(role: str) -> dict[str, object]:
    """
    Load a role's defaults/main.yml
    """
    data = yaml.safe_load((ROLES / role / 'defaults' / 'main.yml').read_text(encoding='utf-8'))
    assert isinstance(data, dict)
    return data


class TestPlaybookSyntax:
    """
    Tests for the playbook as Ansible parses it
    """
    @pytest.mark.skipif(not ANSIBLE_PLAYBOOK.exists(), reason='ansible-playbook not in this environment')
    def test_syntax_check_passes(self, tmp_path: Path) -> None:
        """
        Test that ansible-playbook --syntax-check accepts the playbook (with a throwaway vault password file)
        """
        vault = tmp_path / 'vault-pass'
        vault.write_text('unused\n', encoding='utf-8')

        result = subprocess.run(
            [str(ANSIBLE_PLAYBOOK), '--syntax-check', '-i', 'localhost,', str(PLAYBOOK)],
            capture_output=True,
            text=True,
            check=False,
            cwd=REPO_ROOT,
            env={**os.environ, 'ANSIBLE_VAULT_PASSWORD_FILE': str(vault)},
            timeout=300,
        )
        assert result.returncode == 0, result.stdout + result.stderr


class TestDotfilesRole:
    """
    Tests for the dotfiles role's wiring
    """
    def test_overlay_is_the_nas_profile(self) -> None:
        """
        Test that the role registers profiles/nas and that the profile exists in the repo
        """
        assert _role_defaults('dotfiles')['dotfiles_overlays'] == ['{{ dotfiles_repo_dir }}/profiles/nas']
        assert (REPO_ROOT / 'profiles' / 'nas' / 'README.md').is_file()

    def test_nas_profile_is_a_valid_layer(self, tmp_path: Path) -> None:
        """
        Test that the engine accepts profiles/nas as an overlay
        """
        registry = tmp_path / 'overlays'
        registry.write_text(f'{REPO_ROOT / "profiles" / "nas"}\n', encoding='utf-8')

        result = subprocess.run(
            ['bash', '-c', f'source "{LIB}"; dotfiles_layers'],
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, 'DOTFILES_OVERLAYS_FILE': str(registry), 'HOME': str(tmp_path)},
            timeout=60,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.splitlines()[-1] == str((REPO_ROOT / 'profiles' / 'nas').resolve())

    def test_summary_line_contract(self) -> None:
        """
        Test that the role matches the exact line the driver prints
        """
        driver = (REPO_ROOT / 'bootstrap' / 'bootstrap.sh').read_text(encoding='utf-8')
        tasks  = (ROLES / 'dotfiles' / 'tasks' / 'main.yml').read_text(encoding='utf-8')
        assert "printf 'bootstrap: changes=%d\\n'" in driver
        assert "'bootstrap: changes=0'" in tasks
        assert "'^bootstrap: changes=[0-9]+$'" in tasks

    def test_play_defines_the_repo_dir(self) -> None:
        """
        Test that the play defines dotfiles_repo_dir for every role that needs it
        """
        play = yaml.safe_load(PLAYBOOK.read_text(encoding='utf-8'))[0]
        assert play['vars']['dotfiles_repo_dir'] == "{{ ansible_facts['user_dir'] }}/dotfiles-personal"
```

- [ ] **Step 2: Run them and watch them fail**

Run: `scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider tests/unit/test_nas_playbook.py`
Expected: `TestDotfilesRole` FAILS (no role, no profile, no play var); the syntax check passes.

- [ ] **Step 3: Create the profile**

`profiles/nas/README.md`:

```markdown
[Project Root](../../README.md) > [Profiles](../README.md) > **nas**

# nas

Overlay for the home NAS (Debian with Linuxbrew). It follows the
[overlay contract](../../bootstrap/README.md#overlay-contract) and contributes nothing yet: the NAS runs the base layer
unchanged, the same dev environment as the Macs. NAS-only stages, `Brewfile` entries, or `repos.txt` lines go here when
they are needed.

## Registration

The NAS [`dotfiles`](../../roles/dotfiles/README.md) Ansible role writes the overlays registry
(`~/.config/dotfiles/overlays`) with this directory as its only entry and owns that file; edits made on the NAS are
overwritten on the next provisioning run.
```

`profiles/README.md` table: add the row `| [`nas`](nas/README.md) | Overlay for the home NAS (registered by the `dotfiles` Ansible role) |`.

`git add profiles/nas/README.md` before running the full suite (`test_stow_tree.py`).

- [ ] **Step 4: Create the role**

`roles/dotfiles/defaults/main.yml`:

```yaml
---
# dotfiles_repo_dir (the clone path) is a play variable in playbooks/nas_bootstrap.yml, shared with the haos role

# Fetch over HTTPS (public repo: works before any SSH key is registered with GitHub); push over SSH
dotfiles_repo_url: https://github.com/connormason/dotfiles.git
dotfiles_repo_push_url: git@github.com:connormason/dotfiles.git
dotfiles_repo_version: main

# Overlay roots the engine layers on top of the base; written to the overlays registry, which this role owns
dotfiles_overlays:
  - "{{ dotfiles_repo_dir }}/profiles/nas"

# Login shell for ansible_user
dotfiles_login_shell: /bin/zsh

# true: run the engine with --dry-run even in a real play (first rollout: clone and register, then preview $HOME)
dotfiles_bootstrap_preview: false
```

`roles/dotfiles/tasks/main.yml`:

```yaml
---
- name: Require the clone path
  ansible.builtin.assert:
    that:
      - dotfiles_repo_dir is defined
      - dotfiles_repo_dir | length > 0
    fail_msg: dotfiles_repo_dir (the NAS clone path) must be set; playbooks/nas_bootstrap.yml defines it for the play

- name: Look for an existing clone
  ansible.builtin.stat:
    path: "{{ dotfiles_repo_dir }}/.git"
  register: dotfiles_clone

# The git module's update resets the checkout to the remote branch. Refuse when that would lose work: uncommitted
# changes to tracked files, or a HEAD that exists on no remote-tracking branch (commits made only on the NAS). A clean
# checkout of another pushed branch is safe to switch.
- name: Read uncommitted changes in the clone
  ansible.builtin.command:  # noqa: command-instead-of-module (read-only status the git module cannot report)
    argv: [git, -C, "{{ dotfiles_repo_dir }}", status, --porcelain, --untracked-files=no]
  register: dotfiles_clone_status
  changed_when: false
  check_mode: false
  when: dotfiles_clone.stat.exists

- name: Read the remote branches that contain HEAD
  ansible.builtin.command:
    argv: [git, -C, "{{ dotfiles_repo_dir }}", branch, -r, --contains, HEAD]
  register: dotfiles_clone_remote
  changed_when: false
  failed_when: false
  check_mode: false
  when: dotfiles_clone.stat.exists

- name: Refuse to update a clone with local work
  ansible.builtin.assert:
    that:
      - dotfiles_clone_status.stdout | length == 0
      - dotfiles_clone_remote.rc == 0
      - dotfiles_clone_remote.stdout | length > 0
    fail_msg: >-
      {{ dotfiles_repo_dir }} has local work that updating would discard (uncommitted changes:
      {{ dotfiles_clone_status.stdout_lines }}; remote branches containing HEAD: {{ dotfiles_clone_remote.stdout_lines }}).
      Commit and push it, or discard it, then re-run. The clone was not touched.
  when: dotfiles_clone.stat.exists

- name: Clone or update the dotfiles repository
  ansible.builtin.git:
    repo: "{{ dotfiles_repo_url }}"
    dest: "{{ dotfiles_repo_dir }}"
    version: "{{ dotfiles_repo_version }}"
    update: true

- name: Look for the engine
  ansible.builtin.stat:
    path: "{{ dotfiles_repo_dir }}/bootstrap/bootstrap.sh"
  register: dotfiles_engine

- name: Read the push URL
  ansible.builtin.command:  # noqa: command-instead-of-module (git config has no builtin module)
    argv: [git, -C, "{{ dotfiles_repo_dir }}", config, --get, remote.origin.pushurl]
  register: dotfiles_push_url
  changed_when: false
  failed_when: dotfiles_push_url.rc not in [0, 1]
  check_mode: false
  when: dotfiles_engine.stat.exists

- name: Push over SSH
  ansible.builtin.command:  # noqa: command-instead-of-module (git config has no builtin module)
    argv: [git, -C, "{{ dotfiles_repo_dir }}", config, remote.origin.pushurl, "{{ dotfiles_repo_push_url }}"]
  changed_when: true
  when:
    - dotfiles_engine.stat.exists
    - dotfiles_push_url.stdout != dotfiles_repo_push_url

- name: Create the engine config directory
  ansible.builtin.file:
    path: "{{ ansible_facts['user_dir'] }}/.config/dotfiles"
    state: directory
    mode: "0755"

- name: Register the engine overlays
  ansible.builtin.copy:
    dest: "{{ ansible_facts['user_dir'] }}/.config/dotfiles/overlays"
    content: |
      # Managed by Ansible (roles/dotfiles); edits are overwritten on the next provisioning run
      {% for overlay in dotfiles_overlays %}
      {{ overlay }}
      {% endfor %}
    mode: "0644"

- name: Set the login shell
  become: true
  ansible.builtin.user:
    name: "{{ ansible_user }}"
    shell: "{{ dotfiles_login_shell }}"

- name: Report the skipped engine preview
  ansible.builtin.debug:
    msg: "{{ dotfiles_repo_dir }} is not cloned yet, so there is no engine to preview; a real run clones it first"
  when: not dotfiles_engine.stat.exists

# As the connecting user: the engine owns $HOME and never uses sudo on Linux. Check mode (and the preview variable) map
# to the engine's --dry-run, which is read-only and so runs even under --check. Changed status comes from the driver's
# final `bootstrap: changes=N` line; a run without exactly one such line is a failure.
- name: Run the bootstrap engine
  ansible.builtin.command:
    argv: >-
      {{ [dotfiles_repo_dir ~ '/bootstrap/bootstrap.sh']
         + (['--dry-run'] if (ansible_check_mode or dotfiles_bootstrap_preview | bool) else []) }}
  environment:
    BOOTSTRAP_NONINTERACTIVE: "1"
  register: dotfiles_bootstrap
  check_mode: false
  changed_when: "'bootstrap: changes=0' not in dotfiles_bootstrap.stdout_lines"
  failed_when: >-
    dotfiles_bootstrap.rc != 0 or
    (dotfiles_bootstrap.stdout_lines | select('match', '^bootstrap: changes=[0-9]+$') | list | length) != 1
  when: dotfiles_engine.stat.exists
```

If ansible-lint or Ansible rejects the templated `argv` (a folded string that evaluates to a list), split the task in
two with complementary `when:` conditions (`dotfiles_bootstrap_dry_run` true / false, from a preceding `set_fact` of
`ansible_check_mode or dotfiles_bootstrap_preview | bool`), each with a literal `argv` list and the same
`changed_when`/`failed_when`, registering `dotfiles_bootstrap_real` / `dotfiles_bootstrap_dry`. Prefer the single task
if it passes.

`roles/dotfiles/README.md`:

```markdown
[Project Root](../../README.md) > [Roles](../README.md) > **dotfiles**

# dotfiles

Hands the NAS user's `$HOME` to the stow engine, the same one the Macs use: clones this repository, registers the
[`profiles/nas`](../../profiles/nas/README.md) overlay, sets the login shell, and runs
[`bootstrap/bootstrap.sh`](../../bootstrap/README.md) as the user. Root-level prerequisites (Homebrew build packages,
the Linuxbrew prefix) come from the [`debian`](../debian/README.md) role, which must run first.

## Tasks

| Step               | Effect                                                                                                                  |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------- |
| Safety check       | Fails, touching nothing, if the clone has uncommitted changes to tracked files or a `HEAD` that is on no remote branch  |
| Clone / update     | `ansible.builtin.git` from `dotfiles_repo_url` at `dotfiles_repo_version`; `remote.origin.pushurl` set to the SSH URL |
| Overlay registry   | Writes `~/.config/dotfiles/overlays` from `dotfiles_overlays` (the role owns the file)                                 |
| Login shell        | `dotfiles_login_shell` for `ansible_user` (root)                                                                        |
| Engine             | `bootstrap.sh` with `BOOTSTRAP_NONINTERACTIVE=1`; changed unless its last line is `bootstrap: changes=0`               |

The engine's `95-dotfiles` stage moves pre-existing dotfiles that block a link into `~/.dotfiles-backup/<timestamp>/`.
With `BOOTSTRAP_NONINTERACTIVE=1`, `20-ssh-key` generates a key if needed and prints it for registration instead of
waiting for confirmation.

## Check mode and preview

Under `--check`, the engine runs with `--dry-run` (read-only) and the task reports whether a real run would change
anything; it is skipped when the clone does not exist yet. `-e dotfiles_bootstrap_preview=true` runs `--dry-run` in a
real play: the clone, registry, and login shell are applied, `$HOME` is only previewed.

## Variables

| Variable                     | Default                                         | Purpose                                         |
| ---------------------------- | ----------------------------------------------- | ----------------------------------------------- |
| `dotfiles_repo_dir`          | play variable: `~/dotfiles-personal`            | Clone path (shared with the `haos` role)        |
| `dotfiles_repo_url`          | `https://github.com/connormason/dotfiles.git`   | Fetch URL                                       |
| `dotfiles_repo_push_url`     | `git@github.com:connormason/dotfiles.git`       | Push URL                                        |
| `dotfiles_repo_version`      | `main`                                          | Branch to check out                             |
| `dotfiles_overlays`          | `[<dotfiles_repo_dir>/profiles/nas]`            | Overlays registry content                       |
| `dotfiles_login_shell`       | `/bin/zsh`                                      | Login shell                                     |
| `dotfiles_bootstrap_preview` | `false`                                         | Preview the engine (`--dry-run`) in a real play |
```

- [ ] **Step 5: Wire it into the playbook**

In `playbooks/nas_bootstrap.yml`, add after `hosts: nas`:

```yaml
  vars:
    # The NAS clone of this repository: the dotfiles role clones it, the haos role runs vms/haos/setup.sh from it
    dotfiles_repo_dir: "{{ ansible_facts['user_dir'] }}/dotfiles-personal"
```

and append, after the `zsh` include (Task 14 removes the retired roles and settles the order):

```yaml
    # $HOME: clone the repo, register profiles/nas, login shell, run the stow engine as the user
    - include_role:
        name: roles/dotfiles
        apply:
          tags: dotfiles
      tags:
        - dotfiles
        - configfile
```

- [ ] **Step 6: Run the tests, lint**

```bash
scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider tests/unit/test_nas_playbook.py
scripts/hooks/ansible-lint.sh
```

Expected: PASS; no findings under `roles/dotfiles/` or `playbooks/`.

- [ ] **Step 7: Idempotency review** — dispatch `ansible-idempotency-reviewer` on `git diff -- roles/dotfiles
  playbooks/nas_bootstrap.yml` with this context: "Runs over SSH as the NAS user; `bootstrap.sh` is idempotent and
  prints `bootstrap: changes=N` last; must report changed=0 on a converged host and be safe under --check." Fix
  Critical/Important findings.

- [ ] **Step 8: Full suite, hooks, commit**

```bash
git add profiles/nas/README.md profiles/README.md roles/dotfiles playbooks/nas_bootstrap.yml tests/unit/test_nas_playbook.py
scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider
prek run --files profiles/nas/README.md profiles/README.md roles/dotfiles/defaults/main.yml roles/dotfiles/tasks/main.yml roles/dotfiles/README.md playbooks/nas_bootstrap.yml tests/unit/test_nas_playbook.py
git commit -m "feat(ansible): dotfiles role hands the NAS home directory to the stow engine"
```

---

### Task 13: `haos` role

**Files:**
- Create: `roles/haos/defaults/main.yml`, `roles/haos/tasks/main.yml`, `roles/haos/README.md`
- Modify: `playbooks/nas_bootstrap.yml` (include `haos` after `dotfiles`)
- Modify: `vms/haos/README.md` ("Fresh install" step 2, "Re-bootstrapping a wiped NAS")
- Test: `tests/unit/test_nas_playbook.py`

**Interfaces:**
- Consumes: play variable `dotfiles_repo_dir` (Task 12); `haos: changes=N` (Task 8).
- Produces: role variables `haos_bridge` (default `br0`), `haos_setup_script` (default
  `"{{ dotfiles_repo_dir }}/vms/haos/setup.sh"`).

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_nas_playbook.py`:

```python
class TestHaosRole:
    """
    Tests for the haos role's wiring
    """
    def test_runs_the_repo_script(self) -> None:
        """
        Test that the role runs vms/haos/setup.sh from the clone and that the script exists
        """
        assert _role_defaults('haos')['haos_setup_script'] == '{{ dotfiles_repo_dir }}/vms/haos/setup.sh'
        assert (REPO_ROOT / 'vms' / 'haos' / 'setup.sh').is_file()

    def test_never_runs_bridge_sh(self) -> None:
        """
        Test that no role task executes bridge.sh (it blips the network and would cut the Ansible session)
        """
        tasks = yaml.safe_load((ROLES / 'haos' / 'tasks' / 'main.yml').read_text(encoding='utf-8'))
        for task in tasks:
            for module in ('ansible.builtin.command', 'ansible.builtin.shell', 'ansible.builtin.script'):
                assert 'bridge.sh' not in str(task.get(module, ''))

    def test_summary_line_contract(self) -> None:
        """
        Test that the role matches the exact line setup.sh prints
        """
        setup = (REPO_ROOT / 'vms' / 'haos' / 'setup.sh').read_text(encoding='utf-8')
        tasks = (ROLES / 'haos' / 'tasks' / 'main.yml').read_text(encoding='utf-8')
        assert "printf 'haos: changes=%d\\n'" in setup
        assert "'haos: changes=0'" in tasks
        assert "'^haos: changes=[0-9]+$'" in tasks
```

Run: `scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider tests/unit/test_nas_playbook.py -k Haos` → FAIL.

- [ ] **Step 2: Create the role**

`roles/haos/defaults/main.yml`:

```yaml
---
# LAN bridge the VM attaches to. vms/haos/bridge.sh creates it, never this role: it blips the network.
haos_bridge: br0

# The VM provisioning script, run from the NAS clone (dotfiles_repo_dir is a play variable)
haos_setup_script: "{{ dotfiles_repo_dir }}/vms/haos/setup.sh"
```

`roles/haos/tasks/main.yml`:

```yaml
---
- name: Read the LAN bridge's IPv4 address
  ansible.builtin.command:
    argv: [ip, -4, -o, addr, show, dev, "{{ haos_bridge }}"]
  register: haos_bridge_addr
  changed_when: false
  failed_when: false
  check_mode: false

- name: Require the LAN bridge
  ansible.builtin.assert:
    that:
      - haos_bridge_addr.stdout | length > 0
    fail_msg: >-
      {{ haos_bridge }} has no IPv4 address. Create it from the NAS console or inside tmux, since the network blips for a
      few seconds and would cut an SSH session: sudo {{ dotfiles_repo_dir }}/vms/haos/bridge.sh — then re-run with
      --tags haos. See vms/haos/README.md.

- name: Look for the provisioning script
  ansible.builtin.stat:
    path: "{{ haos_setup_script }}"
  register: haos_setup

- name: Require the provisioning script
  ansible.builtin.assert:
    that:
      - haos_setup.stat.exists
    fail_msg: "{{ haos_setup_script }} is missing; the dotfiles role clones the repository (run --tags dotfiles first)"
  when: not ansible_check_mode

- name: Report the skipped setup preview
  ansible.builtin.debug:
    msg: "{{ haos_setup_script }} is not cloned yet, so there is nothing to preview"
  when: not haos_setup.stat.exists

# setup.sh is idempotent and, with --dry-run, read-only, so check mode runs it too. SUDO_USER (set by become) is the
# user it adds to the libvirt group. Changed status comes from its `haos: changes=N` line.
- name: Provision the Home Assistant OS VM
  become: true
  ansible.builtin.command:
    argv: "{{ [haos_setup_script] + (['--dry-run'] if ansible_check_mode else []) }}"
  environment:
    BRIDGE: "{{ haos_bridge }}"
  register: haos_setup_run
  check_mode: false
  changed_when: "'haos: changes=0' not in haos_setup_run.stdout_lines"
  failed_when: >-
    haos_setup_run.rc != 0 or
    (haos_setup_run.stdout_lines | select('match', '^haos: changes=[0-9]+$') | list | length) != 1
  when: haos_setup.stat.exists
```

`roles/haos/README.md`:

```markdown
[Project Root](../../README.md) > [Roles](../README.md) > **haos**

# haos

Runs [`vms/haos/setup.sh`](../../vms/haos/README.md) from the NAS clone to converge the Home Assistant OS VM (KVM
packages, libvirt settings, the Docker bridge exemption, the VM itself). The script stays the implementation; the role
only checks preconditions and maps Ansible's modes onto it.

| Behaviour     | Detail                                                                                                         |
| ------------- | -------------------------------------------------------------------------------------------------------------- |
| LAN bridge    | Fails with instructions when `haos_bridge` has no IPv4 address. It never runs `bridge.sh`, which blips the network |
| Changed       | From the script's `haos: changes=N` line                                                                        |
| Check mode    | Runs `setup.sh --dry-run` (read-only)                                                                           |
| Depends on    | The [`dotfiles`](../dotfiles/README.md) role, for the clone at `dotfiles_repo_dir`                              |

## Variables

| Variable            | Default                                   | Purpose                  |
| ------------------- | ----------------------------------------- | ------------------------ |
| `haos_bridge`       | `br0`                                     | Bridge the VM attaches to |
| `haos_setup_script` | `<dotfiles_repo_dir>/vms/haos/setup.sh`   | Script to run            |
```

- [ ] **Step 3: Wire it into the playbook** — append after the `dotfiles` include:

```yaml
    # Home Assistant OS VM: preconditions, then vms/haos/setup.sh from the clone (never bridge.sh)
    - include_role:
        name: roles/haos
        apply:
          tags: haos
      tags:
        - haos
        - configfile
```

- [ ] **Step 4: Update `vms/haos/README.md`**

- "Fresh install" step 2: "**Create and boot the VM** with `sudo vms/haos/setup.sh`, or let the NAS playbook do it:
  its `haos` role runs `setup.sh` (and fails with these instructions while `br0` is missing)." Keep the rest of the
  step's text.
- "Re-bootstrapping a wiped NAS" becomes:
  1. `./nas_bootstrap.sh` (system roles, the stow engine in `$HOME`, and the `haos` role, which stops at the missing
     `br0` with instructions).
  2. `sudo ~/dotfiles-personal/vms/haos/bridge.sh` from the console or `tmux`, then re-run the playbook with
     `--tags haos` (or `sudo vms/haos/setup.sh` by hand).
  3. and 4. unchanged.

- [ ] **Step 5: Tests, lint, review**

```bash
scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider tests/unit/test_nas_playbook.py
scripts/hooks/ansible-lint.sh
```

Dispatch `ansible-idempotency-reviewer` on `git diff -- roles/haos playbooks/nas_bootstrap.yml` ("becomes root; must
never run bridge.sh; setup.sh prints `haos: changes=N`; safe under --check"). Fix Critical/Important findings.

- [ ] **Step 6: Full suite, hooks, commit**

```bash
scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider
prek run --files roles/haos/defaults/main.yml roles/haos/tasks/main.yml roles/haos/README.md playbooks/nas_bootstrap.yml vms/haos/README.md tests/unit/test_nas_playbook.py
git add roles/haos playbooks/nas_bootstrap.yml vms/haos/README.md tests/unit/test_nas_playbook.py
git commit -m "feat(ansible): haos role runs vms/haos/setup.sh behind a bridge precondition"
```

---

### Task 14: Retire `zsh`/`git`/`ssh`, settle the order, drop `--ask-become-pass`

**Files:**
- Delete: `roles/git/`, `roles/ssh/`, `roles/zsh/`
- Modify: `playbooks/nas_bootstrap.yml`, `roles/requirements.yml`, `nas_bootstrap.sh`
- Modify docs: `roles/README.md`, `playbooks/README.md`, `README.md` (NAS snippet), `.ctx/BUILD.md` (two lines),
  `roles/tailscale/README.md:78`, `roles/docker/README.md:496`, `.pre-commit-config.yaml:566` (comment)
- Test: `tests/unit/test_nas_playbook.py`, `tests/unit/test_docs_consistency.py`

**Interfaces:**
- Produces: playbook role order exactly `debian, zfs, samba, docker, tailscale, dotfiles, haos`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_nas_playbook.py`:

```python
EXPECTED_ORDER = ['debian', 'zfs', 'samba', 'docker', 'tailscale', 'dotfiles', 'haos']


class TestPlaybookOrder:
    """
    Tests for which roles the playbook runs, and in what order
    """
    def test_role_order(self) -> None:
        """
        Test that the playbook includes exactly the expected roles in order
        """
        play     = yaml.safe_load(PLAYBOOK.read_text(encoding='utf-8'))[0]
        included = [task['include_role']['name'] for task in play['tasks'] if 'include_role' in task]
        assert [name.removeprefix('roles/') for name in included] == EXPECTED_ORDER

    @pytest.mark.parametrize('role', ['git', 'ssh', 'zsh'])
    def test_retired_roles_are_gone(self, role: str) -> None:
        """
        Test that the forked dev-environment roles no longer exist
        """
        assert not (ROLES / role).exists()
```

(`str.removeprefix` needs Python 3.9 — the repo's floor.) Append to `tests/unit/test_docs_consistency.py`, following
its helper style:

```python
def _role_dirs(repo: Path) -> set[str]:
    """
    Return the names of the role directories under ``roles/``

    :param repo: repository root
    :return: one entry per role directory
    """
    return {path.name for path in (repo / 'roles').iterdir() if path.is_dir()}


def _roles_readme_rows(repo: Path) -> set[str]:
    """
    Return the role names linked in the first cell of the ``roles/README.md`` table

    :param repo: repository root
    :return: role names such as ``{"debian", "dotfiles", ...}``
    """
    text = (repo / 'roles' / 'README.md').read_text(encoding='utf-8')
    return set(re.findall(r'^\|\s*\[`([a-z0-9_-]+)`\]\(', text, re.MULTILINE))


class TestRolesReadme:
    """
    Tests that roles/README.md lists exactly the roles on disk
    """
    def test_readme_table_matches_role_dirs(self) -> None:
        """
        Test that every role directory has a table row and every row has a directory
        """
        assert _roles_readme_rows(REPO_ROOT) == _role_dirs(REPO_ROOT)
```

Run: `scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider tests/unit/test_nas_playbook.py tests/unit/test_docs_consistency.py`
→ FAIL.

- [ ] **Step 2: Delete and rewire**

```bash
git grep -n "community.crypto" -- roles playbooks   # only roles/ssh and roles/requirements.yml
git rm -r -q roles/git roles/ssh roles/zsh
```

`roles/requirements.yml` → collections: `community.docker` only. In `playbooks/nas_bootstrap.yml`, delete the `git`,
`ssh` and `zsh` include blocks (with their comments); the remaining order is then debian, zfs, samba, docker, tailscale,
dotfiles, haos. `nas_bootstrap.sh:81` → `ansible-playbook playbooks/nas_bootstrap.yml -i inventory/inventory.yml -vv`
(the play sets `ansible_become_pass` from the vault).

- [ ] **Step 3: Docs**

- `roles/README.md`: table rows in playbook order — remove `git`, `ssh`, `zsh`; add
  `| [`dotfiles`](dotfiles/README.md) | `$HOME` via the stow engine: clone, `profiles/nas` overlay, login shell, `bootstrap.sh` |`
  and `| [`haos`](haos/README.md) | Home Assistant OS VM via `vms/haos/setup.sh` (never `bridge.sh`) |` after
  `tailscale`. "Running roles" examples: drop `--ask-become-pass`; replace `--tags git` / `--tags zsh,git,ssh` with
  `--tags dotfiles` / `--tags dotfiles,haos`. "Variables": replace `dotfiles_home (repository root on the target)` with
  `dotfiles_repo_dir (the NAS clone, a play variable)`.
- `playbooks/README.md`: execution order list (1 APT update, 2 debian, 3 zfs, 4 samba, 5 docker, 6 tailscale,
  7 dotfiles — tags `dotfiles`, `configfile`, 8 haos — tags `haos`, `configfile`); add "Play variable
  `dotfiles_repo_dir`"; drop every `--ask-become-pass` and "with `--ask-become-pass -vv`" → "with `-vv`"; tag example
  `--tags git,ssh,zsh` → `--tags dotfiles,haos`.
- `README.md` NAS snippet: drop `--ask-become-pass` (three lines); `--tags git` → `--tags dotfiles`.
- `.ctx/BUILD.md:19,22`: drop `--ask-become-pass`; `--tags git,zsh` → `--tags dotfiles,haos`.
- `roles/tailscale/README.md:78`, `roles/docker/README.md:496`: drop `--ask-become-pass`.
- `.pre-commit-config.yaml:566` comment: `(e.g. roles/zsh/files/p10k.zsh)` → `(e.g. stow/shell/.config/zsh/conf.d/*.zsh)`.

Then `git grep -n -- "--ask-become-pass\|roles/zsh\|roles/git\|roles/ssh" -- . ':!archive' ':!docs/plans'` → no hits.

- [ ] **Step 4: Tests, lint, review**

```bash
scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider tests/unit/test_nas_playbook.py tests/unit/test_docs_consistency.py tests/unit/test_nas_bootstrap.py
scripts/hooks/ansible-lint.sh
```

Expected: PASS; ansible-lint reports **0 failures** (everything left is in `.ansible-lint-ignore`). Dispatch
`ansible-idempotency-reviewer` on `git diff -- playbooks roles/requirements.yml` (the deletions and order); fix
Critical/Important findings.

- [ ] **Step 5: Full suite, hooks, commit**

```bash
scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider
prek run --all-files
git add -A roles playbooks nas_bootstrap.sh README.md .ctx/BUILD.md .pre-commit-config.yaml tests/unit/test_nas_playbook.py tests/unit/test_docs_consistency.py
git commit -m "feat(ansible): retire the zsh, git and ssh roles; run dotfiles and haos after tailscale"
```

---

### Task 15: ansible-lint as a prek hook and a CI job

**Files:**
- Modify: `.pre-commit-config.yaml` (replace the commented-out ansible-lint block)
- Modify: `.github/workflows/lint.yml` (new job)
- Modify: `roles/README.md` ("Validation"), `.ctx/BUILD.md` (lint line)

- [ ] **Step 1: prek hook**

Replace the commented `ansible-lint` block at the end of `.pre-commit-config.yaml` with:

```yaml
  - repo: local
    hooks:

      # Ansible linting of playbooks/ and roles/ (check only; the wrapper supplies a throwaway vault password)
      - id: ansible-lint
        name: "[lint]   ansible"
        stages: [pre-commit, manual]
        priority: 40
        entry: scripts/hooks/ansible-lint.sh
        language: script
        files: ^(playbooks|roles)/|^\.ansible-lint|^\.yamllint
        pass_filenames: false
```

Run: `prek run ansible-lint --all-files` → Passed.

- [ ] **Step 2: CI job** — add to `.github/workflows/lint.yml` after `yamllint`:

```yaml
  ansible-lint:
    name: ansible-lint
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
      - name: Install dependencies
        run: uv sync
      - name: Install Ansible collections
        run: uv run ansible-galaxy collection install -r roles/requirements.yml
      - name: ansible-lint
        run: scripts/hooks/ansible-lint.sh
```

- [ ] **Step 3: Docs** — `roles/README.md` "Validation": "`prek run --all-files` runs yamllint over role files and
  ansible-lint over `playbooks/` and `roles/` through
  [`scripts/hooks/ansible-lint.sh`](../scripts/hooks/ansible-lint.sh) (check only; accepted findings are listed with
  reasons in [`.ansible-lint-ignore`](../.ansible-lint-ignore)). CI runs the same wrapper." `.ctx/BUILD.md`: add
  `scripts/hooks/ansible-lint.sh` to its lint commands.

- [ ] **Step 4: Commit**

```bash
prek run --files .pre-commit-config.yaml .github/workflows/lint.yml roles/README.md .ctx/BUILD.md
git add .pre-commit-config.yaml .github/workflows/lint.yml roles/README.md .ctx/BUILD.md
git commit -m "ci: run ansible-lint in prek and CI"
```

---

### Task 16: Branch verification and review

- [ ] **Step 1: Everything green**

```bash
scripts/hooks/uv-public.sh run pytest -q -p no:cacheprovider
prek run --all-files
git diff main -- tests/fixtures/os_layout          # must be empty
mkdir -p "$TMPDIR/sp2-home" && HOME="$TMPDIR/sp2-home" bash bootstrap/bootstrap.sh --dry-run --no-log; echo "rc=$?"
```

Expected: suite passes (more tests than the 675 baseline); hooks pass; no golden diff; the throwaway dry run exits 0
and its last line is `bootstrap: changes=<N>`. Delete `$TMPDIR/sp2-home`.

- [ ] **Step 2: Reviews**

- Dispatch `ansible-idempotency-reviewer` on `git diff main -- roles playbooks` (whole-branch view).
- Dispatch a whole-branch code review (`anthropic-pr-review-toolkit:code-reviewer`) on `git diff main`, including the
  engine changes and tests.
- Fix Critical/Important findings in follow-up commits; re-run Step 1.

- [ ] **Step 3: Owner approval to push, then open a draft PR**

Ask the owner before pushing. After approval: `git push -u origin worktree-nas-profile-handoff`, open a **draft** PR
(body: summary, the live-verification checklist below, and the attribution lines from the system prompt). The PR stays
draft until the live verification passes. If a CI job fails and its log host is blocked, ask the owner to run
`gh api repos/connormason/dotfiles/actions/jobs/<job-id>/logs > "$TMPDIR/ci-<job-id>.log"`.

---

### Task 17: Live verification on the NAS (owner runs; Claude reviews the saved output)

This session cannot reach the LAN, so the owner runs each command from a terminal on the work Mac, in the worktree
directory, and saves the output under `$TMPDIR` for review. Each stage must be reviewed and accepted before the next.
The plays are limited to `--tags debian,zfs,dotfiles,haos` (see the addendum's "Verification" for why).

Common prefix (referred to as `PLAY` below). It carries no `--tags`: repeated `--tags` options are unioned, so each
stage passes its own.

```bash
cd ~/dotfiles-personal/.claude/worktrees/nas-profile-handoff
PLAY=(scripts/hooks/uv-public.sh run ansible-playbook playbooks/nas_bootstrap.yml
      -i ~/dotfiles-personal/inventory/inventory.yml
      --vault-password-file ~/dotfiles-personal/vault_password.txt
      -e dotfiles_repo_version=worktree-nas-profile-handoff)
TAGS=(--tags debian,zfs,dotfiles,haos)
```

- [ ] **Stage 0 — prerequisites.** The owner corrects `ansible_host` for `nas` to `192.168.68.79` in the inventory repo
  (`~/dotfiles-personal/inventory/inventory.yml`, then commit/push that private repo), and runs
  `scripts/hooks/uv-public.sh run ansible-galaxy collection install -r roles/requirements.yml`. The branch is pushed
  (Task 16).
- [ ] **Stage 1 — check.** `"${PLAY[@]}" "${TAGS[@]}" --check --diff 2>&1 | tee "$TMPDIR/nas-1-check.txt"`. Review: no
  failures; `debian`/`zfs` report no changes, or only expected ones; the clone and the overlays registry show as
  changes; the engine preview and the `setup.sh` preview are skipped with their "not cloned yet" messages; the `br0`
  check passes.
- [ ] **Stage 2 — clone and preview.** `"${PLAY[@]}" --tags dotfiles -e dotfiles_bootstrap_preview=true 2>&1 | tee
  "$TMPDIR/nas-2-preview.txt"`. Review the engine's dry run: the stow preview lists `.zshrc`, `.zprofile`, `.gitconfig`
  (and any other blocking file) under "would back up"; the Brewfile status; no `docker`/`docker-compose`/`mermaid-cli`;
  a `bootstrap: changes=N` line. Then `"${PLAY[@]}" --tags haos --check 2>&1 | tee "$TMPDIR/nas-2-haos-check.txt"`:
  `setup.sh --dry-run` from the new clone, expected `haos: changes=1` (the libvirt group).
- [ ] **Stage 3 — real run.** `"${PLAY[@]}" "${TAGS[@]}" 2>&1 | tee "$TMPDIR/nas-3-real.txt"` (slow: the first
  `brew bundle`). Review: no failures; changed tasks limited to the engine run, `haos` (one change: libvirt group), and
  anything Stage 1 predicted.
- [ ] **Stage 4 — idempotence.** `"${PLAY[@]}" "${TAGS[@]}" 2>&1 | tee "$TMPDIR/nas-4-rerun.txt"`. Required:
  `changed=0` in the recap. If a task still reports changed, fix it on the branch (`ansible-idempotency-reviewer`
  first), push, and repeat Stages 3–4.
- [ ] **Stage 5 — acceptance on the NAS** (`ssh connormason@192.168.68.79`):

  ```bash
  ls -la ~/.dotfiles-backup/*/            # the Ansible-era .zshrc, .zprofile, .gitconfig (and .p10k.zsh if it blocked)
  exec zsh -l                              # starship prompt, no errors
  command -v docker                        # /usr/bin/docker
  cd ~/dotfiles-personal && scripts/hooks/uv-public.sh run python run.py doctor
  id -nG                                   # includes libvirt after re-login
  ```

  Then the owner deletes the old clone (`rm -rf ~/dotfiles`) when satisfied.
- [ ] **Stage 6 — merge.** Mark the PR ready; after merge, the next provisioning run (default `main`) switches the NAS
  clone back to `main` (the safety check allows it: clean, and `HEAD` is on `origin/worktree-nas-profile-handoff`).
  Update the project memory (`dotfiles-overhaul-program`) and remove the worktree (keep the branch).
