"""PKG-SETUP-5C finding 2 (round 3): a hidden name has one reason, said only in the text presentation.

The verdict (what --json prints) keeps the former wording, two-way text included; the reason that matched is in
signin_facts.evaluate_with_presentation, which only the text view uses. It names a rule, never any part of the name.
"""
import json
import unittest

from intune_iac import signin, signin_facts
from plugin_tests.signin_fakes import TENANT_A, TENANT_B, azure_account, azure_list, github_hosts
from plugin_tests.test_signin_fix1 import Base

OLD_TWO_WAY = 'it is longer than this display allows, or shaped like a credential'
LONG_UPN = 'alexander.morgan@contoso.onmicrosoft.com'
CANONICAL = {'provider', 'status', 'usable', 'tenant_wanted', 'signed_in', 'message', 'next_step'}


class HiddenReasonTests(Base):
    def verdict(self, user, tenant=TENANT_A, **more):
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(user=user, **more)))
        return signin_facts.evaluate_with_presentation(signin.detect_azure(deadline=5), tenant)

    def assert_reason(self, user, phrase, rule, usable=True):
        verdict, shown = self.verdict(user)
        self.assertEqual(verdict['usable'], usable, user)
        self.assertIn('whose name is not shown here (%s)' % phrase, shown['sentence'], user)
        self.assertEqual(shown['rule'], rule, user)
        self.assertNotIn(user, json.dumps(verdict) + json.dumps(shown))
        # the verdict itself is the former one, two-way wording included, and has no other key
        self.assertIn(OLD_TWO_WAY, verdict['message'])
        self.assertEqual(set(verdict), CANONICAL)

    def test_a_usable_long_name_says_only_that_it_is_too_long(self):
        self.assert_reason(LONG_UPN, 'it is longer than this display allows', 'length')

    def test_a_name_with_a_credential_word_says_that_and_is_still_usable(self):
        self.assert_reason('alex.password@example.test', 'it contains a word that credentials carry', 'credential_word')

    def test_a_name_with_characters_outside_the_plain_set_says_that(self):
        self.assert_reason('alex müller@example.test', 'it has characters this display does not allow', 'shape')

    def test_a_block_of_capitals_and_digits_says_that(self):
        self.assert_reason('ABCDEF1234567', 'it is a block of 12 or more capitals and digits, which looks like a key', 'caps_block')

    def test_a_name_over_64_characters_with_short_pieces_says_it_is_too_long(self):
        self.assert_reason('.'.join(['ab'] * 25) + '@example.test', 'it is longer than this display allows', 'length')

    def test_an_unbroken_run_without_a_prefix_names_the_run(self):
        _, shown = self.verdict('a' * 30 + '@contoso.com', tenant=TENANT_B)
        self.assertIn('(it holds an unbroken run of 24 or more letters and digits)', shown['sentence'])
        self.assertNotIn('token prefix', shown['sentence'])

    def test_a_hidden_github_login_says_its_reason_too(self):
        self.fakes.answer('gh', 'auth', 'status', out=github_hosts(('github.com', 'alexander.morgan.longname1234', 'success', True)))
        verdict, shown = signin_facts.evaluate_with_presentation(signin.detect_github(deadline=5))
        self.assertEqual(verdict['status'], 'signed_in')
        self.assertIn('whose name is not shown here (it is longer than this display allows)', shown['sentence'])
        self.assertIn(OLD_TWO_WAY, verdict['message'])
        self.assertNotIn('alexander', json.dumps(verdict))

    def test_facts_from_elsewhere_with_no_recorded_reason_say_it_cannot_be_shown_safely(self):
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(user=LONG_UPN)))
        facts = signin.detect_azure(deadline=5)
        for account in facts['accounts']:
            account.pop('hidden_reasons', None)
        _, shown = signin_facts.evaluate_with_presentation(facts, TENANT_A)
        self.assertIn('whose name is not shown here (it cannot be shown safely)', shown['sentence'])
        self.assertIsNone(shown['rule'])

    def test_several_hidden_names_each_get_their_own_reason_and_no_single_rule(self):
        self.fakes.answer('az', 'account', 'list', out=azure_list(
            azure_account(user=LONG_UPN), azure_account(user='alex.password@example.test', default=False)))
        verdict, shown = signin_facts.evaluate_with_presentation(signin.detect_azure(deadline=5), TENANT_A)
        self.assertEqual(verdict['status'], 'several_accounts')
        self.assertIn('(it is longer than this display allows)', shown['sentence'])
        self.assertIn('(it contains a word that credentials carry)', shown['sentence'])
        self.assertIsNone(shown['rule'])
        self.assertEqual(verdict['message'].count(OLD_TWO_WAY), 2)

    def test_the_private_fields_never_reach_the_verdict(self):
        verdict, _ = self.verdict(LONG_UPN)
        self.assertNotIn('hidden_reasons', json.dumps(verdict))
        self.assertNotIn('digest', json.dumps(verdict))

    def test_a_name_that_is_shown_has_nothing_to_present(self):
        _, shown = self.verdict('alex@example.test')
        self.assertEqual((shown['code'], shown['rule']), (None, None))


if __name__ == '__main__':
    unittest.main()
