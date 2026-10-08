"""Inactive guarded native Ed25519 evidence verifier; no native qualification.

Only an independently approved pinned Windows libsodium image is admitted. Native
loader dependencies are restricted to System32; no fallback or key provisioning.
"""
from contextlib import ExitStack,contextmanager
import ctypes as C
import hashlib
from pathlib import PureWindowsPath
import time
from uuid import uuid4
from . import windows_capture as wc,windows_storage as ws,worker_evidence as contract
from .io import AppError,parse_json

EXPORTS={'sodium_init':(C.c_int,[]),'sodium_version_string':(C.c_char_p,[]),
    'crypto_core_ed25519_is_valid_point':(C.c_int,[C.c_void_p]),
    'crypto_scalarmult_ed25519_noclamp':(C.c_int,[C.c_void_p,C.c_void_p,C.c_void_p]),
    'crypto_core_ed25519_add':(C.c_int,[C.c_void_p,C.c_void_p,C.c_void_p]),
    'crypto_sign_verify_detached':(C.c_int,[C.c_void_p,C.c_void_p,C.c_ulonglong,C.c_void_p])}
SYSTEM32_ONLY=0x800
_SEAL=object()


def _fail(code):raise AppError(code,'The inactive native evidence verifier did not establish its image, identity, signature or cleanup contract.')


class _NativeAPI(wc._NativeAPI):
    def __init__(self):
        super().__init__()
        for name,args,result in [('LoadLibraryExW',[C.c_wchar_p,C.c_void_p,C.c_uint32],C.c_void_p),
                ('GetProcAddress',[C.c_void_p,C.c_char_p],C.c_void_p),('FreeLibrary',[C.c_void_p],C.c_int)]:
            function=getattr(self.k,name);function.argtypes=args;function.restype=result
    def load_library(self,path):
        handle=self.k.LoadLibraryExW(path,None,SYSTEM32_ONLY)
        if not handle:_fail('windows_evidence_loader_failed')
        return handle
    def export(self,handle,name):
        if name not in EXPORTS:_fail('windows_evidence_export_unsupported')
        address=self.k.GetProcAddress(handle,name.encode('ascii'))
        if not address:_fail('windows_evidence_export_missing')
        result,args=EXPORTS[name]
        return C.CFUNCTYPE(result,*args)(address)
    def unload_library(self,handle):
        if not self.k.FreeLibrary(handle):_fail('windows_evidence_unload_failed')


def _pin(value):
    contract.shape(value,'schema_version library_path library_sha256 library_bytes library_version abi dependency_policy')
    if (value['schema_version']!='windows-worker-evidence-verifier/1' or value['abi']!='win64-cdecl-ed25519-v1'
            or value['dependency_policy']!='system32_only' or value['library_version'] not in ('1.0.18','1.0.19','1.0.20')):_fail('windows_evidence_pin_invalid')
    contract.hashed(value['library_sha256']);contract.number(value['library_bytes'],256,16*1024*1024)
    wc.wd._components(value['library_path']);return value


def _pe(raw):
    if len(raw)<256 or raw[:2]!=b'MZ':_fail('windows_evidence_image_invalid')
    offset=int.from_bytes(raw[0x3c:0x40],'little')
    if (offset<64 or offset+26>len(raw) or raw[offset:offset+4]!=b'PE\0\0'
            or int.from_bytes(raw[offset+4:offset+6],'little')!=0x8664
            or not int.from_bytes(raw[offset+22:offset+24],'little')&0x2000
            or int.from_bytes(raw[offset+24:offset+26],'little')!=0x20b):_fail('windows_evidence_image_invalid')


class _Verifier:
    def __init__(self,seal,functions,guard,metadata):
        if seal is not _SEAL:_fail('windows_evidence_capability')
        self.functions,self.guard,self.metadata,self.active=functions,guard,metadata,True
    def __call__(self,key,message,signature):
        if not self.active:_fail('windows_evidence_verifier_closed')
        contract.hashed(key)
        if type(message) is not bytes or len(message)>contract.MAX_BYTES or type(signature) is not bytes or len(signature)!=64:_fail('windows_evidence_signature_shape')
        self.guard.revalidate();public=C.create_string_buffer(bytes.fromhex(key),32);f=self.functions
        if f['crypto_core_ed25519_is_valid_point'](public)!=1:_fail('approval_weak_public_key')
        order=C.create_string_buffer(bytes.fromhex('ecd3f55c1a631258d69cf7a2def9de1400000000000000000000000000000010'),32)
        product=C.create_string_buffer(32);total=C.create_string_buffer(32)
        if (f['crypto_scalarmult_ed25519_noclamp'](product,order,public)!=0
                or f['crypto_core_ed25519_add'](total,product,public)!=0 or total.raw!=b'\x01'+bytes(31)):_fail('approval_weak_public_key')
        signed=C.create_string_buffer(signature,64);data=C.create_string_buffer(message,len(message))
        if f['crypto_sign_verify_detached'](signed,data,len(message),public)!=0:_fail('worker_evidence_signature_invalid')
        self.guard.revalidate()
    def __reduce_ex__(self,_):raise TypeError('Native verifier capabilities cannot be serialized.')


@contextmanager
def _verifier(pin,scratch,api):
    pin=_pin(contract.bounded(pin));wc.wd._components(scratch)
    source=PureWindowsPath(pin['library_path']);copy_root=None;library=None;capability=None;primary=None;stack=ExitStack()
    try:
        original=stack.enter_context(wc._directory(source.parent,api));raw=original.read(source.name,16*1024*1024)
        if len(raw)!=pin['library_bytes'] or hashlib.sha256(raw).hexdigest()!=pin['library_sha256']:_fail('windows_evidence_image_pin')
        _pe(raw);original.revalidate()
        # A unique private path avoids loader-cache aliases to an earlier image.
        name='evidence-verifier-'+uuid4().hex;ws._create_directory(scratch,name,api);copy_root=PureWindowsPath(scratch)/name
        ws._create_file(str(copy_root),'sodium.dll',raw,api)
        copied=stack.enter_context(wc._directory(copy_root,api))
        if set(copied.names())!={'sodium.dll'} or copied.read('sodium.dll')!=raw:_fail('windows_evidence_copy_changed')
        copied.revalidate();original.revalidate()
        library=api.load_library(str(copied.native/'sodium.dll'))
        functions={name:api.export(library,name) for name in EXPORTS}
        if functions['sodium_init']()<0 or functions['sodium_version_string']()!=pin['library_version'].encode('ascii'):_fail('windows_evidence_abi_mismatch')
        copied.revalidate();original.revalidate()
        capability=_Verifier(_SEAL,functions,copied,{'library_sha256':pin['library_sha256'],'source_identity':original.files[source.name]['identity'],
            'loaded_copy_identity':copied.files['sodium.dll']['identity'],'retained_copy':str(copy_root),'dependency_search':'System32 only',
            'platform_qualified':False,'workbench_profile_enabled':False})
        yield capability
        copied.revalidate();original.revalidate()
    except BaseException as error:
        primary=error
        error.native_evidence_outcome={'retained_copy':str(copy_root) if copy_root else None,'loaded':library is not None,'platform_qualified':False}
        raise
    finally:
        if capability is not None:capability.active=False
        cleanup=[]
        if library is not None:
            try:api.unload_library(library)
            except BaseException as error:cleanup.append(error)
        try:stack.close()
        except BaseException as error:cleanup.append(error)
        if cleanup:
            interruption=next((e for e in cleanup if isinstance(e,(KeyboardInterrupt,SystemExit))),None)
            if primary is not None:
                primary.native_verifier_cleanup_failures=[type(e).__name__ for e in cleanup]
                if interruption is not None:raise interruption from primary
                if hasattr(primary,'add_note'):primary.add_note('Native verifier cleanup also failed; copied image and primary failure retained.')
            elif interruption is not None:raise interruption
            else:_fail('windows_evidence_cleanup_failed')


def verifier(pin,scratch):
    """Existing authority must supply exact approved image; no support activation."""
    return _verifier(pin,scratch,_NativeAPI())


def _inspect(envelope_path,request_path,trust_path,pin_path,scratch,api,*,historical=False):
    read=lambda path:parse_json(wc._reference_bytes(path,api,contract.MAX_BYTES))
    envelope,request,trust,pin=(read(path) for path in (envelope_path,request_path,trust_path,pin_path))
    with _verifier(pin,scratch,api) as checked:
        result=contract.verify_envelope(envelope,request,trust,checked,now=int(time.time()),historical=historical).result()
        result['native_verifier']=checked.metadata
    return result


def inspect_windows_evidence(envelope_path,request_path,trust_path,pin_path,scratch,*,historical=False):
    return _inspect(envelope_path,request_path,trust_path,pin_path,scratch,_NativeAPI(),historical=historical)
