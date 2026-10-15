"""Approval validity across a process restart (PKG-TIME-AUTHZ-C round B; decision lanes/advisor-restart-time/DECISION.md).

Before this round the time authority knew a backward step only below the latest reading it had recorded, and carried
elapsed time inside one process only. An approval judged open at wall T50 (recorded mark T50) by a process that then
exited could be judged open again by a new process after real time had passed its expiry T100, if the wall clock was by
then set to T60: above the mark, so not a backward step, and the new process re-armed its own deadline from the wall.

The time authority now records, with the mark and in the same write, the host's boot identity, its clock domain and
CLOCK_BOOTTIME. Within the same boot and clock domain the floor includes the mark plus the boot time elapsed since it was
recorded, so a restart carries elapsed time; a changed boot or domain, or a boot time that went backward, is lost
continuity. An open judgment is also a durable row (committed in its own transaction, under the locks, before the caller
is handed its transaction): a process that finds one from a lost session holds that artifact until the wall clock passes
its expiry, when it is closed and latched, or until the artifact is prepared anew.

The boot session is injected the way monotonic is (Clocks.install_session); the tests that are about processes run real
subprocesses against one store, each with its own injected wall time, boot identity and boot time.
"""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from intune_iac import clock, validity
from intune_iac.io import AppError
from plugin_tests.test_clock_authority import START
from plugin_tests.test_restart_clock import BOOT_X, BOOT_Y, Session

REPO = str(Path(__file__).resolve().parent.parent)
LIFETIME = 100
LOST_WORDS = 'cannot be established'
BLIP_WORDS = 'restarting does not clear this'


def fail(code):
    raise AppError(code, 'toy store refusal')


class PreAuthenticationHoldTests(Session):
    def test_the_hold_before_authentication_applies_the_boot_floor_and_writes_nothing(self):
        self.clocks.wall = START + 50
        clock.Floor(self.base / "clock.json").observe(self.clocks.time())
        before = (self.base / 'clock.json').read_bytes()
        self.restart()
        self.clocks.elapse(70)
        self.clocks.step(-60)
        with self.assertRaises(AppError) as raised:
            validity.hold_if_clock_behind(self.base)
        self.assertEqual(raised.exception.code, 'clock_moved_backward')
        self.assertEqual((self.base / 'clock.json').read_bytes(), before)



class StoreTests(Session):
    """validity.critical on a toy store: the open judgment is a durable row, and a lost session holds."""

    def setUp(self):
        super().setUp()
        self.database = self.base / 'toy.sqlite3'
        self.payload = {'issuer': 'issuer-1', 'nonce': 'a' * 32, 'operation_id': 'operation-1',
                        'expires_at': START + LIFETIME}

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.database, timeout=0, isolation_level=None)
        try:
            yield connection
        finally:
            connection.close()

    def store(self, **kwargs):
        return validity.Store(self.base, self.connect, 'latched', fail, create=True, domain='family', **kwargs)

    def enter(self, payload=None, *, body=None, **kwargs):
        with validity.critical(self.store(**kwargs.pop('store', {})), payload or self.payload, 'r' * 64,
                               expired_code='toy_expired', **kwargs) as db:
            if body:
                body()
            db.execute('COMMIT')

    def refused(self, call):
        with self.assertRaises(AppError) as raised:
            call()
        return raised.exception

    def rows(self, sql):
        with self.connect() as db:
            return db.execute(sql).fetchall()

    def test_a_deadline_is_armed_from_the_effective_time_not_the_bare_wall_clock(self):
        self.clocks.wall = START + 50
        self.enter()
        self.restart()
        self.clocks.elapse(70)  # true time T120
        self.clocks.step(-60)  # the wall reads T60
        self.assertLessEqual(validity.deadline(self.base, START + LIFETIME), time.monotonic())  # nothing is left
        self.assertAlmostEqual(validity.deadline(self.base, START + 200) - time.monotonic(), 80, delta=0.01)
        elsewhere = self.base.parent / 'elsewhere'  # a store with no recorded time falls back to the wall clock
        elsewhere.mkdir(mode=0o700)
        self.assertAlmostEqual(validity.deadline(elsewhere, START + LIFETIME) - time.monotonic(), 40, delta=0.01)

    def test_a_same_boot_restart_keeps_an_open_window_open(self):
        self.clocks.wall = START + 50
        self.enter()
        self.restart()
        self.clocks.elapse(10)
        self.enter()  # open: ten seconds passed on the boot clock, as on the wall clock

    def test_a_same_boot_restart_with_the_wall_set_back_above_the_mark_closes_it_and_latches(self):
        self.clocks.wall = START + 50
        self.enter()
        self.restart()
        self.clocks.elapse(70)
        self.clocks.step(-60)
        self.assertEqual(self.refused(self.enter).code, 'toy_expired')
        self.assertEqual(len(self.rows('SELECT * FROM latched_v2')), 1)

    def test_a_reboot_with_an_open_judgment_holds_then_closes_and_latches_at_the_expiry(self):
        self.clocks.wall = START + 50
        self.enter()
        self.restart()
        self.clocks.reboot()
        self.clocks.elapse(70)
        self.clocks.step(-60)  # wall T60
        error = self.refused(self.enter)
        self.assertEqual(error.code, 'clock_moved_backward')
        self.assertIn(LOST_WORDS, error.message)
        self.assertIn('prepared anew', error.message)
        self.assertNotIn(BLIP_WORDS, error.message)
        self.assertEqual(self.rows('SELECT * FROM latched_v2'), [])
        self.clocks.step(40)  # the wall clock reads T100
        self.assertEqual(self.refused(self.enter).code, 'toy_expired')
        self.assertEqual(len(self.rows('SELECT * FROM latched_v2')), 1)
        self.clocks.step(-40)  # and it stays closed
        self.assertEqual(self.refused(self.enter).code, 'toy_expired')

    def test_a_reboot_does_not_hold_an_artifact_judged_for_the_first_time(self):
        self.clocks.wall = START + 50
        self.clocks.reboot()
        self.enter()

    def test_the_open_judgment_survives_a_later_failure_in_the_callers_own_work(self):
        self.clocks.wall = START + 50

        def later_check_fails():
            raise RuntimeError('a later check fails and the caller rolls back')
        with self.assertRaises(RuntimeError):
            self.enter(body=later_check_fails)
        self.assertEqual(len(self.rows('SELECT * FROM latched_open')), 1)
        self.restart()
        self.clocks.reboot()
        self.clocks.elapse(10)
        error = self.refused(self.enter)
        self.assertEqual(error.code, 'clock_moved_backward')
        self.assertIn(LOST_WORDS, error.message)

    def test_the_open_row_is_committed_before_the_caller_is_handed_its_transaction(self):
        self.clocks.wall = START + 50
        seen = []
        self.enter(body=lambda: seen.append(self.rows('SELECT domain, issuer, nonce, operation_id, request_sha256, expires_at, '
                                                      'boot_id FROM latched_open')))
        self.assertEqual(seen, [[('family', 'issuer-1', 'a' * 32, 'operation-1', 'r' * 64, START + LIFETIME, BOOT_X)]])

    def test_a_changed_clock_domain_with_the_same_boot_identity_holds_an_open_judgment(self):
        self.clocks.wall = START + 50
        self.enter()
        self.restart()
        self.clocks.elapse(10)
        self.clocks.domain = 'boottime 0 -50'
        error = self.refused(self.enter)
        self.assertEqual(error.code, 'clock_moved_backward')
        self.assertIn(LOST_WORDS, error.message)

    def test_the_row_alone_carries_elapsed_time_when_the_recorded_time_is_gone(self):
        self.clocks.wall = START + 50
        self.enter()
        (self.base / 'clock.json').unlink()
        self.restart()
        self.clocks.elapse(70)
        self.clocks.step(-60)
        self.assertEqual(self.refused(self.enter).code, 'toy_expired')

    def test_a_recorded_forward_blip_holds_across_a_restart_and_the_words_say_so(self):
        self.clocks.wall = START + 266  # the host clock jumps forward and a check records it
        self.enter(dict(self.payload, expires_at=START + 1000))
        self.restart()
        self.clocks.elapse(5)
        self.clocks.step(-266)  # the clock is corrected
        error = self.refused(lambda: self.enter(dict(self.payload, nonce='b' * 32, expires_at=START + 1000)))
        self.assertEqual(error.code, 'clock_moved_backward')
        self.assertIn(BLIP_WORDS, error.message)
        self.assertIn('Correct the host clock', error.message)

    def test_open_rows_count_against_the_capacity_and_fail_closed(self):
        self.clocks.wall = START + 50
        self.enter(store={'capacity': 1})
        second = dict(self.payload, nonce='b' * 32)
        self.assertEqual(self.refused(lambda: self.enter(second, store={'capacity': 1})).code, 'approval_store_capacity')

    def test_the_open_row_is_replaced_by_a_later_open_judgment_in_the_same_session(self):
        self.clocks.wall = START + 50
        self.enter()
        self.clocks.elapse(5)
        self.enter()
        self.assertEqual(len(self.rows('SELECT * FROM latched_open')), 1)
        self.assertEqual(self.rows('SELECT wall FROM latched_open'), [(START + 55,)])


CHILD = textwrap.dedent('''
    import contextlib, json, sqlite3, sys, time
    sys.path.insert(0, %(repo)r)
    from pathlib import Path
    from intune_iac import clock, validity
    from intune_iac.io import AppError
    args = json.loads(sys.argv[1])
    clock.boot_id = lambda: args['boot_id']
    clock.boottime = lambda: args['boottime']
    clock.clock_domain = lambda: args['domain']
    time.time = lambda: args['wall']

    @contextlib.contextmanager
    def connect():
        connection = sqlite3.connect(args['db'], timeout=0, isolation_level=None)
        try:
            yield connection
        finally:
            connection.close()

    def fail(code):
        raise AppError(code, 'toy store refusal')
    store = validity.Store(Path(args['root']), connect, 'latched', fail, create=True, domain='family')
    payload = {'issuer': 'issuer-1', 'nonce': 'a' * 32, 'operation_id': 'operation-1', 'expires_at': args['expires']}
    outcome = 'open'
    try:
        with validity.critical(store, payload, 'r' * 64, expired_code='expired') as db:
            if args.get('fail_after'):
                raise RuntimeError('a later check fails')
            db.execute('COMMIT')
    except AppError as error:
        outcome = error.code + ': ' + error.message
    except RuntimeError:
        outcome = 'failed_after_the_judgment'
    print(json.dumps({'outcome': outcome}))
''') % {'repo': REPO}


class TwoProcessTests(unittest.TestCase):
    """Real processes on one store, each with its own injected wall time, boot identity and boot time (Astra's table)."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name) / 'store'
        self.base.mkdir(mode=0o700)
        self.database = self.base / 'toy.sqlite3'

    def process(self, *, wall, boot_id=BOOT_X, boottime, domain='boottime 0 0', fail_after=False):
        args = {'root': str(self.base), 'db': str(self.database), 'wall': START + wall, 'boot_id': boot_id,
                'boottime': 1000.0 + boottime, 'domain': domain, 'expires': START + LIFETIME, 'fail_after': fail_after}
        done = subprocess.run([sys.executable, '-B', '-c', CHILD, json.dumps(args)], capture_output=True, text=True, timeout=60,
                              cwd=REPO)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)['outcome']

    def rows(self, sql):
        connection = sqlite3.connect(self.database)
        try:
            return connection.execute(sql).fetchall()
        finally:
            connection.close()

    def test_same_boot_with_seventy_boot_seconds_elapsed_closes_and_latches(self):
        self.assertEqual(self.process(wall=50, boottime=10), 'open')
        self.assertTrue(self.process(wall=60, boottime=80).startswith('expired'))  # T60 on the wall, B70 later on the boot clock
        self.assertEqual(len(self.rows('SELECT * FROM latched_v2')), 1)

    def test_same_boot_with_ten_boot_seconds_elapsed_stays_open(self):
        self.assertEqual(self.process(wall=50, boottime=10), 'open')
        self.assertEqual(self.process(wall=60, boottime=20), 'open')
        self.assertEqual(self.rows('SELECT * FROM latched_v2'), [])

    def test_another_boot_holds_while_the_expiry_is_unestablished_and_closes_at_it(self):
        self.assertEqual(self.process(wall=50, boottime=10), 'open')
        held = self.process(wall=60, boot_id=BOOT_Y, boottime=5)
        self.assertTrue(held.startswith('clock_moved_backward'), held)
        self.assertIn(LOST_WORDS, held)
        self.assertTrue(self.process(wall=100, boot_id=BOOT_Y, boottime=45).startswith('expired'))
        self.assertEqual(len(self.rows('SELECT * FROM latched_v2')), 1)

    def test_a_later_check_that_fails_after_the_open_judgment_still_causes_the_hold(self):
        self.assertEqual(self.process(wall=50, boottime=10, fail_after=True), 'failed_after_the_judgment')
        self.assertEqual(len(self.rows('SELECT * FROM latched_open')), 1)
        held = self.process(wall=60, boot_id=BOOT_Y, boottime=5)
        self.assertTrue(held.startswith('clock_moved_backward'), held)

    def test_a_time_namespace_offset_with_the_same_boot_identity_holds(self):
        self.assertEqual(self.process(wall=50, boottime=10), 'open')
        held = self.process(wall=60, boottime=20, domain='boottime 0 -50')
        self.assertTrue(held.startswith('clock_moved_backward'), held)
        self.assertIn(LOST_WORDS, held)


if __name__ == '__main__':
    unittest.main()
