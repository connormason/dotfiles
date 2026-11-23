"""
Bootstrap & Deploy commands (bootstrap, nas-provision, nas-deploy, ha-pull, ha-push)
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path
from typing import ClassVar

from cli.infra.command import Command
from cli.infra.config import ANSIBLE_REQUIREMENTS
from cli.infra.config import BOOTSTRAP_SCRIPT
from cli.infra.config import DOTFILES_DIR
from cli.infra.config import HA_CONFIG_DIR
from cli.infra.config import NAS_DEPLOY_SCRIPT
from cli.infra.config import ExitCode
from cli.utils.ansible import build_nas_provision_command
from cli.utils.formatting import folduser
from cli.utils.homeassistant import HA_SECRETS_FILE
from cli.utils.homeassistant import HASyncError
from cli.utils.homeassistant import TreeDiff
from cli.utils.homeassistant import apply_ha_changes
from cli.utils.homeassistant import apply_tree_diff
from cli.utils.homeassistant import delete_ha_files
from cli.utils.homeassistant import diff_ha_secrets
from cli.utils.homeassistant import diff_trees
from cli.utils.homeassistant import fetch_ha_config
from cli.utils.homeassistant import fetch_ha_secrets
from cli.utils.homeassistant import ha_cli
from cli.utils.homeassistant import ha_config_has_local_changes
from cli.utils.homeassistant import ha_secrets_template
from cli.utils.homeassistant import ha_ssh_command
from cli.utils.homeassistant import list_ha_tree
from cli.utils.homeassistant import print_tree_diff
from cli.utils.homeassistant import render_ha_secrets
from cli.utils.homeassistant import require_ha_reachable
from cli.utils.homeassistant import write_ha_secrets
from cli.utils.nas import list_services
from cli.utils.nas import resolve_reachable_nas
from cli.utils.nas import warn_on_dirty_services
from cli.utils.prompts import confirm
from cli.utils.prompts import select_option
from cli.utils.shell import shell_command
from cli.utils.styling import pathstyle
from cli.utils.styling import printf
from cli.utils.styling import style
from cli.utils.uv import uv_command

__all__ = [
    'BootstrapCommand',
    'HaPullCommand',
    'HaPushCommand',
    'NasDeployCommand',
    'NasProvisionCommand',
]


# ==================================================================================================
# Bootstrap & Deploy commands
#
# Commands:
#   - bootstrap:     Run the layered bootstrap stages on local machine
#   - nas-provision: Run the Ansible playbook (playbooks/nas_bootstrap.yml) against the inventory's ``nas`` host
#   - nas-deploy:    Sync services/ to the NAS and run deploy.sh there (scripts/nas/deploy-services.sh, as CI does)
#   - ha-pull:       Pull the tracked Home Assistant YAML from the HAOS VM into services/homeassistant/config/
#   - ha-push:       Push services/homeassistant/config/ to the VM, validate with `ha core check`, roll back on failure
# ==================================================================================================


class BootstrapCommand(Command):
    """
    Run the layered bootstrap stages (bootstrap/bootstrap.sh) on local machine
    """
    name:  ClassVar[str] = 'bootstrap'
    group: ClassVar[str] = 'Bootstrap & Deploy'

    class Args(argparse.Namespace):
        dry_run:    bool            # --dry-run
        list:       bool            # --list
        only:       str | None      # --only
        from_stage: str | None      # --from
        resume:     bool            # --resume
        verify:     bool            # --verify
        no_log:     bool            # --no-log

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simulate every stage',
        )
        parser.add_argument(
            '--list',
            action='store_true',
            help='List stages across layers',
        )
        parser.add_argument(
            '--only',
            metavar='STAGE',
            help='Run a single stage',
        )
        parser.add_argument(
            '--from',
            dest='from_stage',
            metavar='STAGE',
            help='Run from STAGE onward',
        )
        parser.add_argument(
            '--resume',
            action='store_true',
            help='Continue after the last completed stage',
        )
        parser.add_argument(
            '--verify',
            action='store_true',
            help='Run doctor after all stages succeed',
        )
        parser.add_argument(
            '--no-log',
            action='store_true',
            help='Do not tee output to the bootstrap log',
        )

    def run(self, args: Args) -> None:
        cmd: list[str] = ['bash', str(BOOTSTRAP_SCRIPT)]
        for flag, enabled in (
            ('--dry-run', args.dry_run),
            ('--list',    args.list),
            ('--resume',  args.resume),
            ('--verify',  args.verify),
            ('--no-log',  args.no_log),
        ):
            if enabled:
                cmd.append(flag)

        if args.only:
            cmd.extend(['--only', args.only])
        if args.from_stage:
            cmd.extend(['--from', args.from_stage])

        result = shell_command(cmd, check=False)
        sys.exit(result.returncode)


class NasProvisionCommand(Command):
    """
    Provision the NAS with the Ansible playbook: system config, the stow engine, then services
    """
    name:  ClassVar[str] = 'nas-provision'
    group: ClassVar[str] = 'Bootstrap & Deploy'

    class Args(argparse.Namespace):
        tags:       str | None          # --tags
        limit:      str | None          # --limit
        check:      bool                # --check
        diff:       bool                # --diff
        extra_vars: list[str] | None    # --extra-vars
        verbose:    int                 # --verbose

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            '--tags',
            metavar='TAGS',
            help=(
                'Only run tasks with these comma-separated tags\n'
                '(e.g. debian,dotfiles,haos,services,secrets)'
            ),
        )
        parser.add_argument(
            '--limit',
            metavar='HOSTS',
            help='Limit the run to these inventory hosts',
        )
        parser.add_argument(
            '--check',
            action='store_true',
            help='Predict changes without making them',
        )
        parser.add_argument(
            '--diff',
            action='store_true',
            help='Show file and template differences',
        )
        parser.add_argument(
            '-e',
            '--extra-vars',
            action='append',
            metavar='KEY=VALUE',
            help=(
                'Extra playbook variable (repeatable),\n'
                'e.g. -e dotfiles_repo_version=my-branch'
            ),
        )
        parser.add_argument(
            '-v',
            '--verbose',
            action='count',
            default=0,
            help='Increase Ansible verbosity (-v, -vv, ...)',
        )

    def run(self, args: Args) -> None:
        playbook_cmd = build_nas_provision_command(args)
        resolve_reachable_nas()

        printf('📦 Installing Ansible collections', fg='bright_cyan')
        galaxy = shell_command(
            uv_command('run', 'ansible-galaxy', 'collection', 'install', '-r', str(ANSIBLE_REQUIREMENTS)),
            check=False,
            cwd=DOTFILES_DIR,
        )
        if galaxy.returncode != 0:
            printf(
                '🟡 Collection install failed; continuing with the collections already installed',
                fg='bright_yellow',
            )

        result = shell_command(playbook_cmd, check=False, cwd=DOTFILES_DIR)
        sys.exit(result.returncode)


class NasDeployCommand(Command):
    """
    Sync services/ to the NAS and run deploy.sh there (the same script CI uses)
    """
    name:  ClassVar[str] = 'nas-deploy'
    group: ClassVar[str] = 'Bootstrap & Deploy'

    class Args(argparse.Namespace):
        service: str | None     # positional arg "SERVICE"
        dry_run: bool           # --dry-run

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            'service',
            nargs='?',
            help="Directory under services/ to deploy, or 'all' (prompts for one when omitted)",
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview the rsync and print the remote command without running it',
        )

    def run(self, args: Args) -> None:
        service = args.service
        if service is None:
            if not sys.stdin.isatty():
                printf("❌ No service given and stdin is not a terminal; pass a service or 'all'", fg='red', bold=True)
                sys.exit(ExitCode.COMMAND_FAILED)

            service = select_option('Select a service to deploy:', ['all', *list_services()])
            if service is None:
                printf('Cancelled; nothing was deployed', fg='yellow')
                sys.exit(ExitCode.USER_CANCELLED)

        host, user = resolve_reachable_nas()
        warn_on_dirty_services()

        cmd: list[str] = ['bash', str(NAS_DEPLOY_SCRIPT)]
        if args.dry_run:
            cmd.append('--dry-run')
        cmd.append(service)

        result = shell_command(cmd, env={'NAS_HOST': host, 'NAS_USER': user}, check=False)
        sys.exit(result.returncode)


class HaPullCommand(Command):
    """
    Pull the tracked Home Assistant YAML from the HAOS VM into services/homeassistant/config/
    """
    name:  ClassVar[str]  = 'ha-pull'
    group: ClassVar[str]  = 'Bootstrap & Deploy'

    class Args(argparse.Namespace):
        dry_run: bool       # --dry-run
        force:   bool       # --force

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            '-n',
            '--dry-run',
            action='store_true',
            help='Show what would change in the repo without writing anything',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Overwrite uncommitted local edits to the tracked Home Assistant files',
        )

    def run(self, args: Args) -> None:
        if ha_config_has_local_changes() and not (args.force or args.dry_run):
            printf(
                '❌ services/homeassistant/config/ has uncommitted changes that a pull would overwrite',
                fg='red',
                bold=True,
            )
            printf('Commit or push them first (ha-push), or re-run with --force to discard them', indent=3)
            sys.exit(ExitCode.COMMAND_FAILED)

        require_ha_reachable()
        with tempfile.TemporaryDirectory() as tmp:
            remote = Path(tmp)
            try:
                fetch_ha_config(remote)
            except HASyncError as e:
                printf(f'❌ {e}', fg='red', bold=True)
                sys.exit(ExitCode.COMMAND_FAILED)

            diff = diff_trees(HA_CONFIG_DIR, remote)
            if not diff.changed:
                printf('✅ services/homeassistant/config/ already matches the VM', fg='bright_green')
                return

            printf(f'🔎 Changes the VM has relative to {pathstyle(folduser(HA_CONFIG_DIR))}:', fg='bright_cyan')
            print_tree_diff(diff, verbs=('new', 'changed', 'deleted on the VM'))
            if args.dry_run:
                return

            apply_tree_diff(remote, HA_CONFIG_DIR, diff)
            printf('✅ Pulled; review with git diff, then commit', fg='bright_green')


class HaPushCommand(Command):
    """
    Push services/homeassistant/config/ to the HAOS VM, validate it with 'ha core check', and roll back on failure
    """
    name:  ClassVar[str]  = 'ha-push'
    group: ClassVar[str]  = 'Bootstrap & Deploy'

    class Args(argparse.Namespace):
        dry_run: bool       # --dry-run
        restart: bool       # --restart
        yes:     bool       # --yes

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            '-n',
            '--dry-run',
            action='store_true',
            help='Show what would change on the VM without writing anything',
        )
        parser.add_argument(
            '--restart',
            action='store_true',
            help='Restart Home Assistant Core after a successful config check',
        )
        parser.add_argument(
            '-y',
            '--yes',
            action='store_true',
            help='Skip the confirmation prompt',
        )

    def run(self, args: Args) -> None:
        if not list_ha_tree(HA_CONFIG_DIR):
            printf(f'❌ No tracked files under {pathstyle(folduser(HA_CONFIG_DIR))}', fg='red', bold=True)
            printf(f'Seed it from the VM first: {style("python3 run.py ha-pull", fg="bright_magenta")}', indent=3)
            sys.exit(ExitCode.COMMAND_FAILED)

        require_ha_reachable()

        # secrets.yaml is rendered from the vault; without a template in the repo the VM's file is left alone
        new_secrets: str | None = None
        if (secrets_template := ha_secrets_template()) is not None:
            try:
                new_secrets = render_ha_secrets(secrets_template)
            except HASyncError as e:
                printf(f'❌ {e}', fg='red', bold=True)
                sys.exit(ExitCode.COMMAND_FAILED)

        with tempfile.TemporaryDirectory() as tmp:
            snapshot = Path(tmp)
            old_secrets: str | None = None
            try:
                fetch_ha_config(snapshot)
                diff = diff_trees(snapshot, HA_CONFIG_DIR)

                secrets_diff = TreeDiff([], [], [])
                if new_secrets is not None:
                    old_secrets  = fetch_ha_secrets()
                    secrets_diff = diff_ha_secrets(old_secrets, new_secrets)

                if not (diff.changed or secrets_diff.changed):
                    printf('✅ The VM already matches services/homeassistant/config/', fg='bright_green')
                    return

                if diff.changed:
                    printf('🔎 Changes the push would make on the VM:', fg='bright_cyan')
                    print_tree_diff(diff, verbs=('new', 'changed', 'deleted'))
                if secrets_diff.changed:
                    printf(f'🔎 Changes to {HA_SECRETS_FILE} (key names only):', fg='bright_cyan')
                    print_tree_diff(secrets_diff, verbs=('new', 'changed', 'removed'))
                if args.dry_run:
                    return
                if not (args.yes or confirm('Apply these changes to the VM?', default=False)):
                    printf('Cancelled; nothing was changed', fg='yellow')
                    sys.exit(ExitCode.USER_CANCELLED)

                try:
                    # Secrets go first: the config being uploaded may already reference a new key
                    if secrets_diff.changed and new_secrets is not None:
                        write_ha_secrets(new_secrets)
                    apply_ha_changes(HA_CONFIG_DIR, diff)

                # A failure mid-push can leave some files written; the rollback is idempotent, so it is safe then
                except HASyncError as e:
                    printf(f'❌ {e}', fg='red', bold=True)
                    self._roll_back(snapshot, old_secrets, restore_secrets=secrets_diff.changed)
                    printf('The VM was restored to its previous state', fg='yellow', indent=3)
                    sys.exit(ExitCode.COMMAND_FAILED)

                check = shell_command(ha_ssh_command(ha_cli('core check')), capture_output=True, check=False)
                if check.returncode != 0:
                    self._roll_back(snapshot, old_secrets, restore_secrets=secrets_diff.changed)
                    printf(
                        '❌ `ha core check` rejected the config; the VM was restored to its previous state',
                        fg='red',
                        bold=True,
                    )
                    printf((check.stdout + check.stderr).strip(), indent=3)
                    sys.exit(ExitCode.COMMAND_FAILED)

            except HASyncError as e:
                printf(f'❌ {e}', fg='red', bold=True)
                sys.exit(ExitCode.COMMAND_FAILED)

        printf('✅ Pushed; `ha core check` passed', fg='bright_green')
        if args.restart:
            printf('💿 Restarting Home Assistant Core', fg='bright_cyan')
            restart = shell_command(ha_ssh_command(ha_cli('core restart')), capture_output=True, check=False)
            if restart.returncode != 0:
                printf(f'❌ Restart failed: {(restart.stdout + restart.stderr).strip()}', fg='red', bold=True)
                sys.exit(ExitCode.COMMAND_FAILED)
        else:
            printf(
                'Reload automations/scripts/scenes from Developer Tools, or re-run with --restart '
                '(configuration.yaml changes need a restart)',
                dim=True,
                indent=3,
            )

    @staticmethod
    def _roll_back(snapshot: Path, old_secrets: str | None, *, restore_secrets: bool) -> None:
        """
        Restore the VM's tracked files, and its ``secrets.yaml`` when the push rewrote it, to their pre-push state

        :param snapshot: directory holding the VM's config as fetched before the push
        :param old_secrets: the VM's ``secrets.yaml`` before the push, or None when it had none
        :param restore_secrets: whether the push touched ``secrets.yaml``
        :raises HASyncError: if the restore itself fails
        """
        try:
            apply_ha_changes(snapshot, diff_trees(HA_CONFIG_DIR, snapshot))
            if restore_secrets:
                if old_secrets is None:
                    delete_ha_files([HA_SECRETS_FILE])
                else:
                    write_ha_secrets(old_secrets)
        except HASyncError as e:
            raise HASyncError(f'Rollback failed, so the VM may hold a partial push: {e}') from e
