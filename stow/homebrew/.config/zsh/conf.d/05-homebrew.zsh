# =============================================================================
# Homebrew (https://brew.sh)
# =============================================================================

# Equivalent of `eval "$(brew shellenv)"` without the subprocess (`brew` costs ~40 ms per shell). `brew` is often not on
# PATH yet in a fresh shell, so when it is missing, probe $DOTFILES_BREW_PREFIXES (space-separated, set by a layer's
# bootstrap/env.sh), then /opt/homebrew and /usr/local, and prepend the first prefix that has bin/brew.
# Set DOTFILES_BREW_PROBE=0 to skip the probe (only a `brew` already on PATH is used).
_brew_prefix=""
if (( $+commands[brew] )); then
    _brew_prefix="${commands[brew]:h:h}"
elif [[ "${DOTFILES_BREW_PROBE:-1}" != 0 ]]; then
    for _prefix in ${=DOTFILES_BREW_PREFIXES:-} /opt/homebrew /usr/local; do
        if [[ -x "$_prefix/bin/brew" ]]; then
            _brew_prefix="$_prefix"
            break
        fi
    done
    unset _prefix
fi

if [[ -n "$_brew_prefix" ]]; then
    export HOMEBREW_PREFIX="$_brew_prefix"
    export HOMEBREW_CELLAR="$_brew_prefix/Cellar"
    # Intel macOS and Linux keep the git checkout in $prefix/Homebrew; Apple Silicon uses the prefix itself
    if [[ -d "$_brew_prefix/Homebrew" ]]; then
        export HOMEBREW_REPOSITORY="$_brew_prefix/Homebrew"
    else
        export HOMEBREW_REPOSITORY="$_brew_prefix"
    fi

    pathadd "$_brew_prefix/sbin"
    pathadd "$_brew_prefix/bin"
    fpath=("$_brew_prefix/share/zsh/site-functions" $fpath)
    export INFOPATH="$_brew_prefix/share/info:${INFOPATH:-}"
    # A leading colon in MANPATH keeps the system default man directories searched, as `brew shellenv` does
    if [[ -n "${MANPATH-}" ]]; then
        export MANPATH=":${MANPATH#:}"
    fi

    # export HOMEBREW_NO_ENV_HINTS=1

    # Add zsh completions to FPATH for packages installed with `brew`
    fpathadd "$_brew_prefix/share/zsh-completions"
fi
unset _brew_prefix
