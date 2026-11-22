"""
Tiny persistent set of already-notified problems, so a stuck torrent alerts once instead of every cycle
"""
from __future__ import annotations

import contextlib
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

__all__ = [
    'State',
]


class State:
    """
    A JSON-backed set of string keys; a missing or corrupt file is treated as empty
    """
    def __init__(self, path: Path) -> None:
        """
        Load the state file

        :param path: JSON file location (parent directories are created on save)
        """
        self.path = path
        self._keys: set[str] = set()
        with contextlib.suppress(OSError, ValueError):
            data = json.loads(path.read_text(encoding='utf-8'))
            self._keys = {str(key) for key in data.get('notified', [])}

    def __contains__(self, key: str) -> bool:
        """
        Whether a key has been recorded

        :param key: problem key
        :return: True if recorded
        """
        return key in self._keys

    def add(self, key: str) -> None:
        """
        Record a key

        :param key: problem key
        """
        self._keys.add(key)

    def discard(self, key: str) -> None:
        """
        Forget a key (so a recurrence alerts again)

        :param key: problem key
        """
        self._keys.discard(key)

    def prune(self, prefixes: tuple[str, ...], *, keep: set[str]) -> None:
        """
        Forget recorded keys that no longer apply

        :param prefixes: only keys starting with one of these are candidates
        :param keep: candidate keys to retain (the problems still present)
        """
        self._keys = {key for key in self._keys if key in keep or not key.startswith(prefixes)}

    def save(self) -> None:
        """
        Write the state atomically; failures are swallowed because losing dedupe state only costs a repeat alert
        """
        tmp = self.path.with_name(self.path.name + '.tmp')
        with contextlib.suppress(OSError):
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps({'notified': sorted(self._keys)}), encoding='utf-8')
            tmp.replace(self.path)
