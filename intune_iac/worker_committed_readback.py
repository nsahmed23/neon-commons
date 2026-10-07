"""Reconciliation evidence for the ORIGINAL approved state after interruption.

This consumes a separate sealed committed-state recovery completion. It neither
reconstructs a normal GraphCompletion from JSON nor changes its original-state
counterpart's admission rules. No mutation or replay is performed here.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import time

from . import observation_reader as reader_api, protected, worker_committed_recovery as recovery
from .io import AppError, canonical, digest, parse_json
from .provider_journey import _private

_SEAL = object()


def _fail(code):
    raise AppError(code, 'The independently observed original committed state was not established for reconciliation.')


def _copy(value):
    return parse_json(canonical(value))


def _validated(manifest, completion):
    live = manifest.get('profile') == 'azure_public_pilot'
    if (manifest.get('profile') not in ('azure_public_pilot', 'native_docker_laboratory_protocol')
            or type(completion) is not (recovery.LiveCommittedRecoveryCompletion if live else recovery.LaboratoryCommittedRecoveryCompletion)):
        _fail('committed_readback_capability_required')
    facts = completion.verified()
    observation = facts['fresh_observation']
    proof = observation['committed_state_proof']
    contracts = manifest.get('state_contracts')
    if (type(contracts) is not dict or set(contracts) != {'state-write'}
            or facts['original']['operation_id'] != manifest['operation_id']
            or facts['original']['manifest_sha256'] != digest(manifest)
            or proof['original_operation_id'] != manifest['operation_id']
            or proof['original_manifest_sha256'] != digest(manifest)
            or proof['original_contract_sha256'] != digest(contracts['state-write'])
            or proof['original_saved_plan_sha256'] != manifest['saved_plan_sha256']
            or proof['original_template_sha256'] != contracts['state-write']['admission_template_sha256']
            or proof['original_preimage_raw_sha256'] != manifest['precondition_binding']['preimage_raw_sha256']
            or proof['state_sha256'] != observation['state']['sha256']
            or proof['state_lineage'] != observation['state']['lineage']
            or proof['state_serial'] != observation['state']['serial']):
        _fail('committed_readback_original_binding')
    if (facts.get('lease_independently_unlocked') is not True or observation.get('locked') is not False
            or observation.get('metadata') != {} or facts.get('lock_metadata_remaining') is not False):
        _fail('committed_readback_backend_lock_remaining')
    captured = completion.captured_observation()
    if type(captured) is not reader_api.CapturedObservation:
        _fail('committed_readback_capture_required')
    batch, source = captured.verified()
    expected_class = 'graph_authenticated_observation' if live else 'graph_reader_laboratory'
    if (batch['capture_sha256'] != observation['committed_capture']['capture_sha256']
            or batch['tenant_id'] != manifest['tenant_id'] or [batch['object_id']] != manifest['object_ids']
            or digest(batch['source']['raw_observed']) != proof['desired_raw_sha256']
            or source['evidence_class'] != expected_class or source['source_authenticity_verified'] is not live):
        _fail('committed_readback_capture_binding')
    return facts, observation, proof, captured


class _CommittedReadback:
    def __init__(self, seal, *, manifest, completion, facts, root):
        live = manifest['profile'] == 'azure_public_pilot'
        if (seal is not _SEAL or type(self) not in (LiveCommittedServiceReadback, LaboratoryCommittedServiceReadback)
                or live != (type(self) is LiveCommittedServiceReadback)):
            _fail('committed_readback_constructor_forbidden')
        self.manifest_sha256, self.completion, self.facts, self.root = digest(manifest), completion, _copy(facts), root
        self.sha256, self.pid, self.created = digest(facts), os.getpid(), time.monotonic()

    def __repr__(self):
        return '<' + type(self).__name__ + ' read-only>'

    def __reduce_ex__(self, protocol):
        raise TypeError('Committed readback evidence cannot be serialized.')

    def verified(self, manifest):
        if (self.pid != os.getpid() or not 0 <= time.monotonic() - self.created <= 30
                or digest(manifest) != self.manifest_sha256 or digest(self.facts) != self.sha256):
            _fail('committed_readback_changed_or_stale')
        completion, observation, proof, _ = _validated(manifest, self.completion)
        if (digest(completion) != self.facts['recovery_completion_sha256']
                or observation['state'] != self.facts['backend_state'] or proof != self.facts['state_admission']):
            _fail('committed_readback_changed_or_stale')
        for name, expected in self.facts['artifacts'].items():
            path = _private(self.root / name)
            if protected._sha(path) != expected:
                _fail('committed_readback_artifact_changed')
        if protected._sha(self.root / 'receipt.json') != self.sha256:
            _fail('committed_readback_artifact_changed')
        return _copy(self.facts)


class LiveCommittedServiceReadback(_CommittedReadback):
    pass


class LaboratoryCommittedServiceReadback(_CommittedReadback):
    pass


def collect(manifest, *, completion, output):
    """Preserve the sealed independent post-release reads for reconciliation.

    The exact completion already performed a fresh backend GET and authenticated
    Graph read. This adapter validates/binds those reads; it does not claim an
    extra network observation or a second no-change plan that it did not run.
    """
    manifest = _copy(manifest)
    completed, observation, proof, captured = _validated(manifest, completion)
    root = Path(output).absolute()
    _private(root.parent, directory=True)
    root.mkdir(mode=0o700, exist_ok=False)
    original_state = _private(completion.observation.root / 'state.raw')
    descriptor = os.open(original_state, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as stream:
        if not 0 < os.fstat(stream.fileno()).st_size <= 16 * 1024 * 1024:
            _fail('committed_readback_state_artifact_changed')
        raw = stream.read(16 * 1024 * 1024 + 1)
    if len(raw) > 16 * 1024 * 1024 or hashlib.sha256(raw).hexdigest() != observation['state']['sha256']:
        _fail('committed_readback_state_artifact_changed')
    protected._exclusive(root / 'observed-state.raw', raw)
    protected._exclusive(root / 'recovery-completion.json', canonical(completed))
    protected._exclusive(root / 'original-state-proof.json', canonical(proof))
    batch, _ = captured.verified()
    live = manifest['profile'] == 'azure_public_pilot'
    facts = {'schema_version': 'worker-service-independent-readback/1', 'operation_id': manifest['operation_id'],
        'manifest_sha256': digest(manifest), 'execution_binding_sha256': manifest['execution_binding_sha256'],
        'evidence_class': 'authenticated_service_state_convergence' if live else 'laboratory_service_state_convergence',
        'recovery_kind': 'original_approved_state_committed_execution_unknown',
        'recovery_operation_id': completed['recovery_operation_id'], 'recovery_completion_sha256': digest(completed),
        'graph_capture_sha256': batch['capture_sha256'],
        'graph_approved_projection_sha256': manifest['precondition_binding']['approved_projection_sha256'],
        'backend_state': observation['state'], 'backend_lock_released': True, 'state_admission': proof,
        'observed_at': observation['observed_at'], 'started_at': observation['observed_at'],
        'endpoint_effectiveness': 'unestablished', 'second_plan_convergence': 'separate_native_plan_evidence_required',
        'actor_attribution': 'unestablished', 'mutation_replayed': False, 'production_approved': False,
        'artifacts': {name: protected._sha(root / name) for name in
            ('observed-state.raw', 'recovery-completion.json', 'original-state-proof.json')}}
    protected._exclusive(root / 'receipt.json', canonical(facts))
    cls = LiveCommittedServiceReadback if live else LaboratoryCommittedServiceReadback
    return cls(_SEAL, manifest=manifest, completion=completion, facts=facts, root=root)
