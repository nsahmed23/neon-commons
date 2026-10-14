"""Entering an existing repository: the policies it holds and the exact way to record each.

The generated reference project, copied as the engineer's repository, is the
fixture; a commit is written as .git files, so no Git runs. Expected values
are written by hand.
"""
import copy
from collections import deque
import hashlib
import json
from pathlib import Path
import shlex
import unittest
from uuid import UUID

import yaml

from plugin_tests import test_workbench_repository as repository_tests

TENANT, OBJECT, KEY, STACK = repository_tests.TENANT, repository_tests.OBJECT, repository_tests.KEY, repository_tests.STACK
ADDRESS = repository_tests.RepositoryOwnedChangeTests.RESOURCE_ADDRESS
COMMIT = 'c' * 40
OTHER_TENANT = '99999999-9999-4999-8999-999999999999'


def commit(repo, sha=COMMIT):
    git = Path(repo) / '.git'
    (git / 'refs' / 'heads').mkdir(parents=True, exist_ok=True)
    (git / 'HEAD').write_text('ref: refs/heads/main\n')
    (git / 'refs' / 'heads' / 'main').write_text(sha + '\n')


def tree(root):
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(Path(root).rglob('*')) if path.is_file()}


class RepositoryEntryTests(unittest.TestCase):
    RESOURCE_ADDRESS = ADDRESS
    setUp = repository_tests.RepositoryOwnedChangeTests.setUp
    import_intent = repository_tests.RepositoryOwnedChangeTests.import_intent
    edit_description = repository_tests.RepositoryOwnedChangeTests.edit_description

    def survey(self, store=None, repo=None):
        from intune_iac.repository_entry import entry
        value = entry(store or self.store, repo or self.repo)
        self.assertEqual(value['schema_version'], 'workbench-repository-entry/1')
        self.assertFalse(value['execution_authorized']); self.assertFalse(value['cloud_authority'])
        self.assertEqual(value['evidence_class'], 'local_repository_files')
        return value

    def stack(self):
        return yaml.safe_load((self.repo / STACK).read_text())

    def write_stack(self, document):
        (self.repo / STACK).write_text(yaml.safe_dump(document))

    def test_a_generated_repository_offers_its_policy_with_every_value_derived(self):
        commit(self.repo)
        value = self.survey()
        self.assertEqual((value['status'], value['revision']), ('discovered', COMMIT))
        self.assertEqual(value['components'], [{'stack': 'orgs/reference/dev', 'manifest': STACK,
                                                'component': 'intune-reference', 'selectable': True, 'policies': 1}])
        [candidate] = value['candidates']
        self.assertEqual(candidate['number'], 1)
        self.assertEqual((candidate['stack'], candidate['component'], candidate['policy_key']),
                         ('orgs/reference/dev', 'intune-reference', KEY))
        self.assertEqual((candidate['object_id'], candidate['pointer']), (OBJECT, '/vars/policies/' + KEY))
        self.assertEqual((candidate['backend'], candidate['backend_source']), ('local', 'none_declared'))
        self.assertEqual(candidate['resource_address'], ADDRESS)
        self.assertEqual((candidate['consumer']['status'], candidate['consumer']['logical_stack']), ('verified', 'reference-dev'))
        self.assertEqual(candidate['observed'], {'present': True, 'name': 'Windows Privacy Pilot', 'freshness': 'fresh'})
        self.assertEqual(candidate['state'], 'ready')
        values = [str(self.repo), 'orgs/reference/dev', 'intune-reference', OBJECT, '/vars/policies/' + KEY, COMMIT, 'local', ADDRESS]
        self.assertEqual(shlex.split(candidate['terminal_command']), ['repository-import'] + values)
        self.assertEqual(shlex.split(candidate['command']), [
            'intune-iac', 'workbench', 'repository-import', '--root', str(self.store.root), '--repo', str(self.repo),
            '--stack', 'orgs/reference/dev', '--component', 'intune-reference', '--object', OBJECT,
            '--pointer', '/vars/policies/' + KEY, '--revision', COMMIT, '--backend', 'local', '--resource-address', ADDRESS])
        # The command records exactly what the survey showed, and the contract holds.
        from intune_iac.workbench_views import import_repository
        intent = import_repository(self.store, *values)
        self.assertEqual(intent['data']['consumer']['status'], 'verified')
        # No stack value is printed: the description lives only in the stack file.
        self.assertIn('Synthetic reference', (self.repo / STACK).read_text())
        self.assertNotIn('Synthetic reference', json.dumps(value))

    def test_a_recorded_policy_is_shown_as_recorded_and_offers_a_refresh_once_it_changes(self):
        commit(self.repo)
        intent = self.import_intent()
        [candidate] = self.survey()['candidates']
        self.assertEqual(candidate['state'], 'recorded')
        self.assertEqual((candidate['recorded']['intent_id'], candidate['recorded']['freshness']), (intent['artifact_id'], 'current'))
        self.assertIsNone(candidate['command']); self.assertIsNone(candidate['terminal_command'])
        self.assertIn('propose-from-intent', candidate['explanation'])
        self.edit_description('Edited in the repository.')
        [candidate] = self.survey()['candidates']
        self.assertEqual((candidate['state'], candidate['recorded']['freshness']), ('recorded', 'stale'))
        self.assertEqual(shlex.split(candidate['command']), ['intune-iac', 'workbench', 'repository-refresh', '--root',
                                                             str(self.store.root), '--object', OBJECT, '--revision', COMMIT])
        self.assertIn('repository-refresh ' + COMMIT, candidate['explanation'])

    def test_a_policy_for_another_tenant_is_not_offered_to_this_store(self):
        from intune_iac.workbench_store import WorkbenchStore
        commit(self.repo)
        other = WorkbenchStore.create(self.root / 'other-store', OTHER_TENANT)
        [candidate] = self.survey(store=other)['candidates']
        self.assertEqual(candidate['state'], 'other_tenant')
        self.assertIsNone(candidate['command'])
        self.assertIn(TENANT, candidate['explanation']); self.assertIn(OTHER_TENANT, candidate['explanation'])

    def test_a_shared_policy_map_is_refused_before_anything_is_recorded(self):
        commit(self.repo)
        document = self.stack()
        policies = document['components']['terraform']['intune-reference']['vars']['policies']
        second = 'p_' + UUID(TENANT).hex + '_' + 'd' * 32
        policies[second] = copy.deepcopy(policies[KEY])
        self.write_stack(document)
        candidates = self.survey()['candidates']
        self.assertEqual([c['policy_key'] for c in candidates], sorted([KEY, second]))
        for candidate in candidates:
            self.assertEqual(candidate['state'], 'blocked_by_component')
            self.assertIn('policy_keys_not_exactly_adopted', candidate['consumer']['reasons'])
            self.assertIsNone(candidate['command'])
            self.assertIn('one policy per stack and component', candidate['explanation'])

    def test_a_repository_without_a_readable_commit_asks_for_one(self):
        value = self.survey()
        self.assertIsNone(value['revision'])
        [candidate] = value['candidates']
        self.assertEqual((candidate['state'], candidate['missing']), ('needs_choice', ['revision']))
        self.assertIsNone(candidate['command'])
        self.assertIn('COMMIT', candidate['template'])
        self.assertIn('commit', candidate['explanation'])

    def test_a_key_that_does_not_encode_the_object_asks_for_it(self):
        commit(self.repo)
        document = self.stack()
        policies = document['components']['terraform']['intune-reference']['vars']['policies']
        policies['windows_privacy'] = policies.pop(KEY)
        self.write_stack(document)
        [candidate] = self.survey()['candidates']
        self.assertEqual((candidate['state'], candidate['object_id']), ('needs_object', None))
        self.assertIsNone(candidate['command'])
        self.assertIn('OBJECT_ID', candidate['template'])

    def test_a_directory_that_is_not_an_atmos_repository_is_explained(self):
        empty = self.root / 'empty'; empty.mkdir()
        value = self.survey(repo=empty)
        self.assertEqual((value['status'], value['candidates']), ('blocked', []))
        self.assertTrue(value['blockers'])
        self.assertIn('Atmos', value['next_action'])

    def test_the_survey_writes_nothing(self):
        commit(self.repo)
        before = (tree(self.repo), len(self.store.artifacts()))
        self.survey()
        self.assertEqual((tree(self.repo), len(self.store.artifacts())), before)


class EntryScreenTests(unittest.TestCase):
    VALUE = {'schema_version': 'workbench-repository-entry/1', 'repository': '/work/repository', 'status': 'discovered',
             'revision': COMMIT, 'tenant_id': TENANT, 'blockers': [], 'execution_authorized': False, 'cloud_authority': False,
             'components': [{'stack': 'orgs/reference/dev', 'manifest': STACK, 'component': 'intune-reference', 'selectable': True, 'policies': 2}],
             'next_action': 'Two policies.',
             'candidates': [
                 {'number': 1, 'stack': 'orgs/reference/dev', 'component': 'intune-reference', 'policy_key': KEY, 'object_id': OBJECT,
                  'observed': {'present': True, 'name': 'Windows Privacy Pilot', 'freshness': 'fresh'}, 'state': 'ready',
                  'backend': 'local', 'backend_source': 'none_declared', 'resource_address': ADDRESS,
                  'explanation': 'Ready to record.', 'terminal_command': 'repository-import one', 'command': 'intune-iac one'},
                 {'number': 2, 'stack': 'orgs/reference/dev', 'component': 'intune-reference', 'policy_key': 'windows_privacy',
                  'object_id': None, 'observed': {'present': False}, 'state': 'needs_object', 'backend': 'local',
                  'backend_source': 'none_declared', 'resource_address': None,
                  'explanation': 'Supply the object ID.', 'terminal_command': None, 'command': None}]}

    def test_each_policy_shows_its_state_and_the_focus_marker(self):
        from intune_iac.workbench_screens import repository_entry_lines
        from intune_iac.workbench_tui import cell_width
        lines = repository_entry_lines(self.VALUE, 100, focus=1)
        joined = '\n'.join(lines)
        self.assertEqual(lines[0], '[REPOSITORY ENTRY] /work/repository')
        self.assertIn('  1  Windows Privacy Pilot (22222222)', joined)
        self.assertIn('> 2  not observed in this store', joined)
        self.assertIn('ready to record', joined); self.assertIn('needs the object ID', joined)
        self.assertIn('Enter on a policy puts its exact command in the command bar for review', joined)
        for line in lines:
            self.assertLessEqual(cell_width(line), 100, line)
        for line in repository_entry_lines(self.VALUE, 60, focus=0):
            self.assertLessEqual(cell_width(line), 60, line)

    def workspace(self, value):
        from intune_iac.workbench_tui import Workspace
        workspace = Workspace.__new__(Workspace)
        workspace.__dict__.update(
            tab=8, value=value, selected=None, facts={}, highlight=0, scroll=0, mode=None, buffer='', cursor=0,
            pasting=False, input_overflow=False, notice='', last_command='repository-entry /work/repository',
            view_command='repository-entry /work/repository', page_command='overview', rows=[], operation_rows=[],
            operation_highlight=0, active_operation=None, execution_result=None, active_service=None, active_adoption=None,
            active_adoption_plan=None, pending=deque(), size=(100, 40), submission_key='enter', entry_focus=0)
        workspace.draw = lambda: None
        workspace._terminal_size = lambda: (100, 40)
        return workspace

    def keys(self, workspace, keys):
        # Records the notice shown before each key is read, since a later key may replace it.
        class Reader:
            def __init__(self, keys): self.keys, self.notices = list(keys), []
            def read(self): self.notices.append(workspace.notice); return self.keys.pop(0)
        workspace.key_reader = Reader(keys)
        return workspace.input('')

    def test_enter_puts_the_focused_command_in_the_bar_and_only_a_submit_runs_it(self):
        workspace = self.workspace(self.VALUE)
        self.assertEqual(self.keys(workspace, ['enter', 'enter']), 'repository-import one')

    def test_escape_discards_the_prefilled_command(self):
        workspace = self.workspace(self.VALUE)
        self.assertEqual(self.keys(workspace, ['enter', 'escape', ('char', 'q')]), 'quit')

    def test_a_policy_with_nothing_to_run_explains_instead(self):
        workspace = self.workspace(self.VALUE)
        self.assertEqual(self.keys(workspace, ['down', 'enter', ('char', 'q')]), 'quit')
        self.assertEqual(workspace.key_reader.notices[-1], 'Nothing to run for policy 2; its explanation is above.')
        self.assertIsNone(workspace.mode)

    def test_the_whole_prefilled_command_is_shown_for_review(self):
        workspace = self.workspace(self.VALUE)
        before = '\n'.join(workspace._surface_summary(60))
        workspace.mode, workspace.buffer = 'command', 'repository-import ' + 'x' * 150
        text = '\n'.join(workspace._surface_summary(60))
        self.assertIn('[COMMAND FOR REVIEW]', text); self.assertNotIn('[COMMAND FOR REVIEW]', before)
        # Every character of the long argument is on screen, wrapped, not only the tail the one-line bar shows.
        self.assertEqual(text.count('x') - before.count('x'), 150)

    def test_the_entry_renders_on_the_repository_surface(self):
        workspace = self.workspace(self.VALUE)
        text = '\n'.join(workspace._surface_summary(100))
        self.assertIn('[REPOSITORY ENTRY]', text); self.assertNotIn('[EXACT', text)


if __name__ == '__main__':
    unittest.main()
