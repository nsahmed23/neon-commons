"""Self-contained signatures/parser/cleanup and modeled SQL race; no recovery authority.

Native projection and retained-host-envelope replay stay in complete R4 evidence.
The SQL race injects only inert manifest validation; it never executes a worker.
"""
import ast,base64,copy,hashlib,json,os,subprocess,tempfile,time,unittest,uuid
from unittest.mock import patch
from dataclasses import asdict,replace
from pathlib import Path
from intune_iac import worker_adoption_reconcile as bridge,worker_adoption as adoption,worker_service as service,worker_provider
from intune_iac.worker_adoption_provider import NativeAdoptionProviderAdapter
from intune_iac.io import AppError,canonical,digest,write_json
from plugin_tests.signing_fixture import verifier_pin

class RecoveryPlanContracts(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        (self.root/'trust').mkdir(mode=0o700);(self.root/'jobs').mkdir(mode=0o700)
        self.key=self.root/'trust/key.pem';subprocess.run(['/usr/bin/openssl','genpkey','-algorithm','ED25519','-out',str(self.key)],check=True,capture_output=True)
        public=subprocess.check_output(['/usr/bin/openssl','pkey','-in',str(self.key),'-pubout','-outform','DER'])[-32:]
        pin=verifier_pin(Path('/usr/bin/openssl'),hashlib.sha256(Path('/usr/bin/openssl').read_bytes()).hexdigest())
        self.manifest={'operation_id':str(uuid.uuid4()),'prepared_at':int(time.time()),'expires_at':int(time.time())+90,'profile':'native_docker_laboratory_protocol','schema_version':bridge.VERSION,'action':'native_first_plan_only'}
        policy={'schema_version':'worker-service-policy/1','authority_root':str(self.root/'trust/authority'),'jobs_root':str(self.root/'jobs'),
            'verifier':{k:str(v) if isinstance(v,Path) else v for k,v in asdict(pin).items()},'approvers':[{'issuer':'fixture','key_id':'key','approver_id':'reviewer','public_key_hex':public.hex(),'profiles':['native_docker_laboratory_protocol']}],
            'admitted_manifest_sha256':[digest(self.manifest)]}
        self.policy_path=self.root/'trust/policy.json';write_json(self.policy_path,policy);self.policy=service.ServicePolicy(self.policy_path)
    def signed(self,domain=bridge.SIGNATURE_DOMAIN,**changes):
        payload={'schema_version':bridge.APPROVAL_VERSION,'operation_id':self.manifest['operation_id'],'manifest_sha256':digest(self.manifest),
            'issued_at':int(time.time()),'expires_at':self.manifest['expires_at'],'nonce':uuid.uuid4().hex,'issuer':'fixture','key_id':'key','approver_id':'reviewer'}
        payload.update(changes);msg=self.root/'trust/message';sig=self.root/'trust/signature';msg.write_bytes(domain+canonical(payload))
        subprocess.run(['/usr/bin/openssl','pkeyutl','-sign','-rawin','-inkey',str(self.key),'-in',str(msg),'-out',str(sig)],check=True,capture_output=True)
        return {'payload':payload,'signature':base64.b64encode(sig.read_bytes()).decode()}
    def test_real_independent_signature_and_actual_nul_domain(self):
        self.assertTrue(bridge.SIGNATURE_DOMAIN.endswith(b'\0'));signed=self.signed();self.assertEqual(bridge._verify(self.policy,self.manifest,signed),signed['payload'])
    def test_original_import_and_normal_apply_domains_reject(self):
        for domain in (adoption.SIGNATURE_DOMAIN,service.SIGNATURE_DOMAIN):
            with self.assertRaises(AppError):bridge._verify(self.policy,self.manifest,self.signed(domain))
    def test_signed_wrong_schema_operation_hash_nonce_and_expiry_reject(self):
        for changes in ({'schema_version':adoption.APPROVAL_VERSION},{'operation_id':str(uuid.uuid4())},{'manifest_sha256':'1'*64},{'nonce':'x'*32},{'expires_at':int(time.time())-1},{'issued_at':int(time.time())+100}):
            with self.assertRaises(AppError):bridge._verify(self.policy,self.manifest,self.signed(**changes))
    def test_caller_signature_mutation_cannot_validate(self):
        signed=self.signed();signed['payload']['nonce']='0'*32
        with self.assertRaises(AppError):bridge._verify(self.policy,self.manifest,signed)
    def test_json_completion_and_runtime_do_not_mint_capabilities(self):
        with self.assertRaises(AppError):bridge._completion({}, {'approved':True})
        with self.assertRaises(AppError):bridge.RecoveryPlanRuntime(None,profile='native_docker_laboratory_protocol',run={},storage={},binding={},credentials={},upstream={},certificate='',private_key='',provider={})
    def test_inert_plan_parser_cannot_substitute_json_for_receiving_completion(self):
        # The public recovery path now requires exact sealed receiving state.
        # Literal native-format content/tamper controls have their own shared
        # helper suite and cannot manufacture this capability.
        case=object.__new__(bridge.RecoveryPlanJob)
        case.original={}
        with self.assertRaises(AppError):case._plan_evidence(completion={'approved':True})
    def _signature_close_fault(self,secondary):
        signed=self.signed();opened=[];real_open=os.open;real_close=os.close
        def tracked_open(path,*args,**kwargs):
            fd=real_open(path,*args,**kwargs)
            if str(path)==str(self.policy.verifier.executable):opened.append(fd)
            return fd
        def failed_close(fd):
            real_close(fd)
            if opened and fd==opened[0]:raise secondary
        with patch.object(bridge.os,'open',tracked_open),patch.object(bridge.os,'close',failed_close),patch.object(bridge.protected,'_supervise',side_effect=AppError('fixture_signature_primary','retained primary')):
            bridge._verify(self.policy,self.manifest,signed)
    def test_signature_primary_survives_secondary_fd_close_failure(self):
        with self.assertRaises(AppError) as caught:self._signature_close_fault(OSError('fixture close error'))
        self.assertEqual(caught.exception.code,'adoption_recovery_signature_invalid')
        self.assertTrue(any('cleanup' in note for note in getattr(caught.exception,'__notes__',[])))
    def test_signature_secondary_interrupt_preserves_primary_chain(self):
        with self.assertRaises(KeyboardInterrupt) as caught:self._signature_close_fault(KeyboardInterrupt('fixture cancellation'))
        self.assertIsInstance(caught.exception.__cause__,AppError)
        self.assertEqual(caught.exception.__cause__.code,'adoption_recovery_signature_invalid')
    def test_original_disposition_winning_prepare_race_cannot_register_plan(self):
        # Constructed common-authority rows model ONLY the race. Manifest
        # validation is deliberately injected; no signature/runtime is created
        # and this test cannot qualify authenticated recovery.
        original_root=self.root/'jobs/original';original_root.mkdir(mode=0o700)
        original_manifest={'schema_version':adoption.VERSION,'operation_id':str(uuid.uuid4()),'verification_operation_id':str(uuid.uuid4()),
            'tenant_id':'11111111-1111-4111-8111-111111111111','object_ids':['22222222-2222-4222-8222-222222222222'],
            'backend_scope_sha256':'a'*64,'profile':'native_docker_laboratory_protocol'}
        write_json(original_root/'manifest.json',original_manifest);write_json(original_root/'policy-binding.json',{'policy_sha256':self.policy.sha256})
        adoption._tables(self.policy);oid=original_manifest['operation_id'];oldsha=digest(original_manifest);oldoutcome={'status':'outcome_unknown'}
        with self.policy.connection() as db:
            db.execute('INSERT INTO jobs(id,root,manifest_sha256,status,dispatches,outcome) VALUES (?,?,?,?,?,?)',(oid,str(original_root),oldsha,'outcome_unknown',1,canonical(oldoutcome).decode()))
            db.execute('INSERT INTO adoption_operations(operation_id,manifest_sha256,verification_id) VALUES (?,?,?)',(oid,oldsha,original_manifest['verification_operation_id']))
            db.execute('INSERT INTO consumed VALUES (?,?,?,?)',('fixture','1'*32,oid,oldsha))
            for scope in service._scopes(original_manifest):db.execute('INSERT INTO ownership VALUES (?,?)',(scope,oid))
        original=adoption.AdoptionJob(original_root,self.policy_path)
        candidate=dict(self.manifest,original_operation_id=oid,original_manifest_sha256=oldsha,original_facts={'status':'outcome_unknown','outcome_sha256':digest(oldoutcome),'cancelled':False})
        raw=json.loads(self.policy_path.read_text());raw['admitted_manifest_sha256'].append(digest(candidate));write_json(self.policy_path,raw)
        original=adoption.AdoptionJob(original_root,self.policy_path)
        def disposition_wins(value,**kwargs):
            with original.policy.connection() as db:
                db.execute("UPDATE jobs SET status='adoption_not_observed_execution_unknown' WHERE id=?",(oid,));db.execute('DELETE FROM ownership WHERE job=?',(oid,))
            return candidate
        with patch.object(bridge,'validate_manifest',side_effect=disposition_wins):
            with self.assertRaises(AppError):bridge.prepare_job(self.root/'jobs/new-plan',original=original,manifest=candidate,policy_path=self.policy_path)
        with original.policy.connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM adoption_recovery_plans').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM consumed').fetchone()[0],1)
