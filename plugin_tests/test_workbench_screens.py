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
        self.assertEqual(wide, 'SYNTHETIC | TENANT 11111111 | POLICY Windows Privacy Pilot (22222222) | OBSERVED fresh | '
                               'REPOSITORY stale | OPERATION prepared')
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
        # Narrower, the trailing states give way before the mode, tenant or policy.
        self.assertEqual(context_strip(tenant, policy, done, 80, 'synthetic'),
                         'SYNTHETIC | TENANT 11111111 | POLICY 22222222 | OBS fresh | REPO stale')

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
        self.assertIn('  3 targets; group names were not captured', joined)
        self.assertIn('include  44444444-4444-4444-8444-444444444444', joined)
        self.assertIn('filter include 77777777-7777-4777-8777-777777777777', joined)
        self.assertIn('exclude  66666666-6666-4666-8666-666666666666', joined)
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
        self.assertIn('  ├── assignment   44444444-4444-4444-8444-444444444444  filter include 77777777-7777-4777-8777-777777777777', lines)
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
        self.assertIn('  |-- assignment   44444444-4444-4444-8444-444444444444  filter include 77777777-7777-4777-8777-777777777777', lines)
        self.assertIn('  |-- exclusion    66666666-6666-4666-8666-666666666666', lines)
        self.assertIn('  |-- scope tag    "0"', lines)
        self.assertIn('generated    /work/generated/' + POLICY_ID + '  [historical_local_adoption]', joined)
        self.assertIn('repository   /work/repository  orgs/reference/dev / intune-reference  [local_literal_repository_read]', joined)
        self.assertIn('writer       unknown: ownership_index_missing', joined)
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
        self.assertIn('2026-10-14T13:00:00Z', joined); self.assertIn('2026-10-14T12:00:00Z', joined)
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
        matrix = [line for line in lines if line.startswith('    [')]
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
        joined = '\n'.join(queue_lines(value, 100))
        self.assertIn('[MAINTENANCE QUEUE]', joined)
        self.assertIn('review  reporting_incomplete  ' + POLICY_ID, joined)
        self.assertIn('Why: Missing or stale reporting', joined)
        self.assertIn('State review_required | owner unknown | freshness fresh | automatic remediation no', joined)


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
        self.assertIn('Operation b6b3679d5d95457ea8645919a1059863 | policy ' + POLICY_ID + ' | journal succeeded_verified', joined)
        expected = ['  [x] 1 Proposal        recorded 2026-10-14T12:24:54Z | repository intent bcffdf6f0000 (current)',
                    '  [x] 2 Review          1 field change: description | plan sha256 abababababab',
                    '  [x] 3 Approval        exact review digest d1072f310000 supplied at dispatch | window 2026-10-14T12:24:57Z to 2026-10-14T12:29:57Z',
                    '  [x] 4 Execution       engine succeeded_verified | service 200 | recorded 2026-10-14T12:24:58Z',
                    '  [x] 5 Readback        desired_state_observed | second plan no_change | visibility settled | 0 mismatches',
                    '  [-] 6 Reconciliation  not needed',
                    '  [x] 7 Deployment      recorded 2026-10-14T12:25:00Z | intent bcffdf6f0000 | verified_local_modeled_deployment | baseline admissible',
                    '  [x] 8 Observed after  matches desired at service revision 2 (1 before the change) | observed 2026-10-14T12:25:00.854978Z']
        rows = [line for line in lines if line.startswith('  [')]
        self.assertEqual(rows, expected)
        self.assertIn('Next: Nothing pending: the change is recorded and observed as desired.', joined)
        self.assertIn('[x] done  [ ] waiting or not yet  [-] not needed  [?] unknown or required  [!] stopped: failure, expiry or refusal', joined)

    def test_waiting_required_and_refused_stages_are_marked_in_words(self):
        from intune_iac.workbench_screens import delivery_lines
        value = delivery_value(approval={'status': 'waiting'}, execution={'status': 'not_started'}, readback={'status': 'not_started'},
                               deployment_record={'status': 'not_yet'}, observed_after={'status': 'not_yet'})
        joined = '\n'.join(delivery_lines(value, 120))
        self.assertIn('  [ ] 3 Approval        waiting for the exact review digest until 2026-10-14T12:29:57Z', joined)
        self.assertIn('  [ ] 4 Execution       not started', joined)
        value = delivery_value(approval={'status': 'expired'})
        self.assertIn('  [!] 3 Approval        expired: the approval window closed at 2026-10-14T12:29:57Z', '\n'.join(delivery_lines(value, 120)))
        value = delivery_value(execution={'status': 'unknown', 'error_code': 'model_response_lost', 'service_status': None},
                               reconciliation={'status': 'required'},
                               deployment_record={'status': 'not_available', 'reason': 'no_verified_readback'})
        joined = '\n'.join(delivery_lines(value, 120))
        self.assertIn('  [?] 4 Execution       outcome unknown: model_response_lost', joined)
        self.assertIn('  [?] 6 Reconciliation  required: the outcome is unknown', joined)
        self.assertIn('  [!] 7 Deployment      not available: no verified readback', joined)

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
        self.assertIn('  plan 42  claims success | revision bbbbbbbbbbbb | observed 2026-10-14T12:00:00Z | tied to this operation', joined)

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
        self.assertIn('  Evidence  operation_id b6b3679d, operation_root /work/op, error_code model_response_lost', joined)
        self.assertNotIn("{'x': 1}", joined)
        self.assertIn('  Next      reconcile /work/op', joined)
        self.assertIn('  repository       no repository intent recorded', joined)
        self.assertIn('  device evidence  no device evidence imported', joined)
        for line in lines:
            self.assertLessEqual(cell_width(line), 100, line)

    def test_nothing_to_report_is_said_plainly(self):
        from intune_iac.workbench_screens import diagnostics_lines
        value = dict(DIAGNOSTICS, signals=[], checked={'collection': 'clear'})
        self.assertIn('nothing needs attention', '\n'.join(diagnostics_lines(value, 120)))

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
        self.assertEqual(lines[0], '[RECORDED] CI workflow run aaaaaaaaaaaa | new record | 2026-10-14T14:31:06Z')
        self.assertEqual(lines[1], 'apply 1002: success | revision bbbbbbbbbbbb | observed 2026-10-14T14:21:05Z | '
                                   'linked to operation cccccccccccc')
        self.assertIn('never marks a stage done', ' '.join(lines[2:]))
        self.assertIn(':workflows lists every imported run', ' '.join(lines[2:]))

    def test_a_repeated_record_says_nothing_changed(self):
        from intune_iac.workbench_screens import recorded_lines
        value = dict(self.RUN, created=False, kind='device_evidence', data={})
        self.assertEqual(recorded_lines(value, 120),
                         ['[RECORDED] device evidence aaaaaaaaaaaa | already recorded; nothing changed | 2026-10-14T14:31:06Z'])


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
        self.assertIn('0   prepared          2026-10-14T16:35:31Z  approval will need digest aaaaaaaaaaaa', joined)
        self.assertIn('approved with digest aaaaaaaaaaaa', joined)
        self.assertIn('1   dispatch started  time not recorded', joined)
        self.assertIn('engine reported succeeded_verified (synthetic_local_process_only)', joined)
        self.assertIn('3   outcome unknown   2026-10-14T16:35:32Z  model_response_lost', joined)
        self.assertNotIn('could not be paired', joined)
        for width in (120, 60):
            for line in history_event_lines(self.HISTORY, width):
                self.assertLessEqual(cell_width(line), width, line)

    def test_a_store_time_is_shown_to_the_second_and_the_columns_stay_aligned(self):
        from intune_iac.workbench_screens import history_event_lines
        history = copy.deepcopy(self.HISTORY)
        history['events'][0]['store_recorded_at'] = '2026-10-14T17:14:37.396288Z'
        lines = history_event_lines(history, 120)
        self.assertIn('0   prepared          2026-10-14T17:14:37Z  approval will need digest', lines[1])
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
        self.assertEqual(lines[0], '[REFUSED] workbench_repository_intent_missing')
        self.assertIn('Import the repository for this object before using its intent.', joined)
        self.assertIn('No repository intent was recorded for this policy', joined)
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
        self.assertEqual(lines, ['[REFUSED] something_new', 'Engine words.'])

    def test_a_stale_or_incomplete_observation_refusal_says_which_and_what_to_do(self):
        from intune_iac.workbench_screens import refusal_lines
        message = 'Maintenance evidence is incomplete, changed, stale, or outside the local model profile.'
        for code, words in (('maintenance_observation_stale', 'not fresh, or the service changed'),
                            ('maintenance_observation_incomplete', 'incomplete, or the last collection did not finish')):
            joined = '\n'.join(refusal_lines({'status': 'error', 'error': {'code': code, 'message': message}}, 200))
            self.assertIn(words, joined)
            self.assertIn('Next: Collect again (:collect)', joined)

    def test_a_meaning_the_engine_message_already_states_is_not_repeated(self):
        from intune_iac.workbench_screens import refusal_lines
        message = ('The repository changed since this intent was recorded, or its component no longer consumes exactly '
                   'this policy. Refresh the intent, review the difference and prepare a new proposal.')
        lines = refusal_lines({'status': 'error', 'error': {'code': 'workbench_repository_stale', 'message': message}}, 100)
        joined = '\n'.join(lines)
        self.assertNotIn('What it means', joined)
        self.assertIn('Next: Press 9 to see which', joined)
        # A short technical message keeps the plain meaning.
        terse = refusal_lines({'status': 'error', 'error': {'code': 'workbench_repository_stale', 'message': 'stale'}}, 100)
        self.assertIn('What it means: The repository changed since its recorded intent', '\n'.join(terse))


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
            self.assertIn('[REFUSED] selection_required', text)
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
        matrix = ''.join(line[5:-1] for line in lines if line.startswith('    ['))
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
        self.assertIn('Owner role human review assignee: none recorded | writer unknown: ownership_index_missing | source owner claim null', joined)
        self.assertIn('  Review not recorded | review due none | exception expiry none', joined)
        self.assertIn('Compatibility synthetic_windows_settings_catalog | native provider not qualified', joined)
        self.assertIn('Related proposals (1)\n    b668ad2fa6c5 succeeded_verified (2 journal records; latest T2)', joined)


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
