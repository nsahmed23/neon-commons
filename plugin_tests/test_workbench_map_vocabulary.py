"""PKG-UXVIS-1c (journey 29 run 5 frame review): the relationship map says one thing in one way.

Item 1: one kind-word table serves the projection, the map and the page; a generated edge names a file; the header
counts the relationships the read model lists and, apart, the repositories the engineer selected; the word "source"
no longer means two things on one screen.
Item 2: a row the viewport cuts says so with an ellipsis.
Item 3: the narrow key lines keep the keys that work.
Item 4: the page tells the truth about the filter, the policy's state and how to reach live mode.
Item 5: the legend explains every mark it shows.
Item 6: ASCII keeps its rails and its words apart.
The fixtures are the ones of test_workbench_map and test_workbench_map_truth (synthetic seed 510); temporary
directories only.
"""
import re
import unittest

from plugin_tests.test_workbench_map import MARK
from plugin_tests.test_workbench_map_truth import MapTruth

GENERATED = {'relation': 'generated_from', 'target_id': '/home/nsahm/work/journey 29/generated/22222222-2222-4222-8222-222222222222.tf',
             'details': {}, 'assertion_class': 'historical_local_adoption'}


class OneWordOneMeaningTests(MapTruth):
    def with_generated(self):
        return dict(self.value, relationships=self.value['relationships'] + [GENERATED])

    def test_one_kind_word_table_serves_the_projection_the_map_and_the_page(self):
        from intune_iac import companion_page, graph_projection, workbench_screens
        self.assertIs(workbench_screens.MAP_KIND_WORDS, graph_projection.KIND_WORDS)
        self.assertEqual(workbench_screens.MAP_DISTINCT_KINDS, graph_projection.DISTINCT_KINDS)
        self.assertEqual(companion_page.DISTINCT_KINDS, graph_projection.DISTINCT_KINDS)
        graph = self.graph(self.with_generated())
        for node in graph['nodes']:
            self.assertEqual(node['kind_word'], graph_projection.KIND_WORDS[node['kind']], node)

    def test_the_target_of_a_generated_edge_is_a_file_and_the_repository_a_repository(self):
        graph = self.graph(self.with_generated())
        words = {node['kind']: node['kind_word'] for node in graph['nodes']}
        self.assertEqual(words['file'], 'file')
        self.assertEqual(words['repository'], 'repository')
        self.assertNotIn('source', words)
        self.assertFalse(next(node for node in graph['nodes'] if node['kind'] == 'file')['state_applies'])

    def test_the_map_names_the_generated_target_a_file_in_its_row_and_its_focus_rows(self):
        graph = self.graph(self.with_generated(), freshness='fresh')
        for rules in ('unicode', 'ascii'):
            _, rows = self.rows(graph, rules=rules)
            generated = self.node_row(rows, 'generated')
            self.assertIn(' file /home/', generated)
            self.assertNotRegex(generated, r'\bsource\b')
            repository = self.node_row(rows, 'repository')
            self.assertNotRegex(repository, r'\bsource\b')
            file_ref = next(node['ref'] for node in graph['nodes'] if node['kind'] == 'file')
            lines, _ = self.rows(graph, rules=rules, focus=file_ref)
            self.assertTrue(any(line.startswith('FOCUS file  /home/') for line in lines), lines[-4:])
            focus_repo = next(node['ref'] for node in graph['nodes'] if node['kind'] == 'repository')
            lines, _ = self.rows(graph, rules=rules, focus=focus_repo)
            self.assertTrue(any(line.startswith('FOCUS repository  ') for line in lines), lines[-4:])

    def test_the_word_source_means_nothing_on_the_map_beyond_its_layer_heading(self):
        graph = self.graph(self.with_generated(), freshness='fresh')
        for rules in ('unicode', 'ascii'):
            lines, _ = self.rows(graph, rules=rules, focus=next(n['ref'] for n in graph['nodes'] if n['kind'] == 'file'))
            text = '\n'.join(lines).replace('SOURCE AND LINEAGE', '')
            self.assertEqual(re.findall(r'\bsources?\b', text, re.I), [], rules)

    def test_the_header_counts_relationships_and_repositories_apart_as_the_tree_does(self):
        from intune_iac.workbench_screens import relationship_lines
        for value, relationships, repositories in (
                (self.value, 7, 1), (self.with_generated(), 8, 1),
                (dict(self.value, selected_repository=None), 7, 0), (dict(self.value, relationships=[], selected_repository=None), 0, 0)):
            graph = self.graph(value)
            self.assertEqual(graph['counts'], {'relationships': relationships, 'repositories': repositories})
            header = next(line for line in self.rows(graph)[0] if line.startswith('[MAP]'))
            self.assertEqual(header, '[MAP] one hop | %d relationship%s, %d repositor%s' % (
                relationships, '' if relationships == 1 else 's', repositories, 'y' if repositories == 1 else 'ies'))
            tree = next(line for line in relationship_lines(value, 100, 'unicode') if ' edges |' in line or ' edge |' in line)
            self.assertTrue(tree.startswith('%d edge' % relationships), (tree, header))

    def test_frame_21s_policy_reads_seven_relationships_and_one_repository(self):
        header = next(line for line in self.rows(self.graph(states={self.object_id: 'expired'}, freshness='fresh'))[0]
                      if line.startswith('[MAP]'))
        self.assertIn('7 relationships, 1 repository', header)

    def test_the_page_names_the_same_counts_and_kinds_in_its_summary_labels_and_detail(self):
        from intune_iac.companion_page import render_page
        graph = self.graph(self.with_generated(), freshness='fresh')
        page = render_page(graph, mode_class='synthetic_local_process_only')
        self.assertIn('8 relationships, 1 repository from the selected policy', page)
        labels = re.findall(r'<text class="lb"[^>]*>([^<]*)</text>', page)
        self.assertEqual(len([label for label in labels if label.startswith('generated  file /')]), 1, labels)
        self.assertEqual(len([label for label in labels if re.match(r'repository\s', label)]), 1, labels)
        self.assertNotIn('the policy was generated from the source', page)
        self.assertIn('<dt>Kind</dt><dd>file</dd>', page)
        self.assertNotRegex(page.split('id="legend"')[1].split('</section>')[0].replace('SOURCE AND LINEAGE', ''), r'\bsources?\b')


if __name__ == '__main__':
    unittest.main()
