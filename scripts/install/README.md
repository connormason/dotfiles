[Project Root](../../README.md) > [Scripts](../README.md) > **Install Scripts**

# Install Scripts

Installer scripts for bootstrapping tools commonly used in development environments.

<!-- mdformat-toc start --slug=github --maxlevel=3 --minlevel=2 -->

- [Overview](#overview)
  - [Script Summary](#script-summary)
- [Scripts](#scripts)
  - [install_uv.py](#install_uvpy)
  - [install_hatch.py](#install_hatchpy)
  - [`run.py` integration](#runpy-integration)
- [Common Features](#common-features)
  - [Smart Detection](#smart-detection)
  - [Network Resilience](#network-resilience)
  - [Shell-Aware PATH Guidance](#shell-aware-path-guidance)
  - [Platform Support](#platform-support)
- [Troubleshooting](#troubleshooting)
  - [Tool installed but not in PATH](#tool-installed-but-not-in-path)
  - [Download failures](#download-failures)
  - [Verification failures](#verification-failures)
- [Design Philosophy](#design-philosophy)
- [Adding New Installers](#adding-new-installers)
- [Re-syncing from the source repository](#re-syncing-from-the-source-repository)
- [References](#references)

<!-- mdformat-toc end -->

## Overview<a name="overview"></a>

### Script Summary<a name="script-summary"></a>

| Script             | Type   | Purpose                                |
| ------------------ | ------ | -------------------------------------- |
| `install_uv.py`    | Python | uv package manager (cross-platform)    |
| `install_hatch.py` | Python | Hatch project manager (cross-platform) |

## Scripts<a name="scripts"></a>

### install_uv.py<a name="install_uvpy"></a>

Installs [uv](https://docs.astral.sh/uv/), the fast Python package manager from Astral, using the official installer
from `https://astral.sh/uv/install.sh`. Cross-platform (macOS, Linux, Windows). Provides retry logic with exponential
backoff for unreliable networks and shell-specific PATH guidance when the binary is not on PATH after install.

**Usage:**

```bash
./scripts/install/install_uv.py                              # Simple installation
./scripts/install/install_uv.py --force                      # Force reinstall
./scripts/install/install_uv.py --verbose                    # Detailed progress output
./scripts/install/install_uv.py --retries 5 --retry-delay 3  # Custom retry behavior
```

**Options:**

- `-f, --force` — reinstall even if uv is already present
- `-e, --ensure` — install only if uv is missing, otherwise exit quietly with no output (what `run.py` uses)
- `-p, --print-path` — print the path to the uv executable and exit (does not install)
- `-t, --timeout SECONDS` — download timeout (default: 30.0)
- `-r, --retries NUM` — max download retry attempts (default: 3)
- `-d, --retry-delay SECONDS` — initial delay between retries with exponential backoff (default: 2)
- `-m, --download-method METHOD [METHOD ...]` — ordered download methods, highest priority first (`curl`, `urllib`;
  default: `curl urllib`)
- `-v, --verbose` — verbose output for debugging

**What it does:**

1. Checks Python version (3.8+ required)
2. Searches for an existing `uv` in PATH and common install locations
3. Downloads the official installer script
4. Executes the installer with platform-appropriate commands
5. Verifies the installation and prints PATH setup instructions if needed
6. Cleans up temporary files

**Exit codes:** `0` success (or already installed); `1` invalid parameters; `2` download failed; `3` installation
failed; `4` verification failed; `5` unsupported platform; `6` Python version too old; `7` not found (`--print-path`).

### install_hatch.py<a name="install_hatchpy"></a>

Installs [Hatch](https://hatch.pypa.io/), the modern Python project manager and build backend, using the official
universal installer from GitHub releases. Cross-platform with the same retry logic and PATH guidance as `install_uv.py`.

**Usage:**

```bash
./scripts/install/install_hatch.py
./scripts/install/install_hatch.py --force
./scripts/install/install_hatch.py --verbose
./scripts/install/install_hatch.py --retries 5 --retry-delay 3
```

**Options:** the same as `install_uv.py` (`-f`, `-e`, `-p`, `-t`, `-r`, `-d`, `-m`, `-v`), applied to hatch.

**What it does:**

1. Validates Python version (3.8+ required)
2. Checks for an existing hatch installation in PATH and common locations
3. Downloads the universal installer from GitHub releases
4. Runs the installer using the current Python interpreter
5. Verifies installation and provides shell-specific PATH setup instructions

**Exit codes:** the same as `install_uv.py`.

### `run.py` integration<a name="runpy-integration"></a>

`python3 run.py install-uv` and `python3 run.py install-hatch` run these scripts (options `--force`, `--verbose`,
`--retries`, `--retry-delay`). `run.py`'s `ensure_uv()` runs `install_uv.py --ensure` when uv is missing.

## Common Features<a name="common-features"></a>

Both Python installers (`install_uv.py`, `install_hatch.py`) share the following characteristics.

### Smart Detection<a name="smart-detection"></a>

Checks PATH first, then falls back to common install locations:

```
~/.cargo/bin/       ~/.local/bin/
/usr/local/bin/     /usr/bin/
```

### Network Resilience<a name="network-resilience"></a>

Exponential backoff formula: `delay = retry_delay * (2 ** (attempt - 2))`.

| Attempt | Delay (default) |
| ------- | --------------- |
| 1       | no delay        |
| 2       | 2 s             |
| 3       | 4 s             |
| 4       | 8 s             |

```bash
# Aggressive: 10 attempts starting with 1 s delay
./scripts/install/install_uv.py --retries 10 --retry-delay 1

# Conservative: 5 attempts with 5 s initial delay
./scripts/install/install_uv.py --retries 5 --retry-delay 5
```

### Shell-Aware PATH Guidance<a name="shell-aware-path-guidance"></a>

When the tool is installed but not on PATH, the script detects the current shell and prints the appropriate command:

- **bash/zsh:** `export PATH="..."`
- **fish:** `set -gx PATH "..." $PATH`
- **tcsh/csh:** `setenv PATH "..."`

### Platform Support<a name="platform-support"></a>

| Platform | install_uv.py | install_hatch.py |
| -------- | ------------- | ---------------- |
| macOS    | yes           | yes              |
| Linux    | yes           | yes              |
| Windows  | yes           | yes              |

## Troubleshooting<a name="troubleshooting"></a>

### Tool installed but not in PATH<a name="tool-installed-but-not-in-path"></a>

Both Python installers detect this and print shell-specific instructions. Add the printed `export` line to your shell RC
file and `source` it, or open a new terminal.

### Download failures<a name="download-failures"></a>

1. Check internet connectivity and proxy configuration.
2. Increase retry attempts: `--retries 10 --retry-delay 5 --verbose`.

### Verification failures<a name="verification-failures"></a>

1. Close and reopen the terminal.
2. Try `--force` to reinstall cleanly.
3. Consult official documentation (links below).

## Design Philosophy<a name="design-philosophy"></a>

All installers follow the same principles:

1. **Idempotent** — safe to run multiple times; skip if already installed.
2. **Informative** — clear progress messages at each step.
3. **Helpful** — actionable next steps when something goes wrong.
4. **Verifiable** — confirm success before declaring victory.

## Adding New Installers<a name="adding-new-installers"></a>

Follow the established pattern:

1. **Platform detection** — use `platform.system()`
2. **Smart finding** — check PATH then common locations
3. **Retry logic** — wrap downloads with exponential backoff
4. **Verification** — do not trust; verify after installation
5. **PATH guidance** — detect shell and print the right command
6. **Exit codes** — use a typed `ExitCode` enum

## Re-syncing from the source repository<a name="re-syncing-from-the-source-repository"></a>

These scripts are copied from the author's other dotfiles repository, with a scrub pass so nothing environment-specific
reaches this public repo (`install_uv.py`, `install_hatch.py`). To re-sync, copy the newer file over the local one and
re-apply the same pass:

- Header: keep the author name; drop the email, any provenance lines that name an internal tool, and its version
- Remove any internal bug-tracker link comments (keep the explanation of the workaround they annotate)
- Reword employer-specific phrasing in explanations (for example, about native trust stores) to "corporate CAs/hosts"
- Verify with the repository leak guard (`python3 run.py run-hooks check-leaks --all-files`) and a `--help` smoke test
  per script

The scrub rules come from the work-parity design,
[`docs/plans/2026-11/2026-11-02-work-parity-design.md`](../../docs/plans/2026-11/2026-11-02-work-parity-design.md).

## References<a name="references"></a>

- [uv Documentation](https://docs.astral.sh/uv/)
- [uv Installation Guide](https://docs.astral.sh/uv/getting-started/installation/)
- [Hatch Documentation](https://hatch.pypa.io/)
- [Hatch Installation Guide](https://hatch.pypa.io/latest/install/)
