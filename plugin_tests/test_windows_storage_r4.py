"""Windows storage state-machine contracts; no modeled call is native evidence."""
import ctypes as C
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from intune_iac.io import AppError
from intune_iac import windows_storage as ws

SID='S-1-5-21-111-222-333-1001'
VOLUME='\\\\?\\Volume{12345678-1234-1234-1234-123456789abc}\\'
ROOT='C:\\Pilot\\Private'
CANONICAL=VOLUME+'Pilot\\Private'


class RecordedStorage:
    def __init__(self):
        self.directories={VOLUME:1,VOLUME+'Pilot':2,CANONICAL:3};self.files={};self.handles={};self.sequence=100
        self.events=[];self.failure=None;self.locks={};self.bad_file={};self.close_fail=False
    def current_sid(self):return SID
    def volume(self,drive):return VOLUME
    def _open(self,path,kind):
        self.sequence+=1;self.handles[self.sequence]=(kind,path);self.events.append(('open',kind,path));return self.sequence
    def open_directory(self,path):
        if path not in self.directories:raise AppError('fixture_missing_directory','fixture')
        return self._open(path,'directory')
    def mutable_directory(self,path):return self.open_directory(path)
    def metadata(self,handle,*,private):
        kind,path=self.handles[handle]
        value={'volume_serial':77,'file_id':format(self.directories[path],'032x'),'final_path':path,'filesystem':'NTFS','reparse':False}
        if private:value.update(owner_sid=SID,dacl_protected=True,aces=[{'type':'allow','sid':SID,'mask':0x1f01ff,'flags':3}])
        return value
    def create_directory(self,path,sid):
        self.events.append(('create-directory',path,sid))
        if path in self.directories:raise AppError('windows_storage_destination_exists','fixture')
        self.directories[path]=len(self.directories)+1
    def open_file(self,path,sid,*,create=False,lock=False):
        if create:
            self.events.append(('create-file',path,sid))
            if path in self.files:raise AppError('windows_storage_destination_exists','fixture')
            self.files[path]={'data':b'','id':len(self.files)+10}
        if path not in self.files:raise AppError('fixture_missing_file','fixture')
        return self._open(path,'file')
    def file_metadata(self,handle,sid):
        _,path=self.handles[handle];file=self.files[path]
        return {'volume_serial':77,'file_id':format(file['id'],'032x'),'bytes':len(file['data']),'links':1,'owner_sid':SID}|self.bad_file
    def write(self,handle,data):
        path=self.handles[handle][1];self.events.append(('write',path,data));self.files[path]['data']=data
        if self.failure=='write-interrupt':
            self.files[path]['data']=data[:2];raise KeyboardInterrupt()
        if self.failure=='write':raise AppError('windows_storage_write_failed','fixture')
    def read(self,handle):return self.files[self.handles[handle][1]]['data']
    def flush_file(self,handle):
        self.events.append(('flush-file',self.handles[handle][1]))
        if self.failure=='file-flush':raise AppError('windows_storage_file_flush_failed','fixture')
    def flush_namespace(self,handle):
        self.events.append(('flush-namespace',self.handles[handle][1]))
        if self.failure=='namespace':raise AppError('windows_storage_namespace_flush_unavailable','fixture')
    def rename_new(self,handle,root_handle,name):
        source=self.handles[handle][1];destination=self.handles[root_handle][1]+'\\'+name
        self.events.append(('rename-new',source,destination))
        if destination in self.files:raise AppError('windows_storage_destination_exists','fixture')
        self.files[destination]=self.files.pop(source);self.handles[handle]=('file',destination)
        if self.failure=='rename-ack':raise AppError('windows_storage_rename_failed','fixture')
        if self.failure=='rename-interrupt':raise KeyboardInterrupt()
    def lock(self,handle):
        path=self.handles[handle][1]
        if path in self.locks:raise AppError('windows_storage_lock_busy','fixture')
        self.locks[path]=handle;self.events.append(('lock',path));return object()
    def unlock(self,handle,overlap):
        path=self.handles[handle][1];self.locks.pop(path);self.events.append(('unlock',path))
        if self.failure=='unlock':raise AppError('windows_storage_unlock_failed','fixture')
    def close(self,handle):
        value=self.handles.pop(handle);self.events.append(('close',*value))
        if self.close_fail:raise AppError('fixture_close_failure','fixture')


class WindowsStorageContractTests(unittest.TestCase):
    def test_atomic_private_creation_flushes_child_and_parent_without_profile_activation(self):
        api=RecordedStorage();value=ws._create_directory(ROOT,'new - 雪',api)
        self.assertIn(CANONICAL+'\\new - 雪',api.directories)
        self.assertIn(('create-directory',CANONICAL+'\\new - 雪',SID),api.events)
        flushes=[row[1] for row in api.events if row[0]=='flush-namespace']
        self.assertEqual(flushes,[CANONICAL+'\\new - 雪',CANONICAL])
        self.assertEqual(value['schema_version'],'intune-windows-storage/1')
        self.assertFalse(value['workbench_profile_enabled']);self.assertFalse(value['platform_qualified'])
        self.assertEqual(api.handles,{})

    def test_binary_create_new_never_overwrites_and_retains_exact_bytes(self):
        api=RecordedStorage();payload=b'line1\r\nline2\x00\xff'
        value=ws._create_file(ROOT,'- binary.bin',payload,api)
        self.assertEqual(api.files[CANONICAL+'\\- binary.bin']['data'],payload)
        self.assertEqual(value['sha256'],hashlib.sha256(payload).hexdigest())
        with self.assertRaises(AppError) as caught:ws._create_file(ROOT,'- binary.bin',b'bad',api)
        self.assertEqual(caught.exception.code,'windows_storage_destination_exists')
        self.assertEqual(api.files[CANONICAL+'\\- binary.bin']['data'],payload)
        self.assertEqual(api.handles,{})

    def test_exclusive_handle_relative_publication_preserves_identity_and_exact_digest(self):
        api=RecordedStorage();data=b'\x00\xff\r\n';sha=hashlib.sha256(data).hexdigest()
        before=ws._create_file(ROOT,'stage',data,api)
        value=ws._publish(ROOT,'stage','final',sha,api)
        self.assertNotIn(CANONICAL+'\\stage',api.files)
        self.assertEqual(api.files[CANONICAL+'\\final']['data'],data)
        self.assertEqual(value['file_id'],before['file_id'])
        self.assertIn(('rename-new',CANONICAL+'\\stage',CANONICAL+'\\final'),api.events)
        self.assertEqual(api.handles,{})

    def test_known_bad_digest_and_destination_do_not_change_names_or_bytes(self):
        api=RecordedStorage();ws._create_file(ROOT,'stage',b'candidate',api);ws._create_file(ROOT,'final',b'prior',api)
        for digest,error in [('0'*64,'windows_storage_digest_mismatch'),(hashlib.sha256(b'candidate').hexdigest(),'windows_storage_destination_exists')]:
            with self.subTest(error=error),self.assertRaises(AppError) as caught:ws._publish(ROOT,'stage','final',digest,api)
            self.assertEqual(caught.exception.code,error)
            self.assertEqual(api.files[CANONICAL+'\\stage']['data'],b'candidate')
            self.assertEqual(api.files[CANONICAL+'\\final']['data'],b'prior')
        self.assertEqual(api.handles,{})

    def test_missing_namespace_barrier_retains_file_and_never_acknowledges_durable_success(self):
        api=RecordedStorage();api.failure='namespace'
        with self.assertRaises(AppError) as caught:ws._create_file(ROOT,'partial',b'preserved',api)
        self.assertEqual(caught.exception.code,'windows_storage_namespace_flush_unavailable')
        self.assertEqual(api.files[CANONICAL+'\\partial']['data'],b'preserved')
        self.assertTrue(caught.exception.storage_outcome['outcome_uncertain'])
        self.assertFalse(caught.exception.storage_outcome['automatic_retry_permitted'])
        self.assertEqual(api.handles,{})

    def test_cancellation_after_partial_write_or_possible_rename_retains_exact_evidence(self):
        api=RecordedStorage();api.failure='write-interrupt'
        with self.assertRaises(KeyboardInterrupt) as caught:ws._create_file(ROOT,'partial',b'abcde',api)
        self.assertEqual(api.files[CANONICAL+'\\partial']['data'],b'ab')
        self.assertEqual(caught.exception.storage_outcome['phase'],'writing_file')
        self.assertEqual(api.handles,{})
        api=RecordedStorage();ws._create_file(ROOT,'stage',b'exact',api);api.failure='rename-interrupt'
        with self.assertRaises(KeyboardInterrupt) as caught:ws._publish(ROOT,'stage','final',hashlib.sha256(b'exact').hexdigest(),api)
        self.assertEqual(api.files[CANONICAL+'\\final']['data'],b'exact')
        self.assertEqual(caught.exception.storage_outcome['phase'],'rename_dispatched')
        self.assertEqual(api.handles,{})

    def test_directory_barrier_failure_preserves_new_directory_and_cleanup_failure_is_uncertain(self):
        api=RecordedStorage();api.failure='namespace'
        with self.assertRaises(AppError) as caught:ws._create_directory(ROOT,'retained',api)
        self.assertIn(CANONICAL+'\\retained',api.directories)
        self.assertTrue(caught.exception.storage_outcome['outcome_uncertain'])
        self.assertEqual(api.handles,{})
        api=RecordedStorage();api.close_fail=True
        with self.assertRaises(AppError) as caught:ws._create_file(ROOT,'retained',b'known',api)
        self.assertEqual(api.files[CANONICAL+'\\retained']['data'],b'known')
        self.assertEqual(caught.exception.storage_outcome['phase'],'readback_verified_closing')
        self.assertEqual(api.handles,{})

    def test_possible_commit_then_failed_ack_or_namespace_flush_stays_uncertain(self):
        for failure in ('rename-ack','namespace'):
            api=RecordedStorage();data=b'exact';ws._create_file(ROOT,'stage',data,api);api.failure=failure
            with self.subTest(failure=failure),self.assertRaises(AppError) as caught:
                ws._publish(ROOT,'stage','final',hashlib.sha256(data).hexdigest(),api)
            self.assertTrue(caught.exception.storage_outcome['outcome_uncertain'])
            self.assertEqual(caught.exception.storage_outcome['artifacts_preserved'],['stage','final'])
            self.assertEqual(api.files[CANONICAL+'\\final']['data'],data)
            self.assertEqual(api.handles,{})

    def test_wrong_owner_link_or_volume_prevents_write(self):
        for bad in ({'owner_sid':'S-1-5-18'},{'links':2},{'volume_serial':999}):
            api=RecordedStorage();api.bad_file=bad
            with self.subTest(bad=bad),self.assertRaises(AppError):ws._create_file(ROOT,'candidate',b'never',api)
            self.assertFalse(any(row[0]=='write' for row in api.events))
            self.assertEqual(api.handles,{})

    def test_named_lock_rejects_overlap_then_allows_reacquisition(self):
        api=RecordedStorage()
        with ws._lock(ROOT,'scope.lock',api):
            with self.assertRaises(AppError) as caught:
                with ws._lock(ROOT,'scope.lock',api):self.fail('overlap admitted')
            self.assertEqual(caught.exception.code,'windows_storage_lock_busy')
            self.assertEqual(len(api.locks),1)
        with ws._lock(ROOT,'scope.lock',api):self.assertEqual(len(api.locks),1)
        self.assertEqual(api.locks,{})
        self.assertEqual(api.handles,{})

    def test_primary_failure_survives_unlock_and_close_failures(self):
        api=RecordedStorage()
        with self.assertRaisesRegex(RuntimeError,'primary') as caught:
            with ws._lock(ROOT,'scope.lock',api):
                api.failure='unlock';api.close_fail=True;raise RuntimeError('primary')
        self.assertTrue(any('lock release failed' in note for note in caught.exception.__notes__))
        self.assertTrue(any('cleanup failed' in note for note in caught.exception.__notes__))
        self.assertEqual(api.handles,{})

    def test_untrusted_names_and_nonbinary_payloads_fail_before_file_mutation(self):
        for name in ('..','a\\b','a/b','stream:secret','CON','trailing.','bad\x1b'):
            api=RecordedStorage()
            with self.subTest(name=repr(name)),self.assertRaises(AppError):ws._create_file(ROOT,name,b'bad',api)
            self.assertEqual(api.files,{})
        with self.assertRaises(AppError):ws._create_file(ROOT,'a','not binary',RecordedStorage())

    def test_exact_rename_packet_and_nonreplacement_flag_are_independently_asserted(self):
        api=ws._Win32Storage.__new__(ws._Win32Storage)
        class Kernel:
            def SetFileInformationByHandle(self,handle,kind,buffer,size):
                self.values=(handle,kind,C.string_at(buffer,size));return 1
        api.k=Kernel();api.rename_new(123,456,'雪.bin')
        handle,kind,raw=api.k.values
        self.assertEqual((handle,kind),(123,3))
        self.assertEqual(int.from_bytes(raw[:4],'little'),0)
        self.assertEqual(int.from_bytes(raw[8:16],'little'),456)
        count=int.from_bytes(raw[16:20],'little')
        self.assertEqual(raw[20:20+count],'雪.bin'.encode('utf-16-le'))
        self.assertEqual(C.sizeof(ws._SecurityAttributes),24);self.assertEqual(C.sizeof(ws._Overlapped),32)

    def test_native_write_wrapper_handles_partial_progress_and_rejects_zero_progress(self):
        api=ws._Win32Storage.__new__(ws._Win32Storage)
        class Kernel:
            def __init__(self):self.data=b'';self.zero=False
            def WriteFile(self,handle,buffer,size,written,overlap):
                count=0 if self.zero else min(3,size)
                self.data+=C.string_at(buffer,count);written._obj.value=count;return 1
        api.k=Kernel();payload=b'abc\x00\xff\r\ndef'
        api.write(123,payload)
        self.assertEqual(api.k.data,payload)
        api.k.zero=True
        with self.assertRaises(AppError) as caught:api.write(123,b'x')
        self.assertEqual(caught.exception.code,'windows_storage_write_failed')

    def test_native_read_wrapper_preserves_binary_chunks_and_enforces_total_bound(self):
        api=ws._Win32Storage.__new__(ws._Win32Storage)
        class Kernel:
            def __init__(self,data):self.data=data;self.offset=0
            def SetFilePointerEx(self,*args):self.offset=0;return 1
            def ReadFile(self,handle,buffer,size,count,overlap):
                chunk=self.data[self.offset:self.offset+3];self.offset+=len(chunk)
                C.memmove(buffer,chunk,len(chunk));count._obj.value=len(chunk);return 1
        payload=b'\x00\xff\r\nexact';api.k=Kernel(payload)
        self.assertEqual(api.read(123),payload)
        with patch.object(ws,'MAX_BYTES',4),self.assertRaises(AppError) as caught:api.read(123)
        self.assertEqual(caught.exception.code,'windows_storage_file_limit')

    def test_create_error_is_captured_before_localfree_and_descriptor_is_atomic_private(self):
        api=ws._Win32Storage.__new__(ws._Win32Storage);last={'value':0};observed={}
        class Security:
            def ConvertStringSecurityDescriptorToSecurityDescriptorW(self,text,revision,descriptor,size):
                observed['sddl']=text;descriptor._obj.value=42;size._obj.value=64;return 1
        class Kernel:
            def CreateFileW(self,path,access,share,security,disposition,flags,template):
                observed['inherit']=security._obj.inherit;observed['creation']=disposition
                last['value']=183;return C.c_void_p(-1).value
            def LocalFree(self,pointer):last['value']=0;observed['freed']=pointer.value;return None
        api.a=Security();api.k=Kernel()
        with patch.object(C,'get_last_error',lambda:last['value'],create=True),self.assertRaises(AppError) as caught:
            api.open_file('fixed-fixture',SID,create=True)
        self.assertEqual(caught.exception.code,'windows_storage_destination_exists')
        self.assertEqual(observed['sddl'],'O:'+SID+'D:P(A;;FA;;;'+SID+')')
        self.assertEqual(observed['inherit'],0);self.assertEqual(observed['creation'],1);self.assertEqual(observed['freed'],42)

    def test_public_api_remains_unsupported_on_linux(self):
        with patch.object(ws.wd.sys,'platform','linux'):
            for callback in (lambda:ws.create_private_directory(ROOT,'a'),lambda:ws.create_new_file(ROOT,'a',b''),
                             lambda:ws.publish_new(ROOT,'stage','final','0'*64)):
                with self.assertRaises(AppError) as caught:callback()
                self.assertEqual(caught.exception.code,'windows_directory_platform_unsupported')


class NativeStorageProcedureTests(unittest.TestCase):
    def module(self):
        path=Path(__file__).resolve().parents[1]/'scripts/qualify-windows-storage.py'
        spec=importlib.util.spec_from_file_location('native_storage_qualifier',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

    def test_independent_dotnet_oracle_rejects_wrong_owner_broad_acl_or_bytes(self):
        module=self.module();sid=SID
        row={'owner_sid':sid,'protected':True,'aces':[{'sid':sid,'type':'Allow','inherited':False,'rights':0x1f01ff}]}
        value={'schema':'independent-windows-storage-acl/1','powershell_major':7,'current_sid':sid,'file_sha256':'a'*64,
               'entries':[dict(copy.deepcopy(row),name=name) for name in ('root','file','lock')]}
        self.assertTrue(module.independent_acl(value,'a'*64))
        self.assertFalse(module.independent_acl(value,'b'*64))
        for bad in ({'owner_sid':'S-1-5-18'},{'protected':False},
                    {'aces':[{'sid':'S-1-1-0','type':'Allow','inherited':False}]}):
            changed=copy.deepcopy(value);changed['entries'][1].update(bad)
            with self.subTest(bad=bad):self.assertFalse(module.independent_acl(changed,'a'*64))

    def test_actual_linux_procedure_records_blocker_before_parent_or_native_access(self):
        if sys.platform=='win32':self.skipTest('Actual Windows qualification is a separate native gate.')
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'new-evidence'
            result=subprocess.run([sys.executable,'-B',str(root/'scripts/qualify-windows-storage.py'),
                '--disposable-parent','NO-NATIVE-FIXTURE-IS-READ','--output',str(output)],capture_output=True,timeout=10)
            self.assertEqual(result.returncode,3,result.stderr)
            value=json.loads((output/'RESULT.json').read_text())
            self.assertEqual(value['status'],'BLOCKED');self.assertEqual(value['commands'],[])
            self.assertEqual(value['checks'],[]);self.assertIsNone(value['retained_fixture'])
            self.assertFalse(value['workbench_profile_enabled']);self.assertFalse(value['platform_qualified'])


if __name__=='__main__':unittest.main()
