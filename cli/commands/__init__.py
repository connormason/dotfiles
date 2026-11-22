"""
Command modules: importing each one registers its ``Command`` subclasses, in help-text and Makefile order
"""
# isort: skip_file
from __future__ import annotations

from cli.commands import setup
from cli.commands import deploy
from cli.commands import dotfiles
from cli.commands import inventory
from cli.commands import tools
from cli.commands import hooks
from cli.commands import testing
from cli.commands import analysis
from cli.commands import dependencies
from cli.commands import utilities
from cli.commands import tool_config
