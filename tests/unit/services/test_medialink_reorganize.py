"""
Tests for medialink.reorganize, the Jellyfin layout in the reconcile loop, and the reorganize command
"""
from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

import pytest

from medialink.cli import EXIT_CONFIG
from medialink.cli import EXIT_OK
from medialink.cli import EXIT_PROBLEMS
from medialink.cli import main
from medialink.config import Config
from medialink.config import ConfigError
from medialink.engine import reconcile
from medialink.linker import EXISTS
from medialink.linker import LINKED
from medialink.linker import SKIPPED
from medialink.reorganize import CONFLICT
from medialink.reorganize import CROSS
from medialink.reorganize import DROP
from medialink.reorganize import IN_PLACE
from medialink.reorganize import KEEP
from medialink.reorganize import MOVE
from medialink.reorganize import REDUNDANT
from medialink.reorganize import UNPARSED
from medialink.reorganize import apply_plan
from medialink.reorganize import discover
from medialink.reorganize import make_plan
from medialink.reorganize import select
from medialink.reorganize import undo
from medialink.state import State
from medialink.transmission import TransmissionClient
from tests.unit.services.test_medialink import make_torrent
from tests.unit.services.test_medialink import write_source

if TYPE_CHECKING:
    from pathlib import Path

    from medialink.reorganize import Entry
    from medialink.transmission import Torrent

MOVIE_DIR = '/downloads/complete/movies'
TV_DIR    = '/downloads/complete/tv'


# ==================================================================================================
# Helpers and fixtures
# ==================================================================================================


def movie(name: str, *files: str, left: int = 0) -> Torrent:
    """
    A movies torrent whose files all sit inside a release folder called ``name``
    """
    return make_torrent(name, {f'{name}/{f}': 10 for f in files}, download_dir=MOVIE_DIR, left=left)


def episode(name: str) -> Torrent:
    """
    A single-episode TV torrent: a release folder holding one ``<name>.mkv``
    """
    return make_torrent(name, {f'{name}/{name}.mkv': 10}, download_dir=TV_DIR)


def mirrored(config: Config, *torrents: Torrent) -> list[Torrent]:
    """
    Create the sources of each torrent and link them in the mirror layout, as the loop has until now
    """
    for torrent in torrents:
        write_source(config, torrent, torrent.name.encode())
    reconcile(list(torrents), config)
    return list(torrents)


def plan_for(config: Config, torrents: list[Torrent]) -> list[Entry]:
    """
    Discover and plan in one step
    """
    return make_plan(discover(torrents, config), config)


def _config(tmp_path: Path, **extra: str) -> Config:
    """
    Configuration rooted in a temporary media directory with the library layout created
    """
    media = tmp_path / 'media'
    for sub in ('downloads/complete', 'movies', 'tv'):
        (media / sub).mkdir(parents=True)
    env = {'MEDIALINK_MEDIA_ROOT': str(media), 'MEDIALINK_NTFY_URL': 'http://ntfy.invalid', **extra}
    return Config.from_env(env)


@pytest.fixture
def config(tmp_path: Path) -> Config:
    """
    Mirror-layout configuration
    """
    return _config(tmp_path)


@pytest.fixture
def jellyfin(tmp_path: Path) -> Config:
    """
    Jellyfin-layout configuration
    """
    return _config(tmp_path, MEDIALINK_LAYOUT='jellyfin')


# ==================================================================================================
# discover / make_plan / select
# ==================================================================================================


class TestDiscover:
    """
    Tests for discover
    """
    def test_only_files_still_at_their_mirror_path_are_owned(self, config: Config) -> None:
        """
        Test that links are owned, while a copy a person made and a link that already moved are not
        """
        owned  = movie('Film.2020.1080p', 'film.mkv')
        copied = movie('Other.2019.1080p', 'other.mkv')
        moved  = movie('Gone.2018.1080p', 'gone.mkv')
        for torrent in (owned, copied, moved):
            write_source(config, torrent, torrent.name.encode())

        reconcile([owned, moved], config)
        (config.movies_root / 'Other.2019.1080p').mkdir()
        (config.movies_root / 'Other.2019.1080p' / 'other.mkv').write_bytes(b'Other.2019.1080p')  # independent copy
        (config.movies_root / 'Gone (2018)').mkdir()
        (config.movies_root / 'Gone.2018.1080p' / 'gone.mkv').rename(config.movies_root / 'Gone (2018)' / 'gone.mkv')

        found = discover([owned, copied, moved], config)

        assert [c.torrent for c in found] == ['Film.2020.1080p']

    def test_unfinished_and_unclassified_torrents_are_skipped(self, config: Config) -> None:
        """
        Test that torrents still downloading, or with no library, own nothing
        """
        busy   = movie('Busy.2020', 'a.mkv', left=5)
        orphan = make_torrent('Mystery', {'Mystery': 10}, download_dir='/downloads/complete')

        assert discover([busy, orphan], config) == []

    def test_extracted_files_are_found_through_the_state(self, config: Config) -> None:
        """
        Test that a recorded RAR extraction output is owned even though it has no download-tree inode
        """
        torrent = movie('Rel.2020.1080p', 'rel.rar')
        out     = config.movies_root / 'Rel.2020.1080p' / 'Rel.2020.1080p.mkv'
        out.parent.mkdir()
        out.write_bytes(b'video')
        state = State(config.state_path)
        key   = f'extracted:{torrent.hash}:Rel.2020.1080p/rel.rar'
        state.record_outputs(key, ['movies/Rel.2020.1080p/Rel.2020.1080p.mkv'])

        [found] = discover([torrent], config, state)

        assert found.current == out
        assert found.name == 'Rel.2020.1080p/Rel.2020.1080p.mkv'
        assert found.source is None


class TestMakePlan:
    """
    Tests for make_plan
    """
    def test_movie_moves_into_a_titled_folder(self, config: Config) -> None:
        """
        Test that a scene-named movie folder is planned as Title (Year)/Title (Year).ext
        """
        torrents = mirrored(config, movie('Film.2020.1080p-GRP', 'film.2020.1080p.mkv'))

        [entry] = plan_for(config, torrents)

        assert entry.action == MOVE
        assert entry.target == config.movies_root / 'Film (2020)' / 'Film (2020).mkv'

    def test_one_folder_per_episode_merge_under_one_show(self, config: Config) -> None:
        """
        Test that single-episode torrents of one show end up in one show folder
        """
        torrents = mirrored(config, episode('Show.Name.S01E01.1080p'), episode('Show.Name.S01E02.1080p'))

        targets = {e.target for e in plan_for(config, torrents)}

        assert targets == {
            config.tv_root / 'Show Name' / 'Season 01' / 'Show Name - S01E01.mkv',
            config.tv_root / 'Show Name' / 'Season 01' / 'Show Name - S01E02.mkv',
        }

    def test_existing_show_folder_is_reused(self, config: Config) -> None:
        """
        Test that a hand-made show directory with different punctuation receives the new episode
        """
        (config.tv_root / 'Show: Name').mkdir()
        torrents = mirrored(config, episode('Show.Name.S01E01.1080p'))

        [entry] = plan_for(config, torrents)

        assert entry.target is not None
        assert entry.target.parts[-3] == 'Show: Name'

    def test_junk_is_dropped_only_when_the_torrent_is_placed(self, config: Config) -> None:
        """
        Test that scene leftovers are dropped beside a placed video and kept when nothing could be placed
        """
        placed   = movie('Film.2020.1080p', 'film.mkv', 'film.nfo')
        unplaced = movie('Nameless.1080p', 'clip.mkv', 'clip.nfo')
        mirrored(config, placed, unplaced)

        actions = {e.current.name: e.action for e in plan_for(config, [placed, unplaced])}

        assert actions == {'film.mkv': MOVE, 'film.nfo': DROP, 'clip.mkv': UNPARSED, 'clip.nfo': KEEP}

    def test_file_already_in_its_target_directory_is_left_alone(self, config: Config) -> None:
        """
        Test that a link whose folder already matches the layout is not renamed
        """
        torrent = movie('Film (2020)', 'Film.2020.1080p.mkv')
        mirrored(config, torrent)

        [entry] = plan_for(config, [torrent])

        assert entry.action == IN_PLACE

    def test_season_in_the_movies_library_crosses_over(self, config: Config) -> None:
        """
        Test that an episode filed under movies/ is planned into tv/
        """
        torrent = movie('Mini.Series.S01.1080p', 'Mini.Series.S01E01.1080p.mkv')
        mirrored(config, torrent)

        [entry] = plan_for(config, [torrent])

        assert entry.action == CROSS
        assert entry.target == config.tv_root / 'Mini Series' / 'Season 01' / 'Mini Series - S01E01.mkv'

    def test_second_version_of_a_movie_takes_a_quality_suffix(self, config: Config) -> None:
        """
        Test that two releases of one movie both get a place, the later one labelled with its resolution
        """
        hd  = movie('Film.2020.1080p', 'film.mkv')
        uhd = movie('Film.2020.2160p', 'film.mkv')
        mirrored(config, hd, uhd)

        targets = sorted(e.target.name for e in plan_for(config, [hd, uhd]) if e.target)

        assert targets == ['Film (2020) - 2160p.mkv', 'Film (2020).mkv']

    def test_duplicate_episode_is_a_conflict(self, config: Config) -> None:
        """
        Test that a second release of the same episode is reported, not suffixed or overwritten
        """
        a = episode('Show.S01E01.720p')
        b = episode('Show.S01E01.1080p')
        mirrored(config, a, b)

        actions = sorted(e.action for e in plan_for(config, [a, b]))

        assert actions == [CONFLICT, MOVE]

    def test_target_holding_the_same_file_is_redundant(self, config: Config) -> None:
        """
        Test that a target which is already a link of the same file only drops the old link
        """
        torrent = movie('Film.2020.1080p', 'film.mkv')
        mirrored(config, torrent)
        old    = config.movies_root / 'Film.2020.1080p' / 'film.mkv'
        target = config.movies_root / 'Film (2020)' / 'Film (2020).mkv'
        target.parent.mkdir()
        os.link(old, target)

        [entry] = plan_for(config, [torrent])

        assert entry.action == REDUNDANT

    def test_target_held_by_a_different_file_is_a_conflict(self, config: Config) -> None:
        """
        Test that a person's own file at the target is never replaced
        """
        torrent = episode('Show.S01E01.1080p')
        mirrored(config, torrent)
        target = config.tv_root / 'Show' / 'Season 01' / 'Show - S01E01.mkv'
        target.parent.mkdir(parents=True)
        target.write_bytes(b'mine')

        [entry] = plan_for(config, [torrent])

        assert entry.action == CONFLICT

    def test_non_media_files_are_kept(self, config: Config) -> None:
        """
        Test that files that are neither media nor scene leftovers are not touched
        """
        torrent = movie('Film.2020.1080p', 'film.mkv', 'extra.iso')
        mirrored(config, torrent)

        actions = {e.current.name: e.action for e in plan_for(config, [torrent])}

        assert actions['extra.iso'] == KEEP


class TestSelect:
    """
    Tests for select
    """
    def test_only_filters_by_torrent_name_or_path(self, config: Config) -> None:
        """
        Test that --only keeps matching entries and drops the rest
        """
        a = movie('Alpha.2020.1080p', 'a.mkv')
        b = movie('Beta.2021.1080p', 'b.mkv')
        mirrored(config, a, b)

        chosen = select(plan_for(config, [a, b]), only='^alpha')

        assert [e.torrent for e in chosen] == ['Alpha.2020.1080p']

    def test_limit_keeps_whole_torrents_in_name_order(self, config: Config) -> None:
        """
        Test that --limit counts torrents, not files, and takes them alphabetically
        """
        a = movie('Alpha.2020.1080p', 'a.mkv', 'a2.mkv')
        b = movie('Beta.2021.1080p', 'b.mkv')
        mirrored(config, a, b)

        chosen = select(plan_for(config, [a, b]), limit=1)

        assert {e.torrent for e in chosen} == {'Alpha.2020.1080p'}


# ==================================================================================================
# apply_plan / undo
# ==================================================================================================


class TestApplyAndUndo:
    """
    Tests for apply_plan and undo
    """
    def test_apply_moves_links_keeps_seed_journals_and_prunes(self, config: Config) -> None:
        """
        Test that apply relinks, leaves the download untouched, records the move and removes the emptied folder
        """
        torrent = movie('Film.2020.1080p', 'film.mkv', 'film.nfo')
        mirrored(config, torrent)
        source = config.downloads_root / 'complete' / 'movies' / 'Film.2020.1080p' / 'film.mkv'

        result = apply_plan(plan_for(config, [torrent]), config)

        target = config.movies_root / 'Film (2020)' / 'Film (2020).mkv'
        assert result.done == 2
        assert not result.errors
        assert os.path.samestat(source.stat(), target.stat())
        assert source.stat().st_nlink == 2
        assert not (config.movies_root / 'Film.2020.1080p').exists()
        assert config.movies_root.is_dir()
        records = [json.loads(line) for line in config.journal_path.read_text(encoding='utf-8').splitlines()]
        assert sorted(r['op'] for r in records) == ['drop', 'move']

    def test_pass_after_apply_neither_relinks_nor_finds_work(self, config: Config) -> None:
        """
        Test that the loop and a second plan are quiet once the files have moved
        """
        torrent = movie('Film.2020.1080p', 'film.mkv')
        mirrored(config, torrent)
        apply_plan(plan_for(config, [torrent]), config)

        report = reconcile([torrent], config)

        assert report.counts[LINKED] == 0
        assert not (config.movies_root / 'Film.2020.1080p').exists()
        assert discover([torrent], config) == []

    def test_apply_never_overwrites_a_file_that_appeared(self, config: Config) -> None:
        """
        Test that a target created after planning is reported as an error and the old link stays
        """
        torrent = movie('Film.2020.1080p', 'film.mkv')
        mirrored(config, torrent)
        entries = plan_for(config, [torrent])
        target  = config.movies_root / 'Film (2020)' / 'Film (2020).mkv'
        target.parent.mkdir()
        target.write_bytes(b'late arrival')

        result = apply_plan(entries, config)

        assert result.done == 0
        assert len(result.errors) == 1
        assert (config.movies_root / 'Film.2020.1080p' / 'film.mkv').exists()
        assert target.read_bytes() == b'late arrival'

    def test_undo_restores_the_exact_tree(self, config: Config) -> None:
        """
        Test that undo puts moved and dropped links back with the same inodes
        """
        torrent = movie('Film.2020.1080p', 'film.mkv', 'film.nfo')
        mirrored(config, torrent)

        def snapshot() -> dict[str, int]:
            files = (p for p in config.movies_root.rglob('*') if p.is_file())
            return {p.relative_to(config.media_root).as_posix(): p.stat().st_ino for p in files}

        before = snapshot()
        apply_plan(plan_for(config, [torrent]), config)
        assert snapshot() != before

        dry = undo(config, config.journal_path, apply=False)
        assert dry.done == 2
        assert snapshot() != before

        result = undo(config, config.journal_path, apply=True)

        assert result.done == 2
        assert not result.errors
        assert snapshot() == before
        assert not (config.movies_root / 'Film (2020)').exists()

    def test_undo_skips_an_occupied_path_and_a_missing_journal(self, config: Config, tmp_path: Path) -> None:
        """
        Test that undo reports what it cannot restore instead of overwriting or crashing
        """
        torrent = movie('Film.2020.1080p', 'film.mkv')
        mirrored(config, torrent)
        apply_plan(plan_for(config, [torrent]), config)
        occupied = config.movies_root / 'Film.2020.1080p' / 'film.mkv'
        occupied.parent.mkdir()
        occupied.write_bytes(b'someone else')

        result = undo(config, config.journal_path, apply=True)

        assert result.done == 0
        assert 'occupied' in result.errors[0]
        assert occupied.read_bytes() == b'someone else'
        assert undo(config, tmp_path / 'absent.jsonl', apply=True).errors

    def test_prune_stops_at_non_empty_directories(self, config: Config) -> None:
        """
        Test that a folder still holding a file nothing touched is not removed
        """
        torrent = movie('Film.2020.1080p', 'film.mkv')
        mirrored(config, torrent)
        leftover = config.movies_root / 'Film.2020.1080p' / 'mine.txt'
        leftover.write_text('keep', encoding='utf-8')

        apply_plan(plan_for(config, [torrent]), config)

        assert leftover.exists()


# ==================================================================================================
# Jellyfin layout in the loop
# ==================================================================================================


class TestJellyfinLayoutInTheLoop:
    """
    Tests for MEDIALINK_LAYOUT=jellyfin in reconcile
    """
    def test_new_torrent_lands_in_the_titled_layout_without_junk(self, jellyfin: Config) -> None:
        """
        Test that a fresh torrent is linked at its Title (Year) path and its scene leftovers are skipped
        """
        torrent = movie('Film.2020.1080p', 'film.mkv', 'film.nfo')
        write_source(jellyfin, torrent)

        report = reconcile([torrent], jellyfin)

        assert (jellyfin.movies_root / 'Film (2020)' / 'Film (2020).mkv').is_file()
        assert report.counts[LINKED] == 1
        assert report.counts[SKIPPED] == 1
        assert not (jellyfin.movies_root / 'Film.2020.1080p').exists()

    def test_unplaceable_file_falls_back_to_the_mirror(self, jellyfin: Config) -> None:
        """
        Test that a name the parser cannot read is still linked, at its mirrored path
        """
        torrent = movie('Nameless', 'clip.mkv')
        write_source(jellyfin, torrent)

        reconcile([torrent], jellyfin)

        assert (jellyfin.movies_root / 'Nameless' / 'clip.mkv').is_file()

    def test_existing_mirror_links_are_exists_not_duplicated(self, jellyfin: Config) -> None:
        """
        Test that enabling the layout over an already mirrored library creates nothing new
        """
        torrent = movie('Film.2020.1080p', 'film.mkv')
        mirror  = Config.from_env({'MEDIALINK_MEDIA_ROOT': str(jellyfin.media_root)})
        mirrored(mirror, torrent)
        assert (jellyfin.movies_root / 'Film.2020.1080p' / 'film.mkv').exists()

        report = reconcile([torrent], jellyfin)

        assert report.counts[LINKED] == 0
        assert report.counts[EXISTS] == 1
        assert not (jellyfin.movies_root / 'Film (2020)').exists()

    def test_bad_overrides_file_is_a_problem_not_a_crash(self, jellyfin: Config) -> None:
        """
        Test that a damaged overrides.json is reported while the pass still links
        """
        jellyfin.overrides_path.parent.mkdir(parents=True)
        jellyfin.overrides_path.write_text('{broken', encoding='utf-8')
        torrent = movie('Film.2020.1080p', 'film.mkv')
        write_source(jellyfin, torrent)

        report = reconcile([torrent], jellyfin)

        assert [p.key for p in report.problems] == ['overrides']
        assert report.counts[LINKED] == 1

    def test_invalid_layout_value_is_a_config_error(self) -> None:
        """
        Test that an unknown MEDIALINK_LAYOUT is rejected
        """
        with pytest.raises(ConfigError):
            Config.from_env({'MEDIALINK_LAYOUT': 'plex'})


# ==================================================================================================
# Command
# ==================================================================================================


class TestReorganizeCommand:
    """
    Tests for the reorganize CLI command
    """
    def test_dry_run_then_apply_then_undo(
        self,
        config: Config,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test the full command cycle: a dry run changes nothing, apply moves, undo restores
        """
        torrent = movie('Film.2020.1080p', 'film.mkv')
        mirrored(config, torrent)
        monkeypatch.setenv('MEDIALINK_MEDIA_ROOT', str(config.media_root))
        monkeypatch.setattr(TransmissionClient, 'get_torrents', lambda _self: [torrent])

        assert main(['reorganize']) == EXIT_OK
        assert 'dry run' in capsys.readouterr().out
        assert (config.movies_root / 'Film.2020.1080p' / 'film.mkv').exists()

        assert main(['reorganize', '--apply']) == EXIT_OK
        assert 'applied: 1' in capsys.readouterr().out
        assert (config.movies_root / 'Film (2020)' / 'Film (2020).mkv').exists()

        assert main(['reorganize', '--undo', str(config.journal_path), '--apply']) == EXIT_OK
        assert (config.movies_root / 'Film.2020.1080p' / 'film.mkv').exists()

    def test_unparsed_files_make_the_exit_code_nonzero(
        self,
        config: Config,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that a plan with files that cannot be placed reports them and exits with EXIT_PROBLEMS
        """
        torrent = movie('Nameless', 'clip.mkv')
        mirrored(config, torrent)
        monkeypatch.setenv('MEDIALINK_MEDIA_ROOT', str(config.media_root))
        monkeypatch.setattr(TransmissionClient, 'get_torrents', lambda _self: [torrent])

        assert main(['reorganize']) == EXIT_PROBLEMS
        assert 'unparsed' in capsys.readouterr().out

    def test_bad_overrides_exit_with_config_code(self, config: Config, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that an unusable overrides file stops the command before anything is planned
        """
        config.overrides_path.parent.mkdir(parents=True)
        config.overrides_path.write_text('{broken', encoding='utf-8')
        monkeypatch.setenv('MEDIALINK_MEDIA_ROOT', str(config.media_root))
        monkeypatch.setattr(TransmissionClient, 'get_torrents', lambda _self: [])

        assert main(['reorganize']) == EXIT_CONFIG
