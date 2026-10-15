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
    def observation_document(self):
        return {'original': self.original, 'state': self.state, 'metadata': {}, 'locked': True, 'profile': self.profile}

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
        with self.policy.connection() as db:
            db.execute("INSERT INTO jobs(id,root,manifest_sha256,status,dispatches,outcome) VALUES (?,?,?,?,1,?)",
                       (self.job_id, str(self.root / 'jobs' / 'original'), 'm' * 64, 'outcome_unknown',
                        canonical(self.outcome).decode()))
            db.execute('INSERT INTO ownership VALUES (?,?)', ('scope', self.job_id))

    def build_context(self):
        context = object.__new__(self.context_class)
        context.job = types.SimpleNamespace(policy=self.policy, identifier=self.job_id, root=self.root / 'jobs' / 'original')
        context.profile, context.original = self.profile, self.original
        context.binding = types.SimpleNamespace(
            backend_storage_token=lambda credential, timeout: types.SimpleNamespace(_get=lambda: 'token', close=lambda: None))
        context.credential = None
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
            return self.rows('SELECT issuer, nonce, operation_id, expires_at FROM recovery_expired')
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


if __name__ == '__main__':
    unittest.main()
