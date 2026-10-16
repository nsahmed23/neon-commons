"""The workflow map, first slice (requirement 17 UX-VIS, PKG-UXVIS-5): one selected policy's change path.

Item 1 is the projection (`intune_iac.workflow_projection`, schema workflow-map/1): fixed stages, each state read from a
named record and field, a recorded reason, the surface Enter opens and the one step the existing screens give. The
projection is pure, so most cases here pass it hand-built reads that change one recorded field at a time; the cases that
need a real operation (prepared, closed window, unknown outcome, reconciled, recorded, observed) run the real store, the
modeled service and the maintenance engine over temporary directories.
"""
import copy
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
        self.assertIn('a proposal is blocked now (maintenance_observation_stale)', stages['propose']['continuation'])

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
        # The one step left is Delivery's own: collect to observe the policy, which is the observation after the change.
        self.assertEqual({name: stage['continuation'] for name, stage in stages.items() if stage['continuation']},
                         {'observed_after': NO_RECORD_STEP})

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
        self.assertIn('execute %s DIGEST' % self.operation, stages['approve_execute']['continuation'])
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
        self.assertTrue(any(str(row).strip().startswith('execute /w/operation DIGEST') for row in lines), lines)
        self.assertTrue(any(str(row).startswith('        ') and 'execute /w/operation DIGEST' in str(row) for row in lines), lines)

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
        for width in (36, 76):
            text = ' '.join(' '.join(workflow_unavailable_lines(width)).split())
            self.assertIn('needs a larger window', text)
            self.assertIn('intune-iac workbench workflow --root ROOT --policy ID', text)
            self.assertTrue(all(len(row) <= width for row in workflow_unavailable_lines(width)))

    def test_a_projection_with_an_unknown_state_or_no_stages_still_draws_without_claiming_one(self):
        flow = flows()['waiting']
        broken = dict(flow, stages=[dict(stage, state='mystery') if stage['id'] == 'review' else stage for stage in flow['stages']])
        row = lanes_of(lines_of(broken))[4]
        self.assertEqual((row[7], row[-STATE_WORD_WIDTH:].strip()), ('?', 'unknown'))
        self.assertEqual(lanes_of(lines_of(dict(flow, stages=[]))), [])


if __name__ == "__main__":
    unittest.main()
