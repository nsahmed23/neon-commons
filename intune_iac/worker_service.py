"""Signed service controller over the existing native host and HTTPS broker.

Prepared JSON is review material, never a live identity/run/storage capability.
This domain is deliberately separate from network-denied laboratory approvals.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
from dataclasses import asdict
import hashlib
import os
from pathlib import Path
import re
import signal
import sqlite3
import stat
import tempfile
import threading
import time
import uuid

from . import approval_authority as aa, blob_lease, clock, identity_binding as ib
from . import protected, validity, worker_broker as broker, worker_host as host
from .io import AppError, canonical, digest, load_json, parse_json
from .provider_journey import _outside_repository, _private, _absolute

VERSION = 'worker-service-operation/1'
INTENT_VERSION = 'worker-service-operation/2'
SIGNATURE_DOMAIN = b'intune-workbench:worker-service-approval:v1\x00'
_SEAL = object()
_HASH = re.compile(r'[0-9a-f]{64}')
_UUID = re.compile(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}')
_PROFILES = {'native_docker_laboratory_tls', 'native_docker_laboratory_protocol', 'azure_public_pilot'}
_IMPLEMENTATION = ('worker_service.py', 'worker_host.py', 'worker_broker.py', 'worker_provider.py',
                   'identity_binding.py', 'blob_lease.py', 'azure_backend.py', 'approval_authority.py',
                   'protected.py', 'provider_execution.py', 'worker_precondition.py', 'observation_reader.py', 'io.py')


def _fail(code):
    raise AppError(code, 'The signed service operation, host protection or recovery contract was not established.')


MAX_EXPIRED = validity.MAX_EXPIRED
_EXPIRED_TABLE = 'service_expired'
# The recovery approvals of the original job (lease, committed-state, adoption and adoption-plan lease recovery) are
# judged on this store too; their expiry records live in their own table so a family can never latch another.
RECOVERY_EXPIRED_TABLE = 'recovery_expired'


def _critical(policy, payload, request_sha256, deadline=None, *, table=_EXPIRED_TABLE, fail=None,
              expired_code='service_signature_expired', domain=None):
    """The shared validity critical section (intune_iac.validity) on this service policy's own store: its authority
    root, its database and an expiry table. The final window judgment, the recorded time, the expiry record and the
    caller's commit are one step. The payload must come from a receipt that authenticated: an expiry row is written
    for it. A reached expiry is refused here with expired_code (the caller's own time refusal); a backward step is
    held. Lock order: the store directory, the recorded-time lock, then the SQLite write transaction."""
    store = validity.Store(policy.root, policy.connection, table, fail or _fail, capacity=MAX_EXPIRED,
        capacity_code='service_store_capacity', private_code='service_store_not_private', create=True,
        domain=domain or SIGNATURE_DOMAIN.rstrip(b'\x00').decode())
    return validity.critical(store, payload, request_sha256, deadline, expired_code)


def _deadline(payload, policy):
    """This process's monotonic deadline for the receipt, carried with the permit so a stuck wall clock cannot extend it. It is
    armed from the store's effective time (the recorded floor carried by the boot time elapsed), not the bare wall clock: a
    wall clock set back, in this process or before it started, cannot give the receipt more time than the floor says is left."""
    return validity.deadline(policy.root, payload['expires_at'])


def _latched(db, payload, request_sha256, domain=None, table=_EXPIRED_TABLE):
    """Whether an expiry record exists for the receipt: plain reads, no write. A store made before the table existed
    has no record, and gets the table the first time a section runs."""
    return validity.latched(db, table, domain or SIGNATURE_DOMAIN.rstrip(b'\x00').decode(), payload, request_sha256)


def _watch(policy, payload, request_sha256, deadline, latched, *, fail, expired_code, table=_EXPIRED_TABLE, domain=None):
    """The window judgment for a periodic check (the watchdog runs it every 0.2 s): read-only on the open path, so a
    cancel or recover from another process is never refused because a permit is polling. A closed window is recorded
    through the shared critical section and refused; if the store is busy it is refused anyway and recorded on a later
    call. A backward step is held. Its result grants no authority: only the critical section does."""
    state, reading = validity.peek(policy.root, payload['expires_at'], deadline, latched)
    if state == validity.CLOSED:
        _record_expiry(policy, payload, request_sha256, deadline, table=table, fail=fail, expired_code=expired_code, domain=domain)
        fail(expired_code)
    if state == validity.HELD: raise validity.hold(reading)


def _record_expiry(policy, payload, request_sha256, deadline=None, *, table=_EXPIRED_TABLE, fail=None,
                   expired_code='service_signature_expired', domain=None):
    """Record a reached expiry of an authenticated receipt before the caller refuses for the manifest's own window.

    The manifest window is judged on the bare clock ahead of everything else, and the receipt expires no later than the
    manifest, so refusing there without recording would let a clock rollback reopen the receipt. Whatever this section
    refuses is the same closed window the caller is about to report in its original error, so it is not reported twice.
    A backward step is different: validity cannot be established, so the hold, which says how to recover, is reported."""
    try:
        with _critical(policy, payload, request_sha256, deadline, table=table, fail=fail, expired_code=expired_code, domain=domain): pass
    except AppError as error:
        if error.code == validity.HELD: raise
    except OSError: pass


def _record_expiry_of(job, receipt):
    """_record_expiry for a receipt this process has not authenticated yet: verify authenticates it, then judges and
    records the window. A receipt that does not authenticate records nothing. A hold is reported, not swallowed."""
    try: job.policy.verify(job.manifest, receipt)
    except AppError as error:
        if error.code == validity.HELD: raise
    except OSError: pass


def _expiry_may_be_reached(root, payload):
    """Read-only: whether the wall clock or the recorded time is at or past the receipt's expiry. It takes no lock, writes
    nothing and leaves this process's anchor alone, so it can be asked of a receipt that is not valid yet."""
    return validity.effective_now(root) >= payload['expires_at']


def _record_recovery_expiry(store, recovery_policy, manifest, signed, *, fail, expired_code, domain):
    """Record the reached expiry of a recovery approval whose verification just refused it on the bare clock.

    The verification of a recovery approval (lease, committed-state, adoption and adoption-plan lease recovery) judges
    the window on the bare wall clock ahead of everything else, and the original job's store is the only durable home
    these approvals have. The receipt is authenticated again with the clock pinned to its own issue time, so that only
    the window is left out; if it authenticates, its window is judged in the shared section and a reached expiry is
    recorded. A receipt that does not authenticate records nothing, so such input cannot grow the store or move the
    recorded time. Whatever this section refuses is the same closed window the caller is about to report.

    The writing section is entered only when the expiry may actually have been reached (by the wall clock or the recorded
    time): an authentic receipt that is merely dated ahead of this clock moves nothing. Otherwise a backward step is
    reported as the hold it is, with the recovery words, instead of the bare-clock refusal that hid it."""
    try:
        payload = recovery_policy._verified(manifest, signed, signed['payload']['issued_at'])
    except (AppError, OSError, KeyError, TypeError): return
    if _expiry_may_be_reached(store.root, payload):
        _record_expiry(store, payload, digest(manifest), None, table=RECOVERY_EXPIRED_TABLE, fail=fail,
                       expired_code=expired_code, domain=domain)
    else:
        validity.hold_if_clock_behind(store.root)


def _window_open(store, payload, manifest_sha256, deadline, *, fail, expired_code, domain):
    """The recovery approval's window judged once more, read-only, after its dispatch reservation committed and before
    the lease request is sent: the refusal the bare-clock check used to make there, now on the recorded time and this
    process's monotonic deadline (see _watch). It can only refuse; the reservation section is what authorizes."""
    with store.connection() as db:
        latched = _latched(db, payload, manifest_sha256, domain, RECOVERY_EXPIRED_TABLE)
    _watch(store, payload, manifest_sha256, deadline, latched, fail=fail, expired_code=expired_code,
           table=RECOVERY_EXPIRED_TABLE, domain=domain)


_AUTHORIZATIONS = 'service_authorizations'
_AUTHORIZATIONS_SQL = ('CREATE TABLE IF NOT EXISTS ' + _AUTHORIZATIONS + ' (operation_id TEXT NOT NULL, phase TEXT NOT NULL, '
    'authorizations INTEGER NOT NULL, last_authorized_at INTEGER NOT NULL, PRIMARY KEY(operation_id, phase))')


def _mark_authorized(db, operation_id, phase):
    """The per-request dispatch marker of the authorization check, committed inside the critical section before the
    check returns, so a broker request is never released without a durable record that it was authorized."""
    db.execute(_AUTHORIZATIONS_SQL)
    db.execute('INSERT INTO ' + _AUTHORIZATIONS + ' VALUES (?,?,1,?) ON CONFLICT(operation_id, phase) DO UPDATE SET '
        'authorizations = authorizations + 1, last_authorized_at = excluded.last_authorized_at',
        (operation_id, phase, int(time.time())))
    db.execute('COMMIT')


def implementation_binding():
    from .worker_runtime_identity import inventory
    return inventory()


def _bounded_private_json(path):
    path = _private(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not 0 < info.st_size <= 256 * 1024: _fail('service_document_limit')
        raw = stream.read(256 * 1024 + 1)
    if len(raw) > 256 * 1024: _fail('service_document_limit')
    return parse_json(raw)


def _run_context(value):
    if type(value) is not dict: _fail('service_run_context_invalid')
    if value.get('schema_version') == 'service-host-qualification-context/1':
        if (set(value) != {'schema_version', 'fixture_run', 'ci_authenticated'} or
                type(value['fixture_run']) is not str or not aa._LABEL.fullmatch(value['fixture_run']) or
                value['ci_authenticated'] is not False): _fail('service_run_context_invalid')
        return value
    fields = {'schema_version', 'repository', 'source_revision', 'source_sha256', 'workflow_revision',
        'verifier_revision', 'run_id', 'run_attempt', 'protected_ref', 'effective_inputs_sha256',
        'provider_lock_sha256', 'stack', 'component'}
    if set(value) != fields or value['schema_version'] != 'service-run-context/1': _fail('service_run_context_invalid')
    if (type(value['repository']) is not str or not re.fullmatch(r'https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', value['repository'])
            or type(value['run_id']) is not str or not aa._LABEL.fullmatch(value['run_id'])
            or type(value['run_attempt']) is not int or not 1 <= value['run_attempt'] <= 1000
            or type(value['protected_ref']) is not str or not re.fullmatch(r'refs/(heads|tags)/[A-Za-z0-9][A-Za-z0-9_./-]{0,255}', value['protected_ref'])
            or '..' in value['protected_ref'] or value['stack'] != 'worker' or value['component'] != 'intune-policy'):
        _fail('service_run_context_invalid')
    for key in ('source_revision', 'workflow_revision', 'verifier_revision'):
        if type(value[key]) is not str or not re.fullmatch(r'[0-9a-f]{40}', value[key]): _fail('service_run_context_invalid')
    for key in ('source_sha256', 'effective_inputs_sha256', 'provider_lock_sha256'): _hash(value[key])
    return value


def _controller_identity(pid):
    try:
        value = Path('/proc/' + str(pid) + '/stat').read_text()
        started = value[value.rfind(')') + 2:].split()[19]
        return Path('/proc/sys/kernel/random/boot_id').read_text().strip() + ':' + started
    except (OSError, IndexError, ValueError):
        return None


def _hash(value):
    if type(value) is not str or not _HASH.fullmatch(value): _fail('service_hash_invalid')
    return value


def _snapshot(value):
    raw = canonical(value)
    if len(raw) > 256 * 1024: _fail('service_manifest_limit')
    return parse_json(raw)


def _host_spec(value):
    try:
        value = dict(value)
        value['tools'] = tuple(host.PinnedTool(**tool) for tool in value['tools'])
        return host.HostSpec(**value)
    except (KeyError, TypeError, ValueError): _fail('service_host_spec_invalid')


def validate_manifest(value, *, require_implementation=True):
    value = _snapshot(value)
    fields = {'schema_version', 'operation_id', 'profile', 'prepared_at', 'expires_at', 'action',
        'execution_binding_sha256', 'host_spec', 'broker_policy', 'state_contracts', 'saved_plan_sha256',
        'identity_binding_sha256', 'run_binding_sha256', 'storage_binding_sha256', 'provider_binding',
        'tenant_id', 'object_ids', 'backend_scope_sha256', 'implementation_files', 'precondition_binding', 'run_context'}
    version = value.get('schema_version') if type(value) is dict else None
    if version == INTENT_VERSION: fields.add('source_authoring_binding')
    if type(value) is not dict or set(value) != fields or version not in (VERSION, INTENT_VERSION):
        _fail('service_manifest_invalid')
    if (type(value['operation_id']) is not str or not _UUID.fullmatch(value['operation_id'])
            or value['profile'] not in _PROFILES or value['action'] not in ('apply_saved_plan', 'host_qualification')
            or value['profile'] == 'azure_public_pilot' and value['action'] != 'apply_saved_plan'):
        _fail('service_profile_invalid')
    now = int(time.time())
    if (type(value['prepared_at']) is not int or type(value['expires_at']) is not int
            or not value['prepared_at'] <= now + 5 < value['expires_at'] <= value['prepared_at'] + 900):
        _fail('service_manifest_expired')
    for key in ('execution_binding_sha256', 'run_binding_sha256', 'storage_binding_sha256', 'backend_scope_sha256'):
        _hash(value[key])
    if value['identity_binding_sha256'] is not None: _hash(value['identity_binding_sha256'])
    if value['profile'] == 'azure_public_pilot' and value['identity_binding_sha256'] is None:
        _fail('service_identity_required')
    if value['saved_plan_sha256'] is not None: _hash(value['saved_plan_sha256'])
    if value['action'] == 'apply_saved_plan' and value['saved_plan_sha256'] is None:
        _fail('service_saved_plan_required')
    if (type(value['tenant_id']) is not str or not _UUID.fullmatch(value['tenant_id'])
            or type(value['object_ids']) is not list or not 1 <= len(value['object_ids']) <= 100
            or any(type(item) is not str or not _UUID.fullmatch(item) for item in value['object_ids'])
            or len(set(value['object_ids'])) != len(value['object_ids'])):
        _fail('service_scope_invalid')
    if type(value['provider_binding']) is not dict or type(value['state_contracts']) is not dict:
        _fail('service_binding_invalid')
    context = _run_context(value['run_context'])
    if digest(context) != value['run_binding_sha256']: _fail('service_run_context_binding')
    if value['action'] != 'host_qualification':
        native = value['provider_binding']
        if (context['schema_version'] != 'service-run-context/1' or
                any(context[key] != native.get(other) for key, other in [('source_revision', 'source_revision'),
                    ('source_sha256', 'source_sha256'), ('effective_inputs_sha256', 'effective_input_sha256'),
                    ('provider_lock_sha256', 'lockfile_sha256')])): _fail('service_run_context_binding')
    if version == INTENT_VERSION:
        if value['action'] != 'apply_saved_plan' or value['profile'] == 'native_docker_laboratory_tls':
            _fail('service_source_intent_profile')
        from .worker_source_intent import validate_operation_binding
        validate_operation_binding(value['source_authoring_binding'], provider_binding=value['provider_binding'],
            run_context=context, tenant_id=value['tenant_id'], object_ids=value['object_ids'],
            backend_scope_sha256=value['backend_scope_sha256'])
    spec = _host_spec(value['host_spec'])
    policy = broker.validate_policy(value['broker_policy'])
    expected_profile = {'azure_public_pilot': 'azure_public_pilot',
        'native_docker_laboratory_protocol': 'laboratory_native_protocol',
        'native_docker_laboratory_tls': 'laboratory_tls_fixture'}[value['profile']]
    if (policy['profile'] != expected_profile or policy['operation_id'] != value['operation_id']
            or policy['execution_binding_sha256'] != value['execution_binding_sha256']
            or policy['expires_at'] != value['expires_at'] or policy['worker_uid'] != spec.uid
            or spec.broker_root is None or spec.broker_ca_sha256 is None):
        _fail('service_broker_binding')
    state_routes = {route['id']: route['state_contract_sha256'] for route in policy['routes'] if route['effect'] == 'state_write'}
    if {key: digest(item) for key, item in value['state_contracts'].items()} != state_routes:
        _fail('service_state_contract_binding')
    inventory = value['implementation_files']
    if (type(inventory) is not dict or not 1 <= len(inventory) <= 4096 or
            any(type(key) is not str or not 1 <= len(key) <= 4096 or type(item) is not str or not _HASH.fullmatch(item)
                for key, item in inventory.items())): _fail('service_implementation_invalid')
    if require_implementation and inventory != implementation_binding(): _fail('service_implementation_changed')
    if value['profile'] != 'native_docker_laboratory_tls':
        if type(value['precondition_binding']) is not dict: _fail('service_precondition_required')
        binding = value['provider_binding']
        if (binding.get('object_id') not in value['object_ids'] or len(value['object_ids']) != 1
                or binding.get('provider_identity', {}).get('tenant_id') != value['tenant_id']
                or digest(binding.get('backend')) != value['backend_scope_sha256']):
            _fail('service_provider_binding')
        for route in policy['routes']:
            if route['effect'] == 'mutation':
                prefix = '/beta/deviceManagement/configurationPolicies/' + binding['object_id']
                actual_policy_put = "/beta/deviceManagement/configurationPolicies('" + binding['object_id'] + "')"
                exact_target = route['path'] in (prefix, prefix + '/assign') or (route['method'] == 'PUT' and route['path'] == actual_policy_put)
                if route['role'] != 'provider' or route['host'] != 'graph.microsoft.com' or not exact_target:
                    _fail('service_mutation_scope')
    return value


def make_manifest(*, operation_id, profile, expires_at, execution_binding_sha256, host_spec,
        broker_policy, run_binding_sha256, run_context, storage_binding_sha256, tenant_id, object_ids,
        backend_scope_sha256, provider_binding, action='apply_saved_plan', saved_plan_sha256=None,
        identity_binding_sha256=None, state_contracts=None, precondition_binding=None):
    """Prepare exact review material; no registration or authority is conferred."""
    if type(host_spec) is not host.HostSpec: _fail('service_host_spec_invalid')
    return validate_manifest({'schema_version': VERSION, 'operation_id': operation_id, 'profile': profile,
        'prepared_at': int(time.time()), 'expires_at': expires_at, 'action': action,
        'execution_binding_sha256': execution_binding_sha256, 'host_spec': asdict(host_spec),
        'broker_policy': broker_policy, 'state_contracts': state_contracts or {},
        'saved_plan_sha256': saved_plan_sha256, 'identity_binding_sha256': identity_binding_sha256,
        'run_binding_sha256': run_binding_sha256, 'run_context': run_context, 'storage_binding_sha256': storage_binding_sha256,
        'provider_binding': provider_binding, 'tenant_id': tenant_id, 'object_ids': sorted(object_ids),
        'backend_scope_sha256': backend_scope_sha256, 'implementation_files': implementation_binding(),
        'precondition_binding': precondition_binding})


def make_intent_manifest(*, source_intent, **kwargs):
    """Versioned review material using the same exact-operation signature."""
    from .worker_source_intent import RepositoryExecutionIntent
    if type(source_intent) is not RepositoryExecutionIntent: _fail('service_source_capability_required')
    value = make_manifest(**kwargs)
    value['schema_version'] = INTENT_VERSION
    value['source_authoring_binding'] = source_intent.check()
    return validate_manifest(value)


class ControllerBinding:
    """Host-policy capability, explicitly not CI or encryption-service evidence."""
    def __init__(self, seal, kind, facts, recheck):
        if seal is not _SEAL or kind not in ('run', 'storage') or not callable(recheck):
            _fail('service_controller_capability_required')
        self.kind, self.facts, self.recheck = kind, _snapshot(facts), recheck
        self.sha256, self.pid = digest(self.facts), os.getpid()
    def __repr__(self): return '<ControllerBinding host-policy-only>'
    def __reduce_ex__(self, protocol): raise TypeError('Controller capabilities cannot be serialized.')
    def check(self, expected):
        if self.pid != os.getpid() or self.sha256 != expected or digest(self.facts) != expected:
            _fail('service_controller_binding_changed')
        if self.recheck() is not None: _fail('service_controller_recheck_contract')


def trusted_run_binding(facts, *, recheck):
    """Trusted controller code only; no JSON-to-authenticated-CI conversion."""
    return ControllerBinding(_SEAL, 'run', _run_context(facts), recheck)


def trusted_storage_binding(facts, *, recheck):
    """Host must establish actual quota/encryption/key custody; no boolean gate."""
    return ControllerBinding(_SEAL, 'storage', facts, recheck)


class ServiceRuntime:
    def __init__(self, seal, *, profile, run, storage, upstream, certificate, private_key,
            prewrite, binding=None, credentials=None, state_contracts=None, precondition=None, source_intent=None):
        if seal is not _SEAL or not callable(prewrite): _fail('service_runtime_capability_required')
        if (type(run) is not ControllerBinding or run.kind != 'run' or
                type(storage) is not ControllerBinding or storage.kind != 'storage'):
            _fail('service_controller_capability_required')
        self.profile, self.run, self.storage, self.upstream = profile, run, storage, upstream
        self.certificate, self.private_key, self.prewrite = certificate, private_key, prewrite
        self.binding, self.credentials, self.precondition = binding, credentials, precondition
        self.source_intent = source_intent
        self.state_contracts = {} if state_contracts is None else dict(state_contracts)
        self.pid = os.getpid()
    def __repr__(self): return '<ServiceRuntime redacted>'
    def __reduce_ex__(self, protocol): raise TypeError('Service runtime cannot be serialized.')
    def check(self, manifest, *, check_window=True):
        """check_window=False is the mode after a dispatch has started (see BrokerCredentials.check)."""
        if self.pid != os.getpid() or self.profile != manifest['profile']: _fail('service_runtime_profile')
        if manifest['schema_version'] == INTENT_VERSION:
            from .worker_source_intent import RepositoryExecutionIntent, validate_operation_binding
            if type(self.source_intent) is not RepositoryExecutionIntent: _fail('service_source_capability_required')
            facts = self.source_intent.check()
            if facts != manifest['source_authoring_binding']: _fail('service_source_binding_changed')
            validate_operation_binding(facts, provider_binding=manifest['provider_binding'],
                run_context=manifest['run_context'], tenant_id=manifest['tenant_id'], object_ids=manifest['object_ids'],
                backend_scope_sha256=manifest['backend_scope_sha256'])
        elif self.source_intent is not None: _fail('service_source_capability_unexpected')
        self.run.check(manifest['run_binding_sha256']); self.storage.check(manifest['storage_binding_sha256'])
        if self.profile == 'azure_public_pilot':
            ib.require_live_binding(self.binding)
            if type(self.upstream) is not broker.NativeUpstream or type(self.credentials) is not broker.BrokerCredentials:
                _fail('service_live_runtime_required')
        elif type(self.upstream) is not broker.LaboratoryUpstream:
            _fail('service_laboratory_runtime_required')
        if self.binding is not None:
            self.binding.assert_fresh(manifest['identity_binding_sha256'])
        elif manifest['identity_binding_sha256'] is not None: _fail('service_identity_required')
        if {key: item.binding() for key, item in self.state_contracts.items()} != manifest['state_contracts']:
            _fail('service_state_contract_binding')
        if self.credentials is not None: self.credentials.check(manifest['broker_policy'], check_window=check_window)
        from .worker_precondition import LiveGraphPrecondition, LaboratoryGraphPrecondition
        if manifest['precondition_binding'] is not None:
            expected = LiveGraphPrecondition if self.profile == 'azure_public_pilot' else LaboratoryGraphPrecondition
            if type(self.precondition) is not expected or self.precondition.binding() != manifest['precondition_binding']:
                _fail('service_precondition_required')
        elif self.precondition is not None: _fail('service_precondition_binding')
        spec = _host_spec(manifest['host_spec'])
        key = _private(self.private_key)
        for directory in (spec.source_root, spec.control_root, spec.job_root, spec.broker_root):
            if key == Path(directory) or Path(directory) in key.parents: _fail('service_private_key_worker_visible')
        if any(key == Path(tool.path) for tool in spec.tools): _fail('service_private_key_worker_visible')
        if host._hash_file(self.certificate, 1024 * 1024) != spec.broker_ca_sha256: _fail('service_tls_certificate_changed')
        if self.prewrite() is not None: _fail('service_prewrite_contract')


def laboratory_runtime(*, native_protocol=False, **kwargs):
    """Actual native-container/loopback-TLS qualification, never live evidence."""
    if kwargs.get('binding') is not None and type(kwargs['binding']) is not ib.LaboratoryIdentityBinding:
        _fail('service_laboratory_runtime_required')
    return ServiceRuntime(_SEAL, profile='native_docker_laboratory_protocol' if native_protocol else 'native_docker_laboratory_tls', **kwargs)


def live_runtime(**kwargs):
    """Trusted service integration API. Calling it performs no operation.

    External CI attestation, host storage protection and organizational approval
    remain necessary; the API's capabilities cannot be reconstructed from files.
    """
    ib.require_live_binding(kwargs.get('binding'))
    # Native OpenTofu must acquire its own state-blob lease. The broker binds
    # its exact Apply lock before any mutation; a second preheld lease conflicts.
    return ServiceRuntime(_SEAL, profile='azure_public_pilot', **kwargs)


class ServicePolicy:
    def __init__(self, path, *, initialize=True):
        if type(initialize) is not bool: _fail('service_initialization_mode_invalid')
        self.path = _private(path); _private(self.path.parent, directory=True); _outside_repository(self.path)
        value = _bounded_private_json(self.path)
        if (type(value) is not dict or set(value) != {'schema_version', 'authority_root', 'jobs_root',
                'verifier', 'approvers', 'admitted_manifest_sha256'} or value['schema_version'] != 'worker-service-policy/1'):
            _fail('service_policy_invalid')
        self.root, self.jobs_root = _absolute(value['authority_root']), _absolute(value['jobs_root'])
        _private(self.root.parent, directory=True); _private(self.jobs_root, directory=True)
        _outside_repository(self.root / 'authority'); _outside_repository(self.jobs_root / 'job')
        if (self.root == self.jobs_root or self.root in self.jobs_root.parents or self.jobs_root in self.root.parents
                or self.path.is_relative_to(self.jobs_root)):
            _fail('service_policy_overlap')
        if initialize: self.root.mkdir(mode=0o700, exist_ok=True)
        elif not self.root.exists(): _fail('service_store_missing')
        _private(self.root, directory=True)
        verifier = value['verifier']
        if type(verifier) is not dict or set(verifier) != {'executable', 'sha256', 'validator_library', 'validator_sha256'}:
            _fail('service_policy_invalid')
        self.verifier = aa.VerifierPin(_absolute(verifier['executable']), _hash(verifier['sha256']),
            _absolute(verifier['validator_library']), _hash(verifier['validator_sha256']))
        if protected._sha(self.verifier.executable) != self.verifier.sha256: _fail('service_verifier_changed')
        self.approvers = {}
        if type(value['approvers']) is not list or not 1 <= len(value['approvers']) <= 32: _fail('service_policy_invalid')
        for entry in value['approvers']:
            if (type(entry) is not dict or set(entry) != {'issuer', 'key_id', 'approver_id', 'public_key_hex', 'profiles'}
                    or any(type(entry[key]) is not str or not aa._LABEL.fullmatch(entry[key]) for key in ('issuer', 'key_id', 'approver_id'))
                    or type(entry['profiles']) is not list or not entry['profiles'] or not set(entry['profiles']) <= _PROFILES):
                _fail('service_policy_invalid')
            _hash(entry['public_key_hex']); aa._valid_public_key(self.verifier, bytes.fromhex(entry['public_key_hex']))
            key = (entry['issuer'], entry['key_id'])
            if key in self.approvers: _fail('service_duplicate_key')
            self.approvers[key] = entry
        entries = value['admitted_manifest_sha256']
        if type(entries) is not list or not 1 <= len(entries) <= 1000 or len(set(entries)) != len(entries):
            _fail('service_policy_invalid')
        self.admitted = frozenset(_hash(item) for item in entries); self.sha256 = digest(value)
        self.database = self.root / 'service.sqlite3'
        if not initialize:
            self._validate_existing_store()
            return
        try:
            fd = os.open(self.database, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            os.fsync(fd); os.close(fd); protected._sync(self.root)
        except FileExistsError: pass
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, root TEXT UNIQUE NOT NULL, manifest_sha256 TEXT NOT NULL, status TEXT NOT NULL, cancelled INTEGER NOT NULL DEFAULT 0, dispatches INTEGER NOT NULL DEFAULT 0, outcome TEXT)')
            columns = {row[1] for row in db.execute('PRAGMA table_info(jobs)')}
            if 'controller_pid' not in columns: db.execute('ALTER TABLE jobs ADD COLUMN controller_pid INTEGER')
            if 'controller_start' not in columns: db.execute('ALTER TABLE jobs ADD COLUMN controller_start TEXT')
            db.execute('CREATE TABLE IF NOT EXISTS ownership (scope TEXT PRIMARY KEY, job TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS consumed (issuer TEXT, nonce TEXT, operation_id TEXT UNIQUE, manifest_sha256 TEXT, PRIMARY KEY(issuer,nonce))')
            db.execute('CREATE TABLE IF NOT EXISTS approval_transcripts (operation_id TEXT PRIMARY KEY, receipt_json TEXT NOT NULL, receipt_sha256 TEXT NOT NULL, consumed_at INTEGER NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS revoked (issuer TEXT, key_id TEXT, PRIMARY KEY(issuer,key_id))')
            db.execute('CREATE TABLE IF NOT EXISTS events (sequence INTEGER PRIMARY KEY, job TEXT, kind TEXT, payload TEXT, created_at INTEGER)')
            db.execute('COMMIT')
    def _validate_existing_store(self):
        """Open an existing authority without creating, migrating or locking it for writes.

        Preparation owns schema initialization. A status/attach constructor must
        work while the controller holds a reserved writer lock, and must never
        silently upgrade an incomplete authority. Additional operation tables
        remain the responsibility of their respective typed journal readers.
        """
        if not self.database.exists(): _fail('service_store_missing')
        _private(self.database)
        for suffix in ('-journal', '-wal', '-shm'):
            path = Path(str(self.database) + suffix)
            if path.exists() or path.is_symlink(): _private(path)
        # name, declared type, NOT NULL, default SQL, primary-key position.
        columns = {
            'jobs': [('id','TEXT',0,None,1),('root','TEXT',1,None,0),
                ('manifest_sha256','TEXT',1,None,0),('status','TEXT',1,None,0),
                ('cancelled','INTEGER',1,'0',0),('dispatches','INTEGER',1,'0',0),
                ('outcome','TEXT',0,None,0),('controller_pid','INTEGER',0,None,0),
                ('controller_start','TEXT',0,None,0)],
            'ownership': [('scope','TEXT',0,None,1),('job','TEXT',1,None,0)],
            'consumed': [('issuer','TEXT',0,None,1),('nonce','TEXT',0,None,2),
                ('operation_id','TEXT',0,None,0),('manifest_sha256','TEXT',0,None,0)],
            'approval_transcripts': [('operation_id','TEXT',0,None,1),
                ('receipt_json','TEXT',1,None,0),('receipt_sha256','TEXT',1,None,0),
                ('consumed_at','INTEGER',1,None,0)],
            'revoked': [('issuer','TEXT',0,None,1),('key_id','TEXT',0,None,2)],
            'events': [('sequence','INTEGER',0,None,1),('job','TEXT',0,None,0),
                ('kind','TEXT',0,None,0),('payload','TEXT',0,None,0),('created_at','INTEGER',0,None,0)],
        }
        unique = {'jobs': {('id',),('root',)}, 'ownership': {('scope',)},
            'consumed': {('issuer','nonce'),('operation_id',)},
            'approval_transcripts': {('operation_id',)}, 'revoked': {('issuer','key_id')}, 'events': set()}
        # PRAGMA column/index metadata does not expose conflict policies,
        # collations or CHECK clauses. Admit only these existing product-created
        # declarations (including the explicitly migrated jobs columns).
        declarations = {
            'jobs': 'CREATE TABLE jobs (id TEXT PRIMARY KEY, root TEXT UNIQUE NOT NULL, manifest_sha256 TEXT NOT NULL, status TEXT NOT NULL, cancelled INTEGER NOT NULL DEFAULT 0, dispatches INTEGER NOT NULL DEFAULT 0, outcome TEXT, controller_pid INTEGER, controller_start TEXT)',
            'ownership': 'CREATE TABLE ownership (scope TEXT PRIMARY KEY, job TEXT NOT NULL)',
            'consumed': 'CREATE TABLE consumed (issuer TEXT, nonce TEXT, operation_id TEXT UNIQUE, manifest_sha256 TEXT, PRIMARY KEY(issuer,nonce))',
            'approval_transcripts': 'CREATE TABLE approval_transcripts (operation_id TEXT PRIMARY KEY, receipt_json TEXT NOT NULL, receipt_sha256 TEXT NOT NULL, consumed_at INTEGER NOT NULL)',
            'revoked': 'CREATE TABLE revoked (issuer TEXT, key_id TEXT, PRIMARY KEY(issuer,key_id))',
            'events': 'CREATE TABLE events (sequence INTEGER PRIMARY KEY, job TEXT, kind TEXT, payload TEXT, created_at INTEGER)',
        }
        db = None; primary = None
        try:
            db = sqlite3.connect(self.database.as_uri() + '?mode=ro', uri=True, timeout=0, isolation_level=None)
            db.execute('PRAGMA query_only=ON'); db.execute('PRAGMA trusted_schema=OFF')
            db.execute('BEGIN')
            if db.execute('PRAGMA journal_mode').fetchone() != ('delete',): _fail('service_store_schema_required')
            for table, expected in columns.items():
                if db.execute('SELECT type,sql FROM sqlite_master WHERE name=?', (table,)).fetchone() != ('table',declarations[table]):
                    _fail('service_store_schema_required')
                # Names here are fixed source literals, never policy/input SQL.
                actual = db.execute('PRAGMA table_xinfo(' + table + ')').fetchall()
                if ([tuple(row[1:6]) for row in actual] != expected or any(row[6] != 0 for row in actual)):
                    _fail('service_store_schema_required')
                indexes = db.execute('PRAGMA index_list(' + table + ')').fetchall()
                keys = set()
                for row in indexes:
                    if not row[2]: continue
                    if row[4] or row[3] not in ('pk','u'): _fail('service_store_schema_required')
                    fields = db.execute('SELECT name FROM pragma_index_info(?) ORDER BY seqno', (row[1],)).fetchall()
                    keys.add(tuple(field[0] for field in fields))
                if keys != unique[table]: _fail('service_store_schema_required')
                if db.execute("SELECT 1 FROM sqlite_master WHERE type='trigger' AND tbl_name=?", (table,)).fetchone():
                    _fail('service_store_schema_required')
            db.execute('COMMIT')
        except sqlite3.Error as error:
            primary = AppError('service_store_schema_required',
                'An initialized service authority with the supported schema is required; use the explicit preparation/migration procedure.')
            primary.__cause__ = error
        except BaseException as error:
            primary = error
        self._close_database(db, primary)
    @staticmethod
    def _close_database(db, primary):
        """Retain the original failure and surface secondary interruption."""
        try:
            if db is not None: db.close()
        except BaseException as cleanup:
            if primary is None: raise
            if isinstance(cleanup, (KeyboardInterrupt, SystemExit)): raise cleanup from primary
            primary.add_note('Secondary service database cleanup/close failure: ' + type(cleanup).__name__)
        if primary is not None: raise primary
    @contextmanager
    def connection(self):
        _private(self.root, directory=True); _private(self.database)
        for suffix in ('-journal', '-wal', '-shm'):
            path = Path(str(self.database) + suffix)
            if path.exists() or path.is_symlink(): _private(path)
        db = sqlite3.connect(self.database, timeout=0, isolation_level=None)
        primary = None
        try:
            db.execute('PRAGMA synchronous=FULL'); db.execute('PRAGMA journal_mode=DELETE'); db.execute('PRAGMA trusted_schema=OFF')
            yield db
        except sqlite3.Error as error:
            primary = AppError('service_store_unavailable',
                'The service authority database could not complete the requested operation.')
            primary.__cause__ = error
        except BaseException as error:
            primary = error
        self._close_database(db, primary)
    def check(self):
        if digest(_bounded_private_json(self.path)) != self.sha256: _fail('service_policy_changed')
    def event(self, db, identifier, kind, payload):
        db.execute('INSERT INTO events(job,kind,payload,created_at) VALUES (?,?,?,?)',
            (identifier, kind, canonical(payload).decode(), int(time.time())))
    def verify(self, manifest, receipt):
        self.check(); receipt = _snapshot(receipt)
        if type(receipt) is not dict or set(receipt) != {'payload', 'signature'}: _fail('service_signature_shape')
        payload = receipt['payload']
        if (type(payload) is not dict or set(payload) != {'schema_version', 'issuer', 'key_id', 'approver_id',
                'operation_id', 'manifest_sha256', 'issued_at', 'expires_at', 'nonce'}
                or payload['schema_version'] != 'signed-worker-service-approval/1'
                or payload['operation_id'] != manifest['operation_id'] or payload['manifest_sha256'] != digest(manifest)
                or type(payload['nonce']) is not str or not re.fullmatch(r'[0-9a-f]{32}', payload['nonce'])):
            _fail('service_signature_binding')
        now = int(time.time())
        # A receipt dated ahead of this clock is refused either way; when the recorded time shows a backward step the
        # refusal names the hold and the recovery. Read-only and before authentication: nothing is recorded, a damaged
        # record falls through to the original refusal below.
        if type(payload['issued_at']) is int and payload['issued_at'] > now + 5: validity.hold_if_clock_behind(self.root)
        if (type(payload['issued_at']) is not int or type(payload['expires_at']) is not int
                or not manifest['prepared_at'] <= payload['issued_at'] <= now + 5
                or not payload['expires_at'] <= manifest['expires_at']): _fail('service_signature_expired')
        try: self._authenticate(manifest, payload, receipt)
        except AppError:
            if now >= payload['expires_at']: _fail('service_signature_expired')
            raise
        # The window is judged where it is recorded: a reached expiry is latched in the store and refused here, so it
        # stays closed after a backward clock step and a restart. An unauthenticated receipt never gets this far.
        with _critical(self, payload, digest(manifest), _deadline(payload, self)): pass
        return payload
    def _authenticate(self, manifest, payload, receipt):
        if any(type(payload[key]) is not str for key in ('issuer', 'key_id', 'approver_id')): _fail('service_signer_invalid')
        signer = self.approvers.get((payload['issuer'], payload['key_id']))
        if not signer or signer['approver_id'] != payload['approver_id'] or manifest['profile'] not in signer['profiles']:
            _fail('service_signer_invalid')
        try: signature = base64.b64decode(receipt['signature'], validate=True)
        except (ValueError, TypeError): _fail('service_signature_invalid')
        if len(signature) != 64 or base64.b64encode(signature).decode() != receipt['signature']: _fail('service_signature_invalid')
        fd = os.open(protected._path(self.verifier.executable), os.O_RDONLY | os.O_NOFOLLOW)
        try:
            with os.fdopen(os.dup(fd), 'rb') as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != self.verifier.sha256: _fail('service_verifier_changed')
            with tempfile.TemporaryDirectory(prefix='service-verify-', dir=self.root) as temporary:
                root = Path(temporary)
                for name, raw in [('key.der', aa._SPKI + bytes.fromhex(signer['public_key_hex'])),
                                  ('message', SIGNATURE_DOMAIN + canonical(payload)), ('signature', signature)]:
                    protected._exclusive(root / name, raw)
                protected._supervise([str(self.verifier.executable), 'pkeyutl', '-verify', '-pubin', '-keyform', 'DER',
                    '-inkey', str(root / 'key.der'), '-rawin', '-in', str(root / 'message'), '-sigfile', str(root / 'signature')],
                    cwd=root, env={'PATH': '/usr/bin:/bin', 'HOME': str(root), 'OPENSSL_CONF': '/dev/null'},
                    pass_fds=(fd,), executable='/proc/self/fd/' + str(fd), timeout=5, output_limit=4096)
        except AppError: _fail('service_signature_invalid')
        finally: os.close(fd)


def _scopes(manifest):
    # A state's serial/hash changes between operations; physical backend
    # ownership must not change with that revision or with a stack label.
    physical = manifest.get('provider_binding', {}).get('backend', {}).get('state_blob')
    backend_scope = ({'tenant': manifest['tenant_id'], 'state_blob': physical} if type(physical) is str else
                     {'laboratory_backend_binding': manifest['backend_scope_sha256']})
    return sorted([digest({'tenant': manifest['tenant_id'], 'object_and_assignments': identifier})
                   for identifier in manifest['object_ids']] + [digest(backend_scope)])


def prepare_job(job_root, *, manifest, policy_path):
    manifest = validate_manifest(manifest, require_implementation=False); policy = ServicePolicy(policy_path); policy.check()
    root = _absolute(str(job_root))
    if root.parent != policy.jobs_root or digest(manifest) not in policy.admitted: _fail('service_operation_not_admitted')
    spec = _host_spec(manifest['host_spec'])
    if any(policy.root == Path(path) or policy.root in Path(path).parents or Path(path) in policy.root.parents
           for path in (spec.source_root, spec.control_root, spec.job_root, spec.broker_root)):
        _fail('service_authority_overlap')
    root.mkdir(mode=0o700, exist_ok=False)
    protected._exclusive(root / 'manifest.json', canonical(manifest))
    protected._exclusive(root / 'policy-binding.json', canonical({'policy_sha256': policy.sha256}))
    with policy.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0] >= 10000: _fail('service_store_capacity')
        db.execute('INSERT INTO jobs(id,root,manifest_sha256,status) VALUES (?,?,?,?)',
            (manifest['operation_id'], str(root), digest(manifest), 'prepared'))
        for scope in _scopes(manifest): db.execute('INSERT INTO ownership VALUES (?,?)', (scope, manifest['operation_id']))
        policy.event(db, manifest['operation_id'], 'prepared', {'manifest_sha256': digest(manifest)})
        db.execute('COMMIT')
    protected._sync(policy.root)
    return ServiceJob(root, policy_path).status()


class ServicePermit:
    def __init__(self, seal, job, payload, runtime):
        if seal is not _SEAL or type(runtime) is not ServiceRuntime: _fail('service_permit_required')
        self.job, self.payload, self.runtime, self.active, self.pid = job, payload, runtime, True, os.getpid()
        self.deadline = _deadline(payload, job.policy)
    def __reduce_ex__(self, protocol): raise TypeError('Service permits cannot be serialized.')
    def _stopped_or_changed(self, db):
        """Whether the job state no longer supports a running dispatch: status, cancellation, consumption, ownership and
        signer revocation, read from the connection it is given."""
        row = db.execute('SELECT status,cancelled,dispatches FROM jobs WHERE id=?', (self.job.identifier,)).fetchone()
        consumed = db.execute('SELECT manifest_sha256 FROM consumed WHERE operation_id=?', (self.job.identifier,)).fetchone()
        owners = sorted(item[0] for item in db.execute('SELECT scope FROM ownership WHERE job=?', (self.job.identifier,)))
        revoked = db.execute('SELECT 1 FROM revoked WHERE issuer=? AND key_id=?', (self.payload['issuer'], self.payload['key_id'])).fetchone()
        return row != ('running', 0, 1) or consumed != (self.job.sha256,) or owners != _scopes(self.job.manifest) or bool(revoked)
    def _before_judging(self):
        if not self.active or self.pid != os.getpid(): _fail('service_permit_inactive')
        try: self.job._check()
        except AppError as error:
            if error.code == 'service_manifest_expired': _record_expiry(self.job.policy, self.payload, self.job.sha256, self.deadline)
            raise
    def poll_active(self):
        """The watchdog's periodic check (every 0.2 s): read-only, so it never blocks a cancel or recover from another
        process. Its result grants no authority and must never gate a broker request: it reads the expiry record and the
        recorded time at different moments, so a latch committed in between can pass it once. The watchdog stops the job
        when it refuses (closed window, held clock, changed state); a closed window is latched through the shared
        section first (see _watch)."""
        self._before_judging()
        with self.job.policy.connection() as db:
            stopped = self._stopped_or_changed(db)
            latched = _latched(db, self.payload, self.job.sha256)
        _watch(self.job.policy, self.payload, self.job.sha256, self.deadline, latched, fail=_fail,
            expired_code='service_signature_expired')
        if stopped: _fail('service_permit_inactive')
        self.runtime.check(self.job.manifest)
    def inflight_active(self):
        """The in-flight check the broker makes once the upstream has answered: the job must still be running, uncancelled,
        owned, and the signer unrevoked. It never judges the window: the window bounds when a dispatch may start."""
        if not self.active or self.pid != os.getpid(): _fail('service_permit_inactive')
        self.job._check(expiry=False)
        with self.job.policy.connection() as db:
            if self._stopped_or_changed(db): _fail('service_permit_inactive')
        self.runtime.check(self.job.manifest, check_window=False)
    def check_active(self):
        """The authorization check that gates every broker request. It enters the shared critical section, judges the
        window, rereads the job state, the signer revocation and the expiry record inside it, and commits the
        per-request marker before it returns: nothing can latch the expiry between the decision and its record, and a
        stale read cannot authorize."""
        self._before_judging()
        self.runtime.check(self.job.manifest)
        with _critical(self.job.policy, self.payload, self.job.sha256, self.deadline) as db:
            if self._stopped_or_changed(db): _fail('service_permit_inactive')
            _mark_authorized(db, self.job.identifier, 'apply')


class ServiceJob:
    def __init__(self, job_root, policy_path):
        self.policy = ServicePolicy(policy_path, initialize=False); self.root = _private(job_root, directory=True)
        if self.root.parent != self.policy.jobs_root: _fail('service_job_outside_policy')
        self.manifest = _bounded_private_json(self.root / 'manifest.json')
        if self.manifest.get('schema_version') not in (VERSION, INTENT_VERSION): _fail('service_job_domain')
        self.sha256, self.identifier = digest(self.manifest), self.manifest.get('operation_id')
        self._check(expiry=False)
    def _check(self, *, expiry=True):
        self.policy.check()
        if digest(self.manifest) != self.sha256 or digest(_bounded_private_json(self.root / 'manifest.json')) != self.sha256:
            _fail('service_job_changed')
        if expiry:
            if (self.sha256 not in self.policy.admitted or
                    _bounded_private_json(self.root / 'policy-binding.json') != {'policy_sha256': self.policy.sha256}):
                _fail('service_job_admission_changed')
            validate_manifest(self.manifest)
        with self.policy.connection() as db:
            row = db.execute('SELECT root,manifest_sha256 FROM jobs WHERE id=?', (self.identifier,)).fetchone()
        if row != (str(self.root), self.sha256): _fail('service_job_not_registered')
    def review(self):
        self._check(expiry=False)
        return {'manifest': self.manifest, 'manifest_sha256': self.sha256,
            'signature_domain_hex': SIGNATURE_DOMAIN.hex(), 'authority': 'independent_external_signer_required',
            'execution_authorized': False, 'production_authorized': False}
    def status(self):
        self._check(expiry=False)
        with self.policy.connection() as db:
            row = db.execute('SELECT status,cancelled,dispatches,outcome FROM jobs WHERE id=?', (self.identifier,)).fetchone()
            events = [{'sequence': r[0], 'kind': r[1], 'payload': parse_json(r[2]), 'created_at': r[3]} for r in
                db.execute('SELECT sequence,kind,payload,created_at FROM events WHERE job=? ORDER BY sequence', (self.identifier,))]
        return {'operation_id': self.identifier, 'manifest_sha256': self.sha256, 'status': row[0],
            'cancel_requested': bool(row[1]), 'dispatches': row[2], 'outcome': parse_json(row[3]) if row[3] else None,
            'events': events, 'profile': self.manifest['profile'], 'production_authorized': False,
            'ci_attestation': 'unestablished_host_policy_contract_only',
            'implementation_matches_reviewed': self.manifest.get('implementation_files') == implementation_binding(),
            'implementation_comparison_scope': 'current_observer_process_against_reviewed_controller',
            'approved_controller_runtime_re_attested': False,
            'policy_matches_reviewed': _bounded_private_json(self.root / 'policy-binding.json') == {'policy_sha256': self.policy.sha256}}
    def attach(self):
        """Read-only durable view; reopening does not recreate a permit or retry."""
        return self.status()
    def _implementation_current(self):
        """Whether the controller now is the one this job was prepared under; None when the inventory cannot be read."""
        try: return self.manifest.get('implementation_files') == implementation_binding()
        except AppError: return None
    def cancel(self, *, administrative=False):
        """Cancel only restricts and makes no host call, so no inventory gate applies: a job dispatched under an earlier
        controller can always be cancelled. An explicit administrative cancel records in its event that it was administrative
        and whether the controller is current."""
        self._check(expiry=False)
        current = self._implementation_current()
        with self.policy.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute("UPDATE jobs SET cancelled=1,status=CASE WHEN dispatches=0 THEN 'cancelled_before_dispatch' ELSE status END WHERE id=?", (self.identifier,))
            from .worker_successor import restore_undispatched_owner
            if not restore_undispatched_owner(self, db):
                db.execute('DELETE FROM ownership WHERE job=? AND EXISTS(SELECT 1 FROM jobs WHERE id=? AND dispatches=0)', (self.identifier, self.identifier))
            self.policy.event(db, self.identifier, 'cancel_requested', {'dispatch_replayed': False,
                **({'administrative': True, 'implementation_current': current} if administrative else {})}); db.execute('COMMIT')
        return self.status()
    def run(self, signed_receipt, *, runtime):
        try: self._check()
        except AppError as error:
            # The manifest window is judged on the bare clock ahead of everything else. A receipt that authenticates has
            # its expiry recorded here too, or a rollback after this first refusal would reopen it.
            if error.code == 'service_manifest_expired': _record_expiry_of(self, signed_receipt)
            raise
        if threading.current_thread() is not threading.main_thread(): _fail('service_main_thread_required')
        if type(runtime) is not ServiceRuntime: _fail('service_runtime_capability_required')
        runtime.check(self.manifest)
        spec = _host_spec(self.manifest['host_spec'])
        for root, expected in ((spec.source_root, spec.source_sha256), (spec.control_root, spec.control_sha256)):
            if host.directory_binding(root)['sha256'] != expected: _fail('service_input_changed')
        if self.manifest['saved_plan_sha256'] is not None and host._hash_file(Path(spec.control_root) / 'approved.plan', 32 * 1024 * 1024) != self.manifest['saved_plan_sha256']:
            _fail('service_saved_plan_changed')
        if list(_private(spec.job_root, directory=True).iterdir()): _fail('service_fresh_job_required')
        broker_root = _private(spec.broker_root, directory=True)
        if list(broker_root.iterdir()): _fail('service_fresh_broker_required')
        # Freeze once before verification; persist only these exact checked bytes.
        signed_snapshot = _snapshot(signed_receipt)
        payload = self.policy.verify(self.manifest, signed_snapshot)
        # The window is judged again, and the approval consumed, in one critical section: nothing can latch the expiry
        # between the judgment and the consumption, and an expiry reached since the verification is refused here.
        with _critical(self.policy, payload, self.sha256, _deadline(payload, self.policy)) as db:
            if db.execute('SELECT status,cancelled,dispatches FROM jobs WHERE id=?', (self.identifier,)).fetchone() != ('prepared', 0, 0):
                _fail('service_operation_not_replayable')
            if db.execute('SELECT 1 FROM revoked WHERE issuer=? AND key_id=?', (payload['issuer'], payload['key_id'])).fetchone(): _fail('service_key_revoked')
            db.execute('INSERT INTO consumed VALUES (?,?,?,?)', (payload['issuer'], payload['nonce'], self.identifier, self.sha256))
            db.execute('INSERT INTO approval_transcripts VALUES (?,?,?,?)',
                (self.identifier, canonical(signed_snapshot).decode(), digest(signed_snapshot), int(time.time())))
            identity = _controller_identity(os.getpid())
            if identity is None: _fail('service_controller_identity_unavailable')
            db.execute("UPDATE jobs SET status='running',dispatches=1,controller_pid=?,controller_start=? WHERE id=?",
                (os.getpid(), identity, self.identifier))
            self.policy.event(db, self.identifier, 'dispatch_consumed', {'manifest_sha256': self.sha256}); db.execute('COMMIT')
        permit = ServicePermit(_SEAL, self, payload, runtime)
        server = None; thread = None; result = None; primary = None; transport = None
        stopped = threading.Event(); watchdog_fault = []; watchdog = None
        shutdown_failures = []; recording_failures = []; interruption = None; shutdown_interrupted = False
        recording_uncertain = False
        def failed(error, phase, failures):
            nonlocal primary, interruption, shutdown_interrupted
            failures.append({'phase': phase, 'error': getattr(error, 'code', type(error).__name__)})
            if primary is None: primary = error
            if isinstance(error, (KeyboardInterrupt, SystemExit)):
                if interruption is None: interruption = error
                shutdown_interrupted = True
        def finish_thread(value, timeout, phase):
            if value is None: return
            try:
                value.join(timeout=timeout)
                if value.is_alive(): _fail('service_shutdown_thread_active')
            except BaseException as error:
                failed(error, phase, shutdown_failures)
        try:
            permit.check_active()
            guard = (broker.live_guard(self.manifest['execution_binding_sha256'], binding=runtime.binding, recheck=permit.check_active,
                                       inflight=permit.inflight_active)
                     if self.manifest['profile'] == 'azure_public_pilot' else
                     broker.laboratory_guard(self.manifest['execution_binding_sha256'], permit.check_active, permit.inflight_active))
            transport = broker.EgressBroker(self.manifest['broker_policy'], journal=self.root / 'broker.sqlite3',
                guard=guard, upstream=runtime.upstream, state_contracts=runtime.state_contracts, credentials=runtime.credentials,
                **({'precondition': runtime.precondition} if runtime.precondition is not None else {}))
            server = broker.UnixBrokerServer(broker_root / 'egress.sock', transport,
                certificate=runtime.certificate, private_key=runtime.private_key)
            thread = threading.Thread(target=server.serve, daemon=True, name='intune-service-broker'); thread.start()
            permit.check_active()
            def monitor():
                while not stopped.wait(0.2):
                    try: permit.poll_active()
                    except BaseException as error:
                        watchdog_fault.append(getattr(error, 'code', type(error).__name__))
                        if not stopped.is_set(): os.kill(os.getpid(), signal.SIGINT)
                        return
            watchdog = threading.Thread(target=monitor, daemon=True, name='intune-service-watchdog'); watchdog.start()
            result = host.launch(spec, self.root / 'host-run')
        except BaseException as error:
            primary = error
            if isinstance(error, (KeyboardInterrupt, SystemExit)): interruption = error
            receipt_path = self.root / 'host-run/receipt.json'
            try:
                if receipt_path.exists(): result = _bounded_private_json(receipt_path)
            except BaseException as receipt_error:
                failed(receipt_error, 'host_receipt_read', recording_failures)
        finally:
            stopped.set()
            # Revoke broker authority before cleanup; a failed close or join
            # must not leave a permit active or skip recording the first cause.
            permit.active = False
            finish_thread(watchdog, 35, 'watchdog_join')
            if server is not None:
                try: server.close()
                except BaseException as error: failed(error, 'broker_close', shutdown_failures)
            finish_thread(thread, 12, 'broker_join')
            native_recovery = None
            if transport is not None and self.manifest['broker_policy'].get('native_lock') is not None:
                try:
                    private_record = transport.native_recovery_record()
                    protected._exclusive(self.root / 'native-lease-recovery.json', canonical(private_record))
                    native_recovery = {'artifact': str(self.root / 'native-lease-recovery.json'),
                        'sha256': digest(private_record), 'automatic_release_authorized': False,
                        'state': 'independent_current_blob_context_required'}
                except BaseException as error:
                    failed(error, 'native_recovery_archive', recording_failures)
                    native_recovery = {'state': 'recovery_archive_failed', 'error': getattr(error, 'code', type(error).__name__),
                        'automatic_release_authorized': False}
            outcome = {'host': result, 'primary_error': getattr(primary, 'code', type(primary).__name__) if primary else None,
                'independent_service_readback': 'required', 'production_authorized': False,
                'watchdog_error': watchdog_fault[0] if watchdog_fault else None, 'native_backend_recovery': native_recovery,
                'shutdown_failures': shutdown_failures, 'recording_failures': recording_failures,
                'authority_recording': 'committed',
                'operation_outcome': 'host_completed_service_unverified' if result and result.get('status') == 'complete'
                    and primary is None and not shutdown_failures else 'outcome_unknown'}
            try:
                with self.policy.connection() as db:
                    db.execute('BEGIN IMMEDIATE')
                    db.execute('UPDATE jobs SET status=?,outcome=?,controller_pid=NULL,controller_start=NULL WHERE id=?',
                        (outcome['operation_outcome'], canonical(outcome).decode(), self.identifier))
                    self.policy.event(db, self.identifier, 'worker_stopped', outcome); db.execute('COMMIT')
            except BaseException as error:
                # COMMIT may already have succeeded. Preserve the authority as
                # observed and never re-dispatch to resolve missing evidence.
                recording_uncertain = True
                failed(error, 'authority_outcome', recording_failures)
                outcome['authority_recording'] = 'failed_or_uncertain'
                outcome['primary_error'] = getattr(primary, 'code', type(primary).__name__)
            try:
                protected._exclusive(self.root / 'service-receipt.json', canonical(outcome))
            except BaseException as error:
                failed(error, 'service_receipt_archive', recording_failures)
                try:
                    with self.policy.connection() as db:
                        self.policy.event(db, self.identifier, 'receipt_archive_failed',
                            {'error': getattr(error, 'code', type(error).__name__),
                             'primary_error': getattr(primary, 'code', type(primary).__name__),
                             'authority_recording': outcome['authority_recording'],
                             'known_outcome_preserved': not recording_uncertain, 'retry_authorized': False})
                except BaseException as event_error:
                    recording_uncertain = True
                    failed(event_error, 'receipt_failure_event', recording_failures)
        if primary is not None:
            primary.service_failure_record = outcome
        if interruption is not None and (not watchdog_fault or shutdown_interrupted):
            if interruption is primary: raise interruption
            raise interruption from primary
        if recording_uncertain: raise primary
        try: return self.status()
        except BaseException as error:
            if primary is None: raise
            failed(error, 'final_status_read', recording_failures)
            if isinstance(error, (KeyboardInterrupt, SystemExit)): raise error from primary
            raise primary from error
    def reconcile(self, readback):
        """Release ownership only after a sealed fresh independent state read.

        This never replays a mutation, unlocks a remote lease, claims endpoint
        effectiveness or reconstructs approval from a supplied report.
        """
        from .worker_service_readback import LiveServiceReadback, LaboratoryServiceReadback
        self._check(expiry=False)
        from .worker_committed_readback import LiveCommittedServiceReadback, LaboratoryCommittedServiceReadback
        from .worker_completed_readback import LiveKnownCompletedServiceReadback, LaboratoryKnownCompletedServiceReadback
        known_completed = (LiveKnownCompletedServiceReadback, LaboratoryKnownCompletedServiceReadback)
        expected = ((LiveServiceReadback, LiveCommittedServiceReadback, LiveKnownCompletedServiceReadback) if self.manifest['profile'] == 'azure_public_pilot' else
                    (LaboratoryServiceReadback, LaboratoryCommittedServiceReadback, LaboratoryKnownCompletedServiceReadback))
        if type(readback) not in expected: _fail('service_readback_capability_required')
        facts = readback.verified(self.manifest)
        with self.policy.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT status,dispatches,outcome,controller_pid FROM jobs WHERE id=?', (self.identifier,)).fetchone()
            consumed = db.execute('SELECT manifest_sha256 FROM consumed WHERE operation_id=?', (self.identifier,)).fetchone()
            owners = sorted(r[0] for r in db.execute('SELECT scope FROM ownership WHERE job=?', (self.identifier,)))
            if (row[0] not in ('host_completed_service_unverified', 'outcome_unknown') or row[1] != 1
                    or row[3] is not None or consumed != (self.sha256,) or owners != _scopes(self.manifest)):
                _fail('service_reconciliation_not_ready')
            previous = parse_json(row[2]) if row[2] else None
            if (type(readback) in known_completed and
                    (row[0] != 'host_completed_service_unverified' or digest(previous) != facts['original_outcome_sha256'])):
                _fail('service_known_completed_outcome_changed')
            if previous and previous.get('host') and not previous['host'].get('cleanup', {}).get('removed'):
                _fail('service_host_cleanup_unconfirmed')
            host_record = self.root / 'host-run/journal.json'
            if host_record.exists() and not _bounded_private_json(host_record).get('cleanup', {}).get('removed'):
                recovered = db.execute("SELECT payload FROM events WHERE job=? AND kind='recovery_no_replay' ORDER BY sequence DESC LIMIT 1", (self.identifier,)).fetchone()
                if not recovered or not parse_json(recovered[0]).get('cleanup', {}).get('removed'):
                    _fail('service_host_cleanup_unconfirmed')
            status = ('service_state_converged' if row[0] == 'host_completed_service_unverified' else
                      'service_state_converged_execution_unknown')
            report = {'previous_outcome': previous, 'independent_readback': facts, 'reservation_released': True,
                'mutation_replayed': False, 'execution_provenance': 'host_completed' if row[0] == 'host_completed_service_unverified' else 'unresolved',
                'endpoint_effectiveness': 'unestablished', 'production_approved': False}
            db.execute('UPDATE jobs SET status=?,outcome=? WHERE id=?', (status, canonical(report).decode(), self.identifier))
            db.execute('DELETE FROM ownership WHERE job=?', (self.identifier,))
            self.policy.event(db, self.identifier, 'independent_state_reconciled', report)
            db.execute('COMMIT')
        protected._sync(self.policy.root)
        try: protected._exclusive(self.root / ('reconciliation-' + uuid.uuid4().hex + '.json'), canonical(report))
        except OSError as error:
            with self.policy.connection() as db:
                self.policy.event(db, self.identifier, 'reconciliation_archive_failed',
                    {'error': type(error).__name__, 'known_outcome_preserved': True, 'retry_authorized': False})
        return self.status()

    def recover(self):
        """Recovery with the current controller calls the host and writes state. A job prepared under another controller (or
        whose inventory cannot be read) makes no host call: if its recorded controller is dead, recovery only marks it
        outcome_unknown and clears the controller identity, so it can still be settled after an install."""
        self._check(expiry=False)
        current = bool(self._implementation_current())
        # Commit cancellation before considering cleanup, so no new broker
        # request remains authorized while a second process observes recovery.
        with self.policy.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT controller_pid,controller_start,status FROM jobs WHERE id=?', (self.identifier,)).fetchone()
            db.execute('UPDATE jobs SET cancelled=1 WHERE id=?', (self.identifier,))
            self.policy.event(db, self.identifier, 'recovery_cancel_requested', {'mutation_replayed': False})
            db.execute('COMMIT')
        if row[2] == 'running' and row[0] is not None and _controller_identity(row[0]) == row[1]:
            _fail('service_cleanup_owner_active')
        host_root = self.root / 'host-run'
        if not current: recovered = {'host_call_made': False, 'implementation_current': False, 'cleanup_not_attempted': True}
        else: recovered = host.recover(host_root) if (host_root / 'journal.json').exists() else {'container_never_recorded': True}
        with self.policy.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute("UPDATE jobs SET cancelled=1,controller_pid=NULL,controller_start=NULL,status=CASE WHEN dispatches=0 THEN 'cancelled_before_dispatch' WHEN status='running' THEN 'outcome_unknown' ELSE status END WHERE id=?", (self.identifier,))
            from .worker_successor import restore_undispatched_owner
            if not restore_undispatched_owner(self, db):
                db.execute('DELETE FROM ownership WHERE job=? AND EXISTS(SELECT 1 FROM jobs WHERE id=? AND dispatches=0)', (self.identifier, self.identifier))
            self.policy.event(db, self.identifier, 'recovery_no_replay', recovered); db.execute('COMMIT')
        return self.status()
