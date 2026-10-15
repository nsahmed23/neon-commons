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


class DeploymentRecordedOnceTests(unittest.TestCase):
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


if __name__ == '__main__':
    unittest.main()
