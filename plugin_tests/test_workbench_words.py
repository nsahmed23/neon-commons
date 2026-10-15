"""Words where the screens showed raw values or unscoped claims (journey 26 run 3 frame review, items 3, 5, 6, 8, 9,
15, 16, 17, 22, 24, 26, 27 and 28; logs/journey-26/FRAME-REVIEW-run3.md in the custody records).

Each screen keeps its exact values in the typed details (e) and the raw record (r); the summary says what they mean.
Expected words are written by hand.
"""
import tempfile
import unittest
from pathlib import Path

TENANT = '11111111-1111-4111-8111-111111111111'
POLICY = '22222222-2222-4222-8222-222222222222'


def text(lines):
    return ' '.join(' '.join(lines).split())


class ScreenWordTests(unittest.TestCase):
    def test_estate_filters_read_as_words_and_echo_the_search(self):
        # Items 3 and 27: "Global filters: {json}" on a cleared page; a search page that did not say what it searched.
        from intune_iac.workbench_screens import filter_words
        self.assertEqual(filter_words({'query': '', 'ownership': None, 'coverage': None, 'health': None}), 'No filters applied.')
        self.assertEqual(filter_words({'query': 'Pilot', 'ownership': 'unknown', 'coverage': 'stale_or_incomplete', 'health': None}),
                         'Filters: search "Pilot"; ownership unknown; coverage stale or incomplete.')

    def test_health_and_collection_times_are_readable(self):
        # Item 9: "as of 2026-10-14T22:25:35Z".
        from intune_iac.workbench_screens import _collection_lines, _object_health
        lines = text(_object_health({'name': 'Pilot', 'object_id': POLICY}, {
            'as_of': '2026-10-14T22:25:35Z', 'evidence_class': 'synthetic', 'cohort_version': 'v1',
            'targeted': 100, 'eligible': 100, 'excluded': 0, 'stages': {}}, 120))
        self.assertIn('as of 2026-10-14 22:25:35 UTC | cohort v1', lines)
        self.assertNotIn('22:25:35Z', lines)
        lines = text(_collection_lines({'freshness': 'fresh', 'last_success': {
            'completed_at': '2026-10-14T22:40:01.387953Z', 'run_id': 3, 'status': 'complete', 'error_code': None}}, 120))
        self.assertIn('Last success 2026-10-14 22:40:01 UTC | run 3 | complete | error none', lines)

    def test_device_matrix_rows_say_which_devices_they_hold(self):
        # Item 8: 100 devices in two rows of 50 read as a second, unlabelled bar.
        from intune_iac.workbench_screens import _matrix
        lines = _matrix((100, 8, 8, 0, 0, 0, 92), 80)
        bars = [line for line in lines if '[' in line]
        self.assertEqual(len(bars), 2)
        self.assertTrue(bars[0].strip().startswith('devices 1-50'), bars[0])
        self.assertTrue(bars[1].strip().startswith('devices 51-100'), bars[1])
        # Narrower, the label keeps its room and the rows shorten: every row still says which devices it holds.
        bars = [line.strip() for line in _matrix((100, 8, 8, 0, 0, 0, 92), 70) if '[' in line]
        self.assertEqual([bar.split('[')[0].strip() for bar in bars], ['devices 1-48', 'devices 49-96', 'devices 97-100'])
        self.assertTrue(all(len(line) <= 70 for line in _matrix((100, 8, 8, 0, 0, 0, 92), 70)))
        self.assertIn('each cell is 1 device', text(lines))
        single = [line for line in _matrix((30, 30, 30, 0, 0, 0, 0), 70) if '[' in line]
        self.assertEqual(len(single), 1)
        self.assertTrue(single[0].strip().startswith('['), single[0])

    def test_diagnostics_scope_the_device_evidence_claim_and_point_at_the_queue(self):
        # Item 6: "clear: the capture is complete" and "1 signal needs attention" beside three queue findings.
        from intune_iac.workbench_screens import diagnostics_lines
        signal = {'area': 'freshness', 'code': 'observation_stale', 'observed': 'The newest observation is stale.',
                  'next_step': 'Collect again.', 'evidence': {}}
        lines = text(diagnostics_lines({'name': 'Pilot', 'object_id': POLICY, 'signals': [signal],
                                        'checked': {'device_evidence': 'clear'}}, 140))
        self.assertIn('1 signal needs attention; reporting completeness and ownership are reviewed in the maintenance '
                      'queue (m)', lines)
        self.assertIn('device evidence capture complete and cohort consistent; whether devices reported is not judged '
                      'here (h shows the counts)', lines)
        self.assertNotIn('clear: the capture', lines)

    def test_diagnostics_evidence_reads_as_words(self):
        # Item 5: raw keys, ISO times and a JSON array.
        from intune_iac.workbench_screens import diagnostics_lines
        signal = {'area': 'freshness', 'code': 'observation_stale', 'observed': 'The newest observation is stale.',
                  'next_step': 'Wait.', 'evidence': {'snapshot_id': '599f74fd' + 'f' * 56,
                                                     'observed_at': '2026-10-14T22:40:01.387953Z',
                                                     'freshness_checked_at': '2026-10-14T22:36:01.712575Z',
                                                     'freshness_reasons': ['stamped_after_now']}}
        lines = text(diagnostics_lines({'name': 'Pilot', 'object_id': POLICY, 'signals': [signal], 'checked': {}}, 160))
        self.assertIn("Evidence snapshot 599f74fdffff; observed at 2026-10-14 22:40:01 UTC; freshness checked at "
                      "2026-10-14 22:36:01 UTC; freshness reasons: stamped after this host's clock", lines)
        self.assertNotIn('["', lines)
        self.assertNotIn('T22:40', lines)

    def test_families_and_the_writer_read_as_words(self):
        # Items 22 and 24: "live qualification: not_run" and "writer unknown: ownership_index_missing".
        from intune_iac.workbench_screens import families_lines, relationship_lines
        lines = text(families_lines({'available': True, 'source': {'path': 'family-coverage.csv', 'sha256': 'd' * 64},
                                     'families': [{'family': 'Windows', 'live': 'not_run'}]}, 120))
        self.assertIn('live qualification: not run.', lines)
        lines = text(relationship_lines({'object_id': POLICY, 'edges': [], 'ownership': 'unknown',
                                         'ownership_evidence': {'reason': 'ownership_index_missing'}}, 120))
        self.assertIn('writer unknown (ownership index missing)', lines)
        self.assertNotIn('ownership_index_missing', lines)


class WorkspaceWordTests(unittest.TestCase):
    def workspace(self, tab, value, mode_class='synthetic'):
        from intune_iac.workbench_tui import Workspace
        workspace = Workspace.__new__(Workspace)
        workspace.__dict__.update(tab=tab, value=value, selected=POLICY, facts={'object_id': POLICY}, mode_class=mode_class,
                                  rows=[], layer='summary', last_command='views', store=type('S', (), {'tenant_id': TENANT})())
        return workspace

    def test_coverage_states_read_as_statements(self):
        # Item 28: "Ownership freshness: no", "Repository: recorded".
        value = {'schema_version': 'workbench-four-views/1', 'repository': {'status': 'recorded'},
                 'observed': {'status': 'recorded'}, 'proposed': {'status': 'not_recorded'},
                 'coverage': {'observation': 'stale_or_incomplete', 'management': 'unknown', 'state_tracked': 'not_recorded',
                              'mapping': 'supported_comparison_only', 'platform_qualified': False,
                              'ownership': {'declared_scope_complete': False, 'fresh': False}}, 'comparisons': {}}
        lines = text(self.workspace(6, value)._surface_summary(120))
        for words in ('Repository intent: recorded', 'Observation: recorded', 'Proposal: not recorded',
                      'Platform qualification: not qualified',
                      'Ownership: declared scope not complete; ownership index not fresh'):
            self.assertIn(words, lines)
        self.assertNotIn('Ownership freshness', lines)
        self.assertNotIn(': no ', lines + ' ')

    def test_an_estate_page_names_the_estate_evidence_class(self):
        # Item 26: "[evidence class not stated]" on filtered and searched pages of the same synthetic estate.
        workspace = self.workspace(0, {'objects': [], 'filters': {'query': 'x'}})
        self.assertEqual(workspace._scope({}), 'synthetic')
        self.assertEqual(self.workspace(7, {'navigation': []})._scope({}), 'evidence class not stated')


class SurveyWordTests(unittest.TestCase):
    def test_a_journey_session_reads_as_words(self):
        # Item 16: "complete_simulation | next complete_simulation | 17 of 17 stages verify".
        from intune_iac.entry import _summary
        item = {'kind': 'journey_session', 'lifecycle': 'complete_simulation', 'next_state': 'complete_simulation',
                'verified': 17, 'states': {'configured': True}}
        self.assertEqual(_summary(item), 'complete simulation | 17 of 17 stages verified as completed')
        item = dict(item, lifecycle='in_progress', next_state='await_approval', verified=9)
        self.assertEqual(_summary(item), 'in progress | next await approval | 9 of 17 stages verified as completed')

    def test_each_item_says_it_is_usable_here_not_configured(self):
        # Item 15: "configured" on every row beside "No live discovery connection is configured".
        from intune_iac.entry import start_lines
        value = {'directory': '/work', 'items': [{'kind': 'store', 'path': 'store', 'tenant_id': TENANT, 'objects': 1,
                                                 'freshness': 'fresh', 'intents': [], 'operations': 0,
                                                 'states': {'configured': True, 'authenticated': 'offline',
                                                            'qualified': 'synthetic_only'}}],
                 'next_actions': [], 'missing': [], 'notes': []}
        lines = text(start_lines(value, 120))
        self.assertIn('discovered | usable here |', lines)
        self.assertNotIn('| configured |', lines)

    def test_the_store_counts_operations_not_journal_records(self):
        # Item 17: "2 operations" for one operation with two records.
        from intune_iac.entry import _store_item
        from intune_iac.workbench_store import WorkbenchStore
        with tempfile.TemporaryDirectory() as directory:
            store = WorkbenchStore.create(Path(directory) / 'store', TENANT)
            store.record_operation('op-1', {'object_id': POLICY, 'status': 'prepared'})
            store.record_operation('op-1', {'object_id': POLICY, 'status': 'executed'})
            item = _store_item(Path(directory), store.root, 'store')
            self.assertEqual(item['operations'], 1)


class ReviewWordTests(unittest.TestCase):
    """Journey 27 run 2's reviews (logs/journey-27/FRAME-REVIEW-run2.md, Sonnet 2, 3, 4, 5, 6, 8, 12, 13, 22, 27, 29,
    30; Gemini new problem 3)."""

    def workspace(self, tab, value, **extra):
        from intune_iac.workbench_tui import Workspace
        workspace = Workspace.__new__(Workspace)
        workspace.__dict__.update(dict(tab=tab, value=value, selected=POLICY, facts={'object_id': POLICY}, mode_class='synthetic',
                                       rows=[], operation_rows=[], operation_highlight=0, layer='summary', last_command='review',
                                       store=type('S', (), {'tenant_id': TENANT})()), **extra)
        return workspace

    def test_the_plan_review_names_its_values_in_words(self):
        value = {'operation_id': 'a' * 32, 'status': 'outcome_unknown', 'saved_plan_sha256': 'c' * 64,
                 'approval_digest': 'b' * 64, 'evidence_class': 'synthetic_local_process_and_modeled_service_only',
                 'changes': [POLICY + ':description_changed'],
                 'field_changes': {'status': 'changed', 'complete': True, 'changes': [
                     {'path': '/description', 'kind': 'replaced', 'before': 'x', 'after': 'y'}]}}
        lines = text(self.workspace(4, value)._surface_summary(160))
        self.assertIn('Status: outcome unknown', lines)
        self.assertIn('Review digest (execute needs it): ' + 'b' * 64, lines)
        self.assertNotIn('Approval binding', lines)
        self.assertIn('Evidence class: synthetic local process and modeled service only', lines)
        self.assertIn('Plan changes: description changed (22222222)', lines)

    def test_an_execution_error_reads_as_words_with_its_code(self):
        value = {'result': {'operation_id': 'a' * 32, 'status': 'outcome_unknown', 'error': {'code': 'model_response_lost'},
                            'evidence_class': 'synthetic_local_process_and_modeled_service_only'}}
        lines = text(self.workspace(5, value)._surface_summary(160))
        self.assertIn("Error: the modeled service's response was lost (model_response_lost)", lines)

    def test_an_empty_operations_list_says_so(self):
        workspace = self.workspace(5, {'operations': []})
        lines = text(workspace._summary_lines(120))
        self.assertIn('[OPERATIONS] None recorded in this store yet.', lines)

    def test_the_operations_list_reads_as_words(self):
        workspace = self.workspace(5, {'operations': [{}]}, operation_rows=[
            {'operation_id': 'a' * 32, 'recorded_at': '2026-10-14T23:58:28Z', 'status': 'succeeded_verified',
             'operation_root': '/work/op', 'journal_records': 3}])
        lines = text(workspace._summary_lines(160))
        self.assertIn('recorded 2026-10-14 23:58:28 UTC | succeeded verified (3 journal records)', lines)
        self.assertNotIn('status=', lines)

    def test_a_notice_names_the_status_in_words_and_ids_at_one_length(self):
        workspace = self.workspace(5, {}, last_command='execute /work/op digest')
        self.assertEqual(workspace._notice_for({'status': 'outcome_unknown'}),
                         'execute ran; the engine reported status outcome unknown.')
        workspace.last_command = 'repository-refresh ' + 'c' * 40
        self.assertEqual(workspace._notice_for({'artifact_id': 'd' * 64, 'kind': 'repository_intent'}),
                         'repository-refresh recorded repository intent dddddddddddd.')

    def test_a_refusal_says_its_cause_once(self):
        # Gemini 3: the engine's message, "What it means" and "Next" said the same thing three times.
        from intune_iac.workbench_screens import refusal_lines
        message = 'The repository changed again after its difference was shown; review the difference again before recording it.'
        lines = text(refusal_lines({'error': {'code': 'workbench_difference_changed', 'message': message,
                                              'effects': {'intent_recorded': False, 'retained_intent': 'a' * 64}}}, 160))
        self.assertIn('Cause: The repository changed after you reviewed its difference.', lines)
        self.assertNotIn(message, lines)
        self.assertIn("The engine's own message is in the typed details (e).", lines)
        # A message that names something specific (a setting, a path, a value) stays on screen.
        specific = 'The desired policy uses device_vendor_msft_policy_config_x_1, outside the capability map.'
        lines = text(refusal_lines({'error': {'code': 'workbench_desired_capability', 'message': specific}}, 160))
        self.assertIn(specific, lines)
        self.assertNotIn('the message above names it', lines)
        # An unknown code shows the engine's message alone.
        lines = text(refusal_lines({'error': {'code': 'x_unknown', 'message': 'Something failed.'}}, 160))
        self.assertIn('Something failed.', lines)

    def test_diagnostics_names_the_proposal_s_own_observation_check(self):
        # Sonnet 3 and 4: "freshness clear" and "1 signal" beside a source that changed since capture.
        from intune_iac.workbench_screens import diagnostics_lines
        signal = {'area': 'operations', 'code': 'operation_outcome_unknown', 'observed': 'Outcome unknown.',
                  'next_step': 'Reconcile.', 'evidence': {'journal_status': 'outcome_unknown',
                                                          'recorded_at': '2026-10-14T23:58:28.005714Z'}}
        check = {'code': 'maintenance_observation_stale', 'reason': 'service_changed', 'observed_revision': 2,
                 'service_revision': 3}
        lines = text(diagnostics_lines({'name': 'Pilot', 'object_id': POLICY, 'signals': [signal],
                                        'checked': {'freshness': 'clear'}}, 160, check=check))
        self.assertIn("1 signal and the proposal's observation check need attention", lines)
        self.assertIn('The source changed since this observation was captured (revision 2, now 3)', lines)
        self.assertIn('freshness clear by age', lines)
        self.assertIn('journal status outcome unknown; recorded at 2026-10-14 23:58:28 UTC', lines)

    def test_the_inspector_says_a_opens_the_actions(self):
        from intune_iac.workbench_screens import inspector_lines
        value = {'object_id': POLICY, 'name': 'Pilot', 'body': {}, 'attention': {'status': 'clear', 'signals': [], 'checked': {}},
                 'actions': [{'kind': 'collect', 'label': 'Collect again', 'available': True, 'command': 'collect',
                              'summary': 'Reads.', 'effects': 'Reads.'}]}
        lines = text(inspector_lines(value, 160))
        self.assertIn('a opens the actions; Enter there stages one for review', lines)
        self.assertNotIn('a stages one', lines)


class JourneyTwentyEightWordsTests(unittest.TestCase):
    """Journey 28 run 2's frame review (logs/journey-28/FRAME-REVIEW-run2.md), items S6, G2 and G4."""

    def test_a_changed_source_refusal_says_its_cause_and_next_step(self):
        from intune_iac.workbench_screens import refusal_lines
        lines = text(refusal_lines({'error': {'code': 'maintenance_source_changed', 'message': 'Maintenance evidence is '
                                              'incomplete, changed, stale, or outside the local model profile.'}}, 160))
        self.assertIn('Cause: A file this proposal bound changed after it was prepared', lines)
        self.assertIn('Next: Prepare a proposal again (a: actions)', lines)

    def test_the_refused_refresh_names_the_same_next_action_as_the_band(self):
        from intune_iac.workbench_screens import REFUSALS
        self.assertIn('then Refresh the repository intent (a: actions)', REFUSALS['workbench_difference_changed'][1])

    def test_a_proposal_action_says_nothing_is_approved_or_sent_once(self):
        from intune_iac.workbench import ACTION_EFFECTS, ACTION_SUMMARY
        for kind in ('propose-from-intent', 'propose'):
            said = (ACTION_SUMMARY[kind] + ' ' + ACTION_EFFECTS[kind]).lower().count('nothing is approved or sent')
            self.assertEqual(said, 1, kind)


class SayItOnceTests(unittest.TestCase):
    """Journey 28 run 3, frame 24: a refusal says each fact once; the engine's effect facts win over the cause's copy."""

    def test_a_clock_hold_says_nothing_was_dispatched_once(self):
        from intune_iac.workbench_screens import refusal_lines
        lines = text(refusal_lines({'error': {'code': 'clock_moved_backward', 'message': 'Refused.',
                                              'effects': {'dispatched': False}}}, 160))
        self.assertEqual(lines.count('Nothing was dispatched.'), 1, lines)
        self.assertIn('Effect: Nothing was dispatched.', lines)

    def test_without_the_engine_facts_the_cause_keeps_it(self):
        from intune_iac.workbench_screens import refusal_lines
        lines = text(refusal_lines({'error': {'code': 'clock_moved_backward', 'message': 'Refused.'}}, 160))
        self.assertEqual(lines.count('Nothing was dispatched.'), 1, lines)


class RunThreeWordsTests(unittest.TestCase):
    """Journey 28 run 3: the :cancel notice fits a narrow line; a blocked action names what the engine named."""

    def test_the_cancel_notice_fits_eighty_columns(self):
        from intune_iac.workbench_tui import CANCEL_NOTICE
        self.assertIn('Nothing is running to cancel', CANCEL_NOTICE)
        self.assertLessEqual(len(CANCEL_NOTICE), 78)

    def test_a_blocked_action_shows_the_engines_specific_message(self):
        from intune_iac.workbench_screens import actions_lines
        message = ('Setting device_vendor_msft_policy_config_x: value device_vendor_msft_policy_config_x_1 is not a '
                   'supported value for this setting in the offline capability map (supported: '
                   'device_vendor_msft_policy_config_x_2). The reference component cannot propose it.')
        value = {'attention': {'status': 'clear', 'signals': [], 'checked': {}},
                 'actions': [{'kind': 'propose-from-intent', 'label': 'Prepare a proposal from the recorded intent',
                              'available': False,
                              'blocked': {'code': 'workbench_desired_capability', 'message': message}}]}
        lines = text(actions_lines(value['actions'], 0, 200))
        self.assertIn('device_vendor_msft_policy_config_x_1', lines)


class CodesInSentencesTests(unittest.TestCase):
    """Journey 28 run 3, review R7: a known code reads as words inside a sentence; the code stays in brackets."""

    def test_a_refused_approval_in_the_history(self):
        from intune_iac.workbench_screens import _event_text
        text = _event_text({'kind': 'approval_refused', 'fields': {'code': 'expired_request'}})
        self.assertEqual(text, 'the approval window had closed (expired_request); nothing was dispatched')
        self.assertEqual(_event_text({'kind': 'approval_refused', 'fields': {'code': 'x_unknown'}}),
                         'x_unknown; nothing was dispatched')

    def test_an_unknown_outcome_names_the_error_in_words(self):
        from intune_iac.workbench_diagnostics import unknown_outcome_words
        self.assertEqual(unknown_outcome_words('model_response_lost'),
                         "the modeled service's response was lost (model_response_lost)")
        self.assertEqual(unknown_outcome_words('other_code'), 'other_code')


class ClockHoldWordTests(unittest.TestCase):
    """A clock hold on an observation's age reads as words in every place that words a freshness reason (the codes
    are the store's; the sentences are written by hand)."""
    MOVED = "its age cannot be established: this host's clock reads earlier than a time this workspace recorded"
    UNREADABLE = 'its age cannot be established: the time this workspace recorded cannot be read'
    CODES = (('clock_moved_backward', MOVED), ('clock_floor_invalid', UNREADABLE))

    def test_every_freshness_word_map_has_both_codes(self):
        from intune_iac import workbench, workbench_diagnostics, workbench_screens
        for code, words in self.CODES:
            self.assertEqual(workbench.FRESHNESS_REASON_WORDS.get(code), words)
            self.assertEqual(workbench_screens.FRESHNESS_REASON_WORDS.get(code), words)
            self.assertEqual(workbench_diagnostics.FRESHNESS_WORDS.get(code), words)

    def test_the_observation_state_line_reads_each_code_as_words(self):
        from intune_iac.workbench_screens import state_lines
        for code, words in self.CODES:
            states = {'observation': {'freshness': 'stale', 'freshness_reasons': [code], 'observed_at': '2026-10-14T22:40:01Z'}}
            lines = text(state_lines(states, 200))
            # PKG-PRES-RUN4 item 18: a held age reads "age not known", as the strip and the attention item do, never
            # "stale", and the cause is said once.
            self.assertIn('age not known (%s)' % words.split(': ', 1)[1], lines)
            self.assertNotIn('stale', lines)
            self.assertNotIn('cannot be established', lines.replace('cannot be read', ''))
            self.assertNotIn(code, lines)

    def test_diagnostics_evidence_reads_each_code_as_words(self):
        from intune_iac.workbench_screens import diagnostics_lines
        for code, words in self.CODES:
            signal = {'area': 'freshness', 'code': 'observation_stale', 'observed': 'The newest observation is stale.',
                      'next_step': 'Wait.', 'evidence': {'freshness_reasons': [code]}}
            lines = text(diagnostics_lines({'name': 'Pilot', 'object_id': POLICY, 'signals': [signal], 'checked': {}}, 200))
            self.assertIn('freshness reasons: ' + words, lines)
            self.assertNotIn(code, lines)

    def test_the_diagnostics_sentence_reads_each_code_as_words(self):
        from intune_iac.workbench_diagnostics import _freshness
        for code, words in self.CODES:
            signals, _ = _freshness({'freshness': 'stale', 'observed_at': '2026-10-14T22:40:01Z', 'freshness_reasons': [code],
                                     'freshness_checked_at': '2026-10-14T22:36:01Z'}, False)
            self.assertIn(': ' + words + '.', signals[0]['observed'])
            self.assertNotIn(code, signals[0]['observed'])

    def test_the_refusal_sentence_reads_each_code_as_words(self):
        from intune_iac.workbench import _reason_words
        for code, words in self.CODES:
            sentence = _reason_words({'reason': 'not_fresh', 'freshness_reasons': [code]})
            # PKG-PRES-HOLD item 4: the verdict is said once, in front of the cause, never twice.
            self.assertIn(words.split(': ', 1)[1], sentence)
            self.assertEqual(sentence.count('age cannot be established'), 1, sentence)
            self.assertNotIn(code, sentence)


class RunFourWordsTests(unittest.TestCase):
    """PKG-PRES-RUN4: the presentation defects of journey 28 runs 4 and 5 (FRAME-REVIEW-run4-5.md, triage items 7 to 18)."""
    workspace = ReviewWordTests.workspace
    CLOSED = {'operation_id': 'a' * 32, 'object_id': POLICY, 'status': 'prepared', 'saved_plan_sha256': 'c' * 64,
              'approval_digest': 'b' * 64, 'expires_at': 1791980997,
              'evidence_class': 'synthetic_local_process_and_modeled_service_only',
              'approval_window': {'opens_at': 1791980697, 'closes_at': 1791980997, 'state': 'closed'}}
    ELIGIBILITY = {'code': 'maintenance_observation_stale', 'reason': 'service_changed', 'observed_revision': 1,
                   'service_revision': 2}

    def closed(self, state):
        return dict(self.CLOSED, approval_window=dict(self.CLOSED['approval_window'], state=state))

    def test_an_expired_plan_review_does_not_offer_the_review_digest(self):
        # Item 7 (run 4 frame 70): "Review digest (execute needs it)" beside "Approval window: closed".
        for state in ('closed', 'closed_recorded'):
            lines = text(self.workspace(4, self.closed(state))._surface_summary(160))
            self.assertNotIn('execute needs it', lines, state)
            self.assertNotIn('b' * 64, lines)
            self.assertIn('Review digest: not offered; the approval window closed, so execute can no longer run this '
                          'plan. Prepare a new proposal (a: actions)', lines)
        still_open = text(self.workspace(4, self.closed('open'))._surface_summary(160))
        self.assertIn('Review digest (execute needs it): ' + 'b' * 64, still_open)

    def test_the_strip_says_the_window_closed_not_prepared(self):
        # Item 9 (run 3 R5, run 4 frames 72 to 77): "OP prepared" beside an expired approval.
        for state in ('closed', 'closed_recorded'):
            workspace = self.workspace(4, {})
            workspace.last_command = 'review /w/op'
            workspace._learn(self.closed(state))
            line = workspace._context_strip(120)
            self.assertIn('OP expired', line, state)
            self.assertNotIn('OP prepared', line)
        workspace = self.workspace(4, {})
        workspace.last_command = 'review /w/op'
        workspace._learn(self.closed('open'))
        self.assertIn('OP prepared', workspace._context_strip(120))

    def test_the_strip_says_the_window_closed_from_the_delivery_view_too(self):
        value = {'schema_version': 'workbench-delivery/1', 'object_id': POLICY, 'operation_id': 'a' * 32,
                 'journal_status': 'prepared', 'stages': [{'stage': 'approval', 'status': 'expired', 'recorded': True}]}
        workspace = self.workspace(5, {})
        workspace.last_command = 'delivery /w/op'
        workspace._learn(value)
        self.assertIn('OP expired', workspace._context_strip(120))
        value['stages'] = [{'stage': 'approval', 'status': 'waiting'}]
        workspace._learn(value)
        self.assertIn('OP prepared', workspace._context_strip(120))

    def test_a_reconcile_after_an_interruption_says_so_beside_no_error(self):
        # Item 11 (frame 38): "Recorded before reconcile: no error" beside an outcome that was unknown.
        result = {'operation_id': 'a' * 32, 'journal_status': 'reconciled', 'previous_status': 'outcome_unknown',
                  'previous_error_code': None, 'classification': 'desired_state_observed',
                  'evidence_class': 'synthetic_local_process_and_modeled_service_only', 'effects': {'replayed': False}}
        lines = text(self.workspace(5, {'result': result})._surface_summary(160))
        self.assertIn('Recorded before reconcile: no error recorded; the run was interrupted', lines)
        lines = text(self.workspace(5, {'result': dict(result, previous_error_code='model_response_lost')})._surface_summary(160))
        self.assertIn("Recorded before reconcile: the modeled service's response was lost (model_response_lost)", lines)
        self.assertNotIn('interrupted', lines)
        lines = text(self.workspace(5, {'result': dict(result, previous_status='prepared')})._surface_summary(160))
        self.assertIn('Recorded before reconcile: no error', lines)
        self.assertNotIn('interrupted', lines)

    def test_a_message_that_says_the_meaning_leaves_what_it_means_out(self):
        # Item 12 (run 4 frame 67): the message and "What it means" said the same thing.
        from intune_iac.workbench_screens import refusal_lines
        message = ('This operation cites repository intent ' + '8559b6b3b2471ed098e8f602a61c3d616c1a61d2c0468e1a4346b3a731709b78' + ', not the intent given; record the deployment '
                   'with the intent it cites.')
        lines = text(refusal_lines({'error': {'code': 'workbench_deployment_intent_not_cited', 'message': message,
                                              'effects': {'deployment_recorded': False}}}, 200))
        self.assertIn(message, lines)
        self.assertNotIn('What it means', lines)
        self.assertIn('Effect: No deployment receipt was recorded.', lines)
        # A message that names something the meaning cannot, and does not repeat it, keeps the meaning's line.
        specific = 'The desired policy uses device_vendor_msft_policy_config_x_1, outside the capability map.'
        lines = text(refusal_lines({'error': {'code': 'workbench_desired_capability', 'message': specific}}, 200))
        self.assertIn('What it means', lines)

    def test_the_band_leads_the_next_step_when_the_screen_gives_another(self):
        # Item 13 (run 4 frames 19 and 20; Gemini N 3): the band says "Collect again", the lifecycle line says "v".
        from plugin_tests.test_workbench_screens import delivery_value
        from plugin_tests.test_workbench_states import RefusalCauseTests
        workspace = RefusalCauseTests.workspace(self, {'eligibility': self.ELIGIBILITY})
        workspace.tab = 5
        workspace.value = {'result': {'operation_id': 'a' * 32, 'status': 'succeeded_verified',
                                      'evidence_class': 'synthetic_local_process_and_modeled_service_only'}}
        order = 'The step in the band above comes first.'
        self.assertIn(order, text(workspace._summary_lines(118)))
        workspace.value = delivery_value()
        self.assertIn(order, text(workspace._summary_lines(118)))
        # Nothing in the band, nothing to put in order.
        workspace.facts = {'object_id': workspace.facts['object_id']}
        self.assertNotIn(order, text(workspace._summary_lines(118)))
        workspace.value = {'result': {'operation_id': 'a' * 32, 'status': 'succeeded_verified'}}
        self.assertNotIn(order, text(workspace._summary_lines(118)))

    def test_a_key_named_in_the_footer_cannot_be_mistaken_for_another(self):
        # Item 14 (Gemini O 6): both i and e were labelled "details".
        from intune_iac.workbench_tui import band_keys, help_line
        keys = band_keys(['! Observation stale. Next: Collect again (a: actions)', '! Age unknown. Correct it (i: details)'])
        self.assertEqual(keys, ('a actions', 'i diagnostics'))
        line = help_line(120, lead=keys)
        self.assertIn('i diagnostics', line)
        self.assertNotIn('i details', line)
        self.assertIn('e details', line)
        self.assertLessEqual(len(help_line(60, lead=keys)), 60)

    def test_a_key_named_in_a_refusal_or_the_inspector_is_explained_where_it_is_named(self):
        # Item 14 (Gemini N 1; Gemini O 5): v on an Execution refusal, d on the Inspector.
        from intune_iac.workbench_screens import REFUSALS, _setting_summary
        self.assertIn('v opens Delivery', REFUSALS['maintenance_replay_forbidden'][1])
        self.assertIn('v opens Delivery', REFUSALS['expired_request'][1])
        instance = {'@odata.type': '#microsoft.graph.deviceManagementConfigurationChoiceSettingInstance',
                    'settingDefinitionId': 'device_vendor_msft_x',
                    'choiceSettingValue': {'value': 'device_vendor_msft_x_1', 'children': []}}
        lines = text(_setting_summary(instance, 160))
        self.assertIn('Press d to open the setting dictionary and inspect the available setting metadata', lines)

    def test_one_label_means_one_thing_on_adjacent_lines(self):
        # Item 15 (Gemini N 2): "Evidence synthetic_local_process_..." above "Evidence: e typed details | r raw record".
        from plugin_tests.test_workbench_screens import delivery_value
        from intune_iac.workbench_screens import delivery_lines
        lines = delivery_lines(delivery_value(), 160)
        found = [line for line in lines if line.startswith('Evidence')]
        self.assertEqual(found, ['Evidence class synthetic local process and modeled service only | not native-provider '
                                 'qualified | no cloud authority'])
        value = {'result': {'operation_id': 'a' * 32, 'status': 'succeeded_verified',
                            'evidence_class': 'synthetic_local_process_and_modeled_service_only'}}
        lines = self.workspace(5, value)._data_lines(160)
        self.assertEqual(len([line for line in lines if line.startswith('Evidence:')]), 1, lines)
        self.assertIn('Evidence class: synthetic local process and modeled service only', text(lines))

    def test_the_strip_keeps_the_policy_name_beside_the_hazards_at_120_columns(self):
        # Item 15 (Gemini N 6): the name fell away on Execution while the other surfaces showed it.
        from intune_iac.workbench_screens import context_strip
        facts = {'name': 'Windows Privacy Pilot', 'observation': 'fresh', 'repository': 'current',
                 'operation': 'outcome_unknown', 'eligibility': self.ELIGIBILITY}
        line = context_strip('11111111-1111-4111-8111-111111111111', POLICY, facts, 120,
                             'synthetic_local_process_and_modeled_service_only')
        self.assertLessEqual(len(line), 120, line)
        self.assertIn('POLICY Windows Privacy Pilot (22222222)', line)
        self.assertIn('OBS source changed', line)
        self.assertIn('OP unknown', line)

    def test_an_unreadable_file_names_the_file_and_the_next_step(self):
        # Item 16 (Sonnet 6; Gemini O 4): "A required local file could not be read." with no file and no way on.
        from plugin_tests.test_workbench_states import RefusalCauseTests
        refused = {'status': 'error', 'error': {'code': 'unreadable_file', 'message': 'A required local file could not be read.'}}
        with tempfile.TemporaryDirectory() as directory:
            operation = Path(directory) / 'op dir'
            operation.mkdir()
            for name in ('journal.json', 'desired.json'):
                (operation / name).write_text('{}')
            workspace = RefusalCauseTests.workspace(self, None, "execute '%s' %s" % (operation, 'd' * 64))
            workspace.receive(dict(refused))
            lines = text(workspace._surface_summary(300))
            self.assertIn('[REFUSED] unreadable_file', lines)
            self.assertIn('could not be read: %s (it does not exist)' % (operation / 'plan.json'), lines)
            self.assertNotIn(str(operation / 'journal.json'), lines)
            self.assertIn("Next: Check that the file exists and this account can read it", lines)
            # A typed path that is missing is named; nothing outside the typed command is named, and no content is read.
            missing = Path(directory) / 'missing.json'
            workspace = RefusalCauseTests.workspace(self, None, "propose '%s' /w/new" % missing)
            workspace.receive(dict(refused))
            self.assertIn('%s (it does not exist)' % missing, text(workspace._surface_summary(300)))
            # Nothing found unreadable: the screen says the engine did not name the file, and what to check.
            workspace = RefusalCauseTests.workspace(self, None, 'inspect')
            workspace.receive(dict(refused))
            lines = text(workspace._surface_summary(300))
            self.assertIn('the engine does not name it', lines)
            self.assertIn('Next: Check that the files the command names exist', lines)

    def test_a_quoted_path_is_not_split_where_the_line_can_hold_it(self):
        # Item 17 (frames 20 and 41): a journey path split inside a quoted argument.
        from intune_iac.workbench_screens import word_wrap
        quoted = "'/home/nsahm/work/journey 28 run 4/operation-22222222-1e1bf77b8586'"
        lines = word_wrap('Next: Record the deployment: in the workspace, deployment-record %s %s (a lists it)' % (quoted, 'f' * 64), 100)
        self.assertEqual(len([line for line in lines if quoted in line]), 1, lines)
        # An apostrophe in a sentence is not a quote.
        sentence = "this host's clock reads earlier than a time it recorded; the workspace's file cannot be read"
        self.assertEqual(' '.join(word_wrap(sentence, 40)), sentence)
        # A quoted argument wider than the line is still split (a token that cannot fit).
        for line in word_wrap("x '" + 'a b ' * 40 + "'", 30):
            self.assertLessEqual(len(line), 30)

    def test_the_modeled_service_line_keeps_its_flag_whole(self):
        # Item 17 (frame 04): "...; --" then "service-root chooses another)".
        workspace = self.workspace(0, {'objects': [{'object_id': POLICY}], 'modeled_service': {
            'source': 'adoption', 'root': '/home/nsahm/work/journey 28 run 4/handoff/service',
            'artifact_id': '6c0ef6390596' + 'a' * 52}})
        workspace.rows, workspace.highlight = [{'object_id': POLICY, 'name': 'Pilot'}], 0
        lines = list(workspace._summary_lines(116))
        self.assertTrue(any('--service-root' in line for line in lines), lines)
        self.assertFalse(any(line.rstrip().endswith('--') for line in lines), lines)

    def test_delivery_in_the_lifecycle_line_reads_as_a_key_not_a_surface(self):
        # Item 17 (run 3 G3): "v Delivery" had no tab number, as the other entries do.
        from intune_iac.workbench_screens import lifecycle_lines
        lines = text(lifecycle_lines(4, 160, {'status': 'prepared', 'expires_at': 4102444800}, now=0))
        self.assertIn('Lifecycle: 9 Repository > 5 Plan (here) > 6 Execution > Delivery (key v).', lines)
        self.assertNotIn('v Delivery', lines)

    def test_the_delivery_rows_read_codes_as_words(self):
        # Item 8: the codes stay in the typed details (e) and the raw record (r); the rows say them as words.
        from plugin_tests.test_workbench_screens import delivery_value
        from intune_iac.workbench_screens import delivery_lines
        lines = text(delivery_lines(delivery_value(), 200))
        for words in ('engine succeeded verified', 'desired state observed | second plan no change',
                      'verified local modeled deployment'):
            self.assertIn(words, lines)
        for code in ('engine succeeded_verified', 'desired_state_observed', 'second plan no_change',
                     'verified_local_modeled_deployment', 'synthetic_local_process_and_modeled_service_only'):
            self.assertNotIn(code, lines)
        self.assertIn('Evidence class synthetic local process and modeled service only', lines)

    def test_a_clock_held_delivery_note_says_the_age_is_not_known(self):
        # Item 18: "now reads stale (...)" for a clock hold.
        from intune_iac.workbench_delivery import _stale_note
        for code, cause in (('clock_moved_backward', "this host's clock reads earlier than a time this workspace recorded"),
                            ('clock_floor_invalid', 'the time this workspace recorded cannot be read')):
            note = _stale_note({'observation_freshness': 'stale', 'observation_freshness_reasons': [code]})
            self.assertIn('the age of the observation that shows it is not known (%s)' % cause, note)
            self.assertNotIn('stale', note)
            self.assertNotIn(code, note)
        note = _stale_note({'observation_freshness': 'stale', 'observation_freshness_reasons': ['older_than_window']})
        self.assertIn('now reads stale (older than the freshness window)', note)

    def test_the_unreadable_record_sentence_is_one_sentence_with_one_bracket(self):
        # Item 18: "(Diagnostics shows where it is kept) (this host's clock reads ...)".
        from intune_iac.workbench_diagnostics import with_clock_times
        from intune_iac.workbench_screens import KNOWN_NEXT
        step = with_clock_times(KNOWN_NEXT['observation_clock_floor_invalid'], {'reads': 1800000000.0, 'recorded': None})
        self.assertEqual(step.count('('), 1, step)
        self.assertEqual(step.count(')'), 1, step)
        self.assertIn("(Diagnostics shows where it is kept; this host's clock reads 2027-01-15 08:00:00 UTC; "
                      'the time this workspace recorded cannot be read)', step)
        moved = with_clock_times('Correct the clock.', {'reads': 1800000000.0, 'recorded': 1800000100.0})
        self.assertEqual(moved, "Correct the clock (this host's clock reads 2027-01-15 08:00:00 UTC; this workspace "
                                'recorded 2027-01-15 08:01:40 UTC).')
