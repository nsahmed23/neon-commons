"""Read-only links from the persistent workbench to protected service journals.

A path or imported JSON never establishes execution authority. Each display
reopens the registered service job and verifies its immutable manifest. A
deployment comparison additionally needs the exact independently published
Graph capture named by the service reconciliation event. This is a cooperative
local evidence link, not a protected organizational audit anchor.
"""
from pathlib import Path

from .io import AppError, digest

KIND = 'linked_protected_service'


def _fail(code):
    raise AppError(code, 'The linked service operation and independent observation do not establish this comparison.')


def _job(store, object_id, root, policy):
    from .host_capabilities import require_profile
    require_profile('protected_worker')
    from .worker_service import ServiceJob
    job = ServiceJob(root, policy)
    if job.manifest['tenant_id'] != store.tenant_id or job.manifest['object_ids'] != [object_id]:
        _fail('workbench_service_identity')
    return job


def link(store, object_id, root, policy):
    """Persist navigation only; never run, approve, cancel or reconcile."""
    job = _job(store, object_id, root, policy)
    if job.manifest['action'] != 'apply_saved_plan':
        _fail('workbench_service_apply_required')
    return store.record_artifact('deployment_receipt', None, {
        'schema_version': 'workbench-service-link/1', 'tenant_id': store.tenant_id,
        'target_object_id': object_id, 'job_root': str(job.root),
        'policy_path': str(Path(policy).absolute()), 'operation_id': job.identifier,
        'manifest_sha256': job.sha256, 'evidence_class': KIND,
        'baseline_admissible': False, 'cloud_authority': False, 'execution_authorized': False})


def open_link(store, row):
    data = row['data']
    if data.get('schema_version') != 'workbench-service-link/1' or data.get('evidence_class') != KIND:
        _fail('workbench_service_link_shape')
    job = _job(store, data['target_object_id'], data['job_root'], data['policy_path'])
    if job.identifier != data['operation_id'] or job.sha256 != data['manifest_sha256']:
        _fail('workbench_service_link_changed')
    return job


def proposed(store, row):
    job = open_link(store, row)
    review, status = job.review(), job.status()
    manifest = review['manifest']
    return {'status': 'recorded', 'evidence_class': 'protected_service_review',
        'link_artifact_id': row['artifact_id'], 'operation_id': job.identifier,
        'saved_plan_sha256': manifest['saved_plan_sha256'], 'approval_digest': job.sha256,
        'target': {'tenant_id': store.tenant_id, 'object_id': row['data']['target_object_id']},
        'review': review, 'journal_status': status['status'], 'service_journal': status,
        'run_context': manifest['run_context'], 'provider_binding': manifest['provider_binding'],
        'precondition_binding': manifest['precondition_binding'],
        'unresolved_risks': ['Live tenant races require the declared platform qualification.',
            'Service convergence does not establish a no-change second plan or endpoint effectiveness.',
            'The local store and journal are cooperative evidence, not a protected audit anchor.'],
        'platform_qualified': False, 'execution_authorized': False}


def deployment(store, row):
    job = open_link(store, row)
    status = job.status()
    from .worker_evidence import deployment_state
    manifest = job.manifest
    facts, event, evidence = deployment_state(manifest, status, job.identifier, job.sha256)
    outcome = status['outcome']
    observed = store.observation_for_capture(row['data']['target_object_id'], facts['graph_capture_sha256'])
    raw = store.raw_capture_observation(row['data']['target_object_id'], facts['graph_capture_sha256'])
    expected = 'graph_authenticated_observation' if manifest['profile'] == 'azure_public_pilot' else 'graph_reader_laboratory'
    if raw is None or raw['source'].get('evidence_class') != expected:
        _fail('workbench_service_capture_missing')
    if raw.get('capture_integrity',{}).get('status') != 'verified_local_bytes':
        _fail('workbench_service_capture_changed')
    if observed is not None and observed['source'].get('evidence_class') != expected:
        _fail('workbench_service_capture_missing')
    proof = {'operation_id': job.identifier, 'plan_sha256': manifest['saved_plan_sha256'],
        'manifest_sha256': job.sha256, 'reconciliation_sha256': digest(outcome),
        'capture_sha256': facts['graph_capture_sha256'], 'snapshot_id': observed['snapshot_id'] if observed else None,
        'observed_at': raw['observed_at'], 'desired': observed['body'] if observed else None,
        'raw_observation': raw,
        'backend_state': facts['backend_state'], 'source_context': manifest['run_context']}
    return {'artifact_id': row['artifact_id'], 'evidence_class': evidence,
        'baseline_kind': 'verified_protected_service_deployment', 'recorded_at': event['created_at'],
        'proof': proof, 'baseline_admissible': True, 'normalized_comparison_available': observed is not None,
        'source_scope_association': 'compare_by_tenant_and_object_identity',
        'second_plan_convergence': facts['second_plan_convergence'], 'endpoint_effectiveness': 'unestablished',
        'platform_qualified': False, 'cloud_authority': False, 'execution_authorized': False}
