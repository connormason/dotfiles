# Symlink hammerspoon config
symlink_hammerspoon_config:
  file.symlink:
    - name: {{ grains.home }}/.hammerspoon/init.lua
    - target: {{ grains.states_dir }}/macos/hammerspoon/init.lua
    - force: True
    - makedirs: True
    - user: {{ grains.user }}
