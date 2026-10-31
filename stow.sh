#!/usr/bin/env bash
# Stow the base layer's packages, then every registered overlay's, into $HOME.
#
# Usage: stow.sh [-n|--simulate] [-v|--verbose] [--summary|--no-summary] [--backup-conflicts] [--list] [PACKAGE...]
#
#   Options    only those above and -h|--help; any other option is an error (none is passed through to stow)
#   Layers     <repo>/stow, then <overlay>/stow for each overlay in the registry (bootstrap/lib.sh: dotfiles_layers)
#   Packages   every directory in a layer's stow/; a package name may exist in only one layer
#   OS         a package's optional .dotfiles-os file lists the OS ids it applies to (darwin, linux; one per line, '#'
#              comments); packages without one apply everywhere. Other packages are invisible on this OS
#   Ownership  no two packages may provide the same $HOME-relative path (or a file where another has a directory), and
#              none may provide a file render.py writes (render.py --list-targets) or a path above one; checked before
#              anything is linked
#   Folding    always --no-folding: $HOME directories stay real, so several packages (and apps' runtime state) can
#              share them, and nothing an app writes lands inside a repository
#   Apply      all-or-nothing: every layer is simulated first. Unresolvable conflicts (a real directory where a package
#              provides a file, ...) abort with nothing changed. Blocking regular files and foreign symlinks abort too
#              unless --backup-conflicts moves them to ~/.dotfiles-backup/<timestamp>/ first; the layers are then
#              re-verified and only a clean result is linked. -n previews exactly this, writing nothing.
#
# Env: STOW_VERBOSE=N raises stow's verbosity and prints its raw log.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"

# Help must work even when the overlay registry is broken, so it is handled before lib.sh is sourced.
for arg in "$@"; do
    case "$arg" in
    -h | --help)
        sed -n '2,/^set -euo pipefail/p' "${BASH_SOURCE[0]}" | sed -e '$d' -e 's/^# \{0,1\}//'
        exit 0
        ;;
    esac
done

SUMMARIZER="$REPO_DIR/scripts/utility/summarize_stow.awk"
# Pin the base layer to this checkout: an inherited DOTFILES_REPO from another checkout must not redirect it.
DOTFILES_REPO="$REPO_DIR"
export DOTFILES_REPO
# shellcheck source=/dev/null  # lib.sh is sourced at runtime from the repo root; shellcheck runs without -x
source "$REPO_DIR/bootstrap/lib.sh"

DRY_RUN=0
SHOW_RAW=0
SHOW_SUMMARY=1
BACKUP_CONFLICTS=0
LIST_ONLY=0
LEVEL="${STOW_VERBOSE:-0}"
case "$LEVEL" in
*[!0-9]*) die "STOW_VERBOSE must be a non-negative integer (got '$LEVEL')" ;;
esac
if [ "$LEVEL" -gt 0 ]; then
    SHOW_RAW=1
fi
WANT=()
for arg in "$@"; do
    case "$arg" in
    -n | --simulate) DRY_RUN=1 ;;
    -v | --verbose)
        SHOW_RAW=1
        [ "$LEVEL" -ge 1 ] || LEVEL=1
        ;;
    --summary) SHOW_SUMMARY=1 ;;
    --no-summary) SHOW_SUMMARY=0 ;;
    --backup-conflicts) BACKUP_CONFLICTS=1 ;;
    --list) LIST_ONLY=1 ;;
    -[!-]?*) die "combined short flags are not supported: $arg (pass each flag separately, e.g. -n -v)" ;;
    # Nothing else reaches stow: --adopt would move $HOME content into the repo, --dir/--target would defeat conflict
    # classification, and -D would unlink while reporting "applied"
    -*) die "unknown option: $arg (see stow.sh --help)" ;;
    *) WANT+=("$arg") ;;
    esac
done

CURRENT_OS="$(dotfiles_os)" || exit 1

# package_os_ok DIR -> succeed if the package at DIR applies to CURRENT_OS (see "OS" in the header). Dies on an unknown
# OS id or a marker that lists none.
package_os_ok() {
    local marker="$1/.dotfiles-os" line any=0 found=0
    if [ ! -f "$marker" ]; then
        return 0
    fi
    while IFS= read -r line || [ -n "$line" ]; do
        line="${line%%#*}"
        line="${line//[[:space:]]/}"
        if [ -z "$line" ]; then
            continue
        fi
        case "$line" in
        darwin | linux) ;;
        *) die "unknown OS '$line' in $marker (expected darwin or linux, one per line)" ;;
        esac
        any=1
        if [ "$line" = "$CURRENT_OS" ]; then
            found=1
        fi
    done <"$marker"
    if [ "$any" = 0 ]; then
        die "$marker lists no OS (expected darwin and/or linux)"
    fi
    [ "$found" = 1 ]
}

# ---------------------------------------------------------------------------------------------------------------------
# Discovery: parallel arrays (bash 3.2 has no associative arrays)
# ---------------------------------------------------------------------------------------------------------------------
PKG_NAMES=()
PKG_LAYERS=()
# Every package in every layer (for the one-layer-per-name rule), and the packages whose marker excludes this OS
SEEN_NAMES=()
SEEN_LAYERS=()
SKIPPED_NAMES=()

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
        for i in ${SEEN_NAMES[@]+"${!SEEN_NAMES[@]}"}; do
            if [ "${SEEN_NAMES[$i]}" = "$pkg" ]; then
                die "package '$pkg' is defined in two layers: ${SEEN_LAYERS[$i]} and $layer"
            fi
        done
        SEEN_NAMES+=("$pkg")
        SEEN_LAYERS+=("$layer")
        if package_os_ok "${dir%/}"; then
            PKG_NAMES+=("$pkg")
            PKG_LAYERS+=("$layer")
        else
            SKIPPED_NAMES+=("$pkg")
        fi
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

if [ ${#PKG_NAMES[@]} -eq 0 ] && [ ${#WANT[@]} -eq 0 ]; then
    echo "stow: no packages found"
    exit 0
fi

SEL=()
if [ ${#WANT[@]} -eq 0 ]; then
    SEL=("${!PKG_NAMES[@]}")
else
    for pkg in "${WANT[@]}"; do
        if ! idx="$(pkg_index "$pkg")"; then
            for skipped in ${SKIPPED_NAMES[@]+"${SKIPPED_NAMES[@]}"}; do
                if [ "$skipped" = "$pkg" ]; then
                    die "package '$pkg' does not apply to $CURRENT_OS (see its .dotfiles-os)"
                fi
            done
            die "unknown package: $pkg"
        fi
        already=0
        for i in ${SEL[@]+"${SEL[@]}"}; do
            if [ "$i" = "$idx" ]; then
                already=1
            fi
        done
        if [ "$already" = 0 ]; then
            SEL+=("$idx")
        fi
    done
fi

SEL_NAMES=()
for i in "${SEL[@]}"; do
    SEL_NAMES+=("${PKG_NAMES[$i]}")
done

# ---------------------------------------------------------------------------------------------------------------------
# Ownership: every $HOME-relative path belongs to exactly one package (across all packages, not just selected ones), and
# no package provides a file at a path another package uses as a directory.
# The prune list and root-level ignores mirror stow's built-in ignore list (Stow.pm, __DATA__): file names such as
# README.md only count as ignored at the package root, and only an exact COPYING is ignored there. .DS_Store and
# .backups/ (editor-hook backup directories) and .dotfiles-os markers are pruned everywhere, matching the --ignore flags
# passed to stow below.
# ---------------------------------------------------------------------------------------------------------------------
package_files() { # $1=index: $HOME-relative paths the package provides, honoring stow's default ignores
    (
        cd "${PKG_LAYERS[$1]}/stow/${PKG_NAMES[$1]}" &&
            find . \( -name .git -o -name .gitignore -o -name .gitmodules -o -name .DS_Store -o -name .backups \
                -o -name .dotfiles-os -o -name RCS -o -name CVS -o -name .cvsignore -o -name .svn -o -name _darcs \
                -o -name .hg -o -name '?*,v' -o -name '?*~' -o -name '.#?*' -o -name '#*#' \) \
                -prune -o \( -type f -o -type l \) -print |
            sed 's|^\./||' | grep -v -E '^(README.*|LICENSE.*|COPYING)$' || true
    )
}

OWNERS="$(
    for i in "${!PKG_NAMES[@]}"; do
        package_files "$i" | awk -v pkg="${PKG_NAMES[$i]}" '{ print $0 "\t" pkg }'
    done
)"
# Prints "<path><TAB><owners>" for each identical-path clash ("pkgA,pkgB") and each file-vs-directory clash
# ("pkgA (file), pkgB (directory)")
COLLISIONS="$(printf '%s\n' "$OWNERS" | awk -F'\t' '
    $1 == "" { next }
    {
        path = $1
        pkg = $2
        files[path] = (path in files) ? files[path] "," pkg : pkg
        nfile[path]++
        n = split(path, parts, "/")
        prefix = ""
        for (i = 1; i < n; i++) {
            prefix = (i == 1) ? parts[1] : prefix "/" parts[i]
            if (!((prefix SUBSEP pkg) in seen)) {
                seen[prefix SUBSEP pkg] = 1
                dirs[prefix] = (prefix in dirs) ? dirs[prefix] ", " pkg " (directory)" : pkg " (directory)"
            }
        }
    }
    END {
        for (p in files) {
            if (nfile[p] > 1) print p "\t" files[p]
            if (p in dirs) print p "\t" files[p] " (file), " dirs[p]
        }
    }' | LC_ALL=C sort)"
if [ -n "$COLLISIONS" ]; then
    echo "stow: these paths are provided by more than one package:" >&2
    while IFS=$'\t' read -r path owners; do
        printf '  ~/%s <- %s\n' "$path" "$owners" >&2
    done <<EOF
$COLLISIONS
EOF
    exit 1
fi

# Render ownership: render.py writes its targets as real files, so no package may provide one, nor a path above one
# (a linked parent would carry the rendered file into a repository). render.py is the single source of the target list.
RENDER_SCRIPT="$REPO_DIR/scripts/dotfiles/render.py"
RENDER_TARGETS="$(python3 "$RENDER_SCRIPT" --list-targets)" ||
    die "cannot list render targets (python3 $RENDER_SCRIPT --list-targets failed)"
# An empty list would make the ownership check below vacuously pass
[ -n "$RENDER_TARGETS" ] ||
    die "cannot list render targets (python3 $RENDER_SCRIPT --list-targets printed an empty list)"
# Prints "<render target><TAB><package>" for each package path equal to or above a render target
RENDER_CLASHES="$(printf '%s\n' "$OWNERS" | RENDER_TARGETS="$RENDER_TARGETS" awk -F'\t' '
    BEGIN { n = split(ENVIRON["RENDER_TARGETS"], targets, "\n") }
    $1 == "" { next }
    {
        for (i = 1; i <= n; i++) {
            if (targets[i] != "" && ($1 == targets[i] || index(targets[i], $1 "/") == 1)) print targets[i] "\t" $2
        }
    }' | LC_ALL=C sort -u)"
if [ -n "$RENDER_CLASHES" ]; then
    echo "stow: these paths are written by scripts/dotfiles/render.py, so no package may provide them:" >&2
    while IFS=$'\t' read -r path owner; do
        printf '  ~/%s <- %s\n' "$path" "$owner" >&2
    done <<EOF
$RENDER_CLASHES
EOF
    echo "stow: move the settings into a render/<target>.json fragment instead" >&2
    exit 1
fi

# ---------------------------------------------------------------------------------------------------------------------
# Layer runs: one stow invocation per layer that has selected packages
# ---------------------------------------------------------------------------------------------------------------------
EFF_LEVEL="$LEVEL"
if [ "$SHOW_SUMMARY" = 1 ] && [ "$EFF_LEVEL" -lt 1 ]; then
    EFF_LEVEL=1
fi
VERBOSE=()
if [ "$EFF_LEVEL" -gt 0 ]; then
    VERBOSE=(--verbose="$EFF_LEVEL")
fi

PKGS=()
load_pkgs() { # fill PKGS with the selected package names that live in layer $1
    local i
    PKGS=()
    for i in "${SEL[@]}"; do
        if [ "${PKG_LAYERS[$i]}" = "$1" ]; then
            PKGS+=("${PKG_NAMES[$i]}")
        fi
    done
}

LAYER_ROOTS=()
while IFS= read -r layer; do
    load_pkgs "$layer"
    if [ ${#PKGS[@]} -gt 0 ]; then
        LAYER_ROOTS+=("$layer")
    fi
done <<EOF
$LAYERS_OUT
EOF

run_layer() { # $1=layer, $2=simulate (1|0): sets LAYER_OUT and LAYER_RC
    local mode=()
    if [ "$2" = 1 ]; then
        mode=(-n)
    fi
    load_pkgs "$1"
    LAYER_RC=0
    LAYER_OUT="$(stow --dir "$1/stow" --target "$HOME" --no-folding --ignore='\.DS_Store' --ignore='\.backups' \
        --ignore='\.dotfiles-os' --restow ${VERBOSE[@]+"${VERBOSE[@]}"} ${mode[@]+"${mode[@]}"} "${PKGS[@]}" 2>&1)" ||
        LAYER_RC=$?
}

# ---------------------------------------------------------------------------------------------------------------------
# Preflight: simulate every layer and classify what stow reports. Nothing is changed here.
#   BACKUP_TARGETS  $HOME-relative regular files / symlinks (e.g. links from an old checkout) that block a link
#   UNRESOLVED      everything else (a real directory in the way, stow errors): never auto-fixed
# Stow 2.4.1 wording (Stow.pm), reported as "  * <message>" after "WARNING! stowing <pkg> would cause conflicts:":
#   cannot stow <src> over existing target <T> since neither a link nor a directory and --adopt not specified
#   existing target is neither a link nor a directory: <T>
#   existing target is not owned by stow: <T>
# Fatal errors (e.g. "stow: ERROR: unstow_contents() called with non-directory path: ...") have no "  * " lines and a
# non-zero exit.
# ---------------------------------------------------------------------------------------------------------------------
PRE_LOGS=()
BACKUP_TARGETS=()
UNRESOLVED=()

conflict_target() { # print the $HOME-relative target named by a backup-able conflict message $1, else return 1
    local target adopt
    adopt='^cannot stow .* over existing target \(.*\) since neither a link nor a directory'
    adopt+=' and --adopt not specified$'
    target="$(printf '%s\n' "$1" | sed -n \
        -e "s/$adopt/\1/p" \
        -e 's/^existing target is neither a link nor a directory: \(.*\)$/\1/p' \
        -e 's/^existing target is not owned by stow: \(.*\)$/\1/p')"
    if [ -z "$target" ]; then
        return 1
    fi
    printf '%s\n' "$target"
}

preflight() {
    local layer msgs msg target src
    PRE_LOGS=()
    BACKUP_TARGETS=()
    UNRESOLVED=()
    for layer in "${LAYER_ROOTS[@]}"; do
        run_layer "$layer" 1
        PRE_LOGS+=("$LAYER_OUT")
        msgs="$(printf '%s\n' "$LAYER_OUT" | sed -n 's/^  \* //p')"
        if [ -z "$msgs" ]; then
            if [ "$LAYER_RC" -ne 0 ]; then
                UNRESOLVED+=("stow failed (exit $LAYER_RC) for $layer:"$'\n'"$LAYER_OUT")
            fi
            continue
        fi
        while IFS= read -r msg; do
            if target="$(conflict_target "$msg")"; then
                src="$HOME/$target"
                if [ -L "$src" ] || { [ -e "$src" ] && [ ! -d "$src" ]; }; then
                    BACKUP_TARGETS+=("$target")
                    continue
                fi
            fi
            UNRESOLVED+=("$msg")
        done <<EOF
$msgs
EOF
    done
}

report_unresolved() {
    local item
    echo "stow: cannot link; these conflicts need manual attention (nothing was changed):" >&2
    for item in "${UNRESOLVED[@]}"; do
        printf '  %s\n' "$item" >&2
    done
}

summarize() { # $1=log, $2=dry (1|0)
    if [ "$SHOW_SUMMARY" = 1 ]; then
        printf '%s' "$1" | awk -v dry="$2" -f "$SUMMARIZER"
    fi
}

show_raw() { # $1=log
    if [ "$SHOW_RAW" = 1 ]; then
        printf '%s' "$1" | grep -v '^/' >&2 || true
    fi
}

preflight
if [ ${#UNRESOLVED[@]} -gt 0 ]; then
    report_unresolved
    exit 1
fi
if [ ${#BACKUP_TARGETS[@]} -gt 0 ] && [ "$BACKUP_CONFLICTS" = 0 ]; then
    echo "stow: these existing files block linking (nothing was changed):" >&2
    for target in "${BACKUP_TARGETS[@]}"; do
        printf '  ~/%s\n' "$target" >&2
    done
    echo "stow: re-run with --backup-conflicts to move them to ~/.dotfiles-backup/ first" >&2
    exit 1
fi

BACKUP_DIR="$HOME/.dotfiles-backup/$(date +%Y%m%d-%H%M%S)"

# ---------------------------------------------------------------------------------------------------------------------
# Dry run: report what would happen, then stop
# ---------------------------------------------------------------------------------------------------------------------
if [ "$DRY_RUN" = 1 ]; then
    for log in ${PRE_LOGS[@]+"${PRE_LOGS[@]}"}; do
        show_raw "$log"$'\n'
    done
    if [ ${#BACKUP_TARGETS[@]} -gt 0 ]; then
        # Stow reports no link plan while conflicts exist, so no summary is printed for this case
        for target in "${BACKUP_TARGETS[@]}"; do
            echo "stow: would back up existing $target -> $BACKUP_DIR/$target"
        done
        echo "stow: simulated ${SEL_NAMES[*]} (dry-run; ${#BACKUP_TARGETS[@]} conflicting file(s) would be backed up" \
            "first, then linked)"
    else
        ALL_PRE=""
        for log in ${PRE_LOGS[@]+"${PRE_LOGS[@]}"}; do
            ALL_PRE+="$log"$'\n'
        done
        summarize "$ALL_PRE" 1
        echo "stow: simulated ${SEL_NAMES[*]} (dry-run, no changes written)"
    fi
    exit 0
fi

# ---------------------------------------------------------------------------------------------------------------------
# Backup, then re-verify every layer before linking anything
# ---------------------------------------------------------------------------------------------------------------------
if [ ${#BACKUP_TARGETS[@]} -gt 0 ]; then
    for target in "${BACKUP_TARGETS[@]}"; do
        mkdir -p "$BACKUP_DIR/$(dirname "$target")"
        mv "$HOME/$target" "$BACKUP_DIR/$target" ||
            die "could not back up ~/$target (moved files so far are in $BACKUP_DIR)"
        echo "stow: backed up existing $target -> $BACKUP_DIR/$target"
    done
    preflight
    if [ ${#UNRESOLVED[@]} -gt 0 ] || [ ${#BACKUP_TARGETS[@]} -gt 0 ]; then
        for log in ${PRE_LOGS[@]+"${PRE_LOGS[@]}"}; do
            printf '%s\n' "$log" >&2
        done
        echo "stow: re-verification failed after backing up; nothing was linked" >&2
        echo "stow: the moved files are in $BACKUP_DIR (move them back to restore)" >&2
        exit 1
    fi
fi

# ---------------------------------------------------------------------------------------------------------------------
# Apply: stow every layer for real
# ---------------------------------------------------------------------------------------------------------------------
STOW_LOG=""
for layer in "${LAYER_ROOTS[@]}"; do
    run_layer "$layer" 0
    STOW_LOG+="$LAYER_OUT"$'\n'
    if [ "$LAYER_RC" -ne 0 ]; then
        printf '%s' "$STOW_LOG" >&2
        echo "stow: FAILED (exit $LAYER_RC) for $layer" >&2
        exit "$LAYER_RC"
    fi
done

show_raw "$STOW_LOG"
summarize "$STOW_LOG" 0
echo "stow: applied ${SEL_NAMES[*]}"
