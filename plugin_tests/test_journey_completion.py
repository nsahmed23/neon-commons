"""Full journey proves local work and retains real-world gates."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from intune_iac.io import file_sha, load_json, write_json
ROOT = Path(__file__).resolve().parents[1]
POLICY = '22222222-2222-4222-8222-222222222222'
BEFORE_GENERATE = ['continue'] * 3 + [POLICY] + ['continue'] * 4
AFTER_GENERATE = ['generate', 'continue', 'continue', 'plan', 'approve', 'execute', 'reconcile', 'continue', 'finish']

class JourneyCompletionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'source.json'; self.context = self.root / 'context.json'
        self.source.write_bytes((ROOT / 'examples/supported/input/export.json').read_bytes())
        self.context.write_bytes((ROOT / 'examples/context.json').read_bytes())
        self.session = self.root / 'journey.json'; self.output = self.root / 'proposal'; self.messages = []
    def api(self):
        from intune_iac import journey
        return journey
    def run_flow(self, answers, supplied=True, **kw):
        queue = iter(answers)
        def read(prompt):
            value = next(queue, None)
            if value is None: raise EOFError()
            return value() if callable(value) else value
        paths = dict(input_path=self.source, context_path=self.context, output_path=self.output) if supplied else {}
        return self.api().run_journey(self.session, input_fn=read, output_fn=self.messages.append, **paths, **kw)
    def complete(self):
        return self.run_flow(BEFORE_GENERATE + AFTER_GENERATE)
    def test_contract_is_closed_and_executable(self):
        module = self.api(); contract = module.action_contract()
        self.assertEqual([item['id'] for item in contract['actions']], list(module.STAGES))
        for index, item in enumerate(contract['actions']):
            self.assertEqual(item['requires'], list(module.STAGES[:index]))
            self.assertTrue(item['reads']); self.assertTrue(item['writes']); self.assertTrue(item['recovery'])
            self.assertFalse(item['cloud_authority'])
        self.run_flow(['save'])
        self.assertFalse(module.check_action(self.session, 'execute')['allowed'])
        self.assertFalse(module.check_action(self.session, 'arbitrary_shell')['allowed'])
        self.assertEqual(load_json(ROOT / 'contracts/journey-actions.json'), module.action_contract())
        self.assertEqual(load_json(ROOT / 'contracts/journey-semantics.json'), module.semantic_contract())
    def test_complete_journey_generates_and_reconciles_real_local_artifacts(self):
        result = self.complete(); self.assertEqual(result['status'], 'complete_simulation', result)
        self.assertFalse(result['execution_authorized']); self.assertFalse(result['live_ready'])
        progress = self.api().reconstruct_progress(self.session)
        self.assertEqual(progress['verified_completed'], list(self.api().STAGES))
        self.assertEqual(progress['external_verified_completed'], [])
        self.assertTrue((self.output / POLICY / 'generated-files.json').is_file())
        self.assertEqual(progress['next_state'], 'complete_simulation'); self.assertTrue(progress['live_blockers'])
    def test_saved_completion_flags_are_not_evidence(self):
        self.run_flow(['save']); state = load_json(self.session)
        state['completed'] = list(self.api().STAGES); write_json(self.session, state)
        self.assertEqual(self.api().reconstruct_progress(self.session)['verified_completed'], [])
    def test_source_byte_change_invalidates_inventory_and_descendants(self):
        self.complete(); self.source.write_bytes(self.source.read_bytes() + b'\n')
        result = self.api().reconstruct_progress(self.session)
        self.assertEqual(result['next_state'], 'inventory'); self.assertNotIn('approval', result['verified_completed'])
    def test_changed_generated_bytes_even_with_rehashed_manifest_are_rejected(self):
        self.complete(); target = self.output / POLICY / 'README.md'; target.write_text('changed')
        manifest = target.parent / 'generated-files.json'; value = load_json(manifest)
        value['files']['README.md'] = file_sha(target); write_json(manifest, value)
        result = self.api().reconstruct_progress(self.session)
        self.assertEqual(result['next_state'], 'generation'); self.assertNotIn('execute', result['verified_completed'])
    def test_rehashed_forged_receipt_cannot_create_target_evidence(self):
        self.complete(); path = Path(str(self.session) + '.journey') / 'receipts/target.json'
        value = load_json(path); value['payload']['tenant_assurance'] = 'authenticated'; write_json(path, value)
        self.assertEqual(self.api().reconstruct_progress(self.session)['next_state'], 'target')
    def test_back_and_edit_invalidate_dependencies_and_preserve_old_output(self):
        self.complete(); before = (self.output / POLICY / 'README.md').read_bytes()
        result = self.run_flow(['back selection', 'save'], supplied=False)
        self.assertEqual(result['step'], 'selection'); self.assertEqual((self.output / POLICY / 'README.md').read_bytes(), before)
        result = self.run_flow(['edit output ' + str(self.root / 'new-output'), 'save'], supplied=False)
        self.assertEqual(result['step'], 'selection')
    def test_cancel_requires_resume_and_invalidates_unexecuted_approval(self):
        self.run_flow(BEFORE_GENERATE + AFTER_GENERATE[:5] + ['cancel'])
        result = self.run_flow(['execute', 'save'], supplied=False)
        self.assertNotIn('execute', result['verified_completed']); self.assertEqual(load_json(self.session)['lifecycle'], 'cancelled')
    def test_interrupt_before_execution_does_not_resume_approval_authority(self):
        self.run_flow(BEFORE_GENERATE + AFTER_GENERATE[:5])
        result = self.run_flow(['execute', 'save'], supplied=False)
        self.assertNotIn('execute', result['verified_completed']); self.assertEqual(result['step'], 'approval')
    def test_live_mode_reports_gates_without_execution(self):
        result = self.run_flow(BEFORE_GENERATE + AFTER_GENERATE[:4] + ['save'], mode='live')
        self.assertFalse(result['live_ready']); self.assertFalse(result['execution_authorized'])
        self.assertNotIn('execute', result['verified_completed']); self.assertIn('provider_not_qualified', result['live_blockers'])
    def test_missing_receipt_and_symlink_stop_chain(self):
        self.complete(); path = Path(str(self.session) + '.journey') / 'receipts/preservation.json'
        outside = self.root / 'outside.json'; outside.write_bytes(path.read_bytes()); path.unlink(); path.symlink_to(outside)
        self.assertEqual(self.api().reconstruct_progress(self.session)['next_state'], 'preservation')
    def test_output_conflict_is_not_overwritten(self):
        self.output.mkdir(); (self.output / 'user.txt').write_text('keep')
        result = self.run_flow(BEFORE_GENERATE + ['generate', 'save'])
        self.assertNotIn('generation', result['verified_completed']); self.assertEqual((self.output / 'user.txt').read_text(), 'keep')
    def test_production_generation_keeps_inactive_provider_gate(self):
        from plugin_tests.test_production import inputs
        source, context = inputs(); write_json(self.source, source); write_json(self.context, context)
        result = self.complete(); self.assertEqual(result['status'], 'complete_simulation', result)
        self.assertTrue(list(self.output.rglob('*.tf.txt'))); self.assertFalse(list(self.output.rglob('*.tf')))
        self.assertIn('provider_not_qualified', result['live_blockers'])
    def test_uncertain_generation_reconciles_existing_bytes_without_replay(self):
        from intune_iac.io import AppError
        module = self.api(); original = module.runner.run
        calls = []
        def uncertain(*args, **kwargs):
            calls.append(args[0]); original(*args, **kwargs)
            raise AppError('injected_disconnect', 'Result was lost after writing.')
        with patch.object(module.runner, 'run', side_effect=uncertain):
            result = self.run_flow(BEFORE_GENERATE + ['generate', 'generate', 'reconcile', 'save'])
        self.assertEqual(calls, ['generate'])
        self.assertIn('generation', result['verified_completed'])
        self.assertIsNone(load_json(self.session)['in_flight'])
    def test_saved_approval_receipt_does_not_satisfy_action_authority(self):
        self.run_flow(BEFORE_GENERATE + AFTER_GENERATE[:4])
        module = self.api(); state = module._load(self.session); observed = module._observe(self.session, state)
        module._checkpoint(self.session, state, observed, 'approval', lambda: None)
        preview = module.check_action(self.session, 'execute')
        self.assertFalse(preview['allowed']); self.assertEqual(preview['reason'], 'in_process_grant_required')
        result = self.run_flow(['execute', 'save'], supplied=False)
        self.assertNotIn('execute', result['verified_completed'])
    def test_source_changed_at_dispatch_prompt_stops_generation(self):
        def changed():
            self.source.write_bytes(self.source.read_bytes() + b'\n'); return 'generate'
        result = self.run_flow(BEFORE_GENERATE + [changed, 'save'])
        self.assertFalse(self.output.exists()); self.assertEqual(result['step'], 'inventory')
    def test_process_receipt_failure_survives_suspend_and_reconciles_without_replay(self):
        from intune_iac.io import AppError
        module = self.api(); original = module.write_json
        failed = []
        def interrupted(path, value):
            if Path(path).name == 'execute.json' and not failed:
                failed.append(True); raise AppError('injected_receipt_failure', 'Receipt write interrupted.')
            return original(path, value)
        with patch.object(module, 'write_json', side_effect=interrupted):
            first = self.run_flow(BEFORE_GENERATE + AFTER_GENERATE[:6])
        self.assertEqual(first['step'], 'recovery_required')
        self.assertEqual(load_json(self.session)['in_flight'], 'execute')
        from intune_iac import protected
        with patch.object(protected, 'execute_native_operation', side_effect=AssertionError('must not replay')):
            second = self.run_flow(['reconcile', 'save'], supplied=False)
        self.assertIn('execute', second['verified_completed'])
        self.assertIsNone(load_json(self.session)['in_flight'])
    def test_known_predispatch_rejection_requires_review_without_unknown_outcome(self):
        from intune_iac import protected
        with patch.object(protected, 'execute_native_operation', return_value={'status': 'rejected', 'error': 'expired_request', 'execution_authorized': False}):
            result = self.run_flow(BEFORE_GENERATE + AFTER_GENERATE[:6] + ['save'])
        self.assertEqual(result['step'], 'approval')
        self.assertIsNone(load_json(self.session)['in_flight'])
        self.assertFalse((Path(str(self.session) + '.journey') / 'operations').exists())
    def test_target_intent_must_match_capture_before_target_receipt(self):
        context = load_json(self.context); context['tenant_id'] = '99999999-9999-4999-8999-999999999999'
        write_json(self.context, context)
        result = self.run_flow(['continue', 'continue', 'save'])
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['error'], 'journey_target_mismatch')
        self.assertFalse((Path(str(self.session) + '.journey') / 'receipts/target.json').exists())
if __name__ == '__main__': unittest.main()
