"""Persistent synthetic observations: independent expected estate and failures."""
import copy
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from intune_iac.io import AppError, write_json
from intune_iac.modeled_service import BASE, ModeledService
from intune_iac.synthetic import generate_estate
from intune_iac.workbench_store import WorkbenchStore


class WorkbenchStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.estate = generate_estate(seed=104, policy_count=3)
        self.ids = [p['id'] for p in self.estate['truth']['policies']]
        self.tenant = self.estate['truth']['tenant_id']
        self.service = ModeledService.create(self.root/'service',self.estate['capture'],self.ids)
        self.store = WorkbenchStore.create(self.root/'store',self.tenant)
        self.expected = {p['id']:{k:v for k,v in p.items() if k != 'id'} for p in self.estate['truth']['policies']}

    def collect(self, **kw):
        return self.store.collect(self.service,observed_at=kw.pop('observed_at',100),**kw)

    def change(self):
        body = copy.deepcopy(self.expected[self.ids[0]]); body['name'] = 'Intentional maintenance'
        response = self.service.request('PATCH',BASE+'/'+self.ids[0],tenant_id=self.tenant,body=body,if_match='1')
        self.assertEqual(response['status'],200)
        return body

    def test_independent_truth_and_restart_preserve_all_values(self):
        result = self.collect(); self.assertEqual(result['status'],'complete')
        reopened = WorkbenchStore(self.store.root)
        for oid, body in self.expected.items():
            inspected = reopened.inspect(oid)
            self.assertEqual(inspected['body'],body)
            self.assertIsNone(inspected['changed_at'])
            self.assertEqual(inspected['attribution'],'unknown')
        self.assertEqual([r['method'] for r in self.service.snapshot()['requests']],['GET','GET'])

    def test_collector_and_queries_never_mutate_service_objects(self):
        before = copy.deepcopy(self.service.snapshot()['current'])
        self.collect(); request_count = len(self.service.snapshot()['requests'])
        self.store.overview(); self.store.inspect(self.ids[0]); self.store.history(self.ids[0]); self.store.operations()
        self.assertEqual(len(self.service.snapshot()['requests']),request_count)
        self.assertEqual(self.service.snapshot()['current'],before)
        self.assertFalse(any(r['mutation_committed'] for r in self.service.snapshot()['requests']))

    def test_denied_partial_and_interrupted_publish_retain_last_good(self):
        self.collect()
        for fault in ('deny','throttle','partial','missing-coverage','before-publish','cross-origin','loop'):
            with self.subTest(fault=fault):
                result = self.collect(observed_at=110,fault=fault)
                self.assertNotEqual(result['status'],'complete')
                overview = self.store.overview(now=120)
                self.assertEqual(len(overview['objects']),3)
                self.assertEqual(overview['last_success']['run_id'],1)
                self.assertEqual(len(self.store.history(self.ids[0])),1)
                self.assertEqual(self.store.inspect(self.ids[0])['body'],self.expected[self.ids[0]])

    def test_failed_first_read_is_unknown_not_empty_complete(self):
        self.collect(fault='deny')
        overview = self.store.overview(now=100)
        self.assertEqual(overview['objects'],[])
        self.assertIsNone(overview['last_success'])
        self.assertEqual(overview['coverage'],'denied')
        self.assertEqual(overview['freshness'],'unknown')

    def test_snapshots_deduplicate_without_losing_attempt_or_observation_times(self):
        self.collect(observed_at=100); self.collect(observed_at=120)
        history = self.store.history(self.ids[0])
        self.assertEqual(len(history),2)
        self.assertEqual(history[0]['snapshot_id'],history[1]['snapshot_id'])
        self.assertNotEqual(history[0]['observed_at'],history[1]['observed_at'])
        with sqlite3.connect(self.store.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM snapshots').fetchone()[0],3)
            self.assertEqual(db.execute('SELECT count(*) FROM observations').fetchone()[0],6)

    def test_out_of_order_collection_does_not_replace_newer_observation(self):
        self.collect(observed_at=200)
        self.change(); self.collect(observed_at=100)
        overview = self.store.overview(now=220)
        self.assertEqual(overview['last_attempt']['run_id'],2)
        self.assertEqual(overview['last_success']['run_id'],1)
        self.assertEqual(self.store.inspect(self.ids[0])['body'],self.expected[self.ids[0]])
        self.assertEqual([row['run_id'] for row in self.store.history(self.ids[0])],[2,1])

    def test_history_comparison_and_cross_object_rejection(self):
        self.collect(); changed = self.change(); self.collect(observed_at=200)
        history = self.store.history(self.ids[0])
        compared = self.store.compare(self.ids[0],history[0]['snapshot_id'],history[1]['snapshot_id'])
        self.assertEqual(compared['changes'],[{'field':'name','before':self.expected[self.ids[0]]['name'],'after':changed['name']}])
        with self.assertRaises(AppError): self.store.compare(self.ids[1],history[0]['snapshot_id'],history[1]['snapshot_id'])

    def test_typed_relationships_and_source_provenance(self):
        self.collect(source={'repository_path':'components/intune','atmos_stack':'synthetic','ownership':'unknown'})
        inspected = self.store.inspect(self.ids[0])
        kinds = {edge['relation'] for edge in inspected['relationships']}
        self.assertTrue({'assignment','exclusion','filter','setting','source_repository_path','source_atmos_stack'} <= kinds, kinds)
        self.assertEqual(inspected['source']['ownership'],'unknown')
        assignments = inspected['body']['assignments']
        self.assertEqual(assignments,self.expected[self.ids[0]]['assignments'])

    def test_reporting_denominators_and_unknown_endpoint(self):
        self.collect(deployment={'targeted':100,'reporting':8,'successful':8})
        health = self.store.overview(now=101)['health']
        self.assertEqual(health['reporting_success_percent'],100)
        self.assertEqual(health['targeted_success_percent'],8)
        self.assertEqual(health['unknown_or_stale'],92)
        self.assertFalse(health['rollout_ready'])
        self.assertEqual(health['endpoint_outcome'],'unknown')
        stale = self.store.overview(now=10000)['health']
        self.assertEqual(stale['report_freshness'],'stale')
        self.assertEqual(stale['unknown_or_stale'],100)

    def test_zero_denominators_do_not_invent_percentages(self):
        self.collect(deployment={'targeted':0,'reporting':0,'successful':0})
        health = self.store.overview(now=100)['health']
        self.assertIsNone(health['reporting_success_percent']); self.assertIsNone(health['targeted_success_percent'])

    def test_inconsistent_counts_fail_without_publishing(self):
        self.collect()
        for values in ({'targeted':7,'reporting':8,'successful':8}, {'targeted':100,'reporting':8,'successful':9},
                       {'targeted':100,'reporting':8,'successful':True}, {'targeted':100,'reporting':8,'successful':8,'failed':1}):
            result = self.collect(deployment=values)
            self.assertEqual(result['status'],'failed')
        self.assertEqual(len(self.store.history(self.ids[0])),1)

    def test_wrong_tenant_rejected_and_attempt_retained(self):
        other = generate_estate(seed=105,policy_count=1)
        other_service = ModeledService.create(self.root/'other',other['capture'],[other['truth']['policies'][0]['id']])
        result = self.store.collect(other_service)
        self.assertEqual(result['error_code'],'workbench_wrong_tenant')
        self.assertEqual(self.store.overview()['objects'],[])
        with self.assertRaises(AppError): WorkbenchStore(self.store.root,other['truth']['tenant_id'])

    def test_missing_assignments_cannot_be_observed_as_empty(self):
        original = self.service.request
        def omitted(*args,**kwargs):
            response = original(*args,**kwargs)
            response['body']['value'][0].pop('assignments')
            return response
        with patch.object(self.service,'request',side_effect=omitted): result = self.collect()
        self.assertEqual(result['status'],'partial')
        self.assertEqual(self.store.overview()['objects'],[])

    def test_mixed_revision_and_duplicate_identity_do_not_publish(self):
        original = self.service.request; calls = [0]
        def mixed(*args,**kwargs):
            response = original(*args,**kwargs); calls[0] += 1
            if calls[0] == 2: response['revision'] += 1
            return response
        with patch.object(self.service,'request',side_effect=mixed): self.assertNotEqual(self.collect()['status'],'complete')
        self.assertEqual(self.store.overview()['objects'],[])

    def test_complete_empty_batch_records_deletion_without_erasing_history(self):
        self.collect()
        for revision,oid in enumerate(self.ids,1):
            self.assertEqual(self.service.request('DELETE',BASE+'/'+oid,tenant_id=self.tenant,if_match=str(revision))['status'],204)
        self.collect(observed_at=200)
        self.assertEqual(self.store.overview()['objects'],[])
        self.assertEqual(len(self.store.history(self.ids[0])),1)
        with self.assertRaises(AppError): self.store.inspect(self.ids[0])

    def test_private_paths_hardlinks_and_symlinks_rejected(self):
        alias = self.root/'linked'; alias.symlink_to(self.store.root)
        with self.assertRaises(AppError): WorkbenchStore(alias)
        os.link(self.store.path,self.root/'hardlink.sqlite')
        with self.assertRaises(AppError): WorkbenchStore(self.store.root)

    def test_world_readable_database_rejected(self):
        self.store.path.chmod(0o644)
        with self.assertRaises(AppError): WorkbenchStore(self.store.root)

    def test_unsupported_schema_rejected(self):
        with sqlite3.connect(self.store.path) as db: db.execute('PRAGMA user_version=99')
        with self.assertRaises(AppError): WorkbenchStore(self.store.root)

    def test_foreign_keys_enabled_on_store_connection(self):
        with self.store._connection(True) as db:
            self.assertEqual(db.execute('PRAGMA foreign_keys').fetchone()[0],1)
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute('INSERT INTO deployments VALUES(999,?)',('{}',))

    def test_operations_append_and_secret_fields_rejected(self):
        self.store.record_operation('operation-1',{'object_id':self.ids[0],'status':'prepared'})
        self.store.record_operation('operation-1',{'object_id':self.ids[0],'status':'uncertain'})
        self.assertEqual([r['status'] for r in self.store.operations(self.ids[0])],['prepared','uncertain'])
        with self.assertRaises(AppError): self.store.record_operation('operation-2',{'client_secret':'synthetic-canary'})
        self.assertNotIn(b'synthetic-canary',self.store.path.read_bytes())
        with self.assertRaises(AppError): self.collect(source={'access_token':'synthetic-canary'})

    def test_stale_unknown_and_future_observation_are_not_fresh(self):
        self.assertEqual(self.store.overview(now=100)['freshness'],'unknown')
        self.collect(observed_at=200)
        self.assertEqual(self.store.overview(now=100)['freshness'],'stale')
        self.assertEqual(self.store.overview(now=400,max_age_seconds=100)['freshness'],'stale')

    def test_failed_attempt_marks_recent_last_good_stale(self):
        self.collect(); self.collect(observed_at=101,fault='deny')
        overview = self.store.overview(now=102,max_age_seconds=3600)
        self.assertEqual(overview['freshness'],'stale')
        self.assertTrue(overview['retained_last_good'])
        self.assertEqual(overview['age_seconds'],2)

    def test_actual_service_provenance_and_dictionary_are_explicit(self):
        self.collect(source={'service_revision':'invented'})
        inspected = self.store.inspect(self.ids[0])
        self.assertEqual(inspected['source']['service_revision'],1)
        self.assertEqual(inspected['source']['service_root'],str(self.service.root))
        self.assertTrue(inspected['dictionary'])
        self.assertEqual(inspected['dictionary'][0]['meaning'],'unknown')
        self.assertEqual(inspected['ownership'],'unknown')
        self.assertTrue(all(v == 'observed_complete' for v in inspected['field_accounting'].values()))

    def test_backup_restore_reopens_history_and_retains_original(self):
        self.collect(); self.change(); self.collect(observed_at=200)
        self.store.record_operation('one',{'object_id':self.ids[0],'status':'uncertain'})
        receipt = self.store.backup(self.root/'backup.sqlite3')
        self.assertEqual(len(receipt['sha256']),64)
        original = self.store.path.read_bytes()
        restored = WorkbenchStore.restore(self.root/'backup.sqlite3',self.root/'restored',self.tenant)
        self.assertEqual(restored.history(self.ids[0]),self.store.history(self.ids[0]))
        self.assertEqual(restored.operations(),self.store.operations())
        self.assertEqual(self.store.path.read_bytes(),original)
        self.assertEqual((self.root/'backup.sqlite3').stat().st_mode & 0o777,0o600)
        with self.assertRaises(AppError): self.store.backup(self.root/'backup.sqlite3')

    def test_corrupt_backup_and_wrong_tenant_are_rejected(self):
        receipt = self.store.backup(self.root/'backup.sqlite3')
        other = generate_estate(seed=105,policy_count=1)['truth']['tenant_id']
        with self.assertRaises(AppError): WorkbenchStore.restore(receipt['path'],self.root/'wrong',other)
        self.assertFalse((self.root/'wrong').exists())
        broken = self.root/'broken.sqlite3'; broken.write_bytes(b'not sqlite'); broken.chmod(0o600)
        with self.assertRaises(AppError): WorkbenchStore.restore(broken,self.root/'broken-restore')
        self.assertFalse((self.root/'broken-restore').exists())

    def test_dropped_final_page_and_false_empty_batch_cannot_publish(self):
        self.collect()
        original = self.service.request
        for empty in (False, True):
            def truncated(*args,**kwargs):
                response = original(*args,**kwargs)
                response['body'].pop('@odata.nextLink',None)
                if empty: response['body']['value'] = []
                return response
            with patch.object(self.service,'request',side_effect=truncated): result = self.collect(observed_at=110)
            self.assertEqual(result['status'],'partial')
            self.assertEqual(result['error_code'],'workbench_missing_coverage')
            self.assertEqual(len(self.store.overview()['objects']),3)
            self.assertEqual(len(self.store.history(self.ids[0])),1)

    def test_malformed_assignment_is_terminal_partial_not_stuck_collecting(self):
        self.collect()
        body = copy.deepcopy(self.expected[self.ids[0]]); body['assignments'] = [None]
        self.service.request('PATCH',BASE+'/'+self.ids[0],tenant_id=self.tenant,body=body,if_match='1')
        result = self.collect(observed_at=110)
        self.assertEqual(result['status'],'partial')
        self.assertIsNotNone(result['completed_at'])
        self.assertEqual(self.store.inspect(self.ids[0])['body'],self.expected[self.ids[0]])

    def test_reports_without_outcome_details_remain_unknown(self):
        self.collect(deployment={'targeted':100,'reporting':100,'successful':0})
        health = self.store.overview(now=100)['health']
        self.assertEqual(health['unknown_or_stale'],100)
        self.assertEqual(health['reporting_outcome_unknown'],100)
        self.assertIsNone(health['failed']); self.assertIsNone(health['pending'])

    def test_history_and_operation_explicit_pagination_and_default_limit(self):
        self.collect(observed_at=100); self.collect(observed_at=101); self.collect(observed_at=102)
        for state in ('prepared','approved','uncertain'):
            self.store.record_operation('one',{'object_id':self.ids[0],'status':state})
        self.assertEqual([r['run_id'] for r in self.store.history(self.ids[0],limit=1,offset=1)],[2])
        self.assertEqual([r['status'] for r in self.store.operations(limit=1,offset=1)],['approved'])
        with patch('intune_iac.workbench_store.MAX_QUERY_ROWS',2):
            with self.assertRaises(AppError): self.store.history(self.ids[0])
            with self.assertRaises(AppError): self.store.operations()
        for bad in (-1,True,1001):
            with self.assertRaises(AppError): self.store.history(self.ids[0],limit=bad)

    def test_interrupted_collection_attempt_remains_visible_and_last_good_stale(self):
        self.collect()
        with self.store._connection(True) as db, db:
            db.execute('INSERT INTO collection_runs(tenant_id,started_at,observed_at,status,coverage) VALUES(?,?,?,?,?)',
                (self.tenant,101,101,'collecting','unknown'))
        reopened = WorkbenchStore(self.store.root)
        overview = reopened.overview(now=102)
        self.assertEqual(overview['last_attempt']['status'],'collecting')
        self.assertIsNone(overview['last_attempt']['completed_at'])
        self.assertTrue(overview['retained_last_good']); self.assertEqual(overview['freshness'],'stale')
        self.assertEqual(len(overview['objects']),3)

    def test_valid_sqlite_with_incomplete_application_schema_cannot_restore(self):
        backup = self.root/'incomplete.sqlite3'
        with sqlite3.connect(backup) as db:
            db.execute('CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
            db.execute('INSERT INTO metadata VALUES(?,?)',('tenant_id',self.tenant))
            db.execute('PRAGMA user_version=1')
        backup.chmod(0o600)
        with self.assertRaises(AppError) as error: WorkbenchStore.restore(backup,self.root/'restored-invalid')
        self.assertEqual(error.exception.code,'workbench_schema_invalid')
        self.assertFalse((self.root/'restored-invalid').exists())

    def test_naive_time_and_boolean_time_are_rejected(self):
        for timestamp in ('2026-10-05T12:00:00',True,float('nan')):
            with self.subTest(timestamp=timestamp), self.assertRaises(AppError): self.collect(observed_at=timestamp)


if __name__ == '__main__': unittest.main()
