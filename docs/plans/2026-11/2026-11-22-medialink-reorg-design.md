# medialink: Jellyfin-style library layout (Task 6)

Status: **approved 2026-11-22** with every recommendation in [Decisions](#decisions) accepted. Implementation plan:
[`2026-11-22-medialink-reorg-plan.md`](2026-11-22-medialink-reorg-plan.md). Parent: [`2026-11-22-medialink-design.md`](2026-11-22-medialink-design.md) (follow-up 1) and
[`2026-11-22-medialink-plan.md`](2026-11-22-medialink-plan.md) (Task 6).

## Problem

`medialink` mirrors each torrent's own layout into `movies/` and `tv/`, so the library carries scene release names.
Jellyfin and Plex both cope, but badly: one show is spread across many folders, episodes arrive as one folder per file,
and identification depends on how tidy the release name happens to be.

Survey of the live library on 2026-11-22 (read-only; taken while medialink was in steady state):

| Shape                                                       | Count                                       | Consequence for the design                                  |
| ----------------------------------------------------------- | ------------------------------------------- | ----------------------------------------------------------- |
| `movies/` top level                                         | 79 folders, 66 flat files                   | Flat files are autoplex leftovers awaiting `dedupe`         |
| `movies/` folders holding more than one video               | 12 (collections, trilogies, two TV seasons) | Layout must be decided **per file**, not per torrent        |
| TV seasons filed under `movies/`                            | `The.Perfect.Couple.S01`, `Three Women S01` | A cross-library move is sometimes the right answer          |
| `tv/` top level                                             | 130 folders, 9 flat files                   |                                                             |
| `tv/` folders already in `Show/Season NN/` form             | 23                                          | Hand-curated (Friends, Silicon Valley): **must be left alone** |
| One-episode-per-folder releases (Chainsaw Man, Love Island) | many                                        | Episodes of one show must merge under one show folder       |
| Multi-season packs (`S01-S05`, `S01.to.S14`)                | several                                     | Season comes from each file, not from the pack name         |
| Hardlinked library videos                                   | 2,102                                       | These are the files medialink owns                          |
| Sidecars                                                    | 304 `.srt`, 255 `.nfo`, 143 `.sfv`, 139 `.png` | Subtitles follow their video; scene junk does not        |

## Goals and non-goals

- Reorganise **only files medialink owns**: library files that are hardlinks of a Transmission download, plus RAR
  extractions it recorded. Anything else (hand-curated folders, music, files medialink never touched) is invisible to it.
- **Move links, never files.** A move is `rename(2)` inside one dataset: atomic, instantaneous, and the seed copy in
  `downloads/complete` is untouched, so Transmission keeps seeding.
- Everything is **dry-run first, reversible, and batchable**. No metadata is guessed: a name the parser cannot place is
  reported and left where it is, the same stance as `classify`.
- Non-goals: renaming files in the download tree, touching Sonarr/Radarr, fetching posters or metadata (the media
  servers do that).

## Target layout

Both servers accept the same convention, so one layout serves both.

```text
movies/Title (Year)/Title (Year).ext
movies/Title (Year)/Title (Year).en.srt                 subtitles keep the video's base name
tv/Show Name (Year)/Season 01/Show Name - S01E02.ext
tv/Show Name (Year)/Season 00/...                       specials
```

- The `(Year)` on a show is used only to disambiguate (`Criminal Minds` 2005 vs. the spin-offs), and is omitted when the
  release gives none.
- Multiple versions of one movie (1080p and 2160p) use Jellyfin's ` - 2160p` suffix on the file name. Duplicate episodes
  are **not** auto-resolved: the first file wins and the second is reported as a conflict (Love Island and Chainsaw Man
  each have dubbed/alternate episodes).
- Sidecars: `.srt`/`.sub`/`.idx`/`.ass` follow their video. `.nfo`, `.sfv`, `.png`, samples and `.txt` are scene
  junk (the `.nfo` files are release notes, not Kodi XML) and are **not** carried into the new layout; their old links
  are removed with the old folder, the seed copies remain (Decision 3).

## Approach

### 1. Layout function (new `layout.py`)

A pure function `place(category, torrent_name, file_name) -> Placement | None`, shared by the new `reorganize` command
and, later, by the linker for new downloads, so both always agree.

- Parses season/episode (`S01E02`, `1x02`, `Season 3`, folder `S04`), year, and the title (everything before the first
  marker, with dots and underscores normalised, release-group and codec tokens stripped).
- Returns `None` when it cannot decide. The caller falls back to today's mirror layout and reports the file.
- A strong episodic marker on a file in `movies/` yields a `tv/` placement (cross-library move, Decision 4).
- A per-user override file (`config/medialink/overrides.json`: release-name pattern to canonical title/year) fixes the
  cases the parser gets wrong, without code changes. This is the escape hatch that makes "report, don't guess" workable.

### 2. Make the reconcile loop layout-aware first (prerequisite, ships alone)

Today `link_torrent` decides "already linked" by checking `dest_root/file.name`. After a move that path is empty, so the
next 60-second pass would **recreate the old link**, silently undoing the reorganisation. Fix before any move:

- Build an **inode index** of the library once per pass (a `scandir` walk of roughly 7,500 files). A source file whose
  `(st_dev, st_ino)` is present anywhere under `movies/` or `tv/` is `EXISTS`, wherever it lives.
- It needs no new persistent state and self-heals if a link is moved by hand.
- RAR extractions have no source inode, and `State` currently stores only keys (`archives.py` marks an archive done, but
  not where its output went). Extend it to record the output paths per archive so the reorganiser can find them and an
  extraction is never repeated after its files move.
- This step changes no behaviour and can be deployed and soaked before the rest exists.

### 3. `reorganize` command (new, mirrors `dedupe`)

`medialink reorganize [--apply] [--limit N] [--only PATTERN] [--undo JOURNAL]`, dry run by default.

1. Enumerate owned files (inode match against Transmission's file list, plus recorded extractions).
2. Compute each file's `Placement`; skip files already in place and files with `None`.
3. Report: moves, cross-library moves, conflicts (target exists with a different inode), unparsed files, folders that
   would empty.
4. With `--apply`: `rename`, creating parents; a target holding the **same** inode just drops the redundant old link; a
   different inode is a conflict and nothing moves. Prune only directories the run emptied, never a library root.
5. Append every move to `config/medialink/reorg-journal.jsonl` (old, new, timestamp). `--undo` replays it backwards, so
   rollback is as cheap as the move.
6. `--limit N` applies in batches by show/movie so each step can be checked in the servers.

### 4. Forward path (last)

Once the library has converged, `MEDIALINK_LAYOUT=jellyfin` (default `mirror` until then) makes the linker call `place`
for new torrents. `None` falls back to mirror, so a new release is never lost, only reported, and a later override plus
`reorganize` places it.

## Risks and how the plan contains them

| Risk                                                                                   | Containment                                                                                                      |
| -------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| Loop re-links moved files                                                              | Inode index lands and soaks **before** any move (step 2)                                                         |
| Watch history or metadata lost in Jellyfin/Plex when paths change                      | Unverified either way. A pilot of about three shows and three movies, checked in both servers, gates the rest    |
| Wrong parse files an episode under the wrong show                                      | Dry-run report reviewed by the owner, overrides file, `--limit` batches, journal-based `--undo`                  |
| `dedupe` assumes the mirror layout (a flat file is removed only if its foldered twin is found) | **Finish `dedupe --apply` first** (Task 5, step 6); reorganising earlier would hide twins from it       |
| Bad batch is hard to unwind in the servers                                             | `zfs snapshot` of the media dataset and a copy of `config/{jellyfin,plex}` before each batch                     |
| Parser overreach (a regex "title extractor" is a rabbit hole)                          | Test against a fixture of the real names in this library; anything outside it is reported rather than handled    |

Server refresh after moves: both servers watch the filesystem, but a full rescan after each batch is the dependable
path. Triggering it through their APIs would need tokens in `env.j2`, so the rescan stays manual (Decision 5).

## Testing

- `layout.py`: table-driven tests over a fixture of real release names from this library (movies, one-folder-per-episode
  shows, multi-season packs, collections, anime with absolute numbering, name-and-year collisions).
- Inode index: a moved link is `EXISTS`; a deleted link is re-created; extractions are not repeated after a move.
- `reorganize`: dry run changes nothing; apply moves, journals and prunes only emptied folders; conflicts and redundant
  links; cross-library move; `--undo` restores the exact tree; hand-curated folders are never touched.
- Deploy contract: unchanged (single `/storage/media` mount is what makes `rename` and `link` legal).

## Phasing

1. Inode index, extraction records, tests; deploy and soak (no behaviour change).
2. `layout.py` and fixture tests.
3. `reorganize` dry-run report; owner reviews and writes overrides.
4. Pilot apply; verify Jellyfin and Plex.
5. Batched apply of the rest; final audit.
6. `MEDIALINK_LAYOUT=jellyfin` for new downloads; update README and the parent plan.

## Decisions

All five were approved as recommended.

1. **Title source: offline stdlib parser plus the overrides file.** Rejected: the `guessit` library (better coverage but
   breaks the stdlib-only rule) and TMDB lookup (API key, network, and a failure mode for every ambiguous name). Reading
   titles back from Jellyfin's API was also rejected: it matches from the same messy names, so errors would be laundered
   into the layout, and it ties the layout to one server. Revisit TMDB only if the overrides file grows unmanageable.
2. **Show-folder year:** only when needed to disambiguate or when the release gives one and another show shares the title.
3. **Sidecars:** subtitles follow their video; scene junk (`.nfo`, `.sfv`, `.png`, samples, `.txt`) is dropped from the
   library. Seed copies are unaffected.
4. **Misfiled seasons:** `S01`-style files found in `movies/` move into `tv/`, reported as cross-library moves.
5. **Server refresh:** manual rescan after each batch; no Jellyfin or Plex tokens in `env.j2`.
