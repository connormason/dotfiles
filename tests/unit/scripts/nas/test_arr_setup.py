"""
Unit tests for scripts/nas/arr_setup.py (Sonarr / Radarr / Prowlarr provisioning)
"""
from __future__ import annotations

import copy
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler
from http.server import HTTPServer
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from typing import ClassVar

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

REPO_ROOT   = Path(__file__).parents[4]
SCRIPT_PATH = REPO_ROOT / 'scripts' / 'nas' / 'arr_setup.py'

assert SCRIPT_PATH.is_file(), (
    f'Script under test not found: {SCRIPT_PATH}\n'
    'Did the script move? Update SCRIPT_PATH in this test module.'
)
sys.path.insert(0, str(SCRIPT_PATH.parent))

from arr_setup import RADARR
from arr_setup import SONARR
from arr_setup import ApiError
from arr_setup import App
from arr_setup import ArrClient
from arr_setup import Run
from arr_setup import SetupError
from arr_setup import apply_top_level
from arr_setup import configure_arr
from arr_setup import configure_prowlarr
from arr_setup import ensure_entry
from arr_setup import ensure_provider
from arr_setup import ensure_singleton
from arr_setup import ensure_tag
from arr_setup import main
from arr_setup import read_api_key
from arr_setup import set_fields
from arr_setup import validation_message

# ==================================================================================================
# Helpers
# ==================================================================================================

SECRET_COOKIE = 'uid=424242; pass=hunter2-secret'  # pragma: allowlist secret (dummy value for leak tests)


class FakeClient:
    """
    In-memory stand-in for ArrClient: canned GET responses, recorded writes, optional queued write errors
    """
    def __init__(
        self,
        app: App = SONARR,
        *,
        collections: dict[str, Any] | None = None,
        singletons: dict[str, Any] | None = None,
        errors: list[Exception] | None = None,
    ) -> None:
        self.app = app
        self.dry_run = False
        self.collections = collections or {}
        self.singletons = singletons or {}
        self.errors = list(errors or [])
        self.writes: list[tuple[str, str, dict[str, Any]]] = []

    def get(self, path: str) -> Any:
        if path in self.singletons:
            return copy.deepcopy(self.singletons[path])
        return copy.deepcopy(self.collections.get(path, []))

    def write(self, method: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
        self.writes.append((method, path, copy.deepcopy(body)))
        if self.errors:
            raise self.errors.pop(0)
        return {**body, 'id': body.get('id', 7)}


def _fail_nth_write(client: FakeClient, *, index: int, errors: list[Exception]) -> Any:
    """
    Wrap ``client.write`` so the ``index``-th call (1-based) raises the queued errors in turn, and others succeed
    """
    original = client.write
    queued = list(errors)
    calls = {'n': 0}

    def write(method: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
        calls['n'] += 1
        if calls['n'] >= index and queued:
            client.writes.append((method, path, copy.deepcopy(body)))
            raise queued.pop(0)
        return original(method, path, body)
    return write


def transmission_schema() -> dict[str, Any]:
    """
    Schema template shaped like the apps' Transmission download client entry
    """
    return {
        'implementation': 'Transmission',
        'configContract': 'TransmissionSettings',
        'enable':         True,
        'fields': [
            {'name': 'host',        'value': 'localhost'},
            {'name': 'port',        'value': 9091},
            {'name': 'useSsl',      'value': False},
            {'name': 'urlBase',     'value': '/transmission/'},
            {'name': 'tvCategory',  'value': 'tv-sonarr'},
            {'name': 'password',    'value': None, 'privacy': 'password'},
        ],
    }


def indexer_schema() -> dict[str, Any]:
    """
    Schema template shaped like Prowlarr's IPTorrents indexer entry
    """
    return {
        'implementation': 'IPTorrents',
        'definitionName': 'IPTorrents',
        'enable':         False,
        'tags':           [],
        'fields': [
            {'name': 'cookie',    'value': '', 'privacy': 'password'},
            {'name': 'userAgent', 'value': None},
        ],
    }


class TestSetFields:
    """
    Tests for set_fields
    """
    def test_changes_only_differing_fields(self) -> None:
        """
        Test that fields already holding the desired value are not reported as changed
        """
        fields = [{'name': 'host', 'value': 'a'}, {'name': 'port', 'value': 1}]

        changed = set_fields(fields, {'host': 'a', 'port': 2})

        assert changed == ['port']
        assert fields == [{'name': 'host', 'value': 'a'}, {'name': 'port', 'value': 2}]

    def test_unconditional_mode_rewrites_equal_values(self) -> None:
        """
        Test that only_if_different=False reports every field, as needed for masked secrets
        """
        fields = [{'name': 'cookie', 'value': '********'}]

        assert set_fields(fields, {'cookie': 'x'}, only_if_different=False) == ['cookie']

    def test_unknown_field_raises_with_choices(self) -> None:
        """
        Test that an unknown field name raises a SetupError that lists the available names
        """
        with pytest.raises(SetupError, match=r"no field 'nope'.*host"):
            set_fields([{'name': 'host', 'value': 'a'}], {'nope': 1})


class TestApplyTopLevel:
    """
    Tests for apply_top_level
    """
    def test_sets_changed_keys_only(self) -> None:
        """
        Test that equal values are skipped and different ones reported
        """
        item = {'enable': True, 'name': 'x'}

        assert apply_top_level(item, {'enable': True, 'name': 'y'}) == ['name']
        assert item['name'] == 'y'

    def test_tags_are_merged_not_replaced(self) -> None:
        """
        Test that existing tags survive and the wanted tag is added
        """
        item = {'tags': [5]}

        assert apply_top_level(item, {'tags': [2]}) == ['tags']
        assert item['tags'] == [2, 5]
        assert apply_top_level(item, {'tags': [2]}) == []


class TestValidationMessage:
    """
    Tests for validation_message
    """
    @pytest.mark.parametrize(
        ('body', 'expected'),
        [
            ('[{"errorMessage": "bad cookie"}, {"errorMessage": "bad url"}]', 'bad cookie; bad url'),
            ('{"message": "boom"}',                                          'boom'),
            ('plain text\n',                                                 'plain text'),
        ],
    )
    def test_formats_known_shapes(self, body: str, expected: str) -> None:
        """
        Test condensing of list, object and non-JSON error bodies
        """
        assert validation_message(body) == expected

    def test_truncates_long_bodies(self) -> None:
        """
        Test that a very long body is cut to 300 characters
        """
        assert len(validation_message('x' * 1000)) == 300


class TestReadApiKey:
    """
    Tests for read_api_key
    """
    def test_reads_key(self, tmp_path: Path) -> None:
        """
        Test that the ApiKey element is returned
        """
        (tmp_path / 'config.xml').write_text('<Config><ApiKey> abc123 </ApiKey></Config>')

        assert read_api_key(tmp_path) == 'abc123'

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        """
        Test that an app that never started gives an actionable error
        """
        with pytest.raises(SetupError, match='has the app started once'):
            read_api_key(tmp_path)

    def test_missing_key_raises(self, tmp_path: Path) -> None:
        """
        Test that a config.xml without an ApiKey is rejected
        """
        (tmp_path / 'config.xml').write_text('<Config><Port>1</Port></Config>')

        with pytest.raises(SetupError, match='no <ApiKey>'):
            read_api_key(tmp_path)


class TestEnsureProvider:
    """
    Tests for ensure_provider
    """
    def test_creates_from_schema_template(self) -> None:
        """
        Test that a missing provider is built from the schema and posted with values, secrets and defaults
        """
        client = FakeClient(collections={'downloadclient/schema': [transmission_schema()]})

        outcome = ensure_provider(
            client, 'downloadclient', 'Transmission', 'Transmission',
            values={'host': 'transmission', 'tvCategory': 'tv'},
            secrets={'password': 'pw'},  # pragma: allowlist secret
            top={'enable': True},
            defaults={'priority': 3},
        )

        assert outcome.status == 'created'
        method, path, body = client.writes[0]
        assert (method, path) == ('POST', 'downloadclient')
        assert body['name'] == 'Transmission'
        assert body['priority'] == 3
        fields = {f['name']: f['value'] for f in body['fields']}
        assert fields['host'] == 'transmission'
        assert fields['tvCategory'] == 'tv'
        assert fields['port'] == 9091
        assert fields['password'] == 'pw'  # pragma: allowlist secret

    def test_unchanged_when_everything_matches(self) -> None:
        """
        Test that an identical existing provider causes no write
        """
        existing = transmission_schema() | {'id': 3, 'name': 'Transmission'}
        client = FakeClient(collections={'downloadclient': [existing]})

        outcome = ensure_provider(
            client, 'downloadclient', 'Transmission', 'Transmission',
            values={'host': 'localhost'}, top={'enable': True},
        )

        assert outcome.status == 'unchanged'
        assert client.writes == []

    def test_updates_differing_field_with_put(self) -> None:
        """
        Test that a drifted field is corrected by a PUT to the provider's id
        """
        existing = transmission_schema() | {'id': 3, 'name': 'Transmission'}
        client = FakeClient(collections={'downloadclient': [existing]})

        outcome = ensure_provider(
            client, 'downloadclient', 'Transmission', 'Transmission', values={'host': 'transmission'},
        )

        assert outcome.status == 'updated'
        assert client.writes[0][:2] == ('PUT', 'downloadclient/3')

    def test_secrets_rewritten_only_on_refresh(self) -> None:
        """
        Test that masked secrets of an existing provider are left alone unless refresh_secrets is set
        """
        existing = transmission_schema() | {'id': 3, 'name': 'Transmission'}
        client = FakeClient(collections={'downloadclient': [existing]})
        kwargs: dict[str, Any] = {'values': {}, 'secrets': {'password': 'new'}}

        assert ensure_provider(client, 'downloadclient', 'Transmission', 'Transmission', **kwargs).status == 'unchanged'
        assert ensure_provider(
            client, 'downloadclient', 'Transmission', 'Transmission', refresh_secrets=True, **kwargs,
        ).status == 'updated'

    def test_unknown_implementation_raises(self) -> None:
        """
        Test that a schema without the requested implementation is reported clearly
        """
        client = FakeClient(collections={'downloadclient/schema': [transmission_schema()]})

        with pytest.raises(SetupError, match="no downloadclient implementation 'Deluge'"):
            ensure_provider(client, 'downloadclient', 'Deluge', 'Deluge', values={})

    def test_failed_connection_test_saves_disabled(self) -> None:
        """
        Test that a 400 on save makes a second attempt with the provider disabled and reports a warning
        """
        client = FakeClient(
            app=SONARR,
            collections={'indexer/schema': [indexer_schema()]},
            errors=[ApiError(400, 'credentials invalid')],
        )

        outcome = ensure_provider(
            client, 'indexer', 'IPTorrents', 'IPTorrents',
            values={}, secrets={'cookie': SECRET_COOKIE}, top={'enable': True}, disable_on_test_failure=True,
        )

        assert outcome.status == 'warning'
        assert 'credentials invalid' in outcome.detail
        assert SECRET_COOKIE not in outcome.detail
        assert [w[2]['enable'] for w in client.writes] == [True, False]

    def test_other_errors_propagate(self) -> None:
        """
        Test that a non-400 failure, or a 400 without the fallback enabled, is raised
        """
        schema = {'indexer/schema': [indexer_schema()]}
        with pytest.raises(ApiError):
            ensure_provider(
                FakeClient(collections=schema, errors=[ApiError(500, 'x')]),
                'indexer', 'IPTorrents', 'IPTorrents', values={}, disable_on_test_failure=True,
            )
        with pytest.raises(ApiError):
            ensure_provider(
                FakeClient(collections=schema, errors=[ApiError(400, 'x')]),
                'indexer', 'IPTorrents', 'IPTorrents', values={},
            )


class TestEnsureHelpers:
    """
    Tests for ensure_singleton, ensure_entry and ensure_tag
    """
    def test_singleton_updates_then_is_unchanged(self) -> None:
        """
        Test that a config object is PUT by id only when a key differs
        """
        client = FakeClient(singletons={'config/naming': {'id': 1, 'renameEpisodes': False}})

        assert ensure_singleton(client, 'config/naming', {'renameEpisodes': True}).status == 'updated'
        assert client.writes[0][:2] == ('PUT', 'config/naming/1')
        assert ensure_singleton(client, 'config/naming', {'renameEpisodes': False}).status == 'unchanged'

    def test_entry_created_only_when_missing(self) -> None:
        """
        Test that a root folder is posted once and recognized afterwards
        """
        empty = FakeClient()
        assert ensure_entry(empty, 'rootfolder', {'path': '/data/tv'}, {'path': '/data/tv'}).status == 'created'
        assert empty.writes[0][:2] == ('POST', 'rootfolder')

        present = FakeClient(collections={'rootfolder': [{'id': 1, 'path': '/data/tv'}]})
        assert ensure_entry(present, 'rootfolder', {'path': '/data/tv'}, {'path': '/data/tv'}).status == 'unchanged'

    def test_tag_reused_or_created(self) -> None:
        """
        Test that an existing tag's id is returned without a write, and a missing one is created
        """
        assert ensure_tag(FakeClient(collections={'tag': [{'id': 4, 'label': 'x'}]}), 'x') == 4

        creating = FakeClient()
        assert ensure_tag(creating, 'x') == 7
        assert creating.writes[0][2] == {'label': 'x'}


class TestConfigureArr:
    """
    Tests for configure_arr
    """
    @pytest.mark.parametrize(
        ('app', 'root', 'category_field', 'category'),
        [
            (SONARR, '/data/tv',     'tvCategory',    'tv'),
            (RADARR, '/data/movies', 'movieCategory', 'movies'),
        ],
    )
    def test_wires_root_client_mapping_and_settings(
        self, app: Any, root: str, category_field: str, category: str,
    ) -> None:
        """
        Test that each arr gets its root folder, Transmission client, path mapping and config objects
        """
        schema = transmission_schema()
        schema['fields'] = [f for f in schema['fields'] if f['name'] != 'tvCategory']
        schema['fields'].append({'name': category_field, 'value': 'default'})
        client = FakeClient(
            app=app,
            collections={'downloadclient/schema': [schema]},
            singletons={
                'config/naming':          {'id': 1},
                'config/mediamanagement': {'id': 1},
                'config/downloadclient':  {'id': 1, 'enableCompletedDownloadHandling': True},
            },
        )
        run = Run()

        configure_arr(client, app, run)

        writes = {(m, p): b for m, p, b in client.writes}
        assert writes[('POST', 'rootfolder')] == {'path': root}
        fields = {f['name']: f['value'] for f in writes[('POST', 'downloadclient')]['fields']}
        assert fields['host'] == 'transmission'
        assert fields[category_field] == category
        assert writes[('POST', 'remotepathmapping')] == {
            'host': 'transmission', 'remotePath': '/downloads/', 'localPath': '/data/downloads/',
        }
        assert writes[('PUT', 'config/mediamanagement/1')]['copyUsingHardlinks'] is True
        assert ('PUT', 'config/naming/1') in writes
        assert ('PUT', 'config/downloadclient/1') not in writes
        assert run.failures == 0

    def test_step_failure_is_counted_not_raised(self, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that one failing step does not stop the others
        """
        client = FakeClient(
            app=SONARR,
            errors=[ApiError(400, 'path missing')],
            singletons={
                'config/naming':          {'id': 1},
                'config/mediamanagement': {'id': 1},
                'config/downloadclient':  {'id': 1},
            },
        )
        run = Run()

        configure_arr(client, SONARR, run)

        assert run.failures >= 1
        assert 'path missing' in capsys.readouterr().out
        assert len(client.writes) > 1


class TestConfigureProwlarr:
    """
    Tests for configure_prowlarr
    """
    def make_client(self, **extra: Any) -> FakeClient:
        """
        Build a Prowlarr fake with schemas for the proxy, both applications and the indexer
        """
        def app_schema(name: str) -> dict[str, Any]:
            return {
                'implementation': name,
                'fields': [
                    {'name': 'prowlarrUrl', 'value': ''},
                    {'name': 'baseUrl',     'value': ''},
                    {'name': 'apiKey',      'value': None, 'privacy': 'apiKey'},
                ],
            }

        collections = {
            'indexerproxy/schema': [{
                'implementation': 'FlareSolverr',
                'tags': [],
                'fields': [{'name': 'host', 'value': ''}, {'name': 'requestTimeout', 'value': 60}],
            }],
            'applications/schema': [app_schema('Sonarr'), app_schema('Radarr')],
            'indexer/schema':      [indexer_schema()],
            'appprofile':          [{'id': 1, 'name': 'Standard'}],
        }
        return FakeClient(app=SONARR, collections=collections | extra)

    def test_provisions_proxy_applications_and_indexer(self) -> None:
        """
        Test the full Prowlarr wiring: tagged proxy, container-name application URLs with UrlBase, tagged indexer
        """
        client = self.make_client()
        run = Run()

        configure_prowlarr(
            client, run,
            arr_keys={'sonarr': 'sk', 'radarr': 'rk'}, cookie=SECRET_COOKIE, user_agent='UA/1', refresh_secrets=False,
        )

        posts = {b['name']: b for m, p, b in client.writes if m == 'POST' and p != 'tag'}
        proxy_host = next(f['value'] for f in posts['FlareSolverr']['fields'] if f['name'] == 'host')
        assert proxy_host == 'http://flaresolverr:8191/'
        assert posts['FlareSolverr']['tags'] == [7]

        sonarr = {f['name']: f['value'] for f in posts['Sonarr']['fields']}
        assert sonarr['prowlarrUrl'] == 'http://prowlarr:9696/prowlarr'
        assert sonarr['baseUrl'] == 'http://sonarr:8989/sonarr'
        assert sonarr['apiKey'] == 'sk'  # pragma: allowlist secret
        assert posts['Sonarr']['syncLevel'] == 'fullSync'
        assert {f['name']: f['value'] for f in posts['Radarr']['fields']}['baseUrl'] == 'http://radarr:7878/radarr'

        indexer = posts['IPTorrents']
        assert indexer['tags'] == [7]
        assert indexer['enable'] is True
        assert indexer['appProfileId'] == 1
        assert {f['name']: f['value'] for f in indexer['fields']} == {'cookie': SECRET_COOKIE, 'userAgent': 'UA/1'}
        assert run.failures == 0

    @pytest.mark.parametrize('errors', [[], [ApiError(400, 'invalid credentials')]], ids=['saved', 'rejected'])
    def test_cookie_and_api_keys_never_printed(
        self, capsys: pytest.CaptureFixture[str], errors: list[Exception],
    ) -> None:
        """
        Test that neither a saved nor a rejected indexer leaks the cookie or the app API keys to stdout or stderr
        """
        client = self.make_client()
        # Writes run tag, proxy, Sonarr, Radarr, indexer: the indexer is the fifth
        client.write = _fail_nth_write(client, index=5, errors=errors)  # type: ignore[method-assign]

        configure_prowlarr(
            client, Run(), arr_keys={'sonarr': 'SONARR-KEY-123', 'radarr': 'RADARR-KEY-456'},
            cookie=SECRET_COOKIE, user_agent='UA', refresh_secrets=False,
        )

        output = ''.join(capsys.readouterr())
        for secret in (SECRET_COOKIE, 'SONARR-KEY-123', 'RADARR-KEY-456'):
            assert secret not in output

    def test_missing_cookie_skips_new_indexer_with_warning(self, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that without a cookie a not-yet-existing indexer is skipped and flagged, not failed
        """
        client = self.make_client()
        run = Run()

        configure_prowlarr(
            client, run, arr_keys={'sonarr': 'sk', 'radarr': 'rk'}, cookie='', user_agent='', refresh_secrets=False,
        )

        assert run.warnings == 1
        assert run.failures == 0
        assert 'IPTORRENTS_COOKIE' in capsys.readouterr().out
        assert not any(b.get('name') == 'IPTorrents' for _, _, b in client.writes)

    def test_disabled_indexer_gets_new_cookie_without_refresh_flag(self) -> None:
        """
        Test that an indexer left disabled by a failed test is re-saved with the new cookie and enabled
        """
        existing = indexer_schema() | {'id': 9, 'name': 'IPTorrents', 'enable': False}
        client = self.make_client(indexer=[existing])

        configure_prowlarr(
            client, Run(), arr_keys={'sonarr': 'sk', 'radarr': 'rk'}, cookie=SECRET_COOKIE, user_agent='',
            refresh_secrets=False,
        )

        puts = [(p, b) for m, p, b in client.writes if m == 'PUT' and p.startswith('indexer/')]
        assert puts[0][0] == 'indexer/9'
        assert puts[0][1]['enable'] is True
        assert {f['name']: f['value'] for f in puts[0][1]['fields']}['cookie'] == SECRET_COOKIE


class _Handler(BaseHTTPRequestHandler):
    """
    Stub Servarr endpoint recording requests; /api/v3/missing answers 400 with a validation body
    """
    seen: ClassVar[list[dict[str, Any]]] = []

    def _respond(self) -> None:
        length = int(self.headers.get('Content-Length') or 0)
        body = self.rfile.read(length).decode() if length else ''
        type(self).seen.append({
            'method': self.command, 'path': self.path, 'key': self.headers.get('X-Api-Key'), 'body': body,
        })
        if self.path.endswith('/missing'):
            payload, status = b'[{"errorMessage": "nope"}]', 400
        else:
            payload, status = b'{"ok": true}', 200
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = do_POST = do_PUT = _respond

    def log_message(self, format: str, *args: Any) -> None:
        pass


@pytest.fixture
def stub_port() -> Iterator[int]:
    """
    Run a stub HTTP server on an ephemeral port for the duration of one test
    """
    _Handler.seen = []
    server = HTTPServer(('127.0.0.1', 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()


class TestArrClient:
    """
    Tests for ArrClient against a stub HTTP server
    """
    def make(self, port: int, *, dry_run: bool = False) -> ArrClient:
        """
        Build a client whose app port is the stub's port (via the port offset)
        """
        return ArrClient(SONARR, '127.0.0.1', 'KEY', port_offset=port - SONARR.port, dry_run=dry_run)

    def test_get_sends_api_key_and_prefix(self, stub_port: int) -> None:
        """
        Test that requests carry the API key and the UrlBase-prefixed versioned path
        """
        assert self.make(stub_port).get('system/status') == {'ok': True}

        seen = _Handler.seen[0]
        assert seen['path'] == '/sonarr/api/v3/system/status'
        assert seen['key'] == 'KEY'

    def test_write_posts_json_body(self, stub_port: int) -> None:
        """
        Test that write serializes the body as JSON
        """
        self.make(stub_port).write('POST', 'rootfolder', {'path': '/data/tv'})

        assert json.loads(_Handler.seen[0]['body']) == {'path': '/data/tv'}

    def test_dry_run_write_sends_nothing(self, stub_port: int) -> None:
        """
        Test that a dry-run client echoes the body and performs no request
        """
        assert self.make(stub_port, dry_run=True).write('POST', 'rootfolder', {'a': 1}) == {'a': 1}
        assert _Handler.seen == []

    def test_http_error_becomes_api_error(self, stub_port: int) -> None:
        """
        Test that an error status raises ApiError carrying the condensed validation message
        """
        with pytest.raises(ApiError) as exc_info:
            self.make(stub_port).get('missing')

        assert exc_info.value.status == 400
        assert exc_info.value.message == 'nope'

    def test_unreachable_app_raises_setup_error(self) -> None:
        """
        Test that a closed port is reported as SetupError rather than a raw urllib exception
        """
        with pytest.raises(SetupError, match='unreachable'):
            ArrClient(SONARR, '127.0.0.1', 'KEY', port_offset=1 - SONARR.port).get('system/status')


class TestMain:
    """
    Tests for main
    """
    def test_rejects_malformed_cookie(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that a cookie without name=value pairs is refused before any network access
        """
        monkeypatch.setenv('IPTORRENTS_COOKIE', 'justavalue')

        assert main([]) == 2
        assert 'cookie string' in capsys.readouterr().out

    def test_missing_config_xml_fails_cleanly(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that an app that never started produces an error and exit code 1
        """
        monkeypatch.delenv('IPTORRENTS_COOKIE', raising=False)

        assert main(['--config-root', str(tmp_path)]) == 1
        assert 'config.xml' in capsys.readouterr().out
