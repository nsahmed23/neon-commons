"""Guided actions (P-PRES-09, P-PRES-13): the next step with its exact arguments, its effects and its blockers.

The read model offers each action with the command built from structured evidence (never parsed from prose), what
it does, and whether it is available now. A proposal's blockers come from the same observation checks propose
makes. The workspace stages an action into the command bar; nothing runs until it is submitted, Esc discards it,
and a staged action never follows a changed selection. The real store, modeled service and maintenance engine
produce each state.
"""
from collections import deque
import json
import shlex
import unittest
from pathlib import Path

from plugin_tests import test_workbench_repository as repository_tests

OBJECT, TENANT = repository_tests.OBJECT, repository_tests.TENANT


class ActionReadModelTests(unittest.TestCase):
    RESOURCE_ADDRESS = repository_tests.RepositoryOwnedChangeTests.RESOURCE_ADDRESS
    setUp = repository_tests.RepositoryOwnedChangeTests.setUp
    import_intent = repository_tests.RepositoryOwnedChangeTests.import_intent
    edit_description = repository_tests.RepositoryOwnedChangeTests.edit_description

    def inspection(self, service=True):
        from intune_iac.workbench import _inspection
        return _inspection(self.store, OBJECT, attention=True, service_available=service,
                           service_root=self.service.root if service else None)

    def actions(self, service=True):
        return {action['kind']: action for action in self.inspection(service)['actions']}

    def lost_response(self):
        from intune_iac import maintenance
        from intune_iac.workbench_repository import propose_from_intent, refresh_intent
        self.import_intent()
        self.edit_description('Edited in the repository.')
        refresh_intent(self.store, OBJECT, 'b' * 40)
        operation = self.root / 'operation'
        review = propose_from_intent(self.store.root, self.service.root, OBJECT, operation)
        maintenance.execute(operation, approve_digest=review['approval_digest'], fault='lost-response')
        return operation, review

    def test_an_unknown_outcome_offers_reconcile_with_the_exact_operation(self):
        operation, review = self.lost_response()
        actions = self.inspection()['actions']
        first = actions[0]
        self.assertEqual(first['kind'], 'reconcile')
        self.assertEqual(first['command'], 'reconcile ' + shlex.quote(str(operation)))
        self.assertTrue(first['available'])
        self.assertEqual(first['binding']['operation_id'], review['operation_id'])
        self.assertIn('never replays', first['effects'])
        self.assertIn('records', first['effects'])

    def verified_change(self):
        from intune_iac import maintenance
        from intune_iac.workbench_repository import propose_from_intent, refresh_intent
        self.import_intent()
        self.edit_description('Edited in the repository.')
        intent = refresh_intent(self.store, OBJECT, 'b' * 40)
        operation = self.root / 'operation'
        review = propose_from_intent(self.store.root, self.service.root, OBJECT, operation)
        maintenance.execute(operation, approve_digest=review['approval_digest'])
        return operation, review, intent

    def test_a_verified_cited_change_offers_its_deployment_record(self):
        # Offered exactly when Delivery's deployment-record stage is available, with both identities in the command.
        from intune_iac.workbench_views import record_local_deployment
        operation, review, intent = self.verified_change()
        action = self.actions()['deployment-record']
        self.assertTrue(action['available'], action)
        self.assertEqual(action['command'], 'deployment-record %s %s' % (shlex.quote(str(operation)), intent['artifact_id']))
        self.assertEqual((action['binding']['operation_id'], action['binding']['intent_id']),
                         (review['operation_id'], intent['artifact_id']))
        self.assertIn('sends nothing', action['effects'])
        self.assertIn('records a deployment receipt', action['effects'])
        record_local_deployment(self.store, operation, intent['artifact_id'])
        self.assertNotIn('deployment-record', self.actions())

    def test_an_unverified_or_uncited_change_offers_no_deployment_record(self):
        self.lost_response()
        self.assertNotIn('deployment-record', self.actions())

    def test_an_observation_stamped_ahead_of_the_clock_is_not_cured_by_collecting(self):
        # Collecting now would not replace it as the newest, so the step is to wait or correct the clock.
        from intune_iac.workbench import _reason_words
        text = _reason_words({'reason': 'not_fresh', 'freshness_reasons': ['stamped_after_now']})
        self.assertIn("stamped after this host's clock", text)
        self.assertIn('collecting again now would not replace it', text)
        self.assertNotIn('; collect again', text)
        from intune_iac.workbench_diagnostics import _freshness
        signals, _ = _freshness({'observed_at': '2026-10-14T22:40:01Z', 'freshness': 'stale', 'freshness_reasons': ['stamped_after_now'],
                                 'freshness_checked_at': '2026-10-14T22:36:01Z', 'snapshot_id': 'b' * 64}, False)
        step = signals[0]['next_step']
        self.assertIn('2026-10-14 22:40:01 UTC', step)
        self.assertIn('collecting again now would not replace it', step)
        self.assertNotIn('Collect again (:collect) before', step)

    def test_one_read_judges_freshness_once(self):
        # Journey 26: the clock moved between two reads of one Inspector screen, so its states said fresh while its
        # proposal was blocked as not fresh. The proposal check now uses the observation the states show.
        from unittest import mock
        self.import_intent()
        real = type(self.store).inspect
        calls = []
        def later_reads_stale(store, object_id):
            value = real(store, object_id)
            calls.append(value['freshness'])
            return value if len(calls) == 1 else dict(value, freshness='stale', freshness_reasons=['stamped_after_now'])
        with mock.patch.object(type(self.store), 'inspect', later_reads_stale):
            value = self.inspection()
        self.assertEqual(value['freshness'], 'fresh')
        self.assertIsNone(value['observation_eligibility'], value['observation_eligibility'])
        self.assertTrue({action['kind']: action for action in value['actions']}['propose-from-intent']['available'])

    def test_each_action_has_a_canonical_name_and_one_essential_effect(self):
        # TASK-11 2.6 items 4 and 7: the picker names each action as the band and the staged review do, with its
        # availability and one essential effect; the focused action shows its full effects.
        from intune_iac.workbench_screens import actions_lines
        self.import_intent()
        self.edit_description('Changed and not refreshed.')
        actions = self.inspection()['actions']
        refresh = next(action for action in actions if action['kind'] == 'repository-refresh')
        self.assertEqual(refresh['label'], 'Refresh the repository intent')
        self.assertIn('no Git commit, approval or apply', refresh['summary'])
        self.assertIn('REVISION: the full 40-character commit ID', refresh['needs'][0])
        for action in actions:
            self.assertTrue(action.get('summary'), action['kind'])
        focus = actions.index(refresh)
        text = ' '.join(' '.join(actions_lines(actions, focus, 120)).split())
        self.assertIn(' '.join(refresh['effects'].split()), text)  # the focused action, in full
        others = [action for action in actions if action is not refresh]
        for action in others:
            self.assertIn(' '.join(action['summary'].split()), text)
            self.assertNotIn(' '.join(action['effects'].split()), text)  # the rest on demand

    def test_a_clear_policy_offers_a_proposal_into_a_fresh_directory(self):
        self.import_intent()
        action = self.actions()['propose-from-intent']
        self.assertTrue(action['available'], action)
        target = Path(shlex.split(action['command'])[1])
        self.assertTrue(target.parent.is_dir())
        for path in (target, Path(str(target) + '.intent-desired.json'), Path(str(target) + '.intent-context.json')):
            self.assertFalse(path.exists(), path)
        self.assertIn('Nothing is approved or sent', action['effects'])
        self.assertEqual(action['binding']['object_id'], OBJECT)
        self.assertEqual(action['binding']['tenant_id'], TENANT)

    def test_two_offers_never_share_a_directory(self):
        self.import_intent()
        first = self.actions()['propose-from-intent']['command']
        second = self.actions()['propose-from-intent']['command']
        self.assertNotEqual(first, second)

    def test_a_changed_repository_asks_for_the_revision_and_blocks_the_proposal(self):
        self.import_intent()
        self.edit_description('Edited in the repository.')
        actions = self.actions()
        refresh = actions['repository-refresh']
        self.assertEqual(refresh['command'], 'repository-refresh ')
        self.assertTrue(any(need.startswith('REVISION') for need in refresh['needs']))
        blocked = actions['propose-from-intent']
        self.assertFalse(blocked['available'])
        self.assertEqual(blocked['blocked']['code'], 'workbench_repository_stale')
        # The cause diagnostics recorded, not the generic either/or meaning of the code.
        self.assertEqual(blocked['blocked']['reason'], 'repository_changed')
        self.assertIn('changed since its recorded intent: changed ', blocked['blocked']['message'])
        self.assertNotIn(' or ', blocked['blocked']['message'])

    def test_a_stale_observation_blocks_the_proposal_with_the_engines_own_code(self):
        from intune_iac import maintenance
        from intune_iac.io import AppError
        self.import_intent()
        self.store.collect(self.service, fault='deny')
        actions = self.actions()
        self.assertIn('collect', actions)
        blocked = actions['propose-from-intent']
        self.assertFalse(blocked['available'])
        # The same check propose itself makes, with the same code.
        desired = self.root / 'desired.json'; desired.write_text(json.dumps(self.store.inspect(OBJECT)['body']))
        with self.assertRaises(AppError) as caught:
            maintenance.propose(self.store.root, self.service.root, OBJECT, desired, self.root / 'refused')
        self.assertEqual(blocked['blocked']['code'], caught.exception.code)
        self.assertEqual(maintenance.proposal_eligibility(self.store.root, self.service.root, OBJECT)['code'],
                         caught.exception.code)

    def test_a_service_changed_after_collection_names_why_and_offers_collect_first(self):
        # The execute changed the modeled service after the last collection: the observation is fresh by age, but
        # propose compares it with the service and refuses; the actions say which check failed and what fixes it.
        from intune_iac import maintenance
        operation, _ = self.lost_response()
        maintenance.reconcile(operation)
        eligibility = maintenance.proposal_eligibility(self.store.root, self.service.root, OBJECT)
        self.assertEqual((eligibility['code'], eligibility['reason']), ('maintenance_observation_stale', 'service_changed'))
        actions = self.inspection()['actions']
        kinds = [action['kind'] for action in actions]
        self.assertNotIn('reconcile', kinds)
        self.assertLess(kinds.index('collect'), kinds.index('propose-from-intent'))
        self.assertTrue(actions[kinds.index('collect')]['available'])
        blocked = actions[kinds.index('propose-from-intent')]['blocked']
        self.assertEqual((blocked['code'], blocked['reason']), ('maintenance_observation_stale', 'service_changed'))
        self.assertIn('the source changed since this observation was captured', blocked['message'])
        # Collecting again clears it: the proposal becomes available.
        self.store.collect(self.service)
        self.assertTrue(self.actions()['propose-from-intent']['available'])

    def test_a_value_outside_the_capability_map_blocks_the_proposal_as_the_engine_would(self):
        import yaml
        from intune_iac.workbench_repository import refresh_intent
        self.import_intent()
        stack = self.repo / repository_tests.STACK
        document = yaml.safe_load(stack.read_text())
        policy = document['components']['terraform']['intune-reference']['vars']['policies'][repository_tests.KEY]
        instance = policy['settings']['settings'][0]['settingInstance']
        instance['choiceSettingValue']['value'] = instance['settingDefinitionId'] + '_1'
        stack.write_text(yaml.safe_dump(document))
        refresh_intent(self.store, OBJECT, 'b' * 40)
        blocked = self.actions()['propose-from-intent']
        self.assertFalse(blocked['available'])
        self.assertEqual(blocked['blocked']['code'], 'workbench_desired_capability')

    def test_a_shown_difference_binds_the_refresh(self):
        from intune_iac.io import AppError
        from intune_iac.workbench_repository import intent_freshness, latest_intent, refresh_intent
        self.import_intent()
        self.edit_description('First edit, shown.')
        shown = intent_freshness(latest_intent(self.store, OBJECT)['data'])['resolution_sha256']
        self.edit_description('Second edit, never shown.')
        with self.assertRaises(AppError) as caught:
            refresh_intent(self.store, OBJECT, 'b' * 40, expected_resolution=shown)
        self.assertEqual(caught.exception.code, 'workbench_difference_changed')
        current = intent_freshness(latest_intent(self.store, OBJECT)['data'])['resolution_sha256']
        refresh_intent(self.store, OBJECT, 'b' * 40, expected_resolution=current)
        self.assertEqual(intent_freshness(latest_intent(self.store, OBJECT)['data'])['status'], 'current')

    def test_the_refresh_action_shows_the_difference_before_it_is_staged(self):
        self.import_intent()
        self.edit_description('Edited in the repository.')
        refresh = self.actions()['repository-refresh']
        self.assertEqual(refresh['show_first'], 'repository-status')
        self.assertIn('Shows the source difference first', refresh['effects'])

    def test_the_observation_check_is_reported_on_its_own(self):
        from intune_iac import maintenance
        operation, _ = self.lost_response()
        maintenance.reconcile(operation)
        eligibility = self.inspection()['observation_eligibility']
        self.assertEqual((eligibility['code'], eligibility['reason']), ('maintenance_observation_stale', 'service_changed'))
        self.store.collect(self.service)
        self.assertIsNone(self.inspection()['observation_eligibility'])

    def test_an_incomplete_check_area_withholds_the_change_even_with_findings(self):
        from intune_iac.workbench import _actions
        from intune_iac.workbench_views import _intents, _latest
        self.import_intent()
        intent = _latest(_intents(self.store, OBJECT, None))
        attention = {'status': 'attention', 'checked': {'operations': 'unavailable', 'repository': 'clear'},
                     'signals': [{'area': 'operations', 'code': 'operations_unavailable', 'observed': 'x',
                                  'next_step': 'y', 'evidence': {}}]}
        actions = _actions(self.store, OBJECT, attention, intent, str(self.service.root))
        self.assertEqual(actions[0]['kind'], 'diagnostics')
        proposal = {action['kind']: action for action in actions}['propose-from-intent']
        self.assertEqual(proposal['blocked']['code'], 'workbench_attention_not_established')

    def test_every_unknown_outcome_gets_its_own_reconcile_in_band_order(self):
        from intune_iac.workbench import _actions
        def unknown(operation, path):
            return {'area': 'operations', 'code': 'operation_outcome_unknown', 'observed': 'x', 'next_step': 'y',
                    'evidence': {'operation_id': operation, 'operation_root': path}}
        attention = {'status': 'attention', 'checked': {}, 'signals': [unknown('1' * 32, '/w/one'), unknown('2' * 32, '/w/two')]}
        reconciles = [action for action in _actions(self.store, OBJECT, attention, None, str(self.service.root))
                      if action['kind'] == 'reconcile']
        self.assertEqual([action['binding']['operation_root'] for action in reconciles], ['/w/one', '/w/two'])

    def test_a_diverged_operation_is_reconciled_again_as_a_read(self):
        from intune_iac.workbench import _actions
        attention = {'status': 'attention', 'checked': {}, 'signals': [
            {'area': 'operations', 'code': 'operation_diverged', 'observed': 'x', 'next_step': 'y',
             'evidence': {'operation_id': '1' * 32, 'operation_root': '/w/one'}}]}
        action = [item for item in _actions(self.store, OBJECT, attention, None, str(self.service.root))
                  if item['kind'] == 'reconcile'][0]
        self.assertIn('again', action['label'])
        self.assertIn('reads only', action['label'])

    def test_effects_say_what_is_written_and_when(self):
        from intune_iac.workbench import ACTION_EFFECTS
        self.assertIn('before', ACTION_EFFECTS['propose-from-intent'])
        self.assertIn('stay', ACTION_EFFECTS['propose-from-intent'])
        for kind in ('propose-from-intent', 'propose', 'reconcile'):
            self.assertIn('records the operation in this store', ACTION_EFFECTS[kind])

    def test_the_binding_names_the_evidence_mode(self):
        self.import_intent()
        binding = self.actions()['propose-from-intent']['binding']
        self.assertEqual(binding['evidence_class'], self.store.inspect(OBJECT)['evidence_class'])

    def test_unread_diagnostics_offer_the_diagnostics_and_no_change(self):
        # Whether anything needs attention is not established, so no change is offered (as the NEXT steps already said).
        from intune_iac.workbench import _actions
        from intune_iac.workbench_views import _intents, _latest
        self.import_intent()
        intent = _latest(_intents(self.store, OBJECT, None))
        for status in ('unavailable', 'partly_checked'):
            actions = _actions(self.store, OBJECT, {'status': status, 'signals': [], 'checked': {}}, intent, str(self.service.root))
            self.assertEqual((actions[0]['kind'], actions[0]['command']), ('diagnostics', 'diagnostics'))
            self.assertTrue(actions[0]['available'])
            proposal = {action['kind']: action for action in actions}['propose-from-intent']
            self.assertFalse(proposal['available'])
            self.assertEqual(proposal['blocked']['code'], 'workbench_attention_not_established')

    def test_without_a_service_collection_and_proposals_say_what_they_need(self):
        self.import_intent()
        self.store.collect(self.service, fault='deny')
        actions = self.actions(service=False)
        self.assertFalse(actions['collect']['available'])
        self.assertIn('--service-root', actions['collect']['blocked']['message'])
        self.assertFalse(actions['propose-from-intent']['available'])

    def test_without_a_recorded_intent_the_inputs_still_missing_are_named(self):
        actions = self.actions()
        self.assertTrue(any(need.startswith('REPOSITORY') for need in actions['repository-entry']['needs']))
        propose = actions['propose']
        self.assertTrue(any(need.startswith('DESIRED_JSON') for need in propose['needs']))
        self.assertEqual(propose['command'][:propose['cursor']], 'propose ')


def actions_value():
    return {'object_id': OBJECT, 'tenant_id': TENANT, 'name': 'Windows Privacy Pilot', 'snapshot_id': 'f' * 64,
            'evidence_class': 'synthetic', 'freshness': 'fresh',
            'attention': {'status': 'attention', 'checked': {'operations': 'attention'}, 'signals': []},
            'actions': [{'kind': 'reconcile', 'label': 'Reconcile operation 651a8ce8', 'command': 'reconcile /work/op',
                         'cursor': None, 'needs': [], 'effects': 'Reads the modeled service on its own; never replays the write.',
                         'available': True, 'blocked': None, 'binding': {'tenant_id': TENANT, 'object_id': OBJECT}},
                        {'kind': 'propose-from-intent', 'label': 'Prepare a proposal from the recorded intent',
                         'command': 'propose-from-intent /work/operation-22222222-aaaa', 'cursor': None, 'needs': [],
                         'effects': 'Writes a new operation directory. Nothing is approved or sent.', 'available': False,
                         'blocked': {'code': 'maintenance_observation_stale', 'message': 'stale'},
                         'binding': {'tenant_id': TENANT, 'object_id': OBJECT}}]}


class ActionStagingTests(unittest.TestCase):
    def workspace(self):
        from intune_iac.workbench_tui import Workspace
        workspace = Workspace.__new__(Workspace)
        value = actions_value()
        workspace.__dict__.update(
            tab=1, value=value, selected=OBJECT, facts={'object_id': OBJECT, 'actions': value['actions']}, highlight=0,
            scroll=0, mode=None, buffer='', cursor=0, pasting=False, input_overflow=False, notice='', last_command='select ' + OBJECT,
            view_command='inspect', page_command='overview', rows=[], operation_rows=[], operation_highlight=0,
            active_operation=None, execution_result=None, active_service=None, active_adoption=None, active_adoption_plan=None,
            pending=deque(), size=(100, 40), submission_key='enter', entry_focus=0, overview_focus=0, layer='summary', trail=[],
            _detail_cache=None, store=type('S', (), {'tenant_id': TENANT})(), staged=None, action_focus=0, quiet=None)
        workspace.draw = lambda: None
        workspace.save_context = lambda: None
        workspace._terminal_size = lambda: (100, 40)
        return workspace

    def keys(self, workspace, keys):
        class Reader:
            def __init__(self, keys): self.keys = list(keys)
            def read(self): return self.keys.pop(0)
        workspace.key_reader = Reader(keys)
        return workspace.input('')

    def press_a(self, workspace, value=None):
        """a sends the engine's own read; the test answers it as the engine would."""
        self.assertEqual(self.keys(workspace, [('char', 'a')]), 'inspect')
        workspace.receive(actions_value() if value is None else value)

    def stage_first(self, workspace):
        # End of input is refused while a command is staged ("Use Escape to discard"), so the helper stops itself.
        class Stop(Exception):
            pass
        class Reader:
            def __init__(self, keys): self.keys = list(keys)
            def read(self):
                if not self.keys: raise Stop()
                return self.keys.pop(0)
        self.press_a(workspace)
        workspace.key_reader = Reader(['enter'])
        try:
            workspace.input('')
        except Stop:
            pass

    def test_a_blocked_action_shows_the_discriminating_reason(self):
        from intune_iac.workbench_screens import actions_lines
        action = {'kind': 'propose-from-intent', 'label': 'Prepare a proposal from the recorded intent', 'command': 'x',
                  'cursor': None, 'needs': [], 'effects': 'Writes a new operation directory.', 'available': False,
                  'blocked': {'code': 'maintenance_observation_stale', 'reason': 'service_changed',
                              'message': 'the modeled service changed after this observation was collected (revision 1, now 2)'},
                  'binding': {}}
        joined = '\n'.join(actions_lines([action], 0, 120))
        self.assertIn('maintenance_observation_stale: the modeled service changed after this observation was collected', joined)

    def test_a_missing_input_is_shown_where_it_goes(self):
        from intune_iac.workbench_screens import actions_lines
        action = {'kind': 'propose', 'label': 'Prepare a local proposal from a desired file', 'command': "propose  '/w x/op'",
                  'cursor': len('propose '), 'needs': ['DESIRED_JSON: a file holding the desired policy body'],
                  'effects': 'Writes a new operation directory.', 'available': True, 'blocked': None, 'binding': {}}
        joined = '\n'.join(actions_lines([action], 0, 100))
        self.assertIn("command  propose DESIRED_JSON '/w x/op'", joined)
        self.assertNotIn(' ...', joined)

    def test_a_opens_the_actions_with_what_each_does(self):
        workspace = self.workspace()
        self.press_a(workspace)
        self.assertEqual(workspace.layer, 'actions')
        lines = workspace._data_lines(100)
        joined = '\n'.join(lines)
        self.assertTrue(lines[0].startswith('ACTIONS'), lines[0])
        self.assertIn('Reconcile operation 651a8ce8', joined)
        self.assertIn('reconcile /work/op', joined)
        self.assertIn('never replays', joined)
        self.assertIn('blocked', joined.lower())
        self.assertIn('Nothing runs until you submit it', joined)

    def test_a_reads_the_actions_again_and_keeps_the_screen(self):
        workspace = self.workspace()
        shown = {'status': 'complete', 'evidence_class': 'synthetic', 'run': 'collect result being read'}
        workspace.value, workspace.last_command, workspace.tab = shown, 'collect', 5
        workspace.trail = [(0, 'overview')]
        fresh = actions_value()
        fresh['actions'] = fresh['actions'][1:]
        self.press_a(workspace, fresh)
        self.assertEqual(workspace.layer, 'actions')
        self.assertIs(workspace.value, shown)  # the screen underneath is the one the engineer was reading
        self.assertEqual((workspace.tab, workspace.trail, workspace.last_command), (5, [(0, 'overview')], 'collect'))
        self.assertEqual([action['kind'] for action in workspace._actions()], ['propose-from-intent'])

    def test_after_a_command_that_may_write_the_band_is_read_again(self):
        workspace = self.workspace()
        workspace.last_command = 'collect'
        result = {'status': 'complete', 'evidence_class': 'synthetic'}
        workspace.receive(result)
        notice = workspace.notice
        self.assertEqual(workspace.quiet, {'purpose': 'refresh', 'state': 'due'})
        self.assertEqual(self.keys(workspace, []), 'inspect')  # sent before any key is read
        fresh = actions_value()
        fresh['attention']['signals'] = [{'code': 'repository_stale', 'area': 'repository', 'observed': 'The repository changed.'}]
        workspace.receive(fresh)
        self.assertEqual([signal['code'] for signal in workspace.facts['signals']], ['repository_stale'])
        self.assertIs(workspace.value, result)
        self.assertEqual(workspace.notice, notice)
        self.assertIsNone(workspace.quiet)

    def test_a_reconcile_result_teaches_the_journal_status(self):
        workspace = self.workspace()
        workspace.facts['operation'] = 'outcome_unknown'
        workspace.last_command = 'reconcile /work/op'
        workspace.receive({'operation_id': '651a8ce8ff0e42d5a091c70ac13d21a1', 'classification': 'desired_state_observed',
                           'previous_status': 'outcome_unknown', 'journal_status': 'reconciled'})
        self.assertEqual((workspace.facts['operation'], workspace.facts['operation_id']),
                         ('reconciled', '651a8ce8ff0e42d5a091c70ac13d21a1'))

    def test_a_newer_read_retires_a_hazard_it_no_longer_finds(self):
        workspace = self.workspace()
        workspace.facts.update(operation='outcome_unknown', operation_id='651a8ce8ff0e42d5a091c70ac13d21a1')
        workspace.quiet = {'purpose': 'refresh', 'state': 'sent'}
        fresh = actions_value()
        fresh['attention'] = {'status': 'clear', 'signals': [], 'checked': {'operations': 'clear'}}
        workspace.receive(fresh)
        self.assertNotIn('operation', workspace.facts)

    def test_a_view_is_not_followed_by_a_read(self):
        workspace = self.workspace()
        workspace.last_command = 'inspect'
        workspace.receive(actions_value())
        self.assertIsNone(workspace.quiet)

    def test_a_failed_read_keeps_the_conditions_marked_not_re_read(self):
        from intune_iac.workbench_screens import hazard_rows
        workspace = self.workspace()
        workspace.facts['signals'] = [{'code': 'collection_failed', 'area': 'collection', 'evidence': {'status': 'denied'}}]
        workspace.last_command = 'collect'
        workspace.quiet = {'purpose': 'refresh', 'state': 'sent'}
        workspace.receive({'status': 'error', 'error': {'code': 'diagnostics_unavailable', 'message': 'unreadable'}})
        self.assertEqual([signal['code'] for signal in workspace.facts['signals']], ['collection_failed'])
        self.assertEqual(workspace.facts['unverified'], 'collect')
        self.assertNotIn('actions', workspace.facts)
        self.assertIn('could not be read again', workspace.notice)
        self.assertIn('not re-read', ' '.join(hazard_rows(workspace.facts, workspace.facts['signals'], 100)))

    def test_with_nothing_recorded_a_failed_read_is_itself_shown(self):
        from intune_iac.workbench_screens import hazard_rows
        rows = hazard_rows({'unverified': 'collect'}, [], 100)
        self.assertTrue(rows and rows[0].startswith('! '), rows)
        self.assertIn('2: re-read', rows[0])

    def test_a_successful_read_clears_the_mark(self):
        workspace = self.workspace()
        workspace.facts['unverified'] = 'collect'
        workspace.quiet = {'purpose': 'refresh', 'state': 'sent'}
        workspace.receive(actions_value())
        self.assertNotIn('unverified', workspace.facts)

    def test_staging_a_refresh_shows_the_difference_first_and_binds_it(self):
        workspace = self.workspace()
        refresh = {'kind': 'repository-refresh', 'label': 'Record the current source', 'command': 'repository-refresh ',
                   'cursor': len('repository-refresh '), 'needs': ['REVISION: the commit'], 'available': True,
                   'effects': 'Shows the source difference first.', 'blocked': None, 'show_first': 'repository-status',
                   'binding': {'tenant_id': TENANT, 'object_id': OBJECT}}
        value = actions_value()
        value['actions'] = [refresh]
        self.press_a(workspace, value)
        self.assertEqual(self.keys(workspace, ['enter']), 'repository-status')  # the difference is shown first
        self.assertIsNone(workspace.mode)
        workspace.receive({'schema_version': 'workbench-repository-status/1', 'object_id': OBJECT,
                           'freshness': {'status': 'stale', 'resolution_sha256': 'c' * 64}})
        self.assertEqual(workspace.mode, 'command')
        self.assertEqual(workspace.buffer, 'repository-refresh  ' + 'c' * 64)
        self.assertEqual(workspace.cursor, len('repository-refresh '))
        self.assertIn('difference', workspace.notice)
        # What to type, how to submit or discard, and what the value after the cursor is, within 120 columns.
        # The boundary first (TASK-11 2.6 item 1), then what to type and how to submit or cancel.
        self.assertTrue(workspace.notice.startswith('STAGED refresh: no Git commit, approval or apply.'), workspace.notice)
        self.assertIn('the digest after it pins the reviewed difference', workspace.notice)
        self.assertIn('Esc cancels', workspace.notice)
        # Two rows while staged: the complete boundary, then the mechanics, each in a form that fits 120 columns.
        self.assertLessEqual(len(workspace.staged['boundary'][0]), 120)
        self.assertTrue(any(len(form) <= 120 for form in workspace.staged['mechanics']))

    def test_a_staged_action_never_follows_a_changed_evidence_mode(self):
        workspace = self.workspace()
        value = actions_value()
        value['actions'][0]['binding']['evidence_class'] = 'synthetic'
        workspace.facts['evidence_class'] = 'synthetic'
        self.press_a(workspace, value)
        class Stop(Exception):
            pass
        class Reader:
            def __init__(self, keys): self.keys = list(keys)
            def read(self):
                if not self.keys: raise Stop()
                return self.keys.pop(0)
        workspace.key_reader = Reader(['enter'])
        try:
            workspace.input('')
        except Stop:
            pass
        workspace.facts['evidence_class'] = 'graph_authenticated_observation'
        with self.assertRaises(EOFError):
            self.keys(workspace, ['enter', 'eof'])
        self.assertIn('evidence mode changed', workspace.notice)

    def test_an_interruption_during_the_read_is_shown(self):
        workspace = self.workspace()
        workspace.quiet = {'purpose': 'refresh', 'state': 'sent'}
        interrupted = {'status': 'interrupted', 'recovery': 'Reopen the workbench.'}
        workspace.receive(interrupted)
        self.assertIs(workspace.value, interrupted)
        self.assertIsNone(workspace.quiet)  # never left waiting to swallow a later result

    def test_enter_stages_the_exact_command_and_escape_discards_it(self):
        workspace = self.workspace()
        self.press_a(workspace)
        sent = self.keys(workspace, ['enter', 'escape', ('char', 'q')])
        self.assertEqual(sent, 'quit')  # Escape discarded the staged command; nothing else was sent.
        workspace = self.workspace()
        self.stage_first(workspace)
        self.assertEqual(workspace.mode, 'command')
        self.assertEqual(workspace.buffer, 'reconcile /work/op')
        self.assertTrue(workspace.notice.startswith('STAGED reconcile: never repeats the change.'), workspace.notice)
        self.assertIn('Enter submits; Esc cancels.', workspace.notice)

    def test_a_blocked_action_cannot_be_staged(self):
        workspace = self.workspace()
        self.press_a(workspace)
        sent = self.keys(workspace, ['down', 'enter', ('char', 'q')])
        self.assertEqual(sent, 'quit')
        self.assertIsNone(workspace.staged)

    def test_a_staged_action_never_follows_a_changed_selection(self):
        workspace = self.workspace()
        self.stage_first(workspace)
        workspace.selected = '33333333-3333-4333-8333-333333333333'
        with self.assertRaises(EOFError):
            self.keys(workspace, ['enter', 'eof'])
        self.assertIn('selection changed', workspace.notice)
        self.assertIsNone(workspace.mode)

    def test_submitting_the_staged_command_sends_exactly_it(self):
        workspace = self.workspace()
        self.stage_first(workspace)
        self.assertEqual(self.keys(workspace, ['enter']), 'reconcile /work/op')


if __name__ == '__main__':
    unittest.main()
