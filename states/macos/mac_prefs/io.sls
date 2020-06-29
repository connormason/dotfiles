# Disable auto-correct, auto capitalization, smart dashes, smart quotes, auto period substitution
disable_auto_spelling_correction:
  macdefaults.write:
    - domain: NSGlobalDomain
    - name: NSAutomaticSpellingCorrectionEnabled
    - value: false
    - vtype: bool
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

disable_auto_capitalization:
  macdefaults.write:
    - domain: NSGlobalDomain
    - name: NSAutomaticCapitalizationEnabled
    - value: false
    - vtype: bool
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

disable_auto_dash_substitution:
  macdefaults.write:
    - domain: NSGlobalDomain
    - name: NSAutomaticDashSubstitutionEnabled
    - value: false
    - vtype: bool
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

disable_auto_quote_substitution:
  macdefaults.write:
    - domain: NSGlobalDomain
    - name: NSAutomaticQuoteSubstitutionEnabled
    - value: false
    - vtype: bool
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

disable_auto_period_substitution:
  macdefaults.write:
    - domain: NSGlobalDomain
    - name: NSAutomaticPeriodSubstitutionEnabled
    - value: false
    - vtype: bool
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

# Disable “natural” (Lion-style) scrolling
disable_natural_scrolling:
  macdefaults.write:
    - domain: NSGlobalDomain
    - name: com.apple.swipescrolldirection
    - value: false
    - vtype: bool
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

# Set keyboard repeat rate to be super fast
fast_keyboard_repeat_rate:
  macdefaults.write:
    - domain: NSGlobalDomain
    - name: KeyRepeat
    - value: 5
    - vtype: int
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

fast_keyboard_initial_repeat_rate:
  macdefaults.write:
    - domain: NSGlobalDomain
    - name: InitialKeyRepeat
    - value: 10
    - vtype: int
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

# Enable trackpad tap-to-click for this user and the login screen
tap_to_click:
  macdefaults.write:
    - domain: NSGlobalDomain
    - name: com.apple.mouse.tapBehavior
    - value: 1
    - vtype: int
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

# Enable full keyboard access for all controls
# (e.g. enable Tab in modal dialogs)
full_keyboard_access:
  macdefaults.write:
    - domain: NSGlobalDomain
    - name: AppleKeyboardUIMode
    - value: 3
    - vtype: int
    - user: {{ grains.user }}
    - require:
      - close_system_prefs
