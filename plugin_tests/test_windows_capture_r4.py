"""Actual capture bytes and SQLite; recorded Win32 effects are not native proof."""
import base64
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from intune_iac import windows_capture as reader, windows_workbench as store_module
from intune_iac import windows_storage as storage
from intune_iac.capture import capture
from intune_iac.io import AppError
from plugin_tests.test_windows_workbench_r4 import FilesystemAPI
from plugin_tests.test_windows_storage_r4 import ROOT, CANONICAL
from plugin_tests.test_capture_adapter import ROOT as PROJECT, T, P
from plugin_tests.test_workbench_provenance import policy


class WindowsCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name); self.api = FilesystemAPI(self.base/'native-recorded')
        self.fs = store_module._Filesystem(self.api, self.api.connect)
        self.store = store_module.WindowsWorkbenchStore._create(ROOT+'\\store',T,self.fs)
        fixture = json.loads((PROJECT/'examples/supported/input/export.json').read_text())
        self.responses = {page['request_url']:(page['http_status'],json.dumps(page['body']).encode())
            for collection in fixture['collections'] for page in collection['pages']}
        for url, (status, raw) in list(self.responses.items()):
            if url.endswith('/assignments'):
                body=json.loads(raw)
                for row in body['value']: row.update(source='direct',sourceId=None)
                self.responses[url]=(status,json.dumps(body).encode())
        self.path=ROOT+'\\capture'; self.real=self.api.real(CANONICAL+'\\capture')

    def make(self):
        original=self.base/'capture-original'
        capture(T,P,original,transport=lambda url:self.responses[url],source_is_synthetic=True)
        storage._create_directory(ROOT,'capture',self.api)
        storage._create_directory(self.path,'raw',self.api)
        for source in original.rglob('*'):
            if source.is_file():
                parent=self.path+('\\raw' if source.parent.name=='raw' else '')
                storage._create_file(parent,source.name,source.read_bytes(),self.api)
        return original

    def test_import_reopen_raw_projection_exact_values_and_no_authentication(self):
        self.make(); receipt=self.store.import_capture(self.path)
        self.assertEqual(receipt['status'],'complete')
        reopened=store_module.WindowsWorkbenchStore._open(ROOT+'\\store',T,self.fs)
        detail=reopened.inspect(P)
        self.assertEqual(detail['body']['name'],'Windows Privacy Pilot')
        self.assertEqual(len(detail['body']['assignments']),3)
        self.assertEqual(detail['source']['tenant_assurance'],'caller_asserted')
        self.assertFalse(detail['source']['source_authenticity_verified'])
        self.assertTrue(detail['source']['source_is_synthetic'])
        literal=reopened.raw_capture_observation(P)
        self.assertEqual(literal['capture_integrity']['status'],'verified_local_bytes')
        self.assertEqual(literal['source']['raw_observed']['policy']['id'],P)
        with sqlite3.connect(self.api.real(CANONICAL+'\\store\\observations.sqlite3')) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM collection_runs').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM snapshots').fetchone()[0],1)
        self.assertEqual(self.api.handles,{})

    def test_denied_assignments_retains_attempt_without_snapshot(self):
        url=next(url for url in self.responses if url.endswith('/assignments'))
        self.responses[url]=(403,b'{"error":{"message":"secret-canary"}}');self.make()
        result=self.store.import_capture(self.path);self.assertEqual(result['status'],'denied')
        self.assertEqual(self.store.history(P),[])
        raw=self.store.raw_capture_observation(P)
        self.assertEqual(raw['capture_integrity']['status'],'verified_local_bytes')
        self.assertNotIn('secret-canary',json.dumps(raw))

    def test_unknown_mapping_is_preserved_without_normalized_current_snapshot(self):
        url=next(url for url in self.responses if url.endswith('/settings'))
        status,raw=self.responses[url];body=json.loads(raw)
        body['value'][0]['settingInstance']['choiceSettingValue']['value']='future-choice'
        self.responses[url]=(status,json.dumps(body).encode());self.make()
        result=self.store.import_capture(self.path);self.assertEqual(result['status'],'unsupported')
        literal=self.store.raw_capture_observation(P)
        self.assertIn('future-choice',json.dumps(literal['source']['raw_observed']))
        self.assertEqual(literal['capture_integrity']['status'],'verified_local_bytes')
        self.assertEqual(self.store.history(P),[])

    def test_later_raw_mutation_invalidates_retained_projection_without_erasing_it(self):
        self.make();self.store.import_capture(self.path)
        page=self.real/'raw/page-000000.json';page.write_bytes(page.read_bytes()+b' ')
        literal=self.store.raw_capture_observation(P)
        self.assertEqual(literal['capture_integrity']['status'],'unverified_or_changed')
        self.assertEqual(literal['source']['raw_observed']['policy']['id'],P)
        self.assertEqual(len(self.store.collection_history(P)),1)

    def test_wrong_owner_hardlink_volume_and_tenant_rejected_before_publication(self):
        self.make()
        for bad in ({'owner_sid':'S-1-5-18'},{'links':2},{'volume_serial':999}):
            self.api.bad_file=bad
            with self.subTest(bad=bad),self.assertRaises(AppError):reader._load(self.path,T,self.api)
        self.api.bad_file={}
        with self.assertRaises(AppError):reader._load(self.path,'33333333-3333-4333-8333-333333333333',self.api)
        self.assertEqual(self.store.collection_history(P),[]);self.assertEqual(self.api.handles,{})

    def test_namespace_added_after_semantics_is_rejected_and_preserved(self):
        self.make();original=self.api.names;calls={}
        def names(path):
            calls[path]=calls.get(path,0)+1
            if path==CANONICAL+'\\capture' and calls[path]==2:
                (self.real/'unexpected.tmp').write_bytes(b'retain discrepancy')
            return original(path)
        self.api.names=names
        with self.assertRaises(AppError) as caught:self.store.import_capture(self.path)
        self.assertEqual(caught.exception.code,'windows_capture_namespace_changed')
        self.assertEqual((self.real/'unexpected.tmp').read_bytes(),b'retain discrepancy')
        self.assertEqual(self.store.collection_history(P),[]);self.assertEqual(self.api.handles,{})

    def test_file_changes_after_read_are_rejected_before_publication(self):
        self.make();original=self.api.read;seen={}
        def read(handle):
            path=self.api.handles[handle][1];seen[path]=seen.get(path,0)+1
            if path.endswith('page-000000.json') and seen[path]==2:
                self.api.real(path).write_bytes(b'substituted')
            return original(handle)
        self.api.read=read
        with self.assertRaises(AppError):self.store.import_capture(self.path)
        self.assertEqual(self.store.collection_history(P),[]);self.assertEqual(self.api.handles,{})

    def test_reference_exact_bytes_provenance_unknowns_and_reopen(self):
        value=policy();value['unknownVendorField']={'bool':True,'null':None,'empty':[]}
        raw=json.dumps(value,indent=2).replace('\n','\r\n').encode()
        storage._create_file(ROOT,'- reference 雪.json',raw,self.api)
        row=self.store.reference_import(ROOT+'\\- reference 雪.json',hashlib.sha256(raw).hexdigest(),
            'a'*40,'https://example.invalid/blob/'+'a'*40+'/policy.json','GPL-3.0')
        reopened=store_module.WindowsWorkbenchStore._open(ROOT+'\\store',T,self.fs)
        data=reopened.artifacts(kind='source_reference')[0]['data']
        self.assertEqual(base64.b64decode(data['raw_bytes_base64']),raw)
        self.assertEqual(data['raw_source'],value);self.assertFalse(data['execution_authorized'])
        self.assertEqual(data['tenant_object_identity'],'not_established')
        self.assertEqual(data['assertion_class'],'community_reference')
        self.assertIn('unknownVendorField',data['unknown_fields'])

    def test_reference_wrong_pin_and_oversize_fail_without_artifact(self):
        raw=json.dumps(policy()).encode();storage._create_file(ROOT,'reference.json',raw,self.api)
        with self.assertRaises(AppError):self.store.reference_import(ROOT+'\\reference.json','0'*64,'a'*40,'https://example.invalid/p','GPL-3.0')
        self.api.real(CANONICAL+'\\reference.json').write_bytes(b'x'*(512*1024+1))
        with self.assertRaises(AppError) as caught:reader._reference_bytes(ROOT+'\\reference.json',self.api,512*1024)
        self.assertEqual(caught.exception.code,'windows_capture_limit')
        self.assertEqual(self.store.artifacts(kind='source_reference'),[])

    def test_public_native_reader_rejects_linux_and_never_activates_profile(self):
        if sys.platform=='win32':self.skipTest('Linux guard scope')
        with self.assertRaises(AppError) as caught:reader.load_windows_capture(self.path,tenant_id=T)
        self.assertEqual(caught.exception.code,'windows_directory_platform_unsupported')

    def test_qualification_text_routes_reuse_engine_and_leave_database_bytes_unchanged(self):
        from contextlib import redirect_stdout,redirect_stderr
        self.make();self.store.import_capture(self.path)
        launcher=Path(store_module.__file__).resolve().parents[1]/'scripts/intune-windows-inspect.py'
        spec=importlib.util.spec_from_file_location('native_inspection_launcher',launcher)
        app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)
        database=self.api.real(CANONICAL+'\\store\\observations.sqlite3');before=database.read_bytes()
        with patch.object(app,'WindowsWorkbenchStore',lambda root,tenant:store_module.WindowsWorkbenchStore._open(root,tenant,self.fs)):
            for command in (['overview'],['inspect',P],['raw',P],['history',P],['collections'],['operations'],['artifacts'],['storage-status']):
                stdout=io.StringIO();stderr=io.StringIO()
                with redirect_stdout(stdout),redirect_stderr(stderr):
                    code=app.main(['--qualification-only','--store',ROOT+'\\store','--tenant',T,*command])
                self.assertEqual(code,0,stderr.getvalue());value=json.loads(stdout.getvalue())
                self.assertTrue(value['qualification_only']);self.assertFalse(value['platform_qualified'])
                self.assertNotIn('\x1b',stdout.getvalue())
                self.assertEqual(database.read_bytes(),before)
                if command[0]=='inspect':self.assertEqual(value['result']['body']['name'],'Windows Privacy Pilot')
        self.assertEqual(self.api.handles,{})

    def test_actual_no_tty_launcher_rejects_linux_and_missing_explicit_mode(self):
        if sys.platform=='win32':self.skipTest('Linux guard scope')
        launcher=Path(store_module.__file__).resolve().parents[1]/'scripts/intune-windows-inspect.py'
        args=[sys.executable,'-B',str(launcher),'--store',ROOT+'\\absent','--tenant',T,'overview']
        missing=subprocess.run(args,capture_output=True,timeout=10)
        self.assertEqual(missing.returncode,2)
        guarded=subprocess.run(args[:3]+['--qualification-only']+args[3:],capture_output=True,timeout=10)
        self.assertEqual(guarded.returncode,3);self.assertEqual(guarded.stdout,b'')
        self.assertEqual(json.loads(guarded.stderr)['error']['code'],'windows_directory_platform_unsupported')

    def test_native_procedure_retains_timed_out_command_and_partial_bytes(self):
        path=Path(store_module.__file__).resolve().parents[1]/'scripts/qualify-windows-readers.py'
        spec=importlib.util.spec_from_file_location('native_readers_procedure',path)
        app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)
        result={'commands':[]};command=['pinned-python','exact-script','--qualification-only']
        error=subprocess.TimeoutExpired(command,30,output=b'partial stdout\r\n',stderr=b'partial stderr\x00')
        with patch.object(app.subprocess,'run',side_effect=error),self.assertRaises(subprocess.TimeoutExpired):
            app._run('read',command,self.base,result)
        self.assertEqual(result['commands'],[{'id':'read','argv':command,'exit':None,'timed_out':True}])
        self.assertEqual((self.base/'read.stdout.raw').read_bytes(),b'partial stdout\r\n')
        self.assertEqual((self.base/'read.stderr.raw').read_bytes(),b'partial stderr\x00')


if __name__=='__main__':unittest.main()
