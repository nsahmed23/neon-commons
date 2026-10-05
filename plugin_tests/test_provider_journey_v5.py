"""Real CLI prompts/signatures/typed adapter; modeled provider commands only."""
import base64
import copy
from dataclasses import asdict
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch
import uuid
import zipfile

from intune_iac import cli, provider_execution as pe, approval_authority as aa
from intune_iac import provider_journey as pj
from intune_iac.io import AppError, canonical, digest, load_json, write_json
from plugin_tests.test_provider_execution_v5 import FIXTURE, OBJECT_ID, SCHEMA, raw_state, shown, plan


class ModelCommands:
    """Independent command responses persisted as synthetic saved plans."""
    def __init__(self, initial):
        self.remote = copy.deepcopy(initial)
        self.commands = []
        self.failure = None

    def run(self, executor, name, *, plan_sha=None):
        executor._integrity(); self.commands.append(name)
        if name == 'init': (executor.work / '.terraform.lock.hcl').write_text('modeled fixed lock')
        elif name == 'schema': return {'provider_schemas': {pe.SOURCE: {'resource_schemas': {pe.RESOURCE: SCHEMA}}}}
        elif name == 'validate': return {'valid': True}
        elif name == 'import': write_json(executor.work / 'terraform.tfstate', raw_state(self.remote))
        elif name == 'state': return shown(self.remote)
        elif name in ('ordinary', 'refresh', 'readback', 'second'):
            document = plan(self.remote, executor.manifest['desired'], refresh=name in ('refresh', 'readback'))
            with zipfile.ZipFile(executor.work / (name + '.plan'), 'w') as archive:
                archive.writestr('tfstate', canonical(raw_state(self.remote)))
                archive.writestr('tfplan', canonical(document))
        elif name.endswith('_show'):
            with zipfile.ZipFile(executor.work / (name.removesuffix('_show') + '.plan')) as archive:
                return json.loads(archive.read('tfplan'))
        elif name == 'apply':
            assert load_json(executor.root / 'operation.json')['status'] == 'mutation_started'
            self.remote = copy.deepcopy(executor.manifest['desired'])
            if self.failure == 'lost_response': raise AppError('modeled_lost', 'Modeled response loss.')
            if self.failure == 'partial':
                self.remote['assignments'] = copy.deepcopy(executor.manifest['initial']['assignments'])
                raise AppError('modeled_partial', 'Modeled partial write.')
            write_json(executor.work / 'terraform.tfstate', raw_state(self.remote, serial=2))


class ProviderJourneyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.host = self.base / 'operator'; self.host.mkdir(mode=0o700)
        self.session = self.base / 'session.json'
        self.binary = self.base / 'modeled-binary'; self.binary.write_bytes(b'modeled-not-native')
        initial = pe._configuration(FIXTURE)
        desired = copy.deepcopy(initial); desired['name'] = 'changed\x1b[2Jmodeled name'; desired['assignments'].pop()
        self.executor = pe.create_laboratory_executor(self.base / 'executor',
            pins=pe.ProviderPins(pe._sha(self.binary), pe._sha(self.binary), digest(SCHEMA), 'modeled', '1.10.0'),
            tofu=self.binary, provider=self.binary, initial_configuration=initial, admitted_configuration=desired,
            object_id=OBJECT_ID, source_sha256='1'*64, admission_sha256='2'*64, target_sha256='3'*64)
        self.model = ModelCommands(initial)
        model = self.model
        self.patcher = patch.object(pe.ProviderExecutor, '_run', lambda e, n, **kw: model.run(e, n, **kw))
        self.patcher.start(); self.addCleanup(self.patcher.stop)
        self.key = self.base / 'independent-issuer.pem'
        subprocess.run(['/usr/bin/openssl', 'genpkey', '-algorithm', 'ED25519', '-out', str(self.key)], check=True, capture_output=True)
        public = subprocess.run(['/usr/bin/openssl', 'pkey', '-in', str(self.key), '-pubout', '-outform', 'DER'], check=True, capture_output=True).stdout[-32:]
        pin = aa.VerifierPin(Path('/usr/bin/openssl'), pe._sha(Path('/usr/bin/openssl')))
        self.policy = {'schema_version': 'provider-operator-policy/1.0', 'authority_root': str(self.host / 'authority'),
            'verifier': {k: str(v) if isinstance(v, Path) else v for k, v in asdict(pin).items()},
            'approvers': [{'issuer': 'fixture-issuer', 'key_id': 'fixture-key', 'approver_id': 'fixture-reviewer',
                'public_key_hex': public.hex(), 'permitted_modes': ['laboratory'],
                'permitted_actions': ['provider_update', 'provider_no_change']}],
            'executors': [{'root': str(self.executor.root), 'manifest_sha256': digest(self.executor.manifest), 'mode': 'laboratory'}]}
        self.policy_path = self.host / 'policy.json'; write_json(self.policy_path, self.policy)

    def journey(self):
        return pj.ProviderJourney(self.executor.root, self.session, self.policy_path)

    def receipt(self, **changes):
        request = load_json(self.executor.root / 'prepared.json')
        payload = {'schema_version': 'signed-operation-approval/1.0', 'issuer': 'fixture-issuer',
            'key_id': 'fixture-key', 'approver_id': 'fixture-reviewer', 'operation_id': request['operation_id'],
            'request_sha256': digest(request), 'issued_at': int(time.time()), 'expires_at': int(time.time()) + 120,
            'nonce': uuid.uuid4().hex}
        payload.update(changes)
        message = self.base / 'issuer-message'; signature = self.base / 'issuer-signature'
        message.write_bytes(aa.SIGNATURE_DOMAIN + canonical(payload))
        subprocess.run(['/usr/bin/openssl', 'pkeyutl', '-sign', '-rawin', '-inkey', str(self.key),
            '-in', str(message), '-out', str(signature)], check=True, capture_output=True)
        path = self.base / 'receipt.json'
        write_json(path, {'payload': payload, 'signature': base64.b64encode(signature.read_bytes()).decode()})
        return path

    def command(self, action, *extra):
        return ['provider', action, '--executor-root', str(self.executor.root), '--session', str(self.session),
                '--authority-config', str(self.policy_path), *extra]

    def test_prepare_review_signed_execute_and_restart_use_typed_adapter(self):
        journey = self.journey()
        self.assertIs(type(journey.executor), pe.ProviderExecutor)
        prepared = journey.prepare()
        self.assertEqual(prepared['status'], 'needs_review')
        summary = journey.review()
        self.assertEqual(summary['mode'], 'laboratory')
        self.assertEqual(summary['bindings']['state_sha256'], load_json(self.executor.root / 'prepared.json')['bindings']['state_sha256'])
        self.assertNotIn('\x1b', json.dumps(summary))
        journey.approve(self.receipt())
        result = journey.execute()
        self.assertEqual(result['status'], 'verified')
        self.assertFalse(result['production_qualified'])
        self.assertEqual(self.journey().status()['status'], 'verified')
        self.assertEqual(self.model.commands.count('apply'), 1)
        with self.assertRaises(AppError): self.journey().execute()

    def test_actual_wizard_prompts_signed_receipt_and_no_boolean_approval(self):
        commands = iter(['prepare', 'review', 'approve', 'execute', 'status', 'save'])
        def answer(prompt):
            return str(self.receipt()) if prompt == 'Receipt file: ' else next(commands)
        out = io.StringIO()
        with patch('builtins.input', side_effect=answer), patch('sys.stdout', out):
            code = cli.main(self.command('wizard'))
        self.assertEqual(code, 0)
        self.assertIn('laboratory', out.getvalue())
        self.assertNotIn('\x1b', out.getvalue())
        self.assertEqual(self.model.commands.count('apply'), 1)
        self.assertNotIn('signature', self.session.read_text())
        self.assertNotIn('approved', load_json(self.session))

    def test_suspend_resume_discards_approval_and_requires_review(self):
        first = self.journey(); first.prepare(); first.review(); first.approve(self.receipt())
        first.suspend('save')
        with self.assertRaises(AppError): first.execute()
        resumed = self.journey()
        with self.assertRaises(AppError): resumed.execute()
        with self.assertRaises(AppError): resumed.approve(self.receipt())
        resumed.review(); resumed.approve(self.receipt())
        self.assertEqual(resumed.execute()['status'], 'verified')

    def test_back_cancel_edit_and_review_discard_in_memory_approval(self):
        journey = self.journey(); journey.prepare()
        for operation in ('back', 'cancel', 'edit', 'save'):
            journey.review(); journey.approve(self.receipt())
            journey.suspend(operation)
            with self.subTest(operation=operation), self.assertRaises(AppError): journey.execute()
        journey.review(); journey.approve(self.receipt()); journey.review()
        with self.assertRaises(AppError): journey.execute()

    def test_session_flags_or_changed_prepared_bytes_cannot_resume_authority(self):
        journey = self.journey(); journey.prepare()
        session = load_json(self.session); session['approved'] = True; write_json(self.session, session)
        with self.assertRaises(AppError): self.journey()
        del session['approved']; write_json(self.session, session)
        prepared = load_json(self.executor.root / 'prepared.json'); prepared['bindings']['target_sha256'] = '9'*64
        write_json(self.executor.root / 'prepared.json', prepared)
        with self.assertRaises(AppError): self.journey().review()

    def test_new_session_cannot_legitimize_forged_prepared_target(self):
        self.journey().prepare(); self.session.unlink()
        request = load_json(self.executor.root / 'prepared.json'); request['bindings']['scope_sha256'] = '8'*64
        write_json(self.executor.root / 'prepared.json', request)
        with self.assertRaises(AppError): self.journey().review()
        self.assertNotIn('apply', self.model.commands)

    def test_changed_policy_plan_or_state_blocks_approved_dispatch(self):
        journey = self.journey(); journey.prepare(); journey.review(); journey.approve(self.receipt())
        (self.executor.work / 'ordinary.plan').write_bytes(b'changed saved plan')
        with self.assertRaises(AppError): journey.execute()
        self.assertNotIn('apply', self.model.commands)

    def test_forged_verified_journal_is_not_evidence_of_completion(self):
        self.journey().prepare()
        request = load_json(self.executor.root / 'prepared.json')
        write_json(self.executor.root / 'operation.json', {'operation_id': request['operation_id'],
            'request_sha256': digest(request), 'status': 'verified', 'mutation_attempts': 1, 'production_qualified': False})
        with self.assertRaises(AppError): self.journey().status()

    def test_incomplete_journal_reconstructs_unknown_and_boolean_attempts_rejected(self):
        journey = self.journey(); journey.prepare(); journey.review(); journey.approve(self.receipt())
        with journey._authorization: pass
        request = load_json(self.executor.root / 'prepared.json')
        journal = {'operation_id': request['operation_id'], 'request_sha256': digest(request),
                   'status': 'mutation_started', 'mutation_attempts': 1, 'production_qualified': False}
        write_json(self.executor.root / 'operation.json', journal)
        self.assertEqual(self.journey().status()['status'], 'outcome_unknown')
        journal['mutation_attempts'] = True; write_json(self.executor.root / 'operation.json', journal)
        with self.assertRaises(AppError): self.journey().status()

    def test_unsigned_journal_cannot_authorize_reconciliation(self):
        self.journey().prepare()
        request = load_json(self.executor.root / 'prepared.json')
        write_json(self.executor.root / 'operation.json', {'operation_id': request['operation_id'],
            'request_sha256': digest(request), 'status': 'mutation_started', 'mutation_attempts': 1, 'production_qualified': False})
        with self.assertRaises(AppError): self.journey().reconcile()
        self.assertNotIn('readback', self.model.commands)

    def test_consumed_approval_and_convergence_do_not_prove_saved_plan_executed(self):
        journey = self.journey(); journey.prepare(); journey.review(); journey.approve(self.receipt())
        with journey._authorization: pass
        request = load_json(self.executor.root / 'prepared.json')
        self.model.remote = copy.deepcopy(self.executor.manifest['desired'])
        write_json(self.executor.work / 'terraform.tfstate', raw_state(self.model.remote, serial=2))
        write_json(self.executor.root / 'operation.json', {'operation_id': request['operation_id'],
            'request_sha256': digest(request), 'status': 'mutation_started', 'mutation_attempts': 1, 'production_qualified': False})
        result = self.journey().reconcile()
        self.assertEqual(result['status'], 'desired_state_observed_execution_unconfirmed')
        self.assertFalse(result['exact_plan_returned'])
        self.assertNotIn('apply', self.model.commands)
        # Even complete local state/plan evidence plus a spent approval cannot
        # manufacture the private dispatch/outcome attestation.
        operation = load_json(self.executor.root / 'operation.json')
        operation['status'] = 'verified'
        operation['reconciliation'].update(status='verified', exact_plan_returned=True)
        operation['execution_outcome'] = copy.deepcopy(operation['reconciliation'])
        write_json(self.executor.root / 'operation.json', operation)
        with self.assertRaises(AppError): self.journey().status()

    def test_session_cannot_overwrite_executor_control_files(self):
        with self.assertRaises(AppError):
            pj.ProviderJourney(self.executor.root, self.executor.root / 'prepared.json', self.policy_path)

    def test_lost_response_restarts_read_only_reconciliation_and_never_retries(self):
        journey = self.journey(); journey.prepare(); journey.review(); journey.approve(self.receipt())
        self.model.failure = 'lost_response'
        self.assertEqual(journey.execute()['status'], 'outcome_unknown')
        resumed = self.journey()
        self.assertEqual(resumed.status()['status'], 'outcome_unknown')
        with self.assertRaises(AppError): resumed.approve(self.receipt())
        self.model.commands.clear()
        self.assertEqual(resumed.reconcile()['status'], 'service_converged_state_unreconciled')
        self.assertEqual(self.model.commands, ['readback', 'readback_show', 'second', 'second_show'])
        with self.assertRaises(AppError): resumed.execute()

    def test_private_policy_and_executor_admission_are_required(self):
        self.policy_path.chmod(0o644)
        with self.assertRaises(AppError): self.journey()
        self.policy_path.chmod(0o600)
        self.policy['executors'][0]['manifest_sha256'] = '0'*64; write_json(self.policy_path, self.policy)
        with self.assertRaises(AppError): self.journey()

    def test_operator_policy_changed_after_receipt_verification_blocks_execution(self):
        journey = self.journey(); journey.prepare(); journey.review(); journey.approve(self.receipt())
        self.policy['approvers'][0]['approver_id'] = 'changed-reviewer'; write_json(self.policy_path, self.policy)
        with self.assertRaises(AppError): journey.execute()
        self.assertNotIn('apply', self.model.commands)

    def test_recovery_statuses_do_not_return_success_exit_code(self):
        for status in ('partial_or_divergent', 'service_converged_state_unreconciled', 'readback_unresolved', 'desired_state_observed_execution_unconfirmed'):
            with self.subTest(status=status): self.assertNotEqual(cli.exit_code({'status': status}), 0)

    def test_policy_inside_repository_or_executor_and_signing_key_fields_rejected(self):
        self.policy['signing_key'] = str(self.key); write_json(self.policy_path, self.policy)
        with self.assertRaises(AppError): self.journey()
        del self.policy['signing_key']; write_json(self.policy_path, self.policy)
        (self.host / '.git').mkdir()
        with self.assertRaises(AppError): self.journey()

    def test_forged_receipt_wrong_signature_expiry_and_live_mode_rejected(self):
        journey = self.journey(); journey.prepare(); journey.review()
        forged = self.base / 'forged.json'; write_json(forged, {'verified': True})
        for receipt in [forged, self.receipt(expires_at=int(time.time()) - 1)]:
            with self.subTest(receipt=receipt), self.assertRaises(AppError): journey.approve(receipt)
        self.assertNotIn('apply', self.model.commands)
        self.policy['executors'][0]['mode'] = 'live'; write_json(self.policy_path, self.policy)
        with self.assertRaises(AppError): self.journey()

    def test_cli_closed_routes_and_action_registry_unchanged(self):
        from intune_iac.runner import REGISTRY
        for name in REGISTRY:
            self.assertNotIn(name, {'provider_prepare', 'provider_execute', 'target_authenticate'})
        with patch('sys.stderr', io.StringIO()), self.assertRaises(SystemExit):
            cli.parser().parse_args(['provider', 'execute', '--command', 'arbitrary'])
        self.assertIn('provider_journey', cli.doctor()['capabilities'])

    def test_provider_platform_failure_is_explicit_before_native_import(self):
        args = cli.parser().parse_args(self.command('status'))
        with patch.object(cli.sys, 'platform', 'win32'), patch.object(cli.shutil, 'which', return_value=None):
            self.assertEqual(cli.doctor()['capabilities']['provider_journey'], 'unsupported_platform')
            with self.assertRaises(AppError) as caught: cli.execute(args)
        self.assertEqual(caught.exception.code, 'provider_platform_unsupported')


class IdentityAuthenticationCliTests(unittest.TestCase):
    def test_explicit_fd_credentials_strict_config_and_redacted_output(self):
        from intune_iac import identity_binding as ib
        from plugin_tests.test_identity_binding_v5 import config, RecordedServices, Clock
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); path = root / 'identity.json'; write_json(path, asdict(config()))
            files = [root / 'provider.secret', root / 'backend.secret']
            for i, p in enumerate(files): p.write_bytes(('synthetic-secret-' + str(i)).encode()); p.chmod(0o600)
            descriptors = [os.open(p, os.O_RDONLY) for p in files]
            seen = []
            def laboratory_recording(cfg, **kwargs):
                seen.extend([kwargs['provider_credential'], kwargs['backend_credential']])
                return ib.bind_laboratory(cfg, **kwargs, transport=RecordedServices(), clock=Clock())
            try:
                with patch.object(ib, 'bind_live', side_effect=laboratory_recording), patch.dict(os.environ, {'M365_CLIENT_SECRET': 'ambient'}):
                    result = cli.execute(cli.parser().parse_args(['target', 'authenticate', '--input', str(path),
                        '--provider-secret-fd', str(descriptors[0]), '--backend-secret-fd', str(descriptors[1])]))
                self.assertEqual(result['assurance'], 'laboratory_recorded_responses')
                self.assertNotIn('synthetic-secret', json.dumps(result))
                for handle in seen:
                    with self.assertRaises(AppError): handle._get()
            finally:
                for fd in descriptors: os.close(fd)

    def test_no_secret_flags_or_unbounded_fd_inputs(self):
        with patch('sys.stderr', io.StringIO()), self.assertRaises(SystemExit):
            cli.parser().parse_args(['target', 'authenticate', '--secret', 'never-accepted'])
        with tempfile.TemporaryFile() as stream:
            stream.write(b'x' * 4097); stream.seek(0)
            with self.assertRaises(AppError): pj.read_credential_fd(stream.fileno())

    def test_path_only_descriptor_is_rejected_without_leak(self):
        if not hasattr(os, 'O_PATH'): self.skipTest('O_PATH unavailable')
        with tempfile.NamedTemporaryFile() as stream:
            descriptor = os.open(stream.name, os.O_PATH)
            try:
                before = len(os.listdir('/proc/self/fd'))
                for _ in range(3):
                    with self.assertRaises(AppError): pj.read_credential_fd(descriptor)
                self.assertEqual(len(os.listdir('/proc/self/fd')), before)
            finally: os.close(descriptor)

    def test_pipe_requires_eof_within_deadline_and_restores_flags(self):
        import fcntl
        read_fd, write_fd = os.pipe()
        try:
            flags = fcntl.fcntl(read_fd, fcntl.F_GETFL)
            with patch.object(pj.select, 'select', return_value=([], [], [])), self.assertRaises(AppError) as caught:
                pj.read_credential_fd(read_fd)
            self.assertEqual(caught.exception.code, 'identity_credential_fd_deadline')
            self.assertEqual(fcntl.fcntl(read_fd, fcntl.F_GETFL), flags)
        finally: os.close(read_fd); os.close(write_fd)


if __name__ == '__main__': unittest.main()
