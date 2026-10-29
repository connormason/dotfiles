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

# oh-my-zsh runs its own full compinit (compaudit, plus a dump it deletes whenever its metadata changes) on every
# start; 20-completion's cached compinit is the only one wanted. oh-my-zsh has no switch to skip it (ZSH_DISABLE_COMPFIX
# only swaps `-i` for `-u`), so a no-op stands in for compinit while it loads. Plugins call `compdef` at load time, and
# only compinit defines it, so those calls are queued here and replayed by 20-completion once compinit has run. The
# dump oh-my-zsh keeps for its metadata check holds no completions; it moves out of $HOME into the cache directory.
typeset -ga _omz_deferred_compdefs=()
compinit() { : }
compdef() { _omz_deferred_compdefs+=("${(j: :)${(@q)@}}") }
: "${ZSH_COMPDUMP:=${XDG_CACHE_HOME:-$HOME/.cache}/zsh/omz-compdump}"

# Load oh-my-zsh; skipped silently when absent so an empty HOME starts clean (bootstrap step 95-dotfiles installs it).
# The always block removes the stubs even when oh-my-zsh aborts mid-load, so a failure cannot leave compinit a no-op.
{
    source_if_exists "${ZSH}/oh-my-zsh.sh"
} always {
    unfunction compinit compdef
    autoload -Uz compinit
}
