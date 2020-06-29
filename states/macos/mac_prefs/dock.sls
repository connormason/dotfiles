# Dock on right side of the screen
dock_right:
  macdefaults.write:
    - domain: com.apple.Dock
    - name: orientation
    - value: right
    - vtype: string
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

# Auto-hide dock
dock_autohide:
  macdefaults.write:
    - domain: com.apple.Dock
    - name: autohide
    - value: 1
    - vtype: int
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

# Set dock icon size
dock_icon_size:
  macdefaults.write:
    - domain: com.apple.Dock
    - name: tilesize
    - value: 32
    - vtype: int
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

# Enable magnification on hover
dock_magnification:
  macdefaults.write:
    - domain: com.apple.Dock
    - name: magnification
    - value: 1
    - vtype: int
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

# Set magnification level
dock_magnification_largesize:
  macdefaults.write:
    - domain: com.apple.Dock
    - name: largesize
    - value: 64
    - vtype: int
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

# Don’t animate opening applications from the Dock
dock_dont_animate:
  macdefaults.write:
    - domain: com.apple.Dock
    - name: launchanim
    - value: false
    - vtype: bool
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

# Enable spring loading for all Dock items
dock_spring_loading:
  macdefaults.write:
    - domain: com.apple.Dock
    - name: enable-spring-load-actions-on-all-items
    - value: true
    - vtype: bool
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

# Speed up Mission Control animations
mission_control_speed_up:
  macdefaults.write:
    - domain: com.apple.Dock
    - name: expose-animation-duration
    - value: 0.1
    - vtype: float
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

# Don’t automatically rearrange Spaces based on most recent use
spaces_dont_auto_rearrange:
  macdefaults.write:
    - domain: com.apple.Dock
    - name: mru-spaces
    - value: false
    - vtype: bool
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

# Make Dock icons of hidden applications translucent
dock_hidden_apps_translucent:
  macdefaults.write:
    - domain: com.apple.Dock
    - name: showhidden
    - value: true
    - vtype: bool
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

# Set bottom left screen hot corner to put display to sleep
hot_corner_bottom_left:
  macdefaults.write:
    - domain: com.apple.Dock
    - name: wvous-bl-corner
    - value: 10
    - vtype: int
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

hot_corner_bottom_left_mod:
  macdefaults.write:
    - domain: com.apple.Dock
    - name: wvous-bl-modifier
    - value: 0
    - vtype: int
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

# Set top right screen hot corner to show desktop
hot_corner_top_right:
  macdefaults.write:
    - domain: com.apple.Dock
    - name: wvous-tr-corner
    - value: 4
    - vtype: int
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

hot_corner_top_right_mod:
  macdefaults.write:
    - domain: com.apple.Dock
    - name: wvous-tr-modifier
    - value: 0
    - vtype: int
    - user: {{ grains.user }}
    - require:
      - close_system_prefs
