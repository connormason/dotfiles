"""
Ansible vault, inventory, and playbook helpers
"""
from __future__ import annotations

import getpass
import json
import sys
from typing import TYPE_CHECKING
from typing import Any

from cli.infra.config import DOTFILES_DIR
from cli.infra.config import INVENTORY_DIR
from cli.infra.config import INVENTORY_FILE
from cli.infra.config import NAS_BOOTSTRAP_PLAYBOOK
from cli.infra.config import VAULT_FILE_PATTERNS
from cli.infra.config import VAULT_PASSWORD
from cli.infra.config import ExitCode
from cli.infra.types import SSHTarget
from cli.utils.formatting import folduser
from cli.utils.shell import shell_command
from cli.utils.styling import printf
from cli.utils.styling import style
from cli.utils.uv import uv_command

if TYPE_CHECKING:
    import argparse
    from pathlib import Path

__all__ = [
    'build_nas_provision_command',
    'find_vault_files',
    'parse_playbook_extra_vars',
    'require_inventory',
    'require_vault_password',
    'resolve_ssh_target_from_inventory_host',
]


# ==================================================================================================
# Ansible vault helpers
# ==================================================================================================


def find_vault_files() -> list[Path]:
    """
    Find all vault.yml files in the inventory directory

    :return: sorted list of vault file paths
    """
    vault_files: list[Path] = []
    for pattern in VAULT_FILE_PATTERNS:
        vault_files.extend(INVENTORY_DIR.glob(pattern))
    return sorted(vault_files)


def require_vault_password() -> None:
    """
    Validate that the vault password file exists and exit with an error if not

    :raises SystemExit: if vault password file is missing
    """
    if not VAULT_PASSWORD.is_file():
        printf('❌ Vault password file not found', fg='red', bold=True)
        printf(f'   Expected: {folduser(VAULT_PASSWORD)}',                                                    indent=3)
        printf(f'   Create it with: {style("echo YOUR_PASSWORD > vault_password.txt", fg="bright_magenta")}', indent=3)
        sys.exit(ExitCode.COMMAND_FAILED)


# ==================================================================================================
# Ansible inventory helpers
# ==================================================================================================


def require_inventory() -> None:
    """
    Validate that the inventory directory exists and exit with an error if not

    :raises SystemExit: if inventory directory is missing
    """
    if not INVENTORY_DIR.exists():
        printf('❌ Inventory directory not found', fg='red', bold=True)
        printf(f'   Expected: {folduser(INVENTORY_DIR)}',                                  indent=3)
        printf(f'   Run: {style("python3 run.py update-inventory", fg="bright_magenta")}', indent=3)
        sys.exit(ExitCode.COMMAND_FAILED)


def resolve_ssh_target_from_inventory_host(host: str) -> SSHTarget:
    """
    Resolve the SSH host and user of an inventory host through ``ansible-inventory``

    :param host: inventory host name
    :return: tuple of (``ansible_host``, ``ansible_user``); missing values fall back to the inventory name and the
             local login, as ssh would
    """
    result = shell_command(
        uv_command(
            'run', 'ansible-inventory',
            '-i',                    str(INVENTORY_FILE),
            '--vault-password-file', str(VAULT_PASSWORD),
            '--host',                host,
        ),
        capture_output=True,
        check=False,
        cwd=DOTFILES_DIR,
    )
    if result.returncode != 0:
        printf(f'❌ Could not read host "{host}" from the inventory', fg='red', bold=True)
        printf(result.stderr.strip(), indent=3)
        sys.exit(ExitCode.COMMAND_FAILED)

    variables: dict[str, Any] | None
    try:
        variables = json.loads(result.stdout)
    except json.JSONDecodeError:
        variables = None

    if not isinstance(variables, dict):
        printf(f'❌ Unexpected ansible-inventory output for host "{host}"', fg='red', bold=True)
        sys.exit(ExitCode.COMMAND_FAILED)

    ssh_host = str(variables.get('ansible_host') or host)
    ssh_user = str(variables.get('ansible_user') or getpass.getuser())
    if '{{' in (ssh_host + ssh_user):
        printf(f'❌ ansible_host/ansible_user for "{host}" are templated: {ssh_user}@{ssh_host}', fg='red', bold=True)
        printf('Host/user values in inventory must be literal values', indent=3)
        sys.exit(ExitCode.COMMAND_FAILED)

    return SSHTarget(host=ssh_host, user=ssh_user)


# ==================================================================================================
# Ansible playbook helpers
# ==================================================================================================


def parse_playbook_extra_vars(extra_vars_list: list[str] | None) -> dict[str, str]:
    """
    Parse ``ansible-playbook`` extra variables (-e, --extra-vars) from command line format (key=val)

    :param extra_vars_list: value from argparse
    :return: mapping from key -> value
    """
    extra_vars: dict[str, str] = {}
    if extra_vars_list:
        for var_str in extra_vars_list:
            if '=' not in var_str:
                printf(
                    f'❌ {style("Error", fg="red", bold=True)}: Invalid extra var format "{var_str}". '
                    f'Use key=value format'
                )
                sys.exit(ExitCode.COMMAND_FAILED)

            key, value = var_str.split('=', 1)
            extra_vars[key.strip()] = value.strip()

    return extra_vars


def build_nas_provision_command(args: argparse.Namespace) -> list[str]:
    """
    Build the ``ansible-playbook`` command line for nas-provision

    :param args: parsed nas-provision arguments
    :return: command and arguments
    """
    cmd: list[str] = uv_command(
        'run', 'ansible-playbook', str(NAS_BOOTSTRAP_PLAYBOOK),
        '-i',                    str(INVENTORY_FILE),
        '--vault-password-file', str(VAULT_PASSWORD),
    )
    if args.tags:
        cmd.extend(['--tags', args.tags])
    if args.limit:
        cmd.extend(['--limit', args.limit])
    if args.check:
        cmd.append('--check')
    if args.diff:
        cmd.append('--diff')
    for key, value in parse_playbook_extra_vars(args.extra_vars).items():
        cmd.extend(['-e', f'{key}={value}'])
    if args.verbose:
        cmd.append('-' + 'v' * args.verbose)
    return cmd
