"""Actual signed worker interfaces and subprocess effects; no live cloud claims."""
import base64
import copy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch
import uuid

from intune_iac import protected, protected_worker as worker, approval_authority as aa
from intune_iac.io import AppError, canonical, digest, load_json, write_json
from plugin_tests.signing_fixture import verifier_pin


class ProtectedWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(); self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.host = self.root / 'host'; self.host.mkdir(mode=0o700)
        self.jobs = self.root / 'jobs'; self.jobs.mkdir(mode=0o700)
        self.source = self.root / 'source'; self.source.mkdir(mode=0o700)
        (self.source / 'policy.json').write_text('{"setting":"new"}')
        self.executor = protected.create_synthetic_executor(self.root / 'executor',
            initial_value={'setting': 'old'}, desired_value={'setting': 'new'}, engine_version='1.10.0')
        self.context = {
            'schema_version': 'worker-context/1.0', 'evidence_class': 'laboratory_declared_context',
            'repository': 'fixture/repository', 'source_revision': '1' * 40,
            'source_root': str(self.source), 'source_files': {'policy.json': hashlib.sha256((self.source / 'policy.json').read_bytes()).hexdigest()},
            'workflow_revision': '2' * 40, 'verifier_revision': '3' * 40,
            'run_id': 'fixture-run-1', 'run_attempt': 1, 'tenant': 'fixture-tenant', 'cloud': 'laboratory',
            'stack': 'pilot', 'component': 'settings', 'provider_principal': 'fixture-provider',
            'backend_principal': 'fixture-backend', 'ownership': ['immutable-policy-and-assignments'],
            'effective_inputs_sha256': '4' * 64, 'provider_lock_sha256': '5' * 64,
            'backend': {'kind': 'local_fixture', 'identity_sha256': '6' * 64}}
        self.key = self.host / 'signer.pem'
        subprocess.run(['/usr/bin/openssl', 'genpkey', '-algorithm', 'ED25519', '-out', str(self.key)], check=True, capture_output=True)
        public = subprocess.run(['/usr/bin/openssl', 'pkey', '-in', str(self.key), '-pubout', '-outform', 'DER'], check=True, capture_output=True).stdout[-32:]
        pin = verifier_pin(Path('/usr/bin/openssl'), hashlib.sha256(Path('/usr/bin/openssl').read_bytes()).hexdigest())
        self.policy = {'schema_version': 'protected-worker-policy/1.0', 'authority_root': str(self.host / 'authority'),
            'jobs_root': str(self.jobs), 'verifier': {k: str(v) if isinstance(v, Path) else v for k, v in asdict(pin).items()},
            'approvers': [{'issuer': 'fixture-issuer', 'key_id': 'fixture-key', 'approver_id': 'independent-reviewer', 'public_key_hex': public.hex()}],
            'executors': [{'root': str(self.executor.root), 'manifest_sha256': digest(self.executor.manifest),
                           'context_sha256': digest(self.context), 'profile': self.executor.mode}]}
        self.policy_path = self.host / 'policy.json'; write_json(self.policy_path, self.policy)
        self.job_root = self.jobs / 'job-1'

    def prepare(self):
        return worker.prepare_job(self.job_root, executor_root=self.executor.root,
                                  context=self.context, policy_path=self.policy_path)

    def job(self): return worker.WorkerJob(self.job_root, self.policy_path)

    def receipt(self, **changes):
        request = load_json(self.job_root / 'approval-request.json')
        payload = {'schema_version': 'signed-operation-approval/1.0', 'issuer': 'fixture-issuer',
            'key_id': 'fixture-key', 'approver_id': 'independent-reviewer', 'operation_id': request['operation_id'],
            'request_sha256': digest(request), 'issued_at': int(time.time()),
            'expires_at': int(time.time()) + 120, 'nonce': uuid.uuid4().hex}
        payload.update(changes)
        message = self.host / 'message'; signature = self.host / 'signature'
        message.write_bytes(aa.SIGNATURE_DOMAIN + canonical(payload))
        subprocess.run(['/usr/bin/openssl', 'pkeyutl', '-sign', '-rawin', '-inkey', str(self.key),
            '-in', str(message), '-out', str(signature)], check=True, capture_output=True)
        return {'payload': payload, 'signature': base64.b64encode(signature.read_bytes()).decode()}

    def state(self): return load_json(self.executor.root / 'work/state/terraform.tfstate')

    def test_real_signed_dispatch_state_readback_and_restart_do_not_replay(self):
        prepared = self.prepare(); before = self.state(); receipt = self.receipt()
        result = self.job().run(receipt)
        self.assertEqual(result['status'], 'verified_local')
        self.assertEqual(result['mutation_attempts'], 1)
        self.assertEqual(self.state()['outputs']['fixture']['value'], {'setting': 'new'})
        self.assertEqual(self.state()['lineage'], before['lineage'])
        self.assertEqual(self.state()['serial'], before['serial'] + 1)
        self.assertEqual(self.job().status(), result)
        with self.assertRaises(AppError): self.job().run(receipt)
        self.assertEqual(self.state()['serial'], before['serial'] + 1)
        self.assertEqual(prepared['approval_request']['bindings']['worker_manifest_sha256'], digest(self.job().manifest))

    def test_forged_boolean_wrong_signer_and_expiry_do_not_dispatch(self):
        self.prepare(); before = self.state()
        for receipt in ({'approved': True}, self.receipt(approver_id='attacker'),
                        self.receipt(expires_at=int(time.time()) - 1)):
            with self.assertRaises(AppError): self.job().run(receipt)
            self.assertEqual(self.state(), before)
            self.assertEqual(self.job().status()['mutation_attempts'], 0)

    def test_plan_substitution_rejected_before_dispatch(self):
        self.prepare(); before = self.state(); receipt = self.receipt()
        (self.executor.root / 'work/saved.tfplan').write_bytes(b'substituted plan')
        with self.assertRaises(AppError): self.job().run(receipt)
        self.assertEqual(self.state(), before)

    def test_state_advance_between_review_and_execution_is_rejected(self):
        self.prepare(); receipt = self.receipt()
        value = self.state(); value['serial'] += 1
        write_json(self.executor.root / 'work/state/terraform.tfstate', value)
        with self.assertRaises(AppError): self.job().run(receipt)
        self.assertEqual(self.state(), value)
        self.assertEqual(self.job().status()['mutation_attempts'], 0)

    def test_source_or_job_run_attempt_substitution_invalidates_signed_job(self):
        self.prepare(); receipt = self.receipt(); before = self.state()
        (self.source / 'policy.json').write_text('{"setting":"unauthorized"}')
        with self.assertRaises(AppError): self.job().run(receipt)
        self.assertEqual(self.state(), before)
        (self.source / 'policy.json').write_text('{"setting":"new"}')
        manifest = load_json(self.job_root / 'manifest.json'); manifest['context']['run_attempt'] = 2
        write_json(self.job_root / 'manifest.json', manifest)
        with self.assertRaises(AppError): self.job().run(receipt)
        self.assertEqual(self.state(), before)

    def test_cancel_before_dispatch_is_durable_and_does_not_consume_approval(self):
        self.prepare(); receipt = self.receipt(); before = self.state()
        self.assertEqual(self.job().cancel()['status'], 'cancelled_before_dispatch')
        with self.assertRaises(AppError): self.job().run(receipt)
        self.assertEqual(self.state(), before)
        self.assertEqual(self.job().status()['mutation_attempts'], 0)
        with self.assertRaises(AppError): self.job().policy.authority.assert_consumed(self.job().request)

    def test_lost_response_preserves_unknown_and_readonly_recovery_never_replays(self):
        self.prepare(); before = self.state(); receipt = self.receipt()
        original = worker.WorkerJob._apply
        def lost_response(job, permit):
            original(job, permit)
            raise AppError('fixture_response_lost', 'Simulated response loss after actual subprocess write.')
        with patch.object(worker.WorkerJob, '_apply', lost_response): result = self.job().run(receipt)
        self.assertEqual(result['status'], 'outcome_unknown')
        self.assertFalse(result['outcome']['exact_plan_returned'])
        self.assertEqual(self.state()['serial'], before['serial'] + 1)
        after = self.state()
        recovered = self.job().reconcile()
        self.assertTrue(recovered['desired_state_observed'])
        self.assertFalse(recovered['execution_confirmed'])
        self.assertEqual(self.state(), after)
        with self.assertRaises(AppError): self.job().run(self.receipt())
        self.assertEqual(self.state(), after)

    def test_cancel_after_dispatch_stops_before_effect_and_keeps_unknown(self):
        self.prepare(); before = self.state(); receipt = self.receipt()
        original = worker.WorkerJob._apply
        def cancel_then_dispatch(job, permit):
            job.cancel()
            return original(job, permit)
        with patch.object(worker.WorkerJob, '_apply', cancel_then_dispatch): result = self.job().run(receipt)
        self.assertEqual(result['status'], 'outcome_unknown')
        self.assertTrue(result['cancellation_requested'])
        self.assertEqual(result['outcome']['failure_code'], 'worker_cancellation_requested')
        self.assertEqual(self.state(), before)

    def test_local_forged_completion_file_cannot_establish_success(self):
        self.prepare()
        write_json(self.job_root / 'outcome.json', {'status': 'verified_local', 'mutation_attempts': 1})
        status = self.job().status()
        self.assertEqual(status['status'], 'prepared')
        self.assertIsNone(status['outcome'])
        self.assertEqual(status['mutation_attempts'], 0)

    def test_live_claims_and_unadmitted_context_are_rejected(self):
        for key, value in [('cloud', 'public'), ('evidence_class', 'authenticated_service')]:
            context = copy.deepcopy(self.context); context[key] = value
            with self.assertRaises(AppError): worker.prepare_job(self.job_root, executor_root=self.executor.root,
                context=context, policy_path=self.policy_path)
        context = copy.deepcopy(self.context); context['run_attempt'] = 2
        with self.assertRaises(AppError): worker.prepare_job(self.job_root, executor_root=self.executor.root,
            context=context, policy_path=self.policy_path)
        self.assertFalse(self.job_root.exists())

    def test_cross_stack_overlapping_ownership_is_reserved_independently_of_backend(self):
        other = protected.create_synthetic_executor(self.root / 'other-executor', initial_value=0, desired_value=1, engine_version='1.10.0')
        context = copy.deepcopy(self.context); context['run_id'] = 'another-run'; context['stack'] = 'other-stack'
        context['ownership'].append('another-policy')
        self.policy['executors'].append({'root': str(other.root), 'manifest_sha256': digest(other.manifest),
            'context_sha256': digest(context), 'profile': other.mode})
        write_json(self.policy_path, self.policy)
        self.prepare()
        with self.assertRaises(AppError): worker.prepare_job(self.jobs / 'other-job', executor_root=other.root,
            context=context, policy_path=self.policy_path)
        self.assertEqual(load_json(other.root / 'work/state/terraform.tfstate')['serial'], 0)
        self.assertEqual(self.job().status()['status'], 'prepared')

    def test_policy_inside_repository_or_job_tree_is_rejected(self):
        (self.host / '.git').mkdir()
        with self.assertRaises(AppError): worker.WorkerPolicy(self.policy_path)

    def test_changed_source_remains_inspectable_and_cancellable_without_dispatch(self):
        self.prepare(); before = self.state()
        (self.source / 'policy.json').write_text('{"setting":"changed-after-review"}')
        result = self.job().status()
        self.assertEqual(result['execution_validation']['status'], 'invalidated')
        self.assertEqual(result['execution_validation']['failure_code'], 'worker_source_changed')
        self.assertEqual(result['mutation_attempts'], 0)
        self.assertEqual(self.job().cancel()['status'], 'cancelled_before_dispatch')
        self.assertEqual(self.state(), before)

    def test_consumed_approval_without_worker_dispatch_is_reported_explicitly(self):
        self.prepare(); job = self.job(); before = self.state()
        guard = aa.make_laboratory_guard(job.request, lambda: job.check(active=True))
        with job.policy.authority.authorize(job.request, self.receipt(), guard=guard): pass
        result = self.job().status()
        self.assertEqual(result['status'], 'approval_consumed_dispatch_not_recorded')
        self.assertTrue(result['approval_consumed'])
        self.assertEqual(result['mutation_attempts'], 0)
        with self.assertRaises(AppError): self.job().run(self.receipt())
        self.assertEqual(self.state(), before)

    def test_unfinished_durable_dispatch_is_never_reported_as_proven_running(self):
        self.prepare(); job = self.job()
        with job.policy.connection() as db:
            db.execute("UPDATE jobs SET status='dispatched',dispatches=1 WHERE id=?", (job.identifier,))
        status = self.job().status()
        self.assertEqual(status['status'], 'dispatch_outcome_pending_or_unknown')
        self.assertFalse(status['retry_authorized'])
        with self.assertRaises(AppError): self.job().run(self.receipt())

    def test_detached_status_read_is_inert_and_complete_receipt_preserves_scope(self):
        self.prepare()
        for _ in range(3):
            status = self.job().status()
            self.assertEqual(status['status'], 'prepared')
            self.assertEqual(status['mutation_attempts'], 0)
            self.assertFalse(status['reopening_dispatches'])
        result = self.job().run(self.receipt())
        self.assertFalse(result['production_authorized'])
        self.assertEqual(result['profile'], 'synthetic_local_process_only')
        self.assertEqual(self.job().cancel()['status'], 'verified_local')


if __name__ == '__main__': unittest.main()
