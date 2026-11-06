# =====================================================================================================
# yazi (https://yazi-rs.github.io)
# =====================================================================================================

# `y` launches yazi and, on quit, changes the shell's directory to the one last browsed
if (( $+commands[yazi] )); then
    function y() {
        local tmp cwd
        tmp="$(mktemp -t "yazi-cwd.XXXXXX")"
        command yazi "$@" --cwd-file="$tmp"
        IFS= read -r -d '' cwd < "$tmp"
        [[ -n "$cwd" && "$cwd" != "$PWD" && -d "$cwd" ]] && builtin cd -- "$cwd"
        rm -f -- "$tmp"
    }
fi
