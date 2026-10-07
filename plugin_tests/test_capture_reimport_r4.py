"""A repeated verified capture is an import attempt, not a new observation."""
import copy
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from intune_iac.capture import capture
from intune_iac.workbench_store import WorkbenchStore


ROOT = Path(__file__).resolve().parents[1]
TENANT = '11111111-1111-4111-8111-111111111111'
OBJECT = '22222222-2222-4222-8222-222222222222'


class CaptureReimportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = WorkbenchStore.create(self.root / 'store', TENANT)
        fixture = json.loads((ROOT / 'examples/supported/input/export.json').read_bytes())
        self.responses = {}
        for collection in fixture['collections']:
            for page in collection['pages']:
                body = copy.deepcopy(page['body'])
                if page['request_url'].endswith('/assignments'):
                    for row in body['value']:
                        row.update(source='direct', sourceId=None)
                self.responses[page['request_url']] = (page['http_status'], json.dumps(body).encode())
        self.capture = self.root / 'capture'
        capture(TENANT, OBJECT, self.capture, transport=lambda url: self.responses[url])

    def call(self, name, *args):
        result = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/intune-iac.py'),
            'workbench', name, '--root', str(self.store.root), *map(str, args)],
            capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return json.loads(result.stdout)

    def test_real_cli_reimport_retains_attempt_without_fabricating_observation(self):
        raw_before = {str(p.relative_to(self.capture)): p.read_bytes()
                      for p in self.capture.rglob('*') if p.is_file()}
        first = self.call('import-capture', '--capture', self.capture)
        before = self.call('inspect', '--object', OBJECT)
        repeated = self.call('import-capture', '--capture', self.capture)
        after = self.call('inspect', '--object', OBJECT)
        history = self.call('history', '--object', OBJECT)['history']
        attempts = self.call('collection-history', '--object', OBJECT)['collections']
        self.assertEqual(len(history), 1, 'Import replay must not invent another service observation')
        self.assertEqual(len(attempts), 2, 'Every import attempt remains visible')
        self.assertEqual(repeated['source']['duplicate_of_run_id'], first['run_id'])
        self.assertEqual(repeated['object_count'], 0)
        for key in ('snapshot_id', 'run_id', 'observed_at', 'body'):
            self.assertEqual(before[key], after[key])
        self.assertEqual(after['body']['name'], 'Windows Privacy Pilot')
        self.assertEqual(len(after['body']['assignments']), 3)
        self.assertEqual(after['evidence_class'], 'graph_capture_unverified')
        self.assertFalse(after['source']['source_authenticity_verified'])
        self.assertEqual(raw_before, {str(p.relative_to(self.capture)): p.read_bytes()
                                     for p in self.capture.rglob('*') if p.is_file()})

    def test_concurrent_reimport_has_one_published_observation_and_all_attempts(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            receipts = list(pool.map(lambda _: WorkbenchStore(self.store.root).import_capture(self.capture), range(4)))
        self.assertEqual(len(self.store.history(OBJECT)), 1)
        self.assertEqual(len(self.store.collection_history(OBJECT)), 4)
        self.assertEqual(sum(r['object_count'] for r in receipts), 1)
        self.assertEqual(sum('duplicate_of_run_id' in r['source'] for r in receipts), 3)
        with sqlite3.connect(self.store.path) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM observations').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM collection_runs').fetchone()[0], 4)


if __name__ == '__main__':
    unittest.main()
