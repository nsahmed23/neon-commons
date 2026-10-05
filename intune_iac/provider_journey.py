"""Closed provider journey: operator pins, real signatures, no live execution.

The host provisions and admits generated executors independently. This module
does not generate HCL, discover credentials, issue approval signatures or extend
MCP. Session JSON is a locator/binding record, never execution authority.
"""
from __future__ import annotations

from dataclasses import asdict, fields
import fcntl
import os
from pathlib import Path
import re
import select
import stat
import time
import uuid

from . import approval_authority as aa
from . import provider_execution as pe
from .io import AppError, canonical, digest, load_json, parse_json, write_json

_MODES = frozenset({'laboratory', 'native_provider_network_denied'})
_ACTIONS = frozenset({'provider_update', 'provider_no_change'})
_REQUEST_KEYS = frozenset({'version', 'operation_id', 'action', 'mode', 'bindings', 'prepared_at', 'laboratory', 'execution_authorized'})
_BINDING_KEYS = frozenset({'binary_plan_sha256', 'plan_json_sha256', 'configuration_sha256', 'target_sha256',
    'toolchain_sha256', 'provider_schema_sha256', 'provider_lock_sha256', 'state_sha256', 'state_lineage_sha256',
    'state_serial', 'source_sha256', 'admission_sha256', 'object_id_sha256', 'executor_sha256', 'scope_sha256', 'implementation_sha256'})
_SESSION_KEYS = frozenset({'schema_version', 'executor_root_sha256', 'executor_manifest_sha256', 'policy_sha256', 'prepared_request_sha256'})
_RESULTS = frozenset({'mutation_started', 'apply_returned', 'outcome_unknown', 'verified',
                      'partial_or_divergent', 'service_converged_state_unreconciled', 'readback_unresolved',
                      'desired_state_observed_execution_unconfirmed'})


def _fail(code):
    raise AppError(code, 'The provider journey could not establish its required binding.') from None


def _safe(path):
    if not isinstance(path, (str, Path)): _fail('journey_path_invalid')
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)): _fail('journey_symlink_rejected')
    return Path(os.path.abspath(path))


def _private(path, *, directory=False):
    path = _safe(path)
    info = path.stat()
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077 or (not directory and info.st_nlink != 1):
        _fail('journey_private_host_file_required')
    return path


def _bounded_private_json(path):
    path = _private(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077 or info.st_nlink != 1 or not 0 < info.st_size <= 65536:
            _fail('journey_private_host_file_required')
        data = source.read(65537)
    if len(data) > 65536: _fail('journey_document_limit')
    return parse_json(data)


def _outside_repository(path):
    if any((parent / '.git').exists() or (parent / '.git').is_symlink() for parent in (path.parent, *path.parents)):
        _fail('journey_operator_policy_in_repository')


def _absolute(value):
    if type(value) is not str or not Path(value).is_absolute() or len(value) > 4096 or any(ord(c) < 32 or ord(c) == 127 for c in value):
        _fail('journey_operator_policy_shape')
    return _safe(value)


class _OperatorPolicy:
    def __init__(self, path, executor_root):
        self.path = _private(path); _private(self.path.parent, directory=True)
        _outside_repository(self.path)
        self.executor_root = _private(executor_root, directory=True)
        if self.path.is_relative_to(self.executor_root): _fail('journey_operator_policy_in_executor')
        value = _bounded_private_json(self.path)
        required = {'schema_version', 'authority_root', 'verifier', 'approvers', 'executors'}
        if type(value) is not dict or set(value) != required or value['schema_version'] != 'provider-operator-policy/1.0':
            _fail('journey_operator_policy_shape')
        verifier = value['verifier']
        if type(verifier) is not dict or set(verifier) != {'executable', 'sha256', 'validator_library', 'validator_sha256'}:
            _fail('journey_operator_policy_shape')
        pin = aa.VerifierPin(_absolute(verifier['executable']), verifier['sha256'],
                            _absolute(verifier['validator_library']), verifier['validator_sha256'])
        approvers = value['approvers']
        if type(approvers) is not list or not 1 <= len(approvers) <= 32: _fail('journey_operator_policy_shape')
        entries = []
        for row in approvers:
            if type(row) is not dict or set(row) != {'issuer', 'key_id', 'approver_id', 'public_key_hex', 'permitted_modes', 'permitted_actions'}:
                _fail('journey_operator_policy_shape')
            for field, permitted in (('permitted_modes', _MODES), ('permitted_actions', _ACTIONS)):
                items = row[field]
                if type(items) is not list or not items or any(type(x) is not str for x in items) or len(set(items)) != len(items) or not set(items) <= permitted:
                    _fail('journey_operator_policy_shape')
            entries.append(aa.TrustedApprover(row['issuer'], row['key_id'], row['approver_id'], row['public_key_hex'],
                           frozenset(row['permitted_modes']), frozenset(row['permitted_actions'])))
        executors = value['executors']
        if type(executors) is not list or not 1 <= len(executors) <= 128: _fail('journey_operator_policy_shape')
        admitted = {}; roots = set()
        for row in executors:
            if type(row) is not dict or set(row) != {'root', 'manifest_sha256', 'mode'} or type(row['manifest_sha256']) is not str or not pe.HASH.fullmatch(row['manifest_sha256']) or row['mode'] not in _MODES:
                _fail('journey_operator_policy_shape')
            root = _absolute(row['root'])
            if root in roots: _fail('journey_operator_policy_shape')
            roots.add(root)
            if root == self.executor_root: admitted = row
        if not admitted: _fail('journey_executor_not_admitted')
        self.authority_root = _absolute(value['authority_root'])
        if self.authority_root.is_relative_to(self.executor_root) or self.executor_root.is_relative_to(self.authority_root):
            _fail('journey_authority_overlap')
        _outside_repository(self.authority_root / 'store')
        _private(self.authority_root.parent, directory=True)
        self.sha256, self.admitted = digest(value), admitted.copy()
        self.authority = aa.ApprovalAuthority(self.authority_root, pin, entries)
        self.recheck()

    def recheck(self):
        _private(self.path.parent, directory=True)
        if digest(_bounded_private_json(self.path)) != self.sha256: _fail('journey_operator_policy_changed')
        _private(self.executor_root, directory=True)
        if digest(load_json(self.executor_root / 'executor.json')) != self.admitted['manifest_sha256']:
            _fail('journey_executor_admission_changed')


class ProviderJourney:
    """One admitted typed executor and memory-only approval/review state."""
    def __init__(self, executor_root, session, authority_config):
        self.root = _safe(executor_root)
        self.policy = _OperatorPolicy(authority_config, self.root)
        self.executor = pe.ProviderExecutor(self.root)
        if type(self.executor) is not pe.ProviderExecutor: _fail('journey_typed_executor_required')
        self.mode = 'laboratory' if self.executor.manifest.get('laboratory') is True else 'native_provider_network_denied'
        if self.mode != self.policy.admitted['mode']: _fail('journey_executor_mode_mismatch')
        self.session = _safe(session); _private(self.session.parent, directory=True)
        if self.session == self.policy.path or self.session.is_relative_to(self.policy.authority_root) or self.session.is_relative_to(self.root):
            _fail('journey_session_overlap')
        self._authorization = None
        self._reviewed_sha = None
        self._session_value = {'schema_version': 'provider-journey-session/1.0', 'executor_root_sha256': digest(str(self.root)),
            'executor_manifest_sha256': self.executor._manifest_sha, 'policy_sha256': self.policy.sha256,
            'prepared_request_sha256': None}
        if self.session.exists():
            existing = _bounded_private_json(self.session)
            if type(existing) is not dict or set(existing) != _SESSION_KEYS or any(existing[k] != v for k, v in self._session_value.items() if k != 'prepared_request_sha256'):
                _fail('journey_session_binding_changed')
            expected = existing['prepared_request_sha256']
            if expected is not None and (type(expected) is not str or not pe.HASH.fullmatch(expected)):
                _fail('journey_session_shape')
            self._session_value = existing
        self._request_if_present()
        self._save()

    def _save(self):
        _private(self.session.parent, directory=True)
        if self.session.exists(): _private(self.session)
        write_json(self.session, self._session_value)

    def _check(self):
        self.policy.recheck(); self.executor._integrity()

    def _request_if_present(self):
        self._check()
        path = self.root / 'prepared.json'
        if not path.exists():
            if self._session_value['prepared_request_sha256'] is not None or (self.root / 'operation.json').exists():
                _fail('journey_prepared_evidence_missing')
            return None
        request = load_json(path)
        if (type(request) is not dict or set(request) != _REQUEST_KEYS or request.get('version') != 'provider-operation/1.0'
                or request.get('mode') != self.mode or type(request.get('laboratory')) is not bool
                or request['laboratory'] != (self.mode == 'laboratory') or request.get('execution_authorized') is not False
                or request.get('action') not in _ACTIONS or type(request.get('prepared_at')) is not int
                or request['prepared_at'] > int(time.time()) + 5):
            _fail('journey_prepared_request_invalid')
        try:
            if str(uuid.UUID(request['operation_id'])) != request['operation_id']: _fail('journey_prepared_request_invalid')
        except (TypeError, ValueError, AttributeError): _fail('journey_prepared_request_invalid')
        bindings = request['bindings']
        if type(bindings) is not dict or set(bindings) != _BINDING_KEYS:
            _fail('journey_prepared_request_invalid')
        if any(type(v) is not str or not pe.HASH.fullmatch(v) for k, v in bindings.items() if k != 'state_serial') or type(bindings['state_serial']) is not int or bindings['state_serial'] < 0:
            _fail('journey_prepared_request_invalid')
        manifest = self.executor.manifest
        expected = {k: manifest[k] for k in ('configuration_sha256', 'source_sha256', 'admission_sha256', 'target_sha256')}
        expected.update(toolchain_sha256=digest(manifest['pins']), provider_schema_sha256=manifest['pins']['selected_schema_sha256'],
            provider_lock_sha256=pe._sha(self.executor.work / '.terraform.lock.hcl'), object_id_sha256=digest(manifest['object_id']),
            executor_sha256=self.executor._manifest_sha, implementation_sha256=digest(manifest['implementation_files']),
            scope_sha256=digest({'target_sha256': manifest['target_sha256'], 'object_id_sha256': digest(manifest['object_id'])}))
        if any(bindings[k] != v for k, v in expected.items()): _fail('journey_prepared_target_mismatch')
        mutation = (self.root / 'operation.json').exists()
        self.executor._request(request, original_state=not mutation)
        if not mutation:
            state = pe._raw_state(self.executor.work / 'terraform.tfstate', manifest['object_id'])
            if state['observed'] != manifest['initial'] or state['sha256'] != bindings['state_sha256'] or digest(state['lineage']) != bindings['state_lineage_sha256'] or state['serial'] != bindings['state_serial']:
                _fail('journey_prepared_state_mismatch')
        request_sha = digest(request)
        if self._session_value['prepared_request_sha256'] not in (None, request_sha): _fail('journey_prepared_request_changed')
        self._session_value['prepared_request_sha256'] = request_sha
        return request

    def _request(self):
        request = self._request_if_present()
        if request is None: _fail('journey_prepare_required')
        return request

    def _operation(self, request):
        path = self.root / 'operation.json'
        if not path.exists(): return None
        operation = load_json(path)
        if type(operation) is not dict or set(operation) - {'operation_id', 'request_sha256', 'status', 'mutation_attempts', 'production_qualified', 'reconciliation', 'execution_outcome'} or operation.get('operation_id') != request['operation_id'] or operation.get('request_sha256') != digest(request) or type(operation.get('mutation_attempts')) is not int or operation.get('mutation_attempts') != 1 or operation.get('production_qualified') is not False or operation.get('status') not in _RESULTS:
            _fail('journey_operation_journal_invalid')
        # Executor-local flags never prove the host spent an approval. The
        # persistent authority is a separate, operator-owned security domain.
        self.policy.authority.assert_consumed(request)
        if operation['status'] == 'verified':
            # A status flag cannot establish completion after restart. Rebuild
            # the local result from typed state and saved readback/second plan.
            # These remain local evidence, never an assertion of live access.
            report = operation.get('reconciliation')
            prior = operation.get('execution_outcome')
            if type(prior) is not dict or prior.get('exact_plan_returned') is not True:
                _fail('journey_verified_execution_unconfirmed')
            self.policy.authority.assert_outcome(request, prior)
            expected_assurance = 'laboratory_only' if self.mode == 'laboratory' else 'native_provider_local_state'
            if (type(report) is not dict or set(report) != {'operation_id', 'mutation_attempts', 'retry_authorized',
                    'production_qualified', 'assurance', 'readback_sha256', 'second_plan_json_sha256', 'state_sha256', 'status', 'exact_plan_returned'}
                    or report.get('status') != 'verified' or report.get('operation_id') != request['operation_id']
                    or report.get('exact_plan_returned') is not True
                    or type(report.get('mutation_attempts')) is not int or report['mutation_attempts'] != 1
                    or report.get('retry_authorized') is not False or report.get('production_qualified') is not False
                    or report.get('assurance') != expected_assurance):
                _fail('journey_verified_evidence_missing')
            manifest = self.executor.manifest
            state = pe._raw_state(self.executor.work / 'terraform.tfstate', manifest['object_id'])
            if (state['observed'] != manifest['desired'] or state['sha256'] != report['state_sha256']
                    or digest(state['lineage']) != request['bindings']['state_lineage_sha256']
                    or state['serial'] < request['bindings']['state_serial']
                    or digest(manifest['desired']) != report['readback_sha256']
                    or pe._saved_snapshot(self.executor.work / 'readback.plan', manifest['object_id']) != manifest['desired']):
                _fail('journey_verified_state_changed')
            second = self.executor._run('second_show')
            pe._plan(second, manifest['object_id'], manifest['desired'], engine_version=self.executor.engine_version,
                     no_change=True, allow_drift=True)
            if digest(second) != report['second_plan_json_sha256']: _fail('journey_verified_plan_changed')
        return operation

    def status(self):
        request = self._request_if_present()
        result = {'status': 'unprepared', 'mode': self.mode, 'production_qualified': False,
                  'live_service_qualified': False, 'execution_authorized': False, 'approval_retained': False}
        if request is None:
            if (self.executor.work / 'terraform.tfstate').exists() or (self.executor.work / 'ordinary.plan').exists():
                result.update(status='blocked', reason='preparation_incomplete', requires_new_executor=True)
            return result
        operation = self._operation(request)
        state = operation['status'] if operation else 'needs_review'
        if state in ('mutation_started', 'apply_returned'): state = 'outcome_unknown'
        retained = operation is None and type(self._authorization) is aa.ApprovedExecution and self._reviewed_sha == digest(request)
        if retained: state = 'receipt_verified_in_memory'
        result.update(operation_id=request['operation_id'], request_sha256=digest(request),
                      status=state, approval_retained=retained,
                      mutation_attempts=operation['mutation_attempts'] if operation else 0,
                      retry_authorized=False)
        if operation:
            result['next_action'] = 'reconcile_read_only' if operation['status'] != 'verified' else 'complete_local_verification'
        return result

    def prepare(self):
        self.suspend('resume')
        if (self.root / 'operation.json').exists(): _fail('journey_mutation_already_attempted')
        if self._request_if_present() is None:
            self.executor.prepare()
        self._request(); self._save()
        return self.status()

    def review(self):
        self._authorization = None; self._reviewed_sha = None
        request = self._request()
        operation = self._operation(request)
        if operation is None:
            plan = self.executor._run('ordinary_show', plan_sha=request['bindings']['binary_plan_sha256'])
            action = pe._plan(plan, self.executor.manifest['object_id'], self.executor.manifest['desired'], self.executor.manifest['initial'],
                              engine_version=self.executor.engine_version)
            if digest(plan) != request['bindings']['plan_json_sha256'] or request['action'] != ('provider_update' if action == 'update' else 'provider_no_change'):
                _fail('journey_saved_plan_mismatch')
            self._request()
            self._reviewed_sha = digest(request)
        self._save()
        return {'status': 'review_only', 'operation_id': request['operation_id'], 'request_sha256': digest(request),
                'mode': self.mode, 'action': request['action'], 'bindings': request['bindings'].copy(),
                'mutation_attempts': operation['mutation_attempts'] if operation else 0,
                'production_qualified': False, 'live_service_qualified': False,
                'execution_authorized': False, 'external_signed_receipt_required': True,
                'changes_require_new_admitted_executor': True}

    def approve(self, receipt_path):
        self._authorization = None
        request = self._request()
        if self._operation(request) is not None: _fail('journey_mutation_already_attempted')
        if self._reviewed_sha != digest(request): _fail('journey_fresh_review_required')
        receipt = _bounded_private_json(receipt_path)
        # The guard is closed host code. No callback, module or command can be
        # supplied through CLI, operator policy, session, request or receipt.
        def recheck():
            self._check()
            self.executor._request(request, original_state=not (self.root / 'operation.json').exists())
        guard = aa.make_laboratory_guard(request, recheck)
        self._authorization = self.policy.authority.authorize(request, receipt, guard=guard)
        return {'status': 'receipt_verified_in_memory', 'operation_id': request['operation_id'],
                'request_sha256': digest(request), 'mode': self.mode, 'execution_authorized': False,
                'production_qualified': False, 'live_service_qualified': False}

    def execute(self):
        authorization, self._authorization = self._authorization, None
        request = self._request()
        if self._operation(request) is not None: _fail('journey_mutation_already_attempted')
        if self._reviewed_sha != digest(request) or type(authorization) is not aa.ApprovedExecution:
            _fail('journey_signed_receipt_required')
        self._reviewed_sha = None
        try: return self.executor.apply(request, authorization=authorization)
        finally: self._save()

    def reconcile(self):
        self._authorization = None; self._reviewed_sha = None
        request = self._request()
        if self._operation(request) is None: _fail('journey_no_mutation_to_reconcile')
        result = self.executor.reconcile(request, authority=self.policy.authority)
        self._save()
        return result

    def suspend(self, reason='save'):
        if reason not in ('save', 'cancel', 'back', 'edit', 'resume'): _fail('journey_navigation_invalid')
        self._authorization = None; self._reviewed_sha = None
        self._save()
        return {'status': 'cancelled' if reason == 'cancel' else 'suspended', 'approval_retained': False,
                'execution_authorized': False, 'production_qualified': False,
                'changes_require_new_admitted_executor': reason in ('edit', 'back')}


def run_provider_wizard(executor_root, session, authority_config):
    """Actual prompt route. All displayed external content is ASCII-escaped JSON."""
    import json
    journey = ProviderJourney(executor_root, session, authority_config)
    print('Provider journey: network-denied execution only; live services are unqualified.')
    print('Commands: prepare, review, approve, execute, reconcile, status, back, edit, resume, save, cancel.')
    while True:
        try: command = input('provider> ').strip().lower()
        except (EOFError, KeyboardInterrupt): return journey.suspend('save')
        try:
            if command in ('save', 'cancel'): return journey.suspend(command)
            if command in ('back', 'edit', 'resume'): result = journey.suspend(command)
            elif command == 'approve':
                try: receipt = input('Receipt file: ')
                except (EOFError, KeyboardInterrupt): return journey.suspend('save')
                result = journey.approve(receipt)
            elif command == 'prepare': result = journey.prepare()
            elif command == 'review': result = journey.review()
            elif command == 'execute': result = journey.execute()
            elif command == 'reconcile': result = journey.reconcile()
            elif command == 'status': result = journey.status()
            else: result = {'status': 'invalid_command', 'reason': 'choose_a_listed_command'}
        except AppError as error:
            journey._authorization = None; journey._reviewed_sha = None
            result = {'status': 'blocked', 'error': {'code': error.code}, 'approval_retained': False}
        print(json.dumps(result, ensure_ascii=True, sort_keys=True, allow_nan=False))


def provider_command(args):
    if args.provider_command == 'wizard':
        return run_provider_wizard(args.executor_root, args.session, args.authority_config)
    journey = ProviderJourney(args.executor_root, args.session, args.authority_config)
    if args.provider_command == 'prepare': return journey.prepare()
    if args.provider_command == 'review': return journey.review()
    if args.provider_command == 'status': return journey.status()
    if args.provider_command == 'reconcile': return journey.reconcile()
    if args.provider_command == 'execute':
        journey.review(); journey.approve(args.receipt)
        return journey.execute()
    _fail('journey_command_invalid')


def read_credential_fd(descriptor):
    """Read one explicitly inherited private file/pipe, never ambient input."""
    if type(descriptor) is not int or descriptor < 3: _fail('identity_explicit_credential_fd_required')
    fd = os.dup(descriptor)
    original_flags = None
    try:
        info = os.fstat(fd)
        regular = stat.S_ISREG(info.st_mode)
        if not regular and not stat.S_ISFIFO(info.st_mode): _fail('identity_credential_fd_type')
        if regular and (info.st_uid != os.geteuid() or info.st_mode & 0o077): _fail('identity_credential_fd_private')
        if regular and info.st_size > 4096: _fail('identity_credential_fd_limit')
        original_flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        if original_flags & getattr(os, 'O_PATH', 0):
            original_flags = None
            _fail('identity_credential_fd_type')
        if original_flags & os.O_ACCMODE != os.O_RDONLY: _fail('identity_credential_fd_read_only')
        fcntl.fcntl(fd, fcntl.F_SETFL, original_flags | os.O_NONBLOCK)
        deadline, data = time.monotonic() + 5, bytearray()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0: _fail('identity_credential_fd_deadline')
            ready, _, _ = select.select([fd], [], [], remaining)
            if not ready: _fail('identity_credential_fd_deadline')
            try: block = os.read(fd, 4097 - len(data))
            except BlockingIOError: continue
            if not block: break
            data.extend(block)
            if len(data) > 4096: _fail('identity_credential_fd_limit')
        try: return data.decode('ascii')
        except UnicodeDecodeError: _fail('identity_credential_invalid')
    finally:
        try:
            if original_flags is not None: fcntl.fcntl(fd, fcntl.F_SETFL, original_flags)
        finally: os.close(fd)


def authenticate_target(args):
    """Read-only explicit identity collection; only its redacted report leaves."""
    from . import identity_binding as ib
    value = load_json(args.input)
    if type(value) is not dict or set(value) != {'cloud', 'provider', 'backend_identity', 'backend'}:
        _fail('identity_configuration_invalid')
    for field, spec in (('provider', ib.IdentitySpec), ('backend_identity', ib.IdentitySpec), ('backend', ib.BackendSpec)):
        if type(value[field]) is not dict or set(value[field]) != {row.name for row in fields(spec)}:
            _fail('identity_configuration_invalid')
    if args.provider_secret_fd == args.backend_secret_fd: _fail('identity_separate_credential_fds_required')
    config = ib.BindingConfig(ib.IdentitySpec(**value['provider']), ib.IdentitySpec(**value['backend_identity']),
                              ib.BackendSpec(**value['backend']), value['cloud'])
    provider = backend = None
    try:
        provider = ib.ClientSecretHandle(read_credential_fd(args.provider_secret_fd))
        backend = ib.ClientSecretHandle(read_credential_fd(args.backend_secret_fd))
        return ib.bind_live(config, provider_credential=provider, backend_credential=backend).evidence()
    finally:
        if provider is not None: provider.close()
        if backend is not None: backend.close()
