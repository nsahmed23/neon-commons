"""The worker implementation digest binds the approval judgment (PKG-TIME-AUTHZ-B fix round, item 1).

The judgment of an approval's window lives in validity.py and the recorded time it relies on in clock.py, besides
approval_authority.py. If a worker job's implementation digest did not cover them, a changed judgment would leave a
job's recorded implementation looking current and the execution gate open. These tests change each file in a temporary
copy and check that the digest changes and the gate refuses with the current-implementation mismatch; and that records
made under the earlier, smaller file set stay readable as history.
"""
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from intune_iac import implementation_history as history
from intune_iac import protected_worker as worker
from intune_iac.io import AppError, digest
from plugin_tests import test_protected_worker_r4 as worker_base

PACKAGE = Path(worker.__file__).parent


class ComponentListTests(unittest.TestCase):
    def test_the_judgment_and_the_recorded_time_are_bound(self):
        self.assertIn('validity.py', worker.WORKER_COMPONENTS)
        self.assertIn('clock.py', worker.WORKER_COMPONENTS)
        self.assertIn('approval_authority.py', worker.WORKER_COMPONENTS)

    def test_the_worker_reads_its_own_component_list(self):
        self.assertEqual(tuple(worker._implementation()), tuple(worker.WORKER_COMPONENTS))
        longer = tuple(worker.WORKER_COMPONENTS) + ('native_atmos.py',)  # a name only the worker's own list could add
        with patch.object(worker, 'WORKER_COMPONENTS', longer):
            self.assertEqual(tuple(worker._implementation()), longer)

    def test_records_made_under_the_earlier_file_set_stay_readable_as_history(self):
        earlier = dict(history.WORKER_INVENTORY[0]['files'])
        self.assertNotIn('validity.py', earlier)
        current = worker._implementation()
        found = history.worker_relation(earlier, current)
        self.assertEqual((found['relation'], found['inventory_label']), ('known_earlier', history.WORKER_INVENTORY[0]['label']))
        for entry in history.WORKER_INVENTORY[:-1]:  # every entry but the current one is an earlier release
            self.assertEqual(history.worker_relation(dict(entry['files']), current)['relation'], 'known_earlier', entry['label'])
        self.assertEqual(history.worker_relation(current, current)['relation'], 'same')

    def test_a_file_set_no_release_recorded_is_unknown(self):
        current = worker._implementation()
        drifted = dict(history.WORKER_INVENTORY[0]['files'], **{'io.py': 'd' * 64})
        self.assertEqual(history.worker_relation(drifted, current)['relation'], 'unknown')
        without = {name: value for name, value in current.items() if name != 'clock.py'}
        self.assertEqual(history.worker_relation(without, current)['relation'], 'unknown')
        self.assertEqual(history.worker_relation(dict(current, extra='e' * 64), current)['relation'], 'unknown')


class ChangedJudgmentIsRefusedTests(unittest.TestCase):
    setUp = worker_base.ProtectedWorkerTests.setUp
    prepare = worker_base.ProtectedWorkerTests.prepare
    job = worker_base.ProtectedWorkerTests.job
    receipt = worker_base.ProtectedWorkerTests.receipt
    state = worker_base.ProtectedWorkerTests.state

    def changed_copy(self, name):
        """A temporary copy of the bound files with one byte appended to one of them."""
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        copy = Path(directory.name)
        for bound in worker.WORKER_COMPONENTS:
            shutil.copyfile(PACKAGE / bound, copy / bound)
        with open(copy / name, 'ab') as stream:
            stream.write(b'\n')
        return copy

    def test_a_changed_validity_or_clock_changes_the_digest_and_the_gate_refuses(self):
        self.prepare()
        recorded = worker._implementation()
        before = self.state()
        for name in ('validity.py', 'clock.py', 'approval_authority.py'):
            with self.subTest(name=name):
                copy = self.changed_copy(name)
                with patch.object(worker, '__file__', str(copy / 'protected_worker.py')):
                    current = worker._implementation()
                    self.assertNotEqual(digest(current), digest(recorded))
                    self.assertEqual([k for k in current if current[k] != recorded[k]], [name])
                    with self.assertRaises(AppError) as raised:
                        self.job().check()
                    self.assertEqual(raised.exception.code, 'worker_implementation_changed')
                    with self.assertRaises(AppError):
                        self.job().run(self.receipt())
                self.assertEqual(self.state(), before, 'a refused dispatch changed the target')
        self.assertEqual(self.job().status()['mutation_attempts'], 0)


if __name__ == '__main__':
    unittest.main()
