"""Exact process-held selectors for two stopped adoption Plan phases only.

These handles bind registered immutable histories. They neither authenticate
receiving services nor authorize lease release, import replay or reconciliation.
"""
from pathlib import Path
import os
import time
from intune_iac import worker_adoption as adoption, worker_adoption_reconcile as plans
from intune_iac import worker_service as service, worker_host as host, worker_adoption_recovery as imported, protected
from intune_iac.io import AppError, digest, parse_json

_SEAL = object()
_KINDS = ('initial_verification', 'recovery_plan')


def _fail(code):
    raise AppError(code, 'The exact stopped Plan phase and retained original adoption authority were not established.') from None


def _copy(value):
    return service._snapshot(value)


def _host_record(root, expected_spec, outcome):
    if (type(outcome) is not dict or type(outcome.get('host')) is not dict
            or outcome['host'].get('cleanup', {}).get('removed') is not True
            or outcome['host']['cleanup'].get('stopped_state', {}).get('Running') is not False):
        _fail('adoption_plan_recovery_cleanup_unconfirmed')
    manifest = service._bounded_private_json(root / 'manifest.json')
    receipt = service._bounded_private_json(root / 'receipt.json')
    recorded = _copy(outcome['host'])
    if 'receipt' in recorded and recorded.pop('receipt') != str(root / 'receipt.json'):
        _fail('adoption_plan_recovery_host_receipt_binding')
    if (receipt != recorded or digest(manifest) != outcome['host'].get('manifest_sha256')
            or manifest.get('host_spec') != expected_spec
            or manifest.get('container_name') != receipt.get('container_name')
            or manifest.get('run_id') != receipt.get('run_id')):
        _fail('adoption_plan_recovery_host_receipt_binding')
    return {'manifest_sha256': protected._sha(root / 'manifest.json'),
            'receipt_sha256': protected._sha(root / 'receipt.json'),
            'container_name': manifest['container_name'], 'run_id': manifest['run_id']}


class _Phase:
    def __init__(self, seal, *, original, plan=None):
        if seal is not _SEAL or type(original) is not adoption.AdoptionJob:
            _fail('adoption_plan_recovery_phase_required')
        initial = type(self) is InitialVerificationPhase
        if type(self) not in (InitialVerificationPhase, RecoveryPlanPhase) or initial != (plan is None):
            _fail('adoption_plan_recovery_phase_required')
        if not initial and (type(plan) is not plans.RecoveryPlanJob or plan.original is not original):
            _fail('adoption_plan_recovery_phase_required')
        self.original = original
        self.plan = plan
        self.kind = 'initial_verification' if initial else 'recovery_plan'
        self.identifier = original.manifest['verification_operation_id'] if initial else plan.identifier
        self.host_root = original.root / 'verification-host-run' if initial else plan.root / 'host-run'
        self.journal = original.root / 'verification-broker.sqlite3' if initial else plan.root / 'broker.sqlite3'
        self.host_spec = _copy(original.manifest['verification_host_spec'] if initial else plan.manifest['host_spec'])
        self.broker_policy = _copy(original.manifest['verification_broker_policy'] if initial else plan.manifest['broker_policy'])
        self.manifest_sha256 = original.sha256 if initial else plan.sha256
        self.pid = os.getpid()
        self._identity = (id(original), id(plan), self.kind, self.identifier, str(self.host_root), str(self.journal),
                          digest(self.host_spec), digest(self.broker_policy), self.manifest_sha256)
        self.snapshot()

    def __reduce_ex__(self, protocol):
        raise TypeError('A stopped Plan phase cannot be serialized.')

    def _check(self):
        if (self.pid != os.getpid() or type(self) not in (InitialVerificationPhase, RecoveryPlanPhase)
                or self._identity != (id(self.original), id(self.plan), self.kind, self.identifier,
                    str(self.host_root), str(self.journal), digest(self.host_spec), digest(self.broker_policy), self.manifest_sha256)):
            _fail('adoption_plan_recovery_phase_changed')
        initial = type(self) is InitialVerificationPhase
        if self.kind != ('initial_verification' if initial else 'recovery_plan'):
            _fail('adoption_plan_recovery_phase_changed')
        self.original._check(expiry=False)
        if initial:
            if (self.plan is not None or self.identifier != self.original.manifest['verification_operation_id']
                    or self.manifest_sha256 != self.original.sha256
                    or self.host_spec != self.original.manifest['verification_host_spec']
                    or self.broker_policy != self.original.manifest['verification_broker_policy']):
                _fail('adoption_plan_recovery_phase_changed')
        else:
            if type(self.plan) is not plans.RecoveryPlanJob or self.plan.original is not self.original:
                _fail('adoption_plan_recovery_phase_changed')
            self.plan._check(expiry=False)
            if (self.plan.policy.database != self.original.policy.database
                    or self.plan.policy.root != self.original.policy.root
                    or self.identifier != self.plan.identifier or self.manifest_sha256 != self.plan.sha256
                    or self.host_spec != self.plan.manifest['host_spec'] or self.broker_policy != self.plan.manifest['broker_policy']):
                _fail('adoption_plan_recovery_phase_changed')
        manifest = self.original.manifest
        selected = manifest if initial else self.plan.manifest
        if (type(selected.get('prepared_at')) is not int or type(selected.get('expires_at')) is not int
                or not selected['prepared_at'] < selected['expires_at'] <= selected['prepared_at'] + 900
                or self.broker_policy['expires_at'] != selected['expires_at']
                or self.broker_policy['execution_binding_sha256'] != selected['execution_binding_sha256']):
            _fail('adoption_plan_recovery_historical_time_binding')
        # Validate only the route/schema shape through the existing closed
        # validator. This disposable time-adjusted copy is never returned,
        # persisted, signed, supplied to a broker, or used for dispatch. The
        # exact expired original remains the journal/signature-bound policy.
        shape_policy = _copy(self.broker_policy)
        shape_policy['expires_at'] = int(time.time()) + 60
        shape = {**manifest, 'verification_operation_id': self.identifier,
                 'execution_binding_sha256': self.broker_policy['execution_binding_sha256'],
                 'expires_at': shape_policy['expires_at']}
        adoption._policy_shape(shape_policy, shape, service._host_spec(self.host_spec), verification=True)

    def database_snapshot(self, db):
        """Use the caller's coherent transaction for the final pre-dispatch fence."""
        self._check()
        original = self.original
        row = db.execute('SELECT status,cancelled,dispatches,outcome,controller_pid,controller_start,root,manifest_sha256 FROM jobs WHERE id=?', (original.identifier,)).fetchone()
        consumed = db.execute('SELECT manifest_sha256 FROM consumed WHERE operation_id=?', (original.identifier,)).fetchone()
        scopes = sorted(r[0] for r in db.execute('SELECT scope FROM ownership WHERE job=?', (original.identifier,)))
        if (row is None or row[0] not in ('outcome_unknown', 'import_host_completed_unverified', 'first_plan_host_completed_unverified')
                or row[2] != 1 or row[4:6] != (None, None) or row[6:] != (str(original.root), original.sha256)
                or consumed != (original.sha256,) or scopes != service._scopes(original.manifest) or not row[3]):
            _fail('adoption_plan_recovery_original_active_or_unowned')
        initial_row = db.execute('SELECT verification_id,verification_dispatches,verification_status,verification_outcome FROM adoption_operations WHERE operation_id=?', (original.identifier,)).fetchone()
        if initial_row is None or initial_row[0] != original.manifest['verification_operation_id']:
            _fail('adoption_plan_recovery_initial_registration')
        if self.kind == 'initial_verification':
            if (initial_row[1] != 1 or initial_row[2] not in ('outcome_unknown', 'first_plan_host_completed_unverified')
                    or not initial_row[3] or row[0] not in ('outcome_unknown', 'first_plan_host_completed_unverified')):
                _fail('adoption_plan_recovery_initial_not_stopped')
            phase_status, phase_cancelled, phase_outcome = initial_row[2], bool(row[1]), parse_json(initial_row[3])
            phase_row = list(initial_row)
        else:
            phase_row = db.execute('SELECT original_operation_id,manifest_sha256,root,status,cancelled,dispatches,outcome,controller_pid,controller_start FROM adoption_recovery_plans WHERE operation_id=?', (self.identifier,)).fetchone()
            if (phase_row is None or phase_row[:3] != (original.identifier, self.manifest_sha256, str(self.plan.root))
                    or phase_row[3] not in ('outcome_unknown', 'plan_host_completed_unverified') or phase_row[5] != 1
                    or phase_row[7:] != (None, None) or not phase_row[6]
                    or db.execute('SELECT manifest_sha256 FROM consumed WHERE operation_id=?', (self.identifier,)).fetchone() != (self.manifest_sha256,)):
                _fail('adoption_plan_recovery_selected_plan_not_stopped')
            phase_status, phase_cancelled, phase_outcome = phase_row[3], bool(phase_row[4]), parse_json(phase_row[6])
            phase_row = list(phase_row)
        return {'operation_id': original.identifier, 'manifest_sha256': original.sha256, 'status': row[0],
                'cancelled': bool(row[1]), 'outcome_sha256': digest(parse_json(row[3])), 'scopes': scopes,
                'phase_kind': self.kind, 'phase_operation_id': self.identifier, 'phase_manifest_sha256': self.manifest_sha256,
                'phase_job_root': str(original.root if self.plan is None else self.plan.root),
                'phase_status': phase_status, 'phase_cancelled': phase_cancelled, 'phase_outcome_sha256': digest(phase_outcome),
                'phase_row_sha256': digest(phase_row), 'initial_verification_row_sha256': digest(list(initial_row))}, parse_json(row[3]), phase_outcome

    def require_dispatch_quiet(self, db):
        """Release-only fence; later reviewed Plans do not rewrite history."""
        self._check()
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='adoption_recovery_plans'").fetchone():
            conflicts = db.execute("SELECT operation_id,status,controller_pid FROM adoption_recovery_plans WHERE original_operation_id=? AND operation_id!=? LIMIT 1001", (self.original.identifier, self.identifier)).fetchall()
            if len(conflicts) > 1000 or any(r[2] is not None or r[1] not in ('cancelled_before_dispatch', 'outcome_unknown', 'plan_host_completed_unverified') for r in conflicts):
                _fail('adoption_plan_recovery_other_plan_active')

    def snapshot(self):
        with self.original.policy.connection() as db:
            db.execute('BEGIN')
            facts, import_outcome, phase_outcome = self.database_snapshot(db)
            db.execute('COMMIT')
        original_host = _host_record(self.original.root / 'host-run', self.original.manifest['host_spec'], import_outcome)
        phase_host = _host_record(self.host_root, self.host_spec, phase_outcome)
        if host.directory_binding(self.host_spec['source_root'])['sha256'] != self.host_spec['source_sha256']:
            _fail('adoption_plan_recovery_phase_source_changed')
        import_inspection = imported.inspect_adoption_recovery(self.original)
        writes = import_inspection['state_write_attempts']
        if len(writes) != 1:
            _fail('adoption_plan_recovery_original_import_write_unestablished')
        return dict(facts, verification_operation_id=self.original.manifest['verification_operation_id'],
                    policy_sha256=self.original.policy.sha256, original_host=original_host, phase_host=phase_host,
                    original_import_journal_sha256=import_inspection['journal_sha256'], original_import_state_write= writes[0])


class InitialVerificationPhase(_Phase):
    pass


class RecoveryPlanPhase(_Phase):
    pass


def stopped_initial_verification(job):
    return InitialVerificationPhase(_SEAL, original=job)


def stopped_recovery_plan(job):
    if type(job) is not plans.RecoveryPlanJob:
        _fail('adoption_plan_recovery_phase_required')
    return RecoveryPlanPhase(_SEAL, original=job.original, plan=job)
