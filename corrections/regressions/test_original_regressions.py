"""Desired-behavior regressions against the UNMODIFIED supplied Appendix B.

Set APPENDIX_B_PACK to an extracted copy. Tests run local Python/Bash only.
Failures here are observed defects, not successful repairs or provider runs.
"""
import copy, json, os, subprocess, sys, tempfile, unittest
from pathlib import Path
import yaml
ROOT=Path(os.environ['APPENDIX_B_PACK']).resolve()
sys.path.insert(0,str(ROOT))
from reference.core import normalize, generate_files, render_bash, write_project
from reference.invariants import compare
from reference.approval import mismatches
B=json.loads((ROOT/'examples/supported/input/export.json').read_text())
C=json.loads((ROOT/'examples/context.json').read_text())
T=C['tenant_id']; P=C['selected_policy_id']
def base():return copy.deepcopy(B)
def norm(b):return normalize(b,P,T)
def policy(b):return b['collections'][0]['pages'][0]['body']['value'][0]
def settings(b):return b['collections'][1]['pages'][0]['body']['value']
def assignments(b):return b['collections'][2]['pages'][0]['body']['value']
def approval():
 r={k:'a'*64 for k in ['source_digest','configuration_digest','plan_digest','provider_lock_digest','cohort_digest']}
 r.update(git_revision='b'*40,tenant_id=T,subscription_id='sub',component=C['component'],stack=C['stack'],engine='tofu',engine_version='1.10.0',atmos_version='1.199.0',principal_id='principal',expires_at='2026-09-30T14:00:00Z',cloud='public',state_key='reference/intune.tfstate',backend={'type':'azurerm','storage_account':'account-a','container':'tfstate','key':'reference/intune.tfstate','endpoint':'https://account-a.blob.core.windows.net','workspace':'default'})
 return r
class Regressions(unittest.TestCase):
 def assert_blocked(self,b):
  n=norm(b);f=generate_files(n,C)
  self.assertTrue(n['blockers'],'Semantically incomplete/invalid source was marked complete')
  self.assertFalse(any(x.endswith(('.tf','.tf.json')) for x in f),'Active IaC emitted')
 def test_F01_provider_record_has_exact_required_fields(self):
  self.assertEqual(set(norm(base())['desired']['settings']['settings'][0]),{'id','settingInstance'})
 def test_F01_provider_id_matches_observation(self):
  self.assertEqual(norm(base())['desired']['settings']['settings'][0].get('id'),'0')
 def test_F02_initial_continuation_missing_exclusion(self):
  b=base();b['collections'][2]['pages'][0]['request_url']+='?$skiptoken=second-page';assignments(b).pop();self.assert_blocked(b)
 def test_F02_initial_filtered_collection(self):
  b=base();b['collections'][2]['pages'][0]['request_url']+='?$filter=id%20ne%20null';self.assert_blocked(b)
 def test_F02_initial_projected_collection(self):
  b=base();b['collections'][2]['pages'][0]['request_url']+='?$select=id,target';self.assert_blocked(b)
 def test_F03_empty_setting_record(self):
  b=base();settings(b)[0]={};self.assert_blocked(b)
 def test_F03_empty_settings_zero_count(self):
  b=base();settings(b).clear();policy(b)['settingCount']=0;self.assert_blocked(b)
 def test_F03_choice_boolean_value(self):
  b=base();settings(b)[0]['settingInstance']['choiceSettingValue']['value']=False;self.assert_blocked(b)
 def test_F03_children_string(self):
  b=base();settings(b)[0]['settingInstance']['choiceSettingValue']['children']='not-an-array';self.assert_blocked(b)
 def test_F03_unknown_policy_discriminator(self):
  b=base();policy(b)['@odata.type']='#microsoft.graph.unqualifiedPolicy';self.assert_blocked(b)
 def test_F03_invalid_group_id(self):
  b=base();old=assignments(b)[0]['target']['groupId'];assignments(b)[0]['target']['groupId']='not-a-uuid'
  for r in b['references']:
   if r['id']==old:r['id']='not-a-uuid'
  self.assert_blocked(b)
 def test_F03_zero_include_filter(self):
  b=base();old=assignments(b)[0]['target']['deviceAndAppManagementAssignmentFilterId'];zero='00000000-0000-0000-0000-000000000000';assignments(b)[0]['target']['deviceAndAppManagementAssignmentFilterId']=zero
  for r in b['references']:
   if r['id']==old:r['id']=zero
  self.assert_blocked(b)
 def test_F03_description_too_long(self):
  b=base();policy(b)['description']='x'*1501;self.assert_blocked(b)
 def test_F04_conflicting_reference_order_independent(self):
  b=base();denied=copy.deepcopy(b['references'][0]);denied['coverage']='access_denied';b['references'].insert(0,denied)
  x=norm(b);b['references'].reverse();y=norm(b)
  self.assertFalse(x['offline_mapping_complete']);self.assertFalse(y['offline_mapping_complete'])
 def mutate_oracle(self,fn):
  b=base();n=norm(b);fn(n);self.assertTrue(compare(b,n),'Independent oracle accepted changed invariant')
 def test_F05_changed_key(self):self.mutate_oracle(lambda n:n.update(key='p_'+'9'*32+'_'+'8'*32))
 def test_F05_changed_digest(self):self.mutate_oracle(lambda n:n.update(source_canonical_sha256='0'*64))
 def test_F05_changed_technologies(self):self.mutate_oracle(lambda n:n['desired'].update(technologies=['configManager']))
 def test_F05_removed_references(self):self.mutate_oracle(lambda n:n.update(references=[]))
 def test_F05_wrong_dispositions(self):
  def change(n):
   for r in n['field_accounting']:r.update(disposition='service_owned',loss_blocking=False)
  self.mutate_oracle(change)
 def test_F06_unsupported_canary_not_emitted(self):
  b=base();settings(b)[0]['settingInstance']['unrecognizedField']='UNSUPPORTED_CANARY';n=norm(b);f=generate_files(n,C)
  self.assertNotIn('UNSUPPORTED_CANARY',json.dumps(n)+''.join(f.values()))
 def test_F07_early_resume_does_not_jump_to_preview(self):
  m=yaml.safe_load((ROOT/'wizard/wizard-state-machine.yaml').read_text())
  self.assertNotEqual(m['states']['resume_validation']['on']['review_invalid'],'adoption_preview','Unconditional edge ignores saved progress object_selection')
 def test_F07_partial_resume_uses_dispatch(self):
  m=yaml.safe_load((ROOT/'wizard/wizard-state-machine.yaml').read_text())
  self.assertNotEqual(m['states']['resume_validation']['on']['generation_invalid'],'generate','Unconditional edge bypasses complete/partial dispatcher')
 def test_F07_session_fingerprints_complete(self):
  s=json.loads((ROOT/'contracts/session-state.schema.json').read_text());fields=s['properties']['provenance']['properties']
  self.assertTrue({'selected_ids','ownership','provider_version','plan_digest','identity'}<=set(fields))
 def test_F08_cloud_binding(self):
  a=approval();b=copy.deepcopy(a);b['cloud']='usgov';self.assertTrue(mismatches(a,b,'2026-09-30T13:00:00Z'))
 def test_F08_full_backend_binding(self):
  a=approval();b=copy.deepcopy(a);b['backend']['storage_account']='account-b';self.assertTrue(mismatches(a,b,'2026-09-30T13:00:00Z'))
 def test_F08_state_key_binding(self):
  a=approval();b=copy.deepcopy(a);b['state_key']='other/state';self.assertTrue(mismatches(a,b,'2026-09-30T13:00:00Z'))
 def test_F09_malformed_manifest_is_output_conflict(self):
  with tempfile.TemporaryDirectory() as d:
   dest=Path(d)/'out';write_project(generate_files(norm(base()),C),dest);mf=dest/'generated-files.json';mf.write_text('{broken')
   before={str(p.relative_to(dest)):p.read_bytes() for p in dest.rglob('*') if p.is_file()}
   r=subprocess.run([sys.executable,str(ROOT/'tools/build-reference.py'),'--input',str(ROOT/'examples/supported/input/export.json'),'--context',str(ROOT/'examples/context.json'),'--output',str(dest)],capture_output=True,text=True,timeout=15)
   after={str(p.relative_to(dest)):p.read_bytes() for p in dest.rglob('*') if p.is_file()}
   self.assertEqual(before,after);self.assertEqual(r.returncode,4)
 def test_F09_assignment_like_executable_not_silent_success(self):
  try:s=render_bash('AUDIT=probe',[])
  except ValueError:return
  r=subprocess.run(['bash','-c',s],capture_output=True,text=True,timeout=5)
  self.assertNotEqual(r.returncode,0,'No executable invoked, but script exited successfully')
class ExistingControls(unittest.TestCase):
 def test_supported_source_accepted_by_original(self):self.assertFalse(norm(base())['blockers'])
 def test_denied_collection_blocks(self):
  b=base();b['collections'][2]['coverage']='access_denied';self.assertTrue(norm(b)['blockers'])
 def test_missing_tail_blocks(self):
  b=base();b['collections'][2]['pages'][0]['body']['@odata.nextLink']=b['collections'][2]['pages'][0]['request_url']+'?$skiptoken=more';self.assertTrue(norm(b)['blockers'])
 def test_origin_mismatch_blocks(self):
  b=base();b['collections'][2]['pages'][0]['request_url']='https://invalid.example/assignments';self.assertTrue(norm(b)['blockers'])
 def test_original_import_id_is_preserved(self):self.assertEqual(norm(base())['object_id'],P)
