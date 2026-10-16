"""PKG-PRES-RUN20: the Inspector and pager findings of journey 34 run 2 (review A) and journey 33 run 2 (review B).

Item 1: a GUID stays whole after its label at 40x12. Item 2: a label stays with its command across a page boundary.
Item 3: the attention rollup counts a closed approval window. Item 4: one reason name, and next steps that read the
current operation. Item 5: a hint names a key that works where it is shown.
"""
import re
import unittest

from plugin_tests.test_workflow_map import LayerFixture, OBJECT, typed

GUID = re.compile(r'[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}')
FRAGMENT = re.compile(r'[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}(?:-[0-9A-Fa-f]{1,4})*-?(?![0-9A-Fa-f-])')


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


if __name__ == '__main__':
    unittest.main()
