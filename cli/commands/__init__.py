"""
Command modules: importing each one registers its ``Command`` subclasses, in help-text and Makefile order
"""
# isort: skip_file
from __future__ import annotations

from cli.commands import setup         # noqa: F401
from cli.commands import deploy        # noqa: F401
from cli.commands import dotfiles      # noqa: F401
from cli.commands import inventory     # noqa: F401
from cli.commands import tools         # noqa: F401
from cli.commands import hooks         # noqa: F401
from cli.commands import testing       # noqa: F401
from cli.commands import analysis      # noqa: F401
from cli.commands import dependencies  # noqa: F401
from cli.commands import utilities     # noqa: F401
