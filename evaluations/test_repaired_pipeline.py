"""Integrated correction regressions: local artifacts only, never provider execution."""
import copy,json,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from reference.core import normalize,generate_files,render_bash,write_project
B=json.loads((ROOT/'examples/supported/input/export.json').read_text())
C=json.loads((ROOT/'examples/context.json').read_text())
P=C['selected_policy_id'];T=C['tenant_id']
def policy(b):return b['collections'][0]['pages'][0]['body']['value'][0]
def setting(b):return b['collections'][1]['pages'][0]['body']['value'][0]
def assignment(b):return b['collections'][2]['pages'][0]['body']['value'][0]
class PipelineRepairs(unittest.TestCase):
 def blocked(self,b):
  n=normalize(b,P,T);f=generate_files(n,C)
  self.assertTrue(n['blockers']);self.assertFalse(n['offline_mapping_complete'])
  self.assertFalse(any(p.endswith(('.tf','.tf.json')) for p in f))
  self.assertEqual(json.loads(f['commands/command-cards.json'])['cards'],[])
  return n,f
 def test_provider_projection_exact(self):
  n=normalize(copy.deepcopy(B),P,T)
  self.assertEqual(n['blockers'],[])
  self.assertEqual(n['desired']['settings']['settings'],[{'id':'0','settingInstance':setting(B)['settingInstance']}])
 def test_initial_queries_not_complete(self):
  for q in ['?$skiptoken=second','?$filter=id%20ne%20null','?$select=id,target','?$top=1','?$expand=children']:
   with self.subTest(q=q):
    b=copy.deepcopy(B);b['collections'][2]['pages'][0]['request_url']+=q;self.blocked(b)
 def test_malformed_setting_variants(self):
  for mutate in [lambda b:b['collections'][1]['pages'][0]['body']['value'].__setitem__(0,{}),lambda b:setting(b)['settingInstance']['choiceSettingValue'].update(value=False),lambda b:setting(b)['settingInstance']['choiceSettingValue'].update(children='wrong'),lambda b:setting(b).update(id='01')]:
   b=copy.deepcopy(B);mutate(b);self.blocked(b)
 def test_zero_invalid_guids_and_description(self):
  for mutate in [lambda b:assignment(b)['target'].update(groupId='not-a-uuid'),lambda b:assignment(b)['target'].update(deviceAndAppManagementAssignmentFilterId='00000000-0000-0000-0000-000000000000'),lambda b:policy(b).update(description='x'*1501),lambda b:policy(b).update(**{'@odata.type':'#microsoft.graph.future'})]:
   b=copy.deepcopy(B);mutate(b);self.blocked(b)
 def test_duplicate_reference_in_both_orders(self):
  b=copy.deepcopy(B);b['references'].append(copy.deepcopy(b['references'][0]));self.blocked(b);b['references'].reverse();self.blocked(b)
 def test_unknown_value_and_key_canaries_absent(self):
  b=copy.deepcopy(B);setting(b)['settingInstance']['KEY_CANARY_9172']={'known':'VALUE_CANARY_9172'}
  n,f=self.blocked(b);serialized=json.dumps(n)+''.join(f.values())
  self.assertNotIn('KEY_CANARY_9172',serialized);self.assertNotIn('VALUE_CANARY_9172',serialized)
  rows=[r for r in n['field_accounting'] if r['loss_blocking']]
  self.assertTrue(rows);self.assertTrue(all(r['source_pointer'].startswith('opaque:') for r in rows))
 def test_unmapped_capability_review_only(self):
  b=copy.deepcopy(B);setting(b)['settingInstance']['settingDefinitionId']='future_definition';self.blocked(b)
 def test_incomplete_assignment_is_not_empty(self):
  b=copy.deepcopy(B);b['collections'][2]['pages']=[];n,_=self.blocked(b);self.assertIsNone(n['desired']['assignments'])
 def test_unknown_or_malformed_manifest_conflict_preserves_bytes(self):
  f=generate_files(normalize(copy.deepcopy(B),P,T),C)
  for malformed in ['{broken',json.dumps({'schema_version':'99','files':{}}),json.dumps({'schema_version':'1.0.0','files':{'../escape':'0'*64}}),json.dumps([])]:
   with tempfile.TemporaryDirectory() as d:
    dest=Path(d)/'out';write_project(f,dest);(dest/'generated-files.json').write_text(malformed)
    before={str(p.relative_to(dest)):p.read_bytes() for p in dest.rglob('*') if p.is_file()}
    with self.assertRaises(FileExistsError):write_project(f,dest)
    self.assertEqual(before,{str(p.relative_to(dest)):p.read_bytes() for p in dest.rglob('*') if p.is_file()})
 def test_real_cli_owned_symlink_conflict_preserves_bytes(self):
  for entry in ['README.md','adoption']:
   with self.subTest(entry=entry),tempfile.TemporaryDirectory() as d:
    dest=Path(d)/'out'
    argv=[sys.executable,str(ROOT/'tools/build-reference.py'),'--input',str(ROOT/'examples/supported/input/export.json'),'--context',str(ROOT/'examples/context.json'),'--output',str(dest)]
    created=subprocess.run(argv,capture_output=True,text=True,timeout=20)
    self.assertEqual(created.returncode,0,created.stderr)
    owned=json.loads((dest/'generated-files.json').read_text())['files']
    outside=Path(d)/'outside';(dest/entry).rename(outside)
    (dest/entry).symlink_to(outside,target_is_directory=outside.is_dir())
    before={name:(dest/name).read_bytes() for name in owned}
    manifest_before=(dest/'generated-files.json').read_bytes()
    rerun=subprocess.run(argv,capture_output=True,text=True,timeout=20)
    self.assertEqual(rerun.returncode,4,rerun.stderr)
    self.assertIn('Output conflict',rerun.stderr)
    self.assertEqual(before,{name:(dest/name).read_bytes() for name in owned})
    self.assertEqual(manifest_before,(dest/'generated-files.json').read_bytes())
    self.assertTrue((dest/entry).is_symlink())
    self.assertEqual((dest/entry).readlink(),outside)
 def test_real_cli_unowned_output_conflict_preserves_bytes(self):
  for extra in ['components/terraform/intune-reference/user.tf','stacks/extra.yaml','unlisted-directory-link']:
   with self.subTest(extra=extra),tempfile.TemporaryDirectory() as d:
    dest=Path(d)/'out'
    argv=[sys.executable,str(ROOT/'tools/build-reference.py'),'--input',str(ROOT/'examples/supported/input/export.json'),'--context',str(ROOT/'examples/context.json'),'--output',str(dest)]
    created=subprocess.run(argv,capture_output=True,text=True,timeout=20)
    self.assertEqual(created.returncode,0,created.stderr)
    added=dest/extra;added.parent.mkdir(parents=True,exist_ok=True)
    if extra=='unlisted-directory-link':
     outside=Path(d)/'outside';outside.mkdir();(outside/'canary.txt').write_text('KEEP_OUTSIDE')
     added.symlink_to(outside,target_is_directory=True)
    else:added.write_text('resource "unowned" "canary" {}' if extra.endswith('.tf') else 'canary: KEEP_CONFIG')
    before={str(p.relative_to(dest)):p.read_bytes() for p in dest.rglob('*') if p.is_file()}
    rerun=subprocess.run(argv,capture_output=True,text=True,timeout=20)
    self.assertEqual(rerun.returncode,4,rerun.stderr)
    self.assertIn('Output conflict',rerun.stderr)
    self.assertEqual(before,{str(p.relative_to(dest)):p.read_bytes() for p in dest.rglob('*') if p.is_file()})
    if extra=='unlisted-directory-link':
     self.assertTrue(added.is_symlink());self.assertEqual(added.readlink(),outside)
     self.assertEqual((outside/'canary.txt').read_text(),'KEEP_OUTSIDE')
 def test_executable_registry_and_trusted_python(self):
  for executable in ['AUDIT=probe','eval','exec','true','if','-python','unknown-executable']:
   with self.subTest(executable=executable):
    with self.assertRaises(ValueError):render_bash(executable,[])
  code='import json,sys;print(json.dumps(sys.argv[1:]))';args=['','a b',"O'Brien",'$(touch NEVER)','--leading']
  result=subprocess.run(['bash','-c',render_bash(sys.executable,['-c',code,*args])],capture_output=True,text=True,check=True)
  self.assertEqual(json.loads(result.stdout),args)
 def test_generation_context_selected_and_versions(self):
  n=normalize(copy.deepcopy(B),P,T)
  for change in [{'selected_policy_id':'33333333-3333-4333-8333-333333333333'},{'schema_version':'99'},{'engine_version':'9'},{'atmos_version':'9'}]:
   with self.assertRaises(ValueError):generate_files(n,{**C,**change})
 def test_malformed_record_values_safe(self):
  for mutate in [lambda b:setting(b).update(id=[]),lambda b:assignment(b).update(id={}),lambda b:b['references'][0].update(id=[]),lambda b:b['collections'][0].update(owner_id={}),lambda b:b['collections'][2]['pages'][0].update(request_url=[])]:
   b=copy.deepcopy(B);mutate(b);self.blocked(b)
 def test_normalized_guard_flags_rejected(self):
  good=normalize(copy.deepcopy(B),P,T)
  for change in [{'execution_authorized':True},{'live_qualification':'passed'},{'offline_mapping_complete':False}]:
   with self.assertRaises(ValueError):generate_files({**good,**change},C)
 def test_forged_mapping_complete_rejected(self):
  n=normalize(copy.deepcopy(B),P,T);n['desired']['settings']['settings'][0]['id']='17'
  with self.assertRaises(ValueError):generate_files(n,C)
if __name__=='__main__':unittest.main()
