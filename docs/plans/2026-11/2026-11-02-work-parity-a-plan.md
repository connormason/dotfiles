# Work-parity PR A (hooks, doctor, Claude tracking) — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the hook commands, doctor improvements, `track-claude`, `NO_COLOR`, and PEP 723 metadata from
`~/dotfiles/run.py` into this repo's `run.py`.

**Architecture:** All changes land in `run.py` (stdlib-only, single file) following the existing `Command`-subclass
idiom, with one new `tests/unit/test_run_*.py` file per feature. `doctor` gains two `DoctorCheck`-returning functions and
a `confirm()` gate on `--fix`; the hook commands share a `RunHooksCommand` base with `pre`.

**Tech Stack:** Python 3.9-compatible stdlib (`argparse`, `subprocess`, `pathlib`), pytest, prek, ruff check, mypy.

**Design:** [`2026-11-02-work-parity-design.md`](2026-11-02-work-parity-design.md) (PR A section)

## Global Constraints

- Worktree: `/Users/connormason/dotfiles-personal/.claude/worktrees/work-parity-hooks-doctor` (branch
  `worktree-work-parity-hooks-doctor`). Run every command from there; paths below are relative to it.
- Run Python only through `scripts/hooks/uv-public.sh run …` (never bare `python`/`python3`/`uv`). Never run
  `ruff format`; lint with `scripts/hooks/uv-public.sh run ruff check`.
- `run.py` stays stdlib-only at import time and must type-check under mypy `python_version = "3.9"` (`[override]` is
  disabled for module `run`). Python 3.9 syntax only (`from __future__ import annotations` is present).
- isort `force-single-line`: one import per line. Single quotes. Sphinx docstrings (`:param:`, `:return:`), no blank
  line between a class docstring and its first member. Line width 120.
- Tests: class `Test…`, every method `-> None`, multi-line docstrings with a capitalized first word and no trailing
  period, `@pytest.mark.parametrize` tuple format. Each new test file starts with the module docstring, `from __future__
  import annotations`, and the `sys.path.insert(0, str(Path(__file__).resolve().parents[2]))` + `import run` preamble
  used by `tests/unit/test_run_doctor.py`.
- Add an import in the same edit as its first use (the edit-time ruff hook deletes unused imports mid-refactor). No new
  imports are needed by this plan; `os`, `shlex`, `shutil`, `sys`, `Path`, `ClassVar` are already imported in `run.py`.
- Keep every line within 120 columns; if `ruff check` reports E501 on a line in this plan's snippets, wrap it rather
  than adding a `noqa`.
- Every task that changes a registered command or description must regenerate the `Makefile` in the same commit
  (`scripts/hooks/uv-public.sh run python run.py makefile`); `TestMakefileCommand` is a drift guard.
- Final registered-command order (pinned by `test_real_commands_registered`): `list-hosts`, `inventory-status`,
  `update-inventory`, `vault-decrypt`, `vault-encrypt`, `clean`, `run-hooks`, `pre`, `prepare-hooks`, `install-hooks`,
  `uninstall-hooks`, `makefile`, `nas-deploy`, `nas-provision`, `doctor`, `bootstrap`, `stow`, `render`, `track-claude`,
  `test`.
- Baseline before any change: `scripts/hooks/uv-public.sh run --group test pytest tests/unit -q -p no:sugar` → 902
  passed, 3 skipped.
- Reference implementation: `~/dotfiles/run.py` (`RunHooksCommand` `:4061`, `check_hooks_installed` `:1444`,
  `validate_brewfile` `:2590`, `DoctorCommand` `:2896`, `confirm` `:863`, `TrackClaudeCommand` `:3309`,
  `find_untracked_claude_files` `:1373`). Deviations from it are called out in each task.
- Never copy work-only values into this public repo (internal index URLs, corporate hostnames/emails); the leak guard
  blocks them at commit time.

______________________________________________________________________

### Task 1: Commit the design and plan documents

**Files:**

- Create: `docs/plans/2026-11/2026-11-02-work-parity-design.md` (already written)
- Create: `docs/plans/2026-11/2026-11-02-work-parity-a-plan.md` (this file)

- [ ] **Step 1: Commit**

```bash
git add docs/plans/2026-11/2026-11-02-work-parity-design.md docs/plans/2026-11/2026-11-02-work-parity-a-plan.md
git commit -m "docs(plans): design and PR A plan for porting work run.py features"
```

Expected: hooks pass (`docs/plans/` is excluded from mdformat). If a hook rewrites a file, `git add` it and re-commit.

______________________________________________________________________

### Task 2: `NO_COLOR` support in `style()`

**Files:**

- Modify: `run.py` (env-var block `:142-146`; `style()` `:464-497`)
- Create: `tests/unit/test_run_style.py`

**Interfaces:**

- Produces: `run.NO_COLOR: bool` (module constant); `run.style()` returns `str(text)` unstyled when it is true.

- [ ] **Step 1: Write the failing tests** — create `tests/unit/test_run_style.py`:

```python
"""
Unit tests for run.py ANSI styling
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import run

ROOT = Path(__file__).resolve().parents[2]


class TestNoColor:
    """
    Tests for NO_COLOR handling in style()
    """
    def test_style_emits_ansi_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that styling is applied when NO_COLOR is off
        """
        monkeypatch.setattr(run, 'NO_COLOR', False)
        assert run.style('hi', fg='red') == '\033[31mhi\033[0m'

    def test_style_is_plain_when_no_color_is_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that every style attribute is dropped when NO_COLOR is on
        """
        monkeypatch.setattr(run, 'NO_COLOR', True)
        assert run.style('hi', fg='red', bg='blue', bold=True, dim=True, italic=True) == 'hi'

    def test_plain_style_still_stringifies(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that non-str values are converted to str on the unstyled path
        """
        monkeypatch.setattr(run, 'NO_COLOR', True)
        assert run.style(42, fg='red') == '42'

    @pytest.mark.parametrize(
        ('value', 'styled'),
        [
            (None,    True),
            ('',      True),
            ('1',     False),
            ('0',     False),
            ('false', False),
        ],
    )
    def test_env_var_follows_no_color_convention(self, value: str | None, styled: bool) -> None:
        """
        Test that any non-empty NO_COLOR value (even "0") disables styling and an empty or unset one does not
        """
        env = {key: val for key, val in os.environ.items() if key != 'NO_COLOR'}
        if value is not None:
            env['NO_COLOR'] = value

        code = f'import sys; sys.path.insert(0, {str(ROOT)!r}); import run; print(run.style("x", fg="red"))'
        result = subprocess.run([sys.executable, '-c', code], env=env, capture_output=True, text=True, check=True)
        assert (result.stdout.strip() != 'x') is styled
```

- [ ] **Step 2: Run the tests; verify they fail**

Run: `scripts/hooks/uv-public.sh run --group test pytest tests/unit/test_run_style.py -q -p no:sugar`
Expected: FAIL — `AttributeError: <module 'run'> has no attribute 'NO_COLOR'`.

- [ ] **Step 3: Implement** — in `run.py` add the constant between `RUN_DEBUG` and `INVENTORY_REPO_URL`:

```python
RUN_DEBUG:          bool = os.getenv(RUN_DEBUG_ENVVAR, 'false').lower() == 'true'
NO_COLOR:           bool = bool(os.getenv('NO_COLOR'))      # https://no-color.org: any non-empty value disables color
INVENTORY_REPO_URL: str  = os.getenv(
```

and in `style()` add the early return right after the docstring (and one sentence to the docstring summary):

```python
    """
    Style text with ANSI escape codes. Returns the text unstyled when ``NO_COLOR`` is set.

    :param text: the string to style with ansi codes
    ...
    :return: styled text
    """
    if NO_COLOR:
        return str(text)
    if not isinstance(text, str):
        text = str(text)
```

- [ ] **Step 4: Run the tests; verify they pass**

Run: `scripts/hooks/uv-public.sh run --group test pytest tests/unit/test_run_style.py -q -p no:sugar`
Expected: 8 passed.

- [ ] **Step 5: Lint and commit**

```bash
scripts/hooks/uv-public.sh run ruff check run.py tests/unit/test_run_style.py
git add run.py tests/unit/test_run_style.py
git commit -m "feat(run.py): honor NO_COLOR in style()"
```

______________________________________________________________________

### Task 3: PEP 723 metadata and `list-hosts` import handling

**Files:**

- Modify: `run.py` (line 1 area; the `# TODO: some commands have dependency on yaml` comment at `:98`; `ListHostsCommand.run`
  at `:1046-1067`)
- Create: `tests/unit/test_run_startup.py`

**Interfaces:**

- Produces: a `# /// script` block at the top of `run.py`; `list-hosts` exits `ExitCode.SETUP_ERROR` with a PyYAML hint
  when `yaml` cannot be imported.

- [ ] **Step 1: Write the failing tests** — create `tests/unit/test_run_startup.py`:

```python
"""
Unit tests for run.py script metadata and dependency handling
"""
from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import run

ROOT = Path(__file__).resolve().parents[2]

# Reference regex from PEP 723
PEP723_RE = re.compile(r'(?m)^# /// (?P<type>[a-zA-Z0-9-]+)$\s(?P<content>(^#(| .*)$\s)+)^# ///$')


def _script_metadata() -> dict[str, Any]:
    """
    Parse the PEP 723 ``script`` block at the top of run.py
    """
    text   = (ROOT / 'run.py').read_text(encoding='utf-8')
    blocks = [m for m in PEP723_RE.finditer(text) if m.group('type') == 'script']
    assert len(blocks) == 1
    toml_text = ''.join(
        line[2:] if line.startswith('# ') else line[1:]
        for line in blocks[0].group('content').splitlines(keepends=True)
    )
    return tomllib.loads(toml_text)


class TestScriptMetadata:
    """
    Tests for run.py's PEP 723 inline script metadata
    """
    def test_declares_python_floor(self) -> None:
        """
        Test that the script metadata matches the Python floor run.py is written for
        """
        assert _script_metadata()['requires-python'] == '>=3.9'

    def test_dependencies_match_pyproject(self) -> None:
        """
        Test that the one third-party dependency is declared identically in pyproject.toml
        """
        pyproject = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))
        for dependency in _script_metadata()['dependencies']:
            assert dependency in pyproject['project']['dependencies']

    def test_declares_pyyaml(self) -> None:
        """
        Test that PyYAML (imported lazily by list-hosts) is declared
        """
        assert any(dep.lower().startswith('pyyaml') for dep in _script_metadata()['dependencies'])


class TestListHostsDependency:
    """
    Tests for list-hosts when PyYAML is unavailable
    """
    def test_missing_yaml_is_reported_as_setup_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that a missing yaml module is not reported as an unparsable inventory
        """
        inventory = tmp_path / 'inventory.yml'
        inventory.write_text('all: {}\n', encoding='utf-8')
        monkeypatch.setattr(run, 'INVENTORY_FILE', inventory)
        monkeypatch.setitem(sys.modules, 'yaml', None)      # makes `import yaml` raise ImportError

        with pytest.raises(SystemExit) as exc_info:
            run.get_commands()['list-hosts'](argparse.Namespace())

        out = run.unstyle(capsys.readouterr().out)
        assert exc_info.value.code == run.ExitCode.SETUP_ERROR
        assert 'PyYAML is required' in out
        assert 'Failed to parse' not in out
```

- [ ] **Step 2: Run the tests; verify they fail**

Run: `scripts/hooks/uv-public.sh run --group test pytest tests/unit/test_run_startup.py -q -p no:sugar`
Expected: FAIL — `assert len(blocks) == 1` (no block yet) and the list-hosts test fails on `'PyYAML is required'`.

- [ ] **Step 3: Implement the metadata block** — insert directly after the shebang (before the module docstring):

```python
#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "PyYaml >= 6.0",
# ]
# ///
"""
run.py - CLI interface for Connor's personal dotfiles repository
```

Delete the now-resolved comment `# TODO: some commands have dependency on `yaml`. Maybe we should add `uv` metadata to
top of script?` (and one of its surrounding blank lines) from the section above "Constants/configuration".

- [ ] **Step 4: Implement the import split** — in `ListHostsCommand.run` replace

```python
        # Parse inventory file
        try:
            import yaml
            with INVENTORY_FILE.open() as f:
                inventory = yaml.safe_load(f)
        except Exception as e:
```

with

```python
        # PyYAML is the one third-party dependency: report a missing module separately from an unparsable inventory
        try:
            import yaml
        except ImportError:
            hint = style('scripts/hooks/uv-public.sh run python run.py list-hosts', fg='bright_magenta')
            printf('')
            printf('❌ PyYAML is required to read the inventory', fg='red', bold=True)
            printf(f'Run it through uv: {hint}', indent=3)
            sys.exit(ExitCode.SETUP_ERROR)

        # Parse inventory file
        try:
            with INVENTORY_FILE.open() as f:
                inventory = yaml.safe_load(f)
        except Exception as e:
```

- [ ] **Step 5: Run the tests; verify they pass**

Run: `scripts/hooks/uv-public.sh run --group test pytest tests/unit/test_run_startup.py tests/unit/test_run_commands.py -q -p no:sugar`
Expected: all pass.

- [ ] **Step 6: Lint and commit**

```bash
scripts/hooks/uv-public.sh run ruff check run.py tests/unit/test_run_startup.py
git add run.py tests/unit/test_run_startup.py
git commit -m "feat(run.py): add PEP 723 metadata and report a missing PyYAML distinctly"
```

______________________________________________________________________

### Task 4: `run-hooks`, `pre`, and `prepare-hooks`

**Files:**

- Modify: `run.py` (replace `PreCommand` `:1447-1460`; keep `InstallHooksCommand`/`UninstallHooksCommand` as is)
- Modify: `tests/unit/test_run_commands.py` (`test_real_commands_registered` `:107-116`)
- Modify: `Makefile` (regenerated)
- Create: `tests/unit/test_run_hooks.py`

**Interfaces:**

- Produces: `run.RunHooksCommand` (`name='run-hooks'`, `group='Codebase'`, nested `Args`,
  `add_arguments(parser, *, include_files: bool = True)`, `@staticmethod build_command(args) -> list[str]`,
  `run(args)`); `run.PreCommand(RunHooksCommand)` (`name='pre'`, forces `args.all_files = True`);
  `run.PrepareHooksCommand` (`name='prepare-hooks'`).

- [ ] **Step 1: Write the failing tests** — create `tests/unit/test_run_hooks.py`:

```python
"""
Unit tests for the run.py prek hook commands (run-hooks, pre, prepare-hooks)
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import run

Call = tuple[list[str], dict[str, object]]


def _parse(*argv: str) -> argparse.Namespace:
    """
    Parse a run.py command line into the typed root namespace
    """
    return run.build_parser().parse_args(list(argv), namespace=run.Args())


def _option_strings(command: str) -> set[str]:
    """
    Get every option string a command's subparser accepts
    """
    action = next(a for a in run.build_parser()._actions if isinstance(a, argparse._SubParsersAction))
    return {opt for a in action.choices[command]._actions for opt in a.option_strings}


def _record(monkeypatch: pytest.MonkeyPatch, returncode: int = 0) -> list[Call]:
    """
    Patch shell_command to record each call (command and keyword args) and exit with ``returncode``
    """
    calls: list[Call] = []

    def fake_shell_command(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, returncode, stdout='', stderr='')

    monkeypatch.setattr(run, 'shell_command', fake_shell_command)
    return calls


class TestRunHooks:
    """
    Tests for the run-hooks command
    """
    @pytest.mark.parametrize(
        ('argv', 'expected'),
        [
            (['run-hooks'],                                      ['prek', 'run']),
            (['run-hooks', 'mdformat', 'ruff'],                  ['prek', 'run', 'mdformat', 'ruff']),
            (['run-hooks', '-a'],                                ['prek', 'run', '--all-files']),
            (['run-hooks', '-d', 'docs'],                        ['prek', 'run', '--directory', 'docs']),
            (['run-hooks', '--last-commit'],                     ['prek', 'run', '--last-commit']),
            (['run-hooks', '--stage', 'pre-push'],               ['prek', 'run', '--stage', 'pre-push']),
            (
                ['run-hooks', '-s', 'main', '-o', 'HEAD'],
                ['prek', 'run', '--from-ref', 'main', '--to-ref', 'HEAD'],
            ),
            (
                ['run-hooks', '--skip', 'mypy', '--skip', 'ruff'],
                ['prek', 'run', '--skip', 'mypy', '--skip', 'ruff'],
            ),
            (
                ['run-hooks', '--show-diff-on-failure', '--fail-fast', '--dry-run', '-v'],
                ['prek', 'run', '--show-diff-on-failure', '--fail-fast', '--dry-run', '--verbose'],
            ),
        ],
    )
    def test_builds_prek_command(self, argv: list[str], expected: list[str]) -> None:
        """
        Test that each option maps to the matching prek run flag
        """
        assert run.RunHooksCommand.build_command(_parse(*argv)) == expected

    def test_hooks_precede_the_greedy_files_option(self) -> None:
        """
        Test that hook names are placed before --files, which would otherwise swallow them as filenames
        """
        cmd = run.RunHooksCommand.build_command(_parse('run-hooks', 'mdformat', '--files', 'a.md', 'b.md'))
        assert cmd == ['prek', 'run', 'mdformat', '--files', 'a.md', 'b.md']

    def test_streams_output_and_propagates_exit_code(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that prek runs with inherited stdio and its exit code becomes the command's
        """
        calls = _record(monkeypatch, returncode=3)
        with pytest.raises(SystemExit) as exc_info:
            run.get_commands()['run-hooks'](_parse('run-hooks', '-a'))

        assert exc_info.value.code == 3
        assert calls == [(['prek', 'run', '--all-files'], {'check': False})]

    def test_description(self) -> None:
        """
        Test the help description shown in the script help and Makefile
        """
        assert run.get_commands()['run-hooks'].description == 'Run prek hooks on modified or specified project files'


class TestPre:
    """
    Tests for the pre command (run-hooks pinned to all files)
    """
    def test_forces_all_files_and_forwards_filters(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that pre always passes --all-files while still honoring hook filters and skips
        """
        calls = _record(monkeypatch)
        with pytest.raises(SystemExit) as exc_info:
            run.get_commands()['pre'](_parse('pre', 'mdformat', '--skip', 'mypy'))

        assert exc_info.value.code == 0
        assert calls[0][0] == ['prek', 'run', 'mdformat', '--all-files', '--skip', 'mypy']

    def test_file_selection_options_are_not_offered(self) -> None:
        """
        Test that pre does not accept the file-selection options it overrides
        """
        assert not {'--all-files', '--files', '--directory'} & _option_strings('pre')

    def test_description_is_unchanged(self) -> None:
        """
        Test that the pre description (and therefore its Makefile line) is unchanged
        """
        assert run.get_commands()['pre'].description == 'Run prek (pre-commit) hooks on all project files'


class TestPrepareHooks:
    """
    Tests for the prepare-hooks command
    """
    def test_builds_prek_command(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that hook filters, --skip, and --verbose are forwarded to prek prepare-hooks
        """
        calls = _record(monkeypatch)
        with pytest.raises(SystemExit) as exc_info:
            run.get_commands()['prepare-hooks'](_parse('prepare-hooks', 'ruff', '--skip', 'mypy', '-v'))

        assert exc_info.value.code == 0
        expected = ['prek', 'prepare-hooks', 'ruff', '--skip', 'mypy', '--verbose']
        assert calls == [(expected, {'indent': 3, 'check': False})]

    def test_propagates_exit_code(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that a failing prepare exits with prek's return code
        """
        _record(monkeypatch, returncode=2)
        with pytest.raises(SystemExit) as exc_info:
            run.get_commands()['prepare-hooks'](_parse('prepare-hooks'))
        assert exc_info.value.code == 2
```

Also update `test_real_commands_registered` in `tests/unit/test_run_commands.py`:

```python
        assert list(run.REGISTERED_COMMANDS) == [
            'list-hosts', 'inventory-status', 'update-inventory', 'vault-decrypt', 'vault-encrypt',
            'clean', 'run-hooks', 'pre', 'prepare-hooks', 'install-hooks', 'uninstall-hooks', 'makefile',
            'nas-deploy', 'nas-provision',
            'doctor', 'bootstrap', 'stow', 'render', 'test',
        ]
```

- [ ] **Step 2: Run the tests; verify they fail**

Run: `scripts/hooks/uv-public.sh run --group test pytest tests/unit/test_run_hooks.py tests/unit/test_run_commands.py -q -p no:sugar`
Expected: FAIL — `AttributeError: module 'run' has no attribute 'RunHooksCommand'`, and the registration test fails.

- [ ] **Step 3: Implement** — in `run.py` replace the whole `PreCommand` class with:

```python
class RunHooksCommand(Command):
    """
    Run prek hooks on modified or specified project files
    """
    name:  ClassVar[str] = 'run-hooks'
    group: ClassVar[str] = 'Codebase'

    class Args(argparse.Namespace):
        hooks:       list[str] | None   # positional arg(s) "HOOK|PROJECT"
        skip:        list[str] | None   # --skip
        all_files:   bool               # --all-files
        files:       list[str] | None   # --files
        directory:   str | None         # --directory
        from_ref:    str | None         # --from-ref
        to_ref:      str | None         # --to-ref
        last_commit: bool               # --last-commit
        stage:       str | None         # --stage
        show_diff:   bool               # --show-diff-on-failure
        fail_fast:   bool               # --fail-fast
        dry_run:     bool               # --dry-run
        verbose:     bool               # --verbose

    def add_arguments(self, parser: argparse.ArgumentParser, *, include_files: bool = True) -> None:
        parser.add_argument(
            'hooks',
            nargs='*',
            default=None,
            metavar='HOOK|PROJECT',
            help='Hooks or projects to run (default: all)',
        )

        if include_files:
            file_opts = parser.add_argument_group('File selection')
            file_opts.add_argument(
                '-a',
                '--all-files',
                action='store_true',
                help='Run on all files in the repo',
            )
            file_opts.add_argument(
                '--files',
                nargs='*',
                metavar='FILE',
                help='Run on these files (put hook names before this option)',
            )
            file_opts.add_argument(
                '-d',
                '--directory',
                metavar='DIR',
                help='Run on all files in this directory',
            )

        ref_opts = parser.add_argument_group('Ref selection')
        ref_opts.add_argument(
            '-s',
            '--from-ref',
            metavar='REF',
            help='Original ref in a from_ref...to_ref diff expression',
        )
        ref_opts.add_argument(
            '-o',
            '--to-ref',
            metavar='REF',
            help='Destination ref in a from_ref...to_ref diff expression (default: HEAD)',
        )
        ref_opts.add_argument(
            '--last-commit',
            action='store_true',
            help='Run on the files of the last commit (--from-ref HEAD~1 --to-ref HEAD)',
        )

        run_opts = parser.add_argument_group('Run options')
        run_opts.add_argument(
            '--skip',
            action='append',
            metavar='HOOK|PROJECT',
            help='Skip this hook or project (repeatable)',
        )
        run_opts.add_argument(
            '--stage',
            metavar='STAGE',
            help='The git stage the hooks run for (e.g. pre-push, manual)',
        )
        run_opts.add_argument(
            '--show-diff-on-failure',
            action='store_true',
            dest='show_diff',
            help='Run `git diff` after a hook fails',
        )
        run_opts.add_argument(
            '--fail-fast',
            action='store_true',
            help='Stop after the first failing hook',
        )
        run_opts.add_argument(
            '--dry-run',
            action='store_true',
            help='List the hooks that would run without running them',
        )
        run_opts.add_argument(
            '-v',
            '--verbose',
            action='store_true',
            help='Show verbose prek output',
        )

    @staticmethod
    def build_command(args: Args) -> list[str]:
        """
        Build the ``prek run`` command line

        Hook names go first: prek's ``--files`` is greedy, so a trailing hook name would be read as a filename.

        :param args: parsed arguments (the file-selection attributes are absent for commands that omit those options)
        :return: command and arguments
        """
        cmd: list[str] = ['prek', 'run', *(args.hooks or [])]

        if getattr(args, 'all_files', False):
            cmd.append('--all-files')
        if files := getattr(args, 'files', None):
            cmd.extend(['--files', *files])
        if directory := getattr(args, 'directory', None):
            cmd.extend(['--directory', directory])

        if args.from_ref:
            cmd.extend(['--from-ref', args.from_ref])
        if args.to_ref:
            cmd.extend(['--to-ref', args.to_ref])
        if args.last_commit:
            cmd.append('--last-commit')

        for skip in (args.skip or []):
            cmd.extend(['--skip', skip])
        if args.stage:
            cmd.extend(['--stage', args.stage])
        if args.show_diff:
            cmd.append('--show-diff-on-failure')
        if args.fail_fast:
            cmd.append('--fail-fast')
        if args.dry_run:
            cmd.append('--dry-run')
        if args.verbose:
            cmd.append('--verbose')

        return cmd

    def run(self, args: Args) -> None:
        if getattr(args, 'all_files', False):
            printf('🕝 Running prek hooks on all project files...', fg='bright_cyan')
        elif files := getattr(args, 'files', None):
            printf(f'🕝 Running prek hooks on {len(files)} file(s)...', fg='bright_cyan')
        else:
            printf('🕝 Running prek hooks...', fg='bright_cyan')

        sys.exit(shell_command(self.build_command(args), check=False).returncode)


class PreCommand(RunHooksCommand):
    """
    Run prek (pre-commit) hooks on all project files
    """
    name: ClassVar[str] = 'pre'

    def add_arguments(self, parser: argparse.ArgumentParser, **_kwargs: object) -> None:
        super().add_arguments(parser, include_files=False)

    def run(self, args: RunHooksCommand.Args) -> None:
        args.all_files = True
        super().run(args)


class PrepareHooksCommand(Command):
    """
    Prepare the environments of all prek hooks
    """
    name:  ClassVar[str] = 'prepare-hooks'
    group: ClassVar[str] = 'Codebase'

    class Args(argparse.Namespace):
        hooks:   list[str] | None       # positional arg(s) "HOOK|PROJECT"
        skip:    list[str] | None       # --skip
        verbose: bool                   # --verbose

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            'hooks',
            nargs='*',
            default=None,
            metavar='HOOK|PROJECT',
            help='Hooks or projects to prepare (default: all)',
        )
        parser.add_argument(
            '--skip',
            action='append',
            metavar='HOOK|PROJECT',
            help='Skip this hook or project (repeatable)',
        )
        parser.add_argument(
            '-v',
            '--verbose',
            action='store_true',
            help='Show verbose prek output',
        )

    def run(self, args: Args) -> None:
        cmd: list[str] = ['prek', 'prepare-hooks', *(args.hooks or [])]
        for skip in (args.skip or []):
            cmd.extend(['--skip', skip])
        if args.verbose:
            cmd.append('--verbose')

        printf('⏬ Preparing prek hook environments...', fg='bright_cyan')
        sys.exit(shell_command(cmd, indent=3, check=False).returncode)
```

- [ ] **Step 4: Regenerate the Makefile and run the tests**

```bash
scripts/hooks/uv-public.sh run python run.py makefile
scripts/hooks/uv-public.sh run --group test pytest tests/unit/test_run_hooks.py tests/unit/test_run_commands.py tests/unit/test_run_doctor.py -q -p no:sugar
```

Expected: all pass (the Makefile drift guard and `--help` parser tests included). `git diff Makefile` shows only the new
`run-hooks` and `prepare-hooks` entries.

- [ ] **Step 5: Smoke-test the real command**

Run: `scripts/hooks/uv-public.sh run python run.py run-hooks --dry-run trailing-whitespace --last-commit`
Expected: prek lists the hook(s) it would run; exit code 0.

- [ ] **Step 6: Lint and commit**

```bash
scripts/hooks/uv-public.sh run ruff check run.py tests/unit/test_run_hooks.py tests/unit/test_run_commands.py
git add run.py Makefile tests/unit/test_run_hooks.py tests/unit/test_run_commands.py
git commit -m "feat(run.py): add run-hooks and prepare-hooks, make pre a run-hooks subclass"
```

______________________________________________________________________

### Task 5: `confirm()` and `doctor --yes`

**Files:**

- Modify: `run.py` (add `confirm` after `arg_note`; `DoctorCommand` `:1946-1983`)
- Modify: `tests/unit/test_run_doctor.py` (the `Namespace(fix=…)` calls `:228`, `:249`, `:257`, `:275`; new tests)
- Create: `tests/unit/test_run_prompts.py`

**Interfaces:**

- Produces: `run.confirm(prompt_text: str, *, default: bool = True, indent: int = 0) -> bool`;
  `DoctorCommand.Args` gains `yes: bool`. `doctor --fix` now prompts per fix; `-y/--yes` implies `--fix` and skips the
  prompt.
- Consumes: `printf`, `style`, `shlex`, `doctor_checks`, `shell_command` (existing).

- [ ] **Step 1: Write the failing `confirm` tests** — create `tests/unit/test_run_prompts.py`:

```python
"""
Unit tests for run.py interactive prompts
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import run


class TestConfirm:
    """
    Tests for the confirm prompt
    """
    @pytest.mark.parametrize(
        ('answer', 'default', 'expected'),
        [
            ('y',     False, True),
            ('YES',   False, True),
            ('n',     True,  False),
            ('',      True,  True),
            ('',      False, False),
            ('maybe', True,  False),
        ],
    )
    def test_interprets_answer(
        self,
        monkeypatch: pytest.MonkeyPatch,
        answer: str,
        default: bool,
        expected: bool,
    ) -> None:
        """
        Test that yes/no answers are honored and an empty answer falls back to the default
        """
        monkeypatch.setattr('builtins.input', lambda prompt: answer)
        assert run.confirm('Proceed?', default=default) is expected

    def test_prompt_shows_default_and_indent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that the prompt marks the default answer and honors the indent
        """
        prompts: list[str] = []
        monkeypatch.setattr('builtins.input', lambda prompt: prompts.append(prompt) or 'y')

        run.confirm('Proceed?', indent=3)
        run.confirm('Proceed?', default=False)
        assert prompts == ['   Proceed? [Y/n]: ', 'Proceed? [y/N]: ']

    def test_eof_declines(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that a closed stdin counts as "no" rather than raising
        """
        def raise_eof(prompt: str) -> str:
            raise EOFError

        monkeypatch.setattr('builtins.input', raise_eof)
        assert run.confirm('Proceed?') is False

    def test_ctrl_c_propagates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that Ctrl-C reaches main() (cancelling the run) instead of being read as "no"
        """
        def raise_interrupt(prompt: str) -> str:
            raise KeyboardInterrupt

        monkeypatch.setattr('builtins.input', raise_interrupt)
        with pytest.raises(KeyboardInterrupt):
            run.confirm('Proceed?')
```

- [ ] **Step 2: Update and extend `tests/unit/test_run_doctor.py`**

Change the existing namespaces: the three `Namespace(fix=False)` calls (in `test_fix_commands_are_not_run_without_flag`,
`test_doctor_exits_nonzero_on_failure`, `test_doctor_passes_quietly_when_all_ok`) become
`run.argparse.Namespace(fix=False, yes=False)`, and the one in `test_fix_runs_fix_then_rechecks` becomes
`run.argparse.Namespace(fix=True, yes=True)`. Then add these tests to `TestDoctorCommand`:

```python
    def test_fix_asks_before_each_fix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that --fix names the fix command in a confirmation prompt before running it
        """
        results = iter([
            [run.DoctorCheck('links', False, 'pending',             ['echo', 'fix'])],
            [run.DoctorCheck('links', True,  'all packages linked')],
        ])
        asked: list[str] = []
        ran:   list[list[str]] = []

        monkeypatch.setattr(run, 'doctor_checks', lambda: next(results))
        monkeypatch.setattr(run, 'confirm', lambda prompt, **kwargs: asked.append(run.unstyle(prompt)) or True)
        monkeypatch.setattr(run, 'shell_command', lambda cmd, **kwargs: ran.append(cmd) or _completed(0))

        run.get_commands()['doctor'](run.argparse.Namespace(fix=True, yes=False))
        assert len(asked) == 1
        assert 'echo fix' in asked[0]
        assert 'links' in asked[0]
        assert ran == [['echo', 'fix']]

    def test_declined_fix_is_skipped_and_doctor_still_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that a declined fix does not run, the checks are re-run, and the command exits 1
        """
        pending = [run.DoctorCheck('links', False, 'pending', ['echo', 'fix'])]
        ran: list[list[str]] = []

        monkeypatch.setattr(run, 'doctor_checks', lambda: pending)
        monkeypatch.setattr(run, 'confirm', lambda prompt, **kwargs: False)
        monkeypatch.setattr(run, 'shell_command', lambda cmd, **kwargs: ran.append(cmd) or _completed(0))

        with pytest.raises(SystemExit) as exc_info:
            run.get_commands()['doctor'](run.argparse.Namespace(fix=True, yes=False))
        assert exc_info.value.code == 1
        assert ran == []

    def test_yes_implies_fix_without_prompting(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that --yes applies fixes without --fix and never asks
        """
        results = iter([
            [run.DoctorCheck('links', False, 'pending',             ['echo', 'fix'])],
            [run.DoctorCheck('links', True,  'all packages linked')],
        ])
        ran: list[list[str]] = []

        def refuse_prompt(prompt: str, **kwargs: object) -> bool:
            raise AssertionError('--yes must not prompt')

        monkeypatch.setattr(run, 'doctor_checks', lambda: next(results))
        monkeypatch.setattr(run, 'confirm', refuse_prompt)
        monkeypatch.setattr(run, 'shell_command', lambda cmd, **kwargs: ran.append(cmd) or _completed(0))

        run.get_commands()['doctor'](run.argparse.Namespace(fix=False, yes=True))
        assert ran == [['echo', 'fix']]
```

- [ ] **Step 3: Run the tests; verify they fail**

Run: `scripts/hooks/uv-public.sh run --group test pytest tests/unit/test_run_prompts.py tests/unit/test_run_doctor.py -q -p no:sugar`
Expected: FAIL — `AttributeError: module 'run' has no attribute 'confirm'`; the `yes=` namespaces fail in `doctor`.

- [ ] **Step 4: Implement `confirm`** — in `run.py`, after `arg_note`:

```python
def confirm(prompt_text: str, *, default: bool = True, indent: int = 0) -> bool:
    """
    Prompt the user for Y/n confirmation

    :param prompt_text: the question to display
    :param default: the answer used when the user presses Enter without typing
    :param indent: number of spaces to indent the prompt by
    :return: True if the user confirmed; False if they declined or stdin is closed (EOF). Ctrl-C is not caught, so it
             cancels the whole run through :func:`main`
    """
    suffix = '[Y/n]' if default else '[y/N]'
    try:
        answer = input(f'{" " * indent}{prompt_text} {suffix}: ').strip().lower()
    except EOFError:
        printf('')
        return False

    if not answer:
        return default
    return answer in ('y', 'yes')
```

- [ ] **Step 5: Implement `doctor --yes`** — in `DoctorCommand` replace `Args`, `add_arguments`, and `run`:

```python
    class Args(argparse.Namespace):
        fix: bool       # --fix
        yes: bool       # --yes

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            '-f',
            '--fix',
            action='store_true',
            help=(
                'Run the fix for each failing check (after confirming), then re-check\n'
                '(links: stow.sh --backup-conflicts, which moves blocking files\n'
                'into ~/.dotfiles-backup/<timestamp>/)'
            ),
        )
        parser.add_argument(
            '-y',
            '--yes',
            action='store_true',
            help='Apply fixes without prompting for confirmation (implies --fix)',
        )

    def run(self, args: Args) -> None:
        checks = doctor_checks()

        if args.fix or args.yes:
            for check in checks:
                if check.ok or not check.fix:
                    continue

                command  = shlex.join(check.fix)
                question = f'Run {style(command, fg="bright_magenta")} to fix {style(check.name, bold=True)}?'
                if not args.yes and not confirm(question, indent=3):
                    printf(f'Skipped {check.name}', dim=True, indent=3)
                    continue

                printf(f'🔧 {check.name}: {command}', fg='bright_cyan')
                shell_command(check.fix, indent=3, check=False)
            checks = doctor_checks()

        for check in checks:
            emoji = '🟢' if check.ok else '🔴'
            printf(f'{emoji} {style(check.name, fg="white", bold=True)}  {check.detail}', indent=3)

        if not all(check.ok for check in checks):
            sys.exit(ExitCode.COMMAND_FAILED)
```

- [ ] **Step 6: Regenerate the Makefile, run the tests, commit**

```bash
scripts/hooks/uv-public.sh run python run.py makefile
scripts/hooks/uv-public.sh run --group test pytest tests/unit/test_run_prompts.py tests/unit/test_run_doctor.py tests/unit/test_run_commands.py -q -p no:sugar
scripts/hooks/uv-public.sh run ruff check run.py tests/unit/test_run_prompts.py tests/unit/test_run_doctor.py
git add run.py Makefile tests/unit/test_run_prompts.py tests/unit/test_run_doctor.py
git commit -m "feat(run.py): add confirm() and gate doctor --fix behind it (--yes to skip)"
```

Expected: tests pass; `git diff Makefile` is empty (no description changed in this task).

______________________________________________________________________

### Task 6: `doctor` checks for git hooks and Brewfile drift

**Files:**

- Modify: `run.py` (constants near `REQUIRED_TOOLS` `:127-129`; `check_layers` `:1854-1867`; new `check_hooks`,
  `check_brewfiles`; `doctor_checks` `:1936-1943`; `DoctorCommand` docstring)
- Modify: `tests/unit/test_run_doctor.py` (new classes; the `Dotfiles` group test stays as is until Task 7)
- Modify: `Makefile` (regenerated: the `doctor` description changes)

**Interfaces:**

- Produces: `run.GIT_HOOK_TYPES: tuple[str, ...]`; `run.PREK_SHIM_MARKER: str`; `run._probe_layers() ->
  subprocess.CompletedProcess[str]`; `run.check_hooks() -> DoctorCheck`; `run.check_brewfiles() -> DoctorCheck`.
  `doctor_checks()` now returns `[tools, layers, git, hooks, links, render, brewfile]` when the first two pass.
- Consumes: `_capture`, `_first_line`, `DoctorCheck`, `folduser`, `shutil`, `Path` (existing).

- [ ] **Step 1: Write the failing tests** — append to `tests/unit/test_run_doctor.py` (add `import yaml` is NOT needed
      at module top: import it inside the one test that uses it):

```python
SHIM = '#!/bin/sh\n# File generated by prek: https://github.com/j178/prek\nexec prek hook-impl "$@"\n'


def _write_shims(hooks_dir: Path, hook_types: tuple[str, ...], content: str = SHIM) -> None:
    """
    Create hook shim files for the given hook types
    """
    hooks_dir.mkdir(parents=True, exist_ok=True)
    for hook_type in hook_types:
        (hooks_dir / hook_type).write_text(content, encoding='utf-8')


class TestCheckHooks:
    """
    Tests for the git hooks doctor check
    """
    @pytest.fixture(autouse=True)
    def _prek_on_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Pretend prek is installed unless a test says otherwise
        """
        monkeypatch.setattr(run.shutil, 'which', lambda name: f'/usr/bin/{name}')

    def test_ok_when_every_shim_is_installed(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """
        Test that the check passes when all hook types have a prek shim
        """
        hooks = tmp_path / 'hooks'
        _write_shims(hooks, run.GIT_HOOK_TYPES)
        monkeypatch.setattr(run, '_capture', lambda cmd: _completed(0, f'{hooks}\n'))

        check = run.check_hooks()
        assert check.ok
        assert check.detail == '6 prek hook shims installed'

    def test_missing_shim_fails_and_offers_prek_install(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """
        Test that a missing pre-push shim (the leak guard) fails the check and is named in the detail
        """
        hooks = tmp_path / 'hooks'
        _write_shims(hooks, tuple(t for t in run.GIT_HOOK_TYPES if t != 'pre-push'))
        monkeypatch.setattr(run, '_capture', lambda cmd: _completed(0, f'{hooks}\n'))

        check = run.check_hooks()
        assert not check.ok
        assert 'pre-push' in check.detail
        assert check.fix == ['prek', 'install']

    def test_foreign_shim_counts_as_missing(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """
        Test that a hook file not generated by prek does not satisfy the check
        """
        hooks = tmp_path / 'hooks'
        _write_shims(hooks, run.GIT_HOOK_TYPES, content='#!/bin/sh\necho custom hook\n')
        monkeypatch.setattr(run, '_capture', lambda cmd: _completed(0, f'{hooks}\n'))
        assert not run.check_hooks().ok

    def test_relative_hooks_path_is_resolved_against_the_repo(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """
        Test that the relative path git prints in a plain checkout is resolved against the repo root
        """
        _write_shims(tmp_path / '.git' / 'hooks', run.GIT_HOOK_TYPES)
        monkeypatch.setattr(run, 'DOTFILES_DIR', tmp_path)
        monkeypatch.setattr(run, '_capture', lambda cmd: _completed(0, '.git/hooks\n'))
        assert run.check_hooks().ok

    def test_absolute_hooks_path_from_a_linked_worktree(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """
        Test that the absolute common-dir path git prints inside a linked worktree is used as is
        """
        common = tmp_path / 'main-checkout' / '.git' / 'hooks'
        _write_shims(common, run.GIT_HOOK_TYPES)
        monkeypatch.setattr(run, 'DOTFILES_DIR', tmp_path / 'worktree')
        monkeypatch.setattr(run, '_capture', lambda cmd: _completed(0, f'{common}\n'))
        assert run.check_hooks().ok

    def test_fails_outside_a_git_checkout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that a failing git probe fails the check with git's message
        """
        monkeypatch.setattr(run, '_capture', lambda cmd: _completed(128, '', 'fatal: not a git repository\n'))

        check = run.check_hooks()
        assert not check.ok
        assert 'not a git repository' in check.detail

    def test_no_fix_when_prek_is_missing(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """
        Test that the check offers no fix (and says why) when prek is not on PATH
        """
        monkeypatch.setattr(run.shutil, 'which', lambda name: None)
        monkeypatch.setattr(run, '_capture', lambda cmd: _completed(0, f'{tmp_path / "hooks"}\n'))

        check = run.check_hooks()
        assert not check.ok
        assert check.fix is None
        assert 'prek not on PATH' in check.detail

    def test_probe_only_resolves_the_hooks_path(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """
        Test that the check runs a single read-only git probe
        """
        seen: list[list[str]] = []

        def fake_capture(cmd: list[str]) -> subprocess.CompletedProcess[str]:
            seen.append(cmd)
            return _completed(0, f'{tmp_path}\n')

        monkeypatch.setattr(run, '_capture', fake_capture)
        run.check_hooks()
        assert seen == [['git', 'rev-parse', '--git-path', 'hooks']]

    def test_hook_types_match_the_prek_config(self) -> None:
        """
        Test that GIT_HOOK_TYPES mirrors default_install_hook_types in .pre-commit-config.yaml
        """
        import yaml

        config = yaml.safe_load((run.DOTFILES_DIR / '.pre-commit-config.yaml').read_text(encoding='utf-8'))
        assert list(run.GIT_HOOK_TYPES) == config['default_install_hook_types']


class TestCheckBrewfiles:
    """
    Tests for the Brewfile drift doctor check
    """
    @staticmethod
    def _layers(tmp_path: Path, *, with_brewfile: tuple[bool, ...]) -> list[Path]:
        """
        Create one layer directory per flag, with a bootstrap/Brewfile where the flag is true
        """
        layers: list[Path] = []
        for index, has_brewfile in enumerate(with_brewfile):
            layer = tmp_path / f'layer{index}'
            (layer / 'bootstrap').mkdir(parents=True)
            if has_brewfile:
                (layer / 'bootstrap' / 'Brewfile').write_text('brew "jq"\n', encoding='utf-8')
            layers.append(layer)
        return layers

    @staticmethod
    def _capture_with(
        monkeypatch: pytest.MonkeyPatch,
        layers: list[Path],
        *,
        unsatisfied: set[Path] | None = None,
        layers_rc: int = 0,
    ) -> list[list[str]]:
        """
        Stub _capture: the layer probe lists ``layers``; ``brew bundle check`` fails for the ``unsatisfied`` Brewfiles
        """
        seen: list[list[str]] = []
        stdout = ''.join(f'{layer}\n' for layer in layers)

        def fake_capture(cmd: list[str]) -> subprocess.CompletedProcess[str]:
            seen.append(cmd)
            if cmd[:2] == ['bash', '-c']:
                return _completed(layers_rc, stdout)
            return _completed(1 if Path(cmd[-1]) in (unsatisfied or set()) else 0)

        monkeypatch.setattr(run, '_capture', fake_capture)
        monkeypatch.setattr(run.shutil, 'which', lambda name: f'/usr/bin/{name}')
        return seen

    def test_ok_when_every_brewfile_is_satisfied(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """
        Test that the check passes and counts only layers that declare a Brewfile
        """
        layers = self._layers(tmp_path, with_brewfile=(True, False, True))
        self._capture_with(monkeypatch, layers)

        check = run.check_brewfiles()
        assert check.ok
        assert check.detail == '2 Brewfile(s) satisfied'

    def test_ok_when_no_layer_declares_a_brewfile(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """
        Test that a repo without Brewfiles is not reported as drifted
        """
        self._capture_with(monkeypatch, self._layers(tmp_path, with_brewfile=(False,)))
        assert run.check_brewfiles().ok

    def test_drift_fails_names_the_brewfile_and_offers_a_bundle_fix(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """
        Test that only the unsatisfied Brewfile is named and fixed
        """
        layers  = self._layers(tmp_path, with_brewfile=(True, True))
        drifted = layers[1] / 'bootstrap' / 'Brewfile'
        self._capture_with(monkeypatch, layers, unsatisfied={drifted})

        check = run.check_brewfiles()
        assert not check.ok
        assert str(drifted) in check.detail
        assert str(layers[0] / 'bootstrap' / 'Brewfile') not in check.detail
        assert check.fix is not None
        assert check.fix[:2] == ['bash', '-c']
        assert 'brew bundle --file' in check.fix[2]
        assert check.fix[-1] == str(drifted)

    def test_probe_is_read_only(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """
        Test that the check only runs "brew bundle check" with auto-update disabled
        """
        layers = self._layers(tmp_path, with_brewfile=(True,))
        seen   = self._capture_with(monkeypatch, layers)

        run.check_brewfiles()
        brewfile = layers[0] / 'bootstrap' / 'Brewfile'
        assert seen[1:] == [['env', 'HOMEBREW_NO_AUTO_UPDATE=1', 'brew', 'bundle', 'check', '--file', str(brewfile)]]

    def test_fails_when_layers_cannot_be_enumerated(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """
        Test that a broken overlay registry fails the check without probing brew
        """
        seen = self._capture_with(monkeypatch, [], layers_rc=1)

        assert not run.check_brewfiles().ok
        assert len(seen) == 1

    def test_fails_when_brew_is_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that a missing brew is reported rather than raising FileNotFoundError
        """
        monkeypatch.setattr(run.shutil, 'which', lambda name: None)
        assert not run.check_brewfiles().ok


class TestDoctorCheckOrder:
    """
    Tests for the order and gating of the full doctor check list
    """
    def test_full_run_includes_hooks_and_brewfile_checks(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that the slow Brewfile check runs last and the hooks check follows the git version check
        """
        for func, name in {
            'check_tools':       'tools',
            'check_layers':      'layers',
            'check_git_version': 'git',
            'check_hooks':       'hooks',
            'check_links':       'links',
            'check_render':      'render',
            'check_brewfiles':   'brewfile',
        }.items():
            monkeypatch.setattr(run, func, lambda name=name: run.DoctorCheck(name, True, 'ok'))

        assert [c.name for c in run.doctor_checks()] == ['tools', 'layers', 'git', 'hooks', 'links', 'render', 'brewfile']
```

- [ ] **Step 2: Run the tests; verify they fail**

Run: `scripts/hooks/uv-public.sh run --group test pytest tests/unit/test_run_doctor.py -q -p no:sugar`
Expected: FAIL — `AttributeError: module 'run' has no attribute 'GIT_HOOK_TYPES'` / `check_hooks` / `check_brewfiles`.

- [ ] **Step 3: Implement the constants** — in `run.py`, below the `# Doctor requirements` constants:

```python
# Git hook types `prek install` must have shimmed (mirrors `default_install_hook_types` in .pre-commit-config.yaml;
# a test keeps the two in sync) and the marker prek writes into every shim it generates
GIT_HOOK_TYPES: tuple[str, ...] = (
    'pre-commit',
    'commit-msg',
    'post-checkout',
    'post-merge',
    'post-rewrite',
    'pre-push',
)
PREK_SHIM_MARKER: str = 'generated by prek'
```

- [ ] **Step 4: Implement the layer probe and checks** — replace the body of `check_layers` and add the new functions
      (the long comment from `check_layers` moves with the probe):

```python
def _probe_layers() -> subprocess.CompletedProcess[str]:
    """
    Ask bootstrap/lib.sh for the layer directories (base first), one per stdout line
    """

    # DOTFILES_REPO is pinned to this checkout so an inherited value from another one cannot redirect the base layer.
    # Anything lib.sh or a layer env.sh prints while loading goes to stderr so it cannot be counted as a layer.
    script = 'export DOTFILES_REPO="$1"; source "$1/bootstrap/lib.sh" >&2 && dotfiles_layers'
    return _capture(['bash', '-c', script, 'doctor', str(DOTFILES_DIR)])


def check_layers() -> DoctorCheck:
    """
    Check that every registered overlay exists
    """
    result = _probe_layers()
    if result.returncode != 0:
        return DoctorCheck('layers', False, _first_line(result.stderr, 'overlay registry error'))

    count = len([line for line in result.stdout.splitlines() if line])
    return DoctorCheck('layers', True, f'{count} layer(s): base + {count - 1} overlay(s)')


def check_hooks() -> DoctorCheck:
    """
    Check that prek's git hook shims are installed for every type in :data:`GIT_HOOK_TYPES`

    The ``pre-push`` shim runs the public-repo leak guard, so a checkout without it pushes unscanned.
    """
    result = _capture(['git', 'rev-parse', '--git-path', 'hooks'])
    if result.returncode != 0:
        return DoctorCheck('hooks', False, _first_line(result.stderr, 'not a git checkout'))

    # Relative to the repo root in a plain checkout; the absolute common-dir path inside a linked worktree
    hooks_dir = DOTFILES_DIR / result.stdout.strip()

    missing: list[str] = []
    for hook_type in GIT_HOOK_TYPES:
        try:
            installed = PREK_SHIM_MARKER in (hooks_dir / hook_type).read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError):
            installed = False
        if not installed:
            missing.append(hook_type)

    if not missing:
        return DoctorCheck('hooks', True, f'{len(GIT_HOOK_TYPES)} prek hook shims installed')

    detail = f'missing prek shims: {", ".join(missing)}'
    if shutil.which('prek') is None:
        return DoctorCheck('hooks', False, f'{detail} (prek not on PATH)')
    return DoctorCheck('hooks', False, detail, ['prek', 'install'])


def check_brewfiles() -> DoctorCheck:
    """
    Check that every layer's Brewfile is satisfied (``brew bundle check``)

    Homebrew has no lockfile, so ``brew bundle check`` is the reproducibility signal; bootstrap stage 50-brew runs the
    same probe while applying the Brewfiles.
    """
    if shutil.which('brew') is None:
        return DoctorCheck('brewfile', False, 'brew not found')

    layers = _probe_layers()
    if layers.returncode != 0:
        return DoctorCheck('brewfile', False, 'cannot enumerate layers (see the layers check)')

    brewfiles = [
        brewfile
        for line in layers.stdout.splitlines()
        if line and (brewfile := Path(line) / 'bootstrap' / 'Brewfile').is_file()
    ]
    if not brewfiles:
        return DoctorCheck('brewfile', True, 'no Brewfiles declared')

    drifted = [
        brewfile
        for brewfile in brewfiles
        if _capture(
            ['env', 'HOMEBREW_NO_AUTO_UPDATE=1', 'brew', 'bundle', 'check', '--file', str(brewfile)],
        ).returncode != 0
    ]
    if not drifted:
        return DoctorCheck('brewfile', True, f'{len(brewfiles)} Brewfile(s) satisfied')

    install = 'for brewfile in "$@"; do brew bundle --file "$brewfile" || exit 1; done'
    return DoctorCheck(
        'brewfile',
        False,
        f'unsatisfied: {", ".join(folduser(brewfile) for brewfile in drifted)}',
        ['bash', '-c', install, 'doctor', *(str(brewfile) for brewfile in drifted)],
    )
```

and update `doctor_checks` and the `DoctorCommand` docstring:

```python
def doctor_checks() -> list[DoctorCheck]:
    """
    Run every doctor check (tools and layers first; the rest depend on them, and the slow Brewfile probe runs last)
    """
    first = [check_tools(), check_layers()]
    if not all(c.ok for c in first):
        return first
    return [*first, check_git_version(), check_hooks(), check_links(), check_render(), check_brewfiles()]
```

```python
class DoctorCommand(Command):
    """
    Check tools, overlays, git version and hooks, links, rendered settings, and Brewfiles
    """
```

- [ ] **Step 5: Regenerate the Makefile and run the tests**

```bash
scripts/hooks/uv-public.sh run python run.py makefile
scripts/hooks/uv-public.sh run --group test pytest tests/unit/test_run_doctor.py tests/unit/test_run_commands.py tests/unit/test_bootstrap_driver.py -q -p no:sugar
```

Expected: all pass; `git diff Makefile` shows only the new `doctor` description.

- [ ] **Step 6: Smoke-test against this checkout**

Run: `scripts/hooks/uv-public.sh run python run.py doctor`
Expected: a `hooks` line reading `6 prek hook shims installed` (shims live in the main checkout's `.git/hooks`, which this
linked worktree resolves through `git rev-parse --git-path hooks`) and a `brewfile` line; exit 0 on a converged machine.

- [ ] **Step 7: Lint and commit**

```bash
scripts/hooks/uv-public.sh run ruff check run.py tests/unit/test_run_doctor.py
git add run.py Makefile tests/unit/test_run_doctor.py
git commit -m "feat(run.py): doctor checks git hook shims and Brewfile drift"
```

______________________________________________________________________

### Task 7: `track-claude`

**Files:**

- Modify: `run.py` (constants near the filepaths `:106-125`; helper `find_untracked_claude_files`; new command before
  `TestCommand`)
- Modify: `tests/unit/test_run_commands.py` (`test_real_commands_registered`), `tests/unit/test_run_doctor.py`
  (`test_dotfiles_commands_registered`)
- Modify: `Makefile` (regenerated)
- Create: `tests/unit/test_run_track_claude.py`

**Interfaces:**

- Produces: `run.STOW_DIR`, `run.CLAUDE_STOW_DIR`, `run.CLAUDE_CONFIG_DIR`, `run.CLAUDE_TRACKED_SUBDIRS`,
  `run.CLAUDE_IGNORE_NAMES`; `run.find_untracked_claude_files() -> list[Path]`; `run.TrackClaudeCommand`
  (`name='track-claude'`, `group='Dotfiles'`, `-n/--dry-run`).
- Consumes: `confirm` (Task 5), `shell_command`, `STOW_SCRIPT`, `printf`, `style`, `folduser`, `ExitCode`.

- [ ] **Step 1: Write the failing tests** — create `tests/unit/test_run_track_claude.py`:

```python
"""
Unit tests for the run.py track-claude command
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import run


@pytest.fixture
def claude(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Path, Path]:
    """
    Point run.py at a throwaway ~/.claude and stow package; returns (config_dir, stow_dir)
    """
    config = tmp_path / 'home' / '.claude'
    stow   = tmp_path / 'repo' / 'stow' / 'claude' / '.claude'
    config.mkdir(parents=True)
    stow.mkdir(parents=True)
    monkeypatch.setattr(run, 'CLAUDE_CONFIG_DIR', config)
    monkeypatch.setattr(run, 'CLAUDE_STOW_DIR',   stow)
    return config, stow


def _write(path: Path, text: str = 'x') -> Path:
    """
    Write a file, creating parent directories
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


class TestFindUntrackedClaudeFiles:
    """
    Tests for detecting local Claude files that are not yet in the repo
    """
    def test_finds_real_files_in_tracked_subdirs(self, claude: tuple[Path, Path]) -> None:
        """
        Test that regular files under a tracked subdirectory are reported, sorted
        """
        config, _ = claude
        b = _write(config / 'skills' / 'foo' / 'SKILL.md')
        a = _write(config / 'agents' / 'new.md')
        r = _write(config / 'rules' / 'mine.md')
        assert run.find_untracked_claude_files() == sorted([a, b, r])

    def test_ignores_symlinks_ds_store_and_untracked_subdirs(self, claude: tuple[Path, Path]) -> None:
        """
        Test that stowed symlinks, .DS_Store, and files outside the tracked subdirectories are not reported
        """
        config, stow = claude
        target = _write(stow / 'agents' / 'tracked.md')
        (config / 'agents').mkdir()
        (config / 'agents' / 'tracked.md').symlink_to(target)
        _write(config / 'agents' / '.DS_Store')
        _write(config / 'projects' / 'session.jsonl')
        _write(config / 'plugins' / 'cache.json')

        assert run.find_untracked_claude_files() == []

    def test_does_not_descend_into_symlinked_directories(self, claude: tuple[Path, Path]) -> None:
        """
        Test that repo files reached through a symlinked directory are not mistaken for local files
        """
        config, stow = claude
        _write(stow / 'skills' / 'linked' / 'SKILL.md')
        (config / 'skills').mkdir()
        (config / 'skills' / 'linked').symlink_to(stow / 'skills' / 'linked')

        assert run.find_untracked_claude_files() == []

    def test_skips_a_tracked_subdir_that_is_itself_a_symlink(self, claude: tuple[Path, Path]) -> None:
        """
        Test that a symlinked tracked subdirectory is skipped (ingesting would move repo files onto themselves)
        """
        config, stow = claude
        _write(stow / 'hooks' / 'guard.sh')
        (config / 'hooks').symlink_to(stow / 'hooks')

        assert run.find_untracked_claude_files() == []


class TestTrackClaudeCommand:
    """
    Tests for the track-claude command flow
    """
    @staticmethod
    def _run(dry_run: bool = False) -> None:
        """
        Invoke track-claude through the registry
        """
        run.get_commands()['track-claude'](argparse.Namespace(dry_run=dry_run))

    @staticmethod
    def _record_shell(monkeypatch: pytest.MonkeyPatch, returncode: int = 0) -> list[list[str]]:
        """
        Patch shell_command to record commands; a nonzero code raises like check=True would
        """
        calls: list[list[str]] = []

        def fake_shell_command(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append(cmd)
            if returncode:
                raise run.ShellCommandError(returncode, run.shlex.join(cmd))
            return subprocess.CompletedProcess(cmd, 0, stdout='', stderr='')

        monkeypatch.setattr(run, 'shell_command', fake_shell_command)
        return calls

    def test_registered_in_dotfiles_group(self) -> None:
        """
        Test that track-claude is a Dotfiles command
        """
        assert 'track-claude' in run.get_commands(by_group=True)['Dotfiles']

    def test_nothing_to_track(
        self,
        claude: tuple[Path, Path],
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that an empty result reports success without prompting or restowing
        """
        calls = self._record_shell(monkeypatch)
        monkeypatch.setattr(run, 'confirm', lambda *args, **kwargs: pytest.fail('must not prompt'))

        self._run()
        assert 'Nothing to track' in run.unstyle(capsys.readouterr().out)
        assert calls == []

    def test_dry_run_moves_nothing(self, claude: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that --dry-run neither prompts, moves files, nor restows
        """
        config, stow = claude
        src = _write(config / 'agents' / 'new.md')
        calls = self._record_shell(monkeypatch)
        monkeypatch.setattr(run, 'confirm', lambda *args, **kwargs: pytest.fail('must not prompt'))

        self._run(dry_run=True)
        assert src.exists()
        assert not (stow / 'agents' / 'new.md').exists()
        assert calls == []

    def test_declined_confirmation_leaves_files_in_place(
        self,
        claude: tuple[Path, Path],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Test that answering no cancels without moving or restowing
        """
        config, stow = claude
        src = _write(config / 'agents' / 'new.md')
        calls = self._record_shell(monkeypatch)
        monkeypatch.setattr(run, 'confirm', lambda *args, **kwargs: False)

        self._run()
        assert src.exists()
        assert not (stow / 'agents' / 'new.md').exists()
        assert calls == []

    def test_conflicting_destination_is_skipped(self, claude: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that a file whose repo counterpart already exists is left alone and never overwritten
        """
        config, stow = claude
        local = _write(config / 'agents' / 'dup.md', 'local')
        repo  = _write(stow / 'agents' / 'dup.md', 'repo')
        self._record_shell(monkeypatch)
        monkeypatch.setattr(run, 'confirm', lambda *args, **kwargs: pytest.fail('nothing movable, must not prompt'))

        self._run()
        assert local.read_text(encoding='utf-8') == 'local'
        assert repo.read_text(encoding='utf-8')  == 'repo'

    def test_confirmed_files_move_into_the_repo_and_claude_is_restowed(
        self,
        claude: tuple[Path, Path],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Test that confirmed files move (creating parent dirs) and the claude package is restowed with stow.sh
        """
        config, stow = claude
        _write(config / 'skills' / 'foo' / 'SKILL.md', 'skill')
        calls = self._record_shell(monkeypatch)
        monkeypatch.setattr(run, 'confirm', lambda *args, **kwargs: True)

        self._run()
        assert not (config / 'skills' / 'foo' / 'SKILL.md').exists()
        assert (stow / 'skills' / 'foo' / 'SKILL.md').read_text(encoding='utf-8') == 'skill'
        assert calls == [['bash', str(run.STOW_SCRIPT), 'claude']]

    def test_failed_restow_exits_command_failed(self, claude: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that a failing restow exits 1 after the files were already moved
        """
        config, stow = claude
        _write(config / 'agents' / 'new.md')
        self._record_shell(monkeypatch, returncode=1)
        monkeypatch.setattr(run, 'confirm', lambda *args, **kwargs: True)

        with pytest.raises(SystemExit) as exc_info:
            self._run()
        assert exc_info.value.code == run.ExitCode.COMMAND_FAILED
        assert (stow / 'agents' / 'new.md').exists()
```

Also update the two registry tests. In `tests/unit/test_run_commands.py::test_real_commands_registered` append
`'track-claude'` before `'test'`:

```python
            'doctor', 'bootstrap', 'stow', 'render', 'track-claude', 'test',
```

and in `tests/unit/test_run_doctor.py::test_dotfiles_commands_registered`:

```python
        assert set(group) == {'bootstrap', 'stow', 'render', 'doctor', 'test', 'track-claude'}
```

- [ ] **Step 2: Run the tests; verify they fail**

Run: `scripts/hooks/uv-public.sh run --group test pytest tests/unit/test_run_track_claude.py -q -p no:sugar`
Expected: FAIL — `AttributeError: module 'run' has no attribute 'CLAUDE_CONFIG_DIR'`.

- [ ] **Step 3: Implement the constants** — in `run.py`'s filepaths block add `STOW_DIR` and `CLAUDE_STOW_DIR` (after
      `RENDER_SCRIPT`/`UV_PUBLIC`), and the Claude configuration constants after the `Doctor requirements` block:

```python
STOW_DIR:         Path = DOTFILES_DIR / 'stow'
CLAUDE_STOW_DIR:  Path = STOW_DIR / 'claude' / '.claude'
```

```python
# Hand-authored Claude Code config that `track-claude` ingests into the `claude` stow package. Machine-managed state
# (plugins/, projects/, caches) stays untracked; stowed files are symlinks, so a regular file here is local-only.
CLAUDE_CONFIG_DIR:      Path      = Path.home() / '.claude'
CLAUDE_TRACKED_SUBDIRS: list[str] = ['agents', 'commands', 'skills', 'hooks', 'rules']
CLAUDE_IGNORE_NAMES:    set[str]  = {'.DS_Store'}
```

- [ ] **Step 4: Implement the helper** — in `run.py`, next to the other module-level helpers (before the Dotfiles
      command section):

```python
def find_untracked_claude_files() -> list[Path]:
    """
    Find real (non-symlink) files under the tracked ``~/.claude`` subdirectories

    Stowed agents/commands/skills/hooks/rules are symlinks into the repo, so any regular file is something Claude Code
    or the user created locally that the ``claude`` stow package does not have yet. Symlinked directories are never
    descended into, and a tracked subdirectory that is itself a symlink is skipped, so repo files reached through a
    link are never mistaken for local ones.

    :return: sorted absolute paths of untracked files
    """
    untracked: list[Path] = []
    for subdir in CLAUDE_TRACKED_SUBDIRS:
        base = CLAUDE_CONFIG_DIR / subdir
        if base.is_symlink() or not base.is_dir():
            continue

        for dirpath, _dirnames, filenames in os.walk(base):
            for filename in filenames:
                if filename in CLAUDE_IGNORE_NAMES:
                    continue

                path = Path(dirpath) / filename
                if not path.is_symlink():
                    untracked.append(path)

    return sorted(untracked)
```

- [ ] **Step 5: Implement the command** — in `run.py`, after `RenderCommand` and before `TestCommand`:

```python
class TrackClaudeCommand(Command):
    """
    Ingest new ~/.claude agents, commands, skills, hooks, and rules into the repo
    """
    name:  ClassVar[str] = 'track-claude'
    group: ClassVar[str] = 'Dotfiles'

    class Args(argparse.Namespace):
        dry_run: bool       # --dry-run

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            '-n',
            '--dry-run',
            action='store_true',
            help='Preview what would be ingested without moving anything',
        )

    def run(self, args: Args) -> None:
        untracked = find_untracked_claude_files()
        if not untracked:
            printf('✅ Nothing to track: everything under ~/.claude is already in the repo', fg='bright_green')
            return

        printf(
            f'Found {len(untracked)} untracked file(s) under {folduser(CLAUDE_CONFIG_DIR)}:',
            bold=True,
            fg='bright_white',
        )

        # Plan moves: src (real file in ~/.claude) -> dst (mirrored path in the stow package). A dst that already
        # exists is a conflict (the repo has a different file there) and is left untouched.
        moves:     list[tuple[Path, Path]] = []
        conflicts: list[Path]              = []
        for src in untracked:
            rel = src.relative_to(CLAUDE_CONFIG_DIR)
            dst = CLAUDE_STOW_DIR / rel
            if dst.exists():
                conflicts.append(rel)
                printf(f'{style("CONFLICT", fg="red")}  {rel}', indent=2)
            else:
                moves.append((src, dst))
                printf(f'{style("→ repo", fg="green")}  {rel}', indent=2)

        if conflicts:
            printf('')
            printf(f'🟡 {len(conflicts)} file(s) already exist in the repo; skipped (resolve manually)', fg='yellow')

        if not moves:
            printf('')
            printf('Nothing to move.', fg='yellow')
            return

        if args.dry_run:
            printf('')
            printf(f'Dry run: would move {len(moves)} file(s) and restow. No changes made.', fg='cyan')
            return

        printf('')
        if not confirm(f'Move {len(moves)} file(s) into the repo and restow?'):
            printf('⚠️  Cancelled', fg='yellow')
            return

        for src, dst in moves:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            printf(f'└─ {src.relative_to(CLAUDE_CONFIG_DIR)}', fg='green')

        # The source paths are vacant now, so a plain restow links the moved files back in without conflicts
        printf('')
        printf('🔗 Restowing claude package...', fg='bright_cyan')
        try:
            shell_command(['bash', str(STOW_SCRIPT), 'claude'], indent=3)
        except subprocess.CalledProcessError:
            printf('❌ Restow failed: files moved into the repo, but symlinks may be incomplete', fg='red', bold=True)
            printf(f'Re-run: {style("python3 run.py stow claude", fg="bright_magenta")}', indent=3)
            sys.exit(ExitCode.COMMAND_FAILED)

        printf('')
        printf(f'✅ Ingested {len(moves)} file(s). Review and commit them:', fg='bright_green', bold=True)
        printf(style('git add stow/claude/.claude && git commit', fg='bright_magenta'), indent=3)
```

- [ ] **Step 6: Regenerate the Makefile and run the tests**

```bash
scripts/hooks/uv-public.sh run python run.py makefile
scripts/hooks/uv-public.sh run --group test pytest tests/unit/test_run_track_claude.py tests/unit/test_run_doctor.py tests/unit/test_run_commands.py -q -p no:sugar
```

Expected: all pass; `git diff Makefile` shows only the new `track-claude` entry.

- [ ] **Step 7: Smoke-test (dry run only)**

Run: `scripts/hooks/uv-public.sh run python run.py track-claude --dry-run`
Expected: either `Nothing to track…` or a listing of local files with `Dry run: would move N file(s)`; nothing is moved.

- [ ] **Step 8: Lint and commit**

```bash
scripts/hooks/uv-public.sh run ruff check run.py tests/unit/test_run_track_claude.py
git add run.py Makefile tests/unit/test_run_track_claude.py tests/unit/test_run_commands.py tests/unit/test_run_doctor.py
git commit -m "feat(run.py): add track-claude to ingest local ~/.claude config into the stow package"
```

______________________________________________________________________

### Task 8: Documentation, full verification, and PR

**Files:**

- Modify: `run.py` (module docstring `:1-56`)
- Modify: `docs/RUN_PY_REFERENCE.md`, `README.md`, `.ctx/ARCHITECTURE.md`, `.ctx/BUILD.md`

- [ ] **Step 1: `run.py` module docstring** — update three spots:

```text
- **Codebase**: Clean build artifacts, run and prepare prek hooks, generate Makefile
- **NAS**: Provision the home NAS and deploy its Compose services
- **Dotfiles**: Wrap the layered engine (doctor, bootstrap, stow, render, test) and ingest local Claude config
  (track-claude)
```

and, under `Environment Variables`, add `- NO_COLOR: Disable ANSI styling when set to any non-empty value`.

- [ ] **Step 2: `docs/RUN_PY_REFERENCE.md`**

(a) Replace the whole `#### \`pre\`` section (from `#### \`pre\`` through the `See [\`.pre-commit-config.yaml\`]…` line)
with:

````markdown
#### `run-hooks`

Run prek hooks on modified or specified project files.

```bash
python3 run.py run-hooks                          # hooks on the staged files
python3 run.py run-hooks mdformat ruff            # only these hooks (names go before --files)
python3 run.py run-hooks --files README.md docs/README.md
python3 run.py run-hooks --last-commit            # the files of the last commit
python3 run.py run-hooks -s main -o HEAD          # the files changed between two refs
python3 run.py run-hooks --stage pre-push --dry-run
```

| Option                                            | Forwards                                     |
| ------------------------------------------------- | -------------------------------------------- |
| `HOOK\|PROJECT...`                                | hook or project filter (placed first)        |
| `-a/--all-files`, `--files`, `-d/--directory`     | file selection                               |
| `-s/--from-ref`, `-o/--to-ref`, `--last-commit`   | ref range selection                          |
| `--skip` (repeatable), `--stage`                  | skip hooks, choose the git stage             |
| `--show-diff-on-failure`, `--fail-fast`, `--dry-run`, `-v` | run behavior                        |

**Behavior:** runs `prek run …` with inherited stdio and exits with prek's return code (so `make pre` fails when a hook
fails). The hook filter is placed before the options because prek's `--files` is greedy.

#### `pre`

Run prek hooks on all project files. This is `run-hooks --all-files`: it accepts the same hook filter, ref, and run
options but not the file-selection options.

```bash
python3 run.py pre
python3 run.py pre mdformat               # one hook over every file
```

**Hooks include:**

- File integrity checks (large files, merge conflicts, private keys, detect-secrets)
- Python validation (syntax, debug statements, ruff, mypy, interrogate)
- Data format validation (JSON, YAML, TOML, XML)
- Formatters (shfmt, taplo, mdformat, ruff --fix-only)
- Linters (shellcheck, yamllint, codespell)
- Whitespace and line ending fixers

See [`.pre-commit-config.yaml`](../.pre-commit-config.yaml) for complete hook configuration.

#### `prepare-hooks`

Prepare the environments of all prek hooks (`prek prepare-hooks`) so the first commit does not pay for it. Accepts a
`HOOK|PROJECT` filter, `--skip` (repeatable), and `-v/--verbose`.
````

(b) In `### Dotfiles`: add `track-claude` to the table and update the `doctor` row and intro:

```markdown
| `doctor`       | (runs the checks below)      | `-f/--fix`, `-y/--yes`                                                                    |
| `track-claude` | (moves files, then `stow.sh claude`) | `-n/--dry-run`                                                                    |
```

(c) Replace the `doctor` check table and the paragraph after it with:

```markdown
| Check       | Passes when                                                                                          | Fix (`--fix`)                     |
| ----------- | ---------------------------------------------------------------------------------------------------- | --------------------------------- |
| `tools`     | `brew`, `git`, `stow`, `uv`, `zsh` are on `PATH`                                                     | none                              |
| `layers`    | the overlay registry resolves (`dotfiles_layers` in `bootstrap/lib.sh`) and every overlay exists     | none                              |
| `git`       | `git --version` is at least 2.36 (needed for `includeIf "hasconfig:remote.*.url:"`)                  | none                              |
| `hooks`     | every hook type in `default_install_hook_types` has a prek-generated shim in the git hooks directory | `prek install`                    |
| `links`     | `stow.sh -n` reports `no changes` or `no packages found`                                             | `stow.sh --backup-conflicts`      |
| `render`    | `render.py --check` exits 0 (exit 1 is drift; exit 2 is a config or I/O error with no fix)           | `render.py` (without `--force`)   |
| `brewfile`  | `brew bundle check` passes for every layer's `bootstrap/Brewfile`                                    | `brew bundle --file` per Brewfile |

`--fix` asks before running each failing check's fix, then re-runs every check and reports the final state; `-y/--yes`
applies the fixes without asking (and implies `--fix`). The `links` fix runs `stow.sh --backup-conflicts`, which moves
any blocking files into `~/.dotfiles-backup/<timestamp>/` before linking. Without `--fix`, every probe is read-only
(`stow.sh -n`, `render.py --check`, `brew bundle check`). The `hooks` check resolves the hooks directory with
`git rev-parse --git-path hooks`, so it is correct in linked worktrees; it matters because `pre-push` runs the
public-repo leak guard and no bootstrap stage installs hooks. `bootstrap --verify` invokes `doctor` after all stages
succeed.

#### `track-claude`

Moves real files that Claude Code (or you) created under `~/.claude/{agents,commands,skills,hooks,rules}` into
`stow/claude/.claude`, then restows the `claude` package so the originals become symlinks into the repo.

```bash
python3 run.py track-claude --dry-run     # list what would be ingested
python3 run.py track-claude               # confirm, move, restow
```

A file whose repo counterpart already exists is reported as a conflict and left alone. Stowed files are symlinks, so
any regular file counts as local-only; `plugins/`, `projects/`, and other state directories are never touched. Review
and commit the result with `git add stow/claude/.claude && git commit`.
```

(d) In `### Constants` → environment variables, add `NO_COLOR = bool(os.getenv('NO_COLOR'))` with the comment
`# Disable ANSI styling (any non-empty value)`; in `### Environment Variable Configuration` add
`export NO_COLOR=1` with the comment `# Plain output (also useful when piping to a file)`.

- [ ] **Step 3: `README.md`** — in the `Environment Variables` table add the row
      `| \`NO_COLOR\` | Disable ANSI styling in run.py output (any non-empty value) | unset |`; change the doctor comment
      (`# Verify tools, overlay registry, links, and rendered settings`) to
      `# Verify tools, overlays, git hooks, links, rendered settings, and Brewfiles`; and in `Testing Changes` change
      `# Run prek hooks` to `# Run prek hooks (python3 run.py run-hooks --last-commit for just the last commit)`.

- [ ] **Step 4: `.ctx/ARCHITECTURE.md`** — replace the **Codebase** and **Layered dev environment** category lines and the
      `run.py doctor` bullet:

```markdown
- **Codebase**: `clean`, `run-hooks`, `pre`, `prepare-hooks`, `install-hooks`, `uninstall-hooks`, `makefile`
- **NAS**: `nas-provision`, `nas-deploy`
- **Layered dev environment**: `bootstrap`, `stow`, `render`, `doctor`, `track-claude`, `test`
```

```markdown
- **`run.py doctor`**: verifies tools, overlay registry, git version and hook shims, links, rendered settings, and
  Brewfiles (`--fix` asks before each repair; `--yes` skips the prompts).
```

- [ ] **Step 5: `.ctx/BUILD.md`** — after the `python3 run.py pre` example in the command list add:

```bash
# Run hooks on specific hooks/files/refs (names before --files)
python3 run.py run-hooks mdformat --last-commit
python3 run.py run-hooks --files README.md
```

and in the Layered Dev Environment block replace the two doctor lines with:

```bash
# Verify tools, overlays, git version and hooks, links, rendered settings, and Brewfiles (--fix asks first; --yes skips)
python3 run.py doctor
python3 run.py doctor --fix

# Move local ~/.claude agents/commands/skills/hooks/rules into stow/claude and restow (--dry-run previews)
python3 run.py track-claude
```

- [ ] **Step 6: Format the touched markdown and run the full gate**

```bash
scripts/hooks/uv-public.sh run prek run --files README.md docs/RUN_PY_REFERENCE.md
scripts/hooks/uv-public.sh run python run.py makefile
scripts/hooks/uv-public.sh run --group test pytest -q -p no:sugar
scripts/hooks/uv-public.sh run ruff check
scripts/hooks/uv-public.sh run prek run --all-files
```

Expected: pytest all green (the 902-test baseline plus the new tests, 3 skipped as before); ruff clean; all prek hooks
pass; `git status` shows no Makefile diff after regeneration. `.ctx/` and `docs/plans/` are excluded from mdformat, so
those edits stay hand-formatted at 120 columns.

- [ ] **Step 7: Verify behavior against main** (per "diff behavior between main and your changes")

```bash
scripts/hooks/uv-public.sh run python run.py --help | head -40
scripts/hooks/uv-public.sh run python run.py doctor
scripts/hooks/uv-public.sh run python run.py run-hooks --dry-run --last-commit
NO_COLOR=1 scripts/hooks/uv-public.sh run python run.py doctor | cat -v | grep -c '\^\[' || true
```

Expected: help lists `run-hooks`, `prepare-hooks`, `track-claude`; doctor shows `hooks` and `brewfile` lines; the
`NO_COLOR` run prints `0` escape sequences.

- [ ] **Step 8: Commit and open the PR**

```bash
git add run.py docs/RUN_PY_REFERENCE.md README.md .ctx/ARCHITECTURE.md .ctx/BUILD.md Makefile
git commit -m "docs: document run-hooks, doctor hooks/brewfile checks, track-claude, NO_COLOR"
git push -u origin worktree-work-parity-hooks-doctor
gh pr create --title "run.py: hook commands, doctor checks, track-claude (work parity A)" --body "$(cat <<'EOF'
## Summary

First of two PRs porting the useful parts of the work dotfiles' `run.py` (design:
`docs/plans/2026-11/2026-11-02-work-parity-design.md`).

- `run-hooks` / `prepare-hooks`; `pre` is now a `run-hooks` subclass (hook filter, `--files`, ref ranges,
  `--last-commit`, `--skip`, `--stage`, `--fail-fast`, ...)
- `doctor`: new `hooks` check (prek shims for all six hook types, worktree-safe) and `brewfile` drift check
- `track-claude`: ingest local `~/.claude` agents/commands/skills/hooks/rules into `stow/claude` and restow
- `NO_COLOR` support; PEP 723 metadata block on `run.py`; `list-hosts` reports a missing PyYAML distinctly

## Behavior changes

- `doctor --fix` now asks before each fix; `-y/--yes` skips the prompts and implies `--fix`
- `pre` now exits with prek's return code (it previously ignored it)

## Test plan

- [x] `pytest` full suite green (902 baseline + new tests), `ruff check` clean, `prek run --all-files` green
- [x] `run.py doctor` shows the `hooks` and `brewfile` lines; `run-hooks --dry-run --last-commit` and
  `track-claude --dry-run` smoke-tested
- [x] `NO_COLOR=1` output contains no escape sequences

PR B (install-uv/install-hatch/diagnose, uv/venv helpers with `uv-public.sh`, lock commands) stacks on this branch.
EOF
)"
```

Adjust the checked boxes to what was actually run before opening the PR; do not claim a check that was skipped.

- [ ] **Step 9: Hand off**

Per the worktree-cleanup convention, once the PR is open, leave the worktree (`ExitWorktree` with `action: "keep"`
until PR B's worktree is created from this branch, then remove this worktree and keep the branch). Write PR B's plan
(`docs/plans/2026-11/2026-11-02-work-parity-b-plan.md`) against the then-current `run.py`.
