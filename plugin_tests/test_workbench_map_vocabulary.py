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


class ViewportCutTests(MapTruth):
    """Item 2: a row the pane cuts says so, at the right edge and, once panned, at the left."""
    ELLIPSIS = {'unicode': '…', 'ascii': '...'}

    def full_rows(self, rules):
        return self.rows(self.graph(self.value, freshness='fresh'), rules=rules)[1]

    def body_rows(self, ws):
        return [row[2:-2].rstrip() for row in self.plain(ws) if row.startswith(('│', '|'))]

    def test_every_cut_row_ends_with_an_ellipsis_and_no_uncut_row_claims_one(self):
        from intune_iac.workbench_screens import MAP_GUTTER, MAP_WIDTH, viewport_row
        from intune_iac.workbench_tui import cell_width
        for rules, ellipsis in self.ELLIPSIS.items():
            rows = self.full_rows(rules)
            for content in (40, 56, 70, MAP_WIDTH + 2):
                for hscroll in range(0, max(1, MAP_WIDTH - content + 1), 3):
                    for row in rows:
                        shown = viewport_row(row, hscroll, content, MAP_GUTTER, ellipsis)
                        place = (rules, content, hscroll, str(row))
                        self.assertLessEqual(cell_width(shown), content, place)
                        beyond = str(row)[MAP_GUTTER + hscroll + content - MAP_GUTTER:].strip()
                        before = str(row)[MAP_GUTTER:MAP_GUTTER + hscroll].strip() if hscroll else ''
                        if beyond:
                            self.assertTrue(shown.endswith(ellipsis), place)
                            self.assertEqual(cell_width(shown), content, place)
                        else:
                            tail = shown[MAP_GUTTER + (len(ellipsis) if before else 0):].rstrip()
                            self.assertFalse(tail.endswith(ellipsis) and not str(row).rstrip().endswith(ellipsis), place)
                        edge = shown[MAP_GUTTER:MAP_GUTTER + len(ellipsis)]
                        self.assertEqual(edge == ellipsis, bool(before), place)
                        self.assertEqual(shown[:MAP_GUTTER], str(row)[:MAP_GUTTER], 'the gutter is never touched')

    def test_at_60x20_the_policy_word_and_the_group_identifiers_end_with_an_ellipsis(self):
        for rules, ellipsis in self.ELLIPSIS.items():
            body = self.body_rows(self.workspace((60, 20), rules=rules))
            policy = next(row for row in body if row.startswith('>*'))
            group = next(row for row in body if 'exclusion' in row)
            self.assertTrue(policy.endswith(ellipsis), policy)
            self.assertTrue(group.endswith(ellipsis), group)
            self.assertNotRegex(group, r'identity 46e$')
            note = next(row for row in body if 'applies to b564fc9a' in row)
            self.assertFalse(note.endswith(ellipsis), note)

    def test_panned_right_a_row_that_starts_before_the_edge_begins_with_an_ellipsis_after_the_gutter(self):
        for rules, ellipsis in self.ELLIPSIS.items():
            ws = self.workspace((60, 20), rules=rules)
            ws.hscroll = 8
            body = self.body_rows(ws)
            policy = next(row for row in body if row.startswith('>*'))
            self.assertEqual(policy[3:3 + len(ellipsis)], ellipsis, policy)
            self.assertRegex(policy[:3], r'^[> ][* ] ')
            # The policy word is cut at the right edge as well: it can no longer show as a bare "no".
            self.assertTrue(policy.endswith(ellipsis), policy)
            self.assertNotRegex(policy, r'\bno$')
            exclusion = next(row for row in body if 'identity 46ee39ed' in row)
            self.assertEqual(exclusion[3:3 + len(ellipsis)], ellipsis, exclusion)
            # The tree rail of a note row is part of the row, so panning cuts it too.
            note = next(row for row in body if 'applies to b564fc9a' in row)
            self.assertEqual(note[3:3 + len(ellipsis)], ellipsis, note)

    def test_a_row_with_only_blank_space_beyond_an_edge_claims_nothing(self):
        from intune_iac.workbench_screens import viewport_row
        for ellipsis in ('…', '...'):
            row = '>*  ' + ' ' * 30 + 'TEXT' + ' ' * 20
            self.assertEqual(viewport_row(row, 8, 40, 3, ellipsis), '>* ' + row[11:11 + 37])
            self.assertEqual(viewport_row(row, 0, 60, 3, ellipsis), row[:60])
            full = '>* ' + 'A' * 40
            self.assertEqual(viewport_row(full, 0, 20, 3, ellipsis), '>* ' + 'A' * (17 - len(ellipsis)) + ellipsis)
            self.assertEqual(viewport_row(full, 10, 20, 3, ellipsis), '>* ' + ellipsis + 'A' * (17 - 2 * len(ellipsis)) + ellipsis)
            # A cut that leaves nothing of the row in the window still says the row goes on.
            self.assertEqual(viewport_row('>* abc', 8, 20, 3, ellipsis), '>* ' + ellipsis)

    def test_panned_to_the_end_no_row_is_cut_on_the_right(self):
        from intune_iac.workbench_screens import MAP_WIDTH
        ws = self.workspace((60, 20))
        ws.hscroll = 10_000
        body = self.body_rows(ws)
        mapped = [row for row in body if MARK.search(row)]
        self.assertTrue(mapped)
        self.assertTrue(all(not row.endswith('…') for row in mapped), mapped)
        self.assertIn('showing %d-%d of %d' % (MAP_WIDTH - 56 + 4, MAP_WIDTH, MAP_WIDTH), ' '.join(' '.join(body).split()))

    def test_a_pane_wide_enough_for_the_map_cuts_nothing(self):
        for rules, ellipsis in self.ELLIPSIS.items():
            body = self.body_rows(self.workspace((120, 40), rules=rules))
            mapped = [row for row in body if MARK.search(row) and ('→' in row or '->' in row)]
            self.assertTrue(mapped)
            self.assertTrue(all(row.endswith(('—', '--', 'none recorded')) for row in mapped), mapped)

    def test_the_pan_statement_stays(self):
        text = ' '.join(' '.join(row.strip('│ ') for row in self.plain(self.workspace((60, 20)))).split())
        self.assertIn('Left/Right pan: showing 1-56 of 75, states at 63.', text)


class KeyLineTests(MapTruth):
    """Item 3: as the width shrinks the key line gives up b back before a actions and Enter."""
    FIRST_WORD = {'?': 'help', 'a': 'actions', ':': 'command', 'Up/Down': 'move', 'Home': 'edge', 'Left/Right': 'pan',
                  'Enter': 'inspect', 'b': 'back', 'q': 'exit'}

    def keys_named(self, line):
        return {self.FIRST_WORD[part.split(' ')[0]] for part in line.split(' | ')}

    def test_back_goes_before_actions_and_enter_at_every_width(self):
        from intune_iac.workbench_tui import help_line
        for inspect in (True, False):
            for pan in (True, False):
                for width in range(60, 141):
                    line = help_line(width, map_keys=True, inspect=inspect, pan=pan)
                    named = self.keys_named(line)
                    place = (width, inspect, pan, line)
                    if 'back' in named:
                        self.assertIn('actions', named, place)
                        self.assertEqual('inspect' in named, inspect, place)
                    self.assertEqual('pan' in named, pan, place)

    def test_a_narrower_width_only_ever_gives_up_keys(self):
        from intune_iac.workbench_tui import help_line
        for inspect in (True, False):
            for pan in (True, False):
                previous = None
                for width in range(140, 59, -1):
                    named = self.keys_named(help_line(width, map_keys=True, inspect=inspect, pan=pan))
                    if previous is not None:
                        self.assertLessEqual(named, previous, (width, inspect, pan))
                    previous = named

    def test_at_60_columns_the_line_names_actions_enter_and_left_right_where_they_work(self):
        from intune_iac.workbench_tui import help_line
        line = help_line(60, map_keys=True)
        self.assertLessEqual(len(line), 60)
        for key in ('a actions', 'Enter inspect', 'Left/Right', 'q exit', '? help'):
            self.assertIn(key, line)
        self.assertNotIn('b back', line)
        no_route = help_line(60, map_keys=True, inspect=False)
        self.assertNotIn('Enter', no_route)
        self.assertIn('a actions', no_route)
        self.assertIn('Left/Right', no_route)
        no_pan = help_line(60, map_keys=True, pan=False)
        self.assertNotIn('Left/Right', no_pan)
        self.assertIn('a actions', no_pan)
        self.assertIn('Enter inspect', no_pan)

    def test_the_60x20_frame_names_the_keys_that_work_for_the_focused_node(self):
        ws = self.workspace((60, 20))
        last = self.plain(ws)[-1]
        for key in ('a actions', 'Enter inspect', 'Left/Right'):
            self.assertIn(key, last)
        # Focus on a node with no inspect route: Enter is no longer named, the others stay.
        ws.map_focus, ws.follow_focus = ws._map_nodes()[1], True
        last = self.plain(ws)[-1]
        self.assertNotIn('Enter', last)
        for key in ('a actions', 'Left/Right'):
            self.assertIn(key, last)
        self.assertFalse(ws._map_focus_inspectable())

    def test_a_hazard_key_still_leads_and_the_wide_line_is_unchanged(self):
        from intune_iac.workbench_tui import MAP_HELP_LINES, help_line
        self.assertEqual(help_line(140, map_keys=True), MAP_HELP_LINES[0])
        self.assertIn('a actions', help_line(100, lead=('a actions',), map_keys=True))
        self.assertTrue(help_line(60, lead=('a actions',), map_keys=True).startswith('? help | a actions'))


if __name__ == '__main__':
    unittest.main()
