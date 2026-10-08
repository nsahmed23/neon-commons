"""Fresh authenticated read-only evidence for a stopped Plan with no backend dispatch.

No lease operation, approval consumption, ownership release or history rewriting
exists here. A future native Plan requires a separate versioned signed approval.
"""
from __future__ import annotations
from contextlib import contextmanager
from dataclasses import asdict
import base64
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import time
import uuid
from urllib.parse import urlsplit

from intune_iac import approval_authority as aa, protected, identity_binding as ib, worker_broker as broker, worker_host as host, worker_service as service
from intune_iac.azure_backend import StateRevision
from intune_iac.io import AppError, canonical, digest, parse_json
from intune_iac.provider_journey import _private, _outside_repository, _absolute
from intune_iac import worker_adoption as adoption, worker_provider as provider
from intune_iac import worker_precondition as wp
from intune_iac import worker_adoption_projection as observer_api
from intune_iac import worker_adoption_plan_phase as phase_api

from intune_iac import worker_adoption_plan_recovery as release

_SEAL=object()
_HASH=re.compile(r'^[0-9a-f]{64}$')
_GUID=re.compile(r'^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$')
MAX_BYTES=16*1024*1024
TABLE='adoption_plan_unacquired_observations'
CLASSIFICATION='no_native_backend_dispatch_observed_execution_unknown'


def _fail(code):raise AppError(code,'Fresh exact stopped Plan evidence did not establish the bounded no-backend-dispatch observation; preserve all original outcomes and ownership.') from None


def _snapshot(value):return parse_json(canonical(value))

def _close_resource(resource,phase):
    """Keep the primary cause and propagate a real secondary interruption."""
    if resource is None:return
    primary=sys.exc_info()[1]
    try:resource.close()
    except BaseException as secondary:
        if primary is None:raise
        primary.add_note('Secondary adoption recovery '+phase+': '+str(getattr(secondary,'code',type(secondary).__name__)))
        if isinstance(secondary,(KeyboardInterrupt,SystemExit)):raise secondary from primary

def _close_token(token):return _close_resource(token,'token cleanup')

def _response(response):
    if (type(response) is not ib.ServiceResponse or type(response.status) is not int or type(response.body) is not bytes or len(response.body)>MAX_BYTES
            or type(response.headers) is not tuple or len(response.headers)>100):_fail('lease_recovery_response_invalid')
    headers={}
    for pair in response.headers:
        if type(pair) is not tuple or len(pair)!=2 or any(type(v) is not str for v in pair):_fail('lease_recovery_response_invalid')
        key,value=pair;key=key.lower()
        if key in headers or not re.fullmatch(r'[a-z0-9-]{1,128}',key) or any(ord(c)<32 or ord(c)>126 for c in value):_fail('lease_recovery_response_invalid')
        headers[key]=value
    if headers.get('content-encoding') not in (None,'identity'):_fail('lease_recovery_response_invalid')
    return headers


def inspect_unacquired(phase):
    """Missing/hot/malformed journals never establish absence of effects."""
    if type(phase) not in (phase_api.InitialVerificationPhase,phase_api.RecoveryPlanPhase):_fail('unacquired_plan_phase_required')
    initial=release.inspect_plan_recovery(phase)
    if initial['entries'] or initial['state_write_attempts']:_fail('unacquired_plan_backend_attempt_observed')
    path=phase.journal;before=initial['journal_sha256'];policy=phase.broker_policy
    if protected._sha(path)!=before:_fail('unacquired_plan_journal_changed')
    if any(Path(str(path)+suffix).exists() or Path(str(path)+suffix).is_symlink() for suffix in ('-journal','-wal','-shm')):_fail('unacquired_plan_journal_not_quiescent')
    db=sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1',uri=True,timeout=0)
    try:
        db.execute('PRAGMA trusted_schema=OFF');db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
        rows=db.execute('SELECT sequence,route,status,response_code,request_sha256,response_sha256 FROM attempts ORDER BY sequence LIMIT 4097').fetchall()
        if len(rows)>4096:_fail('unacquired_plan_journal_row_limit')
        if db.execute('SELECT sequence FROM native_lease_requests LIMIT 1').fetchone():_fail('unacquired_plan_backend_attempt_observed')
        db.execute('COMMIT')
    except sqlite3.Error:_fail('unacquired_plan_journal_invalid')
    finally:_close_resource(db,'unacquired journal cleanup')
    routes={route['id']:route for route in policy['routes']};attempts=[];empty=hashlib.sha256(b'').hexdigest()
    for row in rows:
        route=routes.get(row[1])
        if (route is None or route['role']!='provider' or route['audience']!='graph'
                or route['effect'] not in ('discovery','readonly') or route['method'] not in ('GET','HEAD')
                or route['body_sha256']!=empty or row[2] not in ('dispatch_started','outcome_unknown','response_received')
                or type(row[0]) is not int or type(row[4]) is not str or not _HASH.fullmatch(row[4])
                or (row[5] is not None and (type(row[5]) is not str or not _HASH.fullmatch(row[5])))):
            _fail('unacquired_plan_backend_or_nonread_attempt_observed')
        attempts.append(dict(zip(('sequence','route','status','response_code','request_sha256','response_sha256'),row)))
    if protected._sha(path)!=before:_fail('unacquired_plan_journal_changed')
    return {'schema_version':'adoption-plan-unacquired-inspection/1','journal_sha256':before,'policy_sha256':digest(policy),
        'attempts':attempts,'backend_attempt_count':0,'native_lease_request_count':0,'state_write_attempt_count':0,
        'journal_unchanged':True,'classification':CLASSIFICATION,'execution_authorized':False,'release_performed':False}


def _original(phase):
    facts=phase.snapshot();inspection=inspect_unacquired(phase)
    return dict(facts,broker_journal_sha256=inspection['journal_sha256'],broker_inspection_sha256=digest(inspection),
        backend_attempt_count=0,native_lease_request_count=0,state_write_attempt_count=0,
        state_contract_sha256=digest(phase.original.manifest['state_contract']),
        host_run_manifest_sha256=facts['phase_host']['manifest_sha256'],host_run_receipt_sha256=facts['phase_host']['receipt_sha256'])


class _Context:
    def __init__(self,seal,*,phase,binding,backend_credential,upstream,storage,reader,baseline_raw,original_capture_root,source_root):
        if type(phase) not in (phase_api.InitialVerificationPhase,phase_api.RecoveryPlanPhase):_fail('adoption_plan_recovery_phase_required')
        phase._check();job=phase.original;self.phase=phase;self.phase_identifier=phase.identifier
        live=type(self) is LiveUnacquiredPlanContext
        if seal is not _SEAL or type(self) not in (LiveUnacquiredPlanContext,LaboratoryUnacquiredPlanContext) or type(job) is not adoption.AdoptionJob:_fail('lease_recovery_context_required')
        if live:
            ib.require_live_binding(binding)
            if type(upstream) is not broker.NativeUpstream or job.manifest['profile']!='azure_public_pilot':_fail('lease_recovery_profile')
        elif type(binding) is not ib.LaboratoryIdentityBinding or type(upstream) is not broker.LaboratoryUpstream or job.manifest['profile']!='native_docker_laboratory_protocol':_fail('lease_recovery_profile')
        if type(storage) is not service.ControllerBinding or storage.kind!='storage':_fail('lease_recovery_storage_required')
        storage.check(job.manifest['storage_binding_sha256'])
        self.job,self.binding,self.credential,self.upstream,self.storage=job,binding,backend_credential,upstream,storage
        self.observer=observer_api.AdoptionRecoveryProjection(contract=job.manifest['state_contract'],baseline_raw=baseline_raw,original_capture_root=original_capture_root,reader=reader)
        self.observer_binding_sha256=self.observer._proof_sha;self.observer_id=id(self.observer)
        self.original_capture_root=Path(original_capture_root).absolute();self.source_root=Path(source_root).absolute();self._source_binding(job)
        self.profile='azure_public_unacquired_adoption_plan' if live else 'laboratory_unacquired_adoption_plan'
        self.pid=os.getpid();self.original=_original(phase);self.original_sha=digest(self.original)
        identity,target=binding.backend_configuration(backend_credential)
        declared=job.manifest['provider_binding']['backend']
        if (asdict(identity)!=declared['identity'] or any(asdict(target)[k]!=declared['backend'][k] for k in
                ('subscription_id','storage_account_resource_id','blob_endpoint','container','key','workspace','state_lineage'))
                or type(target.state_serial) is not int or target.state_serial!=declared['backend']['state_serial']+1):_fail('adoption_recovery_backend_identity')
        self.identity,self.target=identity,target
        self._capability_ids=tuple(map(id,(phase,job,binding,backend_credential,upstream,storage,self.observer)))
        self.binding_sha256=binding.evidence()['binding_sha256'];self.backend_sha256=digest({'identity':asdict(identity),'target':asdict(target)})
    def __repr__(self):return '<'+type(self).__name__+' redacted>'
    def __reduce_ex__(self,protocol):raise TypeError('Recovery authority cannot be serialized.')
    def check(self):
        live=type(self) is LiveUnacquiredPlanContext
        if (self.profile!=('azure_public_unacquired_adoption_plan' if live else 'laboratory_unacquired_adoption_plan')
                or type(self.binding) is not (ib.LiveIdentityBinding if live else ib.LaboratoryIdentityBinding)
                or type(self.upstream) is not (broker.NativeUpstream if live else broker.LaboratoryUpstream)):_fail('lease_recovery_profile')
        if self._capability_ids!=tuple(map(id,(self.phase,self.job,self.binding,self.credential,self.upstream,self.storage,self.observer))) or self.pid!=os.getpid() or digest(self.original)!=self.original_sha or _original(self.phase)!=self.original or self.phase_identifier!=self.phase.identifier:_fail('lease_recovery_context_changed')
        if type(self.observer) is not observer_api.AdoptionRecoveryProjection or id(self.observer)!=self.observer_id or self.observer._proof_sha!=self.observer_binding_sha256:_fail('adoption_recovery_observer_changed')
        self._source_binding(self.job)
        self.binding.assert_fresh(self.binding_sha256)
        identity,target=self.binding.backend_configuration(self.credential)
        if digest({'identity':asdict(identity),'target':asdict(target)})!=self.backend_sha256 or identity!=self.identity or target!=self.target:_fail('lease_recovery_backend_identity')
        self.storage.check(self.job.manifest['storage_binding_sha256']);self.observer.check()
    def _source_binding(self,job):
        spec=job.manifest['host_spec'];contract=job.manifest['state_contract'];native=job.manifest['provider_binding']
        if host.directory_binding(self.source_root)['sha256']!=spec['source_sha256']:_fail('adoption_recovery_source_changed')
        main=self.source_root/'project'/provider.PROJECT/'main.tf.json';lock=self.source_root/'project'/provider.PROJECT/'.terraform.lock.hcl'
        if (protected._sha(main)!=contract['source_sha256'] or protected._sha(lock)!=contract['locks_sha256']
                or contract['source_sha256']!=native['source_sha256'] or contract['locks_sha256']!=native['lockfile_sha256']
                or contract['effective_inputs_sha256']!=native['effective_input_sha256']
                or contract['backend']!=native['backend']['backend'] or contract['execution_binding_sha256']!=job.manifest['execution_binding_sha256']
                or contract['tenant_id']!=job.manifest['tenant_id'] or [contract['object_id']]!=job.manifest['object_ids']):_fail('adoption_recovery_source_changed')
        configuration=parse_json(main.read_bytes())
        try:desired=configuration['resource'][provider.pe.RESOURCE]['selected']
        except (KeyError,TypeError):_fail('adoption_recovery_source_changed')
        if digest(desired)!=contract['effective_inputs_sha256']:_fail('adoption_recovery_effective_inputs_changed')
    def _absent(self,root):
        path=root/'host-inspection';path.mkdir(mode=0o700)
        manifest=service._bounded_private_json(self.phase.host_root/'manifest.json')
        if protected._sha(self.phase.host_root/'manifest.json')!=self.original['host_run_manifest_sha256']:_fail('lease_recovery_host_changed')
        spec=service._host_spec(manifest['host_spec'])
        if host._inspect(host._Docker(spec,path),manifest['container_name'],'recovery-readonly-inspect') is not None:
            _fail('lease_recovery_original_container_present')
    def _fresh(self,root):
        self.check();self._absent(root);token=None
        try:
            self.binding.recheck();self.check();token=self.binding.backend_storage_token(self.credential,timeout=10)
            endpoint=urlsplit(self.target.blob_endpoint);path='/'+self.target.container+'/'+self.target.key
            response=self.upstream.request(endpoint.hostname,'GET',path,{'authorization':'Bearer '+token._get(),'accept':'application/json','accept-encoding':'identity','x-ms-version':'2023-11-03'},b'',timeout=10)
            headers=_response(response);protected._exclusive(root/'state.raw',response.body)
            if response.status!=200 or headers.get('content-length')!=str(len(response.body)):_fail('unacquired_plan_state_unavailable')
            if (headers.get('x-ms-lease-status'),headers.get('x-ms-lease-state'))!=('unlocked','available'):_fail('unacquired_plan_not_unlocked')
            metadata={key:value for key,value in headers.items() if key.startswith('x-ms-meta-')}
            if metadata:_fail('unacquired_plan_metadata_remaining')
            revision=StateRevision.observe(response.body,etag=headers.get('etag'))
            if (revision.lineage,revision.serial,revision.sha256)!=(self.target.state_lineage,self.target.state_serial,self.target.state_sha256):_fail('unacquired_plan_current_revision_mismatch')
            # This count belongs to the original successful adoption import, whose
            # exact body is checked below. Selected stopped Plan counters stay zero.
            proof,captured=self.observer.observe(response.body,root/'adoption-graph',state_write_attempts=1)
            if proof['classification']!='approved_adoption_successor' or proof['graph_unchanged'] is not True:_fail('unacquired_plan_exact_successor_required')
            expected=digest({'host':endpoint.hostname,'method':'PUT','target':path,'body_sha256':hashlib.sha256(response.body).hexdigest()})
            if self.original['original_import_state_write']['request_sha256']!=expected:_fail('unacquired_plan_original_write_body_mismatch')
            batch,_=captured.verified();self.check()
            facts={'schema_version':'adoption-plan-unacquired-fresh-observation/1','profile':self.profile,'original':self.original,
                'identity':asdict(self.identity),'backend_target':asdict(self.target),'identity_binding_sha256':self.binding.evidence()['binding_sha256'],
                'state':asdict(revision),'metadata':{},'locked':False,'adoption_state_proof':proof,
                'adoption_capture':{'capture_sha256':batch['capture_sha256'],'path':str(root/'adoption-graph')},
                'state_artifact_sha256':hashlib.sha256(response.body).hexdigest(),'observed_at':int(time.time()),
                'storage_binding_sha256':self.storage.sha256,'classification':CLASSIFICATION,'release_performed':False,
                'execution_authorized':False,'platform_qualified':False}
            protected._exclusive(root/'observation.json',canonical(facts));return facts,captured
        finally:_close_token(token)
    def observe(self,output):return observe(context=self,output=output)


class LiveUnacquiredPlanContext(_Context):pass
class LaboratoryUnacquiredPlanContext(_Context):pass


def live_context(**kwargs):return LiveUnacquiredPlanContext(_SEAL,upstream=broker.NativeUpstream(),**kwargs)
def laboratory_context(**kwargs):return LaboratoryUnacquiredPlanContext(_SEAL,**kwargs)


def _context(context):
    if type(context) not in (LiveUnacquiredPlanContext,LaboratoryUnacquiredPlanContext):_fail('unacquired_plan_context_required')
    context.check()


def _new_root(context,output):
    root=Path(output).absolute();_private(root.parent,directory=True);_outside_repository(root)
    roots=(context.job.policy.root,context.job.policy.jobs_root,context.job.root,context.phase.host_root,context.source_root,context.original_capture_root,Path(context.phase.host_spec['source_root']))
    if any(root==old or old in root.parents or root in old.parents for old in roots):_fail('unacquired_plan_output_overlap')
    root.mkdir(mode=0o700,exist_ok=False);return root


def _stable_original(value):return {key:item for key,item in value.items() if key!='policy_sha256'}


def _row(db,identifier):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(TABLE,)).fetchone():_fail('unacquired_plan_observation_missing')
    row=db.execute('SELECT observation_id,original_operation_id,phase_operation_id,phase_manifest_sha256,anchor_sha256,anchor_path FROM '+TABLE+' WHERE observation_id=?',(identifier,)).fetchone()
    if row is None:_fail('unacquired_plan_observation_missing')
    return row


def _load_anchor(context,identifier):
    if type(identifier) is not str or not _GUID.fullmatch(identifier):_fail('unacquired_plan_observation_id')
    with context.job.policy.connection() as db:row=_row(db,identifier)
    path=_private(Path(row[5]))
    if path.stat().st_size>MAX_BYTES:_fail('unacquired_plan_anchor_changed')
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=row[4]:_fail('unacquired_plan_anchor_changed')
    anchor=parse_json(raw)
    if (set(anchor)!={'schema_version','observation_id','classification','service_authority_root','original','initial_observation','implementation_files'}
            or anchor['schema_version']!='adoption-plan-unacquired-anchor/1' or anchor['observation_id']!=identifier
            or anchor['classification']!=CLASSIFICATION or anchor['service_authority_root']!=str(context.job.policy.root)
            or row[1:4]!=(context.job.identifier,context.phase.identifier,context.phase.manifest_sha256)
            or _stable_original(anchor['original'])!=_stable_original(context.original)):_fail('unacquired_plan_anchor_changed')
    return row,anchor


def observe(*,context,output):
    _context(context);root=_new_root(context,output);facts,captured=context._fresh(root);identifier=str(uuid.uuid4())
    anchor={'schema_version':'adoption-plan-unacquired-anchor/1','observation_id':identifier,'classification':CLASSIFICATION,
        'service_authority_root':str(context.job.policy.root),'original':facts['original'],'initial_observation':facts,'implementation_files':service.implementation_binding()}
    protected._exclusive(root/'anchor.json',canonical(anchor));anchor_sha=digest(anchor)
    with context.job.policy.connection() as db:
        db.execute('BEGIN IMMEDIATE');selected,_,_=context.phase.database_snapshot(db)
        if any(context.original.get(key)!=value for key,value in selected.items()):_fail('unacquired_plan_phase_changed')
        context.phase.require_dispatch_quiet(db)
        db.execute('CREATE TABLE IF NOT EXISTS '+TABLE+' (observation_id TEXT PRIMARY KEY,original_operation_id TEXT NOT NULL,phase_operation_id TEXT NOT NULL,phase_manifest_sha256 TEXT NOT NULL,anchor_sha256 TEXT NOT NULL,anchor_path TEXT NOT NULL)')
        db.execute('INSERT INTO '+TABLE+' VALUES (?,?,?,?,?,?)',(identifier,context.job.identifier,context.phase.identifier,context.phase.manifest_sha256,anchor_sha,str(root/'anchor.json')))
        context.job.policy.event(db,context.job.identifier,'stopped_plan_no_backend_dispatch_observed',{'observation_id':identifier,'phase_operation_id':context.phase.identifier,'anchor_sha256':anchor_sha,'release_performed':False,'scope_released':False})
        db.execute('COMMIT');protected._sync(context.job.policy.root)
    row,checked=_load_anchor(context,identifier)
    return _mint(context,root,facts,captured,row,checked)


def refresh(observation_id,*,context,output):
    """Reacquire authority after restart; historical bytes alone grant nothing."""
    _context(context);row,anchor=_load_anchor(context,observation_id);root=_new_root(context,output);facts,captured=context._fresh(root)
    old=anchor['initial_observation']
    if ({k:v for k,v in facts['state'].items() if k!='etag'}!={k:v for k,v in old['state'].items() if k!='etag'}
            or facts['identity']!=old['identity'] or facts['backend_target']!=old['backend_target']):_fail('unacquired_plan_state_changed')
    fields=('classification','original_contract_sha256','original_expected_semantic_sha256','original_baseline_sha256',
        'original_preimage_capture_sha256','original_preimage_raw_sha256','fresh_raw_sha256','reader_identity_sha256')
    if any(facts['adoption_state_proof'][key]!=old['adoption_state_proof'][key] for key in fields):_fail('unacquired_plan_projection_changed')
    return _mint(context,root,facts,captured,row,anchor)


def _mint(context,root,facts,captured,row,anchor):
    cls=LiveUnacquiredPlanObservation if type(context) is LiveUnacquiredPlanContext else LaboratoryUnacquiredPlanObservation
    return cls(_SEAL,context=context,root=root,facts=facts,captured=captured,row=row,anchor=anchor)


class _Observation:
    def __init__(self,seal,*,context,root,facts,captured,row,anchor):
        if (seal is not _SEAL or type(self) not in (LiveUnacquiredPlanObservation,LaboratoryUnacquiredPlanObservation)
                or (type(self) is LiveUnacquiredPlanObservation)!=(type(context) is LiveUnacquiredPlanContext)):_fail('unacquired_plan_observation_required')
        self.context,self.root,self.captured,self.row=context,root,captured,row;self.pid=os.getpid();self.created=time.monotonic()
        self._identity=(id(context),id(captured));old=anchor['initial_observation']['state']
        self.facts={'schema_version':'adoption-plan-unacquired-observation/1','profile':context.profile,'classification':CLASSIFICATION,
            'observation_id':row[0],'anchor_sha256':row[4],'anchor_path':row[5],'anchor_row':list(row),
            'original':facts['original'],'service_authority_root':str(context.job.policy.root),'fresh_observation':facts,
            'fresh_observation_sha256':digest(facts),'initial_state_etag':old['etag'],'current_state_etag':facts['state']['etag'],
            'etag_changed_since_assessment':old['etag']!=facts['state']['etag'],'etag_change_cause':'unestablished' if old['etag']!=facts['state']['etag'] else 'unchanged',
            'lease_independently_unlocked':True,'lock_metadata_remaining':False,'release_performed':False,'ownership_release_authorized':False,
            'platform_qualified':False,'production_approved':False}
        self.sha256=digest(self.facts)
    def __repr__(self):return '<'+type(self).__name__+' redacted>'
    def __reduce_ex__(self,protocol):raise TypeError('An authenticated Plan observation cannot be serialized.')
    def captured_observation(self):self.verified();return self.captured
    def verified(self):
        self.context.check()
        if (self.pid!=os.getpid() or self._identity!=(id(self.context),id(self.captured)) or not 0<=time.monotonic()-self.created<=30
                or digest(self.facts)!=self.sha256 or protected._sha(self.root/'state.raw')!=self.facts['fresh_observation']['state_artifact_sha256']
                or protected._sha(self.root/'observation.json')!=self.facts['fresh_observation_sha256']):_fail('unacquired_plan_observation_changed_or_stale')
        row,_=_load_anchor(self.context,self.row[0])
        if row!=self.row or list(row)!=self.facts['anchor_row']:_fail('unacquired_plan_observation_changed')
        batch,_,_=wp._validated_capture(self.captured,self.context.observer.reader,max_age=30)
        fresh=self.facts['fresh_observation']
        if batch['capture_sha256']!=fresh['adoption_capture']['capture_sha256'] or digest(batch['source']['raw_observed'])!=fresh['adoption_state_proof']['fresh_raw_sha256']:_fail('unacquired_plan_capture_changed')
        return _snapshot(self.facts)


class LiveUnacquiredPlanObservation(_Observation):pass
class LaboratoryUnacquiredPlanObservation(_Observation):pass
