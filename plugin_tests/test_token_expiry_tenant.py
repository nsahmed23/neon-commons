"""Expired access and the wrong tenant, offline: the product stops before any further call and says which.

Claims read from a token are unverified. They are used only to explain a refusal, and nothing beyond the tenant
identifier and the expiry time is ever echoed. Every token here is a fake built in the test.
"""
import base64
import contextlib
import datetime as dt
import io
import json
import os
from pathlib import Path
import secrets
import tempfile
import unittest
from unittest.mock import patch

from intune_iac import cli, target
from plugin_tests import test_target as tt

TENANT = tt.GUID                                   # the tenant the context names
OTHER = '99999999-9999-4999-8999-999999999999'     # a different tenant
POLICY = '22222222-2222-4222-8222-222222222222'
NOW = tt.NOW
PAST = int((NOW - dt.timedelta(hours=2)).timestamp())
FUTURE = int((NOW + dt.timedelta(hours=1)).timestamp())
PAST_TEXT = (NOW - dt.timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M:%SZ')


def b64(value):
    return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b'=').decode()


def fake_jwt(tid=TENANT, exp=FUTURE, **extra):
    claims = {'aud': 'https://graph.microsoft.com', **extra}
    if tid is not None:
        claims['tid'] = tid
    if exp is not None:
        claims['exp'] = exp
    return b64({'alg': 'none', 'typ': 'JWT'}) + '.' + b64(claims) + '.' + b64('signature-' + secrets.token_hex(6))


class ClaimTests(unittest.TestCase):
    def test_claims_are_read_without_verification_and_only_tenant_and_expiry_are_kept(self):
        claims = target.token_claims(fake_jwt(tid=OTHER, exp=PAST, upn='someone', oid='x'))
        self.assertEqual(claims, {'tenant_id': OTHER, 'expires_at': PAST_TEXT})

    def test_anything_unreadable_gives_no_claims_and_never_raises(self):
        for token in ('opaque-token-value', 'a.b.c', 'a.b', '', fake_jwt(tid='not-a-guid', exp='soon'),
                      fake_jwt(tid=None, exp=10 ** 30), 'eyJ.' + b64([1, 2]) + '.sig', 5, None):
            with self.subTest(token=str(token)[:20]):
                claims = target.token_claims(token)
                self.assertEqual(claims, {'tenant_id': None, 'expires_at': None})

    def test_wrong_tenant_is_named_before_expiry_and_matches_ignoring_case(self):
        problem = target.token_problem(fake_jwt(tid=OTHER, exp=PAST), TENANT, NOW)
        self.assertEqual(problem['code'], 'token_wrong_tenant')
        self.assertIsNone(target.token_problem(fake_jwt(tid=TENANT.upper()), TENANT, NOW))
        self.assertIsNone(target.token_problem('opaque-token-value', TENANT, NOW))


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def main(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(argv)
        return code, out.getvalue(), err.getvalue()


class CaptureTests(Base):
    def run_capture(self, token, answers=None):
        """answers: list of (status, body) the fake service gives in turn; default is a good three-collection read."""
        calls = []
        script = list(answers or [])

        def factory(value):
            def get(url, *, timeout):
                calls.append(url)
                if script:
                    status, body = script.pop(0)
                else:
                    status, body = 200, {'value': [] if url.endswith(('/settings', '/assignments')) else [{'id': POLICY}]}
                return status, json.dumps(body).encode(), ()
            return get

        output = self.root / 'out'
        with patch('intune_iac.capture._http_transport', factory), \
                patch('intune_iac.capture._stamp', return_value='2026-09-30T12:00:00Z'), \
                patch.dict(os.environ, {'CAPTURE_TEST_TOKEN': token}):
            code, out, err = self.main(['capture', '--tenant', TENANT, '--policy', POLICY, '--output', str(output),
                                        '--token-env', 'CAPTURE_TEST_TOKEN'])
        return code, out, err, calls, output

    def test_token_for_another_tenant_stops_before_any_call_and_names_both_tenants(self):
        extra = 'upn-' + secrets.token_hex(8)
        token = fake_jwt(tid=OTHER, upn=extra)
        code, out, err, calls, output = self.run_capture(token)
        error = json.loads(err)['error']
        self.assertEqual((code, calls, output.exists()), (3, [], False))
        self.assertEqual(error['code'], 'capture_token_wrong_tenant')
        for part in (f'The token is for tenant {OTHER}', f'while this context names tenant {TENANT}',
                     'unverified', f'Obtain a token for tenant {TENANT}'):
            self.assertIn(part, error['message'])
        for secret in (token, extra):
            self.assertNotIn(secret, out + err)

    def test_expired_token_stops_before_any_call_with_the_expiry_time_and_next_step(self):
        extra = 'upn-' + secrets.token_hex(8)
        code, out, err, calls, output = self.run_capture(fake_jwt(exp=PAST, upn=extra))
        error = json.loads(err)['error']
        self.assertEqual((code, calls, output.exists()), (3, [], False))
        self.assertEqual(error['code'], 'capture_token_expired')
        self.assertIn(PAST_TEXT, error['message'])
        self.assertIn('unverified', error['message'])
        self.assertIn(f'Obtain a new token for tenant {TENANT}', error['message'])
        self.assertNotIn(extra, out + err)

    def test_good_and_opaque_tokens_proceed(self):
        for token in (fake_jwt(), 'opaque-' + secrets.token_hex(12)):
            with self.subTest(token=token[:8]):
                self.setUp()
                code, out, err, calls, output = self.run_capture(token)
                self.assertEqual(code, 0, out + err)
                self.assertEqual(len(calls), 3)

    def test_service_answering_expired_stops_after_that_one_call(self):
        body = {'error': {'code': 'InvalidAuthenticationToken', 'message': 'Access token has expired or is not yet valid.',
                          'innerError': {'client-request-id': 'req-' + secrets.token_hex(4)}}}
        code, out, err, calls, output = self.run_capture(fake_jwt(exp=FUTURE), [(401, body)])
        result = json.loads(out)
        self.assertEqual(len(calls), 1, 'no further call after the service says the token expired')
        self.assertEqual(code, 2)
        self.assertEqual(result['status'], 'partial')
        problem = result['credential_problem']
        self.assertEqual(problem['code'], 'token_expired')
        self.assertIn(f'Obtain a new token for tenant {TENANT}', problem['next_step'])
        self.assertEqual([c['reason'] for c in result['coverage']], ['token_expired'] * 3)
        self.assertNotIn('req-', out + err)

    def test_service_answering_wrong_tenant_stops_after_that_one_call(self):
        body = {'error': {'code': 'InvalidAuthenticationTokenTenant',
                          'message': 'The access token is from the wrong issuer. It must match the tenant.'}}
        code, out, err, calls, output = self.run_capture(fake_jwt(tid=OTHER, exp=FUTURE), [(401, body)])
        # The local check already refuses a token whose own claim names another tenant; use an opaque token to reach
        # the service answer.
        self.assertEqual(calls, [])
        self.setUp()
        code, out, err, calls, output = self.run_capture('opaque-' + secrets.token_hex(12), [(401, body)])
        problem = json.loads(out)['credential_problem']
        self.assertEqual((len(calls), problem['code']), (1, 'token_wrong_tenant'))
        self.assertIn(f'tenant {TENANT}', problem['next_step'])

    def test_an_ordinary_denial_keeps_its_existing_meaning(self):
        body = {'error': {'code': 'Forbidden', 'message': 'Insufficient privileges to complete the operation.'}}
        code, out, err, calls, output = self.run_capture('opaque-' + secrets.token_hex(12), [(403, body)])
        result = json.loads(out)
        self.assertNotIn('credential_problem', result)
        self.assertEqual(result['coverage'][0], {'kind': 'policies', 'coverage': 'access_denied', 'reason': 'access_denied'})


class CollectTests(Base):
    def collect(self, graph_token, management_token, responses=None):
        tt.Connection.responses = tt.CollectionTests.responses(None) if responses is None else responses
        tt.Connection.requests = []
        with patch('intune_iac.target._now', return_value=NOW), \
                patch('intune_iac.target.http.client.HTTPSConnection', tt.Connection):
            return target.collect_azure_observations(tt.fixture(), graph_token=graph_token, management_token=management_token)

    def test_wrong_tenant_graph_token_stops_before_any_connection(self):
        extra = 'upn-' + secrets.token_hex(8)
        result = self.collect(fake_jwt(tid=OTHER, upn=extra), fake_jwt())
        self.assertEqual((result['status'], tt.Connection.requests), ('unavailable', []))
        issue = result['issues'][0]
        self.assertEqual((issue['code'], issue['path']), ('token_wrong_tenant', '/graph_token'))
        self.assertIn(f'The token is for tenant {OTHER}', issue['message'])
        self.assertIn(f'while this context names tenant {TENANT}', issue['message'])
        self.assertIn(f'Obtain a token for tenant {TENANT}', issue['next_step'])
        self.assertNotIn(extra, json.dumps(result))

    def test_expired_management_token_stops_before_any_connection(self):
        result = self.collect(fake_jwt(), fake_jwt(exp=PAST))
        self.assertEqual((result['status'], tt.Connection.requests), ('unavailable', []))
        issue = result['issues'][0]
        self.assertEqual((issue['code'], issue['path']), ('token_expired', '/management_token'))
        self.assertIn(PAST_TEXT, issue['message'])
        self.assertIn(f'Obtain a new token for tenant {TENANT}', issue['next_step'])

    def test_the_service_saying_expired_stops_at_the_first_read(self):
        body = {'error': {'code': 'InvalidAuthenticationToken', 'message': 'Lifetime validation failed, the token is expired.'}}
        result = self.collect('opaque-graph-token', 'opaque-arm-token', [tt.Response(body, status=401)])
        self.assertEqual(len(tt.Connection.requests), 1)
        issue = result['issues'][0]
        self.assertEqual((result['status'], issue['code'], issue['path']), ('unavailable', 'token_expired', '/organization'))
        self.assertIn(f'Obtain a new token for tenant {TENANT}', issue['next_step'])

    def test_the_service_saying_wrong_tenant_stops_at_the_read_that_said_it(self):
        good = tt.CollectionTests.responses(None)[0]
        body = {'error': {'code': 'InvalidAuthenticationTokenTenant', 'message': 'The access token is from the wrong issuer.'}}
        result = self.collect('opaque-graph-token', 'opaque-arm-token', [good, tt.Response(body, status=401)])
        self.assertEqual(len(tt.Connection.requests), 2)
        self.assertEqual((result['issues'][0]['code'], result['issues'][0]['path']), ('token_wrong_tenant', '/subscription'))

    def test_other_failures_keep_their_existing_code(self):
        result = self.collect('opaque-graph-token', 'opaque-arm-token', [tt.Response({}, status=500)])
        self.assertEqual(result['issues'], [{'code': 'service_observation_unavailable', 'path': '/organization'}])
        result = self.collect('opaque-graph-token', 'opaque-arm-token',
                              [tt.Response({'error': {'code': 'Forbidden', 'message': 'no'}}, status=403)])
        self.assertEqual(result['issues'], [{'code': 'service_observation_unavailable', 'path': '/organization'}])

    def test_the_cli_exit_code_for_a_token_problem_is_blocked_not_success(self):
        document = self.root / 'target.json'
        document.write_text(json.dumps(tt.fixture()))
        with patch('intune_iac.target._now', return_value=NOW), \
                patch.dict(os.environ, {'G': fake_jwt(tid=OTHER), 'M': fake_jwt()}):
            code, out, err = self.main(['target', 'collect', '--input', str(document),
                                        '--graph-token-env', 'G', '--management-token-env', 'M'])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out)['issues'][0]['code'], 'token_wrong_tenant')


if __name__ == '__main__':
    unittest.main()
