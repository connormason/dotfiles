# Enable the automatic update check
auto_check_for_updates:
  macdefaults.write:
    - domain: com.apple.SoftwareUpdate
    - name: AutomaticCheckEnabled
    - value: true
    - vtype: bool
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

# Check for software updates daily, not just once per week
check_for_updates_daily:
  macdefaults.write:
    - domain: com.apple.SoftwareUpdate
    - name: ScheduleFrequency
    - value: 1
    - vtype: int
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

# Download newly available updates in background
download_updates_in_background:
  macdefaults.write:
    - domain: com.apple.SoftwareUpdate
    - name: AutomaticDownload
    - value: 1
    - vtype: int
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

# Install System data files & security updates
install_system_and_security_updates:
  macdefaults.write:
    - domain: com.apple.SoftwareUpdate
    - name: CriticalUpdateInstall
    - value: 1
    - vtype: int
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

# Turn on app auto-update
auto_update_apps:
  macdefaults.write:
    - domain: com.apple.commerce
    - name: AutoUpdate
    - value: true
    - vtype: bool
    - user: {{ grains.user }}
    - require:
      - close_system_prefs
