"""PKG-PRES-RUN10 (journey 29 run 6 and journey 28 run 10 frame reviews): what the screens say, not what the product decides.

Item 1: the typed tree's header counts as the map's header does, from one function.
Items are added below in the order of the brief; each class names its item.
Temporary directories only.
"""
import unittest

from plugin_tests.test_workbench_map_truth import MapTruth

GENERATED = {'relation': 'generated_from', 'target_id': '/home/nsahm/work/journey 29/generated/22222222-2222-4222-8222-222222222222.tf',
             'details': {}, 'assertion_class': 'historical_local_adoption'}


class TreeCountTests(MapTruth):
    def tree_header(self, value, width=100, rules='unicode'):
        from intune_iac.workbench_screens import relationship_lines
        return next(line for line in relationship_lines(value, width, rules) if '| coverage' in line)

    def test_the_tree_header_reads_as_the_map_header_does(self):
        from intune_iac.graph_projection import count_words
        with_file = dict(self.value, relationships=self.value['relationships'] + [GENERATED])
        for value in (self.value, with_file, dict(self.value, selected_repository=None),
                      dict(self.value, relationships=[], selected_repository=None),
                      dict(self.value, relationships=self.value['relationships'][:1], selected_repository=None)):
            words = count_words(self.graph(value))
            self.assertTrue(self.tree_header(value).startswith(words + ' | coverage'), (self.tree_header(value), words))

    def test_a_listed_repository_is_not_counted_as_an_edge(self):
        header = self.tree_header(self.value)
        self.assertTrue(header.startswith('7 relationships, 1 repository | coverage'), header)
        self.assertNotIn(' edges', header)
        self.assertNotIn(' edge ', header)

    def test_the_header_agrees_with_the_rows_the_tree_lists(self):
        from intune_iac.workbench_screens import relationship_lines
        lines = relationship_lines(self.value, 100, 'unicode')
        rows = [line for line in lines if line.lstrip(' │').startswith(('├', '└')) and ' writer ' not in line]
        self.assertEqual(len(rows), 7 + 1)
        self.assertIn('7 relationships, 1 repository', next(line for line in lines if '| coverage' in line))
