"""Actual loopback TLS and Unix CONNECT probes; no native service claims."""
import base64
import copy
from datetime import datetime, timezone
import io
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import sqlite3
import ssl
import subprocess
import tempfile
import threading
import time
import unittest
from urllib.parse import urlencode, parse_qs

from intune_iac import worker_broker as wb
from intune_iac.io import AppError


class BrokerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.certroot = tempfile.TemporaryDirectory(); root = Path(cls.certroot.name)
        cls.cert, cls.key = root / 'certificate.pem', root / 'key.pem'
        subprocess.run(['/usr/bin/openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
            '-keyout', str(cls.key), '-out', str(cls.cert), '-days', '1', '-subj', '/CN=local-fixture',
            '-addext', 'subjectAltName=IP:127.0.0.1,DNS:login.fixture.invalid,DNS:graph.fixture.invalid,DNS:blob.fixture.invalid'],
            check=True, capture_output=True)
        cls.cert.chmod(0o600); cls.key.chmod(0o600)

    @classmethod
    def tearDownClass(cls): cls.certroot.cleanup()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(); self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name); self.calls = []; self.behavior = 'normal'; outer = self
        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'
            def log_message(self, *args): pass
            def do_POST(self): self.respond()
            def do_PUT(self): self.respond()
            def do_GET(self): self.respond()
            def do_HEAD(self): self.respond()
            def respond(self):
                body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
                outer.calls.append((self.command, self.path, dict(self.headers), body))
                if outer.behavior == 'cancel_after_effect': outer.active = False
                if outer.behavior == 'disconnect':
                    self.connection.shutdown(socket.SHUT_RDWR); self.connection.close(); return
                if outer.behavior == 'redirect':
                    self.send_response(302); self.send_header('Location', 'https://evil.invalid/'); self.send_header('Content-Length', '0'); self.end_headers(); return
                if '?comp=lease' in self.path:
                    status = 412 if outer.behavior == 'lease_failure' else (201 if self.headers.get('x-ms-lease-action') == 'acquire' else 200)
                    self.send_response(status); self.send_header('Content-Length', '0')
                    self.send_header('x-ms-lease-id', self.headers.get('x-ms-proposed-lease-id', self.headers.get('x-ms-lease-id', 'missing')))
                    self.end_headers(); return
                if self.path.startswith('/common/discovery/instance'):
                    endpoint = 'https://login.fixture.invalid/' + outer.tenant + '/v2.0/.well-known/openid-configuration'
                    if outer.behavior == 'foreign_metadata': endpoint = 'https://evil.invalid/metadata'
                    data = json.dumps({'tenant_discovery_endpoint': endpoint, 'metadata': []}).encode()
                elif '/.well-known/openid-configuration' in self.path:
                    base = 'https://login.fixture.invalid/' + outer.tenant + '/oauth2/v2.0/'
                    data = json.dumps({'token_endpoint': base + 'token', 'authorization_endpoint': base + 'authorize'}).encode()
                else:
                    data = (json.dumps({'token_type': 'Bearer', 'access_token': 'fixture-' + str(len(outer.calls)), 'expires_in': 60}).encode()
                        if self.path.endswith('/token') else b'{"accepted":true}')
                self.send_response(200); self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(123 if self.command == 'HEAD' else len(data)))
                self.send_header('ETag', '"fixture-etag"'); self.end_headers()
                if self.command != 'HEAD': self.wfile.write(data)
        self.upstream_server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); context.load_cert_chain(self.cert, self.key)
        self.upstream_server.socket = context.wrap_socket(self.upstream_server.socket, server_side=True)
        self.thread = threading.Thread(target=self.upstream_server.serve_forever, daemon=True); self.thread.start()
        self.addCleanup(self.upstream_server.server_close); self.addCleanup(self.upstream_server.shutdown)
        self.tenant = '00000000-0000-0000-0000-000000000001'; self.client = '00000000-0000-0000-0000-000000000002'
        self.form = urlencode({'client_id': self.client, 'client_secret': 'synthetic-secret',
            'grant_type': 'client_credentials', 'scope': 'https://graph.microsoft.com/.default'}).encode()
        self.body = b'{"name":"exact approved correction"}'
        def route(name, host, method, path, body, effect, maximum=1):
            return {'id': name, 'host': host, 'method': method, 'path': path, 'query': {},
                'headers': {'content-type': 'application/x-www-form-urlencoded' if effect == 'oauth' else 'application/json'} if body else {},
                'body_sha256': hashlib.sha256(body).hexdigest(), 'role': 'provider', 'audience': 'graph',
                'effect': effect, 'max_attempts': maximum}
        self.policy = {'schema_version': 'protected-egress-policy/1.0', 'profile': 'laboratory_tls_fixture',
            'operation_id': 'a' * 32, 'execution_binding_sha256': 'b' * 64, 'expires_at': int(time.time()) + 300,
            'worker_uid': os.geteuid(), 'identities': {'provider': {'tenant_id': self.tenant, 'client_id': self.client}},
            'routes': [route('token', 'login.fixture.invalid', 'POST', '/' + self.tenant + '/oauth2/v2.0/token', self.form, 'oauth', 8),
                       route('policy', 'graph.fixture.invalid', 'PUT', '/beta/deviceManagement/configurationPolicies/id', self.body, 'mutation'),
                       route('readback', 'graph.fixture.invalid', 'GET', '/beta/deviceManagement/configurationPolicies/id', b'', 'readonly', 3),
                       route('head', 'graph.fixture.invalid', 'HEAD', '/head', b'', 'readonly', 2)]}
        self.active = True
        def check():
            if not self.active: raise AppError('fixture_cancelled', 'Synthetic controller cancellation.')
        self.guard = wb.laboratory_guard(self.policy['execution_binding_sha256'], check)
        self.upstream = wb.LaboratoryUpstream(self.upstream_server.server_port, self.cert)
        self.broker = wb.EgressBroker(self.policy, journal=self.root / 'journal.sqlite3', guard=self.guard, upstream=self.upstream)
        self.server = wb.UnixBrokerServer(self.root / 'egress.sock', self.broker, certificate=self.cert, private_key=self.key)
        self.server_thread = threading.Thread(target=self.server.serve, daemon=True); self.server_thread.start()
        self.addCleanup(self.server.close)

    def request(self, host, method, path, body=b'', headers=None, raw=None):
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); connection.settimeout(3)
        connection.connect(str(self.root / 'egress.sock'))
        try:
            connection.sendall(('CONNECT ' + host + ':443 HTTP/1.1\r\nHost: ' + host + ':443\r\n\r\n').encode())
            answer = b''
            while not answer.endswith(b'\r\n\r\n'): answer += connection.recv(1)
            self.assertIn(b'200', answer)
            context = ssl.create_default_context(cafile=self.cert)
            connection = context.wrap_socket(connection, server_hostname=host)
            message = (method + ' ' + path + ' HTTP/1.1\r\nHost: ' + host + '\r\nContent-Length: ' + str(len(body)) + '\r\n' +
                       ''.join(k + ': ' + v + '\r\n' for k, v in (headers or {}).items()) + '\r\n').encode() + body
            connection.sendall(raw if raw is not None else message)
            response = http.client.HTTPResponse(connection, method=method); response.begin()
            return response.status, dict(response.getheaders()), response.read()
        finally: connection.close()

    def token(self):
        status, _, data = self.request('login.fixture.invalid', 'POST', '/' + self.tenant + '/oauth2/v2.0/token', self.form,
            {'Content-Type': 'application/x-www-form-urlencoded'})
        self.assertEqual(status, 200)
        return json.loads(data)['access_token']

    def mutation(self, token, *, body=None, headers=None):
        return self.request('graph.fixture.invalid', 'PUT', self.policy['routes'][1]['path'], self.body if body is None else body,
            {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json', **(headers or {})})

    def journal(self):
        with sqlite3.connect(self.root / 'journal.sqlite3') as db:
            return db.execute('SELECT route,status,response_code FROM attempts ORDER BY sequence').fetchall()

    def test_observed_native_go_connect_user_agent_is_admitted(self):
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.connect(str(self.root / 'egress.sock'))
        try:
            connection.sendall(b'CONNECT login.fixture.invalid:443 HTTP/1.1\r\nHost: login.fixture.invalid:443\r\nUser-Agent: Go-http-client/1.1\r\n\r\n')
            answer = b''
            while not answer.endswith(b'\r\n\r\n'): answer += connection.recv(1)
            self.assertTrue(answer.startswith(b'HTTP/1.1 200'), answer)
        finally: connection.close()
        self.assertEqual(self.calls, [])

    def test_connect_user_agent_does_not_admit_proxy_auth_framing_or_foreign_metadata(self):
        for extra in [b'Proxy-Authorization: Bearer foreign\r\n', b'Content-Length: 1\r\n',
                      b'Transfer-Encoding: chunked\r\n', b'X-HTTP-Method-Override: PUT\r\n',
                      b'User-Agent: altered-client\r\n']:
            connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            connection.connect(str(self.root / 'egress.sock'))
            try:
                connection.sendall(b'CONNECT login.fixture.invalid:443 HTTP/1.1\r\nHost: login.fixture.invalid:443\r\n' + extra + b'\r\n')
                answer = b''
                while not answer.endswith(b'\r\n\r\n'): answer += connection.recv(1)
                self.assertTrue(answer.startswith(b'HTTP/1.1 403'), answer)
            finally: connection.close()
        self.assertEqual(self.calls, [])

    def test_real_unix_connect_tls_exact_put_and_readback(self):
        token = self.token(); self.assertEqual(self.mutation(token)[0], 200)
        status, _, data = self.request('graph.fixture.invalid', 'GET', self.policy['routes'][2]['path'], headers={'Authorization': 'Bearer ' + token})
        self.assertEqual(status, 200); self.assertEqual(json.loads(data), {'accepted': True})
        self.assertEqual([row[0] for row in self.calls], ['POST', 'PUT', 'GET'])
        self.assertEqual(self.calls[1][3], self.body)
        self.assertEqual(self.journal(), [('token', 'response_received', 200), ('policy', 'response_received', 200), ('readback', 'response_received', 200)])

    def test_approved_write_is_at_most_one_dispatch(self):
        token = self.token(); self.assertEqual(self.mutation(token)[0], 200)
        self.assertEqual(self.mutation(token)[0], 403)
        self.assertEqual(len(self.calls), 2)

    def test_body_substitution_does_not_consume_approved_attempt(self):
        token = self.token(); self.assertEqual(self.mutation(token, body=b'{}')[0], 403)
        self.assertEqual(self.mutation(token)[0], 200); self.assertEqual(len(self.calls), 2)

    def test_foreign_token_denied_before_upstream(self):
        self.assertEqual(self.mutation('foreign-canary')[0], 403); self.assertEqual(self.calls, [])

    def test_method_override_header_denied_before_upstream(self):
        token = self.token(); self.assertEqual(self.mutation(token, headers={'X-HTTP-Method-Override': 'DELETE'})[0], 403)
        self.assertEqual(len(self.calls), 1)

    def test_wrong_query_values_denied(self):
        token = self.token()
        self.assertEqual(self.request('graph.fixture.invalid', 'GET', self.policy['routes'][2]['path'] + '?comp=delete', headers={'Authorization': 'Bearer ' + token})[0], 403)
        self.assertEqual(len(self.calls), 1)

    def test_missing_response_is_unknown_and_restart_cannot_retry(self):
        token = self.token(); self.behavior = 'disconnect'
        self.assertEqual(self.mutation(token)[0], 403)
        self.assertEqual(self.journal()[-1], ('policy', 'outcome_unknown', None))
        self.behavior = 'normal'
        restarted = wb.EgressBroker(self.policy, journal=self.root / 'journal.sqlite3', guard=self.guard, upstream=self.upstream)
        response = restarted.handle('login.fixture.invalid', 'POST', self.policy['routes'][0]['path'], {'content-type': 'application/x-www-form-urlencoded'}, self.form)
        token = json.loads(response.body)['access_token']
        with self.assertRaisesRegex(AppError, 'uncertain'):
            restarted.handle('graph.fixture.invalid', 'PUT', self.policy['routes'][1]['path'], {'authorization': 'Bearer ' + token, 'content-type': 'application/json'}, self.body)
        self.assertEqual(len(self.calls), 3)

    def test_redirect_not_followed_and_preserves_uncertainty(self):
        token = self.token(); self.behavior = 'redirect'
        self.assertEqual(self.mutation(token)[0], 403)
        self.assertEqual(len(self.calls), 2); self.assertEqual(self.journal()[-1][1], 'outcome_unknown')

    def test_guard_cancellation_blocks_before_mutation(self):
        token = self.token(); self.active = False
        with self.assertRaises(AppError): self.broker.handle('graph.fixture.invalid', 'PUT', self.policy['routes'][1]['path'], {'authorization': 'Bearer ' + token, 'content-type': 'application/json'}, self.body)
        self.assertEqual(len(self.calls), 1)

    def test_head_preserves_remote_length_without_reading_body(self):
        token = self.token(); status, headers, body = self.request('graph.fixture.invalid', 'HEAD', '/head', headers={'Authorization': 'Bearer ' + token})
        self.assertEqual(status, 200); self.assertEqual(headers['content-length'], '123'); self.assertEqual(body, b'')

    def test_duplicate_header_smuggling_denied(self):
        raw = b'PUT /beta/deviceManagement/configurationPolicies/id HTTP/1.1\r\nHost: graph.fixture.invalid\r\nContent-Length: 0\r\nContent-Length: 4\r\n\r\n'
        self.assertEqual(self.request('graph.fixture.invalid', 'PUT', '/', raw=raw)[0], 403); self.assertEqual(self.calls, [])

    def test_generated_native_state_body_is_checked_before_put_and_cannot_replay(self):
        from plugin_tests.test_azure_backend_r4 import NativeStateWriteTests
        from intune_iac.io import digest
        fixture = NativeStateWriteTests(); fixture.setUp(); contract = fixture.contract()
        value = copy.deepcopy(self.policy)
        backend_client = '00000000-0000-0000-0000-000000000003'
        value['identities']['backend'] = {'tenant_id': self.tenant, 'client_id': backend_client}
        form = urlencode({'client_id': backend_client, 'client_secret': 'synthetic-backend-secret',
            'grant_type': 'client_credentials', 'scope': 'https://storage.azure.com/.default'}).encode()
        oauth = copy.deepcopy(value['routes'][0]); oauth.update(id='backend-token', role='backend', audience='storage', body_sha256=hashlib.sha256(form).hexdigest())
        value['routes'].append(oauth)
        value['routes'].append({'id': 'state', 'host': 'blob.fixture.invalid', 'method': 'PUT',
            'path': '/tfstate/selected.tfstate', 'query': {},
            'headers': {'content-type': 'application/json', 'x-ms-blob-type': 'BlockBlob'},
            'body_sha256': contract.binding()['expected_semantic_sha256'],
            'state_contract_sha256': digest(contract.binding()), 'role': 'backend', 'audience': 'storage',
            'effect': 'state_write', 'max_attempts': 1})
        with self.assertRaises(AppError):
            wb.EgressBroker(value, journal=self.root / 'missing-contract.sqlite3', guard=self.guard, upstream=self.upstream)
        broker = wb.EgressBroker(value, journal=self.root / 'state.sqlite3', guard=self.guard, upstream=self.upstream,
            state_contracts={'state': contract})
        self.server.broker = broker
        status, _, response = self.request('login.fixture.invalid', 'POST', oauth['path'], form,
            {'Content-Type': 'application/x-www-form-urlencoded'})
        self.assertEqual(status, 200); token = json.loads(response)['access_token']
        headers = {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json', 'X-MS-Blob-Type': 'BlockBlob'}
        bad = copy.deepcopy(fixture.expected); bad['resources'][0]['instances'][0]['attributes']['id'] = 'foreign-object'
        self.assertEqual(self.request('blob.fixture.invalid', 'PUT', '/tfstate/selected.tfstate', json.dumps(bad).encode(), headers)[0], 403)
        body = json.dumps(fixture.expected, indent=2).encode()
        self.assertEqual(self.request('blob.fixture.invalid', 'PUT', '/tfstate/selected.tfstate', body, headers)[0], 200)
        self.assertEqual(self.request('blob.fixture.invalid', 'PUT', '/tfstate/selected.tfstate', body, headers)[0], 403)
        self.assertEqual(len(self.calls), 2); self.assertEqual(self.calls[-1][3], body)

    def test_host_held_credentials_replace_only_approved_role_and_never_enter_worker_or_journal(self):
        import pickle
        from intune_iac import identity_binding as ib
        from plugin_tests.test_identity_binding_v5 import config, RecordedServices
        from intune_iac.io import canonical
        provider = ib.ClientSecretHandle('host-only-provider-canary')
        backend = ib.ClientSecretHandle('host-only-backend-canary')
        self.addCleanup(provider.close); self.addCleanup(backend.close)
        binding = ib.bind_laboratory(config(), provider_credential=provider, backend_credential=backend, transport=RecordedServices())
        credentials = wb.broker_credentials(binding=binding, backend_credential=backend, execution_binding_sha256=self.policy['execution_binding_sha256'])
        self.addCleanup(credentials.close)
        value = copy.deepcopy(self.policy); value['identities'] = copy.deepcopy(credentials.identities)
        value['routes'] = []
        forms = {}
        for role, audience in [('provider', 'graph'), ('backend', 'storage')]:
            identity = credentials.identities[role]
            forms[role] = urlencode({'client_id': identity['client_id'], 'client_secret': credentials.placeholders[role],
                'grant_type': 'client_credentials', 'scope': wb._AUDIENCES[audience] + ' openid offline_access profile'}).encode()
            route = copy.deepcopy(self.policy['routes'][0]); route.update(id=role + '-token', role=role, audience=audience,
                path='/' + identity['tenant_id'] + '/oauth2/v2.0/token', body_sha256=hashlib.sha256(forms[role]).hexdigest(),
                headers={'content-type': 'application/x-www-form-urlencoded; charset=utf-8'})
            value['routes'].append(route)
        broker = wb.EgressBroker(value, journal=self.root / 'credential.sqlite3', guard=self.guard, upstream=self.upstream, credentials=credentials)
        self.server.broker = broker
        for route in value['routes']:
            self.assertEqual(self.request('login.fixture.invalid', 'POST', route['path'], forms[route['role']],
                {'Content-Type': 'application/x-www-form-urlencoded; charset=utf-8', 'X-Client-SKU': 'MSAL.Go'})[0], 200)
        observed = [parse_qs(call[3].decode())['client_secret'][0] for call in self.calls]
        self.assertEqual(observed, ['host-only-provider-canary', 'host-only-backend-canary'])
        safe = canonical(value) + canonical(credentials.worker_environment()) + repr(credentials).encode() + (self.root / 'credential.sqlite3').read_bytes()
        for canary in (b'host-only-provider-canary', b'host-only-backend-canary', b'fixture-1', b'fixture-2'):
            self.assertNotIn(canary, safe)
        with self.assertRaises(TypeError): pickle.dumps(credentials)
        credentials.close()
        with self.assertRaises(AppError): credentials.worker_environment()
        self.assertEqual(len(self.calls), 2)

    def test_cancellation_after_upstream_effect_preserves_unknown(self):
        token = self.token(); self.behavior = 'cancel_after_effect'
        self.assertEqual(self.mutation(token)[0], 403)
        self.assertEqual(len(self.calls), 2); self.assertEqual(self.journal()[-1], ('policy', 'outcome_unknown', None))
        self.active = True
        self.assertEqual(self.mutation(token)[0], 403); self.assertEqual(len(self.calls), 2)

    def test_in_memory_policy_change_invalidates_existing_broker(self):
        self.broker.policy['routes'][1]['max_attempts'] = 2
        with self.assertRaises(AppError): self.broker.handle('login.fixture.invalid', 'POST', self.policy['routes'][0]['path'],
            {'content-type': 'application/x-www-form-urlencoded'}, self.form)
        self.assertEqual(self.calls, [])

    def test_response_compression_is_normalized_to_bounded_identity_transport(self):
        status, _, data = self.request('login.fixture.invalid', 'POST', self.policy['routes'][0]['path'], self.form,
            {'Content-Type': 'application/x-www-form-urlencoded', 'Accept-Encoding': 'gzip'})
        self.assertEqual(status, 200); self.assertIn('access_token', json.loads(data))
        self.assertEqual(self.calls[0][2].get('accept-encoding'), 'identity')

    def test_malformed_identity_types_and_foreign_audience_scope_fail_closed(self):
        for key in ('role', 'audience'):
            value = copy.deepcopy(self.policy); value['routes'][0][key] = []
            with self.assertRaises(AppError): wb.validate_policy(value)
        form = self.form.replace(b'graph.microsoft.com', b'storage.azure.com')
        value = copy.deepcopy(self.policy); value['routes'][0]['body_sha256'] = hashlib.sha256(form).hexdigest()
        broker = wb.EgressBroker(value, journal=self.root / 'wrong-scope.sqlite3', guard=self.guard, upstream=self.upstream)
        with self.assertRaises(AppError): broker.handle('login.fixture.invalid', 'POST', value['routes'][0]['path'],
            {'content-type': 'application/x-www-form-urlencoded'}, form)
        self.assertEqual(self.calls, [])

    def test_real_chunked_put_is_decoded_and_forwarded_once_as_exact_bytes(self):
        token = self.token(); body = self.body; split = 11
        chunks = (format(split, 'x').encode() + b'\r\n' + body[:split] + b'\r\n' +
                  format(len(body) - split, 'x').encode() + b'\r\n' + body[split:] + b'\r\n0\r\n\r\n')
        raw = ('PUT ' + self.policy['routes'][1]['path'] + ' HTTP/1.1\r\nHost: graph.fixture.invalid\r\n' +
               'Content-Type: application/json\r\nAuthorization: Bearer ' + token + '\r\nTransfer-Encoding: chunked\r\n\r\n').encode() + chunks
        self.assertEqual(self.request('graph.fixture.invalid', 'PUT', '/', raw=raw)[0], 200)
        self.assertEqual(self.calls[-1][3], self.body)
        self.assertNotIn('transfer-encoding', {k.lower() for k in self.calls[-1][2]})

    def test_chunked_smuggling_extensions_trailers_and_limits_fail(self):
        for headers, data in [({'transfer-encoding': 'chunked', 'content-length': '0'}, b'0\r\n\r\n'),
                ({'transfer-encoding': 'gzip, chunked'}, b'0\r\n\r\n'),
                ({'transfer-encoding': 'chunked'}, b'1;x=y\r\na\r\n0\r\n\r\n'),
                ({'transfer-encoding': 'chunked'}, b'0\r\nX-Trailer: forbidden\r\n\r\n'),
                ({'transfer-encoding': 'chunked'}, b'100001\r\n'),
                ({'transfer-encoding': 'chunked'}, b'1\r\naXX0\r\n\r\n')]:
            with self.subTest(headers=headers, data=data):
                with self.assertRaises(AppError): wb._read_body(io.BytesIO(data), dict(headers))
        self.assertEqual(self.calls, [])

    def install_lease_contract(self):
        value = copy.deepcopy(self.policy); path = '/tfstate/selected.tfstate'
        value['native_lock'] = {'host': 'blob.fixture.invalid', 'path': path}
        client = '00000000-0000-0000-0000-000000000003'
        value['identities']['backend'] = {'tenant_id': self.tenant, 'client_id': client}
        form = urlencode({'client_id': client, 'client_secret': 'synthetic-backend-secret',
            'grant_type': 'client_credentials', 'scope': 'https://storage.azure.com/.default'}).encode()
        oauth = copy.deepcopy(value['routes'][0]); oauth.update(id='backend-token', role='backend', audience='storage', body_sha256=hashlib.sha256(form).hexdigest())
        value['routes'].append(oauth)
        for action in ('acquire', 'renew', 'release', 'set', 'clear'):
            headers = {'x-ms-version': '2026-06-06'}
            dynamic = {'x-ms-lease-id': 'active_native_lease'}
            effect = 'lock_metadata' if action in ('set', 'clear') else 'lease'
            if effect == 'lease': headers['x-ms-lease-action'] = action
            if action == 'acquire':
                headers['x-ms-lease-duration'] = '-1'; dynamic = {'x-ms-proposed-lease-id': 'native_lease_proposal'}
            if action == 'set': dynamic['x-ms-meta-terraformlockid'] = 'native_lock_metadata_apply'
            value['routes'].append({'id': 'native-' + action, 'host': 'blob.fixture.invalid', 'method': 'PUT',
                'path': path, 'query': {'comp': 'metadata' if effect == 'lock_metadata' else 'lease'}, 'headers': headers,
                'dynamic_headers': dynamic, 'body_sha256': hashlib.sha256(b'').hexdigest(),
                'role': 'backend', 'audience': 'storage', 'effect': effect, 'max_attempts': 1})
        self.broker = wb.EgressBroker(value, journal=self.root / 'leased.sqlite3', guard=self.guard, upstream=self.upstream)
        self.server.broker = self.broker
        provider_token = self.token()
        status, _, result = self.request('login.fixture.invalid', 'POST', oauth['path'], form, {'Content-Type': 'application/x-www-form-urlencoded'})
        self.assertEqual(status, 200); backend_token = json.loads(result)['access_token']
        self.lease_id = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'; self.lease_path = path
        return provider_token, backend_token

    def lease_request(self, token, action, *, metadata=None):
        headers = {'Authorization': 'Bearer ' + token, 'X-MS-Version': '2026-06-06'}
        target = self.lease_path + '?comp=' + ('metadata' if action in ('set', 'clear') else 'lease')
        if action == 'acquire': headers.update({'X-MS-Lease-Action': action, 'X-MS-Lease-Duration': '-1', 'X-MS-Proposed-Lease-ID': self.lease_id})
        else:
            headers['X-MS-Lease-ID'] = self.lease_id
            if action in ('renew', 'release'): headers['X-MS-Lease-Action'] = action
        if action == 'set':
            value = metadata or {'ID': self.lease_id, 'Operation': 'OperationTypeApply', 'Info': '', 'Who': '@123456789abc',
                'Version': '1.13.1', 'Created': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
                'Path': 'https://blob.fixture.invalid' + self.lease_path}
            headers['X-MS-Meta-TerraformLockID'] = base64.b64encode(json.dumps(value).encode()).decode()
        return self.request('blob.fixture.invalid', 'PUT', target, headers=headers)

    def test_actual_tls_native_lock_and_metadata_gate_graph_write(self):
        provider, backend = self.install_lease_contract()
        self.assertEqual(self.mutation(provider)[0], 403)
        self.assertEqual(self.lease_request(backend, 'acquire')[0], 201)
        self.assertEqual(self.mutation(provider)[0], 403)
        self.assertEqual(self.lease_request(backend, 'set')[0], 200)
        self.assertEqual(self.mutation(provider)[0], 200)
        self.assertEqual(self.lease_request(backend, 'clear')[0], 200)
        self.assertEqual(self.lease_request(backend, 'release')[0], 200)
        self.assertEqual(self.broker.leases, {})
        self.assertEqual(sum(row[0] == 'PUT' and row[1] == self.policy['routes'][1]['path'] for row in self.calls), 1)

    def test_actual_tls_lease_loss_invalidates_permission_and_durable_next_write(self):
        provider, backend = self.install_lease_contract()
        self.assertEqual(self.lease_request(backend, 'acquire')[0], 201)
        self.assertEqual(self.lease_request(backend, 'set')[0], 200)
        self.behavior = 'lease_failure'
        self.assertEqual(self.lease_request(backend, 'renew')[0], 412)
        before = len(self.calls); self.assertEqual(self.mutation(provider)[0], 403)
        self.assertEqual(len(self.calls), before); self.assertEqual(self.broker.leases, {})
        with sqlite3.connect(self.root / 'leased.sqlite3') as db:
            self.assertEqual(db.execute("SELECT status,response_code FROM attempts WHERE route='native-renew'").fetchone(), ('service_write_not_confirmed', 412))

    def test_native_lease_recovery_facts_survive_reopen_without_release_authority(self):
        provider, backend = self.install_lease_contract()
        self.assertEqual(self.lease_request(backend, 'acquire')[0], 201)
        self.assertEqual(self.lease_request(backend, 'set')[0], 200)
        before = len(self.calls)
        record = self.broker.native_recovery_record()
        self.assertEqual([row['action'] for row in record['entries']], ['acquire', 'metadata_set'])
        self.assertEqual(record['entries'][0]['lease_id'], self.lease_id)
        metadata = json.loads(base64.b64decode(record['entries'][1]['lock_metadata']))
        self.assertEqual(metadata['Operation'], 'OperationTypeApply')
        self.assertEqual(metadata['Path'], 'https://blob.fixture.invalid' + self.lease_path)
        reopened = wb.EgressBroker(self.broker.policy, journal=self.root / 'leased.sqlite3', guard=self.guard, upstream=self.upstream)
        self.assertEqual(reopened.native_recovery_record(), record)
        self.assertEqual(reopened.leases, {})
        self.assertFalse(record['automatic_release_authorized'])
        self.assertEqual(len(self.calls), before)

    def test_uncertain_native_acquire_preserves_proposal_before_dispatch(self):
        provider, backend = self.install_lease_contract(); self.behavior = 'disconnect'
        self.assertEqual(self.lease_request(backend, 'acquire')[0], 403)
        record = self.broker.native_recovery_record()
        self.assertEqual(len(record['entries']), 1)
        self.assertEqual(record['entries'][0]['lease_id'], self.lease_id)
        self.assertEqual(record['entries'][0]['status'], 'outcome_unknown')
        before = len(self.calls); self.behavior = 'normal'
        self.assertEqual(self.lease_request(backend, 'acquire')[0], 403)
        self.assertEqual(len(self.calls), before)

    def test_exact_native_discovery_paths_and_foreign_metadata_rejection(self):
        value = copy.deepcopy(self.policy)
        for name, path, query in [('instance', '/common/discovery/instance', {'api-version': '1.1',
                'authorization_endpoint': 'https://login.fixture.invalid/' + self.tenant + '/oauth2/v2.0/authorize'}),
                ('openid', '/' + self.tenant + '/v2.0/.well-known/openid-configuration', {})]:
            value['routes'].append({'id': name, 'host': 'login.fixture.invalid', 'method': 'GET', 'path': path,
                'query': query, 'headers': {}, 'body_sha256': hashlib.sha256(b'').hexdigest(),
                'role': 'provider', 'audience': 'graph', 'effect': 'discovery', 'max_attempts': 2})
        broker = wb.EgressBroker(value, journal=self.root / 'discovery.sqlite3', guard=self.guard, upstream=self.upstream)
        self.server.broker = broker
        for route in value['routes'][-2:]:
            target = route['path'] + '?' + urlencode(route['query'])
            self.assertEqual(self.request('login.fixture.invalid', 'GET', target)[0], 200)
        self.assertTrue(all('Authorization' not in row[2] for row in self.calls))
        self.behavior = 'foreign_metadata'; route = value['routes'][-2]
        self.assertEqual(self.request('login.fixture.invalid', 'GET', route['path'] + '?' + urlencode(route['query']))[0], 403)

    def test_native_policy_cannot_use_laboratory_transport(self):
        value = copy.deepcopy(self.policy); value['profile'] = 'azure_public_pilot'
        for route in value['routes']:
            route['host'] = 'login.microsoftonline.com' if route['effect'] == 'oauth' else 'graph.microsoft.com'
        with self.assertRaises(AppError): wb.EgressBroker(value, journal=self.root / 'native.sqlite3', guard=self.guard, upstream=self.upstream)
        self.assertFalse((self.root / 'native.sqlite3').exists())

    def test_audience_cannot_send_graph_token_to_storage(self):
        value = copy.deepcopy(self.policy); value['profile'] = 'azure_public_pilot'
        for route in value['routes']:
            route['host'] = 'login.microsoftonline.com' if route['effect'] == 'oauth' else 'account123.blob.core.windows.net'
        with self.assertRaises(AppError): wb.validate_policy(value)

    def test_journal_binding_substitution_denied(self):
        value = copy.deepcopy(self.policy); value['operation_id'] = 'c' * 32
        with self.assertRaises(AppError): wb.EgressBroker(value, journal=self.root / 'journal.sqlite3', guard=self.guard, upstream=self.upstream)

    def test_wrong_peer_uid_denied_without_tls_or_upstream(self):
        self.broker.policy['worker_uid'] = os.geteuid() + 1
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); connection.settimeout(2); connection.connect(str(self.root / 'egress.sock'))
        try:
            connection.sendall(b'CONNECT graph.fixture.invalid:443 HTTP/1.1\r\nHost: graph.fixture.invalid\r\n\r\n')
            self.assertIn(b'403', connection.recv(4096))
        finally: connection.close()
        self.assertEqual(self.calls, [])

    def test_unknown_connect_destination_denied(self):
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); connection.settimeout(2); connection.connect(str(self.root / 'egress.sock'))
        try:
            connection.sendall(b'CONNECT evil.invalid:443 HTTP/1.1\r\nHost: evil.invalid\r\n\r\n')
            self.assertIn(b'403', connection.recv(4096))
        finally: connection.close()
        self.assertEqual(self.calls, [])
