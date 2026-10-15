"""Each bound consumer owns its current component list (PKG-TIME-AUTHZ-B fix round 3, item 1).

The files an implementation digest covers used to be listed in implementation_history.py, which no digest binds. An older
copy of that module (from before clock.py or validity.py was bound) could therefore drop them from what is bound, and a
request or job prepared under that mixed package would read the same as the one it is checked against. Now
protected.py owns the protected set, protected_worker.py the worker set and journey_native_atmos.py the native-Atmos
set, all of them bound; implementation_history.py keeps only historical sets, the inventories and the relation logic.
The tests stand an older history module in for the current one, prepare under it, change clock.py (and validity.py for
the worker) in a temporary copy, and check that every current-mode gate still refuses.
"""
import shutil
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from intune_iac import implementation_history as history
from intune_iac import journey_native_atmos as jna
from intune_iac import protected, protected_worker as worker
from intune_iac.io import AppError, digest
from plugin_tests import test_journey_native_atmos as atmos_base
from plugin_tests import test_protected_worker_r4 as worker_base

PACKAGE = Path(protected.__file__).parent
BOUND = ('protected.py', 'execution.py', 'io.py', 'native_pins.py', 'clock.py', 'validity.py', 'journey_native_atmos.py',
         'native_atmos.py', 'repository.py', 'protected_worker.py', 'provider_execution.py', 'approval_authority.py',
         'provider_journey.py', 'azure_backend.py')  # every file any of the three digests binds, now or earlier


def older_history():
    """What an older implementation_history.py supplied: the current sets and the digest as they were before clock.py
    (protected, native Atmos) and validity.py (worker) were bound. create=True because the current module no longer
    has these names."""
    earlier_protected = ('protected.py', 'execution.py', 'io.py', 'native_pins.py')
    earlier_atmos = ('journey_native_atmos.py', 'native_atmos.py', 'repository.py', 'protected.py', 'io.py', 'native_pins.py')
    earlier_worker = ('protected_worker.py', 'protected.py', 'provider_execution.py', 'approval_authority.py',
                      'provider_journey.py', 'azure_backend.py', 'execution.py', 'io.py', 'native_pins.py')
    stack = ExitStack()
    for name, value in (('PROTECTED_COMPONENTS', earlier_protected), ('NATIVE_ATMOS_COMPONENTS', earlier_atmos),
                        ('WORKER_COMPONENTS', earlier_worker)):
        stack.enter_context(patch.object(history, name, value, create=True))
    stack.enter_context(patch.object(history, 'protected_digest',
                                     lambda files: digest([files[name] for name in earlier_protected]), create=True))
    return stack


def copy_of(components, changed):
    """A temporary copy of the files, with one byte appended to each file in changed. Returns the directory."""
    directory = tempfile.TemporaryDirectory()
    copy = Path(directory.name)
    for name in set(components) | set(changed):
        shutil.copyfile(PACKAGE / name, copy / name)
    for name in changed:
        with open(copy / name, 'ab') as stream:
            stream.write(b'\n')
    return directory


class OwnershipTests(unittest.TestCase):
    def test_each_consumer_owns_its_current_list(self):
        self.assertIn('clock.py', protected.PROTECTED_COMPONENTS)
        self.assertIn('clock.py', jna.NATIVE_ATMOS_COMPONENTS)
        self.assertIn('validity.py', worker.WORKER_COMPONENTS)
        self.assertIn('clock.py', worker.WORKER_COMPONENTS)
        self.assertEqual(tuple(protected._implementation_files()), tuple(protected.PROTECTED_COMPONENTS))
        self.assertEqual(tuple(jna._implementation()), tuple(jna.NATIVE_ATMOS_COMPONENTS))
        self.assertEqual(tuple(worker._implementation()), tuple(worker.WORKER_COMPONENTS))

    def test_the_history_module_keeps_only_historical_sets(self):
        for name in ('PROTECTED_COMPONENTS', 'NATIVE_ATMOS_COMPONENTS', 'WORKER_COMPONENTS'):
            self.assertFalse(hasattr(history, name), name + ' belongs to its consumer')
        self.assertEqual(history.PROTECTED_COMPONENTS_EARLIER, ('protected.py', 'execution.py', 'io.py', 'native_pins.py'))
        self.assertEqual(len(history.NATIVE_ATMOS_COMPONENTS_EARLIER), 6)
        self.assertEqual(len(history.WORKER_COMPONENTS_EARLIER), 9)

    def test_the_relation_reports_the_consumers_current_set(self):
        current = worker._implementation()
        self.assertEqual(history.worker_relation(current, current)['bound_components'], list(worker.WORKER_COMPONENTS))
        found = protected.implementation_relation({'bindings': {'implementation_sha256': protected._implementation_sha256()}})
        self.assertEqual(found['bound_components'], list(protected.PROTECTED_COMPONENTS))


class ProtectedUnderAnOlderHistoryTests(unittest.TestCase):
    def test_a_request_prepared_under_an_older_history_module_is_refused_after_clock_changes(self):
        with tempfile.TemporaryDirectory() as work, older_history():
            executor = protected.create_synthetic_executor(Path(work) / 'executor', initial_value={'a': 1}, desired_value={'a': 2}, engine_version='1.13.1')
            request = protected.prepare_native_operation(executor, ttl_seconds=300)
            protected.approve_synthetic_operation(request, executor=executor)  # the control: approvable as prepared
            copy = copy_of(BOUND, ['clock.py'])
            self.addCleanup(copy.cleanup)
            with patch.object(protected, '__file__', str(Path(copy.name) / 'protected.py')):
                with self.assertRaises(AppError) as raised:
                    protected.approve_synthetic_operation(request, executor=executor)
                self.assertEqual(raised.exception.code, 'evidence_changed')
                result = protected.execute_native_operation(request, Path(work) / 'state', executor=executor, approval=None)
            self.assertEqual((result['status'], result['error']['code']), ('rejected', 'evidence_changed'))
            self.assertFalse((Path(work) / 'state').exists(), 'something was dispatched')


class WorkerUnderAnOlderHistoryTests(unittest.TestCase):
    setUp = worker_base.ProtectedWorkerTests.setUp
    prepare = worker_base.ProtectedWorkerTests.prepare
    job = worker_base.ProtectedWorkerTests.job
    receipt = worker_base.ProtectedWorkerTests.receipt

    def test_a_job_prepared_under_an_older_history_module_is_refused_after_clock_or_validity_changes(self):
        with older_history():
            self.prepare()
            for name in ('clock.py', 'validity.py'):
                with self.subTest(name=name):
                    copy = copy_of(BOUND, [name])
                    self.addCleanup(copy.cleanup)
                    with patch.object(worker, '__file__', str(Path(copy.name) / 'protected_worker.py')):
                        with self.assertRaises(AppError) as raised:
                            self.job().check()
                        self.assertEqual(raised.exception.code, 'worker_implementation_changed')
                        with self.assertRaises(AppError):
                            self.job().run(self.receipt())
            self.assertEqual(self.job().status()['mutation_attempts'], 0)


class AtmosUnderAnOlderHistoryTests(unittest.TestCase):
    reconstruct = atmos_base.NativeAtmosReceiptTests.reconstruct

    def setUp(self):
        stack = older_history()
        stack.__enter__()
        self.addCleanup(stack.close)
        atmos_base.NativeAtmosReceiptTests.setUp(self)  # the receipt is made under the older module

    def test_a_receipt_made_under_an_older_history_module_is_refused_after_clock_changes(self):
        self.reconstruct()  # the control: it verifies as made
        copy = copy_of(BOUND, ['clock.py'])
        self.addCleanup(copy.cleanup)
        with patch.object(jna, '__file__', str(Path(copy.name) / 'journey_native_atmos.py')):
            with self.assertRaises(AppError):
                jna.reconstruct(self.repo, 'physical', 'policy', 'fixture-tool', self.receipt, implementation='current')


if __name__ == '__main__':
    unittest.main()
