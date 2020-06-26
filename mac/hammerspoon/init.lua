spaces = require("hs._asm.undocumented.spaces")

-- remove animation
hs.window.animationDuration = 0

-- check if string start with a given string
function string.starts(String,Start)
   return string.sub(String,1,string.len(Start))==Start
end

-- gets the length of a table
getTableLength = function(t)
    len = 0
    for _, _ in pairs(t) do
        len = len + 1
    end
    return len
end

-- function for performing keystrokes from code
doKeyStroke = function(modifiers, character)
    local event = require('hs.eventtap').event
    event.newKeyEvent(modifiers, string.lower(character), true):post()
    event.newKeyEvent(modifiers, string.lower(character), false):post()
end

-- launches last focused window of app
goToApp = function(appName)
    local windowFilter = hs.window.filter.new(appName)
    windowFilter:setSortOrder(hs.window.filter.sortByFocused)

    local windows = windowFilter:getWindows()
    if windows[1] then
        windows[1]:focus()
    end
end

-- minimizes focused window
function minimizeFocused()
    hs.window.focusedWindow():minimize()
end

-- moves focused window one monitor to the left
function moveFocusedLeftMonitor()
    local win = hs.window.focusedWindow()
    local leftScreen = win:screen():toWest()
    win:moveToScreen(leftScreen)
end

-- moves focused window one monitor to the right
function moveFocusedRightMonitor()
    local win = hs.window.focusedWindow()
    local rightScreen = win:screen():toEast()
    win:moveToScreen(rightScreen)
end

-- moves focused window to 'next' monitor
function moveFocusedNextMonitor()
    local win = hs.window.focusedWindow()
    win:moveToScreen(win:screen():next())
end

-- moves left a space
function moveLeftSpace()
    doKeyStroke({'ctrl'}, 'left')
end

-- moves right a space
function moveRightSpace()
    doKeyStroke({'ctrl'}, 'right')
end

-- shows Mission Control
function showMissionControl()
    doKeyStroke({'ctrl'}, 'up')
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
    spaceMovement = {'ctrl'},
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
        local bindingFunc
        if string.find(key, 'scroll') then
            bindingFunc = bindScrollEvent
        else
            bindingFunc = hs.hotkey.bind
        end

        if type(layoutOrFunc) == 'string' then
            bindingFunc(hyper, key, function()
                hs.window.focusedWindow():moveToUnit(layoutOrFunc)
            end)
        else
            bindingFunc(hyper, key, layoutOrFunc)
        end
    end
end

-- application shortcuts
appShortcutHyper = {'ctrl', 'shift'}
letterToAppMapping = {
    s = 'Safari',
    c = 'Calendar',
    e = 'Mail',
    o = 'OmniFocus',
    r = 'Radar',
    m = 'Messages',
    f = 'Finder',
    n = 'Notes',
    p = 'PyCharm',
    t = 'iTerm2',
    g = 'Google Chrome',
    k = 'Keynote',
    u = 'Sublime Text',
    z = 'Spotify',
    q = 'Quip',
    b = 'Numbers',
    x = 'Microsoft Excel',
    l = 'Slack',
    w = 'Cisco Webex Meetings'
}

for letter, app in pairs(letterToAppMapping) do
    hs.hotkey.bind(appShortcutHyper, letter, function() goToApp(app) end)
end
