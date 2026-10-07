"""A scoped dictionary must remain usable when the full inventory is too large."""
import unittest

from intune_iac.io import AppError
from intune_iac.workbench_provenance import dictionary
from plugin_tests.test_workbench_provenance import MemoryStore, OBJECT, DEFINITION


class LargeInventory(MemoryStore):
    def __init__(self):
        super().__init__()
        self.overview_calls = []

    def overview(self, *, limit=None, offset=0):
        self.overview_calls.append((limit, offset))
        if limit is None:
            raise AppError('workbench_query_limit', 'The full estate exceeds the response budget.')
        return {'objects': [self.inspect(OBJECT)], 'freshness': 'fresh',
                'pagination': {'limit': limit, 'offset': offset, 'total': 1000, 'has_more': True}}


class DictionaryCapacityTests(unittest.TestCase):
    def test_selected_policy_avoids_full_inventory_and_keeps_vendor_separation(self):
        store = LargeInventory()
        result = dictionary(store, DEFINITION, object_id=OBJECT)
        self.assertEqual(store.overview_calls, [])
        self.assertEqual(result['observation_scope'], {'kind': 'object', 'object_id': OBJECT})
        row = result['entries'][0]
        self.assertEqual([r['object_id'] for r in row['actual_uses']], [OBJECT])
        self.assertFalse(row['vendor_documentation'][0]['graph_value_translation_verified'])
        self.assertFalse(result['execution_authorized'])

    def test_explicit_page_retains_honest_inventory_denominator(self):
        store = LargeInventory()
        result = dictionary(store, DEFINITION, limit=10, offset=20)
        self.assertEqual(store.overview_calls, [(10, 20)])
        self.assertEqual(result['observation_scope']['kind'], 'page')
        self.assertEqual(result['observation_scope']['pagination'],
                         {'limit': 10, 'offset': 20, 'total': 1000, 'has_more': True})
        self.assertEqual(len(result['entries'][0]['actual_uses']), 1)

    def test_unpaged_overbudget_query_still_fails_instead_of_truncating(self):
        with self.assertRaises(AppError) as failure:
            dictionary(LargeInventory(), DEFINITION)
        self.assertEqual(failure.exception.code, 'workbench_query_limit')

    def test_object_and_page_scope_cannot_be_ambiguous(self):
        for options in ({'limit': 10}, {'offset': 1}):
            with self.subTest(options=options), self.assertRaises(AppError):
                dictionary(LargeInventory(), DEFINITION, object_id=OBJECT, **options)

    def test_missing_selected_object_is_not_an_empty_dictionary(self):
        with self.assertRaises(AppError):
            dictionary(LargeInventory(), DEFINITION,
                       object_id='33333333-3333-4333-8333-333333333333')


if __name__ == '__main__':
    unittest.main()
