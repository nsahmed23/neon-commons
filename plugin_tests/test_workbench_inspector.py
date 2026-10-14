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


if __name__ == '__main__':
    unittest.main()
