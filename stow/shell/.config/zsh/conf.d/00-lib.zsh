# ================================================================================================
# Shared shell helpers
#
# Generic utility functions, sourced first (00-) so every later conf.d fragment can rely on them.
# Add reusable helpers here; keep tool-specific config in its own fragment.
# ================================================================================================

# Prepend a directory to PATH only if it is not already included
pathadd() {
    if [[ ":$PATH:" != *":$1:"* ]]; then
        export PATH="$1:$PATH"
    fi
}

# Prepend a directory to FPATH only if it is not already included
fpathadd() {
    if [[ ":$FPATH:" != *":$1:"* ]]; then
        export FPATH="$1:$FPATH"
    fi
}

# Source a file only if it exists and is readable
source_if_exists() {
    [[ -r "$1" ]] && source "$1"
}

# Repo root: resolve this snippet's symlink, then climb conf.d/zsh/.config/shell/stow/<repo>
export DOTFILES_REPO="${DOTFILES_REPO:-${${(%):-%x}:A:h:h:h:h:h:h}}"
