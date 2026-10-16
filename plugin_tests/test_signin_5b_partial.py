"""PKG-SETUP-5B items 1 and 21 (findings 1 and 21): the capture child's partial exit (2) is a result, and its early token refusals are relayed.
The real capture command runs behind a fake transport (no network); no token value is ever printed.
"""
import argparse
import contextlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from intune_iac import cli, signin, signin_facts
from intune_iac.io import AppError
from plugin_tests.signin_5b_common import Base, NIL, RealCaptureBase, jwt
from plugin_tests.signin_fakes import TENANT_A, TENANT_B, azure_account, azure_list
from plugin_tests.test_signin_fix1 import LISTING, POLICY, token_answer


class PartialExitTests(RealCaptureBase):  # item 1
    def test_a_403_from_the_service_is_a_partial_result_with_the_childs_real_exit_code(self):
        result = self.collect()
        self.assertEqual((result['status'], result['child_exit']), ('partial', 2))
        shown = result['result']
        self.assertEqual(shown['status'], 'partial')
        self.assertEqual([c['coverage'] for c in shown['coverage']], ['access_denied'] * 3)
        self.assertEqual([c['reason'] for c in shown['coverage']], ['access_denied'] * 3)
        self.assertNotIn('credential_problem', shown)
        self.assertEqual(shown['output'], self.output)
        self.assertNotIn(self.token, json.dumps(result))

    def test_a_401_expired_reaches_the_user_as_a_credential_problem_with_the_sign_in_step(self):
        self.capture_mode = '401-expired'
        result = self.collect()
        self.assertEqual((result['status'], result['child_exit']), ('partial', 2))
        self.assertEqual(result['result']['credential_problem'], 'token_expired')
        self.assertEqual({c['reason'] for c in result['result']['coverage']}, {'token_expired'})
        self.assertIn('az login --tenant %s' % TENANT_A, result['next_step'])

    def test_a_401_wrong_tenant_reaches_the_user_too(self):
        self.capture_mode = '401-wrong-tenant'
        result = self.collect()
        self.assertEqual((result['status'], result['child_exit']), ('partial', 2))
        self.assertEqual(result['result']['credential_problem'], 'token_wrong_tenant')
        self.assertIn('az login --tenant %s' % TENANT_A, result['next_step'])

    def test_the_folder_the_run_wrote_is_named_and_a_new_one_is_the_retry_step(self):
        result = self.collect()
        self.assertTrue(Path(self.output).is_dir())  # the real capture wrote it; the product removes nothing
        step = result['next_step']
        self.assertIn(self.output, step)
        self.assertIn('intune-iac signin collect --tenant %s --policy %s --output NEW_DIR (a folder that does not exist yet)'
                      % (TENANT_A, POLICY), step)
        self.assertNotIn('rm ', step.replace('perform ', ''))

    def test_the_cli_exits_two_for_a_partial_result_and_prints_it(self):
        out, err = io.StringIO(), io.StringIO()
        with patch('intune_iac.signin.collector_command', self.command), contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err):
            code = cli.main(['signin', 'collect', '--tenant', TENANT_A, '--policy', POLICY, '--output', self.output])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out.getvalue())['status'], 'partial')

    def test_the_status_and_exit_code_must_agree(self):
        watch = signin._Watch('sigcanary-0123456789abcdefghijkl')
        good = {'status': 'partial', 'page_count': 1, 'attempt_count': 1, 'retry_count': 0, 'cancelled': False, 'coverage': []}
        for code, status in ((0, 'partial'), (2, 'captured')):
            out = json.dumps(dict(good, status=status)).encode()
            result = signin._collector_result(code, out, b'', watch, '/o', lambda c, e: {}, 'RERUN', TENANT_A)
            self.assertEqual((result['status'], result['error_code']), ('failed', 'collector_output_invalid'), (code, status))
        ok = signin._collector_result(0, json.dumps(dict(good, status='captured')).encode(), b'', watch, '/o', lambda c, e: {},
                                      'RERUN', TENANT_A)
        self.assertEqual((ok['status'], ok['child_exit']), ('collected', 0))

    def test_other_exit_codes_are_still_failures(self):
        watch = signin._Watch('sigcanary-0123456789abcdefghijkl')
        for code in (1, 3, 4):
            result = signin._collector_result(code, b'', b'', watch, '/o', lambda c, e: {}, 'RERUN', TENANT_A)
            self.assertEqual((result['status'], result['child_exit']), ('failed', code))


class EarlyRefusalTests(RealCaptureBase):  # item 21
    def use(self, token):
        self.token = token
        self.fakes.answer('az', 'account', 'get-access-token', out=token_answer(token))

    def test_a_token_whose_own_claims_say_expired_is_refused_early_and_the_code_is_relayed(self):
        self.use(jwt(tid=TENANT_A, exp=1000))
        result = self.collect()
        self.assertEqual((result['status'], result['error_code']), ('failed', 'capture_token_expired'))
        self.assertEqual(result['child_exit'], 3)

    def test_a_token_whose_own_claims_name_another_tenant_is_refused_early_and_relayed(self):
        self.use(jwt(tid=TENANT_B, exp=4102444800))
        result = self.collect()
        self.assertEqual((result['status'], result['error_code']), ('failed', 'capture_token_wrong_tenant'))

    def test_the_two_codes_are_in_the_closed_set(self):
        for code in ('capture_token_expired', 'capture_token_wrong_tenant'):
            self.assertEqual(signin_facts.shown_code(code), code)


if __name__ == '__main__':
    unittest.main()
