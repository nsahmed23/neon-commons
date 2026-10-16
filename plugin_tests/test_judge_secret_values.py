"""The judge checks values, not only key names, before evidence leaves for the external model service."""
import json
import os
import secrets
import unittest
from unittest.mock import patch

from plugin_tests import test_judge


def shaped(label):
    return label + '-' + secrets.token_urlsafe(30) + 'A1'


class JudgeSecretValueTests(unittest.TestCase):
    def setUp(self):
        # Reuse the real local fake endpoint and pinned config from the judge tests.
        self.judge = test_judge.JudgeTests('setUp')
        self.judge.setUp()
        self.addCleanup(self.judge.tearDown)

    def refused(self, evidence, code='secret_shaped_value', location=None, claim='The setting is enabled.'):
        result = self.judge.call(claim=claim, evidence=evidence)
        self.judge.assert_safe(result, code)
        self.assertEqual(self.judge.requests, [], 'nothing may be sent when a secret-shaped value is found')
        if location is not None:
            self.assertEqual(result['location'], location)
        return result

    def test_canary_under_an_innocent_key_refuses_with_a_path_and_never_the_value(self):
        canary = shaped('judge')
        result = self.refused([{'id': 'record-1', 'text': 'enabled', 'detail': canary}], location='$.evidence[0].detail')
        self.assertNotIn(canary, json.dumps(result))
        self.assertEqual(result['status'], 'unavailable')

    def test_each_secret_shape_is_refused_wherever_it_sits(self):
        header = 'eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9'
        jwt = header + '.eyJ0aWQiOiIxMTExMTExMS0xMTExLTQxMTEtODExMS0xMTExMTExMTExMTEiLCJleHAiOjE3MDAwMDAwMDB9.' + 'c2lnbmF0dXJl' * 4
        samples = {
            'jwt': jwt,
            'bearer header text': 'Authorization: Bearer ' + secrets.token_urlsafe(24),
            'private key': '-----BEGIN RSA PRIVATE KEY-----\nMIIEow',
            'github token': 'ghp_' + secrets.token_hex(18),
            'github fine grained': 'github_pat_' + secrets.token_urlsafe(30).replace('-', 'x'),
            'aad client secret': 'abc8Q~' + secrets.token_urlsafe(24).replace('-', 'x'),
            'assignment in prose': 'the client_secret = ' + secrets.token_hex(8) + '7 was set',
            'generic random token': secrets.token_urlsafe(33) + 'Aa1',
        }
        for name, value in samples.items():
            with self.subTest(name):
                self.judge.requests.clear()
                result = self.refused({'section': {'items': ['ok', {'note': value}]}},
                                      location='$.evidence.section.items[1].note')
                self.assertNotIn(value, json.dumps(result))

    def test_a_secret_shaped_key_name_is_never_echoed_in_the_location(self):
        key = shaped('keyname')
        result = self.refused({key: shaped('value')})
        self.assertNotIn(key, json.dumps(result))
        self.assertEqual(result['location'], '$.evidence.<key>')

    def test_the_claim_is_checked_too(self):
        claim = 'The token ' + shaped('claim') + ' is valid.'
        result = self.refused([{'id': 'record-1'}], code='secret_shaped_value', location='$.claim', claim=claim)
        self.assertNotIn(claim, json.dumps(result))

    def test_the_configured_api_key_value_is_refused_even_when_it_is_not_secret_shaped(self):
        self.judge.config['api_key_env'] = 'CLM_TEST_KEY'
        with patch.dict(os.environ, {'CLM_TEST_KEY': 'plainkey123'}):
            result = self.refused([{'id': 'record-1', 'text': 'value plainkey123 here'}],
                                  code='credential_value_in_evidence', location='$.evidence[0].text')
        self.assertNotIn('plainkey123', json.dumps(result))

    def test_ordinary_evidence_is_still_sent(self):
        evidence = [{'id': '11111111-1111-4111-8111-111111111111', 'sha256': 'a' * 64,
                     'resource': '/subscriptions/22222222-2222-4222-8222-222222222222/resourceGroups/rg/providers/'
                                 'Microsoft.Storage/storageAccounts/syntheticstate',
                     'setting': 'device_vendor_msft_policy_config_defender_allowrealtimemonitoring',
                     'url': 'https://graph.microsoft.com/beta/deviceManagement/configurationPolicies/abc',
                     'name': 'Windows baseline policy for the finance organizational unit', 'token_required': 'yes'}]
        result = self.judge.call(evidence=evidence)
        self.assertEqual(result['status'], 'assessed')
        self.assertEqual(len(self.judge.requests), 1)

    def test_existing_refusal_codes_are_unchanged(self):
        self.judge.assert_safe(self.judge.call(evidence=[]), 'empty_evidence')
        self.judge.assert_safe(self.judge.call(evidence='text'), 'invalid_evidence')


if __name__ == '__main__':
    unittest.main()
