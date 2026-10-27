# =============================================================================
# Oh-My-Zsh
# =============================================================================

# Path to oh-my-zsh installation
export ZSH="$HOME/.oh-my-zsh"

# oh-my-zsh plugins
plugins=(
    # keep-sorted start
    alias-tips
    aliases
    # aws
    # brew                  # `bl` alias conflicts with a `bl` function from an overlay snippet
    # chezmoi
    colored-man-pages
    cp
    direnv
    docker-compose
    extract
    gh
    git
    git-extras
    iterm2
    pip
    pre-commit
    python
    sublime
    sudo
    tailscale
    vscode
    # keep-sorted end
)

# oh-my-zsh update configuration (read while oh-my-zsh.sh loads, so it must precede the source below)
zstyle ':omz:update' mode auto      # update automatically without asking
zstyle ':omz:update' frequency 3    # update every 3 days

# Load oh-my-zsh; skipped silently when absent so an empty HOME starts clean (bootstrap step 95-dotfiles installs it)
source_if_exists "${ZSH}/oh-my-zsh.sh"
