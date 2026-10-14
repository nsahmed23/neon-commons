"""Milestone A state assertions with hand-authored identity/value expectations."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

from intune_iac.io import AppError, digest, write_json
from intune_iac.modeled_service import BASE, ModeledService
from intune_iac.synthetic import generate_estate
from intune_iac.workbench_store import WorkbenchStore
from intune_iac import workbench_semantics as semantics
from intune_iac import workbench_views as views

ROOT = Path(__file__).resolve().parents[1]


class ViewsR4Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fixture = generate_estate(seed=804, policy_count=2)
        self.tenant = self.fixture['truth']['tenant_id']
        self.ids = [p['id'] for p in self.fixture['truth']['policies']]
        self.oid = self.ids[0]
        self.service = ModeledService.create(self.root/'service', self.fixture['capture'], self.ids)
        self.store = WorkbenchStore.create(self.root/'store', self.tenant)
        self.store.collect(self.service)
        self.body = copy.deepcopy(self.service.snapshot()['current']['objects'][self.oid])
        self.repo = self.root/'repository'; (self.repo/'stacks').mkdir(parents=True)
        (self.repo/'components/terraform/intune').mkdir(parents=True)
        (self.repo/'atmos.yaml').write_text('stacks:\n  base_path: stacks\n  included_paths: ["a", "b"]\ncomponents:\n  terraform:\n    base_path: components/terraform\n    command: tofu\n')
        self.save_source(self.body)
        for stack in ('a','b'):
            (self.repo/'stacks'/f'{stack}.yaml').write_text('import: [defaults]\ncomponents:\n  terraform:\n    intune:\n      vars: {}\n')
        self.scope = {'repository':str(self.repo),'stack':'a','component':'intune','backend':'lab-state-a'}

    def save_source(self, body):
        import yaml
        (self.repo/'stacks/defaults.yaml').write_text(yaml.safe_dump({'vars':{'policies':{self.oid:body}}},sort_keys=False))

    def intent(self):
        return views.import_repository(self.store, self.repo, 'a','intune',self.oid,
            '/vars/policies/'+self.oid,'a'*40,'lab-state-a','microsoft365_graph_beta_device_management_configuration_policy.policy')

    def ownership(self, *, age=0, complete=True, conflict=False, missing=False):
        row={'scope':self.scope,'coverage':'complete' if complete else 'partial','observed_at':time.time()-age,
             'claims':[] if missing else [{'object_id':self.oid,'resource_address':'policy.one','parts':['object','assignments']}]}
        rows=[row]
        if conflict:
            other=copy.deepcopy(row);other['scope']['stack']='b';other['scope']['backend']='lab-state-b';rows.append(other)
        value={'schema_version':'workbench-ownership-index/1','tenant_id':self.tenant,'max_age_seconds':60,
               'declared_scopes':[r['scope'] for r in rows],'sources':rows}
        path=self.root/'ownership.json';write_json(path,value)
        return views.import_ownership(self.store,path)

    def view(self, **kw): return views.views(self.store,self.oid,scope=self.scope,**kw)

    def test_global_estate_filters_precede_pagination_and_preserve_denominators(self):
        self.intent(); self.ownership()
        out=views.views(self.store,scope=self.scope,ownership_filter='owned_here',limit=1)
        self.assertEqual(out['total_inventory_objects'],2)
        self.assertEqual(out['pagination']['total_objects'],1)
        self.assertEqual([row['object_id'] for row in out['objects']],[self.oid])
        self.assertEqual(out['filters']['ownership'],'owned_here')
        self.assertEqual(out['objects'][0]['name'],self.body['name'])
        target=max(self.ids)
        found=views.views(self.store,query=target,limit=1)
        self.assertEqual([row['object_id'] for row in found['objects']],[target])
        self.assertEqual(found['pagination']['total_objects'],1)
        self.assertEqual(views.views(self.store,query=target,limit=1,offset=1)['objects'],[])
        before_snapshot=views.views(self.store)['snapshot_sha256']
        self.store.collect(self.service,fault='deny')
        stale=views.views(self.store,coverage_filter='stale_or_incomplete',limit=1)
        self.assertNotEqual(stale['snapshot_sha256'],before_snapshot)
        self.assertEqual(stale['pagination']['total_objects'],2)
        self.assertEqual(views.views(self.store,coverage_filter='complete_fresh')['pagination']['total_objects'],0)
        with self.assertRaises(AppError):views.views(self.store,ownership_filter='owner-ish')

    def test_estate_filters_real_cli_and_bounded_search_fields(self):
        self.intent();self.ownership()
        args=[sys.executable,'-B',str(ROOT/'scripts/intune-iac.py'),'workbench','views','--root',str(self.store.root)]
        result=subprocess.run(args+['--query',max(self.ids),'--limit','1'],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr);out=json.loads(result.stdout)
        self.assertEqual([row['object_id'] for row in out['objects']],[max(self.ids)])
        self.assertEqual(out['pagination']['total_objects'],1);self.assertEqual(out['total_inventory_objects'],2)
        desired=dict(self.body,description='DO-NOT-SEARCH-THIS-DESCRIPTION-804')
        self.save_source(desired);self.intent()
        self.assertEqual(views.views(self.store,query='DO-NOT-SEARCH-THIS-DESCRIPTION-804')['objects'],[])
        definition=self.body['settings']['settings'][0]['settingInstance']['settingDefinitionId']
        result=views.views(self.store,query=definition)
        self.assertIn(self.oid,[row['object_id'] for row in result['objects']])
        from unittest.mock import patch
        with patch.object(views,'MAX_OBJECTS',1):
            with self.assertRaises(AppError):views.views(self.store,limit=1)
        with patch.object(views,'MAX_ESTATE_ARTIFACTS',1):
            with self.assertRaises(AppError):views.views(self.store,query='no-match')
        with self.assertRaises(AppError):views.views(self.store,self.oid,query='selected-object')

    def test_health_filter_requires_complete_fresh_targeted_execution_evidence(self):
        from datetime import datetime,timezone
        from plugin_tests.test_workbench_health import document
        from intune_iac.workbench_health import import_device_evidence
        observed=datetime.fromtimestamp(time.time(),timezone.utc)
        now=observed.timestamp();stamp=observed.isoformat()
        def evidence(reporting,status='success'):
            doc=document(100,reporting);doc['as_of']=stamp
            for row in doc['rows']:row.update(observed_at=stamp,status=status)
            path=self.root/'device.json';write_json(path,{'schema_version':'workbench-device-evidence/1','tenant_id':self.tenant,'object_id':self.oid,'evidence':doc})
            import_device_evidence(self.store,path)
        evidence(8)
        result=views.views(self.store,health_filter='reporting_incomplete',now=now)
        self.assertEqual([row['object_id'] for row in result['objects']],[self.oid])
        self.assertEqual(result['objects'][0]['health']['successful'],8)
        self.assertEqual(result['objects'][0]['health']['unknown'],92)
        self.assertEqual(views.views(self.store,health_filter='fresh_success',now=now)['objects'],[])
        evidence(100)
        result=views.views(self.store,health_filter='fresh_success',now=now)
        self.assertEqual([row['object_id'] for row in result['objects']],[self.oid])
        self.assertEqual(result['objects'][0]['health']['endpoint_health'],'unknown')
        evidence(1,'failure')
        self.assertEqual(views.views(self.store,health_filter='fresh_failure',now=now)['pagination']['total_objects'],1)
        self.assertEqual(views.views(self.store,health_filter='reporting_incomplete',now=now+7200)['pagination']['total_objects'],1)

    def test_actual_repository_read_retains_source_and_resolved_inputs(self):
        intent=self.intent(); out=self.view()
        self.assertEqual(out['repository']['desired'],self.body)
        self.assertEqual(out['repository']['source_revision'],'a'*40)
        self.assertFalse(out['repository']['revision_authenticated'])
        self.assertIn('stacks/defaults.yaml',[r['path'] for r in intent['data']['resolution']['sources']])
        self.assertEqual(out['observed']['body'],self.body)
        self.assertEqual(out['comparisons']['repository_vs_deployment']['status'],'unknown')

    def test_observation_delta_and_pending_desired_edit_are_distinct(self):
        self.intent()
        desired=copy.deepcopy(self.body);desired['description']='Merged source change'
        self.save_source(desired);self.intent()
        out=self.view()
        self.assertEqual(out['comparisons']['repository_vs_observed']['status'],'different')
        self.assertEqual(out['comparisons']['collector_snapshot_delta']['status'],'unknown')
        self.assertEqual(out['comparisons']['observed_vs_deployment']['status'],'unknown')
        changed=copy.deepcopy(self.body);changed['name']='Portal changed name'
        self.service.request('PATCH',BASE+'/'+self.oid,tenant_id=self.tenant,body=changed,if_match='1')
        self.store.collect(self.service)
        out=self.view()
        self.assertEqual(out['comparisons']['collector_snapshot_delta']['changed_fields'],['name'])
        self.assertEqual(set(out['comparisons']['repository_vs_observed']['changed_fields']),{'name','description'})
        self.assertEqual(out['observed']['attribution'],'unknown')

    def test_unmanaged_object_and_absent_provider_state_are_visible(self):
        self.intent();out=self.view()
        self.assertEqual(out['coverage']['management'],'unknown')
        self.assertEqual(out['comparisons']['provider_refresh_vs_state']['status'],'unknown')
        self.assertIn(self.ids[1],[x['object_id'] for x in views.views(self.store)['objects']])

    def test_repository_only_identity_does_not_require_collection(self):
        fresh=WorkbenchStore.create(self.root/'empty',self.tenant)
        views.import_repository(fresh,self.repo,'a','intune',self.oid,'/vars/policies/'+self.oid,'a'*40,'lab-state-a','policy.one')
        out=views.views(fresh,self.oid,scope=self.scope)
        self.assertEqual(out['observed']['status'],'unknown')
        self.assertEqual(out['repository']['desired'],self.body)

    def test_ownership_conflicts_stale_and_incomplete_remain_distinct(self):
        self.intent();self.ownership();self.assertEqual(self.view()['coverage']['ownership']['status'],'owned_here')
        self.ownership(conflict=True);self.assertEqual(self.view()['coverage']['ownership']['status'],'conflicting_claims')
        self.ownership(age=120);self.assertEqual(self.view()['coverage']['ownership']['status'],'unknown')
        self.ownership(complete=False);self.assertEqual(self.view()['coverage']['ownership']['status'],'unknown')
        self.ownership(missing=True);self.assertEqual(self.view()['coverage']['ownership']['status'],'no_ownership_found_in_declared_scope')

    def test_actual_state_ownership_scan_conflicts_and_missing_scope(self):
        from intune_iac.production import RESOURCE
        def state(serial=7):
            return {'version':4,'lineage':'fixture-state-lineage','serial':serial,'resources':[{
                'mode':'managed','type':RESOURCE,'name':'policy','provider':'provider["registry.terraform.io/deploymenttheory/microsoft365"]',
                'instances':[{'schema_version':0,'attributes':{'id':self.oid,'assignments':[]}}]}]}
        path=self.root/'a.tfstate';write_json(path,state())
        manifest={'schema_version':'workbench-ownership-scan/1','tenant_id':self.tenant,'max_age_seconds':60,
            'sources':[{'scope':self.scope,'state_path':str(path)}]}
        spec=self.root/'scan.json';write_json(spec,manifest)
        result=views.scan_ownership(self.store,spec)
        self.assertEqual(views.ownership(self.store,self.oid,self.scope)['status'],'owned_here')
        self.assertEqual(result['data']['state_evidence'][0]['state_revision']['serial'],7)
        other=copy.deepcopy(self.scope);other['stack']='b';other['backend']='lab-state-b'
        second=self.root/'b.tfstate';write_json(second,state(8));manifest['sources'].append({'scope':other,'state_path':str(second)})
        write_json(spec,manifest);views.scan_ownership(self.store,spec)
        self.assertEqual(views.ownership(self.store,self.oid,self.scope)['status'],'conflicting_claims')
        second.unlink();views.scan_ownership(self.store,spec)
        result=views.ownership(self.store,self.oid,self.scope)
        self.assertEqual(result['status'],'unknown');self.assertFalse(result['declared_scope_complete'])

    def test_assignment_writer_can_conflict_without_object_writer_conflict(self):
        self.ownership();value=json.loads((self.root/'ownership.json').read_text())
        other=copy.deepcopy(value['sources'][0]);other['scope']['stack']='b';other['claims'][0]['parts']=['assignments']
        value['declared_scopes'].append(other['scope']);value['sources'].append(other)
        write_json(self.root/'ownership.json',value);views.import_ownership(self.store,self.root/'ownership.json')
        result=self.view()['coverage']['ownership']
        self.assertEqual(result['status'],'conflicting_claims');self.assertEqual(result['conflicting_parts'],['assignments'])
        self.assertFalse(result['execution_authorized'])

    def test_incomplete_collection_blocks_difference_claim(self):
        self.intent();self.store.collect(self.service,fault='deny');out=self.view()
        self.assertEqual(out['observed']['body'],self.body)
        self.assertEqual(out['comparisons']['repository_vs_observed']['status'],'unknown')
        self.assertEqual(out['coverage']['observation'],'stale_or_incomplete')

    def test_declared_semantics_preserve_raw_and_ignore_only_declared_set_order(self):
        before=copy.deepcopy(self.body);after=copy.deepcopy(before)
        after['assignments'].reverse();after['role_scope_tag_ids'].reverse()
        raw=json.dumps(after);result=semantics.compare(before,after)
        self.assertEqual(result['status'],'equal');self.assertEqual(json.dumps(after),raw)
        self.assertIn('ordered',json.dumps(semantics.contract()))

    def test_bad_identity_exclusion_filter_type_and_duplicates_fail(self):
        variants=[]
        v=copy.deepcopy(self.body);v['assignments'].pop();variants.append(v)
        v=copy.deepcopy(self.body);v['assignments'][0]['filter_type']='exclude';variants.append(v)
        v=copy.deepcopy(self.body);v['settings']['settings'][0]['id']='changed';variants.append(v)
        v=copy.deepcopy(self.body);v['settings']['settings'][0]['settingInstance']['choiceSettingValue']['value']=True;variants.append(v)
        for value in variants:
            with self.subTest(value=value):self.assertNotEqual(semantics.compare(self.body,value)['status'],'equal')
        v=copy.deepcopy(self.body);v['assignments'].append(copy.deepcopy(v['assignments'][0]))
        self.assertEqual(semantics.compare(self.body,v)['status'],'unknown')
        v=copy.deepcopy(self.body);v['future_property']=None
        result=semantics.compare(self.body,v);self.assertEqual(result['status'],'unknown');self.assertIn('future_property',result['right']['raw'])

    def test_provider_baseline_names_exact_state_not_last_apply(self):
        value={'schema_version':'workbench-provider-refresh/1','tenant_id':self.tenant,'object_id':self.oid,
            'state_revision':{'lineage':'lineage-1','serial':4,'sha256':'c'*64},'state_body':self.body,
            'refreshed_body':dict(self.body,description='Portal edit'),'observed_at':time.time(),'max_age_seconds':60,
            'scope':self.scope}
        path=self.root/'refresh.json';write_json(path,value);views.import_provider_refresh(self.store,path)
        out=self.view()['comparisons']['provider_refresh_vs_state']
        self.assertEqual(out['changed_fields'],['description']);self.assertEqual(out['baseline']['serial'],4)
        self.assertEqual(out['evidence_class'],'caller_asserted_provider_refresh')
        self.assertNotIn('last_apply',json.dumps(out))

    def test_forged_deployment_success_never_advances_baseline(self):
        self.intent();path=self.root/'receipt.json'
        write_json(path,{'schema_version':'workbench-deployment-claim/1','tenant_id':self.tenant,'object_id':self.oid,
            'desired':self.body,'verified':True,'status':'success','readback':self.body})
        views.import_deployment(self.store,path)
        self.assertEqual(self.view()['comparisons']['observed_vs_deployment']['status'],'unknown')

    def test_source_acceptance_is_reviewable_real_source_patch_without_mutation(self):
        self.intent();changed=dict(self.body,description='Observed proposed description')
        self.service.request('PATCH',BASE+'/'+self.oid,tenant_id=self.tenant,body=changed,if_match='1');self.store.collect(self.service)
        before=(self.repo/'stacks/defaults.yaml').read_bytes();output=self.root/'source-proposal'
        result=views.propose_source_acceptance(self.store,self.oid,'/description',output,scope=self.scope)
        self.assertEqual((self.repo/'stacks/defaults.yaml').read_bytes(),before)
        self.assertTrue(result['fresh_plan_required']);self.assertFalse(result['no_resource_changes_established'])
        self.assertEqual({r['stack'] for r in result['shared_inheritance_impact']},{'a','b'})
        self.assertIn('Observed proposed description',(output/'change.patch').read_text())
        self.assertEqual(result['authoritative_source']['path'],'stacks/defaults.yaml')

    def test_changed_source_rejects_stale_acceptance_proposal(self):
        self.intent();self.save_source(dict(self.body,description='new source edit'))
        with self.assertRaises(AppError):views.propose_source_acceptance(self.store,self.oid,'/description',self.root/'patch',scope=self.scope)
        self.assertFalse((self.root/'patch').exists())

    def test_local_deployment_requires_actual_verified_operation_readback(self):
        from intune_iac import maintenance
        desired=dict(self.body,description='Reviewed execution')
        self.save_source(desired);intent=self.intent();path=self.root/'desired.json';write_json(path,desired)
        operation=self.root/'operation';context=self.root/'operation-context.json'
        write_json(context,{'tenant_id':self.tenant,'cloud':'public','repository_intent_id':intent['artifact_id'],'scope':self.scope})
        proposal=maintenance.propose(self.store.root,self.service.root,self.oid,path,operation,context_path=context)
        with self.assertRaises(AppError):views.record_local_deployment(self.store,operation,intent['artifact_id'])
        result=maintenance.execute(operation,approve_digest=proposal['approval_digest']);self.assertEqual(result['status'],'succeeded_verified')
        views.record_local_deployment(self.store,operation,intent['artifact_id']);self.store.collect(self.service)
        out=self.view();self.assertEqual(out['comparisons']['observed_vs_deployment']['status'],'equal')
        self.assertEqual(out['comparisons']['repository_vs_deployment']['status'],'equal')
        self.assertEqual(out['deployment']['evidence_class'],'verified_local_modeled_deployment')
        self.assertFalse(out['deployment']['platform_qualified'])

    def propose_citing(self, intent, desired, name, scope=None, object_id=None):
        from intune_iac import maintenance
        path=self.root/(name+'-desired.json');write_json(path,desired);context=self.root/(name+'-context.json')
        write_json(context,{'tenant_id':self.tenant,'cloud':'public','repository_intent_id':intent['artifact_id'],'scope':scope or self.scope})
        return maintenance.propose(self.store.root,self.service.root,object_id or self.oid,path,self.root/name,context_path=context)

    def test_proposal_rejects_desired_body_that_contradicts_cited_intent(self):
        original=self.intent();edited=dict(self.body,description='Repository edit under review')
        self.save_source(edited);changed=self.intent()
        for name,intent,desired in (('edited-intent',changed,self.body),('original-intent',original,edited)):
            with self.subTest(name=name):
                with self.assertRaises(AppError) as caught:self.propose_citing(intent,desired,name)
                self.assertEqual(caught.exception.code,'maintenance_desired_intent_mismatch')
                self.assertIn('description',caught.exception.message)
                self.assertFalse((self.root/name).exists())
        self.assertEqual(self.store.operations(object_id=self.oid),[])

    def test_proposal_matching_cited_intent_keeps_change_and_no_change_reviewable(self):
        unchanged=self.propose_citing(self.intent(),self.body,'unchanged')
        self.assertEqual((unchanged['status'],unchanged['changes']),('prepared',[]))
        edited=dict(self.body,description='Repository edit under review');self.save_source(edited)
        result=self.propose_citing(self.intent(),edited,'edited')
        self.assertEqual((result['status'],result['changes']),('prepared',[self.oid+':description_changed']))
        self.assertEqual(result['desired'],edited)

    def test_proposal_rejects_invalid_unknown_or_mismatched_intent_reference(self):
        intent=self.intent();other=dict(self.scope,stack='b',backend='lab-state-b')
        second=copy.deepcopy(self.service.snapshot()['current']['objects'][self.ids[1]])
        invalid,missing,target='maintenance_context_intent_invalid','maintenance_context_intent_missing','maintenance_context_intent_target_mismatch'
        for name,cited,scope,object_id,code in (('null',dict(intent,artifact_id=None),None,None,invalid),
                ('empty',dict(intent,artifact_id=''),None,None,invalid),('number',dict(intent,artifact_id=5),None,None,invalid),
                ('unknown',dict(intent,artifact_id='0'*64),None,None,missing),('other-scope',intent,other,None,target),
                ('other-object',intent,None,self.ids[1],target)):
            with self.subTest(name=name):
                with self.assertRaises(AppError) as caught:self.propose_citing(cited,second if object_id else self.body,name,scope,object_id)
                self.assertEqual(caught.exception.code,code);self.assertFalse((self.root/name).exists())
        self.assertEqual(self.store.operations(),[])

    def test_proposal_reports_unknown_comparison_with_cited_intent_separately(self):
        blocked=copy.deepcopy(self.body);blocked['technologies']=['mdm','mdm'];self.save_source(blocked)
        with self.assertRaises(AppError) as caught:self.propose_citing(self.intent(),self.body,'unknown-comparison')
        self.assertEqual(caught.exception.code,'maintenance_intent_comparison_unknown')
        self.assertIn('/technologies',caught.exception.message);self.assertFalse((self.root/'unknown-comparison').exists())

    def test_restore_of_a_cited_change_is_prepared_without_the_citation(self):
        # restore-propose reuses the original context, and the restored body reverses the intent it cites.
        from intune_iac import maintenance
        edited=dict(self.body,description='Repository edit under review');self.save_source(edited)
        forward=self.propose_citing(self.intent(),edited,'forward')
        self.assertEqual(maintenance.execute(self.root/'forward',approve_digest=forward['approval_digest'])['status'],'succeeded_verified')
        self.store.collect(self.service)
        restore=maintenance.propose_restore(self.root/'forward',self.root/'restore')
        self.assertEqual((restore['status'],restore['changes'],restore['desired']),('prepared',[self.oid+':description_changed'],self.body))
        plan=json.loads((self.root/'restore'/'plan.json').read_text())
        self.assertEqual(json.loads(Path(plan['context']['path']).read_text()),{'tenant_id':self.tenant,'cloud':'public'})

    def test_restore_refuses_a_cited_context_changed_since_its_plan(self):
        # Removing the citation from the original context must not turn the restore into an unchecked uncited one.
        from intune_iac import maintenance
        edited=dict(self.body,description='Repository edit under review');self.save_source(edited)
        forward=self.propose_citing(self.intent(),edited,'forward')
        self.assertEqual(maintenance.execute(self.root/'forward',approve_digest=forward['approval_digest'])['status'],'succeeded_verified')
        self.store.collect(self.service)
        write_json(self.root/'forward-context.json',{'tenant_id':self.tenant,'cloud':'public'})
        with self.assertRaises(AppError) as caught: maintenance.propose_restore(self.root/'forward',self.root/'restore')
        self.assertEqual(caught.exception.code,'maintenance_source_changed')
        self.assertEqual(sorted(p.name for p in self.root.iterdir() if p.name.startswith('restore')),[])

    def test_ordered_setting_sequence_and_null_absent_empty_are_distinct(self):
        base=copy.deepcopy(self.body)
        base['settings']['settings'][0]['settingInstance']={
            '@odata.type':'#microsoft.graph.deviceManagementConfigurationSimpleSettingCollectionInstance',
            'settingDefinitionId':'ordered_fixture','simpleSettingCollectionValue':[
              {'@odata.type':'#microsoft.graph.deviceManagementConfigurationStringSettingValue','value':'first'},
              {'@odata.type':'#microsoft.graph.deviceManagementConfigurationStringSettingValue','value':'second'}]}
        changed=copy.deepcopy(base);changed['settings']['settings'][0]['settingInstance']['simpleSettingCollectionValue'].reverse()
        self.assertEqual(semantics.compare(base,changed)['status'],'different')
        duplicate=copy.deepcopy(base);duplicate['settings']['settings'][0]['settingInstance']['simpleSettingCollectionValue'].append(copy.deepcopy(duplicate['settings']['settings'][0]['settingInstance']['simpleSettingCollectionValue'][0]))
        self.assertEqual(semantics.compare(duplicate,duplicate)['status'],'equal')
        for value in (None,'',False,0):
            changed=copy.deepcopy(self.body);changed['description']=value
            self.assertNotEqual(semantics.compare(self.body,changed)['status'],'equal')
        changed=copy.deepcopy(self.body);del changed['description']
        self.assertEqual(semantics.compare(self.body,changed)['status'],'unknown')

    def test_git_selected_revision_is_verified_and_dirty_source_separate(self):
        git='/usr/bin/git';pin=hashlib.sha256(Path(git).read_bytes()).hexdigest()
        env={'PATH':'/usr/bin:/bin','HOME':str(self.root),'LANG':'C','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null'}
        def run(*args):
            result=subprocess.run([git,*args],cwd=self.repo,env=env,capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stderr);return result.stdout.strip()
        run('init');run('add','.')
        run('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','-c','core.hooksPath=/dev/null','commit','-m','Original source')
        revision=run('rev-parse','HEAD')
        args=(self.store,self.repo,'a','intune',self.oid,'/vars/policies/'+self.oid,revision,'lab-state-a','policy.one')
        record=views.import_repository(*args,git_executable=git,git_sha256=pin)
        self.assertTrue(record['data']['revision_content_verified'])
        self.assertEqual(record['data']['revision_evidence']['selected_revision'],revision)
        self.save_source(dict(self.body,description='uncommitted'))
        changed=views.import_repository(*args,git_executable=git,git_sha256=pin)
        self.assertFalse(changed['data']['revision_content_verified'])
        self.assertEqual(changed['data']['desired']['description'],'uncommitted')
        with self.assertRaises(AppError):views.import_repository(*args,git_executable=git,git_sha256='0'*64)
        with (self.repo/'.git/config').open('a') as stream:stream.write('\n[include]\npath=/nonexistent\n')
        with self.assertRaises(AppError):views.import_repository(*args,git_executable=git,git_sha256=pin)

    def test_new_process_cli_views_and_four_discoverable_routes(self):
        self.intent()
        cli=ROOT/'scripts/intune-iac.py';env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
        result=subprocess.run([sys.executable,'-B',str(cli),'workbench','views','--root',str(self.store.root),'--object',self.oid],capture_output=True,text=True,env=env,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)
        out=json.loads(result.stdout);self.assertTrue({'repository','observed','proposed','coverage'}<=set(out))

if __name__=='__main__':unittest.main()
