#!/usr/bin/env bash

NC="\033[0m"
YELLOW="\033[0;33m"

# Request sudo access if we don't already have it
if [ "$EUID" -ne 0 ]; then
	echo -e "${YELLOW}Enter your password plz...${NC}"
	sudo -v
	echo ""

	while true; do sudo -n true; sleep 60; kill -0 "$$" || exit; done 2>/dev/null &
fi

# Exit when any command fails
set -e

# Close any open System Preferences panes, to prevent them from overriding settings we’re about to change
echo "Closing System Preferences to prevent settings from being overridden..."
osascript -e 'tell application "System Preferences" to quit'


# *****************************
# Dock/Mission Control settings
# *****************************
echo "Setting up Dock/Mission Control..."

# Dock on right side of the screen
defaults write com.apple.dock orientation -string right

# Auto-hide dock
defaults write com.apple.dock autohide -integer 1

# Set dock icon size
defaults write com.apple.dock tilesize -integer 32

# Enable magnification on hover
defaults write com.apple.dock magnification -integer 1

# Set magnification level
defaults write com.apple.dock largesize -int 64

# Don’t animate opening applications from the Dock
defaults write com.apple.dock launchanim -bool false

# Enable spring loading for all Dock items
defaults write com.apple.dock enable-spring-load-actions-on-all-items -bool true

# Speed up Mission Control animations
defaults write com.apple.dock expose-animation-duration -float 0.1

# Don’t automatically rearrange Spaces based on most recent use
defaults write com.apple.dock mru-spaces -bool false

# Make Dock icons of hidden applications translucent
defaults write com.apple.dock showhidden -bool true

# Set bottom left screen hot corner to put display to sleep
defaults write com.apple.dock wvous-bl-corner -int 10
defaults write com.apple.dock wvous-bl-modifier -int 0

# Set top right screen hot corner to show desktop
defaults write com.apple.dock wvous-tr-corner -int 4
defaults write com.apple.dock wvous-tr-modifier -int 0

# Restart Dock
killall Dock


# ****************************
# Input/output device settings
# ****************************
echo "Setting up input/output device settings..."

# Disable auto-correct, auto capitalization, smart dashes, smart quotes, auto period substitution
defaults write NSGlobalDomain NSAutomaticSpellingCorrectionEnabled -bool false
defaults write NSGlobalDomain NSAutomaticCapitalizationEnabled -bool false
defaults write NSGlobalDomain NSAutomaticDashSubstitutionEnabled -bool false
defaults write NSGlobalDomain NSAutomaticQuoteSubstitutionEnabled -bool false
defaults write NSGlobalDomain NSAutomaticPeriodSubstitutionEnabled -bool false

# Disable “natural” (Lion-style) scrolling
defaults write NSGlobalDomain com.apple.swipescrolldirection -bool false

# Set keyboard repeat rate to be super fast
defaults write NSGlobalDomain KeyRepeat -int 5
defaults write NSGlobalDomain InitialKeyRepeat -int 10

# Enable trackpad tap-to-click for this user and the login screen
defaults write com.apple.driver.AppleBluetoothMultitouch.trackpad Clicking -bool true
defaults -currentHost write NSGlobalDomain com.apple.mouse.tapBehavior -int 1
defaults write NSGlobalDomain com.apple.mouse.tapBehavior -int 1

# Enable full keyboard access for all controls
# (e.g. enable Tab in modal dialogs)
defaults write NSGlobalDomain AppleKeyboardUIMode -int 3

# Increase sound quality for Bluetooth headphones/headsets
defaults write com.apple.BluetoothAudioAgent "Apple Bitpool Min (editable)" -int 40


# ***************
# Finder settings
# ***************
echo "Setting up Finder..."

# Show hidden files by default
defaults write com.apple.finder AppleShowAllFiles -bool true

# Show Finder status bar and path bar
defaults write com.apple.finder ShowStatusBar -bool true
defaults write com.apple.finder ShowPathbar -bool true

# Display full POSIX path as Finder window title
defaults write com.apple.finder _FXShowPosixPathInTitle -bool true

# Disable the warning when changing a file extension
defaults write com.apple.finder FXEnableExtensionChangeWarning -bool false

# Enable spring loading for directories and disable delay
defaults write NSGlobalDomain com.apple.springing.enabled -bool true
defaults write NSGlobalDomain com.apple.springing.delay -float 0

# Set Documents as the default location for new Finder windows
defaults write com.apple.finder NewWindowTarget -string "PfLo"
defaults write com.apple.finder NewWindowTargetPath -string "file://${HOME}/Documents/"

# Use list view in all Finder windows by default
defaults write com.apple.finder FXPreferredViewStyle -string "Nlsv"

# Show icons for hard drives, servers, and removable media on the desktop
defaults write com.apple.finder ShowExternalHardDrivesOnDesktop -bool true
defaults write com.apple.finder ShowHardDrivesOnDesktop -bool true
defaults write com.apple.finder ShowMountedServersOnDesktop -bool true
defaults write com.apple.finder ShowRemovableMediaOnDesktop -bool true

# Don't show recent tags in Finder sidebar
defaults write com.apple.finder ShowRecentTags -int 0

# Disable finger window animations and Get Info animations
defaults write com.apple.finder DisableAllAnimations -bool true

# Expand the following File Info panes:
# “General”, “Open with”, and “Sharing & Permissions”
defaults write com.apple.finder FXInfoPanesExpanded -dict \
	General -bool true \
	OpenWith -bool true \
	Privileges -bool true

# Avoid creating .DS_Store files on network or USB volumes
defaults write com.apple.desktopservices DSDontWriteNetworkStores -bool true
defaults write com.apple.desktopservices DSDontWriteUSBStores -bool true

# Automatically open a new Finder window when a volume is mounted
defaults write com.apple.frameworks.diskimages auto-open-ro-root -bool true
defaults write com.apple.frameworks.diskimages auto-open-rw-root -bool true
defaults write com.apple.finder OpenWindowForNewRemovableDisk -bool true

# Show the ~/Library folder
chflags nohidden ~/Library

# Show the /Volumes folder
sudo chflags nohidden /Volumes

# Restart Finder
killall Finder


# ***************
# Safari settings
# ***************
echo "Setting up Safari..."

# Show bookmarks bar by default
defaults write com.apple.Safari ShowFavoritesBar -bool true

# Allow hitting the Backspace key to go to the previous page in history
defaults write com.apple.Safari com.apple.Safari.ContentPageGroupIdentifier.WebKit2BackspaceKeyNavigationEnabled -bool true

# Enable Safari’s debug menu
defaults write com.apple.Safari IncludeInternalDebugMenu -bool true

# Enable the Develop menu and the Web Inspector in Safari
defaults write com.apple.Safari IncludeDevelopMenu -bool true
defaults write com.apple.Safari WebKitDeveloperExtrasEnabledPreferenceKey -bool true
defaults write com.apple.Safari com.apple.Safari.ContentPageGroupIdentifier.WebKit2DeveloperExtrasEnabled -bool true

# Update extensions automatically
defaults write com.apple.Safari InstallExtensionUpdatesAutomatically -bool true

# Kill Safari
killall Safari >> /dev/null 2>&1


# *****************
# Messages settings
# *****************
echo "Setting up Messages..."

# Disable smart quotes as it’s annoying for messages that contain code
defaults write com.apple.messageshelper.MessageController SOInputLineSettings -dict-add "automaticQuoteSubstitutionEnabled" -bool false

# Disable continuous spell checking
defaults write com.apple.messageshelper.MessageController SOInputLineSettings -dict-add "continuousSpellCheckingEnabled" -bool false

# Kill messages
killall Messages >> /dev/null 2>&1


# *************
# Mail settings
# *************
echo "Setting up Mail..."

# Copy email addresses as `foo@example.com` instead of `Foo Bar <foo@example.com>` in Mail.app
defaults write com.apple.mail AddressesIncludeNameOnPasteboard -bool false

# Kill Mail
killall Mail >> /dev/null 2>&1


# *************************
# Activity Monitor settings
# *************************
echo "Setting up Activity Monitor..."

# Show the main window when launching Activity Monitor
defaults write com.apple.ActivityMonitor OpenMainWindow -bool true

# Visualize CPU usage in the Activity Monitor Dock icon
defaults write com.apple.ActivityMonitor IconType -int 5

# Show all processes in Activity Monitor
defaults write com.apple.ActivityMonitor ShowCategory -int 0

# Sort Activity Monitor results by CPU usage
defaults write com.apple.ActivityMonitor SortColumn -string "CPUUsage"
defaults write com.apple.ActivityMonitor SortDirection -int 0

# Kill Activity Monitor
killall "Activity Monitor" >> /dev/null 2>&1


# ******************
# App Store settings
# ******************
echo "Setting up App Store..."

# Enable the automatic update check
defaults write com.apple.SoftwareUpdate AutomaticCheckEnabled -bool true

# Check for software updates daily, not just once per week
defaults write com.apple.SoftwareUpdate ScheduleFrequency -int 1

# Download newly available updates in background
defaults write com.apple.SoftwareUpdate AutomaticDownload -int 1

# Install System data files & security updates
defaults write com.apple.SoftwareUpdate CriticalUpdateInstall -int 1

# Turn on app auto-update
defaults write com.apple.commerce AutoUpdate -bool true


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

# Restart system UI server
killall SystemUIServer >> /dev/null 2>&1
killall cfprefsd >> /dev/null 2>&1
killall ControlStrip >> /dev/null 2>&1
