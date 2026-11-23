"""
Tests for the medialink library inode index and the state records that keep moved files from being re-created
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from medialink.archives import Extractor
from medialink.config import Config
from medialink.engine import reconcile
from medialink.index import build_index
from medialink.index import inode_key
from medialink.linker import EXISTS
from medialink.linker import LINKED
from medialink.linker import link_torrent
from medialink.state import State
from tests.unit.services.test_medialink import FakeRunner
from tests.unit.services.test_medialink import archive_torrent
from tests.unit.services.test_medialink import make_torrent
from tests.unit.services.test_medialink import write_source


@pytest.fixture
def config(tmp_path: Path) -> Config:
    """
    Configuration rooted in a temporary media directory with the library layout created
    """
    media = tmp_path / 'media'
    for sub in ('downloads/complete', 'movies', 'tv'):
        (media / sub).mkdir(parents=True)
    return Config.from_env({'MEDIALINK_MEDIA_ROOT': str(media), 'MEDIALINK_NTFY_URL': 'http://ntfy.invalid'})


class TestBuildIndex:
    """
    Tests for build_index
    """
    def test_indexes_only_multiply_linked_regular_files(self, tmp_path: Path) -> None:
        """
        Test that single-link files and symlinks are skipped while a hardlinked file is found by inode
        """
        root = tmp_path / 'lib'
        root.mkdir()
        outside = tmp_path / 'seed.mkv'
        outside.write_bytes(b'x')
        os.link(outside, root / 'linked.mkv')
        (root / 'single.mkv').write_bytes(b'y')
        (root / 'sym.mkv').symlink_to(outside)

        index = build_index(root)

        assert list(index.values()) == [root / 'linked.mkv']
        assert inode_key(outside) in index

    def test_missing_root_is_skipped(self, tmp_path: Path) -> None:
        """
        Test that a library root that does not exist yields an empty index
        """
        assert build_index(tmp_path / 'absent') == {}

    def test_inode_key_of_missing_file_is_none(self, tmp_path: Path) -> None:
        """
        Test that an unreadable path has no inode key
        """
        assert inode_key(tmp_path / 'absent') is None


class TestMovedLinks:
    """
    Tests that a link moved within the library is not created a second time
    """
    def test_moved_link_is_exists_not_linked(self, config: Config) -> None:
        """
        Test that, once the library link moves, the next pass reports exists and creates nothing at the old path
        """
        torrent = make_torrent('Film.2020.1080p', {'Film.2020.1080p/film.mkv': 10})
        write_source(config, torrent)
        reconcile([torrent], config)

        old = config.movies_root / 'Film.2020.1080p' / 'film.mkv'
        new = config.movies_root / 'Film (2020)' / 'Film (2020).mkv'
        new.parent.mkdir()
        old.rename(new)

        report = reconcile([torrent], config)

        assert not old.exists()
        assert report.counts[EXISTS] == 1
        assert report.counts[LINKED] == 0

    def test_deleted_link_is_recreated(self, config: Config) -> None:
        """
        Test that removing a library link altogether still heals on the next pass
        """
        torrent = make_torrent('Film.2020.1080p', {'Film.2020.1080p/film.mkv': 10})
        write_source(config, torrent)
        reconcile([torrent], config)

        (config.movies_root / 'Film.2020.1080p' / 'film.mkv').unlink()

        report = reconcile([torrent], config)

        assert report.counts[LINKED] == 1

    def test_link_torrent_without_index_still_links(self, config: Config) -> None:
        """
        Test that omitting the index keeps the previous behaviour
        """
        torrent = make_torrent('Film.2020.1080p', {'Film.2020.1080p/film.mkv': 10})
        write_source(config, torrent)

        results = link_torrent(torrent, config.downloads_root / 'complete' / 'movies', config.movies_root)

        assert [r.status for r in results] == [LINKED]

    def test_extraction_is_not_repeated_after_its_output_moves(self, config: Config) -> None:
        """
        Test that a finished extraction stays finished when its files are moved elsewhere in the library
        """
        runner    = FakeRunner({'Rel.mkv': b'video'})
        extractor = Extractor('/usr/bin/7z', runner)
        torrent   = archive_torrent()
        write_source(config, torrent)
        state = State(config.state_path)

        first = reconcile([torrent], config, state=state, extractor=extractor)
        assert first.counts['extracted'] == 1

        outputs = [p for paths in state.outputs.values() for p in paths]
        assert outputs
        for relative in outputs:
            moved = config.media_root / 'tv' / 'Moved' / Path(relative).name
            moved.parent.mkdir(exist_ok=True)
            (config.media_root / relative).rename(moved)

        second = reconcile([torrent], config, state=state, extractor=extractor)

        assert second.counts['extracted'] == 0
        assert len(runner.calls) == 1


class TestStateOutputs:
    """
    Tests for the extraction records kept in State
    """
    def test_outputs_roundtrip(self, tmp_path: Path) -> None:
        """
        Test that recorded extraction outputs persist and are returned as copies
        """
        path  = tmp_path / 'state.json'
        state = State(path)
        state.record_outputs('extracted:h:a.rar', ['tv/Show/b.mkv', 'tv/Show/a.mkv'])
        state.save()

        reloaded = State(path)

        assert reloaded.outputs == {'extracted:h:a.rar': ['tv/Show/a.mkv', 'tv/Show/b.mkv']}
        reloaded.outputs['x'] = []
        assert 'x' not in reloaded.outputs

    def test_state_file_without_outputs_still_loads(self, tmp_path: Path) -> None:
        """
        Test that a state file written before outputs existed keeps its keys and has no outputs
        """
        path = tmp_path / 'state.json'
        path.write_text(json.dumps({'notified': ['link:a']}), encoding='utf-8')

        state = State(path)

        assert 'link:a' in state
        assert state.outputs == {}

    def test_malformed_outputs_degrade_to_empty(self, tmp_path: Path) -> None:
        """
        Test that a damaged extracted section does not crash the service
        """
        path = tmp_path / 'state.json'
        path.write_text(json.dumps({'notified': ['k'], 'extracted': ['not', 'a', 'dict']}), encoding='utf-8')

        assert State(path).outputs == {}
