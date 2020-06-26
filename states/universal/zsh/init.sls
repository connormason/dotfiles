Change default shell to zsh:
  module.run:
    - name: user.chshell
    - m_name: {{ grains.user }}
    - shell: /usr/local/bin/zsh

Symlink zsh config:
  file.symlink:
    - name: {{ grains.home }}/.zshrc
    - target: {{ grains.states_dir }}/universal/zsh/zshrc
    - force: True
    - user: {{ grains.user }}
