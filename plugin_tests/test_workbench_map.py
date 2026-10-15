"""The one-hop relationship map (requirement 17 UX-VIS, first slice, items 3 and 4).

The fixture is the synthetic policy of test_graph_projection (one policy, three groups including an exclusion, one
filter, two scope tags, one repository source). The map is drawn from the typed projection; the falsifiers are the
rendering decision's: the same fixture under five states differs only in the mark and the word, no map line passes
its pane, ASCII carries no byte above 0x7F, colour never carries a state alone, a hostile name is shown escaped, an
unresolved group stays an unresolved identity, there is no map at the minimum size and the screen says so, and the
list, the map, the inspector and the strip name one identifier, before and after a visit to the inspector.
Temporary directories only.
"""
from collections import deque
import io
import re
import tempfile
import unittest

from intune_iac.workbench_tui import cell_width
from plugin_tests.test_graph_projection import synthetic_policy

ANSI = re.compile(r'\x1b\[[0-9;?]*[A-Za-z]')
SIZES = ((80, 24), (120, 40), (200, 50))
STATES = ('queued', 'running', 'blocked', 'unknown', 'verified')
STATE_WORDS = ('queued', 'running', 'waiting', 'blocked', 'failed', 'cancelled', 'unknown', 'verified')
MARK = re.compile(r'\[[x+.:!#?_~o -]\]')
WORD = re.compile(r'\b(%s)( *)' % '|'.join(STATE_WORDS))


def mask(rows):
    """Replace the state mark and the padded state word by a placeholder of the same cells."""
    def word(match):
        spaces = match.group(2)
        need = max(0, 13 - len(match.group(1)))
        return 'S' * 13 + spaces[need:] if len(spaces) >= need else 'X' * len(match.group(1)) + spaces
    return [WORD.sub(word, MARK.sub('[M]', row)) for row in rows]


class Fixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.store, cls.value, cls.truth, cls.policy = synthetic_policy(cls.temp.name)
        cls.object_id = cls.policy['id']

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def graph(self, value=None, **kw):
        from intune_iac.graph_projection import project
        return project(self.value if value is None else value, **kw)

    def workspace(self, size=(80, 24), *, value=None, state=None, rules='unicode', color=False, tab=2, **extra):
        from intune_iac.workbench_tui import Workspace
        value = self.value if value is None else value
        ws = Workspace.__new__(Workspace)
        facts = {'object_id': self.object_id, 'name': value.get('name'), 'observation': 'fresh'}
        if state:
            facts['operation'] = state
        ws.__dict__.update(
            stdout=io.StringIO(), tab=tab, value=value, scroll=0, mode=None, notice='Viewing Relationships.', rules=rules,
            color=color, theme='dark', selected=self.object_id, layer='summary', facts=facts,
            store=type('S', (), {'tenant_id': self.truth['tenant_id']})(), mode_class='synthetic',
            last_command='relationships', size=size, pending=deque(), key_reader=None, rows=[], operation_rows=[],
            operation_highlight=0, highlight=0, active_operation=None, execution_result=None, active_service=None,
            active_adoption=None, active_adoption_plan=None, submission_key='enter', trail=[], current_view=(2, 'relationships'),
            quiet=None, staged=None, _detail_cache=None, buffer='', cursor=0, pasting=False, input_overflow=False,
            view_command='relationships', page_command='overview')
        ws.__dict__.update(extra)
        ws._terminal_size = lambda: ws.size
        return ws

    def frame(self, ws):
        ws.draw()
        text = ws.stdout.getvalue().split('\x1b[H')[-1].replace('\x1b[J', '')
        return text.split('\r\n')

    def plain(self, ws):
        return [ANSI.sub('', row) for row in self.frame(ws)]

    def keys(self, ws, sequence, watch=None):
        """Feed keys to the workspace. notices[i] is the notice on screen when key i was read; watch(i) is called then."""
        class Reader:
            def __init__(self, items): self.items, self.notices = list(items), []
            def read(self):
                self.notices.append(ws.notice)
                if watch: watch(len(self.notices) - 1)
                return self.items.pop(0)
        ws.key_reader = Reader(sequence)
        return ws.input('')


class MapLinesTests(Fixture):
    def lines(self, width=76, rules='unicode', **kw):
        from intune_iac.workbench_screens import map_lines
        return map_lines(self.graph(freshness='fresh'), width, rules, **kw)

    def test_every_map_line_fits_each_pane_and_is_marked_unwrappable(self):
        from intune_iac.workbench_screens import MapLine
        for width in (76, 116, 196):
            rows = [row for row in self.lines(width) if isinstance(row, MapLine)]
            self.assertTrue(rows)
            for row in rows:
                self.assertLessEqual(cell_width(row), width, row)
        # Geometry does not depend on the pane: the same rows at every width.
        self.assertEqual([row for row in self.lines(76) if isinstance(row, MapLine)],
                         [row for row in self.lines(196) if isinstance(row, MapLine)])

    def test_layers_come_in_relation_group_order_and_nodes_are_sorted_by_identifier(self):
        from intune_iac.workbench_screens import RELATION_GROUPS
        text = '\n'.join(self.lines())
        positions = [text.index(heading) for heading, _ in RELATION_GROUPS]
        self.assertEqual(positions, sorted(positions))
        graph = self.graph()
        groups = sorted(node['id'] for node in graph['nodes'] if node['kind'] == 'group')
        shown = [text.index('Unresolved group identity ' + identifier[:8]) for identifier in groups]
        self.assertEqual(shown, sorted(shown))

    def test_node_cells_have_fixed_width_and_the_state_word_is_padded(self):
        from intune_iac.workbench_screens import MapLine
        rows = [row for row in self.lines() if isinstance(row, MapLine) and MARK.search(row)]
        self.assertEqual(len(rows), 9)                 # the policy and its eight neighbours
        from intune_iac.workbench_screens import MAP_STATE_COLUMN
        for row in rows:
            self.assertEqual(cell_width(row), cell_width(rows[0]), row)
        # The policy's recorded word and every other node's dash start in one column.
        self.assertTrue(all(row[MAP_STATE_COLUMN] != ' ' for row in rows), [row[MAP_STATE_COLUMN:] for row in rows])
        self.assertTrue(all(row[MAP_STATE_COLUMN - 1] == ' ' for row in rows))

    def test_a_cut_layer_says_how_many_nodes_are_not_drawn(self):
        from intune_iac.workbench_screens import MAP_LAYER_LIMIT
        extra = [{'relation': 'setting', 'target_id': 'device_vendor_msft_policy_config_setting_%02d' % index,
                  'details': {}, 'assertion_class': 'observed'} for index in range(9)]
        value = dict(self.value, relationships=self.value['relationships'] + extra)
        from intune_iac.workbench_screens import map_lines
        text = '\n'.join(map_lines(self.graph(value), 76, 'unicode'))
        configuration = 2 + 1 + 9                       # two scope tags and the settings
        self.assertIn('%d more not drawn' % (configuration - MAP_LAYER_LIMIT), text)
        self.assertEqual(text.count('more not drawn'), 1)
        # A layer that fits says nothing of the kind.
        self.assertNotIn('not drawn', '\n'.join(self.lines()))

    def test_an_unresolved_group_reads_as_an_unresolved_identity_with_its_identifier(self):
        text = '\n'.join(self.lines())
        groups = [row['group_id'] for row in self.policy['assignments']]
        self.assertEqual(text.count('Unresolved group identity'), 3)
        for identifier in groups:
            self.assertIn('Unresolved group identity ' + identifier[:8], text)
        self.assertNotIn('All Users', text)
        self.assertNotIn('all users', text.lower())

    def test_a_name_the_read_model_resolved_is_shown_for_that_group_only(self):
        from intune_iac.workbench_screens import map_lines
        groups = sorted(row['group_id'] for row in self.policy['assignments'])
        text = '\n'.join(map_lines(self.graph(names={groups[0]: 'Pilot devices'}), 76, 'unicode'))
        self.assertIn('Pilot devices', text)
        self.assertEqual(text.count('Unresolved group identity'), 2)

    def test_names_are_escaped_and_no_control_sequence_reaches_the_lines(self):
        from intune_iac.workbench_screens import map_lines
        hostile = 'Evil \x1b[31mred\x1b[0m \x1b]0;title\x07 \u202egnp'
        value = dict(self.value, name=hostile)
        groups = sorted(row['group_id'] for row in self.policy['assignments'])
        text = '\n'.join(map_lines(self.graph(value, names={groups[0]: 'G\x1b[2Jone'}), 76, 'unicode'))
        for forbidden in ('\x1b', '\x07', '\u202e'):
            self.assertNotIn(forbidden, text)
        self.assertIn('\\u001b[31m', text)
        self.assertIn('\\u001b[2J', text)

    def test_ascii_rules_use_no_byte_above_0x7f(self):
        text = '\n'.join(self.lines(rules='ascii'))
        self.assertTrue(all(ord(char) < 0x80 for char in text), [char for char in text if ord(char) >= 0x80])
        self.assertTrue(any(ord(char) >= 0x80 for char in '\n'.join(self.lines(rules='unicode'))))

    def test_the_legend_depends_only_on_the_width(self):
        for width in (76, 116):
            legends = [[row for row in self.lines(width) if '> focus' in row] for _ in STATES]
            self.assertTrue(all(len(found) == 1 for found in legends))
            self.assertLessEqual(cell_width(legends[0][0]), width)
        text = ' '.join(self.lines(116))
        # One row holds every mark and the no-state word from the width of its text (204 cells); two rows hold them below.
        for word in ('verified', 'running', 'queued', 'waiting', 'blocked', 'failed', 'cancelled', 'unknown'):
            self.assertIn(word, [part for row in self.lines(210) if '> focus' in row for part in row.split()])
        self.assertIn('* selected', text)

    def test_focus_and_selection_are_distinct_marks(self):
        graph = self.graph()
        group = next(node['ref'] for node in graph['nodes'] if node['kind'] == 'group')
        from intune_iac.workbench_screens import map_lines
        rows = [row for row in map_lines(graph, 76, 'unicode', focus=group, selected=self.object_id) if MARK.search(row)]
        marked = [row for row in rows if row.startswith('> ') or row.startswith('>*') or row.startswith(' *')]
        self.assertEqual(sum(row.startswith('>') for row in rows), 1)
        self.assertEqual(sum(row[1] == '*' for row in rows), 1)
        self.assertTrue(rows[0].startswith(' *'), rows[0])                  # the policy: selected, not focused
        self.assertTrue(any(row.startswith('> ') and 'Unresolved group' in row for row in rows))
        self.assertEqual(len(marked), 2)

    def test_the_inspector_rows_name_the_focused_node_exactly_and_its_route(self):
        graph = self.graph(freshness='fresh')
        from intune_iac.workbench_screens import map_lines
        group = next(node for node in graph['nodes'] if node['kind'] == 'group')
        text = '\n'.join(map_lines(graph, 76, 'unicode', focus=group['ref']))
        self.assertIn(group['id'], text)                                    # the whole identifier, not the short one
        self.assertIn('no inspect route', text)
        center = '\n'.join(map_lines(graph, 76, 'unicode'))
        self.assertIn(self.object_id, center)
        self.assertNotIn('no inspect route', center)
        self.assertIn('Enter opens the Inspector', center)


class MapFrameTests(Fixture):
    def test_at_each_size_no_map_line_passes_its_pane_and_none_is_split(self):
        from intune_iac.workbench_screens import MapLine
        for size in SIZES:
            for rules in ('unicode', 'ascii'):
                ws = self.workspace(size, rules=rules, state='verified')
                content = size[0] - 4
                side = '│' if rules == 'unicode' else '|'
                mapped = [row for row in ws._body_lines(content, side) if isinstance(row, MapLine)]
                self.assertGreaterEqual(len(mapped), 12, size)
                rows = self.plain(ws)
                for row in mapped:
                    self.assertLessEqual(cell_width(row), content, (size, row))
                for row in rows:
                    self.assertLessEqual(cell_width(row), size[0], (size, row))
                visible = [row for row in rows if row.startswith(side)]
                for row in mapped[:6]:
                    self.assertTrue(any(candidate.startswith(side + ' ' + row.rstrip()) for candidate in visible), (size, row))

    def test_the_five_states_differ_only_in_the_mark_and_the_word(self):
        for size in SIZES:
            for rules in ('unicode', 'ascii'):
                frames = {state: self.plain(self.workspace(size, rules=rules, state=state)) for state in STATES}
                # The state really changed in the policy's own row ...
                for state, rows in frames.items():
                    policy_row = next(row for row in rows if self.object_id[:8] in row and MARK.search(row) and '*' in row[:6])
                    self.assertIn(state, policy_row, (size, state))
                # The FOCUS row of the policy names its operation word whole; it is a word, so it is masked as one.
                masked = {state: mask([row for row in rows if 'operation ' not in row]) for state, rows in frames.items()}
                first = masked['unknown']
                for state, rows in masked.items():
                    self.assertEqual(rows, first, (size, rules, state))
                self.assertEqual(len({tuple(rows) for rows in frames.values()}), len(STATES))

    def test_the_policy_row_changes_its_mark_with_the_state(self):
        marks = {}
        for state in STATES:
            rows = self.plain(self.workspace((80, 24), state=state))
            row = next(row for row in rows if self.object_id[:8] in row and MARK.search(row))
            marks[state] = MARK.search(row).group(0)
        self.assertEqual(len(set(marks.values())), 5, marks)
        self.assertEqual(marks['verified'], '[x]')
        self.assertEqual(marks['unknown'], '[?]')

    def test_ascii_frames_carry_no_byte_above_0x7f(self):
        for size in SIZES:
            text = '\n'.join(self.frame(self.workspace(size, rules='ascii', state='running')))
            self.assertIn('[MAP]', text)                                       # the map is in the frame being checked
            self.assertTrue(all(ord(char) < 0x80 for char in text), (size, [c for c in text if ord(c) >= 0x80]))

    def test_without_colour_every_state_is_a_word_and_a_mark(self):
        for state in STATES:
            ws = self.workspace((80, 24), state=state, color=False)
            rows = self.frame(ws)
            self.assertFalse(any('\x1b[38;5;' in row for row in rows), 'a colour sequence reached the no-colour frame')
            policy = next(row for row in rows if self.object_id[:8] in row and MARK.search(row))
            self.assertIn(state, policy)
            self.assertIsNotNone(MARK.search(policy))

    def test_colour_only_reinforces_and_changes_no_text(self):
        for state in STATES:
            plain = self.plain(self.workspace((80, 24), state=state, color=False))
            coloured = self.frame(self.workspace((80, 24), state=state, color=True))
            self.assertEqual([ANSI.sub('', row) for row in coloured], plain)
            policy = next(row for row in coloured if self.object_id[:8] in row and MARK.search(ANSI.sub('', row)))
            self.assertIn('\x1b[38;5;', policy)                # the mark is tinted ...
            self.assertIn(state, ANSI.sub('', policy))          # ... and the word is still there

    def test_a_hostile_name_is_shown_escaped_in_the_frame(self):
        hostile = 'Evil \x1b[31mred\x1b[0m'
        ws = self.workspace((120, 40), value=dict(self.value, name=hostile))
        ws.facts['name'] = hostile
        text = '\n'.join(self.frame(ws))
        self.assertIn('[MAP]', text)
        self.assertNotIn('\x1b[31m', text)
        self.assertTrue(any('\\u001b[31m' in row and '(%s)' % self.object_id[:8] in row
                            for row in self.plain(ws)), 'the escaped name is on the policy row of the map')

    def test_at_80x24_the_map_sits_above_the_inspector_with_a_one_row_legend(self):
        rows = self.plain(self.workspace((80, 24), state='verified'))
        text = [row.strip('│ ').rstrip() for row in rows]
        header = next(index for index, row in enumerate(text) if row.startswith('[MAP]'))
        last_edge = max(index for index, row in enumerate(text) if MARK.search(row))
        legend = [index for index, row in enumerate(text) if '> focus' in row]
        focus = [index for index, row in enumerate(text) if row.startswith('FOCUS')]
        self.assertEqual(len(legend), 1)
        self.assertEqual(len(focus), 1)
        self.assertTrue(header < last_edge < min(legend + focus), (header, last_edge, legend, focus))
        self.assertTrue(max(legend + focus) <= len(rows) - 5)              # inside the pane (kept in view at its foot), above the footer

    def test_the_tree_stays_the_canonical_reading_beside_the_map(self):
        ws = self.workspace((120, 60))
        text = '\n'.join(self.plain(ws))
        self.assertIn('[MAP]', text)
        self.assertIn('[TYPED RELATIONSHIPS]', text)
        self.assertLess(text.index('[MAP]'), text.index('[TYPED RELATIONSHIPS]'))

    def test_the_map_is_drawn_at_60x20_with_a_pan_and_not_at_the_minimum(self):
        ws = self.workspace((60, 20))
        text = '\n'.join(self.plain(ws))
        self.assertIn('[MAP]', text)
        self.assertIn('Left/Right pan', text)
        for row in self.plain(ws):
            self.assertLessEqual(cell_width(row), 60, row)
        # At the 40x12 minimum there is no map, and the screen says so.
        ws = self.workspace((40, 12))
        rows = self.plain(ws)
        text = ' '.join(' '.join(rows).split())
        self.assertNotIn('[MAP]', text)
        self.assertFalse(any(MARK.search(row) for row in rows))
        self.assertIn('MAP NOT DRAWN (needs 60x20)', text)
        for row in rows:
            self.assertLessEqual(cell_width(row), 40, row)
        # Below the minimum the constrained view hides every surface and says so.
        constrained = ' '.join(' '.join(self.plain(self.workspace((39, 11)))).split()).lower()
        self.assertNotIn('[map]', constrained)
        self.assertIn('below 40x12', constrained)

    def test_only_the_relationships_surface_shows_a_map(self):
        for tab in (0, 1, 3, 4, 5, 6, 7, 8):
            text = '\n'.join(self.plain(self.workspace((120, 40), tab=tab)))
            self.assertNotIn('[MAP]', text, tab)

    def test_the_footer_and_help_name_the_map_keys_only_with_a_map(self):
        with_map = self.plain(self.workspace((60, 20)))[-1]
        self.assertIn('Left/Right', with_map)                                  # at 60x20 the map pans
        self.assertNotIn('Left/Right', self.plain(self.workspace((120, 40)))[-1])   # at 120x40 nothing does
        self.assertNotIn('Left/Right', self.plain(self.workspace((120, 40), tab=3))[-1])
        self.assertNotIn('Left/Right', self.plain(self.workspace((48, 20)))[-1])
        help_value = {'navigation': [1], 'object_id': None}
        shown = '\n'.join(self.plain(self.workspace((120, 60), tab=7, value=help_value)))
        self.assertIn('Left, Right', shown)
        ws = self.workspace((120, 60), tab=7, value=help_value, selected=None, facts={})
        self.assertNotIn('Left, Right', '\n'.join(self.plain(ws)))
        small = self.workspace((48, 20), tab=7, value=help_value)
        self.assertNotIn('Left, Right', '\n'.join(self.plain(small)))


class MapNavigationTests(Fixture):
    def test_the_footer_names_enter_only_where_the_focused_node_has_a_route(self):
        ws = self.workspace((120, 40))
        self.assertIn('Enter inspect', self.plain(ws)[-1])                 # the policy has an inspect route
        self.keys(ws, ['down', ('text', 'q')])
        self.assertTrue(ws._map_focus().startswith('group:') or ws._map_focus().startswith('filter:'))
        footer = self.plain(ws)[-1]
        self.assertNotIn('Enter', footer)                                    # a key with no route is not drawn
        self.assertNotIn('Left/Right', footer)                               # and a pan that moves nothing is not named
        from intune_iac.workbench_tui import help_line
        for width in (120, 80, 60, 40):
            self.assertNotIn('Enter', help_line(width, map_keys=True, inspect=False))
            self.assertLessEqual(cell_width(help_line(width, map_keys=True, inspect=False)), width)

    def test_a_changed_node_set_is_said_and_the_selection_is_kept(self):
        ws = self.workspace((120, 40))
        self.assertEqual(ws._note_topology(self.value), '')                  # first sight of this object's map
        self.assertEqual(ws._note_topology(self.value), '')                  # nothing changed
        extra = {'relation': 'setting', 'target_id': 'device_vendor_msft_policy_config_extra', 'details': {},
                 'assertion_class': 'observed'}
        more = dict(self.value, relationships=self.value['relationships'] + [extra])
        self.assertEqual(ws._note_topology(more), ' Topology changed: +1, -0 nodes; selection kept.')
        fewer = dict(self.value, relationships=self.value['relationships'][2:])   # the two included groups are gone
        self.assertEqual(ws._note_topology(fewer), ' Topology changed: +0, -3 nodes; selection kept.')
        self.assertEqual(ws.selected, self.object_id)
        # A malformed edge list is counted, not drawn, and is not a change.
        self.assertEqual(ws._note_topology({'object_id': 'x', 'relationships': 'no'}), '')

    def test_up_and_down_visit_every_drawn_node_in_order_and_stop_at_the_ends(self):
        ws = self.workspace((120, 40))
        self.assertEqual(ws._map_nodes()[0], 'policy:' + self.object_id)
        order = ws._map_nodes()
        self.assertEqual(len(order), 9)
        seen = []
        for _ in range(len(order) + 3):
            self.keys(ws, ['down', ('text', 'q')])
            seen.append(ws._map_focus())
        self.assertEqual(seen[:8], order[1:9])
        self.assertEqual(seen[-1], order[-1])                       # stops at the last node
        self.keys(ws, ['up'] * 12 + [('text', 'q')])
        self.assertEqual(ws._map_focus(), order[0])

    def test_home_follows_the_edge_to_its_other_end(self):
        ws = self.workspace((120, 40))
        order = ws._map_nodes()
        self.keys(ws, ['down', 'down', ('text', 'q')])
        self.assertEqual(ws._map_focus(), order[2])
        self.keys(ws, ['home', ('text', 'q')])
        self.assertEqual(ws._map_focus(), order[0])                  # from a neighbour to the policy
        self.keys(ws, ['home', ('text', 'q')])
        self.assertEqual(ws._map_focus(), order[1])                  # from the policy to its first neighbour

    def test_enter_on_a_node_without_an_inspect_route_says_so_and_sends_nothing(self):
        for kind in ('group', 'filter', 'scope_tag', 'setting'):
            ws = self.workspace((120, 40))
            order = ws._map_nodes()
            kind_index = next(index for index, ref in enumerate(order) if ref.startswith(kind + ':'))
            ws.facts['operation'] = 'running'
            command = self.keys(ws, ['down'] * kind_index + ['enter', ('text', 'q')])
            self.assertEqual(command, 'quit', 'Enter on a %s must not send a command' % kind)
            notice = ws.key_reader.notices[-1]                  # on screen after Enter, before q replaced it
            self.assertIn('no inspect route', notice)
            self.assertIn('This %s has' % kind.replace('_', ' '), notice)
            self.assertIn('only a policy opens in the Inspector', notice)
            self.assertEqual(ws.selected, self.object_id)            # nothing was selected or changed
            self.assertEqual(ws._map_focus(), order[kind_index])
            self.assertEqual(ws.tab, 2)

    def test_enter_on_the_policy_opens_the_inspector_by_the_one_existing_route(self):
        ws = self.workspace((120, 40))
        self.assertEqual(self.keys(ws, ['enter']), 'inspect')
        self.assertEqual(ws.tab, 1)
        self.assertEqual(ws.selected, self.object_id)

    def test_leaving_the_map_remembers_the_viewport_for_the_return(self):
        ws = self.workspace((60, 20))
        before = []
        self.keys(ws, ['down', 'down', 'right', 'right', 'pagedown', ('text', '2')],
                  watch=lambda index: before.append((ws._map_focus(), ws.hscroll, ws.scroll)) if index == 5 else None)
        before = before[0]
        self.assertGreater(before[1], 0)
        self.assertGreater(before[2], 0)
        self.assertEqual(ws.tab, 1)
        ws.hscroll, ws.scroll, ws.map_focus = 0, 0, None              # the inspector has its own viewport
        ws.tab = 2
        ws._restore_map_view(self.value)                                # what receive does when the map returns
        self.assertEqual((ws._map_focus(), ws.hscroll, ws.scroll), before)
        # It is restored once, and only for the object it was saved for.
        ws.hscroll = 0
        ws._restore_map_view(self.value)
        self.assertEqual(ws.hscroll, 0)

    def test_keys_that_scroll_elsewhere_still_scroll_outside_a_map(self):
        seen = []
        ws = self.workspace((120, 40), tab=3, value={'object_id': self.object_id, 'history': []})
        ws._data_lines = lambda width: ['row %d' % index for index in range(80)]
        self.keys(ws, ['down', 'down', 'down', ('text', 'q')], watch=lambda index: seen.append(ws.scroll))
        self.assertEqual(seen, [0, 1, 2, 3])
        self.assertEqual(getattr(ws, 'hscroll', 0), 0)


class RealEngineJourneyTests(Fixture):
    """The list, the map, the inspector and the strip name one identifier, before and after a visit to the inspector."""

    def run_keys(self, sequence, size=(120, 40)):
        from intune_iac.workbench import run_terminal
        from intune_iac.workbench_tui import Workspace
        out = io.StringIO()
        ws = Workspace(self.store.root, stdout=out, stdin=io.StringIO())
        ws.rules = 'unicode'
        ws._terminal_size = lambda: size
        frames = []

        class Reader:
            def __init__(self, items): self.items = list(items)
            def read(self):
                frames.append([ANSI.sub('', row) for row in out.getvalue().split('\x1b[H')[-1].replace('\x1b[J', '').split('\r\n')])
                return self.items.pop(0)
        ws.key_reader = Reader(sequence)
        result = run_terminal(self.store.root, input_fn=ws.input, output_fn=lambda line: None, result_fn=ws.receive)
        self.assertEqual(result.get('status'), 'closed')
        return ws, frames

    def short(self, rows):
        return next(row for row in rows if 'POLICY ' in row)

    def test_one_identifier_across_list_map_inspector_and_strip_and_after_a_return(self):
        key = lambda char: ('text', char)
        sequence = [key('1'), 'enter',                 # list, then select the highlighted policy (Inspector)
                    key('1'),                          # the list again, with the selection marked
                    key('3'),                          # the map
                    'enter',                           # the policy node: the Inspector
                    key('b'),                          # return to the map
                    key('q')]
        ws, frames = self.run_keys(sequence)
        selected = ws.selected
        short = selected[:8]
        texts = [' '.join(' '.join(rows).split()) for rows in frames]
        inspector, listing, mapped, inspected, returned = texts[2], texts[3], texts[4], texts[5], texts[6]
        # The strip names it on every surface (the third row of the frame).
        for rows in frames[2:]:
            self.assertIn('(%s)' % short, self.short(rows))
        self.assertIn(selected, inspector)
        self.assertIn('>* ' + selected, listing)                    # the list marks it focused and selected
        self.assertIn('[MAP]', mapped)
        self.assertIn('(%s)' % short, mapped)
        self.assertIn(selected, mapped)                              # the focus rows hold the whole identifier
        self.assertIn(selected, inspected)
        self.assertIn('[MAP]', returned)
        self.assertIn('(%s)' % short, returned)
        self.assertEqual(ws.selected, selected)
        self.assertEqual(ws.tab, 2)
        self.assertTrue(ws.page_command.startswith('overview'))              # the estate scope is as it was
        self.assertNotIn('Topology changed', ws.notice)                      # the same node set came back

    def test_returning_from_the_inspector_restores_the_focus_and_the_viewport(self):
        key = lambda char: ('text', char)
        sequence = [key('1'), 'enter', key('3'), 'down', 'right', 'pagedown', 'home', 'enter', key('b'), key('q')]
        ws, frames = self.run_keys(sequence, size=(60, 20))
        before, after = frames[7], frames[9]          # before Enter on the policy; after the return
        self.assertGreater(ws.hscroll, 0)
        self.assertEqual([row for row in before if row.startswith('│')], [row for row in after if row.startswith('│')])
        self.assertEqual(ws.tab, 2)


if __name__ == '__main__':
    unittest.main()
