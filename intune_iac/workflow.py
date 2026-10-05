"""Receipt-backed local cohort authoring; no receipt grants external authority.

Milestones describe completed local observations, including an ownership
assessment whose result is unknown. They do not mean provider qualification or
adoption. Every reconstruction rereads inputs and source-derived generated files.
"""
from __future__ import annotations

import hashlib
import os
import re
import secrets
import stat
import tempfile
from pathlib import Path
from uuid import UUID

from . import engine, runner
from .io import AppError, digest, file_sha, load_json, write_json

VERSION = '2.1.0'
ALGORITHM = 'local-cohort/1.0.0'
STAGES = ('repository', 'source', 'inventory', 'selection', 'ownership', 'mapping', 'generation', 'validation', 'review')
STATES = ('repository_inspection', 'source_selection', 'inventory', 'object_selection', 'ownership_detection', 'provider_mapping', 'generation_dispatch', 'local_validation', 'adoption_preview', 'complete_local')
FRONTIERS = dict(zip(STATES, range(10))) | {'generate': 6, 'partial_generate': 6, 'file_conflict': 6, 'reconciliation_required': 9}
TRIGGERS = {'repository': 0, 'locator': 1, 'identity': 1, 'source': 2, 'selection': 3, 'mapping': 5, 'target': 6, 'output': 6, 'cohort': 8}
SESSION_KEYS = {'schema_version', 'saved_state', 'completed', 'paths', 'repository', 'selected_ids', 'cohort', 'target', 'mapping_status', 'fingerprints', 'lifecycle', 'in_flight_outcome'}


def _safe(path):
    result = Path(path).absolute()
    if any(item.is_symlink() for item in (result, *result.parents)):
        raise AppError('workflow_unsafe_path', 'Guided evidence paths must not contain symbolic links.')
    return result.resolve()


def _uuid(value):
    try:
        return str(UUID(value))
    except (ValueError, TypeError, AttributeError):
        raise AppError('workflow_invalid_uuid', 'Use immutable UUIDs for selection.') from None


def _ids(values, allow_empty=False):
    if not isinstance(values, list) or len(values) > 100 or (not values and not allow_empty):
        raise AppError('workflow_selection_limit', 'Select between one and 100 policy UUIDs.')
    result = [_uuid(value) for value in values]
    if len(set(result)) != len(result):
        raise AppError('workflow_duplicate_selection', 'Duplicate selected identities are not supported.')
    return sorted(result)


def _cohort(value):
    if not isinstance(value, dict) or set(value) != {'ring', 'group_ids'} or value['ring'] not in ('ring0', 'ring1', 'ring2', 'ring3', 'ring4'):
        raise AppError('workflow_invalid_cohort', 'Cohort requires a ring and explicit group UUIDs.')
    return {'ring': value['ring'], 'group_ids': _ids(value['group_ids'], allow_empty=True)}


def _new(paths, repository=None):
    return {'schema_version': VERSION, 'saved_state': STATES[0], 'completed': [], 'paths': paths,
            'repository': repository, 'selected_ids': [], 'cohort': {'ring': 'ring0', 'group_ids': []},
            'target': {}, 'mapping_status': 'unknown', 'fingerprints': {}, 'lifecycle': 'active', 'in_flight_outcome': 'none'}


def _load(session_path):
    value = load_json(_safe(session_path))
    if isinstance(value, dict) and value.get('schema_version') == '1.0.0':
        raise AppError('guided_legacy_session', 'Use the original wizard for this v1 session, or a new guided session path.')
    valid = isinstance(value, dict) and set(value) == SESSION_KEYS and value['schema_version'] == VERSION
    if not valid or not isinstance(value['saved_state'], str) or value['saved_state'] not in FRONTIERS or value['lifecycle'] not in ('active', 'suspended', 'cancelled', 'complete_local') or value['in_flight_outcome'] not in ('none', 'unknown'):
        raise AppError('workflow_invalid_session', 'Unsupported guided session record.')
    completed = value['completed']
    if not isinstance(completed, list) or completed != list(STAGES[:len(completed)]) or len(completed) > 9:
        raise AppError('workflow_invalid_session', 'Milestone completion must be a contiguous prefix.')
    if value['mapping_status'] not in ('unknown', 'complete', 'partial'):
        raise AppError('workflow_invalid_session', 'Unsupported mapping status.')
    if not isinstance(value['paths'], dict) or set(value['paths']) != {'input', 'context', 'output'} or any(not isinstance(p, str) or not p or len(p) > 4096 for p in value['paths'].values()):
        raise AppError('workflow_invalid_session', 'Guided source, context and output paths are required.')
    if value['repository'] is not None and (not isinstance(value['repository'], str) or not value['repository'] or len(value['repository']) > 4096):
        raise AppError('workflow_invalid_session', 'Repository locator is invalid.')
    if not isinstance(value['target'], dict) or not set(value['target']) <= {'stack', 'component'} or any(not isinstance(v, str) or not re.fullmatch(r'[A-Za-z0-9_./-]{1,256}', v) for v in value['target'].values()):
        raise AppError('workflow_invalid_session', 'Target selectors are invalid.')
    if not isinstance(value['fingerprints'], dict) or not set(value['fingerprints']) <= set(TRIGGERS) or any(not isinstance(h, str) or not re.fullmatch('[0-9a-f]{64}', h) for h in value['fingerprints'].values()):
        raise AppError('workflow_invalid_session', 'Saved fingerprints are invalid.')
    value['selected_ids'] = _ids(value['selected_ids'], allow_empty=True)
    value['cohort'] = _cohort(value['cohort'])
    return value


def _scopes(session_path, state):
    session = _safe(session_path)
    evidence = _safe(str(session) + '.evidence')
    paths = {key: _safe(path) for key, path in state['paths'].items()}
    protected = [session, evidence, paths['input'], paths['context']]
    output = paths['output']
    if any(output == path or output in path.parents for path in protected):
        raise AppError('workflow_path_conflict', 'Output must not contain evidence, session or source inputs.')
    for source in (paths['input'], paths['context']):
        if source == session or source == evidence or evidence in source.parents or source in evidence.parents:
            raise AppError('workflow_path_conflict', 'Sources must be separate from guided persistence.')
    return evidence


def _context(state):
    from .wizard import _CONTEXT_KEYS
    value = load_json(_safe(state['paths']['context']))
    extra = {'tenant_assurance', 'implementation', 'repository_source_fingerprint'}
    if not isinstance(value, dict) or not set(value) <= _CONTEXT_KEYS | extra or value.get('authorization') != 'emit_only':
        raise AppError('workflow_invalid_context', 'A bounded emit-only context is required.')
    # These values are consumed as target intent, never as executable strings.
    if any(not isinstance(v, (str, bool)) for v in value.values()):
        raise AppError('workflow_invalid_context', 'Context values must be bounded scalar intent.')
    if any(isinstance(v, str) and len(v) > 1024 for v in value.values()):
        raise AppError('workflow_invalid_context', 'Context values exceed the bounded contract.')
    _uuid(value.get('tenant_id'))
    return dict(value, **state['target'])


def _inspect_one(state, context, policy_id):
    # A temporary private context supports existing path-based engine APIs. No raw
    # export is copied and the temporary context is removed after inspection.
    with tempfile.TemporaryDirectory(prefix='intune-guided-') as temporary:
        path = Path(temporary) / 'context.json'
        write_json(path, dict(context, selected_policy_id=policy_id))
        return engine.inspect_source(state['paths']['input'], path)


def _verify_one(state, context, policy_id):
    with tempfile.TemporaryDirectory(prefix='intune-guided-') as temporary:
        path = Path(temporary) / 'context.json'
        write_json(path, dict(context, selected_policy_id=policy_id))
        return engine.verify_project(state['paths']['input'], path, Path(state['paths']['output']) / policy_id)


def _observe(session_path, state):
    from .wizard import _policy_ids
    from reference.validation import schema_errors
    _scopes(session_path, state)
    source_path = _safe(state['paths']['input'])
    context_path = _safe(state['paths']['context'])
    before = {'source': file_sha(source_path), 'context': file_sha(context_path)}
    source = load_json(source_path)
    if not isinstance(source, dict) or schema_errors('export-intake', source):
        raise AppError('invalid_capture', 'Capture intake schema did not validate.')
    context = _context(state)
    observed_ids = sorted(_policy_ids(source_path))
    if not observed_ids or len(observed_ids) > 1000:
        raise AppError('workflow_inventory_limit', 'Guided inventory supports one to 1000 observed policies.')
    if not set(state['selected_ids']) <= set(observed_ids):
        raise AppError('workflow_selection_missing', 'A selected policy is absent from the current capture.')
    repository = {'mode': 'context_only', 'revision_digest': digest(context.get('repository_revision'))}
    if state['repository'] is not None:
        if source['synthetic']:
            raise AppError('syntheticcore_target_unqualified', 'The synthetic generator cannot qualify repository targets.')
        from .repository import discover_repository
        discovery = discover_repository(_safe(state['repository']))
        from .wizard import _repository_context
        target_context = _repository_context({'root': state['repository'], 'stack': context.get('stack'),
                                              'component': context.get('component'), 'selected_policy_id': observed_ids[0]}, source_path)
        if target_context['tenant_id'] != context['tenant_id'] or target_context['cloud'] != context.get('cloud'):
            raise AppError('workflow_target_mismatch', 'Source and target identity intent do not match.')
        for field in ('stack', 'component', 'implementation', 'repository_source_fingerprint', 'target_assurance'):
            context[field] = target_context[field]
        repository = {'mode': 'literal_observation', 'discovery_digest': digest(discovery), 'status': discovery.get('status')}
    mappings = {}
    for policy_id in state['selected_ids']:
        inspected = _inspect_one(state, context, policy_id)
        mappings[policy_id] = {'source_mode': inspected['source_mode'], 'mapping_complete': inspected['status'] == 'ready',
                               'normalized_digest': digest(inspected['normalized']),
                               'blocker_count': len(inspected.get('blockers', []))}
    status = 'unknown' if not mappings else ('complete' if all(item['mapping_complete'] for item in mappings.values()) else 'partial')
    target_fields = {'stack', 'component', 'state_key', 'backend_owner', 'implementation', 'target_assurance', 'repository_source_fingerprint'}
    mapping_context = {k: v for k, v in context.items() if k not in target_fields | {'selected_policy_id'}}
    target = {k: v for k, v in context.items() if k in target_fields}
    fingerprints = {'repository': digest(repository), 'locator': digest([str(source_path), str(context_path)]),
                    'identity': digest([context.get('tenant_id'), context.get('cloud')]), 'source': before['source'],
                    'selection': digest(state['selected_ids']), 'mapping': digest(mapping_context),
                    'target': digest(target), 'output': digest(state['paths']['output']), 'cohort': digest(state['cohort'])}
    payloads = {'repository': repository,
                'source': {'locator_digest': fingerprints['locator'], 'identity_digest': fingerprints['identity']},
                'inventory': {'source_sha256': before['source'], 'observed_policy_ids': observed_ids, 'synthetic': source['synthetic']},
                'selection': {'selected_ids': state['selected_ids']},
                'ownership': {'status': 'unknown', 'writer_qualified': False, 'scope': 'local_assessment'},
                'mapping': {'mapping_status': status, 'policies': mappings, 'mapping_context_digest': fingerprints['mapping']}}
    if before != {'source': file_sha(source_path), 'context': file_sha(context_path)}:
        raise AppError('workflow_evidence_changed', 'Capture or context changed during observation.')
    return {'fingerprints': fingerprints, 'payloads': payloads, 'context': context, 'synthetic': source['synthetic'], 'mapping_status': status, 'observed_ids': observed_ids}


def _generation_payload(state, observed):
    results = {}
    root = _safe(state['paths']['output'])
    if not root.is_dir() or {p.name for p in root.iterdir()} != set(state['selected_ids']):
        raise AppError('workflow_output_closure', 'Generated cohort directory differs from its selected identities.')
    for policy_id in state['selected_ids']:
        result = _verify_one(state, observed['context'], policy_id)
        results[policy_id] = {'manifest_sha256': result['manifest_sha256'], 'file_count': result['file_count']}
    return {'policies': results, 'target_digest': observed['fingerprints']['target'], 'output_digest': observed['fingerprints']['output']}


def _payload(stage, state, observed):
    if stage in observed['payloads']:
        return observed['payloads'][stage]
    generated = _generation_payload(state, observed)
    if stage == 'generation':
        return generated
    if stage == 'validation':
        return {'generation_digest': digest(generated), 'independent_preservation_verified': True}
    return {'generation_digest': digest(generated), 'cohort': state['cohort'], 'review_kind': 'local_handoff', 'external_execution': False}


def _receipt(stage, state, observed, dependencies):
    return {'schema_version': VERSION, 'algorithm': ALGORITHM, 'milestone': stage,
            'assurance': 'local_consistency_only', 'synthetic': observed['synthetic'],
            'dependencies': dict(dependencies), 'payload': _payload(stage, state, observed)}


def _next(index, status):
    return ('generate' if status == 'complete' else 'partial_generate') if index == 6 else STATES[index]


def _reconstruct(session_path, state, observed):
    evidence = _scopes(session_path, state)
    reasons = []
    verified = []
    dependencies = {}
    try:
        index = load_json(_safe(evidence / 'index.json'))
        if not isinstance(index, dict) or set(index) != {'schema_version', 'algorithm', 'receipts'} or index['schema_version'] != VERSION or index['algorithm'] != ALGORITHM or not isinstance(index['receipts'], dict) or not set(index['receipts']) <= set(STAGES):
            raise AppError('workflow_receipt_index', 'Invalid receipt index.')
        for stage in STAGES:
            path = _safe(evidence / (stage + '.json'))
            if stage not in index['receipts'] or file_sha(path) != index['receipts'][stage]:
                break
            if load_json(path) != _receipt(stage, state, observed, dependencies):
                break
            verified.append(stage)
            dependencies[stage] = index['receipts'][stage]
    except (AppError, OSError, ValueError):
        reasons.append('receipt_reconstruction_incomplete')
    changed = [key for key in TRIGGERS if state['fingerprints'].get(key) != observed['fingerprints'][key]]
    earliest = min([TRIGGERS[key] for key in changed] + [9])
    cap = min(FRONTIERS[state['saved_state']], earliest, len(state['completed']))
    completed = list(STAGES[:min(cap, len(verified))])
    next_state = _next(len(completed), observed['mapping_status'])
    if state['in_flight_outcome'] == 'unknown':
        next_state = 'reconciliation_required'
        reasons.append('ambiguous_operation_no_replay')
    return {'schema_version': VERSION, 'next_state': next_state, 'milestone_index': len(completed),
            'verified_completed': completed, 'external_verified_completed': [],
            'mapping_status': observed['mapping_status'], 'reasons': reasons + ['invalidated:' + key for key in sorted(changed)],
            'execution_authorized': False, 'ownership': 'unknown', 'cohort_membership': 'unverified'}


def reconstruct_progress(session_path):
    """Read receipts and actual current artifacts; no persisted completion is trusted."""
    state = _load(session_path)
    return _reconstruct(session_path, state, _observe(session_path, state))


def preview_resume(session_path, changes):
    """Read-only what-if routing for validated cohort or target intent edits."""
    state = _load(session_path)
    if not isinstance(changes, dict) or not set(changes) <= {'cohort', 'stack', 'component'}:
        raise AppError('workflow_invalid_edit', 'Only cohort and literal target edits are supported.')
    if 'cohort' in changes:
        state['cohort'] = _cohort(changes['cohort'])
    for key in ('stack', 'component'):
        if key in changes:
            value = changes[key]
            if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_./-]{1,256}', value):
                raise AppError('workflow_invalid_edit', 'Target selectors must be bounded literal strings.')
            state['target'][key] = value
    return _reconstruct(session_path, state, _observe(session_path, state))


def _checkpoint(session_path, state, observed, count, guard, next_state=None):
    evidence = _scopes(session_path, state)
    dependencies = {}
    for stage in STAGES[:count]:
        path = _safe(evidence / (stage + '.json'))
        guard()
        write_json(path, _receipt(stage, state, observed, dependencies))
        dependencies[stage] = file_sha(path)
    guard()
    write_json(evidence / 'index.json', {'schema_version': VERSION, 'algorithm': ALGORITHM, 'receipts': dependencies})
    state.update(completed=list(STAGES[:count]), saved_state=next_state or _next(count, observed['mapping_status']),
                 fingerprints=observed['fingerprints'], mapping_status=observed['mapping_status'])
    guard()
    write_json(session_path, state)


def _generate(session_path, state, observed, guard):
    guard()
    output = _safe(state['paths']['output'])
    if output.exists():
        raise AppError('workflow_output_conflict', 'Use a fresh staging directory; existing files are preserved.')
    # A durable intent precedes the first write. A crash or lost receipt leaves
    # an unknown outcome, preventing automatic retries on the next invocation.
    state['in_flight_outcome'] = 'unknown'
    write_json(session_path, state)
    output.mkdir(mode=0o700)
    evidence = _scopes(session_path, state)
    for policy_id in state['selected_ids']:
        context_path = evidence / 'contexts' / (policy_id + '.json')
        guard()
        write_json(context_path, dict(observed['context'], selected_policy_id=policy_id))
        guard()
        result = runner.run('generate', {'input': state['paths']['input'], 'context': str(context_path), 'output': str(output / policy_id)}, evidence / 'attempts')
        if result.get('status') != 'succeeded_verified':
            raise AppError('workflow_generation_uncertain', 'Generation requires independent reconciliation before retry.')
    fresh = _observe(session_path, state)
    if fresh['fingerprints'] != observed['fingerprints']:
        raise AppError('workflow_evidence_changed', 'Source or target changed during generation.')
    _generation_payload(state, fresh)
    state['in_flight_outcome'] = 'none'
    try:
        _checkpoint(session_path, state, fresh, 8, guard)
    except (AppError, OSError, ValueError):
        state['in_flight_outcome'] = 'unknown'
        raise


def _answer(prompt, input_fn):
    answer = input_fn(prompt).strip()
    if len(answer) > 8192:
        raise AppError('workflow_input_limit', 'Guided command exceeds the local input limit.')
    return answer


def _guide(session_path, state, input_fn, output_fn, fresh, guard):
    guard()
    observed = _observe(session_path, state)
    if fresh:
        evidence = _scopes(session_path, state)
        try:
            evidence.mkdir(mode=0o700)
        except FileExistsError:
            raise AppError('workflow_evidence_conflict', 'Existing guided evidence must be preserved; choose a fresh session path.') from None
        _checkpoint(session_path, state, observed, 3, guard)
    progress = _reconstruct(session_path, state, observed)
    cancelled = state['lifecycle'] == 'cancelled'
    def finish(status):
        guard()
        state['lifecycle'] = 'cancelled' if cancelled and status == 'suspended' else status
        write_json(session_path, state)
        return {'status': status, 'step': progress['next_state'], 'session': str(session_path),
                'mapping_status': observed['mapping_status'], 'verified_completed': progress['verified_completed'],
                'execution_authorized': False, 'generated': len(progress['verified_completed']) >= 7}
    try:
        while True:
            step = progress['next_state']
            output_fn('Guided progress: ' + step + '; verified local milestones ' + str(progress['milestone_index']) + '/9. Ownership, cohort membership and external execution remain unqualified.')
            if step == 'object_selection':
                output_fn('Observed policy UUIDs: ' + ', '.join(observed['observed_ids'][:100]))
            prompt = ('Cancelled session [continue/save/cancel]: ' if cancelled else
                      'Guided ' + step + ' [UUIDs/continue/generate/finish/cohort RING UUIDs/edit stack|component|output VALUE/save/cancel]: ')
            answer = _answer(prompt, input_fn)
            guard()
            command, _, argument = answer.partition(' ')
            command = command.lower()
            if command in ('save', 'cancel'):
                return finish('suspended' if command == 'save' else 'cancelled')
            if cancelled:
                if command == 'continue':
                    cancelled = False
                    state['lifecycle'] = 'active'
                    write_json(session_path, state)
                else:
                    output_fn('Resume intent is required before any generation. Enter continue, save, or cancel.')
                continue
            if state['in_flight_outcome'] == 'unknown':
                output_fn('Unknown generation outcome. Preserve files and independently inspect them; this flow will not replay writes.')
                continue
            if command == 'cohort':
                ring, _, ids = argument.partition(' ')
                state['cohort'] = _cohort({'ring': ring, 'group_ids': ids.split(',') if ids else []})
            elif command == 'edit':
                field, _, value = argument.partition(' ')
                if field == 'output' and value:
                    state['paths']['output'] = str(_safe(value))
                elif field in ('stack', 'component') and re.fullmatch(r'[A-Za-z0-9_./-]{1,256}', value):
                    state['target'][field] = value
                else:
                    output_fn('Use a literal stack/component selector or an absolute staging output path.')
                    continue
            elif step == 'object_selection':
                state['selected_ids'] = _ids([value.strip() for value in answer.split(',')])
                observed = _observe(session_path, state)
                _checkpoint(session_path, state, observed, 6, guard)
            elif command == 'continue' and progress['milestone_index'] < 6:
                observed = _observe(session_path, state)
                count = 3 if progress['milestone_index'] < 3 else (6 if state['selected_ids'] else 3)
                _checkpoint(session_path, state, observed, count, guard)
            elif command == 'generate' and step in ('generate', 'partial_generate'):
                fresh_observation = _observe(session_path, state)
                if fresh_observation['fingerprints'] != observed['fingerprints']:
                    output_fn('Evidence changed before generation; review the invalidated prerequisites.')
                else:
                    try:
                        _generate(session_path, state, fresh_observation, guard)
                    except AppError as error:
                        output_fn('Generation stopped: ' + error.code)
                        if error.code == 'workflow_output_conflict':
                            state['saved_state'] = 'file_conflict'
            elif command == 'finish' and step in ('adoption_preview', 'complete_local'):
                fresh_observation = _observe(session_path, state)
                checked = _reconstruct(session_path, state, fresh_observation)
                if checked['milestone_index'] < 8:
                    output_fn('Current source or generated files no longer verify; completion was refused.')
                else:
                    _checkpoint(session_path, state, fresh_observation, 9, guard)
                    progress = _reconstruct(session_path, state, fresh_observation)
                    observed = fresh_observation
                    return finish('complete_local')
            else:
                output_fn('Choose the command appropriate to the displayed stage. No external action is available.')
            observed = _observe(session_path, state)
            progress = _reconstruct(session_path, state, observed)
            guard()
            state['saved_state'] = progress['next_state']
            state['completed'] = progress['verified_completed']
            write_json(session_path, state)
    except (EOFError, KeyboardInterrupt):
        return finish('suspended')


def _requested_state(session_path, input_path, context_path, output_path, repo, stack, component):
    fresh = not session_path.exists()
    if fresh:
        if any(value is None for value in (input_path, context_path, output_path)):
            raise AppError('guided_paths_required', 'Guided mode needs --input, --context and --output on first use.')
        state = _new({key: str(_safe(value)) for key, value in (('input', input_path), ('context', context_path), ('output', output_path))}, str(_safe(repo)) if repo is not None else None)
    else:
        state = _load(session_path)
        for key, value in (('input', input_path), ('context', context_path), ('output', output_path)):
            if value is not None:
                state['paths'][key] = str(_safe(value))
        if repo is not None:
            state['repository'] = str(_safe(repo))
    for key, value in (('stack', stack), ('component', component)):
        if value is not None:
            if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_./-]{1,256}', value):
                raise AppError('workflow_invalid_edit', 'Target selector is not a bounded literal.')
            state['target'][key] = value
    return state, fresh


def _owns_lock(path, identity, token):
    """Cooperative ownership check, not an atomic hostile-filesystem primitive."""
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or (info.st_dev, info.st_ino) != identity:
            return False
        with path.open('rb') as stream:
            opened = os.fstat(stream.fileno())
            return ((opened.st_dev, opened.st_ino) == identity
                    and stream.read(len(token) + 1) == token)
    except OSError:
        return False


def run_guided_workflow(session_path, input_path=None, context_path=None, output_path=None, input_fn=input, output_fn=print, repo=None, stack=None, component=None):
    """Interactive local cohort mode used by the existing wizard entrypoint."""
    lock = None
    acquired = False
    identity = None
    token = (secrets.token_hex(32) + "\n").encode("ascii")
    try:
        session_path = _safe(session_path)
        state, fresh = _requested_state(session_path, input_path, context_path, output_path, repo, stack, component)
        _scopes(session_path, state)
        lock = session_path.parent / ('.intune-wizard-lock-' + hashlib.sha256(str(session_path).encode()).hexdigest()[:32])
        from .io import mkdir_durable, sync_directory
        mkdir_durable(lock.parent)
        try:
            fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            raise AppError('wizard_session_locked', 'A running or interrupted wizard holds the session lock.') from None
        acquired = True
        with os.fdopen(fd, 'wb') as stream:
            info = os.fstat(stream.fileno())
            identity = (info.st_dev, info.st_ino)
            stream.write(token)
            stream.flush()
            os.fsync(stream.fileno())
        sync_directory(lock.parent)
        def guard():
            if not _owns_lock(lock, identity, token):
                raise AppError('wizard_lock_lost', 'Guided session lock ownership changed; preserve current evidence.')
        guard()
        # Re-read after acquiring the cooperative lock; preflight is not a snapshot.
        state, fresh = _requested_state(session_path, input_path, context_path, output_path, repo, stack, component)
        _scopes(session_path, state)
        output_fn('Guided local cohort authoring. Receipts prove current local consistency; they do not approve Intune or Atmos execution.')
        return _guide(session_path, state, input_fn, output_fn, fresh, guard)
    except (AppError, OSError, ValueError) as error:
        from .wizard import _code
        return {'status': 'blocked', 'error': _code(error), 'session': str(session_path), 'execution_authorized': False}
    finally:
        if acquired and _owns_lock(lock, identity, token):
            try:
                lock.unlink(missing_ok=True)
                sync_directory(lock.parent)
            except OSError:
                return {'status': 'blocked', 'error': 'wizard_lock_cleanup_not_durable', 'session': str(session_path), 'execution_authorized': False}
