"""Regressions from independent v0.2.0 relationship/provenance audit."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from intune_iac.atmos import inspect_atmos
from intune_iac.graph import build_graph, query_graph
from intune_iac.io import AppError, digest
from intune_iac.repository import resolve_component

ROOT = Path(__file__).resolve().parents[1]


class AtmosAuditTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = json.loads((ROOT/'examples/supported/input/export.json').read_text())

    def put(self, name, content):
        path = self.root/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def graph(self):
        return build_graph(self.put('source.json', json.dumps(self.source)), atmos_root=self.root)

    def test_static_import_uses_same_configured_base_path_as_effective_resolution(self):
        self.put('atmos.yaml', 'base_path: project\nstacks: {base_path: stacks}\n')
        self.put('project/stacks/base.yaml', 'vars: {actual: correct}\n')
        self.put('stacks/base.yaml', 'vars: {actual: wrong}\n')
        self.put('project/stacks/dev.yaml', 'import: [base]\ncomponents: {terraform: {app: {}}}\n')
        graph = inspect_atmos(self.root)
        nodes = {n['id']:n for n in graph['nodes']}
        paths = {s['id']:s['path'] for s in graph['sources']}
        edges = [e for e in graph['edges'] if e['predicate'] == 'imports']
        self.assertEqual(len(edges), 1)
        self.assertEqual(paths[nodes[edges[0]['target']]['source_artifact_id']], 'project/stacks/base.yaml')
        self.assertEqual(resolve_component(self.root, 'dev', 'app')['effective']['vars'], {'actual':'correct'})

    def test_unknown_import_options_do_not_receive_resolved_static_target(self):
        self.put('atmos.yaml', 'stacks: {base_path: stacks}\n')
        self.put('stacks/base.yaml', 'vars: {actual: base}\n')
        self.put('stacks/dev.yaml', 'import: [{path: base, unsupported: true}]\n')
        graph = inspect_atmos(self.root)
        self.assertFalse(any(e['predicate'] == 'imports' for e in graph['edges']))
        self.assertTrue(any(i['code'] == 'atmos_import_evaluation_unqualified' for i in graph['issues']))

    def test_dynamic_configured_import_base_does_not_fall_back_to_default(self):
        self.put('atmos.yaml', 'base_path: !env PROJECT_ROOT\n')
        self.put('stacks/base.yaml', 'vars: {actual: wrong}\n')
        self.put('stacks/dev.yaml', 'import: [base]\n')
        graph = inspect_atmos(self.root)
        self.assertFalse(any(e['predicate'] == 'imports' for e in graph['edges']))

    def test_unresolved_dependency_declaration_is_visible_in_fixed_query(self):
        self.put('dev.yaml', 'components:\n  terraform:\n    app:\n      settings:\n        depends_on:\n          dependency: {component: target, stack: production}\n')
        result = query_graph(self.graph(), 'dependencies')
        declarations = [n for n in result['nodes'] if n['type'] == 'DependencyDeclaration']
        self.assertEqual(len(declarations), 1)
        self.assertEqual(declarations[0]['resolution_status'], 'unknown')
        self.assertTrue(any(i['code'] == 'atmos_dependency_unresolved' for i in result['issues']))
        self.assertTrue(result['sources'])

    def test_unknown_dependency_selector_fields_never_resolve_same_manifest_target(self):
        self.put('dev.yaml', 'components:\n  terraform:\n    target: {}\n    app:\n      settings:\n        depends_on:\n          dependency: {component: target, workspace: production}\n')
        result = query_graph(self.graph(), 'dependencies')
        self.assertFalse(any(e['predicate'] in ('declaresDependencyOn','dependsOn') for e in result['edges']))
        self.assertEqual(len([n for n in result['nodes'] if n['type'] == 'DependencyDeclaration']), 1)
        self.assertTrue(any(i['code'] == 'atmos_dependency_unresolved' for i in result['issues']))

    def test_nonstring_keys_cannot_disappear_before_import_or_dependency_validation(self):
        self.put('atmos.yaml', 'stacks: {base_path: stacks}\n')
        self.put('stacks/base.yaml', 'vars: {actual: base}\n')
        for extra_key in ('1', 'true', '? [a, b]'):
            with self.subTest(extra_key=extra_key):
                self.put('stacks/dev.yaml', 'import: [{path: base, '+extra_key+': unsupported}]\ncomponents:\n  terraform:\n    target: {}\n    app:\n      settings:\n        depends_on:\n          dependency: {component: target, '+extra_key+': unsupported}\n')
                graph = self.graph()
                self.assertFalse(any(e['predicate'] in ('imports','resolvesToManifest','declaresDependencyOn','dependsOn') for e in graph['edges']))
                self.assertEqual(len([n for n in graph['nodes'] if n['type'] == 'DependencyDeclaration']), 1)
                codes = {i['code'] for i in graph['issues']}
                self.assertIn('atmos_import_evaluation_unqualified', codes)
                self.assertIn('atmos_dependency_unresolved', codes)

    def test_blocked_discovered_stack_prevents_overall_resolved_claim(self):
        self.put('atmos.yaml', 'stacks: {base_path: stacks}\n')
        self.put('stacks/dev.yaml', 'components: {terraform: {app: {}}}\n')
        self.put('stacks/broken.yaml', 'import: [missing]\ncomponents: {terraform: {critical: {}}}\n')
        graph = self.graph()
        self.assertEqual(graph['atmos']['resolution_status'], 'partial')
        self.assertTrue(any(i['code'] == 'atmos_effective_resolution_blocked' for i in graph['issues']))
        query_graph(graph, 'dependencies')

    def test_policy_inventory_count_mismatch_is_unknown_for_both_source_adapters(self):
        for production in (False, True):
            with self.subTest(production=production):
                source = copy.deepcopy(self.source)
                if production:
                    source['synthetic'] = False
                    source['exporter'] = {'id':'intune-iac-settings-catalog-graph','version':'1.0.0'}
                    source['references'] = []; source['ownership'] = []
                source['collections'][0]['pages'][0]['body']['@odata.count'] = 1000
                graph = build_graph(self.put('source.json', json.dumps(source)))
                tenant = next(n['id'] for n in graph['nodes'] if n['type'] == 'Tenant')
                coverage = next(c for c in graph['coverage'] if c['subject_id'] == tenant)
                self.assertEqual(coverage['status'], 'unknown')

    def test_duplicate_case_normalized_policy_id_never_claims_complete_inventory(self):
        source = copy.deepcopy(self.source)
        values = source['collections'][0]['pages'][0]['body']['value']
        values.append(copy.deepcopy(values[0])); values[-1]['id'] = values[0]['id'].upper()
        graph = build_graph(self.put('source.json', json.dumps(source)))
        tenant = next(n['id'] for n in graph['nodes'] if n['type'] == 'Tenant')
        self.assertEqual(next(c for c in graph['coverage'] if c['subject_id'] == tenant)['status'], 'unknown')

    def test_assignment_query_preserves_duplicate_identity_blocker_and_unknown_coverage(self):
        source = copy.deepcopy(self.source)
        collection = source['collections'][2]
        assignments = collection['pages'][0]['body']['value']
        duplicate = copy.deepcopy(assignments[0])
        duplicate['id'] = duplicate['id'].upper()
        assignments.append(duplicate)
        graph = build_graph(self.put('source.json', json.dumps(source)))
        result = query_graph(graph, 'assignments', collection['owner_id'])
        self.assertTrue(result['coverage'])
        self.assertTrue(all(c['status'] == 'unknown' for c in result['coverage']))
        self.assertIn('duplicate_assignment_identity', {i['code'] for i in result.get('issues', [])})
        self.assertFalse(any(n['assignment_uuid'].lower() == duplicate['id'].lower() for n in result['nodes']))
        self.assertTrue(result['sources'])

    def test_opaque_production_assignment_key_is_preserved(self):
        source = copy.deepcopy(self.source)
        source['synthetic'] = False
        source['exporter'] = {'id':'intune-iac-settings-catalog-graph','version':'1.0.0'}
        source['references'] = []; source['ownership'] = []
        assignments = source['collections'][2]['pages'][0]['body']['value']
        for item in assignments:
            item.update(source='direct', sourceId=None)
        assignments[0]['id'] = 'policy-group-opaque-assignment-key'
        graph = build_graph(self.put('source.json', json.dumps(source)))
        result = query_graph(graph, 'assignments')
        self.assertIn(assignments[0]['id'], [n['assignment_uuid'] for n in result['nodes']])

    def test_production_policy_pagination_honors_full_returned_links_and_boundaries(self):
        source = copy.deepcopy(self.source)
        source['synthetic'] = False
        source['exporter'] = {'id':'intune-iac-settings-catalog-graph','version':'1.0.0'}
        source['references'] = []; source['ownership'] = []
        collection = source['collections'][0]
        initial = copy.deepcopy(collection['pages'][0])
        continuation = copy.deepcopy(initial)
        continuation['request_url'] += '?$skip=0&$skiptoken=A%2BB&$top=200'
        initial['body'] = {'value':[], '@odata.count':2, '@odata.nextLink':continuation['request_url']}
        collection['pages'] = [initial, continuation]
        for mutation in ('none', 'root_query', 'lost_query', 'wrong_origin', 'wrong_path', 'count', 'duplicate'):
            with self.subTest(mutation=mutation):
                candidate = copy.deepcopy(source)
                pages = candidate['collections'][0]['pages']
                if mutation == 'root_query': pages[0]['request_url'] += '?$skip=0'
                elif mutation == 'lost_query': pages[1]['request_url'] = pages[1]['request_url'].split('&$skiptoken')[0]
                elif mutation in ('wrong_origin','wrong_path'):
                    pages[1]['request_url'] = pages[1]['request_url'].replace('graph.microsoft.com', 'wrong.example') if mutation == 'wrong_origin' else pages[1]['request_url'].replace('configurationPolicies', 'wrongCollection')
                    pages[0]['body']['@odata.nextLink'] = pages[1]['request_url']
                elif mutation == 'count': pages[0]['body']['@odata.count'] = 1000
                elif mutation == 'duplicate':
                    pages[1]['body']['value'][1]['id'] = pages[1]['body']['value'][0]['id'].upper()
                graph = build_graph(self.put('source.json', json.dumps(candidate)))
                tenant = next(n['id'] for n in graph['nodes'] if n['type'] == 'Tenant')
                coverage = next(c for c in query_graph(graph, 'policies')['coverage'] if c['subject_id'] == tenant)
                self.assertEqual(coverage['status'], 'complete' if mutation == 'none' else 'unknown')
        # The original synthetic adapter deliberately uses a narrower query contract.
        source['synthetic'] = True
        source['exporter'] = {'id':'appendix-b-graph-snapshot','version':'1.0.0'}
        graph = build_graph(self.put('source.json', json.dumps(source)))
        tenant = next(n['id'] for n in graph['nodes'] if n['type'] == 'Tenant')
        self.assertEqual(next(c for c in graph['coverage'] if c['subject_id'] == tenant)['status'], 'unknown')

    def test_recomputed_digest_does_not_accept_contradictory_assignment_relationships(self):
        original = build_graph(self.put('source.json', json.dumps(self.source)))
        for mutation in ('wrong_endpoint_type', 'inclusion_reversed', 'wrong_group_uuid', 'wrong_filter_mode'):
            with self.subTest(mutation=mutation):
                graph = copy.deepcopy(original)
                assignment = next(n for n in graph['nodes'] if n['type'] == 'Assignment' and n['filter_mode'] == 'include')
                relation = next(e for e in graph['edges'] if e['source'] == assignment['id'] and e['predicate'] == 'includesGroup')
                if mutation == 'wrong_endpoint_type':
                    relation['target'] = next(n['id'] for n in graph['nodes'] if n['type'] == 'Tenant')
                elif mutation == 'inclusion_reversed':
                    relation['predicate'] = 'excludesGroup'
                elif mutation == 'wrong_group_uuid':
                    assignment['group_uuid'] = '99999999-9999-4999-8999-999999999999'
                else:
                    assignment['filter_mode'] = 'exclude'
                graph['graph_digest'] = digest({k:v for k,v in graph.items() if k != 'graph_digest'})
                with self.assertRaises(AppError):
                    query_graph(graph, 'assignments')

    def test_coherent_filtered_exclusion_is_outside_the_bounded_assignment_contract(self):
        graph = build_graph(self.put('source.json', json.dumps(self.source)))
        assignment = next(n for n in graph['nodes'] if n['type'] == 'Assignment' and n['filter_mode'] == 'include')
        assignment['target_type'] = 'exclusionGroupAssignmentTarget'
        relation = next(e for e in graph['edges'] if e['source'] == assignment['id'] and e['predicate'] == 'includesGroup')
        relation['predicate'] = 'excludesGroup'
        graph['graph_digest'] = digest({k:v for k,v in graph.items() if k != 'graph_digest'})
        with self.assertRaises(AppError):
            query_graph(graph, 'assignments')


if __name__ == '__main__':
    unittest.main()
