"""Durable service-side job contract with explicit, network-denied local adapters.

The terminal can prepare/review/inspect/cancel a job. A separately invoked worker
consumes an independent signed approval and dispatches its exact saved plan once.
Reopening never starts or retries work. This is common-contract and native local
qualification infrastructure, not a live Graph/Azure execution service.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import stat
import time
import uuid

from . import approval_authority as aa, implementation_history as history, protected, provider_execution as pe
from .io import AppError, canonical, digest, load_json, parse_json
from .provider_journey import _bounded_private_json, _outside_repository, _private, _absolute

_HASH = re.compile(r'^[0-9a-f]{64}$')
_REVISION = re.compile(r'^[0-9a-f]{40}$')
_LABEL = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.:/@-]{0,255}$')
_PROFILES = {'synthetic_local_process_only': protected.SyntheticExecutor,
             'native_local_opentofu_only': protected.NativeLocalExecutor}
_TERMINAL = {'verified_local', 'cancelled_before_dispatch', 'outcome_unknown'}


def _fail(code):
    raise AppError(code, 'The protected worker job could not establish its required contract.') from None


def _implementation():
    return {name: pe._sha(Path(__file__).with_name(name)) for name in
            ('protected_worker.py', 'protected.py', 'provider_execution.py', 'approval_authority.py',
             'provider_journey.py', 'azure_backend.py', 'execution.py', 'io.py', 'native_pins.py')}


def _context(value):
    keys = {'schema_version', 'evidence_class', 'repository', 'source_revision', 'source_root', 'source_files',
            'workflow_revision', 'verifier_revision', 'run_id', 'run_attempt', 'tenant', 'cloud',
            'stack', 'component', 'provider_principal', 'backend_principal', 'ownership',
            'effective_inputs_sha256', 'provider_lock_sha256', 'backend'}
    if type(value) is not dict or set(value) != keys or value['schema_version'] != 'worker-context/1.0':
        _fail('worker_context_invalid')
    if value['evidence_class'] != 'laboratory_declared_context' or value['cloud'] != 'laboratory':
        _fail('worker_live_profile_unimplemented')
    if any(type(value[k]) is not str or not _REVISION.fullmatch(value[k]) for k in
           ('source_revision', 'workflow_revision', 'verifier_revision')):
        _fail('worker_context_invalid')
    for key in ('repository', 'run_id', 'tenant', 'stack', 'component', 'provider_principal', 'backend_principal'):
        if type(value[key]) is not str or not _LABEL.fullmatch(value[key]): _fail('worker_context_invalid')
    if type(value['run_attempt']) is not int or not 1 <= value['run_attempt'] <= 1000:
        _fail('worker_context_invalid')
    for key in ('effective_inputs_sha256', 'provider_lock_sha256'):
        if type(value[key]) is not str or not _HASH.fullmatch(value[key]): _fail('worker_context_invalid')
    backend = value['backend']
    if (type(backend) is not dict or set(backend) != {'kind', 'identity_sha256'} or
            backend['kind'] != 'local_fixture' or type(backend['identity_sha256']) is not str or
            not _HASH.fullmatch(backend['identity_sha256'])):
        _fail('worker_live_profile_unimplemented')
    ownership = value['ownership']
    if (type(ownership) is not list or not 1 <= len(ownership) <= 100 or
            any(type(item) is not str or not _LABEL.fullmatch(item) for item in ownership) or
            len(set(ownership)) != len(ownership)):
        _fail('worker_context_invalid')
    if len(canonical(value)) > 32768: _fail('worker_context_limit')
    root = _absolute(value['source_root'])
    files = value['source_files']
    if type(files) is not dict or not 1 <= len(files) <= 128: _fail('worker_source_invalid')
    total_source_bytes = 0
    for relative, expected in files.items():
        if (type(relative) is not str or not relative or len(relative) > 512 or
                relative.startswith('/') or '\\' in relative or any(p in ('', '.', '..') for p in relative.split('/')) or
                type(expected) is not str or not _HASH.fullmatch(expected)):
            _fail('worker_source_invalid')
        path = root / relative
        try:
            metadata = path.stat(); total_source_bytes += metadata.st_size
            if total_source_bytes > 16 * 1024 * 1024: _fail('worker_source_limit')
            if metadata.st_nlink != 1 or pe._sha(path) != expected: _fail('worker_source_changed')
        except OSError: _fail('worker_source_changed')
    return parse_json(canonical(value))


class WorkerPolicy:
    """External host policy; writable job/repository content cannot supply trust."""
    def __init__(self, path):
        self.path = _private(path); _private(self.path.parent, directory=True)
        _outside_repository(self.path)
        value = _bounded_private_json(self.path)
        if (type(value) is not dict or set(value) != {'schema_version', 'authority_root', 'jobs_root', 'verifier', 'approvers', 'executors'} or
                value['schema_version'] != 'protected-worker-policy/1.0'):
            _fail('worker_policy_invalid')
        self.authority_root = _absolute(value['authority_root']); self.jobs_root = _absolute(value['jobs_root'])
        _private(self.jobs_root, directory=True); _outside_repository(self.authority_root / 'store')
        _private(self.authority_root.parent, directory=True)
        if (self.authority_root == self.jobs_root or self.authority_root.is_relative_to(self.jobs_root) or
                self.jobs_root.is_relative_to(self.authority_root) or self.path.is_relative_to(self.jobs_root)):
            _fail('worker_policy_overlap')
        verifier = value['verifier']
        if type(verifier) is not dict or set(verifier) != {'executable', 'sha256', 'validator_library', 'validator_sha256'}:
            _fail('worker_policy_invalid')
        pin = aa.VerifierPin(_absolute(verifier['executable']), verifier['sha256'],
                             _absolute(verifier['validator_library']), verifier['validator_sha256'])
        approvers = []
        if type(value['approvers']) is not list or not 1 <= len(value['approvers']) <= 32:
            _fail('worker_policy_invalid')
        for row in value['approvers']:
            if type(row) is not dict or set(row) != {'issuer', 'key_id', 'approver_id', 'public_key_hex'}:
                _fail('worker_policy_invalid')
            approvers.append(aa.TrustedApprover(**row, permitted_modes=frozenset({'laboratory'}),
                permitted_actions=frozenset({'provider_update', 'provider_no_change'})))
        self.executors = {}
        if type(value['executors']) is not list or not 1 <= len(value['executors']) <= 128:
            _fail('worker_policy_invalid')
        for row in value['executors']:
            if (type(row) is not dict or set(row) != {'root', 'manifest_sha256', 'context_sha256', 'profile'} or
                    row['profile'] not in _PROFILES or
                    any(type(row[k]) is not str or not _HASH.fullmatch(row[k]) for k in ('manifest_sha256', 'context_sha256'))):
                _fail('worker_policy_invalid')
            root = _absolute(row['root']); _private(root, directory=True)
            if (root in self.executors or self.authority_root.is_relative_to(root) or root.is_relative_to(self.authority_root) or
                    self.path.is_relative_to(root) or self.jobs_root.is_relative_to(root) or root.is_relative_to(self.jobs_root)):
                _fail('worker_policy_overlap')
            self.executors[root] = dict(row)
        self.sha256 = digest(value)
        self.authority = aa.ApprovalAuthority(self.authority_root, pin, approvers)
        self.database = self.authority_root / 'worker.sqlite3'
        try:
            fd = os.open(self.database, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            os.fsync(fd); os.close(fd); protected._sync(self.authority_root)
        except FileExistsError: pass
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, root TEXT UNIQUE NOT NULL, manifest_sha256 TEXT NOT NULL, status TEXT NOT NULL, cancel_requested INTEGER NOT NULL, dispatches INTEGER NOT NULL, outcome TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS ownership (scope TEXT PRIMARY KEY, job_id TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS events (sequence INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL, created_at INTEGER NOT NULL)')
            db.execute('COMMIT')
        protected._sync(self.authority_root)

    def check(self):
        if digest(_bounded_private_json(self.path)) != self.sha256: _fail('worker_policy_changed')

    @contextmanager
    def connection(self):
        _private(self.authority_root, directory=True); _private(self.database)
        for suffix in ('-journal', '-wal', '-shm'):
            sibling = Path(str(self.database) + suffix)
            if sibling.exists() or sibling.is_symlink(): _private(sibling)
        db = sqlite3.connect(self.database, timeout=0, isolation_level=None)
        try:
            db.execute('PRAGMA synchronous=FULL'); db.execute('PRAGMA journal_mode=DELETE'); db.execute('PRAGMA trusted_schema=OFF')
            yield db
        except sqlite3.Error:
            _fail('worker_store_unavailable')
        finally: db.close()

    def event(self, db, job_id, kind, payload):
        db.execute('INSERT INTO events(job_id,kind,payload,created_at) VALUES (?,?,?,?)',
                   (job_id, kind, canonical(payload).decode(), int(time.time())))


def _request(manifest):
    native = manifest['native_request']; context = manifest['context']
    return {'version': 'provider-operation/1.0', 'operation_id': str(uuid.UUID(native['operation_id'])),
            'action': 'provider_no_change' if native['review']['status'] == 'no_change' else 'provider_update',
            'mode': 'laboratory', 'laboratory': True, 'execution_authorized': False,
            'prepared_at': native['created_at'], 'bindings': {
                'scope_sha256': digest({'tenant': context['tenant'], 'ownership': sorted(context['ownership'])}),
                'target_sha256': digest(context), 'binary_plan_sha256': native['bindings']['saved_plan_sha256'],
                'worker_manifest_sha256': digest(manifest), 'native_request_sha256': digest(native),
                'implementation_sha256': digest(manifest['implementation_files'])}}


def prepare_job(job_root, *, executor_root, context, policy_path):
    policy = WorkerPolicy(policy_path); policy.check()
    job_root = _absolute(str(job_root)); executor_root = _absolute(str(executor_root))
    if job_root.parent != policy.jobs_root: _fail('worker_job_outside_policy')
    context = _context(context)
    admission = policy.executors.get(executor_root)
    if not admission or admission['context_sha256'] != digest(context): _fail('worker_executor_not_admitted')
    if digest(load_json(executor_root / 'executor.json')) != admission['manifest_sha256']:
        _fail('worker_executor_changed')
    executor = _PROFILES[admission['profile']](executor_root)
    native = protected.prepare_native_operation(executor)
    manifest = {'schema_version': 'protected-worker-job/1.0', 'profile': executor.mode,
                'policy_sha256': policy.sha256, 'executor_root': str(executor_root),
                'executor_manifest_sha256': admission['manifest_sha256'], 'context': context,
                'native_request': native, 'implementation_files': _implementation(),
                'claims': {'ci_authenticated': False, 'service_identity_authenticated': False,
                           'azure_backend_used': False, 'production_authorized': False}}
    if len(canonical(manifest)) > 65536: _fail('worker_manifest_limit')
    try: job_root.mkdir(mode=0o700, exist_ok=False)
    except FileExistsError: _fail('worker_job_exists')
    protected._exclusive(job_root / 'manifest.json', canonical(manifest))
    protected._exclusive(job_root / 'approval-request.json', canonical(_request(manifest)))
    identifier = native['operation_id']
    try:
        with policy.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0] >= 10000: _fail('worker_store_capacity')
            db.execute('INSERT INTO jobs VALUES (?,?,?,?,0,0,NULL)', (identifier, str(job_root), digest(manifest), 'prepared'))
            for owner in context['ownership']:
                scope = digest({'tenant': context['tenant'], 'object_and_assignment_owner': owner})
                db.execute('INSERT INTO ownership VALUES (?,?)', (scope, identifier))
            policy.event(db, identifier, 'prepared', {'manifest_sha256': digest(manifest)})
            db.execute('COMMIT')
        protected._sync(policy.authority_root)
    except AppError:
        # Prepared native plan and job artifacts remain intact after conflict.
        raise
    return {'status': 'prepared', 'operation_id': identifier, 'manifest_sha256': digest(manifest),
            'approval_request': _request(manifest), 'profile': executor.mode, 'production_authorized': False}


class WorkerJob:
    def __init__(self, job_root, policy_path):
        self.policy = WorkerPolicy(policy_path); self.root = _private(job_root, directory=True)
        if self.root.parent != self.policy.jobs_root: _fail('worker_job_outside_policy')
        self.manifest = _bounded_private_json(self.root / 'manifest.json')
        if (type(self.manifest) is not dict or set(self.manifest) != {'schema_version', 'profile', 'policy_sha256',
                'executor_root', 'executor_manifest_sha256', 'context', 'native_request', 'implementation_files', 'claims'} or
                self.manifest['schema_version'] != 'protected-worker-job/1.0' or self.manifest['profile'] not in _PROFILES):
            _fail('worker_job_invalid')
        self.identifier = self.manifest['native_request']['operation_id']
        self.request = _request(self.manifest)
        self._executor = None
        self._attestation()

    @property
    def executor(self):
        if self._executor is None:
            self._executor = _PROFILES[self.manifest['profile']](_absolute(self.manifest['executor_root']))
        return self._executor

    def _row(self):
        with self.policy.connection() as db:
            row = db.execute('SELECT root,manifest_sha256,status,cancel_requested,dispatches,outcome FROM jobs WHERE id=?', (self.identifier,)).fetchone()
        if row is None or row[:2] != (str(self.root), digest(self.manifest)): _fail('worker_job_not_attested')
        return row

    def _attestation(self):
        self.policy.check()
        if self.manifest['policy_sha256'] != self.policy.sha256: _fail('worker_policy_changed')
        if digest(_bounded_private_json(self.root / 'manifest.json')) != digest(self.manifest): _fail('worker_job_changed')
        if canonical(_bounded_private_json(self.root / 'approval-request.json')) != canonical(self.request): _fail('worker_request_changed')
        self._row()

    def _implementation_finding(self):
        """The relation of the request's recorded implementation to the current one, and which of the worker's own
        bound files differ from the job's record. A result of reading; it authorizes nothing."""
        try:
            found = dict(protected.implementation_relation(self.manifest['native_request']))
            recorded, current = self.manifest['implementation_files'], _implementation()
        except (AppError, OSError) as error:
            return {'relation': 'not_established', 'failure_code': getattr(error, 'code', type(error).__name__)}
        found['worker_relation'] = history.worker_relation(recorded, current)['relation']
        found['worker_files_changed'] = sorted(name for name in set(recorded) | set(current) if recorded.get(name) != current.get(name))
        return found

    def check(self, *, active=False, implementation='current'):
        """The job's attestation and, unless implementation='recorded', the current-implementation comparison.

        'recorded' is for observation only (reconcile). Both implementations the job recorded are judged against the
        inventories: the protected request's digest must not be unknown, and the worker's own file set must equal the
        current one or be a registered worker release. A recognised protected upgrade never waives the worker
        comparison. Dispatch never passes it."""
        if implementation not in ('current', 'recorded'): raise ValueError('implementation must be current or recorded')
        self._attestation()
        if implementation == 'recorded' and protected.implementation_relation(self.manifest['native_request'])['relation'] == 'unknown':
            _fail('implementation_unknown')
        recorded_files, current_files = self.manifest['implementation_files'], _implementation()
        if recorded_files != current_files and (
                implementation != 'recorded' or history.worker_relation(recorded_files, current_files)['relation'] != 'known_earlier'):
            _fail('worker_implementation_changed')
        admission = self.policy.executors.get(self.executor.root)
        if (not admission or admission['manifest_sha256'] != self.manifest['executor_manifest_sha256'] or
                admission['context_sha256'] != digest(_context(self.manifest['context'])) or
                admission['profile'] != self.manifest['profile'] or digest(self.executor.manifest) != admission['manifest_sha256']):
            _fail('worker_executor_changed')
        row = self._row()
        if active and row[3]: _fail('worker_cancellation_requested')
        if active:
            # The shared window judges expiry on the effective time and records a reached expiry before refusing,
            # so a rollback and a restart cannot reopen this job (Astra, lanes/advisor-time-consumers). The window
            # alone: this check also guards a running apply, whose runtime files must not be inspected here.
            try:
                protected.check_approval_window(self.manifest['native_request'], executor=self.executor)
            except AppError as error:
                if error.code == 'expired_request': _fail('worker_request_expired')
                raise

    def status(self):
        self._attestation(); row = self._row()
        try:
            self.check(); validation = {'status': 'valid'}
        except (AppError, OSError) as error:
            validation = {'status': 'invalidated', 'failure_code': getattr(error, 'code', type(error).__name__)}
        with self.policy.connection() as db:
            events = [{'sequence': sequence, 'kind': kind, 'payload': parse_json(payload), 'created_at': created}
                      for sequence, kind, payload, created in db.execute(
                          'SELECT sequence,kind,payload,created_at FROM events WHERE job_id=? ORDER BY sequence LIMIT 100', (self.identifier,))]
        status = 'dispatch_outcome_pending_or_unknown' if row[2] == 'dispatched' and row[5] is None else row[2]
        consumed = False
        try:
            self.policy.authority.assert_consumed(self.request); consumed = True
        except AppError as error:
            if error.code != 'approval_consumption_missing': raise
        if consumed and status == 'prepared': status = 'approval_consumed_dispatch_not_recorded'
        return {'schema_version': 'protected-worker-status/1.0', 'operation_id': self.identifier,
                'status': status, 'durable_worker_state': row[2], 'approval_consumed': consumed, 'execution_validation': validation, 'cancellation_requested': bool(row[3]), 'mutation_attempts': row[4],
                'outcome': parse_json(row[5]) if row[5] else None, 'events': events,
                'implementation': self._implementation_finding(),
                'profile': self.manifest['profile'], 'reopening_dispatches': False,
                'retry_authorized': False, 'production_authorized': False}

    def cancel(self):
        self._attestation()
        with self.policy.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT status,dispatches FROM jobs WHERE id=?', (self.identifier,)).fetchone()
            if row[0] not in _TERMINAL:
                next_status = 'cancelled_before_dispatch' if row[1] == 0 else row[0]
                db.execute('UPDATE jobs SET cancel_requested=1,status=? WHERE id=?', (next_status, self.identifier))
                if row[1] == 0: db.execute('DELETE FROM ownership WHERE job_id=?', (self.identifier,))
                self.policy.event(db, self.identifier, 'cancellation_requested', {'before_dispatch': row[1] == 0})
            db.execute('COMMIT')
        protected._sync(self.policy.authority_root)
        return self.status()

    def _record(self, report, *, verified=False):
        with self.policy.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT dispatches FROM jobs WHERE id=?', (self.identifier,)).fetchone()
            if row != (1,): _fail('worker_dispatch_missing')
            db.execute('UPDATE jobs SET status=?,outcome=? WHERE id=?',
                       ('verified_local' if verified else 'outcome_unknown', canonical(report).decode(), self.identifier))
            if verified: db.execute('DELETE FROM ownership WHERE job_id=?', (self.identifier,))
            self.policy.event(db, self.identifier, 'verified_local' if verified else 'outcome_unknown', report)
            db.execute('COMMIT')
        protected._sync(self.policy.authority_root)

    def _apply(self, permit):
        descriptors = []
        try:
            fd = os.open(self.executor.executable, os.O_RDONLY | os.O_NOFOLLOW); descriptors.append(fd)
            with os.fdopen(os.dup(fd), 'rb') as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != self.manifest['native_request']['bindings']['executable_sha256']:
                    _fail('worker_executable_changed')
            plan = pe._sealed_plan(self.executor.root / 'work/saved.tfplan', self.manifest['native_request']['bindings']['saved_plan_sha256'])
            descriptors.append(plan)
            worker_path = None
            if type(self.executor) is protected.SyntheticExecutor:
                worker = os.open(self.executor.root / 'worker.py', os.O_RDONLY | os.O_NOFOLLOW); descriptors.append(worker)
                with os.fdopen(os.dup(worker), 'rb') as stream:
                    if hashlib.file_digest(stream, 'sha256').hexdigest() != self.manifest['native_request']['bindings']['worker_sha256']:
                        _fail('worker_executable_changed')
                worker_path = '/proc/self/fd/' + str(worker)
            argv = protected._command(self.executor, 'apply', str(self.executor.executable), worker_path,
                                      '/proc/self/fd/' + str(plan))
            result = pe._supervise(argv, cwd=self.executor.root / 'work', env=protected._environment(self.executor),
                executable='/proc/self/fd/' + str(fd), pass_fds=tuple(descriptors), active_check=permit.check_active,
                timeout=30, output_limit=2 * 1024 * 1024)
            if result['code'] != 0: _fail('worker_native_apply_failed')
        finally:
            for descriptor in descriptors: os.close(descriptor)

    def run(self, receipt):
        self.check(active=True)
        if self._row()[2] != 'prepared': _fail('worker_dispatch_already_attempted')
        protected.validate_native_operation(self.manifest['native_request'], executor=self.executor,
                                            require_fresh=True, require_state=True)
        guard = aa.make_laboratory_guard(self.request, lambda: self.check(active=True))
        authorization = self.policy.authority.authorize(self.request, receipt, guard=guard)
        with authorization as permit:
            self.check(active=True)
            protected.validate_native_operation(self.manifest['native_request'], executor=self.executor,
                                                require_fresh=True, require_state=True)
            with self.policy.connection() as db:
                db.execute('BEGIN IMMEDIATE')
                cursor = db.execute('UPDATE jobs SET status=?,dispatches=1 WHERE id=? AND status=? AND dispatches=0 AND cancel_requested=0',
                                    ('dispatched', self.identifier, 'prepared'))
                if cursor.rowcount != 1: _fail('worker_dispatch_already_attempted')
                self.policy.event(db, self.identifier, 'dispatch_started', {'request_sha256': digest(self.request)})
                db.execute('COMMIT')
            protected._sync(self.policy.authority_root)
            report = {'operation_id': self.request['operation_id'], 'status': 'outcome_unknown',
                      'mutation_attempts': 1, 'exact_plan_returned': False, 'retry_authorized': False,
                      'profile': self.manifest['profile'], 'production_authorized': False}
            try:
                permit.mark_dispatch(); permit.check_active()
                self._apply(permit)
                permit.check_active()
                observed = protected.inspect_executor(self.executor)
                if not protected._desired_readback(self.manifest['native_request'], observed): _fail('worker_readback_mismatch')
                convergence = (protected.verify_native_convergence(self.executor, self.manifest['native_request'])
                               if type(self.executor) is protected.NativeLocalExecutor else
                               {'status': 'not_applicable', 'scope': 'synthetic_process_fixture_has_no_native_second_plan'})
                permit.check_active()
                report.update(status='verified_local', exact_plan_returned=True, readback=observed, convergence=convergence)
                permit.record_outcome(report)
                self._record(report, verified=True)
            except BaseException as error:
                unknown = {**report, 'status': 'outcome_unknown', 'exact_plan_returned': False,
                           'failure_code': getattr(error, 'code', type(error).__name__)}
                try: permit.record_outcome(unknown)
                except (AppError, OSError): pass
                self._record(unknown)
                if isinstance(error, (KeyboardInterrupt, SystemExit)): raise
            return self.status()

    def reconcile(self):
        """Observe existing bytes only: no plan, import, apply, unlock or retry.

        The job may predate an upgrade: its record is read as history and the relation is reported, but nothing is
        confirmed, authorized or released because history passed."""
        self.check(implementation='recorded')
        if self._row()[4] != 1: _fail('worker_reconciliation_not_required')
        observed = protected.inspect_executor(self.executor)
        result = {'operation_id': self.request['operation_id'], 'status': 'observed_only',
                  'desired_state_observed': protected._desired_readback(self.manifest['native_request'], observed),
                  'readback': observed, 'execution_confirmed': False, 'retry_authorized': False,
                  'implementation': self._implementation_finding()}
        with self.policy.connection() as db:
            db.execute('BEGIN IMMEDIATE'); self.policy.event(db, self.identifier, 'reconciliation_observed', result); db.execute('COMMIT')
        protected._sync(self.policy.authority_root)
        return result


def add_parser(commands):
    from .workbench_parsers import add_worker_parser
    return add_worker_parser(commands)


def command(args):
    if args.worker_command == 'prepare':
        return prepare_job(args.job_root, executor_root=args.executor_root,
                           context=load_json(args.context), policy_path=args.policy)
    job = WorkerJob(args.job_root, args.policy)
    if args.worker_command in ('status', 'attach'): return job.status()
    if args.worker_command == 'review':
        return {'status': 'reviewed', 'manifest': job.manifest, 'approval_request': job.request,
                'operation': job.status(), 'execution_authorized': False}
    if args.worker_command == 'run': return job.run(_bounded_private_json(args.receipt))
    if args.worker_command == 'cancel': return job.cancel()
    if args.worker_command == 'reconcile': return job.reconcile()
    _fail('worker_command_not_admitted')
