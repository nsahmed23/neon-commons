"""Actual-store review amendments preserve findings and reject stale writers."""
import copy
from datetime import datetime,timezone
import json,os,subprocess,sys,tempfile,time,unittest
from pathlib import Path
from intune_iac.io import AppError,write_json
from intune_iac.modeled_service import ModeledService
from intune_iac.synthetic import generate_estate
from intune_iac.workbench_store import WorkbenchStore
from intune_iac import workbench_queue as queue
ROOT=Path(__file__).resolve().parents[1]

class QueueReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        fixture=generate_estate(seed=918,policy_count=2);self.tenant=fixture['truth']['tenant_id'];self.ids=[p['id'] for p in fixture['truth']['policies']];self.oid=self.ids[0]
        self.service=ModeledService.create(self.root/'service',fixture['capture'],self.ids)
        self.store=WorkbenchStore.create(self.root/'store',self.tenant);self.store.collect(self.service)
        self.doc={'schema_version':'workbench-queue-review-input/1','tenant_id':self.tenant,'object_id':self.oid,'finding':'ownership_unknown',
            'owner':'Endpoint operations','rationale':'Confirm stack ownership before any proposed change.','review_due':'2026-11-01T12:00:00Z',
            'exception_expiry':'2026-11-02T12:00:00Z','linked_proposals':[]}
    def write(self,value=None,name='review.json'):
        path=self.root/name;write_json(path,value or self.doc);return path
    def test_create_amend_reopen_history_preserves_typed_chain(self):
        first=queue.amend(self.store,self.write(),expected_prior=None)
        self.doc['owner']='Platform team';self.doc['rationale']='Owner corrected after review.'
        second=queue.amend(self.store,self.write(),expected_prior=first['artifact_id'])
        reopened=WorkbenchStore(self.store.root)
        current=queue.current(reopened,self.oid,'ownership_unknown',now=1793707201)
        self.assertEqual(current['version'],2);self.assertEqual(current['owner'],'Platform team')
        self.assertTrue(current['review_overdue']);self.assertTrue(current['exception_expired'])
        self.assertFalse(current['exception_authorized']);self.assertFalse(current['execution_authorized'])
        history=queue.history(reopened,self.oid,'ownership_unknown')['amendments']
        self.assertEqual([r['data']['version'] for r in history],[1,2]);self.assertEqual(history[1]['data']['previous_artifact_id'],first['artifact_id'])
        self.assertEqual(history[0]['data']['owner'],'Endpoint operations');self.assertEqual(second['artifact_id'],history[1]['artifact_id'])
    def test_conflict_rejected_and_distinct_findings_independent(self):
        first=queue.amend(self.store,self.write(),expected_prior=None)
        self.doc['rationale']='stale update'
        with self.assertRaises(AppError):queue.amend(self.store,self.write(),expected_prior=None)
        with self.assertRaises(AppError):queue.amend(self.store,self.write(),expected_prior='0'*64)
        self.doc['finding']='reporting_incomplete';other=queue.amend(self.store,self.write(),expected_prior=None)
        self.assertNotEqual(first['data']['queue_key'],other['data']['queue_key'])
        self.assertEqual(len(queue.history(self.store,self.oid,'ownership_unknown')['amendments']),1)
    def test_bad_identity_dates_authority_and_unknown_links_reject(self):
        variants=[]
        for changes in ({'tenant_id':self.oid},{'object_id':'bad'},{'approved':True},{'owner':'bad\x1bowner'},
                {'review_due':'2026-11-01'},{'review_due':None},{'exception_expiry':'2026-10-01T00:00:00Z'},
                {'linked_proposals':[{'kind':'maintenance_operation','operation_id':'missing','approval_digest':'a'*64}]}):
            variants.append(dict(self.doc,**changes))
        for doc in variants:
            with self.subTest(doc=doc):
                with self.assertRaises(AppError):queue.amend(self.store,self.write(doc),expected_prior=None)
        self.assertEqual(self.store.artifacts(kind='queue_review'),[])
    def test_real_proposal_link_and_findings_stay_review_required(self):
        from intune_iac import maintenance
        desired=self.store.inspect(self.oid)['body'];desired=copy.deepcopy(desired);desired['description']='Proposed review change'
        path=self.root/'desired.json';write_json(path,desired)
        proposal=maintenance.propose(self.store.root,self.service.root,self.oid,path,self.root/'operation')
        self.doc['linked_proposals']=[{'kind':'maintenance_operation','operation_id':proposal['operation_id'],'approval_digest':proposal['approval_digest']}]
        saved=queue.amend(self.store,self.write(),expected_prior=None)
        finding={'tenant_id':self.tenant,'object_id':self.oid,'finding':'ownership_unknown','action_state':'review_required','automatic_remediation':False,'priority_rationale':'Ownership is unproven.'}
        result=queue.decorate_findings(self.store,[finding])[0]
        self.assertEqual(result['owner'],'Endpoint operations');self.assertEqual(result['action_state'],'review_required')
        self.assertFalse(result['automatic_remediation']);self.assertFalse(result['exception_authorized'])
        self.assertEqual(result['review_record']['artifact_id'],saved['artifact_id'])
        self.assertEqual(result['linked_proposals'][0]['approval_digest'],proposal['approval_digest'])
        self.assertEqual(self.service.snapshot()['current']['objects'][self.oid]['description'],self.store.inspect(self.oid)['body']['description'])
    def test_actual_queue_writer_index_distinguishes_claims_from_human_owner(self):
        import yaml
        from intune_iac import workbench_views
        self.store.collect(self.service,source={'owner':'Unverified source label'})
        def actual_queue():
            result=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/intune-iac.py'),'workbench','queue','--root',str(self.store.root),'--limit','10'],capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stderr)
            return [r for r in json.loads(result.stdout)['findings'] if r['object_id']==self.oid]
        rows=actual_queue()
        self.assertIn('ownership_unknown',{r['finding'] for r in rows})
        self.assertTrue(all(r['owner'] is None for r in rows))
        prior_review=queue.amend(self.store,self.write(),expected_prior=None)
        repo=self.root/'repo';(repo/'stacks').mkdir(parents=True);(repo/'components/terraform/intune').mkdir(parents=True)
        (repo/'atmos.yaml').write_text('stacks:\n  base_path: stacks\n  included_paths: [a]\ncomponents:\n  terraform:\n    base_path: components/terraform\n')
        body=self.store.inspect(self.oid)['body']
        (repo/'stacks/a.yaml').write_text(yaml.safe_dump({'components':{'terraform':{'intune':{'vars':{'policy':body}}}}}))
        intent=workbench_views.import_repository(self.store,repo,'a','intune',self.oid,'/vars/policy','a'*40,'state-a','policy.one')
        scope=intent['data']['scope'];other=dict(scope,stack='b',backend='state-b')
        first={'scope':scope,'coverage':'complete','observed_at':time.time(),'claims':[{'object_id':self.oid,'resource_address':'policy.one','parts':['object','assignments']}]}
        doc={'schema_version':'workbench-ownership-index/1','tenant_id':self.tenant,'max_age_seconds':60,'declared_scopes':[scope],'sources':[first]}
        def index():
            path=self.root/'ownership.json';write_json(path,doc);workbench_views.import_ownership(self.store,path)
        index();rows=actual_queue()
        self.assertFalse(any(r['finding'].startswith('ownership_') for r in rows))
        self.assertEqual(rows[0]['writer_ownership']['status'],'owned_here')
        second=copy.deepcopy(first);second['scope']=other;second['claims'][0]['parts']=['assignments']
        doc['declared_scopes'].append(other);doc['sources'].append(second);index();rows=actual_queue()
        conflict=next(r for r in rows if r['finding']=='ownership_conflicting_claims')
        self.assertEqual(conflict['writer_ownership']['conflicting_parts'],['assignments'])
        self.assertIsNone(conflict['owner']);self.assertFalse(conflict['automatic_remediation'])
        for surface in ('inspect','settings','relationships'):
            shown=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/intune-iac.py'),'workbench',surface,
                '--root',str(self.store.root),'--object',self.oid],capture_output=True,text=True,timeout=20)
            self.assertEqual(shown.returncode,0,shown.stderr)
            detail=json.loads(shown.stdout)
            self.assertEqual(detail['ownership'],'conflicting_claims')
            self.assertEqual(detail['ownership_evidence']['conflicting_parts'],['assignments'])
            self.assertFalse(detail['ownership_evidence']['cloud_authority'])
        self.assertEqual(queue.current(self.store,self.oid,'ownership_unknown')['artifact_id'],prior_review['artifact_id'])
        conflict_review=dict(self.doc,finding='ownership_conflicting_claims',owner='Conflict reviewer')
        queue.amend(self.store,self.write(conflict_review,name='conflict-review.json'),expected_prior=None)
        reviewed=next(r for r in actual_queue() if r['finding']=='ownership_conflicting_claims')
        self.assertEqual(reviewed['owner'],'Conflict reviewer');self.assertEqual(reviewed['writer_ownership']['status'],'conflicting_claims')
        doc['sources'][0]['claims']=[];doc['sources'][1]['claims'][0]['parts']=['object','assignments'];index()
        self.assertIn('ownership_elsewhere',{r['finding'] for r in actual_queue()})
        doc['sources'][0]['observed_at']=time.time()-120;index();rows=actual_queue()
        stale=next(r for r in rows if r['finding']=='ownership_stale')
        self.assertEqual(stale['writer_ownership']['status'],'unknown');self.assertFalse(stale['writer_ownership']['fresh']);self.assertIsNone(stale['owner'])
        for row in doc['sources']:row['observed_at']=time.time();row['claims']=[]
        index();rows=actual_queue();self.assertIn('ownership_unclaimed',{r['finding'] for r in rows})
        doc['sources'][1]['coverage']='partial';index();rows=actual_queue()
        unknown=next(r for r in rows if r['finding']=='ownership_unknown')
        self.assertFalse(unknown['writer_ownership']['declared_scope_complete'])
        self.assertNotIn('ownership_unclaimed',{r['finding'] for r in rows})

    def test_two_prevalidated_writers_race_at_atomic_store_boundary(self):
        import concurrent.futures,threading
        barrier=threading.Barrier(2);a=self.write(name='a.json');self.doc['rationale']='Concurrent review';b=self.write(name='b.json')
        def worker(path):
            store=WorkbenchStore(self.store.root);original=store.record_artifact
            def record(*args,**kwargs):
                barrier.wait(timeout=10)
                return original(*args,**kwargs)
            store.record_artifact=record
            try:return ('saved',queue.amend(store,path,expected_prior=None)['artifact_id'])
            except AppError as exc:return ('error',exc.code)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(worker,(a,b)))
        self.assertEqual(sum(r[0]=='saved' for r in results),1,results)
        self.assertEqual([r[1] for r in results if r[0]=='error'],['workbench_queue_conflict'])
        self.assertEqual(len(queue.history(self.store,self.oid,'ownership_unknown')['amendments']),1)

    def test_store_requires_explicit_prior_and_real_queue_cli_preserves_findings(self):
        first=queue.amend(self.store,self.write(),expected_prior=None)
        with self.assertRaises(AppError):self.store.record_artifact('queue_review',self.oid,first['data'])
        promoted=dict(first['data'],execution_authorized=True,previous_artifact_id=first['artifact_id'])
        with self.assertRaises(AppError):self.store.record_artifact('queue_review',self.oid,promoted,expected_prior=first['artifact_id'])
        result=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/intune-iac.py'),'workbench','queue','--root',str(self.store.root),'--limit','10'],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr);out=json.loads(result.stdout)
        finding=next(r for r in out['findings'] if r['object_id']==self.oid and r['finding']=='ownership_unknown')
        self.assertEqual(finding['owner'],'Endpoint operations')
        self.assertEqual(finding['action_state'],'review_required');self.assertFalse(finding['automatic_remediation'])
        self.assertEqual(finding['review_record']['artifact_id'],first['artifact_id'])
        self.assertFalse(finding['exception_authorized']);self.assertIn('ownership',finding['priority_rationale'])

    def test_global_collection_review_and_concurrent_cli_compare_append(self):
        self.doc.update(object_id=None,finding='no_complete_observations');first=queue.amend(self.store,self.write(),expected_prior=None)
        self.assertEqual(queue.current(self.store,None,'no_complete_observations')['artifact_id'],first['artifact_id'])
        self.doc.update(object_id=self.oid,finding='ownership_unknown');a=self.write(name='a.json');self.doc['rationale']='Second competing update';b=self.write(name='b.json')
        prefix=[sys.executable,'-B',str(ROOT/'scripts/intune-iac.py'),'workbench','queue-amend','--root',str(self.store.root),'--expected-prior','none','--input']
        procs=[subprocess.Popen(prefix+[str(path)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for path in (a,b)]
        output=[p.communicate(timeout=20) for p in procs]
        self.assertEqual(sorted(p.returncode for p in procs),[0,3],output)
        self.assertEqual(len(queue.history(self.store,self.oid,'ownership_unknown')['amendments']),1)
        failed=[output[i] for i,p in enumerate(procs) if p.returncode]
        self.assertIn('workbench_queue_conflict',str(failed))
if __name__=='__main__':unittest.main()
