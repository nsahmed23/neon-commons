"""Inactive Windows private-file, exclusive-publication and named-lock primitives.

No Workbench profile selects this adapter. Namespace flushing is mandatory; an
unsupported/failed native barrier retains affected files and reports uncertainty.
Observed API completion is not a power-loss or full SQLite qualification.
"""
from __future__ import annotations

from contextlib import contextmanager
import ctypes as C
import hashlib
import re

from .io import AppError
from . import windows_directory as wd

SCHEMA='intune-windows-storage/1'
MAX_BYTES=64*1024*1024
D=C.c_uint32;P=C.c_void_p;B=C.c_int32


class _SecurityAttributes(C.Structure):
    _fields_=[('length',D),('descriptor',P),('inherit',B)]


class _RenameInformation(C.Structure):
    _fields_=[('replace_or_flags',D),('root_directory',P),('name_bytes',D),('name',C.c_uint16*1)]


class _Overlapped(C.Structure):
    _fields_=[('internal',C.c_size_t),('internal_high',C.c_size_t),('offset',D),('offset_high',D),('event',P)]


def _fail(code):
    raise AppError(code,'The native private storage operation did not establish its required contract.') from None


def _leaf(value):
    if type(value) is not str or '\\' in value or '/' in value or len(value)>120:
        _fail('windows_storage_name_invalid')
    wd._components('C:\\'+value)
    return value


def _digest(value):
    if type(value) is not str or not re.fullmatch('[a-f0-9]{64}',value):_fail('windows_storage_digest_invalid')
    return value


def _uncertain(error,operation,phase,names):
    # Preserve the primary error/cancellation. Never retry, remove a stage or
    # overwrite a destination to manufacture a completed publication.
    error.storage_outcome={'schema_version':SCHEMA,'operation':operation,'phase':phase,
        'outcome_uncertain':True,'artifacts_preserved':list(names),'automatic_retry_permitted':False}
    if hasattr(error,'add_note'):error.add_note('Native storage outcome may be partial; preserve artifacts and independently inspect before retry.')


class _Win32Storage(wd._Win32):
    def __init__(self):
        super().__init__()
        declarations=[
            (self.a,'ConvertStringSecurityDescriptorToSecurityDescriptorW',[C.c_wchar_p,D,C.POINTER(P),C.POINTER(D)],B),
            (self.k,'CreateDirectoryW',[C.c_wchar_p,C.POINTER(_SecurityAttributes)],B),
            (self.k,'WriteFile',[P,P,D,C.POINTER(D),P],B),
            (self.k,'ReadFile',[P,P,D,C.POINTER(D),P],B),
            (self.k,'SetFilePointerEx',[P,C.c_int64,C.POINTER(C.c_int64),D],B),
            (self.k,'FlushFileBuffers',[P],B),
            (self.k,'GetFileType',[P],D),
            (self.k,'SetFileInformationByHandle',[P,C.c_int,P,D],B),
            (self.k,'LockFileEx',[P,D,D,D,D,C.POINTER(_Overlapped)],B),
            (self.k,'UnlockFileEx',[P,D,D,D,C.POINTER(_Overlapped)],B),
        ]
        for library,name,arguments,result in declarations:
            function=getattr(library,name);function.argtypes=arguments;function.restype=result

    @contextmanager
    def security(self,sid,*,directory):
        if type(sid) is not str or not wd._SID.fullmatch(sid):_fail('windows_storage_sid_invalid')
        flags='OICI' if directory else ''
        text='O:'+sid+'D:P(A;'+flags+';FA;;;'+sid+')'
        descriptor=P();size=D()
        if not self.a.ConvertStringSecurityDescriptorToSecurityDescriptorW(text,1,C.byref(descriptor),C.byref(size)) or not descriptor:
            _fail('windows_storage_security_descriptor_failed')
        try:yield _SecurityAttributes(C.sizeof(_SecurityAttributes),descriptor,False)
        finally:self.k.LocalFree(descriptor)

    def mutable_directory(self,path):
        # GENERIC_WRITE is necessary for FlushFileBuffers. The existing read
        # pin still protects ancestors and denies deletion of this directory.
        handle=self.k.CreateFileW(path,0x400200A0,3,None,3,0x02200000,None)
        if handle in (None,C.c_void_p(-1).value):_fail('windows_storage_directory_open_failed')
        return handle

    def create_directory(self,path,sid):
        with self.security(sid,directory=True) as security:
            if not self.k.CreateDirectoryW(path,C.byref(security)):
                if C.get_last_error() in (80,183):_fail('windows_storage_destination_exists')
                _fail('windows_storage_directory_create_failed')

    def open_file(self,path,sid,*,create=False,lock=False):
        access=0xC0020000 | (0 if lock else 0x10000)
        share=3 if lock else 1
        with self.security(sid,directory=False) as security:
            handle=self.k.CreateFileW(path,access,share,C.byref(security) if create else None,
                1 if create else 3,0x80200000,None)
            last_error=C.get_last_error()
        if handle in (None,C.c_void_p(-1).value):
            if last_error in (80,183):_fail('windows_storage_destination_exists')
            _fail('windows_storage_file_open_failed')
        return handle

    def _security_metadata(self,handle):
        owner=P();dacl=P();descriptor=P()
        code=self.a.GetSecurityInfo(handle,1,5,C.byref(owner),None,C.byref(dacl),None,C.byref(descriptor))
        if code or not descriptor:_fail('windows_storage_security_unavailable')
        try:
            if not dacl:_fail('windows_storage_file_not_private')
            control=wd._WORD();revision=D();size=wd._AclSize()
            if (not self.a.GetSecurityDescriptorControl(descriptor,C.byref(control),C.byref(revision)) or
                    not self.a.GetAclInformation(dacl,C.byref(size),C.sizeof(size),2) or
                    not 1<=size.count<=32 or not 8<=size.used<=65536):_fail('windows_storage_file_not_private')
            aces=[]
            for index in range(size.count):
                pointer=P()
                if not self.a.GetAce(dacl,index,C.byref(pointer)) or not pointer:_fail('windows_storage_file_not_private')
                header=C.cast(pointer,C.POINTER(wd._AceHeader)).contents
                if header.type!=0 or not 16<=header.size<=size.used:_fail('windows_storage_file_not_private')
                aces.append({'type':'allow','flags':int(header.flags),'mask':int(C.cast(pointer.value+4,C.POINTER(D)).contents.value),
                    'sid':self._sid(pointer.value+8,header.size-8)})
            return {'owner_sid':self._sid(owner),'dacl_protected':bool(control.value&0x1000),'aces':aces}
        finally:self.k.LocalFree(descriptor)

    def file_metadata(self,handle,sid):
        info=wd._FileInformation();identity=wd._FileIdInformation()
        if (self.k.GetFileType(handle)!=1 or not self.k.GetFileInformationByHandle(handle,C.byref(info)) or
                not self.k.GetFileInformationByHandleEx(handle,18,C.byref(identity),C.sizeof(identity))):
            _fail('windows_storage_file_identity_unavailable')
        if info.attributes&(0x10|0x400) or info.links!=1:_fail('windows_storage_file_type_or_links')
        security=self._security_metadata(handle);wd._admit_private(security,sid)
        size=(int(info.size_high)<<32)|info.size_low
        if size>MAX_BYTES:_fail('windows_storage_file_limit')
        return {'volume_serial':int(identity.volume_serial),'file_id':bytes(identity.file_id).hex(),'bytes':size,
                'links':int(info.links),'owner_sid':security['owner_sid']}

    def write(self,handle,data):
        offset=0
        while offset<len(data):
            chunk=data[offset:offset+65536];buffer=C.create_string_buffer(chunk);written=D()
            if not self.k.WriteFile(handle,buffer,len(chunk),C.byref(written),None) or not 0<written.value<=len(chunk):
                _fail('windows_storage_write_failed')
            offset+=written.value

    def read(self,handle):
        if not self.k.SetFilePointerEx(handle,0,None,0):_fail('windows_storage_read_failed')
        chunks=[];size=0
        while True:
            buffer=C.create_string_buffer(65536);count=D()
            if not self.k.ReadFile(handle,buffer,len(buffer),C.byref(count),None):_fail('windows_storage_read_failed')
            if count.value>len(buffer):_fail('windows_storage_read_failed')
            if not count.value:break
            size+=count.value
            if size>MAX_BYTES:_fail('windows_storage_file_limit')
            chunks.append(buffer.raw[:count.value])
        return b''.join(chunks)

    def flush_file(self,handle):
        if not self.k.FlushFileBuffers(handle):_fail('windows_storage_file_flush_failed')

    def flush_namespace(self,handle):
        if not self.k.FlushFileBuffers(handle):_fail('windows_storage_namespace_flush_unavailable')

    def rename_new(self,handle,root_handle,name):
        encoded=_leaf(name).encode('utf-16-le');offset=_RenameInformation.name.offset
        buffer=C.create_string_buffer(max(C.sizeof(_RenameInformation),offset+len(encoded)+2))
        info=C.cast(buffer,C.POINTER(_RenameInformation)).contents
        info.replace_or_flags=0;info.root_directory=root_handle;info.name_bytes=len(encoded)
        C.memmove(C.addressof(buffer)+offset,encoded,len(encoded))
        # FileRenameInfo=3, ReplaceIfExists=False, relative to the held root.
        if not self.k.SetFileInformationByHandle(handle,3,buffer,len(buffer)):
            if C.get_last_error() in (80,183):_fail('windows_storage_destination_exists')
            _fail('windows_storage_rename_failed')

    def lock(self,handle):
        overlap=_Overlapped()
        if not self.k.LockFileEx(handle,3,0,1,0,C.byref(overlap)):
            if C.get_last_error()==33:_fail('windows_storage_lock_busy')
            _fail('windows_storage_lock_failed')
        return overlap

    def unlock(self,handle,overlap):
        if not self.k.UnlockFileEx(handle,0,1,0,C.byref(overlap)):_fail('windows_storage_unlock_failed')


@contextmanager
def _owned_handle(api,handle):
    primary=None
    try:yield handle
    except BaseException as error:primary=error;raise
    finally:
        try:api.close(handle)
        except Exception:
            if primary is not None:
                if hasattr(primary,'add_note'):primary.add_note('Native storage handle cleanup failed; preserve the primary failure.')
            else:_fail('windows_storage_close_failed')


@contextmanager
def _root(value,api):
    with wd._pin(value,api) as pin:
        identity=pin._identities[-1];path=identity['final_path'].rstrip('\\')
        with _owned_handle(api,api.mutable_directory(path)) as handle:
            observed=api.metadata(handle,private=True)
            wd._admit_private(observed,pin._sid)
            if any(observed[key]!=identity[key] for key in ('volume_serial','file_id','final_path')):
                _fail('windows_storage_root_changed')
            yield pin,handle,path
            pin.revalidate()


def _bound_file(api,handle,pin):
    value=api.file_metadata(handle,pin._sid)
    if (value.get('owner_sid')!=pin._sid or value.get('links')!=1 or type(value.get('bytes')) is not int or
            not 0<=value['bytes']<=MAX_BYTES or type(value.get('file_id')) is not str or
            not re.fullmatch('[a-f0-9]{32}',value['file_id'])):_fail('windows_storage_file_identity_unavailable')
    if value['volume_serial']!=pin._identities[-1]['volume_serial']:_fail('windows_storage_volume_changed')
    return value


def _receipt(operation,metadata,**fields):
    return {**metadata,'schema_version':SCHEMA,'status':'IMPLEMENTED','operation':operation,**fields,
        'durability':{'file_or_directory_barriers_completed':True,'native_power_loss_qualified':False},
        'platform_qualified':False,'production_approved':False,'workbench_profile_enabled':False}


def _create_directory(root,name,api):
    name=_leaf(name);wd._components(root+'\\'+name);phase='before_create'
    try:
        with _root(root,api) as (pin,handle,path):
            pin.revalidate()
            phase='creating_directory';api.create_directory(path+'\\'+name,pin._sid)
            phase='directory_created_namespace_pending'
            with wd._pin(root+'\\'+name,api) as child:
                with _owned_handle(api,api.mutable_directory(child._identities[-1]['final_path'])) as child_handle:
                    api.flush_namespace(child_handle)
                api.flush_namespace(handle)
                phase='barriers_completed_closing'
                return _receipt('create_directory',child.receipt(),name=name)
    except BaseException as error:
        if phase!='before_create' and (not isinstance(error,AppError) or error.code!='windows_storage_destination_exists'):
            _uncertain(error,'create_directory',phase,[name])
        raise


def create_private_directory(root,name):
    return _create_directory(root,name,_Win32Storage())


def _create_file(root,name,data,api):
    name=_leaf(name);wd._components(root+'\\'+name)
    if type(data) is not bytes or len(data)>MAX_BYTES:_fail('windows_storage_bytes_required')
    phase='before_create'
    try:
        with _root(root,api) as (pin,root_handle,path):
            pin.revalidate()
            phase='creating_file'
            with _owned_handle(api,api.open_file(path+'\\'+name,pin._sid,create=True)) as handle:
                identity=_bound_file(api,handle,pin);phase='writing_file';api.write(handle,data)
                api.flush_file(handle);phase='file_flushed_namespace_pending';api.flush_namespace(root_handle)
                actual=api.read(handle);after=_bound_file(api,handle,pin)
                if actual!=data or after['file_id']!=identity['file_id']:_fail('windows_storage_readback_mismatch')
                pin.revalidate()
                phase='readback_verified_closing'
                return _receipt('create_new_file',after,name=name,sha256=hashlib.sha256(actual).hexdigest())
    except BaseException as error:
        if phase!='before_create' and (not isinstance(error,AppError) or error.code!='windows_storage_destination_exists'):
            _uncertain(error,'create_new_file',phase,[name])
        raise


def create_new_file(root,name,data):
    return _create_file(root,name,data,_Win32Storage())


def _publish(root,stage,destination,expected_sha256,api):
    stage=_leaf(stage);destination=_leaf(destination);_digest(expected_sha256)
    if stage==destination:_fail('windows_storage_publication_same_name')
    wd._components(root+'\\'+stage);wd._components(root+'\\'+destination)
    phase='before_rename'
    try:
        with _root(root,api) as (pin,root_handle,path):
            with _owned_handle(api,api.open_file(path+'\\'+stage,pin._sid)) as handle:
                before=_bound_file(api,handle,pin);data=api.read(handle)
                if hashlib.sha256(data).hexdigest()!=expected_sha256:_fail('windows_storage_digest_mismatch')
                api.flush_file(handle);pin.revalidate()
                phase='rename_dispatched';api.rename_new(handle,root_handle,destination)
                phase='renamed_namespace_pending';api.flush_file(handle);api.flush_namespace(root_handle)
                after=_bound_file(api,handle,pin)
                if after!=before or hashlib.sha256(api.read(handle)).hexdigest()!=expected_sha256:
                    _fail('windows_storage_publication_readback_mismatch')
                pin.revalidate()
                phase='publication_verified_closing'
                return _receipt('publish_new',after,source_name=stage,name=destination,sha256=expected_sha256)
    except BaseException as error:
        if phase!='before_rename' and (not isinstance(error,AppError) or error.code!='windows_storage_destination_exists'):
            _uncertain(error,'publish_new',phase,[stage,destination])
        raise


def publish_new(root,stage,destination,expected_sha256):
    return _publish(root,stage,destination,expected_sha256,_Win32Storage())


@contextmanager
def _lock(root,name,api):
    name=_leaf(name);wd._components(root+'\\'+name)
    with _root(root,api) as (pin,root_handle,path):
        created=False
        try:handle=api.open_file(path+'\\'+name,pin._sid,create=True,lock=True);created=True
        except AppError as error:
            if error.code!='windows_storage_destination_exists':raise
            handle=api.open_file(path+'\\'+name,pin._sid,lock=True)
        with _owned_handle(api,handle):
            identity=_bound_file(api,handle,pin)
            if created:
                try:api.flush_file(handle);api.flush_namespace(root_handle)
                except BaseException as error:_uncertain(error,'named_lock','lock_file_created',[name]);raise
            overlap=api.lock(handle);primary=None
            try:
                pin.revalidate()
                yield {'schema_version':SCHEMA,'operation':'cooperative_named_lock','file_id':identity['file_id'],
                    'exclusive':True,'native_qualified':False,'scope':'Nonblocking byte zero lock; not SQLite transaction locking or hostile-process containment.'}
                if _bound_file(api,handle,pin)!=identity:_fail('windows_storage_lock_identity_changed')
            except BaseException as error:primary=error;raise
            finally:
                try:api.unlock(handle,overlap)
                except Exception:
                    if primary is not None:
                        if hasattr(primary,'add_note'):primary.add_note('Native named-lock release failed; cleanup outcome is uncertain.')
                    else:_fail('windows_storage_unlock_failed')


@contextmanager
def exclusive_lock(root,name):
    with _lock(root,name,_Win32Storage()) as receipt:yield receipt
