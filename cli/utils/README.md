[Project Root](../../README.md) > [cli](../README.md) > **utils**

# cli/utils

Helpers shared by the command modules. A module here imports from [`cli/infra/`](../infra/README.md) (`config`, `types`)
and from other `utils` modules, never from [`cli/commands/`](../commands/README.md).

| Module                                 | Public API                                                                                                                                                                                                                              |
| -------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`formatting.py`](formatting.py)       | `folduser`, `format_elapsed`, `canonical_pkg_name`, `cleanup_whitespace`                                                                                                                                                                |
| [`styling.py`](styling.py)             | `style`, `unstyle`, `printf`, `status_line`, `pathstyle`, `optstyle`, `typestyle`, `arg_note`, `dim_paren`, `ANSI_COLOR`, `ANSI_RESET_ALL`, `HATCH`, `UV`                                                                               |
| [`prompts.py`](prompts.py)             | `confirm`, `select_option`                                                                                                                                                                                                              |
| [`shell.py`](shell.py)                 | `shell_command`, `capture_command`, `ShellCommandError`, `detect_ssh_error`, `handle_command_error`, `first_output_line`, `RUN_COMMAND_ENVVARS`                                                                                         |
| [`retry.py`](retry.py)                 | `retry_on_failure`                                                                                                                                                                                                                      |
| [`scripts.py`](scripts.py)             | `check_script_validity`, `import_script_module`, `run_installer`                                                                                                                                                                        |
| [`python.py`](python.py)               | `check_python`                                                                                                                                                                                                                          |
| [`uv.py`](uv.py)                       | `find_uv_executable`, `uv_command`, `check_uv`, `ensure_uv`, `uv_run`, `uv_sync`, `uv_lock`, `uv_pip_list`, `uv_tree`                                                                                                                   |
| [`venv.py`](venv.py)                   | `VenvStatus`, `VenvHealth`, `validate_venv`, `ensure_venv`, `enter_venv`, `is_venv_stale`, `get_external_active_venv`, `parse_pyvenv_version`, `count_venv_packages`                                                                    |
| [`ansible.py`](ansible.py)             | `find_vault_files`, `require_vault_password`, `require_inventory`, `resolve_ssh_target_from_inventory_host`, `parse_playbook_extra_vars`, `build_nas_provision_command`                                                                 |
| [`nas.py`](nas.py)                     | `list_services`, `warn_on_dirty_services`, `require_nas_reachable`, `resolve_reachable_nas`                                                                                                                                             |
| [`homeassistant.py`](homeassistant.py) | the `ha-pull` / `ha-push` sync helpers: `HASyncError`, `TreeDiff`, `fetch_ha_config`, `apply_ha_changes`, `upload_ha_files`, `delete_ha_files`, `ha_ssh_command`, `require_ha_reachable`, tree and tar helpers, and the `HA_*` settings |
| [`claude.py`](claude.py)               | `find_untracked_claude_files` and the `CLAUDE_*` settings it uses                                                                                                                                                                       |
| [`doctor_checks.py`](doctor_checks.py) | `DoctorCheck`, `doctor_checks()`, and the individual `check_*` functions the `doctor` command runs                                                                                                                                      |

## Notes

- `styling.py` is the reference implementation of the console-output helpers that the standalone scripts under
  [`scripts/`](../../scripts/README.md) copy; see [`scripts/STYLE-GUIDE.md`](../../scripts/STYLE-GUIDE.md).
- `styling.printf` and `scripts.run_installer` gate debug output on `config.RUN_DEBUG`, read through the module
  attribute so the value `main()` sets after import is the one used.
