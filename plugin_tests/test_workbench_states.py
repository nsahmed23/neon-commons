"""Distinct states (P-PRES-11) and readable times (P-PRES-06).

The Inspector's read model reports the observation, the repository intent and the policy's newest operation as three
separate states, each from its own records: the observation's freshness by age apart from the proposal's own check
against the service; the intent's own revision and whether the repository still matches it; the operation's journal
status and readback. The summary states times to the second with their zone; the exact values stay in the typed
details and the raw record. The real store, modeled service and maintenance engine produce each state.
"""
import unittest

from plugin_tests import test_workbench_repository as repository_tests

OBJECT, TENANT = repository_tests.OBJECT, repository_tests.TENANT


class StateReadModelTests(unittest.TestCase):
    RESOURCE_ADDRESS = repository_tests.RepositoryOwnedChangeTests.RESOURCE_ADDRESS
    setUp = repository_tests.RepositoryOwnedChangeTests.setUp
    import_intent = repository_tests.RepositoryOwnedChangeTests.import_intent
    edit_description = repository_tests.RepositoryOwnedChangeTests.edit_description

    def states(self):
        from intune_iac.workbench import _inspection
        return _inspection(self.store, OBJECT, attention=True, service_available=True,
                           service_root=self.service.root)['states']

    def test_a_clear_policy_has_a_fresh_observation_a_current_intent_and_no_operation(self):
        self.import_intent()
        states = self.states()
        self.assertEqual(states['observation']['freshness'], 'fresh')
        self.assertIsNone(states['observation']['eligibility'])
        self.assertEqual(states['intent']['status'], 'current')
        self.assertIsNone(states['operation'])

    def test_no_intent_is_its_own_state(self):
        self.assertEqual(self.states()['intent'], {'status': 'none'})

    def test_a_changed_repository_is_the_intents_state_with_the_changed_file(self):
        self.import_intent()
        self.edit_description('Edited in the repository.')
        intent = self.states()['intent']
        self.assertEqual(intent['status'], 'changed')
        self.assertIn(repository_tests.STACK, intent['reason'])

    def test_the_operation_state_follows_its_journal(self):
        from intune_iac import maintenance
        from intune_iac.workbench_repository import propose_from_intent, refresh_intent
        self.import_intent()
        self.edit_description('Edited in the repository.')
        refresh_intent(self.store, OBJECT, 'b' * 40)
        operation = self.root / 'operation'
        review = propose_from_intent(self.store.root, self.service.root, OBJECT, operation)
        self.assertEqual(self.states()['operation']['journal_status'], 'prepared')
        maintenance.execute(operation, approve_digest=review['approval_digest'], fault='lost-response')
        state = self.states()['operation']
        self.assertEqual((state['operation_id'], state['journal_status']), (review['operation_id'], 'outcome_unknown'))
        maintenance.reconcile(operation)
        states = self.states()
        self.assertEqual((states['operation']['journal_status'], states['operation']['classification']),
                         ('reconciled', 'desired_state_observed'))
        # The execution changed the service: fresh by age, but the proposal's own check fails, a separate fact.
        self.assertEqual(states['observation']['freshness'], 'fresh')
        self.assertEqual(states['observation']['eligibility']['reason'], 'service_changed')


class StateRenderingTests(unittest.TestCase):
    STATES = {
        'observation': {'evidence_class': 'synthetic', 'run_id': 4, 'observed_at': '2026-10-14T19:55:52.390326Z',
                        'coverage': 'complete', 'freshness': 'fresh', 'freshness_reasons': [],
                        'eligibility': {'code': 'maintenance_observation_stale', 'reason': 'service_changed',
                                        'observed_revision': 1, 'service_revision': 2}},
        'intent': {'status': 'changed', 'artifact_id': 'e927410221924400' + '0' * 48,
                   'scope': {'stack': 'orgs/reference/dev', 'component': 'intune-reference'},
                   'source_revision': '21efad0ec0930fe5c8f5c456db39947f73dfd6ac', 'revision_content_verified': True,
                   'recorded_at': '2026-10-14T19:50:01.000001Z',
                   'reason': 'The repository changed since its recorded intent: changed stacks/orgs/reference/dev.yaml.'},
        'operation': {'operation_id': '4d972e93' + 'a' * 24, 'status': 'reconciled', 'journal_status': 'reconciled',
                      'classification': 'desired_state_observed', 'recorded_at': '2026-10-14T19:57:00.5Z'}}

    def lines(self, states=None):
        from intune_iac.workbench_screens import inspector_lines
        value = {'object_id': OBJECT, 'name': 'Windows Privacy Pilot', 'evidence_class': 'synthetic', 'run_id': 4,
                 'observed_at': '2026-10-14T19:55:52.390326Z', 'coverage': 'complete', 'freshness': 'fresh',
                 'states': self.STATES if states is None else states, 'body': {}}
        # Wrapped lines joined back, so a phrase is found wherever the width broke it.
        return ' '.join(' '.join(inspector_lines(value, 160)).split())

    def test_three_states_each_on_its_own_line(self):
        text = self.lines()
        self.assertIn('STATE', text)
        self.assertIn('Observation', text)
        self.assertIn('fresh by age; the modeled service changed since (revision 1, now 2)', text)
        self.assertIn('Intent', text)
        self.assertIn('e9274102 from orgs/reference/dev / intune-reference at 21efad0e (content verified)', text)
        self.assertIn('(content verified); the repository changed since its recorded intent: changed '
                      'stacks/orgs/reference/dev.yaml', text)
        self.assertIn('Operation', text)
        self.assertIn('4d972e93 reconciled; readback desired state observed', text)

    def test_the_summary_states_times_to_the_second_with_their_zone(self):
        text = self.lines()
        self.assertIn('2026-10-14 19:55:52 UTC', text)
        self.assertNotIn('19:55:52.390326', text)  # the exact value stays in the typed details and the raw record

    def test_management_is_not_repeated_beside_the_intent_state(self):
        text = self.lines()
        self.assertIn('Managed ownership unknown', text)
        self.assertNotIn('repository intent recorded', text)

    def test_no_intent_and_no_operation_are_said_plainly(self):
        states = dict(self.STATES, intent={'status': 'none'}, operation=None)
        text = self.lines(states)
        self.assertIn('none recorded; repository-entry REPOSITORY finds where this policy is maintained', text)
        self.assertIn('none recorded for this policy', text)

    def test_readable_time(self):
        from intune_iac.workbench_screens import readable_time
        self.assertEqual(readable_time('2026-10-14T19:55:52.390326Z'), '2026-10-14 19:55:52 UTC')
        self.assertEqual(readable_time('2026-10-14T19:55:52+00:00'), '2026-10-14 19:55:52 UTC')
        self.assertEqual(readable_time('not a time'), 'not a time')
        self.assertIsNone(readable_time(None))


class StateSurfaceTests(unittest.TestCase):
    """The Repository and Plan surfaces show the same states, from the last read of the policy, labelled as such."""
    def workspace(self, tab, value):
        from collections import deque
        from intune_iac.workbench_tui import Workspace
        workspace = Workspace.__new__(Workspace)
        workspace.__dict__.update(
            tab=tab, value=value, selected=OBJECT, facts={'object_id': OBJECT, 'states': StateRenderingTests.STATES},
            scroll=0, mode=None, buffer='', cursor=0, notice='', last_command='', layer='summary', trail=[],
            store=type('S', (), {'tenant_id': TENANT})(), staged=None, quiet=None, pending=deque(), rows=[],
            operation_rows=[], active_operation=None, execution_result=None, active_service=None, active_adoption=None,
            active_adoption_plan=None, size=(120, 40), _detail_cache=None)
        return workspace

    def summary(self, workspace):
        return ' '.join(' '.join(workspace._surface_summary(118)).split())

    def test_the_repository_surface_shows_the_states(self):
        value = {'schema_version': 'workbench-repository-status/1', 'object_id': OBJECT,
                 'freshness': {'status': 'stale', 'sources': {'added': [], 'removed': [], 'changed': ['a.yaml']}}}
        text = self.summary(self.workspace(8, value))
        self.assertIn('STATE (from the last read of this policy)', text)
        self.assertIn('Observation', text)
        self.assertIn('Operation 4d972e93 reconciled', text)

    def test_the_plan_surface_shows_the_states(self):
        value = {'operation_id': '4d972e93' + 'a' * 24, 'object_id': OBJECT, 'status': 'prepared',
                 'tenant_id': TENANT, 'approval_digest': 'd' * 64, 'expires_at': 1792005916}
        text = self.summary(self.workspace(4, value))
        self.assertIn('STATE (from the last read of this policy)', text)
        self.assertIn('Intent e9274102', text)

    def test_other_surfaces_do_not_repeat_them(self):
        text = self.summary(self.workspace(3, {'object_id': OBJECT, 'history': []}))
        self.assertNotIn('STATE (from the last read', text)

    def test_status_words_read_as_words(self):
        from intune_iac.workbench_screens import state_lines
        states = dict(StateRenderingTests.STATES, operation={'operation_id': '5f18aadb' + 'b' * 24, 'status': 'outcome_unknown',
                                                             'journal_status': 'outcome_unknown', 'classification': None})
        text = ' '.join(' '.join(state_lines(states, 160)).split())
        self.assertIn('5f18aadb outcome unknown', text)


class ReadableTimeTests(unittest.TestCase):
    """Sentences give times to the second with their zone; the exact values stay in the signal's evidence."""
    STAMP = '2026-10-14T00:00:00.123456Z'

    def test_a_failed_collection_says_when_readably_and_keeps_the_exact_time(self):
        from intune_iac.workbench_diagnostics import _collection
        signals, _ = _collection({'last_attempt': {'run_id': 3, 'status': 'denied', 'error_code': 'denied',
                                                   'started_at': self.STAMP, 'completed_at': self.STAMP},
                                  'last_success': {'run_id': 2}})
        self.assertIn('(run 3, 2026-10-14 00:00:00 UTC)', signals[0]['observed'])
        self.assertNotIn('T00:00:00', signals[0]['observed'])
        self.assertEqual(signals[0]['evidence']['completed_at'], self.STAMP)

    def test_an_unfinished_collection_says_when_it_started(self):
        from intune_iac.workbench_diagnostics import _collection
        signals, _ = _collection({'last_attempt': {'run_id': 5, 'status': 'collecting', 'started_at': self.STAMP}})
        self.assertIn('started at 2026-10-14 00:00:00 UTC', signals[0]['observed'])
        self.assertEqual(signals[0]['evidence']['started_at'], self.STAMP)

    def test_a_stale_observation_says_when_readably(self):
        from intune_iac.workbench_diagnostics import _freshness
        signals, _ = _freshness({'freshness': 'stale', 'observed_at': self.STAMP, 'freshness_reasons': ['stamped_after_now'],
                                 'freshness_checked_at': '2026-10-13T23:55:00Z'}, failed=False)
        self.assertIn('The newest observation (2026-10-14 00:00:00 UTC)', signals[0]['observed'])
        self.assertIn('(2026-10-13 23:55:00 UTC)', signals[0]['observed'])
        self.assertEqual(signals[0]['evidence']['freshness_checked_at'], '2026-10-13T23:55:00Z')

    def test_the_relationship_header_and_plan_expiry_read_readably(self):
        from intune_iac.workbench_screens import relationship_lines
        lines = ' '.join(relationship_lines({'object_id': OBJECT, 'name': 'Pilot', 'observed_at': self.STAMP,
                                              'coverage': 'complete', 'relationships': []}, 120))
        self.assertIn('observed 2026-10-14 00:00:00 UTC', lines)

    def test_readable_time_lives_in_the_engine_layer(self):
        from intune_iac.io import readable_time
        self.assertEqual(readable_time(self.STAMP), '2026-10-14 00:00:00 UTC')


class RefusalCauseTests(unittest.TestCase):
    """P-PRES-05: verdict once, the known cause, the next step, the exact code; P-PRES-08: no fragments."""
    CHANGED = {'area': 'repository', 'code': 'repository_stale', 'evidence': {},
               'observed': 'The repository changed since its recorded intent: changed stacks/orgs/reference/dev.yaml.'}

    def workspace(self, facts=None, last_command=''):
        from collections import deque
        from intune_iac.workbench_tui import Workspace
        workspace = Workspace.__new__(Workspace)
        workspace.__dict__.update(
            tab=1, value={}, selected=OBJECT, facts=dict({'object_id': OBJECT}, **(facts or {})), scroll=0, mode=None,
            buffer='', cursor=0, notice='', last_command=last_command, layer='summary', trail=[], view_command='inspect',
            store=type('S', (), {'tenant_id': TENANT})(), staged=None, quiet=None, pending=deque(), rows=[], highlight=0,
            operation_rows=[], operation_highlight=0, active_operation=None, execution_result=None, active_service=None,
            active_adoption=None, active_adoption_plan=None, size=(120, 40), _detail_cache=None, entry_focus=0,
            page_command='overview', pending_stage=None)
        workspace.draw = lambda: None
        workspace.save_context = lambda: None
        return workspace

    def test_a_known_cause_replaces_the_either_or_meaning(self):
        from intune_iac.workbench_screens import refusal_lines
        value = {'status': 'error', 'error': {'code': 'workbench_repository_stale', 'message': 'Refused.'}}
        text = ' '.join(' '.join(refusal_lines(value, 120, known=(self.CHANGED['observed'], 'repository_changed'))).split())
        self.assertIn('Cause: The repository changed since its recorded intent: changed stacks/orgs/reference/dev.yaml.', text)
        self.assertNotIn('or its component no longer consumes', text)
        self.assertIn('[REFUSED] workbench_repository_stale', text)  # the exact code stays
        # The step for this cause, not for every cause the code covers; the engine's general message is one key away.
        self.assertIn('Next: Press 9 to review the difference', text)
        self.assertNotIn('Refused.', text)
        self.assertIn("The engine's own message is in the typed details (e).", text)

    def test_the_workspace_supplies_the_cause_it_read(self):
        workspace = self.workspace({'signals': [self.CHANGED]}, 'propose-from-intent /w/op')
        workspace.receive({'status': 'error', 'error': {'code': 'workbench_repository_stale', 'message': 'Refused.'}})
        text = ' '.join(' '.join(workspace._surface_summary(118)).split())
        self.assertIn('Cause: The repository changed since its recorded intent', text)

    def test_an_observation_refusal_names_the_failed_check(self):
        eligibility = {'code': 'maintenance_observation_stale', 'reason': 'service_changed', 'observed_revision': 1,
                       'service_revision': 2}
        workspace = self.workspace({'eligibility': eligibility}, 'propose-from-intent /w/op')
        workspace.receive({'status': 'error', 'error': {'code': 'maintenance_observation_stale', 'message': 'Refused.'}})
        text = ' '.join(' '.join(workspace._surface_summary(118)).split())
        self.assertIn('Cause: The modeled service changed after this observation was collected (revision 1, now 2)', text)

    def test_the_verdict_is_said_once(self):
        workspace = self.workspace({}, 'propose /w/d.json /w/op')
        workspace.receive({'status': 'error', 'error': {'code': 'workbench_repository_stale', 'message': 'Refused.'}})
        self.assertNotIn('REFUSED', workspace.notice)

    def test_notices_say_what_a_command_recorded(self):
        workspace = self.workspace({}, 'reconcile /w/op')
        notice = workspace._notice_for({'operation_id': 'a' * 32, 'journal_status': 'reconciled',
                                        'classification': 'desired_state_observed'})
        self.assertEqual(notice, 'Ready. reconcile ran; the journal is now reconciled (readback desired state observed).')
        workspace = self.workspace({}, 'repository-refresh ' + 'b' * 40)
        notice = workspace._notice_for({'artifact_id': 'c' * 64, 'kind': 'repository_intent', 'data': {}, 'created': True})
        self.assertEqual(notice, 'Ready. repository-refresh recorded repository intent cccccccc.')
        self.assertNotIn('reported no status', workspace._notice_for({'other': 1}))


class LifecycleTests(unittest.TestCase):
    """P-PRES-15: on each surface of a change, the path with its existing numbers, where you are, and the next step."""
    surface = RefusalCauseTests.workspace

    def summary(self, tab, value):
        workspace = self.surface()
        workspace.tab, workspace.value = tab, value
        return ' '.join(' '.join(workspace._summary_lines(118)).split())

    def test_the_plan_review_says_where_it_sits_and_what_comes_next(self):
        import time
        text = self.summary(4, {'operation_id': 'a' * 32, 'object_id': OBJECT, 'status': 'prepared',
                                'expires_at': time.time() + 200})
        self.assertIn('Lifecycle: 9 Repository > 5 Plan (here) > 6 Execution > v Delivery', text)
        self.assertIn('Next: execute OPERATION_DIR DIGEST', text)

    def test_the_repository_and_execution_surfaces_say_it_too(self):
        text = self.summary(8, {'schema_version': 'workbench-repository-status/1', 'object_id': OBJECT,
                                'freshness': {'status': 'current'}})
        self.assertIn('9 Repository (here)', text)
        text = self.summary(5, {'operation_id': 'a' * 32, 'status': 'outcome_unknown'})
        self.assertIn('6 Execution (here)', text)

    def test_the_next_step_follows_the_state_shown(self):
        # A step the state refuses is never offered as next (journey 25: a changed repository offered a proposal).
        import time
        text = self.summary(8, {'schema_version': 'workbench-repository-status/1', 'object_id': OBJECT,
                                'freshness': {'status': 'stale'}})
        self.assertIn('Next: record the current source first', text)
        self.assertNotIn('a prepares a proposal from the recorded intent', text)
        prepared = {'operation_id': 'a' * 32, 'object_id': OBJECT, 'status': 'prepared', 'expires_at': time.time() + 200}
        text = self.summary(4, dict(prepared, expires_at=time.time() - 1))
        self.assertIn("approval window has closed; a prepares a new proposal", text)
        self.assertNotIn('execute OPERATION_DIR', text)
        text = self.summary(4, dict(prepared, repository={'cited': None, 'context_changed': True}))
        self.assertIn('context file changed, so execute refuses it', text)
        text = self.summary(4, dict(prepared, repository={'cited': True, 'freshness': 'stale'}))
        self.assertIn('repository changed since its intent, so execute refuses it', text)
        text = self.summary(5, {'operation_id': 'a' * 32, 'status': 'outcome_unknown'})
        self.assertIn('Next: a reconciles it (never replays)', text)
        text = self.summary(5, {'operation_id': 'a' * 32, 'status': 'succeeded_verified'})
        self.assertIn('Next: v shows every delivery stage, including the deployment record', text)
        self.assertNotIn('unknown outcome', text)

    def test_delivery_carries_its_own_stages_and_next_step(self):
        # Delivery is the lifecycle in full; a second line pointing at it from itself would only repeat.
        text = self.summary(5, {'schema_version': 'workbench-delivery/1', 'operation_id': 'a' * 32, 'stages': [],
                                'next_action': 'Nothing pending.'})
        self.assertNotIn('Lifecycle:', text)

    def test_other_surfaces_and_refusals_do_not(self):
        self.assertNotIn('Lifecycle:', self.summary(1, {'object_id': OBJECT, 'name': 'Pilot', 'body': {}}))
        self.assertNotIn('Lifecycle:', self.summary(4, {'status': 'error', 'error': {'code': 'x', 'message': 'y'}}))

    def test_the_operations_list_gives_readable_times(self):
        workspace = self.surface()
        workspace.tab = 4
        workspace.operation_rows = [{'operation_id': 'a' * 32, 'operation_root': '/w/op', 'status': 'prepared',
                                     'recorded_at': '2026-10-14T19:57:00.5Z'}]
        workspace.operation_highlight = 0
        workspace.value = {'operations': workspace.operation_rows}
        text = ' '.join(workspace._summary_lines(118))
        self.assertIn('recorded=2026-10-14 19:57:00 UTC', text)


class ChangedContextTests(unittest.TestCase):
    """A plan whose bound context file changed: the Plan review says so instead of a citation."""
    surface = RefusalCauseTests.workspace

    def test_the_plan_review_says_the_context_changed(self):
        workspace = self.surface()
        workspace.tab = 4
        workspace.value = {'operation_id': 'a' * 32, 'object_id': OBJECT, 'status': 'prepared', 'changes': [],
                           'field_changes': {'status': 'no_change', 'changes': []},
                           'repository': {'cited': None, 'context_changed': True, 'context_path': '/w/op.intent-context.json'}}
        text = ' '.join(' '.join(workspace._summary_lines(118)).split())
        self.assertIn('Context file: changed since this proposal was prepared', text)
        self.assertIn('execute refuses it (maintenance_source_changed)', text)
        self.assertNotIn('Cited repository intent', text)


class TypedDetailTests(unittest.TestCase):
    """P-PRES-01: label and value apart by two spaces or separate lines; empty, null and missing kept apart."""
    def lines(self, value, width=60):
        from intune_iac.workbench_screens import details_lines
        return details_lines(value, width)

    def test_empty_null_and_empty_containers_read_differently(self):
        lines = self.lines({'text': '', 'missing': None, 'items': [], 'map': {}})
        joined = '\n'.join(lines)
        self.assertIn('"" (empty text)', joined)
        self.assertIn('not recorded', joined)
        self.assertIn('[] (empty list)', joined)
        self.assertIn('{} (empty map)', joined)

    def test_labels_and_values_never_touch(self):
        from intune_iac.workbench_tui import cell_width
        value = {'short': 'a', '名前': '東京', 'a_very_long_key_name_that_goes_beyond_the_label_column': 'v'}
        lines = self.lines(value, 50)
        self.assertIn('名前', '\n'.join(lines))
        unicode_line = next(line for line in lines if line.startswith('名前'))
        self.assertIn('  ', unicode_line)  # at least two spaces between label and value
        long_label = [line for line in lines if 'a very long key' in line]
        self.assertTrue(long_label and 'v' not in long_label[0].split()[-1:])  # the value sits on its own line
        for line in lines:
            self.assertLessEqual(cell_width(line), 50, line)


if __name__ == '__main__':
    unittest.main()
