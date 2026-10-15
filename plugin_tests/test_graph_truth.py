"""The graph says what is known (PKG-UXVIS-1b, part A): five additions to the projection from the frame review of journey 29.

State applies only where an operation can exist; the policy carries the read model's own operation word (none
recorded, expired, prepared and the rest) beside the existing eight-word state; a filter belongs to the assignment
that applies it, with its type; the relationships the read model lists and the sources the selection adds are counted
apart; and every node carries its kind word and a label that never prints like another's when cut. The fields are
additive: the existing field values are the ones the terminal map reads and do not change.
Cases: frame 21 (a policy with an expired operation and a repository), the seed-510 fixture (a filter on one
assignment), two settings with a common prefix, two sources under one folder. Temporary directories only.
"""
import tempfile
import unittest

from plugin_tests.test_graph_projection import REPOSITORY, synthetic_policy

LONG = 'device_vendor_msft_policy_config_'


def setting(name):
    return {'relation': 'setting', 'target_id': LONG + name, 'details': {}, 'assertion_class': 'observed'}


class Truth(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.store, cls.value, cls.truth, cls.policy = synthetic_policy(cls.temp.name)
        cls.object_id = cls.policy['id']

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def project(self, value=None, **kw):
        from intune_iac.graph_projection import project
        return project(self.value if value is None else value, **kw)

    def node(self, graph, kind, identifier=None):
        found = [node for node in graph['nodes'] if node['kind'] == kind and identifier in (None, node['id'])]
        self.assertEqual(len(found), 1, (kind, identifier, found))
        return found[0]


class StateAppliesTests(Truth):
    def test_an_operation_state_applies_to_a_policy_and_to_nothing_else(self):
        graph = self.project()
        for node in graph['nodes']:
            self.assertIs(node['state_applies'], node['kind'] == 'policy', node)
        self.assertEqual({node['kind'] for node in graph['nodes'] if not node['state_applies']},
                         {'group', 'filter', 'scope_tag', 'setting', 'repository'})
        # A generated source is a source, and no operation exists for it either.
        value = dict(self.value, relationships=self.value['relationships'] + [
            {'relation': 'generated_from', 'target_id': 'stacks/dev/privacy.tf', 'details': {}, 'assertion_class': 'historical_local_adoption'}])
        generated = self.node(self.project(value), 'source')
        self.assertFalse(generated['state_applies'])
        self.assertIsNone(generated['operation'])

    def test_every_node_names_its_kind_in_words(self):
        graph = self.project()
        words = {node['kind']: node['kind_word'] for node in graph['nodes']}
        self.assertEqual(words, {'policy': 'policy', 'group': 'group', 'filter': 'filter', 'scope_tag': 'scope tag',
                                 'setting': 'setting', 'repository': 'repository'})

    def test_the_existing_fields_keep_their_values(self):
        graph = self.project(states={self.object_id: 'expired'}, freshness='fresh')
        policy = self.node(graph, 'policy')
        self.assertEqual((policy['ref'], policy['id'], policy['kind'], policy['name'], policy['state']),
                         ('policy:' + self.object_id, self.object_id, 'policy', self.value['name'], 'unknown'))
        for node in graph['nodes']:
            self.assertIn(node['state'], ('queued', 'running', 'waiting', 'blocked', 'failed', 'cancelled', 'unknown', 'verified'))
        self.assertEqual(sorted(graph['layers']), sorted(['TARGETING', 'CONFIGURATION', 'SOURCE AND LINEAGE']))
        self.assertEqual({edge['type'] for edge in graph['edges']},
                         {'assignment', 'exclusion', 'filter', 'scope_tag', 'setting', 'repository'})
        for edge in graph['edges']:
            self.assertEqual(edge['freshness'], 'fresh')


class OperationWordTests(Truth):
    def test_no_recorded_operation_reads_none_recorded_never_unknown(self):
        graph = self.project()
        policy = self.node(graph, 'policy')
        self.assertEqual(policy['operation'], 'none recorded')
        self.assertEqual(policy['state'], 'unknown', 'the eight-word state is unchanged beside it')

    def test_the_recorded_word_is_carried_exactly_including_expired_and_prepared(self):
        for word, state in (('expired', 'unknown'), ('prepared', 'unknown'), ('running', 'running'), ('blocked', 'blocked'),
                            ('succeeded_verified', 'verified'), ('outcome_unknown', 'unknown'), ('dispatched', 'unknown')):
            policy = self.node(self.project(states={self.object_id: word}), 'policy')
            self.assertEqual((policy['operation'], policy['state']), (word, state), word)

    def test_an_unreadable_word_is_unknown_and_is_not_none_recorded(self):
        for bad in ('', 7, ['expired'], {}):
            policy = self.node(self.project(states={self.object_id: bad}), 'policy')
            self.assertEqual(policy['operation'], 'unknown', bad)

    def test_frame_21_a_policy_with_an_expired_operation_and_a_repository(self):
        graph = self.project(states={self.object_id: 'expired'}, freshness='fresh')
        policy, repository = self.node(graph, 'policy'), self.node(graph, 'repository')
        self.assertEqual(policy['operation'], 'expired')
        self.assertTrue(policy['state_applies'])
        self.assertFalse(repository['state_applies'])
        self.assertIsNone(repository['operation'])
        # A state given for a node that has no operation is not carried as one.
        stray = self.project(states={self.object_id: 'expired', repository['id']: 'running'})
        self.assertIsNone(self.node(stray, 'repository')['operation'])

    def test_a_changed_operation_word_is_a_new_revision(self):
        words = ('prepared', 'expired', 'unknown')
        revisions = {self.project(states={self.object_id: word})['revision'] for word in words} | {self.project()['revision']}
        self.assertEqual(len(revisions), 4)


class FilterTests(Truth):
    def test_a_filter_belongs_to_the_assignment_that_applies_it(self):
        graph = self.project()
        by_target = {edge['target']: edge for edge in graph['edges'] if edge['type'] in ('assignment', 'exclusion')}
        filtered = [edge for edge in by_target.values() if edge['filter']]
        self.assertEqual(len(filtered), 1)
        edge = filtered[0]
        filter_id = next(node['id'] for node in graph['nodes'] if node['kind'] == 'filter')
        self.assertEqual(edge['filter'], {'ref': 'filter:' + filter_id, 'id': filter_id, 'type': 'include'})
        self.assertEqual(edge['type'], 'assignment')
        self.assertTrue(all(other['filter'] is None for other in by_target.values() if other is not edge))
        # The filter node and its own edge stay, and say which assignment they apply to.
        self.assertEqual(self.node(graph, 'filter')['id'], filter_id)
        own = next(row for row in graph['edges'] if row['type'] == 'filter')
        self.assertEqual(own['applies_to'], edge['target'])
        self.assertIsNone(edge['applies_to'])

    def test_the_type_is_the_read_models_include_or_exclude(self):
        group, flt = 'aaaaaaaa-0000-4000-8000-000000000001', 'bbbbbbbb-0000-4000-8000-000000000002'
        for kind, relation in (('include', 'assignment'), ('exclude', 'exclusion')):
            edge = {'relation': relation, 'target_id': group, 'assertion_class': 'observed',
                    'details': {'group_id': group, 'filter_id': flt, 'filter_type': kind}}
            graph = self.project(dict(self.value, relationships=[edge], selected_repository=None))
            self.assertEqual(graph['edges'][0]['filter'], {'ref': 'filter:' + flt, 'id': flt, 'type': kind})

    def test_no_filter_is_claimed_without_the_read_models_word(self):
        group, flt = 'aaaaaaaa-0000-4000-8000-000000000001', 'bbbbbbbb-0000-4000-8000-000000000002'
        for details in ({'group_id': group, 'filter_type': 'none'},
                        {'group_id': group, 'filter_type': 'none', 'filter_id': flt},
                        {'group_id': group, 'filter_type': 'include'},
                        {'group_id': group, 'filter_type': 'maybe', 'filter_id': flt},
                        {'group_id': group, 'filter_id': flt},
                        {'group_id': group, 'filter_type': 'include', 'filter_id': 7}):
            edge = {'relation': 'assignment', 'target_id': group, 'assertion_class': 'observed', 'details': details}
            graph = self.project(dict(self.value, relationships=[edge], selected_repository=None))
            self.assertIsNone(graph['edges'][0]['filter'], details)

    def test_a_filter_edge_without_its_assignment_names_none(self):
        edge = {'relation': 'filter', 'target_id': 'bbbbbbbb-0000-4000-8000-000000000002', 'details': {}, 'assertion_class': 'observed'}
        graph = self.project(dict(self.value, relationships=[edge], selected_repository=None))
        self.assertIsNone(graph['edges'][0]['applies_to'])


class CountTests(Truth):
    def test_the_listed_relationships_and_the_added_sources_are_counted_apart(self):
        graph = self.project()
        self.assertEqual(graph['counts'], {'relationships': 7, 'sources': 1})
        self.assertEqual(graph['counts']['relationships'], len(self.value['relationships']), 'the tree header counts the same list')
        origins = [edge['origin'] for edge in graph['edges']]
        self.assertEqual(origins.count('selection'), 1)
        self.assertEqual(next(edge['type'] for edge in graph['edges'] if edge['origin'] == 'selection'), 'repository')
        self.assertEqual(len(graph['edges']), 8, 'the existing edge list is unchanged')

    def test_a_listed_generated_source_is_a_relationship_and_the_repository_is_the_source(self):
        value = dict(self.value, relationships=self.value['relationships'] + [
            {'relation': 'generated_from', 'target_id': 'stacks/dev/privacy.tf', 'details': {}, 'assertion_class': 'historical_local_adoption'}])
        graph = self.project(value)
        self.assertEqual(graph['counts'], {'relationships': 8, 'sources': 1})
        self.assertEqual(len(graph['edges']), 9)

    def test_an_edge_with_no_target_is_still_one_the_read_model_listed(self):
        value = dict(self.value, relationships=self.value['relationships'] + [{'relation': 'setting', 'target_id': None}], selected_repository=None)
        graph = self.project(value)
        self.assertEqual(graph['counts'], {'relationships': 8, 'sources': 0})
        self.assertEqual(graph['excluded'], 1)
        # Entries that are not edges at all are not counted, as the tree does not count them.
        odd = self.project(dict(value, relationships=value['relationships'] + ['x', 3]))
        self.assertEqual(odd['counts']['relationships'], 8)


class LabelTests(Truth):
    def labels(self, graph, width=34):
        from intune_iac.graph_projection import distinct_labels
        return distinct_labels(graph, width)

    def test_two_settings_with_the_common_prefix_never_print_alike_when_cut(self):
        value = dict(self.value, relationships=[setting('privacy_letappsaccesslocation'), setting('privacy_letappsaccesscamera')],
                     selected_repository=None)
        graph = self.project(value)
        labels = self.labels(graph)
        shown = {node['id']: labels[node['ref']] for node in graph['nodes'] if node['kind'] == 'setting'}
        self.assertEqual(len(set(shown.values())), 2, shown)
        for identifier, text in shown.items():
            self.assertLessEqual(len(text), 34)
            self.assertIn('…', text)
            self.assertTrue(identifier.endswith(text.split('…')[-1]), 'the distinguishing tail is kept: ' + text)
            self.assertTrue(identifier.startswith(text.split('…')[0]))
        self.assertEqual({text.split('…')[-1] for text in shown.values()} & {'', ' '}, set())

    def test_two_sources_under_the_same_folder_are_told_apart(self):
        folder = '/home/nsahm/work/journey 28 run/stacks/dev/components/'
        value = dict(self.value, relationships=[
            {'relation': 'generated_from', 'target_id': folder + 'privacy-pilot.tf', 'details': {}, 'assertion_class': 'historical_local_adoption'}],
            selected_repository={'evidence_class': 'recorded_repository_intent',
                                 'scope': {'repository': folder[:-1], 'stack': 'dev', 'component': 'privacy'}})
        graph = self.project(value)
        for width in (20, 34, 48):
            labels = self.labels(graph, width)
            texts = [labels[node['ref']] for node in graph['nodes'] if node['kind'] in ('source', 'repository')]
            self.assertEqual(len(texts), 2)
            self.assertEqual(len(set(texts)), 2, (width, texts))
            self.assertTrue(all(len(text) <= width for text in texts), (width, texts))

    def test_every_node_carries_a_full_label_and_says_whether_it_was_resolved(self):
        first = sorted(node['id'] for node in self.project()['nodes'] if node['kind'] == 'group')[0]
        graph = self.project(names={first: 'Pilot devices'})
        for node in graph['nodes']:
            self.assertTrue(node['label'])
            self.assertIs(node['resolved'], node['name'] is not None)
            self.assertEqual(node['label'], node['name'] if node['name'] else node['id'])
        self.assertTrue(self.node(self.project(value=dict(self.value, name=None)), 'policy')['label'])

    def test_a_label_that_fits_is_never_cut_and_the_cut_is_a_function_of_the_set(self):
        graph = self.project()
        labels = self.labels(graph, 200)
        for node in graph['nodes']:
            self.assertEqual(labels[node['ref']], node['label'])
        self.assertEqual(self.labels(graph, 20), self.labels(graph, 20))
        reordered = self.project(dict(self.value, relationships=list(reversed(self.value['relationships']))))
        self.assertEqual(self.labels(reordered, 20), self.labels(graph, 20))

    def test_identifiers_that_differ_only_in_the_middle_are_never_made_to_look_alike(self):
        one, two = 'x' * 30 + 'AAAA' + 'y' * 30, 'x' * 30 + 'BBBB' + 'y' * 30
        value = dict(self.value, relationships=[{'relation': 'setting', 'target_id': one, 'details': {}},
                                                {'relation': 'setting', 'target_id': two, 'details': {}}], selected_repository=None)
        graph = self.project(value)
        texts = [self.labels(graph, 12)[node['ref']] for node in graph['nodes'] if node['kind'] == 'setting']
        self.assertEqual(len(set(texts)), 2, 'when no cut can tell them apart, the label stays whole')

    def test_the_additions_do_not_mutate_the_input(self):
        import copy
        before = copy.deepcopy(self.value)
        self.project(states={self.object_id: 'expired'})
        self.assertEqual(self.value, before)


if __name__ == '__main__':
    unittest.main()
