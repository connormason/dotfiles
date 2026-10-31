# =============================================================================
# System info banner (https://github.com/fastfetch-cli/fastfetch)
# =============================================================================

# Print the banner in a top-level shell attached to a terminal when `fastfetch` is installed.
# Piped or redirected shells never see it, and DOTFILES_NO_BANNER=1 suppresses it (automation, tests).
if [[ $SHLVL -eq 1 && -t 1 && -z ${DOTFILES_NO_BANNER-} ]] && (( $+commands[fastfetch] )); then
    if [[ $OSTYPE == darwin* ]]; then
        fastfetch -c archey --logo macOS2
    else
        fastfetch -c archey
    fi
fi
