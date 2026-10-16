"""Inactive exact local source CAS and explicit non-atomic recovery.

No overwrite primitive, automatic retry, plan approval or tenant execution.
An interrupted two-rename operation remains inspectable until explicit recovery.
"""
from contextlib import ExitStack
import copy
import ctypes as C
import hashlib
from pathlib import PureWindowsPath
import re
import time
import uuid
from .io import AppError,canonical,digest,parse_json
from . import windows_directory as wd,windows_storage as ws,windows_repository as source
from . import windows_capture as capture
from .windows_workbench import WindowsWorkbenchStore

PREFIX='.intune-source-edit-'
LOCK='.intune-source-edit.lock'
INTENT_SUFFIX='.intent.json'
CLOSED_SUFFIX='.closed.json'


def _fail(code):raise AppError(code,'The native local source edit/recovery does not establish the exact reviewed bytes, identity, journal or permitted transition.')
def _sha(raw):return hashlib.sha256(raw).hexdigest()


class _BasicInformation(C.Structure):
    _fields_=[('creation',C.c_int64),('access',C.c_int64),('write',C.c_int64),('change',C.c_int64),('attributes',C.c_uint32)]


class _NativeAPI(source._NativeAPI):
    def __init__(self):
        super().__init__();P=C.c_void_p;D=C.c_uint32;B=C.c_int
        for lib,name,args,result in ((self.a,'GetSecurityDescriptorDacl',[P,C.POINTER(B),C.POINTER(P),C.POINTER(B)],B),
                (self.a,'SetSecurityInfo',[P,C.c_int,D,P,P,P,P],D)):
            function=getattr(lib,name);function.argtypes=args;function.restype=result
    def edit_metadata(self,handle,sid):
        info=wd._FileInformation()
        if not self.k.GetFileInformationByHandle(handle,C.byref(info)):_fail('windows_source_edit_metadata_unavailable')
        attributes=int(info.attributes)
        # Preserve exact supported flags. Readonly/compressed/encrypted/offline
        # and unknown flags require their own native contract, never flattening.
        if not attributes or attributes&~0xA6 or attributes&0x80 and attributes!=0x80:_fail('windows_source_edit_attributes_unsupported')
        security=self._security_metadata(handle);wd._admit_private(security,sid)
        return {'attributes':attributes,'security':security}
    def open_candidate(self,path,sid):
        # WRITE_DAC applies only to our newly created private candidate so its
        # exact original owner-only DACL can be preserved before publication.
        handle=self.k.CreateFileW(path,0xC0070000,1,None,3,0x80200000,None)
        if handle in (None,C.c_void_p(-1).value):_fail('windows_source_candidate_open_failed')
        return handle
    def clone_metadata(self,handle,metadata,sid):
        security=metadata['security'];wd._admit_private(security,sid)
        pieces=[]
        for ace in security['aces']:
            flags={0:'',1:'OI',2:'CI',3:'OICI'}.get(ace['flags'])
            if flags is None:_fail('windows_source_edit_security_unsupported')
            pieces.append('(A;'+flags+';0x'+format(ace['mask'],'x')+';;;'+sid+')')
        text='O:'+sid+'D:P'+''.join(pieces);descriptor=C.c_void_p();size=C.c_uint32()
        if not self.a.ConvertStringSecurityDescriptorToSecurityDescriptorW(text,1,C.byref(descriptor),C.byref(size)) or not descriptor:_fail('windows_source_edit_security_copy_failed')
        try:
            present=C.c_int();defaulted=C.c_int();dacl=C.c_void_p()
            if not self.a.GetSecurityDescriptorDacl(descriptor,C.byref(present),C.byref(dacl),C.byref(defaulted)) or not present.value or not dacl:_fail('windows_source_edit_security_copy_failed')
            if self.a.SetSecurityInfo(handle,1,0x80000004,None,None,dacl,None):_fail('windows_source_edit_security_copy_failed')
        finally:self.k.LocalFree(descriptor)
        info=_BasicInformation();info.attributes=metadata['attributes']
        if not self.k.SetFileInformationByHandle(handle,0,C.byref(info),C.sizeof(info)):_fail('windows_source_edit_attributes_copy_failed')
        if self.edit_metadata(handle,sid)!=metadata:_fail('windows_source_edit_metadata_changed')


def _root_identity(access,expected):
    if access.root_identity!=expected:_fail('windows_source_edit_root_changed')


def _proposal(path,expected,api):
    ws._digest(expected);wd._components(path)
    with capture._directory(path,api) as files:
        if set(files.names())!={'proposal.json','source.before.yaml','source.after.yaml','change.patch'}:_fail('windows_source_edit_proposal_members')
        body=parse_json(files.read('proposal.json'))
        if type(body) is not dict or body.get('schema_version')!='workbench-source-acceptance-proposal/1':_fail('windows_source_edit_proposal_schema')
        if body.get('proposal_sha256')!=expected or digest({key:value for key,value in body.items() if key!='proposal_sha256'})!=expected:_fail('windows_source_edit_proposal_digest')
        for key,wanted in (('source_modified',False),('execution_authorized',False),('cloud_authority',False),('fresh_plan_required',True),('normal_change_review_required',True),('no_resource_changes_established',False)):
            if body.get(key) is not wanted:_fail('windows_source_edit_proposal_authority')
        payload={name:files.read(name) for name in ('source.before.yaml','source.after.yaml','change.patch')}
        if set(body.get('proposal_files',{}))!=set(payload):_fail('windows_source_edit_proposal_files')
        for name,raw in payload.items():
            if body['proposal_files'][name]!={'bytes':len(raw),'sha256':_sha(raw)}:_fail('windows_source_edit_proposal_bytes')
        from .workbench_views import _identity,_scope
        _identity(body.get('tenant_id'));_identity(body.get('object_id'))
        authoritative=body.get('authoritative_source');binding=body.get('native_source_binding')
        if type(authoritative) is not dict or type(binding) is not dict:_fail('windows_source_edit_binding')
        if authoritative.get('before_sha256')!=_sha(payload['source.before.yaml']) or authoritative.get('after_sha256')!=_sha(payload['source.after.yaml']):_fail('windows_source_edit_binding')
        root=binding.get('root');wd._components(root)
        if _scope(binding.get('scope'))['repository']!=root:_fail('windows_source_edit_scope_mismatch')
        relative=authoritative.get('path')
        if type(relative) is not str or not relative or '\\' in relative or relative.startswith('/') or any(part in ('','.','..') for part in relative.split('/')):_fail('windows_source_edit_relative_path')
        for part in relative.split('/'):ws._leaf(part)
        return body,payload


class _Window:
    """The acknowledged expiry, judged on the wall clock and on this call's own monotonic deadline.

    The deadline is built from the one wall and monotonic snapshot taken as part of accepting the acknowledgment (see
    _accept) and never moved, and the wall clock is not read again to compute it, so a wall clock that stands still or
    steps back while real time passes cannot carry the edit across the expiry the operator acknowledged. The acknowledgment is
    a local statement with a caller-supplied expiry, not an authenticated artefact: a new acknowledgment is a new
    operation, so there is no durable record to latch beyond the append-only source journal that refuses a replay."""
    def __init__(self,expires_at,now):self.expires_at=expires_at;self.deadline=now[1]+max(0,expires_at-now[0])
    def closed(self):return time.time()>=self.expires_at or time.monotonic()>=self.deadline


def _accept(store,proposal,expected,expires_at,acknowledged,api):
    """Accept the acknowledgment and build its window from one wall and monotonic snapshot taken first."""
    now=(time.time(),time.monotonic())
    return _acknowledge(store,proposal,expected,expires_at,acknowledged,api,now),_Window(expires_at,now)


def _acknowledge(store,proposal,expected,expires_at,acknowledged,api,now=None):
    wall=time.time() if now is None else now[0]
    if type(store) is not WindowsWorkbenchStore or proposal.get('tenant_id')!=store.tenant_id:_fail('windows_source_edit_wrong_store')
    if acknowledged is not True:_fail('windows_source_edit_ack_required')
    if type(expires_at) not in (int,float) or not wall<expires_at<=wall+3600:_fail('windows_source_edit_ack_expired')
    sid=api.current_sid();binding=proposal['native_source_binding']
    if binding['root_identity'].get('owner_sid')!=sid:_fail('windows_source_edit_actor_mismatch')
    identifier=digest({'proposal_sha256':expected,'tenant_id':store.tenant_id,'object_id':proposal['object_id'],'actor_sid':sid,'operation':'local_source_edit','expires_at':expires_at})
    return {'schema_version':'workbench-local-source-ack/1','operation_id':identifier,'operation':'local_source_edit',
        'proposal_sha256':expected,'tenant_id':store.tenant_id,'object_id':proposal['object_id'],'actor_sid':sid,
        'expires_at':expires_at,'acknowledged_at':wall,'root_identity':binding['root_identity'],
        'source_file_identity':binding['source_file_identity'],'authoritative_source':proposal['authoritative_source'],
        'protected_plan_approval':False,'organizational_approval':False,'cloud_authority':False}


def _load_json(directory,name):return parse_json(directory.read(name,64*1024))


def _find_closure(directory,identifier,intent):
    """Inspect all append-only attempts; malformed bytes stay visible evidence."""
    prefix=PREFIX+identifier;names=[name for name in directory.names() if name.startswith(prefix) and name.endswith(CLOSED_SUFFIX)]
    if len(names)>32:_fail('windows_source_edit_journal_bound')
    valid=[];invalid=[];retained_bytes=0
    for name in sorted(names):
        suffix=name[len(prefix):]
        if suffix!=CLOSED_SUFFIX and not re.fullmatch(r'\.[a-f0-9]{16}\.closed\.json',suffix):_fail('windows_source_edit_journal_name')
        # Namespace, ACL, type and read failures are never discarded as a bad
        # JSON attempt. Only a completed guarded read reaches the parser.
        raw=directory.read(name,64*1024);retained_bytes+=len(raw)
        identity={'name':name,'sha256':_sha(raw),'bytes':len(raw)}
        try:
            value=parse_json(raw)
            if (type(value) is not dict or value.get('schema_version')!='workbench-local-source-edit-closure/1' or
                    value.get('intent_sha256')!=digest(intent) or value.get('operation_id')!=identifier or
                    value.get('state') not in ('source_applied','source_restored','source_before_observed')):_fail('windows_source_edit_closure_invalid')
        except AppError as error:
            invalid.append(dict(identity,error_code=error.code));continue
        valid.append(dict(identity,receipt=value))
    states={item['receipt']['state'] for item in valid}
    if len(states)>1:_fail('windows_source_edit_closure_conflict')
    return {'status':'recorded' if valid else 'incomplete' if invalid else 'missing','records':valid,
        'invalid_records':invalid,'state':next(iter(states)) if states else None,'retained_bytes':retained_bytes,
        'historical_provenance_authenticated':False}


def _check_pending(access):
    """Current readers reject unresolved cooperative source transitions."""
    directory=access.accesses[access.root];names=directory.names()
    pending=[name for name in names if name.startswith(PREFIX) and name.endswith(INTENT_SUFFIX)];history=[]
    if len(pending)>256:_fail('windows_source_edit_journal_bound')
    retained_bytes=0
    for name in pending:
        identifier=name[len(PREFIX):-len(INTENT_SUFFIX)]
        if not re.fullmatch('[a-f0-9]{64}',identifier):_fail('windows_source_edit_journal_name')
        intent=_load_json(directory,name)
        if type(intent) is not dict or intent.get('operation_id')!=identifier or intent.get('schema_version')!='workbench-local-source-edit-intent/1':_fail('windows_repository_source_edit_unresolved')
        closure=_find_closure(directory,identifier,intent)
        retained_bytes+=len(canonical(intent))+closure['retained_bytes']
        if retained_bytes>4*1024*1024:_fail('windows_source_edit_journal_bound')
        if closure['status']!='recorded':
            error=AppError('windows_repository_source_edit_unresolved','A local source edit has no verified closure; inspect its retained journal before further source operations.')
            error.source_edit_pending={'operation_id':identifier,'source_root':str(access.root),'outcome_uncertain':True,
                'next_action':{'command':'source-edit-status','arguments':[str(access.root),identifier]},
                'invalid_closure_records':closure['invalid_records'],'automatic_retry_permitted':False}
            raise error
        history.append({'operation_id':identifier,'state':closure['state'],
            'recovery':any(item['receipt'].get('recovery') is True for item in closure['records']),
            'invalid_closure_records':closure['invalid_records'],'closure_records':closure['records'],
            'historical_provenance_authenticated':False,'non_atomic_transition':True})
    return history


def _read_optional(root,name,api):
    with capture._directory(root,api) as directory:
        if name not in directory.names():return None
        return directory.read(name)


def _existing_state(root,parent,original,stage,backup,api):
    result={}
    with capture._directory(parent,api) as directory:
        names=set(directory.names())
        for label,name in (('original',original),('stage',stage),('backup',backup)):
            if name in names:
                raw=directory.read(name);result[label]={'sha256':_sha(raw),'identity':copy.deepcopy(directory.files[name]['identity']),
                    'metadata':api.edit_metadata(directory.files[name]['handle'],directory.pin._sid)}
            else:result[label]=None
    return result


def _publish_journal(root,identifier,kind,value,api):
    # A partial write never becomes the canonical intent/ready gate. Both
    # temporary bytes and possibly-published exact bytes survive failed acks.
    raw=canonical(value)+b'\n'
    temporary=PREFIX+identifier+'.'+uuid.uuid4().hex[:16]+'.'+kind+'-write'
    final=PREFIX+identifier+'.'+kind+'.json'
    ws._create_file(root,temporary,raw,api)
    ws._publish(root,temporary,final,_sha(raw),api)


def _record_closure(root,intent,state,evidence,api,*,recovery=False,recovery_context=None):
    result={'schema_version':'workbench-local-source-edit-closure/1','operation_id':intent['operation_id'],
        'intent_sha256':digest(intent),'state':state,'observed_files':evidence,'recorded_at':time.time(),
        'recovery':recovery,'non_atomic_transition':True,'original_dispatch_uncertainty_preserved':recovery,
        'fresh_plan_required':True,'protected_execution_performed':False,'platform_qualified':False,
        'closure_publication_acknowledgement':'Not self-authenticated by this stored document; inspect retained call/failure receipts.',
        'native_power_loss_qualified':False}
    if recovery_context is not None:result['recovery_context']=recovery_context
    ws._create_file(root,PREFIX+intent['operation_id']+'.'+uuid.uuid4().hex[:16]+CLOSED_SUFFIX,canonical(result)+b'\n',api)
    return result


def _fault(error,root,intent,phase):
    error.source_edit_outcome={'operation_id':intent.get('operation_id'),'root':root,'phase':phase,
        'outcome_uncertain':True,'automatic_retry_permitted':False,'intent_retained':True,
        'recovery_required':True,'original_source_may_have_moved':phase not in ('intent_pending','intent_recorded','candidate_preparing')}


def _apply(store,path,expected,expires_at,acknowledged,api):
    proposal,payload=_proposal(path,expected,api);ack,window=_accept(store,proposal,expected,expires_at,acknowledged,api)
    binding=proposal['native_source_binding'];root=binding['root'];identifier=ack['operation_id']
    relative=PureWindowsPath(*proposal['authoritative_source']['path'].split('/'));parent=str(PureWindowsPath(root)/relative.parent);original=relative.name
    stage=PREFIX+identifier+'.candidate';backup=PREFIX+identifier+'.backup'
    intent={'schema_version':'workbench-local-source-edit-intent/1','operation_id':identifier,'acknowledgment':ack,
        'proposal_path':path,'proposal_sha256':expected,'root':root,'root_identity':binding['root_identity'],
        'relative_source':proposal['authoritative_source']['path'],'original_name':original,'stage_name':stage,'backup_name':backup,
        'before_sha256':_sha(payload['source.before.yaml']),'after_sha256':_sha(payload['source.after.yaml']),
        'before_identity':binding['source_file_identity'],'non_atomic_transition':True,'protected_execution_performed':False}
    phase='before_intent'
    try:
        with ws._lock(root,LOCK,api):
            if _read_optional(root,PREFIX+identifier+INTENT_SUFFIX,api) is not None:_fail('windows_source_edit_replay_denied')
            fresh=source._resolve(root,binding['scope']['stack'],binding['scope']['component'],api)
            if fresh['status']!='resolved' or fresh['sources']!=binding['all_source_files']:_fail('windows_source_edit_source_changed')
            if fresh['native_source_access']['root_identity']!=binding['root_identity']:_fail('windows_source_edit_root_changed')
            with ws._root(parent,api) as (pin,root_handle,native):
                with ws._owned_handle(api,api.open_file(native+'\\'+original,pin._sid)) as old:
                    before=ws._bound_file(api,old,pin)
                    if before!=binding['source_file_identity'] or api.read(old)!=payload['source.before.yaml']:_fail('windows_source_edit_source_changed')
                    metadata=api.edit_metadata(old,pin._sid);intent['preserved_metadata']=metadata
                    phase='intent_pending';_publish_journal(root,identifier,'intent',intent,api);phase='intent_recorded'
                    # Original remains held with write/delete competitors denied.
                    phase='candidate_preparing';ws._create_file(parent,stage,payload['source.after.yaml'],api)
                    with ws._owned_handle(api,api.open_candidate(native+'\\'+stage,pin._sid)) as candidate:
                        api.clone_metadata(candidate,metadata,pin._sid);api.flush_file(candidate);api.flush_namespace(root_handle)
                        after=ws._bound_file(api,candidate,pin)
                        if api.read(candidate)!=payload['source.after.yaml'] or api.edit_metadata(candidate,pin._sid)!=metadata:_fail('windows_source_edit_candidate_changed')
                        ready={'schema_version':'workbench-local-source-edit-ready/1','operation_id':identifier,
                            'intent_sha256':digest(intent),'before_identity':before,'after_identity':after,
                            'metadata':metadata,'before_sha256':intent['before_sha256'],'after_sha256':intent['after_sha256']}
                        _publish_journal(root,identifier,'ready',ready,api)
                        phase='ready_recorded'
                        # The window bounds when the edit may start: it is judged once, here, before the first rename. A
                        # refusal between the two renames would leave the source file moved away and the repository blocked.
                        if window.closed():_fail('windows_source_edit_ack_expired')
                        pin.revalidate();phase='original_rename_dispatched';api.rename_new(old,root_handle,backup)
                        phase='original_backed_up';api.flush_file(old);api.flush_namespace(root_handle)
                        phase='candidate_rename_dispatched';api.rename_new(candidate,root_handle,original)
                        phase='candidate_published';api.flush_file(candidate);api.flush_namespace(root_handle)
                        if (ws._bound_file(api,old,pin)!=before or api.read(old)!=payload['source.before.yaml'] or
                                ws._bound_file(api,candidate,pin)!=after or api.read(candidate)!=payload['source.after.yaml'] or
                                api.edit_metadata(candidate,pin._sid)!=metadata):_fail('windows_source_edit_readback_changed')
                        pin.revalidate();phase='closing_source_handles'
            evidence=_existing_state(root,parent,original,stage,backup,api)
            if evidence['original']['sha256']!=intent['after_sha256'] or evidence['backup']['sha256']!=intent['before_sha256'] or evidence['stage'] is not None:_fail('windows_source_edit_namespace_changed')
            phase='source_verified_closing_lock'
        # Every mutation guard and lock closed before a closure is published.
        phase='closure_pending';result=_record_closure(root,intent,'source_applied',evidence,api)
        result['publication_acknowledged']=True
        return result
    except BaseException as error:
        if phase!='before_intent':_fault(error,root,intent,phase)
        raise


def apply_source_proposal(store,path,expected,expires_at,*,acknowledged=False):
    return _apply(store,path,expected,expires_at,acknowledged,_NativeAPI())


def _intent(store,root,identifier,api):
    if type(store) is not WindowsWorkbenchStore or type(identifier) is not str or not re.fullmatch('[a-f0-9]{64}',identifier):_fail('windows_source_edit_operation_invalid')
    wd._components(root)
    with capture._directory(root,api) as directory:
        intent=_load_json(directory,PREFIX+identifier+INTENT_SUFFIX)
        if (type(intent) is not dict or intent.get('schema_version')!='workbench-local-source-edit-intent/1' or
                intent.get('root')!=root or intent.get('operation_id')!=identifier or
                intent.get('acknowledgment',{}).get('tenant_id')!=store.tenant_id or
                intent.get('root_identity')!=directory.pin.receipt()):_fail('windows_source_edit_intent_identity')
        names=set(directory.names());ready=PREFIX+identifier+'.ready.json'
        return intent,(_load_json(directory,ready) if ready in names else None),_find_closure(directory,identifier,intent)


def _paths(intent):
    relative=intent.get('relative_source')
    if type(relative) is not str or not relative or '\\' in relative or relative.startswith('/') or any(part in ('','.','..') for part in relative.split('/')):_fail('windows_source_edit_relative_path')
    for part in relative.split('/'):ws._leaf(part)
    path=PureWindowsPath(intent['root']).joinpath(*relative.split('/'))
    if path.name!=intent.get('original_name') or intent.get('stage_name')!=PREFIX+intent['operation_id']+'.candidate' or intent.get('backup_name')!=PREFIX+intent['operation_id']+'.backup':_fail('windows_source_edit_journal_names')
    return str(path.parent),path.name,intent['stage_name'],intent['backup_name']


def _classification(intent,ready,evidence):
    if ready is not None and (type(ready) is not dict or ready.get('schema_version')!='workbench-local-source-edit-ready/1' or
            ready.get('intent_sha256')!=digest(intent) or ready.get('operation_id')!=intent['operation_id'] or
            ready.get('before_identity')!=intent['before_identity'] or ready.get('metadata')!=intent['preserved_metadata'] or
            ready.get('before_sha256')!=intent['before_sha256'] or ready.get('after_sha256')!=intent['after_sha256']):_fail('windows_source_edit_ready_invalid')
    def is_before(value):return value is not None and value['sha256']==intent['before_sha256'] and value['identity']==intent['before_identity'] and value['metadata']==intent['preserved_metadata']
    def is_after(value):return value is not None and ready is not None and value['sha256']==intent['after_sha256'] and value['identity']==ready['after_identity'] and value['metadata']==intent['preserved_metadata']
    original,stage,backup=(evidence[key] for key in ('original','stage','backup'))
    if is_before(original) and backup is None:
        if stage is None:return 'original_before_no_candidate'
        if is_after(stage):return 'original_before_candidate_ready'
        if ready is None:return 'original_before_candidate_unqualified'
    if original is None and is_before(backup) and is_after(stage):return 'original_backed_up_candidate_ready'
    if is_after(original) and is_before(backup) and stage is None:return 'candidate_applied'
    _fail('windows_source_edit_conflicting_files')


def _inspect(store,root,identifier,api):
    with ws._lock(root,LOCK,api):
        intent,ready,closed=_intent(store,root,identifier,api);parent,original,stage,backup=_paths(intent)
        evidence=_existing_state(root,parent,original,stage,backup,api);classification=_classification(intent,ready,evidence)
        recorded=closed['status']=='recorded'
        if recorded and ((closed['state']=='source_applied')!=(classification=='candidate_applied')):_fail('windows_source_edit_closure_state_changed')
        return {'schema_version':'workbench-local-source-edit-status/1','operation_id':identifier,'classification':classification,
            'files':evidence,'closure':closed,'closed':recorded,'outcome_uncertain':not recorded,
            'automatic_retry_permitted':False,'recovery_actions':([] if recorded else ['abort'] if classification in ('original_before_no_candidate','original_before_candidate_unqualified') else ['complete','rollback']),
            'source_root':root,'fresh_plan_required':True,'protected_execution_performed':False,'platform_qualified':False}


def inspect_source_edit(store,root,identifier):return _inspect(store,root,identifier,_NativeAPI())


def _dispatch_recovery(intent,ready,proposal,direction,window,api,mark):
    """Hold the exact root and all present transition files through mutation."""
    root=intent['root'];parent,original,stage,backup=_paths(intent)
    with ExitStack() as guards:
        root_pin,root_handle,_=guards.enter_context(ws._root(root,api))
        if root_pin.receipt()!=intent['root_identity']:_fail('windows_source_edit_root_changed')
        pin,parent_handle,native=guards.enter_context(ws._root(parent,api))
        names=set(api.names(native));handles={};facts={}
        for label,name in (('original',original),('stage',stage),('backup',backup)):
            if name not in names:facts[label]=None;continue
            handle=guards.enter_context(ws._owned_handle(api,api.open_file(native+'\\'+name,pin._sid)));handles[label]=handle
            facts[label]={'sha256':_sha(api.read(handle)),'identity':ws._bound_file(api,handle,pin),
                'metadata':api.edit_metadata(handle,pin._sid)}
        state=_classification(intent,ready,facts)
        if direction=='complete' and state not in ('original_before_candidate_ready','original_backed_up_candidate_ready','candidate_applied'):_fail('windows_source_edit_completion_not_established')
        if direction=='abort' and state=='candidate_applied':_fail('windows_source_edit_abort_would_require_mutation')
        if state=='original_before_candidate_unqualified' and direction!='abort':_fail('windows_source_edit_candidate_unqualified')
        # Completion is bound to unchanged bytes of every recorded input, not
        # just the target. Keep those read handles through mutation. This is
        # not a new Atmos resolution or a proof about unrecorded/new sources.
        dependencies=[]
        if direction=='complete':
            expected=source._sources(proposal['native_source_binding']['all_source_files'])
            directories={}
            for relative,sha in expected.items():
                if relative==intent['relative_source']:continue
                path=PureWindowsPath(root).joinpath(*relative.split('/'));key=str(path.parent)
                if key not in directories:directories[key]=guards.enter_context(capture._directory(key,api))
                directory=directories[key];raw=directory.read(path.name)
                if _sha(raw)!=sha:_fail('windows_source_edit_dependency_changed')
                dependencies.append({'path':relative,'sha256':sha})
        judged=[]
        def rename(label,name,phase):
            # Judged once, before the first rename; a later rename of the same recovery is not refused for the window.
            if not judged:
                if window.closed():_fail('windows_source_edit_ack_expired')
                judged.append(True)
            root_pin.revalidate();pin.revalidate();handle=handles[label];fact=facts[label]
            if ws._bound_file(api,handle,pin)!=fact['identity'] or _sha(api.read(handle))!=fact['sha256'] or api.edit_metadata(handle,pin._sid)!=fact['metadata']:_fail('windows_source_edit_source_changed')
            mark(phase);api.rename_new(handle,parent_handle,name);api.flush_file(handle);api.flush_namespace(parent_handle)
            if ws._bound_file(api,handle,pin)!=fact['identity'] or _sha(api.read(handle))!=fact['sha256'] or api.edit_metadata(handle,pin._sid)!=fact['metadata']:_fail('windows_source_edit_readback_changed')
        if direction=='complete':
            if state=='original_before_candidate_ready':rename('original',backup,'recovery_original_rename_dispatched')
            if state!='candidate_applied':rename('stage',original,'recovery_candidate_rename_dispatched')
            final='source_applied'
        elif direction=='rollback':
            if state=='candidate_applied':rename('original',stage,'recovery_applied_candidate_preservation_dispatched')
            if state in ('original_backed_up_candidate_ready','candidate_applied'):rename('backup',original,'recovery_original_restore_dispatched')
            final='source_restored' if state in ('original_backed_up_candidate_ready','candidate_applied') else 'source_before_observed'
        else:final='source_before_observed'
        root_pin.revalidate();pin.revalidate()
    return final,dependencies


def _recover(store,root,identifier,direction,expires_at,acknowledged,api):
    if direction not in ('complete','rollback','abort'):_fail('windows_source_edit_recovery_direction')
    phase='before_recovery_intent';intent={}
    try:
        with ws._lock(root,LOCK,api):
            intent,ready,closed=_intent(store,root,identifier,api)
            if closed['status']=='recorded':_fail('windows_source_edit_already_closed')
            proposal,payload=_proposal(intent['proposal_path'],intent['proposal_sha256'],api)
            if proposal['native_source_binding']['root']!=root or proposal['native_source_binding']['root_identity']!=intent['root_identity']:_fail('windows_source_edit_recovery_binding')
            acknowledgment,window=_accept(store,proposal,intent['proposal_sha256'],expires_at,acknowledged,api)
            parent,original,stage,backup=_paths(intent);evidence=_existing_state(root,parent,original,stage,backup,api)
            state=_classification(intent,ready,evidence)
            if direction=='complete' and state not in ('original_before_candidate_ready','original_backed_up_candidate_ready','candidate_applied'):_fail('windows_source_edit_completion_not_established')
            if direction in ('abort','rollback') and state=='candidate_applied' and direction=='abort':_fail('windows_source_edit_abort_would_require_mutation')
            if state=='original_before_candidate_unqualified' and direction!='abort':_fail('windows_source_edit_candidate_unqualified')
            recovery={'schema_version':'workbench-local-source-recovery-intent/1','parent_operation_id':identifier,
                'intent_sha256':digest(intent),'direction':direction,'observed_state':state,'acknowledgment':acknowledgment,
                'original_dispatch_uncertainty_preserved':True,'automatic_retry_permitted':False}
            phase='recovery_intent_pending';ws._create_file(root,PREFIX+digest({'parent_operation_id':identifier,'acknowledgment_id':acknowledgment['operation_id']})+'.recovery.json',canonical(recovery)+b'\n',api)
            if window.closed():_fail('windows_source_edit_ack_expired')
            def mark(value):
                nonlocal phase
                phase=value
            final,dependencies=_dispatch_recovery(intent,ready,proposal,direction,window,api,mark)
            evidence=_existing_state(root,parent,original,stage,backup,api)
            final_state=_classification(intent,ready,evidence)
            if (final=='source_applied' and final_state!='candidate_applied') or (final!='source_applied' and final_state not in ('original_before_no_candidate','original_before_candidate_ready','original_before_candidate_unqualified','original_restored')):_fail('windows_source_edit_recovery_readback')
            phase='recovery_verified_closing_lock'
        phase='recovery_closure_pending';result=_record_closure(root,intent,final,evidence,api,recovery=True,
            recovery_context={'direction':direction,'acknowledgment_sha256':digest(acknowledgment),
                'recorded_dependencies_checked':dependencies,'new_or_unrecorded_source_impacts_verified':False,
                'surrounding_inputs_restored':False,'fresh_resolved_plan_required':True})
        result.update(recovery_direction=direction,recovery_acknowledgment_sha256=digest(acknowledgment),publication_acknowledged=True,
            recorded_dependencies_checked=dependencies,new_or_unrecorded_source_impacts_verified=False,
            surrounding_inputs_restored=False,fresh_resolved_plan_required=True)
        return result
    except BaseException as error:
        if phase!='before_recovery_intent':_fault(error,root,intent,phase)
        raise


def recover_source_edit(store,root,identifier,direction,expires_at,*,acknowledged=False):
    return _recover(store,root,identifier,direction,expires_at,acknowledged,_NativeAPI())


def _review(store,path,expected,api):
    proposal,payload=_proposal(path,expected,api)
    if type(store) is not WindowsWorkbenchStore or proposal['tenant_id']!=store.tenant_id:_fail('windows_source_edit_wrong_store')
    actor=api.current_sid()
    if proposal['native_source_binding']['root_identity']['owner_sid']!=actor:_fail('windows_source_edit_actor_mismatch')
    return {'schema_version':'workbench-local-source-review/1','tenant_id':store.tenant_id,'object_id':proposal['object_id'],
        'proposal_sha256':expected,'proposal_path':path,'authoritative_source':proposal['authoritative_source'],
        'source_root':proposal['native_source_binding']['root'],'root_identity':proposal['native_source_binding']['root_identity'],
        'shared_inheritance_impact':proposal['shared_inheritance_impact'],'actor_sid_observed':actor,
        'suggested_expiry':time.time()+600,'acknowledgment_recorded':False,
        'required_review':'Review the private source.before.yaml, source.after.yaml and full change.patch; metadata alone is not the complete byte diff.',
        'source_modified':False,'fresh_plan_required':True,'protected_plan_approval':False,'organizational_approval':False}


def review_source_proposal(store,path,expected):return _review(store,path,expected,_NativeAPI())
