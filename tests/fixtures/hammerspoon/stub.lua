-- Minimal `hs` stub for running the stowed Hammerspoon Lua under a stock `lua` interpreter.
-- Tests set fields on the globals below before loading the file under test, and read `calls` afterwards.

calls = {}              -- ordered log of side effects: strings such as 'reload' or 'notify:Title|Body'
hotkeys = {}            -- every callback registered through hs.hotkey.bind
pathwatchers = {}       -- { path = ..., fn = ... } for every hs.pathwatcher.new
state = {
    ssid     = nil,                -- value returned by hs.wifi.currentNetwork()
    location = 'authorized',       -- value returned by hs.location.authorizationStatus()
    focused  = nil,                -- value returned by hs.window.focusedWindow()
    initPath = '/real/repo/.hammerspoon/init.lua',
}

local filter = {}
filter.__index = filter
function filter:keepActive() return self end
function filter:setSortOrder() return self end
function filter:getWindows() return {} end

hs = {
    configdir = '/home/test/.hammerspoon',
    reload    = function() calls[#calls + 1] = 'reload' end,
    alert     = { show = function() end },
    window    = {
        animationDuration = 0.2,
        focusedWindow     = function() return state.focused end,
        filter            = {
            new                = function() return setmetatable({}, filter) end,
            sortByFocusedLast  = 'sortByFocusedLast',
        },
    },
    hotkey    = {
        bind = function(_, _, fn)
            hotkeys[#hotkeys + 1] = fn
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
