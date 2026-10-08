"""Recorded Win32 loader/storage boundaries; never counted as native signatures."""
import copy
import ctypes as C
import hashlib
from pathlib import Path
import tempfile
import unittest
from intune_iac import windows_worker_evidence as native,windows_storage as ws
from intune_iac.io import AppError
from plugin_tests.test_windows_workbench_r4 import FilesystemAPI
from plugin_tests.test_windows_storage_r4 import ROOT,CANONICAL

class API(FilesystemAPI):
    def __init__(self,path):
        super().__init__(path);self.loads=[];self.unloads=[];self.missing=None;self.version=b'1.0.20';self.weak=False;self.bad_signature=False;self.unload_failure=None
    def load_library(self,path):self.loads.append(path);return 123
    def unload_library(self,handle):
        self.unloads.append(handle)
        if self.unload_failure:raise self.unload_failure
    def export(self,handle,name):
        if name==self.missing:raise AppError('windows_evidence_export_missing','fixture')
        if name=='sodium_init':return lambda:0
        if name=='sodium_version_string':return lambda:self.version
        if name=='crypto_core_ed25519_is_valid_point':return lambda key:0 if self.weak else 1
        if name=='crypto_scalarmult_ed25519_noclamp':return lambda out,scalar,key:0
        if name=='crypto_core_ed25519_add':
            def add(out,left,right):C.memmove(out,b'\x01'+bytes(31),32);return 0
            return add
        if name=='crypto_sign_verify_detached':return lambda sig,msg,size,key:-1 if self.bad_signature else 0
        raise AssertionError(name)

class NativeVerifierBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.api=API(Path(self.temp.name))
        ws._create_directory(ROOT,'source',self.api);ws._create_directory(ROOT,'scratch',self.api)
        raw=bytearray(256);raw[:2]=b'MZ';raw[0x3c:0x40]=(64).to_bytes(4,'little');raw[64:68]=b'PE\0\0';raw[68:70]=(0x8664).to_bytes(2,'little');raw[86:88]=(0x2000).to_bytes(2,'little');raw[88:90]=(0x20b).to_bytes(2,'little')
        self.raw=bytes(raw);ws._create_file(ROOT+'\\source','approved-fixture.dll',self.raw,self.api)
        self.pin={'schema_version':'windows-worker-evidence-verifier/1','library_path':ROOT+'\\source\\approved-fixture.dll',
            'library_sha256':hashlib.sha256(self.raw).hexdigest(),'library_bytes':len(self.raw),'library_version':'1.0.20','abi':'win64-cdecl-ed25519-v1','dependency_policy':'system32_only'}
    def opened(self):return native._verifier(self.pin,ROOT+'\\scratch',self.api)
    def test_private_unique_copy_held_revalidated_and_explicitly_closed(self):
        with self.opened() as verify:
            verify('1'*64,b'literal',b'2'*64);self.assertTrue(self.api.handles);copy_root=verify.metadata['retained_copy'];self.assertFalse(verify.metadata['platform_qualified'])
        self.assertEqual(self.api.unloads,[123]);self.assertEqual(self.api.handles,{})
        self.assertTrue(self.api.real(CANONICAL+copy_root[len(ROOT):]+'\\sodium.dll').exists())
        with self.assertRaises(AppError):verify('1'*64,b'literal',b'2'*64)
    def test_wrong_pin_and_non_dll_block_before_loader(self):
        self.pin['library_sha256']='0'*64
        with self.assertRaises(AppError):
            with self.opened():pass
        self.assertEqual(self.api.loads,[]);self.assertEqual(self.api.handles,{})
        with self.assertRaises(AppError):native._pe(b'not DLL')
    def test_missing_export_and_wrong_version_unload_and_preserve_copy(self):
        self.api.missing='crypto_sign_verify_detached'
        with self.assertRaises(AppError):
            with self.opened():pass
        self.assertEqual(self.api.unloads,[123]);self.assertEqual(self.api.handles,{})
        self.api.missing=None;self.api.version=b'unknown'
        with self.assertRaises(AppError):
            with self.opened():pass
        self.assertEqual(self.api.unloads,[123,123]);self.assertEqual(self.api.handles,{})
    def test_bad_signature_and_weak_key_fail_without_fallback(self):
        for weak in (False,True):
            self.api.weak=weak;self.api.bad_signature=not weak
            with self.opened() as verify,self.assertRaises(AppError):verify('1'*64,b'literal',b'2'*64)
        self.assertEqual(len(self.api.loads),2);self.assertEqual(self.api.handles,{})
    def test_changed_loaded_copy_rejected_before_verification(self):
        with self.opened() as verify:
            path=verify.metadata['retained_copy'];real=self.api.real(CANONICAL+path[len(ROOT):]+'\\sodium.dll');original=real.read_bytes();real.write_bytes(original+b'x')
            try:
                with self.assertRaises(AppError):verify('1'*64,b'literal',b'2'*64)
            finally:real.write_bytes(original)
        self.assertEqual(self.api.handles,{})
    def test_primary_error_and_cleanup_error_both_remain(self):
        error=AppError('original_failure','fixture');self.api.unload_failure=OSError('unload fixture')
        try:
            with self.opened():raise error
        except BaseException as actual:self.assertIs(actual,error);self.assertEqual(actual.native_verifier_cleanup_failures,['OSError'])
        else:self.fail('missing failure')
        self.assertEqual(self.api.handles,{})
    def test_secondary_cleanup_interrupt_keeps_primary_as_cause(self):
        error=AppError('original_failure','fixture');self.api.unload_failure=KeyboardInterrupt('fixture')
        try:
            with self.opened():raise error
        except BaseException as actual:self.assertIsInstance(actual,KeyboardInterrupt);self.assertIs(actual.__cause__,error)
        else:self.fail('interrupt swallowed')
        self.assertEqual(self.api.handles,{})
    def test_loader_uses_only_explicit_system32_search_flag(self):
        api=object.__new__(native._NativeAPI);calls=[]
        class Kernel:
            def LoadLibraryExW(self,*args):calls.append(args);return 3
        api.k=Kernel();self.assertEqual(api.load_library('literal-absolute-pinned-path'),3)
        self.assertEqual(calls,[('literal-absolute-pinned-path',None,0x800)])
