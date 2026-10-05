"""Bounded Azure Blob lease mechanics with explicit host-held backend authority.

This module never authorizes Graph writes, restores state, breaks leases, creates
blobs, discovers credentials, or promotes a laboratory response to live authority.
An unknown acquire/renew/release is terminal for its local capability. Live Azure
qualification remains an external release gate.
"""
from __future__ import annotations

from dataclasses import asdict
from email.utils import formatdate
import http.client
import math
import os
import queue
import re
import socket
import threading
import time
from urllib.parse import quote
import uuid

from . import identity_binding as ib
from .io import AppError, digest

API_VERSION = '2023-11-03'
LEASE_SECONDS = 60
SAFETY_SECONDS = 2
RENEW_BEFORE_SECONDS = 30
MAX_RESPONSE_BYTES = 4096
_SEAL = object()
_NETWORK_SLOTS = threading.BoundedSemaphore(4)
_ETAG = re.compile(r'^"[!#-~]{1,128}"$')


def _fail(code):
    raise AppError(code, 'Exclusive backend blob ownership could not be established or retained.') from None


def _timeout(value):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= 10:
        _fail('lease_limits_invalid')
    return float(value)


class _LeaseTransport:
    """Fixed caller-generated HTTPS request; no URL, proxy, redirect or retry API.

    DNS is included in the caller deadline. A timed-out DNS worker may outlive
    the call, but holds one of four slots and checks cancellation before sending.
    A request already sent may succeed remotely after a local timeout.
    """
    def __call__(self, request, *, timeout, max_bytes):
        if not _NETWORK_SLOTS.acquire(blocking=False): _fail('lease_transport_busy')
        result, cancelled, active = queue.Queue(maxsize=1), threading.Event(), []
        connected_sockets = []

        def stop():
            cancelled.set()
            # Connection: close can detach conn.sock while the response file
            # still owns that socket. Interrupt the retained body reader too.
            for connected in connected_sockets:
                try: connected.shutdown(socket.SHUT_RDWR)
                except OSError: pass
            for connection in active:
                try:
                    if connection.sock is not None: connection.sock.shutdown(socket.SHUT_RDWR)
                except OSError: pass
                try: connection.close()
                except OSError: pass

        def worker():
            connection, response = None, None
            try:
                connection = http.client.HTTPSConnection(request.host, port=443,
                    timeout=timeout, context=ib._system_tls_context())
                active.append(connection)
                if cancelled.is_set(): return
                connection.connect()
                if connection.sock is not None: connected_sockets.append(connection.sock)
                # Cancellation may close the socket immediately before send.
                # HTTPConnection must not open a replacement and dispatch late.
                connection.auto_open = 0
                if cancelled.is_set(): return
                connection.request('PUT', request.path, body=b'', headers=request.headers)
                response = connection.getresponse()
                headers = tuple(response.getheaders())
                if len(headers) > 100 or sum(len(k)+len(v) for k,v in headers) > 16384:
                    _fail('lease_response_invalid')
                result.put(ib.ServiceResponse(response.status, headers, response.read(max_bytes+1)))
            except Exception:
                result.put(None)
            finally:
                try:
                    if response is not None: response.close()
                finally:
                    try:
                        if connection is not None: connection.close()
                    finally: _NETWORK_SLOTS.release()

        thread = threading.Thread(target=worker, daemon=True, name='azure-blob-lease')
        try:
            try: thread.start()
            except Exception:
                _NETWORK_SLOTS.release(); _fail('lease_transport_unavailable')
            response = result.get(timeout=timeout)
        except queue.Empty:
            stop(); _fail('lease_transport_deadline')
        except BaseException:
            stop(); raise
        if response is None: _fail('lease_transport_unavailable')
        return response


def _response(response, action, identifier, expected_etag):
    if (type(response) is not ib.ServiceResponse or type(response.status) is not int
            or type(response.body) is not bytes or len(response.body) > MAX_RESPONSE_BYTES
            or type(response.headers) is not tuple or len(response.headers) > 100):
        _fail('lease_response_invalid')
    headers = {}
    for item in response.headers:
        if type(item) is not tuple or len(item) != 2: _fail('lease_response_invalid')
        key, value = item
        if (type(key) is not str or not re.fullmatch(r'[A-Za-z0-9-]{1,128}', key)
                or type(value) is not str or len(value) > 4096
                or any(ord(c) < 32 or ord(c) > 126 for c in value)):
            _fail('lease_response_invalid')
        key = key.lower()
        if key in headers: _fail('lease_response_invalid')
        headers[key] = value
    if sum(len(k)+len(v) for k,v in headers.items()) > 16384: _fail('lease_response_invalid')
    if 300 <= response.status <= 399: _fail('lease_redirect_rejected')
    if response.status != (201 if action == 'acquire' else 200): _fail('lease_service_rejected')
    if response.body or headers.get('content-length', '0') != '0' or headers.get('content-encoding', 'identity').lower() not in ('', 'identity'):
        _fail('lease_response_invalid')
    if headers.get('x-ms-version') != API_VERSION: _fail('lease_service_version_mismatch')
    if action != 'release' and headers.get('x-ms-lease-id') != identifier:
        _fail('lease_response_identity_mismatch')
    if action == 'release' and headers.get('x-ms-lease-id', identifier) != identifier:
        _fail('lease_response_identity_mismatch')
    if expected_etag is not None and headers.get('etag') != expected_etag:
        _fail('lease_revision_changed')
    return headers


class BackendLeaseRole:
    """Explicit operator backend-role intent, not proof of an Azure RBAC grant.

    One acquisition attempt per role. Reconstructing evidence never recreates the
    role. A new factory call is a new explicit host action, never an automatic retry.
    """
    def __init__(self, seal, binding=None, credential=None, transport=None, clock=None, timeout=5, expected_etag=None):
        if seal is not _SEAL or type(self) not in (LiveBackendLeaseRole, LaboratoryBackendLeaseRole):
            _fail('lease_host_role_required')
        self._binding, self._credential, self._transport, self._clock = binding, credential, transport, clock
        self._timeout, self._etag = _timeout(timeout), expected_etag
        if expected_etag is not None and (type(expected_etag) is not str or not _ETAG.fullmatch(expected_etag)):
            _fail('lease_revision_invalid')
        identity, backend = binding.backend_configuration(credential)
        self._binding_sha256 = binding.evidence()['binding_sha256']
        self._scope = digest({'identity': asdict(identity), 'backend': asdict(backend)})
        self._host = backend.blob_endpoint.removeprefix('https://')
        self._path = '/' + quote(backend.container, safe='') + '/' + quote(backend.resolved_blob_name, safe='/') + '?comp=lease'
        self._pid, self._lock = os.getpid(), threading.RLock()
        self._last = float('-inf'); self._now()
        self._status, self._attempted = 'ready', False

    def __repr__(self): return '<' + type(self).__name__ + ' redacted>'
    def __reduce_ex__(self, protocol): raise TypeError('Backend lease roles cannot be serialized.')

    def _now(self):
        now = self._clock()
        if type(now) not in (int, float) or not math.isfinite(now) or now < self._last:
            _fail('lease_clock_invalid')
        self._last = now
        return now

    def _fresh(self):
        if self._pid != os.getpid(): _fail('lease_process_changed')
        self._binding.assert_fresh(self._binding_sha256)
        self._binding.backend_configuration(self._credential)

    def _request(self, action, identifier, *, previous_expiry=None):
        self._fresh()
        started = self._now(); deadline = started + self._timeout
        if previous_expiry is not None and started >= previous_expiry: _fail('lease_expired')
        if previous_expiry is not None: deadline = min(deadline, previous_expiry)
        token = self._binding.backend_storage_token(self._credential, timeout=deadline-started)
        try:
            now = self._now(); self._fresh()
            if now >= deadline or (previous_expiry is not None and now >= previous_expiry): _fail('lease_deadline')
            headers = {'Authorization': 'Bearer '+token._get(), 'Content-Length': '0',
                'Accept-Encoding': 'identity', 'x-ms-version': API_VERSION,
                'x-ms-date': formatdate(usegmt=True), 'x-ms-lease-action': action}
            if action == 'acquire':
                headers.update({'x-ms-proposed-lease-id': identifier, 'x-ms-lease-duration': str(LEASE_SECONDS)})
            else: headers['x-ms-lease-id'] = identifier
            if self._etag is not None: headers['If-Match'] = self._etag
            remaining = deadline-now
            if previous_expiry is not None: remaining = min(remaining, previous_expiry-now)
            response = self._transport(ib._Request('PUT', self._host, self._path, headers, b''),
                timeout=remaining, max_bytes=MAX_RESPONSE_BYTES)
            now = self._now(); self._fresh(); token._get()
            if now >= deadline or (previous_expiry is not None and now >= previous_expiry): _fail('lease_deadline')
            _response(response, action, identifier, self._etag)
            return started + LEASE_SECONDS - SAFETY_SECONDS
        finally: token.close()

    def acquire(self):
        with self._lock:
            if self._attempted: _fail('lease_acquisition_already_attempted')
            self._attempted = True; self._status = 'acquiring'
            identifier = str(uuid.uuid4())
            try:
                if str(uuid.UUID(identifier)) != identifier: _fail('lease_identifier_invalid')
                expires = self._request('acquire', identifier)
                self._status = 'held'
                kind = LiveBlobLease if type(self) is LiveBackendLeaseRole else LaboratoryBlobLease
                return kind(_SEAL, self, identifier, expires)
            except BaseException as exc:
                self._status = 'acquire_unknown'
                if not isinstance(exc, Exception): raise
                _fail('lease_acquire_unknown')

    def evidence(self):
        with self._lock:
            return {'schema_version': 'azure-blob-lease/1.0', 'status': self._status,
                'laboratory': type(self) is LaboratoryBackendLeaseRole, 'scope_sha256': self._scope,
                'identity_binding_sha256': self._binding_sha256, 'api_version': API_VERSION,
                'duration_seconds': LEASE_SECONDS, 'execution_authorized': False,
                'graph_fencing': False, 'live_lease_qualification': 'BLOCKED'}


class LiveBackendLeaseRole(BackendLeaseRole): pass
class LaboratoryBackendLeaseRole(BackendLeaseRole): pass


class BlobLease:
    """Process-held owner handle. check_active may renew; evidence is never authority."""
    def __init__(self, seal, role=None, identifier=None, expires=None):
        if seal is not _SEAL or type(self) not in (LiveBlobLease, LaboratoryBlobLease): _fail('lease_not_acquired')
        self._role, self._identifier, self._expires = role, identifier, expires
        self._status, self._entered, self._release_result = 'held', False, None

    def __repr__(self): return '<' + type(self).__name__ + ' redacted>'
    def __reduce_ex__(self, protocol): raise TypeError('Lease capabilities cannot be serialized.')

    def _active(self):
        if self._status != 'held': _fail('lease_not_active')
        self._role._fresh()
        if self._role._now() >= self._expires: _fail('lease_expired')

    def _lost(self):
        self._status, self._role._status = 'lost', 'lost'

    def check_active(self, expected_binding_sha256=None):
        with self._role._lock:
            try:
                self._active()
                if expected_binding_sha256 is not None and expected_binding_sha256 != self._role._binding_sha256:
                    _fail('lease_binding_mismatch')
                if self._expires - self._role._now() <= RENEW_BEFORE_SECONDS: self.renew()
                self._active()
            except BaseException:
                if self._status == 'held': self._lost()
                raise

    def renew(self):
        with self._role._lock:
            try:
                self._active()
                self._expires = self._role._request('renew', self._identifier, previous_expiry=self._expires)
                self._active()
            except BaseException as exc:
                if self._status == 'held': self._lost()
                if not isinstance(exc, Exception): raise
                _fail('lease_renew_unknown')

    def release(self):
        with self._role._lock:
            if self._release_result is not None: return dict(self._release_result)
            try:
                self._active()
                self._status = 'releasing'
                self._role._request('release', self._identifier, previous_expiry=self._expires)
                self._status = 'released'
            except BaseException:
                self._status = 'release_unknown'
            self._role._status = self._status
            self._release_result = self.evidence()
            return dict(self._release_result)

    def evidence(self):
        with self._role._lock:
            return dict(self._role.evidence(), status=self._status)

    def __enter__(self):
        with self._role._lock:
            if self._entered: _fail('lease_context_reused')
            self._entered = True; self.check_active(); return self

    def __exit__(self, exc_type, exc, traceback):
        result = self.release()
        if exc_type is None and result['status'] != 'released': _fail('lease_release_unknown')
        return False


class LiveBlobLease(BlobLease): pass
class LaboratoryBlobLease(BlobLease): pass


def backend_role_live(binding, *, credential, timeout=5, expected_etag=None):
    """Explicit operator authorization to attempt lease writes, no injected IO."""
    ib.require_live_binding(binding)
    return LiveBackendLeaseRole(_SEAL, binding, credential, _LeaseTransport(), time.monotonic, timeout, expected_etag)


def backend_role_laboratory(binding, *, credential, transport, clock=time.monotonic, timeout=5, expected_etag=None):
    """Only recorded fixture IO; the resulting type cannot satisfy live guards."""
    if type(binding) is not ib.LaboratoryIdentityBinding or not callable(transport) or not callable(clock):
        _fail('lease_laboratory_context_required')
    return LaboratoryBackendLeaseRole(_SEAL, binding, credential, transport, clock, timeout, expected_etag)


def require_live_lease(lease, binding):
    """A host watchdog can compose this check; it does not authorize Graph writes."""
    ib.require_live_binding(binding)
    if type(lease) is not LiveBlobLease or lease._role._binding is not binding:
        _fail('lease_live_capability_required')
    lease.check_active(binding.evidence()['binding_sha256'])
    return lease
