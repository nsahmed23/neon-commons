"""Read an explicitly named existing Windows Generic Credential; never provision.

This module has no CredWrite/Delete, ambient environment or account-creation
route. Process memory still needs host protection; Python strings cannot promise
complete erasure. Credential labels never replace receiving-service identity.
"""
from contextlib import contextmanager
import ctypes as C
from dataclasses import asdict,dataclass
import os
import re
from . import windows_directory as wd
from .identity_binding import ClientSecretHandle
from .io import AppError,digest

_NATIVE=object();_LAB=object()

def _fail(code):raise AppError(code,'The explicitly configured native observer credential is unavailable or changed.') from None

@dataclass(frozen=True)
class CredentialReference:
    target: str
    owner_sid: str
    client_id: str
    encoding: str='utf-8'
    def validate(self):
        if (type(self.target) is not str or not re.fullmatch(r'IntuneWorkbench/observer/[A-Za-z0-9._-]{1,128}',self.target)
                or type(self.owner_sid) is not str or not wd._SID.fullmatch(self.owner_sid)
                or type(self.client_id) is not str or not re.fullmatch(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}',self.client_id)
                or self.encoding!='utf-8'):_fail('windows_observer_credential_reference_invalid')
        return self

class _FileTime(C.Structure):_fields_=[('low',C.c_uint32),('high',C.c_uint32)]
class _Credential(C.Structure):
    _fields_=[('flags',C.c_uint32),('type',C.c_uint32),('target',C.c_wchar_p),('comment',C.c_wchar_p),
        ('last_written',_FileTime),('blob_size',C.c_uint32),('blob',C.c_void_p),('persist',C.c_uint32),
        ('attribute_count',C.c_uint32),('attributes',C.c_void_p),('alias',C.c_wchar_p),('username',C.c_wchar_p)]

class _Win32Credentials(wd._Win32):
    def __init__(self):
        super().__init__()
        self.a.CredReadW.argtypes=[C.c_wchar_p,C.c_uint32,C.c_uint32,C.POINTER(C.POINTER(_Credential))]
        self.a.CredReadW.restype=C.c_int32
        self.a.CredFree.argtypes=[C.c_void_p];self.a.CredFree.restype=None
    @contextmanager
    def read(self,target):
        pointer=C.POINTER(_Credential)()
        if not self.a.CredReadW(target,1,0,C.byref(pointer)) or not pointer:_fail('windows_observer_credential_unavailable')
        try:
            value=pointer.contents
            if not value.blob or not 1<=value.blob_size<=4096:_fail('windows_observer_credential_invalid')
            yield {'flags':int(value.flags),'type':int(value.type),'target':value.target,'username':value.username,
                'persist':int(value.persist),'attribute_count':int(value.attribute_count),'alias':value.alias,
                'blob':C.string_at(value.blob,value.blob_size)}
        finally:
            # Scrub only the allocation owned by this successful CredRead call.
            if pointer and pointer.contents.blob and 0<pointer.contents.blob_size<=4096:
                C.memset(pointer.contents.blob,0,pointer.contents.blob_size)
            self.a.CredFree(pointer)

class _Source:
    __slots__=('_reference','_api','_pin','_pid','_closed','_seal')
    def __init__(self,seal,reference,api):
        if not ((type(self) is NativeCredentialSource and seal is _NATIVE and type(api) is _Win32Credentials)
                or (type(self) is LaboratoryCredentialSource and seal is _LAB)):_fail('windows_observer_credential_capability_required')
        if type(reference) is not CredentialReference:_fail('windows_observer_credential_reference_invalid')
        reference.validate();self._reference,self._api,self._pin=reference,api,digest(asdict(reference));self._pid,self._closed,self._seal=os.getpid(),False,seal
        self.check()
    def __repr__(self):return '<'+type(self).__name__+' existing-entry only, redacted>'
    def __reduce_ex__(self,protocol):raise TypeError('Credential sources cannot be serialized.')
    def check(self):
        if (self._closed or self._pid!=os.getpid() or digest(asdict(self._reference))!=self._pin
                or self._api.current_sid()!=self._reference.owner_sid):_fail('windows_observer_credential_identity_changed')
    def binding(self):self.check();return asdict(self._reference)
    @contextmanager
    def acquire(self):
        self.check();credential=None
        try:
            with self._api.read(self._reference.target) as row:
                if (type(row) is not dict or set(row)!={'flags','type','target','username','persist','attribute_count','alias','blob'}
                        or type(row['flags']) is not int or row['flags']!=0 or type(row['type']) is not int or row['type']!=1
                        or row['target']!=self._reference.target or row['username']!=self._reference.client_id
                        or type(row['persist']) is not int or row['persist'] not in (1,2)
                        or type(row['attribute_count']) is not int or row['attribute_count']!=0 or row['alias'] not in (None,'')
                        or type(row['blob']) is not bytes or not 1<=len(row['blob'])<=4096):_fail('windows_observer_credential_invalid')
                try:secret=row['blob'].decode('utf-8')
                except UnicodeError:_fail('windows_observer_credential_invalid')
                credential=ClientSecretHandle(secret);del secret;self.check()
            yield credential
        finally:
            if credential is not None:credential.close()
    def close(self):self._closed=True

class NativeCredentialSource(_Source):__slots__=()
class LaboratoryCredentialSource(_Source):__slots__=()
def bind_native_credential(reference):return NativeCredentialSource(_NATIVE,reference,_Win32Credentials())
def _bind_laboratory_credential(reference,api):return LaboratoryCredentialSource(_LAB,reference,api)
