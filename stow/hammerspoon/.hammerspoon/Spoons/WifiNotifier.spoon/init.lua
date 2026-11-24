--- === WifiNotifier ===
---
--- Receive notifications every time your wifi network changes.
---
--- Download: https://github.com/Hammerspoon/Spoons/raw/master/Spoons/WifiNotifier.spoon.zip


local obj = {}
obj.__index = obj

-- Metadata
obj.name = "WifiNotifier"
obj.version = "1.0"
obj.author = "Garth Mortensen"
obj.homepage = "https://github.com/Hammerspoon/spoons"
obj.license = "MIT - https://opensource.org/licenses/MIT"

--- WifiNotifier:init()
--- Method
--- Initialize the WifiNotifier spoon
---
--- Returns:
--- * The WifiNotifier object
function obj:init()
    self.wifiNotifier = hs.wifi.watcher.new(function() self:ssidChangedCallback() end)
    self.lastSSID = hs.wifi.currentNetwork()
    self.newSSID  = nil
    return self
end

--- WifiNotifier:start()
--- Method
--- Starts the wifiNotifier
---
--- Returns:
--- * The WifiNotifier object
function obj:start()
    -- Since macOS 14, hs.wifi.currentNetwork() returns nil unless Hammerspoon may use Location Services
    local status = hs.location.authorizationStatus()
    if status ~= "authorized" then
        print("WifiNotifier: Location Services status is '" .. status .. "'; SSIDs will read as nil until " ..
              "Hammerspoon is allowed in System Settings > Privacy & Security > Location Services")
    end

    self.wifiNotifier:start()
    return self
end

--- WifiNotifier:ssidChangedCallback()
--- Method
--- Fires whenever the wifiWatcher detects an SSID change.
---
--- Returns:
--- * The WifiNotifier object
function obj:ssidChangedCallback()
    self.newSSID = hs.wifi.currentNetwork()

    if self.newSSID == nil and self.lastSSID == nil then
        -- nothing to report: neither side of the change is a known network
    elseif self.newSSID == nil then
        hs.notify.new({title="Wifi disconnected", informativeText="Left " .. self.lastSSID}):send()
    elseif self.lastSSID == nil then
        hs.notify.new({title="Wifi connected", informativeText="Joined " .. self.newSSID}):send()
    else
        hs.notify.new({title="Network Change", informativeText="Left " .. self.lastSSID .. ". Joined " .. self.newSSID}):send()
    end

    self.lastSSID = self.newSSID
end

return obj
