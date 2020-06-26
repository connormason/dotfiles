Change default shell to zsh:
  module.run:
    - name: user.chshell
    - m_name: {{ grains.user }}
    - shell: /usr/bin/zsh
