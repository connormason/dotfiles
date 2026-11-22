"""
NAS service listing and SSH reachability helpers
"""
from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from cli.infra.config import DOTFILES_DIR
from cli.infra.config import INVENTORY_FILE
from cli.infra.config import NAS_INVENTORY_HOST
from cli.infra.config import SERVICES_DIR
from cli.infra.config import ExitCode
from cli.utils.ansible import require_inventory
from cli.utils.ansible import require_vault_password
from cli.utils.ansible import resolve_ssh_target_from_inventory_host
from cli.utils.formatting import folduser
from cli.utils.shell import shell_command
from cli.utils.styling import printf

if TYPE_CHECKING:

    from cli.infra.types import SSHTarget

__all__ = [
    'list_services',
    'require_nas_reachable',
    'resolve_reachable_nas',
    'warn_on_dirty_services',
]


# ==================================================================================================
# NAS services helpers
# ==================================================================================================


def warn_on_dirty_services() -> None:
    """
    Warn when services/ has uncommitted changes, since a deploy ships the working tree
    """
    result = shell_command(
        ['git', 'status', '--porcelain', '--', 'services'],
        capture_output=True,
        check=False,
        cwd=DOTFILES_DIR,
    )
    if (result.returncode == 0) and result.stdout.strip():
        printf('🟡 services/ has uncommitted changes; deploying the working tree', fg='bright_yellow')
        printf('CI redeploys main whenever it changes a service, which supersedes a branch deploy', indent=3, dim=True)


def list_services() -> list[str]:
    """
    List the deployable services: the directories under services/ that hold a compose.yml

    :return: sorted service names
    """
    return sorted(compose.parent.name for compose in SERVICES_DIR.glob('*/compose.yml'))


# ==================================================================================================
# NAS SSH connection helpers
# ==================================================================================================


def require_nas_reachable(host: str, user: str) -> None:
    """
    Exit with a remedy unless the NAS answers a non-interactive SSH probe

    :param host: SSH host
    :param user: SSH user
    :raises SystemExit: if the probe fails
    """
    result = shell_command(
        ['ssh', '-o', 'ConnectTimeout=5', '-o', 'BatchMode=yes', f'{user}@{host}', 'true'],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        printf(f'❌ Cannot reach the NAS at {user}@{host} over SSH', fg='red', bold=True)
        printf('Is Tailscale up? Does the host resolve? Is your SSH key loaded (ssh-add)?',                 indent=3)
        printf(f'The host comes from ansible_host of "{NAS_INVENTORY_HOST}" in {folduser(INVENTORY_FILE)}', indent=3)
        printf(f'ssh said: {result.stderr.strip()}', indent=3, dim=True)
        sys.exit(ExitCode.COMMAND_FAILED)


def resolve_reachable_nas() -> SSHTarget:
    """
    Check the inventory and vault password, resolve the NAS target, and probe it over SSH

    :return: tuple of (SSH host, SSH user)
    """
    require_inventory()
    require_vault_password()

    target = resolve_ssh_target_from_inventory_host(NAS_INVENTORY_HOST)
    require_nas_reachable(target.host, target.user)
    return target
