"""Separately signed native state-only adoption on the common service authority.

No ordinary apply permission is reused. JSON is review material only; a trusted
controller must supply exact process-held identity, storage, reader, provider
and ownership capabilities. The terminal can prepare, inspect and cancel only.
"""
from __future__ import annotations
import base64
from dataclasses import asdict
import hashlib
import os
from pathlib import Path
import re
import signal
import tempfile
import threading
import time
import uuid
from urllib.parse import urlsplit

from intune_iac import approval_authority as aa, identity_binding as ib, protected
from intune_iac import worker_broker as broker, worker_host as host, worker_service as service
from intune_iac.azure_backend import StateRevision
from intune_iac.io import AppError, canonical, digest, parse_json
from intune_iac.provider_journey import _private, _absolute
from intune_iac.worker_adoption_ownership import OwnershipAdmission

VERSION = 'native-state-adoption/1'
APPROVAL_VERSION = 'signed-native-state-adoption-approval/1'
SIGNATURE_DOMAIN = b'intune-workbench:native-state-adoption-approval:v1\x00'
_SEAL = object()
_PROFILES = {'native_docker_laboratory_protocol', 'azure_public_pilot'}


def _fail(code):
    raise AppError(code, 'The separately approved state-only adoption or independent qualification was not established.') from None


def _copy(value): return service._snapshot(value)


def _secondary(primary, secondary, phase):
    """Disclose secondary failure without losing a real cancellation request."""
    primary.add_note('Secondary adoption ' + phase + ': ' + str(getattr(secondary, 'code', type(secondary).__name__)))
    if isinstance(secondary, (KeyboardInterrupt, SystemExit)):
        raise secondary from primary


def _policy_shape(value, manifest, spec, *, verification=False):
    if (type(value) is not dict or value.get('schema_version') != 'protected-egress-policy/1.0'
            or value.get('profile') != ('azure_public_pilot' if manifest['profile'] == 'azure_public_pilot' else 'laboratory_native_protocol')
            or value.get('execution_binding_sha256') != manifest['execution_binding_sha256']
            or value.get('expires_at') != manifest['expires_at'] or value.get('worker_uid') != spec.uid
            or type(value.get('routes')) is not list or not 1 <= len(value['routes']) <= 128
            or spec.broker_root is None or spec.broker_ca_sha256 is None):
        _fail('adoption_broker_binding')
    operation = manifest['verification_operation_id'] if verification else manifest['operation_id']
    if value.get('operation_id') != operation: _fail('adoption_broker_binding')
    writes = []
    for route in value['routes']:
        if type(route) is not dict: _fail('adoption_route_invalid')
        if route.get('effect') == 'mutation': _fail('adoption_graph_mutation_forbidden')
        if route.get('host') == 'graph.microsoft.com' and route.get('method') != 'GET':
            _fail('adoption_graph_mutation_forbidden')
        if route.get('host') == 'graph.microsoft.com':
            oid = manifest['object_ids'][0]; base = '/beta/deviceManagement/configurationPolicies'
            allowed = {base + '/' + oid: {}, base + "('" + oid + "')/assignments": {},
                base + "('" + oid + "')/settings": {'$expand': 'children'}}
            if (route.get('path') not in allowed or route.get('query') != allowed[route['path']]
                    or route.get('role') != 'provider' or route.get('audience') != 'graph'
                    or route.get('effect') != 'readonly'):
                _fail('adoption_graph_read_scope')
        if route.get('effect') == 'state_write': writes.append(route)
        dynamic = route.get('dynamic_headers', {})
        if verification and 'native_lock_metadata_adoption' in dynamic.values():
            _fail('adoption_verification_import_lock_forbidden')
    if verification:
        if writes: _fail('adoption_verification_state_write_forbidden')
        # Existing closed broker validator already supports ordinary Plan-only.
        broker.validate_policy(value)
    elif (len(writes) != 1 or writes[0].get('state_contract_sha256') != digest(manifest['state_contract'])
            or writes[0].get('body_sha256') != manifest['state_contract'].get('expected_semantic_sha256')):
        _fail('adoption_state_route_binding')


def validate_manifest(value, *, require_implementation=True):
    value = _copy(value)
    fields = {'schema_version', 'operation_id', 'verification_operation_id', 'profile', 'prepared_at', 'expires_at',
        'action', 'execution_binding_sha256', 'host_spec', 'broker_policy', 'verification_host_spec',
        'verification_broker_policy', 'identity_binding_sha256', 'run_binding_sha256', 'run_context',
        'storage_binding_sha256', 'provider_binding', 'tenant_id', 'object_ids', 'backend_scope_sha256',
        'implementation_files', 'state_contract', 'ownership_binding', 'intended_writer'}
    if type(value) is not dict or set(value) != fields or value['schema_version'] != VERSION:
        _fail('adoption_manifest_invalid')
    if value['profile'] not in _PROFILES or value['action'] != 'native_state_only_import':
        _fail('adoption_profile_invalid')
    for key in ('operation_id', 'verification_operation_id', 'tenant_id'):
        if type(value[key]) is not str or not service._UUID.fullmatch(value[key]) or not uuid.UUID(value[key]).int:
            _fail('adoption_identity_invalid')
    if value['verification_operation_id'] == value['operation_id']: _fail('adoption_operation_ids_overlap')
    if (type(value['object_ids']) is not list or len(value['object_ids']) != 1
            or type(value['object_ids'][0]) is not str or not service._UUID.fullmatch(value['object_ids'][0])):
        _fail('adoption_identity_invalid')
    now = int(time.time())
    if (type(value['prepared_at']) is not int or type(value['expires_at']) is not int
            or not value['prepared_at'] <= now + 5 < value['expires_at'] <= value['prepared_at'] + 900):
        _fail('adoption_expired')
    for key in ('execution_binding_sha256', 'identity_binding_sha256', 'run_binding_sha256',
                'storage_binding_sha256', 'backend_scope_sha256'): service._hash(value[key])
    native, contract, ownership = value['provider_binding'], value['state_contract'], value['ownership_binding']
    if (type(native) is not dict or native.get('schema_version') != 'worker-adoption-provider/1'
            or native.get('adoption_operation') != value['action'] or native.get('tenant_id') != value['tenant_id']
            or native.get('object_id') != value['object_ids'][0]
            or native.get('provider_identity', {}).get('tenant_id') != value['tenant_id']
            or digest(native.get('backend')) != value['backend_scope_sha256']):
        _fail('adoption_provider_binding')
    from intune_iac.worker_adoption_provider import import_command, first_plan_command, show_first_plan_command
    if (native.get('import_argv') != list(import_command(value['object_ids'][0]))
            or native.get('first_plan_argv') != list(first_plan_command())
            or native.get('show_first_plan_argv') != list(show_first_plan_command())):
        _fail('adoption_command_binding')
    context = service._run_context(value['run_context'])
    if (context['schema_version'] != 'service-run-context/1' or digest(context) != value['run_binding_sha256']
            or any(context[key] != native.get(other) for key, other in (
                ('source_revision', 'source_revision'), ('source_sha256', 'source_sha256'),
                ('effective_inputs_sha256', 'effective_input_sha256'), ('provider_lock_sha256', 'lockfile_sha256')))):
        _fail('adoption_run_context_binding')
    if (type(contract) is not dict or contract.get('schema_version') != 'native-adoption-state-contract/1'
            or contract.get('profile') != ('azure_public_pilot' if value['profile'] == 'azure_public_pilot' else 'laboratory_native_protocol')
            or contract.get('execution_binding_sha256') != value['execution_binding_sha256']
            or contract.get('tenant_id') != value['tenant_id'] or contract.get('object_id') != value['object_ids'][0]
            or contract.get('source_sha256') != native['source_sha256']
            or contract.get('effective_inputs_sha256') != native['effective_input_sha256']
            or contract.get('locks_sha256') != native['lockfile_sha256']
            or contract.get('backend') != native['backend']['backend']):
        _fail('adoption_state_contract_binding')
    if (type(ownership) is not dict or ownership.get('schema_version') != 'native-adoption-ownership/1'
            or ownership.get('tenant_id') != value['tenant_id'] or ownership.get('object_id') != value['object_ids'][0]
            or ownership.get('baseline_sha256') != contract.get('baseline_sha256')
            or ownership.get('result') != 'no_owner_in_completely_searched_declared_scope'
            or ownership.get('selected_scope') != {'repository': context['repository'], 'stack': context['stack'],
                'component': context['component'], 'backend': native['backend']['state_blob']}):
        _fail('adoption_ownership_binding')
    if value['intended_writer'] != _writer_intent(native, ownership):
        _fail('adoption_intended_writer_binding')
    specs = [service._host_spec(value[key]) for key in ('host_spec', 'verification_host_spec')]
    # Full host admission requires the sole live broker socket and belongs to
    # launch; manifest review and watchdog checks must not create that socket.
    for spec in specs:
        for path in (spec.source_root, spec.control_root, spec.job_root, spec.broker_root):
            if type(path) is not str or not Path(path).is_absolute() or '..' in Path(path).parts:
                _fail('adoption_host_path_invalid')
    if (specs[0].source_root != specs[1].source_root or specs[0].source_sha256 != specs[1].source_sha256
            or specs[0].tools != specs[1].tools or specs[0].uid != specs[1].uid or specs[0].gid != specs[1].gid
            or len({specs[0].job_root, specs[1].job_root, specs[0].broker_root, specs[1].broker_root}) != 4):
        _fail('adoption_verification_host_binding')
    _policy_shape(value['broker_policy'], value, specs[0])
    _policy_shape(value['verification_broker_policy'], value, specs[1], verification=True)
    inventory = value['implementation_files']
    if (type(inventory) is not dict or not 1 <= len(inventory) <= 4096 or
            any(type(key) is not str or not 1 <= len(key) <= 4096 or type(item) is not str
                or not service._HASH.fullmatch(item) for key, item in inventory.items())):
        _fail('adoption_implementation_invalid')
    if require_implementation and inventory != service.implementation_binding():
        _fail('adoption_implementation_changed')
    return value


def _writer_intent(native, ownership):
    """Signed local intended writer facts; no claim of organizational approval."""
    return {'schema_version': 'native-adoption-intended-writer/1', 'tenant_id': native['tenant_id'],
        'object_id': native['object_id'], 'scope': ownership['selected_scope'],
        'policy_writer': native['provider_identity'], 'assignment_writer': native['provider_identity'],
        'ordinary_graph_changes_require_separate_approval': True,
        'organizational_sole_writer_approval_established': False,
        'absence_of_undeclared_or_external_writers_established': False}


def make_manifest(*, operation_id, verification_operation_id, profile, expires_at, execution_binding_sha256,
        host_spec, broker_policy, verification_host_spec, verification_broker_policy, run_context,
        storage_binding_sha256, provider_binding, identity_binding_sha256, state_contract, ownership_binding):
    if type(host_spec) is not host.HostSpec or type(verification_host_spec) is not host.HostSpec:
        _fail('adoption_host_spec_required')
    return validate_manifest({'schema_version': VERSION, 'operation_id': operation_id,
        'verification_operation_id': verification_operation_id, 'profile': profile, 'prepared_at': int(time.time()),
        'expires_at': expires_at, 'action': 'native_state_only_import', 'execution_binding_sha256': execution_binding_sha256,
        'host_spec': asdict(host_spec), 'broker_policy': broker_policy,
        'verification_host_spec': asdict(verification_host_spec), 'verification_broker_policy': verification_broker_policy,
        'identity_binding_sha256': identity_binding_sha256, 'run_binding_sha256': digest(run_context), 'run_context': run_context,
        'storage_binding_sha256': storage_binding_sha256, 'provider_binding': provider_binding,
        'tenant_id': provider_binding['tenant_id'], 'object_ids': [provider_binding['object_id']],
        'backend_scope_sha256': digest(provider_binding['backend']), 'implementation_files': service.implementation_binding(),
        'state_contract': state_contract, 'ownership_binding': ownership_binding,
        'intended_writer': _writer_intent(provider_binding, ownership_binding)})


def _verify(policy, manifest, receipt):
    policy.check(); receipt = _copy(receipt)
    if type(receipt) is not dict or set(receipt) != {'payload', 'signature'}: _fail('adoption_signature_shape')
    payload = receipt['payload']
    if (type(payload) is not dict or set(payload) != {'schema_version', 'issuer', 'key_id', 'approver_id',
            'operation_id', 'manifest_sha256', 'issued_at', 'expires_at', 'nonce'}
            or payload['schema_version'] != APPROVAL_VERSION or payload['operation_id'] != manifest['operation_id']
            or payload['manifest_sha256'] != digest(manifest) or type(payload['nonce']) is not str
            or not re.fullmatch('[0-9a-f]{32}', payload['nonce'])): _fail('adoption_signature_binding')
    now = int(time.time())
    if (type(payload['issued_at']) is not int or type(payload['expires_at']) is not int
            or not manifest['prepared_at'] <= payload['issued_at'] <= now + 5
            or not now < payload['expires_at'] <= manifest['expires_at']): _fail('adoption_signature_expired')
    if any(type(payload[key]) is not str for key in ('issuer', 'key_id', 'approver_id')): _fail('adoption_signer_invalid')
    signer = policy.approvers.get((payload['issuer'], payload['key_id']))
    if not signer or signer['approver_id'] != payload['approver_id'] or manifest['profile'] not in signer['profiles']:
        _fail('adoption_signer_invalid')
    try: signature = base64.b64decode(receipt['signature'], validate=True)
    except (ValueError, TypeError): _fail('adoption_signature_invalid')
    if len(signature) != 64 or base64.b64encode(signature).decode() != receipt['signature']: _fail('adoption_signature_invalid')
    fd = os.open(protected._path(policy.verifier.executable), os.O_RDONLY | os.O_NOFOLLOW)
    try:
        with os.fdopen(os.dup(fd), 'rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != policy.verifier.sha256: _fail('adoption_verifier_changed')
        with tempfile.TemporaryDirectory(prefix='adoption-verify-', dir=policy.root) as temporary:
            root = Path(temporary)
            for name, raw in [('key.der', aa._SPKI + bytes.fromhex(signer['public_key_hex'])),
                    ('message', SIGNATURE_DOMAIN + canonical(payload)), ('signature', signature)]:
                protected._exclusive(root / name, raw)
            protected._supervise([str(policy.verifier.executable), 'pkeyutl', '-verify', '-pubin', '-keyform', 'DER',
                '-inkey', str(root / 'key.der'), '-rawin', '-in', str(root / 'message'), '-sigfile', str(root / 'signature')],
                cwd=root, env={'PATH': '/usr/bin:/bin', 'HOME': str(root), 'OPENSSL_CONF': '/dev/null'},
                pass_fds=(fd,), executable='/proc/self/fd/' + str(fd), timeout=5, output_limit=4096)
    except AppError: _fail('adoption_signature_invalid')
    finally: os.close(fd)
    return payload


def _tables(policy):
    with policy.connection() as db:
        db.execute('CREATE TABLE IF NOT EXISTS adoption_operations (operation_id TEXT PRIMARY KEY, manifest_sha256 TEXT NOT NULL, verification_id TEXT UNIQUE NOT NULL, verification_dispatches INTEGER NOT NULL DEFAULT 0, verification_status TEXT NOT NULL DEFAULT \'not_started\', verification_outcome TEXT)')
        db.execute('CREATE TABLE IF NOT EXISTS approval_transcripts (operation_id TEXT PRIMARY KEY, receipt_json TEXT NOT NULL, receipt_sha256 TEXT NOT NULL, consumed_at INTEGER NOT NULL)')


def prepare_job(job_root, *, manifest, policy_path):
    manifest = validate_manifest(manifest, require_implementation=False)
    policy = service.ServicePolicy(policy_path); policy.check(); _tables(policy)
    root = _absolute(str(job_root))
    if root.parent != policy.jobs_root or digest(manifest) not in policy.admitted: _fail('adoption_not_admitted')
    for key in ('host_spec', 'verification_host_spec'):
        spec = service._host_spec(manifest[key])
        if any(policy.root == Path(path) or policy.root in Path(path).parents or Path(path) in policy.root.parents
                for path in (spec.source_root, spec.control_root, spec.job_root, spec.broker_root)):
            _fail('adoption_authority_overlap')
    root.mkdir(mode=0o700, exist_ok=False)
    protected._exclusive(root / 'manifest.json', canonical(manifest))
    protected._exclusive(root / 'policy-binding.json', canonical({'policy_sha256': policy.sha256}))
    with policy.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0] >= 10000: _fail('adoption_store_capacity')
        db.execute('INSERT INTO jobs(id,root,manifest_sha256,status) VALUES (?,?,?,?)',
            (manifest['operation_id'], str(root), digest(manifest), 'prepared'))
        db.execute('INSERT INTO adoption_operations(operation_id,manifest_sha256,verification_id) VALUES (?,?,?)',
            (manifest['operation_id'], digest(manifest), manifest['verification_operation_id']))
        for scope in service._scopes(manifest): db.execute('INSERT INTO ownership VALUES (?,?)', (scope, manifest['operation_id']))
        policy.event(db, manifest['operation_id'], 'adoption_prepared', {'manifest_sha256': digest(manifest),
            'scope': 'state_only_import_then_one_read_only_first_plan', 'graph_mutation_authorized': False})
        db.execute('COMMIT')
    protected._sync(policy.root)
    return AdoptionJob(root, policy_path).status()


class AdoptionRuntime:
    def __init__(self, seal, *, profile, run, storage, binding, credentials, upstream, certificate,
            private_key, state_contract, ownership, provider):
        from intune_iac.worker_adoption_state import NativeAdoptionStateContract
        from intune_iac.worker_adoption_provider import NativeAdoptionProviderAdapter
        if (seal is not _SEAL or type(self) is not AdoptionRuntime or type(run) is not service.ControllerBinding
                or run.kind != 'run' or type(storage) is not service.ControllerBinding or storage.kind != 'storage'
                or type(credentials) is not broker.BrokerCredentials or credentials.binding is not binding
                or type(state_contract) is not NativeAdoptionStateContract or type(ownership) is not OwnershipAdmission
                or type(provider) is not NativeAdoptionProviderAdapter): _fail('adoption_runtime_capability_required')
        self.profile, self.run, self.storage, self.binding, self.credentials = profile, run, storage, binding, credentials
        self.upstream, self.certificate, self.private_key = upstream, certificate, private_key
        self.state_contract, self.ownership, self.provider = state_contract, ownership, provider
        self.pid = os.getpid()
    def __reduce_ex__(self, protocol): raise TypeError('Adoption runtime cannot be serialized.')
    def __repr__(self): return '<AdoptionRuntime redacted>'
    def check(self, manifest, *, verification=False):
        if self.pid != os.getpid() or self.profile != manifest['profile']: _fail('adoption_runtime_profile')
        live = self.profile == 'azure_public_pilot'
        if type(self.binding) is not (ib.LiveIdentityBinding if live else ib.LaboratoryIdentityBinding): _fail('adoption_identity_capability')
        if type(self.upstream) is not (broker.NativeUpstream if live else broker.LaboratoryUpstream): _fail('adoption_transport_capability')
        self.run.check(manifest['run_binding_sha256']); self.storage.check(manifest['storage_binding_sha256'])
        self.binding.assert_fresh(manifest['identity_binding_sha256'])
        if self.state_contract.binding() != manifest['state_contract'] or self.provider.binding() != manifest['provider_binding']:
            _fail('adoption_runtime_content_changed')
        if self.ownership.binding() != manifest['ownership_binding']: _fail('adoption_ownership_changed')
        policy = manifest['verification_broker_policy'] if verification else manifest['broker_policy']
        broker.validate_policy(policy, **({} if verification else {'adoption_contract': self.state_contract}))
        self.credentials.check(policy, **({} if verification else {'adoption_contract': self.state_contract}))
        identity, target = self.binding.backend_configuration(self.credentials.backend_credential)
        backend = manifest['provider_binding']['backend']
        if asdict(identity) != backend['identity'] or asdict(target) != backend['backend']:
            _fail('adoption_backend_identity')
        spec = service._host_spec(manifest['verification_host_spec'] if verification else manifest['host_spec'])
        key = _private(self.private_key)
        for spec_key in ('host_spec', 'verification_host_spec'):
            declared = service._host_spec(manifest[spec_key])
            for directory in (declared.source_root, declared.control_root, declared.job_root, declared.broker_root):
                if key == Path(directory) or Path(directory) in key.parents: _fail('adoption_private_key_worker_visible')
            if any(key == Path(tool.path) for tool in declared.tools): _fail('adoption_private_key_worker_visible')
        if host._hash_file(self.certificate, 1024 * 1024) != spec.broker_ca_sha256:
            _fail('adoption_tls_certificate_changed')


def laboratory_runtime(**kwargs):
    return AdoptionRuntime(_SEAL, profile='native_docker_laboratory_protocol', **kwargs)


def live_runtime(**kwargs):
    ib.require_live_binding(kwargs.get('binding'))
    return AdoptionRuntime(_SEAL, profile='azure_public_pilot', upstream=broker.NativeUpstream(), **kwargs)


def _inputs(manifest, runtime, *, verification=False):
    spec = service._host_spec(manifest['verification_host_spec'] if verification else manifest['host_spec'])
    for path, expected, generated in ((spec.source_root, spec.source_sha256, runtime.provider.source_files()),
            (spec.control_root, spec.control_sha256, runtime.provider.control_files('first-plan' if verification else 'import', credentials=runtime.credentials))):
        actual = host.directory_binding(path)
        if actual['sha256'] != expected: _fail('adoption_input_changed')
        expected_files = dict(generated)
        if path == spec.control_root: expected_files['broker-ca.pem'] = _private(runtime.certificate).read_bytes()
        if set(actual['files']) != set(expected_files): _fail('adoption_generated_payload_changed')
        for name, raw in expected_files.items():
            if actual['files'][name]['sha256'] != hashlib.sha256(raw).hexdigest(): _fail('adoption_generated_payload_changed')
    for path in (spec.job_root, spec.broker_root):
        if list(_private(path, directory=True).iterdir()): _fail('adoption_fresh_host_required')
    return spec


class AdoptionPermit:
    def __init__(self, seal, job, payload, runtime, verification=False):
        if seal is not _SEAL or type(runtime) is not AdoptionRuntime: _fail('adoption_permit_required')
        self.job, self.payload, self.runtime, self.verification = job, payload, runtime, verification
        self.active, self.pid = True, os.getpid()
    def __reduce_ex__(self, protocol): raise TypeError('Adoption permits cannot be serialized.')
    def check_active(self):
        if not self.active or self.pid != os.getpid(): _fail('adoption_permit_inactive')
        self.job._check()
        if int(time.time()) >= self.payload['expires_at']: _fail('adoption_signature_expired')
        with self.job.policy.connection() as db:
            row = db.execute('SELECT status,cancelled,dispatches FROM jobs WHERE id=?', (self.job.identifier,)).fetchone()
            consumed = db.execute('SELECT manifest_sha256 FROM consumed WHERE operation_id=?', (self.job.identifier,)).fetchone()
            owners = sorted(item[0] for item in db.execute('SELECT scope FROM ownership WHERE job=?', (self.job.identifier,)))
            revoked = db.execute('SELECT 1 FROM revoked WHERE issuer=? AND key_id=?', (self.payload['issuer'], self.payload['key_id'])).fetchone()
            phase = db.execute('SELECT verification_dispatches,verification_status FROM adoption_operations WHERE operation_id=?', (self.job.identifier,)).fetchone()
        expected = 'verification_running' if self.verification else 'running'
        if (row != (expected, 0, 1) or consumed != (self.job.sha256,) or owners != service._scopes(self.job.manifest)
                or revoked or self.verification and phase != (1, 'running')): _fail('adoption_permit_inactive')
        self.runtime.check(self.job.manifest, verification=self.verification)


class AdoptionJob:
    def __init__(self, job_root, policy_path):
        self.policy = service.ServicePolicy(policy_path); self.root = _private(job_root, directory=True)
        if self.root.parent != self.policy.jobs_root: _fail('adoption_job_outside_policy')
        self.manifest = service._bounded_private_json(self.root / 'manifest.json')
        if self.manifest.get('schema_version') != VERSION: _fail('adoption_job_domain')
        self.sha256, self.identifier = digest(self.manifest), self.manifest.get('operation_id')
        self._completion = None
        self._check(expiry=False)
    def _check(self, *, expiry=True):
        self.policy.check()
        if digest(self.manifest) != self.sha256 or digest(service._bounded_private_json(self.root / 'manifest.json')) != self.sha256:
            _fail('adoption_job_changed')
        if expiry:
            if (self.sha256 not in self.policy.admitted or service._bounded_private_json(self.root / 'policy-binding.json') != {'policy_sha256': self.policy.sha256}):
                _fail('adoption_admission_changed')
            validate_manifest(self.manifest)
        with self.policy.connection() as db:
            row = db.execute('SELECT root,manifest_sha256 FROM jobs WHERE id=?', (self.identifier,)).fetchone()
            kind = db.execute('SELECT manifest_sha256,verification_id FROM adoption_operations WHERE operation_id=?', (self.identifier,)).fetchone()
        if row != (str(self.root), self.sha256) or kind != (self.sha256, self.manifest['verification_operation_id']):
            _fail('adoption_job_not_registered')
    def review(self):
        self._check(expiry=False)
        return {'manifest': self.manifest, 'manifest_sha256': self.sha256, 'signature_domain_hex': SIGNATURE_DOMAIN.hex(),
            'approval_schema': APPROVAL_VERSION, 'authority': 'independent_external_signer_required',
            'execution_authorized': False, 'graph_mutation_authorized': False, 'production_authorized': False}
    def status(self):
        self._check(expiry=False)
        with self.policy.connection() as db:
            row = db.execute('SELECT status,cancelled,dispatches,outcome FROM jobs WHERE id=?', (self.identifier,)).fetchone()
            phase = db.execute('SELECT verification_dispatches,verification_status,verification_outcome FROM adoption_operations WHERE operation_id=?', (self.identifier,)).fetchone()
            events = [{'sequence': r[0], 'kind': r[1], 'payload': parse_json(r[2]), 'created_at': r[3]} for r in
                db.execute('SELECT sequence,kind,payload,created_at FROM events WHERE job=? ORDER BY sequence', (self.identifier,))]
            transcript_table = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='approval_transcripts'").fetchone()
            transcript = db.execute('SELECT receipt_sha256 FROM approval_transcripts WHERE operation_id=?', (self.identifier,)).fetchone() if transcript_table else None
        return {'operation_id': self.identifier, 'manifest_sha256': self.sha256, 'operation_kind': VERSION,
            'status': row[0], 'cancel_requested': bool(row[1]), 'dispatches': row[2],
            'outcome': parse_json(row[3]) if row[3] else None, 'verification_dispatches': phase[0],
            'verification_status': phase[1], 'verification_outcome': parse_json(phase[2]) if phase[2] else None,
            'events': events, 'profile': self.manifest['profile'], 'production_authorized': False,
            'approval_transcript': {'status': 'retained' if transcript else 'not_retained', 'sha256': transcript[0] if transcript else None},
            'graph_mutation_authorized': False, 'reattach_dispatches': False,
            'implementation_matches_reviewed': self.manifest.get('implementation_files') == service.implementation_binding(),
            'implementation_comparison_scope': 'current_observer_process_against_reviewed_controller',
            'approved_controller_runtime_re_attested': False,
            'policy_matches_reviewed': service._bounded_private_json(self.root / 'policy-binding.json') == {'policy_sha256': self.policy.sha256}}
    def attach(self): return self.status()
    def cancel(self):
        self._check(expiry=False)
        with self.policy.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute("UPDATE jobs SET cancelled=1,status=CASE WHEN dispatches=0 THEN 'cancelled_before_dispatch' ELSE status END WHERE id=?", (self.identifier,))
            db.execute('DELETE FROM ownership WHERE job=? AND EXISTS(SELECT 1 FROM jobs WHERE id=? AND dispatches=0)', (self.identifier, self.identifier))
            self.policy.event(db, self.identifier, 'adoption_cancel_requested', {'dispatch_replayed': False}); db.execute('COMMIT')
        return self.status()
    def recover(self):
        self._check(expiry=False)
        with self.policy.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT controller_pid,controller_start,status,dispatches FROM jobs WHERE id=?', (self.identifier,)).fetchone()
            db.execute('UPDATE jobs SET cancelled=1 WHERE id=?', (self.identifier,))
            self.policy.event(db, self.identifier, 'adoption_recovery_cancel_requested', {'import_replayed': False}); db.execute('COMMIT')
        if row[0] is not None and service._controller_identity(row[0]) == row[1]: _fail('adoption_cleanup_owner_active')
        records = {}
        for name in ('host-run', 'verification-host-run'):
            root = self.root / name
            records[name] = host.recover(root) if (root / 'journal.json').exists() else {'container_never_recorded': True}
        with self.policy.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute("UPDATE jobs SET controller_pid=NULL,controller_start=NULL,status=CASE WHEN dispatches=0 THEN 'cancelled_before_dispatch' WHEN status IN ('running','verification_running') THEN 'outcome_unknown' ELSE status END WHERE id=?", (self.identifier,))
            if row[3] == 0: db.execute('DELETE FROM ownership WHERE job=?', (self.identifier,))
            self.policy.event(db, self.identifier, 'adoption_recovery_no_replay', {'hosts': records,
                'native_lease_release_authorized': False, 'import_replayed': False}); db.execute('COMMIT')
        return self.status()

    def run(self, signed_receipt, *, runtime):
        """Consume the import approval once, before any container or lease call."""
        receipt = _copy(signed_receipt)
        self._check()
        if threading.current_thread() is not threading.main_thread(): _fail('adoption_main_thread_required')
        if type(runtime) is not AdoptionRuntime: _fail('adoption_runtime_capability_required')
        runtime.check(self.manifest); spec = _inputs(self.manifest, runtime)
        payload = _verify(self.policy, self.manifest, receipt)
        receipt_raw = canonical(receipt); receipt_sha256 = hashlib.sha256(receipt_raw).hexdigest()
        # Real backend GET + identity re-observation, before consuming authority.
        # The content-only state contract and local ownership scan cannot replace it.
        baseline = _backend_observation(self, runtime, self.root / ('baseline-' + uuid.uuid4().hex), baseline=True)
        with self.policy.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT status,cancelled,dispatches FROM jobs WHERE id=?', (self.identifier,)).fetchone()
            owners = sorted(r[0] for r in db.execute('SELECT scope FROM ownership WHERE job=?', (self.identifier,)))
            if row != ('prepared', 0, 0) or owners != service._scopes(self.manifest): _fail('adoption_not_replayable')
            if db.execute('SELECT 1 FROM revoked WHERE issuer=? AND key_id=?', (payload['issuer'], payload['key_id'])).fetchone():
                _fail('adoption_key_revoked')
            db.execute('INSERT INTO consumed VALUES (?,?,?,?)', (payload['issuer'], payload['nonce'], self.identifier, self.sha256))
            db.execute('INSERT INTO approval_transcripts VALUES (?,?,?,?)',
                (self.identifier, receipt_raw.decode(), receipt_sha256, int(time.time())))
            identity = service._controller_identity(os.getpid())
            if identity is None: _fail('adoption_controller_identity_unavailable')
            db.execute("UPDATE jobs SET status='running',dispatches=1,controller_pid=?,controller_start=? WHERE id=?",
                (os.getpid(), identity, self.identifier))
            self.policy.event(db, self.identifier, 'adoption_dispatch_consumed', {'manifest_sha256': self.sha256,
                'signature_domain_hex': SIGNATURE_DOMAIN.hex(), 'baseline': baseline.facts(),
                'approval_receipt_sha256': receipt_sha256,
                'graph_mutation_authorized': False}); db.execute('COMMIT')
        # Preserve the exact signed receipt after durable consumption; recording
        # failure is an uncertain dispatch boundary, never permission to retry.
        try: protected._exclusive(self.root / 'approval.json', receipt_raw)
        except BaseException as error:
            _record_undispatched_failure(self, error)
            raise
        return self._dispatch(payload, runtime, spec, verification=False)

    def _dispatch(self, payload, runtime, spec, *, verification):
        permit = AdoptionPermit(_SEAL, self, payload, runtime, verification)
        policy = self.manifest['verification_broker_policy'] if verification else self.manifest['broker_policy']
        prefix = 'verification-' if verification else ''
        server = thread = watchdog = transport = result = primary = interruption = None
        stopped = threading.Event(); shutdown_failures = []; recording_failures = []; watchdog_fault = []
        recording_uncertain = False; shutdown_interrupted = False
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
                if value.is_alive(): _fail('adoption_shutdown_thread_active')
            except BaseException as error: failed(error, phase, shutdown_failures)
        try:
            permit.check_active()
            guard = (broker.live_guard(self.manifest['execution_binding_sha256'], binding=runtime.binding, recheck=permit.check_active)
                if self.manifest['profile'] == 'azure_public_pilot' else
                broker.laboratory_guard(self.manifest['execution_binding_sha256'], permit.check_active))
            transport = broker.EgressBroker(policy, journal=self.root / (prefix + 'broker.sqlite3'), guard=guard,
                upstream=runtime.upstream, credentials=runtime.credentials,
                **({} if verification else {'adoption_contract': runtime.state_contract,
                    'state_contracts': {route['id']: runtime.state_contract for route in policy['routes']
                        if route['effect'] == 'state_write'}}))
            server = broker.UnixBrokerServer(Path(spec.broker_root) / 'egress.sock', transport,
                certificate=runtime.certificate, private_key=runtime.private_key)
            thread = threading.Thread(target=server.serve, daemon=True, name='intune-adoption-broker'); thread.start()
            permit.check_active()
            def monitor():
                while not stopped.wait(0.2):
                    try: permit.check_active()
                    except BaseException as error:
                        watchdog_fault.append(getattr(error, 'code', type(error).__name__))
                        if not stopped.is_set(): os.kill(os.getpid(), signal.SIGINT)
                        return
            watchdog = threading.Thread(target=monitor, daemon=True, name='intune-adoption-watchdog'); watchdog.start()
            result = host.launch(spec, self.root / (prefix + 'host-run'))
        except BaseException as error:
            primary = error
            if isinstance(error, (KeyboardInterrupt, SystemExit)): interruption = error
            try:
                path = self.root / (prefix + 'host-run') / 'receipt.json'
                if path.exists(): result = service._bounded_private_json(path)
            except BaseException as error: failed(error, 'host_receipt_read', recording_failures)
        finally:
            stopped.set(); permit.active = False
            finish_thread(watchdog, 35, 'watchdog_join')
            if server is not None:
                try: server.close()
                except BaseException as error: failed(error, 'broker_close', shutdown_failures)
            finish_thread(thread, 12, 'broker_join')
            recovery = None
            if transport is not None:
                try:
                    record = transport.native_recovery_record()
                    protected._exclusive(self.root / (prefix + 'native-lease-recovery.json'), canonical(record))
                    recovery = {'sha256': digest(record), 'automatic_release_authorized': False}
                except BaseException as error: failed(error, 'native_recovery_archive', recording_failures)
            complete = bool(result and result.get('status') == 'complete' and primary is None and not shutdown_failures)
            status = ('first_plan_host_completed_unverified' if verification else 'import_host_completed_unverified') if complete else 'outcome_unknown'
            outcome = {'host': result, 'primary_error': getattr(primary, 'code', type(primary).__name__) if primary else None,
                'operation_outcome': status, 'watchdog_error': watchdog_fault[0] if watchdog_fault else None,
                'shutdown_failures': shutdown_failures, 'recording_failures': recording_failures,
                'authority_recording': 'committed', 'native_backend_recovery': recovery,
                'graph_mutation_authorized': False, 'independent_state_graph_and_plan': 'required',
                'production_authorized': False, 'import_replay_authorized': False}
            try:
                with self.policy.connection() as db:
                    db.execute('BEGIN IMMEDIATE')
                    if verification:
                        db.execute('UPDATE adoption_operations SET verification_status=?,verification_outcome=? WHERE operation_id=?',
                            (status, canonical(outcome).decode(), self.identifier))
                        # Preserve the complete original import outcome.
                        db.execute('UPDATE jobs SET status=?,controller_pid=NULL,controller_start=NULL WHERE id=?', (status, self.identifier))
                    else:
                        db.execute('UPDATE jobs SET status=?,outcome=?,controller_pid=NULL,controller_start=NULL WHERE id=?',
                            (status, canonical(outcome).decode(), self.identifier))
                    self.policy.event(db, self.identifier, prefix + 'adoption_worker_stopped', outcome); db.execute('COMMIT')
            except BaseException as error:
                recording_uncertain = True; failed(error, 'authority_outcome', recording_failures)
                outcome['authority_recording'] = 'failed_or_uncertain'
                outcome['primary_error'] = getattr(primary, 'code', type(primary).__name__)
            try: protected._exclusive(self.root / (prefix + 'adoption-receipt.json'), canonical(outcome))
            except BaseException as error:
                failed(error, 'receipt_archive', recording_failures)
                try:
                    with self.policy.connection() as db:
                        self.policy.event(db, self.identifier, prefix + 'adoption_archive_failed', {
                            'error': getattr(error, 'code', type(error).__name__), 'known_outcome_preserved': not recording_uncertain,
                            'import_replay_authorized': False})
                except BaseException as error: recording_uncertain = True; failed(error, 'archive_failure_event', recording_failures)
        if primary is not None: primary.adoption_failure_record = outcome
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

    def verify_first_plan(self, *, runtime):
        """One preapproved Plan-only native run, never import or apply replay."""
        self._check()
        if threading.current_thread() is not threading.main_thread(): _fail('adoption_main_thread_required')
        if type(runtime) is not AdoptionRuntime: _fail('adoption_runtime_capability_required')
        runtime.check(self.manifest, verification=True)
        spec = _inputs(self.manifest, runtime, verification=True)
        with self.policy.connection() as db:
            transcript = db.execute('SELECT receipt_json,receipt_sha256 FROM approval_transcripts WHERE operation_id=?', (self.identifier,)).fetchone()
        if transcript is None or hashlib.sha256(transcript[0].encode()).hexdigest() != transcript[1]:
            _fail('adoption_approval_transcript_missing_or_changed')
        receipt = _copy(parse_json(transcript[0]))
        if canonical(receipt).decode() != transcript[0] or service._bounded_private_json(self.root / 'approval.json') != receipt:
            _fail('adoption_approval_transcript_missing_or_changed')
        payload = _verify(self.policy, self.manifest, receipt)
        state = _backend_observation(self, runtime, self.root / ('before-first-plan-' + uuid.uuid4().hex), baseline=False)
        with self.policy.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT status,cancelled,dispatches,outcome,controller_pid FROM jobs WHERE id=?', (self.identifier,)).fetchone()
            phase = db.execute('SELECT verification_dispatches,verification_status FROM adoption_operations WHERE operation_id=?', (self.identifier,)).fetchone()
            owners = sorted(r[0] for r in db.execute('SELECT scope FROM ownership WHERE job=?', (self.identifier,)))
            consumed = db.execute('SELECT manifest_sha256 FROM consumed WHERE operation_id=?', (self.identifier,)).fetchone()
            if (row[0] != 'import_host_completed_unverified' or row[1:3] != (0, 1) or row[4] is not None
                    or phase != (0, 'not_started') or owners != service._scopes(self.manifest) or consumed != (self.sha256,)):
                _fail('adoption_first_plan_not_ready')
            previous = parse_json(row[3]) if row[3] else None
            if not previous or previous.get('host', {}).get('cleanup', {}).get('removed') is not True:
                _fail('adoption_host_cleanup_unconfirmed')
            identity = service._controller_identity(os.getpid())
            if identity is None: _fail('adoption_controller_identity_unavailable')
            db.execute("UPDATE adoption_operations SET verification_dispatches=1,verification_status='running' WHERE operation_id=?", (self.identifier,))
            db.execute("UPDATE jobs SET status='verification_running',controller_pid=?,controller_start=? WHERE id=?", (os.getpid(), identity, self.identifier))
            self.policy.event(db, self.identifier, 'adoption_first_plan_consumed', {'manifest_sha256': self.sha256,
                'receiving_state': state.facts(), 'state_content_write_authorized': False}); db.execute('COMMIT')
        result = self._dispatch(payload, runtime, spec, verification=True)
        if result['status'] != 'first_plan_host_completed_unverified': return result
        completion = _qualify_completion(self, runtime)
        self._completion = completion
        return self.reconcile(completion)

    def completion(self):
        """Return only this process's fresh sealed proof; reopening cannot mint it."""
        expected = LiveAdoptionCompletion if self.manifest['profile'] == 'azure_public_pilot' else LaboratoryAdoptionCompletion
        if type(self._completion) is not expected: _fail('adoption_completion_not_held')
        self._completion.verified(self)
        return self._completion

    def reconcile(self, completion):
        self._check(expiry=False)
        expected = LiveAdoptionCompletion if self.manifest['profile'] == 'azure_public_pilot' else LaboratoryAdoptionCompletion
        if type(completion) is not expected: _fail('adoption_completion_capability_required')
        facts = completion.verified(self)
        with self.policy.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT status,dispatches,outcome,controller_pid FROM jobs WHERE id=?', (self.identifier,)).fetchone()
            phase = db.execute('SELECT verification_dispatches,verification_status,verification_outcome FROM adoption_operations WHERE operation_id=?', (self.identifier,)).fetchone()
            owners = sorted(r[0] for r in db.execute('SELECT scope FROM ownership WHERE job=?', (self.identifier,)))
            consumed = db.execute('SELECT manifest_sha256 FROM consumed WHERE operation_id=?', (self.identifier,)).fetchone()
            if (row[0] != 'first_plan_host_completed_unverified' or row[1] != 1 or row[3] is not None
                    or phase[:2] != (1, 'first_plan_host_completed_unverified')
                    or owners != service._scopes(self.manifest) or consumed != (self.sha256,)):
                _fail('adoption_reconciliation_not_ready')
            prior = parse_json(row[2]); verification = parse_json(phase[2])
            if any(item.get('host', {}).get('cleanup', {}).get('removed') is not True for item in (prior, verification)):
                _fail('adoption_host_cleanup_unconfirmed')
            report = {'previous_import_outcome': prior, 'first_plan_outcome': verification, 'independent_completion': facts,
                'reservation_released': True, 'import_replayed': False, 'graph_mutated': False,
                'endpoint_effectiveness': 'unestablished', 'production_approved': False}
            db.execute("UPDATE jobs SET status='adopted_verified',outcome=? WHERE id=?", (canonical(report).decode(), self.identifier))
            db.execute('DELETE FROM ownership WHERE job=?', (self.identifier,))
            self.policy.event(db, self.identifier, 'adoption_reconciled', report); db.execute('COMMIT')
        protected._sync(self.policy.root)
        try: protected._exclusive(self.root / ('adoption-reconciliation-' + uuid.uuid4().hex + '.json'), canonical(report))
        except BaseException as error:
            try:
                with self.policy.connection() as db:
                    self.policy.event(db, self.identifier, 'adoption_reconciliation_archive_failed', {
                        'error': getattr(error, 'code', type(error).__name__), 'known_outcome_preserved': True, 'import_replay_authorized': False})
            except BaseException as secondary:
                _secondary(error, secondary, 'archive-failure recording')
            raise
        return self.status()


def _record_undispatched_failure(job, primary):
    facts = {'status': 'outcome_unknown', 'primary_error': getattr(primary, 'code', type(primary).__name__),
        'host_not_started_by_this_controller': True, 'import_replay_authorized': False, 'ownership_retained': True}
    try:
        with job.policy.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute("UPDATE jobs SET status='outcome_unknown',outcome=?,controller_pid=NULL,controller_start=NULL WHERE id=?", (canonical(facts).decode(), job.identifier))
            job.policy.event(db, job.identifier, 'adoption_approval_archive_failed', facts); db.execute('COMMIT')
    except BaseException as secondary:
        _secondary(primary, secondary, 'authority recording')


class _BackendObservation:
    def __init__(self, seal, job, runtime, facts, root, projection):
        if seal is not _SEAL: _fail('adoption_backend_capability_required')
        self._job, self._runtime, self._facts, self._root, self._projection = job, runtime, _copy(facts), root, projection
        self._sha, self._pid, self._observed = digest(facts), os.getpid(), time.monotonic()
    def __reduce_ex__(self, protocol): raise TypeError('Authenticated adoption observations cannot be serialized.')
    def facts(self):
        if (self._pid != os.getpid() or digest(self._facts) != self._sha or not 0 <= time.monotonic() - self._observed <= 30):
            _fail('adoption_backend_observation_changed_or_stale')
        self._runtime.binding.assert_fresh(self._job.manifest['identity_binding_sha256'])
        self._runtime.storage.check(self._job.manifest['storage_binding_sha256'])
        if hashlib.sha256(_private(self._root / 'state.raw').read_bytes()).hexdigest() != self._facts['state']['sha256']:
            _fail('adoption_backend_artifact_changed')
        if self._projection is not None:
            projected = self._projection.verified()
            if asdict(projected['state_revision']) != self._facts['state']: _fail('adoption_backend_projection_changed')
        return _copy(self._facts)


def _backend_observation(job, runtime, output, *, baseline):
    """Actual fixed Azure receiving GET, never supplied response/boolean authority."""
    runtime.check(job.manifest)
    identity, target = runtime.binding.backend_configuration(runtime.credentials.backend_credential)
    if baseline: runtime.binding.recheck()
    endpoint = urlsplit(target.blob_endpoint)
    if (endpoint.scheme != 'https' or endpoint.port not in (None, 443) or endpoint.path not in ('', '/')
            or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment): _fail('adoption_backend_target')
    root = Path(output).absolute(); _private(root.parent, directory=True); root.mkdir(mode=0o700, exist_ok=False)
    path = '/' + target.container + '/' + target.key; token = None; primary = None
    protected._exclusive(root / 'request.json', canonical({'schema_version': 'adoption-backend-read/1',
        'operation_id': job.identifier, 'manifest_sha256': job.sha256, 'method': 'GET', 'host': endpoint.hostname,
        'path': path, 'phase': 'baseline' if baseline else 'successor', 'credential_persisted': False}))
    try:
        token = runtime.binding.backend_storage_token(runtime.credentials.backend_credential, timeout=10)
        response = runtime.upstream.request(endpoint.hostname, 'GET', path,
            {'authorization': 'Bearer ' + token._get(), 'x-ms-version': '2023-11-03', 'accept': 'application/json',
             'accept-encoding': 'identity'}, b'', timeout=10)
        from intune_iac.worker_lease_recovery import _response
        headers = _response(response)
        protected._exclusive(root / 'state.raw', response.body)
        if (response.status != 200 or headers.get('content-length') != str(len(response.body))
                or headers.get('x-ms-lease-status') != 'unlocked' or headers.get('x-ms-lease-state') != 'available'
                or any(key.startswith('x-ms-meta-') and value for key, value in headers.items())):
            _fail('adoption_backend_unavailable_locked_or_metadata')
        revision = StateRevision.observe(response.body, etag=headers.get('etag'))
        projection = None
        if baseline:
            if asdict(revision) != job.manifest['state_contract']['baseline_revision']:
                _fail('adoption_authenticated_baseline_changed')
        else:
            projection = runtime.state_contract.observe_successor(response.body, revision=revision)
            projected = projection.verified()
            if projected['contract_sha256'] != digest(job.manifest['state_contract']): _fail('adoption_readback_contract_changed')
        runtime.binding.assert_fresh(job.manifest['identity_binding_sha256'])
        facts = {'schema_version': 'authenticated-adoption-backend-observation/1', 'operation_id': job.identifier,
            'manifest_sha256': job.sha256, 'identity_binding_sha256': job.manifest['identity_binding_sha256'],
            'identity': asdict(identity), 'backend': asdict(target), 'state': asdict(revision),
            'profile': runtime.profile, 'backend_state_authenticated': True, 'backend_unlocked': True,
            'terraform_metadata_empty': True, 'state_contract_sha256': digest(job.manifest['state_contract']),
            'graph_capture_sha256': projected['capture'].verified()[0]['capture_sha256'] if projection else None,
            'observed_at': time.time(), 'execution_authorized': False, 'production_approved': False}
        protected._exclusive(root / 'receipt.json', canonical(facts))
        return _BackendObservation(_SEAL, job, runtime, facts, root, projection)
    except BaseException as error:
        primary = error
        try: protected._exclusive(root / 'failure.json', canonical({'error': getattr(error, 'code', type(error).__name__),
            'scope_released': False, 'import_replayed': False}))
        except BaseException as secondary: _secondary(error, secondary, 'readback recording')
        raise
    finally:
        if token is not None:
            try: token.close()
            except BaseException as error:
                if primary is None: raise
                _secondary(primary, error, 'token cleanup')


class _AdoptionCompletion:
    def __init__(self, seal, job, state, facts, artifacts):
        if seal is not _SEAL or type(self) not in (LiveAdoptionCompletion, LaboratoryAdoptionCompletion):
            _fail('adoption_completion_constructor_forbidden')
        self._sha, self._state, self._facts, self._artifacts = job.sha256, state, _copy(facts), artifacts
        self._digest, self._pid = digest(facts), os.getpid()
    def __reduce_ex__(self, protocol): raise TypeError('Adoption completion cannot be serialized.')
    def verified(self, job):
        if self._pid != os.getpid() or job.sha256 != self._sha or digest(self._facts) != self._digest:
            _fail('adoption_completion_changed')
        if self._state.facts() != self._facts['receiving_state']: _fail('adoption_completion_state_changed')
        for path, expected in self._artifacts.items():
            if host._hash_file(Path(path), 32 * 1024 * 1024) != expected: _fail('adoption_completion_artifact_changed')
        return _copy(self._facts)
    def captured_observation(self, job):
        """Exact fresh proof capture for publication, never rehydrated from JSON."""
        self.verified(job)
        from intune_iac.observation_reader import CapturedObservation
        capture = self._state._projection.verified()['capture']
        if type(capture) is not CapturedObservation: _fail('adoption_completion_capture_required')
        return capture


class LiveAdoptionCompletion(_AdoptionCompletion): pass
class LaboratoryAdoptionCompletion(_AdoptionCompletion): pass


def _qualify_completion(job, runtime):
    from intune_iac import worker_adoption_provider as provider
    spec = service._host_spec(job.manifest['verification_host_spec'])
    paths = [Path(spec.job_root) / value.removeprefix('/job/') for value in
        (provider.PLAN_PATH, provider.PLAN_JSON_PATH, provider.PLAN_EXIT_PATH)]
    artifacts = {str(path): host._hash_file(path, 32 * 1024 * 1024) for path in paths}
    if _private(paths[2]).read_bytes() != b'0\n': _fail('adoption_first_plan_changes_or_failure')
    plan = parse_json(_private(paths[1]).read_bytes())
    if (type(plan) is not dict or plan.get('format_version') != '1.2' or plan.get('terraform_version') != '1.13.1'
            or plan.get('errored') is True or plan.get('resource_drift') not in (None, [])
            or type(plan.get('resource_changes')) is not list or len(plan['resource_changes']) != 1
            or plan['resource_changes'][0].get('address') != job.manifest['provider_binding']['resource_address']
            or plan['resource_changes'][0].get('change', {}).get('actions') != ['no-op']
            or any(change.get('actions') != ['no-op'] for change in plan.get('output_changes', {}).values())):
        _fail('adoption_first_plan_not_converged')
    state = _backend_observation(job, runtime, job.root / ('after-first-plan-' + uuid.uuid4().hex), baseline=False)
    facts = {'schema_version': 'native-adoption-independent-completion/1', 'operation_id': job.identifier,
        'manifest_sha256': job.sha256, 'receiving_state': state.facts(), 'native_first_plan_exit_code': 0,
        'native_first_plan_sha256': artifacts[str(paths[0])], 'native_first_plan_json_sha256': artifacts[str(paths[1])],
        'first_plan_no_change': True, 'import_replayed': False, 'graph_mutation_authorized': False,
        'management_mapping_status': job.manifest['state_contract']['management_mapping_status'],
        'management_mapping_blockers': job.manifest['state_contract']['management_mapping_blockers'],
        'endpoint_effectiveness': 'unestablished', 'production_approved': False}
    cls = LiveAdoptionCompletion if runtime.profile == 'azure_public_pilot' else LaboratoryAdoptionCompletion
    return cls(_SEAL, job, state, facts, artifacts)
