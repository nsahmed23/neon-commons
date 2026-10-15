"""The time authority across a process restart (PKG-TIME-AUTHZ-C round B; decision lanes/advisor-restart-time/DECISION.md).

clock.Floor records, with its high-water mark and in the same write, the host's boot identity, its clock domain and
CLOCK_BOOTTIME. Within the same boot and clock domain the floor includes the mark plus the boot time elapsed since it was
recorded, so a new process carries the time that passed while no process ran: a wall clock set back to a value above the
mark is still backward. A different boot or domain, or a boot time that went backward, is lost continuity (the carried part
is dropped and the mark alone remains). Schema 1 files stay readable, marks never lower, and a damaged schema 2 session
fails closed.

The boot session is injected the way monotonic is (Clocks.install_session).
"""
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from intune_iac import clock
from intune_iac.io import AppError, write_json
from plugin_tests.test_clock_authority import Clocks, START

BOOT_X = 'b3c4755e-26bd-4959-a437-47737e4dd6fb'
BOOT_Y = '0f5a6c1e-8d2b-4c47-9a3e-5b1d7e9c2a64'


class Session(unittest.TestCase):
    """Clocks with a boot session, a store directory, and helpers shared by the tests."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name) / 'store'
        self.base.mkdir(mode=0o700)
        self.clocks = Clocks(START)
        for target, name, function in ((time, 'time', self.clocks.time), (clock, 'monotonic', self.clocks.monotonic)):
            patcher = patch.object(target, name, side_effect=function)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.clocks.install_session(self)
        clock.reset_process_anchor()
        self.addCleanup(clock.reset_process_anchor)

    def restart(self):
        """The process exits and a new one starts on the same host: nothing in memory survives."""
        clock.reset_process_anchor()

    def file(self):
        return json.loads((self.base / 'clock.json').read_text())


class FloorTests(Session):
    def floor(self):
        return clock.Floor(self.base / 'clock.json')

    def test_a_rollback_above_the_mark_after_a_restart_is_still_backward(self):
        self.clocks.wall = START + 50
        self.assertEqual(self.floor().observe(self.clocks.time())['effective'], START + 50)
        self.restart()
        self.clocks.elapse(70)  # true time reaches T120, past an expiry at T100
        self.clocks.step(-60)  # the wall is set to T60: above the mark T50, inside the window
        reading = self.floor().observe(self.clocks.time())
        self.assertEqual(reading['effective'], START + 120)
        self.assertTrue(reading['backward'])
        self.assertEqual(clock.window_state(reading, 0, START + 100), 'closed')

    def test_a_restart_keeps_what_the_boot_clock_shows_elapsed_and_no_more(self):
        self.clocks.wall = START + 50
        self.floor().observe(self.clocks.time())
        self.restart()
        self.clocks.boot += 10  # only ten seconds of boot time passed, though the wall clock now reads T60
        self.clocks.step(10)
        reading = self.floor().observe(self.clocks.time())
        self.assertEqual(reading['effective'], START + 60)
        self.assertFalse(reading['backward'])

    def test_a_different_boot_carries_nothing_and_never_lowers_the_mark(self):
        self.clocks.wall = START + 50
        self.floor().observe(self.clocks.time())
        self.restart()
        self.clocks.reboot()
        self.clocks.wall = START + 60
        reading = self.floor().observe(self.clocks.time())
        self.assertEqual(reading['effective'], START + 60)
        self.assertTrue(reading['continuity_lost'])
        self.assertEqual(self.file()['boot_id'], BOOT_Y)  # the new boot's anchor, written with the risen mark
        self.assertEqual(self.file()['high_water'], START + 60)
        self.restart()
        self.clocks.wall = START + 10  # a wall clock far behind the mark is still held by the mark
        self.assertTrue(self.floor().observe(self.clocks.time())['backward'])

    def test_a_changed_clock_domain_with_the_same_boot_identity_is_lost_continuity(self):
        self.clocks.wall = START + 50
        self.floor().observe(self.clocks.time())
        self.restart()
        self.clocks.elapse(10)
        self.clocks.domain = 'boottime 0 -50'  # another time namespace: its boot time is offset
        reading = self.floor().observe(self.clocks.time())
        self.assertTrue(reading['continuity_lost'])
        self.assertEqual(reading['effective'], START + 60)

    def test_a_boot_time_that_went_backward_is_lost_continuity_not_an_error(self):
        self.clocks.wall = START + 50
        self.floor().observe(self.clocks.time())
        self.restart()
        self.clocks.boot -= 500
        reading = self.floor().observe(self.clocks.time())
        self.assertTrue(reading['continuity_lost'])

    def test_a_schema_1_file_stays_readable_is_never_lowered_and_gains_the_session(self):
        write_json(self.base / 'clock.json', {'schema_version': 'intune-clock-floor/1', 'high_water': START + 80})
        self.assertEqual(self.floor().high_water(), START + 80)
        self.clocks.wall = START + 50  # behind the old mark: held, as before
        reading = self.floor().observe(self.clocks.time())
        self.assertTrue(reading['backward'])
        self.assertEqual(self.file()['high_water'], START + 80)  # never lowered
        self.clocks.wall = START + 90
        self.floor().observe(self.clocks.time())
        self.assertEqual(self.file()['schema_version'], 'intune-clock-floor/2')
        self.assertEqual((self.file()['high_water'], self.file()['boot_id']), (START + 90, BOOT_X))

    def test_a_schema_2_file_with_a_damaged_session_fails_closed(self):
        for damage in ({'boot_id': 7}, {'boottime': -1}, {'boottime': 'x'}, {'domain': None, 'boottime': 5.0}):
            record = {'schema_version': 'intune-clock-floor/2', 'high_water': START, 'boot_id': BOOT_X,
                      'domain': 'boottime 0 0', 'boottime': 5.0}
            record.update(damage)
            write_json(self.base / 'clock.json', record)
            with self.subTest(damage=damage), self.assertRaises(AppError) as raised:
                self.floor().observe(self.clocks.time())
            self.assertEqual(raised.exception.code, 'clock_floor_invalid')

    def test_peek_records_nothing_and_applies_the_boot_floor(self):
        self.clocks.wall = START + 50
        self.floor().observe(self.clocks.time())
        before = (self.base / 'clock.json').read_bytes()
        self.restart()
        self.clocks.elapse(70)
        self.clocks.step(-60)
        reading = self.floor().peek(self.clocks.time())
        self.assertEqual(reading['effective'], START + 120)
        self.assertEqual((self.base / 'clock.json').read_bytes(), before)

    def test_no_boot_source_degrades_to_the_mark_alone(self):
        with patch.object(clock, 'boot_id', return_value=None, create=True):
            self.clocks.wall = START + 50
            self.floor().observe(self.clocks.time())
            self.assertIsNone(self.file()['boot_id'])
            self.restart()
            self.clocks.elapse(70)
            self.clocks.step(-60)
            reading = self.floor().observe(self.clocks.time())
        self.assertEqual(reading['effective'], START + 60)
        self.assertFalse(reading['backward'])


if __name__ == '__main__':
    unittest.main()
