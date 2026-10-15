"""Explicitly signed one-shot release of a stranded native Azure state lease.

The old worker approval cannot authorize this operation. No acquire, break,
metadata clear, Graph mutation or state write exists in this module. Ownership
remains reserved after release for separately established reconciliation.
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
import tempfile
import time
import uuid
from urllib.parse import urlsplit

from intune_iac import approval_authority as aa, protected, identity_binding as ib, worker_broker as broker, worker_host as host, worker_service as service
from intune_iac.azure_backend import StateRevision
from intune_iac.io import AppError, canonical, digest, parse_json
from intune_iac.provider_journey import _private, _outside_repository, _absolute
from intune_iac.worker_recovery import inspect_native_recovery

SIGNATURE_DOMAIN=b'intune-workbench:native-lease-recovery-approval:v1\x00'
_SEAL=object()
_HASH=re.compile(r'^[0-9a-f]{64}$')
_GUID=re.compile(r'^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$')
MAX_BYTES=16*1024*1024
PROFILES={'laboratory_native_lease_recovery','azure_public_native_lease_recovery'}


def _fail(code):raise AppError(code,'The explicitly approved native lease recovery was not established; preserve ownership and all uncertain outcomes.') from None

def _snapshot(value):return parse_json(canonical(value))

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


def _original(job):
    if type(job) is not service.ServiceJob:_fail('lease_recovery_original_required')
    job._check(expiry=False)
    with job.policy.connection() as db:
        row=db.execute('SELECT status,cancelled,dispatches,outcome,controller_pid,controller_start FROM jobs WHERE id=?',(job.identifier,)).fetchone()
        consumed=db.execute('SELECT manifest_sha256 FROM consumed WHERE operation_id=?',(job.identifier,)).fetchone()
        scopes=sorted(r[0] for r in db.execute('SELECT scope FROM ownership WHERE job=?',(job.identifier,)))
    if (row is None or row[0] not in ('outcome_unknown','host_completed_service_unverified') or row[2]!=1 or
            row[4] is not None or row[5] is not None or consumed!=(job.sha256,) or scopes!=service._scopes(job.manifest)):
        _fail('lease_recovery_original_active_or_unowned')
    outcome=parse_json(row[3]) if row[3] else None
    if (type(outcome) is not dict or type(outcome.get('host')) is not dict or
            outcome['host'].get('cleanup',{}).get('removed') is not True or
            outcome['host']['cleanup'].get('stopped_state',{}).get('Running') is not False):
        _fail('lease_recovery_original_cleanup_unconfirmed')
    inspection=inspect_native_recovery(job.root/'broker.sqlite3',policy=job.manifest['broker_policy'])
    entries=inspection['entries'];acquires=[r for r in entries if r['action']=='acquire']
    if len(acquires)!=1 or any(r['lease_id']!=acquires[0]['lease_id'] for r in entries):_fail('lease_recovery_original_lease_ambiguous')
    lock=job.manifest['broker_policy'].get('native_lock')
    if not lock or any((r['host'],r['path'])!=(lock['host'],lock['path']) for r in entries):_fail('lease_recovery_original_target')
    return {'operation_id':job.identifier,'manifest_sha256':job.sha256,'policy_sha256':job.policy.sha256,
        'outcome_sha256':digest(outcome),'broker_journal_sha256':inspection['journal_sha256'],'status':row[0],
        'cancelled':bool(row[1]),'scopes':scopes,'lease_id':acquires[0]['lease_id'],'lock':lock,
        'recorded_metadata':sorted({r['lock_metadata'] for r in entries if r['lock_metadata'] is not None}),
        'host_run_manifest_sha256':protected._sha(job.root/'host-run/manifest.json')}


class _Context:
    def __init__(self,seal,*,job,binding,backend_credential,upstream,storage):
        live=type(self) is LiveRecoveryContext
        if seal is not _SEAL or type(self) not in (LiveRecoveryContext,LaboratoryRecoveryContext):_fail('lease_recovery_context_required')
        if live:
            ib.require_live_binding(binding)
            if type(upstream) is not broker.NativeUpstream or job.manifest['profile']!='azure_public_pilot':_fail('lease_recovery_profile')
        elif type(binding) is not ib.LaboratoryIdentityBinding or type(upstream) is not broker.LaboratoryUpstream or job.manifest['profile']!='native_docker_laboratory_protocol':_fail('lease_recovery_profile')
        if type(storage) is not service.ControllerBinding or storage.kind!='storage':_fail('lease_recovery_storage_required')
        storage.check(job.manifest['storage_binding_sha256'])
        self.job,self.binding,self.credential,self.upstream,self.storage=job,binding,backend_credential,upstream,storage
        self.profile='azure_public_native_lease_recovery' if live else 'laboratory_native_lease_recovery'
        self.pid=os.getpid();self.original=_original(job);self.original_sha=digest(self.original)
        identity,target=binding.backend_configuration(backend_credential)
        declared=job.manifest['provider_binding']['backend']
        if (asdict(identity)!=declared['identity'] or any(asdict(target)[k]!=declared['backend'][k] for k in
                ('subscription_id','storage_account_resource_id','blob_endpoint','container','key','workspace',
                 'state_lineage','state_serial','state_sha256'))):_fail('lease_recovery_backend_identity')
        self.identity,self.target=identity,target
        self.binding_sha256=binding.evidence()['binding_sha256'];self.backend_sha256=digest({'identity':asdict(identity),'target':asdict(target)})
    def __repr__(self):return '<'+type(self).__name__+' redacted>'
    def __reduce_ex__(self,protocol):raise TypeError('Recovery authority cannot be serialized.')
    def check(self):
        live=type(self) is LiveRecoveryContext
        if (self.profile!=('azure_public_native_lease_recovery' if live else 'laboratory_native_lease_recovery')
                or type(self.binding) is not (ib.LiveIdentityBinding if live else ib.LaboratoryIdentityBinding)
                or type(self.upstream) is not (broker.NativeUpstream if live else broker.LaboratoryUpstream)):_fail('lease_recovery_profile')
        if self.pid!=os.getpid() or digest(self.original)!=self.original_sha or _original(self.job)!=self.original:_fail('lease_recovery_context_changed')
        self.binding.assert_fresh(self.binding_sha256)
        identity,target=self.binding.backend_configuration(self.credential)
        if digest({'identity':asdict(identity),'target':asdict(target)})!=self.backend_sha256 or identity!=self.identity or target!=self.target:_fail('lease_recovery_backend_identity')
        self.storage.check(self.job.manifest['storage_binding_sha256'])
    def _absent(self,root):
        path=root/'host-inspection';path.mkdir(mode=0o700)
        manifest=service._bounded_private_json(self.job.root/'host-run/manifest.json')
        if protected._sha(self.job.root/'host-run/manifest.json')!=self.original['host_run_manifest_sha256']:_fail('lease_recovery_host_changed')
        spec=service._host_spec(manifest['host_spec'])
        if host._inspect(host._Docker(spec,path),manifest['container_name'],'recovery-readonly-inspect') is not None:
            _fail('lease_recovery_original_container_present')
    def observe(self,output,*,require_locked=True):
        self.check();root=Path(output).absolute();_private(root.parent,directory=True);root.mkdir(mode=0o700,exist_ok=False)
        self._absent(root);token=None
        try:
            self.binding.recheck()
            self.check();token=self.binding.backend_storage_token(self.credential,timeout=10)
            endpoint=urlsplit(self.target.blob_endpoint);path='/'+self.target.container+'/'+self.target.key
            request_headers={'authorization':'Bearer '+token._get(),'accept':'application/json','accept-encoding':'identity','x-ms-version':'2023-11-03'}
            if require_locked:request_headers['x-ms-lease-id']=self.original['lease_id']
            response=self.upstream.request(endpoint.hostname,'GET',path,request_headers,b'',timeout=10)
            headers=_response(response);protected._exclusive(root/'state.raw',response.body)
            if response.status!=200 or headers.get('content-length')!=str(len(response.body)):_fail('lease_recovery_state_unavailable')
            if (headers.get('x-ms-lease-status'),headers.get('x-ms-lease-state')) != (('locked','leased') if require_locked else ('unlocked','available')):
                _fail('lease_recovery_lock_mismatch')
            metadata={key:value for key,value in headers.items() if key.startswith('x-ms-meta-')}
            if set(metadata)-{'x-ms-meta-terraformlockid'}:_fail('lease_recovery_metadata_unknown')
            lockmeta=metadata.get('x-ms-meta-terraformlockid')
            if lockmeta is not None and lockmeta not in self.original['recorded_metadata']:_fail('lease_recovery_metadata_changed')
            if require_locked and lockmeta is None and self.original['recorded_metadata']:
                journal=inspect_native_recovery(self.job.root/'broker.sqlite3',policy=self.job.manifest['broker_policy'])
                if not any(row['action']=='metadata_clear' for row in journal['entries']):
                    _fail('lease_recovery_metadata_missing')
            revision=StateRevision.observe(response.body,etag=headers.get('etag'))
            if (revision.lineage!=self.target.state_lineage or revision.serial!=self.target.state_serial or revision.sha256!=self.target.state_sha256):
                _fail('lease_recovery_current_revision_mismatch')
            self.check()
            facts={'schema_version':'native-lease-recovery-observation/1','profile':self.profile,'original':self.original,
                'identity':asdict(self.identity),'backend_target':asdict(self.target),'identity_binding_sha256':self.binding.evidence()['binding_sha256'],
                'lease_id':self.original['lease_id'],'state':asdict(revision),'metadata':metadata,'locked':require_locked,
                'state_artifact_sha256':hashlib.sha256(response.body).hexdigest(),'observed_at':int(time.time()),
                'storage_binding_sha256':self.storage.sha256,'execution_authorized':False,'platform_qualified':False}
            protected._exclusive(root/'observation.json',canonical(facts));return RecoveryObservation(_SEAL,self,facts,root)
        finally:
            if token is not None:token.close()


class LiveRecoveryContext(_Context):pass
class LaboratoryRecoveryContext(_Context):pass

def live_context(*,job,binding,backend_credential,storage):
    return LiveRecoveryContext(_SEAL,job=job,binding=binding,backend_credential=backend_credential,upstream=broker.NativeUpstream(),storage=storage)

def laboratory_context(*,job,binding,backend_credential,storage,upstream):
    return LaboratoryRecoveryContext(_SEAL,job=job,binding=binding,backend_credential=backend_credential,upstream=upstream,storage=storage)


class RecoveryObservation:
    def __init__(self,seal,context,facts,root):
        if seal is not _SEAL or type(context) not in (LiveRecoveryContext,LaboratoryRecoveryContext):_fail('lease_recovery_observation_required')
        self.context,self.facts,self.root=context,_snapshot(facts),root
        self.sha256=digest(facts);self.created=time.monotonic();self.pid=os.getpid()
    def __reduce_ex__(self,protocol):raise TypeError('Recovery observations cannot be serialized.')
    def verified(self):
        self.context.check()
        if (self.pid!=os.getpid() or not 0<=time.monotonic()-self.created<=30 or digest(self.facts)!=self.sha256
                or protected._sha(self.root/'state.raw')!=self.facts['state_artifact_sha256']
                or protected._sha(self.root/'observation.json')!=self.sha256):_fail('lease_recovery_observation_changed_or_stale')
        return _snapshot(self.facts)


def prepare(observation,*,operation_id,expires_at):
    if type(observation) is not RecoveryObservation:_fail('lease_recovery_observation_required')
    facts=observation.verified();now=int(time.time())
    if (type(operation_id) is not str or not _GUID.fullmatch(operation_id) or operation_id==facts['original']['operation_id']
            or type(expires_at) is not int or not now<expires_at<=now+300 or not facts['locked']):_fail('lease_recovery_manifest_invalid')
    return {'schema_version':'native-lease-recovery-operation/1','operation_id':operation_id,'prepared_at':now,'expires_at':expires_at,
        'profile':facts['profile'],'action':'release_exact_existing_native_lease','observation':facts,
        'implementation_files':service.implementation_binding(),'recovery_implementation_sha256':protected._sha(Path(__file__)), 'metadata_clear_authorized':False,'ownership_release_authorized':False}


class RecoveryPolicy:
    def __init__(self,path):
        self.path=_private(path);_private(self.path.parent,directory=True);_outside_repository(self.path)
        value=service._bounded_private_json(self.path)
        if (type(value) is not dict or set(value)!={'schema_version','authority_root','verifier','approvers','admitted_manifest_sha256'}
                or value['schema_version']!='native-lease-recovery-policy/1'):_fail('lease_recovery_policy_invalid')
        self.root=_absolute(value['authority_root']);_outside_repository(self.root/'recovery');_private(self.root.parent,directory=True)
        if self.root==self.path or self.root in self.path.parents:_fail('lease_recovery_policy_overlap')
        self.root.mkdir(mode=0o700,exist_ok=True);_private(self.root,directory=True)
        verifier=value['verifier']
        if type(verifier) is not dict or set(verifier)!={'executable','sha256','validator_library','validator_sha256'}:_fail('lease_recovery_policy_invalid')
        self.verifier=aa.VerifierPin(_absolute(verifier['executable']),service._hash(verifier['sha256']),_absolute(verifier['validator_library']),service._hash(verifier['validator_sha256']))
        self.approvers={}
        if type(value['approvers']) is not list or not 1<=len(value['approvers'])<=32:_fail('lease_recovery_policy_invalid')
        for item in value['approvers']:
            if (type(item) is not dict or set(item)!={'issuer','key_id','approver_id','public_key_hex','profiles'}
                    or any(type(item[k]) is not str or not aa._LABEL.fullmatch(item[k]) for k in ('issuer','key_id','approver_id'))
                    or type(item['profiles']) is not list or not item['profiles'] or not set(item['profiles'])<=PROFILES):_fail('lease_recovery_policy_invalid')
            service._hash(item['public_key_hex']);aa._valid_public_key(self.verifier,bytes.fromhex(item['public_key_hex']))
            key=(item['issuer'],item['key_id'])
            if key in self.approvers:_fail('lease_recovery_policy_invalid')
            self.approvers[key]=item
        admitted=value['admitted_manifest_sha256']
        if type(admitted) is not list or not 1<=len(admitted)<=1000 or len(set(admitted))!=len(admitted):_fail('lease_recovery_policy_invalid')
        self.admitted=frozenset(service._hash(item) for item in admitted);self.sha256=digest(value)
    def check(self):
        if digest(service._bounded_private_json(self.path))!=self.sha256:_fail('lease_recovery_policy_changed')
    def verify(self,manifest,signed):return self._verified(manifest,signed,int(time.time()))
    def _verified(self,manifest,signed,now):
        self.check();manifest=_snapshot(manifest)
        if (set(manifest)!={'schema_version','operation_id','prepared_at','expires_at','profile','action','observation','implementation_files','recovery_implementation_sha256','metadata_clear_authorized','ownership_release_authorized'}
                or manifest['schema_version']!='native-lease-recovery-operation/1' or manifest['profile'] not in PROFILES
                or manifest['action']!='release_exact_existing_native_lease' or manifest['metadata_clear_authorized'] is not False
                or manifest['ownership_release_authorized'] is not False or type(manifest['operation_id']) is not str or not _GUID.fullmatch(manifest['operation_id'])
                or type(manifest['prepared_at']) is not int or type(manifest['expires_at']) is not int
                or not manifest['prepared_at']<=now+5<manifest['expires_at']<=manifest['prepared_at']+300
                or manifest['implementation_files']!=service.implementation_binding() or manifest['recovery_implementation_sha256']!=protected._sha(Path(__file__)) or digest(manifest) not in self.admitted):_fail('lease_recovery_manifest_not_admitted')
        if type(signed) is not dict or set(signed)!={'payload','signature'}:_fail('lease_recovery_signature_shape')
        payload=signed['payload']
        if (type(payload) is not dict or set(payload)!={'schema_version','issuer','key_id','approver_id','operation_id','manifest_sha256','issued_at','expires_at','nonce'}
                or payload['schema_version']!='signed-native-lease-recovery-approval/1' or payload['operation_id']!=manifest['operation_id']
                or payload['manifest_sha256']!=digest(manifest) or type(payload['nonce']) is not str or not re.fullmatch(r'[0-9a-f]{32}',payload['nonce'])
                or type(payload['issued_at']) is not int or type(payload['expires_at']) is not int
                or not manifest['prepared_at']<=payload['issued_at']<=now+5 or not now<payload['expires_at']<=manifest['expires_at']):_fail('lease_recovery_signature_binding')
        if any(type(payload[k]) is not str for k in ('issuer','key_id','approver_id')):_fail('lease_recovery_signer_invalid')
        signer=self.approvers.get((payload['issuer'],payload['key_id']))
        if signer is None or signer['approver_id']!=payload['approver_id'] or manifest['profile'] not in signer['profiles']:_fail('lease_recovery_signer_invalid')
        try:signature=base64.b64decode(signed['signature'],validate=True)
        except (TypeError,ValueError):_fail('lease_recovery_signature_invalid')
        if len(signature)!=64 or base64.b64encode(signature).decode()!=signed['signature']:_fail('lease_recovery_signature_invalid')
        descriptor=os.open(protected._path(self.verifier.executable),os.O_RDONLY|os.O_NOFOLLOW)
        try:
            with os.fdopen(os.dup(descriptor),'rb') as stream:
                if hashlib.file_digest(stream,'sha256').hexdigest()!=self.verifier.sha256:_fail('lease_recovery_verifier_changed')
            with tempfile.TemporaryDirectory(prefix='lease-recovery-verify-',dir=self.root) as temporary:
                root=Path(temporary)
                for name,raw in [('key.der',aa._SPKI+bytes.fromhex(signer['public_key_hex'])),('message',SIGNATURE_DOMAIN+canonical(payload)),('signature',signature)]:protected._exclusive(root/name,raw)
                protected._supervise([str(self.verifier.executable),'pkeyutl','-verify','-pubin','-keyform','DER','-inkey',str(root/'key.der'),'-rawin','-in',str(root/'message'),'-sigfile',str(root/'signature')],cwd=root,
                    env={'PATH':'/usr/bin:/bin','HOME':str(root),'OPENSSL_CONF':'/dev/null'},pass_fds=(descriptor,),executable='/proc/self/fd/'+str(descriptor),timeout=5,output_limit=4096)
        except AppError:_fail('lease_recovery_signature_invalid')
        finally:os.close(descriptor)
        return payload


def execute(manifest,signed,*,context,policy,output):
    if type(context) not in (LiveRecoveryContext,LaboratoryRecoveryContext) or type(policy) is not RecoveryPolicy:_fail('lease_recovery_context_required')
    manifest=_snapshot(manifest)
    try:payload=policy.verify(manifest,signed)
    except AppError:service._record_recovery_expiry(context.job.policy,policy,manifest,signed,fail=_fail,expired_code='lease_recovery_expired');raise
    # The window is judged where it is recorded, before any observation or request: a reached expiry is latched in the
    # original job's store and refused here, so it stays closed after a backward clock step and a restart.
    deadline=service._deadline(payload)
    with service._critical(context.job.policy,payload,digest(manifest),deadline,table=service.RECOVERY_EXPIRED_TABLE,fail=_fail,expired_code='lease_recovery_expired'):pass
    context.check()
    if manifest['profile']!=context.profile or manifest['observation']['original']!=context.original:_fail('lease_recovery_context_changed')
    with context.job.policy.connection() as db:
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='native_lease_recoveries'").fetchone():
            if db.execute('SELECT 1 FROM native_lease_recoveries WHERE original_operation=? OR recovery_operation=? OR (issuer=? AND nonce=?)',(context.job.identifier,manifest['operation_id'],payload['issuer'],payload['nonce'])).fetchone():_fail('lease_recovery_not_replayable')
    root=Path(output).absolute();_private(root.parent,directory=True);root.mkdir(mode=0o700,exist_ok=False)
    protected._exclusive(root/'manifest.json',canonical(manifest));protected._exclusive(root/'signed-approval.json',canonical(signed))
    fresh=context.observe(root/'prewrite').verified()
    if {k:v for k,v in fresh.items() if k!='observed_at'}!={k:v for k,v in manifest['observation'].items() if k!='observed_at'}:_fail('lease_recovery_prewrite_changed')
    policy.check();context.check();token=None;dispatched=False
    try:
        token=context.binding.backend_storage_token(context.credential,timeout=10)
        # The original service authority is the common serialization boundary:
        # even a new recovery policy/root cannot replay the same original lease.
        # The window is judged again in the same section that reserves the dispatch (the observation took time), so nothing
        # can latch the expiry between the judgment and the reservation.
        with service._critical(context.job.policy,payload,digest(manifest),deadline,table=service.RECOVERY_EXPIRED_TABLE,fail=_fail,expired_code='lease_recovery_expired') as db:
            db.execute('CREATE TABLE IF NOT EXISTS native_lease_recoveries (original_operation TEXT PRIMARY KEY,recovery_operation TEXT UNIQUE,issuer TEXT,nonce TEXT,manifest_sha256 TEXT,status TEXT,response_code INTEGER,observed_sha256 TEXT,UNIQUE(issuer,nonce))')
            if db.execute('SELECT 1 FROM native_lease_recoveries WHERE original_operation=? OR recovery_operation=? OR (issuer=? AND nonce=?)',(context.job.identifier,manifest['operation_id'],payload['issuer'],payload['nonce'])).fetchone():_fail('lease_recovery_not_replayable')
            row=db.execute('SELECT status,controller_pid,controller_start,outcome FROM jobs WHERE id=?',(context.job.identifier,)).fetchone()
            scopes=sorted(r[0] for r in db.execute('SELECT scope FROM ownership WHERE job=?',(context.job.identifier,)))
            if row[0]!=context.original['status'] or row[1] is not None or row[2] is not None or digest(parse_json(row[3]))!=context.original['outcome_sha256'] or scopes!=context.original['scopes']:_fail('lease_recovery_original_active_or_unowned')
            db.execute('INSERT INTO native_lease_recoveries VALUES (?,?,?,?,?,?,NULL,NULL)',(context.job.identifier,manifest['operation_id'],payload['issuer'],payload['nonce'],digest(manifest),'dispatch_started'))
            context.job.policy.event(db,context.job.identifier,'explicit_native_lease_recovery_dispatch',{'recovery_operation':manifest['operation_id'],'manifest_sha256':digest(manifest),'scope_released':False})
            db.execute('COMMIT');protected._sync(context.job.policy.root);dispatched=True
        policy.check();context.check()
        service._window_open(context.job.policy,payload,digest(manifest),deadline,fail=_fail,expired_code='lease_recovery_expired')  # the receipt expires no later than the manifest (verify)
        endpoint=urlsplit(context.target.blob_endpoint);path='/'+context.target.container+'/'+context.target.key+'?comp=lease'
        response=context.upstream.request(endpoint.hostname,'PUT',path,{'authorization':'Bearer '+token._get(),'accept':'application/xml','accept-encoding':'identity',
            'x-ms-version':'2023-11-03','x-ms-lease-action':'release','x-ms-lease-id':context.original['lease_id'],'if-match':fresh['state']['etag']},b'',timeout=10)
        headers=_response(response)
        if response.status!=200 or response.body:_fail('lease_recovery_release_unconfirmed')
        with context.job.policy.connection() as db:
            db.execute('UPDATE native_lease_recoveries SET status=?,response_code=? WHERE original_operation=?',('release_response_received',response.status,context.job.identifier))
        # Fresh GET confirms actual remote outcome; the response alone is not it.
        after=context.observe(root/'after',require_locked=False).verified()
        if after['state']!=fresh['state'] or after['metadata']!=fresh['metadata']:_fail('lease_recovery_readback_changed')
        result={'schema_version':'native-lease-recovery-receipt/1','status':'lease_release_independently_observed',
            'manifest_sha256':digest(manifest),'recovery_operation_id':manifest['operation_id'],'original_operation_id':context.job.identifier,
            'observation':after,'metadata_preserved':bool(after['metadata']),'backend_ready_for_new_apply':False,
            'scope_released':False,'mutation_replayed':False,'platform_qualified':False,'production_approved':False}
        protected._exclusive(root/'receipt.json',canonical(result))
        with context.job.policy.connection() as db:db.execute('UPDATE native_lease_recoveries SET status=?,observed_sha256=? WHERE original_operation=?',('release_observed',digest(after),context.job.identifier))
        return result
    except BaseException as error:
        # The durable dispatch reservation remains spent even if storage fails
        # while recording an error. Secondary recording failures cannot mask
        # the primary cancellation/error or justify replay.
        recording_errors=[]
        if dispatched:
            try:
                with context.job.policy.connection() as db:db.execute('UPDATE native_lease_recoveries SET status=? WHERE original_operation=?',('outcome_unknown',context.job.identifier))
            except BaseException as recording_error:recording_errors.append(getattr(recording_error,'code',type(recording_error).__name__))
        try:
            protected._exclusive(root/'failure.json',canonical({'status':'outcome_unknown' if dispatched else 'not_dispatched','error_code':getattr(error,'code',type(error).__name__),'recording_errors':recording_errors,'scope_released':False,'retry_authorized':False}))
        except BaseException:pass
        if isinstance(error,(AppError,KeyboardInterrupt,SystemExit)):raise
        _fail('lease_recovery_outcome_unknown' if dispatched else 'lease_recovery_not_dispatched')
    finally:
        if token is not None:token.close()


def observe_uncertain(manifest,*,context,policy,output):
    """Read-only post-timeout inspection; no retry and no scope release."""
    policy.check();context.check()
    with context.job.policy.connection() as db:
        row=db.execute('SELECT manifest_sha256,status FROM native_lease_recoveries WHERE original_operation=?',(context.job.identifier,)).fetchone()
    if row is None or row[0]!=digest(manifest) or row[1] not in ('dispatch_started','outcome_unknown','release_response_received'):_fail('lease_recovery_unknown_not_recorded')
    observation=context.observe(output,require_locked=False).verified()
    expected=manifest['observation']
    if observation['state']!=expected['state'] or observation['metadata']!=expected['metadata']:_fail('lease_recovery_readback_changed')
    with context.job.policy.connection() as db:db.execute('UPDATE native_lease_recoveries SET status=?,observed_sha256=? WHERE original_operation=?',('release_observed_execution_unknown',digest(observation),context.job.identifier))
    return {'status':'lease_release_observed_execution_unknown','observation':observation,'scope_released':False,'retry_authorized':False,'backend_ready_for_new_apply':False}


class _RecoveryCompletion:
    """Fresh authenticated evidence; never authority to transfer ownership."""
    def __init__(self,seal,*,context,observation,manifest_sha256,row,policy,recovery_state):
        if (seal is not _SEAL or type(self) not in (LiveRecoveryCompletion,LaboratoryRecoveryCompletion)
                or (type(self) is LiveRecoveryCompletion)!=(type(context) is LiveRecoveryContext)):_fail('lease_recovery_completion_required')
        self.context,self.observation,self.policy=context,observation,policy
        self.manifest_sha256,self.row=manifest_sha256,row
        self.pid=os.getpid();self.profile=context.profile
        facts=observation.verified()
        self.facts={'schema_version':'native-lease-recovery-completion/1','profile':self.profile,
            'original':facts['original'],'service_authority_root':str(context.job.policy.root),
            'current_service_policy_sha256':context.job.policy.sha256,'recovery_policy_sha256':policy.sha256,
            'recovery_operation_id':row[0],'recovery_manifest_sha256':manifest_sha256,'recovery_status':row[2],
            'recovery_observation_sha256':row[3],'fresh_observation':facts,'fresh_observation_sha256':observation.sha256,
            'recovery_state_etag':recovery_state['etag'],'completion_state_etag':facts['state']['etag'],
            'etag_changed_since_release':recovery_state['etag']!=facts['state']['etag'],
            'etag_change_cause':'unestablished' if recovery_state['etag']!=facts['state']['etag'] else 'unchanged',
            'lease_independently_unlocked':True,'lock_metadata_remaining':bool(facts['metadata']),
            'backend_ready_for_new_apply':False,'ownership_release_authorized':False,
            'platform_qualified':False,'production_approved':False}
        self.sha256=digest(self.facts)
    def __repr__(self):return '<'+type(self).__name__+' redacted>'
    def __reduce_ex__(self,protocol):raise TypeError('Recovery completion cannot be serialized.')
    def verified(self):
        if self.pid!=os.getpid() or digest(self.facts)!=self.sha256:_fail('lease_recovery_completion_changed')
        self.policy.check();facts=self.observation.verified()
        with self.context.job.policy.connection() as db:
            row=db.execute('SELECT recovery_operation,manifest_sha256,status,observed_sha256 FROM native_lease_recoveries WHERE original_operation=?',(self.context.job.identifier,)).fetchone()
        if row!=self.row or facts!=self.facts['fresh_observation']:_fail('lease_recovery_completion_changed')
        return _snapshot(self.facts)


class LiveRecoveryCompletion(_RecoveryCompletion):pass
class LaboratoryRecoveryCompletion(_RecoveryCompletion):pass


def completion(manifest,*,context,policy,output):
    """Mint process-held, read-only completion after any later native plan.

    A later normal native plan may legitimately replace/clear preserved lock
    metadata, while the exact independently observed state bytes stay unchanged.
    A current operator policy may admit the new plan. Neither event rewrites the
    historical signed recovery or permits ownership transfer on its own.
    """
    if type(context) not in (LiveRecoveryContext,LaboratoryRecoveryContext) or type(policy) is not RecoveryPolicy:_fail('lease_recovery_context_required')
    policy.check();context.check();manifest=_snapshot(manifest)
    with context.job.policy.connection() as db:
        row=db.execute('SELECT recovery_operation,manifest_sha256,status,observed_sha256 FROM native_lease_recoveries WHERE original_operation=?',(context.job.identifier,)).fetchone()
    if (row is None or row[0]!=manifest.get('operation_id') or row[1]!=digest(manifest)
            or row[2] not in ('release_observed','release_observed_execution_unknown') or not row[3]):_fail('lease_recovery_completion_unestablished')
    expected=manifest.get('observation',{})
    old=expected.get('original',{})
    if (manifest.get('profile')!=context.profile or
            {k:v for k,v in old.items() if k!='policy_sha256'}!={k:v for k,v in context.original.items() if k!='policy_sha256'}):_fail('lease_recovery_completion_original_changed')
    observation=context.observe(output,require_locked=False)
    facts=observation.verified()
    # Azure metadata writes change the blob ETag even when the state bytes do
    # not change. Completion is read-only evidence, so bind the newly observed
    # ETag while retaining every other exact state fact. This does not relax
    # execute()'s reviewed ETag/If-Match mutation gate or attribute the change.
    expected_state=expected.get('state')
    if (type(expected_state) is not dict or
            {k:v for k,v in facts['state'].items() if k!='etag'}!={k:v for k,v in expected_state.items() if k!='etag'} or
            facts['identity']!=expected.get('identity') or facts['backend_target']!=expected.get('backend_target')):
        _fail('lease_recovery_completion_state_changed')
    # Either exact preserved metadata or an independently observed empty set
    # after a normal native plan. Foreign/replaced lock metadata is not proof.
    if facts['metadata'] not in ({},expected.get('metadata')):_fail('lease_recovery_completion_metadata_changed')
    cls=LiveRecoveryCompletion if type(context) is LiveRecoveryContext else LaboratoryRecoveryCompletion
    return cls(_SEAL,context=context,observation=observation,manifest_sha256=digest(manifest),row=row,policy=policy,recovery_state=expected_state)
