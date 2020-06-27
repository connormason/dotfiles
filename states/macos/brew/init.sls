# Install packages with homebrew
brew_bundle_install:
  cmd.run:
    - name: brew bundle install
    - cwd: {{ grains.states_dir }}/macos/brew
    - runas: {{ grains.user }}

# Run cleanup
brew_cleanup:
  cmd.run:
    - name: brew cleanup
    - runas: {{ grains.user }}
    - require:
      - brew_bundle_install
