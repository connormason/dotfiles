"""
Tests for medialink.layout: reading release names into Jellyfin/Plex library paths
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from medialink.config import ConfigError
from medialink.layout import JUNK
from medialink.layout import OTHER
from medialink.layout import SUBTITLE
from medialink.layout import VIDEO
from medialink.layout import Override
from medialink.layout import kind
from medialink.layout import load_overrides
from medialink.layout import place

CASES_FILE = Path(__file__).parent / 'data' / 'release_names.json'
CASES      = json.loads(CASES_FILE.read_text(encoding='utf-8'))


# ==================================================================================================
# Helpers
# ==================================================================================================


def _overrides(raw: list[dict[str, Any]]) -> list[Override]:  # Any: JSON fixture values
    """
    Build Override objects from fixture entries
    """
    return [
        Override(re.compile(o['pattern'], re.IGNORECASE), o['title'], o.get('year'), o.get('category'))
        for o in raw
    ]


# ==================================================================================================
# Unit tests
# ==================================================================================================


class TestPlace:
    """
    Tests for place, driven by a fixture of release names modelled on this library
    """
    @pytest.mark.parametrize('case', CASES, ids=[c['id'] for c in CASES])
    def test_release_names(self, case: dict[str, Any]) -> None:  # Any: JSON fixture values
        """
        Test that each fixture release name is placed exactly as written, or left unplaced
        """
        placement = place(
            case['category'],
            case['torrent'],
            case['file'],
            _overrides(case.get('overrides', [])),
            case.get('shows', ()),
        )

        if case['expect'] is None:
            assert placement is None
        else:
            assert placement is not None
            assert f'{placement.category}/{placement.path}' == case['expect']

    def test_illegal_characters_are_removed_from_titles(self) -> None:
        """
        Test that a colon becomes a dash and other filesystem-hostile characters are dropped
        """
        placement = place(
            'movies',
            'Mission.Impossible.Fallout.2018.1080p.BluRay',
            'Mission.Impossible.Fallout.2018.1080p.BluRay.mkv',
            [Override(re.compile('Mission'), 'Mission: Impossible - Fallout?', 2018)],
        )

        assert placement is not None
        assert placement.directory == 'Mission - Impossible - Fallout (2018)'


class TestSubtitleLanguages:
    """
    Tests for the language suffix of scene-pack subtitle files
    """
    @pytest.mark.parametrize(
        'code',
        ['hin', 'lit', 'slo', 'slv', 'tam', 'tel', 'cat', 'glg'],
    )
    def test_scene_pack_language_codes_are_kept(self, code: str) -> None:
        """
        Test that each ISO 639-2 code seen in scene subtitle packs gets its own file name
        """
        torrent   = 'Film.2020.1080p.BluRay.x264-GRP'
        placement = place('movies', torrent, f'{torrent}/Subs/{code}.srt')

        assert placement is not None
        assert placement.filename == f'Film (2020).{code}.srt'


class TestPlacement:
    """
    Tests for Placement
    """
    def test_second_movie_version_carries_the_quality_label(self) -> None:
        """
        Test that with_version appends the resolution before the extension
        """
        placement = place('movies', 'Deadpool.2016.1080p.BluRay', 'Deadpool.2016.1080p.BluRay.mkv')
        assert placement is not None

        alternate = placement.with_version()
        assert alternate is not None
        assert alternate.path == 'Deadpool (2016)/Deadpool (2016) - 1080p.mkv'

    def test_labelled_subtitle_keeps_its_language_suffix(self) -> None:
        """
        Test that the quality label goes before the language suffix of a subtitle
        """
        placement = place('movies', 'Film.2020.2160p.WEB', 'Film.2020.2160p.WEB/Subs/English.srt')
        assert placement is not None

        alternate = placement.with_version()
        assert alternate is not None
        assert alternate.filename == 'Film (2020) - 2160p.en.srt'

    def test_episodes_have_no_alternate_version(self) -> None:
        """
        Test that a duplicate episode is a conflict, never auto-suffixed
        """
        placement = place('tv', 'Show.S01E01.1080p', 'Show.S01E01.1080p.mkv')

        assert placement is not None
        assert placement.with_version() is None


class TestKind:
    """
    Tests for kind
    """
    @pytest.mark.parametrize(
        ('name', 'expected'),
        [
            ('Rel/film.MKV',               VIDEO),
            ('Rel/film.m2ts',              VIDEO),
            ('Rel/Subs/en.srt',            SUBTITLE),
            ('Rel/film.nfo',               JUNK),
            ('Rel/film.sfv',               JUNK),
            ('Rel/poster.png',             JUNK),
            ('Rel/Sample/film-sample.mkv', JUNK),
            ('Rel/film.sample.mkv',        JUNK),
            ('Rel/Samantha.2020.mkv',      VIDEO),
            ('Rel/film.rar',               OTHER),
            ('Rel/film.iso',               OTHER),
        ],
    )
    def test_classification(self, name: str, expected: str) -> None:
        """
        Test that files are sorted into video, subtitle, junk and other by extension and sample markers
        """
        assert kind(name) == expected


class TestLoadOverrides:
    """
    Tests for load_overrides
    """
    def test_missing_file_means_no_overrides(self, tmp_path: Path) -> None:
        """
        Test that an absent overrides file is not an error
        """
        assert load_overrides(tmp_path / 'overrides.json') == []

    def test_valid_file_is_parsed(self, tmp_path: Path) -> None:
        """
        Test that patterns compile case-insensitively and optional fields are kept
        """
        path = tmp_path / 'overrides.json'
        path.write_text(
            json.dumps([{'pattern': 'weird', 'title': ' Weird ', 'year': 1999, 'category': 'movies'}]),
            encoding='utf-8',
        )

        [override] = load_overrides(path)

        assert override.pattern.search('WEIRD thing')
        assert (override.title, override.year, override.category) == ('Weird', 1999, 'movies')

    @pytest.mark.parametrize(
        'content',
        [
            '{not json',
            '{"pattern": "a", "title": "b"}',
            '[{"pattern": "a"}]',
            '[{"pattern": "(", "title": "b"}]',
            '[{"pattern": "a", "title": "b", "year": "1999"}]',
            '[{"pattern": "a", "title": "b", "year": true}]',
            '[{"pattern": "a", "title": "b", "category": "music"}]',
        ],
    )
    def test_malformed_file_is_an_error(self, tmp_path: Path, content: str) -> None:
        """
        Test that a damaged overrides file raises instead of being ignored
        """
        path = tmp_path / 'overrides.json'
        path.write_text(content, encoding='utf-8')

        with pytest.raises(ConfigError):
            load_overrides(path)
