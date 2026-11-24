--- === ReloadConfiguration ===
---
--- Adds a hotkey to reload the hammerspoon configuration, and a pathwatcher to automatically reload on changes.
---
--- Download: [https://github.com/Hammerspoon/Spoons/raw/master/Spoons/ReloadConfiguration.spoon.zip](https://github.com/Hammerspoon/Spoons/raw/master/Spoons/ReloadConfiguration.spoon.zip)

local obj = {}
obj.__index = obj

-- Metadata
obj.name = "ReloadConfiguration"
obj.version = "1.0"
obj.author = "Jon Lorusso <jonlorusso@gmail.com>"
obj.homepage = "https://github.com/Hammerspoon/Spoons"
obj.license = "MIT - https://opensource.org/licenses/MIT"


--- ReloadConfiguration.watch_paths
--- Variable
--- List of directories to watch for changes, defaults to hs.configdir
obj.watch_paths = { hs.configdir }

--- ReloadConfiguration:bindHotkeys(mapping)
--- Method
--- Binds hotkeys for ReloadConfiguration
---
--- Parameters:
---  * mapping - A table containing hotkey modifier/key details for the following items:
---   * reloadConfiguration - This will cause the configuration to be reloaded
function obj:bindHotkeys(mapping)
   local def = { reloadConfiguration = hs.fnutils.partial(hs.reload, self) }
   hs.spoons.bindHotkeysToSpec(def, mapping)
end

--- ReloadConfiguration:start()
--- Method
--- Start ReloadConfiguration
---
--- Parameters:
---  * None
function obj:start()
    -- Reload only when a Lua file changed, so .DS_Store and editor swap files do not trigger a reload
    local function reloadIfLuaChanged(paths)
        for _, path in ipairs(paths) do
            if path:sub(-4) == ".lua" then
                hs.reload()
                return
            end
        end
    end

    -- Stowed files are symlinks into the repository, and a watcher on hs.configdir never sees edits made
    -- through the link target, so also watch the directory init.lua resolves to.
    local dirs = {}
    for _, dir in pairs(self.watch_paths) do
        dirs[dir] = true
    end
    local initPath = hs.fs.pathToAbsolute(hs.configdir .. "/init.lua")
    if initPath then
        dirs[initPath:match("^(.*)/[^/]+$")] = true
    end

    self.watchers = {}
    for dir in pairs(dirs) do
        self.watchers[dir] = hs.pathwatcher.new(dir, reloadIfLuaChanged):start()
    end
    return self
end

return obj
