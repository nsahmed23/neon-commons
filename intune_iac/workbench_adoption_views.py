"""Persistent navigation to a distinct protected state-only adoption journal.

No graph deployment or last-apply baseline is inferred from import. Every read
reopens the exact registered AdoptionJob; a stored link grants no authority.
"""
from pathlib import Path

from intune_iac.io import AppError, digest

KIND = 'linked_protected_adoption'
MAX_LINKS = 100


def _fail(code):
    raise AppError(code, 'The linked protected adoption journal is unavailable, changed or outside the selected target.')


def _job(store, object_id, root, policy):
    from intune_iac.host_capabilities import require_profile
    require_profile('protected_worker')
    from intune_iac.worker_adoption import AdoptionJob
    job = AdoptionJob(root, policy)
    if job.manifest['tenant_id'] != store.tenant_id or job.manifest['object_ids'] != [object_id]:
        _fail('workbench_adoption_identity')
    return job


def link(store, object_id, root, policy):
    job = _job(store, object_id, root, policy)
    return store.record_artifact('adoption_receipt', None, {
        'schema_version': 'workbench-protected-adoption-link/1', 'tenant_id': store.tenant_id,
        'target_object_id': object_id, 'job_root': str(job.root), 'policy_path': str(Path(policy).absolute()),
        'operation_id': job.identifier, 'manifest_sha256': job.sha256, 'evidence_class': KIND,
        'state_only_adoption': True, 'graph_deployment': False, 'last_apply_baseline_promoted': False,
        'baseline_admissible': False, 'cloud_authority': False, 'execution_authorized': False})


def open_link(store, row):
    data = row['data']
    if (data.get('schema_version') != 'workbench-protected-adoption-link/1' or data.get('evidence_class') != KIND
            or data.get('graph_deployment') is not False or data.get('baseline_admissible') is not False):
        _fail('workbench_adoption_link_shape')
    job = _job(store, data['target_object_id'], data['job_root'], data['policy_path'])
    if job.identifier != data['operation_id'] or job.sha256 != data['manifest_sha256']:
        _fail('workbench_adoption_link_changed')
    return job


def rows(store, object_id):
    result = [row for row in store.artifacts(kind='adoption_receipt')
        if row['data'].get('target_object_id') == object_id and row['data'].get('evidence_class') == KIND]
    if len(result) > MAX_LINKS: _fail('workbench_adoption_history_bound')
    return sorted(result, key=lambda row: row['sequence'], reverse=True)


def project(store, row):
    job = open_link(store, row); review, status = job.review(), job.status(); manifest = review['manifest']
    result = {'status': 'recorded', 'evidence_class': 'protected_state_only_adoption_review',
        'link_artifact_id': row['artifact_id'], 'operation_id': job.identifier, 'manifest_sha256': job.sha256,
        'state_only_adoption': True, 'graph_deployment': False, 'last_apply_baseline_promoted': False,
        'baseline_admissible': False, 'scope': manifest['ownership_binding']['selected_scope'],
        'target': {'tenant_id': store.tenant_id, 'object_id': row['data']['target_object_id']},
        'review': review, 'journal_status': status['status'], 'adoption_journal': status,
        'run_context': manifest['run_context'], 'intended_writer': manifest['intended_writer'],
        'qualification': {'status': 'unverified', 'reason': 'independent_state_graph_and_first_plan_required'},
        'unresolved_risks': ['State adoption cannot establish a Graph deployment or last-apply drift baseline.',
            'No absence of undeclared writers, endpoint effectiveness or organizational approval is established.',
            'The local store and journal are cooperative evidence, not a protected audit anchor.'],
        'platform_qualified': False, 'cloud_authority': False, 'execution_authorized': False}
    if status['status'] == 'adopted_verified':
        outcome = status['outcome']; events = [item for item in status['events'] if item['kind'] == 'adoption_reconciled']
        if (len(events) != 1 or digest(events[0]['payload']) != digest(outcome) or status['dispatches'] != 1
                or status['verification_dispatches'] != 1 or outcome.get('reservation_released') is not True
                or outcome.get('import_replayed') is not False or outcome.get('graph_mutated') is not False):
            _fail('workbench_adoption_reconciliation_changed')
        facts = outcome['independent_completion']; receiving = facts['receiving_state']
        if (facts.get('schema_version') != 'native-adoption-independent-completion/1'
                or facts.get('operation_id') != job.identifier or facts.get('manifest_sha256') != job.sha256
                or facts.get('native_first_plan_exit_code') != 0 or facts.get('first_plan_no_change') is not True
                or receiving.get('manifest_sha256') != job.sha256 or receiving.get('backend_unlocked') is not True):
            _fail('workbench_adoption_readback_changed')
        captured = store.raw_capture_observation(row['data']['target_object_id'], receiving['graph_capture_sha256'])
        expected = 'graph_authenticated_observation' if manifest['profile'] == 'azure_public_pilot' else 'graph_reader_laboratory'
        published = (captured is not None and captured['source'].get('evidence_class') == expected
            and captured.get('capture_integrity', {}).get('status') == 'verified_local_bytes')
        result['qualification'] = {'status': 'recorded_independent_adoption', 'profile': manifest['profile'],
            'receiving_state': receiving, 'native_first_plan_sha256': facts['native_first_plan_sha256'],
            'native_first_plan_json_sha256': facts['native_first_plan_json_sha256'],
            'graph_capture_sha256': receiving['graph_capture_sha256'], 'exact_capture_published': published,
            'published_capture': captured if published else None,
            'management_mapping_status': facts['management_mapping_status'],
            'management_mapping_blockers': facts['management_mapping_blockers'],
            'endpoint_effectiveness': 'unestablished', 'production_approved': False}
    if status['status'] in ('adoption_not_observed_execution_unknown', 'adopted_verified_execution_unknown'):
        outcome = status['outcome']; baseline = status['status'] == 'adoption_not_observed_execution_unknown'
        event_kind = 'adoption_baseline_independently_disposed' if baseline else 'adoption_recovery_plan_reconciled'
        events = [item for item in status['events'] if item['kind'] == event_kind]
        if (type(outcome) is not dict or len(events) != 1 or digest(events[0]['payload']) != digest(outcome)
                or status['dispatches'] != 1 or outcome.get('reservation_released') is not True
                or outcome.get('import_replayed') is not False or outcome.get('graph_mutated') is not False
                or type(outcome.get('previous_import_outcome')) is not dict):
            _fail('workbench_adoption_recovery_changed')
        facts = outcome['independent_completion']; observed = facts['fresh_observation']; proof = observed['adoption_state_proof']
        if (facts['original']['operation_id'] != job.identifier or facts['original']['manifest_sha256'] != job.sha256
                or facts.get('lease_independently_unlocked') is not True or facts.get('lock_metadata_remaining') is not False
                or observed.get('locked') is not False or observed.get('metadata')
                or proof.get('graph_unchanged') is not True or proof.get('original_contract_sha256') != digest(manifest['state_contract'])
                or proof.get('classification') != ('original_baseline' if baseline else 'approved_adoption_successor')):
            _fail('workbench_adoption_recovery_readback_changed')
        if not baseline and (outcome.get('schema_version') != 'adoption-recovery-plan-convergence/1'
                or outcome.get('original_manifest_sha256') != job.sha256
                or outcome.get('native_first_plan', {}).get('first_plan_no_change') is not True
                or outcome.get('native_first_plan', {}).get('exit_code') != 0):
            _fail('workbench_adoption_recovery_plan_changed')
        capture_sha = observed['adoption_capture']['capture_sha256']
        captured = store.raw_capture_observation(row['data']['target_object_id'], capture_sha)
        expected = 'graph_authenticated_observation' if manifest['profile'] == 'azure_public_pilot' else 'graph_reader_laboratory'
        published = (captured is not None and captured['source'].get('evidence_class') == expected
            and captured.get('capture_integrity', {}).get('status') == 'verified_local_bytes')
        result['qualification'] = {'status': status['status'], 'profile': manifest['profile'],
            'original_execution_outcome': 'unknown', 'adoption_observed': not baseline, 'import_replay_authorized': False,
            'receiving_state': observed['state'], 'graph_capture_sha256': capture_sha,
            'exact_capture_published': published, 'published_capture': captured if published else None,
            'reservation_released': True, 'first_plan': outcome.get('native_first_plan'),
            'previous_import_outcome': outcome['previous_import_outcome'],
            'endpoint_effectiveness': 'unestablished', 'production_approved': False}
    return result


def history(store, object_id, *, native_reader=None):
    result = []
    for row in rows(store, object_id):
        if native_reader is not None:
            result.append(native_reader.reject('adoption_history', row=row)); continue
        try: result.append(project(store, row))
        except (AppError, OSError, KeyError, TypeError) as error:
            result.append({'status': 'unknown', 'reason': 'linked_adoption_unavailable_or_changed',
                'error_code': getattr(error, 'code', type(error).__name__), 'link_artifact_id': row['artifact_id'],
                'operation_id': row['data'].get('operation_id'), 'baseline_admissible': False,
                'graph_deployment': False, 'execution_authorized': False})
    return {'schema_version': 'workbench-protected-adoption-history/1', 'tenant_id': store.tenant_id,
        'object_id': object_id, 'operations': result, 'graph_deployment': False,
        'last_apply_baseline_promoted': False, 'cloud_authority': False, 'execution_authorized': False}
