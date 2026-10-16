"""The shared validity decision, tested on its own (PKG-TIME-AUTHZ-B item 1).

intune_iac.validity holds the one critical section that judges an approval's window, records a reached expiry and hands
the open transaction to the caller. The store it works on is a parameter: its root directory, its connection factory
and its expiry table. These tests drive it on a toy store, and check that the approval authority is its first consumer.
"""
import sqlite3
import tempfile
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from intune_iac import approval_authority as aa
from intune_iac import clock, validity
from intune_iac.io import AppError
from plugin_tests import test_approval_authority_v5 as authority_tests
from plugin_tests.test_clock_authority import Clocks

LIFETIME = 60


def fail(code):
    raise AppError(code, 'toy store refusal')


class ToyStoreTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / 'store'
        self.root.mkdir(mode=0o700)
        self.database = self.root / 'toy.sqlite3'
        with self.connect() as db:
            db.execute(validity.table_sql('latched'))
            db.execute(validity.table_sql('latched_other'))
            db.execute(validity.table_v2_sql('latched'))
            db.execute(validity.table_v2_sql('latched_other'))
        self.start = 1_800_000_000
        self.clocks = Clocks(self.start)
        for target, name, function in ((time, 'time', self.clocks.time), (clock, 'monotonic', self.clocks.monotonic)):
            patcher = patch.object(target, name, side_effect=function)
            patcher.start()
            self.addCleanup(patcher.stop)
        clock.reset_process_anchor()
        self.addCleanup(clock.reset_process_anchor)
        self.payload = {'issuer': 'issuer-1', 'nonce': 'a' * 32, 'operation_id': 'operation-1',
                        'expires_at': self.start + LIFETIME}

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.database, timeout=0, isolation_level=None)
        try:
            yield connection
        finally:
            connection.close()

    def store(self, table='latched', capacity=validity.MAX_EXPIRED, root=None):
        return validity.Store(root or self.root, self.connect, table, fail, capacity=capacity,
                              capacity_code='toy_capacity', private_code='toy_not_private')

    def latched(self, table='latched'):
        """The expiry records the section wrote: the version 2 table (nothing writes version 1 any more)."""
        with self.connect() as db:
            return db.execute('SELECT issuer, nonce, operation_id, request_sha256, expires_at FROM ' + table + '_v2').fetchall()

    def refused(self, call):
        with self.assertRaises(AppError) as raised:
            call()
        return raised.exception

    def enter(self, payload=None, store=None, **kwargs):
        """Enter the section and leave it without writing anything, as a caller that only checks."""
        with validity.critical(store or self.store(), payload or self.payload, 'r' * 64, **kwargs) as db:
            self.assertTrue(db.in_transaction)

    def test_an_open_window_hands_the_open_transaction_to_the_caller(self):
        with validity.critical(self.store(), self.payload, 'r' * 64) as db:
            self.assertTrue(db.in_transaction)
            db.execute("INSERT INTO latched_other VALUES ('i','n','o','r',1,1,1)")
            db.execute('COMMIT')
        self.assertEqual(self.latched(), [])
        with self.connect() as db:  # the caller's own insert, made in the transaction the section handed over
            self.assertEqual(db.execute('SELECT count(*) FROM latched_other').fetchone(), (1,))

    def test_a_reached_expiry_is_recorded_in_the_named_table_and_refused(self):
        self.clocks.elapse(LIFETIME + 1)
        self.assertEqual(self.refused(lambda: self.enter(expired_code='toy_expired')).code, 'toy_expired')
        self.assertEqual(self.latched(), [('issuer-1', 'a' * 32, 'operation-1', 'r' * 64, self.start + LIFETIME)])
        self.assertEqual(self.latched('latched_other'), [])

    def test_the_record_refuses_after_a_backward_step_and_a_restart(self):
        self.clocks.elapse(LIFETIME + 1)
        self.refused(lambda: self.enter(expired_code='toy_expired'))
        self.clocks.wall = self.start + LIFETIME - 20
        (self.root / 'clock.json').unlink()  # not even the recorded time remains: the latch alone refuses
        clock.reset_process_anchor()
        self.assertEqual(self.refused(lambda: self.enter(expired_code='toy_expired')).code, 'toy_expired')
        self.assertEqual(len(self.latched()), 1)

    def test_a_backward_step_before_the_expiry_is_held_with_both_times_and_the_recovery_words(self):
        self.clocks.elapse(30)
        self.enter()
        self.clocks.step(-20)
        error = self.refused(self.enter)
        self.assertEqual(error.code, 'clock_moved_backward')
        self.assertIn('reads %d' % (self.start + 10), error.message)
        self.assertIn('time %d' % (self.start + 30), error.message)
        # the recorded time includes the boot time elapsed since it was recorded (the carried floor), so only the exits that
        # work are named: waiting and a new approval are held the same way for the rest of the boot
        self.assertIn('set the host clock to at least the recorded time %d' % (self.start + 30), error.message)
        self.assertIn('start a new boot of this host', error.message)
        self.assertNotIn('wait until', error.message)
        self.assertEqual(self.latched(), [])

    def test_a_monotonic_deadline_reached_is_an_expiry_even_when_the_wall_clock_reads_earlier(self):
        passed = time.monotonic() - 1
        self.assertEqual(self.refused(lambda: self.enter(deadline=passed, expired_code='toy_expired')).code,
                         'toy_expired')
        self.assertEqual(len(self.latched()), 1)

    def test_the_table_is_capped_and_refuses_at_the_cap(self):
        self.clocks.elapse(LIFETIME + 1)
        capped = self.store(capacity=1)
        self.refused(lambda: self.enter(store=capped, expired_code='toy_expired'))
        second = dict(self.payload, nonce='b' * 32)
        self.assertEqual(self.refused(lambda: self.enter(second, capped)).code, 'toy_capacity')
        self.assertEqual(len(self.latched()), 1)

    def test_a_store_made_before_its_expiry_table_existed_gets_it_inside_the_section_when_asked(self):
        with self.connect() as db:
            db.execute('DROP TABLE latched')
        with self.assertRaises(sqlite3.OperationalError):  # by default the table is the store's own responsibility
            self.enter()
        asked = validity.Store(self.root, self.connect, 'latched', fail, create=True)
        with validity.critical(asked, self.payload, 'r' * 64) as db:  # an open window: the caller's commit keeps it
            db.execute('COMMIT')
        self.assertEqual(self.latched(), [])
        self.clocks.elapse(LIFETIME + 1)
        self.assertEqual(self.refused(lambda: self.enter(store=asked, expired_code='toy_expired')).code, 'toy_expired')
        self.assertEqual(len(self.latched()), 1)

    def test_a_store_directory_that_is_not_private_is_refused_with_the_stores_own_code(self):
        other = self.root.parent / 'open'
        other.mkdir(mode=0o755)
        self.assertEqual(self.refused(lambda: self.enter(store=self.store(root=other))).code, 'toy_not_private')

    def judged_open(self, payload, request, store=None):
        """Enter the section for an artifact and return whether it was refused as expired."""
        try:
            with validity.critical(store or self.store(), payload, request, expired_code='toy_expired') as db:
                db.execute('COMMIT')
            return False
        except AppError as error:
            self.assertEqual(error.code, 'toy_expired')
            return True

    def test_an_artifact_that_reuses_another_artifacts_issuer_and_nonce_is_judged_on_its_own(self):
        later = dict(self.payload, operation_id='operation-2', expires_at=self.start + 10 * LIFETIME)
        self.clocks.elapse(LIFETIME + 1)
        self.assertTrue(self.judged_open(self.payload, 'r' * 64))  # the first artifact expires and is latched
        self.assertFalse(self.judged_open(later, 's' * 64))  # a different operation and request, same issuer and nonce
        again = dict(self.payload, expires_at=self.start + 10 * LIFETIME)  # same operation, a different request digest
        self.assertFalse(self.judged_open(again, 't' * 64))
        self.assertTrue(self.judged_open(self.payload, 'r' * 64))  # and the first one stays latched

    def test_the_family_domain_is_part_of_the_key(self):
        other = validity.Store(self.root, self.connect, 'latched', fail, domain='other-family')
        self.clocks.elapse(LIFETIME + 1)
        self.assertTrue(self.judged_open(self.payload, 'r' * 64))
        longer = dict(self.payload, expires_at=self.start + 10 * LIFETIME)
        # same issuer, nonce, operation and request digest, judged for another family
        self.assertFalse(self.judged_open(longer, 'r' * 64, store=other))

    def test_a_version_1_row_still_latches_its_own_artifact_and_only_that_one(self):
        with self.connect() as db:  # a row made before the upgrade: no domain, the identity it stores
            db.execute("INSERT INTO latched VALUES ('issuer-1', ?, 'operation-1', ?, ?, 1, 1)",
                       ('a' * 32, 'r' * 64, self.start + LIFETIME))
        self.assertTrue(self.judged_open(self.payload, 'r' * 64))  # the window is open by the clock; the old row refuses it
        unrelated = dict(self.payload, operation_id='operation-9')
        self.assertFalse(self.judged_open(unrelated, 'r' * 64))
        with self.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM latched').fetchone(), (1,))  # kept, not rewritten

    def test_a_version_1_row_keeps_latching_its_artifact_in_every_domain_after_another_domain_judged_it(self):
        with self.connect() as db:  # a pre-upgrade row: no domain, the identity it stores
            db.execute("INSERT INTO latched VALUES ('issuer-1', ?, 'operation-1', ?, ?, 1, 1)",
                       ('a' * 32, 'r' * 64, self.start + LIFETIME))
        family_a = validity.Store(self.root, self.connect, 'latched', fail, domain='family-a')
        family_b = validity.Store(self.root, self.connect, 'latched', fail, domain='family-b')
        self.assertTrue(self.judged_open(self.payload, 'r' * 64, store=family_b))  # the clock is open; the old row refuses
        with self.connect() as db:
            self.assertEqual(db.execute('SELECT domain, issuer, nonce, operation_id, request_sha256 FROM latched_v2').fetchall(),
                             [('family-b', 'issuer-1', 'a' * 32, 'operation-1', 'r' * 64)])
        clock.reset_process_anchor()  # a restart between the two judgments
        self.assertTrue(self.judged_open(self.payload, 'r' * 64, store=family_a))  # still refused by the other domain
        self.assertTrue(self.judged_open(self.payload, 'r' * 64, store=family_b))
        with self.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM latched').fetchone(), (1,))  # the old row is never rewritten

    def test_nothing_writes_a_version_1_row_any_more(self):
        self.clocks.elapse(LIFETIME + 1)
        self.assertTrue(self.judged_open(self.payload, 'r' * 64))
        with self.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM latched').fetchone(), (0,))  # the version 1 table is legacy only
        self.assertEqual(len(self.latched()), 1)

    def test_the_payload_must_name_its_operation(self):
        bare = {key: value for key, value in self.payload.items() if key != 'operation_id'}
        with self.assertRaises(KeyError):
            self.enter(bare)

    def test_the_cap_counts_the_version_1_rows_and_the_version_2_rows(self):
        with self.connect() as db:
            db.execute("INSERT INTO latched VALUES ('issuer-1', 'old-nonce', 'operation-0', ?, ?, 1, 1)", ('q' * 64, self.start))
        self.clocks.elapse(LIFETIME + 1)
        capped = self.store(capacity=1)
        self.assertEqual(self.refused(lambda: self.enter(store=capped, expired_code='toy_expired')).code, 'toy_capacity')

    def test_only_a_plain_lowercase_table_name_is_accepted(self):
        for name in ('expired; DROP TABLE consumed', 'Expired', '', 'a b'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.store(table=name)

    def test_the_hold_check_before_authentication_reads_the_record_and_writes_nothing(self):
        floor = self.root / 'clock.json'
        validity.hold_if_clock_behind(self.root)  # nothing recorded yet: no hold
        self.assertFalse(floor.exists())
        self.clocks.elapse(30)
        self.enter()
        before = floor.read_bytes()
        self.clocks.step(-20)
        anchors = dict(clock._ANCHORS)
        error = self.refused(lambda: validity.hold_if_clock_behind(self.root))
        self.assertEqual(error.code, 'clock_moved_backward')
        self.assertEqual(floor.read_bytes(), before)
        self.assertEqual(dict(clock._ANCHORS), anchors)
        floor.write_bytes(b'not json')
        validity.hold_if_clock_behind(self.root)  # a damaged record falls through to the caller's own refusal

    def test_the_judgment_is_pure_and_uses_the_shared_window_rule(self):
        reading = {'wall': 100, 'floor': 100, 'effective': 100, 'backward': False}
        behind = dict(reading, wall=90, backward=True)
        self.assertEqual(validity.judge(reading, 101, None, False), 'open')
        self.assertEqual(validity.judge(reading, 100, None, False), 'closed')
        self.assertEqual(validity.judge(dict(reading, wall=90), 100, None, False), 'closed')
        self.assertEqual(validity.judge(behind, 200, None, False), 'clock_moved_backward')
        self.assertEqual(validity.judge(behind, 100, None, False), 'closed')  # a reached expiry outranks the hold
        self.assertEqual(validity.judge(reading, 200, None, True), 'closed')
        self.assertEqual(validity.judge(reading, 200, time.monotonic() - 1, False), 'closed')
        self.assertEqual(validity.judge(reading, 200, time.monotonic() + 100, False), 'open')


class ModuleShapeTests(unittest.TestCase):
    def test_every_top_level_function_is_defined_once(self):
        """A second definition silently replaces the first: a later correction made to only one would not take effect."""
        import ast
        names = [node.name for node in ast.parse(Path(validity.__file__).read_text()).body
                 if isinstance(node, (ast.FunctionDef, ast.ClassDef))]
        self.assertEqual([name for name in set(names) if names.count(name) > 1], [])
        self.assertEqual(names.count('peek'), 1)


class ApprovalAuthorityIsTheFirstConsumerTests(unittest.TestCase):
    setUp_base = authority_tests.ApprovalAuthorityTests.setUp

    def setUp(self):
        self.setUp_base()
        self.addCleanup(self.temp.cleanup)

    def test_the_authority_judges_through_the_shared_critical_section_on_its_own_store(self):
        seen = []
        real = validity.critical

        def spy(store, *args, **kwargs):
            seen.append(store)
            return real(store, *args, **kwargs)
        payload = {'issuer': 'i', 'nonce': 'n' * 32, 'operation_id': 'o', 'expires_at': int(time.time()) + 600}
        with patch.object(validity, 'critical', side_effect=spy):
            with self.authority._critical(payload, 'd' * 64) as db:
                self.assertTrue(db.in_transaction)
        self.assertEqual(len(seen), 1)
        self.assertEqual((seen[0].root, seen[0].table), (self.authority.root, 'expired'))

    def test_the_authority_keeps_no_copy_of_the_judgment(self):
        self.assertFalse(hasattr(aa.ApprovalAuthority, '_judged'))
        self.assertFalse(hasattr(aa.ApprovalAuthority, '_hold_if_backward'))

    def test_the_pre_authentication_hold_is_the_shared_one(self):
        with patch.object(validity, 'hold_if_clock_behind') as hold:
            self.authority.hold_if_clock_behind()
        hold.assert_called_once_with(self.authority.root)


if __name__ == '__main__':
    unittest.main()
