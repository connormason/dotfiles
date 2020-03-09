#!/usr/bin/env bash

# Exit when any command fails
set -e

# Enable location services
gsettings set io.elementary.desktop.agent-geoclue2 location-enabled true

# Enable Night Light (Flux equivalent)
gsettings set org.gnome.settings-daemon.plugins.color night-light-enabled true

# System Settings
## Security & Privacy
### History
gsettings set remember-app-usage
gsetting

### Enable automatic deletion of temp/trash files
gsettings set org.gnome.desktop.privacy remove-old-temp-files true
gsettings set org.gnome.desktop.privacy remove-old-trash-files true


# Disable unsafe paste alert in terminal (warns when pasting code with `sudo` in it)
gsettings set io.elementary.terminal.settings unsafe-paste-alert false