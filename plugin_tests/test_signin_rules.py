"""PKG-SETUP-5C item 5 (run 2 findings 3 and 4): name the rule that applied, and give distinct inner status codes.

Finding 3: a credential-shaped name says "a token prefix" or "an unbroken run of 24 or more letters and digits"; a token that
names no account says "it is opaque" or "it carries none of the upn, unique_name or appid claims". Finding 4: two defaults is
two_defaults and a credential-shaped name is credential_shaped_name (they were several_accounts and unknown).
"""
import json
import unittest

from intune_iac import signin, signin_facts
from plugin_tests.signin_5b_common import Base as BindingBase, jwt
from plugin_tests.signin_fakes import TENANT_A, azure_account, azure_list, github_hosts
from plugin_tests.test_signin_fix1 import Base, token_answer
from plugin_tests.test_signin_tenant import azure

PREFIX_TEXT = '(it starts with a token prefix)'
RUN_TEXT = '(it holds an unbroken run of 24 or more letters and digits)'


class CredentialShapedNameTests(Base):
    def verdict(self, user, **more):
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(user=user, **more)))
        return signin_facts.evaluate(signin.detect_azure(deadline=5), TENANT_A)

    def test_a_token_prefix_is_named_as_the_rule_and_has_its_own_status(self):
        for name in ('ghp_abc1234', 'github_pat_abc1234', 'eyJhbGciOiJIUzI1NiJ9.x@contoso.com'):
            verdict = self.verdict(name)
            self.assertEqual((verdict['status'], verdict['usable']), ('credential_shaped_name', False), name)
            self.assertIn('is shaped like a credential ' + PREFIX_TEXT, verdict['message'], name)
            self.assertNotIn('unbroken run', verdict['message'], name)
            self.assertNotIn(name, json.dumps(verdict))

    def test_an_unbroken_run_is_named_as_the_rule(self):
        for name in ('a' * 30 + '@contoso.com', 'Z9' * 15):
            verdict = self.verdict(name)
            self.assertEqual(verdict['status'], 'credential_shaped_name', name)
            self.assertIn('is shaped like a credential ' + RUN_TEXT, verdict['message'], name)
            self.assertNotIn('token prefix', verdict['message'], name)
            self.assertNotIn(name, json.dumps(verdict))

    def test_the_old_two_way_text_is_gone(self):
        verdict = self.verdict('ghp_abc1234')
        self.assertNotIn('a token prefix or an unbroken run', verdict['message'])

    def test_a_credential_shaped_github_login_has_the_same_status_and_names_its_rule(self):
        self.fakes.answer('gh', 'auth', 'status', out=github_hosts(('github.com', 'ghp_abc1234', 'success', True)))
        verdict = signin_facts.evaluate(signin.detect_github(deadline=5))
        self.assertEqual(verdict['status'], 'credential_shaped_name')
        self.assertIn(PREFIX_TEXT, verdict['message'])
        self.assertNotIn('ghp_', json.dumps(verdict))

    def test_a_collect_with_a_credential_shaped_name_is_blocked_with_the_new_code_and_runs_no_token_command(self):
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(user='ghp_abc1234')))
        result = self.collect()
        self.assertEqual((result['status'], result['signin']['status']), ('blocked', 'credential_shaped_name'))
        self.assertEqual(self.fakes.calls(), ['account list --output json'])

    def test_facts_that_record_no_rule_still_say_credential_shaped_without_naming_one(self):
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(user='ghp_abc1234')))
        facts = signin.detect_azure(deadline=5)
        for account in facts['accounts']:
            account.pop('hidden_reasons', None)
        verdict = signin_facts.evaluate(facts, TENANT_A)
        self.assertEqual(verdict['status'], 'credential_shaped_name')
        self.assertIn('(its form matches a credential signature)', verdict['message'])


class TwoDefaultsTests(Base):
    def test_two_entries_marked_default_is_two_defaults_not_several_accounts(self):
        self.fakes.answer('az', 'account', 'list', out=azure_list(
            azure_account(), azure_account(user='sam@example.test', default=True)))
        verdict = signin_facts.evaluate(signin.detect_azure(deadline=5), TENANT_A)
        self.assertEqual((verdict['status'], verdict['usable']), ('two_defaults', False))
        self.assertIn('marks more than one entry as its default', verdict['message'])

    def test_two_default_rows_of_one_account_are_two_defaults_too(self):
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(sub='s1'), azure_account(sub='s2')))
        verdict = signin_facts.evaluate(signin.detect_azure(deadline=5), TENANT_A)
        self.assertEqual(verdict['status'], 'two_defaults')

    def test_several_accounts_with_one_default_keeps_its_own_status(self):
        self.fakes.answer('az', 'account', 'list', out=azure_list(
            azure_account(), azure_account(user='sam@example.test', default=False)))
        verdict = signin_facts.evaluate(signin.detect_azure(deadline=5), TENANT_A)
        self.assertEqual(verdict['status'], 'several_accounts')

    def test_a_collect_with_two_defaults_is_refused_with_the_new_code(self):
        self.fakes.answer('az', 'account', 'list', out=azure_list(
            azure_account(), azure_account(user='sam@example.test', default=True)))
        result = self.collect()
        self.assertEqual((result['status'], result['signin']['status']), ('blocked', 'two_defaults'))
        self.assertEqual(self.fakes.calls(), ['account list --output json'])


class ReadersOfTheNewCodesTests(Base):
    def test_the_readiness_row_replaces_its_next_action_with_the_new_codes_next_step(self):
        from intune_iac.readiness import readiness
        from plugin_tests.test_readiness import context_item, doctor_report, host_report, rows_of, survey_of
        two = azure(('11111111-1111-4111-8111-111111111111', 'alex@example.test', True, 'active'),
                    ('11111111-1111-4111-8111-111111111111', 'sam@example.test', True, 'active'))
        value = readiness(survey_of(context_item()), host_report(), doctor_report(), signin={'azure': two})
        self.assertEqual(value['signin']['azure']['status'], 'two_defaults')
        row = rows_of(value, 'discover')['integration_service']
        self.assertEqual(row['next_action'], value['signin']['azure']['next_step'])
        self.assertEqual(row['owner_role'], 'engineer')

    def test_the_catalog_keeps_a_credential_shaped_name_unknown_not_unauthenticated(self):
        from intune_iac import catalog
        from plugin_tests.test_readiness import context_item, survey_of
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(user='ghp_abc1234')))
        value = catalog.build(survey_of(context_item()), signin={'azure': signin.detect_azure(deadline=5)})
        states = {g['authenticated']['state'] for g in value['integrations'][0]['goals']}
        self.assertEqual(states, {'unknown'})

    def test_the_text_screen_prints_the_new_codes(self):
        self.fakes.answer('az', 'account', 'list', out=azure_list(
            azure_account(), azure_account(user='sam@example.test', default=True)))
        report = signin.status_report(TENANT_A, None, 'azure', 5)
        self.assertEqual(signin_facts.status_lines(report, 100, 2)[0], 'AZURE: BLOCKED (two_defaults)')


class TokenBindingReasonTests(BindingBase):
    def listing_and_token(self, token):
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(user='alex@example.test')))
        self.fakes.answer('az', 'account', 'get-access-token', out=token_answer(token))

    def refusal(self, token):
        self.listing_and_token(token)
        result = self.collect()
        self.assertEqual((result['status'], result['signin']['status']), ('blocked', 'account_binding_unavailable'))
        self.assertEqual(result['collector_started'], False)
        return result['signin']['message']

    def test_an_opaque_token_says_it_is_opaque_and_nothing_about_claims(self):
        message = self.refusal('opaque-' + 'A' * 40)
        self.assertIn('(it is opaque: it is not a token whose claims can be read)', message)
        self.assertNotIn('carries none', message)

    def test_a_readable_token_with_no_account_claim_says_which_claims_are_missing(self):
        message = self.refusal(jwt(tid=TENANT_A, exp=4102444800))
        self.assertIn('(it carries none of the upn, unique_name or appid claims)', message)
        self.assertNotIn('opaque', message)

    def test_neither_message_carries_any_part_of_the_token(self):
        token = 'opaque-' + 'B' * 40
        self.assertNotIn('BBBBBBBB', self.refusal(token))


if __name__ == '__main__':
    unittest.main()
