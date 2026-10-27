# summarize_stow.awk — distill a GNU Stow verbose log into the net state change.
#
# Reads a captured `stow --restow --verbose` log on stdin and prints only what effectively changed:
# files newly linked (added), files whose link target changed (updated), and files unlinked without a
# replacement (removed). The per-file UNLINK/LINK churn that `--restow` emits for every managed file on
# every run is filtered out using stow's own "(reverts previous action)" reconciliation marker.
#
# How stow's verbose log encodes a net change (GNU Stow 2.x):
#   - A no-op relink prints `LINK: path => target (reverts previous action)`; its paired `UNLINK: path`
#     is also a no-op. Both are ignored here.
#   - A genuine change prints `LINK:`/`UNLINK:` WITHOUT that suffix.
# Classification per path:
#   - LINK (no revert), no genuine UNLINK            -> added
#   - genuine UNLINK and LINK (no revert)            -> updated (link target changed)
#   - genuine UNLINK, no LINK                         -> removed
# Spurious `/`-prefixed path lines emitted by GNU Stow 2.4.1 on macOS never match the prefixes below and
# are therefore ignored.
#
# Variables (set with -v):
#   dry=1   phrase the summary as a preview ("would link/update/remove") for `stow -n` runs.
#
# Usage:
#   awk -f summarize_stow.awk < stow.log
#   awk -v dry=1 -f summarize_stow.awk < stow.log

/^LINK: / {
    rest = substr($0, 7)  # strip "LINK: "
    if (rest ~ / \(reverts previous action\)$/) {
        sub(/ \(reverts previous action\)$/, "", rest)
        idx = index(rest, " => ")
        path = (idx ? substr(rest, 1, idx - 1) : rest)
        reverted[path] = 1
    } else {
        idx = index(rest, " => ")
        path = (idx ? substr(rest, 1, idx - 1) : rest)
        target = (idx ? substr(rest, idx + 4) : "")
        linked[path] = target
    }
    next
}

/^UNLINK: / {
    path = substr($0, 9)  # strip "UNLINK: "
    unlinked[path] = 1
    next
}

END {
    n_add = n_upd = n_rem = 0

    # A path that was linked (without a revert) is either an update (it was also genuinely unlinked
    # first) or a brand-new link. A genuine unlink is one not cancelled by a reverting relink.
    for (path in linked) {
        if (unlinked[path] && !reverted[path]) {
            upd[path] = linked[path]
            n_upd++
        } else {
            add[path] = linked[path]
            n_add++
        }
    }
    for (path in unlinked) {
        if (!reverted[path] && !(path in linked)) {
            rem[path] = 1
            n_rem++
        }
    }

    if (n_add + n_upd + n_rem == 0) {
        print "stow: no changes (already current)"
        exit 0
    }

    link_verb   = dry ? "would link"   : "linked"
    update_verb = dry ? "would update" : "updated"
    remove_verb = dry ? "would remove" : "removed"
    if (dry)
        print "stow: dry-run preview of changes:"

    for (path in add)
        printf "  + ~/%s (%s)\n", path, link_verb
    for (path in upd)
        printf "  ~ ~/%s (%s)\n", path, update_verb
    for (path in rem)
        printf "  - ~/%s (%s)\n", path, remove_verb

    printf "stow: %d added, %d updated, %d removed\n", n_add, n_upd, n_rem
}
