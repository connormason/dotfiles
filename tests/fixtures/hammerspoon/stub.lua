-- Minimal `hs` stub for running the stowed Hammerspoon Lua under a stock `lua` interpreter.
-- Tests set fields on the globals below before loading the file under test, and read `calls` afterwards.

calls = {}              -- ordered log of side effects: strings such as 'reload' or 'notify:Title|Body'
alerts = {}             -- text of every hs.alert.show
hotkeys = {}            -- { mods = 'ctrl+shift', key = 'e', fn = ... } for every hs.hotkey.bind
pathwatchers = {}       -- { path = ..., fn = ... } for every hs.pathwatcher.new
state = {
    ssid      = nil,                -- value returned by hs.wifi.currentNetwork()
    location  = 'authorized',       -- value returned by hs.location.authorizationStatus()
    focused   = nil,                -- value returned by hs.window.focusedWindow()
    installed = {},                 -- set of bundle IDs that hs.application.launchOrFocusByBundleID can find
    initPath  = '/real/repo/.hammerspoon/init.lua',
}

-- presses the hotkey bound to mods (a '+'-joined string such as 'ctrl+shift') and key; fails if none is bound
function press(mods, key)
    for _, hotkey in ipairs(hotkeys) do
        if hotkey.mods == mods and hotkey.key == key then
            return hotkey.fn()
        end
    end
    error('no hotkey bound to ' .. mods .. '+' .. key)
end

hs = {
    configdir = '/home/test/.hammerspoon',
    reload    = function() calls[#calls + 1] = 'reload' end,
    alert     = { show = function(text) alerts[#alerts + 1] = text end },
    window    = {
        animationDuration = 0.2,
        focusedWindow     = function() return state.focused end,
    },
    application = {
        launchOrFocusByBundleID = function(id)
            calls[#calls + 1] = 'bundle:' .. id
            return state.installed[id] == true
        end,
        launchOrFocus = function(name)
            calls[#calls + 1] = 'name:' .. name
            return true
        end,
    },
    hotkey    = {
        bind = function(mods, key, fn)
            hotkeys[#hotkeys + 1] = { mods = table.concat(mods, '+'), key = key, fn = fn }
            return {}
        end,
    },
    fs        = { pathToAbsolute = function() return state.initPath end },
    pathwatcher = {
        new = function(path, fn)
            local watcher = { path = path, fn = fn }
            function watcher:start() return self end
            pathwatchers[#pathwatchers + 1] = watcher
            return watcher
        end,
    },
    wifi      = {
        watcher        = { new = function() return { start = function() end } end },
        currentNetwork = function() return state.ssid end,
    },
    notify    = {
        new = function(args)
            return { send = function() calls[#calls + 1] = 'notify:' .. args.title .. '|' .. args.informativeText end }
        end,
    },
    location  = { authorizationStatus = function() return state.location end },
    loadSpoon = function() end,
}
spoon = { WifiNotifier = { start = function() end }, ReloadConfiguration = { start = function() end } }

-- print() output of the file under test is captured so tests can assert on warnings
printed = {}
print = function(...)
    local parts = {}
    for i = 1, select('#', ...) do parts[#parts + 1] = tostring((select(i, ...))) end
    printed[#printed + 1] = table.concat(parts, '\t')
end
