"""Refusal effects (P-PRES-18): each refusal says what it established about what changed, never a blanket no-op.

The engine attaches the facts it can establish, mostly by reading the store or the filesystem after the refusal: a
refused refresh compares the latest intent before and after; a refused proposal names the input files it wrote and
whether an operation directory exists; a refused execution says whether dispatch had started. The screens only put
those facts into words. The real store, modeled service and maintenance engine produce each case.
"""
import json
from pathlib import Path
import unittest

from plugin_tests import test_workbench_repository as repository_tests

OBJECT, TENANT = repository_tests.OBJECT, repository_tests.TENANT


class RefusalEffectTests(unittest.TestCase):
    RESOURCE_ADDRESS = repository_tests.RepositoryOwnedChangeTests.RESOURCE_ADDRESS
    setUp = repository_tests.RepositoryOwnedChangeTests.setUp
    import_intent = repository_tests.RepositoryOwnedChangeTests.import_intent
    edit_description = repository_tests.RepositoryOwnedChangeTests.edit_description

    def refused(self, call):
        from intune_iac.io import AppError
        with self.assertRaises(AppError) as raised:
            call()
        return raised.exception

    def test_a_refused_refresh_establishes_that_no_new_intent_was_recorded(self):
        from intune_iac.workbench_repository import intent_freshness, latest_intent, refresh_intent
        first = self.import_intent()
        self.edit_description('Shown difference.')
        shown = intent_freshness(latest_intent(self.store, OBJECT)['data'])['resolution_sha256']
        self.edit_description('A second, unseen edit.')
        error = self.refused(lambda: refresh_intent(self.store, OBJECT, 'b' * 40, expected_resolution=shown))
        self.assertEqual(error.code, 'workbench_difference_changed')
        self.assertEqual(error.effects, {'intent_recorded': False, 'retained_intent': first['artifact_id']})

    def test_a_proposal_refused_before_its_inputs_writes_nothing(self):
        from intune_iac.workbench_repository import propose_from_intent
        self.import_intent()
        self.edit_description('Changed and not refreshed.')
        output = self.root / 'operation'
        error = self.refused(lambda: propose_from_intent(self.store.root, self.service.root, OBJECT, output))
        self.assertEqual(error.code, 'workbench_repository_stale')
        self.assertEqual(error.effects, {'files_written': [], 'operation_created': False})

    def test_a_proposal_refused_after_its_inputs_names_the_files_it_left(self):
        from intune_iac.workbench_repository import propose_from_intent, refresh_intent
        from intune_iac.modeled_service import BASE, ModeledService
        self.import_intent()
        self.edit_description('Edited.')
        refresh_intent(self.store, OBJECT, 'b' * 40)
        service = ModeledService(self.service.root)
        body = dict(service.snapshot()['current']['objects'][OBJECT], description='Changed in the service.')
        service.request('PATCH', BASE + '/' + OBJECT, tenant_id=TENANT, body=body,
                        if_match=str(service.snapshot()['revision']))
        output = self.root / 'operation'
        error = self.refused(lambda: propose_from_intent(self.store.root, self.service.root, OBJECT, output))
        self.assertEqual(error.code, 'maintenance_observation_stale')
        self.assertEqual(error.effects, {'files_written': [str(output) + '.intent-desired.json', str(output) + '.intent-context.json'],
                                         'operation_created': False})
        for path in error.effects['files_written']:
            self.assertTrue(Path(path).is_file(), path)

    def test_an_execution_refused_before_dispatch_says_so(self):
        from intune_iac import maintenance
        from intune_iac.workbench_repository import propose_from_intent, refresh_intent
        self.import_intent()
        self.edit_description('Edited.')
        refresh_intent(self.store, OBJECT, 'b' * 40)
        operation = self.root / 'operation'
        propose_from_intent(self.store.root, self.service.root, OBJECT, operation)
        error = self.refused(lambda: maintenance.execute(operation, approve_digest='0' * 64))
        self.assertEqual(error.code, 'maintenance_approval_required')
        self.assertEqual(error.effects, {'dispatched': False})

    def test_a_refused_deployment_record_records_nothing(self):
        from intune_iac.workbench_views import record_local_deployment
        self.import_intent()
        error = self.refused(lambda: record_local_deployment(self.store, self.root / 'missing-operation', 'f' * 64))
        self.assertEqual(error.effects, {'deployment_recorded': False})

    def executed(self, **kw):
        from intune_iac import maintenance
        from intune_iac.workbench_repository import propose_from_intent, refresh_intent
        self.import_intent()
        self.edit_description('Edited.')
        refresh_intent(self.store, OBJECT, 'b' * 40)
        operation = self.root / 'operation'
        review = propose_from_intent(self.store.root, self.service.root, OBJECT, operation)
        return operation, maintenance.execute(operation, approve_digest=review['approval_digest'], **kw)

    def test_execution_and_reconcile_state_their_effect(self):
        from intune_iac import maintenance
        operation, result = self.executed(fault='lost-response')
        self.assertEqual(result['status'], 'outcome_unknown')
        self.assertEqual(result['effects'], {'dispatched': True, 'service_change': 'unknown'})
        reconciled = maintenance.reconcile(operation)
        self.assertEqual(reconciled['effects'], {'replayed': False})

    def test_a_verified_execution_says_the_change_was_observed(self):
        _, result = self.executed()
        self.assertEqual(result['effects'], {'dispatched': True, 'service_change': 'observed_as_desired'})

    def test_the_execution_surface_words_the_effect(self):
        from plugin_tests.test_workbench_states import RefusalCauseTests
        workspace = RefusalCauseTests.workspace(self)
        workspace.tab = 5
        workspace.value = {'operation_id': 'a' * 32, 'status': 'outcome_unknown', 'error_code': 'model_response_lost',
                           'evidence_class': 'synthetic_local_process_and_modeled_service_only',
                           'effects': {'dispatched': True, 'service_change': 'unknown'}}
        text = ' '.join(' '.join(workspace._summary_lines(118)).split())
        self.assertIn('[EXECUTION RESULT]', text)
        self.assertIn('Status: outcome unknown', text)
        self.assertIn('Effect: Dispatch started; whether the service applied the change is unknown '
                      '(model_response_lost). Reconcile checks it without repeating the change.', text)
        self.assertNotIn('[CHECKS / JOURNAL / RESULT]', text)
        self.assertEqual(text.count('Next:'), 1)  # the lifecycle line's next step, not a second generic one

    def test_the_words_follow_the_facts(self):
        from intune_iac.workbench_screens import effect_lines, refusal_lines
        text = ' '.join(effect_lines({'intent_recorded': False, 'retained_intent': 'a' * 64}, 120))
        self.assertIn('No new intent was recorded; the previous intent aaaaaaaaaaaa is retained.', text)
        text = ' '.join(effect_lines({'files_written': ['/w/op.intent-desired.json', '/w/op.intent-context.json'],
                                      'operation_created': False}, 160))
        self.assertIn('No proposal was created. These input files were written and remain: /w/op.intent-desired.json, '
                      '/w/op.intent-context.json.', text)
        self.assertIn('No proposal and no input files were created.',
                      ' '.join(effect_lines({'files_written': [], 'operation_created': False}, 120)))
        self.assertIn('Nothing was dispatched.', ' '.join(effect_lines({'dispatched': False}, 120)))
        self.assertIn('Dispatch had started, so the outcome is unknown',
                      ' '.join(effect_lines({'dispatched': True}, 120)))
        self.assertEqual(effect_lines(None, 120), [])
        value = {'status': 'error', 'error': {'code': 'workbench_difference_changed', 'message': 'changed again',
                                              'effects': {'intent_recorded': False, 'retained_intent': 'a' * 64}}}
        text = ' '.join(' '.join(refusal_lines(value, 120)).split())
        self.assertIn('Effect: No new intent was recorded; the previous intent aaaaaaaaaaaa is retained.', text)

    def test_the_workspace_and_the_cli_carry_the_effects(self):
        import subprocess, sys, os
        from intune_iac.workbench import run_terminal
        self.import_intent()
        commands = iter(['select ' + OBJECT, 'repository-refresh ' + 'b' * 40 + ' ' + '0' * 64, 'quit'])
        results = []
        run_terminal(self.store.root, input_fn=lambda _: next(commands), result_fn=results.append)
        refused = [item for item in results if item.get('status') == 'error']
        self.assertEqual(refused[-1]['error']['code'], 'workbench_difference_changed')
        self.assertIs(refused[-1]['error']['effects']['intent_recorded'], False)
        root = Path(__file__).resolve().parents[1]
        process = subprocess.run([sys.executable, '-B', str(root / 'scripts/intune-iac.py'), 'workbench', 'deployment-record',
                                  '--root', str(self.store.root), '--operation', str(self.root / 'missing'), '--intent', 'f' * 64],
                                 capture_output=True, text=True, cwd='/tmp', timeout=60,
                                 env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
        self.assertNotEqual(process.returncode, 0)
        self.assertEqual(json.loads(process.stderr)['error']['effects'], {'deployment_recorded': False})


if __name__ == '__main__':
    unittest.main()


class RefreshResultTests(unittest.TestCase):
    """A successful refresh says what it established, read back from the store: the new intent, and the previous
    intent kept as history. Reviews prepared from that one do not cover the new intent and stay inspectable; nothing
    says they were deleted or invalidated everywhere (TASK-11 5.8)."""
    RESOURCE_ADDRESS = repository_tests.RepositoryOwnedChangeTests.RESOURCE_ADDRESS
    setUp = repository_tests.RepositoryOwnedChangeTests.setUp
    import_intent = repository_tests.RepositoryOwnedChangeTests.import_intent
    edit_description = repository_tests.RepositoryOwnedChangeTests.edit_description

    def test_a_successful_refresh_names_the_previous_intent_it_kept(self):
        from intune_iac.workbench_repository import refresh_intent
        from intune_iac.workbench_screens import refresh_result_lines
        first = self.import_intent()
        self.edit_description('Edited in the repository.')
        second = refresh_intent(self.store, OBJECT, 'b' * 40)
        self.assertEqual(second['effects'], {'intent_recorded': True, 'previous_intent': first['artifact_id'],
                                             'latest_intent': second['artifact_id']})
        text = ' '.join(' '.join(refresh_result_lines(second, 100)).split())
        self.assertIn('[NEW REPOSITORY INTENT RECORDED]', text)
        self.assertIn('Previous intent %s is kept as history.' % first['artifact_id'][:12], text)
        self.assertIn('Reviews prepared from it do not cover this intent; they remain inspectable (4 History, 5 Plan).', text)
        self.assertNotIn('not current', text)

    def test_a_result_without_effects_claims_nothing_about_the_previous_intent(self):
        from intune_iac.workbench_screens import refresh_result_lines
        value = {'kind': 'repository_intent', 'artifact_id': 'c' * 36, 'data': {'source_revision': 'b' * 40}}
        text = ' '.join(' '.join(refresh_result_lines(value, 100)).split())
        self.assertNotIn('Previous intent', text)
        self.assertNotIn('kept', text)


class RecordedRefreshTests(unittest.TestCase):
    """The workspace shows a recorded refresh through the general record view (journey 27 run 1, frame 16): that view
    must carry what the refresh established, not only that something was recorded."""

    def test_the_record_view_of_a_refresh_names_the_previous_intent_it_kept(self):
        from intune_iac.workbench_screens import recorded_lines
        value = {'kind': 'repository_intent', 'artifact_id': 'b' * 64, 'created': True, 'recorded_at': '2026-10-14T23:50:55Z',
                 'data': {'source_revision': 'c' * 40, 'revision_content_verified': False, 'consumer': {'status': 'verified'}},
                 'effects': {'intent_recorded': True, 'previous_intent': 'a' * 64, 'latest_intent': 'b' * 64}}
        text = ' '.join(' '.join(recorded_lines(value, 100)).split())
        self.assertIn('[RECORDED] repository intent bbbbbbbbbbbb | new record', text)
        self.assertIn('Previous intent aaaaaaaaaaaa is kept as history.', text)
        self.assertIn('Revision: %s (caller asserted, not checked against the files)' % ('c' * 40), text)
        self.assertNotIn('[NEW REPOSITORY INTENT RECORDED]', text)
