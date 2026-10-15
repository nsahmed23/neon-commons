"""An expired service approval stays expired across a backward clock step and a restart (PKG-TIME-AUTHZ-C, worker_service).

ServiceJob.run judged the signed receipt's expiry on the bare wall clock in ServicePolicy.verify, and the manifest's
window on the bare clock in validate_manifest, then consumed the approval in a transaction with no window judgment of
its own. A refusal at or after the expiry recorded nothing, so a clock step back before the expiry and a restart reopened
the same receipt. The permit that gates every broker request had the same flaw (a bare wall read, then a plain read of
the job state, then the call).

The judgment is now the shared one (intune_iac.validity) on the service store's own directory, database and
service_expired table: verify authenticates the receipt and then judges it in the critical section, the consumption is
the second consumer, ServicePermit.check_active (the authorization check that gates every request) enters the same
section and commits a marker, and ServicePermit.poll_active (the watchdog) judges read-only and never authorizes.

Each test drives the public call (ServiceJob.run, the permit's check_active) against a real ServicePolicy store and a
real signature, with injected wall and monotonic clocks. Only the controller seams that need a live host or broker are
modeled: the runtime and input checks and the dispatch itself.
"""
import os
import sqlite3
import time
import types
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from intune_iac import clock, validity
from intune_iac import worker_service as service
from intune_iac.io import AppError, digest
from plugin_tests import test_worker_adoption_reconcile_r4 as old_contracts
from plugin_tests.test_adoption_expiry_latch import BOUND, FORK, LIFETIME, RECOVERY_WORDS, inject, race_with_a_latch, watchdog_refusals
from plugin_tests.test_clock_authority import Clocks

EXPIRED = 'service_signature_expired'


class ServiceFixture(unittest.TestCase):
    def setUp(self):
        self.start = int(time.time())
        self.clocks = Clocks(self.start)
        inject(self, self.clocks)
        old_contracts.RecoveryPlanContracts.setUp(self)
        self.expires = self.start + LIFETIME
        self.manifest = {'schema_version': service.VERSION, 'operation_id': str(uuid.uuid4()),
                         'profile': 'native_docker_laboratory_protocol', 'prepared_at': self.start,
                         'expires_at': self.expires, 'saved_plan_sha256': None,
                         'host_spec': {'modeled': True}, 'execution_binding_sha256': 'e' * 64, 'broker_policy': {}}
        self.job_root = self.root / 'jobs' / 'service-job'
        self.job_root.mkdir(mode=0o700)
        for name in ('source', 'control', 'job', 'broker'):
            (self.root / name).mkdir(mode=0o700)
        self.spec = types.SimpleNamespace(source_root=str(self.root / 'source'), source_sha256='s' * 64,
                                          control_root=str(self.root / 'control'), control_sha256='c' * 64,
                                          job_root=str(self.root / 'job'), broker_root=str(self.root / 'broker'))
        self.job = object.__new__(service.ServiceJob)
        self.job.policy, self.job.root, self.job.manifest = self.policy, self.job_root, self.manifest
        self.job.sha256, self.job.identifier = digest(self.manifest), self.manifest['operation_id']
        with self.policy.connection() as db:
            db.execute('INSERT INTO jobs(id,root,manifest_sha256,status) VALUES (?,?,?,?)',
                       (self.job.identifier, str(self.job_root), self.job.sha256, 'prepared'))
            db.execute('INSERT INTO ownership VALUES (?,?)', ('scope', self.job.identifier))
        self.dispatched, self.manifest_time_rule = [], False
        self.runtime = object.__new__(service.ServiceRuntime)
        self.runtime.certificate = self.runtime.private_key = self.runtime.credentials = self.runtime.upstream = None
        self.runtime.state_contracts, self.runtime.precondition, self.runtime.binding = {}, None, None
        for patcher in (patch.object(service.ServiceJob, '_check', self.check),
                        patch.object(service.ServiceRuntime, 'check', return_value=None),
                        patch.object(service, '_host_spec', return_value=self.spec),
                        patch.object(service.host, 'directory_binding',
                                     side_effect=lambda root: {'sha256': 's' * 64 if root == self.spec.source_root else 'c' * 64}),
                        patch.object(service.ServiceJob, 'status', return_value={'status': 'modeled-dispatch'}),
                        patch.object(service.broker, 'laboratory_guard', side_effect=lambda binding, recheck: object()),
                        patch.object(service.broker, 'EgressBroker',
                                     side_effect=lambda *args, **kwargs: types.SimpleNamespace(native_recovery_record=dict)),
                        patch.object(service.broker, 'UnixBrokerServer',
                                     side_effect=lambda *args, **kwargs: types.SimpleNamespace(serve=lambda: None, close=lambda: None)),
                        patch.object(service.host, 'launch', side_effect=self.launch),
                        patch.object(service, '_scopes', return_value=['scope']),
                        patch.object(service, '_controller_identity', return_value='controller-start')):
            patcher.start()
            self.addCleanup(patcher.stop)

    # The controller seams that need a live host or broker.
    def check(self, *, expiry=True):
        """ServiceJob._check models the manifest's own time rule (validate_manifest) when a test turns it on."""
        now = int(time.time())
        if expiry and self.manifest_time_rule and not self.manifest['prepared_at'] <= now + 5 < self.manifest['expires_at']:
            raise AppError('service_manifest_expired', 'The manifest window is closed.')

    def launch(self, spec, root):
        """The host launch: the only call that reaches the worker. A refused approval never gets here."""
        self.dispatched.append('service')
        return {'status': 'complete'}

    # Records.
    def rows(self, sql):
        connection = sqlite3.connect(self.policy.database)
        try:
            return connection.execute(sql).fetchall()
        finally:
            connection.close()

    def consumed(self):
        return self.rows('SELECT operation_id FROM consumed')

    def latched(self):
        return self.table_rows('SELECT issuer, nonce, operation_id, expires_at FROM service_expired')

    def table_rows(self, sql):
        """Rows of a table the controller creates on first use; none when it was never created."""
        try:
            return self.rows(sql)
        except sqlite3.OperationalError:
            return []

    def job_row(self):
        return self.rows('SELECT status, cancelled, dispatches FROM jobs')[0]

    def assert_nothing_happened(self):
        self.assertEqual(self.consumed(), [])
        self.assertEqual(self.rows('SELECT * FROM approval_transcripts'), [])
        self.assertEqual(self.job_row(), ('prepared', 0, 0))
        self.assertEqual(self.dispatched, [])

    # Actions.
    def receipt(self, **changes):
        return old_contracts.RecoveryPlanContracts.signed(
            self, service.SIGNATURE_DOMAIN, schema_version='signed-worker-service-approval/1',
            issued_at=changes.pop('issued_at', self.start), expires_at=changes.pop('expires_at', self.expires), **changes)

    def run_job(self, receipt):
        return self.job.run(receipt, runtime=self.runtime)

    def refused(self, call):
        with self.assertRaises(AppError) as raised:
            call()
        return raised.exception

    def restart(self):
        clock.reset_process_anchor()
        self.job.policy = self.policy = service.ServicePolicy(self.policy_path, initialize=False)

    def dispatch_running(self, at=None):
        """The job as the consumption leaves it (approval consumed, job running, this process the controller), and the
        permit a dispatch would hold, built at a given time. A finished modeled launch would deactivate its own permit."""
        if at is not None:
            self.clocks.wall = at
        payload = self.receipt()['payload']
        with self.policy.connection() as db:
            db.execute('INSERT INTO consumed VALUES (?,?,?,?)', (payload['issuer'], payload['nonce'], self.job.identifier, self.job.sha256))
            db.execute("UPDATE jobs SET status='running',dispatches=1,controller_pid=?,controller_start='controller-start' WHERE id=?",
                       (os.getpid(), self.job.identifier))
        return service.ServicePermit(service._SEAL, self.job, payload, self.runtime)


class DispatchLatchTests(ServiceFixture):
    def test_an_expired_receipt_stays_refused_after_a_backward_step_and_a_restart(self):
        signed = self.receipt()
        self.clocks.elapse(LIFETIME + 1)
        self.assertEqual(self.refused(lambda: self.run_job(signed)).code, EXPIRED)
        self.clocks.wall = self.expires - 10  # the wall clock now reads ten seconds before the expiry
        self.restart()
        self.assertEqual(self.refused(lambda: self.run_job(signed)).code, EXPIRED)
        self.assert_nothing_happened()
        self.assertEqual(len(self.latched()), 1)

    def test_the_latch_alone_refuses_when_the_recorded_time_is_gone(self):
        signed = self.receipt()
        self.clocks.elapse(LIFETIME + 1)
        self.refused(lambda: self.run_job(signed))
        (self.policy.root / 'clock.json').unlink(missing_ok=True)
        self.clocks.wall = self.expires - 30
        self.restart()
        self.assertEqual(self.refused(lambda: self.run_job(signed)).code, EXPIRED)
        self.assert_nothing_happened()

    def test_an_expiry_reached_between_the_verification_and_the_consumption_is_refused_with_nothing_consumed(self):
        signed = self.receipt()
        self.clocks.wall = self.start + 10
        real = service.ServicePolicy.verify

        def verify_then_run_out_of_time(policy, manifest, receipt):
            payload = real(policy, manifest, receipt)
            self.clocks.elapse(LIFETIME)  # the clock passes the expiry before the approval is consumed
            return payload
        with patch.object(service.ServicePolicy, 'verify', verify_then_run_out_of_time):
            self.assertEqual(self.refused(lambda: self.run_job(signed)).code, EXPIRED)
        self.assert_nothing_happened()
        self.assertEqual(len(self.latched()), 1)

    def test_a_backward_step_before_the_expiry_holds_the_dispatch_and_says_how_to_recover(self):
        signed = self.receipt()
        self.clocks.wall = self.start + 30
        self.assertEqual(self.run_job(signed)['status'], 'modeled-dispatch')  # the judgment recorded T+30
        with self.policy.connection() as db:  # put the job back as prepared, so the model can ask again
            db.execute('DELETE FROM consumed')
            db.execute('DELETE FROM approval_transcripts')
            db.execute("UPDATE jobs SET status='prepared',dispatches=0,controller_pid=NULL,controller_start=NULL")
        self.dispatched.clear()
        self.clocks.step(-20)  # reads T+10, earlier than the recorded T+30
        for attempt in range(2):
            error = self.refused(lambda: self.run_job(signed))
            self.assertEqual(error.code, 'clock_moved_backward')
            self.assertIn('reads %d' % (self.start + 10), error.message)
            self.assertIn('time %d' % (self.start + 30), error.message)
            self.assertIn(RECOVERY_WORDS, error.message)
            self.restart()  # the hold survives a restart: it comes from the recorded time
        self.assert_nothing_happened()
        self.assertEqual(self.latched(), [])
        self.clocks.wall = self.start + 31  # recovery: the clock reads at or after the recorded time
        self.assertEqual(self.run_job(signed)['status'], 'modeled-dispatch')
        self.assertEqual(self.dispatched, ['service'])

    def test_the_manifest_expiry_refusal_still_records_the_receipts_expiry(self):
        # validate_manifest (ServiceJob._check) refuses on the bare wall clock before anything else; the receipt's
        # expiry must be recorded there too, or a rollback after that first refusal reopens the receipt.
        self.manifest_time_rule = True
        signed = self.receipt()
        self.clocks.elapse(LIFETIME + 1)
        self.assertEqual(self.refused(lambda: self.run_job(signed)).code, 'service_manifest_expired')
        self.assertEqual(len(self.latched()), 1)
        self.clocks.wall = self.expires - 20
        self.restart()
        self.assertEqual(self.refused(lambda: self.run_job(signed)).code, EXPIRED)
        self.assert_nothing_happened()

    def test_a_manifest_refusal_does_not_record_anything_for_a_receipt_that_does_not_authenticate(self):
        self.manifest_time_rule = True
        forged = self.receipt()
        forged['signature'] = forged['signature'][:-4] + 'AAAA'
        self.clocks.elapse(LIFETIME + 1)
        self.assertEqual(self.refused(lambda: self.run_job(forged)).code, 'service_manifest_expired')
        self.assertEqual(self.latched(), [])
        self.assertFalse((self.policy.root / 'clock.json').exists())

    def test_a_forged_expired_receipt_is_refused_as_the_time_error_and_records_nothing(self):
        forged = self.receipt()
        forged['signature'] = forged['signature'][:-4] + 'AAAA'
        self.clocks.elapse(LIFETIME + 1)
        self.assertEqual(self.refused(lambda: self.run_job(forged)).code, EXPIRED)
        self.assertEqual(self.latched(), [])
        self.assertFalse((self.policy.root / 'clock.json').exists())

    def test_an_open_window_dispatches_once_and_records_no_expiry(self):
        self.clocks.wall = self.start + 10
        self.assertEqual(self.run_job(self.receipt())['status'], 'modeled-dispatch')
        self.assertEqual(len(self.consumed()), 1)
        self.assertEqual(self.latched(), [])
        self.assertEqual(self.dispatched, ['service'])


class PermitLatchTests(ServiceFixture):
    def authorizations(self):
        return self.table_rows('SELECT operation_id, phase, authorizations FROM service_authorizations')

    def test_check_active_refuses_after_the_expiry_and_after_a_backward_step_that_follows_it(self):
        permit = self.dispatch_running(self.start + 10)
        permit.check_active()  # open: authorized, and a marker committed
        self.clocks.elapse(LIFETIME)
        self.assertEqual(self.refused(permit.check_active).code, EXPIRED)
        self.clocks.wall = self.expires - 10
        (self.policy.root / 'clock.json').unlink()
        clock.reset_process_anchor()
        self.assertEqual(self.refused(permit.check_active).code, EXPIRED)
        self.assertEqual(len(self.latched()), 1)

    def test_the_authorization_check_enters_the_section_and_commits_a_marker_before_the_call(self):
        permit = self.dispatch_running(self.start + 10)
        before = {name: self.rows('SELECT * FROM ' + name) for name in ('jobs', 'consumed', 'ownership', 'events', 'revoked')}
        with patch.object(validity, 'critical', wraps=validity.critical) as section:
            permit.check_active()
            permit.check_active()
        self.assertEqual(section.call_count, 2)
        self.assertEqual(self.authorizations(), [(self.job.identifier, 'apply', 2)])
        self.assertEqual({name: self.rows('SELECT * FROM ' + name) for name in before}, before)

    def test_the_watchdog_poll_never_commits_a_marker_or_enters_the_section(self):
        permit = self.dispatch_running(self.start + 10)
        with patch.object(validity, 'critical', side_effect=AssertionError('the section was entered')):
            for _ in range(5):
                permit.poll_active()
        self.assertEqual(self.authorizations(), [])

    def test_a_refused_authorization_commits_no_marker(self):
        permit = self.dispatch_running(self.start + 10)
        with self.policy.connection() as db:
            db.execute('INSERT INTO revoked VALUES (?,?)', ('fixture', 'key'))
        self.assertEqual(self.refused(permit.check_active).code, 'service_permit_inactive')
        self.assertEqual(self.authorizations(), [])

    def test_an_expiry_latched_before_the_authorization_section_refuses_the_service_call(self):
        permit = self.dispatch_running(self.start + 10)
        child = lambda: service.ServicePermit(service._SEAL, self.job, permit.payload, self.runtime)
        latched, polled, checked, calls = race_with_a_latch(self, permit, child, hook=(service, '_critical', 'before'))
        self.assertEqual(latched, EXPIRED)
        self.assertEqual((polled, checked, calls), (None, EXPIRED, []))
        self.assertEqual(self.authorizations(), [])
        self.assertEqual(len(self.latched()), 1)

    def test_a_poll_that_passed_on_a_stale_read_never_authorizes_the_service_call(self):
        # The poll read no expiry record, then another process latched one, then the poll decided: it may return (it
        # authorizes nothing, the watchdog repeats it every 0.2 s), but the authorization that follows must refuse.
        permit = self.dispatch_running(self.start + 10)
        child = lambda: service.ServicePermit(service._SEAL, self.job, permit.payload, self.runtime)
        latched, polled, checked, calls = race_with_a_latch(self, permit, child, hook=(service, '_latched', 'after'),
                                                            poll_first=True)
        self.assertEqual(latched, EXPIRED)
        self.assertEqual((polled, checked, calls), ('poll_returned', EXPIRED, []))
        self.assertEqual(self.authorizations(), [])

    def test_the_open_path_of_poll_active_takes_no_lock_and_persists_nothing(self):
        permit = self.dispatch_running(self.start + 10)
        permit.check_active()  # the authorization check records the time; the poll then only reads it
        floor, database = self.policy.root / 'clock.json', self.policy.database
        before = (floor.read_bytes(), floor.stat().st_mtime_ns, database.read_bytes(), database.stat().st_mtime_ns)
        with patch.object(clock.Floor, 'locked', side_effect=AssertionError('the recorded-time lock was taken')), \
                patch.object(validity, 'critical', side_effect=AssertionError('the section was entered')):
            for _ in range(100):
                self.clocks.elapse(0.2)  # the effective time rises on every call; none of it is persisted
                permit.poll_active()
        self.assertEqual((floor.read_bytes(), floor.stat().st_mtime_ns, database.read_bytes(), database.stat().st_mtime_ns), before)

    def test_a_write_reservation_from_another_process_is_never_refused_during_a_watchdog_loop(self):
        permit = self.dispatch_running(self.start + 10)
        refused, errors = watchdog_refusals(self, self.policy.database, permit.poll_active,
                                            tick=lambda: self.clocks.elapse(0.01))
        self.assertEqual(errors, [])
        self.assertEqual(refused, [])

    def test_the_watchdog_refuses_a_closed_window_and_latches_it_when_the_store_is_free(self):
        permit = self.dispatch_running(self.start + 10)
        self.clocks.elapse(LIFETIME)
        self.assertEqual(self.refused(permit.poll_active).code, EXPIRED)
        self.assertEqual(len(self.latched()), 1)

    def test_a_busy_store_refuses_the_poll_but_gives_no_authority(self):
        permit = self.dispatch_running(self.start + 10)
        self.clocks.elapse(LIFETIME)
        holder = sqlite3.connect(self.policy.database, timeout=0, isolation_level=None)
        self.addCleanup(holder.close)
        holder.execute('BEGIN IMMEDIATE')  # another writer holds the reservation: the latch cannot be written now
        self.assertEqual(self.refused(permit.poll_active).code, EXPIRED)
        self.assertEqual(self.refused(permit.check_active).code, 'service_store_unavailable')  # no authority either
        holder.execute('ROLLBACK')
        self.assertEqual(self.latched(), [])
        self.assertEqual(self.refused(permit.poll_active).code, EXPIRED)
        self.assertEqual(len(self.latched()), 1)

    def test_the_manifest_expiry_refusal_in_the_permit_records_the_expiry_before_refusing(self):
        permit = self.dispatch_running(self.start + 10)
        self.manifest_time_rule = True
        self.clocks.elapse(LIFETIME)
        self.assertEqual(self.refused(permit.check_active).code, 'service_manifest_expired')
        self.assertEqual(len(self.latched()), 1)


if __name__ == '__main__':
    unittest.main()
