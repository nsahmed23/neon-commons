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
        self.assertIn('last-good', signals['collection_failed']['observed'])
        self.assertIn(':collect', signals['collection_failed']['next_step'])
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


class DiagnosticsEdgeTests(unittest.TestCase):
    """Cases the review of 69da14d named: crash windows, bounds, consumer drift, scope conflicts, unreadable areas."""
    RESOURCE_ADDRESS = repository_tests.RepositoryOwnedChangeTests.RESOURCE_ADDRESS
    setUp = repository_tests.RepositoryOwnedChangeTests.setUp
    import_intent = repository_tests.RepositoryOwnedChangeTests.import_intent
    edit_description = repository_tests.RepositoryOwnedChangeTests.edit_description
    view = DiagnosticsTests.view

    def propose(self, name):
        from intune_iac.workbench_repository import propose_from_intent
        return propose_from_intent(self.store.root, self.service.root, OBJECT, self.root / name)

    def test_a_dispatch_interrupted_before_registration_is_reported_from_the_journal(self):
        from unittest import mock
        from intune_iac import maintenance, protected
        from intune_iac.workbench_repository import refresh_intent
        self.import_intent()
        self.edit_description('Edited in the repository.')
        refresh_intent(self.store, OBJECT, 'b' * 40)
        review = self.propose('change one')
        # The process stops after the journal records dispatch_started and before the store registers the result.
        with mock.patch.object(protected, 'execute_native_operation', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                maintenance.execute(self.root / 'change one', approve_digest=review['approval_digest'])
        self.assertEqual(self.store.operations(object_id=OBJECT)[-1]['status'], 'prepared')
        value, signals = self.view()
        signal = signals['operation_outcome_unknown']
        self.assertEqual((signal['evidence']['status'], signal['evidence']['journal_status']), ('prepared', 'outcome_unknown'))
        self.assertIn('never registered', signal['observed'])
        self.assertIn("reconcile '%s'" % (self.root / 'change one'), signal['next_step'])
        self.assertEqual(value['checked']['operations'], 'attention')

    def test_an_incomplete_operations_read_with_findings_is_still_partly_checked(self):
        from unittest import mock
        from intune_iac import maintenance, workbench_diagnostics
        from intune_iac.workbench_repository import refresh_intent
        self.import_intent()
        self.edit_description('Edited in the repository.')
        refresh_intent(self.store, OBJECT, 'b' * 40)
        # The bounded read takes the oldest records, so the operation with the unknown outcome comes first.
        review = self.propose('first')
        maintenance.execute(self.root / 'first', approve_digest=review['approval_digest'], fault='lost-response')
        self.store.collect(self.service)  # the lost response still changed the service
        self.propose('second')
        with mock.patch.object(workbench_diagnostics, 'OPERATION_PAGE', 1), \
                mock.patch.object(workbench_diagnostics, 'MAX_OPERATION_RECORDS', 1):
            value, signals = self.view()
        self.assertIn('operation_outcome_unknown', signals)
        self.assertEqual(value['checked']['operations'], 'partly_checked')

    def test_operations_beyond_the_read_bound_are_reported_as_partly_checked(self):
        from unittest import mock
        from intune_iac import workbench_diagnostics
        self.import_intent()
        self.propose('first'); self.propose('second')
        with mock.patch.object(workbench_diagnostics, 'OPERATION_PAGE', 1), \
                mock.patch.object(workbench_diagnostics, 'MAX_OPERATION_RECORDS', 1):
            value, signals = self.view()
        self.assertEqual(value['checked']['operations'], 'partly_checked')
        self.assertTrue(any('operation records' in line.lower() for line in value['limitations']))

    def test_a_component_that_no_longer_consumes_exactly_this_policy_is_named_while_unchanged(self):
        import copy
        from uuid import UUID
        import yaml
        document = yaml.safe_load((self.repo / repository_tests.STACK).read_text())
        policies = document['components']['terraform']['intune-reference']['vars']['policies']
        policies['p_' + UUID(TENANT).hex + '_' + 'd' * 32] = copy.deepcopy(policies[repository_tests.KEY])
        (self.repo / repository_tests.STACK).write_text(yaml.safe_dump(document))
        self.import_intent()
        value, signals = self.view()
        signal = signals['repository_consumer_mismatch']
        self.assertIn('policy_keys_not_exactly_adopted', signal['evidence']['reasons'])
        self.assertIn('refuse', signal['next_step'])
        self.assertEqual(value['checked']['repository'], 'attention')

    def test_two_repository_scopes_are_reported_without_promising_that_an_import_resolves_them(self):
        import shutil
        from intune_iac import workbench_views as views
        self.import_intent()
        other = self.root / 'other-repository'; shutil.copytree(self.repo, other)
        views.import_repository(self.store, other, 'orgs/reference/dev', 'intune-reference', OBJECT,
                                '/vars/policies/' + repository_tests.KEY, 'a' * 40, 'local', self.RESOURCE_ADDRESS)
        value, signals = self.view()
        signal = signals['workbench_repository_scope_ambiguous']
        self.assertIn('does not resolve', signal['observed'])
        self.assertNotIn('repository-import', signal['next_step'])

    def test_an_unreadable_area_is_reported_and_the_other_areas_still_show(self):
        from unittest import mock
        from intune_iac.io import AppError
        self.import_intent()
        with mock.patch('intune_iac.workbench_health.device_health', side_effect=AppError('workbench_query_limit', 'Too many rows.')):
            value, signals = self.view()
        self.assertEqual((value['checked']['device_evidence'], value['checked']['repository']), ('unavailable', 'clear'))
        self.assertIn('workbench_query_limit', signals['device_evidence_unavailable']['observed'])


class FreshnessReasonTests(unittest.TestCase):
    """A stale observation says which of the store's conditions made it stale; nothing is inferred from the age alone."""
    RESOURCE_ADDRESS = repository_tests.RepositoryOwnedChangeTests.RESOURCE_ADDRESS
    setUp = repository_tests.RepositoryOwnedChangeTests.setUp
    view = DiagnosticsTests.view

    def test_an_observation_stamped_after_the_hosts_clock_says_so(self):
        import time
        self.store.collect(self.service, observed_at=time.time() + 600)
        observed = self.store.inspect(OBJECT)
        self.assertEqual((observed['freshness'], observed['freshness_reasons']), ('stale', ['stamped_after_now']))
        self.assertIn('freshness_checked_at', observed)
        _, signals = self.view()
        sentence = signals['observation_stale']['observed']
        # Diagnostics reads the policy again, so its check time is its own, later than this inspect's.
        self.assertRegex(sentence, r"stamped later than this host's clock read when it was checked \(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d UTC\)\.$")
        self.assertIn("until this host's clock passes", signals['observation_stale']['next_step'])

    def test_an_observation_older_than_the_window_says_so(self):
        import time
        from unittest import mock
        real = time.time
        # Checked three hours after the fixture's collection: the observation has aged out of the window.
        with mock.patch('time.time', lambda: real() + 3600 * 3):
            observed = self.store.inspect(OBJECT)
            _, signals = self.view()
        self.assertEqual((observed['freshness'], observed['freshness_reasons']), ('stale', ['older_than_window']))
        self.assertEqual(observed['freshness_window_seconds'], 3600)
        self.assertIn('older than the freshness window of 3600 seconds', signals['observation_stale']['observed'])

    def test_a_fresh_observation_has_no_reasons(self):
        self.assertEqual((self.store.inspect(OBJECT)['freshness'], self.store.inspect(OBJECT)['freshness_reasons']), ('fresh', []))


class CollectionAndFreshnessTests(unittest.TestCase):
    """Collection evidence comes from this policy's own attempts, as inspect reports them."""
    def collection(self, attempt, success=None, retained=False, freshness='stale'):
        from intune_iac.workbench_diagnostics import _collection
        return _collection({'last_attempt': attempt, 'last_success': success, 'retained_last_good': retained,
                            'freshness': freshness})

    def test_a_finished_collection_has_nothing_to_report(self):
        self.assertEqual(self.collection({'run_id': 3, 'status': 'complete'}), ([], False))

    def test_a_failed_collection_names_this_policys_last_good_observation(self):
        signals, failed = self.collection({'run_id': 4, 'status': 'denied', 'error_code': 'workbench_collection_denied',
                                           'completed_at': '2026-10-14T00:00:00Z'}, {'run_id': 3}, True)
        self.assertTrue(failed)
        [signal] = signals
        # The observed sentence names the last-good observation; the step does not repeat it.
        self.assertIn('run 3', signal['observed']); self.assertIn('last-good', signal['observed'])
        self.assertIn('kept', signal['observed'])
        self.assertEqual(signal['next_step'], 'Collect again (:collect) when the source is reachable.')

    def test_a_failed_first_collection_does_not_promise_a_last_good_observation(self):
        signals, failed = self.collection({'run_id': 1, 'status': 'failed'}, None, False, 'unknown')
        self.assertTrue(failed)
        self.assertNotIn('last-good', signals[0]['next_step'])
        self.assertIn('no complete observation', signals[0]['next_step'])

    def test_a_collection_without_a_recorded_end_is_not_called_failed(self):
        signals, failed = self.collection({'run_id': 5, 'status': 'collecting', 'started_at': '2026-10-14T00:00:00Z'})
        self.assertFalse(failed)
        self.assertEqual(signals[0]['code'], 'collection_not_finished')
        self.assertNotIn('ended', signals[0]['observed'])

    def test_a_policy_never_observed_completely_is_described_as_such(self):
        from intune_iac.workbench_diagnostics import _freshness
        signals, checked = _freshness({'freshness': 'unknown', 'observed_at': None}, failed=False)
        self.assertEqual(checked, 'attention')
        self.assertIn('No complete observation', signals[0]['observed'])
        self.assertNotIn('None', signals[0]['observed'])


if __name__ == '__main__':
    unittest.main()
