"""
Decide where a torrent's file belongs in a Jellyfin/Plex-style library (``Movie (Year)/``, ``Show/Season NN/``)

Pure and offline: the answer comes from the release names alone, plus an optional overrides file for the names the
parser cannot read. A name it cannot place yields None; callers report it and leave the file where it is.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from medialink.classify import MOVIES
from medialink.classify import TV
from medialink.config import ConfigError

if TYPE_CHECKING:
    from collections.abc import Collection
    from collections.abc import Iterable
    from collections.abc import Sequence
    from pathlib import Path

__all__ = [
    'JUNK',
    'OTHER',
    'SUBTITLE',
    'VIDEO',
    'Override',
    'Placement',
    'kind',
    'load_overrides',
    'place',
]

VIDEO    = 'video'
SUBTITLE = 'subtitle'
JUNK     = 'junk'    # scene leftovers (.nfo, .sfv, artwork, samples): not carried into the new layout
OTHER    = 'other'   # anything else; never moved

VIDEO_EXTENSIONS    = frozenset({'.mkv', '.mp4', '.avi', '.m4v', '.mov', '.divx', '.wmv', '.mpg', '.mpeg', '.m2ts'})
SUBTITLE_EXTENSIONS = frozenset({'.srt', '.sub', '.idx', '.ass', '.ssa', '.vtt', '.sup'})
JUNK_EXTENSIONS     = frozenset({'.nfo', '.sfv', '.png', '.jpg', '.jpeg', '.txt', '.url', '.md5', '.exe', '.diz'})

# Folder names whose videos are bonus material that cannot be placed as an episode or a feature
EXTRAS_DIRS = frozenset({'extras', 'extra', 'featurettes', 'behind the scenes', 'bonus', 'deleted scenes', 'trailers'})

LANGUAGES: dict[str, str] = {
    'en': 'en', 'eng': 'en', 'english': 'en',
    'es': 'es', 'spa': 'es', 'spanish': 'es',
    'fr': 'fr', 'fre': 'fr', 'fra': 'fr', 'french': 'fr',
    'de': 'de', 'ger': 'de', 'deu': 'de', 'german': 'de',
    'it': 'it', 'ita': 'it', 'italian': 'it',
    'pt': 'pt', 'por': 'pt', 'portuguese': 'pt',
    'nl': 'nl', 'dut': 'nl', 'dutch': 'nl',
    'ru': 'ru', 'rus': 'ru', 'russian': 'ru',
    'ja': 'ja', 'jpn': 'ja', 'japanese': 'ja',
    'ko': 'ko', 'kor': 'ko', 'korean': 'ko',
    'zh': 'zh', 'chi': 'zh', 'chinese': 'zh',
    # Languages seen in scene subtitle packs; their ISO 639-2 codes are kept as they are
    **{code: code for code in (
        'ara', 'ces', 'cze', 'dan', 'fil', 'fin', 'gre', 'heb', 'hrv', 'hun', 'ind', 'may', 'nob', 'nor', 'pol', 'rum',
        'swe', 'tha', 'tur', 'ukr', 'vie',
    )},
}
SUBTITLE_FLAGS = frozenset({'forced', 'sdh', 'cc', 'default'})

_BOUNDARY = r'(?<![A-Za-z0-9])'
_END      = r'(?![A-Za-z0-9])'

# Tokens that mark where a release name stops being the title
_QUALITY = re.compile(
    _BOUNDARY
    + r'(?:(?:480|576|720|1080|2160)[pi]|4k|uhd|blu-?ray|bdrip|brrip|bdremux|web-?dl|web-?rip|web|hdtv|dvdrip|dvd|'
    + r'remux|hdrip|hevc|x26[45]|h\.?26[45]|av1|avc|10bit|hdr10?|dv|repack|proper|rerip|extended|unrated|imax|'
    + r'internal|multi|dual|complete|telesync|cam)'
    + _END,
    re.IGNORECASE,
)
_YEAR = re.compile(_BOUNDARY + r'(?<!\d-)(?:19|20)\d{2}(?!-\d)' + _END)

# Episode markers, in order of confidence
_EPISODE = re.compile(
    _BOUNDARY + r's(?P<season>\d{1,2})[ ._-]?e(?P<ep>\d{1,3})(?P<more>(?:[ ._-]?e\d{1,3})*)' + _END,
    re.IGNORECASE,
)
_EPISODE_X = re.compile(_BOUNDARY + r'(?P<season>\d{1,2})x(?P<ep>\d{2,3})' + _END, re.IGNORECASE)
_MARKER    = re.compile(
    _BOUNDARY + r'(?:s\d{1,2}(?:[ ._-]?e\d{1,3})*|\d{1,2}x\d{2,3}|season[ ._-]?\d{1,2}|complete[ ._-]series)' + _END,
    re.IGNORECASE,
)
_RESOLUTION = re.compile(r'\d{3,4}[pi]|4k')
_BRACKETS   = re.compile(r'\[[^\]]*\]')
_ILLEGAL    = re.compile(r'[<>"/\\|?*]')


@dataclass(frozen=True)
class Override:
    """
    A hand-written correction: any torrent whose name matches ``pattern`` is filed under ``title``
    """
    pattern:  re.Pattern[str]
    title:    str
    year:     int | None = None
    category: str | None = None


@dataclass(frozen=True)
class Placement:
    """
    Where one file goes, relative to the media root (``movies/...`` or ``tv/...``)

    ``version`` is a quality label (``2160p``) used to make a second copy of the same movie distinct
    (``Title (Year) - 2160p.mkv``); episodes never take one.
    """
    category:  str
    directory: str
    filename:  str
    version:   str = ''
    stem:      str = ''

    @property
    def path(self) -> str:
        """
        The placement as a posix path below the library root (without the ``movies``/``tv`` prefix)
        """
        return f'{self.directory}/{self.filename}'

    def with_version(self) -> Placement | None:
        """
        The alternate placement that carries the quality label, for a second version of a movie

        :return: the labelled placement, or None for episodes and when no label is known
        """
        if (self.category != MOVIES) or not self.version:
            return None

        suffix = PurePosixPath(self.filename).suffixes
        tail   = ''.join(suffix[-2:] if len(suffix) > 1 and len(suffix[-2]) <= 4 else suffix[-1:])
        stem   = self.filename[: len(self.filename) - len(tail)]
        return Placement(self.category, self.directory, f'{stem} - {self.version}{tail}', self.version, self.stem)


def kind(file_name: str) -> str:
    """
    Classify a torrent file by what the library should do with it

    :param file_name: torrent-relative file name
    :return: ``video``, ``subtitle``, ``junk`` (scene leftovers and sample clips) or ``other``
    """
    path = PurePosixPath(file_name)
    ext  = path.suffix.lower()
    if ext in VIDEO_EXTENSIONS:
        if any(re.match(r'sample\b', part, re.IGNORECASE) for part in path.parts[:-1]) or re.search(
            _BOUNDARY + r'sample' + _END,
            path.stem,
            re.IGNORECASE
        ):
            return JUNK
        return VIDEO
    if ext in SUBTITLE_EXTENSIONS:
        return SUBTITLE
    if ext in JUNK_EXTENSIONS:
        return JUNK
    return OTHER


def load_overrides(path: Path) -> list[Override]:
    """
    Read the overrides file

    The file is a JSON list of ``{"pattern": regex, "title": str, "year": int?, "category": "movies"|"tv"?}`` objects.
    A missing file means no overrides; a malformed one is an error rather than being silently ignored, because a typo
    would otherwise file things somewhere unintended.

    :param path: ``overrides.json``
    :raises ConfigError: if the file exists but is not valid
    :return: the overrides, first match wins
    """
    try:
        raw = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return []
    except (OSError, ValueError) as e:
        raise ConfigError(f'cannot read overrides {path}: {e}') from e

    if not isinstance(raw, list):
        raise ConfigError(f'overrides {path} must be a JSON list')

    overrides: list[Override] = []
    for i, item in enumerate(raw):
        valid = isinstance(item, dict) and all(isinstance(item.get(k), str) for k in ('pattern', 'title'))
        if not valid:
            raise ConfigError(f'overrides {path} entry {i} needs string "pattern" and "title"')

        year     = item.get('year')
        category = item.get('category')
        if (year is not None) and (not isinstance(year, int) or isinstance(year, bool)):
            raise ConfigError(f'overrides {path} entry {i}: "year" must be an integer')
        if category not in {None, MOVIES, TV}:
            raise ConfigError(f'overrides {path} entry {i}: "category" must be "movies" or "tv"')

        try:
            pattern = re.compile(item['pattern'], re.IGNORECASE)
        except re.error as e:
            raise ConfigError(f'overrides {path} entry {i}: bad pattern: {e}') from e

        overrides.append(Override(pattern, item['title'].strip(), year, category))

    return overrides


def _normalise(text: str) -> str:
    """
    Turn a release-style name into words: dots and underscores become spaces when the name uses them as separators

    :param text: a file or folder name without its extension
    :return: the name with separators normalised
    """
    text = _BRACKETS.sub(' ', text)
    if ' ' not in text.strip():
        text = text.replace('.', ' ').replace('_', ' ')
    return re.sub(r'\s+', ' ', text).strip()


def _tidy(title: str) -> str:
    """
    Make a title safe and tidy as a directory name

    :param title: raw title text
    :return: the title without illegal characters, dangling separators or empty brackets
    """
    title = title.replace(':', ' -')
    title = _ILLEGAL.sub('', title)
    title = re.sub(r'\(\s*\)', '', title)
    title = re.sub(r'\s+', ' ', title)
    return title.strip(' -._([')


def _movie_name(text: str) -> tuple[str, int] | None:
    """
    Read a movie title and year from one name

    :param text: file or folder name without extension
    :return: ``(title, year)``, or None when the name carries no title and year
    """
    text    = _normalise(text)
    quality = _QUALITY.search(text)
    limit   = quality.start() if quality else len(text)
    years   = [m for m in _YEAR.finditer(text) if 0 < m.start() < limit]
    if not years:
        return None

    last  = years[-1]
    title = _tidy(text[: last.start()])
    return (title, int(last.group())) if title else None


def _episode_of(text: str) -> tuple[int, str] | None:
    """
    Read season and episode designation from a name

    :param text: file name without extension
    :return: ``(season, episode label such as "S01E02" or "S01E02-E03")``, or None when there is no episode marker
    """
    if m := _EPISODE.search(text):
        season = int(m.group('season'))
        label  = f'S{season:02d}E{int(m.group("ep")):02d}'
        extra  = re.findall(r'e(\d{1,3})', m.group('more') or '', re.IGNORECASE)
        if extra:
            label += '-' + '-'.join(f'E{int(e):02d}' for e in extra)
        return season, label

    if m := _EPISODE_X.search(text):
        season = int(m.group('season'))
        return season, f'S{season:02d}E{int(m.group("ep")):02d}'

    return None


def _show_name(text: str) -> tuple[str, int | None]:
    """
    Read a show title (and a year printed before the marker) from a name

    :param text: file or folder name without extension
    :return: ``(title, year)``; the title is empty when nothing precedes the episode or season marker
    """
    text   = _normalise(text)
    marker = _MARKER.search(text)
    head   = text[: marker.start()] if marker else text
    if not marker:
        quality = _QUALITY.search(head)
        head    = head[: quality.start()] if quality else head

    year  = None
    years = [m for m in _YEAR.finditer(head) if m.start() > 0]
    if years and (head[years[-1].end():].strip(' ()-') == ''):
        year = int(years[-1].group())
        head = head[: years[-1].start()]

    return _tidy(head), year


def _key(name: str) -> str:
    """
    Comparison key for show names: case, punctuation and a trailing ``(Year)`` are ignored

    :param name: show title or directory name
    :return: lower-case alphanumerics only
    """
    return re.sub(r'[^a-z0-9]', '', re.sub(r'\s*\((?:19|20)\d{2}\)\s*$', '', name).lower())


def _best_case(title: str, others: Iterable[str]) -> str:
    """
    Prefer a properly cased spelling of the same title over an all-lower or all-upper one

    Release folders are usually cased well while the files inside them are often not (or the reverse).

    :param title: the title read from the most specific name
    :param others: titles read from the other candidate names
    :return: ``title`` when it is mixed-case already, otherwise a mixed-case spelling that matches it
    """
    if title not in {title.lower(), title.upper()}:
        return title
    for other in others:
        if other and (other not in {other.lower(), other.upper()}) and (_key(other) == _key(title)):
            return other
    return title


def _show_folder(title: str, year: int | None, forced: bool, shows: Collection[str]) -> str:
    """
    Pick the directory name for a show, reusing one that already exists

    A year is only part of a new directory's name when an override asks for it (``forced``); a release's own year is
    used just to choose between existing ``Show (Year)`` directories.

    :param title: show title
    :param year: year printed in the release, or from an override
    :param forced: whether ``year`` came from an override and must appear in the name
    :param shows: names of the show directories that already exist
    :return: directory name
    """
    exact = f'{title} ({year})' if year else ''
    if forced and year:
        return exact

    existing = sorted(s for s in shows if _key(s) == _key(title))
    if year and (exact in existing):
        return exact
    if existing:
        return existing[0]
    return title


def _subtitle_suffix(stem: str) -> str:
    """
    Extract the language (and flags) a subtitle file name carries

    :param stem: subtitle file name without extension
    :return: ``.en`` or ``.en.forced`` style suffix, empty when no language is recognised
    """
    words = [w.lower() for w in re.split(r'[ ._()-]+', stem) if w]
    flags = [w for w in words if w in SUBTITLE_FLAGS]
    for word in reversed(words):
        if word in LANGUAGES:
            return ''.join(f'.{part}' for part in (LANGUAGES[word], *flags))
    return ''.join(f'.{flag}' for flag in flags)


def place(
    category: str,
    torrent_name: str,
    file_name: str,
    overrides: Sequence[Override] = (),
    shows: Collection[str] = (),
) -> Placement | None:
    """
    Work out where a torrent file belongs

    Candidates are tried from the most specific name outwards: the file's own name, its folders, then the torrent name.
    The first one that yields a title (and, for movies, a year) wins.

    :param category: library the torrent was classified into (``movies`` or ``tv``)
    :param torrent_name: Transmission's name for the torrent
    :param file_name: torrent-relative file name
    :param overrides: hand-written corrections, first match wins
    :param shows: names of the directories already in ``tv/``, so an existing show folder is reused
    :return: the placement, or None when the name cannot be placed (junk, extras, no readable title)
    """
    file_kind = kind(file_name)
    if file_kind not in {VIDEO, SUBTITLE}:
        return None

    path    = PurePosixPath(file_name)
    folders = list(path.parts[:-1])
    if any(part.lower() in EXTRAS_DIRS for part in folders):
        return None

    override = next((o for o in overrides if o.pattern.search(torrent_name)), None)
    if override and override.category:
        category = override.category

    stem      = path.stem
    suffix    = ''
    extension = path.suffix.lower()
    if file_kind == SUBTITLE:
        suffix = _subtitle_suffix(stem)

    names = [stem, *reversed(folders), torrent_name]

    episode = _episode_of(stem)
    if episode is None and category == TV:
        # A season folder plus a bare episode number is not enough to be sure; require a real marker.
        return None
    if episode is not None:
        return _place_episode(names, episode, extension, suffix, override=override, shows=shows)
    if category == TV:
        return None

    return _place_movie(names, extension, suffix, override)


def _place_episode(
    names: list[str],
    episode: tuple[int, str],
    extension: str,
    suffix: str,
    *,
    override: Override | None,
    shows: Collection[str],
) -> Placement | None:
    """
    Build the placement of an episode file

    :param names: candidate names, most specific first
    :param episode: ``(season, label)`` read from the file name
    :param extension: lower-cased file extension
    :param suffix: subtitle language suffix, or empty
    :param override: matching override, if any
    :param shows: existing show directories
    :return: the placement, or None when no show title can be read
    """
    season, label = episode
    title, year   = '', None
    if override:
        title, year = override.title, override.year
    else:
        # A purely numeric title is usually an absolute episode number ("378 S30E01 (...)"), not the show, so it only
        # counts when no other name offers a title (a show really called "1883")
        numeric: tuple[str, int | None] | None = None
        for candidate in names:
            title, year = _show_name(candidate)
            if title.isdigit():
                numeric = numeric or (title, year)
                title   = ''
            if title:
                break
        else:
            title, year = numeric or ('', None)
    if not title:
        return None
    if not override:
        title = _best_case(title, [_show_name(n)[0] for n in names])

    forced    = bool(override and override.year)
    folder    = _show_folder(_tidy(title), year, forced, shows)
    directory = f'{folder}/Season {season:02d}'
    return Placement(TV, directory, f'{_tidy(title)} - {label}{suffix}{extension}', stem=label)


def _place_movie(
    names: list[str],
    extension: str,
    suffix: str,
    override: Override | None,
) -> Placement | None:
    """
    Build the placement of a movie file

    :param names: candidate names, most specific first
    :param extension: lower-cased file extension
    :param suffix: subtitle language suffix, or empty
    :param override: matching override, if any
    :return: the placement, or None when no title and year can be read
    """
    parsed: tuple[str, int] | None = None
    source = names[0]
    for candidate in names:
        if parsed := _movie_name(candidate):
            source = candidate
            break
    if override:
        year = override.year or (parsed[1] if parsed else None)
        if year is None:
            return None
        parsed = (_tidy(override.title), year)
    if parsed is None:
        return None

    title, year = parsed
    if not override:
        title = _best_case(title, [m[0] for n in names if (m := _movie_name(n))])
    name = f'{title} ({year})'

    # The quality label comes from the name the title was read from, falling back to the others (a subtitle file
    # called "English.srt" says nothing about the movie's quality)
    version = ''
    for candidate in (source, *names):
        if quality := _QUALITY.search(_normalise(candidate)):
            label = quality.group().lower()
            if _RESOLUTION.fullmatch(label):
                version = label
                break

    return Placement(MOVIES, name, f'{name}{suffix}{extension}', version=version, stem=name)
