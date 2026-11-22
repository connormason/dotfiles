# Split `run.py` into a `cli/` package

## Goal

`run.py` is 5,730 lines in one file. Keep it as the core entry point (PEP 723 header, module docstring, `main()`
invocation) and move the infrastructure, utilities, and commands into a top-level `cli/` package. Behavior, help text,
and the generated Makefile stay byte-identical.

## Decisions

- **Package name:** `cli/` (top-level, stdlib-only, Python 3.9 compatible). A `run/` directory was rejected: it would
  collide with `run.py`.
- **Tests:** retarget every `monkeypatch.setattr(run, ...)` to the module that uses the name, and move
  `tests/unit/run/` to `tests/unit/cli/{infra,utils,commands}/`, mirroring the package.
- **Constants:** shared paths, env vars, and exit codes live in `cli/infra/config.py`. Constants with exactly one owner
  (`HA_*`, `CLAUDE_*`, `CLEAN_PATTERN_GROUPS`, `TRACK_CLAUDE_PREFLIGHT_LINES`) move next to that owner.

## Layout

```
run.py                      PEP 723 header, docstring, imports cli.commands (registration), calls main()
cli/
  infra/
    config.py               constants, env vars, project paths, ExitCode, mutable RUN_DEBUG
    types.py                SupportsWrite, ToolInfo, SSHTarget, InstallableTool
    command.py              Command ABC, REGISTERED_COMMANDS, get_commands, help formatter
    main.py                 Args, build_parser_help_text, build_parser, main
  utils/
    formatting.py  styling.py  prompts.py  shell.py  retry.py  scripts.py
    python.py  uv.py  venv.py  ansible.py  nas.py  homeassistant.py  claude.py  doctor_checks.py
  commands/
    __init__.py             imports the modules below in the current definition order
    setup.py  deploy.py  dotfiles.py  inventory.py  tools.py  hooks.py  testing.py  analysis.py
    dependencies.py  utilities.py
```

Dependency direction: `infra.config`/`infra.types` <- `utils` <- `infra.command` / `infra.main` <- `commands`.
Cross-command imports are avoided; shared helpers sit in `utils`.

## Hazards and how each is handled

| Hazard                                                                                 | Handling                                                                                                                                      |
| -------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| `main()` rebinds `RUN_DEBUG`; `printf` and `run_installer` read it                     | State lives in `cli.infra.config`; readers use `config.RUN_DEBUG` (attribute access), `main()` assigns `config.RUN_DEBUG`                     |
| `DOTFILES_DIR = Path(__file__).parent`                                                 | `config.py` derives the repo root as `Path(__file__).resolve().parents[2]`; `SCRIPT_PATH = DOTFILES_DIR / 'run.py'`                          |
| `MakefileCommand` and doctor use `Path(__file__).name` / `SCRIPT_PATH`                 | Switch to `SCRIPT_PATH.name`                                                                                                                  |
| Help and Makefile order follow registration order                                      | `cli/commands/__init__.py` imports modules in the original definition order; golden snapshots prove it                                       |
| `run.py` run as a script by a bare system `python3`                                    | Script directory is `sys.path[0]`, so `import cli` resolves; the package stays stdlib-only                                                    |
| Tool config entries for `run.py` (ruff per-file-ignores, interrogate exclude)          | Extend to `cli/**`                                                                                                                            |
| Docs naming `run.py`'s `# Text styling` section as the styling source of truth          | Point at `cli/utils/styling.py`                                                                                                               |

## Method

1. Extract by line range with a throwaway script, so code moves verbatim; `ruff` prunes and adds imports (F401/F821).
2. Verify against pre-split snapshots (taken with `NO_COLOR=1`): `--help`, every `<command> -h`, and the regenerated
   Makefile must be identical, and `git status` must show no Makefile change after `run.py makefile`.
3. Migrate tests per module group; the baseline is 321 passing tests in `tests/unit/run/`.
4. Update docs and tool config; add a README per new directory.
5. Gate: full test suite, `ruff check`, interrogate, `prek run --all-files`.

## Out of scope

No behavior changes, no renamed commands or flags, no cleanup of the moved code beyond what the move forces.
