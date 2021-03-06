# Ensure zsh is installed
zsh:
  pkg:
    - installed
    - name: zsh

# Set zsh as the default shell
set_zsh_as_default_shell:
  cmd.run:
    - name: user.chshell
    - m_name: {{ grains.user }}
    - shell: /usr/local/bin/zsh
    - onlyif: "test $(echo $0 | cut -c 2-) = 'zsh'"
    - require:
      - pkg: zsh

# Clone oh-my-zsh
clone_oh_my_zsh:
  git.latest:
    - name: https://github.com/robbyrussell/oh-my-zsh.git
    - rev: master
    - target: {{ grains.home }}/.oh-my-zsh
    - require:
      - pkg: zsh

# Install powerlevel10k oh-my-zsh theme
install_powerlevel10k_theme:
  git.latest:
    - name: https://github.com/romkatv/powerlevel10k.git
    - rev: master
    - target: {{ grains.home }}/.oh-my-zsh/themes/powerlevel10k
    - require:
      - pkg: zsh
      - clone_oh_my_zsh

# Symlink powerlevel10k theme config
symlink_powerlevel10k_config:
    file.symlink:
    - name: {{ grains.home }}/.p10k.zsh
    - target: {{ grains.states_dir }}/universal/zsh/p10k.zsh
    - force: True
    - user: {{ grains.user }}
    - require:
      - pkg: zsh
      - install_powerlevel10k_theme

# Create ~/.rc_files directory to support environment-dependent shell configurations
create_rc_files_dir:
  file.directory:
    - name: {{ grains.home }}/.rc_files
    - dir_mode: 755
    - user: {{ grains.user }}
    - require:
      - pkg: zsh

# Symlink .zshrc to home directory
symlink_zsh_config:
  file.symlink:
    - name: {{ grains.home }}/.zshrc
    - target: {{ grains.states_dir }}/universal/zsh/zshrc
    - force: True
    - user: {{ grains.user }}
    - require:
      - pkg: zsh
      - create_rc_files_dir
      - symlink_powerlevel10k_config  # It will still work without this probably, but it won't be in the desired state
