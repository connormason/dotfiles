# medialink Jellyfin-layout Implementation Plan

> **For agentic workers:** work the checkboxes in order and keep them current. Run Python through `uv run`; never run
> `ruff format`. Match the surrounding hand-aligned style in `services/medialink/medialink/`.

**Goal:** reorganise the library files medialink owns into `Movie (Year)/` and `Show/Season NN/` form, by moving
hardlinks, then make new downloads land that way.

**Spec:** [`2026-11-22-medialink-reorg-design.md`](2026-11-22-medialink-reorg-design.md)

**Architecture:** a pure `layout.place()` shared by a new `reorganize` command and, last, by the linker; an inode index
in the reconcile loop so moved links are not re-created; a journal for undo.

**Tech stack:** Python 3.12 (stdlib only), pytest, Docker Compose.

## Global Constraints

- The `run` loop and `once` only add links; only `reorganize --apply` and `dedupe --apply` move or remove anything.
- `reorganize` is a dry run by default, moves with `rename` inside `/storage/media`, never touches files it does not own,
  and journals every move.
- **Do not run `reorganize --apply` before `dedupe --apply` has finished** (parent plan Task 5, step 6): `dedupe` finds
  flat duplicates through the mirror layout.
- Nothing on the live NAS changes until the owner runs the rollout steps.
- Tests live in `tests/unit/services/test_medialink.py` (or a sibling module); keep `ruff check` and `mypy` clean.

## File Structure

| Path                                                      | Role                                                           |
| --------------------------------------------------------- | -------------------------------------------------------------- |
| `services/medialink/medialink/index.py` (new)             | Library inode index                                            |
| `services/medialink/medialink/state.py`                   | Records output paths per extracted archive                     |
| `services/medialink/medialink/layout.py` (new)            | `place()`, parser, overrides loading                           |
| `services/medialink/medialink/reorganize.py` (new)        | Owned-file discovery, plan, apply, journal, undo               |
| `services/medialink/medialink/{linker,engine,archives}.py` | Index-aware `EXISTS`; extraction records; layout switch        |
| `services/medialink/medialink/{cli,config}.py`            | `reorganize` command, `MEDIALINK_LAYOUT`, overrides path       |
| `tests/unit/services/`                                    | Tests per module, plus a fixture of real release names         |
| `services/README.md`, parent plan, `docs/RUN_PY_REFERENCE.md` | Documentation                                              |

## Tasks

### Task 1: Inode index and extraction records (no behaviour change)

- [ ] `index.py`: walk `movies/` and `tv/` once per pass into a `{(st_dev, st_ino): Path}` map; tolerate files vanishing
      mid-walk
- [ ] `linker._link_one`: a source whose inode is in the index is `EXISTS` wherever it lives; thread the index through
      `link_torrent` and `reconcile` (build it once per pass; dry runs build it too)
- [ ] `state.py`: store `extracted: {key: [relative output paths]}` next to `notified`, loading old files that lack it
- [ ] `archives._extract_one`: record the published output paths with the existing completion key
- [ ] Tests: moved link stays `EXISTS`; deleted link is re-created; extraction is not repeated after its output moves;
      old state files still load
- [ ] `ruff check`, `mypy`, full `uv run pytest`; PR; merge (CI deploys); **soak the deployed loop for at least a day**
      and confirm nothing re-links or alerts

### Task 2: Layout parser

- [ ] Add `tests/unit/services/data/release_names.json` from the live library (movies and tv top-level names plus the
      nested file names of the multi-file folders), each with its expected placement written by hand
- [ ] `layout.py`: `Placement` dataclass (category, relative path); `place(category, torrent_name, file_name,
      overrides)` returning `None` when undecidable
- [ ] Parse `S01E02`, `1x02`, `Season N`, season-only folder names, multi-season packs (season from the file path),
      year, title normalisation (dots, underscores, release-group and codec tokens), anime absolute numbering reported as
      `None`
- [ ] Rules: `Show (Year)` only to disambiguate or when the release gives a year and a same-title show exists; strong
      episodic marker in `movies/` yields a `tv/` placement; `Season 00` for specials; ` - 2160p` style suffix for second
      versions of a movie
- [ ] Overrides: `config/medialink/overrides.json` (`pattern` to `title`, `year`, optional `category`); a missing file
      means none; a malformed one is a `ConfigError`, never silently ignored
- [ ] Table-driven tests over the fixture; every name the parser cannot place asserts `None`
- [ ] `ruff check`, `mypy`; PR; merge

### Task 3: `reorganize` command

- [ ] `reorganize.py`: discover owned files (inode match against Transmission's file list plus recorded extractions)
- [ ] Plan: per file, `place()` result vs current path; classify as `move`, `cross-library`, `in-place`, `conflict`
      (target exists with a different inode), `redundant` (target is the same inode), `unparsed`, `drop-sidecar`
- [ ] Apply: `rename` with parents created (mode `0o775`); redundant old link removed; conflicts and unparsed untouched;
      sidecars follow their video, scene junk links removed; prune only directories this run emptied, never a library
      root
- [ ] Journal: append `{old, new, ts}` per move to `config/medialink/reorg-journal.jsonl` before each rename; `--undo
      JOURNAL` replays it in reverse and refuses if a destination is now occupied
- [ ] `cli.py`: `reorganize [--apply] [--limit N] [--only PATTERN] [--undo JOURNAL]`; report grouped by action with
      totals and the first N examples of each; non-zero exit when conflicts or unparsed files exist
- [ ] Tests: dry run changes nothing; apply moves, journals and prunes; conflict, redundant, cross-library; sidecars;
      `--limit` and `--only`; `--undo` restores the exact tree (compare directory listings and inodes); hand-curated
      folders are never touched
- [ ] `run.py medialink` passthrough already covers the new subcommand; document it in `docs/RUN_PY_REFERENCE.md` and
      `services/README.md`
- [ ] `ruff check`, `mypy`, full `uv run pytest`; PR; merge

### Task 4: Rollout (owner, on the NAS)

- [ ] Confirm parent plan Task 5 is finished, including `dedupe --apply`
- [ ] `docker exec medialink python -m medialink reorganize` for the dry-run report; review conflicts, unparsed files and
      cross-library moves; write `overrides.json` for the misses; repeat until the report is acceptable
- [ ] `zfs snapshot` the media dataset and copy `config/jellyfin` and `config/plex`
- [ ] Pilot: `--apply --only` about three shows and three movies; rescan Jellyfin and Plex; check watch history,
      metadata matches and artwork in both. If history is lost, stop and revise the design before continuing
- [ ] Batched `--apply --limit N`, snapshot and rescan between batches
- [ ] Re-run the name-and-size audit; confirm seeding in Transmission is unaffected and the loop reports no new links

### Task 5: Forward path

- [ ] `config.py`: `MEDIALINK_LAYOUT` (`mirror` default, `jellyfin`)
- [ ] `link_torrent`: with `jellyfin`, destination comes from `place()`; `None` falls back to the mirror path and the
      engine records it as unparsed so it alerts once
- [ ] Tests for both modes and the fallback; update the deploy-contract and README variable table
- [ ] Set `MEDIALINK_LAYOUT=jellyfin` in `services/medialink/compose.yml` after the rollout is complete; deploy
- [ ] Update `services/README.md`, the parent design and plan (tick Task 6) and `.ctx/ARCHITECTURE.md` if it describes
      the layout
