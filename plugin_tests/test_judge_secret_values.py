"""The judge checks values and keys, not only key names, before anything leaves for the external model service.

The scan refuses common credential forms. It cannot prove a secret is absent (one split across fields, or in an
unrecognized format, passes), and these tests do not claim otherwise.
"""
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

    def refused(self, evidence, code='secret_shaped_value', location=None, claim='The setting is enabled.', secret=None):
        self.judge.requests.clear()
        result = self.judge.call(claim=claim, evidence=evidence)
        self.judge.assert_safe(result, code)
        self.assertEqual(self.judge.requests, [], 'nothing may be sent when a secret-shaped value is found')
        if location is not None:
            self.assertEqual(result['location'], location)
        if secret is not None:
            self.assertNotIn(secret, json.dumps(result), 'the refusal repeated the secret')
        self.assertRegex(result['location'], r'\A\$\.(?:claim|request\.model|evidence(?:[\[{]\d+[\]}])*)\Z',
                         'a location holds positions only, never key text')
        return result

    def test_canary_under_an_innocent_key_refuses_with_a_position_and_never_the_value(self):
        canary = shaped('judge')
        # keys sort as detail, id, text: detail is member 0 of item 0
        result = self.refused([{'id': 'record-1', 'text': 'enabled', 'detail': canary}], location='$.evidence[0]{0}',
                              secret=canary)
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
                self.refused({'section': {'items': ['ok', {'note': value}]}}, location='$.evidence{0}{0}[1]{0}',
                             secret=value)

    def test_sols_breaking_inputs_are_refused_with_locations_that_do_not_contain_them(self):
        hex64 = secrets.token_hex(32)
        password = 'CorrectHorse' + secrets.token_urlsafe(6).replace('-', 'x').replace('_', 'y') + 'Staple'
        account_key = __import__('base64').b64encode(secrets.token_bytes(48)).decode().replace('0', 'a').replace('1', 'b')
        for name, evidence, location, secret in (
                ('64 hex under detail', {'detail': hex64}, '$.evidence{0}', hex64),
                ('url with a password', {'detail': 'https://alice:' + password + '@db.example'}, '$.evidence{0}', password),
                ('storage connection string', {'detail': 'DefaultEndpointsProtocol=https;AccountName=x;AccountKey=' + account_key},
                 '$.evidence{0}', account_key),
                ('connection string, other keyword', {'detail': 'Server=a;Password=' + password}, '$.evidence{0}', password),
                ('sas signature', {'detail': 'https://x.blob.core.windows.net/c?sv=2022&sig=' + secrets.token_urlsafe(20)},
                 '$.evidence{0}', None),
                ('base64 run without digits', {'detail': 'AbCdEfGhIjKlMnOpQrStUvWxYzAbCdEfGhIjKlMnOpQrStUvWxYzQqWwEeRrTtYy'},
                 '$.evidence{0}', None),
        ):
            with self.subTest(name):
                self.refused(evidence, location=location, secret=secret)

    def test_a_secret_used_as_a_key_is_refused_and_never_echoed(self):
        key = 'CorrectHorseBatteryStaple'
        self.refused({key: 'ghp_' + secrets.token_hex(12)}, location='$.evidence{0}', secret=key)
        long_key = shaped('keyname')
        self.refused({long_key: 'fine'}, location='$.evidence{0}', secret=long_key)
        plain_key_secret_value = 'hunter2hunter2'
        self.refused({'password': plain_key_secret_value}, location='$.evidence{0}', secret=plain_key_secret_value)

    def test_percent_encoded_secrets_are_refused(self):
        token = 'ghp_' + secrets.token_hex(18)
        encoded = ''.join('%{:02X}'.format(b) for b in token.encode())
        self.refused({'detail': 'see ' + encoded}, location='$.evidence{0}', secret=encoded)
        self.refused({'detail': 'client%5Fsecret%3D' + secrets.token_hex(10)}, location='$.evidence{0}')

    def test_digests_and_commit_ids_are_sent_under_digest_named_keys(self):
        evidence = [{'id': 'record-1', 'sha256': secrets.token_hex(32), 'commit': secrets.token_hex(20),
                     'source_sha512': secrets.token_hex(64), 'head': secrets.token_hex(20),
                     'integrity': {'fingerprint': secrets.token_hex(32)},
                     'recorded': 'sha256:' + secrets.token_hex(32), 'text': 'enabled'}]
        self.judge.requests.clear()
        result = self.judge.call(evidence=evidence)
        self.assertEqual(result['status'], 'assessed', result)
        self.assertEqual(len(self.judge.requests), 1)
        # the same digest under any other key is refused
        self.refused([{'note': secrets.token_hex(32)}], location='$.evidence[0]{0}')

    def test_product_identifier_forms_are_not_secrets_but_a_bare_hex_run_still_is(self):
        policy_key = 'p_' + secrets.token_hex(16) + '_' + secrets.token_hex(16)
        guid = '3f2504e0-4f89-41d3-9a0c-0305e82c3301'
        self.judge.requests.clear()
        result = self.judge.call(evidence=[{policy_key: {'ref': policy_key, 'tenant': guid, 'note': 'see ' + guid}}])
        self.assertEqual(result['status'], 'assessed', result)
        self.assertEqual(len(self.judge.requests), 1)
        bare = secrets.token_hex(16)
        self.refused([{'note': bare}], location='$.evidence[0]{0}', secret=bare)
        self.refused([{'note': 'x ' + policy_key}], location='$.evidence[0]{0}')

    def test_the_claim_is_checked_too(self):
        claim = 'The token ' + shaped('claim') + ' is valid.'
        result = self.refused([{'id': 'record-1'}], location='$.claim', claim=claim, secret=claim)

    def test_the_configured_api_key_value_is_refused_even_when_it_is_not_secret_shaped(self):
        self.judge.config['api_key_env'] = 'CLM_TEST_KEY'
        with patch.dict(os.environ, {'CLM_TEST_KEY': 'plainkey123'}):
            self.refused([{'id': 'record-1', 'text': 'value plainkey123 here'}], code='credential_value_in_evidence',
                         location='$.evidence[0]{1}', secret='plainkey123')

    def test_every_configurable_payload_string_is_scanned_not_only_claim_and_evidence(self):
        for alias_value in ('Server=a;Password=' + secrets.token_hex(8), 'ghp_' + secrets.token_hex(18),
                            'plainkey123'):
            with self.subTest(alias=alias_value[:8]):
                self.setUp()
                self.judge.config['model_identity']['alias'] = alias_value
                self.judge.config['api_key_env'] = 'CLM_TEST_KEY'
                with patch.dict(os.environ, {'CLM_TEST_KEY': 'plainkey123'}):
                    result = self.judge.call()
                self.assertEqual(self.judge.requests, [])
                self.assertIn(result['reason_code'], ('secret_shaped_value', 'credential_value_in_evidence'))
                self.assertEqual(result['location'], '$.request.model')
                self.assertNotIn(alias_value, json.dumps(result))

    def test_the_api_key_is_read_once_and_the_same_value_is_used_and_checked(self):
        self.judge.config['api_key_env'] = 'CLM_TEST_KEY'
        reads = []
        real = os.environ.get

        def counting(name, default=None):
            if name == 'CLM_TEST_KEY':
                reads.append(name)
            return real(name, default)

        with patch.dict(os.environ, {'CLM_TEST_KEY': 'plainkey123'}), patch.object(os.environ, 'get', counting):
            result = self.judge.call()
        self.assertEqual(result['status'], 'assessed')
        self.assertEqual(len(reads), 1)
        self.assertEqual(self.judge.requests[0]['authorization'], 'Bearer plainkey123')
        self.assertNotIn('plainkey123', json.dumps(self.judge.requests[0]['body']))

    def test_ordinary_evidence_is_still_sent(self):
        evidence = [{'id': '11111111-1111-4111-8111-111111111111', 'sha256': 'a' * 64,
                     'resource': '/subscriptions/22222222-2222-4222-8222-222222222222/resourceGroups/rg/providers/'
                                 'Microsoft.Storage/storageAccounts/syntheticstate',
                     'setting': 'device_vendor_msft_policy_config_defender_allowrealtimemonitoring',
                     'type': '#microsoft.graph.deviceManagementConfigurationPolicyAssignmentTarget',
                     'url': 'https://graph.microsoft.com/beta/deviceManagement/configurationPolicies/abc',
                     'name': 'Windows baseline policy for the finance organizational unit', 'token_required': 'yes'}]
        result = self.judge.call(evidence=evidence)
        self.assertEqual(result['status'], 'assessed', result)
        self.assertEqual(len(self.judge.requests), 1)

    def test_existing_refusal_codes_are_unchanged(self):
        self.judge.assert_safe(self.judge.call(evidence=[]), 'empty_evidence')
        self.judge.assert_safe(self.judge.call(evidence='text'), 'invalid_evidence')


if __name__ == '__main__':
    unittest.main()
