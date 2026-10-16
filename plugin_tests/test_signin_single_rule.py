"""PKG-SETUP-5C round 2, item 2: a hidden name records exactly one reason (the first match in one fixed order) and says only that.

Sol's inputs: ghp_ followed by 24 alphanumerics matched both signature rules, and ABCDEF123456! matched both the odd-characters
rule and the capitals block. The fixed order is token_prefix, unbroken_run (the usability judge), then shape, length, caps_block,
credential_word (shown_name's own order).
"""
import unittest

from intune_iac import signin, signin_facts
from plugin_tests.signin_fakes import TENANT_A, TENANT_B, azure_account, azure_list
from plugin_tests.test_signin_fix1 import Base


def readable(verdict):
    return verdict.get('readable_message', verdict['message'])


class SingleRuleTests(Base):
    def facts(self, user):
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(user=user)))
        return signin.detect_azure(deadline=5)

    def test_hiding_reasons_are_a_list_of_exactly_one_for_the_two_review_inputs(self):
        self.assertEqual(self.facts('ghp_' + 'A' * 24)['accounts'][0]['hidden_reasons'], ['token_prefix'])
        self.assertEqual(self.facts('ABCDEF123456!')['accounts'][0]['hidden_reasons'], ['shape'])

    def test_a_token_prefix_followed_by_a_long_run_says_only_the_token_prefix(self):
        for name in ('ghp_' + 'a1' * 12, 'ghp_' + 'A' * 24):
            verdict = signin_facts.evaluate(self.facts(name), TENANT_B)
            self.assertEqual(verdict['status'], 'wrong_tenant')
            self.assertIn('whose name is not shown here (it starts with a token prefix)', readable(verdict), name)
            self.assertNotIn('unbroken', readable(verdict), name)
            self.assertNotIn(' and it ', readable(verdict), name)

    def test_odd_characters_with_a_capitals_block_say_only_the_odd_characters(self):
        verdict = signin_facts.evaluate(self.facts('ABCDEF123456!'), TENANT_A)
        self.assertEqual(verdict['rule'], 'shape')
        self.assertIn('whose name is not shown here (it has characters this display does not allow)', readable(verdict))
        self.assertNotIn('capitals', readable(verdict))

    def test_a_credential_signature_blocked_message_names_one_rule(self):
        verdict = signin_facts.evaluate(self.facts('ghp_' + 'a1' * 12), TENANT_A)
        self.assertEqual((verdict['status'], verdict['rule']), ('unknown', 'token_prefix'))
        self.assertIn('(it starts with a token prefix)', verdict['readable_message'])
        self.assertNotIn('unbroken', verdict['readable_message'])

    def test_a_verdict_never_joins_two_rules_with_and(self):
        for name in ('ghp_' + 'a1' * 12, 'ABCDEF123456!', 'ALEX.PASSWORD' + 'X' * 30, 'a' * 30 + '@contoso.com'):
            verdict = signin_facts.evaluate(self.facts(name), TENANT_A)
            self.assertEqual(len(verdict['rule'].split()), 1, name)
            self.assertLessEqual(readable(verdict).count('(it '), 1, name)


if __name__ == '__main__':
    unittest.main()
