"""An expired approval stays expired across a backward clock step and a restart (PKG-TIME-AUTHZ-A).

The source finding: a receipt is refused at its expiry plus one second, the wall clock then reads ten seconds before the
expiry, the process restarts, and the same receipt verifies again. Each test drives the public call (authorize, the
context it returns, the permit, or the provider journey) with injected wall and monotonic clocks; nothing waits on, or
changes, the host clock. A refusal must also leave the right records: nothing consumed, no permit, no dispatch to the
modeled service, and the expiry recorded in the authority store.
"""
import multiprocessing
import sqlite3
import time
import unittest
from unittest.mock import patch

from intune_iac import approval_authority as aa
from intune_iac import clock
from intune_iac.io import AppError, digest, load_json, write_json
from plugin_tests import test_approval_authority_v5 as authority_tests
from plugin_tests import test_provider_journey_v5 as journey_tests
from plugin_tests.test_clock_authority import Clocks

LIFETIME = 60


def inject(test, clocks):
    for target, name, function in ((time, 'time', clocks.time), (clock, 'monotonic', clocks.monotonic)):
        patcher = patch.object(target, name, side_effect=function)
        patcher.start()
        test.addCleanup(patcher.stop)
    clocks.install_session(test)
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

    def test_a_receipt_that_reuses_an_expired_receipts_issuer_and_nonce_is_judged_on_its_own(self):
        import uuid
        nonce = uuid.uuid4().hex
        early = self.receipt(issued_at=self.start, expires_at=self.start + 30, nonce=nonce)
        self.clocks.wall = self.start + 40
        self.assertEqual(self.refused(lambda: self.authorize(early)).code, 'approval_receipt_time')
        self.assertEqual(len(rows(self.authority, 'SELECT * FROM expired_v2')), 1)
        other = dict(self.request, operation_id=str(uuid.uuid4()))  # another operation, same issuer and nonce
        later = self.receipt(request=other, issued_at=self.start, expires_at=self.start + LIFETIME, nonce=nonce)
        with self.authorize(later, request=other, guard=aa.make_laboratory_guard(other, lambda: None)):
            pass
        self.assertEqual([row[0] for row in self.consumed()], [other['operation_id']])

    def test_a_restart_with_the_wall_set_back_above_the_mark_cannot_reopen_a_receipt_that_has_expired(self):
        self.clocks.wall = self.start + 30
        self.authorize(self.signed)  # judged open at T30: the mark and an open row
        self.restart()
        self.clocks.elapse(40)  # true time T70, past the expiry at T60
        self.clocks.step(-30)  # the wall is set to T40: above the mark
        self.assertEqual(self.refused(lambda: self.authorize(self.signed)).code, 'approval_receipt_time')
        self.assertEqual(self.consumed(), [])

    def test_the_expiry_is_recorded_in_the_authority_store_and_latches_without_the_clock_record(self):
        self.clocks.elapse(LIFETIME + 1)
        self.refused(lambda: self.authorize(self.signed))
        recorded = rows(self.authority, 'SELECT issuer, nonce, operation_id, expires_at FROM expired_v2')
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
        self.assertEqual(rows(self.authority, 'SELECT count(*) FROM expired_v2'), [(0,)])

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
        self.assertEqual(rows(self.authority, 'SELECT count(*) FROM expired_v2'), [(0,)])
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
        self.assertEqual(len(rows(self.authority, 'SELECT * FROM expired_v2')), 1)

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
        self.assertEqual(len(rows(self.authority, 'SELECT * FROM expired_v2')), 1)

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
        self.assertEqual(rows(self.authority, 'SELECT count(*) FROM expired_v2'), [(0,)])


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

    def test_a_large_backward_step_after_approval_names_the_clock_hold_and_dispatches_nothing(self):
        self.clocks.elapse(30)
        journey = self.prepared_review()
        journey.approve(self.receipt(issued_at=self.start + 30, expires_at=self.start + 30 + LIFETIME))
        self.clocks.step(-30)  # the prepared request (dated T+30) is now far ahead of this host's clock
        for attempt in range(2):
            with self.assertRaises(AppError) as raised:
                journey.execute()
            error = raised.exception
            self.assertEqual(error.code, 'clock_moved_backward')
            self.assertIn('reads %d' % self.start, error.message)
            self.assertIn('time %d' % (self.start + 30), error.message)
            self.assertIn('Correct the host clock, or wait until it reads at or after the recorded time', error.message)
            clock.reset_process_anchor()
            with self.assertRaises(AppError) as raised:
                self.journey()  # a restarted journey is held too, from the recorded time
            self.assertEqual(raised.exception.code, 'clock_moved_backward')
        self.assertEqual(self.applies(), 0)
        self.assertEqual(self.consumed(), [])

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


class RecoveryWordsMixin:
    def assert_hold(self, error, reads, recorded):
        self.assertEqual(error.code, 'clock_moved_backward')
        self.assertIn('reads %d' % reads, error.message)
        self.assertIn('time %d' % recorded, error.message)
        self.assertIn('Correct the host clock, or wait until it reads at or after the recorded time', error.message)
        self.assertIn('restart', error.message)


class ClockHoldExplanationTests(RecoveryWordsMixin, unittest.TestCase):
    """A step back larger than the 5 s allowance on prepared_at and issued_at still gets the clock hold, not a bare time
    error. With no backward step the existing refusals are unchanged (test_approval_authority_v5 covers them)."""
    setUp_base = ReceiptExpiryLatchTests.setUp_base
    receipt = ReceiptExpiryLatchTests.receipt
    authorize = ReceiptExpiryLatchTests.authorize
    restart = ReceiptExpiryLatchTests.restart
    refused = ReceiptExpiryLatchTests.refused
    consumed = ReceiptExpiryLatchTests.consumed
    setUp = ReceiptExpiryLatchTests.setUp

    def attempt_after_a_thirty_second_step_back(self, prepared_at, issued_at):
        self.clocks.elapse(30)
        request = dict(self.request, prepared_at=prepared_at)
        guard = aa.make_laboratory_guard(request, lambda: None)
        signed = self.receipt(request, issued_at=issued_at, expires_at=issued_at + LIFETIME)
        self.authorize(signed, request, guard)  # verifies at T+30 and records it
        self.clocks.step(-30)
        for attempt in range(2):
            error = self.refused(lambda: self.authorize(signed, request, guard))
            self.assert_hold(error, self.start, self.start + 30)
            self.restart()
        self.assertEqual(self.consumed(), [])

    def test_a_prepared_request_dated_ahead_after_a_large_step_back_names_the_hold(self):
        self.attempt_after_a_thirty_second_step_back(self.start + 30, self.start + 30)

    def test_a_receipt_issued_ahead_after_a_large_step_back_names_the_hold(self):
        self.attempt_after_a_thirty_second_step_back(self.start, self.start + 30)


class UnauthenticatedInputTests(unittest.TestCase):
    """Input that has not authenticated must not write the recorded time or move this process's anchor."""
    setUp_base = ReceiptExpiryLatchTests.setUp_base
    receipt = ReceiptExpiryLatchTests.receipt
    authorize = ReceiptExpiryLatchTests.authorize
    refused = ReceiptExpiryLatchTests.refused
    consumed = ReceiptExpiryLatchTests.consumed
    setUp = ReceiptExpiryLatchTests.setUp

    def future_dated(self, prepared_at, issued_at):
        self.clocks.elapse(30)  # build the objects at T+30, as a host clock that later reads T would see them
        request = dict(self.request, prepared_at=prepared_at)
        guard = aa.make_laboratory_guard(request, lambda: None)
        forged = self.receipt(request, issued_at=issued_at, expires_at=issued_at + LIFETIME)
        forged['signature'] = forged['signature'][:-4] + 'AAAA'
        self.clocks.step(-30)
        return request, guard, forged

    def check(self, prepared_at, issued_at, code):
        floor = self.root / 'authority' / 'clock.json'
        request, guard, forged = self.future_dated(prepared_at, issued_at)
        floor.unlink(missing_ok=True)
        anchors = dict(clock._ANCHORS)
        self.assertEqual(self.refused(lambda: self.authorize(forged, request, guard)).code, code)
        self.assertFalse(floor.exists())
        self.assertEqual(dict(clock._ANCHORS), anchors)
        # A legitimate approval at the current time is not held because of the rejected input.
        with self.authorize(self.signed): pass

    def test_an_unsigned_request_dated_ahead_records_nothing(self):
        self.check(self.start + 30, self.start + 30, 'approval_preparation_time')

    def test_an_unsigned_receipt_issued_ahead_records_nothing(self):
        self.check(self.start, self.start + 30, 'approval_receipt_time')

    def test_a_damaged_recorded_time_falls_through_to_the_original_refusal(self):
        request, guard, forged = self.future_dated(self.start + 30, self.start + 30)
        (self.root / 'authority' / 'clock.json').write_bytes(b'not json')
        self.assertEqual(self.refused(lambda: self.authorize(forged, request, guard)).code, 'approval_preparation_time')


class RevokedSignerTests(unittest.TestCase):
    setUp_base = ReceiptExpiryLatchTests.setUp_base
    receipt = ReceiptExpiryLatchTests.receipt
    authorize = ReceiptExpiryLatchTests.authorize
    refused = ReceiptExpiryLatchTests.refused
    setUp = ReceiptExpiryLatchTests.setUp

    def test_a_revoked_signer_cannot_write_expiry_records(self):
        first = self.receipt(issued_at=self.start, expires_at=self.start + LIFETIME)
        second = self.receipt(issued_at=self.start, expires_at=self.start + LIFETIME)
        self.assertNotEqual(first['payload']['nonce'], second['payload']['nonce'])
        self.authority.revoke_key('operator-issuer', 'key-1')
        self.clocks.elapse(LIFETIME + 1)
        for signed in (first, second):
            self.assertEqual(self.refused(lambda: self.authorize(signed)).code, 'approval_receipt_time')
        self.assertEqual(rows(self.authority, 'SELECT count(*) FROM expired_v2'), [(0,)])

    def test_the_expired_table_is_capped_like_the_consumed_table(self):
        first = self.receipt(issued_at=self.start, expires_at=self.start + LIFETIME)
        second = self.receipt(issued_at=self.start, expires_at=self.start + LIFETIME)
        self.clocks.elapse(LIFETIME + 1)
        with patch.object(aa, 'MAX_EXPIRED', 1):
            self.assertEqual(self.refused(lambda: self.authorize(first)).code, 'approval_receipt_time')
            self.assertEqual(self.refused(lambda: self.authorize(second)).code, 'approval_store_capacity')
        self.assertEqual(rows(self.authority, 'SELECT count(*) FROM expired_v2'), [(1,)])


FORK = multiprocessing.get_context('fork')
BOUND = 30


class ConcurrentLatchTests(unittest.TestCase):
    """Two real processes. The window judgment, the recorded time, the expiry record and the consumption or dispatch
    insert are one critical section, so no interleaving lets an approval act after another process latched it."""
    setUp_base = ReceiptExpiryLatchTests.setUp_base
    receipt = ReceiptExpiryLatchTests.receipt
    authorize = ReceiptExpiryLatchTests.authorize
    restart = ReceiptExpiryLatchTests.restart
    refused = ReceiptExpiryLatchTests.refused
    consumed = ReceiptExpiryLatchTests.consumed
    setUp = ReceiptExpiryLatchTests.setUp

    def start_process(self, body):
        queue = FORK.Queue()

        def main():
            try:
                body()
                result = ('ok', None)
            except AppError as error:
                result = ('refused', error.code)
            except BaseException as error:
                result = ('error', repr(error))
            queue.put(result)
        process = FORK.Process(target=main, daemon=True)
        process.start()
        self.addCleanup(lambda: process.is_alive() and process.terminate())
        return process, queue

    def finish(self, process, queue):
        result = queue.get(timeout=BOUND)
        process.join(BOUND)
        return result

    def executions(self):
        return rows(self.authority, 'SELECT * FROM executions')

    def test_a_replaced_clock_record_during_expired_authorization_cannot_reopen_the_approval(self):
        authority = self.root / 'authority'
        self.sequence_a(lambda: write_json(authority / 'clock.json',
                                           {'schema_version': clock.SCHEMA, 'high_water': self.expires - 100}))

    def test_deleting_the_clock_lock_and_record_during_expired_authorization_cannot_reopen_the_approval(self):
        # flock is per inode: a second process locking a fresh clock.lock must still wait for the first.
        authority = self.root / 'authority'
        self.sequence_a(lambda: [(authority / name).unlink() for name in ('clock.lock', 'clock.json')])

    def sequence_a(self, tamper):
        paused, release, second_paused, release_second = (FORK.Event() for _ in range(4))

        def process_a():
            self.clocks.wall = self.expires + 1  # this process reads a time after the expiry
            seen = []
            observe, authentic = clock.Floor.observe_locked, aa.ApprovalAuthority._authentic

            def paused_observe(floor, wall, **kwargs):
                reading = observe(floor, wall, **kwargs)
                if not seen:
                    seen.append(True); paused.set(); release.wait(BOUND)
                return reading

            def paused_authentic(authority, *args, **kwargs):
                result = authentic(authority, *args, **kwargs)
                if seen:  # a design that releases the recorded-time lock before recording the expiry pauses here
                    second_paused.set(); release_second.wait(BOUND)
                return result
            with patch.object(clock.Floor, 'observe_locked', paused_observe), \
                    patch.object(aa.ApprovalAuthority, '_authentic', paused_authentic):
                self.authorize(self.signed)

        def process_b():
            self.clocks.wall = self.expires - 10  # a restarted process whose clock reads before the expiry
            self.restart()
            with self.authorize(self.signed) as permit:
                permit.mark_dispatch()

        a_process, a_queue = self.start_process(process_a)
        self.assertTrue(paused.wait(BOUND))
        # While process A has recorded an expired time but not yet the expiry, replace the recorded time.
        tamper()
        b_process, b_queue = self.start_process(process_b)
        time.sleep(1)
        self.assertTrue(b_queue.empty())  # process B waits for the critical section; it does not get through
        release.set()
        b_result = self.finish(b_process, b_queue)
        release_second.set()
        a_result = self.finish(a_process, a_queue)
        self.assertEqual(a_result, ('refused', 'approval_receipt_time'))
        self.assertEqual(b_result, ('refused', 'approval_receipt_time'))
        self.assertEqual(self.consumed(), [])
        self.assertEqual(self.executions(), [])
        self.assertEqual(len(rows(self.authority, 'SELECT * FROM expired_v2')), 1)

    def test_an_expiry_latched_between_the_last_check_and_consumption_refuses_the_entry(self):
        paused, release = FORK.Event(), FORK.Event()

        def process_a():
            self.clocks.wall = self.start + 10
            authorization = self.authorize(self.signed)
            consume = aa._consume

            def paused_consume(*args, **kwargs):
                paused.set(); release.wait(BOUND)
                return consume(*args, **kwargs)
            with patch.object(aa, '_consume', paused_consume):
                with authorization: pass

        a_process, a_queue = self.start_process(process_a)
        self.assertTrue(paused.wait(BOUND))
        self.clocks.elapse(LIFETIME + 1)  # process B reaches the expiry and latches it
        self.assertEqual(self.refused(lambda: self.authorize(self.signed)).code, 'approval_receipt_time')
        release.set()
        self.assertEqual(self.finish(a_process, a_queue), ('refused', 'approval_expired'))
        self.assertEqual(self.consumed(), [])
        self.assertEqual(self.executions(), [])

    def test_an_expiry_latched_between_the_last_check_and_the_dispatch_marker_refuses_the_marker(self):
        paused, release = FORK.Event(), FORK.Event()

        def process_a():
            self.clocks.wall = self.start + 10
            check = aa.ApprovedExecution._check

            def paused_check(authorization):
                check(authorization)
                paused.set(); release.wait(BOUND)
            with self.authorize(self.signed) as permit:
                with patch.object(aa.ApprovedExecution, '_check', paused_check):
                    permit.mark_dispatch()

        a_process, a_queue = self.start_process(process_a)
        self.assertTrue(paused.wait(BOUND))
        self.clocks.elapse(LIFETIME + 1)
        self.assertEqual(self.refused(lambda: self.authorize(self.signed)).code, 'approval_receipt_time')
        release.set()
        self.assertEqual(self.finish(a_process, a_queue), ('refused', 'approval_expired'))
        self.assertEqual(self.executions(), [])
        self.assertEqual(self.consumed(), [(self.request['operation_id'], 'interrupted')])


if __name__ == '__main__':
    unittest.main()
