"""PKG-SETUP-5C finding 2 (round 2): a hidden name records exactly one reason, and only the readable text says it.

The JSON `message` keeps the former wording (a compatibility contract, see test_signin_golden); the one reason that matched is
in the additive keys `rule` and `readable_message`. The reason is the first match in one fixed order, and it names a rule, never
any part of the name.
"""
import json
import unittest

from intune_iac import signin, signin_facts
from plugin_tests.signin_fakes import TENANT_A, TENANT_B, azure_account, azure_list, github_hosts
from plugin_tests.test_signin_fix1 import Base

OLD_TWO_WAY = 'it is longer than this display allows, or shaped like a credential'
LONG_UPN = 'alexander.morgan@contoso.onmicrosoft.com'


def readable(verdict):
    return verdict.get('readable_message', verdict['message'])


class HiddenReasonTests(Base):
    def verdict(self, user, tenant=TENANT_A, **more):
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(user=user, **more)))
        return signin_facts.evaluate(signin.detect_azure(deadline=5), tenant)

    def assert_reason(self, user, phrase, rule, usable=True):
        verdict = self.verdict(user)
        self.assertEqual(verdict['usable'], usable, user)
        self.assertIn('whose name is not shown here (%s)' % phrase, readable(verdict), user)
        self.assertEqual(verdict['rule'], rule, user)
        self.assertNotIn(user, json.dumps(verdict))
        # the JSON message is the former one, two-way wording included
        self.assertIn(OLD_TWO_WAY, verdict['message'])

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
        verdict = self.verdict('a' * 30 + '@contoso.com', tenant=TENANT_B)
        self.assertIn('(it holds an unbroken run of 24 or more letters and digits)', readable(verdict))
        self.assertNotIn('token prefix', readable(verdict))

    def test_a_hidden_github_login_says_its_reason_too(self):
        self.fakes.answer('gh', 'auth', 'status', out=github_hosts(('github.com', 'alexander.morgan.longname1234', 'success', True)))
        verdict = signin_facts.evaluate(signin.detect_github(deadline=5))
        self.assertEqual(verdict['status'], 'signed_in')
        self.assertIn('whose name is not shown here (it is longer than this display allows)', readable(verdict))
        self.assertIn(OLD_TWO_WAY, verdict['message'])
        self.assertNotIn('alexander', json.dumps(verdict))

    def test_facts_from_elsewhere_with_no_recorded_reason_say_it_cannot_be_shown_safely(self):
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(user=LONG_UPN)))
        facts = signin.detect_azure(deadline=5)
        for account in facts['accounts']:
            account.pop('hidden_reasons', None)
        verdict = signin_facts.evaluate(facts, TENANT_A)
        self.assertIn('whose name is not shown here (it cannot be shown safely)', readable(verdict))
        self.assertNotIn('rule', verdict)

    def test_the_private_fields_never_reach_the_verdict(self):
        verdict = self.verdict(LONG_UPN)
        self.assertNotIn('hidden_reasons', json.dumps(verdict))
        self.assertNotIn('digest', json.dumps(verdict))

    def test_a_name_that_is_shown_has_no_additive_keys(self):
        verdict = self.verdict('alex@example.test')
        self.assertFalse({'rule', 'detail_code', 'readable_message'} & set(verdict))


if __name__ == '__main__':
    unittest.main()
