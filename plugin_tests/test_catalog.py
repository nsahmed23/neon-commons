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


if __name__ == '__main__':
    unittest.main()
