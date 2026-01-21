# run.py - Command Reference

Python CLI tool for managing the dotfiles repository. Provides commands for inventory management, tool installation,
and codebase maintenance with ANSI styling and retry logic for robustness.

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

### Tool Installation

Commands for installing Python development tools with robust error handling.

#### `install-uv`

Install the `uv` Python package manager.

```bash
# Basic installation
python3 run.py install-uv

# Force reinstall even if already installed
python3 run.py install-uv --force

# Verbose output for debugging
python3 run.py install-uv --verbose

# Custom retry behavior
python3 run.py install-uv --retries 5 --retry-delay 3
```

**Options:**
- `-f, --force`: Force reinstall even if `uv` already installed
- `-v, --verbose`: Enable verbose output for debugging
- `--retries N`: Maximum number of download retry attempts
- `--retry-delay SECONDS`: Initial delay in seconds between retries with exponential backoff

**Implementation:**
Delegates to `scripts/installers/install_uv.py` (see [scripts/installers/README.md](../scripts/installers/README.md) for details).

#### `install-hatch`

Install the `hatch` Python project manager.

```bash
# Basic installation
python3 run.py install-hatch

# With options (same as install-uv)
python3 run.py install-hatch --force --verbose
```

**Options:**
Same as `install-uv` (see above).

**Implementation:**
Delegates to `scripts/installers/install_hatch.py` (see [scripts/installers/README.md](../scripts/installers/README.md) for details).

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

**Debug mode:**
Shows each file/directory removed (enable with `--debug` flag).

#### `pre`

Run pre-commit hooks on all project files.

```bash
python3 run.py pre
```

**Behavior:**
Executes `pre-commit run --all-files` with live output. Does not fail on hook failures (exit code ignored).

**Pre-commit hooks include:**
- File integrity checks (large files, merge conflicts, private keys)
- Python validation (syntax, debug statements, ruff, mypy, interrogate)
- Data format validation (JSON, YAML, TOML, XML)
- YAML linting with custom config
- Whitespace and line ending fixers

See [`.pre-commit-config.yaml`](../.pre-commit-config.yaml) for complete hook configuration.

#### `makefile`

Generate `Makefile` from registered commands in `run.py`.

```bash
python3 run.py makefile
```

**Behavior:**
- Reads all `@command` decorated functions from `run.py`
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
.PHONY: help list-hosts update-inventory install-uv ...

# Inventory
list-hosts: ## List available bootstrap targets from inventory
	@python3 run.py list-hosts

update-inventory: ## Update inventory repo
	@python3 run.py update-inventory

# Tool Installation
install-uv: ## Install uv Python project manager
	@python3 run.py install-uv
...
```

## Architecture

### Command Registration System

Commands are registered using the `@command` decorator:

```python
@command(
    group='Inventory',
    description='List available bootstrap targets',
    add_arguments=my_args_func,  # Optional
    epilog='Additional help text',  # Optional
)
def cmd_list_hosts(args: argparse.Namespace) -> None:
    """Command implementation"""
    pass
```

**Decorator parameters:**
- `name`: Command name (defaults to function name with prefixes removed)
- `add_arguments`: Function to add command-specific arguments to subparser
- `description`: Command description (defaults to docstring)
- `epilog`: Additional help text shown after arguments
- `formatter_class`: argparse formatter class (default: `RawDescriptionHelpFormatter`)
- `group`: Group name for organizing help output
- `script_only`: If True, exclude from Makefile generation
- `makefile_only`: If True, exclude from script help output

**Registry:**
All registered commands stored in `REGISTERED_COMMANDS` dict mapping `name -> CommandInfo`.

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

**Global environment:**
Commands inherit environment from:
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
SCRIPTS_DIR     = DOTFILES_DIR / 'scripts'
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
```

**Clean patterns:**
See `CLEAN_PATTERN_GROUPS` dict for complete list of glob patterns removed by `clean` command.

### Type System

**Key type aliases:**
```python
PathLike         = Union[str, Path]
StyleColor       = Union[int, tuple[int, int, int], str]
CommandFunc      = Callable[[argparse.Namespace], None]
AddArgumentsFunc = Callable[[argparse.ArgumentParser], None]
```

**Command info dataclass:**
```python
@dataclass
class CommandInfo:
    name: str
    func: CommandFunc
    add_arguments: AddArgumentsFunc | None = None
    description: str | None = None
    epilog: str | None = None
    formatter_class: type[argparse.HelpFormatter] = argparse.RawDescriptionHelpFormatter
    group: str | None = None
    script_only: bool = False
    makefile_only: bool = False
```

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

**ShellCommandError:**
Raised by `shell_command()` when subprocess exits with non-zero code and `check=True`. Extends
`subprocess.CalledProcessError` with formatted `__str__()` that includes stdout/stderr.

**Standard subprocess exceptions:**
- `subprocess.CalledProcessError`: Non-zero exit code
- `subprocess.TimeoutExpired`: Command exceeded timeout
- `KeyboardInterrupt`: User cancelled operation (caught in `main()`)

## Usage Examples

### Basic Command Execution

```bash
# List available hosts
python3 run.py list-hosts

# Update inventory with debug output
python3 run.py --debug update-inventory

# Install uv with custom retry behavior
python3 run.py install-uv --retries 5 --retry-delay 3

# Clean and run pre-commit
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

1. **Define command function:**
```python
@command(
    group='My Group',
    description='Does something useful',
)
def cmd_my_command(args: argparse.Namespace) -> None:
    """Detailed help text shown with --help"""
    printf('Executing my command...', fg='bright_cyan')
    # Implementation here
    printf('✅ Complete', fg='bright_green')
```

2. **Add arguments (optional):**
```python
def add_my_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('--option', help='Some option')

@command(
    group='My Group',
    add_arguments=add_my_args,
)
def cmd_my_command(args: argparse.Namespace) -> None:
    if args.option:
        printf(f'Option: {args.option}')
```

3. **Regenerate Makefile:**
```bash
python3 run.py makefile
```

### Adding New Command Groups

Groups are automatically created when you use the `group` parameter in `@command`:

```python
@command(group='Deployment')
def cmd_deploy(args: argparse.Namespace) -> None:
    """Deploy the application"""
    pass

@command(group='Deployment')
def cmd_rollback(args: argparse.Namespace) -> None:
    """Rollback deployment"""
    pass
```

Both commands will appear under "Deployment:" in help output.

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
5. **Return appropriate exit codes:** Use `sys.exit(1)` on failure

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

### Tool Installation Issues

**Symptom:** `install-uv` or `install-hatch` fails

**Solution:**
```bash
# Run with verbose output
python3 run.py install-uv --verbose

# Force clean reinstall
python3 run.py install-uv --force

# Increase retry attempts
python3 run.py install-uv --retries 10 --retry-delay 5
```

### Pre-commit Hook Failures

**Symptom:** `pre` command shows hook failures

**Solution:**
```bash
# Update pre-commit hooks
pre-commit autoupdate

# Clear hook cache
pre-commit clean
pre-commit install-hooks

# Run again
python3 run.py pre
```

## Implementation Details

### Argument Parser Construction

1. **Main parser:** Built with `build_parser()`, includes global `--debug` and `--help` flags
2. **Subparsers:** One subparser per registered command
3. **Command arguments:** Added via `add_arguments` callback if provided
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
