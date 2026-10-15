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
import re
import stat
from uuid import UUID, uuid4

from . import protected, workbench_semantics
from .pin_profiles import CURRENT, LEGACY, context_profile, engine_profiles, tools
from .io import AppError, canonical, digest, file_sha, load_json, read_bytes, parse_json, write_json, sync_directory
from .modeled_service import BASE, FIELDS, VERSION as SERVICE_VERSION, MAX_VISIBILITY_DELAY_READS, ModeledService, compare_semantics

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
    # A plan records the engine version and profile its modeled executor was made for; an operation stored before the
    # migration records neither and is read as it was made. A recorded value must be the executor's own.
    if 'engine_version' in plan or 'pin_profile' in plan:
        made = load_json(root / 'executor' / 'executor.json').get('engine_version', tools(LEGACY)['engine_version'])
        if (plan.get('engine_version') != made or plan.get('pin_profile') != engine_profiles().get(made)):
            _fail('maintenance_engine_changed')
    request = load_json(root / 'executor' / 'preparation.json')
    if digest(request) != plan['engine_request_sha256'] or request['bindings']['desired_value_sha256'] != digest(expected):
        _fail('maintenance_engine_changed')
    return root, plan, journal, desired, request


def _engine_profile(context):
    """The engine version a new operation's modeled executor names, and the profile it belongs to.

    A context whose schema_version is one of the two known versions selects that profile, as generation does. A context
    that carries no schema_version selects no pins, and so does no context at all: the operation is new and takes the build's
    current profile. A schema_version that is present but not recognised is refused, never defaulted."""
    if context is not None and 'schema_version' in context:
        selected = context_profile(context)
        if selected is None:
            _fail('maintenance_context_version')
        return selected['engine_version'], selected['profile']
    return tools(CURRENT)['engine_version'], CURRENT


def _check_cited_intent(store, object_id, desired, context):
    """Refuse a desired body that disagrees with the repository intent its context cites.

    These are the identity, scope and semantic checks deployment-record applies
    after execution, moved forward to preparation. They bind the proposal to one
    recorded intent snapshot; they do not show that the repository is still
    current, that every value is supported, or that execution is authorized.
    """
    if 'repository_intent_id' not in context:
        return
    cited = context['repository_intent_id']
    # deployment-record refuses a null citation too, so it is not read as "none".
    if type(cited) is not str or not cited:
        raise AppError('maintenance_context_intent_invalid',
                       'The context field repository_intent_id must name a repository intent artifact ID.')
    row = store.artifact(cited, kind='repository_intent')
    found = [row['data']] if row is not None else []
    if len(found) != 1:
        raise AppError('maintenance_context_intent_missing', 'The context cites a repository intent this workbench '
                       'store does not hold. Run repository-import again and cite the new intent ID.')
    intent = found[0]
    if (intent.get('target_object_id') != object_id or intent.get('tenant_id') != store.tenant_id
            or context.get('scope') != intent.get('scope')):
        raise AppError('maintenance_context_intent_target_mismatch', 'The cited repository intent is for another '
                       'object, or the context scope is missing or differs from the scope the intent records.')
    comparison = workbench_semantics.compare(intent.get('desired'), desired)
    if comparison['status'] == 'unknown':
        blockers = [('intent ' if side == 'left' else 'desired ') + (row['path'] or '/') + ' ' + row['code']
                    for side in ('left', 'right') for row in comparison[side]['blockers']]
        raise AppError('maintenance_intent_comparison_unknown', 'The desired body cannot be compared with the cited '
                       'repository intent: ' + '; '.join(blockers[:5]) + '. Correct that content before preparing this proposal.')
    if comparison['status'] != 'equal':
        raise AppError('maintenance_desired_intent_mismatch', 'The desired body does not match the cited repository '
                       'intent (' + ', '.join(comparison['changed_fields']) + '). Prepare it from that intent, or import '
                       'the edited repository and cite the new intent.')


def _observation_problem(store, object_id, tenant, service_root, snapshot, observation=None, binding=False):
    """Why the newest observation cannot ground a proposal: (code, reason, observation), or (None, None, observation).

    The code is what propose refuses with. The reason names which check failed, because one code covers several
    (a stale observation may be old, or the service may have changed since it was collected). Shared by propose
    (under the service lock, where it is binding) and proposal_eligibility (advisory), so the workspace shows a
    blocker with the same code the submission would meet.
    """
    # An advisory caller may pass the observation it already shows, so one screen judges freshness once; propose
    # reads its own under the service lock. A binding reading is recorded before the verdict, so a refused stale
    # decision still raises the store's durable clock mark; an advisory one records nothing.
    observation = store.inspect(object_id, bind=binding) if observation is None else observation
    if observation['tenant_id'] != tenant:
        return 'maintenance_observation_incomplete', 'tenant_mismatch', observation
    if observation.get('coverage') != 'complete':
        return 'maintenance_observation_incomplete', 'coverage_incomplete', observation
    latest = observation.get('last_attempt')
    if latest and latest.get('status') != 'complete':
        return 'maintenance_observation_incomplete', 'last_attempt_incomplete', observation
    if observation.get('freshness') != 'fresh':
        return 'maintenance_observation_stale', 'not_fresh', observation
    observed_source = observation.get('source', {})
    if observed_source.get('service_kind') != 'ModeledService' or observed_source.get('service_root') != str(service_root):
        return 'maintenance_observation_source_mismatch', 'source_mismatch', observation
    estate_sha = digest({'tenant_id': tenant, 'objects': snapshot['current']['objects']})
    if (observed_source.get('service_revision') != snapshot['revision']
            or observed_source.get('observed_estate_sha256') != estate_sha):
        return 'maintenance_observation_stale', 'service_changed', observation
    if object_id not in snapshot['current']['objects'] or digest(observation['body']) != digest(snapshot['current']['objects'][object_id]):
        return 'maintenance_observation_stale', 'policy_changed', observation
    return None, None, observation


def proposal_eligibility(store_root, service_root, object_id, *, observation=None):
    """What propose would refuse with because of the observation, or None; read-only and advisory.

    The code is the engine's own; the reason and the recorded facts beside it say which check failed. No lock is
    taken and nothing is written. Submission rechecks everything under the service lock, so this can only say earlier
    what the proposal itself would say.
    """
    service_root = _safe(service_root)
    snapshot = ModeledService(service_root).snapshot()
    tenant = snapshot['current']['tenant_id']
    problem, reason, observation = _observation_problem(_store(_safe(store_root)), _uuid(object_id), tenant, service_root,
                                                        snapshot, observation)
    if problem is None:
        return None
    latest = observation.get('last_attempt') if isinstance(observation.get('last_attempt'), dict) else {}
    return {'code': problem, 'reason': reason, 'observed_revision': observation.get('source', {}).get('service_revision'),
            'service_revision': snapshot['revision'], 'freshness_reasons': list(observation.get('freshness_reasons') or []),
            'next_collection_replaces': observation.get('next_collection_replaces'),
            'ordering_service_root': observation.get('ordering_service_root'),
            'last_attempt_status': latest.get('status')}


def propose(store_root, service_root, object_id, desired_path, output, *, context_path=None, context_sha256=None):
    """Prepare a persisted single-object operation; a refusal says whether it created the operation directory."""
    progress = {'created': False}
    try:
        return _propose(store_root, service_root, object_id, desired_path, output, context_path=context_path,
                        context_sha256=context_sha256, progress=progress)
    except AppError as error:
        error.effects = dict(error.effects or {}, operation_created=progress['created'])
        raise


def _propose(store_root, service_root, object_id, desired_path, output, *, context_path=None, context_sha256=None,
             progress):
    """Prepare a persisted single-object operation from a complete observation.

    With ``context_sha256`` the context bytes read must have exactly that hash, so a caller that checked a
    context binds the same bytes it checked.
    """
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
        if context_sha256 is not None and context['sha256'] != context_sha256:
            _fail('maintenance_source_changed')
    engine_version, pin_profile = _engine_profile(context_value if context_path is not None else None)
    service = ModeledService(service_root)
    with _lock(service_root):
        snapshot = service.snapshot()
        tenant = snapshot['current']['tenant_id']
        _uuid(tenant)
        if context and (context_value.get('tenant_id', tenant) != tenant or context_value.get('cloud', 'public') != 'public'):
            _fail('maintenance_context_target_mismatch')
        store = _store(store_root)
        if context:
            _check_cited_intent(store, object_id, desired, context_value)
        problem, _, observation = _observation_problem(store, object_id, tenant, service_root, snapshot, binding=True)
        if problem:
            _fail(problem)
        before = service.readback(tenant_id=tenant)
        if digest(before) != digest(snapshot['current']) or service.snapshot()['revision'] != snapshot['revision']:
            _fail('maintenance_plan_stale')
        expected = copy.deepcopy(before); expected['objects'][object_id] = copy.deepcopy(desired)
        root.mkdir(mode=0o700); progress['created'] = True; sync_directory(root.parent)
        write_json(root / 'desired.json', desired)
        executor = protected.create_synthetic_executor(root / 'executor', initial_value=before, desired_value=expected,
                                                       engine_version=engine_version)
        request = protected.prepare_native_operation(executor)
        plan = {'schema_version': VERSION, 'operation_id': uuid4().hex,
            'operation_root': str(root), 'store_root': str(store_root), 'service_root': str(service_root),
            'service_version': SERVICE_VERSION, 'service_source_sha256': snapshot['source_sha256'],
            'tenant_id': tenant, 'object_id': object_id, 'before_revision': snapshot['revision'],
            'before_estate': before, 'desired_estate': expected, 'desired_sha256': digest(desired),
            'desired_source': {'path': str(desired_path), 'sha256': source_sha}, 'context': context,
            'observation_sha256': digest(observation), 'engine_request_sha256': digest(request),
            'expires_at': request['expires_at'], 'evidence_class': EVIDENCE, 'cloud_authority': False,
            'native_provider_qualified': False, 'changes': compare_semantics(before, expected),
            'engine_version': engine_version, 'pin_profile': pin_profile}
        write_json(root / 'plan.json', plan)
        journal = {'operation_id': plan['operation_id'], 'plan_sha256': digest(plan), 'status': 'prepared', 'events': []}
        _event(root, journal, 'prepared', approval_digest=digest(plan))
        _register(root, plan, journal)
    return review(root)


def _bound_context(plan):
    """The context this plan bound, parsed from bytes checked against the recorded hash; None if it bound none.

    Every reader of a plan's context uses this, so no decision rests on a context file edited after the plan.
    """
    binding = plan['context']
    if not binding:
        return None
    data = read_bytes(_safe(binding['path']))
    if hashlib.sha256(data).hexdigest() != binding['sha256']:
        _fail('maintenance_source_changed')
    return parse_json(data)


def _repository_review(plan):
    """The cited repository intent and whether it still describes the repository.

    A context file changed since the plan bound it is reported as changed, with its citation unknown.
    """
    try:
        context = _bound_context(plan)
    except AppError as error:
        if error.code != 'maintenance_source_changed':
            raise
        return {'cited': None, 'context_changed': True, 'context_path': plan['context']['path']}
    if not isinstance(context, dict) or 'repository_intent_id' not in context:
        return {'cited': False}
    from .workbench_repository import intent_freshness
    row = _store(plan['store_root']).artifact(context['repository_intent_id'], kind='repository_intent')
    rows = [row] if row is not None else []
    freshness = intent_freshness(rows[0]['data']) if len(rows) == 1 else {'status': 'unavailable', 'reason': 'intent_missing'}
    return {'cited': True, 'repository_intent_id': context['repository_intent_id'], 'scope': context.get('scope'),
            'freshness': freshness['status'], 'changed_sources': freshness.get('sources')}


def approval_window(root, request):
    """The approval window as execute judges it (protected._window), read-only: nothing is recorded.

    state: open, closed (the effective time reached the expiry), closed_recorded (an expiry is recorded beside the
    approval), clock_moved_backward (validity cannot be established now: the clock reads earlier than a recorded
    time or than the plan's creation) or unknown (the recorded time cannot be read). Views show this, never a
    comparison with a bare wall-clock reading.
    """
    from . import clock
    executor = Path(root) / 'executor'
    window = {'opens_at': request['created_at'], 'closes_at': request['expires_at']}
    if (executor / 'expired.json').exists():
        return dict(window, state='closed_recorded')
    try:
        reading = clock.Floor(executor / 'clock.json').peek(protected._now())
    except AppError:
        return dict(window, state='unknown')
    # The one rule execution uses too (clock.window_state); a view only renders it.
    state = clock.window_state(reading, request['created_at'], request['expires_at'])
    return dict(window, state=state, judged_at=reading['effective'])


def review(operation_root):
    from .workbench_diff import field_changes
    root, plan, journal, desired, request = _load(operation_root)
    protected.validate_native_operation(request, executor=protected.SyntheticExecutor(root / 'executor'))
    before = plan['before_estate']['objects'][plan['object_id']]
    return {'operation_id': plan['operation_id'], 'operation_root': str(root),
        'approval_digest': digest(plan), 'status': journal['status'], 'object_id': plan['object_id'],
        'tenant_id': plan['tenant_id'], 'changes': plan['changes'],
        # Derived from the plan itself; field_changes follows the same equality.
        'no_configuration_change': not plan['changes'], 'field_changes': field_changes(before, desired),
        'repository': _repository_review(plan),
        'before': before, 'desired': desired,
        'expires_at': plan['expires_at'], 'approval_window': approval_window(root, request),
        'evidence_class': EVIDENCE, 'cloud_authority': False,
        'native_provider_qualified': False,
        'saved_plan_sha256': request['bindings']['saved_plan_sha256'],
        'saved_plan_json_sha256': request['bindings']['plan_json_sha256']}


def _readback(root, plan, *, kind):
    service = ModeledService(plan['service_root'])
    if service.snapshot()['source_sha256'] != plan['service_source_sha256']:
        _fail('maintenance_service_changed')
    observation = service.readback_observation(tenant_id=plan['tenant_id'])
    observed = observation['estate']
    desired_mismatches = compare_semantics(plan['desired_estate'], observed)
    before_mismatches = compare_semantics(plan['before_estate'], observed)
    classification = 'desired_state_observed' if not desired_mismatches else 'matches_precondition' if not before_mismatches else 'diverged'
    result = {'operation_id': plan['operation_id'], 'classification': classification,
        'observed_estate': observed, 'mismatches': desired_mismatches, 'visibility': observation['visibility'],
        'second_plan': {'status': 'visibility_pending' if observation['visibility']['pending'] else
                        'no_change' if not desired_mismatches else 'changes_require_review',
                        'changes': desired_mismatches, 'evidence_class': 'modeled_semantic_comparison_only'},
        'evidence_class': EVIDENCE, 'replay_authorized': False, 'cloud_authority': False,
        'native_provider_qualified': False}
    # Keep previous reconciliation and failure receipts, including negative ones. Numbering follows the highest
    # existing receipt, not the count, so a missing receipt never makes the next one replace a surviving one.
    numbers = [int(match.group(1)) for match in (re.fullmatch(re.escape(kind) + r'-([0-9]+)\.json', path.name)
                                                 for path in root.glob(kind + '-*.json')) if match]
    destination = root / (kind + '-' + str(max(numbers) + 1 if numbers else 0) + '.json')
    if destination.exists():
        _fail('maintenance_receipt_exists')
    write_json(destination, result)
    return result


def execute(operation_root, *, approve_digest, fault=None, visibility_delay_reads=0):
    """Run one approved operation; a refusal says whether dispatch had started (before it, nothing was sent)."""
    progress = {'dispatched': False}
    try:
        return _execute(operation_root, approve_digest=approve_digest, fault=fault,
                        visibility_delay_reads=visibility_delay_reads, progress=progress)
    except AppError as error:
        error.effects = dict(error.effects or {}, dispatched=progress['dispatched'])
        raise


def _execute(operation_root, *, approve_digest, fault, visibility_delay_reads, progress):
    root, plan, journal, desired, request = _load(operation_root)
    if fault not in (None, 'lost-response', 'after-policy', 'deny', 'throttle'):
        _fail('maintenance_fault_invalid')
    if type(visibility_delay_reads) is not int or not 0 <= visibility_delay_reads <= MAX_VISIBILITY_DELAY_READS:
        _fail('maintenance_visibility_delay_invalid')
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
        binding = plan['desired_source']
        if file_sha(_safe(binding['path'])) != binding['sha256']:
            _fail('maintenance_source_changed')
        # The one read of the bound context: checked here, in the same order as before, and used below.
        context = _bound_context(plan)
        service = ModeledService(plan['service_root'])
        state = service.snapshot()
        if (state['source_sha256'] != plan['service_source_sha256'] or state['revision'] != plan['before_revision']
                or digest(state['current']) != digest(plan['before_estate'])):
            _fail('maintenance_plan_stale')
        if isinstance(context, dict) and 'repository_intent_id' in context:
            # A cited repository intent must still describe the repository at
            # dispatch time, not only when the proposal was prepared.
            from .workbench_repository import require_current_intent
            require_current_intent(_store(plan['store_root']), context['repository_intent_id'])
        executor = protected.SyntheticExecutor(root / 'executor')
        try:
            approval = protected.approve_synthetic_operation(request, executor=executor)
        except AppError as error:
            if error.code in ('expired_request', 'clock_moved_backward', 'clock_floor_invalid', 'clock_reading_invalid',
                              'clock_lock_unavailable'):
                # Audit, before anything is sent: the approval was refused for its window; nothing was dispatched.
                _event(root, journal, 'approval_refused', code=error.code)
                _register(root, plan, journal)
            raise
        # Durable uncertainty is committed before either engine or model write.
        journal['status'] = 'outcome_unknown'
        progress['dispatched'] = True
        _event(root, journal, 'dispatch_started', approval_digest=approve_digest)
        # From here dispatch has started: until a verified readback says otherwise, the service change is unknown.
        result = {'operation_id': plan['operation_id'], 'status': 'outcome_unknown',
            'evidence_class': EVIDENCE, 'cloud_authority': False, 'native_provider_qualified': False,
            'effects': {'dispatched': True, 'service_change': 'unknown'}}
        try:
            engine_result = protected.execute_native_operation(request, root / 'engine-receipts', executor=executor, approval=approval)
            _event(root, journal, 'engine_result', result=engine_result)
            if engine_result['status'] != 'succeeded_verified':
                _fail('maintenance_engine_incomplete')
            if plan['changes']:
                response = service.request('PATCH', BASE + '/' + plan['object_id'], tenant_id=plan['tenant_id'],
                    body=desired, if_match=str(plan['before_revision']), fault=fault,
                    visibility_delay_reads=visibility_delay_reads)
                _event(root, journal, 'service_response', response=response)
                if response['status'] != 200:
                    _fail('maintenance_service_incomplete')
            else:
                _event(root, journal, 'service_no_change', mutation_dispatched=False)
            readback = _readback(root, plan, kind='readback')
            if readback['visibility']['pending']:
                _fail('maintenance_visibility_pending')
            if readback['classification'] != 'desired_state_observed':
                _fail('maintenance_readback_mismatch')
            journal['status'] = 'succeeded_verified'
            _event(root, journal, 'verified', readback_sha256=digest(readback))
            result.update(status='succeeded_verified', readback=readback,
                          effects={'dispatched': True,
                                   'service_change': 'observed_as_desired' if plan['changes'] else 'no_change_needed'})
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
        # The error the operation recorded before this reconcile, so a reader keeps it beside reconcile's readback.
        uncertain = [event for event in journal['events'] if event.get('kind') == 'uncertain']
        result['previous_error_code'] = uncertain[-1].get('error_code') if uncertain else None
        # Readback resolves observable state, never proves a lost response was
        # delivered or grants permission to replay the consumed operation.
        if previous_status != 'prepared' and not result['visibility']['pending']:
            journal['status'] = 'reconciled'
        # The status the journal is left in, so a reader need not infer it from the classification.
        result['journal_status'] = journal['status']
        # Reconcile only reads the service and records what it found; it has no path that sends the change again.
        result['effects'] = {'replayed': False}
        _event(root, journal, 'reconciled', classification=result['classification'], previous_status=previous_status,
               visibility=result['visibility'])
        _register(root, plan, journal)
        return result


def propose_restore(operation_root, output):
    """Restore the original object through a fresh separately reviewed plan; a refusal lists the input files this
    call wrote beside the operation it never created, and whether an operation directory now exists."""
    written = []
    try:
        result = _propose_restore(operation_root, output, written)
    except AppError as error:
        # Read, not assumed: only files this call wrote, and only those still on disk. Additive; no decision changes.
        error.effects = dict(error.effects or {}, files_written=[str(path) for path in written if path.exists()],
                             operation_created=bool((error.effects or {}).get('operation_created')))
        raise
    # Additive: a proposal says which input files it wrote, as a refusal does, so a reader need not look for them.
    return dict(result, files_written=[str(path) for path in written if path.exists()])


def _propose_restore(operation_root, output, written):
    """Restore the original object only through a fresh separately reviewed plan.

    The caller must first collect current observations. The original operation
    is retained and its consumed approval cannot authorize this new proposal.
    A restore reverses any repository intent the original context cited, so it
    is prepared from a derived context without that citation or its scope.
    The original context is used only as the bytes the original plan bound: a
    changed file is refused before anything is written.
    """
    _, plan, _, _, _ = _load(operation_root)
    output = _safe(output)
    desired_path = _safe(str(output) + '.restore-desired.json')
    context_path = plan['context']['path'] if plan['context'] else None
    context_sha256 = plan['context']['sha256'] if plan['context'] else None
    context_value = _bound_context(plan)
    restore_context = None
    if type(context_value) is dict and 'repository_intent_id' in context_value:
        restore_context = _safe(str(output) + '.restore-context.json')
    if desired_path.exists() or output.exists() or (restore_context and restore_context.exists()):
        _fail('maintenance_fresh_output_required')
    write_json(desired_path, plan['before_estate']['objects'][plan['object_id']])
    written.append(desired_path)
    if restore_context:
        derived = {k: v for k, v in context_value.items() if k not in ('repository_intent_id', 'scope')}
        write_json(restore_context, derived)
        written.append(restore_context)
        context_path, context_sha256 = restore_context, hashlib.sha256(canonical(derived) + b'\n').hexdigest()
    return propose(plan['store_root'], plan['service_root'], plan['object_id'], desired_path, output,
                   context_path=context_path, context_sha256=context_sha256)
