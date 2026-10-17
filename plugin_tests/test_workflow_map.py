"""The workflow map, first slice (requirement 17 UX-VIS, PKG-UXVIS-5): one selected policy's change path.

Item 1 is the projection (`intune_iac.workflow_projection`, schema workflow-map/1): fixed stages, each state read from a
named record and field, a recorded reason, the surface Enter opens and the one step the existing screens give. The
projection is pure, so most cases here pass it hand-built reads that change one recorded field at a time; the cases that
need a real operation (prepared, closed window, unknown outcome, reconciled, recorded, observed) run the real store, the
modeled service and the maintenance engine over temporary directories.
"""
import copy
import io
import re
import unittest
from unittest import mock

from plugin_tests import test_workbench_repository as repository_tests

OBJECT, TENANT = repository_tests.OBJECT, repository_tests.TENANT
IDS = ['observe', 'adopt', 'intent', 'propose', 'review', 'approve_execute', 'readback', 'reconcile', 'record',
       'observed_after', 'maintain']
STATES = {'done', 'current', 'waiting', 'blocked', 'refused', 'unknown', 'not_recorded', 'not_applicable'}
OPERATION = '4d972e93a1b2c3d4e5f60718293a4b5c'


def baseline():
    """A policy with a fresh observation and a current repository intent, and nothing else recorded."""
    return {
        'object_id': OBJECT, 'tenant_id': TENANT, 'name': 'Windows Privacy Pilot', 'evidence_class': 'synthetic',
        'states': {
            'observation': {'evidence_class': 'synthetic', 'run_id': 4, 'observed_at': '2026-10-14T19:55:52.390326Z',
                            'coverage': 'complete', 'freshness': 'fresh', 'freshness_reasons': [], 'eligibility': None},
            'intent': {'status': 'current', 'artifact_id': 'e927410221924400' + '0' * 48,
                       'scope': {'stack': 'orgs/reference/dev', 'component': 'intune-reference'},
                       'source_revision': 'b' * 40, 'recorded_at': '2026-10-14T19:50:01.000001Z', 'reason': None},
            'operation': None},
        'attention': {'status': 'clear', 'signals': [], 'checked': {}},
        'eligibility': None, 'adoptions': [], 'review': None, 'delivery': None, 'identity_prefixes': {}, 'now': 0.0}


def stage_row(name, status, **extra):
    return dict({'stage': name, 'status': status}, **extra)


def prepared_delivery(**approval):
    """What workbench_delivery.delivery returns for a prepared operation inside its window."""
    return {'schema_version': 'workbench-delivery/1', 'operation_id': OPERATION, 'journal_status': 'prepared',
            'next_action': 'Review the change (5); the digest is the one on the review, never filled in for you. '
                           'Approve before 2026-10-14 20:00:00 UTC with:\n  execute /w/operation EXACT_REVIEW_DIGEST',
            'history': {'events': [{'sequence': 0, 'kind': 'prepared', 'fields': {}}]},
            'stages': [stage_row('proposal', 'done', recorded_at='2026-10-14T19:55:00Z', repository_intent_id='e9274102',
                                 intent_freshness='current'),
                       stage_row('review', 'done', changes=[OBJECT + ':description_changed'], no_configuration_change=False),
                       stage_row('approval', 'waiting', opens_at=1_792_000_000, closes_at=1_792_000_300, **approval),
                       stage_row('execution', 'not_started'), stage_row('readback', 'not_started'),
                       stage_row('reconciliation', 'not_needed'), stage_row('deployment_record', 'not_yet'),
                       stage_row('observed_after', 'not_yet')]}


def prepared_review(state='open', **extra):
    return dict({'operation_id': OPERATION, 'operation_root': '/w/operation', 'status': 'prepared',
                 'approval_window': {'opens_at': 1_792_000_000, 'closes_at': 1_792_000_300, 'state': state},
                 'expires_at': 1_792_000_300, 'repository': {'cited': True, 'freshness': 'current'},
                 'no_configuration_change': False, 'changes': [OBJECT + ':description_changed']}, **extra)


def with_operation(read, delivery=None, review=None, journal='prepared', window='open'):
    read = copy.deepcopy(read)
    read['states']['operation'] = {'operation_id': OPERATION, 'operation_root': '/w/operation', 'status': journal,
                                   'journal_status': journal, 'classification': None,
                                   'recorded_at': '2026-10-14T19:55:00.5Z', **({'approval_window': window} if journal == 'prepared' else {})}
    read['delivery'] = delivery if delivery is not None else prepared_delivery()
    read['review'] = review if review is not None else prepared_review(window)
    return read


def project(read):
    from intune_iac.workflow_projection import project as run
    return run(read)


def by_id(flow):
    return {stage['id']: stage for stage in flow['stages']}


def states_of(flow):
    return {stage['id']: stage['state'] for stage in flow['stages']}


def basis_of(flow):
    """What each stage's state rests on: the state, the field it was read from and the recorded reason."""
    return {stage['id']: (stage['state'], stage['basis'], stage['reason']) for stage in flow['stages']}


def differing(before, after):
    return sorted(name for name in IDS if basis_of(before)[name] != basis_of(after)[name])


class StageListTests(unittest.TestCase):
    def test_the_stages_are_the_fixed_ids_in_order_and_each_carries_the_five_fields(self):
        flow = project(baseline())
        self.assertEqual(flow['schema_version'], 'workflow-map/1')
        self.assertEqual([stage['id'] for stage in flow['stages']], IDS)
        for stage in flow['stages']:
            self.assertIn(stage['state'], STATES, stage)
            for key in ('basis', 'reason', 'opens', 'continuation'):
                self.assertIn(key, stage)
            self.assertIsInstance(stage['basis'], str)
            self.assertTrue(stage['basis'], stage)
        self.assertEqual(by_id(flow)['reconcile']['branch_of'], 'readback')
        self.assertEqual([stage['id'] for stage in flow['stages'] if stage['branch_of']], ['reconcile'])
        self.assertRegex(flow['revision'], r'^[0-9a-f]{64}$')
        self.assertEqual((flow['object_id'], flow['evidence_class'], flow['name']), (OBJECT, 'synthetic', 'Windows Privacy Pilot'))
        self.assertIs(flow['read_only'], True)
        self.assertIs(flow['execution_authorized'], False)
        self.assertIs(flow['cloud_authority'], False)

    def test_the_same_inputs_give_the_same_revision_and_any_changed_stage_gives_a_new_one(self):
        read = baseline()
        self.assertEqual(project(read)['revision'], project(copy.deepcopy(read))['revision'])
        # The clock reading a later read stamps on the same records is not part of what the stages rest on.
        later = copy.deepcopy(read)
        later['states']['observation']['freshness_checked_at'] = '2026-10-15T00:00:00Z'
        later['now'] = 99.0
        self.assertEqual(project(read)['revision'], project(later)['revision'])
        stale = copy.deepcopy(read)
        stale['states']['observation'].update(freshness='stale', freshness_reasons=['older_than_window'])
        self.assertNotEqual(project(read)['revision'], project(stale)['revision'])

    def test_an_unnamed_policy_is_refused(self):
        from intune_iac.io import AppError
        for bad in ({}, {'object_id': ''}, {'object_id': 3}, None):
            with self.assertRaises(AppError) as raised:
                project(bad)
            self.assertEqual(raised.exception.code, 'workflow_projection_invalid')

    def test_enter_opens_a_tab_number_or_delivery_and_nothing_for_an_operation_that_is_not_recorded(self):
        stages = by_id(project(baseline()))
        self.assertEqual([stages[name]['opens'] for name in ('observe', 'adopt', 'intent', 'propose', 'review', 'maintain')],
                         ['2', '3', '9', '5', '5', '7'])
        for name in ('approve_execute', 'readback', 'reconcile', 'record', 'observed_after'):
            self.assertIsNone(stages[name]['opens'], name)
        stages = by_id(project(with_operation(baseline())))
        for name in ('approve_execute', 'readback', 'reconcile', 'record', 'observed_after'):
            self.assertEqual(stages[name]['opens'], 'v', name)


class FreshWorkspaceTests(unittest.TestCase):
    def test_only_an_observation_leaves_every_later_stage_not_recorded_with_no_invented_step(self):
        read = baseline()
        read['states']['intent'] = {'status': 'none'}
        flow = project(read)
        states = states_of(flow)
        self.assertEqual(states['observe'], 'done')
        self.assertEqual([states[name] for name in IDS[1:]], ['not_recorded'] * 10, states)
        self.assertEqual([stage['continuation'] for stage in flow['stages']], [None] * 11)
        # "Not started" is never the word: an absent record is not recorded.
        self.assertNotIn('not_started', {stage['state'] for stage in flow['stages']})
        self.assertEqual(flow['position'], 'observe')
        self.assertIsNone(flow['operation'])

    def test_a_current_intent_with_no_operation_offers_the_repository_surfaces_step_at_propose_only(self):
        from intune_iac.workbench_screens import lifecycle_next
        flow = project(baseline())
        stages = by_id(flow)
        self.assertEqual(stages['propose']['state'], 'not_recorded')
        self.assertEqual(stages['propose']['continuation'],
                         lifecycle_next(8, {'freshness': {'status': 'current'}}, 0.0, None))
        self.assertEqual([stage['id'] for stage in flow['stages'] if stage['continuation']], ['propose'])
        self.assertEqual(flow['position'], 'intent')

    def test_a_blocked_proposal_check_is_said_the_way_the_repository_surface_says_it(self):
        from intune_iac.workbench_screens import lifecycle_next
        read = baseline()
        read['eligibility'] = {'code': 'maintenance_observation_stale', 'reason': 'not_fresh'}
        stages = by_id(project(read))
        self.assertEqual(stages['propose']['continuation'],
                         lifecycle_next(8, {'freshness': {'status': 'current'}}, 0.0, read['eligibility']))
        self.assertIn('a proposal is blocked now (not_fresh)', stages['propose']['continuation'])

    def test_an_adoption_record_is_the_adopt_stage_and_moves_the_position_when_nothing_later_is_recorded(self):
        read = baseline()
        read['states']['intent'] = {'status': 'none'}
        read['adoptions'] = [{'artifact_id': 'ab' * 32, 'sequence': 3, 'recorded_at': '2026-10-14T19:40:00Z'}]
        flow = project(read)
        self.assertEqual(by_id(flow)['adopt']['state'], 'done')
        self.assertEqual(by_id(flow)['adopt']['basis'], 'adoption record abababab')
        self.assertEqual(flow['position'], 'adopt')


class OneRecordedFieldAtATimeTests(unittest.TestCase):
    """Change one recorded field; only the stage that reads it changes, and the position only when it depends on it."""

    def changed(self, mutate, base=None):
        before = project(baseline() if base is None else base)
        read = copy.deepcopy(baseline() if base is None else base)
        mutate(read)
        after = project(read)
        return before, after

    def test_the_observation_freshness_changes_only_the_observe_stage(self):
        def stale(read):
            read['states']['observation'].update(freshness='stale', freshness_reasons=['older_than_window'])
        before, after = self.changed(stale)
        self.assertEqual(differing(before, after), ['observe'])
        self.assertEqual(basis_of(after)['observe'], ('blocked', 'states.observation.freshness', 'older_than_window'))
        self.assertEqual(after['position'], before['position'])

    def test_a_source_that_moved_on_blocks_a_fresh_observation_with_its_recorded_reason(self):
        def moved(read):
            read['states']['observation']['eligibility'] = {'code': 'maintenance_observation_stale', 'reason': 'service_changed'}
        before, after = self.changed(moved)
        self.assertEqual(differing(before, after), ['observe'])
        self.assertEqual(basis_of(after)['observe'],
                         ('blocked', 'states.observation.eligibility.reason', 'service_changed'))

    def test_an_age_that_cannot_be_established_is_unknown_not_stale(self):
        for reason in ('clock_moved_backward', 'clock_floor_invalid', 'stamped_after_now'):
            def unknown(read, reason=reason):
                read['states']['observation'].update(freshness='stale', freshness_reasons=['older_than_window', reason])
            before, after = self.changed(unknown)
            self.assertEqual(differing(before, after), ['observe'], reason)
            self.assertEqual(basis_of(after)['observe'][0], 'unknown', reason)
            self.assertEqual(basis_of(after)['observe'][2], reason)

    def test_the_intent_status_changes_only_the_intent_stage(self):
        cases = {'changed': ('blocked', 'repository_stale'), 'consumer_changed': ('blocked', 'repository_consumer_mismatch'),
                 'unreadable': ('unknown', 'repository_unavailable'), 'not_checked': ('unknown', None)}
        for status, (state, reason) in cases.items():
            def moved(read, status=status):
                read['states']['intent']['status'] = status
            before, after = self.changed(moved)
            self.assertEqual(differing(before, after), ['intent'], status)
            self.assertEqual(basis_of(after)['intent'], (state, 'states.intent.status', reason), status)
            self.assertEqual(after['position'], 'intent', status)

    def test_an_adoption_record_changes_only_the_adopt_stage(self):
        def adopted(read):
            read['adoptions'] = [{'artifact_id': 'cd' * 32, 'sequence': 1, 'recorded_at': '2026-10-14T19:40:00Z'}]
        before, after = self.changed(adopted)
        self.assertEqual(differing(before, after), ['adopt'])
        self.assertEqual(after['position'], before['position'])

    def test_a_stale_observation_and_a_changed_intent_are_two_stages_with_two_states(self):
        def observation_stale(read):
            read['states']['observation'].update(freshness='stale', freshness_reasons=['older_than_window'])

        def intent_changed(read):
            read['states']['intent']['status'] = 'changed'
        _, stale = self.changed(observation_stale)
        _, changed = self.changed(intent_changed)
        self.assertEqual((states_of(stale)['observe'], states_of(stale)['intent']), ('blocked', 'done'))
        self.assertEqual((states_of(changed)['observe'], states_of(changed)['intent']), ('done', 'blocked'))
        both = copy.deepcopy(baseline())
        observation_stale(both); intent_changed(both)
        flow = project(both)
        self.assertEqual((states_of(flow)['observe'], states_of(flow)['intent']), ('blocked', 'blocked'))
        self.assertNotEqual(basis_of(flow)['observe'], basis_of(flow)['intent'])

    def test_a_changed_intent_is_given_the_refresh_step_the_repository_surface_gives(self):
        from intune_iac.workbench_screens import lifecycle_next
        def changed(read):
            read['states']['intent']['status'] = 'changed'
        _, flow = self.changed(changed)
        self.assertEqual(by_id(flow)['intent']['continuation'],
                         lifecycle_next(8, {'freshness': {'status': 'stale'}}, 0.0, None))
        self.assertIsNone(by_id(flow)['propose']['continuation'])

    def test_a_stale_observation_carries_the_step_diagnostics_recorded_and_no_other(self):
        read = baseline()
        read['states']['observation'].update(freshness='stale', freshness_reasons=['older_than_window'])
        read['attention'] = {'status': 'attention', 'checked': {}, 'signals': [
            {'area': 'freshness', 'code': 'observation_stale', 'observed': 'x', 'evidence': {},
             'next_step': 'Collect again (a: actions) before preparing or judging a change.'}]}
        stages = by_id(project(read))
        self.assertEqual(stages['observe']['continuation'], 'Collect again (a: actions) before preparing or judging a change.')
        self.assertIsNone(stages['intent']['continuation'])

    def test_the_observe_stage_says_whether_the_proposal_check_was_made_and_claims_nothing_without_it(self):
        from intune_iac.workbench_screens import workflow_fact_words
        for checked, words in ((True, 'made against the service'), (False, 'not made: no service root')):
            read = baseline()
            read['service_checked'] = checked
            stage = by_id(project(read))['observe']
            self.assertEqual(stage['state'], 'done', checked)                 # the state is the age's either way
            self.assertEqual(stage['facts']['proposal_check'], words)
            self.assertIn('proposal check ' + words, workflow_fact_words(stage))
        self.assertNotIn('proposal_check', by_id(project(baseline()))['observe']['facts'])      # not said, not claimed

    def test_a_recorded_operation_changes_the_operation_stages_and_the_position(self):
        before = project(baseline())
        after = project(with_operation(baseline()))
        moved = sorted(name for name in IDS if states_of(before)[name] != states_of(after)[name])
        self.assertEqual(moved, ['approve_execute', 'propose', 'reconcile', 'review'])
        self.assertEqual(states_of(after), {
            'observe': 'done', 'adopt': 'not_recorded', 'intent': 'done', 'propose': 'done', 'review': 'done',
            'approve_execute': 'waiting', 'readback': 'not_recorded', 'reconcile': 'not_applicable',
            'record': 'not_recorded', 'observed_after': 'not_recorded', 'maintain': 'not_recorded'})
        self.assertEqual(after['position'], 'approve_execute')
        # The observation and the intent did not move.
        self.assertEqual(basis_of(before)['observe'], basis_of(after)['observe'])
        self.assertEqual(basis_of(before)['intent'], basis_of(after)['intent'])


class ApprovalWindowTests(unittest.TestCase):
    def test_an_open_window_waits_for_the_digest_with_the_plan_reviews_own_step(self):
        from intune_iac.workbench_screens import lifecycle_next
        read = with_operation(baseline())
        stage = by_id(project(read))['approve_execute']
        self.assertEqual(stage['state'], 'waiting')
        self.assertEqual(stage['continuation'], lifecycle_next(4, read['review'], 0.0, None))
        self.assertIn('approve and run it with the review digest', stage['continuation'])
        self.assertEqual(stage['facts']['closes_at'], 1_792_000_300)
        self.assertIn('delivery stage approval', stage['basis'])
        self.assertTrue(stage['basis'].startswith('operation 4d972e93 '))

    def test_a_closed_window_is_not_runnable_shows_when_it_closed_and_gives_lifecycle_nexts_step(self):
        from intune_iac.workbench_screens import _readable_epoch, lifecycle_next
        delivery = prepared_delivery()
        delivery['stages'][2] = stage_row('approval', 'expired', opens_at=1_792_000_000, closes_at=1_792_000_300)
        read = with_operation(baseline(), delivery=delivery, review=prepared_review('closed'), window='closed')
        flow = project(read)
        stage = by_id(flow)['approve_execute']
        self.assertEqual((stage['state'], stage['reason']), ('blocked', 'closed'))
        self.assertEqual(stage['facts']['closed_at'], 1_792_000_300)
        self.assertNotIn('closes_at', stage['facts'])
        self.assertEqual(stage['continuation'], lifecycle_next(4, read['review'], 0.0, None))
        self.assertIn('this plan cannot run because its approval window closed at ' + _readable_epoch(1_792_000_300),
                      stage['continuation'])
        self.assertNotIn('approve and run it', stage['continuation'])
        self.assertEqual(flow['position'], 'approve_execute')

    def test_a_closed_window_with_a_recorded_refusal_is_refused_with_the_recorded_code(self):
        delivery = prepared_delivery()
        delivery['stages'][2] = stage_row('approval', 'expired', opens_at=1_792_000_000, closes_at=1_792_000_300)
        delivery['history']['events'].append({'sequence': 1, 'kind': 'approval_refused', 'fields': {'code': 'expired_request'}})
        read = with_operation(baseline(), delivery=delivery, review=prepared_review('closed'), window='closed')
        stage = by_id(project(read))['approve_execute']
        self.assertEqual((stage['state'], stage['reason']), ('refused', 'expired_request'))
        self.assertIn('approval_refused', stage['basis'])

    def test_a_rejected_operation_is_refused(self):
        delivery = prepared_delivery()
        delivery['journal_status'] = 'rejected'
        delivery['stages'][2] = stage_row('approval', 'rejected', opens_at=1, closes_at=2)
        read = with_operation(baseline(), delivery=delivery, journal='rejected')
        read['review'] = prepared_review('open', status='rejected')
        stage = by_id(project(read))['approve_execute']
        self.assertEqual((stage['state'], stage['reason']), ('refused', 'rejected'))

    def test_clock_holds_on_the_window_are_blocked_or_unknown_with_their_codes(self):
        cases = {'clock_uncertain': ('blocked', 'clock_moved_backward'), 'clock_unreadable': ('unknown', 'clock_unreadable'),
                 'not_open': ('blocked', 'not_open')}
        for status, (state, reason) in cases.items():
            delivery = prepared_delivery()
            delivery['stages'][2] = stage_row('approval', status, opens_at=1_792_000_000, closes_at=1_792_000_300)
            stage = by_id(project(with_operation(baseline(), delivery=delivery)))['approve_execute']
            self.assertEqual((stage['state'], stage['reason']), (state, reason), status)

    def test_a_context_file_that_changed_since_the_plan_blocks_the_approval(self):
        delivery = prepared_delivery()
        delivery['stages'][0]['context_changed'] = True
        stage = by_id(project(with_operation(baseline(), delivery=delivery)))['approve_execute']
        self.assertEqual((stage['state'], stage['reason']), ('blocked', 'context_changed'))


NO_RECORD_STEP = ('This operation cannot become a deployment record because its own readback was never verified; '
                  'collect to observe the policy.')


def executed_delivery(outcome, **extra):
    """Delivery for an operation that was approved and dispatched: outcome is 'verified', 'unknown' or 'reconciled'."""
    delivery = prepared_delivery()
    delivery['stages'][2] = stage_row('approval', 'done', opens_at=1_792_000_000, closes_at=1_792_000_300,
                                      approval_digest='ab' * 32)
    delivery['history']['events'] += [{'sequence': 1, 'kind': 'dispatch_started', 'fields': {}}]
    if outcome == 'verified':
        delivery['journal_status'] = 'succeeded_verified'
        delivery['stages'][3] = stage_row('execution', 'done', engine_status='succeeded_verified', service_status=200)
        delivery['stages'][4] = stage_row('readback', 'done', classification='desired_state_observed', second_plan='no_change')
        delivery['stages'][6] = stage_row('deployment_record', 'available', intent_id='e9274102')
        delivery['next_action'] = 'Record the deployment (a lists it), then collect to observe the policy after the change.'
    else:
        delivery['journal_status'] = 'outcome_unknown' if outcome == 'unknown' else 'reconciled'
        delivery['stages'][3] = stage_row('execution', 'unknown', engine_status='succeeded_verified',
                                          error_code='maintenance_service_incomplete')
        delivery['stages'][4] = stage_row('readback', 'not_recorded')
        delivery['stages'][5] = (stage_row('reconciliation', 'required') if outcome == 'unknown' else
                                 stage_row('reconciliation', 'done', classification='desired_state_observed',
                                           previous_status='outcome_unknown', count=1))
        delivery['stages'][6] = (stage_row('deployment_record', 'not_yet') if outcome == 'unknown' else
                                 stage_row('deployment_record', 'not_available', reason='no_verified_readback'))
        delivery['next_action'] = (
            'The outcome is unknown, and execution is never replayed. Reconcile before any retry with:\n  reconcile /w/operation'
            if outcome == 'unknown' else NO_RECORD_STEP)
    for stage in delivery['stages']:
        stage.update(extra.get(stage['stage'], {}))
    return delivery


class UnknownOutcomeTests(unittest.TestCase):
    def flow(self):
        read = with_operation(baseline(), delivery=executed_delivery('unknown'), journal='outcome_unknown',
                              review=prepared_review('open', status='outcome_unknown'))
        return project(read)

    def test_readback_is_unknown_never_done_and_the_reconcile_branch_is_present(self):
        stages = by_id(self.flow())
        self.assertEqual(stages['readback']['state'], 'unknown')
        self.assertEqual(stages['readback']['reason'], 'maintenance_service_incomplete')
        self.assertEqual(stages['approve_execute']['state'], 'unknown')
        self.assertEqual(stages['reconcile']['state'], 'current')
        self.assertEqual(stages['reconcile']['branch_of'], 'readback')
        self.assertNotIn('done', {stages[name]['state'] for name in ('approve_execute', 'readback', 'record', 'observed_after',
                                                                      'maintain')})

    def test_the_step_is_the_one_the_screens_give_for_an_unknown_outcome(self):
        from intune_iac.workbench_screens import RECONCILE_NEXT, lifecycle_next
        flow = self.flow()
        stages = by_id(flow)
        for name in ('readback', 'reconcile', 'approve_execute'):
            self.assertEqual(stages[name]['continuation'], RECONCILE_NEXT, name)
        self.assertEqual(lifecycle_next(5, {'status': 'outcome_unknown'}, 0.0), RECONCILE_NEXT)
        self.assertEqual(flow['position'], 'reconcile')
        self.assertIsNone(stages['record']['continuation'])

    def test_a_reconciled_outcome_stays_unknown_for_the_execution_and_done_for_the_branch(self):
        read = with_operation(baseline(), delivery=executed_delivery('reconciled'), journal='reconciled',
                              review=prepared_review('open', status='reconciled'))
        stages = by_id(project(read))
        self.assertEqual((stages['readback']['state'], stages['approve_execute']['state']), ('unknown', 'unknown'))
        self.assertEqual((stages['reconcile']['state'], stages['reconcile']['reason']), ('done', 'desired_state_observed'))
        self.assertEqual((stages['record']['state'], stages['record']['reason']), ('not_applicable', 'no_verified_readback'))
        self.assertEqual(stages['maintain']['state'], 'not_recorded')
        # The one step left is Delivery's own, said about the record that cannot be made: collect to observe the policy.
        self.assertEqual({name: stage['continuation'] for name, stage in stages.items() if stage['continuation']},
                         {'record': NO_RECORD_STEP})

    def test_a_diverged_reconciliation_is_blocked(self):
        delivery = executed_delivery('reconciled', reconciliation={'classification': 'diverged'})
        read = with_operation(baseline(), delivery=delivery, journal='reconciled',
                              review=prepared_review('open', status='reconciled'))
        stage = by_id(project(read))['reconcile']
        self.assertEqual((stage['state'], stage['reason']), ('blocked', 'diverged'))

    def test_the_branch_is_not_applicable_when_the_outcome_was_known_and_not_recorded_with_no_operation(self):
        self.assertEqual(by_id(project(with_operation(baseline())))['reconcile']['state'], 'not_applicable')
        self.assertEqual(by_id(project(baseline()))['reconcile']['state'], 'not_recorded')

    def test_a_pending_readback_waits_for_the_service(self):
        delivery = executed_delivery('verified')
        delivery['stages'][4] = stage_row('readback', 'pending', classification='matches_precondition',
                                          visibility_pending=True)
        delivery['stages'][3] = stage_row('execution', 'done', engine_status='succeeded_verified', service_status=200)
        stage = by_id(project(with_operation(baseline(), delivery=delivery, journal='outcome_unknown')))['readback']
        self.assertEqual((stage['state'], stage['reason']), ('waiting', 'visibility_pending'))


class DeliveredChangeTests(unittest.TestCase):
    def verified(self, **extra):
        return with_operation(baseline(), delivery=executed_delivery('verified', **extra), journal='succeeded_verified',
                              review=prepared_review('open', status='succeeded_verified'))

    def test_a_verified_change_offers_the_deployment_record_with_deliverys_own_step(self):
        flow = project(self.verified())
        stages = by_id(flow)
        self.assertEqual([stages[name]['state'] for name in ('approve_execute', 'readback', 'reconcile', 'record')],
                         ['done', 'done', 'not_applicable', 'current'])
        self.assertEqual(stages['readback']['reason'], 'desired_state_observed')
        self.assertEqual(stages['record']['continuation'], executed_delivery('verified')['next_action'])
        self.assertEqual(flow['position'], 'record')
        self.assertIsNone(stages['approve_execute']['continuation'])

    def test_a_recorded_and_observed_change_reaches_maintenance_and_the_position_is_there(self):
        delivery = executed_delivery('verified')
        delivery['stages'][6] = stage_row('deployment_record', 'done', intent_id='e9274102', recorded_at='2026-10-14T20:00:00Z',
                                          baseline_admissible=True)
        delivery['stages'][7] = stage_row('observed_after', 'matches_desired', observed_at='2026-10-14T20:01:00Z',
                                          service_revision=2, before_revision=1, observation_freshness='fresh',
                                          observation_freshness_reasons=[])
        delivery['next_action'] = 'Nothing pending: the change is recorded and observed as desired.'
        flow = project(with_operation(baseline(), delivery=delivery, journal='succeeded_verified',
                                      review=prepared_review('open', status='succeeded_verified')))
        stages = by_id(flow)
        self.assertEqual([stages[name]['state'] for name in ('record', 'observed_after', 'maintain')],
                         ['done', 'done', 'current'])
        self.assertEqual(flow['position'], 'maintain')

    def test_what_the_recorded_deployment_waits_for_is_the_observation_after_the_change(self):
        delivery = executed_delivery('verified')
        delivery['stages'][6] = stage_row('deployment_record', 'done', intent_id='e9274102', baseline_admissible=True)
        delivery['next_action'] = 'Collect to observe the policy after the change.'
        flow = project(with_operation(baseline(), delivery=delivery, journal='succeeded_verified',
                                      review=prepared_review('open', status='succeeded_verified')))
        stages = by_id(flow)
        self.assertEqual((stages['record']['state'], stages['observed_after']['state']), ('done', 'not_recorded'))
        self.assertEqual(stages['observed_after']['continuation'], 'Collect to observe the policy after the change.')
        self.assertEqual(stages['maintain']['state'], 'not_recorded')
        self.assertEqual(flow['position'], 'record')

    def test_an_observation_that_differs_is_blocked_and_one_that_reads_stale_is_unknown(self):
        delivery = executed_delivery('verified')
        delivery['stages'][6] = stage_row('deployment_record', 'done', intent_id='e9274102')
        delivery['stages'][7] = stage_row('observed_after', 'differs', service_revision=2)
        flow = project(with_operation(baseline(), delivery=delivery, journal='succeeded_verified'))
        self.assertEqual((by_id(flow)['observed_after']['state'], by_id(flow)['observed_after']['reason']), ('blocked', 'differs'))
        delivery['stages'][7] = stage_row('observed_after', 'matches_desired', observation_freshness='stale',
                                          observation_freshness_reasons=['older_than_window'])
        flow = project(with_operation(baseline(), delivery=delivery, journal='succeeded_verified'))
        self.assertEqual((by_id(flow)['observed_after']['state'], by_id(flow)['observed_after']['reason']),
                         ('unknown', 'older_than_window'))

    def test_a_plan_with_no_change_has_no_observation_after_and_no_configuration_change_as_its_reason(self):
        delivery = executed_delivery('verified')
        delivery['stages'][1]['no_configuration_change'] = True
        delivery['stages'][1]['changes'] = []
        delivery['stages'][6] = stage_row('deployment_record', 'not_applicable', reason='no_repository_intent_cited')
        delivery['stages'][7] = stage_row('observed_after', 'not_applicable', reason='no_configuration_change')
        flow = project(with_operation(baseline(), delivery=delivery, journal='succeeded_verified'))
        stages = by_id(flow)
        self.assertEqual((stages['review']['state'], stages['review']['reason']), ('done', 'no_configuration_change'))
        self.assertEqual((stages['observed_after']['state'], stages['observed_after']['reason']),
                         ('not_applicable', 'no_configuration_change'))
        self.assertEqual(stages['maintain']['state'], 'current')

    def test_maintenance_names_what_diagnostics_says_needs_attention(self):
        read = self.verified()
        read['delivery']['stages'][6] = stage_row('deployment_record', 'done', intent_id='e9274102')
        read['delivery']['stages'][7] = stage_row('observed_after', 'matches_desired', observation_freshness='fresh')
        read['attention'] = {'status': 'attention', 'checked': {}, 'signals': [
            {'area': 'repository', 'code': 'repository_stale', 'observed': 'x', 'evidence': {},
             'next_step': 'Review the difference on the Repository surface (9).'}]}
        stage = by_id(project(read))['maintain']
        self.assertEqual((stage['state'], stage['reason']), ('blocked', 'repository_stale'))
        self.assertEqual(stage['continuation'], 'Review the difference on the Repository surface (9).')
        # The step is the one the first signal recorded, never another signal's: with none recorded there is none.
        read['attention']['signals'].insert(0, {'area': 'operations', 'code': 'operation_unreadable', 'observed': 'x', 'evidence': {}})
        stage = by_id(project(read))['maintain']
        self.assertEqual((stage['reason'], stage['continuation']), ('operation_unreadable', None))
        read['attention'] = {'status': 'partly_checked', 'checked': {}, 'signals': []}
        self.assertEqual(by_id(project(read))['maintain']['state'], 'unknown')

    def test_an_operation_whose_evidence_cannot_be_read_is_unknown_with_the_code_and_invents_no_step(self):
        read = with_operation(baseline(), delivery={'error_code': 'maintenance_evidence_changed'},
                              review={'error_code': 'maintenance_evidence_changed'})
        flow = project(read)
        stages = by_id(flow)
        self.assertEqual(stages['propose']['state'], 'done')
        for name in ('review', 'approve_execute', 'readback', 'reconcile', 'record', 'observed_after'):
            self.assertEqual((stages[name]['state'], stages[name]['reason']), ('unknown', 'maintenance_evidence_changed'), name)
            self.assertIsNone(stages[name]['continuation'], name)
        # The position stops at the last stage that was read: unreadable evidence is not a place the records put it at.
        self.assertEqual(flow['position'], 'propose')


class RealStoreTests(unittest.TestCase):
    """The real store, modeled service and maintenance engine: the read model's own values, then the projection."""
    RESOURCE_ADDRESS = repository_tests.RepositoryOwnedChangeTests.RESOURCE_ADDRESS
    setUp = repository_tests.RepositoryOwnedChangeTests.setUp
    import_intent = repository_tests.RepositoryOwnedChangeTests.import_intent
    edit_description = repository_tests.RepositoryOwnedChangeTests.edit_description

    def prepare(self):
        from intune_iac.workbench_repository import propose_from_intent, refresh_intent
        self.import_intent()
        self.edit_description('Edited in the repository.')
        self.intent = refresh_intent(self.store, OBJECT, 'b' * 40)
        self.operation = self.root / 'operation'
        return propose_from_intent(self.store.root, self.service.root, OBJECT, self.operation)

    def flow(self):
        from intune_iac import workbench
        read = workbench._workflow_read(self.store, OBJECT, service_root=self.service.root)
        return read, project(read)

    def test_a_policy_with_only_an_observation_and_an_intent(self):
        self.import_intent()
        read, flow = self.flow()
        self.assertEqual(states_of(flow), {'observe': 'done', 'adopt': 'not_recorded', 'intent': 'done',
                                           'propose': 'not_recorded', 'review': 'not_recorded',
                                           'approve_execute': 'not_recorded', 'readback': 'not_recorded',
                                           'reconcile': 'not_recorded', 'record': 'not_recorded',
                                           'observed_after': 'not_recorded', 'maintain': 'not_recorded'})
        self.assertEqual(flow['position'], 'intent')
        self.assertIn('Prepare a proposal from the recorded intent', by_id(flow)['propose']['continuation'])
        # The service was consulted for the proposal check, and the stage says so.
        self.assertEqual(by_id(flow)['observe']['facts']['proposal_check'], 'made against the service')

    def test_a_repository_edit_blocks_the_intent_and_nothing_else(self):
        self.import_intent()
        _, before = self.flow()
        self.edit_description('Edited in the repository.')
        _, after = self.flow()
        self.assertEqual(differing(before, after), ['intent'])
        self.assertEqual(basis_of(after)['intent'], ('blocked', 'states.intent.status', 'repository_stale'))

    def test_a_prepared_change_waits_for_the_exact_digest(self):
        from intune_iac import maintenance
        from intune_iac.workbench_screens import lifecycle_next
        review = self.prepare()
        read, flow = self.flow()
        stages = by_id(flow)
        self.assertEqual([stages[name]['state'] for name in IDS],
                         ['done', 'not_recorded', 'done', 'done', 'done', 'waiting', 'not_recorded', 'not_applicable',
                          'not_recorded', 'not_recorded', 'not_recorded'])
        self.assertEqual(flow['position'], 'approve_execute')
        self.assertEqual(stages['approve_execute']['continuation'], lifecycle_next(4, maintenance.review(self.operation), 0.0, None))
        self.assertIn('execute %s DIGEST' % self.operation, stages['approve_execute']['continuation'])        # the recorded text, not the words
        self.assertNotIn(review['approval_digest'], str(flow))
        self.assertEqual(flow['operation']['operation_id'], review['operation_id'])

    def test_a_closed_window_is_blocked_with_the_closed_time(self):
        from intune_iac import maintenance
        from intune_iac.workbench_screens import _readable_epoch, lifecycle_next
        review = self.prepare()
        with mock.patch('intune_iac.protected._now', lambda: review['expires_at'] + 10):
            read, flow = self.flow()
            expected = lifecycle_next(4, maintenance.review(self.operation), 0.0, None)
        stage = by_id(flow)['approve_execute']
        self.assertEqual((stage['state'], stage['reason']), ('blocked', 'closed'))
        self.assertEqual(stage['facts']['closed_at'], review['expires_at'])
        self.assertEqual(stage['continuation'], expected)
        self.assertIn('closed at ' + _readable_epoch(review['expires_at']), stage['continuation'])

    def test_a_lost_response_is_unknown_with_the_reconcile_step_and_a_reconcile_resolves_the_branch_only(self):
        from intune_iac import maintenance
        from intune_iac.workbench_screens import RECONCILE_NEXT
        review = self.prepare()
        maintenance.execute(self.operation, approve_digest=review['approval_digest'], fault='lost-response')
        _, flow = self.flow()
        stages = by_id(flow)
        self.assertEqual((stages['approve_execute']['state'], stages['readback']['state'], stages['reconcile']['state']),
                         ('unknown', 'unknown', 'current'))
        self.assertEqual((stages['readback']['continuation'], stages['reconcile']['continuation']), (RECONCILE_NEXT, RECONCILE_NEXT))
        self.assertEqual(flow['position'], 'reconcile')
        maintenance.reconcile(self.operation)
        _, flow = self.flow()
        stages = by_id(flow)
        self.assertEqual((stages['readback']['state'], stages['reconcile']['state'], stages['reconcile']['reason']),
                         ('unknown', 'done', 'desired_state_observed'))

    def test_a_verified_change_then_its_record_then_the_observation_after_it(self):
        from intune_iac import maintenance
        from intune_iac.workbench_views import record_local_deployment
        review = self.prepare()
        maintenance.execute(self.operation, approve_digest=review['approval_digest'])
        _, flow = self.flow()
        stages = by_id(flow)
        self.assertEqual([stages[name]['state'] for name in ('approve_execute', 'readback', 'reconcile', 'record')],
                         ['done', 'done', 'not_applicable', 'current'])
        # The execution moved the service: the observation is fresh by age and no longer current with its source.
        self.assertEqual(basis_of(flow)['observe'], ('blocked', 'states.observation.eligibility.reason', 'service_changed'))
        self.assertEqual(flow['position'], 'record')
        record_local_deployment(self.store, self.operation, self.intent['artifact_id'])
        _, flow = self.flow()
        stages = by_id(flow)
        self.assertEqual((stages['record']['state'], stages['observed_after']['state']), ('done', 'not_recorded'))
        self.assertEqual(stages['observed_after']['continuation'], 'Collect to observe the policy after the change.')
        self.store.collect(self.service)
        _, flow = self.flow()
        stages = by_id(flow)
        self.assertEqual([stages[name]['state'] for name in ('observe', 'record', 'observed_after', 'maintain')],
                         ['done', 'done', 'done', 'current'])
        self.assertEqual(flow['position'], 'maintain')

    def test_reading_the_workflow_writes_nothing(self):
        import hashlib
        from pathlib import Path
        self.prepare()

        def tree(*roots):
            return {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for root in roots
                    for path in sorted(Path(root).rglob('*')) if path.is_file()}
        before = tree(self.store.root, self.operation)
        self.flow()
        self.assertEqual(tree(self.store.root, self.operation), before)

    def test_an_adopted_policy_has_the_adopt_stage_done(self):
        self.import_intent()
        self.store.record_artifact('adoption', OBJECT, {'schema_version': 'workbench-adoption/1', 'tenant_id': TENANT,
                                                         'object_id': OBJECT, 'binding': {}, 'binding_sha256': 'a' * 64,
                                                         'maintenance_service_root': '/s', 'cloud_authority': False,
                                                         'execution_authorized': False})
        _, flow = self.flow()
        self.assertEqual(by_id(flow)['adopt']['state'], 'done')
        self.assertTrue(by_id(flow)['adopt']['basis'].startswith('adoption record '))



# ---- item 2: the renderer -------------------------------------------------------------------------------------------

WIDTHS = {'120': 116, '80': 76, '60': 56}        # the pane's width inside the frame at each window width
MARK = re.compile(r'\[[x+:!#?_-]\]')
LANE_WIDTH = 41
STATE_WORD_WIDTH = 14
NAME = 'Windows Privacy Pilot'


def closed_delivery():
    delivery = prepared_delivery()
    delivery['stages'][2] = stage_row('approval', 'expired', opens_at=1_792_000_000, closes_at=1_792_000_300)
    return delivery


def state_sets():
    """One fixture (one policy, one operation) under five different sets of recorded states."""
    stale_and_changed = with_operation(baseline())
    stale_and_changed['states']['observation'].update(freshness='stale', freshness_reasons=['older_than_window'])
    stale_and_changed['states']['intent']['status'] = 'changed'
    verified = with_operation(baseline(), delivery=executed_delivery('verified'), journal='succeeded_verified',
                              review=prepared_review('open', status='succeeded_verified'))
    return {
        'waiting': with_operation(baseline()),
        'closed': with_operation(baseline(), delivery=closed_delivery(), review=prepared_review('closed'), window='closed'),
        'unknown': with_operation(baseline(), delivery=executed_delivery('unknown'), journal='outcome_unknown',
                                  review=prepared_review('open', status='outcome_unknown')),
        'verified': verified,
        'stale': stale_and_changed}


def flows():
    return {name: project(read) for name, read in state_sets().items()}


def lines_of(flow, width=76, rules='ascii', **kw):
    from intune_iac.workbench_screens import workflow_map_lines
    return workflow_map_lines(flow, width, rules, **kw)


def lanes_of(lines):
    from intune_iac.workbench_screens import MapLine
    return [row for row in lines if isinstance(row, MapLine)]


def mask_lane(row):
    """A lane row with its position mark, state mark and state word replaced by placeholders of the same cells."""
    return row[0] + ' ' + MARK.sub('[M]', row[2:-STATE_WORD_WIDTH]) + 'S' * STATE_WORD_WIDTH


def legend_at(lines):
    return next(index for index, row in enumerate(lines) if '> focus' in row)


def masked_frame(lines):
    """Every row above and including the legend, the lanes with marks and state words masked: the geometry."""
    from intune_iac.workbench_screens import MapLine
    return [mask_lane(row) if isinstance(row, MapLine) else str(row) for row in lines[:legend_at(lines) + 1]]


class WorkflowMapLinesTests(unittest.TestCase):
    def test_eleven_lanes_in_stage_order_each_a_fixed_width_cell_with_a_mark_and_a_state_word(self):
        from intune_iac.workbench_screens import WORKFLOW_LABELS
        flow = flows()['waiting']
        rows = lanes_of(lines_of(flow))
        self.assertEqual(len(rows), 11)
        for row, stage in zip(rows, flow['stages']):
            self.assertEqual(len(row), LANE_WIDTH, row)
            found = MARK.search(row)
            self.assertEqual(found.group(0)[1], {'done': 'x', 'current': '+', 'waiting': ':', 'blocked': '!', 'refused': '#',
                                                 'unknown': '?', 'not_recorded': '_', 'not_applicable': '-'}[stage['state']], row)
            self.assertEqual(found.start(), 9 if stage['branch_of'] else 6, row)       # the side lane hangs three cells in
            # The stage's own label follows its mark, so the rows are in the projection's order.
            self.assertTrue(row[found.end() + 1:].startswith(WORKFLOW_LABELS[stage['id']]), row)
            self.assertEqual(row[-STATE_WORD_WIDTH:], stage['state'].replace('_', ' ').ljust(STATE_WORD_WIDTH), row)

    def test_the_state_words_are_the_closed_set_in_words_and_never_not_started(self):
        for name, flow in flows().items():
            lanes = '\n'.join(lanes_of(lines_of(flow)))
            self.assertNotIn('not started', lanes, name)
            self.assertNotIn('not_', lanes, name)               # words, not codes: not recorded, not applicable
        text = '\n'.join(lanes_of(lines_of(flows()['unknown'])))
        for word in ('done', 'not recorded', 'unknown', 'current'):
            self.assertIn(word, text)

    def test_the_reconcile_branch_is_a_side_lane_right_under_readback_in_the_same_state_column(self):
        for rules in ('ascii', 'unicode'):
            rows = lanes_of(lines_of(flows()['unknown'], rules=rules))
            names = sorted(('observe', 'adopt', 'intent', 'propose', 'review', 'approve, execute', 'readback', 'reconcile',
                            'record', 'observed after', 'maintain'), key=len, reverse=True)
            labels = [next(name for name in names if row[row.index('] ') + 2:].startswith(name)) for row in rows]
            self.assertEqual(labels.index('reconcile'), labels.index('readback') + 1)
            readback, branch, record = rows[labels.index('readback')], rows[labels.index('reconcile')], rows[labels.index('record')]
            self.assertGreater(branch.index('['), readback.index('['))           # the branch hangs inside its parent
            self.assertEqual(len(branch), len(readback))
            # The spine carries on past the branch to the stage after readback.
            spine = '|' if rules == 'ascii' else '\u2502'
            self.assertIn(spine, branch[3:6])
            self.assertEqual(branch[branch.index('[') + 4:][:9], 'reconcile')
            self.assertEqual(record[3], readback[3])

    def test_the_position_is_marked_apart_from_the_focus_and_both_leave_the_state_cell_alone(self):
        flow = flows()['unknown']
        rows = lanes_of(lines_of(flow, focus='intent'))
        stages = [stage['id'] for stage in flow['stages']]
        self.assertEqual([index for index, row in enumerate(rows) if row[0] == '>'], [stages.index('intent')])
        self.assertEqual([index for index, row in enumerate(rows) if row[1] == '@'], [stages.index(flow['position'])])
        self.assertNotEqual(stages.index('intent'), stages.index(flow['position']))
        both = lanes_of(lines_of(flow, focus=flow['position']))
        self.assertEqual([row[:2] for row in both if row[:2].strip()], ['>@'])
        # The default focus is the position; an id that is not a stage falls back to it too.
        for focus in (None, 'nonsense'):
            rows = lanes_of(lines_of(flow, focus=focus))
            self.assertEqual([row[:2] for row in rows if row[:2].strip()], ['>@'])

    def test_one_legend_row_names_focus_and_position_in_every_width(self):
        for width in (56, 76, 116, 130):
            lines = lines_of(flows()['waiting'], width)
            legend = [row for row in lines if '> focus' in row]
            self.assertEqual(len(legend), 1, width)
            self.assertIn('@ position', legend[0])
            self.assertLessEqual(len(legend[0]), width)
        wide = [row for row in lines_of(flows()['waiting'], 130) if '> focus' in row][0]
        for word in ('done', 'current', 'waiting', 'blocked', 'refused', 'unknown', 'not recorded', 'not applicable'):
            self.assertIn(word, wide)
        narrow = [row for row in lines_of(flows()['waiting'], 76) if '> focus' in row][0]
        self.assertIn('? help', narrow)

    def test_the_detail_block_names_basis_reason_continuation_and_what_enter_opens(self):
        from intune_iac.workbench_screens import lifecycle_next
        flow = flows()['waiting']
        lines = lines_of(flow, 76, focus='approve_execute')
        text = '\n'.join(str(row) for row in lines[legend_at(lines):])
        self.assertIn('FOCUS approve, execute | waiting', text)
        self.assertIn('Enter opens v Delivery', text)
        self.assertIn('basis', text)
        self.assertIn('operation 4d972e93 delivery stage approval', text.replace('\n', ' '))
        head = lifecycle_next(4, state_sets()['waiting']['review'], 0.0, None).split('\n')[0]
        self.assertIn(head[:40], text)
        # Commands in a step stand on their own rows, as every screen prints them.
        self.assertTrue(any(str(row).strip().startswith('the execute command using /w/operation') for row in lines), lines)
        self.assertTrue(any(str(row).startswith('        ') and 'the execute command using /w/operation' in str(row) for row in lines), lines)

    def test_the_detail_rows_read_in_order_identity_basis_recorded_then_the_step(self):
        lines = [str(row) for row in lines_of(flows()['waiting'], 76, focus='approve_execute')]
        below = lines[legend_at(lines) + 1:]
        first = {word: next(index for index, row in enumerate(below) if row.startswith(word))
                 for word in ('FOCUS', 'basis', 'recorded', 'next')}
        self.assertEqual(sorted(first, key=first.get), ['FOCUS', 'basis', 'recorded', 'next'])
        # The commands the step prints come after its sentence, each on a row of its own.
        self.assertGreater(next(index for index, row in enumerate(below) if row.strip().startswith('the execute command using /w/operation')),
                           first['next'])

    def test_a_reason_is_shown_as_the_recorded_code_and_an_absent_one_is_said(self):
        flows_ = flows()
        text = '\n'.join(str(row) for row in lines_of(flows_['closed'], 76, focus='approve_execute'))
        self.assertIn('reason closed', text)
        text = '\n'.join(str(row) for row in lines_of(flows_['waiting'], 76, focus='approve_execute'))
        self.assertIn('no reason recorded', text)

    def test_a_closed_window_shows_the_closed_time_in_the_detail(self):
        from intune_iac.workbench_screens import _readable_epoch
        text = ' '.join(' '.join(str(row) for row in lines_of(flows()['closed'], 76, focus='approve_execute')).split())
        self.assertIn('approval window closed ' + _readable_epoch(1_792_000_300), text)

    def test_a_stage_with_no_step_prints_no_step_and_no_operation_says_what_enter_does(self):
        flow = project(baseline())
        lines = lines_of(flow, 76, focus='readback')
        text = '\n'.join(str(row) for row in lines[legend_at(lines):])
        self.assertFalse(any(str(row).startswith('next') for row in lines), lines)
        self.assertIn('Enter opens nothing: no operation is recorded', text)
        self.assertIn('FOCUS readback | not recorded', text)

    def test_every_line_fits_the_pane_at_120_80_and_60_in_both_rules_for_every_focus(self):
        for name, flow in flows().items():
            for rules in ('ascii', 'unicode'):
                for width in WIDTHS.values():
                    for stage in [None] + [stage['id'] for stage in flow['stages']]:
                        for row in lines_of(flow, width, rules, focus=stage):
                            self.assertLessEqual(len(str(row)), width, (name, rules, width, stage, row))

    def test_ascii_output_has_no_byte_above_0x7f_and_the_unicode_rules_do(self):
        for flow in flows().values():
            ascii_text = '\n'.join(str(row) for row in lines_of(flow, 116, 'ascii'))
            self.assertTrue(all(ord(char) < 0x80 for char in ascii_text), [c for c in ascii_text if ord(c) >= 0x80])
        unicode_text = '\n'.join(str(row) for row in lines_of(flows()['waiting'], 116, 'unicode'))
        self.assertTrue(any(ord(char) >= 0x80 for char in unicode_text))

    def test_the_renderer_writes_no_escape_sequence_and_a_hostile_name_is_shown_escaped(self):
        read = state_sets()['waiting']
        read['name'] = 'Evil \x1b[31mred\x1b[0m \x1b]0;title\x07 \u202egnp'
        text = '\n'.join(str(row) for row in lines_of(project(read), 76, 'unicode'))
        for forbidden in ('\x1b', '\x07', '\u202e'):
            self.assertNotIn(forbidden, text)
        self.assertIn('\\u001b[31m', text)
        for flow in flows().values():
            self.assertNotIn('\x1b', '\n'.join(str(row) for row in lines_of(flow)))

    def test_the_geometry_is_the_same_under_five_state_sets_once_marks_and_state_words_are_masked(self):
        for rules in ('ascii', 'unicode'):
            for width in WIDTHS.values():
                # A fixed focus: the default focus is the position, which moves with the records like the marks do.
                drawn = {name: lines_of(flow, width, rules, focus='observe') for name, flow in flows().items()}
                frames = {name: masked_frame(lines) for name, lines in drawn.items()}
                first = frames['waiting']
                for name, rows in frames.items():
                    self.assertEqual(rows, first, (rules, width, name))
                # The states really differ: unmasked, every set draws something different.
                raw = {name: tuple(str(row) for row in lines[:legend_at(lines) + 1]) for name, lines in drawn.items()}
                self.assertEqual(len(set(raw.values())), len(raw))

    def test_the_geometry_does_not_depend_on_the_pane_width_either(self):
        for name, flow in flows().items():
            narrow = lanes_of(lines_of(flow, 56))
            wide = lanes_of(lines_of(flow, 116))
            self.assertEqual([str(row) for row in narrow], [str(row) for row in wide], name)

    def test_the_lanes_are_unwrappable_map_rows_and_the_legend_and_focus_rows_are_pinned(self):
        from intune_iac.workbench_screens import MapLine, PinnedRow
        lines = lines_of(flows()['waiting'], 76, focus='approve_execute')
        self.assertEqual(len(lanes_of(lines)), 11)
        self.assertEqual(sum(row.focused for row in lanes_of(lines)), 1)
        self.assertTrue(lanes_of(lines)[5].focused)
        self.assertIsInstance(lines[legend_at(lines)], PinnedRow)
        focus = next(index for index, row in enumerate(lines) if str(row).startswith('FOCUS'))
        self.assertIsInstance(lines[focus], PinnedRow)
        self.assertFalse(any(isinstance(row, MapLine) for row in lines[legend_at(lines):]))

    def test_the_header_names_the_policy_and_does_not_change_with_a_state(self):
        headers = {name: str(lines_of(flow)[0]) for name, flow in flows().items()}
        self.assertEqual(len(set(headers.values())), 1)
        header = next(iter(headers.values()))
        self.assertTrue(header.startswith('[WORKFLOW] ' + NAME + ' (' + OBJECT[:8] + ')'), header)

    def test_the_size_gate_and_the_larger_window_sentence(self):
        from intune_iac.workbench_screens import WORKFLOW_MIN_SIZE, workflow_fits, workflow_unavailable_lines
        self.assertEqual(WORKFLOW_MIN_SIZE, (60, 20))
        for size in ((120, 40), (80, 24), (60, 20)):
            self.assertTrue(workflow_fits(size), size)
        for size in ((40, 12), (59, 24), (80, 19)):
            self.assertFalse(workflow_fits(size), size)
        for width in (40, 76):
            # A command too wide for a row breaks between its arguments with a trailing backslash; copied, it is one command.
            lines = workflow_unavailable_lines(width, '/tmp/store', OBJECT)
            text = ' '.join(' '.join(lines).replace(' \\', '').split())
            self.assertIn('needs a larger window', text)
            self.assertIn('intune-iac workbench workflow --root /tmp/store --policy ' + OBJECT, text)
            self.assertTrue(all(len(row) <= width for row in lines))
        # With no root or policy to name there is no command, and the sentence says so.
        text = ' '.join(' '.join(workflow_unavailable_lines(36)).split())
        self.assertIn('needs a larger window', text)
        self.assertNotIn('ROOT', text)

    def test_a_projection_with_an_unknown_state_or_no_stages_still_draws_without_claiming_one(self):
        flow = flows()['waiting']
        broken = dict(flow, stages=[dict(stage, state='mystery') if stage['id'] == 'review' else stage for stage in flow['stages']])
        row = lanes_of(lines_of(broken))[4]
        self.assertEqual((row[7], row[-STATE_WORD_WIDTH:].strip()), ('?', 'unknown'))
        self.assertEqual(lanes_of(lines_of(dict(flow, stages=[]))), [])



# ---- item 3: the workspace layer -----------------------------------------------------------------------------------

ANSI = re.compile(r'\x1b\[[0-9;?]*[A-Za-z]')


def typed(command):
    """The keys that type a command into the command bar and submit it."""
    return [('text', ':')] + [('text', char) for char in command] + ['enter']


class Reader:
    """A key reader that hands out the given keys in order; `eof` ends the loop of Workspace.input without a command."""

    def __init__(self, items):
        self.items = list(items)

    def read(self):
        return self.items.pop(0)


class LayerFixture(unittest.TestCase):
    """The real store, modeled service and maintenance engine behind a real Workspace driven by keys."""
    RESOURCE_ADDRESS = repository_tests.RepositoryOwnedChangeTests.RESOURCE_ADDRESS
    setUp = repository_tests.RepositoryOwnedChangeTests.setUp
    import_intent = repository_tests.RepositoryOwnedChangeTests.import_intent
    edit_description = repository_tests.RepositoryOwnedChangeTests.edit_description

    def prepare(self):
        from intune_iac.workbench_repository import propose_from_intent, refresh_intent
        self.import_intent()
        self.edit_description('Edited in the repository.')
        self.intent = refresh_intent(self.store, OBJECT, 'b' * 40)
        self.operation = self.root / 'operation'
        return propose_from_intent(self.store.root, self.service.root, OBJECT, self.operation)

    def run_keys(self, sequence, size=(120, 40), rules='unicode', color=False, watch=None):
        """Run the real engine behind a Workspace fed these keys. ws.states[i] and frames[i] are what was on screen when key
        i was asked for, that is after key i - 1 took effect; ws.sent lists the commands the workspace sent."""
        from intune_iac.workbench import run_terminal
        from intune_iac.workbench_tui import Workspace
        out = io.StringIO()
        ws = Workspace(self.store.root, stdout=out, stdin=io.StringIO(), no_color=not color)
        ws.rules = rules
        ws._terminal_size = lambda: size
        frames, ws.states, ws.sent = [], [], []

        class Keys(Reader):
            def read(self):
                frames.append(out.getvalue().split('\x1b[H')[-1].replace('\x1b[J', '').split('\r\n'))
                ws.states.append(dict(tab=ws.tab, layer=ws.layer, notice=ws.notice, selected=ws.selected,
                                      focus=ws.workflow_focus, scroll=ws.scroll, last=ws.last_command))
                if watch:
                    watch(len(frames) - 1, ws)
                return super().read()
        ws.key_reader = Keys(sequence)
        original = ws._send
        ws._send = lambda command, **kw: (ws.sent.append(command), original(command, **kw))[1]
        result = run_terminal(self.store.root, service_root=self.service.root, input_fn=ws.input,
                              output_fn=lambda line: None, result_fn=ws.receive)
        self.assertEqual(result.get('status'), 'closed')
        return ws, frames

    def layer_workspace(self, size=(120, 40), rules='unicode', focus=None):
        """A Workspace with the layer open on the real projection of the selected policy, and no engine behind it."""
        from intune_iac import workbench
        from intune_iac.workbench_tui import Workspace
        ws = Workspace(self.store.root, stdout=io.StringIO(), stdin=io.StringIO(), no_color=True)
        ws.pending.clear()                    # an earlier workspace on this store left a context to resume; this one starts bare
        ws.rules = rules
        ws._terminal_size = lambda: size
        ws.size = size
        ws.selected = OBJECT
        ws.last_command = 'workflow'
        ws.receive(workbench._workflow(self.store, OBJECT, service_root=self.service.root))
        ws.workflow_focus = focus
        return ws

    @staticmethod
    def press(ws, *keys):
        """Feed keys to a workspace; the command it returns, or None when it read them all and wanted another."""
        ws.key_reader = Reader(list(keys) + ['eof'])
        try:
            return ws.input('')
        except EOFError:
            return None

    @staticmethod
    def plain(rows):
        return [ANSI.sub('', row) for row in rows]

    def open_layer(self, size=(120, 40), rules='unicode', color=False, extra=()):
        key = lambda char: ('text', char)
        return self.run_keys(typed('select ' + OBJECT) + typed('workflow') + list(extra) + [key('q')], size, rules, color)


class EngineCommandTests(LayerFixture):
    def test_the_workflow_command_needs_a_selection_and_returns_the_projection_of_the_selected_policy(self):
        from intune_iac import workbench
        from intune_iac.workbench import run_terminal
        self.prepare()
        commands = iter(['workflow', 'select ' + OBJECT, 'workflow', 'workflow extra', 'quit'])
        results = []
        run_terminal(self.store.root, service_root=self.service.root, input_fn=lambda _: next(commands), result_fn=results.append)
        errors = [item for item in results if item.get('status') == 'error']
        self.assertEqual([item['error']['code'] for item in errors][:1], ['selection_required'])
        flows_ = [item for item in results if item.get('schema_version') == 'workflow-map/1']
        self.assertEqual(len(flows_), 1)
        expected = workbench._workflow(self.store, OBJECT, service_root=self.service.root)
        self.assertEqual(flows_[0]['revision'], expected['revision'])
        self.assertEqual(flows_[0]['object_id'], OBJECT)
        # Extra words are an invalid request, as for every read view that takes none.
        self.assertEqual(errors[-1]['error']['code'], 'invalid_workbench_request')

    def test_workflow_is_a_read_view_listed_in_the_help_and_never_a_resumable_context_view(self):
        from intune_iac.workbench import HELP
        from intune_iac.workbench_tui import LAYERS, READ_VIEWS, SUBVIEWS, VIEW_COMMANDS
        self.assertIn('workflow', VIEW_COMMANDS)
        self.assertNotIn('workflow', READ_VIEWS)
        self.assertEqual((LAYERS['workflow'], SUBVIEWS['workflow']), ('read-only', 'Workflow'))
        line = next(entry for entry in HELP['navigation'] if entry.startswith('workflow'))
        for word in ('selected policy', 'read-only', 'Esc'):
            self.assertIn(word, line)

    def test_the_help_reference_names_workflow_and_its_marks_and_keys_truthfully(self):
        from intune_iac.workbench_screens import help_lines
        text = ' '.join(' '.join(help_lines(100)).split())
        self.assertIn(':workflow', text)
        for word in ('x done', '+ current', ': waiting', '! blocked', '# refused', '? unknown', '_ not recorded',
                     '- not applicable', '@ marks', 'Enter opens', 'Esc', 'intune-iac workbench workflow --root ROOT --policy ID'):
            self.assertIn(word, text, word)
        self.assertIn('reads and records nothing', text)


class LayerFrameTests(LayerFixture):
    def test_the_command_opens_the_layer_over_the_inspector_and_the_frame_names_it(self):
        self.prepare()
        ws, frames = self.open_layer()
        state, rows = ws.states[-1], self.plain(frames[-1])
        self.assertEqual((state['layer'], state['tab']), ('workflow', 1))
        self.assertIn('INTUNE WORKBENCH  /  Inspector  /  Workflow  /  read-only', rows[0])
        # The title fits the narrowest window the map is drawn in, so "read-only" is never cut.
        ws, frames = self.open_layer((60, 20), 'ascii')
        self.assertTrue(self.plain(frames[-1])[0].rstrip().endswith('read-only'), self.plain(frames[-1])[0])
        text = ' '.join(' '.join(rows).split())
        self.assertIn('[WORKFLOW]', text)
        self.assertIn('approve, execute', text)
        self.assertIn('Workflow map shown (read-only)', state['notice'])

    def test_every_frame_line_fits_each_window_in_both_rules_and_ascii_has_no_high_byte(self):
        self.prepare()
        for size in ((120, 40), (80, 24), (60, 20)):
            for rules in ('ascii', 'unicode'):
                ws, frames = self.open_layer(size, rules)
                rows = self.plain(frames[-1])
                for row in rows:
                    self.assertLessEqual(len(row), size[0], (size, rules, row))
                # The focused lane is always in view (at 60x20 the header has scrolled away to make room for it).
                self.assertIn('approve, execute', ' '.join(rows), (size, rules))
                if rules == 'ascii':
                    text = '\n'.join(frames[-1])
                    self.assertTrue(all(ord(char) < 0x80 for char in text), (size, [c for c in text if ord(c) >= 0x80]))

    def test_no_colour_draws_no_colour_code_and_colour_only_reinforces(self):
        self.prepare()
        ws, plain = self.open_layer((80, 24), 'ascii', color=False)
        self.assertNotIn('38;5', '\n'.join(plain[-1]))
        self.assertNotIn('48;5', '\n'.join(plain[-1]))
        ws, coloured = self.open_layer((80, 24), 'ascii', color=True)
        self.assertEqual(self.plain(coloured[-1])[3:], self.plain(plain[-1])[3:])
        lane = next(row for row in coloured[-1] if 'approve, execute' in row)
        self.assertIn('\x1b[38;5;', lane)                       # the mark is tinted ...
        self.assertIn('waiting', ANSI.sub('', lane))              # ... and the word is still there
        # A stage that does not apply, and one with no record, are not tinted like a warning: colour never says more than
        # the word, and neither of these needs attention.
        cell = re.compile(r'\[((?:\x1b\[[0-9;]*m)?)([x+:!#?_-])')

        def tint(word):
            row = next(row for row in coloured[-1] if word in ANSI.sub('', row) and cell.search(row))
            return cell.search(row).group(1)
        self.assertEqual((tint('not applicable'), tint('not recorded')), ('', ''))
        self.assertNotEqual(tint('waiting'), '')

    def test_at_80x24_the_focused_lane_stays_in_view_with_the_legend_and_the_focus_rows_pinned_below_it(self):
        self.prepare()
        ws, frames = self.run_keys(typed('select ' + OBJECT) + typed('workflow') + ['down'] * 10 + [('text', 'q')], (80, 24), 'ascii')
        shown = 0
        for rows in frames[-12:]:
            rows = self.plain(rows)
            text = '\n'.join(rows)
            if '[WORKFLOW]' in text or 'FOCUS ' in text:
                shown += 1
                self.assertTrue(any(row.startswith('| >') for row in rows), text)
                self.assertIn('> focus @ position', text)
                self.assertIn('FOCUS ', text)
        self.assertGreaterEqual(shown, 11)

    def test_below_60x20_the_layer_says_it_needs_a_larger_window_with_the_plain_text_command_and_draws_no_map(self):
        self.prepare()
        for size in ((40, 12), (59, 24), (80, 19), (39, 11)):
            ws, frames = self.open_layer(size, 'ascii')
            text = ' '.join(' '.join(self.plain(frames[-1])).replace(' \\', '').split())
            self.assertIn('needs a larger window', text, size)
            # The workspace knows its root and the selected policy, so the command names them (not the ROOT and ID stand-ins).
            # (A row holds a policy id's 36 cells and the indent from 40 columns; narrower, the stand-in ID is printed.)
            if size[0] >= 40:
                self.assertIn('intune-iac workbench workflow --root %s --policy %s' % (self.store.root, OBJECT), text, size)
            else:
                self.assertNotIn('intune-iac workbench workflow --root', text, size)   # no stand-in: no command
                self.assertIn('--policy (the policy id cannot be shown here)', text, size)
            self.assertNotIn('approve, execute', text, size)
            self.assertNotIn('[WORKFLOW]', text, size)
            for row in self.plain(frames[-1]):
                self.assertLessEqual(len(row), size[0], (size, row))
        # The layer is still open and Esc still closes it: only the drawing was left out.
        self.assertEqual(ws.states[-1]['layer'], 'workflow')
        self.assertEqual(ws.states[-1]['notice'], 'Workflow map needs a larger window. Esc closes it.')

    def test_the_key_line_names_the_layers_keys_and_no_key_that_changes_anything(self):
        from intune_iac.workbench_tui import help_line
        for width in (120, 80, 60, 40):
            line = help_line(width, 'workflow')
            self.assertLessEqual(len(line), width)
            self.assertIn('Esc', line)
            for forbidden in ('a actions', 'execute', 'approve', 'record', 'prepare'):
                self.assertNotIn(forbidden, line)
        self.assertIn('Up/Down stage', help_line(120, 'workflow'))
        self.assertIn('Enter open', help_line(120, 'workflow'))


class LayerKeyTests(LayerFixture):
    def test_up_and_down_move_the_focus_one_stage_at_a_time_through_all_eleven_and_stop_at_the_ends(self):
        self.prepare()
        ws = self.layer_workspace()
        ids = [stage['id'] for stage in ws.value['stages']]
        self.assertEqual(ws._workflow_focus(), ws.value['position'])         # it opens at the position the records give
        for _ in range(14):
            self.press(ws, 'up')
        self.assertEqual(ws._workflow_focus(), ids[0])                       # stops at the first stage
        walked = [ws._workflow_focus()]
        for _ in range(10):
            self.press(ws, 'down')
            walked.append(ws._workflow_focus())
        self.assertEqual(walked, ids)                                        # one at a time, none skipped
        for _ in range(4):
            self.press(ws, 'down')
        self.assertEqual(ws._workflow_focus(), ids[-1])                      # and stops at the last
        self.assertEqual((ws.selected, ws.layer), (OBJECT, 'workflow'))

    def test_enter_opens_the_focused_stages_surface_for_the_same_selected_policy(self):
        self.prepare()
        import shlex
        root = shlex.quote(str(self.operation))
        expected = {'observe': ('inspect', 1), 'adopt': ('relationships', 2), 'intent': ('repository-status', 8),
                    'propose': ('review ' + root, 4), 'review': ('review ' + root, 4),
                    'approve_execute': ('delivery ' + root, 5), 'readback': ('delivery ' + root, 5),
                    'reconcile': ('delivery ' + root, 5), 'record': ('delivery ' + root, 5),
                    'observed_after': ('delivery ' + root, 5), 'maintain': ('views', 6)}
        for stage, (command, tab) in expected.items():
            ws = self.layer_workspace(focus=stage)
            self.assertEqual(self.press(ws, 'enter'), command, stage)
            self.assertEqual((ws.tab, ws.selected, ws.layer), (tab, OBJECT, 'summary'), stage)   # the surface replaces the layer

    def test_a_stage_with_nothing_to_open_sends_nothing_and_says_why(self):
        self.import_intent()
        ws = self.layer_workspace(focus='record')
        self.assertIsNone(self.press(ws, 'enter'))                          # nothing was sent
        self.assertIn('no operation is recorded', ws.notice)
        self.assertEqual((ws.layer, ws.selected, ws.workflow_focus), ('workflow', OBJECT, 'record'))

    def test_a_e_r_and_f_in_the_layer_say_it_is_read_only_and_keep_the_layer(self):
        self.prepare()
        for char in ('a', 'e', 'r', 'f'):
            ws = self.layer_workspace()
            self.assertIsNone(self.press(ws, ('text', char)))
            self.assertEqual(ws.layer, 'workflow', char)
            self.assertIn('read-only', ws.notice, char)
            self.assertFalse(ws.mode)

    def test_b_and_escape_return_to_the_view_before_with_its_selection_and_scroll(self):
        self.prepare()
        key = lambda char: ('text', char)
        for close in ('escape', key('b')):
            # Estate, select the highlighted policy (the Inspector), scroll it down, then the command, then close the layer.
            before_command = [key('1'), 'enter', 'pagedown']
            sequence = before_command + typed('workflow') + [close, key('q')]
            ws, _ = self.run_keys(sequence, (80, 24), 'unicode')
            view_before = ws.states[len(before_command)]                     # asked for the first key of the command
            opened = ws.states[len(before_command) + len(typed('workflow'))]          # asked for the closing key
            returned = ws.states[-1]                                         # asked for q, after the return
            self.assertGreater(view_before['scroll'], 0, 'the view before was scrolled')
            self.assertEqual((view_before['layer'], opened['layer']), ('summary', 'workflow'), close)
            self.assertEqual((returned['tab'], returned['selected'], returned['layer']),
                             (view_before['tab'], view_before['selected'], 'summary'), close)
            self.assertEqual(returned['scroll'], view_before['scroll'], close)       # the scroll it had
            self.assertEqual(returned['last'], view_before['last'], close)           # the same view, from the same command


class ReadOnlyTests(LayerFixture):
    def test_no_key_in_the_layer_changes_the_store_or_an_operation_directory(self):
        import hashlib
        from pathlib import Path
        self.prepare()
        key = lambda char: ('text', char)

        def tree():
            names = ('observations.sqlite3', 'observations.sqlite3-wal', 'observations.sqlite3-shm')
            files = [Path(self.store.root) / name for name in names]
            files += [path for path in sorted(self.operation.rglob('*')) if path.is_file()]
            return {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in files if path.exists()}
        snapshots = []
        sequence = (typed('select ' + OBJECT) + typed('workflow') + ['down'] * 6 + ['enter'] + [key('b')] + ['up', 'up', 'enter']
                    + [key('b'), key('a'), key('e'), key('r'), key('f'), 'home', 'tab', 'escape', key('q')])
        before = tree()
        self.run_keys(sequence, watch=lambda index, ws: snapshots.append(tree()))
        self.assertGreater(len(snapshots), 20)
        for index, snapshot in enumerate(snapshots):
            self.assertEqual(snapshot, before, 'after key %d' % index)
        self.assertTrue(before)

    def test_the_layer_sends_only_read_views_to_the_engine(self):
        self.prepare()
        key = lambda char: ('text', char)
        sequence = (typed('select ' + OBJECT) + typed('workflow') + ['down'] * 10 + ['enter'] + [key('b'), 'escape', key('q')])
        ws, _ = self.run_keys(sequence)
        from intune_iac.workbench_tui import VIEW_COMMANDS
        self.assertIn('workflow', ws.sent)
        for command in ws.sent:
            self.assertIn(command.split(' ', 1)[0], VIEW_COMMANDS | {'quit'}, command)
        for forbidden in ('propose', 'execute', 'reconcile', 'collect', 'deployment-record', 'repository-refresh', 'approve'):
            self.assertFalse(any(command.startswith(forbidden) for command in ws.sent), (forbidden, ws.sent))



# ---- item 4: the command ------------------------------------------------------------------------------------------

READ_ONLY = 'This view is read-only: it reads the recorded state of the policy and writes nothing.'


class CommandTests(LayerFixture):
    """`intune-iac workbench workflow --root ROOT --policy ID [--json]`: the same lines, or the projection."""

    def cli(self, *args, encoding='utf-8'):
        import os
        import subprocess
        import sys
        from pathlib import Path
        script = Path(__file__).resolve().parents[1] / 'scripts/intune-iac.py'
        env = dict(os.environ, PYTHONIOENCODING=encoding, PYTHONUTF8='0')
        env.pop('COLUMNS', None)
        return subprocess.run([sys.executable, str(script), 'workbench', 'workflow', *map(str, args)], text=True,
                              capture_output=True, cwd='/tmp', env=env)

    def tree(self):
        import hashlib
        from pathlib import Path
        return {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                for root in (self.store.root, self.operation) for path in sorted(Path(root).rglob('*')) if path.is_file()}

    def test_the_text_form_prints_every_stage_the_position_and_its_step_complete_when_piped(self):
        self.prepare()
        result = self.cli('--root', self.store.root, '--policy', OBJECT, '--service-root', self.service.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        text = result.stdout
        lines = text.splitlines()
        self.assertTrue(lines[0].startswith('[WORKFLOW] '), lines[:2])
        for label in ('observe', 'adopt', 'intent', 'propose', 'review', 'approve, execute', 'readback', 'reconcile', 'record',
                      'observed after', 'maintain'):
            self.assertEqual(sum(1 for line in lines if label + ':' in line), 1, label)       # one block each in STAGES
        self.assertEqual(sum(line.startswith('  basis') for line in lines), 11)
        flat = ' '.join(text.split())
        self.assertIn('Position: approve, execute', flat)
        self.assertIn('approve and run it with the review digest', flat)
        self.assertIn('the execute command using %s, naming the digest that the review shows' % self.operation, flat)
        self.assertIn('operation ' + self.read_operation_prefix() + ' delivery stage approval', flat)
        self.assertTrue(flat.endswith(READ_ONLY), flat[-120:])                # said last, once
        self.assertEqual(flat.count(READ_ONLY), 1)
        # Piped output is 80 columns: no line is wider, and a command is never cut.
        self.assertTrue(all(len(line) <= 80 for line in lines), [line for line in lines if len(line) > 80])

    def read_operation_prefix(self):
        from intune_iac import workbench
        flow = workbench._workflow(self.store, OBJECT, service_root=self.service.root)
        return flow['operation']['operation_id'][:8]

    def test_the_text_lines_are_the_layers_lanes_in_the_encoding_the_output_can_carry(self):
        from intune_iac import workbench
        from intune_iac.workbench_screens import MapLine, workflow_map_lines
        self.prepare()
        flow = workbench._workflow(self.store, OBJECT, service_root=self.service.root)
        for encoding, rules in (('utf-8', 'unicode'), ('ascii', 'ascii')):
            result = self.cli('--root', self.store.root, '--policy', OBJECT, '--service-root', self.service.root,
                              encoding=encoding)
            self.assertEqual(result.returncode, 0, (encoding, result.stderr))
            lanes = [str(row) for row in workflow_map_lines(flow, 80, rules, detail=False, keyboard=False)
                     if isinstance(row, MapLine)]
            self.assertEqual(len(lanes), 11)
            lines = result.stdout.splitlines()
            for lane in lanes:
                self.assertIn(lane.rstrip(), [line.rstrip() for line in lines], (encoding, lane))
            if encoding == 'ascii':
                self.assertTrue(all(ord(char) < 0x80 for char in result.stdout), encoding)
            else:
                self.assertTrue(any(ord(char) >= 0x80 for char in result.stdout), encoding)

    def test_json_prints_one_document_that_is_the_projection(self):
        import json
        from intune_iac import workbench
        self.prepare()
        result = self.cli('--root', self.store.root, '--policy', OBJECT, '--service-root', self.service.root, '--json')
        self.assertEqual(result.returncode, 0, result.stderr)
        document = json.loads(result.stdout)
        expected = workbench._workflow(self.store, OBJECT, service_root=self.service.root)
        self.assertEqual(document['schema_version'], 'workflow-map/1')
        self.assertEqual(document['revision'], expected['revision'])
        self.assertEqual([stage['id'] for stage in document['stages']], IDS)
        self.assertEqual(document['position'], 'approve_execute')
        self.assertTrue(result.stdout.isascii())                      # the CLI's own safe JSON: every non-ASCII character escaped
        self.assertEqual(result.stdout.count('\n'), 1)

    def test_a_service_root_is_optional_and_without_one_the_policy_is_still_read(self):
        import json
        self.prepare()
        plain = json.loads(self.cli('--root', self.store.root, '--policy', OBJECT, '--json').stdout)
        self.assertEqual(plain['schema_version'], 'workflow-map/1')
        self.assertEqual(plain['position'], 'approve_execute')
        # Without a service only the age of the observation is judged, and the map says the proposal check was not made.
        observe = next(stage for stage in plain['stages'] if stage['id'] == 'observe')
        self.assertEqual(observe['facts']['proposal_check'], 'not made: no service root')

    def test_it_writes_nothing_and_changes_neither_the_store_nor_the_operation(self):
        self.prepare()
        before = self.tree()
        for extra in ((), ('--json',)):
            result = self.cli('--root', self.store.root, '--policy', OBJECT, '--service-root', self.service.root, *extra)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.tree(), before)

    def test_an_unknown_policy_is_an_error_with_a_nonzero_exit_and_nothing_on_stdout(self):
        import json
        self.prepare()
        result = self.cli('--root', self.store.root, '--policy', '33333333-3333-4333-8333-333333333333')
        self.assertEqual(result.returncode, 3)
        self.assertEqual(json.loads(result.stderr)['error']['code'], 'workbench_object_missing')
        self.assertEqual(result.stdout, '')
        missing = self.cli('--root', self.store.root)
        self.assertEqual(missing.returncode, 2)

    def test_the_command_is_listed_in_the_workbench_help(self):
        import subprocess
        import sys
        from pathlib import Path
        script = Path(__file__).resolve().parents[1] / 'scripts/intune-iac.py'
        result = subprocess.run([sys.executable, str(script), 'workbench', '--help'], text=True, capture_output=True, cwd='/tmp')
        # The command itself, not workflow-import or workflows, which this text also holds.
        self.assertRegex(result.stdout, r'(?<![-\w])workflow(?![-\w])')


class TextLinesTests(unittest.TestCase):
    def test_the_text_form_lists_every_stage_with_its_basis_and_fits_each_width_down_to_the_lane(self):
        from intune_iac.workbench_screens import workflow_text_lines
        for name, flow in flows().items():
            for rules in ('ascii', 'unicode'):
                for width in (116, 80, 60, 41):
                    lines = workflow_text_lines(flow, width, rules)
                    for line in lines:
                        self.assertLessEqual(len(str(line)), width, (name, rules, width, line))
                    self.assertEqual(sum(str(line).startswith('  basis') for line in lines), 11, (name, width))
                    self.assertTrue(' '.join(' '.join(str(line) for line in lines).split()).endswith(READ_ONLY), (name, width))

    def test_below_the_lane_width_the_text_form_leaves_the_lanes_out_and_still_lists_every_stage(self):
        from intune_iac.workbench_screens import MapLine, workflow_text_lines
        flow = flows()['unknown']
        lines = workflow_text_lines(flow, 30, 'ascii')
        self.assertFalse(any(isinstance(row, MapLine) for row in lines))
        self.assertEqual(sum(str(line).startswith('  basis') for line in lines), 11)
        for line in lines:
            self.assertLessEqual(len(str(line)), 30, line)

    def test_every_stages_step_is_in_the_text_form_not_only_the_positions(self):
        from intune_iac.workbench_screens import RECONCILE_NEXT, workflow_text_lines
        flat = ' '.join(' '.join(str(line) for line in workflow_text_lines(flows()['unknown'], 80, 'ascii')).split())
        self.assertEqual(flat.count(' '.join(RECONCILE_NEXT.split())), 3)       # approve and execute, readback, reconcile
        self.assertIn('Position: reconcile', flat)



# ---- item 5: the Help row that names the strip's hidden fields (journey 29 run 13, frame 37, rows 6 and 7) ------------

class HiddenStripRowTests(unittest.TestCase):
    """"Hidden in the strip at this size (+2 more): OBS fresh |" ended a row with the separator and left the next field
    for the row below. A break falls between two fields, never after a separator, and a field is never split from its label."""
    FULL = ('SYNTHETIC | TENANT 029c33b1 | POLICY Windows Privacy Pilot (d665d54b) | OBS fresh | REPO current | '
            'OP prepared')
    SHOWN_TWO = 'SYNTHETIC | T 029c33b1 | P d665d54b | REPO current | +2 more: ?'
    FULL_THREE = ('SYNTHETIC | TENANT 029c33b1 | POLICY Windows Privacy Pilot (d665d54b) | OBS source changed | '
                  'REPO current | OP outcome unknown')
    SHOWN_THREE = 'SYNTHETIC | T 029c33b1 | P d665d54b | +3 more: ?'

    def block(self, width, full, shown):
        from intune_iac.workbench_screens import help_lines
        lines = help_lines(width, strip=full, strip_shown=shown)
        return lines[1:lines.index('KEYS')]

    def test_the_journey_case_does_not_end_a_row_with_a_separator(self):
        rows = self.block(56, self.FULL, self.SHOWN_TWO)
        self.assertTrue(rows[0].startswith('Hidden in the strip at this size (+2 more):'), rows)
        for row in rows:
            self.assertFalse(row.rstrip().endswith('|'), rows)
            self.assertFalse(row.lstrip().startswith('|'), rows)
        self.assertEqual(' '.join(' '.join(rows).split()),
                         'Hidden in the strip at this size (+2 more): OBS fresh OP prepared')

    def test_no_width_breaks_after_a_separator_or_splits_a_label_from_its_value(self):
        cases = ((self.FULL, self.SHOWN_TWO, ('OBS fresh', 'OP prepared')),
                 (self.FULL_THREE, self.SHOWN_THREE, ('OBS source changed', 'REPO current', 'OP outcome unknown')))
        for full, shown, fields in cases:
            for width in range(36, 121):
                rows = self.block(width, full, shown)
                for row in rows:
                    self.assertLessEqual(len(row), width, (width, row))
                    self.assertFalse(row.rstrip().endswith('|'), (width, rows))
                    self.assertFalse(row.lstrip().startswith('|'), (width, rows))
                for field in fields:
                    self.assertEqual(sum(field in row for row in rows), 1, (width, field, rows))

    def test_fields_that_fit_one_row_keep_their_separators_and_the_joined_text_is_unchanged(self):
        rows = self.block(100, self.FULL_THREE, self.SHOWN_THREE)
        self.assertEqual(rows, ['Hidden in the strip at this size (+3 more): OBS source changed | REPO current | '
                                'OP outcome unknown'])
        rows = self.block(60, self.FULL_THREE, self.SHOWN_THREE)
        joined = ' '.join(rows)
        self.assertIn('REPO current | OP outcome unknown', joined)                   # the fields that share a row stay separated



# ---- follow-up: unreadable evidence, the way back from a surface, and a refusal -----------------------------------------

class FollowUpTests(LayerFixture):
    def test_an_operation_directory_that_was_removed_reads_unknown_with_its_code_and_the_map_still_draws(self):
        import shutil
        from intune_iac import workbench
        from intune_iac.workbench_screens import workflow_map_lines
        self.prepare()
        shutil.rmtree(self.operation)
        flow = workbench._workflow(self.store, OBJECT, service_root=self.service.root)
        stages = by_id(flow)
        self.assertEqual(stages['propose']['state'], 'done')                  # the store registered the proposal
        for name in ('review', 'approve_execute', 'readback', 'reconcile', 'record', 'observed_after'):
            self.assertEqual((stages[name]['state'], stages[name]['reason']), ('unknown', 'unreadable_file'), name)
            self.assertIsNone(stages[name]['continuation'], name)
        self.assertEqual(flow['position'], 'propose')
        self.assertEqual(len(lanes_of(workflow_map_lines(flow, 76, 'ascii'))), 11)

    def test_enter_on_a_stage_then_b_returns_to_the_map_with_the_same_focus_and_b_again_to_the_view_before(self):
        self.prepare()
        key = lambda char: ('text', char)
        # Select, open the layer, move to `intent` (two up from the position), Enter (Repository), b, b.
        sequence = typed('select ' + OBJECT) + typed('workflow') + ['up', 'up', 'up', 'enter', key('b'), key('b'), key('q')]
        ws, _ = self.run_keys(sequence)
        states = ws.states
        at_layer = len(typed('select ' + OBJECT)) + len(typed('workflow'))
        self.assertEqual(states[at_layer]['layer'], 'workflow')
        self.assertEqual(states[at_layer + 3]['focus'], 'intent')            # after three Up from approve_execute
        self.assertEqual((states[at_layer + 4]['tab'], states[at_layer + 4]['layer']), (8, 'summary'))     # Repository
        self.assertEqual((states[at_layer + 5]['layer'], states[at_layer + 5]['focus']), ('workflow', 'intent'))   # back: the map
        self.assertEqual((states[at_layer + 6]['layer'], states[at_layer + 6]['tab']), ('summary', 1))     # back: the Inspector
        self.assertEqual(states[-1]['selected'], OBJECT)

    def test_the_command_without_a_selection_is_refused_and_opens_no_layer(self):
        self.prepare()
        ws, frames = self.run_keys(typed('workflow') + [('text', 'q')], (80, 24), 'ascii')
        self.assertEqual(ws.states[-1]['layer'], 'summary')
        text = ' '.join(' '.join(self.plain(frames[-1])).split())
        self.assertIn('No policy is selected (selection_required)', text)       # the product's own refusal, as for every read view
        self.assertNotIn('[WORKFLOW]', text)



class InvariantTests(unittest.TestCase):
    """Every combination of the statuses Delivery can report keeps the rules the stages promise."""

    APPROVAL = ('done', 'waiting', 'expired', 'clock_unreadable', 'clock_uncertain', 'not_open', 'rejected')
    EXECUTION = ('not_started', 'done', 'unknown')
    READBACK = ('not_started', 'not_recorded', 'pending', 'failed', 'done')
    RECONCILIATION = ('not_needed', 'required', 'pending', 'done')
    RECORD = ('not_yet', 'available', 'done', 'not_available', 'not_applicable')
    OBSERVED = ('not_yet', 'matches_desired', 'differs', 'unknown', 'not_applicable')

    def deliveries(self):
        import itertools
        for approval, execution, readback, reconciliation, record, observed in itertools.product(
                self.APPROVAL, self.EXECUTION, self.READBACK, self.RECONCILIATION, self.RECORD, self.OBSERVED):
            delivery = prepared_delivery()
            delivery['stages'][2] = stage_row('approval', approval, opens_at=1, closes_at=2)
            delivery['stages'][3] = stage_row('execution', execution, error_code='some_code' if execution == 'unknown' else None)
            delivery['stages'][4] = stage_row('readback', readback, classification='desired_state_observed')
            delivery['stages'][5] = stage_row('reconciliation', reconciliation, classification='desired_state_observed')
            delivery['stages'][6] = stage_row('deployment_record', record, reason='no_verified_readback' if record in
                                              ('not_available', 'not_applicable') else None)
            delivery['stages'][7] = stage_row('observed_after', observed, observation_freshness='fresh')
            yield (approval, execution, readback, reconciliation, record, observed), delivery

    def test_no_combination_breaks_a_promise_the_stages_make(self):
        import json
        from intune_iac.workflow_projection import STAGE_IDS
        count = 0
        for key, delivery in self.deliveries():
            approval, execution, readback, reconciliation, record, observed = key
            journal = 'outcome_unknown' if execution == 'unknown' else 'prepared'
            flow = project(with_operation(baseline(), delivery=delivery, journal=journal,
                                          review=prepared_review('open', status=journal)))
            stages = by_id(flow)
            count += 1
            self.assertEqual([stage['id'] for stage in flow['stages']], list(STAGE_IDS), key)
            for stage in flow['stages']:
                self.assertIn(stage['state'], STATES, (key, stage))
                self.assertTrue(isinstance(stage['basis'], str) and stage['basis'], (key, stage))
                self.assertTrue(stage['reason'] is None or isinstance(stage['reason'], str), (key, stage))
            # An unknown outcome is never done.
            if execution == 'unknown':
                self.assertNotEqual(stages['approve_execute']['state'], 'done', key)
                self.assertNotEqual(stages['readback']['state'], 'done', key)
            # Done needs the recorded fact: an approved and verified execution, a readback that says done.
            if stages['approve_execute']['state'] == 'done':
                self.assertEqual((approval, execution), ('done', 'done'), key)
            if stages['readback']['state'] == 'done':
                self.assertEqual((readback, execution == 'unknown'), ('done', False), key)
            # An absent record is not recorded, never a started stage.
            if readback == 'not_started':
                self.assertEqual(stages['readback']['state'], 'not_recorded', key)
            if record == 'not_yet':
                self.assertEqual(stages['record']['state'], 'not_recorded', key)
            if observed == 'not_yet':
                self.assertEqual(stages['observed_after']['state'], 'not_recorded', key)
            # The reconcile branch appears only for an unknown or reconciled outcome.
            if reconciliation == 'not_needed':
                self.assertEqual(stages['reconcile']['state'], 'not_applicable', key)
            # Maintenance needs a complete path.
            if stages['maintain']['state'] != 'not_recorded':
                self.assertEqual((stages['approve_execute']['state'], stages['readback']['state']), ('done', 'done'), key)
            self.assertTrue(flow['position'] is None or flow['position'] in STAGE_IDS, key)
            if flow['position'] is not None:
                here = stages[flow['position']]['state']
                self.assertNotEqual(here, 'not_recorded', key)
                # A stage that does not apply is a position only where the records show it after dispatch.
                if here == 'not_applicable':
                    self.assertIn(flow['position'], ('record', 'observed_after'), key)
                    self.assertIn(execution, ('done', 'unknown'), key)
            json.dumps(flow, allow_nan=False)
        self.assertEqual(count, 7 * 3 * 5 * 4 * 5 * 5)



# ---- fixes from an independent review of the first nine commits ------------------------------------------------------

class ReviewPureTests(unittest.TestCase):
    def test_a_consumer_mismatch_gives_the_step_diagnostics_recorded_not_a_refresh_that_would_be_refused(self):
        step = ('Proposals and execution refuse this intent until the component consumes exactly this policy; fix the '
                'component, then choose Refresh the repository intent (a: actions).')
        read = baseline()
        read['states']['intent']['status'] = 'consumer_changed'
        read['attention'] = {'status': 'attention', 'checked': {}, 'signals': [
            {'area': 'repository', 'code': 'repository_consumer_mismatch', 'observed': 'x', 'evidence': {}, 'next_step': step}]}
        stage = by_id(project(read))['intent']
        self.assertEqual((stage['state'], stage['reason']), ('blocked', 'repository_consumer_mismatch'))
        self.assertEqual(stage['continuation'], step)
        self.assertNotIn('Refresh the repository intent first', stage['continuation'])
        # With no step recorded there is none; the refresh sentence is for a repository that only changed.
        read['attention']['signals'][0].pop('next_step')
        self.assertIsNone(by_id(project(read))['intent']['continuation'])

    def test_a_proposal_check_that_could_not_be_made_is_unknown_and_never_said_to_have_been_made(self):
        read = baseline()
        read['service_checked'] = True
        read['eligibility'] = {'code': 'service_unavailable', 'reason': None, 'message': 'The service cannot be read.'}
        stage = by_id(project(read))['observe']
        self.assertEqual((stage['state'], stage['reason']), ('unknown', 'service_unavailable'))
        self.assertEqual(stage['basis'], 'observation_eligibility.code')
        self.assertEqual(stage['facts']['proposal_check'], 'could not be made')
        # A check that was made and failed with a recorded reason is blocked, as before; one that passed is done.
        read['eligibility'] = {'code': 'maintenance_observation_stale', 'reason': 'service_changed'}
        read['states']['observation']['eligibility'] = dict(read['eligibility'])
        stage = by_id(project(read))['observe']
        self.assertEqual((stage['state'], stage['reason'], stage['facts']['proposal_check']),
                         ('blocked', 'service_changed', 'made against the service'))
        read['eligibility'], read['states']['observation']['eligibility'] = None, None
        self.assertEqual(by_id(project(read))['observe']['state'], 'done')

    def test_a_pending_readback_that_a_later_reconcile_resolved_is_unknown_and_repeats_no_stale_step(self):
        delivery = executed_delivery('reconciled')
        delivery['stages'][4] = stage_row('readback', 'pending', classification='matches_precondition', visibility_pending=True)
        delivery['next_action'] = ('The service has not yet shown the change; reconcile again later with:\n'
                                   '  reconcile /w/operation')
        read = with_operation(baseline(), delivery=delivery, journal='reconciled',
                              review=prepared_review('open', status='reconciled'))
        stages = by_id(project(read))
        self.assertEqual((stages['readback']['state'], stages['readback']['reason']), ('unknown', 'maintenance_service_incomplete'))
        self.assertEqual(stages['reconcile']['state'], 'done')
        self.assertEqual([name for name, stage in stages.items() if stage['continuation']], [])
        # While the reconcile itself is still pending the stage waits, with Delivery's own step.
        delivery['stages'][5] = stage_row('reconciliation', 'pending', classification='matches_precondition',
                                          previous_status='outcome_unknown', count=1)
        read = with_operation(baseline(), delivery=delivery, journal='outcome_unknown',
                              review=prepared_review('open', status='outcome_unknown'))
        stages = by_id(project(read))
        self.assertEqual((stages['readback']['state'], stages['reconcile']['state']), ('waiting', 'waiting'))

    def test_deliverys_step_for_a_record_that_cannot_be_made_belongs_to_the_record_stage(self):
        delivery = executed_delivery('reconciled')
        read = with_operation(baseline(), delivery=delivery, journal='reconciled',
                              review=prepared_review('open', status='reconciled'))
        stages = by_id(project(read))
        self.assertEqual((stages['record']['state'], stages['record']['reason']), ('not_applicable', 'no_verified_readback'))
        self.assertEqual(stages['record']['continuation'], NO_RECORD_STEP)
        self.assertIsNone(stages['observed_after']['continuation'])
        # The observation after the change keeps no step Delivery never gave for it.
        delivery['stages'][7] = stage_row('observed_after', 'differs', service_revision=2)
        read = with_operation(baseline(), delivery=delivery, journal='reconciled',
                              review=prepared_review('open', status='reconciled'))
        stages = by_id(project(read))
        self.assertEqual((stages['observed_after']['state'], stages['observed_after']['continuation']), ('blocked', None))
        self.assertEqual(stages['record']['continuation'], NO_RECORD_STEP)

    def test_a_value_outside_the_set_a_record_can_hold_reads_as_unknown_and_invents_no_reason(self):
        read = baseline()
        read['states'].pop('observation')
        stage = by_id(project(read))['observe']
        self.assertEqual((stage['state'], stage['basis'], stage['reason']), ('not_recorded', 'states.observation', None))
        read = baseline()
        read['states']['observation']['freshness'] = 'unrecognised'
        stage = by_id(project(read))['observe']
        self.assertEqual((stage['state'], stage['reason']), ('unknown', None))
        # A delivery stage whose status is outside its set is unknown, and its reason is that status, as recorded.
        for index, name, key in ((2, 'approval', 'approve_execute'), (5, 'reconciliation', 'reconcile'),
                                 (6, 'deployment_record', 'record')):
            delivery = prepared_delivery() if name == 'approval' else executed_delivery('reconciled')
            delivery['stages'][index] = stage_row(name, 'unrecognised')
            journal = delivery['journal_status']
            read = with_operation(baseline(), delivery=delivery, journal=journal, review=prepared_review('open', status=journal))
            stage = by_id(project(read))[key]
            self.assertEqual((stage['state'], stage['reason']), ('unknown', 'unrecognised'), name)


class ReviewStoreTests(LayerFixture):
    def flow(self):
        from intune_iac import workbench
        return project(workbench._workflow_read(self.store, OBJECT, service_root=self.service.root))

    def test_a_delay_in_the_services_visibility_then_a_reconcile_leaves_the_execution_unknown_and_no_stale_step(self):
        from intune_iac import maintenance
        review = self.prepare()
        maintenance.execute(self.operation, approve_digest=review['approval_digest'], visibility_delay_reads=1)
        stages = by_id(self.flow())
        self.assertEqual((stages['readback']['state'], stages['readback']['reason']), ('waiting', 'visibility_pending'))
        self.assertEqual(stages['reconcile']['state'], 'current')
        maintenance.reconcile(self.operation)               # the service shows the change now
        flow = self.flow()
        stages = by_id(flow)
        self.assertEqual((stages['readback']['state'], stages['readback']['reason']),
                         ('unknown', 'maintenance_visibility_pending'))
        self.assertEqual((stages['reconcile']['state'], stages['reconcile']['reason']), ('done', 'desired_state_observed'))
        # The execution moved the service, so the observation is blocked and carries its own step (collect again); nothing
        # else keeps a step, and in particular not the stale reconcile step.
        self.assertEqual([name for name, stage in stages.items() if stage['continuation']], ['observe'])
        # The reconcile is done and the record cannot be made (the readback never verified): that is where the records
        # put the policy, an outcome the records show after dispatch.
        self.assertEqual((stages['record']['state'], flow['position']), ('not_applicable', 'record'))

    def test_after_a_lost_response_and_a_reconcile_the_step_is_deliverys_collect_on_the_record_stage(self):
        from intune_iac import maintenance
        review = self.prepare()
        maintenance.execute(self.operation, approve_digest=review['approval_digest'], fault='lost-response')
        maintenance.reconcile(self.operation)
        stages = by_id(self.flow())
        from intune_iac.workbench_screens import ELIGIBILITY_FINDINGS
        self.assertEqual({name: stage['continuation'] for name, stage in stages.items() if stage['continuation']},
                         {'observe': ELIGIBILITY_FINDINGS['service_changed'][1], 'record': NO_RECORD_STEP})

    def test_enter_on_propose_or_review_without_an_operation_opens_the_plan_list_the_surface_the_row_names(self):
        self.import_intent()
        for stage in ('propose', 'review'):
            ws = self.layer_workspace(focus=stage)
            self.assertIn('Enter opens 5 Plan', '\n'.join(str(row) for row in ws._workflow_lines(112)))
            self.assertEqual(self.press(ws, 'enter'), 'operations', stage)
            self.assertEqual((ws.tab, ws.selected), (4, OBJECT), stage)

    def test_a_new_open_starts_at_the_position_and_a_return_from_a_surface_keeps_the_focus(self):
        self.prepare()
        key = lambda char: ('text', char)
        select, opened = typed('select ' + OBJECT), typed('workflow')
        sequence = select + opened + ['up', 'up', 'enter', key('b')] + ['escape'] + opened + [key('q')]
        ws, _ = self.run_keys(sequence)
        at = len(select) + len(opened)
        self.assertEqual(ws.states[at + 2]['focus'], 'propose')                          # moved two up from the position
        self.assertEqual((ws.states[at + 4]['layer'], ws.states[at + 4]['focus']), ('workflow', 'propose'))   # b: same focus
        # Esc, then the command again: a new open, so the focus is the position the records give.
        again = at + 5 + len(opened)
        self.assertEqual((ws.states[again]['layer'], ws.states[again]['focus']), ('workflow', None))

    def test_leaving_the_layer_by_another_route_forgets_the_view_it_was_opened_from(self):
        self.prepare()
        key = lambda char: ('text', char)
        # The Inspector (command inspect), scrolled; the layer over it; Plan by its number key; then the Inspector again.
        before = [key('1'), 'enter', key('2'), 'pagedown']
        sequence = before + typed('workflow') + [key('5'), key('2'), key('q')]
        ws, _ = self.run_keys(sequence, (80, 24))
        self.assertGreater(ws.states[len(before)]['scroll'], 0)                  # the Inspector was scrolled
        self.assertEqual(ws.states[-1]['tab'], 1)
        self.assertEqual(ws.states[-1]['scroll'], 0)             # it is a new visit, not the return the layer promised

    def test_a_in_the_layer_says_the_actions_wait_for_esc_and_e_r_and_f_say_read_only(self):
        self.prepare()
        ws = self.layer_workspace()
        self.assertIsNone(self.press(ws, ('text', 'a')))
        self.assertIn('Esc closes it, then a lists the actions', ws.notice)
        for char in ('e', 'r', 'f'):
            self.assertIsNone(self.press(ws, ('text', char)))
            self.assertEqual(ws.notice, 'The workflow map is read-only; Esc closes it.', char)

    def test_esc_with_no_view_before_the_layer_returns_to_the_estate_overview(self):
        self.prepare()
        ws = self.layer_workspace()
        self.assertEqual(self.press(ws, 'escape'), 'overview')
        self.assertEqual(ws.layer, 'summary')

    def test_a_layer_with_nothing_loaded_says_so_and_a_window_below_the_minimum_says_it_needs_a_larger_one(self):
        self.prepare()
        ws = self.layer_workspace()
        ws.value = {}
        self.assertIn('No workflow map is loaded', ' '.join(str(row) for row in ws._workflow_lines(80)))
        small = self.layer_workspace(size=(50, 15))
        self.assertIn('needs a larger window', ' '.join(str(row) for row in small._workflow_lines(50)))


class ReviewTextTests(unittest.TestCase):
    def test_the_text_form_has_no_keyboard_marks_and_names_its_marks_in_words(self):
        from intune_iac.workbench_screens import MapLine, workflow_map_lines, workflow_text_lines
        for rules in ('ascii', 'unicode'):
            flow = flows()['unknown']
            lines = workflow_text_lines(flow, 80, rules)
            text = '\n'.join(str(line) for line in lines)
            self.assertNotIn('? help', text)                          # there is no ? in a pipe
            self.assertNotIn('> focus', text)
            lanes = [str(row) for row in workflow_map_lines(flow, 80, rules, detail=False, keyboard=False)
                     if isinstance(row, MapLine)]
            self.assertEqual(len(lanes), 11)
            self.assertTrue(all(lane.rstrip() in lines for lane in lanes), lanes)   # the text form prints those very lanes
            self.assertFalse(any(row.startswith('>') for row in lanes), lanes)     # the position is @, nothing is focused
            self.assertEqual([row[:2].strip() for row in lanes if row[:2].strip()], ['@'])
            flat = ' '.join(text.split())
            for item in ('[x] done', '[+] current', '[:] waiting', '[!] blocked', '[#] refused', '[?] unknown',
                         '[_] not recorded', '[-] not applicable', '@ position'):
                self.assertEqual(sum(item in line for line in text.splitlines()), 1, (rules, item))
            self.assertIn('@ position', flat)
            self.assertTrue(all(len(line) <= 80 for line in text.splitlines()))

    def test_no_line_of_the_text_form_ends_in_a_space_so_it_pastes_and_diffs_clean(self):
        from intune_iac.workbench_screens import workflow_text_lines
        for width in (80, 50, 36):
            for rules in ('ascii', 'unicode'):
                for name, flow in flows().items():
                    padded = [line for line in workflow_text_lines(flow, width, rules) if line != line.rstrip()]
                    self.assertEqual(padded, [], (width, rules, name))


class ReviewInvariantTests(unittest.TestCase):
    """Delivery's own order decides which stage a step belongs to; compare with its real _next_step over every combination."""
    APPROVAL = ('done', 'waiting', 'expired', 'clock_unreadable', 'clock_uncertain', 'not_open', 'rejected')
    EXECUTION = ('not_started', 'done', 'unknown')
    READBACK = ('not_started', 'not_recorded', 'pending', 'failed', 'done')
    RECONCILIATION = ('not_needed', 'required', 'pending', 'done')
    RECORD = (('not_yet', None, False), ('available', None, False), ('done', None, False), ('done', None, True),
              ('not_available', 'no_verified_readback', False), ('not_available', 'context_changed', False),
              ('not_applicable', 'no_repository_intent_cited', False))
    OBSERVED = ('not_yet', 'matches_desired', 'differs', 'unknown', 'not_applicable')

    @staticmethod
    def journal_for(approval, execution, reconciliation):
        if approval == 'rejected':
            return 'rejected'
        if execution == 'unknown':
            return 'reconciled' if reconciliation == 'done' else 'outcome_unknown'
        return 'succeeded_verified' if execution == 'done' else 'prepared'

    def combinations(self):
        import itertools
        for approval, execution, readback, reconciliation, record, observed in itertools.product(
                self.APPROVAL, self.EXECUTION, self.READBACK, self.RECONCILIATION, self.RECORD, self.OBSERVED):
            for proposal_changed in ((False, True) if approval == 'waiting' else (False,)):
                status, reason, context = record
                delivery = prepared_delivery()
                delivery['journal_status'] = self.journal_for(approval, execution, reconciliation)
                delivery['stages'][0]['context_changed'] = proposal_changed
                delivery['stages'][2] = stage_row('approval', approval, opens_at=1, closes_at=2)
                delivery['stages'][3] = stage_row('execution', execution, error_code='some_code' if execution == 'unknown' else None)
                delivery['stages'][4] = stage_row('readback', readback, classification='desired_state_observed')
                delivery['stages'][5] = stage_row('reconciliation', reconciliation, classification='desired_state_observed')
                delivery['stages'][6] = stage_row('deployment_record', status, reason=reason, intent_id='e9274102',
                                                  **({'context_changed': True} if context else {}))
                delivery['stages'][7] = stage_row('observed_after', observed, observation_freshness='fresh')
                yield (approval, execution, readback, reconciliation, record, observed, proposal_changed), delivery

    @staticmethod
    def branch(sentence):
        """Which stage a Delivery sentence is about, from its words."""
        if sentence.startswith('Nothing pending'):
            return 'none'
        if sentence == 'Collect to observe the policy after the change.' or sentence.startswith('The latest observation'):
            return 'observed_after'
        if ('deployment record' in sentence or sentence.startswith('Record the deployment')
                or sentence.startswith('The deployment of')):
            return 'record'
        return 'earlier'

    def test_the_stage_that_carries_deliverys_step_is_the_one_deliverys_own_order_gives_it_to(self):
        from intune_iac.workbench_delivery import _next_step
        count = carried = 0
        for key, delivery in self.combinations():
            named = {stage['stage']: stage for stage in delivery['stages']}
            sentence = _next_step(named, '/w/operation', '/w/store')
            delivery['next_action'] = sentence
            journal = delivery['journal_status']
            flow = project(with_operation(baseline(), delivery=delivery, journal=journal,
                                          review=prepared_review('open', status=journal)))
            owners = [stage['id'] for stage in flow['stages'] if stage['continuation'] == sentence]
            count += 1
            carried += bool(owners)
            expected = self.branch(sentence)
            if expected == 'none':
                self.assertEqual(owners, [], (key, sentence))
            elif expected in ('record', 'observed_after'):
                self.assertEqual(owners, [expected], (key, sentence))
            else:
                self.assertTrue(all(owner not in ('record', 'observed_after') for owner in owners), (key, owners, sentence))
        self.assertGreater(count, 14000)
        self.assertGreater(carried, 1000)

    def test_the_position_is_the_last_stage_with_a_recorded_state_and_the_branch_follows_its_outcome(self):
        for key, delivery in self.combinations():
            approval, execution, readback, reconciliation, record, observed, proposal_changed = key
            journal = delivery['journal_status']
            flow = project(with_operation(baseline(), delivery=delivery, journal=journal,
                                          review=prepared_review('open', status=journal)))
            stages = by_id(flow)
            # Recorded: any state but not recorded, and a stage that does not apply only where the records show it
            # after dispatch (the record that cannot be made, the observation after a plan with no change).
            dispatched = execution in ('done', 'unknown')
            reached = [stage['id'] for stage in flow['stages'] if stage['state'] != 'not_recorded'
                       and (stage['state'] != 'not_applicable' or (stage['id'] in ('record', 'observed_after') and dispatched))]
            self.assertEqual(flow['position'], reached[-1], key)
            # The reconcile branch is not applicable exactly when no reconciliation was needed, and present otherwise.
            self.assertEqual(stages['reconcile']['state'] == 'not_applicable', reconciliation == 'not_needed', key)
            if reconciliation in ('required', 'pending', 'done'):
                self.assertIn(stages['reconcile']['state'], ('current', 'waiting', 'done', 'blocked'), key)
            # The context a plan or its record was bound to changed: neither the approval nor the record reads as done.
            if proposal_changed:
                self.assertEqual(stages['approve_execute']['state'], 'blocked', key)
            if record[2]:
                self.assertEqual(stages['record']['state'], 'blocked', key)
                self.assertEqual(stages['record']['reason'], 'context_changed', key)


class ReviewReadOnlyTests(LayerFixture):
    """The write-nothing guarantee holds for every operation state, not only a prepared one."""

    def tree(self):
        import hashlib
        from pathlib import Path
        names = ('observations.sqlite3', 'observations.sqlite3-wal', 'observations.sqlite3-shm')
        files = [Path(self.store.root) / name for name in names]
        files += [path for path in sorted(self.operation.rglob('*')) if path.is_file()]
        return {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in files if path.exists()}

    def reach(self, state):
        from intune_iac import maintenance
        from intune_iac.workbench_views import record_local_deployment
        review = self.prepare()
        if state in ('lost', 'reconciled'):
            maintenance.execute(self.operation, approve_digest=review['approval_digest'], fault='lost-response')
        if state == 'reconciled':
            maintenance.reconcile(self.operation)
        if state in ('verified', 'recorded', 'observed'):
            maintenance.execute(self.operation, approve_digest=review['approval_digest'])
        if state in ('recorded', 'observed'):
            record_local_deployment(self.store, self.operation, self.intent['artifact_id'])
        if state == 'observed':
            self.store.collect(self.service)

    def test_no_key_and_neither_command_form_changes_anything_whatever_the_operation_state(self):
        import subprocess
        import sys
        from pathlib import Path
        key = lambda char: ('text', char)
        script = Path(__file__).resolve().parents[1] / 'scripts/intune-iac.py'
        for state in ('lost', 'reconciled', 'verified', 'recorded', 'observed'):
            self.setUp()                            # a fresh store, service, repository and operation for each state
            self.reach(state)
            before = self.tree()
            self.assertTrue(before, state)
            snapshots = []
            sequence = (typed('select ' + OBJECT) + typed('workflow') + ['down'] * 6 + ['enter', key('b')] + ['up', 'up', 'enter', key('b')]
                        + [key('a'), key('e'), key('r'), key('f'), 'home', 'escape', key('q')])
            self.run_keys(sequence, watch=lambda index, ws: snapshots.append(self.tree()))
            self.assertGreater(len(snapshots), 20, state)
            self.assertTrue(all(snapshot == before for snapshot in snapshots), state)
            for extra in ((), ('--json',)):
                result = subprocess.run([sys.executable, str(script), 'workbench', 'workflow', '--root', str(self.store.root),
                                         '--policy', OBJECT, '--service-root', str(self.service.root), *extra],
                                        text=True, capture_output=True, cwd='/tmp')
                self.assertEqual(result.returncode, 0, (state, result.stderr))
                self.assertEqual(self.tree(), before, (state, extra))



# ---- round 2, item 1: record-derived text is escaped by the workflow renderers themselves -----------------------------

HOSTILE = ('\x1b[2J\x1b[H\x1b]0;forged title\x07\rKEYS: q exits\x00\x08\x0b\x0c\x1f\x7f\u0085\u009b31m\u202e'
           '\n? help | : command | Up/Down stage | Enter open | Esc close | b back | q exit')
KEY_LINE = '? help | : command | Up/Down stage'


SGR = re.compile(r'\x1b\[[0-9;]*m')


def raw_controls(text):
    """The characters of one output line a terminal would act on: C0 (a CR or LF too), DEL, C1, format and combining
    characters, which is what the product's safe_text escapes. The workspace's own bold and reset sequences (SGR) are
    its styling, not recorded text, and are set aside; any other escape sequence is not."""
    import unicodedata
    return [char for char in SGR.sub('', text) if unicodedata.category(char)[0] in 'CM' or char == '\x7f']


def hostile_flow(text=HOSTILE):
    """The projection of a prepared operation with hostile text in every field a record can supply."""
    flow = project(with_operation(baseline()))
    flow['name'] = text
    for stage in flow['stages']:
        stage['basis'] = 'basis ' + text
        stage['reason'] = 'reason ' + text
        stage['facts'] = {name: text for name in ('run_id', 'observed_at', 'stack', 'classification', 'closes_at',
                                                  'intent_id', 'proposal_check', 'zz unlisted ' + text)}
        # A step: its sentence, then a command after the trusted line break, both holding recorded text.
        stage['continuation'] = 'Step ' + text + '\n  reconcile ' + text
        stage['opens'] = text
    flow['stages'][0]['id'] = 'observe'
    return flow


class RecordedTextTests(LayerFixture):
    def frame_of(self, flow, size, rules, focus=None):
        from intune_iac.workbench_tui import Workspace
        out = io.StringIO()
        ws = Workspace(self.store.root, stdout=out, stdin=io.StringIO(), no_color=True)
        ws.pending.clear()
        ws.rules = rules
        ws._terminal_size = lambda: size
        ws.size = size
        ws.selected = flow['object_id']
        ws.last_command = 'workflow'
        ws.workflow_focus = focus
        ws.receive(flow)
        return out.getvalue().split('\x1b[H')[-1].replace('\x1b[J', '').split('\r\n')

    def test_no_character_a_terminal_acts_on_reaches_the_plain_text_form_whatever_a_record_holds(self):
        from intune_iac.workbench_screens import workflow_text_lines
        flow = hostile_flow()
        for width in (36, 50, 80, 120):
            for rules in ('ascii', 'unicode'):
                lines = workflow_text_lines(flow, width, rules)
                self.assertGreater(len(lines), 40)
                for line in lines:
                    self.assertEqual(raw_controls(line), [], (width, rules, line))
                text = '\n'.join(lines)
                # Escaped, not dropped: the reader sees what the record holds.
                self.assertIn('\\u001b[2J', text)
                self.assertIn('\\r', text)

    def test_no_character_a_terminal_acts_on_reaches_the_layer_frame_and_no_key_line_is_forged(self):
        flow = hostile_flow()
        for size in ((120, 40), (80, 24), (60, 20)):
            for rules in ('ascii', 'unicode'):
                for focus in IDS:
                    frame = self.frame_of(flow, size, rules, focus)
                    self.assertEqual(len(frame), size[1], (size, rules, focus))
                    for row in frame:
                        self.assertEqual(raw_controls(row), [], (size, rules, focus, row))
                    # The one key line is the frame's own last row; recorded text inside the pane never starts a row of it.
                    self.assertEqual([index for index, row in enumerate(frame) if row.startswith('? help |')],
                                     [len(frame) - 1] if frame[-1].startswith('? help |') else [], (size, rules, focus))

    def test_the_renderers_escape_for_themselves_and_do_not_lean_on_the_wrapper_doing_it(self):
        from intune_iac import workbench_screens as screens
        flow = hostile_flow()
        raw_wrap = lambda value, width: [str(value)]       # a wrapper that escapes nothing
        with mock.patch.object(screens, 'word_wrap', side_effect=raw_wrap):
            for rules in ('ascii', 'unicode'):
                lines = [str(row) for row in screens.workflow_text_lines(flow, 80, rules)]
                lines += [str(row) for focus in IDS for row in screens.workflow_map_lines(flow, 100, rules, focus=focus)]
                for line in lines:
                    self.assertEqual(raw_controls(line), [], (rules, line))

    def test_a_line_or_paragraph_separator_in_a_record_makes_no_row_in_the_plain_text_form_or_the_layer(self):
        from intune_iac.workbench_screens import workflow_text_lines

        def compared(text):
            # short_id cuts a recorded identity to eight characters before it is escaped, so that one fact would differ between
            # a separator and its six-character spelling; the comparison with the spelled text leaves it out.
            flow = hostile_flow(text)
            for stage in flow['stages']:
                stage['facts'].pop('intent_id')
            return flow
        flow = hostile_flow(SEPARATED)
        for width in (36, 50, 80, 120):
            for rules in ('ascii', 'unicode'):
                lines = workflow_text_lines(flow, width, rules)
                text = '\n'.join(lines)
                for separator in SEPARATORS:
                    self.assertNotIn(separator, text, (width, rules))
                # A splitlines() consumer sees exactly the rows the output has: no row starts where a separator was.
                self.assertEqual(len(text.splitlines()), len(lines), (width, rules))
                self.assertEqual(workflow_text_lines(compared(SEPARATED), width, rules),
                                 workflow_text_lines(compared(SPELLED), width, rules), (width, rules))
        for size in ((120, 40), (80, 24), (60, 20)):
            for rules in ('ascii', 'unicode'):
                for focus in IDS:
                    frame = self.frame_of(flow, size, rules, focus)
                    self.assertEqual(len(frame), size[1], (size, rules, focus))
                    for row in frame:
                        for separator in SEPARATORS:
                            self.assertNotIn(separator, row, (size, rules, focus))
                        self.assertLessEqual(len(row.splitlines()), 1, (size, rules, focus, row))
                    self.assertEqual(self.frame_of(compared(SEPARATED), size, rules, focus),
                                     self.frame_of(compared(SPELLED), size, rules, focus), (size, rules, focus))


class RecordedNameFixture(LayerFixture):
    """A store whose policy carries a hostile name from the collection onward."""
    NAME = HOSTILE

    def setUp(self):
        import json
        import shutil
        import tempfile
        from pathlib import Path
        from intune_iac.engine import generate
        from intune_iac.modeled_service import ModeledService
        from intune_iac.workbench_store import WorkbenchStore
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(repository_tests.ROOT)
        self.root = Path(temp.name)
        generate(root / 'examples/supported/input/export.json', root / 'examples/context.json', self.root / 'generated')
        self.repo = self.root / 'repository'
        shutil.copytree(self.root / 'generated', self.repo)
        capture = json.loads((root / 'examples/supported/input/export.json').read_text())
        for item in capture['collections'][0]['pages'][0]['body']['value']:
            if item.get('id') == OBJECT:
                item['name'] = self.NAME
        self.service = ModeledService.create(self.root / 'service', capture, [OBJECT])
        self.store = WorkbenchStore.create(self.root / 'store', TENANT)
        self.store.collect(self.service)


class StoredNameTests(RecordedNameFixture):
    def test_a_stored_hostile_name_is_kept_exactly_in_the_data_form_and_escaped_in_every_text_form(self):
        import json
        import subprocess
        import sys
        from pathlib import Path
        from intune_iac import workbench
        self.assertEqual(workbench._workflow(self.store, OBJECT, service_root=self.service.root)['name'], HOSTILE)
        script = Path(__file__).resolve().parents[1] / 'scripts/intune-iac.py'
        command = [sys.executable, str(script), 'workbench', 'workflow', '--root', str(self.store.root), '--policy', OBJECT,
                   '--service-root', str(self.service.root)]
        piped = subprocess.run(command, capture_output=True, cwd='/tmp')
        self.assertEqual(piped.returncode, 0, piped.stderr)
        for line in piped.stdout.decode('utf-8').split('\n'):
            self.assertEqual(raw_controls(line), [], line)
        self.assertNotIn(b'\x1b', piped.stdout)
        self.assertNotIn(b'\r', piped.stdout)
        data = subprocess.run(command + ['--json'], capture_output=True, cwd='/tmp')
        self.assertEqual(data.returncode, 0, data.stderr)
        self.assertTrue(all(byte < 0x80 for byte in data.stdout))          # ensure_ascii: nothing a terminal acts on
        self.assertEqual(json.loads(data.stdout)['name'], HOSTILE)

    def test_a_stored_hostile_name_reaches_no_frame_of_the_layer_as_a_character_a_terminal_acts_on(self):
        key = lambda char: ('text', char)
        for size, rules in (((120, 40), 'unicode'), ((80, 24), 'ascii')):
            ws, frames = self.run_keys(typed('select ' + OBJECT) + typed('workflow') + ['down'] * 3 + [key('q')], size, rules)
            self.assertEqual(ws.states[-1]['layer'], 'workflow')
            frame = frames[-1]
            self.assertEqual(len(frame), size[1])
            for row in frame:
                self.assertEqual(raw_controls(row), [], (size, rules, row))



# ---- round 2, item 2: the position follows durable evidence, apart from the semantic state ----------------------------

def delivery_of(journal, **stages):
    """prepared_delivery with the named stages replaced (by stage name) and the journal status as given."""
    delivery = prepared_delivery()
    delivery['journal_status'] = journal
    delivery['stages'] = [stages.get(stage['stage'], stage) for stage in delivery['stages']]
    return delivery


def verified_stages(**changes):
    stages = {'approval': stage_row('approval', 'done', opens_at=1_792_000_000, closes_at=1_792_000_300),
              'execution': stage_row('execution', 'done'),
              'readback': stage_row('readback', 'done', classification='desired_state_observed'),
              'reconciliation': stage_row('reconciliation', 'not_needed')}
    stages.update(changes)
    return stages


def position_of(delivery):
    journal = delivery['journal_status']
    read = with_operation(baseline(), delivery=delivery, journal=journal, review=prepared_review('open', status=journal))
    flow = project(read)
    return flow['position'], states_of(flow)


class PositionEvidenceTests(unittest.TestCase):
    def test_a_record_that_cannot_be_made_is_where_the_records_put_the_policy_after_a_reconcile(self):
        position, states = position_of(executed_delivery('reconciled'))
        self.assertEqual((states['reconcile'], states['record']), ('done', 'not_applicable'))
        self.assertEqual(position, 'record')

    def test_a_record_that_does_not_apply_marks_the_position_once_the_change_was_dispatched_and_not_before(self):
        # Dispatched and verified, no repository intent cited: the record stage is decided, the observation after is not yet.
        delivery = delivery_of('succeeded_verified', **verified_stages(
            deployment_record=stage_row('deployment_record', 'not_applicable', reason='no_repository_intent_cited')))
        position, states = position_of(delivery)
        self.assertEqual((states['record'], states['observed_after']), ('not_applicable', 'not_recorded'))
        self.assertEqual(position, 'record')
        # Prepared and not yet approved: the plan cited no intent, which says nothing of how far the change has got.
        delivery = prepared_delivery()
        delivery['stages'][6] = stage_row('deployment_record', 'not_applicable', reason='no_repository_intent_cited')
        position, states = position_of(delivery)
        self.assertEqual((states['record'], position), ('not_applicable', 'approve_execute'))

    def test_an_observation_after_that_the_plan_made_not_applicable_marks_the_position_and_only_after_dispatch(self):
        delivery = delivery_of('succeeded_verified', **verified_stages(
            observed_after=stage_row('observed_after', 'not_applicable', reason='no_configuration_change')))
        position, states = position_of(delivery)
        self.assertEqual((states['record'], states['observed_after']), ('not_recorded', 'not_applicable'))
        self.assertEqual(position, 'observed_after')
        # Not dispatched: nothing recorded for it, whatever the stage word says.
        delivery = prepared_delivery()
        delivery['stages'][7] = stage_row('observed_after', 'not_applicable', reason='no_configuration_change')
        self.assertEqual(position_of(delivery)[0], 'approve_execute')

    def test_a_reconcile_that_was_never_needed_is_no_place_the_policy_has_got_to(self):
        position, states = position_of(delivery_of('succeeded_verified', **verified_stages()))
        self.assertEqual((states['reconcile'], states['record'], states['observed_after']),
                         ('not_applicable', 'not_recorded', 'not_recorded'))
        self.assertEqual(position, 'readback')

    def test_a_stage_whose_evidence_could_not_be_read_is_no_place_either(self):
        read = with_operation(baseline(), delivery={'error_code': 'maintenance_evidence_changed'},
                              review={'error_code': 'maintenance_evidence_changed'})
        flow = project(read)
        stages = by_id(flow)
        self.assertEqual((stages['review']['state'], stages['record']['state']), ('unknown', 'unknown'))
        self.assertEqual(flow['position'], 'propose')

    def test_the_evidence_flag_is_not_part_of_the_projection(self):
        flow = project(with_operation(baseline()))
        self.assertEqual(set(flow['stages'][0]), {'id', 'state', 'basis', 'reason', 'facts', 'opens', 'continuation', 'branch_of'})



# ---- round 2, item 3: a classification outside the producer's closed sets is unknown, never done ----------------------

class ClassificationTests(unittest.TestCase):
    def reconciled(self, **reconciliation):
        delivery = executed_delivery('reconciled')
        delivery['stages'][5] = stage_row('reconciliation', 'done', previous_status='outcome_unknown', count=1, **reconciliation)
        return by_id(project(with_operation(baseline(), delivery=delivery, journal='reconciled',
                                            review=prepared_review('open', status='reconciled'))))

    def verified(self, **readback):
        delivery = delivery_of('succeeded_verified', **verified_stages(readback=stage_row('readback', 'done', **readback)))
        return by_id(project(with_operation(baseline(), delivery=delivery, journal='succeeded_verified',
                                            review=prepared_review('open', status='succeeded_verified'))))

    def test_the_producers_closed_set_is_the_one_the_projection_checks_against(self):
        import inspect
        from intune_iac import maintenance, workflow_projection
        line = next(row for row in inspect.getsource(maintenance._readback).splitlines()
                    if row.strip().startswith('classification ='))
        self.assertEqual(set(re.findall(r"'([a-z_]+)'", line)), set(workflow_projection.READBACK_CLASSES))
        # Execute records `verified` for the first of them only.
        self.assertIn("readback['classification'] != 'desired_state_observed'", inspect.getsource(maintenance._execute))
        self.assertEqual(workflow_projection.VERIFIED_CLASSES, ('desired_state_observed',))

    def test_a_reconcile_done_under_a_recognized_classification_reads_as_the_producer_classified_it(self):
        for classification, state in (('desired_state_observed', 'done'), ('matches_precondition', 'done'), ('diverged', 'blocked')):
            stage = self.reconciled(classification=classification)['reconcile']
            self.assertEqual((stage['state'], stage['reason']), (state, classification), classification)

    def test_a_reconcile_done_under_a_missing_or_unrecognized_classification_is_unknown(self):
        for classification in ('outcome_unknown', 'succeeded_verified', 'surprise', '', None):
            stage = self.reconciled(classification=classification)['reconcile']
            self.assertEqual(stage['state'], 'unknown', classification)
            self.assertEqual(stage['reason'], classification or None, classification)
            self.assertEqual(stage['basis'], 'operation %s delivery stage reconciliation' % OPERATION[:8], classification)

    def test_a_readback_done_is_done_only_under_the_classification_execute_verifies_with(self):
        stage = self.verified(classification='desired_state_observed')['readback']
        self.assertEqual((stage['state'], stage['reason']), ('done', 'desired_state_observed'))
        for classification in ('matches_precondition', 'diverged', 'outcome_unknown', 'surprise', '', None):
            stages = self.verified(classification=classification)
            self.assertEqual(stages['readback']['state'], 'unknown', classification)
            self.assertEqual(stages['readback']['reason'], classification or None, classification)
            # No later stage reads as complete on a readback that is not a recorded success.
            self.assertEqual(stages['maintain']['state'], 'not_recorded', classification)

    def test_the_other_readback_statuses_and_the_reconcile_in_progress_are_unchanged(self):
        delivery = executed_delivery('reconciled')
        delivery['stages'][5] = stage_row('reconciliation', 'pending', classification='matches_precondition',
                                          previous_status='outcome_unknown', count=1)
        stages = by_id(project(with_operation(baseline(), delivery=delivery, journal='outcome_unknown',
                                              review=prepared_review('open', status='outcome_unknown'))))
        self.assertEqual((stages['reconcile']['state'], stages['reconcile']['reason']), ('waiting', 'visibility_pending'))



# ---- round 2, item 4: done needs the durable identifier or field its basis names -------------------------------------------

ARTIFACT = 'c8c5a140' + '0123456789abcdef' * 3 + '01234567'        # a content digest, as the store names an artifact


class EvidenceBasisTests(unittest.TestCase):
    def adopt(self, adoptions):
        read = baseline()
        read['adoptions'] = adoptions
        return by_id(project(read))['adopt']

    def test_adopt_is_done_only_on_a_record_that_names_its_durable_identifier(self):
        stage = self.adopt([{'artifact_id': ARTIFACT, 'sequence': 3, 'recorded_at': '2026-10-14T19:40:00.000001Z'}])
        self.assertEqual((stage['state'], stage['basis']), ('done', 'adoption record c8c5a140'))
        self.assertEqual(stage['facts'], {'recorded_at': '2026-10-14T19:40:00.000001Z'})
        for absent in ([], None):
            self.assertEqual(self.adopt(absent)['state'], 'not_recorded', absent)
        for malformed in ([{}], [{'sequence': 1}], [{'artifact_id': ''}], [{'artifact_id': 7}], [None], ['text'], 'junk', {'a': 1}):
            stage = self.adopt(malformed)
            self.assertEqual((stage['state'], stage['basis']), ('unknown', 'adoption records for this policy'), malformed)

    def test_a_malformed_adoption_record_beside_a_usable_one_does_not_hide_it_and_the_newest_usable_one_is_the_basis(self):
        older = {'artifact_id': 'a1b2c3d4' + '0' * 56, 'sequence': 1}
        newer = {'artifact_id': ARTIFACT, 'sequence': 2}
        for rows in ([{}, older, newer], [newer, older, {'sequence': 9}]):
            stage = self.adopt(rows)
            self.assertEqual((stage['state'], stage['basis']), ('done', 'adoption record c8c5a140'), rows)

    def test_malformed_adoption_evidence_is_no_place_the_policy_has_got_to(self):
        read = baseline()
        read['states']['intent'] = None
        read['adoptions'] = [{}]
        flow = project(read)
        self.assertEqual(by_id(flow)['adopt']['state'], 'unknown')
        self.assertEqual(flow['position'], 'observe')

    def proposal(self, mutate=None, delivery='keep'):
        read = with_operation(baseline())
        if delivery != 'keep':
            read['delivery'] = delivery
        if mutate:
            mutate(read)
        return by_id(project(read))['propose']

    def test_propose_is_done_on_the_delivery_proposal_stage_with_its_recorded_facts(self):
        stage = self.proposal()
        self.assertEqual((stage['state'], stage['basis']), ('done', 'operation %s delivery stage proposal' % OPERATION[:8]))
        self.assertEqual(stage['facts']['repository_intent_id'], 'e9274102')

    def test_without_the_proposal_stage_the_operation_record_is_the_basis_and_it_needs_the_fields_it_names(self):
        unreadable = {'error_code': 'maintenance_evidence_changed'}
        stage = self.proposal(delivery=unreadable)
        self.assertEqual((stage['state'], stage['basis']), ('done', 'operation %s status' % OPERATION[:8]))
        self.assertEqual(stage['facts'], {'recorded_at': '2026-10-14T19:55:00.5Z'})
        for field in ('status', 'operation_id'):
            stage = self.proposal(lambda read: read['states']['operation'].pop(field), delivery=unreadable)
            self.assertEqual((stage['state'], stage['basis']), ('unknown', 'states.operation'), field)
        for empty in ('', None, 7):
            stage = self.proposal(lambda read: read['states']['operation'].update(status=empty), delivery=unreadable)
            self.assertEqual(stage['state'], 'unknown', empty)

    def test_a_delivery_with_no_proposal_stage_falls_back_to_the_operation_record_and_never_claims_the_stage(self):
        def without_proposal(read):
            read['delivery']['stages'] = [row for row in read['delivery']['stages'] if row['stage'] != 'proposal']
        stage = self.proposal(without_proposal)
        self.assertEqual((stage['state'], stage['basis']), ('done', 'operation %s status' % OPERATION[:8]))
        stage = self.proposal(lambda read: (without_proposal(read), read['states']['operation'].pop('status')))
        self.assertEqual(stage['state'], 'unknown')

    def test_a_proposal_stage_that_is_not_done_is_unknown_and_says_what_it_recorded(self):
        def not_done(read):
            read['delivery']['stages'][0]['status'] = 'surprise'
        stage = self.proposal(not_done)
        self.assertEqual((stage['state'], stage['reason'], stage['basis']),
                         ('unknown', 'surprise', 'operation %s delivery stage proposal' % OPERATION[:8]))

    def test_an_operation_record_with_no_evidence_behind_propose_is_no_place_the_policy_has_got_to(self):
        read = with_operation(baseline(), delivery={'error_code': 'maintenance_evidence_changed'},
                              review={'error_code': 'maintenance_evidence_changed'})
        read['states']['operation'].pop('status')
        flow = project(read)
        self.assertEqual(by_id(flow)['propose']['state'], 'unknown')
        self.assertEqual(flow['position'], 'intent')



# ---- round 2, item 5: --service-root and a stored operation_root are opened by the engine's confining helpers ---------------

class ConfinementTests(LayerFixture):
    """The workflow map opens the service root and the operation root through the same functions the workspace's own read
    route does (maintenance._safe refuses a symlink anywhere in a path; the modeled service checks its own), and writes nothing."""

    def tree(self, *roots):
        import hashlib
        import os
        found = {}
        for root in roots:
            for here, folders, files in os.walk(root, followlinks=False):
                for name in folders + files:
                    path = os.path.join(here, name)
                    if os.path.islink(path):
                        found[path] = 'link to ' + os.readlink(path)
                    elif os.path.isdir(path):
                        found[path] = 'directory'
                    else:
                        with open(path, 'rb') as handle:
                            found[path] = hashlib.sha256(handle.read()).hexdigest()
        return found

    def cli(self, *extra):
        import json
        import subprocess
        import sys
        from pathlib import Path
        script = Path(__file__).resolve().parents[1] / 'scripts/intune-iac.py'
        result = subprocess.run([sys.executable, str(script), 'workbench', 'workflow', '--root', str(self.store.root),
                                 '--policy', OBJECT, '--json', *extra], capture_output=True, text=True, cwd='/tmp')
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def workspace(self, service_root, *commands):
        from intune_iac.workbench import run_terminal
        queue, results = iter(list(commands) + ['quit']), []
        run_terminal(self.store.root, service_root=str(service_root), input_fn=lambda _: next(queue), result_fn=results.append)
        return results

    def foreign_service(self):
        import json
        from pathlib import Path
        from intune_iac.modeled_service import ModeledService
        capture = json.loads((Path(repository_tests.ROOT) / 'examples/supported/input/export.json').read_text())
        capture['tenant_id'] = '99999999-9999-4999-8999-999999999999'
        return ModeledService.create(self.root / 'foreign-service', capture, [OBJECT])

    def test_a_service_root_that_is_a_symlink_or_another_tenants_is_refused_or_confined_as_the_workspace_does(self):
        import os
        self.prepare()
        foreign = self.foreign_service()
        link, parent = self.root / 'service-link', self.root / 'via-parent'
        os.symlink(self.service.root, link)                       # the service itself behind a link
        os.symlink(self.root, parent)                             # a real service under a symlinked ancestor
        cases = {'symlink': link, 'symlinked ancestor': parent / 'service', 'another tenant': foreign.root}
        watched = (self.store.root, self.service.root, self.operation, foreign.root)
        before, top = self.tree(*watched), sorted(os.listdir(self.root))
        for name, bad in cases.items():
            observe = by_id(self.cli('--service-root', str(bad)))['observe']
            results = self.workspace(bad, 'select ' + OBJECT, 'inspect', 'workflow')
            inspected = next(item for item in results if item.get('object_id') == OBJECT and 'observation_eligibility' in item)
            check = inspected['observation_eligibility']
            self.assertIsNotNone(check, name)                    # the proposal's own check did not pass, in the workspace too
            self.assertEqual(observe['reason'], check.get('reason') or check['code'], name)
            worked = by_id(next(item for item in results if item.get('schema_version') == 'workflow-map/1'))['observe']
            self.assertEqual({key: observe[key] for key in ('state', 'basis', 'reason')},
                             {key: worked[key] for key in ('state', 'basis', 'reason')}, name)
            if name == 'another tenant':
                self.assertEqual((observe['state'], observe['reason']), ('blocked', 'tenant_mismatch'))
            else:
                # Refused before anything was opened: the engine's own code, and the map says the check could not be made.
                self.assertEqual(check['code'], 'maintenance_unsafe_path', name)
                self.assertEqual((observe['state'], observe['facts']['proposal_check']), ('unknown', 'could not be made'), name)
        self.assertEqual(self.tree(*watched), before)
        self.assertEqual(sorted(os.listdir(self.root)), top)

    def test_a_stored_operation_root_that_is_a_symlink_is_refused_as_the_workspaces_own_review_refuses_it(self):
        import os
        import shlex
        self.prepare()
        real = self.root / 'operation-real'
        os.rename(self.operation, real)
        os.symlink(real, self.operation)                         # the path the store recorded is now a link
        watched = (self.store.root, self.service.root, real)
        before, top = self.tree(*watched), sorted(os.listdir(self.root))
        stages = by_id(self.cli('--service-root', str(self.service.root)))
        results = self.workspace(self.service.root, 'select ' + OBJECT, 'review ' + shlex.quote(str(self.operation)))
        refusal = next(item for item in results if item.get('status') == 'error')
        self.assertEqual(refusal['error']['code'], 'maintenance_unsafe_path')
        for name in ('review', 'approve_execute', 'readback', 'record', 'observed_after'):
            self.assertEqual((stages[name]['state'], stages[name]['reason']), ('unknown', 'maintenance_unsafe_path'), name)
        self.assertEqual(self.tree(*watched), before)
        self.assertEqual(sorted(os.listdir(self.root)), top)



class StoredRootTextTests(LayerFixture):
    def test_a_stored_operation_root_with_control_characters_reaches_no_text_line_or_frame_as_one(self):
        from intune_iac import workbench
        from intune_iac.workbench_repository import propose_from_intent, refresh_intent
        from intune_iac.workbench_screens import workflow_text_lines
        self.import_intent()
        self.edit_description('Edited in the repository.')
        refresh_intent(self.store, OBJECT, 'b' * 40)
        self.operation = self.root / 'operation\x1b[2J\x1b]0;forged\x07x\ry'
        propose_from_intent(self.store.root, self.service.root, OBJECT, self.operation)
        flow = workbench._workflow(self.store, OBJECT, service_root=self.service.root)
        self.assertIn('\x1b[2J', flow['operation']['operation_root'])          # the record holds the path exactly
        for width in (50, 80, 120):
            for line in workflow_text_lines(flow, width, 'unicode'):
                self.assertEqual(raw_controls(line), [], (width, line))
        key = lambda char: ('text', char)
        # Enter on the review stage (5 Plan) and on the approve stage (v Delivery) sends the stored root to a read view.
        for presses, command in ((['up'] * 2, 'review '), (['down'] * 0, 'delivery ')):
            ws, frames = self.run_keys(typed('select ' + OBJECT) + typed('workflow') + presses + ['enter', key('q')], (120, 40), 'unicode')
            self.assertTrue(any(sent.startswith(command) for sent in ws.sent), (command, ws.sent))
            for frame in frames:
                for row in frame:
                    self.assertEqual(raw_controls(row), [], (command, row))



# ---- round 3: the line and paragraph separators are escaped like every other control -------------------------------------

SEPARATED = 'policy\u2028Position: forged\u2029KEYS: q exits'
SPELLED = SEPARATED.replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')      # the same text with each separator spelled out
SEPARATORS = ('\u2028', '\u2029')


class SafeTextSeparatorTests(unittest.TestCase):
    def test_safe_text_escapes_the_line_and_paragraph_separators_in_the_form_it_uses_for_every_other_control(self):
        from intune_iac.workbench_tui import safe_text
        self.assertEqual(safe_text('a\u2028b'), 'a\\u2028b')
        self.assertEqual(safe_text('a\u2029b'), 'a\\u2029b')
        self.assertEqual(safe_text(SEPARATED), SPELLED)
        self.assertEqual(safe_text(SPELLED), SPELLED)               # escaping twice changes nothing

    def test_no_character_str_splitlines_breaks_on_survives_safe_text(self):
        from intune_iac.workbench_tui import safe_text
        breaks = ['\n', '\r', '\r\n', '\x0b', '\x0c', '\x1c', '\x1d', '\x1e', '\x85', '\u2028', '\u2029']
        text = safe_text('x'.join(breaks))
        self.assertEqual(text.splitlines(), [text])
        self.assertEqual(len(safe_text('policy\u2028Position: forged').splitlines()), 1)

    def test_the_whole_zl_and_zp_categories_are_those_two_characters_and_ordinary_text_is_untouched(self):
        import sys
        import unicodedata
        from intune_iac.workbench_tui import safe_text
        self.assertEqual([chr(n) for n in range(sys.maxunicode + 1) if unicodedata.category(chr(n)) in ('Zl', 'Zp')],
                         ['\u2028', '\u2029'])
        # Spaces (Zs), wide and accented text stay as they are.
        for kept in ('a\u00a0b', 'a\u2003b', 'a b', 'Windows Privacy Pilot', 'caf\u00e9 \u65e5\u672c'):
            self.assertEqual(safe_text(kept), kept)


class StoredSeparatorTests(RecordedNameFixture):
    NAME = SEPARATED

    def command(self):
        import sys
        from pathlib import Path
        script = Path(__file__).resolve().parents[1] / 'scripts/intune-iac.py'
        return [sys.executable, str(script), 'workbench', 'workflow', '--root', str(self.store.root), '--policy', OBJECT,
                '--service-root', str(self.service.root)]

    def test_a_stored_name_with_the_separators_makes_no_row_in_the_piped_text_form(self):
        import json
        import subprocess
        from intune_iac import workbench
        self.assertEqual(workbench._workflow(self.store, OBJECT, service_root=self.service.root)['name'], SEPARATED)
        piped = subprocess.run(self.command(), capture_output=True, cwd='/tmp')
        self.assertEqual(piped.returncode, 0, piped.stderr)
        for separator in SEPARATORS:
            self.assertNotIn(separator.encode('utf-8'), piped.stdout)
        text = piped.stdout.decode('utf-8')
        self.assertEqual(len(text.splitlines()), len(text.rstrip('\n').split('\n')))       # splitlines() adds no row
        self.assertIn('policy\\u2028Position:', text.split('\n')[0])
        data = subprocess.run(self.command() + ['--json'], capture_output=True, cwd='/tmp')
        self.assertEqual(json.loads(data.stdout)['name'], SEPARATED)                       # the data form keeps it exactly
        self.assertTrue(all(byte < 0x80 for byte in data.stdout))

    def test_a_stored_name_with_the_separators_makes_no_row_in_the_text_form_on_a_terminal(self):
        import fcntl
        import os
        import pty
        import struct
        import subprocess
        import termios
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 40, 100, 0, 0))
        env = dict(os.environ, LANG='C.UTF-8', PYTHONIOENCODING='utf-8')
        env.pop('COLUMNS', None)
        process = subprocess.Popen(self.command(), stdout=slave, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, env=env, cwd='/tmp')
        os.close(slave)
        chunks = []
        while True:
            try:
                data = os.read(master, 4096)
            except OSError:
                break
            if not data:
                break
            chunks.append(data)
        process.wait()
        os.close(master)
        self.assertEqual(process.returncode, 0, process.stderr.read())
        raw = b''.join(chunks)
        for separator in SEPARATORS:
            self.assertNotIn(separator.encode('utf-8'), raw)
        text = raw.decode('utf-8').replace('\r\n', '\n')
        self.assertEqual(len(text.splitlines()), len(text.rstrip('\n').split('\n')))
        self.assertIn('policy\\u2028Position:', text.split('\n')[0])

    def test_a_stored_name_with_the_separators_makes_no_row_in_the_layer_frames_of_the_real_engine(self):
        key = lambda char: ('text', char)
        for size, rules in (((120, 40), 'unicode'), ((80, 24), 'ascii')):
            ws, frames = self.run_keys(typed('select ' + OBJECT) + typed('workflow') + ['down'] * 2 + [key('q')], size, rules)
            self.assertEqual(ws.states[-1]['layer'], 'workflow')
            for frame in frames:
                self.assertEqual(len(frame), size[1])
                for row in frame:
                    for separator in SEPARATORS:
                        self.assertNotIn(separator, row, (size, rules))
                    self.assertLessEqual(len(row.splitlines()), 1, (size, rules, row))


# ---- PKG-UXVIS-5b item 1: a blocked observation names its continuation ---------------------------------------------------

def moved_source(read, observed=1, service=2, reason='service_changed'):
    """The baseline's observation, fresh by age, with the proposal's own check saying the source moved on."""
    read['states']['observation']['eligibility'] = {'code': 'maintenance_observation_stale', 'reason': reason,
                                                    'observed_revision': observed, 'service_revision': service}
    return read


class BlockedObservationPureTests(unittest.TestCase):
    def test_a_source_that_moved_on_carries_the_revision_fact_and_the_collect_again_step_the_inspector_gives(self):
        from intune_iac.workbench_screens import ELIGIBILITY_FINDINGS
        stage = by_id(project(moved_source(baseline())))['observe']
        self.assertEqual((stage['state'], stage['reason']), ('blocked', 'service_changed'))
        self.assertEqual({key: stage['facts'].get(key) for key in ('observed_revision', 'service_revision')},
                         {'observed_revision': 1, 'service_revision': 2})
        # The step is the one the diagnostics view already gives for this check, not a sentence written for the map.
        self.assertEqual(stage['continuation'], ELIGIBILITY_FINDINGS['service_changed'][1])
        self.assertIn('Collect again', stage['continuation'])

    def test_the_revision_fact_is_said_in_words_in_the_detail_rows_and_the_text_form(self):
        from intune_iac.workbench_screens import workflow_detail_rows, workflow_text_lines
        flow = project(moved_source(baseline(), observed=7, service=9))
        stage = by_id(flow)['observe']
        detail = ' '.join(' '.join(str(row) for row in workflow_detail_rows(flow, stage, 100)).split())
        self.assertIn('captured revision 7', detail)
        self.assertIn('service revision 9', detail)
        self.assertIn('next', detail)
        self.assertIn('Collect again', detail)
        text = ' '.join(' '.join(workflow_text_lines(flow, 100)).split())
        self.assertIn('captured revision 7; service revision 9', text)
        self.assertIn('Collect again', text)

    def test_a_recorded_diagnostics_step_still_leads_and_no_other_check_invents_a_revision(self):
        from intune_iac.workbench_screens import ELIGIBILITY_FINDINGS
        read = moved_source(baseline())
        read['attention'] = {'status': 'attention', 'checked': {}, 'signals': [
            {'area': 'freshness', 'code': 'observation_stale', 'observed': 'x', 'evidence': {},
             'next_step': 'Collect again (a: actions) before preparing or judging a change.'}]}
        self.assertEqual(by_id(project(read))['observe']['continuation'],
                         'Collect again (a: actions) before preparing or judging a change.')
        # A policy that changed at the source has no revision to show, and still names the one step the check gives.
        stage = by_id(project(moved_source(baseline(), reason='policy_changed')))['observe']
        self.assertEqual((stage['state'], stage['reason']), ('blocked', 'policy_changed'))
        self.assertEqual(stage['continuation'], ELIGIBILITY_FINDINGS['policy_changed'][1])
        # A current observation says nothing: no revision fact and no step.
        stage = by_id(project(baseline()))['observe']
        self.assertEqual((stage['state'], stage['continuation']), ('done', None))
        self.assertNotIn('observed_revision', stage['facts'])
        self.assertNotIn('service_revision', stage['facts'])


class BlockedObservationStateFiveTests(LayerFixture):
    """State 5 of the journey: the response was lost, so the execution moved the service and the observation reads blocked."""

    def lose_the_response(self):
        from intune_iac import maintenance
        review = self.prepare()
        maintenance.execute(self.operation, approve_digest=review['approval_digest'], fault='lost-response')

    def test_the_observe_stage_names_the_revisions_and_the_next_step_at_state_5(self):
        from intune_iac import workbench
        self.lose_the_response()
        recorded = workbench._workflow_read(self.store, OBJECT, service_root=self.service.root)['states']['observation']['eligibility']
        self.assertEqual(recorded['reason'], 'service_changed')
        ws = self.layer_workspace(focus='observe')
        stage = by_id(ws.value)['observe']
        self.assertEqual((stage['state'], stage['reason']), ('blocked', 'service_changed'))
        self.assertEqual({key: stage['facts'].get(key) for key in ('observed_revision', 'service_revision')},
                         {key: recorded[key] for key in ('observed_revision', 'service_revision')})
        self.assertIn('Collect again', stage['continuation'] or '')

    def test_the_focus_rows_of_the_observe_stage_show_both_at_each_window_the_map_is_drawn_in(self):
        from intune_iac import workbench
        self.lose_the_response()
        recorded = workbench._workflow_read(self.store, OBJECT, service_root=self.service.root)['states']['observation']['eligibility']
        key = lambda char: ('text', char)
        for size in ((120, 40), (80, 24), (60, 20)):
            # The identity row and the head of the step are pinned; the recorded values scroll, so the smaller windows
            # reach them with PgDn.
            ws, frames = self.run_keys(typed('select ' + OBJECT) + typed('workflow') + ['up'] * 7 + ['pagedown'] * 3 + [key('q')],
                                       size, 'ascii')
            seen = [' '.join(' '.join(row.strip(' |') for row in self.plain(frame)).split()) for frame in frames[-4:]]
            self.assertIn('FOCUS observe', seen[0], size)
            self.assertIn('Collect again', seen[0], size)
            self.assertTrue(any('captured revision %s' % recorded['observed_revision'] in text for text in seen), (size, seen))
            self.assertTrue(any('service revision %s' % recorded['service_revision'] in text for text in seen), (size, seen))


# ---- PKG-UXVIS-5b item 2: PgUp retraces PgDn in the workflow layer ------------------------------------------------------

class WorkflowPagingTests(LayerFixture):
    """The real key path: the layer opens at the position the records give, some keys move the focus, then PgDn and PgUp."""
    STARTS = {'at the position': [], 'at the first stage': ['up'] * 5, 'two stages on': ['down'] * 2, 'at the last stage': ['down'] * 5,
              'one stage up': ['up']}

    def pressed(self, size, start, paging, rules='ascii'):
        """The frames before the paging keys and after each of them."""
        if not hasattr(self, 'operation'):
            self.prepare()
        opening = typed('select ' + OBJECT) + typed('workflow')
        ws, frames = self.run_keys(opening + start + paging + [('text', 'q')], size, rules)
        first = len(opening) + len(start)
        return [self.plain(frames[first + index]) for index in range(len(paging) + 1)]

    def test_pgup_shows_exactly_the_rows_the_view_showed_before_pgdn_at_80x24_and_60x20(self):
        for size in ((80, 24), (60, 20)):
            for name, start in self.STARTS.items():
                before, down, up = self.pressed(size, start, ['pagedown', 'pageup'])
                if any('more below: PgDn' in row for row in before):
                    self.assertNotEqual(down, before, (size, name, 'PgDn moved nothing although rows lie below'))
                self.assertEqual(up, before, (size, name))

    def test_pgup_steps_back_one_page_at_a_time_through_two_pgdns(self):
        for size in ((80, 24), (60, 20)):
            start, first, second, back_one, back_two = self.pressed(size, ['up'] * 5, ['pagedown', 'pagedown', 'pageup', 'pageup'])
            # A PgDn that moved is undone by the next PgUp; one that moved nothing (the end was already shown) leaves
            # nothing to undo, so the PgUp that follows undoes the one before it.
            moved_twice = second != first
            self.assertEqual(back_one, first if moved_twice else start, size)
            if moved_twice:
                self.assertEqual(back_two, start, size)

    def test_a_long_map_pages_down_and_back_up_page_by_page_and_a_command_is_never_split(self):
        self.prepare()
        ws = self.layer_workspace()
        rows = ['row %d' % index for index in range(30)]
        ws.scroll, seen = 0, [0]
        for _ in range(7):
            ws.scroll = ws._workflow_page(rows, 5, 1)
            seen.append(ws.scroll)
        self.assertEqual(seen, [0, 5, 10, 15, 20, 25, 25, 25])            # the last page is the one that ends the rows
        back = []
        for _ in range(7):
            ws.scroll = ws._workflow_page(rows, 5, -1)
            back.append(ws.scroll)
        self.assertEqual(back, [20, 15, 10, 5, 0, 0, 0])
        # A row that continues on the next (a trailing backslash) is not split: the page ends before the command.
        ws._page_trail = []
        split = ['row %d' % index for index in range(30)]
        split[4] += ' \\'
        ws.scroll = 0
        self.assertEqual(ws._workflow_page(split, 5, 1), 4)
        # With no trail (the view was scrolled by the focus), PgUp goes to the page that ends at the first row shown.
        ws._page_trail = []
        ws.scroll = 7
        self.assertEqual(ws._workflow_page(rows, 5, -1), 2)

    def test_pgup_at_the_top_and_pgdn_at_the_end_change_nothing_and_both_ends_are_reached(self):
        for size in ((80, 24), (60, 20)):
            frames = self.pressed(size, ['up'] * 5, ['pageup', 'pageup', 'pagedown', 'pagedown', 'pagedown'])
            start, top, still_top, *down = frames
            self.assertFalse(any('more above: PgUp' in row for row in top), size)       # the first page, header and all
            self.assertEqual(still_top, top, size)
            self.assertEqual(down[-1], down[-2], size)
            self.assertFalse(any('more below: PgDn' in row for row in down[-1]), size)

    def test_a_page_keeps_every_row_it_pages_past_in_reach_so_none_is_skipped(self):
        # Walking down by pages, every row of the pane shows at least once: 60x20 shows five rows at a time.
        frames = self.pressed((60, 20), ['up'] * 5, ['pagedown'] * 4)
        seen = set()
        for rows in frames:
            seen.update(row.strip(' |') for row in rows if row.startswith('|'))
        for label in ('observe', 'adopt', 'intent', 'propose', 'review', 'approve, execute', 'readback', 'reconcile', 'record',
                      'observed after', 'maintain'):
            self.assertTrue(any(label in row for row in seen), label)


# ---- PKG-UXVIS-5b item 3: the plain-text command of the 40x12 layer is usable -------------------------------------------

def command_block(rows):
    """The rows of the printed command in a frame: from the row that starts it through the row that does not end in a
    backslash, with the index of its first row. None when no row starts a command."""
    rows = [row.rstrip() for row in rows]
    start = next((index for index, row in enumerate(rows) if row.startswith('intune-iac workbench workflow')), None)
    if start is None:
        return None, None
    end = start
    while rows[end].endswith('\\') and end + 1 < len(rows):
        end += 1
    return start, rows[start:end + 1]


class WorkflowRouteTests(unittest.TestCase):
    def tokens(self, rows):
        import shlex
        return shlex.split(' '.join(row.rstrip('\\') for row in rows))

    def test_the_command_names_the_real_root_and_policy_quoted_by_the_shared_path_writer(self):
        from intune_iac.workbench_screens import workflow_command_rows
        rows = workflow_command_rows('/tmp/a store', OBJECT, 76)
        self.assertEqual(self.tokens(rows), ['intune-iac', 'workbench', 'workflow', '--root', '/tmp/a store', '--policy', OBJECT])
        self.assertIn("'/tmp/a store'", ' '.join(rows))                     # quoted for the shell, once
        for row in rows[:-1]:
            self.assertTrue(row.endswith(' \\'), row)                        # every row but the last continues the command
        self.assertFalse(rows[-1].endswith('\\'))

    def test_a_root_the_display_rule_refuses_prints_no_command(self):
        from intune_iac.workbench_screens import workflow_command_rows
        for root in ('/tmp/bad\x1bname', '/tmp/bad​name'):
            self.assertIsNone(workflow_command_rows(root, OBJECT, 40), root)

    def test_every_row_of_a_command_fits_its_width(self):
        from intune_iac.workbench_screens import workflow_command_rows
        for width in (40, 60, 100):
            for row in workflow_command_rows('/tmp/s', OBJECT, width):
                self.assertLessEqual(len(row), width, (width, row))


class WorkflowRouteFrameTests(LayerFixture):
    def test_the_40x12_command_stands_on_its_own_rows_complete_with_the_real_root_and_policy(self):
        import shlex
        self.prepare()
        for size in ((40, 12), (44, 14)):
            ws, frames = self.open_layer(size, 'ascii')
            rows = [row.rstrip() for row in self.plain(frames[-1])]
            start, block = command_block(rows)
            self.assertIsNotNone(start, (size, rows))
            self.assertEqual(shlex.split(' '.join(row.rstrip('\\') for row in block)),
                             ['intune-iac', 'workbench', 'workflow', '--root', str(self.store.root), '--policy', OBJECT], size)
            for row in block:
                self.assertLessEqual(len(row), size[0], (size, row))
            # Never inside a sentence: the sentence before it ends, and nothing of prose follows it on its rows or after.
            self.assertTrue(rows[start - 1].rstrip().endswith(':'), (size, rows[start - 1]))
            self.assertNotIn('prints', ' '.join(rows))
            allowed = set(shlex.split(' '.join(row.rstrip('\\') for row in block)))
            for row in block:
                self.assertTrue(set(shlex.split(row.rstrip('\\'))) <= allowed, (size, row))
            self.assertIn('Esc closes it', ' '.join(' '.join(rows).split()), size)


# ---- PKG-UXVIS-5b item 4: the constrained view keeps the safety clause of an unknown outcome ----------------------------

class ConstrainedBandPureTests(unittest.TestCase):
    """constrained_rows is the one frame every surface draws below its minimum window: its band must not lose "never replays"."""

    def rows(self, layer, width, height=12):
        from intune_iac.workbench_screens import constrained_rows
        from plugin_tests.test_workbench_hazard import UNKNOWN
        facts = {'signals': [UNKNOWN], 'operation': 'outcome_unknown', 'object_id': OBJECT, 'identity_prefixes': {}}
        lines, band = constrained_rows(TENANT, OBJECT, facts, 'synthetic', width, height, '60x20', '', layer=layer,
                                       route=('/tmp/store', OBJECT))
        return [lines[index] for index in band], lines

    def test_where_no_complete_form_fits_a_row_the_shortest_is_wrapped_and_keeps_never_replays(self):
        for layer in ('summary', 'catalog', 'workflow'):
            for width in (40, 38, 36, 32):
                band, lines = self.rows(layer, width)
                self.assertIn('never replays', ' '.join(' '.join(band).split()), (layer, width, band))
                self.assertIn('Reconcile', ' '.join(band), (layer, width, band))
                self.assertEqual(len(band), 2, (layer, width, band))              # the condition on one row, the response on the next
                for row in lines:
                    self.assertLessEqual(len(row), width, (layer, width, row))

    def test_a_window_too_short_for_the_wrapped_band_and_the_header_keeps_the_header_and_the_shorter_band(self):
        for height in (3, 4):
            band, lines = self.rows('summary', 24, height)
            text = ' '.join(lines).lower()
            self.assertIn('below 60x20', text, height)                  # what the window is too small for stays
            self.assertIn('reconcile', text, height)
            self.assertLessEqual(len(lines), height)
        band, lines = self.rows('summary', 36, 12)
        self.assertEqual(len(band), 2)                                   # with room, the band is wrapped whole

    def test_a_window_that_holds_a_complete_form_on_one_row_still_draws_that_one_row(self):
        for width in (60, 80):
            band, _ = self.rows('summary', width)
            self.assertEqual(len(band), 1, (width, band))
            self.assertIn('never replays', band[0])

    def test_the_regular_band_keeps_its_shorter_response_where_the_frame_is_not_constrained(self):
        from intune_iac.workbench_screens import hazard_rows
        from plugin_tests.test_workbench_hazard import UNKNOWN
        # run 12's own expectation for the unconstrained band at 40 columns: only the constrained frame wraps.
        rows = hazard_rows({'signals': [UNKNOWN]}, [UNKNOWN], 40)
        self.assertIn('Reconcile (a actions)', rows[0])


class ConstrainedBandFrameTests(LayerFixture):
    def lose_the_response(self):
        from intune_iac import maintenance
        review = self.prepare()
        maintenance.execute(self.operation, approve_digest=review['approval_digest'], fault='lost-response')

    def text(self, frames):
        return ' '.join(' '.join(self.plain(frames[-1])).split())

    def test_at_40x12_the_workflow_layer_and_the_inspector_both_keep_never_replays_with_the_unknown_outcome(self):
        self.lose_the_response()
        key = lambda char: ('text', char)
        ws, layer = self.run_keys(typed('select ' + OBJECT) + typed('workflow') + [key('q')], (40, 12), 'ascii')
        self.assertEqual(ws.states[-1]['layer'], 'workflow')
        # The Inspector draws its own frame down to 40x12; the same constrained view is what it shows below that.
        ws, inspector = self.run_keys(typed('select ' + OBJECT) + [key('q')], (39, 11), 'ascii')
        self.assertEqual(ws.states[-1]['layer'], 'summary')
        for name, frames, width in (('workflow layer', layer, 40), ('inspector', inspector, 39)):
            text = self.text(frames)
            self.assertIn('Outcome unknown', text, name)
            self.assertIn('never replays', text, name)
            for row in self.plain(frames[-1]):
                self.assertLessEqual(len(row), width, (name, row))
        # The layer's own sentence and command are still whole beside the band.
        self.assertIn('intune-iac workbench workflow --root', self.text(layer).replace(' \\', ''))

    def test_at_40x12_40x13_and_41x12_every_required_piece_is_whole(self):
        import shlex
        self.lose_the_response()
        key = lambda char: ('text', char)
        for size in ((40, 12), (40, 13), (41, 12)):
            ws, frames = self.run_keys(typed('select ' + OBJECT) + typed('workflow') + [key('q')], size, 'ascii')
            rows = [row.rstrip() for row in self.plain(frames[-1])]
            joined = ' | '.join(rows)
            self.assertIn('The workflow map needs a larger window', joined, size)
            self.assertIn('(at least 60x20). Plain text:', joined, size)
            start, block = command_block(rows)
            self.assertIsNotNone(start, (size, rows))
            self.assertEqual(shlex.split(' '.join(row.rstrip('\\') for row in block))[:4],
                             ['intune-iac', 'workbench', 'workflow', '--root'], size)
            self.assertIn('! Outcome unknown.', rows, size)
            self.assertIn('Reconcile, never replays', rows, size)
            self.assertIn('T 11111111 | P 22222222', rows, size)
            self.assertTrue(any(row.startswith('T = tenant | P = policy') for row in rows), (size, rows))
            self.assertIn('Esc closes it.', rows, size)
            self.assertTrue(any('q exits' in row for row in rows), (size, rows))
            for row in rows:
                self.assertLessEqual(len(row), size[0], (size, row))


# ---- PKG-UXVIS-5b item 5: three recorded test gaps (mutants P28, P39 and W06 of the workflow map's mutation run) ----------

class RecordedGapTests(unittest.TestCase):
    def test_a_delivery_review_that_is_not_done_is_unknown_never_done(self):
        # P28: a review stage that is not done read done. Only a stage the records call done is a review that was made.
        for status in ('not_started', 'waiting', 'unknown', 'failed', None):
            delivery = delivery_of('prepared', review=stage_row('review', status, changes=[OBJECT + ':description_changed']))
            stage = by_id(project(with_operation(baseline(), delivery=delivery)))['review']
            self.assertEqual((stage['state'], stage['basis']), ('unknown', 'operation 4d972e93 delivery stage review'), status)
        done = by_id(project(with_operation(baseline())))['review']
        self.assertEqual(done['state'], 'done')

    def test_an_unknown_execution_keeps_its_recorded_error_code_at_the_approve_stage_and_says_outcome_unknown_without_one(self):
        # P39: the approve stage lost the execution's recorded code. The readback stage already keeps it (P40).
        read = with_operation(baseline(), delivery=executed_delivery('unknown'), journal='outcome_unknown',
                              review=prepared_review('open', status='outcome_unknown'))
        stages = by_id(project(read))
        self.assertEqual((stages['approve_execute']['state'], stages['approve_execute']['reason']),
                         ('unknown', 'maintenance_service_incomplete'))
        self.assertEqual(stages['approve_execute']['basis'], 'operation 4d972e93 journal_status')
        bare = executed_delivery('unknown', execution={'error_code': None})
        read = with_operation(baseline(), delivery=bare, journal='outcome_unknown',
                              review=prepared_review('open', status='outcome_unknown'))
        self.assertEqual(by_id(project(read))['approve_execute']['reason'], 'outcome_unknown')


# W06 (the read model reports no policy name) needs no test here: the whole module already fails under it, in
# StoredNameTests and StoredSeparatorTests (three tests), which read the stored name back through the real read model.


# ---- PKG-UXVIS-5b round 3 (Sol review): findings 1 to 5 -----------------------------------------------------------------

class RoundThreeFindingOneTests(unittest.TestCase):
    """Finding 1: no size the constrained view draws loses "never replays"."""
    rows = ConstrainedBandPureTests.rows

    def test_no_size_loses_the_safety_clause_on_any_surface(self):
        for layer in ('summary', 'catalog', 'workflow'):
            for width, height in ((24, 3), (30, 4), (39, 11), (40, 12), (24, 2), (30, 2), (36, 5), (20, 3)):
                band, lines = self.rows(layer, width, height)
                self.assertIn('never replays', ' '.join(' '.join(lines).split()), (layer, width, height, lines))
                self.assertLessEqual(len(lines), height, (layer, width, height))
                for row in lines:
                    self.assertLessEqual(len(row), width, (layer, width, height, row))

    def test_a_single_row_window_keeps_it_too(self):
        band, lines = self.rows('summary', 30, 1)
        self.assertIn('never replays', ' '.join(lines))

    def test_the_compact_form_is_two_rows_and_no_other_form_replaces_it(self):
        from intune_iac.workbench_screens import BAND_COMPACT, BAND_ESSENTIAL
        self.assertIn(BAND_ESSENTIAL['operation_outcome_unknown'], BAND_COMPACT['operation_outcome_unknown'])
        band, _ = self.rows('summary', 24, 5)
        self.assertEqual(band[:2], ['! Outcome unknown.', 'Reconcile, never replays'])


class RoundThreeFindingTwoTests(LayerFixture):
    """Finding 2: the command block is atomic."""
    def test_a_command_row_ending_in_a_backslash_is_always_followed_by_its_own_continuation(self):
        import shlex
        from intune_iac import maintenance
        review = self.prepare()
        maintenance.execute(self.operation, approve_digest=review['approval_digest'], fault='lost-response')
        key = lambda char: ('text', char)
        for size in ((40, 5), (40, 6), (40, 7), (40, 8), (40, 9), (40, 10), (40, 12), (40, 13)):
            ws, frames = self.run_keys(typed('select ' + OBJECT) + typed('workflow') + [key('q')], size, 'ascii')
            rows = [row.rstrip() for row in self.plain(frames[-1])]
            for index, row in enumerate(rows):
                if row.endswith('\\'):
                    self.assertLess(index + 1, len(rows), (size, rows))
                    self.assertTrue(rows[index + 1].startswith('    '), (size, rows))
            start, block = command_block(rows)
            if start is not None:
                # Whole or absent: the block parses to the full command, ending in the policy.
                self.assertEqual(shlex.split(' '.join(row.rstrip('\\') for row in block))[-2:], ['--policy', OBJECT], (size, rows))
                self.assertFalse(block[-1].endswith('\\'), (size, rows))
            self.assertIn('never replays', ' '.join(' '.join(rows).split()), size)


class RoundThreeFindingThreeTests(unittest.TestCase):
    """Finding 3: no stand-in inside a copyable command."""
    STAND_INS = {'ROOT', 'DIRECTORY', 'ID', 'PATH'}

    def check(self, root, policy, width, reason):
        from intune_iac.workbench_screens import workflow_command_rows, workflow_unavailable_lines
        self.assertIsNone(workflow_command_rows(root, policy, width), (root, policy))
        lines = workflow_unavailable_lines(width, root, policy)
        text = ' '.join(' '.join(lines).split())
        self.assertIn('intune-iac workbench workflow', text)
        self.assertIn('--root', text)
        self.assertIn('--policy', text)
        self.assertIn(reason, text)
        for line in lines:
            self.assertFalse(line.rstrip().endswith('\\'), line)
            self.assertLessEqual(len(line), width, line)
            self.assertFalse(self.STAND_INS & set(line.replace('(', ' ').replace(')', ' ').replace(',', ' ').split()), line)

    def test_a_control_character_root_prints_no_command_and_says_the_root_cannot_be_shown(self):
        self.check('/tmp/bad\x1bname', OBJECT, 40, 'the root cannot be shown here')

    def test_an_over_long_root_prints_no_command(self):
        self.check('/tmp/' + '/'.join(['dir'] * 12), OBJECT, 40, 'the root cannot be shown here')

    def test_a_refused_or_missing_policy_prints_no_command_and_says_which(self):
        self.check('/tmp/store', 'bad\x1bid', 40, 'the policy id cannot be shown here')
        self.check('/tmp/store', None, 40, 'no policy is selected')
        self.check(None, OBJECT, 40, 'the root is not known here')

    def test_the_constrained_frame_never_prints_a_stand_in_operand(self):
        from intune_iac.workbench_screens import constrained_rows
        lines, _ = constrained_rows(TENANT, OBJECT, {}, 'synthetic', 40, 12, '60x20', '', layer='workflow',
                                    route=('/tmp/bad\x1bname', OBJECT))
        for line in lines:
            self.assertFalse(self.STAND_INS & set(line.split()), line)
            self.assertFalse(line.endswith('\\'), line)


class RoundThreeFindingFourTests(LayerFixture):
    """Finding 4: the PgUp trail belongs to its pane and its projection."""
    def test_a_resized_pane_does_not_reuse_the_trail(self):
        self.prepare()
        ws = self.layer_workspace()
        rows = ['row %d' % index for index in range(30)]
        ws.scroll = ws._workflow_page(rows, 5, 1)
        self.assertEqual(ws.scroll, 5)
        self.assertEqual(ws._workflow_page(rows, 3, -1), 2)       # the new pane's previous page, not the old pane's row 0

    def test_a_refresh_that_changes_the_rows_or_the_projection_does_not_reuse_the_trail(self):
        self.prepare()
        ws = self.layer_workspace()
        rows = ['row %d' % index for index in range(8)]
        ws.scroll = 1
        ws.scroll = ws._workflow_page(rows, 5, 1)
        self.assertEqual(ws.scroll, 3)                  # clamped to the last page of eight rows
        # A refresh leaves nine rows: the stale trail would return row 1; the pane as it is now has no page ending at row 3.
        self.assertEqual(ws._workflow_page(rows + ['row 8'], 5, -1), 0)
        ws2 = self.layer_workspace()
        ws2.scroll = 1
        ws2.scroll = ws2._workflow_page(rows, 5, 1)
        ws2.value = dict(ws2.value, revision='0' * 64)          # the projection changed under the same row count
        self.assertEqual(ws2._workflow_page(rows, 5, -1), 0)


class RoundThreeFindingFiveTests(LayerFixture):
    """Finding 5: the legend is an atomic block, or its last kept row carries a truncation mark."""
    def test_at_40x13_40x14_and_40x15_the_legend_is_whole_or_marked(self):
        from intune_iac import maintenance
        review = self.prepare()
        maintenance.execute(self.operation, approve_digest=review['approval_digest'], fault='lost-response')
        key = lambda char: ('text', char)
        for size in ((40, 13), (40, 14), (40, 15)):
            ws, frames = self.run_keys(typed('select ' + OBJECT) + typed('workflow') + [key('q')], size, 'ascii')
            rows = [row.rstrip() for row in self.plain(frames[-1])]
            legend = rows[rows.index(next(row for row in rows if row.startswith('T = tenant | P = policy'))):]
            legend = [row for row in legend if row]
            text = ' '.join(' '.join(legend).split())
            if 'unknown =' in text:
                self.assertIn('reconcile it (a)', text, (size, legend))          # the definition shows whole
            else:
                self.assertTrue(legend[-1].endswith('...'), (size, legend))      # or the cut says it is a cut
            self.assertFalse(legend[-1].endswith('reached'), (size, legend))


# ---- PKG-UXVIS-5b round 4: the safety text is never clipped ---------------------------------------------------------------

class RoundFourClippedSafetyTextTests(unittest.TestCase):
    def test_at_every_width_and_height_the_band_holds_a_complete_form_or_only_a_mark_below_the_floor(self):
        from intune_iac import workbench_screens
        from intune_iac.workbench_screens import constrained_rows
        from plugin_tests.test_workbench_hazard import UNKNOWN
        facts = {'signals': [UNKNOWN], 'operation': 'outcome_unknown', 'object_id': OBJECT, 'identity_prefixes': {}}
        # (The defaults are the intended chain, so that a product without it fails by the frames, not by the name.)
        BAND_FLOOR_WIDTH = getattr(workbench_screens, 'BAND_FLOOR_WIDTH', 9)
        forms = [list(form) for form in getattr(workbench_screens, 'BAND_FORMS', (
            ('! Outcome unknown.', 'Reconcile, never replays'), ('! Outcome unknown,', 'never replays'),
            ('Unknown; never replays',), ('Unknown: NO REPLAY',), ('NO REPLAY',)))]
        for layer in ('summary', 'workflow'):
            for height in (1, 2, 3):
                for width in range(1, 46):
                    lines, band = constrained_rows(TENANT, OBJECT, facts, 'synthetic', width, height, '60x20', '', layer=layer,
                                                   route=('/tmp/store', OBJECT))
                    rows = [lines[index] for index in band]
                    where = (layer, width, height, rows)
                    if width < BAND_FLOOR_WIDTH:
                        self.assertEqual(rows, ['!'], where)               # below the floor: one mark, no partial text
                        continue
                    whole = ' '.join(' '.join(rows).split())
                    self.assertTrue(rows in forms or 'never replays' in whole, where)
                    for row in rows:
                        self.assertLessEqual(len(row), width, where)
                    # No row is the start of a form cut short.
                    for form in forms:
                        for text in form:
                            for row in rows:
                                if row != text and len(row) >= 3:
                                    self.assertFalse(text.startswith(row) and len(row) < len(text), where)

    def test_the_forms_are_complete_longest_first_and_the_floor_is_the_narrowest(self):
        from intune_iac.workbench_screens import BAND_FLOOR_WIDTH, BAND_FORMS
        widths = [max(len(row) for row in form) for form in BAND_FORMS]
        self.assertEqual(BAND_FLOOR_WIDTH, min(widths))
        for form in BAND_FORMS:
            self.assertRegex(' '.join(form), r'(?i)never replays|no replay')
        self.assertEqual(self.one_row(BAND_FORMS)[0], 'Unknown; never replays')

    def one_row(self, forms):
        return [form[0] for form in forms if len(form) == 1]


if __name__ == "__main__":
    unittest.main()
