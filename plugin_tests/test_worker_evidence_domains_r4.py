"""Real signed/SQLite/CLI domain history; modeled worker boundary, no native run."""
import base64,copy,hashlib,importlib.util,json,os,sqlite3,subprocess,time,unittest,uuid
from pathlib import Path
from intune_iac import worker_evidence as c,worker_evidence_posix as host,worker_evidence_domains as domains
from intune_iac.io import AppError,canonical,digest
STAGE=Path(c.__file__).parents[1]
spec=importlib.util.spec_from_file_location('domain_evidence_fixture',STAGE/'plugin_tests/test_worker_evidence_r4.py');fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)

class DomainEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixture.EvidenceTests.setUpClass();cls.f=fixture.EvidenceTests
    @classmethod
    def tearDownClass(cls):fixture.EvidenceTests.tearDownClass()
    def setUp(self):
        self.root=self.f.root/('domain-'+uuid.uuid4().hex);self.root.mkdir(mode=0o700)
        self.authority=self.root/'authority';self.authority.mkdir(mode=0o700);self.jobs=self.root/'jobs';self.jobs.mkdir(mode=0o700)
        self.policy=copy.deepcopy(self.f.policy)
        for role in ('publishers','approvers'):
            for row in self.policy[role]:row['profiles']=['native_docker_laboratory_protocol']
        self.worker_policy=copy.deepcopy(self.f.f.fixture.policy);self.worker_policy.update(authority_root=str(self.authority),jobs_root=str(self.jobs),admitted_manifest_sha256=[])
        self.manifest=self.adoption();self.plan=self.recovery(self.manifest);self.worker_policy['admitted_manifest_sha256']=[digest(self.manifest),digest(self.plan)]
        self.worker_policy_path=self.root/'worker-policy.json';host.write_new(self.worker_policy_path,self.worker_policy)
        self.db=sqlite3.connect(self.authority/'service.sqlite3');self.db.executescript('''CREATE TABLE jobs(id TEXT PRIMARY KEY,root TEXT,manifest_sha256 TEXT,status TEXT,cancelled INTEGER,dispatches INTEGER,outcome TEXT,controller_pid INTEGER,controller_start TEXT);CREATE TABLE consumed(issuer TEXT,nonce TEXT,operation_id TEXT,manifest_sha256 TEXT);CREATE TABLE events(sequence INTEGER PRIMARY KEY,job TEXT,kind TEXT,payload TEXT,created_at INTEGER);CREATE TABLE revoked(issuer TEXT,key_id TEXT);CREATE TABLE approval_transcripts(operation_id TEXT PRIMARY KEY,receipt_json TEXT,receipt_sha256 TEXT,consumed_at INTEGER);CREATE TABLE adoption_operations(operation_id TEXT PRIMARY KEY,manifest_sha256 TEXT,verification_id TEXT,verification_dispatches INTEGER,verification_status TEXT,verification_outcome TEXT);CREATE TABLE adoption_recovery_plans(operation_id TEXT PRIMARY KEY,original_operation_id TEXT,manifest_sha256 TEXT,root TEXT,status TEXT,cancelled INTEGER,dispatches INTEGER,outcome TEXT,controller_pid INTEGER,controller_start TEXT);''')
        self.adoption_root=self.register(self.manifest);self.plan_root=self.register(self.plan);self.db.commit();self.db.close();(self.authority/'service.sqlite3').chmod(0o600)
        self.trust=self.root/'trust.json';host.write_new(self.trust,self.policy)
    def adoption(self):
        base=self.f.snap['manifest'];m={key:copy.deepcopy(base[key]) for key in domains.ADOPTION_FIELDS.split() if key in base}
        m.update(schema_version=domains.ADOPTION,operation_id=str(uuid.uuid4()),verification_operation_id=str(uuid.uuid4()),profile='native_docker_laboratory_protocol',action='native_state_only_import',prepared_at=int(time.time())-1,expires_at=int(time.time())+300,verification_host_spec=copy.deepcopy(base['host_spec']),verification_broker_policy=copy.deepcopy(base['broker_policy']))
        context=m['run_context'];provider={'schema_version':'worker-adoption-provider/1','tenant_id':m['tenant_id'],'object_id':m['object_ids'][0],'provider_identity':{'tenant_id':m['tenant_id']},'backend':{'backend':{'state_blob':'literal'},'state_blob':'literal'},'source_revision':context['source_revision'],'source_sha256':context['source_sha256'],'effective_input_sha256':context['effective_inputs_sha256'],'lockfile_sha256':context['provider_lock_sha256']}
        m['provider_binding']=provider;m['backend_scope_sha256']=digest(provider['backend'])
        m['state_contract']={'schema_version':'native-adoption-state-contract/1','tenant_id':m['tenant_id'],'object_id':m['object_ids'][0],'execution_binding_sha256':m['execution_binding_sha256'],'source_sha256':context['source_sha256'],'effective_inputs_sha256':context['effective_inputs_sha256'],'locks_sha256':context['provider_lock_sha256'],'backend':provider['backend']['backend'],'baseline_sha256':'1'*64}
        m['ownership_binding']={'schema_version':'native-adoption-ownership/1','tenant_id':m['tenant_id'],'object_id':m['object_ids'][0],'baseline_sha256':'1'*64,'result':'no_owner_in_completely_searched_declared_scope'}
        m['intended_writer']={'ordinary_graph_changes_require_separate_approval':True,'organizational_sole_writer_approval_established':False,'absence_of_undeclared_or_external_writers_established':False}
        return m
    def recovery(self,m):
        v={key:copy.deepcopy(m[key]) for key in domains.RECOVERY_FIELDS.split() if key in m}
        v.update(schema_version=domains.RECOVERY,operation_id=str(uuid.uuid4()),action='native_first_plan_only',original_operation_id=m['operation_id'],original_manifest_sha256=digest(m),original_facts={'modeled_worker_boundary':True},recovery_binding={'recovery_operation_id':str(uuid.uuid4()),'recovery_manifest_sha256':'2'*64,'state':{'sha256':'3'*64,'serial':13},'projection_sha256':'4'*64,'original_contract_sha256':digest(m['state_contract'])})
        return v
    def sign_approval(self,m):
        recovery=m['schema_version']==domains.RECOVERY
        payload=copy.deepcopy(self.f.receipt['payload']);payload.update(schema_version='signed-native-adoption-recovery-plan-approval/1' if recovery else 'signed-native-state-adoption-approval/1',operation_id=m['operation_id'],manifest_sha256=digest(m),issued_at=m['prepared_at'],expires_at=m['expires_at'],nonce=uuid.uuid4().hex)
        domain=b'intune-workbench:native-adoption-recovery-plan-approval:v1\x00' if recovery else b'intune-workbench:native-state-adoption-approval:v1\x00'
        message=self.root/('message-'+uuid.uuid4().hex);signature=self.root/('signature-'+uuid.uuid4().hex);message.write_bytes(domain+canonical(payload));message.chmod(0o600)
        subprocess.run(['/usr/bin/openssl','pkeyutl','-sign','-rawin','-inkey',str(self.f.f.fixture.key),'-in',str(message),'-out',str(signature)],check=True,capture_output=True);signature.chmod(0o600)
        return {'payload':payload,'signature':base64.b64encode(signature.read_bytes()).decode()}
    def register(self,m):
        root=self.jobs/m['operation_id'];root.mkdir(mode=0o700);host.write_new(root/'manifest.json',m);host.write_new(root/'policy-binding.json',{'policy_sha256':digest(self.worker_policy)})
        recovery=m['schema_version']==domains.RECOVERY;at=int(time.time());receipt=self.sign_approval(m);p=receipt['payload']
        if recovery:
            host.write_new(root/'original.json',{'root':str(self.adoption_root),'manifest_sha256':digest(self.manifest)})
            self.db.execute('INSERT INTO adoption_recovery_plans VALUES(?,?,?,?,?,?,?,?,?,?)',(m['operation_id'],m['original_operation_id'],digest(m),str(root),'interrupted',0,1,None,None,None));job=m['original_operation_id']
        else:
            self.db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?)',(m['operation_id'],str(root),digest(m),'adoption_host_interrupted',0,1,None,None,None))
            self.db.execute('INSERT INTO adoption_operations VALUES(?,?,?,?,?,?)',(m['operation_id'],digest(m),m['verification_operation_id'],0,'not_started',None));job=m['operation_id']
        self.db.execute('INSERT INTO consumed VALUES(?,?,?,?)',(p['issuer'],p['nonce'],m['operation_id'],digest(m)));self.db.execute('INSERT INTO approval_transcripts VALUES(?,?,?,?)',(m['operation_id'],canonical(receipt).decode(),digest(receipt),at))
        for kind in (('adoption_recovery_plan_prepared','adoption_recovery_plan_consumed') if recovery else ('adoption_prepared','adoption_dispatch_consumed')):
            self.db.execute('INSERT INTO events(job,kind,payload,created_at) VALUES(?,?,?,?)',(job,kind,canonical({'manifest_sha256':digest(m),'operation_id':m['operation_id']}).decode(),at))
        return root
    def bundle(self,recovery=False):
        m=self.plan if recovery else self.manifest;root=self.plan_root if recovery else self.adoption_root;req=c.make_request(m,self.policy,uuid.uuid4().hex)
        snap=host.snapshot(root,self.worker_policy_path,req);at=int(time.time());statement={'schema_version':'worker-evidence-statement/1','publisher':self.f.publisher,'request_sha256':digest(req),'request_nonce':req['nonce'],'issued_at':at,'expires_at':at+900,'snapshot':snap}
        return self.f.sign(statement),req
    def check(self,envelope,req):return c.verify_envelope(envelope,req,self.policy,self.f.verifier,now=int(time.time())).result()
    def cli(self,*args,ok=True):return self.f('test_actual_cli_signed_prepare_assemble_ingest_reopen').cli(*args,ok=ok)
    def test_both_distinct_signed_domains_preserve_unknown_state_only_history(self):
        for recovery in (False,True):
            envelope,req=self.bundle(recovery);result=self.check(envelope,req)
            self.assertFalse(result['baseline_admissible']);self.assertFalse(result['graph_deployment']);self.assertTrue(result['state_only']);self.assertFalse(result['execution_authorized']);self.assertEqual(result['approval_artifact_status'],'verified_retained_original');self.assertEqual(result['domain_qualification'],'unestablished')
    def test_actual_cli_request_prepare_assemble_ingest_reopen_both_domains_no_source_writes(self):
        def census():return {str(p):(p.read_bytes(),p.stat().st_mtime_ns) for root in (self.authority,self.jobs) for p in root.rglob('*') if p.is_file()}
        before=census()
        for recovery in (False,True):
            out=self.root/('cli-'+str(recovery));out.mkdir(mode=0o700);store=out/'received';store.mkdir(mode=0o700);root=self.plan_root if recovery else self.adoption_root
            request=out/'request.json';publisher=out/'publisher.json';host.write_new(publisher,self.f.publisher)
            self.cli('request','--manifest',root/'manifest.json','--trust',self.trust,'--output',request)
            statement=out/'statement.json';self.cli('prepare','--request',request,'--trust',self.trust,'--publisher',publisher,'--job-root',root,'--policy',self.worker_policy_path,'--output',statement)
            signed=self.f.sign(host.load(statement));signature=out/'signature';signature.write_bytes(base64.b64decode(signed['signature']));signature.chmod(0o600);envelope=out/'envelope.json';auth=['--trust',self.trust,'--verifier',self.f.verifier_path,'--scratch',self.f.scratch]
            self.cli('assemble',*auth,'--statement',statement,'--signature',signature,'--request',request,'--output',envelope)
            first=self.cli('ingest',*auth,'--envelope',envelope,'--request',request,'--evidence-store',store);last=self.cli('reopen',*auth,'--request-sha256',digest(host.load(request)),'--evidence-store',store)
            self.assertEqual(first['bundle_sha256'],last['bundle_sha256']);self.assertEqual(last['review']['manifest']['schema_version'],domains.RECOVERY if recovery else domains.ADOPTION);self.assertFalse(last['baseline_admissible'])
        self.assertEqual(census(),before)
    def test_wrong_domain_signature_cannot_be_relabelled(self):
        envelope,req=self.bundle();payload=envelope['payload'];payload['snapshot']['approval']['receipt']['payload']['schema_version']='signed-worker-service-approval/1';payload['snapshot']['approval']['receipt_sha256']=digest(payload['snapshot']['approval']['receipt'])
        with self.assertRaises(AppError):self.check(self.f.sign(payload),req)
    def test_original_adoption_approval_missing_stays_nonadmissible(self):
        envelope,req=self.bundle(True);p=envelope['payload'];p['snapshot']['domain_records']['original']['approval']=None;result=self.check(self.f.sign(p),req)
        self.assertEqual(result['approval_artifact_status'],'original_adoption_approval_not_retained');self.assertFalse(result['baseline_admissible'])
    def test_recovery_original_and_source_binding_changes_rejected(self):
        envelope,req=self.bundle(True)
        for edit in (lambda s:s['domain_records']['original']['manifest'].update(operation_id=str(uuid.uuid4())),lambda s:s['manifest']['recovery_binding'].update(original_contract_sha256='0'*64),lambda s:s['manifest'].update(action='apply_saved_plan')):
            p=copy.deepcopy(envelope['payload']);edit(p['snapshot'])
            with self.assertRaises(AppError):self.check(self.f.sign(p),req)
    def test_copied_json_no_original_signature_and_future_domain_rejected(self):
        envelope,req=self.bundle(True);p=copy.deepcopy(envelope['payload']);p['snapshot']['approval']['receipt']['signature']=base64.b64encode(bytes(64)).decode();p['snapshot']['approval']['receipt_sha256']=digest(p['snapshot']['approval']['receipt'])
        with self.assertRaises(AppError):self.check(self.f.sign(p),req)
        changed=copy.deepcopy(self.plan);changed['schema_version']='native-adoption-recovery-plan/3'
        with self.assertRaises(AppError):c.make_request(changed,self.policy,'a'*32)
    def test_hot_source_journal_refused_and_retained(self):
        req=c.make_request(self.manifest,self.policy,'b'*32);sentinel=self.authority/'service.sqlite3-journal';sentinel.write_bytes(b'preserved negative');sentinel.chmod(0o600)
        with self.assertRaises(AppError):host.snapshot(self.adoption_root,self.worker_policy_path,req)
        self.assertEqual(sentinel.read_bytes(),b'preserved negative')
    def plan_bundle(self):
        from plugin_tests.test_worker_plan_evidence_r4 import fixture as literal_fixture,OBJECT
        from intune_iac import worker_plan_content as content
        from intune_iac.worker_evidence_domain_posix import packed
        plan,state,source=literal_fixture();object_id=self.manifest['object_ids'][0]
        plan,state,source=(json.loads(json.dumps(v).replace(OBJECT,object_id)) for v in (plan,state,source))
        envelope,req=self.bundle();snapshot=envelope['payload']['snapshot'];m=snapshot['manifest'];source_raw=canonical(source);state_raw=canonical(state)
        context=m['run_context'];context['source_sha256']=hashlib.sha256(source_raw).hexdigest();context['effective_inputs_sha256']=digest(source['resource'][content.RESOURCE]['selected']);m['run_binding_sha256']=digest(context)
        m['provider_binding'].update(source_sha256=context['source_sha256'],effective_input_sha256=context['effective_inputs_sha256']);m['state_contract'].update(source_sha256=context['source_sha256'],effective_inputs_sha256=context['effective_inputs_sha256'])
        req=c.make_request(m,self.policy,uuid.uuid4().hex);receipt=self.sign_approval(m);snapshot['approval']={'receipt':receipt,'receipt_sha256':digest(receipt),'consumed_at':int(time.time())};snapshot['consumed'].update(nonce=receipt['payload']['nonce'],manifest_sha256=digest(m))
        for event in snapshot['events']:
            if event['payload'].get('operation_id')==m['operation_id']:event['payload']['manifest_sha256']=digest(m)
        snapshot['journal']['events_sha256']=digest(snapshot['events'])
        raw={'plan.bin':b'CONSTRUCTED-NOT-NATIVE','plan.json':canonical(plan),'exit.txt':b'0\n'}
        record={'schema_version':'native-plan-output-capture/1','host_result_sha256':digest({'status':'complete','scope':'modeled host boundary'}),'source_root':'/literal/job','archive_root':'/literal/archive',
            'artifacts':{name:{'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'source_path':'/literal/job/'+name} for name,data in raw.items()},'receiving_state_authentication_established':False,'execution_authorized':False}
        proof=content.validate(raw['plan.json'],state_raw=state_raw,source_raw=source_raw,object_id=object_id,state_sha256=hashlib.sha256(state_raw).hexdigest(),source_sha256=context['source_sha256'],effective_inputs_sha256=context['effective_inputs_sha256'])
        expected={'capture_sha256':digest(record),'artifacts':record['artifacts'],'content_proof':proof,'first_plan_no_change':True,'exit_code':0}
        snapshot['domain_records'].update(plan_artifacts={**{name:packed(data) for name,data in raw.items()},'receipt.json':packed(canonical(record))},state=packed(state_raw),source=packed(source_raw))
        snapshot['job']['outcome']={'independent_completion':{'plan_output_proof':expected}}
        snapshot['domain_records']['verification']['outcome']={'plan_output_capture':record,'host':{'status':'complete','scope':'modeled host boundary'}}
        p=envelope['payload'];p.update(request_sha256=digest(req),request_nonce=req['nonce']);return self.f.sign(p),req
    def test_exact_plan_members_and_shared_pure_content_verified_without_execution_claim(self):
        envelope,req=self.plan_bundle();result=self.check(envelope,req)
        self.assertFalse(result['baseline_admissible']);self.assertFalse(result['execution_authorized']);self.assertEqual(result['domain_qualification'],'unestablished')
        self.assertNotIn('exact_plan_proof_not_retained',result['reasons']);self.assertEqual(result['domain_records']['plan_artifacts'],envelope['payload']['snapshot']['domain_records']['plan_artifacts'])
    def test_signed_plan_binary_exit_json_source_and_state_changes_rejected(self):
        from intune_iac.worker_evidence_domain_posix import packed
        envelope,req=self.plan_bundle()
        for name in ('plan.bin','plan.json','exit.txt','receipt.json','state','source'):
            p=copy.deepcopy(envelope['payload']);records=p['snapshot']['domain_records']
            if name in ('state','source'):records[name]=packed(b'{"changed":true}')
            else:records['plan_artifacts'][name]=packed(b'2\n' if name=='exit.txt' else b'{"changed":true}')
            with self.subTest(name=name),self.assertRaises(AppError):self.check(self.f.sign(p),req)
    def test_recovery_retains_historical_original_policy_without_new_execution_authority(self):
        path=self.adoption_root/'policy-binding.json';path.write_bytes(canonical({'policy_sha256':'7'*64}))
        envelope,req=self.bundle(True);result=self.check(envelope,req)
        facts=result['domain_records']['original']['domain_records']['source_policy']
        self.assertEqual(facts['reviewed_policy_sha256'],'7'*64);self.assertNotEqual(facts['reviewed_policy_sha256'],facts['current_policy_sha256']);self.assertFalse(result['baseline_admissible']);self.assertFalse(result['execution_authorized'])
        selected=c.make_request(self.manifest,self.policy,'c'*32)
        with self.assertRaises(AppError):host.snapshot(self.adoption_root,self.worker_policy_path,selected)
    def test_actual_recovery_observation_schema_binds_adoption_capture(self):
        # Exact field route independently observed in retained native receipt:
        # /tmp/intune-adoption-recovery-native-state-01/receipt.json. This local
        # fixture does not replay that native operation or claim convergence.
        envelope,req=self.bundle(True);p=envelope['payload'];s=p['snapshot'];s['capture']=copy.deepcopy(self.f.snap['capture']);s['capture_provenance']=copy.deepcopy(self.f.snap['capture_provenance'])
        s['job']['outcome']={'independent_completion':{'fresh_observation':{'schema_version':'adoption-native-lease-recovery-observation/1','adoption_capture':{'capture_sha256':self.f.snap['capture_provenance']['capture_sha256'],'path':str(self.f.capture_root)}}}}
        result=self.check(self.f.sign(p),req)
        self.assertNotIn('raw_capture_missing_or_incomplete',result['reasons']);self.assertFalse(result['baseline_admissible']);self.assertEqual(result['domain_qualification'],'unestablished')
    def test_plan_proof_boolean_number_alias_rejected(self):
        envelope,req=self.plan_bundle();p=envelope['payload'];p['snapshot']['job']['outcome']['independent_completion']['plan_output_proof']['content_proof']['before_after_planned_prior_values_equal_state']=1
        with self.assertRaises(AppError):self.check(self.f.sign(p),req)
    def test_plan_proof_exit_false_is_not_zero(self):
        envelope,req=self.plan_bundle();p=envelope['payload'];p['snapshot']['job']['outcome']['independent_completion']['plan_output_proof']['exit_code']=False
        with self.assertRaises(AppError):self.check(self.f.sign(p),req)
