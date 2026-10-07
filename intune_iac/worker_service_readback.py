"""Independent authenticated backend GET plus sealed intended Graph completion.

No imported state/report can release service ownership. Laboratory TLS and native
fixed-service observations create distinct capability types and evidence scopes.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import os
from pathlib import Path
import time
from urllib.parse import urlsplit

from . import identity_binding as ib, protected, worker_broker as broker
from .azure_backend import NativeStateWriteContract, StateRevision
from .io import AppError, canonical, digest, parse_json
from .provider_journey import _private
from .worker_precondition import LiveGraphCompletion, LaboratoryGraphCompletion
from .worker_state import ComputedNativeStateWriteContract
from .worker_state_recovery import DescriptionRecoveryStateWriteContract

_SEAL = object()
MAX_BYTES = 16 * 1024 * 1024


def _fail(code):
    raise AppError(code, 'Independent service readback did not establish the exact intended policy, assignments and backend state.')


def _completion(manifest, completion):
    expected = LiveGraphCompletion if manifest['profile'] == 'azure_public_pilot' else LaboratoryGraphCompletion
    if type(completion) is not expected: _fail('service_readback_graph_capability')
    facts = completion.verified()
    if (facts['execution_binding_sha256'] != manifest['execution_binding_sha256']
            or facts['precondition_binding_sha256'] != digest(manifest['precondition_binding'])
            or facts['approved_projection_sha256'] != manifest['precondition_binding']['approved_projection_sha256']
            or facts['tenant_id'] != manifest['tenant_id'] or manifest['object_ids'] != [facts['object_id']]):
        _fail('service_readback_graph_binding')
    return facts


class _Readback:
    __slots__ = ('_manifest_sha256', '_completion', '_facts', '_digest', '_pid', '_observed', '_root')
    def __init__(self, seal, manifest, completion, facts, root):
        if seal is not _SEAL or type(self) not in (LiveServiceReadback, LaboratoryServiceReadback):
            _fail('service_readback_constructor_forbidden')
        self._manifest_sha256, self._completion = digest(manifest), completion
        self._facts = parse_json(canonical(facts)); self._digest = digest(self._facts)
        self._pid, self._observed, self._root = os.getpid(), time.monotonic(), root
    def __repr__(self): return '<' + type(self).__name__ + ' redacted>'
    def __reduce_ex__(self, protocol): raise TypeError('Service readback cannot be serialized.')
    def verified(self, manifest):
        if (self._pid != os.getpid() or digest(manifest) != self._manifest_sha256
                or digest(self._facts) != self._digest or not 0 <= time.monotonic() - self._observed <= 30):
            _fail('service_readback_changed_or_stale')
        facts = _completion(manifest, self._completion)
        if facts['capture_sha256'] != self._facts['graph_capture_sha256']:
            _fail('service_readback_graph_binding')
        for name, expected in self._facts['artifacts'].items():
            path = _private(self._root / name)
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                _fail('service_readback_artifact_changed')
        return parse_json(canonical(self._facts))


class LiveServiceReadback(_Readback):
    __slots__ = ()


class LaboratoryServiceReadback(_Readback):
    __slots__ = ()


def _collect(manifest, *, binding, backend_credential, completion, state_contract, upstream, storage, output):
    from .worker_service import ControllerBinding
    live = manifest.get('profile') == 'azure_public_pilot'
    if live:
        ib.require_live_binding(binding)
        if type(upstream) is not broker.NativeUpstream: _fail('service_readback_transport')
    elif (manifest.get('profile') != 'native_docker_laboratory_protocol'
            or type(binding) is not ib.LaboratoryIdentityBinding or type(upstream) is not broker.LaboratoryUpstream):
        _fail('service_readback_transport')
    if type(storage) is not ControllerBinding or storage.kind != 'storage': _fail('service_readback_storage_required')
    storage.check(manifest['storage_binding_sha256'])
    graph = _completion(manifest, completion)
    binding.assert_fresh(manifest['identity_binding_sha256'])
    identity, target = binding.backend_configuration(backend_credential)
    backend = manifest['provider_binding'].get('backend')
    if (type(backend) is not dict or backend.get('identity') != asdict(identity)
            or backend.get('backend') != asdict(target) or digest(backend) != manifest['backend_scope_sha256']):
        _fail('service_readback_backend_binding')
    if type(state_contract) not in (NativeStateWriteContract, ComputedNativeStateWriteContract, DescriptionRecoveryStateWriteContract):
        _fail('service_readback_state_contract')
    contract = state_contract.binding()
    if (len(manifest['state_contracts']) != 1 or contract not in manifest['state_contracts'].values()
            or contract.get('saved_plan_sha256') != manifest['saved_plan_sha256']):
        _fail('service_readback_state_contract')
    endpoint = urlsplit(target.blob_endpoint)
    if (endpoint.scheme != 'https' or not endpoint.hostname or endpoint.path not in ('', '/')
            or endpoint.port not in (None, 443) or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment):
        _fail('service_readback_backend_binding')
    path = '/' + target.container + '/' + target.key
    root = Path(output).absolute()
    if any(item.is_symlink() for item in (root, *root.parents)) or '..' in root.parts: _fail('service_readback_output_unsafe')
    _private(root.parent, directory=True); root.mkdir(mode=0o700, exist_ok=False)
    started = time.time(); token = None
    request = {'schema_version': 'worker-service-readback-attempt/1', 'operation_id': manifest['operation_id'],
        'manifest_sha256': digest(manifest), 'method': 'GET', 'host': endpoint.hostname, 'path': path,
        'graph_capture_sha256': graph['capture_sha256'], 'status': 'started', 'credential_persisted': False}
    protected._exclusive(root / 'request.json', canonical(request))
    try:
        token = binding.backend_storage_token(backend_credential, timeout=10)
        response = upstream.request(endpoint.hostname, 'GET', path,
            {'authorization': 'Bearer ' + token._get(), 'x-ms-version': '2023-11-03', 'accept': 'application/json'},
            b'', timeout=10)
        if (type(response) is not ib.ServiceResponse or type(response.status) is not int
                or type(response.body) is not bytes or len(response.body) > MAX_BYTES
                or type(response.headers) is not tuple or len(response.headers) > 100):
            _fail('service_readback_response_invalid')
        # Preserve independently read bytes even when their content is rejected.
        protected._exclusive(root / 'observed-state.raw', response.body)
        headers = {}
        for pair in response.headers:
            if type(pair) is not tuple or len(pair) != 2 or any(type(item) is not str for item in pair):
                _fail('service_readback_response_invalid')
            name, value = pair[0].lower(), pair[1]
            if name in headers or any(ord(char) < 32 or ord(char) == 127 for char in name + value):
                _fail('service_readback_response_invalid')
            headers[name] = value
        if (response.status != 200 or headers.get('content-encoding') not in (None, 'identity')
                or headers.get('x-ms-lease-status') != 'unlocked' or headers.get('x-ms-meta-terraformlockid') not in (None, '')
                or headers.get('content-length') != str(len(response.body))):
            _fail('service_readback_state_unavailable_or_locked')
        revision = StateRevision.observe(response.body, etag=headers.get('etag'))
        if type(state_contract) in (ComputedNativeStateWriteContract, DescriptionRecoveryStateWriteContract):
            admission = state_contract.admit(response.body, completion=completion)
        else:
            admission = state_contract.admit(response.body)
        binding.assert_fresh(manifest['identity_binding_sha256']); storage.check(manifest['storage_binding_sha256'])
        graph = _completion(manifest, completion)
        facts = {'schema_version': 'worker-service-independent-readback/1', 'operation_id': manifest['operation_id'],
            'manifest_sha256': digest(manifest), 'execution_binding_sha256': manifest['execution_binding_sha256'],
            'evidence_class': 'authenticated_service_state_convergence' if live else 'laboratory_service_state_convergence',
            'graph_capture_sha256': graph['capture_sha256'], 'graph_approved_projection_sha256': graph['approved_projection_sha256'],
            'backend_state': asdict(revision), 'backend_lock_released': True, 'state_admission': admission,
            'observed_at': time.time(), 'started_at': started, 'endpoint_effectiveness': 'unestablished',
            'second_plan_convergence': 'separate_native_plan_evidence_required', 'production_approved': False,
            'artifacts': {'request.json': hashlib.sha256((root / 'request.json').read_bytes()).hexdigest(),
                          'observed-state.raw': hashlib.sha256(response.body).hexdigest()}}
        protected._exclusive(root / 'receipt.json', canonical(facts))
        cls = LiveServiceReadback if live else LaboratoryServiceReadback
        return cls(_SEAL, manifest, completion, facts, root)
    except BaseException as error:
        protected._exclusive(root / 'failure.json', canonical({'status': 'failed', 'error': getattr(error, 'code', type(error).__name__),
            'operation_id': manifest['operation_id'], 'scope_released': False, 'mutation_replayed': False}))
        raise
    finally:
        if token is not None: token.close()


def collect_live(manifest, *, binding, backend_credential, completion, state_contract, storage, output):
    """Fixed real Azure HTTPS GET only; no caller URL, token, method or transport."""
    ib.require_live_binding(binding)
    return _collect(manifest, binding=binding, backend_credential=backend_credential, completion=completion,
        state_contract=state_contract, storage=storage, upstream=broker.NativeUpstream(), output=output)


def collect_laboratory(manifest, *, binding, backend_credential, completion, state_contract, storage, upstream, output):
    """Actual bounded loopback TLS test route; cannot mint live assurance."""
    if type(binding) is not ib.LaboratoryIdentityBinding: _fail('service_readback_laboratory_binding')
    return _collect(manifest, binding=binding, backend_credential=backend_credential, completion=completion,
        state_contract=state_contract, storage=storage, upstream=upstream, output=output)
