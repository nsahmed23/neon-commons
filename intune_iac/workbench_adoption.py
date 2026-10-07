"""Receipt-reconstructed local adoption handed to persistent maintenance.

The completed wizard remains historical evidence. Maintenance gets a separate
explicit synthetic service because later reads/writes would otherwise change
the wizard's bound request journal. This is not provider import or ownership.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import stat

from .io import AppError, canonical, digest, file_sha, load_json, parse_json, write_json, sync_directory
from .modeled_service import ModeledService, compare_semantics, project_capture

VERSION = 'workbench-adoption/1'


def _fail(code):
    raise AppError(code, 'Local adoption evidence is incomplete, changed, or outside the supported synthetic handoff.')


def _safe(value):
    path = Path(value).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        _fail('workbench_adoption_unsafe_path')
    return path.resolve()


def _inspect(store, session_path):
    from . import journey
    session = _safe(session_path)
    before = file_sha(session)
    state = journey._load(session)
    if state['mode'] != 'simulation' or state['lifecycle'] != 'complete_simulation' or state['in_flight'] is not None:
        _fail('workbench_adoption_incomplete')
    observed = journey._observe(session, state)
    progress = journey._progress(session, state, observed)
    if progress['next_state'] != 'complete_simulation' or progress['verified_completed'] != list(journey.STAGES):
        _fail('workbench_adoption_evidence_invalid')
    if observed['raw_capture'].get('synthetic') is not True:
        _fail('workbench_adoption_synthetic_required')
    if observed['context']['tenant_id'] != store.tenant_id:
        _fail('workbench_adoption_wrong_tenant')
    expected = project_capture(observed['raw_capture'], state['selected_ids'])
    evidence_root = journey._root(session)
    original_service = ModeledService(evidence_root / 'modeled-service')
    snapshot = original_service.snapshot()
    if compare_semantics(expected, snapshot['current']):
        _fail('workbench_adoption_estate_changed')
    repository = None
    if state['repository'] is not None:
        from .repository import public_resolution, resolve_component
        context = observed['context']
        repository = public_resolution(resolve_component(state['repository'], context['stack'], context['component']))
        if repository.get('status') != 'resolved':
            _fail('workbench_adoption_repository_unresolved')
    generated = {oid: {'path': str(_safe(Path(state['paths']['output']) / oid)),
                      'manifest_sha256': file_sha(_safe(Path(state['paths']['output']) / oid / 'generated-files.json'))}
                 for oid in sorted(state['selected_ids'])}
    binding = {
        'schema_version': VERSION, 'tenant_id': store.tenant_id,
        'object_ids': sorted(state['selected_ids']), 'session': str(session), 'session_sha256': before,
        'source': {'path': state['paths']['input'], 'sha256': observed['fingerprints']['source']},
        'context': {'path': state['paths']['context'], 'sha256': file_sha(_safe(state['paths']['context']))},
        'generated': generated, 'receipt_sha256': progress['receipt_dependencies'],
        'repository': repository, 'discovery': observed['discovery'],
        'atmos': journey._payload('atmos', session, state, observed),
        'original_service': {'path': str(original_service.root), 'sha256': file_sha(original_service.path),
                             'revision': snapshot['revision'], 'request_count': len(snapshot['requests']),
                             'estate_sha256': digest(snapshot['current'])},
        'evidence_class': 'reconstructed_local_synthetic_adoption',
        'native_opentofu_output_only': state.get('tofu_executable') is not None,
        'native_atmos_configuration_only': state.get('atmos_executable') is not None,
        'native_provider_execution': False, 'cloud_execution': False,
        'execution_authorized': False, 'ownership': 'unknown',
        'handoff_semantics': 'separate_maintenance_model_preserving_original_journey',
    }
    if len(canonical(binding)) > 1024 * 1024:
        _fail('workbench_adoption_binding_limit')
    if before != file_sha(session):
        _fail('workbench_adoption_source_changed')
    return binding, observed['raw_capture'], expected


def preview(store, session_path):
    """Reconstruct every stage; no model, collection, or artifact is created."""
    binding, _, _ = _inspect(store, session_path)
    return {'status': 'ready_local_model_handoff', 'binding': binding,
            'binding_sha256': digest(binding), 'cloud_authority': False,
            'execution_authorized': False, 'remote_import_performed': False}


@contextmanager
def _lock(root):
    path = _safe(root / 'adoption.lock')
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            _fail('workbench_adoption_lock_invalid')
        try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: _fail('workbench_adoption_busy')
        yield
    finally:
        os.close(fd)


def _data(store, root, binding, object_id):
    return {'schema_version': VERSION, 'tenant_id': store.tenant_id, 'object_id': object_id,
            'binding': binding, 'binding_sha256': digest(binding), 'maintenance_service_root': str(root / 'service'),
            'cloud_authority': False, 'execution_authorized': False}


def _result(store, root, journal, capture, expected):
    binding = journal['binding']
    object_ids = binding['object_ids']
    artifact_ids = journal['artifact_ids']
    if (set(artifact_ids) != set(object_ids) or len(set(artifact_ids.values())) != len(object_ids)
            or any(type(value) is not str for value in artifact_ids.values())):
        _fail('workbench_adoption_artifact_missing')
    rows = []
    for oid in object_ids:
        matches = [row for row in store.artifacts(kind='adoption', object_id=oid)
                   if row['artifact_id'] == artifact_ids[oid]]
        if (len(matches) != 1 or matches[0]['object_id'] != oid or matches[0]['tenant_id'] != store.tenant_id
                or digest(matches[0]['data']) != digest(_data(store, root, binding, oid))):
            _fail('workbench_adoption_artifact_missing')
        rows.append(matches[0])
    service = ModeledService(_safe(root / 'service'))
    snapshot = service.snapshot()
    # The current model can legitimately advance after completed adoption.
    # Its initial estate and source binding must still establish the handoff.
    if snapshot['source_sha256'] != digest(capture) or compare_semantics(expected, snapshot['initial']):
        _fail('workbench_adoption_initial_model_changed')
    run = store.collection_detail(journal['collection_run_id'])
    source = run.get('source', {})
    coverage = {('policies', None)} | {(kind, oid) for oid in object_ids for kind in ('settings', 'assignments')}
    if (run['status'] != 'complete' or run['coverage'] != 'complete' or run['object_count'] != len(object_ids)
            or run.get('scope') != {'kind': 'estate', 'object_ids': object_ids}
            or source.get('service_kind') != 'ModeledService' or source.get('service_root') != str(service.root)
            or source.get('adoption_binding_sha256') != digest(binding)
            or source.get('observed_estate_sha256') != digest({'tenant_id': store.tenant_id, 'objects': expected['objects']})
            or {(row['kind'], row['owner_id']) for row in run.get('collections', [])} != coverage
            or any(row['coverage'] != 'complete' for row in run.get('collections', []))):
        _fail('workbench_adoption_collection_changed')
    # Check the actual saved batch, not its status flag or self-supplied hash.
    # Reading a single admitted eight-object run avoids an unbounded history scan.
    with store._connection() as db:
        saved = db.execute('SELECT o.object_id,s.body_json FROM observations o JOIN snapshots s USING(snapshot_id) '
                           'WHERE o.run_id=? AND o.tenant_id=? ORDER BY o.object_id LIMIT 9',
                           (run['run_id'], store.tenant_id)).fetchall()
    if (len(saved) != len(object_ids) or {row['object_id'] for row in saved} != set(object_ids)
            or any(digest(parse_json(row['body_json'])) != digest(expected['objects'][row['object_id']]) for row in saved)):
        _fail('workbench_adoption_observation_changed')
    return {'status': 'adopted_local_model', 'handoff_root': str(root), 'service_root': str(root / 'service'),
            'object_ids': journal['binding']['object_ids'], 'binding_sha256': journal['binding_sha256'],
            'collection_run_id': journal['collection_run_id'], 'adoptions': rows,
            'cloud_authority': False, 'execution_authorized': False, 'remote_import_performed': False,
            'ownership': 'unknown', 'original_journey_preserved': True}


def adopt(store, session_path, output):
    """Create or resume the same local handoff without replaying a mutation.

    Failures retain the private checkpoint and model. Only a still-pristine
    model may resume an incomplete handoff; a completed handoff is idempotent.
    """
    from . import journey
    store._require_v2()
    binding, capture, expected = _inspect(store, session_path)
    root = _safe(output)
    protected = [_safe(store.root), _safe(session_path), journey._root(_safe(session_path)),
                 _safe(binding['source']['path']), _safe(binding['context']['path'])]
    protected += [_safe(row['path']) for row in binding['generated'].values()]
    if binding['repository'] is not None: protected.append(_safe(binding['repository']['root']))
    if not root.parent.is_dir() or any(root == p or root in p.parents or p in root.parents for p in protected):
        _fail('workbench_adoption_path_overlap')
    checkpoint = root / 'adoption.json'
    if not root.exists():
        root.mkdir(mode=0o700); sync_directory(root.parent)
        journal = {'schema_version': VERSION, 'store_root': str(store.root), 'handoff_root': str(root),
                   'binding': binding, 'binding_sha256': digest(binding), 'status': 'preparing',
                   'collection_run_id': None, 'artifact_ids': {}}
        write_json(checkpoint, journal)
    else:
        info = root.stat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            _fail('workbench_adoption_path_not_private')
        if not checkpoint.is_file(): _fail('workbench_adoption_output_exists')
    with _lock(root):
        journal = load_json(_safe(checkpoint))
        if (set(journal) != {'schema_version','store_root','handoff_root','binding','binding_sha256','status','collection_run_id','artifact_ids'}
                or journal['schema_version'] != VERSION or journal['store_root'] != str(store.root)
                or journal['handoff_root'] != str(root) or journal['binding_sha256'] != digest(binding)
                or digest(journal['binding']) != digest(binding)
                or journal['status'] not in ('preparing','model_created','collection_incomplete','collected','complete')
                or type(journal['artifact_ids']) is not dict):
            _fail('workbench_adoption_checkpoint_changed')
        if journal['status'] == 'complete': return _result(store, root, journal, capture, expected)
        if {p.name for p in root.iterdir()} - {'adoption.json','adoption.lock','service'}:
            _fail('workbench_adoption_unexpected_file')
        service_root = root / 'service'
        if not service_root.exists(): ModeledService.create(service_root, capture, binding['object_ids'])
        service = ModeledService(service_root)
        snapshot = service.snapshot()
        if (snapshot['source_sha256'] != digest(capture) or snapshot['revision'] != 1
                or compare_semantics(expected, snapshot['initial']) or compare_semantics(expected, snapshot['current'])
                or any(row['method'] != 'GET' or row['mutation_committed'] for row in snapshot['requests'])):
            _fail('workbench_adoption_partial_model_changed')
        journal['status'] = 'model_created'; write_json(checkpoint, journal)
        source = {'adoption_binding_sha256': digest(binding), 'adoption_session': binding['session'],
                  'source_path': str(_safe(Path(binding['generated'][binding['object_ids'][0]]['path']).parent))}
        if binding['repository']:
            source.update(repository_path=binding['repository']['root'], repository_resolution=binding['repository'],
                          inheritance=binding['repository'].get('provenance', {}),
                          atmos_stack=binding['atmos']['stack'], component=binding['atmos']['component'])
        run = store.collect(service, source=source)
        journal.update(collection_run_id=run['run_id'], status='collected' if run['status'] == 'complete' else 'collection_incomplete')
        write_json(checkpoint, journal)
        if run['status'] != 'complete': _fail('workbench_adoption_collection_incomplete')
        for oid in binding['object_ids']:
            data = _data(store, root, binding, oid)
            receipt = store.record_artifact('adoption', oid, data)
            journal['artifact_ids'][oid] = receipt['artifact_id']; write_json(checkpoint, journal)
        journal['status'] = 'complete'; write_json(checkpoint, journal)
        return _result(store, root, journal, capture, expected)


def lineage(store, object_id):
    store.inspect(object_id)
    rows = store.artifacts(kind='adoption', object_id=object_id)
    return {'object_id': object_id, 'adoptions': rows, 'cloud_authority': False, 'ownership': 'unknown',
            'qualification': 'Historical locally reconstructed adoption; current source or service consistency must be observed separately.'}
