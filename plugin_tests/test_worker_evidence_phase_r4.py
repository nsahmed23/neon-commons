"""Signed phase-v2 history: actual SQLite/signatures, modeled worker effects."""
import base64,copy,importlib.util,json,sqlite3,subprocess,time,unittest,uuid
from pathlib import Path
from intune_iac import worker_evidence as c,worker_evidence_phase as phase,worker_evidence_posix as host
from intune_iac.io import canonical,digest,AppError
STAGE=Path(c.__file__).parents[1]
spec=importlib.util.spec_from_file_location('phase_domain_fixture',STAGE/'plugin_tests/test_worker_evidence_domains_r4.py');fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
class PhaseEvidenceTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):fixture.DomainEvidenceTests.setUpClass();cls.f=fixture.DomainEvidenceTests.f
 @classmethod
 def tearDownClass(cls):fixture.DomainEvidenceTests.tearDownClass()
 def setUp(self):
  self.d=fixture.DomainEvidenceTests();self.d.setUp();x=self.d;m=x.plan;m['schema_version']=phase.VERSION
  outcome=canonical({'scope':'modeled stopped initial Plan boundary'}).decode();row=[x.manifest['verification_operation_id'],1,'outcome_unknown',outcome]
  selected={'kind':'initial_verification','operation_id':row[0],'manifest_sha256':digest(x.manifest),'job_root':str(x.adoption_root)}
  facts={'operation_id':x.manifest['operation_id'],'manifest_sha256':digest(x.manifest),'status':'outcome_unknown','cancelled':True,'outcome_sha256':'1'*64,'scopes':['2'*64],
   'phase_kind':selected['kind'],'phase_operation_id':selected['operation_id'],'phase_manifest_sha256':selected['manifest_sha256'],'phase_job_root':selected['job_root'],'phase_status':'outcome_unknown','phase_cancelled':True,'phase_outcome_sha256':digest(json.loads(outcome)),'phase_row_sha256':digest(row),'initial_verification_row_sha256':digest(row),'verification_operation_id':selected['operation_id'],'policy_sha256':digest(x.worker_policy),'original_host':{},'phase_host':{},'original_import_journal_sha256':'3'*64,'original_import_state_write':{},'broker_journal_sha256':'4'*64,'host_run_manifest_sha256':'5'*64,'host_run_receipt_sha256':'6'*64,'lease_id':str(uuid.uuid4()),'lock':{},'recorded_metadata':[],'state_contract_sha256':digest(x.manifest['state_contract']),'state_write_attempts':[]}
  m['original_facts']=facts;m['recovery_binding'].update(phase=selected,ancestors=[])
  x.worker_policy['admitted_manifest_sha256']=[digest(x.manifest),digest(m)];x.worker_policy_path.write_bytes(canonical(x.worker_policy));(x.plan_root/'manifest.json').write_bytes(canonical(m))
  for root in (x.adoption_root,x.plan_root):(root/'policy-binding.json').write_bytes(canonical({'policy_sha256':digest(x.worker_policy)}))
  receipt=self.sign_approval(m);p=receipt['payload']
  with sqlite3.connect(x.authority/'service.sqlite3') as db:
   db.execute("UPDATE jobs SET status='outcome_unknown' WHERE id=?",(x.manifest['operation_id'],));db.execute('UPDATE adoption_operations SET verification_dispatches=1,verification_status=?,verification_outcome=? WHERE operation_id=?',('outcome_unknown',outcome,x.manifest['operation_id']))
   db.execute('UPDATE adoption_recovery_plans SET manifest_sha256=? WHERE operation_id=?',(digest(m),m['operation_id']));db.execute('UPDATE consumed SET nonce=?,manifest_sha256=? WHERE operation_id=?',(p['nonce'],digest(m),m['operation_id']));db.execute('UPDATE approval_transcripts SET receipt_json=?,receipt_sha256=?,consumed_at=? WHERE operation_id=?',(canonical(receipt).decode(),digest(receipt),int(time.time()),m['operation_id']))
   for seq,text in db.execute('SELECT sequence,payload FROM events').fetchall():
    value=json.loads(text)
    if value.get('operation_id')==m['operation_id']:value['manifest_sha256']=digest(m);db.execute('UPDATE events SET payload=? WHERE sequence=?',(canonical(value).decode(),seq))
   db.execute('CREATE TABLE native_lease_recoveries(original_operation TEXT PRIMARY KEY,recovery_operation TEXT,issuer TEXT,nonce TEXT,manifest_sha256 TEXT,status TEXT,response_code INTEGER,observed_sha256 TEXT)')
   b=m['recovery_binding'];db.execute('INSERT INTO native_lease_recoveries VALUES(?,?,?,?,?,?,?,?)',(selected['operation_id'],b['recovery_operation_id'],'lab','nonce',b['recovery_manifest_sha256'],'release_observed',200,'8'*64))
   db.execute('CREATE TABLE adoption_plan_successors('+','.join(key+' TEXT' for key in phase.EDGE.split())+')')
   db.execute('INSERT INTO adoption_plan_successors VALUES(?,?,?,?,?,?,?,?)',(m['operation_id'],x.manifest['operation_id'],digest(m),selected['operation_id'],selected['manifest_sha256'],b['recovery_operation_id'],b['recovery_manifest_sha256'],canonical(facts).decode()))
 def sign_approval(self,m):
  p=copy.deepcopy(self.f.receipt['payload']);p.update(schema_version='signed-native-adoption-recovery-plan-approval/2',operation_id=m['operation_id'],manifest_sha256=digest(m),issued_at=m['prepared_at'],expires_at=m['expires_at'],nonce=uuid.uuid4().hex)
  msg=self.d.root/('v2-message-'+uuid.uuid4().hex);sig=self.d.root/('v2-signature-'+uuid.uuid4().hex);msg.write_bytes(b'intune-workbench:native-adoption-recovery-plan-approval:v2\x00'+canonical(p));msg.chmod(0o600)
  subprocess.run(['/usr/bin/openssl','pkeyutl','-sign','-rawin','-inkey',str(self.f.f.fixture.key),'-in',str(msg),'-out',str(sig)],check=True,capture_output=True);sig.chmod(0o600)
  return {'payload':p,'signature':base64.b64encode(sig.read_bytes()).decode()}
 def test_current_v2_phase_full_original_facts_retained_without_authority(self):
  envelope,req=self.d.bundle(True);result=self.d.check(envelope,req)
  self.assertEqual(result['approval_artifact_status'],'verified_retained_original');self.assertEqual(result['review']['manifest']['original_facts'],self.d.plan['original_facts']);self.assertFalse(result['baseline_admissible']);self.assertFalse(result['execution_authorized'])
 def test_actual_cli_v2_prepare_assemble_ingest_reopen_source_unchanged(self):
  x=self.d;before=(x.authority/'service.sqlite3').read_bytes();out=x.root/'v2-cli';out.mkdir(mode=0o700);store=out/'received';store.mkdir(mode=0o700);host.write_new(out/'publisher.json',self.f.publisher)
  x.cli('request','--manifest',x.plan_root/'manifest.json','--trust',x.trust,'--output',out/'request.json')
  x.cli('prepare','--request',out/'request.json','--trust',x.trust,'--publisher',out/'publisher.json','--job-root',x.plan_root,'--policy',x.worker_policy_path,'--output',out/'statement.json')
  signed=self.f.sign(host.load(out/'statement.json'));sig=out/'signature';sig.write_bytes(base64.b64decode(signed['signature']));sig.chmod(0o600);auth=['--trust',x.trust,'--verifier',self.f.verifier_path,'--scratch',self.f.scratch]
  x.cli('assemble',*auth,'--statement',out/'statement.json','--signature',sig,'--request',out/'request.json','--output',out/'envelope.json');first=x.cli('ingest',*auth,'--envelope',out/'envelope.json','--request',out/'request.json','--evidence-store',store);last=x.cli('reopen',*auth,'--request-sha256',digest(host.load(out/'request.json')),'--evidence-store',store)
  self.assertEqual(first['bundle_sha256'],last['bundle_sha256']);self.assertEqual(last['review']['manifest']['schema_version'],phase.VERSION);self.assertFalse(last['baseline_admissible']);self.assertEqual((x.authority/'service.sqlite3').read_bytes(),before)
 def test_resigned_phase_row_edge_release_and_ancestor_substitutions_reject(self):
  envelope,req=self.d.bundle(True)
  changes=[lambda l:l['selected']['row'].__setitem__(1,False),lambda l:l['current_edge'].update(prior_manifest_sha256='0'*64),lambda l:l['current_release'].__setitem__(2,'release_requested'),lambda l:l['ancestors'].append({}),lambda l:l['selected']['manifest'].update(operation_id=str(uuid.uuid4()))]
  for change in changes:
   p=copy.deepcopy(envelope['payload']);change(p['snapshot']['domain_records']['phase_ledger'])
   with self.subTest(change=change),self.assertRaises(AppError):self.d.check(self.f.sign(p),req)
 def test_v1_signature_domain_cannot_authorize_v2(self):
  envelope,req=self.d.bundle(True);p=envelope['payload'];r=p['snapshot']['approval']['receipt'];r['payload']['schema_version']='signed-native-adoption-recovery-plan-approval/1';p['snapshot']['approval']['receipt_sha256']=digest(r)
  with self.assertRaises(AppError):self.d.check(self.f.sign(p),req)
 def test_phase_shape_union_and_chain_limit(self):
  for change in (lambda m:m['recovery_binding']['phase'].update(unknown=True),lambda m:m['recovery_binding'].update(ancestors=[{}]*32),lambda m:m['original_facts'].pop('broker_journal_sha256')):
   m=copy.deepcopy(self.d.plan);change(m)
   with self.assertRaises(AppError):phase.binding(m,self.d.manifest)
 def test_exact_phase_observation_schema_rejects_v1_recovery_label(self):
  envelope,req=self.d.bundle(True);p=envelope['payload'];p['snapshot']['job']['outcome']={'independent_completion':{'fresh_observation':{'schema_version':'adoption-native-lease-recovery-observation/1','adoption_capture':{'capture_sha256':'1'*64,'path':'/literal'}}}}
  with self.assertRaises(AppError):self.d.check(self.f.sign(p),req)
 def successor(self):
  x=self.d;old=copy.deepcopy(x.plan);oldroot=x.plan_root;db=sqlite3.connect(x.authority/'service.sqlite3');outcome=canonical({'scope':'modeled stopped predecessor Plan'}).decode()
  db.execute("UPDATE adoption_recovery_plans SET status='outcome_unknown',outcome=? WHERE operation_id=?",(outcome,old['operation_id']))
  row=list(db.execute('SELECT original_operation_id,manifest_sha256,root,status,cancelled,dispatches,outcome,controller_pid,controller_start FROM adoption_recovery_plans WHERE operation_id=?',(old['operation_id'],)).fetchone())
  selected={'kind':'recovery_plan','operation_id':old['operation_id'],'manifest_sha256':digest(old),'job_root':str(oldroot)}
  new=copy.deepcopy(old);new['operation_id']=str(uuid.uuid4());new['original_facts'].update(phase_kind='recovery_plan',phase_operation_id=old['operation_id'],phase_manifest_sha256=digest(old),phase_job_root=str(oldroot),phase_status='outcome_unknown',phase_cancelled=False,phase_outcome_sha256=digest(json.loads(outcome)),phase_row_sha256=digest(row))
  oldedge=dict(zip(phase.EDGE.split(),db.execute('SELECT '+','.join(phase.EDGE.split())+' FROM adoption_plan_successors WHERE successor_operation_id=?',(old['operation_id'],)).fetchone()))
  oldrelease=list(db.execute('SELECT recovery_operation,manifest_sha256,status,observed_sha256 FROM native_lease_recoveries WHERE original_operation=?',(old['recovery_binding']['phase']['operation_id'],)).fetchone())
  link={key:oldedge[key] for key in ('successor_operation_id','successor_manifest_sha256','prior_operation_id','prior_manifest_sha256','recovery_operation_id','recovery_manifest_sha256')};link.update(prior_phase_sha256=digest(old['original_facts']),release_row=oldrelease)
  new['recovery_binding'].update(phase=selected,ancestors=[link],recovery_operation_id=str(uuid.uuid4()),recovery_manifest_sha256='9'*64)
  x.plan=new;x.plan_root=x.jobs/new['operation_id'];x.plan_root.mkdir(mode=0o700);x.worker_policy['admitted_manifest_sha256'].append(digest(new));x.worker_policy_path.write_bytes(canonical(x.worker_policy))
  host.write_new(x.plan_root/'manifest.json',new);host.write_new(x.plan_root/'policy-binding.json',{'policy_sha256':digest(x.worker_policy)});host.write_new(x.plan_root/'original.json',{'root':str(x.adoption_root),'manifest_sha256':digest(x.manifest)})
  receipt=self.sign_approval(new);p=receipt['payload'];at=int(time.time());db.execute('INSERT INTO adoption_recovery_plans VALUES(?,?,?,?,?,?,?,?,?,?)',(new['operation_id'],new['original_operation_id'],digest(new),str(x.plan_root),'interrupted',0,1,None,None,None));db.execute('INSERT INTO consumed VALUES(?,?,?,?)',(p['issuer'],p['nonce'],new['operation_id'],digest(new)));db.execute('INSERT INTO approval_transcripts VALUES(?,?,?,?)',(new['operation_id'],canonical(receipt).decode(),digest(receipt),at))
  for kind in ('adoption_recovery_plan_prepared','adoption_recovery_plan_consumed'):db.execute('INSERT INTO events(job,kind,payload,created_at) VALUES(?,?,?,?)',(new['original_operation_id'],kind,canonical({'operation_id':new['operation_id'],'manifest_sha256':digest(new)}).decode(),at))
  b=new['recovery_binding'];db.execute('INSERT INTO native_lease_recoveries VALUES(?,?,?,?,?,?,?,?)',(old['operation_id'],b['recovery_operation_id'],'lab','nonce2',b['recovery_manifest_sha256'],'release_observed',200,'a'*64));db.execute('INSERT INTO adoption_plan_successors VALUES(?,?,?,?,?,?,?,?)',(new['operation_id'],new['original_operation_id'],digest(new),old['operation_id'],digest(old),b['recovery_operation_id'],b['recovery_manifest_sha256'],canonical(new['original_facts']).decode()));db.commit();db.close();return old
 def test_nonempty_ancestor_preserves_and_reverifies_predecessor_original_signature(self):
  old=self.successor();envelope,req=self.d.bundle(True);result=self.d.check(envelope,req)
  self.assertEqual(result['approval_artifact_status'],'verified_retained_original');self.assertEqual(len(result['domain_records']['phase_ledger']['ancestors']),1);self.assertFalse(result['baseline_admissible'])
  p=copy.deepcopy(envelope['payload']);record=p['snapshot']['domain_records']['phase_ledger']['selected'];record['approval']['receipt']['signature']=base64.b64encode(bytes(64)).decode();record['approval']['receipt_sha256']=digest(record['approval']['receipt'])
  with self.assertRaises(AppError):self.d.check(self.f.sign(p),req)
 def test_missing_old_plan_transcript_stays_explicitly_unqualified(self):
  old=self.successor()
  with sqlite3.connect(self.d.authority/'service.sqlite3') as db:db.execute('DELETE FROM approval_transcripts WHERE operation_id=?',(old['operation_id'],))
  envelope,req=self.d.bundle(True);result=self.d.check(envelope,req)
  self.assertEqual(result['approval_artifact_status'],'predecessor_plan_approval_not_retained');self.assertFalse(result['baseline_admissible'])
 def test_recorded_native_receiver_reopens_same_v2_domain(self):
  spec=importlib.util.spec_from_file_location('phase_native_received',STAGE/'plugin_tests/test_windows_worker_evidence_store_r4.py');native=importlib.util.module_from_spec(spec);spec.loader.exec_module(native)
  n=native.NativeReceivedEvidenceTests();n.f=self.f;n.setUp();self.addCleanup(n.doCleanups)
  envelope,req=self.d.bundle(True);n.replace('envelope.json',envelope);n.replace('request.json',req);n.replace('trust.json',self.d.policy)
  first=n.ingest();opened=n.reopen(req);self.assertEqual(first['bundle_sha256'],opened['bundle_sha256']);self.assertEqual(opened['review']['manifest']['schema_version'],phase.VERSION);self.assertFalse(opened['graph_deployment']);self.assertFalse(opened['execution_authorized'])

 def resign_current(self,p):
  s=p['snapshot'];m=s['manifest'];req=c.make_request(m,self.d.policy,uuid.uuid4().hex);receipt=self.sign_approval(m)
  s['approval']={'receipt':receipt,'receipt_sha256':digest(receipt),'consumed_at':s['approval']['consumed_at']};s['consumed'].update(nonce=receipt['payload']['nonce'],manifest_sha256=digest(m))
  for event in s['events']:
   if event['payload'].get('operation_id')==m['operation_id']:event['payload']['manifest_sha256']=digest(m)
  s['journal']['events_sha256']=digest(s['events']);s['domain_records']['phase_ledger']['current_edge']['successor_manifest_sha256']=digest(m)
  p.update(request_sha256=digest(req),request_nonce=req['nonce']);return self.f.sign(p),req
 def test_double_signed_v2_predecessor_cannot_omit_its_chain(self):
  self.successor();envelope,req=self.d.bundle(True);p=copy.deepcopy(envelope['payload']);p['snapshot']['manifest']['recovery_binding']['ancestors']=[];p['snapshot']['domain_records']['phase_ledger']['ancestors']=[]
  if 'terminal' in p['snapshot']['domain_records']['phase_ledger']:p['snapshot']['domain_records']['phase_ledger']['terminal']=copy.deepcopy(p['snapshot']['domain_records']['phase_ledger']['selected'])
  altered,req=self.resign_current(p);host.write_new(self.d.root/'omitted-chain-envelope.json',altered);host.write_new(self.d.root/'omitted-chain-request.json',req)
  with self.assertRaises(AppError):self.d.check(altered,req)

 def test_exact_terminal_row_manifest_and_transcript_required(self):
  self.successor();envelope,req=self.d.bundle(True)
  changes=[lambda l:l.pop('terminal'),lambda l:l['terminal']['row'].__setitem__(1,False),lambda l:l['terminal']['manifest'].update(verification_operation_id=str(uuid.uuid4())),lambda l:l['terminal'].update(approval=None),lambda l:l.update(terminal=copy.deepcopy(l['selected']))]
  for change in changes:
   p=copy.deepcopy(envelope['payload']);change(p['snapshot']['domain_records']['phase_ledger'])
   with self.subTest(change=change),self.assertRaises(AppError):self.d.check(self.f.sign(p),req)
 def test_v1_terminal_exports_and_reverifies_its_distinct_original_approval(self):
  x=self.d;old=x.recovery(x.manifest);x.db=sqlite3.connect(x.authority/'service.sqlite3');oldroot=x.register(old);outcome=canonical({'scope':'stopped v1 Plan terminal'}).decode()
  x.db.execute("UPDATE adoption_recovery_plans SET status='outcome_unknown',outcome=? WHERE operation_id=?",(outcome,old['operation_id']));row=list(x.db.execute('SELECT original_operation_id,manifest_sha256,root,status,cancelled,dispatches,outcome,controller_pid,controller_start FROM adoption_recovery_plans WHERE operation_id=?',(old['operation_id'],)).fetchone())
  m=x.plan;b=m['recovery_binding'];p={'kind':'recovery_plan','operation_id':old['operation_id'],'manifest_sha256':digest(old),'job_root':str(oldroot)};b.update(phase=p,ancestors=[])
  m['original_facts'].update(phase_kind=p['kind'],phase_operation_id=p['operation_id'],phase_manifest_sha256=p['manifest_sha256'],phase_job_root=p['job_root'],phase_status='outcome_unknown',phase_cancelled=False,phase_outcome_sha256=digest(json.loads(outcome)),phase_row_sha256=digest(row))
  receipt=self.sign_approval(m);approval=receipt['payload'];at=int(time.time());x.db.execute('UPDATE adoption_recovery_plans SET manifest_sha256=? WHERE operation_id=?',(digest(m),m['operation_id']));x.db.execute('UPDATE consumed SET nonce=?,manifest_sha256=? WHERE operation_id=?',(approval['nonce'],digest(m),m['operation_id']));x.db.execute('UPDATE approval_transcripts SET receipt_json=?,receipt_sha256=?,consumed_at=? WHERE operation_id=?',(canonical(receipt).decode(),digest(receipt),at,m['operation_id']))
  for seq,text in x.db.execute('SELECT sequence,payload FROM events').fetchall():
   value=json.loads(text)
   if value.get('operation_id')==m['operation_id']:value['manifest_sha256']=digest(m);x.db.execute('UPDATE events SET payload=? WHERE sequence=?',(canonical(value).decode(),seq))
  x.db.execute('UPDATE adoption_plan_successors SET successor_manifest_sha256=?,prior_operation_id=?,prior_manifest_sha256=?,prior_phase_json=? WHERE successor_operation_id=?',(digest(m),old['operation_id'],digest(old),canonical(m['original_facts']).decode(),m['operation_id']))
  x.db.execute('INSERT INTO native_lease_recoveries VALUES(?,?,?,?,?,?,?,?)',(old['operation_id'],b['recovery_operation_id'],'lab','nonce-v1',b['recovery_manifest_sha256'],'release_observed',200,'c'*64));x.db.commit();x.db.close()
  x.worker_policy['admitted_manifest_sha256']=[digest(x.manifest),digest(old),digest(m)];x.worker_policy_path.write_bytes(canonical(x.worker_policy));(x.plan_root/'manifest.json').write_bytes(canonical(m));(x.plan_root/'policy-binding.json').write_bytes(canonical({'policy_sha256':digest(x.worker_policy)}))
  envelope,req=x.bundle(True);result=x.check(envelope,req);self.assertEqual(result['approval_artifact_status'],'verified_retained_original');self.assertEqual(result['domain_records']['phase_ledger']['terminal']['manifest']['schema_version'],'native-adoption-recovery-plan/1');self.assertFalse(result['baseline_admissible'])
  bad=copy.deepcopy(envelope['payload']);ledger=bad['snapshot']['domain_records']['phase_ledger']
  for name in ('selected','terminal'):
   ledger[name]['approval']['receipt']['signature']=base64.b64encode(bytes(64)).decode();ledger[name]['approval']['receipt_sha256']=digest(ledger[name]['approval']['receipt'])
  with self.assertRaises(AppError):x.check(self.f.sign(bad),req)

 def test_initial_terminal_remains_history_after_original_current_status_reconciles(self):
  before,req=self.d.bundle(True);self.d.check(before,req)
  with sqlite3.connect(self.d.authority/'service.sqlite3') as db:db.execute("UPDATE jobs SET status='adopted_verified_execution_unknown' WHERE id=?",(self.d.manifest['operation_id'],))
  after,req=self.d.bundle(True);result=self.d.check(after,req)
  self.assertEqual(result['approval_artifact_status'],'verified_retained_original');self.assertFalse(result['baseline_admissible']);self.assertEqual(result['domain_records']['original']['job']['status'],'adopted_verified_execution_unknown')
