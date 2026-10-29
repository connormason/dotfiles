#!/usr/bin/env bash
#
# 60-macos: apply macOS system preferences (defaults / chflags / killall).
#
# Mac App Store apps are declared in the Brewfile and installed by stage 50-brew (`brew bundle`), not here.
#
# Useful references for available defaults keys/values
#   - https://macos-defaults.com
#   - https://github.com/mathiasbynens/dotfiles/blob/main/.macos
#   - https://github.com/kevinSuttle/macOS-Defaults/tree/master
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh disable=SC1091
source "$HERE/lib.sh"

# Close System Settings so it does not override changes.
run osascript -e 'tell application "System Preferences" to quit' || true

# ------------------------------------------------------------------------------------------------
# Activity Monitor (com.apple.ActivityMonitor)
# ------------------------------------------------------------------------------------------------

# Show main window when launching Activity Monitor
run defaults write com.apple.ActivityMonitor OpenMainWindow -bool true

# Visualize CPU usage in the Activity Monitor dock icon
run defaults write com.apple.ActivityMonitor IconType -int 5

# Show all processes in Activity Monitor
run defaults write com.apple.ActivityMonitor ShowCategory -int 0

# Sort Activity Monitor results by CPU usage (column)
run defaults write com.apple.ActivityMonitor SortColumn -string "CPUUsage"

# Sort Activity Monitor results by CPU usage (direction)
run defaults write com.apple.ActivityMonitor SortDirection -int 0

# ------------------------------------------------------------------------------------------------
# Software Update / App Store
# ------------------------------------------------------------------------------------------------

# Enable automatic software update check
run defaults write com.apple.SoftwareUpdate AutomaticCheckEnabled -bool true

# Check software updates daily
run defaults write com.apple.SoftwareUpdate ScheduleFrequency -int 1

# Install system data files & security updates
run defaults write com.apple.SoftwareUpdate CriticalUpdateInstall -int 1

# Turn on app auto-update
run defaults write com.apple.commerce AutoUpdate -bool true

# ------------------------------------------------------------------------------------------------
# Dock (com.apple.dock)
# ------------------------------------------------------------------------------------------------

# Display dock on left side of the screen
# https://macos-defaults.com/dock/orientation.html
run defaults write com.apple.dock orientation -string "left"

# Auto-hide dock
# https://macos-defaults.com/dock/autohide.html
run defaults write com.apple.dock autohide -bool true

# Remove delay between mouse-over and display of the hidden Dock. Default delay is 0.2
# https://macos-defaults.com/dock/autohide-delay.html
run defaults write com.apple.dock autohide-delay -float 0

# Decrease animation time of Dock auto-hide (and show). Default is 0.5
# https://macos-defaults.com/dock/autohide-time-modifier.html
run defaults write com.apple.dock autohide-time-modifier -float 0.25

# Set dock icon size
# https://macos-defaults.com/dock/tilesize.html
run defaults write com.apple.dock tilesize -int 64

# Enable dock magnification on hover
run defaults write com.apple.dock magnification -int 1

# Set dock magnification level
run defaults write com.apple.dock largesize -float 64

# Keep the launch animation (bouncing icon) when opening apps from the dock enabled; 1 is the macOS default
run defaults write com.apple.dock launchanim -int 1

# Show recently used apps in a separate section of the Dock
# https://macos-defaults.com/dock/show-recents.html
run defaults write com.apple.dock show-recents -bool false

# Set Dock minimize animation to "suck" (hidden value, not available in System Preferences)
# https://macos-defaults.com/dock/mineffect.html
run defaults write com.apple.dock mineffect -string "suck"

# Speed up Mission Control animations
run defaults write com.apple.dock expose-animation-duration -float 0.1

# Disable automatic rearranging of spaces by most recent
run defaults write com.apple.dock mru-spaces -bool false

# Make dock icons of hidden applications translucent
run defaults write com.apple.dock showhidden -string "true"

# Set bottom left screen hot corner to sleep display (corner)
run defaults write com.apple.dock wvous-bl-corner -int 10

# Set bottom left screen hot corner to sleep display (modifier)
run defaults write com.apple.dock wvous-bl-modifier -int 0

# Set top right screen hot corner to show desktop (corner)
run defaults write com.apple.dock wvous-tr-corner -int 4

# Set top right screen hot corner to show desktop (modifier)
run defaults write com.apple.dock wvous-tr-modifier -int 0

# ------------------------------------------------------------------------------------------------
# Finder
# ------------------------------------------------------------------------------------------------

# Show hidden files in Finder
# https://macos-defaults.com/finder/appleshowallfiles.html
run defaults write com.apple.finder AppleShowAllFiles -bool true

# Do not force all file extensions to be shown in Finder: extensions of unknown file types stay hidden (macOS default)
# https://macos-defaults.com/finder/appleshowallextensions.html
run defaults write NSGlobalDomain AppleShowAllExtensions -bool false

# Keep folders on top when sorting by name
# https://macos-defaults.com/finder/_fxsortfoldersfirst.html
run defaults write com.apple.finder _FXSortFoldersFirst -bool true

# Disable warning when changing a file extension
run defaults write com.apple.finder FXEnableExtensionChangeWarning -bool false

# Show status bar in Finder
run defaults write com.apple.finder ShowStatusBar -bool true

# Show path bar in Finder
# https://macos-defaults.com/finder/showpathbar.html
run defaults write com.apple.finder ShowPathbar -bool true

# Use list view in all Finder windows by default
# https://macos-defaults.com/finder/fxpreferredviewstyle.html
run defaults write com.apple.finder FXPreferredViewStyle -string "Nlsv"

# Display full POSIX path in Finder window title
run defaults write com.apple.finder _FXShowPosixPathInTitle -bool true

# Open the home folder in new Finder windows (target type: PfLo = custom folder, given by the path below)
run defaults write com.apple.finder NewWindowTarget -string "PfLo"

# Open the home folder in new Finder windows (target path: the home folder)
run defaults write com.apple.finder NewWindowTargetPath -string "file://${HOME}"

# Show icons for external hard drives on desktop
run defaults write com.apple.finder ShowExternalHardDrivesOnDesktop -bool true

# Show icons for internal hard drives on desktop
run defaults write com.apple.finder ShowHardDrivesOnDesktop -bool true

# Show icons for mounted servers on desktop
run defaults write com.apple.finder ShowMountedServersOnDesktop -bool true

# Show icons for removable media on desktop
run defaults write com.apple.finder ShowRemovableMediaOnDesktop -bool true

# Disable recent tags display in Finder sidebar
run defaults write com.apple.finder ShowRecentTags -int 0

# Disable window and Get Info animations
run defaults write com.apple.finder DisableAllAnimations -bool true

# Disable creating .DS_Store files on network volumes
run defaults write com.apple.finder DSDontWriteNetworkStores -bool true

# Disable creating .DS_Store files on USB volumes
run defaults write com.apple.finder DSDontWriteUSBStores -bool true

# Automatically open new Finder window when a read-only volume is mounted
run defaults write com.apple.frameworks.diskimages auto-open-ro-root -bool true

# Automatically open new Finder window when a read/write volume is mounted
run defaults write com.apple.frameworks.diskimages auto-open-rw-root -bool true

# Automatically open new Finder window when a removable disk is mounted
run defaults write com.apple.finder OpenWindowForNewRemovableDisk -bool true

# Enable spring loading for directories and disable delay
run defaults write NSGlobalDomain com.apple.springing.enabled -bool true

# Show the ~/Library directory (hidden by default)
run chflags nohidden "$HOME/Library"

# Show the /Volumes directory (hidden by default)
run sudo chflags nohidden /Volumes

# ------------------------------------------------------------------------------------------------
# I/O: keyboard, trackpad, scroll (NSGlobalDomain)
# ------------------------------------------------------------------------------------------------

# Disable auto-correct
run defaults write NSGlobalDomain NSAutomaticSpellingCorrectionEnabled -bool false

# Disable auto-capitalization
run defaults write NSGlobalDomain NSAutomaticCapitalizationEnabled -bool false

# Disable smart dashes
run defaults write NSGlobalDomain NSAutomaticDashSubstitutionEnabled -bool false

# Disable smart quotes
run defaults write NSGlobalDomain NSAutomaticQuoteSubstitutionEnabled -bool false

# Disable auto period substitution
run defaults write NSGlobalDomain NSAutomaticPeriodSubstitutionEnabled -bool false

# Disable "natural" (Lion-style) scrolling -- if you like natural scrolling DING DONG UR OPINION IS WRONG
run defaults write NSGlobalDomain com.apple.swipescrolldirection -bool false

# Set keyboard repeat rate to super fast
run defaults write NSGlobalDomain KeyRepeat -int 2

# Set initial keyboard repeat rate to fast, but like... not too fast. Extra medium fast
run defaults write NSGlobalDomain InitialKeyRepeat -int 25

# Enable trackpad tap-to-click
run defaults write NSGlobalDomain com.apple.mouse.tapBehavior -int 1

# Enable full keyboard access for all controls
run defaults write NSGlobalDomain AppleKeyboardUIMode -int 3

# ------------------------------------------------------------------------------------------------
# Mail
#
# com.apple.mail is a sandboxed app container.
# The preference write fails until Mail has created its container.
# Treat as best-effort, rather than aborting the stage.
# ------------------------------------------------------------------------------------------------

# Copy email addresses as `foo@example.com` instead of `Foo Bar <foo@example.com>` in Mail
try defaults write com.apple.mail AddressesIncludeNameOnPasteboard -bool false

# ------------------------------------------------------------------------------------------------
# Messages
#
# com.apple.messageshelper is a sandboxed helper domain.
# May not exist on a fresh machine.
# Treat as best-effort, rather than aborting the stage.
# ------------------------------------------------------------------------------------------------

# Disable smart quotes in Messages
try defaults write com.apple.messageshelper.MessageController SOInputLineSettings \
    -dict-add "automaticQuoteSubstitutionEnabled" -bool false

# Disable continuous spell checking in Messages
try defaults write com.apple.messageshelper.MessageController SOInputLineSettings \
    -dict-add "continuousSpellCheckingEnabled" -bool false

# ------------------------------------------------------------------------------------------------
# Other
# ------------------------------------------------------------------------------------------------

# Show battery percentage in menu bar
run defaults write com.apple.menuextra.battery ShowPercent -string "YES"

# Show audio settings in menu bar
if ! defaults read com.apple.systemuiserver menuExtras 2>/dev/null | grep -q "Volume.menu"; then
    # Idempotent: -array-add would append a duplicate on re-run, so only add if absent.
    run defaults write com.apple.systemuiserver menuExtras \
        -array-add '/System/Library/CoreServices/Menu Extras/Volume.menu'
fi

# Set menu bar date/time format
run defaults write com.apple.menuextra.clock DateFormat -string "EEE d MMM h:mm:ss a"

# Always show expanded options in print menu
run defaults write -g PMPrintingExpandedStateForPrint -bool true

# Change default screenshot storage location to ~/Desktop/Screenshots (ensuring directory exists)
run mkdir -p "${HOME}/Desktop/Screenshots"
run defaults write com.apple.screencapture location -string "${HOME}/Desktop/Screenshots/"

# Increase window resize speed for Cocoa applications
run defaults write NSGlobalDomain NSWindowResizeTime -float 0.001

# Reveal IP address, hostname, OS version (etc) when clicking the clock in login window
run sudo defaults write /Library/Preferences/com.apple.loginwindow AdminHostInfo -string "HostName"

# Prevent iTunes/Music from auto-launching on device connection
run defaults write com.apple.iTunesHelper ignore-devices -int 1

# Prefer tabs when opening documents only in full-screen mode
run defaults write NSGlobalDomain AppleWindowTabbingMode -string fullscreen

# Restart affected services.
run killall Dock || true
run killall Finder || true
run killall SystemUIServer || true

log "macos OK"
