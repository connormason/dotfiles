# medialink Jellyfin-layout Implementation Plan

> **For agentic workers:** work the checkboxes in order and keep them current. Run Python through `uv run`; never run
> `ruff format`. Match the surrounding hand-aligned style in `services/medialink/medialink/`.

**Goal:** reorganise the library files medialink owns into `Movie (Year)/` and `Show/Season NN/` form, by moving
hardlinks, then make new downloads land that way.

**Spec:** [`2026-11-22-medialink-reorg-design.md`](2026-11-22-medialink-reorg-design.md)

**Architecture:** a pure `layout.place()` shared by a new `reorganize` command and by the linker (`MEDIALINK_LAYOUT=jellyfin`);
an inode index in the reconcile loop so moved links are not re-created; a journal for undo.

**Tech stack:** Python 3.12 (stdlib only), pytest, Docker Compose.

## Global Constraints

- The `run` loop and `once` only add links; only `reorganize --apply` and `dedupe --apply` move or remove anything.
- `reorganize` is a dry run by default, moves with `link` plus `unlink` inside `/storage/media` (never overwriting),
  never touches files it does not own, and journals every move.
- **Do not run `reorganize --apply` before `dedupe --apply` has finished** (parent plan Task 5, step 6): `dedupe` finds
  flat duplicates through the mirror layout.
- **Set `MEDIALINK_LAYOUT=jellyfin` before the first `reorganize --apply`.** `reorganize` drops scene leftovers from the
  library; in the `mirror` layout the loop would link them straight back.
- Nothing on the live NAS changes until the owner runs the rollout steps.
- Tests live in `tests/unit/services/`; keep `ruff check` and `mypy` clean.

## Deviations from the design

- **Forward path moved ahead of the rollout** (was Task 5 after it): the junk re-link problem above makes
  `MEDIALINK_LAYOUT=jellyfin` a prerequisite of the first apply, not a finishing step.
- **Ownership is the mirror path.** A file is owned only while it is an inode match *at the path medialink linked it
  to* (plus recorded extractions), not anywhere in the library. This keeps hand-curated hardlinks (the live library has
  some, for example under `tv/Good Eats/`) out of scope. A link already in the directory the layout asks for is left
  as it is.
- **Extracted RAR contents** are placed by `reorganize`, not by the loop: extraction writes into the release folder, and
  nothing moves it until the command runs.

## File Structure

| Path                                                       | Role                                                                    |
| ---------------------------------------------------------- | ----------------------------------------------------------------------- |
| `services/medialink/medialink/index.py` (new)              | Library inode index                                                     |
| `services/medialink/medialink/state.py`                    | Records output paths per extracted archive                              |
| `services/medialink/medialink/layout.py` (new)             | `place()`, parser, overrides loading                                    |
| `services/medialink/medialink/reorganize.py` (new)         | Owned-file discovery, plan, apply, journal, undo                        |
| `services/medialink/medialink/{linker,engine,archives}.py` | Index-aware `EXISTS`; extraction records; layout switch                 |
| `services/medialink/medialink/{cli,config}.py`             | `reorganize` command, `MEDIALINK_LAYOUT`, `MEDIALINK_OVERRIDES_PATH`    |
| `tests/unit/services/`                                     | `test_medialink_{index,layout,reorganize}.py` and `data/release_names.json` |
| `services/README.md`, `docs/RUN_PY_REFERENCE.md`, parent plan | Documentation                                                        |

## Tasks

### Task 1: Inode index and extraction records (no behaviour change)

- [x] `index.py`: walk `movies/` and `tv/` once per pass into a `{(st_dev, st_ino): Path}` map; tolerate files vanishing
- [x] `linker._link_one`: a source whose inode is in the index is `EXISTS` wherever it lives; thread the index through
      `link_torrent` and `reconcile` (build it once per pass; dry runs build it too)
- [x] `state.py`: store `extracted: {key: [relative output paths]}` next to `notified`, loading old files that lack it
- [x] `archives._extract_one`: record the published output paths with the existing completion key
- [x] Tests: moved link stays `EXISTS`; deleted link is re-created; extraction is not repeated after its output moves;
      old state files still load
- [x] `ruff check`, `mypy`, full `uv run pytest`

### Task 2: Layout parser

- [x] `tests/unit/services/data/release_names.json`: release names modelled on the live library, each with its
      expected placement written by hand (inner file names of collections are representative, not copied)
- [x] `layout.py`: `Placement` dataclass; `place(category, torrent_name, file_name, overrides, shows)` returning `None`
      when undecidable; `kind()` sorts files into video, subtitle, junk and other
- [x] Parse `S01E02`, `1x02`, multi-episode files, multi-season packs (season from the file), year, title
      normalisation (separators, release-group and codec tokens, casing from the better-cased name); anime absolute
      numbering and date-based episodes return `None`
- [x] Rules: no year on show folders unless an override gives one or an existing `Show (Year)` directory matches; strong
      episodic marker in `movies/` yields a `tv/` placement; `Season 00`; ` - 2160p` style suffix for a second version
      of a movie; subtitle language suffix
- [x] Overrides: `config/medialink/overrides.json`; a missing file means none, a malformed one is a `ConfigError`
- [x] Table-driven tests over the fixture; read-only sweep over the live library (2,041 videos placed, 28 unplaced)
- [x] `ruff check`, `mypy`

### Task 3: `reorganize` command and Jellyfin layout

- [x] `reorganize.py`: discover owned files (mirror-path inode match against Transmission's file list, plus recorded
      extractions)
- [x] Plan: `move`, `cross-library`, `in-place`, `redundant`, `drop-junk`, `keep`, `conflict`, `unparsed`
- [x] Apply: `link` then `unlink` (never overwrites); redundant old link removed; conflicts and unparsed untouched;
      prune only directories the run emptied, never a library root
- [x] Journal: `config/medialink/reorg-journal.jsonl`, one line per move or drop, fsynced between the link and the
      unlink; `--undo JOURNAL` replays it backwards and skips occupied paths
- [x] `cli.py`: `reorganize [--apply] [--limit N] [--only REGEX] [--undo JOURNAL]`; non-zero exit on conflicts or
      unparsed files
- [x] `MEDIALINK_LAYOUT` (`mirror` default, `jellyfin`) and `MEDIALINK_OVERRIDES_PATH`; with `jellyfin` the linker takes
      destinations from `place()`, falls back to the mirror path for a `None`, and skips RAR volumes and scene leftovers
- [x] Tests for plan, apply, undo, the loop in both layouts, config validation and the command
- [x] Read-only dry run against the live NAS: 1,978 moves, 535 junk drops, 28 unparsed, 161 conflicts (mostly the
      hand-organised `Good Eats` episodes, which already exist at their targets)
- [x] Documentation: `services/README.md` (commands, layout, overrides, variables), `docs/RUN_PY_REFERENCE.md`
- [x] `ruff check`, `mypy`, full `uv run pytest`; open the PR (CI deploys on merge; behaviour is unchanged while
      `MEDIALINK_LAYOUT` is `mirror`)

### Task 4: Rollout (owner, on the NAS)

- [ ] Confirm parent plan Task 5 is finished, including `dedupe --apply`
- [ ] `python3 run.py medialink reorganize` for the dry run; review conflicts, unparsed files and cross-library moves;
      write `overrides.json` for the misses; repeat until the report is acceptable
- [ ] `zfs snapshot` the media dataset and copy `config/jellyfin` and `config/plex`
- [ ] Set `MEDIALINK_LAYOUT=jellyfin` in `services/medialink/compose.yml`; deploy (new downloads now land in the new
      layout and scene leftovers stop being linked)
- [ ] Pilot: `reorganize --apply --only <three shows and three movies>`; rescan Jellyfin and Plex; check watch history,
      metadata matches and artwork in both. If history is lost, `--undo` the batch, stop and revise the design
- [ ] Batched `--apply --limit N`, snapshot and rescan between batches
- [ ] Re-run the name-and-size audit; confirm seeding in Transmission is unaffected and the loop reports no new links

### Task 5: Close out

- [ ] Tick Task 6 in the parent plan and delete any `overrides.json` entries that are no longer needed
- [ ] Decide what to do with the conflicts that remain (duplicate releases of the same episode)
