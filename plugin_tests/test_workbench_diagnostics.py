"""Diagnostics: what needs attention for one policy, as observed facts with their evidence and next step.

The real store, maintenance engine and modeled service produce each failure;
the expected signals are written by hand. The view only reads.
"""
import hashlib
import json
from pathlib import Path
import unittest

from plugin_tests import test_workbench_repository as repository_tests

OBJECT = repository_tests.OBJECT
TENANT = repository_tests.TENANT


def tree(root):
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(Path(root).rglob('*')) if path.is_file() and not path.name.endswith(('-wal', '-shm'))}


def device_evidence(truncated):
    stamp = '2026-10-14T00:00:00Z'
    devices = ['device-%d' % index for index in range(4)]
    return {'schema_version': 'workbench-device-evidence/1', 'tenant_id': TENANT, 'object_id': OBJECT, 'evidence': {
        'schema_version': '1.0.0', 'synthetic': True, 'as_of': stamp, 'freshness_seconds': 3600,
        'cohort': {'version': 'test', 'eligible_ids': devices, 'targeted_ids': devices, 'excluded_ids': []},
        'rows': [{'id': 'row-0', 'device_id': devices[0], 'stage': 'execution', 'status': 'success', 'observed_at': stamp,
                  'source_file': 'minimized.json', 'source_pointer': '/0', 'coverage': 'complete', 'synthetic': True}],
        'capture': {'timezone': 'UTC', 'clock_skew_seconds': None, 'logging_enabled': None, 'truncated': truncated,
                    'access_errors': ['One event channel unavailable'] if truncated else []},
        'promotion_thresholds': {'min_reporting_ratio': 1, 'min_success_ratio': 1}}}


class DiagnosticsTests(unittest.TestCase):
    # No module-level name may refer to the fixture class, or unittest would collect its tests here too.
    RESOURCE_ADDRESS = repository_tests.RepositoryOwnedChangeTests.RESOURCE_ADDRESS
    setUp = repository_tests.RepositoryOwnedChangeTests.setUp
    import_intent = repository_tests.RepositoryOwnedChangeTests.import_intent
    edit_description = repository_tests.RepositoryOwnedChangeTests.edit_description

    def view(self):
        from intune_iac.workbench_diagnostics import diagnostics
        value = diagnostics(self.store, OBJECT)
        self.assertEqual(value['schema_version'], 'workbench-diagnostics/1')
        self.assertFalse(value['execution_authorized']); self.assertFalse(value['cloud_authority'])
        return value, {signal['code']: signal for signal in value['signals']}

    def test_a_healthy_policy_has_no_signals_and_says_what_was_checked(self):
        self.import_intent()
        value, signals = self.view()
        self.assertEqual(signals, {})
        self.assertEqual(value['checked'], {'collection': 'clear', 'freshness': 'clear', 'operations': 'clear',
                                            'repository': 'clear', 'device_evidence': 'not_imported'})

    def test_each_failure_is_an_observed_fact_with_evidence_and_a_next_step(self):
        from intune_iac import maintenance
        from intune_iac.workbench_health import import_device_evidence
        from intune_iac.workbench_repository import propose_from_intent, refresh_intent
        self.import_intent()
        self.edit_description('Edited in the repository.')
        refresh_intent(self.store, OBJECT, 'b' * 40)
        operation = self.root / 'operation'
        review = propose_from_intent(self.store.root, self.service.root, OBJECT, operation)
        maintenance.execute(operation, approve_digest=review['approval_digest'], fault='lost-response')
        self.edit_description('Edited again after the proposal.')
        path = self.root / 'evidence.json'; path.write_text(json.dumps(device_evidence(truncated=True)))
        import_device_evidence(self.store, path)
        self.store.collect(self.service, fault='deny')
        before = (tree(self.store.root), tree(operation), tree(self.service.root))
        value, signals = self.view()
        self.assertEqual(sorted(signals), ['collection_failed', 'device_capture_incomplete', 'operation_outcome_unknown',
                                           'repository_stale'])
        self.assertEqual(signals['operation_outcome_unknown']['evidence']['operation_id'], review['operation_id'])
        self.assertIn('reconcile ' + str(operation), signals['operation_outcome_unknown']['next_step'])
        self.assertIn('model_response_lost', signals['operation_outcome_unknown']['observed'])
        self.assertEqual(signals['repository_stale']['evidence']['changed'], [repository_tests.STACK])
        self.assertIn('repository-refresh', signals['repository_stale']['next_step'])
        self.assertIn('truncated', signals['device_capture_incomplete']['observed'])
        self.assertIn('last-good', signals['collection_failed']['next_step'])
        self.assertEqual(value['checked']['freshness'], 'explained_by_collection')
        for signal in value['signals']:
            self.assertTrue(signal['observed']); self.assertTrue(signal['next_step'])
            self.assertIn(signal['area'], value['checked'])
            self.assertEqual(value['checked'][signal['area']], 'attention')
        self.assertEqual((tree(self.store.root), tree(operation), tree(self.service.root)), before)
        # Resolving the causes clears their signals.
        maintenance.reconcile(operation)
        refresh_intent(self.store, OBJECT, 'c' * 40)
        self.store.collect(self.service)
        value, signals = self.view()
        self.assertEqual(sorted(signals), ['device_capture_incomplete'])
        self.assertEqual(value['checked']['operations'], 'clear')


if __name__ == '__main__':
    unittest.main()
