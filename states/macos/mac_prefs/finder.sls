# Show hidden files by default
show_hidden_files:
  macdefaults.write:
    - domain: com.apple.finder
    - name: AppleShowAllFiles
    - value: true
    - vtype: bool
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

# Show Finder status bar and path bar
show_status_bar:
  macdefaults.write:
    - domain: com.apple.finder
    - name: ShowStatusBar
    - value: true
    - vtype: bool
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

show_path_bar:
  macdefaults.write:
    - domain: com.apple.finder
    - name: ShowPathbar
    - value: true
    - vtype: bool
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

# Display full POSIX path as Finder window title
show_posix_path_in_title:
  macdefaults.write:
    - domain: com.apple.finder
    - name: _FXShowPosixPathInTitle
    - value: true
    - vtype: bool
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

# Disable the warning when changing a file extension
dont_warn_on_extension_change:
  macdefaults.write:
    - domain: com.apple.finder
    - name: FXEnableExtensionChangeWarning
    - value: true
    - vtype: bool
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

# Enable spring loading for directories and disable delay
directory_spring_loading:
  macdefaults.write:
    - domain: NSGlobalDomain
    - name: com.apple.springing.enabled
    - value: true
    - vtype: bool
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

# Set Documents as the default location for new Finder windows
new_window_target:
  macdefaults.write:
    - domain: com.apple.finder
    - name: NewWindowTarget
    - value: PfLo
    - vtype: string
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

new_window_target_path:
  macdefaults.write:
    - domain: com.apple.finder
    - name: NewWindowTargetPath
    - value: file://${HOME}/Documents/
    - vtype: string
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

# Use list view in all Finder windows by default
list_view_by_default:
  macdefaults.write:
    - domain: com.apple.finder
    - name: FXPreferredViewStyle
    - value: Nlsv
    - vtype: string
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

# Show icons for hard drives, servers, and removable media on the desktop
show_external_hard_drives_on_desktop:
  macdefaults.write:
    - domain: com.apple.finder
    - name: ShowExternalHardDrivesOnDesktop
    - value: true
    - vtype: bool
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

show_hard_drives_on_desktop:
  macdefaults.write:
    - domain: com.apple.finder
    - name: ShowHardDrivesOnDesktop
    - value: true
    - vtype: bool
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

show_mounted_servers_on_desktop:
  macdefaults.write:
    - domain: com.apple.finder
    - name: ShowMountedServersOnDesktop
    - value: true
    - vtype: bool
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

show_removable_media_on_desktop:
  macdefaults.write:
    - domain: com.apple.finder
    - name: ShowRemovableMediaOnDesktop
    - value: true
    - vtype: bool
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

# Don't show recent tags in Finder sidebar
dont_show_recent_tags_in_sidebar:
  macdefaults.write:
    - domain: com.apple.finder
    - name: ShowRecentTags
    - value: 0
    - vtype: int
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

# Disable window animations and Get Info animations
disable_window_animations:
  macdefaults.write:
    - domain: com.apple.finder
    - name: DisableAllAnimations
    - value: true
    - vtype: bool
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

# Avoid creating .DS_Store files on network or USB volumes
disable_ds_store_on_network_drives:
  macdefaults.write:
    - domain: com.apple.desktopservices
    - name: DSDontWriteNetworkStores
    - value: true
    - vtype: bool
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

disable_ds_store_on_usb_drives:
  macdefaults.write:
    - domain: com.apple.desktopservices
    - name: DSDontWriteUSBStores
    - value: true
    - vtype: bool
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

# Automatically open a new Finder window when a volume is mounted
auto_open_ro_volumes:
  macdefaults.write:
    - domain: com.apple.frameworks.diskimages
    - name: auto-open-ro-root
    - value: true
    - vtype: bool
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

auto_open_rw_volumes:
  macdefaults.write:
    - domain: com.apple.frameworks.diskimages
    - name: auto-open-rw-root
    - value: true
    - vtype: bool
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

auto_open_removable_disks:
  macdefaults.write:
    - domain: com.apple.finder
    - name: OpenWindowForNewRemovableDisk
    - value: true
    - vtype: bool
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

# Show the ~/Library directory
show_library_directory:
  cmd.run:
    - name: chflags nohidden {{ grains.home }}/Library
    - runas: {{ grains.user }}

# Show the /Volumes directory
show_volumes_directory:
  cmd.run:
    - name: sudo chflags nohidden /Volumes
    - runas: {{ grains.user }}
