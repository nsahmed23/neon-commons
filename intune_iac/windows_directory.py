"""Inactive native Windows directory boundary; not a Workbench store adapter.

The public operation only reads metadata and retains handles. It does not create
files, change ACLs, connect SQLite, load a provider, or enable any host profile.
The first admitted contract is a current-token-owned directory on a local fixed
NTFS volume with a protected, owner-only allow DACL and no reparse ancestors.
"""
from __future__ import annotations

from contextlib import contextmanager
import ctypes as C
import os
from pathlib import PureWindowsPath
import re
import sys

from .io import AppError

SCHEMA = 'intune-windows-directory/1'
_DRIVE = re.compile(r'^[A-Za-z]:$')
_RESERVED = re.compile(r'^(CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|COM[0-9¹²³]|LPT[0-9¹²³])(?:\..*)?$', re.I)
_VOLUME = re.compile(r'^\\\\\?\\Volume\{[0-9a-fA-F-]{36}\}\\$')
_SID = re.compile(r'^S-1-(?:[0-9]+-)*[0-9]+$')
_DWORD = C.c_uint32
_WORD = C.c_uint16
_BYTE = C.c_ubyte
_HANDLE = C.c_void_p


class _FileTime(C.Structure):
    _fields_ = [('low', _DWORD), ('high', _DWORD)]


class _FileInformation(C.Structure):
    _fields_ = [('attributes', _DWORD), ('creation', _FileTime), ('access', _FileTime),
                ('write', _FileTime), ('volume_serial', _DWORD), ('size_high', _DWORD),
                ('size_low', _DWORD), ('links', _DWORD), ('index_high', _DWORD), ('index_low', _DWORD)]


class _FileIdInformation(C.Structure):
    _fields_ = [('volume_serial', C.c_uint64), ('file_id', _BYTE * 16)]


class _SidAttributes(C.Structure):
    _fields_ = [('sid', C.c_void_p), ('attributes', _DWORD)]


class _TokenUser(C.Structure):
    _fields_ = [('user', _SidAttributes)]


class _AclSize(C.Structure):
    _fields_ = [('count', _DWORD), ('used', _DWORD), ('free', _DWORD)]


class _AceHeader(C.Structure):
    _fields_ = [('type', _BYTE), ('flags', _BYTE), ('size', _WORD)]


def _fail(code):
    raise AppError(code, 'The native Windows private directory contract could not be established.') from None


def _components(value):
    """Admit a narrow unambiguous DOS drive path; do not normalize user names."""
    if type(value) is not str or not value or len(value) > 240 or '/' in value:
        _fail('windows_directory_path_unsupported')
    if any(ord(char) < 32 or ord(char) == 127 or 0xD800 <= ord(char) <= 0xDFFF for char in value):
        _fail('windows_directory_path_unsupported')
    path = PureWindowsPath(value)
    if not path.is_absolute() or not _DRIVE.fullmatch(path.drive) or value.startswith('\\\\'):
        _fail('windows_directory_path_unsupported')
    # PureWindowsPath removes '.', repeated separators and trailing separators;
    # inspect the original components before constructing any native path.
    tail = value[3:]
    parts = tail.split('\\') if tail else []
    if not value[2:3] == '\\' or not parts:
        _fail('windows_directory_path_unsupported')
    for part in parts:
        if (not part or part in ('.', '..') or part[-1:] in (' ', '.') or
                any(char in part for char in ':*?"<>|') or _RESERVED.fullmatch(part)):
            _fail('windows_directory_path_unsupported')
    return value[:2].upper(), tuple(parts)


def _admit_private(metadata, sid):
    """Pure contract evaluator; modeled metadata is never native evidence."""
    if metadata.get('owner_sid') != sid or metadata.get('dacl_protected') is not True:
        _fail('windows_directory_owner_or_dacl')
    aces = metadata.get('aces')
    if type(aces) is not list or not 1 <= len(aces) <= 32:
        _fail('windows_directory_dacl_unsupported')
    for ace in aces:
        if (type(ace) is not dict or ace.get('type') != 'allow' or ace.get('sid') != sid or
                type(ace.get('mask')) is not int or not 0 < ace['mask'] <= 0xFFFFFFFF or
                ace.get('flags') not in (0, 3)):
            _fail('windows_directory_dacl_unsupported')


class _Win32:
    def __init__(self):
        if sys.platform != 'win32' or os.name != 'nt' or not hasattr(C, 'WinDLL') or C.sizeof(C.c_void_p)!=8:
            _fail('windows_directory_platform_unsupported')
        # Restrict DLL resolution to Windows' system directory. No PATH/cwd DLL.
        self.k = C.WinDLL('kernel32.dll', use_last_error=True, winmode=0x800)
        self.a = C.WinDLL('advapi32.dll', use_last_error=True, winmode=0x800)
        P = C.c_void_p; W = C.c_wchar_p; D = _DWORD; B = C.c_int32; H = _HANDLE
        declarations = [
            (self.k, 'CreateFileW', [W,D,D,P,D,D,H], H),
            (self.k, 'CloseHandle', [H], B),
            (self.k, 'GetCurrentProcess', [], H),
            (self.k, 'GetCurrentThread', [], H),
            (self.k, 'GetDriveTypeW', [W], D),
            (self.k, 'GetVolumeNameForVolumeMountPointW', [W,W,D], B),
            (self.k, 'GetFileInformationByHandle', [H,C.POINTER(_FileInformation)], B),
            (self.k, 'GetFileInformationByHandleEx', [H,C.c_int,P,D], B),
            (self.k, 'GetVolumeInformationByHandleW', [H,W,D,P,P,P,W,D], B),
            (self.k, 'GetFinalPathNameByHandleW', [H,W,D,D], D),
            (self.k, 'LocalFree', [P], P),
            (self.a, 'OpenThreadToken', [H,D,B,C.POINTER(H)], B),
            (self.a, 'OpenProcessToken', [H,D,C.POINTER(H)], B),
            (self.a, 'GetTokenInformation', [H,C.c_int,P,D,C.POINTER(D)], B),
            (self.a, 'IsValidSid', [P], B),
            (self.a, 'GetLengthSid', [P], D),
            (self.a, 'ConvertSidToStringSidW', [P,C.POINTER(P)], B),
            (self.a, 'GetSecurityInfo', [H,D,D,C.POINTER(P),P,C.POINTER(P),P,C.POINTER(P)], D),
            (self.a, 'GetSecurityDescriptorControl', [P,C.POINTER(_WORD),C.POINTER(D)], B),
            (self.a, 'GetAclInformation', [P,P,D,C.c_int], B),
            (self.a, 'GetAce', [P,D,C.POINTER(P)], B),
        ]
        for library, name, arguments, result in declarations:
            function = getattr(library, name)
            function.argtypes = arguments; function.restype = result

    def close(self, handle):
        if not self.k.CloseHandle(handle): _fail('windows_directory_close_failed')

    def _sid(self, pointer, maximum=68):
        if not pointer or not self.a.IsValidSid(pointer): _fail('windows_directory_sid_invalid')
        size = self.a.GetLengthSid(pointer)
        if not 8 <= size <= min(68, maximum): _fail('windows_directory_sid_invalid')
        result = C.c_void_p()
        if not self.a.ConvertSidToStringSidW(pointer, C.byref(result)):
            _fail('windows_directory_sid_invalid')
        try:
            value = C.wstring_at(result)
            if not _SID.fullmatch(value) or len(value)>184: _fail('windows_directory_sid_invalid')
            return value
        finally: self.k.LocalFree(result)

    def current_sid(self):
        token = _HANDLE()
        if not self.a.OpenThreadToken(self.k.GetCurrentThread(), 8, True, C.byref(token)):
            if C.get_last_error() != 1008: _fail('windows_directory_identity_unavailable')
            if not self.a.OpenProcessToken(self.k.GetCurrentProcess(), 8, C.byref(token)):
                _fail('windows_directory_identity_unavailable')
        try:
            required = _DWORD()
            ok = self.a.GetTokenInformation(token, 1, None, 0, C.byref(required))
            if ok or C.get_last_error()!=122 or not C.sizeof(_TokenUser)<=required.value<=4096:
                _fail('windows_directory_identity_unavailable')
            buffer = C.create_string_buffer(required.value)
            if not self.a.GetTokenInformation(token, 1, buffer, len(buffer), C.byref(required)):
                _fail('windows_directory_identity_unavailable')
            return self._sid(C.cast(buffer, C.POINTER(_TokenUser)).contents.user.sid)
        finally: self.close(token)

    def volume(self, drive):
        root = drive + '\\'
        if self.k.GetDriveTypeW(root) != 3: _fail('windows_directory_volume_unsupported')
        result = C.create_unicode_buffer(64)
        if not self.k.GetVolumeNameForVolumeMountPointW(root, result, len(result)) or not _VOLUME.fullmatch(result.value):
            _fail('windows_directory_volume_unsupported')
        return result.value

    def open_directory(self, path):
        # Share READ and WRITE, never DELETE: retain namespace identity through
        # the caller's use. OPEN_REPARSE_POINT inspects the final component;
        # the caller opens and retains every ancestor in order.
        result = self.k.CreateFileW(path, 0x20080, 3, None, 3, 0x02200000, None)
        if result in (None, C.c_void_p(-1).value): _fail('windows_directory_open_failed')
        return result

    def metadata(self, handle, *, private):
        info = _FileInformation(); identity = _FileIdInformation()
        if (not self.k.GetFileInformationByHandle(handle, C.byref(info)) or
                not self.k.GetFileInformationByHandleEx(handle, 18, C.byref(identity), C.sizeof(identity))):
            _fail('windows_directory_identity_unavailable')
        if not info.attributes & 0x10 or info.attributes & 0x400:
            _fail('windows_directory_reparse_or_type')
        filesystem = C.create_unicode_buffer(32)
        if not self.k.GetVolumeInformationByHandleW(handle, None, 0, None, None, None, filesystem, len(filesystem)) or filesystem.value != 'NTFS':
            _fail('windows_directory_volume_unsupported')
        final = C.create_unicode_buffer(1024)
        count = self.k.GetFinalPathNameByHandleW(handle, final, len(final), 1)
        if not count or count >= len(final): _fail('windows_directory_final_path_unavailable')
        value = {'volume_serial': int(identity.volume_serial), 'file_id': bytes(identity.file_id).hex(),
                 'final_path': final.value, 'filesystem': filesystem.value, 'reparse': False}
        if not private: return value
        owner = C.c_void_p(); dacl = C.c_void_p(); descriptor = C.c_void_p()
        code = self.a.GetSecurityInfo(handle, 1, 5, C.byref(owner), None, C.byref(dacl), None, C.byref(descriptor))
        if code or not descriptor: _fail('windows_directory_security_unavailable')
        try:
            if not dacl: _fail('windows_directory_dacl_unsupported')
            control = _WORD(); revision = _DWORD(); size = _AclSize()
            if (not self.a.GetSecurityDescriptorControl(descriptor,C.byref(control),C.byref(revision)) or
                    not self.a.GetAclInformation(dacl,C.byref(size),C.sizeof(size),2) or
                    not 1<=size.count<=32 or not 8<=size.used<=65536):
                _fail('windows_directory_dacl_unsupported')
            aces = []
            for index in range(size.count):
                pointer = C.c_void_p()
                if not self.a.GetAce(dacl,index,C.byref(pointer)) or not pointer:
                    _fail('windows_directory_dacl_unsupported')
                header = C.cast(pointer,C.POINTER(_AceHeader)).contents
                if header.type != 0 or not 16<=header.size<=size.used:
                    _fail('windows_directory_dacl_unsupported')
                mask = C.cast(pointer.value+4,C.POINTER(_DWORD)).contents.value
                aces.append({'type':'allow','flags':int(header.flags),'mask':int(mask),
                             'sid':self._sid(pointer.value+8,header.size-8)})
            value.update(owner_sid=self._sid(owner),dacl_protected=bool(control.value & 0x1000),aces=aces)
            return value
        finally: self.k.LocalFree(descriptor)


class _PinnedDirectory:
    def __init__(self, api, handles, identities, sid):
        self._api=api; self._handles=handles; self._identities=identities; self._sid=sid; self._active=True

    def revalidate(self):
        """Recheck effective identity, every retained handle, and leaf security."""
        if not self._active:_fail('windows_directory_handle_closed')
        if self._api.current_sid()!=self._sid: _fail('windows_directory_identity_changed')
        for index,(handle,previous) in enumerate(zip(self._handles,self._identities)):
            current=self._api.metadata(handle,private=index==len(self._handles)-1)
            if any(current[key]!=previous[key] for key in ('volume_serial','file_id','final_path','filesystem','reparse')):
                _fail('windows_directory_identity_changed')
            if index==len(self._handles)-1:_admit_private(current,self._sid)
        return self.receipt()

    def receipt(self):
        if not self._active:_fail('windows_directory_handle_closed')
        leaf=self._identities[-1]
        return {'schema_version':SCHEMA,'status':'IMPLEMENTED','evidence_class':'native_handle_observation',
                'owner_sid':self._sid,'volume_serial':leaf['volume_serial'],'directory_file_id':leaf['file_id'],
                'ancestor_handles_retained':len(self._handles),'filesystem':'NTFS',
                'scope':'Read-only current-token owner-only protected-DACL directory pin; no storage or execution enabled.',
                'platform_qualified':False,'production_approved':False}


@contextmanager
def _pin(value, api):
    drive,parts=_components(value); sid=api.current_sid(); volume=api.volume(drive)
    handles=[]; identities=[]; primary=None; pinned=None
    try:
        paths=[volume]+[volume+'\\'.join(parts[:end]) for end in range(1,len(parts)+1)]
        for index,path in enumerate(paths):
            handle=api.open_directory(path);handles.append(handle)
            current=api.metadata(handle,private=index==len(paths)-1)
            if (current.get('reparse') is not False or current.get('filesystem')!='NTFS' or
                    type(current.get('volume_serial')) is not int or
                    type(current.get('file_id')) is not str or not re.fullmatch('[a-f0-9]{32}',current['file_id']) or
                    type(current.get('final_path')) is not str):_fail('windows_directory_identity_unavailable')
            if not current['final_path'].lower().startswith(volume.lower()):_fail('windows_directory_volume_changed')
            if identities and current['volume_serial']!=identities[0]['volume_serial']:_fail('windows_directory_volume_changed')
            identities.append(current)
        _admit_private(identities[-1],sid)
        pinned=_PinnedDirectory(api,handles,identities,sid)
        pinned.revalidate()
        yield pinned
        pinned.revalidate()
    except BaseException as error:
        primary=error; raise
    finally:
        if pinned is not None:pinned._active=False
        failures=[]
        for handle in reversed(handles):
            try:api.close(handle)
            except Exception:failures.append('windows_directory_close_failed')
        if failures:
            if primary is not None:
                if hasattr(primary,'add_note'):primary.add_note('Native directory handle cleanup failed; retained-handle outcome is uncertain.')
            else:_fail('windows_directory_close_failed')


@contextmanager
def pin_private_directory(value):
    """Retain validated native handles; unavailable platforms fail before I/O."""
    with _pin(value,_Win32()) as pinned:
        yield pinned
