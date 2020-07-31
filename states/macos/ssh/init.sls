# Automatically load keys into ssh-agent and store passphrases in Keychain
automatically_load_ssh_keys:
  file.prepend:
    - name: {{ grains.home }}/.ssh/config
    - text: "Host *\n  AddKeysToAgent yes\n  UseKeychain yes\n  IdentityFile ~/.ssh/id_rsa\n\n"
    - makedirs: True
