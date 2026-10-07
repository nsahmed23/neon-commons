"""Real independent signatures and Docker/Unix/TLS effects; no service live claim."""
import base64
import copy
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import time
import sys
import threading
from unittest.mock import patch
import unittest
import uuid

from intune_iac import worker_service as service, worker_host as host, worker_broker as broker
from intune_iac.io import AppError, canonical, digest, load_json, write_json
from plugin_tests.signing_fixture import verifier_pin
from plugin_tests import test_worker_broker_r4 as broker_tests

from scripts.qualification_tools import PINNED as QUALIFICATION_PINS, reference as qualification_tool

PROJECT = Path(__file__).resolve().parents[1]
DOCKER = qualification_tool('docker')
RELAY = qualification_tool('relay_v3')


class WorkerServiceR4Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        broker_tests.BrokerTests.setUpClass()
        cls.build = tempfile.TemporaryDirectory(prefix='iw-service-build-')
        cls.probe = Path(cls.build.name) / 'tls-probe'
        subprocess.run(['/usr/bin/gcc', '-O2', '-static', '-o', str(cls.probe),
            str(PROJECT / 'plugin_tests/fixtures/worker_service_tls_client.c'), '-lssl', '-lcrypto', '-lz', '-lzstd', '-ldl', '-pthread'],
            check=True, capture_output=True)
    @classmethod
    def tearDownClass(cls):
        cls.build.cleanup(); broker_tests.BrokerTests.tearDownClass()
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='iw-service-'); self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        retain = os.environ.get('INTUNE_WORKER_SERVICE_TEST_EVIDENCE')
        if retain:
            def preserve():
                nodes = []
                def ignore(path, names):
                    skipped = []
                    for name in names:
                        p = Path(path) / name
                        if p.is_socket(): nodes.append(str(p.relative_to(self.root))); skipped.append(name)
                    return skipped
                target = Path(retain) / self._testMethodName
                shutil.copytree(self.root, target, symlinks=True, ignore=ignore)
                (target / 'RUNTIME-IPC-NODES.json').write_text(json.dumps({'closed_socket_nodes': nodes, 'original_root': str(self.root)}, indent=2) + '\n')
            self.addCleanup(preserve)
        self.fixture = broker_tests.BrokerTests('test_real_unix_connect_tls_exact_put_and_readback'); self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        for name in ('source', 'control', 'job', 'broker', 'trust', 'jobs'):
            (self.root / name).mkdir(mode=0o700)
        shutil.copyfile(self.probe, self.root / 'source/tls-probe'); (self.root / 'source/tls-probe').chmod(0o500)
        shutil.copyfile(self.fixture.cert, self.root / 'control/broker-ca.pem'); (self.root / 'control/broker-ca.pem').chmod(0o600)
        (self.root / 'control/worker.sh').write_text('''set -eu
/tools/relay &
relay_pid=$!
trap 'kill "$relay_pid" 2>/dev/null || true' EXIT
n=0
while [ ! -f /job/relay.ready ]; do
  n=$((n + 1)); [ "$n" -lt 100 ] || exit 98
  sleep 0.02
done
/source/tls-probe
''')
        self.spec = host.HostSpec(str(DOCKER), str(self.root / 'source'),
            host.directory_binding(self.root / 'source')['sha256'], str(self.root / 'control'),
            host.directory_binding(self.root / 'control')['sha256'], str(self.root / 'job'),
            tools=(host.PinnedTool('relay', str(RELAY), QUALIFICATION_PINS['relay_v3']['sha256']),),
            broker_root=str(self.root / 'broker'), broker_ca_sha256=hashlib.sha256(self.fixture.cert.read_bytes()).hexdigest())
        self.active = True
        def check():
            if not self.active: raise AppError('fixture_revoked', 'Laboratory controller precondition failed.')
        self.check = check
        self.run = service.trusted_run_binding({'schema_version': 'service-host-qualification-context/1', 'fixture_run': 'literal-local-container', 'ci_authenticated': False}, recheck=check)
        self.storage = service.trusted_storage_binding({'profile': 'laboratory_private_plaintext', 'production_encryption': False}, recheck=check)
        self.identifier = str(uuid.uuid4())
        self.broker_policy = copy.deepcopy(self.fixture.policy)
        self.broker_policy.update(operation_id=self.identifier, expires_at=int(time.time()) + 300)
        self.manifest = service.make_manifest(operation_id=self.identifier, profile='native_docker_laboratory_tls',
            expires_at=self.broker_policy['expires_at'], execution_binding_sha256=self.broker_policy['execution_binding_sha256'],
            host_spec=self.spec, broker_policy=self.broker_policy, run_binding_sha256=self.run.sha256, run_context=self.run.facts,
            storage_binding_sha256=self.storage.sha256, tenant_id=self.fixture.tenant,
            object_ids=['00000000-0000-0000-0000-000000000099'], backend_scope_sha256='e' * 64,
            provider_binding={'evidence_class': 'literal_local_tls_fixture'}, action='host_qualification')
        self.key = self.root / 'trust/synthetic-signer.pem'
        subprocess.run(['/usr/bin/openssl', 'genpkey', '-algorithm', 'ED25519', '-out', str(self.key)], check=True, capture_output=True)
        public = subprocess.run(['/usr/bin/openssl', 'pkey', '-in', str(self.key), '-pubout', '-outform', 'DER'], check=True, capture_output=True).stdout[-32:]
        pin = verifier_pin(Path('/usr/bin/openssl'), hashlib.sha256(Path('/usr/bin/openssl').read_bytes()).hexdigest())
        self.policy = {'schema_version': 'worker-service-policy/1', 'authority_root': str(self.root / 'trust/authority'),
            'jobs_root': str(self.root / 'jobs'), 'verifier': {k: str(v) if isinstance(v, Path) else v for k, v in asdict(pin).items()},
            'approvers': [{'issuer': 'fixture', 'key_id': 'key', 'approver_id': 'independent-lab-reviewer',
                'public_key_hex': public.hex(), 'profiles': ['native_docker_laboratory_tls']}],
            'admitted_manifest_sha256': [digest(self.manifest)]}
        self.policy_path = self.root / 'trust/policy.json'; write_json(self.policy_path, self.policy)
        self.job_root = self.root / 'jobs/run'
    def prepare(self): return service.prepare_job(self.job_root, manifest=self.manifest, policy_path=self.policy_path)
    def job(self): return service.ServiceJob(self.job_root, self.policy_path)
    def runtime(self):
        return service.laboratory_runtime(run=self.run, storage=self.storage, upstream=self.fixture.upstream,
            certificate=self.fixture.cert, private_key=self.fixture.key, prewrite=self.check)
    def receipt(self, **changes):
        payload = {'schema_version': 'signed-worker-service-approval/1', 'issuer': 'fixture', 'key_id': 'key',
            'approver_id': 'independent-lab-reviewer', 'operation_id': self.identifier, 'manifest_sha256': digest(self.manifest),
            'issued_at': int(time.time()), 'expires_at': self.manifest['expires_at'], 'nonce': uuid.uuid4().hex}
        payload.update(changes)
        message = self.root / 'trust/message'; message.write_bytes(service.SIGNATURE_DOMAIN + canonical(payload))
        signature = self.root / 'trust/signature'
        subprocess.run(['/usr/bin/openssl', 'pkeyutl', '-sign', '-rawin', '-inkey', str(self.key), '-in', str(message), '-out', str(signature)], check=True, capture_output=True)
        return {'payload': payload, 'signature': base64.b64encode(signature.read_bytes()).decode()}
    def test_actual_signed_native_container_tls_mutation_and_literal_readback(self):
        self.prepare(); approved = self.receipt(); result = self.job().run(approved, runtime=self.runtime())
        self.assertEqual(result['status'], 'host_completed_service_unverified', result)
        self.assertEqual(result['dispatches'], 1)
        self.assertEqual([(r[0], r[1]) for r in self.fixture.calls], [
            ('POST', '/00000000-0000-0000-0000-000000000001/oauth2/v2.0/token'),
            ('PUT', '/beta/deviceManagement/configurationPolicies/id'), ('GET', '/beta/deviceManagement/configurationPolicies/id')])
        self.assertEqual(self.fixture.calls[1][3], b'{"name":"exact approved correction"}')
        self.assertIn(b'{"accepted":true}', (self.root / 'job/literal-readback.txt').read_bytes())
        self.assertTrue(result['outcome']['host']['cleanup']['removed'])
        self.assertFalse(result['production_authorized'])
        self.assertEqual(self.job().attach()['dispatches'], 1)
        with self.assertRaises(AppError): self.job().run(approved, runtime=self.runtime())
        self.assertEqual(len(self.fixture.calls), 3)
    def test_forged_boolean_cannot_authorize_or_reconstruct_runtime(self):
        self.prepare()
        with self.assertRaises(AppError): self.job().run({'approved': True}, runtime=self.runtime())
        with self.assertRaises(AppError): self.job().run(self.receipt(), runtime={'authenticated': True})
        self.assertEqual(self.job().status()['dispatches'], 0); self.assertEqual(self.fixture.calls, [])
    def test_wrong_signer_and_expired_receipt_leave_plan_undispatched(self):
        self.prepare()
        for receipt in (self.receipt(approver_id='intruder'), self.receipt(expires_at=int(time.time()) - 1)):
            with self.assertRaises(AppError): self.job().run(receipt, runtime=self.runtime())
        self.assertEqual(self.job().status()['dispatches'], 0)
    def test_changed_control_and_policy_are_rejected_before_dispatch(self):
        self.prepare(); (self.root / 'control/worker.sh').write_text('echo substituted\n')
        with self.assertRaises(AppError): self.job().run(self.receipt(), runtime=self.runtime())
        self.assertEqual(self.job().status()['dispatches'], 0)
        self.policy['admitted_manifest_sha256'] = ['0' * 64]; write_json(self.policy_path, self.policy)
        self.assertFalse(self.job().status()['policy_matches_reviewed'])
        with self.assertRaises(AppError): self.job().run(self.receipt(), runtime=self.runtime())
    def test_cancel_before_dispatch_and_restart_cannot_start(self):
        self.prepare(); self.job().cancel()
        with self.assertRaises(AppError): self.job().run(self.receipt(), runtime=self.runtime())
        self.assertEqual(self.job().attach()['status'], 'cancelled_before_dispatch')
        self.assertEqual(self.fixture.calls, [])
    def test_controller_precondition_and_storage_capability_fail_closed(self):
        self.prepare(); self.active = False
        with self.assertRaises(AppError): self.job().run(self.receipt(), runtime=self.runtime())
        with self.assertRaises(AppError): service.laboratory_runtime(run=self.run, storage={'encrypted': True}, upstream=self.fixture.upstream,
            certificate=self.fixture.cert, private_key=self.fixture.key, prewrite=lambda: None)
        self.assertEqual(self.job().status()['dispatches'], 0)
    def test_legacy_signature_domain_is_not_accepted(self):
        from intune_iac import approval_authority as old
        self.prepare(); signed = self.receipt()
        (self.root / 'trust/message').write_bytes(old.SIGNATURE_DOMAIN + canonical(signed['payload']))
        subprocess.run(['/usr/bin/openssl', 'pkeyutl', '-sign', '-rawin', '-inkey', str(self.key),
            '-in', str(self.root / 'trust/message'), '-out', str(self.root / 'trust/signature')], check=True, capture_output=True)
        signed['signature'] = base64.b64encode((self.root / 'trust/signature').read_bytes()).decode()
        with self.assertRaises(AppError): self.job().run(signed, runtime=self.runtime())
        self.assertEqual(self.job().status()['dispatches'], 0)
    def test_lab_identity_and_serialized_live_claim_cannot_enable_live_runtime(self):
        with self.assertRaises(AppError): service.live_runtime(binding={'live': True}, lease={'held': True})
        value = copy.deepcopy(self.manifest); value['profile'] = 'azure_public_pilot'
        with self.assertRaises(AppError): service.validate_manifest(value)
    def test_broker_policy_or_plan_binding_substitution_cannot_be_approved(self):
        self.prepare()
        self.job().manifest['broker_policy']['routes'][1]['body_sha256'] = '0' * 64
        signed = self.receipt(manifest_sha256='0' * 64)
        with self.assertRaises(AppError): self.job().run(signed, runtime=self.runtime())
        self.assertEqual(self.job().status()['dispatches'], 0)
    def test_cross_stack_same_object_scope_reservation_conflicts(self):
        self.prepare()
        other = copy.deepcopy(self.manifest); other['operation_id'] = str(uuid.uuid4()); other['broker_policy']['operation_id'] = other['operation_id']
        self.policy['admitted_manifest_sha256'].append(digest(other)); write_json(self.policy_path, self.policy)
        with self.assertRaises(AppError): service.prepare_job(self.root / 'jobs/other', manifest=other, policy_path=self.policy_path)
        with sqlite3.connect(self.root / 'trust/authority/service.sqlite3') as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM ownership').fetchone()[0], 2)
    def test_recovery_after_consumption_never_replays_external_write(self):
        self.prepare()
        with self.job().policy.connection() as db:
            db.execute("UPDATE jobs SET dispatches=1,status='running' WHERE id=?", (self.identifier,))
        recovered = self.job().recover()
        self.assertEqual(recovered['status'], 'outcome_unknown'); self.assertEqual(recovered['dispatches'], 1)
        with self.assertRaises(AppError): self.job().run(self.receipt(), runtime=self.runtime())
        self.assertEqual(self.fixture.calls, [])


    def test_actual_cli_preparation_status_attach_and_wrong_tenant_cancel(self):
        manifest_path = self.root / 'trust/manifest.json'; write_json(manifest_path, self.manifest)
        def cli(action, *extra):
            result = subprocess.run([sys.executable, '-B', str(PROJECT / 'scripts/intune-iac.py'), 'service', action,
                '--job-root', str(self.job_root), '--policy', str(self.policy_path), *extra],
                cwd=PROJECT, capture_output=True, timeout=15)
            (self.root / ('cli-' + action + '.stdout')).write_bytes(result.stdout)
            (self.root / ('cli-' + action + '.stderr')).write_bytes(result.stderr)
            return result
        created = cli('prepare', '--manifest', str(manifest_path))
        self.assertEqual(created.returncode, 0, created.stderr)
        for action in ('review', 'status', 'attach'):
            response = cli(action); self.assertEqual(response.returncode, 0, response.stderr)
            if action != 'review':
                observed = json.loads(response.stdout)
                self.assertEqual(observed['implementation_comparison_scope'],
                    'current_observer_process_against_reviewed_controller')
                self.assertFalse(observed['approved_controller_runtime_re_attested'])
        from intune_iac import service_cli
        with self.assertRaises(AppError): service_cli.invoke('cancel', self.job_root, self.policy_path,
            tenant_id='00000000-0000-0000-0000-000000000088')
        self.assertFalse(self.job().status()['cancel_requested'])
        self.assertEqual(self.job().status()['dispatches'], 0)

    def test_implementation_upgrade_preserves_inspection_and_cleanup_but_blocks_run(self):
        self.prepare()
        changed = service.implementation_binding(); changed['worker_service.py'] = '0' * 64
        with patch.object(service, 'implementation_binding', return_value=changed):
            for action in ('status', 'attach', 'cancel', 'recover'):
                self.assertFalse(getattr(self.job(), action)()['implementation_matches_reviewed'])
            with self.assertRaises(AppError): self.job().run(self.receipt(), runtime=self.runtime())
        self.assertEqual(self.fixture.calls, [])

    def test_zero_dispatch_cancel_releases_object_for_new_signed_operation(self):
        other = copy.deepcopy(self.manifest); other['operation_id'] = str(uuid.uuid4()); other['broker_policy']['operation_id'] = other['operation_id']
        self.policy['admitted_manifest_sha256'].append(digest(other)); write_json(self.policy_path, self.policy)
        self.prepare(); self.job().cancel()
        result = service.prepare_job(self.root / 'jobs/second', manifest=other, policy_path=self.policy_path)
        self.assertEqual(result['status'], 'prepared')
        with sqlite3.connect(self.root / 'trust/authority/service.sqlite3') as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0], 2)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM ownership').fetchone()[0], 2)

    def test_private_tls_key_inside_worker_source_fails_before_dispatch(self):
        copied = self.root / 'source/forbidden-key.pem'; shutil.copyfile(self.fixture.key, copied); copied.chmod(0o600)
        self.prepare(); runtime = self.runtime(); runtime.private_key = copied
        with self.assertRaises(AppError) as caught: self.job().run(self.receipt(), runtime=runtime)
        self.assertEqual(caught.exception.code, 'service_private_key_worker_visible')
        self.assertEqual(self.job().status()['dispatches'], 0)

    def test_in_memory_manifest_change_cannot_retarget_registered_job(self):
        self.prepare(); job = self.job(); job.manifest['object_ids'] = ['00000000-0000-0000-0000-000000000088']
        with self.assertRaises(AppError): job.status()
        self.assertEqual(self.job().status()['dispatches'], 0)

    def test_actual_running_container_cancelled_from_separate_cli_process(self):
        from dataclasses import replace
        (self.root / 'control/worker.sh').write_text('touch /job/waiting\nwhile :; do sleep 0.1; done\n')
        self.spec = replace(self.spec, control_sha256=host.directory_binding(self.root / 'control')['sha256'])
        self.manifest['host_spec'] = asdict(self.spec)
        self.policy['admitted_manifest_sha256'] = [digest(self.manifest)]; write_json(self.policy_path, self.policy)
        self.prepare(); cancellation = []
        def cancel():
            deadline = time.monotonic() + 10
            while not (self.root / 'job/waiting').exists() and time.monotonic() < deadline: time.sleep(0.02)
            cancellation.append(subprocess.run([sys.executable, '-B', str(PROJECT / 'scripts/intune-iac.py'), 'service', 'cancel',
                '--job-root', str(self.job_root), '--policy', str(self.policy_path)], cwd=PROJECT,
                capture_output=True, timeout=15))
        thread = threading.Thread(target=cancel); thread.start()
        result = self.job().run(self.receipt(), runtime=self.runtime()); thread.join(timeout=20)
        self.assertEqual(cancellation[0].returncode, 0, cancellation[0].stderr)
        self.assertEqual(result['status'], 'outcome_unknown')
        self.assertEqual(result['dispatches'], 1); self.assertTrue(result['cancel_requested'])
        self.assertEqual(result['outcome']['watchdog_error'], 'service_permit_inactive')
        self.assertTrue(result['outcome']['host']['cleanup']['removed'])
        self.assertEqual(self.fixture.calls, [])


    def test_active_recover_cancels_but_refuses_competing_controller_cleanup(self):
        from dataclasses import replace
        (self.root / 'control/worker.sh').write_text('touch /job/waiting\nwhile :; do sleep 0.1; done\n')
        self.spec = replace(self.spec, control_sha256=host.directory_binding(self.root / 'control')['sha256'])
        self.manifest['host_spec'] = asdict(self.spec)
        self.policy['admitted_manifest_sha256'] = [digest(self.manifest)]; write_json(self.policy_path, self.policy)
        self.prepare(); cancellation = []
        def cancel():
            deadline = time.monotonic() + 10
            while not (self.root / 'job/waiting').exists() and time.monotonic() < deadline: time.sleep(0.02)
            cancellation.append(subprocess.run([sys.executable, '-B', str(PROJECT / 'scripts/intune-iac.py'), 'service', 'recover',
                '--job-root', str(self.job_root), '--policy', str(self.policy_path)], cwd=PROJECT,
                capture_output=True, timeout=15))
        thread = threading.Thread(target=cancel); thread.start()
        result = self.job().run(self.receipt(), runtime=self.runtime()); thread.join(timeout=20)
        self.assertEqual(cancellation[0].returncode, 3, cancellation[0].stderr)
        self.assertIn(b'service_cleanup_owner_active', cancellation[0].stderr)
        self.assertEqual(result['status'], 'outcome_unknown')
        self.assertEqual(result['dispatches'], 1); self.assertTrue(result['cancel_requested'])
        self.assertEqual(result['outcome']['watchdog_error'], 'service_permit_inactive')
        self.assertTrue(result['outcome']['host']['cleanup']['removed'])
        self.assertEqual(self.fixture.calls, [])


    def test_receipt_archive_failure_preserves_known_outcome_and_cannot_replay(self):
        self.prepare(); (self.job_root / 'service-receipt.json').write_bytes(b'EXISTING-EVIDENCE-MUST-NOT-BE-REPLACED')
        result = self.job().run(self.receipt(), runtime=self.runtime())
        self.assertEqual(result['status'], 'host_completed_service_unverified')
        self.assertTrue(result['outcome']['host']['cleanup']['removed'])
        self.assertEqual(result['events'][-1]['kind'], 'receipt_archive_failed')
        self.assertEqual((self.job_root / 'service-receipt.json').read_bytes(), b'EXISTING-EVIDENCE-MUST-NOT-BE-REPLACED')
        with self.assertRaises(AppError): self.job().run(self.receipt(), runtime=self.runtime())
        self.assertEqual(len(self.fixture.calls), 3)


if __name__ == '__main__': unittest.main()
