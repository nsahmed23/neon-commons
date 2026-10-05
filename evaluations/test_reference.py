"""Offline original-contract tests. Never imports or executes a cloud provider."""
import copy, hashlib, json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from reference.core import normalize, generate_files, render_bash, render_powershell, all_pointers, stable_key, invalidated, write_project, evidence_summary, classify_plan
T='11111111-1111-4111-8111-111111111111'; P='22222222-2222-4222-8222-222222222222'
def load(name='supported'):return json.loads((ROOT/'examples'/name/'input/export.json').read_text())
def context():return json.loads((ROOT/'examples/context.json').read_text())
class ReferenceTests(unittest.TestCase):
 def test_supported_has_no_mapping_blockers(self):self.assertEqual(normalize(load(),P,T)['blockers'],[])
 def test_all_source_nodes_accounted(self):
  b=load();n=normalize(b,P,T); rows=n['field_accounting'];self.assertEqual(set(all_pointers(b)),{r['source_pointer'] for r in rows});self.assertEqual(len(rows),len(set(r['source_pointer'] for r in rows)))
 def test_ids_and_assignments_preserved(self):
  n=normalize(load(),P,T);self.assertEqual(n['object_id'],P);self.assertEqual(len(n['desired']['assignments']),3);self.assertEqual(n['desired']['assignments'][0]['filter_type'],'include');self.assertEqual(n['desired']['assignments'][2]['type'],'exclusionGroupAssignmentTarget')
 def test_name_does_not_determine_key(self):
  b=load();a=normalize(b,P,T);b['collections'][0]['pages'][0]['body']['value'][0]['name']='Renamed';self.assertEqual(a['key'],normalize(b,P,T)['key'])
 def test_duplicate_display_name_not_selected(self):self.assertEqual(normalize(load(),P,T)['object_id'],P)
 def test_id_collision_rejected(self):
  b=load();b['collections'][0]['pages'][0]['body']['value'][1]['id']=P;self.assertTrue(normalize(b,P,T)['blockers'])
 def test_unknown_field_blocks_execution(self):self.assertTrue(normalize(load('partial'),P,T)['blockers'])
 def test_partial_emits_no_active_iac(self):
  f=generate_files(normalize(load('partial'),P,T),context());self.assertFalse(any(p.endswith(('.tf','.tf.json')) for p in f));self.assertIn('BLOCKED.json',f)
 def test_missing_page_blocks_not_empty(self):
  n=normalize(load('missing-page'),P,T);self.assertTrue(n['blockers']);self.assertEqual(len(n['desired']['assignments']),3)
 def test_denied_collection_not_empty_desired(self):
  n=normalize(load('access-denied'),P,T);self.assertTrue(n['blockers']);self.assertIsNone(n['desired']['assignments'])
 def test_forged_complete_nextlink_still_blocks(self):
  b=load('missing-page');b['collections'][2]['coverage']='complete';self.assertTrue(normalize(b,P,T)['blockers'])
 def test_malicious_nextlink_blocks(self):
  b=load();b['collections'][2]['pages'][0]['body']['@odata.nextLink']='https://evil.example/x';self.assertTrue(normalize(b,P,T)['blockers'])
 def test_unknown_polymorph_blocks(self):
  b=load();b['collections'][1]['pages'][0]['body']['value'][0]['settingInstance']['@odata.type']='#microsoft.graph.future';self.assertTrue(normalize(b,P,T)['blockers'])
 def test_absent_null_empty_distinct(self):
  pointer='/collections/0/pages/0/body/value/0/description'
  opaque='opaque:f_'+hashlib.sha256(pointer.encode()).hexdigest()[:24]
  for value,kind in [(None,'null'),('','string'),([],'array')]:
   b=load();b['collections'][0]['pages'][0]['body']['value'][0]['description']=value
   n=normalize(b,P,T)
   row=next(r for r in n['field_accounting'] if r['source_pointer']==(pointer if value=='' else opaque))
   self.assertEqual(row['kind'],kind)
   self.assertEqual(b['collections'][0]['pages'][0]['body']['value'][0]['description'],value)
   if value=='':self.assertEqual(n['observed']['policy']['description'],'')
   else:
    self.assertNotIn('description',n['observed']['policy']);self.assertTrue(row['loss_blocking']);self.assertTrue(n['blockers'])
  b=load();del b['collections'][0]['pages'][0]['body']['value'][0]['description']
  n=normalize(b,P,T);self.assertTrue(n['blockers'])
  self.assertFalse(any(r['source_pointer'] in {pointer,opaque} for r in n['field_accounting']))
 def test_secret_value_not_serialized(self):
  b=load();b['collections'][1]['pages'][0]['body']['value'][0]['settingInstance']['clientSecret']='CANARY_DO_NOT_EMIT';n=normalize(b,P,T);self.assertNotIn('CANARY_DO_NOT_EMIT',json.dumps(n));self.assertTrue(n['blockers'])
 def test_external_writer_blocks(self):
  b=load();b['ownership'][0]['current_writer']='other-controller';self.assertTrue(normalize(b,P,T)['blockers'])
 def test_group_reference_not_owned(self):
  n=normalize(load(),P,T);self.assertTrue(all(x['ownership']=='external' for x in n['references']))
 def test_wrong_tenant_rejected(self):self.assertTrue(normalize(load(),P,'99999999-9999-4999-8999-999999999999')['blockers'])
 def test_wrong_stack_is_rejected(self):
  c=context();c['stack']='production';self.assertRaises(ValueError,generate_files,normalize(load(),P,T),c)
 def test_wrong_engine_is_rejected(self):
  c=context();c['engine']='terraform';self.assertRaises(ValueError,generate_files,normalize(load(),P,T),c)
 def test_wrong_provider_version_is_rejected(self):
  c=context();c['provider_version']='9.9.9';self.assertRaises(ValueError,generate_files,normalize(load(),P,T),c)
 def test_generation_is_stable(self):
  n=normalize(load(),P,T);self.assertEqual(generate_files(n,context()),generate_files(n,context()))
 def test_files_contain_real_import(self):
  f=generate_files(normalize(load(),P,T),context());p=next(v for k,v in f.items() if k.endswith('imports.tf'));self.assertIn(P,p);self.assertNotIn('VERSION-QUALIFIED',p)
 def test_no_live_command_execution_code(self):
  source=(ROOT/'reference/core.py').read_text();self.assertNotIn('subprocess',source);self.assertNotIn('urllib.request',source);self.assertNotIn('os.system',source)
 def test_write_rerun_and_edit_conflict(self):
  f=generate_files(normalize(load(),P,T),context())
  with tempfile.TemporaryDirectory() as d:
   dest=Path(d)/'out';self.assertEqual(write_project(f,dest),'created');self.assertEqual(write_project(f,dest),'unchanged');(dest/'README.md').write_text('user edit');self.assertRaises(FileExistsError,write_project,f,dest)
 def test_path_traversal_is_rejected(self):
  with tempfile.TemporaryDirectory() as d:self.assertRaises(ValueError,write_project,{'../escape':'x'},Path(d)/'out')
 def test_symlink_target_rejected(self):
  if not hasattr(os,'symlink'):self.skipTest('No symlinks')
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'real').mkdir();(p/'link').symlink_to(p/'real',target_is_directory=True);self.assertRaises(ValueError,write_project,{'a':'x'},p/'link'/'out')
 def test_command_rejects_control_chars(self):
  for v in ['bad\x1b[31m','bad\x00','bad\nvalue','bad\rvalue']:
   self.assertRaises(ValueError,render_bash,'python',[v]);self.assertRaises(ValueError,render_powershell,'python',[v])
 def test_bash_argv_roundtrip(self):
  if not shutil.which('bash'):self.skipTest('bash absent')
  values=['','a b',"O'Brien",'a"b',r'C:\Work Space\[pilot]','$HOME','$(touch NEVER)','--leading','emoji-✓','back\\slash','a;b|c&d','`whoami`']
  code='import json,sys;print(json.dumps(sys.argv[1:],ensure_ascii=False))'
  s=render_bash(sys.executable,['-c',code,*values]);p=subprocess.run(['bash','-c',s],capture_output=True,text=True,check=True);self.assertEqual(json.loads(p.stdout),values)
 def test_powershell_quoted_literal(self):
  s=render_powershell('python',["O'Brien",'$HOME']);self.assertIn("'O''Brien'",s);self.assertIn("'$HOME'",s);self.assertIn('$PSNativeCommandArgumentPassing',s)
 def test_resume_invalidation_selective(self):
  self.assertEqual(invalidated({'source_digest'}),['inventory','mapping','generation','review','qualification']);self.assertEqual(invalidated({'cohort_digest'}),['review','qualification'])
 def test_empty_resume_changes_preserves_stages(self):self.assertEqual(invalidated(set()),[])
 def test_pilot_denominators(self):
  rows=[{'id':str(i),'status':'success','fresh':True} for i in range(8)];r=evidence_summary(100,rows);self.assertEqual(r['reporting'],8);self.assertEqual(r['successful'],8);self.assertEqual(r['unknown'],92);self.assertFalse(r['promotion_proven'])
 def test_duplicate_evidence_ids_rejected(self):self.assertRaises(ValueError,evidence_summary,2,[{'id':'x','status':'success','fresh':True}]*2)
 def test_plan_update_not_assumed_state_only(self):self.assertEqual(classify_plan(['update'],None),'requires_effect_evidence')
 def test_plan_replacement_blocks_adoption(self):self.assertEqual(classify_plan(['delete','create'],None),'remote_change')
 def test_state_only_requires_exact_contract(self):self.assertEqual(classify_plan(['update'],'msgraph-0.5.0-ref-update-state-only'),'state_only_by_pinned_source_not_live_proven')
 def test_mutation_guard_detects_lost_exclusion(self):
  n=normalize(load(),P,T);actual=n['desired']['assignments'][:-1];self.assertNotEqual(actual,n['desired']['assignments'])
if __name__=='__main__':unittest.main()
