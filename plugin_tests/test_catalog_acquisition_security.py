"""Acquisition selector path confinement; no external requests are made."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('catalog_acquisition_security', ROOT / 'scripts/acquire-skill-catalogs.py')
catalog = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(catalog)


class CatalogAcquisitionSecurityTests(unittest.TestCase):
    def test_invalid_repository_cannot_create_any_paths_or_request_network(self):
        for value in ['..', '.', '../repo', 'owner/..', 'owner/.', '/absolute',
                      'owner/repo/extra', r'owner\repo', 'owner/repo?query',
                      'owner/repo#fragment', 'https://github.com/owner/repo',
                      'owner/%2e%2e', 'owner/repo\n', 'owner/' + 'a' * 101]:
            with self.subTest(value=value), tempfile.TemporaryDirectory() as directory:
                parent = Path(directory); output = parent / 'approved'
                with patch.object(catalog, 'get') as transport:
                    with self.assertRaises(ValueError): catalog.acquire(value, output)
                    transport.assert_not_called()
                self.assertEqual(list(parent.iterdir()), [])

    def test_legitimate_repository_failure_receipt_stays_under_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'approved'
            with patch.object(catalog, 'get', side_effect=RuntimeError('synthetic-network-failure')):
                result = catalog.acquire('cloudposse/atmos', output)
            self.assertEqual(result['status'], 'BLOCKED')
            receipt = output / 'cloudposse__atmos/receipt.json'
            self.assertEqual(json.loads(receipt.read_text()), result)
            self.assertFalse((Path(directory) / 'receipt.json').exists())

    def test_pinned_catalog_and_literal_punctuation_subset_remain_admitted(self):
        for value in [*catalog.REPOS, 'Valid-Owner/.github', 'owner/a_b.c-1']:
            self.assertEqual(catalog.repository_selector(value), value)


if __name__ == '__main__': unittest.main()
