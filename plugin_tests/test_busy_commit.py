"""A commit that fails busy is a refusal, never a success (PKG-TIME-AUTHZ-B fix round 2, item 3).

The stores run in DELETE journal mode with a zero busy timeout. A reader that holds a statement open keeps a shared lock,
so a writer that already holds the write reservation (BEGIN IMMEDIATE) cannot take the exclusive lock its COMMIT needs,
and COMMIT fails with 'database is locked' while the transaction is still open. Every path that consumes an approval,
writes a dispatch marker, records a cancellation or starts a recovery must then: report a refusal (never success), leave
the transaction rolled back (no row, no marker, no journal left behind), call no backend, executor or host, and move no
process anchor beyond the reading it took. A retry once the reader is gone re-enters the full critical section and
succeeds. Each test holds a read cursor open with reading() and drives the public call.
"""
import sqlite3
import time
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from intune_iac import approval_authority as aa
from intune_iac import clock, validity
from intune_iac import worker_adoption as adoption
from intune_iac import protected_worker as worker
from intune_iac import worker_adoption_reconcile as bridge
from intune_iac.io import AppError
from plugin_tests import test_adoption_expiry_latch as adoption_tests
from plugin_tests import test_adoption_recovery_expiry_latch as recovery_tests
from plugin_tests import test_authz_expiry_latch as authz_tests
from plugin_tests import test_protected_worker_r4 as worker_base

LIFETIME = 60


@contextmanager
def reading(database):
    """A reader with a statement left open: it holds a shared lock until it is closed."""
    connection = sqlite3.connect(database, timeout=0, isolation_level=None)
    # Several rows, so that fetching one leaves the statement active (a statement that ran out of rows is reset and
    # releases its lock): every schema row paired with five numbers.
    cursor = connection.execute('SELECT m.name, c.x FROM sqlite_master m, '
                                '(WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c WHERE x < 5) SELECT x FROM c) c')
    cursor.fetchone()
    try:
        yield
    finally:
        cursor.close()
        connection.close()


@contextmanager
def busy_after_open_commit(database, nth=1):
    """Install the busy reader at the moment the shared section has committed its open judgment (the nth time) and is about
    to hand the caller its own transaction: the caller's work is then active, and only its commit meets the reader. A reader
    installed before the section is entered fails the open judgment's own commit instead, which is a different (earlier)
    refusal and never reaches the caller's commit."""
    real, state = validity._sync, {'calls': 0, 'reader': None}

    def after_the_open_commit(root):
        real(root)
        state['calls'] += 1
        if state['calls'] == nth and state['reader'] is None:
            state['reader'] = reading(database)
            state['reader'].__enter__()
    try:
        with patch.object(validity, '_sync', side_effect=after_the_open_commit):
            yield
    finally:
        if state['reader'] is not None:
            state['reader'].__exit__(None, None, None)


class Harness(unittest.TestCase):
    def test_a_reader_with_an_open_statement_makes_a_zero_timeout_commit_fail_busy_and_leaves_the_transaction_open(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            database = directory + '/s.sqlite3'
            setup = sqlite3.connect(database, isolation_level=None)
            setup.execute('PRAGMA journal_mode=DELETE')
            setup.execute('CREATE TABLE t (x)')
            setup.close()
            writer = sqlite3.connect(database, timeout=0, isolation_level=None)
            with reading(database):
                writer.execute('BEGIN IMMEDIATE')
                writer.execute('INSERT INTO t VALUES (1)')
                with self.assertRaises(sqlite3.OperationalError):
                    writer.execute('COMMIT')
                self.assertTrue(writer.in_transaction)  # the failed COMMIT left the transaction open
                writer.execute('ROLLBACK')
            self.assertEqual(writer.execute('SELECT count(*) FROM t').fetchone(), (0,))
            writer.close()


class BusyAssertions:
    def assert_rolled_back(self, directory):
        self.assertEqual([p.name for p in directory.iterdir() if 'journal' in p.name], [], 'a journal was left behind')

    def entered_sections(self):
        return patch.object(validity, 'critical', wraps=validity.critical)


class ApprovalAuthorityBusyTests(BusyAssertions, unittest.TestCase):
    setUp_base = authz_tests.ReceiptExpiryLatchTests.setUp_base
    receipt = authz_tests.ReceiptExpiryLatchTests.receipt
    authorize = authz_tests.ReceiptExpiryLatchTests.authorize
    refused = authz_tests.ReceiptExpiryLatchTests.refused
    consumed = authz_tests.ReceiptExpiryLatchTests.consumed
    setUp = authz_tests.ReceiptExpiryLatchTests.setUp

    def database(self):
        return self.authority.database

    def test_consumption_that_cannot_commit_is_refused_and_a_retry_reenters_the_section(self):
        signed = self.signed
        authorization = self.authorize(signed)
        with reading(self.database()):
            with self.assertRaises(AppError) as raised:
                with authorization:
                    self.fail('the approval was consumed although the commit failed')
        # The open judgment is committed on its own before the caller's transaction is handed over, so a store that cannot
        # commit refuses at that first commit, earlier than the consumption's own.
        self.assertEqual(raised.exception.code, 'approval_store_unavailable')
        self.assertEqual(self.consumed(), [])
        self.assertEqual(rows(self.authority, 'SELECT * FROM executions'), [])
        self.assert_rolled_back(self.authority.root)
        self.assertEqual({k: v[0] for k, v in clock._ANCHORS.items()}, {k: self.clocks.time() for k in clock._ANCHORS})
        with self.entered_sections() as section:
            with self.authorize(signed):  # the retry authenticates again and consumes inside the full section
                pass
        self.assertGreaterEqual(section.call_count, 2)
        self.assertEqual(len(self.consumed()), 1)

    def test_consumption_that_cannot_commit_in_the_callers_own_transaction_is_refused_with_nothing_consumed(self):
        # The busy reader arrives after the open judgment's commit, while the consumption's transaction is active, so it is
        # the consumption's own commit that fails and must be a refusal.
        signed = self.signed
        authorization = self.authorize(signed)
        with busy_after_open_commit(self.database(), nth=3):  # the sections are: two checks on entry, then the consumption
            with self.assertRaises(AppError) as raised:
                with authorization:
                    self.fail('the approval was consumed although the commit failed')
        self.assertEqual(raised.exception.code, 'approval_consumption_not_durable')
        self.assertEqual(self.consumed(), [])
        self.assertEqual(rows(self.authority, 'SELECT * FROM executions'), [])
        self.assert_rolled_back(self.authority.root)
        self.assertEqual(rows(self.authority, 'SELECT count(*) FROM expired_v2'), [(0,)])
        with self.entered_sections() as section:
            with self.authorize(signed):  # the retry authenticates again and consumes inside the full section
                pass
        self.assertGreaterEqual(section.call_count, 2)
        self.assertEqual(len(self.consumed()), 1)

    def test_a_dispatch_marker_that_cannot_commit_in_the_callers_own_transaction_is_refused_and_recorded_nowhere(self):
        with self.assertRaises(RuntimeError):
            with self.authorize(self.signed) as permit:
                with busy_after_open_commit(self.database(), nth=3):  # the sections are: two checks, then the dispatch marker
                    with self.assertRaises(AppError) as raised:
                        permit.mark_dispatch()
                self.assertEqual(raised.exception.code, 'approval_dispatch_not_durable')
                self.assertEqual(rows(self.authority, 'SELECT * FROM executions'), [])
                self.assert_rolled_back(self.authority.root)
                with self.entered_sections() as section:
                    permit.mark_dispatch()
                self.assertGreaterEqual(section.call_count, 1)
                self.assertEqual(len(rows(self.authority, 'SELECT * FROM executions')), 1)
                raise RuntimeError('stop')

    def test_a_dispatch_marker_that_cannot_commit_is_refused_and_a_retry_reenters_the_section(self):
        with self.assertRaises(RuntimeError):
            with self.authorize(self.signed) as permit:
                with reading(self.database()):
                    with self.assertRaises(AppError) as raised:
                        permit.mark_dispatch()
                self.assertEqual(raised.exception.code, 'approval_store_unavailable')  # at the open judgment's own commit
                self.assertEqual(rows(self.authority, 'SELECT * FROM executions'), [])
                self.assert_rolled_back(self.authority.root)
                with self.entered_sections() as section:
                    permit.mark_dispatch()
                self.assertGreaterEqual(section.call_count, 1)
                self.assertEqual(len(rows(self.authority, 'SELECT * FROM executions')), 1)
                raise RuntimeError('stop')

    def test_a_reached_expiry_that_cannot_be_recorded_is_still_refused_and_recorded_by_the_retry(self):
        self.clocks.elapse(LIFETIME + 1)
        with reading(self.database()):
            error = self.refused(lambda: self.authorize(self.signed))
        self.assertIn(error.code, ('approval_store_unavailable', 'approval_receipt_time'))
        self.assertEqual(rows(self.authority, 'SELECT count(*) FROM expired_v2'), [(0,)])
        self.assertEqual(self.consumed(), [])
        self.assert_rolled_back(self.authority.root)
        self.assertEqual(self.refused(lambda: self.authorize(self.signed)).code, 'approval_receipt_time')
        self.assertEqual(rows(self.authority, 'SELECT count(*) FROM expired_v2'), [(1,)])


class AdoptionBusyTests(BusyAssertions, adoption_tests.AdoptionFixture):
    ready = adoption_tests.VerificationDispatchTests.ready
    phase = adoption_tests.VerificationDispatchTests.phase
    verify = adoption_tests.VerificationDispatchTests.verify

    def assert_anchors_are_this_readings(self):
        self.assertEqual({k: v[0] for k, v in clock._ANCHORS.items()}, {k: self.clocks.time() for k in clock._ANCHORS})

    def test_consumption_that_cannot_commit_is_refused_and_a_retry_reenters_the_section(self):
        signed = self.receipt()
        self.clocks.wall = self.start + 10
        with reading(self.policy.database):
            error = self.refused(lambda: self.run_job(signed))
        self.assertEqual(error.code, 'service_store_unavailable')
        self.assert_nothing_happened()  # no consumed row, no transcript, still prepared, no dispatch, no approval file
        self.assertEqual(self.observations, [])  # the verification's open judgment cannot commit, so nothing is observed
        self.assert_rolled_back(self.policy.root)
        self.assert_anchors_are_this_readings()
        with self.entered_sections() as section:
            self.assertEqual(self.run_job(signed)['status'], 'modeled-dispatch')
        self.assertGreaterEqual(section.call_count, 2)  # the verification judgment and the final consumption
        self.assertEqual(self.job_row(), ('running', 0, 1))

    def test_consumption_that_cannot_commit_in_the_callers_own_transaction_is_refused_after_the_baseline_observation(self):
        # The second section (the consumption) commits its open judgment; the busy reader arrives then. The baseline
        # observation before it has happened, and nothing is consumed, transcribed or dispatched.
        signed = self.receipt()
        self.clocks.wall = self.start + 10
        with busy_after_open_commit(self.policy.database, nth=2):
            error = self.refused(lambda: self.run_job(signed))
        self.assertEqual(error.code, 'service_store_unavailable')
        self.assert_nothing_happened()
        self.assertEqual(self.observations, ['baseline'])  # only the read-only observation that precedes the commit
        self.assert_rolled_back(self.policy.root)
        self.assert_anchors_are_this_readings()
        with self.entered_sections() as section:
            self.assertEqual(self.run_job(signed)['status'], 'modeled-dispatch')
        self.assertGreaterEqual(section.call_count, 2)
        self.assertEqual(self.job_row(), ('running', 0, 1))

    def test_a_verification_dispatch_marker_that_cannot_commit_in_the_callers_own_transaction_is_refused(self):
        self.ready()
        with busy_after_open_commit(self.policy.database):
            error = self.refused(self.verify)
        self.assertEqual(error.code, 'service_store_unavailable')
        self.assertEqual(self.phase(), (0, 'not_started'))
        self.assert_rolled_back(self.policy.root)
        with self.entered_sections():
            self.assertEqual(self.verify()['status'], 'modeled-dispatch')
        self.assertEqual(self.phase(), (1, 'running'))

    def test_a_verification_dispatch_marker_that_cannot_commit_is_refused_and_a_retry_reenters_the_section(self):
        self.ready()
        with reading(self.policy.database):
            error = self.refused(self.verify)
        self.assertEqual(error.code, 'service_store_unavailable')
        self.assertEqual(self.phase(), (0, 'not_started'))
        self.assertEqual(self.dispatched, ['import'])  # no second dispatch
        self.assert_rolled_back(self.policy.root)
        with self.entered_sections() as section:
            self.assertEqual(self.verify()['status'], 'modeled-dispatch')
        self.assertGreaterEqual(section.call_count, 2)
        self.assertEqual(self.phase(), (1, 'running'))

    def test_an_expiry_that_cannot_be_recorded_is_still_refused_and_recorded_by_the_retry(self):
        signed = self.receipt()
        self.clocks.elapse(LIFETIME + 1)
        with reading(self.policy.database):
            self.assertEqual(self.refused(lambda: self.run_job(signed)).code, 'service_store_unavailable')
        self.assertEqual(self.latched(), [])  # nothing recorded, and still nothing consumed or dispatched
        self.assert_nothing_happened()
        self.assert_rolled_back(self.policy.root)
        self.assertEqual(self.refused(lambda: self.run_job(signed)).code, 'adoption_signature_expired')
        self.assertEqual(len(self.latched()), 1)

    def cancelled(self):
        return self.rows('SELECT cancelled FROM jobs')[0][0]

    def test_a_cancellation_that_cannot_commit_is_refused_and_leaves_no_marker(self):
        with patch.object(adoption.AdoptionJob, 'status', return_value={}):
            with reading(self.policy.database):
                self.assertEqual(self.refused(self.job.cancel).code, 'service_store_unavailable')
            self.assertEqual(self.cancelled(), 0)
            self.assertEqual(self.rows("SELECT * FROM events WHERE kind='adoption_cancel_requested'"), [])
            self.assertEqual(self.job_row(), ('prepared', 0, 0))
            self.assert_rolled_back(self.policy.root)
            self.job.cancel()
        self.assertEqual(self.cancelled(), 1)

    def test_a_recovery_that_cannot_commit_is_refused_before_any_host_call(self):
        with patch.object(adoption.AdoptionJob, 'status', return_value={}), \
                patch.object(adoption.host, 'recover', side_effect=AssertionError('the host was touched')) as host:
            with reading(self.policy.database):
                self.assertEqual(self.refused(self.job.recover).code, 'service_store_unavailable')
            self.assertEqual(self.cancelled(), 0)
            self.assertEqual(self.rows("SELECT * FROM events WHERE kind LIKE 'adoption_recovery%'"), [])
            host.assert_not_called()
            self.assert_rolled_back(self.policy.root)
            self.job.recover()
        self.assertEqual(self.cancelled(), 1)


class RecoveryPlanBusyTests(BusyAssertions, recovery_tests.RecoveryFixture):
    def test_consumption_that_cannot_commit_is_refused_and_a_retry_reenters_the_section(self):
        signed = self.receipt()
        self.clocks.wall = self.start + 10
        with reading(self.policy.database):
            error = self.refused(lambda: self.run_job(signed))
        self.assertEqual(error.code, 'service_store_unavailable')
        self.assert_nothing_consumed()
        self.assert_rolled_back(self.policy.root)
        self.assertEqual({k: v[0] for k, v in clock._ANCHORS.items()}, {k: self.clocks.time() for k in clock._ANCHORS})
        with self.entered_sections() as section:
            self.assertEqual(self.run_job(signed)['status'], 'modeled-dispatch')
        self.assertGreaterEqual(section.call_count, 2)
        self.assertEqual(self.rows('SELECT status, dispatches FROM adoption_recovery_plans'), [('running', 1)])

    def cancelled(self):
        return self.rows('SELECT cancelled FROM adoption_recovery_plans')[0][0]

    def test_a_cancellation_that_cannot_commit_is_refused_and_leaves_no_marker(self):
        with patch.object(bridge.RecoveryPlanJob, 'status', return_value={}):
            with reading(self.policy.database):
                self.assertEqual(self.refused(self.job.cancel).code, 'service_store_unavailable')
            self.assertEqual(self.cancelled(), 0)
            self.assertEqual(self.rows("SELECT * FROM events WHERE kind='adoption_recovery_plan_cancel_requested'"), [])
            self.assert_rolled_back(self.policy.root)
            self.job.cancel()
        self.assertEqual(self.cancelled(), 1)

    def test_a_recovery_that_cannot_commit_is_refused_before_any_host_call(self):
        with patch.object(bridge.RecoveryPlanJob, 'status', return_value={}), \
                patch.object(bridge.host, 'recover', side_effect=AssertionError('the host was touched')) as host:
            with reading(self.policy.database):
                self.assertEqual(self.refused(self.job.recover).code, 'service_store_unavailable')
            self.assertEqual(self.cancelled(), 0)
            host.assert_not_called()
            self.assert_rolled_back(self.policy.root)
            self.job.recover()
        self.assertEqual(self.cancelled(), 1)


class WorkerBusyTests(BusyAssertions, unittest.TestCase):
    setUp = worker_base.ProtectedWorkerTests.setUp
    prepare = worker_base.ProtectedWorkerTests.prepare
    job = worker_base.ProtectedWorkerTests.job
    receipt = worker_base.ProtectedWorkerTests.receipt
    state = worker_base.ProtectedWorkerTests.state

    def database(self):
        return self.job().policy.database

    def row(self):
        connection = sqlite3.connect(self.database())
        try:
            return connection.execute('SELECT status, cancel_requested, dispatches FROM jobs').fetchone()
        finally:
            connection.close()

    def test_a_cancellation_that_cannot_commit_is_refused_and_leaves_no_marker(self):
        self.prepare()
        with reading(self.database()):
            with self.assertRaises(AppError) as raised:
                self.job().cancel()
        self.assertEqual(raised.exception.code, 'worker_store_unavailable')
        self.assertEqual(self.row(), ('prepared', 0, 0))
        self.assert_rolled_back(self.database().parent)
        self.assertTrue(self.job().cancel()['cancellation_requested'])
        self.assertEqual(self.row()[1], 1)

    def test_a_dispatch_marker_that_cannot_commit_is_refused_and_nothing_is_executed(self):
        self.prepare()
        before = self.state()
        calls, held = [], []
        real = worker.protected.validate_native_operation

        def validate(*args, **kwargs):
            calls.append(1)
            if len(calls) == 2:  # the check inside the authorization, just before the dispatch marker is written
                held.append(reading(self.database()))
                held[0].__enter__()
            return real(*args, **kwargs)
        try:
            with patch.object(worker.protected, 'validate_native_operation', validate), \
                    patch.object(worker.WorkerJob, '_apply', side_effect=AssertionError('the executor was called')), \
                    patch.object(worker.protected, 'inspect_executor', side_effect=AssertionError('the executor was read')):
                with self.assertRaises(AppError) as raised:
                    self.job().run(self.receipt())
        finally:
            for context in held:
                context.__exit__(None, None, None)
        self.assertEqual(raised.exception.code, 'worker_store_unavailable')
        self.assertEqual(self.row(), ('prepared', 0, 0))  # no dispatch marker
        self.assertEqual(self.state(), before)
        self.assert_rolled_back(self.database().parent)
        status = self.job().status()
        # The approval was consumed before the marker (it stays spent) and nothing was dispatched.
        self.assertEqual((status['status'], status['mutation_attempts'], status['approval_consumed']),
                         ('approval_consumed_dispatch_not_recorded', 0, True))
        with self.assertRaises(AppError):  # a spent approval is never reused: the retry needs a new operation
            self.job().run(self.receipt())
        self.assertEqual(self.state(), before)


def rows(authority, sql):
    return authz_tests.rows(authority, sql)


if __name__ == '__main__':
    unittest.main()
