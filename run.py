#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "PyYaml >= 6.0",
# ]
# ///
"""
run.py - CLI interface for Connor's personal dotfiles repository

This script provides a command-line interface for managing the dotfiles repository, including inventory management
and codebase maintenance tasks. It is the entry point only: the implementation lives in the ``cli`` package next to it.

Architecture
-----------
The script uses a class-based command registration system: each command subclasses the abstract ``Command`` base,
which registers it on class definition and:
- Automatically builds argparse subparsers from registered commands
- Organizes commands by group for help text
- Supports generating Makefile targets from registered commands
- Allows commands to be script-only or makefile-only

Package layout
--------------
- ``cli/infra/``: configuration and paths, shared types, the ``Command`` base and registry, parser and ``main``
- ``cli/utils/``: styling, subprocess execution, and tool/environment/host helpers
- ``cli/commands/``: one module per command group; importing ``cli.commands`` registers every command in the order
  commands appear in help text and in the generated Makefile

Command Categories
-----------------
- **Setup & Environment**: Install and inspect the uv-managed ``.venv`` (install, dev, shell, status), verify the whole
  environment (doctor), clean artifacts, and manage ``uv.lock`` (lock, lock-check, lock-upgrade, lock-sync)
- **Bootstrap & Deploy**: Run the layered bootstrap stages, provision the home NAS and deploy its Compose services
- **Dotfiles**: Wrap the stow and render tooling and ingest local Claude config (track-claude)
- **Inventory**: Manage the standalone inventory git repository and its vault files
- **Tool Installation**: Install uv and hatch with the bundled installer scripts
- **Hooks**: Install, prepare, uninstall, and run prek hooks
- **Testing**: Run the test suite
- **Utilities**: Generate the Makefile, collect a Python environment diagnostic

Key Features
-----------
- ANSI styling with full color/formatting support (style/printf functions)
- Subprocess execution with live output streaming via pty (shell_command)
- Retry logic with exponential backoff for network operations
- SSH error detection and helpful troubleshooting guidance
- Environment variable configuration for debug mode and repo URLs

Environment Variables
--------------------
- DOTFILES_RUN_DEBUG: Enable debug output (true/false)
- DOTFILES_UV_VERBOSE: Enable verbose uv logging (true/false)
- DOTFILES_INVENTORY_REPO_URL: Override inventory repository URL
- NO_COLOR: Disable ANSI styling when set to any non-empty value

Usage Examples
-------------

    # Create .venv and install dependencies
    python3 run.py install

    # List inventory hosts
    python3 run.py inventory-hosts

    # Update inventory from remote
    python3 run.py update-inventory

    # Clean build artifacts
    python3 run.py clean

    # Generate Makefile
    python3 run.py makefile

See Also
-------
- README.md: User-facing documentation
- CLAUDE.md: Architecture and development guidance
- cli/README.md: Layout of the implementation package

"""
from __future__ import annotations

from cli import commands  # noqa: F401  (importing registers every command)
from cli.infra.main import main

if __name__ == '__main__':
    main()
