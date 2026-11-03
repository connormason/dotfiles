# run.py - Command Reference

Python CLI tool for managing the dotfiles repository. Provides commands for inventory management, codebase maintenance,
NAS provisioning and service deploys, and the layered dev environment (stow, bootstrap, render, doctor, track-claude),
with ANSI styling and retry logic for robustness.

## Quick Start

```bash
# Show all available commands
python3 run.py --help

# Enable debug output for any command
python3 run.py --debug <command>

# Or use the generated Makefile
make help
```

## Command Categories

### Inventory Management

Commands for managing the separate inventory repository containing host definitions and encrypted vault files.

#### `list-hosts`

List all bootstrap targets from the inventory file.

```bash
python3 run.py list-hosts
```

**Output example:**

```
Available Bootstrap Targets
============================================================

macos:
  └─ connors-macbook
     (connects to: localhost)

servers:
  └─ nas
     (connects to: 192.168.1.100)

============================================================
Total hosts: 2
```

**Error handling:**

- Checks if `inventory/inventory.yml` exists
- Validates YAML structure
- Suggests running `update-inventory` if missing

#### `update-inventory`

Update (or clone) the inventory repository from remote.

```bash
python3 run.py update-inventory
```

**Behavior:**

- **If inventory exists and is git repo**: Pulls latest changes with `git pull origin main`
- **If inventory exists but not git repo**: Removes directory and clones fresh
- **If inventory doesn't exist**: Clones repository

**Retry logic:**

- Pull operation: 3 attempts with 2s delay, exponential backoff (2x multiplier)
- Clone operation: 3 attempts with 5s delay, exponential backoff (2x multiplier)
- 30s timeout for pull, 60s timeout for clone

**Configuration:**

- Repository URL: `DOTFILES_INVENTORY_REPO_URL` environment variable
- Default: `git@github.com:connormason/dotfiles-inventory.git`

### Codebase Maintenance

Commands for cleaning build artifacts and running code quality checks.

#### `clean`

Remove all build artifacts, caches, and generated files.

```bash
python3 run.py clean
```

**Cleaned patterns:**

**Package build artifacts:**

- `build/`
- `dist/`
- `*.egg-info`

**Package cache files:**

- `**/__pycache__/`
- `**/*.pyc`

**Tool cache files:**

- `.mypy_cache`
- `.pytest_cache`
- `.ruff_cache`
- `.tox`
- `.nox`
- `.coverage`

**Output:**

```
🧹 Cleaning project workspace...
   Cleaning package build artifacts...
   Cleaning package cache files...
   Cleaning tool cache files...
✅ Cleanup complete
```

**Debug mode:** Shows each file/directory removed (enable with `--debug` flag).

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

| Option                                                     | Forwards                              |
| ---------------------------------------------------------- | ------------------------------------- |
| `HOOK\|PROJECT...`                                         | hook or project filter (placed first) |
| `-a/--all-files`, `--files`, `-d/--directory`              | file selection                        |
| `-s/--from-ref`, `-o/--to-ref`, `--last-commit`            | ref range selection                   |
| `--skip` (repeatable), `--stage`                           | skip hooks, choose the git stage      |
| `--show-diff-on-failure`, `--fail-fast`, `--dry-run`, `-v` | run behavior                          |

**Behavior:** runs `prek run …` with inherited stdio and exits with prek's return code (so `make pre` fails when a hook
fails). The hook filter is placed before the options because prek's `--files` is greedy.

#### `pre`

Run prek hooks on all project files. This is `run-hooks --all-files`: it accepts the same hook filter and run options,
but no file or ref selection, because prek rejects `--all-files` combined with `--files`, `--directory`, `--from-ref`,
`--to-ref`, or `--last-commit`. Use `run-hooks` for those.

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

#### `makefile`

Generate `Makefile` from registered commands in `run.py`.

```bash
python3 run.py makefile
```

**Behavior:**

- Reads every registered `Command` in `run.py`
- Generates `Makefile` with targets for each command
- Excludes commands marked `script_only=True`
- Organizes targets by command groups
- Includes color-coded help text

**Generated Makefile usage:**

```bash
# Show help
make help

# Run any command
make update-inventory
make clean
make pre
```

**Auto-generated structure:**

```makefile
.PHONY: help list-hosts update-inventory clean ...

# Inventory
list-hosts: ## List available bootstrap targets from inventory
	@python3 run.py list-hosts

update-inventory: ## Update inventory repo
	@python3 run.py update-inventory
...
```

### Dotfiles

Wrappers over the layered dev-env engine: [`stow.sh`](../stow.sh),
[`bootstrap/bootstrap.sh`](../bootstrap/bootstrap.sh), and
[`scripts/dotfiles/render.py`](../scripts/dotfiles/render.py), plus `test`, which runs the suite through
[`scripts/hooks/uv-public.sh`](../scripts/hooks/uv-public.sh). `bootstrap`, `stow`, `render`, and `test` forward their
flags and exit with the underlying script's return code; `doctor` and `track-claude` run their own logic (described
below). All commands belong to the `Dotfiles` group.

| Command        | Forwards to                          | Options                                                                                   |
| -------------- | ------------------------------------ | ----------------------------------------------------------------------------------------- |
| `bootstrap`    | `bootstrap/bootstrap.sh`             | `--dry-run`, `--list`, `--only STAGE`, `--from STAGE`, `--resume`, `--verify`, `--no-log` |
| `stow`         | `stow.sh`                            | `[PACKAGE...]`, `-n/--simulate`, `--backup-conflicts`, `-v/--verbose`                     |
| `render`       | `scripts/dotfiles/render.py`         | `[TARGET...]`, `--diff`, `--check`, `--force`, `-v/--verbose`                             |
| `doctor`       | (runs the checks below)              | `-f/--fix`, `-y/--yes`                                                                    |
| `track-claude` | (moves files, then `stow.sh claude`) | `-n/--dry-run`                                                                            |
| `test`         | `scripts/hooks/uv-public.sh`         | `[PATH...]` (default: `tests`)                                                            |

```bash
python3 run.py bootstrap --list           # stages across all layers
python3 run.py bootstrap --dry-run        # simulate every stage
python3 run.py stow -n                    # preview links; writes nothing
python3 run.py render --check             # exit 1 if rendered settings drifted
python3 run.py test tests/unit/test_run_doctor.py
```

#### `doctor`

Runs one check per line and exits 1 if any check fails. `tools` and `layers` run first; the remaining checks are skipped
when either fails.

| Check      | Passes when                                                                                          | Fix (`--fix`)                     |
| ---------- | ---------------------------------------------------------------------------------------------------- | --------------------------------- |
| `tools`    | `brew`, `git`, `stow`, `uv`, `zsh` are on `PATH`                                                     | none                              |
| `layers`   | the overlay registry resolves (`dotfiles_layers` in `bootstrap/lib.sh`) and every overlay exists     | none                              |
| `git`      | `git --version` is at least 2.36 (needed for `includeIf "hasconfig:remote.*.url:"`)                  | none                              |
| `hooks`    | every hook type in `default_install_hook_types` has a prek-generated shim in the git hooks directory | `prek install`                    |
| `links`    | `stow.sh -n` reports `no changes` or `no packages found`                                             | `stow.sh --backup-conflicts`      |
| `render`   | `render.py --check` exits 0 (exit 1 is drift; exit 2 is a config or I/O error with no fix)           | `render.py` (without `--force`)   |
| `brewfile` | `brew bundle check` passes for every layer's `bootstrap/Brewfile`                                    | `brew bundle --file` per Brewfile |

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

A file whose repo counterpart already exists (including a dangling symlink at that path) is reported as a conflict and
left alone. Because `stow.sh` is all-or-nothing and refuses to run while a local regular file blocks a target, the
restow is skipped while any conflict remains: the command prints the recovery steps instead (resolve the conflicts, then
`python3 run.py stow claude`; add `--backup-conflicts` to move the blocking local files to `~/.dotfiles-backup/`).
Stowed files are symlinks, so any regular file counts as local-only; `plugins/`, `projects/`, and other state
directories are never touched. Review and commit the result with `git add stow/claude/.claude && git commit`.

### NAS

Provision the home NAS and deploy its Compose services from this machine, over SSH (tailnet or LAN). Both commands
belong to the `NAS` group and run the same preflight first: the inventory is present, `vault_password.txt` exists, and
the `nas` host answers a non-interactive SSH probe (`ConnectTimeout=5`, `BatchMode=yes`) as the user from the inventory.
A failed probe exits 1 with a remedy.

| Command         | Runs                                                     | Options                                                                                                          |
| --------------- | -------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `nas-provision` | `playbooks/nas_bootstrap.yml` through `ansible-playbook` | `--tags TAGS`, `--check`, `--diff`, `--limit HOSTS`, `-e/--extra-vars KEY=VALUE` (repeatable), `-v` (repeatable) |
| `nas-deploy`    | `scripts/nas/deploy-services.sh`                         | `<service\|all>`, `--dry-run`                                                                                    |

```bash
python3 run.py nas-provision --check --diff                  # preview the whole playbook
python3 run.py nas-provision --tags dotfiles,haos            # selected roles only
python3 run.py nas-provision --tags secrets                  # re-render per-service secrets
python3 run.py nas-deploy glance --dry-run                   # preview the rsync and the remote command
python3 run.py nas-deploy all
```

#### `nas-provision`

Runs the preflight, installs the Ansible collections with `ansible-galaxy collection install -r roles/requirements.yml`,
then runs `ansible-playbook playbooks/nas_bootstrap.yml` (with the inventory and vault password file) through
[`scripts/hooks/uv-public.sh`](../scripts/hooks/uv-public.sh). A failed collection install prints a warning and the
playbook still runs with the collections already installed. The exit status is Ansible's. `nas_bootstrap.sh` is a thin
wrapper that forwards its arguments to this command.

#### `nas-deploy`

Resolves `ansible_host` and `ansible_user` of the `nas` host with `ansible-inventory` (literal values are required;
templated values are rejected, and the user falls back to the local login), warns when `services/` has uncommitted
changes (a deploy ships the working tree), then runs `scripts/nas/deploy-services.sh` with `NAS_HOST` and `NAS_USER`
set. The script rsyncs `services/` to `~/docker/` and runs `~/docker/deploy.sh` on the NAS; it is the same script CI
uses. The command is registered `script_only`, so `run.py makefile` does not generate a Makefile target for it.

## Architecture

### Command Registration System

Commands are classes deriving from the abstract `Command` base. Defining a subclass registers an instance of it
(`Command.__init_subclass__`), so no separate registration call exists:

```python
class ListHostsCommand(Command):
    """
    List available bootstrap targets from inventory
    """
    name:  ClassVar[str] = 'list-hosts'
    group: ClassVar[str] = 'Inventory'

    def run(self, args: argparse.Namespace) -> None:
        ...
```

**Class attributes:**

| Attribute       | Default                                                      | Meaning                                                      |
| --------------- | ------------------------------------------------------------ | ------------------------------------------------------------ |
| `name`          | class name minus its `Command` suffix, lowercased, `_` → `-` | Subcommand name; multi-word commands set it explicitly       |
| `description`   | class docstring                                              | First line feeds the script help, Makefile help, and targets |
| `epilog`        | `None`                                                       | Text shown after the subcommand's arguments                  |
| `group`         | `None` (listed under "Other commands")                       | Help-output section                                          |
| `add_help`      | `True`                                                       | Add `-h/--help` to a trailing "Other options" group          |
| `script_only`   | `False`                                                      | Exclude from Makefile generation                             |
| `makefile_only` | `False`                                                      | Exclude from the script's own help output                    |

Setting both `script_only` and `makefile_only` raises `ValueError` at class definition. Pass `register=False` in the
class statement (`class _Base(Command, register=False)`) for an intermediate base that should not become a command.
Override the `help_formatter_type` property to change a subcommand's formatter (default:
`get_default_help_formatter_cls()`, a `RawTextHelpFormatter` that does not re-wrap help text).

**Registry:** `REGISTERED_COMMANDS` maps `name -> Command` instance. Query it with
`get_commands(by_group=..., group_order=..., exclude=...)`, which returns commands by name, or by group then name.

### ANSI Styling System

The `style()` function provides rich terminal formatting:

```python
# Colors
style('text', fg='green')
style('text', bg='blue')
style('text', fg=(255, 128, 0))  # RGB
style('text', fg=123)  # 256-color code

# Text attributes
style('text', bold=True, underline=True)
style('text', dim=True, italic=True)
style('text', blink=True, reverse=True)
style('text', strikethrough=True, overline=True)

# Combine styles
style('IMPORTANT', fg='red', bold=True, underline=True)
```

**Available colors:**

- Basic: `black`, `red`, `green`, `yellow`, `blue`, `magenta`, `cyan`, `white`
- Bright: `bright_black`, `bright_red`, `bright_green`, etc.
- 256-color codes: `0-255`
- RGB tuples: `(r, g, b)` where each component is `0-255`

**Helper function:**

```python
printf('Styled output', fg='green', bold=True, indent=4, debug=True)
```

### Shell Command Execution

The `shell_command()` function provides robust subprocess execution:

```python
# Capture output
result = shell_command(['ls', '-la'], capture_output=True, text=True)
print(result.stdout)

# Live output with indentation
shell_command(['make', 'build'], indent=3)

# Custom environment and working directory
shell_command(
    ['git', 'status'],
    cwd='/path/to/repo',
    env={'GIT_PAGER': 'cat'},
    timeout=30.0,
)
```

**Parameters:**

- `cmd`: List of command arguments
- `text`: If True, return `str` (default); if False, return `bytes`
- `encoding`: Text encoding (when `text=True`)
- `check`: If True, raise exception on non-zero exit (default: True)
- `capture_output`: If True, capture stdout/stderr instead of printing
- `indent`: Number of spaces to indent output (when not capturing)
- `cwd`: Working directory for command execution
- `env`: Environment variables (merged with `os.environ` and `RUN_COMMAND_ENVVARS`)
- `timeout`: Command timeout in seconds

**Error handling:**

- Raises `ShellCommandError` (extends `CalledProcessError`) with formatted output
- Timeout handling with graceful process termination
- Live output via PTY for real-time display

**Global environment:** Commands inherit environment from:

1. `os.environ` (system environment)
2. `RUN_COMMAND_ENVVARS` (global script environment)
3. `env` parameter (command-specific overrides)

### Retry Logic

The `@retry_on_failure` decorator provides exponential backoff:

```python
@retry_on_failure(max_attempts=3, delay=2.0, backoff=2.0)
def network_operation():
    # Code that might fail
    pass
```

**Behavior:**

- Attempt 1: Immediate execution
- Attempt 2: Wait `delay` seconds (2.0s)
- Attempt 3: Wait `delay * backoff` seconds (4.0s)
- Attempt N: Wait `delay * (backoff ** (N-1))` seconds

**Output:**

```
  └─ Attempt 1/3 failed, retrying in 2.0s...
  └─ Attempt 2/3 failed, retrying in 4.0s...
  └─ All 3 attempts failed
```

Used by `update-inventory` for git operations with different parameters:

- Pull: 3 attempts, 2s initial delay, 2x backoff
- Clone: 3 attempts, 5s initial delay, 2x backoff

## Configuration

### Constants

**File paths:**

```python
SCRIPT_PATH     = Path(__file__)
DOTFILES_DIR    = SCRIPT_PATH.parent
MAKEFILE_PATH   = DOTFILES_DIR / 'Makefile'
INVENTORY_DIR   = DOTFILES_DIR / 'inventory'
INVENTORY_FILE  = INVENTORY_DIR / 'inventory.yml'
PLAYBOOKS_DIR   = DOTFILES_DIR / 'playbooks'
```

**Environment variables:**

```python
# Debug mode toggle
RUN_DEBUG_ENVVAR = 'DOTFILES_RUN_DEBUG'
RUN_DEBUG = os.getenv(RUN_DEBUG_ENVVAR, 'false').lower() == 'true'

# Inventory repository URL
INVENTORY_REPO_URL_ENVVAR = 'DOTFILES_INVENTORY_REPO_URL'
INVENTORY_REPO_URL = os.getenv(
    INVENTORY_REPO_URL_ENVVAR,
    'git@github.com:connormason/dotfiles-inventory.git',
)

# Disable ANSI styling (any non-empty value)
NO_COLOR = bool(os.getenv('NO_COLOR'))
```

**Clean patterns:** See `CLEAN_PATTERN_GROUPS` dict for complete list of glob patterns removed by `clean` command.

### Type System

**Key type aliases:**

```python
PathLike   = Union[str, Path]
StyleColor = Union[int, tuple[int, int, int], str]
```

**Exit codes:**

```python
class ExitCode(int, enum.Enum):
    SUCCESS        = 0
    COMMAND_FAILED = 1
    SETUP_ERROR    = 2   # unknown command
    USER_CANCELLED = 3   # Ctrl-C
```

**Parsed arguments:** `main()` parses into the root `Args(argparse.Namespace)` (`command: str | None`, `debug: bool`).
Commands with options declare a nested `Args(argparse.Namespace)` listing their own fields and annotate
`run(self, args: Args)` with it.

## Error Handling

### Formatted Error Display

The `handle_command_error()` function provides rich error output:

```python
try:
    shell_command(['git', 'push'])
except subprocess.CalledProcessError as e:
    handle_command_error(
        e,
        context='Failed to push to remote',
        suggestion='Check your SSH keys and network connection'
    )
    raise
```

**Output format:**

```
❌ Failed to push to remote
  └─ Exit code: 128
  └─ Command: git push
  └─ Error output:
     fatal: Could not read from remote repository
     Please make sure you have the correct access rights
  └─ 💡 Check your SSH keys and network connection
```

### Exception Types

**ShellCommandError:** Raised by `shell_command()` when subprocess exits with non-zero code and `check=True`. Extends
`subprocess.CalledProcessError` with formatted `__str__()` that includes stdout/stderr.

**Standard subprocess exceptions:**

- `subprocess.CalledProcessError`: Non-zero exit code
- `subprocess.TimeoutExpired`: Command exceeded timeout
- `KeyboardInterrupt`: User cancelled operation (caught in `main()`, exits `ExitCode.USER_CANCELLED` = 3)

## Usage Examples

### Basic Command Execution

```bash
# List available hosts
python3 run.py list-hosts

# Update inventory with debug output
python3 run.py --debug update-inventory

# Clean and run prek
python3 run.py clean
python3 run.py pre
```

### Using Make Targets

```bash
# Generate Makefile first
python3 run.py makefile

# Then use make for any command
make list-hosts
make update-inventory
make clean
make pre
```

### Environment Variable Configuration

```bash
# Enable debug output globally
export DOTFILES_RUN_DEBUG=true
python3 run.py update-inventory

# Use custom inventory repository
export DOTFILES_INVENTORY_REPO_URL=git@github.com:myuser/my-inventory.git
python3 run.py update-inventory

# Plain output (also useful when piping to a file)
export NO_COLOR=1
```

### Programmatic Usage

While primarily a CLI tool, you can import and use components:

```python
from run import shell_command, style, printf, retry_on_failure

# Execute commands
result = shell_command(['git', 'status'], capture_output=True)

# Styled output
print(style('Success!', fg='green', bold=True))
printf('Warning!', fg='yellow', indent=4)

# Retry logic
@retry_on_failure(max_attempts=5, delay=1.0, backoff=1.5)
def flaky_operation():
    # Your code here
    pass
```

## Extension Guide

### Adding New Commands

1. **Subclass `Command`** (the docstring becomes the help description; defining the class registers it):

```python
class MyThingCommand(Command):
    """
    Does something useful
    """
    name:  ClassVar[str] = 'my-thing'
    group: ClassVar[str] = 'My Group'

    def run(self, args: argparse.Namespace) -> None:
        printf('Executing my command...', fg='bright_cyan')
        # Implementation here
        printf('✅ Complete', fg='bright_green')
```

2. **Add arguments (optional):** override `add_arguments` and type the parsed fields with a nested `Args`:

```python
class MyThingCommand(Command):
    """
    Does something useful
    """
    name:  ClassVar[str] = 'my-thing'
    group: ClassVar[str] = 'My Group'

    class Args(argparse.Namespace):
        option: str | None

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('--option', help='Some option')

    def run(self, args: Args) -> None:
        if args.option:
            printf(f'Option: {args.option}')
```

3. **Regenerate Makefile:**

```bash
python3 run.py makefile
```

`tests/unit/test_run_commands.py` fails if the checked-in `Makefile` drifts from the generated one.

### Adding New Command Groups

Groups are created by the `group` class attribute:

```python
class DeployCommand(Command):
    """
    Deploy the application
    """
    group: ClassVar[str] = 'Deployment'

    def run(self, args: argparse.Namespace) -> None: ...


class RollbackCommand(Command):
    """
    Rollback deployment
    """
    group: ClassVar[str] = 'Deployment'

    def run(self, args: argparse.Namespace) -> None: ...
```

Both commands (`deploy`, `rollback`) will appear under "Deployment" in help output.

### Custom Clean Patterns

Add new patterns to `CLEAN_PATTERN_GROUPS`:

```python
CLEAN_PATTERN_GROUPS: dict[str, list[str]] = {
    'package build artifacts': [
        'build',
        'dist',
        '*.egg-info',
    ],
    'my custom artifacts': [
        'output/*.log',
        'temp_files',
    ],
}
```

## Best Practices

### Command Implementation

1. **Use printf for output:** Consistent styling and debug support
2. **Handle errors gracefully:** Use `handle_command_error()` for subprocess failures
3. **Provide helpful messages:** Clear success/failure indicators with emojis
4. **Support debug mode:** Add debug output with `printf(..., debug=True)`
5. **Return appropriate exit codes:** Use `sys.exit(ExitCode.COMMAND_FAILED)` on failure

### Shell Command Execution

1. **Use shell_command:** Don't call `subprocess.run()` directly
2. **Set appropriate timeouts:** Prevent hanging on network operations
3. **Capture when needed:** Use `capture_output=True` for parsing, live output for user feedback
4. **Check return codes:** Use `check=True` (default) unless failure is expected

### Styling Guidelines

1. **Success:** `fg='bright_green'`, checkmark emoji ✅
2. **Error:** `fg='red'`, bold, X emoji ❌
3. **Warning:** `fg='yellow'`, warning emoji ⚠️
4. **Info:** `fg='bright_cyan'` or `fg='bright_white'`
5. **Debug:** `dim=True`, `debug=True` parameter
6. **Highlights:** `fg='bright_magenta'` for commands/files

## Troubleshooting

### Inventory Update Failures

**Symptom:** `update-inventory` fails with SSH errors

**Solution:**

```bash
# Verify SSH key access
ssh -T git@github.com

# Check SSH agent
ssh-add -l

# Add your SSH key if needed
ssh-add ~/.ssh/id_ed25519
```

**Alternative:** Use HTTPS URL instead of SSH

```bash
export DOTFILES_INVENTORY_REPO_URL=https://github.com/connormason/dotfiles-inventory.git
python3 run.py update-inventory
```

### YAML Parsing Errors

**Symptom:** `list-hosts` fails with "Failed to parse inventory file"

**Solution:**

```bash
# Validate YAML syntax
python3 -c "import yaml; yaml.safe_load(open('inventory/inventory.yml'))"

# Check for common issues
yamllint inventory/inventory.yml
```

### Pre-commit Hook Failures

**Symptom:** `pre` command shows hook failures

**Solution:**

```bash
# Update prek hooks
prek auto-update

# Clear hook cache
prek cache clean
prek prepare-hooks

# Run again
python3 run.py pre
```

## Implementation Details

### Argument Parser Construction

1. **Main parser:** Built with `build_parser()`; a "Debug Options" group holds `-d/--debug/--no-debug` (default from
   `DOTFILES_RUN_DEBUG`) and an "Other Options" group holds `-h/--help`
2. **Subparsers:** One subparser per registered command, using the command's `help_formatter_type`
3. **Command arguments:** Added by the command's `add_arguments()`; `-h/--help` follows in an "Other options" group
   unless `add_help = False`
4. **Help text:** Custom formatted using `style()` for colors, organized by groups

### Makefile Generation

1. **Filters commands:** Excludes `script_only=True` commands
2. **Groups targets:** Organizes by `group` attribute with section headers
3. **Generates help:** Color-coded help target using Make variables
4. **Phony targets:** All targets marked `.PHONY` (no file dependencies)

### Live Output via PTY

For real-time command output (when `indent` specified and `capture_output=False`):

1. Opens pseudo-terminal (PTY) with master/slave file descriptors
2. Spawns subprocess with stdin/stdout/stderr connected to slave FD
3. Reads from master FD in 1024-byte chunks
4. Prints lines as they arrive (buffering incomplete lines)
5. Handles timeout and cleanup gracefully

This provides better UX than `subprocess.PIPE` for long-running commands.

## Future Enhancements

**Potential improvements tracked in code:**

```python
# TODO: some commands have dependency on `yaml`. Maybe we should add `uv` metadata to top of script?
# TODO: implement bootstrap command(s)
```

**Suggested additions:**

- Bootstrap commands to run full playbook workflows
- Ansible playbook execution wrappers with tag support
- Vault password management helpers
- Role dependency visualization
- Configuration validation commands
- Host SSH connectivity checks
