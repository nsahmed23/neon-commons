"""PKG-SETUP-5C round 4: evaluate() returns a plain canonical dict; the presentation travels only on a separate text route.

Nothing about the presentation is attached to an object that flows through JSON, collect, readiness, the catalog, copying or
persistence: copy, deepcopy, pickle and vars() of the verdict show a plain dict with no notes.
"""
import copy
import json
import pickle
import unittest
from unittest import mock

from intune_iac import signin, signin_facts
from plugin_tests.signin_fakes import TENANT_A, azure_account, azure_list, github_hosts
from plugin_tests.test_signin_fix1 import Base

CANONICAL = {'provider', 'status', 'usable', 'tenant_wanted', 'signed_in', 'message', 'next_step'}
CASES = {
    'credential_shaped': azure_account(user='ghp_abc1234'),
    'hidden': azure_account(user='alexander.morgan@contoso.onmicrosoft.com'),
}


class PlainVerdictTests(Base):
    def facts(self, account):
        self.fakes.answer('az', 'account', 'list', out=azure_list(account))
        return signin.detect_azure(deadline=5)

    def test_evaluate_returns_exactly_a_plain_dict_for_every_kind_of_verdict(self):
        two = azure_list(azure_account(), azure_account(user='sam@example.test', default=True))
        self.fakes.answer('az', 'account', 'list', out=two)
        verdicts = [signin_facts.evaluate(signin.detect_azure(deadline=5), TENANT_A)]
        for account in CASES.values():
            verdicts.append(signin_facts.evaluate(self.facts(account), TENANT_A))
        self.fakes.answer('gh', 'auth', 'status', out=github_hosts(('github.com', 'ghp_abc1234', 'success', True)))
        verdicts.append(signin_facts.evaluate(signin.detect_github(deadline=5)))
        for verdict in verdicts:
            self.assertIs(type(verdict), dict)
            self.assertEqual(set(verdict), CANONICAL)

    def test_copy_deepcopy_pickle_and_vars_of_a_verdict_carry_no_notes(self):
        for name, account in CASES.items():
            verdict = signin_facts.evaluate(self.facts(account), TENANT_A)
            for label, other in (('copy', copy.copy(verdict)), ('deepcopy', copy.deepcopy(verdict)),
                                 # a round trip of a dict this test just made, to see what state it carries (no outside data)
                                 ('pickle', pickle.loads(pickle.dumps(verdict)))):
                self.assertIs(type(other), dict, (name, label))
                self.assertEqual(other, verdict, (name, label))
                self.assertFalse(hasattr(other, 'notes'), (name, label))
            with self.assertRaises(TypeError):
                vars(verdict)  # a plain dict has no instance state to expose
            self.assertFalse(hasattr(verdict, 'notes'))
            self.assertFalse(hasattr(verdict, '__dict__'))

    def test_the_verdict_class_and_its_notes_are_gone(self):
        self.assertFalse(hasattr(signin_facts, 'Verdict'))
        self.assertFalse(hasattr(signin_facts, 'presentation'))

    def test_the_text_route_gives_the_same_canonical_verdict_as_evaluate(self):
        two = azure_list(azure_account(), azure_account(user='sam@example.test', default=True))
        self.fakes.answer('az', 'account', 'list', out=two)
        accounts = [signin.detect_azure(deadline=5)]
        for account in CASES.values():
            accounts.append(self.facts(account))
        for facts in accounts:
            verdict, shown = signin_facts.evaluate_with_presentation(facts, TENANT_A)
            self.assertEqual(verdict, signin_facts.evaluate(facts, TENANT_A))
            self.assertIs(type(verdict), dict)
            self.assertEqual(set(shown), {'code', 'rule', 'sentence'})

    def test_the_text_route_presents_the_finer_code_and_the_one_rule(self):
        verdict, shown = signin_facts.evaluate_with_presentation(self.facts(CASES['credential_shaped']), TENANT_A)
        self.assertEqual((verdict['status'], shown['code'], shown['rule']), ('unknown', 'credential_shaped_name', 'token_prefix'))
        self.assertIn('(it starts with a token prefix)', shown['sentence'])
        self.assertNotIn('ghp_', json.dumps(shown))

    def test_status_report_and_collect_carry_plain_dicts_only(self):
        self.fakes.answer('az', 'account', 'list', out=azure_list(CASES['credential_shaped']))
        report = signin.status_report(TENANT_A, None, 'azure', 5)
        self.assertIs(type(report['azure']), dict)
        self.assertFalse(hasattr(report['azure'], 'notes'))
        result = self.collect()
        self.assertIs(type(result['signin']), dict)

    def test_only_the_text_status_path_asks_for_the_presentation(self):
        import contextlib
        import io
        import os
        from unittest.mock import patch
        from intune_iac import cli
        self.fakes.answer('az', 'account', 'list', out=azure_list(CASES['credential_shaped']))
        with mock.patch.object(signin_facts, 'evaluate_with_presentation', wraps=signin_facts.evaluate_with_presentation) as route, \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            cli.main(['signin', 'status', '--tenant', TENANT_A, '--json'])
            self.assertEqual(route.call_count, 0)
            cli.main(['signin', 'status', '--tenant', TENANT_A])
            self.assertEqual(route.call_count, 1)
        self.assertEqual(signin.status_report.__module__, 'intune_iac.signin')


if __name__ == '__main__':
    unittest.main()
