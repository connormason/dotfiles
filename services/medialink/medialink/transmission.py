"""
Minimal Transmission RPC client (standard library only)
"""
from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from dataclasses import field
from typing import Any

__all__ = [
    'Torrent',
    'TorrentFile',
    'TransmissionClient',
    'TransmissionError',
]

SESSION_HEADER = 'X-Transmission-Session-Id'
TORRENT_FIELDS = [
    'id', 'hashString', 'name', 'downloadDir', 'status', 'leftUntilDone', 'labels', 'files', 'error', 'errorString',
]


class TransmissionError(RuntimeError):
    """
    Raised when the RPC endpoint is unreachable or returns an unusable answer
    """


@dataclass(frozen=True)
class TorrentFile:
    """
    One file inside a torrent; ``name`` is relative to the torrent's ``downloadDir``
    """
    name:            str
    length:          int
    bytes_completed: int

    @property
    def complete(self) -> bool:
        """
        Whether every byte of the file is on disk
        """
        return self.bytes_completed >= self.length


@dataclass(frozen=True)
class Torrent:
    """
    The subset of a Transmission torrent that medialink reads
    """
    id:           int
    hash:         str
    name:         str
    download_dir: str
    status:       int
    left:         int
    error:        int
    error_text:   str
    labels:       tuple[str, ...]         = ()
    files:        tuple[TorrentFile, ...] = field(default_factory=tuple)

    @property
    def finished(self) -> bool:
        """
        Whether nothing wanted remains to download
        """
        return self.left == 0

    @classmethod
    def from_rpc(cls, raw: dict[str, Any]) -> Torrent:  # Any: decoded JSON object
        """
        Build a torrent from one ``torrent-get`` entry

        :param raw: decoded JSON object
        :return: the parsed torrent
        """
        files = tuple(
            TorrentFile(name=f['name'], length=int(f['length']), bytes_completed=int(f['bytesCompleted']))
            for f in raw.get('files', [])
        )
        return cls(
            id           = int(raw['id']),
            hash         = str(raw.get('hashString', '')),
            name         = str(raw['name']),
            download_dir = str(raw['downloadDir']),
            status       = int(raw.get('status', 0)),
            left         = int(raw.get('leftUntilDone', 1)),
            error        = int(raw.get('error', 0)),
            error_text   = str(raw.get('errorString', '')),
            labels       = tuple(str(label) for label in raw.get('labels', [])),
            files        = files,
        )


class TransmissionClient:
    """
    Talks JSON-RPC to Transmission, performing the ``409`` session-id handshake transparently
    """
    def __init__(self, url: str, user: str = '', password: str = '', timeout: float = 30.0) -> None:
        """
        Create a client

        :param url: full RPC URL (``http://host:9091/transmission/rpc``)
        :param user: optional basic-auth user
        :param password: optional basic-auth password
        :param timeout: socket timeout in seconds
        """
        self.url        = url
        self.timeout    = timeout
        self.session_id = ''
        self._auth      = ''
        if user or password:
            self._auth = 'Basic ' + base64.b64encode(f'{user}:{password}'.encode()).decode()

    def _post(self, payload: bytes) -> dict[str, Any]:  # Any: decoded JSON object
        """
        POST one payload, retrying once with a fresh session id on HTTP 409

        :param payload: encoded request body
        :raises TransmissionError: on network failure, non-200 status, or invalid JSON
        :return: the decoded response body
        """
        for _ in range(2):
            request = urllib.request.Request(self.url, data=payload, method='POST')  # noqa: S310 - operator-set URL
            request.add_header('Content-Type', 'application/json')
            request.add_header(SESSION_HEADER, self.session_id)
            if self._auth:
                request.add_header('Authorization', self._auth)
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310
                    return json.loads(response.read())
            except urllib.error.HTTPError as e:
                if e.code == 409:
                    self.session_id = e.headers.get(SESSION_HEADER, '')
                    continue
                raise TransmissionError(f'RPC returned HTTP {e.code}') from e
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                raise TransmissionError(f'RPC unreachable: {e}') from e
            except json.JSONDecodeError as e:
                raise TransmissionError('RPC returned invalid JSON') from e
        raise TransmissionError('RPC kept rejecting the session id')

    def get_torrents(self) -> list[Torrent]:
        """
        Fetch every torrent with the fields medialink needs

        :raises TransmissionError: if the RPC call fails
        :return: all torrents known to Transmission
        """
        body     = json.dumps({'method': 'torrent-get', 'arguments': {'fields': TORRENT_FIELDS}}).encode()
        response = self._post(body)
        if response.get('result') != 'success':
            raise TransmissionError(f'torrent-get failed: {response.get("result")!r}')
        try:
            return [Torrent.from_rpc(raw) for raw in response['arguments']['torrents']]
        except (KeyError, TypeError, ValueError) as e:
            raise TransmissionError(f'unexpected torrent-get payload: {e!r}') from e
