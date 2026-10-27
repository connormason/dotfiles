# =======================================================================================
# zsh completions -- configured to a fairly close approximation of fish shell
# =======================================================================================

fpath=(/usr/local/share/zsh-completions $fpath)                                 # Must come before `compinit`
fpath+=~/.zfunc

autoload -Uz compinit && compinit                                               # Must come before all `zstyle` calls

# Force zsh not to show completion menu, which allows fzf-tab to capture the unambiguous prefix
zstyle ':completion:*' menu no

# Use LS_COLORS to colorize filename completions
zstyle ':completion:*' list-colors "${(s.:.)LS_COLORS}"

# Preview directory contents when tab-completing into a dir
zstyle ':fzf-tab:complete:cd:*' fzf-preview 'eza -1 --color=always --icons $realpath'

# Don't sort by default for some commands where order matters (e.g. git log, history)
zstyle ':completion:*:git-checkout:*' sort false
zstyle ':completion:*:descriptions' format '[%d]'

# Group completions by category with headers (fish does this for things like git subcommands)
zstyle ':completion:*' group-name ''

# Use fzf's native multi-select / popup behavior instead of plain menu
zstyle ':fzf-tab:*' fzf-command fzf
zstyle ':fzf-tab:*' switch-group ',' '.'

# Make fzf-tab continuous (tab again to keep narrowing without re-triggering)
zstyle ':fzf-tab:*' continuous-trigger 'tab'

# =======================================================================================
# zsh-histdb (https://github.com/larkery/zsh-histdb)
# =======================================================================================

HISTDB_TABULATE_CMD=(sed -e $'s/\x1f/\t/g')    # https://github.com/larkery/zsh-histdb#note-for-os-x-users

source_if_exists "$HOME/.oh-my-zsh/custom/plugins/zsh-histdb/sqlite-history.zsh"
autoload -Uz add-zsh-hook

# Homebrew-installed plugins below; HOMEBREW_PREFIX (set by `brew shellenv`) avoids a `brew --prefix` subprocess
_brew_prefix="${HOMEBREW_PREFIX:-}"
if [[ -z "$_brew_prefix" ]] && (( $+commands[brew] )); then
    _brew_prefix="$(brew --prefix)"
fi

# =======================================================================================
# zsh-autosuggestions (https://github.com/zsh-users/zsh-autosuggestions)
# Fish shell-like auto-suggestions, displayed as dim text to the right of cursor
# =======================================================================================

[[ -n "$_brew_prefix" ]] && source_if_exists "$_brew_prefix/share/zsh-autosuggestions/zsh-autosuggestions.zsh"

# Configure zsh auto-completions to find the most frequently issued command in the current directory or any subdirectory
# _zsh_autosuggest_strategy_histdb_top_here() {
#     local query="select commands.argv from
# history left join commands on history.command_id = commands.rowid
# left join places on history.place_id = places.rowid
# where places.dir LIKE '$(sql_escape $PWD)%'
# and commands.argv LIKE '$(sql_escape $1)%'
# group by commands.argv order by count(*) desc limit 1"
#     suggestion=$(_histdb_query "$query")
# }

# ZSH_AUTOSUGGEST_STRATEGY=histdb_top_here

# Include history + completions in auto-suggestions
ZSH_AUTOSUGGEST_STRATEGY=(history completion)

# =======================================================================================
# fzf-tab (https://github.com/Aloxaf/fzf-tab)
# Replace zsh's default completion selection menu with `fzf`
# =======================================================================================

[[ -n "$_brew_prefix" ]] && source_if_exists "$_brew_prefix/share/fzf-tab/fzf-tab.zsh"

# =======================================================================================
# zsh-syntax-highlighting (https://github.com/zsh-users/zsh-syntax-highlighting)
# Fish shell-like syntax highlighting
# Must come after zsh-autosuggestions & fzf-tab
# =======================================================================================

[[ -n "$_brew_prefix" ]] && source_if_exists "$_brew_prefix/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh"
unset _brew_prefix

# =======================================================================================
# zsh alias-tips (https://github.com/djui/alias-tips)
# Suggests configured aliases that could be used in place of entered commands
# =======================================================================================

export ZSH_PLUGINS_ALIAS_TIPS_EXCLUDES="_ py"
