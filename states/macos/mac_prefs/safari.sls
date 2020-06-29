# Show bookmarks bar by default
show_bookmarks_bar:
  macdefaults.write:
    - domain: com.apple.Safari
    - name: ShowFavoritesBar
    - value: true
    - vtype: bool
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

# Allow hitting the Backspace key to go to the previous page in history
backspace_to_go_back:
  macdefaults.write:
    - domain: com.apple.Safari
    - name: com.apple.Safari.ContentPageGroupIdentifier.WebKit2BackspaceKeyNavigationEnabled
    - value: true
    - vtype: bool
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

# Enable the debug menu, develop menu, and the Web Inspector in Safari
enable_debug_menu:
  macdefaults.write:
    - domain: com.apple.Safari
    - name: IncludeInternalDebugMenu
    - value: true
    - vtype: bool
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

enable_develop_menu:
  macdefaults.write:
    - domain: com.apple.Safari
    - name: IncludeDevelopMenu
    - value: true
    - vtype: bool
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

enable_webkit_dev_extras:
  macdefaults.write:
    - domain: com.apple.Safari
    - name: WebKitDeveloperExtrasEnabledPreferenceKey
    - value: true
    - vtype: bool
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

enable_webkit2_dev_extras:
  macdefaults.write:
    - domain: com.apple.Safari
    - name: com.apple.Safari.ContentPageGroupIdentifier.WebKit2DeveloperExtrasEnabled
    - value: true
    - vtype: bool
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

# Update extensions automatically
auto_update_extensions:
  macdefaults.write:
    - domain: com.apple.Safari
    - name: InstallExtensionUpdatesAutomatically
    - value: true
    - vtype: bool
    - user: {{ grains.user }}
    - require:
      - close_system_prefs
