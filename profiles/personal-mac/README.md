[Project Root](../../README.md) > [Profiles](../README.md) > **personal-mac**

# personal-mac

Overlay for the personal MacBook: applications that should not be installed on other machines. It follows the
[overlay contract](../../bootstrap/README.md#overlay-contract) and contributes a single manifest fragment.

## Contents

| File                                       | Purpose                                                                                                  |
| ------------------------------------------ | -------------------------------------------------------------------------------------------------------- |
| [`bootstrap/Brewfile`](bootstrap/Brewfile) | Casks and Mac App Store apps, applied by `50-brew` after the base [`Brewfile`](../../bootstrap/Brewfile) |

The profile Brewfile lists only what the base Brewfile does not already install; a unit test fails if an entry is
repeated.

## Registering the overlay

Run from the repository root. This appends the profile to the overlays registry read by the bootstrap driver:

```bash
echo "$PWD/profiles/personal-mac" >> ~/.config/dotfiles/overlays
```

Verify the layer order (base first, then this profile):

```bash
bash -c 'source bootstrap/lib.sh; manifest_files Brewfile'
```
