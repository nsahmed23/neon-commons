"""Scoped unverified capture publication, explicit migration and inert lineage."""
import copy
from concurrent.futures import ThreadPoolExecutor
import threading
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch

from intune_iac.io import AppError, digest
from intune_iac.modeled_service import ModeledService
from intune_iac.synthetic import generate_estate
from intune_iac import workbench_store as module
from intune_iac.workbench_store import WorkbenchStore


class CaptureStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        estate = generate_estate(seed=104, policy_count=3)
        self.tenant = estate['truth']['tenant_id']
        self.bodies = {p['id']:{k:v for k,v in p.items() if k != 'id'} for p in estate['truth']['policies']}
        self.ids = list(self.bodies)
        self.service = ModeledService.create(self.root/'service',estate['capture'],self.ids)
        self.store = WorkbenchStore.create(self.root/'store',self.tenant)

    def batch(self, oid=None, observed_at=100, status='complete'):
        oid = oid or self.ids[0]
        source = {'evidence_class':'graph_capture_unverified','tenant_assurance':'caller_asserted',
            'source_authenticity_verified':False,'provider_qualified':False,'execution_authorized':False,
            'artifacts':{'export_sha256':'1'*64},'mapping_blockers':[],
            'raw_observed':{'policy':{'id':oid,'name':'Original raw name'},'settings':[], 'assignments':[]}}
        collections = [{'kind':kind,'owner_id':None if kind=='policies' else oid,'coverage':'complete','reason':None,'page_count':1}
            for kind in ('policies','settings','assignments')]
        body = copy.deepcopy(self.bodies[oid]) if status == 'complete' else None
        if status in ('partial','denied'):
            collections[-1].update(coverage='access_denied' if status=='denied' else 'partial',reason='access_denied' if status=='denied' else 'missing_page')
        if status == 'unsupported': source['mapping_blockers'] = [{'code':'unsupported_setting_shape'}]
        return {'tenant_id':self.tenant,'object_id':oid,'observed_at':float(observed_at),'status':status,
            'collections':collections,'body':body,'source':source,'scope':{'kind':'policy','object_ids':[oid]},'capture_sha256':digest(source)}

    def import_batch(self, batch):
        adapter = types.SimpleNamespace(load_capture=lambda path,tenant_id:copy.deepcopy(batch))
        with patch.dict(sys.modules,{'intune_iac.capture_adapter':adapter}): return self.store.import_capture(self.root/'capture')

    def legacy(self):
        root = self.root/'legacy';root.mkdir(mode=0o700);path=root/'observations.sqlite3'
        path.touch(mode=0o600)
        with sqlite3.connect(path) as db:
            db.executescript(module._SCHEMA_SQL_V1)
            db.execute('INSERT INTO metadata VALUES(?,?)',('tenant_id',self.tenant))
        return WorkbenchStore(root)

    def test_new_store_is_v2_and_import_preserves_unselected_objects(self):
        self.assertEqual(self.store.schema_version,2)
        self.store.collect(self.service,observed_at=90)
        run = self.import_batch(self.batch())
        self.assertEqual(run['status'],'complete')
        self.assertEqual(len(self.store.overview(now=100)['objects']),3)
        captured=self.store.inspect(self.ids[0])
        self.assertEqual(captured['evidence_class'],'graph_capture_unverified')
        self.assertEqual(captured['source']['tenant_assurance'],'caller_asserted')
        self.assertNotIn('service_kind',captured['source'])
        self.assertEqual(self.store.inspect(self.ids[1])['source']['service_kind'],'ModeledService')

    def test_failed_and_unsupported_captures_retain_body_and_raw_evidence(self):
        self.import_batch(self.batch())
        for index,status in enumerate(('denied','partial','unsupported'),1):
            run=self.import_batch(self.batch(observed_at=100+index,status=status))
            self.assertEqual(run['status'],status)
            self.assertEqual(self.store.inspect(self.ids[0])['body'],self.bodies[self.ids[0]])
            self.assertEqual(self.store.inspect(self.ids[0])['freshness'],'stale')
            detail=self.store.collection_detail(run['run_id'])
            self.assertEqual(detail['source']['raw_observed']['policy']['id'],self.ids[0])
            self.assertEqual(len(detail['collections']),3)
        self.assertEqual(len(self.store.history(self.ids[0])),1)
        self.assertEqual(len(self.store.collection_history(self.ids[0])),4)

    def test_failed_capture_for_one_policy_does_not_stale_other_current_policy(self):
        self.import_batch(self.batch(self.ids[0],100));self.import_batch(self.batch(self.ids[1],101))
        self.import_batch(self.batch(self.ids[0],102,'denied'))
        rows={o['object_id']:o for o in self.store.overview(now=103)['objects']}
        self.assertEqual(rows[self.ids[0]]['freshness'],'stale')
        self.assertEqual(rows[self.ids[1]]['freshness'],'fresh')

    def test_import_times_control_current_and_identical_body_deduplicates(self):
        original=self.batch(observed_at=200);self.import_batch(original)
        delayed=self.batch(observed_at=100);delayed['body']['name']='Delayed record'
        self.import_batch(delayed);self.import_batch(self.batch(observed_at=210))
        self.assertEqual(self.store.inspect(self.ids[0])['body']['name'],self.bodies[self.ids[0]]['name'])
        history=self.store.history(self.ids[0]);self.assertEqual(len(history),3)
        self.assertEqual(history[1]['snapshot_id'],history[2]['snapshot_id'])
        self.assertNotEqual(history[0]['snapshot_id'],history[1]['snapshot_id'])

    def test_wrong_tenant_scope_and_authority_cannot_enter_store(self):
        variants=[]
        bad=self.batch();bad['tenant_id']=self.ids[0];variants.append(bad)
        bad=self.batch();bad['scope']['object_ids']=[self.ids[1]];variants.append(bad)
        bad=self.batch();bad['source']['execution_authorized']=True;variants.append(bad)
        bad=self.batch();bad['source']['service_kind']='ModeledService';variants.append(bad)
        bad=self.batch();bad['collections'][-1]['owner_id']=self.ids[1];variants.append(bad)
        for batch in variants:
            with self.subTest(batch=batch),self.assertRaises(AppError):self.import_batch(batch)
        self.assertEqual(self.store.overview()['objects'],[])

    def test_unfinished_and_incomplete_capture_does_not_claim_empty_complete(self):
        run=self.import_batch(self.batch(status='partial'))
        self.assertEqual(run['status'],'partial')
        self.assertEqual(self.store.history(self.ids[0]),[])
        overview=self.store.overview(now=100)
        self.assertTrue(overview['pending_observations'])
        self.assertIsNone(overview['last_success'])

    def test_explicit_migration_backups_and_reading_v1_never_migrates(self):
        legacy=self.legacy();before=legacy.path.read_bytes()
        self.assertEqual(legacy.schema_version,1)
        legacy.overview();legacy.history(self.ids[0])
        self.assertEqual(legacy.path.read_bytes(),before)
        with self.assertRaises(AppError) as error:legacy.collect(self.service)
        self.assertEqual(error.exception.code,'workbench_migration_required')
        receipt=legacy.migrate(self.root/'v1-backup.sqlite3')
        self.assertEqual(receipt['from_version'],1);self.assertEqual(receipt['to_version'],2)
        self.assertEqual(WorkbenchStore(legacy.root).schema_version,2)
        with sqlite3.connect(self.root/'v1-backup.sqlite3') as db:self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],1)
        restored=WorkbenchStore.restore(self.root/'v1-backup.sqlite3',self.root/'restored-v1',self.tenant)
        self.assertEqual(restored.schema_version,1)

    def test_migration_failure_rolls_back_and_keeps_backup(self):
        legacy=self.legacy()
        def interrupted(db):
            db.execute(module._MIGRATION_STATEMENTS[0])
            raise RuntimeError('synthetic migration stop after DDL')
        with patch.object(module,'_migrate_v1_to_v2',side_effect=interrupted):
            with self.assertRaises(RuntimeError):legacy.migrate(self.root/'v1-backup.sqlite3')
        self.assertEqual(WorkbenchStore(legacy.root).schema_version,1)
        self.assertTrue((self.root/'v1-backup.sqlite3').is_file())

    def test_artifacts_are_tenant_bound_immutable_and_deduplicated(self):
        self.import_batch(self.batch())
        data={'description':'Observed vendor recommendation','policy':{'name':'Baseline'}}
        first=self.store.record_artifact('source_reference',None,data)
        repeated=self.store.record_artifact('source_reference',None,data)
        self.assertEqual(first['artifact_id'],repeated['artifact_id'])
        self.assertTrue(first['created']);self.assertFalse(repeated['created'])
        row=self.store.artifacts(kind='source_reference')[0]
        self.assertEqual(row['data'],data);self.assertFalse(row['cloud_authority']);self.assertFalse(row['execution_authorized'])
        self.store.record_artifact('device_evidence',self.ids[0],{'cohort':'reviewed'})
        with self.assertRaises(AppError):self.store.record_artifact('device_evidence',self.ids[1],{})
        with self.assertRaises(AppError):self.store.record_artifact('workflow_run',None,{})
        with self.assertRaises(AppError):self.store.record_artifact('schedule',None,{'tenant_id':self.ids[0]})
        with self.assertRaises(AppError):self.store.record_artifact('schedule',None,{'execution_authorized':True})
        with self.assertRaises(AppError):self.store.record_artifact('schedule',None,{'access_token':'canary'})
        self.assertEqual(len(self.store.artifacts(object_id=self.ids[0])),1)

    def test_artifact_and_collection_queries_are_bounded(self):
        self.import_batch(self.batch())
        self.import_batch(self.batch(observed_at=101))
        for i in range(2):self.store.record_artifact('schedule',None,{'run_id':i})
        self.assertEqual(len(self.store.artifacts(limit=1,offset=1)),1)
        self.assertEqual(len(self.store.collection_history(limit=1,offset=1)),1)
        with patch.object(module,'MAX_QUERY_ROWS',1):
            with self.assertRaises(AppError):self.store.artifacts()
            with self.assertRaises(AppError):self.store.collection_history()

    def test_populated_v1_migration_preserves_history_and_failed_attempt(self):
        legacy=self.legacy();oid=self.ids[0];body=self.bodies[oid]
        source={'service_kind':'ModeledService','service_root':str(self.service.root),'service_revision':1}
        snapshot=digest({'tenant_id':self.tenant,'object_id':oid,'body':body})
        with sqlite3.connect(legacy.path) as db:
            db.execute('INSERT INTO collection_runs VALUES(?,?,?,?,?,?,?,?,?)',(1,self.tenant,90,90,91,'complete','complete',None,1))
            db.execute('INSERT INTO collection_runs VALUES(?,?,?,?,?,?,?,?,?)',(2,self.tenant,100,100,101,'denied','denied','workbench_collection_denied',0))
            db.execute('INSERT INTO snapshots VALUES(?,?,?,?)',(snapshot,self.tenant,oid,json.dumps(body)))
            db.execute('INSERT INTO observations VALUES(?,?,?,?,?,?,?)',(1,1,snapshot,self.tenant,oid,90,json.dumps(source)))
        before=legacy.history(oid)
        legacy.migrate(self.root/'populated-backup.sqlite3')
        self.assertEqual(legacy.history(oid),before)
        self.assertEqual(legacy.inspect(oid)['last_attempt']['status'],'denied')
        self.assertEqual(legacy.inspect(oid)['freshness'],'stale')
        self.assertEqual(legacy.collection_detail(1)['collections'][0]['coverage'],'complete')

    def test_real_get_only_capture_import_and_unsupported_raw_inspection(self):
        from intune_iac.capture import capture
        tenant='11111111-1111-4111-8111-111111111111';oid='22222222-2222-4222-8222-222222222222'
        fixture=json.loads((Path(__file__).resolve().parents[1]/'examples/supported/input/export.json').read_text())
        responses={page['request_url']:(page['http_status'],json.dumps(page['body']).encode()) for collection in fixture['collections'] for page in collection['pages']}
        for url,(status,raw) in list(responses.items()):
            if url.endswith('/assignments'):
                value=json.loads(raw)
                for row in value['value']:row.update(source='direct',sourceId=None)
                responses[url]=(status,json.dumps(value).encode())
        store=WorkbenchStore.create(self.root/'captured-store',tenant)
        capture(tenant,oid,self.root/'real-capture',transport=lambda url:responses[url])
        run=store.import_capture(self.root/'real-capture')
        self.assertEqual(run['status'],'complete');self.assertEqual(store.inspect(oid)['body']['name'],'Windows Privacy Pilot')
        self.assertEqual(len(store.inspect(oid)['body']['assignments']),3)
        settings=next(url for url in responses if url.endswith('/settings'));status,raw=responses[settings]
        changed=json.loads(raw);changed['value'][0]['settingInstance']['choiceSettingValue']['value']='future-choice'
        responses[settings]=(status,json.dumps(changed).encode())
        capture(tenant,oid,self.root/'unsupported-capture',transport=lambda url:responses[url])
        failed=store.import_capture(self.root/'unsupported-capture')
        self.assertEqual(failed['status'],'unsupported')
        self.assertIn('future-choice',json.dumps(store.collection_detail(failed['run_id'])['source']['raw_observed']))
        self.assertEqual(store.inspect(oid)['body']['name'],'Windows Privacy Pilot')

    def test_capture_cannot_authorize_modeled_maintenance(self):
        from intune_iac import maintenance
        self.import_batch(self.batch(observed_at=time.time()))
        desired=self.root/'desired.json';desired.write_text(json.dumps(self.bodies[self.ids[0]]))
        with self.assertRaises(AppError) as error:
            maintenance.propose(self.store.root,self.service.root,self.ids[0],desired,self.root/'operation')
        self.assertEqual(error.exception.code,'maintenance_observation_source_mismatch')
        self.assertFalse((self.root/'operation').exists())
        self.assertFalse(any(r['method']=='PATCH' for r in self.service.snapshot()['requests']))

    def test_artifact_modified_payload_cannot_be_returned_under_original_digest(self):
        receipt=self.store.record_artifact('source_reference',None,{'value':'original'})
        with sqlite3.connect(self.store.path) as db:
            db.execute('UPDATE artifacts SET data_json=? WHERE artifact_id=?',(json.dumps({'value':'changed'}),receipt['artifact_id']))
        with self.assertRaises(AppError) as error:self.store.artifacts()
        self.assertEqual(error.exception.code,'workbench_artifact_changed')

    def test_unsupported_mapping_keeps_collection_completeness_separate(self):
        run=self.import_batch(self.batch(status='unsupported'))
        self.assertEqual(run['coverage'],'complete')
        self.assertEqual(run['status'],'unsupported')
        self.assertTrue(all(c['coverage']=='complete' for c in run['collections']))
        self.assertTrue(run['source']['mapping_blockers'])
        self.assertIsNone(self.store.inspect(self.ids[0])['body'])

    def test_artifact_nonfinite_and_unhashable_kind_are_safe_rejections(self):
        with self.assertRaises(AppError):self.store.record_artifact('source_reference',None,{'not_finite':float('nan')})
        with self.assertRaises(AppError):self.store.record_artifact([],None,{})
        self.assertEqual(self.store.artifacts(),[])

    def test_contradictory_capture_status_cannot_hide_coverage_failure(self):
        for status in ('partial','denied'):
            batch=self.batch(status=status)
            for row in batch['collections']:row.update(coverage='complete',reason=None)
            with self.assertRaises(AppError):self.import_batch(batch)

    def test_concurrent_identical_artifact_writers_share_one_immutable_record(self):
        gate=threading.Barrier(12)
        def record(_):
            gate.wait()
            return self.store.record_artifact('source_reference',None,{'value':'same reference'})
        with ThreadPoolExecutor(max_workers=12) as pool:receipts=list(pool.map(record,range(12)))
        self.assertEqual(len({r['artifact_id'] for r in receipts}),1)
        self.assertEqual(sum(r['created'] for r in receipts),1)
        self.assertEqual(len(self.store.artifacts()),1)

    def test_actual_subprocess_exit_during_publish_retains_previous_state(self):
        self.import_batch(self.batch())
        changed=self.batch(observed_at=200);changed['body']['name']='Uncommitted replacement'
        batch_path=self.root/'batch.json';batch_path.write_text(json.dumps(changed))
        script='''import json,os,sys,types
from pathlib import Path
from intune_iac.workbench_store import WorkbenchStore
batch=json.loads(Path(sys.argv[2]).read_text())
sys.modules['intune_iac.capture_adapter']=types.SimpleNamespace(load_capture=lambda path,tenant_id:batch)
original=WorkbenchStore._store_objects
def interrupted(self,*args,**kwargs):
 original(self,*args,**kwargs)
 os._exit(37)
WorkbenchStore._store_objects=interrupted
WorkbenchStore(sys.argv[1]).import_capture(sys.argv[2])
'''
        result=subprocess.run([sys.executable,'-B','-c',script,str(self.store.root),str(batch_path)],capture_output=True,timeout=10)
        self.assertEqual(result.returncode,37,result.stderr)
        reopened=WorkbenchStore(self.store.root)
        self.assertEqual(reopened.inspect(self.ids[0])['body'],self.bodies[self.ids[0]])
        self.assertEqual(len(reopened.history(self.ids[0])),1)
        self.assertEqual(reopened.overview()['last_attempt']['status'],'collecting')
        self.assertEqual(reopened.overview()['freshness'],'stale')

if __name__=='__main__':unittest.main()
