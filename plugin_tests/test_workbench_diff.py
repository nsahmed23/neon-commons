"""Field-level differences with hand-authored expected values.

The differences follow the maintenance plan's own equality: assignments,
technologies and role scope tags are bags; every other field, including the
order of setting records, is exact.
"""
import copy
import unittest

from intune_iac.workbench_diff import field_changes

CHOICE = '#microsoft.graph.deviceManagementConfigurationChoiceSettingInstance'
CHOICE_VALUE = '#microsoft.graph.deviceManagementConfigurationChoiceSettingValue'
LOCATION = 'device_vendor_msft_policy_config_privacy_letappsaccesslocation'
CAMERA = 'device_vendor_msft_policy_config_privacy_letappsaccesscamera'
GROUP_A = '44444444-4444-4444-8444-444444444444'
GROUP_B = '55555555-5555-4555-8555-555555555555'
GROUP_X = '66666666-6666-4666-8666-666666666666'
FILTER = '77777777-7777-4777-8777-777777777777'


def setting(record_id, definition, value):
    return {'id': record_id, 'settingInstance': {'@odata.type': CHOICE, 'settingDefinitionId': definition,
            'choiceSettingValue': {'@odata.type': CHOICE_VALUE, 'value': value, 'children': []}}}


BODY = {
    'name': 'Windows Privacy Pilot', 'description': 'Synthetic reference; not production advice.',
    'platforms': 'windows10', 'technologies': ['mdm'], 'role_scope_tag_ids': ['0'],
    'settings': {'settings': [setting('0', LOCATION, LOCATION + '_2')]},
    'assignments': [
        {'type': 'groupAssignmentTarget', 'group_id': GROUP_A, 'filter_type': 'include', 'filter_id': FILTER},
        {'type': 'groupAssignmentTarget', 'group_id': GROUP_B, 'filter_type': 'none'},
        {'type': 'exclusionGroupAssignmentTarget', 'group_id': GROUP_X, 'filter_type': 'none'}],
}


class FieldChangesTests(unittest.TestCase):
    def body(self):
        return copy.deepcopy(BODY)

    def test_identical_bodies_are_an_explicit_no_change(self):
        result = field_changes(self.body(), self.body())
        self.assertEqual(result['status'], 'no_change')
        self.assertEqual(result['changes'], [])
        self.assertFalse(result['execution_authorized'])

    def test_scalar_edit_shows_exact_before_and_after(self):
        after = self.body(); after['description'] = 'Edited in the repository.'
        result = field_changes(self.body(), after)
        self.assertEqual(result['status'], 'changed')
        self.assertEqual(result['changes'], [{'field': 'description', 'kind': 'changed', 'path': '/description',
            'before': 'Synthetic reference; not production advice.', 'after': 'Edited in the repository.'}])

    def test_null_empty_and_text_descriptions_are_distinct(self):
        for before, after in ((None, ''), ('', None), (None, 'text')):
            with self.subTest(before=before, after=after):
                left = self.body(); left['description'] = before
                right = self.body(); right['description'] = after
                self.assertEqual(field_changes(left, right)['changes'],
                                 [{'field': 'description', 'kind': 'changed', 'path': '/description', 'before': before, 'after': after}])

    def test_assignment_order_alone_is_no_change(self):
        after = self.body(); after['assignments'].reverse(); after['role_scope_tag_ids'] = ['0']
        self.assertEqual(field_changes(self.body(), after)['status'], 'no_change')

    def test_assignment_targets_added_and_removed_are_listed(self):
        after = self.body()
        removed = after['assignments'].pop(1)
        added = {'type': 'exclusionGroupAssignmentTarget', 'group_id': GROUP_B, 'filter_type': 'none'}
        after['assignments'].append(added)
        result = field_changes(self.body(), after)
        self.assertEqual(result['changes'], [
            {'field': 'assignments', 'kind': 'removed', 'path': '/assignments', 'value': removed},
            {'field': 'assignments', 'kind': 'added', 'path': '/assignments', 'value': added}])

    def test_setting_value_change_names_record_definition_and_leaf(self):
        after = self.body()
        after['settings']['settings'][0]['settingInstance']['choiceSettingValue']['value'] = LOCATION + '_1'
        result = field_changes(self.body(), after)
        self.assertEqual(result['changes'], [{'field': 'settings', 'kind': 'changed', 'path': '/settings/settings',
            'setting_id': '0', 'setting_definition_id': LOCATION,
            'differences': [{'path': '/settingInstance/choiceSettingValue/value',
                             'before': LOCATION + '_2', 'after': LOCATION + '_1'}]}])

    def test_setting_records_added_removed_and_reordered(self):
        two = self.body(); two['settings']['settings'].append(setting('1', CAMERA, CAMERA + '_0'))
        added = field_changes(self.body(), two)['changes']
        self.assertEqual(added, [{'field': 'settings', 'kind': 'added', 'path': '/settings/settings',
                                  'setting_id': '1', 'setting_definition_id': CAMERA, 'value': setting('1', CAMERA, CAMERA + '_0')}])
        removed = field_changes(two, self.body())['changes']
        self.assertEqual([(c['kind'], c['setting_id']) for c in removed], [('removed', '1')])
        swapped = copy.deepcopy(two); swapped['settings']['settings'].reverse()
        result = field_changes(two, swapped)
        # The plan compares settings exactly, so order alone is still a change; it is named, not hidden.
        self.assertEqual(result['status'], 'changed')
        self.assertEqual(result['changes'], [{'field': 'settings', 'kind': 'reordered', 'path': '/settings/settings',
                                              'before_order': ['0', '1'], 'after_order': ['1', '0']}])

    def test_unsupported_shapes_are_unknown_never_an_invented_difference(self):
        duplicate = self.body(); duplicate['settings']['settings'].append(setting('0', CAMERA, CAMERA + '_0'))
        missing = self.body(); del missing['platforms']
        for label, before, after in (('duplicate setting id', self.body(), duplicate), ('missing field', missing, self.body()),
                                     ('not an object', self.body(), ['not', 'a', 'policy'])):
            with self.subTest(label=label):
                result = field_changes(before, after)
                self.assertEqual(result['status'], 'unknown')
                self.assertEqual(result['changes'], [])
                self.assertTrue(result['blockers'])

    def test_inputs_are_not_mutated(self):
        before, after = self.body(), self.body(); after['assignments'].reverse()
        snapshot = (copy.deepcopy(before), copy.deepcopy(after))
        field_changes(before, after)
        self.assertEqual((before, after), snapshot)


if __name__ == '__main__':
    unittest.main()
