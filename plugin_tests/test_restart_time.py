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
from intune_iac.io import AppError, write_json
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



class StoreFixture(Session):
    """A toy store on the shared critical section."""

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


class StoreTests(StoreFixture):
    """validity.critical on a toy store: the open judgment is a durable row, and a lost session holds."""

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
        # Only the exits that work: a new boot, or the clock set to at least the recorded time. Waiting, restarting and a
        # new approval are all held the same way for the rest of the boot, so the words must not offer them.
        self.assertIn('start a new boot of this host', error.message)
        self.assertIn('set the host clock to at least the recorded time', error.message)
        for advice in ('prepare the approval anew', 'prepared anew', 'wait until', 'then restart', 'Correct the host clock'):
            self.assertNotIn(advice, error.message)

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


class MigrationTests(StoreFixture):
    """Approvals judged by code that predates the boot session left a schema 1 floor and no open row. The store records an
    immutable cutoff, in its own database, at its first judgment under the boot session; an artifact issued before it with no
    open row is held until its expiry (then closed) or until it is prepared anew. One issued after it, or any artifact of a
    store that had no history, is judged normally."""

    def legacy_store(self, high_water=START + 50):
        write_json(self.base / 'clock.json', {'schema_version': 'intune-clock-floor/1', 'high_water': high_water})

    def issued(self, at, **changes):
        return dict(self.payload, issued_at=at, **changes)

    def cutoff(self):
        return self.rows('SELECT cutoff FROM latched_cutoff')

    def test_a_pre_migration_approval_cannot_reopen_after_a_restart_with_the_wall_set_back(self):
        self.legacy_store()  # old code judged it open at T50 and left only the mark
        self.clocks.wall = START + 60  # true time is past T100 (the boot clock is not relevant to a schema 1 floor)
        self.clocks.boot += 1000
        error = self.refused(lambda: self.enter(self.issued(START + 40)))
        self.assertEqual(error.code, 'clock_moved_backward')
        self.assertIn(LOST_WORDS, error.message)
        self.assertEqual(self.rows("SELECT name FROM sqlite_master WHERE name = 'latched_open'"), [])  # held: nothing recorded
        self.assertEqual(self.cutoff(), [(START + 60,)])  # but the cutoff is committed, and stays
        self.restart()
        self.assertEqual(self.refused(lambda: self.enter(self.issued(START + 40))).code, 'clock_moved_backward')
        self.clocks.step(40)  # the wall clock reaches the expiry: closed and latched
        self.assertEqual(self.refused(lambda: self.enter(self.issued(START + 40))).code, 'toy_expired')
        self.assertEqual(len(self.rows('SELECT * FROM latched_v2')), 1)

    def test_an_artifact_issued_exactly_at_the_cutoff_is_held(self):
        self.legacy_store(START + 50)  # old code judged it open at T50 and left only the mark
        self.clocks.wall = START + 60  # the wall was set back to T60; this first judgment makes the cutoff T60
        artifact = self.issued(START + 60, expires_at=START + 100)  # issued at the cutoff second: it may have been judged earlier
        error = self.refused(lambda: self.enter(artifact))
        self.assertEqual(error.code, 'clock_moved_backward')
        self.assertEqual(self.cutoff(), [(START + 60,)])
        self.assertEqual(self.rows("SELECT name FROM sqlite_master WHERE name = 'latched_open'"), [])
        self.restart()
        self.assertEqual(self.refused(lambda: self.enter(artifact)).code, 'clock_moved_backward')

    def test_an_artifact_prepared_anew_after_the_cutoff_is_judged_normally(self):
        self.legacy_store()
        self.clocks.wall = START + 60
        self.refused(lambda: self.enter(self.issued(START + 40)))
        fresh = self.issued(START + 61, nonce='b' * 32, operation_id='operation-2')
        self.clocks.elapse(2)
        self.enter(fresh)  # open: issued after the cutoff
        self.assertEqual(len(self.rows('SELECT * FROM latched_open')), 1)

    def test_a_store_with_no_history_holds_nothing(self):
        self.clocks.wall = START + 60
        self.enter(self.issued(START + 40))  # the first judgment of a new store: nothing before it can be legacy
        self.assertEqual(self.cutoff(), [(0.0,)])

    def test_the_cutoff_is_written_once_at_the_first_judgment_and_never_changes(self):
        self.legacy_store()
        self.clocks.wall = START + 60
        self.refused(lambda: self.enter(self.issued(START + 40)))
        first = self.cutoff()
        self.assertEqual(first, [(START + 60,)])
        self.clocks.elapse(30)
        self.enter(self.issued(START + 70, nonce='b' * 32))
        self.assertEqual(self.cutoff(), first)
        with self.connect() as db:
            for statement in ('UPDATE latched_cutoff SET cutoff = 0', 'DELETE FROM latched_cutoff'):
                with self.assertRaises(sqlite3.DatabaseError):
                    db.execute(statement)
        self.assertEqual(self.cutoff(), first)

    def test_deleting_the_recorded_time_cannot_erase_the_cutoff_or_the_hold(self):
        self.legacy_store()
        self.clocks.wall = START + 60
        self.refused(lambda: self.enter(self.issued(START + 40)))
        (self.base / 'clock.json').unlink()
        self.restart()
        self.assertEqual(self.refused(lambda: self.enter(self.issued(START + 40))).code, 'clock_moved_backward')

    def test_a_first_attempt_that_cannot_commit_does_not_make_a_new_store_look_old(self):
        with self.connect() as db:
            db.execute('CREATE TABLE seed (x)')
        reader = sqlite3.connect(self.database, timeout=0, isolation_level=None)
        cursor = reader.execute('SELECT m.name, c.x FROM sqlite_master m, (WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL '
                                'SELECT x + 1 FROM c WHERE x < 5) SELECT x FROM c) c')
        cursor.fetchone()  # a statement left open: its shared lock makes the first commit fail busy
        self.clocks.wall = START + 60
        try:
            with self.assertRaises(sqlite3.OperationalError):
                self.enter(self.issued(START + 40))
        finally:
            cursor.close()
            reader.close()
        self.assertFalse((self.base / 'clock.json').exists())  # the recorded time was not touched
        self.enter(self.issued(START + 40))  # the retry: still a store with no history, so the approval is judged normally
        self.assertEqual(self.cutoff(), [(0.0,)])

    def test_a_first_attempt_that_is_refused_does_not_make_an_old_store_look_new(self):
        self.legacy_store()
        self.clocks.wall = START + 60
        self.refused(lambda: self.enter(self.issued(START + 40)))
        # whatever the first attempt left behind (the recorded time is now schema 2), the cutoff was committed first
        self.assertEqual(self.file()['schema_version'], 'intune-clock-floor/2')
        self.restart()
        self.assertEqual(self.refused(lambda: self.enter(self.issued(START + 40))).code, 'clock_moved_backward')

    def test_an_artifact_that_has_an_open_row_is_not_held_by_the_cutoff(self):
        self.clocks.wall = START + 30
        self.enter(self.issued(START + 20))  # judged under the boot session: it has its row
        self.restart()
        self.clocks.elapse(10)
        self.enter(self.issued(START + 20))

    def other_family(self, payload):
        store = validity.Store(self.base, self.connect, 'second', fail, create=True, domain='second-family')
        with validity.critical(store, payload, 'r' * 64, expired_code='toy_expired') as db:
            db.execute('COMMIT')

    def test_the_cutoff_is_store_wide_so_a_family_judged_later_inherits_the_stores_migration_moment(self):
        self.clocks.wall = START + 50
        self.enter(self.issued(START + 40))  # one family is judged first in a new store: nothing before it is legacy
        self.assertEqual(self.cutoff(), [(0.0,)])
        self.clocks.elapse(10)
        # a second family is judged for the first time later, with an approval issued after the first judgment
        self.other_family(self.issued(START + 55, nonce='c' * 32, operation_id='operation-3'))
        self.assertEqual(self.rows('SELECT cutoff FROM second_cutoff'), [(0.0,)])

    def test_a_family_with_no_history_judged_first_does_not_hide_another_familys_legacy_rows(self):
        # Another family's pre-upgrade (version 1) rows are in the database, and there is no recorded time. A family with
        # no history of its own is judged first: the store's cutoff is decided from the history of every family in the
        # database, so it is not 0, and the other family's legacy approval stays held when it is judged later.
        with self.connect() as db:
            db.execute(validity.table_sql('second'))
            db.execute("INSERT INTO second VALUES ('issuer-1', 'old', 'operation-8', 'q', ?, ?, ?)", (START + 100, START + 50, START + 50))
        self.clocks.wall = START + 60
        self.enter(self.issued(START + 61, nonce='c' * 32, operation_id='operation-3'))  # family A, no history of its own
        self.assertEqual(self.cutoff(), [(START + 60,)])
        store = validity.Store(self.base, self.connect, 'second', fail, create=True, domain='second-family')
        legacy = self.issued(START + 40, nonce='z', operation_id='operation-9')
        with self.assertRaises(AppError) as raised:
            with validity.critical(store, legacy, 'q', expired_code='toy_expired') as db:
                db.execute('COMMIT')
        self.assertEqual(raised.exception.code, 'clock_moved_backward')
        self.assertIn(LOST_WORDS, raised.exception.message)

    def test_an_artifact_without_an_issue_time_is_judged_normally(self):
        self.legacy_store()
        self.clocks.wall = START + 60
        self.enter(dict(self.payload, expires_at=START + 1000))  # a policy or synthetic payload names no issue time


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
