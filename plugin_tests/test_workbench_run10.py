"""PKG-PRES-RUN10 (journey 29 run 6 and journey 28 run 10 frame reviews): what the screens say, not what the product decides.

Item 1: the typed tree's header counts as the map's header does, from one function.
Item 2: the companion entry, its long text and the page name the command one way, in the product's own flags.
Items are added below in the order of the brief; each class names its item.
Temporary directories only.
"""
import re
import unittest

from plugin_tests import test_workbench_companion as companion_tests
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
