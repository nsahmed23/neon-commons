"""PKG-PRES-RUN19: the Inspector after Coverage, and the catalog layer at small sizes.

Item 1 (DEF-INSPECTOR-AFTER-VIEWS) drives the real workspace over the real engine, store and modeled service, the way the
workflow map's tests do (LayerFixture): after `:views` (Coverage) every move to the Inspector reached the Inspector.
Items 2 to 5 are the catalog layer at the smaller windows of journey 33 run 1 (frame review B, findings 1 to 4).
"""
import unittest
from unittest import mock

from plugin_tests.test_workflow_map import LayerFixture, OBJECT, typed

NAME = 'Windows Privacy Pilot'
INVALID = ('invalid_workbench_request', 'Invalid workbench request')


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


if __name__ == '__main__':
    unittest.main()
