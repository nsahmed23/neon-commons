"""Staged separate one-use native Plan-only verification after adoption recovery.

No import/apply permission is reused. All original job facts and ownership stay
in the common service authority until fresh typed readback proves convergence.
"""
from __future__ import annotations
import base64
from dataclasses import asdict
import hashlib
import os
from pathlib import Path
import re
import signal
import tempfile
import threading
import time
import uuid
from intune_iac import approval_authority as aa, identity_binding as ib, protected
from intune_iac import worker_service as service, worker_adoption as adoption
from intune_iac import worker_broker as broker, worker_host as host
from intune_iac.io import AppError, canonical, digest, parse_json
from intune_iac.provider_journey import _private

VERSION='native-adoption-recovery-plan/1'
APPROVAL_VERSION='signed-native-adoption-recovery-plan-approval/1'
SIGNATURE_DOMAIN=b'intune-workbench:native-adoption-recovery-plan-approval:v1\x00'
_SEAL=object()


def _fail(code):raise AppError(code,'The separately approved read-only adoption verification was not established; preserve the original unknown outcome and ownership.') from None

def _copy(value):return service._snapshot(value)

def _stable_original(value):return {key:item for key,item in value.items() if key!='policy_sha256'}

def _recovery_types():
    from intune_iac import worker_adoption_recovery as recovery
    return recovery,recovery.LiveAdoptionRecoveryCompletion,recovery.LaboratoryAdoptionRecoveryCompletion


def _completion(job,value):
    recovery,live,lab=_recovery_types()
    if type(job) is not adoption.AdoptionJob:_fail('adoption_recovery_original_required')
    expected=live if job.manifest['profile']=='azure_public_pilot' else lab
    if type(value) is not expected:_fail('adoption_recovery_completion_required')
    job._check(expiry=False);facts=value.verified();observed=facts['fresh_observation'];proof=observed['adoption_state_proof']
    if (facts['service_authority_root']!=str(job.policy.root) or
            _stable_original(facts['original'])!=_stable_original(recovery._original(job)) or
            facts['lease_independently_unlocked'] is not True or observed['locked'] is not False or
            proof['classification']!='approved_adoption_successor' or proof['graph_unchanged'] is not True or
            proof['original_contract_sha256']!=digest(job.manifest['state_contract'])):
        _fail('adoption_recovery_successor_required')
    # Initial verification has a different original-state lifecycle. It is not
    # silently folded into this new recovery approval.
    with job.policy.connection() as db:
        phase=db.execute('SELECT verification_dispatches,verification_status FROM adoption_operations WHERE operation_id=?',(job.identifier,)).fetchone()
    if phase!=(0,'not_started'):_fail('adoption_recovery_initial_verification_unqualified')
    return facts


def _provider_matches_original(original,current,state):
    old=original['provider_binding'];new=_copy(current)
    if type(new) is not dict or new.get('schema_version')!='worker-adoption-provider/1':_fail('adoption_recovery_provider_binding')
    # All immutable source/provider/principal/target inputs stay equal. Only the
    # exact independently observed state baseline changes for credential binding.
    if new.get('backend',{}).get('backend',{}).get('state_serial')!=state['serial'] or new['backend']['backend'].get('state_sha256')!=state['sha256']:
        _fail('adoption_recovery_provider_revision')
    backend_new=dict(new['backend']);backend_old=dict(old['backend'])
    target_new=dict(backend_new.pop('backend'));target_old=dict(backend_old.pop('backend'))
    for item in (target_new,target_old):
        item.pop('state_serial',None);item.pop('state_sha256',None)
    backend_new.pop('spec_sha256',None);backend_old.pop('spec_sha256',None)
    rest_new={k:v for k,v in new.items() if k not in ('backend','provider_binding_sha256')}
    rest_old={k:v for k,v in old.items() if k not in ('backend','provider_binding_sha256')}
    if rest_new!=rest_old or backend_new!=backend_old or target_new!=target_old:_fail('adoption_recovery_provider_changed')


def validate_manifest(value,*,original,require_implementation=True):
    value=_copy(value)
    fields={'schema_version','operation_id','profile','action','prepared_at','expires_at','original_operation_id','original_manifest_sha256',
        'original_facts','recovery_binding','execution_binding_sha256','host_spec','broker_policy','provider_binding','run_context',
        'run_binding_sha256','storage_binding_sha256','identity_binding_sha256','implementation_files'}
    if type(value) is not dict or set(value)!=fields or value['schema_version']!=VERSION or value['action']!='native_first_plan_only':_fail('adoption_recovery_plan_manifest')
    if type(original) is not adoption.AdoptionJob:_fail('adoption_recovery_original_required')
    original._check(expiry=False)
    if (value['original_operation_id']!=original.identifier or value['original_manifest_sha256']!=original.sha256
            or value['profile']!=original.manifest['profile'] or value['operation_id'] in (original.identifier,original.manifest['verification_operation_id'])
            or type(value['operation_id']) is not str or not service._UUID.fullmatch(value['operation_id'])):_fail('adoption_recovery_plan_identity')
    now=int(time.time())
    if (type(value['prepared_at']) is not int or type(value['expires_at']) is not int or
            not value['prepared_at']<=now+5<value['expires_at']<=value['prepared_at']+900):_fail('adoption_recovery_plan_expired')
    for key in ('execution_binding_sha256','run_binding_sha256','storage_binding_sha256','identity_binding_sha256'):service._hash(value[key])
    recovery,_,_=_recovery_types()
    if _stable_original(value['original_facts'])!=_stable_original(recovery._original(original)):_fail('adoption_recovery_original_changed')
    binding=value['recovery_binding']
    if (type(binding) is not dict or set(binding)!={'recovery_operation_id','recovery_manifest_sha256','state','projection_sha256','original_contract_sha256'}
            or binding['original_contract_sha256']!=digest(original.manifest['state_contract'])):_fail('adoption_recovery_plan_readback_binding')
    for key in ('recovery_manifest_sha256','projection_sha256','original_contract_sha256'):service._hash(binding[key])
    _provider_matches_original(original.manifest,value['provider_binding'],binding['state'])
    context=service._run_context(value['run_context']);native=value['provider_binding']
    if (context['schema_version']!='service-run-context/1' or digest(context)!=value['run_binding_sha256']
            or any(context[key]!=native.get(other) for key,other in [('source_revision','source_revision'),('source_sha256','source_sha256'),('effective_inputs_sha256','effective_input_sha256'),('provider_lock_sha256','lockfile_sha256')])):_fail('adoption_recovery_run_binding')
    prior_context=original.manifest['run_context']
    for key in ('repository','stack','component','source_revision','source_sha256','effective_inputs_sha256','provider_lock_sha256'):
        if context[key]!=prior_context[key]:_fail('adoption_recovery_run_scope_changed')
    spec=service._host_spec(value['host_spec'])
    adoption._policy_shape(value['broker_policy'],{'profile':value['profile'],'execution_binding_sha256':value['execution_binding_sha256'],
        'expires_at':value['expires_at'],'verification_operation_id':value['operation_id'],'object_ids':original.manifest['object_ids']},spec,verification=True)
    broker.validate_backend_targets(value['broker_policy'],ib.BackendSpec(**native['backend']['backend']))
    oldspec=service._host_spec(original.manifest['host_spec'])
    if spec.tools!=oldspec.tools or (spec.uid,spec.gid)!=(oldspec.uid,oldspec.gid):_fail('adoption_recovery_tool_profile_changed')
    if spec.job_root in (original.manifest['host_spec']['job_root'],original.manifest['verification_host_spec']['job_root']):_fail('adoption_recovery_fresh_host_required')
    inventory=value['implementation_files']
    if (type(inventory) is not dict or not 1<=len(inventory)<=4096 or any(type(k) is not str or type(v) is not str or not service._HASH.fullmatch(v) for k,v in inventory.items())):_fail('adoption_recovery_runtime_inventory')
    if require_implementation and inventory!=service.implementation_binding():_fail('adoption_recovery_runtime_changed')
    return value


def _projection_binding(facts):
    observed=facts['fresh_observation']
    proof=observed['adoption_state_proof']
    # Reader capture time/hash legitimately changes at each independent read.
    return digest({key:proof[key] for key in ('classification','original_contract_sha256','original_expected_semantic_sha256',
        'original_baseline_sha256','original_preimage_capture_sha256','original_preimage_raw_sha256','fresh_raw_sha256','reader_identity_sha256')})


def _binding(facts):
    return {'recovery_operation_id':facts['recovery_operation_id'],'recovery_manifest_sha256':facts['recovery_manifest_sha256'],
        'state':facts['fresh_observation']['state'],'projection_sha256':_projection_binding(facts),
        'original_contract_sha256':facts['fresh_observation']['adoption_state_proof']['original_contract_sha256']}


def make_manifest(*,original,completion,operation_id,expires_at,execution_binding_sha256,host_spec,broker_policy,
        provider_binding,run_context,storage_binding_sha256,identity_binding_sha256):
    facts=_completion(original,completion)
    if type(host_spec) is not host.HostSpec:_fail('adoption_recovery_host_required')
    return validate_manifest({'schema_version':VERSION,'operation_id':operation_id,'profile':original.manifest['profile'],
        'action':'native_first_plan_only','prepared_at':int(time.time()),'expires_at':expires_at,
        'original_operation_id':original.identifier,'original_manifest_sha256':original.sha256,'original_facts':facts['original'],
        'recovery_binding':_binding(facts),'execution_binding_sha256':execution_binding_sha256,'host_spec':asdict(host_spec),
        'broker_policy':broker_policy,'provider_binding':provider_binding,'run_context':run_context,'run_binding_sha256':digest(run_context),
        'storage_binding_sha256':storage_binding_sha256,'identity_binding_sha256':identity_binding_sha256,
        'implementation_files':service.implementation_binding()},original=original)


def _verify(policy,manifest,receipt):
    policy.check();receipt=_copy(receipt)
    if type(receipt) is not dict or set(receipt)!={'payload','signature'}:_fail('adoption_recovery_signature_shape')
    payload=receipt['payload']
    if (type(payload) is not dict or set(payload)!={'schema_version','issuer','key_id','approver_id','operation_id','manifest_sha256','issued_at','expires_at','nonce'}
            or payload['schema_version']!=APPROVAL_VERSION or payload['operation_id']!=manifest['operation_id'] or payload['manifest_sha256']!=digest(manifest)
            or type(payload['nonce']) is not str or not re.fullmatch('[0-9a-f]{32}',payload['nonce'])):_fail('adoption_recovery_signature_binding')
    now=int(time.time())
    if (type(payload['issued_at']) is not int or type(payload['expires_at']) is not int or
            not manifest['prepared_at']<=payload['issued_at']<=now+5 or not now<payload['expires_at']<=manifest['expires_at']):_fail('adoption_recovery_signature_expired')
    if any(type(payload[k]) is not str for k in ('issuer','key_id','approver_id')):_fail('adoption_recovery_signer_invalid')
    signer=policy.approvers.get((payload['issuer'],payload['key_id']))
    if not signer or signer['approver_id']!=payload['approver_id'] or manifest['profile'] not in signer['profiles']:_fail('adoption_recovery_signer_invalid')
    try:signature=base64.b64decode(receipt['signature'],validate=True)
    except (TypeError,ValueError):_fail('adoption_recovery_signature_invalid')
    if len(signature)!=64 or base64.b64encode(signature).decode()!=receipt['signature']:_fail('adoption_recovery_signature_invalid')
    fd=os.open(protected._path(policy.verifier.executable),os.O_RDONLY|os.O_NOFOLLOW);primary=None
    try:
        with os.fdopen(os.dup(fd),'rb') as stream:
            if hashlib.file_digest(stream,'sha256').hexdigest()!=policy.verifier.sha256:_fail('adoption_recovery_verifier_changed')
        with tempfile.TemporaryDirectory(prefix='adoption-recovery-signature-',dir=policy.root) as temporary:
            root=Path(temporary)
            for name,raw in [('key.der',aa._SPKI+bytes.fromhex(signer['public_key_hex'])),('message',SIGNATURE_DOMAIN+canonical(payload)),('signature',signature)]:protected._exclusive(root/name,raw)
            protected._supervise([str(policy.verifier.executable),'pkeyutl','-verify','-pubin','-keyform','DER','-inkey',str(root/'key.der'),'-rawin','-in',str(root/'message'),'-sigfile',str(root/'signature')],cwd=root,
                env={'PATH':'/usr/bin:/bin','HOME':str(root),'OPENSSL_CONF':'/dev/null'},pass_fds=(fd,),executable='/proc/self/fd/'+str(fd),timeout=5,output_limit=4096)
    except BaseException as error:
        primary=error
        if isinstance(error,AppError):
            primary=AppError('adoption_recovery_signature_invalid','The separately signed Plan approval could not be verified.')
            raise primary from error
        raise
    finally:
        try:os.close(fd)
        except BaseException as secondary:
            if primary is None:raise
            adoption._secondary(primary,secondary,'signature descriptor cleanup')
    return payload


def _tables(policy):
    with policy.connection() as db:
        db.execute('CREATE TABLE IF NOT EXISTS adoption_recovery_plans (operation_id TEXT PRIMARY KEY,original_operation_id TEXT NOT NULL,manifest_sha256 TEXT NOT NULL,root TEXT UNIQUE NOT NULL,status TEXT NOT NULL,cancelled INTEGER NOT NULL DEFAULT 0,dispatches INTEGER NOT NULL DEFAULT 0,outcome TEXT,controller_pid INTEGER,controller_start TEXT)')


class RecoveryPlanRuntime:
    def __init__(self,seal,*,profile,run,storage,binding,credentials,upstream,certificate,private_key,provider):
        from intune_iac.worker_adoption_provider import NativeAdoptionProviderAdapter
        if (seal is not _SEAL or type(self) is not RecoveryPlanRuntime or type(run) is not service.ControllerBinding or run.kind!='run'
                or type(storage) is not service.ControllerBinding or storage.kind!='storage' or type(credentials) is not broker.BrokerCredentials
                or credentials.binding is not binding or type(provider) is not NativeAdoptionProviderAdapter):_fail('adoption_recovery_runtime_required')
        self.profile,self.run,self.storage,self.binding,self.credentials=profile,run,storage,binding,credentials
        self.upstream,self.certificate,self.private_key,self.provider=upstream,certificate,private_key,provider;self.pid=os.getpid()
    def __reduce_ex__(self,protocol):raise TypeError('Recovery Plan runtime cannot be serialized.')
    def check(self,manifest):
        live=self.profile=='azure_public_pilot'
        if (self.pid!=os.getpid() or self.profile!=manifest['profile'] or type(self.binding) is not (ib.LiveIdentityBinding if live else ib.LaboratoryIdentityBinding)
                or type(self.upstream) is not (broker.NativeUpstream if live else broker.LaboratoryUpstream)):_fail('adoption_recovery_runtime_profile')
        self.run.check(manifest['run_binding_sha256']);self.storage.check(manifest['storage_binding_sha256']);self.binding.assert_fresh(manifest['identity_binding_sha256'])
        if self.provider.binding()!=manifest['provider_binding']:_fail('adoption_recovery_provider_changed')
        self.credentials.check(manifest['broker_policy'])
        identity,target=self.binding.backend_configuration(self.credentials.backend_credential)
        if asdict(identity)!=manifest['provider_binding']['backend']['identity'] or asdict(target)!=manifest['provider_binding']['backend']['backend']:_fail('adoption_recovery_identity_changed')
        spec=service._host_spec(manifest['host_spec']);key=_private(self.private_key)
        for directory in (spec.source_root,spec.control_root,spec.job_root,spec.broker_root):
            if key==Path(directory) or Path(directory) in key.parents:_fail('adoption_recovery_private_key_visible')
        if any(key==Path(tool.path) for tool in spec.tools):_fail('adoption_recovery_private_key_visible')
        if host._hash_file(self.certificate,1024*1024)!=spec.broker_ca_sha256:_fail('adoption_recovery_certificate_changed')
        for root,sha,files in ((spec.source_root,spec.source_sha256,self.provider.source_files()),
                (spec.control_root,spec.control_sha256,dict(self.provider.control_files('first-plan',credentials=self.credentials),**{'broker-ca.pem':_private(self.certificate).read_bytes()}))):
            actual=host.directory_binding(root)
            if actual['sha256']!=sha or set(actual['files'])!=set(files) or any(actual['files'][name]['sha256']!=hashlib.sha256(raw).hexdigest() for name,raw in files.items()):_fail('adoption_recovery_payload_changed')


def laboratory_runtime(**kwargs):return RecoveryPlanRuntime(_SEAL,profile='native_docker_laboratory_protocol',**kwargs)
def live_runtime(**kwargs):
    ib.require_live_binding(kwargs.get('binding'));return RecoveryPlanRuntime(_SEAL,profile='azure_public_pilot',upstream=broker.NativeUpstream(),**kwargs)


def _original_row(db,original,facts):
    row=db.execute('SELECT status,cancelled,dispatches,outcome,controller_pid,controller_start,root,manifest_sha256 FROM jobs WHERE id=?',(original.identifier,)).fetchone()
    consumed=db.execute('SELECT manifest_sha256 FROM consumed WHERE operation_id=?',(original.identifier,)).fetchone()
    scopes=sorted(item[0] for item in db.execute('SELECT scope FROM ownership WHERE job=?',(original.identifier,)))
    if (row is None or row[0]!=facts['status'] or bool(row[1])!=facts['cancelled'] or row[2]!=1
            or row[4:6]!=(None,None) or row[6:]!=(str(original.root),original.sha256)
            or consumed!=(original.sha256,) or scopes!=service._scopes(original.manifest)
            or not row[3] or digest(parse_json(row[3]))!=facts['outcome_sha256']):
        _fail('adoption_recovery_original_changed')


def prepare_job(root,*,original,manifest,policy_path):
    policy=service.ServicePolicy(policy_path)
    if type(original) is not adoption.AdoptionJob or original.policy.root!=policy.root or original.policy.database!=policy.database:_fail('adoption_recovery_same_authority_required')
    original=adoption.AdoptionJob(original.root,policy_path);manifest=validate_manifest(manifest,original=original,require_implementation=False)
    if digest(manifest) not in policy.admitted:_fail('adoption_recovery_plan_not_admitted')
    _tables(policy);root=Path(root).absolute()
    if root.parent!=policy.jobs_root:_fail('adoption_recovery_plan_outside_policy')
    root.mkdir(mode=0o700,exist_ok=False);protected._exclusive(root/'manifest.json',canonical(manifest));protected._exclusive(root/'original.json',canonical({'root':str(original.root),'manifest_sha256':original.sha256}));protected._exclusive(root/'policy-binding.json',canonical({'policy_sha256':policy.sha256}))
    with policy.connection() as db:
        db.execute('BEGIN IMMEDIATE');_original_row(db,original,manifest['original_facts'])
        if db.execute("SELECT 1 FROM adoption_recovery_plans WHERE original_operation_id=? AND (controller_pid IS NOT NULL OR status!='cancelled_before_dispatch')",(original.identifier,)).fetchone():_fail('adoption_recovery_plan_conflict')
        db.execute('INSERT INTO adoption_recovery_plans(operation_id,original_operation_id,manifest_sha256,root,status) VALUES (?,?,?,?,?)',(manifest['operation_id'],original.identifier,digest(manifest),str(root),'prepared'))
        policy.event(db,original.identifier,'adoption_recovery_plan_prepared',{'operation_id':manifest['operation_id'],'manifest_sha256':digest(manifest),'job_root':str(root),'policy_path':str(policy.path),'import_replayed':False});db.execute('COMMIT')
    protected._sync(policy.root);return RecoveryPlanJob(root,policy_path).status()


class _Permit:
    def __init__(self,job,payload,runtime):self.job,self.payload,self.runtime=job,payload,runtime;self.pid=os.getpid();self.active=True
    def check_active(self):
        if not self.active or self.pid!=os.getpid():_fail('adoption_recovery_permit_inactive')
        self.job._check();self.runtime.check(self.job.manifest)
        with self.job.policy.connection() as db:
            row=db.execute('SELECT status,cancelled,dispatches,controller_pid,controller_start FROM adoption_recovery_plans WHERE operation_id=?',(self.job.identifier,)).fetchone()
            used=db.execute('SELECT manifest_sha256 FROM consumed WHERE operation_id=?',(self.job.identifier,)).fetchone()
            revoked=db.execute('SELECT 1 FROM revoked WHERE issuer=? AND key_id=?',(self.payload['issuer'],self.payload['key_id'])).fetchone()
        if row!=('running',0,1,os.getpid(),service._controller_identity(os.getpid())) or used!=(self.job.sha256,) or revoked:_fail('adoption_recovery_permit_revoked')
        if int(time.time())>=self.payload['expires_at']:_fail('adoption_recovery_plan_expired')


class RecoveryPlanJob:
    def __init__(self,root,policy_path):
        self.policy=service.ServicePolicy(policy_path);self.root=_private(root,directory=True)
        if self.root.parent!=self.policy.jobs_root:_fail('adoption_recovery_plan_outside_policy')
        self.manifest=service._bounded_private_json(self.root/'manifest.json')
        if self.manifest.get('schema_version')!=VERSION:_fail('adoption_recovery_plan_domain')
        self.identifier=self.manifest['operation_id'];self.sha256=digest(self.manifest);self._completed_capture=None
        reference=service._bounded_private_json(self.root/'original.json');self.original=adoption.AdoptionJob(reference['root'],policy_path)
        if reference!={'root':str(self.original.root),'manifest_sha256':self.original.sha256}:_fail('adoption_recovery_original_changed')
        self._check(expiry=False)
    def _check(self,*,expiry=True):
        self.policy.check();self.original._check(expiry=False)
        if digest(self.manifest)!=self.sha256 or service._bounded_private_json(self.root/'manifest.json')!=self.manifest:_fail('adoption_recovery_plan_changed')
        with self.policy.connection() as db:
            row=db.execute('SELECT original_operation_id,manifest_sha256,root FROM adoption_recovery_plans WHERE operation_id=?',(self.identifier,)).fetchone()
        if row!=(self.original.identifier,self.sha256,str(self.root)):_fail('adoption_recovery_plan_not_registered')
        if expiry:
            if self.sha256 not in self.policy.admitted or service._bounded_private_json(self.root/'policy-binding.json')!={'policy_sha256':self.policy.sha256}:_fail('adoption_recovery_admission_changed')
            validate_manifest(self.manifest,original=self.original)
    def review(self):self._check(expiry=False);return {'manifest':self.manifest,'manifest_sha256':self.sha256,'signature_domain_hex':SIGNATURE_DOMAIN.hex(),'execution_authorized':False,'import_replay_authorized':False}
    def status(self):
        self._check(expiry=False)
        with self.policy.connection() as db:
            row=db.execute('SELECT status,cancelled,dispatches,outcome FROM adoption_recovery_plans WHERE operation_id=?',(self.identifier,)).fetchone()
        return {'operation_id':self.identifier,'manifest_sha256':self.sha256,'original_operation_id':self.original.identifier,'status':row[0],'cancel_requested':bool(row[1]),'dispatches':row[2],
            'outcome':parse_json(row[3]) if row[3] else None,'original':self.original.status(),'import_replay_authorized':False,'graph_mutation_authorized':False,'production_approved':False}
    def attach(self):return self.status()
    def cancel(self):
        self._check(expiry=False)
        with self.policy.connection() as db:
            db.execute('BEGIN IMMEDIATE');db.execute("UPDATE adoption_recovery_plans SET cancelled=1,status=CASE WHEN dispatches=0 THEN 'cancelled_before_dispatch' ELSE status END WHERE operation_id=?",(self.identifier,))
            self.policy.event(db,self.original.identifier,'adoption_recovery_plan_cancel_requested',{'operation_id':self.identifier,'ownership_released':False});db.execute('COMMIT')
        return self.status()
    def recover(self):
        self.cancel()
        with self.policy.connection() as db:row=db.execute('SELECT controller_pid,controller_start FROM adoption_recovery_plans WHERE operation_id=?',(self.identifier,)).fetchone()
        if row[0] is not None and service._controller_identity(row[0])==row[1]:_fail('adoption_recovery_controller_active')
        result=host.recover(self.root/'host-run') if (self.root/'host-run/journal.json').exists() else {'container_never_recorded':True}
        with self.policy.connection() as db:
            db.execute('BEGIN IMMEDIATE');db.execute("UPDATE adoption_recovery_plans SET controller_pid=NULL,controller_start=NULL,status=CASE WHEN status='running' THEN 'outcome_unknown' ELSE status END WHERE operation_id=?",(self.identifier,))
            self.policy.event(db,self.original.identifier,'adoption_recovery_plan_stopped_no_replay',{'operation_id':self.identifier,'host':result,'ownership_released':False});db.execute('COMMIT')
        return self.status()
    def run(self,signed,*,runtime,completion):
        receipt=_copy(signed);self._check()
        if threading.current_thread() is not threading.main_thread() or type(runtime) is not RecoveryPlanRuntime:_fail('adoption_recovery_runtime_required')
        runtime.check(self.manifest);facts=_completion(self.original,completion)
        if _binding(facts)!=self.manifest['recovery_binding'] or facts['fresh_observation']['identity_binding_sha256']!=self.manifest['identity_binding_sha256']:_fail('adoption_recovery_precondition_changed')
        payload=_verify(self.policy,self.manifest,receipt);raw=canonical(receipt);spec=service._host_spec(self.manifest['host_spec'])
        for directory in (spec.job_root,spec.broker_root):
            if list(_private(directory,directory=True).iterdir()):_fail('adoption_recovery_fresh_host_required')
        with self.policy.connection() as db:
            db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT status,cancelled,dispatches FROM adoption_recovery_plans WHERE operation_id=?',(self.identifier,)).fetchone()
            if row!=('prepared',0,0):_fail('adoption_recovery_plan_not_replayable')
            _original_row(db,self.original,self.manifest['original_facts'])
            owners=sorted(r[0] for r in db.execute('SELECT scope FROM ownership WHERE job=?',(self.original.identifier,)))
            if owners!=service._scopes(self.original.manifest):_fail('adoption_recovery_original_unowned')
            if db.execute('SELECT 1 FROM revoked WHERE issuer=? AND key_id=?',(payload['issuer'],payload['key_id'])).fetchone():_fail('adoption_recovery_signer_revoked')
            identity=service._controller_identity(os.getpid())
            if identity is None:_fail('adoption_recovery_controller_identity')
            db.execute('INSERT INTO consumed VALUES (?,?,?,?)',(payload['issuer'],payload['nonce'],self.identifier,self.sha256))
            db.execute('INSERT INTO approval_transcripts VALUES (?,?,?,?)',(self.identifier,raw.decode(),hashlib.sha256(raw).hexdigest(),int(time.time())))
            db.execute("UPDATE adoption_recovery_plans SET status='running',dispatches=1,controller_pid=?,controller_start=? WHERE operation_id=?",(os.getpid(),identity,self.identifier))
            self.policy.event(db,self.original.identifier,'adoption_recovery_plan_consumed',{'operation_id':self.identifier,'manifest_sha256':self.sha256,'receipt_sha256':hashlib.sha256(raw).hexdigest(),'state_content_write_authorized':False});db.execute('COMMIT')
        return self._dispatch(payload,runtime,spec,raw)
    def _dispatch(self,payload,runtime,spec,receipt_raw):
        permit=_Permit(self,payload,runtime);server=thread=watchdog=transport=result=primary=interruption=None
        stopped=threading.Event();faults=[];shutdown=[];recording=[];uncertain=False
        def secondary(error,phase,target):
            nonlocal primary,interruption
            target.append({'phase':phase,'error':str(getattr(error,'code',type(error).__name__))})
            if primary is None:primary=error
            if isinstance(error,(KeyboardInterrupt,SystemExit)) and interruption is None:interruption=error
        def join(value,seconds,phase):
            if value is None:return
            try:
                value.join(timeout=seconds)
                if value.is_alive():_fail('adoption_recovery_thread_active')
            except BaseException as error:secondary(error,phase,shutdown)
        try:
            protected._exclusive(self.root/'approval.json',receipt_raw);permit.check_active()
            guard=(broker.live_guard(self.manifest['execution_binding_sha256'],binding=runtime.binding,recheck=permit.check_active)
                if runtime.profile=='azure_public_pilot' else broker.laboratory_guard(self.manifest['execution_binding_sha256'],permit.check_active))
            transport=broker.EgressBroker(self.manifest['broker_policy'],journal=self.root/'broker.sqlite3',guard=guard,upstream=runtime.upstream,credentials=runtime.credentials)
            server=broker.UnixBrokerServer(Path(spec.broker_root)/'egress.sock',transport,certificate=runtime.certificate,private_key=runtime.private_key)
            thread=threading.Thread(target=server.serve,daemon=True,name='adoption-recovery-plan-broker');thread.start()
            def monitor():
                while not stopped.wait(.2):
                    try:permit.check_active()
                    except BaseException as error:
                        faults.append(str(getattr(error,'code',type(error).__name__)))
                        if not stopped.is_set():os.kill(os.getpid(),signal.SIGINT)
                        return
            watchdog=threading.Thread(target=monitor,daemon=True,name='adoption-recovery-plan-watchdog');watchdog.start()
            permit.check_active();result=host.launch(spec,self.root/'host-run')
        except BaseException as error:
            primary=error
            if isinstance(error,(KeyboardInterrupt,SystemExit)):interruption=error
            try:
                if (self.root/'host-run/receipt.json').exists():result=service._bounded_private_json(self.root/'host-run/receipt.json')
            except BaseException as other:secondary(other,'host_receipt',recording)
        finally:
            stopped.set();permit.active=False;join(watchdog,35,'watchdog_join')
            if server is not None:
                try:server.close()
                except BaseException as error:secondary(error,'broker_close',shutdown)
            join(thread,12,'broker_join')
            lease=None
            if transport is not None:
                try:
                    value=transport.native_recovery_record();protected._exclusive(self.root/'native-lease-recovery.json',canonical(value));lease={'sha256':digest(value),'automatic_release_authorized':False}
                except BaseException as error:secondary(error,'lease_record',recording)
            complete=bool(result and result.get('status')=='complete' and primary is None and not shutdown and not recording)
            status='plan_host_completed_unverified' if complete else 'outcome_unknown'
            report={'host':result,'status':status,'primary_error':str(getattr(primary,'code',type(primary).__name__)) if primary else None,
                'shutdown_failures':shutdown,'recording_failures':recording,'watchdog_error':faults[0] if faults else None,
                'native_backend_recovery':lease,'authority_recording':'committed','original_ownership_retained':True,
                'import_replayed':False,'graph_mutation_authorized':False,'state_content_write_authorized':False}
            try:
                with self.policy.connection() as db:
                    db.execute('BEGIN IMMEDIATE');db.execute('UPDATE adoption_recovery_plans SET status=?,outcome=?,controller_pid=NULL,controller_start=NULL WHERE operation_id=?',(status,canonical(report).decode(),self.identifier))
                    self.policy.event(db,self.original.identifier,'adoption_recovery_plan_stopped',dict(report,operation_id=self.identifier));db.execute('COMMIT')
            except BaseException as error:uncertain=True;secondary(error,'authority_outcome',recording);report['authority_recording']='failed_or_uncertain'
            try:protected._exclusive(self.root/'receipt.json',canonical(report))
            except BaseException as error:
                secondary(error,'receipt_archive',recording)
                try:
                    with self.policy.connection() as db:self.policy.event(db,self.original.identifier,'adoption_recovery_plan_archive_failed',{'operation_id':self.identifier,'error':str(getattr(error,'code',type(error).__name__)),'known_outcome_preserved':not uncertain})
                except BaseException as other:uncertain=True;secondary(other,'archive_failure_event',recording)
        if primary is not None:primary.adoption_recovery_failure_record=report
        if interruption is not None and (not faults or shutdown or recording):
            if interruption is primary:raise interruption
            raise interruption from primary
        if uncertain:raise primary
        try:return self.status()
        except BaseException as error:
            if primary is None:raise
            adoption._secondary(primary,error,'final recovery status');raise primary from error

    def reconcile(self,completion):
        """Only fresh sealed backend/Graph proof plus this exact no-op plan release."""
        self._check(expiry=False);facts=_completion(self.original,completion)
        expected=self.manifest['recovery_binding'];actual=_binding(facts)
        if (actual['recovery_operation_id']!=expected['recovery_operation_id'] or actual['recovery_manifest_sha256']!=expected['recovery_manifest_sha256']
                or actual['projection_sha256']!=expected['projection_sha256'] or actual['original_contract_sha256']!=expected['original_contract_sha256']
                or {k:v for k,v in actual['state'].items() if k!='etag'}!={k:v for k,v in expected['state'].items() if k!='etag'}
                or facts['lock_metadata_remaining'] is not False or facts['fresh_observation']['metadata']):_fail('adoption_recovery_final_readback_changed')
        plan=self._plan_evidence();capture=completion.captured_observation()
        with self.policy.connection() as db:
            db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT status,dispatches,outcome,controller_pid,controller_start FROM adoption_recovery_plans WHERE operation_id=?',(self.identifier,)).fetchone()
            old=db.execute('SELECT status,dispatches,outcome,controller_pid,controller_start FROM jobs WHERE id=?',(self.original.identifier,)).fetchone()
            owners=sorted(r[0] for r in db.execute('SELECT scope FROM ownership WHERE job=?',(self.original.identifier,)))
            used=db.execute('SELECT manifest_sha256 FROM consumed WHERE operation_id=?',(self.identifier,)).fetchone()
            if (row is None or row[0:2]!=('plan_host_completed_unverified',1) or row[3:]!=(None,None)
                    or used!=(self.sha256,) or old[1]!=1 or old[3:]!=(None,None) or owners!=service._scopes(self.original.manifest)
                    or old[0]!=facts['original']['status'] or digest(parse_json(old[2]))!=facts['original']['outcome_sha256']):_fail('adoption_recovery_reconciliation_not_ready')
            _original_row(db,self.original,facts['original'])
            outcome=parse_json(row[2]);host_result=outcome.get('host')
            if not isinstance(host_result,dict) or host_result.get('cleanup',{}).get('removed') is not True or host_result['cleanup'].get('stopped_state',{}).get('Running') is not False:_fail('adoption_recovery_host_cleanup_unconfirmed')
            host_manifest=service._bounded_private_json(self.root/'host-run/manifest.json');host_receipt=service._bounded_private_json(self.root/'host-run/receipt.json')
            host_envelope=_copy(host_result)
            if 'receipt' in host_envelope and host_envelope.pop('receipt')!=str(self.root/'host-run/receipt.json'):
                _fail('adoption_recovery_host_receipt_changed')
            if (host_manifest.get('host_spec')!=self.manifest['host_spec'] or digest(host_manifest)!=host_result.get('manifest_sha256') or host_receipt!=host_envelope):_fail('adoption_recovery_host_receipt_changed')
            report={'schema_version':'adoption-recovery-plan-convergence/1','original_operation_id':self.original.identifier,
                'original_manifest_sha256':self.original.sha256,'recovery_plan_operation_id':self.identifier,'recovery_plan_manifest_sha256':self.sha256,
                'previous_import_outcome':parse_json(old[2]),'previous_import_status':old[0],'first_plan_outcome':outcome,
                'independent_completion':facts,'native_first_plan':plan,'reservation_released':True,'import_replayed':False,
                'original_execution_outcome':'unknown','graph_mutated':False,'endpoint_effectiveness':'unestablished','production_approved':False}
            db.execute("UPDATE jobs SET status='adopted_verified_execution_unknown',outcome=? WHERE id=?",(canonical(report).decode(),self.original.identifier))
            db.execute("UPDATE adoption_recovery_plans SET status='reconciled',outcome=? WHERE operation_id=?",(canonical(report).decode(),self.identifier))
            db.execute('DELETE FROM ownership WHERE job=?',(self.original.identifier,))
            self.policy.event(db,self.original.identifier,'adoption_recovery_plan_reconciled',report);db.execute('COMMIT')
        self._completed_capture=(capture,digest(report))
        protected._sync(self.policy.root)
        try:protected._exclusive(self.root/('reconciliation-'+uuid.uuid4().hex+'.json'),canonical(report))
        except BaseException as error:
            try:
                with self.policy.connection() as db:self.policy.event(db,self.original.identifier,'adoption_recovery_reconciliation_archive_failed',{'operation_id':self.identifier,'known_outcome_preserved':True,'error':str(getattr(error,'code',type(error).__name__))})
            except BaseException as other:adoption._secondary(error,other,'reconciliation archive')
            raise
        return self.status()

    def captured_observation(self):
        # The completion context intentionally stops validating once its original
        # job transitions. Retain only the already verified fresh capture, bound
        # to the exact durable reconciliation; reopening cannot mint it.
        if self._completed_capture is None:_fail('adoption_recovery_capture_not_held')
        capture,report_sha=self._completed_capture
        from intune_iac.observation_reader import CapturedObservation
        if type(capture) is not CapturedObservation:_fail('adoption_recovery_capture_required')
        self._check(expiry=False)
        with self.policy.connection() as db:
            row=db.execute('SELECT status,outcome FROM adoption_recovery_plans WHERE operation_id=?',(self.identifier,)).fetchone()
        if row[0]!='reconciled' or digest(parse_json(row[1]))!=report_sha:_fail('adoption_recovery_capture_binding_changed')
        capture.verified();return capture

    def _plan_evidence(self):
        from intune_iac import worker_adoption_provider as provider
        root=Path(self.manifest['host_spec']['job_root']);paths=[root/part.removeprefix('/job/') for part in (provider.PLAN_PATH,provider.PLAN_JSON_PATH,provider.PLAN_EXIT_PATH)]
        pins={str(path):host._hash_file(path,32*1024*1024) for path in paths}
        if _private(paths[2]).read_bytes()!=b'0\n':_fail('adoption_recovery_plan_changes_or_failure')
        plan=parse_json(_private(paths[1]).read_bytes())
        if (type(plan) is not dict or plan.get('format_version')!='1.2' or plan.get('terraform_version')!='1.13.1' or plan.get('errored') is True
                or plan.get('resource_drift') not in (None,[]) or type(plan.get('resource_changes')) is not list or len(plan['resource_changes'])!=1
                or plan['resource_changes'][0].get('address')!=self.original.manifest['provider_binding']['resource_address']
                or plan['resource_changes'][0].get('change',{}).get('actions')!=['no-op']
                or any(change.get('actions')!=['no-op'] for change in plan.get('output_changes',{}).values())):_fail('adoption_recovery_plan_not_converged')
        return {'first_plan_no_change':True,'exit_code':0,'artifacts':pins,'binary_sha256':pins[str(paths[0])],'json_sha256':pins[str(paths[1])],
            'graph_state_content_write_authorized':False,'scope':'actual closed native first-plan/show; no import or apply'}
