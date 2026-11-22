"""
Individual checks run by the ``doctor`` command
"""
from __future__ import annotations

import dataclasses
import re
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from cli.infra.config import DOTFILES_DIR
from cli.infra.config import GIT_HOOK_TYPES
from cli.infra.config import INSTALLER_SCRIPTS
from cli.infra.config import MIN_GIT_VERSION
from cli.infra.config import MIN_PYTHON
from cli.infra.config import PREK_SHIM_MARKER
from cli.infra.config import RENDER_SCRIPT
from cli.infra.config import REQUIRED_TOOLS
from cli.infra.config import SCRIPT_PATH
from cli.infra.config import STOW_SCRIPT
from cli.infra.config import VENV_DIR
from cli.utils.formatting import folduser
from cli.utils.shell import capture_command
from cli.utils.shell import first_output_line
from cli.utils.uv import check_uv
from cli.utils.venv import VenvStatus
from cli.utils.venv import get_external_active_venv
from cli.utils.venv import validate_venv

if TYPE_CHECKING:
    import subprocess

__all__ = [
    'DoctorCheck',
    'check_brewfiles',
    'check_git_version',
    'check_hooks',
    'check_layers',
    'check_links',
    'check_python_tool',
    'check_render',
    'check_tools',
    'check_uv_tool',
    'check_venv',
    'doctor_checks',
]


# ==================================================================================================
# `doctor` command checks
# ==================================================================================================


@dataclasses.dataclass(frozen=True)
class DoctorCheck:
    """
    Result of one doctor check

    :param name: short check name
    :param ok: whether the check passed
    :param detail: one-line explanation
    :param fix: command that repairs the problem, if one exists
    """
    name:   str
    ok:     bool
    detail: str
    fix:    list[str] | None = None


def _probe_layers() -> subprocess.CompletedProcess[str]:
    """
    Ask bootstrap/lib.sh for the layer directories (base first), one per stdout line
    """
    # DOTFILES_REPO is pinned to this checkout so an inherited value from another one cannot redirect the base layer.
    # Anything lib.sh or a layer env.sh prints while loading goes to stderr so it cannot be counted as a layer.
    script = 'export DOTFILES_REPO="$1"; source "$1/bootstrap/lib.sh" >&2 && dotfiles_layers'
    return capture_command(['bash', '-c', script, 'doctor', str(DOTFILES_DIR)])


def check_layers() -> DoctorCheck:
    """
    Check that every registered overlay exists
    """
    result = _probe_layers()
    if result.returncode != 0:
        return DoctorCheck(name='layers', ok=False, detail=first_output_line(result.stderr, 'overlay registry error'))

    count = len([line for line in result.stdout.splitlines() if line])
    return DoctorCheck(name='layers', ok=True, detail=f'{count} layer(s): base + {count - 1} overlay(s)')


def check_python_tool() -> DoctorCheck:
    """
    Check that the running python satisfies :data:`MIN_PYTHON` (if one is set)
    """
    v      = sys.version_info
    v_str  = f'{v.major}.{v.minor}.{v.micro}'
    detail = f'{v_str} @ {folduser(sys.executable)}'
    if (MIN_PYTHON is not None) and (v < MIN_PYTHON):
        return DoctorCheck(name='python', ok=False, detail=f'{detail} (need >= {MIN_PYTHON[0]}.{MIN_PYTHON[1]})')
    return DoctorCheck(name='python', ok=True, detail=detail)


def check_uv_tool() -> DoctorCheck:
    """
    Check that ``uv`` is installed, offering the bundled installer as the fix
    """
    if uv_info := check_uv():
        return DoctorCheck(name='uv', ok=True, detail=f'{uv_info["version"]} @ {folduser(uv_info["executable"])}')
    return DoctorCheck(
        name='uv',
        ok=False,
        detail='not installed',
        fix=[sys.executable, str(INSTALLER_SCRIPTS['uv']), '--ensure'],
    )


def check_venv() -> DoctorCheck:
    """
    Check that the project ``.venv`` (or the externally active venv) exists and is in sync with ``uv.lock``

    A venv that merely is not activated in this shell is healthy; the fix for a missing or stale one is
    ``run.py install``.
    """
    target = get_external_active_venv() or VENV_DIR
    health = validate_venv(target)
    detail = f'Python {health.python_version or "?"}'
    if health.package_count is not None:
        detail += f', {health.package_count} packages'

    if health.status in (VenvStatus.HEALTHY, VenvStatus.NOT_ACTIVATED):
        return DoctorCheck(name='venv', ok=True, detail=f'{detail}, {health.message}')

    fix = None if (target != VENV_DIR) else [sys.executable, str(SCRIPT_PATH), 'install']
    return DoctorCheck(name='venv', ok=False, detail=health.message, fix=fix)


def check_hooks() -> DoctorCheck:
    """
    Check that prek's git hook shims are installed for every type in :data:`GIT_HOOK_TYPES`

    The ``pre-push`` shim runs the public-repo leak guard, so a checkout without it pushes unscanned.
    """
    result = capture_command(['git', 'rev-parse', '--git-path', 'hooks'])
    if result.returncode != 0:
        return DoctorCheck(name='hooks', ok=False, detail=first_output_line(result.stderr, 'not a git checkout'))

    # Relative to the repo root in a plain checkout; the absolute common-dir path inside a linked worktree
    hooks_dir = DOTFILES_DIR / result.stdout.strip()

    missing: list[str] = []
    for hook_type in GIT_HOOK_TYPES:
        try:
            installed = PREK_SHIM_MARKER in (hooks_dir / hook_type).read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError):
            installed = False
        if not installed:
            missing.append(hook_type)

    if not missing:
        return DoctorCheck(name='hooks', ok=True, detail=f'{len(GIT_HOOK_TYPES)} prek hook shims installed')

    detail = f'missing prek shims: {", ".join(missing)}'
    if shutil.which('prek') is None:
        return DoctorCheck(name='hooks', ok=False, detail=f'{detail} (prek not on PATH)')

    return DoctorCheck(name='hooks', ok=False, detail=detail, fix=['prek', 'install'])


def check_brewfiles() -> DoctorCheck:
    """
    Check that every layer's Brewfile is satisfied: everything it declares is installed (``brew bundle check``)

    Homebrew has no lockfile, so ``brew bundle check`` is the reproducibility signal. ``--no-upgrade`` keeps merely
    outdated entries from counting as drift (a plain check also flags those, and shells out to ``mas outdated``), and
    the fix installs the missing entries without upgrading anything. Bootstrap stage 50-brew runs a similar probe
    without ``--no-upgrade`` and treats a mismatch as non-fatal.
    """
    if shutil.which('brew') is None:
        return DoctorCheck(name='brewfile', ok=False, detail='brew not found')

    layers = _probe_layers()
    if layers.returncode != 0:
        return DoctorCheck(name='brewfile', ok=False, detail='cannot enumerate layers (see the layers check)')

    brewfiles: list[Path] = [
        brewfile for line in layers.stdout.splitlines()
        if line and (brewfile := Path(line) / 'bootstrap' / 'Brewfile').is_file()
    ]
    if not brewfiles:
        return DoctorCheck(name='brewfile', ok=True, detail='no Brewfiles declared')

    drifted: list[Path] = [
        brewfile for brewfile in brewfiles
        if capture_command([
            'env', 'HOMEBREW_NO_AUTO_UPDATE=1',
            'brew', 'bundle', 'check', '--no-upgrade', '--file', str(brewfile),
        ]).returncode != 0
    ]
    if not drifted:
        return DoctorCheck(name='brewfile', ok=True, detail=f'{len(brewfiles)} Brewfile(s) satisfied')

    install = 'for brewfile in "$@"; do brew bundle --no-upgrade --file "$brewfile" || exit 1; done'
    return DoctorCheck(
        name='brewfile',
        ok=False,
        detail=f'unsatisfied: {", ".join(folduser(brewfile) for brewfile in drifted)}',
        fix=['bash', '-c', install, 'doctor', *(str(brewfile) for brewfile in drifted)],
    )


def check_links() -> DoctorCheck:
    """
    Check that stowing would change nothing
    """
    result = capture_command(['bash', str(STOW_SCRIPT), '-n'])
    if (
        (result.returncode == 0) and
        (('stow: no changes' in result.stdout) or ('stow: no packages found' in result.stdout))
    ):
        return DoctorCheck(name='links', ok=True, detail='all packages linked')

    fix: list[str] = ['bash', str(STOW_SCRIPT), '--backup-conflicts']
    if result.returncode != 0:
        return DoctorCheck(
            name='links',
            ok=False,
            detail=first_output_line(result.stderr or result.stdout, 'stow simulation failed'),
            fix=fix,
        )

    summary = next((line for line in result.stdout.splitlines() if re.match(r'stow: \d+ added', line)), '')
    return DoctorCheck(name='links', ok=False, detail=summary or 'stow reports pending changes', fix=fix)


def check_render() -> DoctorCheck:
    """
    Check that rendered settings files match their fragments
    """
    result = capture_command([sys.executable, str(RENDER_SCRIPT), '--check'])
    if result.returncode == 0:
        return DoctorCheck(name='render', ok=True, detail='rendered settings in sync')

    if result.returncode == 1:
        return DoctorCheck(
            name='render',
            ok=False,
            detail='rendered settings out of sync (see: run.py render --diff)',
            fix=[sys.executable, str(RENDER_SCRIPT)],
        )

    # Exit 2 (or anything else): bad fragment/registry or I/O error, which re-rendering cannot repair
    return DoctorCheck(
        name='render',
        ok=False,
        detail=first_output_line(result.stderr, f'render failed (exit {result.returncode})'),
    )


def check_git_version() -> DoctorCheck:
    """
    Check that git supports ``includeIf "hasconfig:remote.*.url:..."`` (git >= 2.36)
    """
    result = capture_command(['git', '--version'])
    match  = re.search(r'(\d+)\.(\d+)', result.stdout)
    if match is None:
        return DoctorCheck(name='git', ok=False, detail='could not determine git version')

    version = (int(match.group(1)), int(match.group(2)))
    want    = '.'.join(map(str, MIN_GIT_VERSION))
    return DoctorCheck(
        name='git',
        ok=version >= MIN_GIT_VERSION,
        detail=f'git {version[0]}.{version[1]} (need >= {want} for per-remote identity)',
    )


def check_tools() -> DoctorCheck:
    """
    Check that required command-line tools are on PATH
    """
    if missing := [tool for tool in REQUIRED_TOOLS if shutil.which(tool) is None]:
        return DoctorCheck(name='tools', ok=False, detail=f'missing: {", ".join(missing)}')
    return DoctorCheck(name='tools', ok=True, detail=', '.join(REQUIRED_TOOLS))


def doctor_checks() -> list[DoctorCheck]:
    """
    Run every doctor check (tools and layers first; the rest depend on them, and the slow Brewfile probe runs last)
    """
    first = [check_tools(), check_layers()]
    if not all(c.ok for c in first):
        return first

    return [
        *first,
        check_python_tool(),
        check_uv_tool(),
        check_git_version(),
        check_hooks(),
        check_venv(),
        check_links(),
        check_render(),
        check_brewfiles(),
    ]
