"""PKG-SETUP-5 items 1 and 2: truthful sign-in output (journey 32 run 1 frame review, findings 2, 5, 6, 7, 8 and 9).

Item 1 (truth): a listed entry carries the state word the CLI printed (listing_state), never a "session"; a GitHub host whose
gh state is error is invalid with its reason code, not expired; a ready report says once what it is ready for.
Item 2 (next steps): the withheld-output failure says whether the output folder was written (it is never removed) and gives
the exact next step; the account-mismatch refusal gives the command that shows the default account; every placeholder in a
printed step is marked, and "check again" is the command to run.
Fake az and gh and a fake collecting child stand in for the real ones; no canary or token value is ever printed.
"""
import json
from pathlib import Path
import re
import shlex
import sys
import unittest

from intune_iac import signin, signin_facts
from plugin_tests.signin_fakes import TENANT_A, TENANT_B, azure_account, azure_list, github_hosts
from plugin_tests.test_signin_fix1 import Base, POLICY

READY_FOR = ('The Azure CLI sign-in is usable for tenant %s; Graph, Intune and state-storage access are not known until a '
             'read is attempted.')
# An upper-case word of three or more letters in a printed step is a placeholder (a few product and tool names aside); it must
# be followed at once by its meaning in brackets, which starts like a description ("the ...", "your ...", "a ..."), so an
# unrelated bracket that happens to follow it does not count as the mark.
PLACEHOLDER = re.compile(r'\b[A-Z][A-Z_]{2,}\b')
NOT_PLACEHOLDERS = frozenset({'CLI', 'JSON', 'GUID'})
MARK = re.compile(r' \((?:the|your|a|an|that) [^()]+\)')
# The child creates the output folder, then prints what it received on the descriptor: the withheld route, folder written.
WRITER = ('import os, sys; received = os.read(int(sys.argv[2]), 8192); os.mkdir(sys.argv[1]); '
          'sys.stdout.write(received.decode())')
LONG_UPN = 'alexander.morgan@contoso.onmicrosoft.com'  # hidden from display (as in test_signin_fix4), not a secret


def unmarked(step):
    return [match.group(0) for match in PLACEHOLDER.finditer(step)
            if match.group(0) not in NOT_PLACEHOLDERS and not MARK.match(step, match.end())]


def keys(value):
    """Every key of a nested document."""
    found = set()
    if isinstance(value, dict):
        for key, item in value.items():
            found.add(key)
            found |= keys(item)
    elif isinstance(value, list):
        for item in value:
            found |= keys(item)
    return found


class ListingStateTests(Base):  # item 1a, finding 5
    def test_a_signed_in_entry_carries_the_listing_state_it_was_given_and_no_session(self):
        facts = signin.detect_azure(deadline=5)
        self.assertEqual([entry.get('listing_state') for entry in facts['accounts']], ['Enabled'])
        verdict = signin_facts.evaluate(facts, TENANT_A)
        self.assertEqual((verdict['status'], verdict['usable']), ('signed_in', True))
        self.assertEqual(verdict['signed_in'], [{'tenant': TENANT_A, 'account': 'alex@example.test', 'cloud': 'AzureCloud',
                                                 'default': True, 'listing_state': 'Enabled'}])
        # The freshness message stays: the listing says nothing about the token, which is checked when one is requested.
        self.assertIn('session freshness is checked when a token is requested', verdict['message'])
        self.assertNotIn('session', keys(facts) | keys(signin.status_report(TENANT_A, None, 'azure', 5)))

    def test_a_blocked_listing_shows_the_listing_state_of_every_entry_and_no_session(self):
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(), azure_account(
            tenant=TENANT_B, user='sam@example.test', default=False, sub='s2')))
        report = signin.status_report(TENANT_B, None, 'azure', 5)
        self.assertEqual((report['status'], report['azure']['status']), ('blocked', 'wrong_tenant'))
        self.assertEqual([entry['listing_state'] for entry in report['azure']['signed_in']], ['Enabled', 'Enabled'])
        self.assertNotIn('session', keys(report))

    def test_an_expired_listing_entry_keeps_the_word_the_cli_printed(self):
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(state='Expired')))
        facts = signin.detect_azure(deadline=5)
        self.assertEqual((facts['state'], [entry.get('listing_state') for entry in facts['accounts']]),
                         ('subscription_expired', ['Expired']))  # changed in 5A round 1: subscription state, not sign-in expiry
        self.assertNotIn('session', keys(facts))

    def test_a_github_entry_carries_the_gh_state_word_and_no_session(self):
        self.fakes.answer('gh', 'auth', 'status', out=github_hosts(('github.com', 'octo-user', 'success', True)))
        facts = signin.detect_github(deadline=5)
        self.assertEqual([entry.get('listing_state') for entry in facts['accounts']], ['success'])
        verdict = signin_facts.evaluate(facts)
        self.assertEqual(verdict['signed_in'], [{'host': 'github.com', 'account': 'octo-user', 'active': True,
                                                 'listing_state': 'success'}])
        self.assertNotIn('session', keys(facts) | keys(verdict))


class GithubStateTests(Base):  # item 1b, finding 6
    def answer(self, *entries):
        self.fakes.answer('gh', 'auth', 'status', out=github_hosts(*entries), code=1)

    def test_a_github_error_state_is_invalid_with_its_reason_code_not_expired(self):
        self.answer(('github.com', 'octo-user', 'error', True))
        facts = signin.detect_github(deadline=5)
        self.assertEqual((facts['state'], facts['reason']), ('invalid', 'gh_state_error'))
        verdict = signin_facts.evaluate(facts)
        self.assertEqual((verdict['status'], verdict['usable']), ('invalid', False))
        self.assertIn('(reason: gh_state_error)', verdict['message'])
        self.assertIn('github.com as octo-user', verdict['message'])
        self.assertNotIn('expired', json.dumps(verdict).lower())
        self.assertNotIn('session', json.dumps(verdict).lower())
        report = signin.status_report(TENANT_A, None, 'all', 5)
        self.assertEqual((report['status'], report['github']['status']), ('blocked', 'invalid'))

    def test_a_github_timeout_is_unknown_with_its_reason_code_not_expired(self):
        self.answer(('github.com', 'octo-user', 'timeout', True))
        facts = signin.detect_github(deadline=5)
        self.assertEqual((facts['state'], facts['reason']), ('unknown', 'gh_state_timeout'))
        verdict = signin_facts.evaluate(facts)
        self.assertEqual((verdict['status'], verdict['usable']), ('unknown', False))
        self.assertIn('(reason: gh_state_timeout)', verdict['message'])
        self.assertNotIn('expired', json.dumps(verdict).lower())

    def test_an_error_beside_a_timeout_is_invalid_and_each_host_shows_its_own_state(self):
        self.answer(('github.com', 'octo-user', 'error', True), ('ghe.example.test', 'octo-user', 'timeout', True))
        verdict = signin_facts.evaluate(signin.detect_github(deadline=5))
        self.assertEqual(verdict['status'], 'invalid')
        self.assertIn('github.com as octo-user (gh state: error)', verdict['message'])
        self.assertIn('ghe.example.test as octo-user (gh state: timeout)', verdict['message'])

    def test_several_accounts_on_a_host_name_the_gh_state_not_a_session(self):
        self.fakes.answer('gh', 'auth', 'status', out=github_hosts(('github.com', 'octo-user', 'success', True),
                                                                  ('github.com', 'other-user', 'error', False)))
        verdict = signin_facts.evaluate(signin.detect_github(deadline=5))
        self.assertEqual(verdict['status'], 'several_accounts')
        self.assertIn('octo-user (gh state: success, active)', verdict['message'])
        self.assertIn('other-user (gh state: error)', verdict['message'])
        self.assertNotIn('session', verdict['message'])


class ReadyForTests(Base):  # item 1c, finding 2
    def test_a_ready_report_says_once_what_it_is_ready_for(self):
        report = signin.status_report(TENANT_A, None, 'azure', 5)
        self.assertEqual(report['status'], 'ready')
        self.assertEqual(report['ready_for'], READY_FOR % TENANT_A)
        self.assertEqual(json.dumps(report).count('not known until a read is attempted'), 1)

    def test_a_ready_report_for_both_providers_names_the_github_sign_in_as_well(self):
        self.fakes.answer('gh', 'auth', 'status', out=github_hosts(('github.com', 'octo-user', 'success', True)))
        report = signin.status_report(TENANT_A, None, 'all', 5)
        self.assertEqual(report['status'], 'ready')
        self.assertIn('The Azure CLI sign-in is usable for tenant %s and the GitHub CLI is signed in' % TENANT_A,
                      report['ready_for'])
        self.assertEqual(json.dumps(report).count('not known until a read is attempted'), 1)

    def test_a_report_that_is_not_ready_says_nothing_about_ready(self):
        blocked = signin.status_report(TENANT_B, None, 'azure', 5)
        reported = signin.status_report(None, None, 'azure', 5)
        self.assertEqual((blocked['status'], reported['status']), ('blocked', 'reported'))
        self.assertNotIn('ready_for', blocked)
        self.assertNotIn('ready_for', reported)


class WithheldTests(Base):  # item 2a, finding 8
    def command(self, tenant, policy, output, descriptor):
        if self.mode == 'mkdir-echo':
            return [sys.executable, '-I', '-c', WRITER, output, str(descriptor)]
        return super().command(tenant, policy, output, descriptor)

    def withheld(self):
        result = self.collect()
        self.assertEqual((result['status'], result['error_code']), ('failed', 'collector_output_withheld'))
        self.assertNotIn(self.token, json.dumps(result))
        self.assertIs(result['product_removed_anything'], False)
        self.assertEqual(unmarked(result['next_step']), [])
        self.assertNotIn('rm -r', json.dumps(result))  # changed in 5A round 1: no deletion command is ever printed
        return result

    def test_a_folder_that_appears_is_reported_as_observed_and_left_with_the_exact_step(self):
        self.mode = 'mkdir-echo'
        result = self.withheld()
        self.assertEqual((result['output_present_before'], result['output_present_after']), (False, True))
        self.assertTrue(Path(self.output).is_dir())  # collect never removes the folder
        self.assertIn('intune-iac signin collect --tenant %s --policy %s --output NEW_DIR (' % (TENANT_A, POLICY),
                      result['next_step'])
        self.assertIn('did not remove anything', result['message'])

    def test_a_folder_that_does_not_appear_is_reported_absent(self):
        self.mode = 'echo'
        result = self.withheld()
        self.assertEqual((result['output_present_before'], result['output_present_after']), (False, False))
        self.assertFalse(Path(self.output).exists())
        self.assertIn('intune-iac signin collect --tenant %s --policy %s --output NEW_DIR (' % (TENANT_A, POLICY),
                      result['next_step'])

    def test_a_folder_that_was_there_before_is_reported_as_observed_and_never_offered_for_deletion(self):
        self.mode = 'echo'
        Path(self.output).mkdir()
        result = self.withheld()
        self.assertEqual((result['output_present_before'], result['output_present_after']), (True, True))


class AccountMismatchTests(Base):  # item 2b, finding 9
    def test_the_mismatch_refusal_gives_the_command_that_shows_the_default_account(self):
        verdict = signin_facts.evaluate(signin.detect_azure(deadline=5), TENANT_A, 'sam@example.test')
        self.assertEqual(verdict['status'], 'account_mismatch')
        self.assertIn('az account show --query user.name -o tsv', verdict['next_step'])
        self.assertNotIn('sam@', json.dumps(verdict))
        result = self.collect(account='sam@example.test')
        self.assertIn('az account show --query user.name -o tsv', result['signin']['next_step'])
        self.assertEqual(self.collectors(), [])


class PlaceholderTests(Base):  # item 2c, finding 7
    def azure(self, *accounts, tenant=TENANT_A, account=None):
        self.fakes.answer('az', 'account', 'list', out=azure_list(*accounts))
        return signin_facts.evaluate(signin.detect_azure(deadline=5), tenant, account)['next_step']

    def github(self, out, code=0, err=''):
        self.fakes.answer('gh', 'auth', 'status', out=out, code=code, err=err)
        return signin_facts.evaluate(signin.detect_github(deadline=5))['next_step']

    def steps(self):
        other = azure_account(user='sam@example.test', default=False, sub='s2')
        return {
            'two defaults': self.azure(azure_account(), azure_account(user='sam@example.test', sub='s2')),
            'no default': self.azure(azure_account(default=False)),
            'several accounts': self.azure(azure_account(), other),
            'hidden name': self.azure(azure_account(user=LONG_UPN)),
            'not signed in, no tenant': self.azure(tenant=None),
            'signed in, no tenant': self.azure(azure_account(), tenant=None),
            'account argument not plain': self.azure(azure_account(), account='not a plain name!'),
            'refused at token time, no tenant': signin_facts.refused('expired', None)['next_step'],
            'github several accounts': self.github(github_hosts(('github.com', 'octo-user', 'success', True),
                                                                ('github.com', 'other-user', 'success', False))),
            'github not signed in': self.github('', code=1, err='You are not logged into any GitHub hosts.'),
            'github error': self.github(github_hosts(('github.com', 'octo-user', 'error', True)), code=1),
        }

    def test_every_placeholder_in_a_printed_step_is_marked(self):
        for name, step in self.steps().items():
            with self.subTest(name):
                self.assertEqual(unmarked(step), [], step)

    def test_a_step_that_was_a_sentence_is_now_the_command_to_run(self):
        steps = self.steps()
        for name in ('github several accounts', 'github not signed in', 'github error'):
            with self.subTest(name):
                self.assertNotIn('check again', steps[name])
                self.assertIn('intune-iac signin status --provider github', steps[name])
        self.assertIn('intune-iac signin status --tenant TENANT_ID (', steps['signed in, no tenant'])
        self.assertIn('az account show --query user.name -o tsv', steps['account argument not plain'])


if __name__ == '__main__':
    unittest.main()
