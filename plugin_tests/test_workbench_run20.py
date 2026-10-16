"""PKG-PRES-RUN20: the Inspector and pager findings of journey 34 run 2 (review A) and journey 33 run 2 (review B).

Item 1: a GUID stays whole after its label at 40x12. Item 2: a label stays with its command across a page boundary.
Item 3: the attention rollup counts a closed approval window. Item 4: one reason name, and next steps that read the
current operation. Item 5: a hint names a key that works where it is shown.
"""
import re
import time
import unittest

from plugin_tests import test_workbench_run19 as run19
from plugin_tests.test_workflow_map import LayerFixture, OBJECT, typed


def key(char):
    return ('text', char)


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


class ClosedWindowAttentionTests(LayerFixture):
    """Journey 34 run 2 review A Low-1: with `OP expired` (the approval window closed) the Inspector said "No signal in
    the areas checked (... operations ...)" while the map said `blocked | reason closed`. A closed window is an
    operations signal; the rollup says so, with the step the map gives."""

    def squash(self, rows):
        return ' '.join(' '.join(self.plain(rows)).replace('│', ' ').split())

    def close_window(self, how):
        """Close the prepared operation's approval window as execute would judge it: the recorded latch, or the clock."""
        import contextlib
        from unittest import mock
        from intune_iac import protected
        if how == 'recorded':
            (self.operation / 'executor' / 'expired.json').write_text('{}')
            return contextlib.nullcontext()
        return mock.patch.object(protected, '_now', return_value=time.time() + 10 ** 7)

    def inspector_and_map(self, how):
        from intune_iac import workbench
        self.prepare()
        with self.close_window(how):
            ws, frames = self.run_keys(typed('select ' + OBJECT) + [key('q')], (120, 40), 'unicode')
            projection = workbench._workflow(self.store, OBJECT, service_root=self.service.root)
            read = workbench._workflow_read(self.store, OBJECT, service_root=self.service.root)
        stage = next(item for item in projection['stages'] if item['id'] == 'approve_execute')
        return self.squash(frames[len(typed('select ' + OBJECT))]), stage, read

    def check(self, how, window):
        text, stage, read = self.inspector_and_map(how)
        self.assertEqual((stage['state'], stage['reason']), ('blocked', window), stage)
        self.assertEqual(read['states']['operation']['approval_window'], window)
        rollup = text[text.index('NEEDS ATTENTION'):text.index('WHAT THE EVIDENCE SAYS')]
        self.assertNotIn('No signal in the areas checked', rollup)
        self.assertIn('approval window closed', rollup)
        # The step the map gives for that stage, word for word.
        self.assertIn(' '.join(stage['continuation'].split()), rollup)
        codes = [signal['code'] for signal in read['attention']['signals']]
        self.assertIn('operation_approval_closed', codes)
        signal = next(item for item in read['attention']['signals'] if item['code'] == 'operation_approval_closed')
        self.assertEqual(signal['area'], 'operations')

    def test_a_window_closed_by_the_clock_is_a_signal_in_the_rollup(self):
        self.check('clock', 'closed')

    def test_a_window_closed_and_recorded_is_a_signal_in_the_rollup(self):
        self.check('recorded', 'closed_recorded')

    def test_an_open_window_is_no_signal(self):
        from intune_iac import workbench
        self.prepare()
        read = workbench._workflow_read(self.store, OBJECT, service_root=self.service.root)
        self.assertNotIn('operation_approval_closed', [signal['code'] for signal in read['attention']['signals']])


class ReasonNameAndCurrentOperationTests(LayerFixture):
    """Journey 34 run 2 review A Low-2. One name for the blocked proposal check: the records hold the engine's refusal
    code (`maintenance_observation_stale`, raised for several different reasons) and the check's own reason
    (`service_changed`, which says which); the map and the Inspector name the reason, and now Repository does too, the
    code only where no reason is recorded. And the Repository next step and the Inspector's first action look at the
    newest operation instead of reading as if none exists."""

    def squash(self, rows):
        return ' '.join(' '.join(self.plain(rows)).replace('│', ' ').split())

    def screen_after(self, keys, size=(120, 40)):
        _, frames = self.run_keys(typed('select ' + OBJECT) + keys + [key('q')], size, 'unicode')
        return self.squash(frames[-1])

    def repository(self):
        return self.screen_after([key('9')])

    def inspector_actions(self):
        text = self.screen_after([])
        return text[text.index('ACTIONS'):text.index('WHAT THE EVIDENCE SAYS')] if 'WHAT THE EVIDENCE SAYS' in text else text[text.index('ACTIONS'):]

    # ---- the reason name ----------------------------------------------------------------------------------------

    def test_the_lifecycle_step_names_the_reason_and_the_code_only_where_no_reason_is_recorded(self):
        from intune_iac.workbench_screens import lifecycle_next
        current = {'freshness': {'status': 'current'}}
        step = lifecycle_next(8, current, 0.0, {'code': 'maintenance_observation_stale', 'reason': 'service_changed'})
        self.assertIn('a proposal is blocked now (service_changed)', step)
        self.assertNotIn('maintenance_observation_stale', step)
        step = lifecycle_next(8, current, 0.0, {'code': 'service_required', 'reason': None})
        self.assertIn('a proposal is blocked now (service_required)', step)

    def lost_response(self):
        from intune_iac import maintenance
        review = self.prepare()
        maintenance.execute(self.operation, approve_digest=review['approval_digest'], fault='lost-response')

    def test_at_state_5_repository_and_the_map_name_the_same_reason(self):
        from intune_iac import workbench
        self.lost_response()
        text = self.repository()
        self.assertIn('a proposal is blocked now (service_changed)', text)
        self.assertNotIn('maintenance_observation_stale', text)
        flow = workbench._workflow(self.store, OBJECT, service_root=self.service.root)
        observe = next(stage for stage in flow['stages'] if stage['id'] == 'observe')
        self.assertEqual(observe['reason'], 'service_changed')

    # ---- the newest operation -----------------------------------------------------------------------------------

    def test_the_lifecycle_step_reads_the_newest_operation(self):
        from intune_iac.workbench_screens import lifecycle_next
        current = {'freshness': {'status': 'current'}}
        plain = lifecycle_next(8, current, 0.0, None)
        self.assertIn('Prepare a proposal from the recorded intent (a: actions); 5 Plan reviews it', plain)
        prepared = dict(current, newest_operation={'short_id': '1c88de40', 'journal_status': 'prepared', 'approval_window': 'open'})
        step = lifecycle_next(8, prepared, 0.0, None)
        self.assertIn('operation 1c88de40 is already prepared', step)
        self.assertIn('5 Plan reviews it', step)
        self.assertEqual(lifecycle_next(8, current, 0.0, None, '1c88de40'), step)       # the strip's own fact says the same
        closed = dict(current, newest_operation={'short_id': '1c88de40', 'journal_status': 'prepared', 'approval_window': 'closed'})
        self.assertEqual(lifecycle_next(8, closed, 0.0, None), plain)
        delivered = dict(current, newest_operation={'short_id': '0f1a0891', 'journal_status': 'succeeded_verified', 'approval_window': None})
        step = lifecycle_next(8, delivered, 0.0, None)
        self.assertIn('operation 0f1a0891 was carried out and verified', step)
        self.assertIn('only for a new change', step)

    def test_at_state_4_a_prepared_proposal_is_named_by_repository_and_the_inspectors_first_action(self):
        self.prepare()
        text = self.repository()
        step = text[text.index('Next:'):]
        self.assertIn('is already prepared', step)
        self.assertNotIn('Next: Prepare a proposal from the recorded intent (a: actions); 5 Plan reviews it', text)
        actions = self.inspector_actions()
        self.assertRegex(actions, r'1\.\s+Prepare a proposal from the recorded intent \(available\); operation \w{8} is already prepared; this would be another')

    def test_at_state_8_a_delivered_change_is_named_by_repository_and_the_inspectors_first_action(self):
        from intune_iac import maintenance
        from intune_iac.workbench_views import record_local_deployment
        review = self.prepare()
        maintenance.execute(self.operation, approve_digest=review['approval_digest'])
        record_local_deployment(self.store, self.operation, self.intent['artifact_id'])
        self.store.collect(self.service)
        text = self.repository()
        step = text[text.index('Next:'):]
        self.assertIn('was carried out and verified', step)
        self.assertNotIn('Next: Prepare a proposal from the recorded intent (a: actions); 5 Plan reviews it', text)
        actions = self.inspector_actions()
        self.assertRegex(actions, r'1\.\s+Prepare a proposal from the recorded intent \(available\); operation \w{8} was already carried out; this is for a new change')

    def test_with_no_operation_the_wording_is_unchanged(self):
        self.import_intent()
        text = self.repository()
        self.assertIn('Next: Prepare a proposal from the recorded intent (a: actions); 5 Plan reviews it', text)
        self.assertRegex(self.inspector_actions(), r'1\.\s+Prepare a proposal from the recorded intent \(available\)')


class LayerKeyHintTests(LayerFixture):
    """Journey 34 run 2 review A Low-3: inside the workflow layer, next steps said "a lists it with the other actions" and
    "(a: actions)", but the layer's keys have no `a`. A hint drawn there names the route that works (Esc closes the layer,
    then `a`), from one shared function; outside the layer it is unchanged."""

    HINTS = (r'\(a: actions\)', r'\(a lists it\)', r'\ba lists it with the other actions')

    def squash(self, rows):
        return ' '.join(' '.join(self.plain(rows)).replace('│', ' ').split())

    def lost_response(self):
        from intune_iac import maintenance
        review = self.prepare()
        maintenance.execute(self.operation, approve_digest=review['approval_digest'], fault='lost-response')

    def stage_rows(self, step, width=100):
        """The rows the layer draws for a focused stage whose step is `step`."""
        from intune_iac.workbench_screens import workflow_detail_rows
        stage = {'id': 'observe', 'state': 'blocked', 'reason': 'service_changed', 'basis': 'a basis', 'facts': {},
                 'opens': '2', 'continuation': step}
        return self.squash(workflow_detail_rows({'operation': None}, stage, width))

    def test_the_layers_step_rows_rewrite_each_form_of_the_hint_and_leave_other_text(self):
        rows = self.stage_rows('Reconcile it (a: actions); it never replays the change')
        self.assertIn('Reconcile it (Esc, then a: actions); it never replays the change', rows)
        rows = self.stage_rows('Collect again; a lists it with the other actions.')
        self.assertIn('Collect again; Esc, then a lists it with the other actions.', rows)
        rows = self.stage_rows('Record the deployment (a lists it).')
        self.assertIn('Record the deployment (Esc, then a lists it).', rows)
        self.assertIn('a proposal is blocked now (service_changed)', self.stage_rows('a proposal is blocked now (service_changed)'))
        # Said once: a step that already names the route is not rewritten again.
        self.assertNotIn('Esc, then Esc', self.stage_rows('Reconcile it (Esc, then a: actions)'))

    def test_the_band_names_the_route_that_works_where_it_is_asked_to_in_a_layer(self):
        from intune_iac.workbench_screens import hazard_rows
        facts = {'object_id': OBJECT, 'operation': 'unknown', 'operation_id': 'a' * 32,
                 'signals': [{'area': 'operations', 'code': 'operation_outcome_unknown', 'evidence': {'operation_id': 'a' * 32}}]}
        plain = ' '.join(hazard_rows(facts, facts['signals'], 140))
        try:
            layered = ' '.join(hazard_rows(facts, facts['signals'], 140, layered=True))
        except TypeError:
            self.fail('the band cannot be asked to name the route that works inside a layer')
        self.assertIn('(a: actions)', plain)
        self.assertIn('(Esc, then a: actions)', layered)
        self.assertNotIn('(a: actions)', layered)

    def layer_texts(self):
        """The pane of the layer, below the band, with each of the eleven stages focused."""
        texts = []
        for stage in range(11):
            _, frames = self.open_layer((120, 40), 'unicode', extra=['up'] * 12 + ['down'] * stage)
            rows = self.plain(frames[-1])
            start = next(index for index, row in enumerate(rows) if row.startswith('┌'))
            texts.append(self.squash(rows[start:]))
        return texts

    def test_inside_the_layer_a_hint_names_esc_then_a_at_every_stage(self):
        self.lost_response()
        named = 0
        for text in self.layer_texts():
            self.assertIn('[WORKFLOW]', text)
            for hint in self.HINTS:
                for found in re.finditer(hint, text):
                    self.assertTrue(text[:found.start()].rstrip().endswith('Esc, then'),
                                    'a hint names a key the layer lacks: ...%s' % text[max(0, found.start() - 40):found.end()])
            named += text.count('Esc, then a')
        self.assertGreater(named, 0)                                  # the state has steps that name the actions list
    def test_outside_the_layer_the_hint_is_unchanged(self):
        self.lost_response()
        _, frames = self.run_keys(typed('select ' + OBJECT) + [key('9')] + [key('q')], (120, 40), 'unicode')
        text = self.squash(frames[-1])
        self.assertIn('Reconcile it (a: actions)', text)             # the hazard band on the Repository surface
        self.assertNotIn('Esc, then a', text)


class ReconciledIsNotProofTests(LayerFixture):
    """Sol review of c679413, finding 1: a reconciliation can find the change NOT applied, so `reconciled` alone gets the
    plain prepare step. The new-change wording needs the carried-out-and-verified status. (The read model holds a
    reconciliation `classification` at workbench_diagnostics.py:228-229, but this step does not read it.)"""

    def test_reconciled_alone_gets_the_plain_prepare_step(self):
        from intune_iac.workbench_screens import lifecycle_next
        current = {'freshness': {'status': 'current'}}
        plain = lifecycle_next(8, current, 0.0, None)
        reconciled = dict(current, newest_operation={'short_id': '0f1a0891', 'journal_status': 'reconciled'})
        step = lifecycle_next(8, reconciled, 0.0, None)
        self.assertNotIn('only for a new change', step)
        self.assertEqual(step, plain)
        verified = dict(current, newest_operation={'short_id': '0f1a0891', 'journal_status': 'succeeded_verified'})
        self.assertIn('only for a new change', lifecycle_next(8, verified, 0.0, None))

    def test_reconciled_gets_no_note_on_the_inspector_action(self):
        from intune_iac.workbench import _proposal_note
        prefixes = {'a' * 32: '0f1a0891'}
        attention = {'newest_operation': {'operation_id': 'a' * 32, 'journal_status': 'reconciled'}}
        self.assertIsNone(_proposal_note(None, attention, prefixes))
        attention['newest_operation']['journal_status'] = 'succeeded_verified'
        self.assertIn('already carried out', _proposal_note(None, attention, prefixes))


if __name__ == '__main__':
    unittest.main()
