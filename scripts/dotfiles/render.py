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
import shutil
import subprocess
import sys
import time
from collections.abc import Sequence
from pathlib import Path

# ==========================
# Constants/defaults/globals
# ==========================


VERBOSE:       bool = False
UNMANAGED_KEY: str  = '$unmanaged'
DEFAULT_REPO:  Path = Path(__file__).resolve().parents[2]

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


# ==================
# Formatting/logging
# ==================


def info(message: str) -> None:
    """
    Print an informational line to stdout.

    :param message: text to print
    """
    print(f'render: {message}')


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
            key = canonical(item)
            if key not in seen:
                combined.append(item)
                seen.add(key)
        return combined
    return _drop_nulls(overlay)


def layers(repo: Path) -> list[Path]:
    """
    Resolve layer roots via ``bootstrap/lib.sh`` so shell and Python agree on one registry.

    :param repo: base repository root
    :raises RenderError: if the registry names a missing overlay or lib.sh fails
    :return: layer roots, base first
    """
    result = subprocess.run(
        ['bash', '-c', 'source "$1/bootstrap/lib.sh" && dotfiles_layers', '_', str(repo)],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, 'DOTFILES_REPO': str(repo)},
    )
    if result.returncode != 0:
        raise RenderError(result.stderr.strip() or 'dotfiles_layers failed')
    return [Path(line) for line in result.stdout.splitlines() if line]


def compose(fragments: Sequence[Path]) -> tuple[dict[str, object], list[str]]:
    """
    Merge fragments in order and split out the unmanaged-key list.

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
    return {k: v for k, v in merged.items() if k not in unmanaged}, unmanaged


def state_path(target: str) -> Path:
    """
    Where the last managed render of a target is stored.

    :param target: target id
    :return: state file path
    """
    state_home = os.environ.get('XDG_STATE_HOME') or str(Path.home() / '.local' / 'state')
    return Path(state_home) / 'dotfiles' / 'render' / f'{target}.json'


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

    :param dest: live target path
    :return: backup path
    """
    home = Path.home()
    try:
        relative = dest.relative_to(home)
    except ValueError:
        relative = Path(dest.name)
    backup = home / '.dotfiles-backup' / time.strftime('%Y%m%d-%H%M%S') / relative
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(dest, backup)
    return backup


def render_target(target: str, repo: Path, *, mode: str, force: bool) -> int:
    """
    Render, check, or diff one target.

    :param target: target id from :data:`TARGETS`
    :param repo: base repository root
    :param mode: ``'render'``, ``'check'``, or ``'diff'``
    :param force: overwrite despite drift (after backing up)
    :raises RenderError: on configuration errors
    :return: 0 ok / in sync, 1 drift refused / out of sync
    """
    fragments = [layer / 'render' / f'{target}.json' for layer in layers(repo)]
    fragments = [f for f in fragments if f.is_file()]
    if not fragments:
        if VERBOSE:
            info(f'{target}: no fragments in any layer; skipped')
        return 0

    managed, unmanaged = compose(fragments)
    new_text  = dumps(managed)
    dest      = Path(TARGETS[target]).expanduser()
    state     = state_path(target)
    last_text = state.read_text(encoding='utf-8') if state.is_file() else None

    live: dict[str, object] | None = None
    live_ok = True
    if dest.exists():
        try:
            parsed = json.loads(dest.read_text(encoding='utf-8'))
            live   = parsed if isinstance(parsed, dict) else None
            live_ok = live is not None
        except (UnicodeDecodeError, json.JSONDecodeError):
            live_ok = False
    live_managed_text = dumps({k: v for k, v in live.items() if k not in unmanaged}) if live is not None else None

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
    if last_text is not None and live_managed_text is not None:
        in_sync = canonical(json.loads(last_text)) == canonical(json.loads(live_managed_text))
    drifted = dest.exists() and not current and not in_sync
    if drifted and not force:
        reason = 'is not valid JSON' if not live_ok else 'was edited since the last render'
        error(f'{target}: {dest} {reason}; move the change into a render fragment, or re-run with --force')
        print(_diff(last_text or '', live_managed_text or '', 'last render', f'{dest} (live)'), end='', file=sys.stderr)
        return 1

    output = dict(managed)
    if live is not None:
        output.update({k: live[k] for k in unmanaged if k in live})
    output_text = dumps(output)

    if dest.exists() and force and drifted:
        info(f'{target}: backed up live file to {_backup(dest)}')
    if dest.is_symlink():
        dest.unlink()
    if not dest.exists() or dest.read_text(encoding='utf-8') != output_text:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(output_text, encoding='utf-8')
        info(f'{target}: rendered {dest}')
    elif VERBOSE:
        info(f'{target}: already current')
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(new_text, encoding='utf-8')
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

    :param argv: command-line arguments (default: ``sys.argv[1:]``)
    :return: 0 ok, 1 drift refused / out of sync, 2 configuration error
    """
    args    = parse_args(argv)
    mode    = 'diff' if args.diff else 'check' if args.check else 'render'
    targets = list(args.targets) or list(TARGETS)
    unknown = [t for t in targets if t not in TARGETS]
    if unknown:
        error(f'unknown target(s): {", ".join(unknown)} (known: {", ".join(TARGETS)})')
        return 2

    retval = 0
    for target in targets:
        try:
            retval = max(retval, render_target(target, Path(args.repo), mode=mode, force=args.force))
        except RenderError as exc:
            error(str(exc))
            return 2
    return retval


if __name__ == '__main__':
    sys.exit(main())
