"""
Runtime configuration, read from the environment
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    'JELLYFIN',
    'LAYOUTS',
    'MIRROR',
    'Config',
    'ConfigError',
]

DEFAULT_MEDIA_ROOT   = '/storage/media'
DEFAULT_RPC_URL      = 'http://transmission:9091/transmission/rpc'
DEFAULT_DOWNLOADS    = '/downloads'
DEFAULT_INTERVAL     = 60
DEFAULT_MAX_FAILURES = 5
DEFAULT_NTFY_TOPIC   = 'nas-media'
FALSE_VALUES         = frozenset({'0', 'false', 'no', 'off'})
MIRROR               = 'mirror'     # library mirrors each torrent's own layout
JELLYFIN             = 'jellyfin'   # Movie (Year)/ and Show/Season NN/, scene leftovers not linked
LAYOUTS              = (MIRROR, JELLYFIN)
DEFAULT_LAYOUT       = MIRROR


class ConfigError(ValueError):
    """
    Raised when an environment variable holds an unusable value
    """
    pass


def _int_env(env: dict[str, str], name: str, default: int, *, minimum: int = 1) -> int:
    """
    Read an integer environment variable

    :param env: environment mapping
    :param name: variable name
    :param default: value used when the variable is unset or empty
    :param minimum: smallest accepted value
    :raises ConfigError: if the value is not an integer or is below the minimum
    :return: the parsed value
    """
    raw = env.get(name, '').strip()
    if not raw:
        return default

    try:
        value = int(raw)
    except ValueError as e:
        raise ConfigError(f'{name} must be an integer, got {raw!r}') from e
    if value < minimum:
        raise ConfigError(f'{name} must be >= {minimum}, got {value}')

    return value


@dataclass(frozen=True)
class Config:
    """
    Settings for one medialink process

    ``transmission_downloads`` is the path under which *Transmission* sees its download tree (it reports
    ``downloadDir`` in its own container's namespace). It is mapped onto ``<media_root>/downloads`` locally.
    """
    media_root:             Path
    rpc_url:                str
    rpc_user:               str
    rpc_password:           str
    transmission_downloads: str
    interval:               int
    max_failures:           int
    ntfy_url:               str
    ntfy_topic:             str
    ntfy_token:             str
    state_path:             Path
    extract:                bool
    extractor:              str
    layout:                 str
    overrides_path:         Path
    journal_path:           Path

    @property
    def downloads_root(self) -> Path:
        """
        Local path of the Transmission download tree
        """
        return self.media_root / 'downloads'

    @property
    def movies_root(self) -> Path:
        """
        Destination directory for movies
        """
        return self.media_root / 'movies'

    @property
    def tv_root(self) -> Path:
        """
        Destination directory for TV shows
        """
        return self.media_root / 'tv'

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Config:
        """
        Build a configuration from ``MEDIALINK_*`` environment variables

        :param env: environment mapping (defaults to ``os.environ``)
        :raises ConfigError: if a numeric variable is malformed
        :return: the resolved configuration
        """
        env        = dict(os.environ) if env is None else env
        media_root = Path(env.get('MEDIALINK_MEDIA_ROOT') or DEFAULT_MEDIA_ROOT)
        state      = env.get('MEDIALINK_STATE_PATH') or str(media_root / 'config' / 'medialink' / 'state.json')
        overrides  = env.get('MEDIALINK_OVERRIDES_PATH') or str(media_root / 'config' / 'medialink' / 'overrides.json')
        layout     = (env.get('MEDIALINK_LAYOUT') or DEFAULT_LAYOUT).strip().lower()
        if layout not in LAYOUTS:
            raise ConfigError(f'MEDIALINK_LAYOUT must be one of {", ".join(LAYOUTS)}, got {layout!r}')

        return cls(
            media_root=media_root,
            rpc_url=env.get('MEDIALINK_TRANSMISSION_URL') or DEFAULT_RPC_URL,
            rpc_user=env.get('MEDIALINK_TRANSMISSION_USER', ''),
            rpc_password=env.get('MEDIALINK_TRANSMISSION_PASSWORD', ''),
            transmission_downloads=(env.get('MEDIALINK_TRANSMISSION_DOWNLOADS') or DEFAULT_DOWNLOADS).rstrip('/'),
            interval=_int_env(env, 'MEDIALINK_INTERVAL', DEFAULT_INTERVAL),
            max_failures=_int_env(env, 'MEDIALINK_MAX_RPC_FAILURES', DEFAULT_MAX_FAILURES),
            ntfy_url=env.get('MEDIALINK_NTFY_URL', '').rstrip('/'),
            ntfy_topic=env.get('MEDIALINK_NTFY_TOPIC') or DEFAULT_NTFY_TOPIC,
            ntfy_token=env.get('MEDIALINK_NTFY_TOKEN', ''),
            state_path=Path(state),
            extract=env.get('MEDIALINK_EXTRACT', '1').strip().lower() not in FALSE_VALUES,
            extractor=env.get('MEDIALINK_EXTRACTOR', '').strip(),
            layout=layout,
            overrides_path=Path(overrides),
            journal_path=Path(state).with_name('reorg-journal.jsonl'),
        )
