#!/usr/bin/env python3
"""
Render JSON settings files from per-layer fragments (base repo first, then registered overlays).

Each layer may provide ``render/<target>.json``. Fragments deep-merge in layer order into a real file at the target's
path. A drift guard refuses to overwrite edits made in the app since the last render.
"""
# /// script
# requires-python = ">= 3.9"
# dependencies = []
# ///
from __future__ import annotations

import argparse
import difflib
import functools
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

# ==========================
# Constants/defaults/globals
# ==========================


VERBOSE:       bool = False
UNMANAGED_KEY: str  = '$unmanaged'
DEFAULT_REPO:  Path = Path(__file__).resolve().parents[2]

DEFAULT_FILE_MODE:  int = 0o644
DEFAULT_STATE_MODE: int = 0o600
BACKUP_FILE_MODE:   int = 0o600
BACKUP_DIR_MODE:    int = 0o700

ANSI_ESCAPE = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')

TARGETS: dict[str, str] = {
    'claude': '~/.claude/settings.json',
    'vscode': '~/Library/Application Support/Code/User/settings.json',
}


# ===============
# Types/protocols
# ===============


class RenderError(Exception):
    """
    Configuration error: bad fragment, bad layer registry, or unknown target.
    """


class Prepared(NamedTuple):
    """
    A target whose fragments have been found and composed successfully.
    """
    target:    str
    managed:   dict[str, object]
    unmanaged: list[str]


# ==================
# Formatting/logging
# ==================


def info(message: str) -> None:
    """
    Print an informational line to stdout.

    :param message: text to print
    """
    print(f'render: {message}')


def warn(message: str) -> None:
    """
    Print a warning line to stderr.

    :param message: text to print
    """
    print(f'render: WARNING: {message}', file=sys.stderr)


def error(message: str) -> None:
    """
    Print an error line to stderr.

    :param message: text to print
    """
    print(f'render: ERROR: {message}', file=sys.stderr)


# =================
# Core script logic
# =================


def canonical(value: object) -> str:
    """
    Canonical JSON text used for equality and de-duplication.

    :param value: JSON-compatible value
    :return: compact, key-sorted JSON text
    """
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def dumps(data: object) -> str:
    """
    Deterministic output format for rendered files and state.

    :param data: JSON-compatible value
    :return: key-sorted, 2-space-indented JSON text with a trailing newline
    """
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + '\n'


def _drop_nulls(value: object) -> object:
    """
    Remove null-valued keys recursively (a null in a later layer means "delete").

    :param value: JSON-compatible value
    :return: value without null-valued object keys
    """
    if isinstance(value, dict):
        return {k: _drop_nulls(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_drop_nulls(v) for v in value]
    return value


def merge(base: object, overlay: object) -> object:
    """
    Merge a later layer's value over an earlier one.

    Objects deep-merge, arrays concatenate with order-preserving de-duplication, scalars are replaced, and a null
    object value deletes the key.

    :param base: earlier layer's value
    :param overlay: later layer's value
    :return: merged value
    """
    if isinstance(base, dict) and isinstance(overlay, dict):
        merged = dict(base)
        for key, value in overlay.items():
            if value is None:
                merged.pop(key, None)
            elif key in merged:
                merged[key] = merge(merged[key], value)
            else:
                merged[key] = _drop_nulls(value)
        return merged
    if isinstance(base, list) and isinstance(overlay, list):
        combined = list(base)
        seen     = {canonical(item) for item in combined}
        for item in overlay:
            cleaned = _drop_nulls(item)
            key     = canonical(cleaned)
            if key not in seen:
                combined.append(cleaned)
                seen.add(key)
        return combined
    return _drop_nulls(overlay)


def layers(repo: Path) -> list[Path]:
    """
    Resolve layer roots via ``bootstrap/lib.sh`` so shell and Python agree on one registry.

    Anything lib.sh or a layer's ``env.sh`` prints while being sourced is routed to stderr so it cannot be mistaken for
    a layer root.

    :param repo: base repository root
    :raises RenderError: if bash cannot run, the registry names a missing overlay, lib.sh fails, or a non-absolute
        layer path is produced
    :return: layer roots, base first
    """
    try:
        result = subprocess.run(
            ['bash', '-c', 'source "$1/bootstrap/lib.sh" >&2 && dotfiles_layers', '_', str(repo)],
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, 'DOTFILES_REPO': str(repo)},
        )
    except OSError as exc:
        raise RenderError(f'cannot run bash to resolve layers: {exc!s}') from exc
    if result.returncode != 0:
        raise RenderError(ANSI_ESCAPE.sub('', result.stderr).strip() or 'dotfiles_layers failed')
    roots = []
    for line in result.stdout.splitlines():
        if not line:
            continue
        root = Path(line)
        if not root.is_absolute():
            raise RenderError(f'dotfiles_layers produced a non-absolute layer path: {ANSI_ESCAPE.sub("", line)!r}')
        roots.append(root)
    return roots


def compose(fragments: Sequence[Path]) -> tuple[dict[str, object], list[str]]:
    """
    Merge fragments in order and split out the unmanaged-key list.

    A key that a fragment sets but that is also listed as unmanaged is dropped from the managed settings (the app or
    installer owns it) with a warning.

    :param fragments: fragment files, base first
    :raises RenderError: on unreadable/invalid JSON, a non-object fragment, or a malformed ``$unmanaged``
    :return: (managed settings, unmanaged top-level key names)
    """
    merged:    object    = {}
    unmanaged: list[str] = []
    for fragment in fragments:
        try:
            data = json.loads(fragment.read_text(encoding='utf-8'))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RenderError(f'{fragment}: {exc!s}') from exc
        if not isinstance(data, dict):
            raise RenderError(f'{fragment}: top level must be an object')
        keys = data.pop(UNMANAGED_KEY, [])
        if not isinstance(keys, list) or not all(isinstance(k, str) for k in keys):
            raise RenderError(f'{fragment}: {UNMANAGED_KEY} must be a list of key names')
        unmanaged.extend(k for k in keys if k not in unmanaged)
        merged = merge(merged, data)
    if not isinstance(merged, dict):
        raise RenderError('merged settings must be an object')
    overlap = [k for k in unmanaged if k in merged]
    if overlap:
        warn(f'fragment value(s) ignored for key(s) listed in {UNMANAGED_KEY}: {", ".join(overlap)}')
    return {k: v for k, v in merged.items() if k not in unmanaged}, unmanaged


def prepare(target: str, roots: Sequence[Path]) -> Prepared | None:
    """
    Find and compose the fragments of one target.

    :param target: target id from :data:`TARGETS`
    :param roots: layer roots, base first
    :raises RenderError: on invalid fragments
    :return: the composed target, or ``None`` if no layer provides a fragment
    """
    fragments = [root / 'render' / f'{target}.json' for root in roots]
    fragments = [f for f in fragments if f.is_file()]
    if not fragments:
        if VERBOSE:
            info(f'{target}: no fragments in any layer; skipped')
        return None
    managed, unmanaged = compose(fragments)
    return Prepared(target, managed, unmanaged)


def state_path(target: str) -> Path:
    """
    Where the last managed render of a target is stored.

    :param target: target id
    :return: state file path
    """
    state_home = os.environ.get('XDG_STATE_HOME') or str(Path.home() / '.local' / 'state')
    return Path(state_home) / 'dotfiles' / 'render' / f'{target}.json'


def read_state(state: Path) -> dict[str, object] | None:
    """
    Load the last managed render, treating a missing or unusable state file as absent.

    :param state: state file path
    :return: the stored managed settings, or ``None`` if absent or unusable (a warning is printed for the latter)
    """
    if not state.is_file():
        return None
    try:
        data = json.loads(state.read_text(encoding='utf-8'))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        warn(f'ignoring unusable state file {state} ({exc!s}); treating it as absent')
        return None
    if not isinstance(data, dict):
        warn(f'ignoring unusable state file {state} (not a JSON object); treating it as absent')
        return None
    return data


def atomic_write(path: Path, text: str, default_mode: int) -> None:
    """
    Write text to path through a temp file in the same directory and ``os.replace``.

    An existing file's mode is preserved; for a symlink the mode of its target is used. A symlink itself is replaced,
    never written through.

    :param path: destination path
    :param text: file content
    :param default_mode: mode used when no existing file supplies one
    """
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except OSError:
        mode = default_mode
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f'.{path.name}.', suffix='.tmp')
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        tmp.chmod(mode)
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def _diff(old: str, new: str, old_label: str, new_label: str) -> str:
    """
    Unified diff of two texts.

    :param old: original text
    :param new: new text
    :param old_label: label for the original
    :param new_label: label for the new text
    :return: diff text (empty when equal)
    """
    return ''.join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), old_label, new_label))


def _backup(dest: Path) -> Path:
    """
    Copy the live file's content to ~/.dotfiles-backup/<timestamp>/<path relative to HOME>.

    Directories are created 0700 and the backup file 0600.

    :param dest: live target path
    :return: backup path
    """
    home = Path.home()
    try:
        relative = dest.relative_to(home)
    except ValueError:
        relative = Path(dest.name)
    backup = home / '.dotfiles-backup' / time.strftime('%Y%m%d-%H%M%S') / relative
    current = home
    for part in backup.parent.relative_to(home).parts:
        current = current / part
        current.mkdir(mode=BACKUP_DIR_MODE, exist_ok=True)
    fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, BACKUP_FILE_MODE)
    with os.fdopen(fd, 'wb') as handle:
        handle.write(dest.read_bytes())
    backup.chmod(BACKUP_FILE_MODE)
    return backup


def render_target(prepared: Prepared, *, mode: str, force: bool) -> int:
    """
    Render, check, or diff one composed target.

    :param prepared: composed target
    :param mode: ``'render'``, ``'check'``, or ``'diff'``
    :param force: overwrite despite drift (after backing up)
    :raises OSError: on I/O failures reading or writing the target, its state, or backups
    :return: 0 ok / in sync, 1 drift refused / out of sync
    """
    target, managed, unmanaged = prepared
    new_text = dumps(managed)
    dest     = Path(TARGETS[target]).expanduser()
    state    = state_path(target)
    last     = read_state(state)

    live:         dict[str, object] | None = None
    live_problem: str | None               = None
    if dest.exists():
        try:
            parsed = json.loads(dest.read_text(encoding='utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError):
            live_problem = 'is not valid JSON'
        else:
            if isinstance(parsed, dict):
                live = parsed
            else:
                live_problem = 'is not a JSON object'
    live_managed = {k: v for k, v in live.items() if k not in unmanaged} if live is not None else None
    live_managed_text = dumps(live_managed) if live_managed is not None else None

    if mode == 'diff':
        print(_diff(live_managed_text or '', new_text, f'{dest} (live)', f'{dest} (rendered)'), end='')
        return 0
    if mode == 'check':
        if live_managed_text == new_text:
            return 0
        error(f'{target}: {dest} is not in sync with its fragments (run: run.py render)')
        return 1

    current = live_managed_text == new_text
    in_sync = False
    if last is not None and live_managed is not None:
        in_sync = canonical(last) == canonical(live_managed)
    drifted = dest.exists() and not current and not in_sync
    if drifted and not force:
        reason = live_problem or 'was edited since the last render'
        error(f'{target}: {dest} {reason}; move the change into a render fragment, or re-run with --force')
        if live_managed_text is not None:
            old_text = dumps(last) if last is not None else ''
            print(_diff(old_text, live_managed_text, 'last render', f'{dest} (live)'), end='', file=sys.stderr)
        return 1

    output = dict(managed)
    if live is not None:
        output.update({k: live[k] for k in unmanaged if k in live})
    output_text = dumps(output)

    if dest.exists() and force and drifted:
        info(f'{target}: backed up live file to {_backup(dest)}')
    if dest.is_symlink():
        info(f'{target}: replacing symlink {dest} -> {dest.readlink()} with a regular file')
    if dest.is_symlink() or not dest.exists() or dest.read_text(encoding='utf-8') != output_text:
        atomic_write(dest, output_text, DEFAULT_FILE_MODE)
        info(f'{target}: rendered {dest}')
    elif VERBOSE:
        info(f'{target}: already current')
    atomic_write(state, new_text, DEFAULT_STATE_MODE)
    return 0


# ======================
# Command-line arguments
# ======================


class Args(argparse.Namespace):
    """
    :class:`argparse.Namespace` annotated with args supported by this script.
    """
    targets: Sequence[str]
    diff:    bool
    check:   bool
    force:   bool
    repo:    str
    verbose: bool


def parse_args(argv: Sequence[str] | None = None) -> Args:
    """
    Parse command-line arguments.

    :param argv: argument list (default: ``sys.argv[1:]``)
    :return: parsed arguments
    """
    global VERBOSE

    parser = argparse.ArgumentParser(
        description='Render JSON settings files from per-layer fragments',
        formatter_class=functools.partial(argparse.RawTextHelpFormatter, max_help_position=50),
    )
    parser.add_argument('targets', nargs='*', help=f'Targets to render (default: all of {", ".join(TARGETS)})')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--diff', action='store_true', help='Show live-vs-rendered differences; write nothing')
    mode.add_argument('--check', action='store_true', help='Exit 1 if a target is out of sync; write nothing')
    parser.add_argument('--force', action='store_true', help='Overwrite in-app edits (live file is backed up first)')
    parser.add_argument('--repo', default=str(DEFAULT_REPO), help='Base repository root (default: this repo)')
    parser.add_argument('-v', '--verbose', action='store_true', help='Report skipped and already-current targets')
    args    = parser.parse_args(argv, namespace=Args())
    VERBOSE = args.verbose
    return args


def main(argv: Sequence[str] | None = None) -> int:
    """
    Render, check, or diff settings targets.

    All requested targets are composed and validated before any is written, so a bad fragment never leaves a partial
    render behind.

    :param argv: command-line arguments (default: ``sys.argv[1:]``)
    :return: 0 ok, 1 drift refused / out of sync, 2 configuration or I/O error
    """
    args    = parse_args(argv)
    mode    = 'diff' if args.diff else 'check' if args.check else 'render'
    targets = list(args.targets) or list(TARGETS)
    unknown = [t for t in targets if t not in TARGETS]
    if unknown:
        error(f'unknown target(s): {", ".join(unknown)} (known: {", ".join(TARGETS)})')
        return 2

    try:
        roots    = layers(Path(args.repo))
        composed = [p for p in (prepare(target, roots) for target in targets) if p is not None]
    except RenderError as exc:
        error(str(exc))
        return 2

    retval = 0
    try:
        for prepared in composed:
            retval = max(retval, render_target(prepared, mode=mode, force=args.force))
    except OSError as exc:
        error(str(exc))
        return 2
    return retval


if __name__ == '__main__':
    sys.exit(main())
