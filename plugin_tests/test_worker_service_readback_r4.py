"""Actual TLS backend reads + sealed Graph parity; no native Azure/Graph claim."""
import copy
from dataclasses import asdict
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import pickle
import shutil
import sqlite3
import ssl
import threading
import time
import unittest
from unittest.mock import patch

from intune_iac import identity_binding as ib, worker_service as service, worker_service_readback as readback
from intune_iac import worker_broker as broker, azure_backend
from intune_iac.io import AppError, canonical, digest, write_json
from plugin_tests import test_identity_binding_v5 as identities
from plugin_tests import test_worker_state_r4 as states
from plugin_tests import test_worker_service_r4 as services


class ServiceReadbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): services.WorkerServiceR4Tests.setUpClass()
    @classmethod
    def tearDownClass(cls): services.WorkerServiceR4Tests.tearDownClass()
    def setUp(self):
        self.fixture = services.WorkerServiceR4Tests('test_cancel_before_dispatch_and_restart_cannot_start')
        # The outer case retains this entire fixture under its own unique name.
        # Avoid colliding with the same helper's standalone service-test case.
        with patch.dict(os.environ):
            os.environ.pop('INTUNE_WORKER_SERVICE_TEST_EVIDENCE', None)
            self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups); self.root = self.fixture.root
        self.graph = states.WorkerStateTests('test_complete_matches_independent_reader_fields_and_preserves_native_metadata')
        self.graph.setUp(); self.addCleanup(self.graph.doCleanups)
        self.contract, self.gate, _, kwargs, before, plan = self.graph.contract()
        self.completion, self.candidate = self.graph.complete(self.gate, kwargs, before, plan)
        tenant = self.gate.binding()['tenant_id']; oid = self.gate.binding()['object_id']
        self.transport = identities.RecordedServices()
        raw = canonical(before); headers = {'etag': '"baseline"', 'content-length': str(len(raw)), 'x-ms-blob-type': 'BlockBlob'}
        self.transport.responses[5][2]['tenantId'] = tenant
        self.transport.responses[8:] = [(200, headers, b''), (200, headers, raw), (200, headers, b'')]
        self.provider_credential = ib.ClientSecretHandle('SYNTHETIC-PROVIDER-READBACK')
        self.backend_credential = ib.ClientSecretHandle('SYNTHETIC-BACKEND-READBACK')
        self.addCleanup(self.provider_credential.close); self.addCleanup(self.backend_credential.close)
        configuration = ib.BindingConfig(ib.IdentitySpec(tenant, identities.CLIENT, identities.OBJECT),
            ib.IdentitySpec(tenant, identities.BACK_CLIENT, identities.BACK_OBJECT),
            ib.BackendSpec(identities.SUBSCRIPTION, identities.RESOURCE, 'https://recordedstate.blob.core.windows.net',
                'tfstate', 'intune.tfstate', 'default', before['lineage'], before['serial'], hashlib.sha256(raw).hexdigest()))
        self.binding = ib.bind_laboratory(configuration, provider_credential=self.provider_credential,
            backend_credential=self.backend_credential, transport=self.transport, max_age=120)
        self.backend_binding = azure_backend.AzureBackendAdapter(azure_backend.AzureBackendSpec(
            configuration.backend_identity, configuration.backend, 'coordination.lock')).binding()
        self.state_raw, self.response_status, self.lease_status = canonical(self.candidate), 200, 'unlocked'
        self.requests = []; outer = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                outer.requests.append({'path': self.path, 'host': self.headers.get('Host'),
                    'authorization_present': self.headers.get('Authorization', '').startswith('Bearer '),
                    'api_version': self.headers.get('x-ms-version')})
                self.send_response(outer.response_status)
                self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(outer.state_raw)))
                self.send_header('ETag', '"independent-after"'); self.send_header('x-ms-lease-status', outer.lease_status)
                self.end_headers(); self.wfile.write(outer.state_raw)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); context.load_cert_chain(self.fixture.fixture.cert, self.fixture.fixture.key)
        self.server.socket = context.wrap_socket(self.server.socket, server_side=True)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True); thread.start()
        self.addCleanup(self.server.server_close); self.addCleanup(self.server.shutdown)
        self.upstream = broker.LaboratoryUpstream(self.server.server_port, self.fixture.fixture.cert)
        backend_sha = digest(self.backend_binding)
        provider = {'object_id': oid, 'provider_identity': asdict(configuration.provider), 'backend': self.backend_binding,
            'source_revision': '1' * 40, 'source_sha256': '2' * 64, 'effective_input_sha256': '3' * 64, 'lockfile_sha256': '4' * 64}
        facts = {'schema_version': 'service-run-context/1', 'repository': 'https://github.com/fixture/fixture',
            'source_revision': '1' * 40, 'source_sha256': '2' * 64, 'workflow_revision': '5' * 40, 'verifier_revision': '6' * 40,
            'run_id': 'literal-readback', 'run_attempt': 1, 'protected_ref': 'refs/heads/pilot',
            'effective_inputs_sha256': '3' * 64, 'provider_lock_sha256': '4' * 64, 'stack': 'worker', 'component': 'intune-policy'}
        self.run = service.trusted_run_binding(facts, recheck=lambda: None)
        policy = {'schema_version': 'protected-egress-policy/1.0', 'profile': 'laboratory_native_protocol',
            'operation_id': self.fixture.identifier, 'execution_binding_sha256': 'a' * 64,
            'expires_at': int(time.time()) + 300, 'worker_uid': os.geteuid(),
            'identities': {'backend': {'tenant_id': tenant, 'client_id': identities.BACK_CLIENT}},
            'native_lock': {'host': 'recordedstate.blob.core.windows.net', 'path': '/tfstate/intune.tfstate'},
            'routes': [{'id': 'state', 'host': 'recordedstate.blob.core.windows.net', 'method': 'PUT',
                'path': '/tfstate/intune.tfstate', 'query': {}, 'headers': {'x-ms-blob-type': 'BlockBlob', 'content-type': 'application/json'},
                'dynamic_headers': {'x-ms-lease-id': 'active_native_lease'}, 'body_sha256': self.contract.binding()['admission_template_sha256'],
                'state_contract_sha256': digest(self.contract.binding()), 'role': 'backend', 'audience': 'storage',
                'effect': 'state_write', 'max_attempts': 1}]}
        self.manifest = service.make_manifest(operation_id=self.fixture.identifier, profile='native_docker_laboratory_protocol',
            expires_at=policy['expires_at'], execution_binding_sha256='a' * 64, host_spec=self.fixture.spec,
            broker_policy=policy, run_binding_sha256=self.run.sha256, run_context=facts,
            storage_binding_sha256=self.fixture.storage.sha256, tenant_id=tenant, object_ids=[oid], backend_scope_sha256=backend_sha,
            provider_binding=provider, saved_plan_sha256='b' * 64, identity_binding_sha256=self.binding.evidence()['binding_sha256'],
            state_contracts={'state': self.contract.binding()}, precondition_binding=self.gate.binding())
        self.fixture.manifest = self.manifest
        self.fixture.policy['admitted_manifest_sha256'] = [digest(self.manifest)]
        self.fixture.policy['approvers'][0]['profiles'] = ['native_docker_laboratory_protocol']
        write_json(self.fixture.policy_path, self.fixture.policy)
        retained = os.environ.get('INTUNE_SERVICE_READBACK_TEST_EVIDENCE')
        if retained:
            def preserve():
                target = Path(retained) / self._testMethodName
                shutil.copytree(self.root, target, symlinks=True, ignore=lambda p, n: [x for x in n if (Path(p) / x).is_socket()])
                shutil.copytree(self.graph.root, target / 'graph-evidence', symlinks=True)
                (target / 'backend-requests.json').write_text(json.dumps(self.requests, indent=2) + '\n')
            self.addCleanup(preserve)
    def collect(self, name='post-readback', **changes):
        values = {'binding': self.binding, 'backend_credential': self.backend_credential, 'completion': self.completion,
            'state_contract': self.contract, 'storage': self.fixture.storage, 'upstream': self.upstream, 'output': self.root / name}
        values.update(changes)
        return readback.collect_laboratory(self.manifest, **values)
    def consumed_interruption(self):
        self.fixture.prepare(); job = self.fixture.job(); signed = self.fixture.receipt()
        payload = job.policy.verify(self.manifest, signed)
        # Explicit interrupted-after-consumption fixture, not an execution claim.
        with job.policy.connection() as db:
            db.execute('INSERT INTO consumed VALUES (?,?,?,?)', (payload['issuer'], payload['nonce'], job.identifier, job.sha256))
            db.execute("UPDATE jobs SET status='outcome_unknown',dispatches=1 WHERE id=?", (job.identifier,))
        return job
    def test_actual_tls_state_and_sealed_graph_completion_release_only_converged_scope(self):
        job = self.consumed_interruption(); capability = self.collect(); facts = capability.verified(self.manifest)
        self.assertIs(type(capability), readback.LaboratoryServiceReadback)
        self.assertEqual(facts['backend_state']['serial'], 3)
        self.assertEqual(self.requests, [{'path': '/tfstate/intune.tfstate', 'host': 'recordedstate.blob.core.windows.net',
            'authorization_present': True, 'api_version': '2023-11-03'}])
        result = job.reconcile(capability)
        self.assertEqual(result['status'], 'service_state_converged_execution_unknown')
        self.assertEqual(result['outcome']['endpoint_effectiveness'], 'unestablished')
        self.assertFalse(result['outcome']['production_approved'])
        with sqlite3.connect(job.policy.database) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM ownership').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM consumed').fetchone()[0], 1)
        self.assertEqual(job.attach()['dispatches'], 1)
    def test_denied_or_still_locked_backend_keeps_reservation_and_raw_negative(self):
        job = self.consumed_interruption(); self.response_status = 403
        with self.assertRaises(AppError): self.collect('denied')
        self.assertEqual((self.root / 'denied/observed-state.raw').read_bytes(), self.state_raw)
        self.response_status = 200; self.lease_status = 'locked'
        with self.assertRaises(AppError): self.collect('locked')
        with sqlite3.connect(job.policy.database) as db: self.assertEqual(db.execute('SELECT COUNT(*) FROM ownership').fetchone()[0], 2)
    def test_unapproved_state_change_or_imported_json_cannot_release(self):
        job = self.consumed_interruption(); changed = copy.deepcopy(self.candidate); changed['serial'] = 100
        self.state_raw = canonical(changed)
        with self.assertRaises(AppError): self.collect()
        with self.assertRaises(AppError): job.reconcile({'complete': True, 'state': self.candidate})
        self.assertEqual(job.status()['status'], 'outcome_unknown')
    def test_raw_capture_or_boolean_cannot_replace_sealed_desired_completion(self):
        for fake in (self.completion.verified(), self.completion.verified()['capture'], {'verified': True}):
            with self.assertRaises(AppError): self.collect(completion=fake)
        self.assertEqual(self.requests, [])
    def test_lab_capability_cannot_enter_native_factory_or_serialize(self):
        with self.assertRaises(AppError): readback.collect_live(self.manifest, binding=self.binding,
            backend_credential=self.backend_credential, completion=self.completion, state_contract=self.contract,
            storage=self.fixture.storage, output=self.root / 'forbidden')
        capability = self.collect()
        with self.assertRaises(TypeError): pickle.dumps(capability)
    def test_postreadback_artifact_tampering_invalidates_capability(self):
        job = self.consumed_interruption(); capability = self.collect()
        (self.root / 'post-readback/observed-state.raw').write_bytes(b'{}')
        with self.assertRaises(AppError): job.reconcile(capability)
        self.assertEqual(job.status()['status'], 'outcome_unknown')
    def test_backend_target_or_signed_operation_substitution_fails_before_get(self):
        original = self.manifest['backend_scope_sha256']; self.manifest['backend_scope_sha256'] = '0' * 64
        with self.assertRaises(AppError): self.collect()
        self.manifest['backend_scope_sha256'] = original
        self.manifest['execution_binding_sha256'] = '0' * 64
        with self.assertRaises(AppError): self.collect()
        self.assertEqual(self.requests, [])

    def test_reviewed_run_attempt_ref_source_and_stack_cannot_be_substituted(self):
        for key, changed in [('run_attempt', 2), ('protected_ref', 'refs/heads/unreviewed'),
                             ('source_revision', '9' * 40), ('component', 'unreviewed-component')]:
            altered = copy.deepcopy(self.manifest); altered['run_context'][key] = changed
            altered['run_binding_sha256'] = digest(altered['run_context'])
            with self.assertRaises(AppError):
                service.prepare_job(self.root / ('jobs/changed-' + key), manifest=altered, policy_path=self.fixture.policy_path)
        self.assertEqual(self.requests, [])



if __name__ == '__main__': unittest.main()
