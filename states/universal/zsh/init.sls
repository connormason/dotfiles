# Ensure zsh is installed
zsh:
  pkg:
    - installed
    - name: zsh

# Set zsh as the default shell
set_zsh_as_default_shell:
  module.run:
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
    - unless: "test -d {{ grains.home }}/.oh-my-zsh"
    - onlyif: "test -d {{ grains.home }}"
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

# Symlink powerlevel10k theme config
symlink_powerlevel10k_config:
    file.symlink:
    - name: {{ grains.home }}/.p10k.zsh
    - target: {{ grains.states_dir }}/universal/zsh/p10k.zsh
    - force: True
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
