include:
  - .brew
  - .hammerspoon
  - .iterm2
  - .mac_prefs
  - .ssh

# We installed fzf with brew, but now we need to actually install it with the install script
install_fzf:
  cmd.run:
    - name: $(brew --prefix)/opt/fzf/install --all --no-zsh
    - runas: {{ grains.user }}
    - onlyif: "test ! -e /Users/connormason/.fzf.bash"
    - require:
      - brew_bundle_install
