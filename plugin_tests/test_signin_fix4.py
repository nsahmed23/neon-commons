"""Round 4 for PKG-SETUP-4 (controller decision): hiding a name is a display control, not a usability block.

A name that is merely hidden from display (long, or split by separators) does not stop reuse. Only an unbroken credential
signature does: a JWT prefix, a known token prefix, or 24 or more letters and digits with no separator. The engineer confirms
an account with --account; the product compares it with the listing's raw value internally and never echoes either.
"""
import contextlib
import io
import json
import unittest

from intune_iac import cli, signin, signin_facts
from plugin_tests.signin_fakes import TENANT_A, azure_account, azure_list, github_hosts
from plugin_tests.test_signin_fix1 import Base, LISTING, jwt_token
from plugin_tests.test_signin_fix1 import token_answer

LONG_UPN = 'alexander.morgan@contoso.onmicrosoft.com'  # 36 letters and digits: hidden from display, no signature
OTHER_UPN = 'someone.else.entirely@contoso.onmicrosoft.com'
SOL_SPLIT = 'abcdefghijklmnopqrstuvw@abcdefghijklmnopqrstuvw.abcdefghijklmnopqrstuvwx'  # last label: 24 unbroken letters
SPLIT_NO_RUN = 'abcdefghijklmnopqrstuvw@abcdefghijklmnopqrstuvw.abcdefghijklmnopqrstuvw'  # every run 23: hidden, no signature
NOT_SHOWN_TEXT = 'whose name is not shown here'


def verdict_for(fakes, user, account=None, tenant=TENANT_A, **more):
    fakes.answer('az', 'account', 'list', out=azure_list(azure_account(user=user, **more)))
    return signin_facts.evaluate(signin.detect_azure(deadline=5), tenant, account)


class HiddenNameTests(Base):
    def name_the_account(self, upn):
        """The token names the listed account, as a bindable token must (PKG-SETUP-5B round 2)."""
        self.token = jwt_token('long-upn-canary-0123456789', upn=upn)
        self.fakes.answer('az', 'account', 'get-access-token', out=token_answer(self.token))

    def test_a_realistic_long_upn_is_usable_with_the_name_not_shown_and_the_next_steps_printed(self):
        verdict = verdict_for(self.fakes, LONG_UPN)
        self.assertEqual((verdict['status'], verdict['usable']), ('signed_in', True))
        self.assertIn(NOT_SHOWN_TEXT, verdict['message'])
        # Changed in PKG-SETUP-5C: the one reason that matched, not an alternative a usable name cannot have.
        self.assertIn('(it is longer than this display allows)', verdict['message'])
        self.assertNotIn('shaped like a credential', verdict['message'])
        self.assertIn('az account show --query user.name -o tsv', verdict['next_step'])
        self.assertIn('--account NAME', verdict['next_step'])
        self.assertNotIn('alexander', json.dumps(verdict))
        self.assertNotIn('contoso', json.dumps(verdict))

    def test_collect_works_for_a_long_upn_and_echoes_nothing(self):
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(user=LONG_UPN)))
        self.name_the_account(LONG_UPN)
        result = self.collect()
        self.assertEqual(result['status'], 'collected')
        self.assertNotIn('alexander', json.dumps(result))

    def test_a_matching_account_argument_confirms_it_and_nothing_is_echoed(self):
        verdict = verdict_for(self.fakes, LONG_UPN, account=LONG_UPN)
        self.assertEqual((verdict['status'], verdict['usable']), ('signed_in', True))
        self.assertIn('the account matches', verdict['message'].lower())
        self.assertNotIn('alexander', json.dumps(verdict))
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(user=LONG_UPN)))
        self.name_the_account(LONG_UPN)
        result = self.collect(account=LONG_UPN)
        self.assertEqual(result['status'], 'collected')
        self.assertNotIn('alexander', json.dumps(result))

    def test_a_wrong_account_argument_is_the_mismatch_refusal_and_nothing_is_echoed(self):
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(user=LONG_UPN)))
        result = self.collect(account=OTHER_UPN)
        self.assertEqual((result['status'], result['signin']['status']), ('blocked', 'account_mismatch'))
        blob = json.dumps(result)
        self.assertNotIn('alexander', blob)
        self.assertNotIn('someone', blob)
        self.assertEqual(self.fakes.calls(), [LISTING])
        self.assertEqual(self.collectors(), [])

    def test_the_account_argument_matches_a_shown_name_as_well(self):
        verdict = verdict_for(self.fakes, 'alex@example.test', account='alex@example.test')
        self.assertEqual((verdict['status'], verdict['usable']), ('signed_in', True))
        wrong = signin_facts.evaluate(signin.detect_azure(deadline=5), TENANT_A, 'sam@example.test')
        self.assertEqual((wrong['status'], wrong['usable']), ('account_mismatch', False))
        self.assertNotIn('sam@', json.dumps(wrong))

    def test_sol_split_input_is_hidden_and_blocked_by_the_unbroken_run_rule(self):
        # Its last label is 24 letters with no separator, so the run rule matches: not shown, and blocked.
        verdict = verdict_for(self.fakes, SOL_SPLIT)
        self.assertEqual((verdict['status'], verdict['usable']), ('unknown', False))
        self.assertNotIn('abcdefghij', json.dumps(verdict))

    def test_the_same_split_with_every_run_under_24_is_hidden_and_usable(self):
        verdict = verdict_for(self.fakes, SPLIT_NO_RUN)
        self.assertEqual((verdict['status'], verdict['usable']), ('signed_in', True))
        self.assertIn(NOT_SHOWN_TEXT, verdict['message'])
        self.assertNotIn('abcdefghij', json.dumps(verdict))

    def test_credential_signatures_block_even_when_confirmed_by_the_account_argument(self):
        names = ('a' * 30 + '@contoso.com',          # an unbroken run of 30 letters
                 'Z9' * 15,                           # an unbroken 30-character run
                 'eyJhbGciOiJIUzI1NiJ9.x@contoso.com',  # JWT prefix
                 'ghp_abc1234', 'gho_abc1234', 'ghu_abc1234', 'ghs_abc1234', 'ghr_abc1234', 'github_pat_abc1234')
        for name in names:
            for account in (None, name):
                verdict = verdict_for(self.fakes, name, account=account)
                self.assertEqual((verdict['status'], verdict['usable']), ('unknown', False), name)
                self.assertIn('credential', verdict['message'])
                self.assertNotIn(name, json.dumps(verdict))
                self.assertEqual(signin.detect_azure(deadline=5)['accounts'][0]['account'], signin_facts.NOT_SHOWN, name)

    def test_a_blocked_signature_runs_no_token_command(self):
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(user='ghp_abc1234')))
        result = self.collect()
        self.assertEqual((result['status'], result['signin']['status']), ('blocked', 'unknown'))
        self.assertEqual(self.fakes.calls(), [LISTING])

    def test_two_hidden_accounts_are_still_ambiguous_unless_the_default_is_confirmed(self):
        self.fakes.answer('az', 'account', 'list', out=azure_list(
            azure_account(user=LONG_UPN), azure_account(user=OTHER_UPN, default=False)))
        facts = signin.detect_azure(deadline=5)
        for account, expected in ((None, 'several_accounts'), (OTHER_UPN, 'several_accounts'), (LONG_UPN, 'signed_in')):
            verdict = signin_facts.evaluate(facts, TENANT_A, account)
            self.assertEqual(verdict['status'], expected, account)
            self.assertEqual(verdict['usable'], expected == 'signed_in')
            self.assertNotIn('alexander', json.dumps(verdict))
            self.assertNotIn('someone', json.dumps(verdict))

    def test_the_wrong_tenant_and_unknown_cloud_still_block_a_hidden_name(self):
        self.assertEqual(verdict_for(self.fakes, LONG_UPN, tenant='55555555-5555-4555-8555-555555555555')['status'], 'wrong_tenant')
        hidden_cloud = verdict_for(self.fakes, LONG_UPN, cloud='MadeUpCloud')
        self.assertEqual((hidden_cloud['status'], hidden_cloud['usable']), ('unknown', False))

    def test_the_facts_and_verdicts_carry_no_raw_name_and_no_internal_key(self):
        verdict = verdict_for(self.fakes, LONG_UPN)
        for entry in verdict['signed_in']:
            self.assertEqual(set(entry), {'tenant', 'account', 'cloud', 'default', 'listing_state'})
        self.assertNotIn(LONG_UPN, json.dumps(verdict))


class SurrogateTests(Base):
    def test_an_escaped_lone_surrogate_account_is_a_malformed_answer_not_a_crash(self):
        for name in ('\ud800', 'ok.name@contoso.onmicrosoft.com\udfff'):
            self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(user=name)))
            facts = signin.detect_azure(deadline=5)
            self.assertEqual((facts['state'], facts['reason']), ('unknown', 'malformed_answer'), repr(name))
            self.assertEqual(facts['accounts'], [])

    def test_an_escaped_lone_surrogate_github_login_is_a_malformed_answer_not_a_crash(self):
        for name in ('\ud800', 'octo\udc00user'):
            self.fakes.answer('gh', 'auth', 'status', out=github_hosts(('github.com', name, 'success', True)))
            facts = signin.detect_github(deadline=5)
            self.assertEqual((facts['state'], facts['reason']), ('unknown', 'malformed_answer'), repr(name))

    def test_the_digest_comparison_is_constant_time(self):
        import hmac
        from unittest import mock
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(user=LONG_UPN)))
        facts = signin.detect_azure(deadline=5)
        with mock.patch('intune_iac.signin_facts.hmac.compare_digest', wraps=hmac.compare_digest) as spy:
            self.assertTrue(signin_facts.evaluate(facts, TENANT_A, LONG_UPN)['usable'])
            self.assertFalse(signin_facts.evaluate(facts, TENANT_A, OTHER_UPN)['usable'])
        self.assertEqual(spy.call_count, 2)


class ArgumentTests(Base):
    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = cli.main(list(argv))
            except SystemExit as exit_:
                code = exit_.code
        return code, out.getvalue(), err.getvalue()

    def test_the_cli_accepts_a_long_upn_as_the_account_argument(self):
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(user=LONG_UPN)))
        code, out, err = self.run_cli('signin', 'status', '--tenant', TENANT_A, '--account', LONG_UPN, '--json')
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)['status'], 'ready')
        self.assertNotIn('alexander', out + err)

    def test_the_cli_refuses_a_malformed_account_argument_without_echo(self):
        bad = 'not a name; ' + 'Q' * 40
        code, out, err = self.run_cli('signin', 'status', '--tenant', TENANT_A, '--account', bad)
        self.assertNotEqual(code, 0)
        self.assertNotIn('Q' * 10, out + err)
        self.assertEqual(self.fakes.calls(), [])


class GithubHiddenLoginTests(Base):
    def test_a_long_login_is_not_shown_and_the_gh_command_is_named(self):
        login = 'alexander.morgan.longname1234'
        self.fakes.answer('gh', 'auth', 'status', out=github_hosts(('github.com', login, 'success', True)))
        verdict = signin_facts.evaluate(signin.detect_github(deadline=5))
        self.assertEqual(verdict['status'], 'signed_in')
        self.assertIn(NOT_SHOWN_TEXT, verdict['message'])
        self.assertIn('gh auth status', verdict['next_step'])
        self.assertNotIn('alexander', json.dumps(verdict))

    def test_a_credential_shaped_login_is_unknown_and_not_shown(self):
        self.fakes.answer('gh', 'auth', 'status', out=github_hosts(('github.com', 'ghp_abc1234', 'success', True)))
        verdict = signin_facts.evaluate(signin.detect_github(deadline=5))
        self.assertEqual(verdict['status'], 'unknown')
        self.assertNotIn('ghp_', json.dumps(verdict))


if __name__ == '__main__':
    unittest.main()
