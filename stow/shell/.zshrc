# =====================================================================================================================
# Modular zsh configuration loader
#
# Configuration is split into numbered fragments under ~/.config/zsh/conf.d/, sourced in sorted
# (numeric-prefix) order. Fragments are merged here by GNU Stow from multiple packages: the shell
# package owns the generic scaffolding (00-lib, 00-path, 10-omz, 20-completion, 40-aliases,
# 50-directories, 35-tools-misc), and each tool package contributes its own snippet
# (e.g. stow/git/.config/zsh/conf.d/40-git.zsh, stow/starship/.config/zsh/conf.d/80-starship.zsh).
#
# Numeric bands encode load order: 00 lib/path -> 05 homebrew -> 10 omz -> 20 completion ->
# 30-49 tools -> 50 directories -> 60 ssh aliases -> 80 starship -> 90 banner.
#
# 00-lib.zsh defines shared helper functions (pathadd, fpathadd, source_if_exists, cached_eval) used by later
# fragments.
#
# To add a tool: create NN-<tool>.zsh in that tool's stow package under .config/zsh/conf.d/.
#
# ~/.zshrc.local (untracked, machine-local) is sourced after every fragment.
# =====================================================================================================================

ZSH_CONF_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/zsh/conf.d"
if [[ -d "$ZSH_CONF_DIR" ]]; then
    for _frag in "$ZSH_CONF_DIR"/*.zsh(N); do
        source "$_frag"
    done
    unset _frag
fi

# Machine-local, untracked additions (sourced last)
if [[ -r "$HOME/.zshrc.local" ]]; then
    source "$HOME/.zshrc.local"
fi
