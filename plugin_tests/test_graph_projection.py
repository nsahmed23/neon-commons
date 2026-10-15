"""The graph projection: one selected object and one hop, typed, directed and revisioned (requirement 17 UX-VIS).

The fixture is the existing synthetic estate (seed 510): its first policy has two included groups, one excluded group,
one filter, two scope tags and one setting, all read through the real store and the engine's relationships result. A
repository source is added the way the Relationships view receives it (the selected repository's scope). Expected
identifiers come from the estate's own truth file, never from the code under test. Temporary directories only.
"""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from intune_iac.io import AppError

REPOSITORY = {'evidence_class': 'recorded_repository_intent',
              'scope': {'repository': 'github.com/example/intune', 'stack': 'dev', 'component': 'intune-reference'}}


def synthetic_policy(root):
    """The relationships result of the first synthetic policy, plus the truth the expectations come from."""
    from intune_iac.modeled_service import ModeledService
    from intune_iac.synthetic import generate_estate
    from intune_iac.workbench import _facet
    from intune_iac.workbench_store import WorkbenchStore
    estate = generate_estate(seed=510, policy_count=3)
    ids = [policy['id'] for policy in estate['truth']['policies']]
    service = ModeledService.create(Path(root) / 'service', estate['capture'], ids)
    store = WorkbenchStore.create(Path(root) / 'store', estate['truth']['tenant_id'])
    store.collect(service)
    value = _facet(store, ids[0], 'relationships')
    value = dict(value, selected_repository=copy.deepcopy(REPOSITORY))
    return store, value, estate['truth'], estate['truth']['policies'][0]


class ProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.store, cls.value, cls.truth, cls.policy = synthetic_policy(cls.temp.name)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def project(self, value=None, **kw):
        from intune_iac.graph_projection import project
        return project(self.value if value is None else value, **kw)

    def nodes(self, graph, kind):
        return [node for node in graph['nodes'] if node['kind'] == kind]

    def test_the_nodes_carry_the_read_models_identifiers_and_kinds(self):
        graph = self.project()
        included = [row['group_id'] for row in self.policy['assignments'] if row['type'] == 'groupAssignmentTarget']
        excluded = [row['group_id'] for row in self.policy['assignments'] if row['type'] == 'exclusionGroupAssignmentTarget']
        self.assertEqual(sorted(node['id'] for node in self.nodes(graph, 'group')), sorted(included + excluded))
        self.assertEqual({node['id'] for node in self.nodes(graph, 'filter')},
                         {row['filter_id'] for row in self.policy['assignments'] if row.get('filter_id')})
        self.assertEqual(sorted(node['id'] for node in self.nodes(graph, 'scope_tag')), sorted(self.policy['role_scope_tag_ids']))
        self.assertEqual(len(self.nodes(graph, 'repository')), 1)
        center = self.nodes(graph, 'policy')
        self.assertEqual([node['id'] for node in center], [self.policy['id']])
        self.assertEqual(graph['center'], center[0]['ref'])
        self.assertEqual(center[0]['name'], self.value['name'])

    def test_an_unresolved_group_keeps_its_identifier_and_never_gets_a_name(self):
        graph = self.project()
        groups = self.nodes(graph, 'group')
        self.assertEqual(len(groups), 3)
        for node in groups:
            self.assertIsNone(node['name'], node)
            self.assertIn(node['id'], {row['group_id'] for row in self.policy['assignments']})
        # A name the read model resolved for one group is carried for that group only.
        named = self.project(names={groups[0]['id']: 'Pilot devices'})
        by_id = {node['id']: node for node in self.nodes(named, 'group')}
        self.assertEqual(by_id[groups[0]['id']]['name'], 'Pilot devices')
        self.assertTrue(all(node['name'] is None for key, node in by_id.items() if key != groups[0]['id']))
        # A name for an identifier the graph does not hold is ignored.
        stray = self.project(names={'ffffffff-0000-4000-8000-000000000000': 'Nobody'})
        self.assertTrue(all(node['name'] is None for node in self.nodes(stray, 'group')))

    def test_every_edge_is_typed_directed_and_carries_its_provenance_and_freshness(self):
        graph = self.project(freshness='fresh')
        self.assertEqual(len(graph['edges']), 8)
        for edge in graph['edges']:
            self.assertEqual(edge['source'], graph['center'])
            self.assertIn(edge['target'], {node['ref'] for node in graph['nodes']})
            self.assertEqual(edge['freshness'], 'fresh')
            self.assertIsInstance(edge['provenance'], str)
        kinds = sorted(edge['type'] for edge in graph['edges'])
        self.assertEqual(kinds, sorted(['assignment', 'assignment', 'exclusion', 'filter', 'scope_tag', 'scope_tag',
                                        'setting', 'repository']))
        repository = next(edge for edge in graph['edges'] if edge['type'] == 'repository')
        self.assertEqual(repository['provenance'], REPOSITORY['evidence_class'])
        observed = next(edge for edge in graph['edges'] if edge['type'] == 'exclusion')
        self.assertEqual(observed['provenance'], 'observed')
        # Freshness the read model did not state is unknown, never fresh.
        self.assertTrue(all(edge['freshness'] == 'unknown' for edge in self.project()['edges']))

    def test_layers_follow_the_relation_groups_and_each_edge_names_its_layer(self):
        from intune_iac.workbench_screens import RELATION_GROUPS
        graph = self.project()
        self.assertEqual(graph['layers'], [heading for heading, _ in RELATION_GROUPS])
        order = [graph['layers'].index(edge['layer']) for edge in graph['edges']]
        self.assertEqual(order, sorted(order))
        layer_of = {edge['type']: edge['layer'] for edge in graph['edges']}
        self.assertEqual(layer_of['exclusion'], 'TARGETING')
        self.assertEqual(layer_of['scope_tag'], 'CONFIGURATION')
        self.assertEqual(layer_of['repository'], 'SOURCE AND LINEAGE')

    def test_edges_inside_a_layer_are_sorted_by_identifier(self):
        graph = self.project()
        for heading in graph['layers']:
            ids = [edge['target'].split(':', 1)[1] for edge in graph['edges'] if edge['layer'] == heading]
            self.assertEqual(ids, sorted(ids), heading)

    def test_a_relation_the_groups_do_not_name_is_kept_in_its_own_layer(self):
        value = dict(self.value, relationships=list(self.value['relationships']) + [
            {'relation': 'related_operation', 'target_id': 'op-1', 'details': {}, 'assertion_class': 'observed'}])
        graph = self.project(value)
        self.assertEqual(graph['layers'][-1], 'OTHER RELATIONSHIPS')
        self.assertEqual([edge['type'] for edge in graph['edges'] if edge['layer'] == 'OTHER RELATIONSHIPS'],
                         ['related_operation'])

    def test_the_revision_is_the_digest_of_the_canonical_form_and_follows_every_change(self):
        graph = self.project()
        body = {key: value for key, value in graph.items() if key != 'revision'}
        wanted = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                                           allow_nan=False).encode('utf-8')).hexdigest()
        self.assertEqual(graph['revision'], wanted)
        # The same facts in another input order are the same graph.
        shuffled = dict(self.value, relationships=list(reversed(self.value['relationships'])))
        self.assertEqual(self.project(shuffled)['revision'], graph['revision'])
        self.assertEqual(self.project()['revision'], graph['revision'])
        # A state, a name, a freshness word or an edge changes it.
        changed = {self.project(states={self.policy['id']: 'running'})['revision'],
                   self.project(names={self.nodes(graph, 'group')[0]['id']: 'Pilot'})['revision'],
                   self.project(freshness='stale')['revision'],
                   self.project(dict(self.value, relationships=self.value['relationships'][1:]))['revision']}
        self.assertEqual(len(changed), 4)
        self.assertNotIn(graph['revision'], changed)

    def test_states_use_the_workbench_words_and_anything_else_is_unknown(self):
        from intune_iac.graph_projection import STATES
        self.assertEqual(STATES, ('queued', 'running', 'waiting', 'blocked', 'failed', 'cancelled', 'unknown', 'verified'))
        policy = self.policy['id']
        for word in STATES:
            graph = self.project(states={policy: word})
            self.assertEqual(self.nodes(graph, 'policy')[0]['state'], word)
        graph = self.project(states={policy: 'approved and shipped'})
        self.assertEqual(self.nodes(graph, 'policy')[0]['state'], 'unknown')
        self.assertTrue(all(node['state'] == 'unknown' for node in graph['nodes']))

    def test_nothing_is_inferred_from_a_string(self):
        # An assignment that names no group is not a group, whatever its text says; a target that looks like another
        # kind's reference stays what its relation says it is.
        value = dict(self.value, relationships=[
            {'relation': 'assignment', 'target_id': 'allLicensedUsersAssignmentTarget',
             'details': {'type': 'allLicensedUsersAssignmentTarget', 'filter_type': 'none'}, 'assertion_class': 'observed'},
            {'relation': 'filter', 'target_id': 'group:looks-like-a-group', 'details': {}, 'assertion_class': 'observed'},
            {'relation': 'assignment', 'target_id': 'All Users', 'details': {}, 'assertion_class': 'observed'}])
        graph = self.project(value)
        self.assertEqual(self.nodes(graph, 'group'), [])
        self.assertEqual([node['id'] for node in self.nodes(graph, 'filter')], ['group:looks-like-a-group'])
        self.assertEqual(sorted(node['id'] for node in self.nodes(graph, 'target')), ['All Users', 'allLicensedUsersAssignmentTarget'])
        self.assertTrue(all(node['name'] is None for node in graph['nodes'] if node['kind'] != 'policy'))

    def test_an_edge_without_a_target_is_counted_not_invented(self):
        value = dict(self.value, relationships=list(self.value['relationships']) + [
            {'relation': 'assignment', 'details': {}, 'assertion_class': 'observed'}, 'not an edge'])
        graph = self.project(value)
        self.assertEqual(len(graph['edges']), 8)
        self.assertEqual(graph['excluded'], 2)

    def test_the_projection_is_pure(self):
        before = json.dumps(self.value, sort_keys=True, default=str)
        self.project()
        self.assertEqual(json.dumps(self.value, sort_keys=True, default=str), before)

    def test_a_result_that_names_no_object_is_refused(self):
        from intune_iac.graph_projection import project
        for bad in (None, [], {'relationships': []}, {'object_id': 3, 'relationships': []}):
            with self.assertRaises(AppError) as raised:
                project(bad)
            self.assertEqual(raised.exception.code, 'graph_projection_invalid')
        # No edges is a valid, empty neighbourhood.
        empty = project({'object_id': self.policy['id'], 'relationships': []})
        self.assertEqual(empty['edges'], [])
        self.assertEqual([node['kind'] for node in empty['nodes']], ['policy'])


if __name__ == '__main__':
    unittest.main()
