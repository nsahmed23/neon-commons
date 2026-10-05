"""Resolved graph facts are distinct from declarations and never expose config."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from intune_iac.graph import build_graph, query_graph
from intune_iac.io import AppError, digest

ROOT = Path(__file__).resolve().parents[1]


class GraphResolutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.capture = self.root / 'capture.json'
        self.capture.write_bytes((ROOT / 'examples/supported/input/export.json').read_bytes())
        self.write('atmos.yaml', '''stacks:
  base_path: stacks
  included_paths: [deploy/**/*]
components:
  terraform:
    base_path: components/terraform
''')
        self.write('components/terraform/intune/main.tf', '# local implementation\n')

    def write(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)

    def graph(self):
        return build_graph(self.capture, atmos_root=self.root)

    def resolved(self, graph, name, stack='deploy/dev'):
        stacks = {n['id']: n for n in graph['nodes'] if n['type'] == 'EffectiveStack'}
        return next(n for n in graph['nodes'] if n['type'] == 'ComponentInstance'
                    and n['name'] == name and n['resolution_status'] == 'resolved'
                    and stacks[n['stack_id']]['physical_stack'] == stack)

    def imported_fixture(self):
        self.write('stacks/catalog/common.yaml', '''vars: {tenant: PRIVATE-TENANT-LABEL}
components:
  terraform:
    foundation:
      metadata: {component: intune}
      vars: {client_secret: PRIVATE-IMPORT-VALUE}
    policy:
      metadata: {component: intune}
      settings:
        depends_on:
          PRIVATE-DEPENDENCY-KEY: {component: foundation}
''')
        self.write('stacks/deploy/dev.yaml', '''import: [catalog/common]
components:
  terraform:
    policy:
      vars: {client_secret: PRIVATE-OVERRIDE-VALUE}
      env: {PRIVATE-ENV-KEY: PRIVATE-ENV-VALUE}
''')

    def production_source(self):
        source = json.loads(self.capture.read_text())
        source.update(synthetic=False, exporter={'id': 'intune-iac-settings-catalog-graph', 'version': '1.0.0'}, references=[], ownership=[])
        source['collections'][0]['pages'][0]['body']['value'][0].update(creationSource='portal', templateReference=None,
            priorityMetaData=None, disableEntraGroupPolicyAssignment=False)
        for assignment in source['collections'][2]['pages'][0]['body']['value']:
            assignment.update(source='direct', sourceId=None)
        return source

    def test_known_capture_adapter_preserves_direct_assignment_annotations(self):
        source = self.production_source()
        self.capture.write_text(json.dumps(source))
        graph = self.graph()
        policy_id = source['collections'][0]['pages'][0]['body']['value'][0]['id']
        policies = query_graph(graph, 'policies', policy_id)
        self.assertEqual(policies['nodes'][0]['name'], source['collections'][0]['pages'][0]['body']['value'][0]['name'])
        result = query_graph(graph, 'assignments', policy_id)
        self.assertEqual(len(result['nodes']), 3)
        self.assertTrue(all(n['assignment_source'] == 'direct' and n['assignment_source_id'] is None for n in result['nodes']))
        self.assertTrue(all(n['capture_adapter'] == 'plugin_graph_capture/1.0.0' for n in result['nodes']))
        self.assertEqual(result['coverage'][0]['status'], 'complete')
        self.assertIn('plugin_graph_capture/1.0.0', {s.get('adapter') for s in result['sources']})
        self.assertFalse(result['execution_authorized'])
        changed = copy.deepcopy(graph)
        next(n for n in changed['nodes'] if n['type'] == 'Assignment')['assignment_source'] = 'policySets'
        changed['graph_digest'] = digest({k: v for k, v in changed.items() if k != 'graph_digest'})
        with self.assertRaises(AppError):
            query_graph(changed, 'assignments', policy_id)

    def test_known_capture_opaque_setting_and_nondirect_assignment_remain_safe(self):
        source = self.production_source()
        source['collections'][1]['pages'][0]['body']['value'][0]['id'] = 'opaque-setting-key'
        source['collections'][2]['pages'][0]['body']['value'][0].update(source='policySets', sourceId='PRIVATE-POLICYSET-ID')
        self.capture.write_text(json.dumps(source))
        graph = self.graph()
        self.assertFalse(any(n['type'] == 'SettingValue' for n in graph['nodes']))
        self.assertEqual(len([n for n in graph['nodes'] if n['type'] == 'Assignment']), 2)
        self.assertNotIn('PRIVATE-POLICYSET-ID', json.dumps(graph))
        self.assertIn('assignment_source_not_direct', {i['code'] for i in graph['issues']})
        query_graph(graph, 'policies')

    def test_known_capture_denied_assignments_remain_unknown(self):
        source = self.production_source()
        collection = source['collections'][2]
        collection.update(coverage='access_denied', reason='access_denied')
        collection['pages'][0].update(http_status=403, body={'error': {'message': 'PRIVATE-DENIAL'}})
        self.capture.write_text(json.dumps(source))
        graph = self.graph()
        policy_id = source['collections'][0]['pages'][0]['body']['value'][0]['id']
        result = query_graph(graph, 'assignments', policy_id)
        self.assertEqual(result['nodes'], [])
        self.assertEqual(result['coverage'][0]['status'], 'unknown')
        self.assertNotIn('PRIVATE-DENIAL', json.dumps(graph))

    def test_imported_effective_instances_have_configuration_implementation_and_sources(self):
        self.imported_fixture()
        graph = self.graph()
        instance = self.resolved(graph, 'policy')
        declared = [n for n in graph['nodes'] if n['type'] == 'ComponentInstance'
                    and n['name'] == 'policy' and n['resolution_status'] == 'unknown']
        self.assertEqual(len(declared), 2)
        self.assertNotIn(instance['id'], {n['id'] for n in declared})
        result = query_graph(graph, 'placement', instance['id'])
        self.assertEqual(result['stack_resolution'], 'resolved')
        self.assertEqual(result['target_verification'], 'not_established')
        kinds = {n['type'] for n in result['nodes']}
        self.assertTrue({'ComponentInstance', 'EffectiveConfiguration', 'EffectiveStack', 'ComponentDefinition'} <= kinds)
        predicates = {e['predicate'] for e in result['edges']}
        self.assertTrue({'hasEffectiveConfiguration', 'usesImplementation', 'derivedFrom'} <= predicates)
        self.assertTrue({'stacks/catalog/common.yaml', 'stacks/deploy/dev.yaml', 'atmos.yaml'} <= {s.get('path') for s in result['sources']})
        for value in ('PRIVATE-TENANT-LABEL', 'PRIVATE-IMPORT-VALUE', 'PRIVATE-OVERRIDE-VALUE',
                      'PRIVATE-ENV-KEY', 'PRIVATE-ENV-VALUE', 'PRIVATE-DEPENDENCY-KEY'):
            self.assertNotIn(value, json.dumps(graph))
        self.assertFalse(graph['execution_authorized'])

    def test_dependency_query_uses_effective_import_and_provenance(self):
        self.imported_fixture()
        graph = self.graph()
        policy = self.resolved(graph, 'policy')
        foundation = self.resolved(graph, 'foundation')
        result = query_graph(graph, 'dependencies', policy['id'])
        dependencies = [n for n in result['nodes'] if n['type'] == 'EffectiveDependency']
        self.assertEqual(len(dependencies), 1)
        self.assertEqual(dependencies[0]['resolution_status'], 'resolved')
        self.assertEqual(dependencies[0]['consumer_id'], policy['id'])
        edge = next(e for e in result['edges'] if e['predicate'] == 'dependsOn')
        self.assertEqual(edge['target'], foundation['id'])
        self.assertEqual(result['execution_order'], 'not_established')
        source = next(s for s in result['sources'] if s['id'] == dependencies[0]['origin']['artifact_id'])
        self.assertEqual(source['path'], 'stacks/catalog/common.yaml')

    def test_equal_tenant_labels_do_not_collapse_distinct_physical_stacks(self):
        for stack in ('blue', 'green'):
            self.write(f'stacks/deploy/{stack}.yaml', '''vars: {tenant: SAME-LABEL}
components:
  terraform:
    policy:
      metadata: {component: intune}
''')
        graph = self.graph()
        blue = self.resolved(graph, 'policy', 'deploy/blue')
        green = self.resolved(graph, 'policy', 'deploy/green')
        self.assertNotEqual(blue['id'], green['id'])
        self.assertNotEqual(blue['stack_id'], green['stack_id'])
        self.assertNotIn('SAME-LABEL', json.dumps(graph))
        self.assertFalse(any(e['predicate'] == 'targetsTenant' for e in graph['edges']))

    def test_dynamic_repository_never_acquires_effective_configuration(self):
        self.write('stacks/deploy/dev.yaml', '''components:
  terraform:
    policy:
      metadata: {component: intune}
      vars: {token: "{{ env.PRIVATE_TEMPLATE }}"}
''')
        graph = self.graph()
        self.assertFalse(any(n['type'] == 'EffectiveConfiguration' for n in graph['nodes']))
        self.assertEqual(graph['atmos']['resolution_status'], 'unknown')
        self.assertNotIn('PRIVATE_TEMPLATE', json.dumps(graph))
        for node in graph['nodes']:
            if node['type'] == 'ComponentInstance':
                self.assertEqual(query_graph(graph, 'placement', node['id'])['stack_resolution'], 'unknown')

    def test_config_resolution_does_not_fabricate_missing_implementation(self):
        self.write('stacks/deploy/dev.yaml', '''components:
  terraform:
    policy:
      metadata: {component: missing-module}
''')
        graph = self.graph()
        instance = self.resolved(graph, 'policy')
        result = query_graph(graph, 'placement', instance['id'])
        self.assertEqual(result['stack_resolution'], 'resolved')
        self.assertEqual(result['implementation_presence'], 'missing')
        self.assertFalse(result['execution_authorized'])

    def test_explicit_stack_selector_does_not_claim_physical_selection_is_logical_identity(self):
        self.write('stacks/deploy/shared.yaml', '''components:
  terraform:
    identity:
      metadata: {component: intune}
''')
        self.write('stacks/deploy/dev.yaml', '''components:
  terraform:
    policy:
      metadata: {component: intune}
      settings:
        depends_on:
          identity: {component: identity, stack: deploy/shared}
          contextual: {component: identity, tenant: guessed-tenant}
''')
        graph = self.graph()
        instance = self.resolved(graph, 'policy')
        self.resolved(graph, 'identity', 'deploy/shared')
        result = query_graph(graph, 'dependencies', instance['id'])
        self.assertEqual([e for e in result['edges'] if e['predicate'] == 'dependsOn'], [])
        dependencies = [n for n in result['nodes'] if n['type'] == 'EffectiveDependency']
        self.assertEqual([n['resolution_status'] for n in dependencies], ['unknown', 'unknown'])
        self.assertNotIn('guessed-tenant', json.dumps(graph))

    def test_same_physical_stack_dependency_requires_equal_known_context(self):
        for stage in ('PRIVATE-DIFFERENT-STAGE', 'null', '[PRIVATE-LIST-STAGE]'):
            with self.subTest(stage=stage):
                self.write('stacks/deploy/dev.yaml', f'''components:
  terraform:
    identity:
      metadata: {{component: intune}}
      vars: {{stage: {stage}}}
    policy:
      metadata: {{component: intune}}
      vars: {{stage: PRIVATE-CONSUMER-STAGE}}
      settings:
        depends_on:
          upstream: {{component: identity}}
''')
                graph = self.graph()
                instance = self.resolved(graph, 'policy')
                result = query_graph(graph, 'dependencies', instance['id'])
                self.assertFalse(any(e['predicate'] == 'dependsOn' for e in result['edges']))
                dependency = next(n for n in result['nodes'] if n['type'] == 'EffectiveDependency')
                self.assertEqual(dependency['resolution_status'], 'unknown')
                self.assertEqual(dependency['context_relation'], 'different' if stage == 'PRIVATE-DIFFERENT-STAGE' else 'unknown')
                self.assertNotIn('PRIVATE-', json.dumps(graph))

    def test_inherited_dependency_override_uses_winning_source_and_skips_abstract_instance(self):
        self.write('stacks/catalog/parents.yaml', '''components:
  terraform:
    base:
      metadata: {type: abstract, component: intune}
      settings:
        depends_on:
          upstream: {component: old-target}
''')
        self.write('stacks/deploy/dev.yaml', '''import: [catalog/parents]
components:
  terraform:
    identity: {metadata: {component: intune}}
    policy:
      metadata: {inherits: [base], component: intune}
      overrides:
        settings:
          depends_on:
            upstream: {component: identity}
''')
        graph = self.graph()
        instance = self.resolved(graph, 'policy')
        result = query_graph(graph, 'dependencies', instance['id'])
        dependency = next(n for n in result['nodes'] if n['type'] == 'EffectiveDependency')
        self.assertEqual(dependency['component_selector'], 'identity')
        source = next(s for s in result['sources'] if s['id'] == dependency['origin']['artifact_id'])
        self.assertEqual(source['path'], 'stacks/deploy/dev.yaml')
        self.assertFalse(any(n['type'] == 'ComponentInstance' and n['name'] == 'base'
                             and n['resolution_status'] == 'resolved' for n in graph['nodes']))

    def test_effective_graph_rejects_payload_and_inconsistent_claims_after_rehash(self):
        self.imported_fixture()
        graph = self.graph()
        instance = self.resolved(graph, 'policy')
        evidence = next(n for n in graph['nodes'] if n['type'] == 'EffectiveConfiguration' and n['component_id'] == instance['id'])
        def reject(mutator):
            changed = copy.deepcopy(graph)
            mutator(changed)
            changed['graph_digest'] = digest({k: v for k, v in changed.items() if k != 'graph_digest'})
            with self.assertRaises(AppError):
                query_graph(changed, 'placement', instance['id'])
        reject(lambda g: next(n for n in g['nodes'] if n['id'] == evidence['id']).update(effective={'vars': {'secret': 'SECRET'}}))
        reject(lambda g: next(n for n in g['nodes'] if n['id'] == evidence['id']).update(config_digest='forged'))
        reject(lambda g: next(n for n in g['nodes'] if n['id'] == evidence['id']).update(source_fingerprint='0' * 64))
        reject(lambda g: next(n for n in g['nodes'] if n['id'] == evidence['id']).update(dependency_context_digest='0' * 64))
        reject(lambda g: next(e for e in g['edges'] if e['predicate'] == 'hasEffectiveConfiguration' and e['source'] == instance['id']).update(target=instance['stack_id']))
        reject(lambda g: next(e for e in g['edges'] if e['predicate'] == 'usesImplementation' and e['source'] == evidence['id']).update(status='declared'))
        reject(lambda g: next(n for n in g['nodes'] if n['type'] == 'EffectiveDependency').update(context_relation='unknown'))
        reject(lambda g: next(n for n in g['nodes'] if n['id'] == instance['id']).update(resolution_status='unknown'))


if __name__ == '__main__':
    unittest.main()
