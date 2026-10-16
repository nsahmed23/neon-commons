"""An expired recovery approval stays expired across a backward clock step and a restart (PKG-TIME-AUTHZ-C, part 1).

The four lease-recovery modules (worker_lease_recovery, worker_committed_recovery, worker_adoption_recovery and
worker_adoption_plan_recovery) judged their signed approval and manifest on the bare wall clock: in the policy's verify,
and once more after the dispatch reservation was committed, just before the lease request. A refusal at or after the
expiry recorded nothing, so a clock step back before the expiry and a restart let the same approval through, and an
expiry reached while the controller observed the backend was only noticed after the reservation had been spent.

The judgment is now the shared one (intune_iac.validity) on the original job's own store, in the recovery_expired table:
execute judges the approval in the critical section before any observation or request, a refusal of the verification
for its time records the expiry of an approval that authenticates, the dispatch reservation is committed inside the same
section, and the check that remains just before the request judges on the recorded time and this process's monotonic
deadline. The approval is single use, so there is no per-request marker: the reservation row is the dispatch record.

Each test drives the public call (execute) against a real service store, a real recovery policy and a real signature,
with injected wall and monotonic clocks. Only the controller seams that need a live backend are modeled: the sealed
context's checks, its backend observation, the identity token and the upstream request. A refusal must leave the right
records: no reservation, no request, and the expiry recorded.
"""
import base64
import copy
import hashlib
import sqlite3
import subprocess
import time
import types
import unittest
import uuid
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from intune_iac import clock
from intune_iac import identity_binding as ib
from intune_iac import worker_adoption as adoption
from intune_iac import worker_adoption_plan_recovery as plan_recovery
from intune_iac import worker_adoption_recovery as adoption_recovery
from intune_iac import worker_committed_recovery as committed
from intune_iac import worker_lease_recovery as lease
from intune_iac import worker_service as service
from intune_iac.io import AppError, canonical, digest
from plugin_tests import test_worker_adoption_reconcile_r4 as old_contracts
from plugin_tests.signing_fixture import verifier_pin
from plugin_tests.test_adoption_expiry_latch import RECOVERY_WORDS, inject
from plugin_tests.test_clock_authority import Clocks

LIFETIME = 60
EXPIRED = 'lease_recovery_expired'
IMPLEMENTATION = {'fixture/controller.py': 'a' * 64}


class RecoveryFixture(unittest.TestCase):
    """The shared fixture. A family names its module, policy class, context class and the schema strings of its
    documents; the modeled seams are the same for every family."""
    module = None
    policy_class = context_class = None
    policy_schema = operation_schema = action = approval_schema = ''
    profile = ''
    original_id = None
    phase_family = False  # the plan family also names the phase operation its context belongs to

    def setUp(self):
        self.start = int(time.time())
        self.clocks = Clocks(self.start)
        inject(self, self.clocks)
        old_contracts.RecoveryPlanContracts.setUp(self)  # the service store (self.policy) and a signing key (self.key)
        self.expires = self.start + LIFETIME
        patcher = patch.object(service, 'implementation_binding', side_effect=lambda: dict(IMPLEMENTATION))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.requests, self.observations = [], []
        self.on_observe = lambda: None
        self.job_id = str(uuid.uuid4())
        self.outcome = {'host': {'cleanup': {'removed': True}}}
        self.original = {'operation_id': self.job_id, 'status': 'outcome_unknown', 'scopes': ['scope'],
                         'outcome_sha256': digest(self.outcome), 'lease_id': 'lease-1'}
        if self.phase_family:
            self.original['phase_operation_id'] = self.job_id
        self.state = {'etag': '"one"', 'serial': 1}
        self.manifest = {'schema_version': self.operation_schema, 'operation_id': str(uuid.uuid4()),
                         'prepared_at': self.start, 'expires_at': self.expires, 'profile': self.profile,
                         'action': self.action, 'observation': self.observation_document(),
                         'implementation_files': dict(IMPLEMENTATION),
                         'recovery_implementation_sha256': hashlib.sha256(Path(self.module.__file__).read_bytes()).hexdigest(),
                         'metadata_clear_authorized': False, 'ownership_release_authorized': False}
        (self.root / 'out').mkdir(mode=0o700)
        self.write_recovery_policy()
        self.seed_original_job()
        self.context = self.build_context()
        for target, name, function in ((self.context_class, 'check', lambda context: None),
                                       (self.context_class, 'observe',
                                        lambda context, output, *, require_locked=True: self.observe(output, require_locked))):
            patcher = patch.object(target, name, function)
            patcher.start()
            self.addCleanup(patcher.stop)

    # Documents.
    adoption_proof = None  # the adoption families name the classification their observation carries

    def observation_document(self):
        document = {'original': self.original, 'state': self.state, 'metadata': {}, 'locked': True, 'profile': self.profile}
        if self.adoption_proof:
            document['adoption_state_proof'] = {'classification': self.adoption_proof, 'graph_unchanged': True,
                                                'fresh_capture_sha256': 'f' * 64}
        return document

    def write_recovery_policy(self):
        verifier = verifier_pin(Path('/usr/bin/openssl'), hashlib.sha256(Path('/usr/bin/openssl').read_bytes()).hexdigest())
        public = self.policy.approvers[('fixture', 'key')]['public_key_hex']
        self.recovery_policy_path = self.root / 'recovery-policy.json'
        self.recovery_policy_value = {'schema_version': self.policy_schema, 'authority_root': str(self.root / 'recovery-authority'),
            'verifier': {k: str(v) if isinstance(v, Path) else v for k, v in asdict(verifier).items()},
            'approvers': [{'issuer': 'recovery', 'key_id': 'key-1', 'approver_id': 'independent-reviewer',
                           'public_key_hex': public, 'profiles': [self.profile]}],
            'admitted_manifest_sha256': [digest(self.manifest)]}
        self.recovery_policy_path.write_bytes(canonical(self.recovery_policy_value))
        self.recovery_policy_path.chmod(0o600)
        self.recovery_policy = getattr(self.module, self.policy_class)(self.recovery_policy_path)

    def receipt(self, **changes):
        payload = {'schema_version': self.approval_schema, 'issuer': 'recovery', 'key_id': 'key-1',
                   'approver_id': 'independent-reviewer', 'operation_id': self.manifest['operation_id'],
                   'manifest_sha256': digest(self.manifest), 'issued_at': self.start, 'expires_at': self.expires,
                   'nonce': uuid.uuid4().hex}
        payload.update(changes)
        message, signature = self.root / 'message', self.root / 'signature'
        message.write_bytes(self.module.SIGNATURE_DOMAIN + canonical(payload))
        subprocess.run(['/usr/bin/openssl', 'pkeyutl', '-sign', '-rawin', '-inkey', str(self.key), '-in', str(message),
                        '-out', str(signature)], check=True, capture_output=True)
        return {'payload': copy.deepcopy(payload), 'signature': base64.b64encode(signature.read_bytes()).decode()}

    # The original job and the sealed context.
    def seed_original_job(self):
        if self.adoption_proof:
            adoption._tables(self.policy)  # the adoption job's own tables, as its preparation made them
        with self.policy.connection() as db:
            db.execute("INSERT INTO jobs(id,root,manifest_sha256,status,dispatches,outcome) VALUES (?,?,?,?,1,?)",
                       (self.job_id, str(self.root / 'jobs' / 'original'), 'm' * 64, 'outcome_unknown',
                        canonical(self.outcome).decode()))
            db.execute('INSERT INTO ownership VALUES (?,?)', ('scope', self.job_id))

    def build_context(self, policy=None, job_id=None, original=None):
        job_id = job_id or self.job_id
        context = object.__new__(self.context_class)
        context.job = types.SimpleNamespace(policy=policy or self.policy, identifier=job_id, root=self.root / 'jobs' / 'original')
        context.profile, context.original = self.profile, original or self.original
        context.binding = types.SimpleNamespace(
            backend_storage_token=lambda credential, timeout: types.SimpleNamespace(_get=lambda: 'token', close=lambda: None))
        context.credential = None
        context.phase_identifier = job_id  # the plan family keys its reservation by the phase operation
        context.phase = types.SimpleNamespace(database_snapshot=lambda db: ({}, None, None),
                                              require_dispatch_quiet=lambda db: None, kind='modeled')
        context.upstream = types.SimpleNamespace(request=self.request)
        context.target = types.SimpleNamespace(blob_endpoint='https://storage.invalid', container='container', key='state')
        return context

    # The controller seams that need a live backend.
    def observe(self, output, require_locked):
        self.observations.append('locked' if require_locked else 'after')
        self.on_observe()
        document = copy.deepcopy(self.observation_document())
        return types.SimpleNamespace(verified=lambda: document)

    def request(self, host, method, path, headers, body, *, timeout):
        self.requests.append((method, path))
        return ib.ServiceResponse(200, (('content-length', '0'),), b'')

    # Records.
    def rows(self, sql):
        connection = sqlite3.connect(self.policy.database)
        try:
            return connection.execute(sql).fetchall()
        finally:
            connection.close()

    def latched(self):
        try:
            return self.rows('SELECT issuer, nonce, operation_id, expires_at FROM recovery_expired_v2')
        except sqlite3.OperationalError:
            return []

    def reservations(self):
        try:
            return self.rows('SELECT status FROM native_lease_recoveries')
        except sqlite3.OperationalError:
            return []

    def assert_nothing_happened(self):
        self.assertEqual(self.reservations(), [])
        self.assertEqual(self.requests, [])
        self.assertEqual(self.observations, [])
        self.assertEqual(sorted(path.name for path in (self.root / 'out').iterdir()), [])

    # Actions.
    def execute(self, signed):
        return self.module.execute(self.manifest, signed, context=self.context, policy=self.recovery_policy,
                                   output=self.root / 'out' / uuid.uuid4().hex)

    def refused(self, call):
        with self.assertRaises(AppError) as raised:
            call()
        return raised.exception

    def restart(self):
        clock.reset_process_anchor()
        self.policy = service.ServicePolicy(self.policy_path, initialize=False)
        self.context.job.policy = self.policy
        self.recovery_policy = getattr(self.module, self.policy_class)(self.recovery_policy_path)


class ExecuteLatchTests:
    """The tests every family runs; a family's module mixes this in with its fixture."""

    def another_job_context(self):
        """A valid sealed context for a different original job, in a different service store."""
        other = unittest.TestCase()
        old_contracts.RecoveryPlanContracts.setUp(other)
        self.addCleanup(other.doCleanups)
        job_b = str(uuid.uuid4())
        named = dict(self.original, operation_id=job_b, **({'phase_operation_id': job_b} if self.phase_family else {}))
        return other, self.build_context(policy=other.policy, job_id=job_b, original=named)

    def assert_no_store_touched(self, *stores):
        for store in stores:
            self.assertFalse((store.root / 'clock.json').exists())
            connection = sqlite3.connect(store.database)
            try:
                tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                for name in ('recovery_expired', 'recovery_expired_v2'):
                    if name in tables:
                        self.assertEqual(connection.execute('SELECT count(*) FROM ' + name).fetchone()[0], 0)
            finally:
                connection.close()

    def test_a_restart_with_the_wall_set_back_above_the_mark_cannot_reopen_an_approval_that_has_expired(self):
        signed = self.receipt()
        self.clocks.wall = self.start + 30
        self.on_observe = lambda: (_ for _ in ()).throw(AppError('modeled_backend_unavailable', 'x'))
        self.refused(lambda: self.execute(signed))  # judged open at T30 (the open row), then the observation fails
        self.on_observe = lambda: None
        self.observations.clear()
        self.restart()
        self.clocks.elapse(40)  # true time T70, past the approval's expiry at T60
        self.clocks.step(-30)  # the wall is set to T40: above the mark, inside the window
        self.assertEqual(self.refused(lambda: self.execute(signed)).code, EXPIRED)
        self.assertEqual((self.reservations(), self.requests, self.observations), ([], [], []))

    def test_a_context_whose_job_is_another_jobs_but_whose_copied_fields_are_this_ones_records_nothing(self):
        other, _ = self.another_job_context()
        job_b = str(uuid.uuid4())
        forged = self.build_context(policy=other.policy, job_id=job_b, original=self.original)  # the job is B's, the fields A's
        signed = self.receipt()
        self.clocks.elapse(LIFETIME + 1)
        with self.assertRaises(AppError):
            self.module.execute(self.manifest, signed, context=forged, policy=self.recovery_policy,
                                output=self.root / 'out' / uuid.uuid4().hex)
        self.assert_no_store_touched(other.policy, self.policy)
        self.assert_nothing_happened()

    def test_an_authentic_approval_issued_in_the_future_writes_no_clock_record_and_no_expiry(self):
        signed = self.receipt(issued_at=self.start + 30)  # authentic, but dated ahead of this clock
        anchors = dict(clock._ANCHORS)
        self.refused(lambda: self.execute(signed))
        self.assertFalse((self.policy.root / 'clock.json').exists())
        self.assertEqual(dict(clock._ANCHORS), anchors)
        self.assertEqual(self.latched(), [])
        self.assert_nothing_happened()

    def test_a_backward_step_to_before_the_issue_time_still_reports_the_hold_and_how_to_recover(self):
        signed = self.receipt()
        self.clocks.wall = self.start + 30
        self.on_observe = lambda: (_ for _ in ()).throw(AppError('modeled_backend_unavailable', 'x'))
        self.refused(lambda: self.execute(signed))  # the judgment recorded T+30 before the observation failed
        self.on_observe = lambda: None
        self.observations.clear()
        self.clocks.wall = self.start - 10  # earlier than the approval's own issue time
        self.restart()
        error = self.refused(lambda: self.execute(signed))
        self.assertEqual(error.code, 'clock_moved_backward')
        self.assertIn(RECOVERY_WORDS, error.message)
        self.assertEqual((self.reservations(), self.requests, self.observations), ([], [], []))

    def test_an_approval_that_reuses_an_expired_approvals_issuer_and_nonce_is_judged_on_its_own(self):
        nonce = uuid.uuid4().hex
        early = self.receipt(nonce=nonce, expires_at=self.start + 30)
        manifest_a = copy.deepcopy(self.manifest)
        self.clocks.wall = self.start + 40  # the first approval is over, the manifest and a later approval are not
        with self.assertRaises(AppError):
            self.module.execute(manifest_a, early, context=self.context, policy=self.recovery_policy,
                                output=self.root / 'out' / uuid.uuid4().hex)
        self.assertEqual(len(self.latched()), 1)
        self.manifest = dict(self.manifest, operation_id=str(uuid.uuid4()))  # another operation, same issuer and nonce
        self.write_recovery_policy()
        result = self.execute(self.receipt(nonce=nonce))
        self.assertEqual(result['status'], 'lease_release_independently_observed')
        self.assertEqual(len(self.requests), 1)

    def test_an_expired_approval_for_one_job_writes_nothing_into_another_jobs_store(self):
        other, context_b = self.another_job_context()
        signed = self.receipt()
        self.clocks.elapse(LIFETIME + 1)
        for _ in range(2):  # the same, then once more: nothing accumulates
            with self.assertRaises(AppError):
                self.module.execute(self.manifest, signed, context=context_b, policy=self.recovery_policy,
                                    output=self.root / 'out' / uuid.uuid4().hex)
        for store in (other.policy, self.policy):
            self.assertFalse((store.root / 'clock.json').exists())
            connection = sqlite3.connect(store.database)
            try:
                tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                self.assertFalse(any(name.startswith('recovery_expired') for name in tables) and
                                 connection.execute('SELECT count(*) FROM recovery_expired_v2').fetchone()[0])
            finally:
                connection.close()
        self.assert_nothing_happened()

    def test_an_expired_approval_stays_refused_after_a_backward_step_and_a_restart(self):
        signed = self.receipt()
        self.clocks.elapse(LIFETIME + 1)
        self.refused(lambda: self.execute(signed))  # the verification refuses the elapsed approval, and records it
        self.clocks.wall = self.expires - 10  # the wall clock now reads ten seconds before the expiry
        self.restart()
        self.assertEqual(self.refused(lambda: self.execute(signed)).code, EXPIRED)
        self.assert_nothing_happened()
        self.assertEqual(len(self.latched()), 1)

    def test_the_latch_alone_refuses_when_the_recorded_time_is_gone(self):
        signed = self.receipt()
        self.clocks.elapse(LIFETIME + 1)
        self.refused(lambda: self.execute(signed))
        (self.policy.root / 'clock.json').unlink(missing_ok=True)
        self.clocks.wall = self.expires - 30
        self.restart()
        self.assertEqual(self.refused(lambda: self.execute(signed)).code, EXPIRED)
        self.assert_nothing_happened()

    def test_the_manifest_window_refusal_still_records_the_approvals_expiry(self):
        # The approval ends ten seconds before the manifest. The manifest's own window is refused first, on the bare
        # clock, and that refusal must record the approval's expiry too, or a rollback reopens the approval.
        signed = self.receipt(expires_at=self.expires - 10)
        self.clocks.elapse(LIFETIME)
        self.refused(lambda: self.execute(signed))
        self.assertEqual(len(self.latched()), 1)
        self.clocks.wall = self.expires - 20
        self.restart()
        self.assertEqual(self.refused(lambda: self.execute(signed)).code, EXPIRED)
        self.assert_nothing_happened()

    def test_an_expiry_reached_during_the_backend_observation_is_refused_with_nothing_reserved(self):
        signed = self.receipt()
        self.clocks.wall = self.start + 10
        self.on_observe = lambda: self.clocks.elapse(LIFETIME)  # the observation takes the clock past the expiry
        self.assertEqual(self.refused(lambda: self.execute(signed)).code, EXPIRED)
        self.assertEqual(self.observations, ['locked'])
        self.assertEqual(self.reservations(), [])
        self.assertEqual(self.requests, [])
        self.assertEqual(len(self.latched()), 1)

    def test_a_monotonic_deadline_reached_during_the_observation_is_an_expiry_too(self):
        signed = self.receipt()
        self.clocks.wall = self.start + 10
        real, jump = time.monotonic, [0]
        self.on_observe = lambda: jump.__setitem__(0, 3600)  # the observation outlasts the approval, the wall clock is stuck
        with patch.object(time, 'monotonic', side_effect=lambda: real() + jump[0]):
            self.assertEqual(self.refused(lambda: self.execute(signed)).code, EXPIRED)
        self.assertEqual(self.reservations(), [])
        self.assertEqual(self.requests, [])

    def test_an_expiry_reached_after_the_reservation_is_still_refused_before_the_request(self):
        # The refusal the bare-clock check made just before the request stays, now on the recorded time. The dispatch is
        # spent, nothing was sent, and the outcome is recorded as unknown.
        signed = self.receipt()
        self.clocks.wall = self.start + 10
        calls = []

        def check_then_run_out_of_time(context):
            if self.reservations():
                self.clocks.elapse(LIFETIME)
                calls.append('after-reservation')
        with patch.object(self.context_class, 'check', check_then_run_out_of_time):
            self.assertEqual(self.refused(lambda: self.execute(signed)).code, EXPIRED)
        self.assertEqual(calls, ['after-reservation'])
        self.assertEqual(self.requests, [])
        self.assertEqual(self.reservations(), [('outcome_unknown',)])

    def test_a_backward_step_before_the_expiry_holds_the_dispatch_and_says_how_to_recover(self):
        signed = self.receipt()
        self.clocks.wall = self.start + 30
        failure = AppError('modeled_backend_unavailable', 'x')
        self.on_observe = lambda: (_ for _ in ()).throw(failure)
        self.refused(lambda: self.execute(signed))  # the first judgment recorded T+30 before the observation failed
        self.on_observe = lambda: None
        self.observations.clear()
        self.clocks.step(-20)  # reads T+10, earlier than the recorded T+30
        for attempt in range(2):
            error = self.refused(lambda: self.execute(signed))
            self.assertEqual(error.code, 'clock_moved_backward')
            self.assertIn('reads %d' % (self.start + 10), error.message)
            self.assertIn('time %d' % (self.start + 30), error.message)
            self.assertIn(RECOVERY_WORDS, error.message)
            self.restart()  # the hold survives a restart: it comes from the recorded time
        self.assertEqual((self.reservations(), self.requests, self.observations), ([], [], []))
        self.assertEqual(self.latched(), [])
        self.clocks.wall = self.start + 31  # recovery: the clock reads at or after the recorded time
        self.assertEqual(self.execute(signed)['status'], 'lease_release_independently_observed')

    def test_a_refusal_for_a_forged_approval_records_nothing_and_moves_no_clock(self):
        forged = self.receipt()
        forged['signature'] = forged['signature'][:-4] + 'AAAA'
        self.clocks.elapse(LIFETIME + 1)
        self.refused(lambda: self.execute(forged))
        self.assertEqual(self.latched(), [])
        self.assertFalse((self.policy.root / 'clock.json').exists())

    def test_an_open_window_dispatches_once_and_records_no_expiry(self):
        self.clocks.wall = self.start + 10
        result = self.execute(self.receipt())
        self.assertEqual(result['status'], 'lease_release_independently_observed')
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.requests[0][0], 'PUT')
        self.assertEqual(self.reservations(), [('release_observed',)])
        self.assertEqual(self.latched(), [])

    def test_the_section_that_reserves_the_dispatch_is_the_shared_one(self):
        from intune_iac import validity
        self.clocks.wall = self.start + 10
        with patch.object(validity, 'critical', wraps=validity.critical) as section:
            self.execute(self.receipt())
        self.assertEqual(section.call_count, 2)  # the gate before any observation, and the reservation


class LeaseRecoveryTests(ExecuteLatchTests, RecoveryFixture):
    module = lease
    policy_class = 'RecoveryPolicy'
    context_class = lease.LaboratoryRecoveryContext
    policy_schema = 'native-lease-recovery-policy/1'
    operation_schema = 'native-lease-recovery-operation/1'
    action = 'release_exact_existing_native_lease'
    approval_schema = 'signed-native-lease-recovery-approval/1'
    profile = 'laboratory_native_lease_recovery'


class CommittedStateRecoveryTests(ExecuteLatchTests, RecoveryFixture):
    module = committed
    policy_class = 'CommittedRecoveryPolicy'
    context_class = committed.LaboratoryCommittedRecoveryContext
    policy_schema = 'committed-state-lease-recovery-policy/1'
    operation_schema = 'committed-state-lease-recovery-operation/1'
    action = 'release_exact_original_committed_state_lease'
    approval_schema = 'signed-committed-state-lease-recovery-approval/1'
    profile = 'laboratory_committed_state_lease_recovery'


class AdoptionRecoveryTests(ExecuteLatchTests, RecoveryFixture):
    module = adoption_recovery
    policy_class = 'AdoptionRecoveryPolicy'
    context_class = adoption_recovery.LaboratoryAdoptionRecoveryContext
    policy_schema = 'adoption-native-lease-recovery-policy/1'
    operation_schema = 'adoption-native-lease-recovery-operation/1'
    action = 'release_exact_original_adoption_lease'
    approval_schema = 'signed-adoption-native-lease-recovery-approval/1'
    profile = 'laboratory_adoption_native_lease_recovery'
    adoption_proof = 'original_baseline'


class AdoptionPlanRecoveryTests(ExecuteLatchTests, RecoveryFixture):
    module = plan_recovery
    policy_class = 'AdoptionPlanRecoveryPolicy'
    context_class = plan_recovery.LaboratoryAdoptionPlanRecoveryContext
    policy_schema = 'adoption-plan-native-lease-recovery-policy/1'
    operation_schema = 'adoption-plan-native-lease-recovery-operation/1'
    action = 'release_exact_stopped_adoption_plan_lease'
    approval_schema = 'signed-adoption-plan-native-lease-recovery-approval/1'
    profile = 'laboratory_adoption_plan_native_lease_recovery'
    adoption_proof = 'approved_adoption_successor'
    phase_family = True

    def test_a_context_whose_phase_is_another_phase_but_whose_copied_fields_are_this_ones_records_nothing(self):
        forged = self.build_context(original=self.original)
        forged.phase_identifier = str(uuid.uuid4())  # the job and the copied fields are A's, the phase is another
        signed = self.receipt()
        self.clocks.elapse(LIFETIME + 1)
        with self.assertRaises(AppError):
            self.module.execute(self.manifest, signed, context=forged, policy=self.recovery_policy,
                                output=self.root / 'out' / uuid.uuid4().hex)
        self.assert_no_store_touched(self.policy)
        self.assert_nothing_happened()


if __name__ == '__main__':
    unittest.main()
