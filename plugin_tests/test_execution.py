"""Adversarial plan inspection and local orchestration qualification."""
import copy
import importlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


def plan(action='no-op'):
    before = {'id': 'policy-identity', 'value': 'before'}
    after = dict(before, value='after') if action == 'update' else copy.deepcopy(before)
    change = {'actions': [action], 'before': before, 'after': after,
              'after_unknown': {}, 'before_sensitive': {}, 'after_sensitive': {}}
    resource = {'address': 'test_policy.main', 'mode': 'managed', 'type': 'test_policy',
                'name': 'main', 'provider_name': 'example.invalid/test', 'change': change}
    return {'format_version': '1.2', 'terraform_version': '1.10.0', 'errored': False,
            'planned_values': {'root_module': {'resources': [dict(address=resource['address'], mode='managed', type='test_policy', name='main', provider_name=resource['provider_name'], schema_version=0, values=copy.deepcopy(after), sensitive_values={})]}}, 'configuration': {}, 'resource_changes': [resource],
            'output_changes': {}, 'prior_state': {'format_version': '1.0', 'terraform_version': '1.10.0',
            'values': {'root_module': {'resources': [dict(address=resource['address'], mode='managed', type='test_policy', name='main', provider_name=resource['provider_name'], schema_version=0, values=copy.deepcopy(before), sensitive_values={})]}}}}


class PlanReviewTests(unittest.TestCase):
    def review(self, value):
        self.assertIsNotNone(importlib.util.find_spec('intune_iac.execution'), 'plan review implementation absent')
        return importlib.import_module('intune_iac.execution').review_plan(value)

    def test_no_change_is_never_execution_authority(self):
        answer = self.review(plan())
        self.assertEqual(answer['status'], 'no_change')
        self.assertFalse(answer['execution_authorized'])
        self.assertEqual(answer['counts']['no-op'], 1)

    def test_update_is_reported_not_implicitly_approved(self):
        answer = self.review(plan('update'))
        self.assertEqual(answer['status'], 'changes_require_review')
        self.assertFalse(answer['execution_authorized'])
        self.assertEqual(answer['counts']['update'], 1)

    def test_destructive_and_replacement_and_forget_blocked(self):
        for actions in [['delete'], ['delete', 'create'], ['create', 'delete'], ['forget'], ['create', 'forget']]:
            value = plan(); value['resource_changes'][0]['change']['actions'] = actions
            self.assertEqual(self.review(value)['status'], 'blocked', actions)

    def test_missing_unknown_future_format_and_engine_fields_blocked(self):
        mutations = [lambda v: v.pop('resource_changes'), lambda v: v.pop('configuration'),
                     lambda v: v.update(format_version='2.0'), lambda v: v.update(format_version='1.99'),
                     lambda v: v.update(terraform_version='1.100.0'), lambda v: v.update(terraform_version=True),
                     lambda v: v.update(new_side_effect=[{}])]
        for mutate in mutations:
            value = plan(); mutate(value)
            self.assertEqual(self.review(value)['status'], 'blocked')

    def test_deferred_incomplete_errored_and_unknown_effects_blocked(self):
        mutations = [lambda v: v.update(deferred_changes=[{}]), lambda v: v.update(complete=False),
                     lambda v: v.update(errored=True),
                     lambda v: v['resource_changes'][0]['change'].update(after_unknown={'x': [True]}),
                     lambda v: v['resource_changes'][0]['change'].update(after_unknown={'x': 'true'}),
                     lambda v: v['resource_changes'][0]['change'].update(actions=['future-action'])]
        for mutate in mutations:
            value = plan(); mutate(value)
            self.assertEqual(self.review(value)['status'], 'blocked')

    def test_sensitive_and_untrusted_names_and_values_never_escape(self):
        value = plan(); change = value['resource_changes'][0]['change']
        change['after']['value'] = 'CANARY_PRIVATE'; change['after_sensitive'] = {'value': True}
        value['resource_changes'][0]['address'] = 'CANARY_RESOURCE_NAME'
        value['output_changes']['CANARY_OUTPUT_NAME'] = copy.deepcopy(change)
        answer = self.review(value)
        self.assertEqual(answer['status'], 'blocked')
        self.assertNotIn('CANARY', json.dumps(answer))

    def test_noop_lie_and_duplicate_resource_identity_blocked(self):
        value = plan(); value['resource_changes'][0]['change']['after']['id'] = 'different'
        self.assertEqual(self.review(value)['status'], 'blocked')
        value = plan(); value['resource_changes'].append(copy.deepcopy(value['resource_changes'][0]))
        self.assertEqual(self.review(value)['status'], 'blocked')

    def test_import_not_no_change_and_identity_mismatch_blocked(self):
        value = plan(); value['resource_changes'][0]['change']['importing'] = {'id': 'policy-identity'}
        answer = self.review(value)
        self.assertEqual(answer['status'], 'changes_require_review')
        self.assertEqual(answer['counts']['import'], 1)
        value['resource_changes'][0]['change']['importing']['id'] = 'another-id'
        self.assertEqual(self.review(value)['status'], 'blocked')

    def test_drift_is_not_no_change(self):
        value = plan(); value['resource_drift'] = copy.deepcopy(plan('update')['resource_changes'])
        answer = self.review(value)
        self.assertEqual(answer['status'], 'blocked')
        self.assertEqual(answer['counts']['drift'], 1)

    def test_output_only_update_is_change(self):
        value = plan(); value['output_changes']['x'] = plan('update')['resource_changes'][0]['change']
        value['planned_values']['outputs'] = {'x': {'value': value['output_changes']['x']['after'], 'sensitive': False}}
        value['prior_state']['values']['outputs'] = {'x': {'value': value['output_changes']['x']['before'], 'type': ['object', {}], 'sensitive': False}}
        self.assertEqual(self.review(value)['status'], 'changes_require_review')

    def test_check_unknown_and_provisioner_blocked(self):
        value = plan(); value['checks'] = [{'address': {}, 'status': 'unknown', 'instances': []}]
        self.assertEqual(self.review(value)['status'], 'blocked')
        value = plan(); value['configuration'] = {'root_module': {'resources': [{'provisioners': [{'type': 'local-exec'}]}]}}
        self.assertEqual(self.review(value)['status'], 'blocked')

    def test_bounds_cycles_nonfinite_and_boolean_masks(self):
        for value in [None, [], {'nested': float('nan')}, {'cycle': None}]:
            if isinstance(value, dict) and 'cycle' in value: value['cycle'] = value
            self.assertEqual(self.review(value)['status'], 'blocked')
        value = plan(); value['resource_changes'][0]['change']['after_unknown'] = {'x': 0}
        self.assertEqual(self.review(value)['status'], 'blocked')


class OperationTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('intune_iac.execution'), 'operation implementation absent')
        self.api = importlib.import_module('intune_iac.execution')
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name); self.state = self.base / 'receipts'
        self.adapter = self.api.create_local_fixture(self.base / 'fixture',
            policy={'id': 'same', 'setting': 'before'}, assignments=[{'group': 'include'}, {'group': 'exclude'}],
            desired_policy={'id': 'same', 'setting': 'after'}, desired_assignments=[{'group': 'include'}, {'group': 'exclude', 'filter': 'new'}])
        self.request = self.api.prepare_operation(self.adapter)

    def run_operation(self, **kwargs):
        return self.api.execute_operation(self.request, self.state, adapter=self.adapter, **kwargs)

    def test_local_write_steps_have_durable_started_and_readback(self):
        result = self.run_operation()
        self.assertEqual(result['status'], 'succeeded_verified')
        self.assertEqual(result['assurance'], 'local_simulation_only')
        self.assertEqual(self.adapter.readback(), self.request['after'])
        events = self.api.read_operation(self.request['operation_id'], self.state)['events']
        self.assertEqual([e['event'] for e in events], ['prepared', 'step_started', 'step_verified', 'step_started', 'step_verified', 'completed'])
        self.assertFalse(self.adapter.lock_path.exists())
        self.assertNotIn('before', ''.join(p.read_text() for p in self.state.rglob('*.json')))

    def test_external_and_json_approval_cannot_authorize(self):
        self.assertEqual(self.api.execute_operation(self.request, self.state)['status'], 'unavailable')
        for key, value in [('approved', True), ('authorization', {'authenticated': True})]:
            request = dict(self.request, **{key: value})
            self.assertEqual(self.api.execute_operation(request, self.state, adapter=self.adapter)['status'], 'rejected')
        request = dict(self.request, action='cloud_apply')
        self.assertEqual(self.api.execute_operation(request, self.state, adapter=self.adapter)['status'], 'unavailable')
        self.assertFalse(self.state.exists())

    def test_each_binding_hash_mutation_rejected_before_write(self):
        before = self.adapter.readback()
        for key in self.request['binding']:
            request = copy.deepcopy(self.request); request['binding'][key] = '0' * 64
            self.assertEqual(self.api.execute_operation(request, self.state, adapter=self.adapter)['status'], 'rejected', key)
        self.assertEqual(self.adapter.readback(), before)
        self.assertFalse(self.state.exists())

    def test_changed_artifact_between_steps_retains_partial_and_lock(self):
        original = self.adapter.execute_step
        def mutate(step, expected):
            original(step, expected)
            if step == 'policy': (self.adapter.root / 'config.json').write_text('{"changed":true}')
        with patch.object(self.adapter, 'execute_step', side_effect=mutate): result = self.run_operation()
        self.assertEqual(result['status'], 'reconciliation_required')
        self.assertTrue(self.adapter.lock_path.exists())
        self.assertEqual(self.adapter.readback()['policy'], self.request['after']['policy'])
        self.assertEqual(self.adapter.readback()['assignments'], self.request['before']['assignments'])

    def test_fail_before_and_after_never_dispatch_next_step(self):
        with patch.object(self.adapter, 'execute_step', side_effect=RuntimeError('CANARY_PRIVATE')):
            result = self.run_operation()
        self.assertEqual(result['status'], 'reconciliation_required')
        self.assertTrue(self.adapter.lock_path.exists())
        self.assertEqual(self.adapter.readback(), self.request['before'])
        self.assertNotIn('CANARY', json.dumps(result))

    def test_lost_response_after_policy_write_requires_readback(self):
        original = self.adapter.execute_step
        def lost(step, expected): original(step, expected); raise RuntimeError('response lost')
        with patch.object(self.adapter, 'execute_step', side_effect=lost): result = self.run_operation()
        self.assertEqual(result['status'], 'reconciliation_required')
        self.assertEqual(self.adapter.readback()['policy'], self.request['after']['policy'])
        self.assertEqual(self.adapter.readback()['assignments'], self.request['before']['assignments'])

    def test_receipt_failure_after_write_retains_started_record_and_lock(self):
        original = self.api._append_event
        def fail(directory, event):
            if event['event'] == 'step_verified': raise OSError('disk full')
            return original(directory, event)
        with patch.object(self.api, '_append_event', side_effect=fail): result = self.run_operation()
        self.assertEqual(result['status'], 'reconciliation_required')
        self.assertTrue(self.adapter.lock_path.exists())
        events = self.api.read_operation(self.request['operation_id'], self.state)['events']
        self.assertEqual(events[-1]['event'], 'step_started')

    def test_initial_receipt_failure_causes_no_effect(self):
        with patch.object(self.api, '_append_event', side_effect=OSError('disk full')): result = self.run_operation()
        self.assertEqual(result['status'], 'reconciliation_required')
        self.assertEqual(self.adapter.readback(), self.request['before'])
        self.assertTrue(self.adapter.lock_path.exists())

    def test_reentry_new_state_directory_and_new_operation_cannot_bypass_lock(self):
        original = self.adapter.execute_step; nested = []
        def concurrent(step, expected):
            nested.append(self.api.execute_operation(self.api.prepare_operation(self.adapter), self.base / 'other', adapter=self.adapter))
            original(step, expected)
        with patch.object(self.adapter, 'execute_step', side_effect=concurrent): self.run_operation()
        self.assertTrue(nested)
        self.assertTrue(all(x['status'] == 'locked' for x in nested))

    def test_keyboard_interrupt_preserves_started_and_lock(self):
        with patch.object(self.adapter, 'execute_step', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): self.run_operation()
        self.assertTrue(self.adapter.lock_path.exists())
        self.assertEqual(self.api.read_operation(self.request['operation_id'], self.state)['events'][-1]['event'], 'step_started')

    def test_completed_operation_id_cannot_replay(self):
        self.assertEqual(self.run_operation()['status'], 'succeeded_verified')
        self.assertEqual(self.run_operation()['status'], 'rejected')

    def test_observed_readback_mismatch_retains_lock(self):
        with patch.object(self.adapter, 'execute_step', return_value=None): result = self.run_operation()
        self.assertEqual(result['status'], 'reconciliation_required')
        self.assertTrue(self.adapter.lock_path.exists())

    def test_symlinks_and_overlapping_journal_rejected(self):
        bad = self.base / 'link'; bad.symlink_to(self.adapter.root, target_is_directory=True)
        with self.assertRaises(ValueError): self.api.LocalFixtureAdapter(bad)
        result = self.api.execute_operation(self.request, self.adapter.root / 'receipts', adapter=self.adapter)
        self.assertEqual(result['status'], 'rejected')

class AdditionalPlanReviewTests(unittest.TestCase):
    review = PlanReviewTests.review
    def test_null_import_and_malformed_known_fields_are_not_ignored(self):
        mutations = [lambda v: v['resource_changes'][0]['change'].update(importing=None),
                     lambda v: v.update(prior_state=[]), lambda v: v.update(variables=[]),
                     lambda v: v.update(relevant_attributes={}),
                     lambda v: v['resource_changes'][0]['change'].update(replace_paths=False)]
        for mutate in mutations:
            value = plan(); mutate(value)
            self.assertEqual(self.review(value)['status'], 'blocked')

    def test_duplicate_change_removed_from_denominator_is_visible(self):
        value = plan()
        value['planned_values'] = {'root_module': {'resources': [
            {'address': 'test_policy.main', 'mode': 'managed', 'type': 'test_policy', 'name': 'main',
             'provider_name': 'example.invalid/test', 'schema_version': 0,
             'values': {'id': 'policy-identity', 'value': 'before'}, 'sensitive_values': {}},
            {'address': 'test_policy.hidden', 'mode': 'managed', 'type': 'test_policy', 'name': 'hidden',
             'provider_name': 'example.invalid/test', 'schema_version': 0,
             'values': {'id': 'hidden', 'value': 'new'}, 'sensitive_values': {}}]}}
        self.assertEqual(self.review(value)['status'], 'blocked')

    def test_planned_values_contradicting_change_after_blocked(self):
        value = plan()
        value['planned_values'] = {'root_module': {'resources': [
            {'address': 'test_policy.main', 'mode': 'managed', 'type': 'test_policy', 'name': 'main',
             'provider_name': 'example.invalid/test', 'schema_version': 0,
             'values': {'id': 'different'}, 'sensitive_values': {}}]}}
        self.assertEqual(self.review(value)['status'], 'blocked')

    def test_bool_number_noop_type_changes_are_not_equal(self):
        for before, after in [(True, 1), (False, 0), (1, True), (0, False)]:
            value = plan(); value['resource_changes'][0]['change']['before']['value'] = {'nested': [before]}
            value['resource_changes'][0]['change']['after']['value'] = {'nested': [after]}
            value['planned_values']['root_module']['resources'][0]['values'] = copy.deepcopy(value['resource_changes'][0]['change']['after'])
            self.assertEqual(self.review(value)['status'], 'blocked')

class OperationRaceTests(unittest.TestCase):
    setUp = OperationTests.setUp
    run_operation = OperationTests.run_operation
    def test_plan_changed_after_started_never_writes_unbound_value(self):
        original = self.api._append_event
        def change(directory, event):
            original(directory, event)
            if event['event'] == 'step_started':
                path = self.adapter.root / 'plan.json'; value = json.loads(path.read_text())
                value['desired']['policy']['setting'] = 'UNREVIEWED'
                path.write_text(json.dumps(value))
        with patch.object(self.api, '_append_event', side_effect=change): result = self.run_operation()
        self.assertEqual(result['status'], 'reconciliation_required')
        self.assertEqual(self.adapter.readback(), self.request['before'])

    def test_changed_desired_identity_cannot_be_prepared(self):
        path = self.adapter.root / 'plan.json'; value = json.loads(path.read_text())
        value['desired']['policy']['id'] = 'substituted'; path.write_text(json.dumps(value))
        with self.assertRaises(ValueError): self.api.prepare_operation(self.adapter)

class OutputDenominatorTests(unittest.TestCase):
    review = PlanReviewTests.review

    def test_planned_output_without_change_or_with_changed_value_blocks(self):
        value = plan(); value['planned_values']['outputs'] = {'hidden': {'value': 'new', 'sensitive': False, 'type': 'string'}}
        self.assertEqual(self.review(value)['status'], 'blocked')
        value['output_changes']['hidden'] = {'actions': ['no-op'], 'before': 'old', 'after': 'old',
            'after_unknown': False, 'before_sensitive': False, 'after_sensitive': False}
        self.assertEqual(self.review(value)['status'], 'blocked')

    def test_removed_output_is_visible_even_when_planned_outputs_omit_it(self):
        value = plan(); value['output_changes']['removed'] = {'actions': ['delete'], 'before': 'old', 'after': None,
            'after_unknown': False, 'before_sensitive': False, 'after_sensitive': False}
        self.assertEqual(self.review(value)['status'], 'blocked')

class NativePlanCorpusTests(unittest.TestCase):
    def test_real_previously_executed_tofu_plans(self):
        from intune_iac.execution import review_plan
        root = Path(__file__).resolve().parents[1] / 'research' / 'enterprise-execution' / 'native-plans'
        for name, status in [('adopt-no-change.json', 'no_change'), ('desired-change.json', 'blocked'),
                             ('prod-isolated-plan.json', 'blocked'), ('import-identity-no-change.json', 'no_change')]:
            with self.subTest(name=name):
                result = review_plan(json.loads((root / name).read_text()))
                self.assertEqual(result['status'], status)
                self.assertFalse(result['execution_authorized'])

class ConcurrentOperationTests(unittest.TestCase):
    setUp = OperationTests.setUp
    run_operation = OperationTests.run_operation

    def test_second_live_thread_with_independent_adapter_and_journal_is_locked(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor
        started = threading.Event(); release = threading.Event()
        original = self.adapter.execute_step
        def pause(step, expected):
            if step == 'policy':
                started.set()
                if not release.wait(3): raise RuntimeError('test timeout')
            original(step, expected)
        other = self.api.LocalFixtureAdapter(self.adapter.root)
        request = self.api.prepare_operation(other)
        with patch.object(self.adapter, 'execute_step', side_effect=pause), ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.run_operation)
            try:
                self.assertTrue(started.wait(3))
                result = self.api.execute_operation(request, self.base / 'other-receipts', adapter=other)
                self.assertEqual(result['status'], 'locked')
                self.assertFalse((self.base / 'other-receipts').exists())
            finally:
                release.set()
            self.assertEqual(future.result(timeout=3)['status'], 'succeeded_verified')

class PriorStateConsistencyTests(unittest.TestCase):
    review = PlanReviewTests.review

    def native(self):
        path = Path(__file__).resolve().parents[1] / 'research/enterprise-execution/native-plans/adopt-no-change.json'
        return json.loads(path.read_text())

    def test_resource_removed_from_both_after_collections_still_detected_in_prior_state(self):
        value = self.native(); removed = value['resource_changes'].pop(0)['address']
        value['planned_values']['root_module']['resources'] = [r for r in value['planned_values']['root_module']['resources'] if r['address'] != removed]
        self.assertEqual(self.review(value)['status'], 'blocked')

    def test_prior_output_cannot_be_hidden_from_both_after_collections(self):
        value = self.native(); removed = next(iter(value['output_changes']))
        value['output_changes'].pop(removed); value['planned_values']['outputs'].pop(removed)
        self.assertEqual(self.review(value)['status'], 'blocked')

    def test_prior_known_values_must_match_resource_and_output_before(self):
        value = self.native(); value['prior_state']['values']['root_module']['resources'][0]['values']['id'] = 'substitute'
        self.assertEqual(self.review(value)['status'], 'blocked')
        value = self.native(); next(iter(value['prior_state']['values']['outputs'].values()))['value'] = 'substitute'
        self.assertEqual(self.review(value)['status'], 'blocked')

    def test_missing_future_and_malformed_prior_state_block(self):
        mutations = [lambda v: v.pop('prior_state'), lambda v: v['prior_state'].update(format_version='2.0'),
                     lambda v: v['prior_state'].update(values=[]), lambda v: v['prior_state'].update(extra_effect={})]
        for mutate in mutations:
            value = self.native(); mutate(value)
            self.assertEqual(self.review(value)['status'], 'blocked')

class LockOwnershipTests(unittest.TestCase):
    setUp = OperationTests.setUp
    run_operation = OperationTests.run_operation

    def test_changed_lock_owner_is_not_removed_by_previous_operation(self):
        original = self.api._append_event
        def replace_owner(directory, event):
            original(directory, event)
            if event['event'] == 'completed':
                path = self.adapter.lock_path / 'owner.json'
                value = json.loads(path.read_text()); value['operation_id'] = '00000000-0000-0000-0000-000000000000'
                path.write_text(json.dumps(value))
        with patch.object(self.api, '_append_event', side_effect=replace_owner): result = self.run_operation()
        self.assertEqual(result['status'], 'reconciliation_required')
        self.assertTrue(self.adapter.lock_path.exists())
