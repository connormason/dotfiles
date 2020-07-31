# Show battery percentage in menu bar
battery_in_menu_bar:
  macdefaults.write:
    - domain: com.apple.menuextra.battery
    - name: ShowPercent
    - value: 'YES'
    - vtype: string
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

# Show audio settings in menu bar
audio_settings_in_menu_bar:
  macdefaults.write:
    - domain: com.apple.systemuiserver
    - name: menuExtras
    - value: '/System/Library/CoreServices/Menu Extras/Volume.menu'
    - vtype: array-add
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

# Set menu bar date format
menu_bar_date_format:
  macdefaults.write:
    - domain: com.apple.menuextra.clock
    - name: DateFormat
    - value: 'EEE d MMM h:mm:ss a'
    - vtype: string
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

# Customize items on right side of touch bar
touch_bar_items_right:
  macdefaults.write:
    - domain: com.apple.controlstrip
    - name: MiniCustomized
    - value: '(com.apple.system.volume, com.apple.system.brightness, com.apple.system.airplay )'
    - vtype: string
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

# Always show expanded options in print menu
expand_print_menu_options:
  cmd.run:
    - name: defaults write -g PMPrintingExpandedStateForPrint -bool TRUE
    - runas: {{ grains.user }}

# Change default screenshot storage location to ~/Desktop/Screenshots
screenshot_storage_dir:
  macdefaults.write:
    - domain: com.apple.screencapture
    - name: location
    - value: {{ grains.home }}/Desktop/Screenshots/
    - vtype: string
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

# Increase window resize speed for Cocoa applications
cocoa_window_resize_speed:
  macdefaults.write:
    - domain: NSGlobalDomain
    - name: NSWindowResizeTime
    - value: 0.001
    - vtype: float
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

# Reveal IP address, hostname, OS version, etc. when clicking the clock in the login window
login_window_info:
  cmd.run:
    - name: sudo defaults write /Library/Preferences/com.apple.loginwindow AdminHostInfo HostName
    - runas: {{ grains.user }}
