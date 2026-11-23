#!/usr/bin/env python3
"""
Provision Sonarr, Radarr and Prowlarr on the NAS through their HTTP APIs.

Run on the NAS after the containers have started with a fresh (or wiped) ``/config``. Every step reads the current
state first and writes only a difference, so the script can be re-run at any time; ``--dry-run`` shows what it would do.

What it sets up:

- Sonarr / Radarr: root folder, the Transmission download client, the remote path mapping between Transmission's
  ``/downloads`` and the arrs' ``/data/downloads``, Jellyfin-style naming, hardlink imports, completed download handling
- Prowlarr: a ``flaresolverr`` tag, the FlareSolverr indexer proxy, Sonarr and Radarr as synced applications, and the
  IPTorrents indexer (cookie and user agent come from the environment, never from a file)

API keys are read from each app's ``config.xml`` at run time and are never printed. The ``UrlBase`` of each app is set
in its compose file (``<APP>__SERVER__URLBASE``), not here.
"""
from __future__ import annotations

import argparse
import copy
import functools
import json
import os
import re
import sys
import textwrap
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from typing import Literal
from typing import Protocol
from typing import TypeVar
from typing import Union

if TYPE_CHECKING:
    from collections.abc import Callable
    from collections.abc import Sequence


# ==================================================================================================
# Generic types
# ==================================================================================================


PathLike   = Union[Path, str]
StyleColor = Union[int, tuple[int, int, int], str]
T_contra   = TypeVar('T_contra', contravariant=True)

# The apps' JSON payloads are schemaless from this script's point of view: field lists differ per implementation and
# per app version, so they are handled as plain dicts
JsonDict = dict[str, Any]


class SupportsWrite(Protocol[T_contra]):
    """
    Protocol for types that support being written to and flushed (what ``print(..., flush=True)`` requires)
    """
    def write(self, s: T_contra, /) -> object: ...

    def flush(self) -> object: ...


# ==================================================================================================
# Constants
# ==================================================================================================


VERBOSE: bool = False

COOKIE_ENV     = 'IPTORRENTS_COOKIE'
USER_AGENT_ENV = 'IPTORRENTS_USER_AGENT'

# Prowlarr's masked value for password and API-key fields when it returns them over the API
MASKED = '********'

DEFAULT_CONFIG_ROOT = '/storage/media/config'

TRANSMISSION_HOST     = 'transmission'
TRANSMISSION_PORT     = 9091
TRANSMISSION_URL_BASE = '/transmission/'
FLARESOLVERR_URL      = 'http://flaresolverr:8191/'
FLARESOLVERR_TAG      = 'flaresolverr'

# Transmission reports the paths it downloads to as /downloads/...; the arrs mount the same files under /data
REMOTE_DOWNLOADS = '/downloads/'
LOCAL_DOWNLOADS  = '/data/downloads/'

# Imports hardlink (Transmission keeps seeding from downloads/complete), subtitles travel with the video, and the
# arrs hand finished downloads over themselves
MEDIA_MANAGEMENT: JsonDict = {
    'copyUsingHardlinks':  True,
    'importExtraFiles':    True,
    'extraFileExtensions': 'srt',
}
DOWNLOAD_HANDLING: JsonDict = {'enableCompletedDownloadHandling': True}


# ==================================================================================================
# Apps
# ==================================================================================================


AppKind = Literal['arr', 'indexer-manager']


@dataclass(frozen=True)
class App:
    """
    Static description of one app: where it listens and how it is configured
    """
    name:           str
    title:          str
    port:           int
    api:            str
    url_base:       str
    kind:           AppKind                                  # 'arr' (Sonarr/Radarr) or 'indexer-manager' (Prowlarr)
    root_folder:    str      = ''
    category_field: str      = ''
    category:       str      = ''
    naming:         JsonDict = field(default_factory=dict)

    @property
    def internal_url(self) -> str:
        """
        URL other containers use to reach this app (container name, container port, ``UrlBase``)
        """
        return f'http://{self.name}:{self.port}{self.url_base}'


SONARR = App(
    name='sonarr',
    title='Sonarr',
    port=8989,
    api='v3',
    url_base='/sonarr',
    kind='arr',
    root_folder='/data/tv',
    category_field='tvCategory',
    category='tv',
    naming={
        'renameEpisodes':           True,
        'replaceIllegalCharacters': True,
        'standardEpisodeFormat':    '{Series TitleYear} - S{season:00}E{episode:00} - {Episode CleanTitle:90}',
        'dailyEpisodeFormat':       '{Series TitleYear} - {Air-Date} - {Episode CleanTitle:90}',
        'animeEpisodeFormat':       '{Series TitleYear} - S{season:00}E{episode:00} - {Episode CleanTitle:90}',
        'seriesFolderFormat':       '{Series TitleYear}',
        'seasonFolderFormat':       'Season {season:00}',
    },
)

RADARR = App(
    name='radarr',
    title='Radarr',
    port=7878,
    api='v3',
    url_base='/radarr',
    kind='arr',
    root_folder='/data/movies',
    category_field='movieCategory',
    category='movies',
    naming={
        'renameMovies':             True,
        'replaceIllegalCharacters': True,
        'standardMovieFormat':      '{Movie CleanTitle} ({Release Year})',
        'movieFolderFormat':        '{Movie CleanTitle} ({Release Year})',
    },
)

PROWLARR = App(
    name='prowlarr',
    title='Prowlarr',
    port=9696,
    api='v1',
    url_base='/prowlarr',
    kind='indexer-manager',
)


# ==================================================================================================
# Formatting / logging
# ==================================================================================================

NO_COLOR: bool = bool(os.getenv('NO_COLOR'))  # https://no-color.org: any non-empty value disables color

ANSI_COLOR: dict[str, int] = {
    'black':   30, 'bright_black':   90,
    'red':     31, 'bright_red':     91,
    'green':   32, 'bright_green':   92,
    'yellow':  33, 'bright_yellow':  93,
    'blue':    34, 'bright_blue':    94,
    'magenta': 35, 'bright_magenta': 95,
    'cyan':    36, 'bright_cyan':    96,
    'white':   37, 'bright_white':   97,
    'reset':   39,
}
ANSI_RESET_ALL = '\033[0m'


def _interpret_color(_color: StyleColor, offset: int = 0) -> str:
    """
    Resolve a color name, integer, or RGB tuple to an ANSI SGR parameter string.

    :param _color: color as a named string, 256-color int, or ``(r, g, b)`` tuple
    :param offset: offset added to the base code (0 for foreground, 10 for background)
    :return: ANSI SGR parameter fragment (e.g. ``"32"`` or ``"38;2;255;0;0"``)
    """
    if isinstance(_color, int):
        return f'{38 + offset};5;{_color:d}'
    if isinstance(_color, (tuple, list)):
        r, g, b = _color
        return f'{38 + offset};2;{r:d};{g:d};{b:d}'
    return str(ANSI_COLOR[_color] + offset)


def style(
    text: Any = '',
    *,
    fg: StyleColor | None = None,
    bg: StyleColor | None = None,
    bold: bool | None = None,
    dim: bool | None = None,
    underline: bool | None = None,
    italic: bool | None = None,
    reset: bool = True,
) -> str:
    """
    Style text with ANSI escape codes. Returns the text unstyled when ``NO_COLOR`` is set.

    :param text: the string to style with ansi codes
    :param fg: foreground color
    :param bg: background color
    :param bold: enable or disable bold mode
    :param dim: enable or disable dim mode
    :param underline: enable or disable underline
    :param italic: enable or disable italic
    :param reset: add a reset-all code at the end of the string so styles do not carry over
    :raises TypeError: if invalid fg/bg color requested
    :return: styled text
    """
    if NO_COLOR:
        return str(text)
    if not isinstance(text, str):
        text = str(text)

    bits: list[str] = []
    if fg is not None:
        try:
            bits.append(f'\033[{_interpret_color(fg)}m')
        except KeyError:
            raise TypeError(f'Unknown color {fg!r}') from None
    if bg is not None:
        try:
            bits.append(f'\033[{_interpret_color(bg, 10)}m')
        except KeyError:
            raise TypeError(f'Unknown color {bg!r}') from None
    if bold is not None:
        bits.append(f'\033[{1 if bold else 22}m')
    if dim is not None:
        bits.append(f'\033[{2 if dim else 22}m')
    if underline is not None:
        bits.append(f'\033[{4 if underline else 24}m')
    if italic is not None:
        bits.append(f'\033[{3 if italic else 23}m')

    bits.append(text)
    if reset:
        bits.append(ANSI_RESET_ALL)
    return ''.join(bits)


def unstyle(text: str) -> str:
    """
    Removes ANSI styling information from a string

    :param text: the text to remove style information from
    :return: string with ANSI styling characters removed
    """
    return re.sub(r'\033\[[;?0-9]*[a-zA-Z]', '', text)


def folduser(path: PathLike) -> str:
    """
    Does the opposite of :meth:`pathlib.Path.expanduser`, replacing the user's home directory with a "~"

    :param path: path
    :return: str folded path
    """
    home = str(Path.home())
    return str(path).replace(home, '~')


def arg_note(name: str, val: str, *, dim: bool = True, color: StyleColor | None = 'yellow') -> str:
    """
    Format a bracketed annotation string for argparse help text

    :param name: the annotation label (e.g. ``"env var"``, ``"default"``)
    :param val: the annotation value
    :param dim: whether to apply dim styling
    :param color: foreground color for the value portion
    :return: the styled annotation string
    """
    return ''.join([
        style(f'[{name}: ', dim=dim),
        style(val,          dim=dim, fg=color),
        style(']',          dim=dim),
    ])


def printf(
    text: str,
    *,
    fg: StyleColor | None = None,
    bold: bool | None = None,
    dim: bool | None = None,
    indent: int = 0,
    verbose: bool = False,
) -> None:
    """
    Print styled text with optional indentation and verbose gating

    When ``verbose=True``, the message is only emitted if ``--verbose`` was given, defaults to dim bright-white text,
    and goes to stderr so it never contaminates stdout

    :param text: the content to print
    :param fg: foreground color
    :param bold: enable or disable bold
    :param dim: enable or disable dim
    :param indent: number of leading spaces to prepend
    :param verbose: if True, only print when verbose output is enabled and route to stderr
    """
    if verbose and not VERBOSE:
        return

    file: SupportsWrite[str] | None = None
    if verbose:
        fg   = fg  if fg  is not None else 'bright_white'
        dim  = dim if dim is not None else True
        file = sys.stderr

    print(
        style(
            textwrap.indent(text, ' ' * indent),
            fg=fg,
            bold=bold,
            dim=dim,
        ),
        file=file,
        flush=True,
    )


# ==================================================================================================
# Command-line arguments
# ==================================================================================================


class Args(argparse.Namespace):
    """
    :class:`argparse.Namespace` annotated with the args supported by this script
    """
    host:            str        # --host
    config_root:     str        # --config-root
    port_offset:     int        # --port-offset
    timeout:         float      # --timeout
    dry_run:         bool       # --dry-run
    refresh_secrets: bool       # --refresh-secrets
    verbose:         bool       # --verbose


def parse_args(argv: Sequence[str] | None = None) -> Args:
    """
    Build the argument parser and parse command-line args.

    :param argv: command-line arguments (default: ``sys.argv[1:]``)
    :return: parsed :class:`Args`
    """
    global VERBOSE

    parser = argparse.ArgumentParser(
        description=(__doc__ or '').split('\n\n')[0],
        epilog='\n'.join([
            'Environment:',
            f'  {style(COOKIE_ENV, fg="yellow")}      full cookie string of a logged-in iptorrents.com session',
            f'  {style(USER_AGENT_ENV, fg="yellow")}  user agent of that same browser (the cookie is tied to it)',
        ]),
        formatter_class=functools.partial(
            argparse.RawTextHelpFormatter,
            max_help_position=50,
        ),
        add_help=False,
    )

    def add_connection_opts() -> None:
        opts = parser.add_argument_group('Connection options')
        opts.add_argument(
            '--host',
            default='localhost',
            help=' '.join(['Host the apps publish their ports on', arg_note('default', 'localhost')]),
        )
        opts.add_argument(
            '--config-root',
            default=DEFAULT_CONFIG_ROOT,
            help=' '.join(['Directory holding <app>/config.xml', arg_note('default', DEFAULT_CONFIG_ROOT)]),
        )
        opts.add_argument(
            '--port-offset',
            type=int,
            default=0,
            help=' '.join([
                "Added to every app's published port, to provision a second (test) stack",
                arg_note('default', '0', color='bright_cyan'),
            ]),
        )
        opts.add_argument(
            '--timeout',
            type=float,
            default=180.0,
            help=' '.join(['Seconds to wait for each app to answer', arg_note('default', '180', color='bright_cyan')]),
        )
    add_connection_opts()

    def add_behavior_opts() -> None:
        opts = parser.add_argument_group('Behavior options')
        opts.add_argument(
            '-n',
            '--dry-run',
            action='store_true',
            help='Show what would change without writing anything',
        )
        opts.add_argument(
            '--refresh-secrets',
            action='store_true',
            help=(
                "Rewrite stored secrets (the IPTorrents cookie, the apps' API keys in Prowlarr) even when the\n"
                'provider already exists; the API masks them, so they cannot be compared'
            ),
        )
    add_behavior_opts()

    def add_output_opts() -> None:
        opts = parser.add_argument_group('Output options')
        opts.add_argument(
            '-v',
            '--verbose',
            action='store_true',
            help='Print each HTTP call (never bodies) to stderr',
        )
    add_output_opts()

    def add_other_opts() -> None:
        opts = parser.add_argument_group('Other options')
        opts.add_argument(
            '-h',
            '--help',
            action='help',
            default=argparse.SUPPRESS,
            help='Show this help message and exit',
        )
    add_other_opts()

    args = parser.parse_args(argv, namespace=Args())
    VERBOSE = args.verbose
    return args


# ==================================================================================================
# API client
# ==================================================================================================


class SetupError(RuntimeError):
    """
    A step cannot be completed (missing field, missing config file, app unreachable)
    """
    pass


class ApiError(SetupError):
    """
    An app answered with an HTTP error status
    """
    def __init__(self, status: int, message: str) -> None:
        super().__init__(f'HTTP {status}: {message}')
        self.status  = status
        self.message = message


def validation_message(body: str) -> str:
    """
    Condense an app's error body (a list of validation failures, or a single message object) into one line.

    :param body: raw response body
    :return: human-readable message, truncated to 300 characters
    """
    try:
        data = json.loads(body)
    except ValueError:
        return body.strip()[:300]
    else:
        if isinstance(data, dict):
            data = [data]

        parts: list[str] = [
            str(item.get('errorMessage') or item.get('message') or item)
            for item in data
            if isinstance(item, dict)
        ]
        return '; '.join(parts)[:300] or body.strip()[:300]


def read_api_key(config_dir: Path) -> str:
    """
    Read the API key an app generated into its ``config.xml``.

    :param config_dir: the app's config directory (the one mounted at ``/config``)
    :raises SetupError: if the file or the key is missing
    :return: the API key
    """
    path = config_dir / 'config.xml'
    try:
        root = ET.parse(path).getroot()         # noqa: S314
    except (OSError, ET.ParseError) as e:
        raise SetupError(f'cannot read {folduser(path)}: {e.__class__.__name__} (has the app started once?)') from e

    key = (root.findtext('ApiKey') or '').strip()
    if not key:
        raise SetupError(f'no <ApiKey> in {folduser(path)}')
    return key


class ArrClient:
    """
    Minimal JSON client for one Servarr app. Writes are skipped in dry-run mode.
    """
    def __init__(self, app: App, host: str, api_key: str, *, port_offset: int = 0, dry_run: bool = False) -> None:
        self.app      = app
        self.dry_run  = dry_run
        self._api_key = api_key
        self._base    = f'http://{host}:{app.port + port_offset}{app.url_base}/api/{app.api}'

    def request(self, method: str, path: str, body: JsonDict | None = None) -> Any:
        """
        Perform one API call.

        :param method: HTTP method
        :param path: path below ``/api/<version>/``
        :param body: JSON body for ``POST``/``PUT``
        :raises ApiError: on an HTTP error status
        :raises SetupError: when the app cannot be reached
        :return: decoded JSON response (``None`` for an empty body)
        """
        url = f'{self._base}/{path}'
        printf(f'{method} {url}', verbose=True)

        req  = urllib.request.Request(                                      # noqa: S310
            url,
            data=json.dumps(body).encode() if body is not None else None,
            method=method,
            headers={
                'X-Api-Key':     self._api_key,
                'Content-Type': 'application/json',
                'Accept':       'application/json',
            }
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:           # noqa: S310
                raw = resp.read()
        except urllib.error.HTTPError as e:
            raise ApiError(e.code, validation_message(e.read().decode(errors='replace'))) from e
        except (urllib.error.URLError, OSError) as e:
            raise SetupError(f'{self.app.title} unreachable at {self._base}: {e}') from e
        else:
            return json.loads(raw) if raw else None

    def get(self, path: str) -> Any:
        """
        ``GET`` a resource

        :param path: path below ``/api/<version>/``
        :return: decoded JSON response
        """
        return self.request('GET', path)

    def write(self, method: str, path: str, body: JsonDict) -> JsonDict:
        """
        ``POST`` or ``PUT`` a resource; a no-op echoing ``body`` in dry-run mode.

        :param method: ``POST`` or ``PUT``
        :param path: path below ``/api/<version>/``
        :param body: JSON body
        :return: the app's response, or ``body`` in dry-run mode
        """
        if self.dry_run:
            return body
        return self.request(method, path, body) or body

    def wait_ready(self, timeout: float) -> None:
        """
        Block until the app answers its status endpoint.

        :param timeout: seconds to wait
        :raises SetupError: if the app does not answer in time
        """
        deadline = time.monotonic() + timeout
        while True:
            try:
                self.get('system/status')
            except SetupError as e:
                if isinstance(e, ApiError) and (e.status in (401, 403)):
                    raise SetupError(f'{self.app.title} rejected the API key from config.xml') from e
                if time.monotonic() >= deadline:
                    raise SetupError(f'{self.app.title} did not become ready within {timeout:.0f}s: {e}') from e
                time.sleep(2)
            else:
                return


# ==================================================================================================
# Provisioning primitives
# ==================================================================================================

Status = Literal['created', 'updated', 'unchanged', 'warning']


@dataclass
class Outcome:
    """
    Result of one provisioning step
    """
    status: Status
    detail: str = ''


def set_fields(fields: list[JsonDict], values: JsonDict, *, only_if_different: bool = True) -> list[str]:
    """
    Set provider ``fields`` entries (``{'name': ..., 'value': ...}``) in place.

    :param fields: the ``fields`` list of a provider or its schema template
    :param values: field name to desired value
    :param only_if_different: when True, report and write only fields whose value differs
    :raises SetupError: if a name is not a field of this provider
    :return: names of the fields that were changed
    """
    by_name = {f['name']: f for f in fields}

    changed: list[str] = []
    for name, want in values.items():
        if name not in by_name:
            raise SetupError(f'provider has no field {name!r} (available: {", ".join(sorted(by_name))})')
        if only_if_different and (by_name[name].get('value') == want):
            continue

        by_name[name]['value'] = want
        changed.append(name)

    return changed


def apply_top_level(item: JsonDict, values: JsonDict) -> list[str]:
    """
    Set top-level keys of a provider or config object in place. ``tags`` are merged, never replaced.

    :param item: the object to modify
    :param values: key to desired value
    :return: keys that were changed
    """
    changed: list[str] = []
    for key, want in values.items():
        if key == 'tags':
            want = sorted(set(item.get('tags') or []) | set(want))
        if item.get(key) != want:
            item[key] = want
            changed.append(key)
    return changed


def ensure_provider(
    client: ArrClient,
    path: str,
    name: str,
    implementation: str,
    *,
    values: JsonDict,
    secrets: JsonDict | None = None,
    top: JsonDict | None = None,
    defaults: JsonDict | None = None,
    refresh_secrets: bool = False,
    disable_on_test_failure: bool = False,
) -> Outcome:
    """
    Create or update a named provider (download client, indexer, application, indexer proxy).

    A new provider is built from the app's own schema template for ``implementation``, so required fields keep their
    defaults. The API masks secret fields, so existing ones are rewritten only with ``refresh_secrets``.

    :param client: client of the app owning the provider
    :param path: collection path, e.g. ``downloadclient`` or ``indexer``
    :param name: provider name (the match key for an existing one)
    :param implementation: schema ``implementation`` (or ``definitionName`` for indexers) to build it from
    :param values: ordinary field values
    :param secrets: secret field values (never printed)
    :param top: top-level keys applied on create and update
    :param defaults: top-level keys applied on create only
    :param refresh_secrets: rewrite secrets of an existing provider
    :param disable_on_test_failure: when the app rejects the provider because its connection test fails, save it
                                    disabled instead and report a warning
    :raises SetupError: if the schema has no such implementation or a field is unknown
    :return: what happened
    """
    secrets  = secrets or {}
    existing = next((p for p in client.get(path) if p.get('name') == name), None)

    method: Literal['PUT', 'POST']
    status: Status

    if existing is None:
        schema = client.get(f'{path}/schema')
        template = next(
            (s for s in schema if implementation in (s.get('implementation'), s.get('definitionName'))),
            None,
        )
        if template is None:
            raise SetupError(f'{client.app.title} has no {path} implementation {implementation!r}')

        item = copy.deepcopy(template)
        item['name'] = name

        set_fields(item['fields'], values,  only_if_different=False)
        set_fields(item['fields'], secrets, only_if_different=False)

        apply_top_level(item, {**(defaults or {}), **(top or {})})
        method, target, status = 'POST', path, 'created'

    else:
        item    = existing
        changed = set_fields(item['fields'], values)
        if refresh_secrets:
            changed += set_fields(item['fields'], secrets, only_if_different=False)

        changed += apply_top_level(item, top or {})
        if not changed:
            return Outcome('unchanged')

        method, target, status = 'PUT', f'{path}/{item["id"]}', 'updated'

    try:
        client.write(method, target, item)
    except ApiError as e:
        if not (disable_on_test_failure and e.status == 400):
            raise

        # Only enabled providers are tested on save (and ``forceSave`` skips warnings, not errors), so keep the
        # configuration by saving it disabled
        item['enable'] = False
        client.write(method, target, item)
        return Outcome('warning', f'{status} but left disabled, its connection test failed: {e.message}')

    return Outcome(status)


def ensure_singleton(client: ArrClient, path: str, values: JsonDict) -> Outcome:
    """
    Update a single-object config resource (``config/naming``, ``config/mediamanagement``, ...).

    :param client: client of the app
    :param path: resource path
    :param values: top-level keys to set
    :return: what happened
    """
    current = client.get(path)
    if not apply_top_level(current, values):
        return Outcome('unchanged')

    client.write('PUT', f'{path}/{current["id"]}', current)
    return Outcome('updated')


def ensure_entry(client: ArrClient, path: str, match: JsonDict, body: JsonDict) -> Outcome:
    """
    Create a collection entry (root folder, remote path mapping) unless one matching ``match`` exists.

    :param client: client of the app
    :param path: collection path
    :param match: keys an existing entry must carry
    :param body: body of the entry to create
    :return: what happened
    """
    if any(all(item.get(k) == v for k, v in match.items()) for item in client.get(path)):
        return Outcome('unchanged')

    client.write('POST', path, body)
    return Outcome('created')


def ensure_tag(client: ArrClient, label: str) -> int:
    """
    Return the id of the tag ``label``, creating it when missing.

    :param client: client of the app
    :param label: tag label
    :return: tag id (``0`` for a tag that a dry run would create)
    """
    for tag in client.get('tag'):
        if tag.get('label') == label:
            return int(tag['id'])
    return int(client.write('POST', 'tag', {'label': label}).get('id', 0))


# ==================================================================================================
# Per-app configuration
# ==================================================================================================


@dataclass
class Run:
    """
    Accumulates results and prints them as they happen
    """
    dry_run:  bool                  = False
    failures: int                   = 0
    warnings: int                   = 0
    log:      list[tuple[str, str]] = field(default_factory=list)

    def step(self, label: str, action: Callable[[], Outcome]) -> None:
        """
        Run one step, print its outcome, and count failures instead of aborting.

        :param label: what the step configures
        :param action: callable performing the step
        """
        try:
            outcome = action()
        except SetupError as e:
            self.failures += 1
            printf(f'❌ {label}: {e}', fg='bright_red', indent=3)
            self.log.append((label, 'failed'))
            return

        verb = outcome.status if not self.dry_run or outcome.status == 'unchanged' else f'would be {outcome.status}'
        if outcome.status == 'unchanged':
            printf(f'🟢 {label} {style("unchanged", dim=True)}', indent=3)
        elif outcome.status == 'warning':
            self.warnings += 1
            printf(f'🟡 {label}: {outcome.detail}', fg='bright_yellow', indent=3)
        else:
            printf(f'✅ {label} {verb}', fg='bright_green', indent=3)

        self.log.append((label, outcome.status))


def configure_arr(client: ArrClient, app: App, run: Run) -> None:
    """
    Configure Sonarr or Radarr.

    :param client: client of the app
    :param app: description of the app
    :param run: result accumulator
    """
    run.step('Root folder', lambda: ensure_entry(
        client=client,
        path='rootfolder',
        match={'path': app.root_folder},
        body={'path': app.root_folder},
    ))
    run.step('Transmission client', lambda: ensure_provider(
        client=client,
        path='downloadclient',
        name='Transmission',
        implementation='Transmission',
        values={
            'host':             TRANSMISSION_HOST,
            'port':             TRANSMISSION_PORT,
            'useSsl':           False,
            'urlBase':          TRANSMISSION_URL_BASE,
            app.category_field: app.category,
        },
        top={'enable': True},
    ))
    run.step('Remote path mapping', lambda: ensure_entry(
        client=client,
        path='remotepathmapping',
        match={'host': TRANSMISSION_HOST, 'remotePath': REMOTE_DOWNLOADS},
        body={'host': TRANSMISSION_HOST, 'remotePath': REMOTE_DOWNLOADS, 'localPath': LOCAL_DOWNLOADS},
    ))
    run.step('Naming',            lambda: ensure_singleton(client, 'config/naming',          app.naming))
    run.step('Media management',  lambda: ensure_singleton(client, 'config/mediamanagement', MEDIA_MANAGEMENT))
    run.step('Download handling', lambda: ensure_singleton(client, 'config/downloadclient',  DOWNLOAD_HANDLING))


def configure_prowlarr(
    client: ArrClient,
    run: Run,
    *,
    arr_keys: dict[str, str],
    cookie: str,
    user_agent: str,
    refresh_secrets: bool,
) -> None:
    """
    Configure Prowlarr: FlareSolverr proxy, Sonarr/Radarr applications, and the IPTorrents indexer.

    :param client: Prowlarr's client
    :param run: result accumulator
    :param arr_keys: app name to API key, for the application connections
    :param cookie: IPTorrents cookie (empty to skip the indexer when it does not exist yet)
    :param user_agent: user agent the cookie was issued to
    :param refresh_secrets: rewrite stored secrets of existing providers
    """
    tag_id = 0
    try:
        tag_id = ensure_tag(client, FLARESOLVERR_TAG)
    except SetupError as e:
        run.failures += 1
        printf(f'❌ Tag {FLARESOLVERR_TAG}: {e}', fg='bright_red', indent=3)

    run.step('FlareSolverr proxy', lambda: ensure_provider(
        client=client,
        path='indexerproxy',
        name='FlareSolverr',
        implementation='FlareSolverr',
        values={'host': FLARESOLVERR_URL, 'requestTimeout': 60},
        top={'tags': [tag_id]},
    ))

    for arr in (SONARR, RADARR):
        run.step(f'{arr.title} application', functools.partial(
            ensure_provider,
            client=client,
            path='applications',
            name=arr.title,
            implementation=arr.title,
            values={'prowlarrUrl': PROWLARR.internal_url, 'baseUrl': arr.internal_url},
            secrets={'apiKey': arr_keys[arr.name]},
            top={'syncLevel': 'fullSync'},
            refresh_secrets=refresh_secrets,
        ))

    def indexer() -> Outcome:
        existing = next((i for i in client.get('indexer') if i.get('name') == 'IPTorrents'), None)
        if (not cookie) and (existing is None):
            return Outcome('warning', f'skipped: set {COOKIE_ENV} (and {USER_AGENT_ENV}) and re-run')

        profiles: list[JsonDict] = client.get('appprofile')
        profile = profiles[0]['id'] if profiles else 1

        values: JsonDict = {'userAgent': user_agent} if user_agent else {}

        # An indexer left disabled by an earlier failed test gets the new cookie without needing --refresh-secrets
        stale = existing is not None and not existing.get('enable')
        return ensure_provider(
            client=client,
            path='indexer',
            name='IPTorrents',
            implementation='IPTorrents',
            values=values,
            secrets={'cookie': cookie} if cookie else {},
            top={'tags': [tag_id], 'enable': True},
            defaults={'appProfileId': profile},
            refresh_secrets=bool(cookie) and (refresh_secrets or stale),
            disable_on_test_failure=True,
        )

    run.step('IPTorrents indexer', indexer)


def report_health(client: ArrClient, run: Run) -> None:
    """
    Print the app's health checks. They are informational and count as warnings, not failures: right after
    provisioning, checks such as "no indexers" lag behind Prowlarr's first sync.

    :param client: client of the app
    :param run: result accumulator
    """
    try:
        checks = client.get('health')
    except SetupError as e:
        run.failures += 1
        printf(f'❌ health: {e}', fg='bright_red', indent=3)
        return

    if not checks:
        printf('🟢 health: no issues', indent=3)

    for check in checks:
        kind    = check.get('type', 'warning')
        message = f'{check.get("source")}: {check.get("message")}'

        run.warnings += 1
        if kind == 'error':
            printf(f'🔴 {message}', fg='bright_red',    indent=3)
        else:
            printf(f'🟡 {message}', fg='bright_yellow', indent=3)


# ==================================================================================================
# Core script
# ==================================================================================================


def main(argv: Sequence[str] | None = None) -> int:
    """
    Main entry point.

    :param argv: command-line arguments (default: ``sys.argv[1:]``)
    :return: 0 on success, non-zero when any step or health check failed
    """
    args = parse_args(argv)

    cookie     = os.environ.get(COOKIE_ENV, '').strip()
    user_agent = os.environ.get(USER_AGENT_ENV, '').strip()
    if cookie and ('=' not in cookie):
        printf(f'❌ {COOKIE_ENV} must be a cookie string such as "uid=...; pass=..."', fg='bright_red')
        return 2

    config_root = Path(args.config_root)
    run         = Run(dry_run=args.dry_run)

    clients: dict[str, ArrClient] = {}
    keys:    dict[str, str]       = {}

    printf(f'🔎 Connecting to {SONARR.title}, {RADARR.title} and {PROWLARR.title} on {args.host}', fg='bright_cyan')
    try:
        for app in (SONARR, RADARR, PROWLARR):
            keys[app.name]    = read_api_key(config_root / app.name)
            clients[app.name] = ArrClient(
                app=app,
                host=args.host,
                api_key=keys[app.name],
                port_offset=args.port_offset,
                dry_run=args.dry_run,
            )
            clients[app.name].wait_ready(args.timeout)
    except SetupError as e:
        printf(f'❌ {e}', fg='bright_red')
        return 1

    for app in (SONARR, RADARR):
        printf(f'\n📦 {app.title}' + (' (dry run)' if args.dry_run else ''), fg='bright_cyan')
        configure_arr(clients[app.name], app, run)

    printf(f'\n📦 {PROWLARR.title}' + (' (dry run)' if args.dry_run else ''), fg='bright_cyan')
    configure_prowlarr(
        client=clients['prowlarr'],
        run=run,
        arr_keys=keys,
        cookie=cookie,
        user_agent=user_agent,
        refresh_secrets=args.refresh_secrets,
    )

    for app in (SONARR, RADARR, PROWLARR):
        printf(f'\n🩺 {app.title} health', fg='bright_cyan')
        report_health(clients[app.name], run)

    printf('')
    if run.failures:
        printf(f'❌ {run.failures} problem(s); see above', fg='bright_red')
        return 1
    if run.warnings:
        printf(f'🟡 Done with {run.warnings} warning(s)', fg='bright_yellow')
    else:
        printf('✅ Done', fg='bright_green')

    printf(
        '   Next: use Library Import on /data/tv (Sonarr) and /data/movies (Radarr) to re-add existing titles.',
        dim=True,
    )
    return 0


if __name__ == '__main__':
    sys.exit(main())
