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

Run from the repository root, once. This creates the registry directory if needed and appends the profile to the
overlays registry read by the bootstrap driver. The location honours `DOTFILES_OVERLAYS_FILE`, then
`$XDG_CONFIG_HOME/dotfiles/overlays`, defaulting to `~/.config/dotfiles/overlays` (the same resolution as
`dotfiles_overlays_file` in [`bootstrap/lib.sh`](../../bootstrap/lib.sh)):

```bash
f="${DOTFILES_OVERLAYS_FILE:-${XDG_CONFIG_HOME:-$HOME/.config}/dotfiles/overlays}"
mkdir -p "$(dirname "$f")" && echo "$PWD/profiles/personal-mac" >> "$f"
```

Registering the same layer twice makes the driver abort, so do not repeat the command.

Verify the layer order (base first, then this profile):

```bash
bash -c 'source bootstrap/lib.sh; manifest_files Brewfile'
```
