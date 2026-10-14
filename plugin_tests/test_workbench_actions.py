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
        self.assertEqual(maintenance.proposal_eligibility(self.store.root, self.service.root, OBJECT), caught.exception.code)

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

    def test_a_view_is_not_followed_by_a_read(self):
        workspace = self.workspace()
        workspace.last_command = 'inspect'
        workspace.receive(actions_value())
        self.assertIsNone(workspace.quiet)

    def test_a_failed_read_keeps_nothing_stale(self):
        workspace = self.workspace()
        workspace.facts['signals'] = [{'code': 'collection_failed', 'area': 'collection'}]
        workspace.quiet = {'purpose': 'refresh', 'state': 'sent'}
        workspace.receive({'status': 'error', 'error': {'code': 'diagnostics_unavailable', 'message': 'unreadable'}})
        self.assertNotIn('signals', workspace.facts)
        self.assertNotIn('actions', workspace.facts)

    def test_an_interruption_during_the_read_is_shown(self):
        workspace = self.workspace()
        workspace.quiet = {'purpose': 'refresh', 'state': 'sent'}
        interrupted = {'status': 'interrupted', 'recovery': 'Reopen the workbench.'}
        workspace.receive(interrupted)
        self.assertIs(workspace.value, interrupted)

    def test_enter_stages_the_exact_command_and_escape_discards_it(self):
        workspace = self.workspace()
        self.press_a(workspace)
        sent = self.keys(workspace, ['enter', 'escape', ('char', 'q')])
        self.assertEqual(sent, 'quit')  # Escape discarded the staged command; nothing else was sent.
        workspace = self.workspace()
        self.stage_first(workspace)
        self.assertEqual(workspace.mode, 'command')
        self.assertEqual(workspace.buffer, 'reconcile /work/op')
        self.assertIn('never replays', workspace.notice)

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
