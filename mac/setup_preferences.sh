#!/usr/bin/env bash

NC="\033[0m"
YELLOW="\033[0;33m"

# **************
# Other settings
# **************
echo "Setting up other various settings..."

# Show battery percentage in menu bar
defaults write com.apple.menuextra.battery ShowPercent -string "YES"

# Show audio settings in menu bar
defaults write com.apple.systemuiserver menuExtras -array-add "/System/Library/CoreServices/Menu Extras/Volume.menu"

# Set menu bar date format
defaults write com.apple.menuextra.clock DateFormat -string "EEE d MMM h:mm:ss a"

# Customize items on right side of touch bar
defaults write com.apple.controlstrip MiniCustomized '(com.apple.system.volume, com.apple.system.brightness, com.apple.system.airplay )'

# Always show expanded options in print menu
defaults write -g PMPrintingExpandedStateForPrint -bool TRUE

# Change default screenshot storage location to ~/Desktop/Screenshots
defaults write com.apple.screencapture location /Users/connormason/Desktop/Screenshots/

# Don’t display the annoying prompt when quitting iTerm
defaults write com.googlecode.iterm2 PromptOnQuit -bool false

# Increase window resize speed for Cocoa applications
defaults write NSGlobalDomain NSWindowResizeTime -float 0.001

# Reveal IP address, hostname, OS version, etc. when clicking the clock in the login window
sudo defaults write /Library/Preferences/com.apple.loginwindow AdminHostInfo HostName


# Kill all apps we modified
for app in "Activity Monitor" \
	"Calendar" \
	"cfprefsd" \
	"ControlStrip" \
	"Dock" \
	"Finder" \
	"Mail" \
	"Messages" \
	"Safari" \
	"SystemUIServer"; do
	killall "${app}" || true &> /dev/null
done
