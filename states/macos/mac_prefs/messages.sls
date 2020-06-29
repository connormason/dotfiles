# Disable smart quotes as it’s annoying for messages that contain code
disable_smart_quotes:
  cmd.run:
    - name: 'defaults write com.apple.messageshelper.MessageController SOInputLineSettings -dict-add "automaticQuoteSubstitutionEnabled" -bool false'
    - runas: {{ grains.user }}
    - require:
      - close_system_prefs

# Disable continuous spell checking
disable_continuous_spell_checking:
  cmd.run:
    - name: 'defaults write com.apple.messageshelper.MessageController SOInputLineSettings -dict-add "continuousSpellCheckingEnabled" -bool false'
    - runas: {{ grains.user }}
    - require:
      - close_system_prefs
