"""Delayed public reads never become rollback/replay authority.

Expected estates come from the fixture's independently authored truth; durable
service JSON and SQLite are inspected directly, not through semantic comparators.
"""
import copy
import sqlite3
import unittest
from unittest.mock import patch

from intune_iac import maintenance
from intune_iac.io import AppError, load_json, write_json
from intune_iac.modeled_service import BASE, ModeledService
from plugin_tests import test_maintenance as maintenance_cases


class VisibilityRecoveryTests(unittest.TestCase):
    setUp = maintenance_cases.MaintenanceTests.setUp
    propose = maintenance_cases.MaintenanceTests.propose
    patches = maintenance_cases.MaintenanceTests.patches
    execute = maintenance_cases.MaintenanceTests.execute

    def raw(self):
        return load_json(self.root / 'service/service.json')

    def mutate(self, **kw):
        return self.service.request('PATCH', BASE + '/' + self.ids[0],
            tenant_id=self.tenant, body=self.desired, if_match='1', **kw)

    def test_commit_visibility_and_observation_are_distinct_across_reopen(self):
        self.mutate(visibility_delay_reads=4)
        raw = self.raw()
        self.assertEqual(raw['current']['objects'][self.ids[0]], self.desired)
        self.assertEqual(raw['revision'], 2)
        self.assertEqual(raw['visibility']['estate'], self.before)
        self.assertEqual(raw['visibility']['revision'], 1)
        self.assertEqual(raw['visibility']['remaining_gets'], 4)
        resumed = ModeledService(self.root / 'service')
        observation = resumed.readback_observation(tenant_id=self.tenant)
        self.assertEqual(observation['estate'], self.before)
        self.assertEqual(observation['visibility'], {
            'committed_revision': 2, 'visible_revision': 1, 'pending': True, 'model_only': True})
        self.assertEqual(self.store.inspect(self.ids[0])['body'], self.before['objects'][self.ids[0]])
        self.assertEqual(self.raw()['visibility']['remaining_gets'], 2)
        self.assertEqual(len(self.patches()), 1)

    def test_denied_wrong_tenant_and_throttled_reads_do_not_advance_visibility(self):
        self.mutate(visibility_delay_reads=2)
        for tenant, fault, code in [(self.tenant, 'deny', 403), (self.tenant, 'throttle', 429),
                                   (self.ids[0], None, 403)]:
            result = self.service.request('GET', BASE, tenant_id=tenant, fault=fault)
            self.assertEqual(result['status'], code)
            self.assertEqual(self.raw()['visibility']['remaining_gets'], 2)

    def test_denied_or_stale_mutation_does_not_create_pending_visibility(self):
        for fault in ['deny', 'throttle']:
            result = self.mutate(fault=fault, visibility_delay_reads=16)
            self.assertIn(result['status'], [403, 429])
            self.assertNotIn('visibility', self.raw())
            self.assertEqual(self.raw()['current'], self.before)
        result = self.service.request('PATCH', BASE + '/' + self.ids[0], tenant_id=self.tenant,
            body=self.desired, if_match='0', visibility_delay_reads=16)
        self.assertEqual(result['status'], 412)
        self.assertNotIn('visibility', self.raw())

    def test_delayed_partial_commit_eventually_reports_divergence_without_rollback(self):
        self.desired['assignments'] = self.desired['assignments'][:1]
        write_json(self.desired_path, self.desired)
        proposal = self.propose()
        result = self.execute(proposal, fault='after-policy', visibility_delay_reads=2)
        self.assertEqual(result['status'], 'outcome_unknown')
        self.assertEqual(self.raw()['current']['objects'][self.ids[0]]['description'], self.desired['description'])
        self.assertEqual(self.raw()['current']['objects'][self.ids[0]]['assignments'],
                         self.before['objects'][self.ids[0]]['assignments'])
        pending = maintenance.reconcile(self.operation)
        self.assertTrue(pending['visibility']['pending'])
        self.assertEqual(load_json(self.operation / 'journal.json')['status'], 'outcome_unknown')
        visible = maintenance.reconcile(self.operation)
        self.assertFalse(visible['visibility']['pending'])
        self.assertEqual(visible['classification'], 'diverged')
        self.assertEqual(visible['second_plan']['status'], 'changes_require_review')
        self.assertFalse(visible['replay_authorized'])
        self.assertEqual(len(self.patches()), 1)

    def test_mixed_readback_failure_retains_uncertainty_and_single_mutation(self):
        proposal = self.propose()
        self.execute(proposal, fault='lost-response', visibility_delay_reads=1)
        with self.assertRaises(AppError) as caught:
            maintenance.reconcile(self.operation)
        self.assertEqual(caught.exception.code, 'model_readback_incomplete')
        self.assertEqual(load_json(self.operation / 'journal.json')['status'], 'outcome_unknown')
        self.assertEqual(len(self.patches()), 1)
        self.assertEqual(maintenance.reconcile(self.operation)['classification'], 'desired_state_observed')
        self.assertEqual(len(self.patches()), 1)

    def test_mixed_page_revisions_fail_without_publishing_stale_estate(self):
        self.mutate(visibility_delay_reads=1)
        result = self.store.collect(self.service)
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['error_code'], 'workbench_revision_changed')
        self.assertEqual(self.store.inspect(self.ids[0])['body'], self.before['objects'][self.ids[0]])
        self.assertEqual(len(self.store.history(self.ids[0])), 1)
        self.assertEqual(self.store.collect(self.service)['status'], 'complete')
        self.assertEqual(self.store.inspect(self.ids[0])['body'], self.desired)

    def test_stale_collection_keeps_last_good_and_does_not_authorize_restore(self):
        proposal = self.propose()
        result = self.execute(proposal, fault='lost-response', visibility_delay_reads=6)
        self.assertEqual(result['status'], 'outcome_unknown')
        collected = self.store.collect(self.service)
        self.assertEqual(collected['status'], 'partial')
        self.assertEqual(collected['error_code'], 'workbench_revision_changed')
        with self.assertRaises(AppError) as caught:
            maintenance.propose_restore(self.operation, self.root / 'restore')
        self.assertEqual(caught.exception.code, 'maintenance_observation_incomplete')
        self.assertFalse((self.root / 'restore').exists())
        self.assertEqual(len(self.patches()), 1)
        with sqlite3.connect(self.root / 'store/observations.sqlite3') as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM observations').fetchone()[0], 3)

    def test_pending_reconcile_cannot_clear_uncertainty_or_offer_change_plan(self):
        proposal = self.propose()
        result = self.execute(proposal, fault='lost-response', visibility_delay_reads=2)
        self.assertEqual(result['error_code'], 'model_response_lost')
        pending = maintenance.reconcile(self.operation)
        self.assertEqual(pending['classification'], 'matches_precondition')
        self.assertEqual(pending['second_plan']['status'], 'visibility_pending')
        self.assertTrue(pending['visibility']['pending'])
        self.assertFalse(pending['replay_authorized'])
        self.assertEqual(load_json(self.operation / 'journal.json')['status'], 'outcome_unknown')
        with self.assertRaises(AppError) as caught:
            self.execute(proposal)
        self.assertEqual(caught.exception.code, 'maintenance_replay_forbidden')
        final = maintenance.reconcile(self.operation)
        self.assertEqual(final['classification'], 'desired_state_observed')
        self.assertEqual(final['second_plan']['status'], 'no_change')
        self.assertFalse(final['visibility']['pending'])
        self.assertEqual(final['visibility']['visible_revision'], 2)
        self.assertEqual(len(self.patches()), 1)
        self.assertEqual(len(list(self.operation.glob('reconciliation-*.json'))), 2)

    def test_successful_patch_acknowledgement_is_not_visible_convergence(self):
        proposal = self.propose()
        result = self.execute(proposal, visibility_delay_reads=2)
        self.assertEqual(result['status'], 'outcome_unknown')
        self.assertEqual(result['error_code'], 'maintenance_visibility_pending')
        first = load_json(self.operation / 'readback-0.json')
        self.assertEqual(first['classification'], 'matches_precondition')
        self.assertEqual(first['second_plan']['status'], 'visibility_pending')
        final = maintenance.reconcile(self.operation)
        self.assertEqual(final['classification'], 'desired_state_observed')
        self.assertEqual(len(self.patches()), 1)

    def test_delay_bound_and_method_reject_before_dispatch(self):
        before = (self.root / 'service/service.json').read_bytes()
        for delay in [-1, 17, True, 1.5, '1', None]:
            with self.subTest(delay=delay), self.assertRaises(AppError):
                self.mutate(visibility_delay_reads=delay)
        with self.assertRaises(AppError):
            self.service.request('GET', BASE, tenant_id=self.tenant, visibility_delay_reads=1)
        self.assertEqual((self.root / 'service/service.json').read_bytes(), before)
        proposal = self.propose()
        with self.assertRaises(AppError) as caught:
            self.execute(proposal, visibility_delay_reads=17)
        self.assertEqual(caught.exception.code, 'maintenance_visibility_delay_invalid')
        self.assertFalse((self.operation / 'executor/consumed.json').exists())

    def test_persisted_delay_corruption_is_rejected_without_repairing_it(self):
        self.mutate(visibility_delay_reads=2)
        original = self.raw()
        for field, value in [('remaining_gets', 17), ('remaining_gets', True), ('revision', 3),
                             ('estate', {'objects': {}})]:
            altered = copy.deepcopy(original); altered['visibility'][field] = value
            write_json(self.root / 'service/service.json', altered)
            before = (self.root / 'service/service.json').read_bytes()
            with self.subTest(field=field, value=value), self.assertRaises(AppError):
                self.service.snapshot()
            self.assertEqual((self.root / 'service/service.json').read_bytes(), before)

    def test_expanded_delayed_state_limit_fails_before_durable_commit(self):
        before = (self.root / 'service/service.json').read_bytes()
        with patch('intune_iac.modeled_service.MAX_STATE_BYTES', len(before) + 1):
            with self.assertRaises(AppError) as caught:
                self.mutate(visibility_delay_reads=2)
        self.assertEqual(caught.exception.code, 'model_state_limit')
        self.assertEqual((self.root / 'service/service.json').read_bytes(), before)

    def test_default_operation_retains_legacy_state_shape(self):
        proposal = self.propose()
        result = self.execute(proposal)
        self.assertEqual(result['status'], 'succeeded_verified')
        self.assertNotIn('visibility', self.raw())
        self.assertEqual(self.service.readback(tenant_id=self.tenant), self.raw()['current'])


if __name__ == '__main__':
    unittest.main()
