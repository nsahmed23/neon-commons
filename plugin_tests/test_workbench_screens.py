"""Readable workspace screens: pure renderers with hand-written expectations."""
import unittest

from intune_iac.workbench_diff import field_changes
from intune_iac.workbench_screens import change_lines, repository_lines
from intune_iac.workbench_tui import cell_width
from plugin_tests.test_workbench_diff import BODY, CAMERA, GROUP_B, LOCATION, setting

import copy

OBSERVED = 'Synthetic reference; not production advice.'
EDITED = 'Synthetic reference; reviewed repository edit.'


def body(**changes):
    value = copy.deepcopy(BODY); value.update(changes); return value


class ChangeLinesTests(unittest.TestCase):
    def fits(self, lines, width):
        for line in lines:
            self.assertLessEqual(cell_width(line), width, line)

    def test_no_change_is_said_plainly(self):
        lines = change_lines(field_changes(body(), body()), 100)
        self.assertEqual(lines[0], 'NO CONFIGURATION CHANGE')
        self.fits(lines, 100)

    def test_wide_layout_puts_before_and_after_side_by_side(self):
        lines = change_lines(field_changes(body(description=OBSERVED), body(description=EDITED)), 120)
        self.assertTrue(lines[0].startswith('1 FIELD CHANGE'))
        header = next(line for line in lines if line.startswith('FIELD'))
        self.assertIn('BEFORE (observed)', header); self.assertIn('AFTER (desired)', header)
        row = next(line for line in lines if line.startswith('description'))
        self.assertIn('"' + OBSERVED + '"', row); self.assertIn('"' + EDITED + '"', row)
        self.fits(lines, 120)

    def test_narrow_layout_stacks_before_and_after(self):
        lines = change_lines(field_changes(body(description=OBSERVED), body(description=EDITED)), 60)
        joined = '\n'.join(lines)
        self.assertIn('description', joined)
        self.assertIn('  before  "Synthetic reference;', joined)
        self.assertIn('  after   "Synthetic reference;', joined)
        self.fits(lines, 60)

    def test_null_and_empty_are_distinguishable(self):
        lines = change_lines(field_changes(body(description=None), body(description='')), 60)
        joined = '\n'.join(lines)
        self.assertIn('before  null', joined); self.assertIn('after   ""', joined)

    def test_setting_change_names_record_definition_and_leaf(self):
        after = body(); after['settings']['settings'][0]['settingInstance']['choiceSettingValue']['value'] = LOCATION + '_1'
        joined = '\n'.join(change_lines(field_changes(body(), after), 120))
        self.assertIn('settings 0', joined)
        self.assertIn(LOCATION, joined)
        self.assertIn('/settingInstance/choiceSettingValue/value', joined)
        self.assertIn('"' + LOCATION + '_1"', joined)

    def test_added_and_removed_targets_and_reordered_settings(self):
        after = body(); after['assignments'].append({'type': 'exclusionGroupAssignmentTarget', 'group_id': GROUP_B, 'filter_type': 'none'})
        joined = '\n'.join(change_lines(field_changes(body(), after), 100))
        self.assertIn('assignments  + exclusionGroupAssignmentTarget group ' + GROUP_B, joined)
        two = body(); two['settings']['settings'].append(setting('1', CAMERA, CAMERA + '_0'))
        swapped = copy.deepcopy(two); swapped['settings']['settings'].reverse()
        joined = '\n'.join(change_lines(field_changes(two, swapped), 100))
        self.assertIn('settings order  0, 1  ->  1, 0', joined)

    def test_unknown_comparison_is_explicit(self):
        lines = change_lines(field_changes(body(), ['not', 'a', 'policy']), 80)
        self.assertEqual(lines[0], 'CHANGE COMPARISON UNKNOWN')

    def test_hostile_text_is_escaped(self):
        lines = change_lines(field_changes(body(description=OBSERVED), body(description='edit\x1b[31m‮evil')), 120)
        joined = '\n'.join(lines)
        self.assertNotIn('\x1b', joined); self.assertNotIn('‮', joined)


class FrameTextTests(unittest.TestCase):
    TABS = ('Estate', 'Inspector', 'Relationships', 'History', 'Plan', 'Execution', 'Coverage', 'Help', 'Repository')

    def test_tab_line_marks_the_active_surface_and_compacts_when_narrow(self):
        from intune_iac.workbench_screens import tab_line
        wide = tab_line(self.TABS, 4, 160)
        self.assertIn('[5 Plan]', wide); self.assertIn('9 Repository', wide)
        narrow = tab_line(self.TABS, 8, 80)
        self.assertLessEqual(cell_width(narrow), 80)
        self.assertIn('[9 Repo]', narrow); self.assertIn('1 Est', narrow)

    def test_context_strip_uses_short_identities_and_fits(self):
        from intune_iac.workbench_screens import context_strip
        tenant, policy = '11111111-1111-4111-8111-111111111111', '22222222-2222-4222-8222-222222222222'
        facts = {'name': 'Windows Privacy Pilot', 'observation': 'fresh', 'repository': 'stale', 'operation': 'prepared'}
        wide = context_strip(tenant, policy, facts, 160)
        self.assertEqual(wide, 'TENANT 11111111 | POLICY Windows Privacy Pilot (22222222) | OBSERVED fresh | REPOSITORY stale | OPERATION prepared')
        narrow = context_strip(tenant, policy, facts, 80)
        self.assertLessEqual(cell_width(narrow), 80)
        self.assertTrue(narrow.startswith('POLICY Windows Privacy Pilot (22222222)'))
        self.assertEqual(context_strip(tenant, None, {}, 80), 'TENANT 11111111 | POLICY none selected')
        done = dict(facts, operation='succeeded_verified')
        self.assertEqual(context_strip(tenant, policy, done, 80),
                         'POLICY 22222222 | OBS fresh | REPO stale | OP succeeded_verified')

    def test_epoch_times_are_shown_as_utc(self):
        from intune_iac.workbench_screens import utc_time
        self.assertEqual(utc_time(1791981362), '2026-10-14T12:36:02Z')
        self.assertEqual(utc_time('not a time'), 'not a time')


class RepositoryLinesTests(unittest.TestCase):
    STATUS = {'schema_version': 'workbench-repository-status/1', 'object_id': '22222222-2222-4222-8222-222222222222',
              'repository_intent_id': 'a' * 64, 'scope': {'repository': '/home/engineer/repo', 'stack': 'orgs/reference/dev',
              'component': 'intune-reference', 'backend': 'local'}, 'effective_pointer': '/vars/policies/p_x',
              'source_revision': 'b' * 40, 'revision_content_verified': True,
              'consumer': {'status': 'verified', 'logical_stack': 'reference-dev', 'reasons': []},
              'next_action': 'The repository still matches this intent.'}

    def test_current_repository(self):
        status = dict(self.STATUS, freshness={'status': 'current', 'sources': {'added': [], 'removed': [], 'changed': []},
                                              'field_changes': field_changes(body(), body()), 'consumer': {'status': 'verified'}})
        lines = repository_lines(status, 100)
        self.assertEqual(lines[0], 'REPOSITORY MATCHES THE RECORDED INTENT')
        joined = '\n'.join(lines)
        self.assertIn('orgs/reference/dev (reference-dev) / intune-reference', joined)
        self.assertIn('Revision ' + 'b' * 40 + ' (content verified)', joined)
        self.assertIn('Consumer verified', joined)

    def test_stale_repository_names_sources_fields_and_next_step(self):
        status = dict(self.STATUS, next_action='Refresh the intent.', freshness={'status': 'stale',
            'sources': {'added': ['components/terraform/intune-reference/override.tf'], 'removed': [], 'changed': ['stacks/orgs/reference/dev.yaml']},
            'field_changes': field_changes(body(description=OBSERVED), body(description=EDITED)), 'consumer': {'status': 'verified'}})
        lines = repository_lines(status, 100)
        self.assertEqual(lines[0], 'REPOSITORY CHANGED SINCE THE RECORDED INTENT')
        joined = '\n'.join(lines)
        self.assertIn('changed  stacks/orgs/reference/dev.yaml', joined)
        self.assertIn('added    components/terraform/intune-reference/override.tf', joined)
        self.assertIn('BEFORE (recorded intent)', joined); self.assertIn('AFTER (repository now)', joined)
        self.assertIn('Next: Refresh the intent.', joined)
        for line in lines:
            self.assertLessEqual(cell_width(line), 100, line)


if __name__ == '__main__':
    unittest.main()
