"""PKG-SETUP-5C findings 3 and 4 (round 2): the rule that applied and the distinct codes ride in additive keys.

status and message keep their former values (test_signin_golden holds the proof); detail_code, rule and readable_message are
new keys. Readers that branch on status (readiness, catalog) use the former codes.
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
FORMER = '(a token prefix or an unbroken run of 24 or more letters and digits)'


class CredentialShapedNameTests(Base):
    def verdict(self, user, **more):
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(user=user, **more)))
        return signin_facts.evaluate(signin.detect_azure(deadline=5), TENANT_A)

    def test_a_token_prefix_keeps_status_unknown_and_adds_its_code_and_rule(self):
        for name in ('ghp_abc1234', 'github_pat_abc1234', 'eyJhbGciOiJIUzI1NiJ9.x@contoso.com'):
            verdict = self.verdict(name)
            self.assertEqual((verdict['status'], verdict['usable']), ('unknown', False), name)
            self.assertEqual((verdict['detail_code'], verdict['rule']), ('credential_shaped_name', 'token_prefix'), name)
            self.assertIn(FORMER, verdict['message'], name)
            self.assertIn('is shaped like a credential ' + PREFIX_TEXT, verdict['readable_message'], name)
            self.assertNotIn('unbroken', verdict['readable_message'], name)
            self.assertNotIn(name, json.dumps(verdict))

    def test_an_unbroken_run_is_named_as_the_rule_in_the_readable_message_only(self):
        for name in ('a' * 30 + '@contoso.com', 'Z9' * 15):
            verdict = self.verdict(name)
            self.assertEqual((verdict['status'], verdict['detail_code'], verdict['rule']), ('unknown', 'credential_shaped_name',
                                                                                          'unbroken_run'), name)
            self.assertIn('is shaped like a credential ' + RUN_TEXT, verdict['readable_message'], name)
            self.assertNotIn('token prefix', verdict['readable_message'], name)
            self.assertIn(FORMER, verdict['message'], name)

    def test_a_credential_shaped_github_login_has_the_same_additive_keys(self):
        self.fakes.answer('gh', 'auth', 'status', out=github_hosts(('github.com', 'ghp_abc1234', 'success', True)))
        verdict = signin_facts.evaluate(signin.detect_github(deadline=5))
        self.assertEqual((verdict['status'], verdict['detail_code'], verdict['rule']), ('unknown', 'credential_shaped_name',
                                                                                      'token_prefix'))
        self.assertIn(PREFIX_TEXT, verdict['readable_message'])
        self.assertNotIn('ghp_', json.dumps(verdict))

    def test_a_collect_with_a_credential_shaped_name_is_blocked_with_status_unknown_and_runs_no_token_command(self):
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(user='ghp_abc1234')))
        result = self.collect()
        self.assertEqual((result['status'], result['signin']['status'], result['signin']['detail_code']),
                         ('blocked', 'unknown', 'credential_shaped_name'))
        self.assertEqual(self.fakes.calls(), ['account list --output json'])

    def test_facts_that_record_no_rule_still_carry_the_code_without_a_rule(self):
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(user='ghp_abc1234')))
        facts = signin.detect_azure(deadline=5)
        for account in facts['accounts']:
            account.pop('hidden_reasons', None)
        verdict = signin_facts.evaluate(facts, TENANT_A)
        self.assertEqual((verdict['status'], verdict['detail_code']), ('unknown', 'credential_shaped_name'))
        self.assertNotIn('rule', verdict)
        self.assertIn('(its form matches a credential signature)', verdict['readable_message'])


class TwoDefaultsTests(Base):
    def test_two_entries_marked_default_keep_status_several_accounts_and_add_two_defaults(self):
        self.fakes.answer('az', 'account', 'list', out=azure_list(
            azure_account(), azure_account(user='sam@example.test', default=True)))
        verdict = signin_facts.evaluate(signin.detect_azure(deadline=5), TENANT_A)
        self.assertEqual((verdict['status'], verdict['usable'], verdict['detail_code']), ('several_accounts', False, 'two_defaults'))
        self.assertNotIn('readable_message', verdict)
        self.assertIn('marks more than one entry as its default', verdict['message'])

    def test_two_default_rows_of_one_account_are_two_defaults_too(self):
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(sub='s1'), azure_account(sub='s2')))
        verdict = signin_facts.evaluate(signin.detect_azure(deadline=5), TENANT_A)
        self.assertEqual((verdict['status'], verdict['detail_code']), ('several_accounts', 'two_defaults'))

    def test_several_accounts_with_one_default_has_no_detail_code(self):
        self.fakes.answer('az', 'account', 'list', out=azure_list(
            azure_account(), azure_account(user='sam@example.test', default=False)))
        verdict = signin_facts.evaluate(signin.detect_azure(deadline=5), TENANT_A)
        self.assertEqual(verdict['status'], 'several_accounts')
        self.assertNotIn('detail_code', verdict)

    def test_a_collect_with_two_defaults_is_refused_with_the_former_status(self):
        self.fakes.answer('az', 'account', 'list', out=azure_list(
            azure_account(), azure_account(user='sam@example.test', default=True)))
        result = self.collect()
        self.assertEqual((result['status'], result['signin']['status']), ('blocked', 'several_accounts'))
        self.assertEqual(self.fakes.calls(), ['account list --output json'])


class ReadersTests(Base):
    def test_the_readiness_row_still_replaces_its_next_action_for_two_defaults(self):
        from intune_iac.readiness import readiness
        from plugin_tests.test_readiness import context_item, doctor_report, host_report, rows_of, survey_of
        two = azure((TENANT_A, 'alex@example.test', True, 'active'), (TENANT_A, 'sam@example.test', True, 'active'))
        value = readiness(survey_of(context_item()), host_report(), doctor_report(), signin={'azure': two})
        self.assertEqual(value['signin']['azure']['status'], 'several_accounts')
        row = rows_of(value, 'discover')['integration_service']
        self.assertEqual(row['next_action'], value['signin']['azure']['next_step'])
        self.assertEqual(row['owner_role'], 'engineer')

    def test_the_readiness_row_still_replaces_its_next_action_for_a_credential_shaped_name(self):
        from intune_iac.readiness import readiness
        from plugin_tests.test_readiness import context_item, doctor_report, host_report, rows_of, survey_of
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(user='ghp_abc1234')))
        value = readiness(survey_of(context_item()), host_report(), doctor_report(),
                          signin={'azure': signin.detect_azure(deadline=5)})
        row = rows_of(value, 'discover')['integration_service']
        self.assertEqual(row['next_action'], value['signin']['azure']['next_step'])

    def test_the_catalog_reads_the_former_status_unknown(self):
        from intune_iac import catalog
        from plugin_tests.test_readiness import context_item, survey_of
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(user='ghp_abc1234')))
        value = catalog.build(survey_of(context_item()), signin={'azure': signin.detect_azure(deadline=5)})
        states = {g['authenticated']['state'] for g in value['integrations'][0]['goals']}
        self.assertEqual(states, {'unknown'})

    def test_the_text_screen_renders_from_the_additive_keys(self):
        self.fakes.answer('az', 'account', 'list', out=azure_list(
            azure_account(), azure_account(user='sam@example.test', default=True)))
        report = signin.status_report(TENANT_A, None, 'azure', 5)
        self.assertEqual(report['azure']['status'], 'several_accounts')
        self.assertEqual(signin_facts.status_lines(report, 100, 2)[0], 'AZURE: BLOCKED (two_defaults)')
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(user='ghp_abc1234')))
        report = signin.status_report(TENANT_A, None, 'azure', 5)
        rows = signin_facts.status_lines(report, 100, 2)
        self.assertEqual(rows[0], 'AZURE: BLOCKED (credential_shaped_name)')
        self.assertIn('(it starts with a token prefix)', ' '.join(rows))
        self.assertNotIn('unbroken', ' '.join(rows))
        self.assertNotIn('ghp_', ' '.join(rows))


class TokenBindingReasonTests(BindingBase):
    def refusal(self, token):
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(user='alex@example.test')))
        self.fakes.answer('az', 'account', 'get-access-token', out=token_answer(token))
        result = self.collect()
        self.assertEqual((result['status'], result['signin']['status']), ('blocked', 'account_binding_unavailable'))
        self.assertEqual(result['collector_started'], False)
        return result['signin']

    def test_an_opaque_token_keeps_the_former_message_and_adds_rule_opaque(self):
        verdict = self.refusal('opaque-' + 'A' * 40)
        self.assertIn('(it is opaque, or carries none of the upn, unique_name or appid claims)', verdict['message'])
        self.assertEqual(verdict['rule'], 'opaque')
        self.assertIn('(it is opaque: it is not a token whose claims can be read)', verdict['readable_message'])
        self.assertNotIn('carries none', verdict['readable_message'])

    def test_a_readable_token_with_no_account_claim_adds_rule_no_claims(self):
        verdict = self.refusal(jwt(tid=TENANT_A, exp=4102444800))
        self.assertIn('(it is opaque, or carries none of the upn, unique_name or appid claims)', verdict['message'])
        self.assertEqual(verdict['rule'], 'no_claims')
        self.assertIn('(it carries none of the upn, unique_name or appid claims)', verdict['readable_message'])
        self.assertNotIn('opaque', verdict['readable_message'])

    def test_nothing_of_the_token_is_in_the_refusal(self):
        self.assertNotIn('BBBBBBBB', json.dumps(self.refusal('opaque-' + 'B' * 40)))


if __name__ == '__main__':
    unittest.main()
