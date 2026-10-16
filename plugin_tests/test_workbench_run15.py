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
