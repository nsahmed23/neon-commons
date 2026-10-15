"""A broker guard names its in-flight check; there is no fallback to the pre-dispatch recheck (PKG-TIME-AUTHZ-C round A, P2-H3).

The recheck before a request is authoritative and judges the approval's window. Once the request has gone out, the window
bounds nothing any more: a response that arrives after the expiry is the response. A guard that names no in-flight check
used to fall back to its recheck, which judged the window after the effect and turned a successful response into an
unknown outcome. Every guard that can dispatch now names a state-only in-flight check (cancellation and revocation), or an
explicit no-op where there is no revocable state.
"""
import os
import sqlite3
import tempfile
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


class InflightGuardTests(unittest.TestCase):
    def setUp(self):
        self.start = int(time.time())
        self.clocks = Clocks(self.start)
        for name, function in (('time', self.clocks.time), ('monotonic', self.clocks.monotonic)):
            patcher = patch.object(time, name, side_effect=function)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.clocks.install_session(self)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
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

    def full_recheck(self):
        """A recheck that judges the approval's window, as a permit's check_active does."""
        if time.monotonic() >= self.clocks.mono_at_start + LIFETIME:
            raise AppError('approval_expired', 'The approval window is over.')

    def upstream_crossing_the_expiry(self, host, method, target, headers, body, *, timeout):
        self.clocks.elapse(LIFETIME + 1)
        return ib.ServiceResponse(200, (('content-type', 'application/json'),),
                                  b'{"token_type": "Bearer", "access_token": "token", "expires_in": 60}')

    def broker(self, guard):
        patcher = patch.object(wb.LaboratoryUpstream, 'request', side_effect=self.upstream_crossing_the_expiry)
        patcher.start()
        self.addCleanup(patcher.stop)
        return wb.EgressBroker(self.policy, journal=self.root / 'journal.sqlite3', guard=guard,
                               upstream=object.__new__(wb.LaboratoryUpstream))

    def request(self, broker):
        return broker.handle('login.fixture.invalid', 'POST', '/' + TENANT + '/oauth2/v2.0/token',
                             {'content-type': 'application/x-www-form-urlencoded'}, self.form)

    def refused(self, call):
        with self.assertRaises(AppError) as raised:
            call()
        return raised.exception

    def attempts(self):
        connection = sqlite3.connect(self.root / 'journal.sqlite3')
        try:
            return connection.execute('SELECT route, status FROM attempts').fetchall()
        finally:
            connection.close()

    def test_a_guard_with_a_full_recheck_cannot_discard_a_response_for_a_closed_window(self):
        self.clocks.mono_at_start = self.clocks.mono
        guard = wb.laboratory_guard(self.policy['execution_binding_sha256'], self.full_recheck, lambda: None)  # state-only
        broker = self.broker(guard)
        response = self.request(broker)
        self.assertEqual(response.status, 200)
        self.assertEqual(self.attempts(), [('token', 'response_received')])
        self.assertIn(self.refused(lambda: self.request(broker)).code, ('broker_expired', 'approval_expired'))  # the next dispatch is judged

    def test_a_guard_cannot_be_built_without_an_inflight_check(self):
        with self.assertRaises(TypeError):
            wb.laboratory_guard(self.policy['execution_binding_sha256'], self.full_recheck)
        with self.assertRaises(AppError) as raised:
            wb.laboratory_guard(self.policy['execution_binding_sha256'], self.full_recheck, None)
        self.assertEqual(raised.exception.code, 'broker_host_guard_required')
        with self.assertRaises(TypeError):
            wb.live_guard(self.policy['execution_binding_sha256'], binding=None, recheck=self.full_recheck)

    def test_the_inflight_check_still_sees_a_cancellation_while_the_request_is_out(self):
        self.clocks.mono_at_start = self.clocks.mono
        state = {'cancelled': False}

        def inflight():
            if state['cancelled']:
                raise AppError('fixture_cancelled', 'Synthetic cancellation.')

        def upstream_then_cancel(*args, **kwargs):
            state['cancelled'] = True
            return ib.ServiceResponse(200, (('content-type', 'application/json'),), b'{}')
        guard = wb.laboratory_guard(self.policy['execution_binding_sha256'], self.full_recheck, inflight)
        broker = self.broker(guard)
        with patch.object(wb.LaboratoryUpstream, 'request', side_effect=upstream_then_cancel):
            error = self.refused(lambda: self.request(broker))
        self.assertEqual(error.code, 'broker_upstream_outcome_unknown')


if __name__ == '__main__':
    unittest.main()
