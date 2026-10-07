"""Independent store navigation expectations, including an actual 16 MiB estate."""
import copy
import hashlib
import json
import sqlite3
import unittest
from unittest.mock import patch

from intune_iac.io import AppError, digest
from intune_iac import workbench_store as store_module
from plugin_tests import test_workbench_capture_store as fixtures


class WorkbenchCapacityTests(unittest.TestCase):
    setUp = fixtures.CaptureStoreTests.setUp
    batch = fixtures.CaptureStoreTests.batch
    import_batch = fixtures.CaptureStoreTests.import_batch

    def observed(self, count=3, padded=False):
        expected = {}
        for index in range(count):
            oid = '90000000-0000-4000-8000-%012x' % (index+1)
            batch = self.batch()
            batch['object_id'] = oid
            batch['scope']['object_ids'] = [oid]
            for collection in batch['collections']:
                if collection['owner_id'] is not None: collection['owner_id'] = oid
            batch['source']['raw_observed']['policy'].update(id=oid, name='Policy %04d' % (index+1))
            batch['body']['name'] = 'Policy %04d' % (index+1)
            if padded:
                batch['body']['description'] = 'b' * 500000
                batch['source']['raw_observed']['policy']['description'] = 'r' * 500000
            expected[oid] = copy.deepcopy(batch['body'])
            self.assertEqual(self.import_batch(batch)['status'], 'complete')
        return expected

    def test_inspection_survives_actual_unpaged_byte_limit_and_preserves_bytes(self):
        expected = self.observed(12, padded=True)
        before = hashlib.sha256(self.store.path.read_bytes()).hexdigest()
        with self.assertRaises(AppError) as caught: self.store.overview()
        self.assertEqual(caught.exception.code, 'workbench_query_limit')
        for oid in (min(expected), max(expected)):
            value = self.store.inspect(oid)
            self.assertEqual(value['body'], expected[oid])
            self.assertEqual(value['coverage'], 'complete')
            self.assertFalse(value['execution_authorized'])
        page = self.store.overview(limit=1, offset=11)
        self.assertEqual(page['objects'][0]['body'], expected[max(expected)])
        self.assertEqual(page['pagination']['total_objects'], 12)
        self.assertEqual(hashlib.sha256(self.store.path.read_bytes()).hexdigest(), before)

    def test_pages_cover_literal_ids_once_and_do_not_claim_complete(self):
        expected = self.observed(5)
        seen = []
        for offset in (0, 2, 4):
            page = self.store.overview(now=100, limit=2, offset=offset)
            seen.extend(row['object_id'] for row in page['objects'])
            self.assertEqual(page['pagination'], {
                'total_objects':5, 'returned_objects':min(2,5-offset), 'limit':2, 'offset':offset,
                'has_more':offset<4, 'next_offset':offset+2 if offset<4 else None,
                'complete':False, 'scope':'page'})
            self.assertEqual(page['freshness'], 'fresh')
        self.assertEqual(seen, sorted(expected))
        beyond = self.store.overview(limit=2, offset=99)
        self.assertEqual(beyond['objects'], [])
        self.assertFalse(beyond['pagination']['has_more'])
        self.assertFalse(beyond['pagination']['complete'])
        all_rows = self.store.overview(now=100)
        self.assertTrue(all_rows['pagination']['complete'])
        self.assertEqual(all_rows['pagination']['scope'], 'unpaged')

    def test_scoped_inspect_equals_complete_overview_with_last_good_and_pending(self):
        self.import_batch(self.batch(self.ids[0], 100))
        self.import_batch(self.batch(self.ids[0], 101, 'denied'))
        self.import_batch(self.batch(self.ids[1], 102, 'partial'))
        with patch.object(store_module.time, 'time', return_value=103):
            overview = self.store.overview()
            for expected in overview['objects'] + overview['pending_observations']:
                self.assertEqual(self.store.inspect(expected['object_id']), expected)
        self.assertEqual(self.store.inspect(self.ids[0])['last_success']['run_id'], 1)
        self.assertEqual(self.store.inspect(self.ids[0])['last_attempt']['status'], 'denied')
        self.assertIsNone(self.store.inspect(self.ids[1])['body'])
        self.assertIsNone(self.store.inspect(self.ids[1])['last_success'])

    def test_off_page_denial_keeps_estate_stale_and_visible_object_fresh(self):
        a, b = sorted(self.ids[:2])
        self.import_batch(self.batch(a, 100))
        self.import_batch(self.batch(b, 101))
        self.import_batch(self.batch(b, 102, 'denied'))
        self.import_batch(self.batch(a, 103))
        page = self.store.overview(now=104, limit=1)
        self.assertEqual([o['object_id'] for o in page['objects']], [a])
        self.assertEqual(page['objects'][0]['freshness'], 'fresh')
        self.assertEqual(page['freshness'], 'stale')
        self.assertEqual(page['last_attempt']['status'], 'complete')

    def test_pending_and_complete_share_one_order_count_and_global_class(self):
        self.store.collect(self.service, observed_at=100)
        pending_id = 'ffffffff-ffff-4fff-8fff-ffffffffffff'
        batch = self.batch(self.ids[0], 101, 'denied')
        batch['object_id'] = pending_id
        batch['scope']['object_ids'] = [pending_id]
        for item in batch['collections']:
            if item['owner_id'] is not None: item['owner_id'] = pending_id
        self.import_batch(batch)
        page = self.store.overview(now=102, limit=3)
        self.assertEqual(page['pending_observations'], [])
        self.assertEqual(page['pagination']['total_objects'], 4)
        self.assertEqual(page['evidence_class'], 'mixed_observations')
        self.assertEqual(page['freshness'], 'stale')
        end = self.store.overview(now=102, limit=3, offset=3)
        self.assertEqual(end['objects'], [])
        self.assertEqual(end['pending_observations'][0]['object_id'], pending_id)
        self.assertEqual(end['pending_observations'][0]['freshness'], 'unknown')

    def test_global_search_filters_before_paging_and_reaches_last_object(self):
        expected = self.observed(12, padded=True)
        found = self.store.overview(query='POLICY 0012', limit=1)
        self.assertEqual(found['objects'][0]['body'], expected[max(expected)])
        self.assertEqual(found['pagination']['total_objects'], 1)
        self.assertEqual(found['total_inventory_objects'], 12)
        self.assertTrue(found['pagination']['complete'])
        self.assertEqual(self.store.overview(query=max(expected))['objects'][0]['object_id'], max(expected))
        no_match = self.store.overview(query='missing object', limit=1)
        self.assertEqual(no_match['objects'], [])
        self.assertEqual(no_match['pagination']['total_objects'], 0)
        self.assertTrue(no_match['pagination']['complete'])

    def test_search_preserves_unicode_casefold_and_setting_identifier(self):
        batch = self.batch()
        batch['body']['name'] = 'Straße observed'
        batch['body']['settings']['settings'] = [{'settingDefinitionId':'Vendor.Unique.Identifier'}]
        self.import_batch(batch)
        for query in ('STRASSE', 'vendor.unique.identifier', self.ids[0].upper()):
            with self.subTest(query=query):
                self.assertEqual(self.store.overview(query=query, limit=1)['objects'][0]['object_id'], self.ids[0])

    def test_search_includes_pending_name_without_claiming_complete_observation(self):
        self.import_batch(self.batch(status='denied'))
        result = self.store.overview(query='original RAW', limit=1)
        self.assertEqual(result['objects'], [])
        self.assertEqual(result['pending_observations'][0]['object_id'], self.ids[0])
        self.assertEqual(result['freshness'], 'unknown')
        self.assertTrue(result['pagination']['complete'])

    def test_search_treats_wildcards_literally_and_does_not_search_arbitrary_values(self):
        batch = self.batch()
        batch['body']['name'] = 'Visible policy'
        batch['body']['description'] = 'DESCRIPTION_ONLY_CANARY'
        batch['body']['settings']['settings'] = [{'settingDefinitionId':'public.identifier','value':'HIDDEN_VALUE_CANARY'}]
        self.import_batch(batch)
        for query in ('%', '_', 'DESCRIPTION_ONLY_CANARY', 'HIDDEN_VALUE_CANARY', 'Original raw name'):
            with self.subTest(query=query):
                result = self.store.overview(query=query, limit=1)
                self.assertEqual(result['objects'], [])
                self.assertEqual(result['pagination']['total_objects'], 0)
                self.assertEqual(result['total_inventory_objects'], 1)

    def test_legacy_v1_exact_inspect_and_search_preserve_failed_attempt_without_writes(self):
        legacy = fixtures.CaptureStoreTests.legacy(self)
        oid, body = self.ids[0], self.bodies[self.ids[0]]
        snapshot = digest({'tenant_id':self.tenant, 'object_id':oid, 'body':body})
        with sqlite3.connect(legacy.path) as db:
            db.execute('INSERT INTO collection_runs VALUES(?,?,?,?,?,?,?,?,?)', (1,self.tenant,90,90,91,'complete','complete',None,1))
            db.execute('INSERT INTO collection_runs VALUES(?,?,?,?,?,?,?,?,?)', (2,self.tenant,100,100,101,'denied','denied','denied',0))
            db.execute('INSERT INTO snapshots VALUES(?,?,?,?)', (snapshot,self.tenant,oid,json.dumps(body)))
            db.execute('INSERT INTO observations VALUES(?,?,?,?,?,?,?)', (1,1,snapshot,self.tenant,oid,90,'{}'))
        before = legacy.path.read_bytes()
        found = legacy.overview(query=oid.upper(), limit=1)
        self.assertEqual(found['objects'][0]['body'], body)
        inspected = legacy.inspect(oid)
        self.assertEqual(inspected['body'], body)
        self.assertEqual(inspected['last_attempt']['status'], 'denied')
        self.assertEqual(inspected['last_success']['run_id'], 1)
        self.assertEqual(inspected['freshness'], 'stale')
        self.assertEqual(legacy.path.read_bytes(), before)

    def test_metadata_scan_and_sql_work_have_finite_fail_closed_budgets(self):
        self.observed(12)
        before = self.store.path.read_bytes()
        with patch.object(store_module, 'MAX_QUERY_SCAN_BYTES', 1):
            with self.assertRaises(AppError) as caught: self.store.overview(query='missing', limit=1)
            self.assertEqual(caught.exception.code, 'workbench_query_limit')
        with patch.object(store_module, 'MAX_QUERY_STEPS', 0):
            with self.assertRaises(AppError) as caught: self.store.overview(limit=1)
            self.assertEqual(caught.exception.code, 'workbench_query_limit')
        self.assertEqual(self.store.path.read_bytes(), before)
        self.assertEqual(self.store.overview(limit=1)['pagination']['total_objects'], 12)

    def test_paging_does_not_weaken_byte_or_row_limits(self):
        self.observed(12, padded=True)
        with self.assertRaises(AppError) as caught: self.store.overview(limit=12)
        self.assertEqual(caught.exception.code, 'workbench_query_limit')
        for kwargs in ({'limit':0}, {'limit':1001}, {'limit':True}, {'offset':-1}, {'offset':True}, {'query':False}):
            with self.subTest(kwargs=kwargs), self.assertRaises(AppError): self.store.overview(**kwargs)
        with patch.object(store_module, 'MAX_QUERY_ROWS', 1):
            with self.assertRaises(AppError) as caught: self.store.overview()
            self.assertEqual(caught.exception.code, 'workbench_query_limit')

    def test_missing_exact_object_is_missing_even_when_full_overview_is_too_large(self):
        self.observed(12, padded=True)
        with self.assertRaises(AppError) as caught: self.store.inspect('ffffffff-ffff-4fff-8fff-ffffffffffff')
        self.assertEqual(caught.exception.code, 'workbench_object_missing')


if __name__ == '__main__': unittest.main()
