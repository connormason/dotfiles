# Split `run.py` into a `cli/` package Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move `run.py`'s infrastructure, utilities, and commands into a top-level `cli/` package while `run.py` stays the entry point and every observable behavior (help text, Makefile, exit codes) is unchanged.

**Architecture:** A throwaway script slices the pre-split `run.py` by original line number into modules, so code moves verbatim; `ruff` prunes unused imports and a symbol index adds the cross-module ones. Shared mutable state (`RUN_DEBUG`) is read through `cli.infra.config`. Tests are retargeted to patch where each name is used.

**Tech Stack:** Python 3.9-compatible stdlib only, `uv`, `ruff check` (never `ruff format`), `pytest`, `mdformat`, `prek`.

**Spec:** `docs/plans/2026-11/2026-11-21-run-py-split-design.md`

## Global Constraints

- Run all Python via `uv run ...`; never bare `python`/`python3`/`pip`. Never run `ruff format`.
- Package `cli/` is stdlib-only and stays compatible with Python >= 3.9 (`from __future__ import annotations` first).
- isort `force-single-line = true`: one import per line. Single quotes for inline strings. Sphinx docstrings, multi-line.
- Public modules define `__all__` after imports; `run.py` (a script) does not.
- No behavior change: `--help`, every `<command> -h`, and the regenerated `Makefile` stay byte-identical (checked with
  `NO_COLOR=1`).
- Tests must pass at every commit. Tasks 3 and 4 land as one commit for that reason.
- Use `$TMPDIR`, never `/tmp`. Scratch files live in `$TMPDIR/runsplit/`.
- Git: plain commands run from the worktree root; no `-C`; no pushing; no PR unless the user asks.
- Baseline: 321 tests pass in `tests/unit/run/` at origin/main `7c785bd`. Snapshots of the pre-split help output are in
  `$TMPDIR/runsplit/before/`; the pre-split source is `$TMPDIR/runsplit/run_original.py` (line numbers below refer to
  it).

---

## Module manifest (line ranges are inclusive, in `run_original.py`)

| Target module                      | Source ranges                                                                              |
| ---------------------------------- | ------------------------------------------------------------------------------------------ |
| `cli/infra/config.py`              | 125-177, 203-210, 241-245, 265-269, 271-297, 306-429                                       |
| `cli/infra/types.py`               | 431-470                                                                                    |
| `cli/infra/command.py`             | 471-664                                                                                    |
| `cli/infra/main.py`                | 5539-5727                                                                                  |
| `cli/utils/formatting.py`          | 665-733                                                                                    |
| `cli/utils/styling.py`             | 734-1073                                                                                   |
| `cli/utils/prompts.py`             | 1074-1132                                                                                  |
| `cli/utils/shell.py`               | 1133-1459                                                                                  |
| `cli/utils/scripts.py`             | 1460-1622                                                                                  |
| `cli/utils/retry.py`               | 1623-1669                                                                                  |
| `cli/utils/python.py`              | 1670-1700                                                                                  |
| `cli/utils/nas.py`                 | 1701-1729, 2577-2616                                                                       |
| `cli/utils/uv.py`                  | 1730-2098                                                                                  |
| `cli/utils/venv.py`                | 2099-2429                                                                                  |
| `cli/utils/ansible.py`             | 2430-2576                                                                                  |
| `cli/utils/homeassistant.py`       | 179-200, 299-303, 2617-2972                                                                |
| `cli/utils/claude.py`              | 247-259, 2973-3010                                                                         |
| `cli/utils/doctor_checks.py`       | 3011-3269                                                                                  |
| `cli/commands/setup.py`            | 212-238, 3270-3624                                                                         |
| `cli/commands/deploy.py`           | 3625-3997                                                                                  |
| `cli/commands/dotfiles.py`         | 261-262, 3998-4335                                                                         |
| `cli/commands/inventory.py`        | 4336-4730                                                                                  |
| `cli/commands/tools.py`            | 4731-4812                                                                                  |
| `cli/commands/hooks.py`            | 4813-5176                                                                                  |
| `cli/commands/testing.py`          | 5177-5210                                                                                  |
| `cli/commands/analysis.py`         | 5211-5263                                                                                  |
| `cli/commands/dependencies.py`     | 5264-5380                                                                                  |
| `cli/commands/utilities.py`        | 5381-5538                                                                                  |

Line ranges not listed (1-124 header/imports, 5728-5730 `__main__` guard) stay in the slim `run.py`.

Exact-text rewrites applied by the script (each asserts it matched exactly the stated count):

| Module                  | Old                                                  | New                                                                                  |
| ----------------------- | ---------------------------------------------------- | ------------------------------------------------------------------------------------ |
| `config.py`             | `SCRIPT_PATH:            Path = Path(__file__)`      | `DOTFILES_DIR:           Path = Path(__file__).parents[2]` (and drop the old `DOTFILES_DIR = SCRIPT_PATH.parent` line) |
| `config.py`             | (after the above)                                    | `SCRIPT_PATH:            Path = DOTFILES_DIR / 'run.py'`                              |
| `styling.py`            | `if debug and not RUN_DEBUG:`                        | `if debug and not config.RUN_DEBUG:`                                                 |
| `scripts.py`            | `if not RUN_DEBUG:`                                  | `if not config.RUN_DEBUG:`                                                           |
| `main.py`               | `default=RUN_DEBUG,`                                 | `default=config.RUN_DEBUG,`                                                          |
| `main.py`               | `repr(RUN_DEBUG)`                                    | `repr(config.RUN_DEBUG)`                                                             |
| `main.py`               | `if RUN_DEBUG else`                                  | `if config.RUN_DEBUG else`                                                           |
| `main.py`               | `    global RUN_DEBUG\n\n`                           | (removed)                                                                            |
| `main.py`               | `    RUN_DEBUG = args.debug`                         | `    config.RUN_DEBUG = args.debug`                                                  |
| `main.py`               | `            if RUN_DEBUG:`                          | `            if config.RUN_DEBUG:`                                                   |
| `utilities.py`          | `Path(__file__).name`                                | `SCRIPT_PATH.name` (2 matches)                                                       |

Modules that rewrite to `config.RUN_DEBUG` also get `from cli.infra import config`.

---

### Task 1: Extraction tooling, `cli/infra/config.py`, `cli/infra/types.py`

**Files:**
- Create: `$TMPDIR/runsplit/extract.py` (throwaway, not committed), `$TMPDIR/runsplit/run_original.py`
- Create: `cli/__init__.py`, `cli/infra/__init__.py`, `cli/utils/__init__.py`, `cli/commands/__init__.py` (temporarily empty)
- Create: `cli/infra/config.py`, `cli/infra/types.py`
- Modify: `pyproject.toml` (ruff per-file-ignores: add `"cli/**/*.py" = ["BLE001", "S112"]`; interrogate exclude: add `"cli/commands/"`)

**Interfaces:**
- Produces: `cli.infra.config` (every constant, env value, path, `ExitCode`, `VERSION_RE`, mutable `RUN_DEBUG`),
  `cli.infra.types` (`F`, `T_contra`, `ModT`, `PathLike`, `StyleColor`, `CommandFunc`, `AddArgumentsFunc`,
  `SupportsWrite`, `ToolInfo`, `SSHTarget`). Later tasks import these by name.

- [ ] **Step 1: Save the pre-split source**

Run: `git show 7c785bd:run.py > "$TMPDIR/runsplit/run_original.py"` then `wc -l "$TMPDIR/runsplit/run_original.py"`
Expected: `5730`.

- [ ] **Step 2: Write `extract.py`**

The script takes a list of target module paths on the command line, builds each from the manifest, and then runs the fix-up loop. It must implement exactly this:

```python
#!/usr/bin/env python3
"""Throwaway: slice the pre-split run.py into the cli/ package (see docs/plans/2026-11/2026-11-21-run-py-split-plan.md)"""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
TMP = Path(os.environ['TMPDIR']) / 'runsplit'
ORIG = (TMP / 'run_original.py').read_text(encoding='utf-8').splitlines()
IMPORT_HEADER = '\n'.join(ORIG[75:122])              # original lines 76-122: every import plus the TYPE_CHECKING block

MANIFEST: dict[str, list[tuple[int, int]]] = {
    # fill from the "Module manifest" table above, e.g.
    'cli/infra/config.py': [(125, 177), (203, 210), (241, 245), (265, 269), (271, 297), (306, 429)],
    'cli/infra/types.py':  [(431, 470)],
    # ... one entry per row of the table ...
}
DOCSTRINGS: dict[str, str] = {
    'cli/infra/config.py': 'Constants, environment-derived values, project paths, exit codes, and runtime flags',
    # ... one entry per module ...
}
REWRITES: dict[str, list[tuple[str, str, int]]] = {
    # module -> [(old, new, expected_count)] from the "Exact-text rewrites" table above
}
CONFIG_IMPORT_MODULES = {'cli/utils/styling.py', 'cli/utils/scripts.py', 'cli/infra/main.py'}


def body(module: str) -> str:
    chunks = ['\n'.join(ORIG[a - 1:b]) for a, b in MANIFEST[module]]
    text = '\n\n\n'.join(chunks)
    for old, new, count in REWRITES.get(module, []):
        assert text.count(old) == count, (module, old, text.count(old))
        text = text.replace(old, new)
    return text


def write_module(module: str) -> None:
    extra = 'from cli.infra import config\n' if module in CONFIG_IMPORT_MODULES else ''
    text = (
        f'"""\n{DOCSTRINGS[module]}\n"""\n'
        f'from __future__ import annotations\n\n{IMPORT_HEADER}\n{extra}\n# __ALL__ MARKER\n\n\n{body(module)}\n'
    )
    path = ROOT / module
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def top_level_names(path: Path) -> list[str]:
    names: list[str] = []
    for node in ast.parse(path.read_text(encoding='utf-8')).body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            names.append(node.name)
        elif isinstance(node, ast.Assign):
            names += [t.id for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.append(node.target.id)
    return names


def symbol_index() -> dict[str, str]:
    index: dict[str, str] = {}
    for module in MANIFEST:
        # names come from the freshly written body, before ruff touches the imports
        for name in top_level_names(ROOT / module):
            index.setdefault(name, module.removesuffix('.py').replace('/', '.'))
    return index


def ruff(*args: str, files: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(['uv', 'run', 'ruff', 'check', *args, *files], capture_output=True, text=True, check=False)


def add_missing_imports(modules: list[str], index: dict[str, str]) -> None:
    for module in modules:
        out = ruff('--select', 'F821', '--output-format', 'json', '--no-fix', files=[module])
        missing = sorted({d['message'].split('`')[1] for d in json.loads(out.stdout or '[]')})
        path = ROOT / module
        text = path.read_text(encoding='utf-8')
        lines = ''.join(f'from {index[n]} import {n}\n' for n in missing if n in index and index[n] != module.removesuffix('.py').replace('/', '.'))
        text = text.replace('\n# __ALL__ MARKER', f'{lines}\n# __ALL__ MARKER', 1)
        path.write_text(text, encoding='utf-8')
        unresolved = [n for n in missing if n not in index]
        if unresolved:
            print(f'UNRESOLVED in {module}: {unresolved}', file=sys.stderr)


def finalize(modules: list[str]) -> None:
    ruff('--select', 'F401,I001,TC001,TC002,TC003', '--fix', '--unsafe-fixes', files=modules)
    for module in modules:
        path = ROOT / module
        public = sorted(n for n in top_level_names(path) if not n.startswith('_'))
        block = '__all__ = [\n' + ''.join(f"    '{n}',\n" for n in public) + ']'
        path.write_text(path.read_text(encoding='utf-8').replace('# __ALL__ MARKER', block, 1), encoding='utf-8')


if __name__ == '__main__':
    targets = sys.argv[1:] or list(MANIFEST)
    for m in targets:
        write_module(m)
    idx = symbol_index()
    (TMP / 'symbols.json').write_text(json.dumps(idx, indent=2, sort_keys=True), encoding='utf-8')
    add_missing_imports(targets, idx)
    finalize(targets)
```

Complete `MANIFEST`, `DOCSTRINGS`, and `REWRITES` from the tables above before running; `config.py`'s rewrite swaps the two path lines as described. The symbol index covers every module in `MANIFEST` even when only some targets are generated, so it is always global.

- [ ] **Step 3: Create the package skeleton**

Create the four `__init__.py` files (each containing only a one-line docstring and `from __future__ import annotations`, except `cli/commands/__init__.py`, which stays minimal until Task 3).

- [ ] **Step 4: Generate `config.py` and `types.py`**

Run: `uv run python "$TMPDIR/runsplit/extract.py" cli/infra/config.py cli/infra/types.py`
Expected: no `UNRESOLVED` output.

Note the symbol index is built from freshly written files, so when only some modules are generated the index still
needs every module's names. Run it once for all modules in a scratch mode first if `symbol_index()` raises
`FileNotFoundError` (generate bodies for every module with `write_module`, then run the fix-ups only on the requested
targets).

- [ ] **Step 5: Hand-check `config.py`**

Confirm `DOTFILES_DIR = Path(__file__).parents[2]`, `SCRIPT_PATH = DOTFILES_DIR / 'run.py'`, and `RUN_DEBUG` is a plain
module-level `bool`. Run: `uv run python -c "from cli.infra import config; print(config.DOTFILES_DIR, config.SCRIPT_PATH.exists())"`
Expected: the worktree root and `True`.

- [ ] **Step 6: Update `pyproject.toml` tool config**

Add `"cli/**/*.py" = ["BLE001", "S112"]` to `[tool.ruff.lint.per-file-ignores]` (keep-sorted block) and `"cli/commands/"`
to the interrogate `exclude` list next to `"run.py"`.

- [ ] **Step 7: Lint and commit**

Run: `uv run ruff check cli pyproject.toml` then `uv run pytest tests/unit/run -q` (still green: `run.py` is untouched).
Commit: `git add cli pyproject.toml docs/plans/2026-11/2026-11-21-run-py-split-design.md docs/plans/2026-11/2026-11-21-run-py-split-plan.md` then `git commit -m "Add cli package skeleton with config and types"`.

---

### Task 2: Extract `cli/utils/`

**Files:**
- Create: `cli/utils/{formatting,styling,prompts,shell,scripts,retry,python,nas,uv,venv,ansible,homeassistant,claude,doctor_checks}.py`

**Interfaces:**
- Consumes: `cli.infra.config`, `cli.infra.types` (Task 1).
- Produces: every helper keeps its original name and signature, importable as `from cli.utils.<module> import <name>`.

- [ ] **Step 1: Generate all utils modules**

Run: `uv run python "$TMPDIR/runsplit/extract.py" cli/utils/formatting.py cli/utils/styling.py cli/utils/prompts.py cli/utils/shell.py cli/utils/scripts.py cli/utils/retry.py cli/utils/python.py cli/utils/nas.py cli/utils/uv.py cli/utils/venv.py cli/utils/ansible.py cli/utils/homeassistant.py cli/utils/claude.py cli/utils/doctor_checks.py`
Expected: no `UNRESOLVED` output.

- [ ] **Step 2: Check for import cycles and residual lint**

Run: `uv run ruff check cli` then `uv run python -c "import cli.utils.styling, cli.utils.shell, cli.utils.scripts, cli.utils.python, cli.utils.nas, cli.utils.uv, cli.utils.venv, cli.utils.ansible, cli.utils.homeassistant, cli.utils.claude, cli.utils.doctor_checks"`
Expected: no errors. If a cycle appears (for example `uv` and `venv` importing each other), move the shared helper to
the lower module and note it in the module docstring; do not use function-local imports.

- [ ] **Step 3: Confirm the old suite still passes (run.py is untouched)**

Run: `uv run pytest tests/unit/run -q`
Expected: 321 passed.

- [ ] **Step 4: Commit**

`git add cli` then `git commit -m "Extract run.py helpers into cli.utils"`.

---

### Task 3: Extract `cli/infra/command.py`, `cli/infra/main.py`, `cli/commands/`; slim `run.py`; migrate tests

**Files:**
- Create: `cli/infra/command.py`, `cli/infra/main.py`, `cli/commands/{setup,deploy,dotfiles,inventory,tools,hooks,testing,analysis,dependencies,utilities}.py`
- Modify: `cli/commands/__init__.py`, `run.py`
- Move/modify: `tests/unit/run/*` to `tests/unit/cli/{infra,utils,commands}/` (see Step 6), `tests/unit/test_docs_consistency.py`

**Interfaces:**
- Produces: `cli.infra.command.Command`, `REGISTERED_COMMANDS`, `get_commands`; `cli.infra.main.main(argv)`,
  `build_parser`, `Args`; importing `cli.commands` registers every command in the original order.

- [ ] **Step 1: Generate the rest**

Run: `uv run python "$TMPDIR/runsplit/extract.py" cli/infra/command.py cli/infra/main.py cli/commands/setup.py cli/commands/deploy.py cli/commands/dotfiles.py cli/commands/inventory.py cli/commands/tools.py cli/commands/hooks.py cli/commands/testing.py cli/commands/analysis.py cli/commands/dependencies.py cli/commands/utilities.py`
Expected: no `UNRESOLVED` output. A command module importing another command module is a design smell; if it
happens (likely `regenerate_derived_files`), move that helper to `cli/utils/` (a new module such as
`cli/utils/derived_files.py`) instead.

- [ ] **Step 2: Write `cli/commands/__init__.py`**

```python
"""
Command modules: importing each one registers its ``Command`` subclasses, in help-text and Makefile order
"""
from __future__ import annotations

from cli.commands import setup           # noqa: F401
from cli.commands import deploy          # noqa: F401
from cli.commands import dotfiles        # noqa: F401
from cli.commands import inventory       # noqa: F401
from cli.commands import tools           # noqa: F401
from cli.commands import hooks           # noqa: F401
from cli.commands import testing         # noqa: F401
from cli.commands import analysis        # noqa: F401
from cli.commands import dependencies    # noqa: F401
from cli.commands import utilities       # noqa: F401
```

Import isort-sorted order would reorder these; keep the explicit order with `# isort: skip_file` or `# noqa: I001` so
the command registration order is preserved.

- [ ] **Step 3: Rewrite `run.py`**

Keep lines 1-73 (shebang, PEP 723 block, docstring) with the "Architecture" paragraph updated to say commands live in
`cli/commands/` and infrastructure in `cli/infra/` and `cli/utils/`, then:

```python
from __future__ import annotations

from cli import commands  # noqa: F401  (importing registers every command)
from cli.infra.main import main

if __name__ == '__main__':
    main()
```

- [ ] **Step 4: Prove behavior is unchanged**

Run: `"$TMPDIR/runsplit/snapshot.sh" "$TMPDIR/runsplit/after"` then `diff -r "$TMPDIR/runsplit/before" "$TMPDIR/runsplit/after"`
Expected: no output (identical).
Run: `NO_COLOR=1 uv run python run.py makefile` then `git status --short Makefile`
Expected: Makefile unmodified.
Also run `python3 run.py --help` with the system interpreter (not `uv`) to confirm bare-`python3` startup works.

- [ ] **Step 5: Lint**

Run: `uv run ruff check --fix cli run.py`
Expected: clean.

- [ ] **Step 6: Migrate the tests (parallel, one fork per file group)**

Mapping (do not split files; place each file by primary subject):

| Old file (`tests/unit/run/`)                                 | New location (`tests/unit/cli/`)                |
| ------------------------------------------------------------ | ----------------------------------------------- |
| `test_startup.py`                                            | `infra/test_startup.py`                         |
| `test_style.py`, `test_prompts.py`, `test_shell_command.py`  | `utils/test_styling.py`, `utils/test_prompts.py`, `utils/test_shell.py` |
| `test_uv.py`, `test_ha_sync.py`                              | `utils/test_uv.py`, `utils/test_homeassistant.py` |
| `test_doctor.py`                                             | `utils/test_doctor_checks.py` (command-level tests stay with it) |
| `test_commands.py`, `test_nas.py`, `test_env_commands.py`    | `commands/test_commands.py`, `commands/test_nas.py`, `commands/test_env_commands.py` |
| `test_hooks.py`, `test_track_claude.py`, `test_docs_audit_command.py` | `commands/test_hooks.py`, `commands/test_track_claude.py`, `commands/test_docs_audit_command.py` |

Each fork's rules: replace `import run` with imports of the real modules; use `git mv` for the file move; for every
`monkeypatch.setattr(run, 'name', ...)` find the module(s) that the code under test uses `name` from (see
`$TMPDIR/runsplit/symbols.json` for the defining module, then read the caller) and patch there, e.g.
`monkeypatch.setattr('cli.commands.deploy.shell_command', fake)`; patch every module on the call path that holds its
own binding. Mutable state (`RUN_DEBUG`) is patched on `cli.infra.config`. Keep test names and docstrings. Done when
the moved files pass and `uv run ruff check tests/unit/cli` is clean. Each fork reports ineffective-patch risks it saw.

Also update `tests/unit/test_docs_consistency.py` (lines ~367-390) to import `cli.commands` and read
`cli.infra.command.REGISTERED_COMMANDS`.

- [ ] **Step 7: Full gate for the swap**

Run: `uv run pytest tests/unit -q`
Expected: every test passes (321 migrated + the rest of the suite); compare the migrated count with 321.
Run `grep -rn "monkeypatch.setattr(run," tests` and `grep -rn "^import run" tests`; expected: no matches.

- [ ] **Step 8: Commit (single commit: Tasks 3 and 4 swap together)**

`git add -A cli run.py tests` (review `git status` first), then
`git commit -m "Move run.py commands and infrastructure into cli package; retarget tests"`.

---

### Task 4: Docs, READMEs, and tool-config references

**Files:**
- Create: `cli/README.md`, `cli/infra/README.md`, `cli/utils/README.md`, `cli/commands/README.md`
- Modify: `docs/RUN_PY_REFERENCE.md`, `README.md` (directory table), `.ctx/ARCHITECTURE.md`, `.ctx/CONVENTIONS.md`,
  `scripts/STYLE-GUIDE.md`, `.claude/rules/script-style.md`, `.claude/rules/python-style.md`, `CLAUDE.md`,
  `scripts/codebase/update_gitignore.py` (comment), `tests/README.md`, `docs/README.md`, `.pre-commit-config.yaml` if it
  references `run.py` paths

**Interfaces:** none (documentation only).

- [ ] **Step 1: Find every stale reference**

Run: `grep -rnE "run\.py" --include='*.md' --include='*.py' --include='*.toml' --include='*.yaml' . | grep -vE "docs/plans|archive/|inventory/|\.venv"`
Triage each hit: command invocations (`python3 run.py <cmd>`) stay; statements about where code *lives* change. In
particular, replace "the `# Text styling` section of `run.py`" with `cli/utils/styling.py`, and
`.claude/rules/python-style.md`'s "`run.py` patterns" paragraph with the `cli/` layout.

- [ ] **Step 2: Write the four READMEs**

Follow `.claude/rules/readme-guidelines.md`: breadcrumb, one-line purpose, down-links, a table of modules and what each
holds (only facts the code proves). `cli/commands/README.md` lists each command module with its commands and group.

- [ ] **Step 3: Format and audit docs**

Run: `uv run prek run mdformat --all-files` then `uv run python run.py docs-audit`
Expected: no new findings attributable to `cli/`.

- [ ] **Step 4: Commit**

`git add -A` for the touched docs (review `git status`), then `git commit -m "Document the cli package layout"`.

---

### Task 5: Final verification

- [ ] **Step 1:** `uv run pytest -q` (whole suite). Expected: all pass.
- [ ] **Step 2:** `uv run ruff check .`; `uv run interrogate` per the repo's configuration; Expected: clean/passing.
- [ ] **Step 3:** `uv run prek run --all-files`. Expected: clean (re-run once if hooks rewrite files, then commit the result).
- [ ] **Step 4:** Re-run the snapshot diff from Task 3 Step 4. Expected: identical.
- [ ] **Step 5:** Smoke-run real commands: `python3 run.py status`, `python3 run.py doctor`, `python3 run.py -d inventory-status`
      (debug output on stderr proves `config.RUN_DEBUG` is honored by `printf`).
- [ ] **Step 6:** `git log --oneline origin/main..HEAD` shows the four commits; report line counts (`wc -l run.py cli/**/*.py`).

## Self-review notes

- Spec coverage: layout (Tasks 1-3), RUN_DEBUG and path hazards (rewrite table), registration order (Task 3 Steps 2 and
  4), tests (Task 3 Step 6), docs/config (Tasks 1 and 4), gates (Task 5).
- Known unknowns resolved at execution time, not guessed here: which helpers cross the commands/utils boundary
  (`regenerate_derived_files` is the likely one) and which modules a given test patch must target.
