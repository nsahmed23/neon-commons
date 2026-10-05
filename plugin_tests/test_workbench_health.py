"""Tenant-bound diagnostic evidence never becomes rollout authorization."""
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from intune_iac.io import AppError
from intune_iac import workbench_health as health

TENANT='11111111-1111-4111-8111-111111111111'
OBJECT='22222222-2222-4222-8222-222222222222'
NOW=1791172800
STAMP=datetime.fromtimestamp(NOW,timezone.utc).isoformat().replace('+00:00','Z')


def document(targeted=100, reporting=8):
    return {'schema_version':'1.0.0','synthetic':True,'as_of':STAMP,'freshness_seconds':3600,
      'cohort':{'version':'fixture','eligible_ids':[f'device-{i}' for i in range(targeted)],
                'targeted_ids':[f'device-{i}' for i in range(targeted)],'excluded_ids':[]},
      'rows':[{'id':f'row-{i}','device_id':f'device-{i}','stage':'execution','status':'success',
               'observed_at':STAMP,'source_file':'minimized.json','source_pointer':f'/{i}',
               'coverage':'complete','synthetic':True} for i in range(reporting)],
      'capture':{'timezone':'UTC','clock_skew_seconds':None,'logging_enabled':None,'truncated':False,'access_errors':[]},
      'promotion_thresholds':{'min_reporting_ratio':1,'min_success_ratio':1}}


class Store:
    tenant_id=TENANT
    def __init__(self):self.rows=[]
    def inspect(self, object_id):
        if object_id!=OBJECT:raise AppError('missing','Missing object')
        return {'tenant_id':TENANT,'object_id':OBJECT,'body':None}
    def record_artifact(self,kind,object_id,data):
        value={'sequence':len(self.rows)+1,'artifact_id':str(len(self.rows)+1),'kind':kind,'object_id':object_id,'data':data}
        self.rows.append(value);return value
    def artifacts(self,kind=None,object_id=None,**kw):return [r for r in self.rows if (kind is None or r['kind']==kind) and (object_id is None or r['object_id']==object_id)]
    def operations(self,object_id=None):return [{'operation_id':'op-local','object_id':OBJECT}]
    def history(self,object_id):return [{'snapshot_id':'a'*64,'observed_at':STAMP}]


class HealthTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.store=Store()
    def write(self,value):
        path=self.root/'input.json';path.write_text(json.dumps(value));return path
    def envelope(self,doc=None):return {'schema_version':'workbench-device-evidence/1','tenant_id':TENANT,'object_id':OBJECT,'evidence':doc or document()}
    def test_stage_denominators_never_merge_execution_into_effectiveness(self):
        value=health.summarize_evidence(document(),now=NOW)
        execution=value['stages']['execution'];self.assertEqual((execution['targeted'],execution['reporting'],execution['successful'],execution['unknown']),(100,8,8,92))
        self.assertEqual(execution['reporting_success_percent'],100);self.assertEqual(execution['targeted_success_percent'],8)
        self.assertEqual(value['stages']['effective_state']['reporting'],0);self.assertEqual(value['stages']['outcome']['unknown'],100)
        self.assertFalse(value['rollout_ready']);self.assertEqual(value['rollout_approval'],'unknown');self.assertEqual(value['endpoint_health'],'unknown')
    def test_unknown_conflicting_denied_stale_and_membership_remain_distinct(self):
        doc=document(5,5);doc['rows'][1]['status']='conflicting';doc['rows'][2]['coverage']='access_denied';doc['rows'][3]['observed_at']='2020-01-01T00:00:00Z';doc['cohort']['excluded_ids']=['device-4']
        stage=health.summarize_evidence(doc,now=NOW)['stages']['execution']
        self.assertEqual(stage['successful'],1);self.assertEqual(stage['unknown'],4)
        self.assertEqual((stage['conflicting'],stage['access_denied'],stage['stale'],stage['membership_conflicts']),(1,1,1,1))
        self.assertTrue(all(row['status']=='unknown' and row['reported_status']=='success' for row in stage['devices'] if row.get('reason')))
    def test_newer_unknown_supersedes_old_success_equal_time_disagreement_conflicts(self):
        doc=document(1,1);row=copy.deepcopy(doc['rows'][0]);row.update(id='new',status='failure');doc['rows'].append(row)
        stage=health.summarize_evidence(doc,now=NOW)['stages']['execution'];self.assertEqual(stage['conflicting'],1);self.assertEqual(stage['successful'],0)
    def test_import_binds_exact_source_and_never_claims_actual_service_evidence(self):
        path=self.write(self.envelope());row=health.import_device_evidence(self.store,path)
        self.assertEqual(row['data']['source_sha256'],hashlib.sha256(path.read_bytes()).hexdigest());self.assertEqual(row['data']['evidence_class'],'synthetic')
        actual=self.envelope();actual['evidence']['synthetic']=False
        for item in actual['evidence']['rows']:item['synthetic']=False
        row=health.import_device_evidence(self.store,self.write(actual));self.assertEqual(row['data']['evidence_class'],'caller_asserted')
    def test_wrong_tenant_and_schema_rejected_before_persistence(self):
        value=self.envelope();value['tenant_id']=OBJECT
        with self.assertRaises(AppError):health.import_device_evidence(self.store,self.write(value))
        value=self.envelope();value['evidence']['rows'][0]['coverage']='green'
        with self.assertRaises(AppError):health.import_device_evidence(self.store,self.write(value))
        self.assertEqual(self.store.rows,[])
    def test_duplicate_row_ids_and_capture_truncation_do_not_promote(self):
        doc=document(2,2);doc['rows'][1]['id']=doc['rows'][0]['id']
        with self.assertRaises(AppError):health.summarize_evidence(doc,now=NOW)
        doc=document();doc['capture']['truncated']=True
        self.assertEqual(health.summarize_evidence(doc,now=NOW)['stages']['execution']['reporting'],0)
    def test_unknown_policy_health_has_no_collection_aggregate_counts(self):
        result=health.device_health(self.store,OBJECT,now=NOW);self.assertEqual(result['evidence_class'],'unknown');self.assertIsNone(result['stages']['execution']['targeted']);self.assertFalse(result['rollout_ready'])
    def test_workflow_lineage_is_inert_and_local_bindings_must_match(self):
        value={'schema_version':'workbench-workflow-run/1','tenant_id':TENANT,'object_id':OBJECT,
               'run_url':'https://github.com/example/repo/actions/runs/42','repository_revision':'b'*40,
               'run_id':'42','status':'success','observed_at':STAMP,'related_operation':'op-local','observed_after':'a'*64}
        row=health.import_workflow_run(self.store,self.write(value));self.assertEqual(row['data']['evidence_class'],'caller_asserted')
        self.assertFalse(row['data']['external_execution_verified']);self.assertEqual({r['relation'] for r in row['data']['relationships']},{'related_operation','observed_after'})
        value['related_operation']='unrecorded'
        with self.assertRaises(AppError):health.import_workflow_run(self.store,self.write(value))
        value['related_operation']='op-local';value['run_url']='https://secret@example.invalid/run'
        with self.assertRaises(AppError):health.import_workflow_run(self.store,self.write(value))

if __name__=='__main__':unittest.main()
