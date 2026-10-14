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
        self.assertIn('execute %s EXACT_REVIEW_DIGEST' % self.operation, value['next_action'])
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

    def test_the_workspace_records_the_deployment_delivery_offers(self):
        # The record step no longer needs a shell: the workspace runs the same command Delivery names.
        from intune_iac import maintenance
        from intune_iac.workbench import run_terminal
        review = self.prepare()
        maintenance.execute(self.operation, approve_digest=review['approval_digest'])
        value, _ = self.view()
        self.assertIn('deployment-record %s %s' % (self.operation, self.intent['artifact_id']), value['next_action'])
        commands = iter(['deployment-record %s %s' % (self.operation, self.intent['artifact_id']), 'quit'])
        results = []
        run_terminal(self.store.root, input_fn=lambda _: next(commands), result_fn=results.append)
        recorded = [item for item in results if item.get('kind') == 'deployment_receipt']
        self.assertEqual(len(recorded), 1, results[-2:])
        _, stages = self.view()
        self.assertEqual((stages['deployment_record']['status'], stages['deployment_record']['intent_id']),
                         ('done', self.intent['artifact_id']))

    def test_imported_workflow_runs_appear_as_inert_delivery_evidence(self):
        from intune_iac.workbench_health import import_workflow_run
        review = self.prepare()
        value, _ = self.view()
        self.assertEqual(value['workflow_runs'], [])
        envelope = {'schema_version': 'workbench-workflow-run/1', 'tenant_id': repository_tests.TENANT, 'object_id': OBJECT,
                    'run_url': 'https://ci.example.invalid/runs/42', 'repository_revision': 'b' * 40, 'run_id': '42',
                    'status': 'success', 'observed_at': '2026-10-14T12:00:00Z', 'workflow': 'plan',
                    'related_operation': review['operation_id']}
        path = self.root / 'run.json'; path.write_text(json.dumps(envelope))
        import_workflow_run(self.store, path)
        other = dict(envelope, run_id='43', related_operation=None, repository_revision='c' * 40)
        other.pop('related_operation')
        path.write_text(json.dumps(other)); import_workflow_run(self.store, path)
        # A run for the revision the operation's intent cites, without an operation link.
        cited = dict(other, run_id='44', repository_revision='b' * 40)
        path.write_text(json.dumps(cited)); import_workflow_run(self.store, path)
        # A run linked to a different operation for the same revision belongs to that operation only.
        from intune_iac.workbench_repository import propose_from_intent
        second = propose_from_intent(self.store.root, self.service.root, OBJECT, self.root / 'operation-2')
        elsewhere = dict(envelope, run_id='45', related_operation=second['operation_id'])
        path.write_text(json.dumps(elsewhere)); import_workflow_run(self.store, path)
        value, _ = self.view()
        runs = value['workflow_runs']
        self.assertEqual([(run['run_id'], run['relation']) for run in runs],
                         [('42', 'related_operation'), ('44', 'cited_revision')])
        self.assertEqual((runs[0]['status'], runs[0]['evidence_class'], runs[0]['external_execution_verified']), ('success', 'caller_asserted', False))

    def run_envelope(self, operation_id, run_id='42'):
        return {'schema_version': 'workbench-workflow-run/1', 'tenant_id': repository_tests.TENANT, 'object_id': OBJECT,
                'run_url': 'https://ci.example.invalid/runs/' + run_id, 'repository_revision': 'b' * 40, 'run_id': run_id,
                'status': 'success', 'observed_at': '2026-10-14T12:00:00Z', 'workflow': 'apply',
                'related_operation': operation_id}

    def import_run(self, envelope):
        from intune_iac.workbench_health import import_workflow_run
        path = self.root / ('run-%s.json' % envelope['run_id']); path.write_text(json.dumps(envelope))
        return import_workflow_run(self.store, path)

    def artifacts_failing_for(self, failing_kind):
        """The store's artifact query, refusing one kind as an oversized query would."""
        from intune_iac.io import AppError
        real = type(self.store).artifacts
        def artifacts(store, kind=None, object_id=None, **kw):
            if kind == failing_kind:
                raise AppError('workbench_query_limit', 'Too many rows.')
            return real(store, kind, object_id, **kw)
        return artifacts

    def test_a_ci_success_claim_never_changes_a_stage(self):
        review = self.prepare()
        _, before = self.view()
        self.import_run(self.run_envelope(review['operation_id']))
        value, after = self.view()
        self.assertEqual(after, before)
        self.assertEqual([run['run_id'] for run in value['workflow_runs']], ['42'])
        self.assertEqual(value['workflow_runs_read'], {'status': 'complete', 'records_read': 1})

    def test_unreadable_ci_runs_never_hide_the_stages(self):
        from unittest import mock
        self.prepare()
        with mock.patch.object(type(self.store), 'artifacts', self.artifacts_failing_for('workflow_run')):
            value, stages = self.view()
        self.assertEqual((stages['proposal']['status'], stages['review']['status']), ('done', 'done'))
        self.assertEqual(value['workflow_runs'], [])
        self.assertEqual(value['workflow_runs_read'], {'status': 'unavailable', 'error_code': 'workbench_query_limit'})

    def test_ci_runs_are_read_in_bounded_pages(self):
        from unittest import mock
        from intune_iac import workbench_delivery
        review = self.prepare()
        self.import_run(self.run_envelope(review['operation_id'], '42'))
        self.import_run(self.run_envelope(review['operation_id'], '43'))
        with mock.patch.object(workbench_delivery, 'RUN_PAGE', 1), mock.patch.object(workbench_delivery, 'MAX_RUN_RECORDS', 1):
            value, _ = self.view()
        self.assertEqual(value['workflow_runs_read'], {'status': 'partial', 'records_read': 1})
        self.assertEqual(len(value['workflow_runs']), 1)

    def test_the_cited_intent_is_found_by_identity_without_reading_every_intent(self):
        from unittest import mock
        self.prepare()
        with mock.patch.object(type(self.store), 'artifacts', self.artifacts_failing_for('repository_intent')):
            value, stages = self.view()
        self.assertEqual(stages['proposal']['intent_freshness'], 'current')

    def test_a_changed_context_is_never_read_as_a_citation(self):
        # The review and the delivery view read the citation only from the bytes the plan bound.
        from intune_iac import maintenance
        from intune_iac.io import AppError
        from intune_iac.workbench_screens import delivery_lines
        review = self.prepare()
        context = Path(json.loads((self.operation / 'plan.json').read_text())['context']['path'])
        value = json.loads(context.read_text()); value.pop('repository_intent_id'); value.pop('scope')
        context.write_text(json.dumps(value))
        self.assertEqual(maintenance.review(self.operation)['repository'],
                         {'cited': None, 'context_changed': True, 'context_path': str(context)})
        value, stages = self.view(now=review['expires_at'] - 10)
        self.assertTrue(stages['proposal']['context_changed'])
        self.assertIsNone(stages['proposal']['repository_intent_id'])
        self.assertEqual((stages['deployment_record']['status'], stages['deployment_record']['reason']),
                         ('not_available', 'context_changed'))
        self.assertIn('changed after it was prepared', value['next_action'])
        self.assertIn('prepare a new proposal', value['next_action'])
        text = ' '.join(' '.join(delivery_lines(value, 140)).split())
        self.assertIn('context changed since this proposal was prepared', text)
        self.assertNotIn('no repository intent cited', text)
        with self.assertRaises(AppError) as raised:
            maintenance.execute(self.operation, approve_digest=review['approval_digest'])
        self.assertEqual(raised.exception.code, 'maintenance_source_changed')

    def edit_bound_context(self):
        context = Path(json.loads((self.operation / 'plan.json').read_text())['context']['path'])
        value = json.loads(context.read_text()); value['note'] = 'edited after the plan'
        context.write_text(json.dumps(value))

    def test_a_context_changed_after_execution_blocks_the_record_and_says_why(self):
        from intune_iac import maintenance
        review = self.prepare()
        maintenance.execute(self.operation, approve_digest=review['approval_digest'])
        self.edit_bound_context()
        value, stages = self.view()
        self.assertEqual((stages['deployment_record']['status'], stages['deployment_record']['reason']),
                         ('not_available', 'context_changed'))
        self.assertIn('cannot become a deployment record', value['next_action'])
        self.assertEqual(value['workflow_runs_read'].get('cited_revision'), 'unknown')

    def test_a_recorded_deployment_whose_context_changed_is_not_called_settled(self):
        # The record exists, but the views recheck the bound bytes and no longer admit it as a baseline.
        from intune_iac import maintenance
        from intune_iac.workbench_screens import delivery_lines
        from intune_iac.workbench_views import record_local_deployment
        review = self.prepare()
        maintenance.execute(self.operation, approve_digest=review['approval_digest'])
        record_local_deployment(self.store, self.operation, self.intent['artifact_id'])
        self.store.collect(self.service)
        self.edit_bound_context()
        value, stages = self.view()
        self.assertEqual(stages['deployment_record']['status'], 'done')
        self.assertTrue(stages['deployment_record']['context_changed'])
        self.assertNotIn('Nothing pending', value['next_action'])
        self.assertIn('no longer passes its own check', value['next_action'])
        text = ' '.join(' '.join(delivery_lines(value, 140)).split())
        self.assertIn('context file changed since; no longer admitted as a baseline', text)
        self.assertNotIn('baseline admissible', text)

    def test_one_artifact_is_read_by_its_identity(self):
        intent = self.import_intent()
        self.assertEqual(self.store.artifact(intent['artifact_id'])['data']['target_object_id'], OBJECT)
        self.assertEqual(self.store.artifact(intent['artifact_id'], kind='repository_intent')['artifact_id'], intent['artifact_id'])
        self.assertIsNone(self.store.artifact(intent['artifact_id'], kind='workflow_run'))
        self.assertIsNone(self.store.artifact('f' * 64))
        self.assertIsNone(self.store.artifact('not-an-artifact-id'))

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
        self.assertIn('reconcile %s' % self.operation, value['next_action'])
        maintenance.reconcile(self.operation)
        value, stages = self.view()
        self.assertEqual((stages['reconciliation']['status'], stages['reconciliation']['classification']), ('done', 'desired_state_observed'))
        self.assertEqual(stages['reconciliation']['previous_status'], 'outcome_unknown')
        self.assertEqual(stages['execution']['status'], 'unknown')
        # deployment-record requires the execution's own verified readback; reconciliation does not supply one.
        self.assertEqual((stages['deployment_record']['status'], stages['deployment_record']['reason']), ('not_available', 'no_verified_readback'))
        self.assertIn('cannot become a deployment record', value['next_action'])

    def test_the_history_lists_every_journal_event_with_store_times_only_where_they_pair(self):
        from intune_iac import maintenance
        review = self.prepare()
        maintenance.execute(self.operation, approve_digest=review['approval_digest'], fault='lost-response')
        value, _ = self.view()
        history = value['history']
        journal = json.loads((self.operation / 'journal.json').read_text())
        self.assertEqual([event['kind'] for event in history['events']], [event['kind'] for event in journal['events']])
        self.assertEqual([event['sequence'] for event in history['events']], list(range(len(journal['events']))))
        records = self.store.operations(object_id=OBJECT)
        first, last = history['events'][0], history['events'][-1]
        # The store registered the journal after the proposal and after the execution, each with its digest.
        self.assertEqual((first['kind'], first['store_status'], first['store_recorded_at']), ('prepared', 'prepared', records[0]['recorded_at']))
        self.assertEqual((last['kind'], last['store_status'], last['store_recorded_at']), ('uncertain', 'outcome_unknown', records[1]['recorded_at']))
        self.assertEqual(last['fields'], {'error_code': 'model_response_lost'})
        # Events between registrations have no recorded time; none is invented.
        for event in history['events'][1:-1]:
            self.assertIsNone(event['store_recorded_at']); self.assertIsNone(event['store_status'])
        self.assertEqual((history['registrations'], history['paired']), (2, 2))
        self.assertNotIn('previous_sha256', json.dumps(history['events']))
        maintenance.reconcile(self.operation)
        value, _ = self.view()
        reconciled = value['history']['events'][-1]
        self.assertEqual((reconciled['kind'], reconciled['store_status']), ('reconciled', 'reconciled'))
        self.assertEqual(reconciled['fields']['classification'], 'desired_state_observed')
        self.assertEqual((value['history']['registrations'], value['history']['paired']), (3, 3))

    def test_dispatch_is_not_established_after_a_lost_response(self):
        from intune_iac import maintenance
        review = self.prepare()
        maintenance.execute(self.operation, approve_digest=review['approval_digest'], fault='lost-response')
        _, stages = self.view()
        # The modeled service applied the change and lost its answer; no answer is not evidence of no dispatch.
        self.assertIsNone(stages['execution']['mutation_dispatched'])
        self.assertFalse(stages['execution']['no_change_dispatch'])

    def test_dispatch_is_true_with_an_answer_and_false_when_nothing_was_sent(self):
        from intune_iac import maintenance
        review = self.prepare()
        maintenance.execute(self.operation, approve_digest=review['approval_digest'])
        self.assertIs(self.view()[1]['execution']['mutation_dispatched'], True)
        # A second proposal whose desired body is what the service now holds: nothing is sent.
        self.store.collect(self.service)
        desired = dict(self.store.inspect(OBJECT)['body'])
        path = self.root / 'same.json'; path.write_text(json.dumps(desired))
        self.operation = self.root / 'operation-same'
        same = maintenance.propose(self.store.root, self.service.root, OBJECT, path, self.operation)
        maintenance.execute(self.operation, approve_digest=same['approval_digest'])
        execution = self.view()[1]['execution']
        self.assertEqual((execution['mutation_dispatched'], execution['no_change_dispatch']), (False, True))

    def test_a_receipt_gap_never_replaces_a_surviving_receipt(self):
        from intune_iac import maintenance
        review = self.prepare()
        maintenance.execute(self.operation, approve_digest=review['approval_digest'], fault='lost-response')
        for _ in range(3):
            maintenance.reconcile(self.operation)
        (self.operation / 'reconciliation-1.json').unlink()
        survivor = (self.operation / 'reconciliation-2.json').read_bytes()
        maintenance.reconcile(self.operation)
        self.assertEqual((self.operation / 'reconciliation-2.json').read_bytes(), survivor)
        self.assertTrue((self.operation / 'reconciliation-3.json').exists())
        self.assertFalse((self.operation / 'reconciliation-1.json').exists())

    def test_a_registration_that_does_not_pair_attaches_to_no_event(self):
        from intune_iac.workbench_delivery import _history
        journal = {'operation_id': 'a' * 32, 'plan_sha256': 'b' * 64, 'status': 'prepared',
                   'events': [{'sequence': 0, 'kind': 'prepared', 'previous_sha256': '0' * 64, 'approval_digest': 'c' * 64}]}
        history = _history(journal, [{'status': 'prepared', 'journal_sha256': 'd' * 64, 'recorded_at': '2026-10-14T00:00:00Z'}])
        self.assertIsNone(history['events'][0]['store_recorded_at'])
        self.assertEqual((history['registrations'], history['paired']), (1, 0))

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
