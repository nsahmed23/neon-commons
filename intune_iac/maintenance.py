"""Bounded maintenance of the existing durable service model.

This joins collected observations, the protected exact-plan child-process
executor, a single-object modeled PATCH, independent GET readback and recovery.
It never contacts Graph or launches a provider. The durable local approval
digest is user intent for this synthetic profile, never cloud authority.
"""
from __future__ import annotations

import copy
from contextlib import contextmanager
import fcntl
import hashlib
import os
from pathlib import Path
import stat
from uuid import UUID, uuid4

from . import protected
from .io import AppError, digest, file_sha, load_json, read_bytes, parse_json, write_json, sync_directory
from .modeled_service import BASE, FIELDS, VERSION as SERVICE_VERSION, ModeledService, compare_semantics

VERSION = 'intune-maintenance/1.0'
EVIDENCE = 'synthetic_local_process_and_modeled_service_only'


def _fail(code):
    raise AppError(code, 'Maintenance evidence is incomplete, changed, stale, or outside the local model profile.')


def _safe(path):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        _fail('maintenance_unsafe_path')
    return path


def _uuid(value):
    try:
        if type(value) is not str or str(UUID(value)) != value:
            _fail('maintenance_identity_invalid')
    except (ValueError, AttributeError):
        _fail('maintenance_identity_invalid')
    return value


def _desired(value):
    """Validate the bounded model's fields without asserting provider mapping."""
    if type(value) is not dict or set(value) != FIELDS:
        _fail('maintenance_desired_shape')
    if type(value['name']) is not str or not value['name'] or len(value['name']) > 512:
        _fail('maintenance_desired_shape')
    if value['description'] is not None and (type(value['description']) is not str or len(value['description']) > 1500):
        _fail('maintenance_desired_shape')
    if value['platforms'] != 'windows10' or value['technologies'] != ['mdm']:
        _fail('maintenance_unsupported_family')
    tags = value['role_scope_tag_ids']
    if type(tags) is not list or any(type(x) is not str or not x for x in tags) or len(set(tags)) != len(tags):
        _fail('maintenance_desired_shape')
    settings = value['settings']
    if type(settings) is not dict or set(settings) != {'settings'} or type(settings['settings']) is not list or not settings['settings']:
        _fail('maintenance_settings_invalid')
    ids = set()
    for row in settings['settings']:
        if type(row) is not dict or set(row) != {'id', 'settingInstance'} or type(row['id']) is not str or row['id'] in ids:
            _fail('maintenance_settings_invalid')
        ids.add(row['id'])
        item = row['settingInstance']
        if type(item) is not dict or type(item.get('@odata.type')) is not str or type(item.get('settingDefinitionId')) is not str:
            _fail('maintenance_settings_invalid')
        # This is an exact JSON model, not permission to widen the provider's
        # supported settings schema. Unknown typed subtrees remain verbatim.
    assignments = value['assignments']
    if type(assignments) is not list or len(assignments) > 1024:
        _fail('maintenance_assignments_invalid')
    seen = set()
    for row in assignments:
        if type(row) is not dict or row.get('type') not in ('groupAssignmentTarget', 'exclusionGroupAssignmentTarget', 'allDevicesAssignmentTarget', 'allLicensedUsersAssignmentTarget'):
            _fail('maintenance_assignments_invalid')
        keys = {'type', 'filter_type'}
        if row['type'] in ('groupAssignmentTarget', 'exclusionGroupAssignmentTarget'):
            keys.add('group_id'); _uuid(row.get('group_id'))
        if row.get('filter_type') not in ('none', 'include', 'exclude'):
            _fail('maintenance_filter_invalid')
        if row['filter_type'] != 'none':
            keys.add('filter_id'); _uuid(row.get('filter_id'))
        if row['type'] == 'exclusionGroupAssignmentTarget' and row['filter_type'] != 'none':
            _fail('maintenance_filter_invalid')
        if set(row) != keys or digest(row) in seen:
            _fail('maintenance_assignments_invalid')
        seen.add(digest(row))
    return value


@contextmanager
def _lock(service_root):
    path = _safe(Path(service_root) / 'maintenance.lock')
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            _fail('maintenance_lock_invalid')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            _fail('maintenance_writer_busy')
        yield
    finally:
        os.close(fd)


def _store(root):
    from .workbench_store import WorkbenchStore
    return WorkbenchStore(root)


def _event(root, journal, kind, **data):
    previous = digest(journal['events'][-1]) if journal['events'] else '0' * 64
    journal['events'].append({'sequence': len(journal['events']), 'kind': kind,
                              'previous_sha256': previous, **data})
    write_json(root / 'journal.json', journal)


def _register(root, plan, journal):
    _store(plan['store_root']).record_operation(plan['operation_id'], {
        'object_id': plan['object_id'], 'operation_root': str(root),
        'approval_digest': digest(plan), 'status': journal['status'],
        'evidence_class': EVIDENCE, 'cloud_authority': False,
        'journal_sha256': digest(journal)})


def _load(operation_root):
    root = _safe(operation_root)
    plan = load_json(root / 'plan.json')
    journal = load_json(root / 'journal.json')
    if (plan.get('schema_version') != VERSION or plan.get('operation_root') != str(root)
            or plan.get('service_version') != SERVICE_VERSION
            or plan.get('evidence_class') != EVIDENCE or plan.get('cloud_authority') is not False
            or journal.get('plan_sha256') != digest(plan)
            or journal.get('operation_id') != plan.get('operation_id')
            or journal.get('status') not in ('prepared', 'outcome_unknown', 'succeeded_verified', 'reconciled', 'rejected')):
        _fail('maintenance_evidence_changed')
    _uuid(plan['object_id']); _uuid(plan['tenant_id'])
    previous = '0' * 64
    for index, event in enumerate(journal['events']):
        if event.get('sequence') != index or event.get('previous_sha256') != previous:
            _fail('maintenance_journal_changed')
        previous = digest(event)
    if not journal['events'] or journal['events'][0]['kind'] != 'prepared':
        _fail('maintenance_journal_changed')
    desired = load_json(root / 'desired.json')
    if digest(_desired(desired)) != plan['desired_sha256']:
        _fail('maintenance_desired_changed')
    expected = copy.deepcopy(plan['before_estate'])
    expected['objects'][plan['object_id']] = desired
    if digest(expected) != digest(plan['desired_estate']):
        _fail('maintenance_scope_changed')
    request = load_json(root / 'executor' / 'preparation.json')
    if digest(request) != plan['engine_request_sha256'] or request['bindings']['desired_value_sha256'] != digest(expected):
        _fail('maintenance_engine_changed')
    return root, plan, journal, desired, request


def propose(store_root, service_root, object_id, desired_path, output, *, context_path=None):
    """Prepare a persisted single-object operation from a complete observation."""
    root, store_root, service_root = map(_safe, (output, store_root, service_root))
    desired_path = _safe(desired_path)
    if root.exists() or not root.parent.is_dir():
        _fail('maintenance_fresh_output_required')
    if any(root == p or root in p.parents or p in root.parents for p in (store_root, service_root, desired_path)):
        _fail('maintenance_path_overlap')
    object_id = _uuid(object_id)
    source_bytes = read_bytes(desired_path)
    desired = _desired(parse_json(source_bytes))
    source_sha = hashlib.sha256(source_bytes).hexdigest()
    context = None
    if context_path is not None:
        context_path = _safe(context_path)
        context_bytes = read_bytes(context_path)
        context_value = parse_json(context_bytes)
        if type(context_value) is not dict:
            _fail('maintenance_context_invalid')
        context = {'path': str(context_path), 'sha256': hashlib.sha256(context_bytes).hexdigest()}
    service = ModeledService(service_root)
    with _lock(service_root):
        snapshot = service.snapshot()
        tenant = snapshot['current']['tenant_id']
        _uuid(tenant)
        if context and (context_value.get('tenant_id', tenant) != tenant or context_value.get('cloud', 'public') != 'public'):
            _fail('maintenance_context_target_mismatch')
        observation = _store(store_root).inspect(object_id)
        if observation['tenant_id'] != tenant or observation.get('coverage') != 'complete':
            _fail('maintenance_observation_incomplete')
        latest = observation.get('last_attempt')
        if latest and latest.get('status') != 'complete':
            _fail('maintenance_observation_incomplete')
        if observation.get('freshness') != 'fresh':
            _fail('maintenance_observation_stale')
        observed_source = observation.get('source', {})
        if observed_source.get('service_kind') != 'ModeledService' or observed_source.get('service_root') != str(service_root):
            _fail('maintenance_observation_source_mismatch')
        estate_sha = digest({'tenant_id': tenant, 'objects': snapshot['current']['objects']})
        if (observed_source.get('service_revision') != snapshot['revision']
                or observed_source.get('observed_estate_sha256') != estate_sha):
            _fail('maintenance_observation_stale')
        if object_id not in snapshot['current']['objects'] or digest(observation['body']) != digest(snapshot['current']['objects'][object_id]):
            _fail('maintenance_observation_stale')
        before = service.readback(tenant_id=tenant)
        if digest(before) != digest(snapshot['current']) or service.snapshot()['revision'] != snapshot['revision']:
            _fail('maintenance_plan_stale')
        expected = copy.deepcopy(before); expected['objects'][object_id] = copy.deepcopy(desired)
        root.mkdir(mode=0o700); sync_directory(root.parent)
        write_json(root / 'desired.json', desired)
        executor = protected.create_synthetic_executor(root / 'executor', initial_value=before, desired_value=expected)
        request = protected.prepare_native_operation(executor)
        plan = {'schema_version': VERSION, 'operation_id': uuid4().hex,
            'operation_root': str(root), 'store_root': str(store_root), 'service_root': str(service_root),
            'service_version': SERVICE_VERSION, 'service_source_sha256': snapshot['source_sha256'],
            'tenant_id': tenant, 'object_id': object_id, 'before_revision': snapshot['revision'],
            'before_estate': before, 'desired_estate': expected, 'desired_sha256': digest(desired),
            'desired_source': {'path': str(desired_path), 'sha256': source_sha}, 'context': context,
            'observation_sha256': digest(observation), 'engine_request_sha256': digest(request),
            'expires_at': request['expires_at'], 'evidence_class': EVIDENCE, 'cloud_authority': False,
            'native_provider_qualified': False, 'changes': compare_semantics(before, expected)}
        write_json(root / 'plan.json', plan)
        journal = {'operation_id': plan['operation_id'], 'plan_sha256': digest(plan), 'status': 'prepared', 'events': []}
        _event(root, journal, 'prepared', approval_digest=digest(plan))
        _register(root, plan, journal)
    return review(root)


def review(operation_root):
    root, plan, journal, desired, request = _load(operation_root)
    protected.validate_native_operation(request, executor=protected.SyntheticExecutor(root / 'executor'))
    return {'operation_id': plan['operation_id'], 'operation_root': str(root),
        'approval_digest': digest(plan), 'status': journal['status'], 'object_id': plan['object_id'],
        'tenant_id': plan['tenant_id'], 'changes': plan['changes'],
        'before': plan['before_estate']['objects'][plan['object_id']], 'desired': desired,
        'expires_at': plan['expires_at'], 'evidence_class': EVIDENCE, 'cloud_authority': False,
        'native_provider_qualified': False,
        'saved_plan_sha256': request['bindings']['saved_plan_sha256'],
        'saved_plan_json_sha256': request['bindings']['plan_json_sha256']}


def _readback(root, plan, *, kind):
    service = ModeledService(plan['service_root'])
    if service.snapshot()['source_sha256'] != plan['service_source_sha256']:
        _fail('maintenance_service_changed')
    observed = service.readback(tenant_id=plan['tenant_id'])
    desired_mismatches = compare_semantics(plan['desired_estate'], observed)
    before_mismatches = compare_semantics(plan['before_estate'], observed)
    classification = 'desired_state_observed' if not desired_mismatches else 'matches_precondition' if not before_mismatches else 'diverged'
    result = {'operation_id': plan['operation_id'], 'classification': classification,
        'observed_estate': observed, 'mismatches': desired_mismatches,
        'second_plan': {'status': 'no_change' if not desired_mismatches else 'changes_require_review',
                        'changes': desired_mismatches, 'evidence_class': 'modeled_semantic_comparison_only'},
        'evidence_class': EVIDENCE, 'replay_authorized': False, 'cloud_authority': False,
        'native_provider_qualified': False}
    # Keep previous reconciliation and failure receipts, including negative ones.
    number = len(list(root.glob(kind + '-*.json')))
    write_json(root / (kind + '-' + str(number) + '.json'), result)
    return result


def execute(operation_root, *, approve_digest, fault=None):
    root, plan, journal, desired, request = _load(operation_root)
    if fault not in (None, 'lost-response', 'after-policy', 'deny', 'throttle'):
        _fail('maintenance_fault_invalid')
    if type(approve_digest) is not str or approve_digest != digest(plan):
        _fail('maintenance_approval_required')
    with _lock(plan['service_root']):
        root, plan, journal, desired, request = _load(root)
        # The exact approval is rechecked after acquiring the target lock: a
        # substituted plan must not redirect dispatch during lock contention.
        if approve_digest != digest(plan):
            _fail('maintenance_approval_required')
        if journal['status'] != 'prepared':
            _fail('maintenance_replay_forbidden')
        for binding in (plan['desired_source'], plan['context']):
            if binding and file_sha(_safe(binding['path'])) != binding['sha256']:
                _fail('maintenance_source_changed')
        service = ModeledService(plan['service_root'])
        state = service.snapshot()
        if (state['source_sha256'] != plan['service_source_sha256'] or state['revision'] != plan['before_revision']
                or digest(state['current']) != digest(plan['before_estate'])):
            _fail('maintenance_plan_stale')
        executor = protected.SyntheticExecutor(root / 'executor')
        approval = protected.approve_synthetic_operation(request, executor=executor)
        # Durable uncertainty is committed before either engine or model write.
        journal['status'] = 'outcome_unknown'
        _event(root, journal, 'dispatch_started', approval_digest=approve_digest)
        result = {'operation_id': plan['operation_id'], 'status': 'outcome_unknown',
            'evidence_class': EVIDENCE, 'cloud_authority': False, 'native_provider_qualified': False}
        try:
            engine_result = protected.execute_native_operation(request, root / 'engine-receipts', executor=executor, approval=approval)
            _event(root, journal, 'engine_result', result=engine_result)
            if engine_result['status'] != 'succeeded_verified':
                _fail('maintenance_engine_incomplete')
            if plan['changes']:
                response = service.request('PATCH', BASE + '/' + plan['object_id'], tenant_id=plan['tenant_id'],
                    body=desired, if_match=str(plan['before_revision']), fault=fault)
                _event(root, journal, 'service_response', response=response)
                if response['status'] != 200:
                    _fail('maintenance_service_incomplete')
            else:
                _event(root, journal, 'service_no_change', mutation_dispatched=False)
            readback = _readback(root, plan, kind='readback')
            if readback['classification'] != 'desired_state_observed':
                _fail('maintenance_readback_mismatch')
            journal['status'] = 'succeeded_verified'
            _event(root, journal, 'verified', readback_sha256=digest(readback))
            result.update(status='succeeded_verified', readback=readback)
        except Exception as error:
            journal['status'] = 'outcome_unknown'
            _event(root, journal, 'uncertain', error_code=getattr(error, 'code', 'maintenance_execution_failed'))
            result['error_code'] = getattr(error, 'code', 'maintenance_execution_failed')
        _register(root, plan, journal)
        return result


def reconcile(operation_root):
    root, plan, journal, _, _ = _load(operation_root)
    plan_sha = digest(plan)
    with _lock(plan['service_root']):
        root, plan, journal, _, _ = _load(root)
        if digest(plan) != plan_sha:
            _fail('maintenance_evidence_changed')
        previous_status = journal['status']
        result = _readback(root, plan, kind='reconciliation')
        result['previous_status'] = previous_status
        # Readback resolves observable state, never proves a lost response was
        # delivered or grants permission to replay the consumed operation.
        if previous_status != 'prepared':
            journal['status'] = 'reconciled'
        _event(root, journal, 'reconciled', classification=result['classification'], previous_status=previous_status)
        _register(root, plan, journal)
        return result


def propose_restore(operation_root, output):
    """Restore the original object only through a fresh separately reviewed plan.

    The caller must first collect current observations. The original operation
    is retained and its consumed approval cannot authorize this new proposal.
    """
    _, plan, _, _, _ = _load(operation_root)
    output = _safe(output)
    desired_path = _safe(str(output) + '.restore-desired.json')
    if desired_path.exists() or output.exists():
        _fail('maintenance_fresh_output_required')
    write_json(desired_path, plan['before_estate']['objects'][plan['object_id']])
    return propose(plan['store_root'], plan['service_root'], plan['object_id'], desired_path, output,
                   context_path=plan['context']['path'] if plan['context'] else None)
