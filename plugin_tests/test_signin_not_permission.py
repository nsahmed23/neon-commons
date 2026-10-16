"""Item 5: a successful sign-in never marks Graph, Intune or state-storage access ready.

Those facts stay unknown until a read actually succeeds. A usable sign-in changes only the next step offered for discovery.
"""
import contextlib
import io
import json
import os
import unittest
from unittest.mock import patch

from intune_iac.readiness import OPERATIONS, readiness
from plugin_tests import test_readiness as tr
from plugin_tests.signin_fakes import FakeClis, TENANT_A, azure_account, azure_list, github_hosts

GOOD = {'provider': 'azure', 'state': 'signed_in', 'reason': None, 'accounts': [
    {'tenant': TENANT_A, 'account': 'alex@example.test', 'cloud': 'AzureCloud', 'default': True, 'listing_state': 'Enabled'}]}
GITHUB = {'provider': 'github', 'state': 'signed_in', 'reason': None,
          'accounts': [{'host': 'github.com', 'account': 'octo-user', 'active': True, 'listing_state': 'success'}]}


def model(signin):
    return readiness(tr.survey_of(tr.repository_item(), tr.context_item(tenant=TENANT_A)), tr.host_report(), tr.doctor_report(),
                     signin=signin)


class NotPermissionTests(unittest.TestCase):
    def test_a_usable_sign_in_leaves_every_access_fact_unknown_in_every_operation(self):
        value = model({'azure': GOOD, 'github': GITHUB})
        for operation in OPERATIONS:
            rows = tr.rows_of(value, operation)
            row = rows['integration_service']
            if not row['needed']:
                continue
            self.assertEqual(row['state'], 'unknown', operation)
            self.assertEqual({k: row['detected'][k] for k in ('graph_access', 'intune_access', 'state_storage_access')},
                             {'graph_access': 'unknown', 'intune_access': 'unknown', 'state_storage_access': 'unknown'})
            self.assertIn('stay unknown until a read actually succeeds', ' '.join(row['missing']))
            self.assertNotIn('ready', [rows[r]['state'] for r in ('backend', 'execution_route', 'secret_input') if rows[r]['needed']])
            self.assertNotEqual(value['operations'][operation]['status'], 'ready', operation)

    def test_the_azure_verdict_is_usable_but_the_row_names_the_match_without_calling_it_access(self):
        value = model({'azure': GOOD})
        row = tr.rows_of(value, 'discover')['integration_service']
        self.assertIn('Signed in to tenant', row['detected']['azure_sign_in'])
        self.assertTrue(value['signin']['azure']['usable'])
        self.assertEqual(row['state'], 'unknown')

    def test_extra_claims_in_the_facts_are_never_copied(self):
        claimed = dict(GOOD, graph='ready', access='granted', accessToken='x')
        value = model({'azure': claimed, 'extra': {'graph': 'ready'}})
        self.assertNotIn('granted', json.dumps(value))
        self.assertNotIn('"ready"', json.dumps(tr.rows_of(value, 'discover')['integration_service']))

    def test_a_change_still_says_a_sign_in_never_implies_permission(self):
        row = tr.rows_of(model({'azure': GOOD}), 'change')['integration_service']
        self.assertIn('never implies permission for a change', ' '.join(row['missing']))

    def test_a_usable_sign_in_offers_the_reuse_route_for_discovery_only(self):
        discover = tr.rows_of(model({'azure': GOOD}), 'discover')['integration_service']
        self.assertIn('intune-iac signin collect --tenant %s --policy POLICY --output NEW_DIR' % TENANT_A, discover['next_action'])
        adopt = tr.rows_of(model({'azure': GOOD}), 'adopt')['integration_service']
        self.assertNotIn('signin collect', adopt['next_action'])

    def test_signin_status_reports_access_unknown_and_the_listing_as_the_only_command(self):
        fakes = FakeClis()
        self.addCleanup(fakes.cleanup)
        fakes.answer('az', 'account', 'list', out=azure_list(azure_account()))
        fakes.answer('gh', 'auth', 'status', out=github_hosts(('github.com', 'octo-user', 'success', True)))
        from intune_iac.cli import main
        out = io.StringIO()
        with patch.dict(os.environ, {'PATH': fakes.path_entry() + os.pathsep + os.environ.get('PATH', '')}), \
                contextlib.redirect_stdout(out):
            code = main(['signin', 'status', '--tenant', TENANT_A, '--provider', 'all'])
        value = json.loads(out.getvalue())
        self.assertEqual((code, value['status']), (0, 'ready'))
        self.assertEqual(value['access'], {'graph': 'unknown', 'intune': 'unknown', 'state_storage': 'unknown'})
        self.assertEqual(fakes.calls(), ['account list --output json', 'auth status --json hosts'])


if __name__ == '__main__':
    unittest.main()
