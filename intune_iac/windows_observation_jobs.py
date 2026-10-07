"""Inactive native one-shot observation jobs; no task registration or activation.

The existing Graph reader and atomic publisher retain service/provenance meaning.
An immutable native event chain replaces POSIX JSON replacement and flock. This
is a cooperative private-user boundary, not protection from that user or host.
"""
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime,timezone
import hashlib
import math
import os
from pathlib import PureWindowsPath
import re
import sys
import time
from uuid import uuid4
import xml.etree.ElementTree as ET

from .io import AppError,canonical,digest,parse_json
from . import windows_directory as wd,windows_storage as ws,windows_capture as wc
from . import windows_observation as targets,windows_observer_credentials as credentials
from .observation_reader import ReaderSpec,bind_live_reader,bind_laboratory_reader
from .observation_jobs import _Fixture

VERSION='intune-windows-observer-job/1'
MAX_RUNS=200  # Native store receipts are bounded independently of the Linux job.
MAX_RETAINED=512*1024*1024
# Native writer enforces raw total 8MiB and each of three documents 16MiB.
MAX_CAPTURE_BYTES=8*1024*1024+3*16*1024*1024
_EVENT=re.compile(r'event-([0-9]{6})-([a-f0-9]{64})\.json')
_ID=re.compile(r'[a-f0-9]{32}')
_NATIVE=object();_LAB=object()
_CONFIG={'schema_version','job_id','job_root','job_identity','target','identity','credential','interval_seconds','max_duration_seconds','runtime','profile','fixture_sha256','created_at','mutation_authorized'}
_STATE={'next_due','active_attempt','active_record','run_count','success_count','failure_count','interrupted_count','retained_capture_bytes','missed_cycles','last_attempt','last_success','last_error'}

def _fail(code):raise AppError(code,'The native observation job is changed, busy, incomplete or outside its explicit profile.') from None
def _copy(v):return parse_json(canonical(v))
def _number(v,lo,hi):
    if type(v) not in (int,float) or not math.isfinite(v) or not lo<=v<=hi:_fail('windows_observer_bound_invalid')
    return float(v)
def _iso(value=None):return datetime.fromtimestamp(time.time() if value is None else value,timezone.utc).isoformat().replace('+00:00','Z')
def _stamp(value):
    try:
        v=datetime.fromisoformat(value.replace('Z','+00:00'))
        if v.tzinfo!=timezone.utc:raise ValueError()
        return v.timestamp()
    except (ValueError,TypeError,AttributeError):_fail('windows_observer_time_invalid')
def _identity(pin):return targets._identity(pin._identities[-1])
def _path(path):wd._components(str(path));return str(PureWindowsPath(path))
def _spec(v):
    if type(v) is not dict or set(v)!={'tenant_id','client_id','principal_object_id','object_ids'}:_fail('windows_observer_identity_invalid')
    return ReaderSpec(v['tenant_id'],v['client_id'],v['principal_object_id'],tuple(v['object_ids'])).validate()

class _IO:
    def __init__(self,target):self.target,self.api,self.fs=target,target._api,target._filesystem
    def identity(self,root):
        with wd._pin(root,self.api) as pin:return _identity(pin)
    def names(self,root):
        with wd._pin(root,self.api) as pin:
            names=self.api.names(pin._identities[-1]['final_path'])
            if len(names)>2*MAX_RUNS+10 or len(set(names))!=len(names):_fail('windows_observer_namespace_limit')
            for name in names:ws._leaf(name)
            return sorted(names)
    def read(self,root,name):return self.fs.read_file(root,name)
    def create_dir(self,root,name):return ws._create_directory(root,name,self.api)
    def write(self,root,name,data):return ws._create_file(root,name,data,self.api)
    def publish(self,root,name,data):
        stage='stage-'+uuid4().hex+'.json';self.write(root,stage,data)
        return ws._publish(root,stage,name,hashlib.sha256(data).hexdigest(),self.api)
    def lock(self,root):return ws._lock(root,'observer.lock',self.api)
    def runtime(self,package_root,interpreter,*,native):
        root=PureWindowsPath(_path(package_root));exe=PureWindowsPath(_path(interpreter))
        if native and (sys.platform!='win32' or os.name!='nt' or sys.version_info[:2]!=(3,12)
                or PureWindowsPath(sys.executable)!=exe or PureWindowsPath(__file__).parent.parent!=root):_fail('windows_observer_runtime_unsupported')
        with wd._pin(str(root/'intune_iac'),self.api) as pin:names=self.api.names(pin._identities[-1]['final_path'])
        files=[root/'scripts'/'intune-windows-observer.py',*sorted(root/'intune_iac'/n for n in names if n.endswith('.py'))]
        if len(files)<3 or len(files)>256:_fail('windows_observer_runtime_unsupported')
        files=[exe,*files];bindings={}
        for file in files:
            with wc._directory(file.parent,self.api) as access:
                data=access.read(file.name)
                if file==exe and data[:2]!=b'MZ':_fail('windows_observer_runtime_not_native')
                bindings[str(file)]={'sha256':hashlib.sha256(data).hexdigest(),**access.files[file.name]['identity']}
        return {'package_root':str(root),'interpreter':str(exe),'entrypoint':str(root/'scripts'/'intune-windows-observer.py'),
            'python_version':sys.version,'files':bindings,'assurance':'declared interpreter and application files; native DLL/trust/host qualification separate'}
    def capture_size(self,root):
        total=0
        with wc._directory(root,self.api) as access:
            names=access.names()
            if set(names)-{'raw','export.json','context.json','capture-receipt.json'}:_fail('windows_observer_capture_namespace')
            for name in names:
                if name!='raw':total+=len(access.read(name))
            if 'raw' in names:
                with access.raw() as raw:
                    pages=raw.names()
                    if any(not re.fullmatch(r'page-[0-9]{6}\.json',name) for name in pages):_fail('windows_observer_capture_namespace')
                    for name in pages:total+=len(raw.read(name))
        return total


def _validate_state(state):
    if type(state) is not dict or set(state)!=_STATE:_fail('windows_observer_state_invalid')
    for key in ('run_count','success_count','failure_count','interrupted_count','retained_capture_bytes','missed_cycles'):
        if type(state[key]) is not int or not 0<=state[key]<=9007199254740991:_fail('windows_observer_state_invalid')
    if state['run_count']>MAX_RUNS or (state['active_attempt'] is not None and not _ID.fullmatch(state['active_attempt'])):_fail('windows_observer_state_invalid')
    _stamp(state['next_due'])
    if state['last_success'] is not None:_stamp(state['last_success'])
    if (state['active_attempt'] is None)!=(state['active_record'] is None):_fail('windows_observer_state_invalid')

class _Job:
    def __init__(self,seal,root,target,*,package_root,interpreter):
        native=type(self) is NativeWindowsObservationJob
        if not ((native and seal is _NATIVE and type(target) is targets.NativeWindowsObservationTarget)
                or (type(self) is LaboratoryWindowsObservationJob and seal is _LAB and type(target) is targets.LaboratoryWindowsObservationTarget)):_fail('windows_observer_capability_required')
        self.root,self.target,self.io=_path(root),target,_IO(target);self.native=native
        self.package_root,self.interpreter=_path(package_root),_path(interpreter)
        self.pid,self.closed=os.getpid(),False;self.seal=seal;self._pin=digest({'root':self.root,'target':target._binding,'package_root':self.package_root,'interpreter':self.interpreter})
        self._load()
    def __repr__(self):return '<'+type(self).__name__+' inactive, finite reader>'
    def __reduce_ex__(self,protocol):raise TypeError('Native observation jobs cannot be serialized.')
    def check(self):
        if (self.closed or self.pid!=os.getpid() or self.seal is not (_NATIVE if self.native else _LAB)
                or digest({'root':self.root,'target':self.target._binding,'package_root':self.package_root,'interpreter':self.interpreter})!=self._pin):_fail('windows_observer_job_changed')
        self.target._snapshot()
    def _load(self):
        self.check();names=set(self.io.names(self.root))
        if names-{'config.json','observer.lock','events','captures','fixture.json'} or not {'config.json','events','captures'}<=names:_fail('windows_observer_job_namespace')
        config=parse_json(self.io.read(self.root,'config.json'))
        if (type(config) is not dict or set(config)!=_CONFIG or config['schema_version']!=VERSION or config['job_root']!=self.root
                or type(config['job_id']) is not str or not _ID.fullmatch(config['job_id']) or config['mutation_authorized'] is not False
                or config['job_identity']!=self.io.identity(self.root) or config['target']!=self.target._binding
                or config['profile'] not in ('graph_public_live','laboratory_recorded_responses')):_fail('windows_observer_config_changed')
        spec=_spec(config['identity']);reference=credentials.CredentialReference(**config['credential']).validate()
        if (spec.tenant_id!=self.target._tenant or reference.client_id!=spec.client_id or reference.owner_sid!=config['job_identity']['owner_sid']
                or (not self.native and config['profile']!='laboratory_recorded_responses')):_fail('windows_observer_identity_changed')
        _number(config['interval_seconds'],60,86400);_number(config['max_duration_seconds'],1,300)
        expected_fixture=config['profile']=='laboratory_recorded_responses'
        if expected_fixture!=('fixture.json' in names) or expected_fixture!=(config['fixture_sha256'] is not None):_fail('windows_observer_fixture_changed')
        if expected_fixture and hashlib.sha256(self.io.read(self.root,'fixture.json')).hexdigest()!=config['fixture_sha256']:_fail('windows_observer_fixture_changed')
        events=str(PureWindowsPath(self.root)/'events');last=None;previous=None
        for sequence,name in enumerate(self.io.names(events),1):
            match=_EVENT.fullmatch(name)
            if match is None or int(match[1])!=sequence:_fail('windows_observer_event_chain_invalid')
            raw=self.io.read(events,name);value=parse_json(raw)
            if (hashlib.sha256(raw).hexdigest()!=match[2] or type(value) is not dict or set(value)!={'schema_version','sequence','previous_sha256','config_sha256','state','record'}
                    or value['schema_version']!=VERSION or type(value['sequence']) is not int or value['sequence']!=sequence
                    or value['previous_sha256']!=previous or value['config_sha256']!=digest(config)):_fail('windows_observer_event_chain_invalid')
            _validate_state(value['state']);last=value;previous=match[2]
        if last is None:_fail('windows_observer_event_chain_invalid')
        return config,last,previous
    def _runtime(self,config):
        if self.io.runtime(self.package_root,self.interpreter,native=self.native)!=config['runtime']:_fail('windows_observer_runtime_changed')
    def _append(self,config,last,previous,state,record):
        _validate_state(state)
        value={'schema_version':VERSION,'sequence':last['sequence']+1,'previous_sha256':previous,'config_sha256':digest(config),'state':_copy(state),'record':_copy(record)}
        raw=canonical(value);name=f"event-{value['sequence']:06d}-{hashlib.sha256(raw).hexdigest()}.json"
        self.io.publish(str(PureWindowsPath(self.root)/'events'),name,raw)
        return value,hashlib.sha256(raw).hexdigest()
    def close(self):self.closed=True

class NativeWindowsObservationJob(_Job):pass
class LaboratoryWindowsObservationJob(_Job):pass

def _create_job(target,spec,*,output,credential_reference,package_root,interpreter,interval_seconds=300,max_duration_seconds=120,laboratory_fixture=None):
    native=type(target) is targets.NativeWindowsObservationTarget
    if type(target) not in (targets.NativeWindowsObservationTarget,targets.LaboratoryWindowsObservationTarget) or type(spec) is not ReaderSpec or type(credential_reference) is not credentials.CredentialReference:_fail('windows_observer_capability_required')
    spec.validate();credential_reference.validate();target._snapshot();io=_IO(target)
    root=PureWindowsPath(_path(output));store=PureWindowsPath(target._root)
    if root==store or root in store.parents or store in root.parents:_fail('windows_observer_path_overlap')
    if spec.tenant_id!=target._tenant or credential_reference.client_id!=spec.client_id or credential_reference.owner_sid!=target._binding['directory']['owner_sid']:_fail('windows_observer_identity_changed')
    interval=_number(interval_seconds,60,86400);duration=_number(max_duration_seconds,1,300)
    if not native and laboratory_fixture is None:_fail('windows_observer_live_to_laboratory_forbidden')
    if laboratory_fixture is not None:_Fixture(laboratory_fixture)
    runtime=io.runtime(package_root,interpreter,native=native)
    io.create_dir(str(root.parent),root.name)
    for name in ('events','captures'):io.create_dir(str(root),name)
    if laboratory_fixture is not None:io.write(str(root),'fixture.json',laboratory_fixture)
    config={'schema_version':VERSION,'job_id':uuid4().hex,'job_root':str(root),'job_identity':io.identity(str(root)),
        'target':_copy(target._binding),'identity':asdict(spec),'credential':asdict(credential_reference),'interval_seconds':interval,
        'max_duration_seconds':duration,'runtime':runtime,'profile':'graph_public_live' if laboratory_fixture is None else 'laboratory_recorded_responses',
        'fixture_sha256':None if laboratory_fixture is None else hashlib.sha256(laboratory_fixture).hexdigest(),'created_at':_iso(),'mutation_authorized':False}
    state={'next_due':_iso(),'active_attempt':None,'active_record':None,'run_count':0,'success_count':0,'failure_count':0,'interrupted_count':0,'retained_capture_bytes':0,'missed_cycles':0,'last_attempt':None,'last_success':None,'last_error':None}
    io.write(str(root),'config.json',canonical(config));event={'schema_version':VERSION,'sequence':1,'previous_sha256':None,'config_sha256':digest(config),'state':state,'record':None};raw=canonical(event)
    io.publish(str(root/'events'),'event-000001-'+hashlib.sha256(raw).hexdigest()+'.json',raw)
    cls,seal=(NativeWindowsObservationJob,_NATIVE) if native else (LaboratoryWindowsObservationJob,_LAB)
    return cls(seal,str(root),target,package_root=package_root,interpreter=interpreter)

def create_native_job(target,spec,**kwargs):
    if type(target) is not targets.NativeWindowsObservationTarget:_fail('windows_observer_native_target_required')
    return _create_job(target,spec,**kwargs)

def open_native_job(root):
    # Read immutable public configuration through native private handles before
    # constructing a fresh target; no credential entry is read while opening.
    from .windows_workbench import _Filesystem
    filesystem=_Filesystem();config=parse_json(filesystem.read_file(_path(root),'config.json'))
    if type(config) is not dict or set(config)!=_CONFIG:_fail('windows_observer_config_changed')
    target=targets.bind_native_target(config['target']['root'],config['identity']['tenant_id'])
    try:return NativeWindowsObservationJob(_NATIVE,root,target,package_root=config['runtime']['package_root'],interpreter=config['runtime']['interpreter'])
    except BaseException:target.close();raise

def _retention_error(state,storage):
    if state['run_count']>=MAX_RUNS:return 'windows_observer_cycle_limit'
    if state['retained_capture_bytes']+MAX_CAPTURE_BYTES>MAX_RETAINED:return 'windows_observer_capture_retention_limit'
    if len(storage['outcomes'])+len(storage['unresolved_intents'])>996:return 'windows_observer_store_receipt_limit'
    return None

def _summary(config,state,record=None):
    age=None if state['last_success'] is None else time.time()-_stamp(state['last_success'])
    record=record or {};declared=list(config['identity']['object_ids'])
    complete={oid for result in record.get('scope_outcomes',[]) if result['status']=='complete' and result['coverage']=='complete' for oid in result['object_ids']}
    missing=[oid for oid in declared if oid not in complete]
    return {**_copy(state),'job_id':config['job_id'],'job_root':config['job_root'],'profile':config['profile'],'interval_seconds':config['interval_seconds'],
        'tenant_id':config['identity']['tenant_id'],'declared_object_ids':declared,'last_attempted_at':record.get('started_at'),'last_attempt_ended_at':record.get('ended_at'),
        'last_attempt_scope_status':'unknown' if not record else 'incomplete' if missing else 'complete','last_attempt_incomplete_object_ids':missing,
        'freshness':'unknown' if age is None else 'stale' if state['last_error'] is not None or age<0 or age>2*config['interval_seconds'] else 'fresh',
        'task_installed':False,'task_activated':False,'workbench_profile_enabled':False,'platform_qualified':False,'production_approved':False,
        'retained_capture_bytes_basis':record.get('capture_bytes_basis','measured_capture_files'),'limits':{'max_cycles':MAX_RUNS,'retained_capture_bytes':MAX_RETAINED,'per_capture_reserved_bytes':MAX_CAPTURE_BYTES,'max_objects':100},'cloud_mutation':False}

def job_status(job):
    if type(job) not in (NativeWindowsObservationJob,LaboratoryWindowsObservationJob):_fail('windows_observer_capability_required')
    config,last,_=job._load();error=None
    try:job._runtime(config)
    except AppError as caught:error=caught.code
    active=False
    try:
        with job.io.lock(job.root):pass
    except AppError as caught:
        if caught.code!='windows_storage_lock_busy':raise
        active=True
    retention=_retention_error(last['state'],job.target._store.storage_status())
    status='blocked' if error else 'active' if active else 'interrupted' if last['state']['active_attempt'] else 'blocked' if retention else 'idle'
    summary=_summary(config,last['state'],last['record'])
    action=('Restore the exact approved runtime or create a newly reviewed job; preserve current evidence.' if error else
        'Allow the current finite attempt to finish; do not launch another collector.' if active else
        'Run the finite job to reconcile persisted publication without authenticating old captures.' if last['state']['active_attempt'] else
        'Preserve this job and raw captures; review archival and a new bounded job/store before further collection.' if retention else
        'Inspect incomplete scope and its retained errors; the next due attempt performs fresh reads.' if summary['last_attempt_scope_status']=='incomplete' else
        'Run at the next due time using the reviewed independently scheduled route.')
    return {**summary,'status':status,'binding_error':error,'retention_error':retention,'next_action':action}

def _note_failure(record,error,phase,default):
    code=error.code if isinstance(error,AppError) else 'observer_interrupted' if isinstance(error,(KeyboardInterrupt,SystemExit)) else default
    detail={'phase':phase,'type':type(error).__name__,'code':code}
    for key in ('storage_outcome','observation_outcome'):
        if hasattr(error,key):
            detail[key]=_copy(getattr(error,key));record.setdefault(key,_copy(getattr(error,key)))
    if record.get('error_code') is None:
        record['error_code']=code;record['primary_failure']=detail
    else:record.setdefault('secondary_failures',[]).append(detail)
    return code

def _attempt_bytes(job,attempt,spec):
    parent=str(PureWindowsPath(job.root)/'captures')
    names=job.io.names(parent)
    if any(not _ID.fullmatch(name) for name in names):_fail('windows_observer_capture_namespace')
    if attempt not in names:return 0
    root=str(PureWindowsPath(parent)/attempt);objects=job.io.names(root)
    if set(objects)-set(spec.object_ids):_fail('windows_observer_capture_namespace')
    return sum(job.io.capture_size(str(PureWindowsPath(root)/name)) for name in objects)

def _settled(state,record):
    result=_copy(state);result['active_attempt']=None;result['active_record']=None;result['last_attempt']=record['attempt_id'];result['last_error']=record.get('error_code');result['next_due']=record['next_due'];result['retained_capture_bytes']+=record.get('capture_bytes',0)
    if record['status']=='complete':result['success_count']+=1;result['last_success']=record['ended_at']
    else:result['interrupted_count' if record['status']=='interrupted' else 'failure_count']+=1
    return result

class _SyntheticCredentialAPI:
    def __init__(self,reference):self.reference=reference
    def current_sid(self):return self.reference.owner_sid
    @contextmanager
    def read(self,target):
        yield {'flags':0,'type':1,'target':target,'username':self.reference.client_id,'persist':1,'attribute_count':0,'alias':None,'blob':b'SYNTHETIC-WINDOWS-OBSERVER-ONLY'}


def run_due(job):
    if type(job) not in (NativeWindowsObservationJob,LaboratoryWindowsObservationJob):_fail('windows_observer_capability_required')
    initial,_,_=job._load();binding=digest(initial)
    with job.io.lock(job.root):
        config,last,previous=job._load()
        if digest(config)!=binding:_fail('windows_observer_config_changed')
        job._runtime(config);state=_copy(last['state']);spec=_spec(config['identity'])
        if state['active_attempt'] is not None:
            record=_copy(state['active_record']);attempt=state['active_attempt']
            if type(record) is not dict or record.get('attempt_id')!=attempt:_fail('windows_observer_state_invalid')
            job.target._snapshot()
            with job.target._store._connection() as db:
                ids=[row[0] for row in db.execute('SELECT run_id FROM run_details WHERE domain LIKE ? ORDER BY run_id',('reader:'+config['job_id']+':'+attempt+':%',))]
            found=bool(ids)
            if not found:
                values=job.target.publish([],job_id=config['job_id'],attempt_id=attempt,failures=[{'object_id':oid,'error_code':'observer_previous_runner_interrupted','observed_at':_stamp(record['started_at'])} for oid in spec.object_ids]);ids=[value['run_id'] for value in values]
            record['capture_bytes']=_attempt_bytes(job,attempt,spec)
            record.update(status='interrupted',ended_at=_iso(),error_code='observer_previous_runner_interrupted',persisted_collection_run_ids=ids,publication_found_before_recovery=found,
                recovery='Persisted publication presence only; authentication not reconstructed and old reads not replayed.')
            state=_settled(state,record);last,previous=job._append(config,last,previous,state,record)
        now=time.time();due=_stamp(state['next_due'])
        if now<due:return {**_summary(config,state,last['record']),'status':'not_due','network_attempted':False}
        storage_status=job.target._store.storage_status()
        if _retention_error(state,storage_status):_fail('windows_observer_retention_limit')
        missed=min(1000000,max(0,math.floor((now-due)/config['interval_seconds'])));state['missed_cycles']+=missed
        due=now if missed==1000000 else due+missed*config['interval_seconds'];attempt=uuid4().hex
        record={'attempt_id':attempt,'sequence':state['run_count']+1,'status':'collecting','started_at':_iso(),'ended_at':None,'next_due':_iso(due+config['interval_seconds']),
            'collection_run_ids':[],'capture_bytes':0,'cloud_mutation':False,'source_authenticity_verified':False}
        state.update(active_attempt=attempt,active_record=_copy(record),run_count=record['sequence']);last,previous=job._append(config,last,previous,state,record)
        capture_root=str(PureWindowsPath(job.root)/'captures'/attempt);captures=[];failures=[];reader=None;source=None;primary=None;interrupted=None
        deadline=time.monotonic()+config['max_duration_seconds']
        try:
            job.io.create_dir(str(PureWindowsPath(capture_root).parent),attempt)
            reference=credentials.CredentialReference(**config['credential'])
            if config['profile']=='laboratory_recorded_responses':
                source=credentials._bind_laboratory_credential(reference,_SyntheticCredentialAPI(reference));fixture=_Fixture(job.io.read(job.root,'fixture.json'))
            else:source=credentials.bind_native_credential(reference);fixture=None
            with source.acquire() as credential:
                reader=bind_laboratory_reader(spec,credential=credential,transport=fixture,max_duration_seconds=config['max_duration_seconds']) if fixture is not None else bind_live_reader(spec,credential=credential,max_duration_seconds=config['max_duration_seconds'])
                reader_primary=None
                try:
                    record['reader_identity']=reader.evidence();record['source_authenticity_verified']=record['reader_identity']['source_authenticity_verified']
                    for oid in spec.object_ids:
                        remaining=deadline-time.monotonic()
                        if remaining<=0 or state['retained_capture_bytes']+record['capture_bytes']+MAX_CAPTURE_BYTES>MAX_RETAINED:
                            failures.append({'object_id':oid,'error_code':'observer_capture_budget','observed_at':time.time()});continue
                        destination=str(PureWindowsPath(capture_root)/oid)
                        record['reserved_capture_bytes']=MAX_CAPTURE_BYTES;capture_primary=None
                        try:
                            value=job.target.capture(reader,oid,destination,max_elapsed_seconds=min(120,remaining));captures.append(value)
                            if value.cancelled:raise KeyboardInterrupt()
                        except AppError as error:
                            capture_primary=error
                            failures.append({'object_id':oid,'error_code':error.code,'observed_at':time.time()})
                            if hasattr(error,'storage_outcome'):record.setdefault('storage_outcomes',[]).append(_copy(error.storage_outcome))
                        except BaseException as error:
                            capture_primary=error;raise
                        finally:
                            try:
                                measured=_attempt_bytes(job,attempt,spec)
                                if measured-record['capture_bytes']>MAX_CAPTURE_BYTES or measured+state['retained_capture_bytes']>MAX_RETAINED:_fail('windows_observer_capture_size_exceeded')
                                record['capture_bytes']=measured;record['reserved_capture_bytes']=0
                            except BaseException as measurement:
                                # The full remaining reservation is spent when safe measurement fails.
                                # A partial failed capture cannot buy another object or another cycle.
                                record['capture_bytes']=max(0,MAX_RETAINED-state['retained_capture_bytes'])
                                record['capture_measurement_error']=getattr(measurement,'code','observer_capture_measurement_failed')
                                record['publication_blocked']=True;record['capture_bytes_basis']='unknown_conservative_budget_charge'
                                if capture_primary is not None:
                                    capture_primary.observer_measurement_failure={'phase':'capture_measurement','type':type(measurement).__name__,'code':'observer_interrupted' if isinstance(measurement,(KeyboardInterrupt,SystemExit)) else record['capture_measurement_error']}
                                    if isinstance(measurement,(KeyboardInterrupt,SystemExit)):capture_primary.observer_measurement_interruption=measurement
                                    raise capture_primary
                                raise
                    job._runtime(config);job.target._snapshot()
                    if digest(job._load()[0])!=binding:_fail('windows_observer_config_changed')
                except BaseException as error:reader_primary=error;raise
                finally:
                    try:reader.close()
                    except BaseException as cleanup:
                        if reader_primary is not None:reader_primary.observer_cleanup_failures=getattr(reader_primary,'observer_cleanup_failures',[])+[type(cleanup).__name__]
                        else:raise
                    finally:reader=None
            source.close();source=None
        except BaseException as error:
            primary=error;code=_note_failure(record,error,'read_or_cleanup','observer_read_failed')
            if hasattr(error,'observer_measurement_failure'):record.setdefault('secondary_failures',[]).append(_copy(error.observer_measurement_failure))
            if hasattr(error,'observer_measurement_interruption'):interrupted=error.observer_measurement_interruption
            covered={item._batch['object_id'] for item in captures}|{item['object_id'] for item in failures}
            failures.extend({'object_id':oid,'error_code':code,'observed_at':time.time()} for oid in spec.object_ids if oid not in covered)
            if code in ('windows_observer_runtime_changed','windows_observer_config_changed','windows_observer_target_changed'):record['publication_blocked']=True
            if isinstance(error,(KeyboardInterrupt,SystemExit)):interrupted=error
        finally:
            for owned in (reader,source):
                if owned is not None:
                    try:owned.close()
                    except BaseException as cleanup:
                        if primary is not None:primary.observer_cleanup_failures=getattr(primary,'observer_cleanup_failures',[])+[type(cleanup).__name__]
                        else:raise
        if primary is not None and getattr(primary,'observer_cleanup_failures',None):record['cleanup_failures']=list(primary.observer_cleanup_failures)
        try:
            if not record.get('capture_measurement_error'):record['capture_bytes']=_attempt_bytes(job,attempt,spec)
        except BaseException as measurement:
            # Unknown retained bytes never buy another unbounded cycle.
            record['capture_bytes']=max(0,MAX_RETAINED-state['retained_capture_bytes']);record['capture_measurement_error']=getattr(measurement,'code','observer_capture_measurement_failed')
            record['publication_blocked']=True;record['capture_bytes_basis']='unknown_conservative_budget_charge';_note_failure(record,measurement,'capture_measurement','observer_capture_measurement_failed')
            if primary is None:primary=measurement
            if isinstance(measurement,(KeyboardInterrupt,SystemExit)):interrupted=measurement
        try:
            if record.get('publication_blocked'):_fail(record['error_code'])
            job._runtime(config);job.target._snapshot()
            results=job.target.publish(captures,job_id=config['job_id'],attempt_id=attempt,failures=failures)
            record['collection_run_ids']=[value['run_id'] for value in results]
            record['scope_outcomes']=[{'object_ids':v['scope']['object_ids'],'status':v['status'],'coverage':v['coverage']} for v in results]
            complete=bool(results) and record.get('error_code') is None and all(v['status']=='complete' and v['coverage']=='complete' for v in results)
            record['status']='interrupted' if interrupted else 'complete' if complete else 'failed'
            if not complete:record.setdefault('error_code','observer_collection_incomplete')
        except BaseException as error:
            _note_failure(record,error,'publication','observer_publication_failed')
            if primary is None:primary=error
            if isinstance(error,(KeyboardInterrupt,SystemExit)):interrupted=error
            record['status']='interrupted' if interrupted else 'failed'
        record['ended_at']=_iso();state=_settled(state,record)
        try:last,previous=job._append(config,last,previous,state,record)
        except BaseException as error:
            if primary is not None:
                primary.observer_recording_failure=type(error).__name__
                if interrupted is not None and interrupted is not primary:raise interrupted from primary
                raise primary
            raise
        if interrupted is not None:
            if interrupted is not primary:raise interrupted from primary
            raise interrupted
        return {**_summary(config,state,record),'status':record['status'],'attempt_record':_copy(record),'event_sha256':previous}

def scheduler_artifacts(job,output,*,start_boundary,account_sid):
    """Render a disabled, least-privilege task; never register or execute it."""
    import subprocess
    if type(job) not in (NativeWindowsObservationJob,LaboratoryWindowsObservationJob):_fail('windows_observer_capability_required')
    config,last,_=job._load();job._runtime(config);_stamp(start_boundary)
    if account_sid!=config['credential']['owner_sid'] or account_sid!=config['job_identity']['owner_sid']:_fail('windows_observer_task_account_changed')
    if type(start_boundary) is not str or start_boundary!=_iso(_stamp(start_boundary)):_fail('windows_observer_time_invalid')
    target=PureWindowsPath(_path(output));job_root=PureWindowsPath(job.root);store=PureWindowsPath(job.target._root)
    if any(target==p or target in p.parents or p in target.parents for p in (job_root,store)):_fail('windows_observer_path_overlap')
    argv=[config['runtime']['interpreter'],'-I','-B',config['runtime']['entrypoint'],'run','--job',job.root]
    if any(type(v) is not str or '%' in v or any(ord(c)<32 for c in v) or '\x7f' in v for v in argv):_fail('windows_observer_task_argument_invalid')
    namespace='http://schemas.microsoft.com/windows/2004/02/mit/task';ET.register_namespace('',namespace)
    def add(parent,name,text=None,**attributes):
        node=ET.SubElement(parent,'{'+namespace+'}'+name,attributes)
        if text is not None:node.text=text
        return node
    task=ET.Element('{'+namespace+'}Task',{'version':'1.4'})
    info=add(task,'RegistrationInfo');add(info,'Description','Inactive Intune scoped read-only observation; review exact pins and existing credential route before authorized registration.')
    triggers=add(task,'Triggers');trigger=add(triggers,'TimeTrigger');repetition=add(trigger,'Repetition')
    add(repetition,'Interval','PT'+str(int(config['interval_seconds']))+'S');add(repetition,'StopAtDurationEnd','false');add(trigger,'StartBoundary',start_boundary);add(trigger,'Enabled','false')
    principals=add(task,'Principals');principal=add(principals,'Principal',id='Observer');add(principal,'UserId',config['credential']['owner_sid']);add(principal,'LogonType','InteractiveToken');add(principal,'RunLevel','LeastPrivilege')
    settings=add(task,'Settings')
    for name,value in [('MultipleInstancesPolicy','IgnoreNew'),('DisallowStartIfOnBatteries','false'),('StopIfGoingOnBatteries','false'),('AllowHardTerminate','true'),('StartWhenAvailable','true'),('RunOnlyIfNetworkAvailable','false'),('AllowStartOnDemand','false'),('Enabled','false'),('Hidden','false'),('ExecutionTimeLimit','PT'+str(math.ceil(config['max_duration_seconds'])+15)+'S'),('Priority','7')]:add(settings,name,value)
    actions=add(task,'Actions',Context='Observer');action=add(actions,'Exec');add(action,'Command',argv[0]);add(action,'Arguments',subprocess.list2cmdline(argv[1:]));add(action,'WorkingDirectory',config['runtime']['package_root'])
    raw=ET.tostring(task,encoding='utf-8',xml_declaration=True)
    # Round-trip the exact rendered fields before publishing the inert file.
    parsed=ET.fromstring(raw);prefix={'t':namespace}
    if parsed.findtext('t:Principals/t:Principal/t:RunLevel',namespaces=prefix)!='LeastPrivilege' or parsed.findtext('t:Settings/t:Enabled',namespaces=prefix)!='false':_fail('windows_observer_task_invalid')
    receipt={'schema_version':'intune-windows-observer-task/1','job_id':config['job_id'],'config_sha256':digest(config),'job_event_sha256':digest(last),
        'owner_sid':config['credential']['owner_sid'],'credential_reference':config['credential'],'argv':argv,'task_sha256':hashlib.sha256(raw).hexdigest(),
        'runtime':config['runtime'],'installed':False,'activated':False,'platform_qualified':False,'production_approved':False,
        'logon_profile':'named user remains logged on; all terminals may close; no logged-off service claim',
        'required_authorization':'Named host owner must approve exact task, identity, credentials, source, scope and retention before native registration/enable.',
        'recovery':'Disable the exact approved task to stop future reads; preserve captures/events and inspect interrupted publication before a fresh due read.'}
    job.io.create_dir(str(target.parent),target.name);job.io.write(str(target),'observer-task.xml',raw);job.io.write(str(target),'scheduler-receipt.json',canonical(receipt));return receipt
