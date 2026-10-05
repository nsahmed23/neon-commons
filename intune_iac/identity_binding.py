"""Explicit host-held Azure identity and backend observation.

Only ``bind_live`` mints live identity bindings. JSON and recorded responses are
never authority. Access tokens are opaque; the fixed tenant-specific OAuth
exchange and the receiving services establish the observations. This module
does not grant Intune mutation permission, approval or writer ownership.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from email.utils import formatdate
import hashlib
import http.client
import os
import queue
import re
import socket
import ssl
import threading
import time
from urllib.parse import quote, urlencode

from .io import AppError, canonical, digest, parse_json

MAX_JSON_BYTES = 1024 * 1024
MAX_STATE_BYTES = 16 * 1024 * 1024
_GUID = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
_SHA = re.compile(r'^[0-9a-f]{64}$')
_RELATIVE = re.compile(r'^[A-Za-z0-9_-][A-Za-z0-9_.-]*(/[A-Za-z0-9_-][A-Za-z0-9_.-]*)*$')
_RESOURCE = re.compile(r'^/subscriptions/([0-9a-f-]{36})/resourceGroups/([A-Za-z0-9_()-][A-Za-z0-9_.()-]{0,89})/providers/Microsoft\.Storage/storageAccounts/([a-z0-9]{3,24})$')
_ETAG = re.compile(r'^"[!#-~]{1,128}"$')
_LIVE_SEAL = object()
_LAB_SEAL = object()
_BACKEND_TOKEN_SEAL = object()
_NETWORK_SLOTS = threading.BoundedSemaphore(4)
_GRAPH_SCOPE = 'https://graph.microsoft.com/.default'
_ARM_SCOPE = 'https://management.azure.com/.default'
_STORAGE_SCOPE = 'https://storage.azure.com/.default'


def _fail(code):
    raise AppError(code, 'Explicit identity and service binding was not established.') from None


def _guid(value):
    return type(value) is str and _GUID.fullmatch(value) is not None


class ClientSecretHandle:
    """Host-injected memory credential. Never load this from a plan or evidence.

    No environment lookup, serialization, callback, rotation or default chain.
    ``close`` invalidates contexts using this handle. Python cannot promise
    erasure of string copies; the host must protect its memory and child env.
    """
    __slots__ = ('__secret', '__closed', '__lock')

    def __init__(self, secret):
        if type(secret) is not str or not 1 <= len(secret) <= 4096 or any(ord(c) < 33 or ord(c) > 126 for c in secret):
            _fail('identity_credential_invalid')
        self.__secret, self.__closed = secret, False
        self.__lock = threading.RLock()

    def _get(self):
        with self.__lock:
            if self.__closed: _fail('identity_credential_unavailable')
            return self.__secret

    def close(self):
        with self.__lock:
            self.__closed, self.__secret = True, ''

    def __repr__(self): return '<ClientSecretHandle redacted>'
    def __reduce_ex__(self, protocol): raise TypeError('Credentials cannot be serialized.')


@dataclass(frozen=True)
class IdentitySpec:
    tenant_id: str
    client_id: str
    principal_object_id: str
    auth_method: str = 'client_secret'


@dataclass(frozen=True)
class BackendSpec:
    subscription_id: str
    storage_account_resource_id: str
    blob_endpoint: str
    container: str
    key: str
    workspace: str
    state_lineage: str
    state_serial: int
    state_sha256: str

    @property
    def resolved_blob_name(self):
        return self.key if self.workspace == 'default' else self.key + 'env:' + self.workspace


@dataclass(frozen=True)
class BindingConfig:
    provider: IdentitySpec
    backend_identity: IdentitySpec
    backend: BackendSpec
    cloud: str = 'public'


def _validate(config, provider, backend, timeout, max_age, total_timeout):
    if type(config) is not BindingConfig or config.cloud != 'public': _fail('identity_configuration_invalid')
    for identity in (config.provider, config.backend_identity):
        if type(identity) is not IdentitySpec or identity.auth_method != 'client_secret' or not all(_guid(v) for v in (identity.tenant_id, identity.client_id, identity.principal_object_id)):
            _fail('identity_configuration_invalid')
    b = config.backend
    if type(b) is not BackendSpec: _fail('identity_configuration_invalid')
    resource = _RESOURCE.fullmatch(b.storage_account_resource_id) if type(b.storage_account_resource_id) is str else None
    if (not resource or resource[1] != b.subscription_id or not _guid(b.subscription_id)
            or b.blob_endpoint != 'https://' + resource[3] + '.blob.core.windows.net'
            or type(b.container) is not str or not 3 <= len(b.container) <= 63 or not re.fullmatch(r'[a-z0-9]+(-[a-z0-9]+)*', b.container)
            or type(b.key) is not str or len(b.key) > 512 or not _RELATIVE.fullmatch(b.key)
            or type(b.workspace) is not str or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', b.workspace)
            or not _guid(b.state_lineage) or type(b.state_serial) is not int or not 0 <= b.state_serial <= 9007199254740991
            or type(b.state_sha256) is not str or not _SHA.fullmatch(b.state_sha256)):
        _fail('identity_configuration_invalid')
    if type(provider) is not ClientSecretHandle or type(backend) is not ClientSecretHandle:
        _fail('identity_credential_required')
    if type(timeout) is not int or not 1 <= timeout <= 30 or type(max_age) is not int or not 1 <= max_age <= 300 or type(total_timeout) is not int or not 1 <= total_timeout <= 120:
        _fail('identity_limits_invalid')
    provider._get(); backend._get()


@dataclass(frozen=True, repr=False)
class _Request:
    method: str
    host: str
    path: str
    headers: dict
    body: bytes | None = None

    def __repr__(self): return '<IdentityServiceRequest redacted>'
    def __reduce_ex__(self, protocol): raise TypeError('Credential requests cannot be serialized.')


@dataclass(frozen=True, repr=False)
class ServiceResponse:
    """Laboratory response bytes; returning this never creates live authority."""
    status: int
    headers: tuple
    body: bytes

    def __repr__(self): return '<IdentityServiceResponse redacted>'


def _system_tls_context():
    # SSL_CERT_FILE/SSL_CERT_DIR do not select an alternate trust store here.
    # The operating-system trust store itself is part of the protected host.
    paths = ssl.get_default_verify_paths()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    cafile = paths.openssl_cafile if paths.openssl_cafile and os.path.isfile(paths.openssl_cafile) else None
    capath = paths.openssl_capath if paths.openssl_capath and os.path.isdir(paths.openssl_capath) else None
    if cafile is None and capath is None: _fail('identity_trust_store_unavailable')
    context.load_verify_locations(cafile=cafile, capath=capath)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context


class _NativeTransport:
    """No proxy, redirect, cookies, token cache, environment chain or URL API.

    A bounded daemon worker makes the caller's wall deadline include DNS. An OS
    resolver may outlive that deadline; at most four workers may exist and a
    cancelled worker cannot proceed from connect to send credentials.
    """
    def __call__(self, request, *, timeout, max_bytes):
        if not _NETWORK_SLOTS.acquire(blocking=False): _fail('identity_transport_busy')
        result = queue.Queue(maxsize=1)
        cancelled = threading.Event()
        active = []
        connected_sockets = []

        def stop():
            cancelled.set()
            # getresponse() may clear conn.sock for Connection: close while
            # HTTPResponse's file still owns the socket. Retain it separately
            # so a deadline interrupts that body reader as well.
            for connected in connected_sockets:
                try: connected.shutdown(socket.SHUT_RDWR)
                except OSError: pass
            for conn in active:
                try:
                    if conn.sock is not None: conn.sock.shutdown(socket.SHUT_RDWR)
                except OSError: pass
                try: conn.close()
                except OSError: pass

        def run():
            conn = None
            response = None
            try:
                conn = http.client.HTTPSConnection(request.host, port=443, timeout=timeout, context=_system_tls_context())
                active.append(conn)
                if cancelled.is_set(): return
                conn.connect()
                if conn.sock is not None: connected_sockets.append(conn.sock)
                # A deadline can close the connected socket between this
                # check and HTTPConnection.send. Never let send reconnect and
                # dispatch credentials after cancellation.
                conn.auto_open = 0
                if cancelled.is_set(): return
                conn.request(request.method, request.path, body=request.body, headers=request.headers)
                response = conn.getresponse()
                headers = tuple(response.getheaders())
                if sum(len(k) + len(v) for k, v in headers) > 65536: _fail('identity_response_invalid')
                body = response.read(max_bytes + 1) if request.method != 'HEAD' else b''
                result.put(ServiceResponse(response.status, headers, body))
            except Exception:
                # Never copy server bodies, library exceptions or token bytes.
                result.put(None)
            finally:
                try:
                    if response is not None: response.close()
                finally:
                    try:
                        if conn is not None: conn.close()
                    finally: _NETWORK_SLOTS.release()

        worker = threading.Thread(target=run, daemon=True, name='identity-service-read')
        try:
            try: worker.start()
            except Exception:
                _NETWORK_SLOTS.release()
                _fail('identity_transport_unavailable')
            response = result.get(timeout=timeout)
        except queue.Empty:
            stop()
            _fail('identity_transport_deadline')
        except BaseException:
            stop()
            raise
        if response is None: _fail('identity_transport_unavailable')
        return response


def _routes(config):
    allowed = set()
    for spec in (config.provider, config.backend_identity):
        allowed.add(('POST', 'login.microsoftonline.com', '/' + spec.tenant_id + '/oauth2/v2.0/token'))
        allowed.add(('GET', 'graph.microsoft.com', "/v1.0/servicePrincipals(appId='" + spec.client_id + "')?$select=id,appId,accountEnabled"))
    b = config.backend
    allowed.add(('GET', 'management.azure.com', '/subscriptions/' + b.subscription_id + '?api-version=2022-12-01'))
    allowed.add(('GET', 'management.azure.com', b.storage_account_resource_id + '?api-version=2023-05-01'))
    path = '/' + quote(b.container, safe='') + '/' + quote(b.resolved_blob_name, safe='/')
    host = b.blob_endpoint.removeprefix('https://')
    allowed.update((method, host, path) for method in ('HEAD', 'GET'))
    return frozenset(allowed), host, path


class _Observer:
    def __init__(self, config, provider, backend, transport, clock, timeout, total_timeout):
        self.config, self.provider, self.backend = config, provider, backend
        self.transport, self.clock, self.timeout = transport, clock, timeout
        self.deadline = clock() + total_timeout
        self.allowed, self.blob_host, self.blob_path = _routes(config)
        self.expiries, self.facts = [], {}

    def read(self, method, host, path, *, token=None, body=None, etag=None, blob=False):
        if (method, host, path) not in self.allowed: _fail('identity_destination_rejected')
        remaining = self.deadline - self.clock()
        if remaining <= 0: _fail('identity_transport_deadline')
        headers = {'Accept': 'application/json', 'Accept-Encoding': 'identity'}
        if token is not None: headers['Authorization'] = 'Bearer ' + token
        if body is not None: headers['Content-Type'] = 'application/x-www-form-urlencoded'
        if blob: headers.update({'x-ms-version': '2023-11-03', 'x-ms-date': formatdate(usegmt=True)})
        if etag is not None: headers['If-Match'] = etag
        limit = MAX_STATE_BYTES if blob else MAX_JSON_BYTES
        try:
            response = self.transport(_Request(method, host, path, headers, body), timeout=min(self.timeout, remaining), max_bytes=limit)
        except AppError: raise
        except Exception: _fail('identity_transport_unavailable')
        if self.clock() >= self.deadline: _fail('identity_transport_deadline')
        if type(response) is not ServiceResponse or type(response.status) is not int or type(response.body) is not bytes or len(response.body) > limit or type(response.headers) is not tuple or len(response.headers) > 100:
            _fail('identity_response_invalid')
        collected = {}
        for item in response.headers:
            if type(item) is not tuple or len(item) != 2: _fail('identity_response_invalid')
            k, v = item
            if type(k) is not str or type(v) is not str or not re.fullmatch(r'[A-Za-z0-9-]{1,128}', k) or len(v) > 8192 or any(ord(c) < 32 or ord(c) > 126 for c in v):
                _fail('identity_response_invalid')
            name = k.lower()
            if name in collected: _fail('identity_response_invalid')
            collected[name] = v
        if sum(len(k) + len(v) for k, v in collected.items()) > 65536: _fail('identity_response_invalid')
        if 300 <= response.status <= 399: _fail('identity_redirect_rejected')
        if response.status == 401 or (method == 'POST' and response.status == 400): _fail('identity_authentication_failed')
        if response.status == 403: _fail('identity_permission_denied')
        if blob and response.status == 412: _fail('identity_state_changed')
        if response.status != 200: _fail('identity_service_unavailable')
        if collected.get('content-encoding', 'identity').lower() not in ('', 'identity'): _fail('identity_response_invalid')
        length = collected.get('content-length')
        if length is not None and (not re.fullmatch(r'[0-9]{1,9}', length) or int(length) > limit or (method != 'HEAD' and int(length) != len(response.body))):
            _fail('identity_response_invalid')
        if blob: return collected, response.body
        if collected.get('content-type', '').split(';')[0].lower() != 'application/json': _fail('identity_response_invalid')
        try: value = parse_json(response.body)
        except AppError: _fail('identity_response_invalid')
        if type(value) is not dict: _fail('identity_response_invalid')
        return value

    def token(self, spec, handle, scope):
        started = self.clock()
        body = urlencode({'client_id': spec.client_id, 'client_secret': handle._get(), 'scope': scope, 'grant_type': 'client_credentials'}).encode('ascii')
        response = self.read('POST', 'login.microsoftonline.com', '/' + spec.tenant_id + '/oauth2/v2.0/token', body=body)
        token, expiry = response.get('access_token'), response.get('expires_in')
        if (response.get('token_type') not in ('Bearer', 'bearer') or type(expiry) is not int or not 1 <= expiry <= 86400
                or type(token) is not str or not 1 <= len(token) <= 16384 or any(ord(c) < 33 or ord(c) > 126 for c in token)):
            _fail('identity_token_response_invalid')
        if self.clock() >= started + expiry: _fail('identity_token_expired')
        # Use response lifetime only. Never parse JWTs or infer client/tenant
        # claims from these Microsoft-owned resource tokens.
        self.expiries.append(started + expiry)
        return token

    def identity(self, label, spec, handle):
        token = self.token(spec, handle, _GRAPH_SCOPE)
        value = self.read('GET', 'graph.microsoft.com', "/v1.0/servicePrincipals(appId='" + spec.client_id + "')?$select=id,appId,accountEnabled", token=token)
        facts = {'id': value.get('id'), 'appId': value.get('appId'), 'accountEnabled': value.get('accountEnabled')}
        if facts != {'id': spec.principal_object_id, 'appId': spec.client_id, 'accountEnabled': True} or type(facts['accountEnabled']) is not bool:
            _fail('identity_service_principal_mismatch')
        self.facts[label] = digest({'tenant_id': spec.tenant_id, **facts})

    def observe(self):
        c, b = self.config, self.config.backend
        self.identity('provider_identity', c.provider, self.provider)
        self.identity('backend_identity', c.backend_identity, self.backend)
        token = self.token(c.backend_identity, self.backend, _ARM_SCOPE)
        subscription = self.read('GET', 'management.azure.com', '/subscriptions/' + b.subscription_id + '?api-version=2022-12-01', token=token)
        facts = {k: subscription.get(k) for k in ('subscriptionId', 'tenantId', 'state')}
        if facts != {'subscriptionId': b.subscription_id, 'tenantId': c.backend_identity.tenant_id, 'state': 'Enabled'}:
            _fail('identity_subscription_mismatch')
        self.facts['subscription'] = digest(facts)
        account = self.read('GET', 'management.azure.com', b.storage_account_resource_id + '?api-version=2023-05-01', token=token)
        properties = account.get('properties')
        endpoints = properties.get('primaryEndpoints') if type(properties) is dict else None
        endpoint = endpoints.get('blob') if type(endpoints) is dict else None
        if account.get('id') != b.storage_account_resource_id or endpoint not in (b.blob_endpoint, b.blob_endpoint + '/'):
            _fail('identity_storage_target_mismatch')
        self.facts['storage_account'] = digest({'resource_id': account['id'], 'blob_endpoint': b.blob_endpoint})
        token = self.token(c.backend_identity, self.backend, _STORAGE_SCOPE)
        head, _ = self.read('HEAD', self.blob_host, self.blob_path, token=token, blob=True)
        first = self.blob_properties(head)
        get, body = self.read('GET', self.blob_host, self.blob_path, token=token, etag=first['etag'], blob=True)
        if self.blob_properties(get) != first or len(body) != first['length']: _fail('identity_state_changed')
        try: state = parse_json(body)
        except AppError: _fail('identity_state_mismatch')
        if (type(state) is not dict or type(state.get('version')) is not int or state['version'] != 4
                or state.get('lineage') != b.state_lineage or type(state.get('serial')) is not int or state['serial'] != b.state_serial
                or hashlib.sha256(body).hexdigest() != b.state_sha256):
            _fail('identity_state_mismatch')
        final, _ = self.read('HEAD', self.blob_host, self.blob_path, token=token, etag=first['etag'], blob=True)
        if self.blob_properties(final) != first: _fail('identity_state_changed')
        self.facts['state_blob'] = digest({'etag': first['etag'], 'lineage': state['lineage'], 'serial': state['serial'], 'sha256': b.state_sha256, 'length': len(body)})
        self.provider._get(); self.backend._get()
        if self.clock() >= min(self.expiries): _fail('identity_token_expired')
        return self.facts, min(self.expiries)

    @staticmethod
    def blob_properties(headers):
        etag, length = headers.get('etag'), headers.get('content-length')
        if type(etag) is not str or not _ETAG.fullmatch(etag) or type(length) is not str or not re.fullmatch(r'[0-9]{1,9}', length) or not 1 <= int(length) <= MAX_STATE_BYTES or headers.get('x-ms-blob-type') != 'BlockBlob':
            _fail('identity_state_properties_invalid')
        return {'etag': etag, 'length': int(length), 'blob_type': 'BlockBlob'}


class BoundContext:
    """Nonserializable process capability with observations, never permissions."""
    __slots__ = ('_config', '_provider', '_backend', '_transport', '_clock', '_timeout', '_max_age', '_total_timeout', '_facts', '_expiry', '_observed', '_binding_sha256', '_valid', '_lock', '_pid')

    def __init__(self, seal, config, provider, backend, transport, clock, timeout, max_age, total_timeout, facts, expiry):
        if (type(self) is LiveIdentityBinding and seal is not _LIVE_SEAL) or (type(self) is LaboratoryIdentityBinding and seal is not _LAB_SEAL) or type(self) not in (LiveIdentityBinding, LaboratoryIdentityBinding):
            _fail('identity_constructor_forbidden')
        self._config, self._provider, self._backend = config, provider, backend
        self._transport, self._clock, self._timeout = transport, clock, timeout
        self._max_age, self._total_timeout = max_age, total_timeout
        self._facts, self._expiry, self._observed = facts.copy(), expiry, clock()
        self._binding_sha256 = digest({'config': asdict(config), 'observations': facts})
        self._valid, self._lock, self._pid = True, threading.RLock(), os.getpid()

    def __repr__(self): return '<' + type(self).__name__ + ' redacted>'
    def __reduce_ex__(self, protocol): raise TypeError('Identity bindings cannot be serialized.')

    def assert_fresh(self, expected_binding_sha256=None):
        """Local lifetime/handle check; call recheck for new service observations."""
        with self._lock:
            if not self._valid or self._pid != os.getpid(): _fail('identity_binding_invalidated')
            self._provider._get(); self._backend._get()
            now = self._clock()
            if now >= self._expiry: _fail('identity_token_expired')
            if now < self._observed or now - self._observed > self._max_age: _fail('identity_binding_stale')
            if expected_binding_sha256 is not None and expected_binding_sha256 != self._binding_sha256: _fail('identity_binding_mismatch')

    def recheck(self):
        """Reacquire credentials and re-observe every binding; invalidate on error.

        Recheck can renew age/expiry, but cannot accept a different state or ETag.
        Credential revocation is detectable only once the authority rejects it.
        """
        with self._lock:
            if not self._valid or self._pid != os.getpid(): _fail('identity_binding_invalidated')
            try:
                facts, expiry = _Observer(self._config, self._provider, self._backend, self._transport, self._clock, self._timeout, self._total_timeout).observe()
                if facts != self._facts: _fail('identity_observation_changed')
                self._observed, self._expiry = self._clock(), expiry
                self.assert_fresh()
            except Exception:
                self._valid = False
                raise
            return self.evidence()

    def provider_environment(self):
        """Exactly pinned provider auth keys; caller must never persist/log this."""
        with self._lock:
            self.assert_fresh()
            return {'M365_TENANT_ID': self._config.provider.tenant_id,
                    'M365_CLIENT_ID': self._config.provider.client_id,
                    'M365_CLIENT_SECRET': self._provider._get(), 'M365_AUTH_METHOD': 'client_secret'}

    def backend_configuration(self, credential):
        """Protected-host access to immutable backend targets for this handle."""
        with self._lock:
            if type(credential) is not ClientSecretHandle or credential is not self._backend:
                _fail('identity_backend_handle_mismatch')
            self.assert_fresh()
            return self._config.backend_identity, self._config.backend

    def backend_storage_token(self, credential, *, timeout=10):
        """Acquire only the bound backend storage audience; no scope/URL input.

        Fractional timeouts let a lease caller include this exchange within its
        own remaining deadline. The returned token stays opaque and in memory.
        """
        with self._lock:
            if type(timeout) not in (int, float) or not 0 < timeout <= 30: _fail('identity_limits_invalid')
            identity, _ = self.backend_configuration(credential)
            observer = _Observer(self._config, self._provider, self._backend, self._transport,
                                 self._clock, min(self._timeout, timeout), timeout)
            token = observer.token(identity, credential, _STORAGE_SCOPE)
            self.assert_fresh()
            return BackendStorageToken(_BACKEND_TOKEN_SEAL, self, credential, token, observer.expiries[-1])

    def evidence(self):
        """Redacted report only; importing it cannot recreate the context."""
        with self._lock:
            self.assert_fresh()
            live = type(self) is LiveIdentityBinding
            return {'schema_version': 'explicit-identity-binding/1.0',
                    'assurance': 'live_fixed_service_observations' if live else 'laboratory_recorded_responses',
                    'laboratory': not live, 'execution_authorized': False,
                    'cloud': 'public', 'auth_method': 'client_secret',
                    'provider_authentication': 'tenant_specific_oauth_and_service_principal_self_read',
                    'backend_authentication': 'separate_graph_arm_storage_token_acquisition',
                    'binding_sha256': self._binding_sha256,
                    'configuration_sha256': digest(asdict(self._config)),
                    'observations': self._facts.copy(),
                    'permissions': 'only_observed_reads_established',
                    'unestablished': ['intune_mutation_permission', 'writer_ownership', 'operation_approval']}


class LiveIdentityBinding(BoundContext):
    """Created only after fixed real HTTPS observations have all succeeded."""
    __slots__ = ()


class LaboratoryIdentityBinding(BoundContext):
    """Explicit synthetic evidence; never admissible as live authority."""
    __slots__ = ()


class BackendStorageToken:
    """Opaque process-held backend credential; never persist or log `_get()`."""
    __slots__ = ('__binding', '__credential', '__token', '__expires', '__closed')

    def __init__(self, seal, binding, credential, token, expires):
        if seal is not _BACKEND_TOKEN_SEAL: _fail('identity_backend_token_unavailable')
        self.__binding, self.__credential, self.__token = binding, credential, token
        self.__expires, self.__closed = expires, False

    def _get(self):
        if self.__closed: _fail('identity_backend_token_unavailable')
        self.__binding.backend_configuration(self.__credential)
        if self.__binding._clock() >= self.__expires: _fail('identity_token_expired')
        return self.__token

    def close(self): self.__closed, self.__token = True, ''
    def __repr__(self): return '<BackendStorageToken redacted>'
    def __reduce_ex__(self, protocol): raise TypeError('Backend tokens cannot be serialized.')


def bind_live(config, *, provider_credential, backend_credential, timeout=10, max_age=60, total_timeout=60):
    """Protected host constructor; transport and clock are intentionally fixed."""
    _validate(config, provider_credential, backend_credential, timeout, max_age, total_timeout)
    transport, clock = _NativeTransport(), time.monotonic
    facts, expiry = _Observer(config, provider_credential, backend_credential, transport, clock, timeout, total_timeout).observe()
    return LiveIdentityBinding(_LIVE_SEAL, config, provider_credential, backend_credential, transport, clock, timeout, max_age, total_timeout, facts, expiry)


def bind_laboratory(config, *, provider_credential, backend_credential, transport, clock=time.monotonic, timeout=10, max_age=60, total_timeout=60):
    """Inject recorded responses here only; no path from this API to live type."""
    _validate(config, provider_credential, backend_credential, timeout, max_age, total_timeout)
    if not callable(transport) or not callable(clock): _fail('identity_laboratory_fixture_invalid')
    facts, expiry = _Observer(config, provider_credential, backend_credential, transport, clock, timeout, total_timeout).observe()
    return LaboratoryIdentityBinding(_LAB_SEAL, config, provider_credential, backend_credential, transport, clock, timeout, max_age, total_timeout, facts, expiry)


def require_live_binding(value):
    """Host guard rejects JSON, subclasses and all laboratory capabilities."""
    if type(value) is not LiveIdentityBinding: _fail('identity_live_binding_required')
    value.assert_fresh()
    return value
