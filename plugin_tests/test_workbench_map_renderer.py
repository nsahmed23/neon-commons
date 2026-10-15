"""The renderer prerequisites of the relationship map (requirement 17 UX-VIS, first slice, item 1).

A map surface is exempt from the body word-wrap in draw(), which wraps at a space and would split a connector row,
and the pane gains a horizontal viewport for map lines (it scrolled rows only). Ordinary text keeps its wrapping and
ignores the viewport. The horizontal keys are named in the footer and the one help reference only when a map is shown.
"""
from collections import deque
import io
import re
import unittest

from intune_iac.workbench_tui import cell_width

ANSI = re.compile(r'\x1b\[[0-9;?]*[A-Za-z]')
TENANT = '11111111-1111-4111-8111-111111111111'
POLICY = '22222222-2222-4222-8222-222222222222'


def workspace(lines, size=(80, 24), **extra):
    from intune_iac.workbench_tui import Workspace
    ws = Workspace.__new__(Workspace)
    out = io.StringIO()
    ws.__dict__.update(
        stdout=out, tab=1, value={'object_id': POLICY, 'evidence_class': 'synthetic'}, scroll=0, mode=None,
        notice='Ready.', rules='unicode', color=False, theme='dark', selected=POLICY, layer='summary',
        facts={'object_id': POLICY, 'name': 'Windows Privacy Pilot'}, store=type('S', (), {'tenant_id': TENANT})(),
        mode_class='synthetic', last_command='inspect', size=size, pending=deque(), key_reader=None, rows=[],
        operation_rows=[], operation_highlight=0, highlight=0, active_operation=None, execution_result=None,
        active_service=None, active_adoption=None, active_adoption_plan=None, submission_key='enter', trail=[],
        current_view=None, quiet=None, staged=None, _detail_cache=None, buffer='', cursor=0, pasting=False,
        input_overflow=False, view_command='inspect', page_command='overview')
    ws.__dict__.update(extra)
    ws._terminal_size = lambda: ws.size
    ws._data_lines = lambda width: list(lines)
    return ws


def rows_of(ws):
    ws.draw()
    frame = ws.stdout.getvalue().split('\x1b[H')[-1].replace('\x1b[J', '')
    return [ANSI.sub('', row) for row in frame.split('\r\n')]


def keys(ws, sequence):
    class Reader:
        def __init__(self, items): self.items = list(items)
        def read(self): return self.items.pop(0)
    ws.key_reader = Reader(sequence)
    return ws.input('')


class WrapExemptionTests(unittest.TestCase):
    def test_a_map_line_wider_than_the_pane_is_not_wrapped_and_ordinary_text_still_is(self):
        from intune_iac.workbench_screens import MapLine
        wide = 'ROW-A ' + 'x' * 40 + ' ' + 'y' * 40          # one space inside: wrapping would split it there
        rows = rows_of(workspace([MapLine(wide), 'plain ' + 'p' * 40 + ' ' + 'q' * 40]))
        body = [row for row in rows if row.startswith('│')]
        self.assertEqual(sum('ROW-A' in row for row in body), 1)
        self.assertFalse(any(row.strip('│ ').startswith('y') for row in body), 'the map row was wrapped at its space')
        self.assertTrue(any(row.strip('│ ').startswith('q') for row in body), 'ordinary text lost its wrapping')
        for row in rows:
            self.assertLessEqual(cell_width(row), 80, row)

    def test_a_map_line_is_a_string_and_marks_only_itself(self):
        from intune_iac.workbench_screens import MapLine
        line = MapLine('abc')
        self.assertEqual(line, 'abc')
        self.assertIsInstance(line, str)
        self.assertNotIsInstance('abc', MapLine)


class HorizontalViewportTests(unittest.TestCase):
    LINE = ''.join(str(index % 10) for index in range(100))        # 0123456789 repeated: a column ruler

    def lines(self):
        from intune_iac.workbench_screens import MapLine
        return [MapLine(self.LINE), 'ordinary text that must not move']

    def test_the_pane_shows_the_columns_from_the_horizontal_offset_and_only_for_map_lines(self):
        for offset in (0, 7, 20):
            ws = workspace(self.lines(), hscroll=offset)
            rows = rows_of(ws)
            # The first three cells (the marker gutter) stay; the rest of the row pans from the offset.
            expected = self.LINE[:3] + self.LINE[3 + offset:3 + offset + 73]
            self.assertTrue(any(row[2:2 + 76] == expected for row in rows), (offset, expected))
            self.assertTrue(any('ordinary text that must not move' in row for row in rows))
            self.assertTrue(all(cell_width(row) <= 80 for row in rows))

    def test_the_offset_never_passes_the_end_of_the_widest_map_line(self):
        ws = workspace(self.lines(), hscroll=10_000)
        rows_of(ws)
        self.assertEqual(ws.hscroll, 100 - 76)

    def test_a_wide_character_cut_by_the_offset_is_not_drawn_half(self):
        from intune_iac.workbench_screens import MapLine
        ws = workspace([MapLine('漢字' * 20)], hscroll=2)       # each character is two cells wide
        rows = rows_of(ws)
        row = next(row for row in rows if '漢' in row or '字' in row)
        self.assertLessEqual(cell_width(row), 80)
        # The gutter is three cells: one character and the blank that stands for half of the next. The cell the offset
        # cuts through is a blank too, never a stray half.
        self.assertTrue(row.startswith('│ 漢  字'), row)

    def test_left_and_right_pan_a_map_and_stop_at_both_ends(self):
        from intune_iac.workbench_screens import MapLine
        ws = workspace([MapLine(self.LINE)], size=(60, 20), tab=2)
        ws._map_shown = lambda: True
        self.assertEqual(keys(ws, ['right', 'right', ('text', 'q')]), 'quit')
        self.assertEqual(ws.hscroll, 16)
        keys(ws, ['right'] * 6 + [('text', 'q')])
        self.assertEqual(ws.hscroll, 100 - 56)            # the end of the line, never past it
        keys(ws, ['left'] * 20 + [('text', 'q')])
        self.assertEqual(ws.hscroll, 0)


class KeyLineTests(unittest.TestCase):
    def test_the_footer_names_the_map_keys_only_when_a_map_is_shown(self):
        from intune_iac.workbench_tui import HELP_LINES, help_line
        for width in (120, 80, 60):
            self.assertIn(help_line(width), HELP_LINES)              # the ordinary line is unchanged
            self.assertNotIn('Left/Right', help_line(width))
            line = help_line(width, map_keys=True)
            self.assertLessEqual(cell_width(line), width, line)
            self.assertIn('Left/Right', line)
            self.assertIn('q exit', line)
        # Keys the hazard band names still lead.
        self.assertIn('a actions', help_line(120, lead=('a actions',), map_keys=True))

    def test_the_help_reference_lists_the_map_keys_only_when_a_map_can_be_shown(self):
        from intune_iac.workbench_screens import help_lines
        plain = ' '.join(' '.join(help_lines(100)).split())
        shown = ' '.join(' '.join(help_lines(100, map_keys=True)).split())
        for word in ('Left, Right', 'Home'):
            self.assertNotIn(word, plain)
            self.assertIn(word, shown)
        for line in help_lines(100, map_keys=True) + help_lines(40, map_keys=True):
            self.assertLessEqual(cell_width(line), 100)
        for line in help_lines(40, map_keys=True):
            self.assertLessEqual(cell_width(line), 40, line)


if __name__ == '__main__':
    unittest.main()
