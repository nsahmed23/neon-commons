"""PKG-PRES-RUN20: the Inspector and pager findings of journey 34 run 2 (review A) and journey 33 run 2 (review B).

Item 1: a GUID stays whole after its label at 40x12. Item 2: a label stays with its command across a page boundary.
Item 3: the attention rollup counts a closed approval window. Item 4: one reason name, and next steps that read the
current operation. Item 5: a hint names a key that works where it is shown.
"""
import re
import unittest

from plugin_tests import test_workbench_run19 as run19
from plugin_tests.test_workflow_map import LayerFixture, OBJECT, typed


def key(char):
    return ('text', char)


class InspectorGuidTests(LayerFixture):
    """Journey 33 run 2 review B finding 1: the 40x12 Inspector broke the policy GUID at a hyphen after `Identity  `."""

    def inspector_rows(self, size, rules='unicode'):
        if not hasattr(self, 'operation'):
            self.prepare()
        opened = len(typed('select ' + OBJECT))
        ws, frames = self.run_keys(typed('select ' + OBJECT) + [key('q')], size, rules)
        return self.plain(frames[opened])

    def assert_whole(self, rows):
        holders = [row for row in rows if OBJECT in row]
        self.assertTrue(holders, 'the policy GUID is on no row:\n' + '\n'.join(rows))
        for row in rows:
            body = row.strip('│| ').strip()
            if OBJECT in row:
                continue
            self.assertIsNone(re.search(r'[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-?\s*$', body), 'a GUID broken: ' + row)
            self.assertFalse(re.match(r'[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\b', body), 'a GUID broken: ' + row)
        return holders[0]

    def test_the_guid_moves_whole_to_its_own_row_at_the_left_margin_at_40x12(self):
        rows = self.inspector_rows((40, 12))
        row = self.assert_whole(rows)
        self.assertEqual(row.strip('│| ').strip(), OBJECT + row.strip('│| ').strip()[len(OBJECT):])
        self.assertTrue(row.strip('│ ').startswith(OBJECT), row)
        self.assertNotIn('Identity  ' + OBJECT[:10], row)

    def test_below_40x12_no_row_holds_a_piece_of_the_guid(self):
        rows = self.inspector_rows((39, 11))
        for row in rows:
            self.assertIsNone(re.search(r'[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}', row), row)

    def test_the_guid_is_whole_in_the_inspector_lines_of_a_38_and_a_37_column_pane(self):
        from intune_iac.workbench_screens import inspector_lines
        value = {'object_id': OBJECT, 'name': 'Windows Privacy Pilot', 'body': {'platforms': 'windows10', 'technologies': ['mdm']}}
        for width in (38, 37, 36):
            rows = inspector_lines(value, width)
            holder = [row for row in rows if OBJECT in row]
            self.assertEqual(len(holder), 1, (width, rows))
            self.assertTrue(holder[0].startswith(OBJECT), (width, holder[0]))
        # Wider than the pane it must break, and then on a row of its own.
        rows = inspector_lines(value, 30)
        self.assertFalse([row for row in rows if OBJECT in row])

    def test_the_guid_stays_after_its_label_at_80x24_and_120x40(self):
        for size in ((80, 24), (120, 40)):
            rows = self.inspector_rows(size)
            holder = next(row for row in rows if OBJECT in row)
            self.assertIn('Identity  ' + OBJECT, holder, size)


class LabelWithCommandPagingTests(run19.CatalogLayerCase):
    """Journey 33 run 2 review B finding 2: a page kept a command whole but left the line that introduces it (`Run:`,
    `Resume:`, `Next action:`) at its foot, so a reader paging forward saw an empty label. The label and its command
    now move together."""

    def test_page_starts_keep_the_introducing_line_with_its_command(self):
        from intune_iac.workbench_screens import page_starts
        rows = ['text'] * 4 + ['  not checked; Run:', "    intune-iac catalog 'd' \\", '      --goal discover'] + ['text'] * 6
        self.assertEqual(page_starts(rows, 5), [0, 4, 9])            # the break was 5, after the label
        rows = ['text'] * 3 + ['  Next action:', '    intune-iac wizard --session s'] + ['text'] * 6
        self.assertEqual(page_starts(rows, 4), [0, 3, 7])            # the break was 4, after the label
        # A line ending in a colon that does not introduce a command stays where it is.
        rows = ['text'] * 3 + ['  available:', '    something else'] + ['text'] * 6
        self.assertEqual(page_starts(rows, 4), [0, 4, 8])
        # A label with a command taller than the page cannot be kept together; the plain break stands.
        rows = ['Run:'] + ['intune-iac x \\'] * 5 + ['end']
        self.assertEqual(page_starts(rows, 3), [0, 3, 6])

    def check_pages(self, size):
        for extra in range(6):
            pages = [self.body(page) for page in self.pages(self.layer(size, run19.CommandPagingTests.catalog_with(extra)))]
            self.assertGreater(len(pages), 4)
            for number, (rows, following) in enumerate(zip(pages, pages[1:]), 1):
                shown = [row for row in rows if row]
                self.assertFalse(shown[-1].endswith('\\'), 'extra %d, page %d ends inside a command' % (extra, number))
                if following:
                    self.assertFalse(shown[-1].endswith(':') and following[0].startswith('intune-iac'),
                                     'extra %d, page %d ends on %r and its command starts the next page' % (extra, number, shown[-1]))

    def test_at_80x24_no_page_ends_on_a_label_whose_command_starts_the_next(self):
        self.check_pages((80, 24))

    def test_at_60x20_no_page_ends_on_a_label_whose_command_starts_the_next(self):
        self.check_pages((60, 20))


if __name__ == '__main__':
    unittest.main()
