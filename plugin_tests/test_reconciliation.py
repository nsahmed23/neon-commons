import importlib
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('intune_iac.execution'), 'execution implementation absent')
        self.assertIsNotNone(importlib.util.find_spec('intune_iac.reconciliation'), 'reconciliation implementation absent')
        self.api = importlib.import_module('intune_iac.execution')
        self.reconcile = importlib.import_module('intune_iac.reconciliation').reconcile_operation
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name); self.state = self.base / 'receipts'
        self.adapter = self.api.create_local_fixture(self.base / 'fixture', policy={'id': 'p', 'v': 1}, assignments=['a'], desired_policy={'id': 'p', 'v': 2}, desired_assignments=['b'])
        self.request = self.api.prepare_operation(self.adapter)

    def interrupt(self, after=False):
        original = self.adapter.execute_step
        def lose(step, expected):
            if after: original(step, expected)
            raise RuntimeError('lost')
        with patch.object(self.adapter, 'execute_step', side_effect=lose):
            return self.api.execute_operation(self.request, self.state, adapter=self.adapter)

    def test_readback_of_unmodified_state_does_not_infer_no_historical_effect(self):
        self.interrupt()
        answer = self.reconcile(self.request['operation_id'], self.state, adapter=self.adapter)
        self.assertEqual(answer['classification'], 'matches_precondition')
        self.assertFalse(answer['retry_authorized'])
        self.assertTrue(self.adapter.lock_path.exists())

    def test_policy_success_assignment_pending_is_partial_not_atomic(self):
        self.interrupt(after=True)
        answer = self.reconcile(self.request['operation_id'], self.state, adapter=self.adapter)
        self.assertEqual(answer['classification'], 'partial_effects_observed')
        self.assertEqual(answer['facets'], {'policy': 'desired', 'assignments': 'precondition'})
        self.assertFalse(answer['retry_authorized'])

    def test_completed_response_lost_can_observe_desired_but_does_not_release_lock(self):
        original = self.api._append_event
        def fail(directory, event):
            if event['event'] == 'completed': raise OSError('lost')
            return original(directory, event)
        with patch.object(self.api, '_append_event', side_effect=fail):
            self.api.execute_operation(self.request, self.state, adapter=self.adapter)
        answer = self.reconcile(self.request['operation_id'], self.state, adapter=self.adapter)
        self.assertEqual(answer['classification'], 'desired_state_observed')
        self.assertFalse(answer['retry_authorized'])
        self.assertTrue(self.adapter.lock_path.exists())

    def test_forged_or_missing_event_chain_rejected(self):
        self.interrupt()
        directory = self.state / self.request['operation_id']
        event = next(directory.glob('000001*.json')); event.write_text('{}')
        answer = self.reconcile(self.request['operation_id'], self.state, adapter=self.adapter)
        self.assertEqual(answer['classification'], 'unknown')
        self.assertFalse(answer['retry_authorized'])

    def test_changed_target_or_failed_readback_stays_unknown(self):
        self.interrupt()
        with patch.object(self.adapter, 'readback', side_effect=OSError('CANARY_PRIVATE')):
            answer = self.reconcile(self.request['operation_id'], self.state, adapter=self.adapter)
        self.assertEqual(answer['classification'], 'unknown')
        self.assertNotIn('CANARY', str(answer))

    def test_absent_adapter_cannot_use_saved_success_as_authority(self):
        self.api.execute_operation(self.request, self.state, adapter=self.adapter)
        answer = self.reconcile(self.request['operation_id'], self.state)
        self.assertEqual(answer['classification'], 'unknown')
        self.assertFalse(answer['retry_authorized'])

    def test_well_hashed_but_impossible_or_extra_field_journal_is_rejected(self):
        import copy
        import json
        from intune_iac.io import canonical, file_sha
        self.interrupt()
        directory = self.state / self.request['operation_id']
        path = directory / '000001.json'; original = json.loads(path.read_text())
        for patch_values in [{'event': 'completed'}, {'step': 'assignments'}, {'secret': 'CANARY'}, {'sequence': True}]:
            forged = copy.deepcopy(original); forged.update(patch_values)
            path.write_bytes(canonical(forged) + b'\n')
            answer = self.reconcile(self.request['operation_id'], self.state, adapter=self.adapter)
            self.assertEqual(answer['classification'], 'unknown', patch_values)
            self.assertNotIn('CANARY', str(answer))
        path.write_bytes(canonical(original) + b'\n')
