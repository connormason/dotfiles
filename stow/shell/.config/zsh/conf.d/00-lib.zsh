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

# Source the output of `BINARY ARGS...` (a tool's `init zsh` / completion script) from a cache instead of running the
# tool on every start. The cache, ${XDG_CACHE_HOME:-$HOME/.cache}/zsh/NAME.zsh, is rewritten (temp file + mv) when it
# is missing or empty, older than the binary, or stamped with a different binary or argument list. The binary path is
# resolved (:A), so a Homebrew upgrade invalidates it even though bottles keep build-time mtimes older than the cache.
# Use it only for output that depends on neither the working directory nor the environment. The cache is sourced from
# this function, so its top-level `local`/`typeset` (without -g) would be function-scoped.
# Returns 1, without output, when BINARY is not installed or the generator fails or prints nothing.
# Usage: cached_eval NAME BINARY [ARGS...]
cached_eval() {
    local name="$1" bin="$2"
    shift 2
    (( $+commands[$bin] )) || return 1
    local exe="${commands[$bin]:A}"
    local cache="${XDG_CACHE_HOME:-$HOME/.cache}/zsh/$name.zsh"
    local stamp="# cached_eval: $exe $*" line=''
    if [[ -s "$cache" && ! "$cache" -ot "$exe" ]] && IFS= read -r line < "$cache" && [[ "$line" == "$stamp" ]]; then
        source "$cache"
        return
    fi

    local output
    output="$("${commands[$bin]}" "$@")" || return 1
    [[ -n "$output" ]] || return 1
    local tmp="$cache.$$.tmp"
    if { command mkdir -p "${cache:h}" && print -r -- "$stamp"$'\n'"$output" >| "$tmp" &&
            command mv -f "$tmp" "$cache"; } 2>/dev/null; then
        source "$cache"
    else
        command rm -f "$tmp" 2>/dev/null    # cache unwritable: initialize without it
        eval "$output"
    fi
}

# Repo root: resolve this snippet's symlink, then climb conf.d/zsh/.config/shell/stow/<repo>
export DOTFILES_REPO="${DOTFILES_REPO:-${${(%):-%x}:A:h:h:h:h:h:h}}"
