"""Inactive native guarded source access for the unchanged literal Atmos resolver.

No Git/process/network execution, repository mutation or revision authentication.
Every selected source byte and visited namespace remains guarded until the
resolver and readback finish. Native platform qualification remains required.
"""
from contextlib import contextmanager,ExitStack
import ctypes as C
import re
import time
from pathlib import PureWindowsPath,PurePosixPath

from .io import AppError,digest
from . import repository as core,windows_directory as wd,windows_storage as ws
from . import windows_capture as wc


def _fail(code):raise AppError(code,'Native repository source identity, type, privacy, namespace or byte consistency was not established.')


class _NativeAPI(wc._NativeAPI):
    def repository_entry_type(self,handle,sid):
        info=wd._FileInformation()
        if self.k.GetFileType(handle)!=1 or not self.k.GetFileInformationByHandle(handle,C.byref(info)):
            _fail('windows_repository_entry_type_unavailable')
        if info.attributes&0x400:_fail('windows_repository_reparse_unsupported')
        if info.attributes&0x10:
            identity=self.metadata(handle,private=True);wd._admit_private(identity,sid)
            return 'directory',identity
        return 'file',self.file_metadata(handle,sid)


class _Access:
    def __init__(self,root,api,stack):
        wd._components(str(root));self.root=PureWindowsPath(root);self.api=api;self.stack=stack
        self.directories=[];self.accesses={};self.kinds={};self.entries=0;self.classifications=[]
        self.accesses[self.root]=wc._Directory(self.root,api,stack,self.directories)
        self.root_identity=self.accesses[self.root].pin.receipt()
        from .windows_source_edit import _check_pending
        self.source_edit_history=_check_pending(self)
    @staticmethod
    def path(value):return PureWindowsPath(value)
    def contained(self,path):
        path=PureWindowsPath(path)
        if not path.is_relative_to(self.root):_fail('windows_repository_path_escape')
        for part in path.relative_to(self.root).parts:ws._leaf(part)
        return path
    def _names(self,access):
        names=access.names()
        if len({name.casefold() for name in names})!=len(names):_fail('windows_repository_case_ambiguity')
        return names
    def _directory(self,path):
        path=self.contained(path)
        if path in self.accesses:return self.accesses[path]
        if self._kind(path)!='directory':_fail('windows_repository_directory_required')
        value=wc._Directory(path,self.api,self.stack,self.directories)
        self.accesses[path]=value
        return value
    def _kind(self,path):
        path=self.contained(path)
        if path==self.root:return 'directory'
        if path in self.kinds:return self.kinds[path]
        parent=self._directory(path.parent);names=self._names(parent)
        if path.name not in names:
            if path.name.casefold() in {name.casefold() for name in names}:_fail('windows_repository_case_ambiguity')
            self.kinds[path]=None;return None
        classify=getattr(self.api,'repository_entry_type',None)
        if not callable(classify):_fail('windows_repository_entry_type_unavailable')
        handle=self.stack.enter_context(ws._owned_handle(self.api,self.api.open_directory(str(parent.native/path.name))))
        kind,identity=classify(handle,parent.pin._sid)
        if kind not in ('file','directory') or identity['volume_serial']!=parent.pin._identities[-1]['volume_serial']:
            _fail('windows_repository_entry_type_unavailable')
        self.classifications.append((handle,kind,identity,parent.pin._sid));self.kinds[path]=kind
        return kind
    def exists(self,path):return self._kind(path) is not None
    def is_dir(self,path):return self._kind(path)=='directory'
    def read(self,path,limit):
        path=self.contained(path)
        if self._kind(path)!='file':_fail('windows_repository_regular_source_required')
        return self._directory(path.parent).read(path.name,limit)
    def scan(self,base,source_kind):
        base=self.contained(base)
        if not self.exists(base):return
        if not self.is_dir(base):raise core._Blocked('invalid_source_directory',base.relative_to(self.root).as_posix())
        pending=[(base,0)]
        while pending:
            directory,depth=pending.pop()
            if depth>core.MAX_DEPTH:raise core._Blocked('repository_limit')
            access=self._directory(directory);names=sorted(self._names(access))
            for name in names:
                self.entries+=1
                if self.entries>core.MAX_ENTRIES:raise core._Blocked('repository_limit')
                if name in core._SKIP_DIRS:continue
                path=directory/name;kind=self._kind(path)
                if kind=='directory':pending.append((path,depth+1))
                elif kind=='file' and ((source_kind=='stack' and name.endswith(('.yaml','.yml','.yaml.tmpl','.yml.tmpl'))) or
                        (source_kind=='component' and (name.endswith(('.tf','.tf.json')) or name=='.terraform.lock.hcl'))):yield path
    def revalidate(self):
        for handle,kind,identity,sid in self.classifications:
            current_kind,current=self.api.repository_entry_type(handle,sid)
            if current_kind!=kind or current!=identity:_fail('windows_repository_entry_changed')
        for access in self.directories:access.revalidate()


@contextmanager
def _access(root,api):
    with ExitStack() as stack:
        value=_Access(root,api,stack)
        yield value
        value.revalidate()


def _report(access,stack,component):
    report=core._Repository(access.root,_access=access).resolve(stack,component)
    report['native_source_access']={'root_identity':access.root_identity,'raw_source_order_preserved':True,
        'held_source_and_namespace_revalidation':True,'git_revision_verified':False,
        'local_source_edit_history':access.source_edit_history,
        'platform_qualified':False,'workbench_profile_enabled':False}
    return report


def _resolve(root,stack,component,api):
    started=time.time()
    with _access(root,api) as access:
        report=_report(access,stack,component)
    report['native_source_access'].update(read_started_at=started,read_completed_at=time.time(),
        temporal_scope='Consistent held source read; freshness after handle release is not established.')
    return report


def resolve_windows_component(root,stack,component):
    return _resolve(root,stack,component,_NativeAPI())


def _sources(value):
    if type(value) is not list or not 1<=len(value)<=core.MAX_FILES:_fail('windows_repository_record_sources_invalid')
    result={};folded=set()
    for item in value:
        if type(item) is not dict or set(item)!={'path','sha256'}:_fail('windows_repository_record_sources_invalid')
        name,sha=item['path'],item['sha256']
        if (type(name) is not str or not name or len(name)>4096 or type(sha) is not str or
                not re.fullmatch('[0-9a-f]{64}',sha) or '\\' in name):_fail('windows_repository_record_sources_invalid')
        path=PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or path.as_posix()!=name:_fail('windows_repository_record_sources_invalid')
        for part in path.parts:ws._leaf(part)
        if name.casefold() in folded:_fail('windows_repository_record_sources_invalid')
        folded.add(name.casefold());result[name]=sha
    return result


def _readback(record,api):
    """Compare native current bytes/inputs with the exact stored scope assertion."""
    from .workbench_views import _scope,_pointer
    from .workbench_semantics import analyze,compare
    if type(record) is not dict or record.get('schema_version')!='workbench-repository-intent/1':_fail('windows_repository_record_invalid')
    scope=_scope(record.get('scope'));root=scope['repository'];wd._components(root)
    pointer=record.get('effective_pointer')
    if type(pointer) is not str:_fail('windows_repository_pointer_missing')
    resolution=record.get('resolution')
    if type(resolution) is not dict:_fail('windows_repository_record_sources_invalid')
    wanted=_sources(resolution.get('sources'))
    if analyze(record.get('desired'))['status']!='supported':_fail('windows_repository_record_policy_unsupported')
    started=time.time()
    with _access(root,api) as access:
        report=_report(access,scope['stack'],scope['component'])
        prior=record.get('native_source_snapshot')
        if prior is not None and (type(prior) is not dict or prior.get('captured_root_identity')!=access.root_identity):
            _fail('windows_repository_recorded_root_identity_changed')
        if report['status']!='resolved':
            result={'status':'unknown','reason':'native_literal_resolution_blocked','blockers':report['blockers'],
                'root_identity':access.root_identity,'git_revision_verified':False}
        else:
            current={item['path']:item['sha256'] for item in report['sources']}
            desired=_pointer(report['effective'],pointer)
            # Never expose arbitrary env/vars through a forged pointer. Only the
            # same supported typed policy projection can leave this boundary.
            if analyze(desired)['status']!='supported':_fail('windows_repository_current_policy_unsupported')
            comparison=compare(record['desired'],desired)
            result={'status':'recorded','scope':scope,'root_identity':access.root_identity,
                'recorded_source_revision':record.get('source_revision'),'recorded_revision_assurance':record.get('revision_assurance'),
                'git_revision_verified':False,'publisher_authenticated':False,
                'prior_native_root_identity_available':prior is not None,
                'recorded_native_root_identity_matches':True if prior is not None else None,
                'historical_root_binding_authenticated':False,
                'association':('Exact recorded local native root identity matches current held observation; publisher unverified.' if prior is not None else 'Exact recorded DOS scope path and selected stack/component; prior filesystem identity was not recorded.'),
                'source_hashes_equal':wanted==current,'source_files':report['sources'],
                'source_file_changes':{'missing':sorted(set(wanted)-set(current)),'added':sorted(set(current)-set(wanted)),
                    'changed':sorted(name for name in set(wanted)&set(current) if wanted[name]!=current[name])},
                'recorded_effective_input_sha256':resolution.get('configuration_sha256'),
                'current_effective_input_sha256':digest(report['effective']),
                'policy_comparison':{key:comparison[key] for key in ('status','changed_fields','raw_changed','semantics_version')},
                'current_policy':desired,'current_resolution':core.public_resolution(report),
                'execution_authorized':False,'cloud_authority':False,'platform_qualified':False,'workbench_profile_enabled':False}
    result.update(read_started_at=started,read_completed_at=time.time(),
        temporal_scope='Consistent held source read; freshness after handle release is not established.')
    return result


def readback_windows_repository(record):return _readback(record,_NativeAPI())
