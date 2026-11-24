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

REPO_ROOT   = Path(__file__).resolve().parents[3]
HAMMERSPOON = REPO_ROOT / 'stow' / 'hammerspoon' / '.hammerspoon'
STUB        = REPO_ROOT / 'tests' / 'fixtures' / 'hammerspoon' / 'stub.lua'
INIT        = HAMMERSPOON / 'init.lua'
WIFI        = HAMMERSPOON / 'Spoons' / 'WifiNotifier.spoon' / 'init.lua'
RELOAD      = HAMMERSPOON / 'Spoons' / 'ReloadConfiguration.spoon' / 'init.lua'

pytestmark = pytest.mark.skipif(not shutil.which('lua'), reason='lua interpreter not available')

EPILOGUE = """
for _, c in ipairs(calls) do io.write('CALL ', c, '\\n') end
for _, p in ipairs(printed) do io.write('PRINT ', p, '\\n') end
for _, a in ipairs(alerts) do io.write('ALERT ', a, '\\n') end
"""

# Shown by init.lua on every load, so tests of other alerts filter it out
STARTUP_ALERT = 'Hammerspoon config reloaded'


def run_lua(body: str) -> tuple[list[str], list[str], list[str]]:
    """
    Run a Lua snippet after loading the ``hs`` stub and return what the code under test did

    :param body: Lua source executed after the stub is loaded
    :raises subprocess.CalledProcessError: if the Lua raises an error
    :return: the ``calls`` log, the captured ``print`` output, and the ``hs.alert`` texts, each in order
    """
    script  = f'dofile([[{STUB}]])\n{body}\n{EPILOGUE}'
    result  = subprocess.run(['lua', '-'], input=script, capture_output=True, text=True, check=True)
    lines   = result.stdout.splitlines()
    calls   = [line.removeprefix('CALL ')  for line in lines if line.startswith('CALL ')]
    printed = [line.removeprefix('PRINT ') for line in lines if line.startswith('PRINT ')]
    alerts  = [line.removeprefix('ALERT ') for line in lines if line.startswith('ALERT ')]
    return calls, printed, alerts


# ==================================================================================================
# init.lua
# ==================================================================================================


class TestInitWindowGuards:
    """
    Tests for the window-management handlers in init.lua
    """
    def test_every_hotkey_is_a_noop_without_a_focused_window(self) -> None:
        """
        Test that no window-management hotkey raises when no window has focus
        """
        calls, _, _ = run_lua(f"""
            dofile([[{INIT}]])
            for _, hotkey in ipairs(hotkeys) do
                if hotkey.mods ~= 'ctrl+shift' and hotkey.mods ~= 'cmd+alt+ctrl' then hotkey.fn() end
            end
        """)
        assert calls == []

    def test_monitor_moves_are_noops_on_a_single_display(self) -> None:
        """
        Test that moving left or right with no neighbouring monitor leaves the window alone
        """
        calls, _, _ = run_lua(f"""
            dofile([[{INIT}]])
            local screen = {{ toWest = function() return nil end, toEast = function() return nil end }}
            state.focused = {{
                screen       = function() return screen end,
                moveToScreen = function() calls[#calls + 1] = 'moved' end,
            }}
            press('ctrl+alt+cmd', 'left')
            press('ctrl+alt+cmd', 'right')
        """)
        assert calls == []

    def test_monitor_move_goes_to_the_neighbouring_screen(self) -> None:
        """
        Test that moving left hands the window to the screen west of its current one
        """
        calls, _, _ = run_lua(f"""
            dofile([[{INIT}]])
            local west   = {{ name = 'west' }}
            local screen = {{ toWest = function() return west end }}
            state.focused = {{
                screen       = function() return screen end,
                moveToScreen = function(_, target) calls[#calls + 1] = 'moved:' .. target.name end,
            }}
            press('ctrl+alt+cmd', 'left')
        """)
        assert calls == ['moved:west']

    @pytest.mark.parametrize(
        ('mods', 'key', 'unit'),
        [
            ('ctrl+cmd',     'left',  '[0,0,50,100]'),
            ('ctrl+cmd',     'pad6',  '[50,0,100,100]'),
            ('ctrl+alt',     'up',    '[50,0,100,50]'),
            ('ctrl+alt',     'down',  '[0,50,50,100]'),
            ('ctrl+cmd',     'pad5',  '[0,0,100,100]'),
            ('ctrl+alt+cmd', 'up',    '[0,0,100,100]'),
        ],
    )
    def test_region_hotkeys_move_the_window_to_their_unit_rect(self, mods: str, key: str, unit: str) -> None:
        """
        Test that the half, quarter, and fullscreen hotkeys fit the focused window to the right unit rect
        """
        calls, _, _ = run_lua(f"""
            dofile([[{INIT}]])
            state.focused = {{ moveToUnit = function(_, unit) calls[#calls + 1] = unit end }}
            press('{mods}', '{key}')
        """)
        assert calls == [unit]


class TestInitAppShortcuts:
    """
    Tests for the launch-or-focus application shortcuts in init.lua
    """
    def test_installed_app_is_launched_or_focused_by_bundle_id(self) -> None:
        """
        Test that a plain bundle ID is handed to launchOrFocusByBundleID
        """
        calls, _, alerts = run_lua(f"""
            state.installed['com.apple.mail'] = true
            dofile([[{INIT}]])
            press('ctrl+shift', 'e')
        """)
        assert calls == ['bundle:com.apple.mail']
        assert alerts == [STARTUP_ALERT]

    def test_edition_list_falls_back_to_the_next_installed_bundle_id(self) -> None:
        """
        Test that the first bundle ID in a list that resolves to an installed app wins
        """
        calls, _, _ = run_lua(f"""
            state.installed['com.jetbrains.pycharm.ce'] = true
            dofile([[{INIT}]])
            press('ctrl+shift', 'p')
        """)
        assert calls == ['bundle:com.jetbrains.pycharm', 'bundle:com.jetbrains.pycharm.ce']

    def test_name_entry_launches_by_app_name(self) -> None:
        """
        Test that a { name = ... } entry uses launchOrFocus instead of a bundle ID
        """
        calls, _, _ = run_lua(f"""
            dofile([[{INIT}]])
            press('ctrl+shift', 'o')
        """)
        assert calls == ['name:OmniGraffle']

    def test_missing_app_raises_an_alert_instead_of_failing_silently(self) -> None:
        """
        Test that a shortcut whose app is not installed tells the user
        """
        _, _, alerts = run_lua(f"""
            dofile([[{INIT}]])
            press('ctrl+shift', 'e')
        """)
        assert alerts == [STARTUP_ALERT, 'No installed app for com.apple.mail']

    def test_every_app_shortcut_launches_exactly_one_app(self) -> None:
        """
        Test that each ctrl+shift hotkey issues a launch request without raising
        """
        calls, _, _ = run_lua(f"""
            dofile([[{INIT}]])
            local count = 0
            for _, hotkey in ipairs(hotkeys) do
                if hotkey.mods == 'ctrl+shift' then
                    count = count + 1
                    local before = #calls
                    hotkey.fn()
                    assert(#calls > before, 'no launch for ' .. hotkey.key)
                end
            end
            calls[#calls + 1] = 'count:' .. count
        """)
        assert calls[-1] == 'count:18'

    def test_overlay_entries_override_and_extend_the_base_table(self, tmp_path: Path) -> None:
        """
        Test that overlay.lua can add a letter and replace a base one before the hotkeys are bound
        """
        (tmp_path / 'overlay.lua').write_text("return { q = 'com.example.Quip', e = { name = 'Other Mail' } }")
        calls, _, _ = run_lua(f"""
            package.path = [[{tmp_path}/?.lua;]] .. package.path
            state.installed['com.example.Quip'] = true
            dofile([[{INIT}]])
            press('ctrl+shift', 'q')
            press('ctrl+shift', 'e')
        """)
        assert calls == ['bundle:com.example.Quip', 'name:Other Mail']

    def test_broken_overlay_is_reported_and_base_shortcuts_survive(self, tmp_path: Path) -> None:
        """
        Test that an overlay that fails to load is skipped with a console note
        """
        (tmp_path / 'overlay.lua').write_text('error("boom")')
        calls, printed, _ = run_lua(f"""
            package.path = [[{tmp_path}/?.lua;]] .. package.path
            state.installed['com.apple.mail'] = true
            dofile([[{INIT}]])
            press('ctrl+shift', 'e')
        """)
        assert calls == ['bundle:com.apple.mail']
        assert printed[0].startswith('overlay.lua ignored')


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
        calls, _, _ = run_lua(f"""
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
        calls, _, _ = run_lua(f"""
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
        _, printed, _ = run_lua(f"""
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
            (['/home/test/.hammerspoon/.DS_Store'],                         False),
            (['/home/test/.hammerspoon/init.lua.swp'],                      False),
            (['/home/test/.hammerspoon/Spoons/X.spoon/docs.json'],          False),
            (['/home/test/.hammerspoon/init.lua'],                          True),
            (['/home/test/.hammerspoon/.DS_Store', '/real/repo/other.lua'], True),
        ],
    )
    def test_reloads_only_when_a_lua_file_changed(self, changed: list[str], reloads: bool) -> None:
        """
        Test that the watcher ignores non-Lua changes and reloads once for Lua ones
        """
        paths = ', '.join(f"'{p}'" for p in changed)
        calls, _, _ = run_lua(f"""
            local obj = dofile([[{RELOAD}]])
            obj:start()
            pathwatchers[1].fn({{ {paths} }})
        """)
        assert calls == (['reload'] if reloads else [])

    def test_watches_the_directory_a_symlinked_init_resolves_to(self) -> None:
        """
        Test that the repository directory behind a stowed init.lua is watched alongside the config directory
        """
        calls, _, _ = run_lua(f"""
            local obj = dofile([[{RELOAD}]])
            obj:start()
            local dirs = {{}}
            for _, w in ipairs(pathwatchers) do dirs[#dirs + 1] = w.path end
            table.sort(dirs)
            calls[#calls + 1] = table.concat(dirs, ',')
        """)
        assert calls == ['/home/test/.hammerspoon,/real/repo/.hammerspoon']
