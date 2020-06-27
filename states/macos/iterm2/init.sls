# Symlink iTerm2 config file
symlink_iterm_config:
  file.symlink:
    - name: {{ grains.home }}/Library/Preferences/com.googlecode.iterm2.plist
    - target: {{ grains.states_dir }}/macos/iterm2/com.googlecode.iterm2.plist
    - force: true
    - user: {{ grains.user }}

# Setup iTerm to load preferences from dotfiles
enable_iterm_custom_config:
  macdefaults.write:
    - domain: com.googlecode.iterm2.plist
    - name: LoadPrefsFromCustomFolder
    - value: true
    - vtype: bool
    - user:  {{ grains.user }}
    - require:
      - symlink_iterm_config

setup_iterm_custom_config:
  macdefaults.write:
    - domain: com.googlecode.iterm2.plist
    - name: PrefsCustomFolder
    - value: {{ grains.states_dir }}/macos/iterm2
    - vtype: string
    - user:  {{ grains.user }}
    - require:
      - symlink_iterm_config
