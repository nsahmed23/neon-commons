"""Estate overview: how observed policies relate through groups, filters, scope tags and settings.

A synthetic three-policy estate is served by the modeled service and collected
into a store. Expectations are computed from the estate's own truth file, not
from the code under test.
"""
from collections import deque
import hashlib
from pathlib import Path
import tempfile
import unittest

from intune_iac.workbench_tui import cell_width


def tree(root):
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(Path(root).rglob('*')) if path.is_file() and not path.name.endswith(('-wal', '-shm'))}


class EstateOverviewTests(unittest.TestCase):
    def setUp(self):
        from intune_iac.modeled_service import ModeledService
        from intune_iac.synthetic import generate_estate
        from intune_iac.workbench_store import WorkbenchStore
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        estate = generate_estate(seed=510, policy_count=3)
        self.truth = estate['truth']
        self.ids = [policy['id'] for policy in self.truth['policies']]
        self.service = ModeledService.create(self.root / 'service', estate['capture'], self.ids)
        self.store = WorkbenchStore.create(self.root / 'store', self.truth['tenant_id'])
        self.store.collect(self.service)

    def view(self, **kw):
        from intune_iac.workbench_overview import estate_overview
        value = estate_overview(self.store, **kw)
        self.assertEqual(value['schema_version'], 'workbench-estate-overview/1')
        self.assertFalse(value['execution_authorized']); self.assertFalse(value['cloud_authority'])
        return value

    def expected(self, kind):
        """Which policies use each group, filter, scope tag or setting, from the truth file."""
        found = {}
        for policy in self.truth['policies']:
            if kind in ('included', 'excluded'):
                wanted = 'groupAssignmentTarget' if kind == 'included' else 'exclusionGroupAssignmentTarget'
                keys = [row['group_id'] for row in policy['assignments'] if row['type'] == wanted]
            elif kind == 'filters':
                keys = [row['filter_id'] for row in policy['assignments'] if row.get('filter_id')]
            elif kind == 'scope_tags':
                keys = policy['role_scope_tag_ids']
            else:
                keys = [row['settingInstance']['settingDefinitionId'] for row in policy['settings']['settings']]
            for key in set(keys):
                found.setdefault(key, set()).add(policy['id'])
        return found

    def test_groups_filters_tags_and_settings_are_mapped_to_the_policies_that_use_them(self):
        value = self.view()
        self.assertEqual(value['counts'], {'policies_read': 3, 'policies_total': 3, 'without_complete_observation': 0})
        groups = {row['group_id']: row for row in value['groups']}
        included, excluded = self.expected('included'), self.expected('excluded')
        self.assertEqual(set(groups), set(included) | set(excluded))
        for group_id, row in groups.items():
            self.assertEqual(set(row['included_by']), included.get(group_id, set()), group_id)
            self.assertEqual(set(row['excluded_by']), excluded.get(group_id, set()), group_id)
        self.assertEqual({row['filter_id']: set(row['used_by']) for row in value['filters']}, self.expected('filters'))
        self.assertEqual({row['tag']: set(row['used_by']) for row in value['scope_tags']}, self.expected('scope_tags'))
        settings = self.expected('settings')
        self.assertEqual({row['setting']: set(row['used_by']) for row in value['shared_settings']},
                         {key: users for key, users in settings.items() if len(users) > 1})
        self.assertEqual(value['distinct_settings'], len(settings))
        # Most-shared first, so what several policies have in common leads.
        sizes = [len(row['included_by']) + len(row['excluded_by']) for row in value['groups']]
        self.assertEqual(sizes, sorted(sizes, reverse=True))
        self.assertEqual({row['object_id'] for row in value['policies']}, set(self.ids))
        for row in value['policies']:
            self.assertIn('ownership', row); self.assertIn('freshness', row); self.assertIsInstance(row['findings'], list)

    def test_policies_beyond_the_read_bound_are_counted_as_not_established(self):
        value = self.view(limit=2)
        self.assertEqual(value['counts']['policies_read'], 2)
        self.assertEqual(value['counts']['policies_total'], 3)
        self.assertIn({'reason': 'beyond_read_bound', 'count': 1}, value['not_established'])

    def test_the_overview_reads_and_writes_nothing_else(self):
        before = tree(self.store.root)
        self.view()
        self.assertEqual(tree(self.store.root), before)

    def test_all_devices_and_all_licensed_users_are_never_counted_as_groups(self):
        import copy
        from intune_iac.modeled_service import BASE
        body = copy.deepcopy(self.service.snapshot()['current']['objects'][self.ids[0]])
        groups = [row for row in body['assignments'] if 'group_id' in row]
        body['assignments'] = groups + [{'type': 'allDevicesAssignmentTarget', 'filter_type': 'none'},
                                        {'type': 'allLicensedUsersAssignmentTarget', 'filter_type': 'none'}]
        response = self.service.request('PATCH', BASE + '/' + self.ids[0], tenant_id=self.truth['tenant_id'], body=body,
                                        if_match=str(self.service.snapshot()['revision']))
        self.assertEqual(response['status'], 200)
        self.store.collect(self.service)
        value = self.view()
        group_ids = {row['group_id'] for row in value['groups']}
        self.assertNotIn('allDevicesAssignmentTarget', group_ids)
        self.assertNotIn('allLicensedUsersAssignmentTarget', group_ids)
        self.assertEqual({row['target']: row['used_by'] for row in value['broad_targets']},
                         {'allDevicesAssignmentTarget': [self.ids[0]], 'allLicensedUsersAssignmentTarget': [self.ids[0]]})
        first = next(policy for policy in value['policies'] if policy['object_id'] == self.ids[0])
        included = sum(1 for row in groups if row['type'] == 'groupAssignmentTarget')
        self.assertEqual(first['included_groups'], included)
        self.assertEqual(first['broad_targets'], ['allDevicesAssignmentTarget', 'allLicensedUsersAssignmentTarget'])


class OverviewScreenTests(unittest.TestCase):
    VALUE = {'schema_version': 'workbench-estate-overview/1', 'counts': {'policies_read': 2, 'policies_total': 2, 'without_complete_observation': 0},
             'ownership': {'unknown': 2}, 'distinct_settings': 3, 'execution_authorized': False, 'cloud_authority': False,
             'groups': [{'group_id': 'a' * 8 + '-0000-4000-8000-' + '0' * 12, 'included_by': ['p1', 'p2'], 'excluded_by': []},
                        {'group_id': 'b' * 8 + '-0000-4000-8000-' + '0' * 12, 'included_by': [], 'excluded_by': ['p2']}],
             'filters': [{'filter_id': 'c' * 8 + '-0000-4000-8000-' + '0' * 12, 'used_by': ['p1']}],
             'scope_tags': [{'tag': '0', 'used_by': ['p1', 'p2']}],
             'shared_settings': [{'setting': 'device_vendor_msft_policy_config_privacy_letappsaccesslocation', 'used_by': ['p1', 'p2']}],
             'policies': [{'object_id': 'p1', 'name': 'First', 'included_groups': 1, 'excluded_groups': 0, 'filters': 1,
                           'settings': 2, 'scope_tags': ['0'], 'ownership': 'unknown', 'freshness': 'fresh', 'findings': []},
                          {'object_id': 'p2', 'name': 'Second', 'included_groups': 1, 'excluded_groups': 1, 'filters': 0,
                           'settings': 1, 'scope_tags': ['0'], 'ownership': 'unknown', 'freshness': 'stale',
                           'findings': ['observation_stale']}],
             'not_established': []}

    def test_broad_targets_are_named_in_words_apart_from_groups(self):
        from intune_iac.workbench_screens import overview_lines
        value = dict(self.VALUE, broad_targets=[{'target': 'allDevicesAssignmentTarget', 'used_by': ['p1']}])
        value['policies'] = [dict(self.VALUE['policies'][0], broad_targets=['allDevicesAssignmentTarget']), self.VALUE['policies'][1]]
        joined = '\n'.join(overview_lines(value, 100, rules='unicode'))
        self.assertIn('ALL-DEVICE AND ALL-USER TARGETS', joined)
        self.assertIn('all devices  targeted by 1 policy (p1)', joined)
        self.assertIn('targets all devices', joined)
        self.assertNotIn('allDevic', joined)

    def test_shared_relationships_lead_and_every_line_fits(self):
        from intune_iac.workbench_screens import overview_lines
        lines = overview_lines(self.VALUE, 100, rules='unicode', focus=1)
        joined = '\n'.join(lines)
        self.assertEqual(lines[0], '[ESTATE OVERVIEW]')
        self.assertIn('2 of 2 policies read | 0 without a complete observation | ownership: unknown 2', joined)
        self.assertIn('├── aaaaaaaa  included by 2 policies (p1, p2)', joined)
        self.assertIn('└── bbbbbbbb  excluded by 1 policy (p2)', joined)
        self.assertIn('SHARED SETTINGS', joined)
        self.assertIn('>  Second (p2)', joined)
        pinned = '\n'.join(overview_lines(self.VALUE, 100, rules='unicode', focus=1, selected='p2'))
        self.assertIn('>* Second (p2)', pinned)
        self.assertIn('1 finding: observation_stale', joined)
        self.assertIn('Nothing was left out', joined)
        for width in (100, 60):
            for line in overview_lines(self.VALUE, width, rules='unicode'):
                self.assertLessEqual(cell_width(line), width, line)

    def workspace(self):
        from intune_iac.workbench_tui import Workspace
        workspace = Workspace.__new__(Workspace)
        workspace.__dict__.update(
            tab=0, value=self.VALUE, selected=None, facts={}, highlight=0, scroll=0, mode=None, buffer='', cursor=0,
            pasting=False, input_overflow=False, notice='', last_command='estate-overview', view_command='estate-overview',
            page_command='overview', rows=[{'object_id': 'x'}], operation_rows=[], operation_highlight=0, active_operation=None,
            execution_result=None, active_service=None, active_adoption=None, active_adoption_plan=None, pending=deque(),
            size=(100, 40), submission_key='enter', entry_focus=0, overview_focus=0)
        workspace.draw = lambda: None
        workspace._terminal_size = lambda: (100, 40)
        return workspace

    def test_enter_on_a_policy_selects_it(self):
        workspace = self.workspace()
        class Reader:
            def __init__(self, keys): self.keys = list(keys)
            def read(self): return self.keys.pop(0)
        workspace.key_reader = Reader(['down', 'enter'])
        self.assertEqual(workspace.input(''), 'select p2')

    def test_the_overview_renders_on_estate_with_its_title(self):
        from intune_iac.workbench_tui import title_line
        text = '\n'.join(self.workspace()._surface_summary(100))
        self.assertIn('[ESTATE OVERVIEW]', text)
        self.assertEqual(title_line('Estate', 'estate-overview', self.VALUE), 'INTUNE WORKBENCH  /  Estate  /  Relationship overview')


if __name__ == '__main__':
    unittest.main()
