"""Behavior checks: scope collapse, secret disclosure and fabricated resolution are bugs."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from intune_iac.graph import build_graph, query_graph
from intune_iac.io import AppError

ROOT = Path(__file__).resolve().parents[1]
POLICY = '22222222-2222-4222-8222-222222222222'

class GraphTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = json.loads((ROOT/'examples/supported/input/export.json').read_text())

    def build(self, source=None, atmos=False, context=None):
        path = self.root/'input.json'
        path.write_text(json.dumps(self.source if source is None else source))
        cp = None
        if context is not None:
            cp = self.root/'context.json'; cp.write_text(json.dumps(context))
        return build_graph(path, cp, self.root if atmos else None)

    def nodes(self, graph, kind):
        return [n for n in graph['nodes'] if n['type'] == kind]

    def test_scopes_and_duplicate_labels_do_not_collapse_policy_identity(self):
        graph = self.build()
        self.assertEqual(len(self.nodes(graph, 'Policy')), 2)
        original = self.nodes(graph, 'Policy')[0]['id']
        other = copy.deepcopy(self.source)
        other['cloud'] = 'usgovernment'
        self.assertNotEqual(original, self.nodes(self.build(other), 'Policy')[0]['id'])
        other['tenant_id'] = '99999999-9999-4999-8999-999999999999'
        self.assertNotEqual(original, self.nodes(self.build(other), 'Policy')[0]['id'])

    def test_assignments_preserve_exclusion_and_filter_modes(self):
        result = query_graph(self.build(), 'assignments', POLICY)
        rows = result['nodes']
        self.assertEqual([r['target_type'] for r in rows], ['groupAssignmentTarget','groupAssignmentTarget','exclusionGroupAssignmentTarget'])
        self.assertEqual([r['filter_mode'] for r in rows], ['include','none','none'])
        self.assertEqual(rows[0]['filter_uuid'], '77777777-7777-4777-8777-777777777777')
        self.assertEqual(result['coverage'][0]['status'], 'complete')

    def test_denied_assignment_collection_is_unknown_not_empty_complete(self):
        source = copy.deepcopy(self.source)
        source['collections'][2]['coverage'] = 'access_denied'
        source['collections'][2]['pages'][0]['http_status'] = 403
        source['collections'][2]['pages'][0]['body'] = {'error': {'message': 'SECRET-DENIED'}}
        result = query_graph(self.build(source), 'assignments', POLICY)
        self.assertEqual(result['nodes'], [])
        self.assertEqual(result['coverage'][0]['status'], 'unknown')
        self.assertNotIn('SECRET-DENIED', json.dumps(result))

    def test_failed_page_records_cannot_borrow_successful_page_origin(self):
        source = copy.deepcopy(self.source)
        collection = source['collections'][2]
        first = copy.deepcopy(collection['pages'][0])
        first['http_status'] = 403
        first['body']['value'] = first['body']['value'][:1]
        second = copy.deepcopy(collection['pages'][0])
        second['body']['value'] = second['body']['value'][1:2]
        collection['pages'] = [first,second]
        result = query_graph(self.build(source),'assignments',POLICY)
        self.assertEqual([n['assignment_uuid'] for n in result['nodes']], ['aaaaaaaa-aaaa-4aaa-8aaa-000000000002'])
        self.assertEqual(result['nodes'][0]['origin']['pointer'], '/collections/2/pages/1/body/value/0')
        self.assertEqual(result['coverage'][0]['status'],'unknown')

    def test_denied_policy_inventory_has_unknown_coverage(self):
        source = copy.deepcopy(self.source)
        source['collections'][0]['coverage'] = 'access_denied'
        source['collections'][0]['pages'][0]['http_status'] = 403
        source['collections'][0]['pages'][0]['body'] = {'error': {}}
        result = query_graph(self.build(source),'policies')
        self.assertEqual(result['nodes'], [])
        self.assertEqual(result['coverage'][0]['status'],'unknown')

    def test_impact_walks_declared_consumers_without_claiming_order(self):
        (self.root/'dev.yaml').write_text('''components:
  terraform:
    base: {}
    consumer:
      metadata: {inherits: [base]}
''')
        graph = self.build(atmos=True)
        base = next(n for n in self.nodes(graph,'ComponentInstance') if n['name']=='base')
        result = query_graph(graph,'impact',base['id'])
        self.assertEqual({n['name'] for n in result['nodes']}, {'base','consumer'})
        self.assertEqual(result['execution_order'],'not_established')
        self.assertEqual(result['completeness'],'unknown')

    def test_yaml_merge_and_external_import_remain_unresolved(self):
        (self.root/'dev.yaml').write_text('''import: [../outside]
vars: &base {tenant: sales}
components:
  terraform:
    policy:
      vars:
        <<: *base
''')
        graph = self.build(atmos=True)
        self.assertFalse(any(e['predicate']=='imports' for e in graph['edges']))
        self.assertIn('atmos_merge_unresolved', {i['code'] for i in graph['issues']})

    def test_unknown_keys_and_secret_settings_are_not_public_review_payload(self):
        source = copy.deepcopy(self.source)
        source['TOP-SECRET-KEY'] = 'TOP-SECRET-VALUE'
        setting = source['collections'][1]['pages'][0]['body']['value'][0]
        setting['settingInstance']['choiceSettingValue']['@odata.type'] = '#microsoft.graph.deviceManagementConfigurationSecretSettingValue'
        setting['settingInstance']['choiceSettingValue']['value'] = 'SETTING-SECRET'
        rendered = json.dumps(self.build(source))
        for secret in ['TOP-SECRET-KEY','TOP-SECRET-VALUE','SETTING-SECRET']:
            self.assertNotIn(secret, rendered)

    def test_setting_explanation_has_mapping_and_byte_backed_origin(self):
        graph = self.build()
        setting = self.nodes(graph, 'SettingValue')[0]
        result = query_graph(graph, 'why-setting', setting['id'])
        self.assertEqual(result['nodes'][0]['definition_id'], 'device_vendor_msft_policy_config_privacy_letappsaccesslocation')
        self.assertEqual(result['nodes'][0]['mapping_status'], 'supported')
        self.assertEqual(result['nodes'][0]['origin']['pointer'], '/collections/1/pages/0/body/value/0')
        self.assertEqual(len(result['sources'][0]['sha256']), 64)
        result['nodes'][0]['definition_id'] = 'mutated'
        self.assertNotEqual(setting['definition_id'], 'mutated')

    def test_edited_and_unknown_graph_fields_fail_closed(self):
        graph = self.build()
        graph['nodes'][0]['raw_credentials'] = 'SECRET'
        with self.assertRaises(AppError):
            query_graph(graph, 'policies')
        # A recomputed integrity digest does not authorize arbitrary payload fields.
        from intune_iac.io import digest
        graph['graph_digest'] = digest({k:v for k,v in graph.items() if k != 'graph_digest'})
        with self.assertRaises(AppError):
            query_graph(graph, 'policies')

    def test_graph_cannot_hide_unreviewed_payload_inside_edge_metadata(self):
        from intune_iac.io import digest
        graph = self.build()
        graph['edges'][0]['qualification'] = {'access_token':'SECRET-NESTED'}
        graph['graph_digest'] = digest({k:v for k,v in graph.items() if k != 'graph_digest'})
        with self.assertRaises(AppError):
            query_graph(graph,'policies')

    def test_source_asserted_identity_and_supported_setting_value_are_explicit(self):
        graph = self.build()
        self.assertEqual(self.nodes(graph,'Tenant')[0]['identity_assurance'], 'source_asserted')
        setting = self.nodes(graph,'SettingValue')[0]
        result = query_graph(graph,'why-setting',setting['id'])
        self.assertEqual(result['nodes'][0]['normalized_instance']['choiceSettingValue']['value'],
                         'device_vendor_msft_policy_config_privacy_letappsaccesslocation_2')

    def test_fixed_queries_reject_arbitrary_query_text(self):
        with self.assertRaises(AppError):
            query_graph(self.build(), 'MATCH (n) RETURN n')
        with self.assertRaises(AppError):
            query_graph(self.build(), 'why-setting')

    def test_atmos_import_inheritance_dependency_and_instance_are_distinct(self):
        (self.root/'atmos.yaml').write_text('stacks:\n  base_path: stacks\n')
        (self.root/'stacks').mkdir()
        (self.root/'stacks/base.yaml').write_text('components:\n  terraform:\n    baseline:\n      metadata:\n        component: intune\n')
        (self.root/'stacks/dev.yaml').write_text('''import: [base]
vars:
  tenant: sales
components:
  terraform:
    baseline:
      metadata: {component: intune}
    policy:
      metadata: {component: intune, inherits: [baseline]}
      settings:
        depends_on:
          upstream: {component: baseline}
''')
        graph = self.build(atmos=True)
        predicates = {e['predicate'] for e in graph['edges']}
        self.assertTrue({'imports','inheritsConfigurationFrom','declaresDependencyOn','usesImplementation'} <= predicates)
        self.assertEqual(len([n for n in self.nodes(graph,'ComponentDefinition') if n['status'] == 'declared']), 1)
        self.assertEqual(len([n for n in self.nodes(graph,'ComponentInstance') if n['status'] == 'declared']), 3)
        self.assertFalse(any(e['predicate'] == 'targetsTenant' for e in graph['edges']))
        deps = query_graph(graph,'dependencies')
        self.assertEqual(len([e for e in deps['edges'] if e['predicate'] == 'declaresDependencyOn']), 1)
        self.assertEqual(deps['execution_order'], 'not_established')

    def test_atmos_component_placement_shows_implementation_without_resolved_stack(self):
        (self.root/'dev.yaml').write_text('components: {terraform: {policy: {metadata: {component: intune}}}}')
        graph = self.build(atmos=True)
        component = self.nodes(graph,'ComponentInstance')[0]
        result = query_graph(graph,'placement',component['id'])
        self.assertEqual({n['type'] for n in result['nodes']}, {'ComponentInstance','ComponentDefinition','StackDeclaration'})
        self.assertEqual(result['stack_resolution'], 'unknown')

    def test_dynamic_dependency_stack_does_not_become_same_manifest_edge(self):
        (self.root/'dev.yaml').write_text('''components:
  terraform:
    baseline: {}
    policy:
      settings:
        depends_on:
          upstream: {component: baseline, stack: !env SECRET_STACK}
''')
        graph = self.build(atmos=True)
        result = query_graph(graph,'dependencies')
        self.assertFalse(any(e['predicate'] in ('declaresDependencyOn','dependsOn') for e in result['edges']))
        self.assertTrue(any(n['type'] == 'DependencyDeclaration' for n in result['nodes']))
        self.assertIn('atmos_dependency_unresolved', {i['code'] for i in graph['issues']})

    def test_atmos_cycles_and_dynamic_tags_remain_unknown_without_execution(self):
        (self.root/'atmos.yaml').write_text('stacks: {base_path: stacks}\n')
        (self.root/'stacks').mkdir()
        (self.root/'stacks/a.yaml').write_text('''import: [b]
components:
  terraform:
    policy:
      metadata: {component: intune, inherits: [policy]}
      vars:
        token: !unknown SECRET-TAG-PAYLOAD
        tenant_id: "{{ env.SECRET_TEMPLATE }}"
      env: {CLIENT_SECRET: SECRET-ENV}
''')
        (self.root/'stacks/b.yaml').write_text('import: [a]\n')
        graph = self.build(atmos=True)
        codes = {i['code'] for i in graph['issues']}
        self.assertTrue({'atmos_import_cycle','atmos_inheritance_cycle','atmos_dynamic_value'} <= codes)
        rendered = json.dumps(graph)
        for secret in ['SECRET-TAG-PAYLOAD','SECRET_TEMPLATE','SECRET-ENV','CLIENT_SECRET']:
            self.assertNotIn(secret, rendered)
        self.assertEqual(graph['atmos']['resolution_status'], 'unknown')

    def test_placement_is_intent_and_context_cannot_verify_identity(self):
        context = json.loads((ROOT/'examples/context.json').read_text())
        graph = self.build(context=context)
        result = query_graph(graph,'placement',POLICY)
        self.assertEqual(result['nodes'][0]['status'], 'declared')
        self.assertEqual(result['target_verification'], 'not_established')
        self.assertFalse(any(e['predicate']=='targetsTenant' for e in graph['edges']))

if __name__ == '__main__':
    unittest.main()
