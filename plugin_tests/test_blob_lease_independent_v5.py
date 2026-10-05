"""Independent adversarial lease review: fixture IO only, never Azure authority."""
from dataclasses import replace
import http.client
import json
import queue
import socket
import threading
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs

from intune_iac import blob_lease as bl
from intune_iac import identity_binding as ib
from intune_iac.io import AppError
from plugin_tests.test_identity_binding_v5 import Clock, RecordedServices, config

OWNER_A = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
OWNER_B = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'


class BoundTokenService:
    """Independent token-call budget recorder after fixture identity binding."""
    def __init__(self, clock):
        self.clock, self.initial = clock, RecordedServices()
        self.bound, self.delay, self.calls = False, 0, []

    def __call__(self, request, *, timeout, max_bytes):
        if not self.bound:
            return self.initial(request, timeout=timeout, max_bytes=max_bytes)
        self.calls.append({'request': request, 'timeout': timeout})
        self.clock.now += self.delay
        return ib.ServiceResponse(200, (('content-type', 'application/json'),),
            json.dumps({'token_type': 'Bearer', 'expires_in': 3600,
                        'access_token': 'opaque-independent-fixture-token'}).encode())


class ConcreteBlob:
    """One independently modeled remote owner for a fixed public fixture route."""
    def __init__(self, clock):
        self.clock, self.owner, self.until = clock, None, 0
        self.calls, self.lose_response = [], None
        self.lock = threading.Lock()

    def __call__(self, request, *, timeout, max_bytes):
        with self.lock:
            self.calls.append(request)
            if (request.method, request.host, request.path) != (
                    'PUT', 'recordedstate.blob.core.windows.net', '/tfstate/intune.tfstate?comp=lease'):
                return ib.ServiceResponse(404, (), b'')
            if self.clock() >= self.until:
                self.owner = None
            action = request.headers['x-ms-lease-action']
            if action == 'acquire' and self.owner in (None, request.headers.get('x-ms-proposed-lease-id')):
                self.owner = request.headers['x-ms-proposed-lease-id']
                self.until = self.clock() + 60
                status = 201
            elif action in ('renew', 'release') and self.owner and request.headers.get('x-ms-lease-id') == self.owner:
                status = 200
                if action == 'renew':
                    self.until = self.clock() + 60
                else:
                    self.owner = None
            else:
                return ib.ServiceResponse(409, (), b'')
            if self.lose_response == action:
                raise TimeoutError('fixture response lost after remote operation committed')
            headers = [('x-ms-version', '2023-11-03'), ('content-length', '0')]
            if action != 'release':
                headers.append(('x-ms-lease-id', self.owner))
            return ib.ServiceResponse(status, tuple(headers), b'')


class IndependentLeaseStateTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.tokens = BoundTokenService(self.clock)
        self.provider = ib.ClientSecretHandle('independent-provider-fixture')
        self.backend = ib.ClientSecretHandle('independent-backend-fixture')
        self.binding = ib.bind_laboratory(config(), provider_credential=self.provider,
            backend_credential=self.backend, transport=self.tokens, clock=self.clock, max_age=300)
        self.tokens.bound = True
        self.remote = ConcreteBlob(self.clock)

    def role(self):
        return bl.backend_role_laboratory(self.binding, credential=self.backend,
            transport=self.remote, clock=self.clock, timeout=5)

    def acquire(self, role=None):
        with patch.object(bl.uuid, 'uuid4', return_value=OWNER_A):
            return (role or self.role()).acquire()

    def test_renew_token_exchange_budget_cannot_exceed_remaining_lease(self):
        lease = self.acquire()
        self.clock.now += 56.5  # Conservative local expiry is acquire-start + 58.
        self.tokens.delay = 2
        with self.assertRaises(AppError):
            lease.renew()
        self.assertLessEqual(self.tokens.calls[-1]['timeout'], 1.5)
        self.assertEqual(len(self.remote.calls), 1, 'No lease write may follow expiry during token acquisition')
        self.assertEqual(lease.evidence()['status'], 'lost')

    def test_release_token_exchange_budget_cannot_exceed_remaining_lease(self):
        lease = self.acquire()
        self.clock.now += 57
        self.tokens.delay = 2
        self.assertEqual(lease.release()['status'], 'release_unknown')
        self.assertLessEqual(self.tokens.calls[-1]['timeout'], 1)
        self.assertEqual(len(self.remote.calls), 1)

    def test_successful_remote_acquire_with_lost_response_is_terminal_locally(self):
        role = self.role()
        self.remote.lose_response = 'acquire'
        with self.assertRaises(AppError):
            self.acquire(role)
        self.assertEqual(self.remote.owner, OWNER_A, 'Remote uncertainty is real in this fixture')
        self.assertEqual(role.evidence()['status'], 'acquire_unknown')
        with self.assertRaises(AppError):
            self.acquire(role)
        self.assertEqual(len(self.remote.calls), 1)

    def test_successful_remote_renew_with_lost_response_never_restores_local_authority(self):
        lease = self.acquire()
        self.clock.now += 31
        old_until = self.remote.until
        self.remote.lose_response = 'renew'
        with self.assertRaises(AppError):
            lease.check_active()
        self.assertGreater(self.remote.until, old_until)
        self.assertEqual(lease.evidence()['status'], 'lost')
        self.remote.lose_response = None
        for action in (lease.check_active, lease.renew):
            with self.assertRaises(AppError):
                action()
        self.assertEqual(lease.release()['status'], 'release_unknown')
        self.assertEqual(len(self.remote.calls), 2)

    def test_successful_remote_release_with_lost_response_is_not_retried(self):
        lease = self.acquire()
        self.remote.lose_response = 'release'
        self.assertEqual(lease.release()['status'], 'release_unknown')
        self.assertIsNone(self.remote.owner)
        self.remote.lose_response = None
        self.assertEqual(lease.release()['status'], 'release_unknown')
        self.assertEqual(len(self.remote.calls), 2)

    def test_expired_local_owner_cannot_release_new_remote_owner(self):
        lease = self.acquire()
        self.clock.now += 60
        self.remote.owner, self.remote.until = OWNER_B, self.clock() + 60
        with self.assertRaises(AppError):
            lease.check_active()
        self.assertEqual(lease.release()['status'], 'release_unknown')
        self.assertEqual(self.remote.owner, OWNER_B)
        self.assertEqual(len(self.remote.calls), 1)

    def test_same_role_concurrency_permits_one_acquisition_attempt(self):
        role, barrier, results = self.role(), threading.Barrier(4), []
        def attempt():
            barrier.wait(timeout=1)
            try: results.append(('held', role.acquire()))
            except AppError as exc: results.append(('denied', exc.code))
        workers = [threading.Thread(target=attempt) for _ in range(4)]
        for thread in workers: thread.start()
        for thread in workers: thread.join(timeout=1)
        self.assertTrue(all(not thread.is_alive() for thread in workers))
        self.assertEqual([r[0] for r in results].count('held'), 1)
        self.assertEqual(len(self.remote.calls), 1)
        next(r[1] for r in results if r[0] == 'held').release()

    def test_same_secret_bytes_do_not_substitute_for_bound_credential_handle(self):
        impostor = ib.ClientSecretHandle('independent-backend-fixture')
        for value in (impostor, self.provider, None):
            with self.assertRaises(AppError):
                bl.backend_role_laboratory(self.binding, credential=value,
                    transport=self.remote, clock=self.clock)
        self.assertEqual(self.remote.calls, [])
        self.assertEqual(self.tokens.calls, [])

    def test_storage_token_is_opaque_and_scope_route_are_fixed(self):
        lease = self.acquire()
        call = self.tokens.calls[0]['request']
        fields = parse_qs(call.body.decode())
        self.assertEqual(call.host, 'login.microsoftonline.com')
        self.assertEqual(fields['scope'], ['https://storage.azure.com/.default'])
        self.assertEqual(fields['client_id'], [config().backend_identity.client_id])
        self.assertEqual(self.remote.calls[0].headers['Authorization'], 'Bearer opaque-independent-fixture-token')
        self.assertFalse(lease.evidence()['graph_fencing'])
        self.assertFalse(lease.evidence()['execution_authorized'])
        self.assertEqual(lease.evidence()['live_lease_qualification'], 'BLOCKED')
        with self.assertRaises(AppError):
            bl.require_live_lease(lease, self.binding)
        lease.release()

    def test_cross_origin_backend_configuration_is_rejected_before_io(self):
        wrong = replace(config(), backend=replace(config().backend, blob_endpoint='https://other.example.invalid'))
        calls = len(self.tokens.initial.calls)
        with self.assertRaises(AppError):
            ib.bind_laboratory(wrong, provider_credential=self.provider,
                backend_credential=self.backend, transport=self.tokens, clock=self.clock)
        self.assertEqual(len(self.tokens.initial.calls), calls)
        self.assertEqual(self.remote.calls, [])


class IndependentNativeTransportTests(unittest.TestCase):
    def test_identity_caller_interrupt_cancels_delayed_connect(self):
        entered, resume = threading.Event(), threading.Event()
        sent, workers = [], []
        slots = threading.BoundedSemaphore(4)
        class Connection:
            sock = None
            def __init__(self, *args, **kwargs): workers.append(threading.current_thread())
            def connect(self): entered.set(); resume.wait(1)
            def request(self, *args, **kwargs): sent.append('sent')
            def getresponse(self): raise RuntimeError('fixture response end')
            def close(self): pass
        def interrupt_wait(*args, **kwargs):
            self.assertTrue(entered.wait(1))
            raise KeyboardInterrupt
        with patch.object(ib.http.client, 'HTTPSConnection', Connection), \
                patch.object(ib, '_system_tls_context', return_value=None), \
                patch.object(ib, '_NETWORK_SLOTS', slots), \
                patch.object(ib.queue.Queue, 'get', side_effect=interrupt_wait):
            try:
                with self.assertRaises(KeyboardInterrupt):
                    ib._NativeTransport()(ib._Request('POST', 'synthetic.invalid', '/token', {}, b'fixture-only'), timeout=.03, max_bytes=1)
            finally:
                resume.set()
                for worker in workers:
                    worker.join(1)
                    self.assertFalse(worker.is_alive())
        self.assertEqual(sent, [], 'No credential request may start after caller interruption')
        self.assertEqual(slots._value, 4)

    def test_timeout_cannot_reconnect_and_send_after_caller_returns(self):
        for module, factory in ((ib, ib._NativeTransport), (bl, bl._LeaseTransport)):
            with self.subTest(module=module.__name__):
                entered, resume = threading.Event(), threading.Event()
                events, workers = [], []
                slots = threading.BoundedSemaphore(4)
                class Socket:
                    def sendall(self, data): events.append('send')
                    def shutdown(self, how): events.append('shutdown')
                    def close(self): events.append('socket-close')
                class Connection(http.client.HTTPConnection):
                    def __init__(self, *args, context=None, **kwargs):
                        super().__init__(*args, **kwargs)
                        workers.append(threading.current_thread())
                    def connect(self): events.append('connect'); self.sock = Socket()
                    def request(self, *args, **kwargs):
                        entered.set()
                        resume.wait(1)  # Model preemption immediately before stdlib's send.
                        return super().request(*args, **kwargs)
                    def getresponse(self): raise RuntimeError('fixture response end')
                real_get = queue.Queue.get
                def wait_for_request(q, *args, **kwargs):
                    self.assertTrue(entered.wait(1))
                    return real_get(q, *args, **kwargs)
                with patch.object(module.http.client, 'HTTPSConnection', Connection), \
                        patch.object(ib, '_system_tls_context', return_value=None), \
                        patch.object(module, '_NETWORK_SLOTS', slots), \
                        patch.object(queue.Queue, 'get', wait_for_request):
                    try:
                        with self.assertRaises(AppError):
                            factory()(ib._Request('PUT', 'synthetic.invalid', '/', {'Authorization': 'Bearer fixture-only'}), timeout=.03, max_bytes=1)
                        events.append('caller-returned')
                    finally:
                        resume.set()
                        for worker in workers:
                            worker.join(1)
                            self.assertFalse(worker.is_alive())
                self.assertNotIn('send', events, events)
                self.assertEqual(events.count('connect'), 1, 'A cancelled request cannot establish another connection')
                self.assertEqual(slots._value, 4)

    def test_connection_close_response_cannot_keep_worker_after_deadline(self):
        for module, factory in ((ib, ib._NativeTransport), (bl, bl._LeaseTransport)):
            with self.subTest(module=module.__name__):
                finish = threading.Event()
                producers, workers, connections = [], [], []
                exercised = {'socketpair_created': False, 'response_detached_by_stdlib': False, 'body_read_started': False}
                socketpair_denied = []
                slots = threading.BoundedSemaphore(4)
                class Connection(http.client.HTTPConnection):
                    def __init__(self, *args, context=None, **kwargs):
                        super().__init__(*args, **kwargs)
                        connections.append(self)
                        workers.append(threading.current_thread())
                    def connect(self):
                        try:
                            self.sock, peer = socket.socketpair()
                        except PermissionError as exc:
                            socketpair_denied.append(exc.errno)
                            raise
                        exercised['socketpair_created'] = True
                        self.sock.settimeout(self.timeout)
                        def produce():
                            try:
                                peer.sendall(b'HTTP/1.1 200 OK\r\nConnection: close\r\nContent-Length: 100000\r\n\r\n')
                                while not finish.wait(.003):
                                    peer.sendall(b'x')
                            except OSError:
                                pass
                            finally:
                                peer.close()
                        producer = threading.Thread(target=produce)
                        producers.append(producer)
                        producer.start()
                    def getresponse(self):
                        response = super().getresponse()
                        exercised['response_detached_by_stdlib'] = self.sock is None
                        original_read = response.read
                        def observed_read(*args, **kwargs):
                            exercised['body_read_started'] = True
                            return original_read(*args, **kwargs)
                        response.read = observed_read
                        return response
                with patch.object(module.http.client, 'HTTPSConnection', Connection), \
                        patch.object(ib, '_system_tls_context', return_value=None), \
                        patch.object(module, '_NETWORK_SLOTS', slots):
                    try:
                        with self.assertRaises(AppError):
                            factory()(ib._Request('GET', 'synthetic.invalid', '/', {}), timeout=.03, max_bytes=4096)
                        for worker in workers:
                            worker.join(.04)
                        alive_before_eof = any(worker.is_alive() for worker in workers)
                        sockets_detached = all(conn.sock is None for conn in connections)
                    finally:
                        finish.set()
                        for producer in producers:
                            producer.join(1)
                            self.assertFalse(producer.is_alive())
                        for worker in workers:
                            worker.join(1)
                            self.assertFalse(worker.is_alive())
                if socketpair_denied:
                    self.skipTest('Local socketpair denied by host; detached-response path is not qualified')
                self.assertTrue(all(exercised.values()), 'Native response cleanup fixture did not reach its intended path: '+repr(exercised))
                self.assertTrue(sockets_detached, 'Real stdlib Connection: close detaches conn.sock')
                self.assertFalse(alive_before_eof, 'Worker must not survive caller deadline until peer EOF')
                self.assertEqual(slots._value, 4)


if __name__ == '__main__':
    unittest.main()
