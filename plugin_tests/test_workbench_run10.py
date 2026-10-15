"""PKG-PRES-RUN10 (journey 29 run 6 and journey 28 run 10 frame reviews): what the screens say, not what the product decides.

Item 1: the typed tree's header counts as the map's header does, from one function.
Item 2: the companion entry, its long text and the page name the command one way, in the product's own flags.
Item 3: at 60x20 the key line names the way to move the focus and the legend defines the no-state word.
Item 4: the typed tree's wrapped identifier sits under its column; a filter note reads as part of its row.
Items are added below in the order of the brief; each class names its item.
Temporary directories only.
"""
import re
import unittest

from plugin_tests import test_workbench_companion as companion_tests
from plugin_tests.test_workbench_map_truth import MARK, MapTruth

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


WRITE_COMMAND = 'workbench companion --root STORE --object ID --out FILE'


class CompanionWordingTests(companion_tests.Fixture):
    """Item 2: the focused companion entry, its long text and the page name the command one way, in the product's flags."""

    def entry(self):
        from intune_iac.workbench import _inspection, _store
        from intune_iac.workbench_screens import actions_lines
        actions = _inspection(_store(self.root), self.object_id, attention=True)['actions']
        last = len(actions) - 1
        rows = [line.strip() for line in actions_lines(actions, last, 116, name='Privacy pilot 3', object_id=self.object_id)]
        return actions[last], ' '.join(' '.join(rows).split())

    def test_the_entry_names_the_command_in_the_products_flags(self):
        action, rendered = self.entry()
        self.assertEqual(action['kind'], 'companion')
        self.assertIn(WRITE_COMMAND, rendered)
        self.assertIn('--serve', rendered)
        self.assertNotIn('"companion serve"', rendered)

    def test_the_address_is_printed_by_the_product_not_supplied(self):
        action, rendered = self.entry()
        self.assertRegex(rendered, r'--serve[^.]*prints? (the|its) (secret )?address')
        need = action['needs'][0]
        self.assertTrue(need.startswith('FILE:'), need)
        self.assertNotIn('serve', need)
        self.assertNotIn('loopback', need)
        self.assertRegex(need, r'you supply (it|the path)')
        self.assertIn('not an address', need)

    def test_the_page_names_the_same_command_and_where_the_address_comes_from(self):
        from intune_iac.companion_page import render_page
        from intune_iac.graph_projection import project
        html = render_page(project(self.value, freshness='fresh'), mode_class='synthetic_local_process_only')
        page = ' '.join(re.sub(r'<[^>]+>', ' ', re.sub(r'(?s)<(script|style).*?</\1>', ' ', html)).split())
        self.assertIn(WRITE_COMMAND, page)
        self.assertIn('workbench companion --root STORE --object ID --serve', page)
        self.assertNotIn('the same workbench companion command', page)
        self.assertRegex(page, r'--serve[^.]*prints? (the|its) (secret )?address')


class NarrowMapTests(MapTruth):
    """Item 3: at 60x20 the key line names a key that moves the focus and the legend defines the no-state word."""

    def narrow(self, size=(60, 20), rules="unicode", hscroll=0):
        ws = self.workspace(size, rules=rules)
        ws.hscroll = hscroll
        return MapTruth.plain(self, ws)

    def test_the_key_line_at_60x20_names_the_way_to_move_the_focus(self):
        for hscroll in (0, 8):
            line = self.narrow(hscroll=hscroll)[-1]
            for key in ('? help', 'a actions', 'Up/Down', 'Left/Right', 'Enter', 'q exit'):
                self.assertIn(key, line, (hscroll, line))
            self.assertLessEqual(len(line), 60)

    def test_a_key_is_named_only_where_it_works(self):
        from intune_iac.workbench_tui import help_line
        for inspect in (True, False):
            for pan in (True, False):
                line = help_line(60, map_keys=True, inspect=inspect, pan=pan)
                self.assertIn('Up/Down', line)
                self.assertIn('a actions', line)
                self.assertEqual('Enter' in line, inspect, (inspect, pan, line))
                self.assertEqual('Left/Right' in line, pan, (inspect, pan, line))

    def test_the_legend_at_60x20_defines_the_word_its_rows_show(self):
        for rules, word in (('unicode', '—'), ('ascii', 'n/a')):
            # Panned until the state column is in view: the rows show the word the legend must define.
            rows = [row.strip('│| ').rstrip() for row in self.narrow(rules=rules, hscroll=12)]
            self.assertTrue(any(row.endswith(' ' + word) for row in rows), (rules, rows))
            legend = next(row for row in rows if '> focus * selected' in row)
            self.assertIn('%s means no state' % word, legend, rules)
            self.assertIn('? help', legend)


class FilterBlockTests(MapTruth):
    """Item 4: a wrapped identifier sits under the column it continues; a filter note reads as part of the row above."""

    CONNECTORS = ('├', '└', '|-', '`-')

    def tree(self, width, rules):
        from intune_iac.workbench_screens import relationship_lines
        return relationship_lines(self.value, width, rules)

    def continuations(self, lines):
        """(row above, continuation) pairs: a continuation has the rail but no connector of its own."""
        found = []
        for above, line in zip(lines, lines[1:]):
            if (above.startswith('  ') and any(mark in above[:9] for mark in self.CONNECTORS) and line.startswith('  ')
                    and not any(mark in line[:9] for mark in self.CONNECTORS) and line.strip(' │|')):
                found.append((above, line))
        return found

    def test_a_wrapped_identifier_is_indented_under_the_column_it_continues(self):
        for rules in ('unicode', 'ascii'):
            seen = 0
            for width in (60, 80, 100):
                for above, line in self.continuations(self.tree(width, rules)):
                    seen += 1
                    target = above.index('Unresolved') if 'Unresolved' in above else None
                    if target is None:
                        continue
                    start = len(line) - len(line.lstrip(' │|'))
                    self.assertEqual(start, target, (rules, width, above, line))
            self.assertGreater(seen, 2, rules)

    def test_the_wrap_keeps_every_identifier_whole(self):
        identifier = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')
        for rules in ('unicode', 'ascii'):
            wide = identifier.findall(' '.join(self.tree(200, rules)))
            self.assertGreater(len(wide), 5)
            for width in (60, 100):
                self.assertEqual(identifier.findall(' '.join(self.tree(width, rules))), wide, (rules, width))

    def test_a_filter_note_reads_as_part_of_the_row_above(self):
        for rules in ('unicode', 'ascii'):
            _, rows = self.rows(self.graph(freshness='fresh'), rules=rules)
            text = [row.rstrip() for row in rows]
            notes = [row for row in text if 'applies to b564fc9a' in row or '+ filter 5aa36291 include' in row]
            self.assertEqual(len(notes), 2, rules)
            for note in notes:
                body = note.lstrip(' │|').rstrip()
                self.assertTrue(body.startswith('(') and body.endswith(')'), (rules, note))
            index = next(i for i, row in enumerate(text) if 'filter 5aa36291' in row and MARK.search(row))
            self.assertIn('(applies to b564fc9a)', text[index + 1], rules)
