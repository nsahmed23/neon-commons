"""The broker never extends its egress window across a backward clock step (PKG-TIME-AUTHZ-C, worker_broker).

The egress policy expires with the approval it serves (expires_at is the manifest's). The guard judged it on the bare
wall clock: before every request, again after the upstream answered, in the timeout it gave the upstream and in the
accept loop. A clock that stepped back after the window had elapsed made the policy current again, and the timeout it
gave the upstream grew with it.

The broker has no store of its own to latch an expiry in, and it authorizes nothing by itself: the durable judgment is
the one its guard calls on every request (the permit's check_active, see test_service_expiry_latch and
test_adoption_expiry_latch). What belongs here is the local elapsed deadline: the guard arms this process's monotonic
deadline when it first judges the policy, and the window is closed when either the wall clock or that deadline says so.
Admitting a policy (validate_policy) still reads the wall clock alone: there is no earlier record to consult.

Each test drives the public call (EgressBroker.handle, UnixBrokerServer.serve) with injected wall and monotonic clocks;
only the upstream is modeled.
"""
import json
import os
import subprocess
import tempfile
import threading
import time
import unittest
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode

from intune_iac import identity_binding as ib
from intune_iac import worker_broker as wb
from intune_iac.io import AppError
from plugin_tests.test_clock_authority import Clocks

LIFETIME = 300
TENANT = '00000000-0000-0000-0000-000000000001'
CLIENT = '00000000-0000-0000-0000-000000000002'


class BrokerWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.certroot = tempfile.TemporaryDirectory()
        root = Path(cls.certroot.name)
        cls.cert, cls.key = root / 'certificate.pem', root / 'key.pem'
        subprocess.run(['/usr/bin/openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', str(cls.key),
                        '-out', str(cls.cert), '-days', '1', '-subj', '/CN=local-fixture',
                        '-addext', 'subjectAltName=IP:127.0.0.1,DNS:login.fixture.invalid'], check=True, capture_output=True)
        cls.cert.chmod(0o600)
        cls.key.chmod(0o600)

    @classmethod
    def tearDownClass(cls):
        cls.certroot.cleanup()

    def setUp(self):
        self.start = int(time.time())
        self.clocks = Clocks(self.start)
        for name, function in (('time', self.clocks.time), ('monotonic', self.clocks.monotonic)):
            patcher = patch.object(time, name, side_effect=function)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        os.chmod(self.root, 0o700)
        self.form = urlencode({'client_id': CLIENT, 'client_secret': 'synthetic-secret', 'grant_type': 'client_credentials',
                               'scope': 'https://graph.microsoft.com/.default'}).encode()
        self.policy = {'schema_version': 'protected-egress-policy/1.0', 'profile': 'laboratory_tls_fixture',
            'operation_id': 'a' * 32, 'execution_binding_sha256': 'b' * 64, 'expires_at': self.start + LIFETIME,
            'worker_uid': os.geteuid(), 'identities': {'provider': {'tenant_id': TENANT, 'client_id': CLIENT}},
            'routes': [{'id': 'token', 'host': 'login.fixture.invalid', 'method': 'POST',
                        'path': '/' + TENANT + '/oauth2/v2.0/token', 'query': {},
                        'headers': {'content-type': 'application/x-www-form-urlencoded'},
                        'body_sha256': sha256(self.form).hexdigest(), 'role': 'provider', 'audience': 'graph',
                        'effect': 'oauth', 'max_attempts': 30}]}
        self.calls, self.rechecks = [], []
        self.guard = wb.laboratory_guard(self.policy['execution_binding_sha256'], lambda: self.rechecks.append('recheck'), lambda: None)
        upstream = object.__new__(wb.LaboratoryUpstream)
        patcher = patch.object(wb.LaboratoryUpstream, 'request', self.upstream_request)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.broker = wb.EgressBroker(self.policy, journal=self.root / 'journal.sqlite3', guard=self.guard, upstream=upstream)

    def upstream_request(self, host, method, target, headers, body, *, timeout):
        self.calls.append(timeout)
        answer = json.dumps({'token_type': 'Bearer', 'access_token': 'token-%d' % len(self.calls), 'expires_in': 60}).encode()
        return ib.ServiceResponse(200, (('content-type', 'application/json'),), answer)

    def token_request(self):
        return self.broker.handle('login.fixture.invalid', 'POST', '/' + TENANT + '/oauth2/v2.0/token',
                                  {'content-type': 'application/x-www-form-urlencoded'}, self.form)

    def refused(self, call):
        with self.assertRaises(AppError) as raised:
            call()
        return raised.exception

    def attempts(self):
        import sqlite3
        connection = sqlite3.connect(self.root / 'journal.sqlite3')
        try:
            return connection.execute('SELECT route, status FROM attempts').fetchall()
        finally:
            connection.close()

    def test_an_expiry_reached_while_the_request_is_in_flight_does_not_turn_its_response_into_an_unknown_outcome(self):
        # The window bounds when a dispatch may start. Once the request went out, a response that arrives after the
        # expiry is the response: the effect happened, and refusing it would record a fiction.
        crossing = self.upstream_request

        def upstream_crossing_the_expiry(host, method, target, headers, body, *, timeout):
            result = crossing(host, method, target, headers, body, timeout=timeout)
            self.clocks.elapse(LIFETIME + 1)
            return result
        with patch.object(wb.LaboratoryUpstream, 'request', side_effect=upstream_crossing_the_expiry):
            response = self.token_request()
        self.assertEqual(response.status, 200)
        self.assertEqual(self.attempts(), [('token', 'response_received')])
        self.assertEqual(self.refused(self.token_request).code, 'broker_expired')  # the next dispatch is judged and refused

    def test_a_cancellation_while_the_request_is_in_flight_is_still_an_unknown_outcome(self):
        state = {'cancelled': False}

        def recheck():
            if state['cancelled']:
                raise AppError('fixture_cancelled', 'Synthetic cancellation.')
        guard = wb.laboratory_guard(self.policy['execution_binding_sha256'], recheck, recheck)
        broker = wb.EgressBroker(self.policy, journal=self.root / 'other.sqlite3', guard=guard, upstream=object.__new__(wb.LaboratoryUpstream))

        def upstream_then_cancel(host, method, target, headers, body, *, timeout):
            state['cancelled'] = True
            return self.upstream_request(host, method, target, headers, body, timeout=timeout)
        with patch.object(wb.LaboratoryUpstream, 'request', side_effect=upstream_then_cancel):
            error = self.refused(lambda: broker.handle('login.fixture.invalid', 'POST', '/' + TENANT + '/oauth2/v2.0/token',
                                                       {'content-type': 'application/x-www-form-urlencoded'}, self.form))
        self.assertEqual(error.code, 'broker_upstream_outcome_unknown')

    def test_an_open_window_admits_the_request(self):
        self.clocks.elapse(10)
        self.token_request()
        self.assertEqual(len(self.calls), 1)

    def test_a_window_that_elapsed_stays_closed_after_a_backward_step(self):
        self.token_request()  # the guard judges the policy and arms its deadline
        self.calls.clear()
        self.clocks.elapse(LIFETIME + 1)  # the window is over
        self.clocks.step(-100)  # the wall clock now reads 99 seconds before the expiry
        self.assertLess(time.time(), self.policy['expires_at'])
        self.assertEqual(self.refused(self.token_request).code, 'broker_expired')
        self.assertEqual(self.calls, [])

    def test_a_backward_step_never_lengthens_the_timeout_given_to_the_upstream(self):
        self.token_request()
        self.calls.clear()
        self.clocks.elapse(LIFETIME - 4)  # four seconds of the window are left
        self.clocks.step(-100)  # the wall clock claims 104
        self.token_request()
        self.assertEqual(len(self.calls), 1)
        self.assertLessEqual(self.calls[0], 4)

    def test_the_accept_loop_ends_when_the_deadline_passes_with_the_wall_clock_stepped_back(self):
        server = wb.UnixBrokerServer(self.root / 'egress.sock', self.broker, certificate=self.cert, private_key=self.key)
        self.addCleanup(server.close)
        self.clocks.elapse(LIFETIME + 1)
        self.clocks.step(-100)
        thread = threading.Thread(target=server.serve, daemon=True)
        thread.start()
        thread.join(3)
        alive = thread.is_alive()
        server.stop.set()
        thread.join(3)
        self.assertFalse(alive)


if __name__ == '__main__':
    unittest.main()
