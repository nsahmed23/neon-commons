"""PKG-SETUP-5C round 3: a hidden name records exactly one reason (the first match in one fixed order) and says only that.

Sol's inputs: ghp_ followed by 24 alphanumerics matched both signature rules, and ABCDEF123456! matched both the odd-characters
rule and the capitals block. The fixed order is token_prefix, unbroken_run (the usability judge), then shape, length, caps_block,
credential_word (shown_name's own order).
"""
import unittest

from intune_iac import signin, signin_facts
from plugin_tests.signin_fakes import TENANT_A, TENANT_B, azure_account, azure_list
from plugin_tests.test_signin_fix1 import Base


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
            sentence = signin_facts.presentation(verdict)['sentence']
            self.assertEqual(verdict['status'], 'wrong_tenant')
            self.assertIn('whose name is not shown here (it starts with a token prefix)', sentence, name)
            self.assertNotIn('unbroken', sentence, name)

    def test_odd_characters_with_a_capitals_block_say_only_the_odd_characters(self):
        shown = signin_facts.presentation(signin_facts.evaluate(self.facts('ABCDEF123456!'), TENANT_A))
        self.assertEqual(shown['rule'], 'shape')
        self.assertIn('whose name is not shown here (it has characters this display does not allow)', shown['sentence'])
        self.assertNotIn('capitals', shown['sentence'])

    def test_a_credential_signature_blocked_sentence_names_one_rule(self):
        verdict = signin_facts.evaluate(self.facts('ghp_' + 'a1' * 12), TENANT_A)
        shown = signin_facts.presentation(verdict)
        self.assertEqual((verdict['status'], shown['code'], shown['rule']), ('unknown', 'credential_shaped_name', 'token_prefix'))
        self.assertIn('(it starts with a token prefix)', shown['sentence'])
        self.assertNotIn('unbroken', shown['sentence'])

    def test_a_presentation_never_joins_two_rules_with_and(self):
        for name in ('ghp_' + 'a1' * 12, 'ABCDEF123456!', 'ALEX.PASSWORD' + 'X' * 30, 'a' * 30 + '@contoso.com'):
            shown = signin_facts.presentation(signin_facts.evaluate(self.facts(name), TENANT_A))
            self.assertEqual(len(shown['rule'].split()), 1, name)
            self.assertLessEqual(shown['sentence'].count('(it '), 1, name)


if __name__ == '__main__':
    unittest.main()
