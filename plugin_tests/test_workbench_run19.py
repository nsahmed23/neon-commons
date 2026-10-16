"""PKG-PRES-RUN19: the Inspector after Coverage, and the catalog layer at small sizes.

Item 1 (DEF-INSPECTOR-AFTER-VIEWS) drives the real workspace over the real engine, store and modeled service, the way the
workflow map's tests do (LayerFixture): after `:views` (Coverage) every move to the Inspector reached the Inspector.
Items 2 to 5 are the catalog layer at the smaller windows of journey 33 run 1 (frame review B, findings 1 to 4).
"""
import re
import tempfile
import unittest
from unittest import mock

from plugin_tests import test_catalog as tc
from plugin_tests import test_catalog_layer as catalog_layer
from plugin_tests import test_readiness as tr
from plugin_tests.test_workflow_map import LayerFixture, OBJECT, typed

NAME = 'Windows Privacy Pilot'
INVALID = ('invalid_workbench_request', 'Invalid workbench request')
GUID = '22222222-2222-4222-8222-222222222222'


def key(char):
    return ('text', char)


class InspectorAfterCoverageTests(LayerFixture):
    """:views opens Coverage; the engine answers with a views result, which names the policy and carries a coverage
    record. The Inspector used to draw that leftover result while its own was still being asked for."""

    def squash(self, rows):
        return ' '.join(' '.join(self.plain(rows)).split())

    def after_views(self, route, size=(120, 40), rules='unicode'):
        self.prepare()
        before = len(typed('select ' + OBJECT)) + len(typed('views'))
        ws, frames = self.run_keys(typed('select ' + OBJECT) + typed('views') + route + [key('q')], size, rules)
        return ws, frames, before

    def assert_refused_nowhere(self, frames, first):
        """No frame from the one before the route on drew a refusal, an invalid request or a display fault."""
        for index, rows in enumerate(frames[first:], first):
            text = self.squash(rows)
            for word in INVALID + ('[REFUSED]', 'DISPLAY FAULT'):
                self.assertNotIn(word, text, 'frame %d' % index)

    def assert_inspector(self, ws, frames, before):
        self.assert_refused_nowhere(frames, before)
        state = ws.states[-1]
        self.assertEqual((state['tab'], state['layer'], state['selected']), (1, 'summary', OBJECT))
        text = self.squash(frames[-1])
        self.assertIn('INTUNE WORKBENCH / Inspector', text)
        self.assertIn('POLICY ' + NAME, text)
        self.assertIn('Identity ' + OBJECT, text)

    def test_key_2_after_coverage_reaches_the_inspector_with_the_policy_selected(self):
        ws, frames, before = self.after_views([key('2')])
        self.assertEqual(ws.sent[-2:], ['inspect', 'quit'])
        self.assert_inspector(ws, frames, before)

    def test_b_after_coverage_reaches_the_inspector_with_the_policy_selected(self):
        ws, frames, before = self.after_views([key('b')])
        self.assertEqual(ws.sent[-2], 'select ' + OBJECT)
        self.assert_inspector(ws, frames, before)

    def test_select_after_coverage_reaches_the_inspector_with_the_policy_selected(self):
        ws, frames, before = self.after_views(typed('select ' + OBJECT))
        self.assertEqual(ws.sent[-2], 'select ' + OBJECT)
        self.assert_inspector(ws, frames, before)

    def test_inspect_after_coverage_reaches_the_inspector_with_the_policy_selected(self):
        ws, frames, before = self.after_views(typed('inspect'))
        self.assertEqual(ws.sent[-2], 'inspect')
        self.assert_inspector(ws, frames, before)

    def test_enter_on_the_maintain_stage_then_b_returns_to_the_map_and_b_again_to_the_inspector(self):
        self.prepare()
        opened = len(typed('select ' + OBJECT)) + len(typed('workflow'))
        # Eleven Down keys end on `maintain`, whatever stage the records put the position on.
        sequence = typed('select ' + OBJECT) + typed('workflow') + ['down'] * 11 + ['enter', key('b'), key('b'), key('q')]
        ws, frames = self.run_keys(sequence, (120, 40), 'unicode')
        coverage, map_again, inspector = ws.states[opened + 12], ws.states[opened + 13], ws.states[opened + 14]
        self.assertEqual((coverage['tab'], coverage['focus'], coverage['last']), (6, 'maintain', 'views'))
        self.assertEqual((map_again['tab'], map_again['layer'], map_again['selected'], map_again['focus']),
                         (1, 'workflow', OBJECT, 'maintain'))
        self.assertEqual((inspector['tab'], inspector['layer'], inspector['selected']), (1, 'summary', OBJECT))
        self.assert_refused_nowhere(frames, opened + 11)
        self.assertIn('[WORKFLOW]', self.squash(frames[opened + 13]))
        self.assertIn('POLICY ' + NAME, self.squash(frames[-1]))

    def views(self):
        from intune_iac.workbench_views import views
        return views(self.store, OBJECT, limit=10)

    def workspace_after_views(self):
        """A Workspace holding the views result of the selected policy under the Coverage tab, with no engine behind it."""
        import io
        from intune_iac.workbench_tui import Workspace
        ws = Workspace(self.store.root, stdout=io.StringIO(), stdin=io.StringIO(), no_color=True)
        ws.pending.clear()
        ws.rules = 'ascii'
        ws._terminal_size = lambda: (120, 40)
        ws.size = (120, 40)
        ws.selected = OBJECT
        ws.tab, ws.last_command = 6, 'views'
        ws.receive(self.views())
        return ws

    def test_the_views_result_names_the_policy_and_carries_a_coverage_record_not_a_word(self):
        value = self.views()
        self.assertEqual(value['object_id'], OBJECT)
        self.assertIsInstance(value['coverage'], dict)

    def test_asking_for_the_inspector_does_not_draw_the_views_result_as_one(self):
        ws = self.workspace_after_views()
        sent = ws._send('inspect')                 # draws the new surface before the engine answers
        self.assertEqual(sent, 'inspect')
        shown = self.squash(ws.stdout.getvalue().split('\x1b[H')[-1].split('\r\n'))
        self.assertIn('RUNNING: waiting for the engine', shown)
        for body in ('Identity', 'WHAT THE EVIDENCE SAYS IT DOES', '(no name in this result)'):
            self.assertNotIn(body, shown)

    def test_the_inspector_draws_nothing_from_a_value_that_is_not_an_inspection(self):
        ws = self.workspace_after_views()
        ws.value, ws.tab = self.views(), 1
        self.assertEqual(ws._surface_summary(100), [])

    def test_coverage_words_does_not_raise_on_a_coverage_that_is_not_a_word(self):
        from intune_iac.workbench_screens import COVERAGE_WORDS, coverage_words
        for coverage in ({'observation': 'complete_fresh'}, {}, ['complete'], None, 3, ('a',)):
            words = coverage_words(coverage)
            self.assertIsInstance(words, str, coverage)
            self.assertTrue(words, coverage)
        self.assertEqual(coverage_words('complete'), COVERAGE_WORDS['complete'])
        self.assertEqual(coverage_words('partial_collection'), 'collection partial collection (i shows what was not read)')


class DisplayFaultTests(LayerFixture):
    """A fault while drawing is the interface's: said as a display fault with its code, the session stays usable, and the
    engine loop still calls genuine invalid input an invalid request."""

    def squash(self, rows):
        return ' '.join(' '.join(self.plain(rows)).split())

    def test_a_renderer_fault_is_reported_as_a_display_fault_not_as_an_invalid_request(self):
        from intune_iac import workbench_screens
        self.prepare()
        opened = len(typed('select ' + OBJECT))
        with mock.patch.object(workbench_screens, 'inspector_lines', side_effect=TypeError('forced renderer fault')):
            ws, frames = self.run_keys(typed('select ' + OBJECT) + [key('q')], (80, 24), 'ascii')
        text = self.squash(frames[opened])
        self.assertIn('[DISPLAY FAULT]', text)
        self.assertIn('workbench_display_fault', text)
        self.assertIn('TypeError', text)
        self.assertIn('not in what you typed', text)
        for word in INVALID + ('[REFUSED]',):
            self.assertNotIn(word, text)
        # The chrome stays: the title, the surface line and the keys are the ordinary frame's.
        rows = self.plain(frames[opened])
        self.assertIn('INTUNE WORKBENCH  /  Inspector', rows[0])
        self.assertIn('[2 Insp]', rows[1])
        self.assertNotIn('forced renderer fault', text)          # the exception's own words are not echoed
        self.assertEqual((ws.states[opened]['selected'], ws.states[opened]['tab']), (OBJECT, 1))

    def test_the_session_stays_usable_after_a_display_fault(self):
        from intune_iac import workbench_screens
        self.prepare()
        opened = len(typed('select ' + OBJECT))
        with mock.patch.object(workbench_screens, 'inspector_lines', side_effect=TypeError('forced renderer fault')):
            ws, frames = self.run_keys(typed('select ' + OBJECT) + [key('1'), key('q')], (80, 24), 'ascii')
        self.assertEqual(ws.sent[-2:], ['overview', 'quit'])
        self.assertEqual(ws.states[-1]['tab'], 0)
        text = self.squash(frames[-1])
        self.assertNotIn('DISPLAY FAULT', text)
        self.assertNotIn('invalid_workbench_request', text)

    def test_the_fault_is_still_said_when_the_chrome_cannot_be_drawn_either(self):
        import io
        from intune_iac.workbench_tui import Workspace
        self.prepare()
        out = io.StringIO()
        ws = Workspace(self.store.root, stdout=out, stdin=io.StringIO(), no_color=True)
        ws._terminal_size = lambda: (80, 24)
        with mock.patch.object(Workspace, '_context_strip', side_effect=KeyError('forced')), \
                mock.patch.object(Workspace, '_strip_choice', side_effect=KeyError('forced')):
            ws.draw()                                           # raises nothing into the engine loop
        text = out.getvalue()
        self.assertIn('DISPLAY FAULT', text)
        self.assertIn('workbench_display_fault', text)
        self.assertIn('KeyError', text)

    def test_genuine_invalid_input_is_still_an_invalid_request(self):
        self.prepare()
        opened = len(typed('select'))
        ws, frames = self.run_keys(typed('select') + [key('q')], (80, 24), 'ascii')
        text = self.squash(frames[opened])
        self.assertIn('invalid_workbench_request', text)
        self.assertNotIn('DISPLAY FAULT', text)


def estate_catalog(directory='/work/estate dir', relative_to=None, extra=0):
    """The catalog of an estate like journey 33 run 1's, built by the product from a survey of `directory`: the real
    goals and kinds, and saved projects with their state words and one resume command each (`extra` repositories, a
    wizard session, a generated project, an operation and a store). The catalog the layer prints from is the build's
    text build, whose directory operand the product's own path writer wrote (entry.text_paths), as in the workspace."""
    from intune_iac import catalog as catalog_module
    items = [tr.repository_item(path='repository-%d' % number) for number in range(extra)] + [
        tr.repository_item(), tr.context_item(),
        {'kind': 'wizard_session', 'path': 'estate dir/session.json', 'valid': True, 'step': 'confirm', 'output': 'generated',
         'states': tr.states()},
        {'kind': 'generated_project', 'path': 'generated', 'classification': 'unchanged', 'session': 'session.json',
         'states': tr.states()},
        {'kind': 'operation', 'path': 'operation-1', 'object_id': GUID, 'status': 'prepared',
         'changes': [GUID + ':description_changed'], 'states': dict(tr.states(), qualified='synthetic_only')},
        {'kind': 'store', 'path': 'store', 'tenant_id': tr.TENANT, 'objects': 1, 'freshness': 'fresh', 'intents': [],
         'operations': 1, 'states': tr.states()}]
    survey = tr.survey_of(*items)
    survey['directory'] = directory
    return catalog_module.build(survey, doctor=tc.doctor(), relative_to=relative_to)


class CatalogLayerCase(unittest.TestCase):
    """The catalog layer opened the way the workspace opens it: the command is sent and its result received."""

    def layer(self, size, data=None, rules='ascii'):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        ws = catalog_layer.workspace(directory.name, size=size)
        ws.rules = rules
        ws._send('catalog')
        ws.receive(data if data is not None else estate_catalog())
        return ws

    @staticmethod
    def body(rows):
        """The rows inside the frame's side rules, with the rules and the padding off."""
        return [row[1:-1].strip() for row in rows if row[:1] in '|│' and row[-1:] in '|│']

    def pages(self, ws, limit=80):
        """The frame of each page of the layer, paged with the real PageDown key until a page repeats the one before."""
        shown = []
        for _ in range(limit):
            rows = catalog_layer.rows_of(ws)
            if shown and rows == shown[-1]:
                break
            shown.append(rows)
            ws.key_reader = catalog_layer.Keys('pagedown', 'eof')
            try:
                ws.input('')
            except EOFError:
                pass
        return shown


class CatalogPlainTextRouteTests(CatalogLayerCase):
    """Item 2 (journey 33 run 1, review B finding 1): below 60x20 the layer says the catalog needs a larger window and
    now also says how to get the same text without one. The directory in that command is the operand the catalog's own
    path writer wrote (round 2, Sol review: the row once quoted the recorded directory itself)."""

    ROUTE = 'Plain text: intune-iac catalog'

    def route_row(self, size, data=None):
        rows = catalog_layer.rows_of(self.layer(size, data))
        routes = [row for row in self.body(rows) if row.startswith(('Plain text: intune-iac catalog', 'Text: intune-iac catalog'))]
        self.assertEqual(len(routes), 1, (size, rows))
        return routes[0]

    def test_at_40x12_the_layer_names_the_plain_text_route_in_the_rows_it_has(self):
        rows = catalog_layer.rows_of(self.layer((40, 12)))
        body = self.body(rows)
        self.assertEqual(len(body), 3, rows)                       # three rows are all a 40x12 frame has for the body
        self.assertEqual(body[2], 'Text: intune-iac catalog DIRECTORY')
        text = ' '.join(body)
        self.assertIn('The catalog needs a larger window: at least 60x20.', text)
        self.assertIn('Esc closes it.', text)
        self.assertNotIn('more below', ' '.join(rows))             # nothing is scrolled out of view
        for row in rows:
            self.assertLessEqual(len(row), 40, row)

    def test_the_route_is_not_drawn_where_the_catalog_itself_is(self):
        rows = catalog_layer.rows_of(self.layer((60, 20)))
        self.assertNotIn(self.ROUTE, ' '.join(rows))
        self.assertIn('INTEGRATION CATALOG', ' '.join(rows))

    def test_an_ordinary_directory_prints_as_the_catalog_writes_it_where_the_row_holds_it(self):
        cases = (((40, 12), '/work', 'Plain text: intune-iac catalog /work'),
                 ((40, 12), '/work/a', 'Text: intune-iac catalog /work/a'),          # the label gives way before the name does
                 ((40, 12), '/work/estate dir', 'Text: intune-iac catalog DIRECTORY'),   # a name the row cannot hold
                 ((59, 24), '/work/estate dir', "Plain text: intune-iac catalog '/work/estate dir'"),
                 ((80, 19), '/work/estate dir', "Plain text: intune-iac catalog '/work/estate dir'"))
        for size, directory, expected in cases:
            self.assertEqual(self.route_row(size, estate_catalog(directory)), expected, (size, directory))

    def test_the_row_uses_the_operand_the_path_writer_wrote_and_does_not_quote_it_again(self):
        # Run from /work, the writer names the directory relative to it, quoted once.
        self.assertEqual(self.route_row((80, 19), estate_catalog('/work/estate dir', relative_to='/work')),
                         "Plain text: intune-iac catalog 'estate dir'")
        # Run from the directory itself, it names it `.`, which a 40x12 row holds.
        self.assertEqual(self.route_row((40, 12), estate_catalog('/work/estate dir', relative_to='/work/estate dir')),
                         'Plain text: intune-iac catalog .')

    def test_a_result_with_no_operand_shows_the_shared_placeholder(self):
        import json
        plain = json.loads(json.dumps(estate_catalog('/work/estate dir')))      # crossed a JSON boundary: no text build
        self.assertEqual(self.route_row((80, 19), plain), 'Plain text: intune-iac catalog DIRECTORY')
        self.assertEqual(self.route_row((40, 12), plain), 'Text: intune-iac catalog DIRECTORY')


class RouteDirectoryTests(CatalogLayerCase):
    """Round 2 (Sol review of 97b4757, High): the narrow route named the directory by quoting the recorded one, so a name
    the shared display rule refuses (a credential shape, a control character, over-long, or one that terminal escaping
    changes) reached the screen, or an escaped copy that addresses another path. The catalog's path writer says such a
    directory is DIRECTORY on every screen; the route row now takes it from there. Through the real layer, built by the
    real catalog builder: no raw control byte, and no refused name or piece of it, on screen."""

    TOKEN = 'ghp_AbCdEfGhIjKlMnOpQrStUvWxYz0123456789'
    REFUSED = (
        # what it is, the directory, strings that must not be on the screen besides the name and its escaped form
        ('credential-shaped', 'ghp_x', ('ghp_',)),
        ('credential-shaped, long', TOKEN, ('ghp_', 'AbCdEf', 'Wx')),
        ('a control character', '/work/a\nb', ('/work/a', 'a\\nb')),
        ('a control character, short', 'a\n', ('a\\n',)),
        ('over-long', '/work/' + 'd' * 220, ('dddddddddd',)),
        ('changed by terminal escaping', '/work/é', ('/work/e', 'u0301', '́')))

    def screen_of(self, directory, size):
        rows = catalog_layer.rows_of(self.layer(size, estate_catalog(directory)))
        self.assertEqual(len(rows), size[1], rows)                 # a raw line feed would have forged a row
        for row in rows:
            self.assertTrue(all(32 <= ord(char) < 127 for char in row), repr(row))
        return rows

    def test_a_refused_directory_is_the_placeholder_on_the_route_row_and_nowhere_else(self):
        from intune_iac.workbench_tui import safe_text
        for what, directory, pieces in self.REFUSED:
            for size in ((40, 12), (59, 24), (80, 19)):
                with self.subTest(what=what, size=size):
                    rows = self.screen_of(directory, size)
                    expected = ('Text: intune-iac catalog DIRECTORY' if size == (40, 12)
                                else 'Plain text: intune-iac catalog DIRECTORY')
                    self.assertIn(expected, self.body(rows))
                    for text in ('\n'.join(rows), ''.join(row.strip() for row in rows), ' '.join(row.strip() for row in rows)):
                        for refused in (directory, safe_text(directory)) + pieces:
                            self.assertNotIn(refused, text)

    def test_an_ordinary_directory_is_shown_as_before_with_no_raw_control_byte(self):
        for size in ((40, 12), (59, 24), (80, 19)):
            for directory in ('/work', '/work/estate dir'):
                rows = self.screen_of(directory, size)
                self.assertTrue(any(row.startswith(('Plain text: intune-iac catalog', 'Text: intune-iac catalog'))
                                    for row in self.body(rows)), (directory, size))


class IdentifierWrapTests(CatalogLayerCase):
    """Item 3 (journey 33 run 1, review B finding 2): the shared word wrap treats a GUID, with or without the suffix that
    says what is recorded of it, as one token. It breaks before it, and breaks inside it only when it is wider than the
    line, and then at a group boundary or beside the colon, never inside a group."""

    def wrap(self, text, width):
        from intune_iac.workbench_screens import word_wrap
        return word_wrap(text, width)

    def test_a_guid_with_a_suffix_wider_than_the_line_starts_a_row_and_breaks_beside_its_colon(self):
        # 60x20: the catalog's rows hold 52 cells under a four-cell indent, and GUID:suffix is 56.
        text = 'Operation operation-1: prepared | %s:description_changed | discovered | usable here' % GUID
        self.assertEqual(self.wrap(text, 52), ['Operation operation-1: prepared |', GUID + ':',
                                               'description_changed | discovered | usable here'])
        # A line the GUID fills exactly: the colon cannot join it, so the suffix starts the next row.
        self.assertEqual(self.wrap('see ' + GUID + ':added', 36), ['see', GUID, ':added'])

    def test_a_guid_wider_than_the_line_breaks_at_a_group_boundary_never_inside_a_group(self):
        # 40x12: the Inspector's Identity text has 26 cells beside its label.
        self.assertEqual(self.wrap(GUID + ' | windows10 | scope tags []', 26),
                         ['22222222-2222-4222-8222-', '222222222222 | windows10 |', 'scope tags []'])
        self.assertEqual(self.wrap('Identity ' + GUID, 20), ['Identity', '22222222-2222-4222-', '8222-222222222222'])
        self.assertEqual(self.wrap('    ' + GUID + ' end', 30), ['    22222222-2222-4222-8222-', '    222222222222 end'])

    def test_a_guid_that_fits_a_row_is_never_split(self):
        self.assertEqual(self.wrap('Operation operation-1: prepared | %s | discovered' % GUID, 52),
                         ['Operation operation-1: prepared |', GUID + ' | discovered'])
        self.assertEqual(self.wrap('Operation operation-1: prepared | %s:description_changed | discovered' % GUID, 60),
                         ['Operation operation-1: prepared |', GUID + ':description_changed |', 'discovered'])
        self.assertEqual(self.wrap('Identity ' + GUID, 36), ['Identity', GUID])
        self.assertEqual(self.wrap('%s %s' % (GUID, GUID.replace('2', '3')), 40), [GUID, GUID.replace('2', '3')])

    def test_no_other_text_wraps_differently(self):
        digest = 'a' * 64
        cases = [
            ('Plan SHA-256: %s recorded' % digest, 40, ['Plan SHA-256: ' + 'a' * 26, 'a' * 38, 'recorded']),
            ('Plan SHA-256: %s recorded' % digest, 60, ['Plan SHA-256: ' + 'a' * 46, 'a' * 18 + ' recorded']),
            ('Resume: /home/nsahm/work/estate-directory/session.json and more text', 30,
             ['Resume:', '/home/nsahm/work/', 'estate-directory/session.json', 'and more text']),
            ('operation-ready and not-yet-qualified identity-binding words that wrap here', 24,
             ['operation-ready and', 'not-yet-qualified', 'identity-binding words', 'that wrap here']),
            ('the code workbench_deployment_intent_not_cited is long enough to need a cut', 28,
             ['the code workbench_deploymen', 't_intent_not_cited is long', 'enough to need a cut']),
            # Not an identifier: a GUID that lost its last group keeps the wrapping every token has.
            ('tenant 11111111-1111-4111-8111 abcdef', 20, ['tenant 11111111-1111', '-4111-8111 abcdef']),
            ('Policy %s is selected and fresh' % GUID, 40, ['Policy', GUID + ' is', 'selected and fresh'])]
        for text, width, expected in cases:
            self.assertEqual(self.wrap(text, width), expected, (text, width))

    def test_the_inspector_identity_row_at_40x12_keeps_the_guids_groups_whole(self):
        from intune_iac.workbench_screens import inspector_lines
        value = {'object_id': GUID, 'name': NAME, 'body': {'platforms': 'windows10', 'technologies': ['mdm'],
                                                            'role_scope_tag_ids': ['0']}}
        rows = inspector_lines(value, 36)
        at = next(index for index, row in enumerate(rows) if row.startswith('Identity'))
        self.assertEqual(rows[at:at + 2], ['Identity  22222222-2222-4222-8222-',
                                           '          222222222222 | windows10 |'])

    def test_the_catalog_layer_at_60x20_shows_the_operations_guid_whole(self):
        rows = [row for page in self.pages(self.layer((60, 20))) for row in self.body(page)]
        self.assertIn(GUID + ':', rows)
        self.assertIn('description_changed | discovered | usable here |', ' '.join(rows))
        for row in rows:
            self.assertNotRegex(row, r'^-[0-9a-f]{4}-', 'a row that continues a GUID cut inside its groups')
            self.assertNotRegex(row, r'[0-9a-f]{8}-[0-9a-f]{4}-4222$', 'a row that ends inside a GUID')


class CommandPagingTests(CatalogLayerCase):
    """Item 5 (journey 33 run 1, review B finding 4): a command that wraps with `\\` continuation rows stood on two pages,
    complete only across both (frames 29 and 30, 31 and 32, 37 and 38). Paging now breaks before such a command when
    the page would end inside it; every row is still shown, in order, and the last page is still the end of the text."""

    @staticmethod
    def catalog_with(extra):
        """The estate catalog with `extra` more saved repositories before the others, in a directory whose name is `extra`
        letters longer: each shifts the rows that follow, and the sign-in commands wrap in different places."""
        return estate_catalog('/work/journey 33/estate directory/' + 'd' * extra, extra=extra)

    @staticmethod
    def commands_of(data, width):
        """Each command of the layer's text as its rows: a run of rows, every one but the last ending in a backslash."""
        from intune_iac.catalog import catalog_lines
        blocks, block = [], []
        for line in catalog_lines(data, width):
            block.append(line.strip())
            if not line.rstrip().endswith('\\'):
                if len(block) > 1:
                    blocks.append(block)
                block = []
        return blocks

    @staticmethod
    def within(rows, block):
        return any(rows[at:at + len(block)] == block for at in range(len(rows) - len(block) + 1))

    def assert_commands_whole(self, size):
        crossings = 0
        for extra in range(6):
            data = self.catalog_with(extra)
            pages = [self.body(page) for page in self.pages(self.layer(size, data))]
            commands = self.commands_of(data, size[0] - 4)
            self.assertGreater(len(commands), 3)                   # the layer holds commands that wrap
            self.assertGreater(len(pages), 4)
            for number, rows in enumerate(pages[:-1], 1):
                self.assertFalse(rows[-1].endswith('\\'), 'extra %d, page %d ends inside a command: %r' % (extra, number, rows[-3:]))
            for command in commands:
                self.assertTrue(any(self.within(rows, command) for rows in pages), 'extra %d: %r on no one page' % (extra, command))
            # Every row of the text is shown, in order (a page may repeat rows the page before it showed).
            shown = iter([row for rows in pages for row in rows])
            from intune_iac.catalog import catalog_lines
            for line in (line.strip() for line in catalog_lines(data, size[0] - 4) if line.strip()):
                self.assertTrue(any(line == row for row in shown), 'extra %d: %r is shown on no page' % (extra, line))
            crossings += sum(len(command) - 1 for command in commands)
        self.assertGreater(crossings, 0)

    def test_at_80x24_no_page_ends_inside_a_command_and_each_command_is_whole_on_a_page(self):
        self.assert_commands_whole((80, 24))

    def test_at_60x20_no_page_ends_inside_a_command_and_each_command_is_whole_on_a_page(self):
        self.assert_commands_whole((60, 20))

    def test_page_up_returns_through_the_same_pages_page_down_went_through(self):
        for size in ((80, 24), (60, 20)):
            ws = self.layer(size, self.catalog_with(2))
            down = self.pages(ws)
            starts = []
            for _ in range(len(down) + 3):
                starts.append(ws.scroll)
                ws.key_reader = catalog_layer.Keys('pageup', 'eof')
                try:
                    ws.input('')
                except EOFError:
                    pass
                catalog_layer.rows_of(ws)
            self.assertEqual(ws.scroll, 0, size)
            # Paging down again gives the pages it gave before.
            self.assertEqual([self.body(page) for page in self.pages(ws)], [self.body(page) for page in down], size)

    def test_a_page_key_pressed_where_no_body_is_drawn_does_not_move_the_page_when_the_window_grows(self):
        ws = self.layer((80, 24), self.catalog_with(2))
        ws._terminal_size = lambda: (39, 11)
        ws.key_reader = catalog_layer.Keys('pagedown', 'eof')
        try:
            ws.input('')
        except EOFError:
            pass
        ws._terminal_size = lambda: (80, 24)
        catalog_layer.rows_of(ws)
        self.assertEqual(ws.scroll, 0)

    def test_scrolling_by_a_row_is_not_paging_and_still_moves_one_row(self):
        ws = self.layer((80, 24), self.catalog_with(2))
        catalog_layer.rows_of(ws)
        ws.key_reader = catalog_layer.Keys('down', 'down', 'up', 'eof')
        try:
            ws.input('')
        except EOFError:
            pass
        self.assertEqual(ws.scroll, 1)

    def test_page_starts_never_split_a_command_and_do_not_loop_on_a_command_taller_than_the_page(self):
        from intune_iac.workbench_screens import page_starts
        rows = ['text'] * 5 + ['cmd \\', '  more \\', '  end'] + ['text'] * 6
        self.assertEqual(page_starts(rows, 7), [0, 5, 12])       # 7 rows would end at "  more \"; the break moves before the command
        self.assertEqual(page_starts(['a \\'] * 6 + ['end'], 3), [0, 3, 6])   # taller than the page: the plain break
        self.assertEqual(page_starts(['x'] * 10, 0), [0, 1, 2, 3, 4, 5, 6, 7, 8, 9])   # a window with no body row still ends
        self.assertEqual(page_starts([], 5), [0])


class NarrowChromeTests(CatalogLayerCase):
    """Item 4 (journey 33 run 1, review B finding 3): at 40x12 the title lost "read-only" and ended in a slash, and the
    notice row ended in "Esc closes…" or "Esc...". Where the full form does not fit, a shorter one that keeps those
    words whole is drawn; where it fits, nothing changes."""

    def rows(self, size, rules='ascii'):
        return [row.rstrip() for row in catalog_layer.rows_of(self.layer(size, rules=rules))]

    def notice_row(self, rows):
        """The row under the status row (`rows A-B/N`), where the notice is."""
        return rows[next(index for index, row in enumerate(rows) if re.search(r'rows \d+-\d+/\d+', row)) + 1]

    def test_at_40x12_the_title_keeps_read_only_whole_in_both_rules(self):
        for rules in ('ascii', 'unicode'):
            rows = self.rows((40, 12), rules)
            self.assertEqual(rows[0], 'INTUNE WORKBENCH  /  Catalog (read-only)', rules)
            self.assertLessEqual(len(rows[0]), 40)

    def test_at_40x12_the_notice_row_keeps_esc_closes_it_whole_in_both_rules(self):
        for rules in ('ascii', 'unicode'):
            self.assertEqual(self.notice_row(self.rows((40, 12), rules)), 'Catalog (read-only). Esc closes it.', rules)

    def test_at_40x12_the_key_row_keeps_esc_whole(self):
        rows = self.rows((40, 12))
        self.assertEqual(rows[-1], '? help | Esc close | b back | q exit')

    def test_where_the_full_forms_fit_they_are_unchanged(self):
        for size in ((60, 20), (80, 24)):
            rows = self.rows(size)
            self.assertEqual(rows[0], 'INTUNE WORKBENCH  /  Help  /  Catalog  /  read-only', size)
            self.assertEqual(self.notice_row(rows), 'Catalog shown (read-only). Esc closes it.', size)

    def test_the_notice_the_layer_holds_is_not_changed_by_a_narrow_window(self):
        ws = self.layer((40, 12))
        self.assertEqual(ws.notice, 'Catalog shown (read-only). Esc closes it.')   # the form is chosen when it is drawn
        ws._terminal_size = lambda: (80, 24)
        ws.size = (80, 24)
        self.assertEqual(self.notice_row([row.rstrip() for row in catalog_layer.rows_of(ws)]),
                         'Catalog shown (read-only). Esc closes it.')

    def test_title_line_names_the_layer_in_the_longest_form_the_width_holds(self):
        from intune_iac.workbench_tui import title_line
        shown = {'schema_version': 'integration-catalog/1'}
        self.assertEqual(title_line('Help', 'catalog', shown, 'catalog'), 'INTUNE WORKBENCH  /  Help  /  Catalog  /  read-only')
        self.assertEqual(title_line('Help', 'catalog', shown, 'catalog', 51), 'INTUNE WORKBENCH  /  Help  /  Catalog  /  read-only')
        self.assertEqual(title_line('Help', 'catalog', shown, 'catalog', 50), 'INTUNE WORKBENCH  /  Catalog (read-only)')
        self.assertEqual(title_line('Help', 'catalog', shown, 'catalog', 40), 'INTUNE WORKBENCH  /  Catalog (read-only)')
        self.assertEqual(title_line('Help', 'catalog', shown, 'catalog', 39), 'Catalog (read-only)')
        self.assertEqual(title_line('Inspector', 'inspect', {'object_id': OBJECT}, 'details', 40), 'Inspector (typed details)')
        # No layer, or no width: the title is what it always was.
        self.assertEqual(title_line('Inspector', 'inspect', {'object_id': OBJECT}, 'summary', 20), 'INTUNE WORKBENCH  /  Inspector')
        self.assertEqual(title_line('Inspector', 'inspect', {'object_id': OBJECT}, 'details'),
                         'INTUNE WORKBENCH  /  Inspector  /  typed details')


if __name__ == '__main__':
    unittest.main()
