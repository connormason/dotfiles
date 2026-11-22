"""
Decide whether a finished torrent belongs in the movies or the TV library
"""
from __future__ import annotations

import re
from pathlib import PurePosixPath

__all__ = [
    'MOVIES',
    'TV',
    'classify',
]

MOVIES = 'movies'
TV     = 'tv'

# Transmission labels and download-directory names that carry an explicit category. 'movie' (singular) exists in the
# wild: four torrents were added with that directory and silently skipped by the tool this one replaces.
LABEL_CATEGORIES: dict[str, str] = {
    'tv':     TV,
    'shows':  TV,
    'movies': MOVIES,
    'movie':  MOVIES,
    'film':   MOVIES,
}

# 'S01E02', 'S01', 'S01-S06', 'S01.to.S14', 'Season 3', 'Complete Series': anything episodic.
_TV_PATTERN    = re.compile(
    r'(?<![a-z0-9])(s\d{1,2}(e\d{1,3})?|season[ ._-]?\d+|complete[ ._-]series)(?![a-z0-9])',
    re.IGNORECASE,
)
_MOVIE_PATTERN = re.compile(r'(?<!\d)(19|20)\d{2}(?!\d)')


def _from_labels(labels: tuple[str, ...]) -> str | None:
    """
    Resolve a category from Transmission labels

    :param labels: torrent labels
    :return: the category, or None when no label names one
    """
    for label in labels:
        if category := LABEL_CATEGORIES.get(label.strip().lower()):
            return category
    return None


def _from_directory(download_dir: str) -> str | None:
    """
    Resolve a category from the directory Transmission saved the torrent in

    The deepest matching path component wins, and trailing slashes are ignored.

    :param download_dir: Transmission's ``downloadDir``
    :return: the category, or None when the path names none (for example the bare ``complete`` directory)
    """
    for part in reversed(PurePosixPath(download_dir).parts):
        if category := LABEL_CATEGORIES.get(part.lower()):
            return category
    return None


def _from_name(name: str) -> str | None:
    """
    Guess a category from the release name

    :param name: torrent name
    :return: ``tv`` for episodic names, ``movies`` for names containing a year, otherwise None
    """
    if _TV_PATTERN.search(name):
        return TV
    if _MOVIE_PATTERN.search(name):
        return MOVIES
    return None


def classify(name: str, download_dir: str, labels: tuple[str, ...] = ()) -> str | None:
    """
    Pick the library a torrent belongs to

    Precedence is label, then download directory, then release-name heuristics.

    Examples:

        >>> classify('Dune.2021.1080p', '/downloads/complete')
        'movies'
        >>> classify('Show.S01E02.1080p', '/downloads/complete/movie/')
        'movies'

    :param name: torrent name
    :param download_dir: Transmission's ``downloadDir``
    :param labels: torrent labels
    :return: ``'movies'``, ``'tv'``, or None when the torrent cannot be placed confidently
    """
    return _from_labels(labels) or _from_directory(download_dir) or _from_name(name)
