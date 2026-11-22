"""
Inventory commands (inventory and vault management)
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from typing import Any
from typing import ClassVar

from cli.infra import config
from cli.infra.command import Command
from cli.infra.config import INVENTORY_DIR
from cli.infra.config import INVENTORY_REPO_URL
from cli.infra.config import ExitCode
from cli.utils.ansible import find_vault_files
from cli.utils.ansible import require_inventory
from cli.utils.ansible import require_vault_password
from cli.utils.formatting import folduser
from cli.utils.retry import retry_on_failure
from cli.utils.shell import handle_command_error
from cli.utils.shell import shell_command
from cli.utils.styling import printf
from cli.utils.styling import style
from cli.utils.styling import typestyle

__all__ = [
    'InventoryHostsCommand',
    'InventoryStatusCommand',
    'UpdateInventoryCommand',
    'VaultDecryptCommand',
    'VaultEncryptCommand',
]


# ==================================================================================================
# Inventory commands
#
# Commands for managing the standalone inventory git repository
#
# The inventory is a separate repository cloned into the inventory/ directory by run.py.
#
# Key commands:
#   - inventory-hosts:  Parse inventory.yml and display available bootstrap targets
#   - inventory-status: Show git status and metadata for inventory directory
#   - update-inventory: Clone (if missing) or pull (if exists) inventory repo
#     - Supports --force flag to reset uncommitted changes before pulling
#     - Includes retry logic with exponential backoff for network resilience
#     - Provides SSH error detection and troubleshooting guidance
#   - vault-decrypt:    Decrypt all inventory vault files for editing
#   - vault-encrypt:    Re-encrypt all inventory vault files after editing
# ==================================================================================================


class InventoryHostsCommand(Command):
    """
    List available bootstrap targets from inventory
    """
    name:  ClassVar[str] = 'inventory-hosts'
    group: ClassVar[str] = 'Inventory'

    def run(self, args: argparse.Namespace) -> None:
        printf('Available Bootstrap Targets', bold=True, fg='bright_white')
        printf('=' * 60,                      bold=True)

        # Check that inventory file exists
        if not config.INVENTORY_FILE.exists():
            printf('')
            printf('❌ Inventory file not found', fg='red', bold=True)
            printf(f'   Expected: {folduser(config.INVENTORY_FILE)}',                                 indent=3)
            printf(f'   Run: {style("python3 run.py update-inventory", fg="bright_magenta")}', indent=3)
            sys.exit(ExitCode.COMMAND_FAILED)

        # PyYAML is the one third-party dependency: report a missing module separately from an unparsable inventory
        try:
            import yaml
        except ImportError:
            hint = style('scripts/hooks/uv-public.sh run python run.py inventory-hosts', fg='bright_magenta')
            printf('')
            printf('❌ PyYAML is required to read the inventory', fg='red', bold=True)
            printf(f'Run it through uv: {hint}', indent=3)
            sys.exit(ExitCode.SETUP_ERROR)

        # Parse inventory file
        try:
            with config.INVENTORY_FILE.open() as f:
                inventory = yaml.safe_load(f)
        except Exception as e:
            printf('')
            printf('❌ Failed to parse inventory file', fg='red', bold=True)
            printf(f'   Error: {e}', indent=3)
            sys.exit(ExitCode.COMMAND_FAILED)

        # Display all groups and hosts
        if (not inventory) or ('all' not in inventory):
            printf('')
            printf('⚠️  No hosts found in inventory', fg='yellow')
            sys.exit(ExitCode.SUCCESS)

        all_hosts: set[str] = set()
        if 'children' in inventory.get('all', {}):
            printf('')
            for group_name, group_data in inventory['all']['children'].items():
                printf(f'{group_name}:', fg='cyan', bold=True)
                if 'hosts' in group_data:
                    for host_name, host_data in group_data['hosts'].items():
                        all_hosts.add(host_name)
                        ansible_host = host_data.get('ansible_host', host_name) if host_data else host_name
                        printf(f'  └─ {style(host_name, fg="green")}')
                        if ansible_host != host_name:
                            printf(f'     (connects to: {style(ansible_host, dim=True)})', indent=3)
                else:
                    printf('  └─ (no hosts)', dim=True)
                printf('')

        # Show total
        printf('=' * 60, bold=True)
        printf(f'Total hosts: {typestyle(len(all_hosts))}', fg='bright_white', dim=True)


# TODO: cleanup formatting
class InventoryStatusCommand(Command):
    """
    Display current status of inventory directory
    """
    name:  ClassVar[str] = 'inventory-status'
    group: ClassVar[str] = 'Inventory'

    def run(self, args: argparse.Namespace) -> None:
        printf('Inventory Status', bold=True, fg='bright_white')
        printf('=' * 60, bold=True)
        printf('')

        # Check if inventory directory exists
        if not INVENTORY_DIR.exists():
            printf('Status:   ', fg='bright_white', bold=True, reset=False)
            printf('Not found',  fg='red',          bold=True)
            printf(f'Path:     {style(folduser(INVENTORY_DIR), fg="magenta", dim=True)}', dim=True)
            printf('')
            printf(
                f'💡 Run {style("python3 run.py update-inventory", fg="bright_magenta")} to clone the inventory',
                fg='yellow',
            )
            return

        printf('Status:   ', fg='bright_white', bold=True, reset=False)
        printf('Found',      fg='green',        bold=True)
        printf(f'Path:     {style(folduser(INVENTORY_DIR), fg="magenta", dim=True)}', dim=True)
        printf('')

        # Check if it's a git repository
        git_dir = INVENTORY_DIR / '.git'
        if not git_dir.exists():
            printf('Type:     ', fg='bright_white', bold=True, reset=False)
            printf('Not a git repository', fg='yellow', bold=True)
            printf('')
            printf('⚠️  Inventory exists but is not a git repository', fg='yellow')
            printf(f'   Run {style("python3 run.py update-inventory",  fg="bright_magenta")} to fix', indent=3)
            return

        printf('Type:     ',     fg='bright_white', bold=True, reset=False)
        printf('Git repository', fg='green',        bold=True)
        printf('')

        # Get git remote information
        try:
            result = shell_command(
                ['git', 'remote', 'get-url', 'origin'],
                cwd=INVENTORY_DIR,
                capture_output=True,
            )
            remote_url = result.stdout.strip()
            printf('Remote:   ',           fg='bright_white', bold=True, reset=False)
            printf(remote_url,             fg='cyan')
        except subprocess.CalledProcessError:
            printf('Remote:   ',           fg='bright_white', bold=True, reset=False)
            printf('No remote configured', fg='yellow')

        # Get current branch
        try:
            result = shell_command(
                ['git', 'branch', '--show-current'],
                cwd=INVENTORY_DIR,
                capture_output=True,
            )
            branch = result.stdout.strip()
            printf('Branch:   ', fg='bright_white', bold=True, reset=False)
            printf(branch,       fg='cyan')
        except subprocess.CalledProcessError:
            printf('Branch:   ', fg='bright_white', bold=True, reset=False)
            printf('Unknown',    fg='yellow')

        # Get last commit info
        try:
            result = shell_command(
                ['git', 'log', '-1', '--format=%h - %s (%cr)'],
                cwd=INVENTORY_DIR,
                capture_output=True,
            )
            last_commit = result.stdout.strip()
            printf('Commit:   ', fg='bright_white', bold=True, reset=False)
            printf(last_commit,  dim=True)
        except subprocess.CalledProcessError:
            pass

        # Check for uncommitted changes
        try:
            result = shell_command(
                ['git', 'status', '--porcelain'],
                cwd=INVENTORY_DIR,
                capture_output=True,
            )
            if result.stdout.strip():
                printf('')
                printf('⚠️  Uncommitted changes detected', fg='yellow', bold=True)
                for line in result.stdout.strip().split('\n')[:5]:
                    printf(f'   {line}', indent=3, fg='yellow')
        except subprocess.CalledProcessError:
            pass

        # Check if inventory.yml file exists
        printf('')
        if config.INVENTORY_FILE.exists():
            printf('Inventory file:', fg='bright_white', bold=True, reset=False)
            printf(' Found',          fg='green',        bold=True)
            printf(f'   {style(folduser(config.INVENTORY_FILE), fg="magenta", dim=True)}', indent=3)
        else:
            printf('Inventory file:', fg='bright_white', bold=True, reset=False)
            printf(' Not found',      fg='red',          bold=True)
            printf(f'   Expected: {style(folduser(config.INVENTORY_FILE), fg="magenta", dim=True)}', indent=3)


class UpdateInventoryCommand(Command):
    """
    Update inventory repo
    """
    name:  ClassVar[str] = 'update-inventory'
    group: ClassVar[str] = 'Inventory'

    class Args(argparse.Namespace):
        force: bool     # --force

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            '-f',
            '--force',
            action='store_true',
            help='Force update by discarding any uncommitted local changes',
        )

    @staticmethod
    @retry_on_failure(max_attempts=3, delay=2.0, backoff=2.0)
    def pull_inventory_repo(*, force: bool = False, timeout: float = 30, **kwargs: Any) -> subprocess.CompletedProcess:
        """
        Pull the latest inventory changes, optionally discarding uncommitted local changes first

        :param force: reset uncommitted changes before pulling
        :param timeout: timeout in seconds for ``git pull`` command
        :param kwargs: extra keyword arguments for :func:`shell_command`
        :return: completed ``git pull`` process
        """

        # If --force flag provided, reset any uncommitted changes before pulling
        if force:
            try:
                result = shell_command(
                    ['git', 'status', '--porcelain'],
                    cwd=INVENTORY_DIR,
                    capture_output=True,
                )
                if result.stdout.strip():
                    printf('⚠️  Uncommitted changes detected, resetting...', fg='yellow', indent=3)
                    shell_command(
                        ['git', 'reset', '--hard', 'HEAD'],
                        cwd=INVENTORY_DIR,
                        indent=3,
                    )
            except subprocess.CalledProcessError:
                pass    # Continue with pull anyway

        try:
            cp = shell_command(
                ['git', 'pull', 'origin', 'main'],
                cwd=INVENTORY_DIR,
                indent=3,
                timeout=timeout,
                **kwargs,
            )
        except subprocess.CalledProcessError as e:
            handle_command_error(e, 'Error pulling inventory repo')
            raise
        else:
            printf('✅ Inventory updated', fg='bright_green')
            return cp

    @staticmethod
    @retry_on_failure(max_attempts=3, delay=5.0, backoff=2.0)
    def clone_inventory_repo(*, timeout: float = 60, **kwargs: Any) -> subprocess.CompletedProcess:
        """
        Clone the inventory repo into the inventory directory

        :param timeout: timeout in seconds for ``git clone`` command
        :param kwargs: extra keyword arguments for :func:`shell_command`
        :return: completed ``git clone`` process
        """
        try:
            cp = shell_command(
                ['git', 'clone', '--no-progress', INVENTORY_REPO_URL, str(INVENTORY_DIR)],
                indent=3,
                timeout=timeout,
                **kwargs,
            )
        except subprocess.CalledProcessError as e:
            handle_command_error(e, 'Error cloning inventory repo')
            raise
        else:
            printf('✅ Inventory cloned', fg='bright_green')
            return cp

    def run(self, args: Args) -> None:
        printf('🔄 Updating inventory...', fg='bright_white')
        try:

            # Case 1: Inventory directory exists and is a git repo - pull latest changes
            if INVENTORY_DIR.exists() and (INVENTORY_DIR / '.git').exists():
                self.pull_inventory_repo(force=args.force)

            # Case 2: Inventory directory exists but isn't a git repo - remove and re-clone
            elif INVENTORY_DIR.exists():
                shutil.rmtree(INVENTORY_DIR)
                self.clone_inventory_repo()

            # Case 3: Inventory directory does not exist - clone from remote
            else:
                self.clone_inventory_repo()

        except Exception:
            printf('❌ Failed to update inventory after multiple attempts', fg='red', bold=True)
            sys.exit(ExitCode.COMMAND_FAILED)


class VaultDecryptCommand(Command):
    """
    Decrypt all inventory vault files for editing
    """
    name:  ClassVar[str] = 'vault-decrypt'
    group: ClassVar[str] = 'Inventory'

    def run(self, args: argparse.Namespace) -> None:
        require_vault_password()
        require_inventory()

        vault_files = find_vault_files()
        if not vault_files:
            printf('⚠️  No vault files found in inventory', fg='yellow')
            return

        printf('🔓 Decrypting vault files...', fg='bright_white')
        failed = 0
        for vault_file in vault_files:
            relative = vault_file.relative_to(INVENTORY_DIR)
            try:
                shell_command(
                    ['ansible-vault', 'decrypt', str(vault_file)],
                    capture_output=True,
                )
            except subprocess.CalledProcessError as e:
                # ansible-vault returns error if file is already decrypted
                stderr = e.stderr if isinstance(e.stderr, str) else (e.stderr.decode() if e.stderr else '')
                if ('is not vault encrypted' in stderr) or ('input is not vault encrypted' in stderr):
                    printf(f'  └─ {style(str(relative), fg="yellow")} already decrypted, skipping', indent=1)
                else:
                    printf(f'  └─ {style(str(relative), fg="red")} failed to decrypt', indent=1)
                    if stderr.strip():
                        printf(f'     {stderr.strip()}', indent=1, fg='red')
                    failed += 1
            else:
                printf(f'  └─ {style(str(relative), fg="green")} decrypted', indent=1)

        if failed:
            printf(f'❌ {failed} file{"s" if failed != 1 else ""} failed to decrypt', fg='red', bold=True)
            sys.exit(ExitCode.COMMAND_FAILED)
        else:
            printf('✅ All vault files decrypted', fg='bright_green')


class VaultEncryptCommand(Command):
    """
    Re-encrypt all inventory vault files after editing
    """
    name:  ClassVar[str] = 'vault-encrypt'
    group: ClassVar[str] = 'Inventory'

    def run(self, args: argparse.Namespace) -> None:
        require_vault_password()
        require_inventory()

        vault_files = find_vault_files()
        if not vault_files:
            printf('⚠️  No vault files found in inventory', fg='yellow')
            return

        printf('🔒 Encrypting vault files...', fg='bright_white')
        failed = 0
        for vault_file in vault_files:
            relative = vault_file.relative_to(INVENTORY_DIR)
            try:
                shell_command(
                    ['ansible-vault', 'encrypt', str(vault_file)],
                    capture_output=True,
                )
            except subprocess.CalledProcessError as e:
                stderr = e.stderr if isinstance(e.stderr, str) else (e.stderr.decode() if e.stderr else '')
                if 'input is already encrypted' in stderr:
                    printf(f'  └─ {style(str(relative), fg="yellow")} already encrypted, skipping', indent=1)
                else:
                    printf(f'  └─ {style(str(relative), fg="red")} failed to encrypt', indent=1)
                    if stderr.strip():
                        printf(f'     {stderr.strip()}', indent=1, fg='red')
                    failed += 1
            else:
                printf(f'  └─ {style(str(relative), fg="green")} encrypted', indent=1)

        if failed:
            printf(f'❌ {failed} file{"s" if failed != 1 else ""} failed to encrypt', fg='red', bold=True)
            sys.exit(ExitCode.COMMAND_FAILED)
        else:
            printf('✅ All vault files encrypted', fg='bright_green')
