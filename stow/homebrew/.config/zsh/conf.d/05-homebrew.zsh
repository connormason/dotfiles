# =============================================================================
# Homebrew (https://brew.sh)
# =============================================================================

# Activate `brew` shell configuration (exports HOMEBREW_PREFIX, extends PATH, MANPATH, and INFOPATH)
# A fresh machine has `brew` on PATH once the Homebrew installer's ~/.zprofile entry is in place
if (( $+commands[brew] )); then
    # `brew shellenv` costs ~40 ms per shell (it spawns path_helper), so cache its output and refresh it only when the
    # brew script itself changes; delete the cache file to force a refresh
    _brew_env="${XDG_CACHE_HOME:-$HOME/.cache}/zsh/brew-shellenv.zsh"
    if [[ ! -s "$_brew_env" || "$_brew_env" -ot "${commands[brew]}" ]]; then
        mkdir -p "${_brew_env:h}" 2>/dev/null && brew shellenv >| "$_brew_env" 2>/dev/null
    fi
    if [[ -s "$_brew_env" ]]; then
        source "$_brew_env"
    else
        eval "$(brew shellenv)"
    fi
    unset _brew_env

    # export HOMEBREW_NO_ENV_HINTS=1

    # Add zsh completions to FPATH for packages installed with `brew`
    fpathadd "$HOMEBREW_PREFIX/share/zsh-completions"
fi
