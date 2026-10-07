"""Real CLI and terminal paging preserves complete selected observations."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from intune_iac.modeled_service import ModeledService
from intune_iac.synthetic import generate_estate
from intune_iac.workbench_store import WorkbenchStore

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'scripts/intune-iac.py'


class WorkbenchPagingCLITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.estate = generate_estate(seed=882, policy_count=8)
        self.ids = sorted(row['id'] for row in self.estate['truth']['policies'])
        self.store_root = self.root / 'observations'
        self.store = WorkbenchStore.create(self.store_root, self.estate['truth']['tenant_id'])
        service = ModeledService.create(self.root / 'service', self.estate['capture'], self.ids)
        self.assertEqual(self.store.collect(service)['status'], 'complete')

    def process(self, *args, input=None):
        return subprocess.run([sys.executable, '-B', str(CLI), 'workbench', *map(str, args)],
                              input=input, text=True, capture_output=True, timeout=20,
                              env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))

    def call(self, *args):
        result = self.process(*args)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return json.loads(result.stdout)

    def test_overview_pages_have_exact_total_continuation_and_complete_bodies(self):
        observed = []
        full = self.call('overview', '--root', self.store_root)
        full_by_id = {row['object_id']: row for row in full['objects']}
        for offset in range(0, 8, 2):
            page = self.call('overview', '--root', self.store_root, '--limit', 2, '--offset', offset)
            meta = page['pagination']
            self.assertEqual(meta['total_objects'], 8)
            self.assertEqual(meta['returned_objects'], 2)
            self.assertEqual(meta['offset'], offset)
            self.assertEqual(meta['has_more'], offset < 6)
            self.assertEqual(meta['next_offset'], offset + 2 if offset < 6 else None)
            self.assertEqual([row['object_id'] for row in page['objects']], self.ids[offset:offset + 2])
            for row in page['objects']:
                self.assertEqual(row['body'], full_by_id[row['object_id']]['body'])
                self.assertEqual(row['relationships'], full_by_id[row['object_id']]['relationships'])
                self.assertEqual(row['dictionary'], full_by_id[row['object_id']]['dictionary'])
            observed.extend(row['object_id'] for row in page['objects'])
        self.assertEqual(observed, self.ids)

    def test_search_matches_global_ids_before_paging(self):
        exact = self.call('search', '--root', self.store_root, '--query', self.ids[-1], '--limit', 1)
        self.assertEqual([row['object_id'] for row in exact['objects']], [self.ids[-1]])
        self.assertEqual(exact['pagination']['total_objects'], 1)
        self.assertFalse(exact['pagination']['has_more'])
        broad = self.call('search', '--root', self.store_root, '--query', 'Privacy', '--limit', 2, '--offset', 6)
        self.assertEqual([row['object_id'] for row in broad['objects']], self.ids[6:])
        self.assertEqual(broad['pagination']['total_objects'], 8)
        setting = self.estate['truth']['policies'][0]['settings']['settings'][0]['settingInstance']['settingDefinitionId']
        by_setting = self.call('search', '--root', self.store_root, '--query', setting, '--limit', 3)
        self.assertEqual(by_setting['pagination']['total_objects'], 8)
        self.assertEqual(len(by_setting['objects']), 3)

    def test_dictionary_health_and_queue_declare_scope(self):
        selected = self.call('dictionary', '--root', self.store_root, '--object', self.ids[-1])
        self.assertEqual(selected['observation_scope'], {'kind': 'object', 'object_id': self.ids[-1]})
        self.assertTrue(all(use['object_id'] == self.ids[-1] for entry in selected['entries'] for use in entry['actual_uses']))
        page = self.call('dictionary', '--root', self.store_root, '--limit', 2, '--offset', 2)
        self.assertEqual(page['observation_scope']['pagination']['total_objects'], 8)
        self.assertEqual(page['observation_scope']['pagination']['returned_objects'], 2)
        health = self.call('health', '--root', self.store_root, '--limit', 2)
        self.assertEqual(health['pagination']['total_objects'], 8)
        self.assertEqual(len(health['objects']), 2)
        queue = self.call('queue', '--root', self.store_root, '--limit', 2, '--offset', 8)
        self.assertEqual(queue['findings'], [])
        self.assertEqual(queue['pagination']['total_objects'], 8)
        self.assertEqual(queue['findings_scope'], 'observation_page')

    def test_terminal_navigation_selected_dictionary_and_safe_invalid_page(self):
        result = self.process('terminal', '--root', self.store_root,
                              input=f'overview 2 0\nnext\nprevious\noverview 0\nnext\nsearch-page 2 0 Privacy\nnext\nselect {self.ids[-1]}\nsettings\ndictionary\nback\ndictionary-page 2 6\nnext\nqueue 2 8\nquit\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('workbench_query_invalid', result.stdout)
        self.assertIn('end_of_observation_pages', result.stdout)
        self.assertIn('"total_objects": 8', result.stdout)
        self.assertIn('"offset": 2', result.stdout)
        self.assertIn('"kind": "object"', result.stdout)
        self.assertNotIn('Traceback', result.stdout + result.stderr)
        self.assertNotIn('no_complete_observations', result.stdout)

    def test_bad_page_arguments_and_object_page_mixture_reject(self):
        for args in [('overview', '--limit', 0), ('search', '--limit', 1001),
                     ('dictionary', '--offset', -1), ('health', '--object', self.ids[0], '--limit', 2),
                     ('dictionary', '--object', self.ids[0], '--limit', 2)]:
            with self.subTest(args=args):
                result = self.process(*args, '--root', self.store_root)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('"status": "error"', result.stderr)


if __name__ == '__main__': unittest.main()
