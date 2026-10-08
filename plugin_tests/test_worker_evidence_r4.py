"""Signed real CLI/readonly SQLite/TLS-readback contracts, modeled dispatch boundary.

The fixture records host completion explicitly; it is NOT native execution or
real Azure/Graph. Other retained native service journeys qualify those effects.
"""
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
import unittest
from intune_iac import worker_evidence as contract,worker_evidence_posix as host,observation_reader
from intune_iac.io import AppError,canonical,digest
from intune_iac.workbench_store import WorkbenchStore
from plugin_tests import test_worker_service_readback_r4 as fixture_module

STAGE=Path(contract.__file__).resolve().parents[1]
class EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture_module.ServiceReadbackTests.setUpClass()
        cls.f=fixture_module.ServiceReadbackTests('test_actual_tls_state_and_sealed_graph_completion_release_only_converged_scope');cls.f.setUp()
        cls.root=cls.f.root;cls.f.fixture.prepare();cls.job=cls.f.fixture.job();cls.receipt=cls.f.fixture.receipt();payload=cls.job.policy.verify(cls.f.manifest,cls.receipt);at=int(time.time())
        # Explicit typed journal boundary fixture with a real original signature.
        # Never claimed native dispatch; actual TLS readback/reconcile follows.
        with cls.job.policy.connection() as db:
            db.execute('BEGIN IMMEDIATE');db.execute('INSERT INTO consumed VALUES (?,?,?,?)',(payload['issuer'],payload['nonce'],cls.job.identifier,cls.job.sha256))
            db.execute('INSERT INTO approval_transcripts VALUES (?,?,?,?)',(cls.job.identifier,canonical(cls.receipt).decode(),digest(cls.receipt),at))
            db.execute("UPDATE jobs SET status='host_completed_service_unverified',dispatches=1 WHERE id=?",(cls.job.identifier,))
            cls.job.policy.event(db,cls.job.identifier,'dispatch_consumed',{'manifest_sha256':cls.job.sha256});db.execute('COMMIT')
        cls.job.reconcile(cls.f.collect())
        capture=cls.f.completion.verified()['capture'];batch,_=capture.verified();cls.capture_root=Path(batch['source']['artifacts']['capture-receipt.json']['path']).parent
        cls.store=WorkbenchStore.create(cls.root/'workbench',cls.f.manifest['tenant_id']);observation_reader.publish_batch(cls.store,[capture],job_id='1'*32,attempt_id='2'*32)
        cls.output=cls.root/'evidence-output';cls.output.mkdir(mode=0o700);cls.scratch=cls.root/'scratch';cls.scratch.mkdir(mode=0o700)
        cls.key=cls.output/'publisher.pem';subprocess.run(['/usr/bin/openssl','genpkey','-algorithm','ED25519','-out',str(cls.key)],check=True,capture_output=True)
        public=subprocess.run(['/usr/bin/openssl','pkey','-in',str(cls.key),'-pubout','-outform','DER'],check=True,capture_output=True).stdout[-32:]
        scope={'profiles':[cls.f.manifest['profile']],'tenant_ids':[cls.f.manifest['tenant_id']],'object_ids':cls.f.manifest['object_ids']}
        approver=copy.deepcopy(cls.f.fixture.policy['approvers'][0]);approver.update(tenant_ids=scope['tenant_ids'],object_ids=scope['object_ids'])
        cls.policy={'schema_version':'worker-evidence-trust/1','publishers':[dict(scope,issuer='lab-export',key_id='publisher',publisher_id='readonly-fixture',public_key_hex=public.hex())],
            'approvers':[approver],'revoked':[],'max_age_seconds':900,'max_lifetime_seconds':900,'clock_skew_seconds':5}
        cls.publisher={'issuer':'lab-export','key_id':'publisher','publisher_id':'readonly-fixture','purpose':'read_only_worker_evidence','source_revision':'9'*40,'implementation_sha256':hashlib.sha256(Path(contract.__file__).read_bytes()).hexdigest()}
        cls.req=contract.make_request(cls.f.manifest,cls.policy,'7'*32)
        cls.snap=host.snapshot(cls.job.root,cls.f.fixture.policy_path,cls.req,capture_root=cls.capture_root,store_root=cls.store.root)
        cls.statement={'schema_version':'worker-evidence-statement/1','publisher':cls.publisher,'request_sha256':digest(cls.req),'request_nonce':cls.req['nonce'],'issued_at':int(time.time()),'expires_at':int(time.time())+900,'snapshot':cls.snap}
        cls.verifier_path=cls.output/'verifier.json';host.write_new(cls.verifier_path,cls.f.fixture.policy['verifier']);cls.verifier=host.DetachedVerifier(cls.verifier_path,cls.scratch)
        cls.policy_path=cls.output/'trust.json';host.write_new(cls.policy_path,cls.policy);cls.req_path=cls.output/'request.json';host.write_new(cls.req_path,cls.req)
        cls.envelope=cls.sign(cls.statement);cls.envelope_path=cls.output/'envelope.json';host.write_new(cls.envelope_path,cls.envelope)
    @classmethod
    def tearDownClass(cls):
        retain=os.environ.get('INTUNE_EVIDENCE_TEST_COPY')
        if retain:
            import shutil
            shutil.copytree(cls.root,Path(retain)/'worker-fixture',symlinks=True,ignore=lambda p,n:[x for x in n if (Path(p)/x).is_socket()])
            shutil.copytree(cls.capture_root,Path(retain)/'capture',symlinks=True)
        cls.f.doCleanups();fixture_module.ServiceReadbackTests.tearDownClass()
    @classmethod
    def sign(cls,statement):
        message=cls.output/('message-'+str(time.monotonic_ns()));signature=cls.output/('signature-'+str(time.monotonic_ns()))
        message.write_bytes(contract.DOMAIN+canonical(statement));message.chmod(0o600)
        subprocess.run(['/usr/bin/openssl','pkeyutl','-sign','-rawin','-inkey',str(cls.key),'-in',str(message),'-out',str(signature)],check=True,capture_output=True);signature.chmod(0o600)
        return {'schema_version':'signed-worker-evidence/1','payload':copy.deepcopy(statement),'signature':base64.b64encode(signature.read_bytes()).decode()}
    def verified(self,envelope=None,req=None,policy=None):return contract.verify_envelope(envelope or self.envelope,req or self.req,policy or self.policy,self.verifier,now=int(time.time())).result()
    def cli(self,*args,ok=True):
        result=subprocess.run([sys.executable,'-B',str(STAGE/'scripts/intune-worker-evidence.py'),*map(str,args)],capture_output=True,text=True,timeout=20)
        if ok:self.assertEqual(result.returncode,0,result.stderr)
        else:self.assertNotEqual(result.returncode,0,result.stdout)
        return json.loads(result.stdout if result.returncode==0 else result.stderr)
    def auth(self):return ['--trust',self.policy_path,'--verifier',self.verifier_path,'--scratch',self.scratch]
    def test_actual_cli_signed_prepare_assemble_ingest_reopen(self):
        out=self.root/'cli-journey';out.mkdir(mode=0o700);store=out/'store';store.mkdir(mode=0o700)
        publisher=out/'publisher.json';host.write_new(publisher,self.publisher)
        req=out/'request.json';self.cli('request','--manifest',self.job.root/'manifest.json','--trust',self.policy_path,'--output',req)
        roots=[self.job.root,self.job.policy.root,self.store.root,self.capture_root]
        def census():return {str(p):(hashlib.sha256(p.read_bytes()).hexdigest(),p.stat().st_mtime_ns) for r in roots for p in r.rglob('*') if p.is_file()}
        before=census();statement=out/'statement.json'
        self.cli('prepare','--request',req,'--trust',self.policy_path,'--publisher',publisher,'--job-root',self.job.root,'--policy',self.f.fixture.policy_path,'--capture-root',self.capture_root,'--store-root',self.store.root,'--output',statement)
        signed=self.sign(host.load(statement));sig=out/'signature';sig.write_bytes(base64.b64decode(signed['signature']));sig.chmod(0o600);envelope=out/'envelope.json'
        assembled=self.cli('assemble',*self.auth(),'--statement',statement,'--signature',sig,'--request',req,'--output',envelope)
        self.assertTrue(assembled['baseline_admissible']);self.assertFalse(assembled['platform_qualified'])
        result=self.cli('ingest',*self.auth(),'--envelope',envelope,'--request',req,'--evidence-store',store)
        reopened=self.cli('reopen',*self.auth(),'--request-sha256',digest(host.load(req)),'--evidence-store',store)
        self.assertEqual(result['bundle_sha256'],reopened['bundle_sha256']);self.assertEqual(reopened['desired']['description'],'Reviewed correction');self.assertFalse(reopened['execution_authorized'])
        self.assertEqual(census(),before);self.assertEqual(reopened['observed_at'],self.snap['capture_provenance']['observed_at'])
    def test_wrong_request_identity_run_plan_and_revision(self):
        for key,value in [('tenant_id','3'*8+'-3333-4333-8333-'+'3'*12),('object_id','4'*8+'-4444-4444-8444-'+'4'*12),('manifest_sha256','0'*64),('saved_plan_sha256','0'*64),('source_revision','0'*40),('run_attempt',2)]:
            req=copy.deepcopy(self.req);req[key]=value
            with self.subTest(key=key),self.assertRaises(AppError):self.verified(req=req)
    def test_publisher_signature_and_purpose_are_required(self):
        for mutate in (lambda p:p['publisher'].update(purpose='approve_execution'),lambda p:p['publisher'].update(publisher_id='other'),lambda p:p.update(request_nonce='8'*32)):
            p=copy.deepcopy(self.statement);mutate(p)
            with self.assertRaises(AppError):self.verified(self.sign(p))
        altered=copy.deepcopy(self.envelope);altered['signature']=base64.b64encode(bytes(64)).decode()
        with self.assertRaises(AppError):self.verified(altered)
    def test_stale_snapshot_not_refreshed_by_new_issue_time(self):
        p=copy.deepcopy(self.statement);p['snapshot']['read_at']=int(time.time())-901;p['issued_at']=int(time.time());p['expires_at']=int(time.time())+900
        with self.assertRaises(AppError):self.verified(self.sign(p))
    def test_original_approval_signature_consumption_and_dispatch_time(self):
        for key,value in [('receipt_sha256','0'*64),('consumed_at',self.receipt['payload']['expires_at'])]:
            p=copy.deepcopy(self.statement);p['snapshot']['approval'][key]=value
            with self.assertRaises(AppError):self.verified(self.sign(p))
        p=copy.deepcopy(self.statement);p['snapshot']['approval']['receipt']['signature']=base64.b64encode(bytes(64)).decode();p['snapshot']['approval']['receipt_sha256']=digest(p['snapshot']['approval']['receipt'])
        with self.assertRaises(AppError):self.verified(self.sign(p))
    def test_legacy_missing_original_is_visible_and_not_baseline(self):
        p=copy.deepcopy(self.statement);p['snapshot']['approval']=None
        result=self.verified(self.sign(p));self.assertFalse(result['baseline_admissible']);self.assertEqual(result['approval_artifact_status'],'not_retained')
    def test_missing_or_reordered_reconciliation_is_not_baseline(self):
        p=copy.deepcopy(self.statement);p['snapshot']['events'].reverse()
        with self.assertRaises(AppError):self.verified(self.sign(p))
        p=copy.deepcopy(self.statement);p['snapshot']['job']['status']='service_state_converged_execution_unknown'
        self.assertFalse(self.verified(self.sign(p))['baseline_admissible'])
    def test_raw_member_hash_identity_and_path_negatives(self):
        for mutate in (lambda c:c['export.json'].update(sha256='0'*64),lambda c:c.update({'../outside':c['export.json']})):
            p=copy.deepcopy(self.statement);mutate(p['snapshot']['capture'])
            with self.assertRaises(AppError):self.verified(self.sign(p))
    def test_source_reader_rejects_journal_and_retains_it(self):
        path=Path(str(self.job.policy.database)+'-journal');path.write_bytes(b'preserved hot journal sentinel');path.chmod(0o600)
        try:
            with self.assertRaises(AppError):host.snapshot(self.job.root,self.f.fixture.policy_path,self.req)
            self.assertEqual(path.read_bytes(),b'preserved hot journal sentinel')
        finally:path.rename(self.output/'retained-hot-journal-sentinel')
    def test_failed_ingest_preserves_received_bytes_and_no_admission(self):
        root=self.root/'failed-ingest';root.mkdir(mode=0o700);envelope=copy.deepcopy(self.envelope);envelope['signature']=base64.b64encode(bytes(64)).decode()
        with self.assertRaises(AppError):host.ingest(root,envelope,self.req,self.policy,self.verifier)
        attempts=list(root.glob('attempt-*'));self.assertEqual(len(attempts),1);self.assertEqual(host.load(attempts[0]/'envelope.json'),envelope);self.assertTrue((attempts[0]/'failure.json').exists());self.assertFalse((root/'evidence.sqlite3').exists())
    def test_exact_repeat_idempotent_changed_replay_preserved(self):
        root=self.root/'replay-store';root.mkdir(mode=0o700);first=host.ingest(root,self.envelope,self.req,self.policy,self.verifier)
        second=host.ingest(root,self.envelope,self.req,self.policy,self.verifier);self.assertTrue(second['idempotent'])
        p=copy.deepcopy(self.statement);p['issued_at']-=1;p['expires_at']-=1
        with self.assertRaises(AppError):host.ingest(root,self.sign(p),self.req,self.policy,self.verifier)
        self.assertEqual(host.reopen(root,digest(self.req),self.policy,self.verifier)['bundle_sha256'],first['bundle_sha256'])

    def test_exact_incoming_serialization_retained(self):
        root=self.root/'exact-bytes';root.mkdir(mode=0o700);store=root/'store';store.mkdir(mode=0o700)
        original=json.dumps(self.envelope,indent=2).encode()+b'\n';incoming=root/'incoming.json';incoming.write_bytes(original);incoming.chmod(0o600)
        result=self.cli('ingest',*self.auth(),'--envelope',incoming,'--request',self.req_path,'--evidence-store',store)
        self.assertEqual((store/result['stored_attempt']/'envelope.json').read_bytes(),original)
    def test_ledger_uses_verified_snapshot_after_caller_mutation(self):
        from unittest.mock import patch
        envelope=copy.deepcopy(self.envelope);root=self.root/'mutation-store';root.mkdir(mode=0o700);verify=contract.verify_envelope
        expected=envelope['payload']['snapshot']['journal']['last_sequence']
        def mutate(*args,**kwargs):
            verified=verify(*args,**kwargs);envelope['payload']['snapshot']['journal']['last_sequence']=999;return verified
        with patch.object(contract,'verify_envelope',side_effect=mutate):host.ingest(root,envelope,self.req,self.policy,self.verifier)
        with sqlite3.connect(root/'evidence.sqlite3') as db:self.assertEqual(db.execute('SELECT sequence FROM heads').fetchone()[0],expected)
    def test_readonly_close_keeps_primary_failure(self):
        from unittest.mock import patch
        connect=sqlite3.connect
        class Closing:
            def __init__(self,*a,**k):self.inner=connect(*a,**k)
            def __getattr__(self,name):return getattr(self.inner,name)
            def close(self):self.inner.close();raise OSError('injected close')
        with patch.object(host.sqlite3,'connect',Closing):
            try:
                with host.readonly_database(self.job.policy.database):raise AppError('primary_fixture','original')
            except BaseException as error:self.assertIsInstance(error,AppError);self.assertEqual(error.code,'primary_fixture')
            else:self.fail('failure suppressed')
    def test_secondary_recording_interrupt_propagates_with_original_cause(self):
        from unittest.mock import patch
        root=self.root/'recording-interrupt';root.mkdir(mode=0o700);envelope=copy.deepcopy(self.envelope);envelope['signature']=base64.b64encode(bytes(64)).decode();write=host.write_new
        def interrupt(path,value):
            if Path(path).name=='failure.json':raise KeyboardInterrupt('injected recording interrupt')
            return write(path,value)
        with patch.object(host,'write_new',side_effect=interrupt):
            try:host.ingest(root,envelope,self.req,self.policy,self.verifier)
            except BaseException as error:self.assertIsInstance(error,KeyboardInterrupt);self.assertIsInstance(error.__cause__,AppError)
            else:self.fail('interrupt suppressed')
    def test_bounded_rejects_deep_input_before_recursive_serialization(self):
        value=[]
        for _ in range(1100):value=[value]
        with self.assertRaises(AppError):contract.bounded(value)
    def test_actual_cli_malformed_input_retained_without_traceback(self):
        root=self.root/'malformed';root.mkdir(mode=0o700);store=root/'store';store.mkdir(mode=0o700)
        raw=b'{"duplicate":1,"duplicate":2}\n';incoming=root/'incoming.json';incoming.write_bytes(raw);incoming.chmod(0o600)
        result=self.cli('ingest',*self.auth(),'--envelope',incoming,'--request',self.req_path,'--evidence-store',store,ok=False)
        self.assertEqual(result['code'],'invalid_json');attempt=next(store.glob('attempt-*'));self.assertEqual((attempt/'envelope.json').read_bytes(),raw);self.assertTrue((attempt/'failure.json').exists())
    def test_actual_cli_deep_input_retained_without_traceback(self):
        root=self.root/'deep';root.mkdir(mode=0o700);store=root/'store';store.mkdir(mode=0o700)
        raw=b'['*1500+b'0'+b']'*1500;incoming=root/'incoming.json';incoming.write_bytes(raw);incoming.chmod(0o600)
        result=self.cli('ingest',*self.auth(),'--envelope',incoming,'--request',self.req_path,'--evidence-store',store,ok=False)
        self.assertEqual(result['code'],'invalid_json');self.assertEqual((next(store.glob('attempt-*'))/'envelope.json').read_bytes(),raw)
    def test_request_caller_mutation_does_not_rebind_ledger(self):
        from unittest.mock import patch
        root=self.root/'request-mutation';root.mkdir(mode=0o700);req=copy.deepcopy(self.req);expected=digest(req);verify=contract.verify_envelope
        def mutate(*args,**kwargs):
            verified=verify(*args,**kwargs);req['object_id']='99999999-9999-4999-8999-999999999999';return verified
        with patch.object(contract,'verify_envelope',side_effect=mutate):host.ingest(root,self.envelope,req,self.policy,self.verifier)
        with sqlite3.connect(root/'evidence.sqlite3') as db:self.assertEqual(db.execute('SELECT request_sha256 FROM received').fetchone()[0],expected)
        self.assertEqual(host.reopen(root,expected,self.policy,self.verifier)['bundle_sha256'],digest(self.envelope))
    def test_revoked_publisher_and_weak_key_never_promote(self):
        for weak in (False,True):
            policy=copy.deepcopy(self.policy)
            if weak:policy['publishers'][0]['public_key_hex']='0'*64
            else:policy['revoked']=[{'issuer':'lab-export','key_id':'publisher','purpose':'publisher'}]
            req=copy.deepcopy(self.req);req['trust_sha256']=digest(policy);payload=copy.deepcopy(self.statement);payload['request_sha256']=digest(req)
            with self.subTest(weak=weak),self.assertRaises(AppError):self.verified(self.sign(payload),req=req,policy=policy)
