"""Item 2: a sign-in to the wrong tenant, or several accounts, blocks the work and says both facts and the exact next step.

Three layers: the pure judgement over facts (signin_facts.evaluate), the readiness row, and start --goal discover with
--check-signin against fake az and gh. Nothing proceeds on a wrong tenant, and the product never picks an account silently.
"""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from intune_iac import signin_facts
from plugin_tests.signin_fakes import FakeClis, TENANT_A, TENANT_B, azure_account, azure_list
from plugin_tests import test_readiness as tr

ROOT = Path(__file__).resolve().parents[1]
CONTEXT_TENANT = json.loads((ROOT / 'examples/context.json').read_text())['tenant_id']
OTHER = '55555555-5555-4555-8555-555555555555'


def azure(*accounts, state='signed_in'):
    """Facts shaped like signin.detect_azure's result."""
    return {'provider': 'azure', 'state': state, 'reason': None, 'accounts': [
        {'tenant': t, 'account': a, 'cloud': 'AzureCloud', 'default': d, 'session': s} for t, a, d, s in accounts]}


class EvaluateTests(unittest.TestCase):
    def test_matching_tenant_and_one_account_is_usable(self):
        value = signin_facts.evaluate(azure((TENANT_A, 'alex@example.test', True, 'active')), TENANT_A)
        self.assertEqual((value['status'], value['usable']), ('signed_in', True))
        self.assertIn(TENANT_A, value['message'])

    def test_without_a_context_tenant_a_sign_in_is_shown_but_not_usable(self):
        value = signin_facts.evaluate(azure((TENANT_A, 'alex@example.test', True, 'active')), None)
        self.assertEqual((value['status'], value['usable']), ('signed_in', False))
        self.assertIn('alex@example.test', value['message'])

    def test_wrong_tenant_names_both_tenants_and_the_exact_next_step(self):
        value = signin_facts.evaluate(azure((TENANT_A, 'alex@example.test', True, 'active')), TENANT_B)
        self.assertEqual((value['status'], value['usable']), ('wrong_tenant', False))
        self.assertIn(TENANT_A, value['message'])
        self.assertIn(TENANT_B, value['message'])
        self.assertIn('alex@example.test', value['message'])
        self.assertIn('Nothing proceeds', value['message'])
        self.assertEqual(value['next_step'], 'Sign in to the tenant the context names: az login --tenant %s; then run this '
                                             'command again.' % TENANT_B)

    def test_wrong_tenant_lists_the_other_sign_ins_and_picks_none(self):
        facts = azure((TENANT_A, 'alex@example.test', True, 'active'), (OTHER, 'sam@example.test', False, 'active'))
        value = signin_facts.evaluate(facts, TENANT_B)
        self.assertEqual(value['status'], 'wrong_tenant')
        self.assertIn('sam@example.test', value['message'])
        self.assertIn(OTHER, value['message'])

    def test_a_default_in_another_tenant_does_not_hide_an_account_in_the_right_one(self):
        # The CLI would hand a token to its default account, which is not in the context's tenant: still blocked.
        facts = azure((TENANT_A, 'alex@example.test', True, 'active'), (TENANT_B, 'sam@example.test', False, 'active'))
        value = signin_facts.evaluate(facts, TENANT_B)
        self.assertEqual((value['status'], value['usable']), ('wrong_tenant', False))

    def test_several_accounts_are_listed_by_name_and_none_is_picked(self):
        facts = azure((TENANT_A, 'alex@example.test', True, 'active'), (TENANT_A, 'sam@example.test', False, 'active'))
        value = signin_facts.evaluate(facts, TENANT_A)
        self.assertEqual((value['status'], value['usable']), ('several_accounts', False))
        self.assertIn('alex@example.test', value['message'])
        self.assertIn('sam@example.test', value['message'])
        self.assertIn('does not pick', value['message'])
        self.assertIn('--account', value['next_step'])
        self.assertEqual(signin_facts.evaluate(facts, None)['status'], 'several_accounts')

    def test_an_account_named_by_the_engineer_must_be_the_one_the_cli_uses(self):
        facts = azure((TENANT_A, 'alex@example.test', True, 'active'), (TENANT_A, 'sam@example.test', False, 'active'))
        chosen = signin_facts.evaluate(facts, TENANT_A, account='alex@example.test')
        self.assertEqual((chosen['status'], chosen['usable']), ('signed_in', True))
        other = signin_facts.evaluate(facts, TENANT_A, account='sam@example.test')
        self.assertEqual((other['status'], other['usable']), ('several_accounts', False))
        self.assertIn('az account set', other['next_step'])
        single = azure((TENANT_A, 'alex@example.test', True, 'active'))
        mismatch = signin_facts.evaluate(single, TENANT_A, account='sam@example.test')
        self.assertEqual((mismatch['status'], mismatch['usable']), ('account_mismatch', False))

    def test_not_signed_in_and_unknown_give_the_exact_next_step(self):
        none = signin_facts.evaluate({'provider': 'azure', 'state': 'not_signed_in', 'reason': None, 'accounts': []}, TENANT_A)
        self.assertEqual((none['status'], none['usable']), ('not_signed_in', False))
        self.assertIn('az login --tenant %s' % TENANT_A, none['next_step'])
        unknown = signin_facts.evaluate({'provider': 'azure', 'state': 'unknown', 'reason': 'deadline', 'accounts': []}, TENANT_A)
        self.assertEqual((unknown['status'], unknown['usable']), ('unknown', False))
        self.assertIn('deadline', unknown['message'])
        placeholder = signin_facts.evaluate({'provider': 'azure', 'state': 'not_signed_in', 'reason': None, 'accounts': []}, None)
        self.assertIn('az login --tenant TENANT_ID', placeholder['next_step'])

    def test_github_facts_are_judged_without_a_tenant_and_never_pick_an_account(self):
        one = {'provider': 'github', 'state': 'signed_in', 'reason': None,
               'accounts': [{'host': 'github.com', 'account': 'octo-user', 'active': True, 'session': 'active'}]}
        value = signin_facts.evaluate(one, TENANT_A)
        self.assertEqual(value['status'], 'signed_in')
        self.assertIn('github.com', value['message'])
        two = dict(one, accounts=one['accounts'] + [{'host': 'github.com', 'account': 'other-user', 'active': False,
                                                      'session': 'active'}])
        value = signin_facts.evaluate(two, None)
        self.assertEqual(value['status'], 'several_accounts')
        self.assertIn('other-user', value['message'])

    def test_evaluate_drops_anything_that_is_not_a_plain_shape(self):
        poison = 'TESTONLY-poison-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA1'
        facts = azure((TENANT_A, poison, True, 'active'))
        value = signin_facts.evaluate(facts, TENANT_A)
        self.assertNotIn(poison, json.dumps(value))
        self.assertEqual(value['status'], 'unknown')


class ReadinessRowTests(unittest.TestCase):
    def model(self, signin, *items):
        from intune_iac.readiness import readiness
        return readiness(tr.survey_of(tr.repository_item(), *items), tr.host_report(), tr.doctor_report(), signin=signin)

    def row(self, value, operation='discover'):
        return tr.rows_of(value, operation)['integration_service']

    def test_wrong_tenant_makes_the_row_missing_and_says_both_tenants_and_the_next_step(self):
        facts = {'azure': azure((TENANT_A, 'alex@example.test', True, 'active'))}
        value = self.model(facts, tr.context_item(tenant=TENANT_B))
        row = self.row(value)
        self.assertEqual(row['state'], 'missing')
        text = ' '.join(row['missing'])
        self.assertIn(TENANT_A, text)
        self.assertIn(TENANT_B, text)
        self.assertEqual(row['next_action'], 'Sign in to the tenant the context names: az login --tenant %s; then run this '
                                              'command again.' % TENANT_B)
        self.assertEqual(value['operations']['discover']['status'], 'missing')
        self.assertIn('integration_service', value['operations']['discover']['blocking'])

    def test_several_accounts_make_the_row_unknown_and_list_the_names(self):
        facts = {'azure': azure((TENANT_A, 'alex@example.test', True, 'active'), (TENANT_A, 'sam@example.test', False, 'active'))}
        row = self.row(self.model(facts, tr.context_item(tenant=TENANT_A)))
        self.assertEqual(row['state'], 'unknown')
        self.assertIn('sam@example.test', ' '.join(row['missing']))

    def test_two_tenants_named_by_the_inputs_are_not_compared_with_the_sign_in(self):
        facts = {'azure': azure((TENANT_A, 'alex@example.test', True, 'active'))}
        row = self.row(self.model(facts, tr.context_item(tenant=TENANT_A), tr.export_item(tenant=TENANT_B)))
        self.assertNotIn('wrong_tenant', json.dumps(row))
        self.assertIn('choose one', ' '.join(row['missing']))

    def test_without_sign_in_facts_the_row_says_the_check_was_not_run_and_names_the_flag(self):
        row = self.row(self.model(None, tr.context_item(tenant=TENANT_A)))
        text = ' '.join(row['missing'])
        self.assertIn('--check-signin', text)
        self.assertNotIn('no route yet for sign-in reuse', text)


class StartGoalTests(unittest.TestCase):
    def setUp(self):
        self.fakes = FakeClis()
        self.addCleanup(self.fakes.cleanup)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)
        shutil.copyfile(ROOT / 'examples/context.json', self.directory / 'context.json')
        patcher = patch.dict(os.environ, {'PATH': self.fakes.path_entry() + os.pathsep + os.environ.get('PATH', '')})
        patcher.start()
        self.addCleanup(patcher.stop)

    def start(self, *extra):
        from intune_iac.cli import main
        out, err = io.StringIO(), io.StringIO()
        with patch('shutil.get_terminal_size', return_value=os.terminal_size((100, 40))), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(['start', str(self.directory), '--goal', 'discover', *extra])
        return code, out.getvalue(), err.getvalue()

    def test_a_wrong_tenant_screen_says_both_tenants_and_the_exact_next_step(self):
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(tenant=OTHER)))
        code, out, _ = self.start('--check-signin', 'azure')
        self.assertEqual(code, 0)
        self.assertIn(OTHER, out)
        self.assertIn(CONTEXT_TENANT, out)
        self.assertIn('az login --tenant %s' % CONTEXT_TENANT, ' '.join(out.split()))  # the screen wraps long lines
        self.assertIn('Integration and service: missing', out)
        self.assertEqual(self.fakes.calls(), ['account list --output json'])

    def test_the_json_carries_the_judgement_and_runs_only_the_listing(self):
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(tenant=OTHER)))
        code, out, _ = self.start('--check-signin', 'azure', '--json')
        view = json.loads(out)['readiness']
        self.assertEqual(view['signin']['azure']['status'], 'wrong_tenant')
        self.assertEqual(view['signin']['azure']['usable'], False)
        self.assertEqual(self.fakes.calls(), ['account list --output json'])

    def test_without_the_flag_no_cli_runs(self):
        code, out, _ = self.start()
        self.assertEqual(self.fakes.calls(), [])
        self.assertNotIn('signin', json.loads(self.run_json())['readiness'])

    def run_json(self):
        return self.start('--json')[1]

    def test_the_flag_needs_a_goal(self):
        from intune_iac.cli import main
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            code = main(['start', str(self.directory), '--check-signin', 'azure'])
        self.assertEqual(code, 3)
        self.assertIn('signin_check_needs_goal', err.getvalue())
        self.assertEqual(self.fakes.calls(), [])


if __name__ == '__main__':
    unittest.main()
