"""The relationship map tells the truth at every size (PKG-UXVIS-1b, part B, items 6 to 13).

The terminal renderer reads part A's fields: a state column that shows a dash where no operation state applies and the
policy's recorded operation word where one does (expired, prepared, none recorded, never "unknown" for a known word);
labels that carry their kind word and never print alike when cut; a filter shown on its assignment; the relationships
the read model listed and the repositories the selection added counted apart; at 60x20 the marker gutter outside the pan
window and a one-line legend and the FOCUS row kept in view, with the stated widths those of the drawn rows; keys named
only where they act; ASCII rows that keep their rail and mean one thing per mark; and the two falsifiers the first
fixture missed. Cases: frame 21 (expired operation and a repository), the seed-510 fixture, two settings sharing a
prefix, two sources under one folder. Temporary directories only.
"""
import re
import unittest

from intune_iac.workbench_tui import cell_width
from plugin_tests.test_workbench_map import ANSI, Fixture

MARK = re.compile(r'\[[x+.:!#?_~o -]\]')
PREFIX = 'device_vendor_msft_policy_config_'


def setting(name):
    return {'relation': 'setting', 'target_id': PREFIX + name, 'details': {}, 'assertion_class': 'observed'}


class MapTruth(Fixture):
    def rows(self, graph=None, width=76, rules='unicode', **kw):
        from intune_iac.workbench_screens import MapLine, map_lines
        lines = map_lines(graph or self.graph(freshness='fresh'), width, rules, **kw)
        return lines, [line for line in lines if isinstance(line, MapLine)]

    def node_row(self, rows, text):
        return next(row for row in rows if text in row and MARK.search(row))


class StateColumnTests(MapTruth):
    def test_a_kind_without_an_operation_shows_a_dash_and_no_state_word(self):
        for rules, dash in (('unicode', '—'), ('ascii', 'n/a')):
            _, rows = self.rows(rules=rules)
            nodes = [row for row in rows if MARK.search(row)]
            self.assertEqual(len(nodes), 9)
            for row in nodes[1:]:
                self.assertIn('[ ]', row)
                self.assertTrue(row.rstrip().endswith(dash), row)
                for word in ('unknown', 'verified', 'queued', 'expired', 'none recorded'):
                    self.assertNotIn(word, row)

    def test_the_policy_shows_the_operation_word_the_read_model_recorded(self):
        for word, mark in (('expired', '~'), ('prepared', 'o'), ('verified', 'x'), ('blocked', '!'), ('dispatched', '?')):
            _, rows = self.rows(self.graph(states={self.object_id: word}))
            policy = rows[0] if MARK.search(rows[0]) else next(row for row in rows if MARK.search(row))
            self.assertIn('[%s]' % mark, policy, word)
            self.assertTrue(policy.rstrip().endswith(word), (word, policy))
        _, rows = self.rows()
        policy = next(row for row in rows if MARK.search(row))
        self.assertIn('[_]', policy)
        self.assertTrue(policy.rstrip().endswith('none recorded'), policy)

    def test_frame_21_an_expired_operation_and_a_repository(self):
        _, rows = self.rows(self.graph(states={self.object_id: 'expired'}, freshness='fresh'))
        policy = next(row for row in rows if MARK.search(row))
        repository = self.node_row(rows, 'repository \u2500\u2192')
        self.assertTrue(policy.rstrip().endswith('expired'))
        self.assertNotIn('unknown', policy + repository)
        self.assertIn('[ ]', repository)

    def test_the_focus_rows_state_the_full_word_and_that_no_state_applies(self):
        graph = self.graph(states={self.object_id: 'succeeded_verified'})
        text = '\n'.join(self.rows(graph)[0])
        self.assertIn('operation succeeded_verified', text)              # cut in the column, whole here
        group = next(node['ref'] for node in graph['nodes'] if node['kind'] == 'group')
        other = '\n'.join(self.rows(graph, focus=group)[0])
        self.assertIn('no operation state', other)

    def test_the_rows_are_one_width_and_the_stated_width_is_the_drawn_width(self):
        from intune_iac.workbench_screens import MAP_WIDTH
        for state in (None, 'expired', 'succeeded_verified'):
            graph = self.graph(states={self.object_id: state} if state else None)
            lines, rows = self.rows(graph, width=60)
            self.assertEqual({cell_width(row) for row in rows if MARK.search(row)}, {MAP_WIDTH}, state)
            statement = next(line for line in lines if 'Left/Right pan' in line)
            self.assertIn('of %d' % MAP_WIDTH, statement)


class LabelTests(MapTruth):
    def test_two_settings_with_a_common_prefix_print_differently_with_their_kind_word(self):
        value = dict(self.value, selected_repository=None,
                     relationships=[setting('privacy_letappsaccesslocation_in_the_workplace'),
                                    setting('privacy_letappsaccesscamera_in_the_workplace')])
        for width in (76, 116):
            _, rows = self.rows(self.graph(value), width=width)
            settings = [row for row in rows if 'setting' in row and MARK.search(row)]
            self.assertEqual(len(settings), 2)
            labels = [re.sub(r'\s+', ' ', row[row.index('→') + 1:] if '→' in row else row) for row in settings]
            self.assertEqual(len(set(labels)), 2, labels)
            self.assertTrue(all('workplace' in label for label in labels), labels)

    def test_a_file_and_a_repository_under_one_folder_are_told_apart_and_name_their_kind(self):
        folder = '/home/nsahm/work/journey 28 run/stacks/dev/components/'
        value = dict(self.value, relationships=[
            {'relation': 'generated_from', 'target_id': folder + 'privacy-pilot.tf', 'details': {}, 'assertion_class': 'historical_local_adoption'}],
            selected_repository={'evidence_class': 'recorded_repository_intent',
                                 'scope': {'repository': folder[:-1], 'stack': 'dev', 'component': 'privacy'}})
        _, rows = self.rows(self.graph(value))
        generated = next(row for row in rows if 'generated' in row and MARK.search(row))
        repository = next(row for row in rows if 'repository' in row and MARK.search(row))
        self.assertIn(' file ', generated)
        self.assertNotIn('source', generated)
        self.assertNotEqual(generated.split('→')[1].strip(), repository.split('→')[1].strip())
        self.assertIn('pilot.tf', generated)
        self.assertTrue(repository.split('→')[1].strip().startswith('—') is False)

    def test_two_nodes_with_one_resolved_name_do_not_print_alike(self):
        a, b = PREFIX + 'privacy_one', PREFIX + 'privacy_two'
        value = dict(self.value, selected_repository=None, relationships=[setting('privacy_one'), setting('privacy_two')])
        _, rows = self.rows(self.graph(value, names={a: 'Shared', b: 'Shared'}))
        settings = [row.split('→')[1].strip() for row in rows if 'setting' in row and MARK.search(row)]
        self.assertEqual(len(set(settings)), 2, settings)


class FilterTests(MapTruth):
    def test_the_filter_is_shown_on_its_assignment_with_its_type(self):
        lines, rows = self.rows(self.graph(freshness='fresh'))
        text = [row.rstrip() for row in rows]
        index = next(i for i, row in enumerate(text) if 'b564fc9a' in row and MARK.search(row))
        self.assertIn('+ filter 5aa36291 include', text[index + 1])
        self.assertFalse(MARK.search(text[index + 1]))
        self.assertEqual(sum('+ filter' in row for row in text), 1)
        # The filter says which assignment it applies to.
        at = next(i for i, row in enumerate(text) if 'filter 5aa36291' in row and MARK.search(row))
        self.assertIn('applies to b564fc9a', text[at + 1])

    def test_ascii_continuation_rows_keep_their_rail_and_a_plus_never_draws_a_branch(self):
        _, rows = self.rows(self.graph(freshness='fresh'), rules='ascii')
        text = [row.rstrip() for row in rows]
        index = next(i for i, row in enumerate(text) if 'b564fc9a' in row and MARK.search(row))
        row, below = text[index], text[index + 1]
        self.assertIn('+ filter 5aa36291 include', below)
        rail = [i for i, char in enumerate(row) if char == '|' and i < 12]
        self.assertTrue(rail and all(below[i] == '|' for i in rail), (row, below))
        for line in text:
            without_marks = MARK.sub('   ', line)
            self.assertNotIn('+-', without_marks, line)
        self.assertTrue(all(ord(char) < 0x80 for line in text for char in line))


class CountTests(MapTruth):
    def test_the_header_counts_relationships_and_repositories_apart_as_the_tree_does(self):
        lines, _ = self.rows()
        header = next(line for line in lines if line.startswith('[MAP]'))
        self.assertIn('7 relationships, 1 repository', header)
        self.assertNotIn('8 edges', header)
        from intune_iac.workbench_screens import relationship_lines
        self.assertTrue(any('7 edges' in line for line in relationship_lines(self.value, 100, 'unicode')))
        none = dict(self.value, relationships=[], selected_repository=None)
        self.assertIn('0 relationships, 0 repositories', next(line for line in self.rows(self.graph(none))[0] if line.startswith('[MAP]')))


class LegendTests(MapTruth):
    MARKS = ('verified', 'running', 'queued', 'waiting', 'blocked', 'failed', 'cancelled', 'unknown', 'expired', 'prepared',
             'none recorded')

    def legend(self, width, **kw):
        """The legend's rows: the pinned rows above the FOCUS rows (one row, or two where the width holds every mark)."""
        from intune_iac.workbench_screens import PinnedRow
        lines, _ = self.rows(width=width, **kw)
        return [str(line) for line in lines if isinstance(line, PinnedRow) and not line.startswith('FOCUS')]

    def test_the_legend_is_one_or_two_rows_that_depend_on_the_width_alone(self):
        for width in (40, 56, 76, 101, 116, 160):
            found = self.legend(width)
            self.assertIn(len(found), (1, 2), width)
            self.assertEqual(sum('> focus' in row for row in found), 1, width)
            self.assertTrue(all(cell_width(row) <= width for row in found), (width, found))
            again = self.legend(width, graph=self.graph(states={self.object_id: 'expired'}))
            self.assertEqual(again, found, 'a state does not change the legend')

    def test_the_legend_never_drops_a_mark_that_can_appear_without_saying_so(self):
        for width in (56, 70, 76, 101, 116, 160):
            legend = ' '.join(self.legend(width))
            missing = [word for word in self.MARKS if word not in legend]
            if missing:
                self.assertIn('? help', legend, (width, missing))
        wide = ' '.join(self.legend(200))
        self.assertTrue(all(word in wide for word in self.MARKS))
        self.assertIn('[ ] — means the kind has no operation state', wide)

    def test_the_help_lists_every_mark(self):
        from intune_iac.workbench_screens import help_lines
        text = ' '.join(' '.join(help_lines(100, map_keys=True)).split())
        for word in self.MARKS:
            self.assertIn(word, text)
        self.assertIn('Home', text)
        self.assertRegex(text, r'Home follow the focused node.s edge to its other end')


class SmallWindowTests(MapTruth):
    def frame_at(self, size=(60, 20), **kw):
        return self.plain(self.workspace(size, **kw))

    def test_at_60x20_the_legend_and_the_focus_row_stay_in_view_wherever_the_focus_is(self):
        ws = self.workspace((60, 20))
        order = ws._map_nodes()
        for target in (0, 3, 5, len(order) - 1):
            ws.map_focus, ws.follow_focus = order[target], True
            rows = self.plain(ws)
            body = [row.strip('│ ').rstrip() for row in rows]
            self.assertEqual(sum('> focus' in row for row in body), 1, target)
            self.assertEqual(sum(row.startswith('FOCUS') for row in body), 1, target)
            self.assertTrue(any(row.startswith('>') and MARK.search(row) for row in body), (target, 'the focused row is in view'))
            for row in rows:
                self.assertLessEqual(cell_width(row), 60, row)

    def test_the_marker_gutter_stays_outside_the_pan_window(self):
        ws = self.workspace((60, 20))
        ws.hscroll = 16
        rows = [row.strip('│').lstrip(' ')[0:0] + row for row in self.plain(ws)]
        body = [row[2:] for row in self.plain(ws) if row.startswith('│')]
        policy = next(row for row in body if MARK.search(row) or row.startswith(' *') or row.startswith('>*'))
        self.assertRegex(policy[:3], r'^[> ][* ] ')
        # Every drawn row starts in the three-cell gutter, and the panned part follows it.
        heads = [row[:3] for row in body if row.strip() and ('─' in row or '→' in row)]
        self.assertTrue(heads)
        self.assertTrue(all(re.fullmatch(r'[> ][* ] ', head) for head in heads), heads)
        self.assertTrue(rows)

    def test_the_pan_statement_names_where_the_state_words_are_and_matches_the_window(self):
        from intune_iac.workbench_screens import MAP_STATE_COLUMN, MAP_WIDTH
        ws = self.workspace((60, 20))
        inside = lambda: ' '.join(' '.join(row.strip('\u2502 ') for row in self.plain(ws)).split())
        text = inside()
        self.assertIn('of %d' % MAP_WIDTH, text)
        self.assertIn('states at %d' % (MAP_STATE_COLUMN + 1), text)
        self.assertIn('showing 1-56', text)
        ws.hscroll = 8
        text = inside()
        self.assertIn('showing 12-64', text)             # the gutter stays; the window moved eight columns

    def test_the_footer_names_left_and_right_only_where_something_pans(self):
        wide = self.plain(self.workspace((120, 40)))[-1]
        self.assertNotIn('Left/Right', wide)
        self.assertIn('Left/Right', self.plain(self.workspace((60, 20)))[-1])
        from intune_iac.workbench_tui import help_line
        for width in range(30, 141, 5):
            for inspect in (True, False):
                for pan in (True, False):
                    line = help_line(width, map_keys=True, inspect=inspect, pan=pan)
                    self.assertLessEqual(cell_width(line), max(width, 1) if width >= 40 else 10 ** 9)
                    self.assertNotRegex(line, r'\bEnter\b(?! inspect)', (width, inspect, pan, line))
                    if not pan:
                        self.assertNotIn('Left/Right', line)

    def test_a_focus_move_replaces_a_stale_notice(self):
        ws = self.workspace((120, 40))
        ws.notice = 'This filter has no inspect route; only a policy opens in the Inspector (2). Nothing was selected or changed.'
        self.keys(ws, ['down', ('text', 'q')])
        self.assertEqual(ws.key_reader.notices[1], 'Viewing Relationships.')      # on screen after Down, before q
        ws.notice = 'Nothing to close. :clear-selection clears the selected policy.'
        self.keys(ws, ['home', ('text', 'q')])
        self.assertEqual(ws.key_reader.notices[1], 'Viewing Relationships.')


class FalsifierTests(MapTruth):
    def test_a_layer_past_its_limit_says_how_many_are_not_drawn_in_the_frame(self):
        from intune_iac.workbench_screens import MAP_LAYER_LIMIT
        extra = [setting('extra_%02d' % index) for index in range(9)]
        value = dict(self.value, relationships=self.value['relationships'] + extra)
        ws = self.workspace((120, 60), value=value)
        text = ' '.join(' '.join(self.plain(ws)).split())
        self.assertIn('%d more not drawn' % (12 - MAP_LAYER_LIMIT), text)
        self.assertEqual(text.count('more not drawn'), 1)

    def test_a_state_change_on_the_policy_changes_only_its_mark_and_word(self):
        def mask(rows):
            masked = []
            for row in rows:
                row = re.sub(r'\[[x+.:!#?_~o -]\] ', '[M] ', row)
                row = re.sub(r'(none recorded|expired|prepared|verified|running|queued|waiting|blocked|failed|cancelled|unknown) *(?=\s│$|\s\|$|$)',
                             'WORD', row)
                row = re.sub(r'operation [^|│]*?(?= \| |  *│|$)', 'operation WORD', row)
                masked.append(row)
            return masked
        for size in ((80, 24), (120, 40), (60, 20)):
            for rules in ('unicode', 'ascii'):
                frames = {word: self.plain(self.workspace(size, rules=rules, state=word))
                          for word in ('queued', 'running', 'blocked', 'expired', 'prepared', 'verified')}
                first = None
                for word, rows in frames.items():
                    body = [row for row in rows if 'FOCUS' not in row and 'Viewing' not in row and 'selected policy' not in row]
                    masked = mask(body)
                    first = first or masked
                    self.assertEqual(len(masked), len(first))
                    self.assertEqual(masked, first, (size, rules, word))
                self.assertEqual(len({tuple(rows) for rows in frames.values()}), len(frames))


if __name__ == '__main__':
    unittest.main()
