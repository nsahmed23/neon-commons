"""PKG-SETUP-5B item 3 (finding 8): the token is bound to the account that was judged; unverified claims may only refuse.
"""
import argparse
import contextlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from intune_iac import cli, signin, signin_facts
from intune_iac.io import AppError
from plugin_tests.signin_5b_common import Base, NIL, RealCaptureBase, jwt
from plugin_tests.signin_fakes import TENANT_A, TENANT_B, azure_account, azure_list
from plugin_tests.test_signin_fix1 import LISTING, POLICY, token_answer


class BindingTests(Base):  # item 8
    def listing(self, user, kind='user'):
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(user=user)))

    def claims(self, **claims):
        self.token = jwt(tid=TENANT_A, exp=4102444800, **claims)
        self.fakes.answer('az', 'account', 'get-access-token', out=token_answer(self.token))

    def test_a_token_for_another_account_than_the_judged_default_is_refused(self):
        self.listing('alex@example.test')
        self.claims(upn='sam@example.test')
        result = self.collect()
        self.assertEqual((result['status'], result['signin']['status']), ('blocked', 'account_mismatch'))
        self.assertEqual(result['collector_started'], False)
        blob = json.dumps(result)
        self.assertNotIn('sam@', blob)
        self.assertNotIn(self.token, blob)
        self.assertIn('az account show --query user.name -o tsv', result['signin']['next_step'])

    def test_unique_name_is_checked_when_there_is_no_upn(self):
        self.listing('alex@example.test')
        self.claims(unique_name='sam@example.test')
        self.assertEqual(self.collect()['signin']['status'], 'account_mismatch')

    def test_a_matching_claim_passes_ignoring_case(self):
        self.listing('alex@example.test')
        self.claims(upn='ALEX@Example.Test')
        self.assertEqual(self.collect()['status'], 'collected')

    def test_a_service_principal_is_bound_by_its_appid(self):
        app = '77777777-7777-4777-8777-777777777777'
        self.listing(app)
        self.claims(appid='88888888-8888-4888-8888-888888888888')
        self.assertEqual(self.collect()['signin']['status'], 'account_mismatch')
        self.claims(appid=app)
        self.assertEqual(self.collect()['status'], 'collected')

    def test_a_hidden_name_is_bound_through_its_digest(self):
        hidden = 'alexander.morgan@contoso.onmicrosoft.com'
        self.listing(hidden)
        self.claims(upn='someone.else.entirely@contoso.onmicrosoft.com')
        result = self.collect()
        self.assertEqual(result['signin']['status'], 'account_mismatch')
        self.assertNotIn('alexander', json.dumps(result))
        self.assertNotIn('someone', json.dumps(result))
        self.claims(upn=hidden)
        self.assertEqual(self.collect()['status'], 'collected')

    def test_a_token_that_names_no_account_cannot_be_bound_and_is_refused_with_its_own_code(self):
        # PKG-SETUP-5B round 2: missing evidence is not a successful binding; claims may only refuse, and so may their absence.
        self.listing('alex@example.test')
        for label, prepare in (('a JWT with no upn, unique_name or appid', lambda: self.claims()),
                               ('an opaque token', lambda: self.fakes.answer(
                                   'az', 'account', 'get-access-token', out=token_answer('opaque-' + 'A' * 40)))):
            (self.fakes.directory / 'calls.log').unlink(missing_ok=True)
            prepare()
            result = self.collect()
            self.assertEqual((result['status'], result['signin']['status']), ('blocked', 'account_binding_unavailable'), label)
            self.assertEqual(result['collector_started'], False)
            self.assertIn('az login --tenant %s' % TENANT_A, result['signin']['next_step'])
            self.assertNotIn('account_mismatch', json.dumps(result))
            self.assertEqual(self.collectors(), [])
            self.assertEqual(len(self.fakes.calls()), 2)  # the listing and the token request; no second listing

    def test_the_claim_must_actually_match_for_collection_to_proceed(self):
        self.listing('alex@example.test')
        self.claims(upn='alex@example.test')
        self.assertEqual(self.collect()['status'], 'collected')


if __name__ == '__main__':
    unittest.main()
