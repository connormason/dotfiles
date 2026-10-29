#!/usr/bin/env bash
# 95-dotfiles: deploy stow packages, then install oh-my-zsh without clobbering .zshrc.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
# shellcheck source=lib.sh disable=SC1091
source "$HERE/lib.sh"

# Deploy every layer's stow packages. --backup-conflicts moves pre-existing real dotfiles (e.g. a default
# .zshrc/.profile) into ~/.dotfiles-backup/ so an unattended run can proceed with the repo's versions as authoritative
# without clobbering the originals. stow.sh prints a concise summary of what changed; pass -v for stow's full log.
#
# Under --dry-run, deliberately bypass run() (which would only echo the command) and invoke stow.sh with -n: it writes
# nothing, so it is safe to execute, and turns the opaque echo into a real preview of what would be backed up and
# linked. On a fresh machine stow is not installed yet (50-brew installs nothing in a dry run), so the preview is
# skipped rather than failing.
log "deploying stow packages"
if [ "${BOOTSTRAP_DRY_RUN}" = "1" ]; then
    if have stow; then
        "$REPO/stow.sh" -n --backup-conflicts
    else
        warn "stow not installed yet; preview skipped"
    fi
else
    run "$REPO/stow.sh" --backup-conflicts
fi

# oh-my-zsh — unattended, keep the stowed .zshrc.
#
# Pin ZSH to the real ~/.oh-my-zsh and reset ZDOTDIR to $HOME for the installer. Some "venv shell"
# tools export ZDOTDIR to an ephemeral temp dir; the upstream installer honors ambient ZSH/ZDOTDIR,
# so without pinning it can clone into the wrong/temporary location, leaving ~/.oh-my-zsh missing
# and every later shell erroring on `source ${ZSH}/oh-my-zsh.sh`.
OMZ_DIR="$HOME/.oh-my-zsh"
OMZ_INSTALLER_URL="https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh"
if [ -f "$OMZ_DIR/oh-my-zsh.sh" ]; then
    log "oh-my-zsh already installed at $OMZ_DIR"
else
    log "installing oh-my-zsh into $OMZ_DIR (--keep-zshrc, unattended)"
    if [ "${BOOTSTRAP_DRY_RUN}" = "1" ]; then
        # shellcheck disable=SC2016  # the command substitution is printed, not run
        run env ZSH="$OMZ_DIR" ZDOTDIR="$HOME" RUNZSH=no KEEP_ZSHRC=yes \
            sh -c '$(curl -fsSL '"$OMZ_INSTALLER_URL"')' "" --unattended --keep-zshrc
    else
        omz_installer="$(curl -fsSL "$OMZ_INSTALLER_URL")" || die "could not download the oh-my-zsh installer"
        run env ZSH="$OMZ_DIR" ZDOTDIR="$HOME" RUNZSH=no KEEP_ZSHRC=yes \
            sh -c "$omz_installer" "" --unattended --keep-zshrc
        [ -f "$OMZ_DIR/oh-my-zsh.sh" ] || die "oh-my-zsh install did not produce $OMZ_DIR/oh-my-zsh.sh"
    fi
fi

# oh-my-zsh custom plugins the shell package uses that do NOT ship with oh-my-zsh: alias-tips (in the 10-omz.zsh
# plugins list) and zsh-histdb (sourced by 20-completion.zsh). fzf-tab comes from the Brewfile instead. Idempotent:
# skip any plugin whose directory already exists. Format: "plugin-name|git-url".
OMZ_CUSTOM_PLUGINS=(
    "alias-tips|https://github.com/djui/alias-tips.git"
    "zsh-histdb|https://github.com/larkery/zsh-histdb"
)
for entry in "${OMZ_CUSTOM_PLUGINS[@]}"; do
    name="${entry%%|*}"
    url="${entry#*|}"
    dest="$OMZ_DIR/custom/plugins/$name"
    if [ -d "$dest" ]; then
        log "omz plugin $name already present"
    else
        log "cloning omz plugin $name into $dest"
        run git clone --depth 1 "$url" "$dest"
    fi
done
log "dotfiles OK"
