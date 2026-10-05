"""Independent edge invariants for workflow locks and local crash recovery."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from intune_iac import execution, workflow
from intune_iac.io import load_json, write_json
from intune_iac.reconciliation import reconcile_operation

ROOT = Path(__file__).resolve().parents[1]


class WorkflowBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.session = self.base / 'session.json'
        self.source = self.base / 'export.json'
        self.context = self.base / 'context.json'
        self.source.write_bytes((ROOT / 'examples/supported/input/export.json').read_bytes())
        self.context.write_bytes((ROOT / 'examples/context.json').read_bytes())
        self.lock = self.base / ('.intune-wizard-lock-' + hashlib.sha256(str(self.session).encode()).hexdigest()[:32])

    def run_flow(self, reader):
        return workflow.run_guided_workflow(self.session, self.source, self.context,
                                           self.base / 'output', input_fn=reader, output_fn=lambda _: None)

    def test_normal_owned_lock_is_removed_on_save(self):
        result = self.run_flow(lambda _: 'save')
        self.assertEqual(result['status'], 'suspended')
        self.assertFalse(self.lock.exists())

    def test_replaced_lock_is_preserved_on_exit(self):
        replacement = b'other-operation-owner\n'
        def replace_then_save(_):
            self.lock.unlink()
            self.lock.write_bytes(replacement)
            return 'save'
        answer = self.run_flow(replace_then_save)
        self.assertEqual(answer['status'], 'blocked')
        self.assertEqual(answer['error'], 'wizard_lock_lost')
        self.assertTrue(self.lock.exists(), 'An invocation must not remove a replacement lock owned by another operation')
        self.assertEqual(self.lock.read_bytes(), replacement)

    def test_lock_substitution_before_generate_prevents_output(self):
        policy = '22222222-2222-4222-8222-222222222222'
        answers = iter([policy, 'generate'])
        def reader(_):
            answer = next(answers)
            if answer == 'generate':
                self.lock.unlink()
                self.lock.write_bytes(b'other-owner')
            return answer
        answer = self.run_flow(reader)
        self.assertEqual(answer['error'], 'wizard_lock_lost')
        self.assertFalse((self.base / 'output').exists())
        self.assertEqual(self.lock.read_bytes(), b'other-owner')

    def test_same_inode_changed_owner_is_preserved(self):
        def reader(_):
            self.lock.write_bytes(b'changed-owner')
            return 'save'
        answer = self.run_flow(reader)
        self.assertEqual(answer['error'], 'wizard_lock_lost')
        self.assertEqual(self.lock.read_bytes(), b'changed-owner')

    def test_symlink_lock_replacement_is_not_followed_or_removed(self):
        outside = self.base / 'outside'
        outside.write_bytes(b'preserve')
        def reader(_):
            self.lock.unlink()
            self.lock.symlink_to(outside)
            return 'save'
        answer = self.run_flow(reader)
        self.assertEqual(answer['error'], 'wizard_lock_lost')
        self.assertTrue(self.lock.is_symlink())
        self.assertEqual(outside.read_bytes(), b'preserve')

    def test_unhashable_saved_state_is_a_blocked_input_not_a_crash(self):
        self.run_flow(lambda _: 'save')
        value = load_json(self.session)
        value['saved_state'] = ['object_selection']
        write_json(self.session, value)
        try:
            answer = self.run_flow(lambda _: 'save')
        except Exception as error:
            self.fail('Malformed persisted JSON escaped instead of being blocked: ' + type(error).__name__)
        self.assertEqual(answer['status'], 'blocked')
        self.assertFalse(answer['execution_authorized'])
        self.assertFalse((self.base / 'output').exists())


class CrashBoundaryTests(unittest.TestCase):
    def test_all_journal_write_boundaries_keep_effects_observable_without_replay(self):
        # Fail each write-ahead/completion receipt independently. Expected current
        # effects come from the public order policy then assignments, not journal inference.
        expected = ['unknown', 'matches_precondition', 'partial_effects_observed',
                    'partial_effects_observed', 'desired_state_observed', 'desired_state_observed']
        for fail_index, classification in enumerate(expected):
            with self.subTest(receipt_index=fail_index), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                adapter = execution.create_local_fixture(root / 'fixture', policy={'id': 'p', 'v': 1},
                    assignments=['old'], desired_policy={'id': 'p', 'v': 2}, desired_assignments=['new'])
                request = execution.prepare_operation(adapter)
                state = root / 'state'
                append = execution._append_event
                calls = []
                def injected(directory, event):
                    calls.append(event['event'])
                    if len(calls) - 1 == fail_index:
                        raise OSError('simulated receipt write loss')
                    return append(directory, event)
                with patch.object(execution, '_append_event', side_effect=injected):
                    outcome = execution.execute_operation(request, state, adapter=adapter)
                self.assertEqual(outcome['status'], 'reconciliation_required')
                self.assertTrue(adapter.lock_path.exists())
                current = adapter.readback()
                recovered = reconcile_operation(request['operation_id'], state, adapter=adapter)
                self.assertEqual(recovered['classification'], classification)
                self.assertFalse(recovered['retry_authorized'])
                self.assertFalse(recovered['lock_released'])
                replay = execution.execute_operation(request, state, adapter=adapter)
                self.assertEqual(replay['status'], 'locked')
                self.assertEqual(adapter.readback(), current)

    def test_completed_control_has_both_desired_facets_and_no_lock(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            adapter = execution.create_local_fixture(root / 'fixture', policy={'id': 'p'}, assignments=[],
                desired_policy={'id': 'p', 'v': 2}, desired_assignments=['new'])
            request = execution.prepare_operation(adapter)
            result = execution.execute_operation(request, root / 'state', adapter=adapter)
            self.assertEqual(result['status'], 'succeeded_verified')
            self.assertEqual(adapter.readback(), request['after'])
            self.assertFalse(adapter.lock_path.exists())
