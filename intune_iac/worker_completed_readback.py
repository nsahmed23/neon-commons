"""Read-only restart evidence after a known successful host outcome.

This route consumes a sealed fresh committed-state observation of an already
unlocked backend. It does not synthesize an exceptional lease-release record,
rebuild a GraphCompletion from JSON, replay a plan, or rewrite the known host
result. ServiceJob.reconcile remains the sole authority-reservation transition.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat
import time

from . import observation_reader as reader_api, protected, worker_service as service
from . import worker_committed_recovery as recovery, worker_precondition as precondition
from .io import AppError, canonical, digest, parse_json
from .provider_journey import _absolute, _private

_SEAL = object()
MAX_BYTES = 16 * 1024 * 1024
KIND = 'original_approved_state_observed_after_known_host_completion'


def _fail(code):
    raise AppError(code, 'Fresh independent observation did not establish the original approved state after known host completion.')


def _copy(value):
    return parse_json(canonical(value))


def _validated(*, job_root, policy_path, observation):
    # The exact capability owns authenticated GETs, source/identity binding,
    # age, actual state bytes, complete Graph capture and native host absence.
    if type(observation) is not recovery.RecoveryObservation:
        _fail('completed_readback_observation_required')
    context = observation.context
    if type(context) not in (recovery.LiveCommittedRecoveryContext, recovery.LaboratoryCommittedRecoveryContext):
        _fail('completed_readback_context_required')
    observed = observation.verified()
    # Reopen the actual authority independently of the process-held context.
    # Reading an expired historical operation does not authorize another run.
    original = service.ServiceJob(Path(job_root), Path(policy_path))
    manifest = original.manifest
    live = manifest.get('profile') == 'azure_public_pilot'
    if (manifest.get('profile') not in ('azure_public_pilot', 'native_docker_laboratory_protocol')
            or type(context) is not (recovery.LiveCommittedRecoveryContext if live else recovery.LaboratoryCommittedRecoveryContext)
            or original.root != context.job.root or original.policy.path != context.job.policy.path
            or original.sha256 != context.job.sha256 or original.identifier != context.job.identifier):
        _fail('completed_readback_original_job_binding')
    with original.policy.connection() as db:
        row = db.execute('SELECT status,cancelled,dispatches,outcome,controller_pid,controller_start FROM jobs WHERE id=?',
                         (original.identifier,)).fetchone()
        consumed = db.execute('SELECT manifest_sha256 FROM consumed WHERE operation_id=?', (original.identifier,)).fetchall()
        owners = sorted(item[0] for item in db.execute('SELECT scope FROM ownership WHERE job=?', (original.identifier,)))
    if (row is None or row[0] != 'host_completed_service_unverified' or row[2] != 1
            or row[4] is not None or row[5] is not None or consumed != [(original.sha256,)]
            or owners != service._scopes(manifest)):
        _fail('completed_readback_known_host_authority_required')
    outcome = parse_json(row[3]) if row[3] else None
    host = outcome.get('host') if type(outcome) is dict else None
    if (type(host) is not dict or host.get('status') != 'complete'
            or type(host.get('container_exit_code')) is not int or host['container_exit_code'] != 0
            or host.get('cleanup', {}).get('removed') is not True
            or host.get('cleanup', {}).get('stopped_state', {}).get('Running') is not False
            or outcome.get('operation_outcome') != 'host_completed_service_unverified'):
        _fail('completed_readback_known_host_result_required')
    binding = observed.get('original')
    if (type(binding) is not dict or binding.get('operation_id') != original.identifier
            or binding.get('manifest_sha256') != original.sha256
            or binding.get('policy_sha256') != original.policy.sha256
            or binding.get('status') != row[0] or binding.get('cancelled') is not bool(row[1])
            or binding.get('outcome_sha256') != digest(outcome) or binding.get('scopes') != owners):
        _fail('completed_readback_authority_observation_binding')
    contracts = manifest.get('state_contracts')
    proof = observed.get('committed_state_proof')
    if (type(contracts) is not dict or set(contracts) != {'state-write'} or type(proof) is not dict
            or proof.get('original_operation_id') != original.identifier
            or proof.get('original_manifest_sha256') != original.sha256
            or proof.get('original_contract_sha256') != digest(contracts['state-write'])
            or proof.get('original_saved_plan_sha256') != manifest.get('saved_plan_sha256')
            or proof.get('original_template_sha256') != contracts['state-write'].get('admission_template_sha256')
            or proof.get('original_preimage_raw_sha256') != manifest['precondition_binding']['preimage_raw_sha256']):
        _fail('completed_readback_original_approval_binding')
    state = observed.get('state')
    backend = manifest['provider_binding']['backend']
    target = backend['backend']
    if (type(state) is not dict or proof.get('state_sha256') != state.get('sha256')
            or proof.get('state_lineage') != state.get('lineage') or proof.get('state_serial') != state.get('serial')
            or type(state.get('serial')) is not int or state['serial'] != target['state_serial'] + 1
            or state.get('lineage') != target.get('state_lineage')
            or observed.get('state_artifact_sha256') != state.get('sha256')
            or observed.get('identity') != backend['identity']
            or observed.get('storage_binding_sha256') != manifest['storage_binding_sha256']
            or any(observed.get('backend_target', {}).get(key) != target.get(key) for key in
                   ('subscription_id', 'storage_account_resource_id', 'blob_endpoint', 'container', 'key', 'workspace', 'state_lineage'))):
        _fail('completed_readback_backend_binding')
    run = manifest.get('run_context')
    provider = manifest['provider_binding']
    if (type(run) is not dict or run.get('source_revision') != provider.get('source_revision')
            or run.get('source_sha256') != provider.get('source_sha256')
            or run.get('effective_inputs_sha256') != provider.get('effective_input_sha256')
            or run.get('provider_lock_sha256') != provider.get('lockfile_sha256')
            or digest(backend) != manifest.get('backend_scope_sha256')):
        _fail('completed_readback_source_binding')
    if observed.get('locked') is not False or observed.get('metadata') != {}:
        _fail('completed_readback_backend_lock_remaining')
    captured = observation.captured
    if type(captured) is not reader_api.CapturedObservation:
        _fail('completed_readback_capture_required')
    batch, source, _ = precondition._validated_capture(captured, context.observer.reader, max_age=30)
    gate = manifest['precondition_binding']
    if (batch['capture_sha256'] != observed.get('committed_capture', {}).get('capture_sha256')
            or batch['tenant_id'] != manifest['tenant_id'] or [batch['object_id']] != manifest['object_ids']
            or digest(batch['source']['raw_observed']) != proof.get('desired_raw_sha256')
            or source['evidence_class'] != ('graph_authenticated_observation' if live else 'graph_reader_laboratory')
            or source['source_authenticity_verified'] is not live
            or canonical(source.get('identity')) != canonical(gate['identity'])
            or digest(source.get('identity')) != proof.get('reader_identity_sha256')):
        _fail('completed_readback_capture_binding')
    return original, observed, proof, captured, digest(outcome)


class _KnownCompletedReadback:
    def __init__(self, seal, *, original, observation, facts, root):
        live = original.manifest['profile'] == 'azure_public_pilot'
        if (seal is not _SEAL or type(self) not in (LiveKnownCompletedServiceReadback, LaboratoryKnownCompletedServiceReadback)
                or live != (type(self) is LiveKnownCompletedServiceReadback)):
            _fail('completed_readback_constructor_forbidden')
        self.job_root, self.policy_path = original.root, original.policy.path
        self.observation, self.root, self.facts = observation, root, _copy(facts)
        self.manifest_sha256, self.sha256 = original.sha256, digest(facts)
        self.pid, self.created = os.getpid(), time.monotonic()

    def __repr__(self):
        return '<' + type(self).__name__ + ' read-only>'

    def __reduce_ex__(self, protocol):
        raise TypeError('Known-completion readback cannot be serialized.')

    def captured_observation(self):
        self.verified(self.observation.context.job.manifest)
        return self.observation.captured

    def verified(self, manifest):
        if (self.pid != os.getpid() or not 0 <= time.monotonic() - self.created <= 30
                or digest(manifest) != self.manifest_sha256 or digest(self.facts) != self.sha256):
            _fail('completed_readback_changed_or_stale')
        # Historical controller bytes remain their original identity. The
        # newly observing implementation must remain exactly the one that
        # collected this capability; it cannot change before reservation release.
        if digest(service.implementation_binding()) != self.facts['observing_implementation_sha256']:
            _fail('completed_readback_observer_implementation_changed')
        original, observed, proof, _, outcome_sha = _validated(job_root=self.job_root, policy_path=self.policy_path,
                                                              observation=self.observation)
        if (digest(observed) != self.facts['committed_observation_sha256']
                or observed['state'] != self.facts['backend_state'] or proof != self.facts['state_admission']
                or outcome_sha != self.facts['original_outcome_sha256'] or original.sha256 != digest(manifest)):
            _fail('completed_readback_changed_or_stale')
        for name, expected in self.facts['artifacts'].items():
            path = _private(self.root / name)
            if protected._sha(path) != expected:
                _fail('completed_readback_artifact_changed')
        if protected._sha(_private(self.root / 'receipt.json')) != self.sha256:
            _fail('completed_readback_artifact_changed')
        return _copy(self.facts)


class LiveKnownCompletedServiceReadback(_KnownCompletedReadback):
    pass


class LaboratoryKnownCompletedServiceReadback(_KnownCompletedReadback):
    pass


def collect(*, job_root, policy_path, observation, output):
    """Bind existing fresh independent reads; perform no execution or release.

    A separate committed context observed native host absence, an unlocked
    backend GET, and an exact original-approved Graph projection. This factory
    checks those capabilities against a freshly reopened service authority.
    It does not attest an additional network read or a no-change native plan.
    """
    original, observed, proof, captured, outcome_sha = _validated(job_root=job_root, policy_path=policy_path,
                                                                observation=observation)
    root = _absolute(str(Path(output).absolute()))
    _private(root.parent, directory=True)
    root.mkdir(mode=0o700, exist_ok=False)
    source = _private(observation.root / 'state.raw')
    descriptor = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_BYTES:
            _fail('completed_readback_state_artifact_changed')
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES or hashlib.sha256(raw).hexdigest() != observed['state']['sha256']:
        _fail('completed_readback_state_artifact_changed')
    protected._exclusive(root / 'observed-state.raw', raw)
    protected._exclusive(root / 'committed-observation.json', canonical(observed))
    protected._exclusive(root / 'original-state-proof.json', canonical(proof))
    batch, _ = captured.verified()
    manifest = original.manifest
    facts = {'schema_version': 'worker-service-independent-readback/1', 'operation_id': original.identifier,
        'manifest_sha256': original.sha256, 'execution_binding_sha256': manifest['execution_binding_sha256'],
        'evidence_class': 'authenticated_service_state_convergence' if manifest['profile'] == 'azure_public_pilot' else 'laboratory_service_state_convergence',
        'recovery_kind': KIND, 'original_outcome_sha256': outcome_sha,
        'committed_observation_sha256': digest(observed), 'exceptional_lease_release_performed': False,
        'graph_capture_sha256': batch['capture_sha256'],
        'graph_approved_projection_sha256': manifest['precondition_binding']['approved_projection_sha256'],
        'backend_state': observed['state'], 'backend_lock_released': True, 'state_admission': proof,
        'observed_at': observed['observed_at'], 'started_at': observed['observed_at'],
        'observing_implementation_sha256': digest(service.implementation_binding()),
        'original_implementation_sha256': digest(manifest.get('implementation_files')),
        'original_execution_provenance': 'host_completed', 'actor_attribution': 'unestablished',
        'endpoint_effectiveness': 'unestablished', 'second_plan_convergence': 'separate_native_plan_evidence_required',
        'mutation_replayed': False, 'ownership_released': False, 'production_approved': False,
        'artifacts': {name: protected._sha(root / name) for name in
            ('observed-state.raw', 'committed-observation.json', 'original-state-proof.json')}}
    protected._exclusive(root / 'receipt.json', canonical(facts))
    kind = LiveKnownCompletedServiceReadback if manifest['profile'] == 'azure_public_pilot' else LaboratoryKnownCompletedServiceReadback
    return kind(_SEAL, original=original, observation=observation, facts=facts, root=root)
