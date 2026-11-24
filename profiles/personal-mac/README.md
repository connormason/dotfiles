[Project Root](../../README.md) > [Profiles](../README.md) > **personal-mac**

# personal-mac

Overlay for the personal MacBook: applications and Claude Code settings that should not apply to other machines. It
follows the [overlay contract](../../bootstrap/README.md#overlay-contract).

## Contents

| File                                                     | Purpose                                                                                                                                                                                                                    |
| -------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`bootstrap/Brewfile`](bootstrap/Brewfile)               | Casks and Mac App Store apps, applied by `50-brew` after the base [`Brewfile`](../../bootstrap/Brewfile)                                                                                                                   |
| [`bootstrap/98-nas-music.sh`](bootstrap/98-nas-music.sh) | Stage that sets up the NAS music auto-mount (see [NAS music share](#nas-music-share))                                                                                                                                      |
| [`stow/nas-music/`](stow/nas-music)                      | macOS-only stow package: `~/.local/bin/nas-music-mount` and its LaunchAgent plist                                                                                                                                          |
| [`render/claude.json`](render/claude.json)               | Claude Code settings merged after the base fragment: pins `model`, enables the official-marketplace plugins, adds the iTerm2 `cc-status` hooks, and leaves `tui` to the app (`$unmanaged`) so `/tui` never counts as drift |

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

## NAS music share

Keeps the NAS `media` share (the `samba` role exports `/storage` under that name) mounted at `/Volumes/media`, so a
Serato library can point at `/Volumes/media/media/music` and every track keeps the same absolute path.

How it fits together:

- The `nas-music` stow package links `~/.local/bin/nas-music-mount` and the `com.connormason.nas-music-mount`
  LaunchAgent. The agent runs the script at login and every 5 minutes. The script exits silently when the share is
  mounted or the NAS is unreachable (away from home), so it also recovers after sleep, Wi-Fi changes, and NAS reboots.
- Stage `98-nas-music` runs after `95-dotfiles` has linked the package. It writes `~/.config/nas-music/mount.conf`
  (untracked), offers to store the share password in the login Keychain (typed into `security`'s own prompt, so it never
  reaches the repo, the shell history, or argv), and loads the agent with `launchctl bootstrap gui/<uid>`.
- The script never calls `mount volume` without a Keychain entry, because that would raise a credentials dialog every 5
  minutes.

Set it up, after registering the overlay as above:

```bash
bootstrap/bootstrap.sh --from 95-dotfiles        # or: --only 98-nas-music once the package is linked
```

The stage prompts for the host (default `nas.local`), share (default `media`), and NAS user. An unattended run skips the
stage unless `NAS_MUSIC_USER` is set (`NAS_MUSIC_HOST` and `NAS_MUSIC_SHARE` override the defaults). Config file values
win over the environment, and re-running keeps an existing config and Keychain entry.

| Command / file                       | Effect                                                               |
| ------------------------------------ | -------------------------------------------------------------------- |
| `nas-music-mount --status`           | Print whether the share is mounted (exit 0) or not (exit 1)          |
| `nas-music-mount --unmount`          | `diskutil unmount` the share; the agent remounts it within 5 minutes |
| `~/Library/Logs/nas-music-mount.log` | Mount successes and failures (an unreachable NAS is not logged)      |

To stop the auto-mount, boot the agent out first, then unmount:

```bash
launchctl bootout "gui/$(id -u)/com.connormason.nas-music-mount"
nas-music-mount --unmount
```

Serato notes: the first mount may show a one-time Keychain access dialog (choose Always Allow). If the share ever
appears as `/Volumes/media-1` (a stale mount was still present), Serato reports every track as missing; eject the stale
volume and let the agent remount it. For gigs, copy the night's crates to the internal drive or an SSD rather than
playing from the network.
