"""The protected and native-Atmos implementation digests bind clock.py (PKG-TIME-AUTHZ-B fix round 2, item 1).

protected.py imports clock and relies on its recorded time for every approval window, but the digest of a protected
request covered protected.py, execution.py, io.py and native_pins.py only; the native-Atmos receipt covered the same
set plus its own files. A changed clock.py therefore left both looking current. These tests change clock.py in a
temporary copy and check that each digest changes and the execution gates refuse; records made under the earlier sets
stay readable as history (the P3a and P3b tests cover that, and run unchanged).
"""
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from intune_iac import implementation_history as history
from intune_iac import journey_native_atmos as jna
from intune_iac.io import AppError, digest
from plugin_tests import test_journey_native_atmos as atmos_base
from plugin_tests import test_pin_history_p3b as p3b

PACKAGE = Path(jna.__file__).parent


class ComponentSetTests(unittest.TestCase):
    def test_clock_is_bound_by_both_sets_and_the_earlier_sets_are_kept(self):
        self.assertIn('clock.py', history.PROTECTED_COMPONENTS)
        self.assertIn('clock.py', history.NATIVE_ATMOS_COMPONENTS)
        self.assertNotIn('clock.py', history.PROTECTED_COMPONENTS_EARLIER)
        self.assertNotIn('clock.py', history.NATIVE_ATMOS_COMPONENTS_EARLIER)
        self.assertEqual(history.PROTECTED_COMPONENTS_EARLIER, ('protected.py', 'execution.py', 'io.py', 'native_pins.py'))

    def test_the_native_atmos_receipt_reads_the_shared_list(self):
        self.assertEqual(tuple(jna._implementation()), tuple(history.NATIVE_ATMOS_COMPONENTS))

    def test_the_protected_digest_is_taken_over_the_files_of_the_set_it_is_given(self):
        for entry in history.PROTECTED_INVENTORY:
            self.assertEqual(history.protected_digest(entry['files']), entry['implementation_sha256'], entry['label'])


class ProtectedDigestChangesWithClockTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.copy = p3b.PackageCopy(self.base / 'pkg')
        self.work = self.base / 'work'
        self.work.mkdir()

    def test_a_changed_clock_changes_the_protected_digest(self):
        changed = p3b.PackageCopy(self.base / 'changed', append='clock.py')
        self.assertNotEqual(self.copy.run('digest')['current'], changed.run('digest')['current'])
        self.assertNotEqual(self.copy.current_digest(), changed.current_digest())

    def test_a_request_prepared_before_clock_changed_is_refused_by_approval_and_execution(self):
        self.copy.run('prepare', self.work)
        before = p3b.tree(self.work)
        self.copy.append('clock.py')
        result = self.copy.run('refuse', self.work)
        self.assertNotEqual(result['approve'], 'accepted')
        self.assertEqual(result['approve']['error'], 'evidence_changed')
        self.assertEqual(result['execute']['status'], 'rejected')
        self.assertEqual(result['execute']['error']['code'], 'evidence_changed')
        self.assertIn('current implementation', result['execute']['error']['reason'])
        self.assertEqual(p3b.tree(self.work), before, 'a refused request changed state')
        self.assertFalse((self.work / 'state').exists(), 'something was dispatched')


class NativeAtmosDigestChangesWithClockTests(unittest.TestCase):
    reconstruct = atmos_base.NativeAtmosReceiptTests.reconstruct
    setUp = atmos_base.NativeAtmosReceiptTests.setUp

    def changed_copy(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        copy = Path(directory.name)
        for name in set(history.NATIVE_ATMOS_COMPONENTS) | {'clock.py'}:
            shutil.copyfile(PACKAGE / name, copy / name)
        with open(copy / 'clock.py', 'ab') as stream:
            stream.write(b'\n')
        return copy

    def test_a_changed_clock_changes_the_receipt_inventory_and_current_refuses_the_receipt(self):
        recorded = jna._implementation()
        self.reconstruct()  # the receipt made now verifies under the unchanged files
        copy = self.changed_copy()
        with patch.object(jna, '__file__', str(copy / 'journey_native_atmos.py')):
            self.assertNotEqual(digest(jna._implementation()), digest(recorded))
            with self.assertRaises(AppError):
                jna.reconstruct(self.repo, 'physical', 'policy', 'fixture-tool', self.receipt, implementation='current')


if __name__ == '__main__':
    unittest.main()
