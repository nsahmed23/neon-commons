"""Native store-backed views: actual SQLite/capture, recorded Win32 only."""
import copy
from datetime import datetime,timezone
import importlib.util
import io
import json
from pathlib import Path
import time
import unittest
from unittest.mock import patch
from intune_iac import workbench_views as subject,workbench,capture,windows_capture_writer
from intune_iac.io import canonical
from plugin_tests import test_windows_capture_r4 as capture_fixture
from plugin_tests.test_windows_storage_r4 import ROOT,CANONICAL
from plugin_tests.test_capture_adapter import T,P

class WindowsViewsTests(unittest.TestCase):
    def setUp(self):
        capture_fixture.WindowsCaptureTests.setUp(self)
        self.database=self.api.real(CANONICAL+'\\store\\observations.sqlite3')
        self.scope={'repository':'C:\\Pilot\\Repository','stack':'pilot','component':'intune','backend':'declared-test-backend'}
        self.now=int(time.time());self.number=0;self.collect();self.body=copy.deepcopy(self.store.inspect(P)['body'])
    def collect(self,*,description=None,unsupported=False):
        responses=copy.deepcopy(self.responses)
        for url,(status,raw) in list(responses.items()):
            body=json.loads(raw)
            if url.endswith('/configurationPolicies') and description is not None:body['value'][0]['description']=description
            if url.endswith('/settings') and unsupported:body['value'][0]['id']='37'
            responses[url]=(status,canonical(body))
        path=ROOT+'\\capture-'+str(self.number)
        stamp=datetime.fromtimestamp(self.now-10+self.number,tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ');self.number+=1
        with patch.object(capture,'_stamp',return_value=stamp):
            capture._capture(T,P,path,transport=lambda url:responses[url],source_is_synthetic=True,
                output_factory=lambda dest:windows_capture_writer._output(dest,self.api))
        self.store.import_capture(path)
    def intent(self,body=None,oid=P):
        return self.store.record_artifact('repository_intent',None,{'schema_version':'workbench-repository-intent/1',
            'tenant_id':T,'target_object_id':oid,'scope':self.scope,'desired':copy.deepcopy(self.body if body is None else body),
            'source_revision':'a'*40,'revision_authenticated':False,'revision_content_verified':False,
            'revision_assurance':'caller_asserted_revision_actual_working_source_hashes','collected_at':self.now-20,
            'resolution':{'sources':[{'path':'stacks/pilot.yaml','sha256':'b'*64}]},
            'evidence_class':'local_literal_repository_read','cloud_authority':False,'execution_authorized':False})
    def view(self,**kw):return subject.views(self.store,P,now=self.now,**kw)
    def test_four_views_preserve_identity_targeting_and_recorded_source_scope(self):
        self.intent();before=self.database.read_bytes();out=self.view()
        self.assertEqual(out['tenant_id'],T);self.assertEqual(out['object_id'],P)
        self.assertEqual(out['observed']['body']['name'],'Windows Privacy Pilot');self.assertEqual(len(out['observed']['body']['assignments']),3)
        self.assertEqual(out['repository']['source_revision'],'a'*40);self.assertEqual(out['repository']['resolution']['sources'][0]['sha256'],'b'*64)
        self.assertFalse(out['repository']['revision_authenticated']);self.assertEqual(out['repository']['current_working_source_readback']['status'],'unknown')
        self.assertEqual(out['comparisons']['repository_vs_observed']['status'],'equal')
        self.assertEqual(out['deployment']['reason'],'verified_deployment_missing');self.assertEqual(out['proposed']['reason'],'operation_not_selected')
        self.assertEqual(out['observed']['raw_capture_observation']['capture_integrity']['status'],'verified_local_bytes')
        self.assertEqual(self.database.read_bytes(),before);self.assertEqual(self.api.handles,{})
    def test_merged_repository_change_is_not_labeled_observed_drift(self):
        self.intent(dict(self.body,description='Merged repository correction'));out=self.view();comparison=out['comparisons']['repository_vs_observed']
        self.assertEqual(comparison['changed_fields'],['description']);self.assertFalse(comparison['drift_established'])
        self.assertEqual(comparison['classification'],'desired_observed_difference');self.assertEqual(out['comparisons']['observed_vs_deployment']['status'],'unknown')
    def test_observed_change_and_simultaneous_intent_keep_distinct_baselines(self):
        self.intent(dict(self.body,description='Merged correction'));self.collect(description='Observed portal correction');out=self.view()
        delta=out['comparisons']['collector_snapshot_delta'];self.assertEqual(delta['changed_fields'],['description'])
        self.assertEqual(delta['baseline']['kind'],'prior_collector_snapshot');self.assertEqual(delta['attribution'],'unknown')
        self.assertEqual(out['comparisons']['repository_vs_observed']['changed_fields'],['description'])
        self.assertEqual(out['repository']['desired']['description'],'Merged correction');self.assertEqual(out['observed']['body']['description'],'Observed portal correction')
    def test_repository_only_object_is_discoverable_without_state_or_observation(self):
        other='44444444-4444-4444-8444-444444444444';self.intent(oid=other);estate=subject.views(self.store,now=self.now,query=other,limit=1)
        self.assertEqual(estate['total_inventory_objects'],2);self.assertEqual(estate['objects'][0]['object_id'],other)
        out=subject.views(self.store,other,now=self.now);self.assertEqual(out['observed']['reason'],'object_not_collected');self.assertEqual(out['coverage']['management'],'unknown')
    def test_stored_ownership_conflict_stale_and_incomplete_are_not_ownership_proof(self):
        self.intent()
        def record(complete=True,stale=False):
            sources=[]
            for component in ('intune','other'):
                scope=dict(self.scope,component=component);sources.append({'scope':scope,'coverage':'complete' if complete else 'partial','observed_at':self.now-(100 if stale else 1),
                    'claims':[{'object_id':P,'resource_address':'policy.one','parts':['object','assignments']}]})
            self.store.record_artifact('ownership_index',None,{'document':{'declared_scopes':[v['scope'] for v in sources],'sources':sources,'max_age_seconds':60},'evidence_class':'declared_ownership_index','external_verification':False})
        record();self.assertEqual(self.view()['coverage']['management'],'conflicting_claims')
        record(stale=True);self.assertEqual(self.view()['coverage']['ownership']['reason'],'stale_or_incomplete_declared_scope')
        record(complete=False);self.assertEqual(self.view()['coverage']['management'],'unknown')
    def test_refresh_baseline_preserves_actual_state_revision_label(self):
        self.intent();self.store.record_artifact('provider_refresh',None,{'document':{'object_id':P,'scope':self.scope,
            'state_body':self.body,'refreshed_body':dict(self.body,description='Refresh difference'),
            'state_revision':{'lineage':'state-after-import','serial':9,'sha256':'c'*64},'observed_at':self.now-1,'max_age_seconds':60}})
        comparison=self.view()['comparisons']['provider_refresh_vs_state']
        self.assertEqual(comparison['baseline'],{'kind':'persisted_state_revision_used','lineage':'state-after-import','serial':9,'sha256':'c'*64})
        self.assertFalse(comparison['independently_authenticated']);self.assertEqual(comparison['changed_fields'],['description'])
    def test_stored_verified_labels_cannot_open_unsupported_journals_or_create_baseline(self):
        intent=self.intent()
        for kind in ('verified_local_modeled_deployment','linked_protected_service','caller_asserted_deployment'):
            self.store.record_artifact('deployment_receipt',None,{'target_object_id':P,'scope':self.scope,'evidence_class':kind,
                'intent_id':intent['artifact_id'],'proof':{'operation_root':'C:\\DO-NOT-OPEN'},'job_root':'C:\\DO-NOT-OPEN','policy_path':'C:\\DO-NOT-OPEN','baseline_admissible':True})
        from intune_iac import workbench_service_views
        before=self.database.read_bytes()
        with (patch.object(subject,'_local_proof',side_effect=AssertionError('POSIX local proof opened')),
                patch.object(workbench_service_views,'deployment',side_effect=AssertionError('service proof opened')),
                patch.object(workbench_service_views,'proposed',side_effect=AssertionError('service proposal opened'))):out=self.view()
        issues=out['native_evidence_access']['issues'];self.assertEqual(len(issues),4)
        self.assertTrue(all(value['path_opened'] is False and value['baseline_admissible'] is False for value in issues))
        self.assertEqual(out['deployment']['status'],'unknown');self.assertEqual(out['proposed']['reason'],'native_protected_service_journal_unsupported')
        self.assertEqual(out['comparisons']['repository_vs_deployment']['status'],'unknown');self.assertEqual(self.database.read_bytes(),before)
    def test_selected_operation_remains_unknown_without_loading_posix_maintenance(self):
        from intune_iac import maintenance
        with patch.object(maintenance,'_load',side_effect=AssertionError('POSIX operation opened')):out=self.view(operation='C:\\DO-NOT-OPEN')
        self.assertEqual(out['proposed']['reason'],'native_selected_operation_journal_unsupported');self.assertFalse(out['proposed']['evidence_access']['path_opened'])
    def test_raw_unsupported_id_remains_visible_without_invented_normalized_update(self):
        self.collect(unsupported=True);out=self.view();raw=out['observed']['raw_capture_observation'];settings=raw['source']['raw_observed']['settings']
        self.assertEqual(settings[0]['id'],'37');self.assertEqual(raw['status'],'unsupported');self.assertEqual(raw['capture_integrity']['status'],'verified_local_bytes')
        self.assertEqual(out['coverage']['latest_capture_status'],'unsupported')
    def test_raw_capture_tamper_is_visible_and_never_promoted(self):
        path=self.api.real(CANONICAL+'\\capture-0\\raw\\page-000000.json');path.write_bytes(path.read_bytes()+b' ');out=self.view()
        self.assertEqual(out['observed']['raw_capture_observation']['capture_integrity']['status'],'unverified_or_changed');self.assertFalse(out['observed']['source']['source_authenticity_verified'])
    def test_shared_terminal_actual_input_sequences_and_exact_readonly_store(self):
        self.intent();before=self.database.read_bytes();inputs=iter(['views-page 1 0 - - - -','select '+P,'views','views C:\\DO-NOT-OPEN','back','quit']);results=[]
        output=workbench.run_terminal(str(self.store.root),input_fn=lambda _:next(inputs),result_fn=results.append,_store_capability=self.store)
        self.assertEqual(output['status'],'closed');views=[r for r in results if type(r) is dict and r.get('schema_version')=='workbench-four-views/1']
        self.assertGreaterEqual(len(views),3);self.assertEqual(views[-1]['proposed']['reason'],'native_selected_operation_journal_unsupported')
        self.assertFalse(any(r.get('error',{}).get('code')=='native_workspace_command_unimplemented' for r in results if type(r) is dict))
        self.assertEqual(self.database.read_bytes(),before);self.assertEqual(self.api.handles,{})
    def test_text_qualification_entrypoint_uses_same_native_store_and_engine(self):
        self.intent();script=Path(subject.__file__).parents[1]/'scripts/intune-windows-inspect.py';spec=importlib.util.spec_from_file_location('native_views_qualifier',script)
        app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app);stdout=io.StringIO();before=self.database.read_bytes()
        with patch.object(app,'WindowsWorkbenchStore',return_value=self.store),patch('sys.stdout',stdout):
            code=app.main(['--qualification-only','--store',str(self.store.root),'--tenant',T,'views',P])
        result=json.loads(stdout.getvalue());self.assertEqual(code,0);self.assertEqual(result['result']['object_id'],P)
        self.assertEqual(result['result']['comparisons']['repository_vs_observed']['status'],'equal');self.assertFalse(result['platform_qualified']);self.assertEqual(self.database.read_bytes(),before)

if __name__=='__main__':unittest.main()
