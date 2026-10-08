"""Closed read-only adoption/first-Plan history. No Graph deployment authority.

Host and provider structures are preserved signed historical facts. This decoder
never constructs their execution capability or asserts a current platform gate.
"""
from __future__ import annotations
import base64
import hashlib
import re
from . import worker_evidence as c
from .io import canonical,digest,parse_json
ADOPTION='native-state-adoption/1'
RECOVERY='native-adoption-recovery-plan/1'
RECOVERY_PHASE='native-adoption-recovery-plan/2'
KINDS={ADOPTION:'state_adoption',RECOVERY:'adoption_recovery_plan',RECOVERY_PHASE:'adoption_recovery_plan'}
ADOPTION_FIELDS='schema_version operation_id verification_operation_id profile prepared_at expires_at action execution_binding_sha256 host_spec broker_policy verification_host_spec verification_broker_policy identity_binding_sha256 run_binding_sha256 run_context storage_binding_sha256 provider_binding tenant_id object_ids backend_scope_sha256 implementation_files state_contract ownership_binding intended_writer'
RECOVERY_FIELDS='schema_version operation_id profile action prepared_at expires_at original_operation_id original_manifest_sha256 original_facts recovery_binding execution_binding_sha256 host_spec broker_policy provider_binding run_context run_binding_sha256 storage_binding_sha256 identity_binding_sha256 implementation_files'
REQUEST_FIELDS='schema_version nonce tenant_id object_id operation_id operation_kind original_manifest_sha256 manifest_sha256 saved_plan_sha256 execution_binding_sha256 run_binding_sha256 source_revision source_sha256 run_id run_attempt trust_sha256'


def request(value):
    c.shape(value,REQUEST_FIELDS)
    if value['schema_version']!='worker-evidence-request/2' or value['operation_kind'] not in KINDS.values() or value['saved_plan_sha256'] is not None:c.fail('worker_evidence_domain_request')
    legacy={key:item for key,item in value.items() if key not in ('operation_kind','original_manifest_sha256')}
    legacy.update(schema_version='worker-evidence-request/1',saved_plan_sha256='0'*64);c.request(legacy)
    if value['operation_kind']=='state_adoption':
        if value['original_manifest_sha256'] is not None:c.fail('worker_evidence_domain_request')
    else:c.hashed(value['original_manifest_sha256'])
    return value


def make_request(manifest,policy,nonce):
    if type(manifest) is not dict or type(manifest.get('run_context')) is not dict or type(manifest.get('provider_binding')) is not dict:c.fail('worker_evidence_domain_manifest')
    version=manifest.get('schema_version');context=manifest['run_context'];provider=manifest['provider_binding']
    if version not in KINDS:c.fail('worker_evidence_domain_unsupported')
    tenant=manifest.get('tenant_id',provider.get('tenant_id'));objects=manifest.get('object_ids',[provider.get('object_id')])
    if type(objects) is not list or len(objects)!=1:c.fail('worker_evidence_identity')
    return request({'schema_version':'worker-evidence-request/2','nonce':nonce,'tenant_id':tenant,'object_id':objects[0],
        'operation_id':manifest['operation_id'],'operation_kind':KINDS[version],'original_manifest_sha256':manifest.get('original_manifest_sha256'),
        'manifest_sha256':digest(manifest),'saved_plan_sha256':None,'execution_binding_sha256':manifest['execution_binding_sha256'],
        'run_binding_sha256':manifest['run_binding_sha256'],'source_revision':context['source_revision'],'source_sha256':context['source_sha256'],
        'run_id':context['run_id'],'run_attempt':context['run_attempt'],'trust_sha256':digest(policy)})


def manifest(value,req,at,original=None):
    if type(value) is not dict:c.fail('worker_evidence_domain_manifest')
    version=value.get('schema_version')
    c.shape(value,ADOPTION_FIELDS if version==ADOPTION else RECOVERY_FIELDS)
    if version not in KINDS or req['operation_kind']!=KINDS[version]:c.fail('worker_evidence_domain_manifest')
    if value['profile'] not in ('native_docker_laboratory_protocol','azure_public_pilot'):c.fail('worker_evidence_domain_profile')
    c.number(value['prepared_at'],1,at+5);c.number(value['expires_at'],value['prepared_at']+1,value['prepared_at']+900)
    for key in ('execution_binding_sha256','run_binding_sha256','storage_binding_sha256','identity_binding_sha256'):c.hashed(value[key])
    context=value['run_context'];c.shape(context,'schema_version repository source_revision source_sha256 workflow_revision verifier_revision run_id run_attempt protected_ref effective_inputs_sha256 provider_lock_sha256 stack component')
    if context['schema_version']!='service-run-context/1' or context['stack']!='worker' or context['component']!='intune-policy' or digest(context)!=value['run_binding_sha256']:c.fail('worker_evidence_domain_run')
    for key in ('source_revision','workflow_revision','verifier_revision'):
        if type(context[key]) is not str or not c.REV.fullmatch(context[key]):c.fail('worker_evidence_revision')
    for key in ('source_sha256','effective_inputs_sha256','provider_lock_sha256'):c.hashed(context[key])
    p=value['provider_binding']
    if (type(p) is not dict or p.get('schema_version')!='worker-adoption-provider/1' or p.get('tenant_id')!=req['tenant_id']
        or p.get('object_id')!=req['object_id'] or type(p.get('provider_identity')) is not dict or p['provider_identity'].get('tenant_id')!=req['tenant_id']
        or any(context[key]!=p.get(other) for key,other in [('source_revision','source_revision'),('source_sha256','source_sha256'),('effective_inputs_sha256','effective_input_sha256'),('provider_lock_sha256','lockfile_sha256')])):c.fail('worker_evidence_domain_provider')
    expected={'operation_id':value['operation_id'],'manifest_sha256':digest(value),'execution_binding_sha256':value['execution_binding_sha256'],'run_binding_sha256':value['run_binding_sha256'],
        'source_revision':context['source_revision'],'source_sha256':context['source_sha256'],'run_id':context['run_id'],'run_attempt':context['run_attempt']}
    if any(req[key]!=item for key,item in expected.items()):c.fail('worker_evidence_binding')
    inventory=value['implementation_files']
    if type(inventory) is not dict or not 1<=len(inventory)<=4096:c.fail('worker_evidence_domain_inventory')
    for name,sha in inventory.items():
        if type(name) is not str or not name or len(name)>4096:c.fail('worker_evidence_domain_inventory')
        c.hashed(sha)
    if version==ADOPTION:
        c.identifier(value['verification_operation_id'])
        if value['action']!='native_state_only_import' or value['tenant_id']!=req['tenant_id'] or value['object_ids']!=[req['object_id']] or value['verification_operation_id']==value['operation_id'] or digest(p.get('backend'))!=value['backend_scope_sha256']:c.fail('worker_evidence_adoption_binding')
        state=value['state_contract'];ownership=value['ownership_binding'];writer=value['intended_writer']
        if (type(state) is not dict or state.get('schema_version')!='native-adoption-state-contract/1' or state.get('tenant_id')!=req['tenant_id'] or state.get('object_id')!=req['object_id']
            or state.get('execution_binding_sha256')!=req['execution_binding_sha256'] or state.get('source_sha256')!=context['source_sha256']
            or state.get('effective_inputs_sha256')!=context['effective_inputs_sha256'] or state.get('locks_sha256')!=context['provider_lock_sha256']
            or state.get('backend')!=p.get('backend',{}).get('backend') or type(ownership) is not dict
            or ownership.get('tenant_id')!=req['tenant_id'] or ownership.get('object_id')!=req['object_id'] or ownership.get('baseline_sha256')!=state.get('baseline_sha256')
            or ownership.get('result')!='no_owner_in_completely_searched_declared_scope' or type(writer) is not dict
            or writer.get('ordinary_graph_changes_require_separate_approval') is not True):c.fail('worker_evidence_adoption_binding')
    else:
        if value['action']!='native_first_plan_only' or type(original) is not dict or original.get('schema_version')!=ADOPTION:c.fail('worker_evidence_recovery_original')
        if (value['original_manifest_sha256']!=digest(original) or req['original_manifest_sha256']!=digest(original)
            or value['original_operation_id']!=original['operation_id'] or value['operation_id'] in (original['operation_id'],original['verification_operation_id'])
            or value['profile']!=original['profile'] or original['tenant_id']!=req['tenant_id'] or original['object_ids']!=[req['object_id']]):c.fail('worker_evidence_recovery_original')
        for key in ('repository','stack','component','source_revision','source_sha256','effective_inputs_sha256','provider_lock_sha256'):
            if context[key]!=original['run_context'][key]:c.fail('worker_evidence_recovery_source')
        b=value['recovery_binding'];c.shape(b,'recovery_operation_id recovery_manifest_sha256 state projection_sha256 original_contract_sha256'+(' phase ancestors' if version==RECOVERY_PHASE else ''))
        c.identifier(b['recovery_operation_id'])
        for key in ('recovery_manifest_sha256','projection_sha256','original_contract_sha256'):c.hashed(b[key])
        if b['original_contract_sha256']!=digest(original['state_contract']) or type(b['state']) is not dict:c.fail('worker_evidence_recovery_binding')
    if version==RECOVERY_PHASE:
        from .worker_evidence_phase import binding
        binding(value,original)
    return version


def member(row,limit=8*1024*1024):
    c.shape(row,'bytes sha256 base64');c.number(row['bytes'],1,limit);c.hashed(row['sha256'])
    try:raw=base64.b64decode(row['base64'],validate=True)
    except (ValueError,TypeError):c.fail('worker_evidence_domain_member')
    if len(raw)!=row['bytes'] or hashlib.sha256(raw).hexdigest()!=row['sha256'] or base64.b64encode(raw).decode()!=row['base64']:c.fail('worker_evidence_domain_member')
    return raw


def validate_snapshot(snapshot,req):
    c.shape(snapshot,'schema_version read_at manifest policy_sha256 journal job events approval consumed capture_provenance capture domain_records')
    if snapshot['schema_version']!='worker-evidence-snapshot/2':c.fail('worker_evidence_domain_snapshot')
    c.number(snapshot['read_at'],1,9007199254740991);c.hashed(snapshot['policy_sha256'])
    records=snapshot['domain_records'];c.shape(records,'verification original plan_artifacts state source source_policy'+(' phase_ledger' if snapshot['manifest'].get('schema_version')==RECOVERY_PHASE else ''))
    c.shape(records['source_policy'],'reviewed_policy_sha256 current_policy_sha256')
    for item in records['source_policy'].values():c.hashed(item)
    if records['source_policy']['current_policy_sha256']!=snapshot['policy_sha256']:c.fail('worker_evidence_domain_source_policy')
    original=records['original'];is_recovery=req['operation_kind']=='adoption_recovery_plan'
    if is_recovery:
        if type(original) is not dict or original.get('schema_version')!='worker-evidence-snapshot/2' or original.get('manifest',{}).get('schema_version')!=ADOPTION:c.fail('worker_evidence_recovery_original')
        oldreq=dict(req,operation_kind='state_adoption',original_manifest_sha256=None,operation_id=original['manifest']['operation_id'],manifest_sha256=digest(original['manifest']))
        m=original['manifest'];oldreq.update(execution_binding_sha256=m['execution_binding_sha256'],run_binding_sha256=m['run_binding_sha256'],run_id=m['run_context']['run_id'],run_attempt=m['run_context']['run_attempt'])
        validate_snapshot(original,oldreq)
    elif original is not None:c.fail('worker_evidence_domain_original')
    version=manifest(snapshot['manifest'],req,snapshot['read_at'],original['manifest'] if original else None)
    verification=records['verification']
    if version==ADOPTION:
        c.shape(verification,'verification_operation_id dispatches status outcome')
        if verification['verification_operation_id']!=snapshot['manifest']['verification_operation_id']:c.fail('worker_evidence_adoption_verification')
        c.number(verification['dispatches'],0,1);c.label(verification['status'])
        if verification['outcome'] is not None and type(verification['outcome']) is not dict:c.fail('worker_evidence_adoption_verification')
    elif verification is not None:c.fail('worker_evidence_domain_verification')
    artifacts=records['plan_artifacts']
    if artifacts is not None:
        c.shape(artifacts,'plan.bin plan.json exit.txt receipt.json')
        for name,row in artifacts.items():member(row,64 if name=='exit.txt' else 8*1024*1024)
    for name in ('state','source'):
        if records[name] is not None:member(records[name])
    if version==RECOVERY_PHASE:
        from .worker_evidence_phase import validate
        validate(snapshot)
    return c.journal_snapshot(snapshot,req,prepared_kind='adoption_recovery_plan_prepared' if is_recovery else 'adoption_prepared',selected_operation=is_recovery)


def approval_proof(snapshot,req,policy,verify):
    recovery=req['operation_kind']=='adoption_recovery_plan'
    phase=snapshot['manifest']['schema_version']==RECOVERY_PHASE;version='2' if phase else '1'
    schema='signed-native-adoption-recovery-plan-approval/'+version if recovery else 'signed-native-state-adoption-approval/1'
    domain=('intune-workbench:native-adoption-recovery-plan-approval:v'+version+'\x00').encode() if recovery else b'intune-workbench:native-state-adoption-approval:v1\x00'
    result=c.approval_transcript(snapshot,req,policy,verify,schema=schema,domain=domain,dispatch_kind='adoption_recovery_plan_consumed' if recovery else 'adoption_dispatch_consumed',selected_operation=recovery)
    if recovery:
        original=snapshot['domain_records']['original'];m=original['manifest']
        oldreq=make_request(m,policy,req['nonce']);old=c.approval_transcript(original,oldreq,policy,verify,schema='signed-native-state-adoption-approval/1',domain=b'intune-workbench:native-state-adoption-approval:v1\x00',dispatch_kind='adoption_dispatch_consumed')
        if old!='verified_retained_original':return 'original_adoption_approval_not_retained'
    if phase:
        from .worker_evidence_phase import approvals
        prior=approvals(snapshot,req,policy,verify)
        if prior!='verified_retained_original':return prior
    return result


def plan_proof(snapshot,req,expected):
    records=snapshot['domain_records'];artifacts=records['plan_artifacts']
    if artifacts is None or records['state'] is None or records['source'] is None:return 'exact_plan_state_or_source_not_retained'
    raw={name:member(row,64 if name=='exit.txt' else 8*1024*1024) for name,row in artifacts.items()};record=parse_json(raw['receipt.json'])
    c.shape(record,'schema_version host_result_sha256 source_root archive_root artifacts receiving_state_authentication_established execution_authorized')
    c.shape(expected,'capture_sha256 artifacts content_proof first_plan_no_change exit_code')
    c.hashed(record['host_result_sha256'])
    if (record['schema_version']!='native-plan-output-capture/1' or record['receiving_state_authentication_established'] is not False or record['execution_authorized'] is not False or raw['receipt.json']!=canonical(record)
        or raw['exit.txt']!=b'0\n' or type(expected) is not dict or expected.get('capture_sha256')!=digest(record) or expected.get('artifacts')!=record['artifacts']
        or expected.get('first_plan_no_change') is not True or type(expected.get('exit_code')) is not int or expected.get('exit_code')!=0):c.fail('worker_evidence_plan_output_binding')
    outcome=snapshot['job']['outcome'] or {}
    durable=(outcome.get('first_plan_outcome') or {}) if req['operation_kind']=='adoption_recovery_plan' else ((records['verification'] or {}).get('outcome') or {})
    if digest(durable.get('plan_output_capture'))!=digest(record) or digest(durable.get('host'))!=record['host_result_sha256']:c.fail('worker_evidence_plan_host_binding')
    c.shape(record['artifacts'],'plan.bin plan.json exit.txt')
    for name,pin in record['artifacts'].items():
        c.shape(pin,'bytes sha256 source_path');c.number(pin['bytes'],1,8*1024*1024);c.hashed(pin['sha256'])
        if pin['bytes']!=len(raw[name]) or pin['sha256']!=hashlib.sha256(raw[name]).hexdigest():c.fail('worker_evidence_plan_output_changed')
    proof=expected.get('content_proof');c.shape(proof,'schema_version object_id resource_address state_sha256 source_sha256 effective_inputs_sha256 full_values_sha256 plan_json_sha256 before_after_planned_prior_values_equal_state source_configuration_equal receiving_state_authentication_established execution_authorized')
    from .worker_plan_content import validate
    checked=validate(raw['plan.json'],state_raw=member(records['state']),source_raw=member(records['source']),object_id=req['object_id'],state_sha256=proof['state_sha256'],source_sha256=req['source_sha256'],effective_inputs_sha256=snapshot['manifest']['run_context']['effective_inputs_sha256'])
    if canonical(checked)!=canonical(proof):c.fail('worker_evidence_plan_content_changed')
    return None


def baseline(snapshot,req,cap,approval_status):
    outcome=snapshot['job']['outcome'] or {};records=snapshot['domain_records'];m=snapshot['manifest'];recovery=req['operation_kind']=='adoption_recovery_plan';reasons=[]
    if approval_status!='verified_retained_original':reasons.append('original_approval_not_retained')
    event_kind='adoption_recovery_plan_reconciled' if recovery else 'adoption_reconciled'
    expected_status='reconciled' if recovery else 'adopted_verified'
    events=[e for e in snapshot['events'] if e['kind']==event_kind and (not recovery or e['payload'].get('recovery_plan_operation_id')==req['operation_id'])]
    if snapshot['job']['status']!=expected_status or snapshot['job']['dispatches']!=1 or len(events)!=1 or digest(events[0]['payload'])!=digest(outcome):reasons.append('domain_convergence_not_established')
    facts=outcome.get('independent_completion',{})
    if type(facts) is not dict:c.fail('worker_evidence_domain_readback_shape')
    receiving=facts.get('fresh_observation',{}) if recovery else facts.get('receiving_state',{})
    if type(receiving) is not dict:c.fail('worker_evidence_domain_readback_shape')
    if recovery:
        if (outcome.get('original_operation_id')!=m['original_operation_id'] or outcome.get('original_manifest_sha256')!=m['original_manifest_sha256'] or outcome.get('recovery_plan_operation_id')!=req['operation_id'] or outcome.get('recovery_plan_manifest_sha256')!=req['manifest_sha256']
            or facts.get('lease_independently_unlocked') is not True or receiving.get('locked') is not False or receiving.get('metadata') not in ({},None)
            or receiving.get('adoption_state_proof',{}).get('classification')!='approved_adoption_successor' or receiving.get('adoption_state_proof',{}).get('graph_unchanged') is not True):reasons.append('recovery_readback_not_established')
        expected=outcome.get('native_first_plan',{}).get('plan_output_proof')
    else:
        if (facts.get('schema_version')!='native-adoption-independent-completion/1' or facts.get('operation_id')!=req['operation_id'] or facts.get('manifest_sha256')!=req['manifest_sha256']
            or facts.get('first_plan_no_change') is not True or type(facts.get('native_first_plan_exit_code')) is not int or facts.get('native_first_plan_exit_code')!=0 or receiving.get('manifest_sha256')!=req['manifest_sha256']
            or receiving.get('backend_unlocked') is not True or records['verification']['dispatches']!=1 or records['verification']['status']!='first_plan_host_completed_unverified'
            or digest(outcome.get('first_plan_outcome'))!=digest(records['verification']['outcome'])):reasons.append('adoption_readback_not_established')
        expected=facts.get('plan_output_proof')
    if any(outcome.get(key) is not value for key,value in [('reservation_released',True),('import_replayed',False),('graph_mutated',False)]):reasons.append('state_only_outcome_not_established')
    if recovery:
        captured=receiving.get('adoption_capture')
        if receiving and (receiving.get('schema_version')!=('adoption-plan-native-lease-recovery-observation/1' if m['schema_version']==RECOVERY_PHASE else 'adoption-native-lease-recovery-observation/1') or type(captured) is not dict):c.fail('worker_evidence_recovery_capture_shape')
        if captured is not None:c.shape(captured,'capture_sha256 path');c.hashed(captured['capture_sha256'])
        rawsha=captured['capture_sha256'] if captured else None
    else:rawsha=receiving.get('graph_capture_sha256')
    if cap is None or cap['capture_sha256']!=rawsha or any(row['coverage']!='complete' for row in cap['collections']):reasons.append('raw_capture_missing_or_incomplete')
    live=m['profile']=='azure_public_pilot';provenance=snapshot['capture_provenance']
    if live and cap is not None and cap['source'].get('source_is_synthetic') is not False:reasons.append('synthetic_capture_cannot_establish_live_service_evidence')
    if type(provenance) is not dict or provenance.get('evidence_class')!=('graph_authenticated_observation' if live else 'graph_reader_laboratory'):reasons.append('capture_provenance_missing')
    if expected is None:reasons.append('exact_plan_proof_not_retained')
    else:
        if type(expected) is not dict or type(expected.get('content_proof')) is not dict or type(receiving.get('state',{})) is not dict:c.fail('worker_evidence_plan_output_binding')
        state_sha=receiving.get('state',{}).get('sha256')
        if state_sha is not None and expected.get('content_proof',{}).get('state_sha256')!=state_sha:c.fail('worker_evidence_plan_receiving_state_binding')
        missing=plan_proof(snapshot,req,expected)
        if missing:reasons.append(missing)
    return {'baseline_admissible':False,'baseline_kind':'state_only_signed_worker_history','reasons':reasons,
        'evidence_class':'signed_state_only_worker_history','domain_qualification':'signed_state_and_plan_content_consistent' if not reasons else 'unestablished',
        'state_only':True,'graph_deployment':False,'original_execution_outcome':outcome.get('original_execution_outcome','recorded_at_snapshot'),
        'normalized_comparison_available':False,'desired':None,'raw_observed':cap['source']['raw_observed'] if cap else None,
        'capture_sha256':cap['capture_sha256'] if cap else None,'observed_at':cap['observed_at'] if cap else None,
        'second_plan_convergence':'state_only_first_plan_no_change' if not reasons else 'unestablished','endpoint_effectiveness':'unestablished',
        'platform_qualified':False,'production_approved':False,'execution_authorized':False,'cloud_authority':False,
        'domain_records':records,'receiving_state_authentication':'signed_publisher_assertion_not_remote_reauthentication'}
