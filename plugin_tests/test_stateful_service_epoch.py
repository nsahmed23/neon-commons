"""Independent corruption, stateful fault, and connected semantic-model probes."""
from concurrent.futures import ThreadPoolExecutor
import copy
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from intune_iac.io import AppError, digest, load_json, write_json
from intune_iac.modeled_service import BASE, ModeledService, project_capture, compare_semantics
from intune_iac.synthetic import generate_estate
from plugin_tests import test_journey_completion as journey_cases
BEFORE_GENERATE, AFTER_GENERATE, POLICY = journey_cases.BEFORE_GENERATE, journey_cases.AFTER_GENERATE, journey_cases.POLICY

class StatefulServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.estate = generate_estate(seed=104, policy_count=3)
        self.ids = [p['id'] for p in self.estate['truth']['policies']]
        self.truth = {'schema_version': 'intune-semantic-estate/1.0',
            'tenant_id': self.estate['truth']['tenant_id'], 'cloud': 'public',
            'objects': {p['id']: {k: copy.deepcopy(v) for k, v in p.items() if k != 'id'} for p in self.estate['truth']['policies']}}
        self.service = ModeledService.create(self.root / 'service', self.estate['capture'], self.ids)
        self.tenant = self.truth['tenant_id']
    def request(self, method, path=None, **kw):
        return self.service.request(method, path or BASE, tenant_id=self.tenant, **kw)
    def desired(self):
        desired = copy.deepcopy(self.truth['objects'][self.ids[0]])
        desired['name'] = 'Explicit synthetic change'; desired['assignments'] = desired['assignments'][:1]
        return desired
    def test_raw_projection_matches_independently_generated_estate_truth(self):
        self.assertEqual(compare_semantics(self.truth, project_capture(self.estate['capture'], self.ids)), [])
        self.assertEqual(compare_semantics(self.truth, self.service.readback(tenant_id=self.tenant)), [])
        logs = self.service.snapshot()['requests']
        self.assertEqual([r['method'] for r in logs], ['GET', 'GET'])
        self.assertTrue(all(r['status'] == 200 and not r['mutation_committed'] for r in logs))
    def test_exact_nested_settings_and_filter_exclusion_fields_survive_readback(self):
        observed = self.service.readback(tenant_id=self.tenant)
        for oid, expected in self.truth['objects'].items():
            self.assertEqual(expected['settings'], observed['objects'][oid]['settings'])
            self.assertEqual(expected['assignments'], observed['objects'][oid]['assignments'])
    def test_raw_projector_rejects_unsafe_empty_and_bad_pagination(self):
        for case in ('denied', 'pagination-loop', 'missing-page', 'omitted-assignments', 'null-assignments', 'cross-origin-page', 'duplicate-page', 'missing-initial-page'):
            with self.subTest(case=case), self.assertRaises(AppError):
                project_capture(generate_estate(seed=104, case=case)['capture'], self.ids)
    def test_explicit_empty_assignments_and_permutations_are_valid(self):
        for case in ('empty-assignments', 'reordered'):
            actual = project_capture(generate_estate(seed=104, case=case)['capture'], self.ids)
            expected = copy.deepcopy(self.truth)
            if case == 'empty-assignments': expected['objects'][self.ids[0]]['assignments'] = []
            self.assertEqual(compare_semantics(expected, actual), [])
    def test_corruption_oracle_detects_identity_omission_null_filters_and_settings(self):
        mutations = []
        wrong = copy.deepcopy(self.truth); wrong['objects'][self.ids[0]]['assignments'].pop(); mutations.append(wrong)
        wrong = copy.deepcopy(self.truth); wrong['objects'][self.ids[0]]['assignments'] = None; mutations.append(wrong)
        wrong = copy.deepcopy(self.truth); del wrong['objects'][self.ids[0]]['settings']; mutations.append(wrong)
        wrong = copy.deepcopy(self.truth); wrong['objects'][self.ids[0]]['assignments'][0]['filter_type'] = 'none'; mutations.append(wrong)
        wrong = copy.deepcopy(self.truth); wrong['objects'][self.ids[0]]['settings']['settings'][0]['settingInstance']['choiceSettingValue']['value'] = 'wrong'; mutations.append(wrong)
        wrong = copy.deepcopy(self.truth); wrong['objects']['00000000-0000-4000-8000-000000000000'] = wrong['objects'].pop(self.ids[0]); mutations.append(wrong)
        for i, actual in enumerate(mutations):
            with self.subTest(mutation=i): self.assertTrue(compare_semantics(self.truth, actual))
        alternate = copy.deepcopy(self.truth)
        for obj in alternate['objects'].values(): obj['assignments'].reverse(); obj['role_scope_tag_ids'].reverse()
        self.assertEqual(compare_semantics(self.truth, alternate), [])
    def test_stateful_crud_preserves_ids_and_enforces_etag(self):
        oid = self.ids[0]
        self.assertEqual(self.request('GET', BASE + '/' + oid)['body']['id'], oid)
        self.assertEqual(self.request('PATCH', BASE + '/' + oid, body=self.desired(), if_match='0')['status'], 412)
        self.assertEqual(self.request('PATCH', BASE + '/' + oid, body=self.desired(), if_match='1')['status'], 200)
        self.assertEqual(self.request('GET', BASE + '/' + oid)['body']['name'], 'Explicit synthetic change')
        new = {'id': '00000000-0000-4000-8000-000000000000', **self.desired()}
        self.assertEqual(self.request('POST', body=new)['status'], 201)
        self.assertEqual(self.request('POST', body=new)['status'], 409)
        self.assertEqual(self.request('DELETE', BASE + '/' + new['id'], if_match='3')['status'], 204)
        self.assertEqual(set(self.service.snapshot()['current']['objects']), set(self.ids))
    def test_partial_policy_write_is_visible_and_assignment_state_is_preserved(self):
        oid = self.ids[0]; before = copy.deepcopy(self.truth['objects'][oid]['assignments'])
        result = self.request('PATCH', BASE + '/' + oid, body=self.desired(), if_match='1', fault='after-policy')
        self.assertEqual(result['status'], 503)
        resumed = ModeledService(self.root / 'service'); actual = resumed.readback(tenant_id=self.tenant)['objects'][oid]
        self.assertEqual(actual['name'], 'Explicit synthetic change'); self.assertEqual(actual['assignments'], before)
        self.assertNotEqual(actual, self.desired())
        self.assertEqual(sum(r['mutation_committed'] for r in resumed.snapshot()['requests']), 1)
    def test_lost_response_restart_readback_does_not_repeat_mutation(self):
        oid = self.ids[0]
        with self.assertRaises(AppError):
            self.request('PATCH', BASE + '/' + oid, body=self.desired(), if_match='1', fault='lost-response')
        resumed = ModeledService(self.root / 'service')
        self.assertEqual(resumed.readback(tenant_id=self.tenant)['objects'][oid], self.desired())
        self.assertEqual(sum(r['method'] == 'PATCH' for r in resumed.snapshot()['requests']), 1)
        self.assertTrue(resumed.snapshot()['requests'][0]['response_lost'])
    def test_denial_throttle_and_wrong_tenant_cannot_mutate(self):
        before = digest(self.service.snapshot()['current'])
        for fault, status in (('deny', 403), ('throttle', 429)):
            self.assertEqual(self.request('PATCH', BASE + '/' + self.ids[0], body=self.desired(), if_match='1', fault=fault)['status'], status)
        response = self.service.request('PATCH', BASE + '/' + self.ids[0], tenant_id='00000000-0000-4000-8000-000000000000', body=self.desired(), if_match='1')
        self.assertEqual(response['status'], 403); self.assertEqual(digest(self.service.snapshot()['current']), before)
    def test_readback_rejects_cross_origin_loop_and_mixed_revisions(self):
        for fault in ('cross-origin', 'loop'):
            original = self.service.request
            with patch.object(self.service, 'request', side_effect=lambda *a, **kw: original(*a, **dict(kw, fault=fault))):
                with self.subTest(fault=fault), self.assertRaises(AppError): self.service.readback(tenant_id=self.tenant)
        original = self.service.request; count = [0]
        def revised(*a, **kw):
            result = original(*a, **kw); count[0] += 1
            if count[0] == 2: result['revision'] += 1
            return result
        with patch.object(self.service, 'request', side_effect=revised), self.assertRaises(AppError): self.service.readback(tenant_id=self.tenant)
    def test_concurrent_writers_have_at_most_one_etag_winner(self):
        def writer(i):
            try: return self.request('PATCH', BASE + '/' + self.ids[0], body=self.desired(), if_match='1')['status']
            except AppError as error: return error.code
        with ThreadPoolExecutor(max_workers=4) as pool: results = list(pool.map(writer, range(4)))
        self.assertEqual(results.count(200), 1, results)
        self.assertTrue(all(r in (200, 412, 'model_writer_busy') for r in results))
        self.assertEqual(self.service.snapshot()['revision'], 2)
    def test_durable_write_failure_does_not_report_or_commit_success(self):
        before = self.service.path.read_bytes()
        with patch('intune_iac.modeled_service.write_json', side_effect=OSError('injected full disk')):
            with self.assertRaises(OSError): self.request('PATCH', BASE + '/' + self.ids[0], body=self.desired(), if_match='1')
        self.assertEqual(self.service.path.read_bytes(), before)

class ConnectedSemanticJourneyTests(unittest.TestCase):
    setUp = journey_cases.JourneyCompletionTests.setUp
    api = journey_cases.JourneyCompletionTests.api
    run_flow = journey_cases.JourneyCompletionTests.run_flow
    complete = journey_cases.JourneyCompletionTests.complete
    def test_selection_limit_rejected_before_any_write(self):
        values = [f'00000000-0000-4000-8000-{index:012d}' for index in range(9)]
        with self.assertRaises(AppError) as raised: self.api()._selected_ids(values)
        self.assertEqual(raised.exception.code, 'journey_selection_limit')
        self.assertFalse(self.output.exists())
    def test_selection_projection_preserves_inventory_and_unknown_collection(self):
        estate = generate_estate(seed=99, policy_count=3); raw = estate['capture']
        owner = estate['truth']['policies'][1]['id']
        unknown = {'kind': 'future-collection', 'owner_id': owner, 'pages': []}
        raw['collections'].append(unknown)
        selected = self.api()._selected_source(raw, estate['truth']['policies'][0]['id'])
        self.assertIn(unknown, selected['collections'])
        self.assertEqual(selected['collections'][0], raw['collections'][0])
        self.assertEqual(raw, estate['capture'])
    def test_native_source_uses_streaming_digest_and_private_copy(self):
        # Native binaries exceed the JSON input bound and the executor deliberately
        # copies the executable: equality with its original locator is incorrect.
        import hashlib
        from types import SimpleNamespace
        from intune_iac import protected
        tool = self.root / 'selected-tool'; tool.write_bytes(b'x' * (17 * 1024 * 1024))
        expected = hashlib.sha256(tool.read_bytes()).hexdigest()
        fake = SimpleNamespace(executable=self.root / 'private/tool', manifest={'executable_sha256': expected})
        with patch.object(self.api(), '_load', return_value={'tofu_executable': str(tool)}), patch.object(protected, 'NativeLocalExecutor', return_value=fake):
            self.assertIs(self.api()._native(self.session), fake)
            tool.write_bytes(b'changed')
            with self.assertRaises(AppError) as raised: self.api()._native(self.session)
            self.assertEqual(raised.exception.code, 'journey_tool_changed')
    def test_progress_feedback_precedes_expensive_recheck(self):
        events = []; observe = self.api()._observe
        def observed(*args):
            events.append('observe'); return observe(*args)
        answers = iter(['continue', 'save'])
        with patch.object(self.api(), '_observe', side_effect=observed):
            result = self.api().run_journey(self.session, self.source, self.context, self.output,
                input_fn=lambda _: next(answers), output_fn=events.append)
        working = next(i for i, event in enumerate(events) if event.startswith('Working:'))
        self.assertEqual(events[working + 1], 'observe')
        self.assertEqual(result['status'], 'suspended')
    def test_native_atmos_path_requires_explicit_repository(self):
        result = self.api().run_journey(self.session, self.source, self.context, self.output,
                                       atmos_executable=self.root / 'tool', input_fn=lambda _: 'save')
        self.assertEqual(result['error'], 'journey_atmos_repository_required')
    def test_cleanup_durability_failure_blocks_and_preserves_prior_outcome(self):
        original = self.api().sync_directory; count = [0]
        def fail_cleanup(path):
            count[0] += 1
            if count[0] == 2: raise OSError('injected cleanup fsync failure')
            return original(path)
        with patch.object(self.api(), 'sync_directory', side_effect=fail_cleanup):
            result = self.run_flow(['save'])
        self.assertEqual(result['error'], 'journey_lock_cleanup_unconfirmed')
        self.assertEqual(result['pre_cleanup_result']['status'], 'suspended')
    def test_missing_source_can_be_repaired_through_actual_prompt_route(self):
        self.run_flow(['continue', 'save'])
        replacement = self.root / 'replacement.json'; replacement.write_bytes(self.source.read_bytes()); self.source.unlink()
        result = self.run_flow(['edit input ' + str(replacement), 'save'], supplied=False)
        self.assertEqual(result['status'], 'suspended')
        self.assertEqual(load_json(self.session)['paths']['input'], str(replacement))
        self.assertEqual(result['step'], 'target')
    def test_malformed_source_suspension_never_trusts_old_completed_flags(self):
        self.run_flow(BEFORE_GENERATE + ['save'])
        self.source.write_text('{bad json')
        result = self.run_flow(['save'], supplied=False)
        self.assertEqual(result['status'], 'suspended')
        self.assertEqual(result['step'], 'observation_required')
        self.assertEqual(result['verified_completed'], [])
    def test_pending_generation_cannot_change_bound_paths_on_restart(self):
        from intune_iac.io import AppError
        original = self.api().runner.run
        def lost(*a, **kw): original(*a, **kw); raise AppError('injected_loss', 'lost after write')
        with patch.object(self.api().runner, 'run', side_effect=lost):
            self.run_flow(BEFORE_GENERATE + ['generate', 'save'])
        alternate = self.root / 'alternate.json'; alternate.write_bytes(self.source.read_bytes())
        result = self.api().run_journey(self.session, input_path=alternate, input_fn=lambda _: 'save', output_fn=self.messages.append)
        self.assertEqual(result['error'], 'journey_pending_operation_binding')
        self.assertEqual(load_json(self.session)['paths']['input'], str(self.source))
    def test_connected_saved_plan_has_complete_semantics_and_service_requests(self):
        self.assertEqual(self.complete()['status'], 'complete_simulation')
        root = Path(str(self.session) + '.journey')
        desired = load_json(root / 'synthetic-executor/work/main.tf.json')['output']['fixture']['value']['policies']
        self.assertEqual(compare_semantics(project_capture(load_json(self.source), [POLICY]), desired), [])
        service = ModeledService(root / 'modeled-service').snapshot()
        self.assertEqual([r['method'] for r in service['requests']], ['GET', 'GET'])
        result = load_json(root / 'receipts/convergence.json')['payload']
        self.assertTrue(result['service_readback']['verified'])
        self.assertEqual(result['scope'], 'synthetic_full_semantic_state_only')
    def test_model_drift_after_approval_rejects_dispatch(self):
        def mutate():
            service = ModeledService(Path(str(self.session) + '.journey') / 'modeled-service')
            body = copy.deepcopy(service.snapshot()['current']['objects'][POLICY]); body['assignments'].pop()
            service.request('PATCH', BASE + '/' + POLICY, tenant_id=load_json(self.context)['tenant_id'], body=body, if_match='1')
            return 'execute'
        result = self.run_flow(BEFORE_GENERATE + AFTER_GENERATE[:5] + [mutate, 'save'])
        self.assertNotIn('execute', result['verified_completed'])
        self.assertFalse((Path(str(self.session) + '.journey') / 'operations').exists())
    def test_model_readback_write_loss_resumes_without_second_execute(self):
        original = self.api().write_json
        def lost(path, value):
            if Path(path).name == 'modeled-readback.json': raise OSError('injected readback receipt failure')
            return original(path, value)
        with patch.object(self.api(), 'write_json', side_effect=lost): first = self.run_flow(BEFORE_GENERATE + AFTER_GENERATE[:6])
        self.assertEqual(first['step'], 'recovery_required')
        from intune_iac import protected
        with patch.object(protected, 'execute_native_operation', side_effect=AssertionError('no mutation replay')):
            second = self.run_flow(['reconcile', 'reconcile', 'continue', 'finish'], supplied=False)
        self.assertEqual(second['status'], 'complete_simulation')

if __name__ == '__main__': unittest.main()
