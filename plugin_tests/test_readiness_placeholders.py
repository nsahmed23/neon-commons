"""PKG-SETUP-5C item 6: every placeholder the readiness rows print is marked as one, and a known tenant is printed, not TENANT_ID.

A placeholder is marked by a legend in brackets after the command ("POLICY is the policy id ..."), never inside the command, so
the command itself stays one parsable run of words. The sign-in steps mark theirs the same way (signin_facts).
Also the confirmation of item 5: the Azure expired wording rests on the listing's subscription state, from the source.
"""
import re
import unittest

from plugin_tests.test_readiness import (OPERATIONS, TENANT, context_item, doctor_report, export_item, host_report, rows_of,
                                         survey_of)

PLACEHOLDERS = ('POLICY', 'NEW_DIR', 'TOKEN_VARIABLE_NAME', 'TARGET_JSON', 'FD', 'TENANT_ID')


def model(*items):
    from intune_iac.readiness import readiness
    return readiness(survey_of(*items), host_report(), doctor_report())


def printed_strings(value):
    """Every action and missing note the rows print, with where it came from."""
    for operation in OPERATIONS:
        for row_id, row in rows_of(value, operation).items():
            yield '%s/%s/next_action' % (operation, row_id), row['next_action']
            for index, note in enumerate(row['missing']):
                yield '%s/%s/missing/%d' % (operation, row_id, index), note


def used(text):
    return [name for name in PLACEHOLDERS if re.search(r'(?<![A-Z_])%s(?![A-Z_])' % name, text)]


class MarkedPlaceholderTests(unittest.TestCase):
    def check_all_marked(self, value):
        seen = 0
        for where, text in printed_strings(value):
            for name in used(text):
                seen += 1
                self.assertIn('%s is ' % name, text, '%s: %s is printed with no legend' % (where, name))
        return seen

    def test_every_placeholder_in_every_printed_step_has_its_meaning_after_the_command(self):
        for items in ((), (context_item(),), (context_item(tenant=TENANT), export_item(tenant='44444444-4444-4444-8444-444444444444'))):
            self.assertGreater(self.check_all_marked(model(*items)), 4)

    def test_the_legend_sits_after_the_command_so_the_command_stays_whole(self):
        action = rows_of(model(), 'discover')['secret_input']['next_action']
        command = action.split(' (')[0]
        self.assertTrue(command.endswith('--token-env TOKEN_VARIABLE_NAME'), command)
        self.assertIn('--policy POLICY --output NEW_DIR', command)

    def test_the_meanings_are_plain_words(self):
        text = rows_of(model(), 'discover')['secret_input']['next_action']
        for phrase in ('POLICY is the policy id', 'NEW_DIR is a folder that does not exist yet',
                       'TOKEN_VARIABLE_NAME is the name of the environment variable that holds your read token'):
            self.assertIn(phrase, text)
        text = rows_of(model(), 'change')['secret_input']['next_action']
        self.assertIn('TARGET_JSON is the path of your target JSON file', text)
        self.assertIn('FD is a file descriptor number', text)

    def test_a_known_single_tenant_is_printed_instead_of_the_placeholder_in_every_row(self):
        value = model(context_item(tenant=TENANT))
        for operation in ('discover',):
            rows = rows_of(value, operation)
            for row_id in ('integration_service', 'secret_input'):
                text = rows[row_id]['next_action']
                self.assertIn('--tenant %s ' % TENANT, text, row_id)
                self.assertNotIn('TENANT_ID', text, row_id)

    def test_an_unknown_tenant_keeps_the_placeholder_and_marks_it(self):
        text = rows_of(model(), 'discover')['secret_input']['next_action']
        self.assertIn('--tenant TENANT_ID', text)
        self.assertIn('TENANT_ID is the tenant id', text)

    def test_the_integration_service_command_marks_its_placeholders_too(self):
        text = rows_of(model(context_item()), 'discover')['integration_service']['next_action']
        self.assertIn('POLICY is the policy id', text)
        self.assertIn('NEW_DIR is a folder that does not exist yet', text)

    def test_the_offered_signin_collect_marks_policy_and_new_dir_and_keeps_the_known_tenant(self):
        from intune_iac.readiness import readiness
        from plugin_tests.test_signin_tenant import azure
        value = readiness(survey_of(context_item()), host_report(), doctor_report(),
                          signin={'azure': azure((TENANT, 'alex@example.test', True, 'active'))})
        text = rows_of(value, 'discover')['integration_service']['next_action']
        self.assertTrue(text.startswith('intune-iac signin collect --tenant %s --policy POLICY --output NEW_DIR (' % TENANT), text)
        self.assertIn('POLICY is the policy id', text)
        self.assertIn('NEW_DIR is a folder that does not exist yet', text)
        self.assertNotIn('TENANT_ID', text)

    def test_the_backend_step_marks_target_json_and_fd(self):
        text = rows_of(model(), 'adopt')['backend']['next_action']
        self.assertIn('TARGET_JSON is the path of your target JSON file', text)
        self.assertIn('FD is a file descriptor number', text)


class ExpiredWordingConfirmationTests(unittest.TestCase):
    def test_the_azure_expired_verdict_names_the_subscription_state_and_leaves_session_expiry_to_the_token_request(self):
        from intune_iac import signin_facts
        facts = {'provider': 'azure', 'state': 'subscription_expired', 'reason': None, 'accounts': [
            {'tenant': TENANT, 'account': 'alex@example.test', 'cloud': 'AzureCloud', 'default': True, 'listing_state': 'Expired'}]}
        verdict = signin_facts.evaluate(facts, TENANT)
        self.assertEqual(verdict['status'], 'subscription_expired')
        self.assertIn('state of the subscription', verdict['message'])
        self.assertIn('a token request shows that', verdict['message'])
        self.assertNotIn('reports itself expired', verdict['message'])


if __name__ == '__main__':
    unittest.main()
