# ezcli Installer Scripts

Bulletproof installer scripts for bootstrapping development environments with `uv` and `hatch`.

## Overview

These scripts provide robust, cross-platform installation of essential Python development tools with comprehensive
error handling, retry logic, and helpful troubleshooting guidance. Perfect for bootstrapping new systems or onboarding
new developers.

## Scripts

### install_uv.py

Installs [uv](https://docs.astral.sh/uv/) - the blazing-fast Python package manager and installer from Astral.

**Features:**
- Cross-platform support (Linux, macOS, Windows)
- Smart executable detection (checks PATH and common install locations)
- Configurable network retry logic with exponential backoff
- Automatic shell detection and PATH configuration guidance
- Comprehensive installation verification
- Verbose mode for debugging
- Force reinstall option

**Usage:**
```bash
# Simple installation
./scripts/installers/install_uv.py

# Force reinstall even if already present
./scripts/installers/install_uv.py --force

# Show detailed progress
./scripts/installers/install_uv.py --verbose

# Combine options
./scripts/installers/install_uv.py --force --verbose

# Customize retry behavior for unreliable networks
./scripts/installers/install_uv.py --retries 5 --retry-delay 3

# Maximum reliability configuration
./scripts/installers/install_uv.py --retries 10 --retry-delay 5 --verbose
```

**Options:**
- `--force` - Force reinstall even if UV is already installed
- `-v, --verbose` - Enable verbose output for debugging
- `--retries N` - Maximum number of download retry attempts (default: 3)
- `--retry-delay SECONDS` - Initial delay in seconds between retries with exponential backoff (default: 2)

**What it does:**
1. Checks Python version (requires 3.8+)
2. Searches for existing `uv` installation in PATH and common locations
3. Downloads the official installer from https://astral.sh/uv/install.sh
4. Executes the installer with platform-appropriate commands
5. Verifies installation and provides PATH configuration guidance if needed
6. Cleans up temporary files

**Exit codes:**
- `0` - Success or already installed
- `2` - Download failed
- `3` - Installation failed
- `4` - Verification failed
- `5` - Unsupported platform
- `6` - Python version too old

### install_hatch.py

Installs [Hatch](https://hatch.pypa.io/) - the modern Python project manager and build system.

**Features:**
- Cross-platform support (Linux, macOS, Windows)
- Uses official Hatch universal installer
- Smart executable detection in multiple common locations
- Configurable network retry logic with exponential backoff
- Shell-aware PATH configuration guidance
- Comprehensive error handling and troubleshooting
- Verbose and force options

**Usage:**
```bash
# Simple installation
./scripts/installers/install_hatch.py

# Force reinstall
./scripts/installers/install_hatch.py --force

# Verbose output
./scripts/installers/install_hatch.py --verbose

# Both options
./scripts/installers/install_hatch.py --force -v

# Customize retry behavior for unreliable networks
./scripts/installers/install_hatch.py --retries 5 --retry-delay 3

# Maximum reliability configuration
./scripts/installers/install_hatch.py --retries 10 --retry-delay 5 --verbose
```

**Options:**
- `--force` - Force reinstall even if Hatch is already installed
- `-v, --verbose` - Enable verbose output for debugging
- `--retries N` - Maximum number of download retry attempts (default: 3)
- `--retry-delay SECONDS` - Initial delay in seconds between retries with exponential backoff (default: 2)

**What it does:**
1. Validates Python version (3.8+ required)
2. Checks for existing Hatch installation
3. Downloads universal installer from GitHub releases
4. Runs installer using current Python interpreter
5. Verifies installation across all common locations
6. Provides shell-specific PATH setup instructions if needed

**Exit codes:**
- `0` - Success or already installed
- `2` - Download failed
- `3` - Installation failed
- `4` - Verification failed
- `5` - Unsupported platform
- `6` - Python version incompatible

## Common Features

Both scripts share a robust architecture:

### Smart Detection
```python
# Checks PATH first
$ which uv

# Then searches common locations:
- ~/.cargo/bin/uv
- ~/.local/bin/uv
- /usr/local/bin/uv
- /usr/bin/uv
```

### Network Resilience
- Configurable retry attempts (default: 3, customize with `--retries`)
- Configurable initial delay with exponential backoff (default: 2s, customize with `--retry-delay`)
- 30-second timeout per request
- Helpful troubleshooting if all retries fail

**Retry behavior:**
```bash
# Default: 3 attempts with 2s, 4s, 8s delays
./scripts/installers/install_uv.py

# Aggressive: 10 attempts starting with 1s delay
./scripts/installers/install_uv.py --retries 10 --retry-delay 1

# Conservative: 5 attempts with longer 5s initial delay
./scripts/installers/install_uv.py --retries 5 --retry-delay 5
```

The exponential backoff formula is: `delay = retry_delay * (2 ** (attempt - 2))`
- Attempt 1: No delay
- Attempt 2: Initial delay (e.g., 2s)
- Attempt 3: 2× initial delay (e.g., 4s)
- Attempt 4: 4× initial delay (e.g., 8s)
- And so on...

### Shell Intelligence
Detects your shell and provides appropriate PATH commands:
- **bash/zsh**: `export PATH="..."`
- **fish**: `set -gx PATH "..." $PATH`
- **tcsh/csh**: `setenv PATH "..."`

### Platform Support

| Platform | install_uv.py | install_hatch.py |
|----------|---------------|------------------|
| macOS    | ✓            | ✓               |
| Linux    | ✓            | ✓               |
| Windows  | ✓            | ✓               |

## Troubleshooting

### Tool installed but not in PATH

Both scripts detect this scenario and provide shell-specific guidance:

```bash
✓ UV installed successfully: uv 0.5.14
✓ Found at: /Users/you/.cargo/bin/uv

⚠ UV is installed but not in your PATH

To make UV available globally, add it to your PATH:

  For zsh, add this line to /Users/you/.zshrc:
  export PATH="/Users/you/.cargo/bin:$PATH"

  Then run:
  source /Users/you/.zshrc

  Or use the full path: /Users/you/.cargo/bin/uv
```

### Download failures

Scripts provide actionable troubleshooting:
1. Check internet connection
2. Verify access to installer URLs
3. Check if proxy configuration is needed

**For unreliable networks:**
```bash
# Increase retry attempts and delay
./scripts/installers/install_uv.py --retries 10 --retry-delay 5

# Use verbose mode to see detailed retry information
./scripts/installers/install_uv.py --retries 5 --verbose
```

### Verification failures

If installation succeeds but verification fails:
1. Close and reopen terminal
2. Try `--force` to reinstall
3. Check official documentation links

## Integration with ezcli

These scripts bootstrap the development environment for ezcli itself:

```bash
# Fresh system setup
./scripts/installers/install_uv.py
./scripts/installers/install_hatch.py

# Then use the Makefile
make dev        # Install ezcli with all dev dependencies
```

The project's `scripts/manage.py` relies on `uv` being available, making `install_uv.py` the first step in any ezcli
development setup.

## Design Philosophy

### Bulletproof by Design

1. **Idempotent**: Safe to run multiple times
2. **Informative**: Clear progress and error messages
3. **Helpful**: Provides next steps when things go wrong
4. **Automatic**: Minimal user intervention required
5. **Verifiable**: Confirms success before declaring victory

### Error Handling Strategy

```python
# Every operation checks success
if not download_installer(url, path):
    sys.exit(ExitCode.DOWNLOAD_FAILED)

if not run_installer(path):
    cleanup()
    sys.exit(ExitCode.INSTALL_FAILED)

if not verify_installation():
    sys.exit(ExitCode.VERIFICATION_FAILED)
```

### User Experience Focus

- Uses emojis for visual scanning (✓, ✗, ⚠)
- Groups related information clearly
- Provides copy-paste commands
- Anticipates common issues
- Links to official documentation

## Development

### Adding New Installers

Follow the established pattern:

1. **Platform detection** - Use `platform.system()`
2. **Smart finding** - Check PATH then common locations
3. **Retry logic** - Wrap downloads with exponential backoff
4. **Verification** - Don't trust, verify the installation
5. **PATH guidance** - Help users make tools accessible
6. **Exit codes** - Use the standard enum pattern

### Testing

```bash
# Test in fresh environment
docker run -it python:3.9 bash
# ... copy script and run ...

# Test force reinstall
./install_uv.py --force

# Test verbose output
./install_hatch.py --verbose
```

## References

- **UV Documentation**: https://docs.astral.sh/uv/
- **Hatch Documentation**: https://hatch.pypa.io/
- **UV Installation Guide**: https://docs.astral.sh/uv/getting-started/installation/
- **Hatch Installation Guide**: https://hatch.pypa.io/latest/install/
