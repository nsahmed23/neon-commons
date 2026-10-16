"""PKG-SETUP-5B item 2 (finding 7): a sovereign-cloud sign-in is refused, with the next step.
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


class CloudTests(Base):  # item 7
    def verdict(self, cloud):
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(cloud=cloud)))
        return signin_facts.evaluate(signin.detect_azure(deadline=5), TENANT_A)

    def test_a_sovereign_cloud_is_not_usable_and_the_next_step_is_exact(self):
        for cloud in ('AzureChinaCloud', 'AzureUSGovernment', 'AzureGermanCloud'):
            verdict = self.verdict(cloud)
            self.assertEqual((verdict['status'], verdict['usable']), ('unknown', False), cloud)
            self.assertIn(cloud, verdict['message'])
            self.assertIn('public Azure cloud', verdict['message'])
            self.assertIn('az cloud set --name AzureCloud', verdict['next_step'])
            self.assertIn('az login --tenant %s' % TENANT_A, verdict['next_step'])

    def test_the_public_cloud_is_still_usable(self):
        verdict = self.verdict('AzureCloud')
        self.assertEqual((verdict['status'], verdict['usable']), ('signed_in', True))

    def test_collect_in_a_sovereign_cloud_mints_no_token(self):
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(cloud='AzureUSGovernment')))
        result = self.collect()
        self.assertEqual((result['status'], result['signin']['status']), ('blocked', 'unknown'))
        self.assertEqual(self.fakes.calls(), [LISTING])
        self.assertEqual(self.collectors(), [])
        report = signin.status_report(TENANT_A, None, 'azure', 5)
        self.assertEqual(report['status'], 'blocked')


if __name__ == '__main__':
    unittest.main()
