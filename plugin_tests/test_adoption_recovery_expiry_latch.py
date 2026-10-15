"""The recovery-plan approval of an adoption stays expired across a backward clock step and a restart (PKG-TIME-AUTHZ-B,
item 3).

worker_adoption_reconcile judged its receipt on the bare wall clock in _verify and again in the permit's check_active.
Both now go through the shared critical section (intune_iac.validity) on the same adoption policy store, with the same
capped adoption_expired table: the receipt is authenticated first, then its window is judged and a reached expiry is
recorded and refused. A receipt that does not authenticate records nothing.

Not covered here, and not changed: RecoveryPlanJob.run still consumes the approval in its own transaction after _verify
(see the report). The permit's check_active is the first call of the dispatch, so an approval consumed in that gap is
refused before any host or broker work.
"""
import sqlite3
import time
import types
import unittest
import uuid
from unittest.mock import patch

from intune_iac import clock, validity
from intune_iac import worker_adoption as adoption
from intune_iac import worker_adoption_reconcile as bridge
from intune_iac import worker_service as service
from intune_iac.io import AppError, digest
from plugin_tests import test_worker_adoption_reconcile_r4 as old_contracts
from plugin_tests.test_adoption_expiry_latch import BOUND, FORK, LIFETIME, RECOVERY_WORDS, inject, watchdog_refusals
from plugin_tests.test_clock_authority import Clocks

EXPIRED = 'adoption_recovery_signature_expired'


class RecoveryFixture(unittest.TestCase):
    def setUp(self):
        self.start = int(time.time())
        self.clocks = Clocks(self.start)
        inject(self, self.clocks)
        old_contracts.RecoveryPlanContracts.setUp(self)
        self.expires = self.start + LIFETIME
        self.manifest.update(operation_id=str(uuid.uuid4()), prepared_at=self.start, expires_at=self.expires,
                             identity_binding_sha256='i' * 64, host_spec={}, original_facts={},
                             recovery_binding={'binding': 'modeled'})
        adoption._tables(self.policy)  # the original adoption job prepared the store, expiry table included
        bridge._tables(self.policy)
        self.job_root = self.root / 'jobs' / 'plan-job'
        self.job_root.mkdir(mode=0o700)
        self.job = object.__new__(bridge.RecoveryPlanJob)
        self.job.policy, self.job.root, self.job.manifest = self.policy, self.job_root, self.manifest
        self.job.sha256, self.job.identifier = digest(self.manifest), self.manifest['operation_id']
        self.job.original = types.SimpleNamespace(identifier='original-op', manifest={}, sha256='a' * 64)
        with self.policy.connection() as db:
            db.execute('INSERT INTO adoption_recovery_plans(operation_id,original_operation_id,manifest_sha256,root,status) VALUES (?,?,?,?,?)',
                       (self.job.identifier, 'original-op', self.job.sha256, str(self.job_root), 'prepared'))
            db.execute('INSERT INTO ownership VALUES (?,?)', ('scope', 'original-op'))
        self.dispatched, self.permits, self.manifest_time_rule = [], [], False
        self.native, self.proxy = self.root / 'native', self.root / 'proxy'
        self.native.mkdir(mode=0o700)
        self.proxy.mkdir(mode=0o700)
        self.runtime = object.__new__(bridge.RecoveryPlanRuntime)
        facts = {'fresh_observation': {'identity_binding_sha256': 'i' * 64}}
        for patcher in (patch.object(bridge.RecoveryPlanJob, '_check', self.check),
                        patch.object(bridge.RecoveryPlanRuntime, 'check', return_value=None),
                        patch.object(bridge, '_completion', return_value=facts),
                        patch.object(bridge, '_binding', return_value=self.manifest['recovery_binding']),
                        patch.object(bridge, '_original_row', return_value=None),
                        patch.object(bridge.service, '_host_spec',
                                     return_value=types.SimpleNamespace(job_root=self.native, broker_root=self.proxy)),
                        patch.object(bridge.service, '_scopes', return_value=['scope']),
                        patch.object(bridge.service, '_controller_identity', return_value='controller-start'),
                        patch.object(bridge.RecoveryPlanJob, '_dispatch', self.dispatch)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def check(self, *, expiry=True):
        """RecoveryPlanJob._check models the manifest's own time rule (validate_manifest) when a test turns it on."""
        now = int(time.time())
        if expiry and self.manifest_time_rule and not self.manifest['prepared_at'] <= now + 5 < self.manifest['expires_at']:
            raise AppError('adoption_recovery_plan_expired', 'The manifest window is closed.')

    def dispatch(self, payload, runtime, spec, receipt_raw):
        self.dispatched.append('plan')
        self.permits.append(bridge._Permit(self.job, payload, runtime))
        return {'status': 'modeled-dispatch'}

    def rows(self, sql):
        connection = sqlite3.connect(self.policy.database)
        try:
            return connection.execute(sql).fetchall()
        finally:
            connection.close()

    def latched(self):
        return self.rows('SELECT issuer, nonce, operation_id, expires_at FROM adoption_expired')

    def receipt(self, **changes):
        return old_contracts.RecoveryPlanContracts.signed(
            self, issued_at=changes.pop('issued_at', self.start), expires_at=changes.pop('expires_at', self.expires), **changes)

    def verify(self, receipt):
        return bridge._verify(self.policy, self.manifest, receipt)

    def run_job(self, receipt):
        return self.job.run(receipt, runtime=self.runtime, completion={})

    def refused(self, call):
        with self.assertRaises(AppError) as raised:
            call()
        return raised.exception

    def restart(self):
        clock.reset_process_anchor()
        self.job.policy = self.policy = service.ServicePolicy(self.policy_path, initialize=False)

    def assert_nothing_consumed(self):
        self.assertEqual(self.rows('SELECT * FROM consumed'), [])
        self.assertEqual(self.rows('SELECT * FROM approval_transcripts'), [])
        self.assertEqual(self.rows('SELECT status, dispatches FROM adoption_recovery_plans'), [('prepared', 0)])
        self.assertEqual(self.dispatched, [])


class VerifyLatchTests(RecoveryFixture):
    def test_an_expired_receipt_stays_refused_after_a_backward_step_and_a_restart(self):
        signed = self.receipt()
        self.clocks.elapse(LIFETIME + 1)
        self.assertEqual(self.refused(lambda: self.verify(signed)).code, EXPIRED)
        self.assertEqual(len(self.latched()), 1)
        self.clocks.wall = self.expires - 10
        self.restart()
        self.assertEqual(self.refused(lambda: self.verify(signed)).code, EXPIRED)
        (self.policy.root / 'clock.json').unlink()  # the latch alone refuses
        self.clocks.wall = self.expires - 30
        self.restart()
        self.assertEqual(self.refused(lambda: self.verify(signed)).code, EXPIRED)
        self.assertEqual(len(self.latched()), 1)

    def test_a_backward_step_before_the_expiry_holds_with_both_times_and_the_recovery_words(self):
        signed = self.receipt()
        self.clocks.wall = self.start + 30
        self.assertEqual(self.verify(signed), signed['payload'])
        self.clocks.step(-20)
        error = self.refused(lambda: self.verify(signed))
        self.assertEqual(error.code, 'clock_moved_backward')
        self.assertIn('reads %d' % (self.start + 10), error.message)
        self.assertIn('time %d' % (self.start + 30), error.message)
        self.assertIn(RECOVERY_WORDS, error.message)
        self.assertEqual(self.latched(), [])

    def test_an_open_window_returns_the_payload_and_records_no_expiry(self):
        signed = self.receipt()
        self.assertEqual(self.verify(signed), signed['payload'])
        self.assertEqual(self.latched(), [])


class UnauthenticatedInputTests(RecoveryFixture):
    def assert_untouched(self):
        self.assertEqual(self.latched(), [])
        self.assertFalse((self.policy.root / 'clock.json').exists())
        self.assertEqual(clock._ANCHORS, {})

    def test_a_forged_expired_receipt_is_refused_as_before_and_records_nothing(self):
        forged = self.receipt()
        forged['signature'] = forged['signature'][:-4] + 'AAAA'
        self.clocks.elapse(LIFETIME + 1)
        self.assertEqual(self.refused(lambda: self.verify(forged)).code, EXPIRED)
        self.assert_untouched()

    def test_a_forged_receipt_inside_its_window_is_refused_as_before_and_records_nothing(self):
        forged = self.receipt()
        forged['signature'] = forged['signature'][:-4] + 'AAAA'
        self.assertEqual(self.refused(lambda: self.verify(forged)).code, 'adoption_recovery_signature_invalid')
        self.assert_untouched()

    def test_an_expired_receipt_from_an_unknown_signer_is_refused_as_before_and_records_nothing(self):
        unknown = self.receipt(key_id='unknown-key')
        self.clocks.elapse(LIFETIME + 1)
        self.assertEqual(self.refused(lambda: self.verify(unknown)).code, EXPIRED)
        self.assert_untouched()

    def test_a_revoked_signer_cannot_write_expiry_records(self):
        with self.policy.connection() as db:
            db.execute('INSERT INTO revoked VALUES (?,?)', ('fixture', 'key'))
        self.assertEqual(self.refused(lambda: self.verify(self.receipt())).code, 'adoption_recovery_signer_revoked')
        for signed in (self.receipt(), self.receipt()):
            self.clocks.elapse(LIFETIME + 1)
            self.assertEqual(self.refused(lambda: self.verify(signed)).code, EXPIRED)
        self.assert_untouched()

    def test_a_future_issued_receipt_is_refused_as_before_and_records_nothing(self):
        self.assertEqual(self.refused(lambda: self.verify(self.receipt(issued_at=self.start + 30))).code, EXPIRED)
        self.assert_untouched()


class RunLatchTests(RecoveryFixture):
    def test_an_expired_receipt_stays_refused_by_run_after_a_backward_step_and_a_restart(self):
        signed = self.receipt()
        self.clocks.elapse(LIFETIME + 1)
        self.assertEqual(self.refused(lambda: self.run_job(signed)).code, EXPIRED)
        self.clocks.wall = self.expires - 10
        self.restart()
        self.assertEqual(self.refused(lambda: self.run_job(signed)).code, EXPIRED)
        self.assert_nothing_consumed()
        self.assertEqual(len(self.latched()), 1)

    def test_the_manifest_expiry_refusal_still_records_the_receipts_expiry(self):
        self.manifest_time_rule = True
        signed = self.receipt()
        self.clocks.elapse(LIFETIME + 1)
        self.assertEqual(self.refused(lambda: self.run_job(signed)).code, 'adoption_recovery_plan_expired')
        self.assertEqual(len(self.latched()), 1)
        self.clocks.wall = self.expires - 20
        self.restart()
        self.assertEqual(self.refused(lambda: self.run_job(signed)).code, EXPIRED)
        self.assert_nothing_consumed()

    def spec_that(self, action):
        """_host_spec runs right after _verify and before the consumption: a stand-in for the time that gap takes."""
        def spec(*args):
            action()
            return types.SimpleNamespace(job_root=self.native, broker_root=self.proxy)
        return patch.object(bridge.service, '_host_spec', side_effect=spec)

    def test_an_expiry_reached_between_verification_and_consumption_is_refused_with_nothing_consumed(self):
        signed = self.receipt()
        self.clocks.wall = self.start + 10
        with self.spec_that(lambda: self.clocks.elapse(LIFETIME)):
            self.assertEqual(self.refused(lambda: self.run_job(signed)).code, EXPIRED)
        self.assert_nothing_consumed()
        self.assertEqual(len(self.latched()), 1)

    def test_an_expiry_latched_by_another_process_between_verification_and_consumption_refuses_the_consumption(self):
        signed = self.receipt()
        paused, release, queue = FORK.Event(), FORK.Event(), FORK.Queue()

        def process_a():
            self.clocks.wall = self.start + 10  # this process reads a time inside the window throughout

            def pause():
                paused.set()
                release.wait(BOUND)
            try:
                with self.spec_that(pause):
                    self.run_job(signed)
                queue.put(('ok', None))
            except AppError as error:
                queue.put(('refused', error.code))
        process = FORK.Process(target=process_a, daemon=True)
        process.start()
        self.addCleanup(lambda: process.is_alive() and process.terminate())
        self.assertTrue(paused.wait(BOUND))
        self.clocks.elapse(LIFETIME + 1)  # process B reaches the expiry and latches it
        self.assertEqual(self.refused(lambda: self.run_job(signed)).code, EXPIRED)
        release.set()
        self.assertEqual(queue.get(timeout=BOUND), ('refused', EXPIRED))
        process.join(BOUND)
        self.assert_nothing_consumed()

    def test_an_open_window_consumes_and_dispatches_once(self):
        self.clocks.wall = self.start + 10
        self.assertEqual(self.run_job(self.receipt())['status'], 'modeled-dispatch')
        self.assertEqual(self.rows('SELECT status, dispatches FROM adoption_recovery_plans'), [('running', 1)])
        self.assertEqual(len(self.rows('SELECT * FROM consumed')), 1)
        self.assertEqual(self.latched(), [])


class PermitLatchTests(RecoveryFixture):
    def running(self, at):
        self.clocks.wall = at
        self.run_job(self.receipt())
        return self.permits[-1]

    def test_check_active_refuses_after_the_expiry_and_after_a_backward_step_that_follows_it(self):
        permit = self.running(self.start + 10)
        permit.check_active()
        self.clocks.elapse(LIFETIME)
        self.assertEqual(self.refused(permit.check_active).code, 'adoption_recovery_plan_expired')
        self.clocks.wall = self.expires - 10
        (self.policy.root / 'clock.json').unlink()
        clock.reset_process_anchor()
        self.assertEqual(self.refused(permit.check_active).code, 'adoption_recovery_plan_expired')
        self.assertEqual(len(self.latched()), 1)

    def test_the_open_path_of_check_active_takes_no_lock_and_persists_nothing(self):
        permit = self.running(self.start + 10)
        floor, database = self.policy.root / 'clock.json', self.policy.database
        before = (floor.read_bytes(), floor.stat().st_mtime_ns, database.read_bytes(), database.stat().st_mtime_ns)
        with patch.object(validity.fcntl, 'flock', side_effect=AssertionError('a lock was taken')), \
                patch.object(validity, 'critical', side_effect=AssertionError('the section was entered')):
            for _ in range(100):
                self.clocks.elapse(0.2)
                permit.check_active()
        self.assertEqual((floor.read_bytes(), floor.stat().st_mtime_ns, database.read_bytes(), database.stat().st_mtime_ns), before)

    def test_a_write_reservation_from_another_process_is_never_refused_during_a_watchdog_loop(self):
        permit = self.running(self.start + 10)
        refused, errors = watchdog_refusals(self, self.policy.database, permit.check_active,
                                            tick=lambda: self.clocks.elapse(0.01))
        self.assertEqual(errors, [])
        self.assertEqual(refused, [])

    def test_a_closed_window_refuses_even_when_the_store_is_busy_and_latches_on_a_later_call(self):
        permit = self.running(self.start + 10)
        self.clocks.elapse(LIFETIME)
        holder = sqlite3.connect(self.policy.database, timeout=0, isolation_level=None)
        self.addCleanup(holder.close)
        holder.execute('BEGIN IMMEDIATE')  # another writer holds the reservation: the latch cannot be written now
        self.assertEqual(self.refused(permit.check_active).code, 'adoption_recovery_plan_expired')
        holder.execute('ROLLBACK')
        self.assertEqual(self.latched(), [])
        self.assertEqual(self.refused(permit.check_active).code, 'adoption_recovery_plan_expired')
        self.assertEqual(len(self.latched()), 1)

    def test_check_active_refuses_after_an_expiry_reached_in_another_process(self):
        permit = self.running(self.start + 10)
        queue = FORK.Queue()

        def other_process():
            self.clocks.wall = self.expires + 1
            try:
                bridge._Permit(self.job, permit.payload, self.runtime).check_active()
                queue.put(('ok', None))
            except AppError as error:
                queue.put(('refused', error.code))
        process = FORK.Process(target=other_process, daemon=True)
        process.start()
        self.addCleanup(lambda: process.is_alive() and process.terminate())
        self.assertEqual(queue.get(timeout=BOUND), ('refused', 'adoption_recovery_plan_expired'))
        process.join(BOUND)
        self.assertEqual(self.clocks.now(), self.start + 10)
        self.assertEqual(self.refused(permit.check_active).code, 'adoption_recovery_plan_expired')
        (self.policy.root / 'clock.json').unlink()
        clock.reset_process_anchor()
        self.clocks.wall = self.expires - 30
        self.assertEqual(self.refused(permit.check_active).code, 'adoption_recovery_plan_expired')

    def test_check_active_is_held_by_a_backward_step_before_the_expiry(self):
        permit = self.running(self.start + 30)
        self.clocks.step(-20)
        error = self.refused(permit.check_active)
        self.assertEqual(error.code, 'clock_moved_backward')
        self.assertIn(RECOVERY_WORDS, error.message)
        self.assertEqual(self.latched(), [])
        self.clocks.wall = self.start + 31
        permit.check_active()

    def test_check_active_inserts_nothing_when_the_window_is_open(self):
        permit = self.running(self.start + 10)
        tables = ('adoption_recovery_plans', 'consumed', 'ownership', 'events', 'approval_transcripts', 'revoked',
                  'adoption_expired')
        before = [self.rows('SELECT * FROM ' + name) for name in tables]
        self.clocks.elapse(5)
        permit.check_active()
        self.assertEqual([self.rows('SELECT * FROM ' + name) for name in tables], before)

    def test_the_manifest_expiry_refusal_in_check_active_records_the_expiry_before_refusing(self):
        permit = self.running(self.start + 10)
        self.manifest_time_rule = True
        self.clocks.elapse(LIFETIME)
        self.assertEqual(self.refused(permit.check_active).code, 'adoption_recovery_plan_expired')
        self.assertEqual(len(self.latched()), 1)
        self.manifest_time_rule = False
        self.clocks.wall = self.expires - 20
        clock.reset_process_anchor()
        self.assertEqual(self.refused(permit.check_active).code, 'adoption_recovery_plan_expired')

    def test_a_signer_revoked_after_dispatch_is_still_refused(self):
        permit = self.running(self.start + 10)
        with self.policy.connection() as db:
            db.execute('INSERT INTO revoked VALUES (?,?)', ('fixture', 'key'))
        self.assertEqual(self.refused(permit.check_active).code, 'adoption_recovery_permit_revoked')


if __name__ == '__main__':
    unittest.main()
