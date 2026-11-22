"""
Tests for the medialink service (services/medialink): classification, linking, RPC client, reconcile engine, CLI loop
"""
from __future__ import annotations

import errno
import json
import logging
import os
import shutil
import subprocess
import threading
import zipfile
from http.server import BaseHTTPRequestHandler
from http.server import HTTPServer
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from typing import ClassVar

import jinja2
import pytest
import yaml

from medialink.archives import ExtractError
from medialink.archives import Extractor
from medialink.archives import extract_torrent
from medialink.archives import is_archive_part
from medialink.archives import is_first_volume
from medialink.classify import classify
from medialink.cli import EXIT_OK
from medialink.cli import EXIT_RPC
from medialink.cli import main
from medialink.cli import run_loop
from medialink.config import Config
from medialink.config import ConfigError
from medialink.dedupe import dedupe
from medialink.dedupe import file_digest
from medialink.dedupe import flat_duplicates
from medialink.engine import reconcile
from medialink.linker import EXISTS
from medialink.linker import EXTRACT_FAILED
from medialink.linker import EXTRACTED
from medialink.linker import FAILED
from medialink.linker import INCOMPLETE
from medialink.linker import LEGACY_COPY
from medialink.linker import LINKED
from medialink.linker import SKIPPED
from medialink.linker import SOURCE_MISSING
from medialink.linker import UNSAFE
from medialink.linker import link_torrent
from medialink.linker import map_download_dir
from medialink.linker import safe_join
from medialink.notify import MAX_BODY_BYTES
from medialink.notify import Notifier
from medialink.notify import truncate
from medialink.state import State
from medialink.transmission import Torrent
from medialink.transmission import TorrentFile
from medialink.transmission import TransmissionClient
from medialink.transmission import TransmissionError

if TYPE_CHECKING:
    from collections.abc import Iterator


REPO_ROOT   = Path(__file__).resolve().parents[3]
SERVICE_DIR = REPO_ROOT / 'services' / 'medialink'


# ==================================================================================================
# Helpers
# ==================================================================================================


def make_torrent(
    name: str,
    files: dict[str, int],
    *,
    download_dir: str = '/downloads/complete/movies',
    left: int = 0,
    labels: tuple[str, ...] = (),
    complete: bool = True,
) -> Torrent:
    """
    Build a torrent; ``files`` maps torrent-relative name to length
    """
    return Torrent(
        id=1,
        hash=f'hash-{name}',
        name=name,
        download_dir=download_dir,
        status=6,
        left=left,
        error=0,
        error_text='',
        labels=labels,
        files=tuple(TorrentFile(n, size, size if complete else 0) for n, size in files.items()),
    )


def write_source(config: Config, torrent: Torrent, content: bytes = b'x' * 10) -> None:
    """
    Create every file of a torrent in the local download tree
    """
    local = map_download_dir(torrent.download_dir, config.transmission_downloads, config.downloads_root)
    assert local is not None

    for file in torrent.files:
        path = local / file.name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


def _service() -> dict[str, Any]:  # Any: yaml-loaded compose structure
    """
    Load the medialink service definition from its compose file
    """
    return yaml.safe_load((SERVICE_DIR / 'compose.yml').read_text(encoding='utf-8'))['services']['medialink']


def archive_torrent(name: str = 'Rel', volumes: tuple[str, ...] = ('rel.rar', 'rel.r00'), **kwargs: Any) -> Torrent:
    """
    A torrent whose payload is a RAR set (plus a loose .nfo)
    """
    files = {f'{name}/{volume}': 10 for volume in volumes}
    files[f'{name}/{name}.nfo'] = 10
    return make_torrent(name, files, **kwargs)


def make_library(root: Path, flat: dict[str, bytes], nested: dict[str, bytes]) -> Path:
    """
    Create a library directory with video files at its root and inside folders
    """
    root.mkdir(parents=True, exist_ok=True)
    for name, data in {**flat, **nested}.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return root


# ==================================================================================================
# Mock classes
# ==================================================================================================


class RecordingNotifier(Notifier):
    """
    Notifier that records messages instead of calling ntfy
    """
    def __init__(self) -> None:
        super().__init__('http://ntfy.invalid', 'nas-media')
        self.sent: list[tuple[str, str]] = []

    def send(self, title: str, message: str, *, priority: str = 'default', tags: str = '') -> bool:
        self.sent.append((title, message))
        return True


class StubClient:
    """
    Stand-in for TransmissionClient that replays queued results (exceptions are raised)
    """
    def __init__(self, *results: list[Torrent] | Exception) -> None:
        self.results = list(results)

    def get_torrents(self) -> list[Torrent]:
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class _RpcHandler(BaseHTTPRequestHandler):
    """
    Minimal Transmission: demands a session id (409 first), then serves one torrent
    """
    seen_auth: ClassVar[list[str | None]] = []
    mode:      ClassVar[str]              = 'ok'

    def do_POST(self) -> None:
        self.rfile.read(int(self.headers.get('Content-Length', 0)))
        type(self).seen_auth.append(self.headers.get('Authorization'))

        if type(self).mode == 'error':
            self.send_response(500)
            self.end_headers()
            return
        if self.headers.get('X-Transmission-Session-Id') != 'sid-1':
            self.send_response(409)
            self.send_header('X-Transmission-Session-Id', 'sid-1')
            self.end_headers()
            return

        body = json.dumps({
            'result':    'success',
            'arguments': {
                'torrents': [{
                    'id':            7,
                    'hashString':    'abc',
                    'name':          'Film.2020',
                    'downloadDir':   '/downloads/complete/movies',
                    'status':        6,
                    'leftUntilDone': 0,
                    'labels':        ['movies'],
                    'error':         0,
                    'errorString':   '',
                    'files':         [{'name': 'Film.2020/film.mkv', 'length': 5, 'bytesCompleted': 5}],
                }]
            }
        }).encode()

        self.send_response(200)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args: object) -> None:
        return


class FakeRunner:
    """
    Stand-in for subprocess.run that "extracts" a fixed set of files into the output directory it is given
    """
    def __init__(
        self,
        files: dict[str, bytes] | None = None,
        *,
        returncode: int = 0,
        stderr: str = '',
        symlinks: dict[str, str] | None = None,
    ) -> None:
        self.files      = files or {}
        self.returncode = returncode
        self.stderr     = stderr
        self.symlinks   = symlinks or {}

        self.calls: list[list[str]] = []

    def __call__(self, argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        self.calls.append(argv)

        out = next((Path(a[2:]) for a in argv if a.startswith('-o') and len(a) > 2 and a[2] == '/'), Path(argv[-1]))
        if self.returncode == 0:
            for rel, data in self.files.items():
                (out / rel).parent.mkdir(parents=True, exist_ok=True)
                (out / rel).write_bytes(data)
            for rel, target in self.symlinks.items():
                (out / rel).symlink_to(target)

        return subprocess.CompletedProcess(argv, self.returncode, '', self.stderr)


# ==================================================================================================
# Fixtures
# ==================================================================================================


@pytest.fixture
def config(tmp_path: Path) -> Config:
    """
    Configuration rooted in a temporary media directory with the library layout created
    """
    media = tmp_path / 'media'
    for sub in ('downloads/complete', 'movies', 'tv'):
        (media / sub).mkdir(parents=True)
    return Config.from_env({'MEDIALINK_MEDIA_ROOT': str(media), 'MEDIALINK_NTFY_URL': 'http://ntfy.invalid'})


@pytest.fixture
def rpc_url() -> Iterator[str]:
    """
    Serve the stub RPC endpoint on an ephemeral port
    """
    _RpcHandler.seen_auth = []
    _RpcHandler.mode      = 'ok'

    server = HTTPServer(('127.0.0.1', 0), _RpcHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield f'http://127.0.0.1:{server.server_port}/transmission/rpc'

    server.shutdown()
    server.server_close()


# ==================================================================================================
# Unit tests
# ==================================================================================================


class TestConfig:
    """
    Tests for Config.from_env
    """
    def test_defaults(self) -> None:
        """
        Test that an empty environment yields the NAS defaults
        """
        config = Config.from_env({})

        assert config.rpc_url        == 'http://transmission:9091/transmission/rpc'
        assert config.downloads_root == Path('/storage/media/downloads')
        assert config.movies_root    == Path('/storage/media/movies')
        assert config.tv_root        == Path('/storage/media/tv')
        assert config.interval       == 60
        assert config.state_path     == Path('/storage/media/config/medialink/state.json')
        assert config.ntfy_url       == ''

    def test_overrides_and_trailing_slashes(self) -> None:
        """
        Test that overrides apply and trailing slashes are stripped from URL and path prefixes
        """
        config = Config.from_env({
            'MEDIALINK_MEDIA_ROOT':             '/m',
            'MEDIALINK_NTFY_URL':               'http://ntfy:80/',
            'MEDIALINK_TRANSMISSION_DOWNLOADS': '/dl/',
            'MEDIALINK_INTERVAL':               '5',
        })
        assert (config.ntfy_url, config.transmission_downloads, config.interval) == ('http://ntfy:80', '/dl', 5)

    @pytest.mark.parametrize(
        ('name', 'value'),
        [
            ('MEDIALINK_INTERVAL',         'soon'),
            ('MEDIALINK_INTERVAL',         '0'),
            ('MEDIALINK_MAX_RPC_FAILURES', '-3'),
        ],
    )
    def test_bad_numbers_raise(self, name: str, value: str) -> None:
        """
        Test that malformed or out-of-range numbers raise ConfigError
        """
        with pytest.raises(ConfigError):
            Config.from_env({name: value})


class TestClassify:
    """
    Tests for classify
    """
    @pytest.mark.parametrize(
        ('name', 'download_dir', 'labels', 'expected'),
        [
            ('Dune.Part.One.2021.2160p',         '/downloads/complete',         (),          'movies'),
            ('Dexter.Original.Sin.S01E06.1080p', '/downloads/complete',         (),          'tv'),
            ('The.Sopranos.S01-S06.DVDRiP',      '/downloads/complete',         (),          'tv'),
            ('Community Season 3 Pack',          '/downloads/complete',         (),          'tv'),
            ('Good Eats',                        '/downloads/complete/tv',      (),          'tv'),
            ('Overboard 2018 1080p',             '/downloads/complete/movie',   (),          'movies'),
            ('A Mistake (2024)',                 '/downloads/complete/movies/', (),          'movies'),
            ('Movie.2020.1080p',                 '/downloads/complete/movies',  ('TV',),     'tv'),
            ('Whatever',                         '/downloads/complete',         ('movies',), 'movies'),
            ('Se7en.1995.1080p',                 '/downloads/complete',         (),          'movies'),
            ('The Let Them Theory.m4b',          '/downloads/complete',         (),          None),
        ],
    )
    def test_precedence_and_heuristics(
        self,
        name: str,
        download_dir: str,
        labels: tuple[str, ...],
        expected: str | None,
    ) -> None:
        """
        Test label > directory > name heuristics, including the 'movie' directory and trailing slashes
        """
        assert classify(name, download_dir, labels) == expected


class TestPaths:
    """
    Tests for map_download_dir and safe_join
    """
    @pytest.mark.parametrize(
        ('download_dir', 'expected'),
        [
            ('/downloads/complete/tv', '/local/complete/tv'),
            ('/downloads',             '/local'),
            ('/downloadsX/tv',         None),
            ('/elsewhere',             None),
        ],
    )
    def test_map_download_dir(self, download_dir: str, expected: str | None) -> None:
        """
        Test translation of Transmission-side paths, including prefix-boundary handling
        """
        result = map_download_dir(download_dir, '/downloads', Path('/local'))
        assert (str(result) if result else None) == expected

    @pytest.mark.parametrize('name', ['../escape.mkv', '/etc/passwd', 'a/../../b', ''])
    def test_safe_join_rejects_escapes(self, name: str) -> None:
        """
        Test that absolute names, parent references and empty names are rejected
        """
        assert safe_join(Path('/base'), name) is None

    def test_safe_join_accepts_nested_names(self) -> None:
        """
        Test that ordinary nested names join under the base
        """
        assert safe_join(Path('/base'), 'Show/S01/ep.mkv') == Path('/base/Show/S01/ep.mkv')


class TestLinkTorrent:
    """
    Tests for link_torrent
    """
    def _link(self, config: Config, torrent: Torrent, *, dry_run: bool = False) -> list[Any]:  # Any: LinkResult list
        local = map_download_dir(torrent.download_dir, config.transmission_downloads, config.downloads_root)
        assert local is not None
        return link_torrent(torrent, local, config.movies_root, dry_run=dry_run)

    def test_creates_hardlinks_that_share_an_inode(self, config: Config) -> None:
        """
        Test that files are hardlinked (same inode), mirroring the torrent's directory layout
        """
        torrent = make_torrent('Film.2020', {'Film.2020/film.mkv': 10, 'Film.2020/Subs/en.srt': 10})
        write_source(config, torrent)

        results = self._link(config, torrent)
        assert [r.status for r in results] == [LINKED, LINKED]

        for file in torrent.files:
            source = config.downloads_root / 'complete' / 'movies' / file.name
            dest   = config.movies_root / file.name
            assert os.path.samestat(source.stat(), dest.stat())

    def test_single_file_torrent_lands_at_library_root(self, config: Config) -> None:
        """
        Test that a single-file torrent is linked directly under the library root
        """
        torrent = make_torrent('Film.2020.mkv', {'Film.2020.mkv': 10})
        write_source(config, torrent)

        self._link(config, torrent)
        assert (config.movies_root / 'Film.2020.mkv').is_file()

    def test_rerun_is_idempotent(self, config: Config) -> None:
        """
        Test that a second pass reports EXISTS and changes nothing
        """
        torrent = make_torrent('Film.2020.mkv', {'Film.2020.mkv': 10})
        write_source(config, torrent)

        self._link(config, torrent)
        assert [r.status for r in self._link(config, torrent)] == [EXISTS]

    def test_completes_a_partially_linked_torrent(self, config: Config) -> None:
        """
        Test that only the missing files are linked when some already exist
        """
        torrent = make_torrent('Show', {'Show/e1.mkv': 10, 'Show/e2.mkv': 10}, download_dir='/downloads/complete/tv')
        write_source(config, torrent)

        local = config.downloads_root / 'complete' / 'tv'
        link_torrent(make_torrent('Show', {'Show/e1.mkv': 10}), local, config.tv_root)

        results = link_torrent(torrent, local, config.tv_root)
        assert [r.status for r in results] == [EXISTS, LINKED]

    def test_legacy_copy_is_left_untouched(self, config: Config) -> None:
        """
        Test that an independent pre-existing copy is reported but never overwritten
        """
        torrent = make_torrent('Film.2020.mkv', {'Film.2020.mkv': 10})
        write_source(config, torrent, b'source-data')

        legacy = config.movies_root / 'Film.2020.mkv'
        legacy.write_bytes(b'legacy-data')

        results = self._link(config, torrent)
        assert [r.status for r in results] == [LEGACY_COPY]
        assert legacy.read_bytes() == b'legacy-data'

    def test_reports_missing_incomplete_and_unsafe_files(self, config: Config) -> None:
        """
        Test that missing sources, partial downloads and traversal names are classified, not linked
        """
        torrent    = make_torrent('T', {'T/gone.mkv': 10, '../evil.mkv': 10})
        incomplete = make_torrent('U', {'U/part.mkv': 10}, complete=False)

        results = self._link(config, torrent) + self._link(config, incomplete)
        assert [r.status for r in results] == [SOURCE_MISSING, UNSAFE, INCOMPLETE]
        assert not (config.movies_root.parent / 'evil.mkv').exists()

    def test_dry_run_creates_nothing(self, config: Config) -> None:
        """
        Test that a dry run reports LINKED but leaves the library untouched
        """
        torrent = make_torrent('Film.2020.mkv', {'Film.2020.mkv': 10})
        write_source(config, torrent)

        results = self._link(config, torrent, dry_run=True)
        assert [r.status for r in results] == [LINKED]
        assert not (config.movies_root / 'Film.2020.mkv').exists()

    def test_cross_device_failure_is_reported_with_a_hint(
        self,
        config: Config,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Test that EXDEV surfaces as FAILED and tells the operator to mount a common parent
        """
        torrent = make_torrent('Film.2020.mkv', {'Film.2020.mkv': 10})
        write_source(config, torrent)

        def exdev(*_args: object, **_kwargs: object) -> None:
            raise OSError(errno.EXDEV, 'Invalid cross-device link')

        monkeypatch.setattr(os, 'link', exdev)
        (result,) = self._link(config, torrent)

        assert result.status == FAILED
        assert 'common parent' in result.detail


class TestTransmissionClient:
    """
    Tests for TransmissionClient
    """
    def test_handles_the_409_session_handshake_and_parses_torrents(self, rpc_url: str) -> None:
        """
        Test that the client retries after a 409, then parses files, labels and completion
        """
        (torrent,) = TransmissionClient(rpc_url).get_torrents()

        assert (torrent.name, torrent.labels, torrent.finished) == ('Film.2020', ('movies',), True)
        assert torrent.files[0].complete

    def test_sends_basic_auth_only_when_configured(self, rpc_url: str) -> None:
        """
        Test that credentials produce an Authorization header and are omitted otherwise
        """
        TransmissionClient(rpc_url, 'user', 'pw').get_torrents()
        assert _RpcHandler.seen_auth[-1] == 'Basic dXNlcjpwdw=='

        _RpcHandler.seen_auth.clear()
        TransmissionClient(rpc_url).get_torrents()
        assert set(_RpcHandler.seen_auth) == {None}

    def test_http_errors_raise_transmission_error(self, rpc_url: str) -> None:
        """
        Test that a non-409 HTTP error is surfaced as TransmissionError
        """
        _RpcHandler.mode = 'error'
        with pytest.raises(TransmissionError, match='HTTP 500'):
            TransmissionClient(rpc_url).get_torrents()

    def test_unreachable_endpoint_raises_transmission_error(self) -> None:
        """
        Test that a refused connection is surfaced as TransmissionError
        """
        with pytest.raises(TransmissionError, match='unreachable'):
            TransmissionClient('http://127.0.0.1:1/transmission/rpc', timeout=1).get_torrents()


class TestNotify:
    """
    Tests for truncate and Notifier
    """
    def test_truncate_respects_the_byte_budget_without_splitting_characters(self) -> None:
        """
        Test that multibyte text is cut on a character boundary within the byte limit
        """
        text   = '鬼' * 5000
        result = truncate(text)

        assert len(result.encode()) <= MAX_BODY_BYTES
        assert result.endswith('…')

    def test_short_messages_pass_through(self) -> None:
        """
        Test that messages under the limit are unchanged
        """
        assert truncate('hello') == 'hello'

    def test_blank_url_disables_the_notifier(self) -> None:
        """
        Test that send is a no-op returning False when no URL is configured
        """
        assert Notifier('', 'topic').send('t', 'm') is False

    def test_unreachable_ntfy_never_raises(self) -> None:
        """
        Test that a failed publish returns False instead of raising
        """
        assert Notifier('http://127.0.0.1:1', 'topic', timeout=1).send('t', 'm') is False


class TestState:
    """
    Tests for State
    """
    def test_roundtrip_and_prune(self, tmp_path: Path) -> None:
        """
        Test persistence and that prune drops only resolved keys with the given prefixes
        """
        path  = tmp_path / 'sub' / 'state.json'
        state = State(path)
        state.add('link:a')
        state.add('link:b')
        state.add('rpc-outage')
        state.prune(('link:',), keep={'link:a'})
        state.save()

        reloaded = State(path)
        assert 'link:a'     in reloaded
        assert 'link:b' not in reloaded
        assert 'rpc-outage' in reloaded

    def test_corrupt_file_is_treated_as_empty(self, tmp_path: Path) -> None:
        """
        Test that unreadable state degrades to an empty set instead of crashing the service
        """
        path = tmp_path / 'state.json'
        path.write_text('{not json', encoding='utf-8')
        assert 'anything' not in State(path)


class TestReconcile:
    """
    Tests for reconcile
    """
    def test_links_torrents_from_every_directory_the_old_tool_ignored(self, config: Config) -> None:
        """
        Test root-level, singular 'movie' and trailing-slash torrents are all placed (the autoplex regression)
        """
        torrents = [
            make_torrent('Root.Film.2021.mkv', {'Root.Film.2021.mkv': 10}, download_dir='/downloads/complete'),
            make_torrent('Single.2018.mkv',    {'Single.2018.mkv': 10},    download_dir='/downloads/complete/movie'),
            make_torrent('Slash.2024.mkv',     {'Slash.2024.mkv': 10},     download_dir='/downloads/complete/movies/'),
            make_torrent('Show.S01E01.mkv',    {'Show.S01E01.mkv': 10},    download_dir='/downloads/complete'),
        ]
        for torrent in torrents:
            write_source(config, torrent)

        report = reconcile(torrents, config)

        assert report.ok
        assert report.counts[LINKED] == 4
        assert (config.movies_root / 'Root.Film.2021.mkv').exists()
        assert (config.movies_root / 'Single.2018.mkv').exists()
        assert (config.movies_root / 'Slash.2024.mkv').exists()
        assert (config.tv_root / 'Show.S01E01.mkv').exists()

    def test_unfinished_torrents_are_pending_not_linked(self, config: Config) -> None:
        """
        Test that torrents still downloading are skipped and counted
        """
        torrent = make_torrent('Film.2020.mkv', {'Film.2020.mkv': 10}, left=5)
        report  = reconcile([torrent], config)

        assert report.pending == 1
        assert not report.results

    def test_unclassifiable_torrent_notifies_once(self, config: Config, tmp_path: Path) -> None:
        """
        Test that a torrent that cannot be placed alerts once, not every cycle
        """
        torrent = make_torrent(
            'The Let Them Theory.m4b',
            {'The Let Them Theory.m4b': 10},
            download_dir='/downloads/complete',
        )
        notifier = RecordingNotifier()
        state    = State(tmp_path / 'state.json')

        first  = reconcile([torrent], config, state=state, notifier=notifier)
        second = reconcile([torrent], config, state=state, notifier=notifier)

        assert not first.ok
        assert not second.ok
        assert len(notifier.sent) == 1
        assert 'Add a "movies" or "tv" label' in notifier.sent[0][1]

    def test_missing_source_is_a_problem_and_clears_when_resolved(self, config: Config, tmp_path: Path) -> None:
        """
        Test that a torrent whose data is gone alerts, and alerts again if the problem returns after resolving
        """
        torrent  = make_torrent('Film.2020.mkv', {'Film.2020.mkv': 10})
        notifier = RecordingNotifier()
        state    = State(tmp_path / 'state.json')

        reconcile([torrent], config, state=state, notifier=notifier)
        assert f'link:{torrent.hash}' in state

        write_source(config, torrent)
        assert reconcile([torrent], config, state=state, notifier=notifier).ok
        assert f'link:{torrent.hash}' not in state

        (config.movies_root / 'Film.2020.mkv').unlink()
        (config.downloads_root / 'complete' / 'movies' / 'Film.2020.mkv').unlink()
        reconcile([torrent], config, state=state, notifier=notifier)
        assert len(notifier.sent) == 2

    def test_dry_run_changes_nothing_and_stays_silent(self, config: Config, tmp_path: Path) -> None:
        """
        Test that dry-run creates no links, sends no notifications and writes no state
        """
        linkable   = make_torrent('Film.2020.mkv', {'Film.2020.mkv': 10})
        unplaceable = make_torrent('Mystery', {'Mystery': 10}, download_dir='/downloads/complete')
        write_source(config, linkable)

        notifier = RecordingNotifier()
        state    = State(tmp_path / 'state.json')

        report = reconcile([linkable, unplaceable], config, dry_run=True, state=state, notifier=notifier)

        assert report.counts[LINKED] == 1
        assert not (config.movies_root / 'Film.2020.mkv').exists()
        assert not notifier.sent
        assert not (tmp_path / 'state.json').exists()


class TestRunLoop:
    """
    Tests for run_loop
    """
    def _loop(self, config: Config, client: StubClient, state: State, notifier: RecordingNotifier, cycles: int) -> int:
        return run_loop(
            config,
            client,                     # type: ignore[arg-type]
            notifier,
            state,
            sleep=lambda _s: None,
            max_cycles=cycles,
        )

    def test_exits_nonzero_and_alerts_once_after_sustained_outage(self, config: Config, tmp_path: Path) -> None:
        """
        Test that N consecutive RPC failures exit EXIT_RPC, alerting once even across restarts
        """
        notifier = RecordingNotifier()
        state    = State(tmp_path / 'state.json')
        down     = TransmissionError('RPC unreachable')
        client   = StubClient(*([down] * config.max_failures))

        assert self._loop(config, client, state, notifier, 99) == EXIT_RPC
        assert len(notifier.sent) == 1

        restarted = StubClient(*([down] * config.max_failures))
        assert self._loop(config, restarted, State(tmp_path / 'state.json'), notifier, 99) == EXIT_RPC
        assert len(notifier.sent) == 1

    def test_recovery_resets_the_failure_count_and_outage_flag(self, config: Config, tmp_path: Path) -> None:
        """
        Test that intermittent failures below the threshold never exit, and success clears the outage key
        """
        notifier = RecordingNotifier()
        state    = State(tmp_path / 'state.json')
        state.add('rpc-outage')
        down     = TransmissionError('blip')
        client   = StubClient(down, down, [], down, down, [])

        assert self._loop(config, client, state, notifier, 6) == EXIT_OK
        assert 'rpc-outage' not in state

    def test_links_new_torrents_each_cycle(self, config: Config, tmp_path: Path) -> None:
        """
        Test that a torrent appearing mid-run is linked on the next cycle (the reconcile guarantee)
        """
        torrent = make_torrent('Film.2020.mkv', {'Film.2020.mkv': 10})
        write_source(config, torrent)

        client = StubClient([], [torrent])
        self._loop(config, client, State(tmp_path / 'state.json'), RecordingNotifier(), 2)

        assert (config.movies_root / 'Film.2020.mkv').exists()


class TestMain:
    """
    Tests for the argument parser and command dispatch
    """
    def test_once_dry_run_reports_via_exit_code(
        self,
        config: Config,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that once --dry-run prints a summary and returns 1 when a torrent cannot be placed
        """
        torrent = make_torrent('Mystery', {'Mystery': 10}, download_dir='/downloads/complete')
        monkeypatch.setenv('MEDIALINK_MEDIA_ROOT', str(config.media_root))
        monkeypatch.setattr(TransmissionClient, 'get_torrents', lambda _self: [torrent])

        assert main(['once', '--dry-run']) == 1
        assert 'PROBLEM  Torrent not placed' in capsys.readouterr().out

    def test_rpc_failure_exits_with_rpc_code(self, config: Config, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that an unreachable Transmission yields EXIT_RPC for single-shot commands
        """
        def boom(_self: TransmissionClient) -> list[Torrent]:
            raise TransmissionError('down')

        monkeypatch.setenv('MEDIALINK_MEDIA_ROOT', str(config.media_root))
        monkeypatch.setattr(TransmissionClient, 'get_torrents', boom)

        assert main(['once']) == EXIT_RPC

    def test_bad_config_exits_with_config_code(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that an invalid MEDIALINK_INTERVAL is reported without a traceback
        """
        monkeypatch.setenv('MEDIALINK_INTERVAL', 'nope')
        assert main(['once']) == 3


class TestDedupe:
    """
    Tests for dedupe
    """
    def _legacy_results(self, config: Config, source: bytes, legacy: bytes) -> list[Any]:  # Any: LinkResult list
        torrent = make_torrent('Film.2020.mkv', {'Film.2020.mkv': len(source)})
        write_source(config, torrent, source)
        (config.movies_root / 'Film.2020.mkv').write_bytes(legacy)
        return reconcile([torrent], config, dry_run=True).results

    def test_dry_run_reports_without_changing(self, config: Config) -> None:
        """
        Test that identical legacy copies are reported as would-replace and left as independent files
        """
        results = self._legacy_results(config, b'same-bytes', b'same-bytes')

        (outcome,) = dedupe(results)
        assert outcome.action == 'would-replace'

        source = config.downloads_root / 'complete' / 'movies' / 'Film.2020.mkv'
        assert not os.path.samestat(source.stat(), outcome.dest.stat())

    def test_apply_replaces_identical_copies_with_hardlinks(self, config: Config) -> None:
        """
        Test that apply swaps an identical copy for a hardlink and leaves no temp file behind
        """
        results = self._legacy_results(config, b'same-bytes', b'same-bytes')

        (outcome,) = dedupe(results, apply=True)

        source = config.downloads_root / 'complete' / 'movies' / 'Film.2020.mkv'
        assert outcome.action == 'replaced'
        assert os.path.samestat(source.stat(), outcome.dest.stat())
        assert [p.name for p in config.movies_root.iterdir()] == ['Film.2020.mkv']

    def test_differing_content_is_never_replaced(self, config: Config) -> None:
        """
        Test that a same-size file with different bytes is flagged and kept even under apply
        """
        results = self._legacy_results(config, b'aaaaaaaaaa', b'bbbbbbbbbb')

        (outcome,) = dedupe(results, apply=True)

        assert outcome.action == 'differs'
        assert outcome.dest.read_bytes() == b'bbbbbbbbbb'


class TestDeployFiles:
    """
    Tests for the compose file, Dockerfile and secret template
    """
    def test_media_tree_is_one_mount_so_hardlinks_work(self) -> None:
        """
        Test that /storage/media is mounted once; separate bind mounts would make link() fail with EXDEV
        """
        assert _service()['volumes'] == ['/storage/media:/storage/media']

    def test_build_context_is_relative_to_the_deploy_project_directory(self) -> None:
        """
        Test that the build context names this service's directory, since deploy.sh uses --project-directory ~/docker

        The Dockerfile copies the package from that context, so both must exist where the rsync will put them.
        """
        service = _service()

        assert service['build']['context'] == 'medialink'
        assert service['pull_policy'] == 'build'
        assert (SERVICE_DIR / 'Dockerfile').is_file()
        assert (SERVICE_DIR / 'medialink' / '__main__.py').is_file()
        assert 'COPY medialink /app/medialink' in (SERVICE_DIR / 'Dockerfile').read_text(encoding='utf-8')

    def test_image_installs_a_rar_capable_extractor(self) -> None:
        """
        Test that the Dockerfile enables Debian non-free and installs unrar (packaged 7zip has no RAR support)
        """
        dockerfile = (SERVICE_DIR / 'Dockerfile').read_text(encoding='utf-8')

        assert 'non-free'        in dockerfile
        assert 'apt-get install' in dockerfile
        assert 'unrar'           in dockerfile

    def test_runs_as_the_media_owner_and_reaches_its_peers_by_name(self) -> None:
        """
        Test the unprivileged user and the in-network Transmission and ntfy addresses
        """
        service = _service()
        env     = dict(item.split('=', 1) for item in service['environment'])

        assert service['user'] == '1000:1000'
        assert env['MEDIALINK_TRANSMISSION_URL'] == 'http://transmission:9091/transmission/rpc'
        assert env['MEDIALINK_NTFY_URL'] == 'http://ntfy:80'

    @pytest.mark.parametrize(
        ('variables', 'expected'),
        [
            ({'ntfy_alerts_token': 's3cret'}, 'MEDIALINK_NTFY_TOKEN=s3cret'),
            ({},                              'MEDIALINK_NTFY_TOKEN='),
        ],
    )
    def test_env_template_renders_the_ntfy_token(self, variables: dict[str, str], expected: str) -> None:
        """
        Test that the vault variable reaches the env file and an unset token renders empty
        """
        template = jinja2.Template((SERVICE_DIR / 'env.j2').read_text(encoding='utf-8'))
        assert template.render(**variables).strip() == expected


class TestArchiveNames:
    """
    Tests for is_archive_part and is_first_volume
    """
    @pytest.mark.parametrize(
        ('name', 'part', 'first'),
        [
            ('a.rar',         True,  True),
            ('A.RAR',         True,  True),
            ('a.r00',         True,  False),
            ('a.R123',        True,  False),
            ('a.part01.rar',  True,  True),
            ('a.part1.rar',   True,  True),
            ('a.part001.rar', True,  True),
            ('a.part02.rar',  True,  False),
            ('a.part10.rar',  True,  False),
            ('a.mkv',         False, False),
            ('a.rar.nfo',     False, False),
            ('a.sfv',         False, False),
            ('rare.mkv',      False, False),
        ],
    )
    def test_volume_classification(self, name: str, part: bool, first: bool) -> None:
        """
        Test that every volume is an archive part and only the first volume starts extraction
        """
        assert (is_archive_part(name), is_first_volume(name)) == (part, first)


class TestExtractor:
    """
    Tests for Extractor
    """
    def test_command_shape_per_tool(self, tmp_path: Path) -> None:
        """
        Test the 7-Zip and unrar command lines (archive and output directory in the right places)
        """
        archive, out = tmp_path / 'a.rar', tmp_path / 'out'

        seven = Extractor('/usr/bin/7z').command(archive, out)
        unrar = Extractor('/usr/bin/unrar').command(archive, out)

        assert seven[:3] == ['/usr/bin/7z', 'x', '-y']
        assert f'-o{out}' in seven
        assert seven[-1] == str(archive)
        assert unrar[:2] == ['/usr/bin/unrar', 'x']
        assert unrar[-2:] == [str(archive), f'{out}{os.sep}']

    def test_discover_prefers_the_configured_tool(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test discovery order: the preferred tool first, then 7zz, 7z, unrar; None when nothing is installed
        """
        installed = {'7z': '/usr/bin/7z', 'unrar': '/usr/bin/unrar', 'mine': '/opt/mine'}
        monkeypatch.setattr(shutil, 'which', installed.get)

        assert Extractor.discover('mine').binary == '/opt/mine'     # type: ignore[union-attr]
        assert Extractor.discover().binary == '/usr/bin/7z'         # type: ignore[union-attr]

        monkeypatch.setattr(shutil, 'which', lambda _name: None)
        assert Extractor.discover() is None

    def test_nonzero_exit_raises_with_the_tool_message(self, tmp_path: Path) -> None:
        """
        Test that a failing tool surfaces its exit code and message as ExtractError
        """
        extractor = Extractor('/usr/bin/7z', FakeRunner(returncode=2, stderr='CRC Failed in x.mkv'))

        with pytest.raises(ExtractError, match='exited 2: CRC Failed'):
            extractor.extract(tmp_path / 'a.rar', tmp_path / 'out')

    def test_missing_binary_raises(self, tmp_path: Path) -> None:
        """
        Test that an unlaunchable tool becomes ExtractError instead of crashing the loop
        """
        def missing(*_args: object, **_kwargs: object) -> None:
            raise FileNotFoundError('no such tool')

        with pytest.raises(ExtractError, match='failed to run'):
            Extractor('/nope/7z', missing).extract(tmp_path / 'a.rar', tmp_path / 'out')  # type: ignore[arg-type]

    @pytest.mark.skipif(shutil.which('7z') is None, reason='7z not installed')
    def test_real_extraction_with_7z(self, tmp_path: Path) -> None:
        """
        Test an actual 7z run (a zip named .rar: 7z detects the format by signature) through the full publish path
        """
        archive = tmp_path / 'rel.rar'
        with zipfile.ZipFile(archive, 'w') as bundle:
            bundle.writestr('Episode.mkv', b'real-video-bytes')
            bundle.writestr('Subs/en.srt', b'subs')

        extractor = Extractor(shutil.which('7z') or '7z')
        staging   = tmp_path / 'staging'

        extractor.extract(archive, staging)

        assert (staging / 'Episode.mkv').read_bytes() == b'real-video-bytes'
        assert (staging / 'Subs' / 'en.srt').read_bytes() == b'subs'


class TestExtractTorrent:
    """
    Tests for extract_torrent
    """
    def _run(
        self,
        config: Config,
        torrent: Torrent,
        extractor: Extractor | None,
        state: State | None = None,
        *,
        dry_run: bool = False,
    ) -> list[Any]:  # Any: LinkResult list
        write_source(config, torrent)
        local = map_download_dir(torrent.download_dir, config.transmission_downloads, config.downloads_root)
        assert local is not None
        return extract_torrent(torrent, local, config.movies_root, extractor, state, dry_run=dry_run)

    def test_extracts_next_to_the_release_folder_and_remembers_it(self, config: Config, tmp_path: Path) -> None:
        """
        Test publish into <library>/<release>/, no staging left behind, and no re-extraction on the next pass
        """
        runner    = FakeRunner({'Rel.mkv': b'video', 'Subs/en.srt': b'subs'})
        extractor = Extractor('/usr/bin/7z', runner)
        state     = State(tmp_path / 'state.json')
        torrent   = archive_torrent()

        (first,) = self._run(config, torrent, extractor, state)
        (again,) = self._run(config, torrent, extractor, state)

        release = config.movies_root / 'Rel'
        assert (first.status, first.detail) == (EXTRACTED, '2 file(s)')
        assert (release / 'Rel.mkv').read_bytes() == b'video'
        assert (release / 'Subs' / 'en.srt').read_bytes() == b'subs'
        assert [p.name for p in release.iterdir() if p.name.startswith('.')] == []
        assert again.status == EXISTS
        assert len(runner.calls) == 1

    def test_only_the_first_volume_is_given_to_the_tool(self, config: Config) -> None:
        """
        Test that a multi-part set is extracted once, from part01
        """
        runner  = FakeRunner({'Rel.mkv': b'v'})
        torrent = archive_torrent(volumes=('rel.part01.rar', 'rel.part02.rar', 'rel.part03.rar'))

        results = self._run(config, torrent, Extractor('/usr/bin/7z', runner))

        assert [r.status for r in results] == [EXTRACTED]
        assert len(runner.calls) == 1
        assert runner.calls[0][-1].endswith('rel.part01.rar')

    def test_dry_run_extracts_nothing(self, config: Config) -> None:
        """
        Test that a dry run reports the extraction and never invokes the tool or creates the folder
        """
        runner = FakeRunner({'Rel.mkv': b'v'})

        (result,) = self._run(config, archive_torrent(), Extractor('/usr/bin/7z', runner), dry_run=True)

        assert (result.status, result.detail) == (EXTRACTED, 'dry-run')
        assert not runner.calls
        assert not (config.movies_root / 'Rel').exists()

    def test_failure_leaves_nothing_behind_and_is_retried(self, config: Config, tmp_path: Path) -> None:
        """
        Test that a failed extraction cleans up, records no marker, and succeeds on the next pass
        """
        state   = State(tmp_path / 'state.json')
        torrent = archive_torrent()

        (failed,) = self._run(config, torrent, Extractor('/usr/bin/7z', FakeRunner(returncode=2, stderr='boom')), state)

        assert failed.status == EXTRACT_FAILED
        assert not (config.movies_root / 'Rel').exists()
        assert f'extracted:{torrent.hash}:Rel/rel.rar' not in state

        (retried,) = self._run(config, torrent, Extractor('/usr/bin/7z', FakeRunner({'Rel.mkv': b'v'})), state)
        assert retried.status == EXTRACTED

    def test_stale_staging_from_a_crash_is_discarded(self, config: Config) -> None:
        """
        Test that a truncated file left in staging by a crashed run is never published
        """
        torrent = archive_torrent()
        stale   = config.movies_root / 'Rel' / f'.medialink-extract-{torrent.hash[:8]}'
        stale.mkdir(parents=True)

        (stale / 'Rel.mkv').write_bytes(b'TRUNCATED')
        (stale / 'Leftover.mkv').write_bytes(b'HALF-WRITTEN')  # a file the fresh run does not regenerate

        self._run(config, torrent, Extractor('/usr/bin/7z', FakeRunner({'Rel.mkv': b'complete-video'})))

        assert (config.movies_root / 'Rel' / 'Rel.mkv').read_bytes() == b'complete-video'
        assert not (config.movies_root / 'Rel' / 'Leftover.mkv').exists()
        assert not stale.exists()

    def test_existing_files_are_never_overwritten(self, config: Config) -> None:
        """
        Test that a file already in the library wins over the extracted one
        """
        (config.movies_root / 'Rel').mkdir()
        (config.movies_root / 'Rel' / 'Rel.mkv').write_bytes(b'already-here')

        (result,) = self._run(config, archive_torrent(), Extractor('/usr/bin/7z', FakeRunner({'Rel.mkv': b'new'})))

        assert result.detail == '0 file(s)'
        assert (config.movies_root / 'Rel' / 'Rel.mkv').read_bytes() == b'already-here'

    def test_symlinks_in_an_archive_are_discarded(self, config: Config) -> None:
        """
        Test that a symlink smuggled in a RAR never reaches the library
        """
        runner = FakeRunner({'Rel.mkv': b'v'}, symlinks={'evil': '/etc/passwd'})

        self._run(config, archive_torrent(), Extractor('/usr/bin/7z', runner))

        assert not (config.movies_root / 'Rel' / 'evil').exists()
        assert not (config.movies_root / 'Rel' / 'evil').is_symlink()

    def test_without_an_extractor_the_set_is_a_failure(self, config: Config) -> None:
        """
        Test that a RAR set with no available tool is reported as EXTRACT_FAILED
        """
        (result,) = self._run(config, archive_torrent(), None)

        assert result.status == EXTRACT_FAILED
        assert 'unrar' in result.detail

    def test_unfinished_volumes_are_incomplete_not_extracted(self, config: Config) -> None:
        """
        Test that a set with missing volumes waits instead of failing
        """
        runner = FakeRunner({'Rel.mkv': b'v'})

        (result,) = self._run(config, archive_torrent(complete=False), Extractor('/usr/bin/7z', runner))

        assert result.status == INCOMPLETE
        assert not runner.calls

    @pytest.mark.skipif(shutil.which('7z') is None, reason='7z not installed')
    def test_end_to_end_with_real_7z(self, config: Config) -> None:
        """
        Test the whole path (staging, real 7z, publish) with a genuine archive named like a RAR volume
        """
        torrent = make_torrent('Rel', {'Rel/rel.rar': 10})
        local   = config.downloads_root / 'complete' / 'movies'
        (local / 'Rel').mkdir(parents=True)
        with zipfile.ZipFile(local / 'Rel' / 'rel.rar', 'w') as bundle:
            bundle.writestr('Episode.mkv', b'real-video-bytes')

        (result,) = extract_torrent(torrent, local, config.movies_root, Extractor(shutil.which('7z') or '7z'))

        assert result.status == EXTRACTED
        assert (config.movies_root / 'Rel' / 'Episode.mkv').read_bytes() == b'real-video-bytes'


class TestReconcileWithArchives:
    """
    Tests for reconcile on RAR-packed torrents
    """
    def test_volumes_are_not_linked_but_contents_are_extracted(self, config: Config) -> None:
        """
        Test that .rar/.rNN files stay out of the library while loose files link and the video is extracted
        """
        torrent = archive_torrent()
        write_source(config, torrent)

        extractor = Extractor('/usr/bin/7z', FakeRunner({'Rel.mkv': b'video'}))
        report    = reconcile([torrent], config, extractor=extractor)

        release = config.movies_root / 'Rel'
        assert report.ok
        assert report.counts[SKIPPED] == 2
        assert report.counts[EXTRACTED] == 1
        assert (release / 'Rel.nfo').exists()
        assert (release / 'Rel.mkv').read_bytes() == b'video'
        assert not (release / 'rel.rar').exists()
        assert not (release / 'rel.r00').exists()

    def test_missing_extractor_is_reported_once(self, config: Config, tmp_path: Path) -> None:
        """
        Test that a RAR torrent with no extractor produces a single alert, not one per cycle
        """
        torrent  = archive_torrent()
        write_source(config, torrent)

        notifier = RecordingNotifier()
        state    = State(tmp_path / 'state.json')

        first  = reconcile([torrent], config, state=state, notifier=notifier)
        second = reconcile([torrent], config, state=state, notifier=notifier)

        assert not first.ok
        assert not second.ok
        assert len(notifier.sent) == 1
        assert 'extract-failed' in notifier.sent[0][1]


class TestFileDigest:
    """
    Tests for file_digest
    """
    def test_quick_mode_samples_start_middle_and_end(self, tmp_path: Path) -> None:
        """
        Test what quick mode can and cannot see: changes at the ends differ, an unsampled middle region does not
        """
        size  = 4 * 1024 * 1024
        base  = bytearray(b'a' * size)

        files = {}
        for label, offset in (('base', None), ('tail', size - 1), ('head', 0), ('gap', 1_200_000)):
            data = bytearray(base)
            if offset is not None:
                data[offset] = ord('z')
            files[label] = tmp_path / label
            files[label].write_bytes(bytes(data))

        quick = {label: file_digest(path, quick=True) for label, path in files.items()}
        full  = {label: file_digest(path) for label, path in files.items()}

        assert quick['tail'] != quick['base']
        assert quick['head'] != quick['base']
        assert quick['gap']  == quick['base']  # the documented limitation of --quick
        assert full['gap']   != full['base']


class TestFlatDuplicates:
    """
    Tests for flat_duplicates
    """
    def test_dry_run_reports_and_apply_removes_only_the_flat_copy(self, tmp_path: Path) -> None:
        """
        Test that an identical flat file is reported on a dry run and removed on apply, keeping the foldered copy
        """
        root = make_library(tmp_path / 'tv', {'Ep.mkv': b'same'}, {'Show/Ep.mkv': b'same'})

        (dry,) = flat_duplicates([root])
        assert (dry.action, dry.size, dry.detail) == ('would-remove-flat', 4, 'Show/Ep.mkv')
        assert (root / 'Ep.mkv').exists()

        (done,) = flat_duplicates([root], apply=True)
        assert done.action == 'removed-flat'
        assert not (root / 'Ep.mkv').exists()
        assert (root / 'Show' / 'Ep.mkv').read_bytes() == b'same'

    def test_different_content_with_the_same_name_and_size_is_left_alone(self, tmp_path: Path) -> None:
        """
        Test that a same-name, same-size file with different bytes is never removed
        """
        root = make_library(tmp_path / 'movies', {'Film.mkv': b'aaaa'}, {'Film/Film.mkv': b'bbbb'})

        assert flat_duplicates([root], apply=True) == []
        assert (root / 'Film.mkv').read_bytes() == b'aaaa'

    def test_flat_files_without_a_foldered_twin_are_kept(self, tmp_path: Path) -> None:
        """
        Test that a flat file with no copy elsewhere (the only copy) is never touched
        """
        root = make_library(tmp_path / 'movies', {'Only.mkv': b'solo'}, {'Other/Different.mkv': b'solo'})

        assert flat_duplicates([root], apply=True) == []
        assert (root / 'Only.mkv').exists()

    def test_a_flat_file_hardlinked_to_its_twin_is_left_alone(self, tmp_path: Path) -> None:
        """
        Test that two names for one inode are not treated as a duplicate (nothing to reclaim, nothing to fix)
        """
        root = make_library(tmp_path / 'movies', {}, {'Film/Film.mkv': b'data'})
        os.link(root / 'Film' / 'Film.mkv', root / 'Film.mkv')

        assert flat_duplicates([root], apply=True) == []
        assert (root / 'Film.mkv').exists()

    def test_staging_directories_dotfiles_and_non_video_are_ignored(self, tmp_path: Path) -> None:
        """
        Test that in-progress extraction, hidden files and non-video files never count as twins or candidates
        """
        root = make_library(
            tmp_path / 'tv',
            {'Ep.mkv': b'same', 'notes.txt': b'same', '.hidden.mkv': b'same'},
            {'.medialink-extract-abcd1234/Ep.mkv': b'same', 'Show/notes.txt': b'same', 'Show/.hidden.mkv': b'same'},
        )
        assert flat_duplicates([root], apply=True) == []

    def test_quick_mode_finds_identical_copies(self, tmp_path: Path) -> None:
        """
        Test that --quick still matches identical large-ish files
        """
        data = os.urandom(2 * 1024 * 1024 + 7)
        root = make_library(tmp_path / 'movies', {'Big.mkv': data}, {'Big/Big.mkv': data})

        (outcome,) = flat_duplicates([root], quick=True)
        assert outcome.action == 'would-remove-flat'


class TestDedupeCommand:
    """
    Tests for the dedupe CLI command
    """
    def test_dry_run_then_apply_reclaims_both_kinds(
        self,
        config: Config,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test one command handling a mirrored legacy copy and a flat duplicate, dry run first
        """
        torrent = make_torrent('Film.2020', {'Film.2020/film.mkv': 10})
        write_source(config, torrent, b'film-bytes')

        (config.movies_root / 'Film.2020').mkdir()
        (config.movies_root / 'Film.2020' / 'film.mkv').write_bytes(b'film-bytes')  # mirrored legacy copy
        (config.movies_root / 'film.mkv').write_bytes(b'film-bytes')                # flat duplicate

        monkeypatch.setenv('MEDIALINK_MEDIA_ROOT', str(config.media_root))
        monkeypatch.setattr(TransmissionClient, 'get_torrents', lambda _self: [torrent])

        assert main(['dedupe']) == EXIT_OK

        dry = capsys.readouterr().out
        assert 'reclaimable' in dry
        assert (config.movies_root / 'film.mkv').exists()

        assert main(['dedupe', '--apply', '--quick']) == EXIT_OK
        assert 'reclaimed' in capsys.readouterr().out

        source = config.downloads_root / 'complete' / 'movies' / 'Film.2020' / 'film.mkv'
        assert os.path.samestat(source.stat(), (config.movies_root / 'Film.2020' / 'film.mkv').stat())
        assert not (config.movies_root / 'film.mkv').exists()


class TestConfigExtraction:
    """
    Tests for the extraction settings
    """
    @pytest.mark.parametrize(
        ('value', 'expected'),
        [(None, True), ('1', True), ('yes', True), ('0', False), ('false', False), ('OFF', False)],
    )
    def test_extract_flag(self, value: str | None, expected: bool) -> None:
        """
        Test that extraction is on by default and the usual false spellings turn it off
        """
        env = {} if value is None else {'MEDIALINK_EXTRACT': value}
        assert Config.from_env(env).extract is expected

    def test_extractor_override(self) -> None:
        """
        Test that MEDIALINK_EXTRACTOR is carried through, trimmed
        """
        assert Config.from_env({'MEDIALINK_EXTRACTOR': ' /opt/unrar '}).extractor == '/opt/unrar'


# ==================================================================================================
# Log noise
# ==================================================================================================


class TestQuietLogs:
    """
    Tests that steady-state conditions are not repeated in the log every cycle
    """

    def test_a_known_problem_is_logged_at_error_only_on_the_announcing_pass(
        self,
        config: Config,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """
        Test that a stuck torrent's error detail is logged once at ERROR, then only at DEBUG
        """
        torrent = make_torrent('Film.2020.mkv', {'Film.2020.mkv': 10})  # never written to disk: source-missing
        state = State(tmp_path / 'state.json')

        with caplog.at_level(logging.DEBUG, logger='medialink.engine'):
            reconcile([torrent], config, state=state, notifier=RecordingNotifier())
            first = [r.levelno for r in caplog.records]
            caplog.clear()
            reconcile([torrent], config, state=state, notifier=RecordingNotifier())
            second = [r.levelno for r in caplog.records]

        assert first == [logging.ERROR]
        assert second == [logging.DEBUG]

    def test_a_dry_run_stays_verbose_about_known_problems(
        self,
        config: Config,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """
        Test that a manual dry run still shows a problem the loop has already announced
        """
        torrent = make_torrent('Film.2020.mkv', {'Film.2020.mkv': 10})
        state = State(tmp_path / 'state.json')
        state.add(f'link:{torrent.hash}')

        with caplog.at_level(logging.DEBUG, logger='medialink.engine'):
            reconcile([torrent], config, dry_run=True, state=state)

        assert [r.levelno for r in caplog.records] == [logging.ERROR]

    def test_heartbeat_is_info_only_when_the_problem_count_changes(
        self,
        config: Config,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """
        Test that a steady known problem produces one INFO heartbeat, not one per cycle
        """
        torrent = make_torrent('Film.2020.mkv', {'Film.2020.mkv': 10})
        client = StubClient([torrent], [torrent], [torrent])

        with caplog.at_level(logging.DEBUG, logger='medialink.cli'):
            run_loop(
                config,
                client,  # type: ignore[arg-type]
                RecordingNotifier(),
                State(tmp_path / 'state.json'),
                sleep=lambda _s: None,
                max_cycles=3,
            )

        beats = [r.levelno for r in caplog.records if r.getMessage().startswith('cycle ok')]
        assert beats == [logging.INFO, logging.DEBUG, logging.DEBUG]

    def test_heartbeat_reports_an_extraction_then_goes_quiet(
        self,
        config: Config,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """
        Test that a pass that extracted a set is INFO and the unchanged pass after it is DEBUG
        """
        # Archive volumes only (no loose .nfo): the extraction is the sole change on the first cycle
        torrent = make_torrent('Rel', {'Rel/rel.rar': 10, 'Rel/rel.r00': 10})
        write_source(config, torrent)
        client = StubClient([torrent], [torrent])
        extractor = Extractor('/usr/bin/7z', FakeRunner({'Rel.mkv': b'video'}))

        with caplog.at_level(logging.DEBUG, logger='medialink.cli'):
            run_loop(
                config,
                client,  # type: ignore[arg-type]
                RecordingNotifier(),
                State(tmp_path / 'state.json'),
                extractor=extractor,
                sleep=lambda _s: None,
                max_cycles=2,
            )

        beats = [r.levelno for r in caplog.records if r.getMessage().startswith('cycle ok')]
        assert beats == [logging.INFO, logging.DEBUG]

    @pytest.mark.parametrize(
        ('marker_present', 'expect_pending'),
        [(True, False), (False, True)],
    )
    def test_dedupe_recognises_finished_extractions(
        self,
        config: Config,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
        marker_present: bool,
        expect_pending: bool,
    ) -> None:
        """
        Test that dedupe's inspection pass reads the extraction markers instead of listing every set as pending
        """
        torrent = archive_torrent()
        write_source(config, torrent)
        if marker_present:
            state = State(config.state_path)
            state.add(f'extracted:{torrent.hash}:Rel/rel.rar')
            state.save()
        monkeypatch.setenv('MEDIALINK_MEDIA_ROOT', str(config.media_root))
        monkeypatch.setattr(TransmissionClient, 'get_torrents', lambda _self: [torrent])

        with caplog.at_level(logging.INFO):
            assert main(['dedupe']) == EXIT_OK

        assert ('would extract' in caplog.text) is expect_pending
