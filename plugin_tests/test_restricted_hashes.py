"""Restricted low-entropy values must not be exposed through per-field hashes."""
import copy
import json
import unittest

from intune_iac.io import digest
from intune_iac.production import normalize
from intune_iac.production_oracle import compare
from plugin_tests.test_production import inputs


class RestrictedHashesTests(unittest.TestCase):
    def test_private_pin_and_containers_have_no_public_value_hash(self):
        source, context = inputs()
        source['collections'][0]['pages'][0]['body']['value'][0]['private_pin'] = '0042'
        normalized = normalize(source, context)
        rows = normalized['field_accounting']
        self.assertNotIn(digest('0042'), {row['source_value_sha256'] for row in rows})
        self.assertTrue(all(row['source_value_sha256'] is None for row in rows if row['classification'] == 'restricted_source'))
        self.assertFalse(normalized['candidate_mapping_complete'])
        self.assertEqual(compare(json.dumps(source).encode(), normalized, context=context), [])

    def test_unselected_value_hash_is_not_a_dictionary_oracle(self):
        source, context = inputs()
        source['collections'][0]['pages'][0]['body']['value'][1]['private_pin'] = '0042'
        normalized = normalize(source, context)
        self.assertNotIn(digest('0042'), json.dumps(normalized))
        self.assertTrue(normalized['candidate_mapping_complete'])
        self.assertEqual(compare(json.dumps(source).encode(), normalized, context=context), [])

    def test_oracle_rejects_reintroducing_restricted_digest(self):
        source, context = inputs()
        source['private_pin'] = '0042'
        normalized = normalize(source, context)
        changed = copy.deepcopy(normalized)
        row = next(row for row in changed['field_accounting'] if row['classification'] == 'restricted_source')
        row['source_value_sha256'] = digest('0042')
        self.assertTrue(compare(json.dumps(source).encode(), changed, context=context))

    def test_visible_scalar_mapping_and_container_suppression(self):
        source, context = inputs()
        normalized = normalize(source, context)
        from hashlib import sha256
        root_ref = sha256(b'').hexdigest()
        root = next(row for row in normalized['field_accounting'] if row['source_node_ref'] == root_ref)
        self.assertIsNone(root['source_value_sha256'])
        self.assertTrue(any(row['source_value_sha256'] == digest(source['tenant_id']) for row in normalized['field_accounting']))
