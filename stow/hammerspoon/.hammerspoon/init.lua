-- remove animation
hs.window.animationDuration = 0

-- runs fn with the focused window; does nothing when no window has focus
local function withFocusedWindow(fn)
    local win = hs.window.focusedWindow()
    if win then
        fn(win)
    end
end

-- minimizes focused window
function minimizeFocused()
    withFocusedWindow(function(win) win:minimize() end)
end

-- moves focused window one monitor to the left (no-op when there is no monitor to the left)
function moveFocusedLeftMonitor()
    withFocusedWindow(function(win)
        local leftScreen = win:screen():toWest()
        if leftScreen then
            win:moveToScreen(leftScreen)
        end
    end)
end

-- moves focused window one monitor to the right (no-op when there is no monitor to the right)
function moveFocusedRightMonitor()
    withFocusedWindow(function(win)
        local rightScreen = win:screen():toEast()
        if rightScreen then
            win:moveToScreen(rightScreen)
        end
    end)
end

-- moves focused window to 'next' monitor
function moveFocusedNextMonitor()
    withFocusedWindow(function(win) win:moveToScreen(win:screen():next()) end)
end

-- window management region definitions
leftHalf = '[0,0,50,100]'
rightHalf = '[50,0,100,100]'
topHalf = '[0,0,100,50]'
bottomHalf = '[0,50,100,100]'

topLeftQuarter = '[0,0,50,50]'
topRightQuarter = '[50,0,100,50]'
bottomLeftQuarter = '[0,50,50,100]'
bottomRightQuarter = '[50,50,100,100]'

fullscreen = '[0,0,100,100]'

-- window management key/hyper mappings
windowManagementHyperMapping = {
    halfScreen = {'ctrl', 'cmd'},
    quarterScreen = {'ctrl', 'alt'},
    fullscreenMonitor = {'ctrl', 'alt', 'cmd'},
    numpad = {'ctrl', 'cmd'},
}

windowManagementKeyMapping = {
    halfScreen = {
        left = leftHalf,
        right = rightHalf,
        up = topHalf,
        down = bottomHalf,
    },
    quarterScreen = {
        left = topLeftQuarter,
        right = bottomRightQuarter,
        up = topRightQuarter,
        down = bottomLeftQuarter,
    },
    fullscreenMonitor = {
        left = moveFocusedLeftMonitor,
        right = moveFocusedRightMonitor,
        up = fullscreen,
        down = minimizeFocused,
    },
    numpad = {
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
}

-- bind hotkeys based on windowManagementHyperMapping and windowManagementKeyMapping
for region_type, mapping in pairs(windowManagementKeyMapping) do
    local hyper = windowManagementHyperMapping[region_type]
    for key, layoutOrFunc in pairs(mapping) do
        if type(layoutOrFunc) == 'string' then
            hs.hotkey.bind(hyper, key, function()
                withFocusedWindow(function(win) win:moveToUnit(layoutOrFunc) end)
            end)
        else
            hs.hotkey.bind(hyper, key, layoutOrFunc)
        end
    end
end

-- application shortcuts
appShortcutHyper = {'ctrl', 'shift'}
letterToWindowFilterMapping = {
    -- keep-sorted start
    b = hs.window.filter.new('Numbers'),
    c = hs.window.filter.new('Calendar'),
    d = hs.window.filter.new('Remote Desktop'),
    e = hs.window.filter.new('Mail'),
    f = hs.window.filter.new('Finder'),
    g = hs.window.filter.new('Google Chrome'),
    k = hs.window.filter.new('Keynote'),
    l = hs.window.filter.new('Slack'),
    m = hs.window.filter.new('Messages'),
    n = hs.window.filter.new('Notes'),
    o = hs.window.filter.new('OmniGraffle'),
    p = hs.window.filter.new('PyCharm'),
    s = hs.window.filter.new('Safari'),
    t = hs.window.filter.new('Todoist'),
    u = hs.window.filter.new('Sublime Text'),
    v = hs.window.filter.new('Code'),
    x = hs.window.filter.new('Microsoft Excel'),
    z = hs.window.filter.new('Zed')
    -- keep-sorted end
}

-- Optional overlay hotkeys: ~/.hammerspoon/overlay.lua returns { [letter] = mapping }
if package.searchpath("overlay", package.path) then
    local loaded, overlayMappings = pcall(require, "overlay")
    if loaded and type(overlayMappings) == "table" then
        for letter, mapping in pairs(overlayMappings) do
            letterToWindowFilterMapping[letter] = mapping
        end
    else
        print("overlay.lua ignored: " .. tostring(overlayMappings))
    end
end

-- launches last focused window of app given its window filter
goToApp = function(filter)
    local windows = filter:getWindows()
    if windows[1] then
        windows[1]:focus()
    end
end

for letter, filter in pairs(letterToWindowFilterMapping) do
    filter:keepActive()
    filter:setSortOrder(hs.window.filter.sortByFocusedLast)
    hs.hotkey.bind(appShortcutHyper, letter, function() goToApp(filter) end)
end

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
