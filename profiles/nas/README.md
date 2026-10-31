[Project Root](../../README.md) > [Profiles](../README.md) > **nas**

# nas

Overlay for the home NAS (Debian with Linuxbrew). It follows the
[overlay contract](../../bootstrap/README.md#overlay-contract) and contributes nothing yet: the NAS runs the base layer
unchanged, the same dev environment as the Macs. NAS-only stages, `Brewfile` entries, or `repos.txt` lines go here when
they are needed.

## Registration

The NAS [`dotfiles`](../../roles/dotfiles/README.md) Ansible role writes the overlays registry
(`~/.config/dotfiles/overlays`) with this directory as its only entry and owns that file; edits made on the NAS are
overwritten on the next provisioning run.
