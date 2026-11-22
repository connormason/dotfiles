[Project Root](../../README.md) > [cli](../README.md) > **commands**

# cli/commands

One module per command group. Each `Command` subclass registers itself when its module is imported, and
[`__init__.py`](__init__.py) imports the modules in a fixed order that sets the order of groups in `run.py --help` and
of targets in the generated `Makefile`.

| Module                               | Group               | Commands                                                                                    |
| ------------------------------------ | ------------------- | ------------------------------------------------------------------------------------------- |
| [`setup.py`](setup.py)               | Setup & Environment | `install`, `dev`, `shell`, `status`, `doctor`, `clean`                                      |
| [`deploy.py`](deploy.py)             | Bootstrap & Deploy  | `bootstrap`, `nas-provision`, `nas-deploy`, `ha-pull`, `ha-push`                            |
| [`dotfiles.py`](dotfiles.py)         | Dotfiles            | `stow`, `render`, `track-claude`                                                            |
| [`inventory.py`](inventory.py)       | Inventory           | `inventory-hosts`, `inventory-status`, `update-inventory`, `vault-decrypt`, `vault-encrypt` |
| [`tools.py`](tools.py)               | Tool Installation   | `install-uv`, `install-hatch`                                                               |
| [`hooks.py`](hooks.py)               | Hooks               | `install-hooks`, `prepare-hooks`, `uninstall-hooks`, `run-hooks`, `pre`                     |
| [`testing.py`](testing.py)           | Testing             | `test`, `test-full`, `test-unit`, `test-integration`, `test-cov`, `test-analyze`            |
| [`analysis.py`](analysis.py)         | Static Analysis     | `docs-audit`                                                                                |
| [`dependencies.py`](dependencies.py) | Dependencies        | `lock`, `lock-check`, `lock-upgrade`, `lock-sync`                                           |
| [`utilities.py`](utilities.py)       | Utilities           | `makefile`, `diagnose`                                                                      |

The full option reference for each command is [`docs/RUN_PY_REFERENCE.md`](../../docs/RUN_PY_REFERENCE.md).

## Dependencies

Command modules import `Command` and `ExitCode` from [`cli/infra/`](../infra/README.md) and helpers from
[`cli/utils/`](../utils/README.md). They do not import one another.
