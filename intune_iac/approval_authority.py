"""Host-owned signed approvals, durable consumption and cooperative scope locks.

No imported document can create authority. The operator installs public keys and
an executable pin outside the reviewed repository, and retains the replay store
across releases/restarts. The issuer holds the private key in another security
domain. Python host compromise, trusted verifier/library compromise, or deletion
of the authority store is outside this control's boundary.

The laboratory factory can only authorize IP-network-denied execution. It never
authenticates a tenant or grants a live-service permission.
"""
from __future__ import annotations

import base64
import ctypes
from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import stat
import tempfile
import threading
import time
import uuid

from .io import AppError, canonical, digest, parse_json
from .protected import _path, _sha, _supervise, _sync

SIGNATURE_DOMAIN = b'intune-iac:operation-approval:v1\x00'
_SPKI = bytes.fromhex('302a300506032b6570032100')
_SEAL = object()
_HASH = re.compile(r'^[0-9a-f]{64}$')
_LABEL = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.:@-]{0,127}$')
_FIELDS = frozenset({'schema_version', 'issuer', 'key_id', 'approver_id', 'operation_id',
                     'request_sha256', 'issued_at', 'expires_at', 'nonce'})
_MODES = frozenset({'laboratory', 'native_provider_network_denied'})
_ACTIONS = frozenset({'provider_update', 'provider_no_change'})
_VALIDATORS = {}
_VALIDATOR_LOCK = threading.Lock()


def _fail(code):
    raise AppError(code, 'The independently signed operation approval could not be verified.')


def _snapshot(document):
    try:
        data = canonical(document)
        if len(data) > 65536: _fail('approval_document_limit')
        return parse_json(data)
    except (ValueError, TypeError, RecursionError, UnicodeError):
        _fail('approval_document_invalid')


def _operation(request):
    request = _snapshot(request)
    if type(request) is not dict or request.get('version') != 'provider-operation/1.0' or request.get('mode') not in _MODES or request.get('action') not in _ACTIONS or request.get('execution_authorized') is not False:
        _fail('approval_operation_not_supported')
    try:
        if str(uuid.UUID(request['operation_id'])) != request['operation_id']: _fail('approval_operation_id')
    except (KeyError, ValueError, AttributeError, TypeError): _fail('approval_operation_id')
    bindings = request.get('bindings')
    if type(bindings) is not dict or any(type(bindings.get(k)) is not str or not _HASH.fullmatch(bindings[k]) for k in ('scope_sha256', 'target_sha256', 'binary_plan_sha256')):
        _fail('approval_required_binding_missing')
    if type(request.get('laboratory')) is not bool or request['laboratory'] != (request['mode'] == 'laboratory'):
        _fail('approval_evidence_mode')
    if type(request.get('prepared_at')) is not int or request['prepared_at'] > int(time.time())+5:
        _fail('approval_preparation_time')
    return request


@dataclass(frozen=True)
class VerifierPin:
    executable: Path
    sha256: str
    validator_library: Path = Path('/usr/lib/x86_64-linux-gnu/libsodium.so.23.3.0')
    validator_sha256: str = 'fe00408090ea084504d7cb0130af56a22554fe299034b864551b65a64ca8a7b5'


@dataclass(frozen=True)
class TrustedApprover:
    issuer: str
    key_id: str
    approver_id: str
    public_key_hex: str
    permitted_modes: frozenset
    permitted_actions: frozenset


def _validator(verifier):
    # dlopen caches by pathname. A recycled /proc/self/fd/N pathname can refer
    # to a previously loaded, different library even after hashing the new FD.
    # Load only an exact private copy under a fresh, unique directory, then
    # cache the loaded handle by its verified content hash, never its FD name.
    with _VALIDATOR_LOCK:
        try:
            source = _path(verifier.validator_library)
            fd = os.open(source,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
            with os.fdopen(fd,'rb') as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 16*1024*1024:
                    _fail('approval_key_validator_pin')
                contents = stream.read(16*1024*1024+1)
            if len(contents) > 16*1024*1024 or hashlib.sha256(contents).hexdigest() != verifier.validator_sha256:
                _fail('approval_key_validator_pin')
            if verifier.validator_sha256 in _VALIDATORS: return _VALIDATORS[verifier.validator_sha256]
            if len(_VALIDATORS) >= 8: _fail('approval_key_validator_capacity')
            with tempfile.TemporaryDirectory(prefix='intune-key-validator-',dir='/tmp') as directory:
                copy = Path(directory)/'validator.so'
                descriptor = os.open(copy,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o500)
                with os.fdopen(descriptor,'wb') as output: output.write(contents)
                library = ctypes.CDLL(str(copy))
            # Resolve all required exports before caching an admitted image.
            library.crypto_core_ed25519_is_valid_point.argtypes = [ctypes.c_char_p]
            library.crypto_core_ed25519_is_valid_point.restype = ctypes.c_int
            library.crypto_scalarmult_ed25519_noclamp.argtypes = [ctypes.c_void_p,ctypes.c_char_p,ctypes.c_char_p]
            library.crypto_scalarmult_ed25519_noclamp.restype = ctypes.c_int
            library.crypto_core_ed25519_add.argtypes = [ctypes.c_void_p,ctypes.c_char_p,ctypes.c_char_p]
            library.crypto_core_ed25519_add.restype = ctypes.c_int
            _VALIDATORS[verifier.validator_sha256] = library
            return library
        except (OSError, AttributeError): _fail('approval_key_validator_unavailable')


def _valid_public_key(verifier, key):
    """Reject invalid, weak and mixed-order Ed25519 points using libsodium.

    Native dependency is explicitly pinned, not discovered via LD_LIBRARY_PATH.
    The L-1/add subgroup check follows libsodium's published workaround for
    versions <=1.0.20; is_valid_point alone is insufficient on those versions.
    No signature or curve arithmetic is implemented in Python.
    """
    library = _validator(verifier)
    if library.crypto_core_ed25519_is_valid_point(key) != 1: _fail('approval_weak_public_key')
    order_minus_one = bytes.fromhex('ecd3f55c1a631258d69cf7a2def9de1400000000000000000000000000000010')
    product = ctypes.create_string_buffer(32); total = ctypes.create_string_buffer(32)
    if library.crypto_scalarmult_ed25519_noclamp(product,order_minus_one,key) != 0 or library.crypto_core_ed25519_add(total,product.raw,key) != 0 or total.raw != b'\x01'+bytes(31):
        _fail('approval_weak_public_key')


class BoundExecutionGuard:
    """A process-held check created by trusted host code, never a JSON claim."""
    def __init__(self, seal, request, recheck):
        if seal is not _SEAL or not callable(recheck): _fail('approval_host_guard_required')
        self._request_sha256 = digest(request)
        self._mode = request['mode']
        self._scope = request['bindings']['scope_sha256']
        self._recheck = recheck

    def _check(self, request):
        if digest(request) != self._request_sha256 or request['mode'] != self._mode:
            _fail('approval_guard_binding')
        # A check signals success only by returning None. A mistaken predicate
        # returning False must never become authorization by being ignored.
        if self._recheck() is not None: _fail('approval_guard_contract')


def make_laboratory_guard(request, recheck):
    """Trusted host API for local fixtures; no credential/live authorization.

    `recheck` is executable host policy, not model-supplied code. Host adapters
    must recheck the admitted plan/state/tools and enforce network denial.
    """
    request = _operation(request)
    return BoundExecutionGuard(_SEAL, request, recheck)


def _private(path, *, directory=False):
    path = _path(path)
    info = path.stat()
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077 or (not directory and info.st_nlink != 1):
        _fail('approval_store_not_private')
    return path


@contextmanager
def _connection(authority):
    _private(authority.root, directory=True)
    _private(authority.database)
    for suffix in ('-journal', '-wal', '-shm'):
        other = Path(str(authority.database)+suffix)
        if other.exists() or other.is_symlink(): _private(other)
    connection = sqlite3.connect(authority.database, timeout=0, isolation_level=None)
    try:
        connection.execute('PRAGMA synchronous=FULL')
        connection.execute('PRAGMA journal_mode=DELETE')
        connection.execute('PRAGMA trusted_schema=OFF')
        yield connection
    finally:
        connection.close()


def _consume(authority, payload, request_sha256):
    try:
        with _connection(authority) as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM revoked WHERE issuer=? AND key_id=?', (payload['issuer'], payload['key_id'])).fetchone():
                _fail('approval_key_revoked')
            if db.execute('SELECT count(*) FROM consumed').fetchone()[0] >= 100000:
                _fail('approval_store_capacity')
            db.execute('INSERT INTO consumed VALUES (?,?,?,?,?,?)',
                       (payload['issuer'], payload['nonce'], payload['operation_id'], request_sha256, int(time.time()), 'consumed'))
            db.execute('COMMIT')
        _sync(authority.root)
    except sqlite3.IntegrityError: _fail('approval_already_consumed')
    except (sqlite3.Error, OSError): _fail('approval_consumption_not_durable')


class ApprovalAuthority:
    """Operator-owned policy and store; none of these inputs come from the plan."""
    def __init__(self, root, verifier, approvers):
        if type(verifier) is not VerifierPin or type(verifier.sha256) is not str or not _HASH.fullmatch(verifier.sha256):
            _fail('approval_verifier_pin')
        if type(verifier.validator_sha256) is not str or not _HASH.fullmatch(verifier.validator_sha256):
            _fail('approval_key_validator_pin')
        self.verifier = VerifierPin(_path(verifier.executable), verifier.sha256,
                                    _path(verifier.validator_library),verifier.validator_sha256)
        if _sha(self.verifier.executable) != verifier.sha256: _fail('approval_verifier_pin')
        self.approvers = {}
        for entry in approvers:
            if type(entry) is not TrustedApprover or any(type(v) is not str or not _LABEL.fullmatch(v) for v in (entry.issuer, entry.key_id, entry.approver_id)) or type(entry.public_key_hex) is not str or not _HASH.fullmatch(entry.public_key_hex):
                _fail('approval_trust_policy')
            if type(entry.permitted_modes) is not frozenset or not entry.permitted_modes or not entry.permitted_modes <= _MODES or type(entry.permitted_actions) is not frozenset or not entry.permitted_actions or not entry.permitted_actions <= _ACTIONS:
                _fail('approval_trust_policy')
            _valid_public_key(self.verifier, bytes.fromhex(entry.public_key_hex))
            key = (entry.issuer, entry.key_id)
            if key in self.approvers: _fail('approval_duplicate_key')
            self.approvers[key] = entry
        if not self.approvers: _fail('approval_trust_policy')
        self.root = _path(root)
        self.root.mkdir(mode=0o700, exist_ok=True)
        _private(self.root, directory=True)
        self.database = self.root/'consumption.sqlite3'
        try:
            fd = os.open(self.database, os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW, 0o600)
            os.fsync(fd); os.close(fd); _sync(self.root)
        except FileExistsError: pass
        try:
            with _connection(self) as db:
                db.execute('BEGIN IMMEDIATE')
                db.execute('CREATE TABLE IF NOT EXISTS consumed (issuer TEXT NOT NULL, nonce TEXT NOT NULL, operation_id TEXT NOT NULL UNIQUE, request_sha256 TEXT NOT NULL, consumed_at INTEGER NOT NULL, status TEXT NOT NULL, PRIMARY KEY(issuer,nonce))')
                db.execute('CREATE TABLE IF NOT EXISTS revoked (issuer TEXT NOT NULL, key_id TEXT NOT NULL, PRIMARY KEY(issuer,key_id))')
                db.execute('CREATE TABLE IF NOT EXISTS executions (operation_id TEXT PRIMARY KEY, request_sha256 TEXT NOT NULL, dispatched_at INTEGER NOT NULL, outcome_sha256 TEXT)')
                db.execute('COMMIT')
            _sync(self.root)
        except (sqlite3.Error, OSError): _fail('approval_store_unavailable')

    def revoke_key(self, issuer, key_id):
        """Administrative host action; persistent and effective for active permits."""
        if (issuer, key_id) not in self.approvers: _fail('approval_unknown_key')
        try:
            with _connection(self) as db:
                db.execute('BEGIN IMMEDIATE')
                db.execute('INSERT OR IGNORE INTO revoked VALUES (?,?)', (issuer,key_id))
                db.execute('COMMIT')
            _sync(self.root)
        except (sqlite3.Error, OSError): _fail('approval_revocation_not_durable')

    def assert_consumed(self, request):
        """Read-only approval provenance; not evidence that the plan executed."""
        request = _operation(request)
        try:
            with _connection(self) as db:
                row = db.execute('SELECT request_sha256 FROM consumed WHERE operation_id=?', (request['operation_id'],)).fetchone()
            if row != (digest(request),): _fail('approval_consumption_missing')
        except (sqlite3.Error, OSError): _fail('approval_store_unavailable')

    def assert_outcome(self, request, report):
        """Match an untrusted local report to the privileged outcome record."""
        self.assert_consumed(request)
        try:
            with _connection(self) as db:
                row = db.execute('SELECT request_sha256,outcome_sha256 FROM executions WHERE operation_id=?', (request['operation_id'],)).fetchone()
            if row != (digest(request),digest(_snapshot(report))): _fail('approval_outcome_not_attested')
        except (sqlite3.Error, OSError): _fail('approval_store_unavailable')

    def _not_revoked(self, payload):
        try:
            with _connection(self) as db:
                if db.execute('SELECT 1 FROM revoked WHERE issuer=? AND key_id=?', (payload['issuer'],payload['key_id'])).fetchone():
                    _fail('approval_key_revoked')
        except (sqlite3.Error, OSError): _fail('approval_store_unavailable')

    def authorize(self, request, signed_receipt, *, guard):
        request = _operation(request); signed_receipt = _snapshot(signed_receipt)
        if type(guard) is not BoundExecutionGuard or guard._request_sha256 != digest(request):
            _fail('approval_host_guard_required')
        if type(signed_receipt) is not dict or set(signed_receipt) != {'payload','signature'}:
            _fail('approval_receipt_shape')
        payload = signed_receipt['payload']
        if type(payload) is not dict or set(payload) != _FIELDS or payload['schema_version'] != 'signed-operation-approval/1.0':
            _fail('approval_receipt_shape')
        if any(type(payload[k]) is not str or not _LABEL.fullmatch(payload[k]) for k in ('issuer','key_id','approver_id')):
            _fail('approval_receipt_identity')
        if payload['operation_id'] != request['operation_id'] or payload['request_sha256'] != digest(request) or type(payload['nonce']) is not str or not re.fullmatch(r'[0-9a-f]{32}', payload['nonce']):
            _fail('approval_receipt_binding')
        now = int(time.time())
        if type(payload['issued_at']) is not int or type(payload['expires_at']) is not int or not request['prepared_at'] <= payload['issued_at'] <= now+5 or not now < payload['expires_at'] <= payload['issued_at']+900:
            _fail('approval_receipt_time')
        approver = self.approvers.get((payload['issuer'],payload['key_id']))
        if not approver or approver.approver_id != payload['approver_id'] or request['mode'] not in approver.permitted_modes or request['action'] not in approver.permitted_actions:
            _fail('approval_signer_not_authorized')
        if type(signed_receipt['signature']) is not str or len(signed_receipt['signature']) != 88:
            _fail('approval_invalid_signature')
        try: signature = base64.b64decode(signed_receipt['signature'], validate=True)
        except (ValueError, TypeError): _fail('approval_invalid_signature')
        if len(signature) != 64 or base64.b64encode(signature).decode() != signed_receipt['signature']:
            _fail('approval_invalid_signature')
        self._not_revoked(payload)
        self._verify(approver, payload, signature)
        return ApprovedExecution(_SEAL, self, request, payload, guard)

    def _verify(self, approver, payload, signature):
        fd = os.open(_path(self.verifier.executable), os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        try:
            with os.fdopen(os.dup(fd), 'rb') as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode) or hashlib.file_digest(stream, 'sha256').hexdigest() != self.verifier.sha256:
                    _fail('approval_verifier_changed')
            with tempfile.TemporaryDirectory(prefix='verify-', dir=self.root) as name:
                root = Path(name)
                for path, data in ((root/'key.der', _SPKI+bytes.fromhex(approver.public_key_hex)),
                                   (root/'message', SIGNATURE_DOMAIN+canonical(payload)), (root/'signature',signature)):
                    descriptor = os.open(path, os.O_CREAT|os.O_EXCL|os.O_WRONLY, 0o600)
                    with os.fdopen(descriptor,'wb') as stream: stream.write(data)
                try:
                    _supervise([str(self.verifier.executable),'pkeyutl','-verify','-pubin','-keyform','DER',
                                '-inkey',str(root/'key.der'),'-rawin','-in',str(root/'message'),'-sigfile',str(root/'signature')],
                               cwd=root, env={'PATH':'/usr/bin:/bin','HOME':str(root),'OPENSSL_CONF':'/dev/null'},
                               pass_fds=(fd,), executable='/proc/self/fd/'+str(fd), timeout=5, output_limit=4096)
                except AppError: _fail('approval_invalid_signature')
        finally: os.close(fd)


class ExecutionPermit:
    def __init__(self, seal, authorization):
        if seal is not _SEAL or type(authorization) is not ApprovedExecution: _fail('approval_permit_not_minted')
        self._authorization = authorization
        self.request_sha256 = digest(authorization._request)
        self.mode = authorization._request['mode']

    def check_active(self):
        auth = self._authorization
        if not auth._active or auth._lock is None: _fail('approval_permit_inactive')
        auth._check()

    def mark_dispatch(self):
        """Durable host marker before child dispatch; an attempt, not success."""
        self.check_active()
        auth = self._authorization
        auth._authority.assert_consumed(auth._request)
        try:
            with _connection(auth._authority) as db:
                db.execute('BEGIN IMMEDIATE')
                db.execute('INSERT INTO executions VALUES (?,?,?,NULL)',
                           (auth._request['operation_id'],self.request_sha256,int(time.time())))
                db.execute('COMMIT')
            _sync(auth._authority.root)
        except sqlite3.IntegrityError: _fail('approval_dispatch_already_attempted')
        except (sqlite3.Error, OSError): _fail('approval_dispatch_not_durable')

    def record_outcome(self, report):
        """Persist the host-observed report independently of writable journals.

        Recording after expiry is allowed while the context still exists: this
        never grants new dispatch authority and must preserve uncertain results.
        """
        auth = self._authorization
        if not auth._active or auth._lock is None: _fail('approval_permit_inactive')
        report = _snapshot(report)
        if type(report) is not dict or report.get('operation_id') != auth._request['operation_id']:
            _fail('approval_outcome_binding')
        try:
            with _connection(auth._authority) as db:
                db.execute('BEGIN IMMEDIATE')
                row = db.execute('SELECT request_sha256,outcome_sha256 FROM executions WHERE operation_id=?', (auth._request['operation_id'],)).fetchone()
                if row != (self.request_sha256,None): _fail('approval_outcome_not_recordable')
                db.execute('UPDATE executions SET outcome_sha256=? WHERE operation_id=?', (digest(report),auth._request['operation_id']))
                db.execute('COMMIT')
            _sync(auth._authority.root)
        except (sqlite3.Error, OSError): _fail('approval_outcome_not_durable')


class ApprovedExecution:
    def __init__(self, seal, authority=None, request=None, payload=None, guard=None):
        if seal is not _SEAL: _fail('approval_not_verified')
        self._authority = authority; self._request = request; self._payload = payload; self._guard = guard
        self._deadline = time.monotonic()+max(0,payload['expires_at']-time.time())
        self._entered = False; self._active = False; self._lock = None

    def _check(self):
        if time.time() >= self._payload['expires_at'] or time.monotonic() >= self._deadline:
            _fail('approval_expired')
        self._authority._not_revoked(self._payload)
        self._guard._check(self._request)
        # A bounded service/lease recheck still consumes time and another
        # process can revoke a signer during that call. Recheck both after it.
        if time.time() >= self._payload['expires_at'] or time.monotonic() >= self._deadline:
            _fail('approval_expired')
        self._authority._not_revoked(self._payload)

    def __enter__(self):
        if self._entered: _fail('approval_context_reused')
        self._entered = True
        try:
            _private(self._authority.root, directory=True)
            path = self._authority.root/('scope-'+self._guard._scope+'.lock')
            fd = os.open(path, os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW|os.O_NONBLOCK, 0o600)
            self._lock = fd; _private(path)
            try: fcntl.flock(fd, fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError: _fail('approval_scope_busy')
            self._check()
            _consume(self._authority,self._payload,digest(self._request))
            self._active = True
            return ExecutionPermit(_SEAL,self)
        except BaseException:
            if self._lock is not None: os.close(self._lock); self._lock = None
            raise

    def __exit__(self, exc_type, exc, traceback):
        self._active = False
        try:
            # A consumed approval stays spent even when this optional outcome
            # update fails. It is never made reusable by a recovery operation.
            with _connection(self._authority) as db:
                db.execute('BEGIN IMMEDIATE')
                db.execute('UPDATE consumed SET status=? WHERE operation_id=?',
                           ('scope_exited' if exc_type is None else 'interrupted',self._payload['operation_id']))
                db.execute('COMMIT')
        except (sqlite3.Error, OSError): _fail('approval_receipt_write_failed')
        finally:
            if self._lock is not None: os.close(self._lock); self._lock = None
        return False
