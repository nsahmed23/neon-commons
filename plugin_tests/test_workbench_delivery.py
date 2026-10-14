"""Delivery: where one intentional change stands, from its durable records.

The real maintenance engine and the modeled service run each case; the
expected stages are written by hand. The view is read-only: it never
dispatches, approves, reconciles or writes.
"""
import hashlib
import json
from pathlib import Path
import unittest

from plugin_tests import test_workbench_repository as repository_tests

OBJECT = repository_tests.OBJECT

STAGES = ['proposal', 'review', 'approval', 'execution', 'readback', 'reconciliation', 'deployment_record', 'observed_after']


def tree(root):
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(Path(root).rglob('*')) if path.is_file()}


class DeliveryTests(unittest.TestCase):
    # The repository-change fixture: a generated project copied as the engineer's
    # repository, a modeled service and a collected store.
    # No module-level name may refer to the fixture class, or unittest would collect its tests here too.
    RESOURCE_ADDRESS = repository_tests.RepositoryOwnedChangeTests.RESOURCE_ADDRESS
    setUp = repository_tests.RepositoryOwnedChangeTests.setUp
    import_intent = repository_tests.RepositoryOwnedChangeTests.import_intent
    edit_description = repository_tests.RepositoryOwnedChangeTests.edit_description

    def prepare(self):
        from intune_iac.workbench_repository import propose_from_intent, refresh_intent
        self.import_intent()
        self.edit_description('Edited in the repository.')
        self.intent = refresh_intent(self.store, OBJECT, 'b' * 40)
        self.operation = self.root / 'operation'
        return propose_from_intent(self.store.root, self.service.root, OBJECT, self.operation)

    def view(self, **kw):
        from intune_iac.workbench_delivery import delivery
        value = delivery(self.operation, **kw)
        self.assertEqual(value['schema_version'], 'workbench-delivery/1')
        self.assertEqual([stage['stage'] for stage in value['stages']], STAGES)
        self.assertFalse(value['execution_authorized']); self.assertFalse(value['cloud_authority'])
        return value, {stage['stage']: stage for stage in value['stages']}

    def test_a_prepared_change_waits_for_approval_inside_its_window(self):
        review = self.prepare()
        value, stages = self.view(now=review['expires_at'] - 10)
        self.assertEqual(stages['proposal']['status'], 'done')
        self.assertEqual(stages['proposal']['repository_intent_id'], self.intent['artifact_id'])
        self.assertEqual(stages['proposal']['intent_freshness'], 'current')
        self.assertEqual(stages['review']['status'], 'done')
        self.assertEqual(stages['review']['changes'], [OBJECT + ':description_changed'])
        self.assertEqual(stages['review']['approval_digest'], review['approval_digest'])
        self.assertEqual((stages['approval']['status'], stages['approval']['closes_at']), ('waiting', review['expires_at']))
        self.assertEqual(stages['execution']['status'], 'not_started')
        self.assertEqual(stages['readback']['status'], 'not_started')
        self.assertEqual(stages['reconciliation']['status'], 'not_needed')
        self.assertEqual(stages['deployment_record']['status'], 'not_yet')
        self.assertEqual(stages['observed_after']['status'], 'not_yet')
        self.assertIn('execute OPERATION_DIR EXACT_REVIEW_DIGEST', value['next_action'])
        # The view never supplies the approval digest for the engineer.
        self.assertNotIn(review['approval_digest'], value['next_action'])

    def test_a_prepared_change_past_its_window_cannot_be_approved(self):
        review = self.prepare()
        value, stages = self.view(now=review['expires_at'])
        self.assertEqual(stages['approval']['status'], 'expired')
        self.assertIn('new proposal', value['next_action'])

    def test_an_executed_change_shows_each_stage_then_its_record_and_observation(self):
        from intune_iac import maintenance
        from intune_iac.workbench_views import record_local_deployment
        review = self.prepare()
        maintenance.execute(self.operation, approve_digest=review['approval_digest'])
        value, stages = self.view()
        self.assertEqual((stages['approval']['status'], stages['approval']['approval_digest']), ('done', review['approval_digest']))
        self.assertEqual((stages['execution']['status'], stages['execution']['service_status']), ('done', 200))
        self.assertEqual(stages['execution']['engine_status'], 'succeeded_verified')
        self.assertEqual((stages['readback']['status'], stages['readback']['classification']), ('done', 'desired_state_observed'))
        self.assertEqual((stages['readback']['second_plan'], stages['readback']['visibility_pending']), ('no_change', False))
        self.assertEqual(stages['reconciliation']['status'], 'not_needed')
        self.assertEqual(stages['deployment_record']['status'], 'available')
        self.assertEqual(stages['observed_after']['status'], 'not_yet')
        self.assertIn('deployment-record', value['next_action'])
        record_local_deployment(self.store, self.operation, self.intent['artifact_id'])
        self.store.collect(self.service)
        value, stages = self.view()
        self.assertEqual((stages['deployment_record']['status'], stages['deployment_record']['intent_id']), ('done', self.intent['artifact_id']))
        self.assertTrue(stages['deployment_record']['baseline_admissible'])
        self.assertEqual(stages['observed_after']['status'], 'matches_desired')
        self.assertEqual(stages['observed_after']['service_revision'], 2)
        self.assertEqual(value['next_action'], 'Nothing pending: the change is recorded and observed as desired.')

    def test_a_lost_response_requires_reconciliation_then_shows_it(self):
        from intune_iac import maintenance
        review = self.prepare()
        maintenance.execute(self.operation, approve_digest=review['approval_digest'], fault='lost-response')
        value, stages = self.view()
        self.assertEqual(stages['approval']['status'], 'done')
        self.assertEqual((stages['execution']['status'], stages['execution']['error_code']), ('unknown', 'model_response_lost'))
        self.assertEqual(stages['readback']['status'], 'not_recorded')
        self.assertEqual(stages['reconciliation']['status'], 'required')
        self.assertEqual(stages['deployment_record']['status'], 'not_yet')
        self.assertIn('reconcile OPERATION_DIR', value['next_action'])
        maintenance.reconcile(self.operation)
        value, stages = self.view()
        self.assertEqual((stages['reconciliation']['status'], stages['reconciliation']['classification']), ('done', 'desired_state_observed'))
        self.assertEqual(stages['reconciliation']['previous_status'], 'outcome_unknown')
        self.assertEqual(stages['execution']['status'], 'unknown')
        # deployment-record requires the execution's own verified readback; reconciliation does not supply one.
        self.assertEqual((stages['deployment_record']['status'], stages['deployment_record']['reason']), ('not_available', 'no_verified_readback'))
        self.assertIn('cannot become a deployment record', value['next_action'])

    def test_a_change_without_a_repository_citation_has_nothing_to_record(self):
        from intune_iac import maintenance
        desired = dict(self.store.inspect(OBJECT)['body'], description='Desired file, no repository citation.')
        path = self.root / 'desired.json'; path.write_text(json.dumps(desired))
        self.operation = self.root / 'operation'
        review = maintenance.propose(self.store.root, self.service.root, OBJECT, path, self.operation)
        maintenance.execute(self.operation, approve_digest=review['approval_digest'])
        value, stages = self.view()
        self.assertEqual(stages['proposal']['repository_intent_id'], None)
        self.assertEqual(stages['deployment_record']['status'], 'not_applicable')

    def test_the_view_reads_and_writes_nothing_else(self):
        from intune_iac import maintenance
        review = self.prepare()
        maintenance.execute(self.operation, approve_digest=review['approval_digest'], fault='lost-response')
        before = (tree(self.operation), tree(self.service.root), self.store.operations(), self.store.artifacts())
        self.view(); self.view(now=0)
        self.assertEqual((tree(self.operation), tree(self.service.root), self.store.operations(), self.store.artifacts()), before)

    def test_a_changed_journal_is_refused(self):
        from intune_iac.io import AppError
        self.prepare()
        journal = json.loads((self.operation / 'journal.json').read_text())
        journal['events'][0]['kind'] = 'approved'
        (self.operation / 'journal.json').write_text(json.dumps(journal))
        with self.assertRaises(AppError) as caught:
            self.view()
        self.assertEqual(caught.exception.code, 'maintenance_journal_changed')


if __name__ == '__main__':
    unittest.main()
