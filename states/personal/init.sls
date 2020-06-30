# Symlink .personalrc
symlink_personalrc:
    file.symlink:
    - name: {{ grains.home }}/.rc_files/personalrc
    - target: {{ grains.states_dir }}/personal/personalrc
    - force: True
    - user: {{ grains.user }}
    - require:
      - pkg: zsh
