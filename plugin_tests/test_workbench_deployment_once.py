"""DEF-DEPLOY-DUP: recording the same deployment twice records it once.

The real maintenance engine and the modeled service run each case. A deployment record carried recorded_at in its data, so
its content-derived identity differed on every call and the store's identical-identity return never applied; the check for
an existing record now runs inside the store's write transaction.
"""
import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path

from plugin_tests import test_workbench_delivery as delivery_tests
from plugin_tests import test_workbench_repository as repository_tests

ROOT = Path(__file__).resolve().parents[1]
OBJECT = repository_tests.OBJECT

# One process records the deployment once the other is also ready, so the two writes contend for the same store.
RECORD_SCRIPT = '''
import json, sys, time
from pathlib import Path
from intune_iac.workbench_store import WorkbenchStore
from intune_iac.workbench_views import record_local_deployment
store_root, operation, intent_id, ready, go = sys.argv[1:6]
store = WorkbenchStore(Path(store_root))
Path(ready).write_text('ready')
deadline = time.time() + 60
while not Path(go).exists() and time.time() < deadline:
    time.sleep(0.005)
result = record_local_deployment(store, operation, intent_id)
print(json.dumps({'artifact_id': result['artifact_id'], 'created': result['created']}))
'''


class Fixture:
    """A prepared, executed operation and its store; a mixin so each test class collects only its own tests."""
    RESOURCE_ADDRESS = repository_tests.RepositoryOwnedChangeTests.RESOURCE_ADDRESS
    setUp = repository_tests.RepositoryOwnedChangeTests.setUp
    import_intent = repository_tests.RepositoryOwnedChangeTests.import_intent
    edit_description = repository_tests.RepositoryOwnedChangeTests.edit_description
    prepare = delivery_tests.DeliveryTests.prepare

    def executed(self):
        from intune_iac import maintenance
        review = self.prepare()
        maintenance.execute(self.operation, approve_digest=review['approval_digest'])
        return review

    def receipts(self):
        return self.store.artifacts(kind='deployment_receipt')

    def record(self, intent_id=None):
        from intune_iac.workbench_views import record_local_deployment
        return record_local_deployment(self.store, self.operation, intent_id or self.intent['artifact_id'])


class DeploymentRecordedOnceTests(Fixture, unittest.TestCase):
    def test_the_second_recording_returns_the_first_record_and_adds_none(self):
        self.executed()
        first, second = self.record(), self.record()
        self.assertTrue(first['created'])
        self.assertFalse(second['created'])
        self.assertEqual(second['artifact_id'], first['artifact_id'])
        # The time it reports is the first record's, so the engineer sees when it was recorded.
        self.assertEqual(second['recorded_at'], first['recorded_at'])
        self.assertEqual(len(self.receipts()), 1)

    def test_a_third_recording_still_returns_the_first(self):
        self.executed()
        first = self.record()
        self.record()
        third = self.record()
        self.assertEqual((third['created'], third['artifact_id']), (False, first['artifact_id']))
        self.assertEqual(len(self.receipts()), 1)

    def test_two_processes_recording_at_once_make_one_receipt(self):
        self.executed()
        ready = [self.root / 'ready-a', self.root / 'ready-b']
        go = self.root / 'go'
        env = dict(os.environ, PYTHONPATH=str(ROOT))
        procs = [subprocess.Popen([sys.executable, '-c', RECORD_SCRIPT, str(self.store.root), str(self.operation),
                                   self.intent['artifact_id'], str(mark), str(go)],
                                  cwd=str(ROOT), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                 for mark in ready]
        self.addCleanup(lambda: [p.kill() for p in procs if p.poll() is None])
        deadline = time.time() + 60
        while not all(mark.exists() for mark in ready) and time.time() < deadline:
            time.sleep(0.01)
        go.write_text('go')
        outputs = [p.communicate(timeout=120) for p in procs]
        for proc, (out, err) in zip(procs, outputs):
            self.assertEqual(proc.returncode, 0, err)
        results = [json.loads(out.strip().splitlines()[-1]) for out, _ in outputs]
        self.assertEqual(len(self.receipts()), 1, results)
        self.assertEqual(sorted(r['created'] for r in results), [False, True], results)
        self.assertEqual(len({r['artifact_id'] for r in results}), 1, results)


class RefusalsAndOtherProofsTests(Fixture, unittest.TestCase):
    """A second recording is only the same deployment when every refusal passes and the proof is the recorded one."""

    def refusal_code(self, intent_id=None):
        from intune_iac.io import AppError
        with self.assertRaises(AppError) as caught:
            self.record(intent_id)
        self.assertIs(caught.exception.effects['deployment_recorded'], False)
        return caught.exception.code

    def test_a_wrong_intent_is_still_refused_after_a_record_exists(self):
        self.executed()
        self.record()
        other = [row for row in self.store.artifacts(kind='repository_intent')
                 if row['artifact_id'] != self.intent['artifact_id']][0]['artifact_id']
        self.assertEqual(self.refusal_code(other), 'workbench_deployment_intent_not_cited')
        self.assertEqual(self.refusal_code('f' * 64), 'workbench_deployment_intent')
        self.assertEqual(len(self.receipts()), 1)

    def test_an_unverified_operation_is_refused_and_records_nothing(self):
        self.prepare()
        self.assertEqual(self.refusal_code(), 'workbench_deployment_unverified')
        self.assertEqual(self.receipts(), [])

    def test_a_context_changed_after_the_record_is_refused_not_answered_with_the_record(self):
        # The refusals run before the store is asked, so a record never excuses a proof that no longer passes.
        from intune_iac import maintenance
        self.executed()
        self.record()
        _, plan, _, _, _ = maintenance._load(self.operation)
        path = Path(plan['context']['path'])
        path.write_bytes(path.read_bytes() + b' ')
        self.assertEqual(self.refusal_code(), 'workbench_deployment_context_mismatch')
        self.assertEqual(len(self.receipts()), 1)

    def test_a_proof_that_differs_from_the_recorded_one_is_a_different_deployment(self):
        import copy
        self.executed()
        first = self.record()
        template = copy.deepcopy(first['data'])
        same_time_later = dict(template, recorded_at=template['recorded_at'] + 5)
        self.assertFalse(self.store.record_artifact('deployment_receipt', None, same_time_later,
                         once_by=('$.proof.operation_id', template['proof']['operation_id'], ('recorded_at',)))['created'])
        def variant(proof=None, **top):
            data = copy.deepcopy(template)
            data['recorded_at'] += 9
            data['proof'].update(proof or {})
            data.update(top)
            return data
        different = {'readback': variant(proof={'readback_sha256': '0' * 64}), 'plan': variant(proof={'plan_sha256': '1' * 64}),
                     'operation': variant(proof={'operation_id': 'another-operation'}), 'intent': variant(intent_id='2' * 64)}
        for name, data in different.items():
            result = self.store.record_artifact('deployment_receipt', None, data,
                                                once_by=('$.proof.operation_id', data['proof']['operation_id'], ('recorded_at',)))
            self.assertTrue(result['created'], name)
        self.assertEqual(len(self.receipts()), 1 + len(different))


class DuplicateRecordsStayReadableTests(Fixture, unittest.TestCase):
    """Records made before the fix, one operation recorded more than once, are read, not rewritten."""

    def duplicates(self, extra=1):
        import copy
        self.executed()
        first = self.record()
        for n in range(extra):
            data = copy.deepcopy(first['data'])
            data['recorded_at'] += 100 * (n + 1)
            self.assertTrue(self.store.record_artifact('deployment_receipt', None, data)['created'])
        return first

    def stage(self):
        from intune_iac.workbench_delivery import delivery
        value = delivery(self.operation)
        return value, {stage['stage']: stage for stage in value['stages']}['deployment_record']

    def test_delivery_shows_the_earliest_record_and_the_count_when_there_are_several(self):
        first = self.duplicates(extra=2)
        self.assertEqual(len(self.receipts()), 3)
        value, stage = self.stage()
        self.assertEqual((stage['status'], stage['artifact_id'], stage['recorded_at']),
                         ('done', first['artifact_id'], first['recorded_at']))
        self.assertEqual(stage['record_count'], 3)
        self.assertIn('3 deployment records', value['next_action'])
        self.assertIn('earliest', value['next_action'])

    def test_one_record_says_nothing_about_a_count(self):
        self.executed()
        first = self.record()
        value, stage = self.stage()
        self.assertEqual(stage['artifact_id'], first['artifact_id'])
        self.assertNotIn('record_count', stage)
        self.assertNotIn('deployment records', value['next_action'])
        self.assertNotIn('earliest', value['next_action'])

    def test_recording_again_over_older_duplicates_returns_the_earliest_and_adds_none(self):
        first = self.duplicates()
        again = self.record()
        self.assertEqual((again['created'], again['artifact_id']), (False, first['artifact_id']))
        self.assertEqual(len(self.receipts()), 2)

    def test_the_stage_for_the_deployment_guided_action_reads_the_same_earliest_record(self):
        from intune_iac.workbench_delivery import deployment_stage
        first = self.duplicates()
        self.assertEqual(deployment_stage(str(self.operation))['artifact_id'], first['artifact_id'])


if __name__ == '__main__':
    unittest.main()
