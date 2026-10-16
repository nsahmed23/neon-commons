"""An approval that was valid at dispatch still passes the in-flight check after its window closes, with real bindings.

The adoption and the recovery-plan permits judge their approval window when a request starts (check_active) and not
when its response comes back (inflight_active): the window bounds when a dispatch may start. The existing permit tests
replace the runtime check with a mock, so they only prove that check_window=False is passed down. Here the runtime is
the real AdoptionRuntime or RecoveryPlanRuntime, built from the real controller bindings: a ControllerBinding for the run
and the storage, a laboratory identity binding with its BrokerCredentials, the NativeAdoptionStateContract with its
Graph reader and captured preimage, the OwnershipAdmission over a real workbench store, and the native provider adapter.
The real EgressBroker then carries the request, with the permit's own check_active and inflight_active as its guard,
and the (loopback) upstream answers after the injected clocks have passed the approval's expiry.

Only the seams that need a live backend or container stay modeled, as in the two modules this one builds on: the job's
own manifest check, the backend observation and the dispatch itself. The runtime check is never replaced here.
Time is the injected clock of the latch tests; nothing sleeps on the host clock.
"""
import hashlib
import os
import sqlite3
import tempfile
import time
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode

from intune_iac import azure_backend as ab
from intune_iac import clock
from intune_iac import identity_binding as ib
from intune_iac import observation_reader as rd
from intune_iac import worker_adoption as adoption
from intune_iac import worker_adoption_reconcile as bridge
from intune_iac import worker_adoption_state as state_module
from intune_iac import worker_broker as wb
from intune_iac import worker_host as host
from intune_iac import worker_provider as wp
from intune_iac import worker_service as service
from intune_iac import workbench_views as views
from intune_iac.azure_backend import StateRevision
from intune_iac.io import AppError, canonical, digest, write_json
from intune_iac.worker_adoption_ownership import admit_ownership
from intune_iac.worker_adoption_provider import NativeAdoptionProviderAdapter
from intune_iac.workbench_store import WorkbenchStore
from plugin_tests import test_adoption_expiry_latch as adoption_latch
from plugin_tests import test_adoption_recovery_expiry_latch as recovery_latch
from plugin_tests import test_identity_binding_v5 as v5
from plugin_tests import test_worker_adoption_state_r4 as state_fixture
from plugin_tests.test_worker_provider_r4 import FIXTURE, LOCK, OBJECT_ID

LIFETIME = adoption_latch.LIFETIME
EXECUTION = 'a' * 64
BLOB_HOST = 'recordedstate.blob.core.windows.net'
STATE_PATH = '/tfstate/intune.tfstate'
TOKEN_HEADERS = {'content-type': 'application/x-www-form-urlencoded; charset=utf-8'}

# The product functions the two fixtures replace in their setUp; this module puts them back.
REAL_ADOPTION_CHECK = adoption.AdoptionRuntime.check
REAL_RECOVERY_CHECK = bridge.RecoveryPlanRuntime.check
REAL_HOST_SPEC = service._host_spec


class StateServices(v5.RecordedServices):
    """The recorded identity services, answering the state blob with this module's baseline state bytes."""
    def __init__(self, raw):
        super().__init__()
        fixed = []
        for status, headers, body in self.responses:
            if body == v5.STATE:
                body = raw
            if 'content-length' in headers:
                headers = dict(headers, **{'content-length': str(len(raw))})
            fixed.append((status, headers, body))
        self.responses = fixed


def private_file(path, raw):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_bytes(raw)
    path.chmod(0o600)


class RealBindings:
    """The real controller bindings; mixed into a latch fixture, built after the fixture's own setUp."""
    sequence = 0

    def build_bindings(self):
        # The Graph capture stamps itself with the real clock while the injected wall reads the start of the fixture.
        # The wall therefore reads five seconds after the fixture start from here on (the dispatches set it explicitly),
        # so neither the capture nor the ownership scan is dated in the future.
        self.clocks.wall = self.start + 5
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.real = Path(temporary.name)
        self.real.chmod(0o700)
        raw = canonical({'version': 4, 'terraform_version': '1.13.1', 'lineage': v5.LINEAGE, 'serial': 12,
                         'outputs': {}, 'resources': []})
        revision = StateRevision.observe(raw, etag='"recorded-etag-1"')
        backend = ib.BackendSpec(v5.SUBSCRIPTION, v5.RESOURCE, 'https://' + BLOB_HOST, 'tfstate', 'intune.tfstate',
                                 'default', revision.lineage, revision.serial, revision.sha256)
        config = ib.BindingConfig(provider=ib.IdentitySpec(v5.TENANT, v5.CLIENT, v5.OBJECT),
                                  backend_identity=ib.IdentitySpec(v5.TENANT, v5.BACK_CLIENT, v5.BACK_OBJECT), backend=backend)
        provider_secret, backend_secret = ib.ClientSecretHandle('synthetic-provider-secret'), ib.ClientSecretHandle('synthetic-backend-secret')
        self.binding = ib.bind_laboratory(config, provider_credential=provider_secret, backend_credential=backend_secret,
                                          transport=StateServices(raw))
        self.credentials = wb.broker_credentials(binding=self.binding, backend_credential=backend_secret,
                                                 execution_binding_sha256=EXECUTION)
        for closable in (provider_secret, backend_secret, self.credentials):
            self.addCleanup(closable.close)
        self.provider = NativeAdoptionProviderAdapter(wp.WorkerProviderAdapter(
            wp.ProviderSpec(config.provider, ab.AzureBackendSpec(config.backend_identity, backend, 'coordination/selected.lock'),
                            OBJECT_ID, '2' * 40, '3' * 64, '4' * 64, FIXTURE), lockfile=LOCK))
        provider_binding = self.provider.binding()
        reader_secret = ib.ClientSecretHandle('SYNTHETIC-READER-ONLY')
        self.addCleanup(reader_secret.close)
        reader = rd.bind_laboratory_reader(rd.ReaderSpec(v5.TENANT, state_fixture.CLIENT, state_fixture.PRINCIPAL, (state_fixture.OID,)),
                                           credential=reader_secret, transport=state_fixture.Transport(state_fixture.GRAPH))
        self.addCleanup(reader.close)
        self.state_contract = state_module.NativeAdoptionStateContract(
            baseline_raw=raw, baseline_revision=revision, backend=backend, reader=reader,
            preimage=reader.capture(state_fixture.OID, self.real / 'preimage'), execution_binding_sha256=EXECUTION,
            source_sha256=provider_binding['source_sha256'], effective_inputs_sha256=provider_binding['effective_input_sha256'],
            locks_sha256=provider_binding['lockfile_sha256'], evidence_root=self.real / 'admission')
        self.ownership = self.admit_ownership(raw, revision.sha256)
        self.run_binding = service.trusted_run_binding({'schema_version': 'service-host-qualification-context/1',
            'fixture_run': 'literal-local-container', 'ci_authenticated': False}, recheck=lambda: None)
        self.storage_binding = service.trusted_storage_binding({'profile': 'laboratory_private_plaintext',
            'production_encryption': False}, recheck=lambda: None)
        self.upstream = object.__new__(wb.LaboratoryUpstream)  # the type is the capability; requests are answered below
        self.certificate, self.private_key = self.real / 'tls' / 'broker-ca.pem', self.real / 'trust' / 'broker-key.pem'
        private_file(self.certificate, b'synthetic broker certificate')
        private_file(self.private_key, b'synthetic broker key')
        self.host_spec = self.materialize_host()
        self.identities = {role: dict(self.credentials.identities[role]) for role in ('provider', 'backend')}
        self.form = urlencode({'client_id': self.identities['provider']['client_id'],
                               'client_secret': self.credentials.placeholders['provider'], 'grant_type': 'client_credentials',
                               'scope': wb._AUDIENCES['graph'] + ' openid offline_access profile'}).encode()
        self.token_path = '/' + self.identities['provider']['tenant_id'] + '/oauth2/v2.0/token'

    def admit_ownership(self, raw, baseline_sha256):
        tenant = '11111111-1111-4111-8111-111111111111'
        store = WorkbenchStore.create(self.real / 'store', tenant)
        (self.real / 'state.json').write_bytes(raw)
        scope = {'repository': 'https://github.com/example/reviewed', 'stack': 'worker', 'component': 'intune-policy',
                 'backend': 'https://' + BLOB_HOST + STATE_PATH}
        write_json(self.real / 'scan.json', {'schema_version': 'workbench-ownership-scan/1', 'tenant_id': tenant,
            'max_age_seconds': 3600, 'sources': [{'scope': scope, 'state_path': str(self.real / 'state.json')}]})
        views.scan_ownership(store, self.real / 'scan.json')
        return admit_ownership(store, object_id=state_fixture.OID, selected_scope=scope, baseline_sha256=baseline_sha256)

    def materialize_host(self):
        """Directories holding exactly the files the provider generates, so a payload check against them can pass."""
        roots = {name: self.real / name for name in ('source', 'control', 'job', 'broker')}
        for name, path in roots.items():
            path.mkdir(mode=0o700)
        for name, raw in self.provider.source_files().items():
            private_file(roots['source'] / name, raw)
        controls = dict(self.provider.control_files('first-plan', credentials=self.credentials),
                        **{'broker-ca.pem': self.certificate.read_bytes()})
        for name, raw in controls.items():
            private_file(roots['control'] / name, raw)
        spec = host.HostSpec('/usr/bin/docker', str(roots['source']), host.directory_binding(roots['source'])['sha256'],
            str(roots['control']), host.directory_binding(roots['control'])['sha256'], str(roots['job']), tools=(),
            broker_root=str(roots['broker']), broker_ca_sha256=hashlib.sha256(self.certificate.read_bytes()).hexdigest(),
            uid=os.geteuid(), gid=os.getegid())
        return dict(asdict(spec), tools=[])

    # Broker policies over the real credentials' identities.
    def token_route(self):
        return {'id': 'token', 'host': 'login.microsoftonline.com', 'method': 'POST', 'path': self.token_path, 'query': {},
                'headers': dict(TOKEN_HEADERS), 'body_sha256': hashlib.sha256(self.form).hexdigest(), 'role': 'provider',
                'audience': 'graph', 'effect': 'oauth', 'max_attempts': 30}

    def egress_policy(self, operation_id, routes, **extra):
        return dict({'schema_version': 'protected-egress-policy/1.0', 'profile': 'laboratory_native_protocol',
            'operation_id': operation_id, 'execution_binding_sha256': EXECUTION, 'expires_at': self.expires,
            'worker_uid': os.geteuid(), 'identities': {role: dict(value) for role, value in self.identities.items()},
            'routes': routes}, **extra)

    def import_policy(self):
        contract = self.state_contract.binding()
        state_route = {'id': 'state', 'host': BLOB_HOST, 'method': 'PUT', 'path': STATE_PATH, 'query': {},
            'headers': {'x-ms-blob-type': 'BlockBlob', 'content-type': 'application/json'},
            'body_sha256': contract['expected_semantic_sha256'], 'role': 'backend', 'audience': 'storage',
            'effect': 'state_write', 'max_attempts': 1, 'state_contract_sha256': digest(contract),
            'dynamic_headers': {'x-ms-lease-id': 'active_native_lease', 'x-ms-meta-terraformlockid': 'native_lock_metadata_adoption'}}
        return self.egress_policy(self.manifest['operation_id'], [self.token_route(), state_route],
                           native_lock={'host': BLOB_HOST, 'path': STATE_PATH})

    def plan_policy(self, operation_id):
        read = {'id': 'read', 'host': 'graph.microsoft.com', 'method': 'GET',
                'path': '/beta/deviceManagement/configurationPolicies/' + state_fixture.OID, 'query': {}, 'headers': {},
                'body_sha256': hashlib.sha256(b'').hexdigest(), 'role': 'provider', 'audience': 'graph',
                'effect': 'readonly', 'max_attempts': 4}
        return self.egress_policy(operation_id, [self.token_route(), read])

    # The real broker around a permit, and a loopback upstream that answers after the approval's expiry.
    def broker(self, permit, policy, **extra):
        RealBindings.sequence += 1
        directory = self.real / ('broker-journal-%d' % RealBindings.sequence)
        directory.mkdir(mode=0o700)
        guard = wb.laboratory_guard(EXECUTION, permit.check_active, permit.inflight_active)
        self.journal = directory / 'journal.sqlite3'
        return wb.EgressBroker(policy, journal=self.journal, guard=guard, upstream=self.upstream,
                               credentials=self.credentials, **extra)

    def upstream_answering_after_the_expiry(self):
        """Every upstream call moves the injected clocks past the approval's expiry, then answers the token request."""
        self.upstream_calls = []

        def answer(host_name, method, target, headers, body, *, timeout):
            self.upstream_calls.append((method, target))
            self.clocks.elapse(LIFETIME + 1)
            return ib.ServiceResponse(200, (('content-type', 'application/json'),),
                                      b'{"token_type": "Bearer", "access_token": "token", "expires_in": 60}')
        patcher = patch.object(wb.LaboratoryUpstream, 'request', side_effect=answer)
        patcher.start()
        self.addCleanup(patcher.stop)

    def send(self, broker):
        return broker.handle('login.microsoftonline.com', 'POST', self.token_path, dict(TOKEN_HEADERS), self.form)

    def attempts(self):
        connection = sqlite3.connect(self.journal)
        try:
            return connection.execute('SELECT route, status FROM attempts').fetchall()
        finally:
            connection.close()

    def assert_request_crosses_and_is_delivered(self, permit, broker):
        opened = clock.monotonic()
        self.assertLess(time.time(), self.expires)  # valid at dispatch
        self.assertEqual(self.send(broker).status, 200)
        self.assertGreaterEqual(time.time(), self.expires)  # the injected clocks crossed the expiry while it was in flight
        self.assertGreaterEqual(clock.monotonic(), opened + LIFETIME)
        self.assertEqual(self.attempts(), [('token', 'response_received')])
        self.assertEqual(len(self.upstream_calls), 1)

    def assert_a_new_request_after_the_expiry_is_refused(self, permit, broker, code):
        self.assertIn(self.refused(lambda: self.send(broker)).code, ('broker_expired', 'broker_policy_invalid', code))
        self.assertIn(self.refused(permit.check_active).code, ('broker_policy_invalid', code))  # the real runtime check refuses first
        self.assertEqual(len(self.upstream_calls), 1)  # nothing new reached the upstream
        self.assertEqual(self.attempts(), [('token', 'response_received')])


class AdoptionCrossingTests(RealBindings, adoption_latch.AdoptionFixture):
    def setUp(self):
        super().setUp()
        self.build_bindings()
        self.manifest.update(execution_binding_sha256=EXECUTION, run_binding_sha256=self.run_binding.sha256,
            storage_binding_sha256=self.storage_binding.sha256, identity_binding_sha256=self.binding.evidence()['binding_sha256'],
            state_contract=self.state_contract.binding(), provider_binding=self.provider.binding(),
            ownership_binding=self.ownership.binding(), host_spec=self.host_spec, verification_host_spec=self.host_spec,
            broker_policy=self.import_policy(), tenant_id=v5.TENANT, object_ids=[state_fixture.OID])
        self.manifest['verification_broker_policy'] = self.plan_policy(self.manifest['verification_operation_id'])
        self.job.sha256 = digest(self.manifest)  # the fixture's job row and operation row carry the manifest digest
        with self.policy.connection() as db:
            db.execute('UPDATE jobs SET manifest_sha256=? WHERE id=?', (self.job.sha256, self.job.identifier))
            db.execute('UPDATE adoption_operations SET manifest_sha256=? WHERE operation_id=?', (self.job.sha256, self.job.identifier))
        patcher = patch.object(adoption.AdoptionRuntime, 'check', REAL_ADOPTION_CHECK)  # the fixture's mock is replaced
        patcher.start()
        self.addCleanup(patcher.stop)
        self.runtime = adoption.laboratory_runtime(run=self.run_binding, storage=self.storage_binding, binding=self.binding,
            credentials=self.credentials, upstream=self.upstream, certificate=self.certificate, private_key=self.private_key,
            state_contract=self.state_contract, ownership=self.ownership, provider=self.provider)
        self.upstream_answering_after_the_expiry()

    def verification_permit(self, permit):
        """The permit of the verification (first plan) phase of the same job, over the verification broker policy."""
        with self.policy.connection() as db:
            db.execute("UPDATE jobs SET status='verification_running' WHERE id=?", (self.job.identifier,))
            db.execute("UPDATE adoption_operations SET verification_dispatches=1, verification_status='running' WHERE operation_id=?",
                       (self.job.identifier,))
        return adoption.AdoptionPermit(adoption._SEAL, self.job, permit.payload, self.runtime, True)

    def test_the_runtime_is_real_and_a_dispatch_inside_the_window_passes_it(self):
        self.assertIs(adoption.AdoptionRuntime.check, REAL_ADOPTION_CHECK)
        permit = self.dispatch_running(self.start + 10)
        permit.check_active()
        permit.inflight_active()
        self.assertEqual(self.dispatched, ['import'])

    def test_an_import_request_that_crosses_the_expiry_is_delivered_and_a_new_one_after_it_is_refused(self):
        permit = self.dispatch_running(self.start + 10)
        broker = self.broker(permit, self.manifest['broker_policy'], adoption_contract=self.state_contract,
                             state_contracts={'state': self.state_contract})
        self.assert_request_crosses_and_is_delivered(permit, broker)
        permit.inflight_active()  # the in-flight check of the dispatched request, after the expiry, with the real runtime
        self.assert_a_new_request_after_the_expiry_is_refused(permit, broker, 'adoption_signature_expired')

    def test_a_verification_request_that_crosses_the_expiry_is_delivered_and_a_new_one_after_it_is_refused(self):
        permit = self.verification_permit(self.dispatch_running(self.start + 10))
        permit.check_active()
        broker = self.broker(permit, self.manifest['verification_broker_policy'])
        self.assert_request_crosses_and_is_delivered(permit, broker)
        permit.inflight_active()
        self.assert_a_new_request_after_the_expiry_is_refused(permit, broker, 'adoption_signature_expired')

    def test_the_real_runtime_check_judges_the_window_unless_it_is_asked_not_to(self):
        # Control: the window really is closed for the real check, so the crossing tests above would catch a regression.
        self.dispatch_running(self.start + 10)
        self.clocks.elapse(LIFETIME + 1)
        for verification in (False, True):
            self.assertEqual(self.refused(lambda: self.runtime.check(self.manifest, verification=verification)).code,
                             'broker_policy_invalid')
            self.runtime.check(self.manifest, verification=verification, check_window=False)

    def test_the_broker_credentials_honor_check_window_false_with_an_adoption_contract(self):
        policy = self.manifest['broker_policy']
        self.credentials.check(policy, adoption_contract=self.state_contract)
        self.clocks.elapse(LIFETIME + 1)
        self.assertEqual(self.refused(lambda: self.credentials.check(policy, adoption_contract=self.state_contract)).code,
                         'broker_policy_invalid')
        self.credentials.check(policy, adoption_contract=self.state_contract, check_window=False)

    def test_after_the_expiry_the_inflight_check_still_refuses_a_cancelled_or_revoked_dispatch(self):
        permit = self.dispatch_running(self.start + 10)
        self.clocks.elapse(LIFETIME + 1)
        permit.inflight_active()
        with self.policy.connection() as db:
            db.execute('UPDATE jobs SET cancelled=1 WHERE id=?', (self.job.identifier,))
        self.assertEqual(self.refused(permit.inflight_active).code, 'adoption_permit_inactive')
        with self.policy.connection() as db:
            db.execute('UPDATE jobs SET cancelled=0 WHERE id=?', (self.job.identifier,))
            db.execute('INSERT INTO revoked VALUES (?,?)', ('fixture', 'key'))
        self.assertEqual(self.refused(permit.inflight_active).code, 'adoption_permit_inactive')

    def test_after_the_expiry_the_inflight_check_still_refuses_a_changed_binding(self):
        permit = self.dispatch_running(self.start + 10)
        self.clocks.elapse(LIFETIME + 1)
        permit.inflight_active()
        self.run_binding.facts = dict(self.run_binding.facts, fixture_run='changed')
        self.assertEqual(self.refused(permit.inflight_active).code, 'service_controller_binding_changed')


class RecoveryPlanCrossingTests(RealBindings, recovery_latch.RecoveryFixture):
    def setUp(self):
        super().setUp()
        self.build_bindings()
        self.manifest.update(execution_binding_sha256=EXECUTION, run_binding_sha256=self.run_binding.sha256,
            storage_binding_sha256=self.storage_binding.sha256, identity_binding_sha256=self.binding.evidence()['binding_sha256'],
            provider_binding=self.provider.binding(), host_spec=self.host_spec)
        self.manifest['broker_policy'] = self.plan_policy(self.manifest['operation_id'])
        self.job.sha256 = digest(self.manifest)
        with self.policy.connection() as db:
            db.execute('UPDATE adoption_recovery_plans SET manifest_sha256=? WHERE operation_id=?', (self.job.sha256, self.job.identifier))
        facts = {'fresh_observation': {'identity_binding_sha256': self.manifest['identity_binding_sha256']}}
        for patcher in (patch.object(bridge.RecoveryPlanRuntime, 'check', REAL_RECOVERY_CHECK),  # the fixture's mocks are replaced
                        patch.object(bridge.service, '_host_spec', REAL_HOST_SPEC),
                        patch.object(bridge, '_completion', return_value=facts)):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.runtime = bridge.laboratory_runtime(run=self.run_binding, storage=self.storage_binding, binding=self.binding,
            credentials=self.credentials, upstream=self.upstream, certificate=self.certificate, private_key=self.private_key,
            provider=self.provider)
        self.upstream_answering_after_the_expiry()

    def running(self, at):
        self.clocks.wall = at
        self.run_job(self.receipt())
        return self.permits[-1]

    def test_the_runtime_is_real_and_a_dispatch_inside_the_window_passes_it(self):
        self.assertIs(bridge.RecoveryPlanRuntime.check, REAL_RECOVERY_CHECK)
        permit = self.running(self.start + 10)
        permit.check_active()
        permit.inflight_active()
        self.assertEqual(self.dispatched, ['plan'])

    def test_a_recovery_plan_request_that_crosses_the_expiry_is_delivered_and_a_new_one_after_it_is_refused(self):
        permit = self.running(self.start + 10)
        broker = self.broker(permit, self.manifest['broker_policy'])
        self.assert_request_crosses_and_is_delivered(permit, broker)
        permit.inflight_active()
        self.assert_a_new_request_after_the_expiry_is_refused(permit, broker, 'adoption_recovery_plan_expired')

    def test_the_real_runtime_check_judges_the_window_unless_it_is_asked_not_to(self):
        self.running(self.start + 10)
        self.clocks.elapse(LIFETIME + 1)
        self.assertEqual(self.refused(lambda: self.runtime.check(self.manifest)).code, 'broker_policy_invalid')
        self.runtime.check(self.manifest, check_window=False)

    def test_after_the_expiry_the_inflight_check_still_refuses_a_cancelled_dispatch_and_a_changed_binding(self):
        permit = self.running(self.start + 10)
        self.clocks.elapse(LIFETIME + 1)
        permit.inflight_active()
        self.run_binding.facts = dict(self.run_binding.facts, fixture_run='changed')
        self.assertEqual(self.refused(permit.inflight_active).code, 'service_controller_binding_changed')
        self.run_binding.facts = dict(self.run_binding.facts, fixture_run='literal-local-container')
        with self.policy.connection() as db:
            db.execute('UPDATE adoption_recovery_plans SET cancelled=1 WHERE operation_id=?', (self.job.identifier,))
        self.assertEqual(self.refused(permit.inflight_active).code, 'adoption_recovery_permit_revoked')


if __name__ == '__main__':
    unittest.main()
