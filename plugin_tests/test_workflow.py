import copy
import importlib.util
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from intune_iac.io import AppError, digest, file_sha, load_json, write_json
from intune_iac.wizard import run_wizard

ROOT = Path(__file__).resolve().parents[1]
POLICY = '22222222-2222-4222-8222-222222222222'
OTHER = '33333333-3333-4333-8333-333333333333'


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'export.json'
        self.context = self.root / 'context.json'
        self.session = self.root / 'guided.json'
        self.output = self.root / 'proposals'
        self.source.write_bytes((ROOT / 'examples/supported/input/export.json').read_bytes())
        self.context.write_bytes((ROOT / 'examples/context.json').read_bytes())
        self.messages = []
        self.prompts = []

    def api(self):
        self.assertIsNotNone(importlib.util.find_spec('intune_iac.workflow'), 'Receipt-backed guided workflow is missing')
        from intune_iac import workflow
        return workflow

    def run_flow(self, answers, supplied=True):
        self.api()
        queue = iter(answers)
        def read(prompt):
            self.prompts.append(prompt)
            value = next(queue, None)
            if value is None:
                raise EOFError()
            return value() if callable(value) else value
        kwargs = {'input_path': self.source, 'context_path': self.context, 'output_path': self.output} if supplied else {}
        return run_wizard(self.session, input_fn=read, output_fn=self.messages.append, guided=True, **kwargs)

    def edit(self, path, function):
        value = load_json(path)
        function(value)
        write_json(path, value)

    def test_guided_entrypoint_reaches_real_generated_handoff(self):
        result = self.run_flow([POLICY, 'generate', 'finish'])
        self.assertEqual(result['status'], 'complete_local')
        self.assertFalse(result['execution_authorized'])
        self.assertTrue((self.output / POLICY / 'generated-files.json').is_file())
        progress = self.api().reconstruct_progress(self.session)
        self.assertEqual(progress['next_state'], 'complete_local')
        self.assertEqual(len(progress['verified_completed']), 9)
        self.assertEqual(progress['external_verified_completed'], [])

    def test_object_selection_changed_cohort_cannot_advance(self):
        self.run_flow(['save'])
        progress = self.api().preview_resume(self.session, {'cohort': {'ring': 'ring1', 'group_ids': []}})
        self.assertEqual(progress['next_state'], 'object_selection')
        self.assertEqual(progress['milestone_index'], 3)

    def test_partial_generation_changed_stack_stays_partial(self):
        self.source.write_bytes((ROOT / 'examples/partial/input/export.json').read_bytes())
        self.run_flow([POLICY, 'save'])
        progress = self.api().preview_resume(self.session, {'stack': 'changed-stack'})
        self.assertEqual(progress['next_state'], 'partial_generate')
        self.assertEqual(progress['milestone_index'], 6)

    def test_missing_mapping_receipt_invalidates_generation_and_descendants(self):
        self.run_flow([POLICY, 'generate', 'save'])
        (self.root / 'guided.json.evidence' / 'mapping.json').unlink()
        progress = self.api().reconstruct_progress(self.session)
        self.assertEqual(progress['next_state'], 'provider_mapping')
        self.assertFalse(progress['execution_authorized'])
        self.assertFalse('generation' in progress['verified_completed'])

    def test_rehashed_forged_receipt_fails_independent_derivation(self):
        self.run_flow([POLICY, 'save'])
        evidence = self.root / 'guided.json.evidence'
        receipt = evidence / 'mapping.json'
        self.edit(receipt, lambda value: value['payload'].update(mapping_status='complete-forged'))
        self.edit(evidence / 'index.json', lambda value: value['receipts'].update(mapping=file_sha(receipt)))
        progress = self.api().reconstruct_progress(self.session)
        self.assertEqual(progress['next_state'], 'provider_mapping')

    def test_generated_mutation_rehashed_by_attacker_is_not_verified(self):
        self.run_flow([POLICY, 'generate', 'save'])
        output = self.output / POLICY
        path = output / 'README.md'
        path.write_text('CHANGED')
        self.edit(output / 'generated-files.json', lambda value: value['files'].update({'README.md': file_sha(path)}))
        progress = self.api().reconstruct_progress(self.session)
        self.assertEqual(progress['next_state'], 'generate')
        self.assertNotIn('generation', progress['verified_completed'])

    def test_saved_frontier_caps_forged_completed_list(self):
        self.run_flow([POLICY, 'generate', 'finish'])
        self.edit(self.session, lambda value: value.update(saved_state='object_selection'))
        progress = self.api().reconstruct_progress(self.session)
        self.assertEqual(progress['next_state'], 'object_selection')
        self.assertEqual(len(progress['verified_completed']), 3)

    def test_receipt_dependency_cycle_and_symlink_are_rejected(self):
        self.run_flow([POLICY, 'save'])
        evidence = self.root / 'guided.json.evidence'
        receipt = evidence / 'source.json'
        self.edit(receipt, lambda value: value['dependencies'].update(source='0'*64))
        self.edit(evidence / 'index.json', lambda value: value['receipts'].update(source=file_sha(receipt)))
        self.assertEqual(self.api().reconstruct_progress(self.session)['next_state'], 'source_selection')
        original = receipt.read_bytes()
        receipt.unlink()
        outside = self.root / 'outside.json'
        outside.write_bytes(original)
        receipt.symlink_to(outside)
        self.assertEqual(self.api().reconstruct_progress(self.session)['next_state'], 'source_selection')

    def test_old_session_is_explicitly_rejected_without_rewriting(self):
        run_wizard(self.session, input_fn=lambda prompt: 'save', output_fn=lambda value: None)
        before = self.session.read_bytes()
        result = self.run_flow(['save'], supplied=False)
        self.assertEqual(result['error'], 'guided_legacy_session')
        self.assertEqual(before, self.session.read_bytes())

    def test_unknown_outcome_never_replays_generation(self):
        self.run_flow([POLICY, 'save'])
        self.edit(self.session, lambda value: value.update(in_flight_outcome='unknown'))
        result = self.run_flow(['generate', 'save'], supplied=False)
        self.assertEqual(result['step'], 'reconciliation_required')
        self.assertFalse(self.output.exists())

    def test_cancelled_resume_requires_explicit_continue_before_writes(self):
        self.run_flow([POLICY, 'cancel'])
        result = self.run_flow(['generate', 'save'], supplied=False)
        self.assertFalse(self.output.exists())
        self.assertEqual(result['status'], 'suspended')
        result = self.run_flow(['continue', 'generate', 'finish'], supplied=False)
        self.assertEqual(result['status'], 'complete_local')

    def test_cohort_contains_supported_and_blocked_policy_without_dropping_either(self):
        result = self.run_flow([POLICY + ',' + OTHER, 'generate', 'finish'])
        self.assertEqual(result['status'], 'complete_local')
        self.assertEqual(result['mapping_status'], 'partial')
        self.assertEqual({path.name for path in self.output.iterdir()}, {POLICY, OTHER})
        self.assertTrue(list((self.output / POLICY).rglob('*.tf')))
        self.assertFalse(list((self.output / OTHER).rglob('*.tf')))
        self.assertTrue((self.output / OTHER / 'BLOCKED.json').is_file())

    def test_cancellation_survives_save_without_resume_intent(self):
        self.run_flow([POLICY, 'cancel'])
        self.run_flow(['save'], supplied=False)
        self.run_flow(['generate', 'save'], supplied=False)
        self.assertFalse(self.output.exists())
        self.assertEqual(load_json(self.session)['lifecycle'], 'cancelled')

    def test_receipt_failure_after_generation_retains_unknown_outcome(self):
        self.run_flow([POLICY, 'save'])
        from intune_iac import workflow
        original = workflow.write_json
        def write(path, value):
            if Path(path).name == 'validation.json':
                raise AppError('write_failed', 'Injected receipt failure')
            return original(path, value)
        with patch.object(workflow, 'write_json', side_effect=write):
            self.run_flow(['generate', 'save'], supplied=False)
        self.assertEqual(load_json(self.session)['in_flight_outcome'], 'unknown')
        self.assertEqual(workflow.reconstruct_progress(self.session)['next_state'], 'reconciliation_required')
        self.assertTrue((self.output / POLICY / 'generated-files.json').is_file())

    def test_source_change_after_prompt_prevents_generation(self):
        def change():
            self.source.write_bytes(self.source.read_bytes() + b'\n')
            return 'generate'
        self.run_flow([POLICY, change, 'save'])
        self.assertFalse(self.output.exists())

    def test_synthetic_receipt_cannot_claim_real_assurance_even_if_rehashed(self):
        self.run_flow([POLICY, 'save'])
        evidence = self.root / 'guided.json.evidence'
        receipt = evidence / 'inventory.json'
        self.edit(receipt, lambda value: value.update(synthetic=False, assurance='authenticated'))
        self.edit(evidence / 'index.json', lambda value: value['receipts'].update(inventory=file_sha(receipt)))
        progress = self.api().reconstruct_progress(self.session)
        self.assertEqual(progress['next_state'], 'inventory')
        self.assertEqual(progress['external_verified_completed'], [])

    def test_cohort_edit_after_generation_returns_to_review_only(self):
        self.run_flow([POLICY, 'generate', 'finish'])
        progress = self.api().preview_resume(self.session, {'cohort': {'ring': 'ring2', 'group_ids': []}})
        self.assertEqual(progress['next_state'], 'adoption_preview')
        self.assertEqual(progress['milestone_index'], 8)

    def test_repository_mode_rejects_synthetic_core_active_generation(self):
        repo = self.root / 'repo'
        (repo / 'stacks').mkdir(parents=True)
        (repo / 'components/terraform/intune-reference').mkdir(parents=True)
        (repo / 'atmos.yaml').write_text('stacks: {base_path: stacks}\ncomponents: {terraform: {base_path: components/terraform, command: tofu}}\n')
        (repo / 'stacks/reference-dev.yaml').write_text('components: {terraform: {intune-reference: {}}}\n')
        answers = iter([POLICY, 'generate', 'finish'])
        result = run_wizard(self.session, input_path=self.source, context_path=self.context, output_path=self.output,
                            repo=repo, guided=True, input_fn=lambda prompt: next(answers), output_fn=self.messages.append)
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['error'], 'syntheticcore_target_unqualified')
        self.assertFalse(self.output.exists())

    def test_session_is_reread_under_lock_before_using_saved_intent(self):
        self.run_flow([POLICY, 'save'])
        from intune_iac import workflow
        original = workflow.os.open
        changed = False
        def race(path, flags, *args, **kwargs):
            nonlocal changed
            if not changed and Path(path).name.startswith('.intune-wizard-lock-'):
                changed = True
                self.edit(self.session, lambda value: value.update(lifecycle='cancelled'))
            return original(path, flags, *args, **kwargs)
        with patch.object(workflow.os, 'open', side_effect=race):
            self.run_flow(['generate', 'save'], supplied=False)
        self.assertTrue(changed)
        self.assertFalse(self.output.exists())
        self.assertEqual(load_json(self.session)['lifecycle'], 'cancelled')

    def test_parent_alias_cannot_hide_source_inside_evidence(self):
        self.api()
        evidence = self.root / 'guided.json.evidence'
        evidence.mkdir()
        victim = evidence / 'inventory.json'
        victim.write_bytes(self.source.read_bytes())
        before = victim.read_bytes()
        (self.root / 'x').mkdir()
        alias = self.root / 'x' / '..' / 'guided.json.evidence' / 'inventory.json'
        result = run_wizard(self.session, input_path=alias, context_path=self.context, output_path=self.output,
                            guided=True, input_fn=lambda prompt: 'save', output_fn=self.messages.append)
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['error'], 'workflow_path_conflict')
        self.assertEqual(victim.read_bytes(), before)
        self.assertFalse(self.session.exists())

    def test_first_use_preserves_preexisting_evidence_directory(self):
        evidence = self.root / 'guided.json.evidence'
        evidence.mkdir()
        victim = evidence / 'inventory.json'
        victim.write_text('existing-user-content')
        result = self.run_flow(['save'])
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['error'], 'workflow_evidence_conflict')
        self.assertEqual(victim.read_text(), 'existing-user-content')
        self.assertFalse(self.session.exists())

    def test_production_capture_remains_inactive_in_guided_repository_journey(self):
        from plugin_tests.test_production import inputs
        source, context = inputs()
        write_json(self.source, source)
        write_json(self.context, context)
        repo = self.root / 'repo'
        (repo / 'stacks').mkdir(parents=True)
        (repo / 'components/terraform/windows-privacy').mkdir(parents=True)
        (repo / 'atmos.yaml').write_text('stacks: {base_path: stacks}\ncomponents: {terraform: {base_path: components/terraform, command: tofu}}\n')
        (repo / 'stacks/workstation-pilot.yaml').write_text('components: {terraform: {windows-privacy: {}}}\n')
        answers = iter([POLICY, 'generate', 'finish'])
        result = run_wizard(self.session, input_path=self.source, context_path=self.context, output_path=self.output,
                            repo=repo, guided=True, input_fn=lambda prompt: next(answers), output_fn=self.messages.append)
        self.assertEqual(result['status'], 'complete_local', result)
        self.assertEqual(result['mapping_status'], 'partial')
        self.assertFalse(result['execution_authorized'])
        self.assertTrue(list(self.output.rglob('*.tf.txt')))
        self.assertFalse(list(self.output.rglob('*.tf')))
        self.assertEqual(self.api().reconstruct_progress(self.session)['external_verified_completed'], [])

    def test_partial_mapping_emits_blockers_and_no_active_iac(self):
        self.source.write_bytes((ROOT / 'examples/partial/input/export.json').read_bytes())
        result = self.run_flow([POLICY, 'generate', 'finish'])
        self.assertEqual(result['status'], 'complete_local')
        self.assertEqual(result['mapping_status'], 'partial')
        self.assertFalse(list(self.output.rglob('*.tf')))
        self.assertFalse(result['execution_authorized'])


if __name__ == '__main__':
    unittest.main()
