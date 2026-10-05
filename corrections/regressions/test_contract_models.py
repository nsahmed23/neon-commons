"""Tests of NEW executable specifications, not an integrated repair of Appendix B."""
import copy,json,sys,unittest
from pathlib import Path
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'models'))
from contract_model import (schema_errors,provider_settings,capture_errors,reference_errors,
 resume_decision,approval_mismatches,validate_executable,ContractViolation)
def fixture(n):return json.loads((R/'fixtures'/n).read_text())
class ContractTests(unittest.TestCase):
 def test_schema_definitions(self):
  from jsonschema import Draft202012Validator
  for p in (R/'contracts').glob('*.schema.json'):Draft202012Validator.check_schema(json.loads(p.read_text()))
 def test_all_positive_schema_examples(self):
  for name,f in [('provider-settings','provider-settings.corrected.json'),('observed-setting','observed-setting.json'),('observed-policy','observed-policy.json'),('observed-assignment','observed-assignment.json'),('capture','capture.json'),('session-state','session-early.json'),('approval-context','approval-context.json')]:
   self.assertEqual(schema_errors(name,fixture(f)),[],name)
 def test_provider_projection(self):
  x=fixture('observed-setting.json');self.assertEqual(provider_settings([x]),fixture('provider-settings.corrected.json'))
 def test_provider_ids_not_invented(self):
  for sid in ['1','-1','01','text',3,None]:
   with self.subTest(sid=sid):
    x=fixture('observed-setting.json');x['id']=sid
    with self.assertRaises(ContractViolation):provider_settings([x])
 def test_provider_empty_rejected(self):
  with self.assertRaises(ContractViolation):provider_settings([])
 def test_provider_wrapper_and_values(self):
  for edit in ['wrapper','bool','children','definition','type','unknown']:
   x=fixture('provider-settings.corrected.json');s=x['settings'][0];i=s['settingInstance']
   if edit=='wrapper':s['@odata.type']='anything'
   if edit=='bool':i['choiceSettingValue']['value']=False
   if edit=='children':i['choiceSettingValue']['children']='wrong'
   if edit=='definition':del i['settingDefinitionId']
   if edit=='type':del i['@odata.type']
   if edit=='unknown':i['unknownFuturePayload']='CANARY'
   self.assertTrue(schema_errors('provider-settings',x),edit)
 def test_policy_constraints(self):
  for key,val in [('description','x'*1501),('@odata.type','unknown'),('settingCount',0),('id','not-a-uuid')]:
   x=fixture('observed-policy.json');x[key]=val;self.assertTrue(schema_errors('observed-policy',x),key)
 def test_assignment_constraints(self):
  for key,val in [('groupId','not-a-uuid'),('deviceAndAppManagementAssignmentFilterId','00000000-0000-0000-0000-000000000000'),('deviceAndAppManagementAssignmentFilterType','wrong')]:
   x=fixture('observed-assignment.json');x['target'][key]=val;self.assertTrue(schema_errors('observed-assignment',x),key)
 def test_capture_boundary(self):
  x=fixture('capture.json');root=x['pages'][0]['request_url'];self.assertEqual(capture_errors(x,root),[])
  for q in ['?$skiptoken=two','?$filter=id%20ne%20null','?$select=id','?$top=1']:
   y=copy.deepcopy(x);y['pages'][0]['request_url']+=q;self.assertIn('initial_boundary',capture_errors(y,root))
 def test_capture_chain(self):
  x=fixture('capture.json');root=x['pages'][0]['request_url'];first=x['pages'][0];second=copy.deepcopy(first)
  first['body']['@odata.nextLink']=root+'?$skiptoken=two';second['request_url']=first['body']['@odata.nextLink'];second['body']['value']=[];x['pages'].append(second)
  self.assertEqual(capture_errors(x,root),[])
  x['pages'][1]['http_status']=403;self.assertIn('page_status',capture_errors(x,root))
 def test_capture_missing_tail_loop_projection(self):
  for mode in ['tail','loop','projection','origin']:
   x=fixture('capture.json');root=x['pages'][0]['request_url'];x['pages'][0]['body']['@odata.nextLink']=root+'?$skiptoken=two'
   if mode!='tail':
    y=copy.deepcopy(x['pages'][0]);y['request_url']=root+'?$skiptoken=two';y['body'].pop('@odata.nextLink');x['pages'].append(y)
    if mode=='loop':y['body']['@odata.nextLink']=root
    if mode=='projection':x['pages'][0]['body']['@odata.nextLink']=root+'?$select=id';y['request_url']=root+'?$select=id'
    if mode=='origin':y['request_url']='https://other.invalid/path'
   self.assertTrue(capture_errors(x,root),mode)
 def test_reference_duplicates_order_independent(self):
  a=fixture('source-export.json')['references'];bad=copy.deepcopy(a[0]);bad['coverage']='access_denied'
  self.assertEqual(set(reference_errors([bad]+a)),set(reference_errors(a+[bad])))
  self.assertIn('duplicate_reference',reference_errors([bad]+a));self.assertEqual(reference_errors(a),[])
 def test_early_resume_does_not_advance(self):
  x=fixture('session-early.json');now=copy.deepcopy(x['fingerprints']);now['cohort_digest']='new'
  self.assertEqual(resume_decision(x,now,x['completed'],'unknown')['next_state'],'object_selection')
 def test_partial_resume_uses_dispatch(self):
  x=fixture('session-early.json');x.update(saved_state='partial_generate',completed=['repository','source','inventory','selection','ownership','mapping'],mapping_status='partial');now=copy.deepcopy(x['fingerprints']);now['stack']='new'
  self.assertEqual(resume_decision(x,now,x['completed'],'partial')['next_state'],'partial_generate')
 def test_resume_missing_verified_prerequisite(self):
  x=fixture('session-early.json');self.assertEqual(resume_decision(x,x['fingerprints'],['repository'],'unknown')['next_state'],'source_selection')
 def test_resume_corruption_unknown_inflight(self):
  x=fixture('session-early.json');x['saved_state']='bogus';self.assertEqual(resume_decision(x,x['fingerprints'],[],'unknown')['next_state'],'blocked_with_offline_alternative')
  x=fixture('session-early.json');x['in_flight_outcome']='unknown';self.assertEqual(resume_decision(x,x['fingerprints'],x['completed'],'unknown')['next_state'],'reconciliation_required')
 def test_resume_cartesian_nonadvancement(self):
  model=json.loads((R/'contracts/resume-stage-map.json').read_text());stages=model['stages'];count=0
  for state,frontier in model['state_frontier'].items():
   for key in model['invalidation_frontier']:
    for m in ['unknown','partial','complete']:
     x=fixture('session-early.json');x.update(saved_state=state,completed=stages[:frontier],mapping_status=m);now=copy.deepcopy(x['fingerprints']);now[key]='changed'
     r=resume_decision(x,now,x['completed'],m);self.assertLessEqual(r['milestone_index'],frontier);self.assertFalse(r['external_execution']);count+=1
  self.assertGreater(count,2000)
 def test_approval_all_leaf_changes_detected(self):
  x=fixture('approval-context.json');self.assertEqual(approval_mismatches(x,x['binding'],'2026-09-30T12:30:00Z'),[])
  def paths(v,p=()):
   if isinstance(v,dict):
    for k,w in v.items():yield from paths(w,p+(k,))
   else:yield p
  for path in paths(x['binding']):
   b=copy.deepcopy(x['binding']);node=b
   for k in path[:-1]:node=node[k]
   old=node[path[-1]];node[path[-1]]=old+1 if isinstance(old,int) else ('changed' if old is None else str(old)+'changed')
   self.assertTrue(approval_mismatches(x,b,'2026-09-30T12:30:00Z'),str(path))
 def test_approval_expiry_and_unknown(self):
  x=fixture('approval-context.json');self.assertIn('expired_or_not_yet_valid',approval_mismatches(x,x['binding'],'2026-09-30T13:00:00Z'));x['binding']['backend']['key']=None;self.assertTrue(approval_mismatches(x,x['binding'],'2026-09-30T12:30:00Z'))
 def test_executable_tokens(self):
  for t in ['AUDIT=probe','if','eval','export','-x','a\nb','']:
   with self.subTest(t=t):
    with self.assertRaises(ContractViolation):validate_executable(t)
  self.assertEqual(validate_executable('atmos'),'atmos')

 def test_guid_exact_length_and_nonzero(self):
  for name,filename,path in [('observed-policy','observed-policy.json',('id',)),('observed-assignment','observed-assignment.json',('target','groupId')),('observed-assignment','observed-assignment.json',('target','deviceAndAppManagementAssignmentFilterId'))]:
   for candidate in ['44444444-4444-4444-8444-444444444444','00000000-0000-0000-0000-000000000000']:
    for suffix in ['\n','\r',' ','\t']:
     value=fixture(filename);node=value
     for key in path[:-1]:node=node[key]
     node[path[-1]]=candidate+suffix
     with self.subTest(name=name,path=path,suffix=repr(suffix)):
      self.assertTrue(schema_errors(name,value))
   value=fixture(filename);node=value
   for key in path[:-1]:node=node[key]
   node[path[-1]]='00000000-0000-0000-0000-000000000000'
   self.assertTrue(schema_errors(name,value))

 def test_valid_coupled_auth_transitions(self):
  federated=fixture('approval-context.json')
  for kind in ['managed_identity','application_certificate']:
   alternative=copy.deepcopy(federated);alternative['binding']['identity'].update(auth_kind=kind,federation=None)
   self.assertEqual(schema_errors('approval-context',alternative),[])
   for expected,observed in [(federated,alternative),(alternative,federated)]:
    mismatches=approval_mismatches(expected,observed['binding'],'2026-09-30T12:30:00Z')
    self.assertIn('binding/identity/federation',mismatches)
    self.assertIn('binding/identity/auth_kind',mismatches)

 def test_preview_registry_rejects_builtin_and_unknown_tokens(self):
  for token in ['exit','printf','read','set','cd','echo','return','break','pwd','unregistered-tool']:
   with self.subTest(token=token):
    with self.assertRaises(ContractViolation):validate_executable(token)
  for token in ['atmos','tofu','python',sys.executable]:
   self.assertEqual(validate_executable(token),token)

class ReceiptIndexTests(unittest.TestCase):
 def test_receipt_index_positive(self):
  self.assertEqual(schema_errors('receipt-index',fixture('receipt-index.json')),[])
 def test_receipt_index_rejects_paths(self):
  for path in ['../escape','/absolute','C:\\private','a/../../escape']:
   x=fixture('receipt-index.json');x['artifacts'][0]['relative_path']=path
   self.assertTrue(schema_errors('receipt-index',x),path)
