#!/usr/bin/env bash
# Stow the base layer's packages, then every registered overlay's, into $HOME.
#
# Usage: stow.sh [-n|--simulate] [-v|--verbose] [--summary|--no-summary] [--backup-conflicts] [--list] [PACKAGE...]
#
#   Layers     <repo>/stow, then <overlay>/stow for each overlay in the registry (bootstrap/lib.sh: dotfiles_layers)
#   Packages   every directory in a layer's stow/; a package name may exist in only one layer
#   Ownership  no two packages may provide the same $HOME-relative path; checked before anything is linked
#   Folding    always --no-folding: $HOME directories stay real, so several packages (and apps' runtime state) can
#              share them, and nothing an app writes lands inside a repository
#
# Env: STOW_VERBOSE=N raises stow's verbosity and prints its raw log.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
SUMMARIZER="$REPO_DIR/scripts/utility/summarize_stow.awk"
# shellcheck source=/dev/null  # lib.sh is sourced at runtime from the repo root; shellcheck runs without -x
source "$REPO_DIR/bootstrap/lib.sh"

DRY=()
DRY_RUN=0
PASSTHRU=()
SHOW_RAW=0
SHOW_SUMMARY=1
BACKUP_CONFLICTS=0
LIST_ONLY=0
LEVEL="${STOW_VERBOSE:-0}"
if [ "$LEVEL" -gt 0 ]; then
    SHOW_RAW=1
fi
WANT=()
for arg in "$@"; do
    case "$arg" in
    -n | --no | --simulate) DRY=(-n) DRY_RUN=1 ;;
    -v | --verbose)
        SHOW_RAW=1
        [ "$LEVEL" -ge 1 ] || LEVEL=1
        ;;
    --summary) SHOW_SUMMARY=1 ;;
    --no-summary) SHOW_SUMMARY=0 ;;
    --backup-conflicts) BACKUP_CONFLICTS=1 ;;
    --list) LIST_ONLY=1 ;;
    -h | --help)
        sed -n '2,/^set -euo pipefail/p' "$0" | sed -e '$d' -e 's/^# \{0,1\}//'
        exit 0
        ;;
    -*) PASSTHRU+=("$arg") ;;
    *) WANT+=("$arg") ;;
    esac
done

# ---------------------------------------------------------------------------------------------------------------------
# Discovery: parallel arrays (bash 3.2 has no associative arrays)
# ---------------------------------------------------------------------------------------------------------------------
PKG_NAMES=()
PKG_LAYERS=()

pkg_index() { # print the index of package $1, or return 1
    local i
    for i in ${PKG_NAMES[@]+"${!PKG_NAMES[@]}"}; do
        if [ "${PKG_NAMES[$i]}" = "$1" ]; then
            printf '%s\n' "$i"
            return 0
        fi
    done
    return 1
}

LAYERS_OUT="$(dotfiles_layers)" || exit 1
while IFS= read -r layer; do
    if [ ! -d "$layer/stow" ]; then
        continue
    fi
    for dir in "$layer"/stow/*/; do
        if [ ! -d "$dir" ]; then
            continue
        fi
        pkg="$(basename "$dir")"
        if idx="$(pkg_index "$pkg")"; then
            die "package '$pkg' is defined in two layers: ${PKG_LAYERS[$idx]} and $layer"
        fi
        PKG_NAMES+=("$pkg")
        PKG_LAYERS+=("$layer")
    done
done <<EOF
$LAYERS_OUT
EOF

if [ "$LIST_ONLY" = 1 ]; then
    for i in ${PKG_NAMES[@]+"${!PKG_NAMES[@]}"}; do
        printf '%s\t%s\n' "${PKG_NAMES[$i]}" "${PKG_LAYERS[$i]}"
    done
    exit 0
fi

if [ ${#PKG_NAMES[@]} -eq 0 ]; then
    echo "stow: no packages found"
    exit 0
fi

SEL=()
if [ ${#WANT[@]} -eq 0 ]; then
    SEL=("${!PKG_NAMES[@]}")
else
    for pkg in "${WANT[@]}"; do
        idx="$(pkg_index "$pkg")" || die "unknown package: $pkg"
        SEL+=("$idx")
    done
fi

SEL_NAMES=()
for i in "${SEL[@]}"; do
    SEL_NAMES+=("${PKG_NAMES[$i]}")
done

# ---------------------------------------------------------------------------------------------------------------------
# Ownership: every $HOME-relative path belongs to exactly one package (across all packages, not just selected ones)
# ---------------------------------------------------------------------------------------------------------------------
package_files() { # $1=index: $HOME-relative paths the package provides, honoring stow's default ignores
    (
        cd "${PKG_LAYERS[$1]}/stow/${PKG_NAMES[$1]}" &&
            find . \( -name .git -o -name .DS_Store -o -name .gitignore \) -prune -o \( -type f -o -type l \) -print |
            sed 's|^\./||' | grep -v -E '^(README|LICENSE|COPYING)([.][^/]*)?$' || true
    )
}

OWNERS="$(
    for i in "${!PKG_NAMES[@]}"; do
        package_files "$i" | awk -v pkg="${PKG_NAMES[$i]}" '{ print $0 "\t" pkg }'
    done
)"
DUPES="$(printf '%s\n' "$OWNERS" | cut -f1 | LC_ALL=C sort | uniq -d | sed '/^$/d')"
if [ -n "$DUPES" ]; then
    echo "stow: these paths are provided by more than one package:" >&2
    while IFS= read -r path; do
        owners="$(printf '%s\n' "$OWNERS" | awk -F'\t' -v p="$path" '$1 == p { print $2 }' | paste -sd, -)"
        printf '  ~/%s <- %s\n' "$path" "$owners" >&2
    done <<EOF
$DUPES
EOF
    exit 1
fi

selected_in_layer() { # print the selected package names that live in layer $1
    local i
    for i in "${SEL[@]}"; do
        if [ "${PKG_LAYERS[$i]}" = "$1" ]; then
            printf '%s\n' "${PKG_NAMES[$i]}"
        fi
    done
}

EFF_LEVEL="$LEVEL"
if [ "$SHOW_SUMMARY" = 1 ] && [ "$EFF_LEVEL" -lt 1 ]; then
    EFF_LEVEL=1
fi
VERBOSE=()
if [ "$EFF_LEVEL" -gt 0 ]; then
    VERBOSE=(--verbose="$EFF_LEVEL")
fi

# ---------------------------------------------------------------------------------------------------------------------
# Conflict backup: move blocking regular files / symlinks (never directories) to ~/.dotfiles-backup/<timestamp>/
# ---------------------------------------------------------------------------------------------------------------------
CONFLICTS_FOUND=0
backup_conflicts() {
    local layer pkgs pkg sim conflicts backup_dir target src
    backup_dir="$HOME/.dotfiles-backup/$(date +%Y%m%d-%H%M%S)"
    while IFS= read -r layer; do
        pkgs=()
        while IFS= read -r pkg; do
            if [ -n "$pkg" ]; then
                pkgs+=("$pkg")
            fi
        done <<EOF
$(selected_in_layer "$layer")
EOF
        if [ ${#pkgs[@]} -eq 0 ]; then
            continue
        fi
        sim="$(stow --dir "$layer/stow" --target "$HOME" --no-folding --restow -n "${pkgs[@]}" 2>&1 || true)"
        conflicts="$(printf '%s\n' "$sim" |
            sed -n -e 's/.* over existing target \(.*\) since .*/\1/p' \
                -e 's/.*existing target is neither a link nor a directory: \(.*\)/\1/p')"
        if [ -z "$conflicts" ]; then
            continue
        fi
        CONFLICTS_FOUND=1
        while IFS= read -r target; do
            if [ -z "$target" ]; then
                continue
            fi
            src="$HOME/$target"
            if { [ -e "$src" ] || [ -L "$src" ]; } && [ ! -d "$src" ]; then
                if [ "$DRY_RUN" = 1 ]; then
                    echo "stow: would back up existing $target -> $backup_dir/$target"
                else
                    mkdir -p "$backup_dir/$(dirname "$target")"
                    mv "$src" "$backup_dir/$target"
                    echo "stow: backed up existing $target -> $backup_dir/$target"
                fi
            fi
        done <<EOF
$conflicts
EOF
    done <<EOF
$LAYERS_OUT
EOF
}
if [ "$BACKUP_CONFLICTS" = 1 ]; then
    backup_conflicts
fi

# ---------------------------------------------------------------------------------------------------------------------
# Stow each layer's selected packages
# ---------------------------------------------------------------------------------------------------------------------
STOW_LOG=""
RC=0
while IFS= read -r layer; do
    pkgs=()
    while IFS= read -r pkg; do
        if [ -n "$pkg" ]; then
            pkgs+=("$pkg")
        fi
    done <<EOF
$(selected_in_layer "$layer")
EOF
    if [ ${#pkgs[@]} -eq 0 ]; then
        continue
    fi
    out=""
    layer_rc=0
    out="$(stow --dir "$layer/stow" --target "$HOME" --no-folding --restow \
        ${VERBOSE[@]+"${VERBOSE[@]}"} ${DRY[@]+"${DRY[@]}"} ${PASSTHRU[@]+"${PASSTHRU[@]}"} "${pkgs[@]}" 2>&1)" || layer_rc=$?
    STOW_LOG+="$out"$'\n'
    if [ "$layer_rc" -ne 0 ] && [ "$RC" -eq 0 ]; then
        RC=$layer_rc
    fi
done <<EOF
$LAYERS_OUT
EOF

CONFLICT_ABORT=0
if [ "$RC" -ne 0 ] && [ "$DRY_RUN" = 1 ] && [ "$BACKUP_CONFLICTS" = 1 ] && [ "$CONFLICTS_FOUND" = 1 ]; then
    CONFLICT_ABORT=1 # expected: the preview cannot link over files it did not actually move
    RC=0
fi
if [ "$RC" -ne 0 ]; then
    printf '%s' "$STOW_LOG" >&2
    echo "stow: FAILED (exit $RC) for ${SEL_NAMES[*]}" >&2
    exit "$RC"
fi
if [ "$SHOW_RAW" = 1 ]; then
    printf '%s' "$STOW_LOG" | grep -v '^/' >&2 || true
fi
if [ "$SHOW_SUMMARY" = 1 ] && [ "$CONFLICT_ABORT" = 0 ]; then
    printf '%s' "$STOW_LOG" | awk -v dry="$DRY_RUN" -f "$SUMMARIZER"
fi
if [ "$CONFLICT_ABORT" = 1 ]; then
    echo "stow: simulated ${SEL_NAMES[*]} (dry-run; conflicting files above would be backed up first, then linked)"
elif [ "$DRY_RUN" = 1 ]; then
    echo "stow: simulated ${SEL_NAMES[*]} (dry-run, no changes written)"
else
    echo "stow: applied ${SEL_NAMES[*]}"
fi
