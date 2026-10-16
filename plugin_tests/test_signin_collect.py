"""Item 4: the reused sign-in's short-lived token goes to the one collecting child through the descriptor route and nowhere else.

The token is obtained with `az account get-access-token` (a fake az prints a canary), written to a pipe whose read end is the
only descriptor passed to the child, and the write end is closed before the child starts. It is never an argument, never in
the parent or the child environment, never written to a file. The collecting child here is a stand-in that reads the
descriptor with the product's own reader and reports only a digest; the real command line is checked against the parser.
"""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from intune_iac import cli, signin
from intune_iac.io import AppError
from plugin_tests.signin_fakes import FakeClis, TENANT_A, TENANT_B, azure_account, azure_list

REAL_COLLECTOR_COMMAND = getattr(signin, "collector_command", None)  # before any test patches it
ROOT = Path(__file__).resolve().parents[1]
COLLECTOR = str(ROOT / 'plugin_tests' / 'signin_collector.py')
POLICY = '22222222-2222-4222-8222-222222222222'
LISTING = 'account list --output json'
TOKEN_CALL = 'account get-access-token --resource https://graph.microsoft.com --tenant %s --output json'


def canary():
    from plugin_tests.test_signin_fix1 import jwt_token
    return jwt_token('sigcanary-' + secrets.token_urlsafe(36) + 'A1')


def token_answer(token, tenant=TENANT_A):
    return json.dumps({'accessToken': token, 'expires_on': int(time.time()) + 3600, 'expiresOn': '2099-01-01 00:00:00.000000',
                       'tenant': tenant})


def fd_numbers():
    return {int(name) for name in os.listdir('/proc/self/fd')}


class CollectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.tmpbox = Path(self.temp.name)
        self.fakes = FakeClis(base=self.tmpbox)
        self.output = str(self.tmpbox / 'out')
        self.token = canary()
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account()))
        self.fakes.answer('az', 'account', 'get-access-token', out=token_answer(self.token))
        self.mode = 'ok'
        self.launches = []
        env = patch.dict(os.environ, {'PATH': self.fakes.path_entry() + os.pathsep + os.environ.get('PATH', '')})
        env.start()
        self.addCleanup(env.stop)
        command = patch('intune_iac.signin.collector_command', self.collector_command)
        command.start()
        self.addCleanup(command.stop)
        real = signin.subprocess.Popen
        launches = self.launches

        class Spy(real):
            def __init__(self, argv, *a, **kwargs):
                if argv and argv[0] == sys.executable:
                    launches.append((list(argv), kwargs))
                super().__init__(argv, *a, **kwargs)

        spying = patch('intune_iac.signin.subprocess.Popen', Spy)
        spying.start()
        self.addCleanup(spying.stop)
        self.report = self.tmpbox / 'report.json'

    def collector_command(self, tenant, policy, output, descriptor):
        return [sys.executable, '-I', COLLECTOR, str(ROOT), '--token-fd', str(descriptor), '--mode', self.mode,
                '--report', str(self.report)]

    def collect(self, **kwargs):
        return signin.collect(TENANT_A, POLICY, self.output, deadline=5, collect_deadline=20, **kwargs)

    def test_the_child_receives_exactly_the_token_through_the_descriptor(self):
        result = self.collect()
        self.assertEqual(result['status'], 'collected')
        report = json.loads(self.report.read_text())  # the stand-in child writes only a digest and a length
        self.assertEqual(report['received_sha256'], hashlib.sha256(self.token.encode()).hexdigest())
        self.assertEqual(report['length'], len(self.token))
        self.assertEqual((report['token_in_environment'], report['token_in_arguments']), (False, False))
        self.assertNotIn(self.token, json.dumps(result))
        self.assertEqual(self.fakes.calls(), [LISTING, TOKEN_CALL % TENANT_A])

    def test_one_read_only_descriptor_is_passed_and_the_launch_is_scrubbed(self):
        self.collect()
        (argv, kwargs), = self.launches
        self.assertEqual(len(kwargs['pass_fds']), 1)
        self.assertGreaterEqual(kwargs['pass_fds'][0], 3)
        self.assertIn(str(kwargs['pass_fds'][0]), argv)
        self.assertTrue(kwargs['close_fds'])
        self.assertFalse(kwargs.get('shell', False))
        self.assertIs(kwargs['stdin'], signin.subprocess.DEVNULL)
        self.assertLessEqual(set(kwargs['env']), set(signin.ENVIRONMENT_ALLOWED))
        self.assertNotIn(self.token, repr(argv) + repr(kwargs['env']))

    def test_no_descriptor_and_no_file_is_left_behind(self):
        before = fd_numbers()
        with patch.object(tempfile, 'tempdir', str(self.tmpbox / 'scratch')):
            (self.tmpbox / 'scratch').mkdir()
            self.collect()
            self.assertEqual(os.listdir(self.tmpbox / 'scratch'), [])
        self.assertEqual(fd_numbers(), before)
        self.assertFalse(Path(self.output).exists())
        for path in self.tmpbox.rglob('*'):
            if path.is_file() and path.parent != self.fakes.directory:
                self.assertNotIn(self.token.encode(), path.read_bytes(), str(path))
        # The fake az answer file holds the token on purpose (it is the fake's canned output); nothing else may.
        holders = [p for p in self.tmpbox.rglob('*') if p.is_file() and self.token.encode() in p.read_bytes()]
        self.assertEqual(holders, [self.fakes.directory / 'az.account_get-access-token.out'])

    def test_the_parent_environment_is_unchanged(self):
        before = dict(os.environ)
        self.collect()
        self.assertEqual(dict(os.environ), before)

    def test_blocked_sign_ins_start_no_child_and_no_token_command(self):
        cases = {'subscription_expired': azure_list(azure_account(state='Expired')),
                 'wrong_tenant': azure_list(azure_account(tenant=TENANT_B)),
                 'several_accounts': azure_list(azure_account(), azure_account(user='sam@example.test', default=False)),
                 'not_signed_in': '[]'}
        for status, listing in cases.items():
            self.fakes.answer('az', 'account', 'list', out=listing)
            (self.fakes.directory / 'calls.log').unlink(missing_ok=True)
            result = self.collect()
            self.assertEqual((result['status'], result['signin']['status']), ('blocked', status), status)
            self.assertEqual(result['collector_started'], False)
            self.assertTrue(result['signin']['next_step'])
            self.assertEqual(self.fakes.calls(), [LISTING], status)
        self.assertEqual(self.launches, [])

    def test_a_named_account_that_is_the_cli_default_is_used_and_another_is_refused(self):
        self.fakes.answer('az', 'account', 'list', out=azure_list(
            azure_account(), azure_account(user='sam@example.test', default=False)))
        self.assertEqual(self.collect(account='alex@example.test')['status'], 'collected')
        refused = self.collect(account='sam@example.test')
        self.assertEqual((refused['status'], refused['signin']['status']), ('blocked', 'several_accounts'))

    def test_a_failing_collector_reports_a_code_and_never_its_text(self):
        self.mode = 'fail'
        result = self.collect()
        self.assertEqual((result['status'], result['error_code']), ('failed', 'collector_failed'))
        self.assertNotIn(self.token, json.dumps(result))

    def test_a_collector_that_echoes_the_token_has_its_output_withheld(self):
        self.mode = 'echo'
        result = self.collect()
        self.assertEqual((result['status'], result['error_code']), ('failed', 'collector_output_withheld'))
        self.assertNotIn(self.token, json.dumps(result))

    def test_a_collector_past_its_deadline_is_stopped_and_the_descriptor_is_closed(self):
        self.mode = 'sleep'
        before = fd_numbers()
        with self.assertRaises(AppError) as caught:
            signin.collect(TENANT_A, POLICY, self.output, deadline=5, collect_deadline=1)
        self.assertEqual(caught.exception.code, 'signin_collect_deadline')
        self.assertNotIn(self.token, str(caught.exception))
        self.assertEqual(fd_numbers(), before)

    def test_the_real_collector_command_is_accepted_by_the_product_parser(self):
        real = REAL_COLLECTOR_COMMAND(TENANT_A, POLICY, self.output, 7)
        self.assertEqual(real[:2], [sys.executable, '-B'])
        self.assertTrue(Path(real[2]).is_file())
        parsed = cli.parser().parse_args(real[3:])
        self.assertEqual((parsed.command, parsed.tenant, parsed.policy, parsed.output, parsed.token_fd),
                         ('capture', TENANT_A, POLICY, self.output, 7))
        self.assertEqual(real[3:], ['capture', '--tenant', TENANT_A, '--policy', POLICY, '--output', self.output,
                                    '--token-fd', '7'])

    def test_the_cli_runs_collect_and_reports_blocked_with_exit_two(self):
        def run(*argv):
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = cli.main(list(argv))
            return code, out.getvalue(), err.getvalue()

        code, out, _ = run('signin', 'collect', '--tenant', TENANT_A, '--policy', POLICY, '--output', self.output)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)['status'], 'collected')
        self.assertNotIn(self.token, out)
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(tenant=TENANT_B)))
        code, out, _ = run('signin', 'collect', '--tenant', TENANT_A, '--policy', POLICY, '--output', self.output)
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out)['signin']['status'], 'wrong_tenant')

    def test_the_cli_refuses_a_mistyped_policy_without_repeating_it(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
            cli.main(['signin', 'collect', '--tenant', TENANT_A, '--policy', self.token, '--output', self.output])
        self.assertNotIn(self.token, err.getvalue())
        self.assertEqual(self.launches, [])


if __name__ == '__main__':
    unittest.main()
