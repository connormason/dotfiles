# Copy email addresses as `foo@example.com` instead of `Foo Bar <foo@example.com>` in Mail.app
copy_raw_email_addresses:
  macdefaults.write:
    - domain: com.apple.mail
    - name: AddressesIncludeNameOnPasteboard
    - value: false
    - vtype: bool
    - user: {{ grains.user }}
    - require:
      - close_system_prefs
