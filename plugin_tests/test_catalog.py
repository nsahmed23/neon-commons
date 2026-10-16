"""The integration catalog (PKG-UXVIS-3): six states apart, facts only, no implied universal support."""
import copy
import json
import unittest

from plugin_tests import test_readiness as tr
from plugin_tests.test_signin_not_permission import GOOD

GOALS = ('inspect', 'discover', 'adopt', 'change')
STATES = ('available', 'configured', 'authenticated', 'operation_ready', 'blocked', 'unsupported')
UNKNOWN = 'unknown (no record establishes it)'


def doctor():
    return dict(tr.doctor_report(), host_capabilities=tr.host_report())


def survey(*items):
    return tr.survey_of(*items)


def catalog(*items, signin=None, manifest=None, goal=None):
    from intune_iac import catalog as module
    return module.build(survey(*items), doctor=doctor(), signin=signin, manifest=manifest, goal=goal)


def goals_of(value):
    return {item['goal']: item for item in value['integrations'][0]['goals']}


class RecordTests(unittest.TestCase):
    def test_one_record_for_the_one_integration_the_manifest_holds(self):
        value = catalog()
        self.assertEqual([item['id'] for item in value['integrations']], ['intune'])
        self.assertEqual(value['integrations'][0]['label'], 'Microsoft Intune')
        self.assertEqual(value['schema_version'], 'integration-catalog/1')
        self.assertFalse(value['execution_authorized'])
        self.assertFalse(value['cloud_authority'])
        json.dumps(value)

    def test_every_goal_carries_the_six_states_apart(self):
        for name, goal in goals_of(catalog()).items():
            for state in STATES:
                self.assertIn(state, goal, name)

    def test_a_goal_filter_keeps_that_goal_only(self):
        self.assertEqual(list(goals_of(catalog(goal='adopt'))), ['adopt'])

    def test_available_comes_from_the_manifests_operations(self):
        goals = goals_of(catalog())
        for name in GOALS:
            self.assertEqual(goals[name]['available']['state'], 'available', name)
            self.assertEqual(goals[name]['available']['missing_operations'], [])
        self.assertIn('discovery', goals['discover']['available']['operations'])
        self.assertEqual(goals['discover']['available']['evidence_classes'], ['local_evidence_only'])
        self.assertEqual(goals['change']['available']['evidence_classes'], ['synthetic_local_process_only'])

    def test_a_goal_whose_operations_the_manifest_does_not_list_is_unsupported(self):
        from intune_iac import integration_manifest
        manifest = copy.deepcopy(integration_manifest.load())
        for kind in manifest['object_kinds']:
            kind['operations'] = [item for item in kind['operations'] if item['name'] != 'adoption']
        goals = goals_of(catalog(manifest=manifest))
        self.assertEqual(goals['adopt']['available']['state'], 'not_available')
        self.assertEqual(goals['adopt']['unsupported']['state'], 'unsupported')
        self.assertIn('adoption', ' '.join(goals['adopt']['unsupported']['reasons']))
        self.assertEqual(goals['discover']['unsupported']['state'], 'none_recorded')

    def test_the_live_blockers_are_carried_as_recorded(self):
        from intune_iac import integration_manifest
        blockers = integration_manifest.load()['live_blockers']
        value = catalog()
        self.assertEqual(value['integrations'][0]['live_blockers'], blockers)
        for goal in goals_of(value).values():
            self.assertEqual(goal['unsupported']['live_blockers'], blockers)

    def test_configured_follows_the_local_input_rows_only(self):
        offline = goals_of(catalog())
        self.assertEqual(offline['adopt']['configured']['state'], 'no')
        self.assertIn('Repository', offline['adopt']['configured']['not_ready'])
        full = goals_of(catalog(tr.repository_item(), tr.context_item()))
        self.assertNotIn('Repository', full['adopt']['configured']['not_ready'])
        self.assertNotIn('Integration and service', full['adopt']['configured']['inputs_checked'])

    def test_authenticated_is_not_checked_without_the_check_and_says_how_to_run_it(self):
        for name, goal in goals_of(catalog()).items():
            self.assertEqual(goal['authenticated']['state'], 'not_checked', name)
            self.assertIn('not checked', goal['authenticated']['message'])
            self.assertIn('--check-signin azure', goal['authenticated']['message'])
        self.assertIn('--goal discover --check-signin azure', goals_of(catalog(goal='discover'))['discover']['authenticated']['message'])

    def test_a_usable_sign_in_reads_authenticated_and_never_permission(self):
        value = catalog(tr.repository_item(), tr.context_item(tenant=GOOD['accounts'][0]['tenant']), signin={'azure': GOOD})
        goal = goals_of(value)['discover']
        self.assertEqual(goal['authenticated']['state'], 'authenticated')
        self.assertIn('not permission', goal['authenticated']['permission'])
        self.assertNotEqual(goal['operation_ready']['state'], 'yes')

    def test_a_sign_in_that_is_not_usable_is_not_authenticated(self):
        expired = dict(GOOD, accounts=[dict(GOOD['accounts'][0], session='expired')])
        goal = goals_of(catalog(tr.context_item(tenant=GOOD['accounts'][0]['tenant']), signin={'azure': expired}))['discover']
        self.assertEqual(goal['authenticated']['state'], 'not_authenticated')
        self.assertIn('expired', goal['authenticated']['status'])
        unknown = {'provider': 'azure', 'state': 'unknown', 'reason': 'cli_missing', 'accounts': []}
        goal = goals_of(catalog(signin={'azure': unknown}))['discover']
        self.assertEqual(goal['authenticated']['state'], 'unknown')

    def test_operation_ready_is_the_readiness_status_and_nothing_more(self):
        from intune_iac import readiness
        value = catalog(tr.repository_item(), tr.context_item())
        model = readiness.readiness(survey(tr.repository_item(), tr.context_item()), tr.host_report(), doctor())
        for name, goal in goals_of(value).items():
            self.assertEqual(goal['operation_ready']['status'], model['operations'][name]['status'], name)
            self.assertEqual(goal['operation_ready']['state'] == 'yes', model['operations'][name]['status'] == 'ready')

    def test_blocked_names_the_first_prerequisite_and_its_next_action_in_the_readiness_words(self):
        from intune_iac import readiness
        model = readiness.readiness(survey(), tr.host_report(), doctor())
        goal = goals_of(catalog())['discover']
        first = next(row for row in model['operations']['discover']['rows'] if row['needed'] and row['state'] != 'ready')
        self.assertEqual(goal['blocked']['state'], 'blocked')
        self.assertEqual(goal['blocked']['row'], first['label'])
        self.assertEqual(goal['blocked']['next_action'], first['next_action'])
        self.assertEqual(goal['blocked']['missing'], first['missing'][0])

    def test_object_kinds_show_a_level_only_where_a_record_establishes_it(self):
        kinds = {item['id']: item for item in catalog()['integrations'][0]['object_kinds']}
        self.assertEqual(kinds['settings_catalog_policy']['level'], UNKNOWN)
        self.assertIsNone(kinds['settings_catalog_policy']['level_record'])
        self.assertEqual(kinds['assignment_target_reference']['level'], UNKNOWN)
        self.assertEqual(kinds['win32_app']['level'], 'review-only')
        self.assertEqual(kinds['win32_app']['level_record'], 'family-coverage.csv')
        self.assertEqual(kinds['settings_catalog_policy']['evidence_classes'],
                         ['local_evidence_only', 'synthetic_local_process_only'])
        for item in kinds.values():
            self.assertTrue(item['scope'])

    def test_families_show_the_release_stage_and_live_status_as_recorded(self):
        families = catalog()['integrations'][0]['families']
        self.assertEqual(len(families), 9)
        for item in families:
            self.assertEqual(item['live'], 'not run')
            self.assertTrue(item['release_stage'])
        self.assertEqual(families[0]['release_stage'], 'offline reference')


def flat(lines):
    return " ".join(" ".join(lines).split())


def text_of(value, width=100):
    from intune_iac import catalog as module
    return module.catalog_lines(value, width)


class NoUniversalSupportTests(unittest.TestCase):
    def test_the_text_says_no_other_integration_is_available_and_lists_only_the_manifests_one(self):
        text = flat(text_of(catalog()))
        self.assertIn('No other integration is available in this build.', text)
        self.assertIn('Microsoft Intune', text)
        self.assertEqual(catalog()['other_integrations'], 'No other integration is available in this build.')
        for name in ('Terraform Cloud', 'Jamf', 'Workspace ONE', 'Ansible', 'Okta', 'ServiceNow'):
            self.assertNotIn(name, text)

    def test_an_object_kind_the_manifest_does_not_list_is_said_to_be_unsupported_not_omitted_silently(self):
        text = flat(text_of(catalog()))
        self.assertIn('An object kind or goal not listed here is unsupported', text)

    def test_every_state_is_a_word_for_every_goal(self):
        lines = text_of(catalog())
        for goal in GOALS:
            start = next(i for i, line in enumerate(lines) if line.strip() == 'GOAL ' + goal)
            block = lines[start + 1:start + 1 + 40]
            labels = [line.strip().split(':')[0] for line in block if line.startswith('    ') and not line.startswith('     ')]
            self.assertEqual(labels[:6], ['available', 'configured', 'authenticated', 'operation-ready', 'blocked', 'unsupported'])

    def test_the_json_form_carries_the_same_states_as_the_text(self):
        value = catalog(tr.repository_item(), tr.context_item())
        lines = '\n'.join(text_of(value))
        goals = goals_of(value)
        self.assertIn('authenticated:   not checked', lines)
        for name in GOALS:
            self.assertEqual(goals[name]['authenticated']['state'], 'not_checked')
            ready = goals[name]['operation_ready']
            self.assertIn('operation-ready: %s (readiness status: %s)' % (ready['state'], ready['status']), lines)

    def test_the_text_never_calls_an_unchecked_sign_in_authenticated_and_never_implies_permission(self):
        text = flat(text_of(catalog()))
        self.assertNotIn('authenticated: yes', text)
        self.assertNotIn('authenticated: authenticated', text)
        self.assertIn('not checked', text)
        signed = catalog(tr.context_item(tenant=GOOD['accounts'][0]['tenant']), signin={'azure': GOOD})
        text = flat(text_of(signed))
        self.assertIn('authenticated: authenticated', text)
        self.assertIn('not permission for any operation', text)

    def test_unknown_levels_stay_explicit_and_families_say_live_not_run(self):
        text = flat(text_of(catalog()))
        self.assertIn('qualification unknown (no record establishes it)', text)
        self.assertIn('qualification review-only (record: family-coverage.csv)', text)
        self.assertIn('live: not run', text)
        self.assertNotIn('adoption-qualified', text)
        self.assertNotIn('change-qualified', text)

    def test_the_lines_fit_120_80_and_60_columns_in_ascii(self):
        value = catalog(tr.repository_item(), tr.context_item())
        for width in (120, 80, 60):
            for line in text_of(value, width):
                self.assertLessEqual(len(line), width, line)
                self.assertTrue(all(32 <= ord(c) < 127 for c in line), repr(line))


class ProjectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from plugin_tests.test_start_goal import Fixtures
        cls.dirs = Fixtures.get()

    @classmethod
    def tearDownClass(cls):
        from plugin_tests.test_start_goal import Fixtures
        Fixtures.release()

    def model(self, name, goal=None, relative_to=None):
        from intune_iac import catalog as module, entry
        value = entry.survey(self.dirs[name], relative_to=relative_to)
        return value, module.build(value, doctor=doctor(), goal=goal, relative_to=relative_to)

    def commands(self, lines):
        from plugin_tests.test_readiness import ReadinessTests
        from plugin_tests.test_start_goal import StartGoalTests
        joined = StartGoalTests('logical_lines').logical_lines(lines)
        extractor = ReadinessTests('printed_commands')
        return [tokens for line in joined for tokens in extractor.printed_commands(line)]

    def test_every_surveyed_item_is_listed_with_its_state_and_a_resume_command_where_one_exists(self):
        value, model = self.model('full')
        projects = model['projects']
        self.assertEqual([p['path'] for p in projects], [i['path'] for i in value['items']])
        self.assertEqual({p['kind'] for p in projects} & {'store', 'repository', 'wizard_session'},
                         {'store', 'repository', 'wizard_session'} & {i['kind'] for i in value['items']})
        for project in projects:
            self.assertTrue(project['state'], project)
            self.assertTrue(project['command'] or project['note'], project)
        kinds = {p['kind']: p for p in projects}
        self.assertIn('workbench workspace --root', kinds['store']['command'])

    def test_every_printed_command_parses_with_the_product_parser(self):
        import shlex
        from intune_iac import cli
        parser = cli.parser()
        checked = 0
        for name in self.dirs:
            _, model = self.model(name)
            for project in model['projects']:
                if project['command']:
                    argv = shlex.split(project['command'])
                    self.assertEqual(argv[0], 'intune-iac')
                    parser.parse_args(argv[1:])
                    checked += 1
            for width in (60, 80, 120):
                for tokens in self.commands(text_of(model, width)):
                    import contextlib, io
                    with contextlib.redirect_stderr(io.StringIO()) as err:
                        try:
                            parser.parse_args(['3' if token == 'FD' else token for token in tokens])
                        except SystemExit:
                            self.fail('rejected: intune-iac %s\n%s' % (' '.join(tokens), err.getvalue()))
                    checked += 1
        self.assertGreater(checked, 20)

    def test_commands_work_from_the_directory_start_was_run_in(self):
        import os
        import shlex
        from pathlib import Path
        base = Path(self.dirs['full']).parent
        _, model = self.model('full', relative_to=str(base))
        for project in model['projects']:
            if project['command'] and project['kind'] in ('store', 'wizard_session'):
                shown = shlex.quote(os.path.relpath(Path(self.dirs['full']) / project['path'], base).replace(os.sep, '/'))
                self.assertIn(shown, project['command'])
                self.assertTrue((base / shown.strip("'")).exists(), shown)

    def test_an_empty_directory_lists_no_project_and_says_so(self):
        _, model = self.model('offline')
        self.assertEqual(model['projects'], [])
        self.assertIn('Nothing recognized here yet.', flat(text_of(model)))

    def test_the_catalog_ends_with_one_next_action_per_goal_or_for_the_goal_chosen(self):
        _, every = self.model('offline')
        lines = text_of(every)
        start = lines.index('NEXT ACTION')
        self.assertEqual([line for line in lines[start + 1:] if line.startswith('  ') and line[2] != ' '][:4],
                         ['  %s:' % goal for goal in GOALS])
        _, chosen = self.model('offline', goal='adopt')
        lines = text_of(chosen)
        tail = lines[lines.index('NEXT ACTION') + 1:]
        self.assertEqual([line for line in tail if line.startswith('  ') and line[2] != ' '], ['  adopt:'])
        self.assertEqual(lines[-1].strip() != '', True)

    def test_the_next_action_is_the_blocking_rows_action_or_says_none_is_needed(self):
        _, model = self.model('offline')
        for goal in goals_of(model).values():
            expected = goal['blocked']['next_action'] or 'No action needed.'
            self.assertEqual(goal['next_action'], expected)


class CommandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from plugin_tests.test_start_goal import Fixtures
        cls.dirs = Fixtures.get()

    @classmethod
    def tearDownClass(cls):
        from plugin_tests.test_start_goal import Fixtures
        Fixtures.release()

    def run_cli(self, *argv, width=100, detect=None):
        import contextlib
        import io
        import os
        from unittest.mock import patch
        from intune_iac.cli import main
        out = io.StringIO()
        with patch('shutil.get_terminal_size', return_value=os.terminal_size((width, 40))), \
                patch('intune_iac.signin.detect', detect or (lambda *a, **k: self.fail('a sign-in check ran unasked'))), \
                contextlib.redirect_stdout(out):
            code = main(['catalog', *argv])
        return code, out.getvalue()

    def test_the_command_prints_the_catalog_and_exits_zero(self):
        code, text = self.run_cli(str(self.dirs['full']))
        self.assertEqual(code, 0)
        self.assertIn('INTEGRATION CATALOG', text)
        self.assertIn('No other integration is available in this build.', text)

    def test_json_carries_the_same_states(self):
        code, text = self.run_cli(str(self.dirs['full']), '--json')
        self.assertEqual(code, 0)
        value = json.loads(text)
        self.assertEqual(value['schema_version'], 'integration-catalog/1')
        for goal in value['integrations'][0]['goals']:
            for state in STATES:
                self.assertIn(state, goal)
        self.assertTrue(value['projects'])
        self.assertEqual(value['other_integrations'], 'No other integration is available in this build.')

    def test_goal_keeps_one_goal_and_an_unknown_goal_is_refused_by_the_parser(self):
        code, text = self.run_cli(str(self.dirs['full']), '--goal', 'discover', '--json')
        self.assertEqual([g['goal'] for g in json.loads(text)['integrations'][0]['goals']], ['discover'])
        with self.assertRaises(SystemExit):
            import contextlib, io
            with contextlib.redirect_stderr(io.StringIO()):
                self.run_cli(str(self.dirs['full']), '--goal', 'prepare')

    def test_no_sign_in_check_runs_unless_asked_and_the_asked_check_feeds_the_authenticated_state(self):
        code, text = self.run_cli(str(self.dirs['context']), '--json')
        self.assertEqual({g['authenticated']['state'] for g in json.loads(text)['integrations'][0]['goals']}, {'not_checked'})
        code, text = self.run_cli(str(self.dirs['context']), '--json', '--check-signin', 'azure', detect=lambda *a, **k: {'azure': GOOD})
        states = {g['authenticated']['state'] for g in json.loads(text)['integrations'][0]['goals']}
        self.assertNotEqual(states, {'not_checked'})

    def test_the_default_directory_is_the_current_one(self):
        import os
        old = os.getcwd()
        os.chdir(self.dirs['offline'])
        try:
            code, text = self.run_cli('--json')
        finally:
            os.chdir(old)
        self.assertEqual(code, 0)
        self.assertEqual(os.path.realpath(json.loads(text)['directory']), os.path.realpath(self.dirs['offline']))

    def test_start_names_the_catalog_in_one_line_and_does_not_repeat_the_readiness_block(self):
        import contextlib
        import io
        import os
        import shlex
        from unittest.mock import patch
        from intune_iac import cli
        for argv in ([str(self.dirs['full'])], [str(self.dirs['full']), '--goal', 'discover']):
            out = io.StringIO()
            with patch('shutil.get_terminal_size', return_value=os.terminal_size((120, 40))), contextlib.redirect_stdout(out):
                cli.main(['start', *argv])
            lines = out.getvalue().split('\n')
            pointer = [line for line in lines if 'intune-iac catalog' in line]
            self.assertEqual(len(pointer), 1, pointer)
            self.assertNotIn('available:', out.getvalue())
            tokens = shlex.split(pointer[0].split('intune-iac ', 1)[1].rstrip('.'))
            cli.parser().parse_args(tokens)
        self.assertEqual(tokens[0], 'catalog')


if __name__ == '__main__':
    unittest.main()
