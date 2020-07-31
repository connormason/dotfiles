# Symlink .personalrc
symlink_personalrc:
    file.symlink:
    - name: {{ grains.home }}/.rc_files/personalrc
    - target: {{ grains.states_dir }}/personal/personalrc
    - force: True
    - user: {{ grains.user }}

# Symlink .gitconfig
symlink_gitconfig:
    file.symlink:
    - name: {{ grains.home }}/.gitconfig
    - target: {{ grains.states_dir }}/personal/gitconfig
    - force: True
    - user: {{ grains.user }}
