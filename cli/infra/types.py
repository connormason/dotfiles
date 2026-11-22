"""
Shared type aliases, protocols, and small data types
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from typing import Callable
from typing import NamedTuple
from typing import Protocol
from typing import TypedDict
from typing import TypeVar
from typing import Union

if TYPE_CHECKING:
    from types import ModuleType

__all__ = [
    'AddArgumentsFunc',
    'CommandFunc',
    'F',
    'ModT',
    'PathLike',
    'SSHTarget',
    'StyleColor',
    'SupportsWrite',
    'T_contra',
    'ToolInfo',
]


# ==================================================================================================
# Basic types
# ==================================================================================================


F        = TypeVar('F',        bound=Callable[..., Any])
T_contra = TypeVar('T_contra', contravariant=True)
ModT     = TypeVar('ModT',     bound='ModuleType')

PathLike         = Union[str, Path]
StyleColor       = Union[int, tuple[int, int, int], str]
CommandFunc      = Callable[[argparse.Namespace],      None]
AddArgumentsFunc = Callable[[argparse.ArgumentParser], None]


class SupportsWrite(Protocol[T_contra]):
    """
    Protocol for types that support being written to and flushed (what ``print(..., flush=True)`` requires)
    """
    def write(self, s: T_contra, /) -> object: ...

    def flush(self) -> object: ...


class ToolInfo(TypedDict):
    """
    Basic metadata about a tool used by this script (like python or uv)
    """
    executable: Path
    version:    str


class SSHTarget(NamedTuple):
    """
    SSH target details (host + user)
    """
    host: str
    user: str
