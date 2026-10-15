"""An expired approval stays expired across a backward clock step and a restart (PKG-TIME-AUTHZ-A).

The source finding: a receipt is refused at its expiry plus one second, the wall clock then reads ten seconds before the
expiry, the process restarts, and the same receipt verifies again. Each test drives the public call (authorize, the
context it returns, the permit, or the provider journey) with injected wall and monotonic clocks; nothing waits on, or
changes, the host clock. A refusal must also leave the right records: nothing consumed, no permit, no dispatch to the
modeled service, and the expiry recorded in the authority store.
"""
import sqlite3
import time
import unittest
from unittest.mock import patch

from intune_iac import approval_authority as aa
from intune_iac import clock
from intune_iac.io import AppError, digest, load_json
from plugin_tests import test_approval_authority_v5 as authority_tests
from plugin_tests import test_provider_journey_v5 as journey_tests
from plugin_tests.test_clock_authority import Clocks

LIFETIME = 60


def inject(test, clocks):
    for target, name, function in ((time, 'time', clocks.time), (clock, 'monotonic', clocks.monotonic)):
        patcher = patch.object(target, name, side_effect=function)
        patcher.start()
        test.addCleanup(patcher.stop)
    clock.reset_process_anchor()
    test.addCleanup(clock.reset_process_anchor)


def rows(authority, sql):
    connection = sqlite3.connect(authority.database)
    try:
        return connection.execute(sql).fetchall()
    finally:
        connection.close()


class ReceiptExpiryLatchTests(unittest.TestCase):
    setUp_base = authority_tests.ApprovalAuthorityTests.setUp
    receipt = authority_tests.ApprovalAuthorityTests.receipt
    authorize = authority_tests.ApprovalAuthorityTests.authorize

    def setUp(self):
        self.setUp_base()
        self.addCleanup(self.temp.cleanup)
        self.start = int(time.time())
        self.clocks = Clocks(self.start)
        inject(self, self.clocks)
        self.signed = self.receipt(issued_at=self.start, expires_at=self.start + LIFETIME)
        self.expires = self.start + LIFETIME

    def restart(self):
        clock.reset_process_anchor()
        self.authority = aa.ApprovalAuthority(self.root / 'authority', self.pin, (self.approver,))

    def refused(self, call):
        with self.assertRaises(AppError) as raised:
            call()
        return raised.exception

    def consumed(self):
        return rows(self.authority, 'SELECT operation_id, status FROM consumed')

    def test_an_expired_receipt_stays_refused_after_a_backward_step_and_a_restart(self):
        self.authorize(self.signed)  # verifies at T
        self.clocks.elapse(LIFETIME + 1)
        self.assertEqual(self.refused(lambda: self.authorize(self.signed)).code, 'approval_receipt_time')
        self.clocks.step(-11)  # the wall clock now reads ten seconds before the expiry
        self.assertEqual(self.clocks.now(), self.expires - 10)
        self.restart()
        self.assertEqual(self.refused(lambda: self.authorize(self.signed)).code, 'approval_receipt_time')
        self.assertEqual(self.consumed(), [])

    def test_the_expiry_is_recorded_in_the_authority_store_and_latches_without_the_clock_record(self):
        self.clocks.elapse(LIFETIME + 1)
        self.refused(lambda: self.authorize(self.signed))
        recorded = rows(self.authority, 'SELECT issuer, nonce, operation_id, expires_at FROM expired')
        self.assertEqual(recorded, [('operator-issuer', self.signed['payload']['nonce'],
                                     self.request['operation_id'], self.expires)])
        # The latch alone refuses: remove the recorded time and read a time before the expiry.
        (self.root / 'authority' / 'clock.json').unlink()
        self.clocks.wall = self.expires - 30
        self.restart()
        self.assertEqual(self.refused(lambda: self.authorize(self.signed)).code, 'approval_receipt_time')
        self.assertEqual(self.consumed(), [])

    def test_a_receipt_that_does_not_verify_records_no_expiry(self):
        forged = self.receipt(issued_at=self.start, expires_at=self.start + LIFETIME)
        forged['signature'] = forged['signature'][:-4] + 'AAAA'
        self.clocks.elapse(LIFETIME + 1)
        self.assertEqual(self.refused(lambda: self.authorize(forged)).code, 'approval_receipt_time')
        self.assertEqual(rows(self.authority, 'SELECT count(*) FROM expired'), [(0,)])

    def test_a_backward_step_before_the_expiry_holds_verification_and_says_how_to_recover(self):
        self.clocks.elapse(30)
        self.authorize(self.signed)
        self.clocks.step(-20)  # reads T+10, earlier than the recorded T+30
        for attempt in range(2):
            error = self.refused(lambda: self.authorize(self.signed))
            self.assertEqual(error.code, 'clock_moved_backward')
            self.assertIn(str(self.start + 10), error.message)
            self.assertIn(str(self.start + 30), error.message)
            self.assertIn('Correct the host clock, or wait until it reads at or after the recorded time', error.message)
            self.assertIn('restart', error.message)
            self.restart()  # the hold survives a restart: it comes from the recorded time
        self.assertEqual(self.consumed(), [])
        self.assertEqual(rows(self.authority, 'SELECT count(*) FROM expired'), [(0,)])
        self.clocks.wall = self.start + 31  # recovery: the clock reads at or after the recorded time
        with self.authorize(self.signed): pass

    def test_a_permit_made_before_the_expiry_cannot_enter_after_it_or_after_a_step_back(self):
        authorization = self.authorize(self.signed)
        self.clocks.elapse(LIFETIME + 1)
        with self.assertRaises(AppError) as raised:
            with authorization: self.fail('no permit after the expiry')
        self.assertEqual(raised.exception.code, 'approval_expired')
        self.assertEqual(self.calls, [])  # the guard never ran
        self.assertEqual(self.consumed(), [])
        self.clocks.wall = self.expires - 10
        self.restart()
        self.assertEqual(self.refused(lambda: self.authorize(self.signed)).code, 'approval_receipt_time')
        self.assertEqual(self.consumed(), [])
        self.assertEqual(len(rows(self.authority, 'SELECT * FROM expired')), 1)

    def test_an_entered_permit_cannot_dispatch_after_the_expiry_even_when_the_clock_steps_back(self):
        with self.assertRaises(RuntimeError):
            with self.authorize(self.signed) as permit:
                self.clocks.elapse(LIFETIME + 1)
                self.assertEqual(self.refused(permit.mark_dispatch).code, 'approval_expired')
                self.clocks.step(-40)  # reads ten seconds before the expiry
                self.assertEqual(self.refused(permit.check_active).code, 'approval_expired')
                self.assertEqual(self.refused(permit.mark_dispatch).code, 'approval_expired')
                self.assertEqual(rows(self.authority, 'SELECT * FROM executions'), [])
                raise RuntimeError('stop')
        self.assertEqual(self.consumed(), [(self.request['operation_id'], 'interrupted')])
        self.assertEqual(len(rows(self.authority, 'SELECT * FROM expired')), 1)

    def test_an_entered_permit_is_held_by_a_backward_step_before_the_expiry(self):
        self.clocks.elapse(30)
        with self.assertRaises(RuntimeError):
            with self.authorize(self.signed) as permit:
                self.clocks.step(-20)
                self.assertEqual(self.refused(permit.check_active).code, 'clock_moved_backward')
                self.assertEqual(self.refused(permit.mark_dispatch).code, 'clock_moved_backward')
                self.assertEqual(rows(self.authority, 'SELECT * FROM executions'), [])
                raise RuntimeError('stop')
        self.assertEqual(self.consumed(), [(self.request['operation_id'], 'interrupted')])
        self.assertEqual(rows(self.authority, 'SELECT count(*) FROM expired'), [(0,)])


class JourneyExpiryLatchTests(unittest.TestCase):
    setUp_base = journey_tests.ProviderJourneyTests.setUp
    journey = journey_tests.ProviderJourneyTests.journey
    receipt = journey_tests.ProviderJourneyTests.receipt

    def setUp(self):
        self.setUp_base()
        self.start = int(time.time())
        self.clocks = Clocks(self.start)
        inject(self, self.clocks)

    def prepared_review(self):
        journey = self.journey()
        journey.prepare()
        journey.review()
        return journey

    def applies(self):
        return self.model.commands.count('apply')

    def consumed(self):
        authority = aa.ApprovalAuthority.__new__(aa.ApprovalAuthority)
        authority.database = self.host / 'authority' / 'consumption.sqlite3'
        return rows(authority, 'SELECT * FROM consumed')

    def test_a_receipt_expired_before_dispatch_cannot_dispatch_after_a_step_back_and_a_restart(self):
        journey = self.prepared_review()
        path = self.receipt(issued_at=self.start, expires_at=self.start + LIFETIME)
        journey.approve(path)
        self.clocks.elapse(LIFETIME + 1)
        with self.assertRaises(AppError) as raised:
            journey.execute()
        self.assertEqual(raised.exception.code, 'approval_expired')
        self.assertEqual(self.applies(), 0)
        self.clocks.wall = self.start + LIFETIME - 10
        clock.reset_process_anchor()
        restarted = self.journey()
        restarted.review()
        with self.assertRaises(AppError) as raised:
            restarted.approve(path)
        self.assertEqual(raised.exception.code, 'approval_receipt_time')
        with self.assertRaises(AppError):
            restarted.execute()
        self.assertEqual(self.applies(), 0)
        self.assertEqual(self.consumed(), [])
        self.assertFalse((self.executor.root / 'operation.json').exists())

    def test_a_backward_step_before_the_expiry_holds_the_mutation_and_dispatches_nothing(self):
        self.clocks.elapse(30)
        journey = self.prepared_review()
        journey.approve(self.receipt(issued_at=self.start + 30, expires_at=self.start + 30 + LIFETIME))
        # Four seconds back is beyond the tolerance but keeps the prepared request (dated T+30) inside the 5 s allowance
        # of provider_journey, so only the clock hold stands between the retry and dispatch.
        self.clocks.step(-4)
        with self.assertRaises(AppError) as raised:
            journey.execute()
        self.assertEqual(raised.exception.code, 'clock_moved_backward')
        self.assertEqual(self.applies(), 0)
        self.assertEqual(self.consumed(), [])
        self.assertFalse((self.executor.root / 'operation.json').exists())
        self.assertEqual(load_json(self.executor.root / 'prepared.json')['execution_authorized'], False)

    def test_a_prepared_request_dated_ahead_of_the_clock_is_refused_not_reopened_by_a_backward_step(self):
        # provider_journey line 181 only refuses a prepared_at later than the host clock plus 5 s. Stepping the clock
        # back makes more requests refused, never fewer, so it needs no latch.
        self.clocks.elapse(100)
        journey = self.prepared_review()
        del journey
        self.clocks.step(-100)
        with self.assertRaises(AppError) as raised:
            self.journey().status()
        self.assertEqual(raised.exception.code, 'journey_prepared_request_invalid')


if __name__ == '__main__':
    unittest.main()
