import ast
import copy
import json
from pathlib import Path
import tempfile
import unittest

from intune_iac import synthetic
from intune_iac.engine import generate, inspect_source


class SyntheticCompletion(unittest.TestCase):
    def test_seed_and_stable_identity(self):
        first = synthetic.generate_estate(7)
        self.assertEqual(first, synthetic.generate_estate(7))
        self.assertNotEqual(first['capture']['tenant_id'], synthetic.generate_estate(8)['capture']['tenant_id'])
        ids = [p['id'] for p in first['truth']['policies']]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len({p['name'] for p in first['truth']['policies']}), 1)
        self.assertTrue(synthetic.inspect_estate(first)['success'])

    def test_estate_inspection_rejects_corrupted_source(self):
        for field in ('name', 'setting', 'assignment'):
            estate = synthetic.generate_estate()
            if field == 'name': estate['capture']['collections'][0]['pages'][0]['body']['value'][0]['name'] = 'changed'
            elif field == 'setting': estate['capture']['collections'][1]['pages'][0]['body']['value'][0]['settingInstance']['choiceSettingValue']['value'] = 'changed'
            else: estate['capture']['collections'][2]['pages'][0]['body']['value'][0]['target']['groupId'] = 'changed'
            self.assertFalse(synthetic.inspect_estate(estate)['success'])

    def test_limits(self):
        for values in [dict(seed=True), dict(seed=-1), dict(policy_count=0), dict(policy_count=9), dict(case='absent')]:
            with self.assertRaises(ValueError): synthetic.generate_estate(**values)

    def test_oracle_code_is_independent(self):
        tree = ast.parse(Path(synthetic.__file__).read_text())
        imports = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        self.assertFalse(any(n and (n.startswith('reference') or 'production' in n) for n in imports))

    def test_generated_policy_oracle_and_meaningful_mutants(self):
        with tempfile.TemporaryDirectory() as td:
            paths = synthetic.write_estate(Path(td) / 'estate', seed=913)
            estate = json.loads(Path(paths['estate']).read_text())
            result = inspect_source(paths['capture'], paths['context'])
            normalized = result['normalized']
            self.assertFalse(synthetic.compare_normalized(estate, normalized))
            reordered = copy.deepcopy(normalized)
            reordered['desired']['assignments'].reverse()
            reordered['desired']['role_scope_tag_ids'].reverse()
            self.assertFalse(synthetic.compare_normalized(estate, reordered))
            reordered['desired']['assignments'].pop()
            self.assertIn('assignments_changed', synthetic.compare_normalized(estate, reordered))
            changed = copy.deepcopy(normalized)
            changed['desired']['settings']['settings'][0]['settingInstance']['choiceSettingValue']['value'] = 'corruption'
            self.assertIn('settings_changed', synthetic.compare_normalized(estate, changed))
            generated = generate(paths['capture'], paths['context'], Path(td) / 'project')
            self.assertTrue(generated['preservation_verified'])
            with self.assertRaises(FileExistsError): synthetic.write_estate(Path(td) / 'estate')

    def test_each_capture_failure_is_blocked_without_active_iac(self):
        for case in ('denied', 'pagination-loop', 'missing-page', 'unknown-setting'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as td:
                paths = synthetic.write_estate(Path(td) / 'estate', case=case)
                estate = json.loads(Path(paths['estate']).read_text())
                inspected = inspect_source(paths['capture'], paths['context'])
                self.assertFalse(synthetic.compare_normalized(estate, inspected['normalized']))
                result = generate(paths['capture'], paths['context'], Path(td) / 'project')
                self.assertFalse(result['offline_mapping_complete'])
                self.assertFalse(list((Path(td) / 'project').rglob('*.tf')))

    def test_selected_adapter_keeps_full_estate_and_identity(self):
        estate = synthetic.generate_estate(policy_count=4)
        for context in estate['contexts']:
            capture = synthetic.selected_capture(estate, context['selected_policy_id'])
            owners = {c['owner_id'] for c in capture['collections']}
            self.assertEqual(owners, {None, context['selected_policy_id']})
            self.assertEqual(len(estate['capture']['collections']), 9)

    def test_protocol_denials_leave_state_intact(self):
        for case, issue in [('stale-state', 'stale_state'), ('approval-replay', 'approval_replay'), ('wrong-target', 'wrong_target')]:
            with self.subTest(case=case):
                estate = synthetic.generate_estate(case=case)
                before = copy.deepcopy(estate)
                result = synthetic.simulate_local_transition(estate)
                self.assertEqual(estate, before)
                self.assertEqual(result['status'], 'blocked')
                self.assertIn(issue, result['issues'])
                self.assertEqual(result['effects'], 0)
                self.assertEqual(result['before_state_sha256'], result['after_state_sha256'])

    def test_positive_noop_and_replay_and_unknown_fault(self):
        estate = synthetic.generate_estate()
        result = synthetic.simulate_local_transition(estate)
        self.assertTrue(result['converged'])
        self.assertFalse(result['execution_authorized'])
        self.assertEqual(synthetic.simulate_local_transition(result['estate'])['status'], 'blocked')
        with self.assertRaises(ValueError): synthetic.simulate_local_transition(estate, fault='undefined')

    def test_partial_failure_stays_inconclusive(self):
        result = synthetic.simulate_local_transition(synthetic.generate_estate(), fault='after-policy')
        self.assertEqual(result['status'], 'reconciliation_required')
        self.assertFalse(result['converged'])
        self.assertEqual(synthetic.simulate_local_transition(result['estate'])['status'], 'blocked')

    def test_empty_omitted_and_denied_are_different(self):
        for case, expected in [('empty-assignments', []), ('omitted-assignments', None), ('denied', None)]:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as td:
                paths = synthetic.write_estate(Path(td) / 'estate', case=case)
                result = inspect_source(paths['capture'], paths['context'])
                self.assertEqual(result['normalized']['desired']['assignments'], expected)
                if expected is None:
                    corrupted = copy.deepcopy(result['normalized'])
                    corrupted['desired']['assignments'] = []
                    self.assertIn('unknown_assignments_became_known', synthetic.compare_normalized(synthetic.generate_estate(case=case), corrupted))

    def test_real_graph_size_gate(self):
        from intune_iac.graph import build_graph
        from intune_iac.io import AppError
        estate = synthetic.generate_estate(policy_count=8)
        capture = copy.deepcopy(estate['capture'])
        prototype = capture['collections'][0]['pages'][0]['body']['value'][0]
        records = []
        for index in range(65):
            item = copy.deepcopy(prototype)
            item['id'] = synthetic._uid(42, 'scale-policy', index)
            records.append(item)
        capture['collections'] = [synthetic._collection('policies', None, records, page_size=65)]
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'scale.json'
            path.write_text(json.dumps(capture))
            with self.assertRaises(AppError) as error:
                build_graph(path)
            self.assertEqual(error.exception.code, 'graph_projection_budget')

    def test_target_context_expiry_lease_and_faults(self):
        for case in ('wrong-cloud','wrong-principal','wrong-backend','wrong-lineage','expired-approval','plan-substitution','lease-loss'):
            with self.subTest(case=case):
                self.assertEqual(synthetic.simulate_local_transition(synthetic.generate_estate(case=case))['status'], 'blocked')
        for fault in ('before-policy','after-policy','before-assignment','after-assignment','before-state','after-state','before-receipt','after-receipt'):
            with self.subTest(fault=fault):
                result = synthetic.simulate_local_transition(synthetic.generate_estate(), fault=fault)
                self.assertEqual(result['status'], 'reconciliation_required')
                self.assertFalse(result['converged'])
                self.assertEqual(result['effects'], 0)

    def test_state_and_action_coverage_are_required_for_noop(self):
        for corruption in ('missing-state', 'lost-assignment', 'changed-setting', 'empty-actions', 'duplicate-action', 'unexpected-action'):
            with self.subTest(corruption=corruption):
                estate = synthetic.generate_estate()
                oid = estate['truth']['policies'][0]['id']
                if corruption == 'missing-state': estate['state']['objects'] = {}
                elif corruption == 'lost-assignment': estate['state']['objects'][oid]['assignments'] = []
                elif corruption == 'changed-setting': estate['state']['objects'][oid]['settings'] = {}
                elif corruption == 'empty-actions': estate['plan']['actions'] = []
                elif corruption == 'duplicate-action': estate['plan']['actions'].append(copy.deepcopy(estate['plan']['actions'][0]))
                else: estate['plan']['actions'][0]['id'] = 'unrelated'
                estate['approval']['plan_sha256'] = synthetic._hash(estate['plan'])
                self.assertFalse(synthetic.inspect_estate(estate)['success'])
                result = synthetic.simulate_local_transition(estate)
                self.assertEqual(result['status'], 'blocked')
                self.assertFalse(result['converged'])
                self.assertEqual(result['effects'], 0)

    def test_legitimate_state_and_action_order_is_accepted(self):
        estate = synthetic.generate_estate()
        estate['plan']['actions'].reverse()
        estate['approval']['plan_sha256'] = synthetic._hash(estate['plan'])
        for policy in estate['state']['objects'].values():
            policy['assignments'].reverse()
            policy['role_scope_tag_ids'].reverse()
        self.assertTrue(synthetic.inspect_estate(estate)['success'])
        self.assertTrue(synthetic.simulate_local_transition(estate)['converged'])

    def test_capture_substitution_and_boolean_serial_are_blocked(self):
        estate = synthetic.generate_estate()
        estate['capture']['captured_at'] = '2020-01-01T00:00:00Z'
        self.assertIn('source_changed', synthetic.simulate_local_transition(estate)['issues'])
        estate = synthetic.generate_estate()
        estate['state']['serial'] = True
        self.assertIn('invalid_state_serial', synthetic.simulate_local_transition(estate)['issues'])

    def test_tampered_plan_and_repository_fail(self):
        for key in ('plan', 'repository'):
            estate = synthetic.generate_estate()
            estate[key]['repository_revision' if key == 'plan' else 'revision'] = 'changed'
            self.assertEqual(synthetic.simulate_local_transition(estate)['status'], 'blocked')

if __name__ == '__main__': unittest.main()
