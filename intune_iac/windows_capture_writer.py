"""Inactive native storage for the unchanged bounded GET capture engine.

No network/identity logic lives here. Every namespace is new and private;
failed and uncertain output is retained. Native barriers are mandatory and
do not imply qualified crash/power-loss or same-account hostile isolation.
"""
from contextlib import contextmanager, ExitStack
import hashlib
from pathlib import PureWindowsPath

from .io import AppError
from . import windows_storage as ws, windows_directory as wd
from .windows_capture import _Directory
from .capture import MAX_PAGE_BYTES, MAX_TOTAL_BYTES


def _fail(code):
    raise AppError(code,'Native capture storage was not established; retain every output artifact.')


class _Files:
    def __init__(self, root, raw, api, directories):
        self.output=root.root;self.root=root;self.raw=raw;self.api=api;self.directories=directories
        self.documents=set();self.pages=[];self.attempted=[];self.total=0;self.finished=False

    def _write(self, access, name, data, limit):
        if type(data) is not bytes or len(data)>limit:_fail('windows_capture_write_limit')
        self.attempted.append(('raw/' if access is self.raw else '')+name)
        receipt=ws._create_file(str(access.root),name,data,self.api)
        retained=access.read(name,limit)
        if retained!=data or receipt['sha256']!=hashlib.sha256(data).hexdigest():
            _fail('windows_capture_write_changed')

    def write_raw(self,name,data):
        if self.finished or len(self.pages)>=10000 or name!=f'page-{len(self.pages):06d}.json' or self.total+len(data)>MAX_TOTAL_BYTES:
            _fail('windows_capture_raw_sequence')
        self._write(self.raw,name,data,MAX_PAGE_BYTES+1)
        self.pages.append(name);self.total+=len(data)

    def write(self,name,data):
        if self.finished or name not in ('export.json','context.json','capture-receipt.json') or name in self.documents:
            _fail('windows_capture_document_sequence')
        self._write(self.root,name,data,16*1024*1024);self.documents.add(name)

    def finish(self):
        if self.finished or self.documents!={'export.json','context.json','capture-receipt.json'}:
            _fail('windows_capture_incomplete')
        if set(self.root.names())!=self.documents|{'raw'} or set(self.raw.names())!=set(self.pages):
            _fail('windows_capture_namespace_changed')
        for access in self.directories:access.revalidate()
        for access in (self.raw,self.root):
            with ws._owned_handle(self.api,self.api.mutable_directory(str(access.native))) as handle:
                observed=self.api.metadata(handle,private=True);wd._admit_private(observed,access.pin._sid)
                if any(observed[key]!=access.pin._identities[-1][key] for key in ('volume_serial','file_id','final_path')):
                    _fail('windows_capture_namespace_changed')
                self.api.flush_namespace(handle)
        self.finished=True


@contextmanager
def _output(destination,api):
    destination=str(destination);wd._components(destination);path=PureWindowsPath(destination)
    phase='before_create';files=None
    try:
        phase='creating_output';ws._create_directory(str(path.parent),path.name,api)
        with ExitStack() as stack:
            directories=[];root=_Directory(path,api,stack,directories)
            phase='creating_raw';ws._create_directory(destination,'raw',api)
            raw=_Directory(path/'raw',api,stack,directories)
            files=_Files(root,raw,api,directories);phase='collecting'
            yield files
            if not files.finished:_fail('windows_capture_incomplete')
            phase='validating_before_cleanup'
            for access in directories:access.revalidate()
        phase='closed'
    except BaseException as error:
        if phase!='before_create':
            names=['raw'] if files is None else ['raw']+files.attempted
            previous=getattr(error,'storage_outcome',None)
            ws._uncertain(error,'native_capture',phase,names)
            error.storage_outcome['output_directory']=destination
            if previous is not None:error.storage_outcome['causal_storage_outcome']=previous
        raise
