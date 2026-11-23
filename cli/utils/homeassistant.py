"""
Home Assistant config sync helpers for ``ha-pull`` and ``ha-push``
"""
from __future__ import annotations

import contextlib
import filecmp
import os
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
from collections.abc import Sequence
from pathlib import Path
from pathlib import PurePosixPath
from typing import TYPE_CHECKING
from typing import NamedTuple
from typing import cast

import yaml

from cli.infra.config import DOTFILES_DIR
from cli.infra.config import HA_CONFIG_DIR
from cli.infra.config import HA_HOST_ENVVAR
from cli.infra.config import HA_PORT_ENVVAR
from cli.infra.config import HA_USER_ENVVAR
from cli.infra.config import INVENTORY_FILE
from cli.infra.config import NAS_INVENTORY_HOST
from cli.infra.config import VAULT_PASSWORD
from cli.infra.config import ExitCode
from cli.utils.shell import shell_command
from cli.utils.styling import optstyle
from cli.utils.styling import printf
from cli.utils.uv import uv_command

if TYPE_CHECKING:
    from collections.abc import Iterable
    from typing import IO

__all__ = [
    'HA_HOST',
    'HA_PORT',
    'HA_REMOTE_CONFIG_DIR',
    'HA_SECRETS_FILE',
    'HA_SECRETS_TEMPLATE_NAME',
    'HA_SSH_CONNECT_TIMEOUT',
    'HA_SYNC_EXCLUDED_NAMES',
    'HA_SYNC_PATHS',
    'HA_USER',
    'HASyncError',
    'TreeDiff',
    'apply_ha_changes',
    'apply_tree_diff',
    'delete_ha_files',
    'diff_ha_secrets',
    'diff_trees',
    'fetch_ha_config',
    'fetch_ha_secrets',
    'ha_cli',
    'ha_config_has_local_changes',
    'ha_privileged',
    'ha_secrets_template',
    'ha_ssh_command',
    'list_ha_tree',
    'pack_ha_files',
    'print_tree_diff',
    'render_ha_secrets',
    'require_ha_reachable',
    'unpack_ha_stream',
    'upload_ha_files',
    'write_ha_secrets',
]


# Home Assistant config sync (`ha-pull` / `ha-push`)
# -------------------------------------------------------------------
# Directory holding Home Assistant's configuration inside the HAOS VM
HA_REMOTE_CONFIG_DIR: str = '/config'

# Top-level entries of the VM's config directory that are tracked in the repo (an allowlist: `.storage/`, the recorder
# database, logs, and `secrets.yaml` must never be synced)
HA_SYNC_PATHS: tuple[str, ...] = (
    'configuration.yaml',
    'automations.yaml',
    'scripts.yaml',
    'scenes.yaml',
    'blueprints',
    'themes',
    'packages',
)

# File and directory names skipped anywhere in a synced tree
HA_SYNC_EXCLUDED_NAMES: frozenset[str] = frozenset({'__pycache__', '.DS_Store'})

# `secrets.yaml` is outside HA_SYNC_PATHS because its values come from the Ansible vault: `ha-push` renders it from a
# template in the repo instead of copying a file
HA_SECRETS_FILE:          str = 'secrets.yaml'
HA_SECRETS_TEMPLATE_NAME: str = 'secrets.yaml.j2'

# Seconds ssh waits for the VM before giving up
HA_SSH_CONNECT_TIMEOUT: int = 5


# Home Assistant OS VM (SSH target of `ha-pull` / `ha-push`: the Advanced SSH & Terminal app inside the VM)
# -------------------------------------------------------------------
HA_HOST: str = os.getenv(HA_HOST_ENVVAR, 'homeassistant.local')
HA_USER: str = os.getenv(HA_USER_ENVVAR, 'connormason')
HA_PORT: str = os.getenv(HA_PORT_ENVVAR, '22')


# ==================================================================================================
# Home Assistant config sync helpers
#
# `ha-pull` and `ha-push` mirror the allowlisted part of the HAOS VM's /config (HA_SYNC_PATHS) to and from
# HA_CONFIG_DIR over SSH as a tar stream, so the VM needs nothing beyond its Advanced SSH & Terminal app
# ==================================================================================================


class HASyncError(RuntimeError):
    """
    A Home Assistant sync step failed (SSH, the tar stream, or a remote command)
    """
    pass


class TreeDiff(NamedTuple):
    """
    Files that differ between two trees, as POSIX paths relative to the tree root
    """
    added:    list[str]
    modified: list[str]
    removed:  list[str]

    @property
    def changed(self) -> bool:
        """
        Whether any file differs
        """
        return bool(self.added or self.modified or self.removed)


def list_ha_tree(root: Path) -> dict[str, Path]:
    """
    List the syncable files under a config tree

    Only entries named in ``HA_SYNC_PATHS`` are considered; symlinks, non-regular files, and names in
    ``HA_SYNC_EXCLUDED_NAMES`` are skipped

    :param root: tree root (a config directory)
    :return: mapping of POSIX path relative to ``root`` to the file's path
    """
    files: dict[str, Path] = {}

    for top in HA_SYNC_PATHS:
        entry = root / top
        if entry.is_symlink():
            continue

        if entry.is_file():
            files[top] = entry
        elif entry.is_dir():
            for path in sorted(entry.rglob('*')):
                rel = path.relative_to(root)
                if path.is_symlink() or not path.is_file() or HA_SYNC_EXCLUDED_NAMES.intersection(rel.parts):
                    continue
                files[rel.as_posix()] = path

    return files


def diff_trees(old: Path, new: Path) -> TreeDiff:
    """
    Compute the changes that turn the syncable files of ``old`` into those of ``new``

    :param old: tree the changes apply to
    :param new: tree holding the desired state
    :return: files to add (only in ``new``), modify (different content), and remove (only in ``old``), each sorted
    """
    old_files = list_ha_tree(old)
    new_files = list_ha_tree(new)

    return TreeDiff(
        added=sorted(new_files.keys() - old_files.keys()),
        modified=sorted(
            rel for rel in old_files.keys() & new_files.keys()
            if not filecmp.cmp(old_files[rel], new_files[rel], shallow=False)
        ),
        removed=sorted(old_files.keys() - new_files.keys()),
    )


def apply_tree_diff(src: Path, dest: Path, diff: TreeDiff) -> None:
    """
    Apply a diff to a local tree: copy added and modified files from ``src`` and delete removed ones

    :param src: tree holding the new content
    :param dest: tree to update
    :param diff: changes from :func:`diff_trees` (``old=dest``, ``new=src``)
    """
    for rel in [*diff.added, *diff.modified]:
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src / rel, target)

    for rel in diff.removed:
        (dest / rel).unlink(missing_ok=True)

        # Prune directories the removal emptied, but never the tracked top-level entry itself
        parent = (dest / rel).parent
        while dest not in (parent, parent.parent) and not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent


def pack_ha_files(root: Path, relpaths: Iterable[str], stream: IO[bytes]) -> None:
    """
    Write files as a tar stream with ownership and modes normalized for Home Assistant (root-owned, 0644 / 0755)

    :param root: directory the paths are relative to
    :param relpaths: POSIX paths of regular files under ``root``
    :param stream: writable binary stream (the stdin of the remote ``tar -x``)
    """
    with tarfile.open(fileobj=stream, mode='w|') as tar:
        for rel in relpaths:
            path = root / rel

            info       = tar.gettarinfo(str(path), arcname=rel)
            info.uid   = info.gid   = 0
            info.uname = info.gname = 'root'
            info.mode  = 0o755 if info.mode & 0o111 else 0o644

            with path.open('rb') as handle:
                tar.addfile(info, handle)


def unpack_ha_stream(stream: IO[bytes], dest: Path) -> None:
    """
    Extract regular files from a tar stream into ``dest``, refusing paths that would escape it

    Directories, links, and special files are skipped, and extracted files get mode 0644 regardless of the archive

    :param stream: readable binary stream (the stdout of the remote ``tar -c``)
    :param dest: directory to extract into
    :raises HASyncError: if a member's path is absolute or contains ``..``
    """
    with tarfile.open(fileobj=stream, mode='r|') as tar:
        for member in tar:
            name = PurePosixPath(member.name)
            if name.is_absolute() or ('..' in name.parts):
                raise HASyncError(f'Refusing unsafe path from Home Assistant: {member.name!r}')
            if not member.isreg() or HA_SYNC_EXCLUDED_NAMES.intersection(name.parts):
                continue

            source = tar.extractfile(member)
            if source is None:
                continue

            target = dest.joinpath(*name.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with source, target.open('wb') as out:
                shutil.copyfileobj(source, out)
            target.chmod(0o644)


def ha_ssh_command(remote_command: str) -> list[str]:
    """
    Build the ssh command that runs a POSIX shell snippet on the Home Assistant VM

    :param remote_command: snippet to run under ``sh -c`` on the VM
    :return: the full ssh argument list (key auth only, so it never prompts)
    """
    return [
        'ssh',
        '-o', 'BatchMode=yes',
        '-o', f'ConnectTimeout={HA_SSH_CONNECT_TIMEOUT}',
        '-p', HA_PORT,
        f'{HA_USER}@{HA_HOST}',
        f'sh -c {shlex.quote(remote_command)}',
    ]


def ha_privileged(remote_command: str) -> str:
    """
    Prefix a remote command with non-interactive sudo unless the SSH login is already root

    The Advanced SSH & Terminal app logs in as an unprivileged user, while ``/config`` and its files are root-owned, so
    writing there needs root

    :param remote_command: command to run on the VM
    :return: ``remote_command``, escalated when ``HA_USER`` is not ``root``
    """
    return remote_command if HA_USER == 'root' else f'sudo -n {remote_command}'


def ha_cli(subcommand: str) -> str:
    """
    Build the remote command that runs the ``ha`` CLI with its Supervisor token

    The token is exported by the VM's ``/etc/profile.d/homeassistant.sh``, which a bare ``ssh host cmd`` never sources,
    so the CLI runs in a login shell

    :param subcommand: arguments to ``ha`` (e.g. ``core check``)
    :return: the command to hand to :func:`ha_ssh_command`
    """
    return f'sh -lc {shlex.quote(f"ha {subcommand}")}'


def require_ha_reachable() -> None:
    """
    Exit with a remedy unless the Home Assistant VM answers a non-interactive SSH probe

    :raises SystemExit: if the probe fails
    """
    result = shell_command(ha_ssh_command('true'), capture_output=True, check=False)
    if result.returncode != 0:
        printf(f'❌ Cannot reach Home Assistant at {HA_USER}@{HA_HOST}:{HA_PORT} over SSH', fg='red', bold=True)
        printf("Is the Advanced SSH & Terminal app running, with this machine's public key in its config?", indent=3)
        printf(
            f'Override the target with {optstyle(HA_HOST_ENVVAR)}, {optstyle(HA_USER_ENVVAR)} and '
            f'{optstyle(HA_PORT_ENVVAR)}; off the LAN, add a ProxyJump through the NAS in ~/.ssh/config',
            indent=3,
        )
        printf(f'ssh said: {result.stderr.strip()}', indent=3, dim=True)
        sys.exit(ExitCode.COMMAND_FAILED)


# TODO: add as classmethod constructor to HASyncError
def _ssh_failure(what: str, stderr_file: IO[bytes], returncode: int) -> HASyncError:
    """
    Build the error for a failed remote step from the stderr captured in a temp file

    :param what: description of the step that failed
    :param stderr_file: file holding the step's stderr
    :param returncode: exit status of the ssh process
    :return: the error to raise
    """
    stderr_file.seek(0)
    detail = stderr_file.read().decode(errors='replace').strip() or 'no error output'
    return HASyncError(f'{what} failed (exit {returncode}): {detail}')


def fetch_ha_config(dest: Path) -> None:
    """
    Download the allowlisted config files from the VM into ``dest``

    :param dest: empty local directory to extract into
    :raises HASyncError: if ssh or the remote tar fails, or the stream is malformed
    """
    paths  = ' '.join(shlex.quote(p) for p in HA_SYNC_PATHS)
    remote = (
        f'cd {shlex.quote(HA_REMOTE_CONFIG_DIR)} || exit 1; set --; '
        f'for p in {paths}; do if [ -e "$p" ]; then set -- "$@" "$p"; fi; done; '
        '[ "$#" -gt 0 ] || exit 3; '
        'exec tar -cf - --exclude=__pycache__ "$@"'
    )

    stream_error: Exception | None = None
    with tempfile.TemporaryFile() as stderr_file:
        with subprocess.Popen(ha_ssh_command(remote), stdout=subprocess.PIPE, stderr=stderr_file) as proc:
            stdout = cast('IO[bytes]', proc.stdout)
            try:
                unpack_ha_stream(stdout, dest)
                stdout.read()                               # drain the tar end-of-archive padding
            except tarfile.TarError as e:
                stream_error = e

        if (proc.returncode != 0) or (stream_error is not None):
            raise _ssh_failure('Downloading the Home Assistant config', stderr_file, proc.returncode) from stream_error


def upload_ha_files(root: Path, relpaths: Sequence[str]) -> None:
    """
    Upload files from ``root`` into the VM's config directory

    :param root: local directory the paths are relative to
    :param relpaths: POSIX paths of the files to upload
    :raises HASyncError: if ssh or the remote tar fails
    """
    if not relpaths:
        return

    remote = f'cd {shlex.quote(HA_REMOTE_CONFIG_DIR)} && {ha_privileged("tar -xf -")}'
    with tempfile.TemporaryFile() as stderr_file:
        with subprocess.Popen(ha_ssh_command(remote), stdin=subprocess.PIPE, stderr=stderr_file) as proc:
            stdin = cast('IO[bytes]', proc.stdin)
            try:
                pack_ha_files(root, relpaths, stdin)
            except BrokenPipeError:
                pass                                        # the remote end died; its exit status says why
            finally:
                with contextlib.suppress(BrokenPipeError):
                    stdin.close()

        if proc.returncode != 0:
            raise _ssh_failure('Uploading to the Home Assistant config', stderr_file, proc.returncode)


def delete_ha_files(relpaths: Sequence[str]) -> None:
    """
    Delete files from the VM's config directory

    :param relpaths: POSIX paths relative to the config directory
    :raises HASyncError: if the remote ``rm`` fails
    """
    if not relpaths:
        return

    quoted = ' '.join(shlex.quote(p) for p in relpaths)
    result = shell_command(
        ha_ssh_command(f'cd {shlex.quote(HA_REMOTE_CONFIG_DIR)} && {ha_privileged(f"rm -f -- {quoted}")}'),
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise HASyncError(f'Deleting from the Home Assistant config failed: {result.stderr.strip()}')


def apply_ha_changes(src: Path, diff: TreeDiff) -> None:
    """
    Apply a diff to the VM's config: upload added and modified files from ``src`` and delete removed ones

    :param src: local tree holding the new content
    :param diff: changes from :func:`diff_trees` (``old`` = the VM's config, ``new`` = ``src``)
    :raises HASyncError: if the upload or the deletion fails
    """
    upload_ha_files(src, [*diff.added, *diff.modified])
    delete_ha_files(diff.removed)


def print_tree_diff(diff: TreeDiff, *, verbs: tuple[str, str, str], indent: int = 3) -> None:
    """
    Print a diff, one styled line per file, followed by a summary

    :param diff: the changes to print
    :param verbs: past-tense summary words for (added, modified, removed)
    :param indent: number of leading spaces
    """
    for marker, color, paths in (
        ('+', 'bright_green',  diff.added),
        ('~', 'bright_yellow', diff.modified),
        ('-', 'bright_red',    diff.removed)
    ):
        for rel in paths:
            printf(f'{marker} {rel}', fg=color, indent=indent)

    printf(
        f'{len(diff.added)} {verbs[0]}, {len(diff.modified)} {verbs[1]}, {len(diff.removed)} {verbs[2]}',
        dim=True,
        indent=indent,
    )


def ha_config_has_local_changes() -> bool:
    """
    Whether the tracked Home Assistant files in the repo have uncommitted changes (including untracked ones)
    """
    base   = HA_CONFIG_DIR.relative_to(DOTFILES_DIR)
    result = shell_command(
        ['git', 'status', '--porcelain', '--', *(str(base / p) for p in HA_SYNC_PATHS)],
        capture_output=True,
        check=False,
        cwd=DOTFILES_DIR,
    )
    return (result.returncode == 0) and bool(result.stdout.strip())


# ==================================================================================================
# Home Assistant secrets (rendered from the Ansible vault by `ha-push`)
# ==================================================================================================


def ha_secrets_template() -> Path | None:
    """
    Locate the template that ``ha-push`` renders into the VM's ``secrets.yaml``

    :return: the template path, or None when the repo has none (the VM's ``secrets.yaml`` is then left alone)
    """
    template = HA_CONFIG_DIR / HA_SECRETS_TEMPLATE_NAME
    return template if template.is_file() else None


def render_ha_secrets(template: Path) -> str:
    """
    Render the secrets template with the variables of the inventory's NAS host, vault included

    Ansible does the rendering (an ad-hoc ``template`` run on the controller), so vault decryption and nested
    variables resolve as they do for the NAS services' ``env.j2`` files. Neither the rendered text nor the variables
    are printed

    :param template: Jinja2 template to render
    :raises HASyncError: if the inventory, the vault, or the template cannot be resolved
    :return: the rendered ``secrets.yaml`` content
    """
    with tempfile.TemporaryDirectory() as tmp:
        rendered = Path(tmp) / HA_SECRETS_FILE
        result   = shell_command(
            uv_command(
                'run', 'ansible', NAS_INVENTORY_HOST,
                '-i',                    str(INVENTORY_FILE),
                '--vault-password-file', str(VAULT_PASSWORD),
                '-e',                    'ansible_connection=local ansible_python_interpreter=auto_silent',
                '-m',                    'ansible.builtin.template',
                '-a',                    f'src={template} dest={rendered} mode=0600',
            ),
            capture_output=True,
            check=False,
            cwd=DOTFILES_DIR,
        )
        if result.returncode != 0:
            detail = (result.stdout + result.stderr).strip() or 'no output'
            raise HASyncError(
                f'Rendering {template.name} from the "{NAS_INVENTORY_HOST}" inventory host failed '
                f'(is the inventory cloned, the vault password present, and every variable defined?): {detail}',
            )
        return rendered.read_text(encoding='utf-8')


def _secret_values(text: str | None) -> dict[str, object]:
    """
    Parse a ``secrets.yaml`` into its top-level mapping

    :param text: file content, or None when the file does not exist
    :return: the mapping, empty when the text is absent, not valid YAML, or not a mapping
    """
    try:
        data = yaml.safe_load(text) if text else None
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def diff_ha_secrets(old: str | None, new: str) -> TreeDiff:
    """
    Compare two ``secrets.yaml`` contents by key, so the result is safe to print (it holds names, never values)

    Formatting and comments are ignored: only a key whose parsed value differs counts as modified

    :param old: the VM's current content, or None when it has no ``secrets.yaml``
    :param new: the rendered content
    :return: keys that are ``added``, ``modified``, or ``removed`` going from ``old`` to ``new``
    """
    before = _secret_values(old)
    after  = _secret_values(new)
    return TreeDiff(
        added=sorted(after.keys() - before.keys()),
        modified=sorted(k for k in before.keys() & after.keys() if before[k] != after[k]),
        removed=sorted(before.keys() - after.keys()),
    )


def fetch_ha_secrets() -> str | None:
    """
    Read the VM's ``secrets.yaml``

    :raises HASyncError: if ssh or the remote read fails
    :return: the file content, or None when the VM has no ``secrets.yaml``
    """
    remote = (
        f'cd {shlex.quote(HA_REMOTE_CONFIG_DIR)} || exit 1; '
        f'[ -e {HA_SECRETS_FILE} ] || exit 3; '
        f'{ha_privileged(f"cat {HA_SECRETS_FILE}")}'
    )
    result = shell_command(ha_ssh_command(remote), capture_output=True, check=False)
    if result.returncode == 3:
        return None
    if result.returncode != 0:
        raise HASyncError(f'Reading secrets.yaml from the Home Assistant VM failed: {result.stderr.strip()}')
    return result.stdout


def write_ha_secrets(content: str) -> None:
    """
    Write the VM's ``secrets.yaml`` readable by root only

    :param content: complete file content
    :raises HASyncError: if ssh or the remote write fails
    """
    remote = (
        f'cd {shlex.quote(HA_REMOTE_CONFIG_DIR)} && umask 077 && '
        f'{ha_privileged(f"tee {HA_SECRETS_FILE} >/dev/null")} && '
        f'{ha_privileged(f"chmod 600 {HA_SECRETS_FILE}")}'
    )
    result = shell_command(ha_ssh_command(remote), input=content, capture_output=True, check=False)
    if result.returncode != 0:
        raise HASyncError(f'Writing secrets.yaml to the Home Assistant VM failed: {result.stderr.strip()}')
