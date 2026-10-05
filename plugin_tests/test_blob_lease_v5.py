"""Recorded Azure lease contract and independent owner-state fixtures; no Azure IO."""
from dataclasses import replace
import pickle
import threading
import time
import unittest
from unittest.mock import patch

from intune_iac import identity_binding as ib
from intune_iac.io import AppError
from plugin_tests.test_identity_binding_v5 import Clock, RecordedServices, config

FIRST = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
SECOND = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'


class OwnerModel:
    """Independent modeled service: one owner for one concrete blob route.

    Statuses/headers below are recorded API-contract fixtures, not live traffic.
    This state machine does not call lease implementation helpers.
    """
    def __init__(self, clock):
        self.clock, self.owner, self.until = clock, None, 0
        self.calls, self.lock, self.mutate = [], threading.Lock(), None

    def __call__(self, request, *, timeout, max_bytes):
        with self.lock:
            self.calls.append(request)
            if self.mutate is not None: return self.mutate(request)
            if request.method != 'PUT' or request.host != 'recordedstate.blob.core.windows.net' or request.path != '/tfstate/intune.tfstate?comp=lease':
                return ib.ServiceResponse(404, (), b'')
            headers = request.headers
            if headers.get('If-Match') not in (None, '"recorded-etag-1"'):
                return ib.ServiceResponse(412, (), b'')
            if self.clock() >= self.until: self.owner = None
            action = headers.get('x-ms-lease-action')
            if action == 'acquire' and self.owner in (None, headers.get('x-ms-proposed-lease-id')):
                self.owner = headers['x-ms-proposed-lease-id']; self.until = self.clock() + 60
                status, identifier = 201, self.owner
            elif action == 'renew' and headers.get('x-ms-lease-id') == self.owner and self.owner is not None:
                self.until = self.clock() + 60; status, identifier = 200, self.owner
            elif action == 'release' and headers.get('x-ms-lease-id') == self.owner and self.owner is not None:
                self.owner = None; status, identifier = 200, None
            else: return ib.ServiceResponse(409, (), b'')
            result = [('x-ms-version', '2023-11-03'), ('etag', '"recorded-etag-1"'), ('content-length', '0')]
            if identifier is not None: result.append(('x-ms-lease-id', identifier))
            return ib.ServiceResponse(status, tuple(result), b'')


class BlobLeaseTests(unittest.TestCase):
    def setUp(self):
        from intune_iac import blob_lease as bl
        self.bl = bl; self.clock = Clock(); self.services = RecordedServices()
        self.provider = ib.ClientSecretHandle('synthetic-provider-secret')
        self.backend = ib.ClientSecretHandle('synthetic-backend-secret')
        self.binding = ib.bind_laboratory(config(), provider_credential=self.provider,
            backend_credential=self.backend, transport=self.services, clock=self.clock)
        # Fresh storage token responses for the subsequent narrow credential API.
        self.services.responses = [(200, {'content-type': 'application/json'},
            {'token_type': 'Bearer', 'expires_in': 3600, 'access_token': 'opaque-lease-storage-token'})]
        self.services.index = 0
        self.model = OwnerModel(self.clock)

    def role(self, **kwargs):
        return self.bl.backend_role_laboratory(self.binding, credential=self.backend,
            transport=self.model, clock=self.clock, **kwargs)

    def acquire(self, role=None, identifier=FIRST):
        with patch.object(self.bl.uuid, 'uuid4', return_value=identifier):
            return (role or self.role()).acquire()

    def test_fixed_api_acquire_renew_release_and_private_identity(self):
        role = self.role(expected_etag='"recorded-etag-1"')
        with self.acquire(role) as lease:
            lease.check_active()
            self.clock.now += 31; lease.check_active()
            self.assertEqual(self.model.owner, FIRST)
        self.assertIsNone(self.model.owner)
        self.assertEqual([r.headers['x-ms-lease-action'] for r in self.model.calls], ['acquire', 'renew', 'release'])
        first, renewal, release = self.model.calls
        self.assertEqual(first.headers['x-ms-lease-duration'], '60')
        self.assertEqual(first.headers['x-ms-proposed-lease-id'], FIRST)
        self.assertEqual(renewal.headers['x-ms-lease-id'], FIRST)
        self.assertEqual(release.headers['x-ms-lease-id'], FIRST)
        self.assertTrue(all(r.headers['x-ms-version'] == '2023-11-03' and r.headers['If-Match'] == '"recorded-etag-1"' for r in self.model.calls))
        self.assertEqual(lease.evidence()['status'], 'released')
        with self.assertRaises(AppError): lease.check_active()

    def test_receipts_and_laboratory_bindings_cannot_mint_live_role(self):
        for value in (self.binding, self.binding.evidence(), {'live': True}):
            with self.subTest(value=type(value)), self.assertRaises(AppError):
                self.bl.backend_role_live(value, credential=self.backend)
        with self.assertRaises(AppError): self.bl.BlobLease(None)
        with self.assertRaises(TypeError): self.bl.backend_role_live(self.binding, credential=self.backend, transport=self.model)

    def test_wrong_credential_no_environment_fallback_and_nonserialization(self):
        with patch.dict('os.environ', {'AZURE_CLIENT_SECRET': 'not-authority'}):
            for credential in (None, self.provider, ib.ClientSecretHandle('synthetic-backend-secret')):
                with self.assertRaises(AppError):
                    self.bl.backend_role_laboratory(self.binding, credential=credential, transport=self.model, clock=self.clock)
        role = self.role(); lease = self.acquire(role)
        for value in (role, lease):
            with self.assertRaises(TypeError): pickle.dumps(value)
            self.assertNotIn(FIRST, repr(value))
        text = str(lease.evidence())
        for secret in (FIRST, 'opaque-lease-storage-token', 'synthetic-backend-secret'):
            self.assertNotIn(secret, text)
        lease.release()

    def test_two_owners_same_blob_conflict_and_first_remains_active(self):
        first = self.acquire()
        with self.assertRaises(AppError): self.acquire(identifier=SECOND)
        first.check_active(); self.assertEqual(self.model.owner, FIRST)
        self.assertEqual(first.release()['status'], 'released')

    def test_mismatched_response_id_rejects_and_role_never_reacquires(self):
        role = self.role()
        self.model.mutate = lambda _: ib.ServiceResponse(201, (('x-ms-lease-id', SECOND), ('x-ms-version', '2023-11-03')), b'')
        with self.assertRaises(AppError): self.acquire(role)
        with self.assertRaises(AppError): self.acquire(role)
        self.assertEqual(len(self.model.calls), 1)
        self.assertEqual(role.evidence()['status'], 'acquire_unknown')

    def test_response_loss_on_renew_permanently_loses_capability(self):
        lease = self.acquire(); self.clock.now += 31
        def lost(_): raise TimeoutError('sensitive server detail')
        self.model.mutate = lost
        with self.assertRaises(AppError): lease.check_active()
        count = len(self.model.calls)
        with self.assertRaises(AppError): lease.check_active()
        self.assertEqual(lease.release()['status'], 'release_unknown')
        self.assertEqual(len(self.model.calls), count)

    def test_expiry_before_and_during_renew_and_clock_rollback(self):
        for variant in ('before', 'during', 'rollback'):
            with self.subTest(variant=variant):
                self.setUp(); lease = self.acquire()
                if variant == 'before': self.clock.now += 60
                elif variant == 'rollback': self.clock.now -= 1
                else:
                    self.clock.now += 31
                    def delayed(_):
                        self.clock.now += 30
                        return ib.ServiceResponse(200, (('x-ms-lease-id', FIRST), ('x-ms-version', '2023-11-03')), b'')
                    self.model.mutate = delayed
                with self.assertRaises(AppError): lease.check_active()
                self.assertEqual(lease.evidence()['status'], 'lost')

    def test_long_acquire_response_never_creates_active_lease(self):
        role = self.role(timeout=2)
        def delayed(_):
            self.clock.now += 3
            return ib.ServiceResponse(201, (('x-ms-lease-id', FIRST), ('x-ms-version', '2023-11-03')), b'')
        self.model.mutate = delayed
        with self.assertRaises(AppError): self.acquire(role)
        self.assertEqual(role.evidence()['status'], 'acquire_unknown')

    def test_redirect_denial_duplicate_headers_encoding_and_large_body(self):
        responses = [ib.ServiceResponse(s, (), b'') for s in (301, 307, 401, 403, 409, 412, 500)]
        responses += [ib.ServiceResponse(201, (('x-ms-lease-id', FIRST), ('X-MS-LEASE-ID', FIRST)), b''),
                      ib.ServiceResponse(201, (('content-encoding', 'gzip'),), b'x'),
                      ib.ServiceResponse(201, (), b'x'*4097)]
        for response in responses:
            with self.subTest(response=response):
                role = self.role(); self.model.mutate = lambda _, response=response: response
                with self.assertRaises(AppError): self.acquire(role)

    def test_etag_mutation_during_renew_and_bad_conditions_fail_closed(self):
        for tag in ('*', 'W/"weak"', '"bad\r\nheader"'):
            with self.assertRaises(AppError): self.role(expected_etag=tag)
        lease = self.acquire(self.role(expected_etag='"recorded-etag-1"'))
        self.model.mutate = lambda _: ib.ServiceResponse(200, (('x-ms-lease-id', FIRST), ('x-ms-version', '2023-11-03'), ('etag', '"changed"')), b'')
        with self.assertRaises(AppError): lease.renew()
        self.assertEqual(lease.evidence()['status'], 'lost')

    def test_closed_identity_invalidates_without_network_and_release_unknown(self):
        lease = self.acquire(); before = len(self.model.calls); self.backend.close()
        with self.assertRaises(AppError): lease.check_active()
        self.assertEqual(len(self.model.calls), before)
        self.assertEqual(lease.release()['status'], 'release_unknown')

    def test_release_lost_response_cancellation_and_repeated_release_no_retry(self):
        lease = self.acquire()
        def lost(_): raise KeyboardInterrupt()
        self.model.mutate = lost
        self.assertEqual(lease.release()['status'], 'release_unknown')
        self.assertEqual(lease.release()['status'], 'release_unknown')
        self.assertEqual(len(self.model.calls), 2)
        with self.assertRaises(AppError): lease.check_active()

    def test_context_exception_is_not_suppressed_and_releases_only_owner(self):
        lease = self.acquire()
        with self.assertRaisesRegex(RuntimeError, 'caller interrupted'):
            with lease: raise RuntimeError('caller interrupted')
        self.assertEqual(self.model.calls[-1].headers['x-ms-lease-action'], 'release')
        self.assertEqual(self.model.calls[-1].headers['x-ms-lease-id'], FIRST)
        self.assertIsNone(self.model.owner)

    def test_no_renew_after_release_preserves_terminal_receipt(self):
        lease = self.acquire(); lease.release(); count = len(self.model.calls)
        with self.assertRaises(AppError): lease.renew()
        self.assertEqual(lease.evidence()['status'], 'released')
        self.assertEqual(len(self.model.calls), count)

    def test_two_concurrent_acquisitions_have_one_independent_model_owner(self):
        roles = [self.role(), self.role()]; barrier = threading.Barrier(2); outcomes = []
        def acquire(role):
            barrier.wait()
            try: outcomes.append(role.acquire())
            except AppError: outcomes.append(None)
        threads = [threading.Thread(target=acquire, args=(r,)) for r in roles]
        for thread in threads: thread.start()
        for thread in threads: thread.join(2); self.assertFalse(thread.is_alive())
        leases = [v for v in outcomes if v is not None]
        self.assertEqual(len(leases), 1); leases[0].check_active(); leases[0].release()

    def test_wrong_blob_binding_and_forked_process_cannot_use_handle(self):
        lease = self.acquire()
        with self.assertRaises(AppError): lease.check_active('f'*64)
        self.assertEqual(lease.evidence()['status'], 'lost')
        self.setUp(); lease = self.acquire(); count = len(self.model.calls)
        with patch.object(self.bl.os, 'getpid', return_value=-1), self.assertRaises(AppError): lease.check_active()
        self.assertEqual(len(self.model.calls), count)

    def test_identity_lost_during_acquire_never_becomes_capability(self):
        role = self.role()
        def changed(_):
            self.backend.close()
            return ib.ServiceResponse(201, (('x-ms-version', '2023-11-03'), ('x-ms-lease-id', FIRST)), b'')
        self.model.mutate = changed
        with self.assertRaises(AppError): self.acquire(role)
        self.assertEqual(role.evidence()['status'], 'acquire_unknown')

    def test_native_transport_mock_uses_only_fixed_https_without_proxy(self):
        calls = []
        class Connection:
            sock = None
            def __init__(self, host, *, port, timeout, context): calls.append(('connect-config', host, port, timeout))
            def connect(self): pass
            def request(self, method, path, *, body, headers): calls.append(('request', method, path, body, headers))
            def getresponse(self): return self
            status = 201
            def getheaders(self): return [('x-ms-version', '2023-11-03'), ('x-ms-lease-id', FIRST), ('content-length', '0')]
            def read(self, limit): calls.append(('read-limit', limit)); return b''
            def close(self): pass
        with patch.dict('os.environ', {'HTTPS_PROXY': 'https://attacker.invalid', 'AZURE_CLIENT_SECRET': 'ambient-not-used'}), \
             patch.object(self.bl.http.client, 'HTTPSConnection', Connection):
            role = self.bl.backend_role_laboratory(self.binding, credential=self.backend,
                transport=self.bl._LeaseTransport(), clock=self.clock)
            lease = self.acquire(role)
        self.assertEqual(calls[0][1:3], ('recordedstate.blob.core.windows.net', 443))
        self.assertEqual(calls[1][1:4], ('PUT', '/tfstate/intune.tfstate?comp=lease', b''))
        self.assertEqual(calls[2], ('read-limit', 4097))
        self.assertFalse(lease.evidence()['execution_authorized'])

    def test_native_transport_dns_timeout_cancels_before_credentials_send(self):
        sent, finished = [], threading.Event()
        class Connection:
            sock = None
            def __init__(self, *a, **kw): pass
            def connect(self): time.sleep(0.08)
            def request(self, *a, **kw): sent.append(True)
            def close(self): finished.set()
        request = ib._Request('PUT', 'recordedstate.blob.core.windows.net', '/tfstate/intune.tfstate?comp=lease', {})
        with patch.object(self.bl.http.client, 'HTTPSConnection', Connection):
            with self.assertRaises(AppError): self.bl._LeaseTransport()(request, timeout=0.01, max_bytes=4096)
            time.sleep(0.12)
        self.assertTrue(finished.is_set()); self.assertEqual(sent, [])

    def test_native_transport_cancellation_does_not_leave_sender_enabled(self):
        gate, finished, sent = threading.Event(), threading.Event(), []
        class Connection:
            sock = None
            def __init__(self, *a, **kw): pass
            def connect(self): gate.wait(0.3)
            def request(self, *a, **kw): sent.append(True)
            def close(self): gate.set(); finished.set()
        request = ib._Request('PUT', 'recordedstate.blob.core.windows.net', '/tfstate/intune.tfstate?comp=lease', {})
        with patch.object(self.bl.http.client, 'HTTPSConnection', Connection), \
             patch.object(self.bl.queue.Queue, 'get', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): self.bl._LeaseTransport()(request, timeout=0.1, max_bytes=4096)
            gate.set(); time.sleep(0.05)
        self.assertEqual(sent, [])


if __name__ == '__main__': unittest.main()
