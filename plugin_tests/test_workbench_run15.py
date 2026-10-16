"""PKG-PRES-RUN15 (adversarial review of aa391f7, journeys 28 run 15 and 29 run 10): what the screens say.

Each class names its item of the brief. Temporary directories only.
"""
import unittest

SELECTED = '11111111-1111-4111-8111-111111111111'
OTHER = '22222222-2222-4222-8222-222222222222'


def flat(rows):
    return ' '.join(' '.join(rows).split())


class QueueRoutesActOnTheFindingsPolicyTests(unittest.TestCase):
    """Item 1 (review 20): queue-review commands act on the selected policy, so a finding of another policy
    puts `select <object_id>` first, and a finding of the selected policy prints no select."""

    def finding(self, object_id):
        return {'finding': 'reporting_incomplete', 'object_id': object_id, 'priority': 'review', 'priority_rationale': 'x',
                'review_record': {'status': 'not_recorded'}}

    def queue(self, object_id, selected):
        from intune_iac.workbench_screens import queue_lines
        return queue_lines({'findings': [self.finding(object_id)], 'scope': {}}, 118, selected=selected)

    def test_a_finding_of_another_policy_selects_it_before_the_review_commands(self):
        rows = [row.strip() for row in self.queue(OTHER, SELECTED)]
        self.assertIn(':select ' + OTHER, rows)
        self.assertLess(rows.index(':select ' + OTHER), rows.index(':queue-review-template reporting_incomplete NEW_JSON'))

    def test_a_finding_of_the_selected_policy_prints_no_select(self):
        rows = [row.strip() for row in self.queue(SELECTED, SELECTED)]
        self.assertNotIn(':select ' + SELECTED, rows)
        self.assertIn(':queue-review-template reporting_incomplete NEW_JSON', rows)

    def test_with_no_selection_the_finding_is_selected_first(self):
        self.assertIn(':select ' + OTHER, [row.strip() for row in self.queue(OTHER, None)])

    RECORDED = {'artifact_id': '53e45c2369a0' + '0' * 52, 'kind': 'queue_review', 'created': True,
                'recorded_at': '2026-10-16T01:17:47Z',
                'data': {'finding': 'reporting_incomplete', 'object_id': OTHER, 'version': 2}}

    def test_the_recorded_review_next_selects_the_findings_policy_first(self):
        from intune_iac.workbench_screens import recorded_lines
        rows = [row.strip() for row in recorded_lines(self.RECORDED, 118, selected=SELECTED)]
        self.assertLess(rows.index('select ' + OTHER), rows.index('queue-review reporting_incomplete'))

    def test_the_recorded_review_next_for_the_selected_policy_has_no_select(self):
        from intune_iac.workbench_screens import recorded_lines
        recorded = dict(self.RECORDED, data=dict(self.RECORDED['data'], object_id=SELECTED))
        rows = [row.strip() for row in recorded_lines(recorded, 118, selected=SELECTED)]
        self.assertNotIn('select ' + SELECTED, rows)
        self.assertIn('queue-review reporting_incomplete', rows)

    def test_the_workspace_passes_the_selected_policy(self):
        from plugin_tests import test_workbench_states as states_tests
        workspace = states_tests.StateSurfaceTests.workspace(None, 6, {'findings': [self.finding(OTHER)]})
        workspace.selected = SELECTED
        self.assertIn(':select ' + OTHER, [row.strip() for row in workspace._surface_summary(118)])


class ChangedBoundFileWordingTests(unittest.TestCase):
    """Item 2 (review 19): maintenance_source_changed is raised for the desired file and for the context file alike, and
    the refusal does not carry which one, so the cause must not name the unchanged context file."""
    WORDS = 'A file it bound (its desired file or its context file) changed after %s, so its review no longer describes what would run.'

    def refusal(self, **kw):
        from intune_iac.workbench_screens import refusal_lines
        value = {'status': 'error', 'error': {'code': 'maintenance_source_changed', 'message': 'A bound file changed.'}}
        return ' '.join(' '.join(refusal_lines(value, 118, **kw)).split())

    def test_the_cause_names_both_files_by_kind_and_no_path(self):
        text = self.refusal(operation='650a1a61', verb='execute', context_file='/w/my ctx.json')
        self.assertIn('Cause: ' + self.WORDS % 'operation 650a1a61 was prepared', text)
        self.assertNotIn('my ctx.json', text)

    def test_with_the_operation_unknown_the_cause_says_the_same_of_it(self):
        text = self.refusal(verb='execute')
        self.assertIn('Cause: ' + self.WORDS % 'it was prepared', text)

    def test_the_general_meaning_names_both_files_too(self):
        from intune_iac.workbench_screens import REFUSALS
        self.assertIn('(its desired file or its context file)', REFUSALS['maintenance_source_changed'][0])


class AgeDefinitionStatesCauseOnlyTests(unittest.TestCase):
    """Item 3 (review 18): a clock hold and a stamp ahead are not cured by collecting again (the band, Diagnostics and
    the actions list all say so), so their definition rows state the cause and point at the Inspector."""
    KEYS = ('age unknown', 'age unknown (stamped ahead)')

    def test_the_rows_do_not_send_the_engineer_to_collect(self):
        from intune_iac.workbench_screens import STRIP_DEFINITIONS
        for key in self.KEYS:
            row = STRIP_DEFINITIONS[key]
            self.assertNotIn('collect', row, row)
            self.assertNotIn('(a)', row, row)
            self.assertIn('2 Inspector says why', row)
            self.assertLessEqual(len(row), 80, row)

    def test_the_rows_a_narrow_strip_prints_do_not_say_collect(self):
        from intune_iac.workbench_screens import strip_choice, strip_key_rows
        for observation in self.KEYS:
            facts = {'observation': observation, 'name': 'A policy', 'repository': 'not checked'}
            definitions = strip_choice('t' * 8, 'p' * 8, facts, 80, None)[1]
            self.assertTrue(definitions, observation)
            rows = strip_key_rows(definitions, 80)
            self.assertTrue(any('age?' in row for row in rows), rows)
            self.assertNotIn('collect', ' '.join(rows))

    def test_the_collect_cured_stale_row_still_says_collect(self):
        from intune_iac.workbench_screens import STRIP_DEFINITIONS
        self.assertIn('collect again (a)', STRIP_DEFINITIONS['stale (later collection incomplete)'])
