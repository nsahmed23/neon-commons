"""Sourced names and unknown identities (P-PRES-14).

A group whose name was not captured is called what it is, an unresolved group identity, with the identity beside it;
it is never given an invented name or read as all users. A name is shown only where the evidence carries one. Each
surface that names a group target follows the same rule: the Inspector, the change review, Relationships and the
estate overview (which says it once for its list). Expected words are written by hand.
"""
import unittest

GROUP_IN, GROUP_OUT = '44444444-4444-4444-8444-444444444444', '66666666-6666-4666-8666-666666666666'
POLICY = '22222222-2222-4222-8222-222222222222'
LABEL = 'Unresolved group identity'


def text(lines):
    return ' '.join(' '.join(lines).split())


class IdentityTests(unittest.TestCase):
    def inspector(self, names=None):
        from intune_iac.workbench_screens import inspector_lines
        body = {'assignments': [{'type': 'groupAssignmentTarget', 'group_id': GROUP_IN, 'filter_type': 'none'},
                                {'type': 'exclusionGroupAssignmentTarget', 'group_id': GROUP_OUT, 'filter_type': 'none'}]}
        value = {'object_id': POLICY, 'name': 'Pilot', 'body': body}
        if names is not None:
            value['target_names'] = names
        return text(inspector_lines(value, 160))

    def test_the_inspector_names_each_unresolved_group_as_such(self):
        rendered = self.inspector()
        self.assertIn('%s %s' % (LABEL, GROUP_IN), rendered)
        self.assertIn('%s %s' % (LABEL, GROUP_OUT), rendered)
        self.assertNotIn('All Users', rendered)
        self.assertNotIn('group names were not captured', rendered)  # said on each line instead

    def test_a_name_the_evidence_carries_is_shown_with_its_identity(self):
        rendered = self.inspector({GROUP_IN: 'Pilot devices'})
        self.assertIn('%s "Pilot devices"' % GROUP_IN, rendered)
        self.assertNotIn('%s %s' % (LABEL, GROUP_IN), rendered)
        self.assertIn('%s %s' % (LABEL, GROUP_OUT), rendered)

    def test_the_change_review_says_it_too(self):
        from intune_iac.workbench_screens import _target
        self.assertIn('%s %s' % (LABEL, GROUP_IN), _target({'type': 'groupAssignmentTarget', 'group_id': GROUP_IN}))

    def test_relationships_say_it_for_group_edges_only(self):
        from intune_iac.workbench_screens import _edge_target
        group = {'relation': 'assignment', 'target_id': GROUP_IN,
                 'details': {'group_id': GROUP_IN, 'type': 'groupAssignmentTarget', 'filter_type': 'none'}}
        self.assertEqual(_edge_target(group), '%s %s' % (LABEL, GROUP_IN))
        a_filter = {'relation': 'filter', 'target_id': '77777777-7777-4777-8777-777777777777', 'details': {}}
        self.assertNotIn(LABEL, _edge_target(a_filter))

    def test_the_overview_says_it_once_for_its_list(self):
        from intune_iac.workbench_screens import overview_lines
        value = {'schema_version': 'workbench-estate-overview/1', 'policies': [],
                 'groups': [{'group_id': GROUP_IN, 'included_by': [POLICY], 'excluded_by': []},
                            {'group_id': GROUP_OUT, 'included_by': [], 'excluded_by': [POLICY]}]}
        rendered = text(overview_lines(value, 160))
        self.assertEqual(rendered.count(LABEL), 1)
        self.assertIn('TARGETED GROUPS', rendered)


if __name__ == '__main__':
    unittest.main()
