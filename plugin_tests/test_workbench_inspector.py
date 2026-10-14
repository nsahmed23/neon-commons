"""The Inspector: what policy this is, what the evidence says it does, what needs attention, and what can be done next.

The real store, modeled service and repository fixture produce each state; the
expected words are written by hand. Nothing here proposes, approves or executes.
"""
from collections import deque
import json
import unittest

from intune_iac.workbench_tui import cell_width
from plugin_tests import test_workbench_repository as repository_tests

OBJECT, TENANT, KEY = repository_tests.OBJECT, repository_tests.TENANT, repository_tests.KEY


class InspectorReadModelTests(unittest.TestCase):
    RESOURCE_ADDRESS = repository_tests.RepositoryOwnedChangeTests.RESOURCE_ADDRESS
    setUp = repository_tests.RepositoryOwnedChangeTests.setUp
    import_intent = repository_tests.RepositoryOwnedChangeTests.import_intent

    def inspection(self, service_available=True):
        from intune_iac.workbench import _inspection
        return _inspection(self.store, OBJECT, attention=True, service_available=service_available)

    def test_a_clear_policy_with_a_recorded_intent_offers_the_repository_route(self):
        self.import_intent()
        value = self.inspection()
        self.assertEqual(value['attention']['status'], 'clear')
        self.assertEqual(value['attention']['signals'], [])
        self.assertEqual([step['source'] for step in value['next_actions']], ['repository_intent'])
        self.assertTrue(value['next_actions'][0]['step'].startswith('propose-from-intent NEW_OPERATION_DIR'))

    def test_without_a_repository_intent_the_next_step_says_how_to_record_one(self):
        value = self.inspection(service_available=False)
        step = value['next_actions'][0]['step']
        self.assertIn('repository-entry REPOSITORY', step)
        self.assertIn('needs --service-root', step)

    def test_a_failed_collection_is_the_recorded_reason_and_its_step_comes_first(self):
        self.import_intent()
        self.store.collect(self.service, fault='deny')
        value = self.inspection()
        codes = [signal['code'] for signal in value['attention']['signals']]
        self.assertIn('collection_failed', codes)
        self.assertEqual(value['attention']['status'], 'attention')
        self.assertEqual(value['next_actions'][0]['source'], 'collection_failed')
        self.assertIn('Collect again', value['next_actions'][0]['step'])

    def test_the_inspection_without_attention_is_unchanged(self):
        from intune_iac.workbench import _inspection
        plain = _inspection(self.store, OBJECT)
        self.assertNotIn('attention', plain); self.assertNotIn('next_actions', plain)


def inspected(**changes):
    """An Inspector value with the read model's attention and next actions, written by hand."""
    body = {'name': 'Windows Privacy Pilot', 'description': 'Synthetic reference.', 'platforms': 'windows10', 'technologies': ['mdm'],
            'role_scope_tag_ids': ['0'],
            'settings': {'settings': [{'id': '0', 'settingInstance': {
                '@odata.type': '#microsoft.graph.deviceManagementConfigurationChoiceSettingInstance',
                'settingDefinitionId': 'device_vendor_msft_policy_config_privacy_letappsaccesslocation',
                'choiceSettingValue': {'value': 'device_vendor_msft_policy_config_privacy_letappsaccesslocation_2', 'children': []}}}]},
            'assignments': [{'type': 'groupAssignmentTarget', 'group_id': '44444444-4444-4444-8444-444444444444',
                             'filter_type': 'include', 'filter_id': '77777777-7777-4777-8777-777777777777'},
                            {'type': 'exclusionGroupAssignmentTarget', 'group_id': '66666666-6666-4666-8666-666666666666',
                             'filter_type': 'none'}]}
    value = {'object_id': OBJECT, 'tenant_id': TENANT, 'name': 'Windows Privacy Pilot', 'body': body, 'run_id': 4,
             'observed_at': '2026-10-14T12:25:00Z', 'coverage': 'complete', 'freshness': 'stale', 'evidence_class': 'synthetic',
             'snapshot_id': '599f74fd' + 'f' * 56, 'ownership': 'unknown', 'selected_repository': None,
             'attention': {'status': 'attention', 'checked': {'collection': 'clear', 'freshness': 'attention'},
                           'signals': [{'area': 'freshness', 'code': 'observation_stale',
                                        'observed': 'The newest observation (2026-10-14T12:25:00Z) is stale.',
                                        'next_step': 'Collect again before preparing or judging a change.'}]},
             'next_actions': [{'source': 'observation_stale', 'step': 'Collect again before preparing or judging a change.'}]}
    value.update(changes)
    return value


class InspectorSummaryTests(unittest.TestCase):
    def lines(self, value, width=100):
        from intune_iac.workbench_screens import inspector_lines
        return inspector_lines(value, width)

    def test_the_summary_answers_what_it_is_what_it_does_what_needs_attention_and_what_next(self):
        lines = self.lines(inspected())
        joined = '\n'.join(lines)
        self.assertEqual(lines[0], 'POLICY  Windows Privacy Pilot')
        self.assertIn(OBJECT, joined)
        self.assertIn('WHAT THE EVIDENCE SAYS IT DOES', joined)
        self.assertIn('synthetic observation, run 4, 2026-10-14T12:25:00Z, coverage complete, stale', joined)
        self.assertIn('device_vendor_msft_policy_config_privacy_letappsaccesslocation', joined)
        self.assertIn('meaning not established', joined)
        self.assertIn('include  44444444-4444-4444-8444-444444444444', joined)
        self.assertIn('filter include 77777777-7777-4777-8777-777777777777', joined)
        self.assertIn('exclude  66666666-6666-4666-8666-666666666666', joined)
        self.assertIn('group names were not captured', joined)
        self.assertIn('NEEDS ATTENTION', joined)
        self.assertIn('The newest observation (2026-10-14T12:25:00Z) is stale.', joined)
        self.assertIn('NEXT', joined)
        self.assertIn('Collect again before preparing or judging a change.', joined)

    def test_nothing_is_invented(self):
        joined = '\n'.join(self.lines(inspected())).lower()
        for word in ('all users', 'allowed', 'force deny', 'refresh now', 'verified'):
            self.assertNotIn(word, joined)

    def test_nothing_recorded_is_said_plainly_with_what_was_checked(self):
        value = inspected(freshness='fresh', attention={'status': 'clear', 'signals': [],
                          'checked': {'collection': 'clear', 'freshness': 'clear', 'repository': 'not_recorded'}},
                          next_actions=[{'source': 'no_repository_intent', 'step': 'repository-entry REPOSITORY shows how.'}])
        joined = '\n'.join(self.lines(value))
        self.assertIn('Nothing recorded needs attention', joined)
        self.assertIn('repository-entry REPOSITORY shows how.', joined)

    def test_areas_that_were_not_examined_are_named_not_counted_as_checked(self):
        value = inspected(freshness='fresh', next_actions=[], attention={'status': 'clear', 'signals': [], 'checked': {
            'collection': 'clear', 'freshness': 'clear', 'operations': 'clear', 'repository': 'not_recorded',
            'device_evidence': 'not_imported'}})
        joined = '\n'.join(self.lines(value, 200))
        self.assertIn('Nothing recorded needs attention (checked: collection, freshness, operations).', joined)
        self.assertIn('Not fully checked: repository (no intent recorded); device evidence (not imported).', joined)

    def test_an_unreadable_attention_is_not_shown_as_clear(self):
        value = inspected(attention={'status': 'unavailable', 'error_code': 'workbench_query_limit', 'signals': [], 'checked': {}},
                          next_actions=[])
        joined = '\n'.join(self.lines(value))
        self.assertIn('could not be read (workbench_query_limit)', joined)
        self.assertNotIn('Nothing recorded needs attention', joined)

    def test_every_line_fits_narrow_and_wide(self):
        for width in (58, 100):
            for line in self.lines(inspected(), width):
                self.assertLessEqual(cell_width(line), width, line)


class EvidenceLayerTests(unittest.TestCase):
    def workspace(self, value=None, tab=1):
        from intune_iac.workbench_tui import Workspace
        workspace = Workspace.__new__(Workspace)
        workspace.__dict__.update(
            tab=tab, value=value or inspected(), selected=OBJECT, facts={}, highlight=0, scroll=0, mode=None, buffer='',
            cursor=0, pasting=False, input_overflow=False, notice='', last_command='select ' + OBJECT, view_command='inspect',
            page_command='overview', rows=[], operation_rows=[], operation_highlight=0, active_operation=None,
            execution_result=None, active_service=None, active_adoption=None, active_adoption_plan=None, pending=deque(),
            size=(100, 40), submission_key='enter', entry_focus=0, overview_focus=0, layer='summary', trail=[],
            _detail_cache=None)
        workspace.draw = lambda: None
        workspace._terminal_size = lambda: (100, 40)
        return workspace

    def keys(self, workspace, keys):
        # Records the layer before each key is read: a later command resets it to the summary.
        class Reader:
            def __init__(self, keys): self.keys, self.layers = list(keys), []
            def read(self): self.layers.append(workspace.layer); return self.keys.pop(0)
        workspace.key_reader = Reader(keys)
        return workspace.input('')

    def test_the_default_body_is_the_summary_with_one_line_of_access_to_the_evidence(self):
        workspace = self.workspace()
        lines = workspace._data_lines(100)
        raw_lines = len(json.dumps(workspace.value, ensure_ascii=False, indent=2).splitlines())
        self.assertFalse(any(line.startswith('{') or line.startswith('  "') for line in lines))
        self.assertEqual(lines[-1], 'Evidence: e typed details | r complete raw record (%d lines)' % raw_lines)
        self.assertEqual(sum('Evidence:' in line for line in lines), 1)

    def test_typed_details_then_raw_then_back_to_the_summary(self):
        workspace = self.workspace()
        workspace.layer = 'details'
        details = workspace._data_lines(100)
        probe = self.workspace()
        self.assertEqual(self.keys(probe, [('char', 'e'), ('char', 'e'), ('char', 'q')]), 'quit')
        self.assertEqual(probe.key_reader.layers, ['summary', 'details', 'summary'])
        self.assertTrue(details[0].startswith('TYPED DETAILS'))
        self.assertTrue(any(line.startswith('name') and 'Windows Privacy Pilot' in line for line in details))
        workspace = self.workspace()
        workspace.layer = 'raw'
        raw = workspace._data_lines(100)
        self.assertTrue(raw[0].startswith('RAW RECORD'))
        self.assertIn('{', raw)
        fresh = self.workspace()
        self.keys(fresh, [('char', 'r'), 'escape', ('char', 'q')])
        self.assertEqual(fresh.key_reader.layers, ['summary', 'raw', 'summary'])

    def test_the_title_names_the_evidence_layer(self):
        from intune_iac.workbench_tui import title_line
        self.assertEqual(title_line('Inspector', 'inspect', {}, 'details'), 'INTUNE WORKBENCH  /  Inspector  /  typed details')
        self.assertEqual(title_line('Inspector', 'inspect', {}, 'raw'), 'INTUNE WORKBENCH  /  Inspector  /  raw record')

    def test_back_returns_to_the_previous_view_and_never_runs_a_change(self):
        workspace = self.workspace()
        workspace.trail = [(0, 'overview'), (1, 'inspect')]
        self.assertEqual(self.keys(workspace, [('char', 'b')]), 'inspect')
        self.assertEqual(workspace.trail, [(0, 'overview')])
        empty = self.workspace()
        self.assertEqual(self.keys(empty, [('char', 'b'), ('char', 'q')]), 'quit')
        from intune_iac.workbench_tui import VIEW_COMMANDS
        for word in ('propose', 'execute', 'approve', 'reconcile', 'collect', 'repository-import', 'repository-refresh'):
            self.assertNotIn(word, VIEW_COMMANDS)

    def test_the_key_line_says_what_q_does(self):
        from intune_iac.workbench_tui import HELP_LINES
        for line in HELP_LINES:
            self.assertIn('q exit', line)
            self.assertNotIn('detach', line)

    def test_a_command_that_is_not_a_view_is_never_called_read_only(self):
        workspace = self.workspace()
        workspace.last_command = 'propose desired.json operation'
        notice = workspace._notice_for({'status': 'prepared', 'operation_id': 'x'})
        self.assertIn('propose ran; the engine reported status prepared', notice)
        self.assertNotIn('nothing was proposed', notice)
        workspace.last_command = 'execute operation digest'
        self.assertIn('execute ran; the engine reported status outcome_unknown', workspace._notice_for({'status': 'outcome_unknown'}))
        workspace.last_command = 'health'
        self.assertIn('Health shown read-only; nothing was proposed, approved or executed', workspace._notice_for({'stages': []}))

    def test_a_refusal_without_an_explanation_says_only_what_is_on_the_screen(self):
        workspace = self.workspace()
        workspace.receive({'status': 'error', 'error': {'code': 'something_new', 'message': 'Engine words.'}})
        self.assertEqual(workspace.notice, "REFUSED something_new: the engine's message is on the screen.")
        workspace.receive({'status': 'error', 'error': {'code': 'workbench_repository_stale', 'message': 'Stale.'}})
        self.assertEqual(workspace.notice, 'REFUSED workbench_repository_stale: what it means and the next step are on the screen.')

    def test_back_from_a_result_that_is_not_a_view_returns_to_the_view_before_it(self):
        workspace = self.workspace()
        workspace.trail = [(0, 'overview')]
        workspace.current_view = (1, 'inspect')
        workspace._send('propose desired.json operation')
        self.assertEqual(workspace.trail, [(0, 'overview'), (1, 'inspect')])
        self.assertIsNone(workspace.current_view)
        self.assertEqual(self.keys(workspace, [('char', 'b')]), 'inspect')
        self.assertEqual(workspace.trail, [(0, 'overview')])

    def test_an_empty_estate_names_no_mode_and_a_mixed_one_says_so(self):
        workspace = self.workspace()
        workspace.mode_class = None
        workspace._learn({'objects': [], 'pending_observations': [], 'evidence_class': 'synthetic'})
        self.assertIsNone(workspace.mode_class)
        workspace._learn({'objects': [{'object_id': OBJECT}], 'pending_observations': [], 'evidence_class': 'mixed_observations'})
        self.assertEqual(workspace.mode_class, 'mixed_observations')

    def test_the_strip_uses_the_repository_view_words_for_a_recorded_signal(self):
        workspace = self.workspace()
        workspace._learn(inspected(attention={'status': 'attention', 'checked': {'repository': 'attention'}, 'signals': [
            {'area': 'repository', 'code': 'repository_stale', 'observed': 'Changed.', 'next_step': 'Refresh.'}]}))
        self.assertEqual(workspace.facts['repository'], 'stale')
        workspace._learn(inspected(attention={'status': 'clear', 'checked': {'repository': 'clear'}, 'signals': []}))
        self.assertEqual(workspace.facts['repository'], 'current')

    def test_no_summary_says_evidence_follows_below_it(self):
        from intune_iac.workbench_screens import change_lines
        plan = {'operation_id': 'a' * 32, 'status': 'prepared', 'tenant_id': TENANT, 'object_id': OBJECT,
                'field_changes': {'status': 'changed', 'complete': False, 'changes': [
                    {'path': '/description', 'kind': 'replaced', 'before': 'x', 'after': 'y'}]}}
        lines = self.workspace(plan, tab=4)._summary_lines(100) + change_lines(plan['field_changes'], 100)
        joined = '\n'.join(lines).lower()
        self.assertNotIn('follow', joined)
        self.assertIn('e typed details', joined)

    def test_a_capture_whose_bytes_no_longer_verify_still_shows_its_integrity(self):
        value = {'object_id': OBJECT, 'name': 'Windows Privacy Pilot', 'relationships': [],
                 'raw_capture_observation': {'status': 'mapped'}, 'raw_mapping_status': 'mapped',
                 'raw_evidence_integrity': {'status': 'unverified_or_changed'}, 'raw_observed_assignments': None}
        joined = '\n'.join(self.workspace(value, tab=2)._summary_lines(100))
        self.assertIn('[LITERAL CAPTURE]', joined)
        self.assertIn('unverified_or_changed', joined)
        self.assertIn('not read: the bytes did not verify', joined)
        synthetic = self.workspace(dict(value, raw_capture_observation=None, raw_evidence_integrity={}), tab=2)
        self.assertNotIn('[LITERAL CAPTURE]', '\n'.join(synthetic._summary_lines(100)))


class NextStepTests(unittest.TestCase):
    def next(self, attention, repository=True, service=True):
        from intune_iac.workbench import _next_actions
        return _next_actions({'selected_repository': {'artifact_id': 'a'} if repository else None}, attention, service)

    def test_unread_diagnostics_offer_no_change(self):
        for status in ('unavailable', 'partly_checked'):
            steps = self.next({'status': status, 'signals': []})
            self.assertEqual(steps[0]['source'], 'diagnostics_' + status)
            self.assertIn('not established', steps[0]['step'])
            self.assertNotIn('repository_intent', [step['source'] for step in steps])

    def test_the_change_route_says_what_it_prepares_and_that_nothing_is_approved(self):
        for repository in (True, False):
            step = self.next({'status': 'clear', 'signals': []}, repository=repository)[0]['step']
            self.assertIn('review digest', step)
            self.assertIn('nothing is approved', step)
            self.assertNotIn('reviewed proposal', step)

    def test_steps_past_the_limit_are_counted_not_dropped(self):
        signals = [{'code': 'c%d' % number, 'next_step': 'step %d' % number} for number in range(5)]
        steps = self.next({'status': 'attention', 'signals': signals})
        self.assertEqual([step['step'] for step in steps], ['step 0', 'step 1', 'step 2', '2 more steps under i (diagnostics).'])


class ModeWordTests(unittest.TestCase):
    def test_each_evidence_class_has_its_own_word_and_unknown_stays_unknown(self):
        from intune_iac.workbench_screens import mode_word
        expected = {'synthetic': 'SYNTHETIC', 'graph_capture_unverified': 'CAPTURE', 'graph_reader_laboratory': 'LABORATORY',
                    'graph_reader_attempt': 'READ FAILED', 'graph_authenticated_observation': 'LIVE READ-ONLY',
                    'mixed_observations': 'MIXED', 'graph_reader_future': 'MODE UNKNOWN', 'unknown': 'MODE UNKNOWN',
                    None: 'MODE UNKNOWN'}
        for evidence_class, word in expected.items():
            self.assertEqual(mode_word(evidence_class), word, evidence_class)

    def test_laboratory_evidence_is_never_called_live(self):
        from intune_iac.workbench_screens import evidence_words, mode_word
        self.assertNotIn('live', evidence_words('graph_reader_laboratory'))
        self.assertNotIn('LIVE', mode_word('graph_reader_laboratory'))
        self.assertNotIn('LIVE', mode_word('graph_reader_attempt'))


class DetailsTests(unittest.TestCase):
    def test_typed_details_keep_every_character_of_a_long_name(self):
        from intune_iac.workbench_screens import details_lines
        lines = details_lines({'service_authentication_reestablished': False, 'id': 'x'}, 60)
        self.assertIn('service authentication reestablished', lines)
        self.assertIn('    no', lines)
        for line in lines:
            self.assertLessEqual(cell_width(line), 60, line)


if __name__ == '__main__':
    unittest.main()
