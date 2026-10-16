"""Distinct states (P-PRES-11) and readable times (P-PRES-06).

The Inspector's read model reports the observation, the repository intent and the policy's newest operation as three
separate states, each from its own records: the observation's freshness by age apart from the proposal's own check
against the service; the intent's own revision and whether the repository still matches it; the operation's journal
status and readback. The summary states times to the second with their zone; the exact values stay in the typed
details and the raw record. The real store, modeled service and maintenance engine produce each state.
"""
import re
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
        # Recency and currentness kept apart (TASK-11 2.6 item 2): captured recently, yet the source moved on.
        self.assertIn('captured recently (fresh by age); the source has changed since capture (revision 1, now 2)', text)
        self.assertIn('Intent', text)
        self.assertIn('e9274102 from orgs/reference/dev / intune-reference at 21efad0e (content verified)', text)
        self.assertIn('(content verified); the repository changed since its recorded intent: changed '
                      'stacks/orgs/reference/dev.yaml', text)
        self.assertIn('Operation', text)
        self.assertIn("4d972e93 reconciled; reconcile's readback: desired state observed", text)

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
        self.assertIn('[REFUSED] The recorded intent no longer matches the repository (workbench_repository_stale)', text)  # the exact code stays
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
        self.assertIn('Cause: The source changed since this observation was captured (revision 1, now 2)', text)

    def test_the_verdict_is_said_once(self):
        workspace = self.workspace({}, 'propose /w/d.json /w/op')
        workspace.receive({'status': 'error', 'error': {'code': 'workbench_repository_stale', 'message': 'Refused.'}})
        self.assertNotIn('REFUSED', workspace.notice)

    def test_notices_say_what_a_command_recorded(self):
        workspace = self.workspace({}, 'reconcile /w/op')
        notice = workspace._notice_for({'operation_id': 'a' * 32, 'journal_status': 'reconciled',
                                        'classification': 'desired_state_observed'})
        self.assertEqual(notice, "reconcile ran; the journal is now reconciled (reconcile's readback: desired state "
                                 'observed).')
        workspace = self.workspace({}, 'repository-refresh ' + 'b' * 40)
        notice = workspace._notice_for({'artifact_id': 'c' * 64, 'kind': 'repository_intent', 'data': {}, 'created': True})
        self.assertEqual(notice, 'repository-refresh recorded repository intent cccccccccccc.')
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
        # PKG-PRES-RUN4 item 17: Delivery has no surface number, so it is named as the key that opens it.
        self.assertIn('Lifecycle: 9 Repository > 5 Plan (here) > 6 Execution > Delivery (v opens it)', text)
        # Run 9 (frame 18): the placeholder template stands on its own row after the sentence, so a copied row carries
        # no words; the sentence and the template are both still said.
        self.assertIn('Next: approve and run it with the review digest (6 Execution shows the result). In the workspace: '
                      'execute OPERATION_DIR DIGEST From a shell: intune-iac workbench execute --operation OPERATION_DIR '
                      '--approve-digest DIGEST', text)  # run 12 item 3

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
        self.assertIn('Next: Refresh the repository intent first (a: actions)', text)
        self.assertNotIn('a prepares a proposal from the recorded intent', text)
        prepared = {'operation_id': 'a' * 32, 'object_id': OBJECT, 'status': 'prepared', 'expires_at': time.time() + 200}
        text = self.summary(4, dict(prepared, expires_at=time.time() - 1))
        # Run 8 item 7: the Approval window row and the Context file row state the facts; the Next lines are the steps.
        self.assertIn('Next: Prepare a proposal from the recorded intent (a: actions); this plan cannot run because its approval window closed at ', text)
        self.assertNotIn('execute OPERATION_DIR', text)
        text = self.summary(4, dict(prepared, repository={'cited': None, 'context_changed': True}))
        self.assertIn('Next: Prepare a proposal from the recorded intent (a: actions).', text)
        self.assertNotIn('context file changed, so execute refuses it', text)
        text = self.summary(4, dict(prepared, repository={'cited': True, 'freshness': 'stale'}))
        self.assertIn('repository changed since its intent, so execute refuses it', text)
        text = self.summary(5, {'operation_id': 'a' * 32, 'status': 'outcome_unknown'})
        self.assertIn('Next: Reconcile it (a: actions); it never replays the change', text)
        text = self.summary(5, {'operation_id': 'a' * 32, 'status': 'succeeded_verified'})
        self.assertIn('Next: v shows every delivery stage, including the deployment record', text)
        self.assertNotIn('unknown outcome', text)

    def test_delivery_carries_its_own_stages_and_next_step(self):
        # Delivery is the lifecycle in full; a second line pointing at it from itself would only repeat.
        text = self.summary(5, {'schema_version': 'workbench-delivery/1', 'operation_id': 'a' * 32, 'stages': [],
                                'next_action': 'Nothing pending.'})
        self.assertNotIn('Lifecycle:', text)

    def test_a_blocked_proposal_is_not_offered_as_next_on_the_repository(self):
        workspace = self.surface()
        workspace.facts['eligibility'] = {'code': 'maintenance_observation_stale', 'reason': 'not_fresh',
                                          'freshness_reasons': ['stamped_after_now']}
        workspace.tab, workspace.value = 8, {'schema_version': 'workbench-repository-status/1', 'object_id': OBJECT,
                                             'freshness': {'status': 'current'}}
        text = ' '.join(' '.join(workspace._summary_lines(118)).split())
        # PKG-PRES-RUN20 item 4: the check's reason is the name, the engine's refusal code is not.
        self.assertIn('a proposal is blocked now (not_fresh); 2 Inspector says why', text)
        self.assertNotIn('a prepares a proposal from the recorded intent', text)

    def test_the_plan_review_labels_the_before_column_as_of_preparation(self):
        workspace = self.surface()
        workspace.tab, workspace.value = 4, {'operation_id': 'a' * 32, 'object_id': OBJECT, 'status': 'succeeded_verified',
            'field_changes': {'status': 'changed', 'changes': [{'field': 'description', 'kind': 'changed', 'path': '/description',
                                                               'before': 'old', 'after': 'new'}]}}
        text = ' '.join(workspace._summary_lines(118))
        self.assertIn('BEFORE (observed when prepared)', text)

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
        self.assertIn('recorded 2026-10-14 19:57:00 UTC', text)


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


class SurfaceListTests(unittest.TestCase):
    """Journey 26: Coverage baselines in words, one row per operation."""
    surface = RefusalCauseTests.workspace

    def test_coverage_baselines_read_as_words_with_readable_times(self):
        workspace = self.surface()
        workspace.tab = 6
        workspace.value = {'schema_version': 'workbench-four-views/1', 'comparisons': {
            'collector_snapshot_delta': {'status': 'different', 'baseline': {
                'kind': 'prior_collector_snapshot', 'snapshot_id': '90a2985ff4957351' + '0' * 48,
                'observed_at': '2026-10-14T22:23:00.049219Z'}},
            'repository_vs_deployment': {'status': 'equal', 'baseline': {
                'kind': 'verified_local_modeled_deployment', 'evidence_class': 'verified_local_modeled_deployment',
                'artifact_id': '7a28be59af174923' + '0' * 48, 'operation_id': '54bbab727d1e4eee' + '0' * 16,
                'recorded_at': 1792016581.3878012, 'plan_sha256': 'ea650a4d199fa3fd' + '0' * 48}},
            'provider_refresh_vs_state': {'status': 'unknown', 'baseline': 'baseline_missing_or_incomplete'}}}
        text = ' '.join(' '.join(workspace._summary_lines(118)).split())
        self.assertNotIn('{"', text)
        self.assertNotIn('1792016581', text)
        self.assertIn('Collector snapshot delta: different', text)
        self.assertIn('prior collector snapshot 90a2985ff495, observed 2026-10-14 22:23:00 UTC', text)
        self.assertIn('verified local modeled deployment 7a28be59af17 of operation 54bbab727d1e (plan ea650a4d199f), '
                      'recorded 2026-10-14', text)
        self.assertIn('baseline missing or incomplete', text)

    def test_a_filter_that_matches_nothing_says_so(self):
        workspace = self.surface()
        workspace.tab = 0
        workspace.value = {'objects': [], 'total_inventory_objects': 1, 'pagination': {'total_objects': 0},
                           'filters': {'query': None, 'ownership': 'owned_elsewhere', 'coverage': 'complete_fresh',
                                       'health': None}}
        text = ' '.join(' '.join(workspace._summary_lines(118)).split())
        self.assertIn('[NO MATCH] No policy matches ownership owned elsewhere and coverage complete fresh', text)
        self.assertIn('0 of 1 policy in the inventory', text)
        self.assertIn('f changes the filters', text)

    def test_coverage_values_read_as_words(self):
        workspace = self.surface()
        workspace.tab = 6
        workspace.value = {'schema_version': 'workbench-four-views/1', 'comparisons': {},
                           'coverage': {'observation': 'complete_fresh', 'mapping': 'supported_comparison_only'}}
        text = ' '.join(' '.join(workspace._summary_lines(118)).split())
        self.assertIn('Observation coverage: complete fresh', text)
        self.assertIn('Mapping: supported comparison only', text)

    def test_each_operation_is_one_row_with_its_latest_status(self):
        from intune_iac.workbench_tui import operation_list
        records = [{'operation_id': 'a' * 32, 'operation_root': '/w/op', 'status': 'prepared', 'recorded_at': '2026-10-14T22:23:00Z'},
                   {'operation_id': 'a' * 32, 'operation_root': '/w/op', 'status': 'succeeded_verified', 'recorded_at': '2026-10-14T22:23:01Z'},
                   {'operation_id': 'b' * 32, 'operation_root': '/w/op2', 'status': 'prepared', 'recorded_at': '2026-10-14T22:24:00Z'}]
        rows = operation_list(records)
        self.assertEqual([(row['operation_id'][0], row['status'], row['journal_records']) for row in rows],
                         [('a', 'succeeded_verified', 2), ('b', 'prepared', 1)])
        workspace = self.surface()
        workspace.tab, workspace.operation_rows, workspace.operation_highlight = 4, rows, 0
        workspace.value = {'operations': records}
        text = ' '.join(workspace._summary_lines(118))
        self.assertEqual(text.count('a' * 32), 1)
        self.assertIn('succeeded verified (2 journal records)', text)


class FilterLayerTests(unittest.TestCase):
    """f lists every estate filter with the one in use marked; Enter applies one as a read-only query."""
    def workspace(self, page_command='overview 10 0'):
        from collections import deque
        from intune_iac.workbench_tui import Workspace
        workspace = Workspace.__new__(Workspace)
        workspace.__dict__.update(
            tab=0, value={'objects': []}, selected=None, facts={}, highlight=0, scroll=0, mode=None, buffer='', cursor=0,
            pasting=False, input_overflow=False, notice='', last_command='overview', view_command='overview',
            page_command=page_command, rows=[{'object_id': OBJECT}], operation_rows=[], operation_highlight=0,
            active_operation=None, execution_result=None, active_service=None, active_adoption=None,
            active_adoption_plan=None, pending=deque(), size=(100, 40), submission_key='enter', entry_focus=0,
            overview_focus=0, layer='summary', trail=[], _detail_cache=None, staged=None, action_focus=0, quiet=None,
            store=type('S', (), {'tenant_id': TENANT})())
        workspace.draw = lambda: None
        workspace.save_context = lambda: None
        return workspace

    def keys(self, workspace, keys):
        class Stop(Exception):
            pass
        class Reader:
            def __init__(self, keys): self.keys = list(keys)
            def read(self):
                if not self.keys: raise Stop()
                return self.keys.pop(0)
        workspace.key_reader = Reader(keys)
        try:
            return workspace.input('')
        except Stop:
            return None

    def test_f_lists_every_filter_in_words_with_the_one_in_use_marked(self):
        workspace = self.workspace('views-page 10 0 - - stale_or_incomplete -')
        self.assertIsNone(self.keys(workspace, [('char', 'f')]))
        self.assertEqual(workspace.layer, 'filters')
        text = '\n'.join(workspace._data_lines(100))
        self.assertTrue(text.startswith('FILTERS'), text[:80])
        for words in ('owned elsewhere', 'no ownership found in declared scope', 'complete fresh', 'reporting incomplete'):
            self.assertIn(words, text)
        self.assertIn('* stale or incomplete', text)  # the coverage filter in use
        self.assertIn('> owned here', text)  # the focus starts on the first choice
        self.assertIn('read-only', text)

    def test_enter_applies_one_filter_and_keeps_the_others(self):
        workspace = self.workspace('views-page 25 50 Privacy - stale_or_incomplete -')
        command = self.keys(workspace, [('char', 'f'), 'down', 'enter'])
        # Down moves to 'owned elsewhere'; the query and the coverage filter stay; the page starts again.
        self.assertEqual(command, 'views-page 25 0 Privacy owned_elsewhere stale_or_incomplete -')
        self.assertEqual((workspace.layer, workspace.tab), ('summary', 0))

    def test_choosing_any_clears_that_filter_and_escape_closes(self):
        workspace = self.workspace('views-page 10 0 - owned_here - -')
        command = self.keys(workspace, [('char', 'f')] + ['down'] * 5 + ['enter'])
        self.assertEqual(command, 'views-page 10 0 - - - -')
        workspace = self.workspace()
        self.assertIsNone(self.keys(workspace, [('char', 'f'), 'escape']))
        self.assertEqual(workspace.layer, 'summary')


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


class ClockHoldPresentationTests(unittest.TestCase):
    """PKG-PRES-HOLD items 2 to 6 on the screens: unknown is not stale; the recovery names its times and is not cut;
    the band names the recovery; a clock hold leads a repository change."""
    workspace = RefusalCauseTests.workspace
    FACT = {'reads': 1_800_000_000.0, 'recorded': 1_800_000_266.0}
    TIMES = "this host's clock reads 2027-01-15 08:00:00 UTC; this workspace recorded 2027-01-15 08:04:26 UTC"
    REPOSITORY = {'area': 'repository', 'code': 'repository_stale', 'observed': 'The repository changed.',
                  'next_step': 'Refresh.', 'evidence': {}}

    def stale(self, *reasons, **evidence):
        return {'area': 'freshness', 'code': 'observation_stale', 'observed': 'The newest observation is not known to '
                'be fresh.', 'next_step': 'Wait.', 'evidence': dict(evidence, freshness_reasons=list(reasons))}

    # Item 2: the strip.
    def test_the_strip_reads_age_unknown_and_never_stale_for_a_hold(self):
        from intune_iac.workbench_screens import context_strip
        facts = {'name': 'Pilot', 'observation': 'age unknown', 'repository': 'current'}
        self.assertIn('OBS age unknown', context_strip(TENANT, OBJECT, facts, 120))
        strips = {width: context_strip(TENANT, OBJECT, facts, width) for width in range(40, 121)}
        self.assertTrue(any('OBS age?' in strip for strip in strips.values()), strips)
        for width, strip in strips.items():
            self.assertNotIn('stale', strip, width)

    def test_the_workspace_reads_a_hold_as_age_unknown_and_an_old_observation_as_stale(self):
        workspace = self.workspace()
        for reasons in (['clock_moved_backward'], ['older_than_window', 'clock_floor_invalid']):
            workspace._learn({'object_id': OBJECT, 'freshness': 'stale', 'freshness_reasons': reasons})
            self.assertEqual(workspace.facts['observation'], 'age unknown', reasons)
        workspace._learn({'object_id': OBJECT, 'freshness': 'stale', 'freshness_reasons': ['older_than_window']})
        self.assertEqual(workspace.facts['observation'], 'stale')
        workspace._learn({'object_id': OBJECT, 'freshness': 'fresh', 'freshness_reasons': []})
        self.assertEqual(workspace.facts['observation'], 'fresh')

    def test_age_unknown_is_a_hazard_the_strip_keeps_ahead_of_the_repository(self):
        from intune_iac.workbench_screens import HAZARD_STATES, _strip_severity
        self.assertIn('age unknown', HAZARD_STATES['OBSERVED'])
        self.assertLess(_strip_severity(('OBSERVED', 'OBS', 'age unknown')), _strip_severity(('REPOSITORY', 'REPO', 'stale')))
        self.assertGreater(_strip_severity(('OBSERVED', 'OBS', 'stale')), _strip_severity(('REPOSITORY', 'REPO', 'stale')))

    # Item 5: the band names the recovery.
    def test_the_band_names_the_recovery_in_each_form(self):
        from intune_iac.workbench_screens import _band_forms
        self.assertEqual(tuple(_band_forms(self.stale('clock_moved_backward'))), (
            '! Observation age unknown: host clock behind a recorded time. Correct the clock, then restart (i: details)',
            '! Age unknown: clock behind. Correct it, restart (i)', '! Clock behind. i: details'))
        self.assertEqual(tuple(_band_forms(self.stale('clock_floor_invalid'))), (
            '! Observation age unknown: the recorded time cannot be read. Changes stay held until it can (i: details)',
            '! Age unknown: recorded time unreadable. Held until readable (i)', '! Time record unreadable. i: details'))

    def test_the_recovery_keys_are_dropped_where_no_key_can_be_taken(self):
        from intune_iac.workbench_screens import hazard_rows
        for code in ('clock_moved_backward', 'clock_floor_invalid'):
            rows = hazard_rows({}, [self.stale(code)], 120, routes=False)
            self.assertTrue(rows[0].startswith('! '), rows)
            self.assertNotIn('(i', ' '.join(rows))
            self.assertNotIn('i: details', ' '.join(rows))

    # Item 6: one order for two hazards.
    def test_a_clock_hold_leads_the_band_and_the_repository_change_is_counted(self):
        from intune_iac.workbench_screens import hazard_rows
        for signals in ([self.REPOSITORY, self.stale('clock_moved_backward')],
                        [self.stale('clock_moved_backward'), self.REPOSITORY]):
            rows = hazard_rows({}, signals, 160)
            self.assertTrue(rows[0].startswith('! Observation age unknown'), rows)
            self.assertIn('+1 more', ' '.join(rows))
            narrow = hazard_rows({}, signals, 120)
            self.assertTrue(narrow[0].startswith('! Age unknown') or narrow[0].startswith('! Observation age unknown'), narrow)
            self.assertIn('+1 more', ' '.join(narrow))
        rows = hazard_rows({}, [self.stale('older_than_window'), self.REPOSITORY], 120)
        self.assertTrue(rows[0].startswith('! Repository changed'), rows)  # an ordinary stale observation does not lead

    # Items 3 and 4: the refusal.
    def refusal_text(self, facts):
        workspace = self.workspace(facts, 'propose-from-intent /w/op')
        workspace.receive({'status': 'error', 'error': {'code': 'maintenance_observation_stale', 'message': 'Refused.',
                                                         'effects': {'files_written': [], 'operation_created': False}}})
        return ' '.join(' '.join(workspace._surface_summary(118)).split())

    def test_the_refusal_next_names_the_times_from_the_signal_or_the_check(self):
        signal = self.stale('clock_moved_backward', freshness_clock=self.FACT)
        check = {'code': 'maintenance_observation_stale', 'reason': 'not_fresh',
                 'freshness_reasons': ['clock_moved_backward'], 'freshness_clock': self.FACT}
        for facts in ({'signals': [signal]}, {'eligibility': check}):
            text = self.refusal_text(facts)
            self.assertIn('then restart the workbench and Prepare a proposal from the recorded intent (a: actions; %s).' % self.TIMES, text)
        unreadable = self.stale('clock_floor_invalid', freshness_clock={'reads': 1_800_000_000.0, 'recorded': None})
        # PKG-PRES-RUN4 item 18: one bracket, not two in a row; the times join what it already says in brackets.
        self.assertIn("(Diagnostics shows where it is kept; this host's clock reads 2027-01-15 08:00:00 UTC; the time this workspace recorded cannot be read)",
                      self.refusal_text({'signals': [unreadable]}))

    def test_a_refusal_without_the_fact_invents_no_time(self):
        text = self.refusal_text({'signals': [self.stale('clock_moved_backward')]})
        self.assertIn('then restart the workbench and Prepare a proposal from the recorded intent (a: actions).', text)
        self.assertNotIn("this host's clock reads 2", text)

    # Item 4: the one-line blocked notice.
    def blocked_notice(self, width, hold, count=None):
        workspace = self.workspace()
        workspace.size = (width, 40)
        blocked = {'code': 'maintenance_observation_stale', 'reason': 'not_fresh', 'clock_hold': hold,
                   'message': 'the newest observation\'s age cannot be established (a very long engine sentence ' * 3}
        self.assertIsNone(workspace._stage({'available': False, 'blocked': blocked}))
        return workspace.notice

    def test_the_blocked_notice_leads_with_the_hold_and_fits_the_pane(self):
        from intune_iac.workbench_tui import cell_width
        self.assertEqual(self.blocked_notice(160, 'clock_moved_backward'),
                         "Blocked: this host's clock reads earlier than a time this workspace recorded; correct the clock "
                         'or wait, then restart (i: details). Nothing was staged.')
        for hold in ('clock_moved_backward', 'clock_floor_invalid'):
            for width in (160, 120, 100, 80, 60, 40):
                notice = self.blocked_notice(width, hold)
                self.assertLessEqual(cell_width(notice), width, (hold, width, notice))
                self.assertTrue(notice.startswith('Blocked'), notice)
                self.assertNotIn('age cannot be established', notice)
                self.assertIn('(i', notice)
        self.assertIn('clock', self.blocked_notice(40, 'clock_moved_backward'))
        self.assertIn('Nothing was staged.', self.blocked_notice(120, 'clock_moved_backward'))

    def test_a_blocked_action_without_a_hold_keeps_its_notice(self):
        workspace = self.workspace()
        workspace._stage({'available': False, 'blocked': {'code': 'service_required', 'message': 'needs a service'}})
        self.assertEqual(workspace.notice, 'Blocked: needs a service. Nothing was staged.')


if __name__ == '__main__':
    unittest.main()


class CollectionResultTests(unittest.TestCase):
    """Journey 28 review S4: after a collect the surface says what the run recorded and the next step, not only the
    evidence keys."""
    RUN = {'run_id': 7, 'tenant_id': TENANT, 'status': 'complete', 'coverage': 'complete', 'object_count': 1,
           'started_at': '2026-10-15T03:29:59Z', 'observed_at': '2026-10-15T03:30:00Z', 'completed_at': '2026-10-15T03:30:01Z',
           'error_code': None, 'evidence_class': 'synthetic', 'collections': []}

    def test_the_run_its_reading_its_effect_and_the_next_step(self):
        from intune_iac.workbench_screens import collection_result_lines
        text = ' '.join(' '.join(collection_result_lines(self.RUN, 120)).split())
        self.assertIn('[COLLECTION RESULT]', text)
        self.assertIn('Run 7: complete; 1 policy observed at 2026-10-15 03:30:00 UTC.', text)
        self.assertIn('Read: policy list, settings and assignments read in full.', text)
        self.assertIn('Effect: recorded collection run 7; no policy was changed.', text)
        self.assertIn('Next: 2 reads this policy again with this observation.', text)

    def test_the_inspector_shows_it_after_a_collect(self):
        workspace = StateSurfaceTests.workspace(self, 1, dict(self.RUN))
        text = StateSurfaceTests.summary(self, workspace)
        self.assertIn('[COLLECTION RESULT]', text)
        self.assertIn('Run 7: complete', text)


class ReconcileReadbackWordsTests(unittest.TestCase):
    """Journey 28 review S2: reconcile's readback is called that wherever it is shown."""
    RESULT = {'operation_id': 'a' * 32, 'journal_status': 'reconciled', 'previous_status': 'outcome_unknown',
              'classification': 'desired_state_observed', 'evidence_class': 'synthetic_local_process_and_modeled_service_only',
              'effects': {'replayed': False}}

    def test_the_execution_surface_labels_reconciles_readback(self):
        workspace = StateSurfaceTests.workspace(self, 5, dict(self.RESULT))
        text = StateSurfaceTests.summary(self, workspace)
        self.assertIn("Reconcile's readback: desired state observed", text)


class ApprovalWindowStateTests(unittest.TestCase):
    """Journey 28 run 3, frames 75 to 80: a prepared operation's state line says its approval window's state."""

    def line(self, window):
        from intune_iac.workbench_screens import state_lines
        states = {'operation': {'operation_id': '62cd1dcf' + 'a' * 24, 'status': 'prepared', 'journal_status': 'prepared',
                                'approval_window': window, 'recorded_at': '2026-10-15T05:18:29Z'}}
        return ' '.join(' '.join(state_lines(states, 160)).split())

    def test_each_window_state_is_said(self):
        self.assertIn('approval window closed (recorded)', self.line('closed_recorded'))
        self.assertIn("approval held: this host's clock reads earlier than a time it recorded", self.line('clock_moved_backward'))
        self.assertIn('approval window open', self.line('open'))
        self.assertIn('store last registered 2026-10-15 05:18:29 UTC', self.line('open'))

    def test_the_band_and_strip_name_a_hold(self):
        from intune_iac.workbench_screens import context_strip, hazard_rows
        from intune_iac.workbench_tui import OPERATION_FROM_SIGNAL, cell_width
        signal = {'area': 'operations', 'code': 'operation_approval_held', 'observed': 'Held.', 'next_step': 'Wait.',
                  'evidence': {'operation_id': '62cd1dcf' + 'a' * 24}}
        for width in (120, 80, 60, 40):
            rows = hazard_rows({}, [signal], width)
            self.assertTrue(rows and rows[0].startswith('! '), rows)
            self.assertIn('eld', rows[0])
            for row in rows:
                self.assertLessEqual(cell_width(row), width, row)
        self.assertEqual(OPERATION_FROM_SIGNAL['operation_approval_held'], 'held')
        strip = context_strip(TENANT, OBJECT, {'name': 'P', 'operation': 'held'}, 200, 'synthetic')
        self.assertIn('OP held', strip)


class NewestOperationTests(unittest.TestCase):
    """Journey 28 run 3, frames 75 and 77: a later event on an older operation does not make it the newest."""

    def test_the_newest_is_the_one_prepared_last_in_its_latest_state(self):
        from intune_iac.workbench_diagnostics import _newest_operation
        records = [{'operation_id': 'a' * 32, 'status': 'prepared', 'recorded_at': 'T1', 'operation_root': None},
                   {'operation_id': 'b' * 32, 'status': 'prepared', 'recorded_at': 'T2', 'operation_root': None},
                   {'operation_id': 'a' * 32, 'status': 'prepared', 'recorded_at': 'T3', 'operation_root': None},
                   {'operation_id': 'b' * 32, 'status': 'reconciled', 'recorded_at': 'T4', 'operation_root': None},
                   {'operation_id': 'a' * 32, 'status': 'prepared', 'recorded_at': 'T5', 'operation_root': None}]
        newest = _newest_operation(records)
        self.assertEqual(newest['operation_id'], 'b' * 32)
        self.assertEqual(newest['status'], 'reconciled')
        self.assertEqual(newest['recorded_at'], 'T4')


class AdoptedSummaryTests(unittest.TestCase):
    """Journey 28 run 3, frames 02 and 03: after adopting, the mode is known and reopening needs no --service-root."""
    RESULT = {'status': 'adopted_local_model', 'handoff_root': '/w/handoff', 'service_root': '/w/handoff/service',
              'object_ids': [OBJECT], 'collection_run_id': 1, 'adoptions': [{'artifact_id': 'a' * 64}],
              'cloud_authority': False, 'execution_authorized': False, 'remote_import_performed': False,
              'ownership': 'unknown', 'original_journey_preserved': True, 'evidence_class': 'synthetic'}

    def test_the_next_step_does_not_ask_for_the_service_root(self):
        from intune_iac.workbench_screens import adoption_lines
        text = ' '.join(' '.join(adoption_lines(dict(self.RESULT), 160)).split())
        self.assertNotIn('--service-root', text.replace('without --service-root', ''))
        self.assertIn("reopen the workspace: it uses this handoff's modeled service", text)

    def test_the_strip_states_the_adopted_evidence_mode(self):
        workspace = StateSurfaceTests.workspace(self, 0, {})
        workspace.mode_class = None
        workspace.selected = None
        workspace._learn(dict(self.RESULT))
        self.assertEqual(workspace.mode_class, 'synthetic')


class ClockHoldBandTests(unittest.TestCase):
    """A clock hold on the observation's age: the band says the age is unknown and never names collecting again, which
    does not clear it. It outranks a stamp ahead of the clock and the generic stale line."""
    # PKG-PRES-HOLD item 5: the forms name the recovery, not only the cause.
    FORMS = {'clock_moved_backward': ('! Observation age unknown: host clock behind a recorded time. Correct the clock, then restart (i: details)',
                                      '! Age unknown: clock behind. Correct it, restart (i)', '! Clock behind. i: details'),
             'clock_floor_invalid': ('! Observation age unknown: the recorded time cannot be read. Changes stay held until it can (i: details)',
                                     '! Age unknown: recorded time unreadable. Held until readable (i)', '! Time record unreadable. i: details')}

    def signal(self, *reasons, **evidence):
        return {'area': 'freshness', 'code': 'observation_stale', 'observed': 'Stale.', 'next_step': 'Wait.',
                'evidence': dict(evidence, freshness_reasons=list(reasons))}

    def test_each_hold_has_its_three_forms(self):
        from intune_iac.workbench_screens import _band_forms
        for code, forms in self.FORMS.items():
            self.assertEqual(tuple(_band_forms(self.signal(code))), forms)

    def test_a_hold_outranks_a_stamp_ahead_and_the_window(self):
        from intune_iac.workbench_screens import _band_forms
        for code, forms in self.FORMS.items():
            for others in (('stamped_after_now',), ('older_than_window',), ('older_than_window', 'stamped_after_now')):
                for cures in (True, False):
                    found = _band_forms(self.signal(*others, code, collect_cures=cures))
                    self.assertEqual(tuple(found), forms, (code, others, cures))
                    self.assertFalse(any('ollect' in form for form in found), found)

    def test_every_form_fits_its_width_and_never_says_collect(self):
        from intune_iac.workbench_screens import hazard_rows
        from intune_iac.workbench_tui import cell_width
        for code in self.FORMS:
            for width in (120, 100, 80, 60, 40):
                rows = hazard_rows({}, [self.signal(code)], width)
                self.assertTrue(rows and rows[0].startswith('! '), rows)
                self.assertNotIn('ollect', ' '.join(rows))
                for row in rows:
                    self.assertLessEqual(cell_width(row), width, row)
        self.assertEqual(hazard_rows({}, [self.signal('clock_moved_backward')], 120)[0],
                         '! Observation age unknown: host clock behind a recorded time. Correct the clock, then restart (i: details)')
        self.assertEqual(hazard_rows({}, [self.signal('clock_floor_invalid')], 40), [self.FORMS['clock_floor_invalid'][2]])

    def test_without_a_hold_the_stale_lines_are_unchanged(self):
        from intune_iac.workbench_screens import _band_forms
        self.assertEqual(_band_forms(self.signal('older_than_window'))[0], '! Observation stale. Next: Collect again (a: actions)')


class ClockHeldRefusalTests(unittest.TestCase):
    """A refusal on an observation whose age cannot be established (a clock hold): the screen never names collecting
    again as the next step, because collecting again does not clear it. Every other refusal keeps its step."""
    workspace = RefusalCauseTests.workspace
    REFUSED = {'status': 'error', 'error': {'code': 'maintenance_observation_stale', 'message': 'Refused.'}}
    MOVED = ('Collecting again does not clear this: correct the host clock, or wait until it reads at or after the time '
             'this workspace recorded, then restart the workbench and Prepare a proposal from the recorded intent (a: actions).')
    UNREADABLE = ("Collecting again does not clear this: changes stay held until the workspace's recorded time can be "
                  'read again (Diagnostics shows where it is kept).')
    HOLDS = (('clock_moved_backward', MOVED), ('clock_floor_invalid', UNREADABLE))

    def stale(self, *reasons):
        return {'area': 'freshness', 'code': 'observation_stale', 'evidence': {'freshness_reasons': list(reasons)},
                'observed': 'The newest observation (2026-10-14 22:40:01 UTC) is stale.'}

    def refused(self, facts):
        workspace = self.workspace(facts, 'propose-from-intent /w/op')
        workspace.receive(dict(self.REFUSED))
        return ' '.join(' '.join(workspace._surface_summary(118)).split())

    def test_the_cause_kind_follows_the_hold_in_the_observation_signal(self):
        for code, step in self.HOLDS:
            workspace = self.workspace({'signals': [self.stale('older_than_window', code)]})
            cause, kind = workspace._known_cause('maintenance_observation_stale')
            self.assertEqual(kind, 'observation_' + code)
            self.assertIn('The newest observation', cause)

    def test_the_cause_kind_follows_the_hold_in_the_proposal_check(self):
        for code, step in self.HOLDS:
            eligibility = {'code': 'maintenance_observation_stale', 'reason': 'not_fresh', 'freshness_reasons': [code]}
            cause, kind = self.workspace({'eligibility': eligibility})._known_cause('maintenance_observation_stale')
            self.assertEqual(kind, 'observation_' + code)
            self.assertIn('age cannot be established', cause)

    def test_a_held_refusal_names_the_recovery_not_collecting(self):
        for code, step in self.HOLDS:
            for facts in ({'signals': [self.stale(code)]},
                          {'eligibility': {'code': 'maintenance_observation_stale', 'reason': 'not_fresh',
                                           'freshness_reasons': [code]}}):
                text = self.refused(facts)
                self.assertIn('[REFUSED] The observation is not fresh (maintenance_observation_stale)', text)
                self.assertIn('Next: ' + step, text)
                self.assertNotIn('Next: Collect again', text)
                self.assertNotIn('Collect again', text)

    def test_the_refusal_without_a_hold_keeps_its_step(self):
        workspace = self.workspace({'signals': [self.stale('older_than_window')]})
        self.assertEqual(workspace._known_cause('maintenance_observation_stale')[1], 'observation_stale')
        self.assertIn('Next: Collect again (a lists it), then Prepare a proposal from the recorded intent (a: actions).',
                      self.refused({'signals': [self.stale('older_than_window')]}))

    def test_the_general_text_stays_true_when_no_cause_is_known(self):
        from intune_iac.workbench_screens import REFUSALS, refusal_lines
        meaning, step = REFUSALS['maintenance_observation_stale']
        self.assertEqual(meaning, 'The newest observation of this policy is not fresh, or the service changed after it was '
                                  'collected; a change is never prepared against it.')
        self.assertEqual(step, "Collect again, then Prepare a proposal from the recorded intent (both in a: actions); i shows the observation's "
                               'freshness. If i says its age cannot be established (a clock hold), collecting again does '
                               'not clear it: correct the host clock and restart the workbench.')
        text = ' '.join(' '.join(refusal_lines(self.REFUSED, 160)).split())
        self.assertIn('Next: ' + step, text)


class StampedAheadWordsTests(unittest.TestCase):
    """PKG-PRES-RUN7 item 1 (journey 28 run 7, frames 40 to 45): an observation stamped after this host's clock has an
    age that is not known, so no surface calls it stale; a stale word names the cause the record gives."""
    workspace = RefusalCauseTests.workspace
    CHECKED, STAMP = '2026-10-15T14:25:23Z', '2026-10-15T14:40:23Z'

    def test_the_strip_says_age_unknown_for_a_stamp_ahead_and_names_the_cause(self):
        workspace = self.workspace()
        workspace._learn({'object_id': OBJECT, 'freshness': 'stale', 'freshness_reasons': ['stamped_after_now']})
        self.assertEqual(workspace.facts['observation'], 'age unknown (stamped ahead)')
        from intune_iac.workbench_screens import context_strip
        facts = {'name': 'Pilot', 'observation': 'age unknown (stamped ahead)', 'repository': 'current'}
        self.assertIn('OBS age unknown (stamped ahead)', context_strip(TENANT, OBJECT, facts, 140))
        for width in range(40, 141):
            self.assertNotIn('stale', context_strip(TENANT, OBJECT, facts, width))

    def test_the_strip_names_a_later_collection_that_did_not_complete(self):
        workspace = self.workspace()
        workspace._learn({'object_id': OBJECT, 'freshness': 'stale', 'freshness_reasons': ['later_collection_not_complete']})
        self.assertEqual(workspace.facts['observation'], 'stale (later collection incomplete)')
        workspace._learn({'object_id': OBJECT, 'freshness': 'stale', 'freshness_reasons': ['older_than_window']})
        self.assertEqual(workspace.facts['observation'], 'stale')

    def test_a_cause_named_state_is_a_hazard_that_shortens_at_narrow_widths(self):
        from intune_iac.workbench_screens import context_strip
        for state in ('age unknown (stamped ahead)', 'stale (later collection incomplete)'):
            facts = {'name': 'Pilot', 'observation': state, 'repository': 'current'}
            strips = {width: context_strip(TENANT, OBJECT, facts, width) for width in range(40, 141)}
            self.assertIn('OBS ' + state, strips[140])
            short = 'OBS age?' if state.startswith('age') else 'OBS stale'
            self.assertTrue(any(short in strip for strip in strips.values()), strips)

    def test_the_inspector_row_says_the_age_is_not_known_and_names_both_times(self):
        from intune_iac.workbench_screens import state_lines
        observation = {'evidence_class': 'synthetic', 'run_id': 5, 'observed_at': self.STAMP, 'coverage': 'complete',
                       'freshness': 'stale', 'freshness_reasons': ['stamped_after_now'],
                       'freshness_checked_at': self.CHECKED, 'eligibility': None}
        text = ' '.join(' '.join(state_lines({'observation': observation}, 200)).split())
        self.assertIn("age not known (stamped after this host's clock: this host's clock read 2026-10-15 14:25:23 UTC)", text)
        self.assertIn('2026-10-15 14:40:23 UTC', text)
        self.assertNotIn('stale', text)

    def test_the_attention_item_says_not_known_to_be_fresh_and_names_both_times(self):
        from intune_iac.workbench_diagnostics import _freshness
        signals, _ = _freshness({'observed_at': self.STAMP, 'freshness': 'stale', 'freshness_reasons': ['stamped_after_now'],
                                 'freshness_checked_at': self.CHECKED, 'snapshot_id': 'b' * 64,
                                 'next_collection_replaces': 'same_service', 'ordering_service_root': '/w/a b'}, False)
        sentence = signals[0]['observed']
        self.assertEqual(sentence, 'The newest observation (2026-10-15 14:40:23 UTC) is not known to be fresh: its age is '
                         "not known, because it is stamped later than this host's clock read when it was checked "
                         '(2026-10-15 14:25:23 UTC).')
        self.assertNotIn('stale', sentence)

    def test_the_read_model_carries_the_clock_reading_to_the_states(self):
        from intune_iac.workbench import _states
        observed = _states({'freshness': 'stale', 'freshness_reasons': ['stamped_after_now'],
                            'freshness_checked_at': self.CHECKED, 'observed_at': self.STAMP}, None,
                           {'checked': {}, 'signals': []}, None)['observation']
        self.assertEqual(observed['freshness_checked_at'], self.CHECKED)


class RestoreProposalWordsTests(unittest.TestCase):
    """PKG-PRES-RUN7 item 2 (run 7 frame 68): a successful restore proposal says which files it wrote."""
    workspace = StateSurfaceTests.workspace
    summary = StateSurfaceTests.summary
    REVIEW = {'operation_id': '4d972e93' + 'a' * 24, 'object_id': OBJECT, 'status': 'prepared', 'tenant_id': TENANT,
              'approval_digest': 'd' * 64, 'expires_at': 1792005916}

    def test_the_plan_review_lists_the_written_files_quoted(self):
        value = dict(self.REVIEW, files_written=['/w/journey 28/restore.restore-desired.json'])
        text = self.summary(self.workspace(4, value))
        self.assertIn("Input files written: '/w/journey 28/restore.restore-desired.json'", text)

    def test_the_plan_review_says_when_it_wrote_none_and_a_plain_review_says_nothing(self):
        self.assertIn('Input files written: none', self.summary(self.workspace(4, dict(self.REVIEW, files_written=[]))))
        self.assertNotIn('Input files written', self.summary(self.workspace(4, dict(self.REVIEW))))


class StripOperationNamingTests(unittest.TestCase):
    """PKG-PRES-RUN7 item 3 (run 7 frame 70): the strip names the operation it reports when that is not the newest one
    for the policy, so it and the Operation row never describe two operations under one word."""
    NEWEST, SHOWN = 'a59ec849' + 'a' * 24, '90ef8bc2' + 'b' * 24

    def facts(self, shown, newest, state='expired'):
        facts = {'name': 'Pilot', 'observation': 'fresh', 'repository': 'current', 'operation': state}
        if shown:
            facts['operation_id'] = shown
        if newest:
            facts['states'] = {'operation': {'operation_id': newest}}
        return facts

    def test_an_operation_that_is_not_the_newest_is_named(self):
        from intune_iac.workbench_screens import context_strip
        for width in (110, 130):
            strip = context_strip(TENANT, OBJECT, self.facts(self.SHOWN, self.NEWEST), width)
            self.assertRegex(strip, r'OP(ERATION)? 90ef8bc2 expired')
            self.assertNotIn('a59ec849', strip)

    def test_the_newest_operation_and_an_unknown_one_are_not_named(self):
        from intune_iac.workbench_screens import context_strip
        for facts in (self.facts(self.NEWEST, self.NEWEST), self.facts(None, self.NEWEST), self.facts(self.SHOWN, None)):
            strip = context_strip(TENANT, OBJECT, facts, 130)
            self.assertRegex(strip, r'OP(ERATION)? expired')
            self.assertNotIn('90ef8bc2', strip)

    def test_the_narrow_forms_keep_the_name_beside_the_hazard(self):
        from intune_iac.workbench_screens import context_strip
        facts = self.facts(self.SHOWN, self.NEWEST, 'outcome_unknown')
        strips = [context_strip(TENANT, OBJECT, facts, width) for width in range(60, 131)]
        self.assertTrue(any(re.search(r'OP(ERATION)? 90ef8bc2 (outcome )?unknown', strip) for strip in strips), strips[:3])


class StripFormatTests(unittest.TestCase):
    """PKG-PRES-RUN7 item 7 (run 7 frames 38, 39, 57; 42 to 46; 58 to 61; 26 and 27): one strip format. The policy name
    stays whenever it fits, the OP segment shows whenever an operation exists, and each segment has one spelling."""
    NAME = 'Windows Privacy Pilot'

    def facts(self, **extra):
        return dict({'name': self.NAME, 'observation': 'fresh', 'repository': 'current',
                     'eligibility': {'reason': 'service_changed'}}, **extra)

    def test_each_segment_has_one_spelling_at_every_width(self):
        from intune_iac.workbench_screens import context_strip
        for facts in (self.facts(operation='reconciled'), self.facts(), self.facts(operation='outcome_unknown')):
            for width in range(40, 201):
                strip = context_strip(TENANT, OBJECT, facts, width, 'synthetic')
                for long in ('OBSERVED', 'REPOSITORY', 'OPERATION'):
                    self.assertNotIn(long, strip, (width, strip))

    def test_the_policy_name_stays_whenever_it_fits(self):
        from intune_iac.workbench_screens import context_strip
        facts = self.facts(operation='reconciled')
        strip = context_strip(TENANT, OBJECT, facts, 120, 'synthetic')
        self.assertEqual(strip, 'SYNTHETIC | T 11111111 | POLICY Windows Privacy Pilot (22222222) | OBS source changed | '
                                'REPO current | OP reconciled')
        wide = context_strip(TENANT, OBJECT, facts, 140, 'synthetic')
        self.assertEqual(wide, 'SYNTHETIC | TENANT 11111111 | POLICY Windows Privacy Pilot (22222222) | OBS source changed | '
                               'REPO current | OP reconciled')
        # The name gives way only when even the shortest form that holds it does not fit.
        for width in range(40, 141):
            strip = context_strip(TENANT, OBJECT, facts, width, 'synthetic')
            if width >= 116:
                self.assertIn('POLICY ' + self.NAME, strip, width)

    def test_the_op_segment_shows_whenever_the_read_of_the_policy_has_an_operation(self):
        from intune_iac.workbench_screens import context_strip
        states = {'operation': {'operation_id': 'a59ec849' + 'a' * 24, 'status': 'prepared', 'journal_status': 'prepared'}}
        strip = context_strip(TENANT, OBJECT, self.facts(states=states), 140, 'synthetic')
        self.assertIn('OP prepared', strip)
        closed = {'operation': dict(states['operation'], approval_window='closed')}
        self.assertIn('OP expired', context_strip(TENANT, OBJECT, self.facts(states=closed), 140, 'synthetic'))
        # An operation the workspace was told about by a result wins over the read of the policy.
        self.assertIn('OP reconciled', context_strip(TENANT, OBJECT, self.facts(states=states, operation='reconciled'),
                                                     140, 'synthetic'))
        # No operation recorded: no segment.
        self.assertNotIn(' OP ', context_strip(TENANT, OBJECT, self.facts(states={'operation': None}), 140, 'synthetic'))


class ChangedContextReviewTests(unittest.TestCase):
    """PKG-PRES-RUN7 item 5 (run 7 frame 65): a review whose context file changed offers no digest, as an expired
    plan's review does; it says why execute refuses and what to do."""
    workspace = StateSurfaceTests.workspace
    summary = StateSurfaceTests.summary
    REVIEW = RestoreProposalWordsTests.REVIEW

    def test_no_digest_is_offered_and_the_refusal_is_explained(self):
        value = dict(self.REVIEW, repository={'cited': None, 'context_changed': True, 'context_path': '/w/context.json'})
        text = self.summary(self.workspace(4, value))
        self.assertNotIn('Review digest (execute needs it)', text)
        self.assertNotIn('d' * 64, text)
        # Run 8 item 7: the Context file row says why; the digest line refers to it.
        self.assertIn('Review digest: not offered (the context file changed, above)', text)
        from intune_iac.workbench_screens import lifecycle_next
        self.assertIn('Prepare a proposal from the recorded intent (a: actions)', lifecycle_next(4, value, 0))

    def test_an_unchanged_context_still_offers_the_digest(self):
        for repository in ({'cited': True, 'repository_intent_id': 'e' * 64, 'freshness': 'current'}, {'cited': False}):
            text = self.summary(self.workspace(4, dict(self.REVIEW, repository=repository)))
            self.assertIn('Review digest (execute needs it): ' + 'd' * 64, text)


class RefusalShapeTests(unittest.TestCase):
    """PKG-PRES-RUN7 items 8 and 10 (run 7 frames 56, 67, 71, 73, 81): every refusal has one shape, a header in words
    with the code in parentheses, then Cause, Effect and Next; a Next line names the operation it is about."""
    workspace = StateSurfaceTests.workspace
    summary = StateSurfaceTests.summary

    def refusal(self, code, message='Engine words.', effects=None, **kwargs):
        from intune_iac.workbench_screens import refusal_lines
        error = {'code': code, 'message': message}
        if effects is not None:
            error['effects'] = effects
        return refusal_lines({'status': 'error', 'error': error}, 200, **kwargs)

    def test_the_header_is_words_with_the_code_in_parentheses_then_cause_effect_next(self):
        lines = self.refusal('maintenance_replay_forbidden', effects={'dispatched': False})
        self.assertEqual(lines[0], '[REFUSED] This operation cannot be replayed (maintenance_replay_forbidden)')
        self.assertEqual([line.split(':')[0] for line in lines[1:4]], ['Cause', 'Effect', 'Next'])

    def test_a_message_that_names_something_particular_is_the_cause(self):
        lines = self.refusal('workbench_deployment_intent_not_cited', effects={'deployment_recorded': False},
                             message='This operation cites repository intent b879046017, not the intent given.')
        self.assertEqual(lines[0], '[REFUSED] The intent given is not the one the plan cites '
                                   '(workbench_deployment_intent_not_cited)')
        self.assertTrue(lines[1].startswith('Cause: This operation cites repository intent b879046017'), lines)
        self.assertEqual([line.split(':')[0] for line in lines[1:]][-2:], ['Effect', 'Next'])
        capability = self.refusal('workbench_desired_capability', message='Setting a_b: value a_b_1 is not supported.',
                                  effects={'files_written': [], 'operation_created': False})
        self.assertTrue(capability[1].startswith('Cause: Setting a_b: value a_b_1 is not supported.'), capability)
        self.assertNotIn('What it means', '\n'.join(capability))

    def test_an_unknown_code_shows_the_engines_words_as_the_cause(self):
        self.assertEqual(self.refusal('something_new'), ['[REFUSED] Something new (something_new)', 'Cause: Engine words.'])

    def test_every_explained_refusal_has_a_title(self):
        from intune_iac.workbench_screens import REFUSAL_TITLES, REFUSALS
        self.assertEqual(set(REFUSAL_TITLES), set(REFUSALS))
        for code, title in REFUSAL_TITLES.items():
            self.assertNotIn('_', title, code)

    def test_a_next_line_names_the_operation_not_the_active_one(self):
        for code in ('expired_request', 'maintenance_replay_forbidden'):
            named = '\n'.join(self.refusal(code, operation='90ef8bc2'))
            self.assertIn('operation 90ef8bc2', named, code)
            unnamed = '\n'.join(self.refusal(code))
            self.assertIn('that operation', unnamed, code)
            for text in (named, unnamed):
                self.assertNotIn('active operation', text)

    def test_the_workspace_names_the_operation_the_command_named(self):
        value = {'status': 'error', 'error': {'code': 'expired_request', 'message': 'Refused.',
                                              'effects': {'dispatched': False}}}
        workspace = self.workspace(5, value)
        workspace.known_operations = {'/w/journey 28/op': '90ef8bc2' + 'b' * 24}
        workspace.last_command = "execute '/w/journey 28/op' " + 'a' * 64
        text = self.summary(workspace)
        self.assertIn('which shows the window of operation 90ef8bc2.', text)


class KeyMExplainedTests(unittest.TestCase):
    """PKG-PRES-RUN7 item 11 (run 7 frames 09 and 29): where a screen names the key m, it says what m opens."""

    def test_the_inspector_and_diagnostics_say_what_m_opens(self):
        from intune_iac.workbench_screens import _attention_lines, diagnostics_lines
        value = {'attention': {'signals': [], 'checked': {'collection': 'clear'}, 'status': 'clear'}}
        text = ' '.join(' '.join(_attention_lines(value, 160)).split())
        self.assertIn('reviewed in the maintenance queue (m opens it)', text)
        for signals in ([], [{'area': 'freshness', 'code': 'observation_stale', 'observed': 'x', 'next_step': 'y', 'evidence': {}}]):
            lines = diagnostics_lines({'object_id': OBJECT, 'name': 'P', 'signals': signals, 'checked': {}}, 200)
            joined = ' '.join(' '.join(lines).split())
            self.assertIn('maintenance queue (m opens it)', joined)
            self.assertNotIn('queue (m)', joined)


class PlainRecoveryWordsTests(unittest.TestCase):
    """PKG-PRES-RUN7 items 12 and 14 (run 7 frame 44): the recovery for a stamp ahead says plainly what collecting does,
    and a path with spaces is quoted so it copies whole."""
    OBSERVED = {'observed_at': '2026-10-15T14:40:23Z', 'freshness': 'stale', 'freshness_reasons': ['stamped_after_now'],
                'freshness_checked_at': '2026-10-15T14:25:23Z', 'snapshot_id': 'b' * 64,
                'next_collection_replaces': 'same_service'}

    def step(self, **observed):
        from intune_iac.workbench_diagnostics import _freshness
        signals, _ = _freshness(dict(self.OBSERVED, **observed), False)
        return signals[0]['next_step']

    def test_the_step_says_a_new_collection_becomes_the_current_observation(self):
        step = self.step(ordering_service_root='/home/nsahm/work/journey 28 run 7/handoff/service')
        self.assertEqual(step, "Collect again (a: actions) from the modeled service it came from "
                               "('/home/nsahm/work/journey 28 run 7/handoff/service'): a new collection becomes the "
                               'current observation. Or correct the host clock.')
        self.assertNotIn('orders its own collections', step)

    def test_a_path_without_spaces_needs_no_quotes(self):
        self.assertIn('came from (/w/service):', self.step(ordering_service_root='/w/service'))


class ExpiredReviewOnceTests(unittest.TestCase):
    """PKG-PRES-RUN7 item 13 (run 7 frame 70): an expired review says its window and its next step once, not in the
    digest line and again in the Next line."""
    workspace = StateSurfaceTests.workspace
    summary = StateSurfaceTests.summary
    CLOSED = dict(RestoreProposalWordsTests.REVIEW, approval_window={'opens_at': 1791980697, 'closes_at': 1791980997,
                                                                       'state': 'closed'})

    def test_the_digest_line_does_not_repeat_the_window_or_the_next_step(self):
        from intune_iac.workbench_screens import lifecycle_lines
        text = ' '.join((self.summary(self.workspace(4, self.CLOSED)) + ' ' + ' '.join(lifecycle_lines(4, 160, self.CLOSED, 2e9))).split())
        self.assertIn('Review digest: not offered; execute can no longer run this plan.', text)
        self.assertEqual(text.count('Prepare a'), 1, text)
        # Run 16 N1: the Next sits above the rows, so it gives the reason itself, once; the digest line does not.
        self.assertEqual(text.count('window closed') + text.count('window has closed'), 1, text)
        self.assertIn('Approval window: closed', text)


def _said(lines):
    return ' '.join(' '.join(lines).split())


class RunEightWorkspaceTests(unittest.TestCase):
    """PKG-PRES-RUN8 (FRAME-REVIEW-run8.md): the surfaces of a workspace say each fact once, name their operation, and
    never claim an order the product does not enforce."""
    workspace = StateSurfaceTests.workspace
    summary = StateSurfaceTests.summary
    REVIEW = RestoreProposalWordsTests.REVIEW
    CITED = '42cb3c2420d44ea613e5a897225befc5c93dc10cfb557ce2bbe6bad5a004677c'
    BAND = {'area': 'freshness', 'code': 'observation_service_changed', 'observed': 'Source changed.',
            'next_step': 'Collect again.', 'evidence': {'observed_revision': 1, 'service_revision': 2}}

    def banded(self, tab, value):
        workspace = self.workspace(tab, value)
        workspace.facts = dict(workspace.facts, signals=[self.BAND])
        return workspace

    # Item 1 (frames 19 to 21): nothing orders collecting again before recording a deployment.
    def test_no_screen_claims_that_the_band_step_comes_first(self):
        from plugin_tests.test_workbench_screens import delivery_value
        delivery = delivery_value(deployment_record={'status': 'available', 'intent_id': self.CITED})
        delivery['next_action'] = 'Record the deployment: in the workspace, deployment-record /w/op %s (a lists it)' % self.CITED
        results = {'result': {'operation_id': 'a' * 32, 'status': 'succeeded_verified'}}
        repository = {'schema_version': 'workbench-repository-status/1', 'object_id': OBJECT,
                      'freshness': {'status': 'stale'}}
        for tab, value in ((5, results), (5, delivery), (8, repository)):
            text = _said(self.banded(tab, value)._summary_lines(120))
            self.assertNotIn('comes first', text)
            self.assertNotIn('band above', text)

    def test_the_screen_names_the_deployment_record_and_claims_no_order(self):
        # Delivery's Next names the record; the actions list offers it (workbench._actions offers it ahead of a
        # collect the proposal check adds). Nothing in deployment-record reads the observation, so no order is claimed.
        from plugin_tests.test_workbench_screens import delivery_value
        delivery = delivery_value(deployment_record={'status': 'available', 'intent_id': self.CITED})
        delivery['next_action'] = 'Record the deployment: in the workspace, deployment-record /w/op %s (a lists it)' % self.CITED
        text = _said(self.banded(5, delivery)._summary_lines(120))
        self.assertIn('Record the deployment', text)
        self.assertNotIn('comes first', text)

    # Item 3 (frame 20): a printed command ends its row and ends its sentence.
    def test_a_printed_command_picks_up_no_following_prose(self):
        from plugin_tests.test_workbench_screens import delivery_value
        delivery = delivery_value(deployment_record={'status': 'available', 'intent_id': self.CITED})
        delivery['next_action'] = ('Record the deployment: in the workspace, deployment-record /w/op %s (a lists it); from a '
                                   'shell, intune-iac workbench deployment-record --root /w/store --operation /w/op --intent %s'
                                   % (self.CITED, self.CITED))
        rows = self.banded(5, delivery)._summary_lines(118)
        holding = [row for row in rows if '--intent' in row or row.rstrip().endswith(self.CITED)]
        self.assertTrue(holding, rows)
        self.assertTrue(holding[-1].rstrip().endswith(self.CITED), holding[-1])

    def test_a_next_step_that_names_a_command_ends_with_the_command(self):
        from intune_iac.workbench_delivery import _next_action
        base = {'proposal': {}, 'readback': {'status': 'done'}, 'reconciliation': {'status': 'not_needed'},
                'deployment_record': {'status': 'not_yet'}, 'observed_after': {'status': 'not_yet'}}
        waiting = _next_action(dict(base, approval={'status': 'waiting', 'closes_at': 1791980997}), '/w/op', '/w/store')
        self.assertTrue(waiting.endswith('execute /w/op EXACT_REVIEW_DIGEST'), waiting)
        required = _next_action(dict(base, approval={'status': 'done'}, reconciliation={'status': 'required'}),
                                '/w/op', '/w/store')
        self.assertTrue(required.endswith('reconcile /w/op'), required)
        pending = _next_action(dict(base, approval={'status': 'done'}, reconciliation={'status': 'pending'}),
                               '/w/op', '/w/store')
        self.assertTrue(pending.endswith('reconcile /w/op'), pending)

    # Item 4 (frame 67): the workspace names the operation a deployment-record command named.
    def test_the_workspace_names_the_operation_a_deployment_record_command_named(self):
        value = {'status': 'error', 'error': {
            'code': 'workbench_deployment_intent_not_cited', 'effects': {'deployment_recorded': False},
            'message': 'This operation cites repository intent %s, not the intent given; record the deployment with the '
                       'intent it cites.' % self.CITED}}
        workspace = self.workspace(5, value)
        workspace.known_operations = {'/w/journey 28/op': '625157a3' + 'b' * 24}
        workspace.last_command = "deployment-record '/w/journey 28/op' " + 'a' * 64
        text = self.summary(workspace)
        self.assertIn('Cause: Operation 625157a3 cites repository intent', text)
        self.assertIn('Next: Record operation 625157a3 with the intent it cites', text)

    # Item 7 (frame 65): the changed context file is said once.
    def test_a_changed_context_file_is_said_once_on_the_plan_screen(self):
        value = dict(self.REVIEW, field_changes={'status': 'unchanged', 'changes': []},
                     repository={'cited': None, 'context_changed': True, 'context_path': '/w/context.json'})
        text = self.summary(self.workspace(4, value))
        self.assertEqual(text.count('maintenance_source_changed'), 1, text)
        self.assertEqual(text.count('execute refuses'), 1, text)
        self.assertIn('Review digest: not offered (the context file changed, above)', text)
        from intune_iac.workbench_screens import lifecycle_next
        self.assertEqual(lifecycle_next(4, value, 0), 'Prepare a proposal from the recorded intent (a: actions)')

    # Item 9 (frames 74 to 82): the Operation row on the surfaces says which operation the strip shows.
    def test_the_operation_row_names_the_strip_operation_on_the_repository_surface(self):
        newest, shown = 'e112edba' + 'a' * 24, '9aac2657' + 'b' * 24
        states = dict(StateRenderingTests.STATES, operation={'operation_id': newest, 'status': 'prepared',
                                                             'journal_status': 'prepared', 'approval_window': 'open'})
        repository = {'schema_version': 'workbench-repository-status/1', 'object_id': OBJECT,
                      'freshness': {'status': 'current'}}
        workspace = self.workspace(8, repository)
        workspace.facts = dict(workspace.facts, states=states, operation='expired', operation_id=shown)
        text = self.summary(workspace)
        self.assertIn('The strip shows operation 9aac2657 (expired), not the newest.', text)
        workspace.facts = dict(workspace.facts, operation_id=newest, operation='prepared')
        self.assertNotIn('The strip shows', self.summary(workspace))

    def test_the_inspector_names_the_strip_operation_too(self):
        from intune_iac.workbench_screens import inspector_lines
        newest, shown = 'e112edba' + 'a' * 24, '9aac2657' + 'b' * 24
        states = dict(StateRenderingTests.STATES, operation={'operation_id': newest, 'status': 'prepared',
                                                             'journal_status': 'prepared'})
        value = {'object_id': OBJECT, 'name': 'P', 'states': states}
        text = _said(inspector_lines(value, 140, strip_operation={'operation_id': shown, 'state': 'expired'}))
        self.assertIn('The strip shows operation 9aac2657 (expired), not the newest.', text)

    # Item 11 (frame 69): the workspace words a refused restore as a restore.
    def test_a_refused_restore_is_worded_as_a_restore_by_the_workspace(self):
        value = {'status': 'error', 'error': {'code': 'maintenance_source_changed', 'message': 'Refused.',
                                              'effects': {'files_written': [], 'operation_created': False}}}
        workspace = self.workspace(4, value)
        workspace.last_command = 'restore-propose /w/op /w/restore'
        text = self.summary(workspace)
        self.assertIn('a restore cannot be derived from it', text)
        self.assertNotIn('review no longer describes what would run', text)

    # Item 12 (frames 38, 57): a reconcile result does not promise a deployment record.
    def test_a_reconcile_result_next_does_not_promise_a_deployment_record(self):
        text = _said(self.workspace(5, dict(ReconcileReadbackWordsTests.RESULT))._summary_lines(160))
        self.assertIn('Next: v shows every delivery stage', text)
        self.assertNotIn('deployment record', text)

    # Item 15 (frames 11 to 16, 75, 77): the changed file once, one Next, one id length.
    def repository_status(self, state='stale'):
        return {'schema_version': 'workbench-repository-status/1', 'object_id': OBJECT, 'repository_intent_id': 'e' * 64,
                'scope': {'repository': '/w/journey 28/repository', 'stack': 'orgs/reference/dev',
                          'component': 'intune-reference'},
                'effective_pointer': '/vars/policies/p_x', 'source_revision': 'b' * 40,
                'consumer': {'status': 'verified'}, 'next_action': 'The repository changed. Review it, then refresh.',
                'freshness': {'status': state, 'sources': {'changed': ['stacks/orgs/reference/dev.yaml'], 'added': [],
                                                          'removed': []}, 'consumer': {'status': 'verified'}}}

    def test_the_changed_file_is_listed_once_on_the_repository_surface(self):
        text = self.summary(self.workspace(8, self.repository_status()))
        self.assertEqual(text.count('stacks/orgs/reference/dev.yaml'), 1, text)
        self.assertIn('SOURCES changed stacks/orgs/reference/dev.yaml', text)
        self.assertIn('the repository changed since its recorded intent', text)

    def test_the_repository_surface_gives_one_next_statement(self):
        # The Lifecycle line's step comes from the policy's own state (it says when a proposal is blocked), so it stays
        # and the status's own Next (still in the typed details, e) is not stacked beside it.
        text = _said(self.workspace(8, self.repository_status())._summary_lines(118))
        self.assertEqual(text.count('Next:'), 1, text)
        self.assertIn('Lifecycle: 9 Repository (here) > 5 Plan > 6 Execution > Delivery (v opens it). Next: Refresh the '
                      'repository intent first (a: actions)', text)
        self.assertNotIn('The repository changed. Review it, then refresh.', text)
        current = _said(self.workspace(8, self.repository_status('current'))._summary_lines(118))
        self.assertEqual(current.count('Next:'), 1, current)
        self.assertIn('Next: Prepare a proposal from the recorded intent (a: actions)', current)

    def test_the_repository_intent_has_the_length_the_state_row_gives_it(self):
        text = self.summary(self.workspace(8, self.repository_status()))
        self.assertIn('Intent e9274102 from', text)
        self.assertIn('Intent eeeeeeee Consumer', text)

    def test_a_plan_names_the_cited_intent_in_the_length_its_state_row_uses(self):
        value = dict(self.REVIEW, field_changes={'status': 'unchanged', 'changes': []},
                     repository={'cited': True, 'repository_intent_id': 'e927410221924400' + '0' * 48, 'freshness': 'current'})
        text = self.summary(self.workspace(4, value))
        self.assertIn('Intent e9274102 from', text)
        self.assertIn('Cited repository intent: e9274102 (current)', text)

    def test_an_empty_estate_does_not_claim_an_evidence_class_in_its_footer(self):
        workspace = self.workspace(0, {'objects': [], 'evidence_class': 'synthetic', 'status': 'empty'})
        self.assertEqual(workspace._scope({}), 'evidence class not stated')
        observed = self.workspace(0, {'objects': [{'object_id': OBJECT}], 'evidence_class': 'synthetic'})
        observed.mode_class = 'synthetic'
        self.assertEqual(observed._scope({}), 'synthetic')
