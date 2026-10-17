"""Readable workspace screens: pure renderers with hand-written expectations."""
from pathlib import Path
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


# One row of the device matrix: optionally the devices (or cells) it holds, then the cells in brackets.
import re as _re  # noqa: E402
MATRIX_ROW = _re.compile(r'^    (?:(?:devices|cells) \d+-\d+ +)?\[([#x~?.]+)\]$')

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
        # The longer line wraps; compared with the wrapping undone.
        self.assertIn('assignments + exclusionGroupAssignmentTarget Unresolved group identity ' + GROUP_B, ' '.join(joined.split()))
        two = body(); two['settings']['settings'].append(setting('1', CAMERA, CAMERA + '_0'))
        swapped = copy.deepcopy(two); swapped['settings']['settings'].reverse()
        joined = '\n'.join(change_lines(field_changes(two, swapped), 100))
        self.assertIn('settings order  0, 1  ->  1, 0', joined)

    def test_an_added_or_removed_setting_shows_its_value(self):
        two = body(); two['settings']['settings'].append(setting('1', CAMERA, CAMERA + '_0'))
        added = '\n'.join(change_lines(field_changes(body(), two), 140))
        self.assertIn('settings 1 ' + CAMERA + '  added', added)
        self.assertIn('(absent)', added)
        self.assertIn('"' + CAMERA + '_0"', added)
        removed = '\n'.join(change_lines(field_changes(two, body()), 140))
        self.assertIn('settings 1 ' + CAMERA + '  removed', removed)
        self.assertIn('"' + CAMERA + '_0"', removed)

    def test_a_cut_comparison_says_where_the_rest_is_and_never_claims_more(self):
        changes = {'status': 'changed', 'complete': False,
                   'changes': [{'field': 'description', 'kind': 'changed', 'path': '/description', 'before': 'a', 'after': 'b'}]}
        plain = ' '.join(change_lines(changes, 140))
        self.assertIn('the comparison stopped there', plain)
        self.assertNotIn('hold the complete result', plain)
        located = ' '.join(change_lines(changes, 140, remainder='the complete before and desired bodies are in r'))
        self.assertIn('the complete before and desired bodies are in r', located)

    def test_unknown_comparison_is_explicit(self):
        lines = change_lines(field_changes(body(), ['not', 'a', 'policy']), 80)
        self.assertEqual(lines[0], 'CHANGE COMPARISON UNKNOWN')

    def test_hostile_text_is_escaped(self):
        lines = change_lines(field_changes(body(description=OBSERVED), body(description='edit\x1b[31m‮evil')), 120)
        joined = '\n'.join(lines)
        self.assertNotIn('\x1b', joined); self.assertNotIn('‮', joined)


class WordWrapTests(unittest.TestCase):
    def test_leading_indentation_is_kept_on_every_wrapped_line(self):
        from intune_iac.workbench_screens import word_wrap
        self.assertEqual(word_wrap('  include  group abc', 80), ['  include  group abc'])
        self.assertEqual(word_wrap('    one two three four', 12), ['    one two', '    three', '    four'])

    def test_long_tokens_are_split_only_when_they_cannot_fit(self):
        from intune_iac.workbench_screens import word_wrap
        self.assertEqual(word_wrap('abcdefghij', 4), ['abcd', 'efgh', 'ij'])
        self.assertEqual(word_wrap('', 10), [''])

    def test_a_token_split_anyway_starts_after_the_current_text(self):
        from intune_iac.workbench_screens import word_wrap
        # A lone '=' is not left on its own line when the value after it must be split regardless.
        self.assertEqual(word_wrap('= "abcdefghijklmnopqrst"', 12), ['= "abcdefghi', 'jklmnopqrst"'])
        # Without enough room for a useful piece, the token starts on the next line as before.
        self.assertEqual(word_wrap('one two three abcdefghijklmnopq', 16), ['one two three', 'abcdefghijklmnop', 'q'])


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
        wide = context_strip(tenant, policy, facts, 160, 'synthetic')
        self.assertEqual(wide, 'SYNTHETIC | TENANT 11111111 | POLICY Windows Privacy Pilot (22222222) | OBS fresh | '
                               'REPO stale | OP prepared')
        # The mode and the tenant lead every width; the states give way first.
        for width in (100, 80, 60):
            narrow = context_strip(tenant, policy, facts, width, 'synthetic')
            self.assertLessEqual(cell_width(narrow), width, narrow)
            self.assertTrue(narrow.startswith('SYNTHETIC | TENANT 11111111 | POLICY '), narrow)
        self.assertEqual(context_strip(tenant, None, {}, 80, 'synthetic'), 'SYNTHETIC | TENANT 11111111 | POLICY none selected')
        self.assertTrue(context_strip(tenant, None, {}, 80).startswith('MODE UNKNOWN | '))
        self.assertTrue(context_strip(tenant, None, {}, 80, 'graph_authenticated_observation').startswith('LIVE READ-ONLY | '))
        done = dict(facts, operation='succeeded_verified')
        self.assertEqual(context_strip(tenant, policy, done, 90, 'synthetic'),
                         'SYNTHETIC | TENANT 11111111 | POLICY 22222222 | OBS fresh | REPO stale | OP verified')
        # Narrower, the states give way before the mode, tenant or policy, and the strip says how many it left out
        # (run 11 item 13): the routine one first, so the repository hazard stays.
        self.assertEqual(context_strip(tenant, policy, done, 80, 'synthetic'),
                         'SYNTHETIC | TENANT 11111111 | POLICY 22222222 | REPO stale | +2 more: ?')

    def test_epoch_times_are_shown_as_utc(self):
        from intune_iac.workbench_screens import utc_time
        self.assertEqual(utc_time(1791981362), '2026-10-14T12:36:02Z')
        self.assertEqual(utc_time('not a time'), 'not a time')


POLICY_ID = '22222222-2222-4222-8222-222222222222'
INSPECT = {'object_id': POLICY_ID, 'name': 'Windows Privacy Pilot', 'observed_at': '2026-10-14T12:34:41.449967Z',
           'coverage': 'complete', 'freshness': 'fresh', 'ownership': 'unknown', 'snapshot_id': '90a2985f' + 'f' * 56,
           'body': copy.deepcopy(BODY)}
ENTRY = {'identifier': LOCATION, 'aliases': [], 'meaning': 'unknown', 'name': None, 'references': [],
         'vendor_documentation': [{'name': 'Let Windows apps access location',
             'meaning': 'Controls whether Windows apps may access location.', 'aliases': ['LetAppsAccessLocation'],
             'csp_uri': './Device/Vendor/MSFT/Policy/Config/Privacy/LetAppsAccessLocation', 'data_type': 'int', 'default_value': 0,
             'allowed_values': [{'value': 0, 'meaning': 'User in control'}, {'value': 1, 'meaning': 'Force allow'}, {'value': 2, 'meaning': 'Force deny'}],
             'applicability': {'scope': 'device', 'minimum_windows_release': 'Windows 10, version 1607', 'editions': ['Pro', 'Enterprise']},
             'documentation': {'publisher': 'Microsoft Learn', 'published_update_at': '2026-09-23T17:34:00Z', 'retrieved_at': '2026-10-07T03:21:49Z',
                               'url': 'https://learn.microsoft.com/en-us/windows/client-management/mdm/policy-csp-privacy#letappsaccesslocation'},
             'graph_value_translation_verified': False,
             'association_basis': 'Explicit local cross-reference to the similarly named CSP; no Graph definition or enum translation attestation'}],
         'local_mapping': [{'entry': {'support_status': 'supported_offline', 'permitted_values': [LOCATION + '_2'],
             'deferred_qualification': ['service_definition_applicability', 'live_tenant_behavior']}}],
         'actual_uses': [{'name': 'Windows Privacy Pilot', 'object_id': POLICY_ID, 'freshness': 'fresh', 'coverage': 'complete', 'evidence_class': 'synthetic',
             'instance': {'@odata.type': '#microsoft.graph.deviceManagementConfigurationChoiceSettingInstance', 'settingDefinitionId': LOCATION,
                          'choiceSettingValue': {'value': LOCATION + '_2', 'children': []}}}],
         'fact_provenance': {'categories': {'community_advice': {'availability': 'absent'}, 'company_annotation': {'availability': 'absent'},
                                            'ai_interpretation': {'availability': 'not_implemented'}}}}


class InspectorAndDictionaryTests(unittest.TestCase):
    def test_inspector_shows_exact_identity_settings_and_targeting(self):
        from intune_iac.workbench_screens import inspector_lines
        lines = inspector_lines(INSPECT, 120)
        joined = '\n'.join(lines)
        self.assertEqual(lines[0], 'POLICY  Windows Privacy Pilot')
        self.assertIn('Identity  ' + POLICY_ID, joined)
        self.assertIn('scope tags "0"', joined)
        self.assertIn('Description  "Synthetic reference; not production advice."', joined)
        self.assertIn('  1 setting', joined)
        self.assertIn('= "' + LOCATION + '_2"', joined)
        self.assertIn('  3 targets', joined)
        self.assertIn('Unresolved group identity', joined)
        self.assertIn('include  Unresolved group identity 44444444-4444-4444-8444-444444444444', joined)
        self.assertIn('filter include 77777777-7777-4777-8777-777777777777', joined)
        self.assertIn('exclude  Unresolved group identity 66666666-6666-4666-8666-666666666666', joined)
        for line in lines:
            self.assertLessEqual(cell_width(line), 120, line)

    def test_inspector_handles_missing_body_and_hostile_names(self):
        from intune_iac.workbench_screens import inspector_lines
        lines = inspector_lines({'object_id': POLICY_ID, 'name': 'bad\x1b]0;title\x07name', 'freshness': 'stale'}, 80)
        joined = '\n'.join(lines)
        self.assertNotIn('\x1b', joined); self.assertNotIn('\x07', joined)
        self.assertIn('Settings are not in this result.', joined)

    def test_dictionary_keeps_vendor_mapping_and_use_apart(self):
        from intune_iac.workbench_screens import dictionary_lines
        lines = dictionary_lines({'entries': [ENTRY], 'query': ''}, 120)
        joined = '\n'.join(lines)
        self.assertEqual(lines[0], '[SETTING DICTIONARY]')
        self.assertIn('Let Windows apps access location', joined)
        self.assertIn('CSP values   0 User in control | 1 Force allow | 2 Force deny', joined)
        self.assertIn('Graph value to CSP value translation NOT verified', joined)
        self.assertIn('"' + LOCATION + '_2"', joined)
        self.assertIn('In use       Windows Privacy Pilot (' + POLICY_ID + ')', joined)
        self.assertIn('AI interpretation not implemented', joined)
        self.assertIn('Microsoft Learn', joined)

    def test_dictionary_source_times_are_readable(self):
        import copy
        from intune_iac.workbench_screens import dictionary_lines
        entry = copy.deepcopy(ENTRY)
        entry['vendor_documentation'][0]['documentation'] = {'publisher': 'Microsoft Learn', 'url': 'https://example.invalid/doc',
            'published_update_at': '2026-09-23T17:34:00Z', 'retrieved_at': '2026-10-07T03:21:49.096637+00:00'}
        joined = ' '.join(' '.join(dictionary_lines({'entries': [entry], 'query': ''}, 120)).split())
        self.assertIn('updated 2026-09-23 17:34:00 UTC', joined)
        self.assertIn('retrieved 2026-10-07 03:21:49 UTC', joined)

    def test_empty_dictionary_says_so(self):
        from intune_iac.workbench_screens import dictionary_lines
        self.assertIn('No dictionary entries for this query.', dictionary_lines({'entries': [], 'query': 'none'}, 80))


RELATIONSHIPS = {'object_id': POLICY_ID, 'name': 'Windows Privacy Pilot', 'coverage': 'complete', 'observed_at': '2026-10-14T12:34:41Z',
    'relationships': [
        {'relation': 'assignment', 'target_id': '44444444-4444-4444-8444-444444444444', 'assertion_class': 'observed',
         'details': {'type': 'groupAssignmentTarget', 'group_id': '44444444-4444-4444-8444-444444444444', 'filter_type': 'include', 'filter_id': '77777777-7777-4777-8777-777777777777'}},
        {'relation': 'exclusion', 'target_id': '66666666-6666-4666-8666-666666666666', 'assertion_class': 'observed', 'details': {}},
        {'relation': 'filter', 'target_id': '77777777-7777-4777-8777-777777777777', 'assertion_class': 'observed', 'details': {}},
        {'relation': 'scope_tag', 'target_id': '0', 'assertion_class': 'observed', 'details': {}},
        {'relation': 'setting', 'target_id': LOCATION, 'assertion_class': 'observed', 'details': {}},
        {'relation': 'generated_from', 'target_id': '/work/generated/' + POLICY_ID, 'assertion_class': 'historical_local_adoption', 'details': {}}],
    'ownership_evidence': {'reason': 'ownership_index_missing', 'declared_scope_complete': False, 'fresh': False},
    'ownership': 'unknown',
    'selected_repository': {'artifact_id': 'f' * 64, 'evidence_class': 'local_literal_repository_read',
                            'scope': {'repository': '/work/repository', 'stack': 'orgs/reference/dev', 'component': 'intune-reference'}}}


class TreeAndSpineTests(unittest.TestCase):
    """Box-drawing rules draw connected trees and a stage spine; ASCII output is unchanged."""
    def test_relationships_hang_from_connected_tree_lines(self):
        from intune_iac.workbench_screens import relationship_lines
        lines = relationship_lines(RELATIONSHIPS, 140, rules='unicode')
        self.assertIn('  ├── assignment   Unresolved group identity 44444444-4444-4444-8444-444444444444  filter include 77777777-7777-4777-8777-777777777777', lines)
        self.assertTrue(any(line.startswith('  └── ') for line in lines))
        self.assertEqual(relationship_lines(RELATIONSHIPS, 140), relationship_lines(RELATIONSHIPS, 140, rules='ascii'))

    def test_delivery_stages_hang_from_one_spine(self):
        from intune_iac.workbench_screens import delivery_lines
        lines = delivery_lines(delivery_value(), 140, rules='unicode')
        stage_lines = [line for line in lines if '] ' in line and line[:1] in '┌├└']
        self.assertEqual(len(stage_lines), 8)
        self.assertTrue(stage_lines[0].startswith('┌─[x] 1 Proposal'))
        self.assertTrue(stage_lines[-1].startswith('└─['))
        ascii_lines = delivery_lines(delivery_value(), 140)
        self.assertIn('  [x] 1 Proposal', '\n'.join(ascii_lines))
        for line in lines:
            self.assertLessEqual(cell_width(line), 140, line)

    def test_one_observation_is_counted_in_the_singular(self):
        from intune_iac.workbench_screens import history_lines
        lines = history_lines({'object_id': POLICY_ID, 'name': 'P', 'pagination': {'total_observations': 1, 'offset': 0},
                               'history': []}, 100)
        self.assertIn('1 observation | this page 0 from offset 0', lines)

    def test_a_long_address_keeps_its_label_and_column(self):
        from intune_iac.workbench_screens import repository_entry_lines
        value = {'repository': '/work/repository', 'revision': 'c' * 40, 'tenant_id': POLICY_ID, 'status': 'discovered',
                 'components': [], 'next_action': 'One policy.', 'candidates': [{
                     'number': 1, 'stack': 's', 'component': 'c', 'policy_key': 'p_' + 'a' * 32 + '_' + 'b' * 32,
                     'object_id': POLICY_ID, 'observed': {'present': False}, 'state': 'ready', 'backend': 'local',
                     'backend_source': 'none_declared', 'resource_address': 'resource.policy["' + 'k' * 90 + '"]',
                     'explanation': 'Ready to record.'}]}
        lines = repository_entry_lines(value, 80)
        address = [index for index, line in enumerate(lines) if line.startswith('     Address   resource.policy')]
        self.assertEqual(len(address), 1)
        self.assertTrue(lines[address[0] + 1].startswith(' ' * 15 + 'k'))
        self.assertIn('     State     ready to record', lines)
        for line in lines:
            self.assertLessEqual(cell_width(line), 80, line)


class RelationshipLinesTests(unittest.TestCase):
    def test_edges_are_grouped_typed_and_keep_their_evidence_class(self):
        from intune_iac.workbench_screens import relationship_lines
        lines = relationship_lines(RELATIONSHIPS, 140)
        joined = '\n'.join(lines)
        self.assertEqual(lines[0], '[TYPED RELATIONSHIPS]')
        for heading in ('TARGETING', 'CONFIGURATION', 'SOURCE AND LINEAGE', 'OWNERSHIP'):
            self.assertIn(heading, joined)
        self.assertIn('TARGETING  [observed]', joined); self.assertIn('CONFIGURATION  [observed]', joined)
        self.assertIn('  |-- assignment   Unresolved group identity 44444444-4444-4444-8444-444444444444  filter include 77777777-7777-4777-8777-777777777777', lines)
        self.assertIn('  |-- exclusion    66666666-6666-4666-8666-666666666666', lines)
        self.assertIn('  |-- scope tag    "0"', lines)
        self.assertIn('generated    /work/generated/' + POLICY_ID + '  [historical_local_adoption]', joined)
        self.assertIn('repository   /work/repository  orgs/reference/dev / intune-reference  [local_literal_repository_read]', joined)
        self.assertIn('writer       unknown (ownership index missing)', joined)
        for line in lines:
            self.assertLessEqual(cell_width(line), 140, line)

    def test_no_relationships_is_said_plainly(self):
        from intune_iac.workbench_screens import relationship_lines
        lines = relationship_lines({'object_id': POLICY_ID, 'relationships': []}, 80)
        self.assertIn('No typed relationships in this result.', lines)


def stage(targeted=None, reporting=None, successful=None, unknown=None):
    return {'targeted': targeted, 'reporting': reporting, 'successful': successful, 'unknown': unknown}


EMPTY_STAGES = {name: stage() for name in ('object', 'assignment', 'cohort', 'execution', 'effective_state', 'outcome')}


class EstateScreensTests(unittest.TestCase):
    def test_history_names_what_changed_between_observations(self):
        from intune_iac.workbench_screens import history_lines
        newer = body(description=EDITED)
        value = {'object_id': POLICY_ID, 'order': 'observed_at_desc_observation_id_desc',
                 'pagination': {'total_observations': 2, 'returned_observations': 2},
                 'history': [{'observed_at': '2026-10-14T13:00:00Z', 'snapshot_id': 'b' * 64, 'coverage': 'complete', 'run_id': 2, 'body': newer},
                             {'observed_at': '2026-10-14T12:00:00Z', 'snapshot_id': 'a' * 64, 'coverage': 'complete', 'run_id': 1, 'body': body()}]}
        joined = '\n'.join(history_lines(value, 120))
        self.assertIn('[OBSERVATION HISTORY]', joined); self.assertIn('Newest first', joined)
        self.assertIn('2026-10-14 13:00:00 UTC', joined); self.assertIn('2026-10-14 12:00:00 UTC', joined)
        self.assertIn('Changed since the previous observation', joined)
        self.assertIn('"' + EDITED + '"', joined)
        self.assertIn('Earliest observation on this page', joined)

    def test_health_keeps_reporting_coverage_and_endpoint_evidence_apart(self):
        from intune_iac.workbench_screens import health_lines
        reported = dict(EMPTY_STAGES, execution=stage(100, 8, 8, 92))
        value = {'freshness': 'fresh', 'coverage': 'complete', 'age_seconds': 472.8, 'limitations': ['Synthetic capture.'],
                 'objects': [{'object_id': POLICY_ID, 'name': 'Windows Privacy Pilot', 'health': {
                     'stages': reported, 'endpoint_health': 'unknown', 'endpoint_outcome': 'unknown', 'rollout_ready': False}},
                     {'object_id': '33333333-3333-4333-8333-333333333333', 'name': 'Other', 'health': {
                     'stages': EMPTY_STAGES, 'reason': 'No policy-bound device evidence was imported.', 'endpoint_health': 'unknown'}}]}
        lines = health_lines(value, 100)
        joined = '\n'.join(lines)
        self.assertEqual(lines[0], '[HEALTH AND REPORTING]')
        self.assertIn('8 of 100 targeted devices reported success at execution; 92 without a fresh report', joined)
        # Wrapped rows lead with the devices they hold ("devices 51-100 [...]"); the cells sit between the brackets.
        matrix = [match.group(1) for match in (MATRIX_ROW.match(line) for line in lines) if match]
        self.assertEqual(sum(line.count('#') for line in matrix), 8)
        self.assertEqual(sum(line.count('.') for line in matrix), 92)
        self.assertIn('each cell is 1 device', joined)
        self.assertIn('Endpoint health unknown', joined)
        self.assertIn('No policy-bound device evidence was imported.', joined)
        self.assertIn('No device evidence for any stage.', joined)
        header = next(line for line in lines if line.startswith('  STAGE'))
        self.assertTrue(header.endswith(' UNKNOWN NO REPORT'), header)
        self.assertLessEqual(cell_width(header), 80)
        for line in lines:
            self.assertLessEqual(cell_width(line), 100, line)

    def test_queue_lists_findings_with_their_reason_and_state(self):
        from intune_iac.workbench_screens import queue_lines
        value = {'findings': [{'object_id': POLICY_ID, 'finding': 'reporting_incomplete', 'priority': 'review', 'freshness': 'fresh',
                               'priority_rationale': 'Missing or stale reporting cannot establish rollout readiness or endpoint success.',
                               'action_state': 'review_required', 'owner_assertion': 'unknown', 'automatic_remediation': False,
                               'review_due': None, 'exception_expiry': None, 'related_proposals': []}],
                 'pagination': {'total_objects': 1}}
        joined = '\n'.join(queue_lines(value, 120))
        self.assertIn('[MAINTENANCE QUEUE]', joined)
        self.assertIn('review  reporting incomplete (reporting_incomplete)  ' + POLICY_ID, joined)
        self.assertIn('Why: Missing or stale reporting', joined)
        self.assertIn('State review required (review_required) | owner unknown | freshness fresh | automatic remediation no', joined)

    def test_each_finding_names_how_to_review_it(self):
        from intune_iac.workbench_screens import queue_lines
        value = {'findings': [{'object_id': POLICY_ID, 'finding': 'ownership_unknown', 'priority': 'review',
                               'review_record': {'status': 'recorded', 'artifact_id': 'c' * 64}}],
                 'pagination': {'total_objects': 1}}
        text = ' '.join(' '.join(queue_lines(value, 120, selected=POLICY_ID)).split())
        # Run 9 (frame 47): each command stands on its own row, so the rows say the sentence and then the commands.
        self.assertIn("This finding's review: write the form with the first command, then record it with the second "
                      '(an annotation, never approval). The last word of the second command is the earlier review it '
                      'replaces. The :queue-review-template command using ownership_unknown, naming a new JSON file for the review '
                      'form The :queue-amend command using ' + 'c' * 64 + ', naming the file you name', text)

    def test_review_results_read_as_words(self):
        from intune_iac.workbench_screens import review_lines
        form = {'status': 'review_form_written', 'path': '/w/form.json', 'object_id': POLICY_ID,
                'finding': 'ownership_unknown', 'expected_prior': None}
        text = ' '.join(' '.join(review_lines(form, 120)).split())
        self.assertIn('[REVIEW FORM WRITTEN] /w/form.json', text)
        self.assertIn("queue-amend '/w/form.json' none", text)
        self.assertIn('never approval', text)
        recorded = {'schema_version': 'workbench-queue-review/1', 'status': 'recorded', 'finding': 'ownership_unknown',
                    'object_id': POLICY_ID, 'version': 2, 'recorded_at': '2026-10-14T22:40:00Z', 'owner': 'Platform team',
                    'owner_assertion': 'organization_annotation_unverified', 'rationale': 'Confirm stack ownership.',
                    'review_due': '2026-11-01T12:00:00Z', 'exception_expiry': None, 'review_overdue': False,
                    'exception_expired': None, 'linked_proposals': [], 'limitations': ['Annotation only.']}
        text = ' '.join(' '.join(review_lines(recorded, 120)).split())
        self.assertIn('[REVIEW] ownership unknown, version 2, recorded 2026-10-14 22:40:00 UTC', text)
        self.assertIn('Owner: Platform team (an unverified annotation)', text)
        self.assertIn('Review due: 2026-11-01 12:00:00 UTC (not overdue)', text)
        self.assertIn('Exception expiry: none', text)
        self.assertNotIn('null', text)
        missing = {'status': 'unknown', 'reason': 'review_not_recorded', 'finding': 'ownership_unknown', 'object_id': POLICY_ID}
        self.assertIn('No review recorded for ownership unknown',
                      ' '.join(' '.join(review_lines(missing, 120)).split()))
        history = {'schema_version': 'workbench-queue-history/1', 'finding': 'ownership_unknown', 'object_id': POLICY_ID,
                   'amendments': [{'artifact_id': 'a' * 64, 'recorded_at': '2026-10-14T22:40:00Z',
                                   'data': {'version': 1, 'owner': 'Endpoint operations', 'rationale': 'First.'}}]}
        text = ' '.join(' '.join(review_lines(history, 120)).split())
        self.assertIn('[REVIEW HISTORY] ownership unknown: 1 version', text)
        self.assertIn('version 1 recorded 2026-10-14 22:40:00 UTC | owner Endpoint operations | First.', text)

    def test_an_absent_source_owner_claim_reads_as_words(self):
        from intune_iac.workbench_screens import queue_lines
        value = {'findings': [{'object_id': POLICY_ID, 'finding': 'ownership_unknown', 'priority': 'review',
                               'owner_role': 'human_review_assignee', 'writer_ownership': {'status': 'unknown'},
                               'source_owner_claim': {'value': None}}], 'pagination': {'total_objects': 1}}
        joined = '\n'.join(queue_lines(value, 120))
        self.assertIn('source owner claim none recorded', joined)
        self.assertNotIn('null', joined)


INTENT = 'bcffdf6f' + '0' * 56
DIGEST = 'd1072f31' + '0' * 56


def delivery_value(**stages):
    value = {'schema_version': 'workbench-delivery/1', 'operation_id': 'b6b3679d5d95457ea8645919a1059863', 'object_id': POLICY_ID,
             'journal_status': 'succeeded_verified', 'evidence_class': 'synthetic_local_process_and_modeled_service_only',
             'next_action': 'Nothing pending: the change is recorded and observed as desired.', 'stages': [
        {'stage': 'proposal', 'status': 'done', 'recorded_at': '2026-10-14T12:24:54Z', 'repository_intent_id': INTENT, 'intent_freshness': 'current'},
        {'stage': 'review', 'status': 'done', 'changes': [POLICY_ID + ':description_changed'], 'no_configuration_change': False,
         'field_changes': {'status': 'changed', 'changes': [{'field': 'description', 'kind': 'changed', 'before': OBSERVED, 'after': EDITED}]},
         'approval_digest': DIGEST, 'saved_plan_sha256': 'ab' * 32},
        {'stage': 'approval', 'status': 'done', 'approval_digest': DIGEST, 'opens_at': 1791980697, 'closes_at': 1791980997},
        {'stage': 'execution', 'status': 'done', 'engine_status': 'succeeded_verified', 'service_status': 200, 'mutation_dispatched': True,
         'error_code': None, 'recorded_at': '2026-10-14T12:24:58Z'},
        {'stage': 'readback', 'status': 'done', 'classification': 'desired_state_observed', 'visibility_pending': False,
         'second_plan': 'no_change', 'mismatch_count': 0, 'committed_revision': 2},
        {'stage': 'reconciliation', 'status': 'not_needed'},
        {'stage': 'deployment_record', 'status': 'done', 'intent_id': INTENT, 'recorded_at': '2026-10-14T12:25:00Z',
         'evidence_class': 'verified_local_modeled_deployment', 'baseline_admissible': True},
        {'stage': 'observed_after', 'status': 'matches_desired', 'service_revision': 2, 'before_revision': 1,
         'observed_at': '2026-10-14T12:25:00.854978Z'}]}
    value['stages'] = [dict(stage, **stages.get(stage['stage'], {})) for stage in value['stages']]
    return value


class DeliveryLinesTests(unittest.TestCase):
    def test_every_stage_is_shown_in_order_with_its_evidence(self):
        from intune_iac.workbench_screens import delivery_lines
        # 140 columns: every stage fits on one line, so the rows can be compared exactly.
        lines = delivery_lines(delivery_value(), 140)
        joined = '\n'.join(lines)
        self.assertEqual(lines[0], '[DELIVERY]')
        self.assertIn('Operation b6b3679d5d95457ea8645919a1059863 | policy ' + POLICY_ID + ' | journal succeeded verified', joined)
        expected = ['  [x] 1 Proposal        recorded 2026-10-14 12:24:54 UTC | repository intent bcffdf6f (current)',
                    '  [x] 2 Review          1 field change: description | plan sha256 abababababab',
                    '  [x] 3 Approval        exact review digest d1072f310000 supplied at dispatch | window 2026-10-14 12:24:57 UTC to 2026-10-14 12:29:57 UTC',
                    '  [x] 4 Execution       engine succeeded verified | service 200 | recorded 2026-10-14 12:24:58 UTC',
                    '  [x] 5 Readback        desired state observed | second plan no change | visibility settled | 0 mismatches',
                    '  [-] 6 Reconciliation  not needed',
                    '  [x] 7 Deployment      recorded 2026-10-14 12:25:00 UTC | intent bcffdf6f | verified local modeled deployment | baseline admissible',
                    '  [x] 8 Observed after  matches desired at service revision 2 (1 before the change) | observed 2026-10-14 12:25:00 UTC']
        rows = [line for line in lines if line.startswith('  [')]
        self.assertEqual(rows, expected)
        self.assertIn('Next: Nothing pending: the change is recorded and observed as desired.', joined)
        self.assertIn('[x] done  [ ] waiting or not yet  [-] not needed  [?] unknown or required  [~] not available yet  [!] stopped: failure, expiry or refusal', joined)

    def test_waiting_required_and_refused_stages_are_marked_in_words(self):
        from intune_iac.workbench_screens import delivery_lines
        value = delivery_value(approval={'status': 'waiting'}, execution={'status': 'not_started'}, readback={'status': 'not_started'},
                               deployment_record={'status': 'not_yet'}, observed_after={'status': 'not_yet'})
        joined = '\n'.join(delivery_lines(value, 120))
        self.assertIn('  [ ] 3 Approval        waiting for the exact review digest until 2026-10-14 12:29:57 UTC', joined)
        self.assertIn('  [ ] 4 Execution       not started', joined)
        value = delivery_value(approval={'status': 'expired'})
        self.assertIn('  [!] 3 Approval        expired: the approval window closed at 2026-10-14 12:29:57 UTC', '\n'.join(delivery_lines(value, 120)))
        value = delivery_value(execution={'status': 'unknown', 'error_code': 'model_response_lost', 'service_status': None},
                               reconciliation={'status': 'required'},
                               deployment_record={'status': 'not_available', 'reason': 'no_verified_readback'})
        joined = '\n'.join(delivery_lines(value, 120))
        self.assertIn("  [?] 4 Execution       outcome unknown: the modeled service's response was lost (model_response_lost)", joined)
        self.assertIn('  [?] 6 Reconciliation  required: the outcome is unknown', joined)
        self.assertIn('  [~] 7 Deployment      not available: no verified readback', joined)

    def test_an_observation_that_differs_shows_the_exact_difference(self):
        from intune_iac.workbench_screens import delivery_lines
        value = delivery_value(observed_after={'status': 'differs', 'field_changes': field_changes(body(description=EDITED), body(description=OBSERVED))})
        joined = '\n'.join(delivery_lines(value, 120))
        self.assertIn('[!] 8 Observed after  differs from the desired configuration at service revision 2', joined)
        self.assertIn('BEFORE (desired)', joined); self.assertIn('AFTER (observed)', joined)

    def test_imported_workflow_runs_are_shown_as_claims(self):
        from intune_iac.workbench_screens import delivery_lines
        value = delivery_value()
        self.assertIn('CI workflow runs: none imported for this operation or its cited revision',
                      '\n'.join(delivery_lines(value, 140)))
        value['workflow_runs'] = [{'relation': 'related_operation', 'workflow': 'plan', 'run_id': '42', 'status': 'success',
                                   'repository_revision': 'b' * 40, 'observed_at': '2026-10-14T12:00:00Z',
                                   'run_url': 'https://ci.example.invalid/runs/42'}]
        joined = '\n'.join(delivery_lines(value, 140))
        self.assertIn('CI WORKFLOW RUNS  (imported claims; not verified)', joined)
        self.assertIn('  plan 42  claims success | revision bbbbbbbbbbbb | observed 2026-10-14 12:00:00 UTC | tied to this operation', joined)

    def test_narrow_terminals_stack_the_stage_text(self):
        from intune_iac.workbench_screens import delivery_lines
        lines = delivery_lines(delivery_value(), 50)
        for line in lines:
            self.assertLessEqual(cell_width(line), 50, line)
        self.assertIn('  [-] 6 Reconciliation', lines)
        self.assertIn('      not needed', lines)


KEY = 'p_11111111111141118111111111111111_22222222222242228222222222222222'
STACK_FILE = 'stacks/orgs/reference/dev.yaml'


def origin(path, line, column, pointer):
    return {'path': path, 'line': line, 'column': column, 'pointer': pointer, 'sha256': 'a' * 64, 'source_kind': 'captured_repository_file'}


LINEAGE = {'object_id': POLICY_ID, 'status': 'available', 'freshness': 'recorded_intent_not_revalidated',
           'provenance_origin': {'kind': 'repository_intent', 'artifact_id': 'f' * 64, 'recorded_at': '2026-10-14T12:25:00Z',
                                 'source_revision': 'b' * 40, 'revision_content_verified': True},
           'repository': {'path': '/work/repository', 'stack': 'orgs/reference/dev', 'component': 'intune-reference'},
           'sources': [{'path': 'atmos.yaml', 'sha256': 'a' * 64}, {'path': STACK_FILE, 'sha256': 'b' * 64}],
           'fields': [{'effective_pointer': '/command', 'winner': origin(STACK_FILE, 7, 16, '/components/terraform/intune-reference/command'),
                       'history': [origin('atmos.yaml', 5, 14, '/components/terraform/command'), origin(STACK_FILE, 7, 16, '/components/terraform/intune-reference/command')],
                       'earlier_origins': [origin('atmos.yaml', 5, 14, '/components/terraform/command')]},
                      {'effective_pointer': '/vars/policies/' + KEY + '/description',
                       'winner': origin(STACK_FILE, 33, 30, '/components/terraform/intune-reference/vars/policies/' + KEY + '/description'),
                       'history': [origin(STACK_FILE, 33, 30, '/components/terraform/intune-reference/vars/policies/' + KEY + '/description')],
                       'earlier_origins': []}],
           'edges': [], 'blockers': []}


class LineageAndNavigationTests(unittest.TestCase):
    def test_lineage_names_where_each_value_is_defined_and_what_it_overrides(self):
        from intune_iac.workbench_screens import lineage_lines
        lines = lineage_lines(LINEAGE, 120)
        joined = '\n'.join(lines)
        self.assertEqual(lines[0], '[REPOSITORY LINEAGE]')
        self.assertIn('repository intent ffffffffffff', joined)
        self.assertIn('revision bbbbbbbbbbbb (content verified)', joined)
        self.assertIn('/work/repository | orgs/reference/dev / intune-reference', joined)
        self.assertIn('<key> = ' + KEY, joined)
        self.assertIn('  /vars/policies/<key>/description', lines)
        self.assertIn('      defined in  ' + STACK_FILE + ':33:30', lines)
        self.assertIn('  /command', lines)
        self.assertIn('      defined in  ' + STACK_FILE + ':7:16', lines)
        self.assertIn('      overrides   atmos.yaml:5:14  /components/terraform/command', lines)
        for line in lines:
            self.assertLessEqual(cell_width(line), 120, line)

    def test_lineage_without_a_source_says_how_to_get_one(self):
        from intune_iac.workbench_screens import lineage_lines
        joined = '\n'.join(lineage_lines({'status': 'unknown', 'reason': 'repository_resolution_not_collected', 'fields': []}, 80))
        self.assertIn('No repository resolution was captured or recorded for this policy', joined)
        self.assertIn('repository-import', joined)

    def test_the_tab_line_keeps_the_active_surface_whole_at_60_columns(self):
        from intune_iac.workbench_screens import tab_line
        tabs = ('Estate', 'Inspector', 'Relationships', 'History', 'Plan', 'Execution', 'Coverage', 'Help', 'Repository')
        line = tab_line(tabs, 8, 58)
        self.assertLessEqual(cell_width(line), 58)
        self.assertTrue(line.startswith('[9 Repository]'), line)
        self.assertIn('1-9', line)  # never a row of bare digits
        self.assertLessEqual(cell_width(tab_line(tabs, 0, 20)), 20)


DIAGNOSTICS = {'schema_version': 'workbench-diagnostics/1', 'object_id': POLICY_ID, 'name': 'Windows Privacy Pilot',
               'signals': [{'area': 'operations', 'code': 'operation_outcome_unknown',
                            'observed': 'Operation b6b3679d was dispatched and its outcome is unknown: model_response_lost.',
                            'evidence': {'operation_id': 'b6b3679d', 'operation_root': '/work/op', 'error_code': 'model_response_lost', 'scope': {'x': 1}},
                            'next_step': 'reconcile /work/op reads the service independently; execution is never replayed.'}],
               'checked': {'collection': 'clear', 'freshness': 'clear', 'operations': 'attention', 'repository': 'not_recorded',
                           'device_evidence': 'not_imported'},
               'limitations': ['Read from local records only.']}


class DiagnosticsLinesTests(unittest.TestCase):
    def test_signals_show_the_fact_its_evidence_and_the_next_step_then_what_is_clear(self):
        from intune_iac.workbench_screens import diagnostics_lines
        lines = diagnostics_lines(DIAGNOSTICS, 100)
        joined = '\n'.join(lines)
        self.assertEqual(lines[0], '[DIAGNOSTICS]')
        self.assertIn('Windows Privacy Pilot (' + POLICY_ID + ') | 1 signal needs attention', joined)
        self.assertIn('[!] operations  operation_outcome_unknown', joined)
        self.assertIn('  Observed  Operation b6b3679d was dispatched', joined)
        self.assertIn('  Evidence  operation id b6b3679d; operation root /work/op; error code model_response_lost', joined)
        self.assertNotIn("{'x': 1}", joined)
        self.assertIn('  Next      reconcile /work/op', joined)
        self.assertIn('  repository       no repository intent recorded', joined)
        self.assertIn('  device evidence  no device evidence imported', joined)
        for line in lines:
            self.assertLessEqual(cell_width(line), 100, line)

    def test_nothing_to_report_is_said_plainly(self):
        from intune_iac.workbench_screens import diagnostics_lines
        value = dict(DIAGNOSTICS, signals=[], checked={'collection': 'clear', 'device_evidence': 'clear'})
        text = ' '.join(' '.join(diagnostics_lines(value, 120)).split())
        # Scoped to what diagnostics reads: reporting completeness and ownership are queue findings (journey 26).
        self.assertIn('no signal in the areas checked below', text)
        self.assertIn('the maintenance queue (m opens it)', text)
        self.assertNotIn('nothing needs attention', text)
        self.assertIn('device evidence capture complete and cohort consistent; whether devices reported is not judged here (h shows the counts)', text)

    def test_partly_checked_and_unreadable_areas_are_not_shown_as_clear(self):
        from intune_iac.workbench_screens import diagnostics_lines
        value = dict(DIAGNOSTICS, signals=[], checked={'operations': 'partly_checked', 'device_evidence': 'unavailable'})
        joined = '\n'.join(diagnostics_lines(value, 120))
        self.assertIn('partly checked: the read bound was reached', joined)
        self.assertIn('could not be read', joined)
        self.assertNotIn('nothing needs attention', joined)


class EvidenceReadStatusTests(unittest.TestCase):
    def test_unreadable_ci_runs_are_said_to_be_unreadable_not_absent(self):
        from intune_iac.workbench_screens import delivery_lines
        value = dict(delivery_value(), workflow_runs=[], workflow_runs_read={'status': 'unavailable', 'error_code': 'workbench_query_limit'})
        joined = '\n'.join(delivery_lines(value, 140))
        self.assertIn('CI workflow runs could not be read (workbench_query_limit); the stages above are unaffected.', joined)
        self.assertNotIn('none imported', joined)

    def test_a_partial_read_of_ci_runs_says_so(self):
        from intune_iac.workbench_screens import delivery_lines
        run = {'relation': 'related_operation', 'workflow': 'plan', 'run_id': '42', 'status': 'success',
               'repository_revision': 'b' * 40, 'observed_at': '2026-10-14T12:00:00Z', 'run_url': 'https://ci.example.invalid/runs/42'}
        value = dict(delivery_value(), workflow_runs=[run], workflow_runs_read={'status': 'partial', 'records_read': 2000})
        self.assertIn('only the first 2000 imported runs for this policy were read',
                      '\n'.join(delivery_lines(value, 140)))

    def test_a_malformed_family_table_is_explained(self):
        from intune_iac.workbench_screens import families_lines
        lines = families_lines({'available': False, 'reason': 'family_coverage_malformed', 'detail': 'missing columns: live',
                                'families': []}, 100)
        self.assertIn('could not be read: missing columns: live', '\n'.join(lines))

    def test_the_estate_caption_fits_a_narrow_terminal(self):
        from intune_iac.workbench_tui import Workspace
        workspace = Workspace.__new__(Workspace)
        workspace.__dict__.update(tab=0, value={'objects': [{'object_id': POLICY_ID}]}, highlight=0, selected=None,
                                  rows=[{'object_id': POLICY_ID, 'name': 'Windows Privacy Pilot'}], _detail_cache=None)
        for line in workspace._data_lines(58):
            self.assertLessEqual(cell_width(line), 58, line)


class RecordedLinesTests(unittest.TestCase):
    RUN = {'artifact_id': 'a' * 64, 'kind': 'workflow_run', 'recorded_at': '2026-10-14T14:31:06Z', 'created': True,
           'data': {'workflow': 'apply', 'run_id': '1002', 'status': 'success', 'repository_revision': 'b' * 40,
                    'observed_at': '2026-10-14T14:21:05Z',
                    'relationships': [{'relation': 'related_operation', 'target_id': 'c' * 32}]}}

    def test_an_imported_ci_run_reads_as_a_claim_with_its_links(self):
        from intune_iac.workbench_screens import recorded_lines
        lines = recorded_lines(self.RUN, 120)
        self.assertEqual(lines[0], '[RECORDED] CI workflow run aaaaaaaaaaaa | new record | 2026-10-14 14:31:06 UTC')
        self.assertEqual(lines[1], 'apply 1002: success | revision bbbbbbbbbbbb | observed 2026-10-14 14:21:05 UTC | '
                                   'linked to operation cccccccccccc')
        self.assertIn('never marks a stage done', ' '.join(lines[2:]))
        self.assertIn(':workflows lists every imported run', ' '.join(lines[2:]))

    def test_a_repeated_record_says_nothing_changed(self):
        from intune_iac.workbench_screens import recorded_lines
        value = dict(self.RUN, created=False, kind='device_evidence', data={})
        self.assertEqual(recorded_lines(value, 120),
                         ['[RECORDED] device evidence aaaaaaaaaaaa | already recorded; nothing changed | 2026-10-14 14:31:06 UTC'])


class HistoryLinesTests(unittest.TestCase):
    HISTORY = {'events': [
        {'sequence': 0, 'kind': 'prepared', 'fields': {'approval_digest': 'a' * 64},
         'store_status': 'prepared', 'store_recorded_at': '2026-10-14T16:35:31Z'},
        {'sequence': 1, 'kind': 'dispatch_started', 'fields': {'approval_digest': 'a' * 64},
         'store_status': None, 'store_recorded_at': None},
        {'sequence': 2, 'kind': 'engine_result', 'fields': {'result': {'status': 'succeeded_verified', 'assurance': 'synthetic_local_process_only'}},
         'store_status': None, 'store_recorded_at': None},
        {'sequence': 3, 'kind': 'uncertain', 'fields': {'error_code': 'model_response_lost'},
         'store_status': 'outcome_unknown', 'store_recorded_at': '2026-10-14T16:35:32Z'}],
        'chain': 'verified when the operation was loaded', 'registrations': 2, 'paired': 2}

    def test_each_event_in_order_with_a_time_only_where_the_store_registered_it(self):
        from intune_iac.workbench_screens import history_event_lines
        lines = history_event_lines(self.HISTORY, 120)
        joined = '\n'.join(lines)
        self.assertTrue(lines[0].startswith('HISTORY  journal events in order (chain verified)'))
        self.assertIn('0   prepared          2026-10-14 16:35:31 UTC  approval will need digest aaaaaaaaaaaa', joined)
        self.assertIn('approved with digest aaaaaaaaaaaa', joined)
        self.assertIn('1   dispatch started  time not recorded', joined)
        self.assertIn('engine reported succeeded verified (synthetic local process only)', joined)
        self.assertIn("3   outcome unknown   2026-10-14 16:35:32 UTC  the modeled service's response was lost (model_response_lost)", joined)
        self.assertNotIn('could not be paired', joined)
        for width in (120, 60):
            for line in history_event_lines(self.HISTORY, width):
                self.assertLessEqual(cell_width(line), width, line)

    def test_a_store_time_is_shown_to_the_second_and_the_columns_stay_aligned(self):
        from intune_iac.workbench_screens import history_event_lines
        history = copy.deepcopy(self.HISTORY)
        history['events'][0]['store_recorded_at'] = '2026-10-14T17:14:37.396288Z'
        lines = history_event_lines(history, 120)
        self.assertIn('0   prepared          2026-10-14 17:14:37 UTC  approval will need digest', lines[1])
        self.assertEqual(lines[1].index('approval will'), lines[2].index('approved with'))

    def test_unpaired_registrations_are_disclosed_and_no_history_draws_nothing(self):
        from intune_iac.workbench_screens import history_event_lines
        lines = history_event_lines(dict(self.HISTORY, registrations=3), 120)
        self.assertIn('  1 store registration could not be paired with an event; r shows it.', lines)
        self.assertEqual(history_event_lines({}, 120), [])


class RefusalLinesTests(unittest.TestCase):
    def test_a_known_refusal_explains_itself_and_names_the_next_step(self):
        from intune_iac.workbench_screens import refusal_lines
        value = {'status': 'error', 'error': {'code': 'workbench_repository_intent_missing',
                                              'message': 'Import the repository for this object before using its intent.'}}
        lines = refusal_lines(value, 100)
        joined = '\n'.join(lines)
        self.assertEqual(lines[0], '[REFUSED] No repository intent is recorded for this policy (workbench_repository_intent_missing)')
        # The cause is said once in words; the engine's plain message is one key away (e).
        self.assertNotIn('Import the repository for this object before using its intent.', joined)
        self.assertIn('Cause: No repository intent was recorded for this policy', joined)
        self.assertIn("The engine's own message is in the typed details (e).", joined)
        self.assertIn('repository-import', joined)
        for line in lines:
            self.assertLessEqual(cell_width(line), 100, line)

    def test_every_explained_refusal_is_raised_by_the_engine(self):
        from intune_iac.workbench_screens import REFUSALS
        root = Path(__file__).resolve().parents[1] / 'intune_iac'
        text = '\n'.join(path.read_text(encoding='utf-8') for path in sorted(root.glob('*.py')) if path.name != 'workbench_screens.py')
        for code in REFUSALS:
            prefix, _, suffix = code.partition('_')
            literal = ("'%s'" % code) in text or ('"%s"' % code) in text
            built = ("+ '_%s'" % suffix) in text and ("code_prefix='%s'" % prefix) in text
            self.assertTrue(literal or built, code)

    def test_a_stale_intent_refusal_names_both_causes(self):
        from intune_iac.workbench_screens import REFUSALS
        for code in ('workbench_repository_stale', 'maintenance_repository_stale'):
            meaning, step = REFUSALS[code]
            self.assertIn('no longer consumes exactly this policy', meaning)
            self.assertIn('fix the component', step)

    def test_an_unknown_refusal_shows_only_what_the_engine_said(self):
        from intune_iac.workbench_screens import refusal_lines
        lines = refusal_lines({'status': 'error', 'error': {'code': 'something_new', 'message': 'Engine words.'}}, 80)
        self.assertEqual(lines, ['[REFUSED] Something new (something_new)', 'Cause: Engine words.'])

    def test_a_stale_or_incomplete_observation_refusal_says_which_and_what_to_do(self):
        from intune_iac.workbench_screens import refusal_lines
        message = 'Maintenance evidence is incomplete, changed, stale, or outside the local model profile.'
        for code, words in (('maintenance_observation_stale', 'not fresh, or the service changed'),
                            ('maintenance_observation_incomplete', 'incomplete, or the last collection did not finish')):
            joined = '\n'.join(refusal_lines({'status': 'error', 'error': {'code': code, 'message': message}}, 200))
            self.assertIn(words, joined)
            self.assertIn('Next: Collect again', joined)
            self.assertIn('a: actions)', joined)

    def test_a_meaning_the_engine_message_already_states_is_not_repeated(self):
        from intune_iac.workbench_screens import refusal_lines
        message = ('The repository changed since this intent was recorded, or its component no longer consumes exactly '
                   'this policy. Refresh the intent, review the difference and prepare a new proposal.')
        lines = refusal_lines({'status': 'error', 'error': {'code': 'workbench_repository_stale', 'message': message}}, 100)
        joined = '\n'.join(lines)
        self.assertNotIn('What it means', joined)
        self.assertEqual(joined.count('The repository changed since'), 1)
        self.assertIn('Next: Press 9 to see which', joined)
        # A short technical message gives way to the plain cause.
        terse = refusal_lines({'status': 'error', 'error': {'code': 'workbench_repository_stale', 'message': 'stale'}}, 100)
        self.assertIn('Cause: The repository changed since its recorded intent', '\n'.join(terse))
        # A message naming something particular stays, and the meaning is added where it says more.
        named = refusal_lines({'status': 'error', 'error': {'code': 'workbench_repository_stale',
                                                            'message': 'stacks/orgs/dev.yaml changed'}}, 100)
        self.assertIn('stacks/orgs/dev.yaml changed', '\n'.join(named))
        self.assertIn('In general: The repository changed since its recorded intent', '\n'.join(named))


class SurfaceRoutingTests(unittest.TestCase):
    """The terminal routes typed results to their readable screens."""
    def summary(self, tab, value, width=100):
        from intune_iac.workbench_tui import Workspace
        workspace = Workspace.__new__(Workspace)
        workspace.tab, workspace.value, workspace.selected, workspace.facts = tab, value, POLICY_ID, {'name': 'Windows Privacy Pilot'}
        return '\n'.join(workspace._surface_summary(width))

    def test_health_and_queue_render_on_the_coverage_surface(self):
        health = {'collection_health': {'targeted': None}, 'freshness': 'fresh',
                  'objects': [{'object_id': POLICY_ID, 'name': 'P', 'health': {'stages': EMPTY_STAGES, 'endpoint_health': 'unknown'}}]}
        self.assertIn('[HEALTH AND REPORTING]', self.summary(6, health))
        self.assertIn('[MAINTENANCE QUEUE]', self.summary(6, {'findings': [], 'pagination': {'total_objects': 0}}))

    def test_the_context_strip_keeps_observation_freshness_apart_from_lineage_freshness(self):
        from intune_iac.workbench_tui import Workspace
        workspace = Workspace.__new__(Workspace)
        workspace.__dict__.update(selected=POLICY_ID, facts={}, last_command='lineage')
        workspace._learn(dict(LINEAGE, observation_freshness='fresh'))
        self.assertEqual(workspace.facts['observation'], 'fresh')
        workspace._learn({'object_id': POLICY_ID, 'freshness': 'stale', 'name': 'P'})
        self.assertEqual(workspace.facts['observation'], 'stale')

    def test_families_render_on_the_help_surface(self):
        from intune_iac.families import families
        text = self.summary(7, families())
        self.assertIn('[POLICY FAMILIES]', text); self.assertNotIn('Full engine values follow', text)

    def test_a_recorded_artifact_renders_its_header_on_any_surface(self):
        text = self.summary(5, dict(RecordedLinesTests.RUN))
        self.assertIn('[RECORDED] CI workflow run aaaaaaaaaaaa', text); self.assertNotIn('[EXACT', text)

    def test_a_refusal_renders_on_any_surface(self):
        value = {'status': 'error', 'error': {'code': 'selection_required', 'message': 'Select an exact immutable object ID first.'}}
        for tab in (0, 4, 8):
            text = self.summary(tab, value)
            self.assertIn('[REFUSED] No policy is selected (selection_required)', text)
            self.assertIn('press 1 for Estate', text)

    def test_diagnostics_render_on_the_coverage_surface(self):
        text = self.summary(6, DIAGNOSTICS)
        self.assertIn('[DIAGNOSTICS]', text); self.assertNotIn('Full engine values follow', text)

    def test_lineage_and_a_cleared_selection_have_readable_screens(self):
        text = self.summary(2, LINEAGE)
        self.assertIn('[REPOSITORY LINEAGE]', text); self.assertNotIn('Full engine values follow', text)
        for tab in (0, 8):
            text = self.summary(tab, {'status': 'selection_cleared', 'mutation_dispatched': False})
            self.assertIn('[SELECTION CLEARED]', text)
            self.assertIn('Press 1 for Estate', text)

    def test_the_start_survey_renders_on_the_help_surface(self):
        survey = {'schema_version': 'workbench-start/1', 'directory': '/work', 'connection': 'offline', 'items': [],
                  'next_actions': ['Start from a supported export: intune-iac wizard --session session.json'],
                  'missing': ['No live discovery connection is configured.'], 'skipped_links': [], 'truncated': False}
        text = self.summary(7, survey)
        self.assertIn('INTUNE WORKBENCH: START', text); self.assertIn('NEXT', text)
        self.assertNotIn('Full engine values follow', text)

    def test_an_empty_estate_explains_how_to_get_observations(self):
        text = self.summary(0, {'objects': [], 'pending_observations': [], 'pagination': {'total_objects': 0}})
        self.assertIn('[NO OBSERVATIONS YET]', text)
        self.assertIn('press s to see what exists beside the store', text)
        self.assertNotIn('[NO OBSERVATIONS YET]', self.summary(0, {'objects': [], 'query': 'none', 'pagination': {'total_objects': 0}}))

    def test_single_policy_health_uses_the_name_already_read_for_that_identity(self):
        value = {'object_id': POLICY_ID, 'stages': EMPTY_STAGES, 'reason': 'No policy-bound device evidence was imported.'}
        self.assertIn('Windows Privacy Pilot (' + POLICY_ID + ')', self.summary(6, value))
        other = dict(value, object_id='33333333-3333-4333-8333-333333333333')
        self.assertIn('(no name) (33333333-3333-4333-8333-333333333333)', self.summary(6, other))

    def test_history_surface_uses_the_comparing_renderer(self):
        value = {'object_id': POLICY_ID, 'order': 'observed_at_desc_observation_id_desc',
                 'history': [{'observed_at': 'T2', 'body': body(description=EDITED)}, {'observed_at': 'T1', 'body': body()}]}
        text = self.summary(3, value)
        self.assertIn('[OBSERVATION HISTORY]', text); self.assertIn('Newest first', text)
        self.assertIn('Changed since the previous observation (T1):', text)


class EstateScreenEdgeTests(unittest.TestCase):
    def test_history_does_not_claim_a_change_it_cannot_compare(self):
        from intune_iac.workbench_screens import history_lines
        uncollected = body(assignments=None)
        value = {'object_id': POLICY_ID, 'pagination': {'total_observations': 3, 'has_more': True},
                 'history': [{'observed_at': 'T2', 'body': uncollected, 'field_accounting': {'assignments': 'not_collected'}},
                             {'observed_at': 'T1', 'body': body()}]}
        joined = '\n'.join(history_lines(value, 100))
        self.assertNotIn('Changed since the previous observation', joined)
        self.assertIn('Comparison with the previous observation (T1):', joined)
        self.assertIn('CHANGE COMPARISON UNKNOWN', joined)
        self.assertIn('Not completely observed: assignments not_collected', joined)
        self.assertIn('Earliest observation on this page; n shows older observations.', joined)

    def test_history_says_when_nothing_changed(self):
        from intune_iac.workbench_screens import history_lines
        value = {'object_id': POLICY_ID, 'history': [{'observed_at': 'T2', 'body': body()}, {'observed_at': 'T1', 'body': body()}]}
        self.assertIn('  No configuration change since the previous observation.', history_lines(value, 100))

    def test_health_fits_narrow_terminals_and_scales_large_cohorts(self):
        from intune_iac.workbench_screens import health_lines
        stages = dict(EMPTY_STAGES, receipt=stage(1000, 900, 880, 120), execution=dict(stage(1000, 850, 800, 150), failed=30, pending=20, missing=150))
        lines = health_lines({'object_id': POLICY_ID, 'stages': stages, 'endpoint_health': 'unknown'}, 60)
        joined = '\n'.join(lines)
        for line in lines:
            self.assertLessEqual(cell_width(line), 60, line)
        self.assertIn('800 of 1000 targeted devices reported success at execution; 30 reported failure; 20 pending; 150 without a fresh report', joined.replace('\n  ', ' '))
        self.assertIn('Not counted as fresh success: 150 missing', joined)
        self.assertIn('each cell is up to 3 devices; exact counts above', joined.replace('\n    ', ' '))
        matrix = ''.join(match.group(1) for match in (MATRIX_ROW.match(line) for line in lines) if match)
        self.assertEqual((matrix.count('#'), matrix.count('x'), matrix.count('~'), matrix.count('.')), (267, 10, 7, 50))
        self.assert_aligned(lines, ['execution', '1000', '850', '800', '30', '20', '0', '150'], 'NONE')
        self.assertIn('TGT targeted', joined)
        tiny = health_lines({'object_id': POLICY_ID, 'stages': stages}, 40)
        for line in tiny:
            self.assertLessEqual(cell_width(line), 40, line)
        self.assertIn('execution: 1000 targeted | 850 reported | 800 success', '\n'.join(tiny).replace('\n  ', ' '))

    def assert_aligned(self, lines, cells, last_title):
        header = next(line for line in lines if line.startswith('  STAGE'))
        row = next(line for line in lines if line.startswith('  ' + cells[0] + ' '))
        self.assertEqual(row.split(), cells)
        self.assertEqual(len(row), len(header), (header, row))
        self.assertTrue(header.endswith(last_title))

    def test_full_stage_table_fits_an_80_column_terminal(self):
        from intune_iac.workbench_screens import health_lines
        lines = health_lines({'object_id': POLICY_ID, 'stages': dict(EMPTY_STAGES, execution=stage(100, 8, 8, 92))}, 78)
        self.assert_aligned(lines, ['execution', '100', '8', '8', '0', '0', '0', '92'], 'NO REPORT')
        self.assertEqual(max(cell_width(line) for line in lines), 78)

    def test_queue_groups_journal_records_by_operation(self):
        from intune_iac.workbench_screens import queue_lines
        records = [{'operation_id': 'b668ad2fa6c54d20b94bd8677ce56735', 'sequence': 1, 'status': 'prepared', 'recorded_at': 'T1'},
                   {'operation_id': 'b668ad2fa6c54d20b94bd8677ce56735', 'sequence': 2, 'status': 'succeeded_verified', 'recorded_at': 'T2'}]
        value = {'findings': [{'object_id': POLICY_ID, 'finding': 'ownership_unknown', 'priority': 'review', 'owner': None,
                               'owner_role': 'human_review_assignee', 'writer_ownership': {'status': 'unknown', 'reason': 'ownership_index_missing'},
                               'source_owner_claim': {'assertion_class': 'source_declared', 'value': None},
                               'review_record': {'status': 'unknown', 'reason': 'review_not_recorded'},
                               'compatibility': {'profile': 'synthetic_windows_settings_catalog', 'native_provider_qualified': False},
                               'evidence': {'evidence_class': 'synthetic', 'observed_at': 'T0', 'snapshot_id': 'a' * 64},
                               'related_proposals': records}]}
        joined = '\n'.join(queue_lines(value, 120))
        self.assertIn('Owner role human review assignee: none recorded | writer unknown: ownership index missing (ownership_index_missing) | source owner claim none recorded', ' '.join(joined.split()))
        self.assertIn('  Review not recorded | review due none | exception expiry none', joined)
        self.assertIn('Compatibility synthetic windows settings catalog (synthetic_windows_settings_catalog) | native provider not qualified', joined)
        self.assertIn('Related operations (1)\n    b668ad2f succeeded verified (2 journal records; latest T2)', joined)  # run 12 L-proposals


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


class ClockHoldScreensTests(unittest.TestCase):
    """PKG-PRES-HOLD items 3, 5 and 6 as the screens word them: the queue finding of a held observation reads age
    unknown with the recovery; a blocked row lists every reason; the Diagnostics evidence names the times."""
    TIMES = "this host's clock reads 2027-01-15 08:00:00 UTC; this workspace recorded 2027-01-15 08:04:26 UTC"
    FACT = {'reads': 1_800_000_000.0, 'recorded': 1_800_000_266.0}

    def finding(self, name='observation_stale', reasons=('clock_moved_backward',), fact=FACT):
        evidence = {'evidence_class': 'synthetic', 'observed_at': '2027-01-15T07:50:00Z', 'snapshot_id': 'a' * 64}
        if reasons:
            evidence['freshness_reasons'] = list(reasons)
        if fact:
            evidence['freshness_clock'] = dict(fact)
        return {'object_id': POLICY_ID, 'finding': name, 'priority': 'review', 'freshness': 'stale',
                'priority_rationale': 'A current complete observation is required before assessing changes.',
                'action_state': 'review_required', 'owner_assertion': 'unknown', 'automatic_remediation': False,
                'evidence': evidence, 'review_due': None, 'exception_expiry': None, 'related_proposals': []}

    def queue_text(self, *findings):
        from intune_iac.workbench_screens import queue_lines
        value = {'findings': list(findings), 'pagination': {'total_objects': 1}}
        return ' '.join(' '.join(queue_lines(value, 120)).split())

    def test_the_queue_finding_of_a_held_observation_reads_age_unknown_with_the_recovery(self):
        text = self.queue_text(self.finding())
        self.assertIn('freshness age unknown (host clock behind a recorded time)', text)
        self.assertNotIn('freshness stale', text)
        self.assertIn('Next: Correct the host clock, or wait until it reads at or after the time this workspace '
                      'recorded; restart the workbench after correcting the clock. Collecting again does not clear this '
                      '(%s).' % self.TIMES, text)
        unreadable = self.queue_text(self.finding(reasons=('clock_floor_invalid',), fact={'reads': 1_800_000_000.0,
                                                                                         'recorded': None}))
        self.assertIn('freshness age unknown (the recorded time cannot be read)', unreadable)

    def test_only_the_stale_finding_carries_the_recovery_and_other_findings_still_read_age_unknown(self):
        text = self.queue_text(self.finding('reporting_incomplete'))
        self.assertIn('freshness age unknown (host clock behind a recorded time)', text)
        self.assertNotIn('Collecting again does not clear this', text)

    def test_a_finding_without_a_hold_keeps_its_words(self):
        text = self.queue_text(self.finding(reasons=('older_than_window',), fact=None))
        self.assertIn('freshness stale', text)
        self.assertNotIn('age unknown', text)

    def blocked_row(self):
        return {'kind': 'propose-from-intent', 'label': 'Prepare a proposal from the recorded intent', 'available': False,
                'blocked': {'code': 'maintenance_observation_stale', 'reason': 'not_fresh', 'message': 'the clock holds it',
                            'clock_hold': 'clock_moved_backward',
                            'also': [{'code': 'workbench_repository_stale', 'reason': 'repository_changed',
                                      'message': 'The repository changed since its recorded intent'}]}}

    def test_a_blocked_action_row_lists_every_reason(self):
        from intune_iac.workbench_screens import actions_lines
        text = ' '.join(' '.join(actions_lines([self.blocked_row()], 0, 120)).split())
        self.assertIn('blocked the clock holds it (maintenance_observation_stale)', text)
        self.assertIn('also blocked The repository changed since its recorded intent (workbench_repository_stale)', text)

    def test_the_inspector_action_list_names_both_reasons(self):
        from intune_iac.workbench_screens import _attention_lines
        value = {'attention': {'signals': [], 'checked': {}, 'status': 'clear'}, 'actions': [self.blocked_row()]}
        text = ' '.join(' '.join(_attention_lines(value, 120)).split())
        # Run 8 item 2: under a clock hold the observation's age is not known, so it is "not known to be fresh".
        self.assertIn('(blocked: the observation is not known to be fresh; the repository changed since its intent)', text)

    def test_the_diagnostics_evidence_names_the_times_not_a_raw_map(self):
        from intune_iac.workbench_screens import diagnostics_lines
        signal = {'area': 'freshness', 'code': 'observation_stale', 'observed': 'Not known to be fresh.',
                  'next_step': 'Wait.', 'evidence': {'freshness_reasons': ['clock_moved_backward'],
                                                     'freshness_clock': self.FACT}}
        text = ' '.join(' '.join(diagnostics_lines({'name': 'Pilot', 'object_id': POLICY_ID, 'signals': [signal],
                                                    'checked': {}}, 160)).split())
        self.assertIn(self.TIMES, text)
        self.assertNotIn("{'reads'", text)
        self.assertNotIn('1800000000', text)


if __name__ == '__main__':
    unittest.main()


class WhoClaimsWhatTests(unittest.TestCase):
    """Journey 28 review S2: the engine's report, the store's registration and reconcile's readback, each labelled."""

    def test_an_unknown_outcome_says_the_engine_reported_and_the_store_never_registered(self):
        from intune_iac.workbench_screens import delivery_lines
        value = delivery_value(execution={'status': 'unknown', 'error_code': None, 'service_status': None},
                               readback={'status': 'not_recorded'})
        joined = '\n'.join(delivery_lines(value, 160))
        self.assertIn('[?] 4 Execution       outcome unknown: the engine reported succeeded verified, but the store never recorded '
                      'a verified result', joined)
        self.assertIn('[?] 5 Readback        not recorded: execution ended before its own independent readback', joined)
        value = delivery_value(execution={'status': 'unknown', 'engine_status': None, 'error_code': 'model_response_lost',
                                          'service_status': None})
        joined = '\n'.join(delivery_lines(value, 160))
        self.assertIn("outcome unknown: the modeled service's response was lost (model_response_lost) | no engine result recorded", joined)
        self.assertNotIn('engine None', joined)

    def test_reconciles_readback_is_labelled_as_its_own(self):
        from intune_iac.workbench_screens import _event_text, delivery_lines
        value = delivery_value(reconciliation={'status': 'done', 'classification': 'desired_state_observed',
                                               'previous_status': 'outcome_unknown', 'count': 1})
        joined = '\n'.join(delivery_lines(value, 160))
        self.assertIn("6 Reconciliation  reconcile's readback: desired state observed | after outcome unknown", joined)
        text = _event_text({'kind': 'reconciled', 'fields': {'classification': 'desired_state_observed',
                                                             'previous_status': 'outcome_unknown'}})
        self.assertEqual(text, "reconcile's readback: desired state observed, after outcome unknown")

    def test_the_delivery_next_step_names_reconciles_readback_in_words(self):
        from intune_iac.workbench_delivery import _next_action
        stages = {stage['stage']: stage for stage in delivery_value(
            approval={'status': 'done'}, readback={'status': 'not_recorded'},
            reconciliation={'status': 'done', 'classification': 'desired_state_observed', 'previous_status': 'outcome_unknown'},
            deployment_record={'status': 'not_available', 'reason': 'no_verified_readback'})['stages']}
        text = _next_action(stages, '/w/op', '/w/store')
        self.assertNotIn("readback: desired state observed", text)  # said once, in the reconciliation stage (run 7 item 13)
        self.assertIn('This operation cannot become a deployment record because its own readback was never verified', text)
        self.assertNotIn('desired_state_observed', text)


class PlanUnderReviewTests(unittest.TestCase):
    """Journey 28 review S3: when the plan under review is not the policy's newest operation, the state line says so."""
    STATES = {'operation': {'operation_id': '23c0d15f' + 'a' * 24, 'status': 'prepared', 'journal_status': 'prepared',
                            'recorded_at': '2026-10-15T03:21:19Z'}}

    def test_the_state_line_says_which_operation_it_describes(self):
        from intune_iac.workbench_screens import state_lines
        text = ' '.join(' '.join(state_lines(self.STATES, 160, reviewing='16e3d1d3' + 'b' * 24)).split())
        self.assertIn('newest for this policy: 23c0d15f prepared', text)
        self.assertIn('The plan below is a different operation, 16e3d1d3.', text)

    def test_the_same_operation_needs_no_note(self):
        from intune_iac.workbench_screens import state_lines
        text = ' '.join(' '.join(state_lines(self.STATES, 160, reviewing='23c0d15f' + 'a' * 24)).split())
        self.assertNotIn('different operation', text)
        self.assertNotIn('newest for this policy', text)


class NarrowWindowTests(unittest.TestCase):
    """Journey 28 review L5 and S7: at 60 and 80 columns the band keeps "never replays", and the strip keeps the
    operation's state, the band's own hazard, before a less severe one."""
    ELIGIBILITY = {'code': 'maintenance_observation_stale', 'reason': 'service_changed', 'observed_revision': 2,
                   'service_revision': 3}

    def test_the_band_keeps_never_replays_where_a_form_with_it_fits(self):
        from intune_iac.workbench_screens import hazard_rows
        from plugin_tests.test_workbench_hazard import UNKNOWN
        for width in (60, 80):
            rows = hazard_rows({'eligibility': self.ELIGIBILITY}, [UNKNOWN], width, here=True)
            self.assertIn('never replays', rows[0], (width, rows))
            self.assertIn('+1 more finding (2 Inspector)', ' '.join(rows), (width, rows))  # run 12 L-more
            for row in rows:
                self.assertLessEqual(cell_width(row), width, row)
        for row in hazard_rows({'eligibility': self.ELIGIBILITY}, [UNKNOWN], 40, here=True):
            self.assertLessEqual(cell_width(row), 40, row)

    def test_the_strip_keeps_the_operation_before_a_less_severe_hazard(self):
        from intune_iac.workbench_screens import context_strip
        from plugin_tests.test_workbench_hazard import POLICY, TENANT
        facts = {'name': 'Windows Privacy Pilot', 'observation': 'fresh', 'eligibility': self.ELIGIBILITY,
                 'repository': 'current', 'operation': 'outcome_unknown'}
        # Where the operation and the marker both fit, the operation stays and the less severe states are counted.
        self.assertEqual(context_strip(TENANT, POLICY, facts, 62, 'synthetic'),
                         'SYNTHETIC | T 11111111 | P 22222222 | OP unknown | +2 more: ?')
        # Where they do not, the marker wins (nothing is dropped silently); the band still leads with the operation.
        self.assertEqual(context_strip(TENANT, POLICY, facts, 60, 'synthetic'),
                         'SYNTHETIC | TENANT 11111111 | POLICY 22222222 | +3 more: ?')
        self.assertEqual(context_strip(TENANT, POLICY, facts, 48, 'synthetic'),
                         'SYNTHETIC | T 11111111 | P 22222222 | +3 more: ?')


class HistoryCurrentTests(unittest.TestCase):
    """Journey 28 run 3, frame 64: the page says what its order is and which observation is current."""
    VALUE = {'object_id': POLICY_ID, 'order': 'observed_at_desc_observation_id_desc',
             'history': [{'observed_at': '2026-10-15T05:27:14Z', 'run_id': 4, 'body': body()},
                         {'observed_at': '2026-10-15T05:12:16Z', 'run_id': 5, 'body': body()}]}

    def test_the_current_observation_and_a_later_stamped_one_are_marked(self):
        from intune_iac.workbench_screens import history_lines
        lines = history_lines(self.VALUE, 160, current={'run_id': 5, 'observed_at': '2026-10-15T05:12:16Z'})
        joined = '\n'.join(lines)
        self.assertIn('Newest first by observation time', joined)
        run4 = next(line for line in lines if '| run 4 |' in line)
        run5 = next(line for line in lines if '| run 5 |' in line)
        self.assertIn('current', run5)
        self.assertIn('not current: stamped later than the current observation', run4)

    def test_without_a_known_current_observation_nothing_is_marked(self):
        from intune_iac.workbench_screens import history_lines
        joined = '\n'.join(history_lines(self.VALUE, 160))
        self.assertNotIn('not current', joined)


class DeliveryRun7Tests(unittest.TestCase):
    """PKG-PRES-RUN7 items 6, 9 and 13 on the Delivery view (run 7 frames 20, 25, 28, 39): codes read as words, a stage
    that is only not available yet has its own marker, and the reconcile readback is said once."""

    def reconciled_value(self):
        from intune_iac.workbench_delivery import _next_action
        value = delivery_value(
            approval={'status': 'done'}, execution={'status': 'unknown', 'error_code': None, 'service_status': None},
            readback={'status': 'not_recorded'},
            reconciliation={'status': 'done', 'classification': 'desired_state_observed',
                            'previous_status': 'outcome_unknown', 'count': 1, 'recorded_at': '2026-10-14T12:25:03Z'},
            deployment_record={'status': 'not_available', 'reason': 'no_verified_readback'},
            observed_after={'status': 'not_yet'})
        value['journal_status'] = 'reconciled'
        stages = {stage['stage']: stage for stage in value['stages']}
        value['next_action'] = _next_action(stages, '/w/op', '/w/store')
        value['history'] = {'events': [
            {'sequence': 2, 'kind': 'engine_result', 'store_recorded_at': None,
             'fields': {'result': {'status': 'succeeded_verified', 'assurance': 'synthetic_local_process_only'}}},
            {'sequence': 3, 'kind': 'reconciled', 'store_recorded_at': '2026-10-14T12:25:03Z',
             'fields': {'classification': 'desired_state_observed', 'previous_status': 'outcome_unknown'}}]}
        return value

    def test_the_header_and_the_history_read_as_words(self):
        from intune_iac.workbench_screens import delivery_lines
        joined = '\n'.join(delivery_lines(delivery_value(), 160))
        self.assertIn('| journal succeeded verified', joined)
        self.assertNotIn('succeeded_verified', joined)
        text = '\n'.join(delivery_lines(self.reconciled_value(), 160))
        self.assertIn('engine reported succeeded verified (synthetic local process only)', text)
        for code in ('succeeded_verified', 'synthetic_local_process_only', 'desired_state_observed', 'outcome_unknown'):
            self.assertNotIn(code, text)

    def test_a_recorded_error_reads_as_words_with_its_code_in_parentheses(self):
        from intune_iac.workbench_screens import delivery_lines
        value = delivery_value(execution={'status': 'unknown', 'engine_status': None, 'error_code': 'model_response_lost',
                                          'service_status': None})
        joined = '\n'.join(delivery_lines(value, 200))
        self.assertIn("outcome unknown: the modeled service's response was lost (model_response_lost) | no engine "
                      'result recorded', joined)
        value = delivery_value(execution={'status': 'unknown', 'engine_status': None, 'error_code': 'maintenance_engine_incomplete',
                                          'service_status': None})
        self.assertIn('outcome unknown: maintenance engine incomplete (maintenance_engine_incomplete)',
                      '\n'.join(delivery_lines(value, 200)))

    def test_only_a_stopped_stage_is_marked_with_an_exclamation_mark(self):
        from intune_iac.workbench_screens import MARK_LEGEND, delivery_lines
        joined = '\n'.join(delivery_lines(self.reconciled_value(), 160))
        self.assertIn('[~] 7 Deployment      not available: no verified readback', joined)
        self.assertNotIn('[!] 7 Deployment', joined)
        self.assertIn('[~] not available yet', MARK_LEGEND)
        self.assertIn('[!] stopped: failure, expiry or refusal', MARK_LEGEND)
        # A refusal that will not change is stopped, not merely unavailable.
        value = delivery_value(deployment_record={'status': 'not_available', 'reason': 'context_changed'})
        self.assertIn('[!] 7 Deployment', '\n'.join(delivery_lines(value, 160)))

    def test_the_reconcile_readback_is_said_once(self):
        from intune_iac.workbench_screens import delivery_lines
        joined = ' '.join('\n'.join(delivery_lines(self.reconciled_value(), 160)).split())
        self.assertEqual(joined.count('desired state observed'), 1, joined)
        self.assertIn("6 Reconciliation reconcile's readback: desired state observed | after outcome unknown", joined)
        self.assertIn('This operation cannot become a deployment record because its own readback was never verified; '
                      'collect to observe the policy.', joined)


class QueueRun7Tests(unittest.TestCase):
    """PKG-PRES-RUN7 items 6 and 13 on the maintenance queue and the actions layer (run 7 frames 45 and 47): codes read as
    words with the lookup key in parentheses, and the object's details are said once, not under every finding."""
    OBJECT_DETAILS = {'owner_role': 'human_review_assignee', 'owner': None, 'owner_assertion': 'unknown',
                      'writer_ownership': {'status': 'unknown', 'reason': 'ownership_index_missing'},
                      'source_owner_claim': {'value': None}, 'action_state': 'review_required', 'freshness': 'fresh',
                      'automatic_remediation': False, 'review_record': {'status': 'not_recorded'},
                      'compatibility': {'profile': 'synthetic_windows_settings_catalog', 'native_provider_qualified': False},
                      'evidence': {'evidence_class': 'synthetic', 'observed_at': '2026-10-15T14:25:25Z', 'snapshot_id': 'ab' * 32},
                      'related_proposals': [{'operation_id': 'a' * 32, 'sequence': 1, 'status': 'succeeded_verified',
                                             'recorded_at': '2026-10-15T14:24:16Z'}]}

    def value(self, *findings):
        return {'findings': [dict(self.OBJECT_DETAILS, object_id=POLICY_ID, finding=name, priority='review',
                                  priority_rationale='Why ' + name) for name in findings],
                'pagination': {'total_objects': 1}}

    def test_related_proposals_and_the_writer_reason_read_as_words(self):
        from intune_iac.workbench_screens import queue_lines
        text = '\n'.join(queue_lines(self.value('reporting_incomplete'), 160))
        self.assertIn('succeeded verified (1 journal record; latest 2026-10-15 14:24:16 UTC)', text)
        self.assertNotIn('succeeded_verified', text)
        self.assertIn('writer unknown: ownership index missing (ownership_index_missing)', text)

    def test_the_details_of_one_object_are_said_once_and_each_finding_keeps_what_differs(self):
        from intune_iac.workbench_screens import queue_lines
        text = '\n'.join(queue_lines(self.value('reporting_incomplete', 'ownership_unknown'), 160))
        for once in ('Owner role human review assignee', 'Compatibility synthetic windows settings catalog',
                     'Related operations (1)', 'Evidence synthetic | observed', 'State review required'):
            self.assertEqual(text.count(once), 1, once)
        self.assertEqual(text.count('Why: Why '), 2)
        self.assertEqual(text.count(':queue-review-template '), 2)
        self.assertIn('Same object details as the finding above', text)

    def test_a_detail_that_differs_between_findings_is_still_shown(self):
        from intune_iac.workbench_screens import queue_lines
        value = self.value('reporting_incomplete', 'ownership_unknown')
        value['findings'][1]['action_state'] = 'in_review'
        text = '\n'.join(queue_lines(value, 160))
        self.assertEqual(text.count('State review required'), 1)
        self.assertEqual(text.count('State in review'), 1)
        self.assertEqual(text.count('Compatibility synthetic windows settings catalog'), 1)

    def test_a_blocked_action_leads_with_words_and_keeps_its_code_in_parentheses(self):
        from intune_iac.workbench_screens import actions_lines
        action = {'label': 'Prepare a proposal', 'available': False, 'summary': 'Creates a local proposal.',
                  'blocked': {'code': 'maintenance_observation_stale', 'reason': 'not_fresh',
                              'message': 'the newest observation is not fresh (older than the freshness window); collect again',
                              'also': [{'code': 'some_other_block', 'message': 'the repository changed'}]}}
        text = ' '.join(' '.join(actions_lines([action], 0, 160)).split())
        self.assertIn('blocked the newest observation is not fresh (older than the freshness window); collect again '
                      '(maintenance_observation_stale)', text)
        self.assertIn('also blocked the repository changed (some_other_block)', text)
        self.assertNotIn('blocked  maintenance_observation_stale:', text)


class QuotedPathsTests(unittest.TestCase):
    """PKG-PRES-RUN7 item 14 (run 7 frames 02, 03, 04, 44, 48): a path with spaces is quoted wherever a screen shows it,
    so it reads and copies as one path, and a quoted path is not broken at a space when the line wraps."""
    SPACED = '/home/nsahm/work/journey 28 run 7'

    def test_the_adoption_preview_and_result_quote_their_paths(self):
        from intune_iac.workbench_screens import adoption_lines
        preview = {'binding': {'object_ids': ['22222222-2222-4222-8222-222222222222'], 'session': self.SPACED + '/session.json',
                               'generated': {'22222222-2222-4222-8222-222222222222': {'path': self.SPACED + '/generated/x'}},
                               'source': {'path': self.SPACED + '/export.json'}, 'context': {'path': '/w/context.json'},
                               'repository': {'root': self.SPACED + '/repo'}}}
        text = ' '.join(' '.join(adoption_lines(preview, 400)).split())
        for path in ('/generated/x', '/session.json', '/export.json', '/repo'):
            self.assertIn("'" + self.SPACED + path + "'", text, path)
        self.assertIn('| context /w/context.json', text)  # no spaces, no quotes
        adopted = {'status': 'adopted_local_model', 'object_ids': ['22222222-2222-4222-8222-222222222222'],
                   'handoff_root': self.SPACED + '/handoff', 'service_root': self.SPACED + '/handoff/service',
                   'adoptions': [], 'cloud_authority': False, 'execution_authorized': False, 'remote_import_performed': False}
        text = ' '.join(' '.join(adoption_lines(adopted, 400)).split())
        self.assertIn("Handoff: '%s/handoff'" % self.SPACED, text)
        self.assertIn("Modeled service: '%s/handoff/service'" % self.SPACED, text)

    def test_the_estate_and_the_review_form_quote_their_paths(self):
        from intune_iac.workbench_screens import review_lines, service_words
        self.assertIn("Modeled service: '%s/handoff/service' (from the latest" % self.SPACED,
                      service_words({'source': 'adoption', 'root': self.SPACED + '/handoff/service', 'artifact_id': 'a' * 64}))
        self.assertEqual(service_words({'source': 'flag', 'root': '/w/service'}), 'Modeled service: /w/service (--service-root)')
        lines = review_lines({'status': 'review_form_written', 'path': self.SPACED + '/queue review.json',
                              'finding': 'reporting_incomplete', 'object_id': 'o'}, 200)
        self.assertEqual(lines[0], "[REVIEW FORM WRITTEN] '%s/queue review.json'" % self.SPACED)

    def test_a_quoted_path_is_not_broken_at_a_space_when_the_line_wraps(self):
        from intune_iac.workbench_screens import word_wrap
        quoted = "'%s/generated/22222222-2222-4222-8222-222222222222'" % self.SPACED
        for width in (90, 100, 120):
            rows = word_wrap('  22222222-2222-4222-8222-222222222222  generated at %s' % quoted, width)
            self.assertTrue(any(quoted in row for row in rows), (width, rows))
        # Wider than the line: it is cut after a "/", so no row ends or starts on one of its spaces.
        for width in (40, 60, 80):
            rows = word_wrap('  22222222-2222-4222-8222-222222222222  generated at %s' % quoted, width)
            self.assertTrue(''.join(row.strip() for row in rows).endswith(quoted), (width, rows))
            for row in rows:
                self.assertLessEqual(len(row), width, row)


class MinorWrapsTests(unittest.TestCase):
    """PKG-PRES-RUN7 item 15 (run 7 frames 05, 06, 25, 28): an address breaks at a delimiter, not inside its identifier; a
    command breaks outside a word; a time and its zone are never parted."""
    IDENTIFIER = 'p_11111111111141118111111111111111_22222222222242228222222222222222'
    ADDRESS = ('microsoft365_graph_beta_device_management_settings_catalog_configuration_policy_json.policy["%s"]'
               % IDENTIFIER)

    def test_an_address_breaks_after_its_opening_bracket_and_quote_not_inside_the_identifier(self):
        from intune_iac.workbench_screens import repository_entry_lines
        value = {'repository': '/w/repo', 'revision': 'd' * 40, 'tenant_id': 't' * 36, 'status': 'discovered',
                 'components': [], 'candidates': [{'number': 1, 'object_id': '2' * 8 + '-2222-4222-8222-' + '2' * 12,
                                                   'stack': 'orgs/reference/dev', 'component': 'intune-reference',
                                                   'state': 'ready', 'policy_key': self.IDENTIFIER, 'backend': 'local',
                                                   'backend_source': 'none_declared', 'resource_address': self.ADDRESS}]}
        for width in (100, 116, 120, 140):
            lines = repository_entry_lines(value, width)
            start = next(index for index, line in enumerate(lines) if line.startswith('     Address'))
            rows = [line[15:] for line in lines[start:start + 3] if line.startswith(' ' * 15) or line.startswith('     Address')]
            rows[0] = lines[start][15:]
            joined = ''.join(row.rstrip() for row in rows)
            self.assertIn(self.ADDRESS, joined, width)
            # The identifier is never cut: every row that holds a piece of it holds all of it.
            holding = [row for row in rows if 'p_1111' in row]
            self.assertTrue(all(self.IDENTIFIER in row for row in holding), (width, rows))

    def test_a_command_is_not_broken_inside_a_word(self):
        from intune_iac.workbench_screens import word_wrap
        command = ("repository-import '/home/nsahm/work/journey 28 run 7/repository' orgs/reference/dev intune-reference "
                   "22222222-2222-4222-8222-222222222222 /vars/policies/%s d42d6e875bfaf4df0b1e1c3e935743c4c2ead325 local '%s'"
                   % (self.IDENTIFIER, self.ADDRESS))
        for width in (100, 116, 120):
            rows = word_wrap(command, width)
            for before, after in zip(rows, rows[1:]):
                joined = before.split(' ')[-1] + after.split(' ')[0]
                if joined in command:  # one word cut in two: it must be cut at a delimiter
                    self.assertIn(before[-1:], './["', (width, before, after))
            self.assertTrue(all(len(row) <= width for row in rows))

    def test_a_time_and_its_zone_are_never_parted(self):
        from intune_iac.workbench_screens import word_wrap
        text = ('matches desired at service revision 2 (1 before the change) | observed 2026-10-15 14:24:23 UTC; '
                'recorded 2026-10-15 14:24:19 UTC | window 2026-10-15 14:24:07 UTC to 2026-10-15 14:29:07 UTC')
        for width in range(30, 120):
            rows = word_wrap(text, width)
            for row in rows:
                self.assertNotEqual(row.strip().split(' ')[0].rstrip(';)'), 'UTC', (width, rows))
            self.assertEqual(' '.join(' '.join(rows).split()), text)


def _flat(lines):
    return ' '.join(' '.join(lines).split())


class RunEightScreensTests(unittest.TestCase):
    """PKG-PRES-RUN8 (journey 28 run 8, FRAME-REVIEW-run8.md): what a screen says, never what it decides."""
    OPERATION = '625157a384594734be91cfbdf73929a1'
    CITED = '42cb3c2420d44ea613e5a897225befc5c93dc10cfb557ce2bbe6bad5a004677c'

    # Item 2 (frames 44, 45): unknown age is not "not fresh".
    def test_a_blocked_action_for_an_observation_of_unknown_age_says_not_known_to_be_fresh(self):
        from intune_iac.workbench import _observation_blocker, _reason_words
        for replaces in ('same_service', 'any_collection', None):
            problem = {'code': 'maintenance_observation_stale', 'reason': 'not_fresh',
                       'freshness_reasons': ['stamped_after_now'], 'next_collection_replaces': replaces}
            said = _reason_words(problem)
            self.assertIn('not known to be fresh', said)
            self.assertNotIn('is not fresh', said)
            # The stamp reason is given once, not as a bracket and again as a clause.
            self.assertEqual(said.count("this host's clock"), 1, said)
        blocker = _observation_blocker({'code': 'maintenance_observation_stale', 'reason': 'not_fresh',
                                        'freshness_reasons': ['stamped_after_now']})
        self.assertEqual(blocker['freshness_reasons'], ['stamped_after_now'])

    def test_the_compact_blocked_line_says_not_known_to_be_fresh_only_for_an_unknown_age(self):
        from intune_iac.workbench_screens import _attention_lines

        def line(reasons):
            blocked = {'code': 'maintenance_observation_stale', 'reason': 'not_fresh', 'message': 'm',
                       'freshness_reasons': reasons}
            action = {'label': 'Prepare a proposal from the recorded intent', 'available': False, 'blocked': blocked}
            return _flat(_attention_lines({'attention': {'signals': [], 'checked': {}}, 'actions': [action]}, 160))
        self.assertIn('(blocked: the observation is not known to be fresh)', line(['stamped_after_now']))
        self.assertIn('(blocked: the observation is not known to be fresh)', line(['clock_moved_backward']))
        # An observation known to be older than the window is not fresh, and says so.
        self.assertIn('(blocked: the observation is not fresh)', line(['older_than_window']))

    # Item 4 (frame 67): a refusal names its operation.
    def test_a_deployment_refusal_names_the_operation_in_cause_and_next(self):
        from intune_iac.workbench_screens import refusal_lines
        message = ('This operation cites repository intent %s, not the intent given; record the deployment with the '
                   'intent it cites.' % self.CITED)
        value = {'status': 'error', 'error': {'code': 'workbench_deployment_intent_not_cited', 'message': message,
                                              'effects': {'deployment_recorded': False}}}
        text = _flat(refusal_lines(value, 118, operation='625157a3'))
        self.assertIn('Cause: Operation 625157a3 cites repository intent ' + self.CITED, text)
        self.assertIn('Next: Record operation 625157a3 with the intent it cites', text)
        self.assertNotIn('This operation cites', text)
        self.assertNotIn('v Delivery name it', text)
        # With no operation known the wording stays general.
        plain = _flat(refusal_lines(value, 118))
        self.assertIn('Cause: This operation cites repository intent', plain)
        self.assertIn('Next: Record that operation with the intent it cites', plain)

    # Item 5 (frames 42, 44, 45): strip words that carry the cause, and the legend for the short ones.
    def test_the_strip_names_the_cause_where_the_width_allows(self):
        from intune_iac.workbench_screens import context_strip
        from plugin_tests.test_workbench_hazard import POLICY, TENANT
        ahead = {'name': 'Windows Privacy Pilot', 'observation': 'age unknown (stamped ahead)', 'repository': 'current',
                 'operation': 'reconciled'}
        self.assertIn('OBS age unknown | REPO current', context_strip(TENANT, POLICY, ahead, 120, 'synthetic'))
        self.assertNotIn('age?', context_strip(TENANT, POLICY, ahead, 120, 'synthetic'))
        stale = dict(ahead, observation='stale (later collection incomplete)')
        strips = {width: context_strip(TENANT, POLICY, stale, width, 'synthetic') for width in range(40, 141)}
        self.assertTrue(any('OBS stale (collection incomplete)' in strip for strip in strips.values()), strips)
        self.assertTrue(any('OBS stale |' in strip for strip in strips.values()), strips)  # still shortens when it must

    def test_the_context_help_lists_every_short_state_word_the_strip_can_show(self):
        from intune_iac.workbench_screens import SHORT_STATES, help_lines
        text = _flat(help_lines(120))
        for state, short in SHORT_STATES.items():
            self.assertIn('%s means' % short, text, state)
        for meaning in ('succeeded verified', 'not checked', 'outcome unknown', 'recorded intent not revalidated',
                        'desired state observed', 'age unknown'):
            self.assertIn(meaning, text)
        self.assertIn('age unknown (stamped ahead)', text)
        self.assertIn('stale (collection incomplete)', text)

    # Items 6 and 14 (frame 47): the queue's own review route, and codes as words.
    def test_the_queue_labels_each_findings_own_review_route_and_reads_codes_as_words(self):
        from intune_iac.workbench_screens import queue_lines
        text = '\n'.join(queue_lines(QueueRun7Tests().value('reporting_incomplete', 'ownership_unknown'), 160,
                                     selected=POLICY_ID))
        for finding in ('reporting_incomplete', 'ownership_unknown'):
            self.assertIn("This finding's review: write the form with the first command", text)
            self.assertIn('\n    The :queue-review-template command using %s, naming a new JSON file for the review form\n' % finding,
                          text + '\n')
            self.assertIn('review  %s (%s)  ' % (finding.replace('_', ' '), finding), text)
        self.assertNotIn('  Review: :queue-review-template', text)
        self.assertIn('State review required (review_required)', text)
        self.assertIn('Compatibility synthetic windows settings catalog (synthetic_windows_settings_catalog)', text)
        # The same-object line comes before the finding's own route, and the route says it is this finding's.
        self.assertLess(text.index('Same object details'), text.index('    The :queue-review-template command using ownership_unknown'))

    # Item 7 (frames 65, 70, 72, 73): each fact once.
    def test_the_approval_close_is_said_once_in_delivery_and_in_the_plan_next(self):
        from intune_iac.workbench_delivery import _next_action
        from intune_iac.workbench_screens import lifecycle_next
        stages = {'approval': {'status': 'expired', 'closes_at': 1791980997, 'recorded': True},
                  'proposal': {}, 'readback': {'status': 'not_started'}, 'reconciliation': {'status': 'not_needed'},
                  'deployment_record': {'status': 'not_yet'}, 'observed_after': {'status': 'not_yet'}}
        said = _next_action(stages, '/w/op', '/w/store')
        self.assertNotRegex(said, r'\d{4}-\d\d-\d\d')
        self.assertIn('Prepare a proposal from the recorded intent (a: actions)', said)
        self.assertIn('stage 3 says when its approval window closed', said)
        closed = lifecycle_next(4, {'status': 'prepared', 'approval_window': {'state': 'closed'}}, 0)
        self.assertEqual(closed, 'Prepare a proposal from the recorded intent (a: actions); this plan cannot run because its approval window is closed')
        self.assertNotIn('has closed', closed)

    # Item 8 (frames 08, 11 to 14, 16, 75, 77): the Source path is quoted when it holds a space.
    def test_the_repository_source_path_is_quoted_and_the_intent_has_one_length(self):
        status = dict(RepositoryLinesTests.STATUS,
                      freshness={'status': 'current', 'sources': {}, 'consumer': {'status': 'verified'}})
        status['scope'] = dict(status['scope'], repository='/home/engineer/journey 28 run 8/repository')
        text = '\n'.join(repository_lines(status, 120))
        self.assertIn("Source   '/home/engineer/journey 28 run 8/repository'", text)
        plain = '\n'.join(repository_lines(dict(RepositoryLinesTests.STATUS, freshness=status['freshness']), 120))
        self.assertIn('Source   /home/engineer/repo', plain)
        # Item 15: the intent has the length the state row gives it (eight, or the read model's unique prefix).
        self.assertIn('Intent   aaaaaaaa\n', text + '\n')
        longer = '\n'.join(repository_lines(status, 120, prefixes={'a' * 64: 'a' * 10}))
        self.assertIn('Intent   ' + 'a' * 10, longer)

    # Item 9 (frames 74 to 82): the Operation row says which operation the strip shows.
    def test_the_operation_row_says_which_operation_the_strip_shows_and_which_is_newest(self):
        from intune_iac.workbench_screens import state_lines
        states = {'operation': {'operation_id': 'e112edba' + 'a' * 24, 'status': 'prepared', 'journal_status': 'prepared',
                                'approval_window': 'closed', 'recorded_at': '2026-10-15T16:17:03Z'}}
        shown = {'operation_id': '9aac2657' + 'b' * 24, 'state': 'expired'}
        text = _flat(state_lines(states, 160, strip_operation=shown))
        self.assertIn('e112edba prepared; approval window closed; store last registered 2026-10-15 16:17:03 UTC. '
                      'The strip shows operation 9aac2657 (expired), not the newest.', text)
        self.assertNotIn('The strip shows', _flat(state_lines(states, 160)))

    def test_the_strip_operation_is_named_only_when_it_is_not_the_newest(self):
        from intune_iac.workbench_screens import strip_operation_shown
        newest = 'e112edba' + 'a' * 24
        facts = {'operation': 'expired', 'operation_id': '9aac2657' + 'b' * 24,
                 'states': {'operation': {'operation_id': newest, 'status': 'prepared'}}}
        self.assertEqual(strip_operation_shown(facts), {'operation_id': '9aac2657' + 'b' * 24, 'state': 'expired'})
        self.assertIsNone(strip_operation_shown(dict(facts, operation_id=newest)))
        self.assertIsNone(strip_operation_shown({'states': facts['states']}))

    # Item 10 (frames 80, 81): a blocked capability value gives its recovery; the header is not restated.
    def test_a_blocked_capability_value_gives_its_recovery_and_the_refusal_does_not_restate_its_header(self):
        from intune_iac.workbench_screens import actions_lines, refusal_lines
        message = ('Setting device_vendor_msft_policy_config_privacy_letappsaccesslocation: value '
                   'device_vendor_msft_policy_config_privacy_letappsaccesslocation_1 is not a supported value for this '
                   'setting in the offline capability map. The reference component cannot propose it.')
        action = {'label': 'Prepare a proposal from the recorded intent', 'available': False, 'summary': 's',
                  'blocked': {'code': 'workbench_desired_capability', 'message': message}}
        text = _flat(actions_lines([action], 0, 140))
        self.assertIn("Change that setting in the repository's stack input to a supported value. Once the repository reads "
                      'as changed, this list offers Refresh the repository intent; after it, this entry, Prepare a proposal '
                      'from the recorded intent, can be staged.', text)
        self.assertIn('(workbench_desired_capability)', text)
        refused = _flat(refusal_lines({'status': 'error', 'error': {'code': 'workbench_desired_capability',
                                                                    'message': message}}, 140))
        self.assertNotIn('In general', refused)
        self.assertNotIn('outside the supported capability map', refused)
        self.assertIn('Next: Change that setting', refused)

    def test_a_specific_message_keeps_the_general_meaning_when_it_adds_something(self):
        from intune_iac.workbench_screens import refusal_lines
        specific = 'The operation /w/op belongs to tenant 3333, not this store.'
        text = _flat(refusal_lines({'status': 'error', 'error': {'code': 'workbench_deployment_identity',
                                                                 'message': specific}}, 140))
        self.assertIn('In general:', text)

    # Item 11 (frame 69): a refused restore says it is a restore.
    def test_a_refused_restore_of_an_altered_original_has_restore_wording(self):
        from intune_iac.workbench_screens import refusal_lines
        value = {'status': 'error', 'error': {'code': 'maintenance_source_changed', 'message': 'Refused.',
                                              'effects': {'files_written': [], 'operation_created': False}}}
        text = _flat(refusal_lines(value, 140, operation='4d972e93', verb='restore-propose'))
        self.assertIn('[REFUSED] A file the original operation bound has changed (maintenance_source_changed)', text)
        self.assertIn('Cause: A file the original operation 4d972e93 bound changed after it was prepared', text)
        self.assertIn('a restore cannot be derived from it', text)
        self.assertNotIn('review no longer describes what would run', text)
        self.assertIn("Next: Prepare a proposal from the recorded intent (a: actions); that proposes the recorded intent's "
                      "value, not the original's, and uses nothing from the original.", text)
        # The same code for an execute keeps the execute wording.
        other = _flat(refusal_lines(value, 140, verb='execute'))
        self.assertIn('review no longer describes what would run', other)

    # Item 12 (frames 38, 57): no deployment record promised to a reconcile.
    def test_the_next_of_a_reconciled_operation_does_not_promise_a_deployment_record(self):
        from intune_iac.workbench_screens import lifecycle_next
        reconciled = {'operation_id': 'a' * 32, 'journal_status': 'reconciled', 'previous_status': 'outcome_unknown'}
        self.assertEqual(lifecycle_next(5, reconciled, 0), 'v shows every delivery stage')
        self.assertEqual(lifecycle_next(5, {'result': reconciled}, 0), 'v shows every delivery stage')
        verified = {'operation_id': 'a' * 32, 'status': 'succeeded_verified'}
        self.assertEqual(lifecycle_next(5, verified, 0), 'v shows every delivery stage, including the deployment record')

    # Item 13 (frame 35): the count says where the other finding is.
    def test_the_count_names_the_section_that_lists_the_other_findings(self):
        from intune_iac.workbench_screens import hazard_rows
        from plugin_tests.test_workbench_hazard import STALE, UNKNOWN
        for width in (40, 60, 80, 118, 140):
            rows = hazard_rows({}, [UNKNOWN, STALE], width, here=True)
            self.assertIn('+1 more finding (2 Inspector)', ' '.join(rows), (width, rows))  # run 12 L-more
            self.assertNotIn('more below', ' '.join(rows))
            for row in rows:
                self.assertLessEqual(cell_width(row), width, row)

    # Item 15: one band form for one fact; a date with its time; the attention item names the operation as the band does.
    def test_one_fact_has_one_band_form_on_every_surface(self):
        from intune_iac.workbench_screens import hazard_rows
        from plugin_tests.test_workbench_hazard import STALE, UNKNOWN
        for width in (100, 110, 118, 120, 140):
            inspector = hazard_rows({}, [UNKNOWN, STALE], width, here=True)[0]
            elsewhere = hazard_rows({}, [UNKNOWN, STALE], width)[0]
            self.assertEqual(inspector.split('  +')[0], elsewhere.split('  +')[0], width)

    def test_a_date_stays_with_its_time(self):
        from intune_iac.workbench_screens import word_wrap
        text = 'last recorded 2026-10-15 16:15:39 UTC and then some more words to push the wrap around the stamp'
        for width in range(30, 100):
            rows = word_wrap(text, width)
            for row in rows:
                self.assertNotRegex(row.rstrip(), r'\d{4}-\d\d-\d\d$', (width, rows))
                self.assertNotRegex(row.lstrip(), r'^\d\d:\d\d:\d\d', (width, rows))

    def test_the_attention_item_names_the_operation_by_the_id_the_band_uses(self):
        from intune_iac.workbench_screens import _attention_lines
        operation = 'f58aa88318ad4b5fb57fcb9c7b08bbd2'
        signal = {'area': 'operations', 'code': 'operation_outcome_unknown', 'next_step': 'Reconcile it.',
                  'observed': 'Operation %s started dispatch, but the result was never registered.' % operation,
                  'evidence': {'operation_id': operation}}
        value = {'attention': {'signals': [signal], 'checked': {}}, 'identity_prefixes': {operation: 'f58aa883'}}
        text = _flat(_attention_lines(value, 160))
        self.assertIn('Operation f58aa883 started dispatch', text)
        self.assertNotIn(operation, text)
