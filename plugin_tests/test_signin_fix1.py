"""Fix round 1 for PKG-SETUP-4 (Sol's review): nine decisions, each with its own tests.

1 collector output schema   2 tenant binding   3 expiry and lifetime   4 display filter   5 two defaults
6 bounded output            7 aggregate status 8 mixed GitHub sessions 9 the capture path sends only GET
Every canary is random per run and never printed; fake az and gh and a fake collecting child stand in for the real ones.
"""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from intune_iac import cli, signin, signin_facts
from intune_iac.io import AppError
from plugin_tests.signin_fakes import FakeClis, TENANT_A, TENANT_B, azure_account, azure_list, github_hosts

ROOT = Path(__file__).resolve().parents[1]
COLLECTOR = str(ROOT / 'plugin_tests' / 'signin_collector.py')
POLICY = '22222222-2222-4222-8222-222222222222'
LISTING = 'account list --output json'
TOKEN_CALL = 'account get-access-token --resource https://graph.microsoft.com --tenant %s --output json'
SEGMENTED = 'AAAAAAAAAAAAAAAAAAAA.BBBBBBBBBBBBBBBBBBBB'  # two runs of 20, joined by a separator: under every old run limit


def canary(slash=False):
    middle = '/' if slash else '-'
    return 'sigcanary' + middle + secrets.token_urlsafe(30) + 'A1'


def token_answer(token, tenant=TENANT_A, expires_in=3600, drop=(), **more):
    value = {'accessToken': token, 'expires_on': int(time.time()) + expires_in, 'expiresOn': '2099-01-01 00:00:00.000000',
             'tenant': tenant, 'tokenType': 'Bearer'}
    value.update(more)
    for name in drop:
        value.pop(name, None)
    return json.dumps(value)


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.box = Path(self.temp.name)
        self.fakes = FakeClis(base=self.box)
        self.output = str(self.box / 'out')
        self.report = self.box / 'report.json'
        self.token = canary()
        self.mode = 'ok'
        self.extra = []
        self.launches = []
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account()))
        self.fakes.answer('az', 'account', 'get-access-token', out=token_answer(self.token))
        self.patch(patch.dict(os.environ, {'PATH': self.fakes.path_entry() + os.pathsep + os.environ.get('PATH', '')}))
        self.patch(patch('intune_iac.signin.collector_command', self.command))
        real = subprocess.Popen
        spy_launches = self.launches

        class Spy(real):
            def __init__(self, argv, *a, **k):
                super().__init__(argv, *a, **k)
                spy_launches.append(self)

        self.patch(patch('intune_iac.signin.subprocess.Popen', Spy))

    def patch(self, patcher):
        patcher.start()
        self.addCleanup(patcher.stop)

    def command(self, tenant, policy, output, descriptor):
        return [sys.executable, '-I', COLLECTOR, str(ROOT), '--token-fd', str(descriptor), '--mode', self.mode,
                '--report', str(self.report)] + self.extra

    def collect(self, **kwargs):
        return signin.collect(TENANT_A, POLICY, self.output, deadline=5, collect_deadline=kwargs.pop('collect_deadline', 20), **kwargs)

    def collectors(self):
        return [p for p in self.launches if p.args and p.args[0] == sys.executable]


class CollectorOutputTests(Base):  # decision 1
    def test_a_json_escaped_token_in_the_collector_output_is_withheld(self):
        self.token = canary(slash=True)
        self.fakes.answer('az', 'account', 'get-access-token', out=token_answer(self.token))
        self.mode = 'escaped'
        result = self.collect()
        self.assertEqual((result['status'], result['error_code']), ('failed', 'collector_output_withheld'))
        self.assertNotIn(self.token, json.dumps(result))
        self.assertNotIn(self.token[:12], json.dumps(result))

    def test_a_token_split_over_two_fields_is_withheld(self):
        self.mode = 'split'
        result = self.collect()
        self.assertEqual((result['status'], result['error_code']), ('failed', 'collector_output_withheld'))
        encoded = json.dumps(result)
        self.assertNotIn(self.token[:10], encoded)
        self.assertNotIn(self.token[-10:], encoded)

    def test_a_plain_echo_and_a_raw_non_json_echo_are_withheld(self):
        for mode in ('echo', 'rawecho'):
            self.mode = mode
            result = self.collect()
            self.assertEqual(result['status'], 'failed', mode)
            self.assertNotIn(self.token, json.dumps(result))

    def test_only_the_allow_listed_fields_are_relayed(self):
        self.mode = 'extra'
        result = self.collect()
        self.assertEqual(result['status'], 'collected')
        shown = result['result']
        self.assertEqual(set(shown), {'status', 'output', 'page_count', 'attempt_count', 'retry_count', 'cancelled', 'coverage'})
        self.assertEqual(shown['output'], self.output)  # the path the product gave, not the child's
        self.assertEqual((shown['status'], shown['page_count'], shown['attempt_count'], shown['retry_count']), ('captured', 3, 3, 0))
        self.assertEqual(shown['coverage'], [{'kind': 'policies', 'coverage': 'complete', 'reason': None}])
        self.assertNotIn('a field the product does not show', json.dumps(result))
        self.assertNotIn('somewhere', json.dumps(result))

    def test_a_result_outside_the_schema_is_refused(self):
        for bad in ({'status': 'captured', 'page_count': 'many'}, {'status': 'weird'}, {'status': 'captured', 'coverage': 'x'}):
            self.assertIsNone(signin.collector_schema(bad), bad)
        self.assertIsNotNone(signin.collector_schema({'status': 'partial', 'page_count': 1, 'attempt_count': 1, 'retry_count': 0,
                                                       'cancelled': False, 'coverage': []}))

    def test_a_credential_problem_is_relayed_as_a_code_only(self):
        value = signin.collector_schema({'status': 'partial', 'page_count': 1, 'attempt_count': 1, 'retry_count': 0,
                                         'cancelled': False, 'coverage': [],
                                         'credential_problem': {'code': 'token_expired', 'message': 'free text',
                                                                'next_step': 'more free text'}})
        self.assertEqual(value['credential_problem'], 'token_expired')
        self.assertNotIn('free text', json.dumps(value))


class TenantBindingTests(Base):  # decision 2
    def test_a_token_response_without_a_tenant_is_malformed(self):
        for answer in (token_answer(self.token, drop=('tenant',)), token_answer(self.token, tenant='not-a-guid'),
                       token_answer(self.token, tenant=7)):
            self.fakes.answer('az', 'account', 'get-access-token', out=answer)
            with self.assertRaises(AppError) as caught:
                signin.obtain_token(TENANT_A, deadline=5)
            self.assertEqual(caught.exception.code, 'signin_token_malformed')
            self.assertNotIn(self.token, str(caught.exception))
        self.assertEqual(self.launches and self.collectors(), [])


class LifetimeTests(Base):  # decision 3
    def test_an_expired_token_is_a_block_with_the_exact_step(self):
        self.fakes.answer('az', 'account', 'get-access-token', out=token_answer(self.token, expires_in=-60))
        with self.assertRaises(signin.SigninBlocked) as caught:
            signin.obtain_token(TENANT_A, deadline=5)
        self.assertEqual(caught.exception.verdict['status'], 'expired')
        self.assertIn('az login --tenant %s' % TENANT_A, caught.exception.verdict['next_step'])

    def test_a_lifetime_beyond_the_maximum_is_refused(self):
        self.assertEqual(signin.MAX_TOKEN_LIFETIME, 7200)
        self.fakes.answer('az', 'account', 'get-access-token', out=token_answer(self.token, expires_in=signin.MAX_TOKEN_LIFETIME + 60))
        with self.assertRaises(AppError) as caught:
            signin.obtain_token(TENANT_A, deadline=5)
        self.assertEqual(caught.exception.code, 'signin_token_lifetime_invalid')
        far = int(time.mktime((2099, 1, 1, 0, 0, 0, 0, 0, 0)))
        self.fakes.answer('az', 'account', 'get-access-token', out=token_answer(self.token, expires_on=far))
        with self.assertRaises(AppError):
            signin.obtain_token(TENANT_A, deadline=5)

    def test_an_absent_or_malformed_expiry_fails_closed_and_the_local_time_string_is_never_used(self):
        cases = (token_answer(self.token, drop=('expires_on',)),  # only the local-time expiresOn string is left
                 token_answer(self.token, expires_on='soon'), token_answer(self.token, expires_on=None),
                 token_answer(self.token, expires_on=True), token_answer(self.token, expires_on=[1]),
                 token_answer(self.token, expires_on=float('nan')))
        for answer in cases:
            self.fakes.answer('az', 'account', 'get-access-token', out=answer)
            with self.assertRaises(AppError) as caught:
                signin.obtain_token(TENANT_A, deadline=5)
            self.assertEqual(caught.exception.code, 'signin_token_malformed', answer[:60])

    def test_a_numeric_string_expiry_in_range_is_accepted(self):
        self.fakes.answer('az', 'account', 'get-access-token', out=token_answer(self.token, expires_on=str(int(time.time()) + 600)))
        value = signin.obtain_token(TENANT_A, deadline=5)
        self.assertEqual(value, self.token)
        self.assertGreater(value.valid_until, time.monotonic())

    def test_a_wall_clock_step_back_after_receipt_never_extends_the_lifetime(self):
        class Clock:
            wall, mono = 1_800_000_000.0, 5000.0

        clock = Clock()
        self.patch(patch('intune_iac.signin._wall', lambda: clock.wall))
        self.patch(patch('intune_iac.signin._mono', lambda: clock.mono))
        self.fakes.answer('az', 'account', 'get-access-token',
                          out=token_answer(self.token, expires_on=int(clock.wall) + 100))

        def delayed(tenant, policy, output, descriptor):
            clock.mono += 500       # the monotonic clock says the token is long expired
            clock.wall -= 100_000   # while the wall clock was stepped far back, which would look like a longer life
            return self.command(tenant, policy, output, descriptor)

        self.patch(patch('intune_iac.signin.collector_command', delayed))
        with self.assertRaises(AppError) as caught:
            self.collect()
        self.assertEqual(caught.exception.code, 'signin_token_expired')
        self.assertEqual(self.collectors(), [])
        self.assertNotIn(self.token, str(caught.exception))

    def test_the_listing_is_not_session_freshness(self):
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account()))
        verdict = signin_facts.evaluate(signin.detect_azure(deadline=5), TENANT_A)
        self.assertIn('session freshness is checked when a token is requested', verdict['message'])
        self.assertNotIn('active', verdict['message'].lower())


class DisplayFilterTests(Base):  # decision 4
    def test_segmented_tokens_are_not_shown_in_any_displayed_field(self):
        for field_name, build in (
                ('account', lambda: azure_list(azure_account(user=SEGMENTED))),
                ('cloud', lambda: azure_list(azure_account(cloud='Aa' + SEGMENTED.replace('.', '')))),
                ('cloud segmented', lambda: azure_list(azure_account(cloud=SEGMENTED))),
        ):
            self.fakes.answer('az', 'account', 'list', out=build())
            facts = signin.detect_azure(deadline=5)
            verdict = signin_facts.evaluate(facts, TENANT_A)
            blob = json.dumps(facts) + json.dumps(verdict)
            self.assertNotIn('BBBBBBBBBB', blob, field_name)
            self.assertNotIn('AAAAAAAAAA', blob, field_name)
            self.assertFalse(verdict['usable'], field_name)

    def test_a_hidden_account_is_shown_as_not_shown_and_is_not_usable(self):
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(user=SEGMENTED)))
        facts = signin.detect_azure(deadline=5)
        self.assertEqual(facts['accounts'][0]['account'], signin_facts.NOT_SHOWN)
        self.assertEqual(signin_facts.NOT_SHOWN, '<not shown>')
        self.assertFalse(signin_facts.evaluate(facts, TENANT_A)['usable'])

    def test_segmented_github_host_and_login_are_hidden(self):
        hosts = {'hosts': {SEGMENTED: [{'state': 'success', 'active': True, 'host': SEGMENTED, 'login': SEGMENTED}]}}
        self.fakes.answer('gh', 'auth', 'status', out=json.dumps(hosts))
        facts = signin.detect_github(deadline=5)
        verdict = signin_facts.evaluate(facts)
        blob = json.dumps(facts) + json.dumps(verdict)
        self.assertNotIn('BBBBBBBBBB', blob)
        self.assertNotIn('AAAAAAAAAA', blob)

    def test_a_segmented_error_code_from_the_collector_is_not_shown(self):
        self.mode, self.extra = 'failcode', ['--code', SEGMENTED]
        result = self.collect()
        self.assertEqual((result['status'], result['error_code']), ('failed', 'collector_failed'))
        self.assertNotIn('BBBBBBBBBB', json.dumps(result))

    def test_plain_names_are_still_shown(self):
        for value, pattern in (('alex@example.test', signin_facts.NAME), ('octo-user', signin_facts.NAME),
                               ('github.com', signin_facts.HOST), ('AzureCloud', signin_facts.CLOUD)):
            self.assertEqual(signin_facts.shown(value, pattern), value)
        self.assertEqual(signin_facts.shown_name('alex@example.test'), 'alex@example.test')
        self.assertEqual(signin_facts.shown_name(SEGMENTED), signin_facts.NOT_SHOWN)
        self.assertEqual(signin_facts.shown_name('eyJhbGciOiJIUzI1NiJ9'), signin_facts.NOT_SHOWN)
        self.assertEqual(signin_facts.shown_cloud('AzureCloud'), 'AzureCloud')
        self.assertEqual(signin_facts.shown_cloud('MadeUpCloud'), signin_facts.NOT_SHOWN)
        self.assertEqual(signin_facts.shown_code('collector_failed'), 'collector_failed')
        self.assertIsNone(signin_facts.shown_code('Mixed.Case-1234567890123456'))


class DefaultAccountTests(Base):  # decision 5
    def test_two_default_entries_are_ambiguous_and_no_token_command_runs(self):
        both = [azure_account(user='alex@example.test'), azure_account(user='sam@example.test')]
        self.fakes.answer('az', 'account', 'list', out=azure_list(*both))
        for account in (None, 'alex@example.test'):
            (self.fakes.directory / 'calls.log').unlink(missing_ok=True)
            result = self.collect(account=account)
            self.assertEqual((result['status'], result['signin']['status']), ('blocked', 'several_accounts'))
            self.assertIn('default', result['signin']['message'])
            self.assertEqual(self.fakes.calls(), [LISTING])
        self.assertEqual(self.collectors(), [])


class BoundedOutputTests(Base):  # decision 6
    def test_an_endless_listing_is_stopped_at_the_ceiling_and_reaped(self):
        self.fakes.flood('az', 'account', 'list')
        started = time.monotonic()
        facts = signin.detect_azure(deadline=30)
        self.assertEqual((facts['state'], facts['reason']), ('unknown', 'output_too_large'))
        self.assertLess(time.monotonic() - started, 15)
        cli_processes = [p for p in self.launches if p.args and str(p.args[0]).endswith('/az')]
        self.assertEqual(len(cli_processes), 1)
        self.assertIsNotNone(cli_processes[0].returncode, 'the process was not reaped')

    def test_an_endless_collector_is_stopped_at_the_ceiling_and_reaped(self):
        self.mode = 'flood'
        started = time.monotonic()
        result = self.collect(collect_deadline=60)
        self.assertEqual((result['status'], result['error_code']), ('failed', 'collector_output_too_large'))
        self.assertLess(time.monotonic() - started, 30)
        self.assertIsNotNone(self.collectors()[0].returncode, 'the collector was not reaped')

    def test_the_deadline_still_kills_and_reaps_a_silent_cli(self):
        self.fakes.answer('az', 'account', 'list', out='[]', sleep=30)
        facts = signin.detect_azure(deadline=0.5)
        self.assertEqual(facts['reason'], 'deadline')
        self.assertIsNotNone([p for p in self.launches if str(p.args[0]).endswith('/az')][0].returncode)


class AggregateTests(Base):  # decision 7
    def test_all_is_ready_only_when_every_provider_is(self):
        self.fakes.answer('gh', 'auth', 'status', out=github_hosts(('github.com', 'octo-user', 'error', True)))
        value = signin.status_report(TENANT_A, None, 'all', 5)
        self.assertEqual(value['azure']['status'], 'signed_in')
        self.assertEqual(value['github']['status'], 'expired')
        self.assertEqual(value['status'], 'blocked')

    def test_all_is_ready_when_both_are_usable(self):
        self.fakes.answer('gh', 'auth', 'status', out=github_hosts(('github.com', 'octo-user', 'success', True)))
        self.assertEqual(signin.status_report(TENANT_A, None, 'all', 5)['status'], 'ready')

    def test_the_cli_exits_two_for_azure_ready_and_github_unknown(self):
        self.fakes.answer('gh', 'auth', 'status', out='{' )
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(['signin', 'status', '--tenant', TENANT_A, '--provider', 'all'])
        self.assertEqual((code, json.loads(out.getvalue())['status']), (2, 'blocked'))


class MixedGithubTests(Base):  # decision 8
    def test_one_success_and_one_error_account_on_a_host_is_ambiguous(self):
        self.fakes.answer('gh', 'auth', 'status', out=github_hosts(('github.com', 'octo-user', 'success', True),
                                                                  ('github.com', 'other-user', 'error', False)))
        verdict = signin_facts.evaluate(signin.detect_github(deadline=5))
        self.assertEqual(verdict['status'], 'several_accounts')
        self.assertIn('octo-user', verdict['message'])
        self.assertIn('other-user', verdict['message'])
        self.assertIn('does not pick', verdict['message'])

    def test_a_hidden_second_account_still_makes_the_host_ambiguous(self):
        hosts = {'hosts': {'github.com': [{'state': 'success', 'active': True, 'host': 'github.com', 'login': 'octo-user'},
                                          {'state': 'error', 'active': False, 'host': 'github.com', 'login': SEGMENTED}]}}
        self.fakes.answer('gh', 'auth', 'status', out=json.dumps(hosts))
        verdict = signin_facts.evaluate(signin.detect_github(deadline=5))
        self.assertEqual(verdict['status'], 'several_accounts')
        self.assertNotIn('BBBBBBBBBB', json.dumps(verdict))


class ReadOnlyCaptureTests(unittest.TestCase):  # decision 9
    def test_the_capture_path_sends_only_get_with_the_delivered_token(self):
        from intune_iac import identity_binding as identity
        tenant, policy = TENANT_A, POLICY
        requests = []

        class Response:
            status = 200

            def getheaders(self):
                return []

            def close(self):
                pass

            def read(self, limit):
                if len(requests) == 1:
                    return b'{"value":[{"id":"' + policy.encode() + b'"}]}'
                return b'{"value":[]}'

        class Connection:
            sock = None

            def __init__(self, host, *, port, timeout, context):
                self.host = host

            def connect(self):
                pass

            def request(self, method, path, *, body, headers):
                requests.append((method, self.host, path, body, headers))

            def getresponse(self):
                return Response()

            def close(self):
                pass

        token = canary()
        read_end, write_end = os.pipe()
        os.write(write_end, token.encode())
        os.close(write_end)
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(identity.http.client, 'HTTPSConnection', Connection), \
                patch.object(identity, '_system_tls_context', return_value=None), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = cli.main(['capture', '--tenant', tenant, '--policy', policy, '--output', str(Path(folder) / 'out'),
                             '--token-fd', str(read_end)])
        self.assertEqual(code, 0)
        self.assertGreaterEqual(len(requests), 3)
        self.assertEqual({r[0] for r in requests}, {'GET'}, 'the capture path sent a method other than GET')
        self.assertTrue(all(r[3] is None for r in requests), 'a request carried a body')
        self.assertTrue(all(r[1] == 'graph.microsoft.com' for r in requests))
        self.assertTrue(all(r[4]['Authorization'] == 'Bearer ' + token for r in requests))

    def test_no_request_in_the_capture_sources_names_a_method_other_than_get(self):
        for name in ('capture.py',):
            source = (ROOT / 'intune_iac' / name).read_text()
            for found in re.findall(r"_Request\(\s*'([A-Za-z]+)'", source):
                self.assertEqual(found, 'GET', name)
            self.assertNotRegex(source, r"'(POST|PUT|PATCH|DELETE)'")


if __name__ == '__main__':
    unittest.main()
