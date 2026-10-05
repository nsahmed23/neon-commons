"""Finite local scheduling of the existing read-only modeled collector.

No daemon, arbitrary command, cloud endpoint, credential, or mutation executor
is accepted. The schedule is cooperative same-user local state, not a hostile-
host trust boundary. Collection attempts and uncertainty survive terminal exit.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import math
import os
from pathlib import Path
import re
import stat
import sys
import time
from uuid import uuid4

from . import protected
from .io import AppError, digest, file_sha, load_json, parse_json, read_bytes, sync_directory, write_json
from .modeled_service import ModeledService, VERSION as SERVICE_VERSION
from .workbench_store import WorkbenchStore

VERSION = 'intune-local-schedule/1.0'
MAX_HISTORY = 10000
MAX_MISSED = 1000000
SOURCE_ROOT = Path(__file__).resolve().parents[1]
_ID = re.compile(r'^[0-9a-f]{32}$')


def _fail(code):
    raise AppError(code, 'The local collection schedule is changed, unavailable, busy, or outside its finite supported profile.')


def _number(value, minimum, maximum):
    if type(value) not in (int, float) or not math.isfinite(value) or not minimum <= value <= maximum:
        _fail('scheduler_bound_invalid')
    return float(value)


def _iso(value=None):
    return datetime.fromtimestamp(time.time() if value is None else value, timezone.utc).isoformat().replace('+00:00', 'Z')


def _stamp(value):
    try:
        moment = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if moment.tzinfo != timezone.utc: _fail('scheduler_time_invalid')
        return moment.timestamp()
    except (ValueError, TypeError, AttributeError):
        _fail('scheduler_time_invalid')


def _safe(value):
    path = Path(value).absolute()
    if any(item.is_symlink() for item in (path, *path.parents)):
        _fail('scheduler_unsafe_path')
    return path.resolve()


def _private(path, *, directory=False):
    path = _safe(path); info = path.stat()
    if ((not stat.S_ISDIR(info.st_mode) if directory else not stat.S_ISREG(info.st_mode))
            or info.st_uid != os.geteuid() or info.st_mode & 0o077 or (not directory and info.st_nlink != 1)):
        _fail('scheduler_private_path_required')
    return path


def _identity(path):
    info = Path(path).stat()
    return {'device': info.st_dev, 'inode': info.st_ino}


def _runtime_binding():
    interpreter = Path(sys.executable).absolute()
    real_interpreter = interpreter.resolve()
    venv = Path(sys.prefix) / 'pyvenv.cfg'
    files = [SOURCE_ROOT / 'scripts' / 'intune-iac.py', *sorted((SOURCE_ROOT / 'intune_iac').glob('*.py'))]
    return {'interpreter': str(interpreter), 'interpreter_realpath': str(real_interpreter),
            'interpreter_sha256': protected._sha(real_interpreter), 'python_version': sys.version,
            'venv_config': str(venv) if venv.exists() else None,
            'venv_config_sha256': file_sha(venv) if venv.exists() else None,
            'entrypoint': str(SOURCE_ROOT / 'scripts' / 'intune-iac.py'),
            'source_files': {str(path.relative_to(SOURCE_ROOT)): file_sha(_safe(path)) for path in files}}


@contextmanager
def _lock(root):
    path = _safe(root / 'schedule.lock')
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077 or info.st_nlink != 1:
            _fail('scheduler_lock_invalid')
        try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: _fail('scheduler_already_running')
        # Pass this exact open-file description to the collector. Parent death
        # cannot release the overlap lock while that collector is still alive.
        yield fd
    finally: os.close(fd)


def _load(job_dir):
    root = _private(job_dir, directory=True)
    config = load_json(_private(root / 'config.json'))
    # Concurrent status readers can open the prior inode just before atomic
    # replacement unlinks it. Retry the bounded strict read; never admit links.
    for attempt in range(3):
        try:
            state = load_json(_private(root / 'state.json'))
            break
        except AppError as error:
            if error.code not in ('unsafe_file_identity', 'unreadable_file') or attempt == 2: raise
    if type(state) is not dict: _fail('scheduler_state_invalid')
    if (type(config) is not dict or config.get('schema_version') != VERSION
            or config.get('job_root') != str(root) or not _ID.fullmatch(config.get('job_id', ''))
            or config.get('source_adapter') != SERVICE_VERSION or config.get('cloud_authority') is not False
            or state.get('config_sha256') != digest(config) or state.get('job_id') != config['job_id']):
        _fail('scheduler_config_changed')
    _number(config['interval_seconds'], 0.1, 86400)
    if state.get('runner_status') not in ('idle', 'running'):
        _fail('scheduler_state_invalid')
    for key in ('run_count', 'success_count', 'failure_count', 'consecutive_failures', 'interrupted_count', 'missed_cycles'):
        if type(state.get(key)) is not int or not 0 <= state[key] <= 9007199254740991:
            _fail('scheduler_state_invalid')
    if state['run_count'] > MAX_HISTORY or (state['active_run'] is not None and not _ID.fullmatch(state['active_run'])):
        _fail('scheduler_state_invalid')
    _stamp(state['next_due'])
    return root, config, state


def _target(config):
    store = WorkbenchStore(config['store_root'])
    service_root = _private(config['service_root'], directory=True)
    service = ModeledService(service_root); snapshot = service.snapshot()
    if (store.tenant_id != config['tenant_id'] or snapshot['current']['tenant_id'] != config['tenant_id']
            or snapshot['source_sha256'] != config['service_source_sha256']
            or _identity(store.root) != config['store_identity'] or _identity(store.path) != config['database_identity']
            or _identity(service_root) != config['service_identity']):
        _fail('scheduler_source_changed')
    return store


def _validate_runtime(config):
    if digest(_runtime_binding()) != digest(config['runtime']):
        _fail('scheduler_runtime_changed')


def _summary(root, config, state):
    return {**state, 'job_root': str(root), 'tenant_id': config['tenant_id'],
            'interval_seconds': config['interval_seconds'], 'source_adapter': config['source_adapter'],
            'evidence_class': 'local_modeled_scheduled_collection', 'cloud_authority': False,
            'daemon_installed': False, 'production_qualified': False,
            'limits': {'cleanup_grace_seconds': protected.PROCESS_CLEANUP_TIMEOUT,
                       'storage': 'Existing bounded SQLite waits and filesystem durability assumptions apply.'}}


def create_schedule(store, service_root, interval_seconds, output):
    """Create an inert private schedule; creation performs no collection."""
    interval = _number(interval_seconds, 0.1, 86400)
    store = store if type(store) is WorkbenchStore else WorkbenchStore(store)
    service_root = _private(service_root, directory=True)
    snapshot = ModeledService(service_root).snapshot()
    if snapshot['current']['tenant_id'] != store.tenant_id:
        _fail('scheduler_source_changed')
    root = _safe(output)
    if root.exists() or not root.parent.is_dir(): _fail('scheduler_fresh_output_required')
    if any(root == path or root in path.parents or path in root.parents for path in (store.root, service_root)):
        _fail('scheduler_path_overlap')
    config = {'schema_version': VERSION, 'job_id': uuid4().hex, 'job_root': str(root),
              'tenant_id': store.tenant_id, 'store_root': str(store.root), 'service_root': str(service_root),
              'store_identity': _identity(store.root), 'database_identity': _identity(store.path),
              'service_identity': _identity(service_root), 'service_source_sha256': snapshot['source_sha256'],
              'source_adapter': SERVICE_VERSION, 'interval_seconds': interval,
              'runtime': _runtime_binding(), 'created_at': _iso(), 'cloud_authority': False}
    state = {'schema_version': VERSION, 'job_id': config['job_id'], 'config_sha256': digest(config),
             'runner_status': 'idle', 'runner_pid': None, 'active_run': None, 'active_record': None,
             'next_due': _iso(), 'run_count': 0, 'success_count': 0, 'failure_count': 0,
             'consecutive_failures': 0, 'interrupted_count': 0, 'missed_cycles': 0,
             'missed_cycles_capped': False, 'last_success': None, 'last_started_at': None,
             'last_ended_at': None, 'last_run': None, 'last_error': None}
    root.mkdir(mode=0o700); (root / 'runs').mkdir(mode=0o700)
    sync_directory(root); sync_directory(root.parent)
    write_json(root / 'config.json', config); write_json(root / 'state.json', state)
    with _lock(root):
        store.record_artifact('schedule', None, {'job_id': config['job_id'], 'status': 'created',
            'config_sha256': digest(config), 'created_at': config['created_at'], 'job_root': str(root),
            'tenant_id': store.tenant_id, 'source_adapter': SERVICE_VERSION})
    return dict(_summary(root, config, state), status='created')


def schedule_status(job_dir):
    root, config, state = _load(job_dir)
    try:
        with _lock(root): active = False
    except AppError as error:
        if error.code != 'scheduler_already_running': raise
        active = True
    return dict(_summary(root, config, state), lock_held=active,
                status='active' if active else 'interrupted_or_unconfirmed' if state['active_run'] else 'idle')


def _run_path(root, run_id):
    if type(run_id) is not str or not _ID.fullmatch(run_id): _fail('scheduler_state_invalid')
    return root / 'runs' / (run_id + '.json')


def _publish(root, store, run):
    if run['status'] == 'outcome_unknown' or run.get('artifact_recorded'): return
    data = {key: value for key, value in run.items() if key not in ('artifact_recorded', 'artifact_id')}
    artifact = store.record_artifact('schedule', None, data)
    run.update(artifact_recorded=True, artifact_id=artifact['artifact_id'])
    write_json(_run_path(root, run['run_id']), run)


def _settle(root, state, run):
    if state['active_run'] != run['run_id']: _fail('scheduler_state_invalid')
    state['active_run'] = None; state['active_record'] = None
    state['last_run'] = run['run_id']; state['last_ended_at'] = run['ended_at']
    state['last_error'] = run.get('error_code')
    state['next_due'] = run['next_due_after']
    if run['status'] == 'complete':
        state['success_count'] += 1; state['consecutive_failures'] = 0
        state['last_success'] = run['ended_at']
    else:
        state['consecutive_failures'] += 1
        state['interrupted_count' if run['status'] == 'interrupted' else 'failure_count'] += 1
    write_json(root / 'state.json', state)


def _recover(root, config, state, store):
    if state['active_run'] is not None:
        path = _run_path(root, state['active_run'])
        run = load_json(_private(path)) if path.exists() else state['active_record']
        if not run or run['run_id'] != state['active_run'] or run['job_id'] != config['job_id']:
            _fail('scheduler_state_invalid')
        if run['status'] == 'outcome_unknown':
            run.update(status='interrupted', ended_at=None, interrupted_detected_at=_iso(),
                       error_code='scheduler_previous_runner_interrupted', replay_scope='new_read_collection_only')
            write_json(path, run)
        _settle(root, state, run)
    # Durable completed records are an outbox. Artifact insertion deduplicates
    # exact data if a prior process died between database commit and local ack.
    count = 0
    for path in sorted((root / 'runs').glob('*.json')):
        if path.name.endswith('.source.json'): continue
        count += 1
        if count > MAX_HISTORY: _fail('scheduler_history_limit')
        run = load_json(_private(path))
        if run['job_id'] != config['job_id']: _fail('scheduler_state_invalid')
        _publish(root, store, run)


def _open_pinned(path, expected):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 256 * 1024 * 1024:
            _fail('scheduler_runtime_changed')
        with os.fdopen(os.dup(fd), 'rb') as source:
            if hashlib.file_digest(source, 'sha256').hexdigest() != expected: _fail('scheduler_runtime_changed')
        os.lseek(fd, 0, os.SEEK_SET)
        return fd
    except BaseException:
        os.close(fd); raise


def _save_bytes(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data); stream.flush(); os.fsync(stream.fileno())
    sync_directory(path.parent)


def _confirmed_result(store, config, run, result):
    if (type(result) is not dict or type(result.get('run_id')) is not int
            or result.get('tenant_id') != config['tenant_id']):
        _fail('scheduler_collector_response_invalid')
    persisted = store.collection_detail(result['run_id'])
    if digest(persisted) != digest(result):
        _fail('scheduler_collector_response_invalid')
    lineage = persisted.get('source', {}).get('scheduler', {})
    if lineage.get('job_id') != config['job_id'] or lineage.get('run_id') != run['run_id']:
        _fail('scheduler_collector_response_invalid')
    return result.get('status') == 'complete' and result.get('coverage') == 'complete'


def _dispatch(root, config, run, lock_fd, timeout):
    runtime = config['runtime']; descriptors = []; evidence = {}; cleanup_evidence = {}
    metadata = root / 'runs' / (run['run_id'] + '.source.json')
    write_json(metadata, {'scheduler': {'job_id': config['job_id'], 'run_id': run['run_id'],
        'scheduled_for': run['scheduled_for'], 'actual_started_at': run['started_at'], 'source_adapter': SERVICE_VERSION}})
    try:
        executable = _open_pinned(runtime['interpreter_realpath'], runtime['interpreter_sha256']); descriptors.append(executable)
        launcher = _open_pinned(runtime['entrypoint'], runtime['source_files']['scripts/intune-iac.py']); descriptors.append(launcher)
        argv = [runtime['interpreter'], '-I', '-B', '/proc/self/fd/' + str(launcher),
                'workbench', 'collect', '--root', config['store_root'], '--service-root', config['service_root'],
                '--source', str(metadata)]
        run['argv'] = argv
        write_json(_run_path(root, run['run_id']), run)
        raw = protected._supervise(argv, cwd=SOURCE_ROOT, env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8'},
              pass_fds=tuple([lock_fd, *descriptors]), executable='/proc/self/fd/' + str(executable), timeout=timeout,
              evidence=evidence, cleanup_evidence=cleanup_evidence)
        return parse_json(raw)
    finally:
        for fd in descriptors: os.close(fd)
        run['process_evidence'] = {key: value for key, value in evidence.items() if key not in ('stdout_bytes', 'stderr_bytes')}
        run['process_evidence'].update(cleanup_evidence)
        for label in ('stdout', 'stderr'):
            raw = evidence.get(label + '_bytes', b'')
            _save_bytes(root / 'runs' / (run['run_id'] + '.' + label), raw)
            run[label + '_sha256'] = hashlib.sha256(raw).hexdigest()
        # A nonzero CLI result can still contain a persisted denied/partial
        # collection receipt. Retain it even though the supervisor rejected it.
        if evidence.get('stdout_bytes'):
            try: run['collection_result'] = parse_json(evidence['stdout_bytes'])
            except AppError: pass


def run_schedule(job_dir, max_runs, max_duration_seconds):
    """Run a finite number of sequential real collections, then return.

    Duration bounds polling and dispatch; a child is only started with at least
    one whole second left. The repaired supervisor adds at most its separate
    cleanup deadline. Existing storage I/O bounds remain explicit assumptions.
    """
    if type(max_runs) is not int or not 1 <= max_runs <= 1000: _fail('scheduler_bound_invalid')
    duration = _number(max_duration_seconds, 1, 3600)
    deadline = time.monotonic() + duration
    root, config, state = _load(job_dir)
    config_sha = digest(config)
    executed = 0; failed = 0; stop_reason = 'duration_limit'
    with _lock(root) as lock_fd:
        root, config, state = _load(root)
        if digest(config) != config_sha: _fail('scheduler_config_changed')
        _validate_runtime(config); store = _target(config)
        _recover(root, config, state, store)
        state.update(runner_status='running', runner_pid=os.getpid())
        write_json(root / 'state.json', state)
        try:
            while executed < max_runs and time.monotonic() < deadline:
                due = _stamp(state['next_due']); now = time.time()
                if now < due:
                    time.sleep(min(0.1, due - now, max(0, deadline - time.monotonic())))
                    continue
                remaining = math.floor(deadline - time.monotonic())
                if remaining < 1: break
                if state['run_count'] >= MAX_HISTORY: _fail('scheduler_history_limit')
                _validate_runtime(config); store = _target(config)
                missed = max(0, math.floor((now - due) / config['interval_seconds']))
                state['missed_cycles'] += min(missed, MAX_MISSED)
                state['missed_cycles_capped'] = state['missed_cycles_capped'] or missed > MAX_MISSED
                due += missed * config['interval_seconds']
                run = {'schema_version': VERSION, 'job_id': config['job_id'], 'run_id': uuid4().hex,
                       'tenant_id': config['tenant_id'], 'sequence': state['run_count'] + 1,
                       'status': 'outcome_unknown', 'scheduled_for': _iso(due), 'started_at': _iso(),
                       'ended_at': None, 'next_due_after': _iso(due + config['interval_seconds']),
                       'missed_cycles_before': min(missed, MAX_MISSED), 'collection_run_id': None,
                       'source_adapter': SERVICE_VERSION, 'config_sha256': config_sha,
                       'evidence_class': 'local_modeled_scheduled_collection', 'cloud_authority': False,
                       'artifact_recorded': False}
                state.update(active_run=run['run_id'], active_record=dict(run),
                             run_count=run['sequence'], last_started_at=run['started_at'])
                # The complete in-flight record is durable before child dispatch;
                # recovery can reconstruct it even if the per-run write fails.
                write_json(root / 'state.json', state); write_json(_run_path(root, run['run_id']), run)
                interrupted = None
                try:
                    result = _dispatch(root, config, run, lock_fd, min(60, remaining))
                    _validate_runtime(config); _target(config)
                    complete = _confirmed_result(store, config, run, result)
                    run.update(status='complete' if complete else 'failed', collection_result=result,
                               collection_run_id=result['run_id'])
                except BaseException as error:
                    run.update(status='interrupted' if isinstance(error, (KeyboardInterrupt, SystemExit)) else 'failed',
                               error_code=getattr(error, 'code', type(error).__name__))
                    if isinstance(error, (KeyboardInterrupt, SystemExit)): interrupted = error
                    observed = run.get('collection_result')
                    if isinstance(observed, dict) and type(observed.get('run_id')) is int:
                        run['collection_run_id'] = observed['run_id']
                run['ended_at'] = _iso()
                write_json(_run_path(root, run['run_id']), run)
                _settle(root, state, run); _publish(root, store, run)
                executed += 1; failed += run['status'] != 'complete'
                if interrupted is not None: raise interrupted
            if executed == max_runs: stop_reason = 'max_runs'
        finally:
            state.update(runner_status='idle', runner_pid=None)
            write_json(root / 'state.json', state)
    return dict(_summary(root, config, state), status='failed' if failed else 'complete' if executed else 'bounded_stop',
                runs_executed=executed, stop_reason=stop_reason)
