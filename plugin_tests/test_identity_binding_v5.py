"""Recorded-response contract tests: synthetic services, never live authority."""
import copy
from dataclasses import replace
import hashlib
import json
import io
import os
import pickle
import threading
import time
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs

from intune_iac import identity_binding as ib
from intune_iac.io import AppError

TENANT = '11111111-1111-1111-1111-111111111111'
CLIENT = '22222222-2222-2222-2222-222222222222'
OBJECT = '33333333-3333-3333-3333-333333333333'
BACK_CLIENT = '44444444-4444-4444-4444-444444444444'
BACK_OBJECT = '55555555-5555-5555-5555-555555555555'
SUBSCRIPTION = '66666666-6666-6666-6666-666666666666'
LINEAGE = '77777777-7777-7777-7777-777777777777'
RESOURCE = '/subscriptions/' + SUBSCRIPTION + '/resourceGroups/state-rg/providers/Microsoft.Storage/storageAccounts/recordedstate'
STATE = ('{"version":4,"lineage":"' + LINEAGE + '","serial":12,"resources":[]}').encode()


class Clock:
    def __init__(self): self.now = 1000.0
    def __call__(self): return self.now


class RecordedServices:
    """Independent fixed service recordings; no implementation-derived response facts."""
    def __init__(self):
        self.calls = []
        self.responses = [
            (200, {'content-type': 'application/json'}, {'token_type': 'Bearer', 'expires_in': 3600, 'access_token': 'opaque-provider-no-jwt'}),
            (200, {'content-type': 'application/json'}, {'id': OBJECT, 'appId': CLIENT, 'accountEnabled': True}),
            (200, {'content-type': 'application/json'}, {'token_type': 'Bearer', 'expires_in': 3600, 'access_token': 'opaque-backend-graph'}),
            (200, {'content-type': 'application/json'}, {'id': BACK_OBJECT, 'appId': BACK_CLIENT, 'accountEnabled': True}),
            (200, {'content-type': 'application/json'}, {'token_type': 'Bearer', 'expires_in': 3600, 'access_token': 'opaque-backend-arm'}),
            (200, {'content-type': 'application/json'}, {'subscriptionId': SUBSCRIPTION, 'tenantId': TENANT, 'state': 'Enabled'}),
            (200, {'content-type': 'application/json'}, {'id': RESOURCE, 'properties': {'primaryEndpoints': {'blob': 'https://recordedstate.blob.core.windows.net/'}}}),
            (200, {'content-type': 'application/json'}, {'token_type': 'Bearer', 'expires_in': 3600, 'access_token': 'opaque-backend-storage'}),
        ]
        headers = {'etag': '"recorded-etag-1"', 'content-length': str(len(STATE)), 'x-ms-blob-type': 'BlockBlob'}
        self.responses += [(200, headers.copy(), b''), (200, headers.copy(), STATE), (200, headers.copy(), b'')]
        self.index = 0

    def __call__(self, request, *, timeout, max_bytes):
        self.calls.append(request)
        status, headers, body = self.responses[self.index % len(self.responses)]
        self.index += 1
        if not isinstance(body, bytes): body = json.dumps(body).encode()
        return ib.ServiceResponse(status, tuple(headers.items()), body)


def config():
    return ib.BindingConfig(
        provider=ib.IdentitySpec(TENANT, CLIENT, OBJECT),
        backend_identity=ib.IdentitySpec(TENANT, BACK_CLIENT, BACK_OBJECT),
        backend=ib.BackendSpec(SUBSCRIPTION, RESOURCE, 'https://recordedstate.blob.core.windows.net',
                               'tfstate', 'intune.tfstate', 'default', LINEAGE, 12, hashlib.sha256(STATE).hexdigest()))


class IdentityBindingTests(unittest.TestCase):
    def setUp(self):
        self.transport, self.clock = RecordedServices(), Clock()
        self.provider = ib.ClientSecretHandle('synthetic-provider-secret')
        self.backend = ib.ClientSecretHandle('synthetic-backend-secret')

    def bind(self, cfg=None):
        return ib.bind_laboratory(cfg or config(), provider_credential=self.provider,
                                  backend_credential=self.backend, transport=self.transport, clock=self.clock)

    def fails(self, code, action=None):
        with self.assertRaises(AppError) as caught: (action or self.bind)()
        self.assertEqual(caught.exception.code, code)

    def test_opaque_tokens_identity_binding_and_exact_scopes(self):
        bound = self.bind()
        self.assertIs(type(bound), ib.LaboratoryIdentityBinding)
        evidence = bound.evidence()
        self.assertEqual(evidence['assurance'], 'laboratory_recorded_responses')
        self.assertFalse(evidence['execution_authorized'])
        self.assertEqual(len(self.transport.calls), 11)
        posts = [call for call in self.transport.calls if call.method == 'POST']
        self.assertEqual([call.host for call in posts], ['login.microsoftonline.com'] * 4)
        self.assertEqual([call.path for call in posts], ['/' + TENANT + '/oauth2/v2.0/token'] * 4)
        forms = [parse_qs(call.body.decode()) for call in posts]
        self.assertEqual([f['scope'][0] for f in forms], ['https://graph.microsoft.com/.default'] * 2 + ['https://management.azure.com/.default', 'https://storage.azure.com/.default'])
        self.assertEqual([f['client_id'][0] for f in forms], [CLIENT, BACK_CLIENT, BACK_CLIENT, BACK_CLIENT])
        self.assertTrue(all(f['grant_type'] == ['client_credentials'] for f in forms))
        self.assertEqual(self.transport.calls[1].path, "/v1.0/servicePrincipals(appId='" + CLIENT + "')?$select=id,appId,accountEnabled")

    def test_provider_environment_uses_same_handle_and_no_inheritance(self):
        with patch.dict(os.environ, {'M365_TENANT_ID': 'wrong', 'ARM_CLIENT_SECRET': 'ambient', 'M365_AUTH_METHOD': 'azure_cli', 'HTTPS_PROXY': 'https://untrusted.invalid'}):
            bound = self.bind()
            self.assertEqual(bound.provider_environment(), {'M365_TENANT_ID': TENANT, 'M365_CLIENT_ID': CLIENT,
                             'M365_CLIENT_SECRET': 'synthetic-provider-secret', 'M365_AUTH_METHOD': 'client_secret'})

    def test_evidence_and_repr_never_contain_secrets_tokens_or_raw_identifiers(self):
        bound = self.bind()
        visible = json.dumps(bound.evidence()) + repr(bound) + repr(self.provider) + repr(self.transport.calls)
        for secret in ['synthetic-provider-secret', 'synthetic-backend-secret', 'opaque-provider-no-jwt', TENANT, CLIENT, OBJECT, RESOURCE]:
            self.assertNotIn(secret, visible)
        for value in (bound, self.provider):
            with self.assertRaises(TypeError): pickle.dumps(value)

    def test_json_and_direct_construction_cannot_create_live_authority(self):
        for value in ({}, self.bind().evidence(), self.bind()):
            self.fails('identity_live_binding_required', lambda: ib.require_live_binding(value))
        with self.assertRaises(TypeError): ib.LiveIdentityBinding()
        with self.assertRaises(TypeError): ib.bind_live(config(), provider_credential=self.provider, backend_credential=self.backend, transport=self.transport)

    def test_graph_client_object_and_enabled_are_exact(self):
        for name, value in [('id', BACK_OBJECT), ('appId', BACK_CLIENT), ('accountEnabled', False), ('accountEnabled', 1)]:
            with self.subTest(name=name, value=value):
                self.transport = RecordedServices()
                self.transport.responses[1][2][name] = value
                self.fails('identity_service_principal_mismatch')

    def test_backend_identity_is_independently_checked(self):
        self.transport.responses[3][2]['id'] = OBJECT
        self.fails('identity_service_principal_mismatch')

    def test_arm_wrong_tenant_subscription_or_disabled(self):
        for field, value in [('tenantId', BACK_OBJECT), ('subscriptionId', CLIENT), ('state', 'Disabled')]:
            with self.subTest(field=field):
                self.transport = RecordedServices()
                self.transport.responses[5][2][field] = value
                self.fails('identity_subscription_mismatch')

    def test_storage_resource_or_cross_origin_endpoint_mismatch(self):
        self.transport.responses[6][2]['properties']['primaryEndpoints']['blob'] = 'https://attacker.invalid/'
        self.fails('identity_storage_target_mismatch')
        self.transport = RecordedServices()
        self.transport.responses[6][2]['id'] += '-wrong'
        self.fails('identity_storage_target_mismatch')

    def test_explicit_configuration_rejects_other_cloud_methods_or_malformed_targets(self):
        cases = [replace(config(), cloud='government'),
                 replace(config(), provider=replace(config().provider, auth_method='azure_cli')),
                 replace(config(), provider=replace(config().provider, tenant_id='common')),
                 replace(config(), backend=replace(config().backend, blob_endpoint='https://attacker.invalid')),
                 replace(config(), backend=replace(config().backend, key='../state'))]
        for cfg in cases:
            with self.subTest(cfg=cfg): self.fails('identity_configuration_invalid', lambda: self.bind(cfg))
        self.assertEqual(self.transport.calls, [])

    def test_redirect_authentication_and_permission_failures_distinct(self):
        for status, code in [(302, 'identity_redirect_rejected'), (401, 'identity_authentication_failed'), (403, 'identity_permission_denied'), (429, 'identity_service_unavailable')]:
            with self.subTest(status=status):
                self.transport = RecordedServices()
                self.transport.responses[1] = (status, {'location': 'https://attacker.invalid'}, b'synthetic-provider-secret')
                self.fails(code)
                self.assertEqual(len(self.transport.calls), 2)

    def test_token_endpoint_failure_and_expiry_never_fall_back(self):
        self.transport.responses[0] = (400, {}, b'{"error":"invalid_client"}')
        self.fails('identity_authentication_failed')
        self.assertEqual(len(self.transport.calls), 1)
        for value in (0, -1, True, '3600'):
            self.transport = RecordedServices()
            self.transport.responses[0][2]['expires_in'] = value
            self.fails('identity_token_response_invalid')

    def test_expired_freshness_or_revoked_handle_blocks_environment(self):
        bound = self.bind()
        self.clock.now += 61
        self.fails('identity_binding_stale', bound.provider_environment)
        self.clock.now = 1000
        self.provider.close()
        self.fails('identity_credential_unavailable', bound.provider_environment)

    def test_token_expiry_is_enforced_before_max_age(self):
        self.transport.responses[0][2]['expires_in'] = 10
        bound = self.bind()
        self.clock.now += 11
        self.fails('identity_token_expired', bound.assert_fresh)

    def test_recheck_reacquires_all_tokens_and_detects_revocation(self):
        bound = self.bind()
        before = bound.evidence()['binding_sha256']
        self.clock.now += 2
        bound.recheck()
        self.assertEqual(bound.evidence()['binding_sha256'], before)
        self.assertEqual(len(self.transport.calls), 22)
        self.transport.responses[0] = (400, {}, b'{"error":"invalid_client"}')
        self.fails('identity_authentication_failed', bound.recheck)
        self.fails('identity_binding_invalidated', bound.provider_environment)

    def test_state_conditional_reads_and_lineage_serial_digest(self):
        self.bind()
        reads = self.transport.calls[-3:]
        self.assertEqual([r.method for r in reads], ['HEAD', 'GET', 'HEAD'])
        self.assertTrue(all(r.host == 'recordedstate.blob.core.windows.net' and r.path == '/tfstate/intune.tfstate' for r in reads))
        self.assertNotIn('If-Match', reads[0].headers)
        self.assertEqual([r.headers['If-Match'] for r in reads[1:]], ['"recorded-etag-1"'] * 2)
        for field, value in [('state_serial', 13), ('state_lineage', OBJECT), ('state_sha256', '0' * 64)]:
            self.transport = RecordedServices()
            self.fails('identity_state_mismatch', lambda: self.bind(replace(config(), backend=replace(config().backend, **{field: value}))))

    def test_etag_race_conditional_failure_and_recheck_changed_etag(self):
        for index, status in [(9, 412), (10, 412)]:
            self.transport = RecordedServices()
            self.transport.responses[index] = (status, {}, b'')
            self.fails('identity_state_changed')
        self.transport = RecordedServices()
        bound = self.bind()
        for i in (8, 9, 10): self.transport.responses[i][1]['etag'] = '"recorded-etag-2"'
        self.fails('identity_observation_changed', bound.recheck)

    def test_partial_missing_or_oversized_state_is_never_empty_success(self):
        for body in (b'', b'{', b'{}', STATE[:-1], b'x' * (ib.MAX_STATE_BYTES + 1)):
            self.transport = RecordedServices()
            self.transport.responses[9] = (200, self.transport.responses[9][1], body)
            with self.assertRaises(AppError): self.bind()

    def test_duplicate_headers_json_keys_and_wrong_encoding_rejected(self):
        for index, body, headers in [(1, b'{"id":1,"id":2}', {'content-type': 'application/json'}),
                                     (1, b'{}', {'content-type': 'text/html'}),
                                     (1, b'{}', {'content-type': 'application/json', 'content-encoding': 'gzip'})]:
            self.transport = RecordedServices()
            self.transport.responses[index] = (200, headers, body)
            with self.assertRaises(AppError): self.bind()

    def test_failing_transport_redacts_exception(self):
        def failed(*args, **kwargs): raise OSError('synthetic-provider-secret')
        self.transport = failed
        with self.assertRaises(AppError) as caught: self.bind()
        self.assertNotIn('synthetic-provider-secret', str(caught.exception))

    def test_no_credentials_from_environment_when_handles_missing(self):
        with patch.dict(os.environ, {'M365_CLIENT_SECRET': 'ambient', 'AZURE_CLIENT_SECRET': 'ambient'}):
            self.fails('identity_credential_required', lambda: ib.bind_laboratory(config(), provider_credential=None,
                backend_credential=self.backend, transport=self.transport))
        self.assertEqual(self.transport.calls, [])

    def test_request_deadline_expires_before_accepting_response(self):
        def slow(request, **kwargs):
            response = self.transport(request, **kwargs)
            self.clock.now += 61
            return response
        self.fails('identity_transport_deadline', lambda: ib.bind_laboratory(config(), provider_credential=self.provider,
            backend_credential=self.backend, transport=slow, clock=self.clock))

    def test_duplicate_headers_and_header_total_bound(self):
        for headers in [(('content-type', 'application/json'), ('Content-Type', 'application/json')),
                        (('content-type', 'application/json'),) + tuple((f'x-{i}', 'a' * 8000) for i in range(10))]:
            response = ib.ServiceResponse(200, headers, b'{"token_type":"Bearer","expires_in":3600,"access_token":"opaque"}')
            self.fails('identity_response_invalid', lambda: ib.bind_laboratory(config(), provider_credential=self.provider,
                backend_credential=self.backend, transport=lambda *a, **kw: response))

    def test_workspace_blob_name_is_exact_and_safely_encoded(self):
        self.bind(replace(config(), backend=replace(config().backend, workspace='production')))
        self.assertEqual(self.transport.calls[-1].path, '/tfstate/intune.tfstateenv%3Aproduction')

    def test_server_diagnostics_never_escape_on_partial_failure(self):
        self.transport.responses[8] = (404, {}, b'{"error":"synthetic-backend-secret"}')
        with self.assertRaises(AppError) as caught: self.bind()
        self.assertNotIn('synthetic-backend-secret', str(caught.exception))
        self.assertEqual(len(self.transport.calls), 9)

    def test_wrong_provider_tenant_only_uses_explicit_tenant_endpoint(self):
        other = replace(config(), provider=replace(config().provider, tenant_id=BACK_OBJECT))
        def independent_authority(request, **kwargs):
            if request.path != '/' + TENANT + '/oauth2/v2.0/token':
                return ib.ServiceResponse(400, (), b'{"error":"invalid_client"}')
            return self.transport(request, **kwargs)
        self.fails('identity_authentication_failed', lambda: ib.bind_laboratory(other, provider_credential=self.provider,
            backend_credential=self.backend, transport=independent_authority))

    def test_backend_access_requires_exact_handle_and_returns_redacted_expiring_token(self):
        bound = self.bind()
        identity, backend = bound.backend_configuration(self.backend)
        self.assertEqual(identity, config().backend_identity)
        self.assertEqual(backend, config().backend)
        self.fails('identity_backend_handle_mismatch', lambda: bound.backend_configuration(self.provider))
        self.transport.index = 7
        token = bound.backend_storage_token(self.backend, timeout=0.5)
        self.assertEqual(token._get(), 'opaque-backend-storage')
        self.assertNotIn('opaque-backend-storage', repr(token))
        with self.assertRaises(TypeError): pickle.dumps(token)
        token.close()
        self.fails('identity_backend_token_unavailable', token._get)

    def test_backend_token_age_and_deadline_bound_are_enforced(self):
        bound = self.bind()
        self.transport.index = 7
        self.transport.responses[7][2]['expires_in'] = 1
        token = bound.backend_storage_token(self.backend, timeout=0.25)
        self.clock.now += 2
        self.fails('identity_token_expired', token._get)
        for timeout in (0, -1, True, float('nan'), 31):
            self.fails('identity_limits_invalid', lambda: bound.backend_storage_token(self.backend, timeout=timeout))


class NativeTransportContractTests(unittest.TestCase):
    """Native adapter with an in-memory connection double: no live authority."""
    def test_dns_deadline_returns_and_cancelled_connect_never_sends(self):
        entered, release, done = threading.Event(), threading.Event(), threading.Event()
        calls = []
        class Connection:
            sock = None
            def __init__(self, *args, **kwargs): pass
            def connect(self): entered.set(); release.wait(1)
            def request(self, *args, **kwargs): calls.append('request')
            def close(self): done.set()
        with patch.object(ib.http.client, 'HTTPSConnection', Connection), patch.object(ib, '_system_tls_context', return_value=None):
            started = time.monotonic()
            try:
                with self.assertRaises(AppError) as caught:
                    ib._NativeTransport()(ib._Request('GET', 'graph.microsoft.com', '/', {}), timeout=0.03, max_bytes=10)
                self.assertEqual(caught.exception.code, 'identity_transport_deadline')
                self.assertLess(time.monotonic() - started, 0.5)
                self.assertTrue(entered.is_set())
            finally: release.set()
            done.wait(1)
        self.assertEqual(calls, [])

    def test_environment_does_not_select_tls_trust_store(self):
        context = unittest.mock.Mock()
        paths = unittest.mock.Mock(openssl_cafile='/fixed/system-ca.pem', openssl_capath='/fixed/certs')
        with patch.dict(os.environ, {'SSL_CERT_FILE': '/attacker/ca.pem', 'SSL_CERT_DIR': '/attacker/certs'}), \
                patch.object(ib.ssl, 'get_default_verify_paths', return_value=paths), \
                patch.object(ib.ssl, 'SSLContext', return_value=context), \
                patch.object(ib.os.path, 'isfile', return_value=True), \
                patch.object(ib.os.path, 'isdir', return_value=True):
            ib._system_tls_context()
        context.load_verify_locations.assert_called_once_with(cafile='/fixed/system-ca.pem', capath='/fixed/certs')

    def test_caller_interrupt_cancels_delayed_connect_before_credentials_send(self):
        entered, release, request_finished = threading.Event(), threading.Event(), threading.Event()
        sent = []
        original_queue = ib.queue.Queue
        class InterruptedQueue(original_queue):
            def get(self, **kwargs):
                self.assert_entered = entered.wait(1)
                raise KeyboardInterrupt()
        class Connection:
            sock = None
            def __init__(self, *args, **kwargs): pass
            def connect(self): entered.set(); release.wait(1)
            def request(self, *args, **kwargs): sent.append('sent'); request_finished.set()
            def getresponse(self): raise OSError('recorded stop')
            def close(self):
                if release.is_set(): request_finished.set()
        with patch.object(ib.queue, 'Queue', InterruptedQueue), patch.object(ib.http.client, 'HTTPSConnection', Connection), patch.object(ib, '_system_tls_context', return_value=None):
            try:
                with self.assertRaises(KeyboardInterrupt):
                    ib._NativeTransport()(ib._Request('POST', 'login.microsoftonline.com', '/fixed/token', {}, b'synthetic'), timeout=1, max_bytes=10)
            finally: release.set()
            self.assertTrue(request_finished.wait(1))
        self.assertEqual(sent, [])

    def test_timeout_closure_never_auto_reconnects_before_request_send(self):
        entered, release, request_finished = threading.Event(), threading.Event(), threading.Event()
        sent, connects = [], []
        class Socket:
            def sendall(self, data): sent.append(data)
            def shutdown(self, how): pass
            def close(self): pass
            def makefile(self, *args): return io.BytesIO(b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}')
        class Connection(ib.http.client.HTTPConnection):
            def __init__(self, host, *, port, timeout, context): super().__init__(host, port=port, timeout=timeout)
            def connect(self): connects.append(1); self.sock = Socket()
            def request(self, *args, **kwargs):
                entered.set(); release.wait(1)
                try: return super().request(*args, **kwargs)
                finally: request_finished.set()
        with patch.object(ib.http.client, 'HTTPSConnection', Connection), patch.object(ib, '_system_tls_context', return_value=None):
            try:
                with self.assertRaises(AppError):
                    ib._NativeTransport()(ib._Request('POST', 'login.microsoftonline.com', '/fixed/token', {}, b'synthetic'), timeout=0.03, max_bytes=10)
                self.assertTrue(entered.is_set())
            finally: release.set()
            self.assertTrue(request_finished.wait(1))
        self.assertEqual(connects, [1])
        self.assertEqual(sent, [])

    def test_detached_connection_close_body_socket_is_shutdown_on_deadline(self):
        reading, stopped, response_closed = threading.Event(), threading.Event(), threading.Event()
        class Socket:
            def shutdown(self, how): stopped.set()
        class Response:
            status = 200
            def getheaders(self): return [('content-length', '2')]
            def read(self, limit): reading.set(); stopped.wait(1); return b'{}'
            def close(self): response_closed.set()
        class Connection:
            sock = None
            def __init__(self, *args, **kwargs): pass
            def connect(self): self.sock = Socket()
            def request(self, *args, **kwargs): pass
            def getresponse(self): self.sock = None; return Response()
            def close(self): self.sock = None
        with patch.object(ib.http.client, 'HTTPSConnection', Connection), patch.object(ib, '_system_tls_context', return_value=None):
            try:
                with self.assertRaises(AppError):
                    ib._NativeTransport()(ib._Request('GET', 'graph.microsoft.com', '/fixed', {}), timeout=0.03, max_bytes=10)
                self.assertTrue(reading.is_set())
                self.assertTrue(stopped.is_set(), 'Deadline must shut down the retained body socket.')
                self.assertTrue(response_closed.wait(0.5))
            finally: stopped.set()


if __name__ == '__main__': unittest.main()
