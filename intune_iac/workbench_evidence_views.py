"""Persistent navigation to cryptographically reverified received worker evidence.

A link is not proof. Every read checks original bytes, current trust and identity.
"""
from pathlib import Path
from .io import AppError,canonical
KIND='linked_signed_worker_evidence'


def _fail(code):raise AppError(code,'The received worker evidence does not establish the selected object view.')


def _read(store,object_id,evidence_store,request_sha256,trust_path,verifier_path,scratch):
    from .windows_workbench import WindowsWorkbenchStore
    if type(store) is WindowsWorkbenchStore:
        from .windows_worker_evidence_store import reopen_windows_evidence
        reopen=lambda historical=False:reopen_windows_evidence(evidence_store,request_sha256,trust_path,verifier_path,scratch,historical=historical)
    else:
        from . import worker_evidence_posix as host
        policy=host.load(trust_path);verifier=host.DetachedVerifier(verifier_path,scratch)
        reopen=lambda historical=False:host.reopen(evidence_store,request_sha256,policy,verifier,historical=historical)
    try:result=reopen()
    except AppError as error:
        if error.code not in ('worker_evidence_expired','worker_evidence_stale_snapshot','worker_evidence_clock_unrecorded','worker_evidence_clock_continuity_lost'):raise
        # Actual current trust/signatures remain mandatory in historical mode.
        result=reopen(historical=True)
    if result['tenant_id']!=store.tenant_id or result['object_id']!=object_id:_fail('workbench_evidence_identity')
    return result


def link(store,object_id,evidence_store,request_sha256,trust_path,verifier_path,scratch):
    result=_read(store,object_id,evidence_store,request_sha256,trust_path,verifier_path,scratch)
    from .windows_workbench import WindowsWorkbenchStore
    from pathlib import PureWindowsPath
    absolute=(lambda value:str(PureWindowsPath(value))) if type(store) is WindowsWorkbenchStore else (lambda value:str(Path(value).absolute()))
    data={'schema_version':'workbench-worker-evidence-link/1','tenant_id':store.tenant_id,'target_object_id':object_id,
        'evidence_class':KIND,'evidence_store':absolute(evidence_store),'request_sha256':request_sha256,
        'trust_path':absolute(trust_path),'verifier_path':absolute(verifier_path),'scratch':absolute(scratch),
        'bundle_sha256':result['bundle_sha256'],'operation_id':result['operation_id'],'manifest_sha256':result['manifest_sha256'],
        'baseline_admissible':False,'cloud_authority':False,'execution_authorized':False}
    return store.record_artifact('deployment_receipt',None,data)


def open_link(store,row):
    from .worker_evidence import shape
    data=row['data'];shape(data,'schema_version tenant_id target_object_id evidence_class evidence_store request_sha256 trust_path verifier_path scratch bundle_sha256 operation_id manifest_sha256 baseline_admissible cloud_authority execution_authorized')
    if data['schema_version']!='workbench-worker-evidence-link/1' or data['evidence_class']!=KIND or data['tenant_id']!=store.tenant_id or any(data[key] is not False for key in ('baseline_admissible','cloud_authority','execution_authorized')):_fail('workbench_evidence_link')
    result=_read(store,data['target_object_id'],data['evidence_store'],data['request_sha256'],data['trust_path'],data['verifier_path'],data['scratch'])
    if any(data[key]!=result[key] for key in ('bundle_sha256','operation_id','manifest_sha256')):_fail('workbench_evidence_link_changed')
    return result


def proposed(store,row):
    result=open_link(store,row)
    return {'status':'historical' if result['historical_only'] else 'recorded','evidence_class':'signed_worker_evidence_review',
        'link_artifact_id':row['artifact_id'],'operation_id':result['operation_id'],'saved_plan_sha256':result['proof']['plan_sha256'],
        'approval_digest':result['manifest_sha256'],'target':{'tenant_id':store.tenant_id,'object_id':row['data']['target_object_id']},
        'review':result['review'],'journal_status':result['worker_status'],'service_journal':result['journal_snapshot'],
        'run_context':result['source_context'],'evidence':result,'platform_qualified':False,'execution_authorized':False,
        'unresolved_risks':['Signed local evidence is not live CI, native platform or organization approval.',
            'Historical-only evidence cannot establish current worker status or an active comparison baseline.']}


def deployment(store,row):
    result=open_link(store,row)
    if result['baseline_admissible'] is not True or result['historical_only']:_fail('workbench_evidence_baseline_unverified')
    return {'artifact_id':row['artifact_id'],'evidence_class':result['evidence_class'],
        'baseline_kind':'verified_signed_worker_deployment','recorded_at':result['snapshot_read_at'],'proof':result['proof'],
        'baseline_admissible':True,'normalized_comparison_available':result['normalized_comparison_available'],
        'source_scope_association':'compare_by_tenant_and_object_identity','second_plan_convergence':result['second_plan_convergence'],
        'endpoint_effectiveness':result['endpoint_effectiveness'],'platform_qualified':False,'cloud_authority':False,'execution_authorized':False}


def history(store,object_id):
    from .workbench_views import _rows
    rows=[row for row in _rows(store,'deployment_receipt') if row['data'].get('target_object_id')==object_id and row['data'].get('evidence_class')==KIND]
    result=[]
    for row in rows:
        try:value=proposed(store,row)
        except (AppError,OSError,ValueError,KeyError,TypeError) as error:value={'status':'unavailable','link_artifact_id':row['artifact_id'],
            'error_code':getattr(error,'code',type(error).__name__),'baseline_admissible':False,'execution_authorized':False}
        result.append(value)
        if len(canonical(result))>16*1024*1024:_fail('workbench_evidence_history_limit')
    return {'schema_version':'workbench-worker-evidence-history/1','tenant_id':store.tenant_id,'object_id':object_id,'entries':result,'execution_authorized':False}
