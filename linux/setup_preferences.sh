#!/usr/bin/env bash

# Exit when any command fails
set -e

# Ask for the administrator password upfront
echo -e "${YELLOW}Enter your password plz...${NC}"
sudo -v
echo ""

# Enable location services
gsettings set io.elementary.desktop.agent-geoclue2 location-enabled true

# Remember app usage
gsettings set org.gnome.desktop.privacy remember-app-usage true

# Enable automatic deletion of temp/trash files
gsettings set org.gnome.desktop.privacy remove-old-temp-files true
gsettings set org.gnome.desktop.privacy remove-old-trash-files true

# Show hidden files in Files app and file chooser pane
gsettings set io.elementary.files.preferences show-hiddenfiles true
gsettings set org.gtk.Settings.FileChooser show-hidden true

# Enable Night Light (Flux equivalent)
gsettings set org.gnome.settings-daemon.plugins.color night-light-enabled true

# Disable unsafe paste alert in terminal (warns when pasting code with `sudo` in it)
gsettings set io.elementary.terminal.settings unsafe-paste-alert false

# Always show tabs in tab bar
gsettings set io.elementary.terminal.settings tab-bar-behavior 'Always Show Tabs'

# Prefer dark style
gsettings set io.elementary.terminal.settings prefer-dark-style true

# Natural copy and paste
gsettings set io.elementary.terminal.settings natural-copy-paste true

# Allow bold text
gsettings set io.elementary.terminal.settings allow-bold true

# Remember tabs on close
gsettings set io.elementary.terminal.settings remember-tabs true

# Disable event sounds 
gsettings set org.gnome.desktop.sound event-sounds true

# Disable Caps Lock
gsettings set org.gnome.desktop.input-sources xkb-options "['ctrl:nocaps']"

# Disable auto-suspen
gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-ac-type 'nothing'

# Set key repeat to desired level
gsettings set org.gnome.desktop.peripherals.keyboard repeat true
gsettings set org.gnome.desktop.peripherals.keyboard repeat-interval 'uint32 30'
gsettings set org.gnome.desktop.peripherals.keyboard delay 'uint32 250'

# Disable automatic suspend
sudo su
su - -s /bin/bash/ lightdm
dbus-launch gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-ac-type nothing
su - -s /usr/bin/zsh connormason
