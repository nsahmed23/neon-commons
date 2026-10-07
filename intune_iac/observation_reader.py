"""Explicit Graph reader capabilities and atomic observation publication.

Only the fixed native TLS constructor produces live assurance. Inert captures,
fixtures and serialized receipts cannot reconstruct that process capability.
The supported trust boundary is a cooperative private host, not its owner.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import os
from pathlib import Path
import time
from urllib.parse import urlencode, urlsplit
from uuid import UUID

from . import capture as capture_module
from .capture_adapter import load_capture
from .identity_binding import ClientSecretHandle, ServiceResponse, _NativeTransport, _Request
from .io import AppError, canonical, digest, parse_json
from .workbench_store import WorkbenchStore, _json, _validate_body

_LIVE = object()
_LAB = object()
_CAPTURE = object()
VERSION = 'intune-graph-reader/1'
MAX_OBJECTS = 100


def _fail(code):
    raise AppError(code, 'The explicit reader identity, scope, lifetime or observation binding is unavailable or changed.')


def _uuid(value):
    try:
        if type(value) is not str or str(UUID(value)) != value or not UUID(value).int:
            raise ValueError()
    except (ValueError, AttributeError):
        _fail('reader_identity_invalid')
    return value


@dataclass(frozen=True)
class ReaderSpec:
    tenant_id: str
    client_id: str
    principal_object_id: str
    object_ids: tuple[str, ...]

    def validate(self):
        for value in (self.tenant_id, self.client_id, self.principal_object_id):
            _uuid(value)
        if (type(self.object_ids) is not tuple or not 1 <= len(self.object_ids) <= MAX_OBJECTS
                or tuple(sorted(set(self.object_ids))) != self.object_ids):
            _fail('reader_scope_invalid')
        for value in self.object_ids:
            _uuid(value)
        return self


def _response_json(response):
    if (type(response) is not ServiceResponse or type(response.status) is not int
            or type(response.body) is not bytes or len(response.body) > 1024 * 1024
            or type(response.headers) is not tuple or len(response.headers) > 100):
        _fail('reader_response_invalid')
    headers = {}
    for item in response.headers:
        if type(item) is not tuple or len(item) != 2:
            _fail('reader_response_invalid')
        key, value = item
        if (type(key) is not str or type(value) is not str or len(key) > 128 or len(value) > 8192
                or any(ord(c) < 32 or ord(c) > 126 for c in key + value) or key.lower() in headers):
            _fail('reader_response_invalid')
        headers[key.lower()] = value
    if 300 <= response.status < 400:
        _fail('reader_redirect_rejected')
    if response.status in (400, 401):
        _fail('reader_authentication_failed')
    if response.status == 403:
        _fail('reader_permission_denied')
    if response.status != 200:
        _fail('reader_identity_service_unavailable')
    if (headers.get('content-type', '').split(';')[0].lower() != 'application/json'
            or headers.get('content-encoding', 'identity').lower() not in ('', 'identity')):
        _fail('reader_response_invalid')
    try:
        value = parse_json(response.body)
    except AppError:
        _fail('reader_response_invalid')
    if type(value) is not dict:
        _fail('reader_response_invalid')
    return value


def _authenticate(spec, credential, transport, deadline, clock):
    spec.validate()
    if type(credential) is not ClientSecretHandle:
        _fail('reader_credential_required')
    def request(method, host, path, *, body=None, token=None):
        remaining = deadline - clock()
        if remaining <= 0:
            _fail('reader_deadline')
        headers = {'Accept': 'application/json', 'Accept-Encoding': 'identity'}
        if body is not None:
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
        if token is not None:
            headers['Authorization'] = 'Bearer ' + token
        try:
            response = transport(_Request(method, host, path, headers, body),
                                 timeout=min(10, remaining), max_bytes=1024 * 1024)
        except AppError:
            raise
        except Exception:
            _fail('reader_identity_transport_unavailable')
        if clock() >= deadline:
            _fail('reader_deadline')
        return _response_json(response)
    started = clock()
    body = urlencode({'client_id': spec.client_id, 'client_secret': credential._get(),
                      'scope': 'https://graph.microsoft.com/.default',
                      'grant_type': 'client_credentials'}).encode('ascii')
    result = request('POST', 'login.microsoftonline.com',
                     '/' + spec.tenant_id + '/oauth2/v2.0/token', body=body)
    token, lifetime = result.get('access_token'), result.get('expires_in')
    if (result.get('token_type') not in ('Bearer', 'bearer') or type(lifetime) is not int
            or not 1 <= lifetime <= 86400 or type(token) is not str or not 1 <= len(token) <= 16384
            or any(ord(c) < 33 or ord(c) > 126 for c in token)):
        _fail('reader_token_invalid')
    identity = request('GET', 'graph.microsoft.com',
        "/v1.0/servicePrincipals(appId='" + spec.client_id + "')?$select=id,appId,accountEnabled", token=token)
    expected = {'id': spec.principal_object_id, 'appId': spec.client_id, 'accountEnabled': True}
    facts = {key: identity.get(key) for key in expected}
    if facts != expected or type(facts['accountEnabled']) is not bool:
        _fail('reader_principal_mismatch')
    expiry = min(started + lifetime, deadline)
    if clock() >= expiry:
        _fail('reader_expired')
    return token, expiry, digest({'tenant_id': spec.tenant_id, **facts})


class _Reader:
    __slots__ = ('_spec', '_credential', '_transport', '_clock', '_token', '_expiry', '_identity', '_pid', '_closed')

    def __init__(self, seal, spec, credential, transport, clock, token, expiry, identity):
        if not ((type(self) is LiveGraphReader and seal is _LIVE)
                or (type(self) is LaboratoryGraphReader and seal is _LAB)):
            _fail('reader_constructor_forbidden')
        self._spec, self._credential, self._transport, self._clock = spec, credential, transport, clock
        self._token, self._expiry, self._identity = token, expiry, identity
        self._pid, self._closed = os.getpid(), False

    def __repr__(self):
        return '<' + type(self).__name__ + ' redacted>'

    def __reduce_ex__(self, protocol):
        raise TypeError('Reader capabilities cannot be serialized.')

    def _fresh(self):
        if self._closed or self._pid != os.getpid():
            _fail('reader_closed')
        self._credential._get()
        if self._clock() >= self._expiry:
            _fail('reader_expired')

    def evidence(self):
        self._fresh()
        live = type(self) is LiveGraphReader
        return {'schema_version': VERSION, 'identity': asdict(self._spec),
                'identity_observation_sha256': self._identity,
                'evidence_class': 'graph_authenticated_observation' if live else 'graph_reader_laboratory',
                'tenant_assurance': 'tenant_specific_oauth_and_service_principal_read' if live else 'laboratory_recorded_responses',
                'source_authenticity_verified': live, 'provider_qualified': False,
                'execution_authorized': False, 'cloud_authority': False,
                'read_scope': {'configuration_policy_listing': 'tenant-wide',
                               'settings_and_assignments': list(self._spec.object_ids)},
                'limitations': ['Reader authentication establishes observed reads, not mutation authority.',
                               'Local persisted receipts are not independent tamper-proof authentication.']}

    def capture(self, object_id, output, *, max_elapsed_seconds=120):
        self._fresh()
        if object_id not in self._spec.object_ids:
            _fail('reader_scope_mismatch')
        roots = (capture_module.GRAPH_ROOT,
                 capture_module.GRAPH_ROOT + '/' + object_id + '/settings',
                 capture_module.GRAPH_ROOT + '/' + object_id + '/assignments')
        remaining = min(float(max_elapsed_seconds), self._expiry - self._clock(), 120)
        if remaining <= 0:
            _fail('reader_expired')
        deadline = self._clock() + remaining
        def get(url):
            self._fresh()
            if not any(capture_module._trusted(url, root) for root in roots):
                _fail('reader_destination_rejected')
            remaining = min(deadline, self._expiry) - self._clock()
            if remaining <= 0:
                _fail('reader_deadline')
            parsed = urlsplit(url)
            request = _Request('GET', 'graph.microsoft.com', parsed.path + ('?' + parsed.query if parsed.query else ''),
                {'Authorization': 'Bearer ' + self._token, 'Accept': 'application/json', 'Accept-Encoding': 'identity'})
            response = self._transport(request, timeout=min(20, remaining), max_bytes=capture_module.MAX_PAGE_BYTES)
            if type(response) is not ServiceResponse:
                _fail('reader_response_invalid')
            return response.status, response.body, response.headers
        result = capture_module.capture(self._spec.tenant_id, object_id, output, transport=get,
            max_elapsed_seconds=remaining, max_pages=100, max_attempts_per_page=3, max_retry_delay_seconds=30)
        batch = load_capture(output, tenant_id=self._spec.tenant_id)
        # Preserve the completed observation even if the token expires just
        # after its last response; its immutable evidence was bound before read.
        live = type(self) is LiveGraphReader
        source = {'schema_version': VERSION, 'identity': asdict(self._spec),
            'identity_observation_sha256': self._identity,
            'evidence_class': 'graph_authenticated_observation' if live else 'graph_reader_laboratory',
            'tenant_assurance': 'tenant_specific_oauth_and_service_principal_read' if live else 'laboratory_recorded_responses',
            'source_authenticity_verified': live, 'provider_qualified': False,
            'execution_authorized': False, 'cloud_authority': False,
            'read_scope': {'configuration_policy_listing': 'tenant-wide', 'settings_and_assignments': list(self._spec.object_ids)}}
        return CapturedObservation(_CAPTURE, Path(output), batch, source, result['cancelled'])

    def close(self):
        self._token, self._closed = '', True


class LiveGraphReader(_Reader):
    __slots__ = ()


class LaboratoryGraphReader(_Reader):
    __slots__ = ()


def bind_live_reader(spec, *, credential, max_duration_seconds=120):
    """Native public-cloud TLS only; no injectable live transport or clock."""
    return _bind(spec, credential, _NativeTransport(), time.monotonic, max_duration_seconds, _LIVE)


def bind_laboratory_reader(spec, *, credential, transport, max_duration_seconds=120, clock=time.monotonic):
    """Explicit local response seam; never creates native authenticated evidence."""
    if not callable(transport) or not callable(clock):
        _fail('reader_laboratory_invalid')
    return _bind(spec, credential, transport, clock, max_duration_seconds, _LAB)


def _bind(spec, credential, transport, clock, duration, seal):
    if type(spec) is not ReaderSpec or type(duration) not in (float, int) or not 1 <= duration <= 300:
        _fail('reader_configuration_invalid')
    deadline = clock() + duration
    token, expiry, identity = _authenticate(spec, credential, transport, deadline, clock)
    cls = LiveGraphReader if seal is _LIVE else LaboratoryGraphReader
    return cls(seal, spec, credential, transport, clock, token, expiry, identity)


class CapturedObservation:
    __slots__ = ('_path', '_batch', '_source', '_digest', '_pid', 'cancelled')

    def __init__(self, seal, path, batch, source, cancelled):
        if seal is not _CAPTURE:
            _fail('reader_capture_constructor_forbidden')
        self._path, self._batch, self._source = path, batch, source
        self._digest, self._pid, self.cancelled = digest(batch), os.getpid(), cancelled

    def __reduce_ex__(self, protocol):
        raise TypeError('Captured observation capabilities cannot be serialized.')

    def verified(self):
        if self._pid != os.getpid() or digest(self._batch) != self._digest:
            _fail('reader_capture_changed')
        current = load_capture(self._path, tenant_id=self._batch['tenant_id'])
        if digest(current) != self._digest:
            _fail('reader_capture_changed')
        return current, parse_json(canonical(self._source))


def publish_batch(store, captures, *, job_id, attempt_id, failures=()):
    """One SQLite transaction publishes all scoped outcomes, or none.

    Retry of the identical process-held batch is idempotent. Recovery cannot
    reconstruct authentication from disk; uncertain stages require new reads.
    """
    if type(store) is not WorkbenchStore or type(captures) not in (list, tuple):
        _fail('reader_publication_invalid')
    if not 1 <= len(captures) + len(failures) <= MAX_OBJECTS:
        _fail('reader_publication_invalid')
    if any(type(value) is not str or len(value) != 32 or any(c not in '0123456789abcdef' for c in value)
           for value in (job_id, attempt_id)):
        _fail('reader_publication_invalid')
    batches = []
    for item in captures:
        if type(item) is not CapturedObservation:
            _fail('reader_capture_required')
        batch, source = item.verified()
        if batch['tenant_id'] != store.tenant_id:
            _fail('reader_wrong_tenant')
        if batch['status'] == 'complete':
            _validate_body(batch['body'])
        source = {**batch['source'], **source, 'capture_sha256': batch['capture_sha256'],
                  'observer': {'job_id': job_id, 'attempt_id': attempt_id}}
        batches.append((batch, source))
    for failure in failures:
        if (type(failure) is not dict or set(failure) != {'object_id', 'error_code', 'observed_at'}
                or type(failure['error_code']) is not str or not failure['error_code'].replace('_', '').isalnum()):
            _fail('reader_publication_invalid')
        oid = _uuid(failure['object_id'])
        batches.append(({'object_id': oid, 'observed_at': failure['observed_at'], 'status': 'failed',
                         'scope': {'kind': 'policy', 'object_ids': [oid]}, 'body': None,
                         'collections': [{'kind': kind, 'owner_id': None if kind == 'policies' else oid,
                            'coverage': 'unknown', 'reason': failure['error_code'], 'page_count': 0}
                            for kind in ('policies', 'settings', 'assignments')]},
                        {'evidence_class': 'graph_reader_attempt', 'tenant_assurance': 'not_established',
                         'source_authenticity_verified': False, 'provider_qualified': False,
                         'execution_authorized': False, 'cloud_authority': False,
                         'error_code': failure['error_code'],
                         'observer': {'job_id': job_id, 'attempt_id': attempt_id}}))
    if len({batch['object_id'] for batch, _ in batches}) != len(batches):
        _fail('reader_duplicate_publication_scope')
    result_ids = []
    store._require_v2()
    with store._connection(True) as db, db:
        db.execute('BEGIN IMMEDIATE')
        for batch, source in batches:
            oid, observed_at, status = batch['object_id'], batch['observed_at'], batch['status']
            domain = 'reader:' + job_id + ':' + attempt_id + ':' + oid
            existing = db.execute('SELECT run_id,source_json FROM run_details WHERE domain=?', (domain,)).fetchall()
            if existing:
                original = parse_json(existing[0]['source_json']) if len(existing) == 1 else {}
                for key in ('duplicate_of_run_id', 'publication_disposition'):
                    original.pop(key, None)
                if len(existing) != 1 or canonical(original) != canonical(source):
                    _fail('reader_publication_conflict')
                result_ids.append(existing[0]['run_id'])
                continue
            duplicate = None
            if status == 'complete':
                snapshot = digest({'tenant_id': store.tenant_id, 'object_id': oid, 'body': batch['body']})
                with store._query_budget(db) as charge:
                    rows = db.execute('''SELECT r.run_id,d.source_json FROM collection_runs r
                        JOIN run_details d USING(run_id) JOIN observations o USING(run_id)
                        WHERE r.status='complete' AND d.evidence_class=? AND o.tenant_id=?
                            AND o.object_id=? AND o.observed_at=? AND o.snapshot_id=? ORDER BY r.run_id''',
                        (source['evidence_class'], store.tenant_id, oid, observed_at, snapshot))
                    for previous in rows:
                        prior = parse_json(charge(previous['source_json']))
                        if (prior.get('capture_sha256') == source['capture_sha256']
                                and prior.get('identity_observation_sha256') == source['identity_observation_sha256']):
                            duplicate = previous['run_id']
                            source = {**source, 'duplicate_of_run_id': duplicate,
                                      'publication_disposition': 'reused_exact_capture_observation'}
                            break
            all_complete = all(row['coverage'] == 'complete' for row in batch['collections'])
            coverage = 'complete' if all_complete else 'denied' if status == 'denied' else 'partial'
            error = None if status == 'complete' else source.get('error_code', 'capture_' + status)
            run_id = db.execute('INSERT INTO collection_runs(tenant_id,started_at,observed_at,completed_at,status,coverage,error_code,object_count) VALUES(?,?,?,?,?,?,?,?)',
                (store.tenant_id, time.time(), observed_at, time.time(), status, coverage, error, int(status == 'complete'))).lastrowid
            db.execute('INSERT INTO run_details VALUES(?,?,?,?,?)',
                (run_id, _json(batch['scope']), _json(source), source['evidence_class'], domain))
            db.execute('INSERT INTO run_scope_objects VALUES(?,?)', (run_id, oid))
            store._store_coverage(db, run_id, batch['collections'])
            if status == 'complete' and duplicate is None:
                store._store_objects(db, run_id, {oid: batch['body']}, observed_at, source)
            result_ids.append(run_id)
    return [store.collection_detail(run_id) for run_id in result_ids]
