"""Read-only attestation of an already unlocked ORIGINAL state after failure.

This deliberately reuses the exact-original-revision recovery context. It does
not admit an advanced state revision, release a lease, clear metadata, transfer
ownership, replay execution or certify desired-state convergence.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import time

from . import observation_reader as reader_api, protected, worker_lease_recovery as recovery
from . import worker_precondition as precondition, worker_service as service, worker_successor as successor
from .io import AppError, canonical, digest, parse_json
from .provider_journey import _private

_SEAL = object()
VERSION = 'unlocked-original-state-attestation/1'


def _fail(code):
    raise AppError(code, 'Fresh read-only observation did not establish the original unlocked backend and exact partial service preimage.')


def _copy(value):
    return parse_json(canonical(value))


def _profile(context, reader):
    live = type(context) is recovery.LiveRecoveryContext
    if type(context) not in (recovery.LiveRecoveryContext, recovery.LaboratoryRecoveryContext):
        _fail('partial_recovery_context_required')
    if type(reader) is not (reader_api.LiveGraphReader if live else reader_api.LaboratoryGraphReader):
        _fail('partial_recovery_reader_profile')
    facts = reader.evidence()
    job = context.job
    if (len(job.manifest['object_ids']) != 1 or facts['identity']['tenant_id'] != job.manifest['tenant_id']
            or job.manifest['object_ids'][0] not in facts['identity']['object_ids']):
        _fail('partial_recovery_reader_scope')
    return 'azure_public_unlocked_original_state' if live else 'laboratory_unlocked_original_state'


class _PartialRecoveryAttestation:
    def __init__(self, seal, *, context, reader, preimage, current, backend, facts, root):
        live = type(context) is recovery.LiveRecoveryContext
        if (seal is not _SEAL or type(self) not in (LivePartialRecoveryAttestation, LaboratoryPartialRecoveryAttestation)
                or live != (type(self) is LivePartialRecoveryAttestation)):
            _fail('partial_recovery_constructor_forbidden')
        self.context, self.reader, self.preimage, self.current, self.backend = context, reader, preimage, current, backend
        self.facts, self.root = _copy(facts), root
        self.sha256, self.pid, self.created = digest(facts), os.getpid(), time.monotonic()

    def __repr__(self):
        return '<' + type(self).__name__ + ' read-only>'

    def __reduce_ex__(self, protocol):
        raise TypeError('Partial recovery evidence cannot be serialized.')

    def verified(self):
        if (self.pid != os.getpid() or not 0 <= time.monotonic() - self.created <= 30
                or digest(self.facts) != self.sha256 or self.facts['profile'] != _profile(self.context, self.reader)):
            _fail('partial_recovery_attestation_changed_or_stale')
        self.context.check()
        backend = self.backend.verified()
        before, _, before_projection = precondition._validated_capture(self.preimage, self.reader, max_age=30)
        current, _, current_projection = precondition._validated_capture(self.current, self.reader, max_age=30)
        if (backend != self.facts['backend_observation'] or before_projection != current_projection
                or before['capture_sha256'] != self.facts['service_preimage']['capture_sha256']
                or current['capture_sha256'] != self.facts['service_current']['capture_sha256']
                or protected._sha(self.root / 'attestation.json') != self.sha256):
            _fail('partial_recovery_attestation_changed_or_stale')
        with self.context.job.policy.connection() as db:
            row = db.execute('SELECT original_operation,original_manifest_sha256,facts_sha256,artifact_root '
                             'FROM partial_recovery_observations WHERE observation_id=?', (self.facts['observation_id'],)).fetchone()
        if row != (self.context.job.identifier, self.context.job.sha256, self.sha256, str(self.root)):
            _fail('partial_recovery_record_changed')
        return _copy(self.facts)


class LivePartialRecoveryAttestation(_PartialRecoveryAttestation):
    pass


class LaboratoryPartialRecoveryAttestation(_PartialRecoveryAttestation):
    pass


def attest(*, context, reader, service_preimage, observation_id, output):
    """Read exact original state and fresh Graph only; persist no authority.

    `service_preimage` is the process-held capture used by the separately
    reviewed new plan. A second capture checks that it is still current.
    """
    profile = _profile(context, reader)
    context.check()
    if (type(observation_id) is not str or not service._UUID.fullmatch(observation_id)
            or observation_id == context.job.identifier):
        _fail('partial_recovery_observation_id')
    before, before_source, before_projection = precondition._validated_capture(service_preimage, reader, max_age=30)
    root = Path(output).absolute()
    _private(root.parent, directory=True)
    root.mkdir(mode=0o700, exist_ok=False)
    started = time.monotonic()
    registered = False
    try:
        backend = context.observe(root / 'backend', require_locked=False)
        backend_facts = backend.verified()
        current = reader.capture(context.job.manifest['object_ids'][0], root / 'graph', max_elapsed_seconds=30)
        after, _, after_projection = precondition._validated_capture(current, reader, max_age=30)
        if before_projection != after_projection:
            _fail('partial_recovery_service_changed')
        if time.monotonic() - started > 30:
            _fail('partial_recovery_observation_deadline')
        context.check()
        # No advanced revision enters through a caller-supplied new baseline:
        # the existing context verifies all original revision fields exactly.
        facts = {'schema_version': VERSION, 'recovery_kind': 'already_unlocked_original_state_observed',
                 'observation_id': observation_id, 'profile': profile, 'original': context.original,
                 'service_authority_root': str(context.job.policy.root),
                 'current_service_policy_sha256': context.job.policy.sha256,
                 'backend_observation': backend_facts,
                 'service_preimage': {'capture_sha256': before['capture_sha256'],
                    'raw_sha256': digest(before['source']['raw_observed']), 'observed_at': before['observed_at'],
                    'reader_identity': before_source['identity'],
                    'identity_observation_sha256': before_source['identity_observation_sha256']},
                 'service_current': {'capture_sha256': after['capture_sha256'],
                    'raw_sha256': digest(after['source']['raw_observed']), 'observed_at': after['observed_at']},
                 'service_projection_sha256': digest(before_projection), 'observed_at': int(time.time()),
                 'lease_release_performed': False, 'metadata_mutation_performed': False,
                 'backend_revision_matches_original': True, 'scope_released': False,
                 'desired_state_convergence': 'unestablished', 'backend_ready_for_new_apply': False,
                 'execution_authorized': False, 'platform_qualified': False, 'production_approved': False}
        protected._exclusive(root / 'attestation.json', canonical(facts))
        with context.job.policy.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            original = successor._original(context.job, db)
            expected = context.original
            if any(original[key] != expected[key] for key in original):
                _fail('partial_recovery_original_changed')
            db.execute('CREATE TABLE IF NOT EXISTS partial_recovery_observations (observation_id TEXT PRIMARY KEY, '
                       'original_operation TEXT NOT NULL,original_manifest_sha256 TEXT NOT NULL,facts_sha256 TEXT NOT NULL,'
                       'artifact_root TEXT UNIQUE NOT NULL,created_at INTEGER NOT NULL)')
            if db.execute('SELECT COUNT(*) FROM partial_recovery_observations').fetchone()[0] >= 10000:
                _fail('partial_recovery_observation_capacity')
            db.execute('INSERT INTO partial_recovery_observations VALUES (?,?,?,?,?,?)',
                       (observation_id, context.job.identifier, context.job.sha256, digest(facts), str(root), int(time.time())))
            context.job.policy.event(db, context.job.identifier, 'already_unlocked_original_state_observed',
                {'observation_id': observation_id, 'attestation_sha256': digest(facts),
                 'artifact': str(root / 'attestation.json'), 'lease_release_performed': False,
                 'scope_released': False, 'execution_authorized': False})
            db.execute('COMMIT')
            registered = True
        protected._sync(context.job.policy.root)
        cls = LivePartialRecoveryAttestation if type(context) is recovery.LiveRecoveryContext else LaboratoryPartialRecoveryAttestation
        return cls(_SEAL, context=context, reader=reader, preimage=service_preimage, current=current,
                   backend=backend, facts=facts, root=root)
    except BaseException as error:
        # Reporting cannot replace the original read/cancellation/durability
        # failure. A committed read-only record is retained even if its final
        # namespace sync or failure archive cannot be established.
        error.read_only_record_committed = registered
        try:
            protected._exclusive(root / 'failure.json', canonical({
                'error': getattr(error, 'code', type(error).__name__),
                'read_only_record_committed': registered, 'lease_release_performed': False,
                'scope_released': False, 'execution_authorized': False}))
        except BaseException as recording_error:
            detail = getattr(recording_error, 'code', type(recording_error).__name__)
            error.recording_failures = [*getattr(error, 'recording_failures', []), detail]
            if hasattr(error, 'add_note'):
                error.add_note('Partial recovery failure evidence could not be recorded: ' + detail +
                               '; retain the original error and inspect the existing read-only registry and artifacts.')
        raise
