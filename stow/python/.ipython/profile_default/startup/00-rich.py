from __future__ import annotations

import os

IPYTHON_RICH_PRETTY_DISABLE: bool = os.getenv('IPYTHON_RICH_PRETTY_DISABLE', 'false').lower() == 'true'
if IPYTHON_RICH_PRETTY_DISABLE:
    print('⚪ Automatic rich pretty printing disabled via IPYTHON_RICH_PRETTY_DISABLE')
else:
    try:
        from rich import pretty
    except (ImportError, ModuleNotFoundError, NameError):
        print('🟡 Automatic rich pretty printing disabled (rich not installed)')
    else:
        pretty.install()
        print('🟢 Automatic rich pretty printing enabled')
