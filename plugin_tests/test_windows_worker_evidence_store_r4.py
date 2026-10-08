"""Real SQLite/signatures with recorded Win32 file effects, not native DLL proof."""
import copy
from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch
from intune_iac import windows_worker_evidence_store as receiver,windows_worker_evidence as native
from intune_iac import windows_workbench as win,windows_storage as storage,workbench_evidence_views as views,worker_evidence as contract
from intune_iac.io import AppError,canonical,digest
from plugin_tests.test_windows_workbench_r4 import FilesystemAPI
from plugin_tests.test_windows_storage_r4 import ROOT,CANONICAL
STAGE=Path(contract.__file__).parents[1]
spec=importlib.util.spec_from_file_location('native_evidence_fixture',STAGE/'plugin_tests/test_worker_evidence_r4.py');fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)

class NativeReceivedEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixture.EvidenceTests.setUpClass();cls.f=fixture.EvidenceTests
    @classmethod
    def tearDownClass(cls):fixture.EvidenceTests.tearDownClass()
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.api=FilesystemAPI(Path(self.temp.name));self.fs=win._Filesystem(self.api,self.api.connect)
        self.root=ROOT+'\\received';self.store=win.WindowsWorkbenchStore._create(self.root,self.f.req['tenant_id'],self.fs)
        storage._create_directory(ROOT,'input',self.api);storage._create_directory(ROOT,'scratch',self.api)
        self.input=ROOT+'\\input';self.scratch=ROOT+'\\scratch';self.write('envelope.json',json.dumps(self.f.envelope,indent=2).replace('\n','\r\n').encode()+b'\r\n');self.write('request.json',canonical(self.f.req));self.write('trust.json',canonical(self.f.policy));self.write('pin.json',b'{}')
        @contextmanager
        def actual_posix_crypto(pin,scratch,api):
            self.f.verifier.metadata={'boundary':'real POSIX Ed25519 verifier; recorded Windows storage','platform_qualified':False}
            yield self.f.verifier
        self.addCleanup(patch.stopall);patch.object(native,'_verifier',side_effect=actual_posix_crypto).start()
        import os,shutil
        retained=os.environ.get('INTUNE_NATIVE_RECEIVED_TEST_COPY')
        if retained:self.addCleanup(lambda:shutil.copytree(Path(self.temp.name),Path(retained)/self._testMethodName,symlinks=True))
    def write(self,name,raw):storage._create_file(self.input,name,raw,self.api)
    def raw(self,name):return self.api.real(CANONICAL+'\\input\\'+name).read_bytes()
    def replace(self,name,value):self.api.real(CANONICAL+'\\input\\'+name).write_bytes(canonical(value))
    def ingest(self,envelope='envelope.json',request='request.json'):
        return receiver._ingest(self.store,self.input+'\\'+envelope,self.input+'\\'+request,self.input+'\\trust.json',self.input+'\\pin.json',self.scratch,self.api)
    def reopen(self,request=None,**kw):
        return receiver._reopen(self.store,digest(request or self.f.req),self.input+'\\trust.json',self.input+'\\pin.json',self.scratch,self.api,**kw)
    def sql(self,query):
        with sqlite3.connect(self.api.real(CANONICAL+'\\received\\observations.sqlite3')) as db:return db.execute(query).fetchall()
    def test_exact_original_serialization_reopens_real_signature_and_one_index(self):
        result=self.ingest();again=self.ingest();observed=self.reopen()
        attempt=self.api.real(CANONICAL+'\\received\\'+result['stored_attempt'])
        self.assertEqual((attempt/'envelope.json').read_bytes(),self.raw('envelope.json'));self.assertEqual(observed['desired']['description'],'Reviewed correction')
        self.assertTrue(again['idempotent']);self.assertFalse(result['execution_authorized']);self.assertEqual(len(self.sql("SELECT key FROM metadata WHERE key LIKE 'worker_evidence_received:%'")),1);self.assertEqual(self.api.handles,{})
    def test_malformed_received_bytes_retained_and_not_indexed(self):
        self.api.real(CANONICAL+'\\input\\envelope.json').write_bytes(b'{"duplicate":1,"duplicate":2}\r\n')
        with self.assertRaises(AppError):self.ingest()
        attempts=list(self.api.real(CANONICAL+'\\received').glob('evidence-attempt-*'));self.assertEqual(len(attempts),1)
        self.assertEqual((attempts[0]/'envelope.json').read_bytes(),self.raw('envelope.json'));self.assertTrue((attempts[0]/'failure.json').exists());self.assertEqual(self.sql("SELECT key FROM metadata WHERE key LIKE 'worker_evidence_%'"),[])
    def test_wrong_tenant_does_not_commit_received_or_head(self):
        other=win.WindowsWorkbenchStore._create(ROOT+'\\wrong','11111111-1111-4111-8111-111111111111',self.fs);self.store=other
        with self.assertRaises(AppError) as raised:self.ingest()
        self.assertEqual(raised.exception.code,'workbench_evidence_identity')
        with other._connection() as db:self.assertEqual(db.execute("SELECT key FROM metadata WHERE key LIKE 'worker_evidence_%'").fetchall(),[])
    def test_rotation_cannot_reset_shared_publisher_high_water(self):
        policy=copy.deepcopy(self.f.policy);second=copy.deepcopy(policy['publishers'][0]);second['key_id']='rotated';policy['publishers'].append(second);self.replace('trust.json',policy)
        request=contract.make_request(self.f.snap['manifest'],policy,'a'*32);self.replace('request.json',request)
        statement=copy.deepcopy(self.f.statement);statement.update(request_sha256=digest(request),request_nonce=request['nonce']);self.replace('envelope.json',self.f.sign(statement));self.ingest()
        low=copy.deepcopy(statement);low['publisher']['key_id']='rotated';snap=low['snapshot'];snap['events']=snap['events'][:1];snap['job']={'status':'prepared','cancel_requested':False,'dispatches':0,'outcome':None};snap['approval']=None;snap['consumed']=None;snap['capture']=None;snap['capture_provenance']=None
        snap['journal'].update(selected_event_count=1,first_sequence=snap['events'][0]['sequence'],last_sequence=snap['events'][0]['sequence'],events_sha256=digest(snap['events']))
        request=contract.make_request(snap['manifest'],policy,'b'*32);self.replace('request.json',request);low.update(request_sha256=digest(request),request_nonce=request['nonce']);self.replace('envelope.json',self.f.sign(low))
        with self.assertRaises(AppError) as raised:self.ingest()
        self.assertEqual(raised.exception.code,'worker_evidence_replay_or_fork');self.assertEqual(len(self.sql("SELECT key FROM metadata WHERE key LIKE 'worker_evidence_head:%'")),1);self.assertEqual(len(self.sql("SELECT key FROM metadata WHERE key LIKE 'worker_evidence_received:%'")),1)
    def test_changed_stored_bytes_never_replaced_by_success_record(self):
        result=self.ingest();path=self.api.real(CANONICAL+'\\received\\'+result['stored_attempt']+'\\envelope.json');path.write_bytes(path.read_bytes()+b' ')
        with self.assertRaises(AppError) as raised:self.reopen()
        self.assertEqual(raised.exception.code,'worker_evidence_stored_bytes_changed')
    def test_current_trust_and_historical_expiry_are_separate(self):
        self.ingest()
        with patch.object(receiver.time,'time',return_value=self.f.statement['expires_at']+1):
            with self.assertRaises(AppError):self.reopen()
            historic=self.reopen(historical=True);self.assertFalse(historic['baseline_admissible']);self.assertEqual(historic['worker_status'],'unknown')
        policy=copy.deepcopy(self.f.policy);policy['revoked']=[{'issuer':'lab-export','key_id':'publisher','purpose':'publisher'}];self.replace('trust.json',policy)
        with self.assertRaises(AppError):self.reopen(historical=True)
    def test_result_record_failure_preserves_committed_index_without_success(self):
        real=storage._create_file
        def writing(root,name,raw,api):
            if name=='result.json':raise OSError('injected result recording failure')
            return real(root,name,raw,api)
        with patch.object(storage,'_create_file',side_effect=writing),self.assertRaises(OSError):self.ingest()
        self.assertEqual(len(self.sql("SELECT key FROM metadata WHERE key LIKE 'worker_evidence_received:%'")),1)
        self.assertEqual(self.reopen()['desired']['description'],'Reviewed correction')
        self.assertTrue(list(self.api.real(CANONICAL+'\\received').glob('evidence-attempt-*/failure.json')))
    def test_secondary_recording_interrupt_retains_primary_failure_as_cause(self):
        self.api.real(CANONICAL+'\\input\\envelope.json').write_bytes(b'not-json');real=storage._create_file
        def writing(root,name,raw,api):
            if name=='failure.json':raise KeyboardInterrupt('literal secondary')
            return real(root,name,raw,api)
        try:
            with patch.object(storage,'_create_file',side_effect=writing):self.ingest()
        except BaseException as error:self.assertIsInstance(error,KeyboardInterrupt);self.assertIsInstance(error.__cause__,AppError)
        else:self.fail('secondary interrupt swallowed')
    def test_shared_native_link_history_and_views_reverify_on_each_read(self):
        self.ingest()
        def reopen(root,req,trust,pin,scratch,**kw):return receiver._reopen(self.store,req,trust,pin,scratch,self.api,**kw)
        with patch.object(receiver,'reopen_windows_evidence',side_effect=reopen):
            row=views.link(self.store,self.f.req['object_id'],self.root,digest(self.f.req),self.input+'\\trust.json',self.input+'\\pin.json',self.scratch)
            self.assertEqual(row['data']['evidence_store'],self.root);self.assertFalse(row['data']['baseline_admissible']);self.assertEqual(views.history(self.store,self.f.req['object_id'])['entries'][0]['journal_status'],'service_state_converged')
            from intune_iac.workbench_views import views as four
            result=four(self.store,self.f.req['object_id']);self.assertEqual(result['deployment']['baseline_kind'],'verified_signed_worker_deployment');self.assertEqual(result['proposed']['saved_plan_sha256'],'b'*64)
            self.assertFalse(result['native_evidence_access']['platform_qualified']);self.assertEqual(self.api.handles,{})
    def test_copy_backup_new_restore_relink_without_original_source(self):
        self.ingest();self.api.real(CANONICAL+'\\input\\envelope.json').write_bytes(b'invalid historical received bytes\r\n')
        with self.assertRaises(AppError):self.ingest()
        before={str(p.relative_to(self.api.real(CANONICAL+'\\received'))):p.read_bytes() for p in self.api.real(CANONICAL+'\\received').rglob('*') if p.is_file()}
        backup=receiver._copy_store(self.store,ROOT+'\\backup',self.api);backup_store=win.WindowsWorkbenchStore._open(ROOT+'\\backup',self.store.tenant_id,self.fs)
        restored_receipt=receiver._copy_store(backup_store,ROOT+'\\restored',self.api);restored=win.WindowsWorkbenchStore._open(ROOT+'\\restored',self.store.tenant_id,self.fs)
        self.assertEqual(before,{str(p.relative_to(self.api.real(CANONICAL+'\\received'))):p.read_bytes() for p in self.api.real(CANONICAL+'\\received').rglob('*') if p.is_file()})
        for name,entry in backup['files'].items():
            if name=='observations.sqlite3':continue
            self.assertEqual((self.api.real(CANONICAL+'\\restored')/name).read_bytes(),before[name])
        self.assertEqual(len(list(self.api.real(CANONICAL+'\\restored').glob('evidence-attempt-*/failure.json'))),1)
        actual=self.api.open_read_guard
        def deny_original(path,**kw):
            if path.startswith(CANONICAL+'\\received\\') or path.startswith(CANONICAL+'\\backup\\'):raise AppError('original_unavailable','fixture')
            return actual(path,**kw)
        def reopen(root,req,trust,pin,scratch,**kw):return receiver._reopen(restored,req,trust,pin,scratch,self.api,**kw)
        with patch.object(self.api,'open_read_guard',side_effect=deny_original),patch.object(receiver,'reopen_windows_evidence',side_effect=reopen):
            result=reopen(ROOT+'\\restored',digest(self.f.req),self.input+'\\trust.json',self.input+'\\pin.json',self.scratch)
            row=views.link(restored,self.f.req['object_id'],ROOT+'\\restored',digest(self.f.req),self.input+'\\trust.json',self.input+'\\pin.json',self.scratch)
            self.assertEqual(views.history(restored,self.f.req['object_id'])['entries'][0]['evidence']['bundle_sha256'],result['bundle_sha256'])
            self.assertEqual(row['data']['evidence_store'],ROOT+'\\restored')
            low=copy.deepcopy(self.f.statement);snap=low['snapshot'];snap['events']=snap['events'][:1]
            snap['job']={'status':'prepared','cancel_requested':False,'dispatches':0,'outcome':None};snap['approval']=None;snap['consumed']=None;snap['capture']=None;snap['capture_provenance']=None
            snap['journal'].update(selected_event_count=1,first_sequence=snap['events'][0]['sequence'],last_sequence=snap['events'][0]['sequence'],events_sha256=digest(snap['events']))
            request=contract.make_request(snap['manifest'],self.f.policy,'c'*32);self.replace('request.json',request);low.update(request_sha256=digest(request),request_nonce=request['nonce']);self.replace('envelope.json',self.f.sign(low))
            with self.assertRaises(AppError) as raised:receiver._ingest(restored,self.input+'\\envelope.json',self.input+'\\request.json',self.input+'\\trust.json',self.input+'\\pin.json',self.scratch,self.api)
            self.assertEqual(raised.exception.code,'worker_evidence_replay_or_fork')
        with restored._connection() as db:
            restored_rows=[tuple(row) for row in db.execute("SELECT key,value FROM metadata WHERE key LIKE 'worker_evidence_%' ORDER BY key")]
        self.assertEqual(restored_rows,self.sql("SELECT key,value FROM metadata WHERE key LIKE 'worker_evidence_%' ORDER BY key"))
        self.assertFalse(restored_receipt['current_trust_and_verifier_included']);self.assertFalse(restored_receipt['platform_qualified']);self.assertEqual(self.api.handles,{})
    def test_copy_refuses_existing_destination_and_unknown_member_without_omission(self):
        self.ingest();receiver._copy_store(self.store,ROOT+'\\backup',self.api)
        with self.assertRaises(AppError):receiver._copy_store(self.store,ROOT+'\\backup',self.api)
        storage._create_file(self.root,'unknown-private-file',b'must not disappear',self.api)
        with self.assertRaises(AppError) as raised:receiver._copy_store(self.store,ROOT+'\\blocked',self.api)
        self.assertEqual(raised.exception.code,'worker_evidence_backup_unsupported_member');self.assertTrue(self.api.real(CANONICAL+'\\received\\unknown-private-file').exists());self.assertFalse(self.api.real(CANONICAL+'\\blocked').exists())
    def test_copy_retains_partial_destination_on_recording_failure(self):
        self.ingest();real=storage._create_file
        def fail(root,name,data,api):
            if name.startswith('evidence-copy-'):raise OSError('copy receipt failure')
            return real(root,name,data,api)
        with patch.object(storage,'_create_file',side_effect=fail),self.assertRaises(OSError):receiver._copy_store(self.store,ROOT+'\\partial',self.api)
        self.assertTrue(self.api.real(CANONICAL+'\\partial\\observations.sqlite3').exists());self.assertTrue(list(self.api.real(CANONICAL+'\\partial').glob('evidence-attempt-*/envelope.json')))
        self.assertEqual(self.reopen()['desired']['description'],'Reviewed correction')
    def test_copy_rejects_target_inside_original_and_changed_indexed_bytes(self):
        result=self.ingest()
        with self.assertRaises(AppError) as raised:receiver._copy_store(self.store,self.root+'\\nested',self.api)
        self.assertEqual(raised.exception.code,'worker_evidence_backup_overlap');self.assertFalse(self.api.real(CANONICAL+'\\received\\nested').exists())
        path=self.api.real(CANONICAL+'\\received\\'+result['stored_attempt']+'\\envelope.json');path.write_bytes(path.read_bytes()+b' ')
        with self.assertRaises(AppError) as raised:receiver._copy_store(self.store,ROOT+'\\changed',self.api)
        self.assertEqual(raised.exception.code,'worker_evidence_stored_bytes_changed');self.assertFalse(self.api.real(CANONICAL+'\\changed').exists())
    def test_newer_signed_head_demotes_older_reopen_and_preserves_latest(self):
        self.ingest();new=copy.deepcopy(self.f.statement);snapshot=new['snapshot'];now=int(time.time());snapshot['read_at']=now
        snapshot['events'].append({'sequence':snapshot['events'][-1]['sequence']+1,'kind':'readonly_observation_marker','payload':{'literal':'signed local fixture, no native dispatch'},'created_at':now})
        snapshot['journal'].update(selected_event_count=len(snapshot['events']),last_sequence=snapshot['events'][-1]['sequence'],events_sha256=digest(snapshot['events']))
        request=copy.deepcopy(self.f.req);request['nonce']='d'*32;new.update(request_sha256=digest(request),request_nonce=request['nonce'],issued_at=now,expires_at=now+900)
        self.replace('envelope.json',self.f.sign(new));self.replace('request.json',request);self.ingest()
        older=self.reopen();latest=self.reopen(request)
        self.assertFalse(older['baseline_admissible']);self.assertTrue(older['historical_only']);self.assertEqual(older['worker_status'],'unknown');self.assertEqual(older['historical_snapshot_status'],'service_state_converged')
        self.assertEqual(older['receipt_currentness'],'superseded_signed_snapshot');self.assertTrue(latest['baseline_admissible']);self.assertFalse(latest['historical_only']);self.assertEqual(latest['journal_sequence'],snapshot['events'][-1]['sequence'])
        self.assertEqual(len(self.sql("SELECT key FROM metadata WHERE key LIKE 'worker_evidence_received:%'")),2)
