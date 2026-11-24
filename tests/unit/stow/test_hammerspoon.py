"""
Tests for the stowed Hammerspoon Lua (``init.lua`` and the WifiNotifier and ReloadConfiguration Spoons)

The Lua runs under a stock ``lua`` interpreter against the ``hs`` stub in ``tests/fixtures/hammerspoon/stub.lua``, so
these cover the control flow of the config (nil guards, notification branches, reload filtering) but not Hammerspoon's
own APIs.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT    = Path(__file__).resolve().parents[3]
HAMMERSPOON  = REPO_ROOT / 'stow' / 'hammerspoon' / '.hammerspoon'
STUB         = REPO_ROOT / 'tests' / 'fixtures' / 'hammerspoon' / 'stub.lua'
INIT         = HAMMERSPOON / 'init.lua'
WIFI         = HAMMERSPOON / 'Spoons' / 'WifiNotifier.spoon' / 'init.lua'
RELOAD       = HAMMERSPOON / 'Spoons' / 'ReloadConfiguration.spoon' / 'init.lua'

pytestmark = pytest.mark.skipif(not shutil.which('lua'), reason='lua interpreter not available')

EPILOGUE = """
for _, c in ipairs(calls) do io.write('CALL ', c, '\\n') end
for _, p in ipairs(printed) do io.write('PRINT ', p, '\\n') end
"""


def run_lua(body: str) -> tuple[list[str], list[str]]:
    """
    Run a Lua snippet after loading the ``hs`` stub and return what the code under test did

    :param body: Lua source executed after the stub is loaded
    :raises subprocess.CalledProcessError: if the Lua raises an error
    :return: the ``calls`` log and the captured ``print`` output, in order
    """
    script = f'dofile([[{STUB}]])\n{body}\n{EPILOGUE}'
    result = subprocess.run(['lua', '-'], input=script, capture_output=True, text=True, check=True)
    lines  = result.stdout.splitlines()
    calls  = [line.removeprefix('CALL ') for line in lines if line.startswith('CALL ')]
    printed = [line.removeprefix('PRINT ') for line in lines if line.startswith('PRINT ')]
    return calls, printed


# ==================================================================================================
# init.lua
# ==================================================================================================


class TestInitWindowGuards:
    """
    Tests for the window-management handlers in init.lua
    """
    def test_every_hotkey_is_a_noop_without_a_focused_window(self) -> None:
        """
        Test that no bound hotkey raises when no window has focus
        """
        run_lua(f'dofile([[{INIT}]])\nfor _, fn in ipairs(hotkeys) do fn() end')

    def test_monitor_moves_are_noops_on_a_single_display(self) -> None:
        """
        Test that moving left or right with no neighbouring monitor leaves the window alone
        """
        calls, _ = run_lua(f"""
            dofile([[{INIT}]])
            local screen = {{ toWest = function() return nil end, toEast = function() return nil end }}
            state.focused = {{
                screen       = function() return screen end,
                moveToScreen = function() calls[#calls + 1] = 'moved' end,
            }}
            moveFocusedLeftMonitor()
            moveFocusedRightMonitor()
        """)
        assert calls == []

    def test_monitor_move_goes_to_the_neighbouring_screen(self) -> None:
        """
        Test that moving left hands the window to the screen west of its current one
        """
        calls, _ = run_lua(f"""
            dofile([[{INIT}]])
            local west   = {{ name = 'west' }}
            local screen = {{ toWest = function() return west end }}
            state.focused = {{
                screen       = function() return screen end,
                moveToScreen = function(_, target) calls[#calls + 1] = 'moved:' .. target.name end,
            }}
            moveFocusedLeftMonitor()
        """)
        assert calls == ['moved:west']


# ==================================================================================================
# WifiNotifier
# ==================================================================================================


class TestWifiNotifier:
    """
    Tests for the WifiNotifier spoon
    """
    def test_notification_branches_follow_the_network_sequence(self) -> None:
        """
        Test that join, roam, leave, and repeated no-network events each produce the right notification
        """
        calls, _ = run_lua(f"""
            local obj = dofile([[{WIFI}]])
            obj:init()
            for _, ssid in ipairs({{ 'A', 'B', false, false, 'C' }}) do
                state.ssid = ssid or nil
                obj:ssidChangedCallback()
            end
        """)
        assert calls == [
            'notify:Wifi connected|Joined A',
            'notify:Network Change|Left A. Joined B',
            'notify:Wifi disconnected|Left B',
            'notify:Wifi connected|Joined C',
        ]

    def test_first_join_without_prior_network_reads_as_connected(self) -> None:
        """
        Test that joining a network when none was known announces a connection rather than a change
        """
        calls, _ = run_lua(f"""
            local obj = dofile([[{WIFI}]])
            obj:init()
            state.ssid = 'Home'
            obj:ssidChangedCallback()
        """)
        assert calls == ['notify:Wifi connected|Joined Home']

    @pytest.mark.parametrize(
        ('status', 'warns'),
        [
            ('authorized', False),
            ('denied',     True),
            ('undefined',  True),
        ],
    )
    def test_start_warns_unless_location_services_are_authorized(self, status: str, warns: bool) -> None:
        """
        Test that start() flags a missing Location Services grant in the console
        """
        _, printed = run_lua(f"""
            local obj = dofile([[{WIFI}]])
            state.location = '{status}'
            obj:init()
            obj:start()
        """)
        assert bool(printed) is warns
        if warns:
            assert status in printed[0]


# ==================================================================================================
# ReloadConfiguration
# ==================================================================================================


class TestReloadConfiguration:
    """
    Tests for the ReloadConfiguration spoon
    """
    @pytest.mark.parametrize(
        ('changed', 'reloads'),
        [
            (['/home/test/.hammerspoon/.DS_Store'],                           False),
            (['/home/test/.hammerspoon/init.lua.swp'],                        False),
            (['/home/test/.hammerspoon/Spoons/X.spoon/docs.json'],            False),
            (['/home/test/.hammerspoon/init.lua'],                            True),
            (['/home/test/.hammerspoon/.DS_Store', '/real/repo/other.lua'],   True),
        ],
    )
    def test_reloads_only_when_a_lua_file_changed(self, changed: list[str], reloads: bool) -> None:
        """
        Test that the watcher ignores non-Lua changes and reloads once for Lua ones
        """
        paths = ', '.join(f"'{p}'" for p in changed)
        calls, _ = run_lua(f"""
            local obj = dofile([[{RELOAD}]])
            obj:start()
            pathwatchers[1].fn({{ {paths} }})
        """)
        assert calls == (['reload'] if reloads else [])

    def test_watches_the_directory_a_symlinked_init_resolves_to(self) -> None:
        """
        Test that the repository directory behind a stowed init.lua is watched alongside the config directory
        """
        calls, _ = run_lua(f"""
            local obj = dofile([[{RELOAD}]])
            obj:start()
            local dirs = {{}}
            for _, w in ipairs(pathwatchers) do dirs[#dirs + 1] = w.path end
            table.sort(dirs)
            calls[#calls + 1] = table.concat(dirs, ',')
        """)
        assert calls == ['/home/test/.hammerspoon,/real/repo/.hammerspoon']
