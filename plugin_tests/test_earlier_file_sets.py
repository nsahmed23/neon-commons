"""A record bound to an earlier file set is history, never authority (PKG-TIME-AUTHZ-B fix round 2, item 2).

The worker, protected and native-Atmos inventories each keep the file sets of earlier releases, and
implementation_history._file_set_relation accepts a record whose file set is the current one or any inventory
entry's own. That relaxation must reach history reads only. These tests make a worker job, a protected request and a
native-Atmos receipt under an earlier file set and check, for each, that it reads as known_earlier through history and
is refused by every path that dispatches or consumes, with no backend, executor or authority call. They also pin the
call sites of the three relation functions, so a new caller that could turn history into acceptance fails here.
"""
import ast
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from intune_iac import approval_authority as aa
from intune_iac import implementation_history as history
from intune_iac import journey_native_atmos as jna
from intune_iac import protected, protected_worker as worker
from intune_iac.io import AppError, digest
from plugin_tests import test_journey_native_atmos as atmos_base
from plugin_tests import test_pin_history_p3b as p3b
from plugin_tests import test_protected_worker_r4 as worker_base

PACKAGE = Path(worker.__file__).parent


def last_entry_with(inventory, earlier):
    """The newest inventory entry that still carries the earlier file set (before the current set was bound)."""
    return next(entry for entry in reversed(inventory) if set(entry['files']) == set(earlier))


def forbidden(name):
    def call(*args, **kwargs):
        raise AssertionError(name + ' was called for a record bound to an earlier file set')
    return call


class WorkerJobOnAnEarlierFileSetTests(unittest.TestCase):
    setUp = worker_base.ProtectedWorkerTests.setUp
    prepare = worker_base.ProtectedWorkerTests.prepare
    job = worker_base.ProtectedWorkerTests.job
    receipt = worker_base.ProtectedWorkerTests.receipt
    state = worker_base.ProtectedWorkerTests.state

    def prepared_under_the_earlier_set(self):
        earlier = dict(last_entry_with(history.WORKER_INVENTORY, history.WORKER_COMPONENTS_EARLIER)['files'])
        self.assertNotEqual(set(earlier), set(worker._implementation()))
        with patch.object(worker, '_implementation', return_value=dict(earlier)):
            self.prepare()
        return earlier

    def test_it_reads_as_known_earlier_and_the_gate_stays_closed(self):
        earlier = self.prepared_under_the_earlier_set()
        self.assertEqual(history.worker_relation(earlier, worker._implementation())['relation'], 'known_earlier')
        status = self.job().status()
        self.assertEqual(status['implementation']['worker_relation'], 'known_earlier')
        self.assertEqual(status['execution_validation']['status'], 'invalidated')
        self.assertEqual(status['execution_validation']['failure_code'], 'worker_implementation_changed')

    def test_dispatch_is_refused_before_anything_is_consumed_or_called(self):
        self.prepared_under_the_earlier_set()
        before = self.state()
        with patch.object(worker.WorkerJob, '_apply', forbidden('_apply')), \
                patch.object(protected, 'inspect_executor', forbidden('inspect_executor')), \
                patch.object(protected, 'validate_native_operation', forbidden('validate_native_operation')), \
                patch.object(aa.ApprovalAuthority, 'authorize', forbidden('authorize')), \
                patch.object(aa, '_consume', forbidden('_consume')):
            with self.assertRaises(AppError) as raised:
                self.job().run(self.receipt())
        self.assertEqual(raised.exception.code, 'worker_implementation_changed')
        self.assertEqual(self.state(), before)
        status = self.job().status()
        self.assertEqual((status['mutation_attempts'], status['approval_consumed']), (0, False))

    def test_reconcile_never_dispatches_and_cancel_is_administrative_only(self):
        # reconcile reads history (recorded mode) but needs a dispatched job; this one never was.
        self.prepared_under_the_earlier_set()
        with patch.object(protected, 'inspect_executor', forbidden('inspect_executor')),                 patch.object(worker.WorkerJob, '_apply', forbidden('_apply')):
            with self.assertRaises(AppError) as raised:
                self.job().reconcile()
            self.assertEqual(raised.exception.code, 'worker_reconciliation_not_required')
            with self.assertRaises(AppError) as raised:  # a normal cancel from a stale record is refused too
                self.job().cancel()
            self.assertEqual(raised.exception.code, 'worker_implementation_changed')
            # The explicit administrative cancel calls no backend (test_earlier_set_cancel_recover covers its event).
            self.assertTrue(self.job().cancel(administrative=True)['cancellation_requested'])
        with self.assertRaises(AppError):
            self.job().run(self.receipt())
        self.assertEqual(self.job().status()['mutation_attempts'], 0)


class ProtectedRequestOnAnEarlierFileSetTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name)
        self.executor = protected.create_synthetic_executor(self.work / 'executor', initial_value={'a': 1}, desired_value={'a': 2}, engine_version='1.10.0')
        self.earlier = last_entry_with(history.PROTECTED_INVENTORY, history.PROTECTED_COMPONENTS_EARLIER)['implementation_sha256']
        self.assertNotEqual(self.earlier, protected._implementation_sha256())
        with patch.object(protected, '_implementation_sha256', return_value=self.earlier):
            self.request = protected.prepare_native_operation(self.executor, ttl_seconds=300)

    def test_it_reads_as_known_earlier_through_history(self):
        self.assertEqual(protected.implementation_relation(self.request)['relation'], 'known_earlier')
        found = protected.validate_native_operation(self.request, executor=self.executor, implementation='recorded')
        self.assertEqual(found['implementation']['relation'], 'known_earlier')

    def test_every_path_that_approves_dispatches_or_consumes_refuses_it_and_changes_nothing(self):
        before = p3b.tree(self.work)
        with patch.object(aa, 'ApprovalAuthority', forbidden('ApprovalAuthority')):
            with self.assertRaises(AppError) as raised:
                protected.approve_synthetic_operation(self.request, executor=self.executor)
            self.assertEqual(raised.exception.code, 'evidence_changed')
            with self.assertRaises(AppError) as raised:
                protected.validate_native_operation(self.request, executor=self.executor)
            self.assertEqual(raised.exception.code, 'evidence_changed')
            result = protected.execute_native_operation(self.request, self.work / 'state', executor=self.executor, approval=None)
        self.assertEqual((result['status'], result['error']['code']), ('rejected', 'evidence_changed'))
        self.assertEqual(p3b.tree(self.work), before, 'a refused request changed state')
        self.assertFalse((self.work / 'state').exists(), 'something was dispatched')
        self.assertFalse((self.work / 'executor/consumed.json').exists())


class NativeAtmosReceiptOnAnEarlierFileSetTests(unittest.TestCase):
    reconstruct = atmos_base.NativeAtmosReceiptTests.reconstruct

    def setUp(self):
        self.earlier = dict(last_entry_with(history.NATIVE_ATMOS_INVENTORY, history.NATIVE_ATMOS_COMPONENTS_EARLIER)['files'])
        self.assertNotEqual(set(self.earlier), set(jna._implementation()))
        with patch.object(jna, '_implementation', return_value=dict(self.earlier)):
            atmos_base.NativeAtmosReceiptTests.setUp(self)

    def test_it_reads_as_known_earlier_in_history_and_is_refused_for_current_use(self):
        report = {}
        result = jna.reconstruct(self.repo, 'physical', 'policy', 'fixture-tool', self.receipt, implementation='recorded', report=report)
        self.assertEqual(result['status'], 'verified')
        self.assertEqual(report['native_atmos']['relation'], 'known_earlier')
        for call in (self.reconstruct,
                     lambda: jna.reconstruct(self.repo, 'physical', 'policy', 'fixture-tool', self.receipt, implementation='current')):
            with self.assertRaises(AppError):
                call()


class RelaxationReachesHistoryOnlyTests(unittest.TestCase):
    """Where the relation functions are called. A call outside this list could turn history into acceptance."""
    ALLOWED = {
        'protected.py': {'protected_relation': {'implementation_relation', '_implementation_gate'}},
        'protected_worker.py': {'worker_relation': {'_implementation_finding', 'check'}},
        'journey_native_atmos.py': {'native_atmos_relation': {'reconstruct'}},
    }
    NAMES = ('protected_relation', 'worker_relation', 'native_atmos_relation', '_file_set_relation')

    def callers(self):
        found = {}
        for path in sorted(PACKAGE.glob('*.py')):
            if path.name == 'implementation_history.py':
                continue
            tree = ast.parse(path.read_text())
            for function in ast.walk(tree):
                if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for node in ast.walk(function):
                    target = node.func if isinstance(node, ast.Call) else None
                    name = getattr(target, 'attr', getattr(target, 'id', None))
                    if name in self.NAMES:
                        found.setdefault(path.name, {}).setdefault(name, set()).add(function.name)
        return found

    def test_the_relation_functions_are_called_only_from_history_reading_code(self):
        found = self.callers()
        for file, names in found.items():
            self.assertIn(file, self.ALLOWED, 'a new caller of a relation function: %s' % file)
            for name, functions in names.items():
                self.assertTrue(functions <= self.ALLOWED[file].get(name, set()),
                                '%s: %s is called from %s' % (file, name, sorted(functions)))

    def test_the_protected_gate_compares_exactly_in_current_mode(self):
        source = (PACKAGE / 'protected.py').read_text()
        self.assertIn("if implementation=='current':\n        if claimed!=current:raise ImplementationChanged(claimed,current)\n"
                      "    elif history.protected_relation", source)

    def test_the_worker_gate_uses_the_relation_only_in_recorded_mode(self):
        source = (PACKAGE / 'protected_worker.py').read_text()
        self.assertIn("implementation != 'recorded' or history.worker_relation(recorded_files, current_files)['relation'] != 'known_earlier'", source)
        self.assertIn("if recorded_files != current_files and (", source)

    def test_current_mode_in_the_atmos_receipt_compares_the_inventory_exactly(self):
        source = (PACKAGE / 'journey_native_atmos.py').read_text()
        self.assertIn("if implementation == 'current':\n            if evidence['implementation'] != current:", source)


if __name__ == '__main__':
    unittest.main()
