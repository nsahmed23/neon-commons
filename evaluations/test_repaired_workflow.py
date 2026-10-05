"""Real local receipt-store integration controls, never supplied verified lists."""
import copy, json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path
from reference import workflow, approval
R=Path(__file__).resolve().parents[1]
def complete_seed(p):
 rows=[('repository_context','repository.json'),('source','source.json'),('decisions','decisions.json'),('normalized','normalized.json'),('provider_evidence','provider.json')]
 shutil.copytree(R/'examples/workflow-demo/partial',p,dirs_exist_ok=True)
 # Git checkouts cannot retain a nested .git fixture. Construct its synthetic
 # detached HEAD in the test's private directory, as seed() does below.
 (p/'repo/.git').mkdir(parents=True,exist_ok=True)
 (p/'repo/.git/HEAD').write_text('1'*40+'\n')
 def write(path,obj):
  q=p/path;q.parent.mkdir(parents=True,exist_ok=True);q.write_text(json.dumps(obj))
 from reference import core
 raw=(R/'corrections/fixtures/source-export.json').read_bytes();source=json.loads(raw);ctx=json.loads((R/'corrections/fixtures/context.json').read_text());norm=core.normalize(source,ctx['selected_policy_id'],ctx['tenant_id']);
 with tempfile.TemporaryDirectory() as buildroot:
  output=Path(buildroot)/'project'
  emitted=subprocess.run([sys.executable,str(R/'tools/build-reference.py'),'--input',str(R/'corrections/fixtures/source-export.json'),'--context',str(R/'corrections/fixtures/context.json'),'--output',str(output)],capture_output=True,text=True)
  if emitted.returncode!=0:raise AssertionError('Actual generator CLI failed: '+emitted.stderr)
  files={q.relative_to(output).as_posix():q.read_text() for q in output.rglob('*') if q.is_file() and q.name!='generated-files.json'}
 (p/'source.json').write_bytes(raw);write('normalized.json',norm)
 workflow.create(p,'object_selection',rows);facts=workflow.inspect(p);(p/'session.json').unlink();(p/'receipt-index.json').unlink()
 for path,value in files.items():q=p/path;q.parent.mkdir(parents=True,exist_ok=True);q.write_text(value)
 write('generation.json',{'schema_version':'1.0.0','files':{k:workflow.sha((p/k).read_bytes()) for k in files}})
 b=json.loads((R/'corrections/fixtures/approval-context.json').read_text())['binding'];current=facts['fingerprints']
 for key in ['source_digest','selected_ids_digest','ownership_digest','provider_source','provider_version','provider_lock_digest','engine_version','atmos_version']:b[key]=current[key]
 provider=json.loads((p/'provider.json').read_text())['payload'];b['engine_binary_sha256']=provider['engine_sha256'];b['atmos_binary_sha256']=provider['atmos_sha256'];b['git_revision']=current['repository_revision'];b['relevant_dirty_files_digest']=current['dirty_files_digest']
 rows += [('generation','generation.json'),('effective_config','effective.json'),('identity_context','identity.json'),('validation','validation.json'),('review','review.json')]
 inputs=sorted({path for kind,path in rows if kind not in ['identity_context','effective_config','review','validation']}|set(files)|{'repo/config.txt','lock.hcl','provider-schema.json','tofu.bin','atmos.bin'})
 e={'component':ctx['component'],'stack':ctx['stack'],'inputs':inputs,'resolved_inputs':{},'closed':True};target={k:b[k] for k in ['cloud','tenant_id','subscription_id','service_endpoint','identity','backend','component','stack']}
 b['configuration_digest']=workflow.sha(workflow.canonical({'files':workflow._manifest_bytes(p,inputs),'resolved_inputs':{},'target':target,'schema_version':'2.0.0'}))
 write('effective.json',{'schema_version':'2.0.0','kind':'effective_config','payload':e});write('validation.json',{'schema_version':'2.0.0','kind':'validation','payload':{'oracle_version':'independent-v2'}})
 from datetime import datetime,timezone,timedelta
 now=datetime.now(timezone.utc)
 cohort={'schema_version':'2.0.0','tenant_id':ctx['tenant_id'],'object_id':ctx['selected_policy_id'],'captured_at':now.isoformat(),'expires_at':(now+timedelta(days=7)).isoformat(),'members':[]};write('cohort.json',cohort);(p/'plan.bin').write_bytes(b'offline synthetic plan');b['cohort_digest']=workflow.sha(workflow.canonical(cohort));b['plan_digest']=workflow.sha((p/'plan.bin').read_bytes());write('identity.json',b)
 write('review.json',{'schema_version':'2.0.0','kind':'review','payload':{'cohort_path':'cohort.json','plan_path':'plan.bin'}})
 return rows


class Workflow(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.root=Path(self.t.name)
 def tearDown(self):self.t.cleanup()
 def write(self,p,value):
  dest=self.root/p;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(json.dumps(value));return p
 def seed(self,state='object_selection'):
  self.root.joinpath('repo/.git').mkdir(parents=True,exist_ok=True)
  self.root.joinpath('repo/.git/HEAD').write_text('1'*40+'\n')
  self.root.joinpath('repo/config.txt').write_text('inputs\n')
  self.write('repository.json',{'schema_version':'2.0.0','kind':'repository_context','payload':{'repository_path':'repo','inputs':['repo/config.txt']}})
  source=json.loads((R/'corrections/fixtures/source-export.json').read_text());self.write('source.json',source)
  ctx=json.loads((R/'corrections/fixtures/context.json').read_text())
  self.write('decisions.json',{'schema_version':'2.0.0','kind':'decisions','payload':{'source_kind':'local_export','source_path':'source.json','tenant_id':ctx['tenant_id'],'cloud':'public','selected_policy_id':ctx['selected_policy_id'],'selected_ids':[ctx['selected_policy_id']],'ownership':[]}})
  return workflow.create(self.root,state,[('repository_context','repository.json'),('source','source.json'),('decisions','decisions.json')])
 def test_early_current_bytes_and_nonadvancement(self):
  self.seed();x=workflow.resume(self.root,local_resume=True);self.assertEqual(x['next_state'],'object_selection');self.assertFalse(x['external_execution'])
 def test_missing_receipt_invalidates_inventory(self):
  s=self.seed();idx=json.loads((self.root/'receipt-index.json').read_text());idx['milestone_receipts']=[r for r in idx['milestone_receipts'] if r['milestone']!='inventory'];self.write('receipt-index.json',idx)
  s['artifact_index']['byte_sha256']=workflow.sha((self.root/'receipt-index.json').read_bytes());self.write('session.json',s)
  self.assertEqual(workflow.resume(self.root,local_resume=True)['next_state'],'inventory')
 def test_mutation_and_deleted_prerequisite(self):
  self.seed();self.root.joinpath('source.json').write_text('{}');self.assertEqual(workflow.resume(self.root,local_resume=True)['next_state'],'source_selection')
  (self.root/'session.json').unlink();(self.root/'receipt-index.json').unlink();self.seed();self.root.joinpath('repo/config.txt').unlink();self.assertEqual(workflow.resume(self.root,local_resume=True)['next_state'],'repository_inspection')
 def test_cannot_self_certify(self):
  self.seed('user_review');s=json.loads((self.root/'session.json').read_text());s['completed']=workflow.STAGES;self.write('session.json',s)
  self.assertEqual(workflow.resume(self.root,local_resume=True)['next_state'],'ownership_detection')
 def test_cancel_requires_local_intent(self):
  self.seed();workflow.set_lifecycle(self.root,'cancelled');self.assertEqual(workflow.resume(self.root)['next_state'],'cancelled')
  x=workflow.resume(self.root,local_resume=True);self.assertEqual(x['next_state'],'object_selection');self.assertFalse(x['authorization_reused'])
 def test_corrupt_unknown_and_ambiguous(self):
  self.seed();s=json.loads((self.root/'session.json').read_text());s['in_flight_outcome']='unknown';self.write('session.json',s);self.assertEqual(workflow.resume(self.root,local_resume=True)['next_state'],'reconciliation_required')
  s['schema_version']='0.0.0';self.write('session.json',s);self.assertEqual(workflow.resume(self.root,local_resume=True)['next_state'],'blocked_with_offline_alternative')
 def test_safe_paths_and_symlink(self):
  self.seed();os.symlink(self.root/'source.json',self.root/'linked.json')
  for p in ['../x','/tmp/x','linked.json']:
   with self.assertRaises(workflow.StoreError):workflow.read_bytes(self.root,p)
 def test_cli_create_inspect_resume(self):
  args=[sys.executable,str(R/'tools/session-reference.py')]
  x=subprocess.run(args+['create','--offline','--root',str(self.root),'--saved-state','object_selection'],capture_output=True,text=True)
  self.assertEqual(x.returncode,0,x.stderr)
  for op in ['inspect','resume']:
   x=subprocess.run(args+[op,'--offline','--root',str(self.root),'--resume'],capture_output=True,text=True)
   self.assertEqual(x.returncode,0,x.stderr);self.assertFalse(json.loads(x.stdout)['external_execution'])
 def test_partial_generation_changed_stack_stays_partial(self):
  self.seed('partial_generate');(self.root/'session.json').unlink();(self.root/'receipt-index.json').unlink()
  source=json.loads((self.root/'source.json').read_text())
  chosen='22222222-2222-4222-8222-222222222222'
  for c in source['collections']:
   if c['kind']=='settings' and c['owner_id']==chosen:c['pages'][0]['body']['value'][0]['settingInstance']['settingDefinitionId']='unqualified_definition'
  self.write('source.json',source)
  d=json.loads((self.root/'decisions.json').read_text());d['payload']['ownership']=[{'object_id':chosen,'writer':'this_repository','owner':'developer'}];self.write('decisions.json',d)
  from reference.core import normalize
  self.write('normalized.json',normalize(source,chosen,d['payload']['tenant_id']))
  self.root.joinpath('lock.hcl').write_text('provider "registry.terraform.io/deploymenttheory/microsoft365" { version = "1.0.0" }')
  self.write('provider-schema.json',{'schema_version':'2.0.0','provider_source':'deploymenttheory/microsoft365','provider_version':'1.0.0','api_version':'beta','qualification':'offline_configuration_only','contract_sha256':workflow.sha(workflow.canonical(workflow._contract('provider-settings')))})
  self.root.joinpath('tofu.bin').write_bytes(b'synthetic tofu identity');self.root.joinpath('atmos.bin').write_bytes(b'synthetic atmos identity')
  self.write('provider.json',{'schema_version':'2.0.0','kind':'provider_evidence','payload':{'provider_source':'deploymenttheory/microsoft365','provider_version':'1.0.0','api_version':'beta','engine_version':'1.10.0','atmos_version':'1.199.0','lock_path':'lock.hcl','schema_path':'provider-schema.json','engine_path':'tofu.bin','atmos_path':'atmos.bin','engine_sha256':workflow.sha((self.root/'tofu.bin').read_bytes()),'atmos_sha256':workflow.sha((self.root/'atmos.bin').read_bytes())}})
  rows=[('repository_context','repository.json'),('source','source.json'),('decisions','decisions.json'),('normalized','normalized.json'),('provider_evidence','provider.json')]
  session=workflow.create(self.root,'partial_generate',rows)
  self.assertEqual(session['completed'],workflow.STAGES[:6]);self.assertEqual(session['mapping_status'],'partial')
  session['fingerprints']['stack']='previous_stack';self.write('session.json',session)
  result=workflow.resume(self.root,local_resume=True);self.assertEqual(result['next_state'],'partial_generate');self.assertIn('invalidated:stack',result['reasons'])
 def test_dag_missing_dependency_and_null_receipt_cannot_verify(self):
  self.seed();s=json.loads((self.root/'session.json').read_text());idx=json.loads((self.root/'receipt-index.json').read_text())
  idx['artifacts'][1]['dependencies']=[];self.write('receipt-index.json',idx);s['artifact_index']['byte_sha256']=workflow.sha((self.root/'receipt-index.json').read_bytes());self.write('session.json',s)
  self.assertEqual(workflow.resume(self.root,local_resume=True)['next_state'],'source_selection')
 def test_duplicate_kind_rejected_before_any_receipt_trust(self):
  self.seed();session=json.loads((self.root/'session.json').read_text());idx=json.loads((self.root/'receipt-index.json').read_text())
  duplicate=copy.deepcopy(next(a for a in idx['artifacts'] if a['kind']=='repository_context'));duplicate['artifact_id']='repository_duplicate';idx['artifacts'].append(duplicate)
  for artifact in idx['artifacts']:
   if artifact['kind']!='repository_context':artifact['dependencies'].append({'artifact_id':'repository_duplicate','byte_sha256':duplicate['byte_sha256']})
  for receipt in idx['milestone_receipts']:
   if receipt['milestone']=='repository':receipt['artifact_ids'].append('repository_duplicate')
  self.write('receipt-index.json',idx);session['artifact_index']['byte_sha256']=workflow.sha((self.root/'receipt-index.json').read_bytes());self.write('session.json',session)
  self.assertEqual(workflow.resume(self.root,local_resume=True)['next_state'],'blocked_with_offline_alternative')
  with self.assertRaises(workflow.StoreError):workflow.inspect(self.root)
 def test_malformed_provider_lock_is_controlled_rejection(self):
  self.test_partial_generation_changed_stack_stays_partial();(self.root/'lock.hcl').write_text('provider "unterminated')
  x=workflow.resume(self.root,local_resume=True);self.assertEqual(x['next_state'],'provider_mapping');self.assertFalse(x['external_execution'])
 def test_concurrent_create_cannot_overwrite(self):
  from concurrent.futures import ThreadPoolExecutor
  import threading
  gate=threading.Barrier(2)
  def creator():
   gate.wait()
   try:return workflow.create(self.root,'object_selection')['session_id']
   except workflow.StoreError:return None
  with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:creator(),range(2)))
  winners=[r for r in results if r is not None];self.assertEqual(len(winners),1)
  self.assertEqual(json.loads((self.root/'session.json').read_text())['session_id'],winners[0])
 def test_lifecycle_does_not_reclaim_edited_index(self):
  self.seed();idx=json.loads((self.root/'receipt-index.json').read_text());idx['lifecycle']='active';self.write('receipt-index.json',idx)
  before={p.name:p.read_bytes() for p in [self.root/'session.json',self.root/'receipt-index.json']}
  with self.assertRaises(workflow.StoreError):workflow.set_lifecycle(self.root,'cancelled')
  self.assertEqual(before,{p.name:p.read_bytes() for p in [self.root/'session.json',self.root/'receipt-index.json']})
 def test_structured_approval_malformed_and_object_null_rejected(self):
  a=json.loads((R/'corrections/fixtures/approval-context.json').read_text());b=copy.deepcopy(a)
  b['binding']['identity']['auth_kind']='managed_identity';b['binding']['identity']['federation']=None
  self.assertTrue(approval.mismatches(a,b,'2026-09-30T13:00:00Z'))
  del b['binding']['backend']['resolved_blob_name'];self.assertIn('observed_context_schema',approval.mismatches(a,b,'2026-09-30T13:00:00Z'))
 def test_complete_generated_validated_reviewed_local_handoff(self):
  rows=complete_seed(self.root);session=workflow.create(self.root,'qualification_handoff',rows)
  self.assertEqual(session['completed'],workflow.STAGES);facts=workflow.inspect(self.root);self.assertEqual(facts['errors'],[])
  result=workflow.resume(self.root,local_resume=True);self.assertEqual(result['next_state'],'qualification_handoff');self.assertFalse(result['external_execution'])
 def test_late_actual_byte_mutations_and_missing_validation_receipt(self):
  for mutation,expected in [('closure','generate'),('identity','generate'),('generated','generate'),('extra_config','generate'),('missing_validation','local_validation')]:
   with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temp:
    root=Path(temp);rows=complete_seed(root);session=workflow.create(root,'qualification_handoff',rows)
    if mutation=='closure':
     value=json.loads((root/'effective.json').read_text());value['payload']['inputs'].remove('lock.hcl');(root/'effective.json').write_text(json.dumps(value))
    elif mutation=='identity':
     value=json.loads((root/'identity.json').read_text());value['backend']['key']='another-state';(root/'identity.json').write_text(json.dumps(value))
    elif mutation=='generated':
     target=next((root/'components').rglob('*.tf'));target.write_text(target.read_text()+'\n# changed bytes\n')
    elif mutation=='extra_config':
     target=next((root/'components').rglob('*.tf'));(target.parent/'extra.tf').write_text('resource "x" "y" {}')
    else:
     idx=json.loads((root/'receipt-index.json').read_text());idx['milestone_receipts']=[r for r in idx['milestone_receipts'] if r['milestone']!='validation'];(root/'receipt-index.json').write_text(json.dumps(idx));session['artifact_index']['byte_sha256']=workflow.sha((root/'receipt-index.json').read_bytes());(root/'session.json').write_text(json.dumps(session))
    self.assertEqual(workflow.resume(root,local_resume=True)['next_state'],expected)
 def test_rehashed_stale_repository_binding_is_not_generation_proof(self):
  rows=complete_seed(self.root);identity=json.loads((self.root/'identity.json').read_text());identity['git_revision']='f'*40;(self.root/'identity.json').write_text(json.dumps(identity))
  session=workflow.create(self.root,'qualification_handoff',rows)
  self.assertNotIn('generation',session['completed']);self.assertEqual(workflow.resume(self.root,local_resume=True)['next_state'],'generate')
 def test_legacy_extra_target_fields_bind(self):
  a={k:'value' for k in approval.FIELDS};a.update(engine='tofu',expires_at='2026-10-01T00:00:00Z',cloud='public',backend={'key':'a'},state_key='a');b=copy.deepcopy(a);b['cloud']='other'
  self.assertIn('cloud',approval.mismatches(a,b,'2026-09-30T00:00:00Z'))
if __name__=='__main__':unittest.main()
