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

from intune_iac.workbench_tui import cell_width
from plugin_tests import test_workbench_companion as companion_tests
from plugin_tests.test_workbench_map import MARK
from plugin_tests.test_workbench_map_truth import MapTruth

GENERATED = {'relation': 'generated_from', 'target_id': '/home/nsahm/work/journey 29/generated/22222222-2222-4222-8222-222222222222.tf',
             'details': {}, 'assertion_class': 'historical_local_adoption'}


class MapCase(MapTruth):
    def legend_rows(self, width, rules='unicode', **kw):
        """The legend's rows: the pinned rows above the FOCUS rows."""
        from intune_iac.workbench_screens import PinnedRow
        lines, _ = self.rows(width=width, rules=rules, **kw)
        return [str(line) for line in lines if isinstance(line, PinnedRow) and not line.startswith('FOCUS')]


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
            self.assertTrue(all(row.endswith(('—', 'n/a', 'none recorded')) for row in mapped), mapped)

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


class PageTruthTests(MapTruth):
    """Item 4: the page says what the map says about the filter and the policy state, names the live command and lists
    the pan keys only where something pans."""

    def page(self, value=None, **kw):
        from intune_iac.companion_page import render_page
        return render_page(self.graph(self.value if value is None else value, **kw), mode_class='synthetic_local_process_only',
                           tenant=self.truth['tenant_id'], observed_at='2026-10-15T12:00:00Z')

    def section(self, text, ident):
        from plugin_tests.test_companion_page import section
        return section(text, ident)

    def test_the_legend_says_a_filter_applies_to_one_assignment_not_to_the_policy(self):
        from intune_iac.companion_page import EDGE_STYLES
        legend = self.section(self.page(), 'legend')
        meaning = EDGE_STYLES['filter']['meaning']
        self.assertIn('one assignment', meaning)
        self.assertIn('applies to', meaning)
        self.assertNotIn('applies to the policy', meaning)
        self.assertNotIn('applies to the policy', legend)
        self.assertIn(meaning, legend.replace('&quot;', '"'))

    def test_every_relation_has_its_own_line_pattern_in_the_legend_and_in_the_drawing(self):
        from intune_iac.companion_page import EDGE_STYLES, _swatch
        dashes = [style['dash'] for style in EDGE_STYLES.values()]
        swatches = [_swatch(dash) for dash in dashes]
        self.assertEqual(len(set(dashes)), len(dashes), dashes)
        self.assertEqual(len(set(swatches)), len(swatches), dict(zip(EDGE_STYLES, swatches)))
        self.assertNotEqual(_swatch(EDGE_STYLES['filter']['dash']), _swatch(EDGE_STYLES['generated_from']['dash']))
        legend = self.section(self.page(), 'legend')
        for swatch in swatches:
            self.assertEqual(legend.count('<span class="swatch">%s</span>' % swatch), 1, swatch)

    def test_the_page_states_the_policy_operation_as_the_map_does_and_never_workbench_state_unknown(self):
        from intune_iac.workbench_screens import map_lines
        for state in (None, 'expired', 'prepared', 'succeeded_verified', 'dispatched', 'running'):
            graph = self.graph(states={self.object_id: state} if state else None, freshness='fresh')
            page = self.page(states={self.object_id: state} if state else None, freshness='fresh')
            policy = next(node for node in graph['nodes'] if node['kind'] == 'policy')
            first = self.section(page, 'detail-list').split('</li>')[0]
            self.assertIn('operation %s' % policy['operation'], first, state)
            self.assertNotIn('workbench state', page, state)
            self.assertNotIn('workbench state unknown', page)
            map_text = ' '.join(map_lines(graph, 100, 'unicode'))
            self.assertIn('operation %s' % policy['operation'], map_text, state)
        # The page and the map say the same two things of the common case: nothing is recorded, and nothing else is claimed.
        none = self.section(self.page(), 'detail-list').split('</li>')[0]
        self.assertIn('operation none recorded (recorded by the read model)', none)
        self.assertNotIn('unknown', none)

    def test_use_live_mode_names_the_command(self):
        page = self.page()
        status = self.section(page, 'live')
        self.assertIn('use live mode', status)
        for part in ('from a shell', 'workbench companion', '--serve', 'instead of --out'):
            self.assertIn(part, status)
        # The live page does not ask for a mode it already has.
        live = self.page_live()
        self.assertNotIn('use live mode', self.section(live, 'live'))

    def page_live(self):
        from intune_iac.companion_page import render_page
        return render_page(self.graph(freshness='fresh'), mode_class='synthetic_local_process_only', observed_at='2026-10-15T12:00:00Z',
                           live={'snapshot': 'snapshot', 'poll_seconds': 3, 'idle_seconds': 1800})

    def test_the_pan_keys_are_listed_only_while_the_drawing_is_zoomed_in(self):
        for page in (self.page(), self.page_live()):
            keys = self.section(page, 'keys')
            item = re.search(r'<li id="key-pan"([^>]*)>([^<]*)</li>', keys)
            self.assertIsNotNone(item, keys)
            self.assertIn('hidden', item.group(1), 'at 100% the whole drawing is in view and nothing pans')
            self.assertIn('Left, Right, Page Up, Page Down', item.group(2))
            self.assertIn('zoomed', item.group(2))
            script = page.split('<script>')[1]
            # The script shows the line when the zoom level is above 100% and hides it again at 100%.
            self.assertRegex(script, r"getElementById\('key-pan'\)")
            self.assertRegex(script, r'panKey\.hidden = level === 0')


class LegendTests(MapCase):
    """Item 5: where the legend has room it names every mark it shows and what the no-state word means; narrower forms
    say where the rest are listed, and the help lists them. The text depends on the width (and the rules), never a state."""
    MARKS = ('verified', 'running', 'queued', 'waiting', 'blocked', 'failed', 'cancelled', 'unknown', 'expired', 'prepared',
             'none recorded')

    def test_where_it_fits_the_legend_names_each_mark_and_says_what_the_dash_means(self):
        for width in (116, 160, 196):
            rows = self.legend_rows(width)
            self.assertLessEqual(len(rows), 2, (width, rows))
            text = ' '.join(rows)
            for word in self.MARKS:
                self.assertIn(word, text, (width, word))
            self.assertRegex(text, r'\[ \] — means the kind has no operation state')
            self.assertIn('> focus * selected', text)

    def test_at_120_columns_the_legend_is_two_rows_and_at_80_one(self):
        self.assertEqual(len(self.legend_rows(116)), 2)
        self.assertEqual(len(self.legend_rows(76)), 1)
        self.assertEqual(len(self.legend_rows(210)), 1)

    def test_every_width_gives_rows_that_fit_and_a_form_that_is_honest_about_what_it_leaves_out(self):
        for rules in ('unicode', 'ascii'):
            for width in range(56, 210, 3):
                rows = self.legend_rows(width, rules)
                text = ' '.join(rows)
                place = (rules, width, rows)
                self.assertTrue(rows, place)
                self.assertTrue(all(cell_width(row) <= width for row in rows), place)
                missing = [word for word in self.MARKS if word not in text]
                if missing:
                    self.assertIn('? help', text, place)
                self.assertNotIn('named beside each node', text, place)
                self.assertEqual(sum('> focus' in row for row in rows), 1, place)
                if width >= 76:
                    # Wide enough for one row that says what a no-state row means.
                    self.assertIn('no operation state', text, place)

    def test_the_legend_depends_on_the_width_and_the_rules_never_on_a_state(self):
        for rules in ('unicode', 'ascii'):
            for width in (56, 76, 101, 116, 160, 200):
                base = self.legend_rows(width, rules)
                for word in ('expired', 'prepared', 'succeeded_verified', 'dispatched'):
                    again = self.legend_rows(width, rules, graph=self.graph(states={self.object_id: word}, freshness='fresh'))
                    self.assertEqual(again, base, (rules, width, word))

    def test_the_legend_defines_the_word_the_rows_show_for_no_state(self):
        from intune_iac.workbench_screens import MAP_NO_STATE
        for rules in ('unicode', 'ascii'):
            self.assertIn('[ ] %s means the kind has no operation state' % MAP_NO_STATE[rules], ' '.join(self.legend_rows(116, rules)))
            lines, rows = self.rows(rules=rules, width=116)
            self.assertTrue(any(row.rstrip().endswith(MAP_NO_STATE[rules]) for row in rows))

    def test_the_help_lists_every_mark_the_legend_leaves_to_it_and_the_no_state_words(self):
        from intune_iac.workbench_screens import help_lines
        text = ' '.join(' '.join(help_lines(100, map_keys=True)).split())
        for word in self.MARKS:
            self.assertIn(word, text)
        self.assertRegex(text, r'\[ \] with — \((--|n/a)[^)]*\) means the kind has no operation state')


class AsciiTests(MapCase):
    """Item 6: ASCII keeps every open rail on a typed-tree continuation line, and its no-state word is not a drawing
    character."""
    TO_ASCII = (('├── ', '|-- '), ('└── ', '`-- '), ('│   ', '|   '))

    def ascii_of(self, line):
        for old, new in self.TO_ASCII:
            line = line.replace(old, new)
        return line

    def test_the_typed_tree_in_ascii_is_the_unicode_tree_with_ascii_rails(self):
        from intune_iac.workbench_screens import relationship_lines
        for width in (60, 100, 116):
            unicode_rows = relationship_lines(self.value, width, 'unicode')
            ascii_rows = relationship_lines(self.value, width, 'ascii')
            self.assertEqual([self.ascii_of(row) for row in unicode_rows], ascii_rows, width)
        # Frame 18 line 27: the filter identifier wraps under its assignment, and the rail of the open branch carries on.
        rows = relationship_lines(self.value, 100, 'ascii')
        index = next(i for i, row in enumerate(rows) if row.startswith('  |-- assignment') and 'filter include' in row)
        self.assertRegex(rows[index + 1], r'^  \|   +5aa36291-9c32-5f60-b5ef-a48382c20714$')
        self.assertTrue(all(ord(char) < 0x80 for row in rows for char in row))

    def test_the_last_branch_of_a_group_leaves_no_rail_behind_it(self):
        from intune_iac.workbench_screens import relationship_lines
        value = dict(self.value, relationships=[
            {'relation': 'setting', 'target_id': 'device_vendor_msft_policy_config_' + 'x' * 120, 'details': {}, 'assertion_class': 'observed'}],
            selected_repository=None)
        rows = relationship_lines(value, 60, 'ascii')
        index = next(i for i, row in enumerate(rows) if row.startswith('  `-- setting'))
        self.assertTrue(rows[index + 1].startswith('      '), rows[index:index + 3])
        self.assertEqual([self.ascii_of(row) for row in relationship_lines(value, 60, 'unicode')], rows)

    def test_the_no_state_word_is_not_a_drawing_character_in_ascii(self):
        from intune_iac.workbench_screens import MAP_NO_STATE
        self.assertEqual(MAP_NO_STATE['unicode'], '—')
        self.assertEqual(MAP_NO_STATE['ascii'], 'n/a')
        _, rows = self.rows(rules='ascii')
        nodes = [row for row in rows if MARK.search(row)]
        self.assertEqual(len(nodes), 9)
        for row in nodes[1:]:
            self.assertTrue(row.rstrip().endswith(' n/a'), row)
        for row in rows:
            self.assertNotIn('--', row, 'no map row has a double dash: it was both a branch and the no-state word')
        self.assertTrue(all(ord(char) < 0x80 for row in rows for char in row))

    def test_the_ascii_legend_and_help_define_the_word_the_rows_show(self):
        from intune_iac.workbench_screens import help_lines
        for width in (76, 116, 196):
            legend = ' '.join(self.legend_rows(width, 'ascii'))
            self.assertIn('n/a means', legend)
            self.assertNotIn('--', legend)
        help_text = ' '.join(' '.join(help_lines(100, map_keys=True)).split())
        self.assertIn('(n/a in ASCII)', help_text)


class CompanionEntryTests(companion_tests.Fixture):
    """Lower weight: the focused companion entry shows its command row, as the focused entry 1 does."""

    def lines(self, focus):
        from intune_iac.workbench import _inspection, _store
        from intune_iac.workbench_screens import actions_lines
        actions = _inspection(_store(self.root), self.object_id, attention=True)['actions']
        return actions, [line.strip() for line in actions_lines(actions, focus, 116, name='Privacy pilot 3', object_id=self.object_id)]

    def test_the_focused_companion_entry_shows_its_command_and_what_it_needs(self):
        actions, _ = self.lines(0)
        last = len(actions) - 1
        self.assertEqual(actions[last]['kind'], 'companion')
        _, rows = self.lines(last)
        self.assertIn('command  companion FILE', rows)
        self.assertTrue(any(row.startswith('needs  FILE') for row in rows), rows)
        # Unfocused, it keeps the short form, as every other available entry does.
        _, others = self.lines(0)
        self.assertNotIn('command  companion FILE', others)
        self.assertIn('needs  FILE', others)

    def test_every_focused_available_entry_shows_a_command_row(self):
        actions, _ = self.lines(0)
        for index, action in enumerate(actions):
            if action['available']:
                _, rows = self.lines(index)
                self.assertTrue(any(row.startswith('command  ') for row in rows), (action['kind'], rows))


class HelpTests(MapCase):
    """Lower weight: the help says which order the map and the tree use, and what the narrowest strip's letters mean."""

    def text(self, **kw):
        from intune_iac.workbench_screens import help_lines
        return ' '.join(' '.join(help_lines(100, **kw)).split())

    def test_the_help_says_which_order_the_map_and_the_tree_use(self):
        text = self.text(map_keys=True)
        self.assertIn('the map draws the layers in the order of the tree below (targeting, configuration, source and '
                      'lineage) and sorts each layer by identifier; the tree lists each group as the read model gives it', text)
        self.assertNotIn('the map draws the layers', self.text())

    def test_the_help_says_what_t_and_p_mean_in_the_narrowest_strip(self):
        from intune_iac.workbench_screens import context_strip
        strip = context_strip('029c33b1-0000-4000-8000-000000000000', 'd665d54b-72e5-5184-9ac0-4486d72ad1ae',
                              {'name': 'Privacy pilot 3', 'observation': 'fresh'}, 40, 'synthetic')
        self.assertRegex(strip, r'\| T [0-9a-f]{8} \| P [0-9a-f]{8}')
        self.assertIn('T stands for TENANT and P for POLICY', self.text())
        self.assertIn('T stands for TENANT and P for POLICY', self.text(map_keys=True))


if __name__ == '__main__':
    unittest.main()
