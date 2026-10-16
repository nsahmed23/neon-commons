"""PKG-SETUP-5A fix round 1 (Sol's review): five items, each with its own tests.

1 folder provenance: only what was observed   2 GitHub hosts aggregated fail-closed   3 Azure Expired is subscription state
4 withheld wording                            5 one access statement in a ready report
Fake az and gh and a fake collecting child stand in for the real ones; no canary or token value is ever printed.
"""
import json
from pathlib import Path
import sys
import unittest

from intune_iac import cli, signin, signin_facts
from plugin_tests.signin_fakes import TENANT_A, azure_account, azure_list, github_hosts
from plugin_tests.test_signin_fix1 import Base, LISTING, POLICY

# Child programs for the folder cases: each reads what it was given on the descriptor, acts on the output path, then echoes it
# (so the output is withheld). argv: output path, descriptor number.
CHILD_MKDIR = ('import os, sys; r = os.read(int(sys.argv[2]), 8192); os.mkdir(sys.argv[1]); sys.stdout.write(r.decode())')
CHILD_SYMLINK = ('import os, sys; r = os.read(int(sys.argv[2]), 8192); os.symlink("/", sys.argv[1]); sys.stdout.write(r.decode())')
CHILD_MKDIR_RMDIR = ('import os, sys; r = os.read(int(sys.argv[2]), 8192); os.mkdir(sys.argv[1]); os.rmdir(sys.argv[1]); '
                     'sys.stdout.write(r.decode())')
CHILD_RMDIR = ('import os, sys; r = os.read(int(sys.argv[2]), 8192); os.rmdir(sys.argv[1]); sys.stdout.write(r.decode())')
CHILD_NOTHING = ('import os, sys; r = os.read(int(sys.argv[2]), 8192); sys.stdout.write(r.decode())')
PROGRAMS = {'mkdir': CHILD_MKDIR, 'symlink': CHILD_SYMLINK, 'mkdir-rmdir': CHILD_MKDIR_RMDIR, 'rmdir': CHILD_RMDIR,
            'nothing': CHILD_NOTHING}


class FolderTests(Base):  # item 1
    def command(self, tenant, policy, output, descriptor):
        if self.mode in PROGRAMS:
            return [sys.executable, '-I', '-c', PROGRAMS[self.mode], output, str(descriptor)]
        return super().command(tenant, policy, output, descriptor)

    def withheld(self, mode, precreate=False):
        self.mode = mode
        if precreate:
            Path(self.output).mkdir()
        result = self.collect()
        self.assertEqual((result['status'], result['error_code']), ('failed', 'collector_output_withheld'))
        blob = json.dumps(result)
        self.assertNotIn(self.token, blob)
        self.assertNotIn('rm -r', blob)
        self.assertNotIn('rm ', blob.replace('form ', ''))
        self.assertNotIn('Delete', blob)
        for inferred in ('output_folder', 'output_removed', 'written', 'existed_before', 'not_written', 'left as it was found'):
            self.assertNotIn(inferred, blob, inferred)
        return result

    def test_a_folder_that_appears_is_reported_as_observed_not_as_written_by_the_collector(self):
        result = self.withheld('mkdir')
        self.assertEqual((result['output_present_before'], result['output_present_after'], result['output_kind_after']),
                         (False, True, 'directory'))
        self.assertTrue(Path(self.output).is_dir())  # still there: the product removes nothing
        self.assertIs(result['product_removed_anything'], False)
        self.assertIn('did not remove anything', result['message'])

    def test_a_symlink_that_appears_is_reported_as_a_symlink(self):
        result = self.withheld('symlink')
        self.assertEqual((result['output_present_before'], result['output_present_after'], result['output_kind_after']),
                         (False, True, 'symlink'))
        self.assertTrue(Path(self.output).is_symlink())
        self.assertIn('symbolic link', result['message'])

    def test_a_folder_that_was_created_and_removed_is_not_called_not_written(self):
        result = self.withheld('mkdir-rmdir')
        self.assertEqual((result['output_present_before'], result['output_present_after'], result['output_kind_after']),
                         (False, False, 'absent'))
        self.assertNotIn('was not written', result['message'])

    def test_a_folder_that_was_there_and_is_gone_is_not_called_left_as_found(self):
        result = self.withheld('rmdir', precreate=True)
        self.assertEqual((result['output_present_before'], result['output_present_after']), (True, False))
        self.assertNotIn('as it was found', result['message'])

    def test_a_folder_there_before_and_after_is_reported_as_observed(self):
        result = self.withheld('nothing', precreate=True)
        self.assertEqual((result['output_present_before'], result['output_present_after'], result['output_kind_after']),
                         (True, True, 'directory'))

    def test_nothing_appearing_is_reported_as_absent_and_the_rerun_step_names_a_new_folder(self):
        result = self.withheld('nothing')
        self.assertEqual((result['output_present_before'], result['output_present_after'], result['output_kind_after']),
                         (False, False, 'absent'))
        self.assertIn('intune-iac signin collect --tenant %s --policy %s --output NEW_DIR (' % (TENANT_A, POLICY),
                      result['next_step'])
        self.assertIn('a folder that does not exist yet', result['next_step'])


class GithubHostsTests(Base):  # item 2
    def answer(self, *entries):
        self.fakes.answer('gh', 'auth', 'status', out=github_hosts(*entries), code=1)

    def test_success_on_one_host_and_error_on_another_is_invalid_not_signed_in(self):
        self.answer(('github.com', 'octo-user', 'success', True), ('ghe.example.test', 'other-user', 'error', True))
        facts = signin.detect_github(deadline=5)
        self.assertEqual((facts['state'], facts['reason']), ('invalid', 'gh_state_error'))
        verdict = signin_facts.evaluate(facts)
        self.assertEqual((verdict['status'], verdict['usable']), ('invalid', False))
        self.assertIn('(reason: gh_state_error)', verdict['message'])
        self.assertIn('ghe.example.test as other-user (gh state: error)', verdict['message'])

    def test_success_on_one_host_and_timeout_on_another_is_unknown(self):
        self.answer(('github.com', 'octo-user', 'success', True), ('ghe.example.test', 'other-user', 'timeout', True))
        facts = signin.detect_github(deadline=5)
        self.assertEqual((facts['state'], facts['reason']), ('unknown', 'gh_state_timeout'))
        verdict = signin_facts.evaluate(facts)
        self.assertEqual((verdict['status'], verdict['usable']), ('unknown', False))
        self.assertIn('(reason: gh_state_timeout)', verdict['message'])

    def test_error_beats_timeout_and_all_success_is_signed_in(self):
        self.answer(('github.com', 'a-user', 'success', True), ('h2.example.test', 'b-user', 'timeout', True),
                    ('h3.example.test', 'c-user', 'error', True))
        self.assertEqual(signin_facts.evaluate(signin.detect_github(deadline=5))['status'], 'invalid')
        self.answer(('github.com', 'a-user', 'success', True), ('h2.example.test', 'b-user', 'success', True))
        self.assertEqual(signin_facts.evaluate(signin.detect_github(deadline=5))['status'], 'signed_in')

    def test_provider_all_is_not_ready_when_another_host_failed(self):
        for state, expected in (('error', 'invalid'), ('timeout', 'unknown')):
            self.answer(('github.com', 'octo-user', 'success', True), ('ghe.example.test', 'other-user', state, True))
            report = signin.status_report(TENANT_A, None, 'all', 5)
            self.assertEqual(report['azure']['status'], 'signed_in')
            self.assertEqual((report['status'], report['github']['status']), ('blocked', expected), state)
            self.assertNotIn('ready_for', report)

    def test_facts_that_claim_signed_in_over_a_failed_host_are_judged_by_their_entries(self):
        facts = {'provider': 'github', 'state': 'signed_in', 'reason': None, 'accounts': [
            {'host': 'github.com', 'account': 'octo-user', 'active': True, 'listing_state': 'success', 'group': 0},
            {'host': 'ghe.example.test', 'account': 'other-user', 'active': True, 'listing_state': 'error', 'group': 0}]}
        self.assertEqual(signin_facts.evaluate(facts)['status'], 'invalid')


class SubscriptionStateTests(Base):  # item 3
    def listing(self, *rows):
        self.fakes.answer('az', 'account', 'list', out=azure_list(*rows))
        return signin.detect_azure(deadline=5)

    def test_an_expired_listing_state_is_subscription_metadata_not_sign_in_expiry(self):
        facts = self.listing(azure_account(state='Expired'))
        self.assertEqual([a['listing_state'] for a in facts['accounts']], ['Expired'])
        self.assertNotEqual(facts['state'], 'expired')
        verdict = signin_facts.evaluate(facts, TENANT_A)
        self.assertEqual((verdict['status'], verdict['usable']), ('subscription_expired', False))
        self.assertIn('subscription', verdict['message'])
        self.assertNotIn('sign-in reports itself expired', verdict['message'])
        self.assertIn('does not show whether the sign-in itself has expired', verdict['message'])
        self.assertIn('az account set --subscription', verdict['next_step'])
        self.assertIn('az login --tenant %s' % TENANT_A, verdict['next_step'])

    def test_it_runs_no_token_command_and_collect_is_blocked(self):
        self.listing(azure_account(state='Expired'))
        (self.fakes.directory / 'calls.log').unlink(missing_ok=True)  # the helper's own listing
        result = self.collect()
        self.assertEqual((result['status'], result['signin']['status']), ('blocked', 'subscription_expired'))
        self.assertEqual(self.fakes.calls(), [LISTING])  # the listing only: no token command
        report = signin.status_report(TENANT_A, None, 'azure', 5)
        self.assertEqual((report['status'], report['azure']['status']), ('blocked', 'subscription_expired'))

    def test_session_expiry_is_still_reported_by_the_token_request(self):
        verdict = signin_facts.refused('expired', TENANT_A)
        self.assertEqual(verdict['status'], 'expired')

    def test_rows_of_one_account_with_different_states_are_refused_not_resolved_by_order(self):
        for rows in ((azure_account(state='Enabled', sub='s1'), azure_account(state='Expired', sub='s2', default=False)),
                     (azure_account(state='Expired', sub='s1'), azure_account(state='Enabled', sub='s2', default=False))):
            facts = self.listing(*rows)
            self.assertEqual((facts['state'], facts['reason']), ('unknown', 'account_state_ambiguous'))
            verdict = signin_facts.evaluate(facts, TENANT_A)
            self.assertEqual((verdict['status'], verdict['usable']), ('unknown', False))

    def test_rows_of_one_account_with_the_same_state_still_merge(self):
        facts = self.listing(azure_account(sub='s1'), azure_account(sub='s2', default=False))
        self.assertEqual((facts['state'], len(facts['accounts'])), ('signed_in', 1))


class WithheldWordingTests(Base):  # item 4
    def test_credential_shaped_text_that_is_not_the_token_is_not_called_the_access_token(self):
        self.mode = 'shapednote'
        result = self.collect()
        self.assertEqual((result['status'], result['error_code']), ('failed', 'collector_output_withheld'))
        self.assertIn('contained the token or credential-shaped text and was withheld', result['message'])
        self.assertNotIn('printed the access token', result['message'])
        self.assertNotIn('itself prints', result['next_step'])
        self.assertEqual(result['token_match'], 'fragment_or_shape')

    def test_a_split_token_is_fragments_not_a_full_match(self):
        self.mode = 'split'
        result = self.collect()
        self.assertEqual(result['error_code'], 'collector_output_withheld')
        self.assertEqual(result['token_match'], 'fragment_or_shape')
        self.assertIn('contained the token or credential-shaped text and was withheld', result['message'])

    def test_an_exact_full_token_match_may_say_the_access_token(self):
        for mode in ('echo', 'rawecho'):
            self.mode = mode
            result = self.collect()
            self.assertEqual(result['error_code'], 'collector_output_withheld', mode)
            self.assertEqual(result['token_match'], 'full_token', mode)
            self.assertIn('access token', result['message'], mode)
            self.assertNotIn(self.token, json.dumps(result))


class OneAccessStatementTests(Base):  # item 5
    def test_a_ready_report_has_ready_for_as_the_only_access_statement(self):
        report = signin.status_report(TENANT_A, None, 'azure', 5)
        self.assertEqual(report['status'], 'ready')
        self.assertNotIn('note', report)
        self.assertNotIn('access', report)
        text = json.dumps(report).lower()
        self.assertEqual(text.count('state-storage'), 1)
        self.assertEqual(text.count('state_storage'), 0)
        self.assertIn('state-storage access', report['ready_for'])

    def test_a_report_that_is_not_ready_keeps_the_general_note_and_the_access_facts(self):
        blocked = signin.status_report(TENANT_A, None, 'azure', 5) if False else None
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(tenant='33333333-3333-4333-8333-333333333333')))
        blocked = signin.status_report(TENANT_A, None, 'azure', 5)
        self.assertEqual(blocked['status'], 'blocked')
        self.assertIn('note', blocked)
        self.assertEqual(blocked['access'], {'graph': 'unknown', 'intune': 'unknown', 'state_storage': 'unknown'})


if __name__ == '__main__':
    unittest.main()
