"""Persistent due-work adapter for an explicitly invoked Graph reader process.

No scheduler is installed or started here. A reviewed OS scheduler invokes the
same one-shot application entrypoint while every terminal is closed. A job
stores identity/scope and a credential *name*, never the credential value.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import math
import os
from pathlib import Path
import re
import shlex
import sys
import time
from uuid import uuid4

from .identity_binding import ClientSecretHandle, ServiceResponse
from .io import AppError, canonical, digest, file_sha, load_json, read_bytes, sync_directory, write_json
from .observation_reader import ReaderSpec, bind_live_reader, bind_laboratory_reader, publish_batch
from .workbench_store import WorkbenchStore

VERSION = 'intune-authenticated-observer/1'
FIXTURE_VERSION = 'intune-observer-fixture/1'
MAX_RUNS = 10000
MAX_RETAINED_BYTES = 512 * 1024 * 1024
COMMANDS = frozenset({'observer-create', 'observer-run', 'observer-status', 'observer-scheduler'})
common = None


def _fail(code):
    raise AppError(code, 'The observation job is changed, busy, incomplete or outside its explicit reader profile.')


def _supported():
    # Registering reader help must not make the complete text interface import
    # Linux-only fcntl on other hosts. Reject only this unqualified job route.
    global common
    if sys.platform != 'linux':
        _fail('observer_platform_unsupported')
    if common is None:
        from . import workbench_scheduler
        common = workbench_scheduler


def _spec(value):
    if type(value) is not dict or set(value) != {'tenant_id', 'client_id', 'principal_object_id', 'object_ids'}:
        _fail('observer_identity_invalid')
    return ReaderSpec(value['tenant_id'], value['client_id'], value['principal_object_id'], tuple(value['object_ids'])).validate()


def _store(config):
    store = WorkbenchStore(config['store_root'])
    if (store.tenant_id != config['identity']['tenant_id'] or common._identity(store.root) != config['store_identity']
            or common._identity(store.path) != config['database_identity']):
        _fail('observer_store_changed')
    return store


def _load(job):
    _supported()
    root = common._private(job, directory=True)
    config = load_json(common._private(root / 'config.json'))
    state = load_json(common._private(root / 'state.json'))
    if (type(config) is not dict or config.get('schema_version') != VERSION or config.get('job_root') != str(root)
            or config.get('profile') not in ('graph_public_live', 'laboratory_recorded_responses')
            or type(config.get('job_id')) is not str or not re.fullmatch('[0-9a-f]{32}', config['job_id'])
            or type(state) is not dict or state.get('config_sha256') != digest(config)
            or state.get('job_id') != config['job_id']):
        _fail('observer_config_changed')
    _spec(config['identity'])
    common._number(config['interval_seconds'], 60, 86400)
    common._number(config['max_duration_seconds'], 1, 300)
    if not re.fullmatch('[A-Za-z_][A-Za-z0-9_]{0,127}', config.get('secret_env', '')):
        _fail('observer_secret_name_invalid')
    for key in ('run_count', 'success_count', 'failure_count', 'interrupted_count', 'retained_capture_bytes', 'missed_cycles'):
        if type(state.get(key)) is not int or not 0 <= state[key] <= 9007199254740991:
            _fail('observer_state_invalid')
    if state['run_count'] > MAX_RUNS:
        _fail('observer_state_invalid')
    common._stamp(state['next_due'])
    if state.get('active_attempt') is not None and not re.fullmatch('[0-9a-f]{32}', state['active_attempt']):
        _fail('observer_state_invalid')
    return root, config, state


def create_job(store, spec, *, output, secret_env, interval_seconds=300, max_duration_seconds=120, laboratory_fixture=None):
    """Persist an inactive reader job. No credential lookup or network request."""
    _supported()
    store = store if type(store) is WorkbenchStore else WorkbenchStore(store)
    if type(spec) is not ReaderSpec:
        _fail('observer_identity_invalid')
    spec.validate()
    if spec.tenant_id != store.tenant_id:
        _fail('observer_wrong_tenant')
    interval = common._number(interval_seconds, 60, 86400)
    duration = common._number(max_duration_seconds, 1, 300)
    if type(secret_env) is not str or not re.fullmatch('[A-Za-z_][A-Za-z0-9_]{0,127}', secret_env):
        _fail('observer_secret_name_invalid')
    root = common._safe(output)
    if root.exists() or not root.parent.is_dir():
        _fail('observer_new_directory_required')
    if root == store.root or root in store.root.parents or store.root in root.parents:
        _fail('observer_path_overlap')
    fixture = None
    if laboratory_fixture is not None:
        path = common._safe(laboratory_fixture)
        _Fixture(read_bytes(path))
        fixture = {'path': str(path), 'sha256': file_sha(path)}
    config = {'schema_version': VERSION, 'job_id': uuid4().hex, 'job_root': str(root),
        'identity': asdict(spec), 'secret_env': secret_env,
        'store_root': str(store.root), 'store_identity': common._identity(store.root),
        'database_identity': common._identity(store.path), 'interval_seconds': interval,
        'max_duration_seconds': duration, 'runtime': common._runtime_binding(),
        'profile': 'laboratory_recorded_responses' if fixture else 'graph_public_live',
        'laboratory_fixture': fixture, 'created_at': common._iso(), 'mutation_authorized': False}
    state = {'schema_version': VERSION, 'job_id': config['job_id'], 'config_sha256': digest(config),
        'next_due': common._iso(), 'active_attempt': None, 'active_record': None,
        'run_count': 0, 'success_count': 0, 'failure_count': 0, 'interrupted_count': 0,
        'retained_capture_bytes': 0, 'missed_cycles': 0,
        'last_attempt': None, 'last_success': None, 'last_error': None}
    root.mkdir(mode=0o700)
    (root / 'runs').mkdir(mode=0o700)
    (root / 'captures').mkdir(mode=0o700)
    write_json(root / 'config.json', config)
    write_json(root / 'state.json', state)
    sync_directory(root)
    sync_directory(root.parent)
    return {**_summary(root, config, state), 'status': 'created'}


def _summary(root, config, state):
    age = None if state['last_success'] is None else time.time() - common._stamp(state['last_success'])
    return {**state, 'job_root': str(root), 'tenant_id': config['identity']['tenant_id'],
        'object_ids': config['identity']['object_ids'], 'profile': config['profile'],
        'interval_seconds': config['interval_seconds'], 'daemon_installed': False,
        'mutation_authorized': False, 'production_qualified': False,
        'freshness': 'unknown' if age is None else
            'stale' if state['last_error'] is not None or age < 0 or age > 2 * config['interval_seconds'] else 'fresh',
        'next_action': 'Invoke the approved scheduler or observer-run when due; inspect failed scopes before relying on freshness.',
        'limits': {'max_objects': 100, 'max_cycles': MAX_RUNS,
                   'retained_capture_bytes': MAX_RETAINED_BYTES,
                   'read_scope': 'Tenant-wide policy listing; settings and assignments only for declared immutable IDs.'}}


def job_status(job):
    root, config, state = _load(job)
    binding_error = None
    try:
        common._validate_runtime(config)
        _store(config)
    except AppError as error:
        binding_error = error.code
    try:
        with common._lock(root):
            active = False
    except AppError as error:
        if error.code != 'scheduler_already_running':
            raise
        active = True
    result = {**_summary(root, config, state), 'lock_held': active,
              'source_and_store_binding_valid': binding_error is None, 'binding_error': binding_error,
              'status': 'blocked' if binding_error else 'active' if active else 'interrupted_or_unconfirmed' if state['active_attempt'] else 'idle'}
    if binding_error:
        result['next_action'] = 'Inspect the changed source/store binding, preserve this job, and create a fresh reviewed job.'
    return result


class _Fixture:
    """An explicitly synthetic exact request script; no live transport route."""
    def __init__(self, raw):
        from .io import parse_json
        value = parse_json(raw)
        if (type(value) is not dict or set(value) != {'schema_version', 'responses'}
                or value['schema_version'] != FIXTURE_VERSION or type(value['responses']) is not list
                or not 1 <= len(value['responses']) <= 10000):
            _fail('observer_fixture_invalid')
        self.rows, self.position, self.requests = value['responses'], 0, []
        for row in self.rows:
            if (type(row) is not dict or set(row) - {'method', 'host', 'path', 'status', 'body', 'headers'}
                    or not {'method', 'host', 'path', 'status', 'body'} <= set(row)
                    or row['method'] not in ('GET', 'POST') or type(row['host']) is not str
                    or type(row['path']) is not str or type(row['status']) is not int
                    or not 100 <= row['status'] <= 599):
                _fail('observer_fixture_invalid')

    def __call__(self, request, *, timeout, max_bytes):
        if self.position >= len(self.rows):
            _fail('observer_fixture_exhausted')
        row = self.rows[self.position]
        actual = {'method': request.method, 'host': request.host, 'path': request.path}
        self.requests.append(actual)
        if any(actual[key] != row[key] for key in actual):
            _fail('observer_fixture_request_mismatch')
        self.position += 1
        raw = canonical(row['body'])
        if len(raw) > max_bytes:
            _fail('observer_fixture_response_limit')
        headers = tuple(tuple(pair) for pair in row.get('headers', [('Content-Type', 'application/json')]))
        return ServiceResponse(row['status'], headers, raw)


def _run_path(root, attempt):
    return root / 'runs' / (attempt + '.json')


def _settle(root, state, record):
    if state['active_attempt'] != record['attempt_id']:
        _fail('observer_state_invalid')
    state['active_attempt'], state['active_record'] = None, None
    state['last_attempt'], state['last_error'] = record['attempt_id'], record.get('error_code')
    state['next_due'] = record['next_due']
    state['retained_capture_bytes'] += record.get('capture_bytes', 0)
    if record['status'] == 'complete':
        state['success_count'] += 1
        state['last_success'] = record['ended_at']
    else:
        state['interrupted_count' if record['status'] == 'interrupted' else 'failure_count'] += 1
    write_json(root / 'state.json', state)


def _recover(root, config, state, store):
    attempt = state['active_attempt']
    if attempt is None:
        return
    path = _run_path(root, attempt)
    record = load_json(common._private(path)) if path.exists() else state['active_record']
    if type(record) is not dict or record.get('attempt_id') != attempt or record.get('job_id') != config['job_id']:
        _fail('observer_state_invalid')
    if record['status'] == 'collecting':
        # An interrupted process may have committed SQLite before its receipt.
        # Preserve that fact without recreating authentication or replaying reads.
        with store._connection() as db:
            ids = [row[0] for row in db.execute('SELECT run_id FROM run_details WHERE domain LIKE ? ORDER BY run_id',
                ('reader:' + config['job_id'] + ':' + attempt + ':%',))]
        found_before_recovery = bool(ids)
        if not ids:
            failures = [{'object_id': oid, 'error_code': 'observer_previous_runner_interrupted',
                         'observed_at': common._stamp(record['started_at'])} for oid in config['identity']['object_ids']]
            ids = [item['run_id'] for item in publish_batch(store, [], job_id=config['job_id'],
                                                           attempt_id=attempt, failures=failures)]
        staged = root / 'captures' / attempt
        if staged.exists():
            record['capture_bytes'] = _capture_size(staged)
        record.update(status='interrupted', error_code='observer_previous_runner_interrupted',
            ended_at=common._iso(), persisted_collection_run_ids=ids,
            publication_found_before_recovery=found_before_recovery,
            recovery='Previous bytes retained. New authentication and new reads are required; no mutation or implicit capture reimport.')
        write_json(path, record)
    _settle(root, state, record)


def _capture_size(path):
    # Exact newly created capture files only; refuse any unexpected file type.
    common._private(path, directory=True)
    total = 0
    for child in path.rglob('*'):
        if child.is_symlink():
            _fail('observer_capture_changed')
        if child.is_file():
            total += child.stat().st_size
        elif not child.is_dir():
            _fail('observer_capture_changed')
    return total


def run_due(job):
    """One due cycle. Suitable for independent systemd/cron invocation.

    The process owns its reader; closing a separate UI cannot cancel it. No
    subprocess, mutation executor, default credentials or activation is used.
    """
    root, config, state = _load(job)
    binding = digest(config)
    with common._lock(root):
        root, config, state = _load(root)
        if digest(config) != binding:
            _fail('observer_config_changed')
        common._validate_runtime(config)
        store = _store(config)
        _recover(root, config, state, store)
        now, due = time.time(), common._stamp(state['next_due'])
        if now < due:
            return {**_summary(root, config, state), 'status': 'not_due', 'network_attempted': False}
        if state['run_count'] >= MAX_RUNS or state['retained_capture_bytes'] >= MAX_RETAINED_BYTES:
            _fail('observer_retention_limit')
        missed = min(1000000, max(0, math.floor((now - due) / config['interval_seconds'])))
        state['missed_cycles'] += missed
        due = now if missed == 1000000 else due + missed * config['interval_seconds']
        attempt = uuid4().hex
        record = {'schema_version': VERSION, 'job_id': config['job_id'], 'attempt_id': attempt,
            'sequence': state['run_count'] + 1, 'status': 'collecting', 'started_at': common._iso(),
            'ended_at': None, 'next_due': common._iso(due + config['interval_seconds']),
            'config_sha256': binding, 'profile': config['profile'], 'collection_run_ids': [],
            'capture_bytes': 0, 'cloud_mutation': False, 'source_authenticity_verified': False}
        state.update(active_attempt=attempt, active_record=dict(record), run_count=record['sequence'])
        write_json(root / 'state.json', state)
        write_json(_run_path(root, attempt), record)
        captures, failures, reader, credential, fixture, interrupted = [], [], None, None, None, None
        capture_root = root / 'captures' / attempt
        capture_root.mkdir(mode=0o700)
        sync_directory(capture_root.parent)
        deadline = time.monotonic() + config['max_duration_seconds']
        spec = _spec(config['identity'])
        try:
            secret = os.environ.get(config['secret_env'])
            if not secret:
                _fail('observer_credential_missing')
            credential = ClientSecretHandle(secret)
            del secret
            if config['profile'] == 'laboratory_recorded_responses':
                source = config['laboratory_fixture']
                raw = read_bytes(common._safe(source['path']))
                if hashlib.sha256(raw).hexdigest() != source['sha256']:
                    _fail('observer_fixture_changed')
                fixture = _Fixture(raw)
                reader = bind_laboratory_reader(spec, credential=credential, transport=fixture,
                                               max_duration_seconds=config['max_duration_seconds'])
            else:
                if config['laboratory_fixture'] is not None:
                    _fail('observer_profile_changed')
                reader = bind_live_reader(spec, credential=credential, max_duration_seconds=config['max_duration_seconds'])
            record['reader_identity'] = reader.evidence()
            record['source_authenticity_verified'] = record['reader_identity']['source_authenticity_verified']
            for oid in spec.object_ids:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or state['retained_capture_bytes'] + record['capture_bytes'] >= MAX_RETAINED_BYTES:
                    failures.append({'object_id': oid, 'error_code': 'observer_capture_budget', 'observed_at': time.time()})
                    continue
                try:
                    captured = reader.capture(oid, capture_root / oid, max_elapsed_seconds=min(120, remaining))
                    captures.append(captured)
                    record['capture_bytes'] += _capture_size(capture_root / oid)
                    if captured.cancelled:
                        raise KeyboardInterrupt()
                except AppError as error:
                    failures.append({'object_id': oid, 'error_code': error.code, 'observed_at': time.time()})
            common._validate_runtime(config)
            _store(config)
            if digest(_load(root)[1]) != binding:
                _fail('observer_config_changed')
        except BaseException as error:
            code = error.code if isinstance(error, AppError) else 'observer_interrupted' if isinstance(error, (KeyboardInterrupt, SystemExit)) else 'observer_read_failed'
            record['error_code'] = code
            if code in ('scheduler_runtime_changed', 'observer_store_changed', 'observer_config_changed'):
                record['publication_blocked'] = True
            covered = {item._batch['object_id'] for item in captures} | {item['object_id'] for item in failures}
            failures.extend({'object_id': oid, 'error_code': code, 'observed_at': time.time()}
                            for oid in spec.object_ids if oid not in covered)
            if isinstance(error, (KeyboardInterrupt, SystemExit)):
                interrupted = error
        finally:
            if reader is not None:
                reader.close()
            if credential is not None:
                credential.close()
            if fixture is not None:
                record['laboratory_requests'] = fixture.requests
                record['laboratory_unconsumed_responses'] = len(fixture.rows) - fixture.position
        try:
            if record.get('publication_blocked'):
                _fail(record['error_code'])
            results = publish_batch(store, captures, job_id=config['job_id'], attempt_id=attempt, failures=failures)
            record['collection_run_ids'] = [item['run_id'] for item in results]
            record['scope_outcomes'] = [{'object_ids': item['scope']['object_ids'], 'status': item['status'],
                                         'coverage': item['coverage']} for item in results]
            complete = all(item['status'] == 'complete' and item['coverage'] == 'complete' for item in results)
            record['status'] = 'interrupted' if interrupted else 'complete' if complete else 'failed'
            if not complete:
                record.setdefault('error_code', 'observer_collection_incomplete')
        except (AppError, OSError) as error:
            record.update(status='failed', error_code=getattr(error, 'code', 'observer_publication_failed'),
                          publication='Atomic observation publication failed; prior observations retained; staged bytes preserved.')
        record['ended_at'] = common._iso()
        write_json(_run_path(root, attempt), record)
        _settle(root, state, record)
        if interrupted is not None:
            raise interrupted
        return {**_summary(root, config, state), 'status': record['status'],
                'attempt_receipt': str(_run_path(root, attempt)), 'collection_run_ids': record['collection_run_ids'],
                'scope_outcomes': record.get('scope_outcomes', [])}


def scheduler_artifacts(job, output):
    """Write inactive user-systemd units and an exact argv recipe; never install."""
    root, config, _ = _load(job)
    common._validate_runtime(config)
    target = common._safe(output)
    if target.exists() or not target.parent.is_dir():
        _fail('observer_new_directory_required')
    argv = [config['runtime']['interpreter'], '-I', '-B', config['runtime']['entrypoint'],
            'workbench', 'observer-run', '--job', str(root)]
    def unit_arg(value):
        if any(ord(c) < 32 or ord(c) > 126 for c in value):
            _fail('observer_scheduler_path_unsupported')
        return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%') + '"'
    service = '[Unit]\nDescription=Intune scoped read-only observation\n\n[Service]\nType=oneshot\nUMask=0077\nNoNewPrivileges=yes\n'
    service += 'EnvironmentFile=/REPLACE/WITH/APPROVED/PRIVATE/READER-ENV\n'
    service += 'ExecStart=' + ' '.join(unit_arg(value) for value in argv) + '\n'
    service += 'TimeoutStartSec=' + str(math.ceil(config['max_duration_seconds']) + 15) + '\nKillMode=control-group\nRestart=no\n'
    timer = '[Unit]\nDescription=Intune observation trigger\n\n[Timer]\nOnBootSec=60\nOnUnitActiveSec=' + str(int(config['interval_seconds'])) + '\nAccuracySec=1\nUnit=intune-observer.service\n\n[Install]\nWantedBy=timers.target\n'
    target.mkdir(mode=0o700)
    for name, text in [('intune-observer.service', service), ('intune-observer.timer', timer)]:
        common._save_bytes(target / name, text.encode('utf-8'))
    receipt = {'schema_version': VERSION, 'job_id': config['job_id'], 'argv': argv,
        'cron_command': shlex.join(argv).replace('%', '\\%'), 'credential_environment_name': config['secret_env'],
        'installed': False, 'activated': False, 'platform_qualified': False,
        'required_review': ['Approve exact host, job scope, source/interpreter hashes and read-only identity.',
            'Replace the EnvironmentFile placeholder with an approved private secret-delivery route; do not commit its contents.',
            'Install under a named unprivileged service owner only after authorization; qualify restart, permissions and stop/recovery on that host.',
            'Stop/disable the timer to stop future reads. An interrupted cycle preserves its raw bytes and last-good database.'],
        'files': {name: file_sha(target / name) for name in ('intune-observer.service', 'intune-observer.timer')}}
    write_json(target / 'scheduler-receipt.json', receipt)
    return {'status': 'prepared', 'output': str(target), **receipt}


def add_parser(sub):
    from .workbench_parsers import add_observer_parser
    return add_observer_parser(sub)


def command(args):
    if args.workbench_command == 'observer-create':
        return create_job(args.root, ReaderSpec(args.tenant, args.client, args.principal, tuple(sorted(args.object))),
            output=args.output, secret_env=args.secret_env, interval_seconds=args.interval_seconds,
            max_duration_seconds=args.max_duration_seconds, laboratory_fixture=args.laboratory_fixture)
    if args.workbench_command == 'observer-run':
        return run_due(args.job)
    if args.workbench_command == 'observer-status':
        return job_status(args.job)
    if args.workbench_command == 'observer-scheduler':
        return scheduler_artifacts(args.job, args.output)
    _fail('observer_command_invalid')
