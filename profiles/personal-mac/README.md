[Project Root](../../README.md) > [Profiles](../README.md) > **personal-mac**

# personal-mac

Overlay for the personal MacBook: applications and Claude Code settings that should not apply to other machines. It
follows the [overlay contract](../../bootstrap/README.md#overlay-contract).

## Contents

| File                                       | Purpose                                                                                                                                                                          |
| ------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`bootstrap/Brewfile`](bootstrap/Brewfile) | Casks and Mac App Store apps, applied by `50-brew` after the base [`Brewfile`](../../bootstrap/Brewfile)                                                                         |
| [`render/claude.json`](render/claude.json) | Claude Code settings merged after the base fragment: pins `model`, adds the iTerm2 `cc-status` hooks, and leaves `tui` to the app (`$unmanaged`) so `/tui` never counts as drift |

The profile Brewfile lists only what the base Brewfile does not already install; a unit test fails if an entry is
repeated.

## Registering the overlay

Run from the repository root. This creates the registry directory if needed and appends the profile to the overlays
registry read by the bootstrap driver, unless that exact line is already there, so repeating it is harmless. The
location honours `DOTFILES_OVERLAYS_FILE`, then `$XDG_CONFIG_HOME/dotfiles/overlays`, defaulting to
`~/.config/dotfiles/overlays` (the same resolution as `dotfiles_overlays_file` in
[`bootstrap/lib.sh`](../../bootstrap/lib.sh)):

```bash
f="${DOTFILES_OVERLAYS_FILE:-${XDG_CONFIG_HOME:-$HOME/.config}/dotfiles/overlays}"
p="$PWD/profiles/personal-mac"
mkdir -p "$(dirname "$f")"
grep -qxF "$p" "$f" 2>/dev/null || echo "$p" >> "$f"
```

The driver aborts if the registry lists the same layer twice. It compares resolved paths, so a second line naming this
directory another way (`~/...`, or through a symlink) also counts; the check above only skips an identical line.

Verify the layer order (base first, then this profile):

```bash
bash -c 'source bootstrap/lib.sh; manifest_files Brewfile'
```
