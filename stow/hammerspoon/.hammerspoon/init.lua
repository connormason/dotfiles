-- remove animation
hs.window.animationDuration = 0

-- ==================================================================================================
-- Window management
-- ==================================================================================================

-- runs fn with the focused window; does nothing when no window has focus
local function withFocusedWindow(fn)
    local win = hs.window.focusedWindow()
    if win then
        fn(win)
    end
end

-- returns a handler that fits the focused window to a unit rect (percentages of its screen)
local function moveToRegion(unitRect)
    return function()
        withFocusedWindow(function(win) win:moveToUnit(unitRect) end)
    end
end

-- minimizes focused window
local function minimizeFocused()
    withFocusedWindow(function(win) win:minimize() end)
end

-- moves focused window one monitor to the left (no-op when there is no monitor to the left)
local function moveFocusedLeftMonitor()
    withFocusedWindow(function(win)
        local leftScreen = win:screen():toWest()
        if leftScreen then
            win:moveToScreen(leftScreen)
        end
    end)
end

-- moves focused window one monitor to the right (no-op when there is no monitor to the right)
local function moveFocusedRightMonitor()
    withFocusedWindow(function(win)
        local rightScreen = win:screen():toEast()
        if rightScreen then
            win:moveToScreen(rightScreen)
        end
    end)
end

-- moves focused window to 'next' monitor
local function moveFocusedNextMonitor()
    withFocusedWindow(function(win) win:moveToScreen(win:screen():next()) end)
end

local leftHalf = moveToRegion('[0,0,50,100]')
local rightHalf = moveToRegion('[50,0,100,100]')
local topHalf = moveToRegion('[0,0,100,50]')
local bottomHalf = moveToRegion('[0,50,100,100]')

local topLeftQuarter = moveToRegion('[0,0,50,50]')
local topRightQuarter = moveToRegion('[50,0,100,50]')
local bottomLeftQuarter = moveToRegion('[0,50,50,100]')
local bottomRightQuarter = moveToRegion('[50,50,100,100]')

local fullscreen = moveToRegion('[0,0,100,100]')

local windowBindings = {
    {
        mods = {'ctrl', 'cmd'},
        keys = {
            left = leftHalf,
            right = rightHalf,
            up = topHalf,
            down = bottomHalf,
        },
    },
    {
        mods = {'ctrl', 'alt'},
        keys = {
            left = topLeftQuarter,
            right = bottomRightQuarter,
            up = topRightQuarter,
            down = bottomLeftQuarter,
        },
    },
    {
        mods = {'ctrl', 'alt', 'cmd'},
        keys = {
            left = moveFocusedLeftMonitor,
            right = moveFocusedRightMonitor,
            up = fullscreen,
            down = minimizeFocused,
        },
    },
    {
        mods = {'ctrl', 'cmd'},
        keys = {
            pad4 = leftHalf,
            pad6 = rightHalf,
            pad8 = topHalf,
            pad2 = bottomHalf,
            pad7 = topLeftQuarter,
            pad9 = topRightQuarter,
            pad1 = bottomLeftQuarter,
            pad3 = bottomRightQuarter,
            pad5 = fullscreen,
            pad0 = moveFocusedNextMonitor,
        },
    },
}

for _, group in ipairs(windowBindings) do
    for key, action in pairs(group.keys) do
        hs.hotkey.bind(group.mods, key, action)
    end
end

-- ==================================================================================================
-- Application shortcuts
-- ==================================================================================================

local appShortcutHyper = {'ctrl', 'shift'}

-- letter -> app to launch or focus. An app is a bundle ID, a list of bundle IDs for apps whose ID differs between
-- editions (the first one that is installed wins), or { name = 'App Name' } when no stable bundle ID exists.
local appShortcuts = {
    -- keep-sorted start
    b = 'com.apple.Numbers',
    c = 'com.apple.iCal',
    d = 'com.apple.RemoteDesktop',
    e = 'com.apple.mail',
    f = 'com.apple.finder',
    g = 'com.google.Chrome',
    k = 'com.apple.Keynote',
    l = 'com.tinyspeck.slackmacgap',
    m = 'com.apple.MobileSMS',
    n = 'com.apple.Notes',
    o = { name = 'OmniGraffle' },
    p = {'com.jetbrains.pycharm', 'com.jetbrains.pycharm.ce'},
    s = 'com.apple.Safari',
    t = 'com.todoist.mac.Todoist',
    u = 'com.sublimetext.4',
    v = 'com.microsoft.VSCode',
    x = 'com.microsoft.Excel',
    z = 'dev.zed.Zed',
    -- keep-sorted end
}

-- Optional overlay shortcuts: ~/.hammerspoon/overlay.lua returns { [letter] = app }, merged over the table above
if package.searchpath("overlay", package.path) then
    local loaded, overlayShortcuts = pcall(require, "overlay")
    if loaded and type(overlayShortcuts) == "table" then
        for letter, app in pairs(overlayShortcuts) do
            appShortcuts[letter] = app
        end
    else
        print("overlay.lua ignored: " .. tostring(overlayShortcuts))
    end
end

-- launches the app, or brings it forward when it is already running (including when it has no open windows)
local function launchOrFocus(app)
    if type(app) == 'string' then
        app = {app}
    end

    if app.name then
        hs.application.launchOrFocus(app.name)
        return
    end

    for _, bundleID in ipairs(app) do
        if hs.application.launchOrFocusByBundleID(bundleID) then
            return
        end
    end
    hs.alert.show("No installed app for " .. table.concat(app, ", "))
end

for letter, app in pairs(appShortcuts) do
    hs.hotkey.bind(appShortcutHyper, letter, function() launchOrFocus(app) end)
end

-- ==================================================================================================
-- Spoons and reload
-- ==================================================================================================

-- notify when WiFi network changes
hs.loadSpoon("WifiNotifier")
spoon.WifiNotifier:start()

-- reload config when config file modified
hs.loadSpoon("ReloadConfiguration")
spoon.ReloadConfiguration:start()

-- reload config hotkey
hs.hotkey.bind({"cmd", "alt", "ctrl"}, "R", function()
  hs.reload()
end)
hs.alert.show("Hammerspoon config reloaded")
