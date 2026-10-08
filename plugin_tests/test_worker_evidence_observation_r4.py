"""Signed v3 read-only history with actual SQLite/CLI, modeled phase effects."""
import base64,copy,importlib.util,json,sqlite3,subprocess,time,unittest,uuid
from pathlib import Path
from intune_iac import worker_evidence as c,worker_evidence_observation as o,worker_evidence_posix as host
from intune_iac.io import canonical,digest,AppError
ROOT=Path(c.__file__).parents[1]
spec=importlib.util.spec_from_file_location('phase_observation_fixture',ROOT/'plugin_tests/test_worker_evidence_phase_r4.py');base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
class ObservationPhaseTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):base.PhaseEvidenceTests.setUpClass();cls.f=base.PhaseEvidenceTests.f
 @classmethod
 def tearDownClass(cls):base.PhaseEvidenceTests.tearDownClass()
 def setUp(self):
  self.inner=base.PhaseEvidenceTests();self.inner.setUp();self.inner.successor();self.d=self.inner.d;x=self.d;m=x.plan;m['schema_version']=o.VERSION
  facts=m['original_facts']
  for key in ('lease_id','lock','recorded_metadata','state_write_attempts'):facts.pop(key)
  facts.update(broker_inspection_sha256='d'*64,backend_attempt_count=0,native_lease_request_count=0,state_write_attempt_count=0)
  backend=copy.deepcopy(m['provider_binding']['backend']);backend['identity']={'tenant_id':m['provider_binding']['tenant_id'],'client_id':str(uuid.uuid4()),'principal_object_id':str(uuid.uuid4()),'auth_method':'client_secret'};target=backend['backend'];target.update(state_lineage=str(uuid.uuid4()),state_serial=13,state_sha256='a'*64,container='fixture',key='fixture.tfstate',workspace='default');m['provider_binding']['backend']=backend;state={'lineage':target['state_lineage'],'serial':target['state_serial'],'sha256':target['state_sha256'],'semantic_sha256':'b'*64,'etag':'"fixture"','bytes':123}
  proof={key:'c'*64 for key in o.PROJECTION.split()};proof.update(classification='approved_adoption_successor',graph_unchanged=True,original_contract_sha256=digest(x.manifest['state_contract']))
  identifier=str(uuid.uuid4());root=x.root/'unacquired';root.mkdir(mode=0o700)
  fresh={'schema_version':'adoption-plan-unacquired-fresh-observation/1','profile':'laboratory_unacquired_adoption_plan','original':copy.deepcopy(facts),
   'identity':copy.deepcopy(backend['identity']),'backend_target':copy.deepcopy(target),'identity_binding_sha256':m['identity_binding_sha256'],
   'state':state,'metadata':{},'locked':False,'adoption_state_proof':proof,'adoption_capture':{'capture_sha256':'f'*64,'path':str(root/'capture')},'state_artifact_sha256':state['sha256'],
   'observed_at':int(time.time()),'storage_binding_sha256':m['storage_binding_sha256'],'classification':o.CLASSIFICATION,'release_performed':False,'execution_authorized':False,'platform_qualified':False}
  anchor={'schema_version':'adoption-plan-unacquired-anchor/1','observation_id':identifier,'classification':o.CLASSIFICATION,'service_authority_root':str(x.authority),'original':copy.deepcopy(facts),'initial_observation':fresh,'implementation_files':{'intune_iac/fixture.py':'a'*64}}
  host.write_new(root/'anchor.json',anchor);prior=m['recovery_binding'];m['recovery_binding']={'resolution_kind':o.KIND,'observation_id':identifier,'anchor_sha256':digest(anchor),'state':state,'projection_sha256':digest({k:proof[k] for k in o.PROJECTION.split()}),'original_contract_sha256':digest(x.manifest['state_contract']),'phase':prior['phase'],'ancestors':prior['ancestors']}
  x.worker_policy['admitted_manifest_sha256'].append(digest(m));x.worker_policy_path.write_bytes(canonical(x.worker_policy));(x.plan_root/'manifest.json').write_bytes(canonical(m));(x.plan_root/'policy-binding.json').write_bytes(canonical({'policy_sha256':digest(x.worker_policy)}))
  receipt=self.sign(m);p=receipt['payload'];at=int(time.time());b=m['recovery_binding'];phase=b['phase']
  with sqlite3.connect(x.authority/'service.sqlite3') as db:
   db.execute('UPDATE adoption_recovery_plans SET manifest_sha256=? WHERE operation_id=?',(digest(m),m['operation_id']));db.execute('UPDATE consumed SET nonce=?,manifest_sha256=? WHERE operation_id=?',(p['nonce'],digest(m),m['operation_id']));db.execute('UPDATE approval_transcripts SET receipt_json=?,receipt_sha256=?,consumed_at=? WHERE operation_id=?',(canonical(receipt).decode(),digest(receipt),at,m['operation_id']))
   for seq,text in db.execute('SELECT sequence,payload FROM events').fetchall():
    value=json.loads(text)
    if value.get('operation_id')==m['operation_id']:value['manifest_sha256']=digest(m);db.execute('UPDATE events SET payload=?,created_at=? WHERE sequence=?',(canonical(value).decode(),at,seq))
   db.execute('DELETE FROM adoption_plan_successors WHERE successor_operation_id=?',(m['operation_id'],))
   db.execute('CREATE TABLE adoption_plan_unacquired_observations('+','.join(k+' TEXT' for k in o.ROW.split())+')');db.execute('INSERT INTO adoption_plan_unacquired_observations VALUES(?,?,?,?,?,?)',(identifier,m['original_operation_id'],phase['operation_id'],phase['manifest_sha256'],digest(anchor),str(root/'anchor.json')))
   db.execute('CREATE TABLE adoption_plan_observation_successors('+','.join(k+' TEXT' for k in o.EDGE.split())+')');db.execute('INSERT INTO adoption_plan_observation_successors VALUES(?,?,?,?,?,?,?,?)',(m['operation_id'],m['original_operation_id'],digest(m),phase['operation_id'],phase['manifest_sha256'],identifier,digest(anchor),canonical(facts).decode()))
  self.anchor=anchor;self.anchor_root=root
 def sign(self,m):
  p=copy.deepcopy(self.f.receipt['payload']);p.update(schema_version='signed-native-adoption-recovery-plan-approval/3',operation_id=m['operation_id'],manifest_sha256=digest(m),issued_at=m['prepared_at'],expires_at=m['expires_at'],nonce=uuid.uuid4().hex)
  message=self.d.root/('v3-message-'+uuid.uuid4().hex);signature=self.d.root/('v3-signature-'+uuid.uuid4().hex);message.write_bytes(b'intune-workbench:native-adoption-recovery-plan-approval:v3\x00'+canonical(p));message.chmod(0o600)
  subprocess.run(['/usr/bin/openssl','pkeyutl','-sign','-rawin','-inkey',str(self.f.f.fixture.key),'-in',str(message),'-out',str(signature)],check=True,capture_output=True);signature.chmod(0o600)
  return {'payload':p,'signature':base64.b64encode(signature.read_bytes()).decode()}
 def test_observation_current_and_release_ancestor_stay_distinct_signed_history(self):
  envelope,req=self.d.bundle(True);result=self.d.check(envelope,req);ledger=result['domain_records']['phase_ledger']
  self.assertEqual(result['approval_artifact_status'],'verified_retained_original');self.assertIn('current_observation',ledger);self.assertNotIn('current_release',ledger);self.assertIn('release',ledger['ancestors'][0]);self.assertFalse(result['baseline_admissible']);self.assertFalse(result['graph_deployment'])
 def test_wrong_observation_row_anchor_or_release_substitution_rejected(self):
  envelope,req=self.d.bundle(True)
  changes=[lambda l:l['current_observation']['row'].__setitem__(2,str(uuid.uuid4())),lambda l:l['current_observation']['anchor'].update(sha256='0'*64),lambda l:l.update(current_release=l.pop('current_observation')),lambda l:l['current_edge'].update(recovery_operation_id=str(uuid.uuid4()))]
  for change in changes:
   p=copy.deepcopy(envelope['payload']);change(p['snapshot']['domain_records']['phase_ledger'])
   with self.subTest(change=change),self.assertRaises(AppError):self.d.check(self.f.sign(p),req)
 def test_strict_zero_counts_and_no_release_fields(self):
  from intune_iac import worker_evidence_phase as phase
  for key,value in [('backend_attempt_count',False),('native_lease_request_count',1),('state_write_attempt_count',1)]:
   m=copy.deepcopy(self.d.plan);m['original_facts'][key]=value
   with self.subTest(key=key),self.assertRaises(AppError):phase.binding(m,self.d.manifest)
  m=copy.deepcopy(self.d.plan);m['original_facts']['lease_id']=str(uuid.uuid4())
  with self.assertRaises(AppError):phase.binding(m,self.d.manifest)
 def test_signature_domain_three_cannot_be_replaced_with_two(self):
  envelope,req=self.d.bundle(True);p=envelope['payload'];receipt=p['snapshot']['approval']['receipt'];receipt['payload']['schema_version']='signed-native-adoption-recovery-plan-approval/2';p['snapshot']['approval']['receipt_sha256']=digest(receipt)
  with self.assertRaises(AppError):self.d.check(self.f.sign(p),req)
 def test_actual_cli_observation_chain_preserves_bytes_and_original_source(self):
  x=self.d;before=(x.authority/'service.sqlite3').read_bytes();anchor_before=(self.anchor_root/'anchor.json').read_bytes();out=x.root/'cli-v3';out.mkdir(mode=0o700);(out/'received').mkdir(mode=0o700);host.write_new(out/'publisher.json',self.f.publisher)
  x.cli('request','--manifest',x.plan_root/'manifest.json','--trust',x.trust,'--output',out/'request.json');x.cli('prepare','--request',out/'request.json','--trust',x.trust,'--publisher',out/'publisher.json','--job-root',x.plan_root,'--policy',x.worker_policy_path,'--output',out/'statement.json')
  signed=self.f.sign(host.load(out/'statement.json'));signature=out/'signature';signature.write_bytes(base64.b64decode(signed['signature']));signature.chmod(0o600);auth=['--trust',x.trust,'--verifier',self.f.verifier_path,'--scratch',self.f.scratch]
  x.cli('assemble',*auth,'--statement',out/'statement.json','--signature',signature,'--request',out/'request.json','--output',out/'envelope.json');first=x.cli('ingest',*auth,'--envelope',out/'envelope.json','--request',out/'request.json','--evidence-store',out/'received');last=x.cli('reopen',*auth,'--request-sha256',digest(host.load(out/'request.json')),'--evidence-store',out/'received')
  self.assertEqual(first['bundle_sha256'],last['bundle_sha256']);self.assertEqual(last['review']['manifest']['schema_version'],o.VERSION);self.assertFalse(last['baseline_admissible']);self.assertFalse(last['graph_deployment']);self.assertEqual((x.authority/'service.sqlite3').read_bytes(),before);self.assertEqual((self.anchor_root/'anchor.json').read_bytes(),anchor_before)
 def completed_facts(self):
  b=self.d.plan['recovery_binding'];row=[b['observation_id'],self.d.plan['original_operation_id'],b['phase']['operation_id'],b['phase']['manifest_sha256'],b['anchor_sha256'],str(self.anchor_root/'anchor.json')];fresh=copy.deepcopy(self.anchor['initial_observation'])
  return {'schema_version':'adoption-plan-unacquired-observation/1','profile':fresh['profile'],'classification':o.CLASSIFICATION,'observation_id':b['observation_id'],'anchor_sha256':b['anchor_sha256'],'anchor_path':row[5],'anchor_row':row,
   'original':fresh['original'],'service_authority_root':str(self.d.authority),'fresh_observation':fresh,'fresh_observation_sha256':digest(fresh),'initial_state_etag':fresh['state']['etag'],'current_state_etag':fresh['state']['etag'],
   'etag_changed_since_assessment':False,'etag_change_cause':'unchanged','lease_independently_unlocked':True,'lock_metadata_remaining':False,'release_performed':False,'ownership_release_authorized':False,'platform_qualified':False,'production_approved':False}
 def test_completed_observation_never_claims_release_and_rejects_contradictions(self):
  envelope,req=self.d.bundle(True);p=envelope['payload'];s=p['snapshot'];facts=self.completed_facts();m=self.d.plan
  s['job']['outcome']={'independent_completion':facts,'original_operation_id':m['original_operation_id'],'original_manifest_sha256':m['original_manifest_sha256'],'recovery_plan_operation_id':m['operation_id'],'recovery_plan_manifest_sha256':digest(m),'reservation_released':True,'import_replayed':False,'graph_mutated':False}
  result=self.d.check(self.f.sign(p),req);self.assertFalse(result['baseline_admissible']);self.assertFalse(result['graph_deployment'])
  for key,value in [('release_performed',True),('ownership_release_authorized',True),('lock_metadata_remaining',True),('anchor_sha256','0'*64),('etag_changed_since_assessment',0)]:
   bad=copy.deepcopy(p);bad['snapshot']['job']['outcome']['independent_completion'][key]=value
   with self.subTest(key=key),self.assertRaises(AppError):self.d.check(self.f.sign(bad),req)
 def next_observation_successor(self):
  x=self.d;old=copy.deepcopy(x.plan);oldroot=x.plan_root;outcome=canonical({'scope':'modeled stopped observation-authorized Plan'}).decode();db=sqlite3.connect(x.authority/'service.sqlite3')
  db.execute("UPDATE adoption_recovery_plans SET status='outcome_unknown',outcome=? WHERE operation_id=?",(outcome,old['operation_id']));row=list(db.execute('SELECT original_operation_id,manifest_sha256,root,status,cancelled,dispatches,outcome,controller_pid,controller_start FROM adoption_recovery_plans WHERE operation_id=?',(old['operation_id'],)).fetchone())
  edge=dict(zip(o.EDGE.split(),db.execute('SELECT '+','.join(o.EDGE.split())+' FROM adoption_plan_observation_successors WHERE successor_operation_id=?',(old['operation_id'],)).fetchone()));orow=list(db.execute('SELECT '+','.join(o.ROW.split())+' FROM adoption_plan_unacquired_observations WHERE observation_id=?',(old['recovery_binding']['observation_id'],)).fetchone())
  link={key:edge[key] for key in ('successor_operation_id','successor_manifest_sha256','prior_operation_id','prior_manifest_sha256','observation_id','anchor_sha256')};link.update(resolution_kind=o.KIND,prior_phase_sha256=digest(old['original_facts']),observation_row=orow)
  m=copy.deepcopy(old);m['operation_id']=str(uuid.uuid4());facts=m['original_facts'];facts.update(phase_kind='recovery_plan',phase_operation_id=old['operation_id'],phase_manifest_sha256=digest(old),phase_job_root=str(oldroot),phase_status='outcome_unknown',phase_cancelled=False,phase_outcome_sha256=digest(json.loads(outcome)),phase_row_sha256=digest(row))
  a=copy.deepcopy(self.anchor);a['observation_id']=str(uuid.uuid4());a['original']=copy.deepcopy(facts);a['initial_observation']['original']=copy.deepcopy(facts);self.anchor_root=x.root/'unacquired-next';self.anchor_root.mkdir(mode=0o700);host.write_new(self.anchor_root/'anchor.json',a);self.anchor=a
  b=m['recovery_binding'];b.update(observation_id=a['observation_id'],anchor_sha256=digest(a),phase={'kind':'recovery_plan','operation_id':old['operation_id'],'manifest_sha256':digest(old),'job_root':str(oldroot)},ancestors=[link]+old['recovery_binding']['ancestors'])
  x.plan=m;x.plan_root=x.jobs/m['operation_id'];x.plan_root.mkdir(mode=0o700);x.worker_policy['admitted_manifest_sha256'].append(digest(m));x.worker_policy_path.write_bytes(canonical(x.worker_policy));host.write_new(x.plan_root/'manifest.json',m);host.write_new(x.plan_root/'policy-binding.json',{'policy_sha256':digest(x.worker_policy)});host.write_new(x.plan_root/'original.json',{'root':str(x.adoption_root),'manifest_sha256':digest(x.manifest)})
  receipt=self.sign(m);p=receipt['payload'];at=int(time.time());db.execute('INSERT INTO adoption_recovery_plans VALUES(?,?,?,?,?,?,?,?,?,?)',(m['operation_id'],m['original_operation_id'],digest(m),str(x.plan_root),'interrupted',0,1,None,None,None));db.execute('INSERT INTO consumed VALUES(?,?,?,?)',(p['issuer'],p['nonce'],m['operation_id'],digest(m)));db.execute('INSERT INTO approval_transcripts VALUES(?,?,?,?)',(m['operation_id'],canonical(receipt).decode(),digest(receipt),at))
  for kind in ('adoption_recovery_plan_prepared','adoption_recovery_plan_consumed'):db.execute('INSERT INTO events(job,kind,payload,created_at) VALUES(?,?,?,?)',(m['original_operation_id'],kind,canonical({'operation_id':m['operation_id'],'manifest_sha256':digest(m)}).decode(),at))
  db.execute('INSERT INTO adoption_plan_unacquired_observations VALUES(?,?,?,?,?,?)',(a['observation_id'],m['original_operation_id'],old['operation_id'],digest(old),digest(a),str(self.anchor_root/'anchor.json')));db.execute('INSERT INTO adoption_plan_observation_successors VALUES(?,?,?,?,?,?,?,?)',(m['operation_id'],m['original_operation_id'],digest(m),old['operation_id'],digest(old),a['observation_id'],digest(a),canonical(facts).decode()));db.commit();db.close()
 def test_mixed_observation_and_release_ancestors_verify_original_domains(self):
  self.next_observation_successor();envelope,req=self.d.bundle(True);result=self.d.check(envelope,req);chain=result['domain_records']['phase_ledger']['ancestors']
  self.assertIn('observation',chain[0]);self.assertIn('release',chain[1]);self.assertEqual(result['approval_artifact_status'],'verified_retained_original');self.assertFalse(result['execution_authorized'])
 def test_double_signed_observation_predecessor_cannot_omit_its_edge(self):
  self.next_observation_successor();envelope,req=self.d.bundle(True);p=envelope['payload'];s=p['snapshot'];m=s['manifest'];ledger=s['domain_records']['phase_ledger'];m['recovery_binding']['ancestors']=[];ledger['ancestors']=[];ledger['terminal']=copy.deepcopy(ledger['selected'])
  req=c.make_request(m,self.d.policy,uuid.uuid4().hex);receipt=self.sign(m);s['approval']={'receipt':receipt,'receipt_sha256':digest(receipt),'consumed_at':s['approval']['consumed_at']};s['consumed'].update(nonce=receipt['payload']['nonce'],manifest_sha256=digest(m));ledger['current_edge']['successor_manifest_sha256']=digest(m)
  for event in s['events']:
   if event['payload'].get('operation_id')==m['operation_id']:event['payload']['manifest_sha256']=digest(m)
  s['journal']['events_sha256']=digest(s['events']);p.update(request_sha256=digest(req),request_nonce=req['nonce'])
  with self.assertRaises(AppError):self.d.check(self.f.sign(p),req)
 def test_opposite_kind_duplicate_edge_in_source_rejected(self):
  m=self.d.plan;b=m['recovery_binding'];phase=b['phase']
  with sqlite3.connect(self.d.authority/'service.sqlite3') as db:db.execute('INSERT INTO adoption_plan_successors VALUES(?,?,?,?,?,?,?,?)',(m['operation_id'],m['original_operation_id'],digest(m),phase['operation_id'],phase['manifest_sha256'],str(uuid.uuid4()),'a'*64,canonical(m['original_facts']).decode()))
  with self.assertRaises(AppError):self.d.bundle(True)

 def test_observation_identity_and_exact_backend_are_bound(self):
  for kind in ('principal','container','binding','storage'):
   fresh=copy.deepcopy(self.anchor['initial_observation'])
   if kind=='principal':fresh['identity']['principal_object_id']=str(uuid.uuid4())
   elif kind=='container':fresh['backend_target']['container']='different-fixture'
   elif kind=='binding':fresh['identity_binding_sha256']='0'*64
   else:fresh['storage_binding_sha256']='0'*64
   with self.subTest(kind=kind),self.assertRaises(AppError):o.fresh(fresh,self.d.plan,int(time.time()))

 def test_completed_etag_rebinding_retains_historical_and_current_hashes(self):
  envelope,req=self.d.bundle(True);p=envelope['payload'];s=p['snapshot'];facts=self.completed_facts();m=self.d.plan
  fresh=facts['fresh_observation'];fresh['state']['etag']='"fixture-after-plan"';fresh['identity_binding_sha256']='1'*64
  facts.update(fresh_observation_sha256=digest(fresh),current_state_etag=fresh['state']['etag'],etag_changed_since_assessment=True,etag_change_cause='unestablished')
  s['job']['outcome']={'independent_completion':facts,'original_operation_id':m['original_operation_id'],'original_manifest_sha256':m['original_manifest_sha256'],'recovery_plan_operation_id':m['operation_id'],'recovery_plan_manifest_sha256':digest(m),'reservation_released':True,'import_replayed':False,'graph_mutated':False}
  result=self.d.check(self.f.sign(p),req);history=result['observation_identity_binding_history']
  self.assertEqual(history['signed_pre_plan_sha256'],m['identity_binding_sha256']);self.assertEqual(history['anchor_initial_sha256'],m['identity_binding_sha256']);self.assertEqual(history['completed_observation_sha256'],'1'*64);self.assertTrue(history['completed_differs_from_pre_plan']);self.assertFalse(result['baseline_admissible'])
  for kind in ('principal','backend','storage','state'):
   bad=copy.deepcopy(p);changed=bad['snapshot']['job']['outcome']['independent_completion'];f=changed['fresh_observation']
   if kind=='principal':f['identity']['principal_object_id']=str(uuid.uuid4())
   elif kind=='backend':f['backend_target']['container']='other-fixture'
   elif kind=='storage':f['storage_binding_sha256']='2'*64
   else:f['state']['sha256']='3'*64;f['state_artifact_sha256']='3'*64
   changed['fresh_observation_sha256']=digest(f)
   with self.subTest(kind=kind),self.assertRaises(AppError):self.d.check(self.f.sign(bad),req)
