"""Item 3: expired access gives the exact next step, and no command that needs the token runs.

Fake az on a temporary search path records every call, so the tests assert that `az account get-access-token` was never
started when the listing reports the session expired, and that a refusal at token time (the CLI cannot refresh) is also a
block, with the CLI's own error text never copied into any result.
"""
import contextlib
import io
import json
import os
import unittest
from unittest.mock import patch

from intune_iac import signin
from intune_iac.io import AppError
from plugin_tests import test_readiness as tr
from plugin_tests.signin_fakes import FakeClis, TENANT_A, TENANT_B, azure_account, azure_list

POISON = 'TESTONLY-poison-BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB2'
TOKEN_CALL = 'account get-access-token --resource https://graph.microsoft.com --tenant %s --output json'
LISTING = 'account list --output json'


def token_answer(token, tenant=TENANT_A):
    return json.dumps({'accessToken': token, 'expiresOn': '2099-01-01 00:00:00.000000', 'tenant': tenant,
                       'tokenType': 'Bearer', 'subscription': 's1'})


class ExpiredTests(unittest.TestCase):
    def setUp(self):
        self.fakes = FakeClis()
        self.addCleanup(self.fakes.cleanup)
        patcher = patch.dict(os.environ, {'PATH': self.fakes.path_entry() + os.pathsep + os.environ.get('PATH', '')})
        patcher.start()
        self.addCleanup(patcher.stop)

    def listing(self, **kwargs):
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(**kwargs)))

    def token(self, **kwargs):
        self.fakes.answer('az', 'account', 'get-access-token', **kwargs)

    def cli(self, *argv):
        from intune_iac.cli import main
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_an_expired_listing_blocks_with_the_exact_next_step_and_never_asks_for_a_token(self):
        self.listing(state='Expired')
        self.token(out=token_answer('never-asked'))
        with self.assertRaises(signin.SigninBlocked) as caught:
            signin.obtain_token(TENANT_A, deadline=5)
        verdict = caught.exception.verdict
        self.assertEqual((verdict['status'], verdict['usable']), ('expired', False))
        self.assertEqual(verdict['next_step'], 'Sign in again to the tenant the context names: az login --tenant %s; then run '
                                               'this command again.' % TENANT_A)
        self.assertEqual(self.fakes.calls(), [LISTING])

    def test_status_reports_expired_as_blocked_and_runs_only_the_listing(self):
        self.listing(state='Expired')
        code, out, _ = self.cli('signin', 'status', '--tenant', TENANT_A)
        value = json.loads(out)
        self.assertEqual(code, 2)
        self.assertEqual((value['status'], value['azure']['status']), ('blocked', 'expired'))
        self.assertIn('az login --tenant %s' % TENANT_A, value['azure']['next_step'])
        self.assertEqual(self.fakes.calls(), [LISTING])

    def test_a_token_request_that_says_the_session_expired_is_a_block_and_the_cli_text_is_not_copied(self):
        self.listing()
        self.token(out='', err='AADSTS70043: The refresh token has expired. Please run az login. ' + POISON, code=1)
        with self.assertRaises(signin.SigninBlocked) as caught:
            signin.obtain_token(TENANT_A, deadline=5)
        verdict = caught.exception.verdict
        self.assertEqual(verdict['status'], 'expired')
        self.assertIn('az login --tenant %s' % TENANT_A, verdict['next_step'])
        self.assertNotIn(POISON, json.dumps(verdict) + str(caught.exception))
        self.assertEqual(self.fakes.calls(), [LISTING, TOKEN_CALL % TENANT_A])

    def test_any_other_token_failure_is_a_coded_refusal_without_the_cli_text(self):
        self.listing()
        self.token(out='', err='unexpected ' + POISON, code=1)
        with self.assertRaises(AppError) as caught:
            signin.obtain_token(TENANT_A, deadline=5)
        self.assertEqual(caught.exception.code, 'signin_token_unavailable')
        self.assertNotIn(POISON, str(caught.exception))

    def test_a_slow_token_request_stops_at_the_deadline(self):
        self.listing()
        self.token(out='x', sleep=30)
        with self.assertRaises(AppError) as caught:
            signin.obtain_token(TENANT_A, deadline=0.5)
        self.assertEqual(caught.exception.code, 'signin_token_deadline')

    def test_malformed_token_answers_are_refused_and_never_echoed(self):
        self.listing()
        for text in ('not json ' + POISON, '[]', json.dumps({'accessToken': 7}), json.dumps({'accessToken': 'has space ' + POISON}),
                     json.dumps({'accessToken': 'short'}), json.dumps({'accessToken': 'A' * 5000})):
            self.token(out=text)
            with self.assertRaises(AppError) as caught:
                signin.obtain_token(TENANT_A, deadline=5)
            self.assertEqual(caught.exception.code, 'signin_token_malformed', text[:30])
            self.assertNotIn(POISON, str(caught.exception))

    def test_a_token_for_another_tenant_is_a_wrong_tenant_block(self):
        self.listing()
        self.token(out=token_answer('B' * 40, tenant=TENANT_B))
        with self.assertRaises(signin.SigninBlocked) as caught:
            signin.obtain_token(TENANT_A, deadline=5)
        self.assertEqual(caught.exception.verdict['status'], 'wrong_tenant')
        self.assertIn(TENANT_B, caught.exception.verdict['message'])

    def test_a_usable_sign_in_yields_the_token_through_the_documented_command_only(self):
        self.listing()
        token = 'C' * 20 + '.' + 'D' * 30
        self.token(out=token_answer(token))
        self.assertEqual(signin.obtain_token(TENANT_A, deadline=5), token)
        self.assertEqual(self.fakes.calls(), [LISTING, TOKEN_CALL % TENANT_A])

    def test_a_mistyped_tenant_or_account_is_refused_without_being_repeated(self):
        for flag in ('--tenant', '--account'):
            err = io.StringIO()
            with contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
                from intune_iac.cli import main
                main(['signin', 'status', flag, POISON + '=='])
            self.assertNotIn(POISON, err.getvalue(), flag)
        self.assertEqual(self.fakes.calls(), [])

    def test_the_readiness_row_for_an_expired_sign_in_is_missing_with_the_exact_step(self):
        from intune_iac.readiness import readiness
        facts = {'azure': {'provider': 'azure', 'state': 'expired', 'reason': None, 'accounts': [
            {'tenant': TENANT_A, 'account': 'alex@example.test', 'cloud': 'AzureCloud', 'default': True, 'session': 'expired'}]}}
        value = readiness(tr.survey_of(tr.repository_item(), tr.context_item(tenant=TENANT_A)), tr.host_report(),
                          tr.doctor_report(), signin=facts)
        row = tr.rows_of(value, 'discover')['integration_service']
        self.assertEqual(row['state'], 'missing')
        self.assertIn('expired', ' '.join(row['missing']))
        self.assertIn('az login --tenant %s' % TENANT_A, row['next_action'])


if __name__ == '__main__':
    unittest.main()
