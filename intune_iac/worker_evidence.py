"""Portable bounded worker evidence; signatures and storage are host capabilities.

No execution permit, network route, native host support or trust-on-first-use.
"""
from __future__ import annotations
import base64
from contextlib import contextmanager
import hashlib
from pathlib import PurePosixPath
import re
import time
from . import clock
from .io import AppError, canonical, digest, parse_json

DOMAIN=b'intune-workbench:worker-evidence:v1\x00'
APPROVAL_DOMAIN=b'intune-workbench:worker-service-approval:v1\x00'
MAX_BYTES=16*1024*1024
MAX_CAPTURE=9*1024*1024
PROFILES={'native_docker_laboratory_tls','native_docker_laboratory_protocol','azure_public_pilot'}
HASH=re.compile('[a-f0-9]{64}\\Z');UUID=re.compile('[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}\\Z')
LABEL=re.compile('[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\\Z');REV=re.compile('[a-f0-9]{40}\\Z')
_SEAL=object()


def fail(code):raise AppError(code,'The signed worker evidence, exact request or independent readback did not establish its contract.')
def shape(value,fields):
    if type(value) is not dict or set(value)!=set(fields.split()):fail('worker_evidence_shape')
def hashed(value):
    if type(value) is not str or not HASH.fullmatch(value):fail('worker_evidence_hash')
    return value
def identifier(value):
    if type(value) is not str or not UUID.fullmatch(value):fail('worker_evidence_identity')
    return value
def number(value,low,high):
    if type(value) is not int or not low<=value<=high:fail('worker_evidence_number')
    return value
def label(value):
    if type(value) is not str or not LABEL.fullmatch(value):fail('worker_evidence_label')
    return value
def bounded(value):
    pending=[(value,0)];nodes=0
    while pending:
        item,depth=pending.pop();nodes+=1
        if depth>64 or nodes>200000:fail('worker_evidence_limit')
        if type(item) is dict:
            if any(type(key) is not str for key in item):fail('worker_evidence_shape')
            pending.extend((child,depth+1) for child in item.values())
        elif type(item) is list:pending.extend((child,depth+1) for child in item)
        elif type(item) not in (str,int,float,bool,type(None)):fail('worker_evidence_shape')
    try:raw=canonical(value)
    except (ValueError,TypeError,RecursionError,UnicodeError):fail('worker_evidence_shape')
    if len(raw)>MAX_BYTES:fail('worker_evidence_limit')
    return parse_json(raw)
def signature(value):
    try:raw=base64.b64decode(value,validate=True)
    except (ValueError,TypeError):fail('worker_evidence_signature')
    if len(raw)!=64 or base64.b64encode(raw).decode()!=value:fail('worker_evidence_signature')
    return raw


def trust(value):
    value=bounded(value)
    shape(value,'schema_version publishers approvers revoked max_age_seconds max_lifetime_seconds clock_skew_seconds')
    if value['schema_version']!='worker-evidence-trust/1':fail('worker_evidence_trust')
    for key in ('max_age_seconds','max_lifetime_seconds'):number(value[key],1,900)
    number(value['clock_skew_seconds'],0,5)
    for role,identity in [('publishers','publisher_id'),('approvers','approver_id')]:
        rows=value[role]
        if type(rows) is not list or not 1<=len(rows)<=32:fail('worker_evidence_trust')
        seen=set()
        for row in rows:
            shape(row,'issuer key_id '+identity+' public_key_hex profiles tenant_ids object_ids')
            for key in ('issuer','key_id',identity):label(row[key])
            hashed(row['public_key_hex'])
            pair=(row['issuer'],row['key_id'])
            if pair in seen:fail('worker_evidence_duplicate_key')
            seen.add(pair)
            if type(row['profiles']) is not list or not row['profiles'] or len(set(row['profiles']))!=len(row['profiles']) or not set(row['profiles'])<=PROFILES:fail('worker_evidence_trust')
            for key in ('tenant_ids','object_ids'):
                if type(row[key]) is not list or not 1<=len(row[key])<=100 or len(set(row[key]))!=len(row[key]):fail('worker_evidence_trust')
                for item in row[key]:identifier(item)
    if type(value['revoked']) is not list or len(value['revoked'])>64:fail('worker_evidence_trust')
    for row in value['revoked']:
        shape(row,'issuer key_id purpose');label(row['issuer']);label(row['key_id'])
        if row['purpose'] not in ('publisher','approver'):fail('worker_evidence_trust')
    return value


def request(value):
    if type(value) is dict and value.get('schema_version')=='worker-evidence-request/2':
        from .worker_evidence_domains import request as domain_request
        return domain_request(value)
    shape(value,'schema_version nonce tenant_id object_id operation_id manifest_sha256 saved_plan_sha256 execution_binding_sha256 run_binding_sha256 source_revision source_sha256 run_id run_attempt trust_sha256')
    if value['schema_version']!='worker-evidence-request/1':fail('worker_evidence_request')
    if type(value['nonce']) is not str or not re.fullmatch('[a-f0-9]{32}',value['nonce']):fail('worker_evidence_nonce')
    for key in ('tenant_id','object_id','operation_id'):identifier(value[key])
    for key in ('manifest_sha256','saved_plan_sha256','execution_binding_sha256','run_binding_sha256','source_sha256','trust_sha256'):hashed(value[key])
    if type(value['source_revision']) is not str or not REV.fullmatch(value['source_revision']):fail('worker_evidence_revision')
    label(value['run_id']);number(value['run_attempt'],1,1000)
    return value


def make_request(manifest,policy,nonce):
    policy=trust(policy);context=manifest['run_context']
    if manifest.get('schema_version') in ('native-state-adoption/1','native-adoption-recovery-plan/1','native-adoption-recovery-plan/2','native-adoption-recovery-plan/3'):
        from .worker_evidence_domains import make_request as domain_request
        return domain_request(manifest,policy,nonce)
    if manifest.get('action')!='apply_saved_plan' or len(manifest.get('object_ids',[]))!=1 or context.get('schema_version')!='service-run-context/1':fail('worker_evidence_action_unsupported')
    return request({'schema_version':'worker-evidence-request/1','nonce':nonce,'tenant_id':manifest['tenant_id'],
        'object_id':manifest['object_ids'][0],'operation_id':manifest['operation_id'],'manifest_sha256':digest(manifest),
        'saved_plan_sha256':manifest['saved_plan_sha256'],'execution_binding_sha256':manifest['execution_binding_sha256'],
        'run_binding_sha256':manifest['run_binding_sha256'],'source_revision':context['source_revision'],
        'source_sha256':context['source_sha256'],'run_id':context['run_id'],'run_attempt':context['run_attempt'],'trust_sha256':digest(policy)})


def scoped_key(policy,role,payload,req,profile):
    identity='publisher_id' if role=='publishers' else 'approver_id';purpose='publisher' if role=='publishers' else 'approver'
    rows=[r for r in policy[role] if all(r[k]==payload.get(k) for k in ('issuer','key_id',identity))]
    if len(rows)!=1:fail('worker_evidence_signer')
    row=rows[0]
    if profile not in row['profiles'] or req['tenant_id'] not in row['tenant_ids'] or req['object_id'] not in row['object_ids']:fail('worker_evidence_signer_scope')
    if {'issuer':row['issuer'],'key_id':row['key_id'],'purpose':purpose} in policy['revoked']:fail('worker_evidence_revoked')
    return row['public_key_hex']


class _MemoryCapture:
    def __init__(self,members,root):self.members=members;self.root=root
    def names(self):
        prefix='' if str(self.root)=='capture' else 'raw/'
        return (['export.json','context.json','capture-receipt.json','raw'] if not prefix else [k[4:] for k in self.members if k.startswith('raw/')])
    def read(self,name,limit=MAX_BYTES):
        key=name if str(self.root)=='capture' else 'raw/'+name
        if key not in self.members or len(self.members[key])>limit:fail('worker_evidence_capture')
        return self.members[key]
    @contextmanager
    def raw(self):yield _MemoryCapture(self.members,self.root/'raw')


def capture_members(value,tenant_id):
    if value is None:return None
    if type(value) is not dict or not 3<=len(value)<=10003:fail('worker_evidence_capture')
    members={};total=0
    for key,row in value.items():
        if key not in ('export.json','context.json','capture-receipt.json') and not re.fullmatch('raw/page-[0-9]{6}\\.json',key):fail('worker_evidence_member_path')
        shape(row,'bytes sha256 base64');number(row['bytes'],0,4*1024*1024 if key.startswith('raw/') else MAX_BYTES);hashed(row['sha256'])
        try:raw=base64.b64decode(row['base64'],validate=True)
        except (ValueError,TypeError):fail('worker_evidence_member_bytes')
        if len(raw)!=row['bytes'] or hashlib.sha256(raw).hexdigest()!=row['sha256'] or base64.b64encode(raw).decode()!=row['base64']:fail('worker_evidence_member_bytes')
        total+=len(raw)
        if total>MAX_CAPTURE:fail('worker_evidence_limit')
        members[key]=raw
    @contextmanager
    def access(_):yield _MemoryCapture(members,PurePosixPath('capture'))
    from .capture_adapter import _load_capture
    return _load_capture('capture',tenant_id,access)


def source_authoring_binding(manifest):
    """Inspect signed v2 facts only; never construct a repository capability."""
    facts=manifest['source_authoring_binding'];context=manifest['run_context'];provider=manifest['provider_binding']
    shape(facts,'schema_version local_scope logical_repository repository_association local_root_identity tenant_id object_id resource_address intent_artifact_id intent_data_sha256 source_revision revision_evidence git_storage_binding resolved_inputs_sha256 materialized_configuration_sha256 materialized_source_manifest provider_binding_sha256 provider_lock_sha256 authored_component_sha256 management_mapping_status source_evidence_class remote_origin_authenticated commit_actor_authenticated execution_authorized platform_qualified limitations')
    if (facts['schema_version'] not in ('worker-source-authoring-binding/1','worker-source-authoring-binding/2') or type(provider) is not dict
        or type(provider.get('backend')) is not dict or type(provider.get('provider_identity')) is not dict
        or manifest['profile']=='native_docker_laboratory_tls'):fail('worker_evidence_source_binding')
    scope=facts['local_scope'];shape(scope,'repository stack component backend')
    if (facts['logical_repository']!=context['repository'] or facts['tenant_id']!=manifest['tenant_id'] or manifest['object_ids']!=[facts['object_id']]
        or provider.get('object_id')!=facts['object_id'] or provider.get('provider_identity',{}).get('tenant_id')!=manifest['tenant_id']
        or scope['stack']!=context['stack'] or scope['component']!=context['component'] or scope['backend']!=provider.get('backend',{}).get('state_blob')
        or digest(provider.get('backend'))!=manifest['backend_scope_sha256'] or facts['source_revision']!=context['source_revision'] or facts['source_revision']!=provider.get('source_revision')
        or facts['resolved_inputs_sha256']!=context['effective_inputs_sha256'] or facts['resolved_inputs_sha256']!=provider.get('effective_input_sha256')
        or facts['materialized_configuration_sha256']!=context['source_sha256'] or facts['materialized_configuration_sha256']!=provider.get('source_sha256')
        or facts['provider_lock_sha256']!=context['provider_lock_sha256'] or facts['provider_lock_sha256']!=provider.get('lockfile_sha256')
        or facts['provider_binding_sha256']!=digest(provider) or facts['repository_association']!='explicit_operation_manifest_declaration'
        or any(facts[key] is not False for key in ('remote_origin_authenticated','commit_actor_authenticated','execution_authorized','platform_qualified'))):fail('worker_evidence_source_binding')
    for key in ('intent_artifact_id','intent_data_sha256','resolved_inputs_sha256','materialized_configuration_sha256','provider_binding_sha256','provider_lock_sha256','authored_component_sha256'):hashed(facts[key])
    if (facts['resource_address']!='microsoft365_graph_beta_device_management_settings_catalog_configuration_policy_json.selected'
        or facts['source_evidence_class']!='pinned_local_git_and_literal_materialization' or facts['management_mapping_status'] not in ('supported','unsupported')
        or type(facts['local_root_identity']) is not list or not facts['local_root_identity']
        or type(facts['revision_evidence']) is not dict or type(facts['git_storage_binding']) is not dict
        or type(facts['materialized_source_manifest']) is not dict or not facts['materialized_source_manifest']
        or type(facts['limitations']) is not list or not facts['limitations'] or any(type(v) is not str for v in facts['limitations'])):fail('worker_evidence_source_binding')
    for key,value in facts['materialized_source_manifest'].items():
        if type(key) is not str or not key or len(key)>4096:fail('worker_evidence_source_binding')
        hashed(value)
    storage=facts['git_storage_binding'];version=facts['schema_version']
    expected={'worker-source-authoring-binding/1':'worker-source-git-storage/1','worker-source-authoring-binding/2':'worker-source-git-storage/2'}
    if storage.get('schema_version')!=expected[version] or type(storage.get('files')) is not list or type(storage.get('directories')) is not list:fail('worker_evidence_source_filesystem_identity')
    for row in [*facts['local_root_identity'],*storage['files'],*storage['directories']]:
        if type(row) is not dict or not {'device','inode'}<=set(row):fail('worker_evidence_source_filesystem_identity')
        for key in ('device','inode'):
            item=row[key]
            if version=='worker-source-authoring-binding/1':
                if type(item) is not int or not 0<=item<=9007199254740991:fail('worker_evidence_source_filesystem_identity')
            elif type(item) is not str or not re.fullmatch(r'0|[1-9][0-9]{0,19}',item) or int(item)>18446744073709551615:fail('worker_evidence_source_filesystem_identity')
    # Nested historical Git/identity detail is retained verbatim. It is signed
    # publisher evidence, not a new local Git check or authenticated remote origin.
    return bounded(facts)


def validate_snapshot(snapshot,req):
    if req.get('schema_version')=='worker-evidence-request/2':
        from .worker_evidence_domains import validate_snapshot as domain_snapshot
        return domain_snapshot(snapshot,req)
    shape(snapshot,'schema_version read_at manifest policy_sha256 journal job events approval consumed capture_provenance capture')
    if snapshot['schema_version']!='worker-evidence-snapshot/1':fail('worker_evidence_snapshot')
    number(snapshot['read_at'],1,9007199254740991);hashed(snapshot['policy_sha256'])
    m=snapshot['manifest']
    fields='schema_version operation_id profile prepared_at expires_at action execution_binding_sha256 host_spec broker_policy state_contracts saved_plan_sha256 identity_binding_sha256 run_binding_sha256 storage_binding_sha256 provider_binding tenant_id object_ids backend_scope_sha256 implementation_files precondition_binding run_context'
    if type(m) is dict and m.get('schema_version')=='worker-service-operation/2':fields+=' source_authoring_binding'
    shape(m,fields)
    if m['schema_version'] not in ('worker-service-operation/1','worker-service-operation/2'):fail('worker_evidence_manifest')
    number(m['prepared_at'],1,snapshot['read_at']+5);number(m['expires_at'],m['prepared_at']+1,m['prepared_at']+900)
    context=m['run_context']
    shape(context,'schema_version repository source_revision source_sha256 workflow_revision verifier_revision run_id run_attempt protected_ref effective_inputs_sha256 provider_lock_sha256 stack component')
    if context['schema_version']!='service-run-context/1' or context['stack']!='worker' or context['component']!='intune-policy':fail('worker_evidence_run_context')
    for key in ('source_revision','workflow_revision','verifier_revision'):
        if type(context[key]) is not str or not REV.fullmatch(context[key]):fail('worker_evidence_revision')
    for key in ('source_sha256','effective_inputs_sha256','provider_lock_sha256'):hashed(context[key])
    if type(m['object_ids']) is not list or len(m['object_ids'])!=1:fail('worker_evidence_identity')
    if m.get('action')!='apply_saved_plan' or m.get('profile') not in PROFILES:fail('worker_evidence_action_unsupported')
    expected={'tenant_id':m.get('tenant_id'),'object_id':m.get('object_ids',[None])[0] if len(m.get('object_ids',[]))==1 else None,
        'operation_id':m.get('operation_id'),'manifest_sha256':digest(m),'saved_plan_sha256':m.get('saved_plan_sha256'),
        'execution_binding_sha256':m.get('execution_binding_sha256'),'run_binding_sha256':m.get('run_binding_sha256'),
        'source_revision':context.get('source_revision'),'source_sha256':context.get('source_sha256'),
        'run_id':context.get('run_id'),'run_attempt':context.get('run_attempt')}
    if any(req[k]!=v for k,v in expected.items()) or digest(context)!=req['run_binding_sha256']:fail('worker_evidence_binding')
    if m['schema_version']=='worker-service-operation/2':source_authoring_binding(m)
    return journal_snapshot(snapshot,req)


def journal_snapshot(snapshot,req,*,prepared_kind='prepared',selected_operation=False):
    shape(snapshot['journal'],'database_sha256 selected_event_count first_sequence last_sequence events_sha256')
    journal=snapshot['journal'];hashed(journal['database_sha256']);hashed(journal['events_sha256'])
    events=snapshot['events']
    if type(events) is not list or not 1<=len(events)<=1000:fail('worker_evidence_event_limit')
    previous=0
    for event in events:
        shape(event,'sequence kind payload created_at');number(event['sequence'],previous+1,9007199254740991);previous=event['sequence']
        label(event['kind']);number(event['created_at'],1,snapshot['read_at'])
        if type(event['payload']) is not dict or len(canonical(event['payload']))>256*1024:fail('worker_evidence_event_limit')
    if journal['selected_event_count']!=len(events) or type(journal['selected_event_count']) is not int or journal['first_sequence']!=events[0]['sequence'] or journal['last_sequence']!=events[-1]['sequence'] or journal['events_sha256']!=digest(events):fail('worker_evidence_events')
    shape(snapshot['job'],'status cancel_requested dispatches outcome')
    label(snapshot['job']['status']);number(snapshot['job']['dispatches'],0,1)
    if type(snapshot['job']['cancel_requested']) is not bool:fail('worker_evidence_job')
    if snapshot['job']['outcome'] is not None and type(snapshot['job']['outcome']) is not dict:fail('worker_evidence_job')
    prepared=[e for e in events if e['kind']==prepared_kind and (not selected_operation or e['payload'].get('operation_id')==req['operation_id'])]
    if len(prepared)!=1 or prepared[0]['payload'].get('manifest_sha256')!=req['manifest_sha256']:fail('worker_evidence_prepared')
    cap=capture_members(snapshot['capture'],req['tenant_id'])
    if cap is not None and cap['object_id']!=req['object_id']:fail('worker_evidence_capture_identity')
    provenance=snapshot['capture_provenance']
    if provenance is not None:
        shape(provenance,'evidence_class capture_sha256 raw_observed_sha256 observed_at source_record_sha256 assurance')
        for key in ('capture_sha256','raw_observed_sha256','source_record_sha256'):hashed(provenance[key])
        if (cap is None or provenance['capture_sha256']!=cap['capture_sha256'] or provenance['raw_observed_sha256']!=digest(cap['source']['raw_observed']) or provenance['observed_at']!=cap['observed_at'] or provenance['assurance']!='publisher_checked_registered_local_observation_not_remote_reauthentication'):
            fail('worker_evidence_capture_provenance')
    return cap


def approval_proof(snapshot,req,policy,verify):
    if req.get('schema_version')=='worker-evidence-request/2':
        from .worker_evidence_domains import approval_proof as domain_approval
        return domain_approval(snapshot,req,policy,verify)
    return approval_transcript(snapshot,req,policy,verify)


def approval_transcript(snapshot,req,policy,verify,*,schema='signed-worker-service-approval/1',domain=APPROVAL_DOMAIN,dispatch_kind='dispatch_consumed',selected_operation=False):
    transcript=snapshot['approval'];consumed=snapshot['consumed'];events=snapshot['events']
    if transcript is None:return 'not_retained'
    shape(transcript,'receipt receipt_sha256 consumed_at');hashed(transcript['receipt_sha256']);number(transcript['consumed_at'],1,snapshot['read_at'])
    if digest(transcript['receipt'])!=transcript['receipt_sha256']:fail('worker_evidence_approval_changed')
    receipt=transcript['receipt'];shape(receipt,'payload signature');payload=receipt['payload']
    shape(payload,'schema_version issuer key_id approver_id operation_id manifest_sha256 issued_at expires_at nonce')
    if payload['schema_version']!=schema or payload['operation_id']!=req['operation_id'] or payload['manifest_sha256']!=req['manifest_sha256']:fail('worker_evidence_approval_binding')
    for name in ('issuer','key_id','approver_id'):label(payload[name])
    if type(payload['nonce']) is not str or not re.fullmatch('[a-f0-9]{32}',payload['nonce']):fail('worker_evidence_approval_binding')
    m=snapshot['manifest'];number(payload['issued_at'],m['prepared_at'],transcript['consumed_at']+5);number(payload['expires_at'],transcript['consumed_at']+1,m['expires_at'])
    shape(consumed,'issuer nonce operation_id manifest_sha256')
    if any(consumed[k]!=payload[k] for k in consumed):fail('worker_evidence_approval_consumption')
    dispatch=[e for e in events if e['kind']==dispatch_kind and (not selected_operation or e['payload'].get('operation_id')==req['operation_id'])]
    if len(dispatch)!=1 or dispatch[0]['payload'].get('manifest_sha256')!=req['manifest_sha256'] or not transcript['consumed_at']<=dispatch[0]['created_at']<=transcript['consumed_at']+1 or snapshot['job']['dispatches']!=1:fail('worker_evidence_approval_consumption')
    key=scoped_key(policy,'approvers',payload,req,m['profile'])
    if verify(key,domain+canonical(payload),signature(receipt['signature'])) is not None:fail('worker_evidence_verifier_contract')
    return 'verified_retained_original'


def deployment_state(manifest,status,operation_id,manifest_sha256):
    """Common local/export convergence contract; never approves an execution."""
    if status.get('status')!='service_state_converged':fail('workbench_service_deployment_unverified')
    outcome=status.get('outcome')
    if (type(outcome) is not dict or outcome.get('execution_provenance')!='host_completed' or
            outcome.get('reservation_released') is not True or outcome.get('mutation_replayed') is not False):
        fail('workbench_service_deployment_unverified')
    events=[e for e in status.get('events',[]) if e.get('kind')=='independent_state_reconciled']
    if len(events)!=1 or digest(events[0]['payload'])!=digest(outcome):fail('workbench_service_reconciliation_event')
    facts=outcome.get('independent_readback')
    evidence=('authenticated_service_state_convergence' if manifest['profile']=='azure_public_pilot' else 'laboratory_service_state_convergence')
    if (type(facts) is not dict or facts.get('schema_version')!='worker-service-independent-readback/1' or
            facts.get('operation_id')!=operation_id or facts.get('manifest_sha256')!=manifest_sha256 or
            facts.get('execution_binding_sha256')!=manifest['execution_binding_sha256'] or
            facts.get('evidence_class')!=evidence or facts.get('backend_lock_released') is not True):
        fail('workbench_service_readback_binding')
    return facts,events[0],evidence


def baseline(snapshot,req,cap,approval_status):
    if req.get('schema_version')=='worker-evidence-request/2':
        from .worker_evidence_domains import baseline as domain_baseline
        return domain_baseline(snapshot,req,cap,approval_status)
    job=snapshot['job'];outcome=job['outcome']
    reasons=[]
    if approval_status!='verified_retained_original':reasons.append('original_approval_not_retained')
    m=snapshot['manifest'];live=m['profile']=='azure_public_pilot'
    evidence='authenticated_service_state_convergence' if live else 'laboratory_service_state_convergence'
    facts=outcome.get('independent_readback',{}) if outcome else {}
    try:deployment_state(m,dict(job,events=snapshot['events']),req['operation_id'],req['manifest_sha256'])
    except AppError as error:reasons.append(error.code)
    provenance=snapshot['capture_provenance'];expected='graph_authenticated_observation' if live else 'graph_reader_laboratory'
    if cap is None or cap['capture_sha256']!=facts.get('graph_capture_sha256'):reasons.append('raw_capture_missing')
    if cap is not None and any(row['coverage']!='complete' for row in cap['collections']):reasons.append('raw_capture_incomplete')
    if live and cap is not None and cap['source'].get('source_is_synthetic') is not False:
        reasons.append('synthetic_capture_cannot_establish_live_service_evidence')
        evidence='contradictory_signed_worker_evidence'
    if type(provenance) is not dict or provenance.get('evidence_class')!=expected or (cap is not None and provenance.get('capture_sha256')!=cap['capture_sha256']):reasons.append('capture_provenance_missing')
    return {'baseline_admissible':not reasons,'reasons':reasons,'evidence_class':evidence,
        'baseline_kind':'verified_signed_worker_evidence' if not reasons else 'unverified_worker_evidence',
        'normalized_comparison_available':cap is not None and cap['body'] is not None,
        'desired':cap['body'] if cap else None,'raw_observed':cap['source']['raw_observed'] if cap else None,
        'capture_sha256':cap['capture_sha256'] if cap else None,'observed_at':cap['observed_at'] if cap else None,
        'second_plan_convergence':facts.get('second_plan_convergence','unestablished'),'endpoint_effectiveness':'unestablished',
        'platform_qualified':False,'production_approved':False,'execution_authorized':False,'cloud_authority':False}


class VerifiedEvidence:
    def __init__(self,seal,raw,result):
        if seal is not _SEAL:fail('worker_evidence_capability')
        self._raw,self._result=bytes(raw),bounded(result)
    def result(self):return bounded(self._result)
    def __reduce_ex__(self,_):raise TypeError('Verified evidence cannot be serialized as authority.')


def received_binding(verified,request_sha256):
    """One host-independent receipt/ordering contract from sealed verified bytes."""
    if type(verified) is not VerifiedEvidence:fail('worker_evidence_capability')
    hashed(request_sha256);result=verified.result();payload=parse_json(verified._raw)['payload']
    if result['request_sha256']!=request_sha256:fail('worker_evidence_request_binding')
    publisher=payload['publisher'];snapshot=payload['snapshot']
    return {'request_sha256':request_sha256,'bundle_sha256':result['bundle_sha256'],
        'scope':digest({'publisher':{k:publisher[k] for k in ('issuer','publisher_id')},
            'tenant':result['tenant_id'],'object':result['object_id'],'operation':result['operation_id'],'manifest':result['manifest_sha256']}),
        'sequence':snapshot['journal']['last_sequence'],'event_sha256':snapshot['journal']['events_sha256']}


def admit_received(binding,prior,head):
    """Pure transaction predicate; changing signing keys cannot reset ordering."""
    shape(binding,'request_sha256 bundle_sha256 scope sequence event_sha256')
    for key in ('request_sha256','bundle_sha256','scope','event_sha256'):hashed(binding[key])
    number(binding['sequence'],1,9007199254740991)
    if prior is not None:
        hashed(prior)
        if prior!=binding['bundle_sha256']:fail('worker_evidence_request_conflict')
    if head is not None:
        shape(head,'sequence event_sha256');number(head['sequence'],1,9007199254740991);hashed(head['event_sha256'])
        if binding['sequence']<head['sequence'] or binding['sequence']==head['sequence'] and binding['event_sha256']!=head['event_sha256']:
            fail('worker_evidence_replay_or_fork')
    return prior is not None


def stored_result(verified,head):
    """Reopening an admitted older receipt cannot bypass the latest known head."""
    if type(verified) is not VerifiedEvidence:fail('worker_evidence_capability')
    result=verified.result();binding=received_binding(verified,result['request_sha256'])
    if head is None:fail('worker_evidence_stored_head_missing')
    shape(head,'sequence event_sha256');number(head['sequence'],1,9007199254740991);hashed(head['event_sha256'])
    if head['sequence']<binding['sequence'] or head['sequence']==binding['sequence'] and head['event_sha256']!=binding['event_sha256']:
        fail('worker_evidence_replay_or_fork')
    result['received_head']=head;result['receipt_currentness']='latest_known_signed_snapshot'
    if head['sequence']>binding['sequence']:
        result['receipt_currentness']='superseded_signed_snapshot'
        if not result['historical_only']:
            result['historical_snapshot_status']=result['worker_status']
            result['journal_snapshot']['status_at_snapshot']=result['journal_snapshot']['status']
        result.update(worker_status='unknown',current_status='unknown',historical_only=True,baseline_admissible=False,baseline_kind='historical_signed_worker_evidence')
        result['journal_snapshot'].update(status='unknown',historical_only=True)
        result['reasons'].append('superseded_by_newer_received_signed_snapshot')
    return result


def fresh_now(*,floor):
    """The time for the first, authenticating pass of a non-historical read: max(wall, recorded mark, boot-session carry).

    Pure: it reads the recorded floor and touches no process anchor and no file, so an input that fails authentication has no
    clock effect at all. (Floor.peek is not used: it advances the process floor.) The process anchor and the durable mark
    are updated only in the authenticated, locked phase, on a resample taken by the reader that holds the lock."""
    wall=time.time();store=clock.Floor(floor);recorded=store.record();carried=store.carried(recorded)
    mark=0 if recorded is None else recorded['high_water']
    return int(max(wall,mark,mark if carried is None else carried))


def unrecorded():
    """An admission whose observed time could not be recorded is refused: admission depends on the write."""
    raise AppError('worker_evidence_clock_unrecorded','The authenticated read time could not be recorded; the evidence was not admitted.')


def mark_unrecorded(error):
    """A temporal refusal keeps its own code; this only says its closure could not be recorded."""
    error.closure_recorded=False
    if hasattr(error,'add_note'):error.add_note('closure_recorded=false: worker_evidence_clock_unrecorded')
    return error


def verify_envelope(envelope,req,policy,verify,*,now,historical=False):
    if type(historical) is not bool:fail('worker_evidence_history_mode')
    envelope=bounded(envelope);req=request(bounded(req));policy=trust(policy)
    if digest(policy)!=req['trust_sha256']:fail('worker_evidence_trust_changed')
    shape(envelope,'schema_version payload signature')
    if envelope['schema_version']!='signed-worker-evidence/1':fail('worker_evidence_envelope')
    payload=envelope['payload'];shape(payload,'schema_version publisher request_sha256 request_nonce issued_at expires_at snapshot')
    if payload['schema_version']!='worker-evidence-statement/1' or payload['request_sha256']!=digest(req) or payload['request_nonce']!=req['nonce']:fail('worker_evidence_request_binding')
    publisher=payload['publisher'];shape(publisher,'issuer key_id publisher_id purpose source_revision implementation_sha256')
    for name in ('issuer','key_id','publisher_id'):label(publisher[name])
    if publisher['purpose']!='read_only_worker_evidence' or type(publisher['source_revision']) is not str or not REV.fullmatch(publisher['source_revision']):fail('worker_evidence_purpose')
    hashed(publisher['implementation_sha256'])
    number(now,1,9007199254740991);number(payload['issued_at'],1,now+policy['clock_skew_seconds'])
    number(payload['expires_at'],payload['issued_at']+1,payload['issued_at']+policy['max_lifetime_seconds'])
    if not historical and now>=payload['expires_at']:fail('worker_evidence_expired')
    snapshot=payload['snapshot'];cap=validate_snapshot(snapshot,req)
    if not payload['issued_at']-policy['max_age_seconds']<=snapshot['read_at']<=payload['issued_at']:fail('worker_evidence_stale_snapshot')
    if not historical and now-snapshot['read_at']>policy['max_age_seconds']:fail('worker_evidence_stale_snapshot')
    key=scoped_key(policy,'publishers',publisher,req,snapshot['manifest']['profile'])
    if verify(key,DOMAIN+canonical(payload),signature(envelope['signature'])) is not None:fail('worker_evidence_verifier_contract')
    approval_status=approval_proof(snapshot,req,policy,verify)
    result=baseline(snapshot,req,cap,approval_status)
    result.update(schema_version='verified-worker-evidence-result/1',bundle_sha256=digest(envelope),request_sha256=digest(req),
        approval_artifact_status=approval_status,snapshot_read_at=snapshot['read_at'],issued_at=payload['issued_at'],expires_at=payload['expires_at'],
        publisher=publisher,operation_id=req['operation_id'],manifest_sha256=req['manifest_sha256'],
        journal_sequence=snapshot['journal']['last_sequence'],source_context=snapshot['manifest']['run_context'],
        tenant_id=req['tenant_id'],object_id=req['object_id'],
        review={'manifest':snapshot['manifest'],'manifest_sha256':req['manifest_sha256'],'approval_transcript_sha256':snapshot['approval']['receipt_sha256'] if snapshot['approval'] else None,'execution_authorized':False},
        journal_snapshot=dict(snapshot['job'],events=snapshot['events'],read_at=snapshot['read_at'],execution_authorized=False),
        worker_status=snapshot['job']['status'],cancel_requested=snapshot['job']['cancel_requested'],
        proof={'operation_id':req['operation_id'],'plan_sha256':req['saved_plan_sha256'],'manifest_sha256':req['manifest_sha256'],
            'reconciliation_sha256':digest(snapshot['job']['outcome']),'capture_sha256':cap['capture_sha256'] if cap else None,
            'observed_at':cap['observed_at'] if cap else None,'desired':cap['body'] if cap else None,
            'raw_observation':cap['source']['raw_observed'] if cap else None,
            'backend_state':(snapshot['job']['outcome'] or {}).get('independent_readback',{}).get('backend_state'),
            'source_context':snapshot['manifest']['run_context']},
        ci_attestation='unestablished_host_policy_contract_only',historical_operation_runtime_re_attested=False)
    result['operation_kind']=req.get('operation_kind','ordinary_apply')
    result['source_authoring_binding']=snapshot['manifest'].get('source_authoring_binding')
    result['source_authoring_assurance']=('signed_historical_local_source_binding_no_capability_or_remote_origin_reauthentication' if result['source_authoring_binding'] is not None else 'not_recorded_v1')
    result['historical_only']=historical
    if historical:
        result.update(historical_snapshot_status=result['worker_status'],worker_status='unknown',baseline_admissible=False,current_status='unknown',baseline_kind='historical_signed_worker_evidence')
        result['journal_snapshot']['status_at_snapshot']=result['journal_snapshot']['status']
        result['journal_snapshot']['status']='unknown';result['journal_snapshot']['historical_only']=True
        result['reasons'].append('historical_inspection_not_current_status_or_baseline')
    return VerifiedEvidence(_SEAL,canonical(envelope),result)
