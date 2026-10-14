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
        self.assertIn('4d972e93 reconciled; readback desired_state_observed', text)

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


if __name__ == '__main__':
    unittest.main()
