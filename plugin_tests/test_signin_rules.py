"""PKG-SETUP-5C findings 3 and 4 (round 3): the finer code and the rule that applied live in a presentation, not in the verdict.

status and message keep their former values and the verdict carries no other key (test_signin_golden holds the proof for the
JSON commands). signin_facts.evaluate_with_presentation gives the text view its code, its one rule and its sentence, with the verdict
and what was noted while it was judged, without judging again. Readers that branch on status use the former codes.
"""
import json
import threading
import unittest
from unittest import mock

from intune_iac import signin, signin_facts
from plugin_tests.signin_fakes import TENANT_A, azure_account, azure_list, github_hosts
from plugin_tests.test_signin_fix1 import Base
from plugin_tests.test_signin_tenant import azure

PREFIX_TEXT = '(it starts with a token prefix)'
RUN_TEXT = '(it holds an unbroken run of 24 or more letters and digits)'
FORMER = '(a token prefix or an unbroken run of 24 or more letters and digits)'
CANONICAL = {'provider', 'status', 'usable', 'tenant_wanted', 'signed_in', 'message', 'next_step'}


class CredentialShapedNameTests(Base):
    def verdict(self, user, **more):
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(user=user, **more)))
        return signin_facts.evaluate_with_presentation(signin.detect_azure(deadline=5), TENANT_A)

    def test_a_token_prefix_keeps_status_unknown_and_the_presentation_has_its_code_and_rule(self):
        for name in ('ghp_abc1234', 'github_pat_abc1234', 'eyJhbGciOiJIUzI1NiJ9.x@contoso.com'):
            verdict, shown = self.verdict(name)
            self.assertEqual((verdict['status'], verdict['usable']), ('unknown', False), name)
            self.assertEqual(set(verdict), CANONICAL, name)
            self.assertEqual((shown['code'], shown['rule']), ('credential_shaped_name', 'token_prefix'), name)
            self.assertIn(FORMER, verdict['message'], name)
            self.assertIn('is shaped like a credential ' + PREFIX_TEXT, shown['sentence'], name)
            self.assertNotIn('unbroken', shown['sentence'], name)
            self.assertNotIn(name, json.dumps(verdict) + json.dumps(shown))

    def test_an_unbroken_run_is_named_as_the_rule_in_the_sentence_only(self):
        for name in ('a' * 30 + '@contoso.com', 'Z9' * 15):
            verdict, shown = self.verdict(name)
            self.assertEqual((verdict['status'], shown['code'], shown['rule']), ('unknown', 'credential_shaped_name', 'unbroken_run'),
                             name)
            self.assertIn('is shaped like a credential ' + RUN_TEXT, shown['sentence'], name)
            self.assertNotIn('token prefix', shown['sentence'], name)
            self.assertIn(FORMER, verdict['message'], name)

    def test_a_credential_shaped_github_login_has_the_same_presentation(self):
        self.fakes.answer('gh', 'auth', 'status', out=github_hosts(('github.com', 'ghp_abc1234', 'success', True)))
        verdict, shown = signin_facts.evaluate_with_presentation(signin.detect_github(deadline=5))
        self.assertEqual((verdict['status'], shown['code'], shown['rule']), ('unknown', 'credential_shaped_name', 'token_prefix'))
        self.assertIn(PREFIX_TEXT, shown['sentence'])
        self.assertNotIn('ghp_', json.dumps(verdict) + json.dumps(shown))

    def test_a_collect_with_a_credential_shaped_name_is_blocked_with_status_unknown_and_runs_no_token_command(self):
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(user='ghp_abc1234')))
        result = self.collect()
        self.assertEqual((result['status'], result['signin']['status']), ('blocked', 'unknown'))
        self.assertEqual(set(result['signin']), CANONICAL)
        self.assertEqual(self.fakes.calls(), ['account list --output json'])

    def test_facts_that_record_no_rule_still_present_the_code_without_a_rule(self):
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(user='ghp_abc1234')))
        facts = signin.detect_azure(deadline=5)
        for account in facts['accounts']:
            account.pop('hidden_reasons', None)
        _, shown = signin_facts.evaluate_with_presentation(facts, TENANT_A)
        self.assertEqual((shown['code'], shown['rule']), ('credential_shaped_name', None))
        self.assertIn('(its form matches a credential signature)', shown['sentence'])


class TwoDefaultsTests(Base):
    def test_two_entries_marked_default_keep_status_several_accounts_and_present_two_defaults(self):
        self.fakes.answer('az', 'account', 'list', out=azure_list(
            azure_account(), azure_account(user='sam@example.test', default=True)))
        verdict, shown = signin_facts.evaluate_with_presentation(signin.detect_azure(deadline=5), TENANT_A)
        self.assertEqual((verdict['status'], verdict['usable'], shown['code']), ('several_accounts', False, 'two_defaults'))
        self.assertEqual(set(verdict), CANONICAL)
        self.assertEqual(shown['sentence'], verdict['message'])
        self.assertIn('marks more than one entry as its default', verdict['message'])

    def test_two_default_rows_of_one_account_are_two_defaults_too(self):
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(sub='s1'), azure_account(sub='s2')))
        verdict, shown = signin_facts.evaluate_with_presentation(signin.detect_azure(deadline=5), TENANT_A)
        self.assertEqual((verdict['status'], shown['code']), ('several_accounts', 'two_defaults'))

    def test_several_accounts_with_one_default_has_no_code(self):
        self.fakes.answer('az', 'account', 'list', out=azure_list(
            azure_account(), azure_account(user='sam@example.test', default=False)))
        verdict, shown = signin_facts.evaluate_with_presentation(signin.detect_azure(deadline=5), TENANT_A)
        self.assertEqual(verdict['status'], 'several_accounts')
        self.assertIsNone(shown['code'])

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

    def test_the_catalog_reads_the_former_status_unknown(self):
        from intune_iac import catalog
        from plugin_tests.test_readiness import context_item, survey_of
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(user='ghp_abc1234')))
        value = catalog.build(survey_of(context_item()), signin={'azure': signin.detect_azure(deadline=5)})
        states = {g['authenticated']['state'] for g in value['integrations'][0]['goals']}
        self.assertEqual(states, {'unknown'})

    def test_the_text_screen_renders_from_the_presentation(self):
        self.fakes.answer('az', 'account', 'list', out=azure_list(
            azure_account(), azure_account(user='sam@example.test', default=True)))
        report, shown = signin.status_view(TENANT_A, None, 'azure', 5)
        self.assertEqual(report['azure']['status'], 'several_accounts')
        self.assertEqual(signin_facts.status_lines(report, 100, 2, shown)[0], 'AZURE: BLOCKED (two_defaults)')
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(user='ghp_abc1234')))
        report, shown = signin.status_view(TENANT_A, None, 'azure', 5)
        rows = signin_facts.status_lines(report, 100, 2, shown)
        self.assertEqual(rows[0], 'AZURE: BLOCKED (credential_shaped_name)')
        self.assertIn('(it starts with a token prefix)', ' '.join(rows))
        self.assertNotIn('unbroken', ' '.join(rows))
        self.assertNotIn('ghp_', ' '.join(rows))

    def test_without_a_presentation_the_text_falls_back_to_the_canonical_message(self):
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(user='ghp_abc1234')))
        report = signin.status_report(TENANT_A, None, 'azure', 5)
        rows = signin_facts.status_lines(report, 100, 2)
        self.assertEqual(rows[0], 'AZURE: BLOCKED (unknown)')
        self.assertIn('a token prefix or an unbroken run', ' '.join(' '.join(rows).split()))


class NoSharedStateTests(Base):
    def test_there_is_no_module_level_presentation_state(self):
        for name in ('_READABLE', '_RULES', '_rule', '_with_detail', 'ADDITIVE_KEYS', 'Verdict', 'presentation'):
            self.assertFalse(hasattr(signin_facts, name), name)

    def test_two_evaluations_interleaved_in_threads_each_return_exactly_their_own_verdict(self):
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(user='ghp_abc1234')))
        shaped = signin.detect_azure(deadline=5)
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(user='alexander.morgan@contoso.onmicrosoft.com')))
        hidden = signin.detect_azure(deadline=5)
        pairs = {'shaped': signin_facts.evaluate_with_presentation(shaped, TENANT_A), 'hidden': signin_facts.evaluate_with_presentation(hidden, TENANT_A)}
        want = {k: v[0] for k, v in pairs.items()}
        want_shown = {k: v[1] for k, v in pairs.items()}
        self.assertEqual((want['shaped']['status'], want['hidden']['status']), ('unknown', 'signed_in'))
        results, barrier = {'shaped': [], 'hidden': []}, threading.Barrier(2)

        def work(kind, facts):
            barrier.wait()
            for _ in range(300):
                results[kind].append(signin_facts.evaluate_with_presentation(facts, TENANT_A))

        import sys
        old = sys.getswitchinterval()
        sys.setswitchinterval(1e-6)
        try:
            threads = [threading.Thread(target=work, args=item) for item in (('shaped', shaped), ('hidden', hidden))]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        finally:
            sys.setswitchinterval(old)
        for kind in ('shaped', 'hidden'):
            self.assertEqual(len(results[kind]), 300)
            for verdict, shown in results[kind]:
                self.assertEqual(verdict, want[kind], kind)
                self.assertEqual(shown, want_shown[kind], kind)

    def test_the_digest_comparison_count_is_the_former_one(self):
        import hmac
        long_upn = 'alexander.morgan@contoso.onmicrosoft.com'
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(user=long_upn)))
        facts = signin.detect_azure(deadline=5)
        with mock.patch('intune_iac.signin_facts.hmac.compare_digest', wraps=hmac.compare_digest) as spy:
            signin_facts.evaluate(facts, TENANT_A, long_upn)
        self.assertEqual(spy.call_count, 1)  # one judgment, one comparison


if __name__ == '__main__':
    unittest.main()
