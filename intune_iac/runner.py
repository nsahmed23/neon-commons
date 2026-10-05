"""Fixed local action registry, byte-bound proposals, and durable attempt receipts.

Preview has no dispatch or persistence. Uncertain writes retain a target lock;
reconciliation is intentionally manual rather than an automatic replay.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .io import AppError, digest, file_sha, load_json, read_bytes, write_json

VERSION = '1.0.0'
REGISTRY = {
    'inspect': {'required': {'input', 'context'}, 'optional': set(), 'adapter': 'engine.inspect_source', 'write': False},
    'generate': {'required': {'input', 'context', 'output'}, 'optional': set(), 'adapter': 'engine.generate', 'write': True},
    'graph_build': {'required': {'input', 'output'}, 'optional': {'context', 'atmos_root'}, 'adapter': 'graph.build_graph', 'write': True},
    'graph_query': {'required': {'graph', 'query'}, 'optional': {'subject'}, 'adapter': 'graph.query_graph', 'write': False},
    'repository_inspect': {'required': {'root'}, 'optional': set(), 'adapter': 'repository.discover_repository', 'write': False},
    'repository_resolve': {'required': {'root', 'stack', 'component'}, 'optional': set(), 'adapter': 'repository.resolve_component', 'write': False},
}
UNAVAILABLE = frozenset({'cloud_apply', 'cloud_import', 'native_windows', 'atmos_execute', 'provider_apply', 'assignment_update'})
QUERIES = frozenset({'policies', 'assignments', 'why-setting', 'impact', 'dependencies', 'placement'})
MESSAGES = {
    'unknown_action': 'Action is not in the fixed local registry.',
    'adapter_unavailable': 'This adapter is unavailable; no operation was dispatched.',
    'invalid_parameters': 'Parameters do not satisfy the action schema.',
    'unsafe_path': 'Symlinked paths or overlapping input, output, and state scopes are not supported.',
    'evidence_changed': 'Bound evidence changed before or during execution.',
    'output_conflict': 'Existing output cannot be safely replaced.',
    'target_locked': 'A target lock exists; inspect its attempt and reconcile the outcome before retrying.',
    'postcondition_failed': 'Output verification failed; reconcile the destination before retrying.',
    'adapter_failed': 'The local adapter failed; details are not included in the public receipt.',
    'persistence_failed': 'Runner persistence failed; inspect the target and attempt before retrying.',
    'invalid_capture': 'Capture validation failed.',
    'invalid_context': 'Target context validation failed.',
    'invalid_json': 'Local JSON validation failed.',
    'unreadable_file': 'A required local file could not be read.',
    'input_too_large': 'Input exceeds the supported size limit.',
    'preservation_failed': 'Independent preservation validation failed.',
}


def _error(code):
    # AppError messages may come from arbitrary source validation. Publish only a
    # stable runner-owned message and known error code.
    code = code if code in MESSAGES else 'adapter_failed'
    return {'code': code, 'message': MESSAGES[code]}


def _path(value):
    if not isinstance(value, (str, os.PathLike)) or not str(value) or '\x00' in str(value):
        raise AppError('invalid_parameters', '')
    path = Path(value).absolute()
    if any(p.is_symlink() for p in [path, *path.parents]):
        raise AppError('unsafe_path', '')
    return path.resolve()


def _contains(parent, child):
    return child == parent or parent in child.parents


def _directory_evidence(path):
    if not path.is_dir():
        raise AppError('invalid_parameters', '')
    entries = {}
    directories = []
    total = 0
    for index, item in enumerate(path.rglob('*')):
        if index >= 4096:
            raise AppError('invalid_parameters', '')
        if item.is_symlink():
            raise AppError('unsafe_path', '')
        if item.is_file():
            data = read_bytes(item)
            total += len(data)
            if len(entries) >= 4096 or total > 32 * 1024 * 1024:
                raise AppError('invalid_parameters', '')
            entries[str(item.relative_to(path))] = hashlib.sha256(data).hexdigest()
        elif item.is_dir():
            directories.append(str(item.relative_to(path)))
        else:
            raise AppError('unsafe_path', '')
    directories.sort()
    return {'path': str(path), 'sha256': digest({'files': entries, 'directories': directories}),
            'kind': 'directory', 'files': entries, 'directories': directories}


def _repository_evidence(path):
    from .repository import discover_repository
    report = discover_repository(path)
    fingerprint = report.get('source_fingerprint')
    if not isinstance(fingerprint, str) or len(fingerprint) != 64:
        raise AppError('invalid_parameters', '')
    # Empty implementation directories have no file bytes, but their presence
    # changes placement claims. Bind the public structural discovery as well.
    structural = {'status': report.get('status'), 'stacks': report.get('stacks'),
                  'blockers': report.get('blockers')}
    return {'path': str(path), 'sha256': digest([fingerprint, structural]),
            'source_fingerprint': fingerprint, 'kind': 'repository'}


def _proposal(action, parameters, state_dir):
    if not isinstance(action, str) or action not in REGISTRY:
        raise AppError('adapter_unavailable' if isinstance(action, str) and action in UNAVAILABLE else 'unknown_action', '')
    spec = REGISTRY[action]
    if not isinstance(parameters, dict) or not all(isinstance(k, str) for k in parameters):
        raise AppError('invalid_parameters', '')
    if not spec['required'] <= parameters.keys() or parameters.keys() - spec['required'] - spec['optional']:
        raise AppError('invalid_parameters', '')
    normalized = {}
    for name, value in parameters.items():
        if name in {'query', 'subject', 'stack', 'component'}:
            if not isinstance(value, str) or not value or len(value) > 512 or '\x00' in value:
                raise AppError('invalid_parameters', '')
            if name == 'query' and value not in QUERIES:
                raise AppError('invalid_parameters', '')
            normalized[name] = value
        else:
            # Public action parameters are JSON strings, never arbitrary objects.
            if not isinstance(value, str):
                raise AppError('invalid_parameters', '')
            normalized[name] = str(_path(value))
    state = _path(state_dir)
    target = _path(normalized['output']) if spec['write'] else None
    evidence = {}
    for name in ('input', 'context', 'graph', 'atmos_root', 'root'):
        if name in normalized:
            path = _path(normalized[name])
            if target and (_contains(target, path) or (name == 'atmos_root' and _contains(path, target))):
                raise AppError('unsafe_path', '')
            if _contains(path, state):
                raise AppError('unsafe_path', '')
            if name == 'root':
                evidence[name] = _repository_evidence(path)
            else:
                evidence[name] = _directory_evidence(path) if name == 'atmos_root' else {'path': str(path), 'sha256': file_sha(path), 'kind': 'file'}
    if target and _contains(target, state):
        raise AppError('unsafe_path', '')
    if target and action == 'graph_build' and target.exists():
        raise AppError('output_conflict', '')
    proposal = {'version': VERSION, 'action': action, 'adapter': spec['adapter'],
                'parameters_sha256': digest(normalized), 'evidence': evidence,
                'target': str(target) if target else None,
                'read_scopes': [v['path'] for v in evidence.values()],
                'write_scopes': [str(target)] if target else [],
                'retry_policy': 'reconcile_uncertain_outcome_before_retry'}
    proposal['id'] = digest(proposal)
    return proposal, normalized, state


def preview(action, parameters, state_dir):
    """Return a read-only proposal. This is information, not authorization."""
    try:
        proposal, _, _ = _proposal(action, parameters, state_dir)
        if proposal['target'] and _lock_path(proposal['target']).exists():
            return {'status': 'needs_review', 'action': action, 'proposal': proposal, 'error': _error('target_locked')}
        return {'status': 'ready', 'action': action, 'proposal': proposal}
    except (AppError, OSError, ValueError, TypeError) as exc:
        return _rejection(action, exc)


def _rejection(action, exc):
    code = getattr(exc, 'code', 'invalid_parameters')
    return {'status': 'unavailable' if code == 'adapter_unavailable' else 'rejected',
            'action': action if isinstance(action, str) and action in (set(REGISTRY) | UNAVAILABLE) else None,
            'error': _error(code)}


def _recheck(proposal):
    for evidence in proposal['evidence'].values():
        if str(_path(evidence['path'])) != evidence['path']:
            raise AppError('evidence_changed', '')
        if evidence['kind'] == 'repository':
            current = _repository_evidence(Path(evidence['path']))['sha256']
        else:
            current = _directory_evidence(Path(evidence['path']))['sha256'] if evidence['kind'] == 'directory' else file_sha(evidence['path'])
        if current != evidence['sha256']:
            raise AppError('evidence_changed', '')


def _dispatch(action, params):
    if action in {'repository_inspect', 'repository_resolve'}:
        from .repository import discover_repository, resolve_component, public_resolution
        if action == 'repository_inspect':
            return discover_repository(params['root'])
        return public_resolution(resolve_component(params['root'], params['stack'], params['component']))
    if action == 'inspect':
        from .engine import inspect_source
        return inspect_source(params['input'], params['context'])
    if action == 'generate':
        from .engine import generate
        return generate(params['input'], params['context'], params['output'])
    if action == 'graph_build':
        from .graph import build_graph
        graph = build_graph(params['input'], params.get('context'), params.get('atmos_root'))
        # An exclusive creation prevents unowned files from being overwritten,
        # including a file introduced after the runner's initial check.
        target = Path(params['output'])
        data = json.dumps(graph, sort_keys=True, ensure_ascii=False, allow_nan=False).encode() + b'\n'
        if len(data) > 16 * 1024 * 1024:
            raise AppError('postcondition_failed', '')
        try:
            fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            raise AppError('output_conflict', '') from None
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        from .io import sync_directory
        sync_directory(target.parent)
        return {'status': 'created', 'output': str(target), 'sha256': hashlib.sha256(data).hexdigest(), 'node_count': len(graph.get('nodes', [])), 'edge_count': len(graph.get('edges', []))}
    if action == 'graph_query':
        from .graph import query_graph
        return query_graph(load_json(params['graph']), params['query'], params.get('subject'))
    raise AppError('unknown_action', '')


def _verify(action, proposal, result):
    if not isinstance(result, dict):
        raise AppError('postcondition_failed', '')
    digest(result)  # Require finite, serializable JSON.
    _recheck(proposal)
    if action in {'repository_inspect', 'repository_resolve'}:
        if result.get('source_fingerprint') != proposal['evidence']['root']['source_fingerprint']:
            raise AppError('postcondition_failed', '')
        allowed = {'discovered', 'partial', 'blocked'} if action == 'repository_inspect' else {'resolved', 'blocked'}
        if result.get('status') not in allowed or 'effective' in result:
            raise AppError('postcondition_failed', '')
        from .repository import discover_repository, public_resolution, resolve_component
        root = proposal['evidence']['root']['path']
        if action == 'repository_resolve':
            selected = {'root': root, 'stack': result.get('stack'), 'component': result.get('component')}
            if digest(selected) != proposal['parameters_sha256']:
                raise AppError('postcondition_failed', '')
            expected = public_resolution(resolve_component(root, selected['stack'], selected['component']))
        else:
            expected = discover_repository(root)
        if digest(result) != digest(expected):
            raise AppError('postcondition_failed', '')
        return {'read_only': True, 'evidence_unchanged': True, 'source_fingerprint': result['source_fingerprint']}
    if action == 'generate':
        if result.get('outcome') != 'succeeded_verified' or result.get('preservation_verified') is not True:
            raise AppError('postcondition_failed', '')
        root = Path(proposal['target'])
        manifest_path = _path(root / 'generated-files.json')
        if result.get('output') != str(root) or file_sha(manifest_path) != result.get('manifest_sha256'):
            raise AppError('postcondition_failed', '')
        manifest = load_json(manifest_path)
        if not isinstance(manifest, dict) or manifest.get('schema_version') != '1.0.0' or not isinstance(manifest.get('files'), dict):
            raise AppError('postcondition_failed', '')
        for name, sha in manifest['files'].items():
            if not isinstance(name, str) or not isinstance(sha, str):
                raise AppError('postcondition_failed', '')
            path = _path(root / name)
            if not _contains(root, path) or path == root or file_sha(path) != sha:
                raise AppError('postcondition_failed', '')
        actual_files = set()
        for candidate in root.rglob('*'):
            if candidate.is_symlink():
                raise AppError('postcondition_failed', '')
            if candidate.is_file():
                actual_files.add(candidate.relative_to(root).as_posix())
            elif not candidate.is_dir():
                raise AppError('postcondition_failed', '')
        if actual_files != set(manifest['files']) | {'generated-files.json'}:
            raise AppError('postcondition_failed', '')
        if result.get('source_sha256') != proposal['evidence']['input']['sha256'] or result.get('context_sha256') != proposal['evidence']['context']['sha256']:
            raise AppError('postcondition_failed', '')
        if result.get('file_count') != len(manifest['files']) + 1:
            raise AppError('postcondition_failed', '')
        return {'preservation_verified': True, 'manifest_sha256': file_sha(manifest_path), 'file_count': len(manifest['files']) + 1}
    if action == 'graph_build':
        actual = file_sha(proposal['target'])
        if actual != result.get('sha256'):
            raise AppError('postcondition_failed', '')
        load_json(proposal['target'])
        return {'output_sha256': actual}
    if action == 'inspect':
        if result.get('status') not in {'ready', 'blocked'} or result.get('preservation_verified') is not True or result.get('source_sha256') != proposal['evidence']['input']['sha256'] or result.get('context_sha256') != proposal['evidence']['context']['sha256']:
            raise AppError('postcondition_failed', '')
        return {'read_only': True, 'preservation_verified': True, 'evidence_unchanged': True}
    return {'read_only': True, 'evidence_unchanged': True}


def _lock_path(target):
    path = Path(target)
    return path.parent / ('.intune-runner-lock-' + hashlib.sha256(str(path).encode()).hexdigest()[:32])


def _target_sha(target):
    path = _path(target)
    if not path.exists():
        return digest({'exists': False})
    if path.is_dir():
        return digest({'exists': True, 'kind': 'directory', 'sha256': _directory_evidence(path)['sha256']})
    return digest({'exists': True, 'kind': 'file', 'sha256': file_sha(path)})


def _receipt_base(proposal, operation_id):
    return {'schema_version': VERSION, 'operation_id': operation_id, 'proposal_id': proposal['id'],
            'action': proposal['action'], 'adapter': proposal['adapter'], 'adapter_version': VERSION,
            'parameters_sha256': proposal['parameters_sha256'], 'evidence': proposal['evidence'],
            'target': proposal['target'], 'recorded_at': datetime.now(timezone.utc).isoformat()}


def run(action, parameters, state_dir):
    """Execute one fixed local adapter; never replay an uncertain target."""
    try:
        proposal, params, state = _proposal(action, parameters, state_dir)
    except (AppError, OSError, ValueError, TypeError) as exc:
        return _rejection(action, exc)
    operation_id = uuid.uuid4().hex
    attempt = state / (operation_id + '.attempt.json')
    outcome = state / (operation_id + '.result.json')
    base = _receipt_base(proposal, operation_id)
    answer = {'action': action, 'proposal_id': proposal['id'], 'operation_id': operation_id,
              'receipt_paths': {'attempt': str(attempt), 'result': str(outcome)}}
    lock = None
    dispatched = False
    release = False
    target_before = None
    try:
        if proposal['target']:
            lock = _lock_path(proposal['target'])
            from .io import mkdir_durable
            mkdir_durable(lock.parent)
            try:
                fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                return dict(answer, status='needs_review', error=_error('target_locked'))
            with os.fdopen(fd, 'wb') as stream:
                stream.write(json.dumps({'operation_id': operation_id, 'attempt': str(attempt), 'proposal_id': proposal['id']}).encode())
                stream.flush(); os.fsync(stream.fileno())
            from .io import sync_directory
            sync_directory(lock.parent)
        _recheck(proposal)
        write_json(attempt, dict(base, status='running'))
        # Reread the actual persisted attempt before it can authorize dispatch.
        if load_json(attempt) != dict(base, status='running'):
            raise AppError('persistence_failed', '')
        _recheck(proposal)
        if proposal['target']:
            target_before = _target_sha(proposal['target'])
        dispatched = True
        result = _dispatch(action, params)
        verification = _verify(action, proposal, result)
        write_json(outcome, dict(base, status='succeeded_verified', verification=verification))
        if load_json(outcome) != dict(base, status='succeeded_verified', verification=verification):
            raise AppError('persistence_failed', '')
        release = True
        return dict(answer, status='succeeded_verified', result=result)
    except Exception as exc:
        code = getattr(exc, 'code', 'adapter_failed')
        uncertain = dispatched and REGISTRY[action]['write']
        status = 'outcome_unknown' if uncertain else 'rejected'
        if uncertain and code == 'output_conflict':
            try:
                if target_before is not None and _target_sha(proposal['target']) == target_before:
                    status = 'failed_no_effect_verified'
                    uncertain = False
            except Exception:
                pass
        release = not uncertain
        error = _error(code)
        try:
            failed_record = dict(base, status=status, error=error)
            if status == 'failed_no_effect_verified':
                failed_record['verification'] = {'target_unchanged': True, 'target_snapshot_sha256': target_before}
            write_json(outcome, failed_record)
        except Exception:
            release = False if dispatched and REGISTRY[action]['write'] else release
            error = _error('persistence_failed')
        return dict(answer, status=status, error=error)
    finally:
        # BaseException (interrupt/termination) deliberately leaves the lock and
        # running attempt. No age-based lease stealing can silently replay it.
        if lock and release:
            try:
                lock.unlink(missing_ok=True)
                from .io import sync_directory
                sync_directory(lock.parent)
            except OSError:
                # A successful remote/local action is distinct from confirmed
                # durable cleanup. Never leak raw paths or return verified
                # success while a lock namespace transition remains uncertain.
                return dict(answer, status='outcome_unknown' if dispatched and REGISTRY[action]['write'] else 'rejected',
                            error=_error('persistence_failed'))
