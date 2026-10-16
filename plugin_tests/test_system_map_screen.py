"""The system map's renderer, plain text and JSON (requirement 17 UX-VIS, PKG-UXVIS-6B).

`intune_iac.system_map_screen` draws a `system-map/1` snapshot and nothing else. The cases build snapshots with the real
projection (from the projection tests' reads, one changed record at a time) and then look at the rows: the words, the
widths, the coordinates and the controls. The golden fixtures in `plugin_tests/fixtures/system_map/` freeze the JSON form,
one per scenario, each with its expected revision and the sha256 of its canonical body.
"""
import copy
import hashlib
import json
import pathlib
import re
import unicodedata
import unittest

from plugin_tests import test_system_map_projection as proj

FIXTURES = pathlib.Path(__file__).parent / 'fixtures' / 'system_map'
SIZES = ((120, 40), (80, 24), (60, 20))
SMALL = (40, 12)
ALL_SIZES = SIZES + (SMALL,)
MODES = [(colour, unicode) for colour in (False, True) for unicode in (False, True)]
SGR = re.compile(r'\x1b\[[0-9;]*m')
# Every kind of character a recorded name could use to act on a terminal or to start a row of its own.
HOSTILE = ('a\x1b[31mb\rc\nd\x07e\x85f' + chr(0x2028) + 'g' + chr(0x2029) + 'h\x9bi\x1b]0;t\x07j')
LONG = 'segment-' * 30


def screen():
    from intune_iac import system_map_screen
    return system_map_screen


def snap(read):
    return proj.project(read)


def recorded():
    return snap(proj.with_adoption(proj.operation_read('verified')))


def stale_link():
    # The repository moved on: the component's reading of the intent is stale, so the link that cites it is stale, while the
    # backend node (named by the same intent) stays recorded.
    return snap(proj.with_intent(proj.baseline(), status='changed'))


def unknown_observation():
    read = proj.baseline()
    read['states']['observation'] = None
    return snap(read)


def absent_edges():
    read = proj.without_intent(proj.baseline())
    read['states']['observation'] = None
    return snap(read)


def half_engine_pin():
    read = proj.baseline()
    del read['setup_pins']['pinned']['engine_version']
    return snap(read)


def unsupported_schema():
    return dict(recorded(), schema_version='system-map/2')


SCENARIOS = {'recorded': recorded, 'stale_link': stale_link, 'unknown_observation': unknown_observation,
             'absent_edges': absent_edges, 'half_engine_pin': half_engine_pin, 'unsupported_schema': unsupported_schema}


def hostile():
    """A policy whose every recorded name is long and full of controls."""
    read = proj.baseline()
    read['object_id'] = 'policy-' + HOSTILE + LONG
    read['name'] = HOSTILE + LONG
    read['states']['intent']['scope'] = {'repository': '/repo', 'stack': HOSTILE + LONG, 'component': LONG + HOSTILE,
                                         'backend': HOSTILE + LONG}
    read['states']['intent']['source_revision'] = HOSTILE + LONG
    read['states']['observation']['evidence_class'] = HOSTILE + LONG
    read['repository_record']['sources'] = [{'path': HOSTILE + LONG}, {'path': LONG}]
    read['setup_pins']['pinned']['engine'] = HOSTILE
    read['setup_pins']['pinned']['provider_source'] = LONG + HOSTILE
    read['setup_pins']['integration_label'] = HOSTILE + LONG
    return snap(read)


def plain(rows):
    return [SGR.sub('', row) for row in rows]


def asciified(rows):
    """Unicode rows in their ASCII spelling: the glyphs differ and the words do not."""
    return [row.replace('├─', '|-').replace('→ ', '->').replace('…', '...') for row in rows]


def width_of(row):
    from intune_iac.workbench_tui import cell_width
    return cell_width(row)


def controls_in(rows):
    return [char for row in rows for char in row if unicodedata.category(char)[0] == 'C' or unicodedata.category(char) in ('Zl', 'Zp')]


def node_row(rows, snapshot, identifier):
    label = screen().LABELS[identifier]
    found = next((row for row in rows if ('|- ' + label + ' ') in row or ('├─ ' + label + ' ') in row
                  or row.rstrip().endswith('|- ' + label)), None)
    if found is None:
        raise AssertionError('no row draws the node %s' % identifier)
    return found


def positions(rows, snapshot):
    out = {}
    for node in snapshot['nodes']:
        row = node_row(rows, snapshot, node['id'])
        out[node['id']] = (rows.index(row), row.index(screen().LABELS[node['id']]))
    return out


class UnavailableTests(unittest.TestCase):
    BAD = {
        'not a mapping': lambda: ['nodes'],
        'another schema': unsupported_schema,
        'no schema': lambda: {key: value for key, value in recorded().items() if key != 'schema_version'},
        'no nodes': lambda: dict(recorded(), nodes=[]),
        'a node state the map does not define': lambda: _set_node(recorded(), 'service', state='current'),
        'a node with no state': lambda: _set_node(recorded(), 'service', state=None),
        'a node in no boundary': lambda: _set_node(recorded(), 'service', boundary='elsewhere'),
        'a node with no layer': lambda: _set_node(recorded(), 'service', layer=None),
        'an edge state the map does not define': lambda: _set_edge(recorded(), 0, state='fresh'),
        'an edge type the map does not define': lambda: _set_edge(recorded(), 0, type='infers'),
        'an edge to a node the map lacks': lambda: _set_edge(recorded(), 0, to='nowhere'),
    }

    def test_each_invalid_snapshot_is_an_explicit_unavailable_result_with_its_reason_and_draws_no_node(self):
        for name, build in self.BAD.items():
            for size in ALL_SIZES:
                rows = screen().render(build(), size[0], size[1], colour=False, unicode=False)
                joined = ' '.join(rows)
                self.assertTrue(rows and rows[0].startswith('System map unavailable: '), (name, size, rows))
                self.assertGreater(len(joined), len('System map unavailable: ') + 8, (name, size))
                for label in screen().LABELS.values():
                    self.assertNotIn('|- ' + label, joined, (name, size))
                self.assertTrue(all(width_of(row) <= size[0] for row in rows), (name, size))

    def test_the_text_and_json_forms_say_the_same_instead_of_a_partial_map(self):
        for name, build in self.BAD.items():
            rows = screen().text(build(), 80)
            self.assertTrue(rows and rows[0].startswith('System map unavailable: '), (name, rows))
            payload = json.loads(screen().to_json(build()))
            self.assertIs(payload['available'], False, name)
            self.assertEqual(payload['schema_version'], 'system-map-unavailable/1')
            self.assertTrue(payload['reason'], name)
            self.assertNotIn('nodes', payload, name)

    def test_the_unsupported_schema_is_named_in_its_reason(self):
        rows = screen().render(unsupported_schema(), 80, 24, colour=False, unicode=False)
        self.assertIn('system-map/2', ' '.join(rows))
        self.assertEqual(json.loads(screen().to_json(unsupported_schema())).get('received_schema_version'), 'system-map/2')


def _set_node(snapshot, identifier, **changes):
    snapshot = copy.deepcopy(snapshot)
    next(node for node in snapshot['nodes'] if node['id'] == identifier).update(changes)
    return snapshot


def _set_edge(snapshot, index, **changes):
    snapshot = copy.deepcopy(snapshot)
    snapshot['edges'][index].update(changes)
    return snapshot


class HelperTests(unittest.TestCase):
    def test_the_presentation_helpers_are_the_ones_the_workbench_owns_and_neither_owner_imports_the_renderer(self):
        from intune_iac import workbench_screens, workbench_tui
        module = screen()
        for name in ('safe_text', 'cell_width', 'clip', 'pad'):
            self.assertIs(getattr(module, name), getattr(workbench_tui, name), name)
        self.assertIs(module.word_wrap, workbench_screens.word_wrap)
        for owner in ('workbench_screens.py', 'workbench_tui.py', 'system_map_projection.py'):
            source = (pathlib.Path(module.__file__).parent / owner).read_text(encoding='utf-8')
            self.assertNotIn('system_map_screen', source, owner)


class PlacementTests(unittest.TestCase):
    def test_every_node_has_the_same_coordinates_in_every_scenario(self):
        base = None
        for unicode in (False, True):
            for name in ('recorded', 'stale_link', 'unknown_observation', 'absent_edges', 'half_engine_pin'):
                snapshot = SCENARIOS[name]()
                rows = screen().render(snapshot, 120, 40, colour=False, unicode=unicode)
                found = positions(rows, snapshot)
                base = base or found
                self.assertEqual(found, base, (name, unicode))

    def test_a_changed_state_changes_the_word_and_never_the_coordinates(self):
        snapshot = recorded()
        before = positions(screen().render(snapshot, 80, 24, colour=False, unicode=False), snapshot)
        for state in ('recorded', 'configured', 'not_configured', 'unknown', 'stale', 'unverified'):
            changed = copy.deepcopy(snapshot)
            for node in changed['nodes']:
                node['state'] = state
            rows = screen().render(changed, 80, 24, colour=False, unicode=False)
            self.assertEqual(positions(rows, changed), before, state)
            for node in changed['nodes']:
                self.assertIn(screen().STATE_WORDS[state], node_row(rows, changed, node['id']))

    def test_an_edge_moves_no_node(self):
        snapshot = recorded()
        before = positions(screen().render(snapshot, 80, 24, colour=False, unicode=False), snapshot)
        for edges in ([], snapshot['edges'][:1], list(reversed(snapshot['edges']))):
            changed = dict(snapshot, edges=edges)
            self.assertEqual(positions(screen().render(changed, 80, 24, colour=False, unicode=False), changed), before)

    def test_the_layer_sets_the_indent_the_list_order_sets_the_row_and_the_boundary_the_tag(self):
        snapshot = recorded()
        rows = screen().render(snapshot, 120, 40, colour=False, unicode=False)
        base = positions(rows, snapshot)
        deeper = _set_node(snapshot, 'provider', layer=snapshot['nodes'][4]['layer'] + 1)
        moved = positions(screen().render(deeper, 120, 40, colour=False, unicode=False), deeper)
        self.assertEqual(moved['provider'][0], base['provider'][0])
        self.assertEqual(moved['provider'][1], base['provider'][1] + 2)
        self.assertEqual({key: value for key, value in moved.items() if key != 'provider'},
                         {key: value for key, value in base.items() if key != 'provider'})
        order = [index for index, _ in sorted(((node['id'], base[node['id']][0]) for node in snapshot['nodes']),
                                              key=lambda pair: pair[1])]
        self.assertEqual(order, [node['id'] for node in snapshot['nodes']])
        tag = lambda changed: node_row(screen().render(changed, 120, 40, colour=False, unicode=False), changed, 'service')[2]
        self.assertEqual(tag(snapshot), 'C')
        self.assertEqual(tag(_set_node(snapshot, 'service', boundary='host')), 'H')


class EdgeTests(unittest.TestCase):
    def edge_rows(self, rows):
        # An edge row starts with its source node's lower-case label; a node row starts with its boundary's capital letter.
        return [row for row in rows if re.match(r'  [a-z]', row) and ' -> ' in row]

    def test_only_the_supplied_edges_are_drawn(self):
        for name in ('recorded', 'stale_link', 'absent_edges', 'unknown_observation'):
            snapshot = SCENARIOS[name]()
            rows = screen().render(snapshot, 120, 40, colour=False, unicode=False)
            self.assertEqual(len(self.edge_rows(rows)), len(snapshot['edges']), name)
        absent = absent_edges()
        self.assertEqual(absent['edges'], [])
        self.assertIn('no link is recorded', ' '.join(screen().render(absent, 80, 24, colour=False, unicode=False)))

    def test_a_stale_link_reads_stale_beside_a_recorded_endpoint(self):
        snapshot = stale_link()
        nodes = {node['id']: node for node in snapshot['nodes']}
        edges = {edge['id']: edge for edge in snapshot['edges']}
        self.assertEqual(nodes['tofu.backend']['state'], 'recorded')
        self.assertEqual(edges['cites:atmos.component>tofu.backend']['state'], 'stale')
        rows = screen().render(snapshot, 80, 24, colour=False, unicode=False)
        self.assertIn('recorded', node_row(rows, snapshot, 'tofu.backend'))
        link = next((row for row in self.edge_rows(rows) if row.split()[0] == 'atmos' and 'backend' in row), '')
        self.assertTrue(link, 'no row draws the link from atmos to backend')
        self.assertIn('stale', link)
        self.assertNotIn('recorded', link)

    def test_each_edge_row_carries_its_type_and_state_and_the_wide_form_its_basis(self):
        snapshot = recorded()
        rows = screen().render(snapshot, 120, 40, colour=False, unicode=False)
        for edge, row in zip(snapshot['edges'], self.edge_rows(rows)):
            self.assertIn(edge['type'], row)
            self.assertIn(screen().STATE_WORDS[edge['state']], row)
            self.assertIn(edge['basis']['record'], row)

    def test_the_focused_node_lists_its_links_with_their_basis(self):
        snapshot = recorded()
        rows = screen().render(snapshot, 120, 40, colour=False, unicode=False, focus='atmos.component')
        links = [row for row in rows if row.startswith('link')]
        self.assertEqual(len(links), len([e for e in snapshot['edges'] if 'atmos.component' in (e['from'], e['to'])]))
        joined = ' '.join(rows)
        self.assertIn('repository_intent', joined)
        self.assertIn('adoption', joined)


class SizeTests(unittest.TestCase):
    def test_the_map_is_drawn_whole_at_the_three_sizes(self):
        for name in ('recorded', 'stale_link', 'unknown_observation', 'half_engine_pin'):
            snapshot = SCENARIOS[name]()
            for size in SIZES:
                for colour, unicode in MODES:
                    rows = plain(screen().render(snapshot, size[0], size[1], colour=colour, unicode=unicode))
                    where = (name, size, colour, unicode)
                    self.assertLessEqual(len(rows), size[1], where)
                    self.assertTrue(all(width_of(row) <= size[0] for row in rows), where)
                    self.assertTrue(rows and rows[0].startswith('[SYSTEM MAP]'), where)
                    for node in snapshot['nodes']:
                        row = node_row(asciified(rows), snapshot, node['id'])
                        self.assertIn(screen().STATE_WORDS[node['state']], row, where)
                    self.assertTrue(any(screen().HAZARD in row for row in rows), where)
                    self.assertTrue(any('H this host' in row and 'C the cloud' in row for row in rows), where)

    def test_the_focused_node_shows_its_state_reason_basis_and_where_enter_goes(self):
        snapshot = half_engine_pin()
        rows = screen().render(snapshot, 120, 40, colour=False, unicode=False, focus='tofu.engine')
        joined = '\n'.join(rows)
        self.assertIn('FOCUS opentofu | unknown | reason engine_pin_incomplete | Enter opens nothing', joined)
        self.assertIn('integration_manifest', joined)
        self.assertTrue(node_row(rows, snapshot, 'tofu.engine').startswith('> '))
        self.assertTrue(node_row(rows, snapshot, 'repo.source').startswith('  '))

    def test_a_node_that_opens_a_surface_names_it(self):
        rows = screen().render(recorded(), 120, 40, colour=False, unicode=False, focus='repo.source')
        self.assertIn('Enter opens 9 Repository', '\n'.join(rows))

    def test_a_focus_the_map_does_not_hold_falls_back_to_the_first_node(self):
        rows = screen().render(recorded(), 120, 40, colour=False, unicode=False, focus='nothing')
        self.assertIn('FOCUS repository', '\n'.join(rows))

    def test_at_40x12_there_is_no_map_and_the_sentence_names_the_plain_text_route(self):
        snapshot = recorded()
        for colour, unicode in MODES:
            rows = screen().render(snapshot, 40, 12, colour=colour, unicode=unicode)
            joined = ' '.join(rows)
            self.assertIn('The system map needs a larger window (at least 60x20). Plain text:', joined)
            self.assertIn('intune-iac workbench system-map --root ROOT --policy ID', ' '.join(row.rstrip(' \\').strip() for row in rows))
            self.assertLessEqual(len(rows), 12)
            self.assertTrue(all(width_of(row) <= 40 for row in rows))
            for label in screen().LABELS.values():
                self.assertNotIn('|- ' + label, joined)
        # Short in either direction is no room: 59 columns or 19 rows is the same sentence.
        for size in ((59, 24), (80, 19)):
            self.assertIn('needs a larger window', ' '.join(screen().render(snapshot, size[0], size[1], colour=False, unicode=False)))


class ModeTests(unittest.TestCase):
    def test_ascii_and_unicode_say_the_same_words_and_ascii_is_only_ascii(self):
        for name in ('recorded', 'stale_link', 'unknown_observation', 'half_engine_pin'):
            snapshot = SCENARIOS[name]()
            for size in SIZES:
                ascii_rows = screen().render(snapshot, size[0], size[1], colour=False, unicode=False)
                unicode_rows = screen().render(snapshot, size[0], size[1], colour=False, unicode=True)
                self.assertEqual(asciified(unicode_rows), ascii_rows, (name, size))
                self.assertTrue(all(ord(char) < 128 for row in ascii_rows for char in row), (name, size))
                self.assertTrue(any(ord(char) > 127 for row in unicode_rows for char in row), (name, size))

    def test_colour_changes_no_word_and_no_width_and_adds_nothing_but_a_style_around_a_state_word(self):
        snapshot = stale_link()
        for size in SIZES:
            for unicode in (False, True):
                bare = screen().render(snapshot, size[0], size[1], colour=False, unicode=unicode)
                coloured = screen().render(snapshot, size[0], size[1], colour=True, unicode=unicode)
                self.assertEqual(plain(coloured), bare, size)
                self.assertFalse(any('\x1b' in row for row in bare), size)
                self.assertTrue(any('\x1b' in row for row in coloured), size)
                self.assertFalse(any('\x1b' in row for row in plain(coloured)), size)
                styled = [match for row in coloured for match in re.findall(r'\x1b\[[0-9;]*m([^\x1b]*)\x1b\[0m', row)]
                self.assertTrue(styled)
                self.assertTrue(all(word in screen().STATE_WORDS.values() for word in styled), styled)

    def test_the_text_form_has_no_colour_and_no_glyph_beyond_ascii(self):
        rows = screen().text(stale_link(), 100)
        self.assertTrue(all(ord(char) < 128 for row in rows for char in row))


class TextTests(unittest.TestCase):
    def test_the_text_form_lists_every_node_and_edge_in_full_at_every_width(self):
        for name in ('recorded', 'stale_link', 'unknown_observation', 'absent_edges', 'half_engine_pin'):
            snapshot = SCENARIOS[name]()
            for width in (40, 60, 80, 120):
                rows = screen().text(snapshot, width)
                where = (name, width)
                self.assertEqual(controls_in(rows), [], where)
                self.assertTrue(all(width_of(row) <= width for row in rows), where)
                joined = ' '.join(row.strip() for row in rows)
                for number, node in enumerate(snapshot['nodes'], 1):
                    self.assertIn('%d %s: %s' % (number, screen().LABELS[node['id']], screen().STATE_WORDS[node['state']]), joined, where)
                    self.assertIn(node['basis']['record'], joined, where)
                for edge in snapshot['edges']:
                    self.assertIn('%s %s -> %s: %s' % (edge['type'], screen().LABELS[edge['from']], screen().LABELS[edge['to']],
                                                       screen().STATE_WORDS[edge['state']]), joined, where)
                self.assertIn(screen().HAZARD, joined, where)
                self.assertTrue(joined.endswith(screen().READ_ONLY), where)

    def test_the_text_form_names_the_reason_of_a_node_that_is_not_recorded(self):
        joined = ' '.join(screen().text(half_engine_pin(), 80))
        self.assertIn('opentofu: unknown | reason engine_pin_incomplete', joined)

    def test_the_text_form_holds_the_same_words_the_map_rows_do(self):
        snapshot = stale_link()
        text_rows = screen().text(snapshot, 120)
        map_rows = screen().render(snapshot, 120, 40, colour=False, unicode=False)
        self.assertTrue(text_rows and map_rows)
        self.assertEqual(text_rows[0], map_rows[0])
        # The map marks the focused row with `>`; the text form focuses nothing, so the gutter is blank.
        in_text = [row[2:] for row in text_rows]
        for row in map_rows[1:len(snapshot['nodes']) + len(snapshot['edges']) + 1]:
            self.assertIn(row[2:], in_text, row)


class JsonTests(unittest.TestCase):
    def test_the_json_form_is_one_parseable_value_with_nothing_around_it(self):
        for name in ('recorded', 'stale_link', 'unknown_observation', 'absent_edges', 'half_engine_pin'):
            snapshot = SCENARIOS[name]()
            body = screen().to_json(snapshot)
            self.assertTrue(body.startswith('{'), name)
            self.assertTrue(body.endswith('}\n'), name)
            self.assertNotIn('\x1b', body)
            self.assertEqual(json.loads(body), snapshot, name)

    def test_it_keeps_raw_identities_nulls_ordering_and_authority_flags(self):
        snapshot = unknown_observation()
        parsed = json.loads(screen().to_json(snapshot), object_pairs_hook=lambda pairs: pairs)
        self.assertEqual([key for key, _ in parsed], list(snapshot))
        loaded = json.loads(screen().to_json(snapshot))
        self.assertEqual([node['id'] for node in loaded['nodes']], proj.NODE_IDS)
        self.assertIsNone(next(n for n in loaded['nodes'] if n['id'] == 'observation')['identity']['run_id'])
        self.assertEqual((loaded['read_only'], loaded['execution_authorized'], loaded['cloud_authority']), (True, False, False))
        self.assertEqual(loaded['revision'], snapshot['revision'])

    def test_terminal_escaping_never_applies_to_json(self):
        snapshot = hostile()
        body = screen().to_json(snapshot)
        self.assertNotIn('\x1b', body)
        self.assertEqual(controls_in([body.replace('\n', '')]), [])
        loaded = json.loads(body)
        self.assertEqual(loaded.get('name'), HOSTILE + LONG)
        self.assertEqual(loaded.get('object_id'), 'policy-' + HOSTILE + LONG)
        self.assertEqual(loaded, snapshot)

    def test_no_banner_key_hint_or_ansi_comes_with_it(self):
        body = screen().to_json(recorded())
        self.assertFalse(SGR.search(body))
        for word in ('Enter', 'Esc', 'press', 'SYSTEM MAP', 'read-only: it reads'):
            self.assertNotIn(word, body)


class FixtureTests(unittest.TestCase):
    NAMES = sorted(SCENARIOS)

    def load(self, name):
        return json.loads((FIXTURES / (name + '.json')).read_text(encoding='utf-8'))

    @staticmethod
    def canonical(value):
        return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)

    def test_there_is_one_fixture_per_scenario(self):
        self.assertEqual(sorted(path.stem for path in FIXTURES.glob('*.json')), self.NAMES)

    def test_each_fixture_holds_its_revision_its_body_digest_and_the_complete_payload(self):
        for name in self.NAMES:
            fixture = self.load(name)
            self.assertEqual(sorted(fixture), ['body_sha256', 'expected_revision', 'payload', 'scenario', 'snapshot'], name)
            self.assertEqual(fixture['scenario'], name)
            self.assertEqual(hashlib.sha256(self.canonical(fixture['snapshot']).encode('utf-8')).hexdigest(),
                             fixture['body_sha256'], name)
            self.assertEqual(fixture['snapshot'].get('revision'), fixture['expected_revision'], name)
            if name != 'unsupported_schema':
                body = {key: value for key, value in fixture['snapshot'].items() if key != 'revision'}
                self.assertEqual(hashlib.sha256(self.canonical(body).encode('utf-8')).hexdigest(),
                                 fixture['expected_revision'], name)

    def test_the_json_form_of_each_fixture_is_exactly_its_payload(self):
        for name in self.NAMES:
            fixture = self.load(name)
            self.assertEqual(json.loads(screen().to_json(fixture['snapshot'])), fixture['payload'], name)

    def test_the_projection_still_produces_each_frozen_snapshot(self):
        for name in self.NAMES:
            self.assertEqual(SCENARIOS[name](), self.load(name)['snapshot'], name)

    def test_the_valid_scenarios_say_what_they_are_for(self):
        states = lambda name: {n['id']: n['state'] for n in self.load(name)['snapshot']['nodes']}
        edges = lambda name: {e['id']: e['state'] for e in self.load(name)['snapshot']['edges']}
        self.assertEqual(set(states('recorded').values()) - {'recorded', 'configured'}, set())
        self.assertEqual((states('stale_link')['tofu.backend'], edges('stale_link')['cites:atmos.component>tofu.backend']),
                         ('recorded', 'stale'))
        self.assertEqual(states('unknown_observation')['observation'], 'unknown')
        self.assertEqual(self.load('absent_edges')['snapshot']['edges'], [])
        self.assertEqual(states('half_engine_pin')['tofu.engine'], 'unknown')
        self.assertEqual(self.load('unsupported_schema')['payload']['schema_version'], 'system-map-unavailable/1')


class FalsifierTests(unittest.TestCase):
    def test_long_names_and_controls_never_reach_a_terminal_and_never_widen_a_row(self):
        snapshot = hostile()
        for size in ALL_SIZES:
            for colour, unicode in MODES:
                rows = screen().render(snapshot, size[0], size[1], colour=colour, unicode=unicode)
                shown = plain(rows)
                where = (size, colour, unicode)
                self.assertEqual(controls_in(shown), [], where)
                self.assertTrue(all(width_of(row) <= size[0] for row in shown), where)
                if not colour:
                    self.assertFalse(any('\x1b' in row for row in rows), where)
                if size == SMALL:
                    self.assertIn('The system map needs a larger window (at least 60x20). Plain text:', ' '.join(shown), where)
                    continue
                self.assertLessEqual(len(shown), size[1], where)
                for node in snapshot['nodes']:
                    self.assertIn(screen().STATE_WORDS[node['state']], node_row(asciified(shown), snapshot, node['id']), where)
                self.assertTrue(any(screen().HAZARD in row for row in shown), where)
                self.assertEqual(len([row for row in shown if row.startswith('[SYSTEM MAP]')]), 1, where)

    def test_the_header_keeps_the_evidence_class_whole_however_long_the_name(self):
        snapshot = hostile()
        evidence = screen().safe_text(snapshot['evidence_class'])
        for size in SIZES:
            rows = screen().render(snapshot, size[0], size[1], colour=False, unicode=False)
            cut = next((index for index, row in enumerate(rows) if '|- ' in row), len(rows))
            header = ''.join(row.strip() for row in rows[:cut])
            self.assertIn(evidence[:20], header, size)

    def test_a_control_in_a_name_is_shown_escaped_where_the_name_is_shown(self):
        rows = screen().text(hostile(), 120)
        joined = ''.join(row.strip() for row in rows)     # a long unbroken name wraps mid-word; its pieces rejoin
        for escaped in ('\\u001b', '\\r', '\\n', '\\u0007', '\\u0085', '\\u2028', '\\u2029', '\\u009b'):
            self.assertIn(escaped, joined)
        self.assertEqual(controls_in(rows), [])

    def test_the_plain_text_form_holds_every_control_free_at_every_width(self):
        snapshot = hostile()
        for width in (40, 60, 80, 120):
            rows = screen().text(snapshot, width)
            self.assertEqual(controls_in(rows), [], width)
            self.assertTrue(all(width_of(row) <= width for row in rows), width)
            joined = ' '.join(row.strip() for row in rows)
            for node in snapshot['nodes']:
                self.assertIn(screen().STATE_WORDS[node['state']], joined)
            self.assertIn(screen().HAZARD, ' '.join(row.strip() for row in rows))

    def test_wide_characters_are_measured_in_cells(self):
        read = proj.baseline()
        read['name'] = '日本語' * 30
        read['states']['intent']['scope']['stack'] = '日本語' * 30
        snapshot = snap(read)
        for size in ALL_SIZES:
            rows = screen().render(snapshot, size[0], size[1], colour=False, unicode=True)
            self.assertTrue(all(width_of(row) <= size[0] for row in rows), size)
        self.assertTrue(all(width_of(row) <= 60 for row in screen().text(snapshot, 60)))


if __name__ == '__main__':
    unittest.main()
