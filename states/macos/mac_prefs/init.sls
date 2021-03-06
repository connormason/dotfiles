# Close any open System Preferences panes, to prevent them from overriding settings we’re about to change
close_system_prefs:
  cmd.run:
    - name: osascript -e 'tell application "System Preferences" to quit'
    - runas: {{ grains.user }}

include:
  - .activity_monitor
  - .app_store
  - .dock
  - .finder
  - .io
  - .mail
  - .messages
  - .other
  - .safari
